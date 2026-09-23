# 2026-09-23 — WMOM-20260923-03：情境比較分析 · A2 Part 3：跨情境相對時間對齊時序疊圖

## 認領理由

TODO.md「下次接手」與 ISSUES.md WMOM-20260922-04（A2 Part 2 前端）皆點名「A2 完整範圍另一半
（相對時間對齊時序疊圖 + 差異圖）需要新後端端點」，連續兩個 session 因此延後。本 session 重新檢視
資料層，發現**其實不需要新後端端點**：既有單情境端點 `GET /api/scenarios/{id}/turbines/{tid}/history`
（A1 的 `ScenarioTrendView` 已在用）已回傳原始 timestamped 讀數，而每個情境的 `config.sim_start`
早就隨 `SavedScenario`（`GET /api/scenarios` 列表）落在前端記憶體裡——相對時間對齊純粹是「拿現有
兩份資料算差」，可以是純前端功能。因此本次改口：疊圖本身（Part 3）零後端變更即可完成；差異圖
（原 caveat 提到的「多序列時間點不完全對齊的插值/分桶問題」）仍需另外設計，維持延後（Part 4）。

Docker 阻塞的兩項（WMOM-20260716-06 footprint pin、WMOM-20260509-F6 PostgreSQL row-lock）本
session 環境同樣只有 docker client、無 daemon（`docker info` 連線 `/var/run/docker.sock` 失敗），
確認仍卡；HTTPS 部署配置需先定部署目標/憑證策略，非 autonomous 可決。故依決策樹挑選本項。

## Preflight

- backend baseline：`1103 passed, 7 skipped, 1 xfailed`（與 STATUS.yaml 記錄一致，全程未變動任何
  backend 檔案）。
- frontend baseline：`npx tsc --noEmit` 0 error；`npx vitest run` `1067 passed`（51 files）；
  `npx vite build` OK。
- Stack-aware 檢查（GitHub MCP 可用）：`list_pull_requests(state=open)` 回傳空陣列，無殘留 PR；
  `git fetch origin main` 後本地分支與 `origin/main` 同步（無需 merge）。
- 分支：環境注入的 `claude/inspiring-mccarthy-jgxo72`。
- ⚠ 環境備註：這次 `npm ci` 第一次以背景執行時失敗（`EUSAGE`：偵測 lockfile 有問題），前景重跑
  立刻成功——懷疑是背景執行時的暫態 I/O 問題，非本次程式碼相關；供下次若遇到同款錯誤時參考「先
  重跑一次」。

## 範圍

**只做疊圖（Part 3），不做差異圖（Part 4，留給下個 session）**——比照 A0→A1→A2 Part1→Part2 一路
拆小任務的既有節奏。

## Implement

零後端變更，純前端：

- **`utils/scenarioTimeline.ts`（新檔）**：純函式 `simStartMs`（ISO → epoch ms，容錯缺值/壞資料）、
  `buildTimelinePoints`（後端 DESC 讀數 → 相對某 `baseMs` 的經過毫秒數序列，ASC）、`formatElapsed`
  （相對時間刻度格式：`3h15m` / 滿一天後 `1d02h`）。
