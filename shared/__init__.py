"""shared — 跨 module 共用的 canonical schema、PLC clients、domain model。

子套件：
- ``schemas/``：canonical SCADA tag schema、event schema、work order schema 等
- ``plc_clients/``：OPC / Modbus client 實作（給 monitoring + 未來 modules 共用）
- ``domain/``：跨 module 領域模型（Turbine、Farm、Component、Alert…）

5 個 modules 都允許 import shared/，但 shared/ 不允許 import modules/。
"""
