import os
import json
import argparse
import textwrap
from neo4j import GraphDatabase
from dotenv import load_dotenv


def load_env():
    load_dotenv()
    return {
        "NEO4J_URI": os.getenv("NEO4J_URI"),
        "NEO4J_USER": os.getenv("NEO4J_USER"),
        "NEO4J_PASSWORD": os.getenv("NEO4J_PASSWORD"),

        # Embeddings (default: local + free)
        "EMBEDDING_BACKEND": os.getenv("EMBEDDING_BACKEND", "sentence-transformers"),
        "EMBEDDING_MODEL": os.getenv("EMBEDDING_MODEL", "thenlper/gte-small"),

        # LLM (Groq for answer synthesis)
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
        "GROQ_CHAT_MODEL": os.getenv("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile"),
    }


def get_embedder(env):
    backend = env["EMBEDDING_BACKEND"]
    model = env["EMBEDDING_MODEL"]

    if backend == "sentence-transformers":
        from sentence_transformers import SentenceTransformer
        st = SentenceTransformer(model)

        def _embed(texts):
            if isinstance(texts, str):
                texts = [texts]
            vecs = st.encode(texts, normalize_embeddings=True)
            return [v.tolist() for v in vecs]

        return _embed

    elif backend == "groq":
        # NOTE: Groq embeddings may not be available to all accounts.
        from groq import Groq
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


def vector_search_chunks(tx, query_vec, top_k, scope="all"):
    """
    Searches :Chunk nodes via vector index, returning contexts linked to either a Part
    or the Product. 'scope' can be 'all' | 'part' | 'product'.
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
      CASE WHEN x:Part THEN x.part_id ELSE 'PRODUCT' END AS part_id,
      x.name        AS part_name,
      CASE WHEN x:Part THEN coalesce(x.category, 'Part') ELSE 'Product' END AS category,
      specs,
      d.name   AS doc_name,
      d.source AS source
    ORDER BY score DESC
    LIMIT $k
    """
    return list(tx.run(cypher, q=query_vec, k=top_k))


def format_specs(specs):
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


def build_context_block(contexts):
    blocks = []
    for i, c in enumerate(contexts, start=1):
        header = f"[{i}] {c['category']}: {c['part_name']} ({c['part_id']})"
        specs_line = format_specs(c.get("specs"))
        if specs_line:
            header += f"\nSpecs: {specs_line}"
        meta = f"Doc: {c['doc_name']} ({c['source']})"
        chunk_text = (c["text"] or "").replace("\n", " ").strip()
        blocks.append(f"{header}\n{meta}\nChunk: {chunk_text}")
    return "\n\n".join(blocks)


def synthesize_answer(env, question, contexts):
    if not env["GROQ_API_KEY"]:
        return None
    from groq import Groq
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
    parser.add_argument("--k", type=int, default=8, help="Top-K chunks")
    parser.add_argument("--scope", choices=["all", "part", "product"], default="all",
                        help="Retrieve from parts only, product only, or both")
    parser.add_argument("--min-score", type=float, default=None,
                        help="Optional client-side filter to drop results below this score")
    parser.add_argument("--json", action="store_true", help="Print raw JSON rows instead of text output")
    args = parser.parse_args()

    env = load_env()
    embed = get_embedder(env)

    # Embed query
    q_vec = embed(args.question)[0]

    # Retrieve
    driver = GraphDatabase.driver(env["NEO4J_URI"], auth=(env["NEO4J_USER"], env["NEO4J_PASSWORD"]))
    with driver.session() as session:
        rows = session.execute_read(vector_search_chunks, q_vec, args.k, args.scope)
    driver.close()

    # Optional score filter (client-side)
    if args.min_score is not None:
        rows = [r for r in rows if r["score"] is not None and float(r["score"]) >= args.min_score]

    if not rows:
        print("No results. Did you ingest data and create the vector index?")
        return

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return

    print("\n=== Top Context Chunks ===")
    for i, r in enumerate(rows, start=1):
        print(f"\n[{i}] Score={r['score']:.4f} | {r['category']} = {r['part_name']} ({r['part_id']})")
        print(f"Doc={r['doc_name']} ({r['source']})")
        snippet = (r["text"] or "").replace("\n", " ").strip()
        print(textwrap.fill(snippet, width=100))

    answer = synthesize_answer(env, args.question, rows)
    if answer:
        print("\n=== Synthesized Answer ===\n")
        print(textwrap.fill(answer, width=100))
    else:
        print("\n(No LLM key set; showing retrieved context only.)")

if __name__ == "__main__":
    main()
