"""
lore_ingestion.py — Multi-Source Lore Extractor for NPC-Forge
--------------------------------------------------------------
This module gives NPC-Forge the ability to ingest lore from THREE sources:

  1. PDF documents  — Upload your game's world book, quest notes, character bible
  2. Wikipedia      — Pull any article directly into the NPC's knowledge base
  3. Plain text     — Write or paste lore manually

All extracted text gets chunked and indexed into ChromaDB via rag.py,
so the NPC can RAG-retrieve the RIGHT section when players ask about it.

WHY THIS IS A KILLER FEATURE:
  An indie dev has a 200-page world-building PDF they've been writing for 3 years.
  Previously: they'd have to summarize it manually for each AI prompt.
  With NPC-Forge Phase 5: they upload the PDF → every NPC instantly knows everything in it.
  When a player asks "Who built the Iron Bridge?", the NPC RETRIEVES the exact paragraph.

ARCHITECT'S NOTE on PyMuPDF:
  The pip package name is `pymupdf`. The import name is `fitz`.
  This naming confusion is historical (PyMuPDF was originally called MuPDF-Python).
  In PyMuPDF >= 1.24, you can also do `import pymupdf as fitz`. We handle both.

FUTURE-PROOFING:
  - Phase 6: Add DOCX support (python-docx) and ePub support (ebooklib)
  - Phase 7: Add YouTube transcript ingestion (yt-dlp + whisper) so devs can
    upload voice-acted lore videos and have NPCs know what was said in them
  - Phase 8: Add auto-summarization: when a PDF is > 50 pages, summarize each
    chapter separately before indexing for better retrieval precision
"""

import re
import io

# ─────────────────────────────────────────────
# OPTIONAL DEPENDENCY GUARDS
# ─────────────────────────────────────────────

# PyMuPDF — PDF extraction
try:
    import fitz as _fitz
    PYMUPDF_AVAILABLE = True
    _fitz_module = _fitz
except ImportError:
    try:
        import pymupdf as _fitz_module  # type: ignore
        PYMUPDF_AVAILABLE = True
    except ImportError:
        PYMUPDF_AVAILABLE = False
        _fitz_module = None

# Wikipedia Python library
try:
    import wikipedia as _wiki
    WIKIPEDIA_AVAILABLE = True
except ImportError:
    WIKIPEDIA_AVAILABLE = False
    _wiki = None


