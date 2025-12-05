# backend/rag/retrieval.py
from typing import Any, Dict, List, Optional
from neo4j import Session

from ..db import run_read
from ..embeddings import embed_text


# 1. VECTOR + FULLTEXT SEARCH WITH PRODUCT / ASSEMBLY FILTERS

def _search_parts(
        question: str,
        question_emb: List[float],
        k: int = 5,
        product_name: Optional[str] = None,
        assembly_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    params = {
        "embedding": question_emb,
        "limit": k,
        "q": question
    }

    filters = []

    # Filter by product_name → Get allowed part_ids
    if product_name:
        rows = run_read("""
            MATCH (prod:Product {name: $name})-[:HAS_ASSEMBLY]->(a)<-[:BELONGS_TO]-(p)
            RETURN DISTINCT p.part_id AS pid
        """, {"name": product_name})

        allowed_ids = [r["pid"] for r in rows]
        params["product_ids"] = allowed_ids
        filters.append("node.part_id IN $product_ids")

    # Filter by assembly_name
    if assembly_name:
        rows = run_read("""
            MATCH (a:Assembly {name: $name})<-[:BELONGS_TO]-(p)
            RETURN DISTINCT p.part_id AS pid
        """, {"name": assembly_name})

        allowed_ids = [r["pid"] for r in rows]
        params["assembly_ids"] = allowed_ids
        filters.append("node.part_id IN $assembly_ids")

    # Build WHERE clause
    where_clause = ""
    if filters:
        where_clause = "WHERE " + " AND ".join(filters)

    # ----------------------
    # 1A. VECTOR SEARCH
    # ----------------------
    vec_query = f"""
    CALL db.index.vector.queryNodes(
        'part_embedding_index',
        $limit,
        $embedding
    )
    YIELD node, score
    {where_clause}
    RETURN node, score, 'vector' AS source
    """

    vec_rows = run_read(vec_query, params)

    # ----------------------
    # 1B. FULLTEXT SEARCH
    # ----------------------
    ft_query = f"""
    CALL db.index.fulltext.queryNodes(
        'part_fulltext_idx',
        $q,
        {{ limit: $limit }}
    )
    YIELD node, score
    {where_clause}
    RETURN node, score, 'fulltext' AS source
    """

    ft_rows = run_read(ft_query, params)

    # ----------------------
    # 1C. MERGE RESULTS
    # ----------------------
    merged: Dict[str, Dict[str, Any]] = {}

    for row in vec_rows + ft_rows:
        node = row["node"]
        pid = node.get("part_id")
        if not pid:
            continue

        score = float(row["score"] or 0.0)

        if pid not in merged or score > merged[pid]["score"]:
            merged[pid] = {
                "part_id": pid,
                "name": node.get("name"),
                "category": node.get("category"),
                "description": node.get("description"),
                "score": score,
                "source": row["source"],
            }

    return sorted(merged.values(), key=lambda x: x["score"], reverse=True)[:k]


# 2. SPEC + PRODUCT ENRICHMENT

def _enrich_parts_with_specs_and_products(parts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not parts:
        return []

    part_ids = [p["part_id"] for p in parts]

    query = """
    MATCH (p:Part)
    WHERE p.part_id IN $part_ids
    OPTIONAL MATCH (p)-[:HAS_SPEC]->(s:Spec)
    OPTIONAL MATCH (prod:Product)-[:HAS_ASSEMBLY]->(:Assembly)<-[:BELONGS_TO]-(p)
    RETURN p.part_id AS part_id,
           collect(DISTINCT {key: s.key, value: s.value, unit: s.unit}) AS specs,
           collect(DISTINCT prod.name) AS products
    """

    rows = run_read(query, {"part_ids": part_ids})
    lookup = {r["part_id"]: r for r in rows}

    enriched = []
    for p in parts:
        pid = p["part_id"]
        ext = lookup.get(pid, {})
        p["specs"] = ext.get("specs", [])
        p["products"] = ext.get("products", [])
        enriched.append(p)

    return enriched


# 3. COMPATIBILITY LOOKUP

def _fetch_compatibility_for_parts(part_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    if not part_ids:
        return {}

    query = """
    MATCH (p:Part)-[r:COMPATIBLE_WITH]->(q:Part)
    WHERE p.part_id IN $ids AND q.part_id IN $ids
    RETURN 
        p.part_id AS from_id,
        q.part_id AS to_id,
        r.score AS score,
        r.explanations AS explanations
    """

    rows = run_read(query, {"ids": part_ids})

    compat: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        fid = r["from_id"]
        compat.setdefault(fid, []).append({
            "to_id": r["to_id"],
            "score": r["score"],
            "explanations": r.get("explanations", []),
        })

    return compat


# 4. PUBLIC ENTRYPOINT

def retrieve_context(
        question: str,
        k_parts: int = 5,
        product_name: Optional[str] = None,
        assembly_name: Optional[str] = None,
) -> Dict[str, Any]:
    emb = embed_text(question)

    parts = _search_parts(
        question,
        emb,
        k=k_parts,
        product_name=product_name,
        assembly_name=assembly_name,
    )

    parts = _enrich_parts_with_specs_and_products(parts)
    part_ids = [p["part_id"] for p in parts]
    compat = _fetch_compatibility_for_parts(part_ids)

    return {
        "question": question,
        "product_filter": product_name,
        "assembly_filter": assembly_name,
        "parts": parts,
        "compatibility": compat,
    }
