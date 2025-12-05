# backend/embeddings.py
from typing import List
from functools import lru_cache
from sentence_transformers import SentenceTransformer
import numpy as np

from .config import get_settings


@lru_cache
def get_model() -> SentenceTransformer:
    settings = get_settings()
    model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return model


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    model = get_model()
    embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    # Ensure Python lists for Neo4j
    return [vec.astype(float).tolist() for vec in embeddings]


def embed_text(text: str) -> List[float]:
    return embed_texts([text])[0]
