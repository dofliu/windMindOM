# 2026-05-22 WMOM-20260522-01 — F4 follow-up：work_order + reporting routers 收尾

> **Issue**：WMOM-20260522-01 — F4 後續清掉 `work_order_router.py` + `reporting/routers/reporting_router.py` 殘留的 `_FARM_REGISTRY` 重複 pattern
> **Branch**：`claude/blissful-turing-Pa3u8`（autonomous daily worker session 2026-05-22 20:00）
> **Goal**：把剩下 2 個 router 也搬到 `shared/farm_registry_provider`，本日 single-session 收完整個 F4 戰場

---

## 1. 為什麼今天做這個

2026-05-21 F2-F5 cleanup batch handoff doc 明確指出：

> **F4 後續清掉 work_order + reporting routers**（0.5h；single-session 可塞進 M5 規劃日順帶做完）

5/21 F4 範圍只列 4 個 routers（inventory / material_request / approval / cost_ledger）；實作中發現 `work_order_router.py` + `reporting/routers/reporting_router.py` 有相同 `_FARM_REGISTRY` lazy singleton pattern 但不在原 issue scope。今天作為「F4 完整收尾」獨立 issue 開新編號 WMOM-20260522-01 處理。

候選比較：

| 任務 | 估時 | 風險 | 阻塞 |
|------|------|------|------|
| **F4 followup（本任務）** | 0.5-1h | 低（pattern 已驗證 4 次） | 無 |
| WMOM-20260519-01 F1 follow-up | 0.5-1d | 中（需 design 決策） | 等劉老師回 |
| WMOM-20260513-02 demo orchestrator | 2-3d | 高（跨 day session） | 太大 |
| M5 規劃 | 跨 session | — | 需先讀 ROADMAP |

F4 followup 是當前唯一可 single-session 100% 收完 + 開 PR 的選擇，故選之。

商業價值：低（zero behavior change）；技術價值：高（消滅最後 2 個「為什麼這樣寫」的問號，F4 全 6 個 routers 用同 pattern）。

---

## 2. 設計決策

### 2.1 work_order_router.py — 有兩個 farm registry 使用點

**A. main repository factory**（lines 107-135）：與 F4 4 routers 同模式
- 刪 `_FARM_REGISTRY = None`、`_get_default_farm_registry()` private helper
- `_default_repository_factory` 改用 `resolve_farm_db_path(farm_id)`
- `set_repository_factory(None)` 改呼叫 `reset_farm_registry()`

**B. finish hook db path resolver**（lines 148-168）：特殊
- 既有行為：失敗時回 None（**安靜跳過**），不 raise
- shared `resolve_farm_db_path` 失敗會 raise HTTPException(404)/500，與這裡需求**不符**
- 解法：直接呼叫 `get_farm_registry()` 拿 registry instance（imports 失敗會 raise HTTPException(500) — 用 try/except 接住）；再用 `registry.get_farm_db_path(farm_id)` 拿 None-or-path（不會 raise）
- 注意：`get_farm_registry()` 失敗會 raise HTTPException — 在 hook 路徑要接住該 exception；finish hook 場景接住後回 None 走「安靜跳過」分支

### 2.2 reporting_router.py — 與 cost_ledger_router 同型

兩個 factories：`_ledger_factory` + `_wo_factory`。F4-1 alignment：「任一 factory 改為 None → reset 共用 singleton」。
- 刪 `_FARM_REGISTRY = None`、`_resolve_farm_db_path()`
- `_get_ledger_repo` / `_get_wo_repo` 改用 shared `resolve_farm_db_path`
- 兩個 setters：保留現有 `if factory is None: reset` 邏輯（單一 setter scope；不需 any-None 聯合判斷因 2 個 setter 互不影響）

實際看 5/21 F4 inventory / cost_ledger 的做法：兩個 setter 分別 `if factory is None: reset`。reporting 完全等同模式。

### 2.3 backward compat / 行為差異

純 refactor，理論上零行為改動。但兩處微差需驗：

1. **HTTPException detail 訊息**：原 `work_order_router._default_repository_factory` 自己組「FarmRegistry not available; call set_repository_factory() to inject」；改用 shared 後訊息是「FarmRegistry not available; call set_*_factory() in the router to inject a mock」。測試若 string-match 會炸 — grep 確認無：
   - `grep -r "FarmRegistry not available" modules/workflow/tests/ tests/ modules/reporting/tests/` → 僅 `tests/test_farm_registry_provider.py` 引用，與本 PR 一致
   - **safe**

2. **finish hook 路徑**：原直接呼叫 `_get_default_farm_registry()` + `reg.get_farm_db_path(farm_id)`；改後呼叫 `get_farm_registry() + registry.get_farm_db_path(farm_id)`。語義一致；唯一差別：`get_farm_registry()` 在 lazy import 失敗 raise HTTPException(500) 而非 ImportError，所以 hook 內 try/except 要從 `except (ImportError, HTTPException)` 改成 `except HTTPException`（ImportError 不可能再 leak 出來）。為 safety 留 `except (ImportError, HTTPException)` 兩個都 catch，與既有相容。

