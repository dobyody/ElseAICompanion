"""
rag generator. handles chat and quiz generation via ollama.

chat flow: retrieve relevant chunks → build prompt with context → stream tokens back
quiz flow: retrieve diverse chunks → ask llm to return structured json → parse and validate
"""
import json
import logging
import re
import time
from typing import AsyncGenerator, Optional

import ollama

from config import settings
from models import QuizQuestion
from rag.retriever import retrieve, course_has_data

logger = logging.getLogger(__name__)


def _msg_content(part) -> str:
    """ollama 0.3.x returns dicts, 0.6.x returns objects — handle both"""
    if isinstance(part, dict):
        return part.get("message", {}).get("content", "") or ""
    return part.message.content or ""


# ── Prompt templates ─────────────────────────────────────────────────────────

SYSTEM_CHAT = """You are an AI assistant for students, specialized in course materials.
Answer ONLY based on the context provided from the course materials.
If the information is not found in the context, clearly state that you don't have information on that topic.
Answer in the same language as the question (Romanian or English).
IMPORTANT: The context may sometimes contain technical artifacts or markup fragments — ignore them completely and focus only on the readable educational content.
Be concise, precise, and helpful."""

SYSTEM_QUIZ = """You are an educational quiz generator.
You generate multiple-choice questions (4 options, one correct answer).
You respond EXCLUSIVELY with valid JSON, no additional text before or after the JSON.
Ignore any HTML, CSS or JavaScript fragments in the source material — use only readable educational text.
Respond in the same language as the request (Romanian or English). If unclear, use the course language."""


def _sanitize_chunk_text(text: str) -> str:
    """strips html tags and code-looking lines from a chunk before sending to the llm"""
    # Remove HTML tags
    text = re.sub(r"<[^>]{0,300}>", "", text)
    # Remove HTML entities
    text = re.sub(r"&(?:#?\w+);", " ", text)
    # Remove lines that look like JS/CSS code
    text = re.sub(
        r"^\s*(?:var |function |const |let |import |export |[{}();]|@media|\.[\w-]+\s*\{).*$",
        "",
        text,
        flags=re.MULTILINE,
    )
    # Collapse blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_chunk_useful(text: str) -> bool:
    """returns false if a chunk is too short or mostly html noise, not worth sending to the llm"""
    stripped = re.sub(r"\s+", " ", text).strip()
    if len(stripped) < 40:
        return False
    # If more than 15% of characters look like HTML/code noise, skip
    noise_chars = sum(1 for c in stripped if c in "<>&{}")
    if noise_chars / max(len(stripped), 1) > 0.15:
        return False
    return True


def _build_context_str(chunks: list[dict]) -> str:
    """builds the context string from retrieved chunks, skipping noise"""
    if not chunks:
        return "No indexed materials available for this course."
    parts = []
    for i, c in enumerate(chunks, 1):
        text = _sanitize_chunk_text(c["text"])
        if not _is_chunk_useful(text):
            logger.debug(f"chunk {i} skipped (noise/too short)")
            continue
        # Truncate very long chunks to avoid context overflow
        if len(text) > 1500:
            text = text[:1500] + "…"
        source = f"{c['module_name']} ({c['section_name']})"
        parts.append(f"[Source {i}: {source}]\n{text}")
    if not parts:
        return "The retrieved materials did not contain usable text for this query."
    return "\n\n---\n\n".join(parts)


# ── Chat ─────────────────────────────────────────────────────────────────────

async def chat_stream(
    course_id: int,
    message: str,
    history: list[dict],
) -> AsyncGenerator[str, None]:
    """
    async generator for streaming chat tokens.
    retrieves context from chromadb, builds prompt, streams tokens from ollama.
    """
    if not course_has_data(course_id):
        yield "⚠️ Cursul nu are materiale indexate. Indexează mai întâi materialele cursului."
        return

    # Retrieval context
    t0 = time.perf_counter()
    chunks = retrieve(course_id, message)
    t1 = time.perf_counter()
    context_str = _build_context_str(chunks)
    t2 = time.perf_counter()
    logger.info(f"[PERF] chat retrieve: {t1-t0:.3f}s | build_context: {t2-t1:.3f}s | chunks: {len(chunks)}")

    # Construieşte mesajele pentru Ollama
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_CHAT},
        {
            "role": "system",
            "content": f"Context from course materials:\n\n{context_str}",
        },
    ]

    # add last 6 turns of history (more than that and the context gets too big)
    for h in history[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})

    messages.append({"role": "user", "content": message})

    # Streaming via Ollama Python client
    try:
        client = ollama.AsyncClient(host=settings.ollama_url)
        t_llm = time.perf_counter()
        first_token = True
        async for part in await client.chat(
            model=settings.ollama_model,
            messages=messages,
            stream=True,
        ):
            token = _msg_content(part)
            if token:
                if first_token:
                    logger.info(f"[PERF] chat first token: {time.perf_counter()-t_llm:.3f}s")
                    first_token = False
                yield token
    except Exception as e:
        logger.error(f"ollama chat error: {e}")
        yield f"\n\n❌ something went wrong: {e}"


