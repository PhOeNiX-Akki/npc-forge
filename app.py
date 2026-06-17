"""
app.py — NPC-Forge Streamlit Interface (Phase 4)
-------------------------------------------------
Phase 4 adds four modes accessible via the sidebar:
  ⚔️ Chat    — Single-NPC conversation (Phase 1–3 core)
  🍺 Tavern  — Multi-NPC scene with overhear reactions
  🎙 Voice   — Full voice I/O (Whisper STT + gTTS)
  🔌 API     — Live API docs + example curl commands

ARCHITECT'S NOTE on app.py size:
  This file delegates heavy lifting to engine.py, tavern.py, voice.py.
  app.py is now ONLY responsible for: CSS injection, session state,
  sidebar rendering, and calling mode-specific render functions.
  Business logic lives in the module files.
"""

import streamlit as st
from engine import NPCForgeEngine
from memory import MemoryManager
from emotion import EmotionEngine, DEFAULT_EMOTIONS
from persistence import PlayerProfile
from tavern import TavernSession
from npc_config import NPC_ROSTER, DEFAULT_MODEL
from lore_ingestion import LoreIngestion

try:
    from voice import VoiceIO
    VOICE_AVAILABLE = True
except ImportError:
    VOICE_AVAILABLE = False

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="NPC-Forge",
    page_icon="⚒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# THEME
# ─────────────────────────────────────────────
def get_theme(npc_key: str) -> dict:
    npc = NPC_ROSTER.get(npc_key, {})
    return {
        "primary":  npc.get("theme_color",  "#C0392B"),
        "accent":   npc.get("accent_color", "#F39C12"),
        "gradient": npc.get("bg_gradient",  "linear-gradient(135deg,#1a0a0a,#0a0a1a)"),
    }

def hex_to_rgba(h: str, alpha: float) -> str:
    h = h.lstrip("#")
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return f"rgba({r},{g},{b},{alpha})"

def inject_css(theme: dict):
    p, a, g = theme["primary"], theme["accent"], theme["gradient"]
    p15=hex_to_rgba(p,.15); p08=hex_to_rgba(p,.08); p40=hex_to_rgba(p,.40)
    p35=hex_to_rgba(p,.35); p25=hex_to_rgba(p,.25); p10=hex_to_rgba(p,.10)
    a08=hex_to_rgba(a,.08)

    st.markdown(f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700;900&family=Inter:wght@300;400;500;600&family=Cinzel+Decorative:wght@700&display=swap');

/* Force dark backing and base text colors across all Streamlit components to override light themes */
html, body, [class*="css"], .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"], [data-testid="stSidebar"] {{
  font-family: 'Inter', sans-serif;
  background: #0d0d0d;
  color: #e8e0d0 !important;
}}
.stApp {{
  background: {g};
  min-height: 100vh;
}}

/* Universal text visibility overrides for all standard Streamlit elements */
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] p,
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] span,
[data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3,
[data-testid="stAppViewContainer"] h4,
[data-testid="stAppViewContainer"] h5,
[data-testid="stAppViewContainer"] h6,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span {{
  color: #e8e0d0 !important;
}}

[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, #120808, #1a0d0d);
  border-right: 1px solid {p40};
}}
[data-testid="collapsedControl"] {{
  position: fixed !important;
  top: 50% !important;
  left: 0 !important;
  transform: translateY(-50%) !important;
  z-index: 999999 !important;
  display: block !important;
  background: transparent !important;
  border: none !important;
}}
[data-testid="collapsedControl"] button {{
  width: 48px !important;
  height: 60px !important;
  background: linear-gradient(135deg, {p}, {a}) !important;
  color: #fff !important;
  border: 2px solid {a} !important;
  border-left: none !important;
  border-radius: 0 12px 12px 0 !important;
  box-shadow: 4px 0 15px {hex_to_rgba(a, 0.4)} !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  cursor: pointer !important;
  transition: all 0.3s ease !important;
}}
[data-testid="collapsedControl"] button:hover {{
  width: 56px !important;
  box-shadow: 6px 0 25px {a} !important;
}}
[data-testid="collapsedControl"] button svg {{
  fill: #ffffff !important;
  width: 30px !important;
  height: 30px !important;
}}

.forge-title {{
  font-family: 'Cinzel Decorative', serif;
  font-size: 2rem;
  font-weight: 700;
  background: linear-gradient(90deg, {p}, {a}, {p});
  background-size: 200%;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: shimmer 3s infinite linear;
  text-align: center;
}}
@keyframes shimmer {{
  0% {{ background-position: 0% 50% }}
  100% {{ background-position: 200% 50% }}
}}
.forge-subtitle {{
  text-align: center;
  color: #a8988a !important;
  font-size: 0.75rem;
  letter-spacing: 0.25em;
  text-transform: uppercase;
  margin-bottom: 1.5rem;
}}

/* NPC card */
.npc-card {{
  background: linear-gradient(135deg, {p15}, {a08});
  border: 1px solid {p40};
  border-radius: 12px;
  padding: 1.2rem 1.5rem;
  margin-bottom: 1.5rem;
  position: relative;
  overflow: hidden;
}}
.npc-card::before {{
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, {p}, {a}, transparent);
}}
.npc-name {{
  font-family: 'Cinzel', serif;
  font-size: 1.3rem;
  font-weight: 700;
  color: {a} !important;
}}
.npc-tagline {{
  color: #cbb8a9 !important;
  font-size: 0.8rem;
  font-style: italic;
}}
.npc-status {{
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.6rem;
  font-size: 0.72rem;
  color: #a8988a !important;
}}
.status-dot {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #2ecc71;
  box-shadow: 0 0 8px #2ecc71;
  animation: pulse 2s infinite;
}}
@keyframes pulse {{
  0%, 100% {{ opacity: 1 }}
  50% {{ opacity: 0.4 }}
}}

