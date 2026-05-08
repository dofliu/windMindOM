# 2026-05-08 — Work Order Frontend（WMOM-20260504-19）

> Session 類型：實作（frontend / TypeScript / React）
> Session 長度：中
> 主導：Claude
> 結果：把 WMOM-20260504-17 的 11 個 work-order REST endpoint 串成可用的 admin UI，包含列表、建立精靈、詳情 + 狀態 transition modal。

---

## 1. Session 目標

進 M3 frontend 主線。範圍（依 ISSUES.md WMOM-20260504-19）：

- `frontend/services/workOrderService.ts`：TypeScript API client（11 endpoints）
- `frontend/hooks/useWorkOrders.ts`：stateful hook（list / loading / error / CRUD + 8 transitions）
- `frontend/components/workflow/WorkflowPage.tsx`：主入口（tab 預留給 -20 approval）
- `frontend/components/workflow/WorkOrderListPanel.tsx`：列表 + status filter + business_key search
- `frontend/components/workflow/CreateWorkOrderWizard.tsx`：3-step 精靈（風機 / 故障碼+類型+優先級 / 派工 + 工時）
- `frontend/components/workflow/WorkOrderDetailModal.tsx`：完整詳情 + 7 個 state transition 按鈕（workflow 版本，與既有 legacy 同名 modal 區分）
- 改 `frontend/App.tsx` + `frontend/components/ui/Logo.tsx`：加 `workflow` 導航項

UI directive（WMOM-20260507-01 後）：必須走 `frontend/components/ui/` + `frontend/theme/`，不可寫 Tailwind utility class、不可硬寫 hex（chart event 標記色除外）。

---

## 2. 實際完成

### 2.1 新檔（共 7 個）

- `frontend/services/workOrderService.ts` — 11 endpoints API client + farm helper + DEV_ACTOR_ID 占位 + ~80 行 enum/type 與 backend `WorkOrderResponse`/`WorkOrderListResponse`/各 request 對齊
- `frontend/hooks/useWorkOrders.ts` — stateful hook：list state + 9 mutations（create + 8 transitions）+ AbortController race guard + client-side search filter
- `frontend/components/workflow/WorkflowPage.tsx` — 主入口（farm 自動偵測 / tab 預留 approval / wizard + detail modal 編排）
- `frontend/components/workflow/WorkOrderListPanel.tsx` — 列表（status filter / search / refresh / empty / error）
- `frontend/components/workflow/CreateWorkOrderWizard.tsx` — 3-step 精靈
- `frontend/components/workflow/WorkOrderDetailModal.tsx` — 詳情 + 7 個 inline transition form（dispatch / start_work / progress / finish / reject / cancel / reopen）
- `frontend/components/workflow/statusUtils.ts` — enum → label / pill tone / datetime fmt 共用 helper

### 2.2 改檔（共 2 個）

- `frontend/App.tsx` — `ViewId` 加 `workflow`、PRIMARY_NAV 加 `workflow` 項、case `workflow` render `<WorkflowPage>`
- `frontend/components/ui/Logo.tsx` — `NavIconId` 加 `'workflow'` + 對應 SVG icon（briefcase）

### 2.3 Smoke test

- `npx tsc --noEmit` → clean（修一處：`buildQuery` 不接 typed interface，改傳 explicit object）
- `npx vite build` → ✓ built in 10.60s（725 modules / 1.05 MB / gzip 283 kB）
- `npx vite --port 5179` + `curl localhost:5179/` → HTTP 200，HTML title `windMindOM · Operations` 正常

### 2.4 UI directive 驗收

- ✅ 全程 import `frontend/components/ui/`（Card / Btn / PageHeader / StatusPill / Field / Input / Select）+ `useTheme()` C palette
- ✅ 沒寫過任何 Tailwind utility class
- ✅ 沒硬寫 hex（除了 `rgba(0,0,0,0.55)` modal overlay backdrop，與其他既有 modal 一致）
- ✅ Modal 套既有 `WorkOrderDetailModal` / `DispatchModal` 風格：`Card padding={0}` + DM Serif title + 底部 Btn group

