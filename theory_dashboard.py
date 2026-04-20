#!/usr/bin/env python3
"""HUNTER Theory Dashboard — 8-page Streamlit dashboard for the Epistemic Residual Framework.

Run with: streamlit run theory_dashboard.py
Install: pip install streamlit plotly networkx
"""

import json
import math
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Config ──────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).parent / "hunter.db"

# Color scheme
C_BG = "#080D19"
C_GOLD = "#D4A843"
C_TEAL = "#4DD0E1"
C_RED = "#FF6B6B"
C_GREY = "#3A3F4B"
C_DIM = "#6B7280"
C_WHITE = "#E8E8E8"

PREDICTED_TOTAL_T = 5.65
PREDICTED_CHAIN_T = 1.71
PREDICTED_CYCLE_T = 1.56
PREDICTED_HIERARCHY_T = 2.38
PREDICTED_HALF_LIFE = 120
PREDICTED_PERSISTENCE = 207
PREDICTED_DECAY = 0.273

LAYER_NAMES = {
    1: "Translation Loss", 2: "Attention Topology", 3: "Question Gap",
    4: "Phase Transition", 5: "Rate-Distortion", 6: "Market Incompleteness",
    7: "Depth-Value", 8: "Epistemic Cycles", 9: "Cycle Hierarchy",
    10: "Fractal Incompleteness", 11: "Negative Space", 12: "Autopoiesis",
    13: "Observer-Dependent",
}


# ── Database helpers ────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def query(sql, params=(), one=False):
    try:
        conn = get_conn()
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows[0] if one and rows else rows
    except Exception:
        return {} if one else []


def table_exists(name):
    r = query("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return len(r) > 0


# ── Domain params (imported or fallback) ────────────────────────────────
try:
    from theory import DOMAIN_THEORY_PARAMS, compute_collision_formula, compute_depth_value, \
        CHAIN_DECAY_RATE, EXPECTED_PERSISTENCE_RATIO, ALL_LAYERS, LAYER_TO_NUM
except ImportError:
    DOMAIN_THEORY_PARAMS = {}
    CHAIN_DECAY_RATE = 0.273
    EXPECTED_PERSISTENCE_RATIO = 207

    def compute_collision_formula(a, b):
        return {"total": 0, "silo_term": 0, "reinforcement_term": 0,
                "correction_term": 0, "residual_term": 0}

    def compute_depth_value(d):
        return 0


# ── Plotly layout defaults ──────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor=C_BG, plot_bgcolor=C_BG,
    font=dict(color=C_WHITE, size=12),
    margin=dict(l=40, r=20, t=40, b=40),
)


def styled_fig(fig, **kwargs):
    fig.update_layout(**PLOTLY_LAYOUT, **kwargs)
    return fig


# ═══════════════════════════════════════════════════════════════════════
# PAGE SETUP
# ═══════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="HUNTER Theory Dashboard",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject dark theme CSS
st.markdown(f"""
<style>
    .stApp {{background-color: {C_BG};}}
    .stSidebar > div {{background-color: #0D1321;}}
    h1, h2, h3 {{color: {C_GOLD} !important;}}
    .stMetric label {{color: {C_DIM} !important;}}
    .stMetric [data-testid="stMetricValue"] {{color: {C_WHITE} !important;}}
    .stMetric [data-testid="stMetricDelta"] {{font-size: 0.9rem;}}
    div[data-testid="stExpander"] {{border-color: {C_GREY};}}
    .ticker-text {{color: {C_GOLD}; font-family: monospace; font-size: 0.8rem;}}
</style>
""", unsafe_allow_html=True)

# Sidebar navigation
st.sidebar.title("🔬 HUNTER Theory")
page = st.sidebar.radio("Navigate", [
    "🔥 Live Fire Map",
    "📊 Evidence Accumulator",
    "🗺️ Domain Topology",
    "⛓️ Chain Explorer",
    "🔄 Cycle Monitor",
    "📈 Backtest Results",
    "💰 Residual Tracker",
    "🏥 Theory Health",
])

# Auto-refresh toggle
auto_refresh = st.sidebar.checkbox("Auto-refresh (60s)", value=False)
if auto_refresh:
    time.sleep(60)
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption(f"DB: {DB_PATH.name}")
fact_count = query("SELECT COUNT(*) as n FROM raw_facts", one=True)
st.sidebar.metric("Facts", fact_count.get("n", 0) if fact_count else 0)
hyp_count = query(
    "SELECT COUNT(*) as n FROM hypotheses WHERE survived_kill=1", one=True)
st.sidebar.metric("Surviving Hypotheses", hyp_count.get("n", 0) if hyp_count else 0)


