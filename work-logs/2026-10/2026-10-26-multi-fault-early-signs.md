# 2026-10-26 — WMOM-20261021-08-d：多重故障＋早期徵兆

> Session 類型：設計＋實作
> Session 長度：中
> 主導：Claude（評分規則由 Claude 建議，劉老師授權「請你建議就好」）
> 結果：WMOM-20261021-08-d done；-08 母 issue done；DEC-20261026-01；合約 v1.7；範例資料包 07

---

## 1. Session 目標

-08 最後一個子項。劉老師 2026-10-26：「同一台機組多個 case 的評分規則請你建議就好，然後開始多重故障＋早期徵兆」。

## 2. 調查

- 評分（`score.py`）：預測依機組與時間對 case，多個時先同元件、否則最晚開始的；每個 case 以最後一筆評；誤診＝對到 case 但元件錯。
  同機組 k 個 case 時「每個元件猜一遍」每個 case 都拿到元件分（EPIC-DS 文件 §6.14 留下的漏洞）。
- 標準答案：每次注入一個 case；同機組不同故障各自成 case；共用碼歸給每個預期它的 case（-08-a 規則）；故障 case 的時間窗到 `sim_end`。
- 故障引擎：同機組不同情境可並存；跳機後嚴重度凍結、`maintenance_lock` 停機；沒有「停在門檻下」的機制——早期徵兆只能靠情境在警報前結束，風況一變警報時點就變。
- 額定風速（13 m/s、25 °C、嚴重度 0.0002 /s）各故障出第一個警報 / 跳機的嚴重度（實測）：

  | 故障 | 第一個警報 | 跳機 |
  |---|---|---|
  | bearing_wear | 262 @ 0.88 | 240 @ 0.94 |
  | stator_winding_degradation | 264 / 265 @ 0.91 | 245 @ 0.95 |
  | main_bearing_temp_sensor_drift | 262 @ 0.69 | 240 @ 0.86 |
  | cooling_water_deionizer_exhausted | 423 @ 0.45 | 440 + 021 @ 0.81 |
  | converter_cooling_pump_wear | 422 @ 0.45、432 @ 0.56 | 439 + 021 @ 0.71 |
  | hydraulic_leak | 261 @ 0.50、260 @ 0.51 | 228 @ 0.76 |
  | pitch_motor_fault | 381 @ 0.53 | 367 @ 0.88 |
  | transformer_overheat | 417 @ 1.0 | 444 @ 1.0 |
  | 感測器斷線 / 編碼器 / 風向標卡住 | — | 0.5 |
  | yaw_misalignment | — | — |

## 3. 評分規則（建議 → DEC-20261026-01）

1. 歸屬：先對同元件的 case，其次同群組的（基準在 07 WT004 只猜到「變槳系統」，不加這級會歸到較晚開始的導電度 case），否則最晚開始的；每個 case 各自評，助手可對一台機組維持多條診斷。
2. 新指標**診斷精確率**：對到 case 的診斷裡元件正確的比例。單 case 時＝1 − 誤診比例；多 case 時抓「每個元件猜一遍」。
3. **早期徵兆 case**：有預期碼、情境內沒到警報的故障 case 分開列；偵測到＝早期預警、不評延遲。與「沒有警報的故障」（預期碼為空）不同。
4. 出題端：排程 `max_severity`（預設 1.0）；標準答案 `injection.max_severity`；合約 1.7。
5. 共用碼仍歸每個 case；範例資料包不放共用碼組合（`check_pack` 擋）。健康時數重疊窗只扣一次。

不採用：猜錯記到每個進行中的 case（會把已對的 case 最後一筆變錯）、集合評分（太複雜）。

## 4. 實作

- `fault_engine.py`：`ActiveFault.max_severity`、`inject(max_severity=)`（(0, 1] 且 ≥ initial，否則 ValueError）、`step` 以上限夾；`TestPlanStep.max_severity`。
- `config.py::_parse_fault_schedule`：`max_severity` 驗證（400）；`engine.py` 批次注入帶上限；`scenarios.py` 註解公式。
- `ground_truth.py`：`_Case.max_severity` → `injection.max_severity`；`CONTRACT_VERSION` 1.7；詞彙檔 1.7。
- `score.py`：`Case.early_sign`、`CaseResult.early_sign`、`Report.diagnosis_precision` / `early_sign_cases` / `early_sign_detected`；報告多兩行、case 明細標（早期徵兆）。
- `tools/build_rag_starter_kit.py`：範例 07（6 台 6 h 額定）＋ `check_pack`（同機組共用預期碼 → ValueError，`generate` 開頭呼叫）。
- 測試：`test_fault_severity_cap.py`（4）、parser 驗證（1）、kit（精確率、早期徵兆、共用碼守門、`max_severity` < 1 不得出警報、PACK_IDS 07）。
- 文件：合約 v1.7（§2 / §7 / §8 規則 7–8 與兩個指標 / §10.1 / §11）、kit README（07、早期徵兆說明、評分規則）、DEC-20261026-01、EPIC-DS §6.19、ISSUES（-08-d、-08 母 issue done）、STATUS、CLAUDE.md。

## 5. Code review（code-reviewer subagent）

Needs revision → 全修：

| 等級 | 發現 | 處理 |
|---|---|---|
| M1 | `TestPlanStep.max_severity` 插在 `description` 前面：內建 18 個 TEST_PLANS 以第 6 個位置參數傳 description，字串落進 `max_severity`，`POST /api/faults/test-plans/{id}/run` 會在背景執行緒 TypeError。 | 欄位移到 `description` 之後；新增測試逐一檢查 TEST_PLANS 的步驟都能注入。 |
| S1 | `initial_severity` > 1 以前接受、下一步夾到 1；新的上限檢查讓它變 ValueError（Live 路由 500）。 | `inject` 先把 `initial_severity` 夾到 1 再檢查；parser 同樣。測試。 |
| S2 | Live 的 `POST /api/faults/inject` 沒開 `maxSeverity`。 | 範圍取捨，寫進 DEC（早期徵兆是出題用，走批次）。 |
| S3 | `Case.early_sign` 把 `pre_existing` case（開始時間不明）也算進早期徵兆。 | 加 `timing_scored` 條件；測試。 |
| S4 | `early_sign_detected` 用 `detected`（任何診斷都算），亂猜也能加分。 | 改用 `early_warning`（元件正確）；報告與文件改「診斷對」；測試。 |
| S5 | 同群組歸屬在同群組有多個 case 時取最晚開始的——沒寫進文件。 | 合約 §8 規則 7 補一句。 |
| S6 | `scenarios.py` 舊路徑的公式註解被改成 `min(max_severity, …)`，程式其實還是 `min(1, …)`。 | 註解改回並註明舊路徑不帶 max_severity；`_generate_bulk` docstring 補 `max_severity?`。 |
| N | parser 不擋 NaN；測試用 naive datetime、`_run_one_step` 私有、單筆讀值比較。 | parser 加 `math.isfinite`；測試照 `test_plc_integration.py` 既有寫法不改。 |

## 6. 驗證

（見下方補記）
