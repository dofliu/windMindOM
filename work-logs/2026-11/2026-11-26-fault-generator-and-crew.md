# 2026-11-26 — 第 5 項：機率式故障、故障紀錄、模擬維修班（WMOM-20261125-06）

> Session 類型：實作
> 主導：Claude（劉老師：「同意，照這個方向開始第五項」）
> 這一項拆成幾段，各自測試、各自開 PR。本檔隨每一段補上。

---

## -06-a　鎖存解除後機組重啟再跳（done）

**做了什麼**

- `simulator/engine.py`：`retrip_after_restart`。只在即時模擬生效（批次時無效）。
- `simulator/physics/fault_engine.py`：`keep_tripped_active`——跳過機的故障照樣作用在機組上。
- `simulator/physics/turbine_physics.py`：`lock_blocks_restart`——維護鎖擋不擋重啟。
- `server/data_broker.py`、`server/app.py`：`live_retrip`；伺服器依 `WMOM_LIVE_RETRIP` 預設開。
- `server/om_loop.py`：A039 在那台機組已有未結案的故障維修工單時不另開一張；帶著故障重啟、還在發電的那幾分鐘算發電。

**實測**（測試用的風場，軸承磨耗）：發電 → 跳機 240 → 80 秒後鎖存解除 → 重啟、發電約 5 分鐘 → 再跳 240 → 75 秒後 A039，機組停在 SHUTDOWN、240 保持鎖存。工單一張（240）。復位之後又跳；工單完工後 10 分鐘內沒有再跳。量測回路斷線：242 一直鎖著，行為和以前一樣。

**測試**：`test_a_faulty_turbine_restarts_and_trips_again_until_the_work_order_is_finished`、`test_batch_scenarios_keep_the_maintenance_lock`；`test_emergency_trips_and_blocked_restarts_get_high_priority` 依新的 A039 規則更新。backend 全部（本機）：2505 passed / 7 skipped / 1 xfailed。

**決策**：DEC-20261126-07。

**沒有做**：批次情境（題庫）維持跳機後停到維護清除，沒有改。

---

## -06-b / -06-c / -06-d　故障產生器、故障紀錄、模擬維修班（done）

**做了什麼**

- `simulator/fault_generator.py`（新）：每台機組一個卜瓦松過程。設定：開關、每台平均幾天一次、情境權重、機組權重、耗損的放大、劣化速度範圍、每台同時幾個、種子、耗損的參考值。掛在 `WindFarmSimulator.fault_generator`，進狀態存檔；`engine._run_one_step` 只在即時模擬呼叫。
- `server/fault_record.py`（新）＋ `fault_records` 表：故障出現 / PLC 事件 / 故障消失三個時機由 broker 呼叫；工單修掉故障時由運維閉環直接帶工單編號結束紀錄。
- `server/crew.py`（新）：模擬維修班，由運維閉環在每批讀值寫進歷史之後呼叫，每 60 個風場秒看一次工單。
- `server/storage.py`：`farm_settings` 表（設定與維修班的狀態）。
- `server/data_broker.py`：`apply_live_settings`（啟動即時模擬與批次結束時套用）。
- `server/routers/operations.py`：`GET / PUT /api/operations/fault-generator`、`/crew`，`GET /fault-records`。都只給主管、永遠強制；兩個 `PUT` 在批次期間回 409。
- `modules/workflow/repository/work_order_repository.py`：`skip_day_form_for`（不是真人的被派工者，結案時不寫當日工作表）。

**量到的數字**

- 耗損：3 台機組跑 4 小時，疲勞損傷約 2×10⁻⁴（換算每年約 0.4）、結垢係數 2×10⁻⁵（每年約 0.044）。所以耗損不能直接用 0–1 的原始值；參考值取疲勞 0.1、結垢 0.02。
- 整合測試：5 台機組、產生器（只用很快跳機的三個情境、平均 0.02 天一次）＋維修班（反應 5 分鐘、修復 10 分鐘、兩組）跑 5 小時，產生 5 個以上的故障，全部由工單修好；關掉產生器再跑 1 小時，沒有未結束的故障紀錄、沒有未結案的工單、5 台都在發電。

**code review**（`code-reviewer` 子代理）：2 項必須修、7 項該補強。

| 審查意見 | 處理 |
|---|---|
| **必須修**：設定的 `enabled` 用 `bool()` 轉，字串 `"false"` 會被當成開 | 改成只收布林值，其他丟錯；測試加上 |
| **必須修**：批次期間 `PUT` 設定會被批次結束時的狀態還原蓋掉，DB 與執行中的物件不一致 | 兩個 `PUT` 掛 `reject_during_batch`（守門測試的清單加上）；批次結束還原之後從風場 DB 再套一次設定 |
| 去重段（強制關閉後重跑最後幾秒）會重複計跳機次數 | `_recording_faults` 加上不在去重段；測試加上 |
| 維修班結案有簽核鏈的工單，會留下一條沒人簽的鏈 | 有簽核鏈的不碰 |
| `approve_all` 的副作用替維修班寫當日工作表（實際時間、假身分） | workflow 加 `skip_day_form_for`，維修班登記自己 |
| nuisance 與沒有警報的故障會一直佔著那台機組的名額；維修班的 `started` 在人接手後沒清；完工一直失敗時那一組永遠被佔 | nuisance 預設不產生；工單離開施工中就清 `started`；完工連續失敗 3 次放手 |
| `note_repair` 的登記可能留下過期項，把之後的手動清除誤記成舊工單 | 拿掉間接登記，完工時直接結束紀錄 |
| 耗損放大實務上幾乎沒效果（損傷的量級很小） | 量了實際的量級，加參考值（見上） |
| 每 60 風場秒列一次未結案工單、上限 500 | 沒有改：未結案工單每台最多三張，14 台最多 42 張 |
| 小建議：`id` 不該能改、多餘的私有屬性判斷、由關轉開時積壓的工單立刻被接手 | 都改了 |

沒有處理的一項：故障被清掉、同一步又注入同一個情境時，broker 的偵測看不出來，舊紀錄不會結束。機率很低（產生器每 60 秒才檢查一次、而且那台機組剛修好）。

**變異檢查** 20 項：18 項被抓到；2 項是重複的防護（批次期間不記故障紀錄、維修班不替人完工，各有兩道，拿掉其中一道另一道仍擋住）。

**回歸**：backend 全部（本機）2554 passed / 7 skipped / 1 xfailed（審查意見修完之後）。新增 `test_fault_generator.py` 29 項、`test_crew_and_records.py` 20 項。前端沒有動。

**決策**：DEC-20261126-08。

**沒有做**

- 風場事件（電網擾動、風向快速變化）的機率觸發：WMOM-20261126-07。
- 準備卡評分的彙整報表。
- 前端的設定畫面：目前只有 API。
- 真伺服器上的長時間驗證：這次只有測試用的風場。建議接著做 72 小時連續運轉測試（WMOM-20261126-01）。

## 下次怎麼接手

- 打開：`PUT /api/operations/fault-generator {"enabled": true}`、`PUT /api/operations/crew {"enabled": true}`（主管）；或啟動時設 `WMOM_FAULT_GENERATOR=true`、`WMOM_CREW=true`。
- 看答案：`GET /api/operations/fault-records`（主管）。
- 新增故障情境：如果它沒有警報、或自己會恢復，要加進 `fault_generator.DEFAULT_EXCLUDED`。
