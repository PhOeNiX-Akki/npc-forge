"""
engine.py — The Shared NPC Inference Core
------------------------------------------
Phase 4 extracts the inference pipeline into this standalone module so that
BOTH the Streamlit UI (app.py) and the REST API (api.py) run the exact same
logic without any code duplication.

ARCHITECT'S NOTE on the Singleton pattern:
  `NPCForgeEngine` uses a class-level `_instance` so it's only initialized once
  per process. Initialization is expensive (ChromaDB, Groq client, lore indexing).
  The first call to `NPCForgeEngine.get()` pays the setup cost; every subsequent
  call reuses the same warmed-up instance.

  In Streamlit: one instance per server process (shared across all browser tabs).
  In FastAPI:   one instance per uvicorn worker process.

FUTURE-PROOFING (10-Year Vision):
  - Phase 5: `run_inference()` becomes async so we can batch requests across
    multiple NPC calls in parallel (vital for multi-NPC tavern at scale).
  - Phase 6: Add function-calling / tool-use here — NPCs can look up weather,
    query game state, roll dice. The inference core becomes an agent loop.
  - Phase 7: Replace brain.think() with a fine-tuned NPC-specific model,
    changing only this file. All callers (UI + API) benefit immediately.
"""

import os
from pathlib import Path
from npc_config import NPC_ROSTER, DEFAULT_MODEL
from brain import NPCBrain
from emotion import EmotionEngine, DEFAULT_EMOTIONS

# Custom NPCs persisted between runs
CUSTOM_NPCS_FILE = Path("data/custom_npcs.json")


