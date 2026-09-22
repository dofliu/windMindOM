# 2026-09-22（session #7）— 情境比較分析 A2 Part 2 前端：跨情境摘要比較 UI（WMOM-20260922-04）

> Session 類型：實作（單一 issue，純前端）
> Session 長度：中
> 主導：Claude（autonomous worker）
> 結果：消費前一 session（#5，WMOM-20260922-03）已完成但當時無前端呼叫方的
> `GET /api/scenarios/compare` 後端端點，新增「過去情境」清單多選（2–5 個）+「比較所選」→
> 新頁 `ScenarioCompareAcrossView`（風場層 rollup 並排：headline 卡片 → 指標選擇 → 長條圖 →
> 全指標並排表）。與 A1（`ScenarioCompareView`，同情境內跨機組）對稱。開發過程中自行抓到並修正
> 2 個真實 bug（見下）。code-reviewer subagent review：0 Must-fix / 0 Should-fix / 3
> Nice-to-have（皆非阻塞），Approve。backend 未動、1103 passed 不變；frontend 961→978 passed
> （+17 新測）、tsc 0、build OK。CI runner 基礎設施持續觀察中（見 §4）。

---

## 1. Session 目標

依 §4 決策樹開工：

1. **baseline regression**：無（backend 1103 passed / 7 skipped / 1 xfailed；frontend 961
   passed / tsc 0 / build OK，與 STATUS.yaml 記錄的基準完全吻合）。
2. **CI 飛輪狀態**：查 `mcp__github__list_pull_requests`（open）→ 空，代表前一 session
   （#5/#6）開的 PR #162（WMOM-20260922-03）與 #163（追蹤檔更正）皆已合併。查最近 5 個
   `ci.yml` run（`actions_list list_workflow_runs`）→ **全部 `conclusion: success`**，其中
   #162/#163 兩個 run 都拿到真實 `runner_id`、`auto-merge.yml` 全自動 squash-merge——CI
   runner 基礎設施看起來已穩定恢復（TODO.md 稍早的警語建議「連續 2-3 個 session 都綠燈再刪除
   舊警語」，本次是恢復後第 2-3 筆樣本，見下方 §4 決定先不刪、留給下一輪再觀察一次確認）。
3. **docker daemon**：仍不可用（`docker info` 連得到 client、daemon socket 不存在）——
   `WMOM-20260716-06`（footprint）、`WMOM-20260509-F6`（PostgreSQL row-lock）本次仍無法接。
4. 依決策樹「情境比較分析 epic 剩餘」：讀 `docs/product/decision_log.md` DEC-20260720-02，
   A2 完整範圍 = 「後端對齊端點 + 前端摘要並排/雷達 + 相對時間對齊時序疊圖 + 差異圖」。前一
   session 只做了純後端「摘要並排」（Part 1），**明確標註「本端點目前無前端呼叫方」**——這是一個
   已經測好、契約穩定、但完全沒有消費方的後端地基，前端消費它（摘要並排 UI）是設計無歧義、範圍
   可獨立驗收的下一步，不需要碰後端也不需要發明新的資料對齊演算法（相對時間對齊時序疊圖才需要
   新後端端點，那個仍留給未來 session，見 §5）。認領為本次工作，比照既有編號序列命名
   `WMOM-20260922-04`。

---

## 2. 實際完成

### 2.1 設計

讀 A1（`ScenarioCompareView.tsx` + `ScenarioDetail.tsx` 頁籤機制）確立既有慣例：Card/Btn/
指標選擇 tab 按鈕/長條圖/明細表的視覺與互動模式。A2 跨情境比較的比較單位定為**風場層 rollup**
（`ScenarioSummary.farm`），而非個別機組——不同情境的機組組成/數量可能不同，逐機組比較沒有意義，
這點在 `utils/scenarioCompare.ts` 新函式的頭部註解說明。

配色：5 個情境上限（`MAX_COMPARE_SCENARIOS=5`，比照後端同名常數）與既有 `Palette` 型別裡本就為
區分圖表類別而設的 5 個 hex token（`chartFault`/`chartWind`/`chartOperator`/`chartState`/
`chartGrid`）數量恰好相同，直接複用、不新增顏色，符合 CLAUDE.md §7「不寫 hex」慣例。依情境在
陣列中的 index 指派顏色，指標切換時同一情境顏色不變，方便來回比對。

