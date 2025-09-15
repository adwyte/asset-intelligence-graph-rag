import os
import textwrap
import streamlit as st
from neo4j import GraphDatabase
from dotenv import load_dotenv


def load_env():
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


@st.cache_resource(show_spinner=False)
def get_embedder(env):
    backend = env["EMBEDDING_BACKEND"]
    model = env["EMBEDDING_MODEL"]
    if backend == "sentence-transformers":
        from sentence_transformers import SentenceTransformer
        st_model = SentenceTransformer(model)
        def _embed(texts):
            if isinstance(texts, str): texts = [texts]
            vecs = st_model.encode(texts, normalize_embeddings=True)
            return [v.tolist() for v in vecs]
        return _embed
    elif backend == "groq":
        from groq import Groq
        client = Groq(api_key=env["GROQ_API_KEY"])
        def _embed(texts):
            if isinstance(texts, str): texts = [texts]
            resp = client.embeddings.create(model=model, input=texts, encoding_format="float")
            return [d.embedding for d in resp.data]
        return _embed
    else:
        raise ValueError(f"Unknown EMBEDDING_BACKEND: {backend}")


def vector_search_chunks(session, q_vec, k, scope):
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
    RETURN node.text AS text, score,
           CASE WHEN x:Part THEN x.part_id ELSE 'PRODUCT' END AS part_id,
           x.name AS part_name,
           CASE WHEN x:Part THEN coalesce(x.category, 'Part') ELSE 'Product' END AS category,
           specs, d.name AS doc_name, d.source AS source
    ORDER BY score DESC LIMIT $k
    """
    return list(session.run(cypher, q=q_vec, k=k))


def vector_search_parts(session, q_vec, k):
    cypher = """
    CALL db.index.vector.queryNodes('part_embedding_index', $k, $q)
    YIELD node, score
    OPTIONAL MATCH (node)-[:HAS_SPEC]->(s:Spec)
    WITH node, score, collect({key:s.key, value:s.value, unit:s.unit, note:s.note}) AS specs
    RETURN coalesce(node.description,'') AS text, score,
           node.part_id AS part_id, node.name AS part_name,
           coalesce(node.category,'Part') AS category,
           specs, 'Part Description' AS doc_name, 'part' AS source
    ORDER BY score DESC LIMIT $k
    """
    return list(session.run(cypher, q=q_vec, k=k))


def synthesize(env, question, contexts):
    if not env["GROQ_API_KEY"]:
        return None
    from groq import Groq
    client = Groq(api_key=env["GROQ_API_KEY"])

    def format_specs(specs):
        if not specs: return ""
        parts = []
        for s in specs:
            k = s.get("key")
            if not k: continue
            v = s.get("value") or ""
            u = s.get("unit") or ""
            parts.append(f"{k}={v}{u}")
        return ", ".join(parts)

    blocks = []
    for i, c in enumerate(contexts, 1):
        header = f"[{i}] {c['category']}: {c['part_name']} ({c['part_id']})"
        sp = format_specs(c.get("specs"))
        if sp: header += f"\nSpecs: {sp}"
        block = f"{header}\nDoc: {c['doc_name']} ({c['source']})\nChunk: {(c['text'] or '').replace('\\n',' ').strip()}"
        blocks.append(block)

    messages = [
        {"role":"system","content":"Answer using ONLY the provided context; if unknown, say you don't know."},
        {"role":"user","content":f"Question: {question}\n\nContext:\n" + "\n\n".join(blocks) + "\n\nAnswer:"}
    ]
    resp = client.chat.completions.create(model=env["GROQ_CHAT_MODEL"], messages=messages, temperature=0)
    return resp.choices[0].message.content.strip()


st.set_page_config(page_title="Graph RAG — Parts", layout="centered")
st.title("GraphRAG for Product Asset Intelligence")

env = load_env()
embed = get_embedder(env)

question = st.text_input("Ask a question", value="List the sensor suite composition")
col1, col2, col3 = st.columns(3)
with col1:
    scope_ui = st.selectbox("Scope", ["All", "Parts only", "Product only"])
with col2:
    k = st.slider("Top-K", 3, 20, 8)
with col3:
    min_score = st.number_input("Min score filter", min_value=0.0, max_value=1.0, value=0.0, step=0.01)

fallback = st.checkbox("Fallback to Part descriptions when chunks are weak/empty", value=True)
scope_map = {"All":"all", "Parts only":"part", "Product only":"product"}
scope = scope_map[scope_ui]

if st.button("Ask"):
    with st.spinner("Retrieving…"):
        driver = GraphDatabase.driver(env["NEO4J_URI"], auth=(env["NEO4J_USER"], env["NEO4J_PASSWORD"]))
        q_vec = embed(question)[0]
        with driver.session() as session:
            rows_chunks = vector_search_chunks(session, q_vec, k, scope)
            rows = rows_chunks

            # apply min score
            if min_score > 0:
                rows = [r for r in rows if float(r["score"] or 0) >= min_score]

            # fallback to part embeddings
            if fallback and (scope in ("all","part")) and len(rows) == 0:
                rows_parts = vector_search_parts(session, q_vec, k)
                if min_score > 0:
                    rows_parts = [r for r in rows_parts if float(r["score"] or 0) >= min_score]
                rows = rows_parts
        driver.close()

    if not rows:
        st.warning("No results. Add per-part documents or keep the fallback enabled.")
    else:
        st.subheader("Top Context Chunks")
        for idx, r in enumerate(rows, 1):
            with st.expander(f"[{idx}] {r['category']} = {r['part_name']} ({r['part_id']}) • Score {r['score']:.4f} • Doc {r['doc_name']} ({r['source']})", expanded=(idx==1)):
                snippet = (r["text"] or "").replace("\n", " ").strip()
                st.write(textwrap.fill(snippet, width=100))

        answer = synthesize(env, question, rows)
        if answer:
            st.subheader("Answer")
            st.write(answer)
        else:
            st.info("No LLM key set; showing retrieved context only.")
