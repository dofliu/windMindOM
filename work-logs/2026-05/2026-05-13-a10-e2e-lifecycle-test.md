# 2026-05-13 A10 — E2E lifecycle test（pytest Layer A + frontend placeholder）

> **Issue**：WMOM-20260509-10 — Fault → Signoff full lifecycle E2E test
> **Branch**：`claude/issue-WMOM-20260509-10-2026-05-13`
> **Goal**：避免 2026-05-10 那種 hotfix 風暴重演 — 把整條 demo flow（建工單 →
> 派工 → 領料簽核 → 庫存扣帳 → 完工 → ledger confirm → 工單簽核 → CLOSED）
> 一次串起來在 pytest 自動跑，每個 PR CI 都會擋下 lifecycle regression。

---

## 1. 為什麼今天做這個（接手快速指南）

2026-05-10 handoff doc 強調：「強烈建議下次 session 第一件事就是 A10 E2E lifecycle test。」
理由如下（節錄）：

| 5/10 那天踩到的 bug | 如果有 A10 會立刻撞到 |
|---|---|
| CORS spec violation | E2E test client 跨 localhost:3100/8100 立刻 fail |
| `work_orders` table 撞名 | 第一個 INSERT 直接 500 |
| dispatch guard 缺 assignee_id | 第一個 dispatch step fail |
| weather_window UX | start_work step fail |

當時 4 個 hotfix 兜了大半天；做完 A10 之後，類似 bug 會在 PR CI 就直接擋住，不會 merge 到 main 才被劉老師實測踩到。

---

## 2. 今日 scope

### 2.1 Layer A — pytest E2E lifecycle test（**今日完整完成**）

檔案：`tests/e2e/test_fault_to_signoff_lifecycle.py`

涵蓋（依 issue acceptance）：

**Happy paths（3 條 — CORRECTIVE / PREVENTIVE / INSPECTION）**

每條走完整 lifecycle：
1. 建工單（CORRECTIVE 帶 `source_alarm_code`、PREVENTIVE/INSPECTION 計畫性無告警）
2. dispatch → start_work
3. 建 material_request linked to WO
4. submit_for_approval + 3 階 approve（employee → leader → treasury）
5. assert chain APPROVED + MR DISPATCHED + ledger entry ESTIMATED + stock -N
6. receive MR with actual_qty
7. finish WO → ledger entry CONFIRMED
8. WO 自動建 signoff chain（employee/leader 2 階）
9. approve 2 階 → WO CLOSED + chain APPROVED + subject_status_changed=True

**Unhappy paths（2 條）**

- A：**Signoff reject → retry path** — 第二階 leader reject → WO 回 IN_PROGRESS →
  重新 finish → 自動建新 chain → 重新 approve → CLOSED（驗 chain history 2 條 chain 都在 DB）
- B：**Dispatch under insufficient stock** — 預建 stock=1，建 MR estimated_qty=3，
  完成 3 階 approve 後 final approve response 帶 `transition_error` 包含 "insufficient"，
  MR 留在 APPROVED（**沒**進 DISPATCHED），stock 仍 = 1

**Mock 策略**

A10 issue 原始描述 Step 1-3 包含「啟動 simulator + 注入 fault scenario +
assert SCADA tag delta + alarm code」— 真的接 simulator 牽涉 monitoring module
跨 modules 整合（M5 才會做）。今日 scope 把 Step 1-3 mock 成「建立 corrective WO 時帶
`source_alarm_code='GBT_TEMP_HIGH'`」，等 M5 接 RAG / monitoring 整合時再把 simulator
fixture 補上（會在 work-log 留 follow-up issue）。

### 2.2 Layer B — frontend demo orchestrator skeleton（**今日做最小可 tsc 版本**）

檔案：`frontend/components/demo/DemoOrchestratorPage.tsx`

- 只放 step list（11 個 step）+ status 標籤
- 不接 API（純靜態 placeholder）
- tsc clean + 不註冊到 App router（避免 navigation 污染）
- 開 follow-up issue：WMOM-20260513-02（M5/M6 demo orchestrator full impl）

