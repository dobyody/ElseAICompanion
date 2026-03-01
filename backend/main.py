"""
else ai companion — fastapi backend

endpoints:
  POST /api/index              → index a course (sse progress stream)
  GET  /api/index/status/{id}  → current indexing status
  POST /api/chat               → chat with ai (full response)
  POST /api/chat/stream        → chat with ai (streaming sse)
  POST /api/quiz/generate      → generate a quiz
  GET  /api/courses            → list indexed courses
  GET  /api/health             → health check + ollama status

run with:
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
import json
import logging
import logging.handlers
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import ollama
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from config import settings
from models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    IndexRequest,
    IndexStatus,
    QuizRequest,
    QuizResponse,
)
from rag.generator import chat, generate_quiz
from rag.indexer import get_chroma, get_indexed_courses, index_course
from rag.retriever import course_has_data

# logging setup──────────────────

def setup_logging() -> None:
    log_path = Path(settings.log_dir) / "backend.log"
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        ),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)
    # quiet down noisy libraries
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger(__name__)

# keeps track of last indexing progress per course_id
_index_status: dict[int, dict] = {}


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("Else AI Companion Backend pornit")
    logger.info(f"Ollama model: {settings.ollama_model}")
    logger.info(f"Moodle URL:   {settings.moodle_url}")
    logger.info(f"ChromaDB dir: {settings.chroma_persist_dir}")
    logger.info("=" * 60)

    # ── Warmup: preload ChromaDB + embedding model so first request is fast ──
    try:
        t0 = time.perf_counter()
        from rag.indexer import get_chroma, get_embedder
        _chroma = get_chroma()
        # Touch every existing collection so HNSW indexes load into memory
        existing = _chroma.list_collections()
        for col_name in existing:
            _chroma.get_collection(col_name if isinstance(col_name, str) else col_name.name)
        t1 = time.perf_counter()
        logger.info(f"[WARMUP] ChromaDB ready ({len(existing)} collections) in {t1-t0:.3f}s")

        t2 = time.perf_counter()
        _emb = get_embedder()
        # Warm up with search_query prefix (used in retrieval pipeline)
        _emb.encode(["warmup"], prefix="search_query: ")
        t3 = time.perf_counter()
        logger.info(f"[WARMUP] Embedder ready in {t3-t2:.3f}s")
    except Exception as e:
        logger.warning(f"[WARMUP] Warmup failed (non-fatal): {e}")

    yield
    logger.info("Backend oprit.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Else AI Companion",
    description="Backend RAG pentru extensia Moodle cu Deepseek/Ollama",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request timing middleware ─────────────────────────────────────────────────

@app.middleware("http")
async def log_request_timing(request: Request, call_next):
    """logs total duration for every request — helps spot slow endpoints"""
    t0 = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - t0
    # Only log API routes, skip static/health noise
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        logger.info(
            f"[REQUEST] {request.method} {request.url.path} → {response.status_code} "
            f"in {duration:.3f}s"
        )
    return response


# ── Helpers SSE ───────────────────────────────────────────────────────────────

def sse_event(data: dict, event: str = "progress") -> str:
    """formats an sse event string"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse, tags=["System"])
async def health():
    """
    checks if ollama is running and chromadb is accessible.
    frontend uses this to show the status dot
    """
    ollama_ok = False
    try:
        client = ollama.AsyncClient(host=settings.ollama_url)
        models_resp = await client.list()
        # ollama 0.3.x returns a plain dict: {"models": [...]}
        # ollama 0.6.x returns a ListResponse object with .models
        if isinstance(models_resp, dict):
            model_names = [m.get("model", "") or m.get("name", "") for m in models_resp.get("models", [])]
        else:
            model_names = [m.model or "" for m in (models_resp.models or [])]
        ollama_ok = any(settings.ollama_model in name for name in model_names)
    except Exception as e:
        logger.warning(f"ollama not reachable: {e}")

    try:
        chroma = get_chroma()
        n_cols = len(chroma.list_collections())
    except Exception:
        n_cols = -1

    return HealthResponse(
        status="ok" if ollama_ok else "degraded",
        ollama_connected=ollama_ok,
        ollama_model=settings.ollama_model,
        chroma_collections=n_cols,
    )


# ── Courses ───────────────────────────────────────────────────────────────────

@app.get("/api/courses", tags=["Courses"])
async def list_courses():
    """returns all courses already indexed in chromadb"""
    return {"courses": get_indexed_courses()}


# ── Index ─────────────────────────────────────────────────────────────────────

