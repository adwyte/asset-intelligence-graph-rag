# backend/compatibility/scoring.py
"""
Compatibility scoring engine v2.0

- Uses:
  - mechanical spec similarity (numeric + categorical)
  - functional role based on category
  - assembly membership (shared assembly)
  - semantic similarity (embedding cosine)
- Supports:
  - offline computation of COMPATIBLE_WITH for existing parts in a product
  - on-the-fly scoring for a NEW part (free text + optional structured specs)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import math

from neo4j import Session

from ..db import run_read, run_write, get_session
from ..embeddings import embed_text
from ..ingestion.yaml_ingestor import ASSEMBLY_MAP  # reuse same mapping


# Internal model

@dataclass
class PartInfo:
    part_id: str
    name: str
    category: str
    description: Optional[str]
    assemblies: List[str]
    specs: Dict[str, Tuple[Any, str]]  # key -> (value, unit)
    embedding: Optional[List[float]]


# Fetch helpers

def _fetch_parts_for_product(product_name: str) -> List[PartInfo]:
    """
    Fetch all parts belonging to a product via assemblies, including specs & embeddings.
    """
    rows = run_read(
        """
        MATCH (prod:Product {name: $name})-[:HAS_ASSEMBLY]->(a:Assembly)
              <-[:BELONGS_TO]-(p:Part)
        OPTIONAL MATCH (p)-[:HAS_SPEC]->(s:Spec)
        OPTIONAL MATCH (p)-[:BELONGS_TO]->(a2:Assembly)
        RETURN p,
               collect(DISTINCT s) AS specs,
               collect(DISTINCT a2.name) AS assemblies
        """,
        {"name": product_name},
    )

    parts: List[PartInfo] = []
    for row in rows:
        p = row["p"]
        if p is None:
            continue

        part_id = p.get("part_id")
        if not part_id:
            continue

        name = p.get("name")
        category = p.get("category", "Uncategorized")
        description = p.get("description")
        assemblies = [a for a in (row.get("assemblies") or []) if a]

        # specs: list of nodes -> dict
        specs_dict: Dict[str, Tuple[Any, str]] = {}
        for s in row.get("specs") or []:
            if not s:
                continue
            key = s.get("key")
            value = s.get("value")
            unit = s.get("unit") or ""
            if key:
                specs_dict[key] = (value, unit)

        embedding = p.get("embedding")

        parts.append(
            PartInfo(
                part_id=part_id,
                name=name,
                category=category,
                description=description,
                assemblies=assemblies,
                specs=specs_dict,
                embedding=embedding,
            )
        )

    return parts


# Scoring helpers

def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except Exception:
        return False


def _score_numeric(a: float, b: float) -> float:
    if a == 0 and b == 0:
        return 1.0
    if a == 0 or b == 0:
        return 0.0
    rel_diff = abs(a - b) / max(abs(a), abs(b))
    return max(0.0, 1.0 - rel_diff)


def _mechanical_similarity(p1: PartInfo, p2: PartInfo) -> Tuple[float, List[str]]:
    """
    Compare overlapping numeric + categorical specs.
    Return (score in [0,1], explanations)
    """
    explanations: List[str] = []
    scores: List[float] = []

    # numeric specs
    shared_keys = set(p1.specs.keys()) & set(p2.specs.keys())
    for key in shared_keys:
        v1, u1 = p1.specs[key]
        v2, u2 = p2.specs[key]

        if _is_number(v1) and _is_number(v2):
            s = _score_numeric(float(v1), float(v2))
            scores.append(s)
            explanations.append(
                f"Numeric spec '{key}' close: {v1}{u1} vs {v2}{u2} (score={s:.2f})"
            )
        else:
            if v1 == v2 and v1 is not None:
                s = 1.0
                scores.append(s)
                explanations.append(
                    f"Categorical spec '{key}' matches: {v1} (score={s:.2f})"
                )

    if not scores:
        return 0.0, ["No shared specs; mechanical similarity default 0.0"]

    avg_score = sum(scores) / len(scores)
    return avg_score, explanations


def _functional_role_similarity(p1: PartInfo, p2: PartInfo) -> Tuple[float, List[str]]:
    """
    Score based on category + known pairs.
    """
    explanations: List[str] = []

    # direct category equality
    if p1.category == p2.category:
        explanations.append(
            f"Same category '{p1.category}' for both parts (score=1.0)"
        )
        return 1.0, explanations

    score = 0.0

    # known useful pairings
    pairings = {
        ("Bearings", "Spindle"),
        ("Spindle", "Bearings"),
        ("Z Axis", "Z Axis"),
        ("X Axis", "X Axis"),
        ("Tailstock", "Tailstock"),
        ("Mold", "Mold"),
        ("Materials", "Mold"),
        ("Tools", "Mold"),
    }

    if (p1.category, p2.category) in pairings:
        score = 0.8
        explanations.append(
            f"Functional pairing between '{p1.category}' and '{p2.category}' (score=0.8)"
        )
    else:
        explanations.append(
            f"Different categories '{p1.category}' vs '{p2.category}' (score=0.0)"
        )

    return score, explanations


def _semantic_similarity(p1: PartInfo, p2: PartInfo) -> Tuple[float, List[str]]:
    """
    Cosine similarity on stored embeddings, mapped from [-1,1] to [0,1].
    """
    e1 = p1.embedding
    e2 = p2.embedding
    if not e1 or not e2:
        return 0.5, ["Missing embeddings; semantic similarity default 0.5"]

    dot = sum(float(x) * float(y) for x, y in zip(e1, e2))
    norm1 = math.sqrt(sum(float(x) * float(x) for x in e1))
    norm2 = math.sqrt(sum(float(y) * float(y) for y in e2))
    if norm1 == 0 or norm2 == 0:
        return 0.5, ["Zero-length embeddings; semantic similarity default 0.5"]

    cos = dot / (norm1 * norm2)
    score = (cos + 1.0) / 2.0  # map [-1,1] → [0,1]
    return score, [f"Embedding cosine similarity ~ {score:.2f}"]


def _hierarchy_similarity(p1: PartInfo, p2: PartInfo) -> Tuple[float, List[str]]:
    """
    Simple hierarchy-based similarity:
    - 1.0 if they share at least one Assembly
    - 0.0 otherwise
    """
    explanations: List[str] = []

    shared_assemblies = set(p1.assemblies) & set(p2.assemblies)
    if shared_assemblies:
        explanations.append(
            f"Parts share assemblies: {', '.join(shared_assemblies)} (score=1.0)"
        )
        return 1.0, explanations

    explanations.append("No shared assemblies (score=0.0)")
    return 0.0, explanations


def _combine_scores(
    mech: float, func: float, sem: float, hier: float
) -> Tuple[float, List[str]]:
    """
    Combine the four components into a single score.
    """
    # weights can be tuned
    w_mech = 0.35
    w_func = 0.25
    w_sem = 0.25
    w_hier = 0.15

    score = (
        w_mech * mech
        + w_func * func
        + w_sem * sem
        + w_hier * hier
    )
    return score, [
        f"Final score = {score:.2f} (mechanical={mech:.2f}, functional={func:.2f}, "
        f"semantic={sem:.2f}, hierarchy={hier:.2f})"
    ]


# Public API 1: Compatibility among existing parts in a Product

def compute_compatibility_for_product(product_name: str) -> None:
    """
    Compute COMPATIBLE_WITH relationships for all parts of a product.
    Writes to Neo4j: (a)-[:COMPATIBLE_WITH {score, ...}]->(b)
    """
    parts = _fetch_parts_for_product(product_name)
    part_map = {p.part_id: p for p in parts}
    ids = list(part_map.keys())

    def work(session: Session):
        for i, a_id in enumerate(ids):
            p1 = part_map[a_id]
            for b_id in ids[i + 1 :]:
                p2 = part_map[b_id]

                mech, mech_exp = _mechanical_similarity(p1, p2)
                func, func_exp = _functional_role_similarity(p1, p2)
                sem, sem_exp = _semantic_similarity(p1, p2)
                hier, hier_exp = _hierarchy_similarity(p1, p2)
                final, final_exp = _combine_scores(mech, func, sem, hier)

                explanations = mech_exp + func_exp + sem_exp + hier_exp + final_exp

                session.run(
                    """
                    MATCH (a:Part {part_id: $a_id}), (b:Part {part_id: $b_id})
                    MERGE (a)-[r:COMPATIBLE_WITH]->(b)
                    SET r.score = $score,
                        r.mechanical = $mech,
                        r.functional = $func,
                        r.semantic = $sem,
                        r.hierarchy = $hier,
                        r.explanations = $explanations
                    MERGE (b)-[r2:COMPATIBLE_WITH]->(a)
                    SET r2.score = r.score,
                        r2.mechanical = r.mechanical,
                        r2.functional = r.functional,
                        r2.semantic = r.semantic,
                        r2.hierarchy = r.hierarchy,
                        r2.explanations = r.explanations
                    """,
                    a_id=a_id,
                    b_id=b_id,
                    score=final,
                    mech=mech,
                    func=func,
                    sem=sem,
                    hier=hier,
                    explanations=explanations,
                )

                print(
                    f"{product_name}: {a_id} ↔ {b_id} score={final:.2f} "
                    f"(mech={mech:.2f}, func={func:.2f}, sem={sem:.2f}, hier={hier:.2f})"
                )

    run_write(work)
    print(f"✅ Computed COMPATIBLE_WITH for product {product_name}")


# Public API 2: Compatibility for a NEW part (not in Neo4j yet)

# Supports:
# - Natural language description (free text)
# - Optional structured specs (dict key -> {value, unit})
# - Optional category and assembly hint

def _build_virtual_part(
    description: str,
    category: Optional[str] = None,
    specs: Optional[Dict[str, Tuple[Any, str]]] = None,
    assembly_hint: Optional[str] = None,
) -> PartInfo:
    """
    Build an in-memory PartInfo for a new part, embedding computed on the fly.
    """
    emb = embed_text(description)

    assemblies: List[str] = []
    if assembly_hint:
        assemblies.append(assembly_hint)
    elif category and category in ASSEMBLY_MAP:
        assemblies.append(ASSEMBLY_MAP[category])

    return PartInfo(
        part_id="NEW_PART",
        name="New Part",
        category=category or "Unknown",
        description=description,
        assemblies=assemblies,
        specs=specs or {},
        embedding=emb,
    )


def compute_compatibility_for_new_part(
    product_name: str,
    description: str,
    category: Optional[str] = None,
    specs: Optional[Dict[str, Tuple[Any, str]]] = None,
    assembly_hint: Optional[str] = None,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """
    Compute compatibility of a NEW part (not stored in DB) against all parts
    of a product. Returns a sorted list of results (no writes to Neo4j).

    Example specs format:
        {
          "diameter": (16, "mm"),
          "pitch": (5, "mm"),
          "length": (650, "mm")
        }
    """
    existing_parts = _fetch_parts_for_product(product_name)
    new_part = _build_virtual_part(description, category, specs, assembly_hint)

    results: List[Dict[str, Any]] = []

    for p in existing_parts:
        mech, mech_exp = _mechanical_similarity(new_part, p)
        func, func_exp = _functional_role_similarity(new_part, p)
        sem, sem_exp = _semantic_similarity(new_part, p)
        hier, hier_exp = _hierarchy_similarity(new_part, p)
        final, final_exp = _combine_scores(mech, func, sem, hier)

        explanations = mech_exp + func_exp + sem_exp + hier_exp + final_exp

        results.append(
            {
                "existing_part_id": p.part_id,
                "existing_part_name": p.name,
                "existing_part_category": p.category,
                "assemblies": p.assemblies,
                "score": final,
                "mechanical": mech,
                "functional": func,
                "semantic": sem,
                "hierarchy": hier,
                "explanations": explanations,
            }
        )

    # sort descending by score, take top_k
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]
