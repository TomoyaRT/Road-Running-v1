# Road Running Bot — Handoff Document

Generated: 2026-06-20（最後更新：2026-06-20 下午，依使用者實測回報修正）

---

## ⚡ 執行規範（接手 AI 必讀）

1. **一次只執行一個任務。** 嚴禁同時動手多個問題。完成、驗證、commit 後，才進入下一個任務。
2. **嚴格按照「待辦事項」章節的優先順序（P0 → P1 → P2）依序執行。** 不可跳號、不可自行調整順序。
3. **每個任務都遵循專案 TDD 流程：** 先寫失敗 test → 實作最小程式碼 → Stop hook 自動驗 L2+L3 → 派 Code Review Agent → 全過才 commit。
4. **任何 `git push` 前必須先詢問使用者。**
5. **開工前先做「零成本診斷」：** 能用 `requests` / `gcloud` 直接驗證假設的，先驗證再寫程式，不要憑猜測動手。

---

## Project Overview

台灣路跑推播 Telegram Bot。從運動筆記（running.biji.co）爬取路跑賽事，透過 Telegram 主動推播可報名活動給訂閱者，並提供輪播瀏覽介面。

**Repository:** TomoyaRT/Road-Running-v1  
**Branch:** main  
**Deploy:** GCP Cloud Run (`road-running-bot`, region: `us-central1`)

---

## Tech Stack

| 類別 | 技術 |
|------|------|
| Runtime | Python 3.12 |
| Bot framework | python-telegram-bot 21.10（webhook 模式） |
| Web server | Quart 0.20.0 + uvicorn 0.34.3（ASGI） |
| Database | Google Cloud Firestore（region: `asia-east1`） |
| Scraper | beautifulsoup4 4.13.4 + requests 2.32.3 |
| Infra | Cloud Run / Cloud Scheduler / Artifact Registry / Secret Manager |
| CI/CD | GitHub Actions → `.github/workflows/deploy.yml` |

---

## Architecture

```
Telegram → /webhook (POST) → python-telegram-bot → handlers.py
Cloud Scheduler → /crawl (POST) → crawler.py → Firestore (events)
Cloud Scheduler → /notify (POST) → push.py → Telegram (send to users)
```

### Cloud Scheduler Jobs

| Job | 排程 | 時區 | 用途 |
|-----|------|------|------|
| `crawl-daily` | `0 4 * * *` | Asia/Taipei（台北標準時間） | 每天 04:00 爬蟲並存 Firestore |
| `notify-hourly` | `0 5-23 * * *` | Asia/Taipei（台北標準時間）✓ | 每小時通知訂閱者 |

> **注意：** Cloud Scheduler 區域為 `asia-east1`，Cloud Run 在 `us-central1`，兩者可正常互通。  
> `notify-hourly` 時區已於 GCP Console 確認為台北標準時間，排程設定本身**無誤**。

### Firestore Collections

| Collection | 用途 |
|-----------|------|
| `users` | 訂閱者資料（user_id, notification_hour, preferred_city） |
| `events` | 爬蟲快取的路跑活動（以 URL 的 MD5 為 doc ID） |

---

## Source Files

```
src/
  main.py              # Quart ASGI app，webhook / crawl / notify / static endpoints
  utils.py             # tw_today()：台灣時區（UTC+8）的 date.today()
  bot/
    handlers.py        # 所有 Telegram command & callback handlers；get_db()
    cards.py           # 活動卡片格式化；send_event_card / send_carousel_start
    webapp_api.py      # Telegram Mini App init_data 驗證
  scraper/
    running_biji.py    # 爬蟲邏輯（parse / filter / enrich）；RaceEvent dataclass
    crawler.py         # crawl_and_store()：爬 → filter → enrich → 存 DB
  db/
    firestore_client.py # FirestoreClient：subscribe / get_events / replace_events 等
  notifier/
    push.py            # notify_users()：從 DB 取活動、按城市篩選、送 Telegram
  static/
    index.html         # Telegram Mini App HTML
    default-bg.jpg     # 沒有活動圖片時的預設背景圖（1.7MB）
tests/
  unit/                # pytest + AsyncMock（不打真實 API）142 tests，全部通過
  integration/         # mock HTTP 跨模組測試
```

