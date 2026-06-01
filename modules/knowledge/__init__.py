"""knowledge module — 警報手冊 RAG（M5）。

WMOM-20260601-01 起填入 baseline 後端骨架（純 Python、simulator-first、
零重量級依賴），讓『警報 → 手冊段落』檢索能在無 ChromaDB / 無 embedding
服務的情況下跑通 demo。

主要 entry：
- ``schemas.knowledge_schemas`` — ManualChunk / RetrievedChunk / AlertContext /
  KnowledgeQuery / KnowledgeResponse domain models
- ``strategy_loader`` — 載入 RAG 策略檔（YAML），未 ready 時回退 baseline
- ``ingest`` — 從 jsonl 載入語料 + 依策略建出檢索器
- ``retrieve`` — BaselineLexicalRetriever（中英混合 lexical 比對 + 警報碼加權）
- ``alert_handler`` — AlertHandler：警報 → 查詢 → 檢索 → 回應 編排

邊界（CLAUDE.md §15）：平台只負責**載入 + query，不重新 embed**；策略檔 +
預計算向量檔由 RAG_Ultimate 研究端提供（M5-3）。ChromaDB 整合（M5-2）、
正式 parquet 語料（M5-4）、API + 前端（M5-5/M5-6）為後續 issue。
"""