class LoreIngestion:
    """
    Static utility class for extracting text from multiple lore sources.
    All methods return clean, chunk-ready strings suitable for rag.py.
    """

    # ──────────────────────────────────────────
    # 1. PDF Extraction
    # ──────────────────────────────────────────

    @staticmethod
    def from_pdf(pdf_bytes: bytes) -> str:
        """
        Extract all readable text from a PDF file.

        ARCHITECT'S NOTE on page ordering:
          PyMuPDF preserves the PDF's page order and extracts text in reading
          order within each page. For most world-building documents this is
          perfect. For complex multi-column layouts (newspapers, magazines),
          the column order may mix — but world-building PDFs are rarely
          multi-column, so this is not a concern in practice.

        Args:
            pdf_bytes: Raw bytes of the PDF file (from st.file_uploader.read()).

        Returns:
            Cleaned full-text string, ready for chunking.

        Raises:
            ImportError: If PyMuPDF is not installed.
            ValueError: If the bytes are not a valid PDF.
        """
        if not PYMUPDF_AVAILABLE:
            raise ImportError(
                "PyMuPDF is not installed. Run: pip install pymupdf"
            )

        try:
            doc = _fitz_module.open(stream=pdf_bytes, filetype="pdf")  # type: ignore
        except Exception as e:
            raise ValueError(f"Could not open PDF: {e}") from e

        page_texts: list[str] = []
        for page in doc:
            text = page.get_text().strip()
            if text:
                page_texts.append(text)
        doc.close()

        if not page_texts:
            return ""

        raw = "\n\n".join(page_texts)
        return _clean_extracted_text(raw)

    @staticmethod
    def pdf_page_count(pdf_bytes: bytes) -> int:
        """Returns the number of pages in a PDF without full extraction."""
        if not PYMUPDF_AVAILABLE:
            return 0
        try:
            doc = _fitz_module.open(stream=pdf_bytes, filetype="pdf")  # type: ignore
            n   = doc.page_count
            doc.close()
            return n
        except Exception:
            return 0

    # ──────────────────────────────────────────
    # 2. Wikipedia Extraction
    # ──────────────────────────────────────────

    @staticmethod
    def from_wikipedia(
        topic:     str,
        lang:      str = "en",
        max_chars: int = 10_000,
    ) -> tuple[str, str]:
        """
        Fetch a Wikipedia article and return its text.

        The article is truncated to `max_chars` before returning.
        Since we're chunking into ~150-word pieces and RAG-retrieving,
        10,000 characters gives us ~60 chunks — more than enough.

        Args:
            topic:     Search query (e.g. "Samurai", "Norse Mythology").
            lang:      Wikipedia language code ("en", "ja", "fr", etc.).
            max_chars: Max characters to return (prevents massive articles
                       overwhelming ChromaDB with irrelevant content).

        Returns:
            (cleaned_text, article_title) — title is empty string if not found.
        """
        if not WIKIPEDIA_AVAILABLE:
            raise ImportError(
                "Wikipedia package is not installed. Run: pip install wikipedia"
            )

        _wiki.set_lang(lang)  # type: ignore

        try:
            page = _wiki.page(topic, auto_suggest=True)  # type: ignore
            text = _clean_wikipedia_text(page.content[:max_chars])
            return text, page.title

        except _wiki.exceptions.DisambiguationError as e:  # type: ignore
            # Multiple articles match — pick the first suggestion
            if e.options:
                try:
                    page = _wiki.page(e.options[0])  # type: ignore
                    text = _clean_wikipedia_text(page.content[:max_chars])
                    return text, f"{page.title} (disambiguated)"
                except Exception:
                    return "", ""
            return "", ""

        except _wiki.exceptions.PageError:  # type: ignore
            return "", ""

        except Exception as e:
            return "", str(e)

    @staticmethod
    def search_wikipedia(
        query:       str,
        lang:        str = "en",
        max_results: int = 6,
    ) -> list[str]:
        """
        Return a list of Wikipedia article titles matching the query.
        Used to show suggestions before the user commits to fetching.

        Returns:
            List of article title strings, or [] if unavailable.
        """
        if not WIKIPEDIA_AVAILABLE:
            return []
        try:
            _wiki.set_lang(lang)  # type: ignore
            return _wiki.search(query, results=max_results)  # type: ignore
        except Exception:
            return []

    # ──────────────────────────────────────────
    # 3. Plain Text
    # ──────────────────────────────────────────

    @staticmethod
    def from_plain_text(text: str) -> str:
        """Clean and normalize manually entered lore text."""
        return _clean_extracted_text(text)

    # ──────────────────────────────────────────
    # Availability Checks
    # ──────────────────────────────────────────

    @staticmethod
    def pdf_available() -> bool:
        """Returns True if PDF extraction is available."""
        return PYMUPDF_AVAILABLE

    @staticmethod
    def wikipedia_available() -> bool:
        """Returns True if Wikipedia fetching is available."""
        return WIKIPEDIA_AVAILABLE

    @staticmethod
    def get_missing_deps() -> list[str]:
        """Returns list of pip install commands for missing optional deps."""
        missing = []
        if not PYMUPDF_AVAILABLE:
            missing.append("pip install pymupdf")
        if not WIKIPEDIA_AVAILABLE:
            missing.append("pip install wikipedia")
        return missing


# ─────────────────────────────────────────────
# PRIVATE TEXT CLEANING UTILITIES
# ─────────────────────────────────────────────

def _clean_extracted_text(text: str) -> str:
    """
    General-purpose cleaner for extracted text (PDF, plain text).
    Removes junk characters, normalizes whitespace, drops empty lines.
    """
    if not text:
        return ""

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove PDF artifact characters (common in scanned PDFs)
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', ' ', text)

    # Collapse 3+ newlines into 2 (paragraph breaks)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Remove lines that are just page numbers, headers, footers
    # (single digits, or very short lines that are likely artifacts)
    lines = text.split('\n')
    filtered = []
    for line in lines:
        stripped = line.strip()
        # Keep if: not empty, and not just a page number / short artifact
        if stripped and (len(stripped) > 3 or not stripped.isdigit()):
            filtered.append(stripped)
        elif not stripped:
            filtered.append('')  # Preserve blank lines as paragraph breaks

    text = '\n'.join(filtered)

    # Collapse multiple spaces
    text = re.sub(r'[ \t]{2,}', ' ', text)

    # Final trim
    return text.strip()


def _clean_wikipedia_text(text: str) -> str:
    """
    Cleaner specific to Wikipedia article content.
    Wikipedia's Python library returns mediawiki-formatted text.
    """
    if not text:
        return ""

    # Remove section headers like "== References ==" and "=== See also ==="
    text = re.sub(r'={2,}[^=\n]+={2,}', '', text)

    # Remove citation markers like [1], [2], [citation needed]
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\[citation needed\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[edit\]', '', text, flags=re.IGNORECASE)

    # Remove "References", "External links", "See also" sections
    # (Everything after these headers is not narrative lore)
    for section in ["References", "External links", "See also", "Notes", "Bibliography"]:
        pattern = rf'\n{section}\n.*$'
        text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

    # Remove infobox-style lines (lines with key: value where key is very short)
    text = re.sub(r'^[A-Z][a-z]+:\s+.{0,50}$', '', text, flags=re.MULTILINE)

    return _clean_extracted_text(text)
