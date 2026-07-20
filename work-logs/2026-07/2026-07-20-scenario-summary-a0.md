# 2026-07-20 — 情境比較分析 A0：情境摘要端點｜WMOM-20260720-09

> Session 類型：DEC-20260720-02 的 A0（情境比較分析 epic 第一步；承 PR B #147 merged）
> 產出：`GET /api/scenarios/{id}/summary` — 單一情境的物理摘要（純讀取/聚合）
> 對應 issue：WMOM-20260720-09

---

## 背景

DEC-20260720-02 定情境比較分析 epic：A0 摘要 → A1 同情境內比較 → A2 跨情境（相對時間對齊）→ A3。
Explore 已確認**所有物理輸出已落地 `scada_json`**（累積損傷/DEL/RUL/齒面磨耗/彎矩/功率/狀態），
故此 epic 是純**讀取/聚合/對齊/UI**，不需重新落地。A0 是基礎：給定情境 id，回一份「每台機組 +
風場層」的摘要，讓前端能顯示情境總覽、並成為 A1/A2 比較的資料來源。

## 計畫（A0 scope）

- 後端 `GET /api/scenarios/{id}/summary`：讀該 session 的 `query_history`（session 隔離），逐筆掃
  `scada_json` 聚合出——
  - **每台機組**：總發電量（能量）、容量因數、max/mean 功率、最終累積損傷（末值）、最小 RUL、
    極限負載（瞬時彎矩 MAX）、DEL（末值/代表值）、故障事件數、運轉/故障/待機時數。
  - **風場層 rollup**：總能量、平均容量因數、最嚴重機組（min RUL / max 損傷）、總故障數。
- 聚合放 storage 層（可測、與端點解耦）；端點只組裝 + 權限。
- 測試：mutation-verified（塞已知 scada 序列 → 斷言聚合值；撤聚合邏輯必轉紅）。

## 做了什麼

**後端（storage 聚合 + endpoint，純讀取）**
- `storage.scenario_turbine_aggregates(session_id)`：單一 `GROUP BY turbine_id` 掃該 session 的
  `turbine_data`，用 SQLite `json_extract` **直接在 SQL 內**聚合 `scada_json` 的物理量（避免把長情境
  數十萬列載進 Python）：功率 `AVG`/`MAX`（`power_output` 欄位，MW）；累積損傷/生產時數末值＝`MAX`；
  RUL 末值＝`MIN`；極限負載＝彎矩 `MAX`；DEL＝`MAX`；生產步數＝`SUM(CASE tur_state=6)`。**刻意不用
  1m/10m 聚合表**（其 downsampling `GROUP BY` 不含 session_id、跨 session 混算）。
- `scenarios.py` `GET /{scenario_id}/summary`（`require_authenticated`，比照 list/get）：取情境 →
  聚合 → 換算每台機組（kW/能量/容量因數/可用率）+ 風場層 rollup。回傳 typed `ScenarioSummary`
  （Pydantic，含 OpenAPI schema）。
- **換算/rollup 抽成純函式**（`_build_turbine_summary`/`_build_farm_summary`/`_fault_counts_by_turbine`/
  `_scenario_rated_power_kw`）便於 mutation-verify，不經 DB/HTTP。
- **容量因數額定功率**：情境未存 `rated_power_kw` → 預設 Z72 2000 kW（可被 session 值覆蓋），回傳帶
  `ratedPowerKw` 讓假設透明。
- **故障事件數**走情境 sim 時間窗（`history_events` 無 session_id）→ 回傳 `eventsByTimeWindow` 旗標
  提醒可能混入時間窗重疊的其他情境（物理聚合走 session_id 隔離，不受影響）。

## 驗證

- **storage 聚合**（`test_scenario_persistence.py` +2）：塞已知物理序列（功率 1→2→3 MW、彎矩非單調
  500→700→600、累積量遞增、RUL 遞減、四部位偏移），斷言每欄精確聚合值（MAX/MIN/分組/column 對位）；
  unknown session → 空 list。
