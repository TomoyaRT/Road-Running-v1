# 調查與規劃文件（Investigation & Plan）

---

## 📌 給下一個 Session 的提醒（接手前必讀）

1. **先讀本文件 + `HANDOFF.md`**：本文件是「根因＋方案」，HANDOFF 是原始問題清單與專案背景。
   兩者衝突時以本文件為準（本文件已用線上實證推翻 HANDOFF 多個假設，見文末總結表）。

2. **文件中的「實測數字是 2026-06-20 快照，會過期」**：`crawl-daily` 每天 04:00（台北時間）重爬，
   所以「88 筆事件、53 筆空組別、cid=xxxx」這類**具體數字／事件會變**，但**根因與解法是結構性的、不會變**。
   → **實作前先重跑各任務「調查方法」的零成本診斷**，用當下資料確認，再動手。

3. **如何讀線上資料（本機 ADC 未設定）**：
   - Cloud Run logs：`gcloud run services logs read road-running-bot --region=us-central1 --limit=200`
   - Scheduler：`gcloud scheduler jobs describe notify-hourly --location=asia-east1`
   - Firestore（用 user token 打 REST，免 ADC）：
     ```bash
     TOKEN=$(gcloud auth print-access-token)
     curl -s -H "Authorization: Bearer $TOKEN" \
       "https://firestore.googleapis.com/v1/projects/road-running-bot/databases/(default)/documents/events?pageSize=300"
     ```
   - 想用 `google-cloud-firestore` SDK 直接讀，先跑一次 `gcloud auth application-default login` 設好 ADC（見任務六）。

4. **實作順序與流程**：依 P0 → P1（任務一 → 二 → 三 → 五；任務四由任務一一併解決）。
   嚴格遵守專案 TDD：先寫失敗 test → 最小實作 → Stop hook 自動驗 L2+L3 → 派 Code Review Agent → 全過才 commit。
   `git push` 前必須詢問使用者。

5. **真正要改的核心只有 3 件事**（其餘為誤判或附帶）：
   ① `臺/台` 正規化（任務一，同時解任務四）
   ② 圖片改抓報名站 og:image ＋ 放行 `irunner.biji.co`（任務二）
   ③ 組別改讀 biji `<select><option>`（任務三）

---

> 本文件由接手 AI 依「一次一個任務、先深度調查根因再規劃方案、不動程式碼」的原則撰寫。
> 每個任務獨立成節，包含：調查方法 → 證據 → 根因 → 解決方案規劃 → 驗證方式。
> **本文件只做調查與規劃，不含任何實作。** 實作須另行依專案 TDD 流程進行。

---

## 任務一　【問題三 + 問題四】推播收不到 / 城市篩選無效

調查日期：2026-06-20
狀態：**根因已確認（zero-cost 實證）**，待實作

---

### 一、調查方法（最新生產資料）

本問題屬「系統內部資料一致性」bug，無需 web 搜尋外部資料；
「最新相關資料」= 線上生產環境的實際狀態，已用以下零成本方式取得：

1. `gcloud scheduler jobs describe notify-hourly` — 檢查排程設定
2. `gcloud run services logs read road-running-bot` — 讀取 `/notify`、`/crawl` 實際執行 log
3. Firestore REST API（`gcloud auth print-access-token` + curl）— 直接讀取 `events` collection 的 85 筆 open events，統計各縣市分佈
4. 靜態追蹤程式碼資料流：`handlers.py`（城市選單）→ `firestore_client.py`（儲存 `preferred_city`）→ `running_biji.py`（`extract_city` / `filter_events_by_city`）

---

### 二、關鍵證據（推翻 HANDOFF 原本假設）

**HANDOFF 原假設「推播完全沒觸發、整條鏈路故障」與實際不符。** 證據：

