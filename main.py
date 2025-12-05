# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, Optional

from backend.rag.retrieval import retrieve_context
from backend.rag.synthesis import synthesize_answer
from backend.db import get_driver, run_read


app = FastAPI(title="Asset Intelligence Graph-RAG API")

# CORS for React dev server (adjust origin as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str
    k_parts: int = 5


class QueryResponse(BaseModel):
    answer: str
    context: Dict[str, Any]


@app.get("/api/health")
def health():
    # Basic health + Neo4j check
    try:
        rows = run_read("RETURN 1 AS ok")
        return {"status": "ok", "neo4j": bool(rows)}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


@app.post("/api/query", response_model=QueryResponse)
def api_query(req: QueryRequest):
    ctx = retrieve_context(req.question, k_parts=req.k_parts)
    answer = synthesize_answer(req.question, ctx)
    return QueryResponse(answer=answer, context=ctx)


@app.get("/api/part/{part_id}")
def api_get_part(part_id: str):
    rows = run_read(
        """
        MATCH (p:Part {part_id: $id})
        OPTIONAL MATCH (p)-[:HAS_SPEC]->(s:Spec)
        OPTIONAL MATCH (prod:Product)-[:HAS_PART|HAS_CHILD*0..3]->(p)
        OPTIONAL MATCH (p)-[r:COMPATIBLE_WITH]->(q:Part)
        RETURN p,
               collect(DISTINCT {key:s.key, value:s.value, unit:s.unit}) AS specs,
               collect(DISTINCT prod.name) AS products,
               collect(DISTINCT {to_id:q.part_id, score:r.score}) AS compat
        """,
        {"id": part_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Part not found")
    row = rows[0]
    p = row["p"]
    return {
        "part_id": p.get("part_id"),
        "name": p.get("name"),
        "category": p.get("category"),
        "description": p.get("description"),
        "source_url": p.get("source_url"),
        "specs": row["specs"],
        "products": row["products"],
        "compatibility": row["compat"],
    }


@app.get("/api/part/{part_id}/compat")
def api_get_part_compat(part_id: str):
    rows = run_read(
        """
        MATCH (p:Part {part_id: $id})-[r:COMPATIBLE_WITH]->(q:Part)
        RETURN q.part_id AS to_id, r.score AS score, r.explanations AS explanations
        ORDER BY score DESC
        """,
        {"id": part_id},
    )
    return {"part_id": part_id, "compatibility": rows}
