import argparse, os, uuid, yaml
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
        "EMBEDDING_MODEL_DIM": int(os.getenv("EMBEDDING_MODEL_DIM", "384")),
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
    }

def get_embedder(env):
    backend = env["EMBEDDING_BACKEND"]
    model   = env["EMBEDDING_MODEL"]
    if backend == "sentence-transformers":
        from sentence_transformers import SentenceTransformer
        st = SentenceTransformer(model)
        def _embed(texts):
            texts = [texts] if isinstance(texts, str) else texts
            return [v.tolist() for v in st.encode(texts, normalize_embeddings=True)]
        return _embed
    elif backend == "groq":
        # NOTE: Groq embeddings endpoint may be in beta / limited availability.
        # If your account lacks access, switch back to sentence-transformers.
        from groq import Groq
        client = Groq(api_key=env["GROQ_API_KEY"])
        def _embed(texts):
            texts = [texts] if isinstance(texts, str) else texts
            resp = client.embeddings.create(model=model, input=texts, encoding_format="float")
            return [d.embedding for d in resp.data]
        return _embed
    else:
        raise ValueError(f"Unknown EMBEDDING_BACKEND: {backend}")

def chunk_text(text, target_chars=900, overlap=120):
    text = (text or "").strip()
    if not text: return []
    chunks, start, n = [], 0, len(text)
    while start < n:
        end = min(n, start + target_chars)
        chunks.append(text[start:end])
        if end == n: break
        start = max(0, end - overlap)
    return chunks

# --- Cypher helpers ---

def upsert_product(tx, product):
    tx.run("""
        MERGE (p:Product {name:$name})
        ON CREATE SET p.description=$desc, p.sku=$sku, p.createdAt=timestamp()
        ON MATCH  SET p.description=$desc, p.sku=$sku, p.updatedAt=timestamp()
    """, name=product.get("name"), desc=product.get("description"), sku=product.get("sku"))

def upsert_materials(tx, materials):
    for m in materials or []:
        tx.run("MERGE (:Material {name:$name})", name=m)

def upsert_suppliers(tx, suppliers):
    for s in suppliers or []:
        tx.run("MERGE (:Supplier {name:$name})", name=s)

def upsert_part(tx, product_name, part, parent_part_id=None, part_embedding=None):
    tx.run("""
        MERGE (pt:Part {part_id:$part_id})
        ON CREATE SET pt.name=$name, pt.category=$category, pt.description=$desc, pt.createdAt=timestamp()
        ON MATCH  SET pt.name=$name, pt.category=$category, pt.description=$desc, pt.updatedAt=timestamp()
        WITH pt
        MATCH (prod:Product {name:$product_name})
        MERGE (prod)-[:HAS_PART]->(pt)
    """, part_id=part["part_id"], name=part.get("name"), category=part.get("category"),
         desc=part.get("description"), product_name=product_name)

    if parent_part_id:
        tx.run("""
            MATCH (child:Part {part_id:$child}), (parent:Part {part_id:$parent})
            MERGE (parent)-[:HAS_PART]->(child)
        """, child=part["part_id"], parent=parent_part_id)

    for m in part.get("materials", []) or []:
        tx.run("""
            MATCH (pt:Part {part_id:$pid})
            MERGE (m:Material {name:$m})
            MERGE (pt)-[:MADE_OF]->(m)
        """, pid=part["part_id"], m=m)

    for s in part.get("suppliers", []) or []:
        tx.run("""
            MATCH (pt:Part {part_id:$pid})
            MERGE (sup:Supplier {name:$s})
            MERGE (pt)-[:FROM_SUPPLIER]->(sup)
        """, pid=part["part_id"], s=s)

    for spec in part.get("specs", []) or []:
        tx.run("""
            MATCH (pt:Part {part_id:$pid})
            MERGE (sp:Spec {key:$key, value:$value, unit:$unit})
            ON CREATE SET sp.note = $note
            ON MATCH  SET sp.note = $note
            MERGE (pt)-[:HAS_SPEC]->(sp)
        """, pid=part["part_id"], key=spec.get("key"),
             value=str(spec.get("value","")), unit=spec.get("unit",""), note=spec.get("note"))

    if part_embedding is not None:
        tx.run("MATCH (pt:Part {part_id:$pid}) SET pt.embedding=$emb",
               pid=part["part_id"], emb=part_embedding)

