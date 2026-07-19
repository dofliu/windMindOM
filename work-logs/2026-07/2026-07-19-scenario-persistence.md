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

## 卡在哪 / 下次怎麼接手

- **本 PR（#4 後端）**：draft + `hold`（待 code review）→ 收 review → 移除 hold → flywheel 自動合。
- **接下來 #4 前端（PR B）**：ScenarioPage 加「情境命名」欄（生成時帶 `name`）+ 「過去情境」清單
  （打 `GET /api/scenarios`）+ 點選調閱（打 `/{id}/turbines/{tid}/history`，餵進趨勢/分析視圖）+
  刪除。API 契約見 `scenarios.py` 頂部註解。
- **再來 #3 啟動 gate**：`app.py` lifespan 不自動 `broker.start(SIMULATION)`；前端登入後出模式選擇頁
  （實接/模擬/產生情境/過去情境）。
