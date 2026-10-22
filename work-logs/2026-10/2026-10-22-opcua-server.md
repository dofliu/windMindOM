# 2026-10-22 — WMOM-20261021-07：模仿 Bachmann Z72 tag 的 OPC UA server（EPIC-DS Phase 3c ③）

> Session 類型：實作
> Session 長度：中
> 主導：Claude（劉老師選定「繼續做 -07」，資料來源等四項由劉老師確認）
> 結果：WMOM-20261021-07 done

---

## 1. Session 目標

讓學生的 RAG 維修助手像接真實 PLC 一樣拿資料：
- 以 `asyncua` 實作 OPC UA server，節點路徑對齊真實讀取腳本 `shared/plc_clients/bachmann/opc_data_reader.py`。
- 資料來源：-06 的回放器或即時模擬；舊的 `modules/monitoring/opcua_interface.py` 不沿用。
- 啟動設定、用 asyncua client 讀回的整合測試。

## 2. 劉老師的決定（開工時確認，DEC-20261022-03）

| 問題 | 決定 |
|---|---|
| 資料來源 | 回放（CLI 綁一個回放，正式評測與 WS 共用時鐘）＋ 即時模擬（主程式環境變數開啟） |
| 合成 tag | 全部掛上，節點說明標示 synthetic |
| 連線身分 | 匿名唯讀 |
| 正式評測開播 | 出題端啟動 server 就開播 |

## 3. 實際完成

### 3.1 server `modules/monitoring/server/opcua_server.py`

- **節點**（namespace `urn:windmindom:z72sim`，字串 NodeId＝真實 OPC DA item ID）：
  - 讀值 `Z72.H{nn}.{group}.Z72PLC__UI_Loc_*`：欄位與盲測版資料包同一組，型別依 PLC（REAL32 → Float …），`SourceTimestamp`＝模擬時間，缺值 `BadNoData`、開播前 `BadWaitingForInitialData`。
  - `WMET.Z72PLC__UI_Loc_WMET_Analogue_WSpeedNacAvg10m`：真實讀取腳本會讀，但模擬器沒有輸出（開工時發現）。由 server 以 `WSpeedNac` 的 10 分鐘移動平均算出，節點說明寫 derived；真實讀取腳本的每個 item ID 都讀得到。
  - 事件碼陣列 `Z72PLC__ActiveAlarm` / `ActiveTrip1` / `ActiveTrip2` [0..20]（PLC 的 SINT16[21]；真實腳本只讀前 10 個）。
  - `WindMindOM.*` 狀態：`Source`、`Status`、`SimTime`、`PackId`、`Mode`、`Speed`。
- **安全**：只收匿名 identity token、關閉 asyncua 內建 admin、唯讀 user manager。
- **`ReplayFeeder`**：依時鐘推進（取樣週期 ÷ 速度，夾在 0.05–0.2 s），各機組只寫最新一筆讀值；事件流重建事件碼陣列；每 5 秒重讀回放。
- **`LiveFeeder`**：每秒讀 simulator 的最新讀值與 PLC 清單；批次期間與批次留下的讀值不發布。

### 3.2 事件碼陣列 `plc_protection.ActiveEventLists`

- 依成立順序、同一個碼只出現一次；A 由 `alarm_raised` / `alarm_cleared` 增刪，T1 / T2 由 `trip` / `trip_cleared` 增刪，`restart_blocked` 不動。
- 即時模擬由 `PlcProtection._emit` 同步更新；回放由事件流重建，同一個類別。
- 操作員復位為每個解除的鎖存另送 `trip_cleared`（code review S5，見 §3.6）。

### 3.3 CLI、WS、主程式

- **`tools/opcua_server.py <db> <回放 id>`**：`load_run`（檢查）→ 建好節點並監聽 → `start_clock`（正式評測寫入 `started_at`；練習把這次的起點寫進同一欄）→ 播到結束。
- **實作中改的一點**：第一版在 server 起來之前就開播，kit 端到端測試裡前幾分鐘的警報在客戶端連上前就過了。改為節點建好、開始監聽後才開播。
- **WS `/ws/replay?stream=false`**：只收預測、不送資料，等到情境結束送 `finished`；開播訊息加 `stream.data`。
- **主程式**：`WMOM_OPCUA_ENABLE=true` 才載入 asyncua、起即時模擬的 OPC UA（`server/opcua_config.py`，預設只聽 `127.0.0.1`）。

