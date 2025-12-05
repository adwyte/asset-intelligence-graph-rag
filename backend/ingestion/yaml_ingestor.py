# backend/ingestion/yaml_ingestor.py
from typing import Any, Dict, List, Optional
import yaml
from neo4j import Session

from ..db import run_write
from ..embeddings import embed_text
from ..config import get_settings


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _make_part_embedding(part: Dict[str, Any]) -> List[float]:
    name = part.get("name", "")
    desc = part.get("description", "")
    specs = part.get("specs", []) or []
    specs_text = ", ".join(
        f"{s.get('key')}={s.get('value')}{s.get('unit','')}" for s in specs
    )
    text = f"{name}\n{desc}\n{specs_text}"
    return embed_text(text)


def _upsert_product(session: Session, product: Dict[str, Any]) -> None:
    name = product["name"]
    description = product.get("description", "")
    sku = product.get("sku", "")
    emb = embed_text(f"{name}\n{description}\n{sku}")
    settings = get_settings()

    session.run(
        """
        MERGE (p:Product {name: $name})
        SET p.description = $description,
            p.sku = $sku,
            p.embedding = $embedding,
            p.embedding_dim = $dim
        """,
        name=name,
        description=description,
        sku=sku,
        embedding=emb,
        dim=settings.EMBEDDING_DIM,
    )


def _upsert_spec(session: Session, part_id: str, spec: Dict[str, Any]) -> None:
    key = spec.get("key")
    value = spec.get("value")
    unit = spec.get("unit") or ""
    note = spec.get("note") or ""

    session.run(
        """
        MATCH (part:Part {part_id: $part_id})
        MERGE (s:Spec {key: $key, value: $value, unit: $unit})
        SET s.note = $note
        MERGE (part)-[:HAS_SPEC]->(s)
        """,
        part_id=part_id,
        key=key,
        value=value,
        unit=unit,
        note=note,
    )


def _upsert_part(
    session: Session,
    product_name: str,
    part: Dict[str, Any],
    parent_part_id: Optional[str] = None,
) -> None:
    part_id = part["part_id"]
    name = part.get("name", "")
    category = part.get("category", "")
    description = part.get("description", "")
    source_url = part.get("source_url")
    emb = _make_part_embedding(part)
    settings = get_settings()

    session.run(
        """
        MERGE (part:Part {part_id: $part_id})
        SET part.name = $name,
            part.category = $category,
            part.description = $description,
            part.source_url = $source_url,
            part.embedding = $embedding,
            part.embedding_dim = $dim
        WITH part
        MATCH (product:Product {name: $product_name})
        MERGE (product)-[:HAS_PART]->(part)
        """,
        part_id=part_id,
        name=name,
        category=category,
        description=description,
        source_url=source_url,
        embedding=emb,
        dim=settings.EMBEDDING_DIM,
        product_name=product_name,
    )

    # Specs
    for spec in part.get("specs", []) or []:
        _upsert_spec(session, part_id, spec)

    # Parent-child relationships
    if parent_part_id:
        session.run(
            """
            MATCH (parent:Part {part_id: $parent_id}),
                  (child:Part {part_id: $child_id})
            MERGE (parent)-[:HAS_CHILD]->(child)
            """,
            parent_id=parent_part_id,
            child_id=part_id,
        )

    # Recurse into children
    for child in part.get("children", []) or []:
        _upsert_part(session, product_name, child, parent_part_id=part_id)


def ingest_yaml_file(path: str) -> None:
    data = _load_yaml(path)
    product = data["product"]
    parts = data.get("parts", [])

    def work(session: Session) -> None:
        _upsert_product(session, product)
        for part in parts:
            _upsert_part(session, product["name"], part, parent_part_id=None)

    run_write(work)
    print(f"✅ Ingested YAML product from {path}")
