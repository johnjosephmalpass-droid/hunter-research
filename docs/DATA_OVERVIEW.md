# HUNTER v1, Complete Data Overview

Every non-trivial table in the frozen corpus, with row counts and what's in it. Read this alongside `schema.md` inside the Zenodo release for column-level detail. This document exists because a first-pass reading of the corpus will naturally notice the headline tables (facts, collisions, hypotheses) and miss roughly half the real output. The instrument is deeper than the headline numbers suggest.

DOI: [10.5281/zenodo.19667567](https://doi.org/10.5281/zenodo.19667567)
Corpus frozen: 2026-03-31 · Code hash locked: 2026-04-19 (`f39d2f5ff6b3e695`)

---

## Ingestion and entity layer

| Table | Rows | What's in it |
|---|---:|---|
| `raw_facts` | 12,030 | Every ingested fact from 18 silos. Each row carries entities, implications for other professional communities, and model-vulnerability fields. |
| `fact_entities` | 30,967 | Normalised entity index mapping mentions to 11,835 canonical entities. Used for exact-match cross-silo lookup. |
| `fact_model_fields` | 6,670 | Tagged fields per fact: methodology, assumption, practitioner community, calibration, disruption channel. The input to the methodology graph. |
| `anomalies` | 1,570 | Facts flagged weirdness ≥ 7 by the anomaly detector. Feed the collision cycle. |
| `expirations` | 606 | Dated future catalysts extracted from facts, patent expirations, regulation effective dates, deadline triggers, executive transitions. The system tracks what's coming due and when. |
| `domain_productivity` | 7,416 | Per-domain per-cycle productivity measurements used by the inverse-quadratic ingestion weighting. |

## Graph layer

| Table | Rows | What's in it |
|---|---:|---|
| `collisions` | 474 | Cross-silo fact collisions, sets of ≥2 facts from structurally independent silos whose joint implication is not implied by any single fact. |
| `held_collisions` | 113 | Collisions held back from immediate processing (failed early gates but flagged for re-review). Research material, not a dead-letter queue. |
| `chains` | 52 | Multi-link causal chains derived from the collision set. Max chain length observed: 7. |
| `causal_edges` | 171 | Directed edges with explicit named transmission pathways. Admitted only if the kill phase verified the pathway. |
| `differential_edge` | 20 | Per-hypothesis differential-edge records: generic-finds probability, pair commonness, entity commonness, strategy novelty, narrative boringness, chain-depth bonus. Operationalises the "why does this specifically survive" measurement. |
| `knowledge_graph` | 12 | High-level graph nodes attached to findings. Per-node: domain, title, summary, keywords, connections. |
| `detected_cycles` | 9 | Closed loops identified by Tarjan SCC over the causal graph under 0.78 semantic merging threshold. Types observed: `cross_domain_3node` (7), `cross_domain_4node` (1), `cross_domain_6node` (1). |
| `kill_failure_topology` | 138 | Per-silo-pair matrix of kill-round success/failure. Used to identify structural-incompleteness candidates. |

## Hypothesis layer

| Table | Rows | What's in it |
|---|---:|---|
| `hypotheses` | 61 | Hypotheses from the **later adversarial-review-upgrade pipeline** run (April 1 – April 4, 2026). 20 survived, 11 scored diamond ≥ 65, 5 scored ≥ 75, 4 scored ≥ 85. Narrative scoring applied to these 61. |
| `hypotheses_archive` | 263 | Hypotheses from the **earlier original-pipeline** run (March 28 – April 3, 2026). Same schema. 84 survived, 28 scored ≥ 65, 13 scored ≥ 75, 9 scored ≥ 85. The bulk of the operator's pre-freeze hypothesis output. Narrative scoring was not applied to this table. |
| `findings` | 45 | Hypotheses (from both tables) with diamond ≥ 65 and additional metadata: title, summary, confidence, domain tag. |
| `narrative_scores` | 61 | Per-hypothesis narrative-structure score (0.0–1.0), computed only for the main `hypotheses` table. Source of the r = −0.49 correlation reported in `docs/pre_freeze_findings_summary.md`. |
| `deep_dives` | 16 | Expanded research packages on selected findings: additional web searches, validation notes, competitor analysis, market size, action plan, final recommendation (PURSUE / HOLD / KILL). The output of a second-pass deep research cycle applied to the top findings. |
| `idea_evolutions` | 5 | Parent-to-child finding evolutions with score delta, how ideas mutated between cycles. |
| `residual_classifications` | 61 | Classifier output labelling each hypothesis by residual type (accidental / self-reinforcing / regulatory / structural / unknown). |

**Hypothesis totals across both tables: 324 with completed adversarial review, 104 survived kill phase, 39 scored diamond ≥ 65, 18 scored ≥ 75, 13 scored ≥ 85.** The 45-row `findings` table includes some entries from additional sources beyond the two hypothesis tables.

## Framework / study infrastructure

| Table | Rows | What's in it |
|---|---:|---|
| `theory_evidence` | 1,155 | Evidence records across 13 framework layers. Used for framework self-audit and auto-detection of drift. |
| `formula_validation` | 2 | Pearson r, Spearman ρ, p-value for the collision-score formula regressed against observed pair counts. |
| `halflife_estimates` | 19 | Per-silo empirical half-life in days. Used to compare against the framework's original 120-day prediction. |
| `measured_domain_params` | 18 | Per-silo measured reinforcement rate, correction rate, persistence ratio. Updates to the hand-calibrated DOMAIN_THEORY_PARAMS. |
| `frontier_test_results` | 12 | Results for the 6 pre-registered frontier hypotheses, measured per run. |
| `negative_inferences` | 423 | Structural gaps detected in the corpus, `chain_lag`, `missing_silo`, `absence_by_inversion`. Each record names what's missing and why that matters. |
| `phase_transition_signals` | 18 | Per-domain signals flagging domains that are accumulating residual faster than average (z-score > threshold). |
| `residual_tam` | 3 | Scenario-based TAM calculations (conservative / central / optimistic). |

## Operations / telemetry

| Table | Rows | What's in it |
|---|---:|---|
| `cycle_logs` | 2,461 | Per-cycle log: which domain, status, tokens used, duration, error message. The primary telemetry source. |
| `daily_summaries` | 10 | Per-day rollups: total cycles, total findings, diamonds found, most promising thread. |
| `overseer_reports` | 5 | Periodic self-assessment reports produced by the overseer module. |
| `domain_state` | 7 | Current rolling state per domain (productivity, deficit, weight). |
| `research_space_snapshots` | 1 | Snapshot of the full research space at one point in time. |

## Not included in the v1 release

These tables are either (a) empty, (b) intentionally withheld, or (c) not yet populated in the pre-freeze state:

- `portfolio_positions`, `portfolio_snapshots`, intentionally withheld. See `docs/LIMITATIONS.md`.
- `prediction_outcomes`, `prediction_audit`, will populate as summer resolutions land on the public board.
- `backtest_results`, `null_runs`, `cycle_outcomes`, `cycle_positions`, `edge_recovery_events`, `market_beliefs`, `inverse_signals`, `residual_estimates`, `decay_tracking`, `theory_run_cycles`, empty at freeze; will populate as summer agents run.
- `targets`, `firm_suggestions`, `overseer_reports`, internal targeting outputs, single-digit rows.

---

## Why this overview exists

A reader skimming the headline table in the README sees "61 hypotheses" and reasonably concludes that's the hypothesis output. It isn't. The hypothesis output is 324 rows across two tables, with an additional 16 deep-dive expansions, 20 differential-edge records, 423 negative-inference gap detections, 606 tracked expirations, 138 kill-failure topology pairs, 12 knowledge-graph nodes, and 1,155 theory-evidence records, all in the public Zenodo release.

The system is deeper than the headline line counts suggest. This file lists the tables so that depth is legible.

For column-level detail on each table, see `schema.md` inside the Zenodo release. For the methodology that produced the data, see `docs/THEORY_CANON.md`. For the limitations and caveats on pre-freeze patterns, see `docs/LIMITATIONS.md` and `docs/pre_freeze_findings_summary.md`.

*John Malpass · University College Dublin · April 2026.*
