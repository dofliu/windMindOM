# 2026-09-23 — 情境比較分析 A2 Part 4：跨情境差異圖

> Session 類型：實作
> Session 長度：中
> 主導：autonomous worker（cron，v4.1）
> 結果：新增 A2 Part 4 差異圖頁籤，A2（情境比較分析）epic 完整範圍至此全數完成。

---

## 1. Session 目標

WMOM-20260923-06。連續兩個 session（-03、目前）把「差異圖」列為 A2 Part 4、留給下個 session。
本次接手：解決 decision_log DEC-20260923-01 caveat 留下的開放問題——差異圖是否需要後端聚合，
或純前端能處理「多情境序列取樣時間點不完全對齊」的插值/分桶問題。

## 2. 實際完成

### 2.1 主要工作

- **判定不需要後端端點**：與 Part 3（時序疊圖）一致，純前端即可處理。採「分桶重採樣」策略：
  - `frontend/utils/scenarioTimeline.ts` 新增純函式 `medianInterval`（序列相鄰間距中位數）、
    `pickBinMs`（取多個序列中**最粗**的取樣間隔當桶寬，刻意不選最細，避免對粗序列插補出假精度）、
    `binSeries`（分桶取平均、忽略 null）、`buildDiffSeries`（逐桶算 `compare − baseline`，
    只有兩邊該桶都有值才算得出差異，否則該桶為 `null` 缺口，不是 0）。
  - 這 4 個函式皆為純函式，24 個新測試（等間距/奇偶中位數/重複時間點/負 t 分桶/排序/空輸入等
    邊界）直接鎖住數值行為。
- **新增 `frontend/utils/scenarioHistoryFetch.ts`**：把 Part 3（`ScenarioCompareTimelineView`）
  既有的「單情境單機組 raw history 抓取 + 對齊基準計算」邏輯抽成獨立函式 `fetchScenarioHistory`，
  供本次新頁籤重用，避免第三份重複的 fetch 邏輯。**刻意不動** `ScenarioCompareTimelineView.tsx`
  本身的既有寫法（只加了 `export` 讓它的 `POWER_TAG`/`WIND_TAG`/`METRICS`/`HISTORY_LIMIT`
  常數可被新頁籤 import 共用，避免兩份 tag 字串各自維護、日久漂移），降低這次改動觸及已測試過
  程式碼的風險。
- **新增 `frontend/components/ScenarioCompareDiffView.tsx`**：第三個頁籤「差異圖」。
  - Baseline 情境可選（下拉選單，預設第一個選取的情境），其餘情境逐點算「該情境 − baseline」
    疊圖，`y=0` 為參考線（即 baseline 本身）。
  - 選取情境變動、原 baseline 已不在清單內 → 自動回退第一個。
  - 提示文案：fetch 失敗、baseline 本身無資料無法算差異、完全無重疊資料的空狀態。
  - 純 DOM 圖例（同 Part 3 的 jsdom 因應寫法）不含 baseline 本身（它是參考線，不是一條差異線）。
- **`ScenarioCompareAcrossView.tsx`** 加第三個頁籤「差異圖」，與既有「摘要並排」/「時序疊圖」並列。
  至此 DEC-20260720-02 A2 epic 完整範圍（摘要並排＋疊圖＋差異圖）全數完成。

### 2.2 卡住或延後的事

- 無。範圍內完整完工。

### 2.3 重大決策（如有）

- 沿用 `DEC-20260923-01` 既有 caveat 段落判定：差異圖比照時序疊圖，純前端分桶重採樣即可，
  不需要新後端端點。未新增獨立 DEC 條目（判斷屬於既有決策的延伸落地，非新架構翻案）。

## 3. 產出清單

### 新增檔案

- `frontend/utils/scenarioHistoryFetch.ts`
- `frontend/utils/__tests__/scenarioHistoryFetch.test.ts`（8 tests）
- `frontend/components/ScenarioCompareDiffView.tsx`
- `frontend/components/__tests__/ScenarioCompareDiffView.test.tsx`（17 tests）

### 修改檔案

- `frontend/utils/scenarioTimeline.ts`（新增 `medianInterval`/`pickBinMs`/`binSeries`/
  `buildDiffSeries` 純函式）
