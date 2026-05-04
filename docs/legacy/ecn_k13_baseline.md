# ECN K13 Baseline — Reference numbers for windMindOM cost migration

> 對應 issue：WMOM-20260504-01（discovery for M2 cost migration）
> 用途：windMindOM 把 ECN engine 移到 `modules/cost/` 之後，**必須**重跑 K13 並比對
> 這份文件的數字 — 任何 deviation > 1% 都要查清楚原因
> Source repo：`../ECN` (path: `D:\Project_CodingSimulation\researchTopic\ECN`)
> Snapshot date：2026-05-04
> ECN repo 版本：progress 80, last_updated 2026-04-13（見 `../ECN/STATUS.yaml`）

---

## 1. K13 demo 是什麼

ECN O&M Tool V5 的官方 demo case。風場規格約如下（從 `k13_general.json` 推斷）：

- **130 turbines**（中型離岸風場）
- **完整 O&M 模型**：corrective + preventive + fixed cost + revenue loss
- **4 季 metocean data**（winter / spring / summer / autumn）
- **多種 fault type**（FTC 1-12 含 long working day 旗標）
- **多種設備等級**（vessel / crew / spare parts mobilization）

這是學界引用 ECN tool 時的 reference case；我們移植正確性的「金標準」。

---

## 2. 黃金數字（Reference vs Computed）

### 2.1 Cost calculation（`test_cost_cal_engine.py::test_k13_cost_calculation`）

| Metric | ECN V5 Reference | Current Computed | Δ% |
|---|---|---|---|
| Availability (time) | ~92.6% | **94.02%** | +1.5% |
| Availability (energy) | ~92.1% | **93.64%** | +1.7% |
| Total revenue loss | ~21.1 M EUR/yr | **15.20 M EUR/yr** | **−28%** ⚠ |
| Total repair cost | ~51.1 M EUR/yr | **52.76 M EUR/yr** | +3.2% |
| Total effort | ~72.2 M EUR/yr | **67.96 M EUR/yr** | −5.9% |
| Cost per kWh | （無 reference） | **0.0369 EUR/kWh** | n/a |

**重要**：reference 來自 ECN V5 的 OverviewResults sheet（見 test docstring），
current computed 來自當前 ECN backend `app/engine/cost_cal/`。Δ 反映 ECN repo
從 V5 Excel 移到 Python 過程的 calibration 偏差，**不是** windMindOM 引入的。

⚠ Revenue loss 偏差最大（−28%），原因待查（可能是 fault 機率 / availability /
energy yield 計算模型差異）。**windMindOM 移植 = 在當前 Python 數字上做
完全等價，不負責修補 ECN ↔ V5 的偏差**。

### 2.2 Seasonal breakdown（4 季 corrective + preventive + fixed cost）

| Season | corrective_wt_material | corrective_wt_equip | corrective_wt_revenue_loss | preventive_material | fixed_cost |
|---|---|---|---|---|---|
| winter | 3,129,581 | 3,269,378 | 6,367,752 | 0 | 5,550,000 |
| spring | 3,129,581 | 1,297,514 | 1,929,932 | 572,075 | 5,175,000 |
| summer | 3,129,581 | 878,500 | 1,074,113 | 898,975 | 5,175,000 |
| autumn | 3,129,581 | 2,222,792 | 4,015,762 | 163,450 | 5,475,000 |

（單位：EUR/yr）

冬季 weather window 最差（對 vessel-dependent corrective 的 equipment 與
revenue_loss 影響最大），夏季最佳（preventive 多排在這裡）。windMindOM 移植
後的 K13 跑出的 seasonal breakdown 必須與此**完全一致**（浮點誤差 < 1e-6）。

### 2.3 Monte Carlo（`test_monte_carlo.py::test_monte_carlo_lcoe`）

n = 100 iterations，K13 baseline。

| Metric | Value |
|---|---|
| Deterministic cost_per_kwh | 0.0369 EUR/kWh |
| Sample range（cost_per_kwh）| ~0.0349 — 0.0392 EUR/kWh |
| LCOE | **72.94 EUR/MWh** |
| CAPEX (NPV) | 650.0 M EUR |
| OPEX (NPV) | 667.3 M EUR |
| Energy (NPV) | 18.06 M MWh |
| Total cost (NPV) | 1,317.3 M EUR |

