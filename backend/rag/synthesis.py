# backend/rag/synthesis.py
from typing import Any, Dict
import textwrap

from groq import Groq

from ..config import get_settings


def _format_context(context: Dict[str, Any]) -> str:
    lines = []
    for p in context.get("parts", []):
        lines.append(f"Part: {p.get('part_id')} - {p.get('name')}")
        lines.append(f"  Category: {p.get('category')}")
        lines.append(f"  Description: {p.get('description')}")
        lines.append("  Specs:")
        for s in p.get("specs", []):
            lines.append(f"    - {s.get('key')} = {s.get('value')}{s.get('unit','')}")
        lines.append(f"  Products: {', '.join(p.get('products', []))}")
        lines.append("")

    compat = context.get("compatibility", {})
    if compat:
        lines.append("Compatibility relationships among retrieved parts:")
        for from_id, lst in compat.items():
            for rel in lst:
                lines.append(
                    f"  {from_id} ↔ {rel['to_id']}: score={rel['score']:.2f}, "
                    f"reasons={'; '.join(rel.get('explanations', []))}"
                )

    return "\n".join(lines)


def synthesize_answer(question: str, context: Dict[str, Any]) -> str:
    settings = get_settings()
    if not settings.GROQ_API_KEY:
        # fallback: just show context
        return textwrap.dedent(
            f"""
            (No LLM configured, returning raw context.)

            Question:
            {question}

            Context:
            {_format_context(context)}
            """
        ).strip()

    client = Groq(api_key=settings.GROQ_API_KEY)

    system_prompt = textwrap.dedent(
        """
        You are an asset intelligence assistant for manufacturing engineers.
        You answer questions about products, parts, specifications, and
        compatibility. Use ONLY the provided context. If something is not
        present, say you don't know.

        When suggesting reusable parts or alternatives:
        - Prefer parts with higher compatibility scores.
        - Explain WHY they are compatible (based on specs and scores).
        - Highlight any constraints or differences (e.g., voltage mismatches).
        """
    )

    user_prompt = textwrap.dedent(
        f"""
        Question:
        {question}

        Context:
        {_format_context(context)}

        Please provide a concise, clear answer suitable for an engineer.
        """
    )

    resp = client.chat.completions.create(
        model=settings.GROQ_CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()
