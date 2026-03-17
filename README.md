# 🧠 TechStack Local MCP Server

> Biến AI của bạn thành một developer thực thụ — tự nhận diện project, nhớ context, và học hỏi qua từng workspace.

**TechStack Local MCP Server** là một [MCP](https://modelcontextprotocol.io/) server chạy local, giúp các AI coding assistants (Antigravity, Claude, Cursor, Windsurf...) trở nên thông minh hơn bằng cách:

- 🔍 **Tự nhận diện dự án** — Quét project, trả về coding rules + skills phù hợp
- 🧠 **Nhớ context 2 tầng** — L1 (tạm, per-project) + L2 (vĩnh viễn, global)
- 🔄 **Auto-recall** — Tự nhớ lại ngữ cảnh từ các cuộc hội thoại trước
- 🛡️ **Chạy lệnh an toàn** — Có blocklist bảo mật, tự kill sau 60s
- 📊 **Theo dõi sử dụng** — Thống kê tool usage, đo mức hài lòng

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

## 🔌 Kết nối AI Client

Thêm config vào file JSON của AI client. Thay `<username>` bằng username trên máy.

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
<summary><strong>Windsurf</strong> — <code>~/.codeium/windsurf/mcp_config.json</code></summary>

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

> ⚠️ Dùng **đường dẫn tuyệt đối**. Đảm bảo ChromaDB đã chạy trước khi mở AI client.

## 📝 Kích hoạt Auto-Recall (khuyến nghị)

Copy file rules vào project bạn muốn AI nhớ context:

```bash
cp /path/to/vibe-light-mcp/mcp_rules.md /path/to/your-project/.gemini/rules.md
```

Sau khi thêm, AI sẽ tự động gọi `auto_recall` đầu mỗi hội thoại để lấy context cũ.

---

## 🛠 Tools

### 🧠 Memory

| Tool | Mô tả |
|---|---|
| `store_working_context` | Lưu code/log tạm vào L1 (per-project, TTL 3 ngày) |
| `store_knowledge` | Lưu knowledge vĩnh viễn vào L2 (global) |
| `search_memory` | Tìm trong cả L1 + L2 |
| `auto_recall` | ⚡ Tự nhớ context (rate‑limited, fail‑safe) |
| `cleanup_workspace` | Dọn dẹp L1 cũ |
| `memory_stats` | Thống kê bộ nhớ |

### 🔍 Workspace & Knowledge

| Tool | Mô tả |
|---|---|
| `analyze_workspace` | Quét project, trả rules + skills theo tech stack |
| `sync_knowledge` | Cập nhật knowledge base từ Git |
| `update_tech_stack` | Cập nhật rules/skills (merge‑aware, chống trùng lặp) |

### ⚙️ System

| Tool | Mô tả |
|---|---|
| `run_terminal_command` | Chạy lệnh shell an toàn (blocklist + 60s timeout) |
| `server_health` | Kiểm tra trạng thái server + ChromaDB |
| `manage_chroma` | Start / stop / status ChromaDB |
| `self_update` | Pull code MCP mới nhất từ Git |

---

## 📚 Tech Stacks hỗ trợ

Android/Kotlin · KMP · Flutter/Dart · iOS/Swift · Python · React Native · Vue.js 3

> 💡 Thêm stack mới? Chỉ cần sửa `tech_stacks/registry.yaml` — không cần sửa code.

---

## 📄 License

MIT
