# 2026-10-21 — Phase 1b-a：故障物理校正到真實 Z72 保護設定值

> Session 類型：實作
> Session 長度：長
> 主導：Claude（劉老師指示「繼續做 Phase 1b」）
> 結果：WMOM-20261021-03 拆成 -03-a / -03-b / -03-c；-03-a done

---

## 1. Session 目標

WMOM-20261021-03（Phase 1b）：警報改由物理訊號越過真實判定條件觸發、T1/T2 停機語意、修 7↔3 狀態擺盪、UTC 時間戳。

## 2. 實際完成

### 2.1 先量測，結果改變了計畫

寫掃描腳本（每個情境 × 嚴重度 0–1 × 9 / 14 m/s × 25 °C × 3 h，dt 5 s），結果多數故障的物理訊號離真實門檻很遠：

| 情境 | 滿嚴重度訊號（14 m/s） | 真實門檻 |
|---|---|---|
| bearing_wear | 主軸承 44 °C | 85 / 95 °C |
| stator_winding_degradation | 定子 68 °C | 140 / 150 °C |
| nacelle_cooling_failure | 機艙櫃溫不變 | 50 °C |
| converter_cooling_fault | 冷卻水溫**下降** | — |
| grid_voltage_sag | 電壓不變 | 欠壓 |

因此警報不能直接改成由訊號觸發：-03 拆成 -03-a（本次，物理校正）→ -03-b（PLC 保護層）→ -03-c（UTC）。

### 2.2 找到的兩個根因

1. **`extra_heat` dict union 覆蓋 bug**：`turbine_physics.py` 用 `{fault heat} | {drivetrain/brake/converter heat}`，右邊把故障熱的 `bearing` / `nacelle` / `converter` 鍵整個蓋掉——這三類故障從未發熱。改為逐鍵相加。
2. **冷卻劣化只改時間常數**：`ThermalElement` 穩態 = 環境 + 熱量 × 熱阻，`cooling_factor` 只影響 τ。冷卻故障因此只會「變慢」不會「變熱」，加上降載反而變涼。新增 `resistance_scale`，`ThermalSystem.step(cooling_degradation=…)` 用故障造成的劣化提高節點熱阻（water / cabinet / transformer / nacelle / bearing / stator）。健康時 = 1.0。

### 2.3 校正與新訊號

- bearing：潤滑劣化熱阻 + 30 kW 摩擦熱；stator：絕緣熱阻 + 40 kW；transformer：30 kW、冷卻 floor 0.30；nacelle：通風 floor 0.25、22 kW、機櫃劣化減弱（讓 A273 先於 T256）
- converter：洩漏 0.8 → 12 L/h·s（數小時後液位 < 70 % → 泵穴蝕 → 靜水壓降，事件 432）
- pitch_imbalance：偏差 3.0 → 1.25°（維持「細微、後期才跳」；`test_fault_signature` 要求 0.85 時 ≥ 1.0°）
- yaw_sensor_drift：只偏風向標 1（新 key `vane1_drift_deg`），12 → 18°
- blade_icing：轉速 bias −1.5 → −0.3（原本中度就卡在啟動狀態 5），振動 6 / 9 mm/s
- grid_voltage_sag：端電壓下陷 11 % + 5 % 擺盪（60 s），既有 ride-through 保護約嚴重度 0.7 起跳機
- 新增 5 個**真實 Bachmann tag**（從 xlsx 找到）：`WYAW_YwVn2AlgnAvg5s`、`WCNV_VtgMsCnvGd1/2/3`、`WYAW_YwBrkSealsLeak`
- `TurbineSpec` 新增保護設定值，每個標 manual / assumed；`yaw_pressure_alarm` 170 → 180（手冊）

### 2.4 健康輸出不變

新類比 tag 的雜訊走新的 `_aux_rng`（不消耗主 `_rng`）；熱阻 scale 健康時乘 1.0；dict 合併改相加對健康值是 `0.0 + x`。實測 3 種工況 × 90 個樣本 × 111 個舊 tag：**0 差異（逐位元相同）**。

### 2.5 卡住或延後的事

- 警報 / 跳機仍由 `FaultEngine` severity 送出，低負載或快速升高時與訊號時點不一致 → -03-b
- generator_overspeed 低風速不會超速、stator 低負載不會到警報：這是期望的負載相依行為，但 -03-b 改訊號觸發後這些情境在低風況下將不會跳機，ground truth（-04）要處理「預期警報可能不出現」

## 3. 產出清單

### 新增檔案

- `tests/physics/test_fault_threshold_reach.py`（29 項）
- 本 work-log

### 修改檔案

- `modules/monitoring/simulator/physics/thermal_model.py`（`resistance_scale`、`cooling_degradation`）
- `modules/monitoring/simulator/physics/turbine_physics.py`（合併 bug、校正、grid sag、vane 2、新 tag、`_aux_rng`、`TurbineSpec` 設定值）
- `modules/monitoring/simulator/physics/scada_registry.py`（+5 tag）
- `docs/physics_model_status.md`、`docs/API_GUIDE.md`（111 → 116）、`docs/product/EPIC-DS_realistic_data_source.md`（§6.2 校正結果表）
- `ISSUES.md`、`STATUS.yaml`、`CLAUDE.md`、`TODO.md`

### 動了狀態的 issue

- WMOM-20261021-03：open → in_progress（拆分）
- WMOM-20261021-03-a：新增 → done
- WMOM-20261021-03-b、-03-c：新增 open

## 4. 下次怎麼接手

1. **WMOM-20261021-03-b**：PLC 保護層。設定值都在 `TurbineSpec`，訊號都已在輸出裡；判定要含延時（葉片差 5 s / 3 s / 瞬間、風向標 25 s 濾波 + 10 分鐘風速 > 4.5）。保留「復位不等於修好」不變量（`test_reset_keeps_fault.py`），但用重啟封鎖取代每步 `cmd_emergency_stop`
2. **WMOM-20261021-03-c**：UTC 時間戳
3. 阻擋項：無

## 5. 驗證

- `python -m pytest modules/*/tests/ tests/ -q` → **1464 passed / 7 skipped / 1 xfailed**（基準 1435，+29）
- `tests/physics/test_fault_threshold_reach.py` 29 項通過；mutation：把合併 bug 放回 → bearing / nacelle 2 項失敗
- `modules/monitoring/examples/data_quality_analysis.py` → **20 項通過 / 0 待改善**（與 main 一致；產生的報告與 CSV 已還原，未提交）
- 健康輸出逐位元比對：0 差異

## 6. 學到的事

- 「冷卻劣化 → 溫度上升」這類直覺效果要先量測確認；模型裡冷卻只影響時間常數，故障效果完全被吃掉
- dict union 的右運算元會覆蓋同名鍵，用在「疊加」語意時很危險
- 新增 tag 時讓 RNG 序列不變，可以用逐位元比對證明健康行為沒動，比跑統計檢查可靠得多

## 7. Open questions（park）

- assumed 設定值（變壓器 80/90、冷卻水 46/52、機櫃 57/62、靜水壓 2.5 bar、機艙 40 °C、振動 7 mm/s）是依本模型尺度選的；如果有 ABB 變頻器手冊，可以換成真實值
