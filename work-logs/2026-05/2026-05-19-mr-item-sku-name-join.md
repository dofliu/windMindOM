# 2026-05-19 WMOM-20260518-01 — MR detail modal 料件表加 SKU+name 顯示（A6 follow-up）

> **Issue**：WMOM-20260518-01 — MR detail items 加 SKU/name/unit join
> **Branch**：`claude/issue-WMOM-20260518-01-2026-05-19`
> **Goal**：`MaterialRequestItemResponse` 補上 `sku / name / unit` 三欄；
> Repository `_to_domain` 在同 session 內 batch fetch inventory_items；
> Frontend MR detail modal items table 改 layout（SKU + name + 數量 + actual + unit），
> 也順手把 CreateMaterialRequestWizard step 3 review 區顯示改成 SKU + name。

---

## 1. 為什麼今天做這個

依 2026-05-18 inventory frontend (A7) handoff 推薦清單，M4 已 100% 完成主要功能。
剩下候選：
- M5 規劃（太 open-ended，不適合單日 autonomous session）
- **WMOM-20260518-01 SKU+name join**（concrete、isolated、demo 友善）← 選此
- F1-F6 follow-up 小修
- WMOM-20260513-02 demo orchestrator simulator 接合

WMOM-20260518-01 是 A6 code review should-fix #4 留下的 follow-up，demo 給現場
工程師看時顯 `…{uuid_tail_12}` 完全無 readability，補上 SKU+name 直接改善 PMF
demo 力。範圍清楚（後端 schema + 後端 repo 一個 join + 前端 detail modal + wizard
review 兩處），可在單 session 完成 + 寫 regression test。

---

## 2. Scope 與設計決策

### 2.1 join 放哪一層？

選項：
- **A. Router 層 batch fetch + manual construct** — 不動 domain，router 後處理
- **B. Repository `_to_domain` 同 session JOIN，把 sku/name/unit 寫進 dataclass**
- **C. 新增 enriched `MaterialRequestItemView` 型別放 schema 層** — over-engineered

選 **B**：
- `_to_domain` 已經跑同個 SQLAlchemy session，加一個 `select(InventoryItemORM)` batch fetch 成本低
- domain `MaterialRequestItem` 加 3 個 `Optional[str]` 欄位（default None），creation flow 不需填
- router 仍可直接 `MaterialRequestResponse.model_validate(mr)` —— 不需動
- `MaterialRequestItem` 已經帶有 `stock_kind` / `actual_qty` 等操作性欄位，再加幾個 denormalized lookup 不算汙染

### 2.2 為什麼 Optional 而非 required？

- 既有 unit test 直接 `MaterialRequestItem(request_id=..., item_id=..., estimated_qty=N)` 建立（無 db），如果 required 會大量 fail
- 純 domain logic（state machine、invariants）不需 SKU/name —— 留 None 是正確語意
- 只有從 DB 讀回時才會被 populate

### 2.3 N+1 vs batch

`MaterialRequestORM.items` 已是 relationship list，`_to_domain` 一次 fetch 一個 MR
通常 ≤ 10 個 items；用一個 `select(...).where(id.in_(item_ids))` batch fetch 即可，
避免 N+1。

### 2.4 frontend 顯示順序

依 issue acceptance：`SKU | name | qty | actual | unit`。我用 grid 重排既有
items table layout。Items 沒對到 InventoryItem 時（理論上不會發生，但 stale data
case），顯 `—` 不 break UI。

### 2.5 不做

- **不動 dispatch ledger note** — `note=f"item={it.item_id} ..."` 仍用 UUID，
  避免動 ledger 既有 35+ tests 的 string match assertion。SKU 顯示是 frontend
  responsibility。
- **不動 `MaterialReturnResponse`** — 退料 dialog 不顯料件 list（user 從現有
  MR items 選），不需要 enriched view。
- **不動 picker (CreateMaterialRequestWizard step 2)** — picker 已從
  inventoryService 拉 InventoryItemSummary（已含 sku+name+unit），無問題

---

## 3. 檔案異動（規劃）

### 3.1 新增

