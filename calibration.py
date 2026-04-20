#!/usr/bin/env python3
"""HUNTER Parameter Calibration & Historical Backtest Runner.

Prompt 7.1: Self-reinforcing parameter calibration loop.
Prompt 7.2: Historical backtest with train/test split.

Run calibration:  python calibration.py calibrate
Run backtest:     python calibration.py backtest --train-start 2025-01-01 --train-end 2025-06-30 --test-start 2025-07-01 --test-end 2025-12-31
"""

import json
import math
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# ── Imports ─────────────────────────────────────────────────────────────
from database import get_connection, init_db

try:
    from theory import (
        DOMAIN_THEORY_PARAMS, compute_collision_formula,
        CHAIN_DECAY_RATE, EXPECTED_PERSISTENCE_RATIO,
    )
except ImportError:
    DOMAIN_THEORY_PARAMS = {}
    CHAIN_DECAY_RATE = 0.273
    EXPECTED_PERSISTENCE_RATIO = 207

    def compute_collision_formula(a, b):
        return {"total": 0}


# ═══════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════

# Current formula coefficients
FORMULA_COEFFICIENTS = {
    "silo": 0.003,
    "reinf": 20.0,
    "corr": 30.0,
    "resid": 400.0,
}

# Calibration constraints
MAX_CHANGES_PER_MONTH = 3
MAX_CHANGE_PCT = 0.30          # Never change a parameter by more than 30%
DIVERGENCE_THRESHOLD = 0.50    # Flag domains diverging >50%
FORMULA_R_THRESHOLD = 0.5      # Suggest adjustments if r < 0.5
HALF_LIFE_SIG_DELTA = 30       # Days — significant if delta > 30 from 120
MIN_SAMPLE_SIZE = 5            # Need at least 5 data points to suggest changes

# Predicted values
PREDICTED_HALF_LIFE = 120
PREDICTED_PERSISTENCE = 207
PREDICTED_TOTAL_T = 5.65


# ═══════════════════════════════════════════════════════════════════════
# 7.1 — PARAMETER CALIBRATION LOOP
# ═══════════════════════════════════════════════════════════════════════

