# 2026-05-19 WMOM-20260518-01 — MR detail items 加 SKU + name + unit（A6 follow-up）

> **Issue**：WMOM-20260518-01 — `MaterialRequestItemResponse` 加 `sku/name/unit`，後端 join、前端 detail modal items table 與 wizard review step 顯示
> **Branch**：`claude/nice-brown-kJDox`（autonomous daily worker session 指派）
> **Goal**：消滅 MR detail items table 只顯 truncated UUID 的 readability 黑洞，補完 A6 review Should #4 留下的 follow-up

---

## 1. 為什麼今天做這個

2026-05-18 inventory frontend handoff doc 列今日候選 3 條：
- M5 規劃（最大，但需先讀 ROADMAP M5 章節 + 決定第一個 issue，single session 不易完成）
- F1-F6 follow-up（皆小修，價值有限）
- **WMOM-20260518-01**（0.5d，A6 直接 follow-up）

WMOM-20260518-01 是 single-session 落地剛好的中型任務：
- backend 改一個 schema + 一個 repo helper + 9 個 router call site
- frontend 改一個 service type + 一個 detail modal items table + wizard review step
- 對 demo readability 立即有感（現場工程師看到 SKU 比 UUID 直觀百倍）

---

## 2. 設計決策

### 2.1 enrichment 放哪一層？

選項：
- **A. 在 domain 層擴 `MaterialRequestItem`** 加 sku/name/unit — 污染 domain（這些屬於 InventoryItem）
- **B. 在 ORM 層 `joinedload` MaterialRequestItemORM → InventoryItemORM** 改 relationship，`_to_domain` 直接拿 — schema 動到，scope creep
- **C. 在 router 層 batch fetch 後合併** — 最 minimal invasive，response-only enrichment

選 **C**。理由：sku/name/unit 是 view-projection（給 frontend 看），不是 MR 本身屬性，留在 response builder 收尾最乾淨。

### 2.2 batch resolver 放哪？

兩個 repo 共用同一 engine（同 farm DB），所以 `MaterialRequestRepository` 直接用內部 engine 查 `inventory_items` 表是合理的（dispatch_request 已經這麼做）。

加 `resolve_item_metadata(item_ids: Iterable[UUID]) -> dict[UUID, ItemMetadata]`：
- batch `SELECT id, sku, name, unit FROM inventory_items WHERE id IN (...)`
- 回 dict；missing item → key 不存在（不 raise，view layer 顯 fallback）

### 2.3 router 怎麼用？

加 helper `_build_mr_response(mr, repo) -> MaterialRequestResponse`：
1. `resp = MaterialRequestResponse.model_validate(mr)`（既有 path）
2. `meta = repo.resolve_item_metadata([it.item_id for it in mr.items])`
3. for each `it_resp in resp.items`：如 `meta` 有對應 row 就填 sku/name/unit

list endpoint 用同 helper 但 batch（一個 list call → 一次 union 所有 items 的 item_id 集合 → 一次 SQL）

### 2.4 schema 欄位 nullable 還是 required？

選 **Optional[str] = None**（向後相容）：
- 既有測試 fixture 不一定建 inventory_item 對應 row（如 sigil mock data）
- 真實 production data drift 也可能讓某 item 被刪 / 找不到（不該 crash response）

### 2.5 frontend 改動範圍

只改 **MR detail modal items table** 與 **wizard step 3 review**：
- detail modal: `SKU | name | qty | actual | unit` 新 layout
- wizard step 3 review: 顯示 `{sku} {name}` 比 truncated UUID 直觀
- wizard step 2 picker 已用 `useInventoryItems` 拿到完整 InventoryItemSummary（已有 sku/name），**不改**

---

## 3. 檔案異動（規劃）

### 3.1 修改 backend

```
M modules/workflow/schemas/material_request_schemas.py     MaterialRequestItemResponse 加 sku/name/unit Optional
M modules/workflow/repository/material_request_repository.py  加 resolve_item_metadata + ItemMetadata dataclass
M modules/workflow/routers/material_request_router.py      加 _build_mr_response helper + 9 個 call site 改用
+ modules/workflow/tests/test_mr_item_metadata.py          新測試（4-5 個 case）
```