- **`components/ScenarioCompareTimelineView.tsx`（新檔）**：新頁籤元件。
  - 機組 + 指標（發電量/風速）選擇器；抓資料只依 `[情境選取, 機組]`，**切換指標不重新 fetch**
    （改用 `useMemo` 從已抓到的原始讀數衍生序列——沿用同一批資料換算不同欄位，避免每次切指標都
    重打後端）。
  - 每個情境各自呼叫既有 `GET /api/scenarios/{id}/turbines/{tid}/history?limit=12000`（限制值
    比照 `ScenarioTrendView` 的 `HISTORY_LIMIT`），對齊基準優先用該情境 `config.sim_start`；缺值
    （未回填的舊情境）才退而求其次改用該情境自己最早一筆讀數，並顯示明確提示（見下）。
  - recharts `<Line>` 各自帶自己的 `data`（recharts 3.x `DataProvider` 介面原生支援每個
    graphical item 覆寫 chart 層級的 `data`，見 `node_modules/recharts/types/cartesian/Line.d.ts`）
    疊在同一張 `LineChart` 上，x 軸為 `type="number" dataKey="t"`。
  - **純 DOM 圖例**（色塊 + 情境名稱），刻意不只靠 recharts 內建 `<Legend>`——後者在 jsdom（無
    ResizeObserver）測試環境下因 `ResponsiveContainer` 量到 0×0 而不渲染內容，只能讀原始碼推論；
    純 DOM 版本讓「哪個顏色對應哪個情境」在瀏覽器與測試環境都同樣可驗證，也比 5 個情境擠在同一個
    SVG legend 更好讀。
  - 兩種提示 banner：**缺 `sim_start` 改用 fallback 對齊**（明講「並非真正的情境開始後經過時間」，
    避免視覺上誤導成兩情境已對齊）；**命中 12000 筆上限截斷**（比照 `ScenarioTrendView` 既有慣例）。
- **`components/ScenarioCompareAcrossView.tsx`**：加頁籤列（「摘要並排」/「時序疊圖」，預設摘要並排，
  A2 Part 1/2 既有內容原封不動只是包進 `tab === 'summary'` 條件）；新增 optional prop
  `savedScenarios`（預設 `[]`，向後相容——只影響新頁籤，摘要並排頁籤不受影響）；`labelFor` 沿用
  已抓到的 `/compare` 摘要做命名查表，兩頁籤同一情境同一名稱。
- **`components/ScenarioPage.tsx`**：多傳 `savedScenarios={savedScenarios}`（頁面已持有的「過去
  情境」清單，`GET /api/scenarios` 抓回來的完整物件，含 `config.sim_start`/`turbine_count`）——
  零額外 fetch，純把既有記憶體資料接線過去。

## Verify

- **手動 mutation-verified 4 個關鍵邏輯分支**（逐一改 production、跑對應測試確認 fail、再還原，
  `git diff` 對 production 檔案最終乾淨）：
  1. `buildTimelinePoints` 拿掉 DESC→ASC 的 `.reverse()` → `scenarioTimeline.test.ts` 對應測試 fail
  2. `formatElapsed` 的 `days > 0` 改 `days >= 0`（永遠顯示天數）→ 3 個邊界測試 fail
  3. 疊圖抓資料的 `useEffect` deps 加回 `tag`（回退成「切指標也重新 fetch」的舊行為）→
     「切換指標不重新 fetch」測試從預期 2 次呼叫變 4 次，fail
  4. `ScenarioCompareAcrossView` 預設頁籤從 `'summary'` 改 `'timeline'` → 13 測中 11 測 fail
     （證實預設頁籤是多數既有斷言的前提，非空談）
- **Full baseline（review 前）**：backend 未動，重跑仍 `1103 passed, 7 skipped, 1 xfailed`；
  frontend `npx tsc --noEmit` 0 error；`npx vitest run` `1067→1098 passed`（51→53 files，+31 新測：
  `scenarioTimeline.test.ts` 14 + `ScenarioCompareTimelineView.test.tsx` 11 +
  `ScenarioCompareAcrossView.test.tsx` +5（頁籤切換）+ `ScenarioPage.test.tsx` +1（端到端接線，
  用刻意一有一無 `sim_start` 的真實 fixture 驗 fallback 對齊路徑））；`npx vite build` OK。
- **Full baseline（review 後修復完）**：frontend `npx vitest run` `1098→1100 passed`（+2，
  should-fix #2 的載入失敗測試）；`npx tsc --noEmit` 0 error；`npx vite build` OK；backend 全程
  未動。

## Review

