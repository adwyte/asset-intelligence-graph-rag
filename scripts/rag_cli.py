import os
import json
import argparse
import textwrap
from typing import Callable, Dict, List, Optional, Any

from neo4j import GraphDatabase
from dotenv import load_dotenv


def load_env() -> Dict[str, Optional[str]]:
    load_dotenv()
    return {
        "NEO4J_URI": os.getenv("NEO4J_URI"),
        "NEO4J_USER": os.getenv("NEO4J_USER"),
        "NEO4J_PASSWORD": os.getenv("NEO4J_PASSWORD"),

        "EMBEDDING_BACKEND": os.getenv("EMBEDDING_BACKEND", "sentence-transformers"),
        "EMBEDDING_MODEL": os.getenv("EMBEDDING_MODEL", "thenlper/gte-small"),

        "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
        "GROQ_CHAT_MODEL": os.getenv("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile"),
    }


def get_embedder(env: Dict[str, Optional[str]]) -> Callable[[Any], List[List[float]]]:
    """
    Returns a function _embed(texts) -> list of embedding vectors (lists of floats).
    Embeddings are normalized (unit vectors) where supported.
    """
    backend = env["EMBEDDING_BACKEND"]
    model = env["EMBEDDING_MODEL"]

    if backend == "sentence-transformers":
        from sentence_transformers import SentenceTransformer  # type: ignore
        st = SentenceTransformer(model)

        def _embed(texts):
            if isinstance(texts, str):
                texts = [texts]
            vecs = st.encode(texts, normalize_embeddings=True)
            return [v.tolist() for v in vecs]

        return _embed

    elif backend == "groq":
        # NOTE: Groq embeddings may not be available to all accounts.
        from groq import Groq  # type: ignore
        client = Groq(api_key=env["GROQ_API_KEY"])

        def _embed(texts):
            if isinstance(texts, str):
                texts = [texts]
            resp = client.embeddings.create(
                model=model,
                input=texts,
                encoding_format="float",
            )
            return [d.embedding for d in resp.data]

        return _embed

    else:
        raise ValueError(f"Unknown EMBEDDING_BACKEND: {backend}")


def vector_search_chunks(tx, query_vec: List[float], top_k: int, scope: str = "all") -> List[Dict]:
    """
    Search :Chunk via native vector index. Returns contexts for Product or Part.
    scope: 'all' | 'part' | 'product'
    """
    filter_clause = ""
    if scope == "part":
        filter_clause = "WHERE x:Part"
    elif scope == "product":
        filter_clause = "WHERE x:Product"

    cypher = f"""
    CALL db.index.vector.queryNodes('chunk_embedding_index', $k, $q)
    YIELD node, score
    MATCH (node)<-[:HAS_CHUNK]-(d:Document)-[:DESCRIBES]->(x)
    {filter_clause}
    OPTIONAL MATCH (x)-[:HAS_SPEC]->(s:Spec)
    WITH node, score, d, x, collect({{key:s.key, value:s.value, unit:s.unit, note:s.note}}) AS specs
    RETURN
      node.chunk_id AS chunk_id,
      node.text     AS text,
      score,
      CASE
        WHEN x:Part THEN x.part_id
        ELSE coalesce(x.sku, x.name, 'PRODUCT')
      END AS part_id,
      x.name        AS part_name,
      CASE WHEN x:Part THEN coalesce(x.category, 'Part') ELSE 'Product' END AS category,
      specs,
      d.name   AS doc_name,
      d.source AS source
    ORDER BY score DESC
    LIMIT $k
    """
    result = tx.run(cypher, q=query_vec, k=top_k)
    return [r.data() for r in result]


