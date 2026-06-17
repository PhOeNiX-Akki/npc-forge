"""
api.py — The NPC-Forge REST API
---------------------------------
Run this alongside Streamlit to give game developers an HTTP interface:

    uvicorn api:app --host 0.0.0.0 --port 8000 --reload

Game engines (Unity, Godot, Pygame) can then call:

    POST http://localhost:8000/v1/chat
    {
      "player_id":  "player_01",
      "npc_id":     "⚔️ The Cursed Samurai",
      "message":    "Tell me about the Oni Seals"
    }

THE PRODUCT ENDPOINT: POST /v1/npc/forge
  This is what indie developers pay for in the future.
  Send a character sheet (name, personality, lore) →
  Get back an `npc_id` that immediately works in /v1/chat.
  The NPC has full memory, emotion, and RAG from day one.

ARCHITECT'S NOTE on Authentication:
  Phase 4 has NO auth — the API runs locally or on a private server.
  Phase 5 will add API keys issued per developer account.
  Phase 6 will add rate limiting and a freemium tier.

FUTURE-PROOFING:
  - Phase 5: Add JWT auth + per-developer API keys (FastAPI OAuth2 or a
    simple token table in SQLite).
  - Phase 6: Add WebSocket endpoint for streaming NPC responses character
    by character (much more game-like than waiting for full response).
  - Phase 7: Multi-tenant deployment on cloud (Railway, Fly.io).
"""

from fastapi import FastAPI, HTTPException, Query, Security, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional
import json
import os

from engine import NPCForgeEngine
from persistence import PlayerProfile
from npc_config import NPC_ROSTER, DEFAULT_MODEL
from emotion import DEFAULT_EMOTIONS


# ─────────────────────────────────────────────
# APP SETUP
# ─────────────────────────────────────────────

app = FastAPI(
    title="🔨 NPC-Forge API",
    description="""
**Autonomous NPC Engine for Indie Game Developers**

Give your game NPCs genuine personality, persistent memory, and lore awareness.

## Quick Start

1. `GET /v1/npcs` — See available NPCs
2. `POST /v1/chat` — Have a conversation
3. `POST /v1/npc/forge` — Create your own NPC

## The Core Concept

NPCs built with NPC-Forge:
- **Remember** players across sessions (emotion + relationship memory persists)  
- **Know their world** (RAG retrieves relevant lore per conversation turn)
- **Feel** (5-axis hidden emotion state shapes every response invisibly)

Powered by Groq (LLaMA 3.3 70B) + ChromaDB.
""",
    version="0.4.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Key Security Schema
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=True)

async def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    expected_key = os.environ.get("NPC_FORGE_API_KEY", "forge_dev_key_123")
    if api_key != expected_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid API Key. Access denied. Please set the X-API-Key header."
        )
    return api_key

# Shared engine singleton (one instance for the whole API server)
_engine: NPCForgeEngine | None = None

def get_engine() -> NPCForgeEngine:
    global _engine
    if _engine is None:
        _engine = NPCForgeEngine.get()
    return _engine


# ─────────────────────────────────────────────
# REQUEST / RESPONSE MODELS
# ─────────────────────────────────────────────

class ChatRequest(BaseModel):
    player_id:            str   = Field(...,  description="Unique player identifier (string, e.g. 'player_01')")
    npc_id:               str   = Field(...,  description="NPC roster ID from GET /v1/npcs")
    message:              str   = Field(...,  description="The player's message (max 1000 chars)", max_length=1000)
    temperature:          float = Field(0.85, description="Creativity dial: 0.1 (robotic) to 1.5 (chaotic)", ge=0.1, le=1.5)
    conversation_history: list[dict] = Field(
        default_factory=list,
        description="Recent messages: [{role: 'user'|'assistant', content: '...'}]. "
                    "Max 10 entries. The API will use these for context."
    )

    model_config = {"json_schema_extra": {
        "example": {
            "player_id": "hero_player",
            "npc_id": "⚔️ The Cursed Samurai",
            "message": "Tell me about the Oni Seals",
            "temperature": 0.85,
            "conversation_history": [],
        }
    }}


class ChatResponse(BaseModel):
    response:                str
    npc_name:                str
    npc_id:                  str
    emotion_state:           dict[str, float]
    long_term_memory_active: bool
    model_used:              str


