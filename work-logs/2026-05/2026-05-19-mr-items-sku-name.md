# 2026-05-19 WMOM-20260518-01 — MR detail items 加 SKU+name+unit 顯示（A6 follow-up）

> **Issue**：WMOM-20260518-01 — `MaterialRequestItemResponse` 加 `sku/name/unit` 三欄；router 層 batch fetch InventoryItem 填回；frontend `MaterialRequestDetailModal` items table 改 layout
> **Branch**：`claude/issue-WMOM-20260518-01-2026-05-19`
> **Goal**：解決 A6 code review Should-fix #4 — 現場工程師看 MR detail items 只能讀到 `…{item_id.slice(-12)}` truncated UUID 完全無 readability 的問題

---

## 1. 為什麼今天做這個

依 2026-05-18 A7 inventory frontend handoff 建議候選清單：
- M5 規劃（highest 但 planning 非 code）
- F1-F6 follow-up（小修可塞）
- **WMOM-20260518-01 SKU+name join（A6 follow-up）** ← 選此
- WMOM-20260513-02 demo orchestrator simulator 接合（更大）

理由：
1. 跨 backend + frontend 一條 thin 垂直線，single-session 範圍剛好
2. 直接改善 demo 品質（運維廠商現場工程師看月報附 MR 詳情會看 SKU + name）
3. 不破壞既有 schema — 加 Optional 欄位 backward compatible

---

## 2. Scope 與設計決策

### 2.1 domain object 加 SKU/name 嗎？

不加。`MaterialRequestItem` 是 pure domain（FK 設計），加 denormalized SKU/name 會破壞 single source of truth（InventoryItem 才是 SKU/name 的主檔，改名後 MR 不可能同步）。

**決策**：domain 不動，只在 API response 層做 enrichment。frontend 收到的 response 是 view-model，含 denormalized 欄位。

### 2.2 N+1 vs batch fetch

`MaterialRequestResponse.model_validate(mr)` 8 個 call site 直接從 dataclass 對映。N+1 query（每個 item call 一次 `get_item`）對 list endpoint 災難（200 MR × 平均 3 items = 600 queries）。

**決策**：用 batch fetch。InventoryRepository 加 `get_items_by_ids(ids: list[UUID]) -> dict[UUID, InventoryItem]` — 一次 SQL `WHERE id IN (...)`。

### 2.3 router enrichment 還是 schema computed

`computed_field` 不能跨 dataclass 邊界拿外部資料。

**決策**：router 層 build response — 加 helper `_build_mr_response(mr, farm_id)` 包 `MaterialRequestResponse` 創建並用 inventory repo batch-fetch fill items。所有 8 個 call site 改用此 helper。

### 2.4 找不到 item 怎辦

理論上 MR.items 都有對應 InventoryItem（FK），但如果 item 被刪（軟刪未實作）或 farm db migration 不完整呢？

**決策**：找不到的 item，`sku/name/unit` 留 `None`（Optional 欄位本就允許）。frontend fallback 顯 `…UUID` 與既有行為一致 — 避免 backend 500 阻塞 demo。

### 2.5 frontend 顯示

`MaterialRequestDetailModal` items table 既有 columns: `料件 / 估計 / 實際 / 狀態`。改為：`SKU / 名稱 / 預估 / 實領 / 單位 / 庫存類型`（6 欄；保留 stock_kind 列方便看「領新 / 領舊 / 領維修中」）。

Wizard step 3 review 已從 picker 帶 SKU/name 顯示 — **不動**（picker subset 已展示 SKU + name 給 reviewer 看）。實際真正的 readability 痛點在 detail modal，不在 wizard。

---

## 3. 檔案異動（規劃）

### 3.1 修改

```
M modules/workflow/schemas/material_request_schemas.py     MaterialRequestItemResponse 加 sku/name/unit Optional
M modules/workflow/repository/inventory_repository.py      加 get_items_by_ids batch helper
M modules/workflow/routers/material_request_router.py      _build_mr_response helper + 替換 8 個 model_validate
M frontend/services/materialService.ts                     MaterialRequestItem type 加 sku/name/unit Optional
M frontend/components/workflow/MaterialRequestDetailModal.tsx  items table 6 欄 layout
```

