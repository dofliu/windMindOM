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
  `turbines` fixture（預設 2 台）+ 回傳 `maintenanceData`/`turbines` 供斷言；新增 9 測（review 後再補 2 測共 11 測）
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
- `frontend/components/__tests__/MaintenanceHub.test.tsx`：+9 測（review 後再補 2 測，共 +11 測） + `renderHub` fixture
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
  trigger 送入的 prompt（v4.1，baseline 1103/1275→1286），建議劉老師找時間同步。

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
  0 error（見 §4 意外發現的限制說明）、`npx vitest run` 1275→1286 passed（60 files
  不變，+11 新測，零 regression）、`npx vite build` OK。
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

code-reviewer subagent review：**Approve，0 must-fix**，2 should-fix + 3 nice-to-have。

- **Should-fix #1（已修）**：技師下拉的本地選取狀態與 `useMaintenanceData` 10s 輪詢資料
  脫節——若使用者開著 modal 超過一輪輪詢、原本選定的在崗技師此時被別處改成
  `DISPATCHED`/`OFF_DUTY`，`available` 清單會把他移除但 `technicianIdStr` state
  不會自動清空，送出時仍可能夾帶這個已過期、繞過「僅能指派在崗技師」規則的 id。
  修法：`handleSubmit` 送出前重新核對 `technicianIdStr` 是否仍在當下 `available`
  清單內，不在則視同未指派（`technicianId = undefined`）。新增 1 測模擬「選定技師後
  `technicians` prop 透過 `rerender` 變成 `DISPATCHED`，送出應得到 `undefined`」，
  mutation-verified（退回舊邏輯 → 如預期送出過期 `7` 而非 `undefined`，已還原）。
- **Should-fix #2（不修，重新措辭記錄）**：reviewer 指出本次選擇沿用 `DispatchModal`
  的 fire-and-forget 模式（後端非 2xx 時 UI 無感知），而非同檔案內 `CurtailModal`
  已示範的 `submitting`/`error` state 完整寫法——精確地說是「同 repo 已有更好範式
  但這次沒採用」而非「無法做」。reviewer 確認此點本次背景已誠實揭露、且是既有系統性
  缺口非本次新增邏輯錯誤，不阻塞本次，留給未來若要補這條錯誤回饋路徑時直接照抄
  `CurtailModal` 寫法即可。
- **Nice-to-have #1（未採納）**：`role="dialog"` 缺 `aria-label`——`workflow/` 目錄下
  較新的 modal 有補，但 `CurtailModal`/`DispatchModal`/`FarmSelector` 等舊款慣例皆無，
  是 repo 內新舊兩代 modal 慣例並存的既有現象，非本次引入，不影響測試。
- **Nice-to-have #2（已採納）**：補「`turbines=[]`」邊界測試，鎖住風場尚無風機資料時
  下拉只剩 placeholder、「建立工單」鈕恆 disabled 的 fallback 行為。
- **Nice-to-have #3（未採納）**：`useMockMaintenanceData.ts`（全 repo 無任何呼叫方的
  死碼）的 `createWorkOrder` 簽名未同步放寬 `technicianId?`，reviewer 確認不影響本次、
  留待該 mock hook 未來若重新啟用時一併處理。
- reviewer 獨立重跑 `vitest run components/__tests__/MaintenanceHub.test.tsx`（58
  passed）+ `hooks/__tests__/useMaintenanceData.test.ts`（4 passed）確認與 work-log
  宣稱一致；逐行比對 `CurtailModal` 確認 `NewWorkOrderModal` 樣式為忠實複製既有慣例；
  確認 `Pick<TurbineData,'id'|'name'>[]` 接 `TurbineData[]` 在 TS 結構化型別下安全
  （陣列賦值不觸發 excess property check）；確認 `technicianId?: number` 型別放寬
  全 repo 只有 `DispatchModal`/`NewWorkOrderModal` 兩個呼叫方，前者一律有具體 id 不受
  影響。

## Wrap-up

- 已修復 1 個 should-fix（技師過期選取校驗）+ 1 個 nice-to-have（`turbines=[]` 邊界
  測試），共新增 2 測（60→62 於本檔測試數，全站 frontend 1284→1286 passed，60 files
  不變）。已重跑 `tsc --noEmit`（0 error）+ 全套 `vitest run`（1286 passed）+
  `vite build`（OK）確認零 regression，並對 should-fix #1 的修法做 mutation-verify
  （退回舊邏輯 → 新測試如預期 fail，已還原確認）。
- `ISSUES.md`/`STATUS.yaml`/`TODO.md` 已同步更新（見下方 commit）。
- 誠實揭露：Should-fix #2（後端寫入失敗時 UI 無感知）刻意不修，留在 `NewWorkOrderModal`
  作為已知限制；`useMaintenanceData.test.ts` 目前只測 happy path 的 auth header，未涵蓋
  `createWorkOrder` 非 2xx 失敗路徑的前端行為（因為目前該路徑本來就沒有任何 UI 回饋
  可供斷言）。
