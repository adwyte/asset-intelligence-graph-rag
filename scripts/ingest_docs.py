#!/usr/bin/env python3
import os, glob, uuid
from neo4j import GraphDatabase
from dotenv import load_dotenv
from pypdf import PdfReader

def load_env():
    load_dotenv()
    return {
        "NEO4J_URI": os.getenv("NEO4J_URI"),
        "NEO4J_USER": os.getenv("NEO4J_USER"),
        "NEO4J_PASSWORD": os.getenv("NEO4J_PASSWORD"),
        "EMBEDDING_BACKEND": os.getenv("EMBEDDING_BACKEND", "sentence-transformers"),
        "EMBEDDING_MODEL": os.getenv("EMBEDDING_MODEL", "thenlper/gte-small"),
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
    }

def get_embedder(env):
    backend = env["EMBEDDING_BACKEND"]
    model = env["EMBEDDING_MODEL"]
    if backend == "sentence-transformers":
        from sentence_transformers import SentenceTransformer
        st = SentenceTransformer(model)
        def _embed(texts):
            if isinstance(texts, str): texts = [texts]
            return [v.tolist() for v in st.encode(texts, normalize_embeddings=True)]
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
        raise ValueError("Unknown EMBEDDING_BACKEND")

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

def upsert_doc_chunks(tx, part_id, doc_name, source, chunks, embeddings):
    doc_id = str(uuid.uuid4())
    tx.run("""
        MATCH (pt:Part {part_id:$pid})
        MERGE (d:Document {doc_id:$doc_id})
        ON CREATE SET d.name=$name, d.source=$source, d.createdAt=timestamp()
        MERGE (d)-[:DESCRIBES]->(pt)
    """, pid=part_id, doc_id=doc_id, name=doc_name, source=source)
    for text, emb in zip(chunks, embeddings):
        cid = str(uuid.uuid4())
        tx.run("""
            MATCH (d:Document {doc_id:$doc_id})
            MERGE (c:Chunk {chunk_id:$cid})
            ON CREATE SET c.text=$text, c.createdAt=timestamp()
            SET c.embedding=$emb
            MERGE (d)-[:HAS_CHUNK]->(c)
        """, doc_id=doc_id, cid=cid, text=text, emb=emb)

def read_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        return open(path, "r", encoding="utf-8", errors="ignore").read()
    if ext == ".pdf":
        reader = PdfReader(path)
        return "\n".join([p.extract_text() or "" for p in reader.pages])
    return ""  # skip other types

def main():
    env = load_env()
    embed = get_embedder(env)

    base = "data/docs"
    if not os.path.isdir(base):
        print("No data/docs folder found.")
        return

    driver = GraphDatabase.driver(env["NEO4J_URI"], auth=(env["NEO4J_USER"], env["NEO4J_PASSWORD"]))
    for part_dir in sorted(os.listdir(base)):
        part_path = os.path.join(base, part_dir)
        if not os.path.isdir(part_path): continue
        files = glob.glob(os.path.join(part_path, "*.*"))
        for f in files:
            text = read_text(f)
            if not text.strip(): continue
            chunks = chunk_text(text)
            embs = embed(chunks)
            doc_name = os.path.basename(f)
            source = "file"
            with driver.session() as s:
                s.execute_write(upsert_doc_chunks, part_dir, doc_name, source, chunks, embs)
            print(f"Ingested {doc_name} for part {part_dir} ({len(chunks)} chunks)")
    driver.close()
    print("Done.")

if __name__ == "__main__":
    main()
