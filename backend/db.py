# backend/db.py
from typing import Any, Callable, Dict, Iterable, List, Optional
from neo4j import GraphDatabase, Driver, Session
from .config import get_settings

_driver: Optional[Driver] = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        settings = get_settings()
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _driver


def get_session() -> Session:
    return get_driver().session()


def run_read(query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    with get_session() as session:
        result = session.run(query, params or {})
        return [r.data() for r in result]


def run_write(
    work: Callable[[Session], Any]
) -> Any:
    with get_session() as session:
        return work(session)
