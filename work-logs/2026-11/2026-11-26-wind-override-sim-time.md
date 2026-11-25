# 2026-11-26 — 風況覆寫的漸變起點改用模擬時間（WMOM-20261126-03）

> Session 類型：實作（bug fix）
> Session 長度：中
> 主導：Claude（劉老師指派 WMOM-20261126-03）
> 結果：風況模型不再讀實際時間。帶風況覆寫 / profile 的批次在任何實際時間產生都逐位元相同，有測試守著。既有的測試資料與七個範例資料包都沒有變。

---

## 1. Session 目標

`modules/monitoring/wind_model.py` 在設定風速覆寫 / ramp profile 的當下用 `utc_now()` 取「現在的自動風況」當漸變起點。批次的模擬時間是固定的，起點卻跟著實際時間變，同樣的設定在不同的實際分鐘產生，前幾分鐘的讀值就不同。全套 backend 測試偶發失敗（`test_nuisance_events.py::test_data_before_a_farm_event_is_identical_to_a_run_without_it`）就是這個原因。

開工時的兩個落差：

- `ISSUES.md` 沒有 `WMOM-20261126-03` 這一條（main 與所有遠端分支都沒有）。依任務說明補上，並照說明的內容做。
- 任務說明提到 `_farm` helper 已經先固定 `wind_model.utc_now`；repo 裡的 `_farm` 只固定 `simulator.engine.utc_now`，沒有那一行，所以第 4 項沒有東西要拿掉。

## 2. 實際完成

### 2.1 重現

固定批次起點（`simulator.engine.utc_now`＝2026-03-01 00:00 UTC），只改實際時間，`turbine_count=2`、`generate_bulk(0.02, time_step=10.0)`：

| 設定 | 同一分鐘內 | 跨過整分鐘 | 另一個季節 |
|---|---|---|---|
| `set_override(13.0, 250.0, 25.0)` | 相同 | 不同 | 不同（第一筆風速 6.14 與 9.93 m/s） |
| `set_profile("rated")` | 相同 | 不同 | 不同 |
| `set_profile("ramp_up")` / `"ramp_down"` | 不同 | 不同 | 不同 |

ramp profile 連同一分鐘內都不同，因為 profile 的起點精確到秒。

偶發失敗的那個測試：兩次建風場之間實際時間跨過整分鐘就失敗（用一個每讀一次就前進 40 秒的時鐘重跑，修正前失敗、修正後通過）。

### 2.2 原因

`wind_model.py` 有三處讀實際時間：

1. `set_override`：`_transition_from = _override_wind_speed or _get_auto_wind(utc_now())`。
2. `set_profile("ramp_up" / "ramp_down")`：同一種寫法取起點。
3. `set_profile("ramp_up" / "ramp_down")`：`_profile_start_time = utc_now()`，之後 `get_wind_speed` 拿模擬時間減它算經過時間。

第 3 處除了不可重現，值也會錯。模擬時間比實際時間早 1 小時的時候（批次起點釘在過去；或 Live 補跑中設定 profile），120 步的漸變完成後：

| profile | 應該停在 | 修正前 |
|---|---|---|
| `ramp_up` | 18 m/s | 0 m/s |
| `ramp_down` | 3 m/s | 452.88 m/s |

### 2.3 修法

風況模型不再有自己的時鐘（不匯入 `utc_now`），它知道的時間只有引擎傳給 getter 的模擬時間。

- `set_override` / `set_profile` 不在設定的當下取自動風況，只標記待定（`_transition_from_pending`、`_profile_start_pending`）。
- 下一次 `get_wind_speed(timestamp)` 用那一步的模擬時間把待定的量定下來（`_resolve_pending`）：漸變起點＝那一步的自動風況，ramp profile 的起點＝那一步的模擬時間。
- 批次與即時模擬走同一條路：批次是 `generate_bulk` 的模擬時間，即時模擬是模擬時鐘（Live 迴圈傳進來的就是 `sim_clock`）。
- 亂數抽樣次數不變：原本在 `set_override` 裡取自動風況時天氣系統與中尺度狀態各前進一步，現在同樣的一步發生在下一次 `get_wind_speed`，其間沒有別的抽樣。
- 已有風速覆寫時起點仍是覆寫值、不取自動風況；`clear_override` 的起點仍是覆寫值。這兩條路徑的行為沒有動。
- 待定的旗標掛在 `wind_model` 上，跟著狀態存檔一起 pickle（`wind_model` 在 `_CHECKPOINT_FIELDS` 裡）。存檔格式沒有變，`CHECKPOINT_VERSION` 不升；`wind_model.py` 在程式指紋裡，舊存檔照規則不還原。
- 另一個考慮過的做法是讓 `set_override` 多收一個「現在的模擬時間」參數。批次的起點要到 `generate_bulk` 裡面才決定，呼叫端在設定風況時還不知道，所以沒有採用。

