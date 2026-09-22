# 2026-09-22 — live/OPC 後端硬化收尾（WMOM-20260720-04 + WMOM-20260720-08）

> Session 類型：實作
> Session 長度：中
> 主導：Claude（autonomous worker）
> 結果：M6 現場部署唯一硬阻塞的 5 個延後子問題一次修完，逐項 mutation-verified；code-reviewer
> subagent 一輪 review 抓到 2 Must-fix + 1 Should-fix 皆已修復並重新驗證；backend 1093 passed
> （+17）/ frontend 957 passed 全綠回歸；PR #待補（見下方 GitHub 狀態）。

---

## 1. Session 目標

依 §4 決策樹（M6 critical path 優先）認領 `WMOM-20260720-04` + `WMOM-20260720-08`——#144/#146/#147
review 累積延後、排「M6 實接前」處理的 live/OPC 後端硬化，共 5 個獨立子問題：

1. `DataBroker.stop()` 未呼叫 `_opc_adapter.stop()` → 切走 live 後孤兒輪詢 thread 續寫新 session。
2. 切走 live 無角色檢查（起 live 需 SUPERVISOR，切走卻不需，不對稱）。
3. `config.py::set_simulation` 在非即時模擬來源時靜默 `switch_mode` 回 simulation（斷 live SCADA）。
4. `DataBroker.start/stop/switch_mode` 全程無鎖（連點兩下 `/api/source/select` 可能撞例外）。
5. `simulator/engine.py` `_loop` 的 `time.sleep(time_step)` 不可中斷（`stop()` 卡到該次睡眠結束）。

---

## 2. 實際完成

### 2.1 主要工作

1. **(1) OPC adapter 停止**：`DataBroker.__init__` 補 `self._opc_adapter: Optional['OPCDAAdapter'] = None`；
   `stop()` 加 `if self._opc_adapter is not None: self._opc_adapter.stop(); self._opc_adapter = None`。
2. **(2) 切走 live 角色檢查**：`routers/source.py::select_source` 加
   `if b.source_kind == "live" and mode != "live": require_role(Role.SUPERVISOR)(request)`，
   對稱起 live 既有的檢查。
3. **(3) set_simulation definitive fix**：`routers/config.py::set_simulation` 開頭加
   `if b.source_kind not in (None, "simulation"): raise HTTPException(409, ...)`，直接拒絕而非
   讓它落到 `switch_mode(SIMULATION)`。
4. **(4) 生命週期鎖**：`DataBroker.__init__` 加 `self._lifecycle_lock = threading.RLock()`（可重入，
   因 `switch_mode` 同執行緒內會呼叫 `stop()` 再 `start()`）；`start`/`stop`/`switch_mode` 三個方法
   整段包進 `with self._lifecycle_lock:`。**自行擴大範圍**：發現 `select_view_only()`（`/api/source/
   select {mode:view}` 的實際路徑）與 `switch_farm()` 也是呼叫 `stop()` 後繼續修改
   `source_active`/`source_kind`/`simulator` 的公開入口，若不一併上鎖，這兩者仍可能與別執行緒的
   `start()`/`switch_mode()` 交錯——用受控延遲（monkeypatch `_init_farm_storage` 插入 0.3s 睡眠）
   確定性重現：`select_view_only` 最終回報 `source_kind='view'`，但同時插進來的 `start()` 已真的建了
   simulator + 起了 maintenance thread，兩者狀態互相矛盾（`_maintenance_running=True` 卻宣稱無來源）。
   兩者也一併包進同一把鎖。
5. **(5) engine 可中斷睡眠**：`WindFarmSimulator` 加 `self._wake = threading.Event()`；`start()` 進場
   `clear()`（重入啟動不被舊旗標打斷）、`stop()` 呼叫 `set()`；`_loop` real-time 分支
   `time.sleep(time_step)` → `self._wake.wait(time_step)`。

### 2.2 Mutation 驗證（Phase 5 規定，逐項做）

