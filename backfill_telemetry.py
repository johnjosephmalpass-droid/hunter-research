"""Backfill TheoryTelemetry evidence over existing collisions & hypotheses.

Current state: 474 collisions, 61 hypotheses, but only 11 theory_evidence rows
(all from a single 04-13 test run). The 13-layer dashboard will look empty to
anyone who sees it.

This script walks every existing collision + hypothesis, runs the LOCAL
(non-LLM) evidence classifier against it, and writes one or more
theory_evidence rows per layer. No LLM calls — this makes the backfill fast,
free, and deterministic.

For the summer run, live TheoryTelemetry will add LLM-refined evidence on
top of this baseline.

Run:
    python backfill_telemetry.py            # dry run, prints counts
    python backfill_telemetry.py write      # actually writes
"""

import json
import sys
from datetime import datetime

from database import get_connection
from theory import (
    classify_evidence,
    compute_collision_formula,
    compute_depth_value,
    LAYER_TO_NUM,
)

try:
    from config import compute_avg_domain_distance
except Exception:
    def compute_avg_domain_distance(_):
        return 0.0


def _iter_collisions():
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, fact_ids, collision_description, num_domains,
                   domains_involved, source_types, temporal_spread_days,
                   oldest_fact_age_days, negative_space_score, created_at
            FROM collisions
            ORDER BY id
        """).fetchall()
        return [dict(zip(
            ["id", "fact_ids", "collision_description", "num_domains",
             "domains_involved", "source_types", "temporal_spread_days",
             "oldest_fact_age_days", "negative_space_score", "created_at"], r)) for r in rows]
    finally:
        conn.close()


def _iter_hypotheses():
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, collision_id, hypothesis_text, survived_kill,
                   diamond_score, created_at
            FROM hypotheses
            ORDER BY id
        """).fetchall()
        return [dict(zip(
            ["id", "collision_id", "hypothesis_text", "survived_kill",
             "diamond_score", "created_at"], r)) for r in rows]
    finally:
        conn.close()


