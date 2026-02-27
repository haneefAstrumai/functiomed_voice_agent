# Add this import at the top of main.py
from voice_agent.state import BookingSession, ConversationState
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse
import os, re, asyncio
from web_data.web_data import get_all_text_with_metadata
from pydantic import BaseModel
from typing import List
from embedding.embedding import build_or_load_vectorstore, retrieve
from chating.chating import ask_llm
from livekit import api as livekit_api
from database.db import init_db, seed_slots, get_appointments, get_available_slots
from dotenv import load_dotenv
#Old
# from pdf_data.pdf_data import save_pdfs_to_clean_text, load_and_chunk_pdfs
#New
from pdf_data.pdf_data import save_pdfs_to_clean_text
from web_data.web_data import get_all_text_with_metadata

import asyncio
from contextlib import asynccontextmanager


load_dotenv()

# app = FastAPI(title="Functiomed Voice AI")


# ── Replace the old @app.on_event("startup") with this ──────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs on startup
    print("\n🚀 Starting Functiomed API...")
    
    # DB init is fast — do it immediately
    init_db()
    seed_slots()
    print("✅ Database ready")

    # Heavy tasks (embedding model + FAISS) run in background
    # so the server starts accepting requests immediately
    asyncio.create_task(_load_heavy_resources())
    
    yield  # Server is running here
    
    # Runs on shutdown
    print("👋 Shutting down...")


async def _load_heavy_resources():
    """Load FAISS + embedding model in background after server starts."""
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        print("📚 Background: Loading PDFs...")
        await loop.run_in_executor(None, save_pdfs_to_clean_text)
        print("📚 Background: Building vector store...")
        await loop.run_in_executor(None, build_or_load_vectorstore)
        print("✅ Background: Vector store ready")
    except Exception as e:
        print(f"⚠️  Background loading error: {e}")
        import traceback
        traceback.print_exc()


# Update the FastAPI app to use lifespan
app = FastAPI(title="Functiomed Voice AI", lifespan=lifespan)

# -------------------------
# CORS
# -------------------------
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:5173"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

#----------------------------------For deployment-----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Directories
# -------------------------
RAW_DIR = "data/raw_html"
CLEAN_DIR = "data/clean_text"
os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(CLEAN_DIR, exist_ok=True)

# -------------------------
# URLs to scrape
# -------------------------
BASE_URL = "https://www.functiomed.ch"
visited = set()