### 2.4 scope 邊界

**做**：
- work_order_router.py 兩個 registry 使用點重構
- reporting_router.py 重構
- 新增 unit test：work_order finish hook FarmRegistry 失敗時安靜跳過（regression test）
- 新增 unit test：reporting `_get_ledger_repo` 走 shared resolve（既有 test mock 走 factory 不會涵蓋這條路徑，加 happy + 404 case）
- ISSUES.md / STATUS.yaml 收尾

**不做**：
- 不擴大到非 F4 議題（例如改 finish hook 的整體錯誤策略 — 出 scope）
- 不改 shared helper 行為
- 不開新 PR for placeholder/UI etc — single PR scope

---

## 3. 檔案異動（規劃）

```
M modules/workflow/routers/work_order_router.py        F4-1 type repository factory + finish hook hook 改 shared
M modules/reporting/routers/reporting_router.py        F4-1 type ledger + wo factory 改 shared
+ modules/workflow/tests/test_work_order_router_f4.py  finish hook FarmRegistry 失敗 / 成功 / 找不到 farm 3 case + 主 factory shared 整合
+ modules/reporting/tests/test_reporting_router_f4.py  ledger/wo 走 shared resolve 失敗 → 404；mock factory 不觸 shared 一條 happy
M ISSUES.md                                            新 issue WMOM-20260522-01 → done；統計表 open +1 後 -1
M STATUS.yaml                                          last_updated / next_milestone / issue_stats
+ work-logs/2026-05/2026-05-22-f4-followup-work-order-reporting.md  本檔
```

---

## 4. TODO

- [x] Branch + work-log
- [x] Open ISSUES.md entry WMOM-20260522-01（in_progress）
- [x] Refactor work_order_router.py（main factory + finish hook）
- [x] Refactor reporting_router.py
- [x] Tests new file（2 個檔，13 個 test）
- [x] backend pytest zero regression vs 554 baseline → 568 passed = 554 + 13 new + 1 flaky concurrency 過
- [x] code-reviewer subagent + 採納 must / should（must-fix #1 採納；其餘 should/nice 是跨 6 routers 一致性議題或誤判，skip）
- [x] ISSUES.md / STATUS.yaml update
- [ ] commit + push + 建 PR（若 sandbox 無 gh，留訊息給劉老師）

---

## 5. 實作紀錄

### 5.1 完成檔案

**Backend 修改（2 個 routers）：**
- `modules/workflow/routers/work_order_router.py`
  - 刪 module-level `_FARM_REGISTRY = None` + `_get_default_farm_registry()` helper
  - `set_repository_factory(None)` 從 `_FARM_REGISTRY = None` 改 `reset_farm_registry()`（shared）
  - `_default_repository_factory` 從手寫 try/except + 兩段檢查 collapse 成單行 `get_repository(resolve_farm_db_path(farm_id))`
  - `_resolve_db_path_for_finish_hook`：保留 silent-skip 語義 — 用 `get_farm_registry()` 拿 instance + 直接 `registry.get_farm_db_path()` 接 None；`get_farm_registry()` 失敗 raise HTTPException(500) 接住後回 None
  - import `from shared.farm_registry_provider import (get_farm_registry, reset_farm_registry, resolve_farm_db_path)`
- `modules/reporting/routers/reporting_router.py`
  - 刪 `_FARM_REGISTRY = None` + `_resolve_farm_db_path()` local function
  - `set_ledger_factory(None)` / `set_work_order_factory(None)` 改用 `reset_farm_registry()`
  - `_get_ledger_repo` / `_get_wo_repo` 改用 shared `resolve_farm_db_path`
  - import `from shared.farm_registry_provider import reset_farm_registry, resolve_farm_db_path`

**Backend 測試新增（2 個檔，13 test）：**
- `modules/workflow/tests/test_work_order_router_f4.py` — 7 test：
  - main factory：happy path（changhua 解出 /tmp/changhua.db）+ 404（未知 farm）+ `set_repository_factory(None)` reset shared singleton
  - finish hook：happy + 未知 farm silent-None + registry import 失敗 silent-None + override bypass shared（init_calls == 0）
- `modules/reporting/tests/test_reporting_router_f4.py` — 6 test：
  - `_get_ledger_repo` / `_get_wo_repo` 走 shared resolve（happy）
  - `_get_ledger_repo` 未知 farm → 404
  - 注入 ledger factory 後不觸 shared singleton（init_calls == 0）
  - `set_ledger_factory(None)` / `set_work_order_factory(None)` 兩 setter 對稱 reset

**Tracking：**
- `ISSUES.md` — 新增 WMOM-20260522-01 → done；統計表 done 41→42 / in_progress 1→0
- `STATUS.yaml` — last_updated / next_milestone / issue_stats

### 5.2 設計決策落實

