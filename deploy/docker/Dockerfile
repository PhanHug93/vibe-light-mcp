# ============================================================================
# Multi-stage Dockerfile — TechStack Local MCP Server
# ============================================================================
# Target: Ubuntu Server (Intel i5, 8GB RAM), chạy 24/7
# Base: python:3.10-slim (nhẹ, tương thích tốt với onnxruntime/hnswlib)
#
# Security: Chạy dưới non-root user (mcpuser) để giảm attack surface.
# Build: 2 stages để giảm image size (~400MB thay vì ~1.5GB).
# ============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder — Cài đặt dependencies (có gcc, cmake)
# ---------------------------------------------------------------------------
FROM python:3.10-slim AS builder

WORKDIR /build

# Build tools cho C extensions (hnswlib, onnxruntime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ cmake build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency file + source code
COPY pyproject.toml ./
COPY src/ ./src/
COPY main.py ./
COPY cascade_bridge.py ./

# Cài dependencies vào venv riêng
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip (base image có pip 23.x quá cũ)
RUN pip install --no-cache-dir --upgrade pip

# Install deps (tách riêng để dễ debug nếu fail)
RUN pip install --no-cache-dir "pyyaml>=6.0" "httpx>=0.27.0" "hatchling"
RUN pip install --no-cache-dir "mcp[cli]>=1.2.0"
RUN pip install --no-cache-dir "chromadb>=0.4.20"
RUN pip install --no-cache-dir "onnxruntime>=1.17.0"

# ---------------------------------------------------------------------------
# Stage 2: Runtime — Image nhẹ, chỉ chứa app + venv
# ---------------------------------------------------------------------------
FROM python:3.10-slim AS runtime

LABEL maintainer="PhanHug93"
LABEL description="TechStack Local MCP Server — Production"
LABEL version="1.0.10"

# ── Non-root user ──────────────────────────────────────────────────────────
# Tạo user `mcpuser` (uid=1000) để KHÔNG chạy dưới quyền root.
# Lý do: Nếu container bị exploit, attacker chỉ có quyền user thường,
# không thể leo thang đặc quyền ra host system.
RUN groupadd --gid 1000 mcpuser \
    && useradd --uid 1000 --gid mcpuser --shell /bin/bash --create-home mcpuser

WORKDIR /app

# Copy venv từ builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application code
COPY --chown=mcpuser:mcpuser main.py ./
COPY --chown=mcpuser:mcpuser cascade_bridge.py ./
COPY --chown=mcpuser:mcpuser src/ ./src/
COPY --chown=mcpuser:mcpuser tech_stacks/ ./tech_stacks/
COPY --chown=mcpuser:mcpuser scripts/ ./scripts/

# Tạo thư mục data với quyền cho mcpuser
RUN mkdir -p /data/logs /data/db /data/usage_logs \
    && chown -R mcpuser:mcpuser /data

# ── Environment defaults ──────────────────────────────────────────────────
# Tất cả có thể override qua docker-compose environment hoặc .env
ENV MCP_TRANSPORT=sse
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
ENV MCP_CHROMA_HOST=chromadb
ENV MCP_CHROMA_PORT=8000
ENV MCP_CHROMA_DB=/data/db
ENV MCP_EXEC_MODE=allowlist

VOLUME ["/data"]

# ── Health check ──────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${MCP_PORT}/sse', timeout=3)" || exit 1

EXPOSE ${MCP_PORT}

# ── Chuyển sang non-root user ─────────────────────────────────────────────
USER mcpuser

# ── Entrypoint ────────────────────────────────────────────────────────────
# main.py reads MCP_TRANSPORT, MCP_PORT from env vars (set in docker-compose).
# No CMD args → env vars control transport mode.
ENTRYPOINT ["python", "main.py"]
