"""Phase transition detector — flags domains accumulating residual fast.

Framework Layer 4 predicts that residual accumulation past a threshold
triggers sudden corrections. Analog: pressure building → earthquake.

Testable operationalisation:
  residual_accumulation_rate(domain, window_days) =
     (new_anomalies + new_survived_hypotheses - new_kill_found) / window_days

Sudden phase-transition risk is HIGH when:
  - rate is > 2 standard deviations above its own 90-day mean
  - correction events in the last 30 days are ≤ 0
  - multiple adjacent domains show the same signature (correlated risk)

This is not prediction of a specific event. It's a compressed-spring signal:
where and when the tension is highest. A portfolio risk manager would use
this to size down exposure to domains with high phase-transition risk.

Run:
    python phase_transition_detector.py
    python phase_transition_detector.py write
"""

import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, stdev

from database import get_connection


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d")
    except Exception:
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None


def detect(write: bool = False, window_days: int = 30, history_days: int = 180) -> dict:
    conn = get_connection()
    now = datetime.now()
    history_start = now - timedelta(days=history_days)
    try:
        # Per-domain time-series of new anomalies
        anomalies = conn.execute("""
            SELECT a.id, f.source_type, COALESCE(f.date_of_fact, f.ingested_at) as d
            FROM anomalies a
            JOIN raw_facts f ON f.id = a.raw_fact_id
        """).fetchall()

        # Per-domain survived hypotheses (proxy: residual accumulation)
        survived = conn.execute("""
            SELECT h.id, c.source_types, h.created_at
            FROM hypotheses h
            JOIN collisions c ON c.id = h.collision_id
            WHERE h.survived_kill = 1
        """).fetchall()

        # Per-domain kill_found events (proxy: correction applied)
        all_hyps = conn.execute("""
            SELECT h.id, c.source_types, h.kill_attempts, h.created_at
            FROM hypotheses h
            JOIN collisions c ON c.id = h.collision_id
        """).fetchall()
    finally:
        conn.close()

    # Build per-domain daily counts
    by_domain_anom = defaultdict(list)   # source_type → list of dates
    for aid, st, d in anomalies:
        dt = _parse_date(d)
        if dt and st:
            by_domain_anom[st].append(dt)

    by_domain_survived = defaultdict(list)
    for hid, st_json, created in survived:
        dt = _parse_date(created)
        if not dt or not st_json:
            continue
        try:
            types = json.loads(st_json) if st_json.startswith("[") else st_json.split(",")
        except Exception:
            types = []
        for st in types:
            by_domain_survived[st.strip()].append(dt)

    by_domain_kills = defaultdict(list)
    for hid, st_json, ka_json, created in all_hyps:
        dt = _parse_date(created)
        if not dt or not st_json:
            continue
        try:
            attempts = json.loads(ka_json) if ka_json else []
        except Exception:
            attempts = []
        found_kill = any(
            (a.get("killed") and (a.get("confidence") or "").lower() in ("strong", "moderate"))
            for a in attempts if isinstance(a, dict)
        )
        if not found_kill:
            continue
        try:
            types = json.loads(st_json) if st_json.startswith("[") else st_json.split(",")
        except Exception:
            types = []
        for st in types:
            by_domain_kills[st.strip()].append(dt)

    # For each domain, compute rolling residual accumulation rate
    window_results = []
    all_domains = set(by_domain_anom) | set(by_domain_survived)
    for dom in sorted(all_domains):
        anoms = sorted(by_domain_anom.get(dom, []))
        surv = sorted(by_domain_survived.get(dom, []))
        kills = sorted(by_domain_kills.get(dom, []))
        if len(anoms) + len(surv) < 10:
            continue
        # Build rate series across history_days in window_days buckets
        buckets = []
        bucket_start = history_start
        while bucket_start + timedelta(days=window_days) <= now:
            b_end = bucket_start + timedelta(days=window_days)
            a_count = sum(1 for d in anoms if bucket_start <= d < b_end)
            s_count = sum(1 for d in surv if bucket_start <= d < b_end)
            k_count = sum(1 for d in kills if bucket_start <= d < b_end)
            residual_rate = (a_count + s_count - k_count) / window_days
            buckets.append({
                "start": bucket_start.strftime("%Y-%m-%d"),
                "end": b_end.strftime("%Y-%m-%d"),
                "anomalies": a_count,
                "survived": s_count,
                "kills_found": k_count,
                "residual_rate": round(residual_rate, 4),
            })
            bucket_start = bucket_start + timedelta(days=window_days)

        rates = [b["residual_rate"] for b in buckets]
        if len(rates) < 3:
            continue
        mean_rate = mean(rates)
        std_rate = stdev(rates) if len(rates) > 1 else 0.0
        latest = rates[-1]
        z_score = (latest - mean_rate) / std_rate if std_rate > 0 else 0.0
        # Correction dryspell: bucketed kills in most recent window
        recent_kills = buckets[-1]["kills_found"] if buckets else 0

        # Phase transition risk: high z-score + zero recent corrections
        risk = 0.0
        if z_score >= 2.0:
            risk = 1.0
        elif z_score >= 1.0:
            risk = 0.5
        if recent_kills == 0 and latest > 0:
            risk += 0.3
        risk = min(1.0, risk)

        window_results.append({
            "domain": dom,
            "latest_rate": round(latest, 4),
            "mean_rate_180d": round(mean_rate, 4),
            "std_rate_180d": round(std_rate, 4),
            "z_score_latest": round(z_score, 2),
            "recent_corrections": recent_kills,
            "phase_transition_risk": round(risk, 3),
            "buckets": buckets[-6:],  # last 6 windows for dashboard
        })

    window_results.sort(key=lambda r: -r["phase_transition_risk"])

    summary = {
        "window_days": window_days,
        "history_days": history_days,
        "n_domains_analysed": len(window_results),
        "top_risk_domains": window_results[:10],
    }

    if write:
        conn = get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS phase_transition_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT, latest_rate REAL,
                    mean_rate_180d REAL, std_rate_180d REAL,
                    z_score_latest REAL, recent_corrections INTEGER,
                    phase_transition_risk REAL,
                    measured_at TEXT
                )
            """)
            now_iso = datetime.now().isoformat()
            for r in window_results:
                conn.execute("""
                    INSERT INTO phase_transition_signals
                    (domain, latest_rate, mean_rate_180d, std_rate_180d,
                     z_score_latest, recent_corrections, phase_transition_risk,
                     measured_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (r["domain"], r["latest_rate"], r["mean_rate_180d"],
                      r["std_rate_180d"], r["z_score_latest"],
                      r["recent_corrections"], r["phase_transition_risk"], now_iso))
            conn.commit()
        finally:
            conn.close()
    return summary


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dry"
    s = detect(write=(cmd == "write"))
    print(f"\nPHASE-TRANSITION DETECTION")
    print("=" * 75)
    print(f"Window:  {s['window_days']} days")
    print(f"History: {s['history_days']} days")
    print(f"Domains analysed: {s['n_domains_analysed']}")
    print()
    print(f"{'Domain':<22} {'latest':>8} {'mean':>8} {'z':>6} "
          f"{'kills':>6} {'risk':>6}")
    print("-" * 75)
    for r in s["top_risk_domains"]:
        print(f"{r['domain']:<22} {r['latest_rate']:>8.3f} "
              f"{r['mean_rate_180d']:>8.3f} {r['z_score_latest']:>+6.1f} "
              f"{r['recent_corrections']:>6} {r['phase_transition_risk']:>6.2f}")
    if cmd == "write":
        print("\n✓ Written to phase_transition_signals table")
