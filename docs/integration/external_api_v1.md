# windMindOM 對外唯讀 API v1.2

> **版本**：1.2（2026-11-26；初版 1.0 是 WMOM-20261125-02，EPIC-SF 第 1 項，[DEC-20261126-01](../product/decision_log.md)；1.1 加 `raw_retention_days`、歷史延伸到半年，WMOM-20261125-03-c，[DEC-20261126-03](../product/decision_log.md)；1.2 加工單與出發前準備卡兩個端點，WMOM-20261125-05，[DEC-20261126-05](../product/decision_log.md)）
> **對象**：要像外部監控一樣，向持續運轉的仿真風場取 SCADA 資料與警報的外部系統——例如 RAG 運維助理。
> **資料格式**跟著 [資料介面合約 v1.7](rag_assistant_data_contract_v1.md)：讀值欄位、事件、10 分鐘統計與盲測版資料包、回放訊息是同一套。本文只規定端點、金鑰與翻頁方式。

---

## 1. 這個 API 給什麼、不給什麼

給的是真實 SCADA 也看得到的東西：

- 每台機組的讀值（105 個 tag，同資料包的欄位）。
- 警報、跳機與運轉狀態轉換的事件（真實 Z72 警報碼）。
- 目前成立的警報與鎖存中的跳機碼。
- tag 字典、Z72 警報目錄、風場的固定資訊。
- 工單的結構化欄位（編號、機組、類型、狀態、優先級、警報碼、各階段的時間），以及出發前準備卡：故障維修工單是故障出勤卡、定檢 / 預防保養工單是例行巡檢卡（1.2 起，§3.9、§3.10）。

不給的：

- 故障注入、故障種類與嚴重度、情境名稱、風況設定——這些是答案。
- 模擬器內部量（疲勞累積損傷、齒面磨耗指數等，合約 §3 的 `MODEL_INTERNAL_TAGS`）。
- 凍結情境（題庫）的資料。那些以資料包、WebSocket 回放、OPC UA 交付（合約 §3、§12、§13）。
- 工單的標題、說明、施工摘要這些自由文字；完工時修掉了哪些故障；準備卡的評分與評分用的答案。
- 任何寫入或控制。全部端點都是 `GET`。

## 2. 金鑰

外部系統不開帳號、不登入。管理者發一把長效金鑰，外部系統在每個請求帶上：

```
X-API-Key: wmk_...
```

- 金鑰只在建立時顯示一次，伺服器只存 sha256。
- 金鑰只能用在 `/api/ext/v1`。它不是角色，其他端點不認它。
- 沒帶、無效或已撤銷：`401`。這個檢查不受 `WMOM_AUTH_ENFORCE` 與 dev mode 影響。
- 伺服器重啟後金鑰仍有效（存在 auth DB，`WMOM_AUTH_DB_URL`）。

發金鑰、列出、撤銷，兩種方式擇一：

```bash
# 在伺服器那台機器、伺服器的啟動目錄下
python tools/external_api_keys.py create rag-assistant
python tools/external_api_keys.py list
python tools/external_api_keys.py revoke <id>
```

```
POST   /api/auth/api-keys        {"name": "rag-assistant"}   → 回應的 key 欄位只出現這一次
GET    /api/auth/api-keys
DELETE /api/auth/api-keys/{id}
```

管理端點只有系統管理員（admin）能用。例外：伺服器開 dev mode（`WMOM_DEV_MODE=true`）時，沒登入的請求會被當成管理員，任何連得到伺服器的人都能發金鑰——這與使用者管理端點相同。dev mode 只給單機開發用，不要拿來做盲測。

### 盲測的前提

**伺服器要開 `WMOM_AUTH_ENFORCE=true`。** 沒開的時候，`/api/faults/active`、`/api/export/events` 這些端點本來就不用登入，拿到金鑰的外部系統直接去讀就看得到故障注入資訊。`GET /status` 的 `other_endpoints_require_login` 會回報這個設定；CLI 在沒開的環境發金鑰時也會提醒。

## 3. 端點

基底路徑 `/api/ext/v1`。時間一律 UTC、`Z` 結尾（合約 §5）。查詢參數的時間要帶時區，例 `2026-11-26T00:00:00Z` 或 `2026-11-26T08:00:00+08:00`；沒帶時區回 `422`。

