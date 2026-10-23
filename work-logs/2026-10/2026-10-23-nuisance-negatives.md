# 2026-10-23 — WMOM-20261021-08-b：誤報 / 健康負樣本

> Session 類型：實作
> Session 長度：長
> 主導：Claude（-08 子項順序與三組設計選項由劉老師決定，DEC-20261023-02）
> 結果：WMOM-20261021-08-b done；合約 v1.5

---

## 1. Session 目標

-02（手冊保真度）合併後，劉老師要接著做 -08 其餘子項，並選了**先做誤報 / 健康負樣本**。

到 v1.4 為止，標準答案只有故障 case：

- 評分只看故障有沒有被診斷出來，看到警報就報故障不會被扣分。
- 範例資料包裡健康機組幾乎沒有警報 / 跳機。
- `nuisance` 預測只統計、不評分。

目標：讓「不是故障的警報 / 跳機」也有答案，評分量得到誤報。

## 2. 實際完成

### 2.1 盤點與劉老師決定（DEC-20261023-02）

- **干擾候選**：
  - 手冊 §11.3 點名的 nuisance trips：風向變化快的偏航逾時、Pt100 鬆線。
  - 電網擾動：模擬器已有電網保護 / LVRT 的停機碼。
  - 環境性停機：暴風切出 201、極端氣溫 256 / 273。
- **偏航逾時**：手冊 Appendix D 有 `SDYawTmOutFact` / `SDYawTmOutOffs`，模擬器沒有 223 規則。
  - 健康偏航實測最長 55 s，實際用時最多約為「誤差 ÷ 偏航速度」的 1.4 倍、允許時間（factor 5）的 0.29，裕度足夠。
  - 單向的風向轉變偏航追得上、不會逾時，所以要用來回擺動。

| 問題 | 決定 |
|---|---|
| 干擾來源 | 電網擾動、手冊 §11.3 nuisance 跳機、環境性停機標記、全健康負樣本資料包，四個都做 |
| 答案格式 | nuisance case（時間窗、預期碼、成因；component 可為 null） |
| 評分 | 加新指標、不改舊規則 |
| 交付 | -08 每個子項各一個 PR |

### 2.2 實作

**風場層級事件**（新檔 `simulator/farm_events.py`）：

- 三種：`grid_voltage_dip`（電壓 p.u.）、`grid_frequency_excursion`（頻率偏移 Hz）、`rapid_wind_direction_change`（擺動振幅°）。
- 答案文字（根因、處置、模擬差異）、會送的事件碼、關鍵訊號都集中在 `FARM_EVENT_KINDS`。
- `generate_bulk(farm_events=..., on_farm_event=...)` 逐個物理子步套用：
  - 電網：`GridEnvironmentModel.apply_event_override`；亂數抽樣次數不變，事件前的資料逐位元相同。
  - 風向：`_direction_offset_deg` 加在風場風向上（180 s 週期正弦，頭尾 60 s 漸強 / 漸弱）。
  - 事件結束恢復批次開始前的電網狀態，批次結束（含例外）時電網與風向都復原。

**PLC 偏航逾時 223**（`plc_protection.py`）：

- 對風（不含解纜，`yaw_model` 新輸出 `is_unwinding`）開始時算允許時間＝5 × max(|誤差|, 2°) ÷ 0.5 °/s + 0 s。
- 這一段對風超過就跳機；偏航停下就重算。
- `TurbineSpec.yaw_timeout_factor` / `yaw_timeout_offset_s` 列入 `Z72_PLC_SETPOINT_FIELDS`。

**nuisance 情境 `main_bearing_temp_loose_contact`**：

- 注入後 5–20 分鐘第一次、之後每 15–45 分鐘瞬斷 10–30 s，瞬斷時讀值＝斷線值，PLC 送 242。
- 排程用獨立的 `_contact_rng`（不動既有 RNG）；故障清掉後排程重設。
- `FaultEngine.mark_tripped` 對 nuisance 回 False：不鎖機組、接回後自動重啟。
- `FaultScenario.nuisance_cause` 新欄位（故障為 None）。

**標準答案**（`ground_truth.py`，合約 v1.5）：

- nuisance case 三種來源：
  - 注入的 nuisance：每次一個；第一個預期碼跳機當 `trip`，跟在後面的 A039 也歸它。
  - 風場事件：每台有反應的機組一個（事件期間到結束後 30 分鐘、沒被認領的該事件碼）。
  - 環境性：沒有故障 case 的機組（或故障開始前）其餘沒被認領的事件，同機組 30 分鐘內一群。
- 新欄位 `nuisance_cause`、`window_end_ts`、`farm_event_id`，頂層 `farm_events`。
- `healthy_turbines`＝沒有故障 case；`unattributed_events` 只剩故障連帶事件。
- 詞彙加 `nuisance_causes`。

**API**（`routers/config.py`）：`generate-bulk` 的 `farm_events`（`_parse_farm_events`：種類、時間、長度、強度範圍、有限數、bool、最多 50 筆）；情境設定記 `farm_events`；回應加 `farm_events_scheduled`。資料包 manifest 不帶。

