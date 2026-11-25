# 2026-11-26 — 對外唯讀 API 與外部系統金鑰（WMOM-20261125-02，EPIC-SF 第 1 項）

> Session 類型：實作
> Session 長度：長
> 主導：Claude（劉老師指示「架構圖可以定稿，開始第 1 項」）
> 結果：`/api/ext/v1` 九個唯讀端點與 API 金鑰完成；外部系統拿得到真實警報碼與讀值，拿不到故障注入資訊。真伺服器端到端檢查通過。

---

## 1. Session 目標

1. 研究架構圖定稿，收進 repo（WMOM-20261125-08，另一個 PR，已合併）。
2. WMOM-20261125-02：讓外部系統（劉老師的 RAG 運維助理）像外部監控一樣，向持續運轉的仿真風場取 SCADA 資料與警報；外部身分用長效 API 金鑰（劉老師 2026-11-25 確認）。

## 2. 實際完成

### 2.1 主要工作

- **API 金鑰**（`modules/auth/api_keys.py`）：`wmk_` 開頭、只在建立時顯示一次、DB 只存 sha256；`require_api_key` 一律強制（不看 `WMOM_AUTH_ENFORCE` 與 dev mode）。金鑰不是 RBAC 角色，其他端點不認它。存在 auth DB 的 `auth_api_keys` 表，dev mode 也用 SQL（重啟後金鑰要還能用）。
- **管理**：`POST / GET / DELETE /api/auth/api-keys`（只有 admin）；CLI `tools/external_api_keys.py create / list / revoke`。
- **對外端點**（`modules/monitoring/server/routers/external.py`，全部 `GET`）：`status`、`farm`、`tags`、`alarm-catalog`、`readings/latest`、`readings`、`stats-10min`、`events`、`alarms/active`。
  - 讀值欄位＝盲測版資料包的 105 個 tag；事件逐筆過 `is_observable_event` 再 `pack_event`；格式與回放訊息相同。
  - 只取 Live：`storage.live_readings` / `live_events` 排除情境 session。
  - 最新讀值取自最近一次寫進 storage 的那一批（`broker.latest_stored_readings()`），不讀 simulator 記憶體。
  - 目前成立的警報取自 PLC 的清單（與 OPC UA 同一份），即時模擬沒跑或批次期間不給。
  - `readings` / `events` 以游標（寫入順序）往後翻頁、輪詢。
  - 10 分鐘統計由讀值即時計算，一次最多 24 小時。
- **文件**：`docs/integration/external_api_v1.md`（端點、金鑰、翻頁、與資料包的差別、錯誤、版本規則）；DEC-20261126-01；資料介面合約與 `API_GUIDE.md` 加上指引；`CLAUDE.md` §10 加「對外 API 守則」。

### 2.2 驗證

- 新測試 76 項：`test_external_api.py` 51 項、`test_api_keys.py` 22 項、`test_external_api_keys_cli.py` 3 項。
- **變異檢查**（把防線逐一拿掉，確認測試會失敗）：拿掉可觀測事件過濾、讀值改給全部 tag、不排除情境 session、拿掉金鑰 dependency、最新讀值改讀 simulator 記憶體、即時警報不看批次狀態——六項都被測試抓到；code review 之後再加兩項（統計的窗結束改回看實際時間、不攔 `OverflowError`），也都被抓到。第一輪時「拿掉可觀測事件過濾」沒被抓到（SQL 預篩與 `pack_event` 已經擋掉測試裡的那些事件），補了一筆只有 `is_observable_event` 擋得住的事件後才抓到。
- **真伺服器端到端**（`run.py`、`WMOM_AUTH_ENFORCE=true`、14 台機組）：
  - CLI 發金鑰後伺服器不必重啟就認得；沒帶金鑰 401；金鑰打 `/api/faults/active`、`/api/export/events`、`/api/turbines`、`/api/scenarios`、`/api/auth/api-keys` 都是 401。
  - 以 admin 注入兩個故障（WT003 量測回路斷線、WT005 超速）。45 秒後外部金鑰看到 WT003 的 `trip1: [242]` 與對應的跳機事件；admin 看得到故障情境名稱與嚴重度，外部回應 16 萬位元組裡掃不到任何故障情境名稱、`scenarioId`、`severity`、`injected`。
  - 重啟伺服器：金鑰仍有效；重新選定資料來源後，歷史含重啟前的讀值與事件；撤銷後立刻 401。
