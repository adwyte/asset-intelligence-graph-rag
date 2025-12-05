# backend/config.py
import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        # Neo4j
        self.NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
        self.NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")

        # Embeddings
        self.EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "thenlper/gte-small")
        self.EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))

        # Groq LLM (for answer synthesis)
        self.GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
        self.GROQ_CHAT_MODEL = os.getenv(
            "GROQ_CHAT_MODEL", "llama-3.1-70b-versatile"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
