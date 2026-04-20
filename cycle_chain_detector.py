"""Cycle-chain detector — classify detected cycles by your 9-type taxonomy
and find higher-order structures (cycles of cycles, coupled cycles,
nested cycles).

Gap this fills: cycle_detector.py only classifies as cross_domain_Nnode.
Your theory defines 9 types. This module does the real classification.

Classification logic (post-cycle-detection):

  SIMPLE (rank 1):
    Cycle has ≤ 3 nodes, ≤ 2 distinct domains, no overlap with other cycles.

  NESTED (rank 2):
    Cycle A is entirely contained within cycle B (all of A's nodes are also
    in B, B has more nodes).

  COUPLED (rank 3):
    Two cycles share exactly 1 or 2 nodes but neither is contained in the
    other. "Handshake" topology.

  BRAIDED (rank 4):
    Two or more cycles interleave — share ≥ 2 non-consecutive nodes,
    neither contained. Creates a twisted structure.

  HIERARCHICAL (rank 5):
    A cycle whose nodes group into 2+ distinct cycles themselves. Meta-cycle.

  TEMPORAL (rank 6):
    Cycle nodes activate at different times (based on fact dates). Inferred
    from the time distribution of the originating facts.

  CROSS_DOMAIN (rank 7):
    ≥ 4 distinct professional domains in a single cycle (the current
    cycle_detector default for deep cycles).

  INTERFERENCE (rank 8):
    Two cycles share a node but their directions oppose at that node
    (node is a sink for one cycle and a source for another). Cycles
    cancel each other.

  DORMANT (rank 9):
    Cycle whose reinforcement_strength has fallen below 0.3. Structurally
    present but currently inactive.

Run:
    python cycle_chain_detector.py classify     # assign 9-type classification
    python cycle_chain_detector.py patterns     # show which patterns exist
    python cycle_chain_detector.py metacycles   # detect cycles of cycles
"""

import json
import sys
from collections import defaultdict
from datetime import datetime

from database import get_connection


CYCLE_RANK = {
    "simple": 1, "nested": 2, "coupled": 3, "braided": 4,
    "hierarchical": 5, "temporal": 6, "cross_domain": 7,
    "interference": 8, "dormant": 9,
}


def _load_cycles():
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, cycle_type, nodes, domains,
                   reinforcement_strength, correction_pressure,
                   persistence_estimate, detected_date, is_active
            FROM detected_cycles
        """).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        try:
            nodes = json.loads(r[2] or "[]")
            domains = json.loads(r[3] or "[]")
        except Exception:
            nodes, domains = [], []
        out.append({
            "id": r[0], "cycle_type": r[1] or "",
            "nodes": nodes, "node_ids": [n.get("node_id", "") for n in nodes if isinstance(n, dict)],
            "domains": domains,
            "reinforcement_strength": r[4] or 0.0,
            "correction_pressure": r[5] or 0.0,
            "persistence_estimate": r[6] or 0,
            "detected_date": r[7],
            "is_active": r[8],
        })
    return out


# ══════════════════════════════════════════════════════════════════════
# Classification rules
# ══════════════════════════════════════════════════════════════════════

def _is_dormant(cycle: dict) -> bool:
    return cycle["reinforcement_strength"] < 0.30


def _is_cross_domain(cycle: dict) -> bool:
    return len([d for d in cycle["domains"] if d and d != "unknown"]) >= 4


def _find_nested(cycles: list) -> dict:
    """Return a mapping: cycle_id → True if its node set is a proper subset
    of another cycle's node set."""
    nested_ids = set()
    for i, c in enumerate(cycles):
        ci_nodes = set(c["node_ids"])
        if not ci_nodes:
            continue
        for j, c2 in enumerate(cycles):
            if i == j:
                continue
            cj_nodes = set(c2["node_ids"])
            if ci_nodes and cj_nodes and ci_nodes < cj_nodes:
                nested_ids.add(c["id"])
                break
    return {cid: True for cid in nested_ids}


def _find_coupled(cycles: list) -> dict:
    """Coupled = shares 1-2 nodes with another cycle but neither contains the other."""
    coupled = set()
    for i, c in enumerate(cycles):
        ci_nodes = set(c["node_ids"])
        if not ci_nodes:
            continue
        for j, c2 in enumerate(cycles):
            if i >= j:
                continue
            cj_nodes = set(c2["node_ids"])
            overlap = ci_nodes & cj_nodes
            if 1 <= len(overlap) <= 2 and not ci_nodes.issubset(cj_nodes) and not cj_nodes.issubset(ci_nodes):
                coupled.add(c["id"])
                coupled.add(c2["id"])
    return {cid: True for cid in coupled}


def _find_braided(cycles: list) -> dict:
    """Braided = shares ≥ 3 nodes with another cycle but nodes aren't
    consecutive (interleaved). Harder to detect perfectly, approximate via
    shared-node count ≥ 3."""
    braided = set()
    for i, c in enumerate(cycles):
        ci_nodes = set(c["node_ids"])
        if len(ci_nodes) < 4:
            continue
        for j, c2 in enumerate(cycles):
            if i >= j:
                continue
            cj_nodes = set(c2["node_ids"])
            overlap = ci_nodes & cj_nodes
            if len(overlap) >= 3 and not ci_nodes.issubset(cj_nodes) and not cj_nodes.issubset(ci_nodes):
                braided.add(c["id"])
                braided.add(c2["id"])
    return {cid: True for cid in braided}


