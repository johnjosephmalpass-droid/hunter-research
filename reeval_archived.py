#!/usr/bin/env python3
"""Re-evaluate archived hypotheses through the mechanism kill.

For each archived thesis:
1. Run the mechanism kill on each causal arrow
2. If an arrow breaks, try to find an alternative transmission pathway
3. If all arrows verified (or successfully rerouted), promote back to hypotheses with updated score
4. If arrows can't be fixed, leave in archive with notes about what broke
"""

import json
import os
import sqlite3

import anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def mechanism_test(hypothesis_text, fact_chain):
    """Test every causal arrow in the thesis. Returns which arrows pass and which break."""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        temperature=0.2,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        messages=[{"role": "user", "content": f"""Decompose this thesis into its causal chain and test EVERY arrow.

THESIS: {hypothesis_text[:800]}
FACTS: {json.dumps(fact_chain)[:600]}

For each causal link in the chain:
1. Name the arrow: "[Output A] transmits to [Input B] through [specific pathway]"
2. Search: does this transmission pathway actually exist?
3. Verdict: VERIFIED or BROKEN

If an arrow is BROKEN, also suggest: is there an ALTERNATIVE pathway that achieves the same transmission through a different mechanism?

Respond with ONLY JSON:
{{
    "arrows": [
        {{
            "from": "what produces the output",
            "to": "what receives the input",
            "claimed_pathway": "how it supposedly transmits",
            "verified": true/false,
            "evidence": "what you found",
            "alternative_pathway": "if broken, is there another route? null if verified or no alternative"
        }}
    ],
    "all_verified": true/false,
    "broken_count": 0,
    "fixable_count": 0,
    "summary": "one sentence assessment"
}}"""}],
        system="Test whether causal mechanisms actually exist. Search for the specific workflow, database, or regulatory process claimed. Be precise about what works and what doesn't.",
    )

    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text

    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1].strip()

    return json.loads(text)


