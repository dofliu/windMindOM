# 2026-07-20 — #143 review Must-fix：live 一鍵切走加二次確認｜WMOM-20260720-03

> Session 類型：#143 合併後 code review Must-fix follow-up（PR 已合併，故走新 PR）
> 產出：本 PR（ScenarioPage 對 live 來源的一鍵啟動加 confirm-guard + 收 review should-fix）
> 對應 issue：WMOM-20260720-03（承接 WMOM-20260720-02 / PR #143）

---

## 背景

#143（WMOM-20260720-02）加了「情境頁未起模擬 → 一鍵啟動模擬以生成」。PR 已由劉老師手動合併，
**合併後** code review 才回，抓到一個真實 Must-fix（＋數個 should-fix）。因 #143 已合併，走新 PR 修。

## Must-fix（review）

「啟動模擬以生成」按鈕對**任何**非 simulation 來源都顯示——**包含 `live`（實接現場 SCADA）**。
點下去直接 `POST /api/source/select {mode:simulation}` → 後端 `switch_mode()` 內 `stop()` 掉現場連線，
**無二次確認**；且 App 只在 `sourceActive===false` 時顯示選源頁 → 一旦 active 就**無 UI 入口切回 live**。
對「第一個客戶 Z72 運維廠商 / 現場工程師也是 user」而言，手滑點到 = 無預警斷掉真實監控。

## 做了什麼（純前端 ScenarioPage）

1. **Must-fix：live 二次確認** — `handleActivateSim` 對 `sourceKind==='live'` 先 `window.confirm`
   （比照本檔刪除情境的謹慎），文案明講「會中斷現場 SCADA 且介面無法切回」；取消則 return 不送 select。
2. **should-fix（型別）** — `sourceKind` 改用 `SourceMode`（來自 useSourceGate）而非裸 `string`，
   比對字串打錯會被 tsc 抓。
3. **should-fix（錯誤一致性）** — 抽 `parseErrorDetail(res)`，`handleActivateSim` 失敗改解析後端 detail
   （與 `handleGenerate` 共用、行為一致）。
4. **should-fix（測試覆蓋缺口，reviewer 用 mutation test 證原本假綠/沒測）** — 補：
   - live 分支 3 測（label、confirm 確認→送 select、confirm 取消→不送）。
   - 「/api/source/status 載入中 → 不顯示提示（避免閃動）」（原 `sourceKind!==undefined` guard 無測試）。
   - 「啟動成功後 `loadFarm` 重載」斷言（farms GET ×2）。

## 驗證

- **tsc --noEmit** 全綠。
- **vitest**：ScenarioPage **43** passed（39 + 4 新）；全前端 **929** passed；**vite build** 成功。
- **mutation 自驗**：(a) 停用 live guard → 「取消確認不送 select」測試轉紅；(b) 拿掉載入中 guard →
  「載入中不顯示提示」測試轉紅。兩者皆確認非假綠。

## 未做（非阻塞，記錄待後）

- `ScenarioPage` 與 `useSourceGate.selectMode` 邏輯重複 → 中長期整併（把 selectMode 傳下來）。
- 後端 `/api/source/select` 切「走 live」無角色檢查（起 live 需 SUPERVISOR）之不對稱 → 可補 defense-in-depth。
- view 模式隱藏註定 400 的 nav（Faults/Settings）。

## 卡在哪 / 下次怎麼接手

- 本 PR：draft + `hold` 待 re-review → 收斂 → 移除 hold → 自動合。