| 端點 | 用途 |
|---|---|
| `GET /status` | 伺服器與即時模擬的狀態 |
| `GET /farm` | 機型、機組、取樣週期、10 分鐘統計的慣例 |
| `GET /tags` | tag 字典（同資料包 `tag_dictionary.json`） |
| `GET /alarm-catalog` | Z72 警報目錄（同資料包 `alarm_catalog.json`） |
| `GET /readings/latest` | 每台機組最新一筆讀值 |
| `GET /readings` | 一台機組的歷史讀值 |
| `GET /stats-10min` | 一台機組的 10 分鐘統計 |
| `GET /events` | 警報、跳機與運轉狀態轉換 |
| `GET /alarms/active` | 每台機組目前成立的警報與跳機碼 |
| `GET /work-orders` | 風場的工單（1.2 起） |
| `GET /work-orders/{business_key}/briefing` | 一張故障維修工單的出發前準備卡（1.2 起） |

### 3.1 `GET /status`

```json
{
  "api_version": "1.2",
  "contract_version": "1.7",
  "server_time": "2026-11-25T17:29:02.606956Z",
  "live": true,
  "live_epoch": 0,
  "time_scale": 1.0,
  "sample_period_s": 10.0,
  "raw_retention_days": 183,
  "latest_reading_ts": "2026-11-25T17:29:00.000000Z",
  "other_endpoints_require_login": true
}
```

- `live`：即時模擬是否在跑。伺服器剛啟動、還沒有人選定資料來源，或管理端暫停即時模擬時是 `false`。
- `live_epoch`：即時資料的連續段編號。風場狀態從頭開始時才會變；數字變了表示即時資料在那裡不連續（§5）。重啟續跑、產生情境都不會改變它。
- `sample_period_s`：讀值寫進歷史的間隔（模擬時間的秒數），固定 10 秒、對齊整點，不隨 `time_scale` 改變。
- `raw_retention_days`（1.1 起）：10 秒原始讀值留幾天，循環保存。算的是資料自己的時間（從最新一筆讀值往回），不是實際時間。比這更早的 `/readings`、`/stats-10min` 查不到；事件不受這個限制。

### 3.2 `GET /farm`

機型、機組清單、風場時區、額定功率、取樣週期、`stats_window_s`、`stats_convention`。欄位與資料包 `manifest.json` 的同名欄位相同（合約 §3）。不含風場名稱。

### 3.3 `GET /readings/latest`

```json
{"readings": [
  {"type": "reading", "ts": "2026-11-25T17:29:12.275456Z", "turbine_id": "WT001",
   "values": {"Z72PLC__UI_Loc_WTUR_State_TurSt": 4, "Z72PLC__UI_Loc_WGEN_Analogue_GnSpd": 0.75, "...": "..."}}
]}
```

每台機組一筆，是最近一次寫進歷史的那一批（所以最多比現在舊一個取樣週期）。`values` 的鍵與型別同回放的 `reading` 訊息（合約 §12）。伺服器剛啟動、即時模擬還沒寫入第一批之前，`readings` 是空的（這時 `/readings` 仍查得到先前的歷史）。

### 3.4 `GET /readings`

| 參數 | 說明 |
|---|---|
| `turbine_id`（必填） | 機組 ID，例 `WT001` |
| `start` / `end` | 時間範圍 `[start, end)`；可只給一邊 |
| `after` | 游標，預設 0（從頭） |
| `limit` | 一頁幾筆，預設 500，最多 2000 |

回應 `{"readings": [...], "next_cursor": 15, "has_more": false}`，依寫入順序由舊到新。

### 3.5 `GET /events`

| 參數 | 說明 |
|---|---|
| `turbine_id` | 只取這台機組；不給＝全部 |
| `start` / `end` | 時間範圍 `[start, end)` |
| `after` | 游標，預設 0 |
| `limit` | 一頁幾筆，預設 500，最多 2000 |

回應 `{"events": [...], "next_cursor": 50, "has_more": false}`。每筆事件是 `{"type": "event", ...}` 加上合約 §4 的全部欄位：

```json
{"type": "event", "ts": "2026-11-25T17:29:36.360000Z", "turbine_id": "WT003", "event_type": "trip",
 "alarm_code": 242, "alarm_level": "T1", "alarm_text": "...", "event_id": "...", "plc_tag": "...",
 "from_state": null, "to_state": null, "from_state_name": null, "to_state_name": null, "stop_reason": null}
```

