# 架構排查與討論：擺脫 biji 單點依賴 ＋ SPA 圖片的免費解法

> 日期：2026-06-20｜所有結論均以「即時抓取實證」為依據，非推測。
> 這是**討論文件**，不是已定案的實作。

---

## 一、排查結論：目前是「單一來源」架構，biji 倒就全崩

整個專案只有**一個資料入口**：

```python
# src/scraper/running_biji.py:22
BASE_URL = "https://running.biji.co/?q=competition"
```

依賴分兩層，兩層都綁死 biji：

| 層級 | 現況 | 依賴 |
|------|------|------|
| **發現層**（有哪些活動？） | `fetch_events(BASE_URL)` 只爬 biji 列表 | 100% biji |
| **詳情層**（圖／報名連結／組別） | `_do_fetch_biji_detail(event.url)` 爬 biji 詳情頁 | 100% biji |

**風險證實**：biji（運動筆記）若關站、改版、封爬蟲，**發現層直接歸零、整個服務崩塌**。這正是你擔心的單點依賴。

---

## 二、技術線 A：SPA 圖片，有「免費且零容器負擔」的最新解法

### 為什麼 focusline 抓不到圖
focusline、lohasnet 首頁是 **Vite 打包的 SPA**：server 回傳的只是 3.4KB 的 JS 殼，圖片由瀏覽器跑 JS 後才出現。`requests` 永遠看不到。

### 三個方案比較（已實測佐證）

| 方案 | 免費？ | 我原本擔心的問題 | 結論 |
|------|--------|------------------|------|
| **A1. Cloud Run 內裝 Chromium** | 運算在免費額度內，但映像 +700MB | 容器變重、冷啟動慢、易 OOM | 可行但笨重 |
| **A2. Cloudflare Browser Rendering REST API** | **每天 10 分鐘 render 免費** | **Cloud Run 完全不用裝瀏覽器** | ⭐ 最佳 |
| **A3. 逆向各 SPA 的 JSON API** | 免費 | 每站不同、JS bundle hash 會變 | 脆弱、不可維護，否決 |

**A2 是關鍵發現**：把「跑瀏覽器渲染」外包給 Cloudflare 的免費 REST API（每日 10 分鐘額度）。我們一天只爬一次、只需渲染少數 SPA 活動，10 分鐘綽綽有餘。

→ 這個方案**同時消除我先前所有顧慮**：Cloud Run 容器維持輕量（不裝 Chromium）、不升記憶體、不會 OOM、冷啟動不變慢、GCP 不增費用。SPA 的圖改打 Cloudflare API 拿截圖或 og:image。

