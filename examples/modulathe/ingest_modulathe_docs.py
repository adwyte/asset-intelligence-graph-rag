"""
Re-ingests Modulathe README markdowns (v1,v2) and ensures text chunks are embedded.
"""
import os, re
from dotenv import load_dotenv
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

def load_env():
    load_dotenv()
    return {
        "NEO4J_URI": os.getenv("NEO4J_URI"),
        "NEO4J_USER": os.getenv("NEO4J_USER"),
        "NEO4J_PASSWORD": os.getenv("NEO4J_PASSWORD"),
    }

def parse_markdown(path):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    title = re.findall(r"#\s*(.+)", text)
    product = title[0].strip() if title else os.path.basename(path)
    modules = re.findall(r"###\s+([A-Za-z0-9\s\-_]+)", text)
    return product, modules, text

def chunk_text(t, size=900, overlap=100):
    """
    Split text into manageable overlapping chunks.
    Ensures progress even for very large documents.
    """
    t = t.strip()
    if not t:
        return []
    chunks = []
    n = len(t)
    start = 0
    while start < n:
        end = min(n, start + size)
        chunks.append(t[start:end])
        if end >= n:
            break
        # move forward by size - overlap
        start += max(size - overlap, 1)
    return chunks

def ingest(driver, embedder, file):
    product, modules, text = parse_markdown(file)
    emb = embedder.encode([text], normalize_embeddings=True)[0].tolist()
    chunks = chunk_text(text)
    vecs = embedder.encode(chunks, normalize_embeddings=True)

    with driver.session() as s:
        s.run("""
            MERGE (p:Product {name:$name})
            SET p.source='modulathe', p.embedding=$emb
        """, name=product, emb=emb)
        for m in modules:
            s.run("""
                MATCH (p:Product {name:$prod})
                MERGE (m:Module {name:$m})
                MERGE (p)-[:HAS_MODULE]->(m)
            """, prod=product, m=m)
        for i,(txt,v) in enumerate(zip(chunks,vecs)):
            s.run("""
                MATCH (p:Product {name:$prod})
                MERGE (d:Document {title:$title})
                MERGE (p)-[:REFERENCED_IN]->(d)
                CREATE (c:Chunk {id:$id, text:$txt, embedding:$emb})
                MERGE (d)-[:HAS_CHUNK]->(c)
            """, prod=product, title=f"{product}-README",
                 id=f"{product}-chunk-{i}", txt=txt, emb=v.tolist())
    print(f"✅ Ingested {product} with {len(modules)} modules and {len(chunks)} chunks")

def main():
    env = load_env()
    driver = GraphDatabase.driver(env["NEO4J_URI"],
        auth=(env["NEO4J_USER"], env["NEO4J_PASSWORD"]))
    embedder = SentenceTransformer("thenlper/gte-small")
    for f in ["data/modulathe_v1.md", "data/modulathe_v2.md"]:
        if os.path.exists(f): ingest(driver, embedder, f)
        else: print(f"⚠️ missing {f}")
    driver.close()

if __name__ == "__main__":
    main()
