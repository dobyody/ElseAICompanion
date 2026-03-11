# Else AI Companion

> An AI-powered Moodle assistant that lives in your browser — enabling semantic chat and quiz generation over your indexed course materials, all running locally on your machine.

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [How It Works (Overview)](#how-it-works-overview)
3. [Installation — Step by Step](#installation--step-by-step)
   - [Step 1 — Install Ollama](#step-1--install-ollama)
   - [Step 2 — Install Python](#step-2--install-python)
   - [Step 3 — Clone the Repository](#step-3--clone-the-repository)
   - [Step 4 — Set Up the Backend](#step-4--set-up-the-backend)
   - [Step 5 — Configure Environment Variables](#step-5--configure-environment-variables)
   - [Step 6 — Start the Backend Server](#step-6--start-the-backend-server)
   - [Step 7 — Install the Browser Extension (Tampermonkey)](#step-7--install-the-browser-extension-tampermonkey)
4. [First Run — Indexing a Course](#first-run--indexing-a-course)
5. [Using Chat & Quiz](#using-chat--quiz)
6. [Configuration Reference (.env)](#configuration-reference-env)
7. [How to Get a Moodle Token](#how-to-get-a-moodle-token)
8. [API Endpoints](#api-endpoints)
9. [RAG Pipeline (Technical)](#rag-pipeline-technical)
10. [Project Structure](#project-structure)
11. [Troubleshooting](#troubleshooting)
12. [License](#license)

---

## What It Does

| Feature | Description |
|---|---|
| **Chat** | Ask any question about your course materials, get grounded answers with source references |
| **Quiz** | Instantly generate multiple-choice quizzes from indexed content |
| **Index** | Index any Moodle course (PDFs, HTML pages, resource files) directly from the browser |

Everything runs **locally** on your machine — your data and queries never leave your computer.

---

## How It Works (Overview)

```
Browser (Tampermonkey script)
         |
         | HTTP (localhost:8000)
         v
FastAPI Backend  ──► Ollama (LLM: minimax-m2:cloud)
         |
         v
    ChromaDB  ◄──── Indexed course chunks
         |
    nomic-embed-text (embeddings)
```

1. The Tampermonkey script injects a floating button on Moodle pages.
2. When you index a course, the backend downloads materials via the Moodle API, splits them into chunks, embeds them, and stores them in ChromaDB on disk.
3. When you ask a question, the backend retrieves the most relevant chunks and sends them to the local LLM (Ollama) to generate an answer.

---

## Installation — Step by Step

> **Note for absolute beginners:** Each step below explains not just *what* to do, but *why*. Take your time — the first setup takes about 15 minutes.

---

### Step 1 — Install Ollama

Ollama is the tool that runs the AI models on your machine.

1. Go to **https://ollama.com** and download the installer for your OS.
2. Install it, then **open a Terminal** (Mac/Linux) or **Command Prompt** (Windows).
3. Pull the two models the app needs:

```bash
ollama pull nomic-embed-text
ollama pull minimax-m2:cloud
```

> **What this does:** Downloads the embedding model (converts text to vectors) and the chat LLM. `minimax-m2:cloud` is large — this may take several minutes depending on your connection.

Verify Ollama is running:
```bash
ollama list
```
You should see both models listed.

---

### Step 2 — Install Python

The backend is written in Python. You need version **3.11 or newer**.

**Check if you already have it:**
```bash
python3 --version
```
If it prints `Python 3.11.x` or higher, skip to Step 3.

**Install Python:**
- **Mac:** Download from https://www.python.org/downloads/ or run `brew install python` if you have Homebrew.
- **Windows:** Download from https://www.python.org/downloads/ — during install, tick **"Add Python to PATH"**.
- **Linux (Ubuntu/Debian):** `sudo apt install python3.11 python3.11-venv`

---

### Step 3 — Clone the Repository

"Cloning" means downloading the project code from GitHub onto your machine.

**Option A — Using Git (recommended):**
```bash
git clone https://github.com/dobyody/ElseAICompanion.git
cd "ElseAICompanion"
```

**Option B — Download ZIP:**
1. Go to https://github.com/dobyody/ElseAICompanion
2. Click the green **Code** button → **Download ZIP**
3. Extract the ZIP and open a terminal in that folder.

---

### Step 4 — Set Up the Backend

> **What is a virtual environment?** A venv is an isolated Python sandbox so the packages you install here don't interfere with anything else on your machine.

Navigate into the `backend` folder first:
```bash
cd backend
```

**Create the virtual environment:**

*Mac / Linux:*
```bash
python3 -m venv ../.venv
source ../.venv/bin/activate
```

*Windows:*
```cmd
python -m venv ..\.venv
..\.venv\Scripts\activate
```

Your terminal prompt will now show `(.venv)` — that means it worked.

**Install dependencies:**
```bash
pip install -r requirements.txt
```

> This installs FastAPI, ChromaDB, and all other required libraries. Takes 1–3 minutes.

---

### Step 5 — Configure Environment Variables

Environment variables are settings stored in a `.env` file. Copy the example:

*Mac / Linux:*
```bash
cp .env.example .env
```

*Windows:*
```cmd
copy .env.example .env
```

Open `.env` in any text editor. The only field you **must** fill in is:

```
MOODLE_TOKEN=your_token_here
```

See [How to Get a Moodle Token](#how-to-get-a-moodle-token) below — it takes under 2 minutes.

All other values have sensible defaults and can be left as-is for a first run.

---

### Step 6 — Start the Backend Server

Make sure you are still inside the `backend` folder and the venv is active (you see `(.venv)` in your prompt). Then run:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

You should see output like:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

**Verify it is working** (open a new terminal tab):
```bash
curl http://localhost:8000/health
```
Expected response: `{"status":"ok"}`

> Keep this terminal open while using the app. The server must be running.

You can also explore the interactive API docs at: **http://localhost:8000/docs**

---

### Step 7 — Install the Browser Extension (Tampermonkey)

Tampermonkey is a browser extension that lets you run custom scripts on websites.

1. Install Tampermonkey for your browser:
   - **Chrome:** https://chrome.google.com/webstore/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo
   - **Firefox:** https://addons.mozilla.org/en-US/firefox/addon/tampermonkey/
   - **Edge:** https://microsoftedge.microsoft.com/addons/detail/tampermonkey/iikmkjmpaadaobahmlepeloendndfphd

2. Click the Tampermonkey icon in your browser toolbar → **Create a new script**.

3. Delete any existing template code in the editor.

4. Open the file `frontend/ec.js` from the project folder in any text editor (Notepad, VS Code, TextEdit).

5. Copy **all** the content and paste it into the Tampermonkey editor.

6. Press **Ctrl+S** (or **Cmd+S** on Mac) to save.

7. Navigate to your Moodle instance — you should see the **EC** floating button in the bottom-right corner.

---

## First Run — Indexing a Course

Before you can chat or generate quizzes, you need to index course materials.

1. Log into your Moodle instance.
2. Navigate to the course page you want to index.
3. Click the **EC** floating button (bottom-right).
4. Click the **Index** tab.
5. Click **Index Course**.
6. Wait — indexing can take **1 to 5 minutes** depending on the amount of content.
7. When complete, you'll see a confirmation message.

> The indexed data is stored locally in `backend/data/chroma_db/`. You only need to index once per course (or whenever the content changes).

---

## Using Chat & Quiz

**Chat:**
1. Open the EC panel on any Moodle page for a course you've indexed.
2. Click the **Chat** tab.
3. Type your question and press Enter.
4. The assistant answers using content from the course materials and cites sources.

**Quiz:**
1. Open the EC panel.
2. Click the **Quiz** tab.
3. Set the number of questions (default: 5).
4. Click **Generate Quiz**.
5. Answer each question — your score is shown at the end.

---

## Configuration Reference (.env)

| Variable | Default | Description |
|---|---|---|
| `MOODLE_URL` | `https://ocw.cs.pub.ro` | Base URL of your Moodle instance |
| `MOODLE_TOKEN` | *(required)* | Your Moodle web services token |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL where Ollama is running |
| `EMBEDDING_MODEL` | `nomic-embed-text:latest` | Model used for text embeddings |
| `LLM_MODEL` | `minimax-m2:cloud` | Model used for chat and quiz generation |
| `CHROMA_DB_PATH` | `./data/chroma_db` | Where ChromaDB stores indexed data |
| `CHUNK_SIZE` | `512` | Tokens per chunk when indexing |
| `CHUNK_OVERLAP` | `64` | Overlap tokens between consecutive chunks |
| `TOP_K` | `10` | Number of chunks retrieved per query |
| `MAX_CONTEXT_TOKENS` | `4096` | Maximum tokens sent to LLM as context |
| `CORS_ORIGINS` | `*` | Allowed CORS origins for the API |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`) |
| `PORT` | `8000` | Port the FastAPI server listens on |

---

## How to Get a Moodle Token

1. Log into your Moodle instance.
2. Click your **profile picture** (top-right) → **Profile**.
3. In the left sidebar, click **Preferences**.
4. Under **Security**, click **Security keys**.
5. Find the **Mobile web services** key (or create one if absent).
6. Copy the token value and paste it into your `.env` file as `MOODLE_TOKEN`.

> If you don't see "Security keys", your Moodle administrator may need to enable web services. Ask them to enable `moodle_mobile_app` web service. Or just ask your Moodle administrator to give you the token.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/index` | Index a Moodle course |
| `POST` | `/api/chat` | Chat with indexed content |
| `POST` | `/api/quiz/generate` | Generate a quiz |
| `GET` | `/api/courses` | List all indexed courses |
| `DELETE` | `/api/index/{course_id}` | Remove a course index |

Full interactive documentation (with request/response schemas and a live try-it interface) is available at:
**http://localhost:8000/docs**

---

## RAG Pipeline (Technical)

### Indexing
1. Fetch course resources from Moodle REST API.
2. Parse PDFs (PyMuPDF), HTML pages, and plain text files.
3. Split content into overlapping chunks (`CHUNK_SIZE` tokens, `CHUNK_OVERLAP` overlap).
4. Each chunk is enriched with contextual metadata (course ID, resource name, chunk position).
5. Embed chunks with `nomic-embed-text` (using `search_document:` task prefix).
6. Store vectors + metadata in ChromaDB collection keyed by course ID.

### Retrieval
1. Embed the user query with `search_query:` task prefix.
2. Retrieve top-K candidates from ChromaDB (cosine similarity).
3. Expand each result with ±1 neighboring chunks for context continuity.
4. Re-rank using multi-signal scoring (semantic similarity + keyword overlap + recency).
5. Detect follow-up queries and inject conversational context.

### Generation
1. Format retrieved chunks as a context block.
2. Build a system prompt that instructs the LLM to answer only from the provided context.
3. For quiz: prompt asks for structured JSON with questions, options, and correct indices.
4. Send to `minimax-m2:cloud` via Ollama API.
5. Parse and validate the response before returning to the frontend.

---

## Project Structure

```
ElseAICompanion/
├── backend/
│   ├── main.py              # FastAPI app, all route definitions
│   ├── config.py            # Settings loaded from .env
│   ├── requirements.txt     # Python dependencies
│   ├── .env.example         # Template for environment variables
│   └── rag/
│       ├── indexer.py       # Course ingestion, chunking, embedding, ChromaDB storage
│       ├── retriever.py     # Query embedding, vector search, re-ranking, context expansion
│       └── generator.py     # LLM prompting for chat answers and quiz generation
│   └── data/
│       └── chroma_db/       # Persistent vector store (created on first index)
└── frontend/
    └── ec.js                # Tampermonkey userscript (UI + API calls)
```

---

## Troubleshooting

**The EC button doesn't appear on Moodle**
- Make sure the Tampermonkey script is enabled (click the Tampermonkey icon — the script should have a green toggle).
- Check that the `@match` URL pattern in `ec.js` matches your Moodle domain. Edit the `// @match` line at the top of the script to match your Moodle URL (e.g., `https://moodle.youruniversity.edu/*`).

**"Connection refused" or "Network Error" in the EC panel**
- The backend server is not running. Go to the terminal where you ran `uvicorn` and check for errors, or restart it.
- Make sure you are running the server on port `8000` and your firewall isn't blocking it.

**Ollama errors / "model not found"**
- Run `ollama list` to confirm both models are downloaded.
- If missing, run `ollama pull nomic-embed-text` and/or `ollama pull minimax-m2:cloud`.
- Make sure Ollama is running (`ollama serve` or the desktop app).

**Indexing fails with a 401 or "forbidden" error**
- Your Moodle token is missing or incorrect. Re-check `.env` → `MOODLE_TOKEN`.
- See [How to Get a Moodle Token](#how-to-get-a-moodle-token).

**Chat returns "No indexed materials found"**
- You haven't indexed the course yet. Go to the **Index** tab and click **Index Course**.
- Make sure you are on the correct course page when indexing.

**Quiz generation returns an error**
- This can happen if the LLM output is malformed. Try again — the parser handles most variants but edge cases can occur.
- Check the backend terminal for the full error traceback.
- You can also test the endpoint directly at http://localhost:8000/docs → `/api/quiz/generate`.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
