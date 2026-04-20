"""Clear all hypothesis-ecosystem tables, preserving facts + stock tracker.

WHAT THIS DELETES (regenerates when HUNTER runs again):
 - hypotheses + hypotheses_archive
 - findings + deep_dives + knowledge_graph + cross_refs + idea_evolutions
 - collisions + chains + held_collisions
 - detected_cycles + cycle_positions + cycle_outcomes
 - theory_evidence (hypothesis-tagged records)
 - narrative_scores, kill_failure_topology, differential_edge
 - edge_recovery_events, firm_suggestions, backtest_results
 - decay_tracking, residual_classifications, phase_transition_signals
 - prediction_outcomes, prediction_audit
 - daily_summaries, theory_run_cycles, overseer_reports
 - domain_productivity, null_runs

WHAT THIS KEEPS (the expensive or manually-curated data):
 - raw_facts (12k ingested facts — the expensive asset)
 - fact_entities (30k entity index)
 - fact_model_fields (6.6k model-field extractions)
 - causal_edges (171 causal relationships — per-fact, not per-hypothesis)
 - anomalies (fact-level flags)
 - portfolio_positions + portfolio_snapshots (stock tracker)
 - market_beliefs + inverse_signals (inverse HUNTER state)
 - measured_domain_params (empirical calibration)
 - formula_validation + halflife_estimates + residual_estimates (theory calibration)
 - expirations (regulatory calendar)
 - targets + firm_suggestions metadata
 - cycle_logs (operational history)
 - research_space_snapshots

Run with:
    python clear_hypotheses.py           # dry-run (shows what would be cleared)
    python clear_hypotheses.py --execute # actually do it (prompts for confirmation)

Always creates hunter.db.backup-YYYYMMDD-HHMMSS before any writes.
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "hunter.db"

# ─── Tables to clear, in dependency order (children first) ─────────────────
TABLES_TO_CLEAR = [
    # Prediction-board resolutions (depends on hypotheses)
    "prediction_outcomes",
    "prediction_audit",

    # Per-hypothesis tables
    "backtest_results",
    "decay_tracking",
    "differential_edge",
    "edge_recovery_events",
    "firm_suggestions",
    "narrative_scores",
    "residual_classifications",
    "phase_transition_signals",

    # Aggregate hypothesis-derived tables
    "kill_failure_topology",
    "overseer_reports",
    "daily_summaries",
    "domain_productivity",
    "null_runs",

    # Cycles + cycle trading
    "cycle_outcomes",
    "cycle_positions",
    "detected_cycles",

    # Findings + knowledge graph (findings is a hypothesis-score copy)
    "idea_evolutions",
    "cross_refs",
    "knowledge_graph",
    "deep_dives",
    "findings",

    # Theory evidence (references hypothesis_id as source_id)
    "theory_evidence",

    # Theory run telemetry
    "theory_run_cycles",

    # Chains + held collisions + collisions (precursors to hypotheses)
    "chains",
    "held_collisions",
    "collisions",

    # Hypotheses themselves
    "hypotheses_archive",
    "hypotheses",
]

# ─── Tables to explicitly preserve (checked; never touched) ─────────────────
TABLES_TO_KEEP = [
    "raw_facts",
    "fact_entities",
    "fact_model_fields",
    "fact_embeddings",  # if exists — embeddings are in raw_facts BLOB column
    "causal_edges",
    "anomalies",
    "portfolio_positions",
    "portfolio_snapshots",
    "market_beliefs",
    "inverse_signals",
    "measured_domain_params",
    "formula_validation",
    "halflife_estimates",
    "residual_estimates",
    "residual_tam",
    "expirations",
    "negative_inferences",
    "targets",
    "cycle_logs",
    "research_space_snapshots",
    "frontier_test_results",
    "reinforcement_measurer_snapshots",
]


def get_row_counts(conn, tables):
    """Return {table: row_count} for existing tables."""
    result = {}
    for t in tables:
        try:
            cur = conn.execute(f"SELECT COUNT(*) FROM {t}")
            result[t] = cur.fetchone()[0]
        except sqlite3.OperationalError:
            result[t] = None  # table doesn't exist
    return result


def backup_db():
    """Create a timestamped backup. Returns backup path."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = DB_PATH.with_suffix(f".db.backup-{ts}")
    shutil.copy2(DB_PATH, backup)
    return backup


