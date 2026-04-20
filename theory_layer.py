"""Theory Layer Agents — 7 autonomous agents that observe HUNTER's pipeline
and generate evidence for the Epistemic Residual Framework.

These agents NEVER modify trading logic. They observe outputs and record evidence.

Agents:
  1. TheoryTelemetry     — per-collision/hypothesis evidence logging (Haiku)
  2. DecayTracker        — daily check: are hypotheses still uncorrected? (Haiku)
  3. CycleDetector       — weekly: find reinforcement loops in causal graph (Python + Haiku)
  4. CollisionFormulaValidator — weekly: regress formula predictions vs outcomes (Python only)
  5. ChainDepthProfiler  — weekly: fit depth-value decay curve (Python only)
  6. BacktestReconciler  — weekly: reconcile expired hypotheses vs reality (Sonnet)
  7. ResidualEstimator   — monthly: aggregate residual density estimates (Sonnet)

Cost: ~$5-10/month total.
"""

import json
import math
import time
from datetime import datetime, timedelta

from theory import (
    ALL_LAYERS, LAYER_TO_NUM, LAYER_DESCRIPTIONS,
    CHAIN_DECAY_RATE, EXPECTED_PERSISTENCE_RATIO, CYCLE_HIERARCHY,
    DOMAIN_THEORY_PARAMS,
    classify_evidence, compute_collision_formula, compute_depth_value,
    compute_persistence_ratio,
)


# ═══════════════════════════════════════════════════════════════════════
# 1. THEORY TELEMETRY — Per-collision evidence logging
# ═══════════════════════════════════════════════════════════════════════

THEORY_TELEMETRY_SYSTEM = """You are the Theory Telemetry Logger for HUNTER. Your job is
to classify every output from the collision pipeline as evidence for
or against the Epistemic Residual Framework.

CLASSIFICATION RULES:
- Translation loss (Layer 1): Any belief-reality mismatch where the
  same fact appears differently in two domains. The distortion score
  IS the measurement.
- Attention topology (Layer 2): The domain distance score IS the
  attention gap measurement. High distance + collision found =
  attention blind spot confirmed.
- Reinforcement > correction (Layer 8): If a hypothesis SURVIVES
  kill phase, the kill survival = one data point for persistence.
  Record the reinforcement count (how many sources repeated the
  wrong belief) and correction count (how many sources corrected it).
- Chain depth (Layer 7): Record the chain length from chain extension.
  Record the hypothesis value. This builds the depth-value distribution.
- Negative space (Layer 11): The gap type and magnitude from negative
  space detection directly measure Layer 11.
- Structural incompleteness (Layer 10): If a hypothesis survives kill
  AND has been public for >120 days AND the market hasn't corrected
  it, flag as potential structural incompleteness candidate.

IMPORTANT: Be conservative. Only tag "direct" evidence when the
measurement genuinely proves the theoretical claim. Most evidence
will be "supporting." Never fabricate measurements — if you can't
compute a specific number from the data provided, set it to null."""

THEORY_CLASSIFY_PROMPT = """Classify this collision against the Epistemic Residual Framework.

COLLISION:
{collision_description}

BROKEN MODEL: {broken_model}
STALE ASSUMPTION: {stale_assumption}
SILO REASON: {silo_reason}

SOURCE TYPES: {source_types}
DOMAIN DISTANCE: {domain_distance}
CHAIN DEPTH: {chain_depth}

NEGATIVE SPACE: {negative_space}

HYPOTHESIS (if formed): {hypothesis_summary}

Produce a JSON classification. For each applicable layer (1-13), provide evidence:

LAYERS:
1-Translation Loss: Info degrades crossing domain boundaries
2-Attention Topology: Non-uniform analyst coverage creates blind spots
3-Question Gap: Gap between questions asked vs questions that exist
4-Phase Transition: Residual accumulation predicts sudden corrections
5-Rate-Distortion: Mathematical floor on information compression
6-Market Incompleteness: Cross-domain implications with no trading instrument
7-Depth-Value: Deeper chain errors worth more per unit
8-Epistemic Cycles: Self-reinforcing error loops (207x persistence)
9-Cycle Hierarchy: 9 cycle types by persistence
10-Fractal Incompleteness: Structurally unreachable by market correction
11-Negative Space: Shape of non-reaction reveals blind spots
12-Autopoiesis: Finding residual where predicted IS evidence
13-Observer-Dependent: Correction changes remaining topology

Respond with ONLY a JSON object:
{{
    "theory_evidence": [
        {{
            "layer": <1-13>,
            "layer_name": "<name>",
            "evidence_type": "direct" | "supporting" | "challenging",
            "description": "<what specifically this proves/supports/challenges>",
            "measurement": {{
                "metric": "<what you measured>",
                "observed_value": <number or null>,
                "predicted_value": <number or null>,
                "unit": "<unit of measurement>"
            }},
            "confidence": <0.0-1.0>,
            "domain_pair": {domain_pair_json},
            "source_types": {source_types_json},
            "chain_depth": {chain_depth},
            "cycle_detected": false,
            "cycle_type": null
        }}
    ]
}}

Only include layers where you have SPECIFIC evidence. Most collisions evidence 3-6 layers. Do not force-fit."""