### 3.6 `GET /alarms/active`

```json
{"live": true, "turbines": [
  {"turbine_id": "WT003", "alarm": [], "trip1": [242], "trip2": []}
]}
```

每台機組三個清單：成立中的警報（A）、鎖存中的跳機（T1、T2），依成立順序。與 OPC UA 的 `ActiveAlarm` / `ActiveTrip1` / `ActiveTrip2` 是同一份（合約 §13）。即時模擬沒在跑時 `live` 為 `false`、`turbines` 為空。

### 3.7 `GET /stats-10min`

| 參數 | 說明 |
|---|---|
| `turbine_id`（必填） | 機組 ID |
| `start` / `end`（必填） | 時間範圍 `[start, end)`，一次最多 24 小時 |

回應 `{"stats": [...], "sample_period_s": 10.0}`。每筆同回放的 `stats` 訊息與資料包 `stats_10min.parquet`（合約 §3、§12）：窗對齊 UTC 的整 10 分鐘，類比量給 `_avg` / `_min` / `_max` / `_std`，離散量給 `_min` / `_max`。

- 只回完整落在 `[start, end)` 內、而且已經收齊的窗。「收齊」看的是資料，不是實際時間：這台機組最近一次寫進歷史的讀值，時間已經到了窗的結束時間或更晚。所以一個窗在結束後大約一個取樣週期才查得到，查到之後值不會再變。
- 統計是查詢當下由讀值算出來的，不是另外存的。用的是 `/readings` 給的同一批值（PLC 資料型別：REAL 是 32 位元浮點數），所以自己拿 `/readings` 的值重算會得到一樣的結果；同一個窗不論查幾次、資料是否已經搬到長期保存，值都相同。
- `sample_period_s` 是這段資料相鄰讀值間隔的中位數，用來判定 `is_partial`。取樣間隔固定之後它就是 10；2026-11-26 以前寫入的資料間隔約 10.15 秒。

### 3.8 `GET /tags`、`GET /alarm-catalog`

內容分別與資料包的 `tag_dictionary.json`、`alarm_catalog.json` 相同（合約 §3）。它們只在版本更新時改變，取一次存起來即可。

### 3.9 `GET /work-orders`（1.2 起）

風場的工單，依建立順序由舊到新。跳機（T1 / T2）或自動重啟被封鎖（A039）時伺服器會自動開一張故障維修工單；管理端也會手動開單、排定檢。

| 參數 | 說明 |
|---|---|
| `turbine_id` | 只取這台機組；不給＝全部 |
| `open_only` | `true`＝只列未結案的；預設 `false` |
| `after` | 游標：上一次回應的 `next_cursor`；不給＝從最舊的開始 |
| `limit` | 一頁幾筆，預設 200，最多 500 |

```json
{"work_orders": [
  {"business_key": "WO-LEGAC-202611-001", "turbine_id": "WT005", "type": "corrective", "status": "draft",
   "priority": "normal", "source_alarm_code": 240,
   "created_at": "2026-11-25T21:12:50.267391Z", "dispatched_at": null, "started_at": null,
   "finished_at": null, "closed_at": null, "has_briefing": true}
 ],
 "next_cursor": "2026-11-25T21:12:50.267391Z~WO-LEGAC-202611-001", "has_more": false}
```

- `type`：`corrective`（故障維修）、`inspection`（定檢）、`preventive`（預防保養）、`commissioning`（試運轉）。
- `status`：`draft`（已開單）→ `dispatched`（已派工）→ `in_progress`（施工中，機組在維修模式）→ `awaiting_signoff`（現場完工、等簽核）→ `closed`；另有 `cancelled`、`reopened`。
- `priority`：`low` / `normal` / `high` / `critical`。
- `source_alarm_code`：開單依據的事件碼（整數）；手動開的單沒填、或填的不是數字時是 `null`。
- `has_briefing`：這張工單有沒有出發前準備卡（§3.10）。
- **工單的時間是實際時間，不是風場時鐘。** 讀值、事件、準備卡的資料截止點用風場時鐘（§5）；時間倍率大於 1 之後兩者不一致，不要拿 `created_at` 去對事件的時間，要對就用準備卡的 `data_cutoff`。
- 只列對得到機組的工單；`turbine_id` 一律是機組 ID（`WT001` 這種），不是畫面上的名稱。
- `business_key` 的第二段是風場代號的前五個字（管理端取的代號，不是風場名稱）。
- `has_briefing` 在工單剛建立時可能還是 `false`：卡片要等下一批讀值寫進歷史才產生，最多約一個取樣週期（10 秒）。這時 §3.10 回 `404`，稍後再問。
- 同一張工單的 `status` 與各階段的時間之後會變。游標只會給「還沒給過的工單」，不會回頭通知狀態改變；要追狀態就定期用 `open_only=true` 重新取未結案的清單。
- 兩張工單在同一毫秒內由不同來源建立時（自動開單和管理端手動開單剛好撞在一起），較早的那張可能較晚寫入；輪詢剛好落在中間就會漏掉它。很少見，但要完全不漏，就用上一點的未結案清單定期對一次。

