# HUNTER Cross-Silo Financial Corpus v1 (frozen April 2026)

**Creator.** John Malpass, School of Economics, University College Dublin.
**Version.** v1.0
**Publication date.** April 2026
**Frozen as of.** 2024-12-31 (data); 2026-04-19 (code and pre-registration manifest)
**License.** Creative Commons Attribution 4.0 International (CC-BY-4.0)
**Keywords.** compositional alpha · cross-silo inference · limits to arbitrage · epistemic residual · pre-registered empirical finance · financial knowledge graph · model-field extraction · kill-failure topology · differential edge
**Related identifiers.** Code repository (MIT); SSRN Working Paper 0 (methods); further working papers rolling.

## What this is

Big financial firms have specialists who don't cross-read. A patent lawyer reads USPTO filings; she does not read NAIC insurance reserves. A CMBS servicer reads Trepp and special-servicer reports; he does not read Federal Register rule changes. Every silo is free and public. The cross-silo *implication* is private, because no single agent reads them all. Only the price ever reflects the composition, and the price is often wrong.

HUNTER is an autonomous research instrument designed to read across these silos at machine speed and make the resulting *compositional residual* — the part of mispricing attributable to information that is individually free but jointly requires cross-silo expertise — empirically measurable. This dataset is the frozen v1 snapshot of what HUNTER has produced in six months of operation.

## Abstract

The HUNTER Cross-Silo Financial Corpus v1 comprises 12,030 dated, source-linked facts drawn from 18 professional financial silos (patent filings, SEC disclosures, NAIC insurance reserves, OSHA enforcement notices, CMBS delinquency and surveillance records, Federal Register rule changes, commodity inventory reports, analyst targets, academic preprints, pharmaceutical approvals, distressed credit, healthcare REIT filings, energy-infrastructure filings, specialty real estate, government contracts, earnings transcripts, job-listing signals, app-ranking signals, and a residual "other" category), covering 77 distinct countries. Each fact is decomposed into normalised entities, cross-domain implications, model-vulnerability fields naming the specific methodologies it could disrupt, and named causal edges with explicit transmission pathways.

The corpus exposes 11,835 distinct entities and 30,967 entity-index entries, 6,670 model-field extractions, 1,570 detected anomalies, 474 cross-silo collisions, 52 multi-link causal chains, 171 directed causal edges with named transmission pathways, 61 formed hypotheses with completed adversarial review, and 1,155 theory-evidence records across 13 framework layers. A pre-registered 12-week out-of-sample study (June–August 2026) operates on the frozen corpus; the pre-registration manifest is SHA-256 locked at hash `f39d2f5ff6b3e695`. The corpus is released for replication, meta-analysis, and benchmarking of cross-silo inference methods.

## Coverage

