# 2026-07-19 — 情境保存/調閱（後端）｜DEC-20260718-01 #4

> Session 類型：Scenario 上線實測 follow-up（用戶選「先 #4 再 #3」）
> 產出：本 PR（#4 後端：scenario session 模型 + 隔離讀取 + /api/scenarios）
> 對應 issue：WMOM-20260719-02｜DEC-20260719-01

---

## 做了什麼

用戶回報「產生過的情境調不回來、融進歷史了」。把「情境」建模成一個以
`config_json.kind == "scenario"` 標記的**專屬、已結束 session**（沿用既有 `sessions` 表，
零 schema 遷移）：

1. **storage**：
   - `query_history(...)` 新增 optional `session_id` 過濾（情境隔離調閱的關鍵）。
   - 新增 `SCENARIO_KIND` / `_session_row_to_dict` / `update_session_config`（併入生成後統計）/
     `list_scenarios` / `get_scenario` / `delete_scenario`（連 turbine_data/1m/10m/snapshots 一起刪、
     只作用在情境 session）。`list/get` 用 `json_extract(config_json,'$.kind')`（SQLite JSON1，
     本機 3.45.1 驗證可用）。
2. **data_broker**：`get_history(...)` 透傳 `session_id`。
3. **config.py generate-bulk**：帶 `name` 時 → 開新情境 session、批次資料寫該 session_id、
   store_cb 順帶擷取模擬時間窗、生成後 `update_session_config`（total/injected/sim_start/sim_end）
   + `end_session`、回傳 `scenario_id`；不帶 `name` 沿用舊行為（寫 active session）。
4. **scenarios.py（新 router）**：`GET /api/scenarios`（list）、`GET /{id}`、
   `GET /{id}/turbines/{tid}/history`（session 隔離調閱 + 時間窗內事件）、`DELETE /{id}`（主管）。
   app.py 註冊。
5. **測試**：`test_scenario_persistence.py` 7 storage tests（建立/list/get/隔離/回填/刪除/不誤刪 Live）。
   monitoring 85 全綠。
6. **端到端 verify**（scratchpad 腳本，未進 repo）：真的跑 `generate_bulk` → 情境 session →
   `query_history(session_id)` 隔離（情境 18 筆、Live 0 筆漏）→ 情境 ended（active 仍是 Live）→
   delete 清列，全通過。

## 眉角 / 決策（詳見 DEC-20260719-01）

- **沿用 sessions 表存情境**（不另立 scenarios 表）：零遷移、複用清理/aggregation；代價是情境與
  Live 同表、靠 `config_json.kind` 區分。
- **events 靠時間窗關聯**（history_events 無 session_id）：省一次 schema 遷移；跨情境窗重疊時
  可能混入（低風險，日後可補 `history_events.session_id` 收斂）。
- **不帶 name 沿用舊行為**：保留 FaultInjectionPanel/快速批次「寫進 active session」用法，非破壞。
- **情境 session 生成後 end_session**：避免被 `get_active_session` 當成 Live。

## code review 結果（code-reviewer subagent）

- **Needs revision → 已收**：2 Must-fix + 6 Should-fix + 4 Nice-to-have，reviewer 以 repro script
  實證兩個 Must-fix。全數處理：
  - **Must-fix #1**：情境生成中途失敗會讓 scenario session 卡 `ended_at IS NULL` → 被
    `get_active_session` 誤認成 Live。修：generate-bulk 的生成段包 try/except，失敗也
    `update_session_config(status=error)` + `end_session` 再 raise。
  - **Must-fix #2**：`offset=0` 注入的故障事件時間戳早於首筆 reading 一個 `time_step` → 被自己情境
    的時間窗 `timestamp >= sim_start` 排除。修：`on_inject` 也把注入時間納入 `sim_window` 下界。
  - **Should-fix**：`get_active_session` 主動排除 kind==scenario（防禦，不依賴呼叫時機）；DELETE
    情境改 ADMIN（對齊 farms/config/modbus 破壞性端點）；scenario history docstring + 回傳
    `events_by_time_window` 旗標明示 events 非 session 隔離；generate-bulk docstring 補物理 state
    併發風險；**新增 `test_scenario_endpoints.py` 4 個 endpoint 層測試**（直呼 async endpoint，
    守住兩個 Must-fix）；強化 delete 測試驗證五張表全清。
  - **Nice-to-have**：補 4 張表的 `session_id` 索引；`_session_row_to_dict` 型別標註；
    delete_scenario / run_downsampling 補 landmine 註解（history_events 孤兒、1m/10m GROUP BY）。
- monitoring **89 全綠**（+4 endpoint tests）。

## 卡在哪 / 下次怎麼接手

- **本 PR（#4 後端）**：review 收完 → 移除 hold → flywheel CI 綠自動合。
- **接下來 #4 前端（PR B）**：ScenarioPage 加「情境命名」欄（生成時帶 `name`）+ 「過去情境」清單
  （打 `GET /api/scenarios`）+ 點選調閱（打 `/{id}/turbines/{tid}/history`，餵進趨勢/分析視圖）+
  刪除。API 契約見 `scenarios.py` 頂部註解。
- **再來 #3 啟動 gate**：`app.py` lifespan 不自動 `broker.start(SIMULATION)`；前端登入後出模式選擇頁
  （實接/模擬/產生情境/過去情境）。