**評分**（`score.py`）：

- 故障指標只算故障 case，規則不變；舊答案（沒有 `window_end_ts`）照常評分。
- 新增：干擾辨識率、把干擾當故障（case 數與筆數）、誤報率（誤報次數 ÷ 沒有故障的機組時數 × 100）、nuisance case 明細。
- 基準助手：同一個碼 60 秒內已在另一台機組出現 → nuisance。

**starter kit**：`z72-starter-05` 健康負樣本（4 台、6 h、額定風速、7 月）。

- 0.5 h 注入 WT003 Pt100 鬆線。
- 1 h 電壓驟降 0.70 p.u.、20 s。
- 2.5 h 頻率 −1.8 Hz、40 s。
- 4 h 風向擺動 ±60°、25 分鐘。
- 結果：12 個 nuisance case、0 個故障、187 筆事件。

### 2.3 驗證

- **範例資料包 01–04**：重建後資料逐位元不變（新規則 223 在這些情境不觸發），只有 manifest 的版本與答案的新欄位。
- **基準助手**（5 個資料包）：故障指標與 -02 相同；誤報 4 次（全在 05）；誤報率 5.46 次 / 100 機組小時（73.3 機組小時）；干擾 12 個認出 8 個（66.7 %），3 個被當故障。
- **新測試**：
  - `test_nuisance_events.py` 24 項（含 review 修正後新增的 10 項）：風場事件三種、事件前資料逐位元相同、Pt100 鬆線跳機與重啟、清掉後排程重設、標準答案 nuisance case、時間窗邊界、詞彙、資料包答案時間格式。
  - PLC 223 規則 3 項；評分 / 基準 4 項；端點 13 項；Pt100 鬆線只改那支讀值的物理守門 1 項。
- **既有測試調整**：
  - 「每個故障滿嚴重度都跳機」與「key signal 偏離健康機組」排除 nuisance（另有專屬測試）。
  - 標準答案測試：注入前 / 別台的事件改成環境性 case。
  - PLC 液壓測試：偏航段給實際的偏航誤差（誤差 0 時 223 的允許時間只有 20 s）。
- **完整 backend**：1991 → 2051 passed / 7 skipped / 1 xfailed（code review 與 Codex review 修正後）。frontend 沒有改動（vitest 1513）。
- **ruff / mypy**：與 origin/main 相比沒有新的 F / E / B；修掉兩個新的 mypy 型別錯誤；`engine.py` 的 `"None" not callable` 是既有的。

### 2.4 code review

code-reviewer：沒有 must-fix，6 個 should-fix 與若干 nit。

- **審查者自己的驗證**：
  - 健康資料與 origin/main 逐位元相同：12 h × 5 台 × 4 種風況、6 h × 3 台。
  - 健康偏航最多用到允許時間的 0.29。
  - 批次中途例外時電網 / 風向都復原。
  - 盲測沒有外洩路徑。
  - v1.4 答案用新評分程式評，故障指標相同；文件引用的基準數字都重現。
- **修正**：
  - **S1**：一小時內兩次同種事件時，第二次的碼被第一次吃掉（第二次沒有 case）。改為歸給涵蓋它、最晚開始的事件。
  - **S2**：頻率 +1 Hz（未達 1.4 Hz 跳機）時三台都送 420，答案標成環境性。
    - 根因是物理：下垂降載少送出的功率被算成變頻器發熱，冷卻水溫一分鐘升 18 °C。
    - 改為只算效率損失：沒有降載時這一項恰為 0，健康資料逐位元不變。
    - 標準答案另外加兩條規則：事件進行中到結束後 10 分鐘的任何碼都歸事件；事件自己的碼到結束後 30 分鐘不讓故障 case 認領（故障預期碼 021 / 481）。
  - **S3**：合約語意變更要不要升主版本。維持 1.5：`nuisance` 從 v1.0 就是保留類別，定義文字不變。合約 §2 註明自己寫評分程式要分開 `nuisance` case；記進 DEC-20261023-02。
  - **S4**：`nuisance` 預測沒有成本。評分加「干擾判定落空」與準確率；DEC 的「互為制衡」措辭改正。
  - **S5**：`build()` 會改紀錄器狀態，第二次呼叫事件消失。改為每次重算歸屬。
  - **S6**：A039 的歸屬沒有界限。改為跟著同機組前一次跳機。
- **nit 處理**：
  - 已修：
    - 偏航裕度措辭（1.34 倍 → 允許時間的 0.29），涉及 DEC、physics status、ISSUES、設計文件。
    - 振幅 < 26° 不會逾時、nuisance 自動重啟假設，寫進 `simulation_notes` / API guide / 合約。
    - `farm_events[].end_ts` 不超過 `sim_end`；`other_observed_codes` 可重疊寫進 §7.1；設計文件過時的限制註記。
    - engine 型別（`Set[int]`、`GridOverrideState`）、事件都結束後不再逐子步掃描。
    - `score.py` 的 assert、沒有故障 case 時的說明。
  - 不改：
    - `farm_events_scheduled` 照 `fault_schedule` 的先例回傳排定數。
    - `C{:03d}` 超過 999 只是變長。
    - 基準助手的 60 s 規則也會把兩個同時跳機的真故障判成干擾，作為基準可以接受。
