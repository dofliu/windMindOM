# 2026-05-22 WMOM-20260522-01 — F4 follow-up：work_order + reporting routers 也改用 shared FARM_REGISTRY

> **Issue**：WMOM-20260522-01 — F4 收尾
> **Branch**：`claude/issue-WMOM-20260522-01-2026-05-22`（autonomous daily worker, 5/22 20:00）
> **Goal**：把 F4 batch 沒收進去的兩個 routers（`work_order_router` + `reporting_router`）也改用 `shared/farm_registry_provider.py`；純結構整理，零行為變更

---

## 1. 為什麼今天做這個

2026-05-21 F4 batch 完成 4 個 routers（inventory / material_request / approval / cost_ledger）的 FARM_REGISTRY 共用化。實作中發現另兩個 routers 也有相同 pattern：

| Router | helper 名 | 多餘性 |
|--------|----------|-------|
| `modules/workflow/routers/work_order_router.py` | `_get_default_farm_registry` | 同 lazy singleton 模式；額外被 `_resolve_db_path_for_finish_hook` 用 |
| `modules/reporting/routers/reporting_router.py` | `_resolve_farm_db_path` | 同 4 routers 完全一樣的 lazy init + 404/500 mapping |

F4 issue 當時 scope 只列 4 個 router，沒擴大。本 issue 補完 F4 收尾。

**商業價值**：低（純 cleanup）；**讀 code 友善度**：+1（FARM_REGISTRY 共用點從 1/6 變成 1/1）。

時間估計：0.5-1h，single-session 可完工。

---

## 2. 設計決策

### 2.1 work_order_router 三處改動

**a. `_default_repository_factory`**

```python
# 原
def _default_repository_factory(farm_id: str) -> WorkOrderRepository:
    try:
        reg = _get_default_farm_registry()
    except ImportError:
        raise HTTPException(status_code=500, detail="FarmRegistry not available; ...")
    db_path = reg.get_farm_db_path(farm_id)
    if db_path is None:
        raise HTTPException(status_code=404, detail=f"Farm not found: {farm_id}")
    return get_repository(str(db_path))

# 新
def _default_repository_factory(farm_id: str) -> WorkOrderRepository:
    return get_repository(resolve_farm_db_path(farm_id))
```

shared.`resolve_farm_db_path` 已內建 404/500 error mapping。

**b. `_resolve_db_path_for_finish_hook`**

```python
# 原
def _resolve_db_path_for_finish_hook(farm_id):
    if farm_id in _overrides: return _overrides[farm_id]
    if "*" in _overrides: return _overrides["*"]
    try:
        reg = _get_default_farm_registry()
    except (ImportError, HTTPException):
        return None
    db_path = reg.get_farm_db_path(farm_id)
    return str(db_path) if db_path is not None else None

# 新
def _resolve_db_path_for_finish_hook(farm_id):
    if farm_id in _overrides: return _overrides[farm_id]
    if "*" in _overrides: return _overrides["*"]
    try:
        return resolve_farm_db_path(farm_id)
    except HTTPException:
        return None
```

**關鍵**：finish hook 失敗（FarmRegistry 沒裝 / farm 不存在）必須**安靜返回 None**（不阻擋工單收尾）— 因此 try/except HTTPException → None。shared helper 對 ImportError 和 farm-not-found 都 raise HTTPException，一個 catch 兩種都收。

**c. `set_repository_factory(None)`**

```python
# 原
def set_repository_factory(factory):
    global _repository_factory, _FARM_REGISTRY
    _repository_factory = factory
    if factory is None:
        _FARM_REGISTRY = None

# 新
def set_repository_factory(factory):
    global _repository_factory
    _repository_factory = factory
    if factory is None:
        reset_farm_registry()
```

刪 `_FARM_REGISTRY` global + `_get_default_farm_registry`。

### 2.2 reporting_router 三處改動

**a. `_resolve_farm_db_path` 整 function 刪掉**（移轉 shared 即可）

