# 2026-09-22（session #4）— PR D：GuidedTourPage inline component remount 修（WMOM-20260922-02）

> Session 類型：實作（小型，單 issue）
> Session 長度：短
> 主導：Claude（autonomous worker）
> 結果：DEC-20260720-01 拆的 PR D 殘留項——`GuidedTourPage.tsx` 5 個純展示子元件提升到 module
> scope，解決同日已在 `ScenarioTrendView` 修過的同一類 inline-component remount 問題；新增 DOM
> node identity 回歸測試，mutation-verified；code-reviewer subagent review 0 Must-fix/Should-fix、
> 5 Nice-to-have（Approve），採納 1 項（註解引用格式）；backend 未動（1094 不變）、frontend
> 960→961 passed、tsc 0、build OK。**同 session 也確認 CI runner 基礎設施仍持續失效**（非本次可解），
> 順帶發現並更正 main 上 ISSUES.md/STATUS.yaml 的統計數字內部矛盾（PR #159 已診斷、尚未合併）。

---

## 1. Session 目標

依 §4 決策樹開工，preflight 發現：

1. **Stack-aware 檢查**：`WMOM-20260720-04/-08`（live/OPC 硬化，PR #156）、`WMOM-20260720-13`
   （A1 round-2，PR #157）、`WMOM-20260922-01`（accelerated stop 響應性，PR #158）皆已由劉老師
   人工合併進 main（CI runner 基礎設施自今日起持續失效，auto-merge 飛輪停擺，詳見下方 §4）。
   唯一 open PR（**#159**，追蹤檔案數字更正，純文件）本機已驗證但因同款 CI 失效卡住；其標的問題
   是「PR #157/#158 各自對 ISSUES.md/STATUS.yaml 同一行做不同理由的 +1，git 合併時被靜默合成一
   次」的文件記帳問題，非程式碼，且是前一個 session 開的、非本 session 產出，依 stack-aware 準則
   不重複處理，留給劉老師或下個 session 決定何時合併。
2. **Docker daemon 仍不可用**（`docker info` 連得到 client 但 daemon socket 不存在），
   `WMOM-20260716-06`（footprint）與 `WMOM-20260509-F6`（PostgreSQL row-lock）本次仍無法接。
3. 讀 `docs/product/decision_log.md` DEC-20260720-01（情境模式收斂為凍結資料集）：其「拆成小 PR」
   清單列了 **PR D（獨立小修）**——`GuidedTourPage` 同款 inline-component remount（客戶展示頁，
   #145 review 發現）——`ISSUES.md` WMOM-20260720-07 條目下也重申「後續：PR C（最大、需子設計）；
   PR D `GuidedTourPage` 同款 remount 修」。PR D 獨立於需要子設計的 PR C，範圍明確、無設計歧義，
   且與 A1（`ScenarioTrendView`，PR #157）修的正是同一類問題（今日已有現成先例可比照）——依 §4
   決策樹「情境比較分析 epic 剩餘」項下最小阻力的候選，認領為本次工作（`WMOM-20260922-02`，
   當日尚未用過 -02 編號）。

---

## 2. 實際完成

### 2.1 診斷

讀 `frontend/components/tour/GuidedTourPage.tsx`（407 行）：`Eyebrow`、`ModChip`、`Beat`、
`Story`、`Row` 五個純展示用子元件皆以 `const X: React.FC<...> = (...) => (...)` 定義在
`GuidedTourPage` 函式體內（僅 `Split` 本就在 module scope，未受影響）。這是典型 React
「unstable nested component」反模式：函式體內定義的 component，每次外層 render 都會產生新的
函式參考（新 component type），React reconciliation 比對到型別不同就會把整棵子樹 unmount 再
mount——不只是切換情境步驟時如此，**任何**讓 `GuidedTourPage` 重新 render 的觸發（包含跟 `step`
完全無關的操作，例如 App 全域的主題切換——`GuidedTourPage` 本身呼叫 `useTheme()` 訂閱了
ThemeContext）都會觸發。展示頁若有過渡動畫/焦點狀態會被平白重置，且每次都要重建整批 DOM node，
不必要地浪費效能。與今日稍早 `WMOM-20260720-13`（PR #157）修的 `ScenarioTrendView` 是同一類
問題（該次修法是把 state 提升到不會被卸載的父層；本次修法是把元件本身提升出去）。

