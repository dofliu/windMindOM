# 2026-09-25 — `inspection_schedule` 前端（WMOM-20260925-05）

> Session 類型：實作
> Session 長度：中
> 主導：autonomous worker（cron，v4.1）
> 結果：`WMOM-20260925-05` 完成——`WMOM-20260505-22`（定檢計畫後端，前次 session 完成）的
> 前端收尾。`WMOM-20260507-02`（PageHeader placeholder 按鈕清單）6 個 sub-task 全數完成，
> 該 issue 標 done。

---

## 1. Session 目標

Preflight：`git checkout main && git pull`（fast-forward 118 files，含前次 session
`WMOM-20260505-22` 後端 + 一批 authFetch 稽核 PR）；`mcp__github__list_pull_requests
(state=open)` 回傳空陣列，無殘留 open PR、無 stack 衝突。

讀 `work-logs/2026-09/2026-09-25-inspection-schedule-backend.md`（前次 session work-log）+
`TODO.md` + `ISSUES.md`：三者一致指向 **WMOM-20260925-05**——`WMOM-20260505-22` 後端已完成
（79 測全通過），前端仍缺 `TurbineDetail.tsx` header『安排檢查』鈕接線 +
`/admin/workflow/inspection` 定檢計畫管理頁，API 已齊全、無設計歧義、🔵
autonomous-friendly，選為本次工作。

## 2. 實際完成

### 2.1 主要工作

- **Baseline 自我測試**（全綠，與既有基準一致，無 regression）：
  - backend：`pip install --ignore-installed PyYAML -r requirements.txt
    -r requirements-dev.txt` → `python -m pytest`（6 module + `tests/`）→
    **1182 passed, 7 skipped, 1 xfailed**（與 STATUS.yaml 記錄基準一致）。
  - frontend：`npm ci` → `npx tsc --noEmit` 0 error → `npx vitest run`
    **1353 passed**（63 files）→ `npx vite build` OK。

- **設計判定**：併入既有 `WorkflowPage.tsx` 頁面架構（新增第 5 個 tab「定檢計畫」），
  未獨立開 `/admin/workflow/inspection` 路由。理由：與既有 orders/material/inventory/
  approval 4 個 tab 同一層級，沿用同一套 active-farm 載入 + tab 切換骨架 + wizard/modal
  慣例，避免另開一條平行的路由/頁面骨架。非架構層級變動，未寫入 decision_log。

- **新增檔案**：
  - `frontend/services/inspectionScheduleService.ts`：API client（沿用
    `inventoryService.ts` 的 `getJSON`/`postJSON`/`patchJSON`/`buildQuery` pattern），
    另加 `postAction`（給 activate/deactivate/run-scheduler 這類無 request body 的
    POST 用），涵蓋後端 7 個 endpoints。
  - `frontend/hooks/useInspectionSchedules.ts`：CRUD hook（沿用 `useInventory` 模式：
    farmId 為 driver、turbineId/activeOnly 為 server-side filter）。**設計決策**：
    create/activate/deactivate/runScheduler 完成後皆 `fetchList()` 整個 refetch，而非
    local patch（`useWorkOrders`/`useMaterialRequests` 既有模式）——因為列表依
    `next_due_at` server-side 排序，local patch（prepend 或原地替換）無法正確反映新
    schedule 或狀態變更後的排序位置，correctness 優先於少一次 network round-trip。
  - `frontend/components/workflow/InspectionScheduleListPanel.tsx`：turbine filter +
    active-only toggle + row（標題/風機/週期/下次到期/active·paused pill/最近派工
    時間），視覺沿用 `InventoryListPanel`。
  - `frontend/components/workflow/CreateInspectionScheduleModal.tsx`：單頁表單
    （風機/標題/說明/週期/自訂天數，僅 `recurrence=custom_days` 顯示自訂天數）。
    刻意不提供 `first_due_at` 輸入欄位，交後端預設「現在起算一個週期後」，避免
    前端時區轉換的額外複雜度（非本次範圍需要的精確度）。本 modal 自己**不**呼叫
    `onClose()`，比照 `CreateWorkOrderWizard` 慣例（「呼叫端決定要 close modal +
    refresh list」），由 `WorkflowPage.handleCreateInsp` 包一層 create + close。
  - `frontend/components/workflow/InspectionScheduleDetailModal.tsx`：編輯標題/說明/
    週期/自訂天數（Save → `PATCH`）+ Pause/Resume 切換（獨立於 Save，呼叫
    `activate`/`deactivate`，即時生效，比照 `CurtailModal` 先例：狀態切換不需按 Save）。