class TavernRequest(BaseModel):
    player_id:   str   = Field(...,  description="Player identifier")
    message:     str   = Field(...,  description="Message (use @NPC_name: prefix to address a specific NPC)")
    active_npcs: list[str] = Field(
        default_factory=lambda: list(NPC_ROSTER.keys())[:2],
        description="List of NPC IDs to include in the scene",
    )
    temperature: float = Field(0.85, ge=0.1, le=1.5)

    model_config = {"json_schema_extra": {
        "example": {
            "player_id": "hero_player",
            "message": "@Kagetora: What do you know about Mount Osore?",
            "active_npcs": ["⚔️ The Cursed Samurai", "🪙 The Grey Merchant"],
            "temperature": 0.85,
        }
    }}


class TavernMessage(BaseModel):
    speaker:     str
    npc_id:      str
    text:        str
    is_reaction: bool


class TavernResponse(BaseModel):
    messages:    list[TavernMessage]
    player_id:   str


class NPCForgeRequest(BaseModel):
    name:             str   = Field(...,  description="The NPC's display name")
    avatar:           str   = Field("🤖", description="An emoji representing the NPC")
    personality:      str   = Field(...,  description="Detailed personality description (2–5 sentences)")
    lore:             str   = Field("",   description="Background lore (longer = better RAG retrieval)")
    greeting:         str   = Field("",   description="First message the NPC sends. Auto-generated if empty.")
    initial_emotions: dict  = Field(
        default_factory=lambda: {"trust": 5.0, "anger": 0.0, "respect": 5.0, "curiosity": 5.0, "wariness": 3.0},
        description="Starting emotion scores (0–10 each)"
    )
    theme_color:  str = Field("#4a90e2", description="Primary hex color for UI theming")
    accent_color: str = Field("#f5a623", description="Accent hex color for UI theming")

    model_config = {"json_schema_extra": {
        "example": {
            "name": "The Blind Oracle",
            "avatar": "🔮",
            "personality": "A blind seer who speaks in cryptic visions. She is ancient, patient, and sees the future in fragments. She refers to herself in the third person occasionally.",
            "lore": "The Oracle lost her sight after gazing directly into the Void Gate during the collapse. In exchange, she gained the ability to perceive threads of fate. She lives in a ruined tower at the edge of the Ashlands...",
            "greeting": "*The Oracle tilts her head before you speak.* I know why you've come. Sit.",
            "initial_emotions": {"trust": 7.0, "anger": 0.0, "respect": 6.0, "curiosity": 9.0, "wariness": 2.0},
            "theme_color": "#6b2fa0",
            "accent_color": "#c084fc",
        }
    }}


class ProfileResponse(BaseModel):
    player_id:         str
    npc_id:            str
    npc_name:          str
    emotion_state:     dict[str, float]
    long_term_summary: str
    message_count:     int
    first_seen:        str
    last_seen:         str
    relationship_tier: str


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _load_player_state(player_id: str, npc_id: str) -> tuple[dict, str]:
    """Load emotion state + memory summary from disk. Returns (emotion, summary)."""
    npc          = NPC_ROSTER[npc_id]
    profile_mgr  = PlayerProfile(player_id)
    saved        = profile_mgr.load(npc_id)

    if saved:
        emotion  = saved.get("emotion_state", dict(npc.get("initial_emotions", DEFAULT_EMOTIONS)))
        summary  = saved.get("long_term_summary", "")
    else:
        emotion  = dict(npc.get("initial_emotions", DEFAULT_EMOTIONS))
        summary  = ""

    return emotion, summary


def _save_player_state(player_id: str, npc_id: str, emotion: dict, summary: str, msg_count: int):
    """Persist emotion state + memory summary to disk."""
    npc = NPC_ROSTER[npc_id]
    PlayerProfile(player_id).save(
        npc_key=npc_id,
        npc_name=npc["name"],
        emotion_state=emotion,
        long_term_summary=summary,
        message_count=msg_count,
    )


def _get_relationship_tier(trust: float) -> str:
    """Convert trust score to a narrative relationship label."""
    if   trust >= 8: return "Deep Bond"
    elif trust >= 6: return "Trusted"
    elif trust >= 4: return "Acquaintance"
    elif trust >= 2: return "Skeptical"
    else:            return "Distrustful"


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.get("/", tags=["Info"])
async def root():
    """API health check + basic info."""
    return {
        "service":    "NPC-Forge API",
        "version":    "0.4.0",
        "status":     "online",
        "npcs_loaded": len(NPC_ROSTER),
        "endpoints":  [
            "GET  /v1/npcs",
            "POST /v1/chat",
            "POST /v1/tavern",
            "GET  /v1/profile/{player_id}/{npc_id}",
            "POST /v1/npc/forge",
            "DELETE /v1/npc/{npc_id}",
        ],
        "docs": "/docs",
    }


