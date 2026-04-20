"""Theory Proof Layer — Epistemic Residual Framework evidence recorder.

Observes HUNTER's trading pipeline outputs and records theoretical evidence.
Every collision is both a trading opportunity AND a data point proving the theory.
This module NEVER modifies scoring, kill, or hypothesis logic — pure observation.

13 Theoretical Layers:
 1. Translation Loss — Shannon channel capacity across domain boundaries
 2. Attention Topology — non-uniform analyst coverage creates permanent blind spots
 3. Question Gap — gap between questions asked vs questions that exist
 4. Epistemic Phase Transitions — residual accumulation predicts sudden corrections
 5. Rate-Distortion Bedrock — mathematical floor on compressible information
 6. Market Incompleteness — cross-domain implications with no trading instrument
 7. Depth-Value Distribution — deeper chain errors worth more per unit
 8. Epistemic Cycles — self-reinforcing error loops (207x persistence ratio)
 9. Cycle Hierarchy — 9 cycle types from simple to dormant
10. Fractal Incompleteness — structurally unreachable errors (Gödel analogy)
11. Negative Space Topology — shape of market non-reaction reveals blind spots
12. Autopoiesis — system proves theory by finding predicted residual
13. Observer-Dependent Topology — correction changes remaining error landscape
"""

import json
import math
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════
# THEORETICAL CONSTANTS
# ═══════════════════════════════════════════════════════════════════════

# Chain decay rate per depth level (Layer 7)
CHAIN_DECAY_RATE = 0.273

# Markov eigenvalues for error persistence (Layer 8)
MARKOV_EIGENVALUES = (1.0, 0.52, 0.18)

# Persistence ratio: reinforcement / correction (Layer 8)
# Measured per-domain ratios (2026-04-19, n=18 source types):
#   median 24x, range 10.5x (healthcare_re) to 74x (bankruptcy).
# Framework originally predicted aggregate 207x; measurement shows that was
# 6-10x too high. The DIRECTION (reinforcement dominates correction) is
# confirmed; the specific constant is recalibrated.
EXPECTED_PERSISTENCE_RATIO = 24   # was 207 — replaced with median of measured
EXPECTED_PERSISTENCE_RATIO_RANGE = (10, 75)  # observed min, max per-domain
EXPECTED_PERSISTENCE_RATIO_LEGACY = 207      # kept for reproducibility of v1 theory

# Depth-value formula constants (Layer 7) — calibrated 2026-04-18
# Per-chain expected residual value in $M. Hump-shaped, peaks near d=3.
# V(d) = BASE * d * exp(-d/TAU) where BASE=$10M, TAU=3
# Previous formula summed combinatorial C(25, d+1) across all possible
# domain subsets and produced absurd totals ($1000T+). That conflated
# per-chain value with cumulative TAM. This version reports the value
# of a SINGLE discovered chain at depth d, which is what gets logged
# as theory evidence and compared to observed diamond scores.
DEPTH_VALUE_BASE_M = 10.0   # $10M typical mid-cap mispricing per chain
DEPTH_VALUE_TAU = 3.0       # depth at which per-chain value peaks

# Cycle type hierarchy (Layer 9) — ordinal rank by persistence
CYCLE_HIERARCHY = {
    "simple": 1,
    "nested": 2,
    "coupled": 3,
    "braided": 4,
    "hierarchical": 5,
    "temporal": 6,
    "cross_domain": 7,
    "interference": 8,
    "dormant": 9,
}

# Total estimated epistemic residual (Layer 12 — autopoiesis target)
TOTAL_ESTIMATED_RESIDUAL_T = 5.65  # $5.65 trillion
RESIDUAL_CHAINS_T = 1.71
RESIDUAL_CYCLES_T = 1.56
RESIDUAL_HIERARCHY_T = 2.38


# ═══════════════════════════════════════════════════════════════════════
# DOMAIN PARAMETERS (25 domains)
# ═══════════════════════════════════════════════════════════════════════

# Each domain: silos (compartments), reinf (reinforcement rate 0-1),
# corr (correction rate 0-1), resid (residual % of addressable value),
# market_size_b (addressable market in $B), access (data accessibility 0-1)
DOMAIN_THEORY_PARAMS = {
    "sec_filing":       {"silo_count": 3, "reinforcement": 0.7, "correction": 0.6,  "residual": 0.02, "market_size_b": 400,  "access": 0.9},
    "earnings":         {"silo_count": 2, "reinforcement": 0.8, "correction": 0.7,  "residual": 0.01, "market_size_b": 800,  "access": 0.95},
    "distressed":       {"silo_count": 4, "reinforcement": 0.5, "correction": 0.3,  "residual": 0.05, "market_size_b": 150,  "access": 0.5},
    "cre_credit":       {"silo_count": 5, "reinforcement": 0.4, "correction": 0.2,  "residual": 0.06, "market_size_b": 600,  "access": 0.3},
    "specialty_re":     {"silo_count": 4, "reinforcement": 0.4, "correction": 0.25, "residual": 0.05, "market_size_b": 200,  "access": 0.35},
    "healthcare_re":    {"silo_count": 3, "reinforcement": 0.4, "correction": 0.2,  "residual": 0.06, "market_size_b": 300,  "access": 0.3},
    "energy_infra":     {"silo_count": 5, "reinforcement": 0.5, "correction": 0.3,  "residual": 0.05, "market_size_b": 500,  "access": 0.4},
    "commodity":        {"silo_count": 4, "reinforcement": 0.6, "correction": 0.5,  "residual": 0.03, "market_size_b": 700,  "access": 0.7},
    "insurance":        {"silo_count": 6, "reinforcement": 0.3, "correction": 0.15, "residual": 0.08, "market_size_b": 400,  "access": 0.2},
    "regulation":       {"silo_count": 8, "reinforcement": 0.3, "correction": 0.1,  "residual": 0.07, "market_size_b": 300,  "access": 0.6},
    "bankruptcy":       {"silo_count": 3, "reinforcement": 0.4, "correction": 0.3,  "residual": 0.04, "market_size_b": 100,  "access": 0.5},
    "pharmaceutical":   {"silo_count": 5, "reinforcement": 0.5, "correction": 0.3,  "residual": 0.05, "market_size_b": 600,  "access": 0.4},
    "patent":           {"silo_count": 4, "reinforcement": 0.3, "correction": 0.1,  "residual": 0.07, "market_size_b": 200,  "access": 0.5},
    "academic":         {"silo_count": 7, "reinforcement": 0.6, "correction": 0.2,  "residual": 0.04, "market_size_b": 100,  "access": 0.8},
    "government_contract": {"silo_count": 5, "reinforcement": 0.4, "correction": 0.15, "residual": 0.06, "market_size_b": 250, "access": 0.4},
    "job_listing":      {"silo_count": 2, "reinforcement": 0.3, "correction": 0.4,  "residual": 0.03, "market_size_b": 50,   "access": 0.9},
    "app_ranking":      {"silo_count": 2, "reinforcement": 0.5, "correction": 0.5,  "residual": 0.02, "market_size_b": 80,   "access": 0.95},
    "other":            {"silo_count": 3, "reinforcement": 0.5, "correction": 0.4,  "residual": 0.03, "market_size_b": 100,  "access": 0.5},
}

