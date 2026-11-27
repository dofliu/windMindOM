# 2026-11-27 — 風場事件在即時模擬裡依機率發生（WMOM-20261126-07）

> Session 類型：實作
> 主導：Claude（劉老師：「好 照你的建議做風場事件的機率觸發」）
> 結果：done，DEC-20261127-10。預設關（`WMOM_FARM_EVENTS` 或營運頁打開）。

---

## 1. 問題

- 電網電壓驟降、電網頻率越界、風向快速變化（`simulator/farm_events.py`）只在批次情境依排程套用。
- 即時風場碰不到「看起來像故障、其實不是」的情況：準備卡的「同場同時同碼」與評分的 `false_escalation` 幾乎沒資料。
- Issue 的四點：(1) 即時模擬裡套用與復原（干擾守則）；(2) 故障產生器同一套機制、自己的亂數；(3) 故障紀錄記成 nuisance；(4) 準備卡與 `false_escalation` 有資料。

## 2. 改了什麼

- `simulator/farm_event_generator.py`（新）：`FarmEventGeneratorConfig`（各種事件的 `mean_days_between`〔null＝不產生〕、強度與時長範圍；檢查不合法的設定）、`FarmEventGenerator`（每 60 模擬秒檢查一次、每種事件固定抽三個數、關著不抽、同一種事件進行中不重開；事件留到結束後 `RECORD_GRACE_S`＝30 分鐘）、`grid_override`。
- `simulator/engine.py`：`_run_one_step` 一開頭、不是批次時呼叫 `_apply_live_farm_events`（產生器擲骰、拿掉記錄期間已過的、套用進行中的電網 / 風向、沒有就復原）；`generate_bulk` 開頭拿掉 Live 的覆寫；產生器加進 `_CHECKPOINT_FIELDS`。
- `simulator/grid_model.py`：`event_override_active`。
- `server/fault_record.py`：`reconcile_farm_events`（每台機組一筆、`origin="farm_event"`；審查後改成依產生器的狀態對帳，見 §4），PLC 事件用事件種類的 `event_codes` 當預期碼，`cases()` 給 nuisance 答案（`farm_event_answer`）。
- `server/data_broker.py`：`_record_farm_events`（`_detect_sim_events` 一開頭，PLC 事件之前；`_recording_faults` 擋掉重跑與去重的步）；`SETTING_FARM_EVENTS` 與 `apply_live_settings`。
- `server/briefing.py`：`capture_answer` 加 `farm_events`（評分答案，卡片不帶）。
- `server/routers/operations.py`：`GET/PUT /api/operations/farm-events`（永遠強制的主管，PUT 掛 `reject_during_batch`）；`server/app.py` 預設 `WMOM_FARM_EVENTS`。
- 前端：營運頁「自動運轉」加「風場事件」卡（`FarmEventsCard.tsx`；各種事件平均幾天一次，空白＝不產生；列出還在記錄期間的事件）。

## 3. 驗證

- `modules/monitoring/tests/test_live_farm_events.py` 21 項（含 §4 審查後補的）：
  - 產生器：關著不抽、每種事件固定抽三個數、頻率越界有正有負、同一種不重開、存檔、記錄期間、設定檢查與來回。
  - 引擎：只在即時模擬擲骰；沒有事件時讀值逐位元不變；電網 / 風向在事件期間覆寫、結束復原、批次期間不套用；批次不帶 Live 的覆寫。
  - 運維：3 台發電中的機組遇到 0.6 p.u. 的驟降全部以 482 跳機；故障紀錄每台一筆 nuisance，記錄期間過後以事件結束時間結束、不算維修；三張工單的答案都標出電壓驟降、`has_fault` 為 false，卡片不帶答案、「同場同時同碼」列出另外兩台。
  - 端點：設定存在風場 DB、重套、422、只給永遠強制登入的主管。
- `test_scenario_endpoints.py` 的批次期間擋下清單加 `PUT /api/operations/farm-events`。
- 前端營運頁 18 項（加 1 項），`tsc` 無錯。
- 完整 backend（審查前）：2680 passed / 7 skipped / 1 xfailed。

## 4. Code review（code-reviewer subagent）與處理

- **沒有要修的**；干擾守則、故障產生器守則、盲測守則、批次守則都核對過。
- **該修**：
  - 沒關掉的 farm_event 紀錄會一直開著、擋住之後同一種事件的紀錄（程式更新後存檔不還原、重啟去重的那幾步漏了結束）→ 不再靠「這一步開始 / 結束」的通知，改成 `FaultRecorder.reconcile_farm_events` 依產生器現在的狀態對帳：事件開始 / 結束那一步、以及每 60 模擬秒對一次；對不到事件的紀錄關掉，發生時間和事件不一樣的也關掉、新事件自己開一筆（加測試）。
  - 同一種事件在前一個的記錄期間（30 分鐘）內又發生，會記到前一筆、然後被提早關掉 → 產生器在記錄期間內也不重開同一種（照樣抽三個數，加測試）。
- **小地方**：`AutomationPanel.tsx` 被 Prettier 整份改成雙引號 → 還原，只留三處改動；兩個新卡片改成和資料夾一致的單引號。故障紀錄加來源篩選（`source=generator|manual|farm_event`，風場事件每次每台一筆，看故障時可以濾掉）。`configure` 補一行跨執行緒的說明。沒改的：`CHECKPOINT_VERSION` 不升（程式指紋已經讓舊存檔不還原，加故障產生器時也沒升）。
- 修完：相關的 monitoring 測試 292 passed / 6 skipped；`test_live_farm_events.py` 21 項；前端營運頁 18 項、`tsc` 無錯。

## 5. 下次接手

- 發生率與強度、時長範圍是假設值；有真實風場或手冊的資料再換（營運頁或 `PUT /api/operations/farm-events`）。
- 開著維修班時，事件造成的跳機工單也會被派工、完工（沒有對應的故障，只做復位），算進停機與人工——和真實「派人去看才知道沒事」一樣。
