"""windMindOM 測試套件。

層級：
- ``tests/monitoring/``：SCADA + 物理模型 test（M1 後逐步加入）
- ``tests/workflow/``：work order + inventory + approval test（M3-M4）
- ``tests/cost/``：cost forecast + LCOE test（M2）
- ``tests/reporting/``：月報生成 test（M4）
- ``tests/knowledge/``：RAG retrieve test（M5）
- ``tests/integration/``：跨 module 流程 test（M4+）

跑法：``python -m pytest tests/``
"""
