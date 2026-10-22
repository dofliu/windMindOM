# 2026-10-22 — WMOM-20261022-01：EPIC-DS 全面程式碼檢查 + 功能驗證

> Session 類型：review＋實作
> Session 長度：長
> 主導：Claude（劉老師要求「先做一次程式碼檢查、功能測試驗證」，四個設計問題由劉老師決定）
> 結果：WMOM-20261022-01 done；新開 WMOM-20261022-02（手冊保真度，排在 -08 其餘子項前）

---

## 1. Session 目標

-08-a 合併後、做 -08 其餘子項前，劉老師要求對 EPIC-DS 至今的程式做一次整體程式碼檢查與功能測試驗證。各 issue 合併前都個別 review 過，所以這次的重點是：

- 跨模組、跨 issue 才看得出來的問題；
- 文件（合約、README）與程式不一致；
- 用真伺服器把三條管道（① 資料包 ② WS 回放 ③ OPC UA）一路跑到評分。

## 2. 實際完成

### 2.1 檢查方式

| 項目 | 做法 | 結果 |
|---|---|---|
| code review | 三個 code-reviewer 平行：模擬器 / PLC / 故障情境、伺服器 / 資料包 / 回放、OPC UA / starter kit / 合約；每項要有重現路徑，多數寫腳本證實 | 🔴 2、🟡 18、🟢 14 |
| 完整 backend | 合併後的 main → 修正後 | 1949 → 1963 passed / 7 skipped / 1 xfailed（+14 新測試） |
| frontend | tsc、vitest、vite build | 通過、1513 passed、成功 |
| ruff | 只看 E9 / F / B | EPIC-DS 程式沒有新問題（剩下的是既有程式與 FastAPI 慣用寫法） |
| mypy | EPIC-DS 8 個模組 | 12 → 0（只改型別標註） |
| 端到端 | 真伺服器、隔離 DB、`WMOM_OPCUA_ENABLE` + `WMOM_AUTH_ENFORCE` | 47 項全過（見 §2.4） |

### 2.2 自己發現的問題

- **產生情境卡住整台伺服器**：`generate-bulk` 是 `async def` 卻同步跑物理模擬。實測 2 h 情境 31.5 s 內，查狀態的請求等了 31.4 s，正在播的正式評測回放 31.6 s 沒有任何訊息（`scratchpad/loop_block.py`）。
- **`wind_profile` 只是標籤**：API 直接帶 `wind_profile` 卻沒先套用風況時，資料包的風況與資料不符。

### 2.3 修正

**直接修（不需決策）**：
- 🔴 非 Z72 機型（前端可選的 SG 8MW）健康機組約 5 分鐘就被 Z72 的溫度保護跳機並 `restart_blocked`：熱模型的發熱用絕對 kW、熱阻與 PLC 設定值是 Z72 的。改為以額定功率正規化（電氣發熱與附加熱 × Z72 額定 ÷ 本機額定）；Z72 係數 1.0，健康 + 3 種故障的讀值與 PLC 事件與 main 逐位元相同（`scratchpad/bitcmp.py`）。
- Live 殘留的 PLC 狀態漏進命名情境：情境開頭出現沒有 `trip` 的 `trip_cleared` / `operator_reset`，答案卻寫健康。`WindFarmSimulator.start_clean_scenario()` 重設帶殘留狀態的機組；乾淨的機組不動（範例資料包重建後只有時間戳變）。
- `reset()` 後每小時重啟上限一直成立（模擬時間歸零、舊時間戳沒清）。
- 正式評測的 WS `?stream=false` 可在 OPC UA server 開播前搶先開始計時 → 4412。
- `wind_profile` 非字串：資料包 500，回放在開始計時後才出錯，用掉單次評測 → 生成時驗證型別、讀取端容錯、開播訊息的內容在開始計時前先算；資料包 / 回放輸出生成時實際套用的風況（`wind_profile_applied`）。
- 情境 / 回放路由的 id 與 `limit` 範圍檢查（超出 SQLite 整數會 500、負數 limit 等於不限）；`history?observable_only=true` 改用資料包事件格式；CLI 評分端版改放 `<pack_id>-full/`（原本與盲測版共用目錄）；正式評測進行中不能切換風場。
- OPC UA 回放的回放狀態檢查失敗會中斷播出 → 只記錄、下一輪再查；`Z72OpcUaServer` 預設只聽 127.0.0.1。
- starter kit：`stream_client` 在判斷途中被關閉 / 網址錯 / Ctrl+C 不再是 traceback；`opcua_client` 看得到晚出現的機組；JSONL 只以 `\n` 分行（U+2028 是合法字元，`splitlines` 會切成兩行）。
- 文件：合約 §3.5 tag 數、§13.2 `Status` 的 `missing`、4410 的寬限期、predictions 建議 `-o`；README 範例清單。

**劉老師決定（DEC-20261022-05）**：

| 問題 | 決定 | 實作 |
|---|---|---|
| 盲測靠登入保護但預設沒開 | 正式評測強制開登入 | REST 409、`replay_runs.py` / `opcua_server.py` 結束碼 1；練習回放帶警告 |
| 產生情境卡住伺服器 | 移到背景執行緒 | `asyncio.to_thread`；`server/batch_state.py` 同時一個批次；批次期間改模擬器的 16 個路由 409（測試鎖清單） |
| 多組同時正式評測會落後 | 建立時檢查總速率 | 未結束的正式評測加總 ≤ 1000 筆 / 秒，超過 409 並列出佔用的回放 |
| 手冊保真度 | 開新 issue 下一步做 | WMOM-20261022-02 |

