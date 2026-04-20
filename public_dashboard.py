"""Public dashboard — sanitised brand-facing view of HUNTER.

Shows live system activity WITHOUT leaking:
  - Specific tickers in open positions (shows count + direction only)
  - Exact hypothesis text for high-score diamonds (shows domain + score)
  - Pre-registration corpus hash (shows "locked" flag only)
  - API cost / budget
  - Source-type query strings

Designed to be deployed to a public URL (Streamlit Cloud / Hugging Face
Spaces / your own domain) so prospective advisors, fund people, and
academics can see the system is live and honest without you leaking edge.

Run:
    streamlit run public_dashboard.py
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

DB = Path(__file__).parent / "hunter.db"

st.set_page_config(page_title="HUNTER · public", layout="wide", page_icon="💎")

st.markdown("""
<style>
    .stApp { background: #0e1117; }
    h1 { color: #FFD700; font-size: 2.2em; }
    h2 { color: #ff8800; border-bottom: 1px solid #333; padding-bottom: 4px; }
    h3 { color: #FFD700; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)  # 5-min cache on public view to reduce load
def sql(q, params=()):
    conn = sqlite3.connect(DB)
    try:
        return pd.read_sql_query(q, conn, params=params)
    finally:
        conn.close()


@st.cache_data(ttl=300)
def sql_one(q, params=()):
    conn = sqlite3.connect(DB)
    try:
        row = conn.execute(q, params).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════
# Header
# ══════════════════════════════════════════════════════════════════════
st.title("HUNTER")
st.markdown(
    "*Autonomous fact-collision research engine. Detects compositional alpha across "
    "18 professional silos. Pre-registered 12-week empirical study, Summer 2026.*"
)
st.caption("Solo build · Dublin · by John Malpass · [GitHub] · [Contact]")

# ══════════════════════════════════════════════════════════════════════
# Live stats — what's safe to show
# ══════════════════════════════════════════════════════════════════════
st.header("System state")
cols = st.columns(6)
cols[0].metric("Facts indexed", f"{(sql_one('SELECT COUNT(*) FROM raw_facts') or 0):,}")
cols[1].metric("Entities resolved", f"{(sql_one('SELECT COUNT(*) FROM fact_entities') or 0):,}")
cols[2].metric("Cross-silo collisions", f"{(sql_one('SELECT COUNT(*) FROM collisions') or 0):,}")
cols[3].metric("Detected cycles", f"{(sql_one('SELECT COUNT(*) FROM detected_cycles') or 0):,}")
cols[4].metric("Surviving hypotheses", f"{(sql_one('SELECT COUNT(*) FROM hypotheses WHERE survived_kill=1') or 0):,}")
cols[5].metric("Theory evidence rows", f"{(sql_one('SELECT COUNT(*) FROM theory_evidence') or 0):,}")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════
# Pre-registration status
# ══════════════════════════════════════════════════════════════════════
st.header("Pre-registration")
manifest_path = Path(__file__).parent / "preregistration.json"
if manifest_path.exists():
    m = json.loads(manifest_path.read_text())
    c1, c2, c3 = st.columns(3)
    c1.metric("Study", "Summer 2026, 12 weeks")
    c2.metric("Corpus cutoff", m.get("corpus_cutoff", "—"))
    c3.metric("Status", "🔒 LOCKED")
    with st.expander("Primary hypothesis + decision rules"):
        st.write(m.get("primary_hypothesis", ""))
        st.markdown("**Decision rules**")
        st.write(m.get("decision_rules", {}))
else:
    st.warning("Pre-registration not yet locked.")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════
# Sanitised diamonds — show domain + score but NOT content
# ══════════════════════════════════════════════════════════════════════
st.header("Surviving diamonds (domain-anonymised)")
st.caption("Full text and assets withheld while study is active. Counts and domain categories only.")

diamonds = sql("""
    SELECT diamond_score, confidence,
           SUBSTR(c.source_types, 1, 100) as domains
    FROM hypotheses h
    LEFT JOIN collisions c ON c.id = h.collision_id
    WHERE h.survived_kill = 1 AND h.diamond_score >= 60
    ORDER BY diamond_score DESC LIMIT 20
""")
if not diamonds.empty:
    # Only show score buckets + anonymised domain pair counts
    diamonds["score_band"] = diamonds["diamond_score"].apply(
        lambda s: "90+" if s >= 90 else ("80-89" if s >= 80 else ("70-79" if s >= 70 else "60-69"))
    )
    # Extract first 3 source types from domains string without showing which specific hypothesis
    st.dataframe(
        diamonds.groupby("score_band").size().reset_index(name="count").rename(
            columns={"score_band": "Score band", "count": "Hypotheses"}),
        hide_index=True, use_container_width=True
    )
else:
    st.info("No diamonds yet.")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════
# Cycle topology — full public disclosure (the methodology IS the artifact)
# ══════════════════════════════════════════════════════════════════════
st.header("Detected epistemic cycles")
st.caption("These are the compositional structures. Cycle identities are public; trading positions are not.")

cycles = sql("""
    SELECT cycle_type, json_array_length(domains) as n_domains,
           reinforcement_strength,
           SUBSTR(domains, 1, 200) as domain_sample
    FROM detected_cycles
    ORDER BY reinforcement_strength DESC, n_domains DESC
""")
if not cycles.empty:
    st.dataframe(cycles, hide_index=True, use_container_width=True)
    st.caption(
        "Each cycle is a closed loop of causal influence through multiple "
        "professional silos. Framework predicts these are stable equilibria "
        "(reinforcement ≥ correction); persistence is being measured through summer 2026."
    )
else:
    st.info("No cycles detected yet.")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════
# Theory layers — high-level view
# ══════════════════════════════════════════════════════════════════════
st.header("Theory evidence")
st.caption("13 framework layers. Evidence accumulates over the study.")

layers = sql("""
    SELECT layer, evidence_type, COUNT(*) as n
    FROM theory_evidence
    GROUP BY layer, evidence_type
""")
if not layers.empty:
    pivot = layers.pivot_table(
        index="layer", columns="evidence_type", values="n", fill_value=0
    ).reset_index()
    pivot["layer"] = pivot["layer"].apply(lambda i: f"L{int(i):02d}")
    st.dataframe(pivot, hide_index=True, use_container_width=True)

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════
# Latest research diary entries (if author has made diary public)
# ══════════════════════════════════════════════════════════════════════
diary_path = Path(__file__).parent / "diary" / "weekly"
if diary_path.exists():
    st.header("Latest weekly rollup")
    weekly_files = sorted(diary_path.glob("*.md"), reverse=True)
    if weekly_files:
        latest = weekly_files[0]
        text = latest.read_text()
        # Only show first 80 lines for brevity
        lines = text.split("\n")[:80]
        st.markdown("\n".join(lines))

st.markdown("---")
st.caption(
    f"HUNTER public dashboard · last refreshed {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}. "
    "Data cached 5 minutes. System operates autonomously."
)
