"""
pydantic models for the api.
fastapi validates everything automatically so we don't have to worry about it
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


# indexing status──────────

class IndexStatus(str, Enum):
    PENDING    = "pending"
    RUNNING    = "running"
    DONE       = "done"
    ERROR      = "error"
    CACHED     = "cached"   # course was already indexed, skip


class IndexProgress(BaseModel):
    """sent over sse while indexing, so the frontend can show a progress bar"""
    course_id: int
    status: IndexStatus
    message: str
    progress: float = Field(ge=0.0, le=100.0, description="Procent 0-100")
    total_chunks: int = 0
    processed_modules: int = 0
    total_modules: int = 0


# requests─────────────

class IndexRequest(BaseModel):
    """frontend sends this to kick off indexing"""
    course_id: int = Field(..., description="moodle course id")
    # set to true to wipe and re-index everything
    force_reindex: bool = Field(default=False)


class ChatRequest(BaseModel):
    """Mesaj chat de la utilizator."""
    course_id: int = Field(..., description="ID-ul cursului pentru context RAG")
    message: str   = Field(..., min_length=1, max_length=4000)
    # Păstrăm ultimele N mesaje din conversație pentru context
    history: list[dict] = Field(default_factory=list, description="[{role, content}]")


class QuizRequest(BaseModel):
    """params for quiz generation"""
    course_id: int = Field(..., description="course id")
    topic: Optional[str]  = Field(default=None, description="specific topic (optional)")
    num_questions: int    = Field(default=10, ge=3, le=30)
    difficulty: Literal["easy", "medium", "hard"] = Field(default="medium")


# responses

class CourseInfo(BaseModel):
    """basic info about an indexed course"""
    course_id: int
    course_name: str
    num_chunks: int
    indexed_at: Optional[str] = None
    modules_indexed: int = 0


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict] = Field(default_factory=list,
                                description="[{module_name, section, chunk_preview}]")


class QuizQuestion(BaseModel):
    question: str
    options: list[str] = Field(..., min_length=4, max_length=4)
    correct_index: int  = Field(ge=0, le=3)
    explanation: str    = ""


class QuizResponse(BaseModel):
    course_id: int
    topic: Optional[str]
    questions: list[QuizQuestion]


class HealthResponse(BaseModel):
    status: str
    ollama_connected: bool
    ollama_model: str
    chroma_collections: int
