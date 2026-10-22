# 2026-10-22 — WMOM-20261021-08-a：感測器故障 vs 真故障（EPIC-DS Phase 4-a）

> Session 類型：實作
> Session 長度：中
> 主導：Claude（劉老師選定「繼續做 -08」，子項與三個設計問題由劉老師確認）
> 結果：WMOM-20261021-08-a done；-08 改 in_progress（其餘子項待選）

---

## 1. Session 目標

-08（難度與多樣性）範圍大，拆子項分 PR。劉老師選定先做「感測器故障 vs 真故障」：讓類別正確率真的能考。在這之前故障庫只有風向標漂移一個感測器故障，元件與類別一對一，猜對元件就等於猜對類別。

## 2. 劉老師的決定（開工時確認，DEC-20261022-04）

| 問題 | 決定 |
|---|---|
| 先做哪個子項 | 感測器故障 vs 真故障 |
| PLC 怎麼看到感測器故障 | 只對被注入的那支感測器改看量測值（其他照舊看製程值） |
| 做哪幾種 | 讀值像真故障（漂移）＋ 有專屬感測器故障碼 |
| component 填什麼 | 被量測的元件，以 category 區分 |

## 3. 實際完成

### 3.1 開工時的發現

- Z72 警報目錄本身就有兩類感測器事件：一般的溫度 / 壓力事件（讀值錯也會觸發），與「I/O 模組偵測到斷線」「編碼器角度超出範圍」的專屬故障碼（242/243 軸承溫度、250-255 定子溫度、229 偏航壓力感測器、326-328 編碼器、274 機艙溫度…）。
- 真實 Z72 PLC 有軸承溫度 2、定子溫度 2-6，但模擬器只輸出 1。沒有第二支感測器，「讀值像真故障」的感測器故障就沒有公平的分辨依據，所以補上 `WGEN_GnBrgTmp2`、`WGEN_GnStaTmp2`。

### 3.2 機制（`turbine_physics.py`）

- `_get_fault_physics` 多一個 `sensor_faults`：`{tag: ("offset", Δ) | ("pinned", 讀值)}`。
- `step()`：製程值 → `_apply_sensor_faults` 得到量測值（沒有感測器故障時就是同一個 dict）→ PLC 判定量測值、感測器模型也吃量測值；`pinned` 讀值在感測器模型之後再蓋一次（斷線讀值固定、沒有雜訊）。
- 製程、控制、其他感測器完全不變：同種子下，故障機組除了那支感測器，每個 tag 每一步都逐位元等於健康機組（測試鎖住）。
- `TurbineSpec`：感測器有效範圍與斷線讀值（Pt100 −40–250 °C、斷線 850 °C；偏航壓力 −5–260 bar、斷線 −62.5 bar；葉片角度 −10–100°、編碼器故障 135°），皆為模擬假設（手冊沒有數字）。
- `SENSOR_BREAK_SEVERITY = 0.5`：斷線 / 編碼器故障在嚴重度到 0.5 時一次發生。

### 3.3 第二支感測器

- `WGEN_GnBrgTmp2`：新的熱節點（`thermal_model.gen_bearing2`），摩擦熱略少；主軸承磨耗的故障熱與潤滑劣化分到 40 %（code review M1 後），升溫約軸承 1 的三成、不到警報。健康時比軸承 1 低約 1 °C。
- `WGEN_GnStaTmp2`：同一繞組另一個槽，固定偏移（±2 °C 以內）；繞組劣化時與定子溫度 1 一起升（預期碼補 265 / 245）。
- 註冊表 116 → 118 個 tag（真實 45 → 47），資料包 100 → 102 欄；Modbus 502 / 510 的預留位改對到這兩個 tag；雜訊與偏移走獨立的 `_rtd_rng`（code review S1 後；既有 116 個 tag 與 main 逐位元相同）。

### 3.4 情境（`fault_engine.py`，全部 `category: sensor_fault`）

| 情境 | component | 碼 | 難度 |
|---|---|---|---|
| `main_bearing_temp_sensor_drift` | main_bearing | 262 / 240 | hard |
| `stator_temp_sensor_drift` | generator_stator | 264 / 244 | hard |
| `main_bearing_temp_sensor_wire_break` | main_bearing | 242 | easy |
| `blade1_pitch_encoder_fault` | pitch_system_blade_1 | 326（T2） | easy |
| `yaw_brake_pressure_sensor_fault` | yaw_brake_hydraulics | 229 | easy |