# ═══════════════════════════════════════════════════════════════════════
# PAGE 1: LIVE FIRE MAP
# ═══════════════════════════════════════════════════════════════════════
if page == "🔥 Live Fire Map":
    st.title("Live Fire Map")

    # Build domain nodes
    domains = list(DOMAIN_THEORY_PARAMS.keys())
    if not domains:
        st.warning("No domain params loaded")
        st.stop()

    # Compute collision scores for all pairs
    edges = []
    for i, a in enumerate(domains):
        for j, b in enumerate(domains):
            if j > i:
                score = compute_collision_formula(a, b)
                if score["total"] > 5:
                    edges.append((a, b, score["total"]))

    # Get actual collision counts
    actual_edges = {}
    rows = query("""
        SELECT source_types, COUNT(*) as cnt FROM collisions
        WHERE source_types IS NOT NULL GROUP BY source_types
    """)
    for r in rows:
        st = r.get("source_types", "")
        if st:
            parts = [t.strip() for t in st.split(",") if t.strip()]
            if len(parts) >= 2:
                key = tuple(sorted(parts[:2]))
                actual_edges[key] = actual_edges.get(key, 0) + r["cnt"]

    # Build network graph with plotly
    import networkx as nx

    G = nx.Graph()
    for d in domains:
        p = DOMAIN_THEORY_PARAMS[d]
        G.add_node(d, access=p.get("access", 0.5),
                   reinf=p.get("reinforcement", 0.5),
                   size=p.get("residual", 0.1) * p.get("market_size_b", 100))

    for a, b, score in edges:
        G.add_edge(a, b, weight=score)

    # Position by (access, reinforcement)
    pos = {}
    for d in domains:
        p = DOMAIN_THEORY_PARAMS[d]
        pos[d] = (p.get("access", 0.5), p.get("reinforcement", 0.5))

    # Draw edges
    edge_traces = []
    for a, b, score in edges:
        x0, y0 = pos[a]
        x1, y1 = pos[b]
        key = tuple(sorted([a, b]))
        actual = actual_edges.get(key, 0)

        if score > 60:
            color = C_RED
        elif score > 45:
            color = C_GOLD
        else:
            color = C_GREY

        # Thicken edges with actual collisions
        width = 1 + min(5, actual)

        edge_traces.append(go.Scatter(
            x=[x0, x1, None], y=[y0, y1, None],
            mode="lines", line=dict(color=color, width=width),
            hoverinfo="text",
            text=f"{a} ↔ {b}<br>Score: {score:.1f}<br>Collisions: {actual}",
            showlegend=False,
        ))

    # Draw nodes
    node_x = [pos[d][0] for d in domains]
    node_y = [pos[d][1] for d in domains]
    node_sizes = [max(8, min(50, DOMAIN_THEORY_PARAMS[d].get("residual", 0.1)
                  * DOMAIN_THEORY_PARAMS[d].get("market_size_b", 100) * 0.3))
                  for d in domains]
    node_colors = [DOMAIN_THEORY_PARAMS[d].get("residual", 0.1) for d in domains]

    node_trace = go.Scatter(
        x=node_x, y=node_y, mode="markers+text",
        marker=dict(size=node_sizes, color=node_colors,
                    colorscale=[[0, C_GREY], [0.5, C_GOLD], [1, C_RED]],
                    colorbar=dict(title="Residual", thickness=15),
                    line=dict(width=1, color=C_GOLD)),
        text=[d.replace("_", " ").title()[:12] for d in domains],
        textposition="top center",
        textfont=dict(size=9, color=C_WHITE),
        hovertext=[f"<b>{d}</b><br>Market: ${DOMAIN_THEORY_PARAMS[d].get('market_size_b', 0):.0f}B<br>"
                   f"Residual: {DOMAIN_THEORY_PARAMS[d].get('residual', 0):.0%}<br>"
                   f"Access: {DOMAIN_THEORY_PARAMS[d].get('access', 0):.2f}<br>"
                   f"Reinforcement: {DOMAIN_THEORY_PARAMS[d].get('reinforcement', 0):.2f}"
                   for d in domains],
        hoverinfo="text",
        showlegend=False,
    )

    fig = go.Figure(data=edge_traces + [node_trace])
    styled_fig(fig, title="Domain Network — Node size = residual × market, Edge color = collision score",
               xaxis=dict(title="Access →", showgrid=False, zeroline=False, range=[-0.1, 1.1]),
               yaxis=dict(title="Reinforcement →", showgrid=False, zeroline=False, range=[-0.1, 1.1]),
               height=600)
    st.plotly_chart(fig, use_container_width=True)

    # Recent events ticker
    st.subheader("Recent Events")
    if table_exists("theory_evidence"):
        events = query("""
            SELECT timestamp, source_event, layer_name, evidence_type, description
            FROM theory_evidence ORDER BY timestamp DESC LIMIT 20
        """)
        if events:
            ticker_html = "<div class='ticker-text'>"
            for e in events:
                icon = "🟢" if e["evidence_type"] == "direct" else "🟡" if e["evidence_type"] == "supporting" else "🔴"
                ticker_html += f"{icon} [{e['timestamp'][:16]}] {e['source_event']}: {(e['description'] or '')[:100]}<br>"
            ticker_html += "</div>"
            st.markdown(ticker_html, unsafe_allow_html=True)
        else:
            st.info("No theory evidence logged yet. Run HUNTER to generate data.")
    else:
        st.info("theory_evidence table not found. Run HUNTER to initialize.")

    # Recent collisions
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Latest Collisions")
        collisions = query("""
            SELECT collision_description, num_domains, source_types, created_at
            FROM collisions ORDER BY created_at DESC LIMIT 8
        """)
        for c in collisions:
            st.markdown(f"**{c.get('source_types', '')}** ({c.get('num_domains', 0)} domains)")
            st.caption(f"{(c.get('collision_description', '') or '')[:120]}...")

    with col2:
        st.subheader("Latest Hypotheses")
        hyps = query("""
            SELECT hypothesis_text, diamond_score, survived_kill, created_at
            FROM hypotheses ORDER BY created_at DESC LIMIT 8
        """)
        for h in hyps:
            score = h.get("diamond_score", 0)
            icon = "💎" if score and score >= 75 else "⭐" if score and score >= 65 else "📝"
            survived = "✅" if h.get("survived_kill") else "❌"
            st.markdown(f"{icon} **{score}** {survived} {(h.get('hypothesis_text', '') or '')[:100]}...")