- `frontend/utils/__tests__/scenarioTimeline.test.ts`（+18 tests）
- `frontend/components/ScenarioCompareTimelineView.tsx`（只加 `export`，無邏輯變動）
- `frontend/components/ScenarioCompareAcrossView.tsx`（掛第三個頁籤）
- `frontend/components/__tests__/ScenarioCompareAcrossView.test.tsx`（+2 tests，差異圖頁籤切換
  + 未傳 savedScenarios 不崩潰/不 fetch）
- `docs/product/decision_log.md`（DEC-20260923-01 Consequences 段落回填「已解決」，nice-to-have）

### 動了狀態的 issue

- WMOM-20260923-06：open → done

### 寫進 decision_log 的決策

- 無新增（沿用 DEC-20260923-01）

## 4. 下次怎麼接手

本次已完整收尾。DEC-20260720-02 A2「情境比較分析」epic 完整範圍（摘要並排 A0/A1/Part1/2 +
時序疊圖 Part3 + 差異圖 Part4）至此全數完成。下次可選：PR C（檢視情境掛載 app，需先寫 broker
子設計）、WMOM-20260716-06（footprint CPU-torch pin，卡 docker daemon）、
WMOM-20260509-F6（PostgreSQL row-lock，同款卡 docker daemon）、M6 部署前置（HTTPS 配置，需先
定部署目標/憑證策略）。詳見 `TODO.md` / `ISSUES.md`。

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 與用戶對話、釐清方向 | 0%（autonomous，無即時對話） |
| 寫程式 / 寫文件 | 55% |
| Code review / 驗證 | 40% |
| 其他（環境安裝等） | 5% |

## 6. 學到的事

- 「刻意不重構已測試過的程式碼、抽共用邏輯到新檔案」這個決策本身沒錯，但抽出後若兩份實作在
  某個分支上有行為分歧（本次是 HTTP 失敗 + 缺 sim_start 的組合），沒有測試會自動抓到——這種
  分歧只能靠 reviewer 逐行比對兩份實作才找得到。下次做類似抽取時，應主動列出「原本每個分支
  組合」逐一對照抽出後是否仍一致，而不是只驗證「常見路徑」。
- 「有資料」與「資料是缺口但看起來像有資料」是兩種完全不同的 bug 類型：`hasAnyDiff` 的
  length>0 誤判、`failedNames`/`baselineHasNoData` 語意重疊，都是「陣列非空≠有意義的資料」
  這個同一類陷阱的不同表現，寫聚合/摘要邏輯時要特別留意「空但存在」的中間狀態。

## 7. Open questions（park）

- 無。

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline：backend `1103 passed, 7 skipped, 1 xfailed`；frontend `npx tsc --noEmit` 0
  error、`npx vitest run` `1171 passed`（56 files）、`npx vite build` OK——皆與 STATUS.yaml 記錄
  的基準一致。
- 本次新增/修改後（含 review 修復）：backend 未動（無 Python 變更，未重跑）；frontend
  `npx tsc --noEmit` 0 error、`npx vitest run` `1171→1216 passed`（56→58 files，+45 新測：
  scenarioTimeline.test.ts 14→32（+18）、scenarioHistoryFetch.test.ts +8（新檔）、
  ScenarioCompareDiffView.test.tsx +17（新檔）、ScenarioCompareAcrossView.test.tsx 13→15（+2））、
  `npx vite build` OK。
- **開發過程中自行抓到並修正 2 個真實 bug（皆 mutation-verified）**：
  1. `hasAnyDiff` 原本只檢查 `diffByScenario[s.id]?.length > 0`，但 `buildDiffSeries` 回傳的是
     兩序列桶集合的**聯集**，即使兩情境完全零重疊，陣列仍非空（全是 `value: null`）——會誤判成
     「有資料」而畫出一條全缺口的線。改成檢查「至少一個桶兩邊都有值」
     （`.some(p => p.value !== null)`）。Mutation-verified：改回舊邏輯 → 「兩情境完全不重疊」
     測試如預期 fail（沒顯示空狀態文案）→ 已還原確認修復。
  2. 元件測試裡 `getByText(情境名稱)` 會同時命中 `<Select>` 的 `<option>` 與純 DOM 圖例的
     `<div>`，造成「多重命中」錯誤——不是 production bug，是測試寫法問題，改為在圖例 div 上
     加 `data-testid="diff-legend-{id}"`，測試改用 `getByTestId` 精準定位。
  - `buildDiffSeries` 的 `compare − baseline` 方向、`pickBinMs` 的「取最大（最粗）而非最小
    （最細）」皆額外做了 mutation testing（分別把運算子/函式呼叫改回相反版本），確認對應
    單元測試會抓到 regression，再還原（`git diff` 最終乾淨）。

