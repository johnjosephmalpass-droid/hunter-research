"""Negative inference — reasoning from what's ABSENT.

Current HUNTER reasons from what EXISTS (facts present in the corpus).
This module reasons from what's MISSING. If A, B, C are known and the
NATURAL fourth piece D should be present but isn't, D's absence is the
signal.

Three specific patterns:

 1. Entity-completion gaps: a set of entities usually appears together;
    if 3 of 4 are present in the corpus for a recent period and the 4th
    isn't, that absence is informative.

 2. Source-type balance gaps: a topic should appear in N source types to
    be "priced in" — if it appears in 2/N, the other (N-2) silos haven't
    absorbed it yet. That's a window.

 3. Causal-chain gaps: chain A → B → C exists and B → C → D usually
    follows, but D doesn't appear yet. The gap between C and D is the
    lag — and the lag is the edge.

All deterministic — no LLM calls. Runs against the corpus only.

Run:
    python negative_inference.py scan          # find all 3 gap types
    python negative_inference.py balance       # source-type balance gaps only
    python negative_inference.py chain         # chain-lag gaps only
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from database import get_connection


def _ensure_tables():
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS negative_inferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gap_type TEXT,
                description TEXT,
                present_count INTEGER,
                expected_count INTEGER,
                missing_description TEXT,
                related_fact_ids TEXT,
                severity REAL,
                detected_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════
# Pattern 1: source-type balance
# ══════════════════════════════════════════════════════════════════════

def source_type_balance_gaps(min_present: int = 2, expected_min: int = 4,
                              lookback_days: int = 60) -> list:
    """Find entities that appear in 2+ source types but should logically
    appear in 4+. The missing source types are the uncovered silos."""
    conn = get_connection()
    try:
        # Entity → set of source types in last lookback_days
        cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        rows = conn.execute("""
            SELECT fe.entity_name_lower, rf.source_type, COUNT(*) as cnt
            FROM fact_entities fe
            JOIN raw_facts rf ON rf.id = fe.raw_fact_id
            WHERE COALESCE(rf.date_of_fact, rf.ingested_at) >= ?
            GROUP BY fe.entity_name_lower, rf.source_type
            HAVING cnt >= 1
        """, (cutoff,)).fetchall()

        by_entity = defaultdict(set)
        fact_ids_by_entity = defaultdict(list)
        for entity, st, _ in rows:
            by_entity[entity].add(st)

        # For each entity, fetch fact ids
        for entity in list(by_entity.keys()):
            fids = conn.execute("""
                SELECT raw_fact_id FROM fact_entities WHERE entity_name_lower = ? LIMIT 10
            """, (entity,)).fetchall()
            fact_ids_by_entity[entity] = [r[0] for r in fids]
    finally:
        conn.close()

    gaps = []
    all_source_types_ever = set()
    for stset in by_entity.values():
        all_source_types_ever.update(stset)

    for entity, sts in by_entity.items():
        if len(sts) < min_present:
            continue
        if len(sts) >= expected_min:
            continue
        missing = all_source_types_ever - sts
        if not missing:
            continue
        severity = 1.0 - (len(sts) / expected_min)
        gaps.append({
            "gap_type": "source_type_balance",
            "entity": entity,
            "present_source_types": sorted(sts),
            "missing_source_types": sorted(missing)[:6],
            "present_count": len(sts),
            "expected_count": expected_min,
            "severity": round(severity, 3),
            "related_fact_ids": fact_ids_by_entity[entity][:5],
        })
    gaps.sort(key=lambda g: -g["severity"])
    return gaps


# ══════════════════════════════════════════════════════════════════════
# Pattern 2: chain lag
# ══════════════════════════════════════════════════════════════════════

def chain_lag_gaps() -> list:
    """For every chain of depth >= 2, look at the final link's 'next_practitioners'
    or 'output_change' field. If those practitioners DON'T appear as authors
    of any recent fact matching that output, the chain has a detected lag."""
    conn = get_connection()
    try:
        chain_rows = conn.execute("""
            SELECT id, collision_id, chain_links, chain_length FROM chains
            WHERE chain_length >= 2
        """).fetchall()
    finally:
        conn.close()

    gaps = []
    for cid, coll_id, links_json, clen in chain_rows:
        try:
            links = json.loads(links_json or "[]")
        except json.JSONDecodeError:
            continue
        if not links:
            continue
        last = links[-1]
        if not isinstance(last, dict):
            continue

        # Extract key phrases from the final link
        next_prac = (last.get("practitioners") or last.get("next_practitioners") or "")[:200]
        output = (last.get("output_change") or last.get("disruption") or "")[:200]
        if not next_prac or not output:
            continue

        # Search for recent facts matching both the output and the next_practitioners
        # If none found → lag gap exists
        conn = get_connection()
        try:
            # Simple keyword check
            kw_output = [w for w in output.lower().split() if len(w) > 4][:4]
            if not kw_output:
                conn.close()
                continue
            like_clauses = " AND ".join(["LOWER(raw_content) LIKE ?"] * len(kw_output))
            params = [f"%{w}%" for w in kw_output]
            params.append((datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d"))
            matching = conn.execute(f"""
                SELECT COUNT(*) FROM raw_facts
                WHERE {like_clauses} AND COALESCE(date_of_fact, ingested_at) >= ?
            """, params).fetchone()[0]
        finally:
            conn.close()

        if matching == 0:
            gaps.append({
                "gap_type": "chain_lag",
                "chain_id": cid,
                "collision_id": coll_id,
                "chain_length": clen,
                "expected_domain": last.get("domain", "unknown"),
                "expected_practitioners": next_prac,
                "expected_output": output,
                "matching_recent_facts": 0,
                "severity": 0.9,  # high — no downstream evidence = big lag
            })
    return gaps


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def persist_gaps(gaps: list):
    _ensure_tables()
    conn = get_connection()
    try:
        for g in gaps:
            conn.execute("""
                INSERT INTO negative_inferences
                (gap_type, description, present_count, expected_count,
                 missing_description, related_fact_ids, severity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                g.get("gap_type"),
                json.dumps(g)[:800],
                g.get("present_count") or 0,
                g.get("expected_count") or 0,
                json.dumps(g.get("missing_source_types", []) or g.get("expected_output", ""))[:500],
                json.dumps(g.get("related_fact_ids", [])),
                g.get("severity", 0.5),
            ))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    _ensure_tables()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"

    if cmd == "balance":
        gaps = source_type_balance_gaps()
        print(f"\nSource-type balance gaps: {len(gaps)}\n")
        for g in gaps[:20]:
            print(f"  [{g['severity']:.2f}] {g['entity'][:50]:<50} "
                  f"in {len(g['present_source_types'])} types, missing {len(g['missing_source_types'])}")

    elif cmd == "chain":
        gaps = chain_lag_gaps()
        print(f"\nChain-lag gaps: {len(gaps)}\n")
        for g in gaps[:15]:
            print(f"  [chain #{g['chain_id']}] expected in {g['expected_domain']}: "
                  f"{(g['expected_practitioners'] or '')[:70]}")
            print(f"    Expected output: {(g['expected_output'] or '')[:100]}")
            print(f"    Matching recent facts: {g['matching_recent_facts']}")
            print()

    elif cmd == "scan":
        balance_gaps = source_type_balance_gaps()
        chain_gaps = chain_lag_gaps()
        all_gaps = balance_gaps + chain_gaps
        print(f"\nNegative inferences detected: {len(all_gaps)} total")
        print(f"  - Source-type balance gaps: {len(balance_gaps)}")
        print(f"  - Chain-lag gaps: {len(chain_gaps)}")
        persist_gaps(all_gaps)
        print(f"  ✓ Persisted to negative_inferences table")
    else:
        print(__doc__)
