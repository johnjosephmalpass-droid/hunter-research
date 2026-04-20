# HUNTER v2 -- Complete System Architecture

## THE FULL PIPELINE

### Stage 0: Initialization
- `python hunter.py` starts the engine
- Creates all database tables via `init_db()`
- Verifies `ANTHROPIC_API_KEY` from `.env`
- Model: `claude-sonnet-4-20250514`

### Stage 1: Cycle Dispatch (Main Loop)
- Infinite loop, 3-5 second pause between cycles
- `random.random() < INGEST_RATIO (0.85)` decides: 85% INGEST, 15% COLLISION
- Every 50 ingest cycles: prints knowledge base stats
- Every 100 ingest cycles OR 24 hours: runs daily synthesis
- SIGINT/SIGTERM: graceful shutdown after current cycle
- Credit exhaustion (2 consecutive errors): `SystemExit`

---

## INGEST CYCLE

### Source Selection
- Queries TOTAL counts per source_type from raw_facts (all-time)
- Inverse-quadratic weights: `(max_count - count + 1)^2`
- Effect: aggressively pushes underrepresented types (patent, bankruptcy, pharma) toward parity
- 32 search queries across 12 source types (patent: 4, bankruptcy: 3, pharma: 3, academic: 3, sec_filing: 4, regulation: 4, gov_contract: 2, commodity: 1, job_listing: 2, earnings: 2, app_ranking: 1, other: 2)

### Web Search
- `call_with_web_search()` -- Claude API with `web_search_20250305` tool, max_uses=3
- Rate limiting: 45 RPM cap, 25k input tokens/min
- Retry: 3 attempts with exponential backoff (2s, 8s, 32s)
- If results < 100 chars, cycle ends early

