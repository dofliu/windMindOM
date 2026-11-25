# windMindOM 對外唯讀 API v1.0

> **版本**：1.0（2026-11-26，WMOM-20261125-02，EPIC-SF 第 1 項，[DEC-20261126-01](../product/decision_log.md)）
> **對象**：要像外部監控一樣，向持續運轉的仿真風場取 SCADA 資料與警報的外部系統——例如 RAG 運維助理。
> **資料格式**跟著 [資料介面合約 v1.7](rag_assistant_data_contract_v1.md)：讀值欄位、事件、10 分鐘統計與盲測版資料包、回放訊息是同一套。本文只規定端點、金鑰與翻頁方式。

---

## 1. 這個 API 給什麼、不給什麼

給的是真實 SCADA 也看得到的東西：

- 每台機組的讀值（105 個 tag，同資料包的欄位）。
- 警報、跳機與運轉狀態轉換的事件（真實 Z72 警報碼）。
- 目前成立的警報與鎖存中的跳機碼。
- tag 字典、Z72 警報目錄、風場的固定資訊。

不給的：

- 故障注入、故障種類與嚴重度、情境名稱、風況設定——這些是答案。
- 模擬器內部量（疲勞累積損傷、齒面磨耗指數等，合約 §3 的 `MODEL_INTERNAL_TAGS`）。
- 凍結情境（題庫）的資料。那些以資料包、WebSocket 回放、OPC UA 交付（合約 §3、§12、§13）。
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

### 3.1 `GET /status`

```json
{
  "api_version": "1.0",
  "contract_version": "1.7",
  "server_time": "2026-11-25T17:29:02.606956Z",
  "live": true,
  "live_epoch": 0,
  "time_scale": 1.0,
  "sample_period_s": 10.0,
  "latest_reading_ts": "2026-11-25T17:29:00.000000Z",
  "other_endpoints_require_login": true
}
```

- `live`：即時模擬是否在跑。伺服器剛啟動、還沒有人選定資料來源，或管理端暫停即時模擬時是 `false`。
- `live_epoch`：即時資料的連續段編號。風場狀態從頭開始時才會變；數字變了表示即時資料在那裡不連續（§5）。重啟續跑、產生情境都不會改變它。
- `sample_period_s`：讀值寫進歷史的間隔（模擬時間的秒數），固定 10 秒、對齊整點，不隨 `time_scale` 改變。

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
- 統計是查詢當下由讀值算出來的，不是另外存的。
- `sample_period_s` 是這段資料相鄰讀值間隔的中位數，用來判定 `is_partial`。取樣間隔固定之後它就是 10；2026-11-26 以前寫入的資料間隔約 10.15 秒。

### 3.8 `GET /tags`、`GET /alarm-catalog`

內容分別與資料包的 `tag_dictionary.json`、`alarm_catalog.json` 相同（合約 §3）。它們只在版本更新時改變，取一次存起來即可。

## 4. 翻頁與輪詢

`/readings` 與 `/events` 用游標往後走：

1. 第一次不帶 `after`（或帶 0）。
2. 之後每次帶上一次回應的 `next_cursor`。
3. `has_more` 為 `true` 就立刻再取；為 `false` 表示已經追到最新，等一個取樣週期再問。

沒有新資料時回空清單，`next_cursor` 不變。游標是不透明的整數，只保證往後走不重複、不遺漏；不要拿它推算時間或筆數。`/events` 在可觀測事件很稀疏時可能回空清單而 `has_more` 為 `true`，照樣用 `next_cursor` 接著取。

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
- **歷史只留最近幾天。** 原始讀值目前保留 3 天，更早的查不到。保留半年排在 WMOM-20261125-03 的下一步。
- **時間倍率很大時伺服器可能跟不上**（14 台機組實測約 75 倍），資料量也跟著放大：倍率 60 等於每個實際秒寫 6 批讀值。

## 6. 錯誤

| 狀態碼 | 情況 |
|---|---|
| `401` | 沒帶金鑰、金鑰無效或已撤銷。未驗證的請求一律先回這個，不檢查參數 |
| `403` | 金鑰的權限範圍不含這個端點 |
| `422` | 參數錯誤：少必填參數、時間沒帶時區、格式不對或超出可表示的範圍、`end` 不晚於 `start`、`limit` 超出範圍、統計超過 24 小時 |

不存在的機組 ID 不算錯誤，回空清單。

## 7. 版本規則

- 本文的版本（`api_version`）管端點、參數與翻頁方式：加端點或加欄位升次版本；改名或刪除升主版本，路徑前綴跟著換（`/api/ext/v2`）。
- 資料格式的版本（`contract_version`）跟著資料介面合約，規則見合約 §2。

| 版本 | 日期 | 內容 |
|---|---|---|
| 1.0 | 2026-11-26 | 初版：金鑰、九個唯讀端點、游標翻頁。同日修訂 §5：取樣間隔固定 10 秒、模擬時鐘只往前走、重啟續跑、產生情境不再改變 `live_epoch`（WMOM-20261125-03-a / -b；端點與欄位沒有變） |