@app.get("/v1/npcs", tags=["NPCs"], dependencies=[Depends(verify_api_key)])
async def list_npcs():
    """
    List all available NPCs with their metadata.
    Use the keys as `npc_id` in /v1/chat.
    """
    result = {}
    for npc_id, npc_data in NPC_ROSTER.items():
        engine = get_engine()
        result[npc_id] = {
            "name":              npc_data["name"],
            "avatar":            npc_data.get("avatar", "🤖"),
            "lore_chunks_in_db": engine.rag.get_chunk_count(npc_id) if engine.rag else 0,
            "initial_emotions":  npc_data.get("initial_emotions", {}),
            "is_custom":         npc_id.startswith("custom_"),
        }
    return result


@app.post("/v1/chat", response_model=ChatResponse, tags=["Chat"], dependencies=[Depends(verify_api_key)])
async def chat(req: ChatRequest):
    """
    Send a message to an NPC and receive a response.

    The API automatically:
    - Loads the player's saved relationship (emotion + memory)
    - Retrieves relevant lore from the NPC's knowledge base
    - Updates emotion state based on the message
    - Saves the updated relationship after responding

    **Conversation history tip:** Send the last 10 messages for best context.
    The API handles long-term memory compression automatically.
    """
    if req.npc_id not in NPC_ROSTER:
        raise HTTPException(
            status_code=404,
            detail=f"NPC '{req.npc_id}' not found. Use GET /v1/npcs to list available NPCs."
        )

    npc    = NPC_ROSTER[req.npc_id]
    engine = get_engine()

    # Load state
    emotion_state, long_term_summary = _load_player_state(req.player_id, req.npc_id)

    # Limit history to last 10
    history = req.conversation_history[-10:]

    # Run inference
    result = engine.run_inference(
        npc_key=req.npc_id,
        user_message=req.message,
        conversation_history=history,
        emotion_state=emotion_state,
        long_term_summary=long_term_summary,
        temperature=req.temperature,
    )

    # Save updated state
    _save_player_state(
        player_id=req.player_id,
        npc_id=req.npc_id,
        emotion=result["updated_emotion_state"],
        summary=long_term_summary,
        msg_count=len(history) + 1,
    )

    return ChatResponse(
        response=result["response"],
        npc_name=npc["name"],
        npc_id=req.npc_id,
        emotion_state=result["updated_emotion_state"],
        long_term_memory_active=bool(long_term_summary),
        model_used=DEFAULT_MODEL,
    )


@app.post("/v1/tavern", response_model=TavernResponse, tags=["Tavern"], dependencies=[Depends(verify_api_key)])
async def tavern_chat(req: TavernRequest):
    """
    Send a message in a multi-NPC tavern scene.

    Use `@NPC_name:` prefix to address a specific NPC.
    Without a prefix, the NPC with the highest curiosity score responds.

    A second NPC may spontaneously react (35% probability) — their reaction
    is also returned in the response.

    **Note:** The tavern endpoint is stateless — send `active_npcs` each time.
    Player relationships persist per NPC as usual.
    """
    valid_npcs = [k for k in req.active_npcs if k in NPC_ROSTER]
    if not valid_npcs:
        raise HTTPException(status_code=400, detail="No valid NPC IDs in active_npcs.")

    engine = get_engine()

    # Build a temporary TavernSession for this request
    from tavern import TavernSession
    session = TavernSession(engine=engine, active_keys=valid_npcs, player_name=req.player_id)

    # Load saved profiles for each NPC in the scene
    for npc_id in valid_npcs:
        emotion, summary = _load_player_state(req.player_id, npc_id)
        session.emotion_states[npc_id] = emotion
        session.memory_managers[npc_id].long_term_summary = summary

    # Run the exchange
    new_msgs = session.run_exchange(req.message, req.temperature)

    # Save updated profiles
    for npc_id in valid_npcs:
        _save_player_state(
            player_id=req.player_id,
            npc_id=npc_id,
            emotion=session.emotion_states[npc_id],
            summary=session.memory_managers[npc_id].long_term_summary,
            msg_count=len(session.npc_histories.get(npc_id, [])),
        )

    return TavernResponse(
        messages=[
            TavernMessage(
                speaker=m.speaker, npc_id=m.npc_key,
                text=m.text, is_reaction=m.is_reaction
            )
            for m in new_msgs
        ],
        player_id=req.player_id,
    )


