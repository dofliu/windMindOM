# 2026-10-23 — WMOM-20261022-02：手冊保真度（Appendix D、A039、yaw drift 233）

> Session 類型：實作
> Session 長度：長
> 主導：Claude（三個設計問題由劉老師決定，DEC-20261023-01）
> 結果：WMOM-20261022-02 done；合約 v1.4

---

## 1. Session 目標

WMOM-20261022-01 的模擬器 review 對照手冊，找到三類不一致，劉老師排在 -08 其餘子項前面做：

1. Appendix D 的設定值、延時、範圍與模擬器不同。
2. 自動重啟被封鎖時，真實 Z72 送 A039；模擬器送自創的 `restart_blocked`，物理層的全域上限則完全沒事件。
3. `yaw_sensor_drift` 在部分機組永遠不跳 233。

## 2. 實際完成

### 2.1 盤點（對照手冊原文）

用 `pdftotext` 抽出 Appendix D（p.131-135）、Appendix C、§6.8.1 / §8.3 / §11.3 的原文逐項核對。除了 issue 列的項目，另外找到：

- **手冊自相矛盾三處**：
  - 液壓 260：C 寫 180 bar，D 寫 170 bar。
  - 切出陣風：C 寫 5 秒，D 寫 3 秒。
  - 233 的風速條件：C 寫 10 分鐘平均，D 的參數名是 60 s 平均。
- **重啟上限的出廠值**：§11.3 說每碼出廠設定是 0，Appendix C 的 Max #/hr 欄卻列了 1、2、5、10。
- **全域上限不在手冊裡**：物理層「每小時 3 次啟動」連低風速正常起停也算。
  - 實測風速在切入風速附近以 5 / 10 / 20 分鐘週期擺動時，健康機組 3 h 內分別有 2.5 / 2.0 / 1.0 h 卡在待機。
  - 被卡住期間沒有任何事件。
- **236 塔架加速度對不上**：手冊看合成加速度（1.75 m/s²），模型的振動是速度（mm/s），要動振動模型，留給後續。
- **既有風場會帶回舊設定值**：farms.db 存的 turbine_spec 是建立當時完整的 `to_dict()`，會把舊的 180 bar 帶回來。

### 2.2 劉老師決定（DEC-20261023-01）

| 問題 | 決定 |
|---|---|
| 自動重啟被封鎖怎麼表示 | 改送 A039、不再送 `restart_blocked`（合約 v1.4，列舉值保留） |
| 全域每小時 3 次啟動上限 | 拿掉，物理層保護停機改照每碼計數 |
| Appendix C / D 衝突 | 以 Appendix D 為準 |

### 2.3 實作

**警報目錄**：

- `tools/build_z72_alarm_catalog.py` 把手冊獨有的碼收進目錄：欄位取手冊、`plc_tag` 依等級推定、標 `manual_only`。
- 重建後只多了 A039 這一筆，共 315 碼。

**PLC 保護層**（`plc_protection.py`）：

- **Pt100 溫度**（主軸承、定子、機艙）以 10 s 一階濾波後判定，沒有事件延時。
  - 斷線判定（242 等）用未濾波讀值。
  - 斷線讀值不進濾波器，接回後從讀值重新起算。
- **液壓 260 / 228**：170 / 150 bar、延時 30 s、> 190 bar 解除。
- **233**：延時 60 s，風速條件改 60 s 平均。
- **編碼器有效範圍**：−5–95°。
- **A039**：
  - 任一碼封鎖時送 `alarm_raised`（只送一次），全部解除時送 `alarm_cleared`。
  - 加進 `active_codes()` 與 `ActiveEventLists`。
  - 操作員復位與維護清除的順序都是 008 → A039 解除 → `trip_cleared`。
- **物理層保護停機**：與訊號跳機共用每碼的跳機時間，超過上限時在跳機當下封鎖。

**物理層**（`turbine_physics.py`）：

- 刪掉 `max_restarts_per_hour` 與 `_max_restarts_exceeded` / `_restart_timestamps`。
- A039 成立時機組進 SHUTDOWN（TurSt 1）。
- `TurbineSpec`：切出陣風 3 s、273 為 45 °C、液壓 170 bar＋解除 / 延時、233 延時與 60 s 平均、`pt100_filter_tau_s`。
- `yaw_sensor_drift`：漂移 24° × 嚴重度²。

