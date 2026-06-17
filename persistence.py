"""
persistence.py — The Player Profile System of NPC-Forge
---------------------------------------------------------
This module saves and loads each player's relationship state with every NPC
across browser sessions. It answers the question:

  "Does Silas Vane remember me the NEXT time I open the app?"

The answer, after Phase 3: YES.

HOW IT WORKS:
  We store JSON files on disk in this structure:

    data/players/
    ├── {player_name}/
    │   ├── the_cursed_samurai/
    │   │   └── profile.json
    │   └── the_grey_merchant/
    │       └── profile.json
    └── another_player/
        └── ...

  Each profile.json contains:
    - emotion_state: the 5-axis emotional bond
    - long_term_summary: the NPC's compressed memory of the relationship
    - message_count: total messages exchanged (for context)
    - first_seen: when this player first talked to this NPC
    - last_seen: when they last talked

FUTURE-PROOFING (10-Year Vision):
  - Phase 5: Replace JSON files with a SQLite or PostgreSQL database.
  - Phase 6: Add player authentication so profiles are cloud-synced.
  - Phase 7: Expose profiles via a REST API so game engines can read
    a player's NPC relationships and trigger game-world consequences.
    ("Silas Vane's trust of the player is 8/10 → unlock secret quest")
"""

import json
import re
from pathlib import Path
from datetime import datetime


class PlayerProfile:
    """
    Manages persistent player-NPC relationship data on disk.

    ARCHITECT'S NOTE on why JSON, not a database:
      At this scale (dozens of players, handful of NPCs), JSON files
      are perfectly adequate. They're human-readable, version-controllable,
      and require zero setup. We follow the principle: "Use the simplest
      tool that solves the problem." We can always migrate to SQLite later.
    """

    def __init__(self, player_name: str, data_dir: str = "data/players"):
        """
        Args:
            player_name: The player's chosen name (case-insensitive).
            data_dir:    Root directory for all player profiles.
        """
        self.player_name   = player_name.strip().lower()
        self.data_dir      = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────
    # Core: Save & Load
    # ──────────────────────────────────────────

    def save(
        self,
        npc_key:            str,
        npc_name:           str,
        emotion_state:      dict[str, float],
        long_term_summary:  str,
        message_count:      int = 0,
    ) -> None:
        """
        Persist the player's current relationship with an NPC to disk.

        This is called automatically after EVERY NPC response in app.py,
        so the profile is always up-to-date. If the app crashes or the
        browser closes, no progress is lost.

        Args:
            npc_key:           The NPC's roster key (e.g., "⚔️ The Cursed Samurai").
            npc_name:          The NPC's display name (e.g., "Kagetora").
            emotion_state:     Current 5-axis emotional bond dict.
            long_term_summary: The compressed relationship memory string.
            message_count:     Total messages exchanged with this NPC.
        """
        profile_path = self._get_profile_path(npc_key)

        # Load existing to preserve first_seen date
        existing = self._load_raw(npc_key)
        first_seen = existing.get("first_seen") if existing else datetime.now().isoformat()

        profile = {
            "player_name":        self.player_name,
            "npc_key":            npc_key,
            "npc_name":           npc_name,
            "emotion_state":      emotion_state,
            "long_term_summary":  long_term_summary,
            "message_count":      message_count,
            "first_seen":         first_seen,
            "last_seen":          datetime.now().isoformat(),
            "schema_version":     "1.0",  # For future migrations
        }

        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)

    def load(self, npc_key: str) -> dict | None:
        """
        Load the player's saved relationship with an NPC.

        Returns:
            The profile dict if it exists, or None for new relationships.
        """
        return self._load_raw(npc_key)

    def exists(self, npc_key: str) -> bool:
        """Returns True if this player has an existing relationship with this NPC."""
        return self._get_profile_path(npc_key).exists()

    # ──────────────────────────────────────────
    # Utility
    # ──────────────────────────────────────────

    def list_known_npcs(self) -> list[str]:
        """Returns a list of NPC names this player has an existing profile for."""
        player_dir = self.data_dir / self.player_name
        if not player_dir.exists():
            return []

        known = []
        for npc_dir in player_dir.iterdir():
            if npc_dir.is_dir():
                profile_path = npc_dir / "profile.json"
                if profile_path.exists():
                    try:
                        with open(profile_path, encoding="utf-8") as f:
                            data = json.load(f)
                        known.append(data.get("npc_name", npc_dir.name))
                    except Exception:
                        pass
        return known

    def days_since_last_visit(self, npc_key: str) -> int | None:
        """
        Returns how many days have passed since the player last spoke to this NPC.
        Returns None if no profile exists.
        """
        profile = self._load_raw(npc_key)
        if not profile:
            return None
        try:
            last_seen = datetime.fromisoformat(profile["last_seen"])
            delta     = datetime.now() - last_seen
            return max(0, delta.days)
        except Exception:
            return None

    # ──────────────────────────────────────────
    # Static Helpers
    # ──────────────────────────────────────────

    @staticmethod
    def list_all_players(data_dir: str = "data/players") -> list[str]:
        """
        Returns all player names that have saved profiles.
        Used in the welcome screen to show autocomplete suggestions.
        """
        root = Path(data_dir)
        if not root.exists():
            return []
        return [
            d.name for d in root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]

    @staticmethod
    def purge_npc_data(npc_key: str, data_dir: str = "data/players") -> None:
        """
        Delete all players' profile folders and histories for a given NPC key.
        """
        import shutil
        root = Path(data_dir)
        if not root.exists():
            return
        
        # We need to sanitize the npc_key using the same rules as _safe_npc_dirname
        # We construct a dummy instance to use its _safe_npc_dirname method
        dummy = PlayerProfile("dummy", data_dir=data_dir)
        safe_name = dummy._safe_npc_dirname(npc_key)
        
        for player_dir in root.iterdir():
            if player_dir.is_dir():
                npc_dir = player_dir / safe_name
                if npc_dir.exists() and npc_dir.is_dir():
                    try:
                        shutil.rmtree(npc_dir)
                    except Exception:
                        pass

    # ──────────────────────────────────────────
    # Private
    # ──────────────────────────────────────────

    def _safe_npc_dirname(self, npc_key: str) -> str:
        """Convert an NPC key (may contain emojis) to a safe directory name."""
        # Strip non-alphanumeric (keeps unicode letters, strips emoji)
        cleaned = re.sub(r'[^\w\s]', '', npc_key, flags=re.UNICODE)
        cleaned = cleaned.lower().strip()
        cleaned = re.sub(r'\s+', '_', cleaned)
        cleaned = re.sub(r'[^a-z0-9_]', '', cleaned)
        cleaned = re.sub(r'_+', '_', cleaned).strip('_')
        return cleaned if cleaned else f"npc_{abs(hash(npc_key)) % 9999}"

    def _get_profile_path(self, npc_key: str) -> Path:
        npc_dir = self.data_dir / self.player_name / self._safe_npc_dirname(npc_key)
        npc_dir.mkdir(parents=True, exist_ok=True)
        return npc_dir / "profile.json"

    def _load_raw(self, npc_key: str) -> dict | None:
        path = self._get_profile_path(npc_key)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
