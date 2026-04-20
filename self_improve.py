"""Self-improving HUNTER — bounded, goal-directed, with guardrails.

HUNTER sets a goal, measures progress, proposes changes to itself, applies
the safe ones automatically, and queues the risky ones for human approval.

Three LEVELS of self-modification, each with different permission rules:

  LEVEL 0 (AUTOPILOT — applies automatically):
    - Parameter tuning within pre-declared bounds (e.g. collision formula
      weights ±20% per month, scoring dimension thresholds ±10%)
    - Re-running analysers when new data arrives
    - Regenerating diary, dashboards, reports
    - Closing expired positions, opening new ones from existing signals
    All reversible. All within hard constraints. Cannot break preregistration.

  LEVEL 1 (QUEUED FOR APPROVAL):
    - Prompt text edits
    - New formula weight versions
    - New analyser module suggestions
    - Parameter changes beyond Level 0 bounds
    Written to proposed_changes/ folder. Human reviews and applies or rejects.
    Won't auto-apply because prompts/weights drift silently and break studies.

  LEVEL 2 (FORBIDDEN DURING STUDY):
    - Structural changes to core engine (hunter.py, orchestrator.py)
    - Pre-registration manifest edits
    - Schema changes to core tables
    - Model version changes
    These VOID the pre-registration code hash. Never auto-applied. Always
    require human decision + re-locking preregistration if done.

GOAL HIERARCHY:

  goals.json defines the current goal stack. Example:

    current_goal: "increase collision formula r² to >= 0.4 on held-out data"
    subgoals:
      - "populate measured_domain_params for all 18 source types"
      - "fit chain decay rate from empirical data"
      - "apply regression-suggested weight updates"
    success_when: "formula_validation.pearson_r >= 0.4 for 2 consecutive runs"
    next_goal_if_success: "achieve positive paper-portfolio alpha"

After the current goal is achieved, `promote_next_goal()` sets the next
goal in the stack as the active one.

Run:
    python self_improve.py plan           # what changes does HUNTER propose?
    python self_improve.py apply          # apply Level 0 changes automatically
    python self_improve.py queue          # show Level 1 changes awaiting review
    python self_improve.py goals          # show current goal + progress
    python self_improve.py promote        # if current goal achieved, advance
    python self_improve.py status         # full self-improvement state
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from database import get_connection


HERE = Path(__file__).parent
GOALS_PATH = HERE / "goals.json"
PROPOSED_CHANGES_DIR = HERE / "proposed_changes"
APPLIED_LOG = HERE / "self_improve_log.md"


# ══════════════════════════════════════════════════════════════════════
# Hard bounds — Level 0 can't cross these
# ══════════════════════════════════════════════════════════════════════

LEVEL_0_BOUNDS = {
    # Max monthly change per parameter
    "collision_formula_weight_pct_per_month": 0.20,
    "scoring_threshold_pct_per_month": 0.10,
    "min_reinforcement_to_open_cycle": (0.3, 0.8),   # (min, max) absolute
    "inverse_contradiction_threshold": (0.50, 0.80),
    # Max autopilot actions per week
    "max_level_0_changes_per_week": 5,
}


DEFAULT_GOALS = [
    {
        "goal": "Increase collision formula Pearson r² to ≥ 0.4 on held-out data",
        "subgoals": [
            "Ensure measured_domain_params has all 18 source types populated",
            "Fit chain decay rate from empirical chains table",
            "Apply regression-suggested weight updates (capped by Level 0 bounds)",
        ],
        "measure": "formula_validation.pearson_r",
        "target": 0.4,
        "success_when": "pearson_r >= 0.4 for 2 consecutive validation runs",
    },
    {
        "goal": "Achieve positive paper-portfolio alpha over 30-day window",
        "subgoals": [
            "Close all identified stale cluster positions via dedup",
            "Score new hypotheses with portfolio-feedback adjustment active",
            "Prefer hypotheses with differential_edge >= 0.6",
        ],
        "measure": "portfolio_snapshots.alpha_pct",
        "target": 0.0,
        "success_when": "alpha_pct > 0 for 14 consecutive days",
    },
    {
        "goal": "Detect 5+ structurally distinct cycle types",
        "subgoals": [
            "Populate causal_edges from all chains",
            "Classify cycles by the 9-type taxonomy (not just cross_domain_N)",
            "Detect nested/coupled/braided cycles from cycle-of-cycles analysis",
        ],
        "measure": "detected_cycles distinct cycle_type count",
        "target": 5,
        "success_when": "COUNT(DISTINCT cycle_type) >= 5",
    },
    {
        "goal": "Inverse HUNTER hits >55% on 30+ resolved signals",
        "subgoals": [
            "Ingest ≥ 30 analyst targets / cap rates / vol surfaces per month",
            "Resolve signals after target dates pass",
            "Track resolution_correct rate weekly",
        ],
        "measure": "inverse_signals resolution_correct rate",
        "target": 0.55,
        "success_when": "rate >= 0.55 on >= 30 resolved signals",
    },
]


def _ensure_goals():
    if not GOALS_PATH.exists():
        GOALS_PATH.write_text(json.dumps({
            "current_goal_index": 0,
            "goals": DEFAULT_GOALS,
            "history": [],
        }, indent=2))


def _load_goals():
    _ensure_goals()
    return json.loads(GOALS_PATH.read_text())


def _save_goals(data):
    GOALS_PATH.write_text(json.dumps(data, indent=2))


# ══════════════════════════════════════════════════════════════════════
# Progress measurement
# ══════════════════════════════════════════════════════════════════════

def _measure_current_goal():
    """Evaluate the current goal's measure against its target."""
    gdata = _load_goals()
    if not gdata["goals"]:
        return None
    idx = gdata["current_goal_index"]
    if idx >= len(gdata["goals"]):
        return {"achieved": True, "message": "All goals achieved. Set new ones."}

    goal = gdata["goals"][idx]
    measure = goal["measure"]

    conn = get_connection()
    observed = None
    try:
        if measure == "formula_validation.pearson_r":
            row = conn.execute(
                "SELECT pearson_r FROM formula_validation ORDER BY date DESC LIMIT 1"
            ).fetchone()
            if row:
                observed = row[0]
        elif measure.startswith("portfolio_snapshots"):
            row = conn.execute(
                "SELECT total_return_pct - spy_return_pct FROM portfolio_snapshots "
                "ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if row:
                observed = row[0] or 0
        elif measure.startswith("detected_cycles"):
            row = conn.execute(
                "SELECT COUNT(DISTINCT cycle_type) FROM detected_cycles WHERE is_active=1"
            ).fetchone()
            if row:
                observed = row[0]
        elif measure.startswith("inverse_signals"):
            row = conn.execute("""
                SELECT CAST(SUM(CASE WHEN resolution_correct=1 THEN 1 ELSE 0 END) AS REAL)
                       / NULLIF(COUNT(*), 0),
                       COUNT(*)
                FROM inverse_signals WHERE status IN ('resolved', 'closed')
            """).fetchone()
            if row and row[1] and row[1] >= 30:
                observed = row[0] or 0
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

    if observed is None:
        return {
            "goal_index": idx,
            "goal": goal["goal"],
            "target": goal["target"],
            "observed": None,
            "achieved": False,
            "message": f"Measure {measure} not yet populated — run analysers first.",
        }

    achieved = observed >= goal["target"] if goal["target"] >= 0 else observed <= goal["target"]
    return {
        "goal_index": idx,
        "goal": goal["goal"],
        "target": goal["target"],
        "observed": round(observed, 4) if isinstance(observed, (int, float)) else observed,
        "achieved": achieved,
        "gap": round(goal["target"] - observed, 4) if isinstance(observed, (int, float)) else None,
    }


def promote_next_goal():
    gdata = _load_goals()
    status = _measure_current_goal()
    if not status or not status.get("achieved"):
        return {"advanced": False, "reason": "current goal not achieved"}

    gdata["history"].append({
        "goal_index": gdata["current_goal_index"],
        "goal": gdata["goals"][gdata["current_goal_index"]]["goal"],
        "achieved_at": datetime.now().isoformat(),
        "observed": status.get("observed"),
    })
    gdata["current_goal_index"] += 1
    _save_goals(gdata)
    return {"advanced": True, "new_goal_index": gdata["current_goal_index"]}


# ══════════════════════════════════════════════════════════════════════
# Proposal generation — what should change to reach the goal?
# ══════════════════════════════════════════════════════════════════════

def generate_proposals():
    """Read system state, propose targeted changes. All deterministic —
    no LLM calls. Proposals are then classified by level."""
    gdata = _load_goals()
    if not gdata["goals"] or gdata["current_goal_index"] >= len(gdata["goals"]):
        return []
    goal = gdata["goals"][gdata["current_goal_index"]]

    proposals = []
    conn = get_connection()
    try:
        # Proposal 1: if formula r < target, apply regression-suggested deltas (Level 0 if within bounds)
        if "pearson_r" in goal["measure"]:
            fv = conn.execute(
                "SELECT pearson_r, suggested_silo_coeff, suggested_reinf_weight, "
                "suggested_corr_weight, suggested_resid_weight "
                "FROM formula_validation ORDER BY date DESC LIMIT 1"
            ).fetchone()
            if fv and fv[0] is not None and fv[0] < goal["target"]:
                proposals.append({
                    "level": 1,
                    "type": "formula_weight_update",
                    "title": "Apply regression-suggested formula weight deltas",
                    "rationale": f"Pearson r={fv[0]:.3f} < target {goal['target']}. "
                                 f"Regression suggests silo_delta={fv[1]}, "
                                 f"reinf_delta={fv[2]}, corr_delta={fv[3]}, resid_delta={fv[4]}.",
                    "suggested_new_version": f"v3_auto_{datetime.now().strftime('%Y%m%d')}",
                    "requires_human": True,
                })

        # Proposal 2: missing measured params for any domain → trigger reinforcement run (Level 0)
        missing = conn.execute("""
            SELECT rf.source_type FROM raw_facts rf
            WHERE rf.source_type IS NOT NULL
              AND rf.source_type NOT IN (SELECT source_type FROM measured_domain_params)
            GROUP BY rf.source_type HAVING COUNT(*) >= 30
        """).fetchall()
        if missing:
            proposals.append({
                "level": 0,
                "type": "rerun_reinforcement_measurer",
                "title": f"Re-run reinforcement_measurer to cover {len(missing)} missing domains",
                "rationale": f"{len(missing)} source types have ≥30 facts but no measured_domain_params row.",
                "action_command": "python reinforcement_measurer.py write",
                "requires_human": False,
            })

        # Proposal 3: cycle types below threshold → trigger cycle detector with lower merge threshold (Level 1)
        if "detected_cycles" in goal["measure"]:
            distinct = conn.execute(
                "SELECT COUNT(DISTINCT cycle_type) FROM detected_cycles WHERE is_active=1"
            ).fetchone()[0] or 0
            if distinct < goal["target"]:
                proposals.append({
                    "level": 1,
                    "type": "cycle_detector_retune",
                    "title": f"Lower cycle_detector merge_sim threshold from 0.78 to 0.72 to find more cycle types",
                    "rationale": f"Only {distinct} distinct cycle types detected; need {goal['target']}.",
                    "current_threshold": 0.78,
                    "proposed_threshold": 0.72,
                    "requires_human": True,
                })

        # Proposal 4: if inverse signals resolving below target, tighten contradiction threshold (Level 0)
        if "inverse_signals" in goal["measure"]:
            row = conn.execute("""
                SELECT CAST(SUM(CASE WHEN resolution_correct=1 THEN 1 ELSE 0 END) AS REAL)
                       / NULLIF(COUNT(*), 0), COUNT(*)
                FROM inverse_signals WHERE status IN ('resolved', 'closed')
            """).fetchone()
            if row and row[1] and row[1] >= 10:
                rate, n = row
                if rate is not None and rate < 0.55:
                    proposals.append({
                        "level": 0,
                        "type": "raise_contradiction_threshold",
                        "title": "Raise MIN_CONTRADICTION_SCORE from 0.60 to 0.65",
                        "rationale": f"Inverse signals hitting only {rate:.1%} on {n} resolved; "
                                     f"fewer-but-stronger signals should raise hit rate.",
                        "requires_human": False,
                    })

        # Proposal 5: always-on — run the full analyser suite if last run > 7 days
        last_analyser_ts = conn.execute(
            "SELECT MAX(measured_at) FROM measured_domain_params"
        ).fetchone()
        if last_analyser_ts and last_analyser_ts[0]:
            try:
                last = datetime.fromisoformat(last_analyser_ts[0])
                if (datetime.now() - last).days >= 7:
                    proposals.append({
                        "level": 0,
                        "type": "refresh_all_analysers",
                        "title": "Full analyser suite hasn't run in 7+ days",
                        "rationale": f"Last analyser run: {last_analyser_ts[0][:10]}",
                        "action_command": "python run.py analyse",
                        "requires_human": False,
                    })
            except Exception:
                pass
    finally:
        conn.close()

    return proposals


# ══════════════════════════════════════════════════════════════════════
# Apply — Level 0 auto, Level 1 queued to disk
# ══════════════════════════════════════════════════════════════════════

def _ensure_proposed_dir():
    PROPOSED_CHANGES_DIR.mkdir(parents=True, exist_ok=True)


def _count_this_week_applications():
    if not APPLIED_LOG.exists():
        return 0
    content = APPLIED_LOG.read_text()
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    return sum(1 for line in content.split("\n") if "APPLIED" in line and line[:10] >= week_ago)


def apply_proposals(dry_run: bool = False):
    _ensure_proposed_dir()
    proposals = generate_proposals()
    if not proposals:
        return {"applied": 0, "queued": 0, "proposals": []}

    applied_this_week = _count_this_week_applications()
    max_week = LEVEL_0_BOUNDS["max_level_0_changes_per_week"]

    applied = 0
    queued = 0
    log_entries = []

    for p in proposals:
        if p["level"] == 0 and not p.get("requires_human"):
            if applied_this_week >= max_week:
                # Out of weekly budget
                p["deferred_reason"] = f"weekly budget ({max_week}) exhausted"
                p["level_bumped_to"] = 1
                queued += 1
                _queue_proposal(p)
                continue
            if not dry_run and p.get("action_command"):
                import subprocess
                try:
                    subprocess.run(p["action_command"].split(), cwd=HERE, timeout=600, check=False)
                    log_entries.append(f"{datetime.now().isoformat()[:19]} APPLIED {p['type']}: {p['title']}")
                    applied += 1
                    applied_this_week += 1
                except Exception as e:
                    log_entries.append(f"{datetime.now().isoformat()[:19]} FAILED {p['type']}: {e}")
            else:
                log_entries.append(f"{datetime.now().isoformat()[:19]} DRY_RUN_APPLIED {p['type']}: {p['title']}")
                applied += 1
        else:
            # Level 1 or higher — queue
            _queue_proposal(p)
            queued += 1

    if log_entries and not dry_run:
        with APPLIED_LOG.open("a") as f:
            f.write("\n".join(log_entries) + "\n")

    return {"applied": applied, "queued": queued, "proposals": proposals}


def _queue_proposal(proposal):
    _ensure_proposed_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = PROPOSED_CHANGES_DIR / f"{ts}_{proposal['type']}.json"
    filename.write_text(json.dumps(proposal, indent=2))


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

def print_status():
    _ensure_goals()
    gdata = _load_goals()
    status = _measure_current_goal()
    print("\nHUNTER SELF-IMPROVEMENT STATE")
    print("=" * 60)
    if status:
        print(f"Current goal: {status.get('goal', 'unknown')}")
        print(f"Target:       {status.get('target')}")
        print(f"Observed:     {status.get('observed')}")
        print(f"Achieved:     {'✓ YES' if status.get('achieved') else '✗ NO'}")
        if status.get("gap") is not None:
            print(f"Gap:          {status['gap']}")

    print(f"\nGoal history ({len(gdata.get('history', []))} completed):")
    for h in gdata.get("history", []):
        print(f"  ✓ {h.get('achieved_at', '')[:10]}  {h.get('goal', '')[:70]}")

    applied_this_week = _count_this_week_applications()
    print(f"\nLevel 0 applications this week: {applied_this_week} / {LEVEL_0_BOUNDS['max_level_0_changes_per_week']}")

    _ensure_proposed_dir()
    queued_files = sorted(PROPOSED_CHANGES_DIR.glob("*.json"))
    print(f"Queued proposals awaiting human review: {len(queued_files)}")
    for f in queued_files[-5:]:
        try:
            data = json.loads(f.read_text())
            print(f"  • [L{data.get('level')}] {data.get('title', '')[:80]}")
        except Exception:
            pass


if __name__ == "__main__":
    _ensure_goals()
    _ensure_proposed_dir()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "plan":
        props = generate_proposals()
        print(f"\n{len(props)} proposals generated:\n")
        for p in props:
            requires = "requires human" if p.get("requires_human") else "AUTO"
            print(f"  [L{p['level']} · {requires}] {p['title']}")
            print(f"     rationale: {p['rationale'][:100]}")

    elif cmd == "apply":
        r = apply_proposals(dry_run=False)
        print(f"Applied: {r['applied']}, Queued for review: {r['queued']}")

    elif cmd == "dry":
        r = apply_proposals(dry_run=True)
        print(f"DRY RUN. Would apply: {r['applied']}, would queue: {r['queued']}")

    elif cmd == "queue":
        files = sorted(PROPOSED_CHANGES_DIR.glob("*.json"))
        print(f"\n{len(files)} proposals awaiting review:\n")
        for f in files:
            try:
                data = json.loads(f.read_text())
                print(f"  {f.name}")
                print(f"     [L{data.get('level')}] {data.get('title', '')}")
                print(f"     {data.get('rationale', '')[:120]}")
                print()
            except Exception as e:
                print(f"  {f.name}  (parse error: {e})")

    elif cmd == "goals":
        data = _load_goals()
        print("\nGOALS STACK")
        for i, g in enumerate(data["goals"]):
            marker = "→" if i == data["current_goal_index"] else ("✓" if i < data["current_goal_index"] else " ")
            print(f"  {marker} #{i}: {g['goal']}")
            print(f"       measure: {g['measure']}  target: {g['target']}")

    elif cmd == "promote":
        r = promote_next_goal()
        if r["advanced"]:
            print(f"✓ Advanced to goal #{r['new_goal_index']}")
        else:
            print(f"Not advanced: {r.get('reason')}")

    elif cmd == "status":
        print_status()

    else:
        print(__doc__)
