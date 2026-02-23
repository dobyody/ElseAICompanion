# Arhitectura Else AI Companion - Extensie Moodle

## 📋 Prezentare Generală

Extensie pentru Moodle care oferă asistent AI cu acces la materialele cursului, folosind RAG (Retrieval-Augmented Generation) și Deepseek prin Ollama.

## 🏗️ Componente Principale

### 1. **Frontend - Tampermonkey Script** (`frontend/ec.js`)
- **Tehnologie**: Vanilla JavaScript (ES6+)
- **UI Framework**: Lit-HTML sau simplu DOM manipulation
- **Styling**: CSS-in-JS minimalist

#### Funcționalități:
- ✅ Chat widget flotant în colțul paginii (draggable, collapsible)
- ✅ Interfață chat simplă cu AI
- ✅ Buton pentru generare quiz cu selectarea topic-ului necesar, numarul de intrebari si complexitatea
- ✅ Progress bar pentru indexare
- ✅ Toast notifications pentru status updates

#### Integrare Moodle:
- Injectează UI-ul în orice pagină Moodle
- Extrage materiale din pagină (PDF links, text content, video URLs)
- Trimite linkul(courseid) la backend pentru indexare, si backendul prin API descarca si indexeaza

---

### 2. **Backend API** (`backend/`)
- **Framework**: **FastAPI** (Python 3.10+)
  - Simplu, rapid, async support nativ
  - Auto-documentație (Swagger UI)
  - Type hints și validare automată

#### Stack Tehnologic:
```
FastAPI         → API server
LangChain       → RAG orchestration  
Ollama          → Local LLM (deepseek-v3.1:671b-cloud)
ChromaDB        → Vector store (embedding storage)
Sentence-T.     → Text embeddings (all-MiniLM-L6-v2)
PyPDF2          → PDF parsing
BeautifulSoup4  → HTML parsing
```

#### Endpoints:
```
POST /api/index          → Indexează materiale noi
GET  /api/index/status   → Status indexare (progress %)
POST /api/chat           → Chat cu AI despre materiale
POST /api/quiz/generate  → Generează quiz din materiale
GET  /api/health         → Health check
```

---

### 3. **Sistem RAG (Retrieval-Augmented Generation)**

#### Flow:
```
1. INDEXARE:
   Material → Extragere text → Chunking (500 tokens) 
   → Embedding → Store în ChromaDB

2. CHAT:
   Query → Embedding → Similarity search în ChromaDB 
   → Top 5 chunks → Context pentru Deepseek → Răspuns

3. QUIZ GENERATION:
   Material indexat → Retrieve chunks diverse 
   → Prompt engineered → Deepseek generează quiz JSON
```

#### Storage:
```
backend/
  ├── data/
  │   ├── chroma_db/        # Vector database
  │   └── uploads/          # Materiale temporare
  └── logs/
      └── indexing.log      # Log indexare
```

---

## 📁 Structura Finală

```
ElseAICompanion/
├── frontend/
│   ├── ec.js                    # Tampermonkey script principal
│   ├── ui-components.js         # Chat UI, Toast, Progress bar
│   └── api-client.js            # Communication cu backend
│
├── backend/
│   ├── main.py                  # FastAPI app
│   ├── rag/
│   │   ├── indexer.py          # Indexare materiale
│   │   ├── retriever.py        # Retrieval din ChromaDB
│   │   └── generator.py        # Chat & Quiz generation
│   ├── parsers/
│   │   ├── pdf_parser.py       # Parse PDFs
│   │   └── html_parser.py      # Parse HTML/text
│   ├── models.py               # Pydantic models
│   ├── config.py               # Settings
│   └── requirements.txt
│
├── data/                        # Git-ignored
├── logs/                        # Git-ignored
├── .gitignore
├── README.md
└── ARCHITECTURE.md
```

---

## 🔄 Flow de Lucru

