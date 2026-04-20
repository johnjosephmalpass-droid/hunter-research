#!/usr/bin/env python3
"""HUNTER Master Orchestrator — Coordinates trading pipeline + theory proof layer.

Replaces the simple main() loop in hunter.py with intelligent scheduling,
adaptive targeting, self-reinforcing parameter adjustments, and robust
error handling.

Run with: python orchestrator.py
"""

import json
import os
import random
import signal
import sqlite3
import sys
import time
import threading
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# ── Import HUNTER subsystems ───────────────────────────────────────────
from config import INGEST_RATIO, TOKEN_CAP_NORMAL, TIMEOUT_NORMAL
from database import (
    init_db, get_knowledge_base_stats, get_collision_to_hypothesis_rate,
    get_connection,
)
from hunter import (
    IngestCycle, CollisionCycle, run_daily_synthesis,
    print_banner, print_info, print_error, print_phase, C,
    count_tokens,
)

# Theory layer agents (imported lazily in case of missing deps)
try:
    from theory_layer import (
        TheoryTelemetry, DecayTracker, CycleDetector,
        CollisionFormulaValidator, ChainDepthProfiler,
        BacktestReconciler, ResidualEstimator,
    )
    THEORY_AVAILABLE = True
except ImportError:
    THEORY_AVAILABLE = False

try:
    from theory import DOMAIN_THEORY_PARAMS, compute_collision_formula
except ImportError:
    DOMAIN_THEORY_PARAMS = {}

    def compute_collision_formula(a, b):
        return {"total": 0}


# ═══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

# Scheduling intervals
DECAY_INTERVAL_HOURS = 24          # Run DecayTracker daily
WEEKLY_INTERVAL_DAYS = 7           # Weekly agents on Sunday
MONTHLY_DAY = 1                    # ResidualEstimator on 1st of month
SYNTHESIS_INTERVAL_CYCLES = 100    # Daily synthesis every N ingest cycles
SYNTHESIS_INTERVAL_HOURS = 24      # Or every 24 hours

# Budget controls
API_BUDGET_PAUSE_THRESHOLD = 5.0   # Pause theory agents below $5
WEEKLY_TIMEOUT_SECONDS = 1800      # Kill weekly run if >30 min
DB_RETRY_WAIT = 5                  # Seconds between DB lock retries
DB_RETRY_MAX = 3                   # Max DB lock retries
RATE_LIMIT_BACKOFF = 60            # Seconds to wait on 429

# Cycle pause
CYCLE_PAUSE_MIN = 3                # Min seconds between cycles
CYCLE_PAUSE_MAX = 5                # Max seconds between cycles

# Adaptive targeting defaults
CHAIN_EXTEND_MAX_DEFAULT = 4       # Default chain extension depth
CHAIN_EXTEND_MAX_BOOSTED = 6       # Boosted when depth data is thin


# ═══════════════════════════════════════════════════════════════════════
# ORCHESTRATOR STATE
# ═══════════════════════════════════════════════════════════════════════

class OrchestratorState:
    """Tracks all scheduling state and metrics."""

    def __init__(self):
        self.cycle_num = 0
        self.ingest_count = 0
        self.collision_count = 0
        self.start_time = time.time()

        # Scheduling timestamps
        self.last_decay_run = None
        self.last_weekly_run = None
        self.last_monthly_run = None
        self.last_synthesis_time = time.time()
        self.last_adaptive_check = None

        # Cost tracking
        self.session_cost_estimate = 0.0
        self.theory_cost_estimate = 0.0

        # Adaptive targeting state
        self.chain_extend_max = CHAIN_EXTEND_MAX_DEFAULT
        self.evidence_gaps = {}       # layer → evidence count
        self.domain_adjustments = {}  # domain → resid delta

        # Error tracking
        self.errors = []
        self.consecutive_errors = 0

    def estimate_cost(self, tokens, model="haiku"):
        """Rough cost estimate per call."""
        if model == "haiku":
            return tokens * 0.00000025  # $0.25/M tokens
        elif model == "sonnet":
            return tokens * 0.000003    # $3/M tokens
        return tokens * 0.000001