def reroute_broken_arrow(hypothesis_text, broken_arrow):
    """Try to find ONE alternative pathway for a broken arrow. Must meet the same bar as the original."""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        temperature=0.2,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
        messages=[{"role": "user", "content": f"""A causal link in an investment thesis has a broken transmission pathway. Search for ONE specific alternative.

THESIS CONTEXT: {hypothesis_text[:400]}

BROKEN LINK:
From: {broken_arrow.get('from', '')}
To: {broken_arrow.get('to', '')}
Claimed pathway: {broken_arrow.get('claimed_pathway', '')}
Why it's broken: {broken_arrow.get('evidence', '')}

Search for a DIFFERENT pathway. The alternative must meet ALL THREE bars:

1. SPECIFICITY: Name the exact database, filing, regulatory process, or professional workflow where transmission occurs. "This affects that" = FAILS. "This data appears in NAIC Schedule D filings which feed RBC capital calculations" = PASSES.

2. VERIFIABILITY: The pathway must be confirmable through a single web search. If you can't find evidence that the pathway exists in published professional documentation, it FAILS.

3. NON-OBVIOUSNESS: The pathway must constitute an edge — it must cross a professional boundary that practitioners don't normally see across. "Oil prices affect hotel costs" = obvious, NOT an edge. "NYCECC compliance triggers reassessment of tax-exempt bond covenants under IRC Section 150(b)" = non-obvious, IS an edge.

If no pathway meets all three bars, respond with found_alternative: false. Do NOT force a connection. It is better to admit the chain is broken than to manufacture a plausible-sounding pathway.

Respond with ONLY JSON:
{{
    "found_alternative": true/false,
    "alternative_pathway": "the specific alternative (only if true)",
    "specificity_evidence": "the exact source confirming this pathway exists (only if true)",
    "why_non_obvious": "why this crosses a professional boundary most analysts wouldn't see (only if true)"
}}"""}],
        system="Find alternative causal pathways that are specific, verifiable, and non-obvious. Do NOT force connections. Admitting a chain is broken is the correct answer when no valid alternative exists.",
    )

    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text

    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1].strip()

    return json.loads(text)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Re-evaluate archived hypotheses")
    parser.add_argument("--min-score", type=int, default=50,
                        help="Minimum diamond_score to re-evaluate (default 50)")
    parser.add_argument("--since", type=str, default=None,
                        help="Only re-eval hypotheses created on/after YYYY-MM-DD. Default: no cutoff.")
    args = parser.parse_args()

    conn = sqlite3.connect("hunter.db")
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    if args.since:
        cursor.execute("""
            SELECT id, hypothesis_text, fact_chain, kill_attempts, diamond_score,
                   novelty, feasibility, timing, asymmetry, intersection, confidence,
                   action_steps, time_window_days, collision_id, full_report
            FROM hypotheses_archive
            WHERE diamond_score >= ?
            AND created_at >= ?
            ORDER BY diamond_score DESC
        """, (args.min_score, args.since))
    else:
        cursor.execute("""
            SELECT id, hypothesis_text, fact_chain, kill_attempts, diamond_score,
                   novelty, feasibility, timing, asymmetry, intersection, confidence,
                   action_steps, time_window_days, collision_id, full_report
            FROM hypotheses_archive
            WHERE diamond_score >= ?
            ORDER BY diamond_score DESC
        """, (args.min_score,))
    archived = [dict(r) for r in cursor.fetchall()]

    print(f"Re-evaluating {len(archived)} archived hypotheses through mechanism kill\n")

    promoted = 0
    broken_unfixable = 0
    rerouted = 0

    for h in archived:
        hid = h["id"]
        score = h["diamond_score"]
        thesis = h["hypothesis_text"]
        fact_chain = json.loads(h["fact_chain"] or "[]")

        print(f"\n{'='*60}")
        print(f"#{hid} | Score {score} | {thesis[:70]}")

        try:
            # Step 1: Test all mechanisms
            result = mechanism_test(thesis, fact_chain)
            arrows = result.get("arrows", [])
            broken = [a for a in arrows if not a.get("verified")]
            verified = [a for a in arrows if a.get("verified")]

            print(f"  Arrows: {len(verified)} verified, {len(broken)} broken")

            if not broken:
                # All arrows verified — promote back
                print(f"  ALL ARROWS VERIFIED — promoting back")

                # Add mechanism kill result to kill attempts
                kills = json.loads(h["kill_attempts"] or "[]")
                kills.append({
                    "round": "mechanism",
                    "killed": False,
                    "reason": f"All {len(arrows)} causal arrows verified. {result.get('summary', '')}",
                    "kill_type": "mechanism",
                })

                conn.execute("""
                    INSERT INTO hypotheses (collision_id, hypothesis_text, fact_chain, action_steps,
                        time_window_days, kill_attempts, survived_kill, diamond_score, novelty,
                        feasibility, timing, asymmetry, intersection, confidence, full_report)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (h["collision_id"], thesis, h["fact_chain"], h["action_steps"],
                      h["time_window_days"], json.dumps(kills), score,
                      h["novelty"], h["feasibility"], h["timing"], h["asymmetry"],
                      h["intersection"], h["confidence"], h["full_report"]))

                promoted += 1
                continue

            # Step 2: Try to reroute broken arrows (MAX 1 attempt per arrow, thesis dies if any arrow unfixable)
            all_fixed = True
            for broken_arrow in broken:
                print(f"  BROKEN: {broken_arrow.get('from', '')[:40]} -> {broken_arrow.get('to', '')[:40]}")
                print(f"    Claimed: {broken_arrow.get('claimed_pathway', '')[:60]}")
                print(f"    Evidence: {broken_arrow.get('evidence', '')[:60]}")

                # ONE attempt to find alternative — no infinite retries
                try:
                    reroute = reroute_broken_arrow(thesis, broken_arrow)
                    if reroute.get("found_alternative"):
                        alt_path = reroute.get("alternative_pathway", "")
                        specificity = reroute.get("specificity_evidence", "")
                        non_obvious = reroute.get("why_non_obvious", "")

                        # Validate the alternative meets the bar
                        if len(alt_path) > 20 and len(specificity) > 10:
                            print(f"    REROUTED: {alt_path[:60]}")
                            print(f"    Source: {specificity[:60]}")
                            rerouted += 1
                        else:
                            print(f"    Alternative too vague — treating as unfixable")
                            all_fixed = False
                    else:
                        print(f"    NO ALTERNATIVE — chain broken here")
                        all_fixed = False
                except Exception as e:
                    print(f"    Reroute failed: {str(e)[:40]}")
                    all_fixed = False

                # If ANY arrow is unfixable, the whole thesis dies — don't keep trying
                if not all_fixed:
                    print(f"  THESIS DIES — unfixable broken arrow")
                    break

            if all_fixed and broken:
                # All broken arrows were rerouted — promote with reduced score
                reduced_score = max(50, int(score * 0.8))
                print(f"  ALL ARROWS REROUTED — promoting at reduced score {reduced_score}")

                kills = json.loads(h["kill_attempts"] or "[]")
                kills.append({
                    "round": "mechanism",
                    "killed": False,
                    "reason": f"{len(broken)} arrows rerouted through alternative pathways. {result.get('summary', '')}",
                    "kill_type": "mechanism_rerouted",
                })

                conn.execute("""
                    INSERT INTO hypotheses (collision_id, hypothesis_text, fact_chain, action_steps,
                        time_window_days, kill_attempts, survived_kill, diamond_score, novelty,
                        feasibility, timing, asymmetry, intersection, confidence, full_report)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (h["collision_id"], thesis, h["fact_chain"], h["action_steps"],
                      h["time_window_days"], json.dumps(kills), reduced_score,
                      h["novelty"], h["feasibility"], h["timing"], h["asymmetry"],
                      h["intersection"], h["confidence"], h["full_report"]))

                promoted += 1
            else:
                print(f"  UNFIXABLE — stays in archive")
                broken_unfixable += 1

        except json.JSONDecodeError:
            print(f"  Parse error — skipping")
            broken_unfixable += 1
        except Exception as e:
            print(f"  Error: {str(e)[:60]}")
            broken_unfixable += 1

    conn.commit()
    conn.close()

    print(f"\n{'='*60}")
    print(f"RESULTS:")
    print(f"  Promoted (all arrows verified): {promoted}")
    print(f"  Rerouted (alternative pathways found): {rerouted}")
    print(f"  Unfixable (stays archived): {broken_unfixable}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
