# 🧠 TechStack Local MCP Server

Local Model Context Protocol (MCP) Server với **Hybrid RAG** (L1/L2 Memory). Tự động phát hiện tech stack, quản lý context thông minh theo 2 tầng, và cung cấp rules/skills cho AI agents.

## Kiến trúc

```
AI Agent (Antigravity, Claude, Cursor, Windsurf...)
        │  stdio / JSON-RPC
        ▼
┌────────────────────────────────────────┐
│        TechStackLocalMCP (FastMCP)     │
│        main.py — 9 Tools              │
├────────────┬───────────────────────────┤
│  Engines   │  Knowledge Base           │
│            │  tech_stacks/             │
│  context   │  ├── android_kotlin/      │
│  execution │  ├── kmp/                 │
│  knowledge │  ├── flutter_dart/        │
│  tracker   │  └── vue_js/              │
└──────┬─────┴───────────────────────────┘
       │  HttpClient (:8888)
       ▼
┌────────────────────────────────────────┐
│      ChromaDB HTTP Server              │
│      ~/.mcp_global_db                  │
├──────────────────┬─────────────────────┤
│  L1: Working     │  L2: Knowledge      │
│  Memory          │  Brain              │
│  (per workspace) │  (global, vĩnh viễn)│
│  TTL: 3 ngày     │  TTL: ♾️            │
└──────────────────┴─────────────────────┘
```

### Hybrid RAG — L1/L2 Memory

| Tầng | Collection | Chức năng | Vòng đời |
|---|---|---|---|
| **L1** | `mcp_local_{hash}` | Code đang sửa, logs, drafts — riêng mỗi project | Auto-cleanup 3 ngày |
| **L2** | `mcp_global_knowledge` | Rules, skills, bug fixes, configs — dùng chung | Vĩnh viễn |

**Federated Search**: Khi AI tìm kiếm → query L1 + L2 cùng lúc → merge → re-rank theo distance → trả kết quả gắn tag `[L1_LOCAL]` / `[L2_GLOBAL]`.

---

## Cài đặt

### 1. Clone & Setup

```bash
git clone https://github.com/PhanHug93/vibe-light-mcp.git
cd vibe-light-mcp

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Start ChromaDB Server

```bash
# Option 1: Script (khuyến nghị)
./start_chroma.sh

# Option 2: Chạy ngầm (sống sót khi đóng terminal)
nohup ./start_chroma.sh > /tmp/chroma.log 2>&1 &

# Option 3: Auto-start khi login (macOS)
cp com.mcp.chromadb.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mcp.chromadb.plist
```

> Script tự kiểm tra port, tìm `chroma` binary, và tạo `~/.mcp_global_db/`.
> AI clients cũng có thể gọi `manage_server(action="chroma_start")` để khởi động.

### 3. Kiểm tra

```bash
# ChromaDB connection
curl -s http://localhost:8888/api/v2/heartbeat && echo " ✅ ChromaDB running"

# Python syntax
.venv/bin/python -m py_compile main.py && echo "✅ MCP OK"
```

---

## Tích hợp AI Client

Cấu hình qua file JSON. Thay `<username>` bằng username thực tế.

### Antigravity (Gemini)

File: `~/.gemini/settings.json`

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

### Claude Desktop

File: `~/Library/Application Support/Claude/claude_desktop_config.json`

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

### Cursor

File: `~/.cursor/mcp.json` (cùng format trên)

### Windsurf

File: `~/.codeium/windsurf/mcp_config.json` (cùng format trên)

> ⚠️ **Quan trọng**: Dùng **đường dẫn tuyệt đối**. Đảm bảo ChromaDB server đã chạy trước khi start MCP.

---

## 9 Tools

### Memory (Hybrid RAG)

| Tool | Tier | Mô tả |
|---|---|---|
| `store_working_context(text, source, tech_stack, workspace_id)` | **L1** | Lưu code/log/draft tạm thời (auto-cleanup 3 ngày) |
| `store_knowledge(text, source, tech_stack)` | **L2** | Lưu knowledge vĩnh viễn (rules, best practices, bug fixes) |
| `search_memory(query, n_results, tech_stack, workspace_id)` | **L1+L2** | Federated search → merge → re-rank by distance |
| `cleanup_workspace(days, workspace_id)` | **L1** | Garbage-collect records cũ |
| `memory_stats()` | **L1+L2** | Thống kê chunks và collections |

### Workspace & Knowledge

| Tool | Mô tả |
|---|---|
| `analyze_workspace(project_path)` | Quét project → phát hiện tech stack → trả rules + skills |
| `sync_knowledge(repo_url)` | Đồng bộ knowledge base từ Git repo |

### System

| Tool | Mô tả |
|---|---|
| `run_terminal_command(command, timeout)` | Shell execution có blocklist bảo mật + timeout 60s |
| `server_health()` | Uptime, RAM, ChromaDB status, knowledge base stats |

---

## Tech Stacks

| Stack | File nhận diện | Knowledge |
|---|---|---|
| Android/Kotlin | `build.gradle.kts`, `build.gradle` | rules + skills |
| KMP | `settings.gradle.kts` | rules + skills |
| Flutter/Dart | `pubspec.yaml` | rules + skills |
| Vue.js 3 | `package.json` | rules + skills |

---

## Monitoring

```bash
# Terminal health check
bash monitor.sh

# Qua MCP tool (AI agent tự gọi)
# → server_health()
# → memory_stats()
```

---

## Cấu trúc Project

```
vibe-light-mcp/
├── main.py                 # FastMCP entry point (9 tools)
├── context_engine.py       # Hybrid RAG — L1/L2, HttpClient, federated search
├── execution_engine.py     # Sandboxed terminal (blocklist + timeout)
├── knowledge_updater.py    # Git sync (clone/pull/force-reset)
├── usage_tracker.py        # Daily analytics & satisfaction scoring
├── start_chroma.sh         # ChromaDB HTTP server launcher
├── monitor.sh              # Terminal health check
├── pyproject.toml          # Dependencies
├── .gitignore
└── tech_stacks/
    ├── android_kotlin/     # rules.md + skills.md
    ├── kmp/
    ├── flutter_dart/
    └── vue_js/
```

---

## Bảo mật

`run_terminal_command` chặn lệnh nguy hiểm:

- **Blocked**: `rm`, `sudo`, `mkfs`, `dd`, `kill`, `shutdown`...
- **Patterns**: `rm -rf`, `chmod 777`, pipe to bash, `$(...)`
- **Timeout**: Auto-kill sau 60s
- **Output**: Truncate tại 50K chars

---

## License

MIT