### 3.4 starter kit、合約

- `opcua_client.py`：用字串 NodeId 一次讀完目前值與事件碼陣列，比較前後兩次的陣列得到事件、交給基準助手，經 WS `?stream=false` 送預測。
- `stream_client.py` 抽出 `with_params` / `connect_options`；README「OPC UA」；`requirements.txt` 加 `asyncua>=2.1,<3`（root 也加）。
- 合約 v1.2：新增 §13；§12 `stream=false`、4412；`CONTRACT_VERSION` / vocabulary 1.2；範例資料包重產（資料檔逐位元不變，只有版本標籤）。

### 3.5 驗證時的觀察

- 只看模式（不送判斷）在 1200× 下看得到全部 5 個陣列變化；送判斷的版本只看到 1 個——原因就是上面「先開播」的問題。
- kit 端到端測試改用 600×：CI 變慢時，6 分鐘長的 262 警報仍在客戶端兩次讀值之間看得到。

### 3.6 code review（code-reviewer：Needs revision → 全修）

審查者寫了重現腳本（admin 登入、批次期間讀即時 OPC UA、移動平均、鎖存）。

**Must-fix**：
- **M1 帳號填 admin 就能寫**：asyncua 預設把帳號名 admin 當管理員、不檢查密碼。修法：只收匿名 identity token、`allow_remote_admin(False)`、自訂唯讀 user manager。admin 登入現在在建立 session 時就被拒（BadIdentityTokenRejected）。
- **M2 即時 OPC UA 播出產生中的考題**：批次與即時模擬共用 simulator。修法：批次期間 `idle`；跑過批次後先略過 `latest_data` 裡留著的讀值，等即時模擬寫入新的再發布；即時 OPC UA 預設只聽本機。批次注入的故障會留在即時模擬裡（既有行為），寫進合約與已知限制。
- **M3 練習回放的 OPC UA 與 WS 時鐘不同**：練習的 WS 連線各自從連上起算。修法：OPC UA 開播時把起點寫進 `replay_runs.started_at`（`anchor_practice_run`），`stream=false` 的練習連線用它；還沒播出 4412、這次已播完 4410。一般的練習連線照舊。

**Should-fix**：
- **S4**：移動平均遇到時間倒退就清空；`LiveFeeder` 在換 simulator / 跑過批次時重來，不見的機組改 `BadNoData`（`clear_turbine`）。
- **S5 事件碼陣列與鎖存不一致**：維護清除故障的 `maintenance_release` 也送 `operator_reset`（不解除鎖存），舊規則卻把跳機陣列清空；操作員復位不解除物理層保護停機（351），也被清掉。修法：`PlcProtection.operator_reset` 為每個解除的鎖存另送 `trip_cleared`，清單不在復位時清空。批次路徑不會呼叫操作員復位，既有資料包不變。新增「每一步陣列＝`active_codes()`」測試（含操作員復位與維護清除）。
- **S6 / S7 / S10 CLI**：撤銷 / 到期 / 刪除時狀態節點保留 10 秒再關；停止原因改用代碼；埠被占用 exit 1；`0.0.0.0` 時提示用主機名稱連線。
- **S8 kit 客戶端**：判斷改在另一個執行緒；送預測時連線已關、WS 握手失敗、播完時 OPC UA server 剛好關掉都不吐 traceback；讀值改用 dataclass。
- **S9**：`LiveFeeder` 改用 `get_current_data()`（有鎖）、Protocol 型別；`Node` / `Tuple` 型別。
- **S11–S14**：即時 OPC UA 預設 `127.0.0.1`；主程式關機 `try/finally`、開關判斷集中在 `opcua_config.py`、`LiveOpcUa.stop` 不吞掉呼叫端的取消；`utc_now()`、docstring；ISSUES / work-log；測試不再改模組共用的 fixture。

**Nice-to-have 採用**：
- 更新間隔依取樣週期與速度（原本固定 0.2 s，3000× 時一次跳 600 模擬秒）。
- 單次更新失敗只記錄、不中斷播出。
- 站號衝突（`WT01` 與 `WT001`）明確報錯。
- 事件碼陣列開播前也是 `BadWaitingForInitialData`，第一次推進寫入全部機組（改完後回放測試抓到「沒事件的機組陣列一直是等待中」，一併修）。
- 文件寫明 OPC UA 與 WS 要同一台電腦（或時鐘對準）。
- asyncua 限定 `>=2.1,<3`（只測過 2.1）。