### 2.4 端到端驗證（最終版，47 項全過）

- 即時 OPC UA：只聽 127.0.0.1、有資料、唯讀、拒絕帳密登入。
- 批次情境（2.5 h、14 台：WT002 主軸承磨耗、WT004 主軸承溫度量測飄移、WT003 偏航壓力感測器斷線）：生成期間 OPC UA 為 idle、查狀態最慢 0.10 s（原本 31.4 s）、改模擬器的請求 409。
- 標準答案：WT002 `real_fault`、WT004 / WT003 `sensor_fault`；答案卷與評分端資料包未登入 401、員工 403。
- 強制登入下，未登入拿不到盲測版資料包 / 情境清單 / 情境詳情 / history。
- 資料包：sha256 與合約版本、無洩漏、104 欄（102 tag）、CLI 與 HTTP 的資料檔相同。
- WS 練習回放：12600 筆讀值、43 筆事件、224 窗統計與資料包逐筆相同；回放 token 拿不到答案 / 清單；4401 / check / 4403。
- 正式評測：同情境已有練習 409、超過速度上限 422、OPC UA 回放讀值與資料包逐位元相同（4896 格）、`--exit-when-finished`、寬限期內 1000 / 之後 4410。
- 三條管道的基準助手評分相同：3 個 case 全偵測、元件 100 %、類別 67 %（讀值像真故障的漂移被判成真故障——正是這類情境要考的）。
- 刪除情境要 admin（主管 403）、收過預測預設 409。

## 3. 產出清單

### 新增檔案

- `modules/monitoring/server/batch_state.py`
- `work-logs/2026-10/2026-10-22-epic-ds-verification.md`

### 修改檔案

- 模擬器：`simulator/engine.py`（`start_clean_scenario`）、`physics/thermal_model.py`（`heat_scale`）、`physics/turbine_physics.py`（`thermal_heat_scale`、`reset()` 清啟動時間戳）
- 伺服器：`server/replay.py`（正式評測總速率、`EVALUATION_NEEDS_AUTH`、`scenario_wind_profile`、`running_evaluations`）、`server/scenario_pack.py`、`server/storage.py`、`server/opcua_server.py`、`routers/config.py`（背景執行緒、`wind_profile_applied`）、`routers/faults.py`（背景執行緒）、`routers/replay.py`（強制登入、4412、id 範圍）、`routers/scenarios.py`（id / limit、`observable_only`）、`routers/farms.py`（評測中不切換）、`routers/control.py` / `source.py`（批次守門）
- CLI：`tools/export_scenario_pack.py`、`tools/replay_runs.py`、`tools/opcua_server.py`
- starter kit：`stream_client.py`、`opcua_client.py`、`score.py`、`pack_reader.py`、`baseline_assistant.py`、`README.md`
- 測試：`test_replay.py`、`test_opcua_server.py`、`test_scenario_endpoints.py`、`test_scenario_pack.py`、`test_monitoring_routers_auth.py`、`test_plc_integration.py`、`test_fault_ground_truth.py`、`test_reset_keeps_fault.py`、`tests/test_rag_starter_kit.py`
- 文件：合約、`docs/API_GUIDE.md`、EPIC-DS 設計文件 §6.14、`decision_log.md`、`ISSUES.md`、`STATUS.yaml`、`TODO.md`、`CLAUDE.md`

### 動了狀態的 issue

- WMOM-20261022-01：（新開）→ done
- WMOM-20261022-02：新開 open

### 寫進 decision_log 的決策

- DEC-20261022-05：正式評測要伺服器強制登入、批次生成移到背景執行緒、正式評測總速率上限、手冊保真度另開 issue

## 4. 下次怎麼接手

1. **WMOM-20261022-02 手冊保真度**（劉老師排在 -08 前）：Appendix D 延遲 / 範圍、A039、`yaw_sensor_drift` 不跳 233；改完重建範例資料包、重量設計文件 §6.3 的時間點。review 的重現腳本在 session scratchpad `review_sim/`（t17.py yaw drift、Appendix D 對照見手冊 p.131-135 / `chunks.jsonl` row 506-530）。
2. **-08 其餘子項**：先問劉老師挑；做多重故障時先定同機組多 case 的評分規則（review 證實「每個元件猜一遍」可拿 (k−1)/k 元件正確率）。
3. Nice-to-have 清單見設計文件 §6.14「留給後續」3。

## 5. 學到的事

- 「各 issue 都 review 過」不等於整體沒問題：這次最嚴重的兩個（盲測靠預設沒開的登入、批次卡住 event loop）都是跨 issue 的組合效果——各自合理，合在一起才出事。
- 端到端要用部署時的設定跑（強制登入、OPC UA 開啟）：預設設定下會漏掉「刪除情境要 admin」這種只在強制登入時才出現的行為。
- 共用的 module-scope fixture 會讓「看狀態」的測試受前面測試影響（CI 跑整檔才失敗）：檢查全域狀態的測試用 DB 複本或先清掉殘留。
