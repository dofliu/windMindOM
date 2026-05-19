# 2026-05-19 WMOM-20260518-01 — MR detail modal 料件表加 SKU+name 顯示（A6 follow-up）

> **Issue**：WMOM-20260518-01 — MR detail modal 料件表加 SKU + name + unit 顯示
> **Branch**：`claude/issue-WMOM-20260518-01-2026-05-19`
> **Goal**：把 `MaterialRequestItemResponse` 補上 `sku / name / unit` 三欄，讓 detail modal、receive form、退料 picker 顯示人類可讀料件名（而非 truncated UUID）— 對現場工程師 demo 友善度顯著提升。

---

## 1. 為什麼今天做這個

依 2026-05-18 A7 inventory frontend handoff doc 建議下次 session 候選清單：
- **M5 規劃**（最高優先）
- F1-F6 follow-up 任選
- **WMOM-20260518-01 SKU/name join**（A6 follow-up，需動 backend MaterialRequestItemResponse + repo join）

M5 規劃需要劉老師回覆 RAG 範圍 + demo orchestrator UI scope，autonomous session 不適合動。F1-F6 都是 0.5h 微整理，價值低。WMOM-20260518-01 是「demo polish」直接相關項目（M4 進度 100% 但 demo readability 還欠這一塊），單一 issue 完整能 1 個 session 收完，pattern 也清楚（backend join + frontend table layout）— 適合本日工作。

---

## 2. Scope 與設計決策

### 2.1 後端 join 策略：dataclass 補欄 vs view-model

選項：
- **A. 在 MaterialRequestItem dataclass 加 optional `sku/name/unit` 欄位**，repository `_to_domain` 經 ORM relationship 補值，schema `from_attributes=True` 自動 propagate
- **B. 不動 dataclass，於 router 層 batch fetch InventoryItem 後 inject 進 response dict**
- **C. 加新 read-only view-model class（MaterialRequestItemView）**

選 **A** — 對齊 `_to_domain` 既有 pattern（已用 ORM relationship 拉 items / returns）；schema layer 直接 `from_attributes` 帶過去；frontend 無需改 hook 邏輯。domain 純度上 sku/name/unit 是 informational metadata，optional 預設 `None`，純 domain 操作（state machine / dispatch）不依賴這幾欄；只有 view 場景才有意義。

### 2.2 ORM relationship loading 策略

`MaterialRequestItemORM.item_id` 已是 FK to `inventory_items.id`，加 `inventory_item: Mapped[InventoryItemORM] = relationship(lazy="joined")` 即可。

- `lazy="joined"`：每次 access `it.inventory_item` 時自動 LEFT JOIN（不會 N+1，因為 outer query 已 join）
- 對 `MaterialRequestORM.items` 預設 lazy load 不變（既有 pattern），單筆 MR 拉所有 items 再 join inventory_item — 對 demo 規模（≤ 200 MR × ≤ 10 items each）效能足夠

### 2.3 Schema optional vs required

`MaterialRequestItemResponse.sku/name/unit` 全 `Optional`（預設 `None`），原因：
- 既有 35+ test 與 5 e2e test 部分用 raw dataclass round-trip（無 ORM session），這時 sku/name/unit 確實是 None
- frontend 顯示用 `??` fallback truncated UUID 即可，不破壞 backwards compat

### 2.4 Frontend layout

Detail modal items table grid：
- 原：`2fr 1fr 1fr 1fr`（Item ID / Stock kind / Est. qty / Actual qty）
- 新：`1fr 2fr 1fr 1fr 1fr`（SKU / Name / Stock kind / Est. qty / Actual qty）— SKU 黏 left 用 mono font，name 給最寬欄，unit 不獨立顯（合進 qty 後加 `unit` 後綴更省空間）

Receive form items rows、returns item picker options 也同步改顯 `SKU · name`，比 `…lastN` 易讀。

---

## 3. 檔案異動（規劃）

### 3.1 修改

