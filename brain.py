"""
brain.py — The LLM Interface Layer of NPC-Forge
-------------------------------------------------
This module handles ALL communication with the Groq API.

ARCHITECT'S NOTE:
  Separating the AI logic from the UI (app.py) is called the 
  "Separation of Concerns" principle. This is critical for scaling:
  
  - Today:   Groq + LLaMA 3 (free tier)
  - Phase 4: Swap to a fine-tuned model or Ollama (local) by only
             changing THIS file. The UI never needs to change.
  - Phase 6: Add tool-calling, function dispatch, and agent loops here.

PHASE 2 CHANGE:
  Added 'context_injection' parameter to think().
  This string is appended to the system prompt and carries:
    - Long-term relationship memory (from memory.py)
    - Hidden emotion state guidance (from emotion.py)
  The NPC reads this invisible context and adjusts behavior naturally.
"""

import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()


class NPCBrain:
    """
    The AI engine powering each NPC.

    Takes a conversation history, an NPC's system prompt, and optional
    memory/emotion context, then returns the NPC's next response.
    """

    def __init__(self, model: str):
        """
        Initialize the Groq client.

        Args:
            model: The Groq model ID (e.g., 'llama-3.3-70b-versatile')
        """
        api_key = None
        # Prioritize Streamlit secrets (for Community Cloud)
        try:
            import streamlit as st
            if "GROQ_API_KEY" in st.secrets:
                api_key = st.secrets["GROQ_API_KEY"]
        except Exception:
            pass

        # Fallback to local environment variables
        if not api_key:
            api_key = os.environ.get("GROQ_API_KEY")

        if not api_key:
            raise ValueError(
                "🔑 GROQ_API_KEY not found! "
                "Please add it to your .env file or Streamlit secrets. "
                "Get your free key at: https://console.groq.com"
            )
        self.client = Groq(api_key=api_key)
        self.model  = model

    @property
    def groq_client(self) -> Groq:
        """
        Exposes the raw Groq client for use by other modules (e.g., memory.py).
        
        ARCHITECT'S NOTE:
          memory.py needs to make its own Groq calls (for summarization).
          Rather than creating a second Groq client, we share the one 
          created here. This is the "single instance" pattern.
        """
        return self.client

    def think(
        self,
        system_prompt: str,
        conversation_history: list[dict],
        temperature: float = 0.85,
        context_injection: str = "",    # ← NEW in Phase 2
    ) -> str:
        """
        The core inference call — the NPC 'thinks' and responds.

        Args:
            system_prompt:         The NPC's core personality instructions.
            conversation_history:  Recent messages [{"role": ..., "content": ...}].
                                   In Phase 2, this is the SHORT-TERM SLICE only
                                   (last 10 messages), not the full history.
            temperature:           Creativity dial (0.0 = robotic, 1.0 = chaotic).
            context_injection:     ← NEW: Memory + emotion context appended to
                                   system_prompt. The NPC reads this invisibly.

        Returns:
            The NPC's response as a plain string.

        ARCHITECT'S NOTE on the augmented system prompt:
          The final system prompt = base personality + memory + emotion.
          This creates a "layered briefing" — like giving an actor:
            1. Their character Bible (who they are)
            2. A relationship dossier (what happened so far)
            3. A mood note (how they feel RIGHT NOW)
          All three layers shape every response.
        """
        # Combine base personality with injected context
        augmented_system = system_prompt
        if context_injection:
            augmented_system = system_prompt + context_injection

        messages = [
            {"role": "system", "content": augmented_system},
            *conversation_history,
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=512,
                stream=False,
            )
            return response.choices[0].message.content

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "invalid_api_key" in error_msg:
                return "*[A dark silence falls. The spirit connection is severed.]*\n\n...Your key is not recognized by the spirit realm."
            elif "429" in error_msg or "rate_limit" in error_msg:
                return "*[The channels are overwhelmed...]*\n\nThe spirit link is strained. Rest a moment, then speak again."
            else:
                return f"*[Something tears at the connection...]*\n\n`{error_msg}`"