| 證據來源 | 內容 | 推論 |
|---------|------|------|
| Cloud Run log `2026-06-20 06:00:03` | `Notified user 8572749755: 1 events (city=嘉義市)` | **推播鏈路正常**，曾成功送出 |
| Scheduler describe | POST → `/notify`、`timeZone: Asia/Taipei`、`state: ENABLED`、`status: {}`（成功） | 排程設定**完全正確** |
| Cloud Run log（每小時） | `Hour N: no subscribers, skip` / `no events for user ... (city=台北市), skip` | endpoint **沒有 500**，是進入正常分支後靜默 skip |
| `/crawl` log | `Replaced events collection: 88 set, 0 deleted` / `stored 88 running events` | **DB 更新正常**（問題五其實也沒問題，見任務說明） |
| Firestore `events` 統計 | 85 筆 open events，`臺北市:13`、`臺中市:8`、`臺南市:6`、`臺東縣:5` … | 事件城市以**「臺」**儲存 |
| Cloud Run log 對照 | 使用者選 `city=台北市` → `no events ... skip`；選 `city=嘉義市` → 成功推播 | 差別只在 `臺` vs `台` |

關鍵對照：
- 使用者設 `台北市`（13 筆 open events 存在）→ **0 命中、skip** ❌
- 使用者設 `嘉義市`（兩邊拼字相同）→ **命中、推播成功** ✅

---

### 三、根本原因（單一根因，同時造成問題三與問題四）

**`臺`（U+81FA）vs `台`（U+53F0）字元不一致。**

| 位置 | 用字來源 | 實際值 | 檔案 |
|------|---------|--------|------|
| 事件城市 `event.city` | 運動筆記網站原文（官方正體「臺」） | `臺北市` | `running_biji.py` `extract_city()` |
| 使用者偏好 `preferred_city` | bot 城市選單按鈕標籤（俗體「台」） | `台北市` | `handlers.py:50-55` `_REGIONS` |

兩個失效點：

1. **`extract_city()`（`running_biji.py:118`）**：以 `_TW_CITIES`（用「台」）做 `location.startswith(city)`。
   biji 傳回 `臺北市` 時 `startswith("台北市")` 為 False → 落入 `return location` → 直接存回原始的 `臺北市`。
   （所以 DB 存的是「臺」而非選單的「台」。）

2. **`filter_events_by_city()`（`running_biji.py:263`）**：`e.city == city` 精確比對，
   `"臺北市" != "台北市"` → 回傳 0 筆 → `notify_users` 走 `no events for user ... skip` 靜默分支。

**受影響的縣市**（選單用「台」、biji 用「臺」者，共 4 個）：
`台北市` / `台中市` / `台南市` / `台東縣`。
其餘縣市兩邊拼字相同，篩選正常（故 `嘉義市` 可成功推播）。

> 註：HANDOFF 問題四描述「收到全台灣所有活動」與目前「收到 0 筆」相反。
> 研判問題四的「收到全部」是更早期、`preferred_city` 欄位尚未存在 → `data.get(..., "all")` 預設 all 的舊行為；
> 兩層城市選單上線後，`preferred_city` 開始被寫入「台」字城市，症狀就從「全收」翻轉為「全不收」。
> 兩種症狀同一根源：城市值的一致性。

---

### 四、解決方案規劃（最小、外科式）

**核心策略：新增一個 `臺→台` 正規化 helper，套用在「寫入」與「篩選」兩端。**
全專案既有程式碼（`_TW_CITIES`、`_REGIONS` 選單）都用「台」，故統一正規化目標為「台」，改動最小。

#### 修改點 1 — `extract_city()`（治本，讓未來 crawl 存成「台」）
- 比對前先 `location = _normalize_city(location)`，使回傳值與 DB 寫入值統一為「台北市」。

#### 修改點 2 — `filter_events_by_city()`（治標 + 向後相容，立即生效）
- 比對時兩邊都正規化：`_normalize_city(e.city) == _normalize_city(city)`。
- **重要**：此修改讓「DB 既有的 81 筆『臺』資料」不必等下次 crawl 即可立即被「台」查詢命中，
  使用者**不需重新設定**就能恢復收到推播。

#### `_normalize_city` 實作（規劃，非實作）
```
def _normalize_city(name: str) -> str:
    return name.replace("臺", "台")
```

