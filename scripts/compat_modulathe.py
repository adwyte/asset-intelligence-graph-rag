from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

def load_env():
    load_dotenv()
    return {
        "NEO4J_URI": os.getenv("NEO4J_URI"),
        "NEO4J_USER": os.getenv("NEO4J_USER"),
        "NEO4J_PASSWORD": os.getenv("NEO4J_PASSWORD")
    }

def cross_compare(driver):
    with driver.session() as s:
        pairs = s.run("""
            MATCH (p1:Product)-[:HAS_MODULE]->(m1:Module),
                  (p2:Product)-[:HAS_MODULE]->(m2:Module)
            WHERE toLower(p1.name) CONTAINS 'modulathe v1'
              AND toLower(p2.name) CONTAINS 'modulathe v2'
            RETURN DISTINCT m1.name AS v1, m2.name AS v2
        """)
        created = 0
        for rec in pairs:
            v1, v2 = rec["v1"], rec["v2"]
            if v1 and v2:
                if v1.lower() == v2.lower():
                    s.run("""
                        MATCH (m1:Module {name:$v1}), (m2:Module {name:$v2})
                        MERGE (m1)-[r:CROSS_VERSION_COMPATIBLE_WITH]->(m2)
                        SET r.score=0.9, r.reason='same module name'
                    """, v1=v1, v2=v2)
                    created += 1
        print(f"✅ created {created} cross-version links")

if __name__ == "__main__":
    env = load_env()
    driver = GraphDatabase.driver(env["NEO4J_URI"], auth=(env["NEO4J_USER"], env["NEO4J_PASSWORD"]))
    cross_compare(driver)
    driver.close()
