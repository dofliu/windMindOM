# 2026-10-21 — WMOM-20261021-11：風場時區（日夜 / 季節循環改用風場當地時刻）

> Session 類型：實作
> Session 長度：短
> 主導：Claude（劉老師指示「繼續做 -11 風場時區」）
> 結果：WMOM-20261021-11 done

---

## 1. Session 目標

-03-c 起時間戳一律 UTC，但 `wind_model.py` 的日夜 / 季節循環仍以「伺服器本地時區」取 hour / month：同一情境在 UTC 的 CI 與 UTC+8 的開發機上相位差 8 小時，資料包（-05）不可重現（-03-c code review 建議）。改為風場層級的時區設定。

## 2. 實際完成

### 2.1 盤點

- 風場設定（`FarmConfig`）原本沒有時區；broker 建立 `WindFarmSimulator` 時也不帶任何風場資訊（切換風場只套用 `turbine_spec`）。
- `to_local_naive` 只有 `wind_model.py` 用（6 個讀 hour / month 的 getter）。
- 時區資料：本機有系統 tz 資料庫；workflow 模組早已用 `ZoneInfo("Asia/Taipei")`，沿用 `zoneinfo`，不新增依賴。

### 2.2 實作

- `simulator/time_utils.py`：`DEFAULT_SITE_TIMEZONE = "Asia/Taipei"`、`site_timezone(name)`（無效名稱 → `ValueError`）、`to_site_naive(ts, tz)` 取代 `to_local_naive`。naive 輸入視為已是風場牆鐘時間（舊呼叫端與測試以牆鐘時間呼叫）——既有測試因此一個都不用改。
- `wind_model.py`：`WindEnvironmentModel(site_timezone_name=...)`、`set_site_timezone`；`WindFarmSimulator(site_timezone=...)`。
- `farm_registry.py`：`FarmConfig.timezone`、`farms.db` 以 ALTER 補欄（既有風場取預設值）、`create_farm` / `update_farm` 驗證（不匯入 `time_utils`——farm_registry 會被 cost / shared 以套件模式匯入，另寫 `_validate_timezone`）。
- `routers/farms.py`：建立 / 更新接受 `timezone`，`ValueError` → 400。
- `data_broker.py`：`_active_farm_timezone()`，建立模擬器時帶入。
- `routers/config.py`：情境 session 的 `config.site_timezone`。

### 2.3 驗證

- `test_farm_timezone.py`（8）：
  - 同一組 UTC 時刻在 UTC / Asia/Taipei / America/New_York 程序時區下，一天的風況逐位元相同。
  - 模擬器 60 步的全部 SCADA tag 在 UTC 與 Asia/Taipei 下逐位元相同。
  - 時區會移動日夜相位；無效時區被拒。
  - 風場預設值、驗證、更新；舊 `farms.db` 補欄。
  - API 400；broker 以風場時區建立模擬器。
- `test_scenario_endpoints.py`：情境 config 有 `site_timezone`。
- -03-c 的風況測試改名為 `test_wind_model_diurnal_cycle_uses_site_time`，不再需要 Asia/Taipei 程序時區 fixture。
- mutation：改回伺服器本地換算（8 項失敗）/ broker 不帶風場時區 / 建立不驗證 / 情境不記時區，各有測試失敗。
- 既有 monitoring + tests/ 全過；`examples/data_quality_analysis.py` 20 通過 / 0 待改善。
- backend 全套：1543 → **1551 passed** / 7 skipped / 1 xfailed。

### 2.4 行為改變

伺服器時區不是 Asia/Taipei 的機器（UTC 的 CI、Docker）日夜相位比改動前移動 +8 小時；台北時區的開發機不變。健康機組物理輸出（`TurbinePhysicsModel` 直接驅動、不經風況模型）不受影響。

### 2.5 卡住或延後的事

- 前端建立風場表單沒有時區欄位（API 預設 Asia/Taipei；有非台灣風場需求時再加）。
- Windows 上 `zoneinfo` 需要 `tzdata` 套件（workflow 模組已依賴，既有環境可用；未新增 requirements）。

## 3. 產出清單

### 新增檔案

- `modules/monitoring/tests/test_farm_timezone.py`（8）
- 本 work-log

### 修改檔案

- `modules/monitoring/simulator/time_utils.py`、`simulator/engine.py`、`wind_model.py`
- `modules/monitoring/server/farm_registry.py`、`data_broker.py`、`routers/farms.py`、`routers/config.py`
- `modules/monitoring/tests/test_utc_timestamps.py`、`test_scenario_endpoints.py`
- 文件：`docs/product/EPIC-DS_realistic_data_source.md`（§6.4 標記已解、新增 §6.6）、`docs/physics_model_status.md`（1.7）、`docs/API_GUIDE.md`、`ISSUES.md`、`STATUS.yaml`、`CLAUDE.md`（時間戳守則）、`TODO.md`

### 動了狀態的 issue

- WMOM-20261021-11：open → done

## 4. 下次怎麼接手

**WMOM-20261021-04**：標準答案 + 情境事件。ground truth 可直接從情境 session config 取 `site_timezone`；PLC 事件時間戳換算見 broker `_plc_event_timestamp`。