### 2.4 影響範圍

**既有資料沒有變。**

- 以前「兩個時鐘都釘在批次起點」的做法（測試與 `tools/build_rag_starter_kit.py`）產生的資料，修正後逐位元相同。比對了 3 個起點 × 8 種設定 × 步長 10 s / 1 s 共 48 組，其中 40 組相同。
- 不同的 8 組都是「起點在某分鐘的第 57 秒、步長 10 s」：新的起點取在第一個物理子步的時刻（起點＋5 s），跨過了整分鐘，自動風況的分鐘值差一格。起點的秒數加子步長不滿 60 就不會有差。現有的測試與範例資料包起點都在整分或整點。
- 七個範例資料包用修正後的程式重建：21 個資料檔（raw / 10 分鐘統計 / 事件）與修正前建的逐位元相同；與 repo 裡已提交的比，Parquet 內容逐值相同、事件與答案相同（位元組不同只因為這台機器的 pyarrow 是 26.0.1、已提交的是 26.0.0，以及匯出時間）。所以**沒有重建範例資料包，也沒有記 DEC**。
- 健康輸出的守門測試（physics / invariants）在全套測試裡，全數通過。自動風況（沒有覆寫）的路徑沒有動。

**行為有變的地方（都是這張 issue 要的）：**

- 模擬時鐘與實際時間不同時（加速運轉過、補跑中、批次），覆寫從模擬當下的風況接著漸變。真的 Live 迴圈、模擬時鐘領先半年：設定覆寫那一步的基準風速變化，修正前約 +2.2 m/s，修正後約 +0.02 m/s（這兩個數字跟執行當天的日期有關）。
- ramp profile 的經過時間從模擬時間起算，2.2 的錯值不再出現。
- 模擬時鐘等於實際時間的一般即時模擬：起點從「呼叫當下」變成「下一步」，差不到一步。
- 自動風況的亂數抽樣原本在 API 執行緒做（與 Live 迴圈同時動同一個亂數產生器），現在都在跑模擬的那條執行緒。

### 2.5 測試

- `modules/monitoring/tests/test_wind_setting_sim_time.py`（新，26 項）：
  - 守門：8 種設定 × 5 個實際時間，批次資料逐位元相同。「實際時間」用替換 `simulator.time_utils` 裡的 `datetime` 來設定，所有經 `utc_now()` 讀時鐘的地方都涵蓋，不只風況模型。
  - 反向確認：批次起點換一個季節，前幾分鐘的風速不同（起點真的跟著模擬時間）。
  - 漸變起點＝那一步模擬時間的自動風況；設定的當下不抽亂數；取起點的抽樣＝自動風況走一步。
  - 設定之後、下一步之前又改設定的五種順序（起點與抽樣次數）；起點用風場當地時刻取。
  - API 的設定落在 Live 那一步的中間時，不會拿新的漸變去配還沒定的起點（見 2.6）。
  - ramp profile 的起點是模擬時間（實際時間早 / 晚 300 天都停在目標值）。
  - 設定之後、下一步之前存檔，還原後接著跑逐位元相同。
  - 修正前 26 項有 24 項失敗（通過的兩項是「設了又清掉」「連設兩次」，起點是覆寫值、本來就不取自動風況）。
- `tests/test_rag_starter_kit.py::test_build_tool_generates_a_small_pack`：第二次生成改在另一個實際時間（2031 年）做，資料檔仍要逐位元相同。拿新的建置工具配修正前的風況模型，這一項會失敗。
- `tools/build_rag_starter_kit.py` 的 `_sim_clock` 只釘批次起點，不再釘 `wind_model.utc_now`（已經沒有這個名稱）。

### 2.6 Code review 與驗證結果

`code-reviewer` subagent：Approve，沒有必須修。

- **建議修 1（已修）**：`tools/build_rag_starter_kit.py` 檔頭的 docstring 還寫「風況模型的時鐘在 `_sim_clock` 釘住」。
- **建議修 2（已修）**：即時模擬的競態。API 執行緒的設定若剛好落在 Live 那一步處理完待定之後，那一步會拿新的漸變去配還沒定的起點——第一次設定風況時起點是 `None`，算成 0 m/s，只錯一步。修改前沒有這個情況（起點在設定時就寫好）。
  - 修法：設定的一方先寫待定旗標、才寫終點與開始；`get_wind_speed` 先讀開始與終點、再定一次起點、最後才讀起點。單執行緒（批次）時多出來的那一次不做事，輸出不變。
  - ramp profile 改成先寫漸變長度、再開始漸變。
  - 其餘的競態（兩個設定在同一步之內、上一個漸變剛好結束時把新漸變的開始蓋掉）修改前就有，沒有動；後者補了一項測試，確認待定的量仍在下一步定下來。
