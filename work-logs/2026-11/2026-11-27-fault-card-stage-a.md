# 2026-11-27 — 故障出勤卡 階段 A：離線重播與自動評分（WMOM-20261127-08）

> Session 類型：實作
> 主導：Claude（劉老師：「照你的建議，先做故障出勤卡，從階段 A 開始」）
> 結果：done，DEC-20261127-11。新開 WMOM-20261127-09。

---

## 1. 這個「階段 A」是什麼

- 出自 2026-11-24 審查出發前助理企劃的建議（`2026-11-24-predeparture-assistant-review.md` §2.4）：先決定先做哪張卡，再從階段 A（離線重播：讀盲測版資料包產生卡片、用標準答案自動評分；補資料品質劣化與只有 10 分鐘資料的模式）開始。
- 之後重新定位（DEC-20261125-01），故障出勤卡已經在即時風場做好（WMOM-20261125-05）。所以這次做的是階段 A 還沒有的部分：拿題庫整批重播、評分，試資料有問題與只有低頻資料的情況。

## 2. 改了什麼

- `modules/monitoring/server/briefing_replay.py`（新）：資料包包成卡片讀資料的兩個介面（`PackEvents.live_events`、`PackReadings.readings`）、出勤（每次停機一張、截止點＝跳機後一個取樣週期）、答案（從標準答案取故障 / 干擾 / 電網事件，重點訊號換成卡片用的欄位名）、五種資料條件（`degrade`、`ten_minute_frame`、讀值晚到用 `visible_until`）、評分與彙總、Markdown 報告。卡片用即時風場同一個 `build_fault_card`。
- `tools/replay_fault_cards.py`（新）：CLI，預設跑學生 starter kit 的 7 個範例資料包、全部資料條件。
- `modules/monitoring/tests/test_briefing_replay.py`（新，9 項）：事件與讀值和資料包逐筆相同、晚到看不到、10 分鐘表、劣化可重現、出勤與答案、範例資料包的護欄、資料有問題時卡片標出來、CLI。

## 3. 結果

資料包：z72-starter-01, z72-starter-02, z72-starter-03, z72-starter-04, z72-starter-05, z72-starter-06, z72-starter-07

| 資料條件 | 出勤 | 有故障 | 重點訊號被標出 | 重點訊號在卡上 | 沒有故障卻標了偏高 / 偏低 | 電網事件列出同場同碼 | 卡片標示資料有問題 |
|---|---|---|---|---|---|---|---|
| 原始 10 秒資料 | 24 | 17 | 65% | 70% | 14% | 100% | 38% |
| 缺測兩成 | 24 | 17 | 59% | 70% | 14% | 100% | 42% |
| 讀值晚 15 分鐘 | 24 | 17 | 47% | 70% | 0% | 100% | 100% |
| 一成讀值重複 | 24 | 17 | 65% | 70% | 14% | 100% | 38% |
| 只有 10 分鐘統計 | 24 | 17 | 71% | 70% | 14% | 100% | 79% |

## 原始資料的逐筆結果

