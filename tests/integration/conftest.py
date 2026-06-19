from __future__ import annotations

# Integration test fixtures
# 用途：測試跨模組的流程（爬蟲 → Firestore → 通知），mock 外部 HTTP 而非內部邏輯
#
# 開發各功能模組後，在此補充：
# - mock Telegram Bot API HTTP 回應（使用 respx 或 pytest-httpx）
# - mock 運動筆記爬蟲 HTTP 回應（固定 HTML fixture）
# - Firestore Emulator 連線設定