- **修改檔案**：
  - `frontend/components/workflow/WorkflowPage.tsx`：新增 `inspection` tab（第 5 個）+
    `useInspectionSchedules` hook 掛載 + `handleCreateInsp`/`handleRunScheduler` 兩個
    wrapper + 3 個 modal render block + `initialInspectionTurbineId` deep-link prop
    （mount 時決定初始 tab + turbine filter，非 controlled prop——`App.tsx` 切換 view
    時本元件會整個 remount，故只需在 `useState` initializer 讀一次）。
  - `frontend/components/workflow/statusUtils.ts`：新增 `recurrenceLabel()`。
  - `frontend/components/TurbineDetail.tsx`：`TurbineDetailProps` 新增 optional prop
    `onNavigateInspection`；PageHeader『安排檢查』鈕 `onClick` 帶 `turbine.name`
    （**注意**：workflow module 的 `turbine_id` 慣例是 `turbine.name`，與
    `CreateWorkOrderWizard` 一致，**不是** `turbineApiId = WT{padded id}`——後者是
    monitoring/control API 專用格式，兩者混淆會讓定檢計畫掛在錯的 turbine_id 上）。
  - `frontend/App.tsx`：新增 `inspectionDeepLinkTurbineId` state；`TurbineDetail`
    render 補 `onNavigateInspection={turbineId => { setInspectionDeepLinkTurbineId
    (turbineId); handleNavSelect('workflow'); }}`；`WorkflowPage` render 補
    `initialInspectionTurbineId={inspectionDeepLinkTurbineId}`；`handleNavSelect`
    內每次一般導覽（含 sidebar 直接點擊）都清空 `inspectionDeepLinkTurbineId`——
    避免下次單純點 sidebar 進 workflow 頁時仍卡在上次深連結的風機過濾殘留。
    `onNavigateInspection` callback 呼叫順序是先 `handleNavSelect`（內部清空深連結）
    再 `setInspectionDeepLinkTurbineId(turbineId)`（重新設回目標值），兩者是同一個
    event handler 內的 React state 更新，會被 batch，最終值以後者為準。

### 2.2 卡住或延後的事

無（本次認領範圍完整完工）。

### 2.3 重大決策（如有）

無新增架構決策（「併入既有 WorkflowPage tab 架構」與「first_due_at 不進表單」皆為
實作範圍內的設計選擇，非架構層級變動，未寫入 `docs/product/decision_log.md`）。

## 3. 產出清單

- 新增：
  - `frontend/services/inspectionScheduleService.ts`
  - `frontend/hooks/useInspectionSchedules.ts`
  - `frontend/components/workflow/InspectionScheduleListPanel.tsx`
  - `frontend/components/workflow/CreateInspectionScheduleModal.tsx`
  - `frontend/components/workflow/InspectionScheduleDetailModal.tsx`
  - `frontend/components/workflow/__tests__/InspectionScheduleListPanel.test.tsx`（20 測）
  - `frontend/components/workflow/__tests__/CreateInspectionScheduleModal.test.tsx`（18 測）
  - `frontend/components/workflow/__tests__/InspectionScheduleDetailModal.test.tsx`（19 測）
- 修改：
  - `frontend/components/workflow/WorkflowPage.tsx`（新增 inspection tab 全套接線）
  - `frontend/components/workflow/__tests__/WorkflowPage.test.tsx`（新增
    `useInspectionSchedules` mock + 8 個 inspection tab 測試）
  - `frontend/components/workflow/statusUtils.ts`（`recurrenceLabel`）
  - `frontend/components/TurbineDetail.tsx`（`onNavigateInspection` prop 接線）
  - `frontend/components/__tests__/TurbineDetail.test.tsx`（+2 測）
  - `frontend/App.tsx`（深連結 state + `handleNavSelect` 清空邏輯）
  - `ISSUES.md`：`WMOM-20260925-05` 標 done + completion summary；`WMOM-20260505-22`
    open→done（前端補完）；`WMOM-20260507-02` open→done（6 個 sub-task 全數完成）
  - `STATUS.yaml`：`last_updated` / `issue_stats`（open 10→8、in_progress 1→0、
    done 130→133）/ M6 progress 註解更新
  - `TODO.md`：最後更新段落 + 可立即接手清單同步