### Fact Extraction
- `INGEST_EXTRACT_PROMPT` extracts: title, raw_content, entities, keywords, domain, country, date_of_fact, source_url, obscurity, implications
- Temperature: 0.2, max_tokens: 8192
- Multi-strategy JSON parsing (```json blocks, raw JSON, brace extraction, regex fallback)

### Fact Validation (`validate_fact()`)
1. Content < 20 chars = rejected
2. Bare commodity spot price (price patterns + commodity source + < 30 words) = rejected as "goes stale"
3. Price sanity: price < $0.50 for known commodity = rejected; price > 10x max range = rejected
4. Opinion rejection: no specifics + 2+ opinion phrases = rejected

### Fact Saving
- Dedup: `LOWER(title) + LOWER(source_type)` uniqueness
- Writes to: `raw_facts` table + `fact_entities` junction table
- Stores: obscurity tag + implications array

### Batch Anomaly Detection
- Single API call for all facts in batch
- `BATCH_ANOMALY_DETECT_PROMPT` with calibration (7+ weirdness = analyst stops, 9-10 = contradicts known reality)
- Hard filter: 13 date-noise phrases auto-rejected
- Writes to: `anomalies` table

---

## COLLISION CYCLE

### Anomaly Selection (Priority Scoring)
- Load anomalies from last 7 days, excluding attempted within last 1 hour
- Score each:
  - Base: weirdness_score (1-10)
  - +5 if implications array has 3+ entries
  - +2 if any implications exist
  - +3 if source_type is patent/bankruptcy/pharmaceutical/academic
- Sort descending, take top 3

### Fact Matching (3 Strategies)

**Strategy 1 -- Entity Match:**
- `fact_entities` junction table, exact match on `entity_name_lower`
- Excludes same source_type as anomaly
- Returns up to 50 RANDOM matches (not newest -- random sampling across full database)

**Strategy 2 -- Implication Match:**
- Breaks implication strings into full phrases + bigrams (excluding stop words)
- LIKE search on `raw_facts.implications` column
- Scores by number of matching terms
- Returns up to 50, ordered by match_score
- THIS IS THE KEY INNOVATION -- finds structural bridges between facts with zero shared entities

**Strategy 3 -- Keyword Fallback:**
- LIKE search on keywords, title, raw_content
- Only used if strategies 1+2 found nothing

Results merged and deduplicated by fact ID.

### Entity Resolution
- Claude identifies related entities (parent/subsidiary, competitors, aliases)
- Expands search with related entity names

### Domain Counting
- Counts DISTINCT SOURCE TYPES not domain tags
- "patent" + "bankruptcy" + "regulation" = 3 (genuinely different silos)
- "Finance" + "Economics" domain tags on commodity facts = same silo

### Collision Dedup
- Jaccard overlap >= 50% on fact_ids = skip

### Collision Evaluation
- `COLLISION_EVALUATE_PROMPT` -- must produce SPECIFIC, ACTIONABLE insight
- Not a theme, not a trend -- something someone could trade/buy/sell THIS WEEK
- Top 5 matching facts, capped at 4000 chars

---

## HYPOTHESIS FORMATION

### Pre-Hypothesis Price Verification
- Web search to verify prices/numbers in up to 3 numeric facts
- Corrections appended to facts visible to hypothesis prompt

### Hypothesis Generation
- `HYPOTHESIS_FORM_PROMPT` with north star example embedded
- Demands: information asymmetry not business idea, specific asset, specific catalyst, specific date
- Returns: hypothesis, fact_chain, action_steps, time_window, domains_crossed, observability, structural_or_event

### Front-Page Filter
- 15 hard-coded topics (hormuz, iran, trump tariff, bitcoin crash, etc.)
- 2+ matches = auto-killed, no kill rounds run

---

## KILL PHASE

### 3 Kill Rounds (via web search)

| Round | Type | Purpose |
|-------|------|---------|
| 1 | fact_check | Are underlying facts correct? |
| 2 | competitor | Does someone already do this exact thing? |
| 3 | barrier | Legal, physical, or economic impossibility? |

### Kill Prompt Rules
- "Fact is wrong" requires citing the CORRECT value from reliable source
- "Competitor exists" requires naming SPECIFIC company at SPECIFIC URL
- "Barrier exists" requires naming SPECIFIC barrier with citation
- "Market is efficient" = NEVER valid kill
- Minor date inaccuracies (off by days/weeks) NOT a kill if underlying event happened
- Must ask: "If I correct this error, does the hypothesis still hold?"

### Fatal Flaw Detection (instant death)
Triggered by kill_type="fact_wrong" OR reason containing:
- "fundamentally" + "wrong"/"incorrect"
- "core fact" + "wrong"
- "data is wrong"
- "never happened"
- "does not exist"

### Soft Kill Voting
- Strong non-fatal kill: +1.0 vote
- Moderate kill: +0.5 vote

### Soft Kill Thresholds (by source type count)

| Source Types | Threshold | Steelman? |
|-------------|-----------|-----------|
| 1-2 | 2 votes | No |
| 3 | 3 votes | Yes |
| 4 | 4 votes | Yes |
| 5+ | 99 (unkillable) | Yes |

### Steelman Round
- Triggers: 3+ source types AND no fatal flaw AND 0 < soft_kill_votes < threshold
- Attempts to reframe/narrow hypothesis to address kill concerns
- If saved: replaces hypothesis text, RESETS soft_kill_votes to 0
- If failed: adds killed entry

---

## POST-SURVIVAL

### Financial Refinement
- Triggers: 20 financial keywords (warrant, option, future, short, arbitrage, etc.)
- Step-by-step instrument mechanics check
- Checks: intrinsic value, exercise decisions, sunk cost confusion, trade direction
- If logic wrong: rewrites hypothesis with correct mechanics (doesn't kill)

### Scoring
- 5 dimensions: novelty, feasibility, timing, asymmetry, intersection (0-20 each)
- Domain bonus: +2 (3 types), +5 (4 types), +8 (5+ types)
- Actionability multiplier: 0.7-1.3
- Confidence penalty: 0 to -15

### Market Awareness Check
- Triggers: score >= 60
- Web search for: current price action, published theses, price already moved, unusual volume
- If edge gone: -15 penalty (floor at 20)

### Report Threshold
- score < 65: saved silently, no report
- score >= 65: full structured report written
- score >= 75: deep dive triggered (5-angle validation)

---

## DATABASE SCHEMA

### Core Tables

**raw_facts** -- 2,800+ facts with entities, implications, obscurity tags
**anomalies** -- flagged unusual facts with weirdness scores
**collisions** -- detected multi-fact connections
**hypotheses** -- formed and killed/survived hypotheses
**hypotheses_archive** -- archived old hypotheses
**fact_entities** -- junction table for entity matching
**findings** -- v1 compatibility, also used for 65+ scored hypotheses
**cycle_logs** -- every cycle with status, tokens, duration
**daily_summaries** -- periodic synthesis
**deep_dives** -- detailed investigation of 75+ scores
**knowledge_graph** -- finding connections
**idea_evolutions** -- parent-child finding chains
**cross_refs** -- cross-domain connections
**domain_state** -- per-domain tracking

---

## ALL FILTERS AND CHECKS

1. **Fact content length** -- < 20 chars rejected
2. **Stale spot price** -- bare commodity price quotes rejected
3. **Price sanity** -- < $0.50 or > 10x max rejected
4. **Opinion rejection** -- no specifics + opinion phrases rejected
5. **Fact dedup** -- title + source_type uniqueness
6. **Anomaly date noise** -- 13 phrases filtered
7. **Anomaly cooldown** -- 1 hour between collision attempts
8. **Collision dedup** -- 50% Jaccard overlap
9. **Front-page filter** -- 2+ topic matches auto-kill
10. **Observability** -- prompt-level guidance on analyst visibility
11. **Structural vs event** -- prompt-level guidance, warning in code
12. **Price signal** -- prompt-level: don't form if asset already moved
13. **Pre-hypothesis verification** -- web search on prices/numbers
14. **Kill phase** -- 3 rounds (fact_check, competitor, barrier)
15. **Fatal flaw detection** -- keyword-based instant death
16. **Soft kill voting** -- domain-scaled thresholds
17. **Steelman round** -- reframe attempt for 3+ domain hypotheses
18. **Financial refinement** -- instrument mechanics check
19. **Market awareness** -- edge already priced in check
20. **Report threshold** -- 65 minimum for report
21. **Deep dive threshold** -- 75 minimum for deep investigation
22. **Credit balance detection** -- 2 errors = shutdown
23. **Source diversity balancing** -- inverse-quadratic weighting

---

## CONFIGURATION SUMMARY

| Parameter | Value |
|-----------|-------|
| Model | claude-sonnet-4-20250514 |
| Ingest ratio | 85% ingest / 15% collision |
| Fact lookback | 30 days |
| Anomaly lookback | 7 days |
| Kill rounds | 3 |
| Report threshold | 65 |
| Deep dive threshold | 75 |
| Market awareness trigger | 60 |
| Market awareness penalty | -15 |
| Collision dedup threshold | 50% Jaccard |
| Front-page kill threshold | 2+ topic matches |
| Credit error shutdown | 2 consecutive |
| Source type queries | 32 across 12 types |
| Rate limit | 45 RPM, 25k input tokens/min |
| Retry backoff | 2s, 8s, 32s |
| Inter-cycle pause | 3-5s random |
