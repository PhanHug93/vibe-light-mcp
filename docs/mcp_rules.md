# MCP Memory Rules

## Auto-Recall
- Ở đầu mỗi cuộc hội thoại, **luôn gọi tool `auto_recall`** với tin nhắn đầu tiên của user để lấy ngữ cảnh từ bộ nhớ MCP trước khi trả lời.
- Nếu cuộc hội thoại dài hơn 10 lượt, gọi lại `auto_recall` để refresh context.

## Context Storage
- Khi phát hiện thông tin quan trọng (bug fix, decision, pattern mới), tự động gọi `store_working_context` để lưu vào L1.
- Khi hoàn thành một task có kết luận hữu ích (best practice, lesson learned), gọi `store_knowledge` để lưu vào L2 vĩnh viễn.

## Tech Stack Detection
- Ở đầu cuộc hội thoại đầu tiên với dự án mới, gọi `analyze_workspace` để detect tech stack và nhận rules/skills phù hợp.
