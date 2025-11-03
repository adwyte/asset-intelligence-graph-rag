"""
Compatibility scoring between parts using spec similarity + rules
"""
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os, math

def load_env():
    load_dotenv()
    return {
        "NEO4J_URI": os.getenv("NEO4J_URI"),
        "NEO4J_USER": os.getenv("NEO4J_USER"),
        "NEO4J_PASSWORD": os.getenv("NEO4J_PASSWORD")
    }

def cosine_similarity(a, b):
    dot = sum(x*y for x,y in zip(a,b))
    norm_a = math.sqrt(sum(x*x for x in a))
    norm_b = math.sqrt(sum(x*x for x in b))
    return dot / (norm_a*norm_b + 1e-8)

def compute_spec_overlap(specs_a, specs_b):
    """Very simple overlap score by matching keys + fuzzy value match"""
    score, reasons = 0, []
    if not specs_a or not specs_b:
        return 0.0, ["missing specs"]
    for sa in specs_a:
        for sb in specs_b:
            if sa["key"] == sb["key"]:
                if str(sa["value"]).lower() == str(sb["value"]).lower():
                    score += 1; reasons.append(f"{sa['key']} exact match")
                else:
                    score += 0.5; reasons.append(f"{sa['key']} differs ({sa['value']} vs {sb['value']})")
    score = score / max(len(specs_a), len(specs_b))
    return min(score, 1.0), reasons

def compute_compatibility(tx, pid_a, pid_b):
    rec = tx.run("""
        MATCH (a:Part {part_id:$a})-[:HAS_SPEC]->(sa:Spec)
        OPTIONAL MATCH (b:Part {part_id:$b})-[:HAS_SPEC]->(sb:Spec)
        RETURN collect(distinct {key:sa.key,value:sa.value,unit:sa.unit}) AS specsA,
               collect(distinct {key:sb.key,value:sb.value,unit:sb.unit}) AS specsB
    """, a=pid_a, b=pid_b).single()
    if not rec: return None
    sA, sB = rec["specsA"], rec["specsB"]
    score, reasons = compute_spec_overlap(sA, sB)
    tx.run("""
        MATCH (a:Part {part_id:$a}), (b:Part {part_id:$b})
        MERGE (a)-[r:COMPATIBLE_WITH]->(b)
        SET r.score=$score, r.reasons=$reasons, r.computedAt=timestamp()
    """, a=pid_a, b=pid_b, score=score, reasons=reasons)
    return {"a":pid_a, "b":pid_b, "score":score, "reasons":reasons}

def compute_all(env, product_name):
    driver = GraphDatabase.driver(env["NEO4J_URI"], auth=(env["NEO4J_USER"], env["NEO4J_PASSWORD"]))
    with driver.session() as s:
        parts = [r["p.part_id"] for r in s.run("MATCH (p:Part)<-[:HAS_PART]-(prod:Product {name:$n}) RETURN p.part_id", n=product_name)]
        for i,a in enumerate(parts):
            for b in parts[i+1:]:
                res = s.execute_write(compute_compatibility, a, b)
                print(f"Computed {a} ↔ {b}: {res['score']:.2f}")
    driver.close()

if __name__ == "__main__":
    env = load_env()
    pname = input("Product name: ")
    compute_all(env, pname)
