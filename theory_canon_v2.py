"""Theory Canon v2 — single source of truth for HUNTER's domain topology.

This file consolidates everything from:
  - HUNTER_Complete_Compendium.pdf
  - HUNTER_Topology_Map.pdf
  - HUNTER_Research_Space_Map.pdf
  - HUNTER_Theoretical_Map.pdf
  - HUNTER_Complete_Framework_v2.pdf

Into one canonical, queryable, code-accessible artefact.

What's in here:
  - The 25 canonical domains with 3-letter codes and all parameters
  - The full 300-pair collision heat map (top pairs with scores)
  - The 2,300 three-domain clusters (top ones)
  - The 12,650 four-domain clusters (top ones)
  - Value vs Difficulty quadrant classification per domain
  - Composite domain rankings
  - Chain vs Cycle decay formulas (calibrated)
  - Translation loss compounding
  - Simulation growth factors per cycle type

Usage:
    from theory_canon_v2 import DOMAINS_25, HEATMAP_PAIRS, TRIPLE_CLUSTERS
    from theory_canon_v2 import score_pair, score_triple, score_quad
    from theory_canon_v2 import chain_value, cycle_value, hierarchy_value
"""

import math
from dataclasses import dataclass, asdict


# ═══════════════════════════════════════════════════════════════════════
# THE 25 CANONICAL DOMAINS (source: HUNTER_Topology_Map.pdf)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Domain:
    code: str              # 3-letter code
    name: str              # human name
    silos: int             # internal compartments
    r_c_ratio: float       # reinforcement/correction ratio
    market_b: float        # addressable market $B
    residual_pct: float    # % of market that's compositional residual
    residual_b: float      # derived: market_b × residual_pct
    access: float          # data accessibility 0-1
    monetization: float    # how easily convertible to $ 0-1

    @property
    def difficulty(self) -> float:
        """Inverse of accessibility, weighted by silo count."""
        return (1 - self.access) * 0.7 + (self.silos / 50) * 0.3

    @property
    def composite_score(self) -> float:
        """Market-weighted opportunity score."""
        return (
            (self.residual_b / 2000) * 0.4 +  # absolute opportunity
            self.monetization * 0.3 +          # convertibility
            self.access * 0.2 +                # accessibility
            math.log1p(self.r_c_ratio) / 4 * 0.1  # persistence
        )


DOMAINS_25 = [
    Domain("FIN", "Financial Markets",              25,  2.0, 55000, 0.03, 1650, 0.85, 0.95),
    Domain("SCI", "Scientific Research",            40, 10.0,  2500, 0.15,  375, 0.70, 0.40),
    Domain("SPT", "Sports Betting",                 12,  0.8,   250, 0.04,   10, 0.90, 0.90),
    Domain("PHA", "Pharma / Drug Discovery",        20, 15.0,  1500, 0.20,  300, 0.55, 0.70),
    Domain("GEO", "Geopolitics / Intelligence",     30, 27.5,   500, 0.25,  125, 0.45, 0.35),
    Domain("SOC", "Social Media / Attention",       15,  7.5,   800, 0.10,   80, 0.75, 0.60),
    Domain("NRG", "Climate / Energy",               20,  9.0,  3000, 0.12,  360, 0.65, 0.55),
    Domain("LAW", "Legal / Regulatory",             25, 13.3,  1000, 0.18,  180, 0.60, 0.50),
    Domain("MFG", "Manufacturing / Supply Chain",   22,  4.4, 14000, 0.06,  840, 0.50, 0.65),
    Domain("EDU", "Education / EdTech",             18, 11.2,   700, 0.15,  105, 0.55, 0.35),
    Domain("CYB", "Cybersecurity",                  20,  5.0,   250, 0.20,   50, 0.60, 0.75),
    Domain("AGR", "Agriculture / Food",             18,  6.7,  5000, 0.08,  400, 0.45, 0.50),
    Domain("RLE", "Real Estate",                    16,  5.8, 12000, 0.05,  600, 0.65, 0.80),
    Domain("LOG", "Transportation / Logistics",     15,  3.0,  8000, 0.05,  400, 0.60, 0.60),
    Domain("TEL", "Telecommunications",             14,  2.1,  1800, 0.06,  108, 0.70, 0.55),
    Domain("MIN", "Mining / Resources",             16,  7.0,  2000, 0.10,  200, 0.50, 0.70),
    Domain("RET", "Retail / Consumer",              18,  2.0,  6000, 0.04,  240, 0.75, 0.70),
    Domain("HLT", "Healthcare Delivery",            22, 11.2,  9000, 0.12, 1080, 0.35, 0.45),
    Domain("DEF", "Aerospace / Defense",            20, 15.0,   800, 0.18,  144, 0.30, 0.40),
    Domain("INS", "Insurance",                      18,  4.4,  6500, 0.07,  455, 0.60, 0.85),
    Domain("CRY", "Crypto / DeFi",                  15,  2.8,  2500, 0.08,  200, 0.90, 0.90),
    Domain("MED", "Media / Entertainment",          14,  3.3,  2500, 0.06,  150, 0.70, 0.55),
    Domain("HRW", "HR / Workforce / Talent",        16,  5.0,   600, 0.12,   72, 0.55, 0.50),
    Domain("GOV", "Government / Public Policy",     28, 25.0, 15000, 0.10, 1500, 0.50, 0.25),
    Domain("BIO", "Biotech / Synthetic Biology",    22, 16.7,   500, 0.25,  125, 0.50, 0.55),
]

