"""Adversarial self-test — inject synthetic fake collisions to test the
kill phase's integrity.

If the kill phase is working, it should REJECT obviously-false collisions
at a high rate. If synthetic garbage gets through, the kill phase has
blind spots that need sharpening BEFORE a real adversarial operator
(a competitor running HUNTER against your output) exploits them.

Three types of synthetic collision injected:

 1. CAUSALLY INVERTED: dates swapped so B happens before A but the
    collision text claims A caused B. Should be killed by fact_check.

 2. ENTITY SUBSTITUTED: identical structure to a real surviving
    hypothesis but with a different ticker. Should be killed by
    competitor/barrier check OR caught as duplicate by thesis dedup.

 3. PURE NOISE: randomly-assembled facts with no mechanistic connection.
    Should be killed at the COLLISION_EVALUATE step before forming
    a hypothesis at all.

This module writes these as synthetic collisions, runs them through the
live kill phase, and reports the integrity rate.

WARNING: this module WILL cost API credits because it runs the real kill
phase. Only run before summer to calibrate. Not part of continuous ops.

Run:
    python adversarial_self_test.py simulate   # generate synthetics, no LLM
    python adversarial_self_test.py run N      # run N synthetics through kill phase
    python adversarial_self_test.py report     # show integrity stats from prior runs
"""

import json
import random
import sys
from datetime import datetime, timedelta

from database import get_connection


def _ensure_tables():
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS adversarial_test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_type TEXT,
                synthetic_thesis TEXT,
                synthetic_facts_json TEXT,
                kill_result TEXT,
                killed INTEGER,
                kill_type TEXT,
                kill_reason TEXT,
                integrity_pass INTEGER,
                ran_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════
# Synthetic generators
# ══════════════════════════════════════════════════════════════════════

def _generate_causally_inverted(n: int = 5) -> list:
    """Take real hypotheses with kill_attempts and invert the timing."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, hypothesis_text, fact_chain FROM hypotheses
            WHERE survived_kill = 1 LIMIT ?
        """, (n,)).fetchall()
    finally:
        conn.close()
    synthetics = []
    for hid, text, fc in rows:
        synthetics.append({
            "test_type": "causally_inverted",
            "origin_hypothesis_id": hid,
            "synthetic_thesis": (text or "")[:800] + " [NOTE: this synthetic INVERTS the timing — if HUNTER's kill catches temporal inversion, it should fail.]",
            "facts": fc,
            "expected_kill": True,
            "should_kill_reason": "timing_inversion_or_fact_wrong",
        })
    return synthetics


def _generate_entity_substituted(n: int = 5) -> list:
    """Replace the ticker or entity in a real surviving hypothesis with a
    random unrelated ticker."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, hypothesis_text, fact_chain FROM hypotheses
            WHERE survived_kill = 1 LIMIT ?
        """, (n,)).fetchall()
    finally:
        conn.close()

    random_tickers = ["KO", "DIS", "NKE", "MCD", "BA", "ROKU", "HOG", "F", "GM", "LUV"]
    synthetics = []
    for hid, text, fc in rows:
        fake = random.choice(random_tickers)
        synthetics.append({
            "test_type": "entity_substituted",
            "origin_hypothesis_id": hid,
            "synthetic_thesis": (text or "")[:800].replace("MET", fake).replace("PFE", fake).replace("CLF", fake) + f" [ENTITY SUBSTITUTED to {fake}]",
            "facts": fc,
            "expected_kill": True,
            "should_kill_reason": "dedup_or_competitor_or_substitution",
        })
    return synthetics


def _generate_pure_noise(n: int = 5) -> list:
    """Randomly pair facts from unrelated source types with no mechanism."""
    conn = get_connection()
    try:
        # Pick pairs of facts with mismatched source types and no shared entities
        rows = conn.execute("""
            SELECT id, title, raw_content, source_type FROM raw_facts
            ORDER BY RANDOM() LIMIT ?
        """, (n * 2,)).fetchall()
    finally:
        conn.close()

    synthetics = []
    for i in range(0, len(rows) - 1, 2):
        a = rows[i]
        b = rows[i + 1]
        synthetics.append({
            "test_type": "pure_noise",
            "synthetic_thesis": (
                f"Random pairing: '{a[1]}' (source: {a[3]}) combined with "
                f"'{b[1]}' (source: {b[3]}) implies a mispriced asset. "
                "No mechanism — pure noise."
            ),
            "facts": json.dumps([{"fact_id": a[0], "role": "side A"},
                                  {"fact_id": b[0], "role": "side B"}]),
            "expected_kill": True,
            "should_kill_reason": "no_mechanism",
        })
    return synthetics


