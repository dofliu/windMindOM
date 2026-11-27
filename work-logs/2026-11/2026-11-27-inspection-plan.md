# 2026-11-27 — 依風場時鐘定期開定檢工單（WMOM-20261127-03）

> Session 類型：實作
> 主導：Claude（劉老師：「照你的建議做定期開定檢工單」）
> 結果：done，DEC-20261127-05。

---

## 1. 為什麼

例行巡檢卡（WMOM-20261126-05）做好了，但定檢工單要人開，或要人呼叫 `run-scheduler`（用實際時間）。仿真風場自己運轉時沒有定檢，潛伏的故障（劣化到頂、到不了警報門檻，DEC-20261127-01）就一直留著。

## 2. 決定了什麼

issue 列的三件事：

1. **預設的排程**：每台機組每 182 天一次（半年），第一次到期在 `182 × (i + 1) ÷ 機組數` 天後——全場錯開（14 台約每 13 天一台）。之後每次開單從開單當下再算一個週期。
2. **批次期間不跑**：只在運維閉環的 `account` 裡跑（即時模擬把讀值寫進歷史之後），批次與還原存檔後的重跑段都不會呼叫。
3. **重啟後不重複開**：排程與上次開單存在 workflow 的定檢排程表；開過單就推進到下一期。開單之後、推進之前伺服器被強制關閉的話，重啟後那台機組已經有未結案的定檢工單，這一期就算那張。

另外決定的：

- **用 workflow 現成的排程表**（每台機組一個，`created_by` 是固定的 `PLAN_ACTOR`），定檢排程的畫面看得到、人可以暫停某一台。workflow 的人工排程器（實際時間）跳過這些排程（`automated_schedule_owner`），兩個時鐘不混。
- **不堆積**：已有未結案的定檢 / 預防保養工單就不再開。沒有人處理的定檢工單一期一張堆起來會佔滿每台三張的上限，跳機開不了單。
- **設定改了才整理排程**；改週期或暫停過期後重新啟用都重新錯開（workflow repository 加 `reschedule`），不會一打開全場同時到期。

## 3. 改了什麼

- `modules/monitoring/server/inspection_plan.py`（新）：`InspectionPlanConfig`（`enabled`、`interval_days` 1–730）、`InspectionPlan`（`step` / `_sync` / `_spawn`）。
- `server/om_loop.py`：`inspection_plan` 屬性；`account` 在維修班之前呼叫；`rebuild` 時重設。
- `server/data_broker.py`：`SETTING_INSPECTION_PLAN`，`apply_live_settings` 載入。`server/app.py`：`WMOM_INSPECTION_PLAN`。
- `server/routers/operations.py`：`GET/PUT /api/operations/inspection-plan`（主管；`PUT` 掛 `reject_during_batch`）。
- `modules/workflow/services/inspection_scheduler.py`：`automated_schedule_owner`；`repository/inspection_repository.py`：`reschedule`。
- 前端：`operationsService.ts` 加 `fetchInspectionPlan` / `saveInspectionPlan`；營運頁「自動運轉」加「自動定檢計畫」卡（開關、週期、各機組的下一次到期與上次開單）。
- 文件：DEC-20261127-05、ISSUES、STATUS、CLAUDE.md（自動定檢計畫守則）、README 的環境變數表。

## 4. 驗證

- `test_inspection_plan.py` 16 項（code review 後 20 項，見 §5）：每台一個排程、錯開 1 / 2 / 3 天、人工排程器（實際時間比測試風場晚快一年）不開單；到期開單、同一期不再開、產生例行巡檢卡、下一台接著到期；已有未結案的定檢工單算那張；三張上限擋下不推進、下次再試；重啟不重建排程、不重開；**潛伏的變壓器過熱（沒有警報、沒有工單）由自動定檢開單 → 維修班施工 → 修掉，故障紀錄記是那張工單修的**；關＝全部暫停、改週期重新錯開、人暫停的保留；批次期間與閉環關著時不動；設定檢查、存在風場 DB、啟動預設、端點只給主管。
- workflow：`test_inspection_scheduler.py` 加 2 項（跳過自動排程、沒載入 monitoring 也跳過仿真風場的計畫）、`test_inspection_repository.py` 加 2 項（`reschedule`）。
- `test_scenario_endpoints.py` 的批次守門清單加 `PUT /api/operations/inspection-plan`。
- 前端 `OperationsPage.test.tsx` 加 2 項（列出排程、儲存週期；週期不合法不送），`tsc` 無錯；前端全套 1538 passed。
- 完整 backend（code review 修正前）：2628 passed / 7 skipped / 1 xfailed。

## 5. Code review

沒有必須修的。建議修的四項都修了：

1. 人工排程器跳過自動排程原本靠 monitoring 的模組被 import 時才登記——閉環關著或只用 workflow 的 API 時，實際時間的排程器會跑到計畫的排程。改成建立者 ID 定在 workflow（`SIMULATED_FARM_PLAN_OWNER`）、載入時就登記。
2. 人暫停的排程在重啟、批次結束（設定從風場 DB 再套一次）之後被重新啟用，和說明不符。改成上次整理時的設定存在風場 DB（`inspection_plan_state`），設定沒變就不動既有的排程，少了的排程照樣補建。
3. 到期了開不了單（未結案工單滿了）只記 debug、畫面看不出來：`GET /inspection-plan` 加 `overdue`、營運頁顯示「到期、還沒開單」，log 每個排程記一次 info。
4. 整理排程失敗時每一步都重試、每 10 秒一筆錯誤：改成隔 15 分鐘（風場時鐘）再試。

另外照 nit 修了：人開的定檢工單用畫面名稱（`WTG-01`）也算數、狀態鍵改用 DB 路徑、`_sync` 整段用同一份設定。測試加 4 項（人暫停的排程經過重啟 / rebuild / 批次後套設定 / 存同樣設定都留著、少了的排程補建而不動其他、整理失敗 15 分鐘後再試、畫面名稱的工單算數），重啟測試加「從比開單早的時刻接著跑不再開」；`test_inspection_plan.py` 共 20 項。變異檢查：拿掉「設定沒變不動」、拿掉名稱對應、拿掉重試間隔，各有測試失敗。workflow 加 1 項（沒載入 monitoring 也跳過）。

## 6. 下次接手

- 預設週期 182 天請劉老師確認；依季節 / 風況排定檢、定檢時數依機組狀況不同、定檢沒找到故障時的紀錄都沒做（寫在 DEC-20261127-05）。