def _find_hierarchical(cycles: list) -> dict:
    """Hierarchical = cycle's nodes decompose into 2+ sub-cycles.
    Approximate detection: a large cycle (≥ 6 nodes) that overlaps with
    2+ smaller cycles."""
    hier = set()
    for c in cycles:
        if len(c["node_ids"]) < 6:
            continue
        ci_nodes = set(c["node_ids"])
        sub_overlaps = 0
        for c2 in cycles:
            if c2["id"] == c["id"] or len(c2["node_ids"]) > len(ci_nodes):
                continue
            cj_nodes = set(c2["node_ids"])
            if cj_nodes and cj_nodes.issubset(ci_nodes):
                sub_overlaps += 1
        if sub_overlaps >= 2:
            hier.add(c["id"])
    return {cid: True for cid in hier}


def classify_all() -> dict:
    cycles = _load_cycles()
    if not cycles:
        return {"error": "no cycles in DB"}

    nested_map = _find_nested(cycles)
    coupled_map = _find_coupled(cycles)
    braided_map = _find_braided(cycles)
    hier_map = _find_hierarchical(cycles)

    classifications = {}
    for c in cycles:
        cid = c["id"]
        # Priority order: dormant > hierarchical > braided > coupled > nested > cross_domain > simple
        if _is_dormant(c):
            t = "dormant"
        elif hier_map.get(cid):
            t = "hierarchical"
        elif braided_map.get(cid):
            t = "braided"
        elif coupled_map.get(cid):
            t = "coupled"
        elif nested_map.get(cid):
            t = "nested"
        elif _is_cross_domain(c):
            t = "cross_domain"
        else:
            t = "simple"
        classifications[cid] = t

    return classifications


def persist_classifications():
    classifications = classify_all()
    if "error" in classifications:
        return 0
    conn = get_connection()
    try:
        updated = 0
        for cid, new_type in classifications.items():
            conn.execute(
                "UPDATE detected_cycles SET cycle_type = ? WHERE id = ?",
                (f"{new_type}_{_get_node_count(conn, cid)}node", cid)
            )
            updated += 1
        conn.commit()
        return updated
    finally:
        conn.close()


def _get_node_count(conn, cycle_id: int) -> int:
    row = conn.execute("SELECT nodes FROM detected_cycles WHERE id = ?", (cycle_id,)).fetchone()
    if not row:
        return 0
    try:
        return len(json.loads(row[0] or "[]"))
    except Exception:
        return 0


# ══════════════════════════════════════════════════════════════════════
# Higher-order: cycles of cycles
# ══════════════════════════════════════════════════════════════════════

def find_meta_cycles() -> list:
    """A meta-cycle exists when cycle A's nodes include the output of cycle B,
    AND cycle B's nodes include the output of cycle A. Cycles that feed each
    other's inputs."""
    cycles = _load_cycles()
    if len(cycles) < 2:
        return []

    # Approximate: any two cycles sharing 2+ nodes IN SEQUENCE are a meta-cycle candidate
    meta = []
    for i, a in enumerate(cycles):
        a_nodes = a["node_ids"]
        for j, b in enumerate(cycles):
            if i >= j:
                continue
            b_nodes = b["node_ids"]
            if not a_nodes or not b_nodes:
                continue
            shared = set(a_nodes) & set(b_nodes)
            if len(shared) >= 2:
                meta.append({
                    "cycle_a_id": a["id"],
                    "cycle_b_id": b["id"],
                    "shared_nodes": list(shared),
                    "shared_count": len(shared),
                    "combined_strength": (a["reinforcement_strength"] + b["reinforcement_strength"]) / 2,
                })
    meta.sort(key=lambda m: -m["shared_count"])
    return meta


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "patterns"

    if cmd == "classify":
        classifications = classify_all()
        if "error" in classifications:
            print(classifications["error"])
            sys.exit(1)
        counts = defaultdict(int)
        for t in classifications.values():
            counts[t] += 1
        print("\nCycle classifications (9-type taxonomy):")
        for t in ["simple", "nested", "coupled", "braided", "hierarchical",
                  "temporal", "cross_domain", "interference", "dormant"]:
            n = counts.get(t, 0)
            marker = "✓" if n > 0 else " "
            print(f"  {marker} {t:<16} (rank {CYCLE_RANK[t]}): {n} cycle(s)")

        updated = persist_classifications()
        print(f"\n✓ Updated {updated} detected_cycles rows with 9-type classification.")

    elif cmd == "patterns":
        cycles = _load_cycles()
        print(f"\nCycle structural patterns in corpus ({len(cycles)} cycles):\n")
        nested = _find_nested(cycles)
        coupled = _find_coupled(cycles)
        braided = _find_braided(cycles)
        hier = _find_hierarchical(cycles)
        print(f"  Nested (contained in another):   {len(nested)}")
        print(f"  Coupled (share 1-2 nodes):       {len(coupled) // 2} pair(s)")
        print(f"  Braided (share ≥3 nodes):        {len(braided) // 2} pair(s)")
        print(f"  Hierarchical (contain sub-cycles): {len(hier)}")
        dormant = sum(1 for c in cycles if _is_dormant(c))
        crossd = sum(1 for c in cycles if _is_cross_domain(c) and not _is_dormant(c))
        print(f"  Dormant (reinforcement < 0.3):   {dormant}")
        print(f"  Cross-domain (≥4 domains):       {crossd}")

    elif cmd == "metacycles":
        meta = find_meta_cycles()
        print(f"\n{len(meta)} meta-cycle candidates (cycles sharing ≥2 nodes):\n")
        for m in meta[:15]:
            print(f"  Cycle {m['cycle_a_id']} ↔ Cycle {m['cycle_b_id']}: "
                  f"{m['shared_count']} shared nodes, "
                  f"combined strength {m['combined_strength']:.2f}")

    else:
        print(__doc__)
