"""cost_cal — ECN 主計算 engine（migration 目標）。

對應 ECN: ../ECN/backend/app/engine/cost_cal/
Migration issue: WMOM-20260504-03（待開）
Files to migrate (8):
  - data_classes.py / corrective.py / preventive.py / fixed.py
  - revenue_loss.py / lcoe.py / aggregator.py / __init__.py

驗證 SOP 見 docs/legacy/ecn_k13_baseline.md §2.1, §2.2。
浮點誤差容忍：< 1e-6。
"""
