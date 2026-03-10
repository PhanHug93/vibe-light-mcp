#!/bin/bash
# MCP Server Health Monitor
# Usage: bash monitor.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID=$(pgrep -f "python.*main.py" 2>/dev/null | head -1 || true)

echo "╔══════════════════════════════════════╗"
echo "║   MCP Server Health Monitor          ║"
echo "╚══════════════════════════════════════╝"
echo ""

# 1. Process status
if [ -z "$PID" ]; then
    echo "❌ MCP Server: NOT RUNNING"
    echo ""
    echo "Start with: .venv/bin/python main.py"
    exit 1
fi

echo "✅ MCP Server: RUNNING (PID $PID)"
echo ""

# 2. Resource usage
echo "── Resource Usage ──"
ps -p "$PID" -o %cpu,%mem,rss,vsz,etime 2>/dev/null | tail -1 | awk '{
    rss_mb = $3 / 1024
    vsz_mb = $4 / 1024
    printf "   CPU      : %s%%\n", $1
    printf "   RAM      : %s%% (%.1f MB real / %.1f MB virtual)\n", $2, rss_mb, vsz_mb
    printf "   Uptime   : %s\n", $5
}'
echo ""

# 3. Threads
THREADS=$(ps -M -p "$PID" 2>/dev/null | tail -n +2 | wc -l | tr -d ' ')
echo "── Threads ──"
echo "   Active   : $THREADS"
echo ""

# 4. ChromaDB storage
echo "── ChromaDB ──"
if [ -d "$SCRIPT_DIR/.chroma_db" ]; then
    DB_SIZE=$(du -sh "$SCRIPT_DIR/.chroma_db" 2>/dev/null | cut -f1)
    echo "   Size     : $DB_SIZE"
else
    echo "   Size     : N/A (not initialized — lazy mode)"
fi
echo ""

# 5. Open connections
FD_COUNT=$(lsof -p "$PID" 2>/dev/null | wc -l | tr -d ' ')
echo "── Connections ──"
echo "   Open FDs : $FD_COUNT"
echo ""

# 6. Tech stacks available
echo "── Knowledge Base ──"
for stack_dir in "$SCRIPT_DIR"/tech_stacks/*/; do
    stack=$(basename "$stack_dir")
    rules=$([ -f "$stack_dir/rules.md" ] && wc -c < "$stack_dir/rules.md" | tr -d ' ' || echo "0")
    skills=$([ -f "$stack_dir/skills.md" ] && wc -c < "$stack_dir/skills.md" | tr -d ' ' || echo "0")
    echo "   $stack: rules=${rules}B skills=${skills}B"
done
echo ""
echo "── Done ──"
