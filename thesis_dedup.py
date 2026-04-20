"""Thesis-level semantic dedup.

Prevents the "CMBS cluster" problem: fact-level dedup (Jaccard on fact_ids)
is too narrow — collisions with *different* fact ids can still express the
SAME underlying macro thesis ("CRE is mispriced") under different labels.

This module embeds each thesis's core mechanism and refuses to open a new
portfolio position whose thesis is cosine-similar to an existing open one.

Usage:
    from thesis_dedup import is_thesis_duplicate

    dup, similar_to, sim = is_thesis_duplicate(
        hypothesis_text="...",
        action_steps="...",
    )
    if dup:
        print(f"Skipping — {sim:.2f} similar to open position in {similar_to}")

Thresholds (cosine on all-MiniLM-L6-v2 normalized embeddings):
    >= 0.85   near-duplicate, block by default
    0.70-0.85 variant, soft-flag (log but still allow)
    < 0.70    genuinely different thesis
"""

import logging
from typing import Optional

from database import get_connection

logger = logging.getLogger("hunter.thesis_dedup")

DUP_THRESHOLD = 0.85
VARIANT_THRESHOLD = 0.70

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _embed(text: str):
    """Return 384-d normalised embedding for a thesis-core string."""
    if not text or not text.strip():
        return None
    model = _get_model()
    return model.encode(text[:2000], normalize_embeddings=True)


def _thesis_core(hypothesis_text: str, action_steps: str = "") -> str:
    """Build the canonical string we embed. Keep hypothesis text primary;
    action steps disambiguate long/short direction and instrument choice."""
    parts = []
    if hypothesis_text:
        parts.append(hypothesis_text.strip()[:1200])
    if action_steps:
        parts.append(action_steps.strip()[:400])
    return " | ".join(parts)


def _open_position_theses():
    """Return list of (position_id, ticker, direction, thesis_core) for
    all currently open positions."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, ticker, direction, hypothesis_text, domains
            FROM portfolio_positions
            WHERE status = 'open'
        """).fetchall()
        out = []
        for r in rows:
            pid, ticker, direction, hyp, domains = r
            if not hyp:
                continue
            out.append({
                "position_id": pid,
                "ticker": ticker,
                "direction": direction,
                "thesis_core": _thesis_core(hyp, ""),
                "domains": domains or "",
            })
        return out
    finally:
        conn.close()


def is_thesis_duplicate(
    hypothesis_text: str,
    action_steps: str = "",
    block_threshold: float = DUP_THRESHOLD,
    variant_threshold: float = VARIANT_THRESHOLD,
) -> dict:
    """Check whether a new hypothesis is a duplicate or variant of any
    currently open portfolio position.

    Returns dict with:
        is_duplicate: True if >= block_threshold
        is_variant:   True if between variant_threshold and block_threshold
        similarity:   max cosine similarity found
        similar_to:   dict with position_id / ticker / direction of nearest
        all_similar:  list of all positions >= variant_threshold
    """
    result = {
        "is_duplicate": False,
        "is_variant": False,
        "similarity": 0.0,
        "similar_to": None,
        "all_similar": [],
    }

    core = _thesis_core(hypothesis_text, action_steps)
    if not core:
        return result

    try:
        new_emb = _embed(core)
    except Exception as e:
        logger.warning(f"Failed to embed new thesis: {e}")
        return result
    if new_emb is None:
        return result

    open_theses = _open_position_theses()
    if not open_theses:
        return result

    import numpy as np

    best = None
    for t in open_theses:
        try:
            t_emb = _embed(t["thesis_core"])
        except Exception:
            continue
        if t_emb is None:
            continue
        sim = float(np.dot(new_emb, t_emb))  # both normalised → cosine

        if sim >= variant_threshold:
            result["all_similar"].append({
                "position_id": t["position_id"],
                "ticker": t["ticker"],
                "direction": t["direction"],
                "similarity": round(sim, 4),
            })
        if best is None or sim > best["similarity"]:
            best = {
                "position_id": t["position_id"],
                "ticker": t["ticker"],
                "direction": t["direction"],
                "similarity": sim,
            }

    if best is not None:
        result["similarity"] = round(best["similarity"], 4)
        result["similar_to"] = best
        if best["similarity"] >= block_threshold:
            result["is_duplicate"] = True
        elif best["similarity"] >= variant_threshold:
            result["is_variant"] = True

    result["all_similar"].sort(key=lambda x: -x["similarity"])
    return result


def log_thesis_fingerprint(hypothesis_id: int, hypothesis_text: str,
                           action_steps: str = "") -> Optional[bytes]:
    """Persist a fingerprint for this hypothesis so future runs can dedup
    even across restarts. Stored as bytes in thesis_fingerprints table.

    Creates table on first call if missing."""
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS thesis_fingerprints (
                hypothesis_id INTEGER PRIMARY KEY REFERENCES hypotheses(id),
                embedding BLOB NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        core = _thesis_core(hypothesis_text, action_steps)
        emb = _embed(core)
        if emb is None:
            return None
        blob = emb.astype("float32").tobytes()
        conn.execute("""
            INSERT OR REPLACE INTO thesis_fingerprints (hypothesis_id, embedding)
            VALUES (?, ?)
        """, (hypothesis_id, blob))
        conn.commit()
        return blob
    finally:
        conn.close()


# CLI for spot-checking the CMBS cluster
if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "audit":
        # Audit existing open positions for clustering
        print("Auditing open portfolio positions for thesis clustering...\n")
        open_theses = _open_position_theses()
        if len(open_theses) < 2:
            print("Fewer than 2 open positions — nothing to compare.")
            sys.exit(0)

        import numpy as np
        embs = []
        for t in open_theses:
            try:
                e = _embed(t["thesis_core"])
                embs.append((t, e))
            except Exception:
                continue

        # Pairwise similarity matrix
        print(f"Pairwise thesis similarity across {len(embs)} open positions:")
        print(f"{'':12} " + " ".join(f"{t[0]['ticker']:>7}" for t in embs))
        clusters = []
        for i, (ti, ei) in enumerate(embs):
            row = []
            for j, (tj, ej) in enumerate(embs):
                if i == j:
                    row.append("  --  ")
                else:
                    sim = float(np.dot(ei, ej))
                    row.append(f"{sim:.3f}")
                    if i < j and sim >= VARIANT_THRESHOLD:
                        clusters.append({
                            "a": ti["ticker"], "b": tj["ticker"],
                            "similarity": round(sim, 3),
                            "level": "DUPLICATE" if sim >= DUP_THRESHOLD else "variant",
                        })
            print(f"{ti['ticker']:12} " + " ".join(f"{v:>7}" for v in row))

        print(f"\nClusters (sim ≥ {VARIANT_THRESHOLD}):")
        clusters.sort(key=lambda c: -c["similarity"])
        for c in clusters:
            print(f"  {c['level']:>10} {c['a']:>5} ↔ {c['b']:<5} sim={c['similarity']}")
        if not clusters:
            print("  (none — positions are semantically diverse)")
        sys.exit(0)

    # Default: check a hypothesis passed via stdin
    text = sys.stdin.read().strip()
    if not text:
        print("Usage: python thesis_dedup.py audit")
        print("   or: echo 'hypothesis text' | python thesis_dedup.py")
        sys.exit(1)
    result = is_thesis_duplicate(text)
    print(json.dumps(result, indent=2))