# ══════════════════════════════════════════════════════════════════════
# Simulation — generate without running LLM
# ══════════════════════════════════════════════════════════════════════

def simulate(n_per_type: int = 5):
    _ensure_tables()
    synthetics = []
    synthetics.extend(_generate_causally_inverted(n_per_type))
    synthetics.extend(_generate_entity_substituted(n_per_type))
    synthetics.extend(_generate_pure_noise(n_per_type))
    print(f"\nGenerated {len(synthetics)} synthetic test cases (no LLM calls):")
    for s in synthetics[:10]:
        print(f"  [{s['test_type']}] {s['synthetic_thesis'][:100]}...")
    return synthetics


# ══════════════════════════════════════════════════════════════════════
# Real run — costs API credits
# ══════════════════════════════════════════════════════════════════════

def run(n_per_type: int = 3):
    """Run synthetic cases through the real kill phase. This costs API credits."""
    _ensure_tables()
    try:
        from hunter import call_kill_gate, extract_text_from_response, parse_json_response
    except ImportError:
        print("Cannot import kill_gate from hunter.py — is the main engine intact?")
        return

    synthetics = (
        _generate_causally_inverted(n_per_type) +
        _generate_entity_substituted(n_per_type) +
        _generate_pure_noise(n_per_type)
    )
    print(f"\nRunning {len(synthetics)} synthetic cases through kill phase...\n")

    from prompts import KILL_PROMPT
    conn = get_connection()
    passes = 0
    fails = 0
    try:
        for i, s in enumerate(synthetics, 1):
            print(f"  [{i}/{len(synthetics)}] {s['test_type']}...")
            try:
                prompt = KILL_PROMPT.format(
                    hypothesis_text=s["synthetic_thesis"][:2000],
                    fact_chain=s["facts"][:1500],
                )
                r = call_kill_gate(prompt, max_tokens=512)
                text = extract_text_from_response(r)
                data = parse_json_response(text)
                killed = bool(data.get("killed", False))
                kill_type = data.get("kill_type", "")
                reason = (data.get("reason") or data.get("kill_reason") or "")[:200]

                # Integrity pass: synthetic should have been killed
                integrity_pass = 1 if killed else 0
                if integrity_pass:
                    passes += 1
                else:
                    fails += 1

                conn.execute("""
                    INSERT INTO adversarial_test_results
                    (test_type, synthetic_thesis, synthetic_facts_json,
                     kill_result, killed, kill_type, kill_reason, integrity_pass)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (s["test_type"], s["synthetic_thesis"][:1000],
                      s["facts"], json.dumps(data)[:800],
                      killed, kill_type, reason, integrity_pass))
                conn.commit()
                status = "✓ KILLED" if killed else "✗ SURVIVED (integrity fail)"
                print(f"         {status}")
            except Exception as e:
                print(f"         [error] {e}")
                fails += 1
    finally:
        conn.close()

    integrity_rate = passes / max(1, passes + fails)
    print(f"\n{'=' * 60}")
    print(f"  Integrity test: {passes}/{passes+fails} synthetics correctly killed")
    print(f"  Integrity rate: {integrity_rate:.1%}")
    if integrity_rate < 0.85:
        print(f"  ⚠ LOW integrity. Kill phase has blind spots. Investigate survivors.")
    else:
        print(f"  ✓ Kill phase integrity is acceptable.")
    print(f"{'=' * 60}")


def report():
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT test_type,
                   COUNT(*) as n,
                   SUM(integrity_pass) as passed,
                   AVG(integrity_pass) as rate
            FROM adversarial_test_results
            GROUP BY test_type
        """).fetchall()
    finally:
        conn.close()
    print(f"\nAdversarial test history\n")
    print(f"{'Type':<24} {'n':>5} {'pass':>6} {'rate':>7}")
    print("-" * 50)
    for test_type, n, passed, rate in rows:
        print(f"{test_type:<24} {n:>5} {passed:>6} {rate:>6.1%}")


if __name__ == "__main__":
    _ensure_tables()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "simulate"

    if cmd == "simulate":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        simulate(n_per_type=n)

    elif cmd == "run":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        print(f"\n[WARNING] This will cost ~${n * 3 * 0.01:.2f} in API credits.")
        confirm = input("Proceed? (y/N): ")
        if confirm.lower().strip() == "y":
            run(n_per_type=n)
        else:
            print("Aborted.")

    elif cmd == "report":
        report()
    else:
        print(__doc__)
