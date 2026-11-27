# 2026-11-27 — 換零件的耗損回饋、故障率回饋與成本表確認（WMOM-20261127-07）

> Session 類型：實作
> 主導：Claude（劉老師：「好 照你的建議做 RUL 回饋與成本表確認」）
> 結果：done，DEC-20261127-09。成本假設確認頁已發布，等劉老師逐列回覆。

---

## 1. 問題

- 原始規格（WMOM-20260504-11 第 3 點）：「工單填料件清單 → 對應 component 表 → cost + RUL adjustment；影響下次 monte_carlo 的 `freq_min/ml/max`（empirical update）」。
- 故障產生器的耗損看整台機組的疲勞（塔架 / 葉片 Miner 總和）與冷卻結垢，參考值 0.1 / 0.02 約三個月到頂，之後發生率一直是 5 倍，換了零件也不會降。
- 物理模型的 RUL（`WLOD_RulHours`）是塔架與葉片的結構壽命；模擬的故障沒有一個會換塔架或葉片，所以回饋的對象是產生器的「零件耗損」。
- 成本模組的蒙地卡羅用 K13 的年故障率 × (0.7, 1, 1.3) 三角分布（adapter），和本風場的維修紀錄無關。K13 JSON 裡另一組 `annual_failure_freq_min/ml/max` 沒有被用到。

## 2. 改了什麼

- `simulator/fault_generator.py`：`part_of`（真故障換元件、感測器故障只換感測器、結冰 / 電網 / 干擾沒有換）、`raw_wear`、`FaultGenerator.record_replacement` / `part_wear` / `replacements`；`scenario_weights` / `hazard_per_second` 多一個 `parts`。不加亂數抽樣、物理狀態不改；`_replaced` 整份換掉（API 執行緒寫、Live 執行緒讀）。
- `server/om_loop.py`：`_finish` 修掉故障後記換掉的零件（時間用風場時鐘）；`failure_observations(start, end)`。
- `server/storage.py`：`repaired_fault_counts`（由工單修好的故障依情境計數）。
- `modules/cost/data/z72_repair_classes.json`：新增 `k13_components`（情境 → K13 元件代碼，假設值）。
- `modules/cost/services/failure_rates.py`（新）：可信度加權、`apply_rate_updates`（三角分布比例不變）、維修紀錄來源的登記。
- 端點：`GET /api/operations/failure-rates`、`POST /api/cost/monte-carlo/empirical`（都是永遠強制的主管）；故障產生器的 `GET` 加 `wear`。伺服器開機時登記維修紀錄來源。
- 前端：營運頁收支分頁加「故障率回饋」表（`FailureRatesCard.tsx`）。
- 成本假設確認頁（artifact）：https://claude.ai/artifact/MxC1AaPVnhaCoJrj3GvSup ——陸域固定成本與吊車 9 列、修復等級 24 列、K13 元件對應 24 列、回饋的做法 3 列；每列「同意 / 要改」，要改時填新值與原因，存在頁面資料庫 `decisions/<列 ID>`。已用一筆測試文件寫入、讀回、刪除確認可用。

## 3. 驗證

- 新增 `modules/monitoring/tests/test_failure_feedback.py`：零件規則、換新後發生率下降（其他零件照舊、感測器不帶主軸承）、抽樣次數不變與存檔、完工記零件與維修紀錄（後門清掉的不算）、故障產生器的耗損畫面、情境對 K13 元件涵蓋全部情境、可信度加權與三角分布、兩個端點（含永遠強制登入）、伺服器的維修紀錄來源。
- 相關的既有測試：成本、故障產生器 / 維修班、運維閉環、收支、續跑、自動定檢、報表 288 passed / 6 skipped / 1 xfailed。
- 前端營運頁 17 項（加 2 項），`tsc` 無錯。
- 完整 backend（審查前）：2660 passed / 7 skipped / 1 xfailed。

## 4. Code review（code-reviewer subagent）與處理

- **要修**：
  - DEC 還沒寫 → 寫了 DEC-20261127-09，ISSUES / STATUS / CLAUDE.md 一起更新。
  - 伺服器在完工之後、下次存檔之前被強制關閉，換掉的零件會不見 → 查過：`_finish` 記完零件之後的完工事件（`source="workflow"`）本來就會要求立即存檔，和清掉故障同一次存；補測試確認完工有要求存檔。
  - 蒙地卡羅端點讀風場用成本模組預設的 registry，和 `/failure-rates` 不同 → 維修紀錄帶伺服器的 `farm_registry`，端點用它讀風場（加測試：只登錄在伺服器的風場不會掉回 K13）。
- **該修**：
  - 結垢被清掉後零件耗損一直是 0 → 低於換新當下時從現在的量算（加測試）。
  - 耗損畫面兩次取快照 → 改用 `.get`。
  - 手動注入的故障也算進故障率 → 只算故障產生器產生的，手動注入的另外回報 `excluded_manual`，營運頁顯示（加測試）。
  - 端點在事件迴圈上查資料庫、跑蒙地卡羅 → 放到背景執行緒。
  - 預設時間窗在即時模擬沒跑時用實際時間 → `OmLoop.history_window` 看資料時鐘（同保留期），兩個端點共用（加測試）。
  - 型別 `Optional[object]` → `Optional[FailureObservations]`。
- **小地方**：耗損來源共用 `_part_source`、`component_map` 回唯讀的 `MappingProxyType`、`z72_repair_classes.json` 還原原本的排版（只剩新增的列）。沒改的：權限測試接受 401 / 403（和既有收支端點的測試一致）。
- 修完：受影響的後端 288 passed / 6 skipped / 1 xfailed；`test_failure_feedback.py` 10 項；前端營運頁 17 項、`tsc` 無錯。

## 5. 確認頁的回覆（2026-11-27）

- 劉老師說「確認頁回完了，讀回來改設定檔」。`ArtifactData` 讀 `decisions`：60 列全部 `choice: ok`、沒有新值也沒有備註（每列間隔約 0.3 秒，看起來是各節的「沒回覆的都同意」按的）。
- 設定檔的值都不變；`z72_onshore_costs.json`、`z72_repair_classes.json`（兩段說明）、`simulation_costs.py` 的說明、DEC-20261127-08 / -09、ISSUES、STATUS、CLAUDE.md 改成「2026-11-27 劉老師確認」。`onshore.other_fixed` 同意＝保險、土地租金、電網費維持不列。

## 6. 下次接手

- 之後要改成本假設：同一頁可以再用（`decisions/<列 ID>`）；`onshore.*` → `z72_onshore_costs.json`、`ftc.*` → `z72_repair_classes.json` 的 `scenarios`、`k13.*` → `k13_components`、`feedback.prior_turbine_years` → `failure_rates.DEFAULT_PRIOR_TURBINE_YEARS`。
- 已知限制：結垢在 0.35 封頂（約 8 年），封頂時換的零件之後不會再老；保險、土地租金、電網費沒有列。
