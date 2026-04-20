# HUNTER Cross‑Silo Financial Corpus v1 (frozen April 2026)

**Creator.** John Malpass, School of Economics, University College Dublin.
**Version.** v1.0
**Publication date.** April 2026
**Frozen as of.** 2024‑12‑31 (data); 2026‑04‑19 (code and pre‑registration manifest)
**License.** Creative Commons Attribution 4.0 International (CC‑BY‑4.0)
**Keywords.** compositional alpha · cross‑silo inference · limits to arbitrage · epistemic residual · pre‑registered empirical finance · financial knowledge graph · model‑field extraction · kill‑failure topology · differential edge
**Related identifiers.** Code repository (MIT), SSRN Working Paper 0 (methods), SSRN Working Papers 2–6 (theoretical and empirical extensions, rolling).

## Abstract

The HUNTER Cross‑Silo Financial Corpus v1 is a structured dataset assembled by an autonomous research instrument (HUNTER) designed to measure compositional inference across professional financial silos. The corpus comprises 12,030 dated, source‑linked facts drawn from eighteen professional silos (patent filings, SEC disclosures, NAIC insurance reserves, OSHA enforcement notices, CMBS delinquency and surveillance records, Federal Register rule changes, commodity inventory reports, analyst targets, academic preprints, pharmaceutical approvals, distressed credit, healthcare REIT filings, energy‑infrastructure filings, specialty real estate, government contracts, earnings transcripts, job‑listing signals, app‑ranking signals, and a residual "other" category), covering 77 distinct countries. Each fact is decomposed into normalised entities, cross‑domain implications, model‑vulnerability fields naming the specific methodologies it could disrupt, and named causal edges with explicit transmission pathways. The corpus exposes 11,835 distinct entities and 30,967 entity‑index entries, 6,670 model‑field extractions, 1,570 detected anomalies, 474 cross‑silo collisions, 52 multi‑link causal chains, 171 directed causal edges with named transmission pathways, 61 formed hypotheses with completed adversarial review, and 1,155 theory‑evidence records across 13 framework layers. A pre‑registered twelve‑week out‑of‑sample study (June–August 2026) operates on the frozen corpus; the pre‑registration manifest is SHA‑256 locked at hash `f39d2f5ff6b3e695`. The corpus is released for replication, meta‑analysis, and benchmarking of cross‑silo inference methods.

## Coverage