class NPCForgeEngine:
    """
    The single source of truth for NPC inference.
    Both the Streamlit UI and the FastAPI service use this class.

    All methods are STATELESS with respect to the player — they receive
    the current state as arguments and return the updated state.
    The caller (app.py / api.py) is responsible for persisting state.
    """

    _instance: "NPCForgeEngine | None" = None

    @classmethod
    def get(cls) -> "NPCForgeEngine":
        """Get the singleton instance (creates it on first call)."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        # Groq client + emotion engine
        self.brain          = NPCBrain(model=DEFAULT_MODEL)
        self.emotion_engine = EmotionEngine()
        self.rag            = None

        # Initialize RAG (optional — degrades gracefully if ChromaDB unavailable)
        self._init_rag()

        # Load any custom NPCs that were forged via the API
        self._load_custom_npcs()

    # ──────────────────────────────────────────
    # Core Inference
    # ──────────────────────────────────────────

    def run_inference(
        self,
        npc_key:              str,
        user_message:         str,
        conversation_history: list[dict],
        emotion_state:        dict[str, float],
        long_term_summary:    str    = "",
        temperature:          float  = 0.85,
        tavern_context:       str    = "",
    ) -> dict:
        """
        The unified inference pipeline. Called by app.py AND api.py.

        PIPELINE:
          emotion.update() → RAG.retrieve() → build_injections() → brain.think()

        Args:
            npc_key:              The NPC's roster key.
            user_message:         The player's raw message text.
            conversation_history: Recent messages (last SHORT_TERM_LIMIT).
            emotion_state:        Current 5-axis emotion dict.
            long_term_summary:    Compressed relationship memory string.
            temperature:          LLM creativity dial.
            tavern_context:       Optional tavern-mode context string injected
                                  to make NPCs aware of each other.

        Returns:
            {
                "response":               str   — The NPC's reply,
                "updated_emotion_state":  dict  — Emotion state after this turn,
            }
        """
        npc = NPC_ROSTER.get(npc_key)
        if not npc:
            return {"response": f"[ERROR: NPC '{npc_key}' not found]", "updated_emotion_state": emotion_state}

        # ── 1. Emotion Update (instant, no API) ──
        new_emotion = self.emotion_engine.update(emotion_state, user_message)

        # ── 2. RAG Lore Retrieval (local ChromaDB, ~30ms) ──
        lore_injection = ""
        if self.rag and len(user_message.split()) >= 3:
            try:
                relevant = self.rag.retrieve(npc_key, npc["name"], user_message)
                if relevant:
                    lore_injection = (
                        f"\n\n[RELEVANT LORE — weave into your answer as lived memory, "
                        f"not recitation]\n{relevant}\n[End lore]\n"
                    )
            except Exception:
                pass

        # ── 3. Build Context Injections ──
        memory_injection = (
            f"\n\n[RELATIONSHIP MEMORY]\n{long_term_summary}\n"
            if long_term_summary else ""
        )
        emotion_injection = self.emotion_engine.to_prompt_injection(new_emotion, npc["name"])

        # Order matters: memory → lore → emotion → tavern
        # (emotion last so behavioral guidance is close to the conversation)
        full_injection = memory_injection + lore_injection + emotion_injection + tavern_context

        # ── 4. LLM Inference (Groq API) ──
        response = self.brain.think(
            system_prompt=npc["system_prompt"],
            conversation_history=conversation_history,
            temperature=temperature,
            context_injection=full_injection,
        )

        return {
            "response":              response,
            "updated_emotion_state": new_emotion,
        }

    def get_welcome_back(
        self,
        npc_key:          str,
        player_name:      str,
        memory_summary:   str,
        emotion_state:    dict[str, float],
        temperature:      float = 0.8,
    ) -> str:
        """
        Generate a personalized returning-player greeting using the brain.
        The NPC subtly acknowledges the relationship without saying "welcome back."

        Called once per session when a returning player is detected.
        """
        npc           = NPC_ROSTER.get(npc_key, {})
        emo_injection = self.emotion_engine.to_prompt_injection(emotion_state, npc.get("name", ""))

        prompt = (
            f"{npc.get('system_prompt', '')}\n\n"
            f"[RETURNING PLAYER]\n"
            f"Player '{player_name}' has returned. Your memory of them:\n{memory_summary}\n"
            f"{emo_injection}\n"
            f"Generate a greeting that shows recognition through specific detail — "
            f"not 'welcome back' but a subtle acknowledgement of what you remember. "
            f"2-3 sentences. Stay in character."
        )

        return self.brain.think(
            system_prompt=prompt,
            conversation_history=[],
            temperature=temperature,
        )

    def forge_npc(self, spec: dict) -> str:
        """
        Create a new NPC from a spec dict (from API or custom form).
        Saves to CUSTOM_NPCS_FILE and indexes lore in RAG.

        Returns:
            The npc_id (roster key) for the new NPC.
        """
        import json, re

        name    = spec["name"]
        npc_id  = "custom_" + re.sub(r'[^a-z0-9_]', '_', name.lower()).strip('_')

        system_prompt = (
            f"You are {name}.\n\n"
            f"## Personality\n{spec.get('personality', 'A mysterious character.')}\n\n"
            f"## Rules\n"
            f"- Stay in character at ALL times.\n"
            f"- When [RELEVANT LORE] is provided, weave it into your answer naturally.\n"
            f"- Keep responses 2–4 sentences unless asked for more.\n"
        )

        greeting = spec.get(
            "greeting",
            f"*{name} regards you carefully.*\n\nSo. You've found me. Speak your purpose."
        )

        npc_data = {
            "avatar":           spec.get("avatar", "🤖"),
            "name":             name,
            "system_prompt":    system_prompt,
            "greeting":         greeting,
            "lore":             spec.get("lore", ""),
            "initial_emotions": spec.get("initial_emotions", dict(DEFAULT_EMOTIONS)),
            "theme_color":      spec.get("theme_color",  "#4a90e2"),
            "accent_color":     spec.get("accent_color", "#f5a623"),
            "bg_gradient":      "linear-gradient(135deg, #0a0a1a 0%, #0d0d20 100%)",
        }

        # Add to in-memory roster
        NPC_ROSTER[npc_id] = npc_data

        # Persist to disk
        CUSTOM_NPCS_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if CUSTOM_NPCS_FILE.exists():
            with open(CUSTOM_NPCS_FILE, encoding="utf-8") as f:
                existing = json.load(f)
        existing[npc_id] = npc_data
        with open(CUSTOM_NPCS_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

        # Index lore
        if self.rag and npc_data["lore"]:
            self.rag.ensure_indexed(npc_id, name, npc_data["lore"])

        return npc_id

    def delete_npc(self, npc_id: str) -> bool:
        """Delete a custom NPC from roster, disk, ChromaDB, and player memory. Returns False if not custom."""
        import json
        if not npc_id.startswith("custom_"):
            return False
        NPC_ROSTER.pop(npc_id, None)
        if CUSTOM_NPCS_FILE.exists():
            with open(CUSTOM_NPCS_FILE, encoding="utf-8") as f:
                existing = json.load(f)
            existing.pop(npc_id, None)
            with open(CUSTOM_NPCS_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)

        # 1. Delete ChromaDB collection
        if self.rag:
            try:
                col_name = self.rag._safe_collection_name(npc_id)
                self.rag._client.delete_collection(name=col_name)
            except Exception:
                pass

        # 2. Purge player profiles & history files
        from persistence import PlayerProfile
        PlayerProfile.purge_npc_data(npc_id)

        return True

    # ──────────────────────────────────────────
    # Private
    # ──────────────────────────────────────────

    def _init_rag(self):
        """Initialize ChromaDB RAG engine and index all base lore."""
        try:
            from rag import LoreRAG
            self.rag = LoreRAG(persist_dir="data/chromadb")
            for npc_key, npc_data in NPC_ROSTER.items():
                if npc_data.get("lore"):
                    self.rag.ensure_indexed(npc_key, npc_data["name"], npc_data["lore"])
        except Exception:
            self.rag = None   # RAG unavailable — non-fatal

    def _load_custom_npcs(self):
        """Load any previously forged custom NPCs from disk."""
        import json
        if not CUSTOM_NPCS_FILE.exists():
            return
        try:
            with open(CUSTOM_NPCS_FILE, encoding="utf-8") as f:
                custom = json.load(f)
            for npc_id, npc_data in custom.items():
                if npc_id not in NPC_ROSTER:
                    NPC_ROSTER[npc_id] = npc_data
                    if self.rag and npc_data.get("lore"):
                        self.rag.ensure_indexed(npc_id, npc_data["name"], npc_data["lore"])
        except Exception:
            pass
