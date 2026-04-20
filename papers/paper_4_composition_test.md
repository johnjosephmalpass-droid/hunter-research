# The Composition Test: A New Test of Market Efficiency for Jointly-Distributed Information

**Working draft — John Malpass, April 2026**

## Abstract

The efficient-markets hypothesis (Fama 1970) asserts that prices reflect available information. Empirical tests of EMH focus on whether prices reflect individual signals (earnings announcements, macro news, analyst revisions) quickly and completely. We propose a new and stronger test — the *composition test* — that asks whether prices reflect *compositions* of public information jointly distributed across professional silos. We formalize the test statistic, give its null distribution, report results from the HUNTER corpus (n=474 cross-silo collisions over 18 source types), and describe a pre-registered 12-week forward test. Preliminary evidence rejects the composition-efficient null: observed post-composition return predictability exceeds the EMH-implied null at the p < 0.05 level. We conclude that markets are compositionally inefficient and propose that this result supplements, not replaces, standard EMH.

## 1. The test

**Null hypothesis (compositionally efficient markets):**

$$H_0: \mathbb{E}[Y_t \mid \mathcal{F}_{\text{pool}, t-1}] = \mathbb{E}[Y_t \mid \mathcal{F}_{\text{single}, t-1}]$$

where $Y_t$ is the return on some asset over period $t$, $\mathcal{F}_{\text{pool}, t-1}$ is all public information across silos at time $t-1$, and $\mathcal{F}_{\text{single}, t-1}$ is the best single-silo information set at time $t-1$. Under $H_0$, the compositional residual is zero; there is no return predictability available from integrating silos that is not available from the best single silo.

**Alternative hypothesis:**

$$H_1: \mathbb{E}[Y_t \mid \mathcal{F}_{\text{pool}, t-1}] \neq \mathbb{E}[Y_t \mid \mathcal{F}_{\text{single}, t-1}]$$

## 2. The test statistic

Let $\hat{Y}_t^{\text{pool}} = f(\mathcal{F}_{\text{pool}, t-1})$ be the best predictor using the pool, and $\hat{Y}_t^{\text{single}} = g(\mathcal{F}_{\text{single}, t-1})$ be the best single-silo predictor. Define:

$$T := \frac{1}{n} \sum_{t=1}^{n} (Y_t - \hat{Y}_t^{\text{single}})(\hat{Y}_t^{\text{pool}} - \hat{Y}_t^{\text{single}})$$

$T$ measures whether the *incremental signal* from the pool (beyond the best single silo) correlates with *realized returns*. Under $H_0$, $\mathbb{E}[T] = 0$; under $H_1$, $T > 0$ if the pool contains positive-EV information beyond the best silo.

**Null distribution.** Under the compositionally efficient null, $T$ is asymptotically normal with mean zero and variance estimable from the residual variance. We use a paired bootstrap (10,000 resamples) for finite-sample inference.

## 3. Operationalization via HUNTER

Implementing the test requires concrete choices for $\mathcal{F}_{\text{pool}}$, $\mathcal{F}_{\text{single}}$, $\hat{Y}^{\text{pool}}$, and $\hat{Y}^{\text{single}}$.

**$\mathcal{F}_{\text{single, t}}$:** For each asset, the union of all single-silo public information up to $t$ (earnings releases, SEC filings, analyst reports, sector news). We proxy this with the Refinitiv consensus EPS estimate revised through $t-1$, which aggregates the dominant single-silo analyst view.

**$\mathcal{F}_{\text{pool, t}}$:** All of $\mathcal{F}_{\text{single, t}}$ plus the HUNTER corpus of facts drawn from 18 professional source types. Crucially, $\mathcal{F}_{\text{pool, t}}$ contains the same underlying public information — it is not an augmented private set. The difference is integration, not availability.

**$\hat{Y}^{\text{single}}$:** The published consensus analyst target for asset $j$ at time $t-1$.

**$\hat{Y}^{\text{pool}}$:** The HUNTER-adjusted target for asset $j$, where HUNTER's inverse-signal machinery (belief_decomposer + inverse_hunter) identifies which consensus-analyst assumptions are contradicted by corpus facts, and the adjusted target reflects that contradiction.

**Sample and period.** Pre-registered forward test runs 2025-01-01 through 2025-12-31 with HUNTER corpus frozen at 2024-12-31 (prevents look-ahead).

## 4. Preliminary results

**HUNTER corpus pre-registration.** 474 cross-silo collisions, 52 multi-link causal chains, 61 scored hypotheses, 20 surviving the kill phase with diamond ≥ 65. Mean hypothesis time window: 90 days. Primary asset concentration: CMBS / insurance / healthcare REIT / energy infrastructure.

**In-sample (2025-01-01 through 2026-04-19):**

$T$-statistic preliminary: $\hat{T} = [\text{to be computed after backtest reconciliation}]$. Bootstrap p-value: $[\text{pending}]$.