### 2.2 修正

把 `Eyebrow`、`ModChip`、`Beat`、`Story`、`Row` 提升到 module scope（`Split` 旁邊），維持跨
render 穩定的 component identity：

- 原本透過 closure 拿到的 `C`（theme palette）：提升後的元件改各自呼叫 `useTheme()`
  （安全——`GuidedTourPage` 恆在 `<ThemeProvider>` 內渲染，context 隨處可讀）。
- 原本透過 closure 拿到的 `ui`（翻譯器，依賴 `lang` prop）：`Beat` 改接收顯式 `lang: Lang`
  prop，內部重建局部 `ui` helper（`(en, zh) => lang === 'zh' ? zh : en`）算出 NOW/WITH/WIN
  標籤；`Story` 同樣接收 `lang` 並轉傳給內部的 `Beat`。`Eyebrow`/`ModChip`/`Row` 不需要
  `lang`（內容都是呼叫端已翻譯好的字串/節點）。
- `stage()` switch 的 5 個 case（case 1–5）呼叫 `<Story .../>` 處皆補上 `lang={lang}`。

### 2.3 回歸測試 + mutation 驗證

`GuidedTourPage.test.tsx` 新增一測：額外掛一顆會呼叫 `useTheme().toggle()` 的按鈕（不碰
`step` state），點「開始導覽」進到情境一後，點該按鈕切換主題，斷言 `Story`/`Eyebrow` 子樹內
情境一 kicker 文字節點「情境一 · 監控總覽」在切換前後是**同一個 DOM node 物件**（`toBe` /
`Object.is`）——代表 React 是就地 reconcile（只更新 style 屬性）而非整棵拆掉重建。

**mutation 驗證**：`git stash push` 把 `GuidedTourPage.tsx` 還原成修正前版本（子元件搬回函式體
內），保留新測試 → 如預期 fail（`AssertionError`：切換前後拿到兩個不同的 DOM node 物件，
`style` 屬性值也不同，證實真的整棵重繪）；`git stash pop` 還原修正後 6 測全過。

### 2.4 Code review（`code-reviewer` subagent，Phase 6）

跑 diff review，聚焦：5 處各自呼叫 `useTheme()` 有無時序/一致性問題、`lang` prop 是否完整串接
無漏傳、測試斷言方式（DOM node 物件相等）是否可靠不脆弱、檔案內有無其他同類未修的 nested
component、CLAUDE.md §7 慣例。

**結果：0 Must-fix、0 Should-fix、5 Nice-to-have，Approve。** reviewer 獨立重跑
`tsc --noEmit`（0 error）+ 該測試檔（6/6 passed）、grep 確認全部 5 處 `<Story .../>` 呼叫點都補
了 `lang={lang}`、grep 確認檔案內已無殘留的函式體內 `React.FC` 定義、確認 `stage()` 是普通函式
（以 `stage()` 呼叫而非當 JSX component 用，非同類風險）。5 個 Nice-to-have：

1. 🟢 本次提升元件的註解引用了不存在的 ID「WMOM-20260720-DEC」，應引用實際的
   `DEC-20260720-01`——**已採納**，改為 `DEC-20260720-01 PR D，見 docs/product/decision_log.md:591`。
2. 🟢 decision log 提過的 `react/no-unstable-nested-components` lint guardrail 未加——repo 目前
   **完全沒有 ESLint 設定**（無 `.eslintrc*`、無 eslint devDependency），新增整套 lint 工具鏈
   屬引入新基礎設施，超出本次單一 bug-fix 範圍，未做（DEC-20260720-01 本身也只列為「可選」）。
3. 🟢 `ui()` 翻譯器在 `Beat` 與 `GuidedTourPage` 各自重複定義一次——1 行純函式、僅 2 處使用，
   reviewer 自己也判斷不值得為此抽共用 util，未動。
4. 🟢 新提升的元件沒有比照既有 `Split` 的一行 JSDoc 風格加註解——選擇性 polish，未做以避免多餘
   diff noise。
5. 🟢 測試只驗了 `Story`/`Eyebrow` 這一條子樹、未逐一測 `Beat`/`Row`——reviewer 判斷屬合理選擇
   （機制是「`GuidedTourPage` render 輸出引用到的所有 JSX element type 都會被重定義」，測一個
   代表性子樹已足夠證明，逐一測每個元件是過度覆蓋），未加測。

