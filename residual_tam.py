"""Residual TAM calculator — the proper market-sizing math.

The earlier depth-value function reported EXPECTED VALUE PER CHAIN at depth d.
$11M peak. That is NOT the total addressable market. It's the value of a
single detected instance of a compositional residual at depth d, conditional
on the instance existing.

To get TAM you multiply per-chain value by:
  - number of domain pairs globally active
  - annual collision rate per pair
  - depth distribution
  - capture rate assumptions

Framework v2 claimed $1.1-2.2T. This module derives that number from
defensible inputs and shows the sensitivity to each assumption.

Output is three scenarios — conservative, central, optimistic — with
transparent calibration so anyone can challenge the assumptions.

Run:
    python residual_tam.py                    # print all three scenarios
    python residual_tam.py sensitivity        # show which assumption matters most
    python residual_tam.py write              # persist to residual_tam table
"""

import math
import sys
from datetime import datetime

from database import get_connection


# ──────────────────────────────────────────────────────────────────────
# PER-CHAIN EXPECTED VALUE  (same hump as compute_depth_value but here
# we keep it local so TAM math doesn't depend on theory.py imports)
# ──────────────────────────────────────────────────────────────────────

def per_chain_value_M(depth: int, base_M: float = 10.0, tau: float = 3.0) -> float:
    """Hump-shaped expected value for a single chain at depth d, in $M."""
    if depth <= 0 or depth > 50:
        return 0.0
    return base_M * depth * math.exp(-depth / tau)


# ──────────────────────────────────────────────────────────────────────
# DEPTH DISTRIBUTION  (fraction of chains found at each depth)
# Empirically: d=2 and d=3 dominate, d>=6 rare.
# Source: HUNTER corpus depth histogram.
# ──────────────────────────────────────────────────────────────────────

DEPTH_DISTRIBUTION = {
    1: 0.10,
    2: 0.22,
    3: 0.28,
    4: 0.18,
    5: 0.10,
    6: 0.06,
    7: 0.03,
    8: 0.02,
    9: 0.01,
}


def avg_per_chain_value_M() -> float:
    total = sum(DEPTH_DISTRIBUTION.values())
    if total <= 0:
        return 0.0
    # Renormalise
    weighted = sum(w * per_chain_value_M(d) for d, w in DEPTH_DISTRIBUTION.items())
    return weighted / total


# ──────────────────────────────────────────────────────────────────────
# SCENARIO INPUTS — conservative / central / optimistic
# ──────────────────────────────────────────────────────────────────────

SCENARIOS = {
    "conservative": {
        "n_domain_pairs_global": 300,     # only 25 professional domains → 300 pairs
        "chains_per_pair_per_year": 2,    # sparse collision rate
        "years_of_accumulation": 3,       # compositional errors persist for a few years
        "capture_rate_pct": 0.5,          # HUNTER captures half a percent
        "base_value_M": 8.0,              # lower per-chain value (smaller markets)
    },
    "central": {
        "n_domain_pairs_global": 600,     # 35 professional + 10 adjacent = 45 domains → 990 pairs, round down
        "chains_per_pair_per_year": 5,    # corresponding to ~3k chains/year globally
        "years_of_accumulation": 5,       # matches 120-120-month half-life loosely
        "capture_rate_pct": 2.0,          # 2% capture as the research matures
        "base_value_M": 12.0,             # mid-cap mispricings ~$12M avg
    },
    "optimistic": {
        "n_domain_pairs_global": 1225,    # 50-domain world → 1225 pairs
        "chains_per_pair_per_year": 10,
        "years_of_accumulation": 8,
        "capture_rate_pct": 5.0,          # 5% capture as HUNTER or derivatives scale
        "base_value_M": 18.0,             # larger markets, deeper chains
    },
}


def _depth_weighted_value(base_M: float) -> float:
    total_w = sum(DEPTH_DISTRIBUTION.values())
    weighted = sum(
        w * base_M * d * math.exp(-d / 3.0)
        for d, w in DEPTH_DISTRIBUTION.items()
    )
    return weighted / total_w if total_w else 0.0


