# 2026-05-25 WMOM-20260525-01 — 並發 dispatch lost-update race（BEGIN IMMEDIATE 從未接上）

> **Issue**：WMOM-20260525-01 — 並發 dispatch 庫存/ledger 不一致（lost-update）
> **Branch**：`claude/upbeat-davinci-s9Juu`（autonomous daily worker, 5/25 20:00）
> **Goal**：根治 `dispatch_request()` 在並發下的 lost-update（庫存少扣、ledger 多寫），讓
> `test_concurrent_dispatch_same_item_serialized_correctly` 從間歇 fail 變 deterministic pass。
> backend only，動到全 workflow/cost 共用的 SQLite engine 交易起手模式，中等 blast radius、已全面 verify。

---

## 1. 為什麼今天做這個（priority tree step 1：production bug）

開工 baseline 跑 `pytest modules/{workflow,cost,reporting}/tests/`：565 passed / 1 xfailed / **4 failed**。
其中 3 個是已記錄的 numpy BLAS float 末位 drift（環境性），但第 4 個
`test_concurrent_dispatch_same_item_serialized_correctly` 之前 handoff 一直當「環境性 flaky、單獨複跑即 pass」。

**進場 root-cause 後發現這不是 flaky test，是真 bug**：單獨複跑 4 次 → fail/fail/pass/fail（~2/3 fail）。
失敗時**沒有任何 exception**（`errors == []` 通過），但 `stock_new == 6` 而非 3 ——
10 - 4 = 6，扣 3 那筆**整個不見了**，可是 ledger 卻有 2 筆 entry。這是 lost-update，不是 timeout。
→ 符合 priority tree step 1「known production bug（資料一致性）」，優先修。

---

## 2. Root cause：BEGIN IMMEDIATE 從未真的接上

`dispatch_request()`（material_request_repository.py:355）一個 session 內：
SELECT+扣庫存（`apply_stock_delta_in_session`，SQLite 上 `with_for_update()` 是 no-op）→ 寫 ledger → commit。

全 workflow/cost repo 共用 `work_order_repository._get_engine()` 的 SQLite engine。原本：

```python
eng = create_engine(f"sqlite:///{abs_path}", future=True,
                    connect_args={"check_same_thread": False, "timeout": 5.0})
sa_event.listen(eng, "connect", _set_sqlite_pragmas)   # 只設 WAL + busy_timeout
```

pysqlite 預設 `BEGIN DEFERRED`：`BEGIN` 只在第一個寫入語句才取鎖，**SELECT 完全不取鎖**。
兩 thread 並發 dispatch 同一 item：

1. T1 `BEGIN`（deferred、不取鎖）→ SELECT stock=10 → 記憶體扣成 7
2. T2 `BEGIN`（deferred、不取鎖）→ SELECT stock=10（讀到舊值！）→ 記憶體扣成 6
3. T1 commit → 寫 7；T2 commit → 寫 6（後寫者覆蓋）→ 最終 6，**扣 3 那筆 lost**
4. 但兩個 thread 各自都寫了一筆 ledger → 庫存 1 筆、帳務 2 筆 → **不一致**

`apply_stock_delta_in_session` 與測試 docstring 都白紙黑字寫「SQLite 的 BEGIN IMMEDIATE +
WAL + busy_timeout 會把寫入序列化」，**但程式從未把 BEGIN IMMEDIATE 接上**（沒設
`isolation_level`、沒有 `begin` event listener）。註解假設了一個不存在的契約。

用兩段獨立 sqlite3 probe 證實：deferred 下兩 connection 都讀到 10 → 最終 6（lost update）；
`isolation_level=None` + 手動 `BEGIN IMMEDIATE` 下 → 最終 3（序列化正確）。

---

## 3. 修法（`work_order_repository.py`，engine begin event + scoped 旗標）

基於 SQLAlchemy/pysqlite serializable recipe，但**只把 IMMEDIATE 套在寫路徑**（見 §7 must-fix）：

- `connect` event：`dbapi_conn.isolation_level = None`（autocommit，關掉 pysqlite 隱式 BEGIN，
  讓 begin event 能自選 BEGIN 模式），再跑 `PRAGMA journal_mode=WAL / busy_timeout=5000 /
  synchronous=NORMAL`（PRAGMA 必須在 autocommit 下跑，WAL 不可在交易內切換）。
