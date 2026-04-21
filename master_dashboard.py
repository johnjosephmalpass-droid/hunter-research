"""HUNTER master dashboard.

Single-instrument view over the pre-registration-locked corpus and the
theory-layer agents. Five tabs: Overview, Corpus, Graph, Hypotheses, Study,
Operations. Read-only.

Run:
    streamlit run master_dashboard.py
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent
DB = ROOT / "hunter.db"
MANIFEST = ROOT / "preregistration.json"
GOALS = ROOT / "goals.json"
PRED_HTML = ROOT / "docs" / "index.html"

st.set_page_config(
    page_title="HUNTER",
    layout="wide",
    page_icon=None,
    initial_sidebar_state="collapsed",
)

# --------------------------------------------------------------------------
# Palette + typography
# --------------------------------------------------------------------------
BG        = "#0a0a0b"
PANEL     = "#111214"
PANEL_ALT = "#17181b"
BORDER    = "#232428"
TEXT      = "#e4e4e7"
MUTED     = "#737378"
ACCENT    = "#c9a24b"
POSITIVE  = "#5d9b63"
NEGATIVE  = "#b84c4c"
WARNING   = "#c8963b"

st.markdown(f"""
<style>
    .stApp {{ background: {BG}; }}
    html, body, [class*="st-"] {{
        color: {TEXT};
        font-family: -apple-system, "SF Pro Text", "Segoe UI", Helvetica, Arial, sans-serif;
    }}
    h1, h2, h3, h4, h5, h6 {{
        color: {TEXT};
        font-weight: 500;
        letter-spacing: -0.005em;
    }}
    h1 {{ font-size: 1.35rem; margin: 0 0 2px 0; }}
    h2 {{
        font-size: 0.95rem; margin: 28px 0 10px 0;
        text-transform: uppercase; letter-spacing: 0.08em;
        color: {MUTED}; font-weight: 600;
        border-bottom: 1px solid {BORDER}; padding-bottom: 6px;
    }}
    h3 {{ font-size: 0.85rem; margin: 18px 0 6px 0;
          color: {TEXT}; font-weight: 600; letter-spacing: 0.02em; }}
    p, li, span, div {{ font-size: 0.88rem; }}
    .stCaption, [data-testid="stCaptionContainer"] {{
        color: {MUTED}; font-size: 0.78rem;
    }}

    /* Tab bar */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 0; border-bottom: 1px solid {BORDER};
    }}
    .stTabs [data-baseweb="tab"] {{
        background: transparent; border-radius: 0;
        padding: 10px 22px; color: {MUTED};
        font-weight: 500; font-size: 0.85rem;
        border-bottom: 2px solid transparent;
    }}
    .stTabs [aria-selected="true"] {{
        background: transparent; color: {TEXT};
        border-bottom: 2px solid {ACCENT};
    }}

    /* Metrics: small, dense, numeric-tabular */
    [data-testid="stMetricValue"] {{
        color: {TEXT}; font-size: 1.15rem; font-weight: 500;
        font-variant-numeric: tabular-nums;
    }}
    [data-testid="stMetricLabel"] {{
        color: {MUTED}; font-size: 0.72rem;
        text-transform: uppercase; letter-spacing: 0.08em; font-weight: 500;
    }}
    [data-testid="stMetricDelta"] {{
        color: {MUTED}; font-size: 0.72rem; font-variant-numeric: tabular-nums;
    }}

    /* Tables */
    .stDataFrame, [data-testid="stDataFrame"] {{
        background: {PANEL}; border: 1px solid {BORDER}; border-radius: 4px;
    }}
    .stDataFrame table {{
        font-variant-numeric: tabular-nums; font-size: 0.82rem;
    }}

    /* Expanders */
    .stExpander {{
        background: {PANEL}; border: 1px solid {BORDER}; border-radius: 4px;
    }}
    .stExpander summary {{ color: {TEXT}; }}

    /* Horizontal rule */
    hr {{ border-color: {BORDER}; margin: 18px 0; }}

    /* Sidebar (unused but if ever opened, match palette) */
    [data-testid="stSidebar"] {{ background: {PANEL}; }}

    /* Remove st.info/st.success/st.error gradient backgrounds */
    [data-testid="stNotification"] {{
        background: {PANEL}; border: 1px solid {BORDER};
        border-left: 3px solid {ACCENT}; color: {TEXT};
    }}

    /* Code blocks */
    code {{
        background: {PANEL_ALT}; color: {ACCENT};
        padding: 1px 5px; border-radius: 3px; font-size: 0.82rem;
    }}

    /* Custom classes */
    .zero {{
        background: {PANEL}; border: 1px solid {BORDER};
        border-left: 3px solid {MUTED};
        padding: 12px 16px; border-radius: 4px;
        color: {MUTED}; font-size: 0.85rem;
    }}
    .row-item {{
        background: {PANEL}; border: 1px solid {BORDER};
        padding: 10px 14px; margin: 4px 0; border-radius: 3px;
        font-size: 0.86rem;
    }}
    .row-item .score {{
        font-variant-numeric: tabular-nums; font-weight: 600;
        margin-right: 10px; color: {ACCENT};
    }}
    .row-item .meta {{ color: {MUTED}; font-size: 0.76rem; margin-top: 3px; }}
    .row-item .body {{ color: {TEXT}; margin-top: 6px; font-size: 0.82rem; }}
    .status-ok   {{ color: {POSITIVE}; }}
    .status-warn {{ color: {WARNING}; }}
    .status-err  {{ color: {NEGATIVE}; }}
    .status-idle {{ color: {MUTED}; }}

    /* Header strip */
    .header-strip {{
        display: flex; align-items: baseline; gap: 24px;
        padding: 8px 0 6px 0; margin-bottom: 8px;
        border-bottom: 1px solid {BORDER};
    }}
    .header-strip .title {{
        font-size: 1.05rem; font-weight: 600; color: {TEXT};
        letter-spacing: 0.02em;
    }}
    .header-strip .subtitle {{
        font-size: 0.78rem; color: {MUTED};
        font-variant-numeric: tabular-nums;
    }}
    .header-strip .tag {{
        background: {PANEL}; border: 1px solid {BORDER};
        padding: 2px 8px; border-radius: 3px;
        font-size: 0.72rem; color: {MUTED};
        text-transform: uppercase; letter-spacing: 0.08em;
    }}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# DB helpers
