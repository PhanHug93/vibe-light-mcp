# MCP Memory Rules — TechStack Local MCP Server

> Copy file này vào `.gemini/rules.md` của mỗi dự án để kích hoạt auto-context trên Antigravity.

## 🔄 Auto-Recall (BẮT BUỘC)

1. **Đầu mỗi cuộc hội thoại**: Luôn gọi `auto_recall` với tin nhắn đầu tiên của user trước khi trả lời.
   - `user_message`: tin nhắn hiện tại của user
   - `workspace_path`: đường dẫn tuyệt đối tới project root (suy ra từ file user đang mở)
   - `tech_stack`: tech stack nếu đã biết (vd: `android_kotlin`, `flutter_dart`, `python`)

2. **Hội thoại dài (>10 lượt)**: Gọi lại `auto_recall` để refresh context, tránh quên thông tin quan trọng.

3. **Khi context bị thiếu**: Nếu user nhắc đến thông tin từ cuộc hội thoại trước mà bạn không nhớ, chủ động gọi `search_memory` để tìm.

## 🔍 Tech Stack Detection

Khi bắt đầu với **dự án mới lần đầu tiên**, gọi `analyze_workspace` để:
- Auto-detect tech stack (Android/Kotlin, Flutter, Python, Vue.js, iOS, KMP, React Native)
- Nhận coding rules + skills + references phù hợp

Kết quả trả về bao gồm:
- `rules`: quy tắc coding chuẩn cho stack đó
- `skills`: kỹ thuật nâng cao, patterns, best practices
- `available_references`: danh sách tài liệu tham khảo có sẵn

## 💾 Context Storage (Chủ động lưu)

### Lưu tạm — L1 Working Memory (per-project, tự xóa sau 3 ngày)

Gọi `store_working_context` khi phát hiện:
- **Bug fix quan trọng** — error trace + nguyên nhân + cách fix
- **Architecture decision** — tại sao chọn approach A thay vì B
- **Code pattern** đang làm việc — snippet + giải thích
- **Task progress** — đang làm gì, đến đâu, tiếp theo là gì

Tham số:
- `content`: nội dung cần lưu (text/code/log)
- `workspace_path`: đường dẫn project root (**BẮT BUỘC**)
- `source`: mô tả nguồn (vd: `"ViewModel refactor"`, `"crash fix login"`)
- `tech_stack`: nếu biết

### Lưu vĩnh viễn — L2 Knowledge Brain (global, dùng chung mọi project)

Gọi `store_knowledge` khi phát hiện:
- **Best practices** tổng quát — áp dụng được cho nhiều project
- **Lesson learned** — pattern lỗi hay gặp và cách tránh
- **Config mẫu** — setup chuẩn cho framework/tool

Tham số:
- `content`: nội dung knowledge
- `source`: mô tả (vd: `"Hilt DI best practice"`)
- `tech_stack`: stack liên quan

## 🔎 Tìm kiếm Memory

Gọi `search_memory` khi:
- User hỏi về thông tin từ cuộc hội thoại trước
- Cần tìm lại bug fix, decision, hoặc pattern đã lưu
- Muốn so sánh approach hiện tại với approach cũ

## ⚙️ System Tools

| Tool | Khi nào gọi |
|---|---|
| `server_health` | User hỏi kiểm tra MCP / database |
| `manage_chroma` | User muốn start/stop/kiểm tra ChromaDB |
| `self_update` | User muốn update MCP server |
| `run_terminal_command` | User yêu cầu chạy lệnh terminal |
| `cleanup_workspace` | User muốn dọn dẹp context cũ |
| `sync_knowledge` | User muốn đồng bộ knowledge từ Git |

## ⚠️ Lưu ý quan trọng

- `workspace_path` là **BẮT BUỘC** cho mọi tool liên quan memory. Suy ra từ file user đang mở.
- **Không bao giờ bỏ qua `auto_recall`** ở đầu hội thoại — đây là cơ chế giữ context xuyên session.
- Khi lưu context, viết `source` mô tả rõ ràng để dễ tìm lại sau.