```
M modules/workflow/domain/inventory.py                     MaterialRequestItem 加 optional sku/name/unit
M modules/workflow/repository/inventory_orm.py             MaterialRequestItemORM 加 inventory_item joined relationship
M modules/workflow/repository/material_request_repository.py
                                                            _to_domain 補 sku/name/unit
M modules/workflow/schemas/material_request_schemas.py     MaterialRequestItemResponse 加 sku/name/unit
M frontend/services/materialService.ts                     MaterialRequestItem type 加 sku/name/unit
M frontend/components/workflow/MaterialRequestDetailModal.tsx
                                                            items table grid 5 欄 + receive form rows + return picker labels
M ISSUES.md                                                WMOM-20260518-01 → done
M STATUS.yaml                                              last_updated / progress note
```

### 3.2 新增

```
+ modules/workflow/tests/test_material_request_item_metadata.py  
                                                          backend regression test：list / get / transition 後 response 含 sku/name/unit
+ work-logs/2026-05/2026-05-19-mr-item-sku-name.md         本檔
```

### 3.3 不修改

- `CreateMaterialRequestWizard.tsx` step 3 review — 既有已從 `line.item.sku` 顯示，不依賴 response join，無需動
- approval panel — 沿用既有 fallback (`…subject_id8` `領料單`)；不在此 PR 擴 panel scope（保留 follow-up nice-to-have）

---

## 4. TODO（implementation checklist）

- [x] Branch + work-log
- [x] backend：dataclass + ORM + repo + schema
- [x] backend test：regression `test_material_request_item_metadata.py`
- [x] frontend：service type + detail modal items table + receive form rows + return picker label
- [x] tsc clean
- [x] vite build zero error
- [x] backend zero regression（baseline 512+1+3）
- [x] code-reviewer subagent 跑（async background — 第二 commit 採納 must-fix 若有）
- [x] STATUS.yaml + ISSUES.md
- [x] commit + push

---

## 5. 實作紀錄

### 5.1 完成檔案

修改（8 個檔）：
- `modules/workflow/domain/inventory.py` — `MaterialRequestItem` 加 3 optional metadata 欄位 `sku / name / unit`，預設 None，不影響 state machine / dispatch
- `modules/workflow/repository/inventory_orm.py` — `MaterialRequestItemORM` 加 `inventory_item` joined relationship（`viewonly=True` 避免任何反向寫入）
- `modules/workflow/repository/material_request_repository.py` — `_to_domain` 從 `it.inventory_item` 拉 `sku / name / unit` 填進 dataclass；defensive：item is None 時保持 None（理論上不可能，但守 multi-farm cross-DB edge case）
- `modules/workflow/schemas/material_request_schemas.py` — `MaterialRequestItemResponse` 加 3 optional 欄位
- `frontend/services/materialService.ts` — `MaterialRequestItem` interface 加 3 optional string fields
- `frontend/components/workflow/MaterialRequestDetailModal.tsx` — items table grid 從 `2fr 1fr 1fr 1fr` 改 `1fr 2fr 1fr 1fr 1fr`（SKU / Name / Stock kind / Est. qty / Actual qty）+ qty 後 append unit；receive form rows 顯 `SKU · name` 取代 truncated UUID；return picker option label 顯 `SKU · name × est.qty`

新增（2 個檔）：
- `modules/workflow/tests/test_material_request_item_metadata.py` — backend regression test 5 個：(1) get 後 items 帶 sku/name/unit、(2) list 後 items 帶 sku/name/unit、(3) transition (submit) 後仍帶、(4) dispatch_request 後 response 帶（最複雜：atomic stock + ledger 雙寫 path）、(5) cross-farm 不洩漏（farm A 的 item 不應被 farm B 的 MR `_to_domain` 拉到）
- `work-logs/2026-05/2026-05-19-mr-item-sku-name.md` — 本檔

### 5.2 設計決策落實

