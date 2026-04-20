"""HUNTER Database -- SQLite schema and operations."""

import sqlite3
import json
from datetime import datetime
from config import DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            domain TEXT NOT NULL,
            score INTEGER NOT NULL,
            novelty_score INTEGER DEFAULT 0,
            feasibility_score INTEGER DEFAULT 0,
            timing_score INTEGER DEFAULT 0,
            asymmetry_score INTEGER DEFAULT 0,
            intersection_score INTEGER DEFAULT 0,
            actionability_multiplier REAL DEFAULT 1.0,
            confidence_penalty REAL DEFAULT 0,
            personal_fit_bonus REAL DEFAULT 0,
            adjusted_score REAL DEFAULT 0,
            summary TEXT,
            full_report TEXT,
            evidence_urls TEXT,
            action_steps TEXT,
            confidence TEXT DEFAULT 'Medium',
            time_sensitivity TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cycle_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            sub_topic TEXT,
            searches_run INTEGER DEFAULT 0,
            tokens_used INTEGER DEFAULT 0,
            max_score_found INTEGER DEFAULT 0,
            duration_seconds REAL DEFAULT 0,
            status TEXT DEFAULT 'completed',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deep_dives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            finding_id INTEGER NOT NULL,
            additional_searches INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            validation_notes TEXT,
            competitor_analysis TEXT,
            market_size TEXT,
            action_plan TEXT,
            final_recommendation TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (finding_id) REFERENCES findings(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS domain_state (
            domain TEXT PRIMARY KEY,
            last_explored TIMESTAMP,
            total_cycles INTEGER DEFAULT 0,
            avg_score REAL DEFAULT 0,
            best_finding_id INTEGER,
            explored_subtopics TEXT DEFAULT '[]'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cross_refs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            finding_a_id INTEGER NOT NULL,
            finding_b_id INTEGER NOT NULL,
            connection_description TEXT,
            combined_score REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (finding_a_id) REFERENCES findings(id),
            FOREIGN KEY (finding_b_id) REFERENCES findings(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_graph (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            finding_id INTEGER NOT NULL,
            domain TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            keywords TEXT,
            embedding_text TEXT,
            connections TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (finding_id) REFERENCES findings(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS idea_evolutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_finding_id INTEGER NOT NULL,
            child_finding_id INTEGER NOT NULL,
            evolution_description TEXT,
            score_improvement INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_finding_id) REFERENCES findings(id),
            FOREIGN KEY (child_finding_id) REFERENCES findings(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            summary_date TEXT NOT NULL,
            total_cycles INTEGER DEFAULT 0,
            total_findings INTEGER DEFAULT 0,
            diamonds_found INTEGER DEFAULT 0,
            best_finding_id INTEGER,
            most_promising_thread TEXT,
            missed_connections TEXT,
            tomorrow_priorities TEXT,
            full_synthesis TEXT,
            tokens_used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # === v2 Fact-Collision Tables ===

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_url TEXT,
            title TEXT NOT NULL,
            raw_content TEXT,
            entities TEXT,
            keywords TEXT,
            domain TEXT,
            country TEXT,
            date_of_fact TEXT,
            ingested_at TEXT DEFAULT (datetime('now')),
            obscurity TEXT DEFAULT 'medium',
            implications TEXT DEFAULT '[]'
        )
    """)

    # Migrate: add obscurity column if missing (for existing databases)
    cursor.execute("PRAGMA table_info(raw_facts)")
    raw_facts_columns = {row[1] for row in cursor.fetchall()}
    if "obscurity" not in raw_facts_columns:
        cursor.execute("ALTER TABLE raw_facts ADD COLUMN obscurity TEXT DEFAULT 'medium'")
    if "implications" not in raw_facts_columns:
        cursor.execute("ALTER TABLE raw_facts ADD COLUMN implications TEXT DEFAULT '[]'")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_fact_id INTEGER REFERENCES raw_facts(id),
            anomaly_description TEXT NOT NULL,
            weirdness_score INTEGER CHECK(weirdness_score BETWEEN 1 AND 10),
            anomaly_type TEXT,
            entities TEXT,
            domain TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            last_collision_attempt TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact_ids TEXT NOT NULL,
            anomaly_ids TEXT,
            collision_description TEXT NOT NULL,
            num_facts INTEGER,
            num_domains INTEGER,
            domains_involved TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hypotheses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collision_id INTEGER REFERENCES collisions(id),
            hypothesis_text TEXT NOT NULL,
            fact_chain TEXT,
            action_steps TEXT,
            time_window_days INTEGER,
            kill_attempts TEXT,
            survived_kill INTEGER DEFAULT 0,
            diamond_score INTEGER,
            novelty INTEGER,
            feasibility INTEGER,
            timing INTEGER,
            asymmetry INTEGER,
            intersection INTEGER,
            confidence TEXT,
            full_report TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fact_entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_fact_id INTEGER REFERENCES raw_facts(id),
            entity_name TEXT NOT NULL,
            entity_name_lower TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fact_entities_name ON fact_entities(entity_name_lower)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fact_entities_fact ON fact_entities(raw_fact_id)")

    # Model vulnerability junction table — enables Strategy 4 matching
    # Two facts challenging the same ASSUMPTION from different domains collide
    # even if they share zero entities and zero keywords
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fact_model_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_fact_id INTEGER REFERENCES raw_facts(id),
            field_type TEXT NOT NULL,
            field_value TEXT NOT NULL,
            field_value_lower TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fmf_type_value ON fact_model_fields(field_type, field_value_lower)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fmf_fact ON fact_model_fields(raw_fact_id)")

    # Backfill fact_model_fields from existing raw_facts.model_vulnerability data
    cursor.execute("SELECT COUNT(*) FROM fact_model_fields")
    fmf_count = cursor.fetchone()[0]
    if fmf_count == 0:
        cursor.execute("SELECT id, model_vulnerability FROM raw_facts WHERE model_vulnerability != 'null' AND model_vulnerability IS NOT NULL")
        backfill_rows = cursor.fetchall()
        _backfill_count = 0
        for row in backfill_rows:
            try:
                mv = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                if isinstance(mv, dict):
                    for field_type in ("assumption", "methodology", "practitioners", "disruption", "calibration"):
                        val = mv.get(field_type, "")
                        if val and isinstance(val, str) and len(val) > 5:
                            cursor.execute("""
                                INSERT INTO fact_model_fields (raw_fact_id, field_type, field_value, field_value_lower)
                                VALUES (?, ?, ?, ?)
                            """, (row[0], field_type, val.strip(), val.strip().lower()))
                            _backfill_count += 1
            except (json.JSONDecodeError, TypeError):
                continue
        if _backfill_count > 0:
            print(f"  Backfilled {_backfill_count} model vulnerability fields from {len(backfill_rows)} facts")

    # Migrate: add last_collision_attempt to anomalies if it doesn't exist yet
    cursor.execute("PRAGMA table_info(anomalies)")
    anomaly_columns = {row[1] for row in cursor.fetchall()}
    if "last_collision_attempt" not in anomaly_columns:
        cursor.execute("ALTER TABLE anomalies ADD COLUMN last_collision_attempt TEXT")

    # Create indexes -- v1
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_domain ON findings(domain)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_score ON findings(adjusted_score DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_created ON findings(created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cycle_logs_domain ON cycle_logs(domain)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_graph_finding ON knowledge_graph(finding_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_graph_domain ON knowledge_graph(domain)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_idea_evolutions_parent ON idea_evolutions(parent_finding_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_idea_evolutions_child ON idea_evolutions(child_finding_id)")

    # Create indexes -- v2
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_facts_source ON raw_facts(source_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_facts_date ON raw_facts(ingested_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomalies_date ON anomalies(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomalies_weirdness ON anomalies(weirdness_score)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hypotheses_score ON hypotheses(diamond_score)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hypotheses_survived ON hypotheses(survived_kill)")

    # Held collisions -- passed collision eval but failed broken model gate
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS held_collisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collision_id INTEGER REFERENCES collisions(id),
            fact_ids TEXT NOT NULL,
            collision_description TEXT NOT NULL,
            gate_reasoning TEXT,
            domains_involved TEXT,
            source_types TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Domain productivity tracking -- feedback loop from collision output to query allocation
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS domain_productivity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            facts_count INTEGER DEFAULT 0,
            hypotheses_survived INTEGER DEFAULT 0,
            productivity_score REAL DEFAULT 0.0,
            calculated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_domain_prod_calc ON domain_productivity(calculated_at DESC)")

    # Transitive chains — multi-link causal chains discovered by extending disruption-assumption pairs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collision_id INTEGER REFERENCES collisions(id),
            chain_links TEXT NOT NULL,
            chain_length INTEGER DEFAULT 1,
            domains_traversed TEXT,
            num_domains INTEGER DEFAULT 1,
            endpoint_vocab_overlap REAL DEFAULT 0.0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Migrate: add source_types column to collisions if it doesn't exist
    cursor.execute("PRAGMA table_info(collisions)")
    collision_columns = {row[1] for row in cursor.fetchall()}
    if "source_types" not in collision_columns:
        cursor.execute("ALTER TABLE collisions ADD COLUMN source_types TEXT DEFAULT ''")
    if "temporal_spread_days" not in collision_columns:
        cursor.execute("ALTER TABLE collisions ADD COLUMN temporal_spread_days INTEGER DEFAULT 0")
    if "oldest_fact_age_days" not in collision_columns:
        cursor.execute("ALTER TABLE collisions ADD COLUMN oldest_fact_age_days INTEGER DEFAULT 0")
    if "negative_space_score" not in collision_columns:
        cursor.execute("ALTER TABLE collisions ADD COLUMN negative_space_score INTEGER DEFAULT NULL")
    if "negative_space_gap" not in collision_columns:
        cursor.execute("ALTER TABLE collisions ADD COLUMN negative_space_gap TEXT DEFAULT NULL")

    # Causal graph table — directed edges extracted from facts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS causal_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_fact_id INTEGER REFERENCES raw_facts(id),
            cause_node TEXT NOT NULL,
            effect_node TEXT NOT NULL,
            cause_node_lower TEXT NOT NULL,
            effect_node_lower TEXT NOT NULL,
            relationship_type TEXT DEFAULT 'causes',
            confidence REAL DEFAULT 0.8,
            source_type TEXT,
            domain TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_causal_cause ON causal_edges(cause_node_lower)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_causal_effect ON causal_edges(effect_node_lower)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_causal_fact ON causal_edges(source_fact_id)")

    # Migrate: add model_vulnerability column to raw_facts if it doesn't exist
    cursor.execute("PRAGMA table_info(raw_facts)")
    rf_columns = {row[1] for row in cursor.fetchall()}
    if "model_vulnerability" not in rf_columns:
        cursor.execute("ALTER TABLE raw_facts ADD COLUMN model_vulnerability TEXT DEFAULT 'null'")
    if "reflexivity_tag" not in rf_columns:
        cursor.execute("ALTER TABLE raw_facts ADD COLUMN reflexivity_tag TEXT DEFAULT NULL")
    if "implication_embedding" not in rf_columns:
        cursor.execute("ALTER TABLE raw_facts ADD COLUMN implication_embedding BLOB DEFAULT NULL")
    if "market_belief" not in rf_columns:
        cursor.execute("ALTER TABLE raw_facts ADD COLUMN market_belief TEXT DEFAULT 'null'")

    # Migrate: add strength and mechanism columns to causal_edges if not present
    cursor.execute("PRAGMA table_info(causal_edges)")
    ce_columns = {row[1] for row in cursor.fetchall()}
    if "strength" not in ce_columns:
        cursor.execute("ALTER TABLE causal_edges ADD COLUMN strength TEXT DEFAULT 'moderate'")
    if "mechanism" not in ce_columns:
        cursor.execute("ALTER TABLE causal_edges ADD COLUMN mechanism TEXT DEFAULT ''")

    # Migrate: add gap_targeted to cycle_logs
    cursor.execute("PRAGMA table_info(cycle_logs)")
    cl_columns = {row[1] for row in cursor.fetchall()}
    if "gap_targeted" not in cl_columns:
        cursor.execute("ALTER TABLE cycle_logs ADD COLUMN gap_targeted INTEGER DEFAULT 0")

    # Migrate: add reviewed column to hypotheses if not exists
    cursor.execute("PRAGMA table_info(hypotheses)")
    hyp_columns = {row[1] for row in cursor.fetchall()}
    if "reviewed" not in hyp_columns:
        cursor.execute("ALTER TABLE hypotheses ADD COLUMN reviewed INTEGER DEFAULT 0")

    # Migrate: add reviewed column to held_collisions if not exists
    cursor.execute("PRAGMA table_info(held_collisions)")
    held_columns = {row[1] for row in cursor.fetchall()}
    if "reviewed" not in held_columns:
        cursor.execute("ALTER TABLE held_collisions ADD COLUMN reviewed INTEGER DEFAULT 0")

    # ── Theory Proof Layer tables ──
    # Migrate: if old theory_evidence schema exists (from Prompt 1.1), recreate with new schema
    cursor.execute("PRAGMA table_info(theory_evidence)")
    te_cols = {row[1] for row in cursor.fetchall()}
    if te_cols and "source_event" not in te_cols:
        # Old schema detected — drop and recreate (table was empty/fresh anyway)
        cursor.execute("DROP TABLE IF EXISTS theory_evidence")

    # theory_evidence: per-layer evidence from every collision, hypothesis, kill, backtest
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS theory_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            source_event TEXT NOT NULL,
            source_id INTEGER,
            layer INTEGER NOT NULL,
            layer_name TEXT NOT NULL,
            evidence_type TEXT NOT NULL,
            description TEXT,
            metric TEXT,
            observed_value REAL,
            predicted_value REAL,
            unit TEXT,
            confidence REAL,
            domain_pair TEXT,
            chain_depth INTEGER,
            cycle_detected INTEGER DEFAULT 0,
            cycle_type TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_theory_layer ON theory_evidence(layer)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_theory_type ON theory_evidence(evidence_type)")

    # decay_tracking: longitudinal tracking of hypothesis decay over time
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decay_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hypothesis_id INTEGER REFERENCES hypotheses(id),
            formation_date TEXT,
            check_date TEXT,
            still_uncorrected INTEGER,
            market_moved_direction TEXT,
            market_moved_magnitude REAL,
            sources_reinforcing INTEGER,
            sources_correcting INTEGER
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decay_hyp ON decay_tracking(hypothesis_id)")

    # detected_cycles: epistemic reinforcement loops (Layer 8-9)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS detected_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            detected_date TEXT,
            cycle_type TEXT,
            nodes TEXT,
            edges TEXT,
            domains TEXT,
            reinforcement_strength REAL,
            correction_pressure REAL,
            persistence_estimate REAL,
            age_days INTEGER,
            last_reinforced_days INTEGER,
            is_active INTEGER DEFAULT 1
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cycles_type ON detected_cycles(cycle_type)")

    # formula_validation: periodic regression of collision formula vs outcomes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS formula_validation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            pearson_r REAL,
            spearman_rho REAL,
            p_value REAL,
            formula_validated INTEGER,
            suggested_silo_coeff REAL,
            suggested_reinf_weight REAL,
            suggested_corr_weight REAL,
            suggested_resid_weight REAL
        )
    """)

    # backtest_results: reconciliation of hypothesis predictions vs reality
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hypothesis_id INTEGER REFERENCES hypotheses(id),
            reconciled_date TEXT,
            direction_correct INTEGER,
            magnitude_predicted REAL,
            magnitude_actual REAL,
            within_timeframe INTEGER,
            mechanism_confirmed INTEGER,
            chain_depth INTEGER,
            domain_distance REAL,
            cycle_involved INTEGER
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_backtest_hyp ON backtest_results(hypothesis_id)")

    # residual_estimates: per-domain residual density tracking over time
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS residual_estimates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            domain TEXT,
            market_size_B REAL,
            predicted_residual_pct REAL,
            observed_residual_pct REAL,
            estimated_residual_B REAL,
            sample_size INTEGER
        )
    """)

    # Portfolio tracking tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hypothesis_id INTEGER UNIQUE REFERENCES hypotheses(id),
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('long', 'short')),
            entry_price REAL,
            entry_date TEXT,
            current_price REAL,
            current_date TEXT,
            pnl_pct REAL DEFAULT 0.0,
            pnl_gbp REAL DEFAULT 0.0,
            capital_allocated REAL DEFAULT 0.0,
            status TEXT DEFAULT 'open' CHECK(status IN ('open', 'closed')),
            close_price REAL,
            close_date TEXT,
            close_reason TEXT,
            time_window_days INTEGER,
            diamond_score INTEGER,
            confidence TEXT,
            hypothesis_text TEXT,
            full_report TEXT,
            domains TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            total_value REAL,
            total_return_pct REAL,
            spy_return_pct REAL,
            num_open INTEGER DEFAULT 0,
            num_closed INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0.0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_status ON portfolio_positions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_hypothesis ON portfolio_positions(hypothesis_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_date ON portfolio_snapshots(date)")

    # Targeting system
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            firm_name TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            verticals TEXT,
            focus_domains TEXT,
            notes TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS firm_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hypothesis_id INTEGER REFERENCES hypotheses(id),
            firms_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS overseer_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_text TEXT NOT NULL,
            suggestions_json TEXT,
            metrics_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Theory run: edge recovery events telemetry
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS edge_recovery_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hypothesis_id INTEGER,
            original_thesis_text TEXT,
            original_awareness_level INTEGER,
            killed_at_score INTEGER,
            recovery_attempted_at TEXT DEFAULT (datetime('now')),
            novel_subelement_found INTEGER DEFAULT 0,
            recovered_thesis_text TEXT,
            recovered_awareness_level INTEGER,
            recovered_score INTEGER,
            delta_awareness INTEGER,
            delta_score INTEGER
        )
    """)

    # Theory run: per-cycle timing and cost telemetry
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS theory_run_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_num INTEGER,
            wall_clock_seconds REAL,
            tokens_used INTEGER DEFAULT 0,
            collisions_generated INTEGER DEFAULT 0,
            hypotheses_scored INTEGER DEFAULT 0,
            hypotheses_survived INTEGER DEFAULT 0,
            estimated_cost_usd REAL DEFAULT 0.0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Migrate: add theory run telemetry columns to hypotheses
    cursor.execute("PRAGMA table_info(hypotheses)")
    hyp_cols_theory = {row[1] for row in cursor.fetchall()}
    for col, coltype in [
        ("market_awareness_telemetry", "TEXT"),
        ("facts_per_domain", "TEXT"),
        ("min_depth", "INTEGER"),
        ("max_depth", "INTEGER"),
        ("domain_count", "INTEGER"),
        ("depth_concentration", "REAL"),
        # v3 Golden: Module F — lightweight awareness
        ("lightweight_awareness_level", "INTEGER"),
        # v3 Golden: Module G — per-stage timing
        ("stage_timestamps", "TEXT"),
        # v3 Golden: Module H — entity specificity
        ("entity_specificity_score", "INTEGER"),
        # v3 Golden: Module J — causal chain depth
        ("causal_chain_length", "INTEGER"),
        # v3 Golden: Module K — score component decomposition
        ("mechanism_integrity", "INTEGER"),
        ("domain_bonus", "INTEGER"),
        ("chain_bonus", "INTEGER"),
        ("fact_confidence_adj", "INTEGER"),
        ("actionability_multiplier", "REAL"),
        ("confidence_penalty", "REAL"),
        # v3 Golden: stratum tracking
        ("stratum", "TEXT"),
        ("collision_mode", "TEXT"),
        # v3 Golden: Module L — cited fact IDs (leakage prevention)
        ("cited_fact_ids", "TEXT"),
        # v3 Golden: Phase 3 — market validation
        ("structured_prediction", "TEXT"),
        ("validation_outcome", "TEXT"),
        ("realized_return_pct", "REAL"),
        ("sector_return_pct", "REAL"),
        ("residual_pct", "REAL"),
        ("materialised", "INTEGER"),
        ("validation_method", "TEXT"),
        ("daily_price_series", "TEXT"),
        # v3 Golden: Phase 4 — leakage audit
        ("leakage_flags", "TEXT"),
    ]:
        if col not in hyp_cols_theory:
            cursor.execute(f"ALTER TABLE hypotheses ADD COLUMN {col} {coltype}")

    # Migrate: add stratum/collision_mode to theory_run_cycles
    cursor.execute("PRAGMA table_info(theory_run_cycles)")
    cycle_cols = {row[1] for row in cursor.fetchall()}
    for col, coltype in [
        ("collision_mode", "TEXT"),
        ("stratum", "TEXT"),
    ]:
        if col not in cycle_cols:
            cursor.execute(f"ALTER TABLE theory_run_cycles ADD COLUMN {col} {coltype}")

    # v3 Golden: null_runs table for three baselines
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS null_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            null_type TEXT NOT NULL,
            paired_real_hypothesis_id INTEGER REFERENCES hypotheses(id),
            primary_ticker TEXT,
            direction TEXT,
            time_window_days INTEGER,
            structured_prediction TEXT,
            validation_outcome TEXT,
            realized_return_pct REAL,
            sector_return_pct REAL,
            residual_pct REAL,
            materialised INTEGER,
            validation_method TEXT,
            daily_price_series TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_null_runs_type ON null_runs(null_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_null_runs_pair ON null_runs(paired_real_hypothesis_id)")

    conn.commit()
    conn.close()


def save_finding(title, domain, score, novelty_score, feasibility_score,
                 timing_score, asymmetry_score, intersection_score,
                 actionability_multiplier, confidence_penalty, personal_fit_bonus,
                 adjusted_score, summary, full_report, evidence_urls,
                 action_steps, confidence, time_sensitivity):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO findings (title, domain, score, novelty_score, feasibility_score,
            timing_score, asymmetry_score, intersection_score,
            actionability_multiplier, confidence_penalty, personal_fit_bonus,
            adjusted_score, summary, full_report, evidence_urls,
            action_steps, confidence, time_sensitivity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (title, domain, score, novelty_score, feasibility_score,
          timing_score, asymmetry_score, intersection_score,
          actionability_multiplier, confidence_penalty, personal_fit_bonus,
          adjusted_score, summary, full_report, evidence_urls,
          action_steps, confidence, time_sensitivity))
    finding_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return finding_id


def save_cycle_log(domain, sub_topic, searches_run, tokens_used,
                   max_score_found, duration_seconds, status="completed",
                   error_message=None, gap_targeted=0):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO cycle_logs (domain, sub_topic, searches_run, tokens_used,
            max_score_found, duration_seconds, status, error_message, gap_targeted)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (domain, sub_topic, searches_run, tokens_used,
          max_score_found, duration_seconds, status, error_message, int(gap_targeted)))
    conn.commit()
    conn.close()


def save_deep_dive(finding_id, additional_searches, total_tokens,
                   validation_notes, competitor_analysis, market_size,
                   action_plan, final_recommendation):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO deep_dives (finding_id, additional_searches, total_tokens,
            validation_notes, competitor_analysis, market_size,
            action_plan, final_recommendation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (finding_id, additional_searches, total_tokens,
          validation_notes, competitor_analysis, market_size,
          action_plan, final_recommendation))
    conn.commit()
    conn.close()


def save_cross_ref(finding_a_id, finding_b_id, connection_description, combined_score):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO cross_refs (finding_a_id, finding_b_id,
            connection_description, combined_score)
        VALUES (?, ?, ?, ?)
    """, (finding_a_id, finding_b_id, connection_description, combined_score))
    conn.commit()
    conn.close()


def update_domain_state(domain, sub_topic, score, finding_id=None):
    conn = get_connection()
    cursor = conn.cursor()

    # Get current state
    cursor.execute("SELECT * FROM domain_state WHERE domain = ?", (domain,))
    row = cursor.fetchone()

    now = datetime.now().isoformat()

    if row is None:
        explored = json.dumps([sub_topic] if sub_topic else [])
        cursor.execute("""
            INSERT INTO domain_state (domain, last_explored, total_cycles, avg_score,
                best_finding_id, explored_subtopics)
            VALUES (?, ?, 1, ?, ?, ?)
        """, (domain, now, score, finding_id, explored))
    else:
        total_cycles = row["total_cycles"] + 1
        avg_score = ((row["avg_score"] * row["total_cycles"]) + score) / total_cycles
        best_id = finding_id if finding_id and (row["best_finding_id"] is None or score > get_finding_score(row["best_finding_id"])) else row["best_finding_id"]

        explored = json.loads(row["explored_subtopics"] or "[]")
        if sub_topic and sub_topic not in explored:
            explored.append(sub_topic)
            # Keep last 50 subtopics
            if len(explored) > 50:
                explored = explored[-50:]

        cursor.execute("""
            UPDATE domain_state
            SET last_explored = ?, total_cycles = ?, avg_score = ?,
                best_finding_id = ?, explored_subtopics = ?
            WHERE domain = ?
        """, (now, total_cycles, avg_score, best_id, json.dumps(explored), domain))

    conn.commit()
    conn.close()


def get_finding_score(finding_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT score FROM findings WHERE id = ?", (finding_id,))
    row = cursor.fetchone()
    conn.close()
    return row["score"] if row else 0


def get_findings(domain=None, min_score=None, max_score=None, limit=100, offset=0):
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM findings WHERE 1=1"
    params = []

    if domain:
        query += " AND domain = ?"
        params.append(domain)
    if min_score is not None:
        query += " AND adjusted_score >= ?"
        params.append(min_score)
    if max_score is not None:
        query += " AND adjusted_score <= ?"
        params.append(max_score)

    query += " ORDER BY adjusted_score DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_finding_by_id(finding_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM findings WHERE id = ?", (finding_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_deep_dive_for_finding(finding_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM deep_dives WHERE finding_id = ?", (finding_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_cross_refs_for_finding(finding_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT cr.*, f1.title as title_a, f2.title as title_b
        FROM cross_refs cr
        JOIN findings f1 ON cr.finding_a_id = f1.id
        JOIN findings f2 ON cr.finding_b_id = f2.id
        WHERE cr.finding_a_id = ? OR cr.finding_b_id = ?
    """, (finding_id, finding_id))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_domain_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM domain_state ORDER BY last_explored DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_domain_state(domain):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM domain_state WHERE domain = ?", (domain,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_recent_findings_for_cross_ref(exclude_domain=None, limit=20):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT id, title, domain, summary, score FROM findings WHERE score >= 40"
    params = []
    if exclude_domain:
        query += " AND domain != ?"
        params.append(exclude_domain)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_dashboard_stats():
    conn = get_connection()
    cursor = conn.cursor()

    stats = {}

    cursor.execute("SELECT COUNT(*) as total FROM cycle_logs")
    stats["total_cycles"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(DISTINCT domain) as total FROM cycle_logs")
    stats["domains_explored"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM findings")
    stats["total_findings"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM findings WHERE score >= 75")
    stats["diamonds_found"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COALESCE(SUM(tokens_used), 0) as total FROM cycle_logs WHERE date(created_at) = date('now')")
    stats["tokens_today"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COALESCE(SUM(tokens_used), 0) as total FROM cycle_logs")
    stats["tokens_total"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM deep_dives")
    stats["deep_dives"] = cursor.fetchone()["total"]

    cursor.execute("SELECT MAX(adjusted_score) as best FROM findings")
    row = cursor.fetchone()
    stats["best_score"] = row["best"] if row["best"] else 0

    conn.close()
    return stats


def get_all_domains_list():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT domain FROM findings ORDER BY domain")
    rows = cursor.fetchall()
    conn.close()
    return [r["domain"] for r in rows]


# ============================================================
# Knowledge Graph operations
# ============================================================

def save_knowledge_node(finding_id, domain, title, summary, keywords, embedding_text):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO knowledge_graph (finding_id, domain, title, summary,
            keywords, embedding_text, connections)
        VALUES (?, ?, ?, ?, ?, ?, '[]')
    """, (finding_id, domain, title, summary, keywords, embedding_text))
    node_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return node_id


def search_knowledge_graph(keywords_list, exclude_finding_id=None, limit=10):
    """Search knowledge graph using keyword LIKE matching."""
    conn = get_connection()
    cursor = conn.cursor()

    if not keywords_list:
        conn.close()
        return []

    # Build LIKE conditions for each keyword
    conditions = []
    params = []
    for kw in keywords_list:
        kw_clean = kw.strip().lower()
        if len(kw_clean) < 3:
            continue
        conditions.append(
            "(LOWER(kg.keywords) LIKE ? OR LOWER(kg.title) LIKE ? OR LOWER(kg.summary) LIKE ? OR LOWER(kg.embedding_text) LIKE ?)"
        )
        pattern = f"%{kw_clean}%"
        params.extend([pattern, pattern, pattern, pattern])

    if not conditions:
        conn.close()
        return []

    where = " OR ".join(conditions)
    query = f"""
        SELECT kg.id, kg.finding_id, kg.domain, kg.title, kg.summary,
               kg.keywords, kg.embedding_text, kg.connections, kg.created_at,
               f.score, f.adjusted_score, f.full_report
        FROM knowledge_graph kg
        JOIN findings f ON kg.finding_id = f.id
        WHERE ({where})
    """
    if exclude_finding_id:
        query += " AND kg.finding_id != ?"
        params.append(exclude_finding_id)

    # Rank by number of keyword matches (rough relevance)
    query += " ORDER BY f.adjusted_score DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_knowledge_connections(node_id, connected_finding_ids):
    conn = get_connection()
    conn.execute(
        "UPDATE knowledge_graph SET connections = ? WHERE id = ?",
        (json.dumps(connected_finding_ids), node_id)
    )
    conn.commit()
    conn.close()


# ============================================================
# Idea Evolution operations
# ============================================================

def save_idea_evolution(parent_finding_id, child_finding_id,
                        evolution_description, score_improvement):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO idea_evolutions (parent_finding_id, child_finding_id,
            evolution_description, score_improvement)
        VALUES (?, ?, ?, ?)
    """, (parent_finding_id, child_finding_id, evolution_description, score_improvement))
    conn.commit()
    conn.close()


def get_evolution_chains():
    """Get all evolution chains, ordered by most recent child."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ie.*,
               fp.title as parent_title, fp.score as parent_score,
               fp.domain as parent_domain, fp.adjusted_score as parent_adjusted,
               fc.title as child_title, fc.score as child_score,
               fc.domain as child_domain, fc.adjusted_score as child_adjusted
        FROM idea_evolutions ie
        JOIN findings fp ON ie.parent_finding_id = fp.id
        JOIN findings fc ON ie.child_finding_id = fc.id
        ORDER BY ie.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_evolution_tree(finding_id):
    """Trace a finding's full lineage -- ancestors and descendants."""
    conn = get_connection()
    cursor = conn.cursor()

    chain = []

    # Trace ancestors (parents)
    current = finding_id
    visited = set()
    while current and current not in visited:
        visited.add(current)
        cursor.execute("""
            SELECT ie.*, f.title, f.score, f.domain, f.adjusted_score
            FROM idea_evolutions ie
            JOIN findings f ON ie.parent_finding_id = f.id
            WHERE ie.child_finding_id = ?
        """, (current,))
        row = cursor.fetchone()
        if row:
            chain.insert(0, dict(row))
            current = row["parent_finding_id"]
        else:
            break

    # Trace descendants (children)
    current = finding_id
    visited = set()
    while current and current not in visited:
        visited.add(current)
        cursor.execute("""
            SELECT ie.*, f.title, f.score, f.domain, f.adjusted_score
            FROM idea_evolutions ie
            JOIN findings f ON ie.child_finding_id = f.id
            WHERE ie.parent_finding_id = ?
        """, (current,))
        row = cursor.fetchone()
        if row:
            chain.append(dict(row))
            current = row["child_finding_id"]
        else:
            break

    conn.close()
    return chain


# ============================================================
# Daily Summary operations
# ============================================================

def save_daily_summary(summary_date, total_cycles, total_findings, diamonds_found,
                       best_finding_id, most_promising_thread, missed_connections,
                       tomorrow_priorities, full_synthesis, tokens_used):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO daily_summaries (summary_date, total_cycles, total_findings,
            diamonds_found, best_finding_id, most_promising_thread,
            missed_connections, tomorrow_priorities, full_synthesis, tokens_used)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (summary_date, total_cycles, total_findings, diamonds_found,
          best_finding_id, most_promising_thread, missed_connections,
          tomorrow_priorities, full_synthesis, tokens_used))
    conn.commit()
    conn.close()


def get_daily_summaries(limit=30):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ds.*, f.title as best_finding_title
        FROM daily_summaries ds
        LEFT JOIN findings f ON ds.best_finding_id = f.id
        ORDER BY ds.summary_date DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_last_daily_summary_date():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(summary_date) as last_date FROM daily_summaries")
    row = cursor.fetchone()
    conn.close()
    return row["last_date"] if row and row["last_date"] else None


def get_findings_since(since_datetime, limit=200):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM findings
        WHERE created_at >= ?
        ORDER BY adjusted_score DESC LIMIT ?
    """, (since_datetime, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_open_threads(domain, min_score=50, limit=5):
    """Get high-scoring findings in a domain that haven't been evolved yet."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.id, f.title, f.score, f.summary, f.adjusted_score
        FROM findings f
        WHERE f.domain = ? AND f.score >= ?
        AND f.id NOT IN (SELECT parent_finding_id FROM idea_evolutions)
        ORDER BY f.adjusted_score DESC LIMIT ?
    """, (domain, min_score, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_domain_best_finding(domain):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, score, summary, adjusted_score
        FROM findings WHERE domain = ?
        ORDER BY adjusted_score DESC LIMIT 1
    """, (domain,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_cycles_since_last_summary():
    conn = get_connection()
    cursor = conn.cursor()
    last_date = get_last_daily_summary_date()
    if last_date:
        cursor.execute("SELECT COUNT(*) as total FROM cycle_logs WHERE created_at > ?", (last_date,))
    else:
        cursor.execute("SELECT COUNT(*) as total FROM cycle_logs")
    row = cursor.fetchone()
    conn.close()
    return row["total"] if row else 0


# ============================================================
# v2 Fact-Collision Operations
# ============================================================

def save_raw_fact(source_type, source_url, title, raw_content, entities,
                  keywords, domain, country, date_of_fact, obscurity="medium",
                  implications=None, model_vulnerability=None, reflexivity_tag=None,
                  market_belief=None):
    conn = get_connection()
    cursor = conn.cursor()

    # Dedup: skip if a fact with the same title AND source_type already exists
    cursor.execute("""
        SELECT id FROM raw_facts
        WHERE LOWER(title) = LOWER(?) AND LOWER(source_type) = LOWER(?)
        LIMIT 1
    """, (title, source_type))
    if cursor.fetchone():
        conn.close()
        return None

    entities_json = json.dumps(entities) if isinstance(entities, list) else entities
    implications_json = json.dumps(implications) if isinstance(implications, list) else (implications or "[]")
    mv_json = json.dumps(model_vulnerability) if isinstance(model_vulnerability, dict) else (model_vulnerability or "null")
    mb_json = json.dumps(market_belief) if isinstance(market_belief, dict) else (market_belief or "null")
    cursor.execute("""
        INSERT INTO raw_facts (source_type, source_url, title, raw_content,
            entities, keywords, domain, country, date_of_fact, obscurity, implications,
            model_vulnerability, reflexivity_tag, market_belief)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (source_type, source_url, title, raw_content,
          entities_json, keywords, domain, country, date_of_fact, obscurity,
          implications_json, mv_json, reflexivity_tag, mb_json))
    fact_id = cursor.lastrowid

    # Insert into fact_entities junction table
    entities_list = entities if isinstance(entities, list) else []
    if isinstance(entities, str):
        try:
            entities_list = json.loads(entities)
        except (json.JSONDecodeError, TypeError):
            entities_list = []
    for entity_name in entities_list:
        if entity_name and isinstance(entity_name, str):
            cursor.execute("""
                INSERT INTO fact_entities (raw_fact_id, entity_name, entity_name_lower)
                VALUES (?, ?, ?)
            """, (fact_id, entity_name.strip(), entity_name.strip().lower()))

    # Insert into fact_model_fields junction table (Strategy 4 matching)
    mv_data = None
    if isinstance(model_vulnerability, dict):
        mv_data = model_vulnerability
    elif isinstance(model_vulnerability, str) and model_vulnerability != "null":
        try:
            mv_data = json.loads(model_vulnerability)
        except (json.JSONDecodeError, TypeError):
            pass
    if isinstance(mv_data, dict):
        for field_type in ("assumption", "methodology", "practitioners", "disruption", "calibration"):
            val = mv_data.get(field_type, "")
            if val and isinstance(val, str) and len(val) > 5:
                cursor.execute("""
                    INSERT INTO fact_model_fields (raw_fact_id, field_type, field_value, field_value_lower)
                    VALUES (?, ?, ?, ?)
                """, (fact_id, field_type, val.strip(), val.strip().lower()))

    conn.commit()
    conn.close()
    return fact_id


def save_anomaly(raw_fact_id, anomaly_description, weirdness_score,
                 anomaly_type, entities, domain):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO anomalies (raw_fact_id, anomaly_description, weirdness_score,
            anomaly_type, entities, domain)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (raw_fact_id, anomaly_description, weirdness_score, anomaly_type,
          json.dumps(entities) if isinstance(entities, list) else entities, domain))
    anomaly_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return anomaly_id


def save_collision(fact_ids, anomaly_ids, collision_description,
                   num_facts, num_domains, domains_involved, source_types="",
                   temporal_spread_days=0, oldest_fact_age_days=0,
                   negative_space_score=None, negative_space_gap=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO collisions (fact_ids, anomaly_ids, collision_description,
            num_facts, num_domains, domains_involved, source_types,
            temporal_spread_days, oldest_fact_age_days,
            negative_space_score, negative_space_gap)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (json.dumps(fact_ids), json.dumps(anomaly_ids or []),
          collision_description, num_facts, num_domains, domains_involved, source_types,
          temporal_spread_days, oldest_fact_age_days,
          negative_space_score, negative_space_gap))
    collision_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return collision_id


def save_held_collision(collision_id, fact_ids, collision_description,
                        gate_reasoning, domains_involved, source_types):
    """Save a collision that passed evaluation but failed the broken model gate."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO held_collisions (collision_id, fact_ids, collision_description,
            gate_reasoning, domains_involved, source_types)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (collision_id, json.dumps(fact_ids), collision_description,
          gate_reasoning, domains_involved, source_types))
    conn.commit()
    conn.close()


def save_chain(collision_id, chain_links, domains_traversed):
    """Save a transitive causal chain discovered by extending a disruption-assumption pair."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO chains (collision_id, chain_links, chain_length,
            domains_traversed, num_domains)
        VALUES (?, ?, ?, ?, ?)
    """, (collision_id, json.dumps(chain_links), len(chain_links),
          ", ".join(domains_traversed), len(set(domains_traversed))))
    conn.commit()
    conn.close()


def save_domain_productivity(metrics):
    """Save domain productivity scores — one row per source type per calculation."""
    conn = get_connection()
    cursor = conn.cursor()
    for m in metrics:
        cursor.execute("""
            INSERT INTO domain_productivity (source_type, facts_count,
                hypotheses_survived, productivity_score)
            VALUES (?, ?, ?, ?)
        """, (m["source_type"], m["facts_count"],
              m["hypotheses_survived"], m["productivity_score"]))
    conn.commit()
    conn.close()


def get_latest_domain_productivity():
    """Get most recent productivity scores. Returns {source_type: productivity_score}."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT source_type, productivity_score
        FROM domain_productivity
        WHERE calculated_at = (SELECT MAX(calculated_at) FROM domain_productivity)
    """)
    rows = cursor.fetchall()
    conn.close()
    return {row["source_type"]: row["productivity_score"] for row in rows}


def get_recent_hypothesis_domain_pairs(n):
    """Get source type sets from last n survived hypotheses.
    Returns list of sets, most recent first."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.source_types
        FROM hypotheses h
        JOIN collisions c ON h.collision_id = c.id
        WHERE h.survived_kill = 1 AND c.source_types IS NOT NULL AND c.source_types != ''
        ORDER BY h.created_at DESC
        LIMIT ?
    """, (n,))
    rows = cursor.fetchall()
    conn.close()
    pairs = []
    for row in rows:
        st = row["source_types"]
        if st:
            types = frozenset(t.strip() for t in st.split(",") if t.strip())
            pairs.append(types)
    return pairs


def save_hypothesis(collision_id, hypothesis_text, fact_chain, action_steps,
                    time_window_days, kill_attempts, survived_kill,
                    diamond_score=None, novelty=None, feasibility=None,
                    timing=None, asymmetry=None, intersection=None,
                    confidence=None, full_report=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO hypotheses (collision_id, hypothesis_text, fact_chain,
            action_steps, time_window_days, kill_attempts, survived_kill,
            diamond_score, novelty, feasibility, timing, asymmetry,
            intersection, confidence, full_report)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (collision_id, hypothesis_text,
          json.dumps(fact_chain) if isinstance(fact_chain, (list, dict)) else fact_chain,
          action_steps, time_window_days,
          json.dumps(kill_attempts) if isinstance(kill_attempts, list) else kill_attempts,
          1 if survived_kill else 0,
          diamond_score, novelty, feasibility, timing, asymmetry,
          intersection, confidence, full_report))
    hypothesis_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return hypothesis_id


def get_recent_anomalies(days=7, exclude_recently_attempted=True):
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT a.*, rf.title as fact_title, rf.raw_content as fact_content,
               rf.source_type, rf.entities as fact_entities, rf.keywords as fact_keywords,
               rf.implications as fact_implications, rf.model_vulnerability as fact_model_vulnerability,
               rf.reflexivity_tag as fact_reflexivity_tag, rf.market_belief as fact_market_belief,
               rf.raw_content as fact_raw_content
        FROM anomalies a
        JOIN raw_facts rf ON a.raw_fact_id = rf.id
        WHERE a.created_at >= datetime('now', ?)
    """
    params = [f"-{days} days"]
    if exclude_recently_attempted:
        query += " AND (a.last_collision_attempt IS NULL OR a.last_collision_attempt < datetime('now', '-1 hours'))"
    query += " ORDER BY a.weirdness_score DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_anomaly_attempted(anomaly_id):
    """Mark an anomaly as having been attempted for collision detection."""
    conn = get_connection()
    conn.execute(
        "UPDATE anomalies SET last_collision_attempt = datetime('now') WHERE id = ?",
        (anomaly_id,)
    )
    conn.commit()
    conn.close()


def get_recent_facts(days=30):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM raw_facts
        WHERE ingested_at >= datetime('now', ?)
        ORDER BY ingested_at DESC
        LIMIT 500
    """, (f"-{days} days",))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_facts_count(days=30):
    """Return just the count of recent facts, without loading all rows."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) as total FROM raw_facts
        WHERE ingested_at >= datetime('now', ?)
    """, (f"-{days} days",))
    count = cursor.fetchone()["total"]
    conn.close()
    return count