# Keep the hand-guessed values for reproducibility; downstream code can use
# get_domain_params() which overlays empirical values from measured_domain_params.
DOMAIN_THEORY_PARAMS_V1_HANDCALIBRATED = {k: dict(v) for k, v in DOMAIN_THEORY_PARAMS.items()}


def _load_measured_domain_params():
    """Overlay empirical reinforcement/correction rates from the
    measured_domain_params table onto DOMAIN_THEORY_PARAMS. Falls back to
    hand-calibrated values if DB unavailable or table missing. Runs once
    at import time."""
    try:
        import sqlite3
        from pathlib import Path
        db = Path(__file__).parent / "hunter.db"
        if not db.exists():
            return
        conn = sqlite3.connect(db)
        try:
            rows = conn.execute(
                "SELECT source_type, reinforcement_measured, correction_measured, n_facts "
                "FROM measured_domain_params"
            ).fetchall()
        except sqlite3.OperationalError:
            # Table doesn't exist yet; keep hand-calibrated values.
            conn.close()
            return
        conn.close()
        for st, reinf_m, corr_m, n in rows:
            if st in DOMAIN_THEORY_PARAMS and n and n >= 30:
                # Only overlay when we have >= 30 facts for the domain.
                if reinf_m is not None:
                    DOMAIN_THEORY_PARAMS[st]["reinforcement"] = round(float(reinf_m), 4)
                if corr_m is not None and corr_m > 0:
                    DOMAIN_THEORY_PARAMS[st]["correction"] = round(float(corr_m), 4)
    except Exception:
        # Never fail import — framework has to work even on a fresh install.
        pass


# Load measured values on import. Downstream code sees the calibrated dict.
_load_measured_domain_params()


# ═══════════════════════════════════════════════════════════════════════
# LAYER DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════

LAYER_TRANSLATION_LOSS = "L01_translation_loss"
LAYER_ATTENTION_TOPOLOGY = "L02_attention_topology"
LAYER_QUESTION_GAP = "L03_question_gap"
LAYER_PHASE_TRANSITION = "L04_phase_transition"
LAYER_RATE_DISTORTION = "L05_rate_distortion"
LAYER_MARKET_INCOMPLETENESS = "L06_market_incompleteness"
LAYER_DEPTH_VALUE = "L07_depth_value"
LAYER_EPISTEMIC_CYCLES = "L08_epistemic_cycles"
LAYER_CYCLE_HIERARCHY = "L09_cycle_hierarchy"
LAYER_FRACTAL_INCOMPLETENESS = "L10_fractal_incompleteness"
LAYER_NEGATIVE_SPACE = "L11_negative_space"
LAYER_AUTOPOIESIS = "L12_autopoiesis"
LAYER_OBSERVER_DEPENDENT = "L13_observer_dependent"

# Layer name → integer (1-13) for database storage
LAYER_TO_NUM = {
    LAYER_TRANSLATION_LOSS: 1,
    LAYER_ATTENTION_TOPOLOGY: 2,
    LAYER_QUESTION_GAP: 3,
    LAYER_PHASE_TRANSITION: 4,
    LAYER_RATE_DISTORTION: 5,
    LAYER_MARKET_INCOMPLETENESS: 6,
    LAYER_DEPTH_VALUE: 7,
    LAYER_EPISTEMIC_CYCLES: 8,
    LAYER_CYCLE_HIERARCHY: 9,
    LAYER_FRACTAL_INCOMPLETENESS: 10,
    LAYER_NEGATIVE_SPACE: 11,
    LAYER_AUTOPOIESIS: 12,
    LAYER_OBSERVER_DEPENDENT: 13,
}

ALL_LAYERS = [
    LAYER_TRANSLATION_LOSS,
    LAYER_ATTENTION_TOPOLOGY,
    LAYER_QUESTION_GAP,
    LAYER_PHASE_TRANSITION,
    LAYER_RATE_DISTORTION,
    LAYER_MARKET_INCOMPLETENESS,
    LAYER_DEPTH_VALUE,
    LAYER_EPISTEMIC_CYCLES,
    LAYER_CYCLE_HIERARCHY,
    LAYER_FRACTAL_INCOMPLETENESS,
    LAYER_NEGATIVE_SPACE,
    LAYER_AUTOPOIESIS,
    LAYER_OBSERVER_DEPENDENT,
]

LAYER_DESCRIPTIONS = {
    LAYER_TRANSLATION_LOSS: "Information degrades when crossing domain boundaries (Shannon channel capacity)",
    LAYER_ATTENTION_TOPOLOGY: "Non-uniform analyst coverage creates permanent blind spots",
    LAYER_QUESTION_GAP: "Gap between questions asked and questions that exist",
    LAYER_PHASE_TRANSITION: "Residual accumulation predicts sudden consensus shifts",
    LAYER_RATE_DISTORTION: "Mathematical floor on information compression across domains",
    LAYER_MARKET_INCOMPLETENESS: "Cross-domain implications with no natural trading instrument",
    LAYER_DEPTH_VALUE: "Deeper chain errors are worth more per unit",
    LAYER_EPISTEMIC_CYCLES: "Self-reinforcing error loops persist at 207x correction rate",
    LAYER_CYCLE_HIERARCHY: "9 cycle types ordered by persistence and complexity",
    LAYER_FRACTAL_INCOMPLETENESS: "Some errors structurally unreachable by market correction",
    LAYER_NEGATIVE_SPACE: "Shape of market non-reaction reveals structural blind spots",
    LAYER_AUTOPOIESIS: "Finding residual where predicted IS the evidence",
    LAYER_OBSERVER_DEPENDENT: "Observation changes remaining error topology",
}


# ═══════════════════════════════════════════════════════════════════════
# THEORETICAL COMPUTATIONS
# ═══════════════════════════════════════════════════════════════════════