class TheoryTelemetry:
    """Logs per-collision and per-hypothesis theory evidence.
    Uses Haiku for classification (~500 tokens per call = ~$0.0004)."""

    def log_collision(self, collision_data, domain_pair, source_types,
                      negative_space_data=None, chains=None,
                      belief_reality_matches=None, validated_pairs=None):
        """Called after collision evaluation succeeds. Classifies against 13 layers."""
        try:
            from database import get_connection

            # Step 1: Local classification (free, fast)
            domain_distance = 0.0
            try:
                from config import compute_avg_domain_distance
                st_list = list(source_types) if source_types else []
                if len(st_list) >= 2:
                    domain_distance = compute_avg_domain_distance(st_list)
            except Exception:
                pass

            local_evidence = classify_evidence(
                collision_data=collision_data,
                source_types=source_types,
                domain_distance=domain_distance,
                chains=chains,
                belief_reality_matches=belief_reality_matches,
                validated_pairs=validated_pairs,
                negative_space_data=negative_space_data,
            )

            # Step 2: LLM classification for nuance (Haiku, cheap)
            llm_evidence = []
            try:
                from hunter import call_text, extract_text_from_response, parse_json_response
                from config import MODEL_FAST

                chain_depth = 0
                if chains:
                    chain_depth = max(c.get("length", 0) for c in chains)

                st_list_prompt = list(source_types)[:5] if source_types else []
                domain_pair_json_prompt = json.dumps(st_list_prompt[:2])
                source_types_json_prompt = json.dumps(st_list_prompt)

                # Negative space summary
                ns_summary = "None"
                if negative_space_data:
                    ns_summary = f"gap_type={negative_space_data.get('gap_magnitude', 'unknown')}, reacted={negative_space_data.get('reaction_occurred', 'unknown')}"

                # Hypothesis summary (if available from collision data)
                hyp_summary = "Not yet formed"

                prompt = THEORY_CLASSIFY_PROMPT.format(
                    collision_description=collision_data.get("collision_description", "")[:300],
                    broken_model=collision_data.get("broken_model", "None")[:200],
                    stale_assumption=collision_data.get("stale_assumption", "None")[:200],
                    silo_reason=collision_data.get("silo_reason", "None")[:200],
                    source_types=", ".join(st_list_prompt) if st_list_prompt else "unknown",
                    domain_distance=f"{domain_distance:.2f}",
                    chain_depth=chain_depth,
                    negative_space=ns_summary,
                    hypothesis_summary=hyp_summary,
                    domain_pair_json=domain_pair_json_prompt,
                    source_types_json=source_types_json_prompt,
                )
                response = call_text(
                    prompt,
                    system=THEORY_TELEMETRY_SYSTEM,
                    max_tokens=768,
                    temperature=0.2,
                    model=MODEL_FAST,
                )
                text = extract_text_from_response(response)
                data = parse_json_response(text)
                llm_evidence = data.get("theory_evidence", data.get("layers", []))
            except Exception:
                pass  # LLM classification is best-effort

            # Step 3: Merge local + LLM evidence and write to DB
            conn = get_connection()
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            collision_id = collision_data.get("collision_id")
            st_list = list(source_types)[:2] if source_types else []
            domain_pair_json = json.dumps(st_list)

            # Write local evidence
            for ev in local_evidence:
                layer_num = LAYER_TO_NUM.get(ev.get("theory_layer", ""), 0)
                if layer_num == 0:
                    continue
                is_cycle = 1 if layer_num in (8, 9) else 0
                cursor.execute("""
                    INSERT INTO theory_evidence
                    (timestamp, source_event, source_id, layer, layer_name,
                     evidence_type, description, metric, observed_value,
                     predicted_value, unit, confidence, domain_pair,
                     chain_depth, cycle_detected, cycle_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now, "collision", collision_id, layer_num,
                    ev.get("theory_layer", ""),
                    ev.get("evidence_type", "supporting"),
                    ev.get("description", "")[:500],
                    ev.get("theory_layer", ""),
                    ev.get("measurement_value"),
                    ev.get("predicted_value"),
                    None,
                    ev.get("confidence", 0),
                    domain_pair_json,
                    max(c.get("length", 0) for c in chains) if chains else None,
                    is_cycle, None,
                ))

            # Write LLM evidence (only layers not already covered by local)
            local_layers = {ev.get("theory_layer") for ev in local_evidence}
            local_layer_nums = {LAYER_TO_NUM.get(l, 0) for l in local_layers}
            for ev in llm_evidence:
                layer_num = ev.get("layer", 0)
                if layer_num < 1 or layer_num > 13:
                    continue
                if layer_num in local_layer_nums:
                    continue  # Don't duplicate
                layer_name = ev.get("layer_name")
                if not layer_name:
                    _matches = [k for k, v in LAYER_TO_NUM.items() if v == layer_num]
                    layer_name = _matches[0] if _matches else f"L{layer_num:02d}"
                is_cycle = 1 if layer_num in (8, 9) else 0

                # Handle nested measurement schema from Prompt 3.1
                measurement = ev.get("measurement", {})
                if isinstance(measurement, dict):
                    metric = measurement.get("metric", "")
                    observed = measurement.get("observed_value")
                    predicted = measurement.get("predicted_value")
                    unit = measurement.get("unit")
                else:
                    # Fallback: flat schema
                    metric = ev.get("metric", "")
                    observed = ev.get("observed_value")
                    predicted = ev.get("predicted_value")
                    unit = None

                cursor.execute("""
                    INSERT INTO theory_evidence
                    (timestamp, source_event, source_id, layer, layer_name,
                     evidence_type, description, metric, observed_value,
                     predicted_value, unit, confidence, domain_pair,
                     chain_depth, cycle_detected, cycle_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now, "collision", collision_id, layer_num, layer_name,
                    ev.get("evidence_type", "supporting"),
                    ev.get("description", "")[:500],
                    metric,
                    observed,
                    predicted,
                    unit,
                    ev.get("confidence", 0),
                    json.dumps(ev.get("domain_pair", st_list[:2])),
                    ev.get("chain_depth") or (max(c.get("length", 0) for c in chains) if chains else None),
                    ev.get("cycle_detected", is_cycle),
                    ev.get("cycle_type"),
                ))

            conn.commit()
            conn.close()

        except Exception:
            pass  # Theory telemetry never breaks the trading pipeline

    def log_hypothesis(self, hypothesis_data, final_score, kill_results,
                       chain_length, domain_pair, source_types=None):
        """Called after hypothesis scoring. Records score vs theory predictions."""
        try:
            from database import get_connection

            conn = get_connection()
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            hyp_id = hypothesis_data.get("hypothesis_id")
            domain_pair_json = json.dumps(list(domain_pair)[:2]) if domain_pair else None

            # Layer 12: Autopoiesis — did we find residual where predicted?
            st_list = list(source_types)[:2] if source_types else list(domain_pair)[:2] if domain_pair else []
            if len(st_list) >= 2:
                formula = compute_collision_formula(st_list[0], st_list[1])
                formula_predicted = formula["total"] > 20
                if formula_predicted and final_score and final_score >= 40:
                    cursor.execute("""
                        INSERT INTO theory_evidence
                        (timestamp, source_event, source_id, layer, layer_name,
                         evidence_type, description, metric, observed_value,
                         predicted_value, unit, confidence, domain_pair,
                         chain_depth, cycle_detected, cycle_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        now, "hypothesis", hyp_id, 12, "L12_autopoiesis",
                        "direct",
                        f"Hypothesis scored {final_score} where formula predicted "
                        f"residual ({formula['total']:.1f} > 20). Loop confirmed.",
                        "diamond_score_vs_formula",
                        final_score, formula["total"],
                        "score", 0.6,
                        domain_pair_json, chain_length, 0, None,
                    ))

            # Layer 7: Depth-value — chain depth vs score
            if chain_length and chain_length >= 2 and final_score:
                predicted_value = compute_depth_value(chain_length)
                cursor.execute("""
                    INSERT INTO theory_evidence
                    (timestamp, source_event, source_id, layer, layer_name,
                     evidence_type, description, metric, observed_value,
                     predicted_value, unit, confidence, domain_pair,
                     chain_depth, cycle_detected, cycle_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now, "hypothesis", hyp_id, 7, "L07_depth_value",
                    "direct" if chain_length >= 3 else "supporting",
                    f"Chain depth {chain_length}, score {final_score}. "
                    f"Predicted value: ${predicted_value:.4f}T.",
                    "chain_depth_vs_score",
                    final_score, predicted_value,
                    "score_vs_$T", min(1.0, chain_length * 0.2),
                    domain_pair_json, chain_length, 0, None,
                ))

            # Record kill results as Layer 3 evidence (question gap — what wasn't checked)
            killed = False
            if kill_results:
                for kr in kill_results:
                    if kr.get("killed"):
                        killed = True
                        break
            if not killed and final_score and final_score >= 65:
                cursor.execute("""
                    INSERT INTO theory_evidence
                    (timestamp, source_event, source_id, layer, layer_name,
                     evidence_type, description, metric, observed_value,
                     predicted_value, unit, confidence, domain_pair,
                     chain_depth, cycle_detected, cycle_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now, "hypothesis", hyp_id, 3, "L03_question_gap",
                    "supporting",
                    f"Hypothesis survived {len(kill_results)} kill attempts with score {final_score}. "
                    f"Kill attempts could not find this connection — confirms question gap.",
                    "kill_survival_rate",
                    final_score, None,
                    "score", 0.5,
                    domain_pair_json, chain_length, 0, None,
                ))

            conn.commit()
            conn.close()

        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════
# 2. DECAY TRACKER — Daily: are hypotheses still uncorrected?
# ═══════════════════════════════════════════════════════════════════════

DECAY_TRACKER_SYSTEM = """You are the Decay Rate Tracker for HUNTER. Your job is to
measure how long epistemic errors persist before the market corrects
them. This directly tests the theory's predicted 120-day half-life
and 207x persistence ratio.

Check:
1. Has the asset price moved in the predicted direction?
2. How much has it moved (percentage)?
3. Are there new sources reinforcing or contradicting the thesis?
   Count reinforcing sources (repeating the error) and correcting sources
   (contradicting the thesis) separately.

Be factual. Only report what you can verify from search results."""


class DecayTracker:
    """Daily check: for each active hypothesis, has the market corrected yet?
    Fits exponential decay to build survival curve and test 120-day half-life.
    Uses Haiku for web search assessment (~5,000 tokens/day)."""

    def run(self):
        """Check all active hypotheses for market correction, then compute survival curve."""
        try:
            from database import get_connection
            from hunter import call_with_web_search, extract_text_from_response, parse_json_response

            conn = get_connection()
            cursor = conn.cursor()

            # Get hypotheses that survived kill (look back further for decay curve)
            cursor.execute("""
                SELECT id, hypothesis_text, diamond_score, time_window_days,
                       created_at, action_steps
                FROM hypotheses
                WHERE survived_kill = 1
                AND diamond_score >= 50
                AND created_at >= datetime('now', '-365 days')
                ORDER BY diamond_score DESC
                LIMIT 30
            """)
            hypotheses = [dict(row) for row in cursor.fetchall()]

            if not hypotheses:
                conn.close()
                return

            now = datetime.now()
            checked = 0

            for hyp in hypotheses:
                try:
                    # Check if already checked today
                    cursor.execute("""
                        SELECT check_date FROM decay_tracking
                        WHERE hypothesis_id = ?
                        ORDER BY check_date DESC LIMIT 1
                    """, (hyp["id"],))
                    last_check = cursor.fetchone()
                    if last_check and last_check[0]:
                        try:
                            last_dt = datetime.fromisoformat(last_check[0])
                            if (now - last_dt).total_seconds() < 20 * 3600:
                                continue  # Checked within 20 hours
                        except (ValueError, TypeError):
                            pass

                    # Web search to check market status
                    response = call_with_web_search(
                        f"""Has the market corrected for this hypothesis? Check current status.

HYPOTHESIS (formed {hyp['created_at'][:10]}):
{hyp['hypothesis_text'][:500]}

Respond with ONLY JSON:
{{
    "still_uncorrected": true/false,
    "market_moved_direction": "predicted|opposite|sideways",
    "market_moved_magnitude_pct": <number>,
    "sources_reinforcing": <count of sources repeating the error/supporting thesis>,
    "sources_correcting": <count of sources contradicting/correcting the thesis>,
    "summary": "brief status"
}}""",
                        system=DECAY_TRACKER_SYSTEM,
                        max_tokens=512,
                    )
                    text = extract_text_from_response(response)
                    data = parse_json_response(text)

                    cursor.execute("""
                        INSERT INTO decay_tracking
                        (hypothesis_id, formation_date, check_date, still_uncorrected,
                         market_moved_direction, market_moved_magnitude,
                         sources_reinforcing, sources_correcting)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        hyp["id"],
                        hyp["created_at"][:10],
                        now.isoformat(),
                        1 if data.get("still_uncorrected", True) else 0,
                        data.get("market_moved_direction", "unknown"),
                        data.get("market_moved_magnitude_pct", 0),
                        data.get("sources_reinforcing", 0),
                        data.get("sources_correcting", 0),
                    ))

                    # Layer 8 evidence: if still uncorrected, reinforcement > correction
                    if data.get("still_uncorrected") and data.get("sources_reinforcing", 0) > 0:
                        reinf = data.get("sources_reinforcing", 0)
                        corr = data.get("sources_correcting", 0)
                        ratio = reinf / max(1, corr)
                        days_alive = (now - datetime.fromisoformat(hyp['created_at'])).days
                        cursor.execute("""
                            INSERT INTO theory_evidence
                            (timestamp, source_event, source_id, layer, layer_name,
                             evidence_type, description, metric, observed_value,
                             predicted_value, unit, confidence, domain_pair,
                             chain_depth, cycle_detected, cycle_type)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            now.isoformat(), "decay_check", hyp["id"],
                            8, "L08_epistemic_cycles",
                            "direct" if ratio > 3 else "supporting",
                            f"Hypothesis {hyp['id']} still uncorrected after "
                            f"{days_alive}d. "
                            f"Reinforcing sources: {reinf}, correcting: {corr}. "
                            f"Ratio: {ratio:.1f}x (predicted: {EXPECTED_PERSISTENCE_RATIO}x).",
                            "reinforcement_correction_ratio",
                            ratio, EXPECTED_PERSISTENCE_RATIO,
                            "ratio", min(1.0, ratio / 50),
                            None, None, 1 if ratio > 3 else 0, None,
                        ))

                    # Layer 10 evidence: structural incompleteness if uncorrected >120 days
                    if data.get("still_uncorrected"):
                        days_alive = (now - datetime.fromisoformat(hyp['created_at'])).days
                        if days_alive > 120:
                            cursor.execute("""
                                INSERT INTO theory_evidence
                                (timestamp, source_event, source_id, layer, layer_name,
                                 evidence_type, description, metric, observed_value,
                                 predicted_value, unit, confidence, domain_pair,
                                 chain_depth, cycle_detected, cycle_type)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                now.isoformat(), "decay_check", hyp["id"],
                                10, "L10_fractal_incompleteness",
                                "supporting",
                                f"Hypothesis {hyp['id']} still uncorrected after "
                                f"{days_alive}d (>120d threshold). Score {hyp['diamond_score']}. "
                                f"Potential structural incompleteness — market may be "
                                f"structurally unable to correct this.",
                                "days_uncorrected",
                                days_alive, 120,
                                "days", min(1.0, days_alive / 365),
                                None, None, 0, None,
                            ))

                    checked += 1
                    if checked >= 10:
                        break  # Cost control: max 10 checks per run

                except Exception:
                    continue

            # ── SURVIVAL CURVE COMPUTATION ──
            # Build survival curve from ALL historical decay_tracking data
            try:
                self._compute_survival_curve(cursor, now)
            except Exception:
                pass

            conn.commit()
            conn.close()

        except Exception:
            pass

    def _compute_survival_curve(self, cursor, now):
        """Compute survival curve, fit exponential decay, compare to theory predictions."""
        # Get all hypotheses with their latest decay check
        cursor.execute("""
            SELECT h.id, h.created_at, h.diamond_score,
                   dt.still_uncorrected, dt.check_date,
                   dt.sources_reinforcing, dt.sources_correcting
            FROM hypotheses h
            JOIN decay_tracking dt ON h.id = dt.hypothesis_id
            WHERE h.survived_kill = 1
            AND h.diamond_score >= 50
            AND dt.check_date = (
                SELECT MAX(dt2.check_date) FROM decay_tracking dt2
                WHERE dt2.hypothesis_id = h.id
            )
        """)
        rows = cursor.fetchall()
        if not rows:
            return

        total_tracked = len(rows)
        resolved = 0
        unresolved = 0
        correction_times = []  # days to correction for resolved hypotheses
        total_reinforcing = 0
        total_correcting = 0

        for row in rows:
            hyp_id, created_at, score, still_uncorrected, check_date, reinf, corr = row
            total_reinforcing += (reinf or 0)
            total_correcting += (corr or 0)

            if still_uncorrected:
                unresolved += 1
            else:
                resolved += 1
                # Compute time to correction
                try:
                    created = datetime.fromisoformat(created_at)
                    checked = datetime.fromisoformat(check_date)
                    days_to_corr = (checked - created).days
                    correction_times.append(max(1, days_to_corr))
                except (ValueError, TypeError):
                    pass

        # Build survival curve at standard checkpoints
        checkpoints = [30, 60, 90, 120, 180, 365]
        survival_curve = {}
        for day in checkpoints:
            # Proportion still surviving at this day
            # Count hypotheses that were still uncorrected at this age
            surviving = 0
            total_at_risk = 0
            for row in rows:
                hyp_id, created_at, score, still_uncorrected, check_date, _, _ = row
                try:
                    created = datetime.fromisoformat(created_at)
                    age_days = (now - created).days
                    if age_days >= day:
                        total_at_risk += 1
                        if still_uncorrected:
                            surviving += 1
                        elif correction_times:
                            # Check if it was corrected AFTER this checkpoint
                            checked = datetime.fromisoformat(check_date)
                            corr_days = (checked - created).days
                            if corr_days > day:
                                surviving += 1
                except (ValueError, TypeError):
                    pass
            survival_curve[f"{day}_days"] = round(surviving / max(1, total_at_risk), 3)

        # Fit exponential decay: P(survival) = e^(-lambda * t)
        # Use MLE: lambda = n_events / sum(observed_times)
        fitted_half_life = None
        half_life_delta = None
        if correction_times:
            # lambda = number of corrections / total time observed
            total_time = sum(correction_times)
            n_events = len(correction_times)
            lambda_hat = n_events / max(1, total_time)
            fitted_half_life = round(math.log(2) / max(0.0001, lambda_hat), 1)
            half_life_delta = round(fitted_half_life - 120, 1)

        # Empirical persistence ratio
        empirical_ratio = round(total_reinforcing / max(1, total_correcting), 1)
        persistence_delta = round(empirical_ratio - EXPECTED_PERSISTENCE_RATIO, 1)

        # Confidence based on sample size
        confidence = min(1.0, round(total_tracked / 50, 2))
        sample_adequate = total_tracked >= 30

        # Write summary as theory evidence (Layer 8: epistemic cycles)
        summary = {
            "date": now.strftime("%Y-%m-%d"),
            "total_hypotheses_tracked": total_tracked,
            "resolved": resolved,
            "unresolved": unresolved,
            "survival_curve": survival_curve,
            "fitted_half_life_days": fitted_half_life,
            "predicted_half_life_days": 120,
            "half_life_delta": half_life_delta,
            "empirical_persistence_ratio": empirical_ratio,
            "predicted_persistence_ratio": EXPECTED_PERSISTENCE_RATIO,
            "persistence_delta": persistence_delta,
            "confidence": confidence,
            "sample_size_adequate": sample_adequate,
        }

        # Record survival curve as Layer 8 evidence
        ev_type = "direct" if sample_adequate else "supporting"
        description = (
            f"Decay tracker summary: {total_tracked} hypotheses tracked, "
            f"{resolved} resolved, {unresolved} unresolved. "
        )
        if fitted_half_life is not None:
            description += f"Fitted half-life: {fitted_half_life}d (predicted: 120d, delta: {half_life_delta}d). "
        description += (
            f"Persistence ratio: {empirical_ratio}x (predicted: {EXPECTED_PERSISTENCE_RATIO}x, "
            f"delta: {persistence_delta}x). "
            f"Survival at 120d: {survival_curve.get('120_days', 'N/A')}."
        )

        cursor.execute("""
            INSERT INTO theory_evidence
            (timestamp, source_event, source_id, layer, layer_name,
             evidence_type, description, metric, observed_value,
             predicted_value, unit, confidence, domain_pair,
             chain_depth, cycle_detected, cycle_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now.isoformat(), "decay_curve_fit", None,
            8, "L08_epistemic_cycles",
            ev_type,
            description[:500],
            "fitted_half_life_days",
            fitted_half_life, 120,
            "days", confidence,
            json.dumps(summary),  # Full summary in domain_pair field for retrieval
            None, 0, None,
        ))


# ═══════════════════════════════════════════════════════════════════════
# 3. CYCLE DETECTOR — Weekly: find reinforcement loops in causal graph
# ═══════════════════════════════════════════════════════════════════════

CYCLE_TYPES = [
    "simple", "nested", "coupled", "braided", "hierarchical",
    "temporal", "cross_domain", "interference", "dormant",
]


class CycleDetector:
    """Find reinforcement loops in the causal graph using DFS.
    Classifies 9 cycle types per Prompt 3.3. Pure Python cycle detection +
    structural classification."""

    def run(self):
        """Detect cycles in causal_edges graph, classify by 9 types, compute metrics."""
        try:
            from database import get_connection
            import hashlib

            conn = get_connection()
            cursor = conn.cursor()

            # Build adjacency list from causal_edges (wider window for dormant detection)
            cursor.execute("""
                SELECT ce.id, ce.cause_node_lower, ce.effect_node_lower,
                       ce.source_type, ce.relationship_type, ce.confidence,
                       ce.strength, ce.created_at
                FROM causal_edges ce
                WHERE ce.created_at >= datetime('now', '-180 days')
            """)
            raw_edges = cursor.fetchall()
            if not raw_edges:
                conn.close()
                return

            # Build directed graph with full edge metadata
            graph = {}       # node → [edge_data]
            node_domains = {}  # node → set of source_types
            edge_dates = {}    # (cause, effect) → [datetime]
            all_relationships = {}  # (cause, effect) → [relationship_type]

            for row in raw_edges:
                eid, cause, effect, src_type, rel, conf, strength, created_at = row
                if cause not in graph:
                    graph[cause] = []
                edge_data = {
                    "target": effect,
                    "source_type": src_type or "unknown",
                    "relationship": rel or "causes",
                    "confidence": conf or 0.5,
                    "strength": strength or "moderate",
                    "created_at": created_at,
                }
                graph[cause].append(edge_data)
                for node in (cause, effect):
                    if node not in node_domains:
                        node_domains[node] = set()
                    node_domains[node].add(src_type or "unknown")

                pair = (cause, effect)
                if pair not in edge_dates:
                    edge_dates[pair] = []
                try:
                    edge_dates[pair].append(datetime.fromisoformat(created_at))
                except (ValueError, TypeError):
                    pass
                if pair not in all_relationships:
                    all_relationships[pair] = []
                all_relationships[pair].append(rel or "causes")

            # ── DFS CYCLE DETECTION (length 2-6) ──
            cycles_found = []

            def _dfs(start, node, path, path_edges, visited_in_path):
                if len(path) > 6:
                    return
                for edge_data in graph.get(node, []):
                    target = edge_data["target"]
                    if target == start and len(path) >= 2:
                        # Found cycle back to start
                        cycles_found.append({
                            "nodes": list(path),
                            "edges": list(path_edges) + [edge_data],
                        })
                    elif target not in visited_in_path and len(path) < 6:
                        visited_in_path.add(target)
                        _dfs(start, target, path + [target],
                             path_edges + [edge_data], visited_in_path)
                        visited_in_path.discard(target)

            # Start DFS from high-degree nodes (more likely in cycles)
            nodes_by_degree = sorted(graph.keys(),
                                     key=lambda n: len(graph.get(n, [])), reverse=True)
            for start_node in nodes_by_degree[:150]:
                _dfs(start_node, start_node, [start_node], [],
                     {start_node})
                if len(cycles_found) >= 200:
                    break  # Safety cap

            if not cycles_found:
                conn.close()
                return

            # ── DEDUPLICATE ──
            unique_cycles = []
            seen_sets = set()
            for c in cycles_found:
                # Canonical form: sorted frozenset of nodes
                key = frozenset(c["nodes"])
                if key not in seen_sets:
                    seen_sets.add(key)
                    unique_cycles.append(c)

            # ── CLASSIFY EACH CYCLE ──
            now = datetime.now()
            type_counts = {t: 0 for t in CYCLE_TYPES}
            classified_cycles = []

            for cycle in unique_cycles[:20]:  # Cap at 20 per run
                nodes = cycle["nodes"]
                edge_list = cycle["edges"]
                cycle_len = len(nodes)

                # Collect domains
                domains = set()
                for node in nodes:
                    domains.update(node_domains.get(node, set()))
                num_domains = len(domains)

                # Collect edge dates for age computation
                all_dates = []
                for i in range(len(nodes)):
                    src = nodes[i]
                    tgt = nodes[(i + 1) % len(nodes)]
                    all_dates.extend(edge_dates.get((src, tgt), []))

                age_days = 0
                last_reinforced_days = 0
                if all_dates:
                    oldest = min(all_dates)
                    newest = max(all_dates)
                    age_days = (now - oldest).days
                    last_reinforced_days = (now - newest).days

                # Collect relationships for direction analysis
                increases = set()
                decreases = set()
                for e in edge_list:
                    rel = e.get("relationship", "causes")
                    if rel in ("increases", "causes", "enables", "accelerates"):
                        increases.add((e.get("target", "")))
                    elif rel in ("decreases", "prevents"):
                        decreases.add((e.get("target", "")))

                # ── 9-TYPE CLASSIFICATION ──
                cycle_type = self._classify_cycle(
                    nodes, edge_list, domains, num_domains, cycle_len,
                    increases, decreases, age_days, last_reinforced_days,
                    all_dates, unique_cycles, node_domains=node_domains,
                )
                type_counts[cycle_type] = type_counts.get(cycle_type, 0) + 1

                # ── METRICS ──
                confidences = [e.get("confidence", 0.5) for e in edge_list]
                reinf_strength = sum(confidences) / max(1, len(confidences))

                # Correction pressure: count contradicting facts touching cycle nodes
                # (edges with opposing relationship on same node pair)
                contradiction_count = 0
                total_edges_touching = 0
                for i in range(len(nodes)):
                    src = nodes[i]
                    tgt = nodes[(i + 1) % len(nodes)]
                    rels = all_relationships.get((src, tgt), [])
                    total_edges_touching += len(rels)
                    # Also check reverse direction
                    rev_rels = all_relationships.get((tgt, src), [])
                    contradiction_count += len(rev_rels)
                    # Check for opposing relationships on same pair
                    has_pos = any(r in ("increases", "causes", "enables", "accelerates") for r in rels)
                    has_neg = any(r in ("decreases", "prevents") for r in rels)
                    if has_pos and has_neg:
                        contradiction_count += 1

                corr_pressure = contradiction_count / max(1, total_edges_touching + contradiction_count)
                persistence = reinf_strength / max(0.01, corr_pressure)

                # Build cycle hash for stable ID
                cycle_hash = hashlib.md5(
                    json.dumps(sorted(nodes)).encode()
                ).hexdigest()[:12]

                # Build edge representation for output
                edge_repr = []
                for i in range(len(nodes)):
                    src = nodes[i]
                    tgt = nodes[(i + 1) % len(nodes)] if i + 1 < len(nodes) else nodes[0]
                    rel = edge_list[i].get("relationship", "causes") if i < len(edge_list) else "causes"
                    edge_repr.append({"from": src, "to": tgt, "rel": rel})

                classified_cycles.append({
                    "id": cycle_hash,
                    "type": cycle_type,
                    "nodes": nodes,
                    "edges": edge_repr,
                    "domains": list(domains),
                    "reinforcement_strength": round(reinf_strength, 3),
                    "correction_pressure": round(corr_pressure, 3),
                    "persistence_estimate": round(persistence, 2),
                    "age_days": age_days,
                    "last_reinforced_days": last_reinforced_days,
                    "theory_prediction": f"Cycles persist at {EXPECTED_PERSISTENCE_RATIO}x correction rate",
                    "observed_ratio": round(persistence, 2),
                })

                # Save to detected_cycles table
                is_active = 0 if cycle_type == "dormant" else 1
                cursor.execute("""
                    INSERT INTO detected_cycles
                    (detected_date, cycle_type, nodes, edges, domains,
                     reinforcement_strength, correction_pressure,
                     persistence_estimate, age_days, last_reinforced_days, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now.isoformat(), cycle_type,
                    json.dumps(nodes), json.dumps(edge_repr),
                    json.dumps(list(domains)),
                    round(reinf_strength, 3), round(corr_pressure, 3),
                    round(persistence, 2),
                    age_days, last_reinforced_days, is_active,
                ))

                # Layer 9 evidence: cycle hierarchy
                cycle_rank = CYCLE_HIERARCHY.get(cycle_type, 1)
                ev_type = "direct" if num_domains >= 2 or cycle_type in ("interference", "cross_domain") else "supporting"
                cursor.execute("""
                    INSERT INTO theory_evidence
                    (timestamp, source_event, source_id, layer, layer_name,
                     evidence_type, description, metric, observed_value,
                     predicted_value, unit, confidence, domain_pair,
                     chain_depth, cycle_detected, cycle_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now.isoformat(), "cycle_detection", cycle_hash,
                    9, "L09_cycle_hierarchy",
                    ev_type,
                    f"{cycle_type} cycle (rank {cycle_rank}): {cycle_len} nodes, "
                    f"{num_domains} domains. Persistence {persistence:.1f}x "
                    f"(predicted: {EXPECTED_PERSISTENCE_RATIO}x). "
                    f"Age: {age_days}d, last reinforced: {last_reinforced_days}d ago. "
                    f"Nodes: {', '.join(nodes[:4])}{'...' if len(nodes) > 4 else ''}.",
                    "cycle_persistence",
                    persistence, EXPECTED_PERSISTENCE_RATIO,
                    "ratio", min(1.0, persistence / 20),
                    json.dumps(list(domains)[:2]),
                    cycle_len, 1, cycle_type,
                ))

            # Write summary as Layer 9 evidence
            summary = {
                "cycles_found": len(classified_cycles),
                "by_type": type_counts,
                "cycles": classified_cycles,
            }
            cursor.execute("""
                INSERT INTO theory_evidence
                (timestamp, source_event, source_id, layer, layer_name,
                 evidence_type, description, metric, observed_value,
                 predicted_value, unit, confidence, domain_pair,
                 chain_depth, cycle_detected, cycle_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now.isoformat(), "cycle_detection_summary", None,
                9, "L09_cycle_hierarchy",
                "supporting",
                f"Cycle detection run: {len(classified_cycles)} unique cycles found. "
                f"Types: {', '.join(f'{t}={c}' for t, c in type_counts.items() if c > 0)}.",
                "cycles_found",
                len(classified_cycles), None,
                "count", min(1.0, len(classified_cycles) / 10),
                json.dumps(summary),
                None, 1, None,
            ))

            conn.commit()
            conn.close()

        except Exception:
            pass

    def _classify_cycle(self, nodes, edge_list, domains, num_domains,
                        cycle_len, increases, decreases, age_days,
                        last_reinforced_days, all_dates, all_cycles,
                        node_domains=None):
        """Classify a cycle into one of 9 types per Prompt 3.3."""
        node_set = frozenset(nodes)

        # DORMANT: all edges older than 90 days with no recent reinforcement
        if last_reinforced_days > 90:
            return "dormant"

        # INTERFERENCE: two effects on same node from different directions
        # (one increases, other decreases the same target)
        if increases & decreases:
            return "interference"

        # CROSS-DOMAIN: cycle spanning 3+ different source_types
        if num_domains >= 3:
            return "cross_domain"

        # HIERARCHICAL: subcycles at different timescales
        # Check if dates span widely (some edges weeks apart, others months)
        if all_dates and len(all_dates) >= 3:
            sorted_dates = sorted(all_dates)
            gaps = [(sorted_dates[i + 1] - sorted_dates[i]).days
                    for i in range(len(sorted_dates) - 1)]
            if gaps:
                min_gap = min(gaps)
                max_gap = max(gaps)
                if max_gap > 30 and min_gap < 14 and max_gap / max(1, min_gap) > 3:
                    return "hierarchical"

        # NESTED: check if any other cycle shares a proper subset of nodes
        for other in all_cycles:
            other_set = frozenset(other["nodes"])
            if other_set != node_set and other_set < node_set:
                return "nested"

        # COUPLED: check if any other cycle shares exactly one node
        for other in all_cycles:
            other_set = frozenset(other["nodes"])
            if other_set != node_set:
                shared = node_set & other_set
                if len(shared) == 1:
                    return "coupled"

        # BRAIDED: two cycles alternating nodes between two paths
        # Detect by checking if cycle length >= 4 and nodes alternate between
        # two domain groups
        if cycle_len >= 4 and num_domains >= 2:
            domain_sequence = []
            for n in nodes:
                doms = node_domains.get(n, set()) if node_domains else set()
                domain_sequence.append(frozenset(doms))
            # Check alternation pattern
            if len(set(domain_sequence)) >= 2:
                alternating = True
                for i in range(2, len(domain_sequence)):
                    if domain_sequence[i] != domain_sequence[i - 2]:
                        alternating = False
                        break
                if alternating and domain_sequence[0] != domain_sequence[1]:
                    return "braided"

        # TEMPORAL: appeared and disappeared (edges clustered in time)
        if all_dates and len(all_dates) >= 2:
            sorted_dates = sorted(all_dates)
            span = (sorted_dates[-1] - sorted_dates[0]).days
            if span < 14 and age_days > 60:
                return "temporal"

        # SIMPLE: A->B->A (2 nodes) or basic loop
        return "simple"


