import os
import re
from typing import Dict
from langchain_community.document_loaders import PyPDFLoader

# ─────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────

PDF_DIR = "pdf_data/files"
CLEAN_DIR = "data/clean_text"

# Prefix for PDF-derived text files
PDF_FILE_PREFIX = "pdf__"


# ─────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """Normalize whitespace and strip."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _pdf_name_to_txt(pdf_filename: str) -> str:
    """
    Convert:
      'Report.pdf' → 'pdf__Report.txt'
    """
    base = os.path.splitext(pdf_filename)[0]
    return f"{PDF_FILE_PREFIX}{base}.txt"


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def save_pdfs_to_clean_text() -> Dict[str, list]:
    """
    Parse all PDFs from PDF_DIR, clean text, and save into CLEAN_DIR.

    Chunking is intentionally NOT done here.

    Returns:
    {
        "saved":   [...],
        "skipped": [...],
        "failed":  [...]
    }
    """
    os.makedirs(CLEAN_DIR, exist_ok=True)

    saved, skipped, failed = [], [], []

    pdf_files = [
        f for f in os.listdir(PDF_DIR)
        if f.lower().endswith(".pdf")
    ]

    if not pdf_files:
        print(f"⚠️  No PDFs found in '{PDF_DIR}'")
        return {"saved": [], "skipped": [], "failed": []}

    print(f"\n📑 Processing {len(pdf_files)} PDF(s)")
    print("=" * 60)

    for pdf_filename in pdf_files:
        txt_filename = _pdf_name_to_txt(pdf_filename)
        txt_path = os.path.join(CLEAN_DIR, txt_filename)
        pdf_path = os.path.join(PDF_DIR, pdf_filename)

        # Skip if already processed (idempotent)
        if os.path.exists(txt_path):
            print(f"  ⏭️  Skip (exists): {txt_filename}")
            skipped.append(txt_filename)
            continue

        try:
            loader = PyPDFLoader(pdf_path)
            pages = loader.load()

            full_text = "\n\n".join(
                _clean_text(page.page_content)
                for page in pages
                if page.page_content and page.page_content.strip()
            )

            if not full_text:
                print(f"  ⚠️  Empty content: {pdf_filename}")
                skipped.append(txt_filename)
                continue

            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(full_text)

            print(f"  ✅ Saved: {txt_filename} ({len(full_text):,} chars)")
            saved.append(txt_filename)

        except Exception as e:
            msg = f"{pdf_filename}: {e}"
            print(f"  ❌ Failed: {msg}")
            failed.append(msg)

    print("=" * 60)
    print(
        f"Done — saved: {len(saved)}, "
        f"skipped: {len(skipped)}, "
        f"failed: {len(failed)}\n"
    )

    return {
        "saved": saved,
        "skipped": skipped,
        "failed": failed,
    }