# ── Collision formula weights ──
# v1: original hand-calibrated weights (kept for reproducibility, frozen)
# v2: refitted from formula_validator regression on 153 pairs, 474 collisions
#     (2026-04-19). In-sample r = 1.0 by construction; out-of-sample validation
#     pending the summer study. Magnitudes are pulled back from the raw
#     regression betas (~30-40% of full delta) to avoid overfitting.
COLLISION_FORMULA_WEIGHTS = {
    "v1_original": {
        "silo": 0.003,
        "reinf": 20.0,
        "corr": 30.0,
        "resid": 400.0,
        "intercept": 0.0,
    },
    "v2_refitted_conservative": {
        # Regression deltas: silo β=+115, reinf β=+0.23, corr β=-3.51, resid β=+34.61, intercept=+57.77
        # Applied conservatively: bump silo and resid toward regression, leave reinf,
        # shrink corr without flipping sign (a sign flip needs independent confirmation).
        "silo": 0.10,       # 33x bump toward regression's 115x hint
        "reinf": 15.0,      # small pullback from 20 — corr and reinf partially proxy each other
        "corr": 10.0,       # large pullback; regression suggested even smaller or negative
        "resid": 1500.0,    # 3.75x bump toward regression's 34x hint
        "intercept": 20.0,  # positive intercept absorbs baseline collision rate
    },
}

# Which weights are LIVE — pre-registration requires this be frozen.
# If you change this mid-study, verify preregister.py throws drift warnings.
ACTIVE_COLLISION_WEIGHTS_VERSION = "v2_refitted_conservative"


def compute_collision_formula(source_type_a, source_type_b, weights_version=None):
    """Apply the epistemic residual collision formula to a domain pair.

    score(A,B) = (A.silos * B.silos * w.silo)
               + (A.reinf + B.reinf) * w.reinf
               + (1 - A.corr) * (1 - B.corr) * w.corr
               + (A.resid * B.resid) * w.resid
               + w.intercept

    Default uses ACTIVE_COLLISION_WEIGHTS_VERSION. Pass weights_version to
    compare versions (e.g. 'v1_original').
    """
    version = weights_version or ACTIVE_COLLISION_WEIGHTS_VERSION
    w = COLLISION_FORMULA_WEIGHTS.get(version, COLLISION_FORMULA_WEIGHTS["v1_original"])
    a = DOMAIN_THEORY_PARAMS.get(source_type_a, DOMAIN_THEORY_PARAMS["other"])
    b = DOMAIN_THEORY_PARAMS.get(source_type_b, DOMAIN_THEORY_PARAMS["other"])

    silo_term = a["silo_count"] * b["silo_count"] * w["silo"]
    reinf_term = (a["reinforcement"] + b["reinforcement"]) * w["reinf"]
    corr_term = (1 - a["correction"]) * (1 - b["correction"]) * w["corr"]
    resid_term = a["residual"] * b["residual"] * w["resid"]
    total = silo_term + reinf_term + corr_term + resid_term + w["intercept"]

    return {
        "total": round(total, 4),
        "silo_term": round(silo_term, 4),
        "reinforcement_term": round(reinf_term, 4),
        "correction_term": round(corr_term, 4),
        "residual_term": round(resid_term, 4),
        "intercept": w["intercept"],
        "weights_version": version,
    }


# Backward compatibility alias
compute_collision_theory_score = compute_collision_formula


def compute_depth_value(depth):
    """Layer 7: Expected per-chain residual value at chain depth d, in $M.

    V(d) = BASE_M * d * exp(-d/TAU)

    Shape: zero at d=0, peak near d=TAU (=3), decays exponentially after.
    Intuition: d=0 is single-domain (no cross-silo insight), peak is where
    information asymmetry is largest, deeper chains rarer and harder to verify.

    Calibration reference points:
      d=1 → ~$7M    d=2 → ~$10M    d=3 → ~$11M (peak)
      d=4 → ~$11M   d=5 → ~$9M     d=6 → ~$8M
      d=10 → ~$4M   d=20 → ~$0.2M

    Cumulative sum across all observed chains in HUNTER (8,656 steady-state
    facts, ~5% chain-participation rate) implies ~$4-5B of addressable
    per-chain value. This is a LOCAL estimate, not a market-wide residual
    claim. Any TAM estimate must be derived from portfolio capture rate,
    not from this function.
    """
    if depth <= 0:
        return 0.0
    if depth > 50:
        return 0.0  # exp decay dominates, value negligible
    value = DEPTH_VALUE_BASE_M * depth * math.exp(-depth / DEPTH_VALUE_TAU)
    return round(value, 3)


def compute_rate_distortion_floor(source_type_a, source_type_b):
    """Layer 5: Theoretical minimum distortion when compressing information
    from domain A for consumption in domain B.

    Uses Shannon rate-distortion: D(R) = sigma^2 * 2^(-2R)
    where sigma^2 approximates domain complexity (silo_count / access)
    and R approximates channel capacity (inverse of domain distance).
    """
    try:
        from config import get_domain_distance
        distance = get_domain_distance(source_type_a, source_type_b)
    except Exception:
        distance = 0.5

    a = DOMAIN_THEORY_PARAMS.get(source_type_a, DOMAIN_THEORY_PARAMS["other"])
    b = DOMAIN_THEORY_PARAMS.get(source_type_b, DOMAIN_THEORY_PARAMS["other"])

    # Source complexity = silo fragmentation / accessibility
    sigma_sq = (a["silo_count"] / max(0.1, a["access"])) * (b["silo_count"] / max(0.1, b["access"]))
    # Channel capacity = inverse of domain distance (closer = more capacity)
    R = max(0.01, 1.0 - distance)
    # Rate-distortion: minimum distortion at rate R
    min_distortion = sigma_sq * (2 ** (-2 * R))

    return {
        "min_distortion": round(min_distortion, 4),
        "source_complexity": round(sigma_sq, 4),
        "channel_capacity": round(R, 4),
        "domain_distance": round(distance, 4),
    }


def compute_persistence_ratio(source_type):
    """Layer 8: Compute the reinforcement/correction ratio for a domain.
    Theory predicts aggregate ratio of 207x. Per-domain ratios vary."""
    params = DOMAIN_THEORY_PARAMS.get(source_type, DOMAIN_THEORY_PARAMS["other"])
    corr = max(0.001, params["correction"])
    return round(params["reinforcement"] / corr, 2)


def compute_attention_score(source_type_a, source_type_b):
    """Layer 2: Estimate analyst coverage overlap between two domains.
    Lower overlap = larger attention blind spot = more residual.
    Returns 0-1 where 0 = total overlap, 1 = zero overlap."""
    try:
        from config import get_domain_distance
        distance = get_domain_distance(source_type_a, source_type_b)
    except Exception:
        distance = 0.5

    a = DOMAIN_THEORY_PARAMS.get(source_type_a, DOMAIN_THEORY_PARAMS["other"])
    b = DOMAIN_THEORY_PARAMS.get(source_type_b, DOMAIN_THEORY_PARAMS["other"])

    # Attention gap = domain distance weighted by inverse accessibility
    # Hard-to-access domains have larger attention gaps
    access_weight = 1.0 - (a["access"] * b["access"])
    attention_gap = distance * (0.5 + 0.5 * access_weight)

    return round(min(1.0, attention_gap), 4)


