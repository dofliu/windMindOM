# 2026-10-22 — WMOM-20261021-12：健康機組偶發 T2 336（葉片同步誤差）

> Session 類型：實作（小題）
> Session 長度：短
> 主導：Claude（劉老師選定「繼續做 -12」）
> 結果：WMOM-20261021-12 done

---

## 1. Session 目標

-04 code review 實測：健康風場長時間（12 h）偶發 T2 336（葉片 1–3 差異 5 s > 1°）。issue 要求：
1. 查健康機組葉片角度差的分佈與 336 規則的延時判定。
2. 依手冊確認 1° / 5 s 的語意。
3. 決定修規則或接受為 nuisance。
4. 加長時間（≥ 12 h、多起點）的健康風場無訊號事件測試。

## 2. 排查

### 2.1 重現

探測腳本做法：
- 釘住 `simulator.engine.utc_now` 與 `wind_model.utc_now`。
- 包住 `PlcProtection._update_signals`，記錄 `pitch_settled` 時的三對葉片差異。

結果：3 機、2026-04-10T09:00Z、12 h、`time_step` 60，WT002 在 16:04:45 跳 T2 336，與 review 報告一致。

### 2.2 延時判定沒問題

-03-b 起延時從第一個越限樣本起算，5 s 子步要兩個連續樣本才成立。
- WT002 葉片 1–3 有 77 個樣本 > 1°，只有一次連續兩個，就是那次跳機。
- issue 懷疑的「單一樣本就成立」不是原因。

### 2.3 根因：健康葉片同步誤差太大

| 來源 | 修正前 |
|---|---|
| 各葉片零點校正誤差 | σ 0.12°（WT002 葉片 1 與 3 相差 0.62°） |
| 伺服死區 | 0.18°（誤差在死區內隨機漂移） |
| 編碼器雜訊 | 穩定發電 0.08°、起動 / 緊急順槳 0.18° |

三者相加，尾端碰到 1°。手冊把「5 s > 1°」列為 T2 故障，處置是檢查變槳驅動、軸承、潤滑、I2t。所以健康機組的同步誤差應遠小於 1°。

## 3. 定案與修正（DEC-20261022-01）

修物理，規則照手冊不動，也不當成 nuisance：
- 放寬規則會讓學生學到不存在的設定值。
- nuisance 應該是可出題、有標註的干擾（-08），不是健康機組的隨機尾端。

`turbine_physics.py`：

| 參數 | 修正前 | 修正後 |
|---|---|---|
| 零點校正誤差 σ | 0.12° | 0.06° |
| 穩定發電時死區 / 雜訊 | 0.18° / 0.08° | 0.10° / 0.04° |
| 起動 / 緊急順槳死區 / 雜訊 | 0.18° / 0.18° | 不變 |

只改 σ、不改抽樣次數，主 `_rng` 序列不位移。

## 4. 驗證

### 4.1 物理

- **健康輸出**：只有 6 個 tag 改變——`WROT_PtAngValBl1-3`、`WLOD_BldFlapMom`、`WLOD_DelBldFlap`、`WLOD_DmgBldFlap`。其餘 110 個逐位元不變。
- **data quality**：20/0。
- **葉片差異分佈**：

  | 量測（14 機 × 12 h） | 修正前 | 修正後 |
  |---|---|---|
  | 「連續 5 s」最大值，批次 5 s | 1.02° | 0.49° |
  | 同上，Live 1 s | 0.84° | 0.43° |
  | 瞬間峰值，Live 1 s | 1.26° | 0.86° |

  峰值出現在變槳速率受限的陣風：各葉片伺服速率差 0.92 / 0.95 / 0.98 倍，1 s 內追上。
- **整模擬**：3 個起點 × 12 h、14 機 12 h、Live 1 s 4 h，都沒有訊號判定事件。
- **故障情境**：`pitch_imbalance` 嚴重度 1.0 / 0.8 的跳機時點不變（0.2 / 0.6 分鐘）；0.7 由 7.2 延到 19.6 分鐘。滿嚴重度跳機碼與門檻測試都通過。

### 4.2 守門測試

新增 `modules/monitoring/tests/test_healthy_blade_sync.py`，6 項。修正前 4 項會失敗（含原始重現點的 T2 336）。
- **機制**（約 6 s）：
  - 14 支種子 × 12 h × Live 1 s / 批次 5 s。
  - 判定方式與 PLC 相同：視窗是 `ceil(延時 / dt) + 1` 個樣本，讀 2 位小數的 tag 值。
  - 門檻：5 s 持續 < 0.7°、3 s 持續 < 1.5°、峰值 < 2°。
- **零點校正誤差**：50 支種子任兩片相差 < 0.4°。
- **整合**（約 37 s / 起點）：
  - 健康 3 機 12 h × 3 起點：原始重現點、冬季夜間、夏季清晨。
  - 前置條件：發電時間 ≥ 50 %。

### 4.3 starter kit 重產

`python tools/build_rag_starter_kit.py`。只有資料包 03 的事件改變：
- WT005 葉片不平衡故障的 336 跳機早 5 s（08:45:55 → 08:45:50）。
- 1.5 h 後的 `trip_cleared` 消失。那是停機後雜訊讓差異短暫低於解除值 0.7°，故障其實沒修。

基準成績、lead time（四捨五入仍 16 分鐘）、238 筆狀態轉換都不變；`tests/test_rag_starter_kit.py` 31 項通過。

### 4.4 完整 backend

1772 → __N__ passed / 7 skipped / 1 xfailed。frontend 未改動。

## 5. 產出清單

### 新增

- `modules/monitoring/tests/test_healthy_blade_sync.py`
- 本 work-log

### 修改

- `modules/monitoring/simulator/physics/turbine_physics.py`
- `examples/rag_starter_kit/packs/*`、`answers/*`（重產）
- 文件：
  - `docs/product/EPIC-DS_realistic_data_source.md`（§6.2 註、§6.3、§6.7、新 §6.10）
  - `docs/product/decision_log.md`（DEC-20261022-01）
  - `ISSUES.md`、`STATUS.yaml`、`CLAUDE.md`、`TODO.md`

### 動了狀態的 issue

- WMOM-20261021-12：open → done

## 6. 下次怎麼接手

- **-06 WS 回放**：事件與預測格式沿用合約 v1。
- **-08**：若要出葉片差異類 nuisance（編碼器雜訊、單葉片校正偏差），以有標註的情境注入，不要放大健康誤差。
- **改變槳模型**（死區、雜訊、速率差、零點）後要跑 `test_healthy_blade_sync.py`，並重產 starter kit。