```
+ work-logs/2026-05/2026-05-19-mr-item-sku-name-join.md
+ modules/workflow/tests/test_mr_item_sku_name.py    regression test（domain Optional 欄位 + repo join + response schema）
```

### 3.2 修改

```
M modules/workflow/domain/inventory.py                 MaterialRequestItem 加 Optional[str] item_sku/item_name/item_unit
M modules/workflow/schemas/material_request_schemas.py MaterialRequestItemResponse 加同 3 欄
M modules/workflow/repository/material_request_repository.py
                                                       _to_domain 加 batch fetch inventory_items 注入 sku/name/unit
M frontend/services/materialService.ts                 MaterialRequestItemResponse type 加 sku/name/unit
M frontend/components/workflow/MaterialRequestDetailModal.tsx
                                                       items table 改 layout: SKU | name | qty | actual | unit
M frontend/components/workflow/CreateMaterialRequestWizard.tsx
                                                       step 3 review 區改顯 SKU + name（既有 picker 已有資料，用 cart 內 lookup）
M ISSUES.md                                            WMOM-20260518-01 → done
M STATUS.yaml                                          progress、last_updated、next_milestone
```

---

## 4. TODO

- [x] domain dataclass 加 3 欄
- [x] schema response 加 3 欄
- [x] repo `_to_domain` batch fetch + populate
- [x] regression test
- [x] frontend type
- [x] frontend detail modal layout
- [x] frontend wizard review
- [x] tsc clean
- [x] vite build
- [x] backend full zero regression
- [x] code-reviewer subagent + must-fix / should-fix 採納
- [x] STATUS.yaml + ISSUES.md
- [x] commit + push + PR

---

## 5. 實作紀錄

### 5.1 完成檔案

新增（2 個檔）：
- `modules/workflow/tests/test_mr_item_sku_name.py` — 14 個 regression test：domain Optional 欄位（2）+ 6 條 read paths（create / get / get_by_business_key / list / list_for_work_order / transition）+ dispatch_request + multi-items 配對 + schema 序列化（含 None 場景）+ helper edge case `_fetch_item_info_map` 空 list / 空 items
- `work-logs/2026-05/2026-05-19-mr-item-sku-name-join.md`

修改（6 個檔）：
- `modules/workflow/domain/inventory.py` — `MaterialRequestItem` 加 `item_sku / item_name / item_unit: str | None = None`，docstring 註明 read-model 用途、不破壞既有 unit test 純 domain 建構
- `modules/workflow/schemas/material_request_schemas.py` — `MaterialRequestItemResponse` 加同 3 欄 `Optional[str]`，docstring 註明從 InventoryItem join
- `modules/workflow/repository/material_request_repository.py` — 新增 `_fetch_item_info_map(sess, mr_orms) -> dict[str, tuple[str|None, str|None, str|None]]` 一次 IN 查詢；`_to_domain` 加 `item_info_map` kwarg；7 處 callers（_create_once / get / get_by_business_key / list / list_for_work_order / transition / dispatch_request）改為先 fetch 再 pass map
- `frontend/services/materialService.ts` — `MaterialRequestItem` interface 加 3 欄
- `frontend/components/workflow/MaterialRequestDetailModal.tsx` — items table 從 4 欄改 6 欄 grid（SKU | name | qty | actual | unit | stock_kind）；receive form label 從 `…{uuid8}` 改顯 `SKU · name (預估 N unit)`；return-item dropdown label 同樣顯 SKU + name
- `frontend/components/workflow/CreateMaterialRequestWizard.tsx` — step 3 review 區的 cart preview 從 `{sku} × {qty} · {stock_kind}` 補完 `{sku} · {name} × {qty} {unit} · {stock_kind}`

### 5.2 設計決策落實