@app.get("/v1/profile/{player_id}/{npc_id}", response_model=ProfileResponse, tags=["Profiles"], dependencies=[Depends(verify_api_key)])
async def get_profile(player_id: str, npc_id: str):
    """
    Get a player's current relationship state with an NPC.

    Useful for game engines that need to query relationship data:
    - Adjust NPC dialogue in cutscenes
    - Trigger quests based on trust level
    - Display relationship indicators in the UI
    """
    # URL-decode the npc_id (it may contain emoji when URL-encoded)
    from urllib.parse import unquote
    npc_id = unquote(npc_id)

    if npc_id not in NPC_ROSTER:
        raise HTTPException(status_code=404, detail=f"NPC '{npc_id}' not found.")

    npc         = NPC_ROSTER[npc_id]
    profile_mgr = PlayerProfile(player_id)
    saved       = profile_mgr.load(npc_id)

    if not saved:
        # Return defaults for a new player-NPC pair
        return ProfileResponse(
            player_id=player_id,
            npc_id=npc_id,
            npc_name=npc["name"],
            emotion_state=dict(npc.get("initial_emotions", DEFAULT_EMOTIONS)),
            long_term_summary="",
            message_count=0,
            first_seen="never",
            last_seen="never",
            relationship_tier="Stranger",
        )

    trust = saved.get("emotion_state", {}).get("trust", 5.0)

    return ProfileResponse(
        player_id=player_id,
        npc_id=npc_id,
        npc_name=npc["name"],
        emotion_state=saved.get("emotion_state", {}),
        long_term_summary=saved.get("long_term_summary", ""),
        message_count=saved.get("message_count", 0),
        first_seen=saved.get("first_seen", "unknown"),
        last_seen=saved.get("last_seen", "unknown"),
        relationship_tier=_get_relationship_tier(trust),
    )


@app.post("/v1/npc/forge", tags=["NPC Management"], dependencies=[Depends(verify_api_key)])
async def forge_npc(req: NPCForgeRequest):
    """
    **The Core Product Endpoint.**

    Create a new autonomous NPC from a character spec.
    The NPC immediately supports:
    - Full conversation via /v1/chat
    - Player memory persistence
    - RAG lore retrieval (if lore is provided)
    - Hidden emotion system

    The NPC persists across API restarts (saved to data/custom_npcs.json).

    Returns an `npc_id` to use in subsequent /v1/chat calls.
    """
    engine = get_engine()

    spec = {
        "name":             req.name,
        "avatar":           req.avatar,
        "personality":      req.personality,
        "lore":             req.lore,
        "greeting":         req.greeting,
        "initial_emotions": req.initial_emotions,
        "theme_color":      req.theme_color,
        "accent_color":     req.accent_color,
    }

    npc_id = engine.forge_npc(spec)

    lore_chunks = engine.rag.get_chunk_count(npc_id) if engine.rag else 0

    return {
        "status":             "forged",
        "npc_id":             npc_id,
        "name":               req.name,
        "lore_chunks_indexed": lore_chunks,
        "message": (
            f"NPC '{req.name}' forged successfully.\n"
            f"Use npc_id '{npc_id}' in POST /v1/chat to start talking.\n"
            f"Lore indexed: {lore_chunks} chunks available for RAG retrieval."
        ),
        "quick_test": {
            "url":    "POST /v1/chat",
            "body": {
                "player_id":  "test_player",
                "npc_id":     npc_id,
                "message":    "Hello",
            }
        }
    }


@app.delete("/v1/npc/{npc_id}", tags=["NPC Management"], dependencies=[Depends(verify_api_key)])
async def delete_npc(npc_id: str):
    """
    Delete a custom NPC (custom NPCs only — built-in NPCs cannot be deleted).
    """
    from urllib.parse import unquote
    npc_id = unquote(npc_id)

    if not npc_id.startswith("custom_"):
        raise HTTPException(
            status_code=403,
            detail="Built-in NPCs cannot be deleted. Only custom (forged) NPCs can be removed."
        )

    engine  = get_engine()
    success = engine.delete_npc(npc_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"NPC '{npc_id}' not found.")

    return {"status": "deleted", "npc_id": npc_id}


@app.get("/v1/health", tags=["Info"])
async def health():
    """Quick health check — confirm the service is running."""
    engine = get_engine()
    return {
        "status":         "healthy",
        "rag_available":  engine.rag is not None,
        "npcs_loaded":    len(NPC_ROSTER),
        "custom_npcs":    len([k for k in NPC_ROSTER if k.startswith("custom_")]),
    }
