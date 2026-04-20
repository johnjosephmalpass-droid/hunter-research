"""Expiration stack — the temporal collision surface.

Current HUNTER: collisions in space (domain × domain).
This module: collisions in TIME. Every patent, regulation, contract,
license, and court decision with a known expiration date is an event on
a cross-domain calendar. Assets exposed to multiple expirations converging
in the same window are the temporal equivalent of cross-silo collisions.

Method:
 1. Scan raw_facts for dated events with explicit expiration / effective
    dates (patent expiry, regulation effective, contract renewal, license
    renewal, sunset provision, court ruling deadline, FDA PDUFA dates).
 2. Extract the expiration date + affected entity + domain.
 3. Build a calendar.
 4. Query: "what crosses on date D ± 30 days?"
 5. Emit cross-time collision = 2+ expirations in same window affecting
    overlapping entities or sectors.

Run:
    python expiration_tracker.py scan           # scan corpus for expirations
    python expiration_tracker.py calendar       # print the next 90 days
    python expiration_tracker.py collide        # find date-clustered expirations
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from database import get_connection


EXPIRATION_PATTERNS = [
    (r"\bpatent (?:US|EP|WO)?\s*[\d,]+\s*expires?\s*(?:on\s*)?([A-Z][a-z]+\s+\d{1,2},?\s*20\d{2}|\d{4}-\d{2}-\d{2})", "patent_expiry"),
    (r"\bexpires?\s*(?:on\s*)?([A-Z][a-z]+\s+\d{1,2},?\s*20\d{2}|\d{4}-\d{2}-\d{2})", "generic_expiry"),
    (r"\beffective\s*(?:on\s*)?([A-Z][a-z]+\s+\d{1,2},?\s*20\d{2}|\d{4}-\d{2}-\d{2})", "regulation_effective"),
    (r"\b(?:sunset|sunsets|sunsetting)\s*(?:on\s*)?([A-Z][a-z]+\s+\d{1,2},?\s*20\d{2}|\d{4}-\d{2}-\d{2})", "sunset"),
    (r"\b(?:PDUFA|goal)\s*date\s*(?:of\s*)?([A-Z][a-z]+\s+\d{1,2},?\s*20\d{2}|\d{4}-\d{2}-\d{2})", "pdufa_deadline"),
    (r"\bby\s+(?:the end of\s+)?(Q[1-4]\s+20\d{2})", "quarterly_deadline"),
    (r"\b(?:expire|expiring|deadline|renewal|renews?)\s*(?:by|on)?\s*([A-Z][a-z]+\s+\d{1,2},?\s*20\d{2}|\d{4}-\d{2}-\d{2})", "renewal_deadline"),
]


def _ensure_tables():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS expirations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_fact_id INTEGER REFERENCES raw_facts(id),
                expiration_date TEXT NOT NULL,
                expiration_type TEXT,
                description TEXT,
                affected_entity TEXT,
                domain TEXT,
                extracted_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_expirations_date ON expirations(expiration_date);
            CREATE INDEX IF NOT EXISTS idx_expirations_domain ON expirations(domain);
        """)
        conn.commit()
    finally:
        conn.close()


def _normalise_date(raw: str) -> str:
    """Try to convert various date string formats to YYYY-MM-DD."""
    raw = raw.strip().rstrip(",")
    # Already ISO
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    # "Q1 2026" etc.
    m = re.match(r"Q([1-4])\s+(20\d{2})", raw)
    if m:
        q, y = m.groups()
        month_map = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}
        return f"{y}-{month_map[q]}"
    # Month Day, Year
    for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return ""