code-reviewer subagent 獨立跑（含自己讀 recharts 原始碼、自己動手對 3 個關鍵分支做 mutation
testing、cross-check 後端 `/compare` 與 `/history` 端點確認未被本次改動）：

**verdict：Needs revision → 已全部處理後視為 Approve**

- 🔴 **1 must-fix（已修）**：`DEC-20260720-02` 原文寫 A2「後端對齊端點 + 前端」，本 session 判定
  時序疊圖不需要後端端點，屬於「動到架構/改變方向」卻沒寫進 `docs/product/decision_log.md`
  （CLAUDE.md §6.3 硬性規定）。修法：新增 `DEC-20260923-01` 完整記錄探勘結論/決策/rationale/
  consequences，並在 `DEC-20260720-02` 該行加註「⚠️ superseded」指回新條目，避免後續 session
  被舊文字誤導成疊圖仍要等後端端點。
- 🟡 **should-fix #1（已處理，非程式碼 bug，是已知限制）**：reviewer 讀了實際安裝的 recharts
  原始碼（非只讀 `.d.ts`）確認 per-`<Line data={...}>` 覆寫本身正確、畫線與 X 軸 domain 計算都對——
  但發現一個獨立的 tooltip 問題：recharts 用**精確數值比對**（`findEntryInArray`，非「找最近的
  點」）在游標位置找每條線的對應值，若情境取樣間隔不同，游標可能只命中部分情境的資料點。這是
  recharts 既有行為特性，非本次程式碼的 bug，也非目前工具可測（jsdom 無法驗證真實 hover）。已在
  `ScenarioCompareTimelineView.tsx` 加程式碼註解解釋成因（引用 `findEntryInArray`），並在 UI 頁尾
  提示文字補一句對使用者的說明，避免誤讀成「資料缺漏」或「畫錯了」。差異圖（Part 4）若要做逐點
  相減，需要先解決同一個「取樣點不對齊」問題（見 decision_log 新條目 Consequences）。
- 🟡 **should-fix #2（已修 + 補測試 + mutation-verified）**：單一情境 fetch 失敗（HTTP 非 2xx /
  例外）原本被靜默壓成跟「情境本來就沒資料」同一種結果，使用者看到的只是那條線安靜消失，容易誤讀。
  修法：`RawScenarioData` 新增 `failed: boolean`，兩個失敗路徑（`.then` 非 ok 分支、`.catch` 例外
  分支）都設 `failed: true`，UI 新增第三種 banner（「載入失敗，可能是暫時性問題，稍後再試」，用
  `C.warn` 顏色跟另外兩種（琥珀色）的「非阻塞提醒」區分開）。新增 2 測（非 ok 分支 / 例外分支各一）
  + 「都成功不顯示提示」的負向測試；**各自 mutation-verified**（把兩個失敗分支的 `failed` 逐一改回
  `false`，確認對應測試 fail，再還原，`git diff` 對 production 檔案最終乾淨）。
- 🟢 **3 個 nice-to-have（部分採納）**：
  1. 跨頁籤配色索引理論上可能因「情境在 `savedScenarios` 查無資料被跳過」而不一致——目前 wiring
     保證不可達（`ScenarioPage` 傳的 `savedScenarios` 恆是 `ids` 的來源清單），純屬防禦性建議，
     **本次不動**，留待兩個 prop 資料來源真的解耦時再處理。
  2. `formatElapsed` 負值夾到 0 但畫點 `t` 本身不夾範圍，可能造成刻度標籤與點位些微不一致——影響
     範圍是 sub-second/sub-minute 誤差等級，**本次不動**。
  3. tab 切換造成 `ScenarioCompareTimelineView` unmount/remount、來回切換會重複 fetch，無 cache——
     **本次不動**，情境數上限 5、非高頻操作，留待日後有效能疑慮時再處理。
  4. **docstring 歸屬小誤植（已修）**：「找不到對應 metadata 的情境會被跳過」這句原本寫在
     `ScenarioCompareTimelineView.tsx` 的 Props 註解，但實際過濾邏輯在呼叫端
     `ScenarioCompareAcrossView.tsx` 的 `timelineScenarios`——已把註解移到正確的檔案/位置。

