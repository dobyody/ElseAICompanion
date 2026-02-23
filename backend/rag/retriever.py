"""
rag retriever. queries chromadb to get the most relevant chunks for a query.
uses cosine similarity, filters out anything too distant to be useful.
"""
import logging
import time
from typing import Optional

from rag.indexer import get_embedder, get_or_create_collection

logger = logging.getLogger(__name__)


def retrieve(
    course_id: int,
    query: str,
    top_k: Optional[int] = None,
) -> list[dict]:
    """
    Returnează cele mai relevante chunk-uri pentru un query.

    Args:
        course_id: ID-ul cursului (selectează colecţia ChromaDB)
        query:     Întrebarea/query-ul utilizatorului
        top_k:     Numărul de rezultate; dacă None, foloseşte settings.retrieval_top_k

    Returns:
        Listă de dicţionare cu câmpurile:
        - text:         Conţinutul chunk-ului
        - module_name:  Numele modulului sursă
        - section_name: Secţiunea cursului
        - source_type:  Tipul sursei (pdf, page, html etc.)
        - source_url:   URL original
        - distance:     Distanţa cosinus (mai mic = mai relevant)
    """
    from config import settings as cfg
    k = top_k or cfg.retrieval_top_k

    collection = get_or_create_collection(course_id)

    if collection.count() == 0:
        logger.warning(f"collection for course {course_id} is empty")
        return []

    # embed the query
    embedder = get_embedder()
    t0 = time.perf_counter()
    query_emb = embedder.encode([query]).tolist()
    t1 = time.perf_counter()

    # query chromadb — exclude the meta doc (module_id = -1)
    results = collection.query(
        query_embeddings=query_emb,
        n_results=min(k, collection.count()),
        where={"module_id": {"$ne": -1}},       # exclude documentul meta
        include=["documents", "metadatas", "distances"],
    )
    t2 = time.perf_counter()
    logger.info(f"[PERF] embed: {t1-t0:.3f}s | chroma_query: {t2-t1:.3f}s")

    docs      = results.get("documents", [[]])[0]
    metas     = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    # filter by relevance — anything above 0.65 cosine distance is probably junk
    MAX_DISTANCE = 0.65

    output = []
    for doc, meta, dist in zip(docs, metas, distances):
        if dist > MAX_DISTANCE:
            logger.debug(f"chunk skipped (distance {dist:.4f} > {MAX_DISTANCE}): {meta.get('module_name','')}")
            continue
        output.append({
            "text":         doc,
            "module_name":  meta.get("module_name", ""),
            "section_name": meta.get("section_name", ""),
            "source_type":  meta.get("source_type", ""),
            "source_url":   meta.get("source_url", ""),
            "distance":     round(dist, 4),
        })

    logger.debug(
        f"Retrieval curs {course_id}: {len(output)} chunk-uri "
        f"(distanţe: {[r['distance'] for r in output]})"
    )
    return output


def course_has_data(course_id: int) -> bool:
    """quick check if a course has anything indexed"""
    try:
        col = get_or_create_collection(course_id)
        return col.count() > 1   # more than just the meta doc
    except Exception:
        return False