# ═══════════════════════════════════════════════════════════════════════
# PAGE 2: EVIDENCE ACCUMULATOR
# ═══════════════════════════════════════════════════════════════════════
elif page == "📊 Evidence Accumulator":
    st.title("Evidence Accumulator")
    st.caption("6 major provable claims — progress toward statistical significance")

    if not table_exists("theory_evidence"):
        st.warning("No theory_evidence table. Run HUNTER to generate data.")
        st.stop()

    # Gather evidence counts per layer
    layer_evidence = query("""
        SELECT layer, layer_name, evidence_type, COUNT(*) as cnt,
               AVG(observed_value) as avg_observed,
               AVG(predicted_value) as avg_predicted,
               AVG(confidence) as avg_conf
        FROM theory_evidence
        GROUP BY layer, evidence_type
    """)

    # Build layer stats
    layer_stats = {}
    for e in layer_evidence:
        l = e["layer"]
        if l not in layer_stats:
            layer_stats[l] = {"direct": 0, "supporting": 0, "challenging": 0,
                              "total": 0, "avg_observed": None, "avg_predicted": None,
                              "avg_conf": 0}
        et = e.get("evidence_type", "supporting")
        layer_stats[l][et] = e["cnt"]
        layer_stats[l]["total"] += e["cnt"]
        if e["avg_observed"] is not None:
            layer_stats[l]["avg_observed"] = e["avg_observed"]
        if e["avg_predicted"] is not None:
            layer_stats[l]["avg_predicted"] = e["avg_predicted"]
        layer_stats[l]["avg_conf"] = max(layer_stats[l]["avg_conf"], e.get("avg_conf", 0) or 0)

    def evidence_progress(n, target=50):
        """Progress toward statistical significance (n > 50, p < 0.01)."""
        return min(1.0, n / target)

    # Claim 1: Translation Loss (Layer 1)
    st.subheader("1. Translation Loss (Layer 1)")
    l1 = layer_stats.get(1, {"total": 0, "avg_observed": None, "avg_conf": 0})
    progress = evidence_progress(l1["total"])
    st.progress(progress, text=f"{l1['total']} instances ({progress:.0%} to significance)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Measured Instances", l1["total"])
    c2.metric("Avg Distortion", f"{l1['avg_observed']:.2f}" if l1["avg_observed"] else "—")
    c3.metric("Avg Confidence", f"{l1['avg_conf']:.2f}")
    with st.expander("Layer 1 Evidence Details"):
        details = query("SELECT * FROM theory_evidence WHERE layer=1 ORDER BY timestamp DESC LIMIT 20")
        if details:
            st.dataframe(details, use_container_width=True)

    st.markdown("---")

    # Claim 2: Reinforcement > Correction (Layer 8)
    st.subheader("2. Reinforcement > Correction (Layer 8)")
    l8 = layer_stats.get(8, {"total": 0, "avg_observed": None, "avg_conf": 0})
    progress = evidence_progress(l8["total"])
    st.progress(progress, text=f"{l8['total']} instances ({progress:.0%} to significance)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Data Points", l8["total"])
    ratio_str = f"{l8['avg_observed']:.1f}x" if l8["avg_observed"] else "—"
    c2.metric("Empirical Persistence Ratio", ratio_str, delta=f"vs {PREDICTED_PERSISTENCE}x predicted")
    c3.metric("Avg Confidence", f"{l8['avg_conf']:.2f}")
    with st.expander("Layer 8 Evidence Details"):
        details = query("SELECT * FROM theory_evidence WHERE layer=8 ORDER BY timestamp DESC LIMIT 20")
        if details:
            st.dataframe(details, use_container_width=True)

    st.markdown("---")

    # Claim 3: Chain Decay (Layer 7)
    st.subheader("3. Chain Decay (Layer 7)")
    l7 = layer_stats.get(7, {"total": 0, "avg_observed": None, "avg_conf": 0})
    progress = evidence_progress(l7["total"])
    st.progress(progress, text=f"{l7['total']} instances ({progress:.0%} to significance)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Data Points", l7["total"])
    decay_str = f"{l7['avg_observed']:.3f}" if l7["avg_observed"] else "—"
    c2.metric("Observed Decay Factor", decay_str, delta=f"vs {PREDICTED_DECAY} predicted")
    c3.metric("Avg Confidence", f"{l7['avg_conf']:.2f}")
    with st.expander("Layer 7 Evidence Details"):
        details = query("SELECT * FROM theory_evidence WHERE layer=7 ORDER BY timestamp DESC LIMIT 20")
        if details:
            st.dataframe(details, use_container_width=True)

    st.markdown("---")

    # Claim 4: Collision Prediction (Layers 2, 11)
    st.subheader("4. Collision Prediction (Layers 2, 11)")
    l2 = layer_stats.get(2, {"total": 0, "avg_observed": None, "avg_conf": 0})
    l11 = layer_stats.get(11, {"total": 0, "avg_observed": None, "avg_conf": 0})
    combined = l2["total"] + l11["total"]
    progress = evidence_progress(combined)
    st.progress(progress, text=f"{combined} instances ({progress:.0%} to significance)")
    # Get latest formula validation
    fv = query("SELECT * FROM formula_validation ORDER BY date DESC LIMIT 1", one=True) if table_exists("formula_validation") else {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Attention Evidence", l2["total"])
    c2.metric("Negative Space Evidence", l11["total"])
    c3.metric("Pearson r", f"{fv.get('pearson_r', '—')}")
    c4.metric("Formula Validated", "✅" if fv.get("formula_validated") else "❌")
    with st.expander("Collision Prediction Details"):
        details = query("SELECT * FROM theory_evidence WHERE layer IN (2,11) ORDER BY timestamp DESC LIMIT 20")
        if details:
            st.dataframe(details, use_container_width=True)

    st.markdown("---")

    # Claim 5: Structural Incompleteness (Layer 10)
    st.subheader("5. Structural Incompleteness (Layer 10)")
    l10 = layer_stats.get(10, {"total": 0, "avg_observed": None, "avg_conf": 0})
    progress = evidence_progress(l10["total"])
    st.progress(progress, text=f"{l10['total']} instances ({progress:.0%} to significance)")
    c1, c2 = st.columns(2)
    c1.metric("Persistent Anomalies", l10["total"])
    c2.metric("Avg Days Uncorrected", f"{l10['avg_observed']:.0f}" if l10["avg_observed"] else "—")
    with st.expander("Layer 10 Evidence Details"):
        details = query("SELECT * FROM theory_evidence WHERE layer=10 ORDER BY timestamp DESC LIMIT 20")
        if details:
            st.dataframe(details, use_container_width=True)

    st.markdown("---")

    # Claim 6: Total Residual (Layer 12)
    st.subheader("6. Total Residual (Layer 12)")
    l12 = layer_stats.get(12, {"total": 0, "avg_observed": None, "avg_conf": 0})
    progress = evidence_progress(l12["total"])
    st.progress(progress, text=f"{l12['total']} instances ({progress:.0%} to significance)")
    # Get latest residual estimate
    re_latest = query("SELECT * FROM residual_estimates ORDER BY date DESC LIMIT 1", one=True) if table_exists("residual_estimates") else {}
    c1, c2, c3 = st.columns(3)
    c1.metric("Autopoiesis Evidence", l12["total"])
    est = re_latest.get("estimated_residual_B")
    c2.metric("Latest Domain Estimate", f"${est:.1f}B" if est else "—")
    c3.metric("Target", f"${PREDICTED_TOTAL_T}T")
    with st.expander("Layer 12 Evidence Details"):
        details = query("SELECT * FROM theory_evidence WHERE layer=12 ORDER BY timestamp DESC LIMIT 20")
        if details:
            st.dataframe(details, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════
# PAGE 3: DOMAIN TOPOLOGY
# ═══════════════════════════════════════════════════════════════════════
elif page == "🗺️ Domain Topology":
    st.title("Domain Topology — 25×25 Heatmap")

    domains = sorted(DOMAIN_THEORY_PARAMS.keys())
    n = len(domains)

    if n < 2:
        st.warning("Need domain params to build topology")
        st.stop()

    mode = st.radio("Mode", ["A: Predicted Scores", "B: Actual Counts", "C: Delta (Match/Mismatch)"],
                    horizontal=True)

    # Compute predicted scores matrix
    pred_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                score = compute_collision_formula(domains[i], domains[j])
                pred_matrix[i][j] = score["total"]

    # Get actual collision counts
    actual_matrix = [[0] * n for _ in range(n)]
    rows = query("""
        SELECT source_types, COUNT(*) as cnt FROM collisions
        WHERE source_types IS NOT NULL GROUP BY source_types
    """)
    domain_idx = {d: i for i, d in enumerate(domains)}
    for r in rows:
        st_str = r.get("source_types", "")
        if st_str:
            parts = [t.strip() for t in st_str.split(",") if t.strip()]
            for p1 in parts:
                for p2 in parts:
                    if p1 != p2 and p1 in domain_idx and p2 in domain_idx:
                        actual_matrix[domain_idx[p1]][domain_idx[p2]] += r["cnt"]

    short_names = [d.replace("_", " ").title()[:10] for d in domains]

    if mode.startswith("A"):
        z = pred_matrix
        colorscale = [[0, C_BG], [0.3, C_GREY], [0.6, C_GOLD], [1, C_RED]]
        title = "Predicted Collision Scores (Formula)"
    elif mode.startswith("B"):
        z = actual_matrix
        colorscale = [[0, C_BG], [0.3, C_GREY], [0.6, C_TEAL], [1, C_GOLD]]
        title = "Actual Collision Counts (Database)"
    else:
        # Delta: normalize both, compute difference
        max_pred = max(max(row) for row in pred_matrix) or 1
        max_actual = max(max(row) for row in actual_matrix) or 1
        z = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                norm_p = pred_matrix[i][j] / max_pred
                norm_a = actual_matrix[i][j] / max_actual
                z[i][j] = norm_a - norm_p  # Positive = more than predicted
        colorscale = [[0, C_RED], [0.5, C_BG], [1, C_TEAL]]
        title = "Delta: Green = More than predicted, Red = Less"

    fig = go.Figure(data=go.Heatmap(
        z=z, x=short_names, y=short_names,
        colorscale=colorscale,
        hoverongaps=False,
    ))
    styled_fig(fig, title=title, height=700,
               xaxis=dict(tickangle=45), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, use_container_width=True)

    # Click to explore a pair
    st.subheader("Explore Domain Pair")
    col1, col2 = st.columns(2)
    d1 = col1.selectbox("Domain A", domains, index=0)
    d2 = col2.selectbox("Domain B", domains, index=min(1, n - 1))

    if d1 and d2 and d1 != d2:
        score = compute_collision_formula(d1, d2)
        st.json(score)

        pair_collisions = query("""
            SELECT collision_description, num_domains, created_at
            FROM collisions
            WHERE source_types LIKE ? AND source_types LIKE ?
            ORDER BY created_at DESC LIMIT 10
        """, (f"%{d1}%", f"%{d2}%"))
        if pair_collisions:
            st.dataframe(pair_collisions, use_container_width=True)
        else:
            st.info(f"No collisions found between {d1} and {d2}")

    # Formula parameters sidebar
    st.sidebar.subheader("Formula Parameters")
    if table_exists("formula_validation"):
        latest_fv = query("SELECT * FROM formula_validation ORDER BY date DESC LIMIT 1", one=True)
        if latest_fv:
            st.sidebar.metric("Pearson r", f"{latest_fv.get('pearson_r', '—')}")
            st.sidebar.metric("Spearman ρ", f"{latest_fv.get('spearman_rho', '—')}")
            st.sidebar.markdown("**Suggested Adjustments:**")
            st.sidebar.text(f"Silo coeff: {latest_fv.get('suggested_silo_coeff', 0.003)}")
            st.sidebar.text(f"Reinf weight: {latest_fv.get('suggested_reinf_weight', 20)}")
            st.sidebar.text(f"Corr weight: {latest_fv.get('suggested_corr_weight', 30)}")
            st.sidebar.text(f"Resid weight: {latest_fv.get('suggested_resid_weight', 400)}")


# ═══════════════════════════════════════════════════════════════════════
# PAGE 4: CHAIN EXPLORER
# ═══════════════════════════════════════════════════════════════════════
elif page == "⛓️ Chain Explorer":
    st.title("Chain Explorer")

    if not table_exists("chains"):
        st.warning("No chains table found.")
        st.stop()

    # Chain depth distribution
    depth_data = query("""
        SELECT chain_length, COUNT(*) as cnt
        FROM chains GROUP BY chain_length ORDER BY chain_length
    """)

    if not depth_data:
        st.info("No chains found yet. Run HUNTER collision cycles to discover chains.")
        st.stop()

    depths = [d["chain_length"] for d in depth_data]
    counts = [d["cnt"] for d in depth_data]
    total_chains = sum(counts)
    base = counts[0] if counts else 1

    # Predicted distribution
    pred_depths = list(range(1, max(depths) + 1))
    pred_counts = [base * ((1 - PREDICTED_DECAY) ** (d - 1)) for d in pred_depths]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=depths, y=counts, name="Actual",
                         marker_color=C_TEAL, opacity=0.8))
    fig.add_trace(go.Scatter(x=pred_depths, y=pred_counts, name="Predicted (0.273 decay)",
                             mode="lines+markers", line=dict(color=C_GOLD, width=2, dash="dash")))
    styled_fig(fig, title=f"Chain Depth Distribution ({total_chains} total chains)",
               xaxis_title="Chain Depth", yaxis_title="Count", height=400)
    st.plotly_chart(fig, use_container_width=True)

    # Scatter: depth vs hypothesis value
    st.subheader("Chain Depth vs Hypothesis Value")
    scatter_data = query("""
        SELECT ch.chain_length, h.diamond_score, h.hypothesis_text
        FROM chains ch
        JOIN hypotheses h ON ch.collision_id = h.collision_id
        WHERE h.diamond_score IS NOT NULL
    """)
    if scatter_data:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=[d["chain_length"] for d in scatter_data],
            y=[d["diamond_score"] for d in scatter_data],
            mode="markers",
            marker=dict(size=8, color=C_TEAL, opacity=0.6),
            text=[d.get("hypothesis_text", "")[:60] for d in scatter_data],
            hoverinfo="text+x+y",
        ))
        styled_fig(fig2, title="Chain Depth vs Diamond Score (theory: positive correlation)",
                   xaxis_title="Chain Depth", yaxis_title="Diamond Score", height=400)
        st.plotly_chart(fig2, use_container_width=True)

    # Top 10 chains by value
    st.subheader("Top 10 Chains by Hypothesis Value")
    top_chains = query("""
        SELECT ch.chain_length, ch.domains_traversed, ch.num_domains,
               h.diamond_score, h.hypothesis_text, ch.created_at
        FROM chains ch
        JOIN hypotheses h ON ch.collision_id = h.collision_id
        WHERE h.diamond_score IS NOT NULL
        ORDER BY h.diamond_score DESC LIMIT 10
    """)
    if top_chains:
        st.dataframe(top_chains, use_container_width=True)

    # Decay curve
    st.subheader("Empirical Decay Curve")
    if len(depths) >= 2:
        decay_ratios = []
        for i in range(1, len(depth_data)):
            if depth_data[i - 1]["cnt"] > 0:
                ratio = depth_data[i]["cnt"] / depth_data[i - 1]["cnt"]
                decay_ratios.append({"depth": depth_data[i]["chain_length"], "ratio": ratio})

        if decay_ratios:
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(
                x=[d["depth"] for d in decay_ratios],
                y=[d["ratio"] for d in decay_ratios],
                mode="lines+markers", name="Observed",
                line=dict(color=C_TEAL, width=2),
            ))
            fig3.add_hline(y=1 - PREDICTED_DECAY, line_dash="dash",
                          line_color=C_GOLD, annotation_text=f"Predicted: {1-PREDICTED_DECAY:.3f}")
            styled_fig(fig3, title="Decay Ratio by Depth (chains at d / chains at d-1)",
                       xaxis_title="Depth", yaxis_title="Ratio", height=350)
            st.plotly_chart(fig3, use_container_width=True)

            empirical = sum(d["ratio"] for d in decay_ratios) / len(decay_ratios)
            st.metric("Empirical Avg Decay Ratio", f"{empirical:.3f}",
                      delta=f"{empirical - (1-PREDICTED_DECAY):+.3f} vs predicted {1-PREDICTED_DECAY:.3f}")