### 3.10 `GET /work-orders/{business_key}/briefing`（1.2 起）

一張工單的**出發前準備卡**：伺服器在工單建立當下，用規則把看得到的證據整理成一張卡。它只用這個 API 本來就給得出去的資料（讀值、事件、工單的結構化欄位、警報目錄），**不判定根因**。外部助理可以拿同一批資料做自己的摘要，再和這張卡比較。

卡片有兩種（`card.kind`）：故障維修工單是**故障出勤卡**（`fault_dispatch`，下面先說明）；定檢 / 預防保養工單是**例行巡檢卡**（`routine_inspection`，卡片 1.2 起，見本節最後）。沒有卡片回 `404`：試運轉工單、對不到機組的工單、工單建立時即時模擬沒在跑。卡片存了就不會變。

```json
{"business_key": "WO-LEGAC-202611-001", "turbine_id": "WT005", "data_cutoff": "2026-11-25T22:30:17.000000Z",
 "card": {
  "card_version": "1.2", "kind": "fault_dispatch",
  "work_order": {"business_key": "WO-LEGAC-202611-001", "turbine_id": "WT005", "type": "corrective",
                 "priority": "normal", "source_alarm_code": 240},
  "data_cutoff": "2026-11-25T22:30:17.000000Z", "generated_late": false,
  "event": {"ts": "2026-11-25T22:30:17.000000Z", "code": 240, "level": "T1",
            "text": "Bearing 1 temperature very high", "event_id": "T_240", "event_type": "trip",
            "turbine_state": 6, "turbine_state_ts": "2026-11-25T22:30:10.000000Z"},
  "recent_events": {
   "window": {"start": "2026-11-18T22:30:17.000000Z", "end": "2026-11-25T22:30:17.000000Z"},
   "same_code": {"count": 1, "first_ts": "...", "last_ts": "...", "recent": ["2026-11-25T22:30:17.000000Z"]},
   "other_codes": [{"code": 262, "level": "A", "text": "Main bearing 1 temperature high", "count": 1,
                    "last_ts": "2026-11-25T22:27:10.000000Z"}],
   "farm_same_code": {"window_minutes": 10, "turbines": []},
   "source": "..."},
  "signals": {
   "window": {"start": "2026-11-25T21:30:17.000000Z", "end": "2026-11-25T22:30:17.000000Z"},
   "recent_window": {"start": "2026-11-25T22:20:17.000000Z", "end": "2026-11-25T22:30:17.000000Z"},
   "baseline_window": {"start": "2026-11-25T15:30:17.000000Z", "end": "2026-11-25T21:30:17.000000Z"},
   "samples": 360, "baseline_samples": 277, "peers": 13,
   "last_reading_ts": "2026-11-25T22:30:10.000000Z", "source": "...",
   "items": [
    {"name": "Z72PLC__UI_Loc_WGEN_Analogue_GnBrgTmp1", "label_zh": "發電機軸承溫度",
     "label_en": "Generator Bearing Temp", "unit": "°C", "role": "primary",
     "turbine_mean": 44.42, "farm_median": 29.93, "farm_min": 27.72, "farm_max": 32.27, "peer_count": 13,
     "deviation": "high", "recent_mean": 81.12, "last_value": 96.2, "recent_farm_median": 30.49,
     "baseline_mean": 28.48, "change_from_baseline": 15.94}
   ]},
  "past_work_orders": [],
  "manual": {"status": "ok", "code": 240, "level": "T1", "text": "Bearing 1 temperature very high",
             "cause": "Bearing temperature 1 is very high",
             "rectification": "Check lubrication main bearing. Check cooling fan.",
             "max_per_hour": 1, "manual_page": 110, "source": "Z72 User Manual Appendix C"},
  "inventory": {"status": "no_mapping", "note": "..."},
  "data_quality": {"flags": [], "degraded": false},
  "notes": ["..."]
 }}
```

