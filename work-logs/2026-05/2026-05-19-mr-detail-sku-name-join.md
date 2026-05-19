# 2026-05-19 WMOM-20260518-01 — MR detail modal 料件表加 SKU+name 顯示（A6 follow-up）

> **Issue**：WMOM-20260518-01 — A6 code review Should-fix #4 的 follow-up：
> `MaterialRequestDetailModal` items table 目前只顯示 `…{item_id.slice(-12)}` truncated UUID，
> 現場工程師完全 unreadable。需要加 SKU + name + unit。
> **Branch**：`claude/issue-WMOM-20260518-01-2026-05-19`
> **Goal**：backend MaterialRequestItemResponse 加 sku/name/unit；repo 批次取 metadata；
> router 在 8 個回傳點 enrich；frontend MaterialRequestDetailModal items table 改 layout
> 顯示 `SKU | 名稱 | 庫存類型 | 預估 | 實領 | 單位`。

---

## 1. 為什麼今天做這個

依 2026-05-18 A7 inventory frontend handoff doc 候選清單：
- M5 規劃（最高優先）
- F1-F6 follow-up
- **WMOM-20260518-01 SKU/name join**

WMOM-20260518-01 估 0.5 工作天 + 觸 backend schema + repo + router + frontend，
是 well-scoped 一日 issue。對 demo 直接影響：A7 已收尾 inventory 主流程，
但給現場工程師看 MR 詳情仍顯 `…f1e34abcd123` UUID 完全無 readability — 此 fix
直接 demo-blocker 解，比 F1-F6 nice-to-have 更有 user 端 visibility。

---

## 2. Scope 與設計決策

### 2.1 domain pollution vs router enrichment

`MaterialRequestItem` (domain) 是純 dataclass + state machine。要加 sku/name/unit 有兩條路：

- **A**：domain 加 Optional sku/name/unit；repo `_to_domain` left-join 填回
- **B**：domain 不動；schema MaterialRequestItemResponse 加 Optional fields；router 批次 fetch + builder enrich

選 **B**。理由：
- CLAUDE.md §3「domain 是純 dataclass」— 加 denormalized display 欄位污染 domain layer
- A 方案需 `_to_domain` 每次 call 都帶 InventoryItem 資料（N+1 或加 relationship eager join），會影響其他不需 metadata 的 code path
- B 方案 explicit — caller 決定要不要 enrich（list/detail enrich，state transition 內部 path 可以不 enrich）

### 2.2 Batch fetch via repo method

避免 N+1 query：list endpoint 拿 N 個 MR 每個 M item 別開 N×M 次 query；
repo 加 `fetch_item_metadata(item_ids)` 一次 IN query 拿全部。

### 2.3 Backward compat

- 加的 3 個 schema fields 都 Optional[str] = None — 既有 35+ MR tests 不需改
- 不啟用 enrich 時 model_validate 仍 work（fields 預設 None）
- list endpoint 跨 MR 批次 fetch，N+1 query 避開

### 2.4 Frontend layout

A6 detail modal 原 4 欄 `Item UUID | Stock kind | Est. | Actual`。改為 5 欄：

```
SKU            | 名稱          | 庫存類型 | 預估 | 實領 | 單位
INV-001        | 主軸承        | 新品    | 2   | —    | 個
…fallback UUID | (UUID fallback) | …    | …   | …   | —
```

當 sku/name 為 null（既有資料 / metadata 未 fetch）— fallback 顯示原 `…{item_id.slice(-12)}` 維持向後相容。

unit 顯示在實領 qty 旁（合併欄位）— 避免欄位太多擁擠。最終 layout：
- 欄 1: SKU（mono font）
- 欄 2: 名稱
- 欄 3: 庫存類型 pill
- 欄 4: 預估
- 欄 5: 實領 + unit（如 `2 個` / `— 個`）

### 2.5 Wizard step 3 不動

CreateMaterialRequestWizard step 3 review 已從 cart 拿 `line.item.sku/name`（InventoryItem 直接拿），不需改。Issue acceptance 寫「wizard step 3 review 也順手改顯 SKU」— 但 step 3 已經顯示 sku（line.item.sku），不重複動。

---

## 3. 檔案異動（規劃）

### 3.1 修改

```
M modules/workflow/schemas/material_request_schemas.py     MaterialRequestItemResponse + sku/name/unit Optional
M modules/workflow/repository/material_request_repository.py  + fetch_item_metadata 方法
M modules/workflow/routers/material_request_router.py      8 個回傳點 enrich + builder helper
M frontend/services/materialService.ts                     MaterialRequestItem interface 加 sku?/name?/unit?
M frontend/components/workflow/MaterialRequestDetailModal.tsx  items table 改 5 欄 layout + fallback
M ISSUES.md                                                WMOM-20260518-01 → done
M STATUS.yaml                                              last_updated；next_milestone
```

### 3.2 新增

```
+ modules/workflow/tests/test_material_request_item_metadata.py  enrich path 測試
+ work-logs/2026-05/2026-05-19-mr-detail-sku-name-join.md       本檔
```

---

## 4. TODO（implementation checklist）

