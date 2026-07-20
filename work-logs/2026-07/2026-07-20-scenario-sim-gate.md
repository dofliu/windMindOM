# 2026-07-20 — 情境頁「未起模擬就生成」guided activation｜WMOM-20260720-02

> Session 類型：#142 合併後接續的 UX follow-up（使用者實測回報 #2）
> 產出：本 PR（ScenarioPage 偵測來源、非 simulation 時停用生成 + 一鍵啟動提示）
> 對應 issue：WMOM-20260720-02（承接 WMOM-20260720-01 使用者回報 #2）

---

## 使用者回報（#2）

> 「我還沒選擇風場，直接開始產生新的情境。好像因為沒有選擇風場，就無法啟用。」
> 「不過我選擇某個風場後，就可以開始產生。」

## 根因（#142 session 已定位）

與「有沒有選風場」無關。使用者從**「調閱過去情境」**進來 → `select_view_only()` 把
`simulator=None`（view 只讀 storage、不起模擬）。此時到情境頁按「生成」→ `generate-bulk` 命中
`if not b.simulator: raise 400 "Simulator not running"` → 前端顯示「生成失敗：Simulator not
running」＝使用者說的「無法啟用」。後來「選某個風場」→ `switch_farm()` → `start()` →
`_start_simulator()` **順帶起了 live 迴圈** → 才能生成——**但那條 live 迴圈正是害 #4 撞 db-lock 的路**。

## approach（使用者已選）

「**一鍵啟動提示**」（vs 後端按生成自動起模擬）：符合 WMOM-20260719-04 開機 gate 的「不自動起來源、
由使用者明確選」哲學，也不會意外中斷 live 連線。

## 做了什麼（純前端 ScenarioPage）

1. **偵測來源種類**：mount 時 GET `/api/source/status` → `sourceKind`（undefined＝載入中／null／
   simulation／view／live）。
2. **生成 gate**：`canGenerate` 加 `simActive = sourceKind === 'simulation'`——非 simulation 時
   「生成情境」停用（不再讓使用者按了才吃 400）。
3. **一鍵啟動提示**：`sourceKind` 已載入且非 simulation 時，顯示明確提示（含目前來源標籤）+
   「啟動模擬以生成」按鈕 → POST `/api/source/select {mode:simulation}` → 成功即
   `sourceKind='simulation'` + 重載風場（`activate_simulation` 會 `ensure_default_farm`）→ 提示消失、
   生成啟用。失敗給明確錯誤。

## 驗證

- **tsc --noEmit** 全綠（先跑 tsc 再寫測試 fixture，守 #139 教訓）。
- **vitest**：ScenarioPage **39** passed（35 既有 + 4 新）；全前端 **925** passed。
  既有 `installFetch` mock 補 `/api/source/status`（預設回 simulation，讓既有生成流程測試不破）+
  `/api/source/select`。
- **mutation 驗證**：拿掉 `&& simActive` gate → 「來源為 view → 生成停用」測試轉紅（非假綠）。
- **vite build** 成功。

## 卡在哪 / 下次怎麼接手

- 本 PR：draft + `hold` 待 code-review → 收 review → 移除 hold → 自動合。
- 後續可考慮：view 模式下隱藏註定 400 的 nav（Faults/Settings）——本 PR 未含（範疇外）。