---

## RaceEvent Dataclass（核心資料結構）

```python
@dataclass
class RaceEvent:
    name: str
    race_date: date
    location: str
    url: str                    # biji 活動詳情頁 URL（永遠存在）
    reg_start: date | None
    reg_end: date | None
    city: str = ""              # extract_city() 從 location 提取的縣市
    image_url: str | None = None   # 活動封面圖（目前有問題，見問題一）
    official_url: str | None = None  # 外部報名連結（或簡章）
    organizer: str | None = None     # 主辦單位
    categories: list[str] = field(default_factory=list)  # 路跑組別（目前有問題，見問題二）
```

---

## Subscription Flow（使用者設定流程）

```
/start
  → 歡迎訊息 + ReplyKeyboard（查詢可報名 / 即將開放 / 設定）
  → InlineKeyboard: 選時段（s1-s4）
  → slot_callback → 選具體時間（hour）
  → hour_callback → 選地區（北中南東離島 / 不限地區）
  → region_callback → 選縣市
  → city_callback → 儲存 subscription（notification_hour + preferred_city）

設定修改：
  "設定" → build_settings_keyboard
  → 修改推播時間（重跑完整流程）
  → 修改推播地區（只更新 city，不動 hour）
  → 取消訂閱
```

---

## 已完成功能（Commit 順序）

以下功能已在程式碼層級完成並部署，但部分有實測 bug（見「已知問題」章節）。

| Commit | 功能 | 實測狀態 |
|--------|------|---------|
| `e48a9b4` | 爬蟲 + Firestore 快取 + Cloud Scheduler | 爬蟲邏輯存在，但 DB 更新有疑慮 |
| `c50bd50` | 卡片改讀 DB；立刻報名按鈕 | 卡片顯示正常，圖片有誤（問題一） |
| `6f51223` | 兩層地區選擇（北中南東離島 → 縣市） | 選擇流程正常，但推播篩選無效（問題四） |
| `704d20e` | 初次訂閱感謝訊息 | 正常 |
| `e592784` | tw_today() 修正台灣時區 | 正常 |
| `3cead09` | 從 biji 詳情頁取 image / 主辦單位 / 路跑組別 | 圖片錯誤（問題一）、組別不完整（問題二） |
| `ecddefa` | 防止 relevant=[] 時清空 DB；清快取；詳細 logging | 已部署，未再實測 |

---

## 已知問題（依嚴重程度排序）

---

### 【問題一】活動卡片圖片全部一樣且不正確 ⚠️ 嚴重

**實測現象：**  
在 Telegram Mini App（點「查詢可報名活動」）瀏覽每張活動卡片，所有卡片的圖片**完全相同**，且顯示的並非路跑活動相關圖片（可能是運動筆記網站的預設圖或同一張佔位圖）。

**目前程式邏輯：**  
`src/scraper/running_biji.py` 的 `_do_fetch_biji_detail()` 對每個活動的 biji 詳情頁抓取 `og:image` meta tag。問題可能在：
- biji 詳情頁對所有活動回傳相同的網站預設 `og:image`（非活動專屬圖）
- 或是 `og:image` 抓取失敗，全部退回到 `default-bg.jpg` 佔位圖

**核心洞察（問題的本質）：**  
運動筆記（biji.co）是**賽事聚合平台**，它的活動詳情頁 `og:image` 是平台共用的通用圖（所以每個活動看起來都一樣）。**真正的活動圖片存在於各賽事自己的報名／簡章網站**——也就是使用者點「立刻報名」後跳轉到的那個外部網站。

使用者提供的範例（這類網站都有完整且專屬的活動資訊、圖片、組別、報名費）：
- `https://www.ctrun.com.tw/Activity?EventMain_ID=334`（中華民國路跑協會報名系統）
- `https://www.focusline.com.tw/260920IL?promo=taipeimarathon`（FocusLine 報名系統）

**鐵則：** 每個正式路跑活動，**一定**有「活動簡章」與「報名網址」——否則無人能報名、無人知道辦什麼。所以這兩個資訊必然存在，問題只在於「如何精準找到」。

