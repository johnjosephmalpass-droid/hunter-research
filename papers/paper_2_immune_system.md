# The Market's Immune Response: A Mechanism for the Persistence of Compositional Mispricing

**Working draft — John Malpass, April 2026**

## Abstract

We propose a formal mechanism for a puzzle implicit in the limits-to-arbitrage literature: why cross-silo information asymmetries persist at a measurable rate despite market participants having strong individual incentives to correct them. We argue that financial markets exhibit *structural immunity* to cross-silo information integration through four selection pressures: (i) compensation structures that reward within-silo depth and penalize outside-lane claims, (ii) liability regimes that make specialists adversarial against un-audited cross-domain evidence, (iii) regulatory and institutional fragmentation that prevents any single agent from accumulating the evidence required, and (iv) cognitive-cost asymmetries in which the marginal cost of reading across silos exceeds the marginal return for any individual practitioner. Taken together, these pressures function analogously to a biological immune system: the market absorbs within-silo information efficiently but actively resists (via social, institutional, and cognitive rejection) the integration of compositional claims. We derive four testable predictions, report three that are already empirically supported in the HUNTER corpus (1,570 anomalies, 474 cross-silo collisions, 61 hypotheses with kill-round outcomes), and pre-register a 12-week study for the remaining prediction.

**Key empirical fact:** Cross-silo hypotheses (≥3 distinct source types) face 1.96× the adversarial kill-round pressure of single-silo hypotheses (1.57 vs 0.80 kills per hypothesis, n=61). This is *not* explained by lower quality: conditional on surviving the kill phase, cross-silo hypotheses score comparably or higher. The asymmetric kill pressure is evidence of an active rejection mechanism, not a selection filter on quality.

---

## 1. The puzzle

The standard limits-to-arbitrage result (Shleifer–Vishny 1997; DeLong–Shleifer–Summers–Waldmann 1990) explains why some mispricings persist even among sophisticated traders: capital is scarce, arbitrageurs face noise-trader risk, and short horizons force them to exit before convergence. This explains the *magnitude* of persistent residual but not its *structural pattern*.

A specific pattern in the HUNTER corpus motivates a sharper question. Of 61 hypotheses that formed from cross-silo collisions, the ones that require integrating information across ≥3 professional silos draw systematically more adversarial kill attempts before surviving. This is not a selection artifact. It is not explained by lower prior quality. It looks like the market — operationalized as the distribution of adversarial web evidence a kill-round surfaces — *responds to* cross-silo claims differently than to within-silo ones.

This paper proposes that difference has a mechanism.

## 2. Related literature

- **Grossman–Stiglitz (1980):** Prices cannot fully reveal information if information is costly; an equilibrium price fully revealing private info destroys the incentive to acquire it.
- **Shleifer–Vishny (1997):** Arbitrageurs face noise-trader risk and capital constraints; limits-to-arbitrage explains persistence.
- **DeLong, Shleifer, Summers, Waldmann (1990):** Noise trader risk can persist in equilibrium.
- **Hong, Stein (1999), Stein (2009):** Slow information diffusion across heterogeneous investors; gradual price adjustment.
- **Kwon, Tang (2022):** Cross-asset information linkages and mispricing.
- **Limitation of prior work:** All treat information acquisition as a single-agent cost decision. None formalize *multi-silo* acquisition where the relevant information is jointly distributed across professional domains whose practitioners systematically do not cross-read.

Our contribution: we formalize the joint-distribution case and show that selection pressures on practitioners function as an active rejection mechanism, not a passive cost.

## 3. The mechanism

Let $\mathcal{D} = \{d_1, ..., d_k\}$ be the set of professional domains (e.g., patent law, CMBS servicing, insurance actuarial science, OSHA enforcement). Each practitioner belongs to exactly one domain. Let $I(d)$ be the information available in domain $d$.