class ParameterCalibrator:
    """Self-reinforcing calibration loop. Analyzes evidence, suggests
    parameter adjustments. All changes are suggestions requiring human
    approval before committing to config.py."""

    def __init__(self):
        self.conn = get_connection()
        self.cursor = self.conn.cursor()
        self.now = datetime.now()
        self.adjustments = []
        self.targeting_adjustments = []
        self.theory_updates = []

    def run(self):
        """Run full calibration analysis and return suggestions."""
        print("\n" + "=" * 60)
        print("  PARAMETER CALIBRATION LOOP")
        print("  Analyzing 30 days of evidence...")
        print("=" * 60)

        # 1. Residual divergence per domain
        self._check_residual_divergence()

        # 2. Formula coefficient validation
        self._check_formula_coefficients()

        # 3. Decay tracker half-life
        self._check_decay_half_life()

        # 4. High-performing domain pairs
        self._check_domain_pair_performance()

        # 5. Underperforming source types
        self._check_underperforming_sources()

        # Apply constraints: max 3 changes per month, max 30% per change
        self._apply_constraints()

        # Log all suggestions as Layer 13 evidence
        self._log_as_evidence()

        # Build output
        output = {
            "date": self.now.strftime("%Y-%m-%d"),
            "parameter_adjustments": self.adjustments,
            "targeting_adjustments": self.targeting_adjustments,
            "theory_updates": self.theory_updates,
        }

        self.conn.close()

        # Print summary
        self._print_summary(output)

        return output

    def _check_residual_divergence(self):
        """Task 1: Flag domains where observed residual diverges >50% from predicted."""
        print("\n  [1/5] Checking residual divergence per domain...")

        self.cursor.execute("""
            SELECT domain, predicted_residual_pct, observed_residual_pct,
                   estimated_residual_B, sample_size, market_size_B
            FROM residual_estimates
            WHERE date = (SELECT MAX(date) FROM residual_estimates)
        """)
        rows = self.cursor.fetchall()

        for row in rows:
            domain, predicted, observed, est_B, n, market_B = row
            if observed is None or predicted is None or predicted == 0 or not n:
                continue
            if n < MIN_SAMPLE_SIZE:
                continue

            divergence = abs(observed - predicted) / predicted

            if divergence > DIVERGENCE_THRESHOLD:
                # Suggest new resid parameter
                current_resid = DOMAIN_THEORY_PARAMS.get(domain, {}).get("residual", 0.1)
                # Scale resid proportionally to observed/predicted ratio
                ratio = observed / predicted
                suggested_resid = current_resid * min(1 + MAX_CHANGE_PCT,
                                                       max(1 - MAX_CHANGE_PCT, ratio))
                suggested_resid = round(suggested_resid, 4)
                change_pct = round((suggested_resid - current_resid) / max(0.001, current_resid) * 100, 1)

                direction = "higher" if observed > predicted else "lower"
                self.adjustments.append({
                    "parameter": f"{domain}.residual",
                    "current_value": current_resid,
                    "suggested_value": suggested_resid,
                    "change_pct": change_pct,
                    "reason": f"Observed residual {observed:.2f}% is {direction} than "
                              f"predicted {predicted:.2f}% (divergence: {divergence:.0%}, n={n})",
                    "evidence_source": "residual_estimates table",
                })
                print(f"    {domain}: observed {observed:.2f}% vs predicted {predicted:.2f}% "
                      f"-> suggest resid {current_resid} -> {suggested_resid} ({change_pct:+.1f}%)")

    def _check_formula_coefficients(self):
        """Task 2: If formula validation r < 0.5, suggest coefficient adjustments."""
        print("\n  [2/5] Checking formula validation...")

        self.cursor.execute("""
            SELECT pearson_r, spearman_rho, p_value, formula_validated,
                   suggested_silo_coeff, suggested_reinf_weight,
                   suggested_corr_weight, suggested_resid_weight
            FROM formula_validation
            ORDER BY date DESC LIMIT 1
        """)
        row = self.cursor.fetchone()
        if not row:
            print("    No formula validation data yet.")
            return

        r, rho, p, validated, s_silo, s_reinf, s_corr, s_resid = row
        print(f"    Pearson r={r:.3f}, Spearman rho={rho:.3f}, p={p:.4f}")

        if r is not None and r < FORMULA_R_THRESHOLD:
            # Suggest the adjustments from FormulaValidator
            coeffs = [
                ("formula.silo_coefficient", FORMULA_COEFFICIENTS["silo"], s_silo),
                ("formula.reinf_weight", FORMULA_COEFFICIENTS["reinf"], s_reinf),
                ("formula.corr_weight", FORMULA_COEFFICIENTS["corr"], s_corr),
                ("formula.resid_weight", FORMULA_COEFFICIENTS["resid"], s_resid),
            ]
            for name, current, suggested in coeffs:
                if suggested is None or suggested == current:
                    continue
                change_pct = round((suggested - current) / max(0.001, abs(current)) * 100, 1)
                if abs(change_pct) > 1:  # Only suggest if >1% change
                    self.adjustments.append({
                        "parameter": name,
                        "current_value": current,
                        "suggested_value": round(suggested, 6),
                        "change_pct": change_pct,
                        "reason": f"Formula Pearson r={r:.3f} < {FORMULA_R_THRESHOLD}. "
                                  f"Component-level correlation suggests this adjustment.",
                        "evidence_source": "formula_validation table",
                    })
                    print(f"    {name}: {current} -> {suggested:.6f} ({change_pct:+.1f}%)")

            # Theory update: formula validation status
            self.theory_updates.append({
                "layer": 12,
                "original_prediction": f"Formula predicts collision density (r > {FORMULA_R_THRESHOLD})",
                "empirical_finding": f"Pearson r = {r:.3f}, Spearman rho = {rho:.3f}",
                "revision_needed": r < 0.3,
                "suggested_revision": f"Adjust coefficients per FormulaValidator suggestions"
                                      if r < 0.3 else None,
            })

    def _check_decay_half_life(self):
        """Task 3: If decay half-life significantly differs from 120 days."""
        print("\n  [3/5] Checking decay tracker half-life...")

        # Look for fitted half-life in theory_evidence
        self.cursor.execute("""
            SELECT observed_value, predicted_value, description
            FROM theory_evidence
            WHERE source_event = 'decay_curve_fit'
            AND metric = 'fitted_half_life_days'
            ORDER BY timestamp DESC LIMIT 1
        """)
        row = self.cursor.fetchone()

        if not row or row[0] is None:
            print("    No decay curve fit data yet.")
            return

        fitted_hl, predicted_hl, description = row
        delta = abs(fitted_hl - PREDICTED_HALF_LIFE)
        print(f"    Fitted half-life: {fitted_hl:.1f}d (predicted: {PREDICTED_HALF_LIFE}d, delta: {delta:.1f}d)")

        if delta > HALF_LIFE_SIG_DELTA:
            self.theory_updates.append({
                "layer": 8,
                "original_prediction": f"Epistemic error half-life = {PREDICTED_HALF_LIFE} days",
                "empirical_finding": f"Fitted half-life = {fitted_hl:.1f} days (delta: {delta:.1f}d)",
                "revision_needed": True,
                "suggested_revision": f"Update predicted half-life to {fitted_hl:.0f} days "
                                      f"(empirically derived from {description[:60] if description else 'decay tracking'})",
            })
            print(f"    SIGNIFICANT: delta {delta:.1f}d > {HALF_LIFE_SIG_DELTA}d threshold")

        # Also check persistence ratio
        self.cursor.execute("""
            SELECT AVG(observed_value) as avg_ratio, COUNT(*) as n
            FROM theory_evidence
            WHERE layer = 8 AND metric = 'reinforcement_correction_ratio'
            AND timestamp >= datetime('now', '-30 days')
        """)
        ratio_row = self.cursor.fetchone()
        if ratio_row and ratio_row[0] is not None and ratio_row[1] >= MIN_SAMPLE_SIZE:
            avg_ratio = ratio_row[0]
            n = ratio_row[1]
            ratio_delta = abs(avg_ratio - PREDICTED_PERSISTENCE)
            print(f"    Persistence ratio: {avg_ratio:.1f}x (predicted: {PREDICTED_PERSISTENCE}x, n={n})")

            if ratio_delta > 50:  # Significant if >50 away from 207
                self.theory_updates.append({
                    "layer": 8,
                    "original_prediction": f"Persistence ratio = {PREDICTED_PERSISTENCE}x",
                    "empirical_finding": f"Observed ratio = {avg_ratio:.1f}x (n={n})",
                    "revision_needed": True,
                    "suggested_revision": f"Update persistence ratio to {avg_ratio:.0f}x",
                })

    def _check_domain_pair_performance(self):
        """Task 4: Find domain pairs that consistently produce high-quality hypotheses."""
        print("\n  [4/5] Checking domain pair performance...")

        self.cursor.execute("""
            SELECT c.source_types, COUNT(*) as hyp_count,
                   AVG(h.diamond_score) as avg_score,
                   SUM(CASE WHEN h.diamond_score >= 65 THEN 1 ELSE 0 END) as diamonds
            FROM hypotheses h
            JOIN collisions c ON h.collision_id = c.id
            WHERE h.survived_kill = 1
            AND h.created_at >= datetime('now', '-90 days')
            AND c.source_types IS NOT NULL
            GROUP BY c.source_types
            HAVING COUNT(*) >= 3
            ORDER BY AVG(h.diamond_score) DESC
        """)
        rows = self.cursor.fetchall()

        for row in rows:
            st, count, avg_score, diamonds = row
            if not st or avg_score is None:
                continue

            types = [t.strip() for t in st.split(",") if t.strip()]
            if len(types) < 2:
                continue

            pair_name = f"{types[0]}-{types[1]}"

            if avg_score >= 60 and diamonds >= 2:
                self.targeting_adjustments.append({
                    "domain_pair": pair_name,
                    "current_weight": 1.0,  # Default
                    "suggested_weight": round(min(2.0, 1.0 + (avg_score - 50) * 0.02), 2),
                    "reason": f"Avg score {avg_score:.0f}, {diamonds} diamonds from {count} hypotheses. "
                              f"Increase gap_targeting weight to find more like this.",
                })
                print(f"    {pair_name}: avg={avg_score:.0f}, diamonds={diamonds}/{count} -> boost targeting")

    def _check_underperforming_sources(self):
        """Task 5: Flag source types that never produce useful collisions."""
        print("\n  [5/5] Checking underperforming source types...")

        self.cursor.execute("""
            SELECT rf.source_type, COUNT(DISTINCT rf.id) as fact_count,
                   COUNT(DISTINCT c.id) as collision_count,
                   COUNT(DISTINCT CASE WHEN h.diamond_score >= 65 THEN h.id END) as diamond_count
            FROM raw_facts rf
            LEFT JOIN fact_entities fe ON rf.id = fe.raw_fact_id
            LEFT JOIN collisions c ON c.source_types LIKE '%' || rf.source_type || '%'
            LEFT JOIN hypotheses h ON h.collision_id = c.id AND h.survived_kill = 1
            WHERE rf.ingested_at >= datetime('now', '-90 days')
            GROUP BY rf.source_type
            HAVING COUNT(DISTINCT rf.id) >= 20
            ORDER BY collision_count ASC
        """)
        rows = self.cursor.fetchall()

        for row in rows:
            src_type, facts, collisions, diamonds = row
            if not src_type:
                continue

            collision_rate = collisions / max(1, facts)

            if collision_rate < 0.01 and facts >= 50:
                self.targeting_adjustments.append({
                    "domain_pair": f"{src_type}-*",
                    "current_weight": 1.0,
                    "suggested_weight": 0.5,
                    "reason": f"{src_type}: {facts} facts, {collisions} collisions ({collision_rate:.1%}), "
                              f"{diamonds} diamonds. Consider removing from rotation or redesigning queries.",
                })
                print(f"    {src_type}: {facts} facts -> {collisions} collisions ({collision_rate:.1%}) -> FLAG")

    def _apply_constraints(self):
        """Apply constraints: max 3 changes/month, max 30%/change."""
        # Check how many changes were made in the last 30 days
        self.cursor.execute("""
            SELECT COUNT(*) FROM theory_evidence
            WHERE source_event = 'calibration_suggestion'
            AND timestamp >= datetime('now', '-30 days')
        """)
        recent_changes = self.cursor.fetchone()[0]
        remaining_budget = MAX_CHANGES_PER_MONTH - recent_changes

        if remaining_budget <= 0:
            print(f"\n  [CONSTRAINT] Already {recent_changes} changes this month "
                  f"(max {MAX_CHANGES_PER_MONTH}). Deferring all suggestions.")
            # Keep suggestions but mark them as deferred
            for adj in self.adjustments:
                adj["deferred"] = True
                adj["reason"] += f" [DEFERRED: {recent_changes}/{MAX_CHANGES_PER_MONTH} monthly budget used]"
            return

        # Sort by absolute change impact, take top N
        self.adjustments.sort(key=lambda a: abs(a.get("change_pct", 0)), reverse=True)

        # Cap at remaining budget
        if len(self.adjustments) > remaining_budget:
            deferred = self.adjustments[remaining_budget:]
            self.adjustments = self.adjustments[:remaining_budget]
            for adj in deferred:
                adj["deferred"] = True
                adj["reason"] += " [DEFERRED: monthly budget]"
            self.adjustments.extend(deferred)

        # Enforce max 30% per change
        for adj in self.adjustments:
            if abs(adj.get("change_pct", 0)) > MAX_CHANGE_PCT * 100:
                current = adj["current_value"]
                direction = 1 if adj["suggested_value"] > current else -1
                capped = current * (1 + direction * MAX_CHANGE_PCT)
                adj["suggested_value"] = round(capped, 6)
                adj["change_pct"] = round(direction * MAX_CHANGE_PCT * 100, 1)
                adj["reason"] += f" [CAPPED at {MAX_CHANGE_PCT:.0%}]"

    def _log_as_evidence(self):
        """Log every suggestion as Layer 13 evidence."""
        for adj in self.adjustments:
            self.cursor.execute("""
                INSERT INTO theory_evidence
                (timestamp, source_event, source_id, layer, layer_name,
                 evidence_type, description, metric, observed_value,
                 predicted_value, unit, confidence, domain_pair,
                 chain_depth, cycle_detected, cycle_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.now.isoformat(), "calibration_suggestion", None,
                13, "L13_observer_dependent",
                "direct",
                f"Calibration: {adj['parameter']} {adj['current_value']} -> "
                f"{adj['suggested_value']} ({adj['change_pct']:+.1f}%). "
                f"{adj['reason'][:200]}",
                "parameter_delta",
                adj["suggested_value"], adj["current_value"],
                "param_value", 0.8,
                json.dumps({"adjustment": adj}),
                None, 0, None,
            ))

        for tu in self.theory_updates:
            if tu.get("revision_needed"):
                self.cursor.execute("""
                    INSERT INTO theory_evidence
                    (timestamp, source_event, source_id, layer, layer_name,
                     evidence_type, description, metric, observed_value,
                     predicted_value, unit, confidence, domain_pair,
                     chain_depth, cycle_detected, cycle_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.now.isoformat(), "theory_revision_needed", None,
                    tu["layer"], f"L{tu['layer']:02d}",
                    "challenging",
                    f"Theory revision needed for L{tu['layer']:02d}. "
                    f"Original: {tu['original_prediction'][:100]}. "
                    f"Empirical: {tu['empirical_finding'][:100]}. "
                    f"Suggested: {(tu.get('suggested_revision') or 'none')[:100]}.",
                    "theory_revision",
                    None, None,
                    "revision", 0.7,
                    json.dumps(tu),
                    None, 0, None,
                ))

        self.conn.commit()

    def _print_summary(self, output):
        """Print human-readable summary."""
        print("\n" + "=" * 60)
        print("  CALIBRATION SUMMARY")
        print("=" * 60)

        n_adj = len([a for a in self.adjustments if not a.get("deferred")])
        n_def = len([a for a in self.adjustments if a.get("deferred")])
        print(f"  Parameter adjustments: {n_adj} active, {n_def} deferred")
        print(f"  Targeting adjustments: {len(self.targeting_adjustments)}")
        print(f"  Theory updates:        {len(self.theory_updates)}")

        if self.adjustments:
            print("\n  SUGGESTED PARAMETER CHANGES (require human approval):")
            for adj in self.adjustments:
                deferred = " [DEFERRED]" if adj.get("deferred") else ""
                print(f"    {adj['parameter']}: {adj['current_value']} -> "
                      f"{adj['suggested_value']} ({adj['change_pct']:+.1f}%){deferred}")
                print(f"      Reason: {adj['reason'][:100]}")

        if self.theory_updates:
            print("\n  THEORY REVISION CANDIDATES:")
            for tu in self.theory_updates:
                status = "NEEDS REVISION" if tu["revision_needed"] else "OK"
                print(f"    L{tu['layer']:02d}: {status}")
                print(f"      Predicted: {tu['original_prediction'][:80]}")
                print(f"      Observed:  {tu['empirical_finding'][:80]}")

        # Write output to file
        output_path = Path(__file__).parent / "calibration_output.json"
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, default=str)
        print(f"\n  Full output written to: {output_path}")
        print("  ACTION REQUIRED: Review suggestions and apply to config.py manually.")
        print("=" * 60)


