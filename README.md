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

- [🚀 Quick Start (Khuyến nghị)](#-quick-start-khuyến-nghị)
- [⚡ Cài đặt thủ công (không Docker)](#-cài-đặt-thủ-công-không-docker)
- [🌐 SSE Hybrid — Multi-Client Architecture](#-sse-hybrid--multi-client-architecture)
- [🐳 Deploy Full Docker (Production Server)](#-deploy-full-docker-production-server)
- [🤖 Tích hợp AI Agent](#-tích-hợp-ai-agent--kích-hoạt-đầy-đủ-sức-mạnh-mcp)
- [🛠 Tools](#-tools)
- [🛡️ Security Model](#️-security-model)
- [🔄 Multi-Instance Behavior](#-multi-instance-behavior)

---

## 🚀 Quick Start (Khuyến nghị)

Kiến trúc khuyến nghị: **ChromaDB chạy Docker** + **MCP Server chạy trực tiếp** (stdio).

```
AI Client (Antigravity/Claude/Cursor)
    │  stdio
    ▼
  main.py (MCP Server)
    │  HTTP :9000
    ▼
  ChromaDB (Docker Container)
```

> 💡 **Tại sao?** Kiến trúc này đơn giản, ổn định, không phụ thuộc vào HTTP streaming library, và AI client kết nối trực tiếp qua stdio (nhanh nhất).

### Bước 1: Clone & cài đặt

```bash
git clone https://github.com/PhanHug93/vibe-light-mcp.git
cd vibe-light-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Bước 2: Chạy ChromaDB bằng Docker

```bash
# Cài Docker: https://www.docker.com/products/docker-desktop/

docker run -d --name mcp-chromadb \
  -p 9000:8000 \
  -v chroma_data:/chroma/chroma \
  -e IS_PERSISTENT=TRUE \
  -e ANONYMIZED_TELEMETRY=FALSE \
  --restart unless-stopped \
  chromadb/chroma:latest
```

Kiểm tra ChromaDB:

```bash
curl http://localhost:9000/api/v2/heartbeat
# → {"nanosecond heartbeat": ...}
```

### Bước 3: Cấu hình AI Client

Thay `<username>` bằng username trên máy.

<details>
<summary><strong>Antigravity</strong> — <code>~/.gemini/antigravity/mcp_config.json</code></summary>

```json
{
  "mcpServers": {
    "tech-stack-expert": {
      "command": "/Users/<username>/projects/vibe-light-mcp/.venv/bin/python",
      "args": ["/Users/<username>/projects/vibe-light-mcp/main.py"],
      "env": {
        "MCP_TRANSPORT": "stdio",
        "MCP_CHROMA_HOST": "127.0.0.1",
        "MCP_CHROMA_PORT": "9000"
      }
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
      "args": ["/Users/<username>/projects/vibe-light-mcp/main.py"],
      "env": {
        "MCP_CHROMA_HOST": "127.0.0.1",
        "MCP_CHROMA_PORT": "9000"
      }
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
      "args": ["/Users/<username>/projects/vibe-light-mcp/main.py"],
      "env": {
        "MCP_CHROMA_HOST": "127.0.0.1",
        "MCP_CHROMA_PORT": "9000"
      }
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
      "args": ["/Users/<username>/projects/vibe-light-mcp/main.py"],
      "env": {
        "MCP_CHROMA_HOST": "127.0.0.1",
        "MCP_CHROMA_PORT": "9000"
      }
    }
  }
}
```
</details>

### Bước 4: Restart AI Client

Restart IDE/app → MCP sẽ tự kết nối. Verify bằng cách yêu cầu AI gọi tool `server_health`.

### Quản lý ChromaDB Docker

```bash
docker logs mcp-chromadb --tail 20   # Xem logs
docker stop mcp-chromadb             # Dừng
docker start mcp-chromadb            # Khởi động lại
docker stats mcp-chromadb            # Xem RAM/CPU
```

---

## ⚡ Cài đặt thủ công (không Docker)

Dùng khi bạn **không muốn dùng Docker** — chạy ChromaDB trực tiếp trên máy.

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
```
</details>

### Bước 3: Cấu hình AI Client

Giống [Quick Start Bước 3](#bước-3-cấu-hình-ai-client), nhưng **không cần env vars** (sử dụng port mặc định 8888):

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

## 🌐 SSE Hybrid — Multi-Client Architecture

> 💡 **Khi nào dùng?** Khi bạn muốn **nhiều AI IDE cùng kết nối 1 MCP server** (Windsurf + Cursor + Claude...) hoặc chia sẻ MCP cho team qua mạng LAN.

Kiến trúc hybrid: ChromaDB chạy Docker, MCP Server chạy SSE trên host, các client kết nối qua `cascade_bridge.py`.

```
 AI Client 1 (Windsurf)     AI Client 2 (Cursor)     AI Client 3 (Claude)
     │  stdio                    │  stdio                    │  stdio
     ▼                           ▼                           ▼
 cascade_bridge.py          cascade_bridge.py          cascade_bridge.py
     │  HTTP POST + SSE          │  HTTP POST + SSE          │  HTTP POST + SSE
     └───────────────────────────┼───────────────────────────┘
                                 ▼
                        main.py (MCP Server)
                        SSE mode — port 8000
                                 │  HTTP :9000
                                 ▼
                     ChromaDB (Docker Container)
```

### Bước 1: Khởi động MCP Server ở chế độ SSE

```bash
cd /path/to/vibe-light-mcp
source .venv/bin/activate

# Start ChromaDB (nếu chưa chạy)
docker start mcp-chromadb

# Start MCP Server — SSE mode
python main.py --transport sse --port 8000
```

> Server sẽ chạy foreground, log ra terminal. Dùng `tmux` hoặc `nohup` nếu muốn chạy nền.

### Bước 2: Cấu hình AI Client với Bridge

`cascade_bridge.py` là proxy stdio ↔ SSE — nhận JSON-RPC từ stdin, POST lên MCP server, và stream kết quả về stdout **real-time**.

<details>
<summary><strong>Windsurf / Cascade</strong> — <code>~/.codeium/windsurf/mcp_config.json</code></summary>

```json
{
  "mcpServers": {
    "tech-stack-expert": {
      "command": "/Users/<username>/projects/vibe-light-mcp/.venv/bin/python",
      "args": ["/Users/<username>/projects/vibe-light-mcp/cascade_bridge.py"],
      "env": {
        "MCP_BRIDGE_URL": "http://127.0.0.1:8000",
        "MCP_BRIDGE_MODE": "sse"
      }
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
      "args": ["/Users/<username>/projects/vibe-light-mcp/cascade_bridge.py"],
      "env": {
        "MCP_BRIDGE_URL": "http://127.0.0.1:8000",
        "MCP_BRIDGE_MODE": "sse"
      }
    }
  }
}
```
</details>

<details>
<summary><strong>Antigravity / Claude / Cline</strong> — cấu hình tương tự</summary>

Thay path file config cho phù hợp:
- Antigravity: `~/.gemini/antigravity/mcp_config.json`
- Claude: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Cline: `.vscode/mcp.json` trong project

Nội dung `mcpServers` giống Windsurf ở trên — chỉ đổi path tới `cascade_bridge.py`.
</details>

### Bước 3: Kết nối nhiều client

```bash
# Terminal 1: MCP Server (SSE mode)
python main.py --transport sse --port 8000

# Terminal 2+: Mỗi client tự động chạy cascade_bridge.py qua config.
# Hoặc test thủ công:
MCP_BRIDGE_URL=http://127.0.0.1:8000 python cascade_bridge.py
```

### Biến môi trường Bridge

| Biến | Mặc định | Mô tả |
|---|---|---|
| `MCP_BRIDGE_URL` | `http://127.0.0.1:8000` | URL MCP server (SSE/HTTP) |
| `MCP_BRIDGE_MODE` | `sse` | `sse` · `http` (streamable-http) |

### Troubleshooting SSE

| Vấn đề | Nguyên nhân | Giải pháp |
|---|---|---|
| Bridge treo không nhận response | Server chưa chạy hoặc sai port | Kiểm tra `python main.py --transport sse` có đang chạy |
| `Timeout: SSE did not provide messages endpoint` | Server chưa sẵn sàng | Đợi server khởi động xong rồi mới chạy bridge |
| `SSE connection error` | Firewall hoặc port bị chiếm | Kiểm tra `lsof -i :8000` |
| `SSE stream closed by server` | Server bị restart | Bridge tự reconnect (exponential backoff 1s → 30s) |
| `singleton lock` khi start server | Đã có server chạy trước đó | `rm ~/.mcp_server.lock` hoặc dùng bridge kết nối |

---

## 🐳 Deploy Full Docker (Production Server)

> ⚠️ **Dành cho deploy 24/7 trên server** (Ubuntu, không có GUI). Dev local nên dùng [Quick Start](#-quick-start-khuyến-nghị).

Full Docker Compose chạy cả **ChromaDB + MCP Server** trong container, expose MCP qua SSE/HTTP.

### Yêu cầu
- Docker Engine ≥ 20.10, Docker Compose ≥ 2.0
- RAM tối thiểu: 4GB (khuyến nghị 8GB)

### Khởi động

```bash
cp deploy/compose/.env.example deploy/compose/.env
# Sửa .env nếu cần (transport, port...)
docker compose -f deploy/compose/docker-compose.yml up -d --build
```

### Kết nối AI Client (qua Bridge)

Khi MCP chạy SSE/HTTP mode trong Docker, dùng `cascade_bridge.py`:

```json
{
  "mcpServers": {
    "tech-stack-expert": {
      "command": "/path/to/.venv/bin/python",
      "args": ["/path/to/cascade_bridge.py"],
      "env": {
        "MCP_BRIDGE_URL": "http://127.0.0.1:8000",
        "MCP_BRIDGE_MODE": "http"
      }
    }
  }
}
```

<details>
<summary><strong>🏗 Kiến trúc Docker (chi tiết)</strong></summary>

```
┌───────────────────────────────────────────────────────┐
│  mcp_internal (internal: true)                        │
│  ┌──────────────┐        ┌──────────────┐             │
│  │   chromadb   │◄──────►│  mcp_server  │             │
│  │   :8000      │        └──────┬───────┘             │
│  │ (NO exposed  │               │                     │
│  │  ports)      │               │                     │
│  └──────────────┘               │                     │
└─────────────────────────────────┼─────────────────────┘
┌─────────────────────────────────┼─────────────────────┐
│  mcp_exposed (bridge)           │                     │
│                      ┌──────────┴───────┐             │
│                      │  mcp_server      │──► :8000    │
│                      └──────────────────┘             │
└───────────────────────────────────────────────────────┘
```

| Component | Chi tiết |
|---|---|
| **ChromaDB** | Internal-only — KHÔNG expose port ra host/LAN |
| **MCP Server** | Dual-network: internal + exposed (port 8000) |
| **Resource Limits** | ChromaDB: 2.5GB / MCP: 1.5GB |
| **Log Rotation** | json-file, max 10MB × 3 files |
| **Security** | Non-root user (`mcpuser`) |

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
│   └── com.mcp.chromadb.plist  # macOS auto-start
└── systemd/
    └── chromadb.service        # Linux auto-start
```

</details>

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
- **Cross-Platform** — Windows dùng `taskkill /F /T /PID`, Unix dùng `os.killpg`
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
