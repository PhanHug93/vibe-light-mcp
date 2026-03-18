# 🧠 TechStack Local MCP Server

> Biến AI của bạn thành một developer thực thụ — tự nhận diện project, nhớ context, và học hỏi qua từng workspace.

**TechStack Local MCP Server** là một [MCP](https://modelcontextprotocol.io/) server chạy local, giúp các AI coding assistants (Antigravity, Claude, Cursor, Windsurf...) trở nên thông minh hơn bằng cách:

- 🔍 **Tự nhận diện dự án** — Quét project, trả về coding rules + skills phù hợp
- 🧠 **Nhớ context 2 tầng** — L1 (tạm, per-project) + L2 (vĩnh viễn, global)
- 🔄 **Auto-recall** — Tự nhớ lại ngữ cảnh từ các cuộc hội thoại trước
- 🛡️ **Chạy lệnh an toàn** — Allowlist + Defense-in-Depth (4 lớp bảo vệ)
- 🌐 **Multi-transport** — stdio, SSE (streaming), Streamable HTTP
- 🖥️ **Cross-platform** — macOS, Linux, Windows

---

## 📖 Mục lục

- [🐳 Deploy bằng Docker (Production)](#-deploy-bằng-docker-production)
- [⚡ Cài đặt thủ công (Development)](#-cài-đặt-thủ-công-development)
- [🔌 Kết nối AI Client](#-kết-nối-ai-client)
- [🤖 Tích hợp AI Agent](#-tích-hợp-ai-agent--kích-hoạt-đầy-đủ-sức-mạnh-mcp)
- [🛠 Tools](#-tools)
- [🛡️ Security Model](#️-security-model)
- [🔄 Multi-Instance Behavior](#-multi-instance-behavior)

---

## 🐳 Deploy bằng Docker (Production)

Cách deploy được khuyến nghị — **hoạt động trên mọi OS**, tự quản lý ChromaDB, log rotation, resource limits.

### Yêu cầu

- [Docker Engine](https://docs.docker.com/engine/install/) ≥ 20.10
- [Docker Compose](https://docs.docker.com/compose/install/) ≥ 2.0
- RAM tối thiểu: **4GB** (khuyến nghị 8GB cho production)

### Bước 1: Clone dự án

```bash
git clone https://github.com/PhanHug93/vibe-light-mcp.git
cd vibe-light-mcp
```

### Bước 2: Tạo file cấu hình

```bash
cp deploy/compose/.env.example deploy/compose/.env
```

Chỉnh sửa `deploy/compose/.env` nếu cần thay đổi port:

```env
# Port MCP Server expose ra host (mặc định 8000)
MCP_EXTERNAL_PORT=8000

# Transport mode: sse (default) hoặc streamable-http
MCP_TRANSPORT=sse
```

### Bước 3: Khởi động

```bash
docker compose -f deploy/compose/docker-compose.yml up -d
```

Lần đầu sẽ build image (~3-5 phút). Các lần sau chỉ mất vài giây.

### Bước 4: Kiểm tra

```bash
# Xem status
docker compose -f deploy/compose/docker-compose.yml ps

# Kết quả mong đợi:
# NAME           STATUS                   PORTS
# mcp-chromadb   Up (healthy)             (no ports — internal only)
# mcp-server     Up (healthy)             0.0.0.0:8000->8000/tcp
```

```bash
# Test MCP Server phản hồi
curl http://localhost:8000/sse
# → data: (stream connection opened)
```

### Bước 5: Kết nối AI Client

Xem mục [🔌 Kết nối AI Client](#-kết-nối-ai-client) bên dưới. Với Docker, dùng **SSE mode** (cascade bridge).

### Quản lý hàng ngày

```bash
# Shortcut: gán alias cho docker compose
DC="docker compose -f deploy/compose/docker-compose.yml"

# Xem logs realtime
$DC logs -f mcp-server

# Dừng tất cả
$DC down

# Khởi động lại
$DC up -d

# Rebuild sau khi update code (git pull)
$DC build --no-cache && $DC up -d

# Xem resource usage
docker stats mcp-server mcp-chromadb
```

<details>
<summary><strong>🏗 Kiến trúc Docker (chi tiết)</strong></summary>

```
┌─────────────────────────────────────────────────────────────┐
│  mcp_internal (internal: true — NO external access)        │
│  ┌──────────────┐          ┌──────────────┐                │
│  │   chromadb   │◄────────►│  mcp_server  │                │
│  │   :8000      │          │              │                │
│  │ (NO exposed  │          └──────┬───────┘                │
│  │  ports)      │                 │                         │
│  └──────────────┘                 │                         │
└───────────────────────────────────┼─────────────────────────┘
┌───────────────────────────────────┼─────────────────────────┐
│  mcp_exposed (bridge)             │                         │
│                        ┌──────────┴───────┐                 │
│                        │  mcp_server      │──► :8000 (host) │
│                        └──────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

| Component | Chi tiết |
|---|---|
| **ChromaDB** | Internal-only — KHÔNG expose port ra host/LAN, bảo vệ Vector DB |
| **MCP Server** | Dual-network: internal (giao tiếp ChromaDB) + exposed (port 8000 ra host) |
| **Resource Limits** | ChromaDB: 2.5GB RAM / MCP: 1.5GB RAM (tối ưu cho server 8GB) |
| **Log Rotation** | json-file, max 10MB × 3 files = tối đa 30MB log/service |
| **Security** | Non-root user (`mcpuser`), ChromaDB cô lập hoàn toàn |
| **Restart** | `unless-stopped` — auto-restart khi crash hoặc reboot |
| **Volumes** | `chroma_data` (persistent DB), `usage_logs` (logs), `tech_stacks` (bind mount) |

</details>

<details>
<summary><strong>📂 Cấu trúc thư mục Deploy</strong></summary>

```
deploy/
├── docker/
│   └── Dockerfile              # Multi-stage build (python:3.10-slim)
├── compose/
│   ├── docker-compose.yml      # 2 services: chromadb + mcp_server
│   └── .env.example            # Template biến môi trường
├── launchd/
│   └── com.mcp.chromadb.plist  # macOS auto-start (khi không dùng Docker)
└── systemd/
    └── chromadb.service        # Linux auto-start (khi không dùng Docker)
```

</details>

---

## ⚡ Cài đặt thủ công (Development)

Dùng khi bạn muốn chạy trực tiếp trên máy **không qua Docker** (dev local, debug, stdio mode).

### Bước 1: Clone & cài đặt

```bash
git clone https://github.com/PhanHug93/vibe-light-mcp.git
cd vibe-light-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Bước 2: Khởi động ChromaDB

```bash
./scripts/start_chroma.sh
```

<details>
<summary>Auto-start mỗi khi bật máy (macOS)</summary>

```bash
cp deploy/launchd/com.mcp.chromadb.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mcp.chromadb.plist
```
</details>

<details>
<summary>Auto-start mỗi khi bật máy (Linux — Systemd)</summary>

```bash
sudo cp deploy/systemd/chromadb.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable chromadb
sudo systemctl start chromadb

# Xem logs
journalctl -u chromadb -f
```
</details>

### Bước 3: Chạy MCP Server

```bash
# stdio (mặc định — cho Antigravity, Claude)
python main.py

# SSE server (streaming, multi-client)
python main.py --transport sse --port 8000

# Streamable HTTP
python main.py --transport streamable-http --port 8000
```

### Biến môi trường

| Biến | Mặc định | Mô tả |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `stdio` · `sse` · `streamable-http` |
| `MCP_HOST` | `127.0.0.1` | Bind address cho HTTP transports |
| `MCP_PORT` | `8000` | Listen port cho HTTP transports |
| `MCP_EXEC_MODE` | `allowlist` | `allowlist` (an toàn) · `unrestricted` (dev only) |
| `MCP_CHROMA_HOST` | `localhost` | ChromaDB host |
| `MCP_CHROMA_PORT` | `8888` | ChromaDB port |

---

## 🔌 Kết nối AI Client

Có **2 cách** kết nối AI client — chọn tùy kiểu deploy:

### Cách A: stdio (Cài đặt thủ công — phổ biến nhất)

Thay `<username>` bằng username trên máy.

<details>
<summary><strong>Antigravity</strong> — <code>~/.gemini/settings.json</code></summary>

```json
{
  "mcpServers": {
    "tech-stack-expert": {
      "command": "/Users/<username>/projects/vibe-light-mcp/.venv/bin/python",
      "args": ["/Users/<username>/projects/vibe-light-mcp/main.py"]
    }
  }
}
```
</details>

<details>
<summary><strong>Claude Desktop</strong> — <code>~/Library/Application Support/Claude/claude_desktop_config.json</code></summary>

```json
{
  "mcpServers": {
    "tech-stack-expert": {
      "command": "/Users/<username>/projects/vibe-light-mcp/.venv/bin/python",
      "args": ["/Users/<username>/projects/vibe-light-mcp/main.py"]
    }
  }
}
```
</details>

<details>
<summary><strong>Cursor</strong> — <code>~/.cursor/mcp.json</code></summary>

```json
{
  "mcpServers": {
    "tech-stack-expert": {
      "command": "/Users/<username>/projects/vibe-light-mcp/.venv/bin/python",
      "args": ["/Users/<username>/projects/vibe-light-mcp/main.py"]
    }
  }
}
```
</details>

<details>
<summary><strong>Windsurf / Cascade</strong> — <code>~/.codeium/windsurf/mcp_config.json</code></summary>

```json
{
  "mcpServers": {
    "tech-stack-expert": {
      "command": "/Users/<username>/projects/vibe-light-mcp/.venv/bin/python",
      "args": ["/Users/<username>/projects/vibe-light-mcp/main.py"]
    }
  }
}
```
</details>

### Cách B: SSE qua Bridge (Docker hoặc SSE server)

Khi MCP chạy ở **SSE mode** (Docker hoặc `python main.py --transport sse`), dùng `cascade_bridge.py` để kết nối:

**Bước 1**: Đảm bảo MCP Server (SSE) đang chạy trên port 8000.

**Bước 2**: Cấu hình AI client trỏ vào bridge:

<details>
<summary><strong>Antigravity</strong> — <code>~/.gemini/settings.json</code></summary>

```json
{
  "mcpServers": {
    "tech-stack-expert": {
      "command": "/Users/<username>/projects/vibe-light-mcp/.venv/bin/python",
      "args": ["/Users/<username>/projects/vibe-light-mcp/cascade_bridge.py"],
      "env": {
        "MCP_BRIDGE_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```
</details>

<details>
<summary><strong>Các client khác</strong> (Claude, Cursor, Windsurf)</summary>

Tương tự Antigravity — thay `main.py` bằng `cascade_bridge.py` và thêm `env.MCP_BRIDGE_URL`.
</details>

> ⚠️ Dùng **đường dẫn tuyệt đối**. Với Docker: đảm bảo `docker compose up -d` đã chạy trước khi mở AI client.

---

## 🤖 Tích hợp AI Agent — Kích hoạt đầy đủ sức mạnh MCP

Để AI agent tận dụng **100% khả năng** của MCP (auto-recall, memory, tech detection), copy System Prompt vào rules file của project:

```bash
# Antigravity (Gemini)
cp /path/to/vibe-light-mcp/docs/mcp_system_prompt.md /your-project/.gemini/rules.md

# Cursor
cp /path/to/vibe-light-mcp/docs/mcp_system_prompt.md /your-project/.cursorrules

# Windsurf / Cascade
cp /path/to/vibe-light-mcp/docs/mcp_system_prompt.md /your-project/.windsurfrules

# Cline / Roo Code
cp /path/to/vibe-light-mcp/docs/mcp_system_prompt.md /your-project/.clinerules

# GitHub Copilot
mkdir -p /your-project/.github
cp /path/to/vibe-light-mcp/docs/mcp_system_prompt.md /your-project/.github/copilot-instructions.md

# Claude Desktop → Dán nội dung vào Project → Custom Instructions
```

<details>
<summary><strong>AI Agent sẽ tự động làm gì sau khi tích hợp?</strong></summary>

| Hành vi | Tool được gọi | Khi nào |
|---|---|---|
| 🔄 Nhớ lại context cũ | `auto_recall` | Đầu mỗi session |
| 🔍 Nhận diện tech stack | `analyze_workspace` | Lần đầu mở project |
| 💾 Lưu bug fix / decision | `store_working_context` | Sau khi fix bug khó |
| 🧠 Lưu best practice | `store_knowledge` | Khi phát hiện pattern tốt |
| 🔎 Tìm lại context cũ | `search_memory` | Khi user nhắc chuyện cũ |
| ⚙️ Build / Test / Lint | `run_terminal_command` | Sau khi viết code |

</details>

> 📖 Xem chi tiết đầy đủ: [`docs/mcp_system_prompt.md`](docs/mcp_system_prompt.md) — System Prompt + Tool Reference Card
> 
> 📋 Phiên bản rút gọn (chỉ memory rules): [`docs/mcp_rules.md`](docs/mcp_rules.md)

---

## 🛠 Tools

### 🧠 Memory

| Tool | Mô tả |
|---|---|
| `store_working_context` | Lưu code/log tạm vào L1 (per-project, TTL 3 ngày). Tự dedup bằng content-hash |
| `store_knowledge` | Lưu knowledge vĩnh viễn vào L2 (global) |
| `search_memory` | Tìm trong cả L1 + L2, re-rank theo similarity |
| `auto_recall` | ⚡ Tự nhớ context (rate-limited, fail-safe, cache 3s) |
| `cleanup_workspace` | Dọn dẹp L1 cũ hơn N ngày |
| `memory_stats` | Thống kê bộ nhớ L1/L2 |
| `backup_memory_database` | 📦 Backup ChromaDB → .tar.gz (auto-cleanup, giữ 5 bản) |

### 🔍 Workspace & Knowledge

| Tool | Mô tả |
|---|---|
| `analyze_workspace` | Quét project, trả rules + skills theo tech stack |
| `read_reference` | Đọc tài liệu tham khảo chi tiết của tech stack |
| `sync_knowledge` | Cập nhật knowledge base từ Git (an toàn, không shell injection) |
| `update_tech_stack` | Cập nhật rules/skills (merge-aware: append / replace_section / overwrite) |

### ⚙️ System

| Tool | Mô tả |
|---|---|
| `run_terminal_command` | Chạy lệnh an toàn (allowlist + interpreter guard + 60s timeout) |
| `server_health` | Kiểm tra trạng thái server + ChromaDB + memory |
| `manage_chroma` | Start / stop / status ChromaDB |
| `self_update` | Pull code MCP mới nhất từ Git |
| `usage_stats` | Thống kê sử dụng hàng ngày + satisfaction score |

---

## 🛡️ Security Model

Hệ thống bảo mật sử dụng **Defense-in-Depth** (4 lớp bảo vệ):

| Layer | Tên | Chức năng |
|---|---|---|
| 1 | **Shell Normalization** | Resolve path → basename (`/bin/rm` → `rm`, `./rm` → `rm`) |
| 1.5 | **Always-Blocked** | `rm`, `sudo`, `dd`, `kill`... bị cấm vĩnh viễn |
| 1.7 | **Interpreter Guard** | Chặn `python -c`, `node -e`, `ruby -e` (Living off the Land) |
| 2 | **Allowlist** | Chỉ cho phép lệnh dev đã đăng ký (git, npm, gradle, pytest...) |
| 3 | **Meta-Attack Detection** | Chặn `$(...)`, backtick, eval, base64 decode, pipe to shell |
| 4 | **Audit Logging** | Mọi lệnh đều được log (kể cả bị chặn) |

Bổ sung:
- **Process Group Kill** — Timeout sẽ kill cả process tree (không để zombie)
- **Path Traversal Protection** — `read_reference`, `update_tech_stack` chặn `../../`
- **URL Validation** — `sync_knowledge` chặn shell injection qua repo URL
- **Thread-safe LRU Cache** — L1 collection cache có giới hạn (max 50) + thread lock

> 💡 Đặt `MCP_EXEC_MODE=unrestricted` nếu bạn tin tưởng hoàn toàn AI client (chỉ nên dùng khi dev local).

---

## 🔄 Multi-Instance Behavior

| Transport | Multi-Instance | Ghi chú |
|---|---|---|
| `stdio` | ✅ Hỗ trợ | Mỗi IDE client spawn process riêng |
| `sse` | ❌ Singleton | Chỉ 1 server, dùng `cascade_bridge.py` để kết nối thêm client |
| `streamable-http` | ❌ Singleton | Tương tự SSE |

SSE/HTTP server dùng **lock file** (`~/.mcp_server.lock`) để ngăn conflict:
- Phát hiện server đang chạy → exit gracefully + gợi ý kết nối
- Phát hiện server đã chết (stale lock) → tự dọn lock cũ + start mới

```bash
# Kết nối nhiều client vào 1 SSE server
python main.py --transport sse --port 8000  # Terminal 1
MCP_BRIDGE_URL=http://127.0.0.1:8000 python cascade_bridge.py  # Terminal 2+

# Troubleshooting
cat ~/.mcp_server.lock    # Xem lock
rm ~/.mcp_server.lock     # Xoá nếu crash bất thường
```

---

## 📦 Backup & Recovery

```bash
# Backup qua MCP tool (AI gọi tự động)
# → backup_memory_database

# Backup thủ công
bash scripts/backup_chroma.sh

# Backup tự động (cron — weekly 3AM)
crontab -e
# Thêm dòng: 0 3 * * 0 /path/to/vibe-light-mcp/scripts/backup_chroma.sh

# Restore
tar xzf ~/.mcp_global_db/backups/chromadb_backup_YYYYMMDD_HHMMSS.tar.gz -C ~/.mcp_global_db
```

---

## 📚 Tech Stacks hỗ trợ

Android/Kotlin · KMP · Flutter/Dart · iOS/Swift · Python · React Native · Vue.js 3

> 💡 Thêm stack mới? Chỉ cần sửa `tech_stacks/registry.yaml` — không cần sửa code.

---

## 📄 License

MIT