# ═══════════════════════════════════════════════════════════════════════
# SCHEDULING LOG
# ═══════════════════════════════════════════════════════════════════════

def log_action(action, reason, duration=0, cost=0, next_scheduled=""):
    """Log scheduling decisions to orchestrator_log table and stdout."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "reason": reason,
        "duration_seconds": round(duration, 2),
        "cost_estimate": f"${cost:.4f}" if cost else "$0",
        "next_scheduled": next_scheduled,
    }
    print(f"  {C.DIM}[ORCH] {action}: {reason} ({duration:.1f}s, {entry['cost_estimate']}){C.RESET}")

    # Persist to database
    try:
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orchestrator_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, action TEXT, reason TEXT,
                duration_seconds REAL, cost_estimate TEXT,
                next_scheduled TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO orchestrator_log (timestamp, action, reason, duration_seconds,
                                          cost_estimate, next_scheduled)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (entry["timestamp"], action, reason, duration,
              entry["cost_estimate"], next_scheduled))
        conn.commit()
        conn.close()
    except Exception:
        pass  # Logging failure is non-fatal

    return entry


# ═══════════════════════════════════════════════════════════════════════
# ERROR HANDLING
# ═══════════════════════════════════════════════════════════════════════

def safe_run(func, name, state, timeout=None):
    """Run a function with error handling, optional timeout, and cost tracking.
    Returns (success, duration, cost_estimate)."""
    start = time.time()
    cost = 0.0

    try:
        if timeout:
            # Run with timeout using threading
            result = [None]
            error = [None]

            def _target():
                try:
                    result[0] = func()
                except Exception as e:
                    error[0] = e

            thread = threading.Thread(target=_target, daemon=True)
            thread.start()
            thread.join(timeout)

            if thread.is_alive():
                duration = time.time() - start
                log_action(f"{name}_timeout", f"Killed after {timeout}s",
                          duration=duration)
                state.errors.append({"agent": name, "error": "timeout",
                                     "time": datetime.now().isoformat()})
                return False, duration, 0
            if error[0]:
                raise error[0]
        else:
            func()

        duration = time.time() - start
        state.consecutive_errors = 0
        return True, duration, cost

    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            # Database locked — retry
            for retry in range(DB_RETRY_MAX):
                print(f"  {C.YELLOW}DB locked, retry {retry+1}/{DB_RETRY_MAX}...{C.RESET}")
                time.sleep(DB_RETRY_WAIT)
                try:
                    func()
                    duration = time.time() - start
                    return True, duration, cost
                except sqlite3.OperationalError:
                    continue
            duration = time.time() - start
            log_action(f"{name}_db_locked", f"Failed after {DB_RETRY_MAX} retries",
                      duration=duration)
            return False, duration, 0
        else:
            raise

    except Exception as e:
        duration = time.time() - start
        error_msg = str(e)

        # Rate limit handling
        if "429" in error_msg or "rate" in error_msg.lower():
            print(f"  {C.YELLOW}Rate limited on {name}, backing off {RATE_LIMIT_BACKOFF}s...{C.RESET}")
            time.sleep(RATE_LIMIT_BACKOFF)
            try:
                func()
                duration = time.time() - start
                return True, duration, cost
            except Exception as e2:
                log_action(f"{name}_rate_limited", f"Failed after retry: {e2}",
                          duration=duration)
                return False, duration, 0

        # General error — log and continue
        state.errors.append({"agent": name, "error": error_msg[:200],
                             "time": datetime.now().isoformat()})
        state.consecutive_errors += 1
        log_action(f"{name}_error", f"{error_msg[:200]}",
                  duration=duration)
        print(f"  {C.RED}[ORCH] {name} failed: {error_msg[:100]}{C.RESET}")
        traceback.print_exc()
        return False, duration, 0


# ═══════════════════════════════════════════════════════════════════════
# THEORY AGENT RUNNERS
# ═══════════════════════════════════════════════════════════════════════

def run_decay_tracker(state):
    """Daily: measure hypothesis persistence, refresh prices, write diary."""
    now = datetime.now()
    if state.last_decay_run:
        hours = (now - state.last_decay_run).total_seconds() / 3600
        if hours < DECAY_INTERVAL_HOURS:
            return

    # (1) Theory-layer DecayTracker — if available
    if THEORY_AVAILABLE:
        print_phase("THEORY", "Running DecayTracker (daily)...")
        ok, dur, cost = safe_run(lambda: DecayTracker().run(), "DecayTracker", state)
        if ok:
            log_action("decay_tracker", "Daily persistence measurement",
                      duration=dur, cost=cost,
                      next_scheduled=f"Next in {DECAY_INTERVAL_HOURS}h")

    # (2) Daily lightweight jobs — no API, cheap, keep dashboard fresh
    import subprocess
    from pathlib import Path
    here = Path(__file__).parent
    daily_jobs = [
        ("research_diary",       "research_diary.py"),
        ("cycle_review_prices",  "cycle_portfolio.py review"),
        ("attribution_report",   "performance_attribution.py"),
    ]
    print_phase("DAILY", f"Running {len(daily_jobs)} daily jobs...")
    for name, script_args in daily_jobs:
        if not (here / script_args.split()[0]).exists():
            continue
        try:
            r = subprocess.run(
                ["python"] + script_args.split(),
                cwd=here, capture_output=True, text=True, timeout=300,
            )
            if r.returncode == 0:
                print(f"  {C.GREEN}✓ {name}{C.RESET}")
            else:
                print(f"  {C.YELLOW}⚠ {name} exited {r.returncode}{C.RESET}")
        except Exception as e:
            print(f"  {C.YELLOW}⚠ {name}: {e}{C.RESET}")

    state.last_decay_run = now


def run_weekly_agents(state):
    """Weekly (Sunday): CycleDetector, FormulaValidator, ChainProfiler, BacktestReconciler."""
    if not THEORY_AVAILABLE:
        return
    now = datetime.now()

    # Check if it's time (every 7 days, prefer Sunday)
    if state.last_weekly_run:
        days = (now - state.last_weekly_run).total_seconds() / 86400
        if days < WEEKLY_INTERVAL_DAYS:
            return

    print_phase("THEORY", "Running weekly theory agents...")
    start = time.time()

    agents = [
        ("CycleDetector", lambda: CycleDetector().run()),
        ("FormulaValidator", lambda: CollisionFormulaValidator().run()),
        ("ChainProfiler", lambda: ChainDepthProfiler().run()),
        ("BacktestReconciler", lambda: BacktestReconciler().run()),
    ]

    total_cost = 0
    for name, func in agents:
        ok, dur, cost = safe_run(func, name, state,
                                 timeout=WEEKLY_TIMEOUT_SECONDS)
        total_cost += cost
        if ok:
            print(f"  {C.GREEN}✓ {name} ({dur:.1f}s){C.RESET}")
        else:
            print(f"  {C.RED}✗ {name}{C.RESET}")

    total_dur = time.time() - start
    state.last_weekly_run = now
    log_action("weekly_agents", "Weekly theory validation cycle",
              duration=total_dur, cost=total_cost,
              next_scheduled=f"Next Sunday ({(now + timedelta(days=7)).strftime('%Y-%m-%d')})")

    # Run adaptive targeting after weekly cycle
    run_adaptive_targeting(state)

    # Run the standalone analyser suite (no LLM calls, cheap)
    run_weekly_analysers(state)


def run_weekly_analysers(state):
    """Run the 10 standalone analyser modules after weekly theory agents.

    These are pure-Python / regression / MLE-based and cost nothing. They
    populate the empirical tables the dashboard reads. Wiring them into the
    weekly cycle means the dashboard is always current without manual intervention.
    """
    import subprocess
    from pathlib import Path

    here = Path(__file__).parent

    # Order matters:
    #   - chain_to_causal_edges must run BEFORE cycle_detector
    #   - cycle_detector must run BEFORE cycle_portfolio.plan
    #   - meta_hunter can run anytime after new hypotheses land
    #   - research_diary should run LAST so it sees all updates
    #   - backfill_telemetry should run after everything else
    analyser_queue = [
        # Tier A — theory/corpus integrity (must run first)
        ("chain_to_causal_edges", "chain_to_causal_edges.py write"),
        ("cycle_detector",        "cycle_detector.py run"),
        ("cycle_chain_detector",  "cycle_chain_detector.py classify"),
        ("chain_decay_fitter",    "chain_decay_fitter.py write"),

        # Tier B — empirical framework tests
        ("formula_validator",     "formula_validator.py write"),
        ("reinforcement",         "reinforcement_measurer.py write"),
        ("halflife",              "halflife_estimator.py write"),
        ("narrative",             "narrative_detector.py write"),
        ("kill_failure",          "kill_failure_mapper.py write"),
        ("phase_transition",      "phase_transition_detector.py write"),
        ("adversarial_residual",  "adversarial_residual_classifier.py write"),
        ("residual_tam",          "residual_tam.py write"),

        # Tier C — reflexivity + moat
        ("meta_hunter",           "meta_hunter.py write"),
        ("negative_inference",    "negative_inference.py scan"),
        ("expiration_tracker",    "expiration_tracker.py scan"),
        ("self_improve_plan",     "self_improve.py apply"),

        # Tier D — trading / portfolio maintenance
        ("cycle_plan",            "cycle_portfolio.py plan"),
        ("cycle_review",          "cycle_portfolio.py review"),
        ("cycle_close_expired",   "cycle_portfolio.py close_expired"),
        ("signal_orders",         "signal_to_order.py today"),

        # Tier E — brand / publication (last — sees everything above)
        ("research_diary",        "research_diary.py"),

        # Tier F — telemetry backfill (very last)
        ("backfill_telemetry",    "backfill_telemetry.py write"),
    ]

    print_phase("ANALYSERS", f"Running {len(analyser_queue)} weekly analyser modules...")
    start = time.time()
    failed = []

    for name, script_args in analyser_queue:
        script_path = here / script_args.split()[0]
        if not script_path.exists():
            continue
        try:
            r = subprocess.run(
                ["python"] + script_args.split(),
                cwd=here, capture_output=True, text=True, timeout=600,
            )
            if r.returncode == 0:
                print(f"  {C.GREEN}✓ {name}{C.RESET}")
            else:
                failed.append(name)
                print(f"  {C.YELLOW}⚠ {name} exited {r.returncode}{C.RESET}")
        except subprocess.TimeoutExpired:
            failed.append(name)
            print(f"  {C.YELLOW}⚠ {name} timed out (>10 min){C.RESET}")
        except Exception as e:
            failed.append(name)
            print(f"  {C.YELLOW}⚠ {name}: {e}{C.RESET}")

    dur = time.time() - start
    log_action("weekly_analysers",
               f"{len(analyser_queue) - len(failed)}/{len(analyser_queue)} analysers OK",
               duration=dur, cost=0.0,
               next_scheduled="Next Sunday with weekly cycle")


def run_monthly_estimator(state):
    """Monthly (1st of month): ResidualEstimator + self-reinforcing adjustments."""
    if not THEORY_AVAILABLE:
        return
    now = datetime.now()

    # Check if it's the 1st and we haven't run this month
    if state.last_monthly_run:
        if now.month == state.last_monthly_run.month and now.year == state.last_monthly_run.year:
            return
    if now.day > 2:  # Allow 2-day window
        if state.last_monthly_run and (now - state.last_monthly_run).days < 28:
            return

    print_phase("THEORY", "Running monthly ResidualEstimator...")
    ok, dur, cost = safe_run(lambda: ResidualEstimator().run(), "ResidualEstimator", state,
                             timeout=WEEKLY_TIMEOUT_SECONDS)
    if ok:
        state.last_monthly_run = now
        log_action("residual_estimator", "Monthly bottom-up residual estimate",
                  duration=dur, cost=cost,
                  next_scheduled=f"Next 1st of month")

        # Self-reinforcing adjustments
        run_self_reinforcing_adjustments(state)


# ═══════════════════════════════════════════════════════════════════════
# ADAPTIVE TARGETING
# ═══════════════════════════════════════════════════════════════════════

def run_adaptive_targeting(state):
    """After weekly cycle: analyze evidence gaps and adjust targeting."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get evidence counts per layer
        cursor.execute("""
            SELECT layer, COUNT(*) as cnt FROM theory_evidence
            GROUP BY layer
        """)
        layer_counts = {r[0]: r[1] for r in cursor.fetchall()}
        state.evidence_gaps = layer_counts

        adjustments = []

        # 1. Find claims with least evidence
        target_50 = 50  # Need 50 for significance
        weakest_layers = sorted(
            [(l, layer_counts.get(l, 0)) for l in range(1, 14)],
            key=lambda x: x[1]
        )
        weakest = weakest_layers[0]
        if weakest[1] < target_50:
            adjustments.append(f"L{weakest[0]:02d} has only {weakest[1]} evidence points — targeting")

        # 2. Find claims closest to significance (almost at 50)
        near_sig = [(l, c) for l, c in layer_counts.items() if 30 <= c < 50]
        for l, c in near_sig:
            adjustments.append(f"L{l:02d} at {c}/50 — push to significance")

        # 3. Check formula validation r value
        cursor.execute("SELECT pearson_r FROM formula_validation ORDER BY date DESC LIMIT 1")
        fv_row = cursor.fetchone()
        if fv_row and fv_row[0] is not None and fv_row[0] < 0.3:
            adjustments.append(f"Formula r={fv_row[0]:.3f} < 0.3 — diversify domain pairs")
            # Could adjust GAP_TARGETING_RATIO higher here

        # 4. Check chain depth data
        cursor.execute("""
            SELECT chain_length, COUNT(*) FROM chains
            WHERE chain_length >= 3 GROUP BY chain_length
        """)
        deep_chains = sum(r[1] for r in cursor.fetchall())
        if deep_chains < 10:
            state.chain_extend_max = CHAIN_EXTEND_MAX_BOOSTED
            adjustments.append(f"Only {deep_chains} chains at depth 3+ — boosted CHAIN_EXTEND_MAX to {CHAIN_EXTEND_MAX_BOOSTED}")
        else:
            state.chain_extend_max = CHAIN_EXTEND_MAX_DEFAULT

        # 5. Check cycle type distribution
        cursor.execute("""
            SELECT cycle_type, COUNT(*) FROM detected_cycles
            GROUP BY cycle_type
        """)
        cycle_types = {r[0]: r[1] for r in cursor.fetchall()}
        total_cycles = sum(cycle_types.values())
        simple_pct = cycle_types.get("simple", 0) / max(1, total_cycles)
        if simple_pct > 0.7 and total_cycles >= 5:
            adjustments.append(f"Simple cycles = {simple_pct:.0%} — target 3+ domain collision sets")

        conn.close()

        if adjustments:
            log_action("adaptive_targeting",
                      f"{len(adjustments)} adjustments: {'; '.join(adjustments[:3])}",
                      next_scheduled="Next weekly cycle")
            for adj in adjustments:
                print(f"  {C.CYAN}[ADAPT] {adj}{C.RESET}")

    except Exception as e:
        print(f"  {C.YELLOW}[ORCH] Adaptive targeting failed: {e}{C.RESET}")


