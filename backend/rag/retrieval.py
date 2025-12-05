# backend/rag/retrieval.py
from typing import Any, Dict, List, Optional
from neo4j import Session

from ..db import run_read, get_session
from ..embeddings import embed_text


def _search_parts(
    question: str,
    question_emb: List[float],
    k: int = 5
) -> List[Dict[str, Any]]:
    # 1) Semantic vector search
    vec_query = """
    CALL db.index.vector.queryNodes('part_embedding_index', $k, $embedding)
    YIELD node, score
    RETURN node, score, 'vector' AS source
    """
    vec_rows = run_read(vec_query, {"k": k, "embedding": question_emb})

    # 2) Fulltext search (if index exists)
    # This will not error if index missing, but you can wrap in try/except if needed.
    ft_query = """
    CALL db.index.fulltext.queryNodes('part_fulltext_idx', $q, $limit)
    YIELD node, score
    RETURN node, score, 'fulltext' AS source
    """
    ft_rows = run_read(ft_query, {"q": question, "limit": k})

    # 3) Merge results by part_id, keep best score
    merged: Dict[str, Dict[str, Any]] = {}
    for row in vec_rows + ft_rows:
        node = row["node"]
        pid = node.get("part_id")
        if not pid:
            continue
        existing = merged.get(pid)
        score = float(row["score"] or 0.0)

        if not existing or score > existing["score"]:
            merged[pid] = {
                "part_id": pid,
                "name": node.get("name"),
                "category": node.get("category"),
                "description": node.get("description"),
                "score": score,
                "source": row["source"],
            }

    # 4) Sort by score desc, then take top k
    results = sorted(merged.values(), key=lambda x: x["score"], reverse=True)[:k]
    return results


def _enrich_parts_with_specs_and_products(parts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not parts:
        return []
    part_ids = [p["part_id"] for p in parts if p.get("part_id")]

    query = """
    MATCH (p:Part)-[:HAS_SPEC]->(s:Spec)
    WHERE p.part_id IN $part_ids
    OPTIONAL MATCH (prod:Product)-[:HAS_PART|HAS_CHILD*0..3]->(p)
    RETURN p.part_id AS part_id,
           collect(DISTINCT {key: s.key, value: s.value, unit: s.unit}) AS specs,
           collect(DISTINCT prod.name) AS products
    """
    rows = run_read(query, {"part_ids": part_ids})
    by_id = {r["part_id"]: r for r in rows}

    enriched = []
    for p in parts:
        pid = p.get("part_id")
        extra = by_id.get(pid, {})
        p["specs"] = extra.get("specs", [])
        p["products"] = extra.get("products", [])
        enriched.append(p)
    return enriched


def _fetch_compatibility_for_parts(part_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    if not part_ids:
        return {}
    query = """
    MATCH (p:Part)-[r:COMPATIBLE_WITH]->(q:Part)
    WHERE p.part_id IN $ids AND q.part_id IN $ids
    RETURN p.part_id AS from_id,
           q.part_id AS to_id,
           r.score AS score,
           r.explanations AS explanations
    """
    rows = run_read(query, {"ids": part_ids})
    compat: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        from_id = r["from_id"]
        compat.setdefault(from_id, []).append(
            {
                "to_id": r["to_id"],
                "score": r.get("score", 0.0),
                "explanations": r.get("explanations", []),
            }
        )
    return compat


def retrieve_context(
    question: str,
    k_parts: int = 5,
) -> Dict[str, Any]:
    emb = embed_text(question)
    parts = _search_parts(question, emb, k=k_parts)
    parts = _enrich_parts_with_specs_and_products(parts)
    part_ids = [p["part_id"] for p in parts if p.get("part_id")]
    compat = _fetch_compatibility_for_parts(part_ids)

    return {
        "question": question,
        "parts": parts,
        "compatibility": compat,
    }

