"""Public pre-registered prediction board.

Generates a static HTML page listing every surviving hypothesis with:
 - thesis one-liner
 - diamond score
 - date posted
 - target resolution date (created_at + time_window_days)
 - countdown
 - status (pending / resolved-win / resolved-loss / expired-unresolved)
 - verification link (hypothesis id → report page)

The whole point: every prediction is timestamped and public. Win or lose,
both go on the ledger. After 12 months you have a track record nobody
can replicate without 12 months of real time.

Output is static HTML suitable for GitHub Pages or any static host. No
server needed. Regenerate daily with a cron job.

Usage:
    python prediction_board.py             # regenerate HTML
    python prediction_board.py resolve 328 win "NAIC Q1 filings showed reserve increase as predicted"
    python prediction_board.py resolve 328 loss "No reserve increase materialised"
    python prediction_board.py stats       # track record summary
"""

import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from database import get_connection


HERE = Path(__file__).parent
OUT_HTML = HERE / "public" / "predictions.html"
OUT_JSON = HERE / "public" / "predictions.json"


# ══════════════════════════════════════════════════════════════════════
# Schema — prediction_outcomes captures resolved predictions
# ══════════════════════════════════════════════════════════════════════

def _ensure_tables():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS prediction_outcomes (
                hypothesis_id INTEGER PRIMARY KEY REFERENCES hypotheses(id),
                outcome TEXT CHECK(outcome IN ('win', 'loss', 'partial', 'unresolved')),
                resolution_date TEXT,
                resolution_evidence TEXT,
                resolution_url TEXT,
                resolved_by TEXT DEFAULT 'manual',
                resolved_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS prediction_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hypothesis_id INTEGER REFERENCES hypotheses(id),
                event_type TEXT,
                event_data TEXT,
                event_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════
# Data gathering
# ══════════════════════════════════════════════════════════════════════

def gather_predictions(min_score: int = 65) -> list:
    """Return all surviving hypotheses with score >= min_score, joined
    with any resolved outcome. Sorted by target-date ascending."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT h.id, h.diamond_score, h.confidence, h.hypothesis_text,
                   h.action_steps, h.time_window_days, h.created_at,
                   c.source_types, c.num_domains,
                   p.outcome, p.resolution_date, p.resolution_evidence, p.resolution_url
            FROM hypotheses h
            LEFT JOIN collisions c ON c.id = h.collision_id
            LEFT JOIN prediction_outcomes p ON p.hypothesis_id = h.id
            WHERE h.survived_kill = 1 AND h.diamond_score >= ?
            ORDER BY h.created_at
        """, (min_score,)).fetchall()
    finally:
        conn.close()

    predictions = []
    now = datetime.now()
    for row in rows:
        (hid, score, conf, text, actions, window, created_at,
         source_types, num_domains, outcome, res_date, res_evidence, res_url) = row

        try:
            created_dt = datetime.fromisoformat(str(created_at).replace(" ", "T"))
        except (ValueError, TypeError):
            created_dt = now
        target_dt = created_dt + timedelta(days=int(window or 90))
        days_elapsed = (now - created_dt).days
        days_remaining = (target_dt - now).days

        # Status logic
        if outcome in ("win", "loss", "partial"):
            status = f"resolved_{outcome}"
        elif now > target_dt:
            status = "expired_unresolved"
        else:
            status = "pending"

        predictions.append({
            "id": hid,
            "diamond_score": score,
            "confidence": conf or "Medium",
            "thesis": (text or "")[:500],
            "thesis_short": (text or "")[:140] + ("..." if len(text or "") > 140 else ""),
            "action_steps": (actions or "")[:400],
            "source_types": source_types or "",
            "num_domains": num_domains or 0,
            "posted_date": created_dt.strftime("%Y-%m-%d"),
            "target_date": target_dt.strftime("%Y-%m-%d"),
            "window_days": window or 90,
            "days_elapsed": days_elapsed,
            "days_remaining": days_remaining,
            "status": status,
            "outcome": outcome,
            "resolution_date": res_date,
            "resolution_evidence": (res_evidence or "")[:600],
            "resolution_url": res_url,
        })
    return predictions