DOMAINS_BY_CODE = {d.code: d for d in DOMAINS_25}

TOTAL_MARKET_B = sum(d.market_b for d in DOMAINS_25)          # $151,700B
TOTAL_RESIDUAL_B = sum(d.residual_b for d in DOMAINS_25)      # $9,749B
ANNUAL_FLOW_B = round(TOTAL_RESIDUAL_B * 0.20, 1)             # $1,950B (20% turnover)


# ═══════════════════════════════════════════════════════════════════════
# COLLISION HEAT MAP — top pair scores (source: Compendium Ch.23, Topology Ch.3)
# ═══════════════════════════════════════════════════════════════════════

HEATMAP_PAIRS = [
    ("SCI", "BIO", 100.0, "Breakthrough science enables biotech applications"),
    ("SCI", "PHA",  99.7, "Drug discovery directly depends on scientific breakthroughs"),
    ("PHA", "BIO",  74.2, "Pharma-biotech tight integration"),
    ("GEO", "SOC",  71.2, "Geopolitics drives social media narratives"),
    ("GEO", "GOV",  62.3, "Policy shifts with geopolitical realignment"),
    ("GEO", "LAW",  54.7, "International law shapes geopolitical outcomes"),
    ("SCI", "HLT",  54.1, "Research translates to healthcare delivery"),
    ("GEO", "DEF",  47.9, "Geopolitics determines defense procurement"),
    ("PHA", "HLT",  47.6, "Pharma sold through healthcare channels"),
    ("LAW", "GOV",  46.4, "Legal framework defines government action"),
    ("PHA", "LAW",  45.1, "Pharma subject to deep regulation"),
    ("HLT", "BIO",  42.6, "Biotech therapies hit clinical care"),
    ("SCI", "DEF",  36.3, "Science foundational for defense R&D"),
    ("SCI", "GOV",  36.3, "Science funding is policy-driven"),
    ("PHA", "GOV",  34.2, "Pharma pricing politically sensitive"),
    ("NRG", "GEO",  88.0, "Energy supply determines geopolitics"),
    ("FIN", "CRY",  85.0, "Crypto integrates with traditional finance"),
    ("MFG", "NRG",  78.0, "Manufacturing is energy-intensive"),
    ("LOG", "RET",  76.0, "Logistics efficiency drives retail margins"),
    ("INS", "DEF",  72.0, "Defense creates novel insurance risk"),
    ("RLE", "LOG",  68.0, "Real estate location determines logistics"),
    ("INS", "RLE",  65.0, "Property insurance tightly coupled with RE"),
    ("AGR", "NRG",  62.0, "Agriculture vs biofuel energy tradeoff"),
    ("MIN", "NRG",  60.0, "Mining inputs to energy infrastructure"),
    ("HRW", "EDU",  58.0, "Talent pipeline from education"),
    ("MFG", "LOG",  56.0, "Manufacturing and logistics integrated"),
    ("FIN", "GEO",  54.0, "Capital flows respond to geopolitics"),
    ("NRG", "LAW",  52.0, "Energy deeply regulated"),
    ("AGR", "LAW",  50.0, "Agriculture subsidised and regulated"),
    ("TEL", "CYB",  48.0, "Telecom infrastructure cybersecurity-critical"),
    ("MED", "SOC",  46.0, "Media converges with social platforms"),
    ("RET", "SOC",  44.0, "Retail depends on social attention"),
    ("HLT", "INS",  52.0, "Healthcare-insurance mutually determining"),
    ("LAW", "CYB",  40.0, "Cyber-regulation growing field"),
]


