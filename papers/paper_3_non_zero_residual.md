# Compositional Residual is Bounded Below: A Formal Argument

**Working sketch — John Malpass, April 2026. Flagged for formal-theorist collaboration.**

## Thesis

Define the *compositional residual* as the gap between the best single-silo posterior and the best multi-silo posterior over a state of the world. We argue that under plausible specialization constraints, this residual is strictly bounded away from zero *even in the limit of a fully-informed market*. The bound does not require irrational agents, finite capital, or noise traders. It requires only that no single agent acquires all silos.

This is an extension of Grossman–Stiglitz 1980. Grossman–Stiglitz shows that an equilibrium price cannot fully reveal information if information is costly. We show that *even if every silo's information is costlessly available, the price cannot reflect their composition unless some agent integrates them*, and we give conditions under which no agent does.

## Setup

Let $(\Omega, \mathcal{F}, \mathbb{P})$ be a probability space representing states of the world. Let $\mathcal{S} = \{\mathcal{F}_1, ..., \mathcal{F}_k\}$ be a collection of sub-$\sigma$-algebras of $\mathcal{F}$, each representing a professional *silo*. Let $\mathcal{F}_{\text{pool}} = \sigma(\bigcup_i \mathcal{F}_i)$ be the pooled silo information.

A *single-silo posterior* is the conditional expectation of some target random variable $Y$ (e.g., future asset return) given $\mathcal{F}_i$ for some single $i$. A *compositional posterior* is $\mathbb{E}[Y \mid \mathcal{F}_{\text{pool}}]$.

Define the *compositional residual* as:

$$R := \mathbb{E}[Y \mid \mathcal{F}_{\text{pool}}] - \max_i \mathbb{E}[Y \mid \mathcal{F}_i]$$

and the *scalar residual* as the $L^2$-norm:

$$\rho := \|R\|_{L^2} = \sqrt{\mathbb{E}[R^2]}.$$

The price in a market populated only by single-silo agents reflects (at best) $\max_i \mathbb{E}[Y \mid \mathcal{F}_i]$. The compositional posterior $\mathbb{E}[Y \mid \mathcal{F}_{\text{pool}}]$ is the "correct" price if the market could integrate silos. The gap $R$ is the structurally uncorrectable residual.

## Claim

**Theorem (informal).** If the silos $\mathcal{F}_1, ..., \mathcal{F}_k$ are *jointly informative but marginally weak* — meaning that each individual $\mathcal{F}_i$ contains little information about $Y$ but their join $\mathcal{F}_{\text{pool}}$ contains substantial information — then under any market populated only by single-silo agents, $\rho > \rho^* > 0$ where $\rho^*$ is a constant depending only on the conditional mutual information structure of the silos.

**Why the claim is non-trivial.** Grossman–Stiglitz gives $\rho > 0$ when information is costly. We claim $\rho$ is bounded *below by a constant* even when each silo's information is *freely available*, as long as no agent acquires all silos.

## Sketch of proof (requires formal-theorist refinement)

**Step 1 — Decomposition.** By the tower property:

$$\mathbb{E}[Y \mid \mathcal{F}_{\text{pool}}] = \mathbb{E}[Y \mid \mathcal{F}_i] + \big(\mathbb{E}[Y \mid \mathcal{F}_{\text{pool}}] - \mathbb{E}[Y \mid \mathcal{F}_i]\big)$$

The second term on the right is the *incremental information in the pool beyond silo $i$*. Its $L^2$-norm is bounded below by:

$$\|\mathbb{E}[Y \mid \mathcal{F}_{\text{pool}}] - \mathbb{E}[Y \mid \mathcal{F}_i]\|_{L^2}^2 = \text{Var}(Y \mid \mathcal{F}_i) - \text{Var}(Y \mid \mathcal{F}_{\text{pool}}).$$

The RHS is the *conditional variance gap* between silo $i$ and the pool.

**Step 2 — Jointly-informative assumption.** Assume:

$$\text{Var}(Y \mid \mathcal{F}_{\text{pool}}) \leq \sigma_{\text{low}}^2 \ll \sigma_{\text{high}}^2 \leq \min_i \text{Var}(Y \mid \mathcal{F}_i).$$