**既有風場**：載入風場（`app.py` 啟動、`switch_farm`）改用 `TurbineSpec.from_farm_dict`，`Z72_PLC_SETPOINT_FIELDS` 不讓存檔覆寫。spec 更新 API 仍可明確修改。

**yaw drift 的數學**：

- PLC 看到的差異＝漂移 + (風向標 1 − 2 的安裝偏差)，偏差差落在 ±4.5°（風向標 1 ±2.5°、風向標 2 ±2°）。
- 線性映射的可行範圍只有 19.5–21°、邊界不到 1°。
- 平方映射 24° 在滿嚴重度 ≥ 19.5°、0.5 ≤ 10.5°，任何偏差都成立。

### 2.4 驗證

- **PLC 單元測試**：改寫 7 個依舊延時 / `restart_blocked` 的測試，新增 12 個（濾波、斷線不進濾波器、A039 成立 / 只送一次 / 維護清除、Appendix D 液壓、60 s 延時與 60 s 平均風速、保護停機每碼計數、351 上限 5、編碼器邊界、273、`from_farm_dict`）。
- **整合測試**（真物理）：
  - `generator_overspeed` 第 6 次 351、`grid_voltage_sag` 第 2 次 481 / 021 送 A039，機組停在 SHUTDOWN，操作員復位後恢復發電。
  - 低風速反覆起停 3 h 不受限、沒有事件。
- **yaw drift 守門**：
  - 機制測試：300 種子的偏差差落在 ±4.5° 內。
  - 端到端：偏差最負（種子 273，−3.89°）/ 最正與原始重現種子 33 / 34 / 119，滿嚴重度都在 65 s 跳 233、0.5 都不跳。
- **健康機組最熱日**：37 °C、20 m/s 時機艙空氣最高 43.3 °C，低於 45。
- **§6.3 實測重量**：每個情境用新模擬器單獨跑。
  - hydraulic_leak 的 T228 2.3 → 2.8 分，A260 同一步。
  - yaw_sensor_drift 0.7 → 1.4 分。
  - 溫度事件差 ±0.1 分內。
- **範例資料包重建**：
  - PLC 事件都與 -02 前相同。
  - 01 / 02 / 04 完全不變。
  - 03 的 WT001 / WT002 多了低風速起停（不再被全域上限卡在待機，240 → 291 筆事件）。
  - 基準助手成績不變（8 case 全偵測、元件 87.5 %、類別 75 %）。
- **完整 backend**：（待補）
- **code review**（code-reviewer，沒有 must-fix）：
  - 審查者自己的驗證：
    - PLC 層 fuzz（150 種子 × 400 步，隨機穿插 evaluate / 保護停機 / 起動 / 復位 / 維護清除）與全模擬器 fuzz：A039 的成立 / 解除交替正確，事件碼陣列與 `active_codes()` 一致（只有碼 021 例外，見 S3）。
    - 16 情境清除後都回到發電、沒有卡死。
    - 健康風場 24 h（1 月 / 7 月）與 4 h × 5 種風速 0 個事件。
    - 手冊數值逐項對過。
  - 修正：
    - **S1**：命名情境開頭的乾淨機組沒清每小時跳機計數，Live 一小時內自動恢復過的保護停機（320 / 481 / 021）會讓情境的第一次同碼跳機就送 A039。加 `PlcProtection.clear_trip_counts()`，`start_clean_scenario` 對沒重設的機組呼叫（不動 RNG、不送事件）。測試證實修正前會出 A039。
    - **S2**：233 的風速條件原本把差異訊號歸零，60 s 平均比 10 分鐘更常掉到 4.5 m/s 以下，鎖存的跳機在風速低谷解除、風回來再跳，停機中的機組還出現 Shutdown → Normal Stop（範例資料包 03 的 WT003 跳 4 次）。改為判定窗（`gate`，Appendix D 寫的是「enable」）：只禁止新的成立。重建後 03 的 PLC 事件與 -02 前相同。
    - **S5**：保護停機在執行中新增 `_codes` 的鍵，API 執行緒的 `operator_reset` 迭代時可能 `dictionary changed size`。改為 reset 時建好全部碼，迭代用複本。
  - 寫進 DEC 的取捨：
    - **S3**：021 不分成因一起計數（手冊「identical trips」以事件碼計）。
    - **S4**：訊號跳機在解除時、保護停機在跳機當下判定封鎖。
  - nit：過時註解（5 秒、180 bar、restart tracking、維護復位的陣列說明）、合約 §10 的 `manual_only` / `unattributed_events` 說法、A039 進 OPC UA 每步一致性測試、封鎖次數改由目錄上限推算、`Z72_PLC_SETPOINT_FIELDS` 守門測試。
  - 留著不修：
    - 021 訊號 / 保護兩條路徑重疊時的陣列短暫不一致：-01 已列 nice-to-have，不是這次引入。
    - 已停機時 PLC 跳機仍走一次 Normal Stop（同上）。