### 2.2 新增

- `frontend/utils/scenarioCompare.ts`：新增 `FarmCompareMetricKey`、`scenarioLabel`、
  `farmMetricValue`、`scenarioCompareBars` 純函式（風場層版本的既有機組層 `compareBars` 等）。
- `frontend/components/ScenarioCompareAcrossView.tsx`（新檔）：headline 卡片（依配色標記）→
  指標選擇（6 個風場層指標：平均容量因數/總發電量/平均生產佔比/總故障事件/最嚴重損傷/最短剩餘
  壽命）→ 跨情境長條圖 → 全指標並排表。fetch `/api/scenarios/compare?ids=...`，`AbortController`
  防呆比照 A1。
- `frontend/components/ScenarioPage.tsx`：「過去情境」清單每列加勾選 checkbox（`auto` grid
  欄位）+ 清單上方「比較所選（N）」按鈕（未達下限 2 時 disabled；達上限 5 時未勾選項目
  disabled，已勾選的仍可取消）+ `comparingIds` 狀態渲染新頁面。

### 2.3 開發過程中自行抓到並修正的 2 個 bug（皆已測試鎖住 + mutation-verified）

1. **全指標並排表格式化錯誤**：初版 `fmtCell` 誤用「目前選中指標」的格式化函式（`activeMetric.
   fmt`）去格式化並排表**每一列**（每個 metric 各自的值），導致例如「總發電量」列在選中「平均
   容量因數」時被當成百分比格式化（實測跑出 `700000.0 %`，正確應為 `7,000 kWh`）。寫
   `ScenarioCompareAcrossView.test.tsx` 的「全指標並排表顯示每個情境的欄位值」測試時自己先抓到
   （測試本身在修正前就 fail，不是回頭補的）。修法：`fmtCell(v, m)` 改吃該列自己的 `MetricDef`，
   不再依賴外層 `activeMetric` closure。Mutation-verified：改回舊邏輯 → 測試如預期 fail → 已還原。
2. **刪除已勾選情境未同步清除勾選**：`deleteScenario` 成功後只從 `savedScenarios` 移除，未從
   `selectedForCompare` 移除——若使用者勾了某情境後把它刪除，該 id 會殘留在勾選 Set 裡；後續按
   「比較所選」送出的 `/compare?ids=...` 會包含這個已不存在的 id，後端 `_load_scenario_summary`
   對任一 id 404 就讓整個 `asyncio.gather` 連帶失敗（非部分成功），使用者會看到整批比較請求失敗
   且無從得知原因。修法：`deleteScenario` 成功時一併把該 id 從 `selectedForCompare` 移除。新增
   回歸測試「刪除已勾選的情境 → 自動移除其勾選」（用 3 筆情境確保刪除後清單仍 ≥2 筆、工具列仍
   顯示，才能真正驗證「勾選數變 1」而非被「工具列因情境數不足而整個消失」蓋過去）。
   Mutation-verified：拿掉這段清除邏輯 → 測試如預期 fail（按鈕誤判仍可比較）→ 已還原。

### 2.4 回歸測試

- `utils/__tests__/scenarioCompare.test.ts`：+3（`scenarioLabel` 命名回退、
  `farmMetricValue`/`scenarioCompareBars` 缺值處理與順序保留）。
- `components/__tests__/ScenarioCompareAcrossView.test.tsx`（新檔）：+8（mount 抓取、headline
  卡片、未命名回退、指標切換、並排表數值、缺值顯示 `—`、載入失敗、onBack）。
- `components/__tests__/ScenarioPage.test.tsx`：+6（工具列顯示門檻、勾選啟用/停用按鈕、取消勾選、
  上限防呆、刪除同步清除勾選回歸）。

共 +17 新測（961→978），所有新增/修改的邏輯分支皆 mutation-verified（見 §2.3 兩處，以及 MIN/MAX
disable 邏輯也各自驗證過改回舊邏輯會 fail）。

### 2.5 Code review（`code-reviewer` subagent，Phase 6）

0 Must-fix、0 Should-fix，3 Nice-to-have（皆非阻塞，未採納，理由如下）：