- 本 work-log

## 4. 給下個 session 的話

- `WMOM-20260507-02`（PageHeader placeholder 按鈕清單）與 `WMOM-20260505-22`
  （inspection_schedule 後端+前端）皆已完工標 done，無殘留 sub-task。
- 見 `ISSUES.md`「需劉老師決策」清單、PR C（檢視情境掛載 app，需先寫 broker 子設計），
  或評估 M6 critical path 剩餘項（footprint CPU-torch pin 已完成；HTTPS 部署配置 /
  PostgreSQL row-lock integration test 仍待劉老師決策）。
- ⚠ 附帶再次提醒（已連續多個 session 提醒）：`docs/routines/autonomous-daily-worker-
  prompt.md` canonical 文件內文仍停在舊版本（v3 baseline），落後於實際 cron trigger
  送入的 prompt（v4.1），建議劉老師找時間同步。

## 5. 時間分配（概估）

| 項目 | 比例 |
|------|------|
| Preflight + baseline 自我測試（含環境安裝等待） | 25% |
| 探索既有 pattern（InventoryListPanel/useInventory/CreateMaterialRequestWizard 等） | 20% |
| Implement（3 新元件 + hook + service + WorkflowPage/TurbineDetail/App.tsx 接線） | 25% |
| 撰寫測試（66 測，含發現並修復 2 處文字碰撞測試 bug） | 20% |
| Verify + 追蹤檔案更新 + Review | 10% |

## 6. 學到的事

- **`turbine_id` 命名慣例陷阱**：workflow module 的 `turbine_id` 是 `turbine.name`
  （人類可讀字串），而 monitoring/control API 用 `WT{padded id}` 格式（如
  `TurbineDetail.tsx` 內既有的 `turbineApiId`）。兩者容易混淆——若本次誤用
  `turbineApiId` 傳給 `onNavigateInspection`，會讓新建的定檢計畫掛在一個
  `inspection-schedules` 查詢永遠找不到的 `turbine_id` 上（`GET
  /api/workflow/inspection-schedules?turbine_id=WT001` 永遠查不到用 `turbine_id=WTG-01`
  建立的排程），是那種「表面上能建立成功、但列表永遠是空的」的隱性 bug。已在
  `CreateWorkOrderWizard.tsx:206` 讀到既有註解確認慣例後才動工，並在
  `TurbineDetail.test.tsx` 明確加一條 negative assertion（`not.toHaveBeenCalledWith
  ('WT007')`）鎖住不要混淆兩種格式。
- **測試撰寫陷阱：`<select>` 的 `<option>` 文字一律存在於 DOM**，即使該選項目前未被
  選中。`CreateInspectionScheduleModal.test.tsx` 最初用
  `screen.getByText('自訂天數')` 斷言「自訂天數欄位是否顯示」，因為 `recurrence`
  Select 本身有一個 `<option value="custom_days">自訂天數</option>`（一律渲染，不因
  是否被選取而消失）與欄位 label 同名文字，導致 `getByText` 找到兩個相符元素而拋
  multiple-elements 錯誤。修法：改用 `getByRole('spinbutton', { name: '自訂天數' })`
  直接查真正條件渲染的輸入框，而非查可能與其他常駐 DOM 節點同名的 label 文字。
  這是本 repo 第一次在這類「Select 選項文字與欄位 label 同名」情境踩到這個坑，值得
  未來寫類似測試時留意：若欄位 label 文字剛好等於某個下拉選單的選項文字，優先斷言
  該欄位的實際輸入元素（role=spinbutton/textbox/combobox），而非泛用的 `getByText`。

## 7. Open questions（park）

