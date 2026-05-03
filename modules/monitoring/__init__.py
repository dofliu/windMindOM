"""monitoring module — SCADA 即時監控 + 物理模擬器。

繼承自 digiWindTurbine，於 2026-05-03 (WMOM-20260503-01) 從 repo 根目錄
搬入本路徑。內部既有的 ``from simulator.x``、``from server.x`` 等 absolute
import 仍保持原樣；entry point ``run.py`` 會把本資料夾注入 ``sys.path``，
所以這些 import 在新位置依然可解析。

長期重構（另開 issue）會把這些改為 ``from modules.monitoring.simulator.x``
等明確 import；目前優先**零行為變動**。

主要子套件：
- ``simulator/``：物理引擎、Modbus server、grid model
- ``server/``：FastAPI app、routers、storage、farm registry
- ``examples/``：external 使用範例（data quality analysis、fetch script）
- ``data/``：farm registry DB、各 farm 的 SQLite 檔
- 根 module：``wind_model``、``turbine_model``、``scada_system``、
  ``subsystems``、``opcua_interface``、``dashboard``、``main``、
  ``common_types``、``main_architecture``
"""
