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

- `test_inspection_plan.py` 16 項：每台一個排程、錯開 1 / 2 / 3 天、人工排程器（實際時間比測試風場晚快一年）不開單；到期開單、同一期不再開、產生例行巡檢卡、下一台接著到期；已有未結案的定檢工單算那張；三張上限擋下不推進、下次再試；重啟不重建排程、不重開；**潛伏的變壓器過熱（沒有警報、沒有工單）由自動定檢開單 → 維修班施工 → 修掉，故障紀錄記是那張工單修的**；關＝全部暫停、改週期重新錯開、人暫停的保留；批次期間與閉環關著時不動；設定檢查、存在風場 DB、啟動預設、端點只給主管。
- workflow：`test_inspection_scheduler.py` 加 1 項（跳過自動排程）、`test_inspection_repository.py` 加 2 項（`reschedule`）。
- `test_scenario_endpoints.py` 的批次守門清單加 `PUT /api/operations/inspection-plan`。
- 前端 `OperationsPage.test.tsx` 加 2 項（列出排程、儲存週期；週期不合法不送），`tsc` 無錯。

## 5. 下次接手

- 預設週期 182 天請劉老師確認；依季節 / 風況排定檢、定檢時數依機組狀況不同、定檢沒找到故障時的紀錄都沒做（寫在 DEC-20261127-05）。
