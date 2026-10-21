# 2026-10-21 — Phase 1b-b：PLC 保護層（警報 / 跳機改由物理訊號觸發）

> Session 類型：實作
> Session 長度：長
> 主導：Claude（劉老師指示「繼續做 -03-b PLC 保護層」）
> 結果：WMOM-20261021-03-b done；新增 WMOM-20261021-10（切出風速平均判定）

---

## 1. Session 目標

WMOM-20261021-03-b：以 `TurbineSpec` 真實設定值（-03-a）判定量測訊號，送出 Z72 真實事件碼；T1 正常伺服停機、T2 緊急變槳；跳機鎖存、依目錄 `max_per_hour` 自動重啟，超過需復位；修 7↔3 擺盪；保留「復位不等於修好」不變量（WMOM-20260719-01）。

## 2. 實際完成

### 2.1 新模組 `simulator/physics/plc_protection.py`

- `ProtectionRule`（碼、訊號、方向、設定值、遲滯、延時、`producing_only`、`gate`）；同一碼可有多條規則（葉片三段延時、021 對應冷卻水與機櫃兩種來源）
- `PlcProtection.evaluate()` 每步回傳新跳機 `(code, level)`；`turbine_physics.step()` 依等級 `_request_stop("emergency" if T2 else "normal", f"plc:{code}")`
- 鎖存：條件解除時看該碼一小時內跳機次數，≤ `max_per_hour` → `trip_cleared`；超過 → `restart_blocked`，`cmd_reset` → `operator_reset`（事件 008）
- 物理層保護停機補事件碼（`note_protection_stop`，從 `_request_stop` 呼叫）：超速 351/320、LVRT/HVRT/電網 481/482/475/489 + 021、切出 I 201（600 s 去重）
- 事件放有上限（512）的佇列，broker 每步 `drain_events()`

### 2.2 健康機組誤跳——三個坑

先接上就跑健康風場，出現誤跳，逐一處理：

1. **葉片同步 336（T2）**：兩個來源。(a) 感測器模型的漂移（上限 ±0.8°）與卡值讓兩片葉片讀數差超過 1° 達 5 s——量測估計健康機組約兩天一次 T2 誤跳；(b) 啟動時從 30° 大幅變槳到工作角，各葉片響應差異暫態可達 ~6.6°。處理：PLC 改判定**製程值**（感測器模型之前），並加 `pitch_settled` 判定窗（穩定發電 60 s 後）。量測穩定發電的健康製程值差異：超過 1° 最長連續 2 s、從未超過 3°。
2. **偏航煞車 228/260**：偏航時煞車鬆開壓力降到 ~20 bar，結束後 3 bar/s 回升，回升期間本來就低於 180 / 150 bar。加 `yaw_brake_settled` 判定窗（煞車施加 90 s 後）。
3. **延時語意**：批次路徑 dt = 5 s 時，單一樣本就滿足「持續 5 s」。改為嚴格大於（`timer > delay`），單元測試時點相應 +1 s。

### 2.3 故障引擎連動

- `FaultEngine`：移除 24 個 `threshold` 與 `active_alarms` 的 severity 判定；`alarm_codes` 只是預期碼；新增 `mark_tripped()` / `trip_code`
- `engine._run_one_step`：故障 tripped 時 `model.maintenance_lock = True`（`_update_state` 在 4/5/6/8 要求正常停機、並擋所有重啟路徑），取代每步 `cmd_emergency_stop` → 7↔3 擺盪消失
- `engine._link_faults_to_plc`：`active_alarms` = PLC 目前成立的預期碼；PLC 以預期 T 碼跳機 → `mark_tripped` + `on_fault_tripped` callback
- `generate_bulk(on_fault_tripped=…)`；`routers/config.py` 情境排程記 `kind="trip"` 事件、注入事件帶 `tripEvents: True`；`routers/scenarios.py` 依 trip 事件判斷已跳機（舊 session 沿用 severity 公式）
- broker：移除 severity「Fault alarm threshold reached」事件，改記 PLC 事件（`source="plc"`）

### 2.4 途中修的兩個 bug

- **T2 被降級**：故障 tripped 後引擎設 maintenance_lock，`_update_state` 同一步要求正常停機，蓋掉 PLC 剛要求的緊急停機 → `_request_stop` 不再把已排定的緊急停機降級
- **blade_icing 以 336 跳機**：情境對葉片 1 加了 `2°×嚴重度` 的變槳 bias，PLC 正確地判成葉片不同步 T2，與預期碼 236 不符 → 移除 bias（結冰的特徵是振動與功率，不是單片變槳差）

### 2.5 驗證

- 健康 3 機風場（自動風況，含紊流、偏航）2 h：0 個訊號判定事件
- 11 情境滿嚴重度（15 m/s、25 °C）都以預期碼跳機，事件序列見設計文件 §6.3
- 健康機組既有 111 tag 輸出與 -03-a 之前逐位元相同（0 差異）
- `examples/data_quality_analysis.py`：20 通過 / 0 待改善（不變）
- backend 全套：1471 → **1521 passed** / 7 skipped / 1 xfailed（frontend 未動；review 修正前 1507）

### 2.6 Code review（code-reviewer subagent）

結論 Needs revision：2 must-fix、6 should-fix、5 nice-to-have。處理如下：

