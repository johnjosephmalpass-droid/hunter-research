# What I built, and why I'm putting every prediction on a public ledger

*The HUNTER Ledger · Issue #1 · April 28, 2026*

---

Here is a fact almost nobody has thought through.

If you stood outside any large financial firm, you would see specialists walk past each other all day, never speaking. The patent lawyer is reading USPTO filings. He is very good at it. He does not read 10‑Ks. Why would he? His clients don't care. The insurance actuary is reading NAIC reserve filings and mortality tables. She does not read patent filings. Her models don't use them. The CMBS servicer is reading special‑servicer reports and Trepp data. She does not read OSHA enforcement notices. Her book doesn't include steel mills.

Walking past each other. All day. Good at their jobs. Well paid. Well trained.

And somewhere between them — between the patent office and the insurance reserve and the CMBS servicer and the OSHA investigator — there are facts that, when combined, imply a specific asset is mispriced by a specific amount, correctable on a specific date.

No single person walks through all those rooms. So the facts are public and the implication is private. Only the price ever shows it. And the price is wrong.

That is what I spent the last six months building an instrument to study. It is called HUNTER. Today I am taking it public. This post explains what it is, what it does, what I can honestly claim about it right now, and what I am about to find out — in public — over the next twelve months.

## What it is, in one paragraph

HUNTER is a continuously‑running Python pipeline. It ingests specific, dated facts from eighteen professional financial silos — patent filings, SEC disclosures, NAIC insurance reserves, OSHA enforcement, CMBS delinquency and special‑servicer reports, Federal Register rule changes, commodity inventories, analyst targets, academic preprints, government contracts, academic retractions, pharmaceutical approvals, distressed credit, healthcare REIT filings, job‑listing signals, app‑ranking signals, earnings transcripts, and a catch‑all for obscure professional filings that don't fit the other seventeen. It breaks each fact into entities, implications for other silos, model‑vulnerability fields, and named causal edges. It hunts for anomalies. It cross‑matches anomalous facts against the rest of the corpus using seven parallel strategies. Matches become *collisions* — two facts from independent professional worlds that, together, imply something neither implies alone. Collisions are sent into a multi‑round kill gauntlet that tries to destroy them: fact‑check, competitor‑check, barrier‑check, and — the hardest test — mechanism check, which demands that every causal arrow name the specific database, filing, or workflow through which one silo's output enters the next silo's input. Hypotheses that survive are scored in a fresh context by an adversarial reviewer calibrated against four anchor scores, and anything scoring sixty‑five or higher is posted to a public prediction board with an asset, a direction, and a resolution date. Win or loss, both go on the ledger. Forever.

That is HUNTER. A machine that reads across eighteen professional silos simultaneously and keeps a public, timestamped, falsifiable record of what the integration reveals.

## What I am and am not claiming today

Before I go any further I want to be specific about what I can and cannot say right now, because the research program is pre‑registered and the honesty is the whole point.

**What I can say.** The instrument is real. It is approximately 32,000 lines of Python across sixty‑plus modules, forty‑three database tables, and twenty‑six distinct language‑model prompts defining every pipeline stage. The frozen corpus contains 12,030 facts across eighteen professional silos, references 77 distinct countries, and resolves to 11,835 distinct entities and 30,967 normalised entity‑index entries. The causal graph has 171 directed edges, each with a named transmission pathway. The corpus includes 6,670 model‑field extractions that name the specific methodology or assumption each fact could disrupt, a 153‑pair hand‑calibrated domain distance matrix, 474 cross‑silo collisions, and 52 multi‑link causal chains. The pre‑registration manifest is SHA‑256 locked at hash `f39d2f5ff6b3e695`; the corpus is frozen at 2024‑12‑31 and the code hash is locked as of 2026‑04‑19. The prediction board is live at a public URL, shows zero resolved predictions today, and begins accepting posts from the upgraded summer pipeline starting June 1. A twelve‑week out‑of‑sample study runs June through August. All code ships MIT‑licensed; the corpus ships CC‑BY‑4.0 on Zenodo with a DOI.

**What I cannot say.** I do not have a track record. Zero predictions have resolved. The early empirical signatures on the pre‑frozen corpus — a striking asymmetry between mechanism‑focused and audience‑focused kill rates, a hub‑and‑spoke topology concentrated on a single methodology node (ARGUS Enterprise DCF cap‑rate assumptions), a bimodal distribution of diamond scores, a negative correlation between narrative strength and kill survival (r = −0.49), and nine closed causal cycles detected by Tarjan's algorithm — were produced on a pipeline tier that has since been upgraded, and they are held back as *hypotheses to be tested* under the frozen pre‑registration before I will restate them as findings. I have a framework, I have preliminary signatures, and I have a schedule for testing both. I do not yet have results.

**What I will not say.** Nothing about revolutionary anything. No market‑opportunity numbers. No "HUNTER has found $X in alpha." If you read those phrases anywhere with my name attached, assume it is a misquote.

## Why this is possible now and was not possible in 2019

Reading across eighteen professional silos in the same afternoon is not an information problem. The filings are free. What is expensive is *integration* — holding the vocabulary, databases, and methodological defaults of multiple professional worlds in one head at the same time, long enough to see the cross‑domain implication. No human does this. The specialist is rewarded for depth; the breadth‑seeker is called a dilettante. The system actively selects against the person who would find the compositions.

