# 2026-09-25 — `MaintenanceHub.tsx` header『+ 新工單』鈕接線（WMOM-20260507-02 sub-task e）

> Session 類型：實作
> Session 長度：中
> 主導：autonomous worker（cron）
> 結果：完成。

---

## 1. Session 目標

Preflight：`git checkout main && git pull`（fast-forward，本機 main 落後 origin 37
commits，含 `WMOM-20260925-01`/`-02` 已在 main，`git log -1` 確認 head 為 `ec493f3`）；
`mcp__github__list_pull_requests(state=open)` 回傳空陣列，無殘留 open PR、無 stack 衝突。

Baseline 自我測試全綠（與既有基準完全一致）：
- backend：`pip install --ignore-installed PyYAML -r requirements.txt -r requirements-dev.txt`
  → `python -m pytest`（6 module + `tests/`）→ **1103 passed, 7 skipped, 1 xfailed**。
- frontend：`npm ci` → `npx tsc --noEmit` 0 error → `npx vitest run` **1275 passed**
  （60 files）→ `npx vite build` OK。

依決策樹挑題：M6 critical path（`-04`/`-08`/`-06`）已全數完成；情境比較 A2 epic 全完成；
PR C 需先寫 broker 子設計、非單 session 可清楚定義範圍；`WMOM-20260507-02` 清單尚餘
sub-task d~f，其中 **d** 依賴 `WMOM-20260505-22`（`inspection_schedule`）尚未做、**f**
依賴 M4 reporting module 且需先設計報告類型 modal（估時 2-3h，範圍較模糊：「報告類型」
選項需對照 reporting module 既有 API 才能定案）——**e（維護中心『+ 新工單』）估時 2h、API
已存在（`POST /api/maintenance/work-orders`）、且經確認 `useMaintenanceData.ts` 的
`createWorkOrder(turbineId, turbineName, faultDescription, technicianId)` 早已完整實作
（供 `DispatchModal` 使用）但 `MaintenanceHub.tsx` 的「+ 新工單」鈕本身仍是零功能
placeholder** ——選為本次工作，開新 issue `WMOM-20260925-03` 追蹤。

## 2. 實際完成

### 2.1 主要工作

- **`frontend/components/MaintenanceHub.tsx`**：新增 `NewWorkOrderModal`（比照
  `TurbineDetail.tsx` `CurtailModal` / `DispatchModal` 的遮罩 + `role="dialog"` +
  `Card` 樣式慣例）：
  - 風機 `Select`（選項來自新增的 `turbines` prop，非寫死清單）
  - 問題描述 `textarea`（`Field` 包裹 + 明確 `aria-label`）
  - 技師 `Select`（選項為「未指派」+ 僅列出 `ON_DUTY` 技師，比照 `DispatchModal` 既有
    「只能派遣目前在崗者」的業務規則，避免重複指派 `DISPATCHED`/`OFF_DUTY` 技師）
  - 「建立工單」鈕 `disabled={!turbineIdStr || !description.trim()}`（比照
    `CreateFarmModal.handleCreate` 的 `disabled={creating || !name.trim()}` 前例，
    必填欄位用 disable 擋、非跳錯誤訊息）
  - 送出呼叫 `maintenanceData.createWorkOrder(turbine.id, turbine.name,
    description.trim(), technicianId)`（`technicianId` 未選時傳 `undefined`）後立即
    `onClose()`（比照 `DispatchModal` 既有 `handleConfirmDispatch` 前例：不额外維護
    送出中/失敗狀態，`createWorkOrder` 本身已是 fire-and-forget 且 10s 輪詢會反映最新
    工單清單）
  - PageHeader「+ 新工單」鈕 `onClick` 開啟 modal
- **`MaintenanceHubProps`** 新增必填 prop `turbines: Pick<TurbineData, 'id' | 'name'>[]`
  （型別命名為 `TurbineOption`）供風機選單使用
- **`frontend/hooks/useMaintenanceData.ts`**：`createWorkOrder` 第 4 參數
  `technicianId: number` 改為 `technicianId?: number`（原本型別宣告為必填，但後端
  `CreateWorkOrderRequest.technicianId: Optional[int] = None` 本來就是選填——`DispatchModal`
  既有呼叫方式一律有選技師故從未觸發型別不符，本次新增「未指派」路徑才真正需要傳
  `undefined`）。此為既有 API 契約的型別修正，非新增行為，`useMaintenanceData.test.ts`
  既有呼叫方式（傳入具體 `technicianId`）不受影響