def score_pair(code_a: str, code_b: str) -> float:
    """Lookup or compute collision score for domain pair."""
    if code_a == code_b:
        return 0.0
    key = tuple(sorted([code_a.upper(), code_b.upper()]))
    for a, b, score, _ in HEATMAP_PAIRS:
        if tuple(sorted([a, b])) == key:
            return score
    # Fallback: compute from domain parameters
    da, db = DOMAINS_BY_CODE.get(code_a.upper()), DOMAINS_BY_CODE.get(code_b.upper())
    if not da or not db:
        return 0.0
    return round(
        (da.silos * db.silos) * 0.08
        + math.sqrt(da.r_c_ratio * db.r_c_ratio) * 3.0
        + (1 - da.access) * (1 - db.access) * 30
        + (da.residual_pct * db.residual_pct) * 800,
        1
    )


# ═══════════════════════════════════════════════════════════════════════
# TOP 3-DOMAIN CLUSTERS (source: Topology Map p.4)
# ═══════════════════════════════════════════════════════════════════════

TRIPLE_CLUSTERS = [
    ("SCI", "PHA", "BIO", 91.3,  800),
    ("SCI", "PHA", "HLT", 67.1, 1755),
    ("SCI", "HLT", "BIO", 65.6, 1580),
    ("SCI", "PHA", "GOV", 56.7, 2175),
    ("PHA", "HLT", "BIO", 54.8, 1505),
    ("SCI", "HLT", "GOV", 52.1, 2455),
    ("SCI", "PHA", "LAW", 51.9, 1055),
    ("PHA", "HLT", "LAW", 48.3, 1560),
    ("SCI", "GOV", "HLT", 47.8, 2380),
    ("PHA", "LAW", "HLT", 46.5, 1680),
    ("NRG", "GEO", "GOV", 68.0, 2100),
    ("FIN", "CRY", "LAW", 62.0,  920),
    ("MFG", "NRG", "GEO", 58.0, 3400),
    ("RLE", "LOG", "RET", 54.0, 8100),
    ("INS", "HLT", "PHA", 50.0, 2400),
]


def score_triple(code_a: str, code_b: str, code_c: str) -> float:
    key = tuple(sorted([code_a.upper(), code_b.upper(), code_c.upper()]))
    for a, b, c, score, _ in TRIPLE_CLUSTERS:
        if tuple(sorted([a, b, c])) == key:
            return score
    # Fallback: geometric mean of pair scores
    p1 = score_pair(code_a, code_b)
    p2 = score_pair(code_a, code_c)
    p3 = score_pair(code_b, code_c)
    if p1 == 0 or p2 == 0 or p3 == 0:
        return 0.0
    return round((p1 * p2 * p3) ** (1/3), 1)


# ═══════════════════════════════════════════════════════════════════════
# TOP 4-DOMAIN CLUSTERS
# ═══════════════════════════════════════════════════════════════════════

QUAD_CLUSTERS = [
    ("SCI", "PHA", "HLT", "BIO", 69.7, 1880),
    ("SCI", "PHA", "GOV", "BIO", 59.0, 2300),
    ("SCI", "PHA", "LAW", "BIO", 57.7,  980),
    ("SCI", "PHA", "HLT", "LAW", 54.2, 2130),
    ("PHA", "HLT", "BIO", "LAW", 51.8, 1760),
]


def score_quad(*codes) -> float:
    if len(codes) != 4:
        return 0.0
    key = tuple(sorted([c.upper() for c in codes]))
    for a, b, c, d, score, _ in QUAD_CLUSTERS:
        if tuple(sorted([a, b, c, d])) == key:
            return score
    # Fallback: scale triple by extra-domain factor
    return round(score_triple(codes[0], codes[1], codes[2]) * 0.85, 1)


# ═══════════════════════════════════════════════════════════════════════
# VALUE vs DIFFICULTY QUADRANT
# ═══════════════════════════════════════════════════════════════════════

QUADRANTS = {
    "easy_high":   ["FIN", "RLE", "INS", "CRY", "RET"],
    "hard_high":   ["PHA", "HLT", "MFG", "NRG", "GOV", "AGR"],
    "easy_low":    ["SPT", "SOC", "CYB"],
    "hard_low":    ["GEO", "LAW", "EDU", "DEF", "MIN", "TEL"],
}


def quadrant_of(code: str) -> str:
    code = code.upper()
    for q, codes in QUADRANTS.items():
        if code in codes:
            return q
    return "unclassified"


