"""Populate causal_edges from existing chains.

The `causal_edges` table is empty (0 rows). The `chains` table has 52
rows with structured (cause → effect) relationships inside each link.
Extracting those edges unlocks:
 - CycleDetector agent running over a real graph (currently runs on chains only)
 - find_causal_paths() BFS in database.py
 - find_contradictory_paths() used in hypothesis formation
 - Layer 8 (epistemic cycles) evidence generation

Each chain has links like:
  {
    "link": 1,
    "disruption": "...",
    "broken_methodology": "...",
    "broken_assumption": "...",
    "practitioners": "...",
    "transmission_pathway": "...",
    "explanation": "...",
    "domain": "...",
    "output_change": "..."  (for links 2+)
  }

We derive causal edges as:
  cause_node = link[i].broken_methodology  or  link[i].broken_assumption
  effect_node = link[i+1].broken_methodology  or  link[i+1].broken_assumption
  confidence = 0.8 if transmission_pathway present else 0.5

Run:
    python chain_to_causal_edges.py           # dry report
    python chain_to_causal_edges.py write     # populate the table
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime

from database import get_connection


def _canonical(s: str, maxlen: int = 120) -> str:
    if not s or not isinstance(s, str):
        return ""
    t = s.strip()
    t = re.sub(r"\s+", " ", t)
    return t[:maxlen]


def _node_string(link: dict) -> str:
    """Build a compact node identity from a chain link."""
    parts = []
    for k in ("broken_methodology", "broken_assumption"):
        v = link.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(_canonical(v, 80))
    if not parts:
        fallback = link.get("disruption") or link.get("output_change") or ""
        if isinstance(fallback, str) and fallback.strip():
            parts.append(_canonical(fallback, 120))
    return " | ".join(parts)[:200]


def extract(dry_run: bool = True) -> dict:
    conn = get_connection()
    try:
        chains = conn.execute("""
            SELECT id, collision_id, chain_links, chain_length, domains_traversed
            FROM chains
        """).fetchall()

        edges = []
        domain_counts = defaultdict(int)

        for cid, coll_id, links_json, clen, domains in chains:
            try:
                links = json.loads(links_json) if links_json else []
            except Exception:
                continue
            if not isinstance(links, list) or len(links) < 2:
                continue

            for i in range(len(links) - 1):
                a = links[i] if isinstance(links[i], dict) else {}
                b = links[i + 1] if isinstance(links[i + 1], dict) else {}

                cause = _node_string(a)
                effect = _node_string(b)
                if not cause or not effect or cause == effect:
                    continue

                # Prefer transmission pathway strength marker
                transmission = (b.get("transmission_pathway") or "").strip()
                mechanism = (b.get("explanation") or a.get("explanation") or "")[:200]
                confidence = 0.85 if transmission else 0.55
                strength = "strong" if transmission else "moderate"
                domain = a.get("domain") or b.get("domain") or "unknown"

                edges.append({
                    "chain_id": cid,
                    "collision_id": coll_id,
                    "cause_node": cause,
                    "effect_node": effect,
                    "cause_node_lower": cause.lower(),
                    "effect_node_lower": effect.lower(),
                    "domain": domain,
                    "confidence": confidence,
                    "strength": strength,
                    "mechanism": mechanism,
                    "relationship_type": "causal",
                })
                domain_counts[domain] += 1

        summary = {
            "chains_processed": len(chains),
            "edges_extracted": len(edges),
            "edges_per_domain": dict(domain_counts),
        }

        if dry_run:
            return summary

        # Write
        now = datetime.now().isoformat()
        for e in edges:
            conn.execute("""
                INSERT INTO causal_edges
                (source_fact_id, cause_node, effect_node,
                 cause_node_lower, effect_node_lower,
                 relationship_type, confidence, source_type, domain,
                 strength, mechanism, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                None,  # source_fact_id not directly available at link-level
                e["cause_node"], e["effect_node"],
                e["cause_node_lower"], e["effect_node_lower"],
                e["relationship_type"], e["confidence"],
                None, e["domain"],
                e["strength"], e["mechanism"], now,
            ))
        conn.commit()
        summary["written"] = len(edges)
        return summary
    finally:
        conn.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dry"
    s = extract(dry_run=(cmd != "write"))
    print(f"\nCAUSAL EDGE EXTRACTION FROM CHAINS")
    print("=" * 60)
    print(f"Chains processed:  {s['chains_processed']}")
    print(f"Edges extracted:   {s['edges_extracted']}")
    print(f"\nEdges per domain:")
    for d, n in sorted(s["edges_per_domain"].items(), key=lambda x: -x[1])[:15]:
        print(f"  {d[:55]:<55} {n:>5}")
    if "written" in s:
        print(f"\n✓ Written to causal_edges: {s['written']}")