### 3.2 修改 frontend

```
M frontend/services/materialService.ts                    MaterialRequestItemResponse type 加 sku/name/unit?: string
M frontend/components/workflow/MaterialRequestDetailModal.tsx  items table layout 改 5 欄 SKU | Name | Qty | Actual | Unit
M frontend/components/workflow/CreateMaterialRequestWizard.tsx  step 3 review 顯示 SKU + name（picker 已有，這裡只改顯示）
```

### 3.3 修改 tracking

```
M ISSUES.md         WMOM-20260518-01 → done；issue_stats open 20→19 / done 35→36
M STATUS.yaml       last_updated / next_milestone
+ work-logs/2026-05/2026-05-19-mr-item-sku-name.md  本檔
```

### 3.4 不修改

- domain layer（`MaterialRequestItem` 不加屬性）
- ORM layer（不加 relationship / joinedload）
- materialService `inventoryApi` picker subset（已有完整 sku/name，不動）

---

## 4. TODO

- [x] Read existing code（schema / repo / router / detail modal）
- [x] Branch + work-log
- [x] backend schema 加 Optional sku/name/unit
- [x] backend repo `resolve_item_metadata` + `ItemMetadata` dataclass
- [x] backend router `_build_mr_response` helper + 改 9 call sites
- [x] backend tests for new helper + 不破壞既有 35+ MR + 5+ e2e tests（9 new tests）
- [x] frontend type 加 sku/name/unit?
- [x] frontend detail modal items table 改 6 欄（含 fallback UUID）
- [x] frontend receive form + returns dropdown 改顯 SKU·name
- [x] frontend wizard step 3 review 顯 SKU + name + unit
- [x] tsc clean / vite build 3.57s 748 modules 917.15 kB
- [x] backend pytest zero regression（526 pass + 1 xfailed + 3 numpy drift + 1 flaky）
- [x] code-reviewer subagent + 採納 3 must-fix + 3 should-fix + 2 nice-to-have（全採納）
- [x] ISSUES.md / STATUS.yaml update
- [ ] commit + push + PR

---

## 5. 實作紀錄

### 5.1 完成檔案

**Backend 修改（4 個檔）：**
- `modules/workflow/schemas/material_request_schemas.py` — `MaterialRequestItemResponse` 加 `sku/name/unit: Optional[str] = None`
- `modules/workflow/repository/material_request_repository.py` — 加 `ItemMetadata` frozen dataclass + `resolve_item_metadata(item_ids: Iterable[UUID]) -> dict[UUID, ItemMetadata]`（一次 batch SQL）
- `modules/workflow/repository/__init__.py` — re-export `ItemMetadata`
- `modules/workflow/routers/material_request_router.py` — 加 3 個 helper（`_enrich_items` / `_build_mr_response` / `_build_mr_list_response`）+ 換 9 個 endpoint call site

**Backend 測試新增（1 個檔，9 test）：**
- `modules/workflow/tests/test_mr_item_metadata.py` — repo 3（resolve / empty / missing item）+ router CRUD 3（create / get / list）+ transition smoke 2（4-state lifecycle + cancel）+ data drift 1

**Frontend 修改（3 個檔）：**
- `frontend/services/materialService.ts` — `MaterialRequestItem` 加 `sku/name/unit?: string | null`
- `frontend/components/workflow/MaterialRequestDetailModal.tsx` — items table 4 欄 → 6 欄；receive form label + returns Select option 改顯 SKU·name
- `frontend/components/workflow/CreateMaterialRequestWizard.tsx` — step 3 review 顯 `SKU · name × qty unit · stock_kind`（移除 InventoryItemSummary 非 nullable 欄的多餘 null guard）

### 5.2 設計決策落實