def vector_search_parts(tx, query_vec: List[float], top_k: int) -> List[Dict]:
    """
    Search :Part via the part_embedding_index (embeddings of part descriptions).
    Build a pseudo-context using the part description + specs.
    """
    cypher = """
    CALL db.index.vector.queryNodes('part_embedding_index', $k, $q)
    YIELD node, score
    OPTIONAL MATCH (node)-[:HAS_SPEC]->(s:Spec)
    WITH node, score, collect({key:s.key, value:s.value, unit:s.unit, note:s.note}) AS specs
    RETURN
      node.part_id AS part_id,
      node.name    AS part_name,
      coalesce(node.category, 'Part') AS category,
      coalesce(node.description, '')  AS description,
      specs,
      score
    ORDER BY score DESC
    LIMIT $k
    """
    rows = [r.data() for r in tx.run(cypher, q=query_vec, k=top_k)]
    # Normalize to the same shape as chunk rows
    out = []
    for r in rows:
        desc = r.get("description") or ""
        text = desc.strip() if desc.strip() else f"{r.get('part_name')} ({r.get('category')})"
        out.append({
            "chunk_id": None,
            "text": text,
            "score": r.get("score"),
            "part_id": r.get("part_id"),
            "part_name": r.get("part_name"),
            "category": r.get("category"),
            "specs": r.get("specs"),
            "doc_name": "Part Description",
            "source": "part",
        })
    return out


def vector_search_products(tx, query_vec: List[float], top_k: int) -> List[Dict]:
    """
    OPTIONAL: Search :Product via a product_embedding_index (if created).
    Mirrors the part search; only used if --product-fallback is passed.
    """
    cypher = """
    CALL db.index.vector.queryNodes('product_embedding_index', $k, $q)
    YIELD node, score
    OPTIONAL MATCH (node)-[:HAS_SPEC]->(s:Spec)
    WITH node, score, collect({key:s.key, value:s.value, unit:s.unit, note:s.note}) AS specs
    RETURN
      coalesce(node.sku, node.name, 'PRODUCT') AS part_id,
      node.name    AS part_name,
      'Product'    AS category,
      coalesce(node.description, '')  AS description,
      specs,
      score
    ORDER BY score DESC
    LIMIT $k
    """
    rows = [r.data() for r in tx.run(cypher, q=query_vec, k=top_k)]
    out = []
    for r in rows:
        desc = r.get("description") or ""
        text = desc.strip() if desc.strip() else f"{r.get('part_name')} (Product)"
        out.append({
            "chunk_id": None,
            "text": text,
            "score": r.get("score"),
            "part_id": r.get("part_id"),
            "part_name": r.get("part_name"),
            "category": r.get("category"),
            "specs": r.get("specs"),
            "doc_name": "Product Description",
            "source": "product",
        })
    return out


