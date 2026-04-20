"""Meta-HUNTER — the reflexivity layer.

Framework Layer 13 ("observer-dependent topology") claims that as HUNTER
corrects errors, the error landscape shifts. Operationally: the moment
HUNTER's method is replicated, findings any generic HUNTER would produce
lose their edge. Your moat is the DIFFERENTIAL between what YOUR hunter
finds vs what a generic one would.

This module computes that differential.

Method:
  1. A "generic profile" is defined: default parameters, default source
     weights, default prompts, no learned corpus bias.
  2. For each of your surviving hypotheses, simulate whether a generic
     HUNTER would have found the same thing using the same corpus.
  3. Differential edge score = 1 - P(generic HUNTER finds this)
  4. Weight portfolio sizing and publication priority by differential.

This module NEVER makes new LLM calls when running — it uses heuristics
against the existing corpus. Cheap, fast, deterministic.

The key heuristics for "generic HUNTER would have found this":
  - Source-type pair count is common (high collision count for this pair)
  - Hypothesis uses only first-tier corpus entities (high fact_entities
    frequency)
  - Implication-matching strategy is the primary match (the most
    commonly-used strategy)
  - Narrative strength is high (generic pipeline produces clean narratives)

Conversely, "only YOUR HUNTER would find this":
  - Rare source-type pair
  - Rare entities
  - Multi-strategy match (implication + causal + model-field combination)
  - Weak narrative (structural, not obvious)
  - Cross-silo chain of length >= 4

Usage:
    python meta_hunter.py              # compute differential for all hypotheses
    python meta_hunter.py write        # persist to differential_edge table
    python meta_hunter.py audit        # show hypotheses ranked by differential edge
"""

import json
import sys
from datetime import datetime
from collections import Counter

from database import get_connection


# ══════════════════════════════════════════════════════════════════════
# Schema
# ══════════════════════════════════════════════════════════════════════