### Scenario 1: Indexare Materiale
```
1. User deschide pagină Moodle cu materiale
2. Tampermonkey script detectează materiale noi
3. Afișează buton "Index Course Materials"
4. User click → Script extrage URLs/text
5. POST /api/index cu materiale
6. Backend:
   - Download materiale
   - Parse (PDF/HTML)
   - Chunk text
   - Generate embeddings
   - Store în ChromaDB
   - Return progress real-time (SSE sau polling)
7. Frontend afișează progress bar
8. Success toast când finished
```

### Scenario 2: Chat cu AI
```
1. User deschide chat widget
2. Scrie întrebare: "Explică conceptul X din curs"
3. POST /api/chat cu query
4. Backend:
   - Embedding query
   - Retrieve top 5 relevant chunks
   - Construct prompt cu context
   - Send la Ollama/Deepseek
   - Stream response
5. Frontend afișează răspuns în timp real
```

### Scenario 3: Generare Quiz
```
1. User click "Generate Quiz"
2. POST /api/quiz/generate
3. Backend:
   - Retrieve chunks diverse din măteriale
   - Prompt: "Generate 10 multiple choice questions..."
   - Deepseek generează JSON quiz
4. Frontend afișează quiz interactiv
5. User răspunde → Frontend evaluează local
```

---

## 🔒 Securitate & Limitări

- **CORS**: Backend configurate pentru doar origin-uri Moodle cunoscute
- **Rate Limiting**: 10 req/min per user pentru chat, 2 req/min pentru indexare
- **Content Security**: Sanitizare HTML injectate
- **Privacy**: Materiale stocate doar local, nu în cloud

---

## 🚀 Avantaje Arhitectură

✅ **Simplu**: Stack minimal, dependencies clare
✅ **Robust**: FastAPI + LangChain battle-tested
✅ **Local-First**: Tot rulează pe mașina ta, no cloud costs
✅ **Extensibil**: Ușor de adăugat alte surse (YouTube transcripts, etc.)
✅ **Performant**: ChromaDB rapid, Deepseek local = latență mică

---

## 📦 Dependințe Principale

### Backend (Python):
```
fastapi==0.109.0
uvicorn==0.27.0
langchain==0.1.5
chromadb==0.4.22
sentence-transformers==2.3.1
ollama==0.1.6
pypdf2==3.0.1
beautifulsoup4==4.12.3
python-multipart==0.0.6
```

### Frontend (JavaScript):
- Pure JavaScript (no build step)
- Fetch API pentru requests
- CSS variables pentru theming

---

## ⚙️ Configurare Inițială

1. **Backend**: `pip install -r requirements.txt`
2. **Ollama**: Deja ai `deepseek-v3.1:671b-cloud`
3. **ChromaDB**: Auto-initialized la primul rulaj
4. **Tampermonkey**: Copy-paste script în browser

Server rulează pe: `http://localhost:8000`

---

## 🎯 Compromisuri Design

| Feature | Soluție Aleasă | Alternativă | Motivație |
|---------|----------------|-------------|-----------|
| Backend Framework | FastAPI | Flask | Async nativ, type safety |
| Vector DB | ChromaDB | FAISS | Persist auto, API simplu |
| Embeddings | sentence-transformers | OpenAI | Local, free, rapid |
| LLM | Ollama/Deepseek | Cloud API | Privacy, no cost |
| Frontend | Vanilla JS | React | No build step, lighter |
| UI State | LocalStorage | IndexedDB | Sufficient pentru use-case |

---

## 📊 Estimare Performanță

- **Indexare**: ~500 pagini/min (depends on material complexity)
- **Chat Latency**: 2-5s (Deepseek inference local)
- **Quiz Generation**: ~10s pentru 10 întrebări
- **Storage**: ~100MB pentru 1000 pagini (embeddings)

---

## ✅ Next Steps După Aprobare

1. Setup repository structure
2. Install backend dependencies
3. Implement core RAG system
4. Build FastAPI endpoints
5. Create Tampermonkey script
6. Test end-to-end
7. Document usage

**Durata estimată implementare**: 3-4 ore

---

**Ești de acord cu această arhitectură? Confirmă pentru a începe implementarea!**