---

## 2.5 Commit

`feat(#WMOM-20260504-19): work order frontend (orders list + wizard + detail) — see git log`



---

## 3. 設計決策

### 3.1 為何 detail modal 在 `components/workflow/` 而非沿用 `components/WorkOrderDetailModal.tsx`

舊 modal 對應的是 `frontend/types.ts` 內 legacy 的 `WorkOrder` interface（`turbineId: number`、`notes: string`、`photos: string[]`、3-status enum），來源是 mock maintenance hub。

backend `/api/workflow/work-orders` 回傳的是 dataclass 衍生的 schema（`WorkOrderResponse`，`turbine_id: string`、7-status state machine、`progress_notes` array、`signoff_chain_id`...），完全不同 shape。

折衷：保留 legacy modal 不動（仍服務 MaintenanceHub mock 流程），新檔 `components/workflow/WorkOrderDetailModal.tsx` 走 backend schema；directive 講的「套既有 modal 風格」用同樣 Card padding=0 + DM Serif title + 底部 Btn 的版面，但邏輯獨立。

### 3.2 actor_id 占位

`/dispatch` 跟 `/update-progress` 後端要 `actor_id: UUID` 做 audit。windMindOM 目前還沒 user 系統（M5+ 才會接 RAG 認證），所以前端用一個固定 dev UUID `00000000-0000-0000-0000-000000000001`（hard-coded constant，命名 `DEV_ACTOR_ID`，註解標 `TODO: replace with auth user when WMOM-2026XX-XX lands`）。

### 3.3 farm_id 來源

backend 所有 endpoint 都要 `farm_id` query param。前端不重複寫 fetch — 直接讀 `/api/farms` 取得 `active_farm_id`，跟 FarmSelector 同 source。WorkflowPage 內部跑一次 fetch，存進 state，全部 hook 用同一個 farm_id。

### 3.4 為何用 fetch 而非 axios

延續 costService.ts 模式（純 fetch + helper），保持 lightweight，不引新 dep。

### 3.5 wizard 步驟設計

按 ISSUES.md 描述「多步：選風機 / 選故障代碼 / 派工人員 / 預估工時」：

- Step 1: 風機選擇（從 `useRealtimeData().turbines` 列表，顯示 `name` + 狀態 pill；`turbine_id` 取 `name` 因為 backend simulator 用 `name` 作 string id）
- Step 2: 工單細節（type + priority + title + description + source_alarm_code 選填）
- Step 3: 派工 + 工時（assignee_id 選填走 dev placeholder、crew_size、estimated_hours）

每步用 Card + 「Next / Back」Btn 控制；最終 Submit 呼叫 `POST /api/workflow/work-orders`（建出來是 DRAFT，後續使用者可在列表 → detail modal 走 dispatch / start-work / finish... 流程）。

---

## 4. 風險 / 待辦

- ⬜ `/finish` body 含 `followup_kind` enum 跟 `actual_hours`，UI 要 inline form 而非單純按鈕 — modal 內用 collapsible section 處理
- ⬜ `/approve` 跟 `/reject` 的 single-button 流程其實要走 -20 的 approval-router（detail modal 顯示「Pending signoff」disable 直接 approve；實際走 `/api/workflow/approvals/{step_id}/approve`），這留給 WMOM-20）
- ⬜ i18n：lang prop 已 thread 到所有元件，但詳細 enum label（status / type / priority）的 zh 字串先寫死在 component 內，沒抽 hook
- ⬜ pagination：先支援 `limit=200 / offset=0`（單頁），下次頁碼控制再說

---

## 5. 後續 issue 備註

完成後更新：
- ISSUES.md WMOM-20260504-19 status → done
- STATUS.yaml progress 從 82 上推；M3 milestone progress 80→90
- next_milestone 更新為 WMOM-20260504-20（approval frontend）

---

（待 session 結束補完成 summary、commit hash、smoke test 結果）