A *composition* is a claim that requires combining $I(d_1) \cap I(d_2) \cap ... \cap I(d_m)$ for $m \geq 2$ distinct domains. A *single-silo claim* is one that requires only $I(d_i)$ for some single $i$.

We model the practitioner as optimizing:

$$U(\text{claim}) = R(\text{claim}) \cdot P(\text{survive}) - C(\text{claim}) - L(\text{wrong})$$

where $R$ is professional reward (bonus, promotion, reputation), $P$ is the probability the claim survives peer scrutiny, $C$ is the cost to produce the claim, and $L$ is the liability/career-damage if wrong.

**Four pressures drive compositional claims to a lower $U$ than within-silo claims, independent of quality:**

### 3.1 Compensation pressure
Within-silo: depth is rewarded (an analyst who knows CMBS servicing deeply gets promoted by the head of fixed income). Cross-silo: breadth is discounted (a researcher making a claim outside their named specialty is viewed as dilettante). Thus $R(\text{composition}) < R(\text{single-silo})$ conditional on equivalent quality.

### 3.2 Liability pressure
Within-silo: errors are *expected* in the population of within-silo claims; the practitioner inherits the baseline error rate. Cross-silo: errors are *exceptional*; the practitioner bears disproportionate blame because "you should have known you were outside your expertise." Thus $L(\text{composition, wrong}) \gg L(\text{single-silo, wrong})$.

### 3.3 Audience pressure
Within-silo claims have an audience that can *verify*. Cross-silo claims have no audience that can verify because no individual listener holds all the required silos. The practitioner must *teach* the listener the missing silos before making the claim, which listeners perceive as condescension or as evidence of weak expertise in the listener's home silo. Thus $P(\text{survive} | \text{composition}) < P(\text{survive} | \text{single-silo})$.

### 3.4 Cost-of-acquisition asymmetry
Within-silo: information acquisition has low marginal cost (the practitioner reads their normal sources). Cross-silo: acquiring the non-native silo requires learning its vocabulary, reputational hierarchy, and data-source idioms. This cost is largely *up-front* (a fixed cost for the first composition) but because practitioners produce compositions infrequently, the fixed cost is never amortized. Thus $C(\text{composition}) \gg C(\text{single-silo})$.

### 3.5 The aggregation
All four pressures push the same direction. The market-level consequence: compositions with equal or higher expected alpha than single-silo claims are systematically under-produced. The residual that remains is *structurally uncorrectable* not because arbitrage is hard (Shleifer–Vishny) but because *no single agent finds it worth producing the claim in the first place*.

## 4. Testable predictions

**P1 (Kill-pressure asymmetry):** Cross-silo hypotheses (≥3 source types) attract more adversarial evidence per unit claim than single-silo hypotheses. Mechanism: audience-pressure (3.3) — there is more "outside the lane" rejection evidence available.
*Status in HUNTER corpus: supported. 1.57 vs 0.80 kills/hypothesis, n=61.*

**P2 (Narrative reversal):** Strong-narrative hypotheses — those with clean protagonist/antagonist/catalyst structure — die MORE often than weak-narrative ones. Mechanism: compositional claims that already have clean narrative are already in circulation, so the residual has been absorbed; weak-narrative survivors are the structurally-uncorrectable core.
*Status in HUNTER corpus: supported. r = −0.49 (narrative strength → kill survival), n=61.*

**P3 (Kill-type asymmetry):** Mechanism-type kills should succeed disproportionately; audience-type kills (competitor, barrier, market-check) should fail disproportionately. Mechanism: the mechanism of a composition is verifiable by any one sufficient expert; the audience is not.
*Status in HUNTER corpus: supported. Mechanism kills: 100% success rate. Competitor / barrier / market-check kills: 0% success rate (n=34 total).*

**P4 (Compensation visibility):** In a within-silo population, highly-cited within-silo authors should be *less* likely to make compositional claims than low-cited authors, even conditional on equivalent cross-silo competence. Mechanism: compensation pressure (3.1) — they have more to lose from outside-lane claims.
*Status: not yet tested. Pre-registered for summer 2026 study.*

