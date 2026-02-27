from web_data.web_data import get_all_text_with_metadata
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
from sentence_transformers import CrossEncoder
import os
import shutil
import re

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
VECTOR_DB_PATH = "data/faiss_index"

# Increased threshold to filter out more irrelevant content
RELEVANCE_THRESHOLD = -2.5  # More strict than -3.5

# Fewer candidates → faster CrossEncoder, still good quality
CANDIDATE_MULTIPLIER = 4

# CrossEncoder has ~512 token limit; truncate doc text to avoid overflow/OOM
RERANKER_DOC_MAX_CHARS = 450
RERANKER_BATCH_SIZE = 8

# Set RERANKER_ENABLED=1 in env to enable CrossEncoder reranking (can cause OOM/timeout on some machines)
RERANKER_ENABLED = os.environ.get("RERANKER_ENABLED", "").strip().lower() in ("1", "true", "yes")

# ─────────────────────────────────────────────
# In-memory caches to avoid reloading heavy models/indexes every query
# ─────────────────────────────────────────────
_embedding_model = None
_vector_store_cache = None
_all_chunks_cache = None
_web_chunks_cache = None
_pdf_chunks_cache = None
_bm25_cache = None
_reranker_cache = None


# ─────────────────────────────────────────────
# Query Classification
# ─────────────────────────────────────────────

def classify_query_intent(query: str) -> str:
    """
    Detect if query is asking for:
    - 'information' (how-to, what is, services, process)
    - 'form' (registration, what documents needed)
    - 'general' (unclear/mixed)
    
    Returns: 'information', 'form', or 'general'
    """
    q_lower = query.lower()
    
    # Informational query indicators
    info_keywords = [
        'how', 'what', 'when', 'where', 'can i', 'wie kann', 
        'book', 'appointment', 'termin', 'buchen', 'contact',
        'phone', 'email', 'opening hours', 'services', 'treatment',
        'cost', 'price', 'insurance', 'process', 'procedure',
        'öffnungszeiten', 'kontakt', 'telefon', 'angebot'
    ]
    
    # Form-related query indicators
    form_keywords = [
        'registration', 'anmeldung', 'form', 'formular',
        'documents needed', 'what information', 'fill out',
        'patient form', 'which documents', 'bring to appointment'
    ]
    
    info_count = sum(1 for kw in info_keywords if kw in q_lower)
    form_count = sum(1 for kw in form_keywords if kw in q_lower)
    
    if info_count > form_count:
        return 'information'
    elif form_count > info_count:
        return 'form'
    else:
        return 'general'


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def normalize_query(query: str) -> str:
    """
    Normalize query text for BM25:
    - Lowercase
    - Collapse whitespace
    (Keeping "functiomed" helps BM25 match clinic-specific pages like contact/booking.)
    """
    q = query.strip().lower()
    q = re.sub(r"\s+", " ", q)
    return q.strip()


def load_all_chunks():
    """
    Load all chunks from data/clean_text/ (web + PDF).
    Cached in-memory so we only hit disk + splitter once.
    """
    global _all_chunks_cache, _web_chunks_cache, _pdf_chunks_cache

    if _all_chunks_cache is not None:
        return _all_chunks_cache, _web_chunks_cache, _pdf_chunks_cache

    print("\n" + "=" * 70)
    print("📚 LOADING ALL DOCUMENT CHUNKS  (web + pdf from clean_text/)")
    print("=" * 70)

    all_chunks = get_all_text_with_metadata()

    web_chunks = [c for c in all_chunks if c.metadata.get("source_type") == "web"]
    pdf_chunks = [c for c in all_chunks if c.metadata.get("source_type") == "pdf"]

    print(f"\n📊 SUMMARY:")
    print(f"    • Web chunks : {len(web_chunks):,}")
    print(f"    • PDF chunks : {len(pdf_chunks):,}")
    print(f"    • TOTAL      : {len(all_chunks):,}")
    print("=" * 70 + "\n")

    _all_chunks_cache = all_chunks
    _web_chunks_cache = web_chunks
    _pdf_chunks_cache = pdf_chunks

    return all_chunks, web_chunks, pdf_chunks


