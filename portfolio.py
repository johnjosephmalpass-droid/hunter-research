#!/usr/bin/env python3
"""HUNTER Portfolio -- Paper trading engine.

Usage:
    python portfolio.py log      # Log new positions from unlogged hypotheses
    python portfolio.py update   # Update prices and P&L for open positions
    python portfolio.py report   # Generate HTML report
"""

import json
import os
import statistics
import sys
from datetime import datetime, timedelta

import anthropic
import yfinance as yf
from dotenv import load_dotenv

from config import MODEL, MODEL_FAST
from database import (
    close_position,
    get_all_positions,
    get_closed_positions,
    get_open_positions,
    get_portfolio_snapshots,
    get_portfolio_stats,
    get_unlogged_hypotheses,
    init_db,
    save_portfolio_position,
    save_portfolio_snapshot,
    update_position_price,
)

load_dotenv(override=True)

# ============================================================
# Constants
# ============================================================
STARTING_CAPITAL = 1_000_000  # GBP
MAX_POSITION_PCT = 0.01     # 1% max per position = GBP 10k
MIN_SCORE_TO_LOG = 70       # Only diamonds 70+ get positions
AUTO_LOG_ENABLED = False    # Set True to auto-log, False for review-only mode


# ============================================================
# Helpers
# ============================================================

def _get_client():
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def score_to_allocation_pct(diamond_score):
    """Small allocations for tracking: score 50 = GBP 5k, score 100 = GBP 10k on 1M base."""
    return min(diamond_score / 10000, 0.01)  # Max 1% per position = GBP 10k


def extract_ticker_direction(hypothesis_text, action_steps, full_report):
    """Use Haiku to extract ticker and direction from hypothesis."""
    client = _get_client()

    text_block = f"HYPOTHESIS: {(hypothesis_text or '')[:500]}\n\nACTION: {(action_steps or '')[:500]}"
    if full_report:
        text_block += f"\n\nREPORT EXCERPT: {full_report[:500]}"

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            temperature=0.1,
            system="You are a portfolio construction specialist. Given an investment thesis, you identify the single best liquid equity vehicle that most cleanly expresses the novel mechanism. Return ONLY a JSON object.",
            messages=[{
                "role": "user",
                "content": f"""Read this investment thesis carefully. Then identify the BEST tradeable vehicle.

{text_block}

CRITICAL RULES — read these before answering:
- DO NOT pick the most obvious company mentioned in the thesis. Pick the instrument whose price movement would MOST DIRECTLY reflect whether the thesis mechanism is correct.
- If the thesis is about a specific company with $500M-$50B market cap, that company's stock is usually right.
- If the thesis is about a sector-wide mechanism (like appraisal contamination), pick the company MOST EXPOSED to that specific mechanism, not a broad ETF.
- NEVER use broad sector ETFs (IYR, XLF, XLE) unless the thesis is genuinely about the whole sector. A thesis about Northern Virginia office buildings should NOT use IYR.
- If the thesis names specific tickers in its trade structure, use those.
- If the thesis has a long AND short leg, pick the PRIMARY leg (the one with the most direct mechanism exposure).
- For pharma theses: pick the specific company with the highest revenue concentration on the drug in question, NOT Pfizer or Merck (too diversified).
- direction: "long" if undervalued/will rise, "short" if overvalued/will fall.
- If you genuinely cannot determine a ticker, use "MANUAL".

Respond with ONLY a JSON object:
{{"ticker": "XYZ", "direction": "long", "reasoning": "One sentence explaining why this vehicle"}}"""
            }],
        )

        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)
        ticker = data.get("ticker", "MANUAL").upper().strip()
        direction = data.get("direction", "long").lower().strip()
        if direction not in ("long", "short"):
            direction = "long"
        return {"ticker": ticker, "direction": direction}

    except Exception as e:
        print(f"  [WARN] Ticker extraction failed: {e}")
        return {"ticker": "MANUAL", "direction": "long"}


def fetch_price(ticker):
    """Get current price via yfinance. Returns None if invalid."""
    if ticker == "MANUAL":
        return None
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty:
            return None
        return round(float(hist["Close"].iloc[-1]), 4)
    except Exception:
        return None


