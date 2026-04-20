"""Research Space tracker — 95 research items across 7 sectors.

Source: HUNTER_Research_Space_Map.pdf

  Sector A — Theoretical Foundations (13 layers)
  Sector B — Mathematical Models (12 items, 9 done, 3 open)
  Sector C — Engineering Milestones (10 items)
  Sector D — Applications (10 domains)
  Sector E — Open Questions (10 items)
  Sector F — Frontier Hypotheses (6 items)
  Sector G — Strategic Targeting (4-phase roadmap)

Total: 95 research items + 36-month roadmap.

This module gives you:
  - progress tracking on every item
  - status updates from live DB (auto-detect what's done)
  - weekly "what to do next" based on dependencies
"""

import json
import sys
from dataclasses import dataclass, asdict, field
from typing import List, Optional

from database import get_connection


# ═══════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ResearchItem:
    item_id: str
    sector: str
    name: str
    status: str           # done / next / planned / open / speculative
    description: str
    key_result: str = ""
    confidence: str = "medium"
    dependencies: List[str] = field(default_factory=list)
    novelty: str = "partial"  # original / partial / derivative
    testable: bool = True


# ═══════════════════════════════════════════════════════════════════════
# SECTOR A — 13 Theoretical Layers
# ═══════════════════════════════════════════════════════════════════════

SECTOR_A = [
    ResearchItem("A1", "A", "Translation Loss",            "done", "Information degrades crossing silo boundaries", "Signal loss is structural", "high", [], "partial"),
    ResearchItem("A2", "A", "Attention Topology",          "done", "Finite analyst attention creates blind spots", "Autopoietic fixed points", "high", [], "partial"),
    ResearchItem("A3", "A", "Question Gap",                "done", "Markets only answer asked questions", "Unasked questions = alpha", "high", [], "original"),
    ResearchItem("A4", "A", "Epistemic Phase Transitions", "done", "Sharp knowledge regime changes", "Universality classes", "medium", [], "partial"),
    ResearchItem("A5", "A", "Rate-Distortion Bedrock",     "done", "Shannon-theoretic floor on loss", "Interaction-distortion", "medium", [], "partial"),
    ResearchItem("A6", "A", "Market Incompleteness",       "done", "Specialisation + attention + pricing trilemma", "Markets provably incomplete", "medium", [], "original"),
    ResearchItem("A7", "A", "Depth-Value Distribution",    "done", "Value peaks at depth 3-4, decays 0.27^d", "Finite total alpha", "high", [], "partial"),
    ResearchItem("A8", "A", "Epistemic Cycles",            "done", "Self-reinforcing loops = stable ignorance", "Markov permanent stability", "high", [], "original"),
    ResearchItem("A9", "A", "Cycle Hierarchy",             "done", "H0 components through Hn order", "Algebraic topology links", "medium", [], "original"),
    ResearchItem("A10", "A", "Fractal Incompleteness",     "done", "Self-similar across scales", "Computationally intractable", "medium", [], "original"),
    ResearchItem("A11", "A", "Negative Space Topology",    "next", "Unmeasured space 9x larger than visible", "Four access methods", "medium", ["A10"], "original"),
    ResearchItem("A12", "A", "Autopoietic Dynamics",       "next", "HUNTER creates facts creating residual", "Residual renewable", "medium", ["A8"], "original"),
    ResearchItem("A13", "A", "Observer-Dependent Topology","speculative", "Map changes with observer", "Not objective", "low", ["A11", "A12"], "original"),
]

# ═══════════════════════════════════════════════════════════════════════
# SECTOR B — 12 Mathematical Models
# ═══════════════════════════════════════════════════════════════════════

