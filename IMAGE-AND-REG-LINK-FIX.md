# 圖片與「立刻報名」連結問題 — 調查與修復方案

> 調查日期：2026-06-20｜資料來源：對 `running.biji.co` 線上即時抓取驗證（非推測）

## 一、問題描述（使用者回報）

| # | 現象 | 期望結果 |
|---|------|---------|
| 1 | 活動卡片圖片無法正常顯示，且**全部來自同一個 domain** | 顯示各路跑活動官網自己的活動圖片 |
| 2 | 不論點哪一張卡片，「立刻報名」按鈕**一律連到運動筆記/biji** | 連到該活動的官方完整資訊／報名頁（如下方範例網站） |

使用者期望的目標網站範例：
- https://lohasnet.tw/BNM40thMarathon2026/
- https://bao-ming.com/eb/content/7013#reg
- https://www.focusline.com.tw/261018LI
- https://irunner.biji.co/2026SpongeBob-KHH（注意：irunner 的**個別活動頁**是可接受的）
- https://www.ctrun.com.tw/Activity?EventMain_ID=334

---

## 二、根本原因（單一根因，造成兩個現象）

兩個問題其實是**同一個 bug**：`official_url` 對每一個活動都被抽成 `https://irunner.biji.co/`（irunner 首頁）。

- 卡片按鈕用 `event.official_url or event.url`（`src/bot/cards.py:90`、`src/bot/handlers.py:369`），所以按鈕全部指向同一個 irunner 首頁。
- 圖片在 `enrich_event` 改成抓 `official_url` 的 og:image（任務二），既然 `official_url` 全是 irunner 首頁，og:image 自然**全部同一張、同一個 domain**。

### 為什麼 `official_url` 全變成 irunner 首頁？

biji 活動詳情頁在 header/側欄有一個 biji 自家推廣連結：

```
DOM 位置 idx48：文字 '筆記報名' → https://irunner.biji.co/   （irunner 首頁，無活動資訊）
DOM 位置 idx59：文字 '線上報名' → https://www.focusline.com.tw/260621KF/personal  （真正官方報名頁）
```

任務二把 `_SKIP_DOMAINS` 從 `"biji.co"` 收窄成 `"running.biji.co"`（目的是放行 irunner 個別活動頁）。
**副作用**：irunner **首頁**那個 `'筆記報名'` 連結不再被略過，而它的文字含「報名」，又排在 DOM 較前面（idx48 < idx59），於是 `_extract_reg_url` 對**每一頁**都先撞到它而回傳 `https://irunner.biji.co/`，把真正的官方連結（focusline、bao-ming…）整個遮蔽掉。

### 線上實證（跑現行 `_extract_reg_url`）

```
cid 13010: official_url = https://irunner.biji.co/
cid 12906: official_url = https://irunner.biji.co/
cid 12949: official_url = https://irunner.biji.co/
cid 12937: official_url = https://irunner.biji.co/
cid 12962: official_url = https://irunner.biji.co/
cid 12919: official_url = https://irunner.biji.co/
```

每一個活動都是 irunner 首頁 → 完全對應使用者「按鈕全連到 biji、圖片全同一個 domain」的描述。

### 次要原因

部分活動的官方連結文字是 **「官方網站」/「活動官方網站」**（例：cid 12906 → natgeomedia.com），而現行 `_REG_KEYWORDS` / `_BROCHURE_KEYWORDS` 完全沒有這組關鍵字，這類活動即使修掉首頁遮蔽問題仍會抽不到連結。

---

## 三、解決方案（已用線上資料驗證）

### 修改 `src/scraper/running_biji.py` 的 `_extract_reg_url`

1. **略過 biji 推廣首頁，但保留 irunner 個別活動頁**
   新增判斷：URL 的 host 屬於 `*.biji.co` 且 path 為空或 `/` → 略過（擋掉 `https://irunner.biji.co/` 這種裸首頁）；`irunner.biji.co/<活動slug>` 這類深層路徑**照常保留**。

2. **新增「官方網站」關鍵字層級**
   在 `報名` → `簡章` 之間（或之後）加入 `_OFFICIAL_KEYWORDS = {"官方網站", "活動官方網站"}`，補上只有官網連結、沒有報名連結的活動。

   建議比對順序（優先取「能直接報名」的頁）：
   `線上報名/報名` → `官方網站` → `活動簡章`

> 不需要動 `cards.py` / `handlers.py` / `enrich_event` — 它們的邏輯本來就正確，只是被餵了錯的 `official_url`。

### 修復後線上實證（原型已驗證）

```
cid 13010: https://nb10krun.com/Test2026/index.html        ← 官方網站
cid 12906: https://irunner.biji.co/tw_wodrun2026/signup     ← irunner 個別活動頁（保留 ✓）
cid 12949: https://bao-ming.com/eb/content/6945#reg         ← 線上報名
cid 12937: https://bao-ming.com/eb/content/6923#reg         ← 線上報名
cid 12962: http://esg.soonest.com/Home/Index               ← 線上報名
cid 12919: https://www.focusline.com.tw/260621KF/personal  ← 線上報名
```

全部指向各活動真正的官方/報名站，且 irunner 裸首頁已正確被擋、irunner 個別活動頁正確保留。

### 圖片（og:image）連帶修復實證

`official_url` 修正後，`extract_og_image` 直接抓到各站自己的活動圖：

```
bao-ming.com           -> https://bao-ming.com/.../banner-...jpg            ✓ 各站不同
natgeomedia.com        -> https://www.natgeomedia.com/event/2026/.../fb-share2026.jpg ✓
nb10krun.com           -> https://nb10krun.com/images/m-banner-line.jpg     ✓
irunner.biji.co/deep   -> https://cdntwirunner.biji.co/reg/736/...jpg       ✓ 每活動不同
```

---

## 四、已知限制（非本專案 bug，文件記錄）

部分官方站是純前端 SPA、HTML 內無 og:image，server-side 抓不到圖：

```
focusline.com.tw     -> og:image = None（SPA，圖由 JS 載入）
esg.soonest.com      -> og:image = None
```

這類活動「立刻報名」按鈕仍會**正確**連到官方站（問題 2 解決），只是卡片圖片會落空。
biji 列表縮圖目前 server-side 也抓不到（lazy-load / 背景圖），無法當後備。
影響範圍小、屬外站限制，**本次先不處理**；若日後要補圖可評估 headless 渲染或站別客製 selector。

---

## 五、實作步驟（TDD，依專案規範）

1. 先寫失敗 unit test（`tests/unit/test_scraper.py`）：
   - `test_extract_reg_url_skips_irunner_homepage`：HTML 同時含 `'筆記報名'→irunner.biji.co/` 與 `'線上報名'→外站`，斷言回傳**外站**。
   - `test_extract_reg_url_keeps_irunner_event_page`：`'線上報名'→irunner.biji.co/<slug>`，斷言保留該深層連結。
   - `test_extract_reg_url_matches_official_website_keyword`：只有 `'活動官方網站'→外站`，斷言抽得到。
2. 實作最小修改讓測試通過（host+path 判斷、新增官網關鍵字層）。
3. Stop hook 自動跑 Layer 2 + 3。
4. 派遣獨立 Code Review Agent 審查。
5. 全綠後 commit；部署後手動 `gcloud scheduler jobs run crawl-daily`（asia-east1）重爬驗證 Firestore 的 `official_url` 不再全是 irunner 首頁、`image_url` 各不相同。