**b. `_get_ledger_repo` / `_get_wo_repo`** 改 import shared：

```python
return get_cost_ledger_repository(resolve_farm_db_path(farm_id))
return get_work_order_repository(resolve_farm_db_path(farm_id))
```

**c. `set_ledger_factory(None)` / `set_work_order_factory(None)`** 改呼叫 `reset_farm_registry()`：

`set_availability_provider` **不改** — availability provider 與 FarmRegistry 無關。

### 2.3 backward compat

純 refactor。Public API 完全不變：
- 兩 router 對外 endpoints 簽名 / 行為不變
- setter 行為一致：None → reset
- 404 / 500 error message 與原版完全一致（shared helper 已對齊）

唯一可觀察變化：**404 / 500 訊息會帶 shared helper 的訊息（"call set_*_factory()..."）**。原 work_order 訊息是 "call set_repository_factory() to inject"；shared 訊息是 "call set_*_factory() in the router to inject a mock"。兩者語意等價，前端 / test 不依賴具體字串。

### 2.4 test 影響

**現有 test 必須 zero regression**：
- `test_work_order_api.py` / `test_approval_api.py` / `test_material_request_api.py` 都用 `set_repository_factory()` 注入 mock → 不走 `_default_repository_factory` → 不會撞到 FARM_REGISTRY → 零影響
- `test_review_fixes_2026_05_09.py` 直接測 `_resolve_db_path_for_finish_hook` 的 per-farm / wildcard 邏輯 → 邏輯不變 → 零影響
- `test_reporting_api.py` 同上：用 `set_ledger_factory()` + `set_work_order_factory()` 注入 → 零影響
- F4 既有的 `tests/test_farm_registry_provider.py` 5 個 helper test → 零影響

**新加 regression test**（驗證重構正確）：
- `test_set_repository_factory_none_resets_shared_registry`：set None → 證實 shared.`_FARM_REGISTRY` 被 reset
- `test_reporting_set_ledger_factory_none_resets_shared_registry`：同上
- `test_reporting_set_work_order_factory_none_resets_shared_registry`：同上
- `test_finish_hook_silent_on_farm_registry_failure`：mock 讓 `resolve_farm_db_path` raise HTTPException → `_resolve_db_path_for_finish_hook` 應該返回 None（不 raise）

放在新檔 `modules/workflow/tests/test_f7_followup.py` + `modules/reporting/tests/test_f7_followup.py`（或 inline 進 existing）。

---

## 3. 檔案異動（規劃）

```
M modules/workflow/routers/work_order_router.py    F7：刪 _FARM_REGISTRY + _get_default_farm_registry；改 shared
M modules/reporting/routers/reporting_router.py    F7：刪 _FARM_REGISTRY + _resolve_farm_db_path；改 shared
+ modules/workflow/tests/test_f7_work_order_shared_registry.py     2 regression test
+ modules/reporting/tests/test_f7_reporting_shared_registry.py     2 regression test
M ISSUES.md                                        WMOM-20260522-01 標 done；stats open 15 / done 42
M STATUS.yaml                                      last_updated / next_milestone
+ work-logs/2026-05/2026-05-22-f4-followup-work-order-reporting.md  本檔
```

---

## 4. TODO

- [x] Read existing code（2 routers + 4 tests touching FARM_REGISTRY）
- [x] Branch + work-log
- [x] work_order_router.py 改用 shared
- [x] reporting_router.py 改用 shared
- [x] Regression tests x10（5 + 5）
- [x] backend pytest zero regression（715 pass / 3 baseline numpy drift / 2 deselected flaky concurrency）
- [x] code-reviewer subagent（1 must + 2 should + 1 nice → 全採納，should-1 out-of-scope skip）
- [x] ISSUES.md / STATUS.yaml update
- [ ] commit + push + PR（sandbox 無 gh CLI；劉老師手動開）

---

## 5. 實作紀錄

### 5.1 完成檔案

