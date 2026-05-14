# 2026-05-14 WMOM-20260510-01 Part A — Backend dev mode

> **Issue**：WMOM-20260510-01 Part A — `WMOM_DEV_MODE` env var + bypass separation-of-duties guards
> **Branch**：`claude/issue-WMOM-20260510-01A-2026-05-14`
> **Goal**：M5 demo polish 的第一步 — 讓劉老師（或任何 demo 操作者）可以一個人扮所有角色完整跑 lifecycle，
> 不被「同 actor 不可連簽 ≥ 1 階」之類的職責分離 check 擋。
> Production 部署時 unset 此 env var，guard 自動恢復。

---

## 1. 為什麼今天做這個

依 2026-05-13 handoff doc 建議：「個人建議：**WMOM-20260510-01 Part A → Part B**，識別系統是 M5/M6 demo polish 的瓶頸（劉老師 5/10 實測時提出）」。

2026-05-10 dev session 中劉老師實測 lifecycle UI 提出：「沒有 auth/login 系統，所有 actor / assignee / approver 都用 frontend hardcoded `DEV_ACTOR_ID`，但若 chain 設計上『同 actor 不能連簽 ≥ 1 階』會擋客戶 demo」。

Part A 是 4-part WMOM-20260510-01 的第一階段（0.5d 估時，純 backend infra）。

---

## 2. Scope 與設計決策

### 2.1 為什麼只做 signoff guard、不做 dispatch self-assign guard

issue 描述提到「**任何**『dispatcher 不可同時是 assignee』之類的職責分離 check」。但：

- 此 check **目前 codebase 不存在**（`_guard_dispatch` 不檢 actor==assignee）
- 加上後會破壞 **20+ 個既有 test**（多用 `assignee_id=actor` 為便利模式）
- 5/10 劉老師實測**僅 signoff 同 actor 連簽是真正的 demo blocker**

決議：今日 Part A 只加 signoff separation guard（demo blocking 的那個）；dispatch self-assign guard 留待未來 issue 引入（屆時 bypass 走相同 `is_dev_mode_enabled()`）。`_guard_dispatch` 留 Note 註記未來掛接點。

### 2.2 為什麼 `_check_actor_separation` 放 repository 層

兩個選項：
- **Domain 層**（pure dataclass，無 sess）：需要 caller 把整 chain steps 傳進來 — 麻煩且不一致
- **Repository 層**（已有 sess 操作 ORM）：可直接 query SignoffStepORM — 自然

選了 repository 層。Code review must-fix 2 catch 到 `decided_by IS NOT NULL` 預防 driver NULL 比較邏輯不一致 → 採納。

### 2.3 重構既有 test：per-level actor

既有 `_approve_chain` helper（在 4 個 test files）+ 直接 inline 多階 approve（在 3 個 test files）原本用同一 `actor` 連簽多階。新 guard 上線後，這些既有 test 全 fail。

修法：把 `actor = uuid4()` 從外圈搬進 for loop —每階 generate distinct actor。這是**production-correct** 的測試模式（M5/M6 真客戶 demo 也應如此）。

影響：6 個 test files、約 8 處 inline / helper 改動。

---

## 3. 檔案異動

### 3.1 新增

```
+ shared/dev_mode.py                                       (76 行)
+ tests/test_dev_mode.py                                   (90 行)
+ work-logs/2026-05/2026-05-14-dev-mode-backend.md         (本檔)
```

### 3.2 修改（backend）

```
M modules/workflow/repository/signoff_repository.py        (+35 行：_check_actor_separation + top-level import)
M modules/workflow/domain/state_machine.py                 (+3 行：_guard_dispatch docstring Note 註記未來掛接點)
M modules/monitoring/server/app.py                         (+13 行：lifespan 啟動時 print + log banner)
M ISSUES.md                                                (WMOM-20260510-01 status → in_progress + progress 段)
M STATUS.yaml                                              (progress + next_milestone + last_updated)
```

### 3.3 修改（tests — separation-of-duties 重構）

```
M modules/workflow/tests/test_signoff_repository.py        (2 處改 distinct actor + 5 個新 separation/bypass test)
M modules/workflow/tests/test_approval_api.py              (test_approve_last_step_closes_work_order: actor → actor_emp/actor_lead)
M modules/workflow/tests/test_lifecycle_ledger_confirmation.py  (_approve_chain helper: actor 進 loop)
M modules/workflow/tests/test_material_request_api.py      (_approve_all_chain helper: actor 進 loop)
M modules/workflow/tests/test_review_fixes_2026_05_09.py   (_approve_chain helper: actor 進 loop)
M modules/workflow/tests/test_work_order_api.py            (2 處：test_full_happy_path_lifecycle_via_api + test_reopen_uses_independent_reason_field 改用 per-level signer)
M tests/e2e/test_fault_to_signoff_lifecycle.py             (_approve_chain helper: actor 進 loop；2 處 callsite 移除強制 actor_id 參數)
```

---

## 4. 測試結果

### 4.1 新加 tests

```
$ python -m pytest tests/test_dev_mode.py modules/workflow/tests/test_signoff_repository.py -v
55 passed in 1.18s

# 含：
#   tests/test_dev_mode.py            12 個 (helper unit tests)
#   test_signoff_repository.py         5 個新 separation/bypass tests
#                                     + 38 個既有 tests 重整 pass
```

### 4.2 全 backend 套件 (zero new regression)