to_visit = {
    # Homepage
    "https://www.functiomed.ch": 0,
    "https://www.functiomed.ch/en": 0,

    # Abteilung / Geschäftsleitung
    "https://www.functiomed.ch/abteilung/geschaeftsleitung": 0,
    "https://www.functiomed.ch/abteilung/empfang": 0,
    "https://www.functiomed.ch/abteilung/physiotherapie": 0,

    # Angebote
    "https://www.functiomed.ch/angebot/physiotherapie": 0,
    "https://www.functiomed.ch/en/angebot/physiotherapie-kinderphysiotherapie": 0,
    "https://www.functiomed.ch/angebot/mental-coaching": 0,
    "https://www.functiomed.ch/en/angebot/mentaltraining": 0,
    "https://www.functiomed.ch/angebot/massage": 0,
    "https://www.functiomed.ch/en/angebot/massage": 0,
    "https://www.functiomed.ch/angebot/ergotherapie": 0,
    "https://www.functiomed.ch/angebot/orthopaedie-und-traumatologie": 0,
    "https://www.functiomed.ch/en/angebot/orthopaedie-und-traumatologie_sportmedizin": 0,
    "https://www.functiomed.ch/angebot/stammzellen": 0,
    "https://www.functiomed.ch/angebot/integrative_medizin": 0,
    "https://www.functiomed.ch/en/angebot/integrative_medizin": 0,
    "https://www.functiomed.ch/angebot/infusionstherapie": 0,
    "https://www.functiomed.ch/angebot/erspe-institut-ernaehrungsdiagnostik": 0,
    "https://www.functiomed.ch/en/angebot/ernaehrungsberatung": 0,
    "https://www.functiomed.ch/angebot/numo": 0,
    "https://www.functiomed.ch/en/angebot/numo": 0,
    "https://www.functiomed.ch/angebot/fitamara-praxis-fuer-ernaehrung-und-gesundheit-in-zuerich": 0,
    "https://www.functiomed.ch/angebot/homoeopathie": 0,
    "https://www.functiomed.ch/en/angebot/homoeopathie": 0,
    "https://www.functiomed.ch/angebot/akupunktur": 0,
    "https://www.functiomed.ch/en/angebot/akupunktur": 0,
    "https://www.functiomed.ch/angebot/osteophatie-etiopathie": 0,
    "https://www.functiomed.ch/en/angebot/osteophatie-etiopathie": 0,
    "https://www.functiomed.ch/angebot/sport-osteopathie": 0,
    "https://www.functiomed.ch/en/angebot/sport-osteopathie": 0,
    "https://www.functiomed.ch/angebot/kinderosteopathie": 0,
    "https://www.functiomed.ch/en/angebot/kinderosteopathie": 0,
    "https://www.functiomed.ch/angebot/functiotraining": 0,
    "https://www.functiomed.ch/en/angebot/functiotraining": 0,
    "https://www.functiomed.ch/angebot/functiokurse": 0,
    "https://www.functiomed.ch/en/angebot/functiokurse": 0,
    "https://www.functiomed.ch/angebot/schwangerschaft": 0,
    "https://www.functiomed.ch/en/angebot/schwangerschaft": 0,
    "https://www.functiomed.ch/termin-buchen": 0,
    "https://www.functiomed.ch/en/book-appointment": 0,
    "https://www.functiomed.ch/news": 0,
    "https://www.functiomed.ch/news/spezielle-oeffnungszeiten": 0,
    "https://www.functiomed.ch/tarife": 0,
    "https://www.functiomed.ch/unsere-partner": 0,
    "https://www.functiomed.ch/unsere-functiosportler": 0,
    "https://www.functiomed.ch/news/bilderausstellung-von-leoarta-rushiti": 0,
    "https://www.functiomed.ch/ausstellungen/bilderausstellung-von-manu-ueltschi": 0,
    "https://www.functiomed.ch/gesundheitstipps/uebung-des-monats-juni": 0,
    "https://www.functiomed.ch/gesundheitstipps/uebung-des-monats-juli": 0,
    "https://www.functiomed.ch/gesundheitstipps/uebung-des-monats-mai": 0,
    "https://www.functiomed.ch/gesundheitstipps/uebung-des-monats-april": 0,
    "https://www.functiomed.ch/gesundheitstipps/uebung-des-monats-maerz": 0,
    "https://www.functiomed.ch/gesundheitstipps/uebung-des-monats-februar": 0,
    "https://www.functiomed.ch/gesundheitstipps/uebung-des-monats-januar": 0,
    "https://www.functiomed.ch/ausstellungen/bilderausstellung-von-claudia-kircher": 0,
    "https://www.functiomed.ch/shop": 0,
    "https://www.functiomed.ch/angebot/rheumatologie-innere-medizin": 0,
    "https://www.functiomed.ch/angebot/colon-hydro-therapie": 0,
    "https://www.functiomed.ch/eventontesting": 0,
    "https://www.functiomed.ch/kontakt": 0,
    "https://www.functiomed.ch/angebot/test": 0,
    "https://www.functiomed.ch/events/leichtathletik-em-rom-2024": 0,
    "https://www.functiomed.ch/notfall": 0,
    "https://www.functiomed.ch/news/world-athletics-relays-bahamas": 0,
    "https://www.functiomed.ch/ueber-die-praxis": 0,
    "https://www.functiomed.ch/sonstiges/wir-gratulieren-luisa-furrer-zum-masterdiplom-heds-fr": 0,
    "https://www.functiomed.ch/news/interview-mit-martin-spring": 0,
    "https://www.functiomed.ch/ausstellungen/bilderausstellung-von-milijana-tanovic": 0,
    "https://www.functiomed.ch/angebot/kiefertherapie": 0,
    "https://www.functiomed.ch/ausstellungen/bilderausstellung-von-annette-k": 0,
    "https://www.functiomed.ch/datenschutz": 0,
    "https://www.functiomed.ch/impressum": 0,
    "https://www.functiomed.ch/news/bilderausstellung-marcel-doerig": 0,
    "https://www.functiomed.ch/sonstiges/neue-website-online": 0,
    "https://www.functiomed.ch/demo-page": 0,
    "https://www.functiomed.ch/ueber-uns": 0,
    "https://www.functiomed.ch/privacy-policy": 0,
    "https://www.functiomed.ch/angebot": 0,
    "https://www.functiomed.ch/cookie-policy": 0,
    "https://www.functiomed.ch/videos/trainingsvideo-die-goldenen-uebungen": 0,
    "https://www.functiomed.ch/videos/vortrag-von-tamara-meier-ernaehrungsberatung": 0,
    "https://www.functiomed.ch/videos/vortrag-von-marian-leuthold-naturheilpraktikerin": 0,
    "https://www.functiomed.ch/videos/ein-schmerzfreier-ruecken": 0,
    "https://www.functiomed.ch/videos/trainingsvideo-rueckenturnen": 0,
    "https://www.functiomed.ch/videos/yoga": 0,
    "https://www.functiomed.ch/angebot/unser-engagement-functiosport": 0,
}

