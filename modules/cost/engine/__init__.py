"""cost.engine — 4 個 ECN-derived 計算引擎的 namespace。

層次：

- cost_cal/      主成本計算（M2 主菜，WMOM-20260504-03）
- waiting_time/  氣象等待時間（WMOM-20260504-02，最先做）
- monte_carlo/   風險評估，依賴 cost_cal（WMOM-20260504-04）
- var_fluct/     生命週期 bathtub（WMOM-20260504-05）

Engine 之間的關係見 docs/legacy/ecn_engine_inventory.md §2.2 / §3.2。
"""