/* Chat bubbles */
.user-bubble {{
  display: flex;
  justify-content: flex-end;
  margin: 0.8rem 0;
  animation: sIR 0.3s ease;
}}
.user-bubble-inner {{
  background: linear-gradient(135deg, #1a3a5c, #2d527a);
  border: 1px solid rgba(52, 152, 219, .4);
  border-radius: 18px 18px 4px 18px;
  padding: .8rem 1.2rem;
  max-width: 70%;
  color: #ffffff !important;
  font-size: .95rem;
  line-height: 1.5;
}}
.user-bubble-inner * {{
  color: #ffffff !important;
}}

.npc-bubble {{
  display: flex;
  gap: .8rem;
  margin: .8rem 0;
  animation: sIL 0.3s ease;
}}
.npc-avatar {{
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: linear-gradient(135deg, #1a0808, {p});
  border: 2px solid {p};
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  flex-shrink: 0;
  box-shadow: 0 0 15px {p25};
}}
.npc-bubble-inner {{
  background: linear-gradient(135deg, rgba(20, 10, 10, .95), rgba(10, 5, 15, .95));
  border: 1px solid {p35};
  border-radius: 4px 18px 18px 18px;
  padding: .9rem 1.3rem;
  max-width: 75%;
  color: #f5f0e6 !important;
  font-size: .95rem;
  line-height: 1.6;
  box-shadow: 0 4px 20px {p10};
}}
.npc-bubble-inner * {{
  color: #f5f0e6 !important;
}}
/* Dynamic high-contrast styling for italic lore/actions in NPC bubble */
.npc-bubble-inner em {{
  color: #ffd899 !important;
  font-style: italic !important;
  font-weight: 500 !important;
}}
.npc-speaker-name {{
  font-family: 'Cinzel', serif;
  font-size: .75rem;
  color: {a} !important;
  text-transform: uppercase;
  letter-spacing: .1em;
  margin-bottom: .3rem;
  font-weight: 700 !important;
}}
.reaction-label {{
  font-size: .65rem;
  color: #a8988a !important;
  font-style: italic;
  margin-bottom: .2rem;
}}

/* Welcome screen */
.welcome-card {{
  background: linear-gradient(135deg, {p15}, {a08});
  border: 1px solid {p40};
  border-radius: 16px;
  padding: 2.5rem;
  max-width: 480px;
  width: 100%;
  margin: auto;
  position: relative;
  overflow: hidden;
}}
.welcome-card::before {{
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, {p}, {a}, transparent);
}}

/* Sidebar info boxes */
.s-title {{
  font-family: 'Cinzel', serif;
  font-size: .7rem;
  color: {a} !important;
  letter-spacing: .12em;
  text-transform: uppercase;
  margin-bottom: .4rem;
  font-weight: 700 !important;
}}
.info-box {{
  background: {p08};
  border-left: 3px solid {p};
  border-radius: 0 8px 8px 0;
  padding: .7rem .9rem;
  margin: .4rem 0;
  font-size: .78rem;
  color: #cbb8a9 !important;
  line-height: 1.5;
  font-style: italic;
}}
.emo-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: .4rem;
  margin: .5rem 0;
}}
.emo-chip {{
  background: {p08};
  border: 1px solid {p40};
  border-radius: 6px;
  padding: .3rem .5rem;
  font-size: .7rem;
  color: #cbb8a9 !important;
  text-align: center;
}}
.emo-chip-lbl {{
  color: {a} !important;
  font-weight: 600;
  display: block;
}}

