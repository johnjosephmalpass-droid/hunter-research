"""Dynamic obscurity filter — replaces the 15-word hardcoded blocklist.

Problem: the old front-page filter was a hardcoded list ("hormuz", "iran",
"trump tariff", etc.). It's brittle, maintenance-heavy, and only catches
the topics you already thought of. The whole point of HUNTER is to find
non-obvious things — the obvious-thing filter should not itself be manual.

This module computes a corpus-local obscurity score for any hypothesis by:

 1. Extracting the named entities from the hypothesis text + fact chain.
 2. Looking up each entity's corpus frequency in raw_facts.
 3. Counting how many distinct source types mention each entity.
 4. Checking how many published findings already reference these entities.
 5. Computing a score on 0-100 where:
      0   = totally obscure (few facts, one silo)
      50  = normal coverage
      100 = saturated (many facts, many silos, many findings)

Hypotheses above the threshold (default 75) are flagged as potentially
front-page and downscored. Below the threshold is the edge zone.

This is 100% corpus-local — zero web search cost. It's self-calibrating:
as HUNTER finds more facts, the threshold automatically rises.

Optional: a single web-search fallback for hypotheses right at the borderline.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from database import get_connection

logger = logging.getLogger("hunter.obscurity")

# Regex for candidate proper-noun entities (titlecased multi-word phrases,
# acronyms ≥ 2 chars, ticker-like strings)
_ENTITY_RX = re.compile(r"(?:[A-Z][a-zA-Z0-9&]+(?:\s+[A-Z][a-zA-Z0-9&]+)*|[A-Z]{2,6})")

# Stop-phrases (common words that look like entities)
_STOP = {
    "The", "This", "That", "These", "Those", "A", "An",
    "I", "We", "You", "They", "He", "She", "It",
    "Q1", "Q2", "Q3", "Q4", "H1", "H2",
    "HUNTER", "Claude", "Anthropic",
}

# Obscurity score thresholds
OBVIOUS_THRESHOLD = 75  # above this = likely front-page
EDGE_ZONE = (40, 75)    # sweet spot for genuine edge
OBSCURE_THRESHOLD = 40  # below this = very obscure

# Caching the corpus stats for the process lifetime; refresh via refresh_stats()
_corpus_stats_cache = None
_cache_stamp = None
CACHE_TTL_MIN = 60


def _extract_entities(text: str) -> list:
    """Extract candidate entity strings from a text blob."""
    if not text:
        return []
    candidates = _ENTITY_RX.findall(text)
    out = []
    seen = set()
    for c in candidates:
        c = c.strip()
        if not c or c in _STOP or len(c) < 2:
            continue
        if c.lower() in seen:
            continue
        seen.add(c.lower())
        out.append(c)
    return out


def _refresh_corpus_stats():
    """Compute fact frequency and source-type breadth per entity in raw_facts.
    Uses the normalised fact_entities junction table for speed."""
    global _corpus_stats_cache, _cache_stamp
    conn = get_connection()
    try:
        # Entity → (fact_count, distinct_source_type_count)
        rows = conn.execute("""
            SELECT fe.entity_name_lower,
                   COUNT(DISTINCT fe.raw_fact_id) AS fact_count,
                   COUNT(DISTINCT rf.source_type) AS source_count
            FROM fact_entities fe
            JOIN raw_facts rf ON rf.id = fe.raw_fact_id
            GROUP BY fe.entity_name_lower
        """).fetchall()
        entity_freq = {r[0]: {"facts": r[1], "sources": r[2]} for r in rows}

        # Entity mentions in published findings (proxy for "already known")
        finding_rows = conn.execute("""
            SELECT LOWER(title || ' ' || COALESCE(summary, '')) FROM findings
        """).fetchall()
        finding_text = " ".join(r[0] for r in finding_rows)

        # Total corpus size for normalisation
        total_facts = conn.execute("SELECT COUNT(*) FROM raw_facts").fetchone()[0]

        _corpus_stats_cache = {
            "entity_freq": entity_freq,
            "finding_text": finding_text,
            "total_facts": total_facts,
        }
        _cache_stamp = datetime.now()
        return _corpus_stats_cache
    finally:
        conn.close()


def _corpus_stats():
    global _corpus_stats_cache, _cache_stamp
    if _corpus_stats_cache is None or (
        _cache_stamp and datetime.now() - _cache_stamp > timedelta(minutes=CACHE_TTL_MIN)
    ):
        _refresh_corpus_stats()
    return _corpus_stats_cache


def compute_obscurity_score(hypothesis_text: str, fact_chain: Optional[list] = None) -> dict:
    """Return an obscurity score + breakdown.

    Lower score = more obscure = more edge. Score on 0-100.

    Components (each 0-100, averaged):
      - fact_saturation: how many facts mention these entities (normalised)
      - source_breadth: how many silos mention them (normalised)
      - finding_overlap: how many published findings already cover them
    """
    stats = _corpus_stats()
    total_facts = max(1, stats["total_facts"])
    entity_freq = stats["entity_freq"]
    finding_text = stats["finding_text"]

    # Entities: from hypothesis + chain combined
    combined = hypothesis_text or ""
    if fact_chain:
        if isinstance(fact_chain, list):
            for f in fact_chain:
                if isinstance(f, dict):
                    combined += " " + (f.get("title", "") + " " + f.get("raw_content", ""))[:400]
                elif isinstance(f, str):
                    combined += " " + f[:400]
        elif isinstance(fact_chain, str):
            combined += " " + fact_chain[:1000]

    entities = _extract_entities(combined)
    if not entities:
        return {
            "obscurity_score": 50.0,
            "num_entities": 0,
            "top_entities": [],
            "classification": "unknown",
            "reason": "No entities extracted — defaulting to neutral",
        }

    per_entity = []
    for e in entities[:20]:  # cap at 20 to keep cheap
        freq = entity_freq.get(e.lower(), {"facts": 0, "sources": 0})
        # Normalise: 1 fact out of 12k corpus is 0.008% — very obscure.
        # 500 facts is ~4% — saturated.
        fact_pct = (freq["facts"] / total_facts) * 100  # 0..100
        fact_saturation = min(100, fact_pct * 25)  # 4% corpus mention → 100
        source_breadth = min(100, freq["sources"] * 14)  # 7+ sources → 100
        finding_hit = 100 if e.lower() in finding_text else 0
        per_entity.append({
            "entity": e,
            "facts": freq["facts"],
            "sources": freq["sources"],
            "fact_saturation": round(fact_saturation, 1),
            "source_breadth": round(source_breadth, 1),
            "already_in_findings": bool(finding_hit),
        })

    # Score = max of component scores (worst case dominates — if one entity
    # is front-page, the whole thesis is front-page)
    max_fact_sat = max((p["fact_saturation"] for p in per_entity), default=0)
    max_source = max((p["source_breadth"] for p in per_entity), default=0)
    finding_hits = sum(1 for p in per_entity if p["already_in_findings"])
    finding_score = min(100, finding_hits * 20)

    obscurity = round((max_fact_sat * 0.4 + max_source * 0.3 + finding_score * 0.3), 2)

    if obscurity >= OBVIOUS_THRESHOLD:
        classification = "obvious"
        reason = "Entities saturated in corpus / findings — likely front-page, low edge"
    elif obscurity <= OBSCURE_THRESHOLD:
        classification = "obscure"
        reason = "Sparse corpus coverage — high potential edge"
    else:
        classification = "edge_zone"
        reason = "Moderate coverage — edge plausible"

    per_entity.sort(key=lambda p: -(p["fact_saturation"] + p["source_breadth"]))

    return {
        "obscurity_score": obscurity,
        "num_entities": len(entities),
        "top_entities": per_entity[:10],
        "classification": classification,
        "reason": reason,
        "component_scores": {
            "max_fact_saturation": round(max_fact_sat, 2),
            "max_source_breadth": round(max_source, 2),
            "finding_overlap": round(finding_score, 2),
        },
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "audit":
        # Rank existing findings by obscurity
        conn = get_connection()
        rows = conn.execute("""
            SELECT id, title, score, summary FROM findings
            ORDER BY score DESC LIMIT 20
        """).fetchall()
        conn.close()
        print(f"{'ID':>4} {'Score':>5} {'Obs':>5} {'Class':>10}  Title")
        print("-" * 100)
        for fid, title, score, summary in rows:
            combined = f"{title} {summary or ''}"
            r = compute_obscurity_score(combined)
            print(f"{fid:>4} {score:>5} {r['obscurity_score']:>5.1f} "
                  f"{r['classification']:>10}  {title[:60]}")
        sys.exit(0)

    text = sys.stdin.read().strip()
    if not text:
        print("Usage: python obscurity_filter.py audit")
        print("   or: echo 'hypothesis text' | python obscurity_filter.py")
        sys.exit(1)
    r = compute_obscurity_score(text)
    print(json.dumps(r, indent=2))