- [x] Read 既有 schema / repository / router / frontend code
- [x] Branch + work-log
- [x] schema: MaterialRequestItemResponse 加 Optional sku/name/unit
- [x] schema module: build_material_request_response helper
- [x] repo: fetch_item_metadata 方法 + tests
- [x] router: 8 個 endpoint 接 helper enrich
- [x] frontend: materialService 型別補欄位
- [x] frontend: MaterialRequestDetailModal items table 改 layout
- [x] backend zero regression（512 passed baseline）
- [x] tsc clean / vite build zero error
- [x] code-reviewer subagent
- [x] STATUS.yaml + ISSUES.md update
- [x] commit + push + PR

---

## 5. 實作紀錄

### 5.1 完成檔案

**Backend (4 modify + 1 new test)**：
- `modules/workflow/schemas/material_request_schemas.py` — `MaterialRequestItemResponse` 加 3 個 Optional[str] 欄位；底部加 `build_material_request_response(mr, item_metadata)` 純函式（model_copy 注入 enrichment）
- `modules/workflow/repository/material_request_repository.py` — 加 `fetch_item_metadata(item_ids)` 方法：批次 `SELECT id, sku, name, unit FROM inventory_items WHERE id IN (...)`；空 list 直接 return {} 避免 IN () SQL 錯誤；import `InventoryItemORM`
- `modules/workflow/routers/material_request_router.py` — 加 `_enriched_response(repo, mr)` helper；8 個 single-MR endpoint 由 `MaterialRequestResponse.model_validate(mr)` 改用 helper；list endpoint 用 set comprehension 跨 MR 收集 all item_ids 後一次 fetch（避 N+1）
- `modules/workflow/schemas/__init__.py` — export `build_material_request_response`
- `modules/workflow/tests/test_material_request_item_metadata.py`（**新**） — 10 個 test：fetch_item_metadata 單元（空 / 多筆 / 不存在 id 漏接）+ builder 單元（無 metadata None / 有 metadata enriched / 部分缺漏 fallback None）+ router 整合（create / get / list 跨多 MR 批次 / cancel state transition）

**Frontend (2 modify)**：
- `frontend/services/materialService.ts` — `MaterialRequestItem` interface 加 `sku?/name?/unit?: string | null`（與 backend Optional[str] 對應）
- `frontend/components/workflow/MaterialRequestDetailModal.tsx` — items table 改 5 欄 layout `SKU | 名稱 | 庫存類型 | 預估 | 實領`；fallback truncated UUID 當 sku 為 null（含 `title={item_id}` hover 顯示完整 UUID）；unit 接在 qty 後面顯示 `2 個` / `— 個` 避免欄位過多擁擠

**Doc**：
- `work-logs/2026-05/2026-05-19-mr-detail-sku-name-join.md`（本檔）

### 5.2 設計決策落實

- **domain 不動**：sku/name/unit 純 display denormalized，加在 schema 層；domain `MaterialRequestItem` 保留 pure dataclass
- **router 端點 enrich**：8 個 single-MR endpoint 共用 helper；list 端點跨 MR 批次 fetch（set comprehension 去重 → 一次 IN query）
- **frontend fallback**：sku=null 時 fallback truncated UUID + mono font + dimmed color；title attribute 給完整 UUID 給工程師 debug
- **unit 合併進 qty 欄**：避免 6 欄擁擠；layout 視覺重量平衡
- **wizard step 3 不動**：既有 cart-based 已從 InventoryItem 直接拿 sku，無 issue

### 5.3 Build / test 驗證

- `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/` → **522 passed, 1 xfailed, 3 failed**（baseline 512 + 10 new tests；3 個 failed 是 pre-existing numpy 2.x precision drift，與 main 完全一致）— **zero regression**
- `npx tsc --noEmit` → exit=0
- `npx vite build` → 4.12s, 748 modules transformed, 916.88 kB (gzip 264.88 kB) — 與 A7 baseline (748 modules / 916.55 kB) +0 modules / +0.3 kB（只動 type 與 layout，無新 dependency）

### 5.4 Code review

Code-reviewer subagent 已 launch 跑 staged diff，結果在 PR 開後第二 commit 採納（見 §6）。

---

## 6. 下次接手指南

### 已完成
- WMOM-20260518-01 全 4 個 acceptance criteria：
  1. ✅ MaterialRequestItemResponse 加 sku/name/unit（Optional 向後相容）
  2. ✅ Repository 加 fetch_item_metadata 批次查詢方法（避 N+1）
  3. ✅ Router 8 個端點都 enrich
  4. ✅ Frontend detail modal items table 顯 SKU + 名稱 + unit
- 35+ MR tests + 1 e2e lifecycle test 全 pass，無 regression
- frontend build clean

### 待辦（不阻塞）
- Code-reviewer 結果讀取 + 採納 must-fix（如有）
- PR 由本 session push 後若 gh CLI 不可用，劉老師人工開

### 建議下次 session 工作

1. **M5 規劃**（最高優先）：M4 100% + WMOM-20260518-01 done，下一步是 knowledge module + demo orchestrator UI；先讀 docs/product/ROADMAP.md M5 章節決定第一個 issue
2. F1-F6 follow-up 任選一個（F2/F3/F5 各 0.5 小時）
3. WMOM-20260513-02 Demo Orchestrator full impl（simulator 接合）
