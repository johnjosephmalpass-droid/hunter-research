#!/usr/bin/env python3
"""Run Edge Recovery on all 45-scored hypotheses."""

import json
import os
import sqlite3

import anthropic
from dotenv import load_dotenv

load_dotenv(override=True)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

conn = sqlite3.connect("hunter.db")
conn.row_factory = sqlite3.Row

# Dynamic — find every hypothesis capped at 45 (market awareness cap)
# or with a market_check kill that hasn't had edge recovery attempted yet.
ids_rows = conn.execute("""
    SELECT id FROM hypotheses
    WHERE diamond_score = 45
       OR (survived_kill = 1 AND kill_attempts LIKE '%"kill_type":"market_check"%'
           AND kill_attempts NOT LIKE '%"kill_type":"edge_recovery"%')
    ORDER BY diamond_score DESC
""").fetchall()
ids = [r["id"] for r in ids_rows]
print(f"Found {len(ids)} hypotheses needing edge recovery.\n")

for hid in ids:
    row = conn.execute("SELECT * FROM hypotheses WHERE id = ?", (hid,)).fetchone()
    if not row:
        continue
    h = dict(row)
    raw = (h["novelty"] or 0) + (h["feasibility"] or 0) + (h["timing"] or 0) + (h["asymmetry"] or 0) + (h["intersection"] or 0)

    kills = json.loads(h["kill_attempts"] or "[]")
    market = [k for k in kills if k.get("kill_type") == "market_check"]
    if not market:
        continue
    pub = market[0].get("reason", "")

    # Skip if already has edge recovery
    if any(k.get("kill_type") == "edge_recovery" for k in kills):
        print(f"#{hid} | Already has edge recovery, skipping")
        continue

    print(f"\n#{hid} | Raw {raw} | {h['hypothesis_text'][:70]}")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            temperature=0.2,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
            messages=[{
                "role": "user",
                "content": (
                    f"Thesis: {h['hypothesis_text'][:500]}\n"
                    f"What's already known: {pub[:300]}\n\n"
                    "Is there a SPECIFIC sub-element (quantification, mechanism, chain link, "
                    "trade structure) that is NOT in published research?\n\n"
                    'Respond with ONLY JSON:\n'
                    '{"has_novel": true/false, "novel": "what specifically", "reframed": "thesis reframed"}'
                ),
            }],
            system="Check if specific sub-elements of an investment thesis are novel even though the broad category is known. Be precise. Respond with JSON only.",
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

        data = json.loads(text)

        if data.get("has_novel"):
            novel = data.get("novel", "")
            reframed = data.get("reframed", "")
            recovered = max(50, int(raw * 0.75))

            conn.execute("UPDATE hypotheses SET diamond_score = ? WHERE id = ?", (recovered, hid))
            kills.append({
                "round": "edge_recovery",
                "killed": False,
                "reason": f"Novel: {novel[:200]}. Reframed: {reframed[:200]}",
                "kill_type": "edge_recovery",
            })
            conn.execute("UPDATE hypotheses SET kill_attempts = ? WHERE id = ?", (json.dumps(kills), hid))
            # Also write to edge_recovery_events for proper telemetry
            try:
                conn.execute("""
                    INSERT INTO edge_recovery_events
                    (hypothesis_id, original_thesis_text, killed_at_score,
                     recovered_thesis_text, delta_score, recovery_attempted_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (hid, h["hypothesis_text"], 45, reframed, recovered - 45,
                      __import__("datetime").datetime.now().isoformat()))
            except Exception:
                pass
            print(f"  RECOVERED -> {recovered} | {novel[:70]}")
        else:
            print(f"  No novel element. Stays at 45.")

    except json.JSONDecodeError:
        print(f"  Parse error, skipping")
    except Exception as e:
        print(f"  Error: {str(e)[:80]}")

conn.commit()
conn.close()
print("\nDone.")