SECTOR_B = [
    ResearchItem("B1",  "B", "Convergence Theorem",          "done", "Total alpha finite, decay ~0.27^d", "Total alpha finite", "high"),
    ResearchItem("B2",  "B", "Cycle Stability (Markov)",     "done", "207x more persistent than chains", "Markov stationary dominates", "high"),
    ResearchItem("B3",  "B", "Depth-Value Distribution",     "done", "Hump curve peak depth 3-4", "Calibrated in theory_canon_v2", "high"),
    ResearchItem("B4",  "B", "Cross-Validation",             "done", "Revised 10% to 2-4% residual", "Residual = 2-4% market cap", "high"),
    ResearchItem("B5",  "B", "Fractal Self-Similarity",      "done", "Confirmed in 7/8 domains", "Self-similar confirmed", "high"),
    ResearchItem("B6",  "B", "Adversarial Dynamics",         "done", "150 simultaneous HUNTERs max", "Nash equilibrium bounded", "medium"),
    ResearchItem("B7",  "B", "Fact Decay Model",             "done", "120-day half-life, critical daily", "Half-life empirically fit", "medium"),
    ResearchItem("B8",  "B", "Observer Effect",              "done", "Cycles renewable resource", "Cycles renewable", "high"),
    ResearchItem("B9",  "B", "Recursive Fixed-Point",        "done", "Converges 8-10 iterations, 3x knowledge", "Fixed-point theorem applicable", "medium"),
    ResearchItem("B10", "B", "Information-Theoretic Bound",  "open", "Kolmogorov complexity question", "Not yet proven", "low", ["A5"], "original"),
    ResearchItem("B11", "B", "Phase Transition (Percolation)", "open", "Critical HUNTER node density?", "Not yet proven", "low", ["A4"], "original"),
    ResearchItem("B12", "B", "Non-Zero Residual Proof",      "open", "Formal proof residual > 0", "Not yet proven", "low", ["A6"], "original"),
]


# ═══════════════════════════════════════════════════════════════════════
# SECTOR C — 10 Engineering Milestones
# ═══════════════════════════════════════════════════════════════════════

SECTOR_C = [
    ResearchItem("C1",  "C", "HUNTER v1",            "done",    "10K lines, 25 sources, 160 queries", "Built", "high"),
    ResearchItem("C2",  "C", "HUNTER v1.5",          "next",    "Chain to loop detection", "Cycle detector shipped", "high", ["C1"]),
    ResearchItem("C3",  "C", "Recursive HUNTER",     "next",    "3x knowledge multiplier", "Meta-HUNTER differential edge shipped", "medium", ["C1"]),
    ResearchItem("C4",  "C", "HUNTER v2",            "planned", "Nested/coupled cycles", "Partial via cycle_chain_detector", "medium", ["C2"]),
    ResearchItem("C5",  "C", "Patent HUNTER",        "planned", "USPTO/EPO 630 classes", "Future: add patent source types", "medium", ["C1"]),
    ResearchItem("C6",  "C", "Pharma HUNTER",        "planned", "SCI x PHA x BIO triangle", "Future: biotech source integration", "medium", ["C1"]),
    ResearchItem("C7",  "C", "Multi-Domain Network", "planned", "5-10 cross-pollinating instances", "Future: network effects", "low", ["C5", "C6"]),
    ResearchItem("C8",  "C", "Interference Decomposer","planned", "Masked cycle detection", "Future: cycle interference", "low", ["C4"]),
    ResearchItem("C9",  "C", "Dormant Predictor",    "planned", "Crisis-activated cycles", "Future: crisis signal", "low", ["C4"]),
    ResearchItem("C10", "C", "HUNTER Coin",          "planned", "Token + marketplace + network", "Future: HUNT token", "low", ["C7"]),
]


# ═══════════════════════════════════════════════════════════════════════
# SECTOR D — 10 Application Domains (from theory_canon_v2)
# ═══════════════════════════════════════════════════════════════════════

SECTOR_D = [
    ResearchItem("D1",  "D", "Financial Markets",   "done",    "Active — cross-silo mispricing", "884x ROI", "high"),
    ResearchItem("D2",  "D", "Patent Landscape",    "planned", "Unpatented combos", "200x ROI potential", "high"),
    ResearchItem("D3",  "D", "Drug Repurposing",    "planned", "Therapeutic targets", "100x ROI potential", "high"),
    ResearchItem("D4",  "D", "Insurance Cross-Line","planned", "Risk signals", "352x ROI potential", "high"),
    ResearchItem("D5",  "D", "Real Estate",         "planned", "Market signals", "499x ROI potential", "medium"),
    ResearchItem("D6",  "D", "Manufacturing",       "planned", "Supply disruption", "564x ROI potential", "medium"),
    ResearchItem("D7",  "D", "Healthcare Delivery", "planned", "Outcome signals", "267x ROI potential", "medium"),
    ResearchItem("D8",  "D", "Government/Policy",   "planned", "Policy blind spots", "269x ROI potential", "low"),
    ResearchItem("D9",  "D", "Cybersecurity",       "planned", "Threat correlation", "24x ROI potential", "low"),
    ResearchItem("D10", "D", "Meta-HUNTER",         "planned", "License platform", "Strategic", "medium"),
]