**Backend 修改（2 個檔）：**
- `modules/workflow/routers/work_order_router.py`：
  - 刪 `_FARM_REGISTRY` global + `_get_default_farm_registry()` 函式
  - 加 `from shared.farm_registry_provider import reset_farm_registry, resolve_farm_db_path`
  - `_default_repository_factory` 收成一行 `get_repository(resolve_farm_db_path(farm_id))`（原 8 行）
  - `_resolve_db_path_for_finish_hook` 用 try/except HTTPException 包 shared 呼叫（finish hook 不阻擋工單收尾的語義保留）
  - `set_repository_factory(None)` 改呼叫 `reset_farm_registry()`
- `modules/reporting/routers/reporting_router.py`：
  - 刪 `_FARM_REGISTRY` global + `_resolve_farm_db_path()` 函式
  - 加同樣 import
  - `_get_ledger_repo` / `_get_wo_repo` 直接呼叫 shared
  - `set_ledger_factory(None)` / `set_work_order_factory(None)` 各自呼叫 `reset_farm_registry()`
  - `set_availability_provider` 不動（與 farm 解析無關）

**Backend 測試新增（2 個檔，10 test）：**
- `modules/workflow/tests/test_f7_work_order_shared_registry.py` — 5 test
  - `test_set_repository_factory_none_resets_shared_registry`
  - `test_work_order_router_has_no_local_farm_registry_global`（防止後續再加回 local cache）
  - `test_finish_hook_silent_on_shared_500`（review M1：monkeypatch `resolve_farm_db_path` 直接 raise HTTPException(500)）
  - `test_finish_hook_silent_on_farm_not_found`
  - `test_finish_hook_override_takes_priority_over_shared`
- `modules/reporting/tests/test_f7_reporting_shared_registry.py` — 5 test
  - `test_set_ledger_factory_none_resets_shared_registry`
  - `test_set_work_order_factory_none_resets_shared_registry`
  - `test_set_availability_provider_none_does_not_reset_shared_registry`（守住「availability 不該動 farm」語義）
  - `test_reporting_router_has_no_local_farm_registry_global`
  - `test_get_repos_route_through_shared_when_factory_none`（review N1：production code path 真正 hit shared）

**Tracking：**
- `ISSUES.md` — WMOM-20260522-01 加 + 標 done；統計表 done 41→42 / total 56→57；改頭部 summary
- `STATUS.yaml` — last_updated 2026-05-22 / issue_stats done 41→42 / next_milestone

### 5.2 設計決策落實

- **work_order finish hook 安靜返回 None 的語義保留**：shared `resolve_farm_db_path` 對 ImportError（500）和 farm-not-found（404）都 raise HTTPException — 一個 try/except 就能同時收兩種 silent skip 條件；原 code 區分 `(ImportError, HTTPException)` 中 HTTPException 那條其實是 dead code（`_get_default_farm_registry` 不 raise HTTPException）
- **`set_availability_provider` 不動 farm registry**：availability provider 與 farm 解析在概念上獨立；切換 availability provider 不該意外清掉 farm cache 強迫所有 router 下次 lookup 重新 init。加 `test_set_availability_provider_none_does_not_reset_shared_registry` 守住這條設計意圖
- **HTTPException coupling 不擴大 scope**：review should-1 提出 shared 直接 raise HTTPException 把 framework 耦合進 shared 層。本 PR 不擴大 — 改 shared 要連動 F4 batch 的 4 routers 也跟著改，single-session 不適合（要重做 yesterday 的 work 沒必要）。Follow-up 可開新 issue。
- **`__builtins__` patch 改 monkeypatch shared function**：review M1 must-fix。原寫法 `__builtins__["__import__"]` 跨 Python interpreter / module 不一致（dict vs module），且 patch 全 process import 風險高。改 `monkeypatch.setattr(work_order_router, "resolve_farm_db_path", _always_raise_500)` 精確測試「shared raise HTTPException → finish hook 返回 None」這條 contract，不碰 import 機制
- **teardown 不重複 reset**：review should-2。原 fixture teardown `reset_farm_registry()` + `set_repository_factory(None)`（內部又會 reset）兩次呼叫；改為只呼叫 setter 一次，文件化 setter 有 side effect 的事實

