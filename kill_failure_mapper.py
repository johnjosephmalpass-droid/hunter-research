"""Kill-failure topology mapper — the empirical map of structural incompleteness.

The framework's Layer 10 claim is that some errors are structurally uncorrectable.
If a hypothesis survives N rounds of web-searched adversarial kill attempts,
that survival is itself evidence of structural incompleteness. This module
aggregates kill-round data across all surviving hypotheses and maps the
topology of domains where kills consistently fail.

For each surviving hypothesis, we look at kill_attempts and ask:
  - Which kill types were attempted (fact_check, competitor, barrier)?
  - Which found no evidence (genuinely failed to kill)?
  - Which found evidence but were overruled by steelman?

Then aggregate by source-type pair. Pairs where kill rounds systematically
fail are candidate structural-incompleteness zones — the places markets
cannot self-correct.

Run:
    python kill_failure_mapper.py
    python kill_failure_mapper.py write
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from itertools import combinations

from database import get_connection


def _parse_source_types(collision_row):
    """Extract source type list from a collisions row dict."""
    types = []
    st = collision_row.get("source_types")
    if st:
        try:
            types = json.loads(st) if st.startswith("[") else st.split(",")
        except Exception:
            types = st.split(",")
    if not types and collision_row.get("domains_involved"):
        try:
            types = json.loads(collision_row["domains_involved"])
        except Exception:
            pass
    return sorted({t.strip() for t in types if t and t.strip()})


def _classify_kill_attempt(attempt: dict) -> str:
    """Return 'found_kill' | 'no_evidence' | 'overruled'."""
    killed = attempt.get("killed", False)
    confidence = (attempt.get("confidence") or "").lower()
    reason = (attempt.get("reason") or "").lower()

    if killed and confidence in ("strong", "moderate"):
        return "found_kill"
    if not killed and ("no evidence" in reason or "not found" in reason
                       or "unable to confirm" in reason or not reason):
        return "no_evidence"
    if not killed:
        return "no_evidence"
    return "overruled"


def map_failures(write: bool = False) -> dict:
    conn = get_connection()
    try:
        hyps = conn.execute("""
            SELECT id, collision_id, kill_attempts, diamond_score, survived_kill
            FROM hypotheses
            WHERE kill_attempts IS NOT NULL
        """).fetchall()
        collisions = {
            r[0]: dict(zip(
                ["id", "source_types", "domains_involved", "num_domains"], r
            ))
            for r in conn.execute("""
                SELECT id, source_types, domains_involved, num_domains
                FROM collisions
            """).fetchall()
        }
    finally:
        conn.close()

    # Per-pair statistics
    pair_stats = defaultdict(lambda: {
        "total_hypotheses": 0,
        "total_kill_rounds_attempted": 0,
        "kills_found": 0,
        "no_evidence": 0,
        "overruled": 0,
        "survived_kills": 0,
        "hypothesis_ids": [],
    })
    # Per-round statistics
    round_stats = defaultdict(lambda: {"attempts": 0, "no_evidence": 0, "found_kill": 0})

    for hid, cid, ka_json, score, survived in hyps:
        try:
            attempts = json.loads(ka_json) if ka_json else []
        except Exception:
            attempts = []
        if not attempts:
            continue
        col = collisions.get(cid)
        if not col:
            continue
        types = _parse_source_types(col)
        if len(types) < 2:
            continue

        for a, b in combinations(types, 2):
            key = (a, b)
            pair_stats[key]["total_hypotheses"] += 1
            pair_stats[key]["hypothesis_ids"].append(hid)
            if survived:
                pair_stats[key]["survived_kills"] += 1

        for att in attempts:
            if not isinstance(att, dict):
                continue
            kill_type = att.get("kill_type") or att.get("type") or "unknown"
            outcome = _classify_kill_attempt(att)
            round_stats[kill_type]["attempts"] += 1
            if outcome == "no_evidence":
                round_stats[kill_type]["no_evidence"] += 1
            elif outcome == "found_kill":
                round_stats[kill_type]["found_kill"] += 1
            for a, b in combinations(types, 2):
                pair_stats[(a, b)]["total_kill_rounds_attempted"] += 1
                if outcome == "found_kill":
                    pair_stats[(a, b)]["kills_found"] += 1
                elif outcome == "no_evidence":
                    pair_stats[(a, b)]["no_evidence"] += 1
                else:
                    pair_stats[(a, b)]["overruled"] += 1

    # Compute failure rate per pair
    pairs_ranked = []
    for (a, b), s in pair_stats.items():
        if s["total_kill_rounds_attempted"] < 3:
            continue
        failure_rate = s["no_evidence"] / s["total_kill_rounds_attempted"]
        survival_rate = s["survived_kills"] / max(1, s["total_hypotheses"])
        pairs_ranked.append({
            "pair": f"{a} × {b}",
            "a": a, "b": b,
            "hypotheses": s["total_hypotheses"],
            "kill_rounds": s["total_kill_rounds_attempted"],
            "kills_found": s["kills_found"],
            "no_evidence": s["no_evidence"],
            "failure_rate": round(failure_rate, 4),
            "survival_rate": round(survival_rate, 4),
            "structural_incompleteness_score": round(
                failure_rate * survival_rate * (s["total_hypotheses"] ** 0.5), 4
            ),
        })
    pairs_ranked.sort(key=lambda p: -p["structural_incompleteness_score"])

    summary = {
        "n_hypotheses_with_kill_data": len(hyps),
        "n_pairs_analysed": len(pairs_ranked),
        "round_stats": dict(round_stats),
        "top_structural_pairs": pairs_ranked[:10],
    }

    if write:
        conn = get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kill_failure_topology (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain_a TEXT, domain_b TEXT,
                    hypotheses INTEGER, kill_rounds INTEGER,
                    kills_found INTEGER, no_evidence INTEGER,
                    failure_rate REAL, survival_rate REAL,
                    structural_incompleteness_score REAL,
                    measured_at TEXT
                )
            """)
            now = datetime.now().isoformat()
            for p in pairs_ranked:
                conn.execute("""
                    INSERT INTO kill_failure_topology
                    (domain_a, domain_b, hypotheses, kill_rounds, kills_found,
                     no_evidence, failure_rate, survival_rate,
                     structural_incompleteness_score, measured_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (p["a"], p["b"], p["hypotheses"], p["kill_rounds"],
                      p["kills_found"], p["no_evidence"], p["failure_rate"],
                      p["survival_rate"], p["structural_incompleteness_score"], now))
            conn.commit()
        finally:
            conn.close()
    return summary


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dry"
    s = map_failures(write=(cmd == "write"))
    print(f"\nKILL-FAILURE TOPOLOGY")
    print("=" * 80)
    print(f"Hypotheses with kill data: {s['n_hypotheses_with_kill_data']}")
    print(f"Domain pairs analysed:     {s['n_pairs_analysed']}")
    print()
    print(f"{'Kill type':<16} {'attempts':>10} {'no_evidence':>13} {'found_kill':>12}")
    for kt, rs in sorted(s["round_stats"].items()):
        print(f"{kt:<16} {rs['attempts']:>10} {rs['no_evidence']:>13} {rs['found_kill']:>12}")
    print()
    print("Top 10 pairs by structural-incompleteness score (survival × failure × sqrt(n)):")
    print(f"{'Pair':<50} {'hyp':>5} {'rnds':>5} {'fail%':>7} {'surv%':>7} {'SI':>7}")
    for p in s["top_structural_pairs"]:
        print(f"{p['pair']:<50} "
              f"{p['hypotheses']:>5} {p['kill_rounds']:>5} "
              f"{p['failure_rate']*100:>6.1f}% "
              f"{p['survival_rate']*100:>6.1f}% "
              f"{p['structural_incompleteness_score']:>7.3f}")
    if cmd == "write":
        print("\n✓ Written to kill_failure_topology table")