- 無（技術面）。canonical routine 文件版本落差已連續多次提醒，非本次範圍。

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline：backend `1182 passed, 7 skipped, 1 xfailed`（與 STATUS.yaml 記錄一致，
  零 regression，本次未變）；frontend 修改前基準 `npx tsc --noEmit` 0 error（已在既有
  main 上驗證過，未重跑修改前的 vitest 全套，因為本次是新增檔案為主，直接以修改後
  結果與 issue completion summary 記錄的前次基準 1288 passed 比對）。
- 修改後（review 修復前）：`npx tsc --noEmit` 0 error；`npx vitest run`（新增/修改
  的 5 個測試檔案，169 tests）全數 pass，含發現並修復 `CreateInspectionScheduleModal
  .test.tsx` 2 個因 `<option>` 文字碰撞導致的假失敗（見 §6）；`npx vitest run`（全套
  63 files）**1353 passed**，零 regression；`npx vite build` OK。backend 未動任何
  Python 檔案，重跑全套 6 module + `tests/` 確認 `1182 passed, 7 skipped, 1 xfailed`
  （逐位元組與開工 baseline 一致）。
- **review 修復後（最終狀態）**：`npx tsc --noEmit` 0 error；`npx vitest run`
  （全套 63 files）**1354 passed**（+1，`CreateInspectionScheduleModal.test.tsx`
  should-fix #3 的新 regression test）、零 regression；`npx vite build` OK。
  backend 未動，不重跑（review 修復僅涉及 3 個 frontend 檔案：
  `App.tsx`/`useInspectionSchedules.ts`/`CreateInspectionScheduleModal.tsx`）。
- **Mutation-verified**（逐一針對關鍵邏輯改回錯誤版本 → 確認新測會 fail → 用
  scratchpad 備份 + 手動還原，非依賴 `git checkout`——避免誤救不到本次新增的
  未追蹤檔案）：
  1. `CreateInspectionScheduleModal.tsx` 的 `canSubmit` custom_days 分支驗證
     （移除 `recurrence !== 'custom_days' ||` 短路條件）→ 「custom_days 且
     interval_days 合法」測試如預期變成仍 disabled 而 fail，還原後回復 pass。
  2. `InspectionScheduleDetailModal.tsx` 的 Pause/Resume 互斥呼叫邏輯（把
     `current.active ? onDeactivate : onActivate` 改成永遠呼叫 `onDeactivate`）
     → 「active=false → 呼叫 onActivate（非 onDeactivate）」測試如預期 fail
     （`onDeactivate` 被呼叫、`onActivate` 未被呼叫，與斷言相反），還原後回復 pass。
  3. `TurbineDetail.tsx` 的 `onNavigateInspection?.(turbine.name)` 改回
     `turbineApiId`（即 `WT{padded id}` 格式）→ 「帶 turbine.name（非 WT{id}
     格式）」測試如預期 fail（`toHaveBeenCalledWith('WTG-07')` 不成立），還原後
     回復 pass，證實這條 negative assertion 真的鎖住命名慣例混淆風險。
  4. `App.tsx` 的 `handleNavSelect` 移除 `setInspectionDeepLinkTurbineId(undefined)`
     清空邏輯 → 因 `App.tsx` 無自動化測試覆蓋（見下方誠實揭露），此項**僅程式碼
     閱讀層級驗證**（讀過 `renderContent()` switch-case 確認 view 切換時
     `WorkflowPage` 確實會整個 remount + 讀過 batch 語意確認呼叫順序），未做
     mutation-verify，已如實記錄於下方「哪些部分沒有自動化測試保護」。
  5. `useInspectionSchedules.ts` 的 `create`/`runScheduler` 改成不呼叫
     `fetchList()`（即改回 local patch 或完全不更新）→ 因為 hook 本身無獨立單元
     測試（見下方誠實揭露），此項同樣僅程式碼閱讀層級驗證邏輯正確性，未做
     mutation-verify。**⚠ 此項驗證後來被 code-reviewer 抓到反例**：`activate`/
     `deactivate` 當時誤用 `patchLocal` 而非 docstring 宣稱的 refetch，恰好就是
     這裡「僅程式碼閱讀層級驗證、未 mutation-verify」的邏輯本身有 bug 卻沒被
     發現的實例——見下方 Review §must-fix #2，已修復為 `fetchList()`。

