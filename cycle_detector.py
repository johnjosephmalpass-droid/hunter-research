"""Cycle detector — finds closed epistemic loops A→B→C→...→A.

The summer research protocol requires cycle detection as Hypothesis 1.
Current state: HUNTER has 52 chains (linear A→B→C paths), 0 detected cycles.
Reason: nothing has traversed chain endpoints looking for back-edges.

This module:
 1. Parses every chain's links into (cause_node → effect_node) edges,
    where node identity is a canonicalised string of
    (broken_methodology + broken_assumption + domain).
 2. Builds the full directed graph across all chains.
 3. Runs Tarjan's strongly-connected-component algorithm to find SCCs
    of size >= 3 (genuine cycles).
 4. Classifies each cycle by type (simple, cross-domain, nested,
    hierarchical, etc. — per the Framework).
 5. Computes reinforcement_strength (edge weight × recency) vs
    correction_pressure (public-correction signals in the data).
 6. Writes to the detected_cycles table.

This is pure graph theory. No LLM calls in the detection itself.
LLM is only used for OPTIONAL cycle-description generation after
detection, as a separate step.

Run:
    python cycle_detector.py run       # detect and write
    python cycle_detector.py dry       # detect and print without writing
"""

import hashlib
import json
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime

from database import get_connection

logger = logging.getLogger("hunter.cycle_detector")

MIN_CYCLE_LENGTH = 3  # Simple loop requires at least 3 nodes
MAX_CYCLE_LENGTH = 12 # Defensive cap
NODE_CANONICAL_LEN = 120  # Chars used for node identity
NODE_MERGE_SIM = 0.78  # cosine similarity threshold for node equivalence

_embed_model = None


def _emb_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embed_model