對每個修正，把實作改回舊邏輯 → 確認新測真的 fail → 還原：

| # | 修正 | 還原後結果 |
|---|------|-----------|
| 1 | 移除 `_opc_adapter.stop()` 呼叫 | `test_stop_stops_opc_adapter_and_clears_reference` fail（`stopped is False`） |
| 2 | 移除 source.py 角色檢查 | `test_switch_away_from_live_requires_supervisor` + `..._to_view_...` 兩個 fail（200 != 403） |
| 3 | 移除 config.py 409 guard | 3 個 parametrize（view/live/scenario）全 fail（200 != 409） |
| 4 | `_lifecycle_lock` 換成 `contextlib.nullcontext()` | 獨立壓測腳本（4 threads×30 輪、mock 掉 session I/O）20s 內即重現 15 次真實例外：`IntegrityError: UNIQUE constraint failed: farms.farm_id` + `OperationalError: database is locked`；加鎖後同壓測 0.77s、零例外 |
| 4c | `select_view_only()` 的 `with self._lifecycle_lock:` 移除 | 用隨機 hammer（4 threads×30 輪）測連續跑 5 次都沒抓到（GIL 排程運氣太差，抓不到就是沒鎖住的警訊）；改用受控延遲（monkeypatch `_init_farm_storage` 插入 0.3s 睡眠 + 另一執行緒延遲 0.05s 呼叫 `start()`）確定性重現：`source_kind='view'` 但 `_maintenance_running=True` 同時成立，斷言失敗；加鎖後 100% 通過 |
| 4b | 移除 `start()` 的 `self._wake.clear()` | `test_restart_after_stop_does_not_wake_immediately` fail（重入啟動後舊旗標未清，`is_set()` 仍 True） |
| 5 | `self._wake.wait(...)` 還原成 `time.sleep(time_step)` | `test_stop_returns_promptly_during_real_time_sleep` fail（4.95s vs 門檻 <1.0s） |
| 1b（review 後補） | `OPCDAAdapter._poll_loop` 的 `self._wake.wait(...)` 還原成 `time.sleep(...)` | `test_stop_returns_promptly_during_poll_sleep` fail（4.95s vs 門檻 <1.0s） |
| 1c（review 後補） | `OPCDAAdapter.start()` 的 `self._wake.clear()` 移除 | `test_restart_after_stop_does_not_wake_immediately`（opc_adapter 版）fail（`is_set()` 仍 True） |

第 4 項因牽涉真併發（thread race），先用 pytest 版本嘗試（4 threads×50 輪、真實 SQLite session
create/end）——**卡住超過 5 分鐘**（不是死鎖，是無鎖下 SQLite busy_timeout + farm registry
UNIQUE 衝突反覆重試疊加的慢速失敗）；改寫成獨立腳本（mock 掉 `Storage.create_session`/`end_session`、
單機組、30 輪），才在合理時間內拿到乾淨的失敗證據，據此把正式測試也改成同款輕量版本（見產出清單）。

### 2.3 Code review 一輪（`code-reviewer` subagent，Phase 6）

跑 diff review，回報 2 Must-fix + 1 Should-fix + 2 Nice-to-have。逐項處理：

- 🔴 **Must-fix「`switch_farm()`/`select_view_only()` 仍在鎖外」**：review 送出時我已自行擴大範圍
  把這兩個方法包進鎖（見 §2.1 第 4 項），但 review 是對送審當下的 diff 做的，仍正確點出這是「先關掉
  start/stop/switch_mode race」修法沒關完的漏網之魚，且直接點名這正是 ISSUES.md 自陳的
  `farms.farm_id` UNIQUE 撞鍵症狀的殘留路徑——**驗證已修**（我的 self-review 動作早於報告送達，但
  review 的診斷本身完全正確且更深入，特別是指出這會讓剛加的「切走 live 需 SUPERVISOR」判斷可能被
  交錯覆寫繞過）。