LCOE = (CAPEX + OPEX_NPV) / Energy_NPV ≈ 72.94 EUR/MWh — 屬於合理離岸風電
LCOE 區間（北海離岸風場 2020s 平均 60-90 EUR/MWh）。

### 2.4 Waiting time（`test_waiting_time_engine.py`）

3 tests pass；具體 polynomial coefficients 與 weather window 數列細節未抓
（量大、不放本檔；移植時直接用 ECN test 比對即可）。本層核心：

- Weather window 計算（Hs / Tp / wind speed thresholds）
- Polynomial fit 給 `cost_cal` 的 corrective_wt_equipment 用

---

## 3. 怎麼重跑 K13 baseline（migration 後驗證 SOP）

### 3.1 在 ECN 跑（reference）

```bash
cd D:/Project_CodingSimulation/researchTopic/ECN/backend
python -m pytest tests/test_cost_cal_engine.py -v
python -m pytest tests/test_waiting_time_engine.py -v
python -m pytest tests/test_monte_carlo.py -v
```

預期：5 tests pass（cost_cal 1 + waiting_time 3 + monte_carlo 1），
數字符合 §2 表格。

### 3.2 在 windMindOM 跑（移植後驗證）

**TBD**（等 WMOM-20260504-02 移植完成後寫）。預定：

```bash
cd D:/Project_CodingSimulation/researchTopic/windMindOM
python -m pytest modules/cost/tests/test_k13_equivalence.py -v
```

驗證 strategy：

1. **Numerical equivalence**：每個 metric 與 §2 表格的 current computed 數字
   差異 < 1e-6（浮點誤差級）
2. **Seasonal breakdown** 完全一致
3. **Monte Carlo** 用同 random seed 比較 deterministic + 抽樣分布

任何 deviation 超過 1e-6 → 移植有 bug，**stop and fix**，不能 merge。

---

## 4. K13 dataset 檔案清單（migration 時要 copy 到 windMindOM）

| 檔案 | 用途 | 大小 |
|---|---|---|
| `k13_general.json` | 風場 + 經濟參數（CAPEX、discount rate、life） | 144 行 |
| `k13_equipment.json` | 設備等級 + cost rates（vessel / crew / mob） | 217 行 |
| `k13_fault_types_wt.json` | 故障類型機率 + repair time | 836 行 |
| `k13_fixed_costs.json` | 固定成本（保險 / 場地租金 / 監控） | 95 行 |
| `k13_metocean.csv` | 氣象資料時序（Hs / Tp / Ws） | 29,225 行 |
| `k13_waiting_time_coefficients.json` | 預算的 waiting_time polynomial 係數 | 1,477 行 |
| `k13_weather_windows.json` | weather window thresholds | 251 行 |

**搬到**：`modules/cost/data/demo/k13_*.{json,csv}`（建議在 WMOM-20260504-02 一起搬）

---

## 5. ECN repo 版本記錄（snapshot）

```yaml
name: ECN O&M Tool
progress: 80
status: active
last_updated: "2026-04-13"
next_milestone: "Phase 4 - Monte Carlo validation"
description_zh: |
  離岸風電營運維護成本計算器，複製強化 ECN Excel 工具功能，包含 6 大模組：
  氣象等待時間分析、成本計算、Monte Carlo 風險評估、LCOE 計算、
  VarFluct 生命週期預測、情景比較。已驗證準確度達 10+ 位小數，
  支援 130+ 風機的大規模風場分析。
key_metrics: "6 major modules, K13 demo 130 turbines"
```

完整路徑：`D:\Project_CodingSimulation\researchTopic\ECN\STATUS.yaml`

---

## 6. 已知問題與待釐清事項

1. **ECN V5 ↔ Python calibration 偏差**（§2.1 Δ 欄位）— 不在 windMindOM 範圍，
   但若客戶問「為什麼跟 ECN V5 paper 數字不同」要能答覆。建議在 windMindOM
   報告層的「方法論」section 寫一行 disclaimer
2. **Equipment usage / Component breakdown** 在 cost result 中是空 dict
   （`equipment_usage={}, component_breakdown={}`）— 是 ECN engine 還沒實作，
   還是輸入資料缺項？migration 後要查
3. **`test_user_data_parse.py` 0 tests collected** — 檔案是 placeholder，待用
   自己的 input parser（windMindOM 應該不需要這個 — 我們自己做 schema）
