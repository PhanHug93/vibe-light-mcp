---
description: Quy trình tạo Pull Request cho vibe-light-mcp
---

## Trước khi tạo PR

> ⚠️ **BẮT BUỘC**: Luôn hỏi user về version TRƯỚC KHI push hoặc tạo PR.
> Nếu quên hỏi → dừng lại, hỏi ngay, rồi mới tiếp tục.

1. Hỏi user: **"Bạn muốn đánh version bao nhiêu cho PR này?"**
2. Nếu user **có điền version** (ví dụ `2.1.0`):
   - Cập nhật `__version__` trong `main.py`
   - Cập nhật `version` trong `pyproject.toml`
   - Commit thay đổi version
3. Nếu user **không điền** hoặc nói "không cần": bỏ qua, không thay đổi version

## Sync main (bắt buộc)

// turbo
4. `git checkout main && git pull origin main`
// turbo
5. `git checkout <feature-branch> && git merge main -m "merge: sync with main before PR"`
// turbo
6. `git push origin <feature-branch>`

## Tạo PR

7. Cung cấp link tạo PR: `https://github.com/PhanHug93/vibe-light-mcp/pull/new/<branch>`

## Sau khi merge PR

8. Nếu có version mới:
   // turbo
   - `git checkout main && git pull origin main`
   // turbo
   - `git tag v<version>` (ví dụ `git tag v2.1.0`)
   // turbo
   - `git push origin v<version>`
9. Nếu không có version: không tạo tag
