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

## ⚡ Cài đặt

```bash
git clone https://github.com/PhanHug93/vibe-light-mcp.git
cd vibe-light-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 🗄️ Khởi động ChromaDB

```bash
./scripts/start_chroma.sh
```

<details>
<summary>Auto-start mỗi khi bật máy (macOS)</summary>

```bash
cp scripts/com.mcp.chromadb.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mcp.chromadb.plist
```
</details>

## 🚀 Chạy MCP Server

```bash
# stdio (mặc định — cho Antigravity, Claude)
python main.py

# SSE server (streaming, multi-client)
python main.py --transport sse --port 8000

# Streamable HTTP (MCP spec mới, streaming)
python main.py --transport streamable-http --port 8000
```

Hoặc cấu hình qua biến môi trường:

```bash
MCP_TRANSPORT=sse MCP_PORT=9000 python main.py
```

### Biến môi trường

| Biến | Mặc định | Mô tả |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `stdio` · `sse` · `streamable-http` |
| `MCP_HOST` | `127.0.0.1` | Bind address cho HTTP transports |
| `MCP_PORT` | `8000` | Listen port cho HTTP transports |
| `MCP_EXEC_MODE` | `allowlist` | `allowlist` (chỉ lệnh an toàn) · `unrestricted` (cho phép tất cả — chỉ dùng khi dev) |
| `MCP_CHROMA_HOST` | `localhost` | ChromaDB host |
| `MCP_CHROMA_PORT` | `8888` | ChromaDB port |

## 🔌 Kết nối AI Client

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

**Option A: stdio trực tiếp**
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

**Option B: Bridge (nếu stdio gặp trục trặc trên Android Studio)**

Chạy SSE server trước: `python main.py --transport sse`

```json
{
  "mcpServers": {
    "tech-stack-expert": {
      "command": "/Users/<username>/projects/vibe-light-mcp/.venv/bin/python",
      "args": ["/Users/<username>/projects/vibe-light-mcp/cascade_bridge.py"]
    }
  }
}
```
</details>

> ⚠️ Dùng **đường dẫn tuyệt đối**. Đảm bảo ChromaDB đã chạy trước khi mở AI client.

## 🤖 Tích hợp AI Agent — Kích hoạt đầy đủ sức mạnh MCP

Để AI agent tận dụng **100% khả năng** của MCP (auto-recall, memory, tech detection), bạn cần copy System Prompt vào rules file của project:

### Quick Setup (chọn 1 lệnh theo nền tảng)

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

Hệ thống bảo mật sử dụng **Defense-in-Depth** (4 lớp bảo vệ) thay vì blocklist:

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

## 📚 Tech Stacks hỗ trợ

Android/Kotlin · KMP · Flutter/Dart · iOS/Swift · Python · React Native · Vue.js 3

> 💡 Thêm stack mới? Chỉ cần sửa `tech_stacks/registry.yaml` — không cần sửa code.

---

## 📄 License

MIT