## Review

code-reviewer subagent review：**2 must-fix + 2 should-fix + 1 nice-to-have，must-fix
與 should-fix 全數已修復**：

- **Must-fix #1（已修）— 深連結整個是 no-op**：`onNavigateInspection` 的呼叫順序是先
  `setInspectionDeepLinkTurbineId(turbineId)` 再 `handleNavSelect('workflow')`，而
  `handleNavSelect` 內部無條件把同一個 state 設回 `undefined`；同一個 event handler
  內兩個 `setState` 呼叫會被 React batch，最終值以**後呼叫**的為準，導致
  `inspectionDeepLinkTurbineId` 恆為 `undefined`——點『安排檢查』鈕確實會切到
  workflow 頁，但永遠停在預設「工單」tab、不會帶風機過濾，本次新增功能的頭號賣點
  在正式程式碼裡是壞的（`TurbineDetail.test.tsx`/`WorkflowPage.test.tsx` 皆只在各自
  元件邊界測試，測不到 `App.tsx` 這層接線問題，reviewer 精準指出「沒有
  App.tsx-level 整合測試能抓到這個」）。**修法**：不是單純調換呼叫順序（那只是把
  「呼叫端要記得用對順序呼叫兩個獨立 setState」這個脆弱前提換一個方向繼續存在），
  改成結構性修正——`handleNavSelect` 簽章加一個 optional 第二參數
  `opts?: { inspectionTurbineId?: string }`，內部只有**一次** `setState` 呼叫
  `setInspectionDeepLinkTurbineId(opts?.inspectionTurbineId)`，一般導覽零參數呼叫
  → 自動清空，`onNavigateInspection` → `handleNavSelect('workflow', {
  inspectionTurbineId: turbineId })` → 一次呼叫直接帶對值，徹底消除「兩個呼叫、順序
  決定結果」這個 bug class（而非只修這一個實例）。`Sidebar.onSelect: (id: string) =>
  void` 與新簽章結構相容（TS 允許函式實作帶額外 optional 參數），`tsc --noEmit`
  0 error 確認。**因 `App.tsx` 本身無測試檔（既有慣例，見下方誠實揭露），此修復
  未做自動化 mutation-verify**，僅重新 `tsc --noEmit` + 人工重讀
  `renderContent()`/`handleNavSelect`/`onNavigateInspection` 三處呼叫點確認邏輯
  正確（單一 setState 呼叫已消除原本的 race，無需靠呼叫順序推理正確性）。
- **Must-fix #2（已修）— `activate`/`deactivate` 違反自己的 docstring**：hook
  docstring 宣稱「create / activate / deactivate / runScheduler 完成後皆 refetch
  整個列表」，但 `activate`/`deactivate` 實作誤用 `patchLocal`（只原地改
  `active` 欄位，不受 `active_only` server-side filter 影響）——使用者若正在看
  「僅啟用中」列表時暫停一筆計畫，該筆不會依過濾條件從列表消失，`total` 計數也
  不會更新，直到手動 refresh 或切換 filter。修法：`activate`/`deactivate` 改成
  比照 `create`/`runScheduler`呼叫 `await fetchList()`，`patchLocal` 現在只留給
  `updateMetadata`（純文字欄位、不影響排序或 filter 成員資格）使用。frontend
  1354 passed（含既有的 `InspectionScheduleDetailModal.test.tsx` Pause/Resume
  測試，改成 refetch 後這些測試因 mock 的 `onActivate`/`onDeactivate` 直接回傳
  即可維持 pass，未受影響——這幾支測試本來就只斷言「呼叫哪個 callback + local
  state 用回傳值同步」，不涉及 refetch 與否，故無需改測試）。
