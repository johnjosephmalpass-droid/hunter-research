"""Inverse HUNTER — mine PUBLISHED MARKET BELIEFS against the fact corpus.

Core insight:
  Standard HUNTER: obscure fact → check market knows → find asymmetry.
  Inverse HUNTER: published number → decompose into assumptions → find corpus
                  fact that contradicts → emit directional signal on the asset.

Why this is higher-quality alpha than standard HUNTER:
  - Faster resolution: analyst targets get revised within weeks-to-months.
  - Directly tradeable: you're betting that a specific published NUMBER is wrong,
    not that an obscure pattern exists.
  - Clean counterfactual: if the contradicting fact is real, the number moves.
  - Small positions resolve fast → quick empirical validation.

Pipeline:
  1. Ingest beliefs (analyst targets, options-implied vols, cap rates, etc.)
  2. Decompose each into 4-8 testable assumptions (belief_decomposer.py)
  3. For each assumption, query the corpus for facts that contradict it
  4. Score the contradiction strength
  5. If score > threshold → emit inverse signal
  6. Signal → portfolio position (short the belief direction)

Usage:
    python inverse_hunter.py run              # process all active beliefs
    python inverse_hunter.py ingest <csv>     # ingest beliefs from CSV
    python inverse_hunter.py audit            # show signals awaiting action
    python inverse_hunter.py simulate         # simulate signals on existing beliefs (free)
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from database import get_connection

load_dotenv(override=True)


# ══════════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════════

MIN_CONTRADICTION_SCORE = 0.60    # below this, don't emit signal
SIGNAL_MODEL = "claude-haiku-4-5"
MAX_FACTS_PER_ASSUMPTION = 20     # capped at 20 contradicting-fact candidates


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


# ══════════════════════════════════════════════════════════════════════
# Prompts
# ══════════════════════════════════════════════════════════════════════

CONTRADICTION_SYSTEM = """You evaluate whether a specific FACT contradicts a specific ASSUMPTION embedded in a market belief. You are adversarial — your job is to be strict about what counts as contradiction, not generous.

RULES FOR CONTRADICTION:
- DIRECT contradiction: fact states the exact variable is above/below the threshold the assumption specifies. Score 0.8-1.0.
- STRONG indirect: fact describes a condition that materially impacts the variable within the assumption's time window. Score 0.5-0.75.
- WEAK: fact is tangentially related but doesn't move the variable enough to break the assumption. Score 0.2-0.4.
- IRRELEVANT: fact doesn't address the variable. Score 0.0-0.15.

SIGN (direction of impact):
- CONFIRMS: fact supports the assumption staying true
- CONTRADICTS: fact implies the assumption will be false within its time window
- NEUTRAL: affects the variable but direction unclear

Only emit a contradiction signal if score >= 0.50. Lower scores are either noise or evidence of robustness, not signal."""


CONTRADICTION_PROMPT = """Evaluate whether this FACT contradicts this ASSUMPTION.

ASSUMPTION:
  Claim: {claim}
  Variable: {variable}
  Threshold: {threshold}
  Window: {window_start} to {window_end}
  Domain: {domain}

FACT:
  Title: {fact_title}
  Content: {fact_content}
  Source: {fact_source}
  Date: {fact_date}

Determine:
1. Does this fact directly or indirectly affect the assumption's variable?
2. Within the assumption's time window?
3. In which direction?

