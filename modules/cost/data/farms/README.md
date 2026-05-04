# Farm-specific cost dataset (overlay mode)

## 用途

讓 cost engine 能依不同 farm 跑出 personalize 的成本估算，而**不必**為每個 farm 重做完整 K13-style dataset。

## 設計：K13 baseline overlay

- K13 baseline（130 × 4 MW 北海離岸 / `data/demo/k13_*.json`）提供完整的：
  - components / FTC / equipment / PM schedules / fixed costs / waiting time polynomials
- 每個 farm 只需提供 **wind_farm 級覆寫** — 其餘全部沿用 K13 預設值

未來客戶帶完整 OEM-specific 數據時，再延伸到 component-level override。

## File layout

```
modules/cost/data/farms/
├── README.md                              # 本檔
├── 台中港曲風場/
│   └── cost_inputs.json
├── 彰化離岸風場台電/
│   └── cost_inputs.json
└── {farm_id}/                             # 客戶端新增時
    └── cost_inputs.json
```

`farm_id` 必須與 `monitoring/farm_registry` 內的 farm_id 一致（系統用同一個 ID 串接 monitoring + cost + workflow）。

## Schema (cost_inputs.json)

```json
{
  "schema_version": "1.0",
  "farm_id": "台中港曲風場",
  "name": "Z72-2000-MV 台中港曲風場",
  "base_dataset": "k13",
  "currency": "EUR",
  "wind_farm_overrides": {
    "nr_turbines": 14,
    "capacity_kw": 2000,
    "investment_cost_per_kw": 1100,
    "kwh_price": 0.10,
    "lifetime_years": 20,
    "tech_yearly_salary": 70000,
    "tech_count": {"winter": 8, "spring": 6, "summer": 6, "autumn": 7, "year": 8}
  },
  "notes": "台灣陸域 Z72 / 2 MW 配置；kwh_price 與 investment_cost 取自 2026 台電 onshore reference 換算 EUR"
}
```

### 必填

| 欄位 | 說明 |
|------|------|
| `schema_version` | "1.0" |
| `farm_id` | 與 FarmRegistry 一致 |
| `base_dataset` | 目前固定 `"k13"` |

### 可覆寫的 wind_farm 參數（全部選填）

| 欄位 | K13 預設 | 說明 |
|------|----------|------|
| `nr_turbines` | 130 | 風場機組數 |
| `capacity_kw` | 4000 | 單機額定功率 (kW) |
| `investment_cost_per_kw` | 1250 | CAPEX 單價 (EUR/kW) |
| `kwh_price` | 0.13 | 售電單價 (EUR/kWh) |
| `lifetime_years` | 20 | 設計壽命 |
| `farm_efficiency` | 0.9 | wake / availability 等綜合效率 |
| `capacity_factors` | (per season) | `{winter, spring, summer, autumn, year}` |
| `tech_yearly_salary` | 150000 | 單人年薪 (EUR) |
| `tech_count` | (per season dict) | `{winter, spring, summer, autumn, year}` |

未在 `wind_farm_overrides` 列出的欄位 → 沿用 K13 預設值。

## Lookup 順序（adapter.py）

`load_engine_params_from_farm(farm_id)` 三層 fallback：

1. **第一層** — `data/farms/{farm_id}/cost_inputs.json` 存在 → 用此檔案 overrides
2. **第二層** — 否則查 `FarmRegistry.get_farm(farm_id)`，用 `turbine_count` + `turbine_spec.rated_power_kw` 推導最小 overrides，其餘沿用 K13
3. **第三層** — 兩者皆無 → 純 K13 + `is_fallback=True` warning

回傳 `(EngineParams, FarmDatasetMeta)`，meta 含 `dataset_used` / `farm_id` / `is_fallback` / `warning`，會送到 API response 給前端顯示。

## 客戶端使用

1. 在 monitoring 建一個 farm（`POST /api/farms`），取得 `farm_id`
2. 在本目錄建 `{farm_id}/cost_inputs.json`，填好 overrides
3. API 呼叫 `POST /api/cost/forecast { "dataset": "farm:{farm_id}" }`
4. 響應 `dataset_meta.is_fallback` 為 false → personalize 數字
