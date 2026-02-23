"""
rag indexer. downloads course materials from moodle and stores them in chromadb.

flow:
  1. fetch module list from moodle api
  2. for each module → download/extract text
  3. split into chunks
  4. generate embeddings with sentence-transformers
  5. store in chromadb collection for this course

deduplication: each chunk id is 'mod_{module_id}_c{chunk_idx}'
if the module is already indexed and force_reindex is false, it gets skipped
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

from config import settings
from models import IndexProgress, IndexStatus
from moodle import (
    download_file,
    get_course_by_id,
    get_course_contents,
    get_pages_by_course,
)
from parsers.html_parser import extract_text_from_html
from parsers.pdf_parser import extract_text_from_pdf

logger = logging.getLogger(__name__)

# singletons — created once, reused everywhere
_chroma_client = None
_embedder = None
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def get_chroma() -> chromadb.PersistentClient:
    """returns the chromadb client, creates it lazily on first call"""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    return _chroma_client


def get_embedder() -> SentenceTransformer:
    """returns the embedding model, downloads and loads it lazily on first call"""
    global _embedder
    if _embedder is None:
        logger.info(f"loading embedding model: {settings.embedding_model}")
        _embedder = SentenceTransformer(settings.embedding_model)
    return _embedder


def collection_name(course_id: int) -> str:
    """naming convention for chromadb collections"""
    return f"course_{course_id}"


def get_or_create_collection(course_id: int) -> chromadb.Collection:
    """
    gets or creates the chromadb collection for a course.
    each course has its own collection so they don't interfere with each other
    """
    return get_chroma().get_or_create_collection(
        name=collection_name(course_id),
        metadata={"hnsw:space": "cosine"},
    )


def module_is_indexed(collection: chromadb.Collection, module_id: int) -> bool:
    """
    checks if a module is already stored in chromadb.
    used to skip re-indexing unless force_reindex is set
    """
    result = collection.get(
        where={"module_id": module_id},
        limit=1,
        include=[],          # we just want to know if it exists
    )
    return len(result["ids"]) > 0


def embed_and_store(
    collection: chromadb.Collection,
    module_id: int,
    module_name: str,
    section_name: str,
    source_type: str,
    source_url: str,
    text: str,
    course_id: int,
) -> int:
    """
    Splitează textul, generează embeddings şi le stochează în ChromaDB.

    Args:
        collection:   Colecţia ChromaDB a cursului
        module_id:    ID-ul modulului Moodle (cheie de deduplicare)
        module_name:  Numele afişat al modulului
        section_name: Secţiunea cursului în care se află modulul
        source_type:  'pdf', 'html', 'page' etc.
        source_url:   URL original al resursei (pentru referinţe)
        text:         Textul extras complet
        course_id:    ID-ul cursului (stocat ca metadata)

    Returns:
        Numărul de chunk-uri stocate.
    """
    if not text.strip():
        return 0

    chunks = _splitter.split_text(text)
    if not chunks:
        return 0

    embedder = get_embedder()
    embeddings = embedder.encode(chunks, show_progress_bar=False).tolist()

    ids       = [f"mod_{module_id}_c{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "course_id":    course_id,
            "module_id":    module_id,
            "module_name":  module_name,
            "section_name": section_name,
            "source_type":  source_type,
            "source_url":   source_url,
            "chunk_index":  i,
            "content_hash": hashlib.md5(chunks[i].encode()).hexdigest(),
        }
        for i in range(len(chunks))
    ]

    collection.upsert(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
    return len(chunks)


def delete_module_chunks(collection: chromadb.Collection, module_id: int) -> None:
    """deletes all chunks for a module (used when force_reindex=True)"""
    result = collection.get(where={"module_id": module_id}, include=[])
    if result["ids"]:
        collection.delete(ids=result["ids"])


# text extractor per module type─────

async def _extract_module_text(
    module: dict,
    section_name: str,
    pages_map: dict[int, str],   # instance_id → html content
) -> tuple[str, str, str]:
    """
    extracts text from a moodle module depending on its type.
    returns (text, source_type, source_url).
    - resource: downloads and parses pdf or html file
    - page: gets html from pages_map (already fetched via api)
    - label: inline description html
    - everything else: ignored
    """
    modname = module.get("modname", "")
    mod_id  = module.get("id", 0)
    mod_url = module.get("url", "")

    # ── MODULE TIP PAGE ──────────────────────────────────────────────────────
    if modname == "page":
        # Conţinutul HTML vine direct din mod_page_get_pages_by_courses
        html = pages_map.get(module.get("instance", 0), "")
        text = extract_text_from_html(html, base_url=settings.moodle_url)
        return text, "page", mod_url

    # ── MODULE TIP RESOURCE (fişier) ─────────────────────────────────────────
    if modname == "resource":
        contents = module.get("contents", [])
        for item in contents:
            if item.get("type") != "file":
                continue

            filename = item.get("filename", "")
            fileurl  = item.get("fileurl", "")
            mimetype = item.get("mimetype", "")

            # Descarcă în director temporar
            suffix = Path(filename).suffix or ".bin"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp_path = Path(tmp.name)

            try:
                await download_file(fileurl, tmp_path)

                if "pdf" in mimetype or suffix.lower() == ".pdf":
                    text = extract_text_from_pdf(tmp_path)
                    return text, "pdf", fileurl

                elif "html" in mimetype or suffix.lower() in (".htm", ".html"):
                    raw = tmp_path.read_text(errors="replace")
                    text = extract_text_from_html(raw, base_url=settings.moodle_url)
                    return text, "html", fileurl

                elif "text" in mimetype or suffix.lower() == ".txt":
                    text = tmp_path.read_text(errors="replace")
                    return text, "text", fileurl

                else:
                    logger.debug(f"unsupported type: {mimetype} ({filename}) — skipping")
                    return "", "unsupported", fileurl

            except Exception as e:
                logger.warning(f"download failed for {filename}: {e}")
                return "", "error", fileurl
            finally:
                tmp_path.unlink(missing_ok=True)

    # ── MODULE TIP LABEL (text inline) ───────────────────────────────────────
    if modname == "label":
        html = module.get("description", "")
        text = extract_text_from_html(html)
        return text, "label", mod_url

    # anything else (quiz, assignment, forum etc.) — not useful for indexing
    return "", modname, mod_url


# main indexer───

async def index_course(
    course_id: int,
    force_reindex: bool = False,
) -> AsyncGenerator[IndexProgress, None]:
    """
    async generator that indexes a course and yields progress updates.
    pipe these straight to sse and the frontend handles the rest.
    """

    def emit(status: IndexStatus, msg: str, pct: float,
             proc: int = 0, total: int = 0, chunks: int = 0) -> IndexProgress:
        p = IndexProgress(
            course_id=course_id,
            status=status,
            message=msg,
            progress=pct,
            total_chunks=chunks,
            processed_modules=proc,
            total_modules=total,
        )
        logger.info(f"[Curs {course_id}] {pct:.0f}% — {msg}")
        return p

    # step 1: validate course exists in moodle─────
    yield emit(IndexStatus.RUNNING, "Validare curs Moodle...", 2.0)
    try:
        course_info = await get_course_by_id(course_id)
    except Exception as e:
        yield emit(IndexStatus.ERROR, f"couldn't access course: {e}", 0.0)
        return

    course_name = course_info.get("fullname", f"course {course_id}")
    yield emit(IndexStatus.RUNNING, f"found course: '{course_name}'", 5.0)

    # step 2: get or create chromadb collection for this course
    collection = get_or_create_collection(course_id)

    # step 3: fetch course content from moodle
    yield emit(IndexStatus.RUNNING, "fetching course modules from moodle...", 10.0)
    try:
        sections = await get_course_contents(course_id)
        pages_list = await get_pages_by_course(course_id)
    except Exception as e:
        yield emit(IndexStatus.ERROR, f"failed to fetch course content: {e}", 0.0)
        return

    # build instance_id → html map for page modules
    pages_map: dict[int, str] = {
        p["coursemodule"]: p.get("content", "")
        for p in pages_list
    }

    # collect all indexable modules from all sections
    indexable_types = {"resource", "page", "label"}
    all_modules: list[tuple[str, dict]] = []  # (section_name, module)
    for section in sections:
        sec_name = section.get("name", "General")
        for mod in section.get("modules", []):
            if mod.get("modname") in indexable_types:
                all_modules.append((sec_name, mod))

    total = len(all_modules)
    yield emit(IndexStatus.RUNNING,
               f"found {total} modules to index...", 15.0,
               total=total)

    if total == 0:
        yield emit(IndexStatus.DONE,
                   "no indexable content found in this course", 100.0)
        return

    # step 4: index module by module
    total_chunks   = 0
    processed      = 0
    skipped        = 0

    for idx, (sec_name, mod) in enumerate(all_modules):
        mod_id   = mod.get("id", 0)
        mod_name = mod.get("name", f"module {mod_id}")
        pct      = 15.0 + (idx / total) * 80.0

        # deduplication check
        if not force_reindex and module_is_indexed(collection, mod_id):
            skipped += 1
            processed += 1
            yield emit(
                IndexStatus.RUNNING,
                f"[{idx+1}/{total}] '{mod_name}' — already indexed, skipping",
                pct, processed, total, total_chunks,
            )
            await asyncio.sleep(0)   # yield control back to event loop
            continue

        if force_reindex:
            delete_module_chunks(collection, mod_id)

        yield emit(
            IndexStatus.RUNNING,
            f"[{idx+1}/{total}] indexing '{mod_name}'...",
            pct, processed, total, total_chunks,
        )

        # extract text (may involve async download)
        text, src_type, src_url = await _extract_module_text(mod, sec_name, pages_map)

        if text.strip():
            n_chunks = embed_and_store(
                collection=collection,
                module_id=mod_id,
                module_name=mod_name,
                section_name=sec_name,
                source_type=src_type,
                source_url=src_url,
                text=text,
                course_id=course_id,
            )
            total_chunks += n_chunks
            yield emit(
                IndexStatus.RUNNING,
                f"[{idx+1}/{total}] '{mod_name}' → {n_chunks} chunks added",
                pct + 0.5, processed + 1, total, total_chunks,
            )
        else:
            yield emit(
                IndexStatus.RUNNING,
                f"[{idx+1}/{total}] no extractable text in '{mod_name}'",
                pct, processed + 1, total, total_chunks,
            )

        processed += 1
        await asyncio.sleep(0)

    # step 5: write a metadata doc so we can list indexed courses later
    meta_doc = (
        f"course: {course_name}\n"
        f"id: {course_id}\n"
        f"indexed at: {datetime.now(timezone.utc).isoformat()}\n"
        f"modules processed: {processed} (skipped: {skipped})\n"
        f"total chunks: {total_chunks}"
    )
    embedder = get_embedder()
    meta_emb = embedder.encode([meta_doc]).tolist()
    collection.upsert(
        ids=[f"_meta_course_{course_id}"],
        embeddings=meta_emb,
        documents=[meta_doc],
        metadatas=[{"course_id": course_id, "module_id": -1,
                    "is_meta": True, "course_name": course_name}],
    )

    msg = (
        f"done! {processed} modules, {total_chunks} chunks "
        f"({skipped} skipped — already indexed)"
    )
    yield emit(IndexStatus.DONE, msg, 100.0, processed, total, total_chunks)


def get_indexed_courses() -> list[dict]:
    """returns all indexed courses from chromadb. used by GET /api/courses"""
    client = get_chroma()
    result = []
    for col in client.list_collections():
        if not col.name.startswith("course_"):
            continue
        try:
            course_id = int(col.name.split("_", 1)[1])
        except ValueError:
            continue

        # Preluăm doc-ul de metadate
        meta = col.get(ids=[f"_meta_course_{course_id}"], include=["documents"])
        meta_text = meta["documents"][0] if meta["documents"] else ""

        # Număr total chunks (excluzând meta)
        total = col.count() - 1   # minus the meta doc

        result.append({
            "course_id": course_id,
            "num_chunks": max(total, 0),
            "meta": meta_text,
        })
    return result