def get_facts_by_ids(fact_ids):
    if not fact_ids:
        return []
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(fact_ids))
    cursor.execute(f"SELECT * FROM raw_facts WHERE id IN ({placeholders})", fact_ids)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_facts_by_entities(entities, exclude_source_type=None, days=30):
    """Find facts that mention any of the given entities, using the fact_entities junction table."""
    if not entities:
        return []
    conn = get_connection()
    cursor = conn.cursor()

    normalized = []
    for entity in entities:
        ent = entity.strip().lower()
        if len(ent) < 3:
            continue
        normalized.append(ent)

    if not normalized:
        conn.close()
        return []

    placeholders = ",".join(["?"] * len(normalized))
    params = list(normalized)

    query = f"""
        SELECT DISTINCT rf.* FROM raw_facts rf
        JOIN fact_entities fe ON fe.raw_fact_id = rf.id
        WHERE fe.entity_name_lower IN ({placeholders})
        AND rf.ingested_at >= datetime('now', ?)
    """
    params.append(f"-{days} days")

    if exclude_source_type:
        query += " AND rf.source_type != ?"
        params.append(exclude_source_type)

    query += " ORDER BY RANDOM() LIMIT 50"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_facts_by_keywords(keywords, days=30):
    if not keywords:
        return []
    conn = get_connection()
    cursor = conn.cursor()

    conditions = []
    params = []
    for kw in keywords:
        kw_clean = kw.strip().lower()
        if len(kw_clean) < 3:
            continue
        conditions.append("(LOWER(keywords) LIKE ? OR LOWER(title) LIKE ? OR LOWER(raw_content) LIKE ?)")
        pattern = f"%{kw_clean}%"
        params.extend([pattern, pattern, pattern])

    if not conditions:
        conn.close()
        return []

    where = " OR ".join(conditions)
    query = f"""
        SELECT * FROM raw_facts
        WHERE ({where})
        AND ingested_at >= datetime('now', ?)
        ORDER BY ingested_at DESC LIMIT 50
    """
    params.append(f"-{days} days")
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_facts_by_implications(implications, exclude_source_type=None, days=30):
    """Find facts whose implications overlap with the given implications.

    This is the key to finding structural connections between facts that
    share no surface-level entities. A silver restriction implies "silver
    substitutes gain advantage" and a bismuth patent implies "solar can
    bypass silver" -- they share an implication even though they share
    zero entities.
    """
    if not implications:
        return []
    conn = get_connection()
    cursor = conn.cursor()

    # Extract search terms from implications at multiple levels:
    # 1. Key professional terms (FDA, ANDA, CMS, PTAB, etc.)
    # 2. Named actors (company names, agencies)
    # 3. Mechanism phrases (2-3 word professional concepts)
    import re as _re
    search_terms = []
    stop_words = {"the", "a", "an", "for", "and", "or", "in", "of", "to", "is", "are",
                  "can", "may", "will", "that", "this", "then", "if", "by", "from",
                  "with", "would", "because", "don't", "don", "their", "they", "but",
                  "neither", "nor", "each", "hold", "half", "tracked", "creating",
                  "analysts", "specialists", "community", "communities", "professional"}

    for imp in implications:
        if not imp or not isinstance(imp, str):
            continue
        imp_lower = imp.strip().lower()

        # Extract named actors (capitalized words in original)
        actors = _re.findall(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', imp)
        for actor in actors:
            if len(actor) > 4 and actor.lower() not in stop_words:
                search_terms.append(actor.lower())

        # Extract professional acronyms and terms (FDA, ANDA, CMS, PTAB, CDER, etc.)
        acronyms = _re.findall(r'\b[A-Z]{2,6}\b', imp)
        for acr in acronyms:
            if acr.lower() not in {"if", "or", "and", "the", "not"}:
                search_terms.append(acr.lower())

        # Extract 2-3 word mechanism phrases
        words = imp_lower.split()
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            if len(bigram) > 8 and words[i] not in stop_words and words[i+1] not in stop_words:
                search_terms.append(bigram)

        # Extract 3-word phrases for more specific matching
        for i in range(len(words) - 2):
            trigram = f"{words[i]} {words[i+1]} {words[i+2]}"
            if len(trigram) > 12 and words[i] not in stop_words and words[i+2] not in stop_words:
                search_terms.append(trigram)

    # Deduplicate and prioritise longer, more specific terms
    search_terms = list(dict.fromkeys(search_terms))
    search_terms.sort(key=len, reverse=True)

    if not search_terms:
        conn.close()
        return []

    # Search implications column for overlapping terms
    conditions = []
    params = []
    for term in search_terms[:15]:  # Cap at 15 to keep query manageable
        conditions.append("LOWER(implications) LIKE ?")
        params.append(f"%{term}%")

    if not conditions:
        conn.close()
        return []

    where = " OR ".join(conditions)
    query = f"""
        SELECT *, (
            {' + '.join(f"(CASE WHEN LOWER(implications) LIKE ? THEN 1 ELSE 0 END)" for _ in search_terms[:15])}
        ) as match_score
        FROM raw_facts
        WHERE ({where})
        AND implications != '[]'
        AND ingested_at >= datetime('now', ?)
    """
    # Add params for the match_score calculation
    for term in search_terms[:15]:
        params.append(f"%{term}%")
    params.append(f"-{days} days")

    if exclude_source_type:
        query += " AND source_type != ?"
        params.append(exclude_source_type)

    query += " ORDER BY match_score DESC, RANDOM() LIMIT 50"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_facts_by_model_fields(model_vulnerability, exclude_source_type=None, days=30):
    """Strategy 4: Find facts whose model_vulnerability fields overlap with the anchor's.

    The key insight: one fact's DISRUPTION is another fact's broken ASSUMPTION.
    A patent that disrupts "assumes regulatory compliance costs < $2/ton" should match
    a CRE model whose assumption is "compliance costs immaterial" — even with zero
    shared entities and zero shared keywords.

    Cross-matches:
    - anchor assumption  ↔  other facts' assumption (same broken model)
    - anchor methodology ↔  other facts' methodology (same model affected)
    - anchor disruption  ↔  other facts' assumption (one breaks the other)
    """
    if not model_vulnerability or not isinstance(model_vulnerability, dict):
        return []

    import re as _re
    conn = get_connection()
    cursor = conn.cursor()

    stop_words = {"the", "a", "an", "for", "and", "or", "in", "of", "to", "is", "are",
                  "can", "may", "will", "that", "this", "then", "if", "by", "from",
                  "with", "would", "because", "their", "they", "but", "not", "all",
                  "some", "most", "many", "each", "using", "based", "standard", "specific"}

    def _extract_terms(text):
        """Extract search terms from a model vulnerability field value."""
        if not text or not isinstance(text, str):
            return []
        terms = []
        text_lower = text.strip().lower()

        # Professional acronyms (FDA, NAIC, ARGUS, DSCR, etc.)
        acronyms = _re.findall(r'\b[A-Z]{2,6}\b', text)
        for acr in acronyms:
            if acr.lower() not in stop_words:
                terms.append(acr.lower())

        # Named models/frameworks (capitalized multi-word)
        actors = _re.findall(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', text)
        for actor in actors:
            if len(actor) > 4:
                terms.append(actor.lower())

        # Bigrams
        words = text_lower.split()
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            if len(bigram) > 8 and words[i] not in stop_words and words[i+1] not in stop_words:
                terms.append(bigram)

        return terms

    # Build search terms from anchor's fields
    # Cross-match: disruption terms search against assumption fields, and vice versa
    search_pairs = []  # (term, target_field_types)

    for field in ("assumption", "methodology"):
        val = model_vulnerability.get(field, "")
        for term in _extract_terms(val):
            search_pairs.append((term, [field]))  # Same field match

    # Cross-domain key: anchor's disruption matches other facts' assumptions
    disruption_val = model_vulnerability.get("disruption", "")
    for term in _extract_terms(disruption_val):
        search_pairs.append((term, ["assumption"]))  # Disruption → Assumption bridge

    if not search_pairs:
        conn.close()
        return []

    # Deduplicate terms, cap at 12
    seen = set()
    unique_pairs = []
    for term, fields in search_pairs:
        if term not in seen:
            seen.add(term)
            unique_pairs.append((term, fields))
    unique_pairs.sort(key=lambda x: len(x[0]), reverse=True)
    unique_pairs = unique_pairs[:12]

    # Query fact_model_fields for matches, join back to raw_facts
    conditions = []
    params = []
    for term, field_types in unique_pairs:
        field_filter = " OR ".join(f"fmf.field_type = ?" for _ in field_types)
        conditions.append(f"(({field_filter}) AND fmf.field_value_lower LIKE ?)")
        params.extend(field_types)
        params.append(f"%{term}%")

    if not conditions:
        conn.close()
        return []

    where = " OR ".join(conditions)

    # Count matching conditions for scoring
    score_parts = []
    score_params = []
    for term, field_types in unique_pairs:
        field_filter = " OR ".join(f"fmf2.field_type = ?" for _ in field_types)
        score_parts.append(f"(CASE WHEN EXISTS (SELECT 1 FROM fact_model_fields fmf2 WHERE fmf2.raw_fact_id = rf.id AND ({field_filter}) AND fmf2.field_value_lower LIKE ?) THEN 1 ELSE 0 END)")
        score_params.extend(field_types)
        score_params.append(f"%{term}%")

    query = f"""
        SELECT DISTINCT rf.*, (
            {' + '.join(score_parts)}
        ) as match_score
        FROM raw_facts rf
        INNER JOIN fact_model_fields fmf ON rf.id = fmf.raw_fact_id
        WHERE ({where})
        AND rf.ingested_at >= datetime('now', ?)
    """
    all_params = score_params + params
    all_params.append(f"-{days} days")

    if exclude_source_type:
        query += " AND rf.source_type != ?"
        all_params.append(exclude_source_type)

    query += " ORDER BY match_score DESC, RANDOM() LIMIT 50"
    cursor.execute(query, all_params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# Causal Graph Operations (Branch 2)
# ============================================================

def save_causal_edges(fact_id, edges, source_type, domain):
    """Save causal edges extracted from a fact."""
    if not edges:
        return
    conn = get_connection()
    cursor = conn.cursor()
    for edge in edges:
        cause = (edge.get("cause", "") or "").strip()
        effect = (edge.get("effect", "") or "").strip()
        if not cause or not effect or len(cause) < 3 or len(effect) < 3:
            continue
        strength = edge.get("strength", "moderate")
        if strength not in ("strong", "moderate", "weak"):
            strength = "moderate"
        mechanism = (edge.get("mechanism", "") or "").strip()
        cursor.execute("""
            INSERT INTO causal_edges
            (source_fact_id, cause_node, effect_node, cause_node_lower, effect_node_lower,
             relationship_type, confidence, source_type, domain, strength, mechanism)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (fact_id, cause, effect, cause.lower(), effect.lower(),
              edge.get("relationship", "causes"),
              min(1.0, max(0.0, float(edge.get("confidence", 0.8)))),
              source_type, domain, strength, mechanism))
    conn.commit()
    conn.close()


def find_causal_paths(start_nodes, max_hops=4, exclude_source_type=None):
    """BFS through causal_edges to find multi-hop paths crossing domain boundaries.
    Returns list of paths, each path = list of edge dicts."""
    conn = get_connection()
    cursor = conn.cursor()

    visited = set()
    queue = []

    for node in start_nodes:
        node_lower = node.strip().lower()
        queue.append((node_lower, [], set()))
        visited.add(node_lower)

    all_paths = []

    while queue:
        current, path, domains = queue.pop(0)
        if len(path) >= max_hops:
            continue

        query = "SELECT * FROM causal_edges WHERE cause_node_lower = ?"
        params = [current]
        if exclude_source_type:
            query += " AND source_type != ?"
            params.append(exclude_source_type)
        query += " LIMIT 20"
        cursor.execute(query, params)
        rows = cursor.fetchall()

        for row in rows:
            edge = dict(row)
            next_node = edge["effect_node_lower"]
            new_domains = domains | {edge.get("source_type", "unknown")}
            new_path = path + [edge]

            if len(new_domains) >= 2:
                all_paths.append(new_path)

            if next_node not in visited and len(all_paths) < 50:
                visited.add(next_node)
                queue.append((next_node, new_path, new_domains))

    conn.close()
    return all_paths


def find_contradictory_paths(node_lower):
    """Find pairs of causal edges that predict OPPOSITE effects on the same node.
    Returns list of (positive_edge, negative_edge, node) tuples."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM causal_edges WHERE effect_node_lower = ? LIMIT 30",
                   (node_lower,))
    incoming = [dict(r) for r in cursor.fetchall()]
    conn.close()

    positive = [e for e in incoming if e["relationship_type"] in ("increases", "causes", "enables", "accelerates")]
    negative = [e for e in incoming if e["relationship_type"] in ("decreases", "prevents", "inhibits")]

    contradictions = []
    for pos in positive:
        for neg in negative:
            if pos["source_type"] != neg["source_type"]:
                contradictions.append((pos, neg, node_lower))
    return contradictions


def get_collision_counts_by_source_pair():
    """Get collision counts per source_type pair for gap analysis (Branch 5)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT source_types, COUNT(*) as cnt
        FROM collisions
        WHERE source_types IS NOT NULL AND source_types != ''
        GROUP BY source_types
    """)
    rows = cursor.fetchall()
    conn.close()

    pair_counts = {}
    for row in rows:
        types = [t.strip() for t in row["source_types"].split(",") if t.strip()]
        for i in range(len(types)):
            for j in range(i + 1, len(types)):
                pair = tuple(sorted([types[i], types[j]]))
                pair_counts[pair] = pair_counts.get(pair, 0) + row["cnt"]
    return pair_counts


# ============================================================
# Embedding Operations (Branch 1)
# ============================================================

def save_fact_embedding(fact_id, embedding_bytes):
    """Save precomputed embedding BLOB for a fact."""
    conn = get_connection()
    conn.execute("UPDATE raw_facts SET implication_embedding = ? WHERE id = ?",
                 (embedding_bytes, fact_id))
    conn.commit()
    conn.close()


def search_facts_by_embedding(query_embedding_bytes, exclude_source_type=None, days=30, k=50):
    """Strategy 6: Cosine similarity search weighted by domain distance.
    Returns top-k facts ranked by (cosine_similarity * domain_distance).
    This literally searches for 'same consequence, different world.'"""
    try:
        import numpy as np
    except ImportError:
        return []

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT id, source_type, title, raw_content, entities, keywords, domain,
               country, date_of_fact, obscurity, implications, model_vulnerability,
               reflexivity_tag, ingested_at, implication_embedding
        FROM raw_facts
        WHERE implication_embedding IS NOT NULL
        AND ingested_at >= datetime('now', ?)
    """
    params = [f"-{days} days"]
    if exclude_source_type:
        query += " AND source_type != ?"
        params.append(exclude_source_type)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return []

    query_vec = np.frombuffer(query_embedding_bytes, dtype=np.float32)
    scored = []
    for row in rows:
        row_dict = dict(row)
        emb_bytes = row_dict.pop("implication_embedding")
        if not emb_bytes:
            continue
        fact_vec = np.frombuffer(emb_bytes, dtype=np.float32)
        similarity = float(np.dot(query_vec, fact_vec))
        if exclude_source_type:
            from config import get_domain_distance
            distance = get_domain_distance(exclude_source_type, row_dict.get("source_type", "unknown"))
        else:
            distance = 0.5
        combined = similarity * (0.3 + 0.7 * distance)
        scored.append((combined, row_dict))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:k]]


def search_facts_with_beliefs_for_asset(asset_keywords, exclude_source_type=None, days=30, limit=20):
    """Find facts that have a market_belief matching asset keywords.
    Used to find endogenous beliefs that an exogenous fact could contradict."""
    conn = get_connection()
    cursor = conn.cursor()
    conditions = ["market_belief IS NOT NULL", "market_belief != 'null'",
                   "ingested_at >= datetime('now', ?)"]
    params = [f"-{days} days"]
    if exclude_source_type:
        conditions.append("source_type != ?")
        params.append(exclude_source_type)

    # Match any keyword against the market_belief JSON text
    keyword_clauses = []
    for kw in asset_keywords[:5]:
        kw = kw.strip().lower()
        if len(kw) > 2:
            keyword_clauses.append("LOWER(market_belief) LIKE ?")
            params.append(f"%{kw}%")
    if not keyword_clauses:
        conn.close()
        return []
    conditions.append(f"({' OR '.join(keyword_clauses)})")

    query = f"""
        SELECT id, source_type, title, raw_content, entities, keywords, domain,
               country, date_of_fact, obscurity, implications, model_vulnerability,
               reflexivity_tag, market_belief, ingested_at
        FROM raw_facts
        WHERE {' AND '.join(conditions)}
        ORDER BY ingested_at DESC
        LIMIT ?
    """
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_exogenous_facts_for_belief(belief_keywords, exclude_source_type=None, days=30, limit=20):
    """Find exogenous facts that could contradict a market belief.
    Searches for facts tagged 'exogenous' whose content matches belief keywords."""
    conn = get_connection()
    cursor = conn.cursor()
    conditions = ["reflexivity_tag = 'exogenous'",
                   "ingested_at >= datetime('now', ?)"]
    params = [f"-{days} days"]
    if exclude_source_type:
        conditions.append("source_type != ?")
        params.append(exclude_source_type)

    # Match keywords against title + raw_content
    keyword_clauses = []
    for kw in belief_keywords[:5]:
        kw = kw.strip().lower()
        if len(kw) > 2:
            keyword_clauses.append("(LOWER(title) LIKE ? OR LOWER(raw_content) LIKE ?)")
            params.extend([f"%{kw}%", f"%{kw}%"])
    if not keyword_clauses:
        conn.close()
        return []
    conditions.append(f"({' OR '.join(keyword_clauses)})")

    query = f"""
        SELECT id, source_type, title, raw_content, entities, keywords, domain,
               country, date_of_fact, obscurity, implications, model_vulnerability,
               reflexivity_tag, market_belief, ingested_at
        FROM raw_facts
        WHERE {' AND '.join(conditions)}
        ORDER BY ingested_at DESC
        LIMIT ?
    """
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_raw_facts_stream(limit=100, source_type=None):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT rf.*, (SELECT COUNT(*) FROM anomalies a WHERE a.raw_fact_id = rf.id) as anomaly_count FROM raw_facts rf"
    params = []
    if source_type:
        query += " WHERE rf.source_type = ?"
        params.append(source_type)
    query += " ORDER BY rf.ingested_at DESC LIMIT ?"
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def toggle_reviewed(table, item_id, reviewed):
    """Toggle the reviewed status of a hypothesis or held collision."""
    if table not in ("hypotheses", "held_collisions"):
        return
    conn = get_connection()
    conn.execute(f"UPDATE {table} SET reviewed = ? WHERE id = ?", (1 if reviewed else 0, item_id))
    conn.commit()
    conn.close()


def get_held_collisions_list(limit=100):
    """Get held collisions — passed evaluation but failed the search gate."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM held_collisions
        ORDER BY created_at DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_held_collisions_count():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM held_collisions")
    total = cursor.fetchone()["total"]
    conn.close()
    return total


def get_collisions_list(limit=50):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*,
               (SELECT COUNT(*) FROM hypotheses h WHERE h.collision_id = c.id) as hypothesis_count,
               (SELECT COUNT(*) FROM hypotheses h WHERE h.collision_id = c.id AND h.survived_kill = 1) as survived_count
        FROM collisions c
        ORDER BY c.created_at DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_hypotheses_list(min_score=0, survived_only=True, limit=100):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM hypotheses WHERE 1=1"
    params = []
    if survived_only:
        query += " AND survived_kill = 1"
    if min_score > 0:
        query += " AND diamond_score >= ?"
        params.append(min_score)
    query += " ORDER BY diamond_score DESC LIMIT ?"
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_hypothesis_with_chain(hypothesis_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,))
    hyp = cursor.fetchone()
    if not hyp:
        conn.close()
        return None
    hyp = dict(hyp)

    # Get collision
    cursor.execute("SELECT * FROM collisions WHERE id = ?", (hyp["collision_id"],))
    collision = cursor.fetchone()
    hyp["collision"] = dict(collision) if collision else None

    # Get contributing facts
    if collision:
        fact_ids = json.loads(collision["fact_ids"])
        if fact_ids:
            placeholders = ",".join(["?"] * len(fact_ids))
            cursor.execute(f"SELECT * FROM raw_facts WHERE id IN ({placeholders})", fact_ids)
            hyp["facts"] = [dict(r) for r in cursor.fetchall()]
        else:
            hyp["facts"] = []

        anomaly_ids = json.loads(collision["anomaly_ids"] or "[]")
        if anomaly_ids:
            placeholders = ",".join(["?"] * len(anomaly_ids))
            cursor.execute(f"SELECT * FROM anomalies WHERE id IN ({placeholders})", anomaly_ids)
            hyp["anomalies"] = [dict(r) for r in cursor.fetchall()]
        else:
            hyp["anomalies"] = []

    conn.close()
    return hyp


def is_collision_duplicate(fact_ids, similarity_threshold=0.5):
    """Check if a collision with substantially overlapping fact IDs already exists."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT fact_ids FROM collisions")
    rows = cursor.fetchall()
    conn.close()

    new_set = set(fact_ids)
    for row in rows:
        try:
            existing_set = set(json.loads(row["fact_ids"]))
            if not existing_set or not new_set:
                continue
            overlap = len(new_set & existing_set) / max(len(new_set), len(existing_set))
            if overlap >= similarity_threshold:
                return True
        except (json.JSONDecodeError, TypeError):
            continue
    return False


def get_collision_to_hypothesis_rate():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM collisions")
    total_collisions = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) as total FROM hypotheses")
    total_hypotheses = cursor.fetchone()["total"]
    conn.close()
    if total_collisions == 0:
        return 0.0
    return total_hypotheses / total_collisions


def get_knowledge_base_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM raw_facts")
    total_facts = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(*) as total FROM anomalies")
    total_anomalies = cursor.fetchone()["total"]
    cursor.execute("SELECT COUNT(DISTINCT entity_name_lower) as total FROM fact_entities")
    unique_entities = cursor.fetchone()["total"]
    conn.close()
    return {
        "total_facts": total_facts,
        "total_anomalies": total_anomalies,
        "unique_entities": unique_entities,
    }


def get_source_type_counts(hours=24):
    """Get count of facts ingested per source type in the last N hours."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT source_type, COUNT(*) as cnt
        FROM raw_facts
        WHERE ingested_at >= datetime('now', ?)
        GROUP BY source_type
    """, (f"-{hours} hours",))
    rows = cursor.fetchall()
    conn.close()
    return {row["source_type"]: row["cnt"] for row in rows}


def get_v2_dashboard_stats():
    conn = get_connection()
    cursor = conn.cursor()
    stats = {}

    cursor.execute("SELECT COUNT(*) as total FROM raw_facts")
    stats["total_facts"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM raw_facts WHERE date(ingested_at) = date('now')")
    stats["facts_today"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM anomalies")
    stats["total_anomalies"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM anomalies WHERE date(created_at) = date('now')")
    stats["anomalies_today"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM collisions")
    stats["total_collisions"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM hypotheses")
    stats["total_hypotheses"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM hypotheses WHERE survived_kill = 1")
    stats["survived_hypotheses"] = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM hypotheses WHERE survived_kill = 0")
    stats["killed_hypotheses"] = cursor.fetchone()["total"]

    cursor.execute("SELECT MAX(diamond_score) as best FROM hypotheses WHERE survived_kill = 1")
    row = cursor.fetchone()
    stats["best_score"] = row["best"] if row["best"] else 0

    conn.close()
    return stats


def get_source_type_diversity_score():
    """Return a dict showing how evenly distributed facts are across source types.

    Returns a dict with each source_type mapped to its proportion of total facts.
    Example: {"arxiv": 0.35, "news": 0.40, "patent": 0.25}
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM raw_facts")
    total = cursor.fetchone()["total"]
    if total == 0:
        conn.close()
        return {}
    cursor.execute("""
        SELECT source_type, COUNT(*) as cnt
        FROM raw_facts
        GROUP BY source_type
    """)
    rows = cursor.fetchall()
    conn.close()
    return {row["source_type"]: row["cnt"] / total for row in rows}


# ============================================================
# Portfolio functions
# ============================================================

def get_unlogged_hypotheses(min_score=50):
    """Return survived hypotheses with score >= min_score not yet in portfolio."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT h.*, c.domains_involved
        FROM hypotheses h
        LEFT JOIN collisions c ON h.collision_id = c.id
        LEFT JOIN portfolio_positions pp ON pp.hypothesis_id = h.id
        WHERE h.survived_kill = 1
          AND h.diamond_score >= ?
          AND pp.id IS NULL
        ORDER BY h.diamond_score DESC
    """, (min_score,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_portfolio_position(hypothesis_id, ticker, direction, entry_price, entry_date,
                            capital_allocated, time_window_days, diamond_score, confidence,
                            hypothesis_text, full_report, domains):
    """Insert a new open position. Returns position id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO portfolio_positions (hypothesis_id, ticker, direction, entry_price,
            entry_date, current_price, current_date, capital_allocated, time_window_days,
            diamond_score, confidence, hypothesis_text, full_report, domains)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (hypothesis_id, ticker, direction, entry_price, entry_date,
          entry_price, entry_date, capital_allocated, time_window_days,
          diamond_score, confidence, hypothesis_text, full_report, domains))
    pos_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return pos_id


def get_open_positions():
    """Return all open positions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM portfolio_positions WHERE status = 'open' ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_closed_positions():
    """Return all closed positions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM portfolio_positions WHERE status = 'closed' ORDER BY close_date DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_positions():
    """Return all positions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM portfolio_positions ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_position_price(position_id, current_price, current_date, pnl_pct, pnl_gbp):
    """Update live price and P&L for an open position."""
    conn = get_connection()
    conn.execute("""
        UPDATE portfolio_positions
        SET current_price = ?, current_date = ?, pnl_pct = ?, pnl_gbp = ?
        WHERE id = ?
    """, (current_price, current_date, pnl_pct, pnl_gbp, position_id))
    conn.commit()
    conn.close()


def close_position(position_id, close_price, close_date, close_reason, pnl_pct, pnl_gbp):
    """Close a position."""
    conn = get_connection()
    conn.execute("""
        UPDATE portfolio_positions
        SET status = 'closed', close_price = ?, close_date = ?, close_reason = ?,
            pnl_pct = ?, pnl_gbp = ?, current_price = ?, current_date = ?
        WHERE id = ?
    """, (close_price, close_date, close_reason, pnl_pct, pnl_gbp,
          close_price, close_date, position_id))
    conn.commit()
    conn.close()


def save_portfolio_snapshot(date, total_value, total_return_pct, spy_return_pct,
                            num_open, num_closed, win_rate):
    """Insert or replace a daily portfolio snapshot."""
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO portfolio_snapshots
            (date, total_value, total_return_pct, spy_return_pct, num_open, num_closed, win_rate)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (date, total_value, total_return_pct, spy_return_pct, num_open, num_closed, win_rate))
    conn.commit()
    conn.close()


def get_portfolio_snapshots(limit=365):
    """Return snapshots ordered by date."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM portfolio_snapshots ORDER BY date DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_portfolio_stats():
    """Aggregate portfolio stats."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as cnt FROM portfolio_positions WHERE status = 'open'")
    num_open = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM portfolio_positions WHERE status = 'closed'")
    num_closed = cursor.fetchone()["cnt"]

    cursor.execute("SELECT COUNT(*) as cnt FROM portfolio_positions WHERE status = 'closed' AND pnl_pct > 0")
    wins = cursor.fetchone()["cnt"]

    win_rate = (wins / num_closed * 100) if num_closed > 0 else 0.0

    cursor.execute("SELECT SUM(pnl_gbp) as total_pnl FROM portfolio_positions")
    total_pnl = cursor.fetchone()["total_pnl"] or 0.0

    cursor.execute("SELECT MAX(pnl_pct) as best FROM portfolio_positions WHERE status = 'closed'")
    best = cursor.fetchone()["best"] or 0.0

    cursor.execute("SELECT MIN(pnl_pct) as worst FROM portfolio_positions WHERE status = 'closed'")
    worst = cursor.fetchone()["worst"] or 0.0

    cursor.execute("SELECT AVG(pnl_pct) as avg FROM portfolio_positions WHERE status = 'closed'")
    avg_return = cursor.fetchone()["avg"] or 0.0

    conn.close()
    return {
        "num_open": num_open,
        "num_closed": num_closed,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "total_value": 1_000_000 + total_pnl,
        "total_return_pct": (total_pnl / 1_000_000) * 100,
        "best_trade": best,
        "worst_trade": worst,
        "avg_return": avg_return,
    }