---

### 📋 解決方案 1.1（依 80/20 帕累托法則排列，由最高效到最後備援）

> **原則：** 我們**已經**在抓 biji 詳情頁（為了組別、主辦單位），而且**已經**透過 `_extract_reg_url()` 取出外部報名連結存進 `official_url`。所以最高槓桿的修法，是「複用既有的 `official_url`」，而非重新發明搜尋機制。

#### 步驟 0 — 零成本診斷（動手前必做，先驗證假設）

不寫任何程式，直接用 `requests` 抓 3–5 個真實活動驗證：
1. 抓 biji 詳情頁 → 印出 `og:image` → 確認是否每個活動都相同／通用圖。
2. 對每個活動，取出 `official_url`（外部報名站）→ 抓該頁 → 印出 `og:image` → 確認是否**各自不同、且為活動專屬海報圖**。
3. 用使用者提供的兩個範例 URL（ctrun / focusline）實際確認它們的 `og:image` 是否為活動圖。

> 這一步成本趨近於零，但能在寫任何程式前確定根因，避免白做工。

#### 步驟 1 — 主路徑（預期解決 ~80% 案例，改動最小）

把活動圖片來源從「biji 詳情頁的 og:image」**改為「`official_url` 報名站的 og:image」**：
- `official_url` 已存在、已被 `_extract_reg_url()` 抽出，**不需新增搜尋邏輯**。
- 修改 `_do_fetch_biji_detail()`：在拿到 `official_url` 後，多發一個 `requests.get(official_url)`，對其 HTML 跑 `extract_og_image()`，作為 `image_url`。
- 成本：每個活動多一次 HTTP 請求；但 enrichment 已用 `_ENRICH_EXECUTOR`（16 條 thread）平行化，且有 `_biji_detail_cache` 快取，邊際成本低。
- **同時順帶解決問題二（組別不完整）**：報名站（ctrun/focusline）頁面結構乾淨、組別集中，比 biji 更容易解析出**完整**組別。

#### 步驟 2 — 第一層備援（official_url 缺失或 og:image 抓不到時）

- 若 biji 詳情頁找不到外部報名連結（`official_url` 為 `None`），或該站 og:image 抓取失敗 → 退而抓 **biji 詳情頁 `<body>` 內第一張非 icon／非 calendar 的 `<img>`**（活動海報通常以一般 `<img>` 呈現，非 meta tag）。

#### 步驟 3 — 第二層備援（關鍵字搜尋，僅在前兩步都失敗時才考慮，成本最高）

- 僅針對「biji 完全沒有外部連結」的少數活動，才用使用者提議的「精準關鍵字搜尋」：
  - 用**活動正式名稱 + 主辦單位 + 舉辦地點**組成查詢（不要用模糊／簽套式搜尋，要用最精準的關鍵字）。
  - 找到最可能的報名站／簡章 URL 後，再抓其 og:image。
- **為何排最後：** 需要 web search API（有成本與延遲），且結果可能命中錯誤網站、可靠度低。依 80/20，這只服務長尾的少數案例，不應作為主路徑。

#### 步驟 4 — 最終備援

- 以上全失敗 → 使用 `default-bg.jpg` 預設背景圖（`PLACEHOLDER_IMAGE_URL`，已正常運作）。

---

**驗證方式（完成後如何確認真的修好）：**
1. 本地對 5–10 個真實活動跑一次 enrichment，斷言 `image_url` **彼此互不相同**、且網域指向各報名站（非 biji 通用圖）。
2. 針對 ctrun / focusline 兩個範例 URL 寫單元測試，確認能正確抽出 og:image。

**成本評估（為何此方案符合帕累托）：**
| 方案 | 額外成本 | 可靠度 | 覆蓋率 |
|------|---------|--------|--------|
| 步驟 1（複用 official_url） | 每活動 +1 HTTP（已平行化） | 高（確定性） | ~80% |
| 步驟 2（biji 內 img） | 無（同一次請求） | 中 | +10~15% |
| 步驟 3（關鍵字搜尋） | search API 費用＋延遲 | 低 | 長尾少數 |