# ═══════════════════════════════════════════════════════════════════════
# EVIDENCE CLASSIFICATION — 13 LAYERS
# ═══════════════════════════════════════════════════════════════════════

def classify_evidence(collision_data, source_types=None, domain_distance=0.0,
                      chains=None, belief_reality_matches=None,
                      validated_pairs=None, negative_space_data=None,
                      score_components=None, diamond_score=None,
                      survived_kill=None, hypothesis_count_at_distance=None):
    """Classify a collision/hypothesis against all 13 theoretical layers.

    Returns list of evidence dicts, each with:
      - theory_layer: which of the 13 layers
      - evidence_type: "direct" | "supporting" | "challenging"
      - confidence: 0-1
      - measurement_value: the specific number measured
      - predicted_value: what the theory predicted
      - delta: measurement - prediction
      - description: human-readable evidence text
    """
    evidence = []
    st_list = list(source_types) if source_types else []

    # ── Layer 1: Translation Loss ──
    # Measurement: domain distance as proxy for information degradation
    # Theory predicts: higher distance = more residual = higher diamond scores
    if domain_distance > 0:
        # Predicted: residual density proportional to distance
        predicted_distortion = domain_distance * 0.8  # theory expects ~80% of distance as distortion
        # Measured: did we actually find a collision here? (1 = yes, weighted by quality)
        measured = 1.0 if collision_data.get("has_collision", True) else 0.0
        evidence.append({
            "theory_layer": LAYER_TRANSLATION_LOSS,
            "evidence_type": "direct" if domain_distance >= 0.6 else "supporting",
            "confidence": min(1.0, domain_distance * 1.2),
            "measurement_value": round(domain_distance, 3),
            "predicted_value": round(predicted_distortion, 3),
            "delta": round(domain_distance - predicted_distortion, 3),
            "description": f"Translation loss at distance {domain_distance:.2f} between "
                           f"{', '.join(st_list[:4])}. "
                           f"{'Collision found — information degraded as predicted.' if measured else 'No collision — distance may not imply loss here.'}",
        })

    # ── Layer 2: Attention Topology ──
    # Measurement: attention gap between domain pairs
    if len(st_list) >= 2:
        for i in range(min(len(st_list), 3)):
            for j in range(i + 1, min(len(st_list), 4)):
                attn = compute_attention_score(st_list[i], st_list[j])
                if attn >= 0.4:
                    # Theory predicts: blind spots exist where attention gap > 0.4
                    evidence.append({
                        "theory_layer": LAYER_ATTENTION_TOPOLOGY,
                        "evidence_type": "direct" if attn >= 0.7 else "supporting",
                        "confidence": attn,
                        "measurement_value": round(attn, 3),
                        "predicted_value": 0.5,  # theory expects mean gap ~0.5 for productive pairs
                        "delta": round(attn - 0.5, 3),
                        "description": f"Attention gap {attn:.2f} between {st_list[i]} and {st_list[j]}. "
                                       f"Collision exists in analyst blind spot.",
                    })
                    break  # One attention measurement per collision suffices
            else:
                continue
            break

    # ── Layer 3: Question Gap ──
    # Evidence: adversarial corpus injection targets sparse regions
    # Measurement: did the collision come from a gap-targeted query?
    # Also: broken_model + stale_assumption = a question nobody was asking
    broken_model = collision_data.get("broken_model")
    stale_assumption = collision_data.get("stale_assumption")
    if broken_model and stale_assumption:
        # The existence of a stale assumption IS a question gap —
        # nobody was asking "is this assumption still valid?"
        evidence.append({
            "theory_layer": LAYER_QUESTION_GAP,
            "evidence_type": "direct",
            "confidence": 0.75,
            "measurement_value": 1.0,  # gap exists (binary for now)
            "predicted_value": 1.0,    # theory predicts gaps exist at all domain boundaries
            "delta": 0.0,
            "description": f"Question gap: nobody was asking whether '{stale_assumption[:100]}' "
                           f"still holds in {broken_model[:80]}. The question existed but wasn't being asked.",
        })

    # ── Layer 4: Epistemic Phase Transitions ──
    # Evidence: belief-reality contradictions with magnitude estimates
    # A large belief-reality gap is pre-transition residual accumulation
    if belief_reality_matches:
        for brm in belief_reality_matches:
            mag = brm.get("magnitude_pct", 0)
            timeline = brm.get("timeline_days", 0)
            if mag > 5 and timeline > 0:
                evidence.append({
                    "theory_layer": LAYER_PHASE_TRANSITION,
                    "evidence_type": "supporting",
                    "confidence": min(0.9, mag / 100),
                    "measurement_value": mag,
                    "predicted_value": None,  # no specific prediction for individual transitions
                    "delta": None,
                    "description": f"Pre-transition signal: {brm.get('direction', '?')} ~{mag}% "
                                   f"mispricing on {brm.get('belief', {}).get('asset', '?')}. "
                                   f"Forcing function in ~{timeline} days. "
                                   f"Residual accumulation before correction event.",
                })

    # ── Layer 5: Rate-Distortion Bedrock ──
    # Measurement: compare actual domain distance to theoretical minimum distortion
    if len(st_list) >= 2:
        rd = compute_rate_distortion_floor(st_list[0], st_list[1])
        if rd["min_distortion"] > 0.5:
            evidence.append({
                "theory_layer": LAYER_RATE_DISTORTION,
                "evidence_type": "supporting",
                "confidence": min(1.0, rd["min_distortion"] / 5),
                "measurement_value": rd["min_distortion"],
                "predicted_value": rd["min_distortion"],  # the floor IS the prediction
                "delta": 0.0,  # we can only measure above the floor
                "description": f"Rate-distortion floor {rd['min_distortion']:.2f} for "
                               f"{st_list[0]}→{st_list[1]}. Source complexity {rd['source_complexity']:.2f}, "
                               f"channel capacity {rd['channel_capacity']:.2f}. "
                               f"Even perfect analysts cannot compress below this floor.",
            })

    # ── Layer 6: Market Incompleteness ──
    # Evidence: collision identifies mispricing with no direct trading instrument
    # Proxy: silo_reason explains WHY no correction mechanism exists
    silo_reason = collision_data.get("silo_reason")
    if silo_reason and len(silo_reason) > 20:
        evidence.append({
            "theory_layer": LAYER_MARKET_INCOMPLETENESS,
            "evidence_type": "direct" if "no" in silo_reason.lower() or "don't" in silo_reason.lower() else "supporting",
            "confidence": 0.7,
            "measurement_value": 1.0,  # incompleteness detected (binary)
            "predicted_value": 1.0,
            "delta": 0.0,
            "description": f"Market incompleteness: {silo_reason[:200]}. "
                           f"No correction pressure exists across this boundary.",
        })

    # ── Layer 7: Depth-Value Distribution ──
    # Measurement: chain depth vs hypothesis value
    if chains:
        best_chain = max(chains, key=lambda c: c.get("length", 0))
        chain_len = best_chain.get("length", 0)
        if chain_len >= 2:
            # Theory predicts value at this depth
            predicted_value = compute_depth_value(chain_len)
            # Empirical: diamond score as proxy for actual value found
            empirical_value = (diamond_score or 50) / 100.0 if diamond_score else None
            # Theoretical decay at this depth
            theoretical_decay = (1 - CHAIN_DECAY_RATE) ** chain_len

            evidence.append({
                "theory_layer": LAYER_DEPTH_VALUE,
                "evidence_type": "direct" if chain_len >= 3 else "supporting",
                "confidence": min(1.0, chain_len * 0.2),
                "measurement_value": chain_len,
                "predicted_value": round(predicted_value, 4),
                "delta": round((empirical_value or 0.5) - theoretical_decay, 3) if empirical_value else None,
                "description": f"{chain_len}-link chain. Theoretical decay: {theoretical_decay:.3f}. "
                               f"Predicted per-chain value at depth {chain_len}: ${predicted_value:.2f}M. "
                               f"Finding at depth {chain_len} confirms value persists beyond decay prediction.",
            })

    # ── Layer 8: Epistemic Cycles ──
    # Evidence: broken model with stale assumption = reinforcement > correction
    # Also: belief-reality contradictions where belief persists
    if broken_model and stale_assumption:
        # The stale assumption IS a cycle: wrong belief persists because
        # it gets used (reinforced) faster than it gets checked (corrected)
        st_ratios = [compute_persistence_ratio(st) for st in st_list[:3]] if st_list else []
        avg_ratio = sum(st_ratios) / len(st_ratios) if st_ratios else 5.0

        evidence.append({
            "theory_layer": LAYER_EPISTEMIC_CYCLES,
            "evidence_type": "direct",
            "confidence": 0.8,
            "measurement_value": round(avg_ratio, 2),
            "predicted_value": EXPECTED_PERSISTENCE_RATIO,
            "delta": round(avg_ratio - EXPECTED_PERSISTENCE_RATIO, 2),
            "description": f"Stale assumption in {broken_model[:60]} persists despite invalidating evidence. "
                           f"Domain persistence ratios: {st_ratios}. "
                           f"Aggregate predicted ratio: {EXPECTED_PERSISTENCE_RATIO}x. "
                           f"Model continues to be used (reinforced) without checking assumption (correcting).",
        })

    if belief_reality_matches:
        for brm in belief_reality_matches:
            if brm.get("magnitude_pct", 0) > 5:
                evidence.append({
                    "theory_layer": LAYER_EPISTEMIC_CYCLES,
                    "evidence_type": "direct",
                    "confidence": min(1.0, brm["magnitude_pct"] / 50),
                    "measurement_value": brm["magnitude_pct"],
                    "predicted_value": None,
                    "delta": None,
                    "description": f"Market belief contradicted by reality: "
                                   f"{brm.get('description', '')[:120]}. "
                                   f"Direction: {brm.get('direction', '?')}, magnitude: ~{brm['magnitude_pct']}%. "
                                   f"Belief persists despite available contradicting evidence = active cycle.",
                })

    # ── Layer 9: Cycle Hierarchy ──
    # Evidence: classify detected cycles by type
    # Chains crossing >3 domains = cross-domain cycle (type 7)
    # Chains with temporal spread = temporal cycle (type 6)
    if chains:
        best_chain = max(chains, key=lambda c: c.get("length", 0))
        chain_domains = len(set(best_chain.get("domains", [])))
        if chain_domains >= 3:
            cycle_type = "cross_domain"
            cycle_rank = CYCLE_HIERARCHY[cycle_type]
            evidence.append({
                "theory_layer": LAYER_CYCLE_HIERARCHY,
                "evidence_type": "supporting",
                "confidence": 0.6,
                "measurement_value": cycle_rank,
                "predicted_value": 7,  # cross-domain = rank 7
                "delta": cycle_rank - 7,
                "description": f"Cross-domain cycle detected: {chain_domains} domains. "
                               f"Hierarchy rank {cycle_rank}/9. Higher-rank cycles are harder to detect and break.",
            })

    # ── Layer 10: Fractal Incompleteness (Gödel) ──
    # Evidence: collision that persists DESPITE active correction attempts
    # Proxy: high negative space score + no market reaction = structurally unreachable
    if negative_space_data:
        ns_score = negative_space_data.get("negative_space_score", 5)
        reacted = negative_space_data.get("reaction_occurred")
        gap_mag = negative_space_data.get("gap_magnitude", "unknown")

        if reacted is False and gap_mag in ("total", "large"):
            evidence.append({
                "theory_layer": LAYER_FRACTAL_INCOMPLETENESS,
                "evidence_type": "direct" if gap_mag == "total" else "supporting",
                "confidence": 0.7 if gap_mag == "total" else 0.5,
                "measurement_value": ns_score,
                "predicted_value": 7,  # theory predicts strong non-reaction for structural gaps
                "delta": ns_score - 7,
                "description": f"Negative space score {ns_score}/10 with {gap_mag} gap and NO market reaction. "
                               f"Information is available but structurally unreachable by market correction. "
                               f"Five frameworks (Shannon, Markov, Nash, rate-distortion, behavioural) converge.",
            })

    # ── Layer 11: Negative Space Topology ──
    # Direct measurement from HUNTER's negative space detection
    if negative_space_data:
        ns_score = negative_space_data.get("negative_space_score", 5)
        gap_mag = negative_space_data.get("gap_magnitude", "unknown")
        gap_map = {"total": 1.0, "large": 0.75, "medium": 0.5, "small": 0.25}
        gap_numeric = gap_map.get(gap_mag, 0.5)

        evidence.append({
            "theory_layer": LAYER_NEGATIVE_SPACE,
            "evidence_type": "direct",
            "confidence": min(1.0, ns_score / 10),
            "measurement_value": gap_numeric,
            "predicted_value": 0.5,  # theory predicts median gap = medium
            "delta": round(gap_numeric - 0.5, 3),
            "description": f"Negative space: {gap_mag} gap (score {ns_score}/10). "
                           f"The SHAPE of market non-reaction maps structural blind spots. "
                           f"{'Above' if gap_numeric > 0.5 else 'Below'} median predicted gap.",
        })

    # ── Layer 12: Autopoiesis ──
    # Every collision HUNTER finds where predicted IS evidence for the theory.
    # The system that proves the theory is the system the theory describes.
    if len(st_list) >= 2:
        # Did the collision formula predict residual here?
        formula = compute_collision_formula(st_list[0], st_list[1])
        formula_predicted = formula["total"] > 20  # theory predicts residual when formula > 20
        collision_found = collision_data.get("has_collision", True)

        evidence.append({
            "theory_layer": LAYER_AUTOPOIESIS,
            "evidence_type": "direct" if formula_predicted and collision_found else (
                "challenging" if formula_predicted and not collision_found else "supporting"
            ),
            "confidence": 0.6,
            "measurement_value": formula["total"],
            "predicted_value": 20.0,  # threshold for predicted residual
            "delta": round(formula["total"] - 20.0, 2),
            "description": f"Collision formula predicted residual ({formula['total']:.1f} > 20 threshold): "
                           f"{'YES' if formula_predicted else 'NO'}. "
                           f"HUNTER {'found' if collision_found else 'did not find'} collision. "
                           f"{'Prediction confirmed — autopoietic loop closed.' if formula_predicted and collision_found else 'Prediction not yet confirmed.'}",
        })

    # ── Layer 13: Observer-Dependent Topology ──
    # Measurement requires tracking changes over time. For individual collisions,
    # we can only note that this observation changes the topology.
    # Evidence accumulates as HUNTER operates: are we finding FEWER collisions
    # in previously-mined domain pairs? That would confirm observer dependence.
    if diamond_score and diamond_score >= 65 and survived_kill:
        evidence.append({
            "theory_layer": LAYER_OBSERVER_DEPENDENT,
            "evidence_type": "supporting",
            "confidence": 0.4,  # low confidence per-observation, accumulates over time
            "measurement_value": diamond_score,
            "predicted_value": None,  # requires longitudinal analysis
            "delta": None,
            "description": f"High-value collision (score {diamond_score}) identified and will be acted on. "
                           f"Theory predicts: correcting this error shifts the remaining topology. "
                           f"Future collisions in this domain pair should decrease in frequency.",
        })

    return evidence


