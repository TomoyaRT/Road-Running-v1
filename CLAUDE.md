# Road Running Bot

台灣路跑推播 Telegram Bot。每日主動推播可報名路跑活動，並提供按鈕查詢 30 天內即將開放報名的活動。部署於 GCP Cloud Run，透過 GitHub Actions 自動化 CI/CD。

## Tech Stack（均使用最新 LTS 穩定版）

- **Python 3.12**
- **python-telegram-bot 21.x**（webhook 模式）
- **quart + uvicorn**（ASGI web server）
- **google-cloud-firestore**
- **beautifulsoup4 + requests**（爬蟲）
- **GCP**：Cloud Run（us-central1）/ Firestore（asia-east1）/ Cloud Scheduler / Artifact Registry / Secret Manager

> 版本衝突或不相容時，先詢問使用者確認，才能降版。

## 專案結構

```
src/
  bot/         # Telegram handlers, commands, inline keyboards
  scraper/     # 運動筆記爬蟲
  notifier/    # 通知推播邏輯
  db/          # Firestore client wrapper
  main.py      # Quart app entry point（webhook + scheduler endpoints）
tests/
  unit/        # pytest + AsyncMock，不打真實 API
  integration/ # mock HTTP，測跨模組流程
.env           # 本地開發用（不 commit）
```

## 常用指令

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -x -q          # 測試
ruff check . --fix            # Lint
ruff format .                 # 格式化
mypy src/                     # 型別檢查
python -m src.main            # 本地執行（long-polling 模式）
```

## 三層驗證架構（CRITICAL）

| 層級 | 觸發時機 | 工具 | 阻擋行為 |
|------|---------|------|---------|
| **Layer 1 語法層** | 每次 Write/Edit 後（PostToolUse） | ruff + mypy | 非阻擋，注入回饋讓 Claude 自行修正 |
| **Layer 2 意圖層** | 每次 Claude 想回覆完成前（Stop） | pytest tests/unit/ | 阻擋，失敗則強制繼續修正 |
| **Layer 3 回歸層** | 同上（Stop，接在 Layer 2 之後） | pytest tests/（全套件） | 阻擋，失敗則強制繼續修正 |

Hook 腳本位於 `.claude/hooks/`，由 `settings.json` 自動掛載。

### 手動執行（Code Review Agent，宣告完成前必做）

**每次功能完成、準備告知使用者之前，必須：**

1. Stop hook 已自動執行 Layer 1–3 並全部通過
2. **另外派遣獨立 Code Review Agent**（不能由同一個開發 Agent 自我審查）：
   ```
   使用 /code-review skill 或 Agent tool（subagent_type: general-purpose）
   ```
3. Code Review Agent 任務：對照使用者的需求，審查實作是否符合意圖、有無破壞原有功能
4. 若 Code Review Agent 發現問題 → 開發 Agent 修正 → 重新觸發整個流程
5. 全部通過後才能回覆使用者「完成」

**不允許在任何層級失敗的情況下回報完成。**

## Agent 分工規則

| Agent 角色 | 使用時機 | 工具 |
|------------|---------|------|
| 開發 Agent（主要） | 實作功能、修正 bug | 本體 |
| Code Review Agent | 宣告完成前，由主 Agent 派遣，獨立審查 | `/code-review` skill 或 `Agent(subagent_type: general-purpose)` |
| 文件查詢 | 使用任何第三方套件 API 前 | context7 MCP，在 prompt 加上 `"use context7"` |

**Playwright MCP 不用於 bot 測試**（Playwright 是網頁 UI 測試工具）。
Telegram bot 測試使用 `pytest` + `AsyncMock` 模擬 Update / Context 物件。

### 測試開發規則（TDD per feature）

每個功能按此順序：
1. 先寫失敗的 unit test（tests/unit/）
2. 實作最小程式碼讓 test 通過
3. Stop hook 自動驗證 Layer 2 + 3
4. 派遣 Code Review Agent 審查
5. 全過才 commit

## 程式碼標準

- 所有 function 必須有 type hints（`from __future__ import annotations`）
- f-string only，禁止 `.format()` 和 `%` 格式化
- 禁止 `print()`，一律使用 `logging`
- 禁止 wildcard import（`from x import *`）
- 每個 function 不超過 30 行；複雜邏輯抽成獨立 function
- 錯誤處理只在真正的邊界（用戶輸入、外部 API）做，不做不可能發生的情境防禦

## Git 規範

**Commit 格式**（Conventional Commits 1.0.0）：`type(scope): 簡短描述（英文）`

type 包含：`feat` / `fix` / `chore` / `test` / `refactor` / `docs` / `ci`

- `git push` 前必須詢問使用者確認
- 其他所有 git 操作（add, commit, status, diff, log, branch）自動執行，不詢問

## 語言規則

- **與使用者的所有溝通**：繁體中文
- **程式碼、變數名稱、function 名稱、檔案名稱**：英文
- **程式碼註解**：中文或英文均可

## 權限規則

此專案內所有操作無須詢問，直接執行：檔案讀寫、套件安裝、指令執行、git add/commit。
**唯一例外：`git push` 前必須詢問使用者。**

## 環境變數

```env
TELEGRAM_BOT_TOKEN=   # GCP Secret Manager: telegram-bot-token
GCP_PROJECT_ID=       # GCP 專案 ID
WEBHOOK_SECRET=       # GCP Secret Manager: webhook-secret
```
