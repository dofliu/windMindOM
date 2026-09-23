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
- **Full baseline**：backend 未動，重跑仍 `1103 passed, 7 skipped, 1 xfailed`；frontend
  `npx tsc --noEmit` 0 error；`npx vitest run` `1067→1098 passed`（51→53 files，+31 新測：
  `scenarioTimeline.test.ts` 14 + `ScenarioCompareTimelineView.test.tsx` 11 +
  `ScenarioCompareAcrossView.test.tsx` +5（頁籤切換）+ `ScenarioPage.test.tsx` +1（端到端接線，
  用刻意一有一無 `sim_start` 的真實 fixture 驗 fallback 對齊路徑））；`npx vite build` OK。

## Review

code-reviewer subagent（獨立跑，含自己動手 mutation testing）：**結果待補**——review 於 wrap-up
撰寫當下仍在背景執行，本節與下方 Verify 結論將於 review 完成後於同一 PR 內以追加 commit 補齊
（若有 must-fix）或直接在此段落記錄「0 must-fix / should-fix 清單」。

## 誠實回報：沒有自動化保護的部分

- **實際 recharts 疊圖渲染**（多條 `<Line>` 各自 `data` 覆寫是否真的在瀏覽器正確疊圖、圖例色塊與
  線條顏色是否視覺一致）：jsdom 無 `ResizeObserver`，`ResponsiveContainer` 在測試環境量到 0×0，
  圖表本身不會真的畫出來——這點只驗證了「資料/props 有沒有正確傳進 `<Line>`」與「不會拋例外」，
  真實視覺渲染需人工瀏覽器驗證（本 session 未做，屬已知限制，非本次新增）。
- **相對時間對齊的「視覺正確性」**（例如兩情境的線是否在圖上真的以「經過時間」而非「絕對時間」
  對齊、x 軸刻度是否好讀）同樣只驗證了換算數學（`buildTimelinePoints`/`formatElapsed` 純函式測試），
  未經人工瀏覽器檢視實際圖表。
- **fallback 對齊語意**（缺 `sim_start` 的舊情境改用自己最早一筆讀數對齊）目前只用單元測試鎖住
  「確實有觸發 fallback + 有顯示提示」，未評估這個 UX 決策本身對使用者是否夠清楚——已在 banner
  文案明講「並非真正的情境開始後經過時間」，但若使用者忽略提示文字直接看圖，仍可能誤讀成「兩情境
  已對齊」。

## Wrap-up

- ISSUES.md：新增 WMOM-20260923-03 done 條目；stats `done 109→110`、`total 120→121`。
- STATUS.yaml：`issue_stats.done` 109→110；`last_updated` 追加本 session 摘要；
  `next_milestone` 更新「下次接手」為 A2 Part 4（差異圖）。
- TODO.md：更新「最後更新」摘要，補上「A2 Part 3（疊圖）已做，Part 4（差異圖）留待下次」。
- 分支：`claude/inspiring-mccarthy-jgxo72`；commit 待 review 完成後一併 push + 開 PR。

**下次接手**：A2 Part 4（差異圖）——需要先解決「多情境序列時間點不完全對齊」的插值/分桶問題
（例如以固定相對時間間隔重新取樣後再逐點相減），本次 Part 3 的 `buildTimelinePoints` 已提供對齊後
的序列可直接重用/延伸；或轉向 PR C（檢視情境掛載 app，需先寫 broker 子設計，仍卡）。M6 critical
path 的 docker 阻塞兩項（footprint pin / PostgreSQL row-lock）與 HTTPS 部署配置仍待部署環境/
劉老師決策，非本次可解。