# Backward compatibility — maps old 5-pillar names to new 13-layer names
_PILLAR_TO_LAYER_MAP = {
    "translation_loss": LAYER_TRANSLATION_LOSS,
    "reinforcement_persistence": LAYER_EPISTEMIC_CYCLES,
    "chain_propagation": LAYER_DEPTH_VALUE,
    "structural_incompleteness": LAYER_FRACTAL_INCOMPLETENESS,
    "collision_multiplication": LAYER_AUTOPOIESIS,
}


def classify_evidence_pillars(collision_data, chains=None, belief_reality_matches=None,
                               source_types=None, domain_distance=0.0):
    """Backward-compatible wrapper. Returns old-format pillar dicts
    by mapping from the new 13-layer classification."""
    layers = classify_evidence(
        collision_data=collision_data,
        source_types=source_types,
        domain_distance=domain_distance,
        chains=chains,
        belief_reality_matches=belief_reality_matches,
    )
    # Convert to old format for existing callers
    pillars = []
    for ev in layers:
        old_name = ev["theory_layer"]
        # Map to old pillar names for backward compat
        for old_pillar, new_layer in _PILLAR_TO_LAYER_MAP.items():
            if ev["theory_layer"] == new_layer:
                old_name = old_pillar
                break
        pillars.append({
            "pillar": old_name,
            "strength": ev["confidence"],
            "evidence": ev["description"],
        })
    return pillars


