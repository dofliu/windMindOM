# 2026-05-09 — Approval Frontend（WMOM-20260504-20）

> Session 類型：實作（frontend / TypeScript / React）
> Session 長度：短-中（接續 -19 session 同一日 push）
> 主導：Claude
> 結果：把 WMOM-20260504-18 的 3 個 approval REST endpoint 串成可用的簽核 UI；M3 frontend 全收。

---

## 1. Session 目標

進 M3 frontend 收官 issue。範圍（依 ISSUES.md WMOM-20260504-20）：

- 擴充 `frontend/services/workOrderService.ts`：加 signoff types + `signoffApi`（3 endpoints）
- `frontend/hooks/usePendingApprovals.ts`：list + approve/reject mutations + work-order subject 自動拉 cache
- `frontend/components/workflow/PendingApprovalPanel.tsx`：層級選擇 + subject filter + 待簽列表
- `frontend/components/workflow/ApprovalActionDialog.tsx`：approve / reject 對話框（comment / reason 輸入 + subject 摘要）
- 改 `frontend/components/workflow/WorkflowPage.tsx`：啟用 approval tab + 串新 panel + dialog

---

## 2. 實際完成

### 2.1 新檔（共 3 個）

- `frontend/hooks/usePendingApprovals.ts` — pending list state + approve/reject 兩個 mutations + workOrderCache（auto-fetch 每筆 chain.subject_type=='work_order' 的 work order detail，給 UI 顯示 title/turbine/priority 用）+ AbortController race guard
- `frontend/components/workflow/PendingApprovalPanel.tsx` — level selector (employee/leader/supervisor/treasury，default leader) + subject_type filter (all / work_order / material_request) + 列表（subject 摘要 / step/chain progress / approve+reject 按鈕）+ empty/loading/error
- `frontend/components/workflow/ApprovalActionDialog.tsx` — 兩模式：approve（comment 選填）/ reject（reason 必填）；上方顯示 work order 摘要避免簽錯；底部處理 `subject_transition_error` warning（chain 已落地但 work_order transition 失敗的 race case）

### 2.2 改檔（共 3 個）

- `frontend/services/workOrderService.ts`：加 SignoffLevel/SignoffStatus/SignoffSubjectType type + value arrays、SignoffStep/Chain/PendingItem/ApprovalResult 等 response interface、ApproveStepRequest/RejectStepRequest body、`signoffApi.{listPending, approve, reject}` 3 個 method
- `frontend/components/workflow/statusUtils.ts`：加 `signoffLevelLabel` / `signoffStatusLabel` / `signoffStatusTone` / `subjectTypeLabel` 4 個 zh/en helper
- `frontend/components/workflow/WorkflowPage.tsx`：tab 從 dummy disabled 變真切換、render `<PendingApprovalPanel>` + dialog；tab badge 顯示 pendingCount；approve/reject 完成且 `subject_status_changed === true` → 自動 `wo.refresh()` 把 orders list 同步

### 2.3 Smoke test

- `npx tsc --noEmit` → clean（0 error）
- `npx vite build` → ✓ built in 10.17s（1067 kB / gzip 286 kB；比 -19 多 ~12 kB ≈ 新元件 + types overhead）
- `npx vite --port 5179` + `curl localhost:5179/` → HTTP 200，title `windMindOM · Operations` 正常

### 2.4 UI directive 驗收

- ✅ 全程 import `frontend/components/ui/`（Card / Btn / Field / Select / StatusPill / PageHeader）+ `useTheme()` C palette
- ✅ 沒寫任何 Tailwind utility / 沒硬寫 hex（除 modal overlay rgba 與既有檔一致）
- ✅ ApprovalActionDialog 套既有 modal 風格：`Card padding={0}` + DM Serif title + 底部 Btn group

---

## 3. 設計決策

### 3.1 work order detail cache 策略

`GET /approvals/pending` 回傳的 chain 只有 `subject_id`（UUID），UI 要顯示工單 title/priority/status 必須再去 query。三種選項：