- **Finish hook silent-skip 保留**：選 `get_farm_registry()` + 直接 `registry.get_farm_db_path()` 路徑而非 `resolve_farm_db_path()`（後者失敗會 raise 404，不符 hook 需求）。雙重失敗保護：lazy import 失敗 catch HTTPException、farm 未知 接 None 分支
- **與 5/21 F4 setter pattern 對齊**：reporting_router 兩個 setter 各自 `if factory is None: reset_farm_registry()`（與 inventory_router / cost_ledger_router 同模式；非 approval/material_request 的 multi-setter `any-None` 模式，因 reporting 兩 setter 互相獨立）
- **HTTPException detail 訊息**：沿用 shared helper 既有訊息（"call set_*_factory() in the router to inject a mock"），與 5/21 已 migrate 的 4 個 routers 一致，避免本 PR 引入訊息不一致
- **Test fixture autouse**：fixture 在 setup + teardown 兩段清 factory，對齊 reporting fixture pattern；code review must-fix #1 採納修

### 5.3 Build / test 驗證

- `python -m pytest modules/workflow/tests/test_work_order_router_f4.py modules/reporting/tests/test_reporting_router_f4.py -v` → **13 passed**
- `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ -q` → **568 passed, 1 xfailed, 4 failed**
  - 4 failed 全 pre-existing：1 flaky concurrency（5/21 文件記錄為偶發；本次另一條 concurrency 過）+ 3 numpy/pandas drift
  - 對 5/21 baseline 554 passed +14（13 new test + 1 flaky 過），**zero regression**

### 5.4 Code review 採納

Code-reviewer subagent 找出 **1 must-fix + 3 should-fix + 2 nice-to-have**。採納 must-fix；should-fix / nice-to-have 全 skip + 寫進此處供未來參考：

| 級別 | 議題 | 採納？ | 原因 |
|------|------|--------|------|
| Must-fix #1 | work_order_router test fixture 漏 `set_repository_factory(None)` setup/teardown | ✅ 採納 | 必修 — test isolation 風險 |
| Should-fix #2 | reporting_router 雙 setter teardown 觸發 double reset，理論 race | ❌ skip | 5/21 已確立模式跨 6 routers；本 PR scope 不應動共用 pattern；race 在 sync FastAPI test 不存在；若要修應跨所有 6 routers 一次 |
| Should-fix #3 | `_default_repository_factory` 型別標註缺失 | ❌ 誤判 skip | 實際已有 `-> WorkOrderRepository`；reviewer 因 diff context 沒看到 |
| Should-fix #4 | HTTPException detail 訊息退化（從 router 特定改成 `set_*_factory()` glob） | ❌ skip | 5/21 shared helper 訊息設計；改了會與已 migrate 4 routers 不一致；應在 shared 層改一次套用全部 |
| Nice #5 | `_FakeFarmRegistry.init_calls` class variable 跨 pytest-xdist worker 脆弱 | ❌ skip | 當前無 xdist 設定；對齊 5/21 `test_farm_registry_provider.py` 模式 |
| Nice #6 | `sys.path.insert(0, str(PROJECT_ROOT))` 多餘 | ❌ skip | 對齊既有 test 文件慣例（`test_work_order_api.py` etc 皆有）；統一移除應在獨立 PR |

---

## 6. 下次接手指南

### 已完成（push 到 origin/claude/blissful-turing-Pa3u8）
- F4 戰場完整收完：所有 6 個 routers（inventory / material_request / approval / cost_ledger / work_order / reporting）共用 `shared/farm_registry_provider`
- 新加 13 個 regression test（含 finish hook 三條失敗安靜跳過分支）
- Zero behavior change，純結構整理

### 待辦（不阻塞，可下次再處理）
- **PR 開啟**：sandbox 無 gh CLI；劉老師收到通知後從 GitHub 介面開 PR 並 merge（branch 已 push）
- **F4 後續改進機會（low priority）**：
  - Shared helper HTTPException detail 訊息可改回 router-specific（pass detail prefix arg 進去）— 影響 6 個 routers
  - 6 個 routers 統一改成「only reset on actual None transition」模式（避免 double reset overhead）— 影響 6 個 routers
  - 移除 test 文件 `sys.path.insert(0, str(PROJECT_ROOT))` 改用 conftest.py — 跨 ~20 個 test files

### 建議下次 session 工作

依優先級：

1. **WMOM-20260519-01**（F1 follow-up，0.5-1d）— `add_return` 超量退料 domain guard：需先與劉老師 walkthrough 決定 guard 策略（domain layer vs router vs UI），再寫 negative path test
2. **M5 規劃**：讀 `docs/product/ROADMAP.md` M5 章節決定第一個 issue（RAG knowledge module skeleton 或 demo orchestrator UI）；建議獨立 session 因 single-session 不易完整完工
3. **WMOM-20260513-02** demo orchestrator simulator 接合（M5 demo 視覺化用）— A10 e2e 接 simulator 一鍵 replay lifecycle，2-3d
4. **F4 後續改進（上述 nice-to-have）**：可挑一個塞進 M5 規劃日順帶做完