- **可做可不做（已做）**：設定順序的測試、風場時區的測試；單調漸變的斷言不再假設自動風況低於覆寫值。

變異檢查 8 項都被測試抓到：拿掉漸變分支裡的再定一次、`clear_override` 不取消待定、已有覆寫時不取消待定、拿掉函式開頭的那一次、ramp 起點不標記待定、取起點改回讀實際時間、ramp 起點改回讀實際時間、設定當下就取自動風況。

review 修完後重跑：

- 全套 backend：2435 passed / 1 skipped / 1 xfailed（修改前 2409 passed / 1 skipped / 1 xfailed，新增 26 項）。本機沒裝 chromadb / sentence-transformers，knowledge 的部分測試整檔略過，完整數字以 CI 為準。
- 與舊做法（兩個時鐘都釘住）的 48 組比對：結果與 review 前相同（40 組逐位元相同）。
- 七個範例資料包重建：21 個資料檔與修正前建的逐位元相同。
- 真的 Live 迴圈、偶發失敗的那個測試（實際時間跨整分鐘）：通過。
- `ruff check --select E,F`（改過的檔案）：無。

### 2.7 卡住或延後的事

- **電網模型有同類問題，這次沒有修，另開 WMOM-20261126-04。** `simulator/grid_model.py` 的 recovery profile 起點也是 `utc_now()`：帶 recovery profile 的批次不可重現（實際時間差 30 秒資料就不同）；模擬時間比實際時間早 1 小時的時候算出 29.09 Hz / −7338 V（額定 60 Hz / 3500 V）。這次的守門測試沒有涵蓋電網設定。
- `FaultEngine.inject` 的 `started_at=utc_now()` 也是實際時間，只出現在管理端的故障狀態清單，不進讀值、事件、資料包，一併寫進 -04 評估。
- 順帶看到、沒有動：漸變的長度依 `get_wind_speed` 的呼叫次數計（30 步 / 120 步），不是模擬秒數，所以批次（子步 5 s）的漸變是 150 / 600 模擬秒，Live（1 s）是 30 / 120 秒。它不讀實際時間，結果是確定的；改它會動到所有帶覆寫的既有資料。`set_profile("ramp_up")` 之後 `_transition_duration` 留在 120，之後的覆寫也用 120 步。

## 3. 產出清單

### 新增檔案

- `modules/monitoring/tests/test_wind_setting_sim_time.py`
- `work-logs/2026-11/2026-11-26-wind-override-sim-time.md`

### 修改檔案

- `modules/monitoring/wind_model.py`（不讀實際時間；待定的漸變起點與 profile 起點在下一步定下來）
- `tools/build_rag_starter_kit.py`（`_sim_clock` 只釘批次起點）
- `tests/test_rag_starter_kit.py`（重產的檢查改在另一個實際時間做）
- `modules/monitoring/tests/test_healthy_blade_sync.py`（docstring）
- `docs/product/EPIC-DS_realistic_data_source.md`（「時鐘要釘兩處」加註現況）
- `ISSUES.md`、`STATUS.yaml`、`TODO.md`、`CLAUDE.md`

### 動了狀態的 issue

- WMOM-20261126-03：新增條目（原本不在 `ISSUES.md`）→ done
- WMOM-20261126-04（電網 recovery profile 的起點讀實際時間）：新開，open

### 寫進 decision_log 的決策

- 無（範例資料包與既有資料都沒有變）

## 4. 下次怎麼接手

1. EPIC-SF 第 3 項 `WMOM-20261125-04`（運維閉環），順序不變。
2. `WMOM-20261126-04`（電網 recovery profile）：修法與這次相同，約半天；`test_wind_setting_sim_time.py` 的守門測試加上電網設定即可。
3. 阻擋項：無。

## 5. 學到的事

- 「可重現」的守門測試要從最底層換掉時鐘（`time_utils` 的 `datetime`），不要逐一釘各模組的 `utc_now`：後者只守得住已經知道的那幾處，這次的問題就是漏釘一處。
- 模型自己讀時鐘、引擎又另外傳時間進來，兩個時間遲早對不上。模型只用傳進來的時間，就沒有這類問題。
