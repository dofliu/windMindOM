"""waiting_time — 氣象等待時間 polynomial 擬合 engine（migration 目標）。

對應 ECN: ../ECN/backend/app/engine/waiting_time/
Migration issue: WMOM-20260504-02（待開，建議先做，最簡單）
Files to migrate (7):
  - data_processor.py / weather_windows.py / season_filter.py
  - power_calculator.py / waiting_calculator.py / polynomial_fitter.py / __init__.py

與 cost_cal 之間透過 JSON（k13_waiting_time_coefficients.json）串接，
不直接 import — 可獨立開發測試。
"""
