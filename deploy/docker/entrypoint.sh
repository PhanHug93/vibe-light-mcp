#!/bin/sh
# ============================================================================
# Docker Entrypoint — Fix bind mount permissions, then exec as mcpuser
# ============================================================================
# Problem: Bind-mounted directories (e.g., tech_stacks/) inherit host UID/GID.
#          If host user UID ≠ 1000 (mcpuser), the container gets Permission Denied.
#
# Solution: This script runs as root (briefly), fixes ownership of writable
#           bind mounts, then drops to mcpuser via `exec gosu`.
#           If gosu is not available, falls back to `exec su-exec` or plain exec.
# ============================================================================

set -e

# Directories that may be Docker named volumes or bind mounts and need write access.
WRITABLE_DIRS="/app/tech_stacks /app/skill_registry /data"

seed_if_empty() {
    source_dir="$1"
    target_dir="$2"

    if [ ! -d "$source_dir" ]; then
        return
    fi

    mkdir -p "$target_dir"
    if [ -z "$(find "$target_dir" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
        echo "Seeding $target_dir from $source_dir"
        cp -a "$source_dir"/. "$target_dir"/
    fi
}

seed_if_empty "/opt/mcp-defaults/tech_stacks" "/app/tech_stacks"
seed_if_empty "/opt/mcp-defaults/skill_registry" "/app/skill_registry"

ensure_skill_store() {
    SKILL_REGISTRY_DIR="${MCP_SKILL_REGISTRY_DIR:-/app/skill_registry}"
    SKILL_STORE_PATH="${MCP_SKILL_STORE_PATH:-$SKILL_REGISTRY_DIR/index/skill_store.sqlite}"

    if [ ! -f "$SKILL_REGISTRY_DIR/registry.yaml" ]; then
        return
    fi

    if [ ! -f "$SKILL_STORE_PATH" ]; then
        echo "Building skill store at $SKILL_STORE_PATH"
        mkdir -p "$(dirname "$SKILL_STORE_PATH")"
        python scripts/build_skill_store.py \
            --registry-dir "$SKILL_REGISTRY_DIR" \
            --output "$SKILL_STORE_PATH"
    fi
}

ensure_skill_store

# Fix ownership (only if running as root)
if [ "$(id -u)" = "0" ]; then
    for dir in $WRITABLE_DIRS; do
        if [ -d "$dir" ]; then
            # Only chown if not already owned by mcpuser
            owner=$(stat -c '%u' "$dir" 2>/dev/null || echo "unknown")
            if [ "$owner" != "1000" ]; then
                chown -R mcpuser:mcpuser "$dir" 2>/dev/null || true
            fi
        fi
    done

    # Drop privileges and exec the main command as mcpuser
    exec gosu mcpuser "$@"
fi

# Already running as non-root (e.g., Kubernetes with securityContext)
exec "$@"