async def chat(
    course_id: int,
    message: str,
    history: list[dict],
) -> tuple[str, list[dict]]:
    """
    non-streaming chat. retrieves chunks once and reuses them for both the answer and sources list.
    """
    if not course_has_data(course_id):
        return "⚠️ course has no indexed materials. index the course first.", []

    # Single retrieval — reused for both generation and sources
    t0 = time.perf_counter()
    chunks = retrieve(course_id, message)
    t1 = time.perf_counter()
    context_str = _build_context_str(chunks)
    t2 = time.perf_counter()
    logger.info(f"[PERF] chat (non-stream) retrieve: {t1-t0:.3f}s | build_context: {t2-t1:.3f}s | chunks: {len(chunks)}")

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_CHAT},
        {"role": "system", "content": f"Context from course materials:\n\n{context_str}"},
    ]
    for h in history[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})

    full_response = ""
    try:
        client = ollama.AsyncClient(host=settings.ollama_url)
        async for part in await client.chat(
            model=settings.ollama_model,
            messages=messages,
            stream=True,
        ):
            token = _msg_content(part)
            if token:
                full_response += token
    except Exception as e:
        logger.error(f"ollama chat error: {e}")
        full_response = f"❌ something went wrong: {e}"

    # format sources for frontend (deduplicated by module name)
    seen = set()
    sources = []
    for c in chunks:
        key = c["module_name"]
        if key not in seen:
            seen.add(key)
            sources.append({
                "module_name":  c["module_name"],
                "section":      c["section_name"],
                "chunk_preview": c["text"][:150] + "...",
                "source_url":   c["source_url"],
            })

    return full_response, sources


# ── Quiz Generation ───────────────────────────────────────────────────────────

_DIFFICULTY_DESC = {
    "easy":   "simplu, factual — definiții și fapte de bază",
    "medium": "necesită înţelegere conceptuală — aplicare şi analiză",
    "hard":   "analiză şi sinteză — concepte avansate şi conexiuni",
}

_QUIZ_PROMPT_TEMPLATE = """\
Generate exactly {num_questions} multiple-choice questions based on the course material below.
Difficulty: {difficulty} — {difficulty_desc}
{topic_line}

Course material:
{context}

Respond ONLY with a valid JSON array, no markdown, no extra text:
[
  {{"question": "...", "options": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "..."}}
]
Rules: exactly 4 options per question, correct_index is 0-3, questions must be varied.
"""


async def generate_quiz(
    course_id: int,
    topic: Optional[str],
    num_questions: int,
    difficulty: str,
) -> list[QuizQuestion]:
    """
    generates a quiz from indexed course materials.
    does a broad retrieval, shuffles chunks for variety, asks ollama for json.
    throws ValueError if course isn't indexed or the model returns garbage json.
    """
    if not course_has_data(course_id):
        raise ValueError(f"Cursul {course_id} nu are materiale indexate.")

    # Retrieval diversificat — query broad sau specific pe topic
    query = topic if topic else "main content key concepts definitions theories"
    # fetch a bit more than needed for shuffling diversity, then trim
    chunks = retrieve(course_id, query, top_k=10)

    import random
    random.shuffle(chunks)
    # 6 chunks is enough context without making the prompt too long
    selected_chunks = chunks[:6]
    context_str = _build_context_str(selected_chunks)

    topic_line = f"Topic specific: {topic}" if topic else ""
    prompt = _QUIZ_PROMPT_TEMPLATE.format(
        num_questions=num_questions,
        difficulty=difficulty,
        difficulty_desc=_DIFFICULTY_DESC.get(difficulty, difficulty),
        topic_line=topic_line,
        context=context_str,
    )

    # Apel Ollama — non-streaming pentru quiz (aşteptăm JSON complet)
    try:
        client = ollama.AsyncClient(host=settings.ollama_url)
        t_quiz = time.perf_counter()
        logger.info(f"[PERF] quiz start | questions={num_questions} | chunks={len(selected_chunks)} | context_chars={len(context_str)}")
        response = await client.chat(
            model=settings.ollama_model,
            messages=[
                {"role": "system", "content": SYSTEM_QUIZ},
                {"role": "user",   "content": prompt},
            ],
            stream=False,
        )
        logger.info(f"[PERF] quiz LLM done: {time.perf_counter()-t_quiz:.3f}s")
        raw = _msg_content(response).strip()
    except Exception as e:
        raise RuntimeError(f"ollama quiz error: {e}") from e

    # deepseek sometimes wraps json in ```json ``` blocks, strip that
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"bad json from model:\n{raw[:500]}")
        raise ValueError(f"model didn't return valid json: {e}") from e

    # validate and build pydantic objects, skip bad items
    questions: list[QuizQuestion] = []
    for item in data[:num_questions]:
        try:
            questions.append(QuizQuestion(
                question=item["question"],
                options=item["options"][:4],
                correct_index=int(item["correct_index"]),
                explanation=item.get("explanation", ""),
            ))
        except Exception as e:
            logger.warning(f"skipped invalid question: {e} | {item}")

    if not questions:
        raise ValueError("model generated zero valid questions")

    return questions
