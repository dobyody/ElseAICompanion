# Else AI Companion

> An AI-powered Moodle assistant that lives in your browser — chat with your course materials, generate quizzes, and browse the course index, all without leaving Moodle.

https://github.com/user-attachments/assets/4fbaa3ce-e65f-485e-a3d6-da6f33078ce6

---

## What it does

- **Chat** — asks questions about indexed course materials, answered by a local LLM using RAG (only what's actually in the course, not hallucinations)
- **Quiz** — generates multiple-choice quizzes from the course content with configurable difficulty and topic
- **Index** — browse all course sections and modules directly in the widget

---

## Architecture

```
Browser (Tampermonkey)          Local Machine
┌─────────────────────┐         ┌──────────────────────────────────────┐
│  frontend/ec.js     │  HTTP   │  FastAPI backend                     │
│  ─────────────────  │◄───────►│  ┌──────────┐   ┌─────────────────┐ │
│  • Chat UI          │         │  │ Moodle   │   │ RAG Pipeline    │ │
│  • Quiz UI          │         │  │ API      │   │ sentence-transf.│ │
│  • Index browser    │         │  │ client   │   │ ChromaDB        │ │
│  • Floating widget  │         │  └──────────┘   │ Ollama (LLM)    │ │
└─────────────────────┘         │                 └─────────────────┘ │
                                └──────────────────────────────────────┘
```

| Layer | Technology |
|---|---|
| Frontend | Vanilla JS Tampermonkey userscript |
| Backend | FastAPI (Python 3.11+) |
| Embeddings | `sentence-transformers` — `all-MiniLM-L6-v2` |
| Vector DB | ChromaDB (persistent, local) |
| LLM | Ollama — `deepseek-v3.1:671b-cloud` (configurable) |
| HTML parsing | BeautifulSoup4 + html2text |
| PDF parsing | pdfminer.six |

---

## Setup

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) running locally with a model pulled (`ollama pull deepseek-v3.1:671b-cloud` or any other)
- [Tampermonkey](https://www.tampermonkey.net) browser extension installed

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy the example env file and fill in your Moodle token:

```bash
cp .env.example .env
# edit .env — set MOODLE_TOKEN and optionally OLLAMA_MODEL
```

Start the server:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend (Tampermonkey)

1. Open Tampermonkey dashboard → **Create new script**
2. Paste the contents of `frontend/ec.js`
3. Save — the script activates on any `else.fcim.utm.md` page

### 3. Configure `.env`

| Variable | Default | Description |
|---|---|---|
| `MOODLE_URL` | `https://else.fcim.utm.md` | Your Moodle instance URL |
| `MOODLE_TOKEN` | — | Moodle web service token |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `deepseek-v3.1:671b-cloud` | Model to use for chat + quiz |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model |
| `RETRIEVAL_TOP_K` | `6` | Number of chunks retrieved per query |
| `CHUNK_SIZE` | `1000` | Characters per text chunk |

---

## Usage

1. Navigate to a Moodle course page
2. Click the **EC** floating button (bottom-right)
3. **Index tab** — click *Index Course* to download and embed all course materials
4. **Chat tab** — ask anything about the course
5. **Quiz tab** — configure difficulty/topic and generate a quiz

---

## Project Structure

```
├── backend/
│   ├── main.py               # FastAPI app, all endpoints
│   ├── config.py             # Settings (pydantic-settings)
│   ├── models.py             # Pydantic request/response models
│   ├── moodle/               # Moodle REST API client
│   ├── parsers/
│   │   ├── html_parser.py    # HTML → clean text (BS4 + html2text)
│   │   └── pdf_parser.py     # PDF → text (pdfminer)
│   ├── rag/
│   │   ├── indexer.py        # Moodle → chunks → ChromaDB
│   │   ├── retriever.py      # ChromaDB cosine similarity search
│   │   └── generator.py      # Chat + quiz generation via Ollama
│   └── requirements.txt
├── frontend/
│   ├── ec.js                 # Tampermonkey userscript (all-in-one)
│   └── preview.html          # Local UI preview (no Moodle needed)
└── ARCHITECTURE.md
```

---

## License

MIT
