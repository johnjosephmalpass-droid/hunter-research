# HUNTER v2 — Fact-Collision Autonomous Opportunity Engine

## Full Technical Specification

---

## 1. WHAT IT IS

HUNTER is an autonomous fact-collision engine that runs continuously on a MacBook, searching the public internet for raw facts from 20+ structured data sources, detecting anomalies in those facts, colliding facts from independent sources to discover non-obvious connections, forming time-bound hypotheses from those collisions, actively trying to destroy each hypothesis, and — only if a hypothesis survives — scoring it on a 100-point Diamond Scale and writing a full report.

It is NOT an idea generator. It does not ask AI to be creative. It asks AI to do three things it is genuinely good at: extract structured facts from messy data, notice when something doesn't add up, and connect specific data points across a dataset too large for any human to hold.

The insight emerges from the collision of facts — it is discovered, not generated.

---

## 2. ARCHITECTURE

### Core Pipeline

```
INGEST → EXTRACT → ANOMALY DETECT → COLLISION → ENTITY RESOLVE → HYPOTHESIS → KILL → SCORE → REPORT → DEEP DIVE
```

### Two Cycle Types

| Mode | Frequency | Purpose |
|------|-----------|---------|
| **INGEST** | 70% of cycles | Search web, extract facts, detect anomalies, save to database |
| **COLLISION** | 30% of cycles | Collide anomalies with facts from different sources, form and kill hypotheses |

### Cycle Selection
Each cycle, `random.random() < 0.7` determines INGEST vs COLLISION. This is not deterministic — it's stochastic to prevent predictable patterns.

---

## 3. THE INGEST CYCLE

### Phase 1: Source Selection
- **Weighted random selection** from 20 data source queries
- Sources that have been used LESS in the last 24 hours get higher weight (inverse frequency weighting)
- Prevents any single source type from dominating the fact database

### Phase 2: Web Search
- Uses Claude Sonnet's `web_search` tool (max 3 searches per call)
- Estimated input token budget: 25,000 per web search call
- Smart rate limiting tracks actual token usage and only pauses when approaching 30k/min limit

### Phase 3: Fact Extraction
- Single Claude call extracts ALL discrete, verifiable facts from search results
- Facts must be specific, dated claims — not opinions, trends, or predictions
- Each fact includes: title, raw content, entities (array), keywords, domain, country, date, source URL

### Phase 4: Fact Deduplication
- Before saving, checks if a fact with the same title AND source type already exists (case-insensitive)
- Duplicate facts return None and are skipped
- Prevents database pollution from repeated searches

### Phase 5: Entity Indexing
- Each fact's entities are saved to a normalized `fact_entities` junction table
- Enables exact-match entity search across the entire fact database
- No more LIKE '%meta%' matching "metadata" — proper entity resolution

### Phase 6: Batch Anomaly Detection
- ALL facts from a single ingest cycle are sent in ONE Claude call (not N separate calls)
- Claude evaluates each fact and flags genuinely anomalous ones
- Hard code-level filter rejects date-based false positives (12 noise phrases checked)
- Anomaly calibration: 7+ weirdness = analyst should investigate, 9-10 = contradicts known reality
- Target: <20% of facts should be flagged as anomalous

### Data Sources (20 queries across 11 types)

| Type | Queries | Icon |
|------|---------|------|
| patent | Expired patents this month | 📜 |
| sec_filing | 8-K filings, IPOs, data breaches, M&A | 📊 |
| government_contract | Awarded contracts, cancelled contracts | 🏛️ |
| regulation | EU Official Journal, Federal Register, trade tariffs, export restrictions | ⚖️ |
| bankruptcy | Chapter 11 filings this month | 💀 |
| commodity | Unexpected price movements | 📈 |
| pharmaceutical | FDA approvals this month | 💊 |
| academic | Retracted papers 2026 | 🔬 |
| job_listing | Mass layoff announcements | 👥 |
| app_ranking | App store biggest movers | 📱 |
| earnings | CEO resignations | 💰 |
| other | Domain sales, class action lawsuits | 📌 |

---

## 4. THE COLLISION CYCLE

### Phase 1: Anomaly Retrieval
- Pulls recent anomalies (last 7 days) sorted by weirdness score DESC
- Excludes anomalies attempted in the last hour (prevents re-evaluating the same ones)
- Picks top 3 anomalies to evaluate per cycle

### Phase 2: Entity Matching
- For each anomaly, extracts its underlying fact's entities
- Searches the `fact_entities` junction table for facts from DIFFERENT source types that share entities
- Falls back to keyword matching if no entity matches found

### Phase 3: Entity Resolution
- Takes entities from the anomaly and matching facts
- Asks Claude to identify RELATED entities (parent companies, subsidiaries, competitors, same tech by different names)
- Expands the search with resolved entity groups

### Phase 4: Collision Deduplication
- Before evaluating, checks if 50%+ of the fact IDs overlap with any existing collision
- Prevents the same fact combination from being re-collided

### Phase 5: Collision Evaluation
- Sends all matching facts + the anomaly to Claude
- Rules: "two things in the same industry" = NOT a collision. Must create an insight that NONE of the individual facts produce alone
- Multi-domain collisions weighted higher

