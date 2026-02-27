# ── Stage: Python base ────────────────────────────────────────
FROM python:3.11-slim

# Set working directory
WORKDIR /app

ENV PYTHONPATH=/app        

# Install system dependencies needed by some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# ── Install Python dependencies ───────────────────────────────
# Copy requirements first so Docker caches this layer
# (only rebuilds if requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# ── Pre-download embedding model during build ─────────────────
# This bakes the model into the image so startup is instant
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
print('Downloading embedding model...'); \
SentenceTransformer('paraphrase-multilingual-mpnet-base-v2'); \
print('Model downloaded and cached')"

RUN playwright install chromium --with-deps

# ── Copy application code ─────────────────────────────────────
COPY . .

# Create required directories if they don't exist
RUN mkdir -p data/clean_text data/raw_html data/faiss_index database pdf_data/files

# ── Expose FastAPI port ───────────────────────────────────────
# EXPOSE 8000

# # Default command (overridden by docker-compose for each service)
# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
# For Production
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