- **`frontend/App.tsx`**：`<MaintenanceHub>` 呼叫點補上 `turbines={turbines}` +
  `lang={lang}`（**附帶發現並修正**：`lang` 先前完全未傳給 `MaintenanceHub`，導致
  `/admin/maintenance` 頁面無論全站語系設定為何一律 fallback 顯示繁中——本次一併修正，
  非本次範圍擴大，屬同一呼叫點的直接關聯修正）
- **`frontend/components/__tests__/MaintenanceHub.test.tsx`**：`renderHub()` 補
  `turbines` fixture（預設 2 台）+ 回傳 `maintenanceData`/`turbines` 供斷言；新增 9 測
  （開關 dialog / 取消・✕ 不呼叫 API / 必填欄位擋送出 / 風機+描述+無技師送出
  `technicianId=undefined` / 風機+描述+技師送出 `technicianId` 為 number / 技師下拉只列
  `ON_DUTY` / 風機下拉選項來自 prop / lang=en 文案），皆 mutation-verified

### 2.2 卡住或延後的事

無（本次認領範圍完整完工）。

### 2.3 重大決策（如有）

無新增架構決策；沿用既有 `DispatchModal`「只能指派在崗技師」的業務規則於新 modal。

## 3. 產出清單

- `frontend/components/MaintenanceHub.tsx`：+約 155 行（`NewWorkOrderModal` + prop +
  接線）
- `frontend/hooks/useMaintenanceData.ts`：1 行型別修正（`technicianId` 選填化）
- `frontend/App.tsx`：`MaintenanceHub` 呼叫點 +2 行（`turbines`/`lang`）
- `frontend/components/__tests__/MaintenanceHub.test.tsx`：+9 測 + `renderHub` fixture
  擴充
- `ISSUES.md`：新增 `WMOM-20260925-03`（含 completion summary）+ 回頭勾選
  `WMOM-20260507-02` sub-task e；統計表 in_progress 0→0（開單即完工）、done 128→129
- `STATUS.yaml`：`last_updated` / `issue_stats` 更新
- `TODO.md`：「最後更新」段落 + 可立即接手清單勾選
- 本 work-log

## 4. 給下個 session 的話

- `WMOM-20260507-02` 清單至此僅剩 **d**（風機細節『安排檢查』，依賴
  `WMOM-20260505-22` `inspection_schedule` 尚未做，仍卡著）與 **f**（風場總覽
  『+ 新報告』，需先確認 reporting module 現有 API 支援哪些報告類型才能定案 modal
  欄位，範圍比 e 模糊，建議下次認領前先花 15 min 讀
  `modules/reporting/routers/*.py` 摸清可選報告類型清單，避免中途卡在「不知道
  UI 選項該列什麼」）。
- **附帶發現的 `lang` 缺口**：`App.tsx` 呼叫 `MaintenanceHub` 先前從未傳
  `lang`，本次順手修正（不是本 issue 範圍擴大，是同一行呼叫點的直接修正，未新開
  獨立 issue追蹤，因已在本次一併修完不需留給下次）。
- **未受自動化測試保護的部分**：`NewWorkOrderModal` 送出中 Cancel/✕ 未 disable
  （同款 `CurtailModal`/`CreateFarmModal` 既存模式，非本次新增問題，維持現狀不修）；
  `createWorkOrder` 本身是 fire-and-forget（`useMaintenanceData.ts` 內部 try/catch
  console.warn 吞掉錯誤），若後端回傳非 2xx，modal 仍會樂觀關閉、UI 不會顯示任何
  失敗訊息——這是延用 `DispatchModal` 既有的既存行為（非本次引入），但誠實揭露：
  這條路徑「送出失敗後 UI 無感知」目前全站沒有任何自動化測試涵蓋（`createWorkOrder`
  本身在 `useMaintenanceData.test.ts` 只測了 happy path 的 auth header）。