MAX_PAGES = len(to_visit)


# -------------------------
# Helper functions
# -------------------------
def normalize_url(url):
    parsed = urlparse(url)
    url = urlunparse(parsed._replace(fragment=""))
    if url.endswith("/") and url != BASE_URL + "/":
        url = url[:-1]
    return url.lower()

def is_valid_page(url):
    bad_ext = (".pdf", ".jpg", ".png", ".jpeg", ".svg", ".zip")
    return not url.lower().endswith(bad_ext) and "undefined" not in url

def skip_dynamic_pages(url):
    m = re.search(r"news/page/(\d+)", url)
    return m and int(m.group(1)) > 20

def clean_text(text):
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def extract_text_from_html(html):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    main = soup.find("main")
    content = main.get_text(" ") if main else soup.get_text(" ")
    return clean_text(content)


# -------------------------
# Startup: auto-load vector store + ingest PDFs
# -------------------------
vector_store = None

# @app.on_event("startup")
# def startup_event():
#     global vector_store
#     # Ensure any PDFs already in pdf_data/files/ are converted to clean_text/
#     print("\n🚀 STARTUP: Ingesting PDFs to clean_text/ ...")
#     save_pdfs_to_clean_text()
#     # Load (or build) the FAISS vector store
#     vector_store = build_or_load_vectorstore()
#     init_db()
#     seed_slots()
#     print("🚀 STARTUP complete.\n")

@app.get("/")
def root():
    return {"status": "ok", "service": "Functiomed Voice AI API"}

# -------------------------
# Scrape Endpoint
# -------------------------
@app.get("/scrape")
async def scrape_site():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        scraped_count = 0

        while to_visit:
            url, _ = to_visit.popitem()
            url = normalize_url(url)
            if url in visited or skip_dynamic_pages(url) or not is_valid_page(url):
                continue
            visited.add(url)

            print(f"Scraping ({scraped_count + 1}): {url}")

            try:
                await page.goto(url, timeout=30000)
                await page.wait_for_load_state("networkidle")
                html = await page.content()

                # Save raw HTML
                filename = url.replace("https://", "").replace("/", "_") + ".html"
                with open(os.path.join(RAW_DIR, filename), "w", encoding="utf-8") as f:
                    f.write(html)

                # Save clean text
                text = extract_text_from_html(html)
                out_file = filename.replace(".html", ".txt")
                with open(os.path.join(CLEAN_DIR, out_file), "w", encoding="utf-8") as f:
                    f.write(text)

                scraped_count += 1

            except Exception as e:
                print(f"Failed {url}: {e}")

        await browser.close()
        print(f"Scraping completed. Total pages: {scraped_count}")

    return {"status": "completed", "pages_scraped": scraped_count}


# -------------------------
# Ingest PDFs endpoint
# -------------------------
@app.post("/ingest_pdfs")
def ingest_pdfs():
    """
    Parse all PDFs in pdf_data/files/ → save as .txt in data/clean_text/.
    Call this whenever you add new PDF files.
    After this, call /ingest to rebuild the FAISS index.
    """
    result = save_pdfs_to_clean_text()
    return {
        "message": "PDF ingestion complete",
        "saved":   result["saved"],
        "skipped": result["skipped"],
        "failed":  result["failed"],
    }


# -------------------------
# Ingest (rebuild FAISS) endpoint
# -------------------------
@app.post("/ingest")
def ingest_data():
    """
    Rebuild the FAISS index from all files in data/clean_text/
    (web pages + PDF-derived .txt files).
    Run /ingest_pdfs first if you have new PDFs to add.
    """
    global vector_store
    vector_store = build_or_load_vectorstore(force_rebuild=True)
    return {"message": "Vector store rebuilt successfully from web + PDF data"}


# -------------------------
# All text (debug)
# -------------------------
@app.get("/all_text")
def all_text():
    docs = get_all_text_with_metadata()
    return {
        "total_chunks": len(docs),
        "documents": [
            {"content": doc.page_content, "metadata": doc.metadata}
            for doc in docs
        ],
    }