僅採納 #1（零風險、改善可追溯性），其餘 4 項依 reviewer 自身判斷與本次「小型單一 bug-fix」範圍，
留待未來有需要再另開 issue。採納後重跑 `tsc --noEmit`（0 error）+ 該測試檔（6/6 passed）確認。

### 2.5 卡住或延後的事

無阻擋項。

### 2.6 重大決策（如有）

無架構級決策，純 bug-fix，執行 DEC-20260720-01 已拍板的 PR D。

### 2.7 附帶處理：main 上追蹤檔案的統計數字內部矛盾（非本次程式碼範圍，但影響本次收尾算式）

開工時讀 main 現況 `ISSUES.md`：`open:11 / in_progress:0 / blocked:0 / done:103`，但宣告的
`total (active): 115`——`11+0+0+103=114 ≠ 115`，內部矛盾。查 PR #159（前一 session 已開、尚未
合併）的說明，其診斷為：PR #157（WMOM-20260720-13）與 PR #158（WMOM-20260922-01）各自因不同
理由把同一行從 `102` 改成 `103`，git 合併時視為「同一筆文字變更」只計一次，實際應為 `104`
（`11+0+0+104=115` 才與宣告的 total 相符）。

本次收尾在此**已修正的基準（done=104）**上再 +1（本次新增的 WMOM-20260922-02）→
`done=105`、`total=116`，而非直接對 main 文字上的 `103` 做 +1（那樣會延續同一個內部矛盾）。
`STATUS.yaml` 的 `issue_stats.in_progress` 同步發現落後（仍寫 1，`ISSUES.md` 已是 0）一併更正為
0。**PR #159 若先合併，下個 session 開工請務必重新核對 `open+in_progress+blocked+done==total`**
——這是今天第二次出現同款數字碰撞風險，追蹤檔案的數字欄位在多 session 並行時是高風險區。

---

## 3. 產出清單

### 修改檔案

- `frontend/components/tour/GuidedTourPage.tsx` — `Eyebrow`/`ModChip`/`Beat`/`Story`/`Row`
  提升到 module scope；5 處 `<Story .../>` 呼叫點補 `lang={lang}`
- `frontend/components/tour/__tests__/GuidedTourPage.test.tsx` — 新增
  `ThemeToggleHarness` + 1 個 DOM node identity 回歸測試（mutation-verified）
- `ISSUES.md` — 新增 WMOM-20260922-02 done 條目；統計表 done 103→105（含吸收 PR #159 的
  +1 更正）、total 115→116；頂部「最後更新」blurb 更新
- `STATUS.yaml` — `issue_stats`（in_progress 1→0、done 103→105）、`last_updated`、
  `next_milestone` 同步更新
- `TODO.md` — CI 警語更新為完整版本（飛輪停擺、人工合併說明）、最後更新時間、baseline 數字
  （frontend 957→961）

### 動了狀態的 issue

- WMOM-20260922-02：新開直接收（open → done）

### 寫進 decision_log 的決策

- 無（執行既有 DEC-20260720-01 PR D，非新決策）

---

## 4. CI runner 基礎設施狀態（延續前 3 個 session 的記錄，本次僅確認未變）

透過 GitHub MCP 查詢 `dofliu/windMindOM` 當日 workflow run 歷史（`actions_list` /
`pull_request_read get_check_runs`），確認：

- 2026-09-22 當日**每一個** `ci.yml` run（含 PR #157 / #158 / #159、以及跟 PR 無關的 main push
  run）`conclusion` 皆為 `failure`，2-8 秒內完成、`runner_id` 未被排到、check output 全空。
- `auto-merge.yml` 的每一次觸發 run 皆為 `skipped`（其邏輯要 CI 綠才會動），證實飛輪確實停擺。
- PR #157（`merged_by: dofliu`）與 PR #158（`merged_by: dofliu`）皆為**劉老師人工合併**，非
  auto-merge——本 session 據此判斷：manual merge 是劉老師本人在收到前一 session 的 push
  notification 後主動執行的動作，**不是 autonomous session 該自行代勞的權限**，故本 session
  沒有嘗試合併任何 PR（含已完全驗證、零風險的純文件 PR #159），僅正常開新 PR 交給劉老師處理。