## 5. Empirical anatomy of the rejection

The kill-failure topology in the HUNTER corpus maps *which* domain pairs produce rejection-resistant residuals:

| Pair | n hypotheses | Kill failure rate | Interpretation |
|---|---:|---:|---|
| bankruptcy × regulation | 5 | 87.0% | No single professional reads both PACER + Federal Register |
| other × regulation | 9 | 73.0% | Regulatory change × general corporate events |
| cre_credit × energy_infra | 9 | 66.7% | CMBS × grid-interconnection |

These are the empirical locations of structural immunity. Each represents a professional-domain pair where no single practitioner has the incentive + expertise + audience to reliably produce the compositional claim.

## 6. Generalization beyond finance

The four pressures are not specific to financial markets. They are specific to professional-specialization equilibria. We conjecture the mechanism applies in:

- **Medicine** (dermatology × endocrinology misses); (cardiology × rheumatology misses).
- **Law** (IP × antitrust contradictions); (securities × employment law misses).
- **Science** (climatology using assumptions refuted in atmospheric physics).
- **Policy** (EPA × DOE regulatory conflicts).

In each, prices do not exist to resolve disputes, so the immune system is harder to measure. Financial markets are useful as a testbed precisely because they provide a $-denominated resolution mechanism.

## 7. Implications for market efficiency

The efficient-markets hypothesis (Fama 1970) says prices reflect available information. Our mechanism implies a sharper claim: *prices reflect available information conditional on some agent having the incentive to produce the claim that makes the information price-relevant*. When the claim requires cross-silo integration, no such agent exists, and prices do not reflect the information.

We propose this be called the *compositional efficiency hypothesis*: markets are efficient with respect to any information that can be integrated within a single professional silo, and systematically inefficient with respect to information that requires cross-silo integration. The residual is not zero; it is *bounded below* by the expected value of the marginal composition that no single agent finds profitable to produce (see companion paper, "A Non-Zero Residual Proof").

## 8. Limitations

- **Small n.** 61 hypotheses in the current HUNTER corpus. Pre-registered study expands to ~300.
- **Selection in anomalies.** The anomaly detector itself prefers within-domain weirdness. We discuss correction in §A.2.
- **No population of non-HUNTER-generated compositions.** We cannot test the mechanism against compositions generated by humans; a future study with analyst-report decomposition closes this.
- **Mechanism is necessary, not sufficient.** Other mechanisms (Shleifer–Vishny limits, Stein slow diffusion) coexist. We claim compositional immunity *contributes to* persistence, not that it is the sole cause.

## 9. Pre-registration

The summer 2026 study tests P4 and provides out-of-sample tests of P1–P3 at n ≥ 300. Manifest locked at `preregistration.json`; code hash frozen. Decision rules:

- **P1 accepted** if kill-rate ratio (cross / single) > 1.3 with p < 0.05 (binomial test on kill counts).
- **P2 accepted** if Pearson r (narrative_strength → survival) ≤ −0.3 with p < 0.05.
- **P3 accepted** if mechanism kill rate > 2× audience kill rate with p < 0.05.
- **P4 accepted** if within-silo citation count inversely predicts compositional-claim production with p < 0.05 among n ≥ 30 authors.

If ≥ 3 of 4 accept, the mechanism is empirically validated.

---

## A. Appendix — model-field extraction and implication matching as instruments

[To be written. Cites the methods paper (Paper 0). Reports that the 6,670 model-field extractions allow a novel empirical test of P3 because each extraction names the specific methodology that is vulnerable to invalidation.]

## B. Appendix — full kill-failure topology

[138-pair table from kill_failure_topology view. Referenced in §5.]

---

*Draft v0.1. 4 pages → ~12 pages after appendices. Target venue: Review of Financial Studies or Journal of Finance. Companion papers: Paper 0 (methods), Paper 3 (non-zero residual proof), Paper 4 (composition test).*
