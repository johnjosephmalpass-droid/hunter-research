#!/usr/bin/env python3
"""Backfill implications for existing facts that don't have them.

Run this ONCE to add implications to all existing facts in the database.
Uses Claude API to generate implications for each fact.
"""

import json
import os
import sys
import time

import anthropic
from dotenv import load_dotenv

from database import get_connection

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

BATCH_SIZE = 10  # Process 10 facts at a time to save API calls
MODEL = "claude-sonnet-4-20250514"


_backfill_processed = set()

def get_facts_needing_implications(limit=50):
    """Get facts with empty OR old shallow implications that need upgrading.

    No artificial id cap — works on current and future facts.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, raw_content, source_type, domain, entities
        FROM raw_facts
        WHERE NOT (implications LIKE '%If %' AND implications LIKE '%, then %' AND length(implications) > 300)
           OR implications IS NULL
           OR implications = ''
           OR implications = '[]'
        ORDER BY id
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_fact_implications(fact_id, implications):
    conn = get_connection()
    conn.execute(
        "UPDATE raw_facts SET implications = ? WHERE id = ?",
        (json.dumps(implications), fact_id)
    )
    conn.commit()
    conn.close()


def generate_implications_batch(facts):
    """Generate implications for a batch of facts in one API call."""
    facts_block = ""
    for f in facts:
        facts_block += f"\n[Fact #{f['id']}] ({f['source_type']}, {f.get('domain', 'unknown')})\n"
        facts_block += f"  Title: {f['title']}\n"
        facts_block += f"  Content: {(f.get('raw_content') or '')[:300]}\n"

    prompt = f"""For each fact below, generate 3-5 LATERAL COLLISION BRIDGES.

A lateral collision bridge is NOT a downstream consequence. It is an identification of which TWO PROFESSIONAL COMMUNITIES each hold one half of an insight and DON'T READ EACH OTHER'S PUBLICATIONS.

CRITICAL DISTINCTION:
WRONG (causal chain / consensus): "If oil rises to $102, then Delta Air Lines cancels flights" — every energy analyst and airline analyst already knows this. This is priced in before the headline prints.
WRONG (obvious downstream): "If bankruptcy filings increase, then restructuring law firms make more money" — every lawyer knows this.
WRONG (first-order): "If FDA approves drug, then biotech stock goes up" — every analyst models this.

RIGHT (lateral collision): "If oil rises to $102 (tracked by energy desks), then fertilizer input costs spike 35% (tracked by agriculture analysts), but CF Industries' natural gas-based production becomes relatively cheaper vs coal-based competitors — creating a margin advantage that neither energy analysts nor agriculture analysts would identify because energy desks don't model fertilizer production economics and agriculture analysts don't track relative feedstock cost structures"

RIGHT: "If CDER loses 385 staff (tracked by FDA policy analysts), then ANDA processing delays 6-12 months (tracked by pharma patent lawyers), extending monopoly pricing for companies with 40%+ revenue concentration on expiring drugs (tracked by equity analysts) — three communities each holding one piece, none seeing the full picture"

FORMAT: "If [fact], then [consequence that requires expertise from domain A] combined with [knowledge from domain B that domain A doesn't have], creating [specific insight neither community would independently identify]"

For each implication, you MUST answer: which two professional communities each hold half of this insight? If a single Bloomberg terminal operator would see the whole picture, it's NOT a collision bridge. Kill it.

FACTS:
{facts_block}

FACTS:
{facts_block}

Respond with ONLY a JSON object:
{{
    "implications": [
        {{"fact_id": <id>, "implications": ["implication1", "implication2", "implication3"]}},
        ...
    ]
}}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
        system="You are an analyst who sees second and third-order effects. For each fact, identify what it implies for domains OUTSIDE its own field."
    )

    text = ""
    for block in response.content:
        if block.type == "text":
            text += block.text

    # Parse JSON
    text = text.strip()
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        text = text[start:end].strip()

    # Try to find JSON object
    brace_start = text.find("{")
    brace_end = text.rfind("}") + 1
    if brace_start >= 0 and brace_end > brace_start:
        text = text[brace_start:brace_end]

    return json.loads(text)


def main():
    total_updated = 0

    # Count total remaining and total facts — dynamic, not hardcoded
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM raw_facts")
    total_facts = cursor.fetchone()[0]
    cursor.execute("""
        SELECT COUNT(*) FROM raw_facts
        WHERE NOT (implications LIKE '%If %' AND implications LIKE '%, then %' AND length(implications) > 300)
           OR implications IS NULL OR implications = '' OR implications = '[]'
    """)
    total_remaining = cursor.fetchone()[0]
    conn.close()

    already_done = total_facts - total_remaining
    print(f"Backfilling implications: {already_done} done / {total_facts} total ({total_remaining} remaining)")
    print()

    while True:
        facts = get_facts_needing_implications(limit=BATCH_SIZE)
        if not facts:
            print(f"\nDone! Updated {total_updated} facts total.")
            break

        print(f"  Processing batch of {len(facts)} facts (IDs {facts[0]['id']}-{facts[-1]['id']})...")

        try:
            result = generate_implications_batch(facts)
            implications_list = result.get("implications", [])

            for item in implications_list:
                fact_id = item.get("fact_id")
                imps = item.get("implications", [])
                if fact_id and imps:
                    update_fact_implications(int(fact_id), imps)
                    total_updated += 1

            # Mark all facts in this batch as processed
            for f in facts:
                _backfill_processed.add(f["id"])

            done_now = already_done + total_updated
            pct = (done_now / max(1, total_facts)) * 100
            print(f"  ✓ {done_now}/{total_facts} ({pct:.1f}%) -- updated {len(implications_list)} this batch")

        except anthropic.RateLimitError:
            print("  Rate limited, waiting 60s...")
            time.sleep(60)
            continue
        except json.JSONDecodeError as e:
            print(f"  JSON parse error: {e}, marking batch and moving on")
            for f in facts:
                _backfill_processed.add(f["id"])
        except Exception as e:
            print(f"  Error: {e}")
            if "credit balance" in str(e):
                print("  Credits exhausted. Run again when you have credits.")
                break
            time.sleep(5)
            continue

        # Rate limit pause
        time.sleep(2)

    print(f"\nBackfill complete. {total_updated} facts now have implications.")


if __name__ == "__main__":
    main()
