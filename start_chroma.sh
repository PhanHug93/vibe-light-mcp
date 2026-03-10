#!/bin/bash
# Start ChromaDB as a background HTTP service for Hybrid RAG.
#
# Usage:
#   bash start_chroma.sh          # foreground (see logs)
#   bash start_chroma.sh &        # background
#   nohup bash start_chroma.sh &  # survive terminal close
#
# Data stored at: ~/.mcp_global_db/
# Endpoint:       http://localhost:8888

set -euo pipefail

PORT=8888
DB_PATH="$HOME/.mcp_global_db"

# Ensure data directory exists
mkdir -p "$DB_PATH"

# Find chroma binary
CHROMA_BIN=""
if command -v chroma &>/dev/null; then
    CHROMA_BIN="chroma"
elif [ -f "$(dirname "$0")/.venv/bin/chroma" ]; then
    CHROMA_BIN="$(dirname "$0")/.venv/bin/chroma"
else
    echo "❌ 'chroma' CLI not found."
    echo "   Install: pip install chromadb"
    exit 1
fi

# Check if already running
if lsof -i :"$PORT" &>/dev/null; then
    echo "⚠️  ChromaDB already running on port $PORT"
    lsof -i :"$PORT" | head -3
    exit 0
fi

echo "🚀 Starting ChromaDB server..."
echo "   Port: $PORT"
echo "   Data: $DB_PATH"
echo "   PID:  $$"
echo ""

exec "$CHROMA_BIN" run --path "$DB_PATH" --port "$PORT"
