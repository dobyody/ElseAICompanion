"""
settings. reads from .env or env vars.
basically just defaults you can override if you want
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path

BASE_DIR = Path(__file__).parent


class Settings(BaseSettings):
    # ── Moodle ───────────────────────────────────────────────────────────────
    # URL-ul instalației Moodle target (fără slash final)
    moodle_url: str = Field(default="https://else.fcim.utm.md", alias="MOODLE_URL")
    # moodle web service token — set in .env, no default on purpose
    moodle_token: str = Field(alias="MOODLE_TOKEN")

    # ── Ollama ───────────────────────────────────────────────────────────────
    # URL-ul serverului Ollama local
    ollama_url: str = Field(default="http://localhost:11434", alias="OLLAMA_URL")
    # Modelul utilizat pentru generare (chat + quiz)
    ollama_model: str = Field(default="deepseek-v3.1:671b-cloud", alias="OLLAMA_MODEL")

    # ── ChromaDB ─────────────────────────────────────────────────────────────
    # Director unde ChromaDB persistă vectorii pe disc
    chroma_persist_dir: str = Field(
        default=str(BASE_DIR / "data" / "chroma_db"),
        alias="CHROMA_PERSIST_DIR",
    )

    # ── Embeddings (via Ollama) ──────────────────────────────────────────────
    # Model de embeddings rulat prin Ollama
    embedding_model: str = Field(
        default="nomic-embed-text:latest", alias="EMBEDDING_MODEL"
    )

    # ── RAG ──────────────────────────────────────────────────────────────────
    # Dimensiunea unui chunk de text (în caractere)
    chunk_size: int = Field(default=1200, alias="CHUNK_SIZE")
    # Suprapunerea dintre chunk-uri consecutive (caractere)
    chunk_overlap: int = Field(default=200, alias="CHUNK_OVERLAP")
    # Numărul de chunk-uri returnate la retrieval
    retrieval_top_k: int = Field(default=6, alias="RETRIEVAL_TOP_K")
    # Maximum cosine distance — chunks above this are filtered out (0=identical, 2=opposite)
    max_distance: float = Field(default=0.60, alias="MAX_DISTANCE")
    # Number of neighboring chunks to include for context expansion (0 = disabled)
    neighbor_chunks: int = Field(default=1, alias="NEIGHBOR_CHUNKS")
    # Maximum total characters of context sent to the LLM
    max_context_chars: int = Field(default=12000, alias="MAX_CONTEXT_CHARS")
    # Token generation limits for LLM responses
    num_predict_chat: int = Field(default=2048, alias="NUM_PREDICT_CHAT")
    num_predict_quiz: int = Field(default=4096, alias="NUM_PREDICT_QUIZ")

    # ── API ──────────────────────────────────────────────────────────────────
    # Port pe care rulează FastAPI
    api_port: int = Field(default=8000, alias="API_PORT")
    # Origini permise pentru CORS (separate prin virgulă)
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")

    # ── Logging ──────────────────────────────────────────────────────────────
    log_dir: str = Field(
        default=str(BASE_DIR / "logs"), alias="LOG_DIR"
    )

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"
        populate_by_name = True


settings = Settings()

# make sure all the dirs exist before anything tries to use them
Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
Path(settings.log_dir).mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data" / "downloads").mkdir(parents=True, exist_ok=True)