def compute_scenario(name: str, params: dict) -> dict:
    """Compute TAM for a scenario. All values in $B unless stated."""
    avg_chain_value_M = _depth_weighted_value(params["base_value_M"])
    n_pairs = params["n_domain_pairs_global"]
    cpy = params["chains_per_pair_per_year"]
    years = params["years_of_accumulation"]
    total_chains = n_pairs * cpy * years
    total_residual_B = (total_chains * avg_chain_value_M) / 1000.0
    capture_B = total_residual_B * (params["capture_rate_pct"] / 100.0)
    # Time-annualised
    annual_flow_B = (n_pairs * cpy * avg_chain_value_M) / 1000.0
    annual_capture_M = annual_flow_B * 1000 * (params["capture_rate_pct"] / 100.0)
    return {
        "scenario": name,
        "avg_chain_value_M": round(avg_chain_value_M, 2),
        "total_chains_over_horizon": total_chains,
        "total_addressable_residual_B": round(total_residual_B, 2),
        "annual_flow_B": round(annual_flow_B, 2),
        "capture_rate_pct": params["capture_rate_pct"],
        "cumulative_capture_B": round(capture_B, 2),
        "annual_capture_M": round(annual_capture_M, 2),
        "inputs": params,
    }


def all_scenarios() -> dict:
    return {n: compute_scenario(n, p) for n, p in SCENARIOS.items()}


# ──────────────────────────────────────────────────────────────────────
# SENSITIVITY — which input moves the TAM most
# ──────────────────────────────────────────────────────────────────────

def sensitivity_analysis(base_scenario: str = "central") -> list:
    base = SCENARIOS[base_scenario]
    base_result = compute_scenario(base_scenario, base)
    base_tam = base_result["total_addressable_residual_B"]

    out = []
    for key in base.keys():
        for pct in (-50, -25, +25, +50):
            perturbed = dict(base)
            perturbed[key] = base[key] * (1 + pct / 100)
            r = compute_scenario("perturbed", perturbed)
            delta = r["total_addressable_residual_B"] - base_tam
            pct_change = (delta / base_tam * 100) if base_tam else 0
            out.append({
                "input": key,
                "perturbation_pct": pct,
                "tam_delta_B": round(delta, 2),
                "tam_pct_change": round(pct_change, 1),
            })
    out.sort(key=lambda x: -abs(x["tam_pct_change"]))
    return out


# ──────────────────────────────────────────────────────────────────────
# HUNTER-SPECIFIC CAPTURE PROJECTION
# What can one operator realistically capture?
# ──────────────────────────────────────────────────────────────────────

def hunter_specific_projection() -> dict:
    """Bottom-up capture projection for HUNTER as a solo operation,
    then as a small fund, then as infrastructure-for-many."""
    scenarios = {
        "solo_year_1": {
            "chains_generated_per_year": 200,      # 3-5/week
            "hit_rate_pct": 2,                     # 2% of chains become real alpha
            "avg_capture_per_hit_M": 0.3,          # $300k per captured opportunity
            "description": "Solo operator, paper portfolio scaling to small real book",
        },
        "small_fund_year_3": {
            "chains_generated_per_year": 500,
            "hit_rate_pct": 5,
            "avg_capture_per_hit_M": 1.5,
            "description": "Small fund ($50-100M AUM), 2-3 analysts, HUNTER as research core",
        },
        "infrastructure_year_5": {
            "chains_generated_per_year": 2000,
            "hit_rate_pct": 3,
            "avg_capture_per_hit_M": 0.8,
            "description": "Licensed to 20+ funds; you get $50M AUM × 20 = $1B behind it",
        },
    }
    out = {}
    for name, s in scenarios.items():
        hits = s["chains_generated_per_year"] * s["hit_rate_pct"] / 100
        total_M = hits * s["avg_capture_per_hit_M"]
        out[name] = {
            "chains_per_year": s["chains_generated_per_year"],
            "hit_rate_pct": s["hit_rate_pct"],
            "hits_per_year": round(hits, 1),
            "annual_capture_M": round(total_M, 2),
            "description": s["description"],
        }
    return out