## Review

code-reviewer subagent review：**1 must-fix（已修）+ 3 should-fix（全數採納）+ 4 nice-to-have
（3 採納、1 不採納）**。

- **Must-fix（已修）**：`ScenarioCompareDiffView.tsx` 抓了 `usedFallbackAlign`（缺 `sim_start`
  改用自己最早一筆讀數對齊）卻從未讀取、也沒有像 Part 3 那樣顯示提示——差異圖把兩條線相減成
  一個數字，若 baseline 與比較情境剛好一真一假對齊，算出來的差異會是兩個不同時間基準相減、
  看起來精確卻是誤導，且完全沒有提示使用者。已補上 `fallbackNames` banner（沿用 Part 3 文案，
  差異圖情境額外加一句「牽涉這些情境的差異值可能是在比較不同時間基準」），並新增 2 個測試
  （`缺 sim_start 的情境 → 顯示 fallback 對齊提示`、`都有 sim_start → 不顯示`）+ mutation-verified
  （暫時清空 `fallbackNames`/`truncatedNames` 陣列 → 兩個對應測試如預期 fail → 已還原）。
- **Should-fix 1（已修）**：`truncated`（命中 `HISTORY_LIMIT` 截斷）同樣被抓了卻未顯示提示，
  差異線較早段的缺口會被誤讀成「真的沒有重疊」而非「資料未載入」。已補 `truncatedNames` banner
  （同上一併 mutation-verified）。
- **Should-fix 2（已修）**：抽出的 `fetchScenarioHistory` 在 HTTP 非 ok 分支寫死
  `usedFallbackAlign: false`，但原本內嵌於 `ScenarioCompareTimelineView` 的寫法即使 fetch 失敗
  也會走到同一段算 `declaredBase`/`usedFallbackAlign` 的程式碼——兩份邏輯在「fetch 失敗 + 缺
  sim_start」這個組合上已經分歧（且原本測試沒蓋到這個組合）。已改成 `failed` 只影響
  `res.readings` 是否視為空，`usedFallbackAlign`/`baseMs` 一律照 sim_start 邏輯算，與原寫法
  一致；新增/修正 2 個測試鎖住「HTTP 非 ok + 有 sim_start」與「HTTP 非 ok + 缺 sim_start」兩種
  組合，並 mutation-verified（改回舊的短路寫法 → 2 測皆如預期 fail → 已還原）。
- **Should-fix 3（已修）**：`diffByScenario` 的 `useMemo` 省略 `compareScenarios`/`scenarios`
  依賴卻沒有註解說明為何安全，不像本檔其餘 `eslint-disable` 都有解釋——已補一行註解（`id` 查表、
  情境集合變動必經 `scenariosKey` 觸發重新 fetch，省略不會造成資料落後）。
- **Nice-to-have 採納**：
  1. `docs/product/decision_log.md` DEC-20260923-01 的 Consequences 段落原寫「差異圖是否需要
     後端仍待評估」，本次已解決卻沒回填——已補上「已於 WMOM-20260923-06 解決：不需要」的更新。
  2. `binSeries` 測試原本只驗 2 點/桶，補一個 3 點以上/桶的測試，完整鎖住「取平均」而非只驗
     2 點的特例。
  3. baseline 抓取失敗時，原本 `failedNames` 通用提示與新的 `baselineHasNoData` 提示會同時
     顯示（語意重疊、有點吵）——已改成 `failedNames` 排除 baseline 本身，該情況只顯示更具體的
     baseline 專屬提示；新增 2 個測試區分「非 baseline 失敗」vs「baseline 本身失敗」的提示分流，
     並 mutation-verified（改回不排除 baseline → 新測試如預期 fail → 已還原）。
  - **不採納**：`binMs` 在切換指標（`tag`）時會重算，雖然桶寬理論上與指標無關（純看 `t`）——
    reviewer 也判斷這只是多算一次、非 bug，影響有限，本次不動。

## Wrap-up

- STATUS.yaml / ISSUES.md / TODO.md 已同步更新（見下方 commit）。
- 本次沒有引入未受自動化測試保護的邏輯；已知既有限制沿用 Part 3 的說明——recharts 圖表本身
  在 jsdom（無 ResizeObserver）無法驗證實際畫出的線條/像素，只能讀原始碼推論 + 人工瀏覽器驗，
  這點與其餘情境比較頁籤一致，非本次新增的缺口。