# ═══════════════════════════════════════════════════════════════════════
# SELF-REINFORCING ADJUSTMENTS
# ═══════════════════════════════════════════════════════════════════════

def run_self_reinforcing_adjustments(state):
    """After monthly ResidualEstimator: adjust domain params based on evidence."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get latest residual estimates per domain
        cursor.execute("""
            SELECT domain, predicted_residual_pct, observed_residual_pct,
                   estimated_residual_B, sample_size
            FROM residual_estimates
            WHERE date = (SELECT MAX(date) FROM residual_estimates)
        """)
        estimates = cursor.fetchall()
        if not estimates:
            conn.close()
            return

        adjustments = []
        now = datetime.now()

        for row in estimates:
            domain = row[0]
            predicted = row[1]
            observed = row[2]
            if observed is None or predicted is None or predicted == 0:
                continue

            ratio = observed / predicted

            # Over-performing: increase resid
            if ratio > 1.5 and row[4] and row[4] >= 10:  # sample_size >= 10
                delta = min(0.02, (ratio - 1) * 0.01)
                adjustments.append({
                    "domain": domain,
                    "direction": "increase",
                    "delta": round(delta, 4),
                    "reason": f"Observed {observed:.2f}% vs predicted {predicted:.2f}% "
                              f"(ratio {ratio:.2f}x, n={row[4]})",
                })

            # Under-performing: decrease resid
            elif ratio < 0.5 and row[4] and row[4] >= 10:
                delta = min(0.02, (1 - ratio) * 0.01)
                adjustments.append({
                    "domain": domain,
                    "direction": "decrease",
                    "delta": round(delta, 4),
                    "reason": f"Observed {observed:.2f}% vs predicted {predicted:.2f}% "
                              f"(ratio {ratio:.2f}x, n={row[4]})",
                })

        if adjustments:
            # Log as Layer 13 evidence (observer-dependent topology)
            for adj in adjustments:
                cursor.execute("""
                    INSERT INTO theory_evidence
                    (timestamp, source_event, source_id, layer, layer_name,
                     evidence_type, description, metric, observed_value,
                     predicted_value, unit, confidence, domain_pair,
                     chain_depth, cycle_detected, cycle_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now.isoformat(), "self_reinforcing_adjustment", None,
                    13, "L13_observer_dependent",
                    "direct",
                    f"Parameter adjustment for {adj['domain']}: "
                    f"{adj['direction']} resid by {adj['delta']}. {adj['reason']}",
                    "resid_parameter_delta",
                    adj["delta"] if adj["direction"] == "increase" else -adj["delta"],
                    0,  # predicted delta = 0 (we're changing the map)
                    "resid_pct", 0.7,
                    json.dumps([adj["domain"]]),
                    None, 0, None,
                ))

                state.domain_adjustments[adj["domain"]] = adj
                sign = "+" if adj["direction"] == "increase" else "-"
                print(f"  {C.MAGENTA}[SELF] {adj['domain']}: {sign}{adj['delta']} resid "
                      f"({adj['reason'][:60]}){C.RESET}")

            conn.commit()
            log_action("self_reinforcing_adjustment",
                      f"{len(adjustments)} domain params adjusted",
                      next_scheduled="Next monthly cycle")

            # Recompute collision scores with adjusted parameters
            # (The adjustments are logged but actual param changes would need
            # a config reload mechanism — for now they inform the dashboard)
            log_action("collision_recompute",
                      f"Logged {len(adjustments)} suggested parameter changes. "
                      f"Apply via config update to take effect.",
                      next_scheduled="Manual review")

        conn.close()

    except Exception as e:
        print(f"  {C.YELLOW}[ORCH] Self-reinforcing adjustment failed: {e}{C.RESET}")