# ═══════════════════════════════════════════════════════════════════════
# PAGE 5: CYCLE MONITOR
# ═══════════════════════════════════════════════════════════════════════
elif page == "🔄 Cycle Monitor":
    st.title("Cycle Monitor")

    if not table_exists("detected_cycles"):
        st.warning("No detected_cycles table. Run CycleDetector agent first.")
        st.stop()

    cycles = query("SELECT * FROM detected_cycles ORDER BY detected_date DESC")
    if not cycles:
        st.info("No cycles detected yet.")
        st.stop()

    # Donut: cycles by type
    type_counts = {}
    for c in cycles:
        ct = c.get("cycle_type", "unknown")
        type_counts[ct] = type_counts.get(ct, 0) + 1

    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure(data=[go.Pie(
            labels=list(type_counts.keys()),
            values=list(type_counts.values()),
            hole=0.5,
            marker=dict(colors=[C_TEAL, C_GOLD, C_RED, C_GREY, C_WHITE,
                               "#9B59B6", "#3498DB", "#E67E22", "#1ABC9C"]),
        )])
        styled_fig(fig, title=f"Cycles by Type ({len(cycles)} total)", height=400)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Cycle Summary")
        for ct, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            st.metric(ct.replace("_", " ").title(), count)

    # Table: all cycles
    st.subheader("All Detected Cycles")
    display_cycles = []
    for c in cycles:
        display_cycles.append({
            "type": c.get("cycle_type", ""),
            "nodes": (c.get("nodes", "")[:60] + "...") if len(c.get("nodes", "")) > 60 else c.get("nodes", ""),
            "domains": c.get("domains", ""),
            "strength": c.get("reinforcement_strength", 0),
            "correction": c.get("correction_pressure", 0),
            "persistence": c.get("persistence_estimate", 0),
            "age_days": c.get("age_days", 0),
            "active": "✅" if c.get("is_active") else "💤",
            "date": c.get("detected_date", "")[:10],
        })
    st.dataframe(display_cycles, use_container_width=True)

    # Time series: cycle count over time
    st.subheader("Cycles Discovered Over Time")
    time_data = query("""
        SELECT DATE(detected_date) as day, COUNT(*) as cnt
        FROM detected_cycles GROUP BY DATE(detected_date) ORDER BY day
    """)
    if time_data:
        cumulative = 0
        for d in time_data:
            cumulative += d["cnt"]
            d["cumulative"] = cumulative

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=[d["day"] for d in time_data],
            y=[d["cumulative"] for d in time_data],
            mode="lines+markers", line=dict(color=C_TEAL, width=2),
            fill="tozeroy", fillcolor="rgba(77,208,225,0.1)",
        ))
        styled_fig(fig2, title="Cumulative Cycles Detected", height=350,
                   xaxis_title="Date", yaxis_title="Total Cycles")
        st.plotly_chart(fig2, use_container_width=True)

    # Persistence chart
    st.subheader("Persistence: Reinforcement vs Correction Pressure")
    active_cycles = [c for c in cycles if c.get("is_active")]
    if active_cycles:
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(
            x=[c.get("correction_pressure", 0) for c in active_cycles],
            y=[c.get("reinforcement_strength", 0) for c in active_cycles],
            mode="markers",
            marker=dict(size=[max(5, min(20, c.get("persistence_estimate", 1)))
                             for c in active_cycles],
                       color=[c.get("persistence_estimate", 0) for c in active_cycles],
                       colorscale=[[0, C_GREY], [0.5, C_GOLD], [1, C_RED]],
                       colorbar=dict(title="Persistence")),
            text=[f"{c.get('cycle_type', '')}: {c.get('persistence_estimate', 0):.1f}x"
                  for c in active_cycles],
            hoverinfo="text",
        ))
        # Add 207x reference line (reinf/corr = 207)
        fig3.add_trace(go.Scatter(
            x=[0, 0.01, 0.05], y=[0, 0.01 * PREDICTED_PERSISTENCE, 0.05 * PREDICTED_PERSISTENCE],
            mode="lines", line=dict(color=C_GOLD, dash="dash", width=1),
            name=f"{PREDICTED_PERSISTENCE}x line",
        ))
        styled_fig(fig3, title="Reinforcement vs Correction (size = persistence)",
                   xaxis_title="Correction Pressure", yaxis_title="Reinforcement Strength",
                   height=400)
        st.plotly_chart(fig3, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════
# PAGE 6: BACKTEST RESULTS
# ═══════════════════════════════════════════════════════════════════════
elif page == "📈 Backtest Results":
    st.title("Backtest Results")

    if not table_exists("backtest_results"):
        st.warning("No backtest_results table. Run BacktestReconciler agent first.")
        st.stop()

    bt = query("""
        SELECT br.*, h.diamond_score, h.hypothesis_text, h.created_at as hyp_date
        FROM backtest_results br
        JOIN hypotheses h ON br.hypothesis_id = h.id
        ORDER BY br.reconciled_date DESC
    """)

    if not bt:
        st.info("No backtests completed yet.")
        st.stop()

    total = len(bt)
    dir_hits = sum(1 for b in bt if b.get("direction_correct"))
    timing_hits = sum(1 for b in bt if b.get("within_timeframe"))
    mech_hits = sum(1 for b in bt if b.get("mechanism_confirmed"))

    # Top metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Hypotheses Tested", total)
    c2.metric("Directional Accuracy", f"{dir_hits/total:.0%}" if total else "—")
    c3.metric("Timing Accuracy", f"{timing_hits/total:.0%}" if total else "—")
    c4.metric("Mechanism Confirmed", f"{mech_hits/total:.0%}" if total else "—")

    # Calibration curve
    st.subheader("Score Calibration Curve")
    buckets = {"50-59": [], "60-69": [], "70-79": [], "80-89": [], "90+": []}
    for b in bt:
        s = b.get("diamond_score", 0) or 0
        if s >= 90:
            buckets["90+"].append(b)
        elif s >= 80:
            buckets["80-89"].append(b)
        elif s >= 70:
            buckets["70-79"].append(b)
        elif s >= 60:
            buckets["60-69"].append(b)
        else:
            buckets["50-59"].append(b)

    cal_labels = list(buckets.keys())
    cal_counts = [len(v) for v in buckets.values()]
    cal_hits = [sum(1 for b in v if b.get("direction_correct")) / max(1, len(v))
                for v in buckets.values()]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=cal_labels, y=cal_hits, name="Actual Hit Rate",
                         marker_color=C_TEAL, opacity=0.8))
    fig.add_trace(go.Scatter(x=cal_labels, y=[0.3, 0.45, 0.6, 0.75, 0.9],
                             name="Ideal Calibration", mode="lines+markers",
                             line=dict(color=C_GOLD, dash="dash")))
    styled_fig(fig, title="Score Decile vs Actual Hit Rate",
               xaxis_title="Score Bucket", yaxis_title="Hit Rate", height=400,
               yaxis=dict(range=[0, 1]))
    st.plotly_chart(fig, use_container_width=True)

    # Predicted vs actual magnitude scatter
    st.subheader("Predicted vs Actual Magnitude")
    scatter_bt = [b for b in bt if b.get("magnitude_predicted") is not None
                  and b.get("magnitude_actual") is not None]
    if scatter_bt:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=[b["magnitude_predicted"] for b in scatter_bt],
            y=[b["magnitude_actual"] for b in scatter_bt],
            mode="markers",
            marker=dict(size=10, color=[b.get("diamond_score", 50) for b in scatter_bt],
                       colorscale=[[0, C_GREY], [0.5, C_GOLD], [1, C_RED]],
                       colorbar=dict(title="Score")),
            text=[b.get("hypothesis_text", "")[:50] for b in scatter_bt],
            hoverinfo="text+x+y",
        ))
        # Perfect prediction line
        max_val = max(max(b["magnitude_predicted"] for b in scatter_bt),
                      max(b["magnitude_actual"] for b in scatter_bt))
        fig2.add_trace(go.Scatter(x=[0, max_val], y=[0, max_val],
                                  mode="lines", line=dict(color=C_GOLD, dash="dash"),
                                  name="Perfect Prediction"))
        styled_fig(fig2, title="Predicted vs Actual Magnitude (%)",
                   xaxis_title="Predicted %", yaxis_title="Actual %", height=400)
        st.plotly_chart(fig2, use_container_width=True)

    # Breakdown tables
    st.subheader("Accuracy by Chain Depth")
    depth_bt = {}
    for b in bt:
        d = b.get("chain_depth", 0) or 0
        if d not in depth_bt:
            depth_bt[d] = {"total": 0, "hits": 0}
        depth_bt[d]["total"] += 1
        if b.get("direction_correct"):
            depth_bt[d]["hits"] += 1
    depth_table = [{"depth": d, "count": v["total"],
                    "accuracy": f"{v['hits']/v['total']:.0%}"}
                   for d, v in sorted(depth_bt.items())]
    st.dataframe(depth_table, use_container_width=True)

    st.subheader("Accuracy by Domain Distance")
    dist_bt = {"< 0.3": {"t": 0, "h": 0}, "0.3-0.5": {"t": 0, "h": 0},
               "0.5-0.7": {"t": 0, "h": 0}, "> 0.7": {"t": 0, "h": 0}}
    for b in bt:
        dd = b.get("domain_distance", 0) or 0
        if dd > 0.7:
            key = "> 0.7"
        elif dd > 0.5:
            key = "0.5-0.7"
        elif dd > 0.3:
            key = "0.3-0.5"
        else:
            key = "< 0.3"
        dist_bt[key]["t"] += 1
        if b.get("direction_correct"):
            dist_bt[key]["h"] += 1
    dist_table = [{"distance": k, "count": v["t"],
                   "accuracy": f"{v['h']/max(1,v['t']):.0%}"}
                  for k, v in dist_bt.items()]
    st.dataframe(dist_table, use_container_width=True)

    # P&L curve
    st.subheader("Hypothetical P&L (if traded)")
    sorted_bt = sorted(bt, key=lambda b: b.get("hyp_date", ""))
    cumulative_pnl = 0
    pnl_series = []
    for b in sorted_bt:
        mag = b.get("magnitude_actual", 0) or 0
        direction = 1 if b.get("direction_correct") else -1
        pnl = abs(mag) * direction * 0.01  # As fraction
        cumulative_pnl += pnl
        pnl_series.append({"date": b.get("hyp_date", "")[:10], "pnl": cumulative_pnl * 100})

    if pnl_series:
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(
            x=[p["date"] for p in pnl_series],
            y=[p["pnl"] for p in pnl_series],
            mode="lines", line=dict(color=C_TEAL, width=2),
            fill="tozeroy",
            fillcolor="rgba(77,208,225,0.1)" if cumulative_pnl >= 0 else "rgba(255,107,107,0.1)",
        ))
        fig3.add_hline(y=0, line_color=C_GREY)
        styled_fig(fig3, title="Cumulative Hypothetical Return (%)",
                   xaxis_title="Date", yaxis_title="Cumulative Return %", height=350)
        st.plotly_chart(fig3, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════
# PAGE 7: RESIDUAL TRACKER
# ═══════════════════════════════════════════════════════════════════════
elif page == "💰 Residual Tracker":
    st.title("Residual Tracker")

    if not table_exists("residual_estimates"):
        st.warning("No residual_estimates table. Run ResidualEstimator agent first.")
        st.stop()

    estimates = query("SELECT * FROM residual_estimates ORDER BY date DESC")
    if not estimates:
        st.info("No residual estimates yet.")
        st.stop()

    # Get latest estimates per domain
    latest_date = estimates[0].get("date", "")[:10] if estimates else ""
    latest = [e for e in estimates if (e.get("date", "")[:10]) == latest_date]

    # Top metrics
    total_observed = sum(e.get("estimated_residual_B", 0) or 0 for e in latest)
    total_predicted = sum((e.get("market_size_B", 0) or 0) * (e.get("predicted_residual_pct", 0) or 0) / 100
                          for e in latest)
    domains_with_data = sum(1 for e in latest if e.get("observed_residual_pct") is not None)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Estimated Total", f"${total_observed/1000:.2f}T",
              delta=f"vs ${PREDICTED_TOTAL_T}T predicted")
    c2.metric("Domains with Data", f"{domains_with_data}/{len(latest)}")
    c3.metric("Predicted Total", f"${total_predicted/1000:.2f}T")
    c4.metric("Coverage", f"{domains_with_data/max(1,len(latest)):.0%}")

    # Bar chart: observed vs predicted per domain
    st.subheader("Residual by Domain: Observed vs Predicted")
    if latest:
        sorted_latest = sorted(latest, key=lambda e: e.get("estimated_residual_B", 0) or 0, reverse=True)
        domain_names = [e.get("domain", "")[:12] for e in sorted_latest]
        observed_vals = [e.get("estimated_residual_B", 0) or 0 for e in sorted_latest]
        predicted_vals = [(e.get("market_size_B", 0) or 0) * (e.get("predicted_residual_pct", 0) or 0) / 100
                         for e in sorted_latest]

        fig = go.Figure()
        fig.add_trace(go.Bar(x=domain_names, y=observed_vals, name="Observed",
                             marker_color=C_TEAL))
        fig.add_trace(go.Bar(x=domain_names, y=predicted_vals, name="Predicted",
                             marker_color=C_GOLD, opacity=0.5))
        styled_fig(fig, title="Estimated Residual by Domain ($B)",
                   xaxis_title="Domain", yaxis_title="$B", height=450,
                   barmode="group", xaxis=dict(tickangle=45))
        st.plotly_chart(fig, use_container_width=True)

    # Donut: chain vs cycle vs hierarchy
    st.subheader("Residual Source Breakdown")
    # Get from latest theory evidence summary if available
    te_summary = query("""
        SELECT domain_pair FROM theory_evidence
        WHERE source_event = 'residual_estimation'
        ORDER BY timestamp DESC LIMIT 1
    """, one=True)
    if te_summary and te_summary.get("domain_pair"):
        try:
            summary = json.loads(te_summary["domain_pair"])
            agg = summary.get("aggregate", {})
            chain_t = agg.get("chain_residual_T", 0)
            cycle_t = agg.get("cycle_residual_T", 0)
            hier_t = agg.get("hierarchy_residual_T", 0)

            fig2 = go.Figure(data=[go.Pie(
                labels=["Chain", "Cycle", "Hierarchy"],
                values=[chain_t, cycle_t, hier_t],
                hole=0.5,
                marker=dict(colors=[C_TEAL, C_GOLD, C_RED]),
            )])
            styled_fig(fig2, title="Residual by Source Type ($T)", height=400)
            st.plotly_chart(fig2, use_container_width=True)

            # Comparison table
            comp_data = [
                {"Source": "Chain", "Observed": f"${chain_t:.2f}T", "Predicted": f"${PREDICTED_CHAIN_T}T",
                 "Delta": f"${chain_t - PREDICTED_CHAIN_T:+.2f}T"},
                {"Source": "Cycle", "Observed": f"${cycle_t:.2f}T", "Predicted": f"${PREDICTED_CYCLE_T}T",
                 "Delta": f"${cycle_t - PREDICTED_CYCLE_T:+.2f}T"},
                {"Source": "Hierarchy", "Observed": f"${hier_t:.2f}T", "Predicted": f"${PREDICTED_HIERARCHY_T}T",
                 "Delta": f"${hier_t - PREDICTED_HIERARCHY_T:+.2f}T"},
                {"Source": "TOTAL", "Observed": f"${chain_t+cycle_t+hier_t:.2f}T",
                 "Predicted": f"${PREDICTED_TOTAL_T}T",
                 "Delta": f"${chain_t+cycle_t+hier_t - PREDICTED_TOTAL_T:+.2f}T"},
            ]
            st.dataframe(comp_data, use_container_width=True)
        except (json.JSONDecodeError, TypeError):
            st.info("No source breakdown available yet.")
    else:
        st.info("No source breakdown available. Run ResidualEstimator agent.")

    # Time series: rolling estimate
    st.subheader("Rolling Residual Estimate Over Time")
    time_est = query("""
        SELECT date, SUM(estimated_residual_B) as total_B
        FROM residual_estimates
        GROUP BY date ORDER BY date
    """)
    if time_est:
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(
            x=[t["date"][:10] for t in time_est],
            y=[t["total_B"] / 1000 for t in time_est],
            mode="lines+markers", line=dict(color=C_TEAL, width=2),
            fill="tozeroy", fillcolor="rgba(77,208,225,0.1)",
        ))
        fig3.add_hline(y=PREDICTED_TOTAL_T, line_dash="dash", line_color=C_GOLD,
                      annotation_text=f"Predicted: ${PREDICTED_TOTAL_T}T")
        styled_fig(fig3, title="Total Estimated Residual Over Time ($T)",
                   xaxis_title="Date", yaxis_title="$T", height=350)
        st.plotly_chart(fig3, use_container_width=True)

    # Confidence interval
    if te_summary and te_summary.get("domain_pair"):
        try:
            summary = json.loads(te_summary["domain_pair"])
            ci = summary.get("aggregate", {}).get("confidence_interval_95", [])
            if ci and len(ci) == 2:
                st.metric("95% Confidence Interval",
                          f"${ci[0]:.2f}T — ${ci[1]:.2f}T")
        except (json.JSONDecodeError, TypeError):
            pass


