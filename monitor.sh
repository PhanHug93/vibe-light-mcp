#!/bin/bash
# MCP Server Health Monitor
# Usage: bash monitor.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${SCRIPT_DIR}/.venv/bin/python"

# ── Version ──
VERSION="unknown"
if [ -f "$SCRIPT_DIR/main.py" ]; then
    VERSION=$(grep '__version__' "$SCRIPT_DIR/main.py" | head -1 | sed 's/.*"\(.*\)".*/\1/')
fi

echo "╔══════════════════════════════════════╗"
echo "║   MCP Server Monitor  v${VERSION}        ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. MCP Process ──
# Detect MCP process: covers both direct run and stdio transport
PID=$(pgrep -f "main\.py" 2>/dev/null | head -1 || true)

if [ -z "$PID" ]; then
    # Fallback: check if FastMCP/TechStackLocalMCP is running
    PID=$(pgrep -f "TechStackLocalMCP" 2>/dev/null | head -1 || true)
fi

if [ -z "$PID" ]; then
    # Fallback: any python process loading main.py from this dir
    PID=$(pgrep -f "$SCRIPT_DIR/main.py" 2>/dev/null | head -1 || true)
fi

if [ -z "$PID" ]; then
    echo "⚠️  MCP Server: NOT DETECTED as standalone process"
    echo "   (Normal if running via AI client stdio transport)"
    echo ""
else
    echo "✅ MCP Server: RUNNING (PID $PID)"
    echo ""

    # Resource usage
    echo "── Resource Usage ──"
    ps -p "$PID" -o %cpu,%mem,rss,vsz,etime 2>/dev/null | tail -1 | awk '{
        rss_mb = $3 / 1024
        vsz_mb = $4 / 1024
        printf "   CPU      : %s%%\n", $1
        printf "   RAM      : %s%% (%.1f MB real / %.1f MB virtual)\n", $2, rss_mb, vsz_mb
        printf "   Uptime   : %s\n", $5
    }'
    echo ""

    # Threads
    THREADS=$(ps -M -p "$PID" 2>/dev/null | tail -n +2 | wc -l | tr -d ' ')
    echo "── Threads ──"
    echo "   Active   : $THREADS"
    echo ""
fi

# ── 2. ChromaDB Server ──
echo "── ChromaDB Server ──"
if curl -s http://localhost:8888/api/v2/heartbeat > /dev/null 2>&1; then
    HEARTBEAT=$(curl -s http://localhost:8888/api/v2/heartbeat)
    echo "   Status   : ✅ RUNNING (port 8888)"
    echo "   Heartbeat: $HEARTBEAT"
else
    CHROMA_PID=$(lsof -ti :8888 2>/dev/null | head -1 || true)
    if [ -n "$CHROMA_PID" ]; then
        echo "   Status   : ⚠️  Port 8888 in use (PID $CHROMA_PID) but not responding"
    else
        echo "   Status   : ❌ NOT RUNNING"
        echo "   Start    : ./start_chroma.sh"
    fi
fi
echo ""

# ── 3. ChromaDB Storage ──
echo "── ChromaDB Storage ──"
GLOBAL_DB="$HOME/.mcp_global_db"
if [ -d "$GLOBAL_DB" ]; then
    DB_SIZE=$(du -sh "$GLOBAL_DB" 2>/dev/null | cut -f1)
    echo "   Path     : $GLOBAL_DB"
    echo "   Size     : $DB_SIZE"
else
    echo "   Path     : $GLOBAL_DB (not created yet)"
fi
echo ""

# ── 4. Open Connections ──
if [ -n "${PID:-}" ] && [ "$PID" != "" ]; then
    FD_COUNT=$(lsof -p "$PID" 2>/dev/null | wc -l | tr -d ' ')
    echo "── Connections ──"
    echo "   Open FDs : $FD_COUNT"
    echo ""
fi

# ── 5. Knowledge Base ──
echo "── Knowledge Base ──"
STACK_COUNT=0
for stack_dir in "$SCRIPT_DIR"/tech_stacks/*/; do
    [ -d "$stack_dir" ] || continue
    stack=$(basename "$stack_dir")
    rules=$([ -f "$stack_dir/rules.md" ] && wc -c < "$stack_dir/rules.md" | tr -d ' ' || echo "0")
    skills=$([ -f "$stack_dir/skills.md" ] && wc -c < "$stack_dir/skills.md" | tr -d ' ' || echo "0")
    echo "   $stack: rules=${rules}B skills=${skills}B"
    STACK_COUNT=$((STACK_COUNT + 1))
done
echo "   Total    : $STACK_COUNT stacks"
echo ""

# ── Summary ──
echo "── Summary ──"
echo "   Version  : $VERSION"
echo "   Python   : $($PYTHON --version 2>/dev/null || echo 'N/A')"
echo "   ChromaDB : $(curl -s http://localhost:8888/api/v2/heartbeat > /dev/null 2>&1 && echo '✅ OK' || echo '❌ Down')"
echo ""
echo "── Done ──"