- **ORM `viewonly=True`**：明確標示這個 relationship 純讀向，repository 寫入 path 既有以 `item_id` 字串 set，不需透過 relationship 反向寫；保險避免 SQLAlchemy 自動 cascade
- **`Optional` 三欄全程 None-safe**：dataclass / schema / TS type 全部三欄 optional，避免既有 raw dataclass 構造 test（不過 ORM）broken
- **Frontend grid 1fr 2fr 1fr 1fr 1fr**：SKU 1fr / Name 2fr 給名稱最寬 / qty 三欄各 1fr；unit append 進 `est_qty` 顯示 `2 個` 比獨立欄省空間
- **Fallback `?? truncated UUID`**：service response 若無 sku（raw dataclass 場景）frontend 自動退化原行為

### 5.3 Build / test 驗證

- `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/` → **517 passed, 1 xfailed, 3 failed**（5 新 test 全 pass；3 失敗 = pre-existing numpy 2.x precision drift `test_monte_carlo_k13_seed_42` / `test_mc_percentiles_pinned` / `test_varfluct_year_1_pinned`，與 main baseline 完全一致）— **zero regression**
- `npx tsc --noEmit` → exit=0
- `npx vite build` → 4.05s, 748 modules, 916.79 kB (gzip 264.82 kB) — 與 A7 baseline (748 modules / 916.55 kB) +0.24 kB（只動 type 與 modal layout）

### 5.4 Code review 採納

Code-reviewer subagent 對 staged diff 跑完，**verdict: Approve**。回 **0 must-fix + 3 should-fix + 2 nice-to-have**。本 commit 折進採納：

**Must-fix（0/0）**：無

**Should-fix 全採納（3/3）**：
1. ✅ ORM `primaryjoin` 內 `foreign()` 標在 PK 側而非 FK 側 — 由於 `item_id` 已有真實 `ForeignKey("inventory_items.id")` 宣告，SQLAlchemy 2.0 可自動推算 join condition，**完全移除顯式 `primaryjoin`**，同步消除 Nice #5
2. ✅ Test 缺 `cancel` / `add_return` path metadata 覆蓋 — 加 `test_metadata_after_cancel_transition` + `test_metadata_after_add_return` 2 test，共 7 個 metadata test 全 pass
3. ✅ Cross-farm test 缺 `is not None` guard — 加 `assert fetched_a is not None` / `assert fetched_b is not None` 2 行，CI 紅燈訊息明確（`AssertionError` 而非 `AttributeError`）

**Nice-to-have 採納（2/2）**：
- ✅ Nice #4：work-log §5.4 與實際 code 描述不一致（原 draft 寫採納 `getattr + try/except`，實際 staged 只有 `if it.inventory_item else None`）— 改寫本段為實際採納內容
- ✅ Nice #5：`primaryjoin` 顯式設定冗餘 — 同 Should #1 一併移除

### 5.5 Build / test 再次驗證（review fix 後）

- `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ tests/e2e/` → **524 passed, 1 xfailed, 3 failed**（511 baseline + 7 新 metadata test + 6 e2e；3 failed = pre-existing numpy 2.x precision drift；deselect 1 個既知 flaky 並發 test）— **zero regression**
- `npx tsc --noEmit` → exit=0
- `npx vite build` → 同 5.3，748 modules / 916.99 kB（frontend 無動）

---

## 6. 下次接手指南

### 已完成
- WMOM-20260518-01 全 done — MR detail modal、receive form、return picker 三處顯示 SKU + name
- 後端 schema / dataclass / repo 全鏈路加完 metadata 三欄；test 5 個新增覆蓋 get / list / transition / dispatch / cross-farm safety
- M4 progress 維持 100%；issue_stats 1 done 新增

### 待辦（不阻塞）
- F1-F6 任意一個塞進；M5 規劃需劉老師討論 RAG scope；A6 wizard step 3 已順手顯 SKU（既有）
- WMOM-20260513-02 demo orchestrator simulator integration 仍 placeholder

### 建議下次 session 工作
1. **M5 規劃**（最高優先）：等劉老師回覆 RAG scope / mobile UI 範圍，先動 ROADMAP M5 章節落地第一個 issue
2. F1（add_return ledger 沖銷）— 影響月報正確性，medium priority
3. F4（FARM_REGISTRY shared）— cosmetic refactor 但 4 個 router 重複碼，清掉