- **enrichment 放 router 層**（不污染 domain；不動 ORM relationship）— `MaterialRequestItem` dataclass 維持原樣
- **pure-function enrichment 用 `model_copy(update=...)`**（不 mutate Pydantic instance）— code review must-fix #1，未來若 schema 加 `frozen=True` 也不會悄悄失效
- **batch fetch by IN clause**：list endpoint 一次 union 所有 mrs 的 item_ids 後單次 SQL 取 metadata，避免 N+1
- **data drift fallback**：缺漏 item_id → key 不在 dict → schema 已宣告 Optional 自動成 None；前端顯示 fallback truncated UUID + monospace + `title={item_id}`
- **transaction boundary**：metadata fetch 與 mr fetch 在不同 session，非 transactional — view-projection only，已在 `_build_mr_response` docstring 註明（code review must-fix #2）

### 5.3 Build / test 驗證

- `npx tsc --noEmit` → exit=0
- `npx vite build` → 3.57s, 748 modules transformed, 917.15 kB（gzip 264.94 kB；與 A7 baseline 916.55 kB +0.6 kB — 合理：3 個 components 加 SKU/name 顯示）
- `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ tests/e2e/` → **526 passed (+9 new), 1 xfailed, 4 failed**（3 pre-existing numpy drift + 1 flaky concurrency；與 main baseline 同 — **zero regression**）

### 5.4 Code review 採納

Code-reviewer subagent 找出 **3 must-fix + 3 should-fix + 2 nice-to-have**，**全 8 採納**：

| 級別 | # | 議題 | 修法 |
|------|---|------|------|
| Must-fix | 1 | Pydantic attribute mutation 若 schema 加 frozen=True 會悄悄失效 | 改用 `model_copy(update=...)` 並抽 `_enrich_items` pure helper |
| Must-fix | 2 | enrichment 與 mr fetch 跨 session 非 transactional | docstring 註明 view-projection-only 邊界 |
| Must-fix | 3 | transition endpoints（dispatch/receive/close/cancel）缺 enrichment smoke test | 加 `test_full_transition_chain_responses_carry_sku_name_unit` + `test_cancel_response_carries_sku_name_unit` |
| Should-fix | 1 | `Iterable[UUID]` 語義不明 | docstring 註明「只消費一次」 |
| Should-fix | 2 | 測試裸用 `sqlite3` 繞 ORM | import 移頂層 + 註解 SQLite-only（PG 切換見 WMOM-20260509-F6） |
| Should-fix | 3 | grid SKU 欄寬度 1fr 太窄 | 改 1.2fr |
| Nice | 1 | `_build_mr_list_response` 空 list 早 return | 加 `if not mrs: return ...` |
| Nice | 2 | wizard 多餘 null guard | 移除（`InventoryItemSummary.name/unit` 為 required string） |

無 follow-up 新 issue 開出。

---

## 6. 下次接手指南

### 已完成
- WMOM-20260518-01：MR detail modal items table + receive form + returns dropdown + wizard review 全切到 SKU+name+unit 顯示
- Backend repo 加 `resolve_item_metadata` batch fetch helper（給未來 reporting / 警報 module 也可用）
- 9 個新 test，含 data drift 場景（item 刪除後不 crash）

### 待辦（不阻塞）
- PR 由本 session push 後若 gh CLI 不可用，劉老師人工開
- F1-F6 follow-up 5 個小修（皆 0.5h-0.5d）
- WMOM-20260513-02 demo orchestrator simulator 接合（M5 demo 視覺化用）

### 建議下次 session 工作
1. **F1-F6 小修一次清掉**（5 個 0.5h-0.5d，可一個 session 全做完）：
   - F1 `add_return` 寫 ledger 沖銷（最高商業價值）
   - F2 `list_items` / `list` 用 `func.count` 而非 Python `len`
   - F3 `list_warehouses` 加 repo method
   - F4 `_FARM_REGISTRY` lazy singleton 抽 shared
   - F5 `InventoryAdjustmentLog.actor_id` 改 Optional
2. **M5 規劃**：讀 `docs/product/ROADMAP.md` M5 章節決定第一個 issue（RAG knowledge module skeleton 或 demo orchestrator UI 完整版）
3. **WMOM-20260513-02 demo orchestrator simulator**：A10 e2e 接 simulator 一鍵 replay lifecycle

