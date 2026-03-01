"""
RAG Retriever — multi-strategy retrieval with re-ranking and context expansion.

Pipeline:
  1. Contextualize query (use chat history for follow-up questions)
  2. Semantic search (embedding similarity with search_query prefix)
  3. Filter by max cosine distance (configurable)
  4. Expand context with neighboring chunks (N-1, N+1 from same module)
  5. Re-rank by combined score: similarity + keyword overlap + metadata match + diversity
  6. Return top-k results with expanded context
"""
import logging
import re
import time
from typing import Optional

from config import settings
from rag.indexer import get_embedder, get_or_create_collection

logger = logging.getLogger(__name__)


# ── Follow-up detection ────────────────────────────────────────────────────

_FOLLOWUP_MARKERS = {
    # English
    "it", "this", "that", "these", "those", "its", "the same",
    "also", "more", "why", "how", "explain", "what about",
    # Romanian
    "el", "ea", "asta", "acesta", "aceasta", "acestea", "acelasi",
    "mai", "tot", "si", "și", "dar", "despre", "la fel", "cum", "de ce",
}


def _contextualize_query(query: str, history: list[dict] | None) -> str:
    """Enriches short/follow-up queries with context from chat history.

    If the current query looks like a follow-up (short or uses pronouns/markers),
    the last user message is prepended to provide retrieval context.
    This avoids the need for an expensive LLM reformulation call.
    """
    if not history:
        return query

    query_lower = query.lower().strip()
    words = query_lower.split()

    is_followup = (
        len(words) <= 5
        or any(marker in query_lower for marker in _FOLLOWUP_MARKERS)
    )

    if not is_followup:
        return query

    # Find last user message in history
    for h in reversed(history):
        if h.get("role") == "user" and h.get("content"):
            prev = h["content"].strip()
            if prev:
                contextualized = f"{prev} — {query}"
                logger.debug(f"Query contextualized: '{query}' → '{contextualized}'")
                return contextualized

    return query


# ── Result parsing ─────────────────────────────────────────────────────────

def _parse_results(results: dict, max_distance: float) -> list[dict]:
    """Parses ChromaDB query results into structured chunk dicts, filtering by distance."""
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    ids = results.get("ids", [[]])[0]

    chunks = []
    for id_, doc, meta, dist in zip(ids, docs, metas, distances):
        if dist > max_distance:
            logger.debug(
                f"  filtered (dist={dist:.4f} > {max_distance}): "
                f"{meta.get('module_name', '')}"
            )
            continue
        chunks.append({
            "_id": id_,
            "text": doc,
            "module_id": meta.get("module_id", 0),
            "module_name": meta.get("module_name", ""),
            "section_name": meta.get("section_name", ""),
            "source_type": meta.get("source_type", ""),
            "source_url": meta.get("source_url", ""),
            "chunk_index": meta.get("chunk_index", 0),
            "chunk_total": meta.get("chunk_total", 0),
            "distance": round(dist, 4),
            "context_before": "",
            "context_after": "",
        })
    return chunks


# ── Neighbor chunk expansion ───────────────────────────────────────────────

def _expand_with_neighbors(
    collection, chunks: list[dict], n: int = 1
) -> list[dict]:
    """Fetches neighboring chunks (N-1, N+1) from the same module for richer context.

    Individual chunks often cut in the middle of important explanations.
    Neighbors complete the picture by providing surrounding text.
    Uses a single batch ChromaDB call for all neighbor IDs — very efficient.
    """
    if not chunks or n <= 0:
        return chunks

    chunk_ids = {c["_id"] for c in chunks}
    ids_to_fetch: list[str] = []

    for c in chunks:
        mod_id = c["module_id"]
        idx = c["chunk_index"]
        total = c.get("chunk_total", 0)
        for offset in range(-n, n + 1):
            if offset == 0:
                continue
            new_idx = idx + offset
            if new_idx < 0 or (total > 0 and new_idx >= total):
                continue
            nid = f"mod_{mod_id}_c{new_idx}"
            if nid not in chunk_ids:
                ids_to_fetch.append(nid)

    if not ids_to_fetch:
        return chunks

    # Single batch fetch
    try:
        result = collection.get(
            ids=list(set(ids_to_fetch)), include=["documents"]
        )
        neighbor_map = dict(zip(result["ids"], result["documents"]))
    except Exception as e:
        logger.warning(f"Neighbor expansion failed: {e}")
        return chunks

    # Attach before/after context to each chunk
    for c in chunks:
        mod_id = c["module_id"]
        idx = c["chunk_index"]

        before_parts = []
        for offset in range(n, 0, -1):
            nid = f"mod_{mod_id}_c{idx - offset}"
            if nid in neighbor_map:
                before_parts.append(neighbor_map[nid])
        c["context_before"] = "\n".join(before_parts)

        after_parts = []
        for offset in range(1, n + 1):
            nid = f"mod_{mod_id}_c{idx + offset}"
            if nid in neighbor_map:
                after_parts.append(neighbor_map[nid])
        c["context_after"] = "\n".join(after_parts)

    return chunks


# ── Re-ranking ─────────────────────────────────────────────────────────────