（範例的數值四捨五入過；實際回應是完整的浮點數。）

| 區塊 | 內容 |
|---|---|
| `data_cutoff` | 資料截止點（風場時鐘）＝工單建立之後第一批寫進歷史的讀值的時間，所以最多比建單晚一個取樣週期（10 秒）；建單當下歷史已經涵蓋到現在時就是建單當下。卡上的每一項都只用這個時間以前（含）的資料。`generated_late` 為 `true` 表示卡片是事後補的，截止點是補的那一刻 |
| `event` | 開單依據的那筆事件（同 `/events` 的內容）。`turbine_state` 是截止點前最後一筆讀值的運轉狀態，`turbine_state_ts` 是那筆讀值的時間——讀值每 10 秒一筆，跳機當下產生的卡，這個狀態可能還是跳機前的 |
| `recent_events` | 截止點前 7 天：這台機組同一個碼出現幾次（`same_code`）、其他警報 / 跳機碼各幾次（`other_codes`，最多 10 種）、事件前後 10 分鐘同場還有哪些機組送出同一個碼（`farm_same_code`——整場一起跳通常是外部原因） |
| `signals` | 相關訊號的對照。`window`＝截止點前 1 小時、`recent_window`＝最後 10 分鐘、`baseline_window`＝再往前 6 小時。`peers`＝拿來比的機組數：同場其他機組裡，那 1 小時有一半以上時間在發電的 |
| `signals.items[]` | `role`：`primary`（PLC 判定這個碼時看的量測）、`related`（同一條判定邏輯的其他量測；`primary` 加 `related` 最多 8 個）、`context`（機艙風速、功率、轉速）。`turbine_mean` / `recent_mean`＝這台機組 1 小時 / 最後 10 分鐘的平均；`last_value`（卡片 1.1 起）＝截止點前最後一筆讀值，斷線、卡住這類突然的變化在平均裡看不出來；`farm_median`、`farm_min`、`farm_max`、`recent_farm_median`＝同場的對照；`baseline_mean`＝自己前 6 小時的平均；`deviation`＝`high` / `low` / `normal` / `unknown` |
| `past_work_orders` | 這張工單之前開的、同一台機組的工單（最多 10 張，新的在前；只有結構化欄位：`business_key`、`type`、`status`、`source_alarm_code`、`created_at`、`finished_at`） |
| `manual` | 警報目錄（Z72 手冊 Appendix C）對這個碼列的原因與處置，照引、不加判斷。`status`：`ok` / `no_alarm_code` / `not_in_catalog` |
| `inventory` | 目前固定是 `{"status": "no_mapping"}`：還沒有「警報碼 → 料件」的對應表，卡上不列料件 |
| `data_quality` | `flags` 不是空的時候 `degraded` 為 `true`，表示證據不完整，要保守判讀 |

`deviation` 的算法：這台機組的平均減同場中位數，除以同場的離散程度（1.4826 × 絕對中位差；至少取中位數的 2 % 與量測範圍的 0.5 %），絕對值 ≥ 3 算偏高或偏低。1 小時與最後 10 分鐘各算一次，任一個偏離就算偏離——最後才飆高的訊號在 1 小時平均裡會被稀釋。可比較的機組少於 3 台時給 `unknown`。

`data_quality.flags` 的值：

| 值 | 意思 |
|---|---|
| `no_alarm_code` | 工單沒有帶事件碼（手動開的單）：只列背景量測 |
| `no_event_found` | 工單帶了事件碼，但截止點前 7 天找不到這台機組的這筆事件 |
| `events_truncated` | 7 天內的事件太多，沒有掃完：次數可能少算 |
| `signals_unmapped` | 這個碼沒有對應的量測：只列背景量測 |
| `signal_data_missing` | 截止點前 1 小時這台機組沒有讀值 |
| `stale_data` | 最後一筆讀值比截止點早 5 分鐘以上 |
| `too_few_peers` | 可比較的機組少於 3 台：不做同場對照 |
| `no_baseline` | 前 6 小時沒有讀值：沒有自己的基準 |