→ 80% 的效果來自步驟 1 的微小改動（複用既有資料），完全不需引入搜尋 API。搜尋只作為長尾備援。

**相關程式碼：**
- `src/scraper/running_biji.py`: `_do_fetch_biji_detail()`（主修改點）、`extract_og_image()`、`_extract_reg_url()`（已抽出 official_url）、`_extract_image_url()`（biji 內 img 備援）、`_extract_categories()`（步驟 1 順帶改善組別）
- `src/bot/cards.py`: `PLACEHOLDER_IMAGE_URL`（最終備援，已正常）

---

### 【問題二】路跑組別（categories）顯示不完整 ⚠️ 嚴重

**實測現象：**  
活動卡片上的「報名組別」只顯示其中一個組別，並非該活動的完整組別清單（例如一個活動有 42K、21K、10K、5K 四個組別，但只顯示其中一個，且是隨機的）。

**目前程式邏輯：**  
`src/scraper/running_biji.py` 的 `_extract_categories()` 找到第一個包含「組別」關鍵字的 `<td>`/`<th>` cell，取其相鄰 cell 的文字並分割。問題可能在：
- biji 頁面的組別資訊分散在多個 table row 而非單一 cell
- 或者分割符（`[、/\n\r|]`）不符合實際 HTML 格式
- 或是只取到第一個 match 就 return，沒有繼續找後面的

**建議方向：**
1. 直接 `requests.get()` 幾個有多組別的活動 URL，印出 HTML，觀察組別在 DOM 中的真實結構
2. 根據實際結構調整 `_extract_categories()` 的解析邏輯

**相關程式碼：**
- `src/scraper/running_biji.py`: `_extract_categories()`, `_CATEGORY_KEYWORDS`

---

### 【問題三】系統主動推播完全沒有觸發 ⚠️ 嚴重

**實測現象：**  
使用者設定好推播時間與地區後，從未收過**任何一次**系統主動推播，一次都沒有。表示整個推播鏈路有根本性故障，並非偶發問題。

**已排除的原因：**
- Cloud Scheduler `notify-hourly` 時區：已確認為台北標準時間，排程 `0 5-23 * * *`，設定正確 ✓

**尚未排查的可能根因（需逐一確認）：**

1. **DB 裡沒有 open events** → `notify_users()` 在 `if not open_events: return` 處靜默跳過，不送任何通知。這是目前最可能的根因，且與下方 DB 更新問題（問題五）直接相關。

2. **Firestore `users` document 的 `notification_hour` 值不符** → 例如值是 `0` 或 `null`，導致 `get_users_for_hour(hour=14)` 永遠查不到使用者。

3. **`notify_endpoint` 靜默 500** → `src/main.py` 的 `notify_endpoint` 有 `assert _telegram_app is not None` 但**沒有 try-except**，若 startup 失敗或 `notify_users` 拋例外，整個請求會 500 但沒有任何 error log。

4. **Cloud Scheduler HTTP target 設定錯誤** → notify-hourly 的「設定執行作業」區段（HTTP target URL、Method）尚未確認是否正確指向 Cloud Run 的 `/notify` endpoint。

**診斷步驟（AI 可直接執行）：**
```bash
# 1. 查 notify endpoint 的 Cloud Run logs
gcloud run services logs read road-running-bot \
  --region=us-central1 --limit=50 \
  --filter='textPayload=~"Hour [0-9]+"'

# 2. 強制執行 notify-hourly 並立即看 logs
gcloud scheduler jobs run notify-hourly --location=asia-east1
gcloud run services logs read road-running-bot --region=us-central1 --limit=20

# 3. 查 Firestore users collection（需 Python 環境 + credentials）
# 或在 GCP Console → Firestore → users → 找自己的 user_id document
```

**相關程式碼：**
- `src/main.py`: `notify_endpoint()` — 缺 try-except
- `src/notifier/push.py`: `notify_users()` — `if not open_events: return` 是靜默跳過
- `src/db/firestore_client.py`: `get_users_for_hour()`

---

### 【問題四】推播城市篩選完全無效（收到全台灣活動）⚠️ 嚴重

**實測現象：**  
使用者不管選擇哪個地區（例如「台北市」），收到的推播通知永遠包含全台灣所有地區的活動，篩選設定完全不生效。