### Phase 6: Hypothesis Formation
- If a collision is detected, Claude forms a SPECIFIC, TIME-BOUND hypothesis
- Must reference specific fact IDs, include a 90-day action plan, explain why nobody has done this, name a time window with dates
- Explicitly banned: generic "build a platform for X" ideas

### Phase 7: Kill Phase (3 rounds)
- Each round: web search for reasons the hypothesis is WRONG
- Round 1: Search for existing competitors
- Round 2: Search for barriers/reasons nobody has built this
- Round 3: Search for failed attempts
- If killed with "moderate" or "strong" confidence → hypothesis dies
- Killed hypotheses are saved for the record

### Phase 8: Scoring
- Only hypotheses that SURVIVE all 3 kill attempts are scored
- Diamond Scale (0-100) with 5 dimensions × 20 points each
- Novelty Gate: if a chatbot could generate this, Novelty ≤ 5
- Calibration: most hypotheses should score 35-55

### Phase 9: Report Writing
- For hypotheses scoring 40+, a full structured report is generated
- Mandatory sections: Summary, Fact Chain, Full Analysis, Why Now, Action Steps, Kill Attempts (Survived), Risks
- Every claim must trace back to a specific fact in the chain

### Phase 10: Deep Dive
- For hypotheses scoring 75+ (DIAMOND), triggers an automated deep dive
- Uses web search to validate from multiple angles
- Saves validation notes, competitor analysis, market size, action plan, recommendation

---

## 5. SCORING — THE DIAMOND SCALE

### 5 Dimensions (0-20 each)

| Dimension | 0-5 | 6-10 | 11-15 | 16-20 |
|-----------|-----|------|-------|-------|
| **Novelty** | Anyone could think of this | Known but under-explored | Requires connecting non-obvious dots | Nobody has articulated this |
| **Feasibility** | Requires $10M+ or PhD team | Hard but funded team possible | Solo with existing tools | Start this weekend |
| **Timing** | No urgency | 1-2 years | Specific 3-6 month window named | Closing window with a DATE |
| **Asymmetry** | Linear returns | Good ROI | 10x-100x with mechanism | Unbounded upside, minimal downside |
| **Intersection** | Single domain, obvious | Two domains, known way | Novel cross-domain requiring both | New category nobody is watching |

### Adjustments
- **Actionability multiplier**: 0.7x to 1.3x
- **Confidence penalty**: 0 to -15
- **Adjusted score** = (raw × multiplier) + penalty

### Score Labels

| Score | Label | Expected Frequency |
|-------|-------|--------------------|
| 90-100 | LEGENDARY | ~1 per week of continuous running |
| 75-89 | DIAMOND | ~1 in 200 collision cycles |
| 60-74 | STRONG | ~1 in 50 cycles |
| 40-59 | NOTABLE | Common for decent findings |
| 20-39 | INTERESTING | Most findings land here |
| 1-19 | NOISE | Filtered out |

---

## 6. DATABASE SCHEMA

### Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `raw_facts` | All ingested facts | source_type, title, raw_content, entities (JSON), keywords, domain, country, date_of_fact |
| `fact_entities` | Normalized entity index | raw_fact_id, entity_name, entity_name_lower |
| `anomalies` | Flagged anomalies | raw_fact_id, anomaly_description, weirdness_score (1-10), anomaly_type, last_collision_attempt |
| `collisions` | Detected fact collisions | fact_ids (JSON array), anomaly_ids, collision_description, num_facts, num_domains |
| `hypotheses` | Formed hypotheses (survived + killed) | collision_id, hypothesis_text, fact_chain, kill_attempts, survived_kill, diamond_score, full_report |
| `findings` | Scored hypotheses (40+) for dashboard | title, domain, score, all sub-scores, summary, full_report |
| `deep_dives` | Deep investigation of diamonds (75+) | finding_id, validation_notes, competitor_analysis, market_size, action_plan |
| `cycle_logs` | Operational telemetry | domain, tokens_used, duration, status |
| `daily_summaries` | Daily synthesis reports | most_promising_thread, missed_connections, tomorrow_priorities |

### Indexes
- `fact_entities(entity_name_lower)` — fast entity lookup
- `raw_facts(ingested_at)` — time-based queries
- `anomalies(weirdness_score)` — priority-based anomaly selection
- `hypotheses(diamond_score)` — score-based ranking
- `hypotheses(survived_kill)` — filter survived vs killed

---

## 7. RATE LIMITING & PERFORMANCE

### Smart Rate Limiter
- Tracks request timestamps in a sliding 60-second window
- Tracks input token usage per request
- Only sleeps when approaching limits (not unconditionally)
- Web search calls estimated at 25k input tokens
- Text calls estimated at 2k input tokens
- After each response, corrects estimates with actual `response.usage.input_tokens`

### Tier 1 Limits (current)
- 30,000 input tokens/minute
- ~50 requests/minute

### Retry Logic
- 3 attempts with exponential backoff: 2s → 8s → 32s
- Handles: 429 (rate limit), 500 (server error), 503 (service unavailable), network errors, timeouts

