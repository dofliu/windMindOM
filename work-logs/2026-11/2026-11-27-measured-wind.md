# 2026-11-27 — 實測風況匯入（WMOM-20261125-07，EPIC-SF 第 7 項）

> Session 類型：實作
> 主導：Claude（劉老師：「開始第 7 項」）
> 結果：done，DEC-20261127-03。EPIC-SF 七項全部完成。

---

## 1. 設計

- **格式**：CSV，第一列是欄名。時間＋風速必填；風向、氣溫、紊流強度（或風速標準差）、濕度、氣壓可選。常見欄名自動辨識，也可以指定對應；沒有時區的時間是風場時區；超出範圍當缺值；給了量測高度就換算到輪轂高度。
- **存在風場 DB**（`wind_series`），匯入與套用分開。
- **套用後取代模型的基準風速**（序列有的量也取代風向、氣溫等）；手動設定優先；紊流、尾流、各機組的差異照舊由模型加上去。
- **模型照樣在底下跑**：亂數抽樣次數和自動模式一樣，批次在任何實際時間產生都逐位元相同。
- **對時**：`replay`（從現在開始播，可指定從第幾小時開始）／`absolute`（模擬時間＝序列的時間）。**播完**：`loop`／`hold`／`auto`。缺太久的那一段回到模型。

## 2. 改了什麼

- `simulator/wind_series.py`（新）：`parse_csv`、`MeasuredWindSeries`（內插、npz 存取）、`MeasuredWindPlayback`（對時、播完、循環接縫）。
- `wind_model.py`：`set_measured` / `clear_measured`（一次物件指派，下一步套用、漸變）、`_free_wind`、風向 / 氣溫 / 濕度 / 氣壓 / 大氣穩定度用實測值、`effective_turbulence`、狀態的 `mode: measured`。
- `simulator/engine.py`：紊流強度改由 `effective_turbulence` 給（沒有序列時算法不變）。
- `server/storage.py`：`wind_series` 表。
- `server/routers/config.py`：`POST/GET /api/config/wind/series`、`DELETE /{id}`、`POST /{id}/apply`；`/wind/clear` 與 profile `auto` 一併停掉序列；情境的 `wind_profile_applied` 依序列時記 null。
- `docs/API_GUIDE.md` 加一節；ROADMAP 的 EPIC-SF 表第 6、7 項打勾。

## 3. 驗證

- `test_wind_series.py` 27 項：讀檔、清理、換算、錯誤訊息、repo 裡的 K13 測風資料（29,224 筆、每 3 小時）、內插與風向、缺口、循環 / 停住 / 回到模型、對時、npz、風況模型的漸變與優先順序、亂數抽樣次數、存檔還原逐位元相同、氣溫與紊流強度進到物理、API 與權限。
- `test_wind_setting_sim_time.py` 的守門清單加兩種序列設定（replay、absolute）：在五個不同的實際時間產生的批次逐位元相同。

## 4. Code review

全套測試只有一項失敗：批次期間要擋的路由清單（`test_scenario_endpoints.py` 鎖住）要加上套用的端點，已加。Code review 有兩項必須修，都修了：(1) 待套用的變更原本是一個欄位，Live 執行緒讀了、還沒清掉時 API 執行緒又放一個進來，會被清掉——改成 deque，依序套用；(2) 狀態讀了兩次「目前的序列」，中間被換掉會出錯——只讀一次。建議修的也修了：批次從序列的開頭重新播（不看 Live 跑了多久）、值改 float32、上限降到 16 萬筆、日期與時間分兩欄 / 沒補零的斜線日期 / 分號分隔、讀不懂的時間超過 5% 整份不收、單位可能不對時回報、循環接縫不接頭尾缺太久的量、進行中的漸變也從現在的風速重新開始、不知道輪轂高度時回 422、沒有模擬器時用風場設定的時區、從資料庫讀序列放到背景執行緒。沒改：存檔仍帶整份序列（見 DEC），手動設定的優先順序逐個量看（寫進 DEC）。

## 5. 下次接手

- 前端畫面（匯入、套用、狀態）併入 WMOM-20261127-01。
- 歷史回填（WMOM-20261126-02）可以用 `absolute` 對時的實測序列。