- 🔴 **Must-fix「OPC adapter 的 `_poll_loop` 睡眠仍不可中斷」**：`self._opc_adapter.stop()` 這次補上了，
  但 `OPCDAAdapter.stop()` 本身的 `join(timeout=10)` 若撞上不可中斷的 `time.sleep(self._poll_interval)`
  （Z72 預設 17 秒）仍會逾時，孤兒 thread 續寫新 session 的窗口只是被縮小（~7 秒）而非關閉。比照
  engine.py 同款加 `threading.Event`，`_poll_loop` 兩處 sleep 都改 `wait()`，新增
  `test_opc_adapter_stop_responsive.py`（2 測，同款 mutation-verified）。
- 🟡 **Should-fix「壓測 mock 在第一輪後失效」**：`test_concurrent_start_stop_does_not_race` 對
  `broker.storage` 的 monkeypatch 在 `start()` 第一次呼叫觸發 `_init_farm_storage()`（因
  `_active_farm_id` 初始為 None）換掉 `self.storage` 後就失效——之後全程都是真實 SQLite 寫入。改成
  測試一開始先設定 `broker._active_farm_id`，讓 `start()` 內那個分支全程不觸發，`self.storage` 就不
  會被換掉，mock 才真的全程生效。
- 🟢 Nice-to-have（`set_datasource` 同款守門缺口 + role 檢查順序的 fail-closed 語意）：前者記進
  §7 open questions（超出本次 issue 範圍，未展開）；後者補了一句 docstring 說明（見
  `routers/source.py`）。

### 2.4 卡住或延後的事

- 無阻擋項。第 4 項的壓測腳本設計花了較多時間排錯（見上）。

### 2.5 重大決策（如有）

無架構級決策，不寫 decision_log。純 bug-fix 性質，符合原 issue 草擬的修法方向。

---

## 3. 產出清單

### 新增檔案

- `modules/monitoring/tests/test_engine_stop_responsive.py` — engine `_loop` 睡眠可中斷性（2 測）
- `modules/monitoring/tests/test_data_broker_lifecycle.py` — OPC adapter 停止 + 併發 start/stop 壓測 +
  `select_view_only()` 與併發 `start()` 的確定性交錯測試（4 測）
- `modules/monitoring/tests/test_config_set_simulation_gate.py` — set_simulation 來源守門（5 測，含 3 組 parametrize）
- `modules/monitoring/tests/test_opc_adapter_stop_responsive.py` — OPC 輪詢睡眠可中斷性（2 測，review 後補）

### 修改檔案

- `modules/monitoring/server/data_broker.py` — `_opc_adapter` 初始化 + stop 邏輯、`_lifecycle_lock`（RLock）包住 start/stop/switch_mode/select_view_only/switch_farm
- `modules/monitoring/server/opc_adapter.py` — `_wake` Event 取代 `_poll_loop` 兩處 `time.sleep`（review 後補）
- `modules/monitoring/server/routers/source.py` — 切走 live 對稱要求 SUPERVISOR + docstring 補角色檢查順序說明
- `modules/monitoring/server/routers/config.py` — `set_simulation` 非即時模擬來源時 409
- `modules/monitoring/simulator/engine.py` — `_wake` Event 取代 real-time 分支的 `time.sleep`
- `modules/monitoring/tests/test_source_selection.py` — +4 測（切走 live 角色檢查正負向 + 對照組）
- `ISSUES.md` — WMOM-20260720-04 + WMOM-20260720-08 標 done（統計表 open 13→11、done 100→102）
- `STATUS.yaml` — `last_updated`、`next_milestone`、M6 `progress` 20→25、`issue_stats` 同步
- `TODO.md` — 更新最後更新時間 + baseline 數字，標註內文其餘段落仍是 2026-07-18 舊快照（未展開重寫，超出本次範圍）

### 動了狀態的 issue

- WMOM-20260720-04: open → done
- WMOM-20260720-08: open → done

### 寫進 decision_log 的決策

- 無

---

## 4. 下次怎麼接手