- **新測試**：
  - 兩次電壓驟降各自有 case。
  - A039 跟前一次跳機。
  - 事件碼不讓故障 case 認領。
  - `build()` 可重複呼叫。
  - 電壓 + 頻率重疊與手動覆寫復原。
  - 批次例外時復原。
  - 頻率偏高只降載（不再 420）。
  - 三種事件的 key signal 偏離。
  - 評分的落空與準確率。

## 3. 產出清單

### 新增檔案

- `modules/monitoring/simulator/farm_events.py`
- `modules/monitoring/tests/test_nuisance_events.py`
- `examples/rag_starter_kit/packs/z72-starter-05/`、`answers/z72-starter-05.ground_truth.json`
- `work-logs/2026-10/2026-10-23-nuisance-negatives.md`

### 修改檔案

- **程式**：
  - `modules/monitoring/simulator/engine.py`、`grid_model.py`、`ground_truth.py`
  - `simulator/physics/plc_protection.py`、`turbine_physics.py`、`fault_engine.py`、`yaw_model.py`
  - `server/routers/config.py`、`server/scenario_pack.py`
  - `examples/rag_starter_kit/score.py`、`baseline_assistant.py`
  - `tools/build_rag_starter_kit.py`
- **資料**：`shared/data/rag_assistant_vocabulary.json`（1.5、`nuisance_causes`）、`examples/rag_starter_kit/`（重建）
- **測試**：`test_fault_ground_truth.py`、`test_plc_protection.py`、`test_plc_integration.py`、`test_scenario_endpoints.py`、`tests/physics/test_fault_threshold_reach.py`、`tests/test_rag_starter_kit.py`
- **文件**：合約 v1.5、`decision_log.md`（DEC-20261023-02）、EPIC-DS 設計文件 §6.16、`API_GUIDE.md`、`physics_model_status.md`、kit README、`ISSUES.md`、`STATUS.yaml`、`TODO.md`、`ROADMAP.md`、`CLAUDE.md`、`README.md`、架構文件

## 4. 卡住 / 留給後續

- 極端氣溫沒做進 05：額定風速、38 °C 時機艙控制櫃最高 49.7 °C（256 設定值 50 °C），要 39 °C 以上才跳，台灣沿海不切實際。
- 暴風切出沒做進 05：24 m/s 以上全場切出後一直停著（回切要 20 m/s），會蓋掉其他干擾。
- 上面兩種在情境裡出現時照樣標成環境性 case（合成事件測試）。
- -08 其餘子項：故障庫擴充；多重故障 + 早期徵兆（同機組多 case 的評分規則要先定）。

## 5. 下次怎麼接手

- -08 下一個子項請劉老師挑：故障庫擴充，或多重故障 + 早期徵兆（後者要先定同機組多 case 的評分規則）。
- 新增干擾來源：風場事件加進 `FARM_EVENT_KINDS`（`event_codes` 決定標準答案認領哪些碼），nuisance 情境用 `category="nuisance"` 加 `nuisance_cause`；成因先加進 `rag_assistant_vocabulary.json` 的 `nuisance_causes`。

## 6. Codex review（PR 標成 ready 後自動觸發）

5 項（P1 × 3、P2 × 2），逐項驗證都成立，全修：

| 項目 | 問題 | 修正 |
|---|---|---|
| P1 保留窗 | 事件碼只保留 10 分鐘，10–30 分鐘的事件碼會被故障 case 認領，與 `build` 的 30 分鐘歸屬窗、合約 §7.1 不一致 | 保留窗改為 `NUISANCE_WINDOW_GRACE_S` |
| P1 短事件 | 只在子步開始時判定，比子步短、落在兩個取樣點之間的事件完全不套用、不回呼、不進答案 | 改為與子步重疊就套用，回呼排定的開始時刻 |
| P1 Pt100 排程 | 連續兩個命名情境都在開頭注入、中間沒有物理步時沿用上一次的排程 | `ActiveFault.instance_id`（每次注入新編號），模型換了注入就重新排程；拿掉靠「某一步沒有這個故障」的重設 |
| P2 recovery | 電網事件把 profile 換成 `farm_event`，另一個量的 recovery 斜坡被打斷 | 事件覆寫另存 `_event_frequency` / `_event_voltage`，只蓋自己的量；profile、手動覆寫不動（移除 snapshot / restore） |
| P2 時間窗 | offset 0 的風場事件早於第一筆讀值，情境時間窗沒包含它 | `on_farm_event` 同 `on_inject` 拉低時間窗下界 |

新測試 6 項（每項各一）；pack 05 重建後資料與答案不變。