# ============================================================
# Targeting functions
# ============================================================

def get_active_targets():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM targets WHERE active = 1 ORDER BY weight DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_target(firm_name, weight=1.0, verticals="", focus_domains="", notes=""):
    conn = get_connection()
    conn.execute("""
        INSERT INTO targets (firm_name, weight, verticals, focus_domains, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (firm_name, weight, verticals, focus_domains, notes))
    conn.commit()
    conn.close()


def remove_target(target_id):
    conn = get_connection()
    conn.execute("UPDATE targets SET active = 0 WHERE id = ?", (target_id,))
    conn.commit()
    conn.close()


def get_firm_suggestions(hypothesis_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT firms_json FROM firm_suggestions WHERE hypothesis_id = ?", (hypothesis_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row["firms_json"]:
        try:
            return json.loads(row["firms_json"])
        except:
            return None
    return None


# === Theory Run Telemetry Functions ===

def update_hypothesis_telemetry(hypothesis_id, **kwargs):
    """Update telemetry columns on a hypothesis via UPDATE (not INSERT modification)."""
    if not kwargs:
        return
    conn = get_connection()
    sets = []
    values = []
    for col, val in kwargs.items():
        sets.append(f"{col} = ?")
        values.append(json.dumps(val) if isinstance(val, (dict, list)) else val)
    values.append(hypothesis_id)
    conn.execute(f"UPDATE hypotheses SET {', '.join(sets)} WHERE id = ?", values)
    conn.commit()
    conn.close()


def save_edge_recovery_event(hypothesis_id, original_thesis_text, original_awareness_level,
                             killed_at_score, novel_subelement_found, recovered_thesis_text=None,
                             recovered_awareness_level=None, recovered_score=None,
                             delta_awareness=None, delta_score=None):
    conn = get_connection()
    conn.execute("""
        INSERT INTO edge_recovery_events (hypothesis_id, original_thesis_text,
            original_awareness_level, killed_at_score, novel_subelement_found,
            recovered_thesis_text, recovered_awareness_level, recovered_score,
            delta_awareness, delta_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (hypothesis_id, original_thesis_text, original_awareness_level,
          killed_at_score, 1 if novel_subelement_found else 0,
          recovered_thesis_text, recovered_awareness_level, recovered_score,
          delta_awareness, delta_score))
    conn.commit()
    conn.close()


def save_theory_run_cycle(cycle_num, wall_clock_seconds, tokens_used,
                          collisions_generated, hypotheses_scored,
                          hypotheses_survived, estimated_cost_usd,
                          collision_mode=None, stratum=None):
    conn = get_connection()
    conn.execute("""
        INSERT INTO theory_run_cycles (cycle_num, wall_clock_seconds, tokens_used,
            collisions_generated, hypotheses_scored, hypotheses_survived, estimated_cost_usd,
            collision_mode, stratum)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cycle_num, wall_clock_seconds, tokens_used,
          collisions_generated, hypotheses_scored, hypotheses_survived, estimated_cost_usd,
          collision_mode, stratum))
    conn.commit()
    conn.close()


def export_theory_run_data():
    """Export all theory run data as a dict for JSON serialization."""
    conn = get_connection()
    cursor = conn.cursor()

    # All hypotheses with telemetry columns
    cursor.execute("""
        SELECT id, collision_id, hypothesis_text, fact_chain, action_steps,
               time_window_days, kill_attempts, survived_kill, diamond_score,
               novelty, feasibility, timing, asymmetry, intersection, confidence,
               created_at, market_awareness_telemetry, facts_per_domain,
               min_depth, max_depth, domain_count, depth_concentration
        FROM hypotheses
        ORDER BY created_at DESC
    """)
    hypotheses = []
    for row in cursor.fetchall():
        h = dict(row)
        for json_col in ("fact_chain", "kill_attempts", "market_awareness_telemetry", "facts_per_domain"):
            if h.get(json_col):
                try:
                    h[json_col] = json.loads(h[json_col])
                except (json.JSONDecodeError, TypeError):
                    pass
        hypotheses.append(h)

    # Edge recovery events
    cursor.execute("SELECT * FROM edge_recovery_events ORDER BY recovery_attempted_at")
    edge_recovery = [dict(row) for row in cursor.fetchall()]

    # Cycle telemetry
    cursor.execute("SELECT * FROM theory_run_cycles ORDER BY cycle_num")
    cycles = [dict(row) for row in cursor.fetchall()]

    # Awareness distribution
    awareness_counts = {f"level_{i}": 0 for i in range(5)}
    surviving_awareness = []
    for h in hypotheses:
        tel = h.get("market_awareness_telemetry")
        if isinstance(tel, dict) and "awareness_level" in tel:
            level = tel["awareness_level"]
            key = f"level_{level}" if 0 <= level <= 4 else "level_0"
            awareness_counts[key] = awareness_counts.get(key, 0) + 1
            if h.get("survived_kill"):
                surviving_awareness.append(level)
    awareness_counts["mean_awareness_surviving"] = (
        sum(surviving_awareness) / len(surviving_awareness) if surviving_awareness else None
    )

    # Depth-breadth pairs (surviving only)
    depth_breadth = []
    for h in hypotheses:
        if h.get("survived_kill") and h.get("diamond_score"):
            depth_breadth.append({
                "hypothesis_id": h["id"],
                "score": h["diamond_score"],
                "min_depth": h.get("min_depth"),
                "max_depth": h.get("max_depth"),
                "domain_count": h.get("domain_count"),
                "depth_concentration": h.get("depth_concentration"),
            })

    # Self-contribution summary
    total_flags = 0
    flagged_examples = []
    total_sources_checked = 0
    for h in hypotheses:
        tel = h.get("market_awareness_telemetry")
        if isinstance(tel, dict):
            flags = tel.get("self_contribution_flags", [])
            total_flags += len(flags)
            total_sources_checked += len(tel.get("awareness_sources", []))
            for f in flags:
                flagged_examples.append({"hypothesis_id": h["id"], **f})

    conn.close()
    return {
        "hypotheses": hypotheses,
        "edge_recovery_events": edge_recovery,
        "theory_run_cycles": cycles,
        "awareness_distribution": awareness_counts,
        "depth_breadth_pairs": depth_breadth,
        "self_contribution_summary": {
            "total_flags": total_flags,
            "total_sources_checked": total_sources_checked,
            "flag_rate": total_flags / total_sources_checked if total_sources_checked > 0 else 0.0,
            "flagged_examples": flagged_examples,
        },
    }


def save_null_run(null_type, paired_real_hypothesis_id, primary_ticker, direction,
                  time_window_days, structured_prediction=None, validation_outcome=None,
                  realized_return_pct=None, sector_return_pct=None, residual_pct=None,
                  materialised=None, validation_method=None, daily_price_series=None):
    """Save a null baseline run (A, B, or C)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO null_runs (null_type, paired_real_hypothesis_id, primary_ticker,
            direction, time_window_days, structured_prediction, validation_outcome,
            realized_return_pct, sector_return_pct, residual_pct, materialised,
            validation_method, daily_price_series)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (null_type, paired_real_hypothesis_id, primary_ticker, direction,
          time_window_days,
          json.dumps(structured_prediction) if isinstance(structured_prediction, (dict, list)) else structured_prediction,
          json.dumps(validation_outcome) if isinstance(validation_outcome, (dict, list)) else validation_outcome,
          realized_return_pct, sector_return_pct, residual_pct,
          1 if materialised else (0 if materialised is not None else None),
          validation_method,
          json.dumps(daily_price_series) if isinstance(daily_price_series, (dict, list)) else daily_price_series))
    null_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return null_id


def get_null_runs_for_hypothesis(hypothesis_id):
    """Get all null runs paired with a specific hypothesis."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM null_runs WHERE paired_real_hypothesis_id = ? ORDER BY null_type",
                   (hypothesis_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_firm_suggestions(hypothesis_id, firms_json):
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO firm_suggestions (hypothesis_id, firms_json) VALUES (?, ?)",
                 (hypothesis_id, json.dumps(firms_json)))
    conn.commit()
    conn.close()


def save_overseer_report(report_text, suggestions, metrics):
    conn = get_connection()
    conn.execute("""
        INSERT INTO overseer_reports (report_text, suggestions_json, metrics_json)
        VALUES (?, ?, ?)
    """, (report_text, json.dumps(suggestions), json.dumps(metrics)))
    conn.commit()
    conn.close()


def get_latest_overseer_report():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM overseer_reports ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
