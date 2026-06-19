# 專案事前準備記錄

> 建立日期：2026-06-19
> 專案名稱：Road Running Bot（台灣路跑推播 Telegram Bot）

---

## 專案目標

打造一個 Telegram Bot，每天主動推播「目前可報名的路跑活動」給用戶，並提供按鈕讓用戶查詢「未來 30 天內即將開放報名的活動」。部署於 GCP，透過 GitHub CI/CD 自動化流程。

---

## 一、Telegram

### 操作平台
- Telegram → @BotFather

### 完成動作
- 透過 `/newbot` 指令建立新的 Telegram Bot
- 取得 Bot Token（格式：`數字:英數字串`）

### 拿到的資訊
| 項目 | 說明 | 存放位置 |
|------|------|---------|
| Bot Token | Telegram Bot 的身份驗證金鑰 | `.env` → `TELEGRAM_BOT_TOKEN` / GCP Secret Manager |

---

## 二、Google Cloud Platform（GCP）

### 操作平台
- GCP Console：[console.cloud.google.com](https://console.cloud.google.com)
- gcloud CLI（本地終端機）

### 2-1 帳號與帳單

| 動作 | 說明 |
|------|------|
| 建立 GCP 帳號 | 綁定信用卡（驗證用，不會自動扣款） |
| 啟用帳單警報 | 帳單 → 預算和快訊 → 建立預算，上限 $1 USD，50% / 100% 警示，email 通知 |

### 2-2 專案

| 項目 | 值 |
|------|---|
| 專案名稱 | Road-Running-Bot |
| Project ID | 存於 `.env` → `GCP_PROJECT_ID` |

### 2-3 啟用的 API

以下 6 個 API 已全部啟用：

| API | 用途 |
|-----|------|
| Cloud Run Admin API | 部署並執行 Bot 主程式 |
| Cloud Scheduler API | 排程每日通知與爬蟲觸發 |
| Cloud Firestore API | 儲存用戶資料與活動快取 |
| Artifact Registry API | 儲存 Docker image |
| Cloud Build API | CI/CD 自動化建構 |
| Secret Manager API | 安全儲存 Token 等機密資訊 |

### 2-4 Firestore 資料庫

| 設定項目 | 值 |
|---------|---|
| 資料庫 ID | `(default)` |
| 模式 | Firestore in Native mode |
| 版本 | Standard |
| 位置類型 | 區域（單一 Region） |
| Region | `asia-east1`（台灣） |
| 安全性規則 | 限定（預設拒絕所有讀寫，僅後端 Service Account 可存取） |
| 即時更新 | 停用 |
| 時間點復原 | 停用 |
| 排定的備份 | 停用 |
| 加密 | Google 代管的加密金鑰 |

> **選擇 asia-east1 的原因**：Firestore 免費方案不限 Region，資料存台灣較合規。Cloud Run 則維持在 us-central1 享有免費方案。

### 2-5 Artifact Registry

| 設定項目 | 值 |
|---------|---|
| Repository 名稱 | `road-running-bot` |
| 格式 | Docker |
| 模式 | 標準 |
| 位置類型 | 區域（單一 Region） |
| Region | `us-central1`（愛荷華州） |
| 加密 | Google 代管的加密金鑰 |
| 不可變的映像檔標記 | 停用 |
| 資源清理政策 | 模擬測試（待後續 CI/CD 建立後加入刪除舊 image 政策） |
| 安全漏洞掃描 | 已啟用（但 Container Scanning API 停用，實際不執行，不計費） |

> **選擇 us-central1 的原因**：Cloud Run 在 us-central1，Artifact Registry 與 Cloud Run 同 Region 才不會產生跨 Region 的 image 拉取費用。

### 2-6 Secret Manager

已建立以下兩個 Secret：

| Secret 名稱 | 內容 | 用途 |
|------------|------|------|
| `telegram-bot-token` | Telegram Bot Token | Cloud Run 執行時讀取，用於呼叫 Telegram API |
| `webhook-secret` | 隨機 hex 字串（openssl rand -hex 32 產生） | 驗證 Telegram Webhook 請求的合法性 |

---

## 三、GitHub

### 操作平台
- [github.com](https://github.com)

### 完成動作
- 建立新的 Repository
- 取得 Repository SSH URL（格式：`git@github.com:帳號/repo名稱.git`）

### 拿到的資訊
| 項目 | 說明 |
|------|------|
| Repository SSH URL | 本地端 git remote 串接用 |

> **CI/CD（Workload Identity Federation）尚未設定**，待程式碼開發完成後再進行 GitHub Actions 串接 GCP 的設定。

---

## 四、本地環境

### 安裝的工具

| 工具 | 用途 | 確認指令 |
|------|------|---------|
| Python 3.12+ | 主要開發語言 | `python3 --version` |
| Docker | 本地 image 建構與測試 | `docker --version` |
| gcloud CLI | GCP 資源操作與部署 | `gcloud --version` |

### gcloud CLI 設定

```bash
gcloud auth login                          # 登入 Google 帳號
gcloud config set project PROJECT_ID       # 設定預設專案
```

---

## 五、本地 .env 檔案

> 此檔案已加入 `.gitignore`，不會被提交到 GitHub。

```env
TELEGRAM_BOT_TOKEN=（存於 Secret Manager: telegram-bot-token）
GCP_PROJECT_ID=（你的 GCP Project ID）
WEBHOOK_SECRET=（存於 Secret Manager: webhook-secret）
```

---

## 六、待完成項目（開發階段）

| 項目 | 說明 | 時機 |
|------|------|------|
| Workload Identity Federation | GitHub Actions 部署到 GCP 的無密鑰認證方式 | CI/CD 設定時 |
| Cloud Run Service Account | 給 Cloud Run 讀取 Secret Manager 的權限 | 第一次部署前 |
| Cloud Scheduler Job × 2 | 每小時通知觸發 + 每日凌晨爬蟲觸發 | 部署完成後 |
| Artifact Registry 清理政策 | 自動刪除舊 Docker image，維持在 0.5GB 免費額度內 | CI/CD 設定時 |

---

## 七、架構概覽

```
Telegram 用戶
  ↕ Telegram API（新加坡）
Cloud Run（us-central1）← Webhook 接收 + 通知發送
  ↕
Firestore（asia-east1/台灣）← 用戶資料 + 活動快取
  ↑
Cloud Scheduler（每小時）← 通知排程觸發
Cloud Scheduler（每日 02:00 台灣時間）← 爬蟲觸發

GitHub（程式碼）
  → GitHub Actions
  → Artifact Registry（us-central1）← Docker image
  → Cloud Run（部署）
```

---

## 八、免費方案限制備忘

| 服務 | 免費額度 | 注意事項 |
|------|---------|---------|
| Cloud Run | 每月 200 萬次請求 | min-instances 必須設為 0 |
| Cloud Scheduler | 每月 3 個 Job | 目前規劃使用 2 個 |
| Firestore | 每日 5 萬次讀取 / 4 萬次寫入 / 1 GB 儲存 | 100 用戶規模完全不會超出 |
| Artifact Registry | 0.5 GB 儲存 | 需定期清理舊 image |
| Cloud Build | 每月 2,500 分鐘 | 約可執行 80+ 次建構 |
| Secret Manager | 每月 1 萬次存取 | 遠低於上限 |

**預估月費（100 用戶規模）：$0 USD**