1. **最該做的事**：`WMOM-20260720-13`（A1 round-2 review 的 4 個 Should-fix，見 ISSUES.md 該條目）——
   有明確 diagnosis + 修法草案，屬 autonomous-friendly。
2. **第二優先**：`WMOM-20260716-06`（footprint CPU-torch pin，需 docker 環境驗）或
   `WMOM-20260509-F6`（PostgreSQL row-lock integration test，需 docker postgres）——兩者都卡在本
   sandbox 無 docker，若下個 session 有 docker 環境可挑。
3. **阻擋項**：無。GitHub MCP 這次可用，但因故障排錯耗時，若時間不夠可能來不及在本 session 開 PR
   （見下方 GitHub 狀態一節，push 之後補記）。

---

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 讀 issue + 相關程式碼定位 5 個子問題 | 20% |
| 寫修正（5 處） | 25% |
| 寫新測 + 既有測試補強 | 20% |
| Mutation 驗證（含第 4 項排錯壓測腳本） | 25% |
| 全套 baseline 驗證（backend + frontend）+ 文件收尾 | 10% |

---

## 6. 學到的事

- **真併發 race 的 mutation 測試不能直接上大量真 I/O**：第一版壓測（4×50 輪、真 SQLite session
  create/end）在無鎖情況下不是乾淨拋例外，而是「busy_timeout + UNIQUE 衝突重試」疊加成類似掛住的
  慢速失敗，浪費了排錯時間。mock 掉非本次驗證目標的 I/O（session 讀寫）、縮小規模（單機組、30 輪），
  才能在合理時間內拿到乾淨、可重現的失敗證據。
- **`threading.RLock` 而非 `Lock`**：`switch_mode` 在同一執行緒內呼叫 `stop()` 再 `start()`，若用一般
  `Lock` 會自我死鎖；`RLock` 允許同執行緒重入，同時仍擋掉跨執行緒的併發。
- **隨機 hammer 測試「連續幾次都過」不代表沒問題，可能只是抓不到**：`select_view_only()` 的鎖遺漏一開始
  用 4 threads×30 輪隨機壓測，連續 5 次全過（GIL 排程下這段交錯視窗太短、機率太低）。改用「monkeypatch
  注入固定延遲」構造確定性交錯後，100% 重現。教訓：mutation 驗證時若隨機壓測測試「怎麼跑都過」，不能
  當作「修法沒用」的證據，反而該懷疑是測試本身抓不到——這種情況要換成受控延遲的確定性版本，而不是放棄
  驗證或调大迭代次數硬賭機率。
- **修一個鎖時要盤點所有會動到同一組欄位的公開入口**：原 issue 只點名 `start/stop/switch_mode`，但
  `select_view_only()` 與 `switch_farm()` 這兩個常被忽略的入口也會在 `stop()` 之後繼續修改
  `source_kind`/`simulator` 等欄位，若不一併上鎖，鎖等於只做了一半。
- **`Event.wait()` 取代 `time.sleep()` 這個修法模式已是本 repo 第三次用**（#147 的 maintenance
  thread、本次的 engine `_loop`）——下次遇到「背景迴圈的固定睡眠讓 stop() 反應慢」時可直接套用，
  記得同時處理「重入啟動要 clear() 舊旗標」這個容易漏掉的配套修正（本次也差點漏掉，靠對照測試抓到）。

---

## 7. Open questions（park）

- `simulator/engine.py` 的 accelerated 分支（`time_scale > 1` 時的 `time.sleep(wall_sleep)`，第 330
  行附近）有同款「不可中斷睡眠」問題，但本次 issue 文字只點名 line 310（real-time 分支），故未動。
  若之後要用到高倍速模式且在意 stop() 響應性，值得補一併修掉。
- `config.py::set_datasource`（`/api/config/datasource`，供前端 Settings 頁 OPC 設定用）目前沒有比照
  `set_simulation` 加來源守門；本次 issue 範圍只點名 `set_simulation`，未展開，若之後發現同款問題再開
  新 issue。
