import yaml
from typing import Any, Dict, List, Optional
from neo4j import Session

from ..db import run_write, run_read
from ..embeddings import embed_text



# Assembly mapping: determines which assembly each category belongs to

ASSEMBLY_MAP = {
    "Spindle": "Spindle Assembly",
    "Bearings": "Spindle Assembly",

    "Z Axis": "Z Axis Assembly",
    "X Axis": "X Axis Assembly",

    "Tailstock": "Tailstock Assembly",

    "Mold": "Mold System Assembly",

    "Materials": "Material Group",
    "Tools": "Tooling Group",
    "Hardware": "Hardware Group",

    "Workholding": "Spindle Assembly",
    "Motor": "Spindle Assembly",

    "Transmission": "Spindle Assembly",
    "Mechanical": "Spindle Assembly",

    "Rotary Tool": "Tooling Group",

    "Linear Motion": "Axis Motion Assembly",
    "Frame": "Axis Motion Assembly",

    "Electronics": "Electronics Assembly",
}



# Helpers


def _ensure_assembly(session: Session, product_name: str, assembly_name: str):
    """Ensure Assembly node exists and is linked to Product."""
    session.run(
        """
        MERGE (a:Assembly {name: $assembly})
        MERGE (p:Product {name: $product})
        MERGE (p)-[:HAS_ASSEMBLY]->(a)
        """,
        assembly=assembly_name,
        product=product_name,
    )


def _upsert_spec(session: Session, part_id: str, spec: Dict[str, Any]):
    """Store a spec and link it to a part."""
    key = spec.get("key")
    value = spec.get("value")
    unit = spec.get("unit") or ""  # FIX: ensure non-null
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
    parent_part_id: Optional[str] = None
):
    """Create/merge a part node, assign assembly, create children, handle specs."""
    part_id = part["part_id"]
    name = part.get("name")
    category = part.get("category", "Uncategorized")
    description = part.get("description")
    source_url = part.get("source_url")

    # Embedding for semantic search
    emb_text = f"{name} {description or ''}"
    embedding = embed_text(emb_text)

    # 1) Create Part node
    session.run(
        """
        MERGE (p:Part {part_id: $part_id})
        SET p.name = $name,
            p.category = $category,
            p.description = $description,
            p.source_url = $source_url,
            p.embedding = $embedding,
            p.embedding_dim = size($embedding)
        """,
        part_id=part_id,
        name=name,
        category=category,
        description=description,
        source_url=source_url,
        embedding=embedding,
    )

    # 2) Attach part to parent part (HAS_CHILD)
    if parent_part_id:
        session.run(
            """
            MATCH (parent:Part {part_id: $parent}), (child:Part {part_id: $child})
            MERGE (parent)-[:HAS_CHILD]->(child)
            """,
            parent=parent_part_id,
            child=part_id,
        )

    # 3) Assign to Assembly based on category
    assembly_name = ASSEMBLY_MAP.get(category)
    if assembly_name:
        _ensure_assembly(session, product_name, assembly_name)
        session.run(
            """
            MATCH (a:Assembly {name: $assembly})
            MATCH (p:Part {part_id: $part_id})
            MERGE (p)-[:BELONGS_TO]->(a)
            """,
            assembly=assembly_name,
            part_id=part_id,
        )

    # 4) Specs
    for spec in part.get("specs", []):
        _upsert_spec(session, part_id, spec)

    # 5) Children (recursive)
    for child in part.get("children", []):
        _upsert_part(session, product_name, child, parent_part_id=part_id)



# Ingest YAML Product


def ingest_yaml_file(path: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    product = data["product"]
    parts = data.get("parts", [])

    product_name = product["name"]
    description = product.get("description")
    sku = product.get("sku")

    # Product embedding
    embedding = embed_text(f"{product_name} {description}")

    def work(session: Session):
        # Create product
        session.run(
            """
            MERGE (p:Product {name: $name})
            SET p.description = $description,
                p.sku = $sku,
                p.embedding = $embedding,
                p.embedding_dim = size($embedding)
            """,
            name=product_name,
            description=description,
            sku=sku,
            embedding=embedding,
        )

        # Ingest parts
        for part in parts:
            _upsert_part(session, product_name, part, parent_part_id=None)

    run_write(work)
    print(f"✅ Ingested YAML product from {path}")