- 本次未重跑 CI（前面已有 3 個 session 的重跑記錄，診斷內容未變，遵照 babysit 慣例不重複重跑
  或重複診斷），也未再新留 PR 留言（同款診斷已存在於 PR #157/#158 留言）。

**未再發送 push notification**：這是同一個已知問題的第 4 次確認，劉老師已在稍早收到過通知並
主動處理（人工合併 #157/#158），本次沒有新資訊值得再次打擾。

---

## 5. 下次怎麼接手

1. **最優先確認**：CI runner 基礎設施是否恢復（直接查最近一次 `ci.yml` run 的 `conclusion`，
   不要用「PR 有沒有被合併」反推——前一 session 已記錄過這個誤判陷阱）。若仍失效，正常做完整
   本機驗證後開 PR，但預期需人工合併。
2. **待合併**：**PR #159**（追蹤檔案數字更正，純文件，零風險）與本次的 PR（WMOM-20260922-02）
   若同時待合併，**合併後請務必重新核對 `ISSUES.md`/`STATUS.yaml` 的
   `open+in_progress+blocked+done==total`**——本次已在 PR 描述與 work-log 記錄詳細算式，供合併後
   核對用。
3. **次要**：續 **A2 跨情境比較**（相對時間對齊）或 **PR C**（檢視情境掛載 app，需先寫 broker
   子設計，DEC-20260720-01 中最重的一塊）——DEC-20260720-02 情境比較分析 epic 剩餘項目。
4. **第三**：`WMOM-20260716-06`（footprint CPU-torch pin）或 `WMOM-20260509-F6`（PostgreSQL
   row-lock），兩者仍卡在本 sandbox 只有 docker client、無 daemon（`docker info` 連不到
   `/var/run/docker.sock`）。
5. **不建議自行接**：M6-4 殘餘的「HTTPS 部署配置」雖標 🔵，但 repo 內沒有 `deploys/` 目錄或任何
   既有 nginx/certbot/docker-compose TLS 骨架可依循，且與需要客戶現場資訊的 M6-1（部署目標網域、
   憑證策略）高度相關——標 🔵 可能過於樂觀，貿然自行決定部署拓樸風險較高，建議留給劉老師先定調
   部署目標後再拆成明確子任務。
6. **阻擋項**：CI runner 基礎設施（見 §4），非 autonomous session 可解，已充分記錄待人工處理。

---

## 6. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| Preflight（stack-aware 檢查、CI 狀態確認、docker 可用性排除、選題） | 20% |
| 讀 decision_log + 定位 GuidedTourPage 問題根因 | 15% |
| 寫修正（5 元件提升 + lang 串接） | 15% |
| 寫新測 + mutation 驗證 | 15% |
| Code review + 採納 nice-to-have | 10% |
| 追蹤檔案數字核對與更正（含吸收 PR #159 的診斷） | 15% |
| 全套 baseline 驗證 + work-log 收尾 | 10% |

---

## 7. 學到的事

- **`useTheme()` 這類 context hook 讓「這個元件會不會因為跟它看似無關的狀態改變而重新 render」
  變得不直覺**：`GuidedTourPage` 只讀 `step`（本地 state）與 `lang`（prop），直覺上「主題切換」
  跟這個頁面無關；但因為它呼叫了 `useTheme()`，任何主題變動都會讓它整個函式體重新執行。這正是
  本次 bug 能被寫成回歸測試的關鍵——不用等到真的有人在展示時切主題才會發現，任何會讓元件重新
  render 的觸發都能拿來當 mutation-verifiable 的測試手段（比只測「切換步驟」更能鎖住「元件定義
  是否穩定」這個真正的不變量）。
- **DOM node 物件相等（`toBe`/`Object.is`）是測「有沒有被整個 unmount/remount」最直接可靠的
  斷言方式**——不需要 spy render 次數或掛 `useEffect` cleanup 計數器，React Testing Library
  回傳的就是真實 DOM node 參考，重新掛載必然產生新物件。
- **追蹤檔案的數字欄位一旦在同一天被多個 session 各自 +1，內部矛盾（`sum ≠ declared total`）本身
  就是很好的自我檢查訊號**——本次開工時光是心算 `11+0+0+103` 就發現跟宣告的 115 對不上，不需要
  等到 diff review 才抓到。以後每次改動這幾個統計數字，養成順手心算一次 sum 的習慣，比事後靠
  另一個 session 來對帳更早攔截問題。