| 資料包 | 機組 | 跳機碼 | 答案 | 重點訊號被標出 | 誤判 | 卡片的資料品質旗標 |
|---|---|---|---|---|---|---|
| z72-starter-01 | WT002 | 240 | bearing_wear | 否 | — | too_few_peers |
| z72-starter-02 | WT001 | 228 | hydraulic_leak | 是 | — | no_baseline |
| z72-starter-02 | WT004 | 21 | converter_cooling_fault | 否 | — | too_few_peers |
| z72-starter-03 | WT003 | 233 | yaw_sensor_drift | 否 | — | no_baseline |
| z72-starter-03 | WT005 | 336 | pitch_imbalance | 是 | — | — |
| z72-starter-04 | WT003 | 240 | main_bearing_temp_sensor_drift | 是 | — | — |
| z72-starter-04 | WT001 | 240 | bearing_wear | 是 | — | — |
| z72-starter-04 | WT004 | 229 | yaw_brake_pressure_sensor_fault | 否 | — | too_few_peers |
| z72-starter-05 | WT003 | 242 | main_bearing_temp_loose_contact | — | 是 | no_baseline |
| z72-starter-05 | WT001 | 482 | grid_voltage_dip | — | 否 | — |
| z72-starter-05 | WT002 | 482 | grid_voltage_dip | — | 否 | — |
| z72-starter-05 | WT004 | 482 | grid_voltage_dip | — | 否 | — |
| z72-starter-05 | WT002 | 223 | rapid_wind_direction_change | — | 否 | too_few_peers |
| z72-starter-05 | WT004 | 223 | rapid_wind_direction_change | — | 否 | too_few_peers |
| z72-starter-05 | WT001 | 223 | rapid_wind_direction_change | — | 否 | too_few_peers |
| z72-starter-06 | WT002 | 21 | converter_cooling_pump_wear | 是 | — | — |
| z72-starter-06 | WT001 | 367 | pitch_motor_fault | 是 | — | — |
| z72-starter-06 | WT003 | 21 | cooling_water_deionizer_exhausted | 是 | — | — |
| z72-starter-06 | WT004 | 29 | rotor_speed_sensor_fault | 否 | — | — |
| z72-starter-06 | WT006 | 231 | wind_vane1_stuck | 否 | — | — |
| z72-starter-06 | WT005 | 230 | anemometer_fault | 是 | — | — |
| z72-starter-07 | WT004 | 367 | pitch_motor_fault, cooling_water_deionizer_exhausted | 是 | — | — |
| z72-starter-07 | WT001 | 21 | bearing_wear, converter_cooling_pump_wear | 是 | — | — |
| z72-starter-07 | WT002 | 228 | yaw_misalignment, hydraulic_leak | 是 | — | — |

### 3.1 解讀

- **有故障的出勤：重點訊號被標出 65%**（11/17）。依風場大小：5 台以上的資料包 8/11，3–4 台的只有 3/6——同場發電中的機組少於 3 台時卡片不比（`too_few_peers`），訊號全是「不明」。仿真風場是 14 台，這個問題主要在小的範例資料包。
- **沒標出的另外三個都是感測器故障**：風向標 1 漂移（233）、轉速感測器（029）、風向標 1 卡住（231）——讀值本身看起來正常（漂移、卡在合理的值），和同場比不出來。這是題庫刻意出的難題；卡片照規則「證據不足就不判讀」。
- **沒有故障的出勤：誤判 1/7**。電網電壓驟降（3 張）、風向快速變化（3 張）都沒有誤判，而且電網事件 100% 列出同場同時同碼的機組。唯一的一張是 Pt100 接觸不良（242）：卡片標出那支溫度讀值異常——讀值確實異常，卡片沒有說是故障；評分的定義（沒有故障時標了偏高 / 偏低就算誤判）把它算進去。指標的定義要再想（感測器干擾時指出那支讀值是對的）。
- **手冊**：24 個跳機碼都在警報目錄查得到。
- **資料條件**：
  - 缺測兩成：65% → 59%（一張變成沒標出），卡片多標一次沒有基準。
  - 讀值晚 15 分鐘：65% → 47%，但每張卡都標了「資料過期」——卡片知道自己看不到最後那段。
  - 一成重複：和原始一模一樣。
  - 只有 10 分鐘統計：71%，和原始差不多（多的那一張是同場機組數的算法不同，不是真的變好），**但 79% 的卡標了資料有問題**：新鮮度規則（最後一筆離截止點超過 5 分鐘）是照 10 秒資料定的，10 分鐘資料一定會被標成過期。開 WMOM-20261127-09。

### 3.2 對企劃指標的意義

- 審查時建議補的「下一步的正確性」：這裡量的是「卡片的證據有沒有指對地方」（重點訊號、同場同碼、手冊），不是準備時間——準備時間要真人或真實風場才量得到。
- 規則版在題庫上的表現有了基準線，之後改卡片（或加語言模型整理，企劃的 C）可以拿同一份重播比。

## 4. 驗證

- `test_briefing_replay.py` 9 項。
- 完整 backend、code review：見 §5。

## 5. Code review 與完整測試

（下方補）

## 6. 下次接手

- WMOM-20261127-09：卡片認得只有 10 分鐘資料。
- 指標定義：感測器干擾（Pt100 接觸不良）時指出那支讀值，不該算誤判——評分要分「機組故障的誤判」與「感測器讀值異常的提示」。
- 小風場：同場發電中的機組少於 3 台時，可以考慮和自己過去的資料比（目前只標 `too_few_peers`）。
- 階段 B（5–10 件真實案例人工評估）仍要授權的真實資料。
