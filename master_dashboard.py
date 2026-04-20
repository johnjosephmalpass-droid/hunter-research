"""HUNTER master dashboard — 5 tabs, clean, fast.

Run:
    streamlit run master_dashboard.py
"""

import json
import sqlite3
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path

import pandas as pd
import streamlit as st

DB = Path(__file__).parent / "hunter.db"
MANIFEST = Path(__file__).parent / "preregistration.json"

st.set_page_config(page_title="HUNTER", layout="wide", page_icon="💎",
                   initial_sidebar_state="collapsed")

# ── Styling ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background: #0b0d12; }
    h1 { color: #FFD700; font-size: 2.0em; margin-bottom: 0; }
    h2 { color: #ff8800; border-bottom: 1px solid #262d3d; padding-bottom: 4px;
         font-size: 1.3em; }
    h3 { color: #FFD700; font-size: 1.05em; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background: #141821; border-radius: 8px 8px 0 0;
        padding: 8px 18px; color: #8892a3; font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background: #1a1d23; color: #FFD700;
        border-bottom: 2px solid #FFD700;
    }
    [data-testid="stMetricValue"] { color: #FFD700; font-size: 1.6em; }
    [data-testid="stMetricLabel"] { color: #8892a3; font-size: 0.85em; }
    [data-testid="stMetricDelta"] { color: #8892a3; font-size: 0.8em; }
    .stDataFrame { background: #141821; border-radius: 6px; }
    .stExpander { background: #141821; border: 1px solid #262d3d; }
    .zero-state {
        background: #141821; border-left: 3px solid #FFD700;
        padding: 14px 18px; border-radius: 6px; color: #8892a3;
    }
    hr { border-color: #262d3d; margin: 16px 0; }
</style>
""", unsafe_allow_html=True)


# ── DB helpers ──────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def sql(q, params=()):
    conn = sqlite3.connect(DB)
    try:
        return pd.read_sql_query(q, conn, params=params)
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()


@st.cache_data(ttl=30)
def sql_one(q, params=()):
    conn = sqlite3.connect(DB)
    try:
        row = conn.execute(q, params).fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        conn.close()


def zero_state(msg):
    st.markdown(f"<div class='zero-state'>{msg}</div>", unsafe_allow_html=True)


# ── Header ──────────────────────────────────────────────────────────────
col_h1, col_h2, col_h3 = st.columns([2, 1, 1])
with col_h1:
    st.markdown("# HUNTER")
    st.caption("Autonomous cross-silo research instrument · John Malpass · UCD · 2026")

# Timeline-aware phase indicator
try:
    from timeline import current_phase, next_phase, days_until_next_phase
    p = current_phase()
    nxt = next_phase()
    with col_h2:
        if p:
            st.metric(f"Phase [{p.id}]", p.name, delta=f"{p.days_remaining()}d left")
        elif nxt:
            st.metric("Next phase", nxt.name, delta=f"starts in {days_until_next_phase()}d")
        else:
            st.metric("Phase", "—")
    with col_h3:
        st.metric("System time", datetime.now().strftime("%H:%M:%S"),
                  delta=datetime.now().strftime("%Y-%m-%d"))
except Exception:
    with col_h2:
        st.metric("System time", datetime.now().strftime("%H:%M:%S"),
                  delta=datetime.now().strftime("%Y-%m-%d"))
    with col_h3:
        pass

# ── Hero row (always visible above tabs) ────────────────────────────────
hero_stats = {
    "Facts": sql_one("SELECT COUNT(*) FROM raw_facts") or 0,
    "Anomalies": sql_one("SELECT COUNT(*) FROM anomalies") or 0,
    "Collisions": sql_one("SELECT COUNT(*) FROM collisions") or 0,
    "Hypotheses": sql_one("SELECT COUNT(*) FROM hypotheses") or 0,
    "Survived": sql_one("SELECT COUNT(*) FROM hypotheses WHERE survived_kill=1") or 0,
    "Cycles": sql_one("SELECT COUNT(*) FROM detected_cycles") or 0,
    "Causal edges": sql_one("SELECT COUNT(*) FROM causal_edges") or 0,
}
hero_cols = st.columns(len(hero_stats))
for col, (label, val) in zip(hero_cols, hero_stats.items()):
    col.metric(label, f"{val:,}")

st.markdown("---")


# ── Tabs ────────────────────────────────────────────────────────────────
tab_overview, tab_findings, tab_knowledge, tab_theory, tab_ops = st.tabs([
    "🏠 Overview",
    "💎 Findings & Portfolio",
    "🧠 Knowledge Graph",
    "📐 Theory & Moat",
    "⚙️ Operations",
])


# ═══════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ═══════════════════════════════════════════════════════════════════════
with tab_overview:
    col_a, col_b = st.columns([2, 1])

    with col_a:
        st.markdown("## What's happening right now")
        recent = sql("""
            SELECT created_at, domain, status, error_message
            FROM cycle_logs
            ORDER BY id DESC
            LIMIT 10
        """)
        if not recent.empty:
            # Quick-read recent activity
            recent["created_at"] = pd.to_datetime(recent["created_at"])
            for _, r in recent.iterrows():
                t = r["created_at"].strftime("%m-%d %H:%M")
                emoji = "✓" if r["status"] == "completed" else ("⚠" if r["status"] == "rate_limit" else "✗")
                err = f" — {r['error_message'][:80]}" if r.get("error_message") else ""
                colour = "#4ade80" if r["status"] == "completed" else ("#FFD700" if r["status"] == "rate_limit" else "#f87171")
                st.markdown(
                    f"<div style='font-family: monospace; color: {colour}; font-size: 0.9em; margin: 3px 0;'>"
                    f"{t}  {emoji}  [{r['domain']}]  {r['status']}{err}"
                    f"</div>", unsafe_allow_html=True)
        else:
            zero_state("No cycles logged yet. Start HUNTER with `python run.py live`.")

    # Phase context panel (collapsible — gives context on what HUNTER SHOULD be doing now)
    try:
        from timeline import current_phase, next_phase, PHASES
        p = current_phase()
        with st.expander("📍 Current operational phase", expanded=(p is None or p.id == "alpha")):
            if p:
                st.markdown(f"### Phase [{p.id}] — **{p.name}**")
                st.caption(f"{p.start} → {p.end}  ·  {p.days_elapsed()}d elapsed  ·  {p.days_remaining()}d remaining")
                st.markdown(p.description)
                if p.key_milestones:
                    st.markdown("**Upcoming milestones:**")
                    today = datetime.now().date()
                    for m in p.key_milestones:
                        st.markdown(f"- {m}")
                flags = [f for f in ["run_continuously", "throttle_api", "prefer_short_windows",
                                      "public_board_active", "paper_push_active", "outreach_active"]
                         if getattr(p, f, False)]
                if flags:
                    st.caption(f"Active behaviour flags: `{'`  `'.join(flags)}`")
            else:
                nxt = next_phase()
                if nxt:
                    st.info(f"Between phases. Next: **{nxt.name}** starts {nxt.start} "
                            f"(in {(nxt.start - datetime.now().date()).days}d)")
    except Exception:
        pass

    with col_b:
        st.markdown("## Pipeline rates")
        total_cycles = sql_one("SELECT COUNT(*) FROM cycle_logs") or 0
        last_24h = sql_one("SELECT COUNT(*) FROM cycle_logs WHERE created_at >= datetime('now', '-1 day')") or 0
        last_1h = sql_one("SELECT COUNT(*) FROM cycle_logs WHERE created_at >= datetime('now', '-1 hour')") or 0

        st.metric("Total cycles run", f"{total_cycles:,}")
        st.metric("Last 24h", last_24h)
        st.metric("Last 1h", last_1h)

        # Success rate
        errors_24h = sql_one("SELECT COUNT(*) FROM cycle_logs WHERE status != 'completed' AND created_at >= datetime('now', '-1 day')") or 0
        success_rate = (last_24h - errors_24h) / max(1, last_24h)
        delta_color = "normal" if success_rate > 0.9 else "inverse"
        st.metric("Success rate (24h)", f"{success_rate:.0%}",
                  delta=f"{errors_24h} errors" if errors_24h else "clean",
                  delta_color=delta_color)

    st.markdown("---")
    st.markdown("## Funnel")
    facts = hero_stats["Facts"]
    anoms = hero_stats["Anomalies"]
    coll = hero_stats["Collisions"]
    hyps = hero_stats["Hypotheses"]
    surv = hero_stats["Survived"]
    findings = sql_one("SELECT COUNT(*) FROM findings") or 0

    funnel_data = pd.DataFrame([
        {"Stage": "1. Facts ingested", "Count": facts, "Rate": "—"},
        {"Stage": "2. Anomalies flagged", "Count": anoms,
         "Rate": f"{(anoms/max(1,facts))*100:.1f}% of facts"},
        {"Stage": "3. Collisions formed", "Count": coll,
         "Rate": f"{(coll/max(1,anoms))*100:.1f}% of anomalies"},
        {"Stage": "4. Hypotheses formed", "Count": hyps,
         "Rate": f"{(hyps/max(1,coll))*100:.1f}% of collisions"},
        {"Stage": "5. Survived kill phase", "Count": surv,
         "Rate": f"{(surv/max(1,hyps))*100:.1f}% of hypotheses"},
        {"Stage": "6. Scored ≥ 65 (findings)", "Count": findings,
         "Rate": f"{(findings/max(1,surv))*100:.1f}% of survivors"},
    ])
    st.dataframe(funnel_data, hide_index=True, use_container_width=True)

    st.markdown("---")
    col_x, col_y = st.columns(2)
    with col_x:
        st.markdown("## Source-type distribution")
        st_dist = sql("""
            SELECT source_type, COUNT(*) as n
            FROM raw_facts GROUP BY source_type ORDER BY n DESC LIMIT 20
        """)
        if not st_dist.empty:
            st.bar_chart(st_dist.set_index("source_type"))
        else:
            zero_state("No facts yet.")

    with col_y:
        st.markdown("## Pre-registration")
        if MANIFEST.exists():
            m = json.loads(MANIFEST.read_text())
            st.metric("Corpus cutoff", m.get("corpus_cutoff", "—"))
            st.metric("Frozen facts", f"{m.get('corpus_fact_count', 0):,}")
            st.metric("Code hash", m.get("code_hash", "—"))
            try:
                from preregister import verify_manifest
                v = verify_manifest()
                if v.get("status") == "ok":
                    st.success("✓ No drift — pre-registration intact")
                else:
                    st.error(f"⚠ DRIFT: {v.get('drift', 'unknown')}")
            except Exception:
                pass
        else:
            zero_state("No pre-registration locked. Run `python run.py preregister lock`.")


# ═══════════════════════════════════════════════════════════════════════
# TAB 2 — FINDINGS & PORTFOLIO
# ═══════════════════════════════════════════════════════════════════════
with tab_findings:
    sub_diamonds, sub_portfolio, sub_predictions = st.tabs([
        "Diamonds", "Portfolio", "Public predictions"
    ])

    # ── Diamonds ────────────────────────────────────────────────────────
    with sub_diamonds:
        st.markdown("## Top scoring hypotheses")
        diamonds = sql("""
            SELECT id, title, score, domain, confidence, summary, created_at
            FROM findings
            ORDER BY score DESC LIMIT 20
        """)
        if not diamonds.empty:
            # Score-distribution chart
            col_d1, col_d2 = st.columns([1, 2])
            with col_d1:
                st.markdown("### Score distribution")
                score_hist = diamonds["score"].value_counts().sort_index()
                st.bar_chart(score_hist)
            with col_d2:
                st.markdown("### Top 10")
                for _, r in diamonds.head(10).iterrows():
                    score = int(r["score"])
                    colour = "#4ade80" if score >= 90 else ("#FFD700" if score >= 75 else "#ff8800")
                    st.markdown(
                        f"<div style='border-left: 3px solid {colour}; padding: 8px 12px; "
                        f"margin: 6px 0; background: #141821; border-radius: 4px;'>"
                        f"<strong style='color: {colour}'>[{score}]</strong> "
                        f"<strong>{r['title']}</strong><br>"
                        f"<span style='color:#8892a3; font-size:0.85em;'>"
                        f"{r['domain']} · {r['confidence']} · {str(r['created_at'])[:10]}</span>"
                        f"<p style='margin: 6px 0 0 0; color: #c9d1d9; font-size: 0.88em;'>"
                        f"{(r['summary'] or '')[:280]}</p>"
                        f"</div>", unsafe_allow_html=True)
        else:
            zero_state("No findings yet. They appear here once HUNTER has run collision cycles and produced hypotheses scoring ≥ 65.")

        # Surviving hypotheses full table
        with st.expander(f"All surviving hypotheses ({hero_stats['Survived']})"):
            surv_df = sql("""
                SELECT h.id, h.diamond_score as score, h.confidence,
                       c.num_domains, c.source_types,
                       substr(h.hypothesis_text, 1, 160) as thesis,
                       h.time_window_days as window_d,
                       h.created_at
                FROM hypotheses h
                LEFT JOIN collisions c ON c.id = h.collision_id
                WHERE h.survived_kill = 1
                ORDER BY h.diamond_score DESC
            """)
            if not surv_df.empty:
                st.dataframe(surv_df, hide_index=True, use_container_width=True)
            else:
                zero_state("No surviving hypotheses yet.")

    # ── Portfolio ───────────────────────────────────────────────────────
    with sub_portfolio:
        positions = sql("""
            SELECT id, ticker, direction, entry_price, current_price,
                   pnl_pct, pnl_gbp, diamond_score, confidence, status,
                   entry_date, close_date, hypothesis_text, domains
            FROM portfolio_positions
            WHERE ticker != 'LOGGED'
        """)
        open_pos = positions[positions["status"] == "open"] if not positions.empty else pd.DataFrame()
        closed_pos = positions[positions["status"] == "closed"] if not positions.empty else pd.DataFrame()

        st.markdown("## Portfolio state")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Open positions", len(open_pos))
        c2.metric("Closed positions", len(closed_pos))
        if not closed_pos.empty:
            avg_ret = closed_pos["pnl_pct"].mean()
            c3.metric("Avg closed P&L", f"{avg_ret:+.2f}%")
            wins = (closed_pos["pnl_pct"] > 0).sum()
            c4.metric("Win rate", f"{wins/max(1,len(closed_pos)):.0%}")
        else:
            c3.metric("Avg closed P&L", "—")
            c4.metric("Win rate", "—")

        st.markdown("### Open positions")
        if not open_pos.empty:
            show = open_pos[["ticker", "direction", "entry_price", "current_price",
                             "pnl_pct", "pnl_gbp", "diamond_score", "entry_date"]].copy()
            st.dataframe(show, hide_index=True, use_container_width=True)
        else:
            zero_state("No open positions.")

        with st.expander(f"Closed positions ({len(closed_pos)})"):
            if not closed_pos.empty:
                st.dataframe(
                    closed_pos[["ticker", "direction", "pnl_pct", "pnl_gbp",
                                "diamond_score", "entry_date", "close_date", "close_reason"]]
                    if "close_reason" in closed_pos.columns else
                    closed_pos[["ticker", "direction", "pnl_pct", "pnl_gbp",
                                "diamond_score", "entry_date", "close_date"]],
                    hide_index=True, use_container_width=True)
            else:
                zero_state("No closed positions.")

        # Cluster audit
        with st.expander("Cluster audit (thesis-level similarity)"):
            if not open_pos.empty and len(open_pos) >= 2:
                try:
                    from thesis_dedup import _embed
                    import numpy as np
                    tickers = open_pos["ticker"].tolist()
                    embs = [_embed(t) for t in open_pos["hypothesis_text"].tolist()]
                    embs = [e for e in embs if e is not None]
                    if len(embs) >= 2:
                        sim_matrix = np.array(embs) @ np.array(embs).T
                        pairs = []
                        for i in range(len(tickers)):
                            for j in range(i + 1, len(tickers)):
                                s = float(sim_matrix[i][j])
                                if s >= 0.50:
                                    pairs.append({
                                        "A": tickers[i], "B": tickers[j],
                                        "similarity": round(s, 3),
                                        "severity": "DUP" if s >= 0.85 else ("variant" if s >= 0.70 else "related"),
                                    })
                        pairs.sort(key=lambda x: -x["similarity"])
                        if pairs:
                            st.dataframe(pd.DataFrame(pairs), hide_index=True, use_container_width=True)
                            dup_count = sum(1 for p in pairs if p["severity"] == "DUP")
                            if dup_count:
                                st.error(f"⚠ {dup_count} near-identical theses in open book.")
                        else:
                            st.success("✓ No significant clusters.")
                except Exception as e:
                    st.info(f"Cluster audit unavailable: {e}")
            else:
                st.info("Need ≥2 open positions for cluster audit.")

    # ── Public predictions ──────────────────────────────────────────────
    with sub_predictions:
        st.markdown("## Public prediction board")
        st.caption("Every hypothesis with score ≥ 65 posted publicly with resolution date. "
                   "Win or loss, both go on the ledger.")

        pred_path = Path(__file__).parent / "public" / "predictions.html"
        if pred_path.exists():
            st.success(f"✓ Live board: `{pred_path.relative_to(Path(__file__).parent)}`")
        else:
            st.info("Board not generated. Run `python prediction_board.py build`.")

        try:
            from prediction_board import gather_predictions, compute_track_record
            preds = gather_predictions(min_score=65)
            tr = compute_track_record(preds)

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Posted", tr["total_predictions"])
            c2.metric("Pending", tr["pending"])
            c3.metric("Resolved", tr["resolved"])
            c4.metric("Hit rate", f"{tr['hit_rate']:.0%}" if tr["hit_rate"] is not None else "—")
            c5.metric("Brier", f"{tr['brier_score']}" if tr["brier_score"] is not None else "—")

            if preds:
                df = pd.DataFrame([{
                    "ID": p["id"], "Score": p["diamond_score"],
                    "Status": p["status"], "Posted": p["posted_date"],
                    "Target": p["target_date"], "Days left": p["days_remaining"],
                    "Confidence": p["confidence"],
                    "Thesis": p["thesis_short"],
                } for p in preds])
                st.dataframe(df, hide_index=True, use_container_width=True)
            else:
                zero_state("No predictions yet. They appear here once HUNTER has produced hypotheses scoring ≥ 65.")
        except Exception as e:
            st.info(f"Prediction board unavailable: {e}")


# ═══════════════════════════════════════════════════════════════════════
# TAB 3 — KNOWLEDGE GRAPH
# ═══════════════════════════════════════════════════════════════════════
with tab_knowledge:
    sub_cycles, sub_chains, sub_graph, sub_collisions = st.tabs([
        "Cycles", "Chains", "Causal graph", "Collision map"
    ])

    # ── Cycles ──────────────────────────────────────────────────────────
    with sub_cycles:
        st.markdown("## Detected epistemic cycles")
        st.caption("Closed loops A → B → C → … → A through HUNTER's causal graph.")

        cycles = sql("""
            SELECT id, cycle_type, nodes, domains, reinforcement_strength,
                   persistence_estimate, detected_date, age_days
            FROM detected_cycles
            ORDER BY reinforcement_strength DESC
        """)

        if not cycles.empty:
            cycle_types = cycles["cycle_type"].value_counts()
            st.bar_chart(cycle_types)
            st.caption(f"{len(cycles)} cycles detected across "
                       f"{cycles['cycle_type'].nunique()} distinct types.")

            for _, r in cycles.iterrows():
                try:
                    nodes = json.loads(r["nodes"] or "[]")
                    domains = json.loads(r["domains"] or "[]")
                except Exception:
                    nodes, domains = [], []
                with st.expander(
                    f"#{r['id']} [{r['cycle_type']}] · {len(nodes)} nodes · "
                    f"strength {r['reinforcement_strength']:.2f} · "
                    f"{len(domains)} domains"
                ):
                    for i, n in enumerate(nodes):
                        dom = n.get('domain', '?') if isinstance(n, dict) else str(n)
                        meth = n.get('methodology', '') if isinstance(n, dict) else ''
                        st.markdown(f"**{i+1}.** {dom[:100]}")
                        if meth:
                            st.caption(meth[:240])
                    st.caption(f"Detected {str(r['detected_date'])[:10]} · "
                               f"est persistence {r.get('persistence_estimate', 0):.0f}d")
        else:
            zero_state("No cycles detected yet. Run `python cycle_detector.py run` "
                       "after collision cycles have populated chains.")

    # ── Chains ──────────────────────────────────────────────────────────
    with sub_chains:
        st.markdown("## Multi-link causal chains")
        chains = sql("""
            SELECT id, collision_id, chain_length, num_domains, domains_traversed
            FROM chains ORDER BY chain_length DESC, created_at DESC LIMIT 50
        """)
        if not chains.empty:
            len_dist = chains["chain_length"].value_counts().sort_index()
            st.bar_chart(len_dist)
            st.caption(f"{len(chains)} chains total, avg length "
                       f"{chains['chain_length'].mean():.1f}, max {chains['chain_length'].max()}.")
            st.dataframe(chains, hide_index=True, use_container_width=True)
        else:
            zero_state("No chains yet. Chains form from validated disruption-assumption pairs in collision cycles.")

    # ── Causal graph ────────────────────────────────────────────────────
    with sub_graph:
        st.markdown("## Causal edge graph")
        edges = sql("""
            SELECT id, cause_node, effect_node, strength, confidence, source_type
            FROM causal_edges
        """)
        if not edges.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total edges", len(edges))
            c2.metric("Distinct nodes", edges[["cause_node", "effect_node"]].stack().nunique())
            c3.metric("Avg confidence", f"{edges['confidence'].mean():.2f}")

            # Top hub nodes
            node_degrees = pd.concat([
                edges.groupby("cause_node").size().reset_index(name="out_deg").rename(columns={"cause_node": "node"}),
                edges.groupby("effect_node").size().reset_index(name="in_deg").rename(columns={"effect_node": "node"}),
            ]).groupby("node").sum(numeric_only=True).reset_index()
            node_degrees["total_deg"] = node_degrees.get("out_deg", 0).fillna(0) + node_degrees.get("in_deg", 0).fillna(0)
            node_degrees = node_degrees.sort_values("total_deg", ascending=False).head(10)

            st.markdown("### Top 10 hub nodes")
            node_degrees["node"] = node_degrees["node"].str[:100]
            st.dataframe(node_degrees, hide_index=True, use_container_width=True)

            with st.expander(f"All edges ({len(edges)})"):
                st.dataframe(edges, hide_index=True, use_container_width=True)
        else:
            zero_state("No causal edges yet. These are extracted from facts during ingest cycles.")

    # ── Collision map ───────────────────────────────────────────────────
    with sub_collisions:
        st.markdown("## Collision fire map")
        st.caption("Which source-type pairs produce the most collisions?")
        fire_df = sql("""
            SELECT source_types, COUNT(*) as n
            FROM collisions
            WHERE source_types IS NOT NULL AND source_types != ''
            GROUP BY source_types
            ORDER BY n DESC LIMIT 30
        """)
        if not fire_df.empty:
            pair_counts = {}
            for _, r in fire_df.iterrows():
                try:
                    types = json.loads(r["source_types"]) if isinstance(r["source_types"], str) and r["source_types"].startswith("[") else r["source_types"].split(",")
                except Exception:
                    types = []
                types = sorted({t.strip() for t in types if t and t.strip()})
                if len(types) < 2:
                    continue
                for a, b in combinations(types, 2):
                    key = f"{a} × {b}"
                    pair_counts[key] = pair_counts.get(key, 0) + int(r["n"])
            if pair_counts:
                top_pairs = pd.DataFrame([{"Pair": k, "Collisions": v}
                                          for k, v in sorted(pair_counts.items(),
                                                             key=lambda x: -x[1])[:20]])
                st.dataframe(top_pairs, hide_index=True, use_container_width=True)
        else:
            zero_state("No collisions yet. Once HUNTER runs ingest + collision cycles, pairs appear here.")


# ═══════════════════════════════════════════════════════════════════════
# TAB 4 — THEORY & MOAT
# ═══════════════════════════════════════════════════════════════════════
with tab_theory:
    sub_layers, sub_tests, sub_frontier, sub_moat = st.tabs([
        "13 Layers", "Empirical tests", "Frontier hypotheses", "Moat"
    ])

    # ── Layers ──────────────────────────────────────────────────────────
    with sub_layers:
        st.markdown("## 13-layer evidence matrix")
        layer_names = {
            1: "Translation Loss", 2: "Attention Topology", 3: "Question Gap",
            4: "Phase Transition", 5: "Rate-Distortion", 6: "Market Incompleteness",
            7: "Depth-Value", 8: "Epistemic Cycles", 9: "Cycle Hierarchy",
            10: "Fractal Incompleteness", 11: "Negative Space", 12: "Autopoiesis",
            13: "Observer-Dependent",
        }
        ev = sql("""
            SELECT layer, evidence_type, COUNT(*) as n
            FROM theory_evidence GROUP BY layer, evidence_type
        """)
        rows = []
        for i in range(1, 14):
            layer_ev = ev[ev["layer"] == i] if not ev.empty else pd.DataFrame()
            direct = int(layer_ev[layer_ev["evidence_type"] == "direct"]["n"].sum()) if not layer_ev.empty else 0
            supporting = int(layer_ev[layer_ev["evidence_type"] == "supporting"]["n"].sum()) if not layer_ev.empty else 0
            challenging = int(layer_ev[layer_ev["evidence_type"] == "challenging"]["n"].sum()) if not layer_ev.empty else 0
            if challenging > direct and challenging > 0:
                status = "🔴 challenged"
            elif direct > 0:
                status = "🟢 direct"
            elif supporting > 0:
                status = "🟡 supporting"
            else:
                status = "⚪ empty"
            rows.append({
                "Layer": f"L{i:02d}", "Name": layer_names.get(i, "?"),
                "Status": status, "Direct": direct,
                "Supporting": supporting, "Challenging": challenging,
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        # Theory health score
        total_direct = sum(r["Direct"] for r in rows)
        total_support = sum(r["Supporting"] for r in rows)
        total_challenge = sum(r["Challenging"] for r in rows)
        layers_with_any = sum(1 for r in rows if r["Direct"] + r["Supporting"] > 0)
        coverage_pts = min(40, (layers_with_any / 13) * 40)
        quality_pts = min(40, total_direct * 0.5)
        challenge_penalty = min(20, total_challenge * 3)
        theory_health = max(0, round(coverage_pts + quality_pts - challenge_penalty))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Theory health", f"{theory_health}/100")
        c2.metric("Layers populated", f"{layers_with_any}/13")
        c3.metric("Direct evidence", total_direct)
        c4.metric("Challenges", total_challenge)

    # ── Empirical tests ─────────────────────────────────────────────────
    with sub_tests:
        st.markdown("## Empirical framework tests")

        # Formula validation
        st.markdown("### 1. Collision formula predictiveness")
        fv = sql("SELECT * FROM formula_validation ORDER BY date DESC LIMIT 1")
        if not fv.empty:
            row = fv.iloc[0]
            c1, c2, c3 = st.columns(3)
            c1.metric("Pearson r", f"{row.get('pearson_r', 0):+.3f}")
            c2.metric("Spearman ρ", f"{row.get('spearman_rho', 0):+.3f}")
            c3.metric("p-value", f"{row.get('p_value', 0):.3f}")
        else:
            zero_state("No formula validation. Run `python formula_validator.py write`.")

        # Measured domain params
        st.markdown("### 2. Measured reinforcement & correction")
        measured = sql("""
            SELECT source_type, reinforcement_measured, correction_measured,
                   persistence_ratio_measured, n_facts
            FROM measured_domain_params ORDER BY persistence_ratio_measured DESC LIMIT 20
        """)
        if not measured.empty:
            st.dataframe(measured, hide_index=True, use_container_width=True)
        else:
            zero_state("Run `python reinforcement_measurer.py write`.")

        # Half-life
        st.markdown("### 3. Half-life vs 120-day prediction")
        hl = sql("""
            SELECT source_type, half_life_days, n_correction_events, n_observations
            FROM halflife_estimates
            ORDER BY half_life_days LIMIT 20
        """)
        if not hl.empty:
            st.dataframe(hl, hide_index=True, use_container_width=True)
        else:
            zero_state("Run `python halflife_estimator.py write`.")

        # Narrative
        st.markdown("### 4. Narrative strength vs kill-survival")
        ns = sql("""
            SELECT narrative_strength, h.survived_kill, h.diamond_score
            FROM narrative_scores ns JOIN hypotheses h ON h.id = ns.hypothesis_id
        """)
        if not ns.empty:
            high = ns[ns["narrative_strength"] >= 0.6]
            low = ns[ns["narrative_strength"] < 0.4]
            c1, c2, c3 = st.columns(3)
            c1.metric("High-narrative n", len(high),
                      delta=f"{high['survived_kill'].mean():.0%} survival" if not high.empty else "—")
            c2.metric("Low-narrative n", len(low),
                      delta=f"{low['survived_kill'].mean():.0%} survival" if not low.empty else "—")
            if not high.empty and not low.empty:
                c3.metric("Uplift", f"{(high['survived_kill'].mean()-low['survived_kill'].mean()):+.1%}")
        else:
            zero_state("Run `python narrative_detector.py write`.")

    # ── Frontier hypotheses ─────────────────────────────────────────────
    with sub_frontier:
        st.markdown("## Frontier hypotheses — 6 testable claims")
        ft = sql("""
            SELECT hypothesis_id, hypothesis_name, supports_hypothesis,
                   observation_value, measured_at
            FROM frontier_test_results
            ORDER BY measured_at DESC LIMIT 12
        """)
        if not ft.empty:
            latest = ft.drop_duplicates(subset=["hypothesis_id"], keep="first")
            st.dataframe(latest, hide_index=True, use_container_width=True)
            supported = latest[latest["supports_hypothesis"] == 1]
            st.metric("Supported", f"{len(supported)} of {len(latest)}")
        else:
            zero_state("Run `python run.py frontier all`.")

    # ── Moat ────────────────────────────────────────────────────────────
    with sub_moat:
        st.markdown("## Moat — 5-layer multiplicative")
        try:
            from moat_tracker import all_layers, composite_score
            layers = all_layers()
            comp = composite_score(layers)
            cols = st.columns(len(layers))
            for col, l in zip(cols, layers):
                col.metric(l["layer"], f"{l['strength']}/10",
                           delta=f"{l['time_to_replicate_months']}mo")
            st.metric("Composite (product)", f"{comp['product_score']:,}")
            with st.expander("Action items per layer"):
                for l in layers:
                    st.markdown(f"**{l['layer']}** ({l['strength']}/10):")
                    for action in l["actions_to_strengthen"]:
                        st.markdown(f"- {action}")
        except Exception as e:
            zero_state(f"Moat tracker unavailable: {e}")

        # TAM
        st.markdown("---")
        st.markdown("## Total Addressable Residual (TAM)")
        tam = sql("""
            SELECT scenario, avg_chain_value_M, total_addressable_residual_B,
                   annual_flow_B, annual_capture_M
            FROM residual_tam
            WHERE measured_at = (SELECT MAX(measured_at) FROM residual_tam)
            ORDER BY total_addressable_residual_B
        """)
        if not tam.empty:
            tam.columns = ["Scenario", "Avg $M/chain", "TAM ($B)",
                           "Annual flow ($B)", "Annual capture ($M)"]
            st.dataframe(tam, hide_index=True, use_container_width=True)
        else:
            zero_state("Run `python residual_tam.py write`.")


# ═══════════════════════════════════════════════════════════════════════
# TAB 5 — OPERATIONS
# ═══════════════════════════════════════════════════════════════════════
with tab_ops:
    sub_runs, sub_goals, sub_reports = st.tabs([
        "Recent runs", "Goals & self-improve", "Reports"
    ])

    # ── Runs ────────────────────────────────────────────────────────────
    with sub_runs:
        st.markdown("## Cycle history")
        runs = sql("""
            SELECT id, datetime(created_at) as t, domain, status,
                   tokens_used, duration_seconds, error_message
            FROM cycle_logs ORDER BY id DESC LIMIT 100
        """)
        if not runs.empty:
            # Activity by hour
            runs["t"] = pd.to_datetime(runs["t"])
            runs["hour"] = runs["t"].dt.floor("h")
            hourly = runs.groupby(["hour", "status"]).size().unstack(fill_value=0)
            st.markdown("### Cycles per hour (last 100)")
            st.line_chart(hourly)

            st.markdown("### Cycles (most recent 50)")
            st.dataframe(runs.head(50)[["t", "domain", "status", "tokens_used",
                                          "duration_seconds", "error_message"]],
                         hide_index=True, use_container_width=True)
        else:
            zero_state("No runs yet.")

    # ── Goals ───────────────────────────────────────────────────────────
    with sub_goals:
        st.markdown("## Self-improvement goals")
        goals_path = Path(__file__).parent / "goals.json"
        if goals_path.exists():
            g = json.loads(goals_path.read_text())
            idx = g.get("current_goal_index", 0)
            goals = g.get("goals", [])
            if idx < len(goals):
                current = goals[idx]
                st.success(f"**Current goal:** {current.get('goal')}")
                st.caption(f"Target: {current.get('target')} · "
                           f"Measure: {current.get('measure')}")
                with st.expander("Subgoals"):
                    for sub in current.get("subgoals", []):
                        st.markdown(f"- {sub}")
            with st.expander(f"All goals ({len(goals)})"):
                for i, gl in enumerate(goals):
                    marker = "✓" if i < idx else ("→" if i == idx else "○")
                    st.markdown(f"{marker} **#{i}** {gl.get('goal')}")
        else:
            zero_state("No goals.json.")

        # Proposed changes
        prop_dir = Path(__file__).parent / "proposed_changes"
        if prop_dir.exists():
            files = sorted(prop_dir.glob("*.json"))
            st.markdown(f"### Queued proposals ({len(files)})")
            for f in files[-5:]:
                try:
                    data = json.loads(f.read_text())
                    st.markdown(
                        f"- **[L{data.get('level')}]** {data.get('title', '')}  \n"
                        f"  *{data.get('rationale', '')[:120]}*"
                    )
                except Exception:
                    pass

    # ── Reports ─────────────────────────────────────────────────────────
    with sub_reports:
        st.markdown("## Overseer reports")
        overseer = sql("""
            SELECT created_at, substr(report_text, 1, 400) as preview
            FROM overseer_reports ORDER BY id DESC LIMIT 5
        """)
        if not overseer.empty:
            for _, r in overseer.iterrows():
                with st.expander(str(r["created_at"])[:16]):
                    st.markdown(r["preview"])
        else:
            zero_state("No overseer reports. Run `python targeting.py` or via orchestrator.")

        # Daily summaries
        st.markdown("---")
        st.markdown("## Daily summaries")
        daily = sql("""
            SELECT summary_date, total_cycles, total_findings, diamonds_found,
                   most_promising_thread
            FROM daily_summaries ORDER BY summary_date DESC LIMIT 10
        """)
        if not daily.empty:
            st.dataframe(daily, hide_index=True, use_container_width=True)
        else:
            zero_state("No daily summaries yet.")


# ── Footer ──────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"HUNTER · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · "
           f"John Malpass · UCD · [github repo](#) · [SSRN paper](#)")
