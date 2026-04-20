"""One-time backfill: generate embeddings for all existing facts."""
import json
import time
from database import get_connection, save_fact_embedding
from hunter import compute_fact_embedding

def backfill():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, implications, model_vulnerability
        FROM raw_facts
        WHERE implication_embedding IS NULL
        AND (implications != '[]' OR model_vulnerability != 'null')
    """)
    rows = cursor.fetchall()
    conn.close()

    print(f"Backfilling embeddings for {len(rows)} facts...")
    success = 0
    start = time.time()

    for i, row in enumerate(rows):
        try:
            implications = json.loads(row["implications"]) if row["implications"] else []
            mv = None
            if row["model_vulnerability"] and row["model_vulnerability"] != "null":
                mv = json.loads(row["model_vulnerability"])

            embedding = compute_fact_embedding(implications, mv)
            if embedding is not None:
                save_fact_embedding(row["id"], embedding.tobytes())
                success += 1
        except Exception as e:
            pass

        if (i + 1) % 500 == 0:
            elapsed = time.time() - start
            print(f"  {i+1}/{len(rows)} processed ({success} embedded, {elapsed:.1f}s)")

    elapsed = time.time() - start
    print(f"Done: {success}/{len(rows)} facts embedded in {elapsed:.1f}s")

if __name__ == "__main__":
    backfill()
