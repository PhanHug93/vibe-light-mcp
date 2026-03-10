---
description: Quy trình tạo Pull Request cho vibe-light-mcp
---

## Trước khi tạo PR

1. Hỏi user: **"Bạn muốn đánh version bao nhiêu cho PR này?"**
2. Nếu user **có điền version** (ví dụ `2.1.0`):
   - Cập nhật `__version__` trong `main.py`
   - Cập nhật `version` trong `pyproject.toml`
   - Commit thay đổi version
3. Nếu user **không điền** hoặc nói "không cần": bỏ qua, không thay đổi version

## Tạo PR

4. Push branch lên remote
5. Cung cấp link tạo PR cho user

## Sau khi merge PR

6. Nếu có version mới:
   // turbo
   - `git checkout main && git pull origin main`
   // turbo
   - `git tag v<version>` (ví dụ `git tag v2.1.0`)
   // turbo
   - `git push origin v<version>`
7. Nếu không có version: không tạo tag