- **漂移的校正**：第一版軸承偏移 45 °C，但 14 m/s 時健康軸承只有 43 °C，到不了 95 °C 跳機；改 60 °C（定子 100 °C），滿嚴重度越過跳機、0.5 還不到警報。偏移這麼大，「校正漂移」說不通，根因改寫成「Pt100 量測回路接觸電阻增加（端子鬆動 / 接點氧化）」——約 0.385 Ω/°C，十幾歐姆的接觸電阻就有幾十度。
- 根因寫明哪些訊號正常、怎麼分辨；處置含手冊條目（262/240 的潤滑與風扇、242 的 Pt100 配線、326 的編碼器配線與校正、229 的壓力感測器配線）。

### 3.5 PLC（`plc_protection.py`）

- 第二支感測器的規則：263 / 241（軸承 2）、265 / 245（定子 2）。
- 感測器故障碼：讀值超出有效範圍持續 2 s → 242 / 243、250 / 251、229、326-328。
- 失效的讀值不再參與越限判定：溫度規則以 `*_ok` gate；偏航低壓與葉片差異的既有 gate 加上讀值有效條件。所以斷線不會連帶送出溫度過高 / 壓力過低 / 葉片差異。

### 3.6 knowledge 語料、kit、合約

- knowledge baseline 語料補 242 / 326 / 229 三段（測試要求語料碼＝情境碼）。
- starter kit 加 `z72-starter-04`（4 台、5 h、額定風）：WT001 主軸承磨耗、WT003 軸承溫度量測回路劣化、WT004 偏航壓力感測器斷線。WT001 與 WT003 送出一模一樣的 262 / 240（感測器那台還先跳）。
- 基準助手：警報文字點名感測器（sensor / encoder / temperature fault）才判 `sensor_fault`。四個範例上元件 87.5 %、類別 75 %；類別錯的兩個 case 都是讀值像真故障的（風向標漂移、軸承溫度量測回路）。
- 範例資料包 01-03 重產：多兩欄、`_aux_rng` 的雜訊順序改變（風向標 2、電網電壓），事件逐筆不變、答案只有版本與產生時間改變。
- 合約 v1.3：§3.3 數量、§7 / §8 類別說明與基準、§9 同元件兩種答案的對照表、§10 感測器故障須知、§10.1 開發集（16 種故障中的 7 種）、版本歷史。

### 3.7 code review（code-reviewer：Needs revision → 全修）

審查者跑了每個情境 × 5 種風速 × 3 種氣溫的 PLC 掃描（健康與 11 個真故障都不會送出感測器故障碼）、五個新情境的注入 → 跳機 → 清除 → 復機，以及與 main 的同種子比對。

- **M1 軸承溫度 2 分不出真故障與感測器故障**：主軸承磨耗原本只讓軸承 2 升 1.8 °C（滿嚴重度），「軸承 2 正常 → 感測器故障」對兩者都成立；範例 04 的兩台在 03:00 的軸承 2 是 43.8 與 42.5 °C。改為軸承 2 分到 40 % 的故障熱與潤滑劣化（`_BEARING2_FAULT_SHARE`），滿嚴重度 +28 °C、37 °C 天也不到警報；範例 04 跳機時 WT001 56.4 °C、WT003 42.7 °C。主軸承磨耗的根因與 key signal 補上軸承溫度 2；新測試比較兩者在跳機當下的軸承 2 升溫（真故障 > 8 °C、感測器 < 2 °C）。
- **S1**：新感測器原本走 `_aux_rng`，讓風向標 2 與三相電網電壓的雜訊每步都位移（守門測試只檢查主 RNG）。改用 `_rtd_rng`，與 main 同種子比對既有 tag 逐位元相同；新增守門測試。
- **S2**：已成立的規則不受讀值失效影響（262 成立後斷線，262 仍在）。新增 `ProtectionRule.valid`（與 `gate` 分開），無效時立即解除；測試涵蓋。
- **S3**：漂移先警報後跳機的測試靠「注入時讀值剛好 94 °C」；改從嚴重度 0 慢慢漂。
- **Nice-to-have 採用**：葉片差異依每一對葉片的編碼器判定；斷線讀值寫回 `_sensor_last`；docstring；語料用詞；匯出 CSV 加兩個 tag；補測試（跳機 → 維修鎖 → 清除 → 復機；嚴重度剛好 0.5）。
- **修 review 時發現**：定子 2 改用 `_rtd_rng` 後偏移換了值，定子繞組劣化在這個種子下由定子 2 先跳（245），不在預期碼內 → 故障沒被標成跳機、機組反覆重啟到封鎖。真故障本來就是整個繞組變熱，預期碼補上 265 / 245（語料同步）。
- **未採用**：同一 tag 兩個感測器故障、同機組多重故障的歸屬（記入已知限制，留給多重故障子項）；`affected_tags` 的舊欄位值（只是說明用）。