# ═══════════════════════════════════════════════════════════════════════
# CHAIN vs CYCLE VALUE FORMULAS (source: Compendium Ch.16-17)
# ═══════════════════════════════════════════════════════════════════════

CHAIN_DECAY_RATE = 0.271       # per-depth decay for chains
CYCLE_DECAY_RATE = 0.220       # per-depth decay for cycles
TRANSLATION_LOSS_COEFF = 0.60  # per boundary
DEPTH_VALUE_PEAK = 3           # depth at which hump curve peaks


def chain_value(depth: int, v0: float = 100.0) -> float:
    """V_chain(d) = V_0 × 0.271^d"""
    if depth < 1:
        return 0.0
    return round(v0 * (CHAIN_DECAY_RATE ** (depth - 1)), 4)


def cycle_value(length: int, v0: float = 100.0) -> float:
    """V_cycle(L) = V_0 × 0.220^L × (L-1)!/2
    Factorial growth because cycles of length L have (L-1)!/2 distinct
    directed cycles — so deeper cycles DOMINATE chains."""
    if length < 3:
        return 0.0
    factorial = math.factorial(length - 1) / 2
    return round(v0 * (CYCLE_DECAY_RATE ** length) * factorial, 4)


def cycle_vs_chain_ratio(depth: int) -> float:
    """At which depth does cycle value exceed chain value?"""
    if depth < 3:
        return 0.0
    ch = chain_value(depth)
    cy = cycle_value(depth)
    return round(cy / max(0.001, ch), 2)


def hierarchy_value(levels: int, v0: float = 100.0) -> float:
    """Cycles of cycles amplify. 3-level hierarchy ≈ 67,000x growth."""
    if levels < 1:
        return 0.0
    # Calibrated to simulation: 1-level=1x, 2-level=7.4x, 3-level=67000x
    multipliers = {1: 1.0, 2: 7.4, 3: 67000, 4: 4.5e8, 5: 3e12}
    return round(v0 * multipliers.get(levels, multipliers[5] * (levels - 4)), 2)


def translation_loss(signal_strength: float, n_boundaries: int,
                     loss_coeff: float = TRANSLATION_LOSS_COEFF) -> float:
    """S^final = S × L^N. With L=0.6 and N=3, signal → 21.6% of original."""
    return round(signal_strength * (loss_coeff ** n_boundaries), 4)


# ═══════════════════════════════════════════════════════════════════════
# CYCLE ZOO with growth factors (source: Compendium Ch.21 Simulations)
# ═══════════════════════════════════════════════════════════════════════

CYCLE_ZOO = {
    "simple_3":        {"rank": 1, "structure": "A→B→C→A",        "initial": 100e6, "t100": 5.2e6,   "growth": 0.052,   "difficulty": "easy"},
    "nested":          {"rank": 2, "structure": "Inner feeds outer","initial": 100e6, "t100": 740e6,  "growth": 7.4,     "difficulty": "moderate"},
    "coupled":         {"rank": 3, "structure": "Figure-8",        "initial": 100e6, "t100": 200e6,  "growth": 2.0,     "difficulty": "moderate"},
    "braided":         {"rank": 4, "structure": "Shared edge",     "initial": 100e6, "t100": 300e6,  "growth": 3.0,     "difficulty": "hard"},
    "hierarchical_3x": {"rank": 5, "structure": "Cycles of cycles","initial": 100e6, "t100": 6.7e12, "growth": 67000,   "difficulty": "very_hard"},
    "temporal":        {"rank": 6, "structure": "Periodic",        "initial": 100e6, "t100": 150e6,  "growth": 1.5,     "difficulty": "moderate"},
    "cross_domain":    {"rank": 7, "structure": "Spans domains",   "initial": 100e6, "t100": 16e9,   "growth": 160,     "difficulty": "very_hard"},
    "interference":    {"rank": 8, "structure": "Opposing",        "initial": 100e6, "t100": 2.3e6,  "growth": 0.023,   "difficulty": "extremely_hard"},
    "dormant":         {"rank": 9, "structure": "Crisis-activation","initial": 100e6, "t100": 4.2e9,  "growth": 42.0,    "difficulty": "very_hard"},
}


# ═══════════════════════════════════════════════════════════════════════
# 10 APPLICATION DOMAINS — RANKED BY ROI (source: Research Space Sector D)
# ═══════════════════════════════════════════════════════════════════════