# ═══════════════════════════════════════════════════════════════════════
# PAGE 8: THEORY HEALTH
# ═══════════════════════════════════════════════════════════════════════
elif page == "🏥 Theory Health":
    st.title("Theory Health")

    if not table_exists("theory_evidence"):
        st.warning("No theory evidence data.")
        st.stop()

    # Per-layer evidence summary
    layer_summary = query("""
        SELECT layer, layer_name, evidence_type, COUNT(*) as cnt,
               AVG(confidence) as avg_conf
        FROM theory_evidence GROUP BY layer, evidence_type
    """)

    # Aggregate per layer
    layers = {}
    for r in layer_summary:
        l = r["layer"]
        if l not in layers:
            layers[l] = {"name": r.get("layer_name", LAYER_NAMES.get(l, f"Layer {l}")),
                         "direct": 0, "supporting": 0, "challenging": 0,
                         "total": 0, "confidence": 0}
        et = r.get("evidence_type", "supporting")
        layers[l][et] = r["cnt"]
        layers[l]["total"] += r["cnt"]
        layers[l]["confidence"] = max(layers[l]["confidence"], r.get("avg_conf", 0) or 0)

    # Overall theory validation score (0-100)
    total_evidence = sum(l["total"] for l in layers.values())
    total_direct = sum(l["direct"] for l in layers.values())
    total_challenging = sum(l["challenging"] for l in layers.values())
    layers_with_evidence = sum(1 for l in layers.values() if l["total"] > 0)

    # Score formula: coverage × evidence quality × challenge penalty
    coverage_score = min(40, layers_with_evidence * (40 / 13))
    quality_score = min(40, total_direct * 2)
    challenge_penalty = min(20, total_challenging * 3)
    theory_score = max(0, min(100, coverage_score + quality_score - challenge_penalty))

    # Big score
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Theory Validation Score", f"{theory_score:.0f}/100")
    c2.metric("Layers with Evidence", f"{layers_with_evidence}/13")
    c3.metric("Direct Evidence", total_direct)
    c4.metric("Challenges", total_challenging, delta_color="inverse")

    st.markdown("---")

    # Per-layer detail
    st.subheader("Per-Layer Evidence")
    for l_num in sorted(layers.keys()):
        l = layers[l_num]
        name = l["name"]
        total = l["total"]
        direct = l["direct"]
        supporting = l["supporting"]
        challenging = l["challenging"]
        conf = l["confidence"]

        # Color based on evidence quality
        if challenging > direct:
            status = "🔴"
        elif direct > 0:
            status = "🟢"
        elif supporting > 0:
            status = "🟡"
        else:
            status = "⚪"

        col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
        col1.markdown(f"{status} **L{l_num:02d}: {name}**")
        col2.caption(f"Direct: {direct}")
        col3.caption(f"Supporting: {supporting}")
        col4.caption(f"Challenging: {challenging}")
        col5.caption(f"Conf: {conf:.2f}")

    st.markdown("---")

    # Challenges section
    st.subheader("🔴 Challenges — Evidence Against Theory")
    challenges = query("""
        SELECT layer, layer_name, description, observed_value, predicted_value,
               confidence, timestamp
        FROM theory_evidence
        WHERE evidence_type = 'challenging'
        ORDER BY confidence DESC, timestamp DESC
        LIMIT 20
    """)
    if challenges:
        for c in challenges:
            with st.expander(f"L{c.get('layer', '?')}: {(c.get('description', '') or '')[:100]}"):
                st.write(c.get("description", ""))
                col1, col2, col3 = st.columns(3)
                col1.metric("Observed", c.get("observed_value"))
                col2.metric("Predicted", c.get("predicted_value"))
                col3.metric("Confidence", f"{c.get('confidence', 0):.2f}")
    else:
        st.success("No challenging evidence found — theory unchallenged so far.")

    # Open questions
    st.subheader("❓ Open Questions — Where More Data Is Needed")
    missing_layers = [l for l in range(1, 14) if l not in layers or layers[l]["total"] < 5]
    if missing_layers:
        for l in missing_layers:
            name = LAYER_NAMES.get(l, f"Layer {l}")
            count = layers.get(l, {}).get("total", 0)
            st.markdown(f"- **L{l:02d}: {name}** — only {count} evidence points "
                        f"(need 50 for significance)")
    else:
        st.success("All layers have sufficient data!")

    # Suggested next targets
    st.subheader("🎯 Suggested Next Targets for Maximum Evidence Value")
    # Layers with least evidence that are most important
    priority_layers = sorted(
        [(l, layers.get(l, {"total": 0})["total"]) for l in range(1, 14)],
        key=lambda x: x[1]
    )
    suggestions = [
        (1, "Ingest more cross-domain facts to generate translation loss measurements"),
        (8, "Run DecayTracker more frequently to build persistence ratio sample"),
        (7, "Extend more chains to depth 3+ for depth-value curve fitting"),
        (12, "Run CollisionFormulaValidator to test autopoiesis predictions"),
        (10, "Track hypotheses past 120-day mark for structural incompleteness"),
        (4, "Run BacktestReconciler on expired hypotheses for phase transition evidence"),
    ]
    for layer, suggestion in suggestions:
        if layers.get(layer, {}).get("total", 0) < 20:
            st.markdown(f"- **L{layer:02d}**: {suggestion}")