def scan_corpus(limit: int = 0) -> int:
    _ensure_tables()
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, title, raw_content, domain, source_type, entities
            FROM raw_facts
        """).fetchall()
    finally:
        conn.close()

    if limit:
        rows = rows[:limit]

    count = 0
    conn = get_connection()
    try:
        for fid, title, content, domain, source_type, entities_json in rows:
            text = ((title or "") + " " + (content or ""))[:3000]
            try:
                entities = json.loads(entities_json or "[]")
            except json.JSONDecodeError:
                entities = []
            affected = entities[0] if entities else None

            for pattern, etype in EXPIRATION_PATTERNS:
                for m in re.finditer(pattern, text, re.IGNORECASE):
                    raw_date = m.group(1) if m.lastindex else m.group(0)
                    norm = _normalise_date(raw_date)
                    if not norm:
                        continue
                    # Only keep future-ish dates (within ±3 years of today)
                    try:
                        d = datetime.strptime(norm, "%Y-%m-%d")
                        delta = (d - datetime.now()).days
                        if delta < -365 or delta > 3 * 365:
                            continue
                    except Exception:
                        continue
                    conn.execute("""
                        INSERT INTO expirations
                        (source_fact_id, expiration_date, expiration_type,
                         description, affected_entity, domain)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (fid, norm, etype, (title or "")[:200],
                          (affected or "")[:120], source_type or domain))
                    count += 1
        conn.commit()
    finally:
        conn.close()
    return count


def calendar_next_days(days: int = 90) -> list:
    conn = get_connection()
    try:
        end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        rows = conn.execute("""
            SELECT expiration_date, expiration_type, description, affected_entity, domain
            FROM expirations
            WHERE expiration_date BETWEEN ? AND ?
            ORDER BY expiration_date
        """, (today, end)).fetchall()
    finally:
        conn.close()
    return [dict(zip(["date", "type", "description", "entity", "domain"], r)) for r in rows]


def find_collisions(window_days: int = 30) -> list:
    """Find date-clusters: 2+ expirations within `window_days` days affecting
    entities that share domain OR entity overlap."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT expiration_date, expiration_type, description, affected_entity, domain, source_fact_id
            FROM expirations ORDER BY expiration_date
        """).fetchall()
    finally:
        conn.close()

    # Bucket by sliding window
    events = [dict(zip(["date", "type", "description", "entity", "domain", "fact_id"], r)) for r in rows]
    collisions = []
    for i, a in enumerate(events):
        for j in range(i + 1, min(i + 30, len(events))):
            b = events[j]
            try:
                da = datetime.strptime(a["date"], "%Y-%m-%d")
                db_ = datetime.strptime(b["date"], "%Y-%m-%d")
                delta = abs((db_ - da).days)
            except Exception:
                continue
            if delta > window_days:
                break
            shared = False
            if a.get("domain") and a.get("domain") == b.get("domain") and a["domain"] != b["domain"]:
                shared = True
            if a.get("entity") and b.get("entity") and a["entity"].lower() in b["entity"].lower():
                shared = True
            if shared or (a.get("domain") != b.get("domain") and a.get("domain") and b.get("domain")):
                collisions.append({
                    "event_a": a,
                    "event_b": b,
                    "days_apart": delta,
                    "cross_domain": a.get("domain") != b.get("domain"),
                })
    return collisions


if __name__ == "__main__":
    _ensure_tables()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"

    if cmd == "scan":
        n = scan_corpus()
        print(f"✓ Extracted {n} expiration events from corpus. Stored in `expirations` table.")

    elif cmd == "calendar":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 90
        events = calendar_next_days(days=days)
        print(f"\nExpirations in next {days} days: {len(events)}")
        for e in events[:50]:
            print(f"  {e['date']}  [{e['type']:<18}] {e['domain'] or '?':<18} — {(e['description'] or '')[:80]}")

    elif cmd == "collide":
        window = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        cols = find_collisions(window_days=window)
        print(f"\nTemporal collisions within ±{window} days: {len(cols)}\n")
        for c in cols[:30]:
            a, b = c["event_a"], c["event_b"]
            print(f"  {a['date']}  ↔  {b['date']}  ({c['days_apart']}d apart)")
            print(f"    A [{a['type']:<16}] {a['domain'] or '?'}: {(a['description'] or '')[:60]}")
            print(f"    B [{b['type']:<16}] {b['domain'] or '?'}: {(b['description'] or '')[:60]}")
            print()
    else:
        print(__doc__)