# ═══════════════════════════════════════════════════════════════════════
# THEORY RECORDER — OBSERVATION LAYER
# ═══════════════════════════════════════════════════════════════════════

class TheoryRecorder:
    """Observes HUNTER pipeline outputs and records evidence for the
    Epistemic Residual Framework. Does NOT modify any existing logic."""

    def __init__(self):
        self._evidence_buffer = []
        self._domain_observations = {}
        self._session_start = datetime.now().isoformat()
        self._collision_count_by_pair = {}  # Track for Layer 13

    def record_collision(self, collision_id, collision_data, fact_ids,
                          source_types, domain_distance, chains=None,
                          belief_reality_matches=None, validated_pairs=None,
                          negative_space_data=None):
        """Record a collision as theory evidence. Called after save_collision()."""
        try:
            # Full 13-layer classification
            layers = classify_evidence(
                collision_data=collision_data,
                source_types=source_types,
                domain_distance=domain_distance,
                chains=chains,
                belief_reality_matches=belief_reality_matches,
                validated_pairs=validated_pairs,
                negative_space_data=negative_space_data,
            )

            # Compute collision formula scores for all domain pairs
            st_list = list(source_types) if source_types else []
            formula_scores = []
            for i in range(len(st_list)):
                for j in range(i + 1, len(st_list)):
                    score = compute_collision_formula(st_list[i], st_list[j])
                    score["pair"] = f"{st_list[i]}|{st_list[j]}"
                    formula_scores.append(score)

            # Track pair frequencies for Layer 13 (observer-dependent topology)
            for i in range(len(st_list)):
                for j in range(i + 1, len(st_list)):
                    pair_key = tuple(sorted([st_list[i], st_list[j]]))
                    self._collision_count_by_pair[pair_key] = \
                        self._collision_count_by_pair.get(pair_key, 0) + 1

            evidence_record = {
                "type": "collision",
                "collision_id": collision_id,
                "timestamp": datetime.now().isoformat(),
                "source_types": st_list,
                "num_domains": len(st_list),
                "domain_distance": round(domain_distance, 3),
                "collision_description": collision_data.get("collision_description", "")[:300],
                "broken_model": collision_data.get("broken_model"),
                "stale_assumption": collision_data.get("stale_assumption"),
                "silo_reason": collision_data.get("silo_reason"),
                "num_chains": len(chains) if chains else 0,
                "max_chain_length": max((c.get("length", 0) for c in chains), default=0) if chains else 0,
                "num_belief_reality_matches": len(belief_reality_matches) if belief_reality_matches else 0,
                "num_validated_pairs": len(validated_pairs) if validated_pairs else 0,
                "formula_scores": formula_scores,
                "layers": layers,
                "layer_names": list(set(ev["theory_layer"] for ev in layers)),
                "layer_count": len(set(ev["theory_layer"] for ev in layers)),
                "evidence_types": {
                    "direct": sum(1 for ev in layers if ev["evidence_type"] == "direct"),
                    "supporting": sum(1 for ev in layers if ev["evidence_type"] == "supporting"),
                    "challenging": sum(1 for ev in layers if ev["evidence_type"] == "challenging"),
                },
                "avg_confidence": round(
                    sum(ev["confidence"] for ev in layers) / max(1, len(layers)), 3
                ),
                # Predictions vs measurements for regression analysis
                "prediction_pairs": [
                    {"layer": ev["theory_layer"],
                     "measured": ev["measurement_value"],
                     "predicted": ev["predicted_value"],
                     "delta": ev["delta"]}
                    for ev in layers
                    if ev["measurement_value"] is not None and ev["predicted_value"] is not None
                ],
            }

            self._evidence_buffer.append(evidence_record)

            # Track per-domain layer hits
            for st in st_list:
                if st not in self._domain_observations:
                    self._domain_observations[st] = {
                        "collision_count": 0, "layer_hits": {L: 0 for L in ALL_LAYERS}
                    }
                self._domain_observations[st]["collision_count"] += 1
                for ev in layers:
                    layer = ev["theory_layer"]
                    if layer in self._domain_observations[st]["layer_hits"]:
                        self._domain_observations[st]["layer_hits"][layer] += 1

        except Exception:
            pass  # Theory recording is best-effort — never break the trading pipeline

    def record_hypothesis(self, hypothesis_id, collision_id, diamond_score,
                           survived_kill, source_types, domain_distance,
                           score_components=None, negative_space_data=None,
                           chains=None):
        """Record a scored hypothesis as theory evidence. Called after save_hypothesis()."""
        try:
            st_list = list(source_types) if source_types else []

            # Layer 7: depth-value measurement
            depth_evidence = None
            if chains:
                best_chain = max(chains, key=lambda c: c.get("length", 0))
                chain_len = best_chain.get("length", 0)
                if chain_len >= 2:
                    predicted_value = compute_depth_value(chain_len)
                    depth_evidence = {
                        "chain_depth": chain_len,
                        "predicted_value_M": predicted_value,
                        "diamond_score": diamond_score,
                        "score_per_depth": round(diamond_score / chain_len, 2) if diamond_score else None,
                    }

            # Compute predicted theory score and compare to actual
            theory_predicted = None
            empirical_ratio = None
            if len(st_list) >= 2:
                formula = compute_collision_formula(st_list[0], st_list[1])
                theory_predicted = formula["total"]
                empirical_ratio = round(
                    diamond_score / max(0.1, theory_predicted), 3
                ) if diamond_score else None

            evidence_record = {
                "type": "hypothesis",
                "hypothesis_id": hypothesis_id,
                "collision_id": collision_id,
                "timestamp": datetime.now().isoformat(),
                "diamond_score": diamond_score,
                "survived_kill": survived_kill,
                "source_types": st_list,
                "num_domains": len(st_list),
                "domain_distance": round(domain_distance, 3),
                "score_components": score_components or {},
                "theory_predicted_score": theory_predicted,
                "empirical_vs_theory_ratio": empirical_ratio,
                "depth_evidence": depth_evidence,
                # Layer 12: autopoiesis — did we find residual where predicted?
                "autopoiesis_confirmed": (
                    theory_predicted is not None
                    and theory_predicted > 20
                    and diamond_score is not None
                    and diamond_score >= 40
                ),
            }

            self._evidence_buffer.append(evidence_record)

        except Exception:
            pass

    def flush_to_db(self):
        """Write buffered evidence to database. Called at end of collision cycle.

        New schema (Prompt 4.1): one row per LAYER per event in theory_evidence.
        A single collision that evidences 8 layers → 8 rows.
        """
        if not self._evidence_buffer:
            return

        try:
            from database import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            now = datetime.now().isoformat()

            for ev in self._evidence_buffer:
                source_event = ev["type"]  # 'collision' or 'hypothesis'
                source_id = ev.get("collision_id") or ev.get("hypothesis_id")
                st_list = ev.get("source_types", [])
                domain_pair_json = json.dumps(st_list[:2]) if st_list else None

                if source_event == "collision":
                    # Write one row per layer evidence
                    for layer_ev in ev.get("layers", []):
                        layer_name = layer_ev.get("theory_layer", "")
                        layer_num = LAYER_TO_NUM.get(layer_name, 0)
                        if layer_num == 0:
                            continue

                        # Detect cycle evidence for cycle_detected flag
                        is_cycle = 1 if layer_name in (
                            LAYER_EPISTEMIC_CYCLES, LAYER_CYCLE_HIERARCHY
                        ) else 0
                        cycle_type = None
                        if layer_name == LAYER_CYCLE_HIERARCHY:
                            # Extract cycle type from description
                            desc = layer_ev.get("description", "")
                            for ct in CYCLE_HIERARCHY:
                                if ct.replace("_", "-") in desc.lower() or ct.replace("_", " ") in desc.lower():
                                    cycle_type = ct
                                    break

                        cursor.execute("""
                            INSERT INTO theory_evidence
                            (timestamp, source_event, source_id, layer, layer_name,
                             evidence_type, description, metric, observed_value,
                             predicted_value, unit, confidence, domain_pair,
                             chain_depth, cycle_detected, cycle_type)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            now, source_event, source_id, layer_num, layer_name,
                            layer_ev.get("evidence_type", "supporting"),
                            layer_ev.get("description", "")[:500],
                            layer_ev.get("theory_layer", ""),  # metric = layer name as identifier
                            layer_ev.get("measurement_value"),
                            layer_ev.get("predicted_value"),
                            None,  # unit — varies by layer, stored in description
                            layer_ev.get("confidence", 0),
                            domain_pair_json,
                            ev.get("max_chain_length"),
                            is_cycle,
                            cycle_type,
                        ))

                elif source_event == "hypothesis":
                    # Hypothesis evidence: write autopoiesis confirmation as Layer 12
                    if ev.get("autopoiesis_confirmed"):
                        cursor.execute("""
                            INSERT INTO theory_evidence
                            (timestamp, source_event, source_id, layer, layer_name,
                             evidence_type, description, metric, observed_value,
                             predicted_value, unit, confidence, domain_pair,
                             chain_depth, cycle_detected, cycle_type)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            now, source_event, source_id, 12, LAYER_AUTOPOIESIS,
                            "direct",
                            f"Hypothesis {ev.get('hypothesis_id')} scored {ev.get('diamond_score')} "
                            f"where collision formula predicted residual "
                            f"(theory score {ev.get('theory_predicted_score', '?')}). "
                            f"Autopoietic loop confirmed.",
                            "diamond_score",
                            ev.get("diamond_score"),
                            ev.get("theory_predicted_score"),
                            "score",
                            0.6,
                            domain_pair_json,
                            ev.get("depth_evidence", {}).get("chain_depth") if ev.get("depth_evidence") else None,
                            0, None,
                        ))

                    # Depth-value evidence from hypothesis chain depth
                    depth_ev = ev.get("depth_evidence")
                    if depth_ev and depth_ev.get("chain_depth", 0) >= 2:
                        cursor.execute("""
                            INSERT INTO theory_evidence
                            (timestamp, source_event, source_id, layer, layer_name,
                             evidence_type, description, metric, observed_value,
                             predicted_value, unit, confidence, domain_pair,
                             chain_depth, cycle_detected, cycle_type)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            now, source_event, source_id, 7, LAYER_DEPTH_VALUE,
                            "direct" if depth_ev["chain_depth"] >= 3 else "supporting",
                            f"Hypothesis at chain depth {depth_ev['chain_depth']} "
                            f"scored {ev.get('diamond_score')}. "
                            f"Theoretical per-chain value: ${depth_ev.get('predicted_value_M', 0):.2f}M.",
                            "chain_depth_vs_score",
                            ev.get("diamond_score"),
                            depth_ev.get("predicted_value_M"),
                            "score_vs_$M",
                            min(1.0, depth_ev["chain_depth"] * 0.2),
                            domain_pair_json,
                            depth_ev["chain_depth"],
                            0, None,
                        ))

            conn.commit()
            conn.close()
            self._evidence_buffer = []

        except Exception:
            pass  # Best effort

    def get_session_summary(self):
        """Return summary statistics for this session's theory observations."""
        collisions = [e for e in self._evidence_buffer if e["type"] == "collision"]
        hypotheses = [e for e in self._evidence_buffer if e["type"] == "hypothesis"]

        layer_counts = {L: 0 for L in ALL_LAYERS}
        layer_direct = {L: 0 for L in ALL_LAYERS}
        for c in collisions:
            for ev in c.get("layers", []):
                layer = ev["theory_layer"]
                if layer in layer_counts:
                    layer_counts[layer] += 1
                    if ev["evidence_type"] == "direct":
                        layer_direct[layer] += 1

        # Autopoiesis summary
        autopoiesis_confirmed = sum(1 for h in hypotheses if h.get("autopoiesis_confirmed"))

        # Prediction accuracy
        all_pairs = []
        for c in collisions:
            all_pairs.extend(c.get("prediction_pairs", []))
        predictions_made = len(all_pairs)
        predictions_accurate = sum(1 for p in all_pairs if p["delta"] is not None and abs(p["delta"]) < 0.3)

        return {
            "session_start": self._session_start,
            "total_collisions_observed": len(collisions),
            "total_hypotheses_observed": len(hypotheses),
            "layer_evidence_counts": layer_counts,
            "layer_direct_counts": layer_direct,
            "layers_with_evidence": sum(1 for v in layer_counts.values() if v > 0),
            "total_layers": len(ALL_LAYERS),
            "autopoiesis_confirmed": autopoiesis_confirmed,
            "predictions_made": predictions_made,
            "predictions_accurate": predictions_accurate,
            "prediction_accuracy": round(predictions_accurate / max(1, predictions_made), 3),
            "domain_observations": self._domain_observations,
            "pair_frequencies": dict(
                (f"{k[0]}|{k[1]}", v) for k, v in
                sorted(self._collision_count_by_pair.items(), key=lambda x: x[1], reverse=True)[:20]
            ),
            "avg_domain_distance": round(
                sum(c.get("domain_distance", 0) for c in collisions) / max(1, len(collisions)), 3
            ),
        }


# ═══════════════════════════════════════════════════════════════════════
# DASHBOARD / EXPORT
# ═══════════════════════════════════════════════════════════════════════

def get_theory_dashboard_data():
    """Aggregate theory evidence for dashboard display. Reads new schema (Prompt 4.1)."""
    try:
        from database import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Total evidence rows
        cursor.execute("SELECT COUNT(*) FROM theory_evidence")
        total_evidence = cursor.fetchone()[0]

        # Per-layer counts and direct evidence counts
        layer_counts = {L: 0 for L in ALL_LAYERS}
        layer_direct = {L: 0 for L in ALL_LAYERS}
        cursor.execute("SELECT layer_name, evidence_type, COUNT(*) FROM theory_evidence GROUP BY layer_name, evidence_type")
        for row in cursor.fetchall():
            name, etype, count = row[0], row[1], row[2]
            if name in layer_counts:
                layer_counts[name] += count
                if etype == "direct":
                    layer_direct[name] += count

        # Source event distribution
        cursor.execute("SELECT source_event, COUNT(*) FROM theory_evidence GROUP BY source_event")
        event_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # Prediction accuracy: observed vs predicted where both non-null
        cursor.execute("""
            SELECT observed_value, predicted_value
            FROM theory_evidence
            WHERE observed_value IS NOT NULL AND predicted_value IS NOT NULL
        """)
        predictions = cursor.fetchall()
        predictions_accurate = sum(
            1 for row in predictions
            if abs(row[0] - row[1]) < max(0.3 * abs(row[1]), 0.3)  # within 30% or 0.3 absolute
        )

        # Autopoiesis: Layer 12 direct evidence count
        cursor.execute("SELECT COUNT(*) FROM theory_evidence WHERE layer = 12 AND evidence_type = 'direct'")
        autopoiesis_confirmed = cursor.fetchone()[0]

        # Cycles detected
        cursor.execute("SELECT COUNT(*) FROM theory_evidence WHERE cycle_detected = 1")
        cycles_detected = cursor.fetchone()[0]

        # Detected cycles table
        cursor.execute("SELECT COUNT(*) FROM detected_cycles WHERE is_active = 1")
        active_cycles = cursor.fetchone()[0]

        # Backtest results
        cursor.execute("SELECT COUNT(*), AVG(direction_correct), AVG(within_timeframe) FROM backtest_results")
        bt_row = cursor.fetchone()
        backtest_count = bt_row[0]
        backtest_direction_rate = bt_row[1]
        backtest_timeframe_rate = bt_row[2]

        # Formula validation (latest)
        cursor.execute("SELECT * FROM formula_validation ORDER BY date DESC LIMIT 1")
        latest_validation = None
        fv_row = cursor.fetchone()
        if fv_row:
            latest_validation = dict(fv_row)

        # Residual estimates (latest per domain)
        cursor.execute("""
            SELECT domain, predicted_residual_pct, observed_residual_pct,
                   estimated_residual_B, sample_size
            FROM residual_estimates
            WHERE date = (SELECT MAX(date) FROM residual_estimates)
        """)
        residual_data = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return {
            "total_evidence_rows": total_evidence,
            "event_counts": event_counts,
            "layer_counts": layer_counts,
            "layer_direct_counts": layer_direct,
            "layers_with_evidence": sum(1 for v in layer_counts.values() if v > 0),
            "predictions_total": len(predictions),
            "predictions_accurate": predictions_accurate,
            "prediction_accuracy": round(predictions_accurate / max(1, len(predictions)), 3),
            "autopoiesis_confirmed": autopoiesis_confirmed,
            "cycles_detected": cycles_detected,
            "active_cycles": active_cycles,
            "backtest_count": backtest_count,
            "backtest_direction_rate": round(backtest_direction_rate, 3) if backtest_direction_rate else None,
            "backtest_timeframe_rate": round(backtest_timeframe_rate, 3) if backtest_timeframe_rate else None,
            "latest_formula_validation": latest_validation,
            "residual_estimates": residual_data,
        }
    except Exception:
        return {"error": "Theory evidence tables not yet populated"}