- **read-model 走 domain Optional 欄位**：與 Alt-A（router 後處理）比，cost 是 domain 多 3 個 None 欄位，但 schema 仍用 `model_validate(mr)` 一行就回，不需動 router；且 6 條 read path 統一在 repo 收口
- **batch fetch via IN**：`_fetch_item_info_map` 一個 query 處理 list 內所有 MR 的 items，避免 N+1
- **空 list guard**：`if not item_ids: return {}` 防 IN-empty SQL 行為
- **type 用 `str | None` tuple**：對應 InventoryItemORM 雖然目前 NOT NULL 但 defensive 不誤導 mypy
- **transition 內 info reuse**：state machine + 出境 return 共用同個 info map，加 comment 明示 sku/name/unit 是 immutable inventory metadata
- **frontend fallback SKU=null → `…{uuid8}`**：保留原本 8 字 tail 一致性（review #5），不混用 12 字
- **不動 ledger note**：dispatch 的 ledger entry `note=f"item={uuid} ..."` 保留 UUID（既有 35+ test 字串 match assertion），SKU 顯示是 frontend 責任

### 5.3 Build / test 驗證

- `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ tests/` →
  **672 passed, 1 xfailed, 3 failed**（與 main baseline `658 + 1 xfailed + 3 failed` 完全一致：3 個 pre-existing numpy 2.x precision drift；本 PR 新增 14 test 全綠）— **zero regression**
- `npx tsc --noEmit` → exit=0
- `npx vite build` → 3.67s, 748 modules, 917.06 kB (gzip 264.85 kB)；對比 A7 baseline `916.55 kB` +0.51 kB（合理：3 個欄位 + 6 欄 grid + receive label 等小幅 string template 增量）

### 5.4 Code-reviewer 採納

Code-reviewer subagent 跑出 **1 must-fix + 4 should-fix + 1 nice-to-have**。本 session 一次全採納（單 commit）：

**Must-fix（1/1）**：
1. ✅ #1：dispatch_request read path 漏測 — 補 `test_dispatch_request_returns_items_with_sku`：建單 → submit_for_approval → approve_all → `dispatch_request` 後檢查 SKU/name/unit 帶回。需要 `import modules.cost.repository.cost_ledger` 觸發 ORM 註冊 cost_ledger_entries table（既有 test_dispatch_atomic_transaction 同樣 pattern）

**Should-fix（4/4）**：
- ✅ #2：transition 內 info reuse 加 comment 明示「InventoryItem metadata 在同 transaction 內 immutable」
- ✅ #3：`_fetch_item_info_map` 回傳 type 從 `tuple[str, str, str]` 改 `tuple[str | None, str | None, str | None]` 對應 ORM 欄位真實 nullability
- ✅ #4：補 `test_fetch_item_info_map_empty_mrs_returns_empty` + `test_fetch_item_info_map_mrs_with_no_items_returns_empty` — guard 不被未來 refactor 不慎拔掉
- ✅ #5：detail modal 改回用 `slice(-8)` fallback（與 return dropdown 一致；本 PR 原本用 12 個字 inconsistent）

**Nice-to-have（1/1）**：
- ✅ #6：work-log TODO 全打勾 + 補上實作紀錄

---

## 6. 下次接手指南

### ⚠ 重要：本 issue 已有兩個 open PR（劉老師要選一個 merge）

Push 階段才發現 **同一 issue WMOM-20260518-01 已有 2 個 open PR**（同日早班並行 session 產出）：

| PR | Branch | 作法 | Test 數 | Code review 結論 |
|----|--------|------|---------|----------------|
| **#37**（07:57 UTC） | `claude/issue-WMOM-20260518-01-2026-05-19` | ORM `viewonly` relationship + `lazy="joined"`；改 `inventory_orm.py` | 7 | 0 must-fix + 3 should-fix（全採納）+ 2 nice-to-have（全採納）；verdict: Approve |
| **#38**（08:56 UTC） | `claude/nice-brown-kJDox` | Router 層 `_enrich_items` 用 pydantic `model_copy(update=...)`；公開 `MaterialRequestRepository.resolve_item_metadata` | 9 | 3 must-fix + 3 should-fix + 2 nice-to-have 全 8 採納 |
| **本 session** | `claude/nice-brown-Qg9KM`（推上 remote，**未開 PR**） | Repository `_to_domain` 加 batch fetch helper `_fetch_item_info_map` + `item_info_map` kwarg；domain dataclass 加 3 Optional 欄 | 14 | 1 must-fix + 4 should-fix + 1 nice-to-have 全 6 採納 |

