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
- `frontend/utils/__tests__/scenarioHistoryFetch.test.ts`（7 tests）
- `frontend/components/ScenarioCompareDiffView.tsx`
- `frontend/components/__tests__/ScenarioCompareDiffView.test.tsx`（13 tests）

### 修改檔案

- `frontend/utils/scenarioTimeline.ts`（新增 `medianInterval`/`pickBinMs`/`binSeries`/
  `buildDiffSeries` 純函式）
- `frontend/utils/__tests__/scenarioTimeline.test.ts`（+24 tests）
- `frontend/components/ScenarioCompareTimelineView.tsx`（只加 `export`，無邏輯變動）
- `frontend/components/ScenarioCompareAcrossView.tsx`（掛第三個頁籤）
- `frontend/components/__tests__/ScenarioCompareAcrossView.test.tsx`（+2 tests，差異圖頁籤切換
  + 未傳 savedScenarios 不崩潰/不 fetch）

### 動了狀態的 issue

- WMOM-20260923-06：open → in_progress（code-reviewer review 進行中，待收尾後標 done）

### 寫進 decision_log 的決策

- 無新增（沿用 DEC-20260923-01）

## 4. 下次怎麼接手

本次應可完整收尾（單 session）。若因故中斷，下次接手看本檔 §7 或本檔是否已補上 Verify/Review/
Wrap-up 段落判斷是否完工。

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 與用戶對話、釐清方向 | 0%（autonomous，無即時對話） |
| 寫程式 / 寫文件 | 55% |
| Code review / 驗證 | 40% |
| 其他（環境安裝等） | 5% |

## 6. 學到的事

- （待 Review/Wrap-up 段落補完後回填）

## 7. Open questions（park）

- （待 Review 完成後視 finding 補充）

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline：backend `1103 passed, 7 skipped, 1 xfailed`；frontend `npx tsc --noEmit` 0
  error、`npx vitest run` `1171 passed`（56 files）、`npx vite build` OK——皆與 STATUS.yaml 記錄
  的基準一致。
- 本次新增/修改後：backend 未動（無 Python 變更，未重跑）；frontend `npx tsc --noEmit` 0 error、
  `npx vitest run` `1171→1210 passed`（56→58 files，+39 新測：scenarioTimeline.test.ts +24、
  scenarioHistoryFetch.test.ts +7 新檔、ScenarioCompareDiffView.test.tsx +13 新檔、
  ScenarioCompareAcrossView.test.tsx +2）、`npx vite build` OK。
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

code-reviewer subagent review 進行中（背景執行），本檔將在收到結果後更新此段落（must-fix 全數
處理 + should-fix 逐項決議）。

## Wrap-up

（待 Review 完成後補齊：STATUS.yaml / ISSUES.md / TODO.md 更新、issue 狀態改 done、最終
commit + push + PR。）
