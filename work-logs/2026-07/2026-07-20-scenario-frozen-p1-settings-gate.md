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
- **模擬參數 / 風況控制 / 電網控制 / 風機規格**四區塊在 `liveTuningBlocked` 時以一則說明取代。
  - 初版只 gate 後三個（會即時 POST `/api/config/*`），把**模擬參數**當「存檔用」排除——**review
    Must-fix 指出這判斷錯了**：view/live 下按「儲存設定」若 sim 參數有變，`useSettings.saveSettings`
    會 `POST /api/config/simulation` → 後端 `set_simulation` 落到 `switch_mode`，把來源**悄悄切回
    simulation**（live 時 `b.simulator.is_running` 為 False → 一樣走 restart 分支 = 斷現場 SCADA，
    正是 #144 的風險）。破壞力比另外三個更大，故**一併 gate**（藏起 → 無從觸發那次 POST）。
  - 提示文案改寫得更準（點明「改了按儲存會把來源切回即時模擬 / live 時斷 SCADA」），live 時額外標明。
- **Round-2 review 又抓到 Must-fix（更窄但同後果，reviewer 用端到端測試證實）**：gate 只藏 UI、不 reset
  `formData.simulation`。情境：使用者在 simulation 下編輯風機數（未存）→ 5 秒輪詢抓到來源被**別處**切走
  （view/live）→ Section 隱藏但 `formData` 仍留 stale 編輯值 → 按儲存 → `useSettings` 偵測 simChanged →
  `POST /api/config/simulation` → 後端 `switch_mode` 切回 simulation（live 斷 SCADA）。**我加的 5 秒輪詢
  反而讓此既有缺口更容易在同一次瀏覽踩到。** 修：`handleSubmit` 送出當下若 blocked，把 `simulation`
  還原成 `settings`（payload guard；formData 本身保留編輯值，來源切回即時模擬時不遺失）→ simChanged
  false → 不 POST。+1 端到端回歸測試（編輯→advanceTimers 5s 切 view→儲存→斷言 onSave 收到原值 21），
  同時補上「5 秒輪詢有效」的覆蓋（round-2 Should-fix）。mutation 自驗：拿掉 guard → 該測試轉紅。
- **Should-fix 折入**：`sourceKind` 併入既有 5 秒輪詢（gate 是安全網，來源被別處切換要跟得上）。
- **Nits 折入**：測試 helper `sourceKindFetch` 型別改 `SourceMode`；`sourceKindLabel` fallback 加註
  「防禦性、目前不會走到」；英文文案改自然。
- **Should-fix 延後**：`sourceKind`/`sourceKindLabel` 與 ScenarioPage 重複 → 待 PR B/C 前抽共用 hook/util。

## 驗證

- **tsc --noEmit** 全綠。
- **vitest**：SettingsPage **22** passed（#145 的 18 + 4 新 gate 測試：view 隱藏四區塊 / live 文案點明
  斷 SCADA / simulation 顯示 / fail-open）；全前端 **934** passed。既有 `defaultFetch` mock 補
  `/api/source/status`（預設 simulation，既有 SIMULATION 測試維持有效）。
- **mutation 自驗**：(a) `liveTuningBlocked` 寫死 false → view 測試轉紅；(b) 把模擬參數的 `!liveTuningBlocked`
  拿掉 → view 測試（模擬參數應隱藏）轉紅。皆非假綠。
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