@app.post("/api/index", tags=["Index"])
async def start_index(req: IndexRequest):
    """
    starts indexing a course and streams progress via sse.
    client should read this as an eventsource.
    each event is a json IndexProgress, last event has status done or error.
    if force_reindex is false, already-indexed modules are skipped automatically
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        async for progress in index_course(req.course_id, req.force_reindex):
            data = progress.model_dump()
            _index_status[req.course_id] = data
            yield sse_event(data)
            if progress.status in (IndexStatus.DONE, IndexStatus.ERROR):
                yield sse_event(data, event="done")
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",     # disable nginx buffering
        },
    )


@app.get("/api/index/status/{course_id}", tags=["Index"])
async def index_status(course_id: int):
    """
    returns the last known indexing status for a course.
    useful for polling if the sse connection was dropped
    """
    if course_id not in _index_status:
        if course_has_data(course_id):
            return {"course_id": course_id, "status": "done", "message": "Deja indexat"}
        return {"course_id": course_id, "status": "not_started", "message": "Nicio indexare iniţiată"}
    return _index_status[course_id]


class MockIndexRequest(BaseModel):
    course_id: int
    course_name: str = "Mock Course"
    texts: list[str]   # list of raw text strings, each treated as a "module"


@app.post("/api/index/mock", tags=["Index"])
async def mock_index(req: MockIndexRequest):
    """
    [dev only] indexes arbitrary text without moodle.
    handy when moodle is down and you just want to test the rag pipeline.
    each string in 'texts' is treated as a separate module.
    """
    from rag.indexer import embed_and_store, get_or_create_collection, get_embedder
    from datetime import datetime, timezone

    collection = get_or_create_collection(req.course_id)
    total_chunks = 0

    for i, text in enumerate(req.texts):
        n = embed_and_store(
            collection=collection,
            module_id=9000 + i,
            module_name=f"Mock Module {i+1}",
            section_name="Mock Section",
            source_type="mock",
            source_url="",
            text=text,
            course_id=req.course_id,
        )
        total_chunks += n

    # Meta doc
    meta = f"Curs: {req.course_name}\nID: {req.course_id}\nIndexat: {datetime.now(timezone.utc).isoformat()}\nChunks: {total_chunks}"
    embedder = get_embedder()
    collection.upsert(
        ids=[f"_meta_course_{req.course_id}"],
        embeddings=embedder.encode([meta]).tolist(),
        documents=[meta],
        metadatas=[{"course_id": req.course_id, "module_id": -1, "is_meta": True, "course_name": req.course_name}],
    )

    logger.info(f"mock index: course {req.course_id}, {len(req.texts)} modules, {total_chunks} chunks")
    return {"course_id": req.course_id, "modules": len(req.texts), "total_chunks": total_chunks}


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse, tags=["Chat"])
async def chat_endpoint(req: ChatRequest):
    """
    non-streaming chat. returns full answer + sources.
    sources show which modules were used so the user knows where the info comes from
    """
    if not course_has_data(req.course_id):
        raise HTTPException(
            status_code=404,
            detail=f"course {req.course_id} has no indexed materials",
        )

    answer, sources = await chat(req.course_id, req.message, req.history)
    return ChatResponse(answer=answer, sources=sources)


@app.post("/api/chat/stream", tags=["Chat"])
async def chat_stream_endpoint(req: ChatRequest):
    """
    streaming chat via sse. sends partial tokens as they come in.
    event types: 'token' (text fragment), 'done' (end of stream)
    """
    from rag.generator import chat_stream

    if not course_has_data(req.course_id):
        raise HTTPException(
            status_code=404,
            detail=f"course {req.course_id} has no indexed materials",
        )

    async def event_gen() -> AsyncGenerator[str, None]:
        async for token in chat_stream(req.course_id, req.message, req.history):
            yield sse_event({"token": token}, event="token")
        yield sse_event({}, event="done")

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Quiz ──────────────────────────────────────────────────────────────────────

@app.post("/api/quiz/generate", response_model=QuizResponse, tags=["Quiz"])
async def quiz_endpoint(req: QuizRequest):
    """
    generates a quiz from indexed course materials.
    the llm returns structured json which gets validated by pydantic
    """
    if not course_has_data(req.course_id):
        raise HTTPException(
            status_code=404,
            detail=f"course {req.course_id} has no indexed materials",
        )

    try:
        questions = await generate_quiz(
            course_id=req.course_id,
            topic=req.topic,
            num_questions=req.num_questions,
            difficulty=req.difficulty,
        )
    except (ValueError, RuntimeError) as e:
        logger.warning(f"Quiz generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception(f"Quiz generation unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return QuizResponse(
        course_id=req.course_id,
        topic=req.topic,
        questions=questions,
    )


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=True,
        log_level="info",
    )
