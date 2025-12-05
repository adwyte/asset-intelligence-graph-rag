# backend/compatibility/scoring.py
from typing import Dict, Any, List, Tuple
import math
from neo4j import Session

from ..db import run_write
from ..embeddings import embed_text
from ..config import get_settings


def _fetch_parts_for_product(session: Session, product_name: str) -> List[Dict[str, Any]]:
    result = session.run(
        """
        MATCH (prod:Product {name: $name})-[:HAS_PART|HAS_CHILD*0..3]->(p:Part)
        RETURN DISTINCT p AS part
        """,
        name=product_name,
    )
    return [r["part"] for r in result]


def _fetch_specs_for_part(session: Session, part_id: str) -> Dict[str, Tuple[Any, str]]:
    result = session.run(
        """
        MATCH (p:Part {part_id: $part_id})-[:HAS_SPEC]->(s:Spec)
        RETURN s.key AS key, s.value AS value, s.unit AS unit
        """,
        part_id=part_id,
    )
    specs: Dict[str, Tuple[Any, str]] = {}
    for row in result:
        specs[row["key"]] = (row["value"], row["unit"])
    return specs


def _score_numeric(a: float, b: float) -> float:
    if a == 0 and b == 0:
        return 1.0
    if a == 0 or b == 0:
        return 0.0
    rel_diff = abs(a - b) / max(abs(a), abs(b))
    return max(0.0, 1.0 - rel_diff)


def _compatibility_rules(
    specs_a: Dict[str, Tuple[Any, str]],
    specs_b: Dict[str, Tuple[Any, str]],
) -> Tuple[float, List[str]]:
    """
    Very simple rules:
    - If voltage present in both: must be close
    - If shaft_diameter present: must be close
    - If power present: similarity contributes but is not hard constraint
    """
    explanations: List[str] = []
    scores: List[float] = []

    # Voltage
    if "voltage" in specs_a and "voltage" in specs_b:
        try:
            va = float(specs_a["voltage"][0])
            vb = float(specs_b["voltage"][0])
            s = _score_numeric(va, vb)
            scores.append(s)
            explanations.append(f"Voltage similarity: {va} vs {vb} (score={s:.2f})")
        except Exception:
            pass

    # Shaft diameter
    if "shaft_diameter" in specs_a and "shaft_diameter" in specs_b:
        try:
            da = float(specs_a["shaft_diameter"][0])
            db = float(specs_b["shaft_diameter"][0])
            s = _score_numeric(da, db)
            scores.append(s)
            explanations.append(f"Shaft diameter similarity: {da} vs {db} (score={s:.2f})")
        except Exception:
            pass

    # Power
    if "power" in specs_a and "power" in specs_b:
        try:
            pa = float(specs_a["power"][0])
            pb = float(specs_b["power"][0])
            s = _score_numeric(pa, pb)
            scores.append(s * 0.5)  # lower weight
            explanations.append(f"Power similarity: {pa} vs {pb} (score={s:.2f})")
        except Exception:
            pass

    if not scores:
        return 0.5, ["No matching numeric specs; default rule score 0.5"]

    avg_score = sum(scores) / len(scores)
    return avg_score, explanations


def _score_embeddings(session: Session, part_a_id: str, part_b_id: str) -> float:
    res = session.run(
        """
        MATCH (a:Part {part_id: $a}), (b:Part {part_id: $b})
        RETURN a.embedding AS ea, b.embedding AS eb
        """,
        a=part_a_id,
        b=part_b_id,
    ).single()

    if not res:
        return 0.5

    ea = res["ea"]
    eb = res["eb"]
    if not ea or not eb:
        return 0.5

    # cosine similarity
    dot = sum(x * y for x, y in zip(ea, eb))
    norm_a = math.sqrt(sum(x * x for x in ea))
    norm_b = math.sqrt(sum(y * y for y in eb))
    if norm_a == 0 or norm_b == 0:
        return 0.5
    cos = dot / (norm_a * norm_b)
    # scale from [-1,1] to [0,1]
    return (cos + 1.0) / 2.0


def compute_compatibility_for_product(product_name: str) -> None:
    def work(session: Session) -> None:
        parts = _fetch_parts_for_product(session, product_name)
        ids = [p["part_id"] for p in parts if "part_id" in p]

        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                specs_a = _fetch_specs_for_part(session, a)
                specs_b = _fetch_specs_for_part(session, b)

                rule_score, explanations = _compatibility_rules(specs_a, specs_b)
                emb_score = _score_embeddings(session, a, b)

                final_score = 0.6 * rule_score + 0.4 * emb_score
                session.run(
                    """
                    MATCH (a:Part {part_id: $a}), (b:Part {part_id: $b})
                    MERGE (a)-[r:COMPATIBLE_WITH]->(b)
                    SET r.score = $score,
                        r.rule_score = $rule_score,
                        r.emb_score = $emb_score,
                        r.explanations = $explanations
                    MERGE (b)-[r2:COMPATIBLE_WITH]->(a)
                    SET r2.score = $score,
                        r2.rule_score = $rule_score,
                        r2.emb_score = $emb_score,
                        r2.explanations = $explanations
                    """,
                    a=a,
                    b=b,
                    score=final_score,
                    rule_score=rule_score,
                    emb_score=emb_score,
                    explanations=explanations,
                )
                print(f"{product_name}: {a} ↔ {b} score={final_score:.2f}")

    run_write(work)
    print(f"✅ Computed COMPATIBLE_WITH for product {product_name}")
