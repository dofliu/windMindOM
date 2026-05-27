# 2026-05-27 — 修復並發 dispatch flaky 測試：實作 BEGIN IMMEDIATE 寫入序列化

> Autonomous daily worker session（2026-05-27 20:00 Asia/Taipei，雲端 sandbox）。
> Issue：**WMOM-20260527-02**（新開）。Branch：`claude/upbeat-davinci-2imrR`。
> 本日第二個 5/27 session（前一個是 WMOM-20260527-01 cost pinned 容差，已 merge）。

---

## 1. 為什麼做這個

開工 preflight 跑 baseline 撞到唯一剩下的紅燈：

```
FAILED modules/workflow/tests/test_dispatch_atomic_transaction.py::test_concurrent_dispatch_one_loses_when_stock_short
```

重跑 5 次：**3 pass / 2 fail**（約 40% fail）。連跑 20 次量化前後對比見 §3。

這是 5/27-01 修掉 3 個 cost numpy drift 後，**baseline 唯一剩下的不穩定來源** —— 每個 daily
session 的 preflight 都有近半機率紅燈，反覆被各 handoff 標為「既有 SQLite WAL flaky，
與本 PR 無關」帶過。決策樹第 1 條（known blocker：test fail 污染 baseline）。

### Root cause（真正原因，非單純 flaky）

`dispatch_request()`（material_request_repository.py:355）對庫存做 **read-modify-write**：

1. `SELECT ... with_for_update()` 讀 inventory item 的 stock
2. Python 端計算 `new = stock + delta`，不足則 raise `InsufficientStock`
3. `UPDATE` 寫回扣減後的 stock + 寫 cost_ledger
4. commit

問題：
- **`with_for_update()` 在 SQLite 是 no-op**（語法支援，不真做 row-lock）。
- **pysqlite 預設 `BEGIN DEFERRED`**：寫鎖（RESERVED lock）延後到 transaction 內
  **第一次寫**才取得，不是 transaction 一開始。

所以兩個並發 dispatch：兩 thread 都先 SELECT 讀到 `stock=5`，各自算 `5-4=1 ≥ 0` 通過，
各自 UPDATE 寫 `stock=1` 都 commit → **lost update / double-spend**（`results=[('mr1',None),('mr2',None)]`，
兩個都成功，但庫存只夠一個）。測試斷言「必有 1 成功 + 1 InsufficientStock」於是偶爾紅。

**關鍵發現**：`inventory_repository.py:105` 的 docstring 與 ISSUES.md A2 acceptance（line 1013）
早已**聲稱**靠「BEGIN IMMEDIATE + WAL + busy_timeout 序列化寫入」，連並發測試的 docstring
（`test_concurrent_dispatch_same_item_serialized_correctly`）都寫「驗 SQLite 自己的 BEGIN
IMMEDIATE 序列化」——但 `_get_engine` 從未真的把 BEGIN IMMEDIATE 接上。是**文件聲稱、
但從未實作的 invariant**。

> 與 WMOM-20260509-F6 的關係：F6 是 M6 客戶部署若選 PostgreSQL 才要補的「真實
> `SELECT FOR UPDATE` row-lock integration test」。本 issue 是 SQLite single-farm 單機
> 部署的正確性 + 測試確定性，兩者正交，本 PR 不碰 PostgreSQL。

---

## 2. 完成內容

### 2.1 實作 BEGIN IMMEDIATE 序列化（SQLAlchemy 官方 pysqlite recipe）

`modules/workflow/repository/work_order_repository.py`（全 workflow repo:
work_order / inventory / material_request / signoff 共用此單一 `_get_engine`）：

- **connect listener `_set_sqlite_pragmas`**：新增 `dbapi_conn.isolation_level = None`
  —— 關掉 pysqlite 自動發 BEGIN（轉 autocommit，PRAGMA 仍正常生效，因 autocommit 下
  PRAGMA 不需在交易內）。
- **新增 begin listener `_begin_immediate`**：每個 transaction 改發 `BEGIN IMMEDIATE`，
  transaction 一開始就取得 RESERVED 寫鎖。