#### 為何不改別處
- 不改 `_REGIONS` / `_TW_CITIES`（已用「台」，正確）。
- 不改 `firestore_client.py`（city 只是被動讀寫，正規化集中在 scraper 層即可）。
- 不需 HANDOFF 原本規劃的「notify_endpoint 加 try-except / 查 scheduler 時區 / 排查 500」——
  那些都不是本問題根因（已實證排除）。`notify_endpoint` 加 try-except 仍可列為 P1 防禦性改善（任務六），但與本 bug 無關。

---

### 五、驗證方式（實作後如何確認真的修好）

1. **單元測試（TDD 先寫失敗測試）**
   - `extract_city("臺北市大安區") == "台北市"`（含 台中/台南/台東）
   - `filter_events_by_city([event(city="臺北市")], "台北市")` 能命中
2. **回歸**：既有 142 tests 全綠。
3. **生產驗證**（部署後）
   - 強制執行 `gcloud scheduler jobs run crawl-daily`，再查 Firestore，確認 `events` 的 city 變為「台北市」。
   - 設定一個 `台北市` 訂閱者於下一個整點，查 log 應出現 `Notified user ...: N events (city=台北市)` 而非 `no events ... skip`。

---

### 六、影響範圍與風險

- 改動僅 2 個 function + 1 個 helper，純字串正規化，無資料破壞風險。
- DB 既有「臺」資料在下次 crawl 後會自然被「台」覆寫；在那之前靠修改點 2 相容。
- 不影響 `filter_open_events` / `filter_upcoming_events` 等其他邏輯。

---

### 七、結論

問題三、問題四為**同一根因（臺/台 不一致）**，且問題五（DB 未更新）經實證為**誤判（DB 正常更新）**。
單一最小修改（正規化 helper + 兩處套用）即可同時解決問題三、四，使用者無需重新設定。

---

## 任務二　【問題一】活動卡片圖片全部相同（biji 通用圖／誤用廣告圖）

調查日期：2026-06-20
狀態：**根因已確認（zero-cost 實證）**，待實作

---

### 一、調查方法（實際抓取最新資料）

1. 對使用者提供的 5 個報名／簡章網站實際 `requests.get` 抓 `og:image`
   （lohasnet / ctrun / bao-ming / focusline / irunner.biji）
2. 對 DB 既有 88 筆事件，用 Firestore REST 統計 `image_url`、`official_url` 分佈與網域
3. 對每個 `official_url` 網域各抓一筆，驗證其 og:image 是否為「活動專屬圖」
4. 對 2 筆 biji 活動詳情頁抓 og:image，驗證 biji 端到底給什麼
5. 對「無 official_url」的 13 筆，抓其 biji 詳情頁，檢查是否藏有被丟棄的報名連結

---

### 二、關鍵證據

**(A) DB 現況：88 筆事件的 `image_url` 100% 相同**
```
[88x] https://running.biji.co/static/default_jpg/competition_470x246.jpg
```
→ 完全證實使用者回報：每張卡片圖片一模一樣，且是運動筆記的**通用預設圖**。

**(B) biji 活動詳情頁的 og:image 永遠是那張預設圖**
```
cid=12733 → og:image = .../static/default_jpg/competition_470x246.jpg
cid=13012 → og:image = .../static/default_jpg/competition_470x246.jpg
```
→ 證實使用者的核心洞察：biji 是聚合平台，**自己不放活動專屬圖**。
現行 `enrich_event` 用 `detail.image_url`（= biji 詳情頁 og:image）覆寫，所以全部變成這張預設圖。