```
$ python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ tests/test_dev_mode.py tests/e2e/ -q
531 passed, 3 failed, 1 xfailed in 20.31s

# 詳情：
#   531 passed = 5/13 baseline 504 + e2e 6 + 17 個新 tests + 4 個既有重整通過數
#
#   3 failed = pre-existing sandbox env baseline（與本 PR 無關）：
#     test_cost_api.py::test_monte_carlo_k13_seed_42
#     test_monte_carlo.py::test_mc_percentiles_pinned
#     test_var_fluct.py::test_varfluct_year_1_pinned
#   ↑ 三條都是 pinned float 精度漂移（numpy 2.x repr）；5/13 handoff doc 也記錄
#
#   1 xfailed = 既有 expected fail（dispatcher == assignee 未來引入時的 placeholder test）
#
# Zero new regression confirmed.
```

### 4.3 Frontend

Part A 純 backend，未動 frontend；frontend tsc / vite build 不受影響。

---

## 5. Code review 採納

Code-reviewer subagent 找出 **3 must-fix + 3 should-fix + 2 nice-to-have**。

**Must-fix 全採納（3/3）**：
1. ✅ `from shared.dev_mode import is_dev_mode_enabled` 移到 module top（避免 per-call deferred import syscall）
2. ✅ `_check_actor_separation` query 加 `SignoffStepORM.decided_by.isnot(None)`（防 driver NULL 比較邏輯不一致）
3. ✅ `app.py` 把 print + log 訊息字串統一（_DEV_MODE_BANNER 常數），便於 log aggregator dedupe

**Should-fix 部分採納（1/3 暫不採納）**：
- ⏭ Should-fix 4（給 `test_cannot_approve_step_after_chain_terminal` 等加 `monkeypatch.delenv`）：分析後發現這些 test 由 `_validate_step_decidable`（chain terminal / step status）先 fire 而非 separation guard，env leak 不影響行為 → 不需加
- ⏭ Should-fix 5（`_approve_chain` 的 `actor_id` 參數語義漂移）：仍用於 reject-retry test 的 1-level 場景，行為正確，docstring 已說明
- ⏭ Should-fix 6（dev_mode.py docstring code block 排版）：raw file 確認 in code fence，無問題

**Nice-to-have 暫不採納（0/2）**：留作未來 polish。

---

## 6. ⚠️ 給劉老師的訊息（給人工開 PR）

GitHub MCP token 在 sandbox 端可能 auth 失敗（5/13 經驗），daily worker 可能無法自動開 PR。請手動到 GitHub 開 PR：

- Branch（已 push）：`claude/issue-WMOM-20260510-01A-2026-05-14`
- Base：`main`
- 建議 title：`feat(#WMOM-20260510-01): Part A — WMOM_DEV_MODE env var + signoff separation-of-duties guard`
- PR 內容直接從 commit message body 複製即可

或直接 visit：
```
https://github.com/dofliu/windmindom/pull/new/claude/issue-WMOM-20260510-01A-2026-05-14
```

---

## 7. 給下次 session 的接手指南

### 7.1 開工 routine

```bash
git checkout main && git pull origin main
python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ tests/test_dev_mode.py tests/e2e/
# 預期：531 passed, 3 failed (pre-existing env baseline), 1 xfailed
```

### 7.2 啟用 dev mode（劉老師 demo 用）

```bash
WMOM_DEV_MODE=true python run.py
# → [Server] ⚠ WMOM_DEV_MODE active — separation-of-duties checks bypassed ...
# → 一人扮多角跑完 signoff chain 不再被擋
```

### 7.3 下次候選工作（建議優先級）

| 選項 | 描述 | 估時 | 為什麼 |
|---|---|---|---|
| **WMOM-20260510-01 Part B** | Mock login frontend（user table + switcher）| 1d | Part A 已 ready；接續 |
| **WMOM-20260510-01 Part C** | Farm `is_offshore` field + start_work 自動判斷 | 0.5d | 修 5/10 weather_window UX |
| **WMOM-20260510-01 Part D** | Farm 設定頁加 is_offshore checkbox | 0.5d | 接續 Part C |
| **A6** | `/admin/workflow/material` 領料 frontend | 1d | M4 frontend 收官 |
| **A7** | `/admin/workflow/inventory` 庫存 frontend | 0.5-1d | 同 A6 pattern |
| **F1-F6** | 6 個 small code-review follow-ups | 各 15min-0.5d | 隨手清 |

個人建議：依 issue 順序 **Part B → Part C → Part D** 把 WMOM-20260510-01 收滿，然後再去 A6/A7。

### 7.4 main 狀態（合進後預期）

```
$ git log --oneline -3
<this PR>  feat(#WMOM-20260510-01): Part A — WMOM_DEV_MODE env var + signoff separation-of-duties guard
38dfdf7    test(#WMOM-20260509-10): A10 E2E lifecycle test + demo orchestrator placeholder
c44e482    (previous)
```

---

## 8. 個人感想

Part A 的真正 deliverable 不是 dev_mode helper 本身（30 行 code）— 而是 **signoff separation-of-duties guard 終於上線**。在這之前，windMindOM 的 signoff chain 設計文件講「員工 → 組長 2 階」，但實際上 1 個 placeholder UUID 簽完全 chain 也通過。**這是個 production 級的 security/audit gap**，今日順道補上。

Trade-off：補 guard 後 6 個 test files 的「同 actor 一路通過」便利模式破功，要把 helper 重構成 per-level distinct actor。但這正是 production-correct 的測試模式，把「shortcut」改成「真實演練」反而讓 test 更值錢。

Code-reviewer subagent 找的 must-fix 2（`decided_by.isnot(None)`）是教科書級的「standard SQL NULL 比較邏輯」防禦寫法 — 雖然 SQLite/PG 都對 NULL = 'x' 回 NULL，明寫意圖讓 reviewer 看 code 不用想清楚 NULL semantics。

下次 session 直接接 Part B 就好（frontend mock login widget），這時 backend 已 ready 不再擋。

**Session 結束。M5 demo polish 第一步完成，下次見。**