def merge_and_trim(rows_a: List[Dict], rows_b: List[Dict], top_k: int) -> List[Dict]:
    """Merge two result lists, dedupe by (part_id, text), keep best scores, trim to K."""
    seen = set()
    merged: List[Dict] = []
    for lst in (rows_a, rows_b):
        for r in lst:
            key = (r.get("part_id"), r.get("text"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(r)
    merged.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    return merged[:top_k]


def format_specs(specs: Optional[List[Dict]]) -> str:
    if not specs:
        return ""
    items = []
    for s in specs:
        key = s.get("key")
        if not key:
            continue
        val = s.get("value") or ""
        unit = s.get("unit") or ""
        items.append(f"{key}={val}{unit}")
    return ", ".join(items)


def build_context_block(contexts: List[Dict]) -> str:
    blocks = []
    for i, c in enumerate(contexts, start=1):
        header = f"[{i}] {c.get('category')}: {c.get('part_name')} ({c.get('part_id')})"
        specs_line = format_specs(c.get("specs"))
        if specs_line:
            header += f"\nSpecs: {specs_line}"
        meta = f"Doc: {c.get('doc_name')} ({c.get('source')})"
        chunk_text = (c.get("text") or "").replace("\n", " ").strip()
        blocks.append(f"{header}\n{meta}\nChunk: {chunk_text}")
    return "\n\n".join(blocks)


def synthesize_answer(env: Dict[str, Optional[str]], question: str, contexts: List[Dict]) -> Optional[str]:
    if not env.get("GROQ_API_KEY"):
        return None
    try:
        from groq import Groq  # type: ignore
    except Exception:
        return None

    client = Groq(api_key=env["GROQ_API_KEY"])
    messages = [
        {
            "role": "system",
            "content": "You are a careful parts librarian. Answer using ONLY the provided context; if unknown, say you don't know.",
        },
        {
            "role": "user",
            "content": f"Question: {question}\n\nContext:\n{build_context_block(contexts)}\n\nAnswer:",
        },
    ]
    resp = client.chat.completions.create(
        model=env["GROQ_CHAT_MODEL"],
        messages=messages,
        temperature=0,
    )
    return resp.choices[0].message.content.strip()


def main():
    parser = argparse.ArgumentParser(description="Graph RAG CLI (Neo4j + vector search + Groq synthesis)")
    parser.add_argument("question", type=str, help="Your question")
    parser.add_argument("--k", type=int, default=8, help="Top-K items to return")
    parser.add_argument("--scope", choices=["all", "part", "product"], default="all",
                        help="Retrieve from parts only, product only, or both")
    parser.add_argument("--min-score", type=float, default=None,
                        help="Optional client-side filter to drop results below this score")
    parser.add_argument("--no-part-fallback", action="store_true",
                        help="Disable fallback to part embeddings when chunk results are weak/empty")
    parser.add_argument("--product-fallback", action="store_true",
                        help="Enable fallback to product embeddings (requires product_embedding_index)")
    parser.add_argument("--json", action="store_true", help="Print raw JSON rows instead of text output")
    args = parser.parse_args()

    env = load_env()
    embed = get_embedder(env)

    # Embed query
    q_vec = embed(args.question)[0]

    # Retrieve
    driver = GraphDatabase.driver(env["NEO4J_URI"], auth=(env["NEO4J_USER"], env["NEO4J_PASSWORD"]))
    try:
        with driver.session() as session:
            rows_chunks = session.execute_read(vector_search_chunks, q_vec, args.k, args.scope)

            # Decide on part fallback
            rows_parts: List[Dict] = []
            want_parts = (args.scope in ("all", "part")) and (not args.no_part_fallback)
            if want_parts:
                need_fallback = (len(rows_chunks) == 0)
                if args.min_score is not None and not need_fallback:
                    # If all chunk scores are below threshold, also fallback
                    above = [r for r in rows_chunks if r.get("score") is not None and float(r["score"]) >= args.min_score]
                    need_fallback = (len(above) == 0)
                if need_fallback:
                    try:
                        rows_parts = session.execute_read(vector_search_parts, q_vec, args.k)
                    except Exception as e:
                        # Index might not exist; swallow gracefully
                        rows_parts = []

            # Optional product fallback (off by default)
            rows_products: List[Dict] = []
            want_products = (args.scope in ("all", "product")) and args.product_fallback
            if want_products:
                need_fallback_prod = (len(rows_chunks) == 0)
                if args.min_score is not None and not need_fallback_prod:
                    above = [r for r in rows_chunks if r.get("score") is not None and float(r["score"]) >= args.min_score]
                    need_fallback_prod = (len(above) == 0)
                if need_fallback_prod:
                    try:
                        rows_products = session.execute_read(vector_search_products, q_vec, args.k)
                    except Exception:
                        rows_products = []
    finally:
        driver.close()

    # Merge & filter
    rows = merge_and_trim(rows_chunks, rows_parts + rows_products, args.k)
    if args.min_score is not None:
        rows = [r for r in rows if r.get("score") is not None and float(r["score"]) >= args.min_score]

    if not rows:
        print("No results. If you used --scope part, add per-part documents or leave fallback enabled.")
        return

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return

    print("\n=== Top Context Chunks ===")
    for i, r in enumerate(rows, start=1):
        score_val = float(r.get("score") or 0.0)
        print(f"\n[{i}] Score={score_val:.4f} | {r.get('category')} = {r.get('part_name')} ({r.get('part_id')})")
        print(f"Doc={r.get('doc_name')} ({r.get('source')})")
        snippet = (r.get("text") or "").replace("\n", " ").strip()
        print(textwrap.fill(snippet, width=100))

    answer = synthesize_answer(env, args.question, rows)
    if answer:
        print("\n=== Synthesized Answer ===\n")
        print(textwrap.fill(answer, width=100))
    else:
        print("\n(No LLM key set; showing retrieved context only.)")


if __name__ == "__main__":
    main()