1. `palette`（5 色陣列）與 `MAX_COMPARE_SCENARIOS`（=5）之間沒有型別/執行期斷言綁定這個耦合
   假設——目前程式碼註解已明確記下該假設，非隱藏地雷，優先度低，未加執行期 assert。
2. `ScenarioPage.tsx` 本地既有的 `scenarioLabel`（故障場景 id → 顯示名稱）與本次
   `utils/scenarioCompare.ts` 新增的 `scenarioLabel`（情境摘要 → 顯示名稱）同名但語意不同、無
   實際 import 衝突——純命名可讀性問題，重新命名屬於觸碰既有程式碼的範圍外改動，未做。
3. 測試邊界小缺口（「所有情境同一指標皆缺值」「eventsByTimeWindow 提示文字實際渲染」未逐一斷言）
   ——reviewer 確認底層邏輯已正確處理這兩種情況，只是沒有測試鎖定，判斷不影響本次驗收，未補。

reviewer 額外指出一個環境現象：review 期間兩次 Read 同一份 `ScenarioPage.tsx` 內容不同（mtime
在其間變動）——這是本 session 在其 review 執行期間持續編輯同一檔案（正常開發流程，非背景異常
process），reviewer 已重新讀取最新內容並基於此下結論，不影響 review 有效性。

### 2.6 卡住或延後的事

無阻擋項。A2 完整範圍的另一半（相對時間對齊時序疊圖 + 差異圖）刻意不在本次範圍，留給未來 session
（見 §5）。

### 2.7 重大決策（如有）

無架構級新決策，執行既有 DEC-20260720-02 epic 拆解裡「A2 前端摘要並排」這一塊。

### 2.8 流程插曲：一度誤 checkout 到 main

開工初期為了 `git pull origin main` 取最新程式碼，`git checkout main` 之後忘記切回本 session
的注入分支 `claude/inspiring-mccarthy-9fqwp9`，在 `main` 分支上做完全部實作與測試。收尾要
commit 時發現這個問題（`git branch --show-current` 顯示 `main`），因為 `claude/inspiring-
mccarthy-9fqwp9` 當時與 `origin/main` 指向同一個 commit（前一 session 的改動已全部合併），
`git checkout claude/inspiring-mccarthy-9fqwp9` 安全地帶走所有未 commit 的工作目錄變更，未
造成任何資料遺失或衝突。**已改到正確分支後才 commit**，main 分支本身**未曾**被直接 commit
（CLAUDE.md §12「不要在 master/main 直接做 risky 工作」得以維持）。提醒未來 session：
`git pull` 後若需要 checkout main 才能拿到最新內容，記得動作完就切回注入分支，或直接
`git fetch origin main && git merge origin/main`（不切分支）更安全。

---

## 3. 產出清單

### 修改檔案

- `frontend/utils/scenarioCompare.ts` — 新增 A2 跨情境比較純函式
- `frontend/utils/__tests__/scenarioCompare.test.ts` — 對應新測試（+3）
- `frontend/components/ScenarioCompareAcrossView.tsx` — 新元件（新檔）
- `frontend/components/__tests__/ScenarioCompareAcrossView.test.tsx` — 新測試（新檔，+8）
- `frontend/components/ScenarioPage.tsx` — 勾選 UI + 比較按鈕 + 刪除同步清除勾選修正
- `frontend/components/__tests__/ScenarioPage.test.tsx` — 對應新測試（+6）

### 動了狀態的 issue

- WMOM-20260922-04：新開直接收（open → done）

### 寫進 decision_log 的決策

- 無（執行既有 DEC-20260720-02 epic 拆解，非新決策）

---

## 4. CI runner 基礎設施狀態

透過 GitHub MCP 查詢最近 5 個 `ci.yml` run：**全部 `conclusion: success`**，含前一 session
（#5/#6）開的 PR #162（WMOM-20260922-03）與 #163（追蹤檔更正）——兩者皆拿到真實 `runner_id`、
`auto-merge.yml` 全自動 squash-merge 進 main + 刪分支，無人工介入痕跡。這是 TODO.md 記錄的
「疑似恢復」後第 2-3 筆連續綠燈樣本。本次沿用 TODO.md 既有建議（連續 2-3 個 session 都綠燈再
整段刪除舊警語），**先不刪除舊警語**，正常開 PR 交給飛輪處理，若本次 PR 也順利 auto-merge，
建議下一個 session 可以把 TODO.md 的舊警語（`<details>` 區塊）整段清除、視為問題已解。