**決定不開第 3 個 PR**：同 issue 三條 patch 撞在一起讓 reviewer 重複工作。本 session 的 commit 已 push 到 `claude/nice-brown-Qg9KM` (commit `33dc3fe`) 作為第 3 條 approach 參考，劉老師可比較三條後選一條 merge、close 其他 2 條。

### 三條 approach 比較（給劉老師參考）

| 維度 | PR #37 (ORM viewonly) | PR #38 (router enrichment) | 本 session (repo batch fetch) |
|------|---------------------|--------------------------|----------------------------|
| **抽象層次** | ORM | Router | Repository |
| **改 ORM model?** | 是 | 否 | 否 |
| **改 router?** | 否 | 是（9 endpoint call sites） | 否 |
| **改 domain dataclass?** | 是 | 否 | 是 |
| **N+1 防護** | `lazy="joined"` 全自動 | 一次 `IN` 查詢 | 一次 `IN` 查詢 + 含空集合 guard |
| **新 helper 暴露** | 無 | `resolve_item_metadata` 公開 | `_fetch_item_info_map` 為 private static |
| **data drift fallback** | join 失敗→None | 顯式 fallback | 顯式 fallback |
| **multi-tenant 隔離 test** | 有 | 無 | 無（依賴 farm-scoped db_path） |
| **dispatch_request test** | 有 | 有 | 有 |
| **multi-items 配對 test** | 部分 | 部分 | 有（明確驗證不同 sku 對到不同 item） |
| **empty-IN guard test** | 無 | 無 | 有 |
| **Schema serialize None test** | 無 | 無 | 有 |

**主觀建議**：PR #38（router enrichment）與本 session 都把改動量收在 schema/router/repo helper 層、不動 ORM relationship，比 PR #37 改動風險小。PR #38 的 `model_copy(update=...)` 對未來 schema `frozen=True` 較安全；本 session 的 repo-層 collect 對 N+1 控制更直接（map 在 list path 一次共用）。三條 frontend 顯示行為等價。

### 已完成

- M4 demo flow：MR 詳情、領料 receive form、退料 dropdown、wizard review 區全顯 SKU+name+unit
- Backend regression test 14 個全綠，6 條 read paths 全覆蓋
- 三條 approach 之一已 push 到 `claude/nice-brown-Qg9KM`，劉老師可選

### 待辦（不阻塞）

- **劉老師抉擇**：PR #37 / PR #38 / 本 session branch (`claude/nice-brown-Qg9KM`)，3 選 1 merge 後 close 其他 2 條
- M5 規劃（最高優先）：M4 完整 demo flow 已通
- F2-F6 follow-up
- WMOM-20260513-02 demo orchestrator simulator 接合（A10 follow-up）

### 建議下次 session 工作

1. **不要再做 WMOM-20260518-01 第 4 條 PR** — 等劉老師選
2. **M5 規劃**：讀 `docs/product/ROADMAP.md` M5 章節決定第一個 issue
3. **F2 / F3 任選**：F2 用 `func.count` 改 list 計數 / F3 `list_warehouses` 移出 router raw SQL — 都是 1h 內小修

### Daily worker 流程改善建議

未來 session 應在 Claim phase 多一步：
- **`mcp__github__list_pull_requests` 看是否有同 issue 已 open 的 PR**
- 若有 open PR for 同 issue → 跳過該 issue 挑下一個

這次因為 ISSUES.md WMOM-20260518-01 仍 `Status: open`（PR #37/#38 還沒 merge），daily worker 仍合理認為可以做，但實際上同 issue 已 in-flight — 多做第 3 個浪費 reviewer 時間。

---

## 7. 提交給劉老師的訊息

> 早班兩條 session（07:57 / 08:56 UTC）各自為 WMOM-20260518-01 開了 PR #37 / #38；
> 我（20:00 UTC daily worker）開工前沒檢查 GitHub PR 狀態就動工，做完後才發現有並行。
> 為避免再開第 3 個 PR 製造 noise，commit 已 push 到 `claude/nice-brown-Qg9KM` (`33dc3fe`) 保留作為第 3 條 approach 參考；**未開 PR**。
> 請從 #37 / #38 / `claude/nice-brown-Qg9KM` 三選一 merge，close 其他 2 條。
> 三條 approach 比較表見上方 §6。

---