What changed around 2022–2023 was the first appearance of language models capable of simulating multiple specialist perspectives concurrently with enough fidelity to extract model‑field metadata, name causal arrows, and adversarially review compositional claims across unfamiliar silos. That is the capability HUNTER harnesses. What is new is not the instrument; it is that a single operator can now, for the first time, read every specialist's output in parallel. Whether that produces measurable cross‑silo alpha, and for how long, is an empirical question. The ledger is where I answer it.

## What is actually novel about the methodology

Three components of HUNTER's pipeline, to my knowledge, do not appear in prior published work on financial NLP or structured knowledge graphs.

The first is *implication matching*: every ingested fact carries explicit, extracted claims about which professional communities elsewhere should care about it and why, and cross‑silo collisions are then searched across that implication field rather than across surface keywords. Two facts can collide even when they share no vocabulary at all, so long as their implications overlap in a specific named way.

The second is *model‑field extraction*: each fact is tagged with the specific methodology, assumption, practitioner community, calibration, and disruption channel it could affect. This yields a methodology graph rather than an entity graph — a structure in which the nodes are things like "ARGUS Enterprise DCF cap‑rate assumption" or "NAIC RBC C‑1 calculation" rather than companies.

The third is *differential edge*: causal arrows between facts are only admitted into the graph when the kill phase has verified a specific, named transmission pathway — the actual filing or database or workflow through which the output of one silo becomes an input to another. Arrows without named transmission pathways are rejected. This is what makes the graph usable; it is also what makes the mechanism‑assembly bottleneck empirically testable.

I will write much more about each of these in future posts. For now: if you are a researcher in this space and any of it is prior art I have missed, please email me. I would rather find out now than in review.

## The pre‑registered summer study

From June 1 through August 31, 2026, HUNTER runs a twelve‑week out‑of‑sample study on the frozen corpus. The pre‑registration manifest locks four hypotheses about cross‑silo inference structure. The primary endpoint is a monotonicity test on compositional depth — median realised alpha over SPY total return should be ordered A ≤ B ≤ C ≤ D across strata defined by the number of distinct silos in each hypothesis — with D − A > 0 at p < 0.05 under a 10,000‑resample paired bootstrap. Three null baselines are committed in advance: random‑pair (facts drawn from distinct source types at random), within‑silo (same‑source‑type pairing enforced), and shuffled‑label (source‑type labels shuffled before pipeline execution). Decision rules for replication, partial replication, and refutation are fixed in the manifest. Any drift in code or corpus during the study is automatically flagged and reported in the final paper regardless of outcome.

If the primary endpoint accepts, there is probably a structural source of cross‑silo alpha worth measuring carefully. If it does not, the null is informative: it tells us that automated cross‑silo research instruments do not produce systematically unique findings, and the limits‑to‑arbitrage literature operates in the cross‑silo regime through the standard channels. Either outcome is publishable. I will publish either.

## What this Substack will be

Methodology posts now, findings posts after summer. I will walk through how HUNTER actually extracts model‑field metadata, what the kill‑failure topology looks like across 138 domain pairs where adversarial review systematically succeeds or fails, and why narrative strength is negatively correlated with kill survival in the pre‑frozen corpus (one of several results HUNTER produced that contradicted my own prior). When the first predictions begin resolving in mid‑July I will walk through each one in public, with evidence and URL, win or loss. In September I will publish a full summer report.

The Substack exists because the prediction board exists. Every resolved prediction is a new post. That is the rhythm.

## The caveats, up front, before anyone else says them

I am nineteen years old and in the second year of a BSc Economics at University College Dublin. I am one operator running one instrument. The corpus is small — 12,030 facts is a research prototype, not a production feed. About sixty percent of surviving high‑scoring hypotheses in the pre‑frozen corpus concentrate in the CMBS / insurance / regulatory‑transition domain, which will shape how the results should be read. The hypothesis generator and the adversarial reviewer are both language models, and the steps I have taken to decorrelate them — fresh context, web search, four calibrated anchor scores, three pre‑committed null baselines — reduce but do not eliminate shared‑blindspot risk. Until the summer study is complete and out‑of‑sample, every empirical claim on this Substack is provisional.

None of that changes what I am doing next.

## Come and watch

HUNTER is live. The repository is public at GitHub. The corpus is released with a DOI on Zenodo. The methods paper is going up on SSRN. The methodology brief is a free two‑page PDF. The prediction board is already accepting resolution dates and is empty by design: it fills from June 1 as summer hypotheses clear the upgraded pipeline.

If you think any of this is worth watching, subscribe. You will get methodology posts weekly until June, a live feed of predictions from June onward, and a full summer report in September.

If you think it is nonsense, the ledger is public and you can watch it fail in real time. That is the whole point of putting it there.

If you are a researcher with prior art I have missed, a methodologist who sees a flaw in the design, or a practitioner who thinks one of the pre‑freeze signatures is mis‑specified, please email me. Honest criticism is worth more to me right now than anything else.

The fun part starts now.

---

*John Malpass · University College Dublin · April 2026*

*Repo · Zenodo · SSRN · Prediction board · Methodology brief — all linked on the About page.*