def build_or_load_vectorstore(force_rebuild: bool = False):
    """
    Build a new FAISS index or load an existing one.
    Uses in-memory cache so we don't reload the model/index on every query.
    """
    global _embedding_model, _vector_store_cache

    print("\n" + "=" * 70)
    print("🔧 VECTOR STORE INITIALIZATION")
    print("=" * 70)

    # Lazy-load embedding model once
    if _embedding_model is None:
        print("\n📦 Loading embedding model: paraphrase-multilingual-mpnet-base-v2 ...")
        _embedding_model = HuggingFaceEmbeddings(
            model_name="paraphrase-multilingual-mpnet-base-v2",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        print("    ✅ Embedding model loaded")

    # On force rebuild, drop on-disk index and in-memory cache
    if force_rebuild and os.path.exists(VECTOR_DB_PATH):
        print(f"\n🗑️  FORCE REBUILD — deleting {VECTOR_DB_PATH}")
        shutil.rmtree(VECTOR_DB_PATH)
        print("    ✅ Old index deleted")
        _vector_store_cache = None

    # If we already have an in-memory vector store and not forcing rebuild, reuse it
    if _vector_store_cache is not None and not force_rebuild:
        print("\n📂 Using cached in-memory FAISS index")
        print("=" * 70 + "\n")
        return _vector_store_cache

    try:
        if os.path.exists(VECTOR_DB_PATH) and not force_rebuild:
            print(f"\n📂 Loading existing index from {VECTOR_DB_PATH} ...")
            _vector_store_cache = FAISS.load_local(
                VECTOR_DB_PATH,
                _embedding_model,
                allow_dangerous_deserialization=True,
            )
            print("    ✅ Index loaded successfully!")
            print("=" * 70 + "\n")
            return _vector_store_cache
        else:
            raise FileNotFoundError("No index found or force rebuild requested")

    except Exception as e:
        print(f"\n🔨 BUILDING NEW FAISS INDEX")
        print(f"    Reason: {e}")

        all_docs, _, _ = load_all_chunks()

        if not all_docs:
            raise ValueError("No documents found!")

        print(f"\n🧮 Creating embeddings for {len(all_docs):,} chunks ...")
        _vector_store_cache = FAISS.from_documents(
            documents=all_docs,
            embedding=_embedding_model,
        )

        print(f"\n💾 Saving index to {VECTOR_DB_PATH} ...")
        _vector_store_cache.save_local(VECTOR_DB_PATH)
        print("    ✅ Saved!")
        print("=" * 70 + "\n")

        return _vector_store_cache


def load_reranker():
    """Load CrossEncoder reranker (cached in memory). Forces CPU to avoid OOM."""
    global _reranker_cache
    if _reranker_cache is None:
        print("\n📦 Loading CrossEncoder reranker (this may take a moment) ...")
        _reranker_cache = CrossEncoder(
            "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
            device="cpu",
        )
        print("    ✅ Reranker loaded")
    return _reranker_cache


def get_bm25(all_chunks):
    """Build BM25 retriever once and reuse it."""
    global _bm25_cache
    if _bm25_cache is None:
        print("\n📦 Building BM25 index (first query only) ...")
        _bm25_cache = BM25Retriever.from_documents(all_chunks, bm25_variant="plus")
    return _bm25_cache


def _deduplicate(docs: list) -> list:
    """Remove duplicates by page_content."""
    seen, unique = set(), []
    for doc in docs:
        key = hash(doc.page_content)
        if key not in seen:
            unique.append(doc)
            seen.add(key)
    return unique


def _heuristic_sort_when_reranker_disabled(query: str, docs: list) -> list:
    """
    Lightweight heuristic sorting used when CrossEncoder reranking is disabled.
    Helps ensure common "opening hours / availability" questions surface the
    correct page chunks (e.g., functioTraining opening hours) in the top-N.
    """
    q = (query or "").lower()
    wants_hours = any(
        t in q
        for t in (
            "opening hours",
            "open hours",
            "öffnungszeiten",
            "oeffnungszeiten",
            "when is",
            "wann",
            "available",
            "availability",
            "open",
            "geöffnet",
            "geoeffnet",
        )
    )
    if not wants_hours or not docs:
        return docs

    time_re = re.compile(r"\b\d{1,2}:\d{2}\b")

    scored = []
    for idx, doc in enumerate(docs):
        name = (
            (doc.metadata.get("page_name") or doc.metadata.get("source_pdf") or "")
            .lower()
            .strip()
        )
        content = (doc.page_content or "").lower()

        score = 0

        # Prefer the actual functioTraining pages
        if "functiotraining" in name:
            score += 12
        if "angebot_functiotraining" in name or "en_angebot_functiotraining" in name:
            score += 20

        # Prefer chunks that mention opening hours / training area hours
        if "öffnungszeiten" in content or "oeffnungszeiten" in content or "opening hours" in content:
            score += 10
        if "trainingsfläche" in content or "trainingsflaeche" in content or "trainingsfla" in content:
            score += 6

        # Prefer chunks that contain explicit time patterns
        if time_re.search(content):
            score += 3

        scored.append((score, idx, doc))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [d for _, __, d in scored]


# ─────────────────────────────────────────────
# MAIN RETRIEVAL
# ─────────────────────────────────────────────

def retrieve(query: str, top_n: int = 6) -> list:
    """
    Query-aware adaptive retrieval:
    - Detects query intent (information vs form)
    - For information queries: Heavily boosts web content
    - For form queries: Allows more PDF content
    - Uses strict relevance filtering
    """
    try:
        print("\n" + "=" * 70)
        print("🔍 QUERY-AWARE ADAPTIVE RETRIEVAL")
        print("=" * 70)
        print(f"Original query  : '{query}'")

        # Classify query intent
        intent = classify_query_intent(query)
        print(f"Query intent    : {intent.upper()}")
        
        # Set additive boost based on intent
        if intent == 'information':
            web_boost = 3.0  # Strong additive boost for web chunks
            print(f"Strategy        : INFORMATION → Additive web boost +3.0")
        elif intent == 'form':
            web_boost = 0.0  # Neutral for form-related questions
            print(f"Strategy        : FORM → Neutral (no web boost)")
        else:
            web_boost = 1.5  # Moderate additive boost
            print(f"Strategy        : GENERAL → Additive web boost +1.5")

        normalized_q = normalize_query(query)
        print(f"Normalized query: '{normalized_q}'")
        print(f"Target          : {top_n} docs  |  Threshold: {RELEVANCE_THRESHOLD}")

        # Load resources
        vector_store = build_or_load_vectorstore()
        all_chunks, web_chunks, pdf_chunks = load_all_chunks()

        n_candidates = top_n * CANDIDATE_MULTIPLIER
        print(f"\n📊 Available: {len(web_chunks)} web  |  {len(pdf_chunks)} PDF")
        print(f"    Fetching {n_candidates} candidates from each retriever")

        # STEP 1: FAISS
        print(f"\n🔹 STEP 1: FAISS Semantic Search  (k={n_candidates})")
        faiss_retriever = vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": n_candidates},
        )
        faiss_docs = faiss_retriever.invoke(query)
        faiss_web = [d for d in faiss_docs if d.metadata.get("source_type") == "web"]
        faiss_pdf = [d for d in faiss_docs if d.metadata.get("source_type") == "pdf"]
        print(f"    Retrieved: {len(faiss_web)} web  |  {len(faiss_pdf)} PDF")

        # STEP 2: BM25
        print(f"\n🔹 STEP 2: BM25 Keyword Search  (k={n_candidates})")
        bm25 = get_bm25(all_chunks)
        bm25.k = n_candidates
        bm25_docs = bm25.invoke(normalized_q)
        bm25_web = [d for d in bm25_docs if d.metadata.get("source_type") == "web"]
        bm25_pdf = [d for d in bm25_docs if d.metadata.get("source_type") == "pdf"]
        print(f"    Retrieved: {len(bm25_web)} web  |  {len(bm25_pdf)} PDF")

        # STEP 3: Combine
        print(f"\n🔹 STEP 3: Combine & Deduplicate")
        combined = _deduplicate(faiss_docs + bm25_docs)
        print(f"    Unique candidates: {len(combined)}")

        if not combined:
            print("    ⚠️  No candidates found.")
            return []

        # STEP 4: Rerank (optional; disable to avoid OOM/timeout — set RERANKER_ENABLED=1 to enable)
        if not RERANKER_ENABLED:
            print(f"\n🔹 STEP 4: Reranking disabled — using combined order for top {top_n}")
            combined = _heuristic_sort_when_reranker_disabled(query, combined)
            final_docs = combined[:top_n]
            actual_web = sum(1 for d in final_docs if d.metadata.get("source_type") == "web")
            actual_pdf = sum(1 for d in final_docs if d.metadata.get("source_type") == "pdf")
            print(f"\n📊 FINAL RESULTS:")
            print("=" * 70)
            print(f"    • Web  : {actual_web}")
            print(f"    • PDF  : {actual_pdf}")
            print(f"    • Total: {len(final_docs)} (target: {top_n})")
            for i, doc in enumerate(final_docs, 1):
                stype = doc.metadata.get("source_type", "?")
                icon = "🌐" if stype == "web" else "📑"
                name = doc.metadata.get("page_name") or doc.metadata.get("source_pdf", "Unknown")
                print(f"\n    {i}. {icon} [{stype.upper()}] {name}")
                print(f"       Preview: {doc.page_content[:100]}...")
            print("\n" + "=" * 70 + "\n")
            return final_docs

        print(f"\n🔹 STEP 4: CrossEncoder Reranking with Intent-Based Boost")
        reranker = load_reranker()
        # Truncate long docs so CrossEncoder input stays within model limits
        def _truncate_for_rerank(text: str) -> str:
            if not text or not text.strip():
                return " "
            text = text.strip()
            if len(text) <= RERANKER_DOC_MAX_CHARS:
                return text
            return text[: RERANKER_DOC_MAX_CHARS].rsplit(" ", 1)[0] or text[: RERANKER_DOC_MAX_CHARS]

        pairs = [[query, _truncate_for_rerank(doc.page_content)] for doc in combined]

        try:
            scores = []
            for i in range(0, len(pairs), RERANKER_BATCH_SIZE):
                batch = pairs[i : i + RERANKER_BATCH_SIZE]
                scores.extend(reranker.predict(batch))
        except Exception as rerank_err:
            print(f"    ⚠️  Reranker failed: {rerank_err} — using combined order for top {top_n}")
            combined = _heuristic_sort_when_reranker_disabled(query, combined)
            final_docs = combined[:top_n]
            actual_web = sum(1 for d in final_docs if d.metadata.get("source_type") == "web")
            actual_pdf = sum(1 for d in final_docs if d.metadata.get("source_type") == "pdf")
            print(f"\n📊 FINAL RESULTS (fallback): Web {actual_web}  |  PDF {actual_pdf}  |  Total {len(final_docs)}")
            print("=" * 70 + "\n")
            return final_docs

        # Apply web boost (additive so higher = better, even when scores are negative)
        boosted_scores = []
        for doc, score in zip(combined, scores):
            if doc.metadata.get("source_type") == "web":
                boosted_score = score + web_boost
            else:
                boosted_score = score
            boosted_scores.append(boosted_score)

        ranked = sorted(
            zip(combined, boosted_scores, scores),  # Keep original scores
            key=lambda x: x[1],  # Sort by boosted score
            reverse=True
        )
        
        print(f"    Original score range: {max(scores):.4f} → {min(scores):.4f}")
        print(f"    Boosted score range:  {max(boosted_scores):.4f} → {min(boosted_scores):.4f}")

        # STEP 5: Threshold filter
        print(f"\n🔹 STEP 5: Relevance Filter (boosted >= {RELEVANCE_THRESHOLD})")
        above = [(d, bs, os) for d, bs, os in ranked if bs >= RELEVANCE_THRESHOLD]
        below = [(d, bs, os) for d, bs, os in ranked if bs < RELEVANCE_THRESHOLD]
        print(f"    Above threshold: {len(above)}   |   Discarded (below threshold): {len(below)}")

        if not above:
            # No hits above threshold → just take the best overall
            print(f"    ⚠️  All below threshold — taking top {top_n} by boosted score")
            candidate_pool = ranked[:top_n]
        elif len(above) >= top_n:
            # Plenty of good hits → just use the top-N above threshold
            candidate_pool = above[:top_n]
        else:
            # Too few above threshold → fill the rest from below-threshold docs
            need = top_n - len(above)
            print(f"    ℹ️  Only {len(above)} above threshold — adding {need} best below-threshold docs")
            candidate_pool = above + below[:need]

        # Extract final docs
        final_docs = [doc for doc, _, _ in candidate_pool]
        
        actual_web = sum(1 for d in final_docs if d.metadata.get("source_type") == "web")
        actual_pdf = sum(1 for d in final_docs if d.metadata.get("source_type") == "pdf")

        # Summary
        print(f"\n📊 FINAL RESULTS:")
        print("=" * 70)
        print(f"    • Web  : {actual_web}")
        print(f"    • PDF  : {actual_pdf}")
        print(f"    • Total: {len(final_docs)} (target: {top_n})")

        for i, (doc, boosted, original) in enumerate(candidate_pool, 1):
            stype = doc.metadata.get("source_type", "?")
            icon = "🌐" if stype == "web" else "📑"
            name = doc.metadata.get("page_name") or doc.metadata.get("source_pdf", "Unknown")
            boost_note = f" (from {original:.4f})" if boosted != original else ""
            
            print(f"\n    {i}. {icon} [{stype.upper()}] {name}")
            print(f"       Score: {boosted:.4f}{boost_note}")
            print(f"       Preview: {doc.page_content[:100]}...")

        print("\n" + "=" * 70 + "\n")
        return final_docs

    except Exception as e:
        print(f"\n❌ RETRIEVAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return []