def compute_track_record(predictions: list) -> dict:
    total = len(predictions)
    resolved = [p for p in predictions if p["status"].startswith("resolved_")]
    wins = [p for p in resolved if p["outcome"] == "win"]
    losses = [p for p in resolved if p["outcome"] == "loss"]
    partials = [p for p in resolved if p["outcome"] == "partial"]
    pending = [p for p in predictions if p["status"] == "pending"]
    expired = [p for p in predictions if p["status"] == "expired_unresolved"]

    # Brier score would require probability forecasts; we approximate with
    # confidence-level string mapped to p
    conf_map = {"Low": 0.35, "Medium": 0.55, "High": 0.70, "Very High": 0.85}
    brier_terms = []
    for p in resolved:
        p_hat = conf_map.get(p["confidence"], 0.55)
        outcome_bit = 1.0 if p["outcome"] == "win" else (0.5 if p["outcome"] == "partial" else 0.0)
        brier_terms.append((p_hat - outcome_bit) ** 2)
    brier = sum(brier_terms) / max(1, len(brier_terms)) if brier_terms else None

    # Calibration by confidence bucket
    cal = {}
    for p in resolved:
        conf = p["confidence"] or "Medium"
        if conf not in cal:
            cal[conf] = {"n": 0, "wins": 0, "partials": 0}
        cal[conf]["n"] += 1
        if p["outcome"] == "win":
            cal[conf]["wins"] += 1
        elif p["outcome"] == "partial":
            cal[conf]["partials"] += 1
    for conf, v in cal.items():
        v["hit_rate"] = (v["wins"] + 0.5 * v["partials"]) / max(1, v["n"])

    return {
        "total_predictions": total,
        "resolved": len(resolved),
        "wins": len(wins),
        "losses": len(losses),
        "partials": len(partials),
        "pending": len(pending),
        "expired_unresolved": len(expired),
        "hit_rate": (len(wins) + 0.5 * len(partials)) / max(1, len(resolved)) if resolved else None,
        "brier_score": round(brier, 4) if brier is not None else None,
        "calibration": cal,
    }


# ══════════════════════════════════════════════════════════════════════
# HTML rendering — inline CSS, no external dependencies
# ══════════════════════════════════════════════════════════════════════

CSS = """
:root {
  --bg: #0b0d12;
  --card: #141821;
  --border: #262d3d;
  --text: #e6e9ef;
  --muted: #8892a3;
  --accent: #ffb23f;
  --win: #4ade80;
  --loss: #f87171;
  --pending: #60a5fa;
  --expired: #a78bfa;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 40px 24px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg); color: var(--text);
  line-height: 1.5;
}
.container { max-width: 1040px; margin: 0 auto; }
header { margin-bottom: 40px; border-bottom: 1px solid var(--border); padding-bottom: 24px; }
header h1 { margin: 0 0 8px 0; font-size: 1.8rem; color: var(--accent); }
header .sub { color: var(--muted); font-size: 0.95rem; }
header .manifesto { margin-top: 16px; padding: 16px; background: var(--card); border-radius: 8px; border-left: 3px solid var(--accent); font-size: 0.9rem; }
.summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 32px; }
.stat { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.stat .label { color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; }
.stat .value { font-size: 1.6rem; font-weight: 600; margin-top: 4px; }
.prediction {
  background: var(--card); border: 1px solid var(--border); border-radius: 10px;
  padding: 20px; margin-bottom: 16px;
}
.prediction .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; gap: 12px; }
.prediction .header .id { font-family: ui-monospace, monospace; color: var(--muted); font-size: 0.85rem; }
.prediction .header .status { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
.status.pending { background: rgba(96,165,250,0.15); color: var(--pending); border: 1px solid var(--pending); }
.status.resolved_win { background: rgba(74,222,128,0.15); color: var(--win); border: 1px solid var(--win); }
.status.resolved_loss { background: rgba(248,113,113,0.15); color: var(--loss); border: 1px solid var(--loss); }
.status.resolved_partial { background: rgba(255,178,63,0.15); color: var(--accent); border: 1px solid var(--accent); }
.status.expired_unresolved { background: rgba(167,139,250,0.15); color: var(--expired); border: 1px solid var(--expired); }
.prediction .thesis { font-weight: 500; margin-bottom: 12px; }
.prediction .meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; font-size: 0.85rem; color: var(--muted); margin-bottom: 12px; }
.prediction .meta div span { display: block; color: var(--text); font-weight: 500; margin-top: 2px; }
.prediction .resolution { margin-top: 12px; padding: 12px; background: rgba(74,222,128,0.06); border-left: 2px solid var(--win); border-radius: 4px; font-size: 0.9rem; }
.prediction.loss .resolution { background: rgba(248,113,113,0.06); border-left-color: var(--loss); }
.prediction .countdown { font-family: ui-monospace, monospace; font-size: 0.85rem; }
.positive { color: var(--pending); }
.past { color: var(--loss); }
footer { margin-top: 60px; color: var(--muted); font-size: 0.8rem; text-align: center; border-top: 1px solid var(--border); padding-top: 24px; }
footer a { color: var(--accent); text-decoration: none; }
details summary { cursor: pointer; color: var(--muted); font-size: 0.85rem; margin-top: 8px; }
details[open] summary { margin-bottom: 8px; }
"""


