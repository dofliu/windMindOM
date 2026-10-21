# 2026-10-21 — WMOM-20261021-10：切出風速改用平均風速判定（手冊事件 201）

> Session 類型：實作
> Session 長度：短-中
> 主導：Claude（劉老師指示「繼續做 -10 切出風速」）
> 結果：WMOM-20261021-10 done

---

## 1. Session 目標

物理層以瞬間有效風速判定切出（> 25 / 25.5 m/s 就緊急停機），高紊流、高風速時反覆切出、重啟，產生大量 I201 事件與不真實的發電中斷（-03-b 實作時觀察到）。改為手冊事件 201 的平均風速判定、正常停機、回切遲滯。

## 2. 實際完成

### 2.1 手冊依據

警報目錄 201（I 類，手冊 p.107）：原因「V > 25.0 m/s wind, 10 min. avg. or V > 35.0 wind, 5 sec. avg.」、處置「Wait until V wind,10 < 20.0 m/s min. avg.」——三個數字都有手冊出處，寫進 `TurbineSpec`（`cut_out_avg_window_s` 600、`cut_out_gust_speed` 35、`cut_out_gust_window_s` 5、`cut_back_in_speed` 20）。已查 `docs/legacy/digiwt_project_notes.md`，沒有與切出相關的既有約束。

### 2.2 先探測，再改

- 狀態機有兩處瞬間判定（`_update_state` 開頭 > 25.5 緊急停機、發電狀態 > 25 緊急停機），啟動條件 `wind_ok` 也有瞬間上限。
- **氣動模型也是瞬間閘門**：`PowerCurveModel.get_power_cp` 在瞬間風速 > `cut_out` 時直接回傳 0——只改狀態機的話，運轉中一陣 > 25 m/s 的陣風會讓功率瞬間歸零。
- 探測（暫時拿掉兩個閘門）：運轉中 25-35 m/s 維持額定轉速 22.5 rpm、額定功率、槳距約 30°，無超速——氣動 / 槳距模型在這個範圍是合理的，切出可以完全交給控制器。

### 2.3 實作（`turbine_physics.py`）

- `_RollingMean`：時間加權移動平均，dt 不同（Live 1 s、批次 5 s 子步）都正確；`is_full` 表示已累積滿一個窗長。
- `_update_storm_stop`：10 分鐘平均 > 25 或 5 秒平均 > 35 → 暴風停機旗標；10 分鐘平均 < 20 才解除。
- 暴風停機旗標成立且機組在 4 / 5 / 6 / 8 → 正常停機（cause `cut_out`，已有停機要求時不改寫）；`wind_ok` 不再看瞬間上限，改為「不在暴風停機中」。
- `PowerCurveModel` 的 `cut_out` 改傳 `math.inf`（`__init__` 與 `update_spec` 兩處）。
- `reset()` / `update_spec()` 清空平均值與旗標。

### 2.4 途中發現：開機時第一個陣風樣本＝10 分鐘平均

寫「短暫陣風不阻擋啟動」測試時，冷啟動第一步就是 28 m/s 的樣本 → 10 分鐘平均＝28 → 暴風停機；之後平均風速 24 m/s（介於 20-25）永遠不解除。修法：**平均累積滿一個窗長才判定**——開機 / reset 後前 10 分鐘沒有「10 分鐘平均」，由 5 秒平均（35 m/s）保護；解除也需要有效的 10 分鐘平均。

### 2.5 實測（1 機、2 h、dt 1 s，風況 override + 指定 TI）

| 平均風速 / TI | 發電時間比例（改前 → 改後） | 切出停機次數 | I201 事件數 |
|---|---|---|---|
| 16 m/s / 0.18 | 31.5 % → **99.8 %** | 1 → 0 | 7 → 0 |
| 22 m/s / 0.15 | 3.4 % → 5.7 % | 1 → 1 | 12 → 1 |
| 24 m/s / 0.12 | 1.7 % → 5.6 % | 3 → 1 | 12 → 1 |
| 27 m/s / 0.12 | 0.2 % → 1.9 % | 1 → 1 | 12 → 1 |

22 m/s 那次切出是 5 秒平均 36.4 m/s（陣風規則），24 m/s 是 10 分鐘平均 25.01——都照手冊。切出後 10 分鐘平均 > 20 m/s 一直不重啟，也照手冊。

### 2.6 驗證

- `tests/physics/test_envelope.py` 切出測試改寫為 6 項（原 2 項：瞬間 27 m/s 30 s 內停機、30 m/s 60 s 內功率歸零——兩者都是被本 issue 取代的舊行為）
- mutation（逐一放回舊行為）：瞬間上限 / 拿掉滿窗判定 / 拿掉 20 m/s 遲滯 / 氣動閘門放回 25 / 改回緊急停機 / 拿掉陣風規則——各有測試失敗
- 健康機組既有 111 tag 輸出逐位元不變（測試工況風速 < 25 m/s）
- `examples/data_quality_analysis.py`：20 通過 / 0 待改善
- backend 全套：1539 → **1543 passed** / 7 skipped / 1 xfailed

### 2.7 卡住或延後的事

- **高風速時陣風模型偏強**：`wind_field.py` 自然陣風事件頻率與振幅都隨平均風速放大（22 m/s 時約每 3 分鐘一次、振幅最大 4 × V / 12 ≈ 7 m/s），疊加農場與單機兩層紊流，22-24 m/s、TI 0.12-0.15 時約 7 分鐘內就越過 5 秒平均 35 m/s。切出規則照手冊；陣風的高風速校準留給 -08 / Phase 5（不在本 issue 範圍）。
- 判定用自由流有效風速而非機艙風速計讀值（`WMET_WSpeedRaw`）。

## 3. 產出清單

### 新增檔案

- 本 work-log

### 修改檔案

- `modules/monitoring/simulator/physics/turbine_physics.py`
- `tests/physics/test_envelope.py`
- 文件：`docs/product/EPIC-DS_realistic_data_source.md`（§6.3 限制標記已解、新增 §6.5）、`docs/physics_model_status.md`、`ISSUES.md`、`STATUS.yaml`、`CLAUDE.md`、`TODO.md`

### 動了狀態的 issue

- WMOM-20261021-10：open → done

## 4. 下次怎麼接手

1. **WMOM-20261021-11**：風場時區（-05 資料包要可重現，之前做）。
2. **WMOM-20261021-04**：標準答案 + 情境事件。I201 現在每次暴風只出一次，可直接當作「環境性停機」的可觀測事件（ground truth 標為非故障）。