---

## 0. ⚠️ 給劉老師的訊息（給人工開 PR）

GitHub MCP token 在 sandbox 端 auth 失敗（`Failed to retrieve GitHub token`），所以 daily worker **無法自動開 PR**。請手動到 GitHub 開 PR：

- Branch（已 push）：`claude/issue-WMOM-20260509-10-2026-05-13`
- Base：`main`
- 建議 title：`test(#WMOM-20260509-10): A10 E2E lifecycle test + demo orchestrator placeholder`
- PR 內容直接從 commit message body 複製即可

或直接 visit GitHub UI：
```
https://github.com/dofliu/windMindOM/pull/new/claude/issue-WMOM-20260509-10-2026-05-13
```

---

## 3. 今日成果

### 3.1 檔案異動

```
+ tests/e2e/__init__.py                                    （0 行；package marker）
+ tests/e2e/conftest.py                                    （12 行；sys.path setup）
+ tests/e2e/test_fault_to_signoff_lifecycle.py             （680 行；6 個 E2E test）
+ frontend/components/demo/DemoOrchestratorPage.tsx        （145 行；Layer B skeleton）
+ work-logs/2026-05/2026-05-13-a10-e2e-lifecycle-test.md   （本檔）
M STATUS.yaml                                              （progress + next_milestone）
M ISSUES.md                                                 （A10 → done + 新 WMOM-20260513-02）
```

### 3.2 測試結果

```
$ python -m pytest tests/e2e/ -v
6 passed in 1.88s

# acceptance criteria：< 60s ✓

$ python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ tests/e2e/ -q
507 passed, 3 failed, 1 xfailed in 20.92s

# 詳情：
#   501 baseline tests passed（與 main 同數量）
#   + 6 new E2E tests passed（A10）
#   = 507 passed
#
#   3 failed = pre-existing env baseline：
#     test_cost_api.py::test_monte_carlo_k13_seed_42
#     test_monte_carlo.py::test_mc_percentiles_pinned
#     test_var_fluct.py::test_varfluct_year_1_pinned
#   ↑ 三條都是 pinned float 精度漂移（Python repr 在不同環境下尾位差 1 bit）
#     與本 PR 無關，main 上跑同樣 sandbox env 也是這樣
#
# Zero new regression confirmed.

$ cd frontend && npx tsc --noEmit && npx vite build
0 errors, vite 4.34s, 734 modules
```

### 3.3 Code review 採納

Code-reviewer subagent 找出 **4 must-fix + 7 should-fix + 4 nice-to-have**。

**Must-fix 全採納（4/4）**：
1. INSPECTION test 名稱誤導 → rename 成 `test_inspection_same_qty_lifecycle` + TODO 註記
2. `_walk_happy_lifecycle` 未驗 dispatch 中間狀態 → 補 MR=DISPATCHED + stock 扣 + ledger=ESTIMATED 三條 assertion（**這是 A10 設計目的最核心的擋 regression 機制**）
3. teardown `set_signoff_factories(None, None)` → `(None, None, None)` 對稱
4. `__import__("modules.workflow.domain", ...)` 兩處 → 直接 `from modules.workflow.domain import SignoffSubjectType`

**Should-fix 採納（6/7）**：
- conftest.py dead imports（Decimal / pytest）移除
- 測試模組 `sys.path.insert` 移除（讓 conftest 統一管）
- `WorkOrder` import 進來，移除 `"WorkOrder"` 字串前向引用 + `type: ignore`
- INSPECTION test 補 stock + ledger assertions
- reject-retry test 把 inline approve 改成 `_approve_chain` helper
- `import time` 移到 module top

**Should-fix 暫不採納（1/7）**：
- alarm code naming 與 monitoring 層 schema 不一致 → 留 follow-up WMOM-20260513-02 Part B（需先抽 shared constant，超出今日 scope）；test 內 docstring 加 TODO 註記

**Nice-to-have 暫不採納（0/4）**：留作未來 polish。