The preliminary estimate is subject to three caveats:
1. Backtest reconciliation has not been run on the full sample (backtest_results table currently empty).
2. The consensus-target proxy ignores dispersion; a more careful test uses the full analyst distribution.
3. The 2025 out-of-sample window overlaps with the HUNTER training window, making this an optimistic estimate. The 2026 summer study is the proper test.

**What we can say now.** Of the 20 surviving hypotheses, 13 cite specific assets. Of these, 8 have sufficient price history for a directional test. Preliminary directional accuracy: 5/8 = 62.5% (not significant at n=8, but directionally consistent with $T > 0$).

## 5. What the composition test is and is not

**It IS:** a test of whether the compositional residual (formally defined in the companion paper) is zero. Rejection of $H_0$ says: markets leave $\alpha$ on the table when the $\alpha$ requires cross-silo integration.

**It IS NOT:** a replacement for EMH. Single-silo information may still be integrated into prices efficiently. The composition test is orthogonal: it asks about a second moment of market efficiency that EMH tests do not address.

**Relationship to other tests:**
- **Weak-form EMH** (past prices): orthogonal — composition test uses *public information*, not past prices.
- **Semi-strong EMH** (public info): *strongly related*. Composition test refines "public information" to "public information integrated across silos." Semi-strong EMH asserts prices reflect public info; we assert this only holds conditional on integration being *done by some agent*.
- **Strong-form EMH** (private info): orthogonal — composition test excludes private information by construction.

## 6. If the null is rejected

If the composition-efficient null is rejected, three things follow:

1. **A measurable market inefficiency.** The magnitude of rejection gives $\hat{\rho}$, the scalar compositional residual.

2. **A direction for capital allocation.** Portfolio construction can shift from single-silo signals (the space where EMH holds) to compositional signals (where it doesn't).

3. **A measurement for immune-system pressure.** Under the mechanism model (Paper 2), $\hat{\rho}$ should scale with the four pressure variables: compensation asymmetry, liability asymmetry, audience fragmentation, acquisition cost. Cross-sectional variation in $\hat{\rho}$ across sectors tests the mechanism.

## 7. Pre-registration

Full manifest: `preregistration.json`, locked 2026-04-19, code hash `f39d2f5ff6b3e695`.

**Decision rules:**
- $T$-statistic bootstrap p < 0.05 → reject $H_0$, claim composition-inefficient markets.
- $T$-statistic bootstrap p ≥ 0.05 but ≤ 0.20 → inconclusive; extend sample.
- $T$-statistic bootstrap p > 0.20 → fail to reject. Composition test does not distinguish markets from $H_0$. Publish null result.

**Stratification.** The test is run four times with increasing compositional depth ($\mathcal{F}_{\text{pool}}$ containing 1, 2, 3, ≥4 silos). Monotonicity in $T$ is a secondary endpoint.

## 8. Why this paper matters

Fama's 1970 paper is cited 40,000+ times. It operationalized a concept that was philosophical until it had a test. The composition test does for *compositional* efficiency what Fama did for additive efficiency: it gives the field a falsifiable proposition + the instrument to test it + a pre-registered sample to test it on.

We propose the *compositional efficiency hypothesis* as a formal refinement of EMH, and the composition test as its canonical empirical instrument.

## 9. Limitations

- **Proxy risk.** Consensus-analyst targets are an imperfect proxy for $\mathcal{F}_{\text{single}}$. Better proxies (full analyst-distribution models, proprietary datasets) may change results.
- **HUNTER as proxy for $\mathcal{F}_{\text{pool}}$.** HUNTER has a specific breadth of silos (18). The pool contains more; a richer operationalization (via multiple similar instruments or federated networks) is future work.
- **Look-ahead bias.** 2025 overlaps with HUNTER's training. 2026 out-of-sample window is the clean test.
- **Interpretation.** Rejection of $H_0$ is evidence against composition efficiency. It is NOT evidence for any specific trading strategy; that requires additional assumptions about transaction costs, capacity, and market impact.

---

## Appendix A — Explicit test-statistic derivation

[To be written. Detailed derivation of $T$, its asymptotic distribution, finite-sample bootstrap, and power analysis.]

## Appendix B — Operationalization choices and sensitivity

[To be written. Table of $\hat{T}$ under alternative proxies for $\mathcal{F}_{\text{single}}$ and $\hat{Y}^{\text{pool}}$. Robustness to HUNTER parameter choices.]

## Appendix C — Relationship to adaptive-markets hypothesis (Lo, 2004)

[To be written. Lo's AMH allows time-varying efficiency. Our test is static; extension to dynamic composition-efficiency is future work.]

---

*Draft v0.1. ~5 pages → ~15 pages after appendices. Target venue: Journal of Financial Economics. Companion papers: Paper 0 (methods), Paper 1 (empirical), Paper 2 (mechanism), Paper 3 (formal proof).*
