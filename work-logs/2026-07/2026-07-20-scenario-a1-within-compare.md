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

（實作後填）

## 驗證

（實作後填）

## 卡在哪 / 下次怎麼接手

（收尾填；下一步預期 A2 跨情境比較，或 PR C）