# ═══════════════════════════════════════════════════════════════════════
# 4. COLLISION FORMULA VALIDATOR — Weekly: Python only, zero AI cost
# ═══════════════════════════════════════════════════════════════════════

class CollisionFormulaValidator:
    """Compute all 300 predicted collision scores and correlate with actual counts.
    Tests: score(A,B) = (A.silos * B.silos * 0.003) + (A.reinf + B.reinf) * 20
           + (1 - A.corr) * (1 - B.corr) * 30 + (A.resid * B.resid) * 400
    Pure Python — no LLM calls needed."""

    # Current formula coefficients
    SILO_COEFF = 0.003
    REINF_WEIGHT = 20.0
    CORR_WEIGHT = 30.0
    RESID_WEIGHT = 400.0

    def run(self):
        """Compute all 300 pairs, correlate with actuals, find mismatches, suggest adjustments."""
        try:
            from database import get_connection

            conn = get_connection()
            cursor = conn.cursor()

            # ── 1. Get actual collision counts by source_type pair ──
            cursor.execute("""
                SELECT source_types, COUNT(*) as cnt
                FROM collisions
                WHERE source_types IS NOT NULL AND source_types != ''
                GROUP BY source_types
            """)
            actual_counts = {}
            for row in cursor.fetchall():
                st = row[0]
                if st:
                    types = frozenset(t.strip() for t in st.split(",") if t.strip())
                    if len(types) >= 2:
                        actual_counts[types] = actual_counts.get(types, 0) + row[1]

            # Also get hypothesis counts and average scores per pair
            cursor.execute("""
                SELECT c.source_types, COUNT(h.id) as hyp_count,
                       AVG(h.diamond_score) as avg_score
                FROM collisions c
                JOIN hypotheses h ON h.collision_id = c.id
                WHERE c.source_types IS NOT NULL AND c.source_types != ''
                GROUP BY c.source_types
            """)
            hyp_data = {}
            for row in cursor.fetchall():
                st = row[0]
                if st:
                    types = frozenset(t.strip() for t in st.split(",") if t.strip())
                    if len(types) >= 2:
                        hyp_data[types] = {"count": row[1], "avg_score": row[2] or 0}

            # ── 2. Compute predicted scores for ALL 300 domain pairs ──
            all_types = list(DOMAIN_THEORY_PARAMS.keys())
            all_pairs = []  # [{pair, predicted, actual, hyp_count, avg_score}]

            for i in range(len(all_types)):
                for j in range(i + 1, len(all_types)):
                    a, b = all_types[i], all_types[j]
                    formula = compute_collision_formula(a, b)
                    pair_key = frozenset([a, b])
                    actual = actual_counts.get(pair_key, 0)
                    hyp = hyp_data.get(pair_key, {"count": 0, "avg_score": 0})

                    all_pairs.append({
                        "pair": f"{a}-{b}",
                        "pair_key": pair_key,
                        "predicted": formula["total"],
                        "actual": actual,
                        "hyp_count": hyp["count"],
                        "avg_score": hyp["avg_score"],
                        "components": formula,
                    })

            pairs_with_data = sum(1 for p in all_pairs if p["actual"] > 0)
            total_pairs = len(all_pairs)

            if pairs_with_data < 3:
                conn.close()
                return  # Not enough data yet

            # ── 3. Pearson correlation (on pairs with data) ──
            pairs_nonzero = [p for p in all_pairs if p["actual"] > 0]
            predicted_vals = [p["predicted"] for p in pairs_nonzero]
            actual_vals = [p["actual"] for p in pairs_nonzero]
            n = len(predicted_vals)

            pearson_r = self._pearson(predicted_vals, actual_vals)

            # ── 4. Spearman rank correlation ──
            spearman_rho = self._spearman(predicted_vals, actual_vals)

            # ── 5. P-value approximation ──
            if abs(pearson_r) < 0.999 and n > 2:
                t_stat = pearson_r * ((n - 2) / max(0.001, 1 - pearson_r ** 2)) ** 0.5
                # Beta-function approximation for two-tailed p-value
                p_value = max(0.001, 2 * math.exp(-0.717 * abs(t_stat) - 0.416 * t_stat ** 2 / max(1, n)))
                p_value = min(1.0, p_value)
            else:
                p_value = 0.001 if n > 2 else 1.0

            validated = pearson_r > 0.3 and p_value < 0.05

            # ── 6. Top 10 matches (smallest residual) ──
            for p in all_pairs:
                if p["actual"] > 0:
                    # Normalize: predicted relative to max predicted, actual relative to max actual
                    max_pred = max(pp["predicted"] for pp in all_pairs) or 1
                    max_act = max(pp["actual"] for pp in all_pairs if pp["actual"] > 0) or 1
                    p["residual"] = abs(p["predicted"] / max_pred - p["actual"] / max_act)
                else:
                    p["residual"] = abs(p["predicted"] / (max(pp["predicted"] for pp in all_pairs) or 1))

            sorted_by_match = sorted(
                [p for p in all_pairs if p["actual"] > 0],
                key=lambda p: p["residual"]
            )
            top_10_matches = [
                {"pair": p["pair"], "predicted": round(p["predicted"], 2), "actual": p["actual"]}
                for p in sorted_by_match[:10]
            ]

            # ── 7. Top 10 mismatches (largest residual) ──
            sorted_by_mismatch = sorted(all_pairs, key=lambda p: p["residual"], reverse=True)
            top_10_mismatches = []
            for p in sorted_by_mismatch[:10]:
                # Hypothesize why the mismatch exists
                hypothesis = self._hypothesize_mismatch(p)
                top_10_mismatches.append({
                    "pair": p["pair"],
                    "predicted": round(p["predicted"], 2),
                    "actual": p["actual"],
                    "hypothesis": hypothesis,
                })

            # ── 8. Suggest coefficient adjustments ──
            # Use gradient of correlation: which component most improves fit?
            suggested = self._suggest_adjustments(pairs_nonzero)

            # ── 9. Build full output ──
            now = datetime.now()
            confidence = min(1.0, round(pairs_with_data / 50, 2))
            summary = {
                "date": now.strftime("%Y-%m-%d"),
                "pairs_analyzed": total_pairs,
                "pairs_with_data": pairs_with_data,
                "pearson_r": round(pearson_r, 4),
                "spearman_rho": round(spearman_rho, 4),
                "p_value": round(p_value, 6),
                "formula_validated": validated,
                "top_10_matches": top_10_matches,
                "top_10_mismatches": top_10_mismatches,
                "suggested_adjustments": suggested,
                "confidence": confidence,
            }

            # Save to formula_validation table
            cursor.execute("""
                INSERT INTO formula_validation
                (date, pearson_r, spearman_rho, p_value, formula_validated,
                 suggested_silo_coeff, suggested_reinf_weight,
                 suggested_corr_weight, suggested_resid_weight)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now.isoformat(),
                round(pearson_r, 4), round(spearman_rho, 4),
                round(p_value, 6), 1 if validated else 0,
                suggested["silo_coefficient"],
                suggested["reinf_weight"],
                suggested["corr_weight"],
                suggested["resid_weight"],
            ))

            # Layer 12 evidence: autopoiesis — formula predicting reality
            ev_type = "direct" if validated else "challenging"
            description = (
                f"Formula validation: Pearson r={pearson_r:.3f}, "
                f"Spearman ρ={spearman_rho:.3f}, p={p_value:.4f}. "
                f"{pairs_with_data}/{total_pairs} pairs have data. "
                f"{'VALIDATED' if validated else 'Not yet validated'}. "
                f"Top mismatch: {top_10_mismatches[0]['pair'] if top_10_mismatches else 'N/A'}."
            )
            cursor.execute("""
                INSERT INTO theory_evidence
                (timestamp, source_event, source_id, layer, layer_name,
                 evidence_type, description, metric, observed_value,
                 predicted_value, unit, confidence, domain_pair,
                 chain_depth, cycle_detected, cycle_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now.isoformat(), "formula_validation", None,
                12, "L12_autopoiesis",
                ev_type,
                description[:500],
                "pearson_r",
                pearson_r, 0.5,  # Theory hopes for r > 0.5
                "pearson_r", confidence,
                json.dumps(summary),  # Full summary for retrieval
                None, 0, None,
            ))

            conn.commit()
            conn.close()

        except Exception:
            pass

    @staticmethod
    def _pearson(x, y):
        """Pure Python Pearson correlation coefficient."""
        n = len(x)
        if n < 2:
            return 0.0
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y)) / n
        std_x = (sum((xi - mean_x) ** 2 for xi in x) / n) ** 0.5
        std_y = (sum((yi - mean_y) ** 2 for yi in y) / n) ** 0.5
        return cov / max(0.001, std_x * std_y)

    @staticmethod
    def _spearman(x, y):
        """Pure Python Spearman rank correlation."""
        n = len(x)
        if n < 2:
            return 0.0

        def _rank(values):
            indexed = sorted(enumerate(values), key=lambda t: t[1])
            ranks = [0.0] * len(values)
            i = 0
            while i < len(indexed):
                # Handle ties with average rank
                j = i
                while j < len(indexed) - 1 and indexed[j + 1][1] == indexed[j][1]:
                    j += 1
                avg_rank = (i + j) / 2.0 + 1
                for k in range(i, j + 1):
                    ranks[indexed[k][0]] = avg_rank
                i = j + 1
            return ranks

        rank_x = _rank(x)
        rank_y = _rank(y)
        d_sq = sum((rx - ry) ** 2 for rx, ry in zip(rank_x, rank_y))
        return 1 - (6 * d_sq) / (n * (n ** 2 - 1))

    def _hypothesize_mismatch(self, pair_data):
        """Generate a hypothesis for why prediction and reality diverge."""
        predicted = pair_data["predicted"]
        actual = pair_data["actual"]
        components = pair_data.get("components", {})
        pair_name = pair_data["pair"]
        types = pair_name.split("-")

        if predicted > 0 and actual == 0:
            # High prediction, no collisions
            # Check if access might be the issue
            access_vals = []
            for t in types:
                params = DOMAIN_THEORY_PARAMS.get(t, {})
                access_vals.append(params.get("access", 5))
            if any(a <= 3 for a in access_vals):
                return f"Data access too low ({min(access_vals)}/10) to generate collisions despite high theoretical score"
            if any(a <= 5 for a in access_vals):
                return f"Moderate data access ({min(access_vals)}/10) limits collision opportunity — may need more ingest cycles"
            return f"High prediction ({predicted:.1f}) but zero collisions — possible domain language mismatch preventing entity resolution"

        elif actual > predicted * 2 and predicted > 0:
            # Actual much higher than predicted
            return f"Actual {actual}x exceeds prediction — formula underweights this pair. Possible: shared entities not captured by formula params"

        elif predicted > actual * 3 and actual > 0:
            # Predicted much higher than actual
            return f"Formula overestimates: predicted {predicted:.1f} vs actual {actual}. Possible: formula params (resid, reinf) inflated for this domain"

        elif actual > 0 and abs(predicted - actual) > 5:
            return f"Moderate mismatch — may indicate non-linear relationship or temporal effects not captured by static formula"

        return "Within expected variance"

    def _suggest_adjustments(self, pairs_with_data):
        """Suggest formula coefficient adjustments using component-level correlation."""
        if len(pairs_with_data) < 5:
            return {
                "silo_coefficient": self.SILO_COEFF,
                "reinf_weight": self.REINF_WEIGHT,
                "corr_weight": self.CORR_WEIGHT,
                "resid_weight": self.RESID_WEIGHT,
            }

        actual_vals = [p["actual"] for p in pairs_with_data]

        # Extract component contributions
        silo_contrib = []
        reinf_contrib = []
        corr_contrib = []
        resid_contrib = []

        for p in pairs_with_data:
            comp = p.get("components", {})
            silo_contrib.append(comp.get("silo_term", 0))
            reinf_contrib.append(comp.get("reinforcement_term", 0))
            corr_contrib.append(comp.get("correction_term", 0))
            resid_contrib.append(comp.get("residual_term", 0))

        # Per-component correlation with actual counts
        r_silo = self._pearson(silo_contrib, actual_vals) if any(s != 0 for s in silo_contrib) else 0
        r_reinf = self._pearson(reinf_contrib, actual_vals) if any(r != 0 for r in reinf_contrib) else 0
        r_corr = self._pearson(corr_contrib, actual_vals) if any(c != 0 for c in corr_contrib) else 0
        r_resid = self._pearson(resid_contrib, actual_vals) if any(r != 0 for r in resid_contrib) else 0

        # Adjust: increase weight for high-correlation components,
        # decrease for low/negative correlation components
        def _adjust(current, r):
            if r > 0.5:
                return round(current * 1.2, 4)  # Increase 20%
            elif r > 0.2:
                return round(current, 4)         # Keep
            elif r > 0:
                return round(current * 0.9, 4)  # Decrease 10%
            else:
                return round(current * 0.7, 4)  # Decrease 30%

        return {
            "silo_coefficient": _adjust(self.SILO_COEFF, r_silo),
            "reinf_weight": _adjust(self.REINF_WEIGHT, r_reinf),
            "corr_weight": _adjust(self.CORR_WEIGHT, r_corr),
            "resid_weight": _adjust(self.RESID_WEIGHT, r_resid),
        }