def fetch_spy_return(start_date):
    """Return SPY total return % from start_date to today."""
    try:
        spy = yf.Ticker("SPY")
        hist = spy.history(start=start_date)
        if len(hist) < 2:
            return 0.0
        return round((hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100, 2)
    except Exception:
        return 0.0


def calculate_sharpe(closed_positions, risk_free_rate=0.04):
    """Calculate simplified Sharpe ratio from closed position returns."""
    returns = [p["pnl_pct"] / 100 for p in closed_positions if p.get("pnl_pct") is not None]
    if len(returns) < 2:
        return 0.0
    avg = statistics.mean(returns)
    std = statistics.stdev(returns)
    if std == 0:
        return 0.0
    return round((avg * 12 - risk_free_rate) / (std * (12 ** 0.5)), 2)


# ============================================================
# Commands
# ============================================================

def extract_trade_legs(hypothesis_text, action_steps, full_report, diamond_score):
    """Use Sonnet to extract ALL trade legs from a thesis - not just one ticker."""
    client = _get_client()
    text_block = f"THESIS: {(hypothesis_text or '')[:600]}\nACTION: {(action_steps or '')[:400]}"
    if full_report:
        text_block += f"\nREPORT: {full_report[:600]}"

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            temperature=0.1,
            system="You are a portfolio construction specialist. Extract ALL trade legs from an investment thesis. Return ONLY JSON.",
            messages=[{"role": "user", "content": f"""Read this thesis and extract EVERY tradeable position it implies.

{text_block}

Rules:
- Extract ALL legs of the trade, not just one. If the thesis says "short X, long Y" that's two positions.
- For each position, pick the instrument whose price MOST DIRECTLY expresses the thesis mechanism.
- DO NOT use broad ETFs (IYR, XLF, XLE) unless the thesis is genuinely about the whole sector.
- For pharma theses, pick the specific company with highest single-drug revenue concentration, NOT diversified giants like Pfizer or Merck.
- If the thesis names specific tickers, use those.
- Each leg gets capital proportional to its importance to the thesis.

Return JSON:
{{
    "positions": [
        {{"ticker": "XYZ", "direction": "long", "reasoning": "one sentence", "weight": 0.6}},
        {{"ticker": "ABC", "direction": "short", "reasoning": "one sentence", "weight": 0.4}}
    ]
}}

The weights should sum to 1.0. The primary leg gets the most weight."""}],
        )

        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)
        return data.get("positions", [])
    except Exception as e:
        print(f"  [WARN] Trade leg extraction failed: {e}")
        # Fallback to single ticker extraction
        result = extract_ticker_direction(hypothesis_text, action_steps, full_report)
        return [{"ticker": result["ticker"], "direction": result["direction"], "reasoning": "fallback", "weight": 1.0}]


