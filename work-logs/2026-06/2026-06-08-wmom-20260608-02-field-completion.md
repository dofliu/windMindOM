# WMOM-20260608-02 — M5-5 Part B-2 現場完工流程

- **Date**: 2026-06-08
- **Branch**: `claude/issue-WMOM-20260608-02-2026-06-08`
- **Decision baseline**: DEC-20260608-02（assignee_id 過濾「我的工單」+ 完工需簽名/拍照）

## 現況盤點（開工前）

- **WorkOrder domain** 已有 `assignee_id: UUID | None` + 完工欄位（`finished_at`/`actual_hours`/`work_summary`/`unfinished_items`/`followup_kind`/`followup_note`）；完工 = IN_PROGRESS → AWAITING_SIGNOFF（`state_machine` finish action）
- **list_work_orders** endpoint **無 assignee 過濾** → 要加
- **finish** 流程無 signature/photo → 要加
- **mock login**：`mockUsers.ts` user `id` = actor_id；current user 走 `getCurrentActorId()` / `useCurrentUser`。Alice(employee) = 現場工程師 persona。「我的工單」= `assignee_id == 目前 actor_id`
- **FieldPage.tsx**：mobile 雙模式（query / alert）；要加第三模式「我的工單 + 完工」
- **workOrderService.ts**：已有完整 list / finish API client

## 設計決策

### 關鍵：signature/photo 設 optional（向後相容）
既有 admin finish path + 測試不帶 signature/photo。若設必填會破壞既有測試。
→ backend schema/domain 設 **optional**（存即可）；「完工須簽名+拍照」的**強制在現場前端**那層（完工表單未簽未拍 → submit disabled）。符合 DEC「現場工程師完工」語意，不影響 office finish。

### 儲存策略（demo-first）
- `completion_signature`: TEXT nullable（canvas base64 PNG data URL，單張）
- `completion_photos`: TEXT nullable（JSON array of base64 data URL，多張）
- demo 階段 base64 進 DB 最簡、離線可跑；M6 生產前可改物件儲存（follow-up）

## 範圍

### Backend（本 session 主體）
1. domain `work_order.py`：加 `completion_signature` / `completion_photos`
2. `state_machine.py` finish action：存 signature/photos
3. ORM `orm_models.py`：加兩欄
4. schema `work_order_schemas.py`：FinishRequest + WorkOrderResponse 加欄（optional）
5. repository `work_order_repository.py`：persist/load + `list()` 加 `assignee_id` 過濾
6. router `work_order_router.py`：list 加 `assignee_id` query param
7. tests：domain / state_machine / repo round-trip + assignee filter / API finish with signature

### Frontend
8. `workOrderService.ts`：FinishRequest + list query 加欄位
9. `FieldPage.tsx`：第三模式「我的工單」（assignee 過濾）+ 完工表單（actual_hours + summary + 簽名 canvas + 拍照）

## 完成

### Backend
- domain `work_order.py`：`completion_signature` / `completion_photos`
- `state_machine.py` finish：存佐證
- ORM + 輕量 migration（`ALTER TABLE wmom_work_orders ADD COLUMN`，try/except OperationalError 防 multi-worker 鎖）
- schema：FinishRequest + WorkOrderResponse 加欄（optional）
- repository：`_load_completion_photos`（JSON 還原 + 防呆）+ `list(assignee_id=)` 過濾 + mappers（`ensure_ascii=False`）
- router：finish 傳佐證 + list 加 `assignee_id` query param
- `test_field_completion.py` **11 tests**（round-trip / assignee 過濾 + None 排除 / migration 冪等 / API）

### Frontend
- `workOrderService.ts`：FinishRequest/Response/ListQuery 加欄（response 設 optional 免動既有 fixture）
- `MyOrdersMode.tsx`（新）：我的工單列表（assignee 過濾）+ 完工表單 + SignaturePad canvas + 拍照；**簽名+照片+工時齊備才能送**（DEC 前端強制）；reload race guard（reqId）
- `FieldPage.tsx`：接第三模式「我的工單」
- `MyOrdersMode.test.tsx` **7 tests**

### Verify
- backend **436 workflow passed**（425 + 11；全 backend 711 passed / 1 xfailed 零 regression）
- frontend tsc 0 + vitest **797 passed**（790 + 7）+ vite build ✓

### Code review（code-reviewer subagent）
2 must + 5 should + 4 nice → **採納 6**（must#1 migration 鎖 / should#1 onPointerCancel / should#4 assignee=None test / should#5 reload race / should#2 錯誤訊息 / nice#2 ensure_ascii）；
**婉拒/跳過**：must#2（finish 是 fresh 完工，`or []` 與 signature 處理一致，非 bug）/ should#3 to_dict Any（既有碼非本 diff）/ should#6 actual_hours ge=0（既有 schema）/ nice#1,#3,#4（封裝/farmApi/可讀性，ROI 低）。

## 踩坑
- tablename 是 `wmom_work_orders` 不是 `work_orders`（migration 一開始用錯名 → 28 errors）
- 新增 required response 欄破壞 6 個既有 fixture → TS response 改 optional（消費端不讀佐證）

## 設計決策
- signature/photo backend optional + 前端強制：不破壞 office finish path，符合 DEC「現場工程師完工」語意
- base64 進 DB（demo-first）；M6 生產前可改物件儲存 + 加大小上限（review must#3 標記，列 follow-up）

## 下一步 / follow-up
- 完工佐證大小上限（base64 photo 無界，M6 前加 `max_length` + 物件儲存）
- M5-3/4 完整 Z72 手冊向量檔