### 5.3 Build / test 驗證

- `python -m pytest modules/workflow/tests/test_f7_work_order_shared_registry.py modules/reporting/tests/test_f7_reporting_shared_registry.py -v` → **10 passed in 0.73s**
- 完整 backend regression（deselect 2 個環境 flaky concurrency）：`python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ tests/ -q --deselect ...` → **715 passed + 1 xfailed + 3 pre-existing numpy drift + 2 deselected**（與 main baseline 一致）
- 與 main 對照：main 上同 deselect 設定 = 714 passed；本 PR +1（N1 production path test）= 715，**zero regression**
- 並發 dispatch test 環境 flakiness 確認（main 上 3 連跑：0/0/1 fail；本 PR 3 連跑：2/0/1 fail）— 為環境 SQLite WAL 排程不穩 + 本 PR 的 refactor 完全不碰 dispatch 邏輯，**不為本 PR 引入**

### 5.4 Code review 採納

| 級別 | # | 議題 | 修法 |
|------|---|------|------|
| Must-fix | M1 | `__builtins__` patch 不可靠 + 全 process 高危 | 改 monkeypatch `resolve_farm_db_path` 直接 raise HTTPException(500)；不碰 import 機制 |
| Should-fix | S1 | shared 依賴 HTTPException 把 framework 耦合進 shared 層 | **不採納** — 要連動修 F4 batch 4 routers，single-session 不適合擴大 scope；可開新 issue 追蹤 |
| Should-fix | S2 | teardown `reset_farm_registry()` + `set_repository_factory(None)` 重複 reset | 採納 — 只留 setter 一次（內部已 reset），fixture docstring 文件化 |
| Nice (採納) | N1 | reporting 缺 production code path 驗 shared 真有被 hit | 採納 — 加 `test_get_repos_route_through_shared_when_factory_none` 用 spy 驗證 |

無新 follow-up issue 開出（S1 不採納；M1/S2/N1 都已修在本 PR）。

---

## 6. 下次接手指南

### 已完成（push 到 origin/claude/issue-WMOM-20260522-01-2026-05-22）
- F4 batch 真正全收尾：6 個 routers（inventory / material_request / approval / cost_ledger / **work_order** / **reporting**）全部走 `shared/farm_registry_provider.py` 唯一入口
- 10 個新 regression test 守住重構不被回退
- WMOM-20260522-01 issue done；ISSUES.md / STATUS.yaml 更新

### 待辦（不阻塞，可下次再處理）
- **PR 開啟**：sandbox 無 gh CLI；劉老師收到通知後從 GitHub 介面開 PR 並 merge（branch 已 push）

### 建議下次 session 工作（依優先級）

1. **WMOM-20260504-13** cost frontend AbortController（0.25d，single-session 友善）— `useCostData.useAsync.run` 加 AbortController 防 React 18 Strict Mode dev 雙 fetch race；low risk 前端 only
2. **WMOM-20260519-01**（F1 follow-up，0.5-1d）— `add_return` 超量退料 domain guard 評估；需與劉老師 walkthrough 決定 guard 策略（domain layer vs router vs UI），**不適合 solo session**
3. **M5 規劃**：讀 `docs/product/ROADMAP.md` M5 章節決定第一個 issue（RAG knowledge module skeleton or demo orchestrator UI）；獨立 session 因 single-session 不易完整完工
4. **WMOM-20260513-02** demo orchestrator simulator 接合（2-3d 跨 session）— A10 e2e 接 simulator 一鍵 replay lifecycle，M5 demo 視覺化用
5. **可選**：F4 review S1（shared 改 raise 自家 exception，不依賴 HTTPException）— 要連動改 F4 batch 4 routers + 本 PR 兩 routers + shared，single-session 偏緊；建議獨立 session 做