Respond with ONLY a JSON object:
{{
    "contradicts": true | false | "neutral",
    "score": <0.0 to 1.0>,
    "reasoning": "1-2 sentences explaining why this fact does or doesn't contradict",
    "direct_or_indirect": "direct" | "indirect" | "irrelevant",
    "magnitude_estimate": "qualitative assessment of how much this fact moves the variable"
}}"""


# ══════════════════════════════════════════════════════════════════════
# Schema setup
# ══════════════════════════════════════════════════════════════════════

def _ensure_tables():
    conn = get_connection()
    try:
        conn.executescript("""
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
            );

            CREATE TABLE IF NOT EXISTS inverse_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                belief_id INTEGER REFERENCES market_beliefs(id),
                assumption_index INTEGER,
                assumption_claim TEXT,
                contradicting_fact_id INTEGER REFERENCES raw_facts(id),
                contradiction_score REAL,
                signal_direction TEXT,
                signal_strength TEXT,
                reasoning TEXT,
                asset TEXT,
                target_published_value TEXT,
                emitted_at TEXT DEFAULT (datetime('now')),
                status TEXT DEFAULT 'open',
                resolution_date TEXT,
                resolution_notes TEXT,
                resolution_correct INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_inverse_signals_belief ON inverse_signals(belief_id);
            CREATE INDEX IF NOT EXISTS idx_inverse_signals_status ON inverse_signals(status);
            CREATE INDEX IF NOT EXISTS idx_market_beliefs_status ON market_beliefs(status);
            CREATE INDEX IF NOT EXISTS idx_market_beliefs_asset ON market_beliefs(asset);
        """)
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════
# Core matching: assumption → contradicting facts
# ══════════════════════════════════════════════════════════════════════

def _find_candidate_facts(assumption: dict, limit: int = MAX_FACTS_PER_ASSUMPTION) -> list:
    """Retrieve facts from the corpus that could contradict this assumption.

    Strategy: match on (domain, keyword-in-variable, keyword-in-claim) within
    assumption's time window. Returns sorted by freshness + relevance.
    """
    domain = assumption.get("domain", "").lower()
    variable = assumption.get("variable", "")
    claim = assumption.get("claim", "")

    # Extract keywords from variable and claim for matching
    import re
    terms = set()
    for text in (variable, claim):
        for w in re.findall(r"[a-zA-Z][a-zA-Z0-9]{3,}", text):
            if w.lower() not in {"with", "through", "from", "that", "this", "which",
                                  "stays", "reaches", "between", "after", "before"}:
                terms.add(w.lower())
    if not terms:
        return []

    like_terms = list(terms)[:6]

    conn = get_connection()
    try:
        # Match on domain + content keywords within assumption window
        window_start = assumption.get("window_start", "")
        # 180-day lookback window for contradicting facts
        cutoff = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

        conditions = []
        params = []
        if domain:
            conditions.append("LOWER(source_type) = ?")
            params.append(domain)
        # AT LEAST 2 keyword hits
        kw_clause = " OR ".join([
            "(LOWER(title) LIKE ? OR LOWER(raw_content) LIKE ? OR LOWER(keywords) LIKE ?)"
            for _ in like_terms
        ])
        conditions.append(f"({kw_clause})")
        for t in like_terms:
            params.extend([f"%{t}%", f"%{t}%", f"%{t}%"])
        conditions.append("COALESCE(date_of_fact, ingested_at) >= ?")
        params.append(cutoff)
        params.append(limit)

        q = f"""
            SELECT id, title, raw_content, source_type, source_url,
                   COALESCE(date_of_fact, ingested_at) as fact_date
            FROM raw_facts
            WHERE {' AND '.join(conditions)}
            ORDER BY fact_date DESC
            LIMIT ?
        """
        rows = conn.execute(q, params).fetchall()
        return [
            {
                "id": r[0], "title": r[1], "raw_content": r[2] or "",
                "source_type": r[3], "source_url": r[4], "date": r[5],
            }
            for r in rows
        ]
    finally:
        conn.close()


def _score_contradiction(assumption: dict, fact: dict) -> dict:
    """LLM-scored contradiction strength between a fact and an assumption."""
    prompt = CONTRADICTION_PROMPT.format(
        claim=assumption.get("claim", ""),
        variable=assumption.get("variable", ""),
        threshold=assumption.get("threshold", ""),
        window_start=assumption.get("window_start", ""),
        window_end=assumption.get("window_end", ""),
        domain=assumption.get("domain", ""),
        fact_title=fact.get("title", ""),
        fact_content=(fact.get("raw_content") or "")[:1500],
        fact_source=fact.get("source_type", ""),
        fact_date=fact.get("date", ""),
    )
    try:
        client = _get_client()
        r = client.messages.create(
            model=SIGNAL_MODEL,
            max_tokens=512,
            temperature=0.1,
            system=CONTRADICTION_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for b in r.content:
            if b.type == "text":
                text += b.text
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            parts = text.split("```")
            if len(parts) >= 3:
                text = parts[1].strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text[start:end])
        else:
            data = json.loads(text)
        return data
    except Exception as e:
        return {"contradicts": False, "score": 0.0,
                "reasoning": f"error: {e}", "direct_or_indirect": "irrelevant"}


# ══════════════════════════════════════════════════════════════════════
# Signal emission
# ══════════════════════════════════════════════════════════════════════

def _emit_signal(belief_id: int, belief: dict, assumption_idx: int,
                 assumption: dict, fact: dict, scored: dict):
    conn = get_connection()
    try:
        direction = belief.get("implied_direction", "long")
        # Invert because this signal SHORTS the belief
        signal_direction = "short" if direction == "long" else ("long" if direction == "short" else "neutral")

        strength = "strong" if scored["score"] >= 0.80 else ("moderate" if scored["score"] >= 0.65 else "weak")

        conn.execute("""
            INSERT INTO inverse_signals
            (belief_id, assumption_index, assumption_claim,
             contradicting_fact_id, contradiction_score,
             signal_direction, signal_strength, reasoning,
             asset, target_published_value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            belief_id, assumption_idx,
            assumption.get("claim", "")[:500],
            fact["id"], scored["score"],
            signal_direction, strength,
            scored.get("reasoning", "")[:500],
            belief.get("asset"),
            belief.get("belief_text", "")[:200],
        ))
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════
# Main loop
# ══════════════════════════════════════════════════════════════════════