# ═══════════════════════════════════════════════════════════════════════
# 5. CHAIN DEPTH PROFILER — Weekly: Python only, zero AI cost
# ═══════════════════════════════════════════════════════════════════════

class ChainDepthProfiler:
    """Track every causal chain and test whether the depth distribution matches
    the theoretical 0.273 decay per level. Tests V(d) depth-value model.
    Pure Python — no LLM calls needed."""

    def run(self):
        """Profile chain depth distribution, fit decay, compute R², find anomalies."""
        try:
            from database import get_connection

            conn = get_connection()
            cursor = conn.cursor()

            # ── 1. Count chains at each depth level ──
            cursor.execute("""
                SELECT chain_length, COUNT(*) as cnt
                FROM chains
                GROUP BY chain_length
                ORDER BY chain_length
            """)
            raw_depth_dist = {row[0]: row[1] for row in cursor.fetchall()}

            if not raw_depth_dist or sum(raw_depth_dist.values()) < 3:
                conn.close()
                return

            total_chains = sum(raw_depth_dist.values())

            # ── 2. Get hypothesis values (diamond_score) by depth ──
            cursor.execute("""
                SELECT ch.chain_length, h.diamond_score
                FROM chains ch
                JOIN hypotheses h ON ch.collision_id = h.collision_id
                WHERE h.diamond_score IS NOT NULL
            """)
            depth_scores = {}
            for row in cursor.fetchall():
                depth = row[0]
                if depth not in depth_scores:
                    depth_scores[depth] = []
                depth_scores[depth].append(row[1])

            # ── Build depth distribution for levels 1-6+ ──
            depth_distribution = {}
            base_count = raw_depth_dist.get(1, 0) or max(raw_depth_dist.values())

            for d in range(1, 7):
                if d < 6:
                    count = raw_depth_dist.get(d, 0)
                    scores = depth_scores.get(d, [])
                else:
                    # 6+ bucket: aggregate all depths >= 6
                    count = sum(v for k, v in raw_depth_dist.items() if k >= 6)
                    scores = []
                    for k, v in depth_scores.items():
                        if k >= 6:
                            scores.extend(v)

                avg_value = round(sum(scores) / max(1, len(scores)), 1) if scores else 0
                theoretical_value = compute_depth_value(d)

                # Predicted count: base_count * (1 - decay)^(d-1)
                predicted_count = round(base_count * ((1 - CHAIN_DECAY_RATE) ** (d - 1)), 1)

                key = str(d) if d < 6 else "6+"
                depth_distribution[key] = {
                    "count": count,
                    "avg_value": avg_value,
                    "predicted_count": predicted_count,
                    "theoretical_value": round(theoretical_value, 6),
                }

            # ── 3. Empirical decay ratio ──
            decay_ratios = []
            sorted_depths = sorted(d for d in raw_depth_dist.keys() if d >= 1)
            for i in range(1, len(sorted_depths)):
                prev_d = sorted_depths[i - 1]
                curr_d = sorted_depths[i]
                if curr_d == prev_d + 1 and raw_depth_dist[prev_d] > 0:
                    ratio = raw_depth_dist[curr_d] / raw_depth_dist[prev_d]
                    decay_ratios.append(ratio)

            empirical_decay = round(sum(decay_ratios) / max(1, len(decay_ratios)), 4) if decay_ratios else None
            decay_delta = round(empirical_decay - CHAIN_DECAY_RATE, 4) if empirical_decay is not None else None

            # ── 4. R-squared: predicted vs actual count distribution ──
            actual_counts = []
            predicted_counts = []
            for d in sorted_depths:
                if d >= 1:
                    actual_counts.append(raw_depth_dist[d])
                    predicted_counts.append(base_count * ((1 - CHAIN_DECAY_RATE) ** (d - 1)))

            r_squared = self._r_squared(actual_counts, predicted_counts)

            # ── 5. Value increases with depth? (theory predicts yes per unit) ──
            value_increases = False
            avg_values_by_depth = []
            for d in sorted_depths:
                scores = depth_scores.get(d, [])
                if scores:
                    avg_values_by_depth.append((d, sum(scores) / len(scores)))
            if len(avg_values_by_depth) >= 2:
                # Check if trend is upward
                first_half = [v for d, v in avg_values_by_depth[:len(avg_values_by_depth) // 2]]
                second_half = [v for d, v in avg_values_by_depth[len(avg_values_by_depth) // 2:]]
                if first_half and second_half:
                    avg_first = sum(first_half) / len(first_half)
                    avg_second = sum(second_half) / len(second_half)
                    value_increases = avg_second > avg_first

            # ── 6. Anomalous depths ──
            anomalous_depths = []
            for d in sorted_depths:
                if d < 1:
                    continue
                actual = raw_depth_dist[d]
                predicted = base_count * ((1 - CHAIN_DECAY_RATE) ** (d - 1))
                if predicted > 0:
                    ratio = actual / predicted
                    if ratio > 2.0:
                        anomalous_depths.append({
                            "depth": d,
                            "issue": f"Excess chains at depth {d}: {actual} actual vs "
                                     f"{predicted:.1f} predicted ({ratio:.1f}x). "
                                     f"Possible: systematic bias in chain extension at this depth, "
                                     f"or domain-specific pathways that cluster here.",
                        })
                    elif ratio < 0.3 and actual > 0:
                        anomalous_depths.append({
                            "depth": d,
                            "issue": f"Deficit at depth {d}: {actual} actual vs "
                                     f"{predicted:.1f} predicted ({ratio:.1f}x). "
                                     f"Possible: entity resolution failure breaks chains before this depth, "
                                     f"or data sparsity prevents extension.",
                        })
                elif actual > 0 and predicted == 0:
                    anomalous_depths.append({
                        "depth": d,
                        "issue": f"Unexpected chains at depth {d}: {actual} found where 0 predicted. "
                                 f"Possible: base count too low for prediction, or serendipitous discovery.",
                    })

            # ── 7. Build full summary ──
            now = datetime.now()
            confidence = min(1.0, round(total_chains / 30, 2))

            summary = {
                "date": now.strftime("%Y-%m-%d"),
                "total_chains": total_chains,
                "depth_distribution": depth_distribution,
                "empirical_decay_factor": empirical_decay,
                "predicted_decay_factor": CHAIN_DECAY_RATE,
                "decay_delta": decay_delta,
                "r_squared": r_squared,
                "value_increases_with_depth": value_increases,
                "anomalous_depths": anomalous_depths,
                "confidence": confidence,
            }

            # ── Write per-depth evidence ──
            for d_key, d_data in depth_distribution.items():
                d_int = int(d_key.replace("+", "")) if d_key != "6+" else 6
                ev_type = "direct" if d_data["count"] >= 3 else "supporting"

                cursor.execute("""
                    INSERT INTO theory_evidence
                    (timestamp, source_event, source_id, layer, layer_name,
                     evidence_type, description, metric, observed_value,
                     predicted_value, unit, confidence, domain_pair,
                     chain_depth, cycle_detected, cycle_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now.isoformat(), "chain_profiling", None,
                    7, "L07_depth_value",
                    ev_type,
                    f"Depth {d_key}: {d_data['count']} chains (predicted: "
                    f"{d_data['predicted_count']}), avg score {d_data['avg_value']}. "
                    f"Theoretical value: ${d_data['theoretical_value']}T.",
                    "depth_distribution",
                    d_data["count"], d_data["predicted_count"],
                    "chain_count", min(1.0, d_int * 0.2),
                    None, d_int, 0, None,
                ))

            # ── Write summary evidence ──
            description = (
                f"Chain depth profile: {total_chains} chains. "
                f"Empirical decay: {empirical_decay} (predicted: {CHAIN_DECAY_RATE}, "
                f"delta: {decay_delta}). R²={r_squared}. "
                f"Value {'increases' if value_increases else 'does NOT increase'} with depth. "
                f"{len(anomalous_depths)} anomalous depths."
            )
            cursor.execute("""
                INSERT INTO theory_evidence
                (timestamp, source_event, source_id, layer, layer_name,
                 evidence_type, description, metric, observed_value,
                 predicted_value, unit, confidence, domain_pair,
                 chain_depth, cycle_detected, cycle_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now.isoformat(), "chain_profile_summary", None,
                7, "L07_depth_value",
                "direct" if r_squared and r_squared > 0.5 else "supporting",
                description[:500],
                "r_squared",
                r_squared, 0.8,  # Theory hopes for R² > 0.8
                "r_squared", confidence,
                json.dumps(summary),  # Full summary for dashboard retrieval
                None, 0, None,
            ))

            conn.commit()
            conn.close()

        except Exception:
            pass

    @staticmethod
    def _r_squared(actual, predicted):
        """Compute R² goodness of fit between actual and predicted distributions."""
        if not actual or not predicted or len(actual) != len(predicted):
            return None
        n = len(actual)
        if n < 2:
            return None
        mean_actual = sum(actual) / n
        ss_res = sum((a - p) ** 2 for a, p in zip(actual, predicted))
        ss_tot = sum((a - mean_actual) ** 2 for a in actual)
        if ss_tot == 0:
            return 1.0 if ss_res == 0 else 0.0
        return round(1 - ss_res / ss_tot, 4)


# ═══════════════════════════════════════════════════════════════════════
# 6. BACKTEST RECONCILER — Weekly: Sonnet for complex reasoning
# ═══════════════════════════════════════════════════════════════════════

BACKTEST_SYSTEM = """You are the Backtest Reconciler for HUNTER. For every hypothesis whose
time window has expired, you determine whether the predicted market
move actually occurred. This is the strongest empirical evidence:
does HUNTER's detection of epistemic residual translate into real
market outcomes?

For each expired hypothesis, determine:
1. Did the asset move in the predicted direction? (directional accuracy)
2. By how much? (magnitude accuracy)
3. Within the predicted timeframe? (timing accuracy)
4. Was the move caused by the predicted mechanism? (mechanism accuracy)

Be factual and precise. Only confirm direction/mechanism if you can
find clear evidence. When uncertain, say so."""


class BacktestReconciler:
    """Reconcile expired hypotheses against actual market outcomes.
    Uses web search + Sonnet for complex reasoning. Then computes
    aggregate statistics and theory validation breakdowns."""

    def run(self):
        """Find expired hypotheses, reconcile each, then compute aggregates."""
        try:
            from database import get_connection
            from hunter import call_with_web_search, extract_text_from_response, parse_json_response

            conn = get_connection()
            cursor = conn.cursor()

            # ── STEP 1: Reconcile new expired hypotheses ──
            cursor.execute("""
                SELECT h.id, h.hypothesis_text, h.diamond_score, h.time_window_days,
                       h.created_at, h.action_steps, c.source_types, c.domains_involved
                FROM hypotheses h
                JOIN collisions c ON h.collision_id = c.id
                WHERE h.survived_kill = 1
                AND h.diamond_score >= 50
                AND julianday('now') - julianday(h.created_at) > h.time_window_days
                AND h.id NOT IN (SELECT hypothesis_id FROM backtest_results)
                ORDER BY h.diamond_score DESC
                LIMIT 5
            """)
            expired = [dict(row) for row in cursor.fetchall()]

            now = datetime.now()
            newly_reconciled = 0

            for hyp in (expired or []):
                try:
                    response = call_with_web_search(
                        f"""This hypothesis was generated on {hyp['created_at'][:10]} with a
{hyp['time_window_days']}-day window. The window has expired. What actually happened?

HYPOTHESIS:
{hyp['hypothesis_text'][:800]}

PREDICTED ACTION:
{(hyp.get('action_steps') or '')[:400]}

Search for the actual outcome. Determine:
1. Did the asset move in the predicted direction?
2. By how much (percentage)?
3. Was the move within the predicted timeframe?
4. Was the move caused by the specific mechanism described?

Respond with ONLY JSON:
{{
    "direction_correct": true/false/null,
    "magnitude_predicted_pct": <predicted percentage move or null>,
    "magnitude_actual_pct": <actual percentage move or null>,
    "within_timeframe": true/false/null,
    "mechanism_confirmed": true/false/null,
    "negative_space_score": <0-10 how much the market failed to react>,
    "summary": "What actually happened"
}}""",
                        system=BACKTEST_SYSTEM,
                        max_tokens=1024,
                    )
                    text = extract_text_from_response(response)
                    data = parse_json_response(text)

                    # Compute domain distance
                    domain_dist = 0.0
                    try:
                        from config import compute_avg_domain_distance
                        st = hyp.get("source_types", "")
                        types = [t.strip() for t in st.split(",") if t.strip()]
                        if len(types) >= 2:
                            domain_dist = compute_avg_domain_distance(types)
                    except Exception:
                        pass

                    # Get chain depth
                    cursor.execute("""
                        SELECT MAX(chain_length) FROM chains
                        WHERE collision_id = (SELECT collision_id FROM hypotheses WHERE id = ?)
                    """, (hyp["id"],))
                    chain_row = cursor.fetchone()
                    chain_depth = chain_row[0] if chain_row and chain_row[0] else 0

                    # Check if cycle was involved
                    cycle_involved = 0
                    try:
                        first_domain = hyp.get('domains_involved', '').split(',')[0].strip()
                        if first_domain:
                            cursor.execute("""
                                SELECT COUNT(*) FROM detected_cycles
                                WHERE domains LIKE ? AND is_active = 1
                            """, (f"%{first_domain}%",))
                            if cursor.fetchone()[0] > 0:
                                cycle_involved = 1
                    except Exception:
                        pass

                    cursor.execute("""
                        INSERT INTO backtest_results
                        (hypothesis_id, reconciled_date, direction_correct,
                         magnitude_predicted, magnitude_actual, within_timeframe,
                         mechanism_confirmed, chain_depth, domain_distance, cycle_involved)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        hyp["id"], now.isoformat(),
                        1 if data.get("direction_correct") else 0,
                        data.get("magnitude_predicted_pct"),
                        data.get("magnitude_actual_pct"),
                        1 if data.get("within_timeframe") else 0,
                        1 if data.get("mechanism_confirmed") else 0,
                        chain_depth, round(domain_dist, 3), cycle_involved,
                    ))
                    newly_reconciled += 1

                except Exception:
                    continue

            # ── STEP 2: Compute aggregate statistics from ALL backtest results ──
            try:
                self._compute_aggregates(cursor, now)
            except Exception:
                pass

            conn.commit()
            conn.close()

        except Exception:
            pass

    def _compute_aggregates(self, cursor, now):
        """Compute aggregate backtest statistics and theory validation."""
        cursor.execute("""
            SELECT br.hypothesis_id, br.direction_correct, br.magnitude_predicted,
                   br.magnitude_actual, br.within_timeframe, br.mechanism_confirmed,
                   br.chain_depth, br.domain_distance, br.cycle_involved,
                   h.diamond_score
            FROM backtest_results br
            JOIN hypotheses h ON br.hypothesis_id = h.id
        """)
        rows = cursor.fetchall()
        if not rows or len(rows) < 2:
            return

        total = len(rows)

        # ── Aggregate accuracy metrics ──
        direction_hits = sum(1 for r in rows if r[1])
        timing_hits = sum(1 for r in rows if r[4])
        mechanism_hits = sum(1 for r in rows if r[5])

        directional_accuracy = round(direction_hits / total, 3)
        timing_accuracy = round(timing_hits / total, 3)
        mechanism_accuracy = round(mechanism_hits / total, 3)

        # Average magnitude error
        mag_errors = []
        for r in rows:
            pred = r[2]
            actual = r[3]
            if pred is not None and actual is not None:
                mag_errors.append(abs(pred - actual))
        avg_mag_error = round(sum(mag_errors) / max(1, len(mag_errors)), 2) if mag_errors else None

        # ── Calibration curve by score decile ──
        calibration = {
            "score_50_59": {"count": 0, "hits": 0},
            "score_60_69": {"count": 0, "hits": 0},
            "score_70_79": {"count": 0, "hits": 0},
            "score_80_89": {"count": 0, "hits": 0},
            "score_90_plus": {"count": 0, "hits": 0},
        }
        for r in rows:
            score = r[9] or 0
            hit = 1 if r[1] else 0  # direction_correct
            if score >= 90:
                bucket = "score_90_plus"
            elif score >= 80:
                bucket = "score_80_89"
            elif score >= 70:
                bucket = "score_70_79"
            elif score >= 60:
                bucket = "score_60_69"
            else:
                bucket = "score_50_59"
            calibration[bucket]["count"] += 1
            calibration[bucket]["hits"] += hit

        calibration_curve = {}
        for k, v in calibration.items():
            calibration_curve[k] = {
                "count": v["count"],
                "hit_rate": round(v["hits"] / max(1, v["count"]), 3),
            }

        # ── Theory validation breakdowns ──

        # Accuracy by chain depth
        depth_buckets = {}  # depth → [direction_correct]
        for r in rows:
            d = r[6] or 0
            if d not in depth_buckets:
                depth_buckets[d] = []
            depth_buckets[d].append(1 if r[1] else 0)
        sorted_depths = sorted(depth_buckets.keys())
        deeper_more_accurate = False
        if len(sorted_depths) >= 2:
            shallow = [v for d in sorted_depths[:len(sorted_depths) // 2]
                       for v in depth_buckets[d]]
            deep = [v for d in sorted_depths[len(sorted_depths) // 2:]
                    for v in depth_buckets[d]]
            if shallow and deep:
                deeper_more_accurate = (sum(deep) / len(deep)) > (sum(shallow) / len(shallow))

        # Accuracy by domain distance
        low_dist = [1 if r[1] else 0 for r in rows if (r[7] or 0) < 0.5]
        high_dist = [1 if r[1] else 0 for r in rows if (r[7] or 0) >= 0.5]
        higher_dist_more_accurate = False
        if low_dist and high_dist:
            higher_dist_more_accurate = (sum(high_dist) / len(high_dist)) > (sum(low_dist) / len(low_dist))

        # Cycles persist longer (directional accuracy for cycle-involved)
        no_cycle = [1 if r[1] else 0 for r in rows if not r[8]]
        with_cycle = [1 if r[1] else 0 for r in rows if r[8]]
        cycles_persist = False
        if no_cycle and with_cycle:
            cycles_persist = (sum(with_cycle) / len(with_cycle)) > (sum(no_cycle) / len(no_cycle))

        # Negative space predicts magnitude (check if high NS score correlates
        # with larger actual moves — we don't have NS score in backtest_results
        # directly, so approximate from hypotheses with higher scores)
        high_score_mag = [abs(r[3]) for r in rows if r[3] is not None and (r[9] or 0) >= 70]
        low_score_mag = [abs(r[3]) for r in rows if r[3] is not None and (r[9] or 0) < 70]
        ns_predicts_magnitude = False
        if high_score_mag and low_score_mag:
            ns_predicts_magnitude = (sum(high_score_mag) / len(high_score_mag)) > \
                                    (sum(low_score_mag) / len(low_score_mag))

        # ── Implied annual residual captured ──
        # Rough extrapolation: avg magnitude * directional accuracy * hypotheses/year
        implied_residual = None
        if avg_mag_error is not None and directional_accuracy > 0:
            avg_actual_mag = sum(abs(r[3]) for r in rows if r[3] is not None) / max(1, len(mag_errors))
            # Assume average position size of $10M, ~50 hypotheses/year
            annual_hyps = total * (365 / max(1, 30))  # Extrapolate from sample period
            implied_value = avg_actual_mag * 0.01 * 10_000_000 * directional_accuracy * min(50, annual_hyps)
            if implied_value > 1_000_000_000:
                implied_residual = f"${implied_value / 1_000_000_000:.1f} billion"
            elif implied_value > 1_000_000:
                implied_residual = f"${implied_value / 1_000_000:.1f} million"
            else:
                implied_residual = f"${implied_value:,.0f}"

        # ── Build summary ──
        confidence = min(1.0, round(total / 30, 2))
        summary = {
            "date": now.strftime("%Y-%m-%d"),
            "hypotheses_reconciled": total,
            "directional_accuracy": directional_accuracy,
            "avg_magnitude_error": avg_mag_error,
            "timing_accuracy": timing_accuracy,
            "mechanism_confirmed": mechanism_accuracy,
            "calibration_curve": calibration_curve,
            "theory_validation": {
                "deeper_chains_more_accurate": deeper_more_accurate,
                "higher_distance_more_accurate": higher_dist_more_accurate,
                "cycles_persist_longer": cycles_persist,
                "negative_space_predicts_magnitude": ns_predicts_magnitude,
            },
            "implied_annual_residual_captured": implied_residual or "insufficient data",
            "confidence": confidence,
        }

        # ── Write theory evidence ──
        # Layer 4: phase transition — do scores predict actual moves?
        cursor.execute("""
            INSERT INTO theory_evidence
            (timestamp, source_event, source_id, layer, layer_name,
             evidence_type, description, metric, observed_value,
             predicted_value, unit, confidence, domain_pair,
             chain_depth, cycle_detected, cycle_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now.isoformat(), "backtest_reconciliation", None,
            4, "L04_phase_transition",
            "direct" if directional_accuracy > 0.5 else "challenging",
            f"Backtest: {total} hypotheses reconciled. "
            f"Directional accuracy: {directional_accuracy:.1%}. "
            f"Timing accuracy: {timing_accuracy:.1%}. "
            f"Mechanism confirmed: {mechanism_accuracy:.1%}. "
            f"Avg magnitude error: {avg_mag_error}pp. "
            f"Deeper chains {'more' if deeper_more_accurate else 'NOT more'} accurate. "
            f"Higher distance {'more' if higher_dist_more_accurate else 'NOT more'} accurate.",
            "directional_accuracy",
            directional_accuracy, 0.6,  # Theory hopes for >60% directional accuracy
            "proportion", confidence,
            json.dumps(summary),  # Full summary for dashboard
            None, 0, None,
        ))

        # Layer 12: autopoiesis — calibration curve (do scores predict hit rates?)
        # Check if calibration is monotonically increasing
        hit_rates = [calibration_curve[k]["hit_rate"]
                     for k in ["score_50_59", "score_60_69", "score_70_79",
                               "score_80_89", "score_90_plus"]
                     if calibration_curve[k]["count"] > 0]
        calibration_monotonic = all(
            hit_rates[i] <= hit_rates[i + 1]
            for i in range(len(hit_rates) - 1)
        ) if len(hit_rates) >= 2 else False

        cursor.execute("""
            INSERT INTO theory_evidence
            (timestamp, source_event, source_id, layer, layer_name,
             evidence_type, description, metric, observed_value,
             predicted_value, unit, confidence, domain_pair,
             chain_depth, cycle_detected, cycle_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now.isoformat(), "backtest_calibration", None,
            12, "L12_autopoiesis",
            "direct" if calibration_monotonic else "supporting",
            f"Score calibration {'MONOTONIC' if calibration_monotonic else 'non-monotonic'}. "
            f"Hit rates by decile: " +
            ", ".join(f"{k}={v['hit_rate']:.0%}" for k, v in calibration_curve.items() if v["count"] > 0),
            "calibration_monotonic",
            1 if calibration_monotonic else 0, 1,
            "boolean", confidence,
            None, None, 0, None,
        ))


# ═══════════════════════════════════════════════════════════════════════
# 7. RESIDUAL ESTIMATOR — Monthly: Sonnet for complex reasoning
# ═══════════════════════════════════════════════════════════════════════

PREDICTED_CHAIN_RESIDUAL_T = 1.71
PREDICTED_CYCLE_RESIDUAL_T = 1.56
PREDICTED_HIERARCHY_RESIDUAL_T = 2.38
PREDICTED_TOTAL_RESIDUAL_T = 5.65


class ResidualEstimator:
    """Monthly aggregate: bottom-up estimate of total epistemic residual in the
    knowledge economy. Compares to theoretical prediction of $5.65T.
    Pure Python with optional Sonnet for reasoning."""

    def run(self):
        """Aggregate per-domain residual, break down by source, bootstrap CI."""
        try:
            from database import get_connection
            import random as _rand

            conn = get_connection()
            cursor = conn.cursor()
            now = datetime.now()

            # ── 1. Per-domain statistics ──
            domain_estimates = []
            domain_residuals_B = []  # For bootstrap

            for domain, params in DOMAIN_THEORY_PARAMS.items():
                market_size_b = params.get("market_size_b", 100)
                predicted_residual_pct = params["residual"] * 100

                # Count collisions involving this domain
                cursor.execute("""
                    SELECT COUNT(*) FROM collisions
                    WHERE source_types LIKE ?
                """, (f"%{domain}%",))
                collision_count = cursor.fetchone()[0]

                # Hypotheses and avg score
                cursor.execute("""
                    SELECT COUNT(*), AVG(h.diamond_score) FROM hypotheses h
                    JOIN collisions c ON h.collision_id = c.id
                    WHERE c.source_types LIKE ? AND h.survived_kill = 1
                """, (f"%{domain}%",))
                row = cursor.fetchone()
                hyp_count = row[0]
                avg_score = row[1]

                # Fact count
                cursor.execute("""
                    SELECT COUNT(*) FROM raw_facts WHERE source_type = ?
                """, (domain,))
                fact_count = cursor.fetchone()[0]

                # Backtest results for this domain
                cursor.execute("""
                    SELECT br.magnitude_actual, br.direction_correct
                    FROM backtest_results br
                    JOIN hypotheses h ON br.hypothesis_id = h.id
                    JOIN collisions c ON h.collision_id = c.id
                    WHERE c.source_types LIKE ?
                """, (f"%{domain}%",))
                bt_rows = cursor.fetchall()
                bt_count = len(bt_rows)

                # Compute observed residual rate
                # Best method: use actual backtest magnitudes if available
                if bt_rows and any(r[0] is not None for r in bt_rows):
                    # Sum of actual value captured (magnitude × direction correctness)
                    value_captured = sum(
                        abs(r[0] or 0) * (1 if r[1] else -0.5)
                        for r in bt_rows
                    )
                    # Observed rate = value captured / subset tested
                    # Subset tested ≈ number of hypotheses × avg_score proxy
                    tested_fraction = max(0.001, hyp_count / max(1, fact_count))
                    observed_pct = (value_captured / max(1, bt_count)) * tested_fraction
                    observed_pct = max(0.01, min(20, observed_pct))
                elif collision_count > 0 and fact_count > 0:
                    # Fallback: collision density × score quality
                    score_factor = (avg_score or 50) / 100
                    observed_pct = (collision_count * score_factor / fact_count) * 100
                    observed_pct = max(0.01, min(20, observed_pct))
                else:
                    observed_pct = None

                # Extrapolated domain residual
                if observed_pct is not None:
                    estimated_B = market_size_b * (observed_pct / 100)
                else:
                    estimated_B = market_size_b * (predicted_residual_pct / 100)

                delta = round(estimated_B - (market_size_b * predicted_residual_pct / 100), 2)

                domain_estimates.append({
                    "domain": domain,
                    "market_size_B": market_size_b,
                    "predicted_residual_pct": round(predicted_residual_pct, 2),
                    "observed_residual_pct": round(observed_pct, 3) if observed_pct else None,
                    "estimated_residual_B": round(estimated_B, 2),
                    "delta_from_prediction": delta,
                    "sample_size": fact_count,
                })
                domain_residuals_B.append(estimated_B)

                # Save to residual_estimates table
                cursor.execute("""
                    INSERT INTO residual_estimates
                    (date, domain, market_size_B, predicted_residual_pct,
                     observed_residual_pct, estimated_residual_B, sample_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    now.isoformat(), domain,
                    market_size_b,
                    round(predicted_residual_pct, 2),
                    round(observed_pct, 3) if observed_pct else None,
                    round(estimated_B, 2),
                    fact_count,
                ))

            # ── 2. Aggregate total ──
            total_estimated_B = sum(domain_residuals_B)
            total_estimated_T = round(total_estimated_B / 1000, 3)

            # ── 3. Break down by source type (chain, cycle, hierarchy) ──
            chain_residual_T, cycle_residual_T, hierarchy_residual_T = \
                self._compute_source_breakdown(cursor, total_estimated_T)

            # ── 4. Bootstrap confidence interval (95%) ──
            ci_lower, ci_upper = self._bootstrap_ci(domain_residuals_B, _rand)

            # ── 5. Methodology validation ──
            # Observed within 3x of predicted?
            ratio = total_estimated_T / PREDICTED_TOTAL_RESIDUAL_T if PREDICTED_TOTAL_RESIDUAL_T > 0 else 0
            methodology_validated = 0.33 <= ratio <= 3.0

            # Confidence based on domains with observed data
            domains_with_data = sum(1 for d in domain_estimates if d["observed_residual_pct"] is not None)
            confidence = min(1.0, round(domains_with_data / 15, 2))

            # ── 6. Build full summary ──
            summary = {
                "date": now.strftime("%Y-%m-%d"),
                "domain_estimates": domain_estimates,
                "aggregate": {
                    "chain_residual_T": chain_residual_T,
                    "cycle_residual_T": cycle_residual_T,
                    "hierarchy_residual_T": hierarchy_residual_T,
                    "total_estimated_T": total_estimated_T,
                    "predicted_total_T": PREDICTED_TOTAL_RESIDUAL_T,
                    "delta_T": round(total_estimated_T - PREDICTED_TOTAL_RESIDUAL_T, 3),
                    "confidence_interval_95": [ci_lower, ci_upper],
                },
                "methodology_validated": methodology_validated,
                "confidence": confidence,
            }

            # ── Write theory evidence ──
            # Layer 5: rate-distortion — is total residual close to Shannon floor?
            description = (
                f"Residual estimate: ${total_estimated_T:.2f}T "
                f"(predicted: ${PREDICTED_TOTAL_RESIDUAL_T}T, "
                f"delta: ${total_estimated_T - PREDICTED_TOTAL_RESIDUAL_T:+.2f}T). "
                f"Chain: ${chain_residual_T:.2f}T (pred: ${PREDICTED_CHAIN_RESIDUAL_T}T). "
                f"Cycle: ${cycle_residual_T:.2f}T (pred: ${PREDICTED_CYCLE_RESIDUAL_T}T). "
                f"Hierarchy: ${hierarchy_residual_T:.2f}T (pred: ${PREDICTED_HIERARCHY_RESIDUAL_T}T). "
                f"95% CI: [${ci_lower:.2f}T, ${ci_upper:.2f}T]. "
                f"{'VALIDATED' if methodology_validated else 'Outside 3x range'}. "
                f"{domains_with_data}/25 domains with observed data."
            )
            cursor.execute("""
                INSERT INTO theory_evidence
                (timestamp, source_event, source_id, layer, layer_name,
                 evidence_type, description, metric, observed_value,
                 predicted_value, unit, confidence, domain_pair,
                 chain_depth, cycle_detected, cycle_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now.isoformat(), "residual_estimation", None,
                5, "L05_rate_distortion",
                "direct" if methodology_validated else "challenging",
                description[:500],
                "total_residual_T",
                total_estimated_T, PREDICTED_TOTAL_RESIDUAL_T,
                "$T", confidence,
                json.dumps(summary),  # Full summary for dashboard
                None, 0, None,
            ))

            conn.commit()
            conn.close()

        except Exception:
            pass

    def _compute_source_breakdown(self, cursor, total_T):
        """Break down residual by source: chains, cycles, hierarchy."""
        # Chain residual: hypotheses with chain_length >= 2
        cursor.execute("""
            SELECT COUNT(*), AVG(h.diamond_score) FROM hypotheses h
            JOIN chains ch ON ch.collision_id = h.collision_id
            WHERE h.survived_kill = 1 AND ch.chain_length >= 2
        """)
        chain_row = cursor.fetchone()
        chain_count = chain_row[0] or 0

        # Cycle residual: hypotheses touching active cycles
        cursor.execute("""
            SELECT COUNT(*), AVG(h.diamond_score) FROM hypotheses h
            JOIN collisions c ON h.collision_id = c.id
            WHERE h.survived_kill = 1
            AND EXISTS (
                SELECT 1 FROM detected_cycles dc
                WHERE dc.is_active = 1
                AND c.source_types LIKE '%' || SUBSTR(dc.domains, 3, 20) || '%'
            )
        """)
        cycle_row = cursor.fetchone()
        cycle_count = cycle_row[0] or 0

        # Hierarchy residual: hypotheses with chain_length >= 3 AND multi-domain
        cursor.execute("""
            SELECT COUNT(*), AVG(h.diamond_score) FROM hypotheses h
            JOIN chains ch ON ch.collision_id = h.collision_id
            JOIN collisions c ON h.collision_id = c.id
            WHERE h.survived_kill = 1
            AND ch.chain_length >= 3
            AND c.num_domains >= 3
        """)
        hier_row = cursor.fetchone()
        hier_count = hier_row[0] or 0

        # Total hypothesis count for proportioning
        cursor.execute("""
            SELECT COUNT(*) FROM hypotheses WHERE survived_kill = 1
        """)
        total_hyps = cursor.fetchone()[0] or 1

        # Proportion-based allocation of total estimated residual
        chain_frac = chain_count / total_hyps
        cycle_frac = cycle_count / total_hyps
        hier_frac = hier_count / total_hyps

        # Normalize: if fractions sum > 1 (overlap), scale down
        total_frac = chain_frac + cycle_frac + hier_frac
        if total_frac > 1:
            chain_frac /= total_frac
            cycle_frac /= total_frac
            hier_frac /= total_frac
        elif total_frac < 1:
            # Remainder is "simple collision" residual — distribute proportionally
            # to theoretical predictions
            remainder = 1 - total_frac
            pred_total = PREDICTED_CHAIN_RESIDUAL_T + PREDICTED_CYCLE_RESIDUAL_T + PREDICTED_HIERARCHY_RESIDUAL_T
            chain_frac += remainder * (PREDICTED_CHAIN_RESIDUAL_T / pred_total)
            cycle_frac += remainder * (PREDICTED_CYCLE_RESIDUAL_T / pred_total)
            hier_frac += remainder * (PREDICTED_HIERARCHY_RESIDUAL_T / pred_total)

        return (
            round(total_T * chain_frac, 3),
            round(total_T * cycle_frac, 3),
            round(total_T * hier_frac, 3),
        )

    @staticmethod
    def _bootstrap_ci(domain_residuals_B, rng, n_bootstrap=1000, ci=0.95):
        """Bootstrap 95% confidence interval on total residual estimate."""
        if not domain_residuals_B or len(domain_residuals_B) < 2:
            total = sum(domain_residuals_B) / 1000 if domain_residuals_B else 0
            return (round(total * 0.5, 3), round(total * 2.0, 3))

        n = len(domain_residuals_B)
        totals = []
        for _ in range(n_bootstrap):
            # Resample with replacement
            sample = [domain_residuals_B[rng.randint(0, n - 1)] for _ in range(n)]
            totals.append(sum(sample) / 1000)  # Convert B to T

        totals.sort()
        alpha = (1 - ci) / 2
        lower_idx = max(0, int(alpha * n_bootstrap))
        upper_idx = min(n_bootstrap - 1, int((1 - alpha) * n_bootstrap))

        return (round(totals[lower_idx], 3), round(totals[upper_idx], 3))


# ═══════════════════════════════════════════════════════════════════════
# SCHEDULING HELPERS
# ═══════════════════════════════════════════════════════════════════════

# Timestamps for periodic task scheduling
_last_decay_check = None
_last_weekly_run = None
_last_monthly_run = None


def run_periodic_theory_tasks():
    """Called from the main loop. Runs theory agents on their schedules.
    Returns quickly if nothing is due."""
    global _last_decay_check, _last_weekly_run, _last_monthly_run

    now = datetime.now()

    # Initialize timestamps on first call
    if _last_decay_check is None:
        _last_decay_check = now
        _last_weekly_run = now
        _last_monthly_run = now
        return

    # Daily: decay tracker (every 24 hours)
    hours_since_decay = (now - _last_decay_check).total_seconds() / 3600
    if hours_since_decay >= 24:
        try:
            DecayTracker().run()
            _last_decay_check = now
        except Exception:
            pass

    # Weekly: cycle detector, formula validator, chain profiler, backtest (every 7 days)
    days_since_weekly = (now - _last_weekly_run).total_seconds() / 86400
    if days_since_weekly >= 7:
        try:
            CycleDetector().run()
        except Exception:
            pass
        try:
            CollisionFormulaValidator().run()
        except Exception:
            pass
        try:
            ChainDepthProfiler().run()
        except Exception:
            pass
        try:
            BacktestReconciler().run()
        except Exception:
            pass
        _last_weekly_run = now

    # Monthly: residual estimator (every 30 days)
    days_since_monthly = (now - _last_monthly_run).total_seconds() / 86400
    if days_since_monthly >= 30:
        try:
            ResidualEstimator().run()
        except Exception:
            pass
        _last_monthly_run = now