---

## 5. 下次怎麼接手

1. **確認本次 PR 是否 auto-merge 成功**：若成功，累積 3 個連續綠燈樣本，建議清除 TODO.md 的
   CI 失效舊警語（`<details>` 摺疊區塊）。
2. **A2 Part 2 剩餘範圍**：相對時間對齊的時序疊圖 + 差異圖。需要：
   - 後端新端點（例如 `GET /api/scenarios/compare/timeseries?ids=...&turbine_id=...`），對每個
     情境用各自的 `sim_start` 算相對時間 `t − sim_start`，回傳可疊圖的時序資料。**注意**：
     `downsampling` 表非 session-safe（`GROUP BY` 不含 `session_id`，見 `storage.py` 註解），
     長情境（duration 上限 8760h）走 raw table 全表掃描可能是分鐘級（`_load_scenario_summary`
     docstring 已提過同款效能顧慮）——設計時需一併考慮 downsampling/分頁策略，這是本次故意留給
     未來 session 的主要設計工作。
   - 前端新元件（可能命名 `ScenarioCompareTimelineView.tsx`）+ 疊圖/差異圖 UI。
3. **PR C**（檢視情境掛載 app，需先寫 broker 子設計，DEC-20260720-01 最重的一塊）——仍卡，
   需要專門一個 session 先做設計而非直接實作。
4. **持續卡住**：`WMOM-20260716-06`（footprint CPU-torch pin）、`WMOM-20260509-F6`
   （PostgreSQL row-lock）——本 sandbox 仍只有 docker client、無 daemon。

---

## 6. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| Preflight（stack-aware 檢查、CI 狀態確認、docker 排除、選題） | 15% |
| 讀 A1 既有模式 + 後端 `/compare` 契約確認 + 設計 | 15% |
| 寫新元件 + 純函式 + ScenarioPage 整合 | 25% |
| 寫測試（含開發中抓到 2 個真實 bug 並修正） | 25% |
| Code review + 分流 nice-to-have | 10% |
| 全套 baseline 驗證 + 分支插曲處理 + work-log 收尾 | 10% |

---

## 7. 學到的事

- **後端端點合併但無前端消費方，是刻意的、有價值的中間狀態**——A0/A2 Part1 都採這個模式（先把
  後端做穩、測好，前端消費留給下一個 session），讓每個 session 的範圍可以獨立驗收、不必為了
  「完整功能」硬塞進單一 session。判斷「這是不是下一步該做的事」的訊號很簡單：契約穩定
  （已測試、已合併）+ 消費方明確缺席 + 消費邏輯本身無設計歧義（有現成的 A1 模式可比照）。
- **在同一批「比較表格」程式碼裡，同時處理「目前選中的單一指標」（給圖表用）與「逐一列出所有
  指標」（給並排表用）時，很容易不小心讓兩者共用同一個格式化 closure**——這正是本次踩到的 bug
  根因。以後寫這種雙重用途的比較 UI，圖表 tooltip 用 `activeMetric.fmt` 沒問題（tooltip 本來就
  只對應當前選中指標），但任何「列出多個指標」的迴圈都必須明確傳入該列自己的 `MetricDef`，不能
  依賴外層 state 的 closure——寫測試斷言「表格裡每一列的實際數值」（而非只斷言「表格存在」）是
  抓到這類 bug 最直接的方式。
- **多選 UI 的勾選狀態如果跟另一個會被刪減的清單分開存放（`selectedForCompare: Set<number>`
  vs `savedScenarios: SavedScenario[]`），刪除操作必須記得同步清理孤兒的選取狀態**——這類 bug
  在功能剛做出來時很容易被忽略（因為刪除流程與勾選流程是兩條獨立寫的程式碼路徑，各自看起來都
  正確），只有想著「使用者可能會用什麼順序操作」才會發現。以後寫任何「勾選一個外部 id 清單的
  子集合」功能，都該問一句：「這個外部清單如果有項目被移除，勾選狀態會不會殘留孤兒？」
