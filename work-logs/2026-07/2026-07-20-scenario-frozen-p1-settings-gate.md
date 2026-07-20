# 2026-07-20 — 情境=凍結資料集 PR A：設定依實際來源 gate｜WMOM-20260720-06

> Session 類型：使用者定案「情境模式語意」後的第一個實作增量（DEC-20260720-01）
> 產出：本 PR（設定頁風況/電網/機組區塊依 `/api/source/status` gate）＋ DEC-20260720-01
> 對應 issue：WMOM-20260720-06（DEC-20260720-01 的 PR A）

---

## 背景

使用者定案（回「go」）把「情境」收斂為**凍結資料集**（DEC-20260720-01）：產生完不自由跑、進入
情境整個 app 掛上去操作、**設定依實際來源 gate**。本 PR 是最低風險、可獨立合併的第一步（PR A）。

## 做了什麼（純前端 SettingsPage）

- mount 時 GET `/api/source/status` → `sourceKind`（SourceMode 型別）。
- `liveTuningBlocked = sourceKind === 'view' || sourceKind === 'live'`——**fail-open**：載入中
  (undefined) / 查不到 (null) 不擋（不因狀態查詢失敗就把即時模擬使用者的控制藏掉）。
- **風況控制 / 電網控制 / 風機規格**（三個會即時 POST `/api/config/*` 去改「正在跑的模擬」的區塊）
  在 `liveTuningBlocked` 時以一則說明取代：「即時調整只在『即時模擬』來源下生效；情境風況於生成時
  就固定」。**模擬參數**（存檔用、非即時 POST）不受 gate。

## 驗證

- **tsc --noEmit** 全綠。
- **vitest**：SettingsPage **21** passed（#145 的 18 + 3 新 gate 測試）；全前端 **933** passed。
  既有 `defaultFetch` mock 補 `/api/source/status`（預設 simulation，既有 SIMULATION 測試維持有效）。
- **mutation 自驗**：把 `liveTuningBlocked` 寫死 false → 「來源為 view → 隱藏風況控制」測試轉紅（非假綠）。
- **vite build** 成功。含 fail-open 測試（source/status 查詢失敗仍顯示控制）。

## 分支基底（重要）

本 PR **stack 在 #145 之上**（#145「設定頁跳頂 remount 修」尚未合併，若基於其前的 main 會把
remount bug 帶回來）。故基於 `claude/wmom-20260720-05-settings-scroll-jump`。**掛 `hold` 直到
#145 合併**再移除，確保合併順序（#145 先、#06 後）。`git diff origin/main...HEAD` 會同時含 #145
的 remount 修（已於 #145 review 過）＋本 PR 的 gate。

## 後續（DEC-20260720-01 其餘增量）

- **PR B**：產生情境不自由跑（後端 activate/來源狀態機 + 生成後導向檢視該情境）。
- **PR C**：檢視情境把整個 app 掛上去（broker 情境檢視來源；最大、需子設計）。
- **PR D**：GuidedTourPage 同款 inline-component remount 修 + 可選 lint 規則。