def cmd_log():
    """Log new positions from unlogged hypotheses. Only runs if AUTO_LOG_ENABLED=True."""
    if not AUTO_LOG_ENABLED:
        print("Auto-logging is DISABLED. Use 'python portfolio.py review' to see proposed positions.")
        print("To log manually, set AUTO_LOG_ENABLED = True in portfolio.py or use the dashboard.")
        return

    init_db()
    hypotheses = get_unlogged_hypotheses(min_score=MIN_SCORE_TO_LOG)

    if not hypotheses:
        print("No new hypotheses to log.")
        return

    print(f"\nFound {len(hypotheses)} unlogged hypotheses (score >= {MIN_SCORE_TO_LOG}):\n")

    # Calculate current portfolio value
    stats = get_portfolio_stats()
    portfolio_value = stats["total_value"]

    # Lazy import so portfolio.py still runs if these modules fail
    try:
        from thesis_dedup import is_thesis_duplicate
        DEDUP_ON = True
    except Exception:
        DEDUP_ON = False
    try:
        from portfolio_feedback import compute_score_adjustment, log_adjustment
        FEEDBACK_ON = True
    except Exception:
        FEEDBACK_ON = False

    for h in hypotheses:
        score = h.get("diamond_score", 50) or 50
        print(f"  Processing #{h['id']} (score {score})...")

        # ── NEW: Thesis-level dedup ──
        # Reject if the thesis is near-duplicate of any currently-open position.
        # This is the fix for the CMBS cluster (VNO+SLG+PLD identical theses).
        if DEDUP_ON:
            try:
                dup = is_thesis_duplicate(
                    hypothesis_text=h.get("hypothesis_text", ""),
                    action_steps=h.get("action_steps", ""),
                )
                if dup["is_duplicate"]:
                    sim = dup["similar_to"]
                    print(f"  [DEDUP-BLOCK] {sim['ticker']} {sim['direction']} "
                          f"sim={dup['similarity']:.2f} — skipping")
                    continue
                if dup["is_variant"]:
                    sim = dup["similar_to"]
                    print(f"  [DEDUP-WARN]  {sim['ticker']} {sim['direction']} "
                          f"sim={dup['similarity']:.2f} — proceeding with reduced size")
                    # Reduce capital to 50% for variants
                    h["_capital_multiplier"] = 0.5
            except Exception as e:
                print(f"  [DEDUP] skipped ({e})")

        # ── NEW: Portfolio → scoring feedback ──
        # Adjust effective score based on realised P&L of similar past theses
        effective_score = float(score)
        if FEEDBACK_ON:
            try:
                adj = compute_score_adjustment(h.get("hypothesis_text", ""), float(score))
                effective_score = adj["adjusted_score"]
                if adj["adjustment"] != 0:
                    print(f"  [FEEDBACK] raw={score} → adjusted={effective_score:.1f} "
                          f"({adj['adjustment']:+.1f}, {adj['num_related']} related closed)")
                log_adjustment(h["id"], float(score), adj)
                if effective_score < MIN_SCORE_TO_LOG:
                    print(f"  [FEEDBACK-BLOCK] adjusted score below threshold, skipping")
                    continue
                # Rescale capital proportional to adjusted score
                h["_score_adjusted"] = effective_score
            except Exception as e:
                print(f"  [FEEDBACK] skipped ({e})")

        # Step 1: Auto-generate PDF if not already done
        reports_dir = os.path.join(os.path.dirname(__file__), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        report_name = f"HUNTER_Thesis_{h['id']}.pdf"
        report_path = os.path.join(reports_dir, report_name)
        if not os.path.exists(report_path) and score >= 50:
            print(f"  [PDF] Generating enriched PDF...")
            try:
                import subprocess as _sp
                result = _sp.run(["python", "enrich_thesis.py", str(h["id"])],
                               capture_output=True, text=True, timeout=120,
                               cwd=os.path.dirname(os.path.abspath(__file__)))
                if result.returncode == 0:
                    print(f"  [PDF] Generated: {report_name}")
                else:
                    print(f"  [PDF] Generation failed (non-fatal)")
            except Exception:
                print(f"  [PDF] Generation failed (non-fatal)")

        # Step 2: Extract ALL trade legs using Sonnet
        print(f"  [TRADES] Extracting trade legs...")
        legs = extract_trade_legs(
            h.get("hypothesis_text", ""),
            h.get("action_steps", ""),
            h.get("full_report", ""),
            score,
        )

        if not legs:
            print(f"  [WARN] No trade legs extracted, skipping")
            continue

        # Step 3: Log each leg as a separate position
        # Use adjusted score if feedback ran, apply dedup-variant multiplier
        alloc_score = h.get("_score_adjusted", score)
        total_alloc_pct = score_to_allocation_pct(alloc_score)
        total_alloc_pct *= h.get("_capital_multiplier", 1.0)
        total_capital = portfolio_value * total_alloc_pct

        for leg in legs:
            ticker = (leg.get("ticker") or "MANUAL").upper().strip()
            direction = (leg.get("direction") or "long").lower().strip()
            if direction not in ("long", "short"):
                direction = "long"
            weight = float(leg.get("weight", 1.0 / len(legs)))
            capital = round(total_capital * weight, 2)
            reasoning = leg.get("reasoning", "")

            # Fetch entry price
            entry_price = fetch_price(ticker)
            if entry_price is None and ticker != "MANUAL":
                print(f"  [WARN] Could not fetch price for {ticker}, setting to MANUAL")
                ticker = "MANUAL"

            # Validate ticker is actively trading before logging
            if ticker != "MANUAL":
                entry_price = fetch_price(ticker)
                if entry_price is None:
                    print(f"  [SKIP] {ticker} - no price data (possibly delisted). Skipping.")
                    continue

            # Save position
            try:
                pos_id = save_portfolio_position(
                    hypothesis_id=None,
                    ticker=ticker,
                    direction=direction,
                    entry_price=entry_price,
                    entry_date=datetime.now().strftime("%Y-%m-%d"),
                    capital_allocated=capital,
                    time_window_days=h.get("time_window_days") or 90,
                    diamond_score=score,
                    confidence=h.get("confidence", "Medium"),
                    hypothesis_text=f"{h.get('hypothesis_text', '')[:200]} | {reasoning}",
                    full_report=h.get("full_report", ""),
                    domains=h.get("domains_involved", ""),
                )
                arrow = "\u2191" if direction == "long" else "\u2193"
                price_str = f"${entry_price:.2f}" if entry_price else "MANUAL"
                print(f"  [LOGGED] #{pos_id} | {ticker} {arrow} {direction} | entry {price_str} | GBP {capital:,.0f} | {reasoning[:60]}")
            except Exception as e:
                if "UNIQUE" in str(e):
                    print(f"  [SKIP] {ticker} already logged")
                else:
                    print(f"  [ERROR] {e}")

        # Mark hypothesis as logged by saving a dummy link
        try:
            save_portfolio_position(
                hypothesis_id=h["id"], ticker="LOGGED", direction="long",
                entry_price=0, entry_date=datetime.now().strftime("%Y-%m-%d"),
                capital_allocated=0, time_window_days=0, diamond_score=score,
                confidence="", hypothesis_text="", full_report="", domains="",
            )
        except: pass

    print(f"\nPortfolio value: GBP {portfolio_value:,.0f}")


def cmd_update():
    """Update prices and P&L for all open positions."""
    init_db()
    positions = get_open_positions()

    if not positions:
        print("No open positions to update.")
        return

    print(f"\nUpdating {len(positions)} open positions:\n")
    today = datetime.now().strftime("%Y-%m-%d")

    for p in positions:
        ticker = p["ticker"]
        if ticker == "MANUAL":
            print(f"  [{ticker}] #{p['id']} - skipped (manual ticker)")
            continue

        # Fetch current price
        current_price = fetch_price(ticker)
        if current_price is None:
            print(f"  [{ticker}] #{p['id']} - price fetch failed, skipped")
            continue

        entry_price = p["entry_price"]
        if not entry_price:
            print(f"  [{ticker}] #{p['id']} - no entry price, skipped")
            continue

        capital = p["capital_allocated"] or 0

        # Direction-aware P&L
        if p["direction"] == "long":
            pnl_pct = round((current_price - entry_price) / entry_price * 100, 2)
        else:  # short
            pnl_pct = round((entry_price - current_price) / entry_price * 100, 2)

        pnl_gbp = round(capital * (pnl_pct / 100), 2)

        # Check expiry
        entry_date = p.get("entry_date", "")
        time_window = p.get("time_window_days") or 90
        try:
            entry_dt = datetime.strptime(entry_date, "%Y-%m-%d")
            expiry_dt = entry_dt + timedelta(days=time_window)
            expired = datetime.now() > expiry_dt
        except (ValueError, TypeError):
            expired = False

        if expired:
            close_position(p["id"], current_price, today, "expired", pnl_pct, pnl_gbp)
            status = "CLOSED (expired)"
        else:
            update_position_price(p["id"], current_price, today, pnl_pct, pnl_gbp)
            status = "updated"

        color = "\033[92m" if pnl_pct >= 0 else "\033[91m"
        reset = "\033[0m"
        print(f"  [{ticker}] #{p['id']} | {color}{pnl_pct:+.2f}% (GBP {pnl_gbp:+,.0f}){reset} | {status}")

    # Save daily snapshot
    stats = get_portfolio_stats()
    all_pos = get_all_positions()
    earliest = min((p.get("entry_date", today) for p in all_pos), default=today)
    spy_return = fetch_spy_return(earliest)

    save_portfolio_snapshot(
        date=today,
        total_value=stats["total_value"],
        total_return_pct=stats["total_return_pct"],
        spy_return_pct=spy_return,
        num_open=stats["num_open"],
        num_closed=stats["num_closed"],
        win_rate=stats["win_rate"],
    )

    print(f"\n  Portfolio: GBP {stats['total_value']:,.0f} ({stats['total_return_pct']:+.2f}%)")
    print(f"  SPY benchmark: {spy_return:+.2f}%")
    print(f"  Alpha: {stats['total_return_pct'] - spy_return:+.2f}%")
    print(f"  Open: {stats['num_open']} | Closed: {stats['num_closed']} | Win rate: {stats['win_rate']:.0f}%")


def cmd_report():
    """Generate self-contained HTML portfolio report."""
    init_db()
    stats = get_portfolio_stats()
    open_pos = get_open_positions()
    closed_pos = get_closed_positions()
    all_pos = get_all_positions()
    snapshots = get_portfolio_snapshots()

    # SPY benchmark
    earliest = min((p.get("entry_date", "") for p in all_pos if p.get("entry_date")), default="")
    spy_return = fetch_spy_return(earliest) if earliest else 0.0
    sharpe = calculate_sharpe(closed_pos)

    # Domain breakdown
    domain_returns = {}
    for p in all_pos:
        domains = (p.get("domains") or "").split(",")
        for d in domains:
            d = d.strip()
            if d:
                if d not in domain_returns:
                    domain_returns[d] = []
                domain_returns[d].append(p.get("pnl_pct", 0) or 0)

    domain_avg = {d: round(statistics.mean(rets), 2) if rets else 0 for d, rets in domain_returns.items()}

    # Confidence calibration
    conf_buckets = {}
    for p in closed_pos:
        conf = p.get("confidence", "Medium")
        if conf not in conf_buckets:
            conf_buckets[conf] = []
        conf_buckets[conf].append(p.get("pnl_pct", 0) or 0)

    conf_cal = {c: {"avg_return": round(statistics.mean(rets), 2), "count": len(rets), "win_rate": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1)} for c, rets in conf_buckets.items() if rets}

    # Top 3 closed trades
    top3 = sorted(closed_pos, key=lambda p: p.get("pnl_pct", 0) or 0, reverse=True)[:3]

    now = datetime.now().strftime("%B %d, %Y at %H:%M")

    def _pos_rows(positions):
        rows = ""
        for p in positions:
            pnl = p.get("pnl_pct", 0) or 0
            pnl_color = "#00ff88" if pnl >= 0 else "#ff4444"
            arrow = "\u2191" if p["direction"] == "long" else "\u2193"
            entry = f"${p['entry_price']:.2f}" if p.get("entry_price") else "MANUAL"
            current = f"${p['current_price']:.2f}" if p.get("current_price") else "-"
            pnl_gbp = p.get("pnl_gbp", 0) or 0

            rows += f"""<tr>
                <td>{p.get('ticker', '?')}</td>
                <td>{arrow} {p['direction']}</td>
                <td>{entry}</td>
                <td>{current}</td>
                <td style="color:{pnl_color}">{pnl:+.2f}%</td>
                <td style="color:{pnl_color}">GBP {pnl_gbp:+,.0f}</td>
                <td>{p.get('diamond_score', '?')}</td>
                <td>{p.get('confidence', '?')}</td>
                <td>{p.get('entry_date', '?')}</td>
            </tr>"""
        return rows

    # Pre-build top calls HTML (avoids nested f-string issues)
    top_calls_html = ""
    if top3:
        top_calls_html = "<h2>Top Calls</h2>"
        for i, p in enumerate(top3):
            t = p.get("ticker", "?")
            d = p.get("direction", "?")
            pnl = p.get("pnl_pct", 0) or 0
            thesis = (p.get("hypothesis_text", "") or "")[:500]
            top_calls_html += f'<h3>{i+1}. {t} ({d}) - {pnl:+.2f}%</h3>'
            top_calls_html += f'<div class="thesis-box">{thesis}</div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HUNTER Portfolio Report</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ background: #0e1117; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 40px; }}
    h1 {{ color: #00ff88; font-size: 2em; margin-bottom: 5px; }}
    h2 {{ color: #ff8800; font-size: 1.4em; margin: 30px 0 15px; border-bottom: 1px solid #333; padding-bottom: 8px; }}
    h3 {{ color: #ffcc00; font-size: 1.1em; margin: 20px 0 10px; }}
    .subtitle {{ color: #888; font-size: 0.9em; margin-bottom: 30px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin: 20px 0; }}
    .card {{ background: #1a1d23; border-radius: 10px; padding: 20px; text-align: center; border: 1px solid #333; }}
    .card .value {{ font-size: 1.8em; font-weight: bold; margin: 5px 0; }}
    .card .label {{ color: #888; font-size: 0.85em; }}
    .green {{ color: #00ff88; }}
    .red {{ color: #ff4444; }}
    .orange {{ color: #ff8800; }}
    table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
    th {{ background: #1a1d23; color: #ff8800; padding: 10px; text-align: left; font-size: 0.85em; }}
    td {{ padding: 8px 10px; border-bottom: 1px solid #222; font-size: 0.85em; }}
    tr:hover {{ background: #1a1d23; }}
    .thesis-box {{ background: #1a1d23; border-left: 3px solid #00ff88; padding: 15px; margin: 10px 0; border-radius: 5px; font-size: 0.85em; line-height: 1.5; }}
    .footer {{ color: #555; font-size: 0.75em; margin-top: 40px; text-align: center; border-top: 1px solid #333; padding-top: 15px; }}
    .confidential {{ color: #ff4444; font-size: 0.8em; text-transform: uppercase; letter-spacing: 2px; }}
</style>
</head>
<body>

<p class="confidential">Confidential</p>
<h1>HUNTER Portfolio Report</h1>
<p class="subtitle">Generated {now} | Paper Trading | Inception: GBP 100,000</p>

<h2>Portfolio Summary</h2>
<div class="cards">
    <div class="card">
        <div class="label">Total Value</div>
        <div class="value {'green' if stats['total_return_pct'] >= 0 else 'red'}">GBP {stats['total_value']:,.0f}</div>
    </div>
    <div class="card">
        <div class="label">Return</div>
        <div class="value {'green' if stats['total_return_pct'] >= 0 else 'red'}">{stats['total_return_pct']:+.2f}%</div>
    </div>
    <div class="card">
        <div class="label">SPY Benchmark</div>
        <div class="value">{spy_return:+.2f}%</div>
    </div>
    <div class="card">
        <div class="label">Alpha</div>
        <div class="value {'green' if stats['total_return_pct'] - spy_return >= 0 else 'red'}">{stats['total_return_pct'] - spy_return:+.2f}%</div>
    </div>
    <div class="card">
        <div class="label">Win Rate</div>
        <div class="value">{stats['win_rate']:.0f}%</div>
    </div>
    <div class="card">
        <div class="label">Sharpe Ratio</div>
        <div class="value">{sharpe:.2f}</div>
    </div>
    <div class="card">
        <div class="label">Open Positions</div>
        <div class="value">{stats['num_open']}</div>
    </div>
    <div class="card">
        <div class="label">Closed Positions</div>
        <div class="value">{stats['num_closed']}</div>
    </div>
</div>

<h2>Open Positions</h2>
{"<p style='color:#888'>No open positions.</p>" if not open_pos else f'''
<table>
<tr><th>Ticker</th><th>Direction</th><th>Entry</th><th>Current</th><th>P&L %</th><th>P&L GBP</th><th>Score</th><th>Confidence</th><th>Opened</th></tr>
{_pos_rows(open_pos)}
</table>'''}

<h2>Closed Positions</h2>
{"<p style='color:#888'>No closed positions yet.</p>" if not closed_pos else f'''
<table>
<tr><th>Ticker</th><th>Direction</th><th>Entry</th><th>Current</th><th>P&L %</th><th>P&L GBP</th><th>Score</th><th>Confidence</th><th>Opened</th></tr>
{_pos_rows(closed_pos)}
</table>'''}

<h2>Domain Performance</h2>
{"<p style='color:#888'>No domain data yet.</p>" if not domain_avg else f'''
<table>
<tr><th>Domain</th><th>Positions</th><th>Avg Return</th></tr>
{"".join(f'<tr><td>{d}</td><td>{len(domain_returns[d])}</td><td style="color:{"#00ff88" if v >= 0 else "#ff4444"}">{v:+.2f}%</td></tr>' for d, v in sorted(domain_avg.items(), key=lambda x: -x[1]))}
</table>'''}

<h2>Confidence Calibration</h2>
{"<p style='color:#888'>No closed positions for calibration.</p>" if not conf_cal else f'''
<table>
<tr><th>Confidence</th><th>Positions</th><th>Avg Return</th><th>Win Rate</th></tr>
{"".join(f'<tr><td>{c}</td><td>{v["count"]}</td><td style="color:{"#00ff88" if v["avg_return"] >= 0 else "#ff4444"}">{v["avg_return"]:+.2f}%</td><td>{v["win_rate"]:.0f}%</td></tr>' for c, v in conf_cal.items())}
</table>'''}

{top_calls_html}

<h2>Analytics</h2>
<div class="cards">
    <div class="card">
        <div class="label">Avg Return (Closed)</div>
        <div class="value {'green' if stats['avg_return'] >= 0 else 'red'}">{stats['avg_return']:+.2f}%</div>
    </div>
    <div class="card">
        <div class="label">Best Trade</div>
        <div class="value green">{stats['best_trade']:+.2f}%</div>
    </div>
    <div class="card">
        <div class="label">Worst Trade</div>
        <div class="value red">{stats['worst_trade']:+.2f}%</div>
    </div>
</div>

<div class="footer">
    <p>HUNTER Autonomous Fact-Collision Intelligence Engine</p>
    <p>Paper trading portfolio - not financial advice</p>
    <p>Generated {now}</p>
</div>

</body>
</html>"""

    report_path = os.path.join(os.path.dirname(__file__), "HUNTER_Portfolio_Report.html")
    with open(report_path, "w") as f:
        f.write(html)

    print(f"\nReport generated: {report_path}")
    print(f"\n  Portfolio: GBP {stats['total_value']:,.0f} ({stats['total_return_pct']:+.2f}%)")
    print(f"  SPY: {spy_return:+.2f}% | Alpha: {stats['total_return_pct'] - spy_return:+.2f}%")
    print(f"  Open: {stats['num_open']} | Closed: {stats['num_closed']} | Win rate: {stats['win_rate']:.0f}%")
    print(f"  Sharpe: {sharpe:.2f}")


# ============================================================
# Main
# ============================================================

def cmd_review():
    """Show proposed positions for review without logging them."""
    init_db()
    hypotheses = get_unlogged_hypotheses(min_score=MIN_SCORE_TO_LOG)

    if not hypotheses:
        print("No new hypotheses to review.")
        return

    print(f"\n{'='*60}")
    print(f"PROPOSED POSITIONS FOR REVIEW")
    print(f"{'='*60}\n")

    stats = get_portfolio_stats()
    portfolio_value = stats["total_value"]

    for h in hypotheses:
        score = h.get("diamond_score", 50) or 50
        print(f"Hypothesis #{h['id']} (Score {score})")
        print(f"  {h.get('hypothesis_text', '')[:120]}")
        print()

        legs = extract_trade_legs(
            h.get("hypothesis_text", ""),
            h.get("action_steps", ""),
            h.get("full_report", ""),
            score,
        )

        total_alloc = portfolio_value * score_to_allocation_pct(score)

        for leg in legs:
            ticker = (leg.get("ticker") or "MANUAL").upper()
            direction = leg.get("direction", "long")
            weight = float(leg.get("weight", 1.0 / len(legs)))
            capital = round(total_alloc * weight, 2)
            reasoning = leg.get("reasoning", "")
            price = fetch_price(ticker)
            price_str = f"${price:.2f}" if price else "NO DATA"
            arrow = "\u2191" if direction == "long" else "\u2193"
            status = "\u2705" if price else "\u274c DELISTED/INVALID"

            print(f"  {status} {ticker} {arrow} {direction} | {price_str} | GBP {capital:,.0f} ({weight*100:.0f}%)")
            print(f"     Reason: {reasoning[:80]}")

        print(f"\n  Total allocation: GBP {total_alloc:,.0f}")
        print(f"  {'='*50}\n")

    print("To log these positions, run: python portfolio.py log")
    print("To override a ticker, update the hypothesis action_steps first.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python portfolio.py [log|update|report|review]")
        print("  log    - Log new positions from surviving hypotheses")
        print("  update - Update prices and P&L for open positions")
        print("  report - Generate HTML portfolio report")
        print("  review - Preview proposed positions before logging")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "log":
        cmd_log()
    elif cmd == "update":
        cmd_update()
    elif cmd == "report":
        cmd_report()
    elif cmd == "review":
        cmd_review()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