- **Temporal range.** Facts are dated primary‑source publications; the ingestion window for v1 closed 2024‑12‑31. Post‑freeze facts are quarantined and excluded from the primary analysis and from the v1 release.
- **Source types.** Eighteen professional financial silos, with one additional test‑type source excluded from the primary corpus (see `config.py` for the canonical enumeration).
- **Jurisdictions.** 77 distinct countries; entities include sovereigns, subnational jurisdictions (U.S. states, Canadian provinces), federal agencies, supranational bodies (European Union), public corporations, and professional methodologies (e.g. ARGUS Enterprise DCF, NAIC RBC, Moody's CMBS methodology).
- **Languages.** The frozen v1 corpus is English‑language. Multi‑lingual ingestion (German, Japanese, Chinese, Korean, French) is configured for v2 and runs during the summer 2026 study; multi‑lingual facts are tagged and excluded from v1 primary analysis.

## Schema

The corpus is distributed as a SQLite database plus CSV extracts of each table. The 43 tables are documented in `schema.md` accompanying this release. The principal tables are:

- `raw_facts` — one row per ingested fact, with primary‑source URL, silo classification, date, language, and the raw extracted claim.
- `fact_entities` — 30,967 normalised entity mentions mapped to 11,835 canonical entities across silos.
- `fact_implications` — per‑fact cross‑domain implication statements naming which professional communities are affected and why.
- `fact_model_fields` — 6,670 records naming the specific methodology, assumption, practitioner community, calibration, and disruption channel each fact could affect.
- `causal_edges` — 171 directed edges, each with a named transmission pathway (e.g. "ARGUS Enterprise DCF cap‑rate assumption → CMBS servicer loan file → Morningstar/Intex CMBS Analytics module → bond portfolio manager").
- `chains` — 52 multi‑link causal chains derived from the edge set.
- `collisions` — 474 cross‑silo collision records, each linking two or more facts and naming the shared implication.
- `hypotheses` — 61 formed hypotheses with asset, direction, resolution date, and diamond score.
- `kill_rounds` — full adversarial review records (mechanism, fact‑check, competitor, barrier, market, steelman), including kill type, reviewer reasoning, and outcome.
- `findings` — hypotheses scoring ≥ 65 on the diamond scale.
- `detected_cycles` — 9 closed causal loops identified by Tarjan's strongly connected components algorithm over the causal graph under 0.78 semantic merging threshold.
- `theory_evidence` — 1,155 theory‑evidence pairings across 13 framework layers.
- `narrative_scores`, `kill_failure_topology`, `measured_domain_params`, `portfolio_positions` — analyser outputs supporting the published empirical reports.

## Collection methodology

Facts were ingested by an autonomous pipeline that selects silos by inverse‑quadratic weighting of under‑represented source types, issues targeted web searches for obscure professional filings (rather than generic news), and extracts structured fields via language‑model prompts defined in `prompts.py`. A three‑tier model routing configuration separates critical reasoning (mechanism kill, adversarial review) from standard extraction and high‑volume ingestion. All prompts and routing thresholds are fixed in the pre‑registration manifest. Extraction quality was spot‑checked against primary sources during development; full validation statistics are reported in Paper 0 (methods).

Three pipeline components, to the operator's knowledge, are not documented in prior published work on financial NLP or structured knowledge graphs: (i) *implication matching*, which searches for cross‑silo collisions across extracted implication fields rather than surface keywords; (ii) *model‑field extraction*, which tags each fact with the specific methodology, assumption, practitioner community, calibration, and disruption channel it could affect, yielding a methodology graph rather than an entity graph; and (iii) *differential edge*, which admits causal arrows into the graph only when the kill phase has verified a specific, named transmission pathway.

## Intended uses

The corpus is released to support:

1. Replication of HUNTER's published empirical analyses and extensions to alternative kill‑phase designs.
2. Meta‑analysis of cross‑silo inference in finance and adjacent fields (insurance, regulatory analysis, intellectual‑property economics).
3. Benchmarking of alternative knowledge‑graph construction methods against a structured, methodology‑level financial graph with named transmission pathways.
4. Teaching — the corpus is suitable for graduate‑level coursework on limits to arbitrage, market microstructure, and automated research methodology.

Redistribution, derivation, and commercial use are permitted under CC‑BY‑4.0 with attribution.

## Limitations

Users should read the corpus with six limitations in mind.

**L1 — Single operator.** The corpus is assembled by one researcher using one instrument. Independent replication by a second instrument and operator is required before findings are generalised.

**L2 — Sample size.** 61 hypotheses with completed adversarial review is small. The pre‑registered summer 2026 study targets n ≥ 300 out‑of‑sample adversarial review attempts to strengthen the power of downstream claims.

**L3 — Corpus concentration.** Approximately 60 percent of high‑scoring hypotheses concentrate in the CMBS / insurance / regulatory‑transition domain. Results may apply most robustly to regulatory‑transition finance and less clearly to other domains.

**L4 — Self‑correlation.** The hypothesis generator and the adversarial reviewer are both language models. Decorrelation is attempted via fresh‑context review, four calibrated anchor scores, web‑searched kill rounds, and three pre‑registered null baselines (random‑pair, within‑silo, shuffled‑label), but shared‑blindspot risk cannot be fully excluded. The null baselines bound the residual effect.

**L5 — Temporal concentration.** Facts in v1 are concentrated in the 2024 calendar year of active ingestion; temporal dynamics cannot be tested within v1 alone.

**L6 — Pipeline tier change.** Preliminary empirical observations produced on the pre‑freeze pipeline tier — including the mechanism‑vs‑audience kill asymmetry, the hub‑and‑spoke methodology graph topology, the bimodal diamond‑score distribution, the negative narrative‑survival correlation (r = −0.49), and the nine detected Tarjan cycles — are held back as *hypotheses to be tested* on the frozen corpus under the upgraded three‑tier Opus 4.7 / Sonnet 4.5 / Haiku 4.5 routing during summer 2026. Users should not treat pre‑freeze empirical numbers as established findings until replication is reported.

## Pre‑registration

The pre‑registration manifest (`preregistration.json`) accompanies this release. It contains the frozen fact‑ID hash, the locked code hash (`f39d2f5ff6b3e695`), the four strata definitions (A single‑domain, B two‑domain, C three‑domain, D four‑plus‑domain compositional), the primary endpoint (median portfolio alpha over SPY total return monotonic across strata with D − A > 0 at p < 0.05 via 10,000‑resample paired bootstrap), three null baselines, and fixed decision rules. Any drift in code or corpus during the summer study is automatically flagged and reported in the final paper regardless of outcome.

## Citation

Please cite the corpus as:

> Malpass, J. (2026). *HUNTER Cross‑Silo Financial Corpus v1 (frozen April 2026)* [Data set]. Zenodo. https://doi.org/XXXXXX

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

- Malpass, J. (2026). *HUNTER: An Autonomous Research Instrument for Cross‑Silo Financial Inference* (Working Paper 0). SSRN.
- Malpass, J. (2026). *The Market's Immune Response: A Mechanism for the Persistence of Compositional Mispricing* (Working Paper 2). SSRN.
- Malpass, J. (2026). *The Non‑Zero Compositional Residual* (Working Paper 3). SSRN. *Draft, rolling.*
- Malpass, J. (2026). *The Composition Test: A Test of Market Efficiency for Jointly‑Distributed Information* (Working Paper 4). SSRN. *Pre‑registered summer 2026 empirical results.*

Theoretical extension papers (5 and 6) are released as drafts conditional on summer 2026 replication of their motivating empirical signatures; users are directed to read them as conjectures until that replication is reported.

## Version history

- **v1.0 (April 2026).** First public release. Corpus frozen 2024‑12‑31. 12,030 facts, 18 silos, 171 causal edges. English‑language only. Pre‑registration manifest locked at hash `f39d2f5ff6b3e695`.
- **v2 (planned autumn 2026).** Post‑summer release. Adds multi‑lingual ingestion (DE, JA, ZH, KO, FR). Incorporates summer 2026 out‑of‑sample facts and replication‑phase adversarial review records.

## Contact

John Malpass · University College Dublin · School of Economics.
Contact address: see the corresponding‑author block of the methods paper (SSRN) or the repository README.

Honest critique, replication attempts, and prior‑art pointers are welcome.