def upsert_document_and_chunks_for_part(tx, part_id, doc_name, source, chunks, embeddings):
    doc_id = str(uuid.uuid4())
    tx.run("""
        MATCH (pt:Part {part_id:$pid})
        MERGE (d:Document {doc_id:$doc_id})
        ON CREATE SET d.name=$name, d.source=$source, d.createdAt=timestamp()
        MERGE (d)-[:DESCRIBES]->(pt)
    """, pid=part_id, doc_id=doc_id, name=doc_name, source=source)

    for text, emb in zip(chunks, embeddings):
        chunk_id = str(uuid.uuid4())
        tx.run("""
            MATCH (d:Document {doc_id:$doc_id})
            MERGE (c:Chunk {chunk_id:$cid})
            ON CREATE SET c.text=$text, c.createdAt=timestamp()
            SET c.embedding=$emb
            MERGE (d)-[:HAS_CHUNK]->(c)
        """, doc_id=doc_id, cid=chunk_id, text=text, emb=emb)

def upsert_document_and_chunks_for_product(tx, product_name, doc_name, source, chunks, embeddings):
    doc_id = str(uuid.uuid4())
    tx.run("""
        MATCH (p:Product {name:$product})
        MERGE (d:Document {doc_id:$doc_id})
        ON CREATE SET d.name=$name, d.source=$source, d.createdAt=timestamp()
        MERGE (d)-[:DESCRIBES]->(p)
    """, product=product_name, doc_id=doc_id, name=doc_name, source=source)

    for text, emb in zip(chunks, embeddings):
        chunk_id = str(uuid.uuid4())
        tx.run("""
            MATCH (d:Document {doc_id:$doc_id})
            MERGE (c:Chunk {chunk_id:$cid})
            ON CREATE SET c.text=$text, c.createdAt=timestamp()
            SET c.embedding=$emb
            MERGE (d)-[:HAS_CHUNK]->(c)
        """, doc_id=doc_id, cid=chunk_id, text=text, emb=emb)

def ingest_parts(session, product_name, parts, embed):
    def recurse(part, parent_id=None):
        p_text = part.get("description") or part.get("name") or ""
        p_emb  = embed(p_text)[0] if p_text else None
        session.execute_write(upsert_part, product_name, part, parent_id, p_emb)

        for doc in part.get("documents", []) or []:
            chunks = chunk_text(doc.get("text",""))
            if chunks:
                c_embs = embed(chunks)
                session.execute_write(
                    upsert_document_and_chunks_for_part,
                    part["part_id"], doc.get("name","Doc"), doc.get("source","unknown"),
                    chunks, c_embs
                )
        for child in part.get("children", []) or []:
            recurse(child, parent_id=part["part_id"])

    for p in parts:
        recurse(p)

def ingest_product_documents(session, product_name, docs, embed):
    for doc in docs or []:
        chunks = chunk_text(doc.get("text",""))
        if not chunks: continue
        c_embs = embed(chunks)
        session.execute_write(
            upsert_document_and_chunks_for_product,
            product_name, doc.get("name","Doc"), doc.get("source","unknown"),
            chunks, c_embs
        )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="YAML file with product + parts")
    args = parser.parse_args()

    env   = load_env()
    embed = get_embedder(env)

    driver = GraphDatabase.driver(env["NEO4J_URI"], auth=(env["NEO4J_USER"], env["NEO4J_PASSWORD"]))
    with driver.session() as s:
        payload = yaml.safe_load(open(args.data, "r", encoding="utf-8"))
        product = payload.get("product") or {}
        parts   = payload.get("parts") or []
        docs    = payload.get("documents") or []

        s.execute_write(upsert_product, product)

        # light pre-creation (optional)
        def collect(p, mats, sups):
            for m in p.get("materials", []) or []: mats.add(m)
            for u in p.get("suppliers", []) or []: sups.add(u)
            for c in p.get("children", []) or []: collect(c, mats, sups)

        mats, sups = set(), set()
        for p in parts: collect(p, mats, sups)
        s.execute_write(upsert_materials, list(mats))
        s.execute_write(upsert_suppliers, list(sups))

        ingest_parts(s, product.get("name"), parts, embed)
        ingest_product_documents(s, product.get("name"), docs, embed)

    driver.close()
    print("✅ Ingestion complete. If you change embedding dims, update the Neo4j vector index config accordingly.")
if __name__ == "__main__":
    main()
