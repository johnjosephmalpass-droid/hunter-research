---
title: "HUNTER — Methodology Brief"
author: "John Malpass · School of Economics · University College Dublin"
date: "April 2026 · v1.0"
geometry: "margin=0.4in"
documentclass: extarticle
classoption: 8pt
colorlinks: true
---

# HUNTER

**An autonomous research instrument for cross-silo financial inference, with a pre-registered 12-week empirical study and a public prediction ledger.**

*John Malpass · School of Economics · University College Dublin · April 2026*

## Problem

Financial markets are populated by specialists who do not cross-read. A patent attorney reads USPTO filings; she does not read NAIC insurance reserves. A CMBS servicer reads Trepp and special-servicer reports; he does not read Federal Register rule changes. Each silo is publicly documented; none is integrated. The resulting *compositional residual* — the component of mispricing attributable to information that is individually free but jointly requires cross-silo expertise — is not addressed by the standard limits-to-arbitrage apparatus (Grossman-Stiglitz 1980; Shleifer-Vishny 1997), which treats information as a single-agent acquisition cost. HUNTER is an autonomous instrument designed to make this residual empirically measurable.

## Methodology (five components, three novel)

**Implication matching** *(novel).* Each fact carries explicit claims about which professional communities elsewhere should care about it and why. Cross-silo collisions are searched across extracted implication fields rather than surface keywords, permitting collision between facts that share no vocabulary but share a specific named cross-domain implication.

**Model-field extraction** *(novel).* Each fact is tagged with five fields naming the methodology, assumption, practitioner community, calibration, and disruption channel it could affect. This yields a methodology graph rather than an entity graph — nodes are constructs such as "ARGUS Enterprise DCF cap-rate assumption," not companies.

**Differential edge** *(novel).* Causal arrows enter the graph only when the adversarial kill phase verifies a specific, named transmission pathway: the filing, database, or workflow through which the output of one silo becomes an input to another. Arrows without a named pathway are rejected.

**Mechanism-verified kill phase.** Multi-round web-searched review: fact-check, competitor-check, barrier-check, and a mechanism check that demands every causal arrow name its transmission pathway. Survivors are scored in a fresh context by an adversarial reviewer against four calibrated anchors (92, 88, 35, 25) with no memory of the generation step.

**Pre-registration.** Corpus frozen 2024-12-31. Code hash locked 2026-04-19 at SHA-256 `f39d2f5ff6b3e695`. Four hypotheses, three null baselines, fixed decision rules, and explicit prohibitions on post-hoc additions, weight changes, and endpoint swaps committed in `preregistration.json`. Drift during the study is automatically flagged.

## Data (frozen v1 corpus, April 2026)

| Artifact | Count | | Artifact | Count |
|---|---:|---|---|---:|
| Raw facts | 12,030 | | Cross-silo collisions | 474 |
| Professional silos | 18 | | Multi-link causal chains | 52 |
| Distinct countries | 77 | | Directed causal edges (named pathway) | 171 |
| Distinct entities (normalised) | 11,835 | | Hypotheses (adversarial review) | 61 |
| Entity-index entries | 30,967 | | Detected epistemic cycles (Tarjan) | 9 |
| Model-field extractions | 6,670 | | Theory-evidence (13 layers) | 1,155 |

Code base: ~32,000 lines of Python / 60+ modules / 43 DB tables / 26 LLM prompts. Domain distance matrix: 153 hand-calibrated pairs. Three-tier model routing (Opus 4.7 for mechanism and adversarial review; Sonnet 4.5 for extraction; Haiku 4.5 for ingestion).

## Pre-registered summer 2026 hypotheses

**H1 (primary; compositional depth).** Median realised alpha over SPY total return increases monotonically across strata A (1 silo) $\leq$ B (2) $\leq$ C (3) $\leq$ D ($\geq$ 4), with D $-$ A $>$ 0 at p $<$ 0.05 via 10,000-resample paired bootstrap. Reject $\Rightarrow$ null-result paper. **H2 (cycle persistence).** Cycles (reinforcement $\geq$ 0.5) persist uncorrected for $\geq$ 14 days in $\geq$ 2 of 9 detected cycles. **H3 (domain distance).** Cross-silo collisions (distance $\geq$ 0.60) score $\geq$ 10 points higher than within-silo ($<$ 0.30) on average. **H4 (chain depth).** Chain-depth-3 hypotheses outperform chain-depth-1 at Cohen's d $\geq$ 0.3.

**Null baselines (pre-committed):** B1 random-pair · B2 within-silo · B3 shuffled-label.

*Pre-freeze signatures — the mechanism/audience kill asymmetry, hub-and-spoke methodology graph centred on ARGUS cap-rate assumptions, bimodal diamond-score distribution, narrative/survival correlation r = −0.49, and the nine Tarjan cycles — are secondary hypotheses pending summer replication, not findings.*

## Paper programme

**Paper 0 (Methods)** · instrument, pipeline, novel triad, kill-phase design · SSRN Apr 2026. **Paper 2 (Immune Response)** · mechanism for compositional persistence via compensation/liability/audience/acquisition-cost asymmetries · SSRN rolling. **Paper 3 (Non-Zero Residual)** · formal extension of Grossman-Stiglitz under specialisation constraints · SSRN rolling. **Paper 4 (Composition Test)** · test statistic for cross-silo market efficiency with pre-registered finite-sample test · SSRN rolling. **Paper 1 (Empirical)** · summer-study findings and null-baseline comparisons · SSRN Sep 2026.

## Timeline

Apr 28, 2026 launch (repo public, corpus on Zenodo, Paper 0 on SSRN, prediction board live) · Jun 1 – Aug 31, 2026 pre-registered 12-week out-of-sample study · mid-Jul 2026 first resolutions · Sep 2026 Paper 1 on SSRN + full summer report · autumn 2026 – 2027 Papers 2, 3, 4 submissions to peer-reviewed venues.

## Honest limitations

Single operator, single instrument. 61 hypotheses in the pre-freeze corpus is small; summer 2026 targets n $\geq$ 300. Approximately 60% of pre-freeze high-scoring hypotheses concentrate in the CMBS / insurance / regulatory-transition domain. Generator and reviewer share an LLM substrate; decorrelation is attempted via fresh context, web-searched kill rounds, calibrated anchors, and three pre-registered null baselines. Zero predictions resolved as of launch. Operator is a second-year undergraduate; formal statistical methodology in Paper 3 awaits senior-theorist collaboration.

## Artifacts and contact

Repo `github.com/<username>/hunter-research` (MIT code, CC-BY-4.0 data) · Corpus Zenodo DOI (pending) · Methods paper SSRN (pending) · Prediction board `<username>.github.io/hunter-research/` · Pre-registration `preregistration.json` SHA-256 locked. **John Malpass · School of Economics · University College Dublin.** Email on the Zenodo record and the repository README. Critique, prior-art pointers, and replication attempts welcome.
