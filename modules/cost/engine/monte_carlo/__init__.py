"""monte_carlo — 風險評估 engine（migration 目標）。

對應 ECN: ../ECN/backend/app/engine/monte_carlo/
Migration issue: WMOM-20260504-04（待開，必須在 cost_cal 之後做）
Files to migrate (4):
  - sampler.py / runner.py / statistics.py / __init__.py

依賴：cost_cal（每次 iteration call run_cost_calculation）。
驗證：固定 random seed → deterministic 與 cost_cal §1.5 一致；
      抽樣分布 mean/std 與 ECN baseline 相同；LCOE = 72.94 EUR/MWh（K13）。
"""
