#!/bin/bash
# ============================================================================
# ChromaDB Backup Script — for cron/scheduled use
# ============================================================================
# Usage:
#   bash scripts/backup_chroma.sh                # One-time backup
#   crontab -e → 0 3 * * 0 /path/to/backup_chroma.sh  # Weekly at 3 AM
#
# Backups stored in: ~/.mcp_global_db/backups/
# Keeps last 5 backups, auto-cleans older ones.
# ============================================================================

set -euo pipefail

DB_PATH="${MCP_CHROMA_DB:-$HOME/.mcp_global_db}"
BACKUP_DIR="$DB_PATH/backups"
MAX_BACKUPS=5
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/chromadb_backup_${TIMESTAMP}.tar.gz"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Check if DB exists
if [ ! -d "$DB_PATH" ]; then
    echo "❌ ChromaDB directory not found: $DB_PATH"
    exit 1
fi

# Create backup (exclude backups/ and logs/ directories)
echo "📦 Creating backup..."
tar czf "$BACKUP_FILE" \
    --exclude="backups" \
    --exclude="logs" \
    -C "$DB_PATH" .

BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "✅ Backup created: $BACKUP_FILE ($BACKUP_SIZE)"

# Cleanup old backups
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/chromadb_backup_*.tar.gz 2>/dev/null | wc -l | tr -d ' ')
if [ "$BACKUP_COUNT" -gt "$MAX_BACKUPS" ]; then
    REMOVE_COUNT=$((BACKUP_COUNT - MAX_BACKUPS))
    echo "🧹 Cleaning up $REMOVE_COUNT old backup(s)..."
    ls -1t "$BACKUP_DIR"/chromadb_backup_*.tar.gz | tail -n "$REMOVE_COUNT" | xargs rm -f
fi

echo "📊 Total backups: $(ls -1 "$BACKUP_DIR"/chromadb_backup_*.tar.gz 2>/dev/null | wc -l | tr -d ' ')/$MAX_BACKUPS"
echo ""
echo "💡 Restore: tar xzf $BACKUP_FILE -C $DB_PATH"