/* Form inputs & selectboxes styling */
.stTextInput input {{
  background: rgba(20, 10, 10, .8) !important;
  border: 1px solid {p40} !important;
  border-radius: 12px !important;
  color: #e8e0d0 !important;
  font-family: 'Inter', sans-serif !important;
  padding: .8rem 1.2rem !important;
  transition: border-color .3s, box-shadow .3s;
}}
.stTextInput input:focus {{
  border-color: {p} !important;
  box-shadow: 0 0 20px {p25} !important;
}}
.stTextInput input::placeholder {{
  color: #8a7a7a !important;
}}
.stButton>button {{
  background: linear-gradient(135deg, #3a1a1a, {p}) !important;
  color: #fff !important;
  border: none !important;
  border-radius: 10px !important;
  font-family: 'Cinzel', serif !important;
  letter-spacing: .05em !important;
  transition: all .3s !important;
}}
.stButton>button:hover {{
  box-shadow: 0 0 20px {p25} !important;
  transform: translateY(-1px) !important;
}}

/* Dropdown select box visibility fixes */
.stSelectbox div[data-baseweb="select"] div,
.stSelectbox select,
.stSelectbox div {{
  color: #e8e0d0 !important;
}}
.stSelectbox>div>div {{
  background: rgba(20, 10, 10, .8) !important;
  border: 1px solid {p40} !important;
  border-radius: 8px !important;
}}

/* Custom theme for popovers / selectbox options dropdown list */
div[data-baseweb="popover"], div[role="listbox"] {{
  background-color: #150808 !important;
  border: 1px solid {p40} !important;
}}
div[data-baseweb="popover"] ul li, div[role="listbox"] li {{
  background-color: transparent !important;
  color: #e8e0d0 !important;
}}
div[data-baseweb="popover"] ul li:hover, div[role="listbox"] li[aria-selected="true"], div[role="listbox"] li:hover {{
  background-color: {p35} !important;
  color: #ffffff !important;
}}

/* Slider labels and parameters */
.stSlider [data-testid="stWidgetLabel"] p {{
  color: #e8e0d0 !important;
}}
.stSlider div {{
  color: #e8e0d0 !important;
}}

hr {{
  border: none !important;
  border-top: 1px solid {p40} !important;
  margin: 1rem 0 !important;
  opacity: .3 !important;
}}
.forge-footer {{
  text-align: center;
  color: #5a4a4a !important;
  font-size: .7rem;
  letter-spacing: .1em;
  padding: 1rem;
  text-transform: uppercase;
}}

/* Tavern scene */
.tavern-header {{
  background: linear-gradient(90deg, {p15}, {a08});
  border: 1px solid {p40};
  border-radius: 8px;
  padding: .7rem 1rem;
  margin-bottom: 1rem;
  font-size: .8rem;
  color: #cbb8a9 !important;
}}
.api-block {{
  background: #0a0a0a;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  padding: 1rem;
  font-family: monospace;
  font-size: .8rem;
  color: #aaa;
  overflow-x: auto;
  margin: .5rem 0;
}}
.api-method-get {{ color: #27ae60; font-weight: 700; }}
.api-method-post {{ color: #e67e22; font-weight: 700; }}
.api-method-del {{ color: #e74c3c; font-weight: 700; }}

@keyframes sIR {{ from {{ opacity: 0; transform: translateX(20px) }} to {{ opacity: 1; transform: translateX(0) }} }}
@keyframes sIL {{ from {{ opacity: 0; transform: translateX(-20px) }} to {{ opacity: 1; transform: translateX(0) }} }}
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
[data-testid="stHeader"] {{ background: transparent !important; }}
[data-testid="stDeployButton"] {{ display: none !important; }}
</style>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────
def init_session():
    defaults = {
        "npc_key":        list(NPC_ROSTER.keys())[0],
        "messages":       [],
        "greeted":        False,
        "temperature":    0.85,
        "player_name":    "",
        "mode":           "⚔️ Chat",
        "emotion_states": {},
        "memory_managers":{},
        # Tavern
        "tavern_session": None,
        "tavern_greeted": False,
        "tavern_npcs":    list(NPC_ROSTER.keys())[:2],
        # Voice
        "voice_transcript":"",
        "voice_response":  "",
        "voice_audio":     None,
        # Forge
        "f_name":         "",
        "f_avatar":       "🤖",
        "f_personality":  "",
        "f_lore":         "",
        "f_greeting":     "",
        "f_theme":        "#4a90e2",
        "f_accent":       "#f5a623",
        "f_trust":        5.0,
        "f_anger":        0.0,
        "f_respect":      5.0,
        "f_curiosity":    5.0,
        "f_wariness":     3.0,
        "last_loaded_template": "-- Blank Slate --",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Engine (singleton)
    if "engine" not in st.session_state:
        try:
            st.session_state.engine = NPCForgeEngine.get()
        except Exception as e:
            st.error(f"Engine init failed: {e}")
            st.stop()

    if "emotion_engine" not in st.session_state:
        st.session_state.emotion_engine = EmotionEngine()

    # Voice I/O
    if "voice_io" not in st.session_state and VOICE_AVAILABLE:
        try:
            st.session_state.voice_io = VoiceIO(
                groq_client=st.session_state.engine.brain.groq_client
            )
        except Exception:
            st.session_state.voice_io = None

    # Force sidebar open on initial load (ignores browser localstorage cache)
    if "sidebar_forced_open" not in st.session_state:
        st.session_state.sidebar_forced_open = True
        st.markdown("""
            <iframe src="javascript:void(0);" style="display:none;" onload="
                const doc = window.parent.document;
                const collapsedControl = doc.querySelector('[data-testid=\\'collapsedControl\\']');
                if (collapsedControl) {
                    const button = collapsedControl.querySelector('button');
                    if (button) { button.click(); }
                }
            "></iframe>
        """, unsafe_allow_html=True)

    _ensure_npc_state(st.session_state.npc_key)

def _ensure_npc_state(npc_key: str):
    npc = NPC_ROSTER.get(npc_key, {})
    if npc_key not in st.session_state.emotion_states:
        st.session_state.emotion_states[npc_key] = dict(npc.get("initial_emotions", DEFAULT_EMOTIONS))
    if npc_key not in st.session_state.memory_managers:
        st.session_state.memory_managers[npc_key] = MemoryManager(
            groq_client=st.session_state.engine.brain.groq_client,
            model=DEFAULT_MODEL,
            npc_name=npc.get("name","NPC"),
        )

def load_profile(npc_key: str):
    if not st.session_state.player_name: return False
    saved = PlayerProfile(st.session_state.player_name).load(npc_key)
    if saved:
        st.session_state.emotion_states[npc_key] = saved.get("emotion_state",
            dict(NPC_ROSTER[npc_key].get("initial_emotions", DEFAULT_EMOTIONS)))
        st.session_state.memory_managers[npc_key].long_term_summary = saved.get("long_term_summary","")
        return True
    return False

def save_profile(npc_key: str):
    if not st.session_state.player_name: return
    npc = NPC_ROSTER[npc_key]
    PlayerProfile(st.session_state.player_name).save(
        npc_key=npc_key, npc_name=npc["name"],
        emotion_state=st.session_state.emotion_states.get(npc_key, {}),
        long_term_summary=st.session_state.memory_managers[npc_key].long_term_summary,
        message_count=len(st.session_state.messages),
    )

init_session()
_ensure_npc_state(st.session_state.npc_key)
npc_key = st.session_state.npc_key
npc     = NPC_ROSTER[npc_key]
theme   = get_theme(npc_key)
inject_css(theme)   # Re-inject with current NPC's theme


# ═══════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════
with st.sidebar:
    p, a = theme["primary"], theme["accent"]
    player_display = st.session_state.player_name if st.session_state.player_name else "Wanderer"

    st.markdown(f"""
        <div style="text-align:center;padding:.8rem 0 .3rem 0;">
            <div style="font-family:'Cinzel Decorative',serif;font-size:1.2rem;
                background:linear-gradient(90deg,{p},{a});-webkit-background-clip:text;
                -webkit-text-fill-color:transparent;font-weight:700;">⚒ NPC-Forge</div>
            <div style="font-size:.65rem;color:#4a3a3a;letter-spacing:.2em;text-transform:uppercase;">v0.4 · Phase 4</div>
        </div>
        <div style="text-align:center;padding:.2rem 0 .4rem 0;">
            <span style="font-size:.75rem;color:{a};">⚔ {player_display}</span>
        </div><hr>
    """, unsafe_allow_html=True)

    # ── Mode Selector ──
    st.markdown(f'<div class="s-title">🗺 Mode</div>', unsafe_allow_html=True)
    mode = st.selectbox(
        "Mode",
        ["⚔️ Chat", "🍺 Tavern", "🎙 Voice", "⚒️ Forge", "🔌 API"],
        index=["⚔️ Chat","🍺 Tavern","🎙 Voice","⚒️ Forge","🔌 API"].index(st.session_state.mode),
        label_visibility="collapsed",
    )
    if mode != st.session_state.mode:
        st.session_state.mode = mode
        st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)

    if mode == "⚔️ Chat":
        # NPC Selector
        st.markdown(f'<div class="s-title">⚔ NPC</div>', unsafe_allow_html=True)
        sel = st.selectbox("NPC", list(NPC_ROSTER.keys()),
            index=list(NPC_ROSTER.keys()).index(npc_key), label_visibility="collapsed")
        if sel != npc_key:
            st.session_state.npc_key = sel
            st.session_state.messages = []; st.session_state.greeted = False
            _ensure_npc_state(sel); load_profile(sel); st.rerun()

        st.markdown("<hr>", unsafe_allow_html=True)

        # Temp
        st.markdown(f'<div class="s-title">🌡 Intensity</div>', unsafe_allow_html=True)
        st.session_state.temperature = st.slider("T", .1, 1.5, st.session_state.temperature, .05,
            label_visibility="collapsed")

        st.markdown("<hr>", unsafe_allow_html=True)

        # Emotion
        emo = st.session_state.emotion_states.get(npc_key, DEFAULT_EMOTIONS)
        ml, me = st.session_state.emotion_engine.get_dominant_mood(emo)
        st.markdown(f"""
            <div class="s-title">🧠 Mood</div>
            <div style="text-align:center;font-size:1.3rem;">{me}</div>
            <div style="text-align:center;font-family:Cinzel,serif;font-size:.8rem;color:{a};margin-bottom:.4rem;">{ml}</div>
            <div class="emo-grid">
                <div class="emo-chip"><span class="emo-chip-lbl">Trust</span>{emo['trust']:.0f}/10</div>
                <div class="emo-chip"><span class="emo-chip-lbl">Anger</span>{emo['anger']:.0f}/10</div>
                <div class="emo-chip"><span class="emo-chip-lbl">Respect</span>{emo['respect']:.0f}/10</div>
                <div class="emo-chip" style="grid-column:1/-1;"><span class="emo-chip-lbl">Wariness</span>{emo['wariness']:.0f}/10</div>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("<hr>", unsafe_allow_html=True)

        # Memory
        mem = st.session_state.memory_managers.get(npc_key)
        st.markdown(f'<div class="s-title">📜 Memory</div>', unsafe_allow_html=True)
        if mem and mem.long_term_summary:
            st.markdown(f'<div class="info-box"><b style="color:{p};font-style:normal;font-size:.65rem;">COMPRESSED</b><br>{mem.long_term_summary[:250]}...</div>',
                unsafe_allow_html=True)
        else:
            remain = max(0, 20-len(st.session_state.messages))
            st.markdown(f'<div class="info-box">{remain} more messages to first compression.</div>',
                unsafe_allow_html=True)

    elif mode == "🍺 Tavern":
        st.markdown(f'<div class="s-title">🍺 Tavern NPCs</div>', unsafe_allow_html=True)
        selected_tavern_npcs = st.multiselect(
            "NPCs in scene",
            options=list(NPC_ROSTER.keys()),
            default=st.session_state.tavern_npcs[:2],
            max_selections=4,
            label_visibility="collapsed",
        )
        if selected_tavern_npcs != st.session_state.tavern_npcs:
            st.session_state.tavern_npcs    = selected_tavern_npcs
            st.session_state.tavern_session = None
            st.session_state.tavern_greeted = False
            st.rerun()

        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown(f'<div class="s-title">🌡 Intensity</div>', unsafe_allow_html=True)
        st.session_state.temperature = st.slider("T", .1, 1.5, st.session_state.temperature, .05,
            label_visibility="collapsed")
        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown(f"""
            <div class="info-box">
                <b style="color:{p};font-style:normal;">Syntax hint:</b><br>
                @Kagetora: your question<br>
                @Silas: your question<br>
                Or just type — the room listens.
            </div>
        """, unsafe_allow_html=True)

        if st.button("🔄 Reset Scene", use_container_width=True):
            st.session_state.tavern_session = None
            st.session_state.tavern_greeted = False
            st.rerun()

    elif mode == "🎙 Voice":
        st.markdown(f'<div class="s-title">🎙 Voice NPC</div>', unsafe_allow_html=True)
        sel = st.selectbox("NPC", list(NPC_ROSTER.keys()),
            index=list(NPC_ROSTER.keys()).index(npc_key), label_visibility="collapsed")
        if sel != npc_key:
            st.session_state.npc_key = sel
            st.session_state.messages=[]; st.session_state.greeted=False
            _ensure_npc_state(sel); load_profile(sel); st.rerun()
        st.markdown("<hr>", unsafe_allow_html=True)

        if VOICE_AVAILABLE and st.session_state.get("voice_io"):
            voice_label = st.session_state.voice_io.get_voice_label(npc_key)
            st.markdown(f'<div class="info-box"><b style="color:{p};font-style:normal;">Voice Profile:</b><br>{voice_label}</div>',
                unsafe_allow_html=True)

        st.markdown(f"""
            <div class="info-box">
                STT: Groq Whisper<br>
                TTS: gTTS<br>
                Model: whisper-large-v3-turbo
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    msg_c = len(st.session_state.messages)
    st.markdown(f'<div style="font-size:.7rem;color:#4a3a3a;text-align:center;">💬 {msg_c//2} exchanges · ⚡ Groq · {player_display}</div>',
        unsafe_allow_html=True)

    if st.button("🗑 Clear Chat", use_container_width=True):
        st.session_state.messages=[]; st.session_state.greeted=False
        st.session_state.tavern_session=None; st.session_state.tavern_greeted=False
        st.rerun()
    if st.button("🔄 Switch Player", use_container_width=True):
        for k in ["player_name","messages","greeted","tavern_session","tavern_greeted",
                  "voice_transcript","voice_response","voice_audio"]:
            st.session_state[k] = "" if isinstance(st.session_state.get(k), str) else \
                                   None if st.session_state.get(k) is None else \
                                   False if isinstance(st.session_state.get(k), bool) else []
        st.session_state.player_name = ""
        st.rerun()

    st.markdown(f'<div class="forge-footer">NPC-Forge · Phase 4</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════
# WELCOME SCREEN
# ═══════════════════════════════════════════
if not st.session_state.player_name:
    known = PlayerProfile.list_all_players()
    st.markdown(f"""
        <div style="text-align:center;padding:3rem 0 1.5rem 0;">
            <div class="forge-title">⚒ NPC-Forge</div>
            <div class="forge-subtitle">Phase 4 · Tavern · Voice · API</div>
        </div>
    """, unsafe_allow_html=True)
    _, col, _ = st.columns([1,2,1])
    with col:
        st.markdown("""<div class="welcome-card">
            <div style="font-family:Cinzel,serif;font-size:1.1rem;color:#F39C12;text-align:center;margin-bottom:.4rem;">⚔ Enter the Forge</div>
            <div style="color:#7a6a5a;font-size:.8rem;text-align:center;margin-bottom:1.2rem;font-style:italic;">
            NPCs remember you across sessions.</div></div>""", unsafe_allow_html=True)

        with st.form("welcome_form"):
            name_input = st.text_input("Your Name", placeholder="e.g. Hiroshi, wanderer_42...")
            if known:
                st.caption(f"Known travelers: {', '.join(known[:5])}")
            entered = st.form_submit_button("⚔ Enter the Forge", use_container_width=True)

        if entered and name_input.strip():
            st.session_state.player_name = name_input.strip()
            for k in NPC_ROSTER:
                _ensure_npc_state(k)
                load_profile(k)
            st.rerun()
        elif entered:
            st.warning("Enter a name to continue.")
    st.stop()


# ═══════════════════════════════════════════
# MAIN CONTENT — MODE ROUTING
# ═══════════════════════════════════════════
mode = st.session_state.mode

st.markdown(f"""
    <div class="forge-title">⚒ NPC-Forge</div>
    <div class="forge-subtitle">{mode} Mode · {st.session_state.player_name}</div>
""", unsafe_allow_html=True)

# No top navigation bar on main page (controls are in the sidebar)


# ─────────────────────────────────────────────
# HELPERS — MESSAGE RENDERING
# ─────────────────────────────────────────────
def render_bubble(role: str, content: str, npc_data: dict, is_reaction: bool = False):
    if role == "user":
        html = f'<div class="user-bubble"><div class="user-bubble-inner">{content.replace(chr(10), "<br>")}</div></div>'
        st.markdown(html, unsafe_allow_html=True)
    else:
        f = content.replace("\n", "<br>")
        reaction_lbl = '<div class="reaction-label">💬 overhears...</div>' if is_reaction else ""
        html = f'<div class="npc-bubble"><div class="npc-avatar">{npc_data["avatar"]}</div><div>{reaction_lbl}<div class="npc-speaker-name">{npc_data["name"]}</div><div class="npc-bubble-inner">{f}</div></div></div>'
        st.markdown(html, unsafe_allow_html=True)


# ═══════════════════════════════════════════
# MODE: CHAT
# ═══════════════════════════════════════════
if mode == "⚔️ Chat":
    npc_key = st.session_state.npc_key
    npc     = NPC_ROSTER[npc_key]
    engine  = st.session_state.engine
    em_eng  = st.session_state.emotion_engine

    taglines = {
        "⚔️ The Cursed Samurai": '"The demon stirs... Choose your words carefully, wanderer."',
        "🪙 The Grey Merchant":  '"Everything has a price. Some things, you cannot afford."',
    }

    st.markdown(f"""<div class="npc-card">
        <div class="npc-name">{npc['avatar']} {npc['name']}</div>
        <div class="npc-tagline">{taglines.get(npc_key,'...')}</div>
        <div class="npc-status"><div class="status-dot"></div>
            <span>ACTIVE · RAG · Memory · Emotion · {st.session_state.player_name}</span>
        </div></div>""", unsafe_allow_html=True)

    # Greeting
    if not st.session_state.greeted:
        profile_mgr  = PlayerProfile(st.session_state.player_name)
        is_returning = profile_mgr.exists(npc_key)
        mem          = st.session_state.memory_managers[npc_key]

        if is_returning and mem.long_term_summary:
            with st.spinner(f"*{npc['name']} recognizes you...*"):
                greeting = engine.get_welcome_back(
                    npc_key=npc_key, player_name=st.session_state.player_name,
                    memory_summary=mem.long_term_summary,
                    emotion_state=st.session_state.emotion_states[npc_key],
                    temperature=st.session_state.temperature,
                )
        else:
            greeting = npc["greeting"]

        st.session_state.messages.append({"role":"assistant","content":greeting})
        st.session_state.greeted = True

    # Render history
    for msg in st.session_state.messages:
        render_bubble(msg["role"], msg["content"], npc)

    # Input
    st.markdown("<br>", unsafe_allow_html=True)
    with st.form("chat_form", clear_on_submit=True):
        c1, c2 = st.columns([5,1])
        with c1: user_input = st.text_input("Msg", placeholder=f"Speak to {npc['name']}...", label_visibility="collapsed")
        with c2: sent = st.form_submit_button("⚔ Send", use_container_width=True)

    if sent and user_input.strip():
        st.session_state.messages.append({"role":"user","content":user_input.strip()})

        em = st.session_state.emotion_states[npc_key]
        st.session_state.emotion_states[npc_key] = em_eng.update(em, user_input.strip())

        mem = st.session_state.memory_managers[npc_key]
        with st.spinner(f"*{npc['name']} considers...*"):
            mem.maybe_summarize(st.session_state.messages)
            recent, mem_inj = mem.get_context(st.session_state.messages)
            result = engine.run_inference(
                npc_key=npc_key, user_message=user_input.strip(),
                conversation_history=recent,
                emotion_state=st.session_state.emotion_states[npc_key],
                long_term_summary=mem.long_term_summary,
                temperature=st.session_state.temperature,
            )

        st.session_state.messages.append({"role":"assistant","content":result["response"]})
        st.session_state.emotion_states[npc_key] = result["updated_emotion_state"]
        save_profile(npc_key)
        st.rerun()


# ═══════════════════════════════════════════
# MODE: TAVERN
# ═══════════════════════════════════════════
elif mode == "🍺 Tavern":
    engine     = st.session_state.engine
    tavern_npcs= st.session_state.tavern_npcs

    if not tavern_npcs:
        st.warning("Select at least one NPC from the sidebar to open the Tavern.")
        st.stop()

    npc_names = ", ".join(NPC_ROSTER[k]["name"] for k in tavern_npcs if k in NPC_ROSTER)
    st.markdown(f"""<div class="tavern-header">
        🍺 <b>The Wanderer's Tavern</b> — Present: {npc_names}<br>
        <span style="font-size:.72rem;color:#5a4a3a;">
        Use @Name: to address an NPC · Others may overhear and react (35% chance)
        </span></div>""", unsafe_allow_html=True)

    npc_names = ", ".join(NPC_ROSTER[k]["name"] for k in tavern_npcs if k in NPC_ROSTER)

    # Init tavern session
    if st.session_state.tavern_session is None:
        valid_keys = [k for k in tavern_npcs if k in NPC_ROSTER]
        st.session_state.tavern_session = TavernSession(
            engine=engine, active_keys=valid_keys,
            player_name=st.session_state.player_name,
        )
        # Load profiles
        for k in valid_keys:
            _ensure_npc_state(k)
            saved = PlayerProfile(st.session_state.player_name).load(k)
            if saved:
                st.session_state.tavern_session.emotion_states[k] = saved.get("emotion_state",
                    dict(NPC_ROSTER[k].get("initial_emotions", DEFAULT_EMOTIONS)))
                st.session_state.tavern_session.memory_managers[k].long_term_summary = \
                    saved.get("long_term_summary","")

    tavern: TavernSession = st.session_state.tavern_session

    # Opening scene
    if not st.session_state.tavern_greeted:
        with st.spinner("*The tavern stirs as you enter...*"):
            intros = tavern.get_opening_scene(temperature=st.session_state.temperature)
        st.session_state.tavern_greeted = True

    # Render full tavern log
    for msg in tavern.log:
        role = "user" if msg.is_player else "assistant"
        npc_data = NPC_ROSTER.get(msg.npc_key, {"avatar":"🤖","name":msg.speaker})
        render_bubble(role, msg.text, npc_data, is_reaction=msg.is_reaction)

    # Input
    st.markdown("<br>", unsafe_allow_html=True)
    with st.form("tavern_form", clear_on_submit=True):
        c1, c2 = st.columns([5,1])
        with c1:
            hint = " · ".join(f"@{NPC_ROSTER[k]['name'].split()[0]}:" for k in tavern_npcs if k in NPC_ROSTER)
            user_input = st.text_input("Tavern msg", placeholder=f"Type or use: {hint}", label_visibility="collapsed")
        with c2: sent = st.form_submit_button("⚔ Send", use_container_width=True)

    if sent and user_input.strip():
        with st.spinner("*The tavern holds its breath...*"):
            tavern.run_exchange(user_input.strip(), temperature=st.session_state.temperature)
        # Save all NPC profiles
        for k in tavern.active_keys:
            if k in NPC_ROSTER:
                PlayerProfile(st.session_state.player_name).save(
                    npc_key=k, npc_name=NPC_ROSTER[k]["name"],
                    emotion_state=tavern.emotion_states.get(k, {}),
                    long_term_summary=tavern.memory_managers[k].long_term_summary,
                    message_count=len(tavern.npc_histories.get(k,[])),
                )
        st.rerun()

    # Autonomous conversation trigger
    if st.button("🍻 Let them converse autonomously", use_container_width=True):
        with st.spinner("*The NPCs exchange glances and begin talking...*"):
            tavern.run_npc_to_npc_exchange(temperature=st.session_state.temperature)
        # Save all NPC profiles
        for k in tavern.active_keys:
            if k in NPC_ROSTER:
                PlayerProfile(st.session_state.player_name).save(
                    npc_key=k, npc_name=NPC_ROSTER[k]["name"],
                    emotion_state=tavern.emotion_states.get(k, {}),
                    long_term_summary=tavern.memory_managers[k].long_term_summary,
                    message_count=len(tavern.npc_histories.get(k,[])),
                )
        st.rerun()


# ═══════════════════════════════════════════
# MODE: VOICE
# ═══════════════════════════════════════════
elif mode == "🎙 Voice":
    npc_key = st.session_state.npc_key
    npc     = NPC_ROSTER[npc_key]
    engine  = st.session_state.engine
    em_eng  = st.session_state.emotion_engine

    st.markdown(f"""<div class="npc-card">
        <div class="npc-name">{npc['avatar']} {npc['name']} — Voice Mode</div>
        <div class="npc-tagline">Speak. Be heard. Hear the NPC speak back.</div>
        <div class="npc-status"><div class="status-dot"></div>
            <span>Groq Whisper STT · gTTS · LLaMA 3.3 70B</span></div></div>""",
        unsafe_allow_html=True)

    voice_io = st.session_state.get("voice_io")

    if not VOICE_AVAILABLE or not voice_io:
        st.error("Voice unavailable. Run: `pip install gtts`")
        st.info("Groq Whisper STT requires no extra install (uses your existing GROQ_API_KEY).")
    else:
        st.markdown(f"""
            <style>
            .voice-container {{
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                text-align: center;
                padding: 1rem 0;
            }}
            .voice-avatar {{
                width: 90px;
                height: 90px;
                border-radius: 50%;
                background: linear-gradient(135deg, {theme["primary"]}, {theme["accent"]});
                border: 3px solid {theme["accent"]};
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 2.5rem;
                box-shadow: 0 0 25px {hex_to_rgba(theme["accent"], 0.4)};
                margin-bottom: 0.8rem;
            }}
            .mic-pulsing-circle {{
                width: 120px;
                height: 120px;
                border-radius: 50%;
                background: linear-gradient(135deg, {theme["primary"]}, {theme["accent"]});
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 0 0 0 {hex_to_rgba(theme["accent"], 0.7)};
                animation: mic-pulse-anim 2.5s infinite;
                margin: 1.5rem 0;
            }}
            .mic-pulsing-circle svg {{
                width: 50px;
                height: 50px;
                fill: #ffffff;
            }}
            @keyframes mic-pulse-anim {{
                0% {{
                    transform: scale(0.95);
                    box-shadow: 0 0 0 0 {hex_to_rgba(theme["accent"], 0.6)};
                }}
                70% {{
                    transform: scale(1.05);
                    box-shadow: 0 0 0 25px rgba(0, 0, 0, 0);
                }}
                100% {{
                    transform: scale(0.95);
                    box-shadow: 0 0 0 0 rgba(0, 0, 0, 0);
                }}
            }}
            .voice-status-lbl {{
                font-family: 'Cinzel', serif;
                font-size: 1rem;
                color: {theme["accent"]};
                letter-spacing: 0.15em;
                text-transform: uppercase;
                margin-top: 0.5rem;
            }}
            </style>
        """, unsafe_allow_html=True)

        _, col_center, _ = st.columns([1, 2, 1])

        with col_center:
            st.markdown(f"""
                <div class="voice-container">
                    <div class="voice-avatar">{npc['avatar']}</div>
                    <div style="font-family:'Cinzel',serif;font-size:1.4rem;font-weight:700;color:{theme['accent']};">{npc['name']}</div>
                    <div style="font-size:0.75rem;color:#7a6a5a;letter-spacing:0.1em;text-transform:uppercase;">Connected</div>
                </div>
            """, unsafe_allow_html=True)

            st.markdown(f"""
                <div style="display: flex; justify-content: center; align-items: center; width: 100%;">
                    <div class="mic-pulsing-circle">
                        <svg viewBox="0 0 24 24">
                            <path d="M12,2A3,3 0 0,1 15,5V11A3,3 0 0,1 12,14A3,3 0 0,1 9,11V5A3,3 0 0,1 12,2M19,11C19,14.53 16.39,17.44 13,17.93V21H11V17.93C7.61,17.44 5,14.53 5,11H7A5,5 0 0,0 12,16A5,5 0 0,0 17,11H19Z" />
                        </svg>
                    </div>
                </div>
                <div style="text-align: center; margin-bottom: 1rem;">
                    <div class="voice-status-lbl">TAP TO RECORD</div>
                </div>
            """, unsafe_allow_html=True)

            audio_value = st.audio_input(
                "Record your message",
                label_visibility="collapsed",
                key="voice_audio_recorder"
            )

            if audio_value:
                audio_bytes = audio_value.read()
                with st.spinner("Transcribing..."):
                    transcript = voice_io.transcribe(audio_bytes)

                if transcript and not transcript.startswith("[VOICE_ERROR"):
                    st.session_state.voice_transcript = transcript
                    st.success(f"**You said:** {transcript}")

                    _ensure_npc_state(npc_key)
                    mem = st.session_state.memory_managers[npc_key]
                    emo = st.session_state.emotion_states[npc_key]

                    with st.spinner(f"*{npc['name']} responds...*"):
                        emo_updated = em_eng.update(emo, transcript)
                        st.session_state.emotion_states[npc_key] = emo_updated

                        mem.maybe_summarize(st.session_state.messages)
                        recent, _ = mem.get_context(st.session_state.messages)

                        result = engine.run_inference(
                            npc_key=npc_key, user_message=transcript,
                            conversation_history=recent,
                            emotion_state=emo_updated,
                            long_term_summary=mem.long_term_summary,
                            temperature=st.session_state.temperature,
                        )

                    response_text = result["response"]
                    st.session_state.emotion_states[npc_key] = result["updated_emotion_state"]

                    st.session_state.messages.append({"role":"user","content":transcript})
                    st.session_state.messages.append({"role":"assistant","content":response_text})
                    save_profile(npc_key)

                    with st.spinner("Synthesizing voice..."):
                        audio_out = voice_io.synthesize(response_text, npc_key)
                    st.session_state.voice_response = response_text
                    st.session_state.voice_audio    = audio_out

                elif transcript.startswith("[VOICE_ERROR"):
                    st.error(transcript)

            if st.session_state.voice_response:
                st.markdown("<br>", unsafe_allow_html=True)
                render_bubble("assistant", st.session_state.voice_response, npc)

                if st.session_state.voice_audio:
                    st.audio(st.session_state.voice_audio, format="audio/mp3", autoplay=True)
                else:
                    st.info("Install `gtts` for audio playback: `pip install gtts`")
            else:
                st.markdown(f'<div class="info-box" style="margin-top:2rem; text-align: center;">Record a message above to start speaking with {npc["name"]}.</div>',
                    unsafe_allow_html=True)

        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown(f'<div style="font-family:Cinzel,serif;font-size:.8rem;color:{theme["accent"]};">📜 Session Transcript</div>',
            unsafe_allow_html=True)
        for msg in st.session_state.messages[-10:]:
            prefix = "🧑 You" if msg["role"]=="user" else f"{npc['avatar']} {npc['name']}"
            st.markdown(f"**{prefix}:** {msg['content'][:200]}{'...' if len(msg['content'])>200 else ''}")


# ═══════════════════════════════════════════
# MODE: FORGE
# ═══════════════════════════════════════════
elif mode == "⚒️ Forge":
    p, a = theme["primary"], theme["accent"]

    TEMPLATES = {
        "🔮 Mysterious Seer": {
            "name": "The Blind Oracle",
            "avatar": "🔮",
            "personality": "A blind seer who speaks in cryptic visions. She is ancient, patient, and sees the future in fragments. She refers to herself in the third person occasionally.",
            "lore": "The Oracle lost her sight after gazing directly into the Void Gate during the collapse. In exchange, she gained the ability to perceive threads of fate. She lives in a ruined tower at the edge of the Ashlands...",
            "greeting": "*The Oracle tilts her head before you speak.* I know why you've come. Sit.",
            "trust": 7.0, "anger": 0.0, "respect": 6.0, "curiosity": 9.0, "wariness": 2.0,
            "theme_color": "#6B2FA0", "accent_color": "#C084FC"
        },
        "🦝 Shady Merchant": {
            "name": "Finn the Fence",
            "avatar": "🦝",
            "personality": "A street-smart, fast-talking thief and fence. He is always looking over his shoulder, speaks in low whispers, and uses slang. He is highly suspicious of authority.",
            "lore": "Finn grew up in the Undercity slums. He has been arrested twelve times but escaped eleven times. He knows every secret tunnel, corrupt guard, and smuggling route in the capital.",
            "greeting": "*Finn beckons you into the shadow of an alley.* Keep it down. You looking to buy, or just wasting my breath? Make it quick.",
            "trust": 2.0, "anger": 0.0, "respect": 3.0, "curiosity": 6.0, "wariness": 8.0,
            "theme_color": "#273746", "accent_color": "#E67E22"
        },
        "🛡️ Loyal Squire": {
            "name": "Pip",
            "avatar": "🛡️",
            "personality": "An enthusiastic, young squire who is eager to please. He is brave but clumsy, respects chivalry, and talks with unbridled optimism. He addresses the player as 'My Lord' or 'My Lady'.",
            "lore": "Pip was orphaned during the dragon raids and taken in by Sir Gawain. He polishes armor, feeds the horses, and dreams of being knighted. He has a habit of dropping things when nervous.",
            "greeting": "A-ah! Salutations, traveler! *[Pip quickly polishes his shield, almost dropping it.]* I am Pip, squire to the realm! How may I serve you today?",
            "trust": 8.0, "anger": 0.0, "respect": 9.0, "curiosity": 7.0, "wariness": 1.0,
            "theme_color": "#196F3D", "accent_color": "#2ECC71"
        }
    }

    st.markdown(f"""
        <div style="font-family:Cinzel,serif;font-size:1.3rem;color:{a};margin-bottom:.3rem;">
            ⚒️ NPC Soul Forge
        </div>
        <div style="color:#7a6a5a;font-size:.8rem;margin-bottom:1.5rem;">
            Forge a custom autonomous NPC. Define their avatar, prompt guidelines, and initial emotion state, or import lore using PDF/Wikipedia.
        </div>
    """, unsafe_allow_html=True)

    # Template Preset Selector
    template_sel = st.selectbox(
        "Start from a Preset Template",
        options=["-- Blank Slate --"] + list(TEMPLATES.keys()),
        index=0 if st.session_state.last_loaded_template == "-- Blank Slate --" else 
              (list(TEMPLATES.keys()).index(st.session_state.last_loaded_template) + 1 if st.session_state.last_loaded_template in TEMPLATES else 0)
    )

    if template_sel != "-- Blank Slate --" and template_sel != st.session_state.last_loaded_template:
        t = TEMPLATES[template_sel]
        # Delete keys first so Streamlit recreates the widgets with the new defaults
        for key in ["f_name", "f_avatar", "f_personality", "f_lore", "f_greeting", "f_theme", "f_accent", "f_trust", "f_anger", "f_respect", "f_curiosity", "f_wariness"]:
            if key in st.session_state:
                del st.session_state[key]
        st.session_state.f_name = t["name"]
        st.session_state.f_avatar = t["avatar"]
        st.session_state.f_personality = t["personality"]
        st.session_state.f_lore = t["lore"]
        st.session_state.f_greeting = t["greeting"]
        st.session_state.f_theme = t["theme_color"]
        st.session_state.f_accent = t["accent_color"]
        st.session_state.f_trust = t["trust"]
        st.session_state.f_anger = t["anger"]
        st.session_state.f_respect = t["respect"]
        st.session_state.f_curiosity = t["curiosity"]
        st.session_state.f_wariness = t["wariness"]
        st.session_state.last_loaded_template = template_sel
        st.rerun()
    elif template_sel == "-- Blank Slate --" and st.session_state.last_loaded_template != "-- Blank Slate --":
        # reset
        for key in ["f_name", "f_avatar", "f_personality", "f_lore", "f_greeting", "f_theme", "f_accent", "f_trust", "f_anger", "f_respect", "f_curiosity", "f_wariness"]:
            if key in st.session_state:
                del st.session_state[key]
        st.session_state.f_name = ""
        st.session_state.f_avatar = "🤖"
        st.session_state.f_personality = ""
        st.session_state.f_lore = ""
        st.session_state.f_greeting = ""
        st.session_state.f_theme = "#4a90e2"
        st.session_state.f_accent = "#f5a623"
        st.session_state.f_trust = 5.0
        st.session_state.f_anger = 2.0
        st.session_state.f_respect = 5.0
        st.session_state.f_curiosity = 5.0
        st.session_state.f_wariness = 2.0
        st.session_state.last_loaded_template = "-- Blank Slate --"
        st.rerun()

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown(f'<div style="font-family:Cinzel,serif;font-size:1rem;color:{a};margin-bottom:.5rem;">👤 Identity & Prompts</div>', unsafe_allow_html=True)
        st.text_input("Name", key="f_name", placeholder="e.g. Eldrin the Wise")
        st.text_input("Avatar (Emoji)", key="f_avatar", placeholder="e.g. 🧙‍♂️")
        st.text_area("Personality & Rules", key="f_personality", placeholder="How does the NPC think, behave, and speak? (e.g. Speaks in riddles, stoic, warm...)", height=150)
        st.text_area("Greeting Message", key="f_greeting", placeholder="First message the NPC sends when meeting a player (Optional)", height=80)
        
        # Color pickers
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.color_picker("Theme Color", key="f_theme")
        with col_c2:
            st.color_picker("Accent Color", key="f_accent")
            
    with col2:
        st.markdown(f'<div style="font-family:Cinzel,serif;font-size:1rem;color:{a};margin-bottom:.5rem;">📜 Knowledge & Lore</div>', unsafe_allow_html=True)
        st.text_area("Raw Lore / Backstory", key="f_lore", placeholder="Paste history, encyclopedia entries, or world details here...", height=200)
        
        # Lore Ingestion: PDF
        st.markdown('<div style="font-size:0.8rem;font-weight:600;margin-top:0.8rem;">📂 Import from PDF</div>', unsafe_allow_html=True)
        pdf_file = st.file_uploader("Upload Lore PDF", type=["pdf"], key="forge_pdf_uploader")
        if pdf_file:
            pdf_bytes = pdf_file.read()
            try:
                pages = LoreIngestion.pdf_page_count(pdf_bytes)
                st.caption(f"PDF detected: {pdf_file.name} ({pages} pages).")
                if st.button("Extract & Append PDF Lore", key="btn_pdf_extract", use_container_width=True):
                    with st.spinner("Extracting text from PDF..."):
                        extracted = LoreIngestion.from_pdf(pdf_bytes)
                        if extracted:
                            new_lore = (st.session_state.f_lore + "\n\n" + extracted).strip()
                            if "f_lore" in st.session_state:
                                del st.session_state["f_lore"]
                            st.session_state.f_lore = new_lore
                            st.success(f"Appended lore from {pdf_file.name}!")
                            st.rerun()
                        else:
                            st.warning("No readable text found in PDF.")
            except Exception as e:
                st.error(f"Error reading PDF: {e}")
                
        # Lore Ingestion: Wikipedia
        st.markdown('<div style="font-size:0.8rem;font-weight:600;margin-top:0.8rem;">🌐 Import from Wikipedia</div>', unsafe_allow_html=True)
        col_w1, col_w2 = st.columns([3, 1])
        with col_w1:
            wiki_query = st.text_input("Wikipedia Topic", placeholder="e.g. Samurai, Greek Mythology", label_visibility="collapsed")
        with col_w2:
            fetch_wiki = st.button("Fetch", key="btn_fetch_wiki", use_container_width=True)

        if fetch_wiki and wiki_query.strip():
            with st.spinner(f"Fetching '{wiki_query}' from Wikipedia..."):
                try:
                    text, title = LoreIngestion.from_wikipedia(wiki_query.strip())
                    if text:
                        new_lore = (st.session_state.f_lore + f"\n\n## Wikipedia: {title}\n" + text).strip()
                        if "f_lore" in st.session_state:
                            del st.session_state["f_lore"]
                        st.session_state.f_lore = new_lore
                        st.success(f"Appended Wikipedia article '{title}'!")
                        st.rerun()
                    else:
                        st.warning(f"Could not find a Wikipedia page matching '{wiki_query}'.")
                except Exception as e:
                    st.error(f"Error fetching from Wikipedia: {e}")

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(f'<div style="font-family:Cinzel,serif;font-size:1rem;color:{a};margin-bottom:.5rem;">🧠 Initial Emotions (0–10)</div>', unsafe_allow_html=True)
    
    col_e1, col_e2, col_e3, col_e4, col_e5 = st.columns(5)
    with col_e1:
        st.slider("Trust", 0.0, 10.0, step=1.0, key="f_trust")
    with col_e2:
        st.slider("Anger", 0.0, 10.0, step=1.0, key="f_anger")
    with col_e3:
        st.slider("Respect", 0.0, 10.0, step=1.0, key="f_respect")
    with col_e4:
        st.slider("Curiosity", 0.0, 10.0, step=1.0, key="f_curiosity")
    with col_e5:
        st.slider("Wariness", 0.0, 10.0, step=1.0, key="f_wariness")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔨 Forge NPC Soul", use_container_width=True):
        if not st.session_state.f_name.strip():
            st.error("Name is required.")
        elif not st.session_state.f_personality.strip():
            st.error("Personality is required.")
        else:
            with st.spinner("Forging soul and indexing lore..."):
                spec = {
                    "name": st.session_state.f_name.strip(),
                    "avatar": st.session_state.f_avatar.strip() or "🤖",
                    "personality": st.session_state.f_personality.strip(),
                    "lore": st.session_state.f_lore.strip(),
                    "greeting": st.session_state.f_greeting.strip() or f"*{st.session_state.f_name.strip()} regards you.* Hello, traveller.",
                    "initial_emotions": {
                        "trust": st.session_state.f_trust,
                        "anger": st.session_state.f_anger,
                        "respect": st.session_state.f_respect,
                        "curiosity": st.session_state.f_curiosity,
                        "wariness": st.session_state.f_wariness
                    },
                    "theme_color": st.session_state.f_theme,
                    "accent_color": st.session_state.f_accent,
                }
                
                engine = st.session_state.engine
                npc_id = engine.forge_npc(spec)
                
                # Switch to Chat mode with the newly forged NPC
                st.session_state.npc_key = npc_id
                st.session_state.messages = []
                st.session_state.greeted = False
                st.session_state.mode = "⚔️ Chat"
                
                # Reset forge inputs
                for key in ["f_name", "f_avatar", "f_personality", "f_lore", "f_greeting"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.session_state.f_name = ""
                st.session_state.f_avatar = "🤖"
                st.session_state.f_personality = ""
                st.session_state.f_lore = ""
                st.session_state.f_greeting = ""
                st.session_state.last_loaded_template = "-- Blank Slate --"
                
                st.success(f"Successfully forged NPC '{spec['name']}'!")
                st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(f'<div style="font-family:Cinzel,serif;font-size:1rem;color:{a};margin-bottom:.5rem;">🗑️ Manage Forged NPCs</div>', unsafe_allow_html=True)
    
    custom_npcs = [k for k in NPC_ROSTER.keys() if k.startswith("custom_")]
    if not custom_npcs:
        st.info("No custom NPCs forged yet.")
    else:
        for c_id in custom_npcs:
            c_npc = NPC_ROSTER[c_id]
            col_m1, col_m2 = st.columns([4, 1])
            with col_m1:
                st.markdown(f"**{c_npc.get('avatar', '🤖')} {c_npc.get('name', 'Custom NPC')}** (`{c_id}`)")
                st.caption(f"*Personality:* {c_npc.get('system_prompt', '')[:120]}...")
            with col_m2:
                if st.button("🗑️ Delete", key=f"del_{c_id}", use_container_width=True):
                    engine = st.session_state.engine
                    engine.delete_npc(c_id)
                    # If currently chatting with this NPC, reset selection
                    if st.session_state.npc_key == c_id:
                        st.session_state.npc_key = list(NPC_ROSTER.keys())[0]
                        st.session_state.messages = []
                        st.session_state.greeted = False
                    st.success(f"NPC deleted.")
                    st.rerun()


# ═══════════════════════════════════════════
# MODE: API DOCS
# ═══════════════════════════════════════════
elif mode == "🔌 API":
    p, a = theme["primary"], theme["accent"]

    st.markdown(f"""
        <div style="font-family:Cinzel,serif;font-size:1.3rem;color:{a};margin-bottom:.3rem;">
            🔌 NPC-Forge REST API
        </div>
        <div style="color:#7a6a5a;font-size:.8rem;margin-bottom:1.5rem;">
            Run <code>uvicorn api:app --port 8000</code> in a second terminal.
            Full Swagger UI at <b>http://localhost:8000/docs</b>
        </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    with c1:
        st.markdown(f'<div style="font-family:Cinzel,serif;font-size:.9rem;color:{a};margin-bottom:.5rem;">⚡ Quick Start</div>',
            unsafe_allow_html=True)

        endpoints = [
            ("GET",    "/v1/npcs",                      "List all available NPCs"),
            ("POST",   "/v1/chat",                      "Single NPC conversation"),
            ("POST",   "/v1/tavern",                    "Multi-NPC tavern scene"),
            ("GET",    "/v1/profile/{player}/{npc}",    "Get relationship state"),
            ("POST",   "/v1/npc/forge",                 "🔨 Create a new NPC"),
            ("DELETE", "/v1/npc/{npc_id}",              "Delete a custom NPC"),
        ]

        for method, path, desc in endpoints:
            color = {"GET":"#27ae60","POST":"#e67e22","DELETE":"#e74c3c"}[method]
            st.markdown(f"""
                <div class="api-block">
                    <span style="color:{color};font-weight:700;">{method}</span>
                    <span style="color:#ddd;"> {path}</span><br>
                    <span style="color:#777;font-size:.72rem;">{desc}</span>
                </div>
            """, unsafe_allow_html=True)

    with c2:
        st.markdown(f'<div style="font-family:Cinzel,serif;font-size:.9rem;color:{a};margin-bottom:.5rem;">📋 Example Requests</div>',
            unsafe_allow_html=True)

        st.code("""# 1. List NPCs
curl http://localhost:8000/v1/npcs

# 2. Chat with Kagetora
curl -X POST http://localhost:8000/v1/chat \\
  -H "Content-Type: application/json" \\
  -d '{
    "player_id":  "my_player",
    "npc_id":     "⚔️ The Cursed Samurai",
    "message":    "Tell me about the Oni Seals"
  }'

# 3. Forge a new NPC
curl -X POST http://localhost:8000/v1/npc/forge \\
  -H "Content-Type: application/json" \\
  -d '{
    "name":        "The Blind Oracle",
    "avatar":      "🔮",
    "personality": "A blind seer. Speaks in cryptic visions.",
    "lore":        "Lost sight gazing into the Void Gate...",
    "theme_color": "#6b2fa0"
  }'

# 4. Use forged NPC immediately
curl -X POST http://localhost:8000/v1/chat \\
  -d '{"player_id":"p1","npc_id":"custom_the_blind_oracle","message":"Hello"}'""",
            language="bash")

    st.markdown("<hr>", unsafe_allow_html=True)

    st.markdown(f"""
        <div style="font-family:Cinzel,serif;font-size:.9rem;color:{a};margin-bottom:.5rem;">
            🎮 Unity / Godot Integration Pattern
        </div>
    """, unsafe_allow_html=True)

    st.code("""// Unity C# — NPC dialogue trigger
using UnityEngine;
using System.Net.Http;

public class NPCDialogue : MonoBehaviour {
    string API_BASE = "http://localhost:8000";
    string playerId = "unity_player_01";
    string npcId    = "⚔️ The Cursed Samurai";

    async void OnPlayerInteract(string playerMessage) {
        var body = new { player_id=playerId, npc_id=npcId, message=playerMessage };
        var json = JsonUtility.ToJson(body);
        // POST /v1/chat → get response text
        // Display in dialogue box
        // NPC emotion_state in response tells you trust level
        // Use trust >= 7 to unlock secret quest
    }
}""", language="csharp")

    st.markdown(f"""
        <div style="margin-top:1rem;padding:.8rem;background:{hex_to_rgba(p,.08)};
             border-left:3px solid {p};border-radius:0 8px 8px 0;font-size:.8rem;color:#9a8a7a;">
            <b style="color:{p};font-style:normal;">💡 Game Integration Tip:</b><br>
            The <code>emotion_state.trust</code> field in every /v1/chat response is a number (0–10).
            Use it to unlock dialogue branches, enable secret quests, or change NPC behavior in your game —
            no extra API calls needed. The emotion system is already running invisibly on every turn.
        </div>
    """, unsafe_allow_html=True)