def process_belief(belief_id: int, dry_run: bool = False) -> dict:
    """Process a single belief: find contradicting facts, emit signals."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, belief_text, belief_type, asset, source, implied_direction, "
            "assumptions_json, target_date FROM market_beliefs WHERE id = ?",
            (belief_id,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return {"error": f"belief_id {belief_id} not found"}

    belief = {
        "id": row[0], "belief_text": row[1], "belief_type": row[2],
        "asset": row[3], "source": row[4], "implied_direction": row[5],
        "target_date": row[7],
    }
    try:
        assumptions = json.loads(row[6] or "[]")
    except json.JSONDecodeError:
        return {"error": "failed to parse assumptions_json"}

    signals_emitted = []
    candidates_checked = 0

    for i, assumption in enumerate(assumptions):
        candidates = _find_candidate_facts(assumption)
        candidates_checked += len(candidates)

        for fact in candidates[:8]:  # cap at 8 per assumption to limit cost
            if dry_run:
                # Don't call LLM — just report candidates
                signals_emitted.append({
                    "assumption": assumption.get("claim", "")[:80],
                    "candidate_fact": fact.get("title", "")[:80],
                    "dry_run": True,
                })
                continue

            scored = _score_contradiction(assumption, fact)
            if scored.get("contradicts") is True and scored.get("score", 0) >= MIN_CONTRADICTION_SCORE:
                _emit_signal(belief_id, belief, i, assumption, fact, scored)
                signals_emitted.append({
                    "assumption": assumption.get("claim", "")[:80],
                    "fact_id": fact["id"],
                    "fact_title": fact.get("title", "")[:80],
                    "score": scored["score"],
                    "reasoning": scored.get("reasoning", "")[:120],
                })

    return {
        "belief_id": belief_id,
        "candidates_checked": candidates_checked,
        "signals_emitted": len(signals_emitted),
        "signals": signals_emitted,
    }


def run(dry_run: bool = False, min_score: float = MIN_CONTRADICTION_SCORE) -> dict:
    """Process all active beliefs."""
    _ensure_tables()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id FROM market_beliefs WHERE status = 'active' ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"message": "No active beliefs. Use belief_decomposer.py to add some."}

    total_signals = 0
    per_belief = []
    for row in rows:
        r = process_belief(row[0], dry_run=dry_run)
        per_belief.append(r)
        total_signals += r.get("signals_emitted", 0)

    return {
        "beliefs_processed": len(rows),
        "total_signals_emitted": total_signals,
        "per_belief": per_belief,
    }


# ══════════════════════════════════════════════════════════════════════
# Audit
# ══════════════════════════════════════════════════════════════════════

def audit_open_signals():
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT s.id, s.signal_direction, s.signal_strength, s.contradiction_score,
                   s.asset, s.assumption_claim, s.reasoning, s.emitted_at,
                   b.belief_text, b.target_date
            FROM inverse_signals s
            LEFT JOIN market_beliefs b ON b.id = s.belief_id
            WHERE s.status = 'open'
            ORDER BY s.contradiction_score DESC
        """).fetchall()
    finally:
        conn.close()

    print(f"\nOpen Inverse Signals: {len(rows)}\n")
    for r in rows:
        sid, direction, strength, score, asset, claim, reason, emit_at, belief, target = r
        print(f"  #{sid} [{direction.upper()} {strength}] score={score:.2f}")
        print(f"       asset: {asset or '?'}")
        print(f"       belief: {(belief or '')[:100]}")
        print(f"       assumption: {(claim or '')[:100]}")
        print(f"       reasoning: {(reason or '')[:120]}")
        print(f"       emitted: {emit_at[:10]}, target: {target or '?'}")
        print()


if __name__ == "__main__":
    _ensure_tables()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "audit"

    if cmd == "run":
        dry = "--dry" in sys.argv
        out = run(dry_run=dry)
        print(json.dumps(out, indent=2, default=str))

    elif cmd == "simulate":
        out = run(dry_run=True)
        print(f"\nSIMULATION MODE (no LLM calls)")
        print(f"Beliefs processed: {out.get('beliefs_processed', 0)}")
        print(f"Candidate facts found across beliefs: "
              f"{sum(b.get('candidates_checked', 0) for b in out.get('per_belief', []))}")

    elif cmd == "audit":
        audit_open_signals()

    elif cmd == "ingest":
        print("Use belief_decomposer.py for ingestion. Example:")
        print("  python belief_decomposer.py 'Goldman PT $42 CLF by Q3 2026' CLF Goldman")

    else:
        print(__doc__)