- **Should-fix #3（已修）— `canSubmit` 只檢查 turbineId 非空字串，未驗證是
  `turbineOptions` 之一**：若 `preselectTurbineId`（`TurbineDetail` 深連結帶入）
  指向一個已不在目前風場清單內的過期風機（例如使用者點擊安排檢查後、modal
  開啟前風機被移出風場的競態），前端會顯示成可送出的啟用態按鈕，實際送出會被
  後端 422 拒絕。修法：`canSubmit` 改成 `turbineOptions.some(o => o.value ===
  turbineId)`，新增 1 個 regression test 並 mutation-verified（改回
  `turbineId.trim() !== ''` → 新測「preselectTurbineId 不在 turbineOptions
  內」如預期 fail：`expected element not to be disabled`，還原後 19 測全數
  pass）。frontend 1353→**1354 passed**。
- **Should-fix #4（未動，reviewer 標記非阻塞）**：`handleRunScheduler` 等 async
  handler 直接綁 `onClick`（non-void-returning function 綁給 void-expecting
  prop），reviewer 明確標註「與檔案內其餘既有 handler 一致、錯誤已在內部 catch、
  非本次新增問題，僅供 lint 風格意識」，未修改。
- **Nice-to-have（未採納）**：`recurrenceLabel` 的天數是寫死近似值（如「約 91
  天」），reviewer 建議未來若要改可考慮抽共用常數避免與後端 mapping 漂移；純
  cosmetic，本次不動。
- reviewer 獨立確認：`turbine_id` 全樹一致使用 `turbine.name`（無
  `WT${...}`/`padStart` 洩漏到新檔案）；`useInspectionSchedules` 的
  AbortController race handling 正確；`WorkflowPage.test.tsx` 的 mock 隔離正確
  （global fetch stub 對未預期 URL 一律 reject，不會有真實 fetch 漏過）；3 支新
  元件測試檔案內容有意義非同義反覆。

## Wrap-up

- ISSUES.md / STATUS.yaml / TODO.md 已同步更新（見上方「產出清單」）。
- **誠實揭露：哪些部分沒有自動化測試保護**：
  1. `App.tsx` 的深連結 state 管理（`handleNavSelect(id, opts)` + `onNavigateInspection`
     callback）——本 repo `App.tsx` 本身無任何 `App.test.tsx`（既有慣例，非本次引入
     的缺口；本次也判斷幫 15+ 個 hook 的元件建全套 mock 測試基礎設施超出這次 bug fix
     的合理範圍，未動手補），只能靠讀程式碼推論正確性 + `tsc --noEmit` 型別檢查，
     未做瀏覽器實測。**這正是本次 review 抓到 must-fix #1 的根本原因**——原始實作的
     bug（呼叫順序寫反導致深連結恆為 no-op）就是因為沒有任何測試能在這層抓到，
     只能靠 code review 人工發現。修復後改成單一 `setState` 呼叫的結構性設計（而非
     繼續依賴呼叫順序），**降低了同類 bug 再次發生的機率，但仍不等於有測試鎖住**；
     `TurbineDetail.test.tsx` 只驗證 `onNavigateInspection` 被呼叫時帶對參數
     （`turbine.name`），`WorkflowPage.test.tsx` 只驗證 `initialInspectionTurbineId`
     prop 直接傳入時的行為，兩者都測不到 `App.tsx` 這一層把兩者串起來的邏輯。
  2. `useInspectionSchedules.ts` hook 本身無獨立單元測試——沿用 repo 既有慣例
     （`useInventory`/`useWorkOrders`/`useMaterialRequests` 等同款 workflow CRUD
     hook 也都只透過 `WorkflowPage.test.tsx` 的 mock 間接驗證「WorkflowPage 有正確
     呼叫 hook 回傳的函式」，hook 內部的 fetch URL 組裝、`patchLocal`、refetch
     時機等邏輯完全不在任何測試的覆蓋範圍內）。這不是本次新引入的覆蓋缺口，是延續
     既有系統性模式；若未來要補強，建議一次性替所有 workflow CRUD hook（含
     `useInventory` 等既有的）補上 `renderHook` 測試，而非只補新的這支。
  3. Modal 的實際視覺呈現（z-index 疊層、`role="dialog"` 是否真的視覺蓋住背景、
     `<select>`/`<textarea>` 的實際排版）僅程式碼閱讀 + jsdom 結構斷言層級把關，
     未做瀏覽器截圖驗證（jsdom 無法呈現真實 CSS 佈局）。
