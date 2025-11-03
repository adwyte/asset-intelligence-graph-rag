import argparse, os, uuid, yaml
from neo4j import GraphDatabase
from dotenv import load_dotenv

# -----------------------
# Environment + Embedding
# -----------------------
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
    backend, model = env["EMBEDDING_BACKEND"], env["EMBEDDING_MODEL"]
    if backend == "sentence-transformers":
        from sentence_transformers import SentenceTransformer
        st = SentenceTransformer(model)
        def _embed(texts):
            texts = [texts] if isinstance(texts, str) else texts
            return [v.tolist() for v in st.encode(texts, normalize_embeddings=True)]
        return _embed
    elif backend == "groq":
        from groq import Groq
        client = Groq(api_key=env["GROQ_API_KEY"])
        def _embed(texts):
            texts = [texts] if isinstance(texts, str) else texts
            resp = client.embeddings.create(model=model, input=texts, encoding_format="float")
            return [d.embedding for d in resp.data]
        return _embed
    else:
        raise ValueError(f"Unknown EMBEDDING_BACKEND: {backend}")

# -----------------------
# Text Utilities
# -----------------------
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

# -----------------------
# Cypher Helpers
# -----------------------
def upsert_product(tx, product, embedding):
    tx.run("""
        MERGE (p:Product {name:$name})
        ON CREATE SET p.description=$desc, p.createdAt=timestamp()
        ON MATCH SET p.description=$desc, p.updatedAt=timestamp()
        SET p.embedding=$embedding
    """, name=product.get("name"), desc=product.get("description",""), embedding=embedding)

def upsert_part(tx, product_name, part, embedding):
    tx.run("""
        MERGE (pt:Part {part_id:$part_id})
        ON CREATE SET pt.name=$name, pt.category=$category, pt.description=$desc, pt.createdAt=timestamp()
        ON MATCH SET pt.name=$name, pt.category=$category, pt.description=$desc, pt.updatedAt=timestamp()
        SET pt.embedding=$embedding
        WITH pt
        MATCH (prod:Product {name:$product_name})
        MERGE (prod)-[:HAS_PART]->(pt)
    """, part_id=part["part_id"], name=part.get("name"), category=part.get("category"),
         desc=part.get("description"), product_name=product_name, embedding=embedding)

def upsert_specs_for_part(tx, part_id, specs):
    for s in specs or []:
        tx.run("""
            MATCH (p:Part {part_id:$pid})
            MERGE (sp:Spec {key:$key, value:$value, unit:$unit})
            ON CREATE SET sp.note=$note
            MERGE (p)-[:HAS_SPEC]->(sp)
        """, pid=part_id, key=s.get("key"), value=str(s.get("value")), unit=s.get("unit"), note=s.get("note"))

# -----------------------
# Main Ingestion
# -----------------------
def ingest_yaml(file_path, driver, embed):
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    product = data.get("product")
    product_emb = embed(product.get("description", ""))[0]
    with driver.session() as s:
        s.execute_write(upsert_product, product, product_emb)

    for part in data.get("parts", []):
        ptext = f"{part.get('name','')} {part.get('description','')} {part.get('category','')}"
        p_emb = embed(ptext)[0]
        with driver.session() as s:
            s.execute_write(upsert_part, product["name"], part, p_emb)
            s.execute_write(upsert_specs_for_part, part["part_id"], part.get("specs"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="YAML data file path")
    args = parser.parse_args()

    env = load_env()
    embed = get_embedder(env)
    driver = GraphDatabase.driver(env["NEO4J_URI"], auth=(env["NEO4J_USER"], env["NEO4J_PASSWORD"]))

    ingest_yaml(args.data, driver, embed)
    driver.close()
    print(f"✅ Ingested {args.data}")

if __name__ == "__main__":
    main()
