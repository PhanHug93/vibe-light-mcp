# 🧠 TechStack Local MCP Server

> Biến AI của bạn thành một developer thực thụ — tự nhận diện project, nhớ context, và học hỏi qua từng workspace.

**TechStack Local MCP Server** là một MCP (Model Context Protocol) server chạy local trên máy Mac. Nó giúp các AI coding assistants (Antigravity, Claude, Cursor, Windsurf...) trở nên thông minh hơn bằng cách:

- 🔍 **Tự nhận diện dự án** — Quét project và trả về coding rules + skills phù hợp
- 🧠 **Nhớ context theo 2 tầng** — Bộ nhớ ngắn hạn (L1) cho project hiện tại + bộ nhớ dài hạn (L2) dùng chung mọi dự án
- 🔎 **Tìm kiếm thông minh** — Federated search ghép kết quả từ cả L1 và L2, xếp hạng theo độ liên quan
- 🛡️ **Chạy lệnh an toàn** — Terminal có blocklist bảo mật, tự kill sau 60s
- 📊 **Theo dõi sử dụng** — Thống kê tech stack nào được hỏi nhiều, đo mức hài lòng

---

## 🎯 Giải quyết vấn đề gì?

| Vấn đề | Giải pháp |
|---|---|
| AI quên context sau vài tin nhắn | **L1 Memory** — lưu code, logs, error traces tạm thời |
| Phải dạy lại AI cùng một rule nhiều lần | **L2 Knowledge** — lưu vĩnh viễn, dùng chung mọi project |
| Lỗi "database is locked" khi mở nhiều workspace | **ChromaDB HTTP Server** — một server duy nhất, mọi workspace kết nối qua mạng |
| AI không biết project dùng công nghệ gì | **Auto-detect** — quét file, trả rules + skills theo tech stack |

---

## 📐 Kiến trúc

```
  Antigravity / Claude / Cursor / Windsurf
                 │
                 ▼  stdio (JSON-RPC)
  ┌──────────────────────────────────┐
  │   TechStack Local MCP Server     │
  │   10 Tools · FastMCP · Python    │
  └──────────────┬───────────────────┘
                 │  HttpClient
                 ▼
  ┌──────────────────────────────────┐
  │     ChromaDB Server (:8888)      │
  ├────────────────┬─────────────────┤
  │  L1: Working   │  L2: Knowledge  │
  │  Memory        │  Brain          │
  │  Per project   │  Global         │
  │  TTL 3 ngày    │  Vĩnh viễn      │
  └────────────────┴─────────────────┘
```

### L1 vs L2 — Khi nào dùng cái nào?

| | L1 — Working Memory | L2 — Knowledge Brain |
|---|---|---|
| **Dùng cho** | Code đang sửa, logcat, crash trace, UI draft | Rules, best practices, solved bugs, configs mẫu |
| **Phạm vi** | Chỉ project hiện tại | Tất cả projects |
| **Thời gian sống** | Auto-xóa sau 3 ngày | Vĩnh viễn |
| **Ví dụ** | *"Lưu file ViewModel này"* | *"Luôn dùng sealed class cho UiState"* |

---

## 🚀 Cài đặt (3 bước)

### Bước 1 — Clone & cài đặt

```bash
git clone https://github.com/PhanHug93/vibe-light-mcp.git
cd vibe-light-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Bước 2 — Khởi động ChromaDB

```bash
# Cách đơn giản nhất
./start_chroma.sh

# Chạy ngầm (không mất khi đóng terminal)
nohup ./start_chroma.sh > /tmp/chroma.log 2>&1 &

