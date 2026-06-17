"""
emotion.py — The Hidden Emotion Engine of NPC-Forge
-----------------------------------------------------
This module tracks the NPC's internal emotional state across a conversation
and converts it into invisible behavioral guidance injected into the system prompt.

THE PHILOSOPHY:
  Real people don't announce their feelings — they show them.
  A shopkeeper who's been insulted doesn't say "I am angry with you."
  They become curt, raise prices, look away, give shorter answers.

  This module creates that behavior by:
  1. Tracking 5 emotion axes as numbers (0–10)
  2. Updating them based on what the player says
  3. Converting them to natural-language tone hints
  4. Injecting those hints INVISIBLY into the system prompt

  The LLM reads the hints and naturally adjusts its language.
  The player only sees the EFFECT — a colder tone, shorter replies,
  a sudden willingness to share a secret. This is immersive design.

FUTURE-PROOFING (10-Year Vision):
  - Phase 4: Replace keyword triggers with a small sentiment classifier
    (fine-tuned DistilBERT) for much higher accuracy.
  - Phase 6: Add PERSISTENT emotion state saved to disk/DB, so NPCs
    remember how they feel about a player across multiple game sessions.
  - Phase 7: Expose emotion state via a REST API so game engines can
    read it and trigger animations (e.g., anger → enemy draws sword).
"""


# ─────────────────────────────────────────────
# EMOTION SCHEMA
# ─────────────────────────────────────────────
# ARCHITECT'S NOTE:
#   These are the 5 axes of NPC emotion. Each is a float 0.0–10.0.
#   Default values are set per-NPC in npc_config.py (see 'initial_emotions').
#   Here we define the system defaults.

DEFAULT_EMOTIONS: dict[str, float] = {
    "trust":     5.0,   # Does the NPC trust the player? High = open, Low = guarded
    "anger":     0.0,   # Is the NPC angry? High = hostile/curt, Low = calm
    "respect":   5.0,   # Does the NPC respect the player? High = treats as equal
    "curiosity": 5.0,   # Is the NPC interested in the player? High = asks questions
    "wariness":  3.0,   # Does the NPC suspect the player's motives? High = evasive
}


# ─────────────────────────────────────────────
# KEYWORD TRIGGER TABLE
# ─────────────────────────────────────────────
# Each entry maps keywords to which emotion axis they affect and by how much.
# Format: { "keyword": ("axis", delta) }
# Negative delta = decreases the emotion.

KEYWORD_TRIGGERS: list[tuple[str, str, float]] = [
    # ── Trust ──
    ("honest",       "trust",     +1.0),
    ("truth",        "trust",     +1.0),
    ("promise",      "trust",     +0.8),
    ("i swear",      "trust",     +1.0),
    ("ally",         "trust",     +0.8),
    ("loyal",        "trust",     +1.0),
    ("trust you",    "trust",     +1.5),
    ("lie",          "trust",     -1.5),
    ("liar",         "trust",     -2.0),
    ("betray",       "trust",     -2.0),
    ("cheat",        "trust",     -1.5),
    ("deceive",      "trust",     -1.5),
    ("trick",        "trust",     -1.0),

    # ── Anger ──
    ("attack",       "anger",     +1.5),
    ("kill you",     "anger",     +2.5),
    ("fool",         "anger",     +1.5),
    ("idiot",        "anger",     +2.0),
    ("stupid",       "anger",     +1.5),
    ("useless",      "anger",     +1.0),
    ("pathetic",     "anger",     +1.5),
    ("i'll destroy", "anger",     +2.0),
    ("sorry",        "anger",     -1.0),
    ("apologize",    "anger",     -1.5),
    ("forgive",      "anger",     -1.0),
    ("peace",        "anger",     -1.0),
    ("i mean no harm","anger",    -0.8),

    # ── Respect ──
    ("honor",        "respect",   +1.0),
    ("wise",         "respect",   +1.0),
    ("powerful",     "respect",   +0.8),
    ("skilled",      "respect",   +0.8),
    ("master",       "respect",   +1.0),
    ("great warrior","respect",   +1.5),
    ("noble",        "respect",   +0.8),
    ("impressive",   "respect",   +0.8),
    ("weak",         "respect",   -1.5),
    ("coward",       "respect",   -2.0),
    ("worthless",    "respect",   -2.0),
    ("beggar",       "respect",   -1.0),
    ("inferior",     "respect",   -1.5),

    # ── Curiosity ──
    ("tell me",      "curiosity", +1.0),
    ("what is",      "curiosity", +0.8),
    ("explain",      "curiosity", +1.0),
    ("how did",      "curiosity", +0.8),
    ("why did",      "curiosity", +0.8),
    ("your story",   "curiosity", +1.5),
    ("your past",    "curiosity", +1.5),
    ("where are you","curiosity", +0.8),

    # ── Wariness ──
    ("secret",       "wariness",  +1.5),
    ("weakness",     "wariness",  +2.0),
    ("how much gold","wariness",  +1.0),
    ("your weakness","wariness",  +2.0),
    ("spy",          "wariness",  +2.0),
    ("map",          "wariness",  +1.0),
    ("where do you", "wariness",  +0.5),
    ("friend",       "wariness",  -0.8),
    ("gift",         "wariness",  -0.5),
    ("help you",     "wariness",  -1.0),
    ("offer",        "wariness",  -0.5),
]