# --------------------------------------------------------------------------
@st.cache_data(ttl=30, show_spinner=False)
def sql(q: str, params: tuple = ()) -> pd.DataFrame:
    try:
        conn = sqlite3.connect(DB)
        df = pd.read_sql_query(q, conn, params=params)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=30, show_spinner=False)
def sql_one(q: str, params: tuple = ()):
    try:
        conn = sqlite3.connect(DB)
        row = conn.execute(q, params).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def fmt(n) -> str:
    if n is None:
        return "—"
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n)


def zero(msg: str) -> None:
    st.markdown(f"<div class='zero'>{msg}</div>", unsafe_allow_html=True)


def section(title: str) -> None:
    st.markdown(f"## {title}")


# --------------------------------------------------------------------------
# Header strip
# --------------------------------------------------------------------------
now = datetime.now()

try:
    from timeline import current_phase, next_phase  # noqa
    _p = current_phase()
    _nxt = next_phase()
    if _p is not None:
        phase_label = f"Phase {_p.id} · {_p.name}"
        phase_sub = f"{_p.days_remaining()} days remaining"
    elif _nxt is not None:
        phase_label = f"Pre-phase · {_nxt.name}"
        phase_sub = f"starts in {(_nxt.start - now.date()).days} days"
    else:
        phase_label = "No active phase"
        phase_sub = ""
except Exception:
    phase_label = "—"
    phase_sub = ""

