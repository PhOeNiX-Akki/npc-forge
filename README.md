# NPC-Forge 🔨⚔️

> **Autonomous NPC Engine** — Powered by LLaMA 3.3 & Groq

NPC-Forge gives indie game developers and anime fans AI-powered NPCs with deep personalities, memory, and lore awareness.

---

## 🚀 Quick Start (5 minutes)

### 1. Clone & Navigate
```bash
cd npc-forge
```

### 2. Create a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Set Your Groq API Key
```bash
cp .env.example .env
# Now open .env and replace 'your_groq_api_key_here' with your real key
# Get your FREE key at: https://console.groq.com
```

### 5. Launch
```bash
streamlit run app.py
```

Your browser will open at `http://localhost:8501` ⚔️

---

## 🏗️ Architecture (Completed)

```
npc-forge/
├── app.py              → Streamlit UI + Mode Selectors + Voice UI
├── api.py              → FastAPI Backend REST API (Game Engine integration)
├── start.sh            → Unified Server Launcher (UI on 8501, API on 8000)
├── brain.py            → Groq LLM Interface (LLaMA 3.3 70B swap-able backend)
├── engine.py           → Inference orchestration engine (combines memory, emotions, RAG)
├── emotion.py          → Emotion Engine (dynamic Trust/Anger/Respect/Wariness tracking)
├── memory.py           → Memory Managers (short-term & summary-based memory compression)
├── persistence.py      → Local player relationship persistence
├── rag.py              → RAG vector database pipeline (ChromaDB)
├── lore_ingestion.py   → Lore ingestion engine (PDF parsing, Wikipedia scraper)
├── voice.py            → Voice Interface (Groq Whisper STT + gTTS audio synthesis)
├── npc_config.py       → Personality configuration definitions (the "Soul Registry")
├── .env                → Environment config (API Key, Ports)
└── requirements.txt    → Project python dependencies
```

## 🗺️ Roadmap

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Core Brain — Personality + Chat | ✅ **Done** |
| 2 | Persistent Memory (per-session + long-term) | ✅ **Done** |
| 3 | RAG Lore Engine (Vector DB + Custom PDF/Wiki Ingest) | ✅ **Done** |
| 4 | Multi-NPC Conversations (Tavern Mode with Bystander Overhear) | ✅ **Done** |
| 5 | Voice Interface (Whisper STT + TTS Speech Output) | ✅ **Done** |
| 6 | Emotion Engine + Dynamic Mood States | ✅ **Done** |
| 7 | Game Engine REST API (FastAPI with API Key Security) | ✅ **Done** |