- 在 `_get_engine` `sa_event.listen(eng, "begin", _begin_immediate)`。

效果：第二個並發 dispatch 的 `BEGIN IMMEDIATE` 被 `busy_timeout`（5s）擋住，等第一個
commit/rollback 後才放行，屆時讀到**已扣減的最新 stock** → 正確 raise `InsufficientStock`。
WAL 仍允許並發讀，只序列化寫入 —— 符合 single-farm 單機部署的正確性需求，且**讓程式碼
與它自己 docstring 聲稱的 invariant 對齊**。

### 2.2 補直接斷言的 regression test

`test_dispatch_atomic_transaction.py` 新增 `test_engine_serializes_writes_with_begin_immediate`：
直接斷言 engine 的 `isolation_level is None` + begin listener `_begin_immediate` 已註冊。
不依賴 thread timing（上面兩支並發 test 驗端到端行為，本支驗 driver 層設定），
若未來有人移掉 listener 讓寫鎖退回 DEFERRED，這支立刻紅 → 防止 flaky lost-update 復活。

---

## 3. Verify（zero regression + 確定性量化）

| 項目 | 改前 | 改後 |
|---|---|---|
| `test_concurrent_dispatch_one_loses_when_stock_short` 連跑 20 次 | ~60% pass（flaky） | **20/20 pass** |
| dispatch 測試檔 | 14 passed（偶爾紅） | 15 passed（+1 regression，連跑 3 次穩定） |
| 完整 backend `pytest modules/{workflow,cost,reporting}/tests/` | 568 passed + 1 flaky | **569 passed / 1 xfailed，連跑 3 次確定性** |
| `tests/`（含 e2e + physics） | — | **151 passed，零 regression** |

→ baseline 自此**完全綠且確定性**，preflight 不再有近半機率紅燈。

---

## 4. Code review

跑 `code-reviewer` subagent 對 staged diff（背景執行）。本次 session 為保全工作（雲端
ephemeral container 風險）先 commit/push 驗證完成的改動；review 回報後若有 must-fix
以 follow-up commit 補上並更新本節。

**自評（review 回報前）**：
- BEGIN IMMEDIATE 是 SQLAlchemy 官方 pysqlite serializable recipe，與 future engine 相容
  （`conn.exec_driver_sql` 在 2.0 begin event 為正規用法）。
- isolation_level=None 下 PRAGMA 仍生效已由「569 passed + WAL 並發行為正確」間接驗證。
- blast radius：所有 workflow 寫入交易 BEGIN IMMEDIATE grab 寫鎖 up front；single-process
  部署下測試全綠（workflow 全套 + e2e + physics 151 passed），busy_timeout=5s 吸收競爭，
  無觀察到死鎖 / 餓死。

---

## 5. 下次 session 接手建議

- 本 PR 後 baseline `569 passed / 1 xfailed`（workflow+cost+reporting）+ `tests/ 151 passed`
  完全確定性，preflight 應一次就綠。
- WMOM-20260509-F6（PostgreSQL row-lock integration test）仍 open（M6 部署前）；本 PR
  已讓 SQLite 路徑正確序列化，F6 只剩驗 PG `SELECT FOR UPDATE` 真實 row-lock 語意。
- 候選工：WMOM-20260519-01（F1 超量退料 domain guard，需劉老師會計語意決策）/
  WMOM-20260513-02 demo orchestrator simulator / 擴大 frontend 元件層測試（CostPage / FarmOverview）/
  A6 領料 frontend / A7 庫存 frontend。

---

## 6. 檔案異動清單

```
改  modules/workflow/repository/work_order_repository.py   （isolation_level=None + BEGIN IMMEDIATE begin listener）
改  modules/workflow/tests/test_dispatch_atomic_transaction.py（+1 regression test 直接斷言 driver 設定）
改  work-logs/2026-05/2026-05-27-dispatch-begin-immediate.md（本檔）
改  ISSUES.md / STATUS.yaml
```
