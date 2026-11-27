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

## 3. 結果（code review 修正後）

資料包：z72-starter-01, z72-starter-02, z72-starter-03, z72-starter-04, z72-starter-05, z72-starter-06, z72-starter-07

| 資料條件 | 出勤 | 有故障 | 重點訊號被標出 | 觸發跳機的故障的訊號被標出 | 重點訊號在卡上 | 沒有故障卻標了偏高 / 偏低 | 電網事件列出同場同碼 | 卡片標示資料有問題 |
|---|---|---|---|---|---|---|---|---|
| 原始 10 秒資料 | 29 | 17 | 65% | 65% | 70% | 0% | 100% | 41% |
| 缺測兩成 | 29 | 17 | 59% | 59% | 70% | 0% | 100% | 45% |
| 讀值晚 15 分鐘 | 29 | 17 | 47% | 47% | 70% | 0% | 100% | 100% |
| 一成讀值重複 | 29 | 17 | 65% | 65% | 70% | 0% | 100% | 41% |
| 只有 10 分鐘統計 | 29 | 17 | 71% | 71% | 70% | 0% | 100% | 76% |

從沒跳過機、不會有出勤的故障 case（不在上面的比例裡）：z72-starter-06:C001（yaw_misalignment）、z72-starter-07:C003（stator_winding_degradation）、z72-starter-07:C006（main_bearing_temp_sensor_drift）

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
| z72-starter-05 | WT003 | 242 | main_bearing_temp_loose_contact | — | 否 | no_baseline |
| z72-starter-05 | WT001 | 482 | grid_voltage_dip | — | 否 | — |
| z72-starter-05 | WT002 | 482 | grid_voltage_dip | — | 否 | — |
| z72-starter-05 | WT004 | 482 | grid_voltage_dip | — | 否 | — |
| z72-starter-05 | WT003 | 242 | main_bearing_temp_loose_contact | — | 否 | — |
| z72-starter-05 | WT001 | 489 | grid_frequency_excursion | — | 否 | too_few_peers |
| z72-starter-05 | WT002 | 489 | grid_frequency_excursion | — | 否 | too_few_peers |
| z72-starter-05 | WT003 | 489 | grid_frequency_excursion | — | 否 | — |
| z72-starter-05 | WT004 | 489 | grid_frequency_excursion | — | 否 | too_few_peers |
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

- **出勤**：29 次（17 次那台機組有故障、12 次沒有）。同一台機組 30 分鐘內又跳的算同一次停機（自動重啟後再跳）；工單什麼時候結案在資料包裡看不到，所以是近似。
- **有故障的出勤：重點訊號被標出 65%**（11/17）；只看觸發這次跳機的故障也是 65%（這批題庫沒有被同機組的潛伏故障灌水）。依風場大小：5 台以上的資料包 8/11，3–4 台的只有 3/6——同場發電中的機組少於 3 台時卡片不比（`too_few_peers`），訊號全是「不明」。仿真風場是 14 台，這個問題主要在小的範例資料包。
- **沒標出的另外三個都是感測器故障**：風向標 1 漂移（233）、轉速感測器（029）、風向標 1 卡住（231）——讀值本身看起來正常（漂移、卡在合理的值），和同場比不出來。這是題庫刻意出的難題；卡片照規則「證據不足就不判讀」。
- **沒有故障的出勤：誤判 0/12**。電網電壓驟降、電網頻率越界、風向快速變化、Pt100 接觸不良都沒有誤判；電網事件 100% 列出同場同時同碼的機組。卡片在接觸不良時標出那支溫度讀值、在頻率越界時標出頻率——那是干擾自己的訊號、是對的證據，評分改成不算誤判（`score_card`，即時風場的評分同一套）。
- **從沒跳過機的故障 case**（靜態偏航失準、兩個早期徵兆）不會有出勤，不在上面的比例裡，報告另列。
- **手冊**：每個跳機碼都在警報目錄查得到。
- **資料條件**：
  - 缺測兩成：65% → 59%（一張變成沒標出），卡片多標一次沒有基準。
  - 讀值晚 15 分鐘：65% → 47%，但每張卡都標了「資料過期」——卡片知道自己看不到最後那段。
  - 一成重複：和原始一模一樣。
  - 只有 10 分鐘統計：71%，和原始差不多（多的那一張是同場機組數的算法不同，不是真的變好），**但 76% 的卡標了資料有問題**：新鮮度規則（最後一筆離截止點超過 5 分鐘）是照 10 秒資料定的，10 分鐘資料一定會被標成過期。開 WMOM-20261127-09。

### 3.2 對企劃指標的意義

- 審查時建議補的「下一步的正確性」：這裡量的是「卡片的證據有沒有指對地方」（重點訊號、同場同碼、手冊），不是準備時間——準備時間要真人或真實風場才量得到。
- 規則版在題庫上的表現有了基準線，之後改卡片（或加語言模型整理，企劃的 C）可以拿同一份重播比。

## 4. 驗證

- `test_briefing_replay.py` 11 項（含審查後補的：合約的時間窗、干擾自己的訊號不算誤判）；`test_briefing.py` 照過。
- 完整 backend（審查前）：2690 passed / 7 skipped / 1 xfailed。審查後相關的 monitoring 測試（準備卡、巡檢卡、閉環、風場事件、對外 API）158 passed / 6 skipped。

## 5. Code review（code-reviewer subagent）與處理

- 資料包換掉的兩個介面忠實（順序、時間窗、游標、時間字串格式、NaN、晚到），答案沒有流進卡片。
- **該修，都修了**：
  - 答案歸屬照合約 §8：`pre_existing`（開始是 null）從 `sim_start` 起算、被取代的 case 不另算、時間窗結束後不算；干擾的比對改用 case 自己的時間窗（第一次警報到 `window_end_ts`，null＝資料包結束），不拿故障開始的時間比——會一再跳的接觸不良，後面那次跳機也對得到（加合成的測試）。
  - 同一台機組同時有潛伏的故障時「重點訊號被標出」會偏樂觀 → 另算只看觸發這次跳機的故障。
  - 比例只算有出勤的 → 報告另列從沒跳過機的 case。
  - 護欄門檻完全沒有餘裕 → 門檻放到 50% / 25%（重建範例資料包後雜訊會變），另外釘住幾個不該變的結果（軸承磨耗、變槳馬達標得出來、電網驟降不誤判且列出同場同碼、沒有警報的故障另列）。
  - 重複讀值的測試要求完全相同 → 改成最多差一張、各資料條件的出勤數相同。
  - 「沒有故障時誤判」的定義：干擾 / 風場事件自己的訊號不算（`score_card`，即時風場的評分同一套）。
- **小地方**：`bisect` 用標準庫、補 docstring、找不到答案檔時給清楚的錯誤、資料包時間要帶時區、CLI 測試用 `monkeypatch.syspath_prepend`。出勤的合併改成「離上一次跳機 30 分鐘內」並寫明是近似（原本 2 小時從第一次算，會把資料包 05 的頻率越界、風向變化併掉）。沒改的：讀值用 float64（資料包本身已經是 PLC 型別的值，放寬成 float64 不改值）。

## 6. 下次接手

- WMOM-20261127-09：卡片認得只有 10 分鐘資料。
- 小風場：同場發電中的機組少於 3 台時，可以考慮和自己過去的資料比（目前只標 `too_few_peers`）。
- 階段 B（5–10 件真實案例人工評估）仍要授權的真實資料。