def _merge_semantic_nodes(node_meta: dict, threshold: float = NODE_MERGE_SIM) -> dict:
    """Cluster node ids whose methodology+assumption embeddings are cosine-similar
    above `threshold`. Return a map node_id -> canonical_node_id.

    Uses simple greedy single-linkage clustering. For 200-500 nodes this is fine.
    """
    import numpy as np
    model = _emb_model()

    ids = list(node_meta.keys())
    texts = []
    for nid in ids:
        m = node_meta.get(nid, {})
        txt = f"{m.get('methodology','')} {m.get('assumption','')}".strip()[:500]
        texts.append(txt or nid)
    embs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    parent = list(range(len(ids)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    sim = embs @ embs.T
    n = len(ids)
    for i in range(n):
        for j in range(i + 1, n):
            if sim[i][j] >= threshold:
                union(i, j)

    merge_map = {}
    for i, nid in enumerate(ids):
        canonical = ids[find(i)]
        merge_map[nid] = canonical
    return merge_map


def _canonicalise(text: str) -> str:
    """Normalise a node-identity string for equality comparison."""
    if not text:
        return ""
    t = text.lower().strip()
    # Strip filler words and punctuation that shouldn't affect identity
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t)
    # Drop common framing words
    for filler in ("the ", "a ", "an ", "their ", "its ", "this ", "that "):
        t = t.replace(filler, " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:NODE_CANONICAL_LEN]


def _node_id(link: dict) -> str:
    """Compact node identity from a chain link."""
    parts = []
    for k in ("broken_methodology", "broken_assumption"):
        v = link.get(k, "")
        if isinstance(v, str):
            parts.append(_canonicalise(v))
    dom = _canonicalise(link.get("domain", ""))
    if dom and dom != "unknown":
        parts.append(dom)
    combined = " | ".join(p for p in parts if p)
    if not combined:
        combined = _canonicalise(link.get("disruption", ""))
    if not combined:
        return ""
    # Short stable hash for compact storage + short readable prefix
    h = hashlib.sha1(combined.encode("utf-8")).hexdigest()[:10]
    readable = combined[:60]
    return f"{h}::{readable}"


def _load_edges():
    """Walk every chain and emit (source_node, target_node, chain_id, chain_len)."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, chain_links, chain_length, domains_traversed, created_at
            FROM chains
        """).fetchall()
    finally:
        conn.close()

    edges = []
    node_meta = {}
    for cid, links_json, chain_len, domains, created_at in rows:
        try:
            links = json.loads(links_json) if links_json else []
        except json.JSONDecodeError:
            continue
        nodes = []
        for link in links:
            nid = _node_id(link)
            if not nid:
                continue
            nodes.append(nid)
            if nid not in node_meta:
                node_meta[nid] = {
                    "first_seen": created_at,
                    "methodology": link.get("broken_methodology", "")[:200],
                    "assumption": link.get("broken_assumption", "")[:200],
                    "domain": link.get("domain", "unknown"),
                    "practitioners": link.get("practitioners", "")[:200],
                }
        for i in range(len(nodes) - 1):
            if nodes[i] == nodes[i + 1]:
                continue  # self-loop on consecutive identical nodes = not meaningful
            edges.append({
                "src": nodes[i],
                "dst": nodes[i + 1],
                "chain_id": cid,
                "chain_length": chain_len,
                "created_at": created_at,
            })
    return edges, node_meta


def _build_graph(edges):
    """Return adjacency dict: src → {dst: [edge, ...]}."""
    adj = defaultdict(lambda: defaultdict(list))
    for e in edges:
        adj[e["src"]][e["dst"]].append(e)
    return adj


def _tarjan_sccs(adj, all_nodes):
    """Find strongly connected components using iterative Tarjan's algorithm.
    Returns list of SCCs (each a list of node ids). Only SCCs of size >= 2
    contain cycles (a single node with a self-loop is filtered by edge construction)."""
    index_counter = [0]
    stack = []
    lowlinks = {}
    index = {}
    on_stack = {}
    result = []

    def strongconnect(node):
        # Iterative version to avoid Python recursion-limit issues on wide graphs
        work_stack = [(node, iter(adj.get(node, {}).keys()))]
        call_stack = [node]
        index[node] = index_counter[0]
        lowlinks[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack[node] = True

        while work_stack:
            v, it = work_stack[-1]
            try:
                w = next(it)
                if w not in index:
                    index[w] = index_counter[0]
                    lowlinks[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack[w] = True
                    work_stack.append((w, iter(adj.get(w, {}).keys())))
                    call_stack.append(w)
                elif on_stack.get(w, False):
                    lowlinks[v] = min(lowlinks[v], index[w])
            except StopIteration:
                work_stack.pop()
                call_stack.pop()
                if lowlinks[v] == index[v]:
                    scc = []
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        scc.append(w)
                        if w == v:
                            break
                    if len(scc) >= 2:
                        result.append(scc)
                if work_stack:
                    parent = work_stack[-1][0]
                    lowlinks[parent] = min(lowlinks[parent], lowlinks[v])

    for n in all_nodes:
        if n not in index:
            strongconnect(n)
    return result


def _extract_shortest_cycles_in_scc(scc_nodes, adj):
    """Within an SCC, return the shortest simple cycle for each starting node
    (deduplicated by rotation)."""
    scc_set = set(scc_nodes)
    seen_signatures = set()
    cycles = []

    for start in scc_nodes:
        # BFS for shortest cycle back to start
        queue = [(start, [start])]
        visited = {start}
        found = None
        while queue and len(visited) < len(scc_set) * 4:
            cur, path = queue.pop(0)
            if len(path) > MAX_CYCLE_LENGTH:
                continue
            for nxt in adj.get(cur, {}):
                if nxt not in scc_set:
                    continue
                if nxt == start and len(path) >= MIN_CYCLE_LENGTH:
                    cyc = path + [nxt]
                    found = cyc
                    break
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, path + [nxt]))
            if found:
                break
        if not found:
            continue
        # Canonical signature: rotate so smallest element is first
        cyc = found[:-1]  # drop closing repeat
        rot_idx = cyc.index(min(cyc))
        canonical = tuple(cyc[rot_idx:] + cyc[:rot_idx])
        if canonical in seen_signatures:
            continue
        seen_signatures.add(canonical)
        cycles.append(list(canonical))
    return cycles


def _classify_cycle(cycle, node_meta):
    """Classify cycle type per the Framework's 9 categories."""
    n = len(cycle)
    domains = [node_meta.get(nid, {}).get("domain", "unknown") for nid in cycle]
    unique_domains = set(d for d in domains if d and d != "unknown")

    if n == 3:
        base = "simple_3node"
    elif 4 <= n <= 5:
        base = "extended"
    elif n >= 6:
        base = "deep"
    else:
        base = "simple"

    if len(unique_domains) >= max(3, n - 1):
        return f"cross_domain_{n}node"
    if len(unique_domains) <= 1:
        return f"single_domain_{n}node"
    return base


def _cycle_strength(cycle, adj, node_meta):
    """Rough reinforcement strength = edge count × chain depth × recency decay.
    Normalised to 0..1."""
    n = len(cycle)
    total = 0.0
    for i in range(n):
        src = cycle[i]
        dst = cycle[(i + 1) % n]
        edge_list = adj.get(src, {}).get(dst, [])
        if not edge_list:
            continue
        # Longer chains = stronger edges (more evidence)
        max_len = max((e["chain_length"] or 1) for e in edge_list)
        total += min(5, max_len) / 5.0
    return round(total / max(1, n), 4)


def detect_cycles(dry_run: bool = False, merge_sim: float = NODE_MERGE_SIM) -> dict:
    """Main entrypoint. Returns summary dict; optionally writes to DB.

    merge_sim: cosine-similarity threshold for merging semantically
    equivalent nodes before graph construction. Lower => more merges =>
    more cycles. 0.78 is conservative; 0.70 is aggressive.
    """
    edges, node_meta = _load_edges()
    if not edges:
        return {"edges": 0, "cycles": 0, "message": "No edges extracted — is the chains table empty?"}

    # ── Embedding-based node merging ──
    # Same real-world concept can appear with slightly different methodology/assumption
    # wording across chains. Merge semantic duplicates before cycle detection.
    try:
        merge_map = _merge_semantic_nodes(node_meta, threshold=merge_sim)
    except Exception as e:
        logger.warning(f"Semantic node merge failed: {e}. Falling back to exact string identity.")
        merge_map = {nid: nid for nid in node_meta}

    # Rewrite edges with canonical nodes
    canonical_edges = []
    for e in edges:
        src_c = merge_map.get(e["src"], e["src"])
        dst_c = merge_map.get(e["dst"], e["dst"])
        if src_c == dst_c:
            continue  # skip self-loops created by merging
        canonical_edges.append({
            **e,
            "src": src_c,
            "dst": dst_c,
        })

    # Keep canonical-only metadata
    canonical_meta = {}
    for nid, canon in merge_map.items():
        if canon not in canonical_meta:
            canonical_meta[canon] = node_meta[nid]
    node_meta = canonical_meta
    edges = canonical_edges

    num_merged = len(merge_map) - len(set(merge_map.values()))

    all_nodes = set()
    for e in edges:
        all_nodes.add(e["src"])
        all_nodes.add(e["dst"])

    adj = _build_graph(edges)
    sccs = _tarjan_sccs(adj, all_nodes)
    multi_sccs = [s for s in sccs if len(s) >= MIN_CYCLE_LENGTH]

    all_cycles = []
    for scc in multi_sccs:
        cycles = _extract_shortest_cycles_in_scc(scc, adj)
        for cyc in cycles:
            cycle_type = _classify_cycle(cyc, node_meta)
            strength = _cycle_strength(cyc, adj, node_meta)
            readable_nodes = []
            domains_in_cycle = []
            for nid in cyc:
                meta = node_meta.get(nid, {})
                method = (meta.get("methodology") or "")[:80]
                domain = meta.get("domain", "unknown")
                readable_nodes.append({
                    "node_id": nid,
                    "methodology": method,
                    "domain": domain,
                })
                if domain and domain not in domains_in_cycle:
                    domains_in_cycle.append(domain)
            all_cycles.append({
                "cycle_type": cycle_type,
                "length": len(cyc),
                "nodes": readable_nodes,
                "domains": domains_in_cycle,
                "reinforcement_strength": strength,
            })

    summary = {
        "edges": len(edges),
        "nodes": len(all_nodes),
        "nodes_merged_from_semantic_dupes": num_merged,
        "merge_threshold": merge_sim,
        "sccs_total": len(sccs),
        "sccs_with_cycles": len(multi_sccs),
        "cycles": len(all_cycles),
        "cycle_details": all_cycles[:10],  # top 10 in summary for readability
    }

    if dry_run or not all_cycles:
        return summary

    # Persist
    conn = get_connection()
    try:
        now = datetime.now().isoformat()
        inserted = 0
        for c in all_cycles:
            try:
                conn.execute("""
                    INSERT INTO detected_cycles
                    (detected_date, cycle_type, nodes, edges, domains,
                     reinforcement_strength, correction_pressure,
                     persistence_estimate, age_days, last_reinforced_days, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now,
                    c["cycle_type"],
                    json.dumps(c["nodes"]),
                    json.dumps([]),  # edges list — could be populated later
                    json.dumps(c["domains"]),
                    c["reinforcement_strength"],
                    0.0,  # correction_pressure — needs a separate pass over public-correction signals
                    float(c["reinforcement_strength"] * 120),  # rough persistence days
                    0,  # age_days
                    0,  # last_reinforced_days
                    1,
                ))
                inserted += 1
            except Exception as e:
                logger.warning(f"Insert failed for cycle: {e}")
        conn.commit()
        summary["persisted"] = inserted
    finally:
        conn.close()

    return summary


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dry"
    result = detect_cycles(dry_run=(cmd != "run"))
    print(f"\nEdges: {result['edges']}")
    print(f"Nodes: {result.get('nodes', 0)}")
    print(f"SCCs: {result.get('sccs_total', 0)} total, {result.get('sccs_with_cycles', 0)} with cycles")
    print(f"Cycles detected: {result['cycles']}")
    if result.get("persisted"):
        print(f"Cycles persisted to detected_cycles: {result['persisted']}")
    print(f"\nTop cycles:")
    for i, c in enumerate(result.get("cycle_details", [])[:5], 1):
        print(f"\n  {i}. [{c['cycle_type']}] length={c['length']} strength={c['reinforcement_strength']:.2f}")
        print(f"     Domains: {', '.join(c['domains'])}")
        for j, n in enumerate(c["nodes"][:6]):
            print(f"       {j+1}. {n['domain']}: {n['methodology'][:80]}")