**(C) 報名／簡章網站 og:image = 各自的活動專屬海報** ✓
| 範例網站 | og:image | 結果 |
|---------|----------|------|
| lohasnet.tw | `.../app_banner.jpg` | ✓ 活動海報 |
| ctrun.com.tw | `.../BannerImage/-_1920X500164.jpg` | ✓ 活動橫幅 |
| bao-ming.com | `.../pic/pic_xxx.jpg` | ✓ 活動海報 |
| irunner.biji.co | `.../reg/768/xxx.webp` | ✓ 活動橫幅 |
| beclass.com | `.../share/xxx.jpg` | ✓ |
| joinnow.com.tw | `.../upload_file/870/xxx.jpg` | ✓ |
| toyota.com.tw | `.../og-image.jpg` | △ 系列通用，仍勝過 biji 預設 |
| **focusline.com.tw** | `favicon76.ico` | ✗ **SPA，shell 僅 favicon** |
| **sportsnet.org.tw** | None | ✗ 無 og:image |

**(D) `official_url` 已存在於 DB（75/88），且網域正是各報名站**
```
bao-ming.com:32  signup.lohasnet.tw:19  focusline:8  ctrun:7
beclass:3  lohasnet.tw:2  toyota:2  sportsnet:1  joinnow:1   (None: 13)
```
→ HANDOFF「複用既有 official_url」策略成立：報名連結早已被 `_extract_reg_url` 抽出。

**(E) 「無 official_url」的 13 筆，其實全部都有 irunner.biji.co 報名連結被丟棄**
```
13/13 events: reg_domains=['irunner.biji.co']
```
→ 根因：`_SKIP_DOMAINS` 含 `"biji.co"`，`_extract_reg_url` 的
`any(d in href for d in _SKIP_DOMAINS)` 把 `irunner.biji.co`（biji 的**報名子站**，有專屬 og:image）一併濾掉。
但使用者提供的範例 `irunner.biji.co/2026SpongeBob-KHH` 正是有完整活動圖的報名站。

---

### 三、根本原因

1. **圖片來源錯誤**：`enrich_event`（`running_biji.py:372`）以 biji 詳情頁 og:image 當圖片，
   而 biji og:image 恆為 `competition_470x246.jpg` 通用預設圖 → 88 筆全同。
2. **誤用廣告圖的風險來源**：fallback `_extract_image_url`（`running_biji.py:187`）抓「列表行第一張非日曆 img」，
   這種「隨便抓 `<img>`」正是會誤抓到 banner／廣告圖的寫法。應改用 og:image（網頁指定的代表圖）才安全。
3. **irunner 報名站被誤殺**：`_SKIP_DOMAINS = {"biji.co", ...}`（`running_biji.py:50`）連帶濾掉
   `irunner.biji.co` 這個有專屬圖的合法報名站，使 13 筆事件完全失去 official_url。

---

### 四、解決方案規劃（依 80/20，全部複用既有資料，無需 web search）

**新的圖片來源優先序（取代現行 biji og:image）：**

| 步驟 | 來源 | 覆蓋筆數 | 累計覆蓋 |
|------|------|---------|---------|
| 1 | `official_url` 的 og:image | 66/88 | 75% |
| 2 | 放行 `irunner.biji.co` 後，新增的 official_url 之 og:image | +13 | **90%** |
| 3 | 以上皆無 → `PLACEHOLDER_IMAGE_URL` 預設圖 | 9（focusline 8 + sportsnet 1） | 100% |

**規劃的具體修改點（4 處，皆小改）：**

1. **`_SKIP_DOMAINS`**：把 `"biji.co"` 改為 `"running.biji.co"`，使 `irunner.biji.co` 報名連結不再被丟棄。
   （仍擋掉 running.biji.co 聚合站自身連結。）→ 恢復 13 筆 official_url。

2. **`_do_fetch_biji_detail`**：在拿到 `official_url` 後，**多一個 `requests.get(official_url)`**，
   對其 HTML 跑 `extract_og_image` 作為 `image_url`；不再使用 biji 詳情頁的 og:image。
   - 用 `_ENRICH_EXECUTOR`（16 thread）平行化、`_biji_detail_cache` 快取 → 邊際成本低（每筆 +1 HTTP）。

