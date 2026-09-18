"""Ash's self-knowledge: chunking, embedding and retrieval.

The source of truth is docs/ASH_SELF.md. It is split on Markdown headings so
each chunk is a coherent idea rather than an arbitrary window, embedded locally
with fastembed (Groq offers no embeddings API), and stored in Postgres with a
pgvector column. `search()` is what the search_self tool calls.

Rebuild the index after editing the document:

    venv/bin/python manage.py index_self
"""

import os
import re

# bge-small-en-v1.5: 384 dimensions, ~130MB, runs on CPU in milliseconds.
EMBED_MODEL = os.getenv("ASH_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIMENSIONS = 384

# A chunk aims for one section. Sections longer than this are split on
# paragraphs, carrying one paragraph of overlap so a split idea stays readable.
MAX_CHUNK_CHARS = 900
OVERLAP_PARAGRAPHS = 1

_embedder = None


def _get_embedder():
    """Load the embedding model once per process (first call downloads it)."""
    global _embedder
    if _embedder is None:
        from fastembed import TextEmbedding
        _embedder = TextEmbedding(model_name=EMBED_MODEL)
    return _embedder


def embed(texts: list) -> list:
    """Embed a list of passages. Returns one vector of floats per text."""
    return [v.tolist() for v in _get_embedder().embed(list(texts))]


def embed_query(question: str) -> list:
    """Embed a question.

    fastembed's query_embed applies whatever instruction prefix the model was
    trained with, so don't add one by hand — doing both measurably hurt
    retrieval in testing.
    """
    return list(_get_embedder().query_embed(question))[0].tolist()


def _split_long_section(body: str) -> list:
    """Split an oversized section on paragraph boundaries, with overlap."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    parts, current = [], []
    for para in paragraphs:
        candidate = "\n\n".join(current + [para])
        if current and len(candidate) > MAX_CHUNK_CHARS:
            parts.append("\n\n".join(current))
            current = current[-OVERLAP_PARAGRAPHS:] + [para]
        else:
            current.append(para)
    if current:
        parts.append("\n\n".join(current))
    return parts


def chunk_markdown(text: str) -> list:
    """Split a Markdown document into retrievable chunks.

    Each chunk carries its document title and heading as a breadcrumb, so a
    chunk retrieved on its own still says what it is about.
    """
    lines = text.splitlines()
    doc_title = next((l[2:].strip() for l in lines if l.startswith("# ")), "Ash")

    # Sections start at a level-2 heading. Anything before the first one is
    # front matter about the document itself — it describes the kinds of
    # question the document answers, so indexing it makes one chunk match
    # everything. Skipped.
    sections, heading, body = [], None, []
    for line in lines:
        if line.startswith("## "):
            sections.append((heading, "\n".join(body).strip()))
            heading, body = line[3:].strip(), []
        elif not line.startswith("# "):
            body.append(line)
    sections.append((heading, "\n".join(body).strip()))

    chunks = []
    for head, section_body in sections:
        if head is None or not section_body or section_body == "---":
            continue
        section_body = section_body.strip("-\n ").strip()
        for part in _split_long_section(section_body):
            breadcrumb = f"{doc_title} › {head}"
            # A split part often starts at a sub-heading (each failure mode is
            # one). Name it, so the chunk says which case it covers.
            sub = re.match(r"###+\s+(.+)", part)
            if sub:
                breadcrumb += f" › {sub.group(1).strip()}"
            chunks.append({
                "heading": head,
                # Shown to Ash: carries the breadcrumb so a lone chunk explains
                # itself.
                "content": f"{breadcrumb}\n\n{part}",
                # Embedded: the section name plus the body. The document title
                # is deliberately left out — repeating it in every chunk makes
                # them all look alike to the embedding model.
                "embed_text": f"{head}. {part}",
            })
    return chunks


def reindex(path: str = None) -> dict:
    """Re-chunk and re-embed the self-knowledge document.

    Idempotent: every chunk for this source is replaced, never appended.
    """
    from django.conf import settings
    from django.db import transaction
    from .models import SelfChunk

    # BASE_DIR is the backend/ directory; docs/ sits beside it in the repo.
    path = path or os.path.join(
        os.path.dirname(settings.BASE_DIR), "docs", "ASH_SELF.md"
    )
    with open(path, "r") as f:
        text = f.read()

    chunks = chunk_markdown(text)
    vectors = embed([c["embed_text"] for c in chunks])
    source = os.path.basename(path)

    with transaction.atomic():
        SelfChunk.objects.filter(source=source).delete()
        SelfChunk.objects.bulk_create([
            SelfChunk(
                source=source,
                heading=c["heading"],
                ordinal=i,
                content=c["content"],
                embedding=v,
            )
            for i, (c, v) in enumerate(zip(chunks, vectors))
        ])

    return {
        "source": source,
        "chunks": len(chunks),
        "avg_chars": sum(len(c["content"]) for c in chunks) // max(len(chunks), 1),
    }


def search(question: str, k: int = 4) -> list:
    """Nearest chunks to *question*, closest first.

    Returns dicts with heading, content and similarity (1.0 is identical).
    """
    from pgvector.django import CosineDistance
    from .models import SelfChunk

    vector = embed_query(question)
    rows = (
        SelfChunk.objects
        .annotate(distance=CosineDistance("embedding", vector))
        .order_by("distance")[:k]
    )
    return [
        {
            "heading": r.heading,
            "content": r.content,
            "similarity": round(1 - float(r.distance), 3),
        }
        for r in rows
    ]
