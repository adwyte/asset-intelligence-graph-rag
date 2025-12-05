# backend/ingestion/docs_ingestor.py
import os
from typing import List, Tuple
from neo4j import Session
from pypdf import PdfReader

from ..db import run_write
from ..embeddings import embed_texts


def _read_pdf(path: str) -> str:
    reader = PdfReader(path)
    texts = []
    for page in reader.pages:
        texts.append(page.extract_text() or "")
    return "\n".join(texts)


def _chunk_text(text: str, max_tokens: int = 512) -> List[str]:
    # naive char-based chunking; good enough for demo
    chunks = []
    current = []
    count = 0
    words = text.split()
    for w in words:
        current.append(w)
        count += 1
        if count >= max_tokens:
            chunks.append(" ".join(current))
            current = []
            count = 0
    if current:
        chunks.append(" ".join(current))
    return chunks


def ingest_docs_for_root(root_dir: str) -> None:
    """
    Expects structure:
      root_dir/
        PART_ID_1/
          some_doc.pdf
        PART_ID_2/
          manual.pdf
    """
    docs: List[Tuple[str, str, str]] = []  # (part_id, file_name, text)

    for part_dir in os.listdir(root_dir):
        part_path = os.path.join(root_dir, part_dir)
        if not os.path.isdir(part_path):
            continue

        part_id = part_dir
        for fname in os.listdir(part_path):
            if not fname.lower().endswith(".pdf"):
                continue
            fpath = os.path.join(part_path, fname)
            try:
                text = _read_pdf(fpath)
            except Exception as e:
                print(f"⚠ Failed to read {fpath}: {e}")
                continue
            docs.append((part_id, fname, text))

    if not docs:
        print("No docs found for ingestion.")
        return

    # Process each doc separately
    for part_id, fname, text in docs:
        chunks = _chunk_text(text, max_tokens=256)
        embeddings = embed_texts(chunks)

        def work(session: Session) -> None:
            session.run(
                """
                MATCH (p:Part {part_id: $part_id})
                MERGE (d:Document {id: $doc_id})
                SET d.file_name = $file_name
                MERGE (p)-[:HAS_DOCUMENT]->(d)
                """,
                part_id=part_id,
                doc_id=f"{part_id}:{fname}",
                file_name=fname,
            )

            for idx, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
                session.run(
                    """
                    MATCH (d:Document {id: $doc_id})
                    MERGE (c:DocChunk {doc_id: $doc_id, chunk_index: $idx})
                    SET c.text = $text,
                        c.embedding = $embedding
                    MERGE (d)-[:HAS_CHUNK]->(c)
                    """,
                    doc_id=f"{part_id}:{fname}",
                    idx=idx,
                    text=chunk_text,
                    embedding=emb,
                )

        run_write(work)
        print(f"✅ Ingested doc {fname} for part {part_id}")