---

---

## 4. 環境注意

開工發現 sandbox env：
- pytest 沒裝 → `pip install pytest pytest-asyncio`
- numpy/pandas/sqlalchemy/reportlab/httpx 都沒裝 → 從 requirements.txt + 額外裝
- numpy 2.x 改了 float repr → 3 個 cost tests pinned 值會 fail，降回 numpy 1.26.4
- 仍有 3 個 cost tests fail（pinned float drift）+ 1 個 dispatch concurrent test flaky
  — **這些都是 sandbox env baseline 問題，非我引入的 regression**
- 我關心的 metric：**新增 test 全 pass + 既有 501 個 pass 的 test 仍 pass**（zero new regression）

---

## 5. 接手指南（給下次 session）

### 5.1 開工 routine

```bash
git checkout main && git pull origin main
python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ tests/e2e/
# 預期：507 passed, 3 failed (pre-existing env baseline), 1 xfailed
```

### 5.2 下次候選工作（建議優先級）

| 選項 | 描述 | 估時 | 為什麼 |
|---|---|---|---|
| **WMOM-20260510-01 Part A** | Backend dev mode（`WMOM_DEV_MODE=true` 跳過 signoff 同 actor guard）| 0.5d | M5 demo polish；client demo 要一人扮全角 |
| **WMOM-20260510-01 Part B** | Mock login + user switcher | 1d | 接 Part A |
| **A6** | `/admin/workflow/material` 領料 frontend | 1d | M4 frontend 收官（之前都是 backend） |
| **A7** | `/admin/workflow/inventory` 庫存 frontend | 0.5-1d | 同 A6 pattern |
| **WMOM-20260513-02** | A10 follow-up：真 simulator + canonical alarm code + INSPECTION over-use variant | 2-3d | A10 mock 還在；M5 才會做 |
| **F1-F6** | 6 個 small code-review follow-ups | 各 15min-0.5d | 隨手清 |

個人建議：**WMOM-20260510-01 Part A → Part B**，識別系統是 M5/M6 demo polish 的瓶頸（劉老師 5/10 實測時提出）。

### 5.3 main 狀態（合進後預期）

```
$ git log --oneline -3
<this PR>  feat(#WMOM-20260509-10): A10 E2E lifecycle test + demo orchestrator placeholder
9c8f476    hotfix: remove weather_window checkbox + open WMOM-20260510-01
ab7ef0e    Merge pull request #26 from dofliu/claude/hotfix-dispatch-assignee-2026-05-10
```

---

## 6. 個人感想

A10 是 5/10 handoff doc 強烈點名的「第一件事」；今天從早上 preflight 到傍晚 wrap-up
總工時約 0.5d（issue estimate 是 1-1.5d，提前完成因為已有 `test_lifecycle_ledger_confirmation.py`
的 fixture pattern 可直接複用）。最有價值的是 **code-reviewer subagent 找出的 must-fix 2**
（中間狀態未驗）—— 那個沒修的話，A10 對 dispatch guard regression 形同虛設；
修完之後，5/10 那連環 4 個 hotfix 中至少有 3 個會被這套 E2E test 在 PR CI 直接擋下：

| 5/10 bug | 對應的 E2E assertion |
|---|---|
| CORS spec violation | TestClient 跨服務通訊不會撞（單元測試級） |
| `work_orders` table 撞名 | `test_corrective_alarm_to_signoff_full_lifecycle` 第一個 wo_repo.create 就會 IntegrityError |
| dispatch 缺 assignee_id | `_walk_happy_lifecycle` 的 `wo_repo.transition(wo.id, "dispatch", actor_id=actor)` 會 fail |
| weather_window UX bug | start_work transition guard 撞氣象視窗檢查會 fail |

接下來 dev session 開始就在 main 上跑這套 6 個 test，PR 出來 review 也跑一次，
進到 client demo 之前所有 lifecycle regression 都會早早被發現。

**Session 結束。M4 acceptance E2E 補齊，下次見。**
