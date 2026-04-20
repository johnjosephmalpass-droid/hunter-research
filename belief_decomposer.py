"""Belief decomposer — translate a published market belief into testable
physical-world assumptions.

A "belief" is anything the market has priced into a specific number:
  - An analyst price target ($X for ticker Y by date Z)
  - An options-implied volatility (~N% implied move by date)
  - A credit spread (bond Y trading at X bps spread)
  - A consensus estimate (sell-side average EPS for next quarter)
  - A cap rate / DCF assumption published in research
  - An actuarial loss rate published by rating agency or insurer
  - A regulatory compliance cost estimate

Each belief encodes ASSUMPTIONS about the physical world. If any assumption
fails, the belief is wrong. Inverse HUNTER's job is to find assumptions
contradicted by facts in the corpus.

This module does the DECOMPOSITION: belief → list of specific testable claims.

Usage:
    from belief_decomposer import decompose_belief

    claims = decompose_belief(
        belief_text="Goldman Sachs PT $42 for Cleveland-Cliffs by end Q3 2026",
        source_type="analyst_target",
        asset="CLF",
    )
    # Returns list of structured claims, each falsifiable.
"""

import json
import os
from datetime import datetime
from typing import Optional

import anthropic
from dotenv import load_dotenv

from database import get_connection

load_dotenv(override=True)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


DECOMPOSE_SYSTEM = """You are a quantitative analyst who understands that every published market number is a compressed bet on specific physical-world conditions. Your job is to DECOMPOSE a given published number into the explicit assumptions it encodes, each as a falsifiable claim.

CRITICAL RULES:
- Each assumption must be EMPIRICALLY TESTABLE against objective facts (commodity prices, regulatory filings, production rates, court decisions, announced layoffs, patent grants, trade data).
- Each assumption must have a TIMELINE — it's true "through X date" or "by Y date."
- Each assumption must name the DOMAIN an analyst would normally track for that claim (so HUNTER can search the right corpus region).
- Do NOT list vague claims like "market conditions stable." Every assumption must reference specific variables, thresholds, or events.
- Aim for 4-8 assumptions per belief. Fewer means you're being too high-level; more means too decomposed.

Example — for "Goldman PT $42 CLF by Q3 2026":
1. HRC steel price stays > $780/ton through Q3 2026 (domain: commodity)
2. Coking coal price stays < $260/ton through Q3 2026 (domain: commodity)
3. Cleveland-Cliffs' EBITDA margins stay > 9.5% through Q3 2026 (domain: earnings)
4. No new OSHA silica enforcement adds > $8/ton compliance through Q3 2026 (domain: regulation)
5. Automotive steel demand stays within 6% of 2025 baseline (domain: sec_filing / earnings)
6. No major blast furnace outage at Cleveland or IH6 (domain: sec_filing)
7. Domestic steel import tariff regime unchanged through Q3 2026 (domain: regulation)
8. USD/CNY does not appreciate >8% vs current (affects import cost dynamics) (domain: commodity)

Each of these is independently testable. If any fails, the $42 target is wrong.

Respond with ONLY a JSON object."""


DECOMPOSE_PROMPT = """Decompose this published market belief into falsifiable assumptions.

BELIEF: {belief_text}

BELIEF TYPE: {belief_type}
ASSET (if applicable): {asset}
PUBLISHED BY: {source}
PUBLISHED DATE: {published_date}
TARGET DATE: {target_date}

Decompose this into 4-8 specific empirical assumptions. Each must be:
- Testable against objective corpus facts
- Dated (what window must it hold)
- Domain-tagged (which HUNTER source type to search)
- Falsifiable (a specific fact could contradict it)

Respond with ONLY a JSON object:
{{
    "belief_summary": "one-line restatement of what the belief claims",
    "implied_direction": "<long|short|neutral>",
    "assumptions": [
        {{
            "claim": "the specific testable claim",
            "variable": "the variable this depends on (e.g. HRC steel price, EBITDA margin, compliance cost)",
            "threshold": "the numeric threshold if applicable (e.g. '>780/ton', '<0.095', 'no outage')",
            "window_start": "YYYY-MM-DD",
            "window_end": "YYYY-MM-DD",
            "domain": "commodity | earnings | regulation | sec_filing | patent | insurance | ...",
            "contradiction_would_mean": "if false, the belief's direction flips to <...>",
            "confidence_this_is_testable": <0.0-1.0>
        }}
    ]
}}"""


def decompose_belief(
    belief_text: str,
    belief_type: str = "analyst_target",
    asset: Optional[str] = None,
    source: Optional[str] = None,
    published_date: Optional[str] = None,
    target_date: Optional[str] = None,
    model: str = "claude-haiku-4-5",
    persist: bool = True,
) -> dict:
    """Decompose a belief into testable assumptions."""
    prompt = DECOMPOSE_PROMPT.format(
        belief_text=belief_text,
        belief_type=belief_type,
        asset=asset or "not specified",
        source=source or "unknown",
        published_date=published_date or "unknown",
        target_date=target_date or "unknown",
    )
    client = _get_client()
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        temperature=0.2,
        system=DECOMPOSE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = ""
    for b in response.content:
        if b.type == "text":
            text += b.text
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Find first { and last }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
        else:
            return {"error": "failed to parse", "raw": text[:500]}

    if persist:
        _persist_belief(data, belief_text, belief_type, asset, source,
                        published_date, target_date)

    return data


def _persist_belief(data, belief_text, belief_type, asset, source,
                    published_date, target_date):
    """Save decomposed belief to market_beliefs table (auto-creates)."""
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_beliefs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                belief_text TEXT NOT NULL,
                belief_type TEXT,
                asset TEXT,
                source TEXT,
                implied_direction TEXT,
                published_date TEXT,
                target_date TEXT,
                belief_summary TEXT,
                assumptions_json TEXT,
                n_assumptions INTEGER,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            INSERT INTO market_beliefs
            (belief_text, belief_type, asset, source, implied_direction,
             published_date, target_date, belief_summary, assumptions_json, n_assumptions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            belief_text, belief_type, asset, source,
            data.get("implied_direction"),
            published_date, target_date,
            data.get("belief_summary"),
            json.dumps(data.get("assumptions", [])),
            len(data.get("assumptions", [])),
        ))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python belief_decomposer.py '<belief text>' [asset] [source]")
        print("Example: python belief_decomposer.py 'Goldman PT $42 CLF by Q3 2026' CLF Goldman")
        sys.exit(1)

    belief = sys.argv[1]
    asset = sys.argv[2] if len(sys.argv) > 2 else None
    source = sys.argv[3] if len(sys.argv) > 3 else None

    result = decompose_belief(belief, asset=asset, source=source)
    print(json.dumps(result, indent=2))