In words: the pool is highly informative (low residual variance); each individual silo is weakly informative (high residual variance). This captures the empirical observation that cross-silo compositions are high-value while individual silos are not.

**Step 3 — The bound.** For the single-silo agent optimizing over silo $i$:

$$\rho^2 \geq \|\mathbb{E}[Y \mid \mathcal{F}_{\text{pool}}] - \mathbb{E}[Y \mid \mathcal{F}_i]\|_{L^2}^2 \geq \sigma_{\text{high}}^2 - \sigma_{\text{low}}^2 > 0.$$

**Step 4 — Taking the max.** The market integrates the *best* single-silo posterior: $\max_i \mathbb{E}[Y \mid \mathcal{F}_i]$. But this is bounded by the best-silo residual variance, not the pool's. If even the best individual silo has $\text{Var}(Y \mid \mathcal{F}_i) \geq \sigma_{\text{high}}^2$, the bound holds.

**Step 5 — Specialization constraint.** The assumption we *need* is that no agent in the market has $\sigma(\bigcup_{i \in S} \mathcal{F}_i)$ for any $S$ large enough that $\text{Var}(Y \mid \sigma(\bigcup_{i \in S} \mathcal{F}_i)) < \sigma_{\text{high}}^2$. We call this the *specialization constraint*. It is empirically plausible: it says no single practitioner reads $\geq K$ domains where $K$ is the minimum set needed to compress the pool's information into the low-variance regime.

**Specialization constraint is where the immune-system paper (Paper 2) connects.** The four pressures (compensation, liability, audience, acquisition cost) give a mechanism-level account of *why* the specialization constraint holds in practice.

## Consequences

1. **Market efficiency is silo-dependent.** The EMH-consistent statement of the market is not "prices reflect all information" but "prices reflect the best single-silo posterior." The pool posterior is strictly more informative, and the gap does not close through trade.

2. **Residual is not arbitrable without silo integration.** A trader who sees the pool posterior but has no mechanism to execute against the price cannot close $\rho$. The residual persists until some agent acquires sufficient silos to integrate.

3. **HUNTER operationalizes the integration.** HUNTER is an instrument that reads across silos. When HUNTER produces a compositional claim with diamond-score ≥ 65, it is claiming to have computed a component of $\mathbb{E}[Y \mid \mathcal{F}_{\text{pool}}]$ that no single-silo agent had.

## What's missing from this sketch

I'm an undergraduate; the proof above is informal. Before submission I need:

- **Rigorous measure-theoretic setup.** The σ-algebra machinery needs cleaning.
- **The "jointly-informative assumption" needs empirical calibration.** The HUNTER corpus gives a plausible empirical $\sigma_{\text{high}}^2 / \sigma_{\text{low}}^2$ ratio, but the proof currently assumes it without derivation.
- **The $\max_i$ argument needs care.** Agents may specialize *across* silos in ways the simple max ignores (ensembles of specialists).
- **Connection to rate-distortion.** Shannon rate-distortion gives a natural scalar for the gap; formalizing this could upgrade the bound.
- **A senior co-author.** This is a Journal of Economic Theory or Econometrica-style paper. I need to be co-author with someone who does this kind of proof routinely.

## Target venues (after formal cleanup)

- *Journal of Economic Theory* (best fit)
- *Econometrica*
- *Review of Economic Studies*
- *Quarterly Journal of Economics*

## Companion

This paper provides the *existence* theorem. The immune-system paper (Paper 2) provides the *mechanism* for why the specialization constraint empirically holds. The methods paper (Paper 0) provides the *instrument* for measuring $\rho$ in real markets. The empirical paper (Paper 1) reports $\hat{\rho}$ for financial markets 2024–2026 from the HUNTER corpus.

Together these four papers constitute the foundational sequence of the compositional-alpha research program.

---

*v0.1. ~3 pages → ~12 pages after formalization. Collaborator needed: any formal theorist with measure-theory comfort and working knowledge of Grossman–Stiglitz/rate-distortion. Target: Vayanos (LSE), Biais (TSE), or Hirshleifer (UCI) pending response to outreach.*
