"""
memory.py — The Dual-Layer Memory System of NPC-Forge
-------------------------------------------------------
This module solves one of the hardest problems in LLM applications:
"How do you give an AI a LONG memory without hitting token limits?"

THE PROBLEM:
  Groq's LLaMA 3.3 70B has a ~32k token context window.
  A long conversation eats through this fast.
  If you pass ALL messages every time → slow + expensive + eventually crashes.
  If you only pass RECENT messages → NPC forgets everything from earlier.

OUR SOLUTION — Two-layer memory:
  ┌────────────────────────────────────────────────────────┐
  │  Layer 1: SHORT-TERM (sliding window)                  │
  │  Last 10 messages passed verbatim to the API.          │
  │  The NPC has perfect recall of recent conversation.    │
  ├────────────────────────────────────────────────────────┤
  │  Layer 2: LONG-TERM (LLM-compressed relationship memo) │
  │  Every 20 messages, Groq compresses the older history  │
  │  into a rich "relationship summary" injected into the  │
  │  system prompt. Think of it as the NPC's "diary."      │
  └────────────────────────────────────────────────────────┘

FUTURE-PROOFING (10-Year Vision):
  - Phase 3: Replace the string summary with a ChromaDB vector store.
    The NPC will do semantic search over its memories.
  - Phase 5: Persist summaries to disk → NPCs remember players across
    MULTIPLE sessions (true long-term memory).
  - Phase 7: Export memories to a game engine via API.
"""

from groq import Groq


class MemoryManager:
    """
    Manages the two-layer memory system for a single NPC-player session.

    Usage:
        memory = MemoryManager(groq_client, model_name, npc_name)
        
        # After each full exchange (user + NPC):
        memory.maybe_summarize(all_messages)

        # Before each API call:
        recent, injection = memory.get_context(all_messages)
        # Pass 'recent' to brain.think() and inject 'injection' into system prompt
    """

    SHORT_TERM_LIMIT = 10       # Messages to pass verbatim to the API (5 exchanges)
    SUMMARIZE_EVERY  = 20       # Trigger compression every N total messages

    def __init__(self, groq_client: Groq, model: str, npc_name: str):
        """
        Args:
            groq_client: The initialized Groq client (shared from brain.py)
            model:       The LLM model ID
            npc_name:    Used to frame the summary correctly (e.g., "Kagetora")
        """
        self.client   = groq_client
        self.model    = model
        self.npc_name = npc_name

        # The compressed relationship memo (grows richer over time)
        self.long_term_summary: str = ""
        
        # Tracks how many messages were in scope for the last summary
        self._last_summarized_at: int = 0

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────

    def maybe_summarize(self, all_messages: list[dict]) -> bool:
        """
        Check if it's time to summarize, and do so if needed.

        ARCHITECT'S NOTE on WHEN to summarize:
          We trigger when total messages are a multiple of SUMMARIZE_EVERY
          AND we haven't summarized this batch yet.
          This means summaries happen at message counts: 20, 40, 60...

        Args:
            all_messages: The full conversation history (for UI rendering).
        
        Returns:
            True if a new summary was generated, False otherwise.
        """
        total = len(all_messages)

        # Condition: enough messages AND we haven't done this batch yet
        if (total >= self.SUMMARIZE_EVERY and
                total // self.SUMMARIZE_EVERY > self._last_summarized_at // self.SUMMARIZE_EVERY):

            # Summarize everything EXCEPT the most recent SHORT_TERM_LIMIT messages
            # (those will stay verbatim for the API)
            messages_to_compress = all_messages[:-self.SHORT_TERM_LIMIT]

            if messages_to_compress:
                self.long_term_summary = self._compress(messages_to_compress)
                self._last_summarized_at = total
                return True

        return False

    def get_context(self, all_messages: list[dict]) -> tuple[list[dict], str]:
        """
        Returns everything needed for an API call:
          1. The recent message slice (for the API's 'messages' array)
          2. The memory injection string (for the system prompt)

        Args:
            all_messages: Full conversation history.

        Returns:
            (recent_messages, memory_injection_string)
        """
        recent = all_messages[-self.SHORT_TERM_LIMIT:]

        # Build the injection string
        if self.long_term_summary:
            omitted_count = max(0, len(all_messages) - self.SHORT_TERM_LIMIT)
            injection = (
                f"\n\n[YOUR RELATIONSHIP MEMORY — {omitted_count} earlier messages compressed]\n"
                f"{self.long_term_summary}\n"
                f"[End of compressed memory. Recent {len(recent)} messages follow in full.]\n"
            )
        else:
            injection = ""  # No summary yet — conversation is still fresh

        return recent, injection

    def reset(self):
        """Clear all memory. Call when the user switches NPCs or resets chat."""
        self.long_term_summary = ""
        self._last_summarized_at = 0

    # ──────────────────────────────────────────
    # Private: Compression via Groq
    # ──────────────────────────────────────────

    def _compress(self, messages: list[dict]) -> str:
        """
        Use Groq to compress a batch of messages into a relationship memo.

        ARCHITECT'S NOTE:
          This uses a LOW temperature (0.2) because we want factual,
          concise compression — not creative interpretation.
          The NPC's 'perspective' makes it feel like a personal diary,
          not a cold transcript.
        """
        # Format conversation as readable text
        convo_text = "\n".join([
            f"{'[Player]' if m['role'] == 'user' else f'[{self.npc_name}]'}: {m['content']}"
            for m in messages
        ])

        # Build the prompt for the summarizer
        summarizer_prompt = f"""You are a memory compression system for an AI character named {self.npc_name}.

PREVIOUS RELATIONSHIP SUMMARY (may be empty if first compression):
{self.long_term_summary or "This is the first compression. No prior summary exists."}

NEW CONVERSATION TO COMPRESS:
{convo_text}

TASK: Write an updated, concise relationship summary from {self.npc_name}'s perspective (max 200 words).
Include:
- Key topics the player brought up
- The player's apparent personality, goals, and motivations
- Any emotional dynamics (moments of tension, trust, respect)
- Important facts {self.npc_name} learned about the player
- Any deals, promises, or significant events
- The current emotional tone of the relationship

Write in third person (e.g., "The wanderer asked about the Oni Seals twice...").
Be specific and factual. Avoid vague generalities."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": summarizer_prompt}],
                temperature=0.2,
                max_tokens=250,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            # If summarization fails, keep the old summary rather than crashing
            return self.long_term_summary or f"[Memory compression failed: {e}]"