# Auto-start mỗi khi bật máy (macOS)
cp com.mcp.chromadb.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mcp.chromadb.plist
```

> 💡 **Ghi chú**: AI client cũng có thể tự gọi `manage_server(action="chroma_start")` để khởi động ChromaDB mà không cần mở terminal.

### Bước 3 — Kết nối AI Client

Thêm config vào file JSON của AI client. Thay `<username>` bằng tên user thật.

<details>
<summary><strong>Antigravity (Gemini)</strong> — ~/.gemini/settings.json</summary>

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
<summary><strong>Claude Desktop</strong> — ~/Library/Application Support/Claude/claude_desktop_config.json</summary>

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
<summary><strong>Cursor</strong> — ~/.cursor/mcp.json</summary>

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
<summary><strong>Windsurf</strong> — ~/.codeium/windsurf/mcp_config.json</summary>

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

> ⚠️ Dùng **đường dẫn tuyệt đối**. Đảm bảo ChromaDB đã chạy trước.

---

## 🛠 10 Tools

### 🧠 Memory — Lưu trữ & Tìm kiếm context

| Tool | Khi nào dùng | Ví dụ user nói |
|---|---|---|
| `store_working_context` | Lưu code/log tạm thời vào L1 | *"Lưu file này lại"*, *"Nhớ error trace này"* |
| `store_knowledge` | Lưu knowledge vĩnh viễn vào L2 | *"Nhớ rule này cho mọi project"* |
| `search_memory` | Tìm trong cả L1 + L2 | *"Tìm lại lỗi NullPointer hôm qua"* |
| `cleanup_workspace` | Dọn dẹp L1 cũ | *"Xóa context cũ"* |
| `memory_stats` | Xem thống kê bộ nhớ | *"Đang lưu bao nhiêu chunks?"* |

### 🔍 Workspace & Knowledge

| Tool | Khi nào dùng | Ví dụ user nói |
|---|---|---|
| `analyze_workspace` | Quét project, trả rules + skills | *"Phân tích project này"* |
| `sync_knowledge` | Cập nhật knowledge từ Git | *"Update knowledge base"* |

### ⚙️ System & Monitoring

| Tool | Khi nào dùng | Ví dụ user nói |
|---|---|---|
| `run_terminal_command` | Chạy lệnh shell an toàn | *"Run ls -la"*, *"Build project"* |
| `server_health` | Kiểm tra server | *"Check server status"* |
| `usage_stats` | Xem analytics sử dụng | *"Hôm nay tech nào được dùng nhiều?"* |
| `manage_server` | Start/stop ChromaDB, update MCP | *"Start database"*, *"Update MCP"* |

---

## 📚 Tech Stacks hỗ trợ

| Stack | Nhận diện qua | Nội dung |
|---|---|---|
| 🤖 Android/Kotlin | `build.gradle.kts` | Clean Architecture, Security, Coroutines... |
| 🔗 KMP | `settings.gradle.kts` | Shared modules, expect/actual... |
| 🎯 Flutter/Dart | `pubspec.yaml` | State management, navigation... |
| 🌐 Vue.js 3 | `package.json` | Composition API, Pinia, routing... |

> Muốn thêm stack mới? Tạo folder `tech_stacks/<tên_stack>/` với `rules.md` + `skills.md`.

---

## 📁 Cấu trúc Project

```
vibe-light-mcp/
├── main.py                 # MCP Server entry point (10 tools)
├── context_engine.py       # Hybrid RAG — L1/L2, federated search
├── execution_engine.py     # Terminal runner (blocklist + timeout)
├── knowledge_updater.py    # Git sync engine
├── usage_tracker.py        # Daily analytics & satisfaction scoring
├── start_chroma.sh         # ChromaDB launcher script
├── com.mcp.chromadb.plist  # macOS auto-start service
├── monitor.sh              # Terminal health check
├── pyproject.toml          # Dependencies
└── tech_stacks/
    ├── android_kotlin/     # rules.md + skills.md
    ├── kmp/
    ├── flutter_dart/
    └── vue_js/
```

---

## 🔒 Bảo mật

`run_terminal_command` có lớp bảo vệ chống lệnh nguy hiểm:

- 🚫 **Blocked**: `rm`, `sudo`, `mkfs`, `dd`, `kill`, `shutdown`...
- 🚫 **Patterns**: `rm -rf`, `chmod 777`, pipe to bash, `$(...)`
- ⏱️ **Timeout**: Tự kill sau 60 giây
- 📏 **Output**: Giới hạn 50K ký tự

---

## 📄 License

MIT — Tự do sử dụng, chỉnh sửa, phân phối.
