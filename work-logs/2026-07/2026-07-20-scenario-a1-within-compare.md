# 2026-07-20 — 情境比較分析 A1：同情境內比較｜WMOM-20260720-10

> Session 類型：DEC-20260720-02 的 A1（承 A0 #148 merged）
> 產出：單一情境內「不同機組 / 有故障 vs 健康機組」的比較視圖（消費 A0 summary 端點）
> 對應 issue：WMOM-20260720-10

---

## 背景

DEC-20260720-02 情境比較分析 epic：B ✅ → A0 ✅（summary 端點）→ **A1 同情境內比較** → A2 跨情境。
A0 的 `GET /api/scenarios/{id}/summary` 已回每台機組 + 風場層物理摘要，A1 是**消費該端點的前端比較
視圖**：在單一情境內比較不同機組，凸顯「有故障 vs 健康機組」的差異（使用者願景 level 1-2）。

## 計畫（A1 scope）

- 前端比較視圖（放 ScenarioDetail 內新頁籤 / 新元件，待 explore 確認）：
  - 每台機組跨指標比較（容量因數 / 能量 / 最嚴重損傷 / RUL / 故障數 / 生產佔比）——比較圖表。
  - **faulted vs healthy 分群/著色**：由 summary `turbines[].faultEvents > 0`（或 config fault_schedule）判別。
  - 風場層 headline（總能量 / 平均容量因數 / 最嚴重機組 / 最小 RUL 機組）。
- 純函式（判別 faulted、排序、min/max 標記）抽出便於測試；mutation-verified。
- summary 端點型別對接（對齊後端 ScenarioSummary，camelCase）。
- 附帶：折入 A0 round-2 遺留的小 fix（`storage.count_scenario_fault_events` docstring 補 `Args:`）。

## 做了什麼

> 註：#149 只合了 skeleton（work-log + issue）；本實作於新分支 `claude/wmom-20260720-11-a1-compare-view`
> off main，收斂後才開 PR（避免又只合到骨架）。

**純邏輯（`frontend/utils/scenarioCompare.ts`）** — 鏡射後端 `ScenarioSummary`（camelCase，不轉換）+ 純函式：
- `faultedTurbineIds(fault_schedule)`：由情境**注入排程**取 faulted 機組集合（session 隔離、可靠；**非**用
  summary `faultEvents`——後者走時間窗、`eventsByTimeWindow` 可能混入重疊情境）。
- `classifyTurbines`：每台機組標 `faulted` + `scheduledNotTriggered`（排定但 faultEvents===0，有價值提示）。
- `groupMeans`（A1 核心）：faulted vs healthy 兩群某指標平均，量化「有故障 vs 健康的差異」；缺值不計入。
- `compareBars`（缺值→0 + missing 旗標）、`faultedHealthyCounts`、`metricValue`。

**比較視圖（`frontend/components/ScenarioCompareView.tsx`）** — mount 抓 `/api/scenarios/{id}/summary`
（`authFetch` + AbortController）→ 風場層 headline（總能量/平均容量因數/最嚴重損傷機組/最短 RUL 機組/
faulted·healthy 計數）→ 指標選擇（容量因數/發電量/生產佔比/最嚴重損傷/剩餘壽命/故障事件）→ **有故障/健康
分群平均對照** → 跨機組 recharts BarChart（faulted=warn / healthy=accent，`Cell` 逐條著色；缺值半透明）→
每台機組明細表（faulted 標 pill）。eventsByTimeWindow 時附時間窗提示。載入/失敗/空狀態齊備。

**整合**：`ScenarioDetail` 加頁籤列「趨勢｜機組比較」，趨勢維持原單機視圖、比較掛 `ScenarioCompareView`
（拿現成 `scenario` prop，含 `fault_schedule`，零額外接線）。

**附帶**：折入 A0 round-2 遺留 — `storage.count_scenario_fault_events` docstring 補 `Args:`（§7）。

## 驗證

- 純函式 **+7**（`utils/__tests__/scenarioCompare.test.ts`）：faulted 判別/去重/空防護、classify、compareBars
  缺值、groupMeans（含某群全缺/無成員→None）、counts。`classifyTurbines` faulted 判定 mutation（`false &&`）
  → 前端 5 測（含 component 的 faulted pill 斷言）轉紅。
- 元件 **+7**（`components/__tests__/ScenarioCompareView.test.tsx`）：mount 抓 summary、風場 headline、
  **faulted 由 fault_schedule 判定**（WT002 有 pill、WT001 無）、分群平均對照、指標切換 aria-pressed、
  時間窗提示、非 ok → 錯誤狀態。ScenarioDetail 既有 7 測不受頁籤整合影響。
- 前端 941→**955** passed、tsc/build 綠；backend 情境測 23 passed、ruff 綠（docstring 無邏輯變更）。

## 卡在哪 / 下次怎麼接手

- 本實作分支收斂 → 開 PR（draft + `hold`）→ code-review → 移除 `hold` → 合。
- 下一步 **A2 跨情境比較**（不同風況情境間比較同/不同機組，需相對時間對齊）——可在本 A1 的比較 UI 骨架
  之上擴充；或 PR C（檢視情境把 app 掛上去，需先寫 broker 子設計）。
