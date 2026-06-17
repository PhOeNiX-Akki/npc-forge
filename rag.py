"""
rag.py — The Lore RAG Engine of NPC-Forge
------------------------------------------
RAG = Retrieval-Augmented Generation.

THE PROBLEM IT SOLVES:
  An NPC's system prompt has a token limit. We can't dump the entire
  lore encyclopedia into every API call — it's expensive and wasteful.
  
  Instead, we store lore in a local vector database (ChromaDB) and
  RETRIEVE only the most relevant chunks for each user message.
  
  Example:
    Player asks: "Tell me about Mount Osore"
    → RAG retrieves the 2 chunks most semantically similar to that query
    → Injects them into the system prompt
    → Kagetora can now answer with specific, accurate lore detail

HOW VECTOR SEARCH WORKS (for the Architect):
  1. At startup: lore text is split into chunks (~150 words each)
  2. Each chunk is converted to a vector embedding (a list of 384 numbers
     that capture the semantic meaning of the text)
  3. These vectors are stored in ChromaDB on disk
  4. At query time: the user's message is also embedded
  5. ChromaDB finds the stored chunks whose vectors are most SIMILAR
     (cosine similarity) to the query vector → these are semantically relevant
  6. The top N chunks are returned and injected into the system prompt

  This is the same core technique used by ChatGPT's "memory" feature,
  Microsoft Copilot, and every serious production AI assistant.

EMBEDDING MODEL:
  ChromaDB's built-in ONNXMiniLM-L6 (384-dimensional vectors).
  - Runs 100% locally — no API, no internet after first install
  - Downloads once (~45MB) and caches permanently
  - Fast: <50ms per embedding on CPU

FUTURE-PROOFING (10-Year Vision):
  - Phase 5: Replace MiniLM with a fine-tuned embedding model trained
    on fantasy/anime text for even better lore retrieval.
  - Phase 6: Expand to multi-modal: embed NPC voice lines, character art
    descriptions, and map data alongside text lore.
  - Phase 7: Expose RAG via API so Unity/Godot game engines can query
    lore and dynamically generate quest descriptions.
"""

import re
from pathlib import Path


# ─────────────────────────────────────────────
# CHROMADB IMPORT WITH HELPFUL ERROR
# ─────────────────────────────────────────────
try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