`card_version` 管卡片的欄位：加欄位升次版本，改名或刪除升主版本。1.1（2026-11-26）：每個訊號加 `last_value`；資料截止點改為建單之後第一批讀值的時間，訊號的視窗含截止點那一筆。1.2（2026-11-27）：加例行巡檢卡；故障出勤卡的欄位沒有變。

#### 例行巡檢卡（`kind`＝`routine_inspection`，卡片 1.2 起）

定檢 / 預防保養工單的卡：一份固定的檢查清單（技師上塔的路線：塔底的變頻器與冷卻水、變壓器、電網 → 偏航 → 機艙的通風、發電機、主軸承、轉速量測 → 機艙頂的氣象感測器 → 輪轂與變槳 → 葉片），**依證據排順序**：有證據的項目往前（分數高的先），沒有證據的維持原訂順序；整張都沒有證據時順序完全不動。不刪項目，排在後面的照樣要檢查。

```json
{"card_version": "1.2", "kind": "routine_inspection",
 "work_order": {"business_key": "WO-LEGAC-202611-020", "turbine_id": "WT003", "type": "inspection",
                "priority": "normal", "source_alarm_code": null},
 "data_cutoff": "2026-11-27T10:00:10.000000Z", "generated_late": false,
 "checklist": {"order_changed": true, "items": [
   {"id": "transformer", "label_zh": "變壓器", "label_en": "Transformer", "default_position": 2, "position": 1,
    "attention": true, "score": 2,
    "evidence": [{"type": "signal", "name": "Z72PLC__UI_Loc_WGDC_Analogue_TrfCoreTmp", "label_zh": "...",
                  "label_en": "...", "unit": "°C", "deviation": "high", "turbine_mean": 66.1,
                  "recent_mean": 67.9, "farm_median": 34.2}],
    "signals": ["Z72PLC__UI_Loc_WGDC_Analogue_TrfCoreTmp"]},
   {"id": "converter_cooling", "label_zh": "變頻器與冷卻水系統", "...": "...", "default_position": 1,
    "position": 2, "attention": false, "score": 0, "evidence": [], "signals": ["..."]}
 ]},
 "recent_events": {"window": {"start": "...", "end": "..."},
                   "by_code": [{"code": 264, "level": "A", "text": "...", "event_type": "alarm_raised", "count": 3,
                                "first_ts": "...", "last_ts": "...", "checklist_item": "generator"}],
                   "source": "..."},
 "signals": {"window": {"...": "6 小時"}, "recent_window": {"...": "最後 1 小時"},
             "baseline_window": {"...": "7 天前同樣長的一段"}, "samples": 2160, "peers": 13,
             "items": [{"name": "...", "role": "related", "checklist_item": "transformer", "...": "同故障出勤卡"}]},
 "past_work_orders": [],
 "data_quality": {"flags": ["no_baseline"], "degraded": false},
 "notes": ["..."]}
```

| 區塊 | 內容 |
|---|---|
| `checklist.items[]` | 清單的每一項：`default_position`（原訂第幾）、`position`（卡上排第幾）、`attention`（有證據）、`score`（證據的分數）、`evidence`（證據）、`signals`（這一項看的量測）。`order_changed`＝有沒有任何一項換了位置 |
| `evidence[]` | `type`＝`events`：截止點前 30 天這台機組的警報 / 跳機，同一個碼一筆（`count` 次、`last_ts`）；`signal`：這一項的量測和同場其他發電中的機組比偏高 / 偏低（最近 6 小時，或最後 1 小時）；`open_work_order`：這台機組未結案、帶事件碼的故障維修工單。分數：跳機 3、未結案的故障維修工單 3、量測偏離 2、警報 1；同一個碼的次數最多算 3 次 |
| `recent_events.by_code` | 截止點前 30 天的警報 / 跳機，依碼與種類彙總；`checklist_item`＝屬於清單的哪一項（依 PLC 的判定邏輯：這個碼主要看的量測在哪一項；對不到為 `null`） |
| `signals` | 同故障出勤卡的訊號對照，但視窗是 6 小時（最後 1 小時另算），`baseline_window` 是 7 天前同樣長的一段；每個訊號多一個 `checklist_item`。這台機組在視窗裡發電的時間不到一半（`own_producing_fraction` < 0.5，停機或維修中）時，量測不當證據（停著的機組轉速、溫度本來就和發電中的不一樣） |
| 證據的來源 | 未結案的故障維修工單取這台機組**所有**未結案的（`past_work_orders` 只列最近 10 張）。卡片在工單建立時做好就不再更新：建單之後才發生的事件不會改變順序 |

