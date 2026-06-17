"""
voice.py — The Voice I/O Layer of NPC-Forge
--------------------------------------------
Provides Speech-to-Text (STT) and Text-to-Speech (TTS) for NPC conversations.

STT — Groq Whisper:
  We already have a Groq API key (used for LLM inference).
  Groq also hosts whisper-large-v3-turbo for transcription — FREE on the same key.
  
  Input: audio bytes (WAV from st.audio_input)
  Output: text transcript

  ARCHITECT'S NOTE on why Groq Whisper (not OpenAI Whisper):
    - Same API key we already have → zero extra setup
    - Groq's Whisper is FAST (real-time factor ~0.05x on their infra)
    - Free tier: 7,200 seconds/day of audio — enough for development

TTS — gTTS (Google Text-to-Speech):
  Free, no API key, no sign-up. Uses Google's TTS service under the hood.
  Produces MP3 audio that Streamlit can play with st.audio().

  Limitation: No fine-grained voice control (pitch, timbre).
  Future swap: ElevenLabs / Bark for character-specific voices (Phase 6).

  ARCHITECT'S NOTE on NPC Voice Profiles:
    Each NPC has a 'voice_speed' setting:
      - Kagetora: slow=True  → brooding, deliberate delivery
      - Silas:    slow=False → smooth, quick, salesman pace

FUTURE-PROOFING:
  - Phase 6: Replace gTTS with Bark (open-source, local TTS) for distinct
    NPC voices with emotion and accent control.
  - Phase 7: Stream audio to Unity/Godot via WebSocket instead of playing
    it in the browser. NPCs speak inside the game world.
"""

import io
import os
import tempfile
from pathlib import Path


# ─────────────────────────────────────────────
# DEPENDENCY GUARDS
# ─────────────────────────────────────────────

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

# Groq client is always available (required for the app to run)
# We import it from brain.py's client instead of creating a new one


# ─────────────────────────────────────────────
# NPC VOICE PROFILES
# ─────────────────────────────────────────────
# Controls how gTTS renders each NPC's speech.
# Add entries here when new NPCs are added.

NPC_VOICE_PROFILES: dict[str, dict] = {
    "⚔️ The Cursed Samurai": {
        "slow":   True,            # Deliberate, weighted delivery
        "lang":   "en",
        "label":  "Brooding · Slow · Ancient",
    },
    "🪙 The Grey Merchant": {
        "slow":   False,           # Smooth, quick, salesman pace
        "lang":   "en",
        "label":  "Smooth · Quick · Silver-tongued",
    },
    # Default for custom NPCs
    "_default": {
        "slow":   False,
        "lang":   "en",
        "label":  "Neutral",
    },
}


class VoiceIO:
    """
    Handles speech-to-text and text-to-speech for NPC conversations.

    Usage:
        voice = VoiceIO(groq_client)
        text  = voice.transcribe(audio_bytes)   # STT
        audio = voice.synthesize(text, npc_key)  # TTS → MP3 bytes
    """

    WHISPER_MODEL = "whisper-large-v3-turbo"  # Groq's hosted Whisper

    def __init__(self, groq_client):
        """
        Args:
            groq_client: The initialized Groq client from brain.py.
                         We reuse it instead of creating a duplicate.
        """
        self.client = groq_client

    # ──────────────────────────────────────────
    # STT — Groq Whisper
    # ──────────────────────────────────────────

    def transcribe(self, audio_bytes: bytes, language: str = "en") -> str:
        """
        Transcribe audio bytes to text using Groq's Whisper.

        ARCHITECT'S NOTE on the temp file:
          The Groq API requires a file-like object WITH a filename
          (it uses the extension to detect the audio format).
          st.audio_input returns WAV format, so we write a .wav temp file.

        Args:
            audio_bytes: Raw audio bytes (WAV format from st.audio_input).
            language:    BCP-47 language code hint (helps accuracy).

        Returns:
            Transcribed text string, or "" on failure.
        """
        if not audio_bytes:
            return ""

        # Write to a temp file (Groq SDK needs filename for format detection)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False, dir=_get_tmp_dir()
            ) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            with open(tmp_path, "rb") as audio_file:
                transcription = self.client.audio.transcriptions.create(
                    model=self.WHISPER_MODEL,
                    file=audio_file,
                    language=language,
                    response_format="text",
                )
            # response_format="text" returns a plain string
            return str(transcription).strip()

        except Exception as e:
            error_str = str(e)
            if "rate_limit" in error_str or "429" in error_str:
                return "[VOICE_ERROR: Rate limit. Wait a moment and try again.]"
            return f"[VOICE_ERROR: {error_str[:80]}]"

        finally:
            if tmp_path and Path(tmp_path).exists():
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    # ──────────────────────────────────────────
    # TTS — gTTS
    # ──────────────────────────────────────────

    def synthesize(self, text: str, npc_key: str = "_default") -> bytes | None:
        """
        Convert NPC response text to MP3 audio bytes using gTTS.

        Args:
            text:    The NPC's response text (markdown/italics will be stripped).
            npc_key: NPC roster key (used to select voice profile).

        Returns:
            MP3 audio as bytes, or None if gTTS is unavailable or text is empty.
        """
        if not GTTS_AVAILABLE:
            return None

        clean_text = _strip_markdown(text)
        if not clean_text:
            return None

        profile  = NPC_VOICE_PROFILES.get(npc_key, NPC_VOICE_PROFILES["_default"])

        try:
            tts    = gTTS(text=clean_text, lang=profile["lang"], slow=profile["slow"])
            buffer = io.BytesIO()
            tts.write_to_fp(buffer)
            buffer.seek(0)
            return buffer.read()
        except Exception:
            return None

    def get_voice_label(self, npc_key: str) -> str:
        """Returns a human-readable label for an NPC's voice style."""
        return NPC_VOICE_PROFILES.get(npc_key, NPC_VOICE_PROFILES["_default"])["label"]

    @staticmethod
    def is_tts_available() -> bool:
        """Check if gTTS is installed."""
        return GTTS_AVAILABLE


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _get_tmp_dir() -> str:
    """Returns a writable temp directory inside the project for audio files."""
    tmp_dir = Path("data/audio_tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return str(tmp_dir)


def _strip_markdown(text: str) -> str:
    """
    Strip markdown formatting from text before TTS synthesis.
    TTS reads asterisks and brackets aloud otherwise.

    Removes: *italics*, **bold**, [brackets], # headers
    """
    import re
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)   # *italic* **bold***
    text = re.sub(r'\[([^\]]*)\]', r'\1', text)            # [text]
    text = re.sub(r'^\s*#+\s*', '', text, flags=re.M)      # # Headers
    text = re.sub(r'`[^`]*`', '', text)                    # `code`
    text = re.sub(r'\n+', '. ', text)                      # newlines → pauses
    text = re.sub(r'\.{2,}', '.', text)                    # collapse ...
    return text.strip()