def render_html(predictions: list, track_record: dict) -> str:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    hr = track_record["hit_rate"]
    hr_str = f"{hr:.1%}" if hr is not None else "—"
    brier_str = f"{track_record['brier_score']}" if track_record["brier_score"] is not None else "—"

    # Sort: pending by closest-to-resolving, then resolved by most recent, then expired
    def sort_key(p):
        if p["status"] == "pending":
            return (0, p["days_remaining"])
        if p["status"].startswith("resolved_"):
            return (1, -(p.get("resolved_at_ts") or 0))
        return (2, p["days_remaining"])
    predictions_sorted = sorted(predictions, key=sort_key)

    cards = []
    for p in predictions_sorted:
        status_class = p["status"]
        status_label = {
            "pending": "Pending",
            "resolved_win": "Won",
            "resolved_loss": "Lost",
            "resolved_partial": "Partial",
            "expired_unresolved": "Expired",
        }.get(status_class, "Unknown")

        countdown = ""
        if p["status"] == "pending":
            countdown = f'<span class="positive">{p["days_remaining"]}d remaining</span>'
        elif p["status"] == "expired_unresolved":
            countdown = f'<span class="past">expired {abs(p["days_remaining"])}d ago</span>'
        else:
            countdown = f'resolved on {p.get("resolution_date") or "—"}'

        resolution_block = ""
        if p["status"].startswith("resolved_"):
            evidence = (p.get("resolution_evidence") or "").strip()
            url = p.get("resolution_url")
            link = f' <a href="{url}" target="_blank">source</a>' if url else ""
            resolution_block = f'<div class="resolution"><strong>Outcome:</strong> {evidence}{link}</div>'

        extra_class = "loss" if p["status"] == "resolved_loss" else ""

        card = f"""
<article class="prediction {extra_class}">
  <div class="header">
    <div class="id">#{p['id']}</div>
    <span class="status {status_class}">{status_label}</span>
  </div>
  <div class="thesis">{_escape(p['thesis_short'])}</div>
  <div class="meta">
    <div>Score<span>{p['diamond_score']}/100</span></div>
    <div>Confidence<span>{p['confidence']}</span></div>
    <div>Posted<span>{p['posted_date']}</span></div>
    <div>Target<span>{p['target_date']}</span></div>
    <div>Window<span>{p['window_days']}d</span></div>
    <div>Domains<span>{p['num_domains']}</span></div>
    <div>Status<span class="countdown">{countdown}</span></div>
  </div>
  {resolution_block}
  <details>
    <summary>Full thesis + source types</summary>
    <div style="font-size:0.88rem; color:var(--text); margin-top:8px;">
      <p>{_escape(p['thesis'])}</p>
      <p style="color:var(--muted); margin-top:8px;"><strong>Source types:</strong> {_escape(p['source_types'] or '—')}</p>
    </div>
  </details>
</article>"""
        cards.append(card)

    cards_html = "\n".join(cards) if cards else "<p style='color:var(--muted)'>No predictions posted yet.</p>"

    html = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HUNTER Public Prediction Board</title>
<style>{CSS}</style>
</head><body>
<div class="container">

<header>
  <h1>HUNTER Public Prediction Board</h1>
  <div class="sub">Every surviving hypothesis with a target-date resolution. Win or loss, both go on the ledger.</div>
  <div class="manifesto">
    <strong>Rules of the board:</strong> Every prediction is posted before its outcome is known. Resolution dates are fixed at time of posting (thesis window + posting date). Outcomes are resolved against public evidence only; no retroactive adjustment. Failures stay visible forever. This is a solo-operator research project in the <em>compositional alpha</em> framework. Methodology: <a href="methodology.html">methodology brief</a>. Code: <a href="https://github.com/" target="_blank">GitHub</a>. Pre-registration: <code>preregistration.json</code> with locked code hash.
  </div>