# -------------------------
# PDF chunks (debug / legacy)
# -------------------------
@app.get("/pdfs")
def get_pdf_chunks():
    docs = load_and_chunk_pdfs()
    return {
        "total_chunks": len(docs),
        "documents": [
            {"content": doc.page_content, "metadata": doc.metadata}
            for doc in docs
        ],
    }


# -------------------------
# Retrieve endpoint
# -------------------------
class QueryRequest(BaseModel):
    query: str
    k: int = 10

@app.post("/retrieve")
def retrieve_text(request: QueryRequest):
    global vector_store
    if vector_store is None:
        vector_store = build_or_load_vectorstore()
    results = retrieve(request.query, top_n=request.k)
    return {
        "query": request.query,
        "results": [
            {"content": doc.page_content, "metadata": doc.metadata}
            for doc in results
        ],
    }


# -------------------------
# Chat endpoint
# -------------------------
class ChatQueryRequest(BaseModel):
    query: str

@app.post("/chat")
def chat(request: ChatQueryRequest):
    try:
        answer = ask_llm(request.query)
        print(f"Answer: {answer}")
        return {"query": request.query, "answer": answer}
    except Exception as e:
        print(f"Chat error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "query": request.query,
            "answer": f"I'm sorry, something went wrong on the server. Please try again. (Error: {str(e)})",
        }


#---------------------------------Previous Endpoint for tokens------------------------------------------------------

# @app.get("/livekit/token")
# def get_livekit_token(room: str = "room-1", username: str = "patient"):
#     """
#     Generate a signed JWT token for a patient to join a LiveKit room.
#     Called by the React frontend before connecting.
#     """
#     api_key    = os.getenv("LIVEKIT_API_KEY", "devkey")
#     api_secret = os.getenv("LIVEKIT_API_SECRET", "secret")
#     livekit_url = os.getenv("LIVEKIT_URL", "ws://localhost:7880")

#     token = (
#         livekit_api.AccessToken(api_key, api_secret)
#         .with_grants(
#             livekit_api.VideoGrants(
#                 room_join=True,
#                 room=room,
#             )
#         )
#         .with_identity(username)
#         .with_name(f"Patient - {username}")
#         .to_jwt()
#     )

#     return {
#         "token": token,
#         "url": livekit_url,
#         "room": room,
#         "username": username,
#     }

#--------------------------------New Endpoint for tokens-------------------------------------------------
@app.get("/livekit/token")
def get_livekit_token(room: str = "room-1", username: str = "patient"):
    api_key    = os.getenv("LIVEKIT_API_KEY", "devkey")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "secret")

    # Browser URL — uses localhost (not the internal docker hostname)
    # Falls back to internal URL if BROWSER var not set (local dev without Docker)
    livekit_url = os.getenv("LIVEKIT_URL_BROWSER") or os.getenv("LIVEKIT_URL", "ws://localhost:7880")

    token = (
        livekit_api.AccessToken(api_key, api_secret)
        .with_grants(livekit_api.VideoGrants(room_join=True, room=room))
        .with_identity(username)
        .with_name(f"Patient - {username}")
        .to_jwt()
    )

    return {"token": token, "url": livekit_url, "room": room}


# ─────────────────────────────────────────────
# Appointments endpoints (Admin)
# ─────────────────────────────────────────────

@app.get("/appointments")
def list_appointments(date: str = None):
    """
    Return all appointments.
    Optional query param: ?date=YYYY-MM-DD to filter by date.
    """
    return {
        "appointments": get_appointments(date),
        "filter_date": date,
    }


# ─────────────────────────────────────────────
# Slots endpoint
# ─────────────────────────────────────────────

@app.get("/slots")
def list_slots(date: str, service: str = None):
    """
    Return available (unbooked) slots for a given date.
    Optional: filter by service type.
    """
    slots = get_available_slots(date, service)
    return {
        "date": date,
        "service": service,
        "available_slots": slots,
        "count": len(slots),
    }
# Add this endpoint
class TextMessage(BaseModel):
    room_id: str = "test-room"
    text: str

@app.post("/agent/message")
async def test_agent_message(msg: TextMessage):
    """
    Test endpoint — simulates sending a message to the agent.
    Lets you test the state machine without needing the voice frontend.
    """
    from voice_agent.agent import get_session, process_message

    session = get_session(msg.room_id)
    response = await process_message(msg.text, session)

    return {
        "input":    msg.text,
        "response": response,
        "state":    session.state.value,
        "session": {
            "language": session.language,
            "service":  session.service,
            "date":     session.date,
            "time":     session.time,
            "name":     session.name,
            "phone":    session.phone,
        }
    }