- 回歸測試與 code review 的結果見 §2.4。

### 2.3 實測發現（留給 WMOM-20261125-03，已寫進該 issue）

- 伺服器重啟後模擬器狀態歸零：重啟前鎖存的 242 不在 `/alarms/active`，事件流也沒有對應的解除事件。
- 伺服器重啟後要有人登入重新選定資料來源，即時模擬才會再跑；在那之前 Live 的歷史查不到。
- Live 的寫入間隔不是精確的 10 秒，實測 10.12–10.17 秒，一個 10 分鐘窗通常 59 筆。`/stats-10min` 因此改用間隔的中位數判定殘缺窗（`StatsBuilder.median_period_s`）。
- 時間倍率大於 1 時資料變稀疏，時間戳會前後跳（讀程式得知，沒有實測）。
- 產生情境會暫停即時模擬並重設風場狀態，對外 API 以 `live_epoch` 標示不連續。
- 附帶看到：`modules/monitoring/data/farms/legacy/config.json`（有進版控）的 `name` / `description` 是亂碼，伺服器執行時會把它改寫成正確的中文並補欄位。這次沒有動它（端到端檢查後已還原）。

### 2.4 回歸測試與 code review

- **回歸**：照 CI 的指令在本機跑全部 backend 測試——2313 passed / 1 skipped / 1 xfailed（6 分 2 秒）。本機沒裝 chromadb / sentence-transformers，knowledge 的部分測試整檔略過，所以總數與 CI 不同；前次 CI 是 2240 passed / 7 skipped / 1 xfailed，這次新增 76 項。frontend 沒有動、沒有跑。CI 用 Python 3.11，本機是 3.13。
- **code review**（`code-reviewer` subagent）：沒有找到讓帶金鑰的請求拿到故障注入資訊的路徑；金鑰授權、盲測過濾、游標翻頁、`median_period_s`、`latest_stored_readings` 的執行緒安全都看過、沒有問題。提出 1 項必須修、5 項應該修：
  1. **必須修（已修）**：`stats-10min` 以實際時間判定窗是否結束。Live 每個取樣週期才寫一次，窗的最後一筆還沒寫入時窗就被放出去，之後值又變；時間倍率大於 1 時讀值的時間跑在實際時間前面，未來的窗永遠查不到。改成看這台機組最近一次寫入的讀值時間（記憶體裡有就用，沒有就查 `storage.last_live_reading_timestamp`）。
  2. **已修**：輪詢查詢每次掃整台機組的列再依 id 排序。我在審查進行中已把沒有時間下限的查詢改成從游標沿主鍵往後掃（尾端輪詢 0.1 毫秒）；有時間下限的查詢仍要排序範圍內的列，留給 -03。
  3. **查證後不改**：`session_id` 為 NULL 的舊情境事件會不會被當成 Live 放出去。查了程式：可觀測的情境事件（`BulkEvent`）與 session 隔離是 WMOM-20261021-04 同一版加入的，一定帶 `session_id`；之前產生情境只寫 `source="scenario"` 的標記，不在可觀測的來源內。NULL 的舊列是當時的 Live 事件。若照建議用情境時間窗排除，會把同一段實際時間的 Live 事件一起藏掉。加了測試鎖住，並寫進 DEC。
  4. **已修**：`0001-01-01T00:00:00+05:00` 這類日期換算 UTC 時拋 `OverflowError`，回 500 → 改回 422。
  5. **寫進文件**：dev mode 下 `/api/auth/api-keys` 不用登入（dev fallback 身分是管理員，與使用者管理端點相同）。
  6. **已修**：`/status` 的 `batch_running` 等於告訴外部系統管理端正在出題；拿掉，只留 `live` 與 `live_epoch`。
  - 審查另外指出的測試缺口：補了資料時鐘（含時間跑在實際時間前面）、舊情境標記、極端日期、`/status` 與 `/farm` 的欄位白名單、外洩掃描加上統計 / tag 字典 / 警報目錄、輪詢的查詢計畫。沒有補：並行讀寫 `latest_stored_readings` 的測試、大表效能測試。