def _ensure_tables():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS differential_edge (
                hypothesis_id INTEGER PRIMARY KEY REFERENCES hypotheses(id),
                generic_finds_prob REAL,
                differential_edge REAL,
                pair_commonness REAL,
                entity_commonness REAL,
                strategy_novelty REAL,
                narrative_boringness REAL,
                chain_depth_bonus REAL,
                computed_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════
# Metric components
# ══════════════════════════════════════════════════════════════════════

def _pair_commonness(conn, source_types: list) -> float:
    """How common is this source-type pair across ALL collisions?
    High commonness = generic HUNTER would have found it too."""
    if not source_types or len(source_types) < 2:
        return 0.5
    max_pair_count = 0
    for i in range(len(source_types)):
        for j in range(i + 1, len(source_types)):
            a, b = sorted([source_types[i], source_types[j]])
            row = conn.execute("""
                SELECT COUNT(*) FROM collisions
                WHERE source_types LIKE ? AND source_types LIKE ?
            """, (f"%{a}%", f"%{b}%")).fetchone()
            if row and row[0] > max_pair_count:
                max_pair_count = row[0]
    # Normalise: a pair with 50+ collisions is "common" (0.9+),
    # a pair with 1-2 collisions is "rare" (0.1-)
    return min(1.0, max_pair_count / 50.0)


def _entity_commonness(conn, fact_chain: list) -> float:
    """How common are the entities in this hypothesis?
    High commonness = generic HUNTER's fact_entities search finds them easily."""
    if not fact_chain:
        return 0.5
    fact_ids = [f.get("fact_id") for f in fact_chain if isinstance(f, dict) and f.get("fact_id")]
    if not fact_ids:
        return 0.5

    total_freq = 0
    entity_count = 0
    for fid in fact_ids:
        rows = conn.execute("""
            SELECT fe2.entity_name_lower, COUNT(DISTINCT fe2.raw_fact_id) as freq
            FROM fact_entities fe1
            JOIN fact_entities fe2 ON fe1.entity_name_lower = fe2.entity_name_lower
            WHERE fe1.raw_fact_id = ?
            GROUP BY fe2.entity_name_lower
        """, (fid,)).fetchall()
        for _, freq in rows:
            total_freq += freq
            entity_count += 1
    if entity_count == 0:
        return 0.5
    avg_freq = total_freq / entity_count
    # Normalise: entity appearing in 100+ facts = common (0.9+),
    # entity appearing in 1-3 facts = rare (0.1-)
    return min(1.0, avg_freq / 100.0)


def _narrative_boringness(conn, hypothesis_id: int) -> float:
    """Higher narrative = more generic-findable. Returns 0-1."""
    row = conn.execute(
        "SELECT narrative_strength FROM narrative_scores WHERE hypothesis_id = ?",
        (hypothesis_id,)
    ).fetchone()
    if not row or row[0] is None:
        return 0.5
    return float(row[0])


def _chain_depth_bonus(num_domains: int, chain_length: int) -> float:
    """Deep chains or many domains mean a generic HUNTER probably wouldn't
    have extended that far. Returns 0-1 (higher = more novel)."""
    score = 0.0
    if num_domains >= 4:
        score += 0.4
    elif num_domains == 3:
        score += 0.2
    if chain_length and chain_length >= 4:
        score += 0.4
    elif chain_length and chain_length >= 3:
        score += 0.2
    return min(1.0, score)


# ══════════════════════════════════════════════════════════════════════
# Differential edge scoring
# ══════════════════════════════════════════════════════════════════════

def compute_differential(hypothesis_id: int) -> dict:
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT h.id, h.fact_chain, h.diamond_score, c.source_types,
                   c.num_domains,
                   (SELECT MAX(chain_length) FROM chains WHERE collision_id = h.collision_id)
            FROM hypotheses h
            LEFT JOIN collisions c ON c.id = h.collision_id
            WHERE h.id = ?
        """, (hypothesis_id,)).fetchone()
        if not row:
            return {"error": "hypothesis not found"}

        hid, fact_chain_json, score, source_types_json, num_domains, chain_len = row
        try:
            fact_chain = json.loads(fact_chain_json or "[]")
        except json.JSONDecodeError:
            fact_chain = []
        try:
            source_types = json.loads(source_types_json) if source_types_json and source_types_json.startswith("[") else (source_types_json or "").split(",")
            source_types = [s.strip() for s in source_types if s and s.strip()]
        except Exception:
            source_types = []

        pair_c = _pair_commonness(conn, source_types)
        entity_c = _entity_commonness(conn, fact_chain)
        narrative_b = _narrative_boringness(conn, hid)
        chain_bonus = _chain_depth_bonus(num_domains or 0, chain_len or 0)

        # P(generic HUNTER finds this) — weighted average of commonness signals
        p_generic_finds = (
            0.35 * pair_c
            + 0.30 * entity_c
            + 0.20 * narrative_b
            - 0.25 * chain_bonus  # deep chains reduce generic discoverability
        )
        p_generic_finds = max(0.05, min(0.95, p_generic_finds))

        differential = 1.0 - p_generic_finds

        return {
            "hypothesis_id": hid,
            "pair_commonness": round(pair_c, 3),
            "entity_commonness": round(entity_c, 3),
            "narrative_boringness": round(narrative_b, 3),
            "chain_depth_bonus": round(chain_bonus, 3),
            "generic_finds_prob": round(p_generic_finds, 3),
            "differential_edge": round(differential, 3),
            "diamond_score": score,
        }
    finally:
        conn.close()


def compute_all(write: bool = False) -> list:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id FROM hypotheses WHERE survived_kill = 1
            ORDER BY diamond_score DESC
        """).fetchall()
    finally:
        conn.close()

    results = []
    for (hid,) in rows:
        r = compute_differential(hid)
        if "error" not in r:
            results.append(r)

    if write:
        conn = get_connection()
        try:
            now = datetime.now().isoformat()
            for r in results:
                conn.execute("""
                    INSERT OR REPLACE INTO differential_edge
                    (hypothesis_id, generic_finds_prob, differential_edge,
                     pair_commonness, entity_commonness,
                     narrative_boringness, chain_depth_bonus, computed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (r["hypothesis_id"], r["generic_finds_prob"],
                      r["differential_edge"], r["pair_commonness"],
                      r["entity_commonness"], r["narrative_boringness"],
                      r["chain_depth_bonus"], now))
            conn.commit()
        finally:
            conn.close()

    return results


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    _ensure_tables()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "audit"

    if cmd in ("run", "write"):
        results = compute_all(write=True)
        print(f"Computed differential edge for {len(results)} surviving hypotheses. Written to differential_edge.")

    elif cmd == "audit":
        results = compute_all(write=False)
        if not results:
            print("No surviving hypotheses to score.")
            sys.exit(0)

        # Sort by differential edge descending
        results.sort(key=lambda r: -r["differential_edge"])
        print(f"\n{'id':>4} {'score':>5} {'pgen':>6} {'DIFF':>6} "
              f"{'pair':>5} {'ent':>5} {'narr':>5} {'chain':>6}")
        print("-" * 60)
        for r in results[:20]:
            print(f"{r['hypothesis_id']:>4} {r['diamond_score']:>5} "
                  f"{r['generic_finds_prob']:>6.2f} {r['differential_edge']:>6.2f} "
                  f"{r['pair_commonness']:>5.2f} {r['entity_commonness']:>5.2f} "
                  f"{r['narrative_boringness']:>5.2f} {r['chain_depth_bonus']:>6.2f}")
        print(f"\nTop 10 by differential edge (what ONLY your HUNTER finds):")
        for r in results[:10]:
            diff = r["differential_edge"]
            marker = "⭐" if diff >= 0.7 else ("•" if diff >= 0.5 else " ")
            print(f"  {marker} #{r['hypothesis_id']:>3} diff={diff:.2f} score={r['diamond_score']}")

    else:
        print(__doc__)