### 3.2 新增

```
+ modules/workflow/tests/test_mr_item_enrichment.py        新 regression test: detail/list response 帶 sku/name/unit
+ work-logs/2026-05/2026-05-19-mr-items-sku-name.md         本檔
```

---

## 4. TODO

- [x] 建分支 + work-log
- [x] backend schema：MaterialRequestItemResponse 加 3 欄
- [x] backend repo：get_items_by_ids batch helper + MaterialRequestRepository.engine 公開 property
- [x] backend router：_build_mr_response / _build_mr_responses helper + 替換 8 個 call sites
- [x] backend regression test（5 新 test）
- [x] backend pytest zero regression（517 passed + 1 xfailed + 3 pre-existing numpy drift）
- [x] frontend types：MaterialRequestItem 加 3 Optional 欄位
- [x] frontend modal table layout 改 6 欄 + receive form label + return select 顯 SKU
- [x] frontend tsc + vite build zero regression（tsc 0 / vite 4.45s 748 modules）
- [x] code-reviewer subagent 跑（async background；must-fix 採納見 §5.3）
- [x] STATUS.yaml + ISSUES.md 更新（M4 100% 不變、issue_stats 19/36）
- [x] commit + push（PR 視 gh CLI 可用性）

---

## 5. 實作紀錄

### 5.1 完成檔案

修改（6 個檔）：
- `modules/workflow/schemas/material_request_schemas.py` — `MaterialRequestItemResponse` 加 `sku/name/unit` 三個 Optional[str] 欄位 + docstring 說明 enrich 來源
- `modules/workflow/repository/inventory_repository.py` — 加 `get_items_by_ids(item_ids) -> dict[UUID, InventoryItem]` batch helper（一次 `WHERE id IN (...)`，空 list shortcut）
- `modules/workflow/repository/material_request_repository.py` — 加 `engine` public property（給 router 共享同 farm DB engine 構 InventoryRepository）
- `modules/workflow/routers/material_request_router.py` — 加 `_build_mr_response(mr_repo, mr)` + `_build_mr_responses(mr_repo, mrs)`；8 個 `MaterialRequestResponse.model_validate(mr)` call site 全改用 helper；移除多餘 import
- `frontend/services/materialService.ts` — `MaterialRequestItem` interface 加 3 個 `string | null` 欄位
- `frontend/components/workflow/MaterialRequestDetailModal.tsx` — items table 從 4 欄擴 6 欄（`1.1fr 1.8fr 0.8fr 0.8fr 0.8fr 1fr`：SKU / 名稱 / 預估 / 實領 / 單位 / 庫存類型）；SKU 缺值 fallback `…{item_id.slice(-12)}` 維持既有行為；receive form Field label 用 `<strong>{sku}</strong> · {name}` 顯示；return form select option 走 `{sku} · {name} · est. {qty} {unit}`

新增（2 個檔）：
- `modules/workflow/tests/test_mr_item_enrichment.py` — 5 個 regression test：create / get detail / list / missing-item fallback / repo batch dedupe
- `work-logs/2026-05/2026-05-19-mr-items-sku-name.md`

### 5.2 設計決策落實

- **不污染 domain**：`MaterialRequestItem` dataclass 維持只有 FK（item_id）；enrich 只在 router 層做，schema response 端 model_copy 添加。InventoryItem 才是 sku/name/unit 主檔，未來改名不必同步 MR
- **共用 engine 避免 farm 路徑 double-resolve**：`mr_repo.engine` 公開只讀 property → `InventoryRepository(mr_repo.engine)` 直接 reuse，省一輪 FarmRegistry lookup + 避免 test factory pattern 重新改造
- **batch fetch 防 N+1**：list endpoint（200 MR × 3 items）只發一次 `WHERE id IN (...)`，靠 `_build_mr_responses` 跨整批 MR 合併 id set
- **找不到 InventoryItem fallback None 不 raise**：避免 backend 500 阻塞 demo（item 被刪 / migration 漏），frontend 顯 truncated UUID 與既有 UX 一致
- **frontend 不 break locale**：所有新文案走 `ui(en, zh)` helper 雙語