- **最終版再驗一次真伺服器**：輪詢只回新資料；還沒收齊的窗不給；極端日期回 422；伺服器 log 沒有錯誤。

### 2.5 卡住或延後的事

- 沒有做前端的金鑰管理頁；目前用 CLI 或 admin 端點。
- 沒有把對外 API 的範例程式放進 `examples/rag_starter_kit/`（那是學生專題的 kit）；範例在 `external_api_v1.md` §4。
- `/api/export/events` 與 `/api/faults/active` 照舊給登入的人員看，沒有改。外部系統碰不到它們的前提是伺服器開 `WMOM_AUTH_ENFORCE=true`。
- 工單的唯讀端點等 WMOM-20261125-04 完成後再加。
- `docs/architecture/windMindOM-architecture.md` 的內容還沒依 EPIC-SF 改寫。

### 2.6 重大決策

- DEC-20261126-01：金鑰不是角色、一律強制；只給 Live 的可觀測資料；API 自己編版本（1.0），資料介面合約維持 1.7。

## 3. 產出清單

### 新增檔案

- `modules/auth/api_keys.py`、`modules/auth/tests/test_api_keys.py`
- `modules/monitoring/server/routers/external.py`、`modules/monitoring/tests/test_external_api.py`
- `tools/external_api_keys.py`、`tests/test_external_api_keys_cli.py`
- `docs/integration/external_api_v1.md`
- `work-logs/2026-11/2026-11-26-external-readonly-api.md`

### 修改檔案

- `modules/auth/repository.py`（`ApiKeyRow`、`SqlApiKeyStore`）、`schemas.py`、`routers/auth_router.py`（`/api/auth/api-keys`）
- `modules/monitoring/server/storage.py`（`live_readings`、`live_events`、`OBSERVABLE_CANDIDATE_SOURCES`、`reading_timestamp`）
- `modules/monitoring/server/data_broker.py`（`_remember_stored`、`latest_stored_readings`、`live_sample_period_s`）
- `modules/monitoring/server/scenario_pack.py`（`StatsBuilder.median_period_s`）
- `modules/monitoring/server/app.py`（註冊 router、CORS 加 `X-API-Key`）
- `docs/product/decision_log.md`、`docs/integration/rag_assistant_data_contract_v1.md`、`docs/API_GUIDE.md`、`docs/architecture/research-framework.md`、`docs/product/ROADMAP.md`
- `CLAUDE.md`、`ISSUES.md`、`STATUS.yaml`、`TODO.md`

### 動了狀態的 issue

- WMOM-20261125-08：in_progress → done（研究架構圖定稿，PR #241）
- WMOM-20261125-02：open → done
- WMOM-20261125-03：補上實測發現（仍 open）

### 寫進 decision_log 的決策

- DEC-20261126-01

## 4. 下次怎麼接手

- 下一項是 `WMOM-20261125-03`（長時間運轉的基礎）。建議先做重啟續跑與固定取樣間隔，因為它們直接影響對外 API 給出去的資料是否連續；再做保留期與分層儲存。
- 劉老師的 RAG 運維助理要接：伺服器開 `WMOM_AUTH_ENFORCE=true`，`python tools/external_api_keys.py create rag-assistant` 發金鑰，照 `docs/integration/external_api_v1.md` 接。
- 新增對外端點：掛在 `external.router` 上，並加進 `test_external_api.py` 的 `_ENDPOINTS`。
