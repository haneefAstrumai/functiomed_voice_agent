# Functiomed Voice AI Appointment System

A fully self-hosted voice AI assistant for the **functiomed** medical clinic. Patients can speak naturally to book appointments, and staff can view all bookings in an admin dashboard. Everything runs locally — no paid cloud APIs required.

---

## Tech Stack

| Layer | Technology | Cost |
|-------|-----------|------|
| Voice server | LiveKit (self-hosted Docker) | Free |
| Speech-to-Text | Web Speech API (browser) | Free |
| Text-to-Speech | SpeechSynthesis API (browser) | Free |
| Language model | Groq (qwen3-32b) | Free tier |
| Vector search | FAISS + HuggingFace embeddings | Free (local) |
| Database | SQLite | Free |
| Backend | FastAPI (Python) | Free |
| Frontend | React + Vite | Free |
| Containers | Docker + Docker Compose | Free |

---

## Prerequisites

- Docker Desktop (v20+) — https://docs.docker.com/get-docker
- Docker Compose v2+
- A Groq API key — https://console.groq.com (free)
- Chrome or Edge browser (for Web Speech API)

---

## Quick Start

### 1. Clone and configure
```bash
git clone <your-repo-url>
cd functiomed_fastapi

cp .env.example .env
# Edit .env and set your GROQ_API_KEY
```

### 2. Start all services
```bash
docker compose up --build
```

Wait for all four services to show as running:
```
functiomed_livekit   running  0.0.0.0:7880->7880/tcp
functiomed_backend   running  0.0.0.0:8000->8000/tcp
functiomed_agent     running
functiomed_frontend  running  0.0.0.0:5173->5173/tcp
```

### 3. One-time data setup
```bash
# Scrape clinic website
curl -X GET http://localhost:8000/scrape

# Build vector index
curl -X POST http://localhost:8000/ingest
```

### 4. Open the app

| URL | Purpose |
|-----|---------|
| http://localhost:5173 | Patient voice interface |
| http://localhost:5173/admin | Staff appointment dashboard |
| http://localhost:8000/docs | FastAPI Swagger UI |

---

## Project Structure
```
functiomed_fastapi/
├── docker-compose.yml       All 4 services
├── Dockerfile               Python backend + agent
├── Dockerfile.frontend      React frontend
├── .env                     API keys (never commit)
├── main.py                  FastAPI app + REST endpoints
│
├── voice_agent/
│   ├── agent.py             LiveKit agent + state machine
│   └── state.py             Booking session + states
│
├── database/
│   ├── db.py                SQLite operations
│   └── functiomed.db        Auto-created on startup
│
├── chating/
│   └── chating.py           Groq LLM integration
│
├── embedding/
│   └── embedding.py         FAISS vector store
│
├── web_data/
│   └── web_data.py          Text chunking
│
├── pdf_data/
│   ├── pdf_data.py          PDF ingestion
│   └── files/               Drop PDFs here
│
├── data/
│   ├── clean_text/          Processed text files
│   ├── raw_html/            Scraped HTML (backup)
│   └── faiss_index/         Vector index (auto-built)
│
└── frontend/
    └── src/
        ├── App.jsx           Router
        ├── VoiceAgent.jsx    Patient voice interface
        └── Admin.jsx         Staff dashboard
```

---

## REST API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/livekit/token` | GET | Get room access token |
| `/appointments` | GET | List all appointments |
| `/appointments?date=YYYY-MM-DD` | GET | Filter by date |
| `/slots?date=YYYY-MM-DD` | GET | Check available slots |
| `/slots?date=X&service=Y` | GET | Filter by service |
| `/scrape` | GET | Scrape clinic website |
| `/ingest` | POST | Rebuild FAISS index |
| `/ingest_pdfs` | POST | Process new PDFs |
| `/agent/message` | POST | Test state machine |
| `/chat` | POST | Text chat (non-voice) |

---

## Booking Flow (Voice)
```
Patient says "I want to book" 
  → Agent asks: service → date → time → name → email → phone
  → Agent reads back full summary
  → Patient says "yes"
  → Appointment saved to SQLite
  → Agent confirms with booking ID
```

The agent is **stateful** — it remembers all collected information
across the full conversation. Saying "cancel" at any point resets
to the beginning.

---

## Adding New Content

### Add a PDF document
```bash
# Copy PDF to the files folder
cp your-document.pdf pdf_data/files/

# Process it
curl -X POST http://localhost:8000/ingest_pdfs

# Rebuild index to include it
curl -X POST http://localhost:8000/ingest
```

### Add new appointment slots

Edit `database/db.py` → `seed_slots()` to change:
- Number of days ahead
- Available times
- Services offered

Then restart the backend container:
```bash
docker compose restart backend
```

---

## Docker Commands Reference
```bash
# Start everything
docker compose up -d

# Stop everything
docker compose down

# Rebuild after code changes
docker compose up --build

# View logs
docker compose logs -f
docker compose logs -f backend
docker compose logs -f agent

# Restart one service
docker compose restart backend
docker compose restart agent

# Run a command inside a container
docker compose exec backend python -c "from database.db import get_appointments; print(get_appointments())"

# Open SQLite shell
docker compose exec backend sqlite3 database/functiomed.db
```

---

## Troubleshooting

**Agent not responding to voice messages**
```bash
# Check agent logs
docker compose logs agent --tail=50

# Restart agent
docker compose restart agent
```

**FAISS index errors on startup**
```bash
# Delete old index and rebuild
rm -rf data/faiss_index/
curl -X POST http://localhost:8000/ingest
```

**Browser STT not working**
- Use Chrome or Edge only (Firefox not supported)
- Allow microphone access when prompted
- Check `chrome://settings/content/microphone`

**LiveKit connection refused**
```bash
# Verify LiveKit is running
docker compose ps livekit
curl http://localhost:7880
```

**Database not persisting between restarts**
```bash
# Verify volume mount
docker compose exec backend ls -la database/
# Should show functiomed.db
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | required | Groq API key |
| `LIVEKIT_URL` | `ws://livekit:7880` | Internal Docker URL |
| `LIVEKIT_URL_BROWSER` | `ws://localhost:7880` | Browser-facing URL |
| `LIVEKIT_API_KEY` | `devkey` | LiveKit API key |
| `LIVEKIT_API_SECRET` | `secret` | LiveKit API secret |
| `RERANKER_ENABLED` | `0` | Enable CrossEncoder reranking (uses more RAM) |

---

## Supported Languages

The agent auto-detects the patient's language from the first message:
- **English** — full support
- **German** — full support (Deutsch)

All responses, booking prompts, and confirmations switch automatically.

---

## Browser Requirements

| Feature | Chrome | Edge | Firefox | Safari |
|---------|--------|------|---------|--------|
| Voice input (STT) | ✅ | ✅ | ❌ | ⚠️ |
| Voice output (TTS) | ✅ | ✅ | ✅ | ✅ |
| LiveKit DataChannel | ✅ | ✅ | ✅ | ✅ |

**Use Chrome or Edge for full voice functionality.**