</header>

<section class="summary">
  <div class="stat"><div class="label">Total posted</div><div class="value">{track_record['total_predictions']}</div></div>
  <div class="stat"><div class="label">Pending</div><div class="value">{track_record['pending']}</div></div>
  <div class="stat"><div class="label">Resolved</div><div class="value">{track_record['resolved']}</div></div>
  <div class="stat"><div class="label">Hit rate</div><div class="value">{hr_str}</div></div>
  <div class="stat"><div class="label">Brier score</div><div class="value">{brier_str}</div></div>
  <div class="stat"><div class="label">Expired unresolved</div><div class="value">{track_record['expired_unresolved']}</div></div>
</section>

<section class="predictions">
{cards_html}
</section>

<footer>
  <div>Generated {generated}. Auto-regenerated daily.</div>
  <div style="margin-top:8px;">John Malpass · BSc Economics · University College Dublin · 2026</div>
</footer>

</div></body></html>"""
    return html


def _escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ══════════════════════════════════════════════════════════════════════
# Generate output
# ══════════════════════════════════════════════════════════════════════

def build():
    _ensure_tables()
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)

    predictions = gather_predictions(min_score=65)
    track_record = compute_track_record(predictions)

    html = render_html(predictions, track_record)
    OUT_HTML.write_text(html)

    OUT_JSON.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(),
        "track_record": track_record,
        "predictions": predictions,
    }, indent=2, default=str))

    print(f"✓ {len(predictions)} predictions rendered to {OUT_HTML}")
    print(f"✓ Track record: {track_record['wins']}W / {track_record['losses']}L / "
          f"{track_record['partials']}P / {track_record['pending']} pending")
    return OUT_HTML


# ══════════════════════════════════════════════════════════════════════
# Resolve / audit CLI
# ══════════════════════════════════════════════════════════════════════

def resolve(hypothesis_id: int, outcome: str, evidence: str, url: str = None):
    if outcome not in ("win", "loss", "partial", "unresolved"):
        raise ValueError("outcome must be one of: win, loss, partial, unresolved")
    _ensure_tables()
    conn = get_connection()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO prediction_outcomes
            (hypothesis_id, outcome, resolution_date, resolution_evidence, resolution_url)
            VALUES (?, ?, ?, ?, ?)
        """, (hypothesis_id, outcome, datetime.now().strftime("%Y-%m-%d"), evidence, url))
        conn.execute("""
            INSERT INTO prediction_audit (hypothesis_id, event_type, event_data)
            VALUES (?, 'resolve', ?)
        """, (hypothesis_id, json.dumps({"outcome": outcome, "evidence": evidence, "url": url})))
        conn.commit()
    finally:
        conn.close()
    print(f"✓ Hypothesis #{hypothesis_id} resolved as {outcome.upper()}")


def print_stats():
    preds = gather_predictions(min_score=65)
    tr = compute_track_record(preds)
    print(f"\nHUNTER Track Record")
    print(f"{'=' * 50}")
    print(f"Total posted:       {tr['total_predictions']}")
    print(f"Pending:            {tr['pending']}")
    print(f"Resolved:           {tr['resolved']} "
          f"({tr['wins']}W / {tr['losses']}L / {tr['partials']}P)")
    print(f"Expired unresolved: {tr['expired_unresolved']}")
    if tr['hit_rate'] is not None:
        print(f"Hit rate:           {tr['hit_rate']:.1%}")
    if tr['brier_score'] is not None:
        print(f"Brier score:        {tr['brier_score']}")
    if tr['calibration']:
        print(f"\nCalibration by confidence:")
        for conf, v in tr['calibration'].items():
            print(f"  {conf:<12} n={v['n']}  hit={v['hit_rate']:.1%}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        build()
    elif cmd == "resolve":
        if len(sys.argv) < 5:
            print("Usage: python prediction_board.py resolve <id> <win|loss|partial> <evidence> [url]")
            sys.exit(1)
        hid = int(sys.argv[2])
        outcome = sys.argv[3]
        evidence = sys.argv[4]
        url = sys.argv[5] if len(sys.argv) > 5 else None
        resolve(hid, outcome, evidence, url)
        build()
    elif cmd == "stats":
        print_stats()
    else:
        print(__doc__)