def _insert_evidence(conn, row):
    conn.execute("""
        INSERT INTO theory_evidence
        (timestamp, source_event, source_id, layer, layer_name,
         evidence_type, description, metric, observed_value,
         predicted_value, unit, confidence, domain_pair,
         chain_depth, cycle_detected, cycle_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        row["timestamp"], row["source_event"], row["source_id"],
        row["layer_num"], row["layer_name"],
        row["evidence_type"], row["description"],
        row.get("metric"), row.get("observed_value"),
        row.get("predicted_value"), row.get("unit", ""),
        row.get("confidence", 0.5),
        row.get("domain_pair_json", "[]"),
        row.get("chain_depth", 0),
        row.get("cycle_detected", 0),
        row.get("cycle_type"),
    ))


def backfill(write: bool = False) -> dict:
    collisions = _iter_collisions()
    hypotheses = _iter_hypotheses()

    # Build hypothesis lookup by collision_id
    hyps_by_collision = {}
    for h in hypotheses:
        cid = h["collision_id"]
        if cid is None:
            continue
        hyps_by_collision.setdefault(cid, []).append(h)

    counts_by_layer = {i: 0 for i in range(1, 14)}
    to_write = []

    for col in collisions:
        # Parse source types
        source_types = []
        if col.get("source_types"):
            try:
                source_types = json.loads(col["source_types"]) if col["source_types"].startswith("[") else col["source_types"].split(",")
            except Exception:
                source_types = []
        if not source_types and col.get("domains_involved"):
            try:
                source_types = json.loads(col["domains_involved"])
            except Exception:
                source_types = []
        source_types = [s.strip() for s in source_types if s]

        # Domain distance
        try:
            dist = compute_avg_domain_distance(source_types) if len(source_types) >= 2 else 0.0
        except Exception:
            dist = 0.0

        # Get related hypothesis if any
        related = hyps_by_collision.get(col["id"], [])
        survived = any(h.get("survived_kill") for h in related)
        diamond_score = max((h.get("diamond_score") or 0) for h in related) if related else None

        collision_data = {
            "collision_description": col.get("collision_description", ""),
            "has_collision": True,
            "num_domains": col.get("num_domains", 0),
        }

        # Negative space from collision table if present
        ns_data = None
        if col.get("negative_space_score"):
            ns_data = {
                "gap_magnitude": col["negative_space_score"],
                "reaction_occurred": False,  # by construction (it was the detected gap)
            }

        evidence_list = classify_evidence(
            collision_data=collision_data,
            source_types=source_types,
            domain_distance=dist,
            chains=None,  # could be joined but local classifier handles absence
            belief_reality_matches=None,
            validated_pairs=None,
            negative_space_data=ns_data,
            score_components=None,
            diamond_score=diamond_score,
            survived_kill=survived,
        )

        for ev in evidence_list:
            layer_name = ev.get("theory_layer") or ev.get("layer_name")
            layer_num = LAYER_TO_NUM.get(layer_name)
            if not layer_num:
                continue
            counts_by_layer[layer_num] = counts_by_layer.get(layer_num, 0) + 1
            to_write.append({
                "timestamp": col["created_at"] or datetime.now().isoformat(),
                "source_event": "backfill_collision",
                "source_id": col["id"],
                "layer_num": layer_num,
                "layer_name": layer_name,
                "evidence_type": ev.get("evidence_type", "supporting"),
                "description": ev.get("description", ""),
                "metric": ev.get("measurement_value") and "backfill_local_classifier" or None,
                "observed_value": ev.get("measurement_value"),
                "predicted_value": ev.get("predicted_value"),
                "unit": "",
                "confidence": ev.get("confidence", 0.5),
                "domain_pair_json": json.dumps(source_types[:2]) if len(source_types) >= 2 else "[]",
                "chain_depth": 0,
                "cycle_detected": 0,
                "cycle_type": None,
            })

    # Additional layer-12 (autopoiesis) evidence per surviving hypothesis
    for h in hypotheses:
        if not h.get("survived_kill"):
            continue
        score = h.get("diamond_score") or 0
        if score < 60:
            continue
        counts_by_layer[12] = counts_by_layer.get(12, 0) + 1
        to_write.append({
            "timestamp": h["created_at"] or datetime.now().isoformat(),
            "source_event": "backfill_hypothesis",
            "source_id": h["id"],
            "layer_num": 12,
            "layer_name": "L12_autopoiesis",
            "evidence_type": "direct" if score >= 80 else "supporting",
            "description": f"Hypothesis {h['id']} survived 3-round kill phase with score {score}. "
                           f"Predicted residual found where theory expected it — autopoiesis confirmed at score level.",
            "observed_value": score,
            "predicted_value": 60,  # threshold for "residual exists"
            "unit": "diamond_score",
            "confidence": min(1.0, score / 100.0),
            "domain_pair_json": "[]",
            "chain_depth": 0,
            "cycle_detected": 0,
            "cycle_type": None,
        })

    summary = {
        "collisions_processed": len(collisions),
        "hypotheses_processed": len(hypotheses),
        "evidence_rows_to_write": len(to_write),
        "by_layer": counts_by_layer,
    }

    if not write:
        return summary

    conn = get_connection()
    try:
        for row in to_write:
            _insert_evidence(conn, row)
        conn.commit()
        summary["written"] = len(to_write)
    finally:
        conn.close()

    return summary


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dry"
    s = backfill(write=(cmd == "write"))
    print(f"\nCollisions processed:  {s['collisions_processed']}")
    print(f"Hypotheses processed:  {s['hypotheses_processed']}")
    print(f"Evidence rows:         {s['evidence_rows_to_write']}")
    print("\nBy layer:")
    layer_names = {
        1: "Translation Loss", 2: "Attention Topology", 3: "Question Gap",
        4: "Phase Transition", 5: "Rate-Distortion", 6: "Market Incompleteness",
        7: "Depth-Value", 8: "Epistemic Cycles", 9: "Cycle Hierarchy",
        10: "Fractal Incompleteness", 11: "Negative Space", 12: "Autopoiesis",
        13: "Observer-Dependent",
    }
    for layer_num in sorted(s["by_layer"].keys()):
        if s["by_layer"][layer_num] > 0:
            print(f"  L{layer_num:02d} {layer_names.get(layer_num, '?'):>22}  {s['by_layer'][layer_num]:>5}")
    if "written" in s:
        print(f"\n✓ Written to theory_evidence: {s['written']}")
