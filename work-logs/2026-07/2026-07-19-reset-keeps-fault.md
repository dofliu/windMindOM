# 2026-07-19 — 復位不清故障（bug fix）+ 啟動流程/情境保存（討論）

> Session 類型：Live 測試回饋處理（承 DEC-20260718-01 Scenario 模式上線後的實測）
> 產出：PR（本 #2 reset bug fix）+ #3/#4 設計討論（待拍板）
> 對應 issue：WMOM-20260719-01（reset 語意）｜#3 #4 待開 issue/DEC

---

## 做了什麼

1. **#2 復位語意修正（本 PR）** — 使用者實測回報：監控畫面按「復位(reset)」會把注入的故障
   直接清掉、機組立刻復電；照現場語意這不對（復位 ≠ 修好）。
   - **根因**：`server/routers/control.py` 的 reset 分支除 `model.cmd_reset()` 外，還多呼叫
     `fault_engine.clear(turbine_id=...)`，等於一按復位就刪掉未解決故障。
   - **修法**：移除該 `fault_engine.clear(...)`。引擎 `engine._run_one_step`（line 196-198）本就
     「每步只要該機組有 tripped 故障就重新 `cmd_emergency_stop`」，故移除後帶病機組復位會被
     引擎每步重壓在跳機(7)↔重啟等待(3)迴圈、**永不復電**。唯一真正清故障的路徑是維護中心
     `/api/faults/clear`（`faults.py::clear_faults`，會 `fault_engine.clear` + `turbine.reset()`）。
   - 更新兩處 docstring（control.py reset 說明、turbine_physics.py `cmd_reset`）。
   - 新增 `tests/test_reset_keeps_fault.py`（3 tests，引擎層守不變量）；monitoring 78 + physics 45 全綠。

## 眉角 / 決策

- **reset(Coil[3]) = acknowledge latched trip**，非 resolve fault。現場 reset 只是「確認並嘗試
  重啟」；故障實體只由維護（工單完成）清除。這正對齊使用者「照理說應該不行」的直覺。
- **「持續 grid trip」是另一機制**：`_check_grid_trip` 依 `_grid_frequency_ref`/`_grid_voltage_ref`
  的隨機漂移判斷，與注入故障**無關**；`cmd_reset` 已同時歸零 normal/emergency 兩個 accum，故
  復位不會惡化 grid trip。grid trip 於 grid ref 回到容忍帶後自行恢復（emergency 後有 20s
  restart block）。→ 本 PR 不動 grid 模型；若實測仍頻繁再另案處理（可先做 UI 區分故障 vs grid）。

## #3 / #4 討論（待拍板，先勘查現況）

- **#4 情境保存/調閱**：`generate-bulk` 目前把資料寫進**當前 active session**（`b._session_id`），
  無情境識別 → 融進歷史。但 storage 已有 `sessions` 表（`data_source` / 彈性 `config_json`），
  `turbine_data` 以 `session_id` 為單位。→ 建議把「情境」建模為**專屬命名 session**
  （`data_source="SCENARIO"`, `config_json={name, wind_profile, duration_hours, fault_schedule}`），
  generate-bulk 開新 session 寫入 + 新增 list/load/delete API。
- **#3 啟動模式選擇**：`app.py` lifespan 開機即 `broker.start(SIMULATION, 預設風場)` 自動跑，
  與登入無關 → 這就是「進系統就以預設風場產資料」。→ 建議開機不自動模擬（idle/未選狀態），
  強制登入後由前端選：實際對接 / 模擬 / 產生情境 / 選過去情境（後者依賴 #4）。
- 兩者皆 DEC 級（改 app 進入契約 + 加保存層），且相依（#3 的「過去情境」需 #4）。→ 先對齊
  方向（擬寫 DEC 補遺 / 設計 note）再分階段 build；#4 為基礎、#3 為進入流程。

## code review 結果（code-reviewer subagent）

- **Approve — 0 must-fix / 4 should-fix / 4 nice-to-have**。reviewer 另寫反演腳本重演修復前行為，
  實證舊碼同一組步驟會讓機組回到 PRODUCING(6)，修復後三測試 PRODUCING 從未出現。
- **已收的 4 個 should-fix**（同 PR 第二 commit）：
  1. `_step` helper 補回傳型別 `-> List[Dict]`（CLAUDE.md §7）。
  2. `_inject_and_trip` 前置 assert 從 `== EMERGENCY_STOP` 放寬為 `!= PRODUCING`——tripped 後機組
     在 7↔3 擺盪，綁死單一 state 碼日後調 severity_rate/dt/dwell 會無端斷裂（改守真正不變量）。
  3. `cmd_reset` docstring 精確化——列出實際歸零的電氣/機械暫態（非只「控制狀態 + fault_modifiers」）。
  4. ISSUES.md / STATUS.yaml 同步（本次補上 WMOM-20260719-01 done + 統計 +1）。
- nice-to-have（執行緒鎖、fault_modifiers 死欄位）屬既有現況、範圍外，未動。

## 卡在哪 / 下次怎麼接手

- **PR #137**：draft + 暫掛 `hold`（待 review）→ review Approve + should-fix 收完 → **移除 hold**
  讓 flywheel CI 綠自動合。
- **#3/#4 待使用者拍板方向**後開 issue/DEC 分階段實作（建議順序：#4 情境保存 → #3 啟動 gate）。