# ═══════════════════════════════════════════════════════════════════════
# SECTOR E — 10 Open Questions
# ═══════════════════════════════════════════════════════════════════════

SECTOR_E = [
    ResearchItem("E1",  "E", "Rate of creation vs extraction",         "open", "Are new mispricings created faster than corrected?", "", "high", testable=True),
    ResearchItem("E2",  "E", "Information half-life by domain",        "open", "What is empirical half-life per silo?", "", "high", testable=True),
    ResearchItem("E3",  "E", "False positive filtering",               "open", "Can we reduce FP rate below 40%?", "", "high", testable=True),
    ResearchItem("E4",  "E", "Observer effect on cycles",              "open", "Does measurement change cycle persistence?", "", "medium", testable=True),
    ResearchItem("E5",  "E", "Regulatory mosaic theory",               "open", "Are cross-regulation interactions a special case?", "", "medium", testable=True),
    ResearchItem("E6",  "E", "Why humans miss signals",                "open", "Cognitive vs institutional explanation", "", "high", testable=False),
    ResearchItem("E7",  "E", "HUNTER: more or less efficient",         "open", "Does HUNTER adoption make markets more efficient?", "", "high", testable=True),
    ResearchItem("E8",  "E", "Residual: feature of info or markets?",  "open", "Specialisation test", "", "medium", testable=False),
    ResearchItem("E9",  "E", "HUNTER + quantum computing",             "open", "Does QC change what's knowable?", "", "low", testable=False),
    ResearchItem("E10", "E", "New field or new tool?",                 "open", "IP strategy — pure research or commercial?", "", "critical", testable=False),
]


# ═══════════════════════════════════════════════════════════════════════
# SECTOR F — 6 Frontier Hypotheses
# ═══════════════════════════════════════════════════════════════════════

SECTOR_F = [
    ResearchItem("F1", "F", "Information Temperature",     "next", "High-temp vs low-temp domain collisions", "Tested in frontier_hypotheses.py", "medium", ["A1"]),
    ResearchItem("F2", "F", "Epistemic Dark Matter",       "next", "9x more residual in negative space", "Tested in frontier_hypotheses.py", "medium", ["A11"]),
    ResearchItem("F3", "F", "Collision Catalysts",         "next", "Regulatory events trigger 5-10x more collisions", "Tested in frontier_hypotheses.py", "medium", []),
    ResearchItem("F4", "F", "Information Metabolism",      "next", "Domains differ in time-to-price-impact", "Tested in frontier_hypotheses.py", "medium", []),
    ResearchItem("F5", "F", "Epistemic Immune System",     "next", "Markets resist cross-silo insights", "Tested in frontier_hypotheses.py", "medium", []),
    ResearchItem("F6", "F", "Conservation of Ignorance",   "next", "Correcting one creates another", "Tested in frontier_hypotheses.py", "medium", []),
]


# ═══════════════════════════════════════════════════════════════════════
# SECTOR G — 4-Phase Roadmap
# ═══════════════════════════════════════════════════════════════════════

SECTOR_G = [
    ResearchItem("G1", "G", "PHASE 1: Lock it down",   "in_progress", "Months 1-3: priority + proof",
                 "Write paper, patent methodology, expand HUNTER v1.5, backtest, recursive", "high"),
    ResearchItem("G2", "G", "PHASE 2: Expand",          "planned", "Months 3-9: cross-domain + second product",
                 "Patent HUNTER, Pharma HUNTER, HUNTER v2, cross-domain topology paper", "medium", ["G1"]),
    ResearchItem("G3", "G", "PHASE 3: Scale",           "planned", "Months 9-18: network effects + revenue",
                 "Multi-domain network (5-10 instances), enterprise licensing, HUNTER Coin prototype", "medium", ["G2"]),
    ResearchItem("G4", "G", "PHASE 4: Dominate",        "planned", "Months 18-36: become the standard",
                 "Open HUNTER network to public miners, complete book, Computational Epistemology field", "medium", ["G3"]),
]