class LoreRAG:
    """
    Local RAG engine powered by ChromaDB.

    Each NPC gets its own ChromaDB collection (a separate vector space).
    This means Kagetora's lore doesn't interfere with Silas's lore.

    Usage:
        rag = LoreRAG(persist_dir="data/chromadb")
        rag.ensure_indexed(npc_key, npc_name, lore_text)   # at startup
        chunks = rag.retrieve(npc_key, npc_name, user_msg) # at inference
    """

    CHUNK_SIZE    = 150   # Target words per chunk
    CHUNK_OVERLAP = 30    # Words of overlap between adjacent chunks
    TOP_N_RESULTS = 2     # How many chunks to retrieve per query

    def __init__(self, persist_dir: str = "data/chromadb"):
        """
        Initialize ChromaDB with persistent storage.

        Args:
            persist_dir: Directory where ChromaDB stores its index files.
                         Persists across app restarts — lore only needs
                         to be indexed once.
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "ChromaDB is not installed. Run: pip install chromadb"
            )

        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_dir)

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────

    def ensure_indexed(
        self,
        npc_key:   str,
        npc_name:  str,
        lore_text: str,
    ) -> int:
        """
        Index the NPC's base lore if not already done.

        ARCHITECT'S NOTE:
          We use 'upsert' (update-or-insert) with deterministic chunk IDs.
          This means calling this function multiple times is SAFE — it
          won't create duplicate entries. Idempotent design is critical for
          any production system.

        Args:
            npc_key:   The roster key (used to derive the collection name).
            npc_name:  Display name (used in chunk metadata).
            lore_text: The raw lore text from npc_config.py.

        Returns:
            Number of chunks indexed.
        """
        collection = self._get_collection(npc_key)
        chunks     = self._chunk_text(lore_text)

        if not chunks:
            return 0

        # Create deterministic IDs based on source + position
        ids       = [f"config_{i:04d}" for i in range(len(chunks))]
        metadatas = [{"source": "config", "npc": npc_name, "chunk_id": i}
                     for i in range(len(chunks))]

        collection.upsert(documents=chunks, ids=ids, metadatas=metadatas)
        return len(chunks)

    def index_uploaded_text(
        self,
        npc_key:  str,
        npc_name: str,
        text:     str,
        filename: str = "upload",
    ) -> int:
        """
        Index text from a user-uploaded file (.txt or .md).

        Called from the sidebar file uploader in app.py.

        Args:
            npc_key:  NPC roster key.
            npc_name: NPC display name.
            text:     The raw file content.
            filename: Original filename (stored in metadata for reference).

        Returns:
            Number of new chunks added.
        """
        collection = self._get_collection(npc_key)
        chunks     = self._chunk_text(text)

        if not chunks:
            return 0

        # Use filename as source prefix to avoid ID collisions with config chunks
        safe_fname = re.sub(r'[^a-zA-Z0-9_]', '_', filename)[:20]
        ids        = [f"{safe_fname}_{i:04d}" for i in range(len(chunks))]
        metadatas  = [{"source": filename, "npc": npc_name, "chunk_id": i}
                      for i in range(len(chunks))]

        collection.upsert(documents=chunks, ids=ids, metadatas=metadatas)
        return len(chunks)

    def retrieve(
        self,
        npc_key:   str,
        npc_name:  str,
        query:     str,
        n_results: int | None = None,
    ) -> str:
        """
        Retrieve the most semantically relevant lore chunks for a query.

        This is the core RAG operation called during inference.

        Args:
            npc_key:   NPC roster key.
            npc_name:  NPC display name (unused here but kept for symmetry).
            query:     The user's message (used as the search query).
            n_results: How many chunks to return (defaults to TOP_N_RESULTS).

        Returns:
            A formatted string of relevant lore chunks, or "" if none found.
            Returns "" if query is very short (unlikely to match well).
        """
        # Don't bother retrieving for very short messages
        if len(query.strip().split()) < 3:
            return ""

        collection = self._get_collection(npc_key)
        total_docs  = collection.count()

        if total_docs == 0:
            return ""

        k = min(n_results or self.TOP_N_RESULTS, total_docs)

        try:
            results = collection.query(
                query_texts=[query],
                n_results=k,
                include=["documents", "distances"],
            )
        except Exception:
            return ""

        docs      = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not docs:
            return ""

        # Filter out chunks that are too distant (not relevant enough)
        # ChromaDB uses L2 distance by default; lower = more similar
        # Threshold ~1.5 filters out clearly unrelated chunks
        relevant = [
            doc for doc, dist in zip(docs, distances)
            if dist < 1.5
        ]

        if not relevant:
            return ""

        return "\n---\n".join(relevant)

    def get_chunk_count(self, npc_key: str) -> int:
        """Returns total number of indexed chunks for this NPC."""
        try:
            return self._get_collection(npc_key).count()
        except Exception:
            return 0

    def get_sources(self, npc_key: str) -> list[str]:
        """Returns list of distinct lore sources indexed for this NPC."""
        try:
            collection = self._get_collection(npc_key)
            if collection.count() == 0:
                return []
            # Get a sample of metadata to find sources
            results = collection.get(limit=200, include=["metadatas"])
            sources = list({
                m.get("source", "unknown")
                for m in results.get("metadatas", [])
            })
            return sources
        except Exception:
            return []

    # ──────────────────────────────────────────
    # Private Helpers
    # ──────────────────────────────────────────

    def _get_collection(self, npc_key: str) -> "chromadb.Collection":
        """
        Get (or create) the ChromaDB collection for an NPC.

        ARCHITECT'S NOTE on collection naming:
          ChromaDB requires alphanumeric names (3-63 chars).
          We sanitize the NPC key (which may contain emojis) to a safe name.
        """
        name = self._safe_collection_name(npc_key)
        return self._client.get_or_create_collection(name=name)

    @staticmethod
    def _safe_collection_name(npc_key: str) -> str:
        """Convert an NPC key to a ChromaDB-safe collection name."""
        # Remove emoji and non-ASCII, keep latin letters/digits/spaces
        cleaned = re.sub(r'[^\w\s]', '', npc_key, flags=re.UNICODE)
        cleaned = cleaned.lower().strip()
        cleaned = re.sub(r'\s+', '_', cleaned)              # spaces → underscores
        cleaned = re.sub(r'[^a-z0-9_]', '', cleaned)        # strip non-alphanumeric
        cleaned = re.sub(r'_+', '_', cleaned).strip('_')    # collapse underscores

        # Ensure min length of 3 (ChromaDB requirement)
        if len(cleaned) < 3:
            cleaned = f"npc{abs(hash(npc_key)) % 9999}"

        # Ensure max 63 chars
        cleaned = cleaned[:63].rstrip('_')

        # Must start and end with alphanumeric
        cleaned = re.sub(r'^[^a-z0-9]+', '', cleaned)
        cleaned = re.sub(r'[^a-z0-9]+$', '', cleaned)

        return cleaned if cleaned else f"npc{abs(hash(npc_key)) % 9999}"

    def _chunk_text(self, text: str) -> list[str]:
        """
        Split lore text into overlapping word-based chunks.

        ARCHITECT'S NOTE on chunking strategy:
          Overlap (30 words) ensures that a concept spanning two chunks
          isn't missed. For example, if "Ryugu-jo Palace" appears at the
          end of chunk 4 and beginning of chunk 5, both chunks will match
          a query about the Sunken Palace.

          Chunk size of 150 words is empirically optimal for this use case:
          - Large enough to carry coherent context
          - Small enough to be precise (not return irrelevant tangents)
        """
        # Clean up whitespace
        text   = re.sub(r'\n+', ' ', text.strip())
        words  = text.split()

        if not words:
            return []

        chunks = []
        step   = self.CHUNK_SIZE - self.CHUNK_OVERLAP
        step   = max(step, 1)

        for i in range(0, len(words), step):
            chunk = " ".join(words[i: i + self.CHUNK_SIZE])
            if len(chunk.split()) >= 10:   # Skip tiny trailing chunks
                chunks.append(chunk)

        return chunks