**程式碼判斷：**  
`src/notifier/push.py` 的 `notify_users()` 篩選邏輯本身正確：
```python
city = user.get("preferred_city", "all")
city_events = filter_events_by_city(open_events, city)
```
`filter_events_by_city` 在 `city == "all"` 時回傳全部活動，否則只回傳符合縣市的活動。邏輯無誤。

**根本原因（推測）：**  
Firestore `users` collection 裡該使用者 document 的 `preferred_city` 欄位值是 `"all"` 或欄位不存在（`data.get("preferred_city", "all")` 預設為 `"all"`）。可能原因：
- 使用者訂閱時選擇了「不限地區」
- 或使用者訂閱時用的是舊版程式碼（城市功能上線前），document 沒有 `preferred_city` 欄位

**暫時解法：**  
使用者在 bot 內重新設定一次推播地區：「設定」→「修改推播地區」→ 選縣市，確認 Firestore 的 `preferred_city` 被正確更新後，再測試推播是否只推該城市。

**需確認：**  
此問題與問題三（推播完全沒有觸發）可能是同一根因（DB 無 open events）。建議**先解決問題三**，確認推播能夠觸發後，再驗證城市篩選是否正確。

**相關程式碼：**
- `src/notifier/push.py`: `notify_users()` → `filter_events_by_city()`
- `src/db/firestore_client.py`: `get_users_for_hour()` → 回傳 `preferred_city`

---

### 【問題五】DB 更新狀況不明（爬蟲執行成功但資料疑似未更新）⚠️ 待確認

**實測現象：**  
手動在 GCP Console 對 `crawl-daily` 執行「強制執行」，Cloud Scheduler 顯示成功（HTTP 200），但 Firestore events collection 的文件 update_time 沒有變動，仍顯示當天上午的時間戳。

**已修正的相關 bug（`ecddefa`）：**
- 舊版在 `relevant=[]` 時會呼叫 `replace_events([])` 清空所有 events → 已加 guard
- 每次 crawl 開始前自動清除 `_biji_detail_cache` → 避免同一 instance 服務舊快取
- 加了每步的 INFO log（`fetch_events: X total events` / `filter_relevant: X events`）

**可能根因（仍未確認）：**
- `fetch_events()` 抓到 HTML 但 parse 出 0 筆（biji 網站結構改版或短暫封鎖）
- response body 是 `"stored 0 events"`，HTTP 200 讓 Cloud Scheduler 顯示成功但 DB 完全沒動

**診斷步驟：**
```bash
# 強制執行後立即看 logs，確認每步的數字
gcloud run services logs read road-running-bot \
  --region=us-central1 --limit=30 \
  --filter='textPayload=~"fetch_events:|filter_running:|filter_relevant:|Crawl complete"'
```

**相關程式碼：**
- `src/scraper/crawler.py`: `crawl_and_store()` — 每步都有 INFO log
- `src/scraper/running_biji.py`: `fetch_events()`, `parse_events_html()`

---

## 環境變數（Cloud Run 目前設定）

| 變數 | 來源 | 用途 | 狀態 |
|------|------|------|------|
| `GCP_PROJECT_ID` | deploy.yml env var | Firestore 專案 ID | ✓ |
| `WEBHOOK_URL` | deploy.yml secret | Telegram webhook URL | ✓ |
| `TELEGRAM_BOT_TOKEN` | Secret Manager | Bot token | ✓ |
| `WEBHOOK_SECRET` | Secret Manager | webhook 驗證 | ✓ |
| `GCP_CLOUD_RUN_URL` | **未設定** | （原用於 PLACEHOLDER_IMAGE_URL） | 已改由 WEBHOOK_URL 衍生，無需設定 ✓ |

---

## GCP 診斷工具評估（問題六：是否導入 GCP MCP）

**需求背景：**  
目前診斷 GCP 問題（Cloud Run logs、Firestore 資料、Cloud Scheduler 狀態）需要手動操作 GCP Console 或在 terminal 輸入 gcloud 指令，希望讓 AI 能直接存取 GCP 資源進行診斷。