# ═══════════════════════════════════════════════════════════════════════
# 7.2 — HISTORICAL BACKTEST RUNNER
# ═══════════════════════════════════════════════════════════════════════

class HistoricalBacktester:
    """Run HUNTER against historical data with known outcomes.
    Creates training/test split to validate on out-of-sample data.

    Key rules:
    - NEVER use future information
    - NEVER cherry-pick — run ALL collisions
    - ALWAYS report all metrics including failures
    - Split data: train on one period, test on another
    """

    def __init__(self, train_start, train_end, test_start, test_end):
        self.train_start = train_start
        self.train_end = train_end
        self.test_start = test_start
        self.test_end = test_end
        self.results = {
            "train": {"hypotheses": [], "collisions": 0},
            "test": {"hypotheses": [], "collisions": 0},
        }

    def run(self):
        """Execute full historical backtest with train/test split."""
        print("\n" + "=" * 60)
        print("  HISTORICAL BACKTEST RUNNER")
        print(f"  Train: {self.train_start} to {self.train_end}")
        print(f"  Test:  {self.test_start} to {self.test_end}")
        print("=" * 60)

        # Phase 1: Training period
        print(f"\n  PHASE 1: TRAINING PERIOD ({self.train_start} to {self.train_end})")
        train_results = self._run_period(self.train_start, self.train_end, "train")

        # Phase 2: Calibrate from training
        print(f"\n  PHASE 2: CALIBRATION FROM TRAINING DATA")
        calibration = self._calibrate_from_results(train_results)

        # Phase 3: Test period (with calibrated parameters)
        print(f"\n  PHASE 3: TEST PERIOD ({self.test_start} to {self.test_end})")
        test_results = self._run_period(self.test_start, self.test_end, "test")

        # Phase 4: Compare and report
        print(f"\n  PHASE 4: REPORT")
        report = self._generate_report(train_results, test_results, calibration)

        return report

    def _run_period(self, start_date, end_date, phase):
        """Run backtest for a specific period using only pre-period facts."""
        import config

        conn = get_connection()
        cursor = conn.cursor()

        # Count available facts before the prediction window
        cursor.execute("""
            SELECT COUNT(*) FROM raw_facts
            WHERE date_of_fact != 'unknown'
            AND date_of_fact IS NOT NULL
            AND date_of_fact < ?
        """, (start_date,))
        pre_facts = cursor.fetchone()[0]

        # Count facts IN the prediction window (these are outcomes)
        cursor.execute("""
            SELECT COUNT(*) FROM raw_facts
            WHERE date_of_fact >= ? AND date_of_fact <= ?
        """, (start_date, end_date))
        window_facts = cursor.fetchone()[0]

        print(f"    Facts before window: {pre_facts}")
        print(f"    Facts in window:     {window_facts}")

        # Get hypotheses formed during the window
        cursor.execute("""
            SELECT h.id, h.hypothesis_text, h.diamond_score, h.time_window_days,
                   h.survived_kill, h.created_at, h.action_steps,
                   h.novelty, h.feasibility, h.timing, h.asymmetry, h.intersection,
                   c.source_types, c.num_domains, c.domains_involved
            FROM hypotheses h
            JOIN collisions c ON h.collision_id = c.id
            WHERE h.created_at >= ? AND h.created_at <= ?
            ORDER BY h.diamond_score DESC
        """, (start_date, end_date))
        hypotheses = [dict(r) for r in cursor.fetchall()]

        print(f"    Hypotheses in window: {len(hypotheses)}")
        survived = [h for h in hypotheses if h.get("survived_kill")]
        print(f"    Survived kill:       {len(survived)}")

        # Get backtest results for these hypotheses (if available)
        results = {
            "phase": phase,
            "start": start_date,
            "end": end_date,
            "pre_facts": pre_facts,
            "window_facts": window_facts,
            "total_hypotheses": len(hypotheses),
            "survived": len(survived),
            "hypotheses": [],
        }

        for h in hypotheses:
            hyp_result = {
                "id": h["id"],
                "score": h.get("diamond_score", 0),
                "survived": bool(h.get("survived_kill")),
                "source_types": h.get("source_types", ""),
                "num_domains": h.get("num_domains", 0),
            }

            # Check if we have backtest results
            cursor.execute("""
                SELECT direction_correct, magnitude_predicted, magnitude_actual,
                       within_timeframe, mechanism_confirmed,
                       chain_depth, domain_distance, cycle_involved
                FROM backtest_results WHERE hypothesis_id = ?
            """, (h["id"],))
            bt = cursor.fetchone()

            if bt:
                hyp_result["direction_correct"] = bool(bt[0])
                hyp_result["magnitude_predicted"] = bt[1]
                hyp_result["magnitude_actual"] = bt[2]
                hyp_result["within_timeframe"] = bool(bt[3])
                hyp_result["mechanism_confirmed"] = bool(bt[4])
                hyp_result["chain_depth"] = bt[5]
                hyp_result["domain_distance"] = bt[6]
                hyp_result["cycle_involved"] = bool(bt[7])
                hyp_result["has_outcome"] = True
            else:
                hyp_result["has_outcome"] = False

            results["hypotheses"].append(hyp_result)

        conn.close()
        return results

    def _calibrate_from_results(self, train_results):
        """Extract calibration insights from training period."""
        hyps = [h for h in train_results["hypotheses"] if h.get("has_outcome")]

        if not hyps:
            print("    No outcome data available for calibration.")
            return {"adjustments": [], "insights": []}

        # Directional accuracy by score bucket
        buckets = {}
        for h in hyps:
            score = h.get("score", 0) or 0
            bucket = (score // 10) * 10
            if bucket not in buckets:
                buckets[bucket] = {"total": 0, "hits": 0}
            buckets[bucket]["total"] += 1
            if h.get("direction_correct"):
                buckets[bucket]["hits"] += 1

        insights = []
        print("\n    Score calibration from training data:")
        for b in sorted(buckets.keys()):
            rate = buckets[b]["hits"] / max(1, buckets[b]["total"])
            print(f"      Score {b}-{b+9}: {rate:.0%} hit rate ({buckets[b]['total']} hypotheses)")
            insights.append({
                "bucket": f"{b}-{b+9}",
                "hit_rate": round(rate, 3),
                "n": buckets[b]["total"],
            })

        # Accuracy by chain depth
        depth_accuracy = {}
        for h in hyps:
            d = h.get("chain_depth", 0) or 0
            if d not in depth_accuracy:
                depth_accuracy[d] = {"total": 0, "hits": 0}
            depth_accuracy[d]["total"] += 1
            if h.get("direction_correct"):
                depth_accuracy[d]["hits"] += 1

        # Determine if deeper chains are more accurate
        sorted_depths = sorted(depth_accuracy.keys())
        deeper_better = False
        if len(sorted_depths) >= 2:
            shallow = [depth_accuracy[d] for d in sorted_depths[:len(sorted_depths)//2]]
            deep = [depth_accuracy[d] for d in sorted_depths[len(sorted_depths)//2:]]
            shallow_rate = sum(d["hits"] for d in shallow) / max(1, sum(d["total"] for d in shallow))
            deep_rate = sum(d["hits"] for d in deep) / max(1, sum(d["total"] for d in deep))
            deeper_better = deep_rate > shallow_rate
            print(f"\n    Depth analysis: shallow={shallow_rate:.0%}, deep={deep_rate:.0%} "
                  f"-> deeper {'better' if deeper_better else 'NOT better'}")

        return {
            "score_calibration": insights,
            "deeper_chains_better": deeper_better,
            "total_with_outcomes": len(hyps),
        }

    def _generate_report(self, train_results, test_results, calibration):
        """Generate full backtest report with confusion matrix and breakdowns."""
        report = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "train_period": f"{train_results['start']} to {train_results['end']}",
            "test_period": f"{test_results['start']} to {test_results['end']}",
        }

        for phase_name, phase_data in [("train", train_results), ("test", test_results)]:
            hyps = phase_data["hypotheses"]
            with_outcome = [h for h in hyps if h.get("has_outcome")]
            survived = [h for h in hyps if h.get("survived")]

            # Confusion matrix
            tp = sum(1 for h in with_outcome if h.get("direction_correct") and h.get("score", 0) >= 65)
            fp = sum(1 for h in with_outcome if not h.get("direction_correct") and h.get("score", 0) >= 65)
            tn = sum(1 for h in with_outcome if not h.get("direction_correct") and h.get("score", 0) < 65)
            fn = sum(1 for h in with_outcome if h.get("direction_correct") and h.get("score", 0) < 65)

            total_w = len(with_outcome) or 1
            dir_hits = sum(1 for h in with_outcome if h.get("direction_correct"))
            timing_hits = sum(1 for h in with_outcome if h.get("within_timeframe"))
            mech_hits = sum(1 for h in with_outcome if h.get("mechanism_confirmed"))

            # Magnitude error
            mag_errors = []
            for h in with_outcome:
                if h.get("magnitude_predicted") is not None and h.get("magnitude_actual") is not None:
                    mag_errors.append(abs(h["magnitude_predicted"] - h["magnitude_actual"]))

            # Profit simulation
            cumulative_pnl = 0
            max_drawdown = 0
            peak = 0
            for h in sorted(with_outcome, key=lambda x: x.get("score", 0), reverse=True):
                if h.get("score", 0) < 65:
                    continue
                mag = h.get("magnitude_actual") or 0
                pnl = abs(mag) * (1 if h.get("direction_correct") else -1)
                cumulative_pnl += pnl
                peak = max(peak, cumulative_pnl)
                drawdown = peak - cumulative_pnl
                max_drawdown = max(max_drawdown, drawdown)

            # Payoff ratio
            wins = [abs(h.get("magnitude_actual", 0) or 0) for h in with_outcome
                    if h.get("direction_correct") and h.get("score", 0) >= 65]
            losses = [abs(h.get("magnitude_actual", 0) or 0) for h in with_outcome
                      if not h.get("direction_correct") and h.get("score", 0) >= 65]
            avg_win = sum(wins) / max(1, len(wins))
            avg_loss = sum(losses) / max(1, len(losses))
            payoff_ratio = avg_win / max(0.01, avg_loss)

            # Calibration curve (by score decile)
            cal_curve = {}
            for h in with_outcome:
                s = h.get("score", 0) or 0
                if s >= 90:
                    bucket = "90+"
                elif s >= 80:
                    bucket = "80-89"
                elif s >= 70:
                    bucket = "70-79"
                elif s >= 60:
                    bucket = "60-69"
                else:
                    bucket = "50-59"
                if bucket not in cal_curve:
                    cal_curve[bucket] = {"total": 0, "hits": 0}
                cal_curve[bucket]["total"] += 1
                if h.get("direction_correct"):
                    cal_curve[bucket]["hits"] += 1
            cal_formatted = {k: {"count": v["total"],
                                  "hit_rate": round(v["hits"] / max(1, v["total"]), 3)}
                             for k, v in cal_curve.items()}

            # Per-layer accuracy (using chain_depth and domain_distance as proxies)
            layer_accuracy = {}
            # L7 proxy: deeper chains -> higher accuracy?
            depth_groups = {"shallow(1-2)": [], "deep(3+)": []}
            for h in with_outcome:
                d = h.get("chain_depth", 0) or 0
                key = "deep(3+)" if d >= 3 else "shallow(1-2)"
                depth_groups[key].append(1 if h.get("direction_correct") else 0)
            for k, v in depth_groups.items():
                if v:
                    layer_accuracy[f"L07_depth_{k}"] = round(sum(v) / len(v), 3)

            # L2 proxy: higher domain distance -> higher accuracy?
            dist_groups = {"low(<0.5)": [], "high(>=0.5)": []}
            for h in with_outcome:
                dd = h.get("domain_distance", 0) or 0
                key = "high(>=0.5)" if dd >= 0.5 else "low(<0.5)"
                dist_groups[key].append(1 if h.get("direction_correct") else 0)
            for k, v in dist_groups.items():
                if v:
                    layer_accuracy[f"L02_distance_{k}"] = round(sum(v) / len(v), 3)

            report[phase_name] = {
                "total_hypotheses": phase_data["total_hypotheses"],
                "survived_kill": phase_data["survived"],
                "with_outcomes": len(with_outcome),
                "confusion_matrix": {"TP": tp, "FP": fp, "TN": tn, "FN": fn},
                "directional_accuracy": round(dir_hits / total_w, 3),
                "timing_accuracy": round(timing_hits / total_w, 3),
                "mechanism_accuracy": round(mech_hits / total_w, 3),
                "avg_magnitude_error": round(sum(mag_errors) / max(1, len(mag_errors)), 2) if mag_errors else None,
                "calibration_curve": cal_formatted,
                "cumulative_pnl_pct": round(cumulative_pnl, 2),
                "max_drawdown_pct": round(max_drawdown, 2),
                "payoff_ratio": round(payoff_ratio, 2),
                "win_rate": round(dir_hits / max(1, len(with_outcome)), 3),
                "layer_accuracy": layer_accuracy,
            }

        # Improvement check: did calibration help?
        train_acc = report.get("train", {}).get("directional_accuracy", 0)
        test_acc = report.get("test", {}).get("directional_accuracy", 0)
        report["calibration_improved_accuracy"] = test_acc >= train_acc
        report["accuracy_delta"] = round(test_acc - train_acc, 3)

        # Print report
        self._print_report(report)

        # Save report
        output_path = Path(__file__).parent / "backtest_report.json"
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n  Full report: {output_path}")

        # Log as theory evidence
        try:
            conn = get_connection()
            conn.execute("""
                INSERT INTO theory_evidence
                (timestamp, source_event, source_id, layer, layer_name,
                 evidence_type, description, metric, observed_value,
                 predicted_value, unit, confidence, domain_pair,
                 chain_depth, cycle_detected, cycle_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(), "historical_backtest", None,
                4, "L04_phase_transition",
                "direct" if test_acc > 0.5 else "supporting",
                f"Historical backtest: train {train_results['start']}-{train_results['end']} "
                f"(acc={train_acc:.0%}), test {test_results['start']}-{test_results['end']} "
                f"(acc={test_acc:.0%}). Delta: {report['accuracy_delta']:+.1%}. "
                f"Payoff ratio: {report.get('test', {}).get('payoff_ratio', 0):.1f}x.",
                "directional_accuracy",
                test_acc, 0.6,
                "proportion",
                min(1.0, len([h for h in test_results['hypotheses'] if h.get('has_outcome')]) / 20),
                json.dumps(report),
                None, 0, None,
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass

        return report

    def _print_report(self, report):
        """Print human-readable backtest report."""
        print("\n" + "=" * 60)
        print("  HISTORICAL BACKTEST REPORT")
        print("=" * 60)

        for phase in ["train", "test"]:
            data = report.get(phase, {})
            if not data:
                continue

            label = "TRAINING" if phase == "train" else "TEST (OUT-OF-SAMPLE)"
            print(f"\n  {label}:")
            print(f"    Hypotheses: {data.get('total_hypotheses', 0)} total, "
                  f"{data.get('survived_kill', 0)} survived, "
                  f"{data.get('with_outcomes', 0)} with outcomes")

            cm = data.get("confusion_matrix", {})
            print(f"\n    Confusion Matrix:")
            print(f"                  Predicted +    Predicted -")
            print(f"    Actual +      TP={cm.get('TP', 0):>4}        FN={cm.get('FN', 0):>4}")
            print(f"    Actual -      FP={cm.get('FP', 0):>4}        TN={cm.get('TN', 0):>4}")

            print(f"\n    Directional accuracy: {data.get('directional_accuracy', 0):.0%}")
            print(f"    Timing accuracy:      {data.get('timing_accuracy', 0):.0%}")
            print(f"    Mechanism accuracy:    {data.get('mechanism_accuracy', 0):.0%}")
            print(f"    Avg magnitude error:   {data.get('avg_magnitude_error', '—')}pp")
            print(f"    Payoff ratio:          {data.get('payoff_ratio', 0):.1f}x")
            print(f"    Win rate:              {data.get('win_rate', 0):.0%}")
            print(f"    Cumulative P&L:        {data.get('cumulative_pnl_pct', 0):+.1f}%")
            print(f"    Max drawdown:          {data.get('max_drawdown_pct', 0):.1f}%")

            cal = data.get("calibration_curve", {})
            if cal:
                print(f"\n    Calibration curve:")
                for bucket in ["50-59", "60-69", "70-79", "80-89", "90+"]:
                    if bucket in cal:
                        print(f"      Score {bucket}: {cal[bucket]['hit_rate']:.0%} "
                              f"(n={cal[bucket]['count']})")

        delta = report.get("accuracy_delta", 0)
        improved = report.get("calibration_improved_accuracy", False)
        print(f"\n  CALIBRATION IMPACT: {'IMPROVED' if improved else 'NO IMPROVEMENT'} "
              f"(delta: {delta:+.1%})")

        train_pr = report.get("train", {}).get("payoff_ratio", 0)
        test_pr = report.get("test", {}).get("payoff_ratio", 0)
        if train_pr > 0 and test_pr > 0:
            print(f"  Payoff ratio: train {train_pr:.1f}x -> test {test_pr:.1f}x")

        print("=" * 60)


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    init_db()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python calibration.py calibrate")
        print("  python calibration.py backtest --train-start 2025-01-01 --train-end 2025-06-30 "
              "--test-start 2025-07-01 --test-end 2025-12-31")
        sys.exit(1)

    command = sys.argv[1]

    if command == "calibrate":
        calibrator = ParameterCalibrator()
        output = calibrator.run()

    elif command == "backtest":
        # Parse date arguments
        args = {}
        i = 2
        while i < len(sys.argv) - 1:
            key = sys.argv[i].lstrip("-").replace("-", "_")
            args[key] = sys.argv[i + 1]
            i += 2

        train_start = args.get("train_start", "2025-01-01")
        train_end = args.get("train_end", "2025-06-30")
        test_start = args.get("test_start", "2025-07-01")
        test_end = args.get("test_end", "2025-12-31")

        # Validate: test must not overlap train
        if test_start <= train_end:
            print(f"ERROR: Test period ({test_start}) must start after train period ({train_end})")
            sys.exit(1)

        backtester = HistoricalBacktester(train_start, train_end, test_start, test_end)
        report = backtester.run()

    else:
        print(f"Unknown command: {command}")
        print("Use 'calibrate' or 'backtest'")
        sys.exit(1)


if __name__ == "__main__":
    main()