### 5.3 Code review

Code-reviewer subagent 回報 **4 must-fix + 6 should-fix + 2 nice-to-have**。本 session 第二輪 commit 採納：

**Must-fix 全採納（4/4）**：
1. ✅ #1/#2 — Test fixture `tmp_path` 雙重 resolve（雖然 pytest 同 test 內快取讓 path 一致，第一輪 5 個 test 也都通過，但模式仍 fragile） → 改 fixture 直接 yield `db_path` 給 test，移除 test 函式自己接 `tmp_path`
2. ✅ #3 — Test 存取 `inv_repo._engine` private 屬性 → 在 `InventoryRepository` 加 `engine` public property（與新增的 `MaterialRequestRepository.engine` 對稱），test 改用 `inv_repo.engine`
3. ✅ #4 — `submit_for_approval` `mr_repo.get(material_request_id)` 沒 None guard，極端 race 會 `model_validate(None)` AttributeError → 加 None guard 回 404

**Should-fix 採納（5/6）**：
- ✅ #5 — `inventory` 重複 import block 合併
- ✅ #7 — work-log §2.5 / §3.1 「5 欄」→ 「6 欄」改正（漏記 stock_kind 列）
- ✅ #8 — 加 state-transition regression test（`test_state_transition_response_keeps_enrichment`：submit_for_approval 後驗 items[0].sku 仍 enriched）
- ✅ #9 — Return form select option label `name` 為 null 時不再產生 `"GBR-001 ·  · est. 2 個"`（兩個 · 中間空字串）；改用 `[sku, name].filter(Boolean).join(' · ')`
- ✅ #10 — work-log TODO checklist 全部 mark done（commit 前完成）
- ⏭ #6 — `_build_mr_response` 的 `mr: MaterialRequest` 型別標註：#4 fix 後 caller 都保證非 None，型別維持 non-optional（不需改）

**Nice-to-have（0/2 採納）**：
- ⏭ #11 — `_build_mr_response` / `_build_mr_responses` 抽共用 `_enrich_item` helper：日後加第 4 欄再抽（YAGNI）
- ⏭ #12 — InventoryRepository.engine property — 本輪 must-fix #3 已順手補上（達到對稱），nice-to-have #12 等於同時解決

### 5.4 Build / test 驗證

- backend `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/` → **517 passed + 1 xfailed + 3 failed**
  - 3 個 failed 皆 pre-existing numpy 2.x precision drift（main baseline 一致：`test_monte_carlo_k13_seed_42` / `test_mc_percentiles_pinned` / `test_varfluct_year_1_pinned`）
  - 比 baseline 512 多 5 — 都是本 PR 新增的 `test_mr_item_enrichment.py`
  - 既有 27 個 `test_material_request_api.py` 全 pass，e2e + lifecycle ledger 全 pass — **zero regression**
- frontend `npx tsc --noEmit` → exit=0
- frontend `npx vite build` → 4.45s, 748 modules transformed, 917.11 kB (gzip 264.89 kB) — 與 A7 baseline (748 modules / 916.55 kB) +0.5 kB（合理：3 欄位 + 4 個顯示 site 微改）

---

## 6. 下次接手指南

### 已完成
- WMOM-20260518-01 backend + frontend 全收
- M4 follow-up 一條收尾（M4 milestone 仍 100%；不影響 issue_stats 開放清單但 A6 review Should-fix #4 兌現）

### 待辦（不阻塞）
- code-reviewer subagent 採納（若有 must-fix）
- PR 若 gh CLI 不可用 → 留 push 後手動開

### 建議下次 session 工作
1. **M5 規劃**（最高優先）：M4 100% + 此 follow-up done 後，下一步是 knowledge module + demo orchestrator UI；先讀 `docs/product/ROADMAP.md` M5 章節決定第一個 issue
2. **F1**（add_return 寫 ledger 沖銷，0.5d，medium priority）— 月報 material 成本會偏高，demo 給客戶看會被發現
3. **F2 / F3 / F5**（30min-1h 小修）任選一個塞進
4. **WMOM-20260513-02**（demo orchestrator simulator 接合）— 較大，1-2 工作天