def clear_tables(conn, tables):
    """DELETE FROM each table. Order matters; children before parents."""
    cleared = {}
    for t in tables:
        try:
            cur = conn.execute(f"DELETE FROM {t}")
            cleared[t] = cur.rowcount
        except sqlite3.OperationalError as e:
            cleared[t] = f"SKIPPED ({e})"
    conn.commit()
    return cleared


def main():
    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} not found.")
        sys.exit(1)

    execute = "--execute" in sys.argv

    conn = sqlite3.connect(DB_PATH)

    print(f"\n{'='*70}")
    print(f"  HUNTER — Clear hypothesis ecosystem")
    print(f"{'='*70}\n")

    print(f"Database: {DB_PATH}  ({DB_PATH.stat().st_size / 1024 / 1024:.1f} MB)\n")

    # Show what WOULD be cleared
    print("TABLES TO CLEAR (regenerate on next HUNTER run):")
    print(f"  {'table':<35} {'rows':>8}")
    print(f"  {'-'*35} {'-'*8}")
    clear_counts = get_row_counts(conn, TABLES_TO_CLEAR)
    total_rows = 0
    for t in TABLES_TO_CLEAR:
        n = clear_counts.get(t)
        if n is None:
            print(f"  {t:<35} {'(no table)':>8}")
        else:
            print(f"  {t:<35} {n:>8,}")
            total_rows += n
    print(f"  {'-'*35} {'-'*8}")
    print(f"  {'TOTAL':<35} {total_rows:>8,}\n")

    # Show what WILL be kept
    print("TABLES TO PRESERVE (never touched):")
    print(f"  {'table':<35} {'rows':>8}")
    print(f"  {'-'*35} {'-'*8}")
    keep_counts = get_row_counts(conn, TABLES_TO_KEEP)
    total_kept = 0
    for t in TABLES_TO_KEEP:
        n = keep_counts.get(t)
        if n is None:
            continue  # table doesn't exist, skip silently
        print(f"  {t:<35} {n:>8,}")
        total_kept += n
    print(f"  {'-'*35} {'-'*8}")
    print(f"  {'TOTAL':<35} {total_kept:>8,}\n")

    conn.close()

    if not execute:
        print("This was a DRY RUN. No changes made.")
        print("\nTo actually clear, run:")
        print(f"  python {Path(__file__).name} --execute")
        print("\nYou will be asked to confirm before anything is deleted.\n")
        return

    # Live run — confirm first
    print("You are about to CLEAR ALL of the tables above.")
    print(f"A backup will be made at: {DB_PATH}.backup-<timestamp>")
    response = input("\nType 'yes' to proceed: ").strip().lower()
    if response != "yes":
        print("Aborted.")
        return

    # Backup
    print("\nCreating backup...")
    backup_path = backup_db()
    print(f"  Backup saved: {backup_path} ({backup_path.stat().st_size / 1024 / 1024:.1f} MB)")

    # Clear
    print("\nClearing tables...")
    conn = sqlite3.connect(DB_PATH)
    cleared = clear_tables(conn, TABLES_TO_CLEAR)
    for t, n in cleared.items():
        print(f"  {t:<35} {n}")

    # Reclaim space
    print("\nRunning VACUUM to reclaim disk space...")
    conn.execute("VACUUM")
    conn.close()

    final_size = DB_PATH.stat().st_size / 1024 / 1024
    print(f"\nDone. Database is now {final_size:.1f} MB.\n")

    print("NEXT STEPS:")
    print("  1. Run HUNTER to generate fresh hypotheses:")
    print("       python run.py live")
    print("  2. Or run a finite number of cycles:")
    print("       python run.py cycles 100")
    print("  3. Open the dashboard:")
    print("       python run.py dashboard")
    print("  4. Regenerate the public prediction board:")
    print("       python prediction_board.py build")
    print()
    print("If anything went wrong, restore from backup:")
    print(f"  cp {backup_path} {DB_PATH}")
    print()


if __name__ == "__main__":
    main()
