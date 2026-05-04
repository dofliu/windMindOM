"""cost module — 成本計算 + LCOE。

從 ECN O&M Tool V5（Python port）移植 4 個 engine submodule：

- engine/cost_cal/      ECN 主計算（corrective / preventive / fixed / revenue_loss / lcoe / aggregator）
- engine/waiting_time/  氣象等待時間 polynomial 擬合
- engine/monte_carlo/   風險評估（依賴 cost_cal）
- engine/var_fluct/     bathtub failure rate + lifecycle 模擬

Migration plan 與 K13 baseline 黃金數字見：

- docs/legacy/ecn_engine_inventory.md
- docs/legacy/ecn_k13_baseline.md

Status：M2 (2026-06) 進行中。WMOM-20260504-01 (skeleton + baseline) done；
WMOM-20260504-02..05 為 4 個 engine submodule 的真正移植 issue。
"""