1. backend 改 endpoint 加 `?include=work_order` join 回傳 — 需動 backend，超出 -20 範圍
2. UI 按需求 lazy fetch — 每張 row hover 或開 dialog 才打 — 一般情境每次都要看到 title，浪費 round-trip
3. **採用：list 拉到後並行 fetch 所有 unique work_order subject_id，存進 Map**

第 3 個方案：`Promise.allSettled` 容忍個別 fetch 失敗（404 等），放棄該 row 的 title 顯示但其他正常；race guard 跟 list fetch 共用一個 `AbortController`。Trade-off：每次切換 level 會多 N 個 GET，但 UI 顯示完整。M4 領料單來時 cache 同邏輯擴充。

### 3.2 為什麼工單 detail modal 的 approve 按鈕仍然 disable

DN-02 設計上 approve 是走 `POST /approvals/{step_id}/approve`（multi-step chain）而非工單層的 `POST /work-orders/{id}/approve`（後者 backend 有 server-side guard 會檢 chain 是否全 APPROVED，等於故意設計成 approval 流程的副作用 endpoint）。

UI 流程因此分得很清楚：
- 工單 IN_PROGRESS → 完工 → AWAITING_SIGNOFF（detail modal）
- AWAITING_SIGNOFF → 由 reviewer 在 approval tab 處理 → 自動 close

工單 detail modal 內的 approve 按鈕保留 disable + 「請至 approval tab 處理」hint 是正確的。

### 3.3 subject_transition_error 的 UI 處理

backend `ApprovalResultResponse.subject_transition_error` 是 nullable string — chain 已 approve/reject 落地但 work_order 那邊 transition 失敗（罕見，例如工單剛被別的 session 改掉 status）。dialog 不關，改顯示 warning Card 提示「請通知 ops 補正工單狀態」，這樣 user 知道 chain 已結束、不能重做，但工單需要人工 backfill。

### 3.4 default level = leader

工單 chain 預設 = `[EMPLOYEE, LEADER]`（DN-02 D2-Q2），EMPLOYEE 是「派工簽收 / 完工申報」，這層通常派工人員自己處理；LEADER 是組長簽核，是 reviewer 最常出現的角色。所以 panel 預設 `level=leader`。CRITICAL priority 工單會多加 SUPERVISOR 這層（backend `escalate_to_supervisor` flag），user 自行切到 supervisor tab 看。

### 3.5 actor_id 占位策略

延續 -19，全部 mutation 用 `DEV_ACTOR_ID` 常數。Auth 系統 M5+ 上線時改抽 hook + replace constant 即可。

---

## 4. 待辦 / Follow-up

- ⬜ Pending list 拉太多時 cache 也會跟著膨脹（`Promise.allSettled` 同時打 N 個 GET）— 工單量 > 200 時加 server-side eager join 或 dedupe
- ⬜ Pagination UI（目前單頁 limit=200）
- ⬜ approval history view（已簽過的 chain 列表）— 等 backend 加 endpoint
- ⬜ 切 level / subject_type 時保留之前選的 dialog 狀態 — 目前 dialog 是 modal-level state，切 panel 不影響但可重複進入

---

## 5. M3 Milestone 收官

WMOM-20260504-19 (orders frontend) + -20 (approval frontend) 都收掉後，M3 backend 5 issue + frontend 2 issue 全 done：

- WMOM-20260504-14（z72_etech 取設計）✅ done
- WMOM-20260504-15（walkthrough）✅ done
- WMOM-20260504-16（domain + state machine）✅ done
- WMOM-20260504-17（work order CRUD API）✅ done
- WMOM-20260504-18（approval/signoff API）✅ done
- WMOM-20260504-19（orders frontend）✅ done
- WMOM-20260504-20（approval frontend）✅ done

M3 衍生 issue（不阻塞）：WMOM-20260505-21（day_work_form）、-22（inspection_schedule）— 排到 M3+/M4 之間。

下一個主軸候選：M4（inventory）開工，或 WMOM-24 data quality 修正。

---

## 6. Commit

`feat(#WMOM-20260504-20): approval frontend (pending list + approve/reject dialog)` — 6 files changed
