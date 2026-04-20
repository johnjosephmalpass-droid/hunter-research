"""Moat Tracker — 5-layer moat with measurable action items.

Source: HUNTER_Research_Space_Map.pdf, THE MOAT section.

Five multiplicative moat layers. Each has a strength (0-10), a time-to-
replicate, specific action items that increase it, and measurable proxies
from the live DB.

  Layer 1: Theory         — publications + citations
  Layer 2: Engineering    — code lines + test coverage + modules shipped
  Layer 3: Data           — corpus size + entity index + fact model-fields
  Layer 4: Tacit Knowledge— diary entries + curation decisions + iterations
  Layer 5: Network Effects— users + integrations + external citations

Total moat = product of layers (not sum). Because multiplicative:
  all-3s = 3^5 = 243 (weak)
  all-5s = 5^5 = 3,125 (medium)
  all-8s = 8^5 = 32,768 (strong)
  all-9s = 9^5 = 59,049 (near-impregnable)

Run:
    python moat_tracker.py              # current state
    python moat_tracker.py targets      # next moves to strengthen each layer
    python moat_tracker.py snapshot     # persist a dated snapshot
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from database import get_connection


HERE = Path(__file__).parent


# ══════════════════════════════════════════════════════════════════════
# Layer definitions with measurement proxies
# ══════════════════════════════════════════════════════════════════════

def _measure_theory():
    """Theory moat: publications, preprints, coined terms."""
    preprint = 1 if (HERE / "HUNTER_PITCH.md").exists() else 0
    canon = 1 if (HERE / "THEORY_CANON.md").exists() else 0
    canon_v2 = 1 if (HERE / "theory_canon_v2.py").exists() else 0
    empirical = 1 if (HERE / "EMPIRICAL_FINDINGS.md").exists() else 0
    # SSRN posting bumps this hugely; currently zero
    ssrn_posted = 0
    citations = 0
    strength = min(10, preprint + canon + canon_v2 + empirical + ssrn_posted * 3 + citations * 0.2)
    return {
        "layer": "Theory",
        "strength": round(strength, 1),
        "measured_components": {
            "preprint_draft": preprint,
            "theory_canon": canon,
            "theory_canon_v2": canon_v2,
            "empirical_findings_doc": empirical,
            "ssrn_posted": ssrn_posted,
            "citations": citations,
        },
        "actions_to_strengthen": [
            "Post arXiv/SSRN preprint (bumps +3 immediately)",
            "Each citation adds +0.2 up to cap",
            "Invited talk or workshop = +1",
            "Journal publication (after review) = +3",
        ],
        "time_to_replicate_months": 3,
        "note": "WEAK once published — but priority of discovery is yours forever",
    }


def _measure_engineering():
    """Engineering moat: code volume, module count, test coverage."""
    py_files = list(HERE.glob("*.py"))
    n_modules = len(py_files)
    total_lines = 0
    for f in py_files:
        try:
            total_lines += len(f.read_text(errors="ignore").splitlines())
        except Exception:
            pass
    has_tests = (HERE / "test_core.py").exists()
    has_reproduce = (HERE / "reproduce.py").exists()
    has_preregister = (HERE / "preregistration.json").exists()
    has_dashboard = (HERE / "master_dashboard.py").exists()
    has_self_improve = (HERE / "self_improve.py").exists()

    strength = min(10, (
        (n_modules / 10) +              # modules
        (total_lines / 10000) +         # lines (normalised)
        has_tests * 1.2 +
        has_reproduce * 1.0 +
        has_preregister * 1.5 +
        has_dashboard * 0.5 +
        has_self_improve * 1.0
    ))
    return {
        "layer": "Engineering",
        "strength": round(strength, 1),
        "measured_components": {
            "python_modules": n_modules,
            "total_lines": total_lines,
            "unit_tests": has_tests,
            "reproduce_script": has_reproduce,
            "preregistration_locked": has_preregister,
            "dashboard_shipped": has_dashboard,
            "self_improve_live": has_self_improve,
        },
        "actions_to_strengthen": [
            "Add CI/CD pipeline (bumps +0.5)",
            "Add unit tests for every core module (bumps +1 at 90% coverage)",
            "Open-source scaffolding layer (bumps +1 for discoverability)",
            "Add proper logging/telemetry export (+0.5)",
        ],
        "time_to_replicate_months": 5,
        "note": "MEDIUM — engineering is replicable but takes months",
    }


def _measure_data():
    """Data moat: corpus size, uniqueness, entity resolution."""
    conn = get_connection()
    try:
        facts = conn.execute("SELECT COUNT(*) FROM raw_facts").fetchone()[0]
        entities = conn.execute("SELECT COUNT(*) FROM fact_entities").fetchone()[0]
        model_fields = conn.execute("SELECT COUNT(*) FROM fact_model_fields").fetchone()[0]
        chains = conn.execute("SELECT COUNT(*) FROM chains").fetchone()[0]
        causal_edges = conn.execute("SELECT COUNT(*) FROM causal_edges").fetchone()[0]
        cycles = conn.execute("SELECT COUNT(*) FROM detected_cycles").fetchone()[0]
    finally:
        conn.close()

    strength = min(10, (
        (facts / 20000) * 4 +           # 20k facts = 4 points
        (entities / 50000) * 2 +        # 50k entities = 2 points
        (model_fields / 10000) * 2 +    # 10k model fields = 2 points
        (chains / 100) * 1 +            # 100 chains = 1 point
        (causal_edges / 300) * 0.5 +
        (cycles / 20) * 0.5
    ))
    return {
        "layer": "Data",
        "strength": round(strength, 1),
        "measured_components": {
            "raw_facts": facts,
            "entity_index": entities,
            "model_field_extractions": model_fields,
            "chains": chains,
            "causal_edges": causal_edges,
            "detected_cycles": cycles,
        },
        "actions_to_strengthen": [
            f"Reach 50,000 facts ({50000 - facts} more — expected by late summer)",
            "Add JP/DE/ZH source types (bumps +1 for multilingual)",
            "Reach 100 chains (empirical depth distribution)",
            "Publish non-sensitive domain distance matrix as CC0 (bumps +0.5 — others cite)",
        ],
        "time_to_replicate_months": 10,
        "note": "STRONG — compounds daily with zero manual work",
    }


def _measure_tacit():
    """Tacit knowledge: iterations documented, curation decisions, diary depth."""
    diary_root = HERE / "diary"
    diary_entries = len(list(diary_root.glob("*.md"))) if diary_root.exists() else 0
    weekly_rollups = len(list((diary_root / "weekly").glob("*.md"))) if (diary_root / "weekly").exists() else 0
    monthly_rollups = len(list((diary_root / "monthly").glob("*.md"))) if (diary_root / "monthly").exists() else 0
    v3_golden = 1 if (HERE / "archive" / "v3_golden").exists() else 0  # documented failed experiment
    proposed_dir = HERE / "proposed_changes"
    n_proposals = len(list(proposed_dir.glob("*.json"))) if proposed_dir.exists() else 0

    strength = min(10, (
        (diary_entries / 40) * 3 +      # 40 diary entries = 3 points
        weekly_rollups * 0.3 +
        monthly_rollups * 0.5 +
        v3_golden * 2 +                 # documented honest failure is worth a lot
        (n_proposals / 10) * 0.5 +      # self-improvement proposals tracked
        2                               # 6-week iteration history baseline
    ))
    return {
        "layer": "Tacit Knowledge",
        "strength": round(strength, 1),
        "measured_components": {
            "diary_entries": diary_entries,
            "weekly_rollups": weekly_rollups,
            "monthly_rollups": monthly_rollups,
            "v3_golden_failure_documented": v3_golden,
            "self_improvement_proposals": n_proposals,
        },
        "actions_to_strengthen": [
            "Each weekly rollup (with YOUR prose) adds 0.2",
            "Each 2-page diary entry on a specific finding adds 0.1",
            "Publishing lessons-learned post = +0.5",
            "Keeping the v3_golden retrospective prominently visible = ongoing +2",
        ],
        "time_to_replicate_months": 18,
        "note": "VERY STRONG — cannot be copied. Every day makes it stronger.",
    }


def _measure_network():
    """Network effects: users of the system, integrations, external reference."""
    # Approximate proxies — real metrics require deployment
    public_dashboard = (HERE / "public_dashboard.py").exists()
    preregistered = (HERE / "preregistration.json").exists()
    advisor_emails_drafted = 1 if (HERE / "advisor_emails").exists() else 0
    # External users / integrations / citations — currently 0
    external_users = 0
    external_citations = 0
    partner_funds = 0

    strength = min(10, (
        public_dashboard * 0.5 +
        preregistered * 0.5 +
        advisor_emails_drafted * 0.3 +
        external_users * 0.5 +
        external_citations * 0.3 +
        partner_funds * 1.5
    ))
    return {
        "layer": "Network Effects",
        "strength": round(strength, 1),
        "measured_components": {
            "public_dashboard_built": public_dashboard,
            "preregistered": preregistered,
            "advisor_outreach_ready": advisor_emails_drafted,
            "external_users": external_users,
            "external_citations": external_citations,
            "partner_funds": partner_funds,
        },
        "actions_to_strengthen": [
            "Each external user of open-source component adds +0.1",
            "Each independent citation adds +0.3",
            "Each partner fund integration adds +1.5",
            "Open-sourcing domain distance matrix = potential +1 network boost",
        ],
        "time_to_replicate_months": 48,
        "note": "EXTREMELY STRONG if achieved — currently near-zero",
    }


# ══════════════════════════════════════════════════════════════════════
# Compose
# ══════════════════════════════════════════════════════════════════════

def all_layers():
    return [
        _measure_theory(),
        _measure_engineering(),
        _measure_data(),
        _measure_tacit(),
        _measure_network(),
    ]


def composite_score(layers=None):
    if layers is None:
        layers = all_layers()
    strengths = [max(1.0, l["strength"]) for l in layers]
    product = 1.0
    for s in strengths:
        product *= s
    return {
        "product_score": round(product, 1),
        "strict_moat_index": round(product / 100000, 4),
        "average_strength": round(sum(strengths) / len(strengths), 2),
        "time_to_replicate_months": sum(l["time_to_replicate_months"] for l in layers),
    }


def snapshot():
    layers = all_layers()
    comp = composite_score(layers)

    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS moat_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT DEFAULT (datetime('now')),
                theory REAL, engineering REAL, data REAL, tacit REAL, network REAL,
                composite REAL, layers_json TEXT
            )
        """)
        conn.execute("""
            INSERT INTO moat_snapshots
            (theory, engineering, data, tacit, network, composite, layers_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            layers[0]["strength"], layers[1]["strength"], layers[2]["strength"],
            layers[3]["strength"], layers[4]["strength"],
            comp["product_score"], json.dumps(layers),
        ))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    layers = all_layers()
    comp = composite_score(layers)

    if cmd == "status":
        print("\nHUNTER MOAT — 5 layers (multiplicative)")
        print("=" * 65)
        for l in layers:
            bar = "█" * int(l["strength"]) + "░" * (10 - int(l["strength"]))
            print(f"  {l['layer']:<18}  [{bar}] {l['strength']:>4.1f}/10  ({l['time_to_replicate_months']}mo to replicate)")
        print()
        print(f"  Composite (product):     {comp['product_score']:,.0f}")
        print(f"  Moat index (composite/100k): {comp['strict_moat_index']:.4f}")
        print(f"  Average strength:        {comp['average_strength']:.2f}/10")
        print(f"  Total time-to-replicate: {comp['time_to_replicate_months']} months combined")
        print()
        for l in layers:
            print(f"  [{l['layer']}] {l['note']}")

    elif cmd == "targets":
        print("\nMOAT STRENGTHENING TARGETS")
        print("=" * 65)
        for l in layers:
            print(f"\n{l['layer']} (current: {l['strength']}/10):")
            for action in l["actions_to_strengthen"]:
                print(f"  • {action}")

    elif cmd == "snapshot":
        snapshot()
        print(f"✓ Moat snapshot persisted")

    elif cmd == "json":
        print(json.dumps({"layers": layers, "composite": comp}, indent=2, default=str))

    else:
        print(__doc__)