例行巡檢卡的 `data_quality.flags`：`events_truncated`、`signal_data_missing`、`stale_data`、`too_few_peers` 的意思同上表；`own_not_producing`＝這台機組大半時間沒有發電，量測不當證據；`signals_truncated`＝讀值多到超過一次讀取的上限，平均與最後一筆可能不準；`no_evidence`＝沒有任何證據，順序維持原訂；`no_baseline`＝7 天前沒有讀值。最後兩個不算降級（`degraded` 不會因此變成 `true`）。

兩種卡的 `signals` 從 1.2 起都多兩個欄位：`own_producing_fraction`（這台機組在視窗裡發電的時間比例）、`truncated`（讀值有沒有讀滿一次讀取的上限）。

## 4. 翻頁與輪詢

`/readings` 與 `/events` 用游標往後走：

1. 第一次不帶 `after`（或帶 0）。
2. 之後每次帶上一次回應的 `next_cursor`。
3. `has_more` 為 `true` 就立刻再取；為 `false` 表示已經追到最新，等一個取樣週期再問。

沒有新資料時回空清單，`next_cursor` 不變。游標是不透明的整數，只保證往後走不重複、不遺漏；不要拿它推算時間或筆數。`/events` 在可觀測事件很稀疏時可能回空清單而 `has_more` 為 `true`，照樣用 `next_cursor` 接著取。

`/work-orders` 的用法相同，差別只有兩點：游標是不透明的**字串**（第一次不帶 `after`；還沒有任何工單時 `next_cursor` 是 `null`，下次照樣不帶），而且它只往後給新建立的工單，已經給過的工單狀態改變不會再出現（§3.9）。游標只含英數字與 `-`、`:`、`.`、`~`，可以直接放進網址。

```python
import json
import time
import urllib.request

BASE = "http://<server>:8100/api/ext/v1"
KEY = "wmk_..."  # 由管理者提供


def get(path: str) -> dict:
    request = urllib.request.Request(BASE + path, headers={"X-API-Key": KEY})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


catalog = {e["code"]: e for e in get("/alarm-catalog")["events"]}
cursor = 0
while True:
    page = get(f"/events?after={cursor}")
    for event in page["events"]:
        if event["alarm_code"] is not None:
            entry = catalog.get(event["alarm_code"], {})
            print(event["ts"], event["turbine_id"], event["event_type"], event["alarm_code"], entry.get("text"))
    cursor = page["next_cursor"]
    if not page["has_more"]:
        time.sleep(10)
```

## 5. 即時資料與資料包的差別

格式相同，但即時資料有幾件事要知道：

