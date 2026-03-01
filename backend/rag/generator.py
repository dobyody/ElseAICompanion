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

SYSTEM_CHAT = """You are a knowledgeable AI tutor for university students. You have access to course materials provided as context below.

RESPONSE RULES:
1. PRIORITIZE course materials — always cite specific content when available.
2. If the context fully answers the question, answer from context only.
3. If the context is incomplete, supplement with your general knowledge and mark it: “(supplementary — not from course materials)”.
4. NEVER refuse a clear academic question. Always help to the best of your ability.
5. Answer in the SAME LANGUAGE as the question (Romanian or English).
6. Be structured and clear: use headings, bullet points, and numbered lists where appropriate.
7. For math formulas, use LaTeX: inline $formula$ or display $$formula$$.
8. Ignore any HTML, CSS, JavaScript or markup artifacts in the source material."""

SYSTEM_QUIZ = """You are an educational quiz generator for university courses.
Generate multiple-choice questions with exactly 4 options (one correct answer).
Respond EXCLUSIVELY with a valid JSON array — no text, no markdown fences, no commentary.
Each question should test genuine understanding, not just word matching.
Write explanations that teach the student WHY the correct answer is right.
Ignore HTML/CSS/JavaScript fragments in the source material.
Language: match the request language (Romanian/English). If unclear, use the language of the source material."""


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
    """Builds context string from retrieved chunks with expanded neighbor context.

    Each chunk may include context_before/context_after from neighbor expansion.
    Total context is capped at settings.max_context_chars to fit LLM window.
    Chunks are sanitized and noise-filtered before inclusion.
    """
    if not chunks:
        return "No indexed materials available for this course."

    max_chars = settings.max_context_chars
    parts = []
    total_chars = 0

    for i, c in enumerate(chunks, 1):
        text = _sanitize_chunk_text(c["text"])
        if not _is_chunk_useful(text):
            logger.debug(f"chunk {i} skipped (noise/too short)")
            continue

        # Build expanded passage: context_before + main chunk + context_after
        passage_parts = []
        before = c.get("context_before", "")
        if before:
            before = _sanitize_chunk_text(before)
            if _is_chunk_useful(before):
                passage_parts.append(before)
        passage_parts.append(text)
        after = c.get("context_after", "")
        if after:
            after = _sanitize_chunk_text(after)
            if _is_chunk_useful(after):
                passage_parts.append(after)

        full_text = "\n\n".join(passage_parts)

        # Respect total context budget
        remaining = max_chars - total_chars
        if remaining <= 200:
            logger.debug(f"Context budget exhausted at chunk {i}, stopping")
            break
        if len(full_text) > remaining:
            full_text = full_text[:remaining] + "…"

        source = f"{c['module_name']} ({c['section_name']})"
        part = f"[Source {i}: {source}]\n{full_text}"
        parts.append(part)
        total_chars += len(part)

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
    chunks = retrieve(course_id, message, history=history)
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
        token_count = 0
        async for part in await client.chat(
            model=settings.ollama_model,
            messages=messages,
            stream=True,
            options={"num_predict": settings.num_predict_chat},
        ):
            token = _msg_content(part)
            if token:
                if first_token:
                    logger.info(f"[PERF] chat first token: {time.perf_counter()-t_llm:.3f}s")
                    first_token = False
                token_count += 1
                yield token
        logger.info(f"[PERF] chat LLM total: {time.perf_counter()-t_llm:.3f}s | tokens≈{token_count}")
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
    chunks = retrieve(course_id, message, history=history)
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
            options={"num_predict": settings.num_predict_chat},
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
            options={
                "num_predict": settings.num_predict_quiz,
                "temperature": 0.4,
            },
        )
        logger.info(f"[PERF] quiz LLM done: {time.perf_counter()-t_quiz:.3f}s")
        raw = _msg_content(response).strip()
    except Exception as e:
        raise RuntimeError(f"ollama quiz error: {e}") from e

    # deepseek sometimes wraps json in ```json...``` or has prose before/after — extract the array
    # Try: find the first '[' and last ']' to extract only the JSON array
    raw = re.sub(r"^```(?:json)?\s*", "", raw)  # strip opening fence if present
    raw = re.sub(r"\s*```$", "", raw)            # strip closing fence if present

    # Robustly extract the JSON array even if there's surrounding text
    match = re.search(r"(\[.*\])", raw, re.DOTALL)
    if match:
        raw = match.group(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"bad json from model:\n{raw[:500]}")
        raise ValueError(f"model didn't return valid json: {e}") from e

    # validate and build pydantic objects, skip bad items
    questions: list[QuizQuestion] = []
    for item in data[:num_questions]:
        try:
            # normalise question text — try common key variants
            q_text = (
                item.get("question") or item.get("q") or
                item.get("text") or item.get("prompt") or ""
            ).strip()
            if not q_text:
                logger.warning(f"skipped question with no text: {item}")
                continue

            # normalise options — try common key variants
            opts = (
                item.get("options") or item.get("choices") or
                item.get("answers") or item.get("variants") or []
            )
            opts = [str(o) for o in opts]  # ensure strings
            # ensure exactly 4 options
            if len(opts) > 4:
                opts = opts[:4]
            while len(opts) < 4:
                opts.append(f"— option {len(opts)+1} —")

            # normalise correct_index — handle int OR letter ("A"/"a"/"0")
            raw_idx = (
                item.get("correct_index") if item.get("correct_index") is not None
                else item.get("answer") or item.get("correct") or item.get("correct_answer") or 0
            )
            if isinstance(raw_idx, str):
                raw_idx = raw_idx.strip()
                if raw_idx.upper() in ("A", "B", "C", "D"):
                    raw_idx = ord(raw_idx.upper()) - ord("A")  # A→0, B→1 …
                else:
                    raw_idx = int(raw_idx)
            correct_idx = max(0, min(3, int(raw_idx)))  # clamp to 0-3

            questions.append(QuizQuestion(
                question=q_text,
                options=opts,
                correct_index=correct_idx,
                explanation=item.get("explanation", ""),
            ))
        except Exception as e:
            logger.warning(f"skipped invalid question: {e} | {item}")

    if not questions:
        logger.error(f"all questions were invalid, raw output was:\n{raw[:800]}")
        raise ValueError("model generated zero valid questions — check logs for raw LLM output")

    return questions