- `begin` event listener `_emit_begin`：讀 thread-local 旗標 — read-modify-write 寫路徑
  發 `BEGIN IMMEDIATE`（交易起手即取 RESERVED write lock，第二筆並發在 busy_timeout 5s 內等
  第一筆 commit/rollback 後讀最新 stock 再扣 → 序列化正確）；其餘（含 reporting 長查詢 / list /
  dashboard 等純讀）發預設 `BEGIN`（deferred）→ WAL snapshot read，互不阻塞。
- `immediate_transaction()` context manager：把 thread-local 旗標設 True，包在 stock 異動三條
  read-modify-write 路徑外層：`MaterialRequestRepository.dispatch_request` / `.add_return` /
  `InventoryRepository.adjust`。begin event 與發起交易同 thread 同步執行，thread-local 取值正確。

全 repo（work_order / inventory / material_request / signoff / cost_ledger / reporting）共用同一個
`_get_engine` cache；monitoring 走獨立 raw sqlite3（`sqlite_utils.open_sqlite`），不受影響。

同步把 `inventory_repository.apply_stock_delta_in_session` 的 docstring 從「假設 BEGIN IMMEDIATE」
改成「靠 caller 外層 `immediate_transaction()`」。

---

## 4. 檔案異動

```
M modules/workflow/repository/work_order_repository.py   connect 設 isolation_level=None + begin event BEGIN IMMEDIATE
M modules/workflow/repository/inventory_repository.py     docstring 更正（指向真正生效的 _begin_immediate）
M modules/workflow/tests/test_dispatch_atomic_transaction.py  + deterministic regression test
+ work-logs/2026-05/2026-05-25-dispatch-lost-update-fix.md   本檔
M ISSUES.md / STATUS.yaml                                  狀態更新
```

---

## 5. Regression test（deterministic，不靠 thread 排程運氣）

`test_dispatch_no_lost_update_under_forced_interleave`：用 `threading.Barrier(2)` 把 barrier
塞在 stock 讀取（apply_stock_delta）之後、commit 之前的 `insert_in_session`，強制兩 thread
在 lost-update window 內交會。

- **修復前**：兩 thread 的 deferred BEGIN/SELECT 都不取鎖 → 都讀到 10、都抵達 barrier →
  放行後各自寫回 → 後寫者覆蓋 → **deterministic 失敗**（已實測 stock=7）。
- **修復後**：第二 thread 卡在 `BEGIN IMMEDIATE` 取 RESERVED lock，根本到不了 barrier；
  第一 thread 的 `barrier.wait(timeout=2.0)` 逾時（`BrokenBarrierError`）後獨自 commit 放鎖，
  第二 thread 才接續讀到最新 stock=7 再扣 4 → 最終 stock=3。**deterministic 通過**。

barrier timeout(2s) < busy_timeout(5s)：第一 thread 必先逾時 commit、放鎖在第二 thread 的
5s 等待內，故不會 deadlock 也不靠運氣。patch target 為
`modules.cost.repository.cost_ledger.insert_in_session`（dispatch_request 是 lazy import，
與既有 `test_dispatch_ledger_insert_fails_full_rollback` 同 target）。

---

## 6. Verify（zero regression）

- `pytest modules/{workflow,cost,reporting}/tests/`：**568 passed / 1 xfailed / 3 failed**。
  - 568（原 565 + 並發 test 由間歇 fail 轉穩定 pass + 2 個新 regression test：lost-update + read-not-serialized）。
  - 剩 3 failed 全是 pre-existing numpy BLAS float 末位 drift（test_monte_carlo_k13_seed_42 /
    test_mc_percentiles_pinned / test_varfluct_year_1_pinned），多 run 完全穩定、與 SQLite 交易無關，
    非本 PR 引入（5/22-5/24 handoff 已記錄）。
- 廣域 blast-radius 驗證 `pytest modules/workflow/tests modules/monitoring/tests tests/`（含
  work_order / signoff / inventory / e2e）×2 run：**614 passed / 0 failed**（穩定）。
- 兩個並發 test 單獨複跑穩定 pass（修前該檔的 serialized test ~2/3 fail）。
- **兩個新 regression test 皆實測「修前必失敗、修後必過」**：
  - `test_dispatch_no_lost_update_under_forced_interleave`：immediate_transaction 失效時 stock=7（lost update）。
  - `test_read_transactions_not_serialized`：強制全交易 IMMEDIATE 時第二讀 busy_timeout(5s) → 失敗（守住 must-fix scope）。