- **endpoint + 純函式**（`test_scenario_endpoints.py` +8）：generate_bulk 建真情境 → summary 結構/一致性；
  404；`_build_turbine_summary` 換算數學（×1000/能量/容量因數/可用率/worstDamage）；n=0 與缺物理鍵防護；
  `_build_farm_summary` rollup + 取最嚴重；`_fault_counts_by_turbine`；額定功率預設/覆蓋。
- **mutation-verified**：storage `MAX→MIN`（極限負載）、純函式 `×1000→×1`（功率換算）各自撤修即轉紅。
- monitoring **120→130**、repo e2e **151** passed、ruff 全綠。

## PR #148 review round-1（3 Must-fix + 6 Should-fix + 4 Nice-to-have）

reviewer 用**真 physics engine** 實測，抓到三個落在聚合核心的真 bug（RUL/DEL 語意 + 阻塞）：

- 🔴 **RUL 用 MIN 冒充末值錯**：`WLOD_RulHours` 是外推估計（`prod_h·(1-dmg)/dmg`），暖機回 sentinel
  `-1.0`、之後隨 prod_h **上升**（實測 3h 情境 97% 為上升 step）。`MIN` 會鎖在 -1.0 sentinel。
  **修**：改取每台機組**最後一列**（`ROW_NUMBER() OVER (PARTITION BY turbine_id ORDER BY timestamp
  DESC)`）真實值；sentinel(<0)→None。farm rollup 改用 rulHours 取 min。
- 🔴 **DEL 用 MAX 冒充末值錯**：`WLOD_Del*` 每 10 分鐘視窗**重算覆蓋**（非累積），MAX 取到「最差視窗」
  非情境結束值（實測 MAX 599 vs 末值 344）。**修**：同 RUL 取末列。
- 🔴 **async 端點內同步阻塞 SQLite**：長情境（上限 8760h × 多機組）掃描外插達 ~7 分鐘，會卡住整個
  event loop。**修**：聚合/事件計數/get_scenario 全丟 `asyncio.to_thread`。
- 🟡 **額定功率非 Z72 誤算**：情境從未存 rated_power_kw → 恆 fallback 2000；切 3MW/8MW 機型後容量因數
  可 >100%。**修**：`generate_bulk` 建情境時把機型 `spec.rated_power_kw` 釘進 session。
- 🟡 **`availability` 命名撞 reporting 模組**（其 = 1−downtime/total）→ 改名 `productionRate` + 註明。
- 🟡 **故障計數 LIMIT 5000 靜默截斷** → 改 storage SQL `COUNT ... GROUP BY`（無 LIMIT）。
- 🟡 **測試抓不到假設錯**（合成資料剛好落在 MAX/MIN 成立區）→ storage 測改用**非單調** RUL/DEL
  （末值≠MIN/MAX）+ sentinel→None 專測，deterministic 守住語意。
- 🟡 `_max_ignore_none` 補 docstring；🟡 `estop_steps` 算了沒回 → 加 `estopSteps` 欄位。
- 🟢 rounding 說明對齊；🟢 加 `status` 欄位（error 情境提示）。deferred（記 ISSUES）：TypedDict、
  情境凍結後 summary 快取。

**驗證**：final-row 選取以 `ORDER BY DESC→ASC` mutation 兩測轉紅（RUL 900→1000、sentinel None→500）；
monitoring 130→**131**、repo e2e **151**、ruff 綠。

## 卡在哪 / 下次怎麼接手

- 本 PR #148：draft + `hold`；round-1 已處理 → 待 review 覆核 → 移除 `hold` → 合。
- A0 是**後端 only**（資料基礎）；前端情境總覽/比較 UI 屬 A1。下一步 **A1 同情境內比較**（不同機組、
  有故障 vs 健康機組）——可直接吃本端點回傳。PR C（檢視情境把 app 掛上去）前仍需寫 broker 子設計。