3. **`extract_og_image` 強化**（避免誤判與相對路徑）：
   - 同時接受 `<meta property="og:image">` 與 `<meta name="og:image">`（focusline/部分站用 `name`）。
   - **排除無效圖**：副檔名 `.ico`／favicon、以及 biji 預設圖網址 → 視為「無圖」往下一步退。
   - 相對路徑用 `urljoin(official_url, content)` 補成絕對網址（如 lohasnet 的 `assets/images/...`）。

4. **`enrich_event`**：圖片優先序改為「official_url og:image → 否則 placeholder」；
   移除「用 biji og:image / biji 列表縮圖」當圖片來源（兩者皆為預設圖且後者有廣告風險）。

**刻意不做（符合簡潔原則）：**
- 不實作 HANDOFF 步驟 3「關鍵字 web 搜尋」——實證顯示 90% 已由既有 official_url 解決，長尾 9 筆退預設圖即可，
  不值得引入 search API 的成本、延遲與誤命中風險。
- 不為 focusline（SPA）導入 headless 瀏覽器——8 筆，退預設圖；如未來要救，再評估其 API（列為長尾備案）。

---

### 五、驗證方式

1. **單元測試（先寫失敗測試）**
   - `extract_og_image` 能從 ctrun／bao-ming／irunner 範例 HTML 取出正確圖。
   - `extract_og_image` 對 `favicon.ico`／biji 預設圖回傳 None。
   - 相對路徑 og:image 經 urljoin 補成絕對網址。
   - `_extract_reg_url` 對含 `irunner.biji.co` 報名連結的 HTML 能回傳該連結（不再被 skip）。
2. **回歸**：既有 142 tests 全綠（注意原本斷言 biji og:image 行為的測試需同步更新）。
3. **生產驗證**（部署後）
   - 強制執行 `crawl-daily`，查 Firestore：`image_url` 的**相異值數量應 ≥ 70**（不再 88 筆全同），
     且 `official_url is None` 的筆數應從 13 降到 0（irunner 已放行）。
   - 隨機抽 5 張卡片，圖片網域應指向各報名站／irunner，而非 `running.biji.co/static/default_jpg`。

---

### 六、影響範圍與風險

- 改動集中在 `running_biji.py` 的 4 個點，純爬蟲層，不動 bot / DB schema。
- 每筆事件多 1 次對 official_url 的 HTTP（75→88 筆），已平行化＋快取，crawl 仍在可接受時間內。
- 風險：少數報名站可能擋爬蟲或改版 → 已有 try/except 退預設圖，不致整批失敗。

---

### 七、與問題二（組別不完整）的關係

本次調查確認報名站（ctrun/bao-ming 等）頁面結構乾淨、資訊集中。
問題二（組別）為獨立任務，但屆時可一併評估「組別是否也改從報名站解析」——
本任務先聚焦圖片，不擴大範圍。

---

### 八、結論

問題一根因為**「圖片取自 biji 通用 og:image」+「irunner 報名站被 `_SKIP_DOMAINS` 誤殺」**。
解法為複用既有 `official_url`（放行 irunner 後覆蓋率達 90%）改抓報名站 og:image，
搭配 og:image 強化與預設圖 fallback，**完全不需 web search**。改動小、可實證驗收。

---

## 任務三　【問題二】路跑組別（categories）顯示不完整

調查日期：2026-06-20
狀態：**根因已確認（zero-cost 實證）**，待實作

---

### 一、調查方法

1. Firestore REST 統計 DB 88 筆 `categories` 的長度分佈與內容
2. 抓 biji 詳情頁與報名站（bao-ming/ctrun/irunner），用 BeautifulSoup 觀察「組別」在 DOM 的真實結構
3. 對 10 筆 biji 詳情頁，專門驗證 `<select><option>` 下拉選單是否穩定列出完整組別

---

### 二、關鍵證據

