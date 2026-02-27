import os
from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# ─────────────────────────────────────────────────────────────
# Paths & constants
# ─────────────────────────────────────────────────────────────

CLEAN_DIR = "data/clean_text"

# Must match pdf_data.py
PDF_FILE_PREFIX = "pdf__"


# ─────────────────────────────────────────────────────────────
# Unified loader + chunker
# ─────────────────────────────────────────────────────────────

def get_all_text_with_metadata(
    chunk_size: int = 400,      # Reduced from 1000 for better granularity
    chunk_overlap: int = 200,   # Reduced from 200 to match proportion
) -> List[Document]:
    """
    Load ALL .txt files from CLEAN_DIR, assign metadata,
    and chunk them together in one pass.

    File naming convention:
      • pdf__<name>.txt  → PDF
      • anything_else   → Web
    
    Chunk size = 500 gives better granularity for precise retrieval
    while keeping each chunk focused on a single topic.
    """
    documents: List[Document] = []

    web_files = 0
    pdf_files = 0

    txt_files = sorted(
        f for f in os.listdir(CLEAN_DIR)
        if f.endswith(".txt")
    )

    if not txt_files:
        print(f"⚠️  No .txt files found in '{CLEAN_DIR}'")
        return []

    for filename in txt_files:
        path = os.path.join(CLEAN_DIR, filename)

        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        if not text.strip():
            continue

        name_without_ext = os.path.splitext(filename)[0]

        if filename.startswith(PDF_FILE_PREFIX):
            original_pdf = name_without_ext[len(PDF_FILE_PREFIX):] + ".pdf"
            metadata = {
                "source_type": "pdf",
                "source_pdf": original_pdf,
                "page_name": name_without_ext,
            }
            pdf_files += 1
        else:
            metadata = {
                "source_type": "web",
                "page_name": name_without_ext,
            }
            web_files += 1

        documents.append(
            Document(
                page_content=text,
                metadata=metadata,
            )
        )

    print(
        f"📂 Loaded {len(documents)} files "
        f"({web_files} web + {pdf_files} pdf)"
    )

    # ─────────────────────────────────────────────────────────
    # Chunk ALL documents together (single splitter)
    # ─────────────────────────────────────────────────────────

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        # These separators help maintain semantic boundaries
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = splitter.split_documents(documents)

    web_chunks = sum(
        1 for c in chunks if c.metadata.get("source_type") == "web"
    )
    pdf_chunks = sum(
        1 for c in chunks if c.metadata.get("source_type") == "pdf"
    )

    print(
        f"✂️  Chunked into {len(chunks)} chunks "
        f"({web_chunks} web + {pdf_chunks} pdf)"
    )

    return chunks