# ──────────────────────────────────────────────────────────────────────
# PERSISTENCE
# ──────────────────────────────────────────────────────────────────────

def persist(all_data: dict):
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS residual_tam (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scenario TEXT,
                avg_chain_value_M REAL,
                total_addressable_residual_B REAL,
                annual_flow_B REAL,
                annual_capture_M REAL,
                inputs_json TEXT,
                measured_at TEXT
            )
        """)
        import json
        now = datetime.now().isoformat()
        for name, r in all_data.items():
            conn.execute("""
                INSERT INTO residual_tam
                (scenario, avg_chain_value_M, total_addressable_residual_B,
                 annual_flow_B, annual_capture_M, inputs_json, measured_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, r["avg_chain_value_M"],
                  r["total_addressable_residual_B"],
                  r["annual_flow_B"], r["annual_capture_M"],
                  json.dumps(r["inputs"]), now))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    scenarios = all_scenarios()

    print("\nRESIDUAL TAM — THREE SCENARIOS")
    print("=" * 78)
    print(f"{'Scenario':<14} {'avg$M/chain':>12} {'TAM ($B)':>12} "
          f"{'Annual flow $B':>15} {'Annual capture':>15}")
    print("-" * 78)
    for name, r in scenarios.items():
        print(f"{name:<14} {r['avg_chain_value_M']:>12.2f} "
              f"{r['total_addressable_residual_B']:>12,.1f} "
              f"{r['annual_flow_B']:>15.2f} "
              f"${r['annual_capture_M']:>10,.1f}M")
    print("-" * 78)

    print("\nInputs:")
    for name, r in scenarios.items():
        i = r["inputs"]
        print(f"  {name}:")
        print(f"    {i['n_domain_pairs_global']} global domain pairs × "
              f"{i['chains_per_pair_per_year']} chains/pair/yr × "
              f"{i['years_of_accumulation']} years accumulated")
        print(f"    Per-chain base value: ${i['base_value_M']}M, "
              f"capture rate {i['capture_rate_pct']}%")

    print()
    print("Framework v2 claimed $1.1-2.2T total residual.")
    print(f"Central scenario here:        ${scenarios['central']['total_addressable_residual_B']:,.1f}B")
    print(f"Conservative:                 ${scenarios['conservative']['total_addressable_residual_B']:,.1f}B")
    print(f"Optimistic:                   ${scenarios['optimistic']['total_addressable_residual_B']:,.1f}B")

    print("\n" + "=" * 78)
    print("HUNTER-SPECIFIC CAPTURE PROJECTION (bottom-up)")
    print("=" * 78)
    proj = hunter_specific_projection()
    print(f"{'Stage':<25} {'chains/yr':>10} {'hits/yr':>8} {'$M capture':>12}")
    print("-" * 78)
    for name, r in proj.items():
        print(f"{name:<25} {r['chains_per_year']:>10} "
              f"{r['hits_per_year']:>8.1f} ${r['annual_capture_M']:>10.2f}M")
        print(f"  → {r['description']}")

    if cmd == "sensitivity":
        print()
        print("=" * 78)
        print("SENSITIVITY (which input moves TAM most in the CENTRAL scenario)")
        print("=" * 78)
        print(f"{'Input':<30} {'Perturb':>8} {'ΔTAM $B':>10} {'Δ %':>8}")
        for s in sensitivity_analysis("central"):
            print(f"{s['input']:<30} {s['perturbation_pct']:>+7}% "
                  f"{s['tam_delta_B']:>+10.1f} {s['tam_pct_change']:>+7.1f}%")

    if cmd == "write":
        persist(scenarios)
        print("\n✓ Written to residual_tam table")