**(A) DB 現況：組別嚴重缺漏且夾雜雜訊**
```
組別數量分佈 (n_cats: 事件數)：{0: 53, 1: 21, 2: 11, 3: 2, 4: 1}
空組別：53/88
範例：
  「麗晨臺中國際馬拉松」: ['全程', '馬拉松組']         ← 一個組被切成兩段
  「嘉義雙潭星光路跑」  : ['13K挑戰組']                ← 實際有 13K/6.5K/3.5K 三組，只取到一個
  「大觀盃珍珠海岸超半馬」: ['25K','超半程馬拉松','(','限額1000名)']  ← 切出雜訊「(」
```
→ 完全證實使用者回報：組別不完整、且是隨機只顯示一個。

**(B) 現行 `_extract_categories` 的三個失效點**（`running_biji.py:322`）
1. 只搜尋 `<td>/<th>`，但 biji 組別其實在 `<div>`／`<select>` → **53 筆完全抓不到**。
2. 找到第一個關鍵字 cell 後只取「相鄰一個 cell」就 return → 報名站是「比較表」多欄／多列佈局，
   只拿到第一欄 → **21 筆只剩一個組別**。
3. 用 `re.split(r"[、/\n\r|]")` 硬切 → 切出 `(`、`限額1000名)` 等雜訊。

**(C) 各報名站結構分歧、不適合統一解析**
| 站 | 組別呈現方式 |
|----|------------|
| bao-ming | 多個 `組別` 列，每列一組（重複 row） |
| ctrun | 比較表，`報名組別` 為列首，每組一欄 |
| irunner | `組別:` → 相鄰 td 一個值 |
| focusline | SPA（抓不到內容） |
→ 若逐站寫解析，複雜且脆弱，違反簡潔原則。

**(D) 決定性發現：biji 詳情頁的 `<select><option>` 穩定列出完整組別（10/10）**
```
cid=12814 → ['請選擇參賽組別','全程馬拉松組 42.195K','半程馬拉松組 21.0975K','10K 10K','5K 5K']
cid=12859 → ['請選擇參賽組別','半馬組 21K','挑戰組 11K','樂活組 6K','健走組 4K']
cid=12889 → ['請選擇參賽組別','人生勝利組 50K','人生奮鬥組 43K','人生幸福組 24K','人生健康組 10K']
cid=12733 → ['請選擇參賽組別','制霸組 102.5K','挑戰組 51.7K']   ← 此筆現況 DB 為空，新法可救回
```
- 第一個 option 永遠是 placeholder「請選擇參賽組別」，其餘即為**完整組別清單**。
- 此 `<select>` 在 biji 詳情頁（**我們已經會抓**）就有 → **零額外 HTTP**。
- 同時解決 (A) 的三種症狀：空的（53）、不完整（21）、雜訊切割。

---

### 三、根本原因

組別資訊在 biji 是放在報名用的 `<select>` 下拉選單，而非表格；
現行解析鎖定 `<td>/<th>` 表格＋只取單一相鄰 cell＋粗暴切割，三重錯誤導致大量缺漏與雜訊。

---

### 四、解決方案規劃（單一來源，最簡）

**改寫 `_extract_categories`：改從 biji `<select>` 的 `<option>` 取完整組別。**

1. 定位組別 `<select>`：找到文字含「參賽組別」的 `<option>`，取其所屬 `<select>`；
   找不到時退回「頁面全部 `<option>`」（實測該頁僅有此一組 select）。
2. 取出所有 `<option>` 文字，**濾掉 placeholder**（含「請選擇」「參賽組別」「請選擇組別」者）。
3. 輕量清理：
   - 去除連續重複 token（`10K 10K` → `10K`、`5K 5K` → `5K`）。
   - strip、去空字串、長度 < 30 過濾。
4. 不再使用 `<td>/<th>` 表格解析與 `re.split` 粗切。

**為何不從報名站取組別：** 報名站結構分歧（比較表／多 row／SPA），逐站解析複雜脆弱；
biji `<select>` 已是單一、一致、完整、且零額外請求的最佳來源。任務二（圖片）走報名站、任務三（組別）走 biji select，各取所長。

---

### 五、驗證方式