### Throughput Estimates (Tier 1)
- Ingest cycle: ~2-3 min (1 web search + 1 extract + 1 batch anomaly)
- Collision cycle: ~5-15 min (entity resolve + collision eval + hypothesis + 3 kill searches + score + report)
- ~15-20 ingest cycles/hour, ~3-5 collision cycles/hour

---

## 8. THINKING METHODOLOGY

### What Hunter Does NOT Do
- Generate ideas from scratch (consulting-brain)
- Follow the "underserved market + emerging technology = startup idea" formula
- Produce Medium-article-worthy observations and call them diamonds
- Score things generously to look productive

### What Hunter DOES Do
1. **Search Weird** — expired patents, regulatory filings, commodity price movements, retracted papers, bankruptcy filings
2. **Collide Domains** — shipping insurance regulation + computer vision model = opportunity nobody in either industry sees
3. **Follow Money Backward** — find the $200/hour professional doing something AI could do in 4 seconds
4. **Find Glitches** — stock up while every signal says down, company hiring while competitors lay off
5. **Think in Timing Windows** — regulation taking effect in 90 days, patent expiring next month, competitor just went bankrupt
6. **Obscurity Test** — could a smart person think of this in 30 seconds? If yes, it's not a diamond
7. **Hunt Asymmetry** — $100M market at 30% capture beats $50B market competing with Google
8. **Use Memory** — every cycle informed by the entire fact database, compounding over time

---

## 9. DAILY SYNTHESIS

Triggered every 100 ingest cycles OR every 24 hours:
1. Reviews ALL findings from the period
2. Identifies the single most promising thread
3. Looks for missed connections between independently-scored findings
4. Sets priorities for tomorrow
5. Identifies meta-patterns across domains
6. Honest quality check on scoring calibration

---

## 10. DASHBOARD (Streamlit)

6 tabs:
1. **Overview** — Stats cards: facts, anomalies, collisions, hypotheses, best score, source diversity
2. **Fact Feed** — Latest 100 facts with source icons, entities, anomaly flags, filterable by source type
3. **Anomalies** — Weirdness-scored anomalies with colored bars (red 7+, yellow 5-6, green below)
4. **Collisions** — All detected collisions with fact count, domain count, hypothesis status
5. **Hypotheses** — Surviving hypotheses ranked by diamond score, expandable reports. Killed hypotheses in collapsed section
6. **Daily Summaries** — Synthesis reports with most promising threads and priorities

Auto-refreshes every 30 seconds.

---

## 11. FILE STRUCTURE

```
~/HUNTER/
├── hunter.py          # Main engine (932 lines) — cycles, API calls, rate limiting, deep dives
├── database.py        # SQLite operations (1124 lines) — all CRUD, entity junction, dedup
├── prompts.py         # All prompts (712 lines) — system prompt, 12 phase-specific prompts
├── config.py          # Configuration (271 lines) — model, thresholds, data sources, domains
├── dashboard.py       # Streamlit dashboard (409 lines) — 6-tab v2-native view
├── .env               # ANTHROPIC_API_KEY=sk-ant-...
├── hunter.db          # SQLite database (persists across restarts)
├── hunter.log         # File log (survives terminal death)
└── requirements.txt   # anthropic, python-dotenv, streamlit
```

---

## 12. RUNNING IT

Terminal 1 (Hunter):
```bash
cd ~/HUNTER && python hunter.py
```

Terminal 2 (Dashboard):
```bash
cd ~/HUNTER && streamlit run dashboard.py
```

Stop gracefully: `Ctrl+C` (finishes current cycle, prints final stats)

---

## 13. THE COMPOUNDING FLYWHEEL

Day 1: ~100 facts. Few entity overlaps. Collisions sparse.
Day 7: ~1,000+ facts across 11 source types. Entity overlaps everywhere. Multi-domain collisions producing hypotheses.
Day 30: ~5,000+ facts. The collision surface area grows exponentially with fact count. Connections that would take a team of analysts weeks to spot happen automatically.
Day 180: ~20,000+ facts. The collision engine produces connections that no human could generate — not because it's smarter, but because it's holding more threads simultaneously than any person can.

The machine gets better every cycle. That's the architecture. That's what makes it different.

---

## 14. MODEL & API

- **Model**: Claude Sonnet 4 (`claude-sonnet-4-20250514`)
- **API**: Anthropic Messages API with web_search tool
- **Token caps**: 50k output per normal cycle, 150k per deep dive
- **Timeouts**: 30 min normal, 3 hours deep dive

---

## 15. WHAT A DIAMOND LOOKS LIKE

A chemical company in Germany filed Chapter 11 three days ago. That same company held the only active licence for a specific industrial compound. An EU regulation published two weeks ago mandates that compound in water treatment by 2028. The patent on the compound's manufacturing process expired last month. Nobody has filed to produce it.

Three facts. Three different source types. Three different domains. No human on earth is reading German bankruptcy filings AND EU regulatory journals AND USPTO patent expirations simultaneously.

Hunter is. Every day. And the more facts it accumulates, the more potential collisions exist. That's the flywheel. That's the machine.