**未採用**：
- session / subscription 上限：教室網路使用，記入已知限制。
- `stream=false` 不載入整個情境：`describe()` 需要，影響小。

## 4. 驗證

### 4.1 自動測試

`modules/monitoring/tests/test_opcua_server.py`，20 項，一律用 asyncua client 讀回：
- 規則：`ActiveEventLists`、`RollingMean`（含時間倒退）、更新間隔、站號與 item ID。
- 回放：節點型別、合成 tag 標示、瀏覽路徑；6 個檢查點的讀值（float32 比對）/ `SourceTimestamp` / 10 分鐘平均 / 事件碼陣列 / 狀態節點與回放訊息一致；真實讀取腳本的每個 item ID 都讀得到；寫入被拒。
- 撤銷時停止更新；正式評測的開播時機與 WS `stream=false` 共用時鐘；練習回放的 `stream=false` 對時、4412、4410。
- 即時模擬：讀值與 PLC 清單；批次期間與批次後不發布；機組不見改 `BadNoData`；即時清單與回放重建的清單一致；每一步陣列＝PLC 狀態；環境變數開關、預設位址、埠被占用。
- 安全：admin 登入被拒、匿名寫值 / 加節點被拒。
- CLI：練習播完、撤銷中途停止、埠被占用；kit 客戶端對真的 OPC UA + uvicorn WS 伺服器跑完一次（600×，預測含 `main_bearing`）。

既有的回放 / PLC / kit 測試：146 項通過（`operator_reset` 多送 `trip_cleared` 不影響既有斷言）。

### 4.2 完整 backend

1833 → 1853 passed / 7 skipped / 1 xfailed（frontend 沒有改動）。

## 5. 產出清單

### 新增

- `modules/monitoring/server/opcua_server.py`
- `modules/monitoring/server/opcua_config.py`
- `modules/monitoring/tests/test_opcua_server.py`
- `tools/opcua_server.py`
- `examples/rag_starter_kit/opcua_client.py`
- 本 work-log

### 修改

- `modules/monitoring/simulator/physics/plc_protection.py`（`ActiveEventLists`、`operator_reset` 送 `trip_cleared`）
- `modules/monitoring/simulator/engine.py`（`is_bulk_running`、`bulk_runs`）
- `modules/monitoring/server/storage.py`（`anchor_practice_run`）
- `modules/monitoring/server/routers/replay.py`（`stream=false`、練習回放對時、4412）、`server/replay.py`（關閉碼說明）
- `modules/monitoring/server/scenario_pack.py`（`scada_dict_values`）
- `modules/monitoring/server/app.py`（即時模擬的 OPC UA）
- `modules/monitoring/simulator/ground_truth.py`（`CONTRACT_VERSION` 1.2）
- `examples/rag_starter_kit/`（`stream_client.py`、README、requirements、vocabulary、重產的 manifest / 答案）
- `shared/data/rag_assistant_vocabulary.json`（1.2）、`requirements.txt`（asyncua）、`tools/replay_runs.py`（說明文字）
- 文件：
  - `docs/integration/rag_assistant_data_contract_v1.md`（v1.2、§13、§12 `stream=false` 與 4412）
  - `docs/product/EPIC-DS_realistic_data_source.md`（§5.3 註、§6.12）
  - `docs/product/decision_log.md`（DEC-20261022-03）
  - `ISSUES.md`、`STATUS.yaml`、`CLAUDE.md`、`TODO.md`

### 動了狀態的 issue

- WMOM-20261021-07：open → done

## 6. 下次怎麼接手

- **-08 難度與多樣性**：劉老師已選定先做「感測器故障 vs 真故障」（-08-a），四項決定：
  - PLC 只對被注入感測器故障的那支感測器改看量測值（其他照舊看製程值，健康機組與既有情境不變）。
  - 兩種感測器故障：讀值像真故障（例：主軸承 / 發電機繞組溫度感測器漂移觸發同樣的警報碼），與有專屬感測器故障碼的（例：274、326、237、436）。
  - 標準答案的 `component` 填被量測的元件、`category` 填 `sensor_fault`（與真故障同元件、不同類別）。
- **出題流程**：有受測端連著即時 OPC UA 時，不要在同一個主程式產生考題（批次的故障會留在即時模擬裡）。
- **OPC UA 只有目前值**：正式評測用 OPC UA 時，速度要選受測端讀得過來的（60× 時每次更新約一筆取樣）。