來源：[Cloudflare Browser Rendering](https://www.cloudflare.com/products/browser-rendering/)、[Browser Rendering Limits](https://developers.cloudflare.com/browser-run/limits/)

> 註：Cloudflare 免費 render 需註冊 Cloudflare 帳號（免費）並建一個 Worker/API token。非 GCP 服務，但同樣零成本。

---

## 三、架構線 B：去單點化 —— 各報名平台「本身」就能當資料來源

### 實測：主流報名平台 server-side 可爬性

| 平台 | 首頁可爬 | 活動列表 | 活動詳情頁 | 能否當「發現層」來源 |
|------|---------|---------|-----------|-------------------|
| **bao-ming.com**（報名網） | ✓ 285KB | **242 個 `/eb/content/<id>` 活動** | ✓ 可爬、有 og:image | ✅ 強 |
| **ctrun.com.tw**（中華路跑） | ✓ 715KB | **122 個 `Activity?EventMain_ID=<id>`** | ✓ 可爬、og:image=banner | ✅ 強 |
| **lohasnet.tw**（樂活報名網） | ✗ 首頁 SPA | （需查列表頁） | ✓ 詳情頁可爬、og:image=banner | ◐ 詳情可用 |
| **focusline.com.tw** | ✗ SPA | ✗ | ✗ 需 render | 需方案 A2 |
| **irunner.biji.co** | — | — | ✓ | ⚠️ 屬 biji 體系，要降低依賴 |

**重點**：bao-ming（242 活動）和 ctrun（122 活動）各自就是一個**完整、可獨立爬取**的活動聚合站。它們可以直接當作 biji 以外的發現層來源。

### 一個必須誠實面對的權衡

biji 的價值正是「**它聚合了全台幾乎所有路跑活動**」。bao-ming / ctrun / lohasnet 各自只涵蓋「在自家平台報名的活動」，是**部分子集**。

→ 所以務實目標不是「立刻拔掉 biji」，而是「**去單點化**」：讓 biji 從「唯一來源」降級為「來源之一」，再把 bao-ming、ctrun 等平台加進來。即使 biji 哪天倒了，服務仍有其他來源撐著，只是覆蓋率下降而非歸零。

---

## 四、建議的目標架構：多來源 Adapter ＋ 官方站直連 enrich

```
                 ┌─ BijiSource     (running.biji.co 列表)
  發現層         ├─ BaoMingSource  (bao-ming.com 列表)      每個 source 各自產出
 (多來源並行) ──┼─ CtrunSource    (ctrun.com.tw 列表)      統一的 RaceEvent
                 └─ (未來可加 lohasnet…)
                        │
                        ▼
              去重合併（key = 活動名正規化 + race_date）
                        │
                        ▼
  詳情層        enrich：圖／報名連結／組別「直接從官方站」抓
 (不綁 biji)     ├─ 一般站：官方站 og:image（requests）
                 └─ SPA 站：Cloudflare Browser Rendering（方案 A2）
                        │
                        ▼
                   Firestore
```

設計要點：
1. **`Source` 抽象介面**：每個平台一個 adapter，各自實作 `fetch_events() -> list[RaceEvent]`。新增/移除來源只是加減一個 adapter。
2. **biji 降為來源之一**：不刪，但不再是唯一命脈。
3. **enrich 直連官方站**：就算某活動是「透過 biji 發現」的，它的圖／報名連結也**直接抓官方站**（你早就要的），不依賴 biji 詳情頁。
4. **去重**：跨來源同一活動用「名稱正規化＋比賽日期」合併。

這個架構同時解掉三件事：去單點依賴、SPA 圖片、enrich 不綁 biji。

---

## 五、漸進式落地路線（每步可獨立驗證、TDD）

| 階段 | 內容 | 風險 |
|------|------|------|
| **P0（已完成）** | 修好 `official_url` 抽取，按鈕/圖片直連官方站 | 低，已驗證 |
| **P1** | 抽出 `Source` 介面，把現有 biji 邏輯包成 `BijiSource`（純重構，行為不變） | 低 |
| **P2** | 新增 `BaoMingSource` + `CtrunSource`，多來源去重合併 | 中 |
| **P3** | 接 Cloudflare Browser Rendering，補 SPA 站圖片 | 中（需 Cloudflare 帳號） |
| **P4（選配）** | 評估是否把 biji 權重再降，或完全移除 | 視 P2 覆蓋率而定 |

---

## 六、需要你拍板的決策

1. **覆蓋率 vs 純淨度**：要「biji 降為來源之一」（務實、覆蓋率最高），還是「完全不要 biji」（純淨但覆蓋率會掉，需爬更多平台補足）？我建議前者。
2. **SPA 圖片**：採方案 **A2（Cloudflare，免費零負擔）**？需要你願意開一個免費 Cloudflare 帳號。若不想，SPA 活動的圖就先留預設。
3. **落地節奏**：要我先做 **P1（純重構抽 Source 介面，零行為改變）**，還是直接連 P2（加 bao-ming/ctrun 來源）一起？
4. **commit**：第二節提到的 P0 修復（已驗證、164 測試過）要先 commit 嗎？

> 我的整體建議：先 commit P0 → 做 P1 重構 → 再評估 P2/P3。這樣每一步都小、可回溯、不會一次大改炸掉。