# ═══════════════════════════════════════════════════════════════════════
# BUDGET CHECK
# ═══════════════════════════════════════════════════════════════════════

def check_budget(state):
    """Check if API budget allows theory agents to run.
    Returns True if theory agents should be paused."""
    try:
        # Check Anthropic API credit via environment or tracking
        # Since we don't have direct credit API access, estimate from usage
        # Theory agents are cheap (mostly Haiku), so we track cumulative cost
        if state.theory_cost_estimate > API_BUDGET_PAUSE_THRESHOLD:
            return True  # Pause theory agents

        # Also check if we can read credit from any tracking file
        credit_file = Path(__file__).parent / ".api_credit"
        if credit_file.exists():
            try:
                credit = float(credit_file.read_text().strip())
                if credit < API_BUDGET_PAUSE_THRESHOLD:
                    return True
            except (ValueError, IOError):
                pass

        return False
    except Exception:
        return False  # Don't pause on check failure


# ═══════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR LOOP
# ═══════════════════════════════════════════════════════════════════════

_shutdown = False


def signal_handler(sig, frame):
    global _shutdown
    print(f"\n{C.YELLOW}Orchestrator shutting down gracefully...{C.RESET}")
    _shutdown = True


def main():
    global _shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initialize
    init_db()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print(f"{C.RED}ERROR: Set ANTHROPIC_API_KEY in .env file{C.RESET}")
        sys.exit(1)

    state = OrchestratorState()

    # Banner
    print_banner()
    print(f"  {C.GOLD if hasattr(C, 'GOLD') else C.YELLOW}{'═' * 50}{C.RESET}")
    print(f"  {C.BOLD}HUNTER ORCHESTRATOR v1.0{C.RESET}")
    print(f"  {C.DIM}Trading pipeline + Theory proof layer{C.RESET}")
    print(f"  {C.DIM}Theory agents: {'AVAILABLE' if THEORY_AVAILABLE else 'NOT AVAILABLE'}{C.RESET}")
    print(f"  {C.DIM}INGEST_RATIO: {INGEST_RATIO}{C.RESET}")
    print(f"  {C.DIM}Domains: {len(DOMAIN_THEORY_PARAMS)}{C.RESET}")
    print(f"  {C.GOLD if hasattr(C, 'GOLD') else C.YELLOW}{'═' * 50}{C.RESET}")
    print()

    log_action("orchestrator_start", "System initialized",
              next_scheduled="First cycle immediately")

    while not _shutdown:
        state.cycle_num += 1
        cycle_start = time.time()

        try:
            # ── TRADING PIPELINE ──────────────────────────────────
            if random.random() < INGEST_RATIO:
                # INGEST MODE
                state.ingest_count += 1
                ok, dur, _ = safe_run(
                    lambda: IngestCycle(state.cycle_num).run(),
                    "IngestCycle", state
                )

                # Knowledge base stats every 50 ingest cycles
                if state.ingest_count % 50 == 0:
                    try:
                        stats = get_knowledge_base_stats()
                        print(f"  {C.DIM}KB: {stats['total_facts']} facts, "
                              f"{stats['total_anomalies']} anomalies, "
                              f"{stats.get('unique_entities', 0)} entities{C.RESET}")
                    except Exception:
                        pass

            else:
                # COLLISION MODE
                state.collision_count += 1
                ok, dur, _ = safe_run(
                    lambda: CollisionCycle(state.cycle_num).run(),
                    "CollisionCycle", state
                )

                # After every collision cycle: run TheoryTelemetry
                # (This is already hooked into CollisionCycle via hunter.py,
                #  but we log it for orchestrator tracking)
                if ok and THEORY_AVAILABLE and not check_budget(state):
                    # TheoryTelemetry runs inline during CollisionCycle
                    # No separate call needed — it's hooked in hunter.py
                    pass

            # ── THEORY SCHEDULING ─────────────────────────────────
            budget_paused = check_budget(state)
            if budget_paused:
                if state.cycle_num % 100 == 0:
                    print(f"  {C.YELLOW}[BUDGET] Theory agents paused "
                          f"(${state.theory_cost_estimate:.2f} spent){C.RESET}")

            if not budget_paused and THEORY_AVAILABLE:
                # Daily: DecayTracker
                run_decay_tracker(state)

                # Weekly: full agent suite (prefer Sunday)
                now = datetime.now()
                is_sunday = now.weekday() == 6
                if state.last_weekly_run is None or \
                   (now - state.last_weekly_run).total_seconds() / 86400 >= WEEKLY_INTERVAL_DAYS:
                    if is_sunday or state.last_weekly_run is None or \
                       (now - state.last_weekly_run).total_seconds() / 86400 >= WEEKLY_INTERVAL_DAYS + 1:
                        run_weekly_agents(state)

                # Monthly: ResidualEstimator + self-reinforcing
                run_monthly_estimator(state)

            # ── DAILY SYNTHESIS ────────────────────────────────────
            hours_since_synthesis = (time.time() - state.last_synthesis_time) / 3600
            if state.ingest_count > 0 and (
                state.ingest_count % SYNTHESIS_INTERVAL_CYCLES == 0
                or hours_since_synthesis >= SYNTHESIS_INTERVAL_HOURS
            ):
                ok, dur, _ = safe_run(run_daily_synthesis, "daily_synthesis", state)
                if ok:
                    state.last_synthesis_time = time.time()
                    log_action("daily_synthesis", "Periodic synthesis",
                              duration=dur)

        except SystemExit as e:
            print(f"\n{C.YELLOW}Stopping: {e}{C.RESET}")
            break

        except Exception as e:
            print_error(f"Cycle {state.cycle_num} failed: {e}")
            traceback.print_exc()
            state.consecutive_errors += 1

            # If too many consecutive errors, pause
            if state.consecutive_errors >= 5:
                print(f"  {C.RED}[ORCH] 5 consecutive errors — pausing 30s{C.RESET}")
                time.sleep(30)
                state.consecutive_errors = 0

        if _shutdown:
            break

        # Pause between cycles
        pause = random.uniform(CYCLE_PAUSE_MIN, CYCLE_PAUSE_MAX)
        cycle_dur = time.time() - cycle_start
        print(f"  {C.DIM}Cycle {state.cycle_num} ({cycle_dur:.1f}s). "
              f"I:{state.ingest_count} C:{state.collision_count}. "
              f"Next in {pause:.0f}s...{C.RESET}")
        time.sleep(pause)

    # ── SHUTDOWN ──────────────────────────────────────────────────
    session_dur = time.time() - state.start_time
    print(f"\n{C.BOLD}{'═' * 50}{C.RESET}")
    print(f"{C.BOLD}Orchestrator session complete.{C.RESET}")
    print(f"  Duration: {session_dur/3600:.1f}h")
    print(f"  Cycles: {state.cycle_num} (I:{state.ingest_count}, C:{state.collision_count})")
    print(f"  Theory cost: ~${state.theory_cost_estimate:.2f}")
    print(f"  Errors: {len(state.errors)}")

    try:
        stats = get_knowledge_base_stats()
        rate = get_collision_to_hypothesis_rate()
        print(f"  Facts: {stats['total_facts']} | Anomalies: {stats['total_anomalies']}")
        print(f"  Collision → Hypothesis rate: {rate*100:.1f}%")
    except Exception:
        pass

    # Log final state
    if state.domain_adjustments:
        print(f"\n  {C.MAGENTA}Domain adjustments this session:{C.RESET}")
        for domain, adj in state.domain_adjustments.items():
            sign = "+" if adj["direction"] == "increase" else "-"
            print(f"    {domain}: {sign}{adj['delta']} resid")

    log_action("orchestrator_shutdown",
              f"Session complete: {state.cycle_num} cycles, "
              f"~${state.theory_cost_estimate:.2f} theory cost",
              duration=session_dur)

    print(f"{C.BOLD}{'═' * 50}{C.RESET}")


if __name__ == "__main__":
    main()