def _rerank(chunks: list[dict], query: str, top_k: int) -> list[dict]:
    """Re-ranks chunks using multi-signal scoring instead of pure distance.

    Signals combined:
      - Semantic similarity (from embedding distance) — primary signal (60%)
      - Keyword overlap — exact term matches matter for names/formulas (20%)
      - Metadata match — boosts chunks from modules whose names match query (15%)
      - Diversity penalty — prevents all results from same module (5%)
    """
    if not chunks:
        return chunks

    query_terms = set(re.findall(r"\w{3,}", query.lower()))
    if not query_terms:
        return chunks[:top_k]

    seen_modules: dict[str, int] = {}

    for c in chunks:
        # 1. Semantic similarity (0-1, higher = better)
        sim_score = max(0, 1.0 - c["distance"])

        # 2. Keyword overlap with chunk text (0-1)
        chunk_terms = set(re.findall(r"\w{3,}", c["text"].lower()))
        keyword_score = len(query_terms & chunk_terms) / len(query_terms)

        # 3. Metadata match — module/section name contains query terms (0-1)
        meta_text = f"{c['module_name']} {c['section_name']}".lower()
        meta_terms = set(re.findall(r"\w{3,}", meta_text))
        meta_score = len(query_terms & meta_terms) / len(query_terms)

        # 4. Diversity penalty — penalize 2nd, 3rd, ... chunk from same module
        mod_key = c["module_name"]
        mod_count = seen_modules.get(mod_key, 0)
        diversity_penalty = 0.03 * mod_count
        seen_modules[mod_key] = mod_count + 1

        # Combined score (weights tuned for educational content retrieval)
        c["_score"] = (
            sim_score * 0.60
            + keyword_score * 0.20
            + meta_score * 0.15
            - diversity_penalty
        )

    chunks.sort(key=lambda c: c["_score"], reverse=True)

    # Clean up internal fields before returning
    for c in chunks:
        c.pop("_score", None)
        c.pop("_id", None)

    return chunks[:top_k]


# ── Public API ─────────────────────────────────────────────────────────────

def retrieve(
    course_id: int,
    query: str,
    top_k: int | None = None,
    history: list[dict] | None = None,
) -> list[dict]:
    """
    Main retrieval pipeline with multi-strategy ranking and context expansion.

    Pipeline:
      1. Contextualize query (merge with history for follow-up questions)
      2. Semantic search with search_query prefix (nomic-embed-text best practice)
      3. Filter by max cosine distance (configurable via MAX_DISTANCE)
      4. Expand context with neighboring chunks (N ± NEIGHBOR_CHUNKS)
      5. Re-rank by combined score (similarity + keywords + metadata + diversity)
      6. Return top-k results

    Args:
        course_id: Moodle course ID (selects ChromaDB collection)
        query:     User's question
        top_k:     Number of results (default: settings.retrieval_top_k)
        history:   Chat history for follow-up detection

    Returns:
        List of dicts with: text, module_name, section_name, source_type,
        source_url, distance, context_before, context_after
    """
    k = top_k or settings.retrieval_top_k
    t_start = time.perf_counter()

    # ── Step 0: Get collection ─────────────────────────────────────────────
    t0 = time.perf_counter()
    collection = get_or_create_collection(course_id)
    t_col = time.perf_counter()

    count = collection.count()
    if count == 0:
        logger.warning(f"Collection for course {course_id} is empty")
        return []

    # ── Step 1: Contextualize query ────────────────────────────────────────
    retrieval_query = _contextualize_query(query, history)

    # ── Step 2: Semantic search with search_query prefix ───────────────────
    embedder = get_embedder()
    t_emb = time.perf_counter()
    query_emb = embedder.encode(
        [retrieval_query], prefix="search_query: "
    ).tolist()
    t_emb_done = time.perf_counter()

    # Fetch 3x top_k for re-ranking headroom
    fetch_k = min(k * 3, count)
    results = collection.query(
        query_embeddings=query_emb,
        n_results=fetch_k,
        where={"module_id": {"$ne": -1}},
        include=["documents", "metadatas", "distances"],
    )
    t_query = time.perf_counter()

    # ── Step 3: Filter by distance ─────────────────────────────────────────
    chunks = _parse_results(results, settings.max_distance)

    # ── Step 4: Context expansion with neighbors ───────────────────────────
    if settings.neighbor_chunks > 0 and chunks:
        chunks = _expand_with_neighbors(
            collection, chunks, settings.neighbor_chunks
        )
    t_expand = time.perf_counter()

    # ── Step 5: Re-rank ────────────────────────────────────────────────────
    chunks = _rerank(chunks, query, k)
    t_end = time.perf_counter()

    logger.info(
        f"[PERF] retrieval: col={t_col - t0:.3f}s | "
        f"embed={t_emb_done - t_emb:.3f}s | query={t_query - t_emb_done:.3f}s | "
        f"expand={t_expand - t_query:.3f}s | rerank={t_end - t_expand:.3f}s | "
        f"total={t_end - t_start:.3f}s | results={len(chunks)}/{fetch_k}"
    )

    return chunks


def course_has_data(course_id: int) -> bool:
    """Quick check if a course has anything indexed."""
    try:
        col = get_or_create_collection(course_id)
        return col.count() > 1  # more than just the meta doc
    except Exception:
        return False
