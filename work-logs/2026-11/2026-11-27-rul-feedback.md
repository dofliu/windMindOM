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
- 完整 backend、code review：見 §4。

## 4. Code review 與處理

（見下方更新）

## 5. 下次接手

- 劉老師回覆確認頁後：`ArtifactData` 讀 `decisions` collection，依列 ID 改 `z72_onshore_costs.json`（`onshore.*`）、`z72_repair_classes.json`（`ftc.*` → `scenarios`、`k13.*` → `k13_components`）、`failure_rates.DEFAULT_PRIOR_TURBINE_YEARS`（`feedback.prior_turbine_years`）；要改的列在 work-log 記下來源與理由。
- 已知限制：結垢在 0.35 封頂（約 8 年），封頂時換的零件之後不會再老；保險、土地租金、電網費沒有列。