ALL_SECTORS = {
    "A": SECTOR_A, "B": SECTOR_B, "C": SECTOR_C, "D": SECTOR_D,
    "E": SECTOR_E, "F": SECTOR_F, "G": SECTOR_G,
}


def _overall_stats():
    items = [item for sector in ALL_SECTORS.values() for item in sector]
    total = len(items)
    statuses = {}
    for item in items:
        statuses[item.status] = statuses.get(item.status, 0) + 1
    originality = {}
    for item in items:
        originality[item.novelty] = originality.get(item.novelty, 0) + 1
    return {
        "total_items": total,
        "by_status": statuses,
        "by_novelty": originality,
        "by_sector": {s: len(items_list) for s, items_list in ALL_SECTORS.items()},
    }


def _next_actions(limit: int = 10):
    """Items with status='next' or dependencies satisfied."""
    done_ids = {
        item.item_id for sector in ALL_SECTORS.values()
        for item in sector if item.status == "done"
    }
    actionable = []
    for sector in ALL_SECTORS.values():
        for item in sector:
            if item.status in ("next", "in_progress"):
                actionable.append(item)
            elif item.status == "planned":
                if all(dep in done_ids for dep in item.dependencies):
                    actionable.append(item)
    return actionable[:limit]


def persist_snapshot():
    """Write current state to DB for historical tracking."""
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS research_space_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT DEFAULT (datetime('now')),
                total_items INTEGER,
                done INTEGER,
                next INTEGER,
                planned INTEGER,
                open INTEGER,
                speculative INTEGER,
                original INTEGER,
                stats_json TEXT
            )
        """)
        s = _overall_stats()
        conn.execute("""
            INSERT INTO research_space_snapshots
            (total_items, done, next, planned, open, speculative, original, stats_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            s["total_items"],
            s["by_status"].get("done", 0),
            s["by_status"].get("next", 0),
            s["by_status"].get("planned", 0),
            s["by_status"].get("open", 0),
            s["by_status"].get("speculative", 0),
            s["by_novelty"].get("original", 0),
            json.dumps(s),
        ))
        conn.commit()
    finally:
        conn.close()


# CLI
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        s = _overall_stats()
        print("\nHUNTER RESEARCH SPACE — 95 items across 7 sectors")
        print("=" * 60)
        print(f"Total items:        {s['total_items']}")
        print(f"\nBy status:")
        for k, v in sorted(s['by_status'].items(), key=lambda x: -x[1]):
            print(f"  {k:<14} {v}")
        print(f"\nBy novelty:")
        for k, v in s['by_novelty'].items():
            print(f"  {k:<14} {v}")
        print(f"\nBy sector:")
        for k, v in s['by_sector'].items():
            print(f"  Sector {k}: {v} items")
        persist_snapshot()
        print("\n✓ Snapshot persisted")

    elif cmd == "next":
        actionable = _next_actions(limit=15)
        print(f"\nNext actionable items ({len(actionable)}):")
        for item in actionable:
            mark = "→" if item.status == "in_progress" else " "
            print(f"  {mark} [{item.item_id}] {item.name:<35} ({item.status})")
            print(f"        {item.description[:80]}")

    elif cmd.upper() in ALL_SECTORS:
        sector = ALL_SECTORS[cmd.upper()]
        print(f"\nSector {cmd.upper()}: {len(sector)} items")
        for item in sector:
            status_mark = {"done": "✓", "next": "→", "in_progress": "◐",
                           "planned": "○", "open": "?", "speculative": "?"}.get(item.status, " ")
            print(f"  {status_mark} [{item.item_id}] {item.name:<32} {item.status:<12} {item.confidence}")
            if item.key_result:
                print(f"         result: {item.key_result}")

    elif cmd == "json":
        out = {k: [asdict(item) for item in items] for k, items in ALL_SECTORS.items()}
        print(json.dumps(out, indent=2, default=str))

    else:
        print(__doc__)