1. **單元測試（先寫失敗測試）**
   - 給含 `<select>` 的 biji 樣本 HTML，`_extract_categories` 回傳**完整**組別、且**不含** placeholder。
   - `10K 10K` → `10K`（連續重複收斂）。
   - 無 select 時回傳 `[]`。
   - 既有「table slash/newline」測試需重寫成 select 結構（行為已改變）。
2. **回歸**：142 tests 全綠（含上面被取代的舊測試）。
3. **生產驗證**（部署後）
   - crawl 後查 Firestore：空組別事件數應從 53 大幅下降（預期 < 10），
     多組別事件（cid=12859/12889 等）應顯示 4 個完整組別、無 `(` 雜訊。

---

### 六、影響範圍與風險

- 僅改寫 `_extract_categories` 一個 function（＋更新對應測試），不增加 HTTP、不動 schema。
- 風險：少數 biji 頁面若無 select（如已停辦或特殊頁）→ 回 `[]`，與現況一致，不致退步。

---

### 七、結論

問題二根因為「解析鎖定錯誤的 DOM（表格）且只取單一 cell」。
改從 biji `<select><option>` 取組別即可一次解決「空白／不完整／雜訊」三症狀，
來源單一、零額外請求，比 HANDOFF 建議的逐站表格解析更簡單可靠。

---

## 任務四　【問題四】推播城市篩選無效（確認＝任務一同根因）

調查日期：2026-06-20
狀態：**根因已確認，與任務一同源**，由任務一之修復一併解決

---

### 一、實證

查 `users` collection（目前唯一使用者）：
```
user 8572749755 | hour 15 | city '台北市'
```
而 `events` 的城市存為 `'臺北市'`（任務一已證實）。

### 二、根因

與任務一**完全相同**：`preferred_city='台北市'`（台） vs `event.city='臺北市'`（臺），
`filter_events_by_city` 精確比對失敗。HANDOFF 推測的「preferred_city 為 all 或欄位不存在」**不成立**——
欄位存在且有值，只是 `臺/台` 對不上。

> HANDOFF 問題四原描述「收到全台灣所有活動」與現況「收到 0 筆」相反，研判為早期（無 preferred_city 欄位→預設 all）的舊症狀；
> 兩層城市選單上線後翻轉為「全不收」。兩者同根：城市值一致性。

### 三、解決方案

**不需獨立修改。** 任務一規劃的 `filter_events_by_city` 正規化（兩端 `臺→台`）即同時修好問題四，
且因為是在「查詢時」正規化，**使用者無需重新設定**：現有 `台北市` 訂閱可立即命中 DB 既有的 `臺北市` 事件。

### 四、驗證

部署任務一修復後，於該使用者的推播時段（hour=15）查 Cloud Run log，
應由 `no events for user 8572749755 (city=台北市), skip` 變為 `Notified user 8572749755: N events (city=台北市)`。

---

## 任務五　【P1】`notify_endpoint` 缺 try-except（防禦性改善）

調查日期：2026-06-20
狀態：**確認為真實缺口**（非本批 bug 根因，但值得補）

---

### 一、現況（`src/main.py:117`）

```python
@quart_app.route("/notify", methods=["POST"])
async def notify_endpoint() -> Response:
    assert _telegram_app is not None
    tw_hour = datetime.datetime.now(...).hour
    bot = _telegram_app.bot
    await notify_users(bot=bot, hour=tw_hour)
    return Response("ok", status=200)
```
- 無 try-except：若 `notify_users` 拋例外，請求 500 但**無 error log**，難診斷。
- 對照 `crawl_endpoint`（`main.py:127`）已有 try-except + `logger.exception`，notify 應比照。

> 註：本次實測 notify 並未 500（都是正常 `skip`/`Notified`），所以這不是問題三的根因；
> 但補上後，未來任何 notify 例外都會留下 log，是低成本高價值的可觀測性改善。

### 二、解決方案規劃