**現況（已可做到）：**  
`settings.json` 已授權 `Bash(*)` 權限，且本機已安裝並登入 `gcloud` CLI。AI 目前**已可直接執行**：
```bash
# Cloud Run logs
gcloud run services logs read road-running-bot --region=us-central1 --limit=50

# Cloud Scheduler 狀態
gcloud scheduler jobs describe notify-hourly --location=asia-east1

# 強制執行 job
gcloud scheduler jobs run crawl-daily --location=asia-east1
```

Firestore 資料讀取需要額外處理：可透過執行一小段 Python（使用 `google-cloud-firestore` SDK）來讀取，或透過 `gcloud firestore` 命令列工具（功能較有限）。

**GCP MCP 的評估：**  
若希望 AI 能直接讀取 Firestore collection、即時查詢 BigQuery logs、或操作更多 GCP 資源，可考慮安裝 GCP 官方 MCP server（`@google-cloud/mcp-server`）或社群版本。但目前 `gcloud` CLI 已涵蓋大部分診斷需求，**短期內優先用 gcloud 解決問題即可，GCP MCP 可列為中期評估項目**。

---

## 驗證架構（三層）

| 層 | 時機 | 工具 | 行為 |
|----|------|------|------|
| Layer 1（語法） | 每次 Write/Edit 後（PostToolUse hook） | ruff + mypy | 非阻擋，注入回饋 |
| Layer 2（單元） | 每次準備回覆前（Stop hook） | pytest tests/unit/ | 阻擋，失敗強制修正 |
| Layer 3（回歸） | 同上（接在 L2 後） | pytest tests/（全套件） | 阻擋 |

目前測試數量：**142 tests**，全部通過。

---

## 待辦事項（依優先順序）

### P0 — 必須先解決（功能性問題）

1. **【問題三】診斷推播系統** — 用 `gcloud` 強制執行 notify-hourly 並立即讀 Cloud Run logs，確認是 "no open events"、"no subscribers" 還是 500 error。找到根因後修復。

2. **【問題五】確認爬蟲 DB 更新** — 強制執行 crawl-daily 後讀 logs，確認 `fetch_events` 抓到幾筆、`filter_relevant` 過濾後剩幾筆。若每次都是 0，需進一步排查 biji 網站結構是否改版。

3. **【問題一】修正活動圖片取得邏輯** — 依「解決方案 1.1」執行：先做步驟 0 零成本診斷，再實作步驟 1（複用 `official_url` 抓報名站 og:image），備援步驟 2/4。詳細規劃見上方問題一章節。

4. **【問題二】修正路跑組別解析** — 直接抓幾個有多組別的活動 URL，觀察 HTML 結構，修正 `_extract_categories()` 使其能取得完整組別清單。（註：解決方案 1.1 的步驟 1 改抓報名站後，可能順帶改善此問題，建議與問題一一併評估。）

### P1 — 重要但可在 P0 後處理

5. **【問題四】確認城市篩選** — 在問題三修復、確認推播能觸發後，檢查 Firestore 裡的 `preferred_city` 值，確認城市篩選是否正確運作。

6. **`notify_endpoint` 加 try-except** — 目前若 `notify_users` 拋例外，endpoint 無 error log 直接 500，難以診斷。應加 try-except 並記錄 error。

### P2 — 中期評估

7. **GCP MCP 評估** — 評估是否安裝 GCP MCP server，讓 AI 可直接讀取 Firestore collection 和 Cloud Run logs，取代手動 gcloud 指令。

---

## 開發規範摘要

- **Commit message:** Conventional Commits 1.0.0，type: feat/fix/chore/test/refactor/docs/ci
- **程式碼標準:** 所有 function 需有 type hints；f-string only；禁 print()；禁 wildcard import；每個 function 不超過 30 行
- **TDD 規則:** 先寫失敗 test → 實作最小程式碼 → Stop hook 自動驗 L2+L3 → 派 Code Review Agent → 確認後 commit
- **git push 前：** 必須詢問使用者確認，其他所有 git 操作（add/commit/status/diff）直接執行
- **語言：** 與使用者溝通用繁體中文；程式碼、變數名稱、commit message 用英文