## 4. 驗證

- `modules/monitoring/tests/test_sensor_faults.py`（新，16 項）：每個感測器故障只送自己的碼；漂移先警報後跳機、第二支感測器正常；跳機當下軸承 2 分得出真故障與感測器故障；真故障不送感測器故障碼；PLC 斷線規則（確認延時、修好解除、低於範圍、已成立規則的解除、每對葉片）；跳機 → 維修鎖 → 清除 → 復機。
- `tests/physics/test_fault_threshold_reach.py`（+12 項）：第二支 Pt100 的獨立 RNG；健康炎熱天第二支感測器不越限；漂移滿嚴重度越過跳機、0.5 還沒；故障機組除了那支感測器逐位元等於健康機組；斷線讀值固定、嚴重度 0.4 還正常；第二支感測器跟著同元件。
- 既有守門自動涵蓋新情境：每個情境都會跳機（`test_plc_integration.py`）、key signal 偏離健康、答案欄位齊全、預期碼可由 PLC 送出、語料碼一致。
- 更新：`test_plc_tags.py`（118 / 47）、`test_scenario_pack.py`（102 欄）、`test_fault_ground_truth.py`（感測器故障集合、同元件兩種類別）、`test_plc_protection.py`（基準值加兩個 tag）、`test_rag_starter_kit.py`（第四個資料包、基準成績）。

## 5. 產出清單

### 新增

- `modules/monitoring/tests/test_sensor_faults.py`
- `examples/rag_starter_kit/packs/z72-starter-04/`、`answers/z72-starter-04.ground_truth.json`
- 本 work-log

### 修改

- `modules/monitoring/simulator/physics/turbine_physics.py`、`thermal_model.py`、`plc_protection.py`、`fault_engine.py`、`scada_registry.py`、`simulator/modbus_server.py`
- `modules/monitoring/simulator/ground_truth.py`（`CONTRACT_VERSION` 1.3）、`shared/data/rag_assistant_vocabulary.json`（1.3）
- `modules/knowledge/data/baseline_corpus_z72.json`
- `tools/build_rag_starter_kit.py`、`examples/rag_starter_kit/`（基準助手、README、vocabulary、重產的資料包與答案）
- 測試：見 §4
- 文件：合約 v1.3、`EPIC-DS_realistic_data_source.md`（§6 表、§6.13）、`decision_log.md`（DEC-20261022-04）、`ISSUES.md`、`STATUS.yaml`、`CLAUDE.md`、`TODO.md`

### 動了狀態的 issue

- WMOM-20261021-08-a：新增 → done
- WMOM-20261021-08：open → in_progress

## 6. 下次怎麼接手

- -08 其餘子項（開工時請劉老師挑）：
  - **誤報與健康負樣本**：nuisance / healthy case 與評分規則（目前 nuisance 預測不評分）。
  - **多重故障 + 早期徵兆**：同一台兩個故障、警報前數小時就偏離的慢速劣化、嚴重度變體。
  - **故障庫擴充**：Z72 常見事件；修 `gearbox_overheat` / `pitch_motor_fault` / `yaw_misalignment` 三個不能注入的 alias。
  - 感測器故障的延伸：間歇性斷線（有早期徵兆）、卡值、其他溫度感測器（274、235）、轉速感測器（029 轉子與發電機轉速差 > 10 %）。
- 新增感測器故障情境時：在 `_get_fault_physics` 填 `sensor_faults`；有專屬碼的要在 `TurbineSpec` 定有效範圍並加 PLC 規則，同時把那個讀值從越限規則的 gate 排除；`_SENSOR_FAULT_TAG`（physics 測試）與 `EXPECTED`（`test_sensor_faults.py`）各加一行。