- **取樣間隔是模擬時間的 10 秒，對齊整點。** 讀值的時間戳落在 `…:00`、`…:10`、`…:20`，一個完整的 10 分鐘窗是 60 筆。風場剛啟動時的第一筆可能不在整點上。
- **時間戳是模擬時鐘，只往前走。** 平常它跟著實際時間。時間倍率大於 1 時它跑在實際時間前面，倍率調回 1 之後維持領先的量繼續走，不會跳回來。事件與讀值用同一個時鐘。
- **落後時會補跑。** 伺服器重啟、管理端產生情境、程序被暫停之後，風場從停下的地方全速補跑到現在，歷史是連續的；補跑期間 `latest_reading_ts` 會暫時落後。落後超過 6 小時就不補，直接跳到現在，中間留下缺口。
- **伺服器重啟後風場接著跑**——前提是伺服器開了 `WMOM_LIVE_RESUME=true`。重啟前鎖存的跳機仍在 `/alarms/active`，疲勞與結垢不歸零，`live_epoch` 不變。伺服器另外開 `WMOM_AUTOSTART_SOURCE=simulation` 的話，開機就啟動即時模擬，不必有人登入選來源。
- **`live_epoch` 變了表示風場狀態從頭開始。** 會這樣的情況：伺服器沒開 `WMOM_LIVE_RESUME`、模擬器程式更新過（舊的狀態存檔不相容）、機組數或風場時區改了、管理端選擇從頭開始，或狀態存檔讀不出來。這時前一段鎖存的跳機不會有對應的解除事件。
- **伺服器被強制關閉時，最後幾秒的操作可能要重做。** 狀態每 30 秒存一次，操作員動過風場（注入或清除故障、控制指令）之後會立刻再存；兩次存檔之間被強制關閉，重啟後從上一次存檔接著跑。已經寫進歷史的讀值與事件不會重複。
- **管理端產生情境（題庫）期間即時模擬暫停**（`live` 為 `false`）。結束後風場接著原本的狀態補跑，`live_epoch` 不變。
- **歷史留半年，循環保存。** 天數看 `/status` 的 `raw_retention_days`（預設 183；伺服器可以設定）。較舊的讀值在伺服器那邊搬到長期保存，對外沒有差別：同一個游標從最舊翻到最新，值與格式相同。超過保留期的讀值查不到；游標落在已經刪掉的範圍時，會從還留著的最舊一筆接著給。伺服器的長期保存暫時讀不到時，`/readings` 與 `/stats-10min` 回 `503`（稍後再試），不會回一份缺了舊資料的結果。
- **工單的時間是實際時間。** `/work-orders` 的 `created_at` 等欄位是伺服器的實際時間；讀值、事件與準備卡的 `data_cutoff` 是模擬時鐘。兩者在時間倍率調大過之後就不一致（§3.9）。
- **管理端產生情境期間開的工單沒有即時的準備卡。** 那段時間即時模擬暫停、沒有風場時鐘；結束後伺服器會替還沒完工的故障維修工單補一張，標 `generated_late`。
- **時間倍率很大時伺服器可能跟不上**（14 台機組實測約 75 倍），資料量也跟著放大：倍率 60 等於每個實際秒寫 6 批讀值。

## 6. 錯誤

| 狀態碼 | 情況 |
|---|---|
| `401` | 沒帶金鑰、金鑰無效或已撤銷。未驗證的請求一律先回這個，不檢查參數 |
| `403` | 金鑰的權限範圍不含這個端點 |
| `404` | `/work-orders/{business_key}/briefing`：這張工單沒有出發前準備卡（或沒有這張工單） |
| `422` | 參數錯誤：少必填參數、時間沒帶時區、格式不對或超出可表示的範圍、`end` 不晚於 `start`、`limit` 超出範圍、統計超過 24 小時、`after` 不是這個端點給的游標 |
| `503` | 長期保存的歷史讀值暫時讀不到（`/readings`、`/stats-10min`）：稍後再試 |

不存在的機組 ID 不算錯誤，回空清單。

## 7. 版本規則

- 本文的版本（`api_version`）管端點、參數與翻頁方式：加端點或加欄位升次版本；改名或刪除升主版本，路徑前綴跟著換（`/api/ext/v2`）。
- 資料格式的版本（`contract_version`）跟著資料介面合約，規則見合約 §2。

| 版本 | 日期 | 內容 |
|---|---|---|
| 1.0 | 2026-11-26 | 初版：金鑰、九個唯讀端點、游標翻頁。同日修訂 §5：取樣間隔固定 10 秒、模擬時鐘只往前走、重啟續跑、產生情境不再改變 `live_epoch`（WMOM-20261125-03-a / -b；端點與欄位沒有變） |
| 1.1 | 2026-11-26 | `/status` 加 `raw_retention_days`；原始讀值的歷史由 3 天延伸到半年（預設），`/readings` 與 `/stats-10min` 查得到的範圍跟著變長，端點與參數沒有變。`/stats-10min` 改由 PLC 資料型別的讀值計算（與 `/readings` 給的值相同），個別統計值的最後一位有效數字可能和 1.0 不同（WMOM-20261125-03-c） |
| 1.2 | 2026-11-26 | 加 `GET /work-orders`（工單的結構化欄位、字串游標）與 `GET /work-orders/{business_key}/briefing`（故障維修工單的出發前準備卡，`card_version` 1.0）。既有端點沒有變（WMOM-20261125-05） |
| 1.2（修訂） | 2026-11-27 | 定檢 / 預防保養工單也有出發前準備卡（例行巡檢卡，`card_version` 1.2，§3.10）；端點、參數與故障出勤卡的欄位沒有變（WMOM-20261126-05） |