APPLICATIONS_RANKED = [
    {"rank": 1,  "domain": "Financial Markets",    "residual_b": 1650, "cost_yr_m": 1865, "roi_x":  884, "priority": "ACTIVE",    "opportunity": "Cross-silo mispricing"},
    {"rank": 2,  "domain": "Patent Landscape",     "residual_b":  400, "cost_yr_m": 1800, "roi_x":  200, "priority": "HIGH",      "opportunity": "Unpatented combos"},
    {"rank": 3,  "domain": "Drug Repurposing",     "residual_b":  800, "cost_yr_m": 3200, "roi_x":  100, "priority": "HIGH",      "opportunity": "Therapeutic targets"},
    {"rank": 4,  "domain": "Insurance Cross-Line", "residual_b":  455, "cost_yr_m": 1293, "roi_x":  352, "priority": "HIGH",      "opportunity": "Risk signals"},
    {"rank": 5,  "domain": "Real Estate",          "residual_b":  600, "cost_yr_m": 1201, "roi_x":  499, "priority": "MEDIUM",    "opportunity": "Market signals"},
    {"rank": 6,  "domain": "Manufacturing",        "residual_b":  840, "cost_yr_m": 1489, "roi_x":  564, "priority": "MEDIUM",    "opportunity": "Supply disruption"},
    {"rank": 7,  "domain": "Healthcare Delivery",  "residual_b": 1080, "cost_yr_m": 2021, "roi_x":  267, "priority": "MEDIUM",    "opportunity": "Outcome signals"},
    {"rank": 8,  "domain": "Government/Policy",    "residual_b": 1500, "cost_yr_m": 2792, "roi_x":  269, "priority": "LOW",       "opportunity": "Policy blind spots"},
    {"rank": 9,  "domain": "Cybersecurity",        "residual_b":   50, "cost_yr_m": 2086, "roi_x":   24, "priority": "LOW",       "opportunity": "Threat correlation"},
    {"rank": 10, "domain": "Meta-HUNTER",          "residual_b": None, "cost_yr_m": None, "roi_x": None, "priority": "STRATEGIC", "opportunity": "License platform"},
]


# ═══════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════

CANON_SUMMARY = {
    "version": "v2",
    "source_documents": [
        "HUNTER_Complete_Compendium.pdf",
        "HUNTER_Topology_Map.pdf",
        "HUNTER_Research_Space_Map.pdf",
        "HUNTER_Theoretical_Map.pdf",
        "HUNTER_Complete_Framework_v2.pdf",
    ],
    "n_domains": len(DOMAINS_25),
    "n_heatmap_pairs": len(HEATMAP_PAIRS),
    "n_triple_clusters": len(TRIPLE_CLUSTERS),
    "n_quad_clusters": len(QUAD_CLUSTERS),
    "n_cycle_types": len(CYCLE_ZOO),
    "n_applications": len(APPLICATIONS_RANKED),
    "total_market_b": TOTAL_MARKET_B,
    "total_residual_b": TOTAL_RESIDUAL_B,
    "annual_flow_b": ANNUAL_FLOW_B,
}


if __name__ == "__main__":
    import json
    print("\n" + "=" * 70)
    print("  HUNTER THEORY CANON v2 — Summary")
    print("=" * 70)
    for k, v in CANON_SUMMARY.items():
        if isinstance(v, list):
            print(f"  {k}:")
            for item in v:
                print(f"    - {item}")
        else:
            print(f"  {k:<25} {v}")

    print("\n" + "=" * 70)
    print("  Top 10 domains by composite score:")
    print("=" * 70)
    ranked = sorted(DOMAINS_25, key=lambda d: -d.composite_score)
    for i, d in enumerate(ranked[:10], 1):
        print(f"  {i:>2}. {d.code}  {d.name:<35} score={d.composite_score:.3f}  residual=${d.residual_b}B")

    print("\n" + "=" * 70)
    print("  Chain vs Cycle crossover table:")
    print("=" * 70)
    print(f"  {'d':>3} {'chain':>10} {'cycle':>14} {'ratio':>8}")
    for d in range(2, 9):
        ch = chain_value(d)
        cy = cycle_value(d)
        ratio = cycle_vs_chain_ratio(d)
        winner = "CYCLE" if ratio > 1 else "CHAIN"
        print(f"  {d:>3} {ch:>10.4f} {cy:>14.4f} {ratio:>8.2f}x  [{winner}]")

    print("\n" + "=" * 70)
    print("  Cycle Zoo growth factors:")
    print("=" * 70)
    for name, info in sorted(CYCLE_ZOO.items(), key=lambda x: x[1]["rank"]):
        print(f"  [{info['rank']}] {name:<20} {info['growth']:>12.2f}x  ({info['difficulty']})")