## 3. 產出清單

### 新增檔案

- `work-logs/2026-10/2026-10-23-manual-fidelity.md`

### 修改檔案

- **程式**：
  - `modules/monitoring/simulator/physics/plc_protection.py`
  - `simulator/physics/turbine_physics.py`
  - `simulator/engine.py`
  - `server/app.py`
  - `server/data_broker.py`
  - `server/scenario_pack.py`（說明）
  - `simulator/ground_truth.py`（`CONTRACT_VERSION` 1.4）
  - `shared/alarm_codes.py`（說明）
  - `tools/build_z72_alarm_catalog.py`
- **資料**：
  - `shared/data/z72_alarm_catalog.json`（+A039）
  - `shared/data/rag_assistant_vocabulary.json`（1.4）
  - `examples/rag_starter_kit/`（4 個範例資料包、答案、vocabulary）
- **測試**：
  - `tests/test_alarm_codes.py`
  - `tests/physics/test_fault_threshold_reach.py`
  - `modules/monitoring/tests/test_plc_protection.py`
  - `test_plc_integration.py`
  - `test_reset_keeps_fault.py`
- **文件**：
  - 合約 v1.4
  - `decision_log.md`（DEC-20261023-01）
  - EPIC-DS 設計文件（§6.3、§6.12、§6.15）
  - `physics_model_status.md`
  - 架構文件、README、ROADMAP、kit README、CLAUDE.md
  - ISSUES、STATUS、TODO

### 動了狀態的 issue

- WMOM-20261022-02：open → done

### 寫進 decision_log 的決策

- DEC-20261023-01：手冊 Appendix C / D 衝突以 D 為準、自動重啟被封鎖送 A039、拿掉全域每小時啟動上限

## 4. 下次怎麼接手

1. **-08 其餘子項**：開工時請劉老師挑順序——誤報 / 健康負樣本與評分、多重故障 + 早期徵兆、故障庫擴充。做多重故障時，先定同機組多 case 的評分規則（-01 review：「每個元件猜一遍」可拿 (k−1)/k）。
2. **手冊仍未對上**：
   - 236 塔架加速度：要把機艙振動改成加速度、或加 `VibMsNacR`。
   - Appendix D 的暴風等級：`SDVwind_Storm_10m` 27 m/s → 204 Storm park。
3. **-01 的 nice-to-have 仍在**（設計文件 §6.14「留給後續」3），例如已停機時 PLC 跳機仍走一次 Normal Stop、021 兩條路徑重疊時陣列短暫不一致。

## 5. 學到的事

- 手冊不是單一真相：同一份手冊的 Appendix C（說明文字）與 Appendix D（設定值）會打架。這類取捨要寫成原則（以設定值為準），並在合約告訴受測端「RAG 查到的文字可能和資料差幾 bar / 幾秒」。
- 守門測試只用一個種子，會漏掉跟機組個體差相關的問題。有個體差參與判定的條件，要用機制測試掃種子範圍，再對極端種子端到端。
- 「關掉 PLC 量物理」的測試會不知不覺依賴其他保護機制。這次拿掉全域上限後，grid sag 測試才露出它其實在靠那個上限讓機組停在最後一筆。
- 改「條件」時要想「已成立的狀態」怎麼辦：風速條件從 10 分鐘改 60 s 本身沒錯，但原本「把訊號歸零」的寫法讓條件同時決定了解除，換更短的平均才露出來。判定窗（只管新成立）與解除條件要分開。
- 背景跑完整測試時不要 `git stash`：工作目錄會短暫變回 base，跑到一半的測試結果就不可信（這次停掉重跑）。