reviewer 對我原本提出的 5 個 open question 逐一回覆確認：recharts per-Line data 用法正確（讀了
原始碼，非猜測）；fallback 對齊邏輯健全、banner 文案已足夠清楚；`tag` 從 fetch effect deps 移除
無 stale closure/race condition 風險（`ctrl` 每次 effect 重跑都是新的、閉包正確捕捉，reviewer 自己
mutation test 過會被抓到）；測試非 tautological（3 個關鍵分支獨立 mutation-verified 全部抓到）；
scope 收斂到 Part 3/Part 4 合理，`buildTimelinePoints` 是 Part 4 可直接復用的地基。

## 誠實回報：沒有自動化保護的部分

- **實際 recharts 疊圖渲染**（多條 `<Line>` 各自 `data` 覆寫是否真的在瀏覽器正確疊圖、圖例色塊與
  線條顏色是否視覺一致）：jsdom 無 `ResizeObserver`，`ResponsiveContainer` 在測試環境量到 0×0，
  圖表本身不會真的畫出來——這點只驗證了「資料/props 有沒有正確傳進 `<Line>`」與「不會拋例外」，
  真實視覺渲染需人工瀏覽器驗證（本 session 未做）。reviewer 有讀 recharts 原始碼佐證邏輯正確，
  但仍未經真實瀏覽器 hover/render 驗證。
- **跨情境取樣間隔不同時的 tooltip 精確度**（should-fix #1）：已知限制，非本次修正範圍——已加
  程式碼註解 + UI 提示文字說明成因，未實作重採樣修正（見 decision_log DEC-20260923-01
  Consequences，留給 Part 4 一併評估）。
- **相對時間對齊的「視覺正確性」**（例如兩情境的線是否在圖上真的以「經過時間」而非「絕對時間」
  對齊、x 軸刻度是否好讀）同樣只驗證了換算數學（`buildTimelinePoints`/`formatElapsed` 純函式測試），
  未經人工瀏覽器檢視實際圖表。
- **fallback 對齊語意**（缺 `sim_start` 的舊情境改用自己最早一筆讀數對齊）已用單元測試鎖住「確實
  有觸發 fallback + 有顯示提示」，banner 文案明講「並非真正的情境開始後經過時間」；reviewer 確認
  邏輯與文案皆健全。

## Wrap-up

- `docs/product/decision_log.md`：新增 `DEC-20260923-01`（記錄「A2 疊圖不需後端端點」的決策翻案）；
  `DEC-20260720-02` 該行加註 superseded 指回新條目。
- ISSUES.md：新增 WMOM-20260923-03 done 條目；stats `done 109→110`、`total 120→121`。
- STATUS.yaml：`issue_stats.done` 109→110；`last_updated` 追加本 session 摘要；
  `next_milestone` 更新「下次接手」為 A2 Part 4（差異圖）。
- TODO.md：更新「最後更新」摘要，補上「A2 Part 3（疊圖）已做，Part 4（差異圖）留待下次」。
- 分支：`claude/inspiring-mccarthy-jgxo72`；code commit 已 push（含 review 後的 must-fix/
  should-fix 追加 commit）；PR 待開（見下）。

**下次接手**：A2 Part 4（差異圖）——需要先解決「多情境序列時間點不完全對齊」的插值/分桶問題
（例如以固定相對時間間隔重新取樣後再逐點相減），本次 Part 3 的 `buildTimelinePoints` 已提供對齊後
的序列可直接重用/延伸；或轉向 PR C（檢視情境掛載 app，需先寫 broker 子設計，仍卡）。M6 critical
path 的 docker 阻塞兩項（footprint pin / PostgreSQL row-lock）與 HTTPS 部署配置仍待部署環境/
劉老師決策，非本次可解。
