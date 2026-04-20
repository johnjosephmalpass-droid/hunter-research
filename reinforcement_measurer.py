"""Replace hand-guessed reinforcement / correction rates with measured ones.

The theoretical parameters in theory.DOMAIN_THEORY_PARAMS (reinforcement,
correction) are educated guesses. This module measures them empirically.

Definitions used:
  reinforcement(domain): the fraction of facts in that source_type whose core
    entity-and-implication set is substantially shared with an EARLIER fact
    in the same source_type. High → echo chamber.
  correction(domain): the fraction of facts that explicitly contain
    correction markers (retraction, revision, update, amendment,
    recall, contradicted, reversed, discontinued, withdrawn, restated).

Both are normalised to 0..1 per domain. Results are stored in a
measured_domain_params table and printed as a delta vs. the hand-coded
values in theory.py.

Run:
    python reinforcement_measurer.py
    python reinforcement_measurer.py write
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime

from database import get_connection
from theory import DOMAIN_THEORY_PARAMS

CORRECTION_RX = re.compile(
    r"\b(retracted|retraction|revised|revision|updated|update|amended|"
    r"amendment|recall|recalled|contradicted|contradicts|reversed|reversal|"
    r"discontinued|withdrawn|withdrawal|restated|restatement|"
    r"correction|corrected|errata|erratum|nullified|voided|rescinded|"
    r"overturned|quashed|disproved|disputes)\b",
    re.IGNORECASE,
)


def _entity_set(conn, fact_id):
    rows = conn.execute(
        "SELECT entity_name_lower FROM fact_entities WHERE raw_fact_id = ?",
        (fact_id,),
    ).fetchall()
    return {r[0] for r in rows if r[0]}


def _implication_bigrams(implications_json):
    if not implications_json:
        return set()
    try:
        imps = json.loads(implications_json)
    except Exception:
        return set()
    if not isinstance(imps, list):
        return set()
    bgs = set()
    stop = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "by", "with"}
    for imp in imps:
        if not isinstance(imp, str):
            continue
        words = [w.lower() for w in re.findall(r"[A-Za-z]+", imp) if w.lower() not in stop]
        for i in range(len(words) - 1):
            bgs.add(words[i] + " " + words[i + 1])
    return bgs


def measure(write: bool = False) -> dict:
    conn = get_connection()
    try:
        conn.row_factory = None
        rows = conn.execute("""
            SELECT id, source_type, title, raw_content, implications, ingested_at
            FROM raw_facts
            WHERE source_type IS NOT NULL
            ORDER BY source_type, ingested_at
        """).fetchall()

        # Group facts by source_type
        by_source = defaultdict(list)
        for r in rows:
            fid, st, title, content, imps, ingested = r
            by_source[st].append({
                "id": fid, "title": title or "", "content": content or "",
                "imps": imps, "ingested_at": ingested,
            })

        # Per-source measurements
        results = {}
        for source_type, facts in by_source.items():
            if len(facts) < 10:
                continue  # skip underpopulated domains
            # Build entity + bigram sets for each fact
            per_fact = []
            for f in facts:
                ents = _entity_set(conn, f["id"])
                bgs = _implication_bigrams(f["imps"])
                per_fact.append({**f, "entities": ents, "bigrams": bgs})

            # Reinforcement: for each fact after the 10th, does it share >= 50%
            # entities OR >= 3 implication bigrams with any earlier same-source fact?
            reinforced = 0
            total = 0
            for i, f in enumerate(per_fact):
                if i < 10:
                    continue
                total += 1
                matched = False
                # Look back up to 100 earlier facts for efficiency
                lookback = per_fact[max(0, i - 100): i]
                for g in lookback:
                    if not f["entities"] and not f["bigrams"]:
                        break
                    ent_overlap = 0
                    if f["entities"] and g["entities"]:
                        inter = f["entities"] & g["entities"]
                        ent_overlap = len(inter) / max(1, len(f["entities"]))
                    big_overlap = 0
                    if f["bigrams"] and g["bigrams"]:
                        big_overlap = len(f["bigrams"] & g["bigrams"])
                    if ent_overlap >= 0.5 or big_overlap >= 3:
                        matched = True
                        break
                if matched:
                    reinforced += 1

            reinf_rate = reinforced / total if total > 0 else 0.0

            # Correction: fraction of facts whose content matches CORRECTION_RX
            corrections = sum(
                1 for f in facts
                if CORRECTION_RX.search((f["title"] + " " + f["content"])[:2000])
            )
            corr_rate = corrections / len(facts)

            predicted = DOMAIN_THEORY_PARAMS.get(source_type, {})
            results[source_type] = {
                "n_facts": len(facts),
                "reinforcement_measured": round(reinf_rate, 4),
                "reinforcement_predicted": predicted.get("reinforcement"),
                "reinforcement_delta": round(
                    reinf_rate - (predicted.get("reinforcement") or 0), 4
                ),
                "correction_measured": round(corr_rate, 4),
                "correction_predicted": predicted.get("correction"),
                "correction_delta": round(
                    corr_rate - (predicted.get("correction") or 0), 4
                ),
                "persistence_ratio_measured": (
                    round(reinf_rate / max(0.001, corr_rate), 2)
                ),
            }

        if write:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS measured_domain_params (
                    source_type TEXT PRIMARY KEY,
                    reinforcement_measured REAL,
                    correction_measured REAL,
                    persistence_ratio_measured REAL,
                    n_facts INTEGER,
                    measured_at TEXT
                )
            """)
            now = datetime.now().isoformat()
            for st, r in results.items():
                conn.execute("""
                    INSERT OR REPLACE INTO measured_domain_params
                    (source_type, reinforcement_measured, correction_measured,
                     persistence_ratio_measured, n_facts, measured_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (st, r["reinforcement_measured"], r["correction_measured"],
                      r["persistence_ratio_measured"], r["n_facts"], now))
            conn.commit()
    finally:
        conn.close()

    return results


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dry"
    r = measure(write=(cmd == "write"))
    print(f"\n{'Source type':<22} {'n':>5} "
          f"{'reinf_meas':>10} {'reinf_pred':>10} {'Δ':>7} "
          f"{'corr_meas':>10} {'corr_pred':>10} {'Δ':>7} "
          f"{'persist_ratio':>14}")
    print("-" * 120)
    for st in sorted(r.keys()):
        d = r[st]
        rp = d["reinforcement_predicted"] if d["reinforcement_predicted"] is not None else 0
        cp = d["correction_predicted"] if d["correction_predicted"] is not None else 0
        print(f"{st:<22} {d['n_facts']:>5} "
              f"{d['reinforcement_measured']:>10.3f} {rp:>10.3f} {d['reinforcement_delta']:>+7.3f} "
              f"{d['correction_measured']:>10.3f} {cp:>10.3f} {d['correction_delta']:>+7.3f} "
              f"{d['persistence_ratio_measured']:>14.1f}")

    print("\nInterpretation:")
    print("  persist_ratio = reinforcement / correction.")
    print("  Framework predicts 207x aggregate. Per-domain rates will differ.")
    print("  Large +Δ on reinforcement = echo chamber, formula underestimates")
    print("  Large -Δ = domain self-corrects faster than assumed (fewer residual)")
    if cmd == "write":
        print("\n✓ Measured values written to measured_domain_params table")
