# Else AI Companion

> An AI-powered Moodle assistant that lives in your browser — chat with your course materials, generate quizzes, and index course content, all without leaving Moodle.

https://github.com/user-attachments/assets/4fbaa3ce-e65f-485e-a3d6-da6f33078ce6

---

## What It Does

- **Chat** — ask questions about indexed course materials, answered by a local LLM using a multi-stage RAG pipeline (retrieval + re-ranking + context expansion)
- **Quiz** — generate multiple-choice quizzes from course content with configurable difficulty, topic, and question count
- **Index** — download, parse, chunk, and embed all course materials from Moodle with a single click; progress streamed in real-time via SSE

---

## Architecture

```
Browser (Tampermonkey)              Local Machine
┌──────────────────────┐            ┌─────────────────────────────────────┐
│  frontend/ec.js      │   HTTP     │  FastAPI backend (port 8000)        │
│  ────────────────    │◄──────────►│                                     │
│  • Chat UI + KaTeX   │            │  ┌───────────┐   ┌───────────────┐  │
│  • Quiz UI           │            │  │ Moodle    │   │ RAG Pipeline  │  │
│  • Index + progress  │            │  │ API       │   │               │  │
│  • Floating widget   │            │  │ client    │   │ nomic-embed   │  │
│  • Markdown render   │            │  └───────────┘   │ ChromaDB      │  │
│                      │            │                  │ Ollama LLM    │  │
└──────────────────────┘            │                  └───────────────┘  │
                                    └─────────────────────────────────────┘
```

| Layer | Technology |
|---|---|
| Frontend | Vanilla JS Tampermonkey userscript + KaTeX for math rendering |
| Backend | FastAPI 0.115 (Python 3.11+) |
| Embeddings | `nomic-embed-text` via Ollama (768 dims, multilingual) |
| Vector DB | ChromaDB (persistent, cosine similarity) |
| LLM | Ollama — `minimax-m2:cloud` (configurable) |
| HTML parsing | BeautifulSoup4 + html2text |
| PDF parsing | PyPDF2 |

---

## RAG Pipeline

The retrieval-augmented generation pipeline follows current best practices:

### Indexing
1. **Fetch** course materials from Moodle API (PDFs, pages, labels)
2. **Parse** with format-specific parsers (PyPDF2, BS4 + html2text)
3. **Chunk** with recursive text splitting (1200 chars, 200 overlap)
4. **Enrich** — prepend `[Module: X | Section: Y]` metadata before embedding (contextual enrichment — [20-67% recall boost](https://arxiv.org/abs/2407.01219))
5. **Embed** with `search_document:` prefix (nomic-embed-text best practice)
6. **Store** in ChromaDB with full metadata (module ID, section, source URL, chunk index)

### Retrieval (per query)
1. **Contextualize** — detect follow-up questions and enrich with chat history
2. **Embed** query with `search_query:` prefix
3. **Over-fetch** 3× top_k candidates from ChromaDB
4. **Filter** by configurable max cosine distance threshold
5. **Expand** — fetch neighboring chunks (N-1, N+1) for surrounding context
6. **Re-rank** with multi-signal scoring:
   - Semantic similarity (60%) — embedding distance
   - Keyword overlap (20%) — exact term matches
   - Metadata match (15%) — module/section name relevance
   - Diversity penalty (5%) — prevents all results from one module

### Generation
- Context assembled from chunks + expanded neighbors (configurable budget)
- System prompt prioritizes course materials, supplements with general knowledge when needed
- Math formulas rendered in LaTeX notation for KaTeX frontend rendering

---

## Setup

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) running locally
- [Tampermonkey](https://www.tampermonkey.net) browser extension

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Pull the required Ollama models:

```bash
ollama pull nomic-embed-text        # embedding model (768 dims)
ollama pull minimax-m2:cloud        # LLM (or any model you prefer)
```

Copy the example env and configure:

```bash
cp .env.example .env
# Edit .env — set MOODLE_TOKEN and optionally change OLLAMA_MODEL
```

Start the server:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. Frontend (Tampermonkey)

1. Open Tampermonkey dashboard → **Create new script**
2. Paste the contents of `frontend/ec.js`
3. Save — the script activates on any `else.fcim.utm.md` page

### 3. Configure `.env`

| Variable | Default | Description |
|---|---|---|
| `MOODLE_URL` | `https://else.fcim.utm.md` | Moodle instance URL |
| `MOODLE_TOKEN` | — | Moodle web service token (required) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `minimax-m2:cloud` | LLM model for chat + quiz |
| `EMBEDDING_MODEL` | `nomic-embed-text:latest` | Embedding model (via Ollama) |
| `CHUNK_SIZE` | `1200` | Characters per text chunk |
| `CHUNK_OVERLAP` | `200` | Overlap between consecutive chunks |
| `RETRIEVAL_TOP_K` | `6` | Number of chunks returned per query |
| `MAX_DISTANCE` | `0.60` | Max cosine distance threshold (0–2) |
| `NEIGHBOR_CHUNKS` | `1` | Neighboring chunks to include (0 = disabled) |
| `MAX_CONTEXT_CHARS` | `12000` | Max total context sent to LLM |
| `NUM_PREDICT_CHAT` | `2048` | Max tokens for chat responses |
| `NUM_PREDICT_QUIZ` | `4096` | Max tokens for quiz generation |

---

## Usage

1. Navigate to a Moodle course page
2. Click the floating **EC** button (bottom-right corner)
3. **Index tab** — click *Index Course* to download and embed all course materials
4. **Chat tab** — ask anything about the course (supports follow-up questions)
5. **Quiz tab** — configure difficulty/topic and generate a quiz

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check + Ollama/ChromaDB status |
| `GET` | `/api/courses` | List all indexed courses |
| `POST` | `/api/index` | Index a course (SSE progress stream) |
| `GET` | `/api/index/status/{id}` | Indexing status for a course |
| `POST` | `/api/chat` | Chat with AI (full response + sources) |
| `POST` | `/api/chat/stream` | Chat with AI (streaming SSE tokens) |
| `POST` | `/api/quiz/generate` | Generate a quiz from course materials |

---

## Project Structure

```
├── backend/
│   ├── main.py               # FastAPI app, endpoints, warmup, middleware
│   ├── config.py             # Settings via pydantic-settings (.env)
│   ├── models.py             # Pydantic request/response models
│   ├── moodle/               # Async Moodle REST API client
│   ├── parsers/
│   │   ├── html_parser.py    # HTML → clean text (BS4 + html2text)
│   │   └── pdf_parser.py     # PDF → text (PyPDF2)
│   ├── rag/
│   │   ├── indexer.py        # Moodle → chunks → contextual embeddings → ChromaDB
│   │   ├── retriever.py      # Multi-strategy retrieval + re-ranking + expansion
│   │   └── generator.py      # Chat + quiz generation via Ollama
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── ec.js                 # Tampermonkey userscript (chat, quiz, index UI)
│   └── preview.html          # Local UI preview (no Moodle needed)
├── ARCHITECTURE.md
└── README.md
```

---

## License

MIT
