from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.rag.retrieval import retrieve_context
from backend.rag.synthesis import synthesize_answer
from backend.db import run_read
from backend.compatibility.scoring import (
    compute_compatibility_for_new_part,
)
from backend.config import get_settings

try:
    from groq import Groq
except ImportError:
    Groq = None


app = FastAPI(title="Asset Intelligence Graph-RAG API")

# CORS (adjust as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Models
class QueryRequest(BaseModel):
    question: str
    k_parts: int = 5
    product_name: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    context: Dict[str, Any]


class NewPartSpec(BaseModel):
    value: Any
    unit: Optional[str] = ""


class NewPartCompatRequest(BaseModel):
    product_name: str
    description: str
    category: Optional[str] = None
    specs: Optional[Dict[str, NewPartSpec]] = None
    assembly_hint: Optional[str] = None
    top_k: int = 10


# Health & Products
@app.get("/api/health")
def health():
    try:
        rows = run_read("RETURN 1 AS ok")
        return {"status": "ok", "neo4j": bool(rows)}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


@app.get("/api/products")
def api_list_products():
    rows = run_read(
        """
        MATCH (p:Product)
        RETURN p.name AS name, p.sku AS sku
        ORDER BY name
        """
    )
    return {"products": rows}


# Graph-RAG Query
@app.post("/api/query", response_model=QueryResponse)
def api_query(req: QueryRequest):
    ctx = retrieve_context(
        req.question,
        k_parts=req.k_parts,
        product_name=req.product_name,
    )
    answer = synthesize_answer(req.question, ctx)
    return QueryResponse(answer=answer, context=ctx)


# Compatibility - existing product pairs
@app.get("/api/compat/product/{product_name}")
def api_compat_for_product(product_name: str, limit: int = 200):
    """
    Read precomputed COMPATIBLE_WITH edges for a product.
    We assume scripts.compat has already been run for this product.
    """
    rows = run_read(
        """
        MATCH (prod:Product {name: $name})-[:HAS_ASSEMBLY]->(a:Assembly)
              <-[:BELONGS_TO]-(p:Part)
        MATCH (p)-[r:COMPATIBLE_WITH]->(q:Part)-[:BELONGS_TO]->(a2:Assembly)
              <-[:HAS_ASSEMBLY]-(prod)
        WHERE p.part_id < q.part_id   // avoid duplicates
        RETURN p.part_id AS part_a_id,
               p.name    AS part_a_name,
               q.part_id AS part_b_id,
               q.name    AS part_b_name,
               r.score   AS score,
               r.mechanical AS mechanical,
               r.functional AS functional,
               r.semantic AS semantic,
               r.hierarchy AS hierarchy,
               r.explanations AS explanations
        ORDER BY score DESC
        LIMIT $limit
        """,
        {"name": product_name, "limit": limit},
    )
    return {"product_name": product_name, "pairs": rows}


# Compatibility - new part vs existing
@app.post("/api/compat/new-part")
def api_new_part_compat(req: NewPartCompatRequest):
    specs_typed = None
    if req.specs:
        specs_typed = {
            key: (spec.value, spec.unit or "")
            for key, spec in req.specs.items()
        }

    results = compute_compatibility_for_new_part(
        product_name=req.product_name,
        description=req.description,
        category=req.category,
        specs=specs_typed,
        assembly_hint=req.assembly_hint,
        top_k=req.top_k,
    )
    return {"results": results}


# Speech-to-Text via Groq Whisper
@app.post("/api/stt")
async def api_stt(file: UploadFile = File(...)):
    """
    Accepts an audio file (e.g. webm/wav) and returns transcribed text.
    Uses Groq Whisper if configured.
    """
    settings = get_settings()
    if not settings.GROQ_API_KEY or Groq is None:
        raise HTTPException(
            status_code=500,
            detail="STT not configured (missing GROQ_API_KEY or groq client).",
        )

    audio_bytes = await file.read()

    client = Groq(api_key=settings.GROQ_API_KEY)
    try:
        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=("audio.webm", audio_bytes),
            # or use: file=audio_bytes and mime_type="audio/webm"
        )
        text = transcription.text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT error: {e}")

    return {"text": text}
