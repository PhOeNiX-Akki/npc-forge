#!/bin/bash

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "⚠️ Warning: venv folder not found. Running with global python."
fi

# Print welcome message
echo "⚒️ Starting NPC-Forge Frontend & Backend Servers..."

# Load env variables if .env exists
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Load API key default if not set
export NPC_FORGE_API_KEY=${NPC_FORGE_API_KEY:-"forge_dev_key_123"}
echo "🔑 API Key set to: $NPC_FORGE_API_KEY"
echo "👉 Request Header required: X-API-Key: $NPC_FORGE_API_KEY"

# Check ports and free them if occupied
echo "🔍 Checking ports..."
API_PORT=8000
UI_PORT=8501

free_port() {
    local port=$1
    local pid=$(lsof -t -i:$port)
    if [ ! -z "$pid" ]; then
        echo "🧹 Port $port is already in use by process $pid. Freeing it..."
        kill -9 $pid 2>/dev/null
    fi
}

free_port $API_PORT
free_port $UI_PORT

# Start Uvicorn API server in background
echo "⚡ Launching REST API on port $API_PORT..."
uvicorn api:app --host 0.0.0.0 --port $API_PORT --reload > api.log 2>&1 &
API_PID=$!
echo "📝 API server logging to api.log (PID: $API_PID)"

# Start Streamlit UI in foreground
echo "🎨 Launching Streamlit UI on port $UI_PORT..."
streamlit run app.py --browser.gatherUsageStats=false

# Clean up background process on exit
echo "🧹 Cleaning up background servers..."
if kill -0 $API_PID 2>/dev/null; then
    kill $API_PID 2>/dev/null
    echo "✅ Stopped REST API server."
fi