st.markdown(f"""
<div class='header-strip'>
    <span class='title'>HUNTER</span>
    <span class='subtitle'>Cross-silo research instrument · John Malpass · UCD · 2026</span>
    <span style='flex:1'></span>
    <span class='tag'>{phase_label}</span>
    <span class='subtitle'>{phase_sub}</span>
    <span class='subtitle'>{now.strftime('%Y-%m-%d %H:%M:%S')}</span>
</div>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Hero strip — seven counts
# --------------------------------------------------------------------------
facts_n = sql_one("SELECT COUNT(*) FROM raw_facts") or 0
anomalies_n = sql_one("SELECT COUNT(*) FROM anomalies") or 0
collisions_n = sql_one("SELECT COUNT(*) FROM collisions") or 0
chains_n = sql_one("SELECT COUNT(*) FROM chains") or 0
edges_n = sql_one("SELECT COUNT(*) FROM causal_edges") or 0
hypotheses_n = sql_one("SELECT COUNT(*) FROM hypotheses") or 0
survived_n = sql_one("SELECT COUNT(*) FROM hypotheses WHERE survived_kill=1") or 0
findings_n = sql_one("SELECT COUNT(*) FROM findings") or 0
cycles_n = sql_one("SELECT COUNT(*) FROM detected_cycles") or 0

hero = [
    ("Facts",       facts_n),
    ("Anomalies",   anomalies_n),
    ("Collisions",  collisions_n),
    ("Chains",      chains_n),
    ("Edges",       edges_n),
    ("Hypotheses",  hypotheses_n),
    ("Findings",    findings_n),
    ("Cycles",      cycles_n),
]
cols = st.columns(len(hero))
for c, (label, val) in zip(cols, hero):
    c.metric(label, fmt(val))

st.markdown("<hr>", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Tabs
# --------------------------------------------------------------------------
tabs = st.tabs(["Overview", "Corpus", "Graph", "Hypotheses", "Study", "Operations"])

# ==========================================================================
# 1. OVERVIEW
# ==========================================================================
with tabs[0]:
    c_left, c_right = st.columns([3, 2])

    with c_left:
        section("Pipeline funnel")
        funnel = pd.DataFrame([
            {"Stage": "1  Facts ingested",       "Count": facts_n,       "Yield": "—"},
            {"Stage": "2  Anomalies detected",   "Count": anomalies_n,
             "Yield": f"{(anomalies_n/max(1,facts_n))*100:5.1f}% of facts"},
            {"Stage": "3  Collisions formed",    "Count": collisions_n,
             "Yield": f"{(collisions_n/max(1,anomalies_n))*100:5.1f}% of anomalies"},
            {"Stage": "4  Hypotheses formed",    "Count": hypotheses_n,
             "Yield": f"{(hypotheses_n/max(1,collisions_n))*100:5.1f}% of collisions"},
            {"Stage": "5  Survived kill phase",  "Count": survived_n,
             "Yield": f"{(survived_n/max(1,hypotheses_n))*100:5.1f}% of hypotheses"},
            {"Stage": "6  Findings (score ≥ 65)", "Count": findings_n,
             "Yield": f"{(findings_n/max(1,survived_n))*100:5.1f}% of survivors"},
        ])
        st.dataframe(funnel, hide_index=True, use_container_width=True)

        section("Recent cycle activity")
        recent = sql("""
            SELECT created_at, domain, status, error_message
            FROM cycle_logs ORDER BY id DESC LIMIT 8
        """)
        if not recent.empty:
            recent["created_at"] = pd.to_datetime(recent["created_at"])
            for _, r in recent.iterrows():
                cls = {"completed": "status-ok", "rate_limit": "status-warn"}.get(
                    r["status"], "status-err"
                )
                t = r["created_at"].strftime("%m-%d %H:%M")
                err = f" — {str(r.get('error_message') or '')[:80]}" if r.get("error_message") else ""
                st.markdown(
                    f"<div style='font-family: ui-monospace, monospace; "
                    f"font-size: 0.8rem; padding: 2px 0;'>"
                    f"<span style='color:{MUTED}'>{t}</span>  "
                    f"<span class='{cls}'>{r['status']}</span>  "
                    f"<span style='color:{TEXT}'>[{r['domain']}]</span>"
                    f"<span style='color:{MUTED}'>{err}</span>"
                    f"</div>", unsafe_allow_html=True
                )
        else:
            zero("No cycles logged. Start with `python run.py live`.")

    with c_right:
        section("System state")
        total_cycles = sql_one("SELECT COUNT(*) FROM cycle_logs") or 0
        last24 = sql_one("SELECT COUNT(*) FROM cycle_logs WHERE created_at >= datetime('now', '-1 day')") or 0
        last1h = sql_one("SELECT COUNT(*) FROM cycle_logs WHERE created_at >= datetime('now', '-1 hour')") or 0
        errors24 = sql_one("SELECT COUNT(*) FROM cycle_logs WHERE status != 'completed' AND created_at >= datetime('now', '-1 day')") or 0
        success_rate = (last24 - errors24) / max(1, last24)

        m1, m2 = st.columns(2)
        m1.metric("Cycles total", fmt(total_cycles))
        m2.metric("Cycles 24h", fmt(last24))
        m3, m4 = st.columns(2)
        m3.metric("Cycles 1h", fmt(last1h))
        m4.metric("24h success", f"{success_rate:.0%}",
                  delta=f"{errors24} errors" if errors24 else "clean",
                  delta_color="inverse" if errors24 else "normal")

        section("Pre-registration integrity")
        if MANIFEST.exists():
            try:
                m = json.loads(MANIFEST.read_text())
                rows = [
                    ("Study", m.get("study_name", "—")),
                    ("Cutoff", m.get("corpus_cutoff", "—")),
                    ("Holdout start", m.get("holdout_start", "—")),
                    ("Frozen facts", fmt(m.get("corpus_fact_count"))),
                    ("Code hash", m.get("code_hash", "—")),
                    ("Fact-ID hash", (m.get("corpus_fact_id_hash") or "—")[:16] + "…"),
                    ("Locked", (m.get("created_at") or "—")[:16]),
                ]
                for k, v in rows:
                    st.markdown(
                        f"<div style='display:flex; justify-content:space-between; "
                        f"padding:3px 0; border-bottom:1px solid {BORDER}; font-size:0.82rem;'>"
                        f"<span style='color:{MUTED}'>{k}</span>"
                        f"<span style='font-family:ui-monospace,monospace; color:{TEXT}'>{v}</span>"
                        f"</div>", unsafe_allow_html=True
                    )

                try:
                    from preregister import verify_manifest  # noqa
                    v = verify_manifest()
                    if isinstance(v, dict) and v.get("status") == "ok":
                        st.markdown(
                            f"<div style='margin-top:10px; padding:8px 12px; "
                            f"border:1px solid {POSITIVE}; color:{POSITIVE}; "
                            f"border-radius:3px; font-size:0.82rem;'>"
                            f"Manifest verified · no drift detected</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        drift = (v or {}).get("drift", "unknown") if isinstance(v, dict) else "unknown"
                        st.markdown(
                            f"<div style='margin-top:10px; padding:8px 12px; "
                            f"border:1px solid {NEGATIVE}; color:{NEGATIVE}; "
                            f"border-radius:3px; font-size:0.82rem;'>"
                            f"Drift detected: {drift}</div>",
                            unsafe_allow_html=True,
                        )
                except Exception:
                    pass
            except Exception as e:
                zero(f"Manifest unreadable: {e}")
        else:
            zero("No manifest. Run `python run.py preregister lock`.")


# ==========================================================================
# 2. CORPUS
# ==========================================================================
with tabs[1]:
    section("Source-type distribution")
    sil = sql("""
        SELECT source_type AS silo, COUNT(*) AS n
        FROM raw_facts GROUP BY source_type ORDER BY n DESC
    """)
    if not sil.empty:
        c1, c2 = st.columns([2, 1])
        with c1:
            st.bar_chart(sil.set_index("silo"), height=280)
        with c2:
            st.dataframe(sil, hide_index=True, use_container_width=True, height=300)
    else:
        zero("No facts ingested yet.")

    section("Country coverage")
    cty = sql("""
        SELECT country, COUNT(*) AS facts
        FROM raw_facts WHERE country IS NOT NULL AND country != ''
        GROUP BY country ORDER BY facts DESC LIMIT 20
    """)
    if not cty.empty:
        st.dataframe(cty, hide_index=True, use_container_width=True, height=360)
    else:
        zero("No country-tagged facts.")

    section("Model-field extractions")
    mf_by_type = sql("""
        SELECT field_type, COUNT(*) AS n
        FROM fact_model_fields GROUP BY field_type ORDER BY n DESC
    """)
    if not mf_by_type.empty:
        c1, c2 = st.columns([1, 2])
        c1.dataframe(mf_by_type, hide_index=True, use_container_width=True)
        top_methodologies = sql("""
            SELECT field_value AS methodology, COUNT(*) AS n
            FROM fact_model_fields
            WHERE field_type = 'methodology'
            GROUP BY field_value ORDER BY n DESC LIMIT 20
        """)
        with c2:
            st.markdown("### Top 20 methodologies named across facts")
            if not top_methodologies.empty:
                top_methodologies["methodology"] = top_methodologies["methodology"].str[:100]
                st.dataframe(top_methodologies, hide_index=True, use_container_width=True)
    else:
        zero("No model-field extractions yet.")

    section("Anomaly sample")
    anomalies = sql("""
        SELECT a.id, a.weirdness_score, a.reasoning, r.source_type, r.title
        FROM anomalies a LEFT JOIN raw_facts r ON r.id = a.raw_fact_id
        ORDER BY a.weirdness_score DESC LIMIT 25
    """)
    if not anomalies.empty:
        anomalies["title"] = anomalies["title"].astype(str).str[:80]
        anomalies["reasoning"] = anomalies["reasoning"].astype(str).str[:140]
        st.dataframe(anomalies, hide_index=True, use_container_width=True, height=420)
    else:
        zero("No anomalies flagged yet.")


# ==========================================================================
# 3. GRAPH
# ==========================================================================
with tabs[2]:
    g_edges, g_chains, g_cycles, g_coll = st.tabs(
        ["Causal edges", "Chains", "Cycles", "Collision map"]
    )

    with g_edges:
        section("Directed causal edges with named transmission pathway")
        edges = sql("""
            SELECT id, cause_node, effect_node, relationship_type,
                   confidence, source_type, domain
            FROM causal_edges
        """)
        if not edges.empty:
            m1, m2, m3 = st.columns(3)
            m1.metric("Edges total", fmt(len(edges)))
            m2.metric("Distinct nodes",
                      fmt(edges[["cause_node", "effect_node"]].stack().nunique()))
            m3.metric("Mean confidence", f"{edges['confidence'].mean():.2f}")

            deg_out = edges.groupby("cause_node").size().reset_index(name="out").rename(columns={"cause_node": "node"})
            deg_in = edges.groupby("effect_node").size().reset_index(name="in_").rename(columns={"effect_node": "node"})
            deg = deg_out.merge(deg_in, on="node", how="outer").fillna(0)
            deg["total"] = deg["out"] + deg["in_"]
            deg = deg.sort_values("total", ascending=False).head(15)
            deg["node"] = deg["node"].str[:110]

            st.markdown("### Top 15 hub nodes (by total degree)")
            st.dataframe(deg, hide_index=True, use_container_width=True)

            with st.expander(f"All edges ({len(edges)})"):
                edges["cause_node"] = edges["cause_node"].str[:90]
                edges["effect_node"] = edges["effect_node"].str[:90]
                st.dataframe(edges, hide_index=True, use_container_width=True, height=460)
        else:
            zero("No edges yet. Edges form during ingest + collision cycles.")

    with g_chains:
        section("Multi-link causal chains")
        chains = sql("""
            SELECT id, collision_id, chain_length, num_domains, domains_traversed
            FROM chains ORDER BY chain_length DESC, created_at DESC LIMIT 100
        """)
        if not chains.empty:
            m1, m2, m3 = st.columns(3)
            m1.metric("Chains total", fmt(len(chains)))
            m2.metric("Mean length", f"{chains['chain_length'].mean():.1f}")
            m3.metric("Max length", fmt(chains["chain_length"].max()))
            st.bar_chart(chains["chain_length"].value_counts().sort_index(), height=180)
            st.dataframe(chains, hide_index=True, use_container_width=True, height=360)
        else:
            zero("No chains yet.")

    with g_cycles:
        section("Detected epistemic cycles")
        st.caption("Closed loops A → B → … → A identified by Tarjan SCC over the causal graph.")
        cycles = sql("""
            SELECT id, cycle_type, nodes, domains,
                   reinforcement_strength, persistence_estimate,
                   detected_date, age_days
            FROM detected_cycles
            ORDER BY reinforcement_strength DESC
        """)
        if not cycles.empty:
            tcount = cycles["cycle_type"].value_counts()
            c1, c2 = st.columns([1, 2])
            c1.dataframe(tcount.reset_index().rename(
                columns={"index": "type", "cycle_type": "n"}),
                hide_index=True, use_container_width=True)
            with c2:
                st.markdown("### Cycle details")
                for _, r in cycles.iterrows():
                    try:
                        nodes = json.loads(r["nodes"] or "[]")
                    except Exception:
                        nodes = []
                    with st.expander(
                        f"#{r['id']}  ·  {r['cycle_type']}  ·  "
                        f"{len(nodes)} nodes  ·  strength {r['reinforcement_strength']:.2f}"
                    ):
                        for i, n in enumerate(nodes):
                            if isinstance(n, dict):
                                dom = n.get('domain', '?')
                                meth = n.get('methodology', '')
                                st.markdown(f"**{i+1}.** {dom[:120]}")
                                if meth:
                                    st.caption(meth[:220])
                            else:
                                st.markdown(f"**{i+1}.** {str(n)[:120]}")
                        st.caption(
                            f"detected {str(r['detected_date'])[:10]} · "
                            f"est persistence {r.get('persistence_estimate') or 0:.0f}d"
                        )
        else:
            zero("No cycles detected. Run `python cycle_detector.py run`.")

    with g_coll:
        section("Cross-silo collision pairs (top 20)")
        fire_df = sql("""
            SELECT source_types FROM collisions
            WHERE source_types IS NOT NULL AND source_types != ''
        """)
        if not fire_df.empty:
            pair_counts: dict[str, int] = {}
            for _, r in fire_df.iterrows():
                s = r["source_types"]
                try:
                    types = json.loads(s) if isinstance(s, str) and s.startswith("[") else s.split(",")
                except Exception:
                    types = []
                types = sorted({t.strip() for t in types if t and str(t).strip()})
                if len(types) < 2:
                    continue
                for a, b in combinations(types, 2):
                    key = f"{a} × {b}"
                    pair_counts[key] = pair_counts.get(key, 0) + 1
            if pair_counts:
                top = pd.DataFrame([
                    {"Silo pair": k, "Collisions": v}
                    for k, v in sorted(pair_counts.items(), key=lambda x: -x[1])[:20]
                ])
                st.dataframe(top, hide_index=True, use_container_width=True, height=520)
        else:
            zero("No collisions yet.")


# ==========================================================================
# 4. HYPOTHESES
# ==========================================================================
with tabs[3]:
    h_top, h_all, h_portfolio, h_board = st.tabs(
        ["Top findings", "All hypotheses", "Paper-trade positions", "Public board"]
    )

    with h_top:
        section("Top-scoring hypotheses (score ≥ 65)")
        diamonds = sql("""
            SELECT id, title, score, domain, confidence, summary, created_at
            FROM findings ORDER BY score DESC LIMIT 20
        """)
        if not diamonds.empty:
            c1, c2 = st.columns([1, 3])
            with c1:
                st.markdown("### Score distribution")
                hist = diamonds["score"].value_counts().sort_index()
                st.bar_chart(hist, height=220)
            with c2:
                for _, r in diamonds.head(12).iterrows():
                    score = int(r["score"])
                    st.markdown(f"""
<div class='row-item'>
    <span class='score'>{score}</span>
    <strong>{(r['title'] or '')[:140]}</strong>
    <div class='meta'>{r['domain']} · {r['confidence']} · {str(r['created_at'])[:10]}</div>
    <div class='body'>{(r['summary'] or '')[:320]}</div>
</div>
                    """, unsafe_allow_html=True)
        else:
            zero("No findings yet. Entries appear once HUNTER has run collision cycles "
                 "and produced hypotheses scoring ≥ 65.")

    with h_all:
        section("All hypotheses with completed adversarial review")
        all_h = sql("""
            SELECT h.id, h.diamond_score AS score, h.confidence,
                   h.survived_kill, c.num_domains, c.source_types,
                   substr(h.hypothesis_text, 1, 200) AS thesis,
                   h.time_window_days AS window_d,
                   h.created_at
            FROM hypotheses h LEFT JOIN collisions c ON c.id = h.collision_id
            ORDER BY h.diamond_score DESC
        """)
        if not all_h.empty:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Hypotheses", fmt(len(all_h)))
            m2.metric("Survived", fmt(int((all_h["survived_kill"] == 1).sum())))
            m3.metric("Killed", fmt(int((all_h["survived_kill"] == 0).sum())))
            m4.metric("Mean score", f"{all_h['score'].mean():.1f}")
            st.dataframe(all_h, hide_index=True, use_container_width=True, height=500)
        else:
            zero("No hypotheses yet.")

    with h_portfolio:
        section("Paper-trade positions (internal, not in Zenodo release)")
        positions = sql("""
            SELECT id, ticker, direction, entry_price, current_price,
                   pnl_pct, pnl_gbp, diamond_score, confidence, status,
                   entry_date, close_date, hypothesis_text
            FROM portfolio_positions WHERE ticker != 'LOGGED'
        """)
        if positions.empty:
            zero("No paper-trade positions. The v1 Zenodo release intentionally "
                 "withholds these tables; see docs/LIMITATIONS.md and the summer "
                 "pre-registration for the provenance regime that applies to v2.")
        else:
            opos = positions[positions["status"] == "open"]
            cpos = positions[positions["status"] == "closed"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Open", fmt(len(opos)))
            c2.metric("Closed", fmt(len(cpos)))
            if not cpos.empty:
                c3.metric("Avg closed P&L", f"{cpos['pnl_pct'].mean():+.2f}%")
                wins = int((cpos["pnl_pct"] > 0).sum())
                c4.metric("Win rate", f"{wins/max(1,len(cpos)):.0%}")
            else:
                c3.metric("Avg closed P&L", "—")
                c4.metric("Win rate", "—")

            st.markdown("### Open positions")
            if not opos.empty:
                show = opos[["ticker", "direction", "entry_price", "current_price",
                             "pnl_pct", "pnl_gbp", "diamond_score", "entry_date"]]
                st.dataframe(show, hide_index=True, use_container_width=True)
            else:
                zero("No open positions.")

    with h_board:
        section("Public prediction board")
        st.caption("Every hypothesis scoring ≥ 65 posts with asset, direction, and resolution date. "
                   "Board is deliberately empty until the pre-registered summer run begins June 1.")
        if PRED_HTML.exists():
            st.markdown(
                f"<div class='zero'>Live board deployed at "
                f"<code>{PRED_HTML.relative_to(ROOT)}</code> → "
                f"<code>johnmalpass.github.io/hunter-research/</code></div>",
                unsafe_allow_html=True,
            )
        try:
            from prediction_board import gather_predictions, compute_track_record  # noqa
            preds = gather_predictions(min_score=65)
            tr = compute_track_record(preds)
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Posted", fmt(tr["total_predictions"]))
            c2.metric("Pending", fmt(tr["pending"]))
            c3.metric("Resolved", fmt(tr["resolved"]))
            c4.metric("Hit rate",
                      f"{tr['hit_rate']:.0%}" if tr.get("hit_rate") is not None else "—")
            c5.metric("Brier",
                      f"{tr['brier_score']}" if tr.get("brier_score") is not None else "—")
            if preds:
                df = pd.DataFrame([{
                    "ID": p["id"], "Score": p["diamond_score"],
                    "Status": p["status"], "Posted": p["posted_date"],
                    "Target": p["target_date"], "Days left": p["days_remaining"],
                    "Confidence": p["confidence"],
                    "Thesis": p["thesis_short"],
                } for p in preds])
                st.dataframe(df, hide_index=True, use_container_width=True)
        except Exception as e:
            st.caption(f"Board module not available: {e}")


# ==========================================================================
# 5. STUDY
# ==========================================================================
with tabs[4]:
    s_hyps, s_tests, s_layers = st.tabs(
        ["Pre-registered hypothesis tests", "Framework empirical tests", "13-layer evidence"]
    )

    with s_hyps:
        section("Pre-registered hypothesis tests (frontier)")
        ft = sql("""
            SELECT hypothesis_id, hypothesis_name, supports_hypothesis,
                   observation_value, measured_at
            FROM frontier_test_results ORDER BY measured_at DESC LIMIT 50
        """)
        if not ft.empty:
            latest = ft.drop_duplicates(subset=["hypothesis_id"], keep="first")
            m1, m2, m3 = st.columns(3)
            m1.metric("Tests measured", fmt(len(latest)))
            m2.metric("Supported", fmt(int((latest["supports_hypothesis"] == 1).sum())))
            m3.metric("Refuted", fmt(int((latest["supports_hypothesis"] == 0).sum())))
            st.dataframe(latest, hide_index=True, use_container_width=True, height=420)
        else:
            zero("No frontier-test results. Run `python run.py frontier all`.")

    with s_tests:
        section("1. Collision formula predictiveness")
        fv = sql("SELECT * FROM formula_validation ORDER BY date DESC LIMIT 1")
        if not fv.empty:
            row = fv.iloc[0]
            c1, c2, c3 = st.columns(3)
            c1.metric("Pearson r", f"{row.get('pearson_r', 0):+.3f}")
            c2.metric("Spearman ρ", f"{row.get('spearman_rho', 0):+.3f}")
            c3.metric("p-value", f"{row.get('p_value', 0):.3f}")
        else:
            zero("Run `python formula_validator.py write`.")

        section("2. Measured reinforcement and correction per silo")
        measured = sql("""
            SELECT source_type AS silo, reinforcement_measured, correction_measured,
                   persistence_ratio_measured, n_facts
            FROM measured_domain_params ORDER BY persistence_ratio_measured DESC
        """)
        if not measured.empty:
            st.dataframe(measured, hide_index=True, use_container_width=True, height=320)
        else:
            zero("Run `python reinforcement_measurer.py write`.")

        section("3. Half-life per silo vs 120-day framework prediction")
        hl = sql("""
            SELECT source_type AS silo, half_life_days, n_correction_events, n_observations
            FROM halflife_estimates ORDER BY half_life_days
        """)
        if not hl.empty:
            st.dataframe(hl, hide_index=True, use_container_width=True, height=320)
        else:
            zero("Run `python halflife_estimator.py write`.")

        section("4. Narrative strength vs kill survival")
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
                c3.metric("Uplift",
                          f"{(high['survived_kill'].mean() - low['survived_kill'].mean()):+.1%}")
        else:
            zero("Run `python narrative_detector.py write`.")

    with s_layers:
        section("13-layer theory-evidence matrix")
        layer_names = {
            1: "Translation Loss",      2: "Attention Topology",
            3: "Question Gap",          4: "Phase Transition",
            5: "Rate-Distortion",       6: "Market Incompleteness",
            7: "Depth-Value",           8: "Epistemic Cycles",
            9: "Cycle Hierarchy",       10: "Fractal Incompleteness",
            11: "Negative Space",       12: "Autopoiesis",
            13: "Observer-Dependent",
        }
        ev = sql("""
            SELECT layer, evidence_type, COUNT(*) AS n
            FROM theory_evidence GROUP BY layer, evidence_type
        """)
        rows = []
        for i in range(1, 14):
            le = ev[ev["layer"] == i] if not ev.empty else pd.DataFrame()
            direct = int(le[le["evidence_type"] == "direct"]["n"].sum()) if not le.empty else 0
            support = int(le[le["evidence_type"] == "supporting"]["n"].sum()) if not le.empty else 0
            challenge = int(le[le["evidence_type"] == "challenging"]["n"].sum()) if not le.empty else 0
            if challenge > direct and challenge > 0:
                state = "challenged"
            elif direct > 0:
                state = "direct"
            elif support > 0:
                state = "supporting"
            else:
                state = "empty"
            rows.append({
                "Layer": f"L{i:02d}", "Name": layer_names.get(i, "?"),
                "State": state, "Direct": direct,
                "Supporting": support, "Challenging": challenge,
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ==========================================================================
# 6. OPERATIONS
# ==========================================================================
with tabs[5]:
    o_agents, o_runs, o_goals, o_reports = st.tabs(
        ["Theory agents", "Cycle history", "Goals", "Reports"]
    )

    with o_agents:
        section("Theory-layer agents")
        st.caption("Seven agents attached to the orchestrator. Each writes its most "
                   "recent output into the tables below. Idle does not mean broken; "
                   "it means the agent's next scheduled slot hasn't arrived yet.")

        # Last-run check for each agent's output table
        agent_rows = []
        agent_specs = [
            ("TheoryTelemetry",           "theory_evidence",       "created_at", "per cycle"),
            ("DecayTracker",              "decay_tracking",        "recorded_at", "daily"),
            ("CycleDetector",             "detected_cycles",       "detected_date", "weekly"),
            ("CollisionFormulaValidator", "formula_validation",    "date", "weekly"),
            ("ChainDepthProfiler",        "chains",                "created_at", "weekly"),
            ("BacktestReconciler",        "backtest_results",      "created_at", "weekly"),
            ("ResidualEstimator",         "residual_tam",          "measured_at", "monthly"),
        ]
        for name, table, ts_col, cadence in agent_specs:
            last_ts = sql_one(f"SELECT {ts_col} FROM {table} ORDER BY {ts_col} DESC LIMIT 1")
            n_rows = sql_one(f"SELECT COUNT(*) FROM {table}") or 0
            if last_ts:
                try:
                    dt_last = pd.to_datetime(last_ts).to_pydatetime()
                    age = (datetime.now() - dt_last).total_seconds() / 3600
                    if age < 24:
                        state = "active"
                    elif age < 24 * 7:
                        state = "recent"
                    elif age < 24 * 30:
                        state = "stale"
                    else:
                        state = "idle"
                    last_str = dt_last.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    state = "unknown"
                    last_str = str(last_ts)[:16]
            else:
                state = "empty"
                last_str = "—"
            agent_rows.append({
                "Agent": name,
                "Cadence": cadence,
                "Output table": table,
                "Rows": fmt(n_rows),
                "Last run": last_str,
                "State": state,
            })
        st.dataframe(pd.DataFrame(agent_rows), hide_index=True, use_container_width=True)

        section("Orchestrator scheduling")
        st.markdown(f"""
<div class='zero'>
Theory agents run on fixed intervals from <code>orchestrator.py</code>.<br>
<code>DecayTracker</code> daily at 24h rollover · <code>CycleDetector</code>,
<code>CollisionFormulaValidator</code>, <code>ChainDepthProfiler</code>,
<code>BacktestReconciler</code> weekly on Sundays · <code>ResidualEstimator</code>
monthly on the 1st. <code>TheoryTelemetry</code> runs inline during each
collision cycle. Start the orchestrator with <code>python run.py live</code>.
</div>
        """, unsafe_allow_html=True)

    with o_runs:
        section("Cycle history (last 100)")
        runs = sql("""
            SELECT id, datetime(created_at) AS t, domain, status,
                   tokens_used, duration_seconds, error_message
            FROM cycle_logs ORDER BY id DESC LIMIT 100
        """)
        if not runs.empty:
            runs["t"] = pd.to_datetime(runs["t"])
            runs["hour"] = runs["t"].dt.floor("h")
            hourly = runs.groupby(["hour", "status"]).size().unstack(fill_value=0)
            st.markdown("### Cycles per hour")
            st.line_chart(hourly, height=200)

            st.markdown("### Cycles (most recent 50)")
            show = runs.head(50)[["t", "domain", "status", "tokens_used",
                                    "duration_seconds", "error_message"]]
            st.dataframe(show, hide_index=True, use_container_width=True, height=420)
        else:
            zero("No runs yet.")

    with o_goals:
        section("Self-improvement goals")
        if GOALS.exists():
            g = json.loads(GOALS.read_text())
            idx = g.get("current_goal_index", 0)
            goals = g.get("goals", [])
            if idx < len(goals):
                current = goals[idx]
                st.markdown(f"**Active goal:** {current.get('goal')}")
                st.caption(f"Target: {current.get('target')} · Measure: {current.get('measure')}")
                subgoals = current.get("subgoals", [])
                if subgoals:
                    with st.expander(f"Subgoals ({len(subgoals)})"):
                        for s in subgoals:
                            st.markdown(f"- {s}")
            with st.expander(f"All goals ({len(goals)})"):
                for i, gl in enumerate(goals):
                    marker = "done" if i < idx else ("active" if i == idx else "queued")
                    st.markdown(
                        f"<div style='display:flex; gap:10px; padding:2px 0; "
                        f"font-size:0.82rem;'>"
                        f"<span style='color:{MUTED}; width:60px'>{marker}</span>"
                        f"<span>#{i} {gl.get('goal')}</span></div>",
                        unsafe_allow_html=True,
                    )
        else:
            zero("No goals.json found.")

    with o_reports:
        section("Overseer reports (most recent 5)")
        overseer = sql("""
            SELECT created_at, substr(report_text, 1, 600) AS preview
            FROM overseer_reports ORDER BY id DESC LIMIT 5
        """)
        if not overseer.empty:
            for _, r in overseer.iterrows():
                with st.expander(str(r["created_at"])[:16]):
                    st.markdown(r["preview"])
        else:
            zero("No overseer reports. Run `python targeting.py`.")

        section("Daily summaries")
        daily = sql("""
            SELECT summary_date, total_cycles, total_findings, diamonds_found,
                   most_promising_thread
            FROM daily_summaries ORDER BY summary_date DESC LIMIT 14
        """)
        if not daily.empty:
            st.dataframe(daily, hide_index=True, use_container_width=True, height=420)
        else:
            zero("No daily summaries yet.")


# --------------------------------------------------------------------------
# Footer
# --------------------------------------------------------------------------
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown(
    f"<div style='color:{MUTED}; font-size:0.75rem; text-align:center;'>"
    f"HUNTER · {now.strftime('%Y-%m-%d %H:%M:%S')} · John Malpass · "
    f"University College Dublin · "
    f"<a href='https://github.com/Johnmalpass/hunter-research' "
    f"style='color:{ACCENT}; text-decoration:none;'>repo</a> · "
    f"<a href='https://doi.org/10.5281/zenodo.19667567' "
    f"style='color:{ACCENT}; text-decoration:none;'>corpus DOI</a></div>",
    unsafe_allow_html=True,
)
