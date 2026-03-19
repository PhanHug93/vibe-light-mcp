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

# Directories that may be bind-mounted from host and need write access
WRITABLE_DIRS="/app/tech_stacks /data"

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
