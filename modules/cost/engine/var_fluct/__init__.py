"""var_fluct — bathtub failure rate + lifecycle 計算 engine（migration 目標）。

對應 ECN: ../ECN/backend/app/engine/var_fluct/
Migration issue: WMOM-20260504-05（待開，最簡單，可最後做）
Files to migrate (3):
  - bathtub.py / calculator.py / __init__.py

無對外依賴。ECN 沒有對應 unit test — migration 時順便補一個。
"""
