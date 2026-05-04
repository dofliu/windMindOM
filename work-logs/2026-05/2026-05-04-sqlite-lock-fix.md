# 2026-05-04 — SQLite 並發 lock 修復（WMOM-20260504-09）

> Session 類型：bug fix（production crash）
> Session 長度：短（~25 分鐘）
> 主導：Claude（劉老師回報實際跑 monitoring 時碰到 OperationalError）
> 結果：3 處 sqlite connection 加 WAL + busy_timeout PRAGMA，3 個 stress test pass，1 秒內 8,800+ ops 並發無 lock

---

## 1. Session 目標

WMOM-20260504-09 — bug fix。劉老師實際跑 `python run.py` 時（M1 deliverable）
浮現 SQLite 並發 lock 問題：

```
sqlite3.OperationalError: database is locked
[DataBroker] Maintenance error: database is locked
GET /api/maintenance/technicians 500 Internal Server Error
```

跡證：在 `modules/monitoring/server/storage.py:799` `query_technicians()` 撞到。

## 2. 根因分析

**問題**：

1. SQLite 預設 `journal_mode=DELETE` + `busy_timeout=0` — 撞鎖立刻 raise
2. 系統同時跑 4 個 thread 操作同一個 DB：
   - FastAPI asyncio handlers（GET /api/turbines、/api/maintenance/technicians）
   - DataBroker write callback（每 10s INSERT 大量 turbine_data）
   - **Maintenance thread**（每 5 分 downsampling、每 1 小時 cleanup — 持有 write lock 較久，**真兇**）
   - Simulator background（持續產生 data）

當 Maintenance thread 跑 DELETE/UPDATE 時，整個 DB 鎖住，其它 thread 連 SELECT 都 fail。

## 3. 解法

業界標準 SQLite 並發配置（5 行 PRAGMA）：

```python
conn = sqlite3.connect(db_path, timeout=10.0)
conn.execute("PRAGMA journal_mode=WAL")    # writer 不 block reader
conn.execute("PRAGMA synchronous=NORMAL")  # WAL 下安全的折衷
conn.execute("PRAGMA busy_timeout=5000")   # 鎖住時等 5 秒再 raise
```

抽成 `modules/monitoring/server/sqlite_utils.py:open_sqlite()` helper，
`storage.py` + `farm_registry.py` 都用。

## 4. 實際完成

### 4.1 主要工作

- ✅ 新增 `modules/monitoring/server/sqlite_utils.py`（55 行）：
  - `open_sqlite(db_path, timeout=10.0)` — 建議的 connection 入口
  - `configure_sqlite_pragmas(conn)` — 已開的 connection 補套用 PRAGMA
- ✅ 改 `modules/monitoring/server/storage.py`：
  - `_get_conn()` 改用 `open_sqlite()`
  - `_init_db()` 也改用 `open_sqlite()`（首次連線就把 WAL 寫進 DB header）
  - import 路徑：try `from .sqlite_utils` else fallback `from sqlite_utils`（兼容
    `run.py` 的 sys.path 注入）
- ✅ 改 `modules/monitoring/server/farm_registry.py`：
  - `_get_conn()` 改用 `open_sqlite()`
  - 同樣 try/except import fallback
- ✅ 新增 `modules/monitoring/tests/__init__.py` + `test_storage_concurrency.py`（130 行）：
  - `test_pragmas_applied` — 驗證 connection 開後 journal_mode==WAL、busy_timeout==5000
  - `test_concurrent_read_write_no_lock` — 4 thread（2 reader + writer + deleter）並發 1 秒，
    驗證 0 errors 且每 thread 都跑出 10+ ops
  - `test_storage_basic_crud_still_works` — regression：CRUD 仍正常
- ✅ Stress test 結果：1 秒內 reader_a=4062 / reader_b=4591 / writer=178 / deleter=49 ops，**0 lock errors**
- ✅ 整 modules/ 全 test suite：**32 PASS + 1 XFAIL**（含 cost 30 + monitoring 3）

### 4.2 沒動的 SQLite 使用點

`modules/monitoring/scada_system.py` 也有 `sqlite3.connect()` 用法（4 處）— 看起來是
legacy module，與 `Storage` 不共用 DB path，不在用戶報告的 lock crash 路徑上。
**留待未來 issue**（如果 scada_system 仍在用，再評估）。

### 4.3 重大決策

- 選 **共用 helper** 而非每個 _get_conn 各自 inline PRAGMA — DRY，未來若再加 PRAGMA
  （例如 `mmap_size`、`cache_size`）只改一處
- `synchronous=NORMAL`（vs FULL）— WAL 下這是業界推薦折衷，效能好且 crash-safe
- `busy_timeout=5000ms` — 經驗值，足以吸收 maintenance thread 的長 DELETE，
  但又不會讓 client 等到超時

## 5. 產出清單

### 新增檔案

- `modules/monitoring/server/sqlite_utils.py`（55 行）— SQLite 連線統一設定
- `modules/monitoring/tests/__init__.py`（空）
- `modules/monitoring/tests/test_storage_concurrency.py`（130 行）— 3 tests
- `work-logs/2026-05/2026-05-04-sqlite-lock-fix.md`（本檔）

### 修改檔案

- `modules/monitoring/server/storage.py`（_get_conn + _init_db 改用 open_sqlite）
- `modules/monitoring/server/farm_registry.py`（_get_conn 改用 open_sqlite）
- `ISSUES.md`（新增 WMOM-09 done；統計 +1 done）
- `STATUS.yaml`（issue_stats +1 done；overall progress 41→42）

### 動了狀態的 issue

- WMOM-20260504-09: 新建 + done

## 6. 下次怎麼接手

回到 M2 軌道：**WMOM-20260504-07 FastAPI cost router**（10 個 schema + adapter
都 ready，~30-45 分鐘）。

劉老師若再跑 monitoring：
- 不用任何遷移動作 — DB 第一次被 _init_db open 時就會切 WAL mode（持久化在 DB
  header），舊 DB 也會自動升級
- 會看到 `wind_farm_data.db-wal` + `.db-shm` 兩個輔助檔（已 gitignore）
- API response time 預期會略快（WAL 比 DELETE journal mode 高效）

## 7. 學到的事

- **production debug 第一手 log 最值錢** — 用戶提供的完整 stack trace 直接指到
  `storage.py:799 query_technicians`，省掉所有定位時間
- **SQLite 並發默認設定不適合 production** — 不只是 windMindOM，任何帶 background
  thread 的 SQLite app 都該預設 WAL + busy_timeout
- **try/except import 模式**（`from .sqlite_utils` else `from sqlite_utils`）對應
  `run.py` 的 sys.path 注入策略 — 與其重寫所有 import，不如保持兼容
- **Stress test 證明價值**：1 秒 8,800+ ops + 0 errors 比口頭說 "WAL 應該夠用"
  有說服力得多