- **Temporal range.** Facts are dated primary-source publications; the ingestion window for v1 closed 2024-12-31. Post-freeze facts are quarantined and excluded from v1.
- **Source types.** 18 professional financial silos. One additional test-type source is excluded from the primary corpus. See `config.py` for the canonical list.
- **Jurisdictions.** 77 distinct countries. Entities include sovereigns, subnational jurisdictions (U.S. states, Canadian provinces), federal agencies, supranational bodies (European Union), public corporations, and professional methodologies (e.g. ARGUS Enterprise DCF, NAIC RBC, Moody's CMBS methodology).
- **Languages.** v1 is English-language. Multi-lingual ingestion (German, Japanese, Chinese, Korean, French) is configured for v2 and runs during the summer 2026 study.

## Schema

The corpus ships as a SQLite dump plus CSV extracts. Full schema documentation (43 tables) accompanies the release. The principal tables:

- `raw_facts` — one row per ingested fact, with primary-source URL, silo classification, date, language, raw claim.
- `fact_entities` — 30,967 normalised entity mentions mapped to 11,835 canonical entities.
- `fact_implications` — per-fact cross-domain implication statements (who in other fields should care, and why).
- `fact_model_fields` — 6,670 records naming the methodology, assumption, practitioner community, calibration, and disruption channel each fact could affect.
- `causal_edges` — 171 directed edges with named transmission pathways (e.g. "ARGUS Enterprise DCF cap-rate assumption → CMBS servicer loan file → Morningstar/Intex CMBS Analytics module → bond portfolio manager").
- `chains` — 52 multi-link causal chains derived from the edge set.
- `collisions` — 474 cross-silo collision records, each linking two or more facts and naming the shared implication.
- `hypotheses` — 61 formed hypotheses with asset, direction, resolution date, diamond score.
- `kill_rounds` — full adversarial review records (mechanism, fact-check, competitor, barrier, market, steelman), with kill type, reasoning, and outcome.
- `findings` — hypotheses scoring ≥ 65.
- `detected_cycles` — 9 closed causal loops identified by Tarjan's SCC algorithm over the causal graph under 0.78 semantic merging threshold.
- `theory_evidence` — 1,155 theory-evidence pairings across 13 framework layers.
- `narrative_scores`, `kill_failure_topology`, `measured_domain_params`, `portfolio_positions` — analyser outputs supporting the published empirical reports.

## How the corpus was built

Facts were ingested by an autonomous pipeline that selects silos by inverse-quadratic weighting of under-represented source types, issues targeted web searches for obscure professional filings (rather than generic news), and extracts structured fields via language-model prompts defined in `prompts.py`. A three-tier model routing separates critical reasoning (mechanism kill, adversarial review) from standard extraction and high-volume ingestion. All prompts and routing thresholds are fixed in the pre-registration manifest. Extraction quality was spot-checked against primary sources during development; full validation statistics are in Paper 0 (methods).

Three pipeline components are, to the operator's knowledge, not documented in prior work on financial NLP or structured knowledge graphs: (i) *implication matching*, which searches for cross-silo collisions across extracted implication fields rather than surface keywords; (ii) *model-field extraction*, which tags each fact with its methodology, assumption, practitioner community, calibration, and disruption channel, producing a methodology graph rather than an entity graph; and (iii) *differential edge*, which admits causal arrows into the graph only when the kill phase has verified a specific named transmission pathway.

## What this corpus is useful for

1. **Replication.** Reproducing HUNTER's published empirical analyses or running alternative kill-phase designs against the same frozen facts.
2. **Meta-analysis.** Studying cross-silo inference in finance and adjacent fields (insurance, regulatory analysis, IP economics).
3. **Benchmarking.** Comparing alternative knowledge-graph construction methods against a structured, methodology-level financial graph with named transmission pathways.
4. **Teaching.** Graduate-level courses on limits to arbitrage, market microstructure, and automated research methodology.

Redistribution, derivation, and commercial use are permitted under CC-BY-4.0 with attribution.

## Limitations you should know about before using this

**L1 — Single operator.** One researcher, one instrument. Independent replication by a second instrument and operator is needed before any finding is generalised.

**L2 — Sample size.** 61 hypotheses with completed adversarial review is small. The pre-registered summer 2026 study targets n ≥ 300 out-of-sample review attempts.

**L3 — Corpus concentration.** About 60 percent of high-scoring hypotheses concentrate in CMBS / insurance / regulatory-transition finance. Results may hold most robustly there and less clearly elsewhere.

**L4 — Self-correlation.** The generator and the adversarial reviewer are both language models. Decorrelation is attempted via fresh-context review, four calibrated anchor scores, web-searched kill rounds, and three pre-registered null baselines (random-pair, within-silo, shuffled-label). Shared-blindspot risk is reduced, not eliminated.

**L5 — Temporal concentration.** v1 facts are concentrated in the 2024 calendar year. Temporal dynamics cannot be tested within v1 alone.

**L6 — Pipeline tier change.** Early empirical patterns produced under the pre-freeze pipeline tier — including the mechanism/audience kill asymmetry, the hub-and-spoke methodology graph topology, the bimodal diamond-score distribution, the negative narrative-survival correlation (r = −0.49), and the nine detected Tarjan cycles — are held back as *hypotheses to be tested* on the frozen corpus under the upgraded Opus 4.7 / Sonnet 4.5 / Haiku 4.5 routing during summer 2026. Treat pre-freeze empirical numbers as patterns awaiting replication, not findings.

**L7 — Framework iteration.** The corpus includes outputs from multiple HUNTER framework iterations during development. The `findings` table contains entries from earlier exploratory phases alongside later cross-silo financial inference outputs. Researchers interpreting specific findings should filter by creation date and/or domain to isolate the current-framing subset.

## Pre-registration

The manifest `preregistration.json` ships with this release. It contains the frozen fact-ID hash, the locked code hash (`f39d2f5ff6b3e695`), the four strata definitions (A single-domain, B two-domain, C three-domain, D four-plus-domain compositional), the primary endpoint (median alpha over SPY total return monotonic across strata with D − A > 0 at p < 0.05 via 10,000-resample paired bootstrap), three null baselines, and fixed decision rules. Drift during the summer study is auto-flagged and reported in the final paper regardless of outcome.

## How to cite

> Malpass, J. (2026). *HUNTER Cross-Silo Financial Corpus v1 (frozen April 2026)* [Data set]. Zenodo. https://doi.org/XXXXXX

BibTeX:

```bibtex
@dataset{malpass_2026_hunter_corpus_v1,
  author       = {Malpass, John},
  title        = {{HUNTER Cross-Silo Financial Corpus v1 (frozen April 2026)}},
  year         = 2026,
  publisher    = {Zenodo},
  version      = {v1.0},
  doi          = {10.5281/zenodo.XXXXXX},
  url          = {https://doi.org/10.5281/zenodo.XXXXXX}
}
```

## Related publications

- Malpass, J. (2026). *HUNTER: An Autonomous Research Instrument for Cross-Silo Financial Inference* (Working Paper 0). SSRN.
- Further working papers — on the mechanism-assembly bottleneck, the formal non-zero compositional residual, and the cross-silo composition test — ship through summer and autumn 2026. See the repository README for the current publication pipeline.

## Version history

- **v1.0 (April 2026).** First public release. Corpus frozen 2024-12-31. 12,030 facts, 18 silos, 171 causal edges. English-language only. Pre-registration locked at hash `f39d2f5ff6b3e695`.
- **v2 (planned autumn 2026).** Post-summer release. Adds multi-lingual ingestion (DE, JA, ZH, KO, FR) and summer 2026 out-of-sample facts plus replication-phase adversarial review records.

## Contact

John Malpass · University College Dublin · School of Economics.
Contact address: see the corresponding-author block of the methods paper (SSRN) or the repository README. Honest critique, replication attempts, and prior-art pointers welcome.
