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

- `test_wind_series.py` 22 項：讀檔、清理、換算、錯誤訊息、repo 裡的 K13 測風資料（29,224 筆、每 3 小時）、內插與風向、缺口、循環 / 停住 / 回到模型、對時、npz、風況模型的漸變與優先順序、亂數抽樣次數、存檔還原逐位元相同、氣溫與紊流強度進到物理、API 與權限。
- `test_wind_setting_sim_time.py` 的守門清單加兩種序列設定（replay、absolute）：在五個不同的實際時間產生的批次逐位元相同。

## 4. 下次接手

- 前端畫面（匯入、套用、狀態）併入 WMOM-20261127-01。
- 歷史回填（WMOM-20261126-02）可以用 `absolute` 對時的實測序列。