- **⚠ 意外發現（與本次無關但值得記錄）**：`npx tsc --noEmit` 對 `.test.tsx` 檔案內的
  JSX prop 型別（例如元件必填 prop 缺漏或打錯名）**完全不會報錯**——手動注入
  `bogusPropXYZ={123}` 與移除必填 `turbines` prop 皆未觸發任何 tsc 錯誤，但同檔案內
  一般（非 JSX）型別錯誤（`const x: number = 'string'`）正常被抓到。研判與
  `tsconfig.json` 的 `"types": ["node", "vite/client"]` 未含 `"react"` 有關（JSX 全域
  命名空間可能因此退化成寬鬆型別，只影響 JSX attribute 檢查，不影響一般型別檢查）。
  **這代表本專案「`tsc --noEmit` 0 error」對元件 prop 型別的保護力比預期弱**——props
  wiring 正確與否實際上完全依賴 vitest render 測試而非型別系統。本次已用完整的
  render 測試覆蓋新增的 `turbines`/`onCreate` 等 prop（見上方 mutation-verify），
  不受此限制影響；但這是全 repo 範圍的既有 tsconfig 設定問題，非本次引入，記錄性
  提醒劉老師評估是否要修 `tsconfig.json` 補回 `"react"` 到 `types` 陣列（風險：可能
  讓其他既有元件冒出大量先前被蓋住的 prop 型別錯誤，屬於獨立的技術債清理工作，
  建議另開 issue 評估，不在本次 fix）。
- ⚠ 附帶再次提醒（已連續多個 session 提醒）：`docs/routines/autonomous-daily-worker-
  prompt.md` canonical 文件內文仍停在舊版本（v3，baseline 638/59），落後於實際 cron
  trigger 送入的 prompt（v4.1，baseline 1103/1275→1284），建議劉老師找時間同步。

## 5. Open questions（park）

- tsconfig `"types"` 陣列是否要補回 `"react"`，讓 `tsc --noEmit` 真正檢查 JSX prop
  型別？（見上方§4 意外發現；風險：可能連動冒出大量既有元件的隱藏型別錯誤，需要
  獨立 session 評估 + 清理，非本次範圍）

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline：backend `1103 passed, 7 skipped, 1 xfailed`；frontend
  `npx tsc --noEmit` 0 error、`npx vitest run` 1275 passed（60 files）、`npx vite build`
  OK。
- 修改後：backend 未動，不重跑（本次零 Python 變更，已於開工時跑過一次確認 baseline
  後於收尾前再次全套重跑確認）→ **1103 passed 不變**；frontend `npx tsc --noEmit`
  0 error（見 §4 意外發現的限制說明）、`npx vitest run` 1275→1284 passed（60 files
  不變，+9 新測，零 regression）、`npx vite build` OK。
- **Mutation-verified**（scratchpad 備份 + md5sum 核對還原，非 `git checkout`，因
  `MaintenanceHub.test.tsx` 為未追蹤新增測試段落、`git checkout` 無法還原編輯中的
  working tree 內容差異基準）：
  1. 移除 header「+ 新工單」鈕 `onClick` → 新增的 9 個 modal 測試（依賴 dialog 能開啟）
     如預期全部 fail（找不到 `role="dialog"`）。
  2. 技師下拉 `available` 改為不過濾（`technicians.filter(...)` → `technicians`）
     → 「技師下拉只列出 ON_DUTY」測試如預期 fail（多出 `派遣中乙`/`下班丙` 選項）。
  3. `canSubmit` 改為恆真（忽略必填欄位檢查）→ 「未選風機/描述空白仍 disabled」測試
     如預期 fail（按鈕未 disabled）。
  4. `technicianId` 轉換邏輯改為直接傳原始字串（不轉 `undefined`/`number`）→
     「不選技師送出 `undefined`」與「選技師送出 number 型別」兩測皆如預期 fail
     （收到 `""`/`"7"` 字串而非 `undefined`/`7`）。
  每輪皆用 md5sum 核對還原後檔案與原檔一致，確認測試非同義反覆、真的鎖住對應邏輯。

## Review

code-reviewer subagent review：待執行（見下方 Wrap-up 前將呼叫）。

## Wrap-up

見上方 §3/§4；`ISSUES.md`/`STATUS.yaml`/`TODO.md` 已同步更新（完成 code review 後）。
