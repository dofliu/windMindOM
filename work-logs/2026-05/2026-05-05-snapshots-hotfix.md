# 2026-05-05 — Snapshots 表失控 hotfix（WMOM-20260505-01）

> Session 類型：實作（hotfix）
> Session 長度：中
> 主導：Claude
> 結果：3 件事一起做 — cleanup retention + broker dedupe + VACUUM INTO 工具

---

## 1. Session 目標

劉老師 2026-05-05 截圖：彰化離岸風場台電 farm 的 `wind_farm.db` 累積到 41.9 GB。經分析確認根因（見 ISSUES.md WMOM-20260505-01）：

- `turbine_snapshots` 表 1,081 萬 row 佔絕大部分容量
- 17.5 天 / 19,594 個 distinct event_ref / 每 event 平均 606 row
- 三個放大因子疊加：
  1. `storage.run_cleanup` 不清 snapshots
  2. `data_broker._trigger_snapshot` 每次重 trigger 都 retroactively 重寫 in-memory history
  3. simulator state machine 在 stop=7 附近 flapping，每幾秒重新 emit 同類 stop event_ref

3 件事一起做：cleanup retention / broker dedupe / VACUUM INTO 工具。

---

## 2. 實際完成

### 2.1 主要工作

- ✅ **storage.run_cleanup 加 snapshots retention**（預設 7 天，0 = 不清 legacy 模式）
- ✅ **data_broker._trigger_snapshot dedupe + 5 分鐘 cooldown**：
  - `_extract_event_class` static method 截 ISO timestamp 取 dedupe key
  - 同 turbine 同 event_class 在 cooldown 內 → 僅延長 active window，**不重 retroactive**，不改 event_ref（保 grouping）
  - DataBroker 新增 class const：`SNAPSHOTS_RETENTION_DAYS = 7`、`SNAPSHOT_DEDUPE_COOLDOWN_S = 300`
- ✅ **tools/vacuum_db.py CLI**：cleanup → VACUUM INTO sibling → swap 三步驟，含 dry-run / row-count diff / EXCLUSIVE lock pre-check
- ✅ **Tests +19** 全 PASS：
  - test_storage_cleanup.py × 6（cleanup retention 三表 / 0=keep all / 空 DB / no-op）
  - test_broker_snapshot_dedupe.py × 13（含 5 個 parametrized regex + 7 個 dedupe 行為 + 1 個壓力 + 1 個 cooldown regression）
- ✅ Code review by code-reviewer agent — 10 finding（6 must-fix + 3 should-fix + 1 nice-to-have）**全處理**

### 2.2 Code review fix 重點

| Finding | 修法 |
|---|------|
| #1 cooldown 路徑刷新 last_class timestamp（**真實 bug**）— 持續 flapping 永不過期 | 改為「不更新 timestamp」，cooldown 從第一次同類 trigger 起算；新增 `test_cooldown_starts_from_first_trigger_not_latest` regression |
| #2 regex 對 `:YYYY` 寬鬆匹配可能誤截 turbine_id 含年份的 ref | 強化為 `:\d{4}-\d{2}-\d{2}T\d{2}:`（要時分都對） |
| #3 `_snapshot_last_class` 在 active window 結束時不清 | 加註解說明刻意保留（cooldown 機制需要） |
| #4 vacuum SQL string 構造 | 加 path traversal assertion + escape 註解 |
| #5 vacuum dry-run 訊息誤導 | 移除 `target.exists()` dead code |
| #6 vacuum swap 中途斷電 | 加 `_check_app_stopped()` EXCLUSIVE lock pre-check |
| #8 test docstring 與 assertion 語意不符 | 改為「單一 cooldown window 內」+ 補跨 cooldown regression |
| #9 `_seed_raw` 缺欄位 | 加註解標明「不適合 aggregation test」 |
| #10 7 天 retention 取捨 | 寫進 [`docs/product/decision_log.md`](../../docs/product/decision_log.md) DEC-20260505-01 |

### 2.3 實際執行 VACUUM 結果（劉老師 2026-05-05 跑）+ 加 --purge-snapshots

劉老師跑 `tools/vacuum_db.py` retention=7 天 → **只省 50 MB / 0.1%**：

```
removed: raw=0  1m=0  snapshots=2,135
✅ Done. 41.89 GB → 41.84 GB  (saved 50.82 MB, 0.1%)
```

**原因**：分析 distinct (turbine_id, timestamp) 發現 1080 萬 row 裡 **98.9% 都是重複** —
只有 11.7 萬 row 是真實 distinct timestamp。retroactive write 把 in-memory 600 row 
歷史一寫再寫，retention-based cleanup 清不掉（重複 row 的 timestamp 也都在 7 天內）。

**修補追加**（小延伸）：加 `tools/vacuum_db.py --purge-snapshots` flag：
- 強制 truncate 整個 turbine_snapshots table（跳過 retention 邏輯）
- 救火用：retroactive write bug 累積的「重複 row 全在 retention 內」場景
- +5 tests `test_vacuum_db.py`（含 dry-run / purge+cleanup 互動 / fresh row 也清）
- 對應 row count mismatch check 加 `not purge_snapshots` 條件

劉老師 SOP 改為：
1. 停 `python run.py`
2. `rm wind_farm.db.bak`（先前 vacuum 留下的，41.89 GB 釋放）
3. `python tools/vacuum_db.py "..." --purge-snapshots` → 41.84 GB → ~50 MB

### 2.4 重大決策

- **DEC-20260505-01**：turbine_snapshots 預設 7 天 retention（取代既有 schema permanent）— 寫進 decision_log

---

## 3. 產出清單

- 修改 `modules/monitoring/server/storage.py`
- 修改 `modules/monitoring/server/data_broker.py`
- 新增 `modules/monitoring/tests/test_storage_cleanup.py`
- 新增 `modules/monitoring/tests/test_broker_snapshot_dedupe.py`
- 新增 `tools/vacuum_db.py`

## 4. 下次怎麼接手

劉老師執行 VACUUM 釋放實際 41.9 GB 磁碟空間（步驟見 `tools/vacuum_db.py --help`）。

## 5. 學到的事

- "Permanent" 在 schema 註解裡是 design intent 但實作 bug：snapshots 永久不清等於沒有 retention 控制
- Retroactive write 是 amplifier — 不只資料來不及清，還主動「補寫」舊資料每次重 trigger
- Edge-trigger 在 simulator 已正確（`if last_state != current_state`），但 state machine flapping 把 edge 變成 high-frequency edges → broker 端必須有 cooldown 守門
