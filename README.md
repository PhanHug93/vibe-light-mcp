# TechStack Local MCP Server

Local Model Context Protocol (MCP) Server cho Mobile & Web development. Tự động phát hiện tech stack, cung cấp rules/skills cho AI agents, và quản lý context thông minh.

## Tổng quan

```
AI Agent (Antigravity, Claude, Cursor...)
        │
        ▼  (stdio / JSON-RPC)
┌──────────────────────────────┐
│     TechStackLocalMCP        │
│     main.py (FastMCP)        │
├──────────────────────────────┤
│  6 Tools:                    │
│  • analyze_workspace         │
│  • compress_and_store_context│
│  • query_local_memory        │
│  • run_terminal_command      │
│  • sync_knowledge            │
│  • server_health             │
├──────────────────────────────┤
│  Engines:                    │
│  • context_engine (ChromaDB) │
│  • execution_engine (Shell)  │
│  • knowledge_updater (Git)   │
├──────────────────────────────┤
│  Knowledge Base:             │
│  tech_stacks/                │
│  ├── android_kotlin/         │
│  ├── kmp/                    │
│  ├── flutter_dart/           │
│  └── vue_js/                 │
└──────────────────────────────┘
```

## Cài đặt

### 1. Clone & Setup

```bash
git clone <repo-url> local-mcp-server
cd local-mcp-server

# Tạo virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Cài dependencies
pip install -e .
# hoặc nếu dùng uv:
uv pip install -e .
```

### 2. Kiểm tra hoạt động

```bash
.venv/bin/python -c "import main; print(f'✅ {len(main.mcp._tool_manager._tools)} tools registered')"
```

## Tích hợp với AI Client

MCP Server giao tiếp qua **stdio** (JSON-RPC). Mỗi AI client cấu hình bằng file JSON riêng.

---

### Antigravity (Gemini)

File: `~/.gemini/settings.json`

```json
{
  "mcpServers": {
    "tech-stack-expert": {
      "command": "/Users/<username>/projects/local-mcp-server/.venv/bin/python",
      "args": ["/Users/<username>/projects/local-mcp-server/main.py"],
      "env": {}
    }
  }
}
```

---

### Claude Desktop

File: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "tech-stack-expert": {
      "command": "/Users/<username>/projects/local-mcp-server/.venv/bin/python",
      "args": ["/Users/<username>/projects/local-mcp-server/main.py"]
    }
  }
}
```

---

### Cursor

File: `~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "tech-stack-expert": {
      "command": "/Users/<username>/projects/local-mcp-server/.venv/bin/python",
      "args": ["/Users/<username>/projects/local-mcp-server/main.py"]
    }
  }
}
```

---

### Windsurf

File: `~/.codeium/windsurf/mcp_config.json`

```json
{
  "mcpServers": {
    "tech-stack-expert": {
      "command": "/Users/<username>/projects/local-mcp-server/.venv/bin/python",
      "args": ["/Users/<username>/projects/local-mcp-server/main.py"]
    }
  }
}
```

> **⚠️ Quan trọng**: Thay `<username>` bằng username thực tế trên máy. Dùng **đường dẫn tuyệt đối** cho cả `command` và `args`.

---

## 6 Tools

| Tool | Mô tả |
|---|---|
| `analyze_workspace(project_path)` | Quét project, phát hiện tech stack, trả rules + skills |
| `compress_and_store_context(text_data, metadata_source)` | Lưu text vào ChromaDB (chunking + embedding) |
| `query_local_memory(query, n_results)` | Semantic search trong context đã lưu |
| `run_terminal_command(command, timeout)` | Chạy lệnh terminal (có blocklist bảo mật, timeout 60s) |
| `sync_knowledge(repo_url)` | Đồng bộ knowledge base từ Git repo |
| `server_health()` | Kiểm tra server: uptime, RAM, ChromaDB, stacks |

## Tech Stacks hỗ trợ

| Stack | File nhận diện | Knowledge |
|---|---|---|
| Android/Kotlin | `build.gradle.kts`, `build.gradle` | rules + skills |
| KMP | `settings.gradle.kts` | rules + skills |
| Flutter/Dart | `pubspec.yaml` | rules + skills |
| Vue.js 3 | `package.json` | rules + skills |

## Monitoring

```bash
# Terminal
bash monitor.sh

# Hoặc qua MCP tool (AI agent gọi)
# → server_health()
```

## Cấu trúc project

```
local-mcp-server/
├── main.py                 # Entry point — FastMCP server (6 tools)
├── context_engine.py       # ChromaDB RAG (lazy-init, paragraph-aware chunking)
├── execution_engine.py     # Sandboxed terminal runner (blocklist + timeout)
├── knowledge_updater.py    # Git sync (clone/pull/force-reset)
├── monitor.sh              # Health check script
├── pyproject.toml          # Dependencies
├── .gitignore
└── tech_stacks/
    ├── android_kotlin/
    │   ├── rules.md        # Clean Architecture, Security, Performance...
    │   └── skills.md       # Gradle, ADB, testing commands...
    ├── kmp/
    │   ├── rules.md
    │   └── skills.md
    ├── flutter_dart/
    │   ├── rules.md
    │   └── skills.md
    └── vue_js/
        ├── rules.md
        └── skills.md
```

## Bảo mật

`run_terminal_command` chặn các lệnh nguy hiểm:

- **Blocked commands**: `rm`, `sudo`, `mkfs`, `dd`, `kill`, `shutdown`...
- **Blocked patterns**: `rm -rf`, `chmod 777`, `chown`, pipe to bash, `$(...)`, `` `...` ``
- **Timeout**: Auto-kill sau 60s
- **Output**: Truncate tại 50K chars

## License

MIT