比照 `crawl_endpoint`，將 `notify_users` 呼叫包進 try-except：
```python
try:
    await notify_users(bot=bot, hour=tw_hour)
    return Response("ok", status=200)
except Exception:
    logger.exception("notify failed")
    return Response("notify failed", status=500)
```
- `notify_users` 內部對「單一使用者推播失敗」已有 try/except（`push.py:_notify_one_user`），
  本層 catch 的是「取 DB / 篩選」等整體失敗。

### 三、驗證

- 單元測試：mock `notify_users` 拋例外，斷言 endpoint 回 500 且有呼叫 `logger.exception`。
- 回歸：142 tests 全綠。

---

## 任務六　【P2】GCP 診斷工具（GCP MCP）評估

調查日期：2026-06-20
狀態：**評估完成，建議短期不導入 GCP MCP**

---

### 一、本次調查的實證經驗

整個任務一～五的生產診斷，**全程只用 `gcloud` CLI + Firestore REST API** 即完成：
- Cloud Run logs：`gcloud run services logs read`（看 notify/crawl 每步）
- Scheduler 設定：`gcloud scheduler jobs describe`
- Firestore 讀取：`gcloud auth print-access-token` + `curl` 打 Firestore REST（讀 events/users collection、統計分佈）

→ 證明**現有工具已足以完成深度診斷**，包含讀任意 collection、統計欄位、跨筆比對。

### 二、唯一摩擦點

- 本機 **Application Default Credentials（ADC）未設定**（`gcloud auth application-default login` 沒做過），
  所以無法直接用 `google-cloud-firestore` SDK；改用「user access token + REST API」繞過，可行但每次要組 curl。

### 三、建議（依成本效益）

1. **短期（建議）**：不導入 GCP MCP。改用兩個零成本作法即可：
   - 執行一次 `gcloud auth application-default login` 設好 ADC → 之後可直接用 repo 既有的 `firestore-client` 寫小段 Python 讀 DB（比 curl 方便）。
   - 或在 repo 加一支唯讀診斷小工具（`scripts/inspect_firestore.py`）封裝常用查詢。
2. **中期（可選）**：若未來診斷頻率高、需即時查 BigQuery logs 或跨多專案，再評估 GCP 官方 MCP server。
3. **不建議**：為目前單一專案、單一服務的規模導入完整 GCP MCP——維運與授權成本大於效益。

### 四、結論

`gcloud` + Firestore REST 已涵蓋本專案所有診斷需求。
最划算的改善是「設定 ADC」或「加一支唯讀查詢腳本」，GCP MCP 列為中期再議。

---

## 全部任務總結（Executive Summary）

| 任務 | 對應 HANDOFF | 根因（實證） | 規劃方案 | HANDOFF 原假設修正 |
|------|------|------|------|------|
| 一 | 問題三 | `臺/台` 不一致 | `_normalize_city` 套用於 extract_city + filter | 推播鏈路其實正常、scheduler 正確 |
| 二 | 問題一 | 圖片取自 biji 通用 og:image；irunner 報名站被 `_SKIP_DOMAINS` 誤殺 | 改抓 official_url og:image＋放行 irunner，覆蓋 90% | 不需 web search |
| 三 | 問題二 | 解析鎖定錯誤 DOM（表格）只取單一 cell | 改從 biji `<select><option>` 取完整組別 | 不需逐站表格解析 |
| 四 | 問題四 | 同任務一（`臺/台`） | 由任務一修復一併解決，免重設 | preferred_city 欄位其實存在且有值 |
| 五 | P1 | notify_endpoint 無 try-except（可觀測性缺口） | 比照 crawl_endpoint 補 try-except | 非問題三根因 |
| 六 | P2 | — | 短期不導入 GCP MCP，建議設 ADC／加唯讀腳本 | — |

**最重要的修正：** HANDOFF 列為「嚴重」的問題三、四、五，實際上：
- 問題五（DB 未更新）為**誤判**——DB 每次 crawl 正常更新 88 筆。
- 問題三、四為**同一個小 bug（臺/台）**，一處正規化即解。
- 真正需要實作的核心只有三件事：①`臺/台` 正規化 ②圖片改抓報名站 og:image＋放行 irunner ③組別改讀 biji select。