---

## 7. Code review 採納

code-reviewer subagent 對 staged diff review：1 must / 2 should / 1 nice。

| 級別 | 議題 | 處置 |
|------|------|------|
| **Must-fix** | engine-wide `begin` event 把**所有**交易（含 reporting 長查詢 / list / dashboard 純讀）都升級 `BEGIN IMMEDIATE` → 取 RESERVED write lock → WAL 下本可並發的讀也被序列化（一個長讀卡住所有寫）。locking intent 對、但 scope 太寬。 | **採納（重做）** — 改 thread-local 旗標 + `immediate_transaction()` context manager：begin event 預設發 `BEGIN`（deferred，純讀維持 WAL snapshot read 不互鎖），只有 read-modify-write stock 路徑（`dispatch_request` / `add_return` / `InventoryRepository.adjust`）外層包 `immediate_transaction()` 才 `BEGIN IMMEDIATE`。begin event 與發起交易同 thread 同步執行，thread-local 取值正確。**新增 `test_read_transactions_not_serialized` 鎖住此行為**（讀也 IMMEDIATE 會 busy_timeout 失敗）。 |
| Should-fix | regression test `join(timeout)` 逾時靜默返回，後續 assert 可能讀到中間值 / 假性通過 | **採納** — 加 `assert not t1.is_alive() / not t2.is_alive()`。 |
| Should-fix | 缺「第二筆交易 busy_timeout 後 `OperationalError`」的 error-path 測試覆蓋（behavior 已正確，只缺覆蓋；upstream 需轉 503/429） | **不在本 PR 補（記 follow-up）** — scoped 修法後只有 stock 異動寫路徑短暫競爭，lock-timeout 機率大降；模擬 begin event 拋 `OperationalError` 的注入測試較重，另開 issue 補（含 API router 層 HTTP status 轉換）。 |
| Nice | `MaterialRequestRepository._next_business_key` 用 `COUNT` 而非 `MAX`（與 `WorkOrderRepository` fix #3 不一致，月內刪 MR 後序號可能撞 UNIQUE） | **不在本 PR（記 follow-up）** — 與本 issue 無關，另開獨立 issue 對齊。 |

reviewer 另確認三點修法**正確無需改**：(1) connect event `isolation_level=None` → WAL PRAGMA → begin event 的順序；(2) `patch.object` target（lazy import 解析到被 patch 的 module 屬性）；(3) monitoring raw sqlite3 reader 與 workflow `BEGIN IMMEDIATE` 在 WAL 下無互鎖。

### Follow-up（建議另開 issue）

- **WMOM 待開-A**：dispatch/adjust 在 busy_timeout 後 `OperationalError` 的 error-path 測試 + API router 轉 503/429。
- **WMOM 待開-B**：`MaterialRequestRepository._next_business_key` `COUNT` → `MAX` 對齊 work_order fix #3。

---

## 8. 下次接手指南

### 已完成（push 到 origin/claude/upbeat-davinci-s9Juu）

- engine 層 `BEGIN IMMEDIATE` 接上，根治並發 dispatch lost-update（庫存/ledger 一致性）。
- deterministic regression test。
- ISSUES.md / STATUS.yaml 更新；本 work-log。

### 待 close 條件

本 issue 為完整可驗證的 backend bug-fix，PR open 後即可標 done（不需劉老師本機長跑）。

### 建議下次 session 工作（依優先級）

1. **WMOM-20260519-01**（F1 超量退料 domain guard，0.5-1d）— 需劉老師 walkthrough 決定 guard 層級。
2. **M5 規劃** — RAG（Knowledge）+ 現場 mobile UI，需架構決策 + 外部依賴（ChromaDB / RAG_Ultimate 策略檔）。
3. **WMOM-20260513-02** demo orchestrator + simulator（2-3d 跨 session）。
4. **前端測試基礎設施**（vitest + RTL）— 回補 5/23 AbortController + 5/24 WS 殭屍重連的 regression test。

### 環境備忘（給下次 sandbox session）

sandbox 初始無 Python 測試依賴。開工先：

```bash
pip install pytest pytest-asyncio httpx sqlalchemy jinja2 pandas reportlab pytz scipy
pip install -r requirements.txt
```

（仍建議另開 issue 把 test 依賴補進 requirements-dev.txt + SessionStart hook。）