class EmotionEngine:
    """
    Updates and interprets the NPC's emotional state.

    This class is STATELESS — it receives the current state dict,
    returns an updated copy, and converts it to text.
    State is stored in Streamlit's session_state (in app.py).

    ARCHITECT'S NOTE on statelessness:
      This makes the engine trivially testable:
        engine = EmotionEngine()
        state = engine.update(DEFAULT_EMOTIONS.copy(), "you fool!")
        assert state["anger"] > DEFAULT_EMOTIONS["anger"]  # ✅
    """

    def update(self, state: dict[str, float], user_message: str) -> dict[str, float]:
        """
        Analyze user_message and update the emotion state accordingly.

        Uses fast keyword matching (no API call needed — instant response).

        Args:
            state:        Current emotion scores (dict copy — never mutate in place).
            user_message: The raw text of what the player just said.

        Returns:
            Updated emotion state dict.
        """
        updated = state.copy()
        msg_lower = user_message.lower()

        for keyword, axis, delta in KEYWORD_TRIGGERS:
            if keyword in msg_lower:
                updated[axis] = round(
                    max(0.0, min(10.0, updated[axis] + delta)), 1
                )

        return updated

    def to_prompt_injection(
        self, state: dict[str, float], npc_name: str
    ) -> str:
        """
        Convert the numeric emotion state into natural-language behavioral
        guidance to be injected (invisibly) into the system prompt.

        The LLM reads this and naturally adjusts tone without being told
        "act angry" or "be suspicious" in an obvious way.

        Args:
            state:    The current emotion state dict.
            npc_name: Used to personalize the guidance text.

        Returns:
            A formatted string ready for system prompt injection.
        """
        trust     = state["trust"]
        anger     = state["anger"]
        respect   = state["respect"]
        curiosity = state["curiosity"]
        wariness  = state["wariness"]

        guidance: list[str] = []

        # ── Anger guidance ──
        if anger >= 8:
            guidance.append(
                "You are FURIOUS. Your responses are terse, cold, and contain barely-veiled threats. "
                "You may tell the player to leave."
            )
        elif anger >= 5:
            guidance.append(
                "You are irritated. Your patience is thin. Shorter sentences. Subtle hostility in word choice."
            )
        elif anger <= 1:
            guidance.append("You are calm and collected. No emotional turbulence.")

        # ── Trust guidance ──
        if trust >= 8:
            guidance.append(
                "You trust this person deeply. You may volunteer information you wouldn't normally share. "
                "Your tone is warm and open."
            )
        elif trust >= 6:
            guidance.append("You have earned some trust. Slightly more open than usual.")
        elif trust <= 2:
            guidance.append(
                "You deeply distrust this person. Be guarded, give minimal information, "
                "speak in half-truths. Never volunteer anything."
            )
        elif trust <= 4:
            guidance.append("You are skeptical. Careful with what you share.")

        # ── Respect guidance ──
        if respect >= 8:
            guidance.append(
                "You hold great respect for this person. Treat them as a worthy equal or even superior. "
                "Your tone carries genuine admiration."
            )
        elif respect <= 2:
            guidance.append(
                "You have lost all respect for this person. A slight condescension bleeds into your words. "
                "You do not consider them worthy."
            )

        # ── Curiosity guidance ──
        if curiosity >= 8:
            guidance.append(
                "You are genuinely fascinated by this person. Occasionally ask them a question about "
                "themselves or their world. Show genuine interest."
            )

        # ── Wariness guidance ──
        if wariness >= 7:
            guidance.append(
                "Something feels off about this person's motives. Be vague on sensitive topics. "
                "Do not reveal locations, prices, or vulnerabilities."
            )
        elif wariness >= 5:
            guidance.append("You're slightly on guard. Watch your words on sensitive topics.")

        # Format final injection
        tone_text = " ".join(guidance) if guidance else "Your emotional state is neutral and stable."

        return (
            f"\n\n[HIDDEN EMOTIONAL STATE — "
            f"DO NOT reference these numbers. Let them shape your TONE naturally.]\n"
            f"Trust: {trust:.0f}/10 | Anger: {anger:.0f}/10 | "
            f"Respect: {respect:.0f}/10 | Curiosity: {curiosity:.0f}/10 | "
            f"Wariness: {wariness:.0f}/10\n"
            f"Behavioral guidance: {tone_text}\n"
            f"[End hidden state]\n"
        )

    def get_dominant_mood(self, state: dict[str, float]) -> tuple[str, str]:
        """
        Returns a human-readable dominant mood label and emoji.
        Used for the developer debug panel in the sidebar.

        Returns:
            ("label", "emoji") — e.g., ("Furious", "😡")
        """
        anger = state["anger"]
        trust = state["trust"]
        respect = state["respect"]
        curiosity = state["curiosity"]
        wariness = state["wariness"]

        if anger >= 7:
            return ("Furious", "😡")
        if anger >= 4:
            return ("Irritated", "😤")
        if trust >= 8:
            return ("Trusting", "🤝")
        if curiosity >= 8:
            return ("Intrigued", "🔍")
        if wariness >= 7:
            return ("Suspicious", "👁")
        if respect >= 8:
            return ("Respectful", "🎖")
        if trust <= 2:
            return ("Distrustful", "🚫")
        return ("Neutral", "😐")