- **must-fix 1：只清故障不 reset 機組會永久停機**。一小時內第二次 228 跳機（手冊每小時上限 1）留下 `restart_blocked`；`/api/faults/clear` 不帶機組、情境批次、測試計畫都只清故障不 reset 機組，修好的機組永遠停在 TurSt 1。修法：維修鎖由 True 變 False 時，引擎呼叫新增的 `PlcProtection.maintenance_release`（清每小時跳機計數與封鎖、送事件 008）。不直接用 `operator_reset`：修好後殘餘條件（液壓回壓中）仍成立時，解除鎖存會立刻再跳一次。
- **must-fix 2：T1 跳機原因被蓋成 `maintenance_lock`**。PLC 在步末要求正常停機，下一步引擎設維修鎖、`_update_state` 再要求一次同模式停機 → 覆寫 `shutdown_cause`。修法：已有停機要求時不再要求；broker 把 `plc:<碼>` 分類為 `Automatic fault stop: PLC event <碼>`（原 `fault:` 分支已無人使用）。
- **should-fix 已修**：判定窗關閉不再等於條件解除（`_rule_on` 成立後只依遲滯解除）；`generate_bulk` 結束清空 PLC 佇列；broker 事件時間戳由 reading 模擬時間回推；value / setpoint 取實際成立的規則；延時改為「從第一個越限樣本起算 ≥ 延時」（dt = 1 s 時與原本完全相同，dt = 5 s 時 3 s 規則從 1 個樣本改為 2 個）；物理層保護停機改以每次起動（進入 4 / 8 / 6）為一個週期。
- **測試補強**：`test_plc_event_recording.py`（新，broker 記錄與時間戳、PLC 停機分類）、情境端點 trip 事件接線、`test_reset_keeps_fault.py` +2（訊號路徑 T1 原因與復位 + 啟動、只清故障的二次跳機）、`test_plc_protection.py` +10。兩個 must-fix 的測試都做了 mutation 驗證（拿掉修正 → 失敗）。
- **nice-to-have 已修**：LVRT band ≥ 2 與電網 < 0.81 p.u. 一致對應 482；`enabled=False` 時不擋重啟；`API_GUIDE.md` 註記 `alarm_codes` 移除 `threshold`、新增 `trip_code`；補 docstring。
- **未修**：每小時計數在解除時判定（手冊未說明，列設計文件已知限制）；`update_spec` 與 sim 執行緒的競爭（`switch_farm` 既有模式，非本次引入）。
- 修正後健康 111 tag 仍逐位元相同；`data_quality_analysis.py` 20 / 0。

### 2.7 卡住或延後的事

- **切出風速用瞬間風速**：手冊 201 是 10 分鐘平均 > 25 或 5 秒平均 > 35 m/s；物理層看瞬間有效風速且走緊急停機，高紊流高風速時反覆切出 → 開 WMOM-20261021-10
- **物理層保護停機的停機模式**：351 在手冊是 T1，物理層仍走緊急停機——未改，避免動到超速物理的既有校正
- **批次路徑不收 PLC 事件**（-04）；`faults.py` `run_test_plan` 不記 trip 事件
- **預期碼可能不出現**：嚴重度 0.8 時 bearing / stator / transformer / nacelle 3 h 內不跳機，-04 ground truth 必須允許

## 3. 產出清單

### 新增檔案

- `modules/monitoring/simulator/physics/plc_protection.py`
- `modules/monitoring/tests/test_plc_protection.py`（40，含 review 補的 10）
- `modules/monitoring/tests/test_plc_event_recording.py`（2，review 補）
- `modules/monitoring/tests/test_plc_integration.py`（13）
- 本 work-log

### 修改檔案

- `modules/monitoring/simulator/physics/turbine_physics.py`、`fault_engine.py`、`scada_registry.py`（註解）
- `modules/monitoring/simulator/engine.py`
- `modules/monitoring/server/data_broker.py`、`routers/config.py`、`routers/scenarios.py`、`routers/control.py`（註解）
- `modules/monitoring/examples/data_quality_analysis.py`（docstring）
- 測試：`test_reset_keeps_fault.py`（改寫 + 無 7↔3）、`test_fault_alarm_codes.py`、`test_generate_bulk_fault_schedule.py`、`test_scenario_endpoints.py`（+3）、`tests/physics/test_fault_signature.py` / `test_fault_threshold_reach.py`（關 PLC，純物理特性）
- 文件：`docs/product/EPIC-DS_realistic_data_source.md`（§6.1 標記已解、新增 §6.3）、`docs/API_GUIDE.md`（故障 API 註記）、`docs/physics_model_status.md`（1.8a）、`ISSUES.md`、`STATUS.yaml`、`CLAUDE.md`、`TODO.md`

### 動了狀態的 issue

- WMOM-20261021-03-b：open → done
- WMOM-20261021-10：新增 open

## 4. 下次怎麼接手

1. **WMOM-20261021-03-c**：UTC 時間戳。
2. **WMOM-20261021-10**：切出風速平均判定（小題，可與 -03-c 同日）。
3. **WMOM-20261021-04**：ground truth 的「預期警報序列」應取自 PLC 實際事件（`PlcEvent`），並允許預期碼未出現；bulk 路徑需 `drain_events()`。
