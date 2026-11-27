# 2026-11-27 — 仿真風場的收支（WMOM-20260504-11，EPIC-SF 第 6 項）

> Session 類型：實作
> 主導：Claude（劉老師：「好 按照你的建議繼續」——先做潛伏故障 (d)，再進第 6 項成本）
> 結果：done，DEC-20261127-02。另開 WMOM-20261127-01。

---

## 1. 設計

原本的規格（2026-05）要把收入、少收的錢、支出全部寫進成本帳本。現在監控已經有運轉狀態紀錄（`availability_hourly`），可用率就是由它算的，所以：

- **收入與少收的錢不進帳本**，由運轉狀態紀錄 × 電價算：只有一份來源，時間基準同可用率（風場時鐘）。
- **工單完工時支出進帳本**：人工（實際工時 × 人數 × 時薪）、料件（修掉的故障對應的 K13 修復等級）；每張工單一次；有已出庫的領料單時料件不另算。
- 費率（電價、幣別、時薪）讀成本模組既有的農場設定；K13 只給年薪，時薪用年薪 ÷ 1800 小時。

## 2. 改了什麼

- `modules/cost/services/simulation_costs.py`（新）：`farm_rates`、`repair_class`、`work_order_cost_entries`、`revenue`、`summarize`。
- `modules/cost/data/z72_repair_classes.json`（新）：24 個故障情境 → K13 FTC（假設值）。
- `CostLedgerRepository.add_once_for_subject`：同一個交易裡先查後寫，每個 subject 一次。
- `server/om_loop.py`：`_finish` 之後 `_post_costs`（風場時鐘、出錯只記 log）。
- `GET /api/operations/finance`（主管、永遠強制；start / end 取整到整點，收入與帳本用同一個時間窗）。
- 月報：`MonthlyReportData.generation`（發電量、電價、收入、計畫 / 非計畫停機少收、運維支出、淨額），`set_revenue_provider`，伺服器接上運轉狀態紀錄；範本加一節。

## 3. 用長跑的資料試算

拿 WMOM-20261126-01 長跑（14 台、73 模擬小時）的資料離線算一次（K13 電價 0.13 EUR/kWh、時薪 83.3）：

| 項目 | 金額（EUR） |
|---|---|
| 發電量 473,226 kWh → 收入 | 61,519 |
| 非計畫停機少收 | 4,334 |
| 人工（12 張工單 × 4 小時） | 10,333 |
| 料件（7 張修到故障的） | 17,000 |

這份資料是修 bug 之前跑的，12 張工單裡有 5 張是重複或沒有故障的（DEC-20261126-09 已修），人工會比現在多算。

## 4. Code review

沒有必須修。修了三項：(1) 只有「已經出庫入帳」的領料單才讓料件不另算（草稿、退回的不算）；(2) 幣別和電價取同一層設定；(3) `/finance` 的時間窗取整到整點（運轉狀態紀錄以小時為單位）；另外沒有風場時鐘時不入帳（不混用實際時間）。沒改、寫進文件的：閉環沒跑時完工的工單不補入帳；簽核退回後再完工不重寫。

## 5. 驗證

`test_operations_finance.py` 10 項；reporting、cost、workflow、om_loop、crew、scenario endpoints 一起 914 passed / 6 skipped / 1 xfailed。

## 6. 下次接手

- 第 7 項 `WMOM-20261125-07`（實測風況匯入）。
- WMOM-20261127-01：設備與固定成本、RUL 回饋、前端畫面、修復等級表請劉老師看過。
