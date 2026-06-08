# WMOM-20260608-01 — M5-2 ChromaVectorRetriever

- **Date**: 2026-06-08
- **Branch**: `claude/issue-WMOM-20260608-01-2026-06-08`
- **Issue**: WMOM-20260608-01（M5-2 ChromaDB 語意檢索升級）
- **Decision baseline**: DEC-20260608-01（採 RAG_Ultimate 預算向量檔 + 內嵌 `Z72_WT_embed_small` query encoder）

## 目標

新增 `ChromaVectorRetriever` 實作既有 `Retriever` Protocol（`is_baseline=False`），
讓 knowledge module 從 baseline keyword 檢索升級為語意向量檢索。
`AlertHandler` / schema / 前端不動（MVP_ARCHITECTURE §3.5 升級契約）。
baseline retriever 保留為 fallback。

## 環境（開工前確認）

- torch 2.6.0+cu124（RTX 4080，CUDA 可用）— 已裝
- sentence-transformers 3.3.1 — 已裝
- transformers 4.57.3 — 已裝
- chromadb — 缺，本 session 裝；**踩坑**：legacy resolver 先裝到 0.5.0（用 `np.float_` 撞 numpy 2.4.6），升到 **1.5.9** 才相容 numpy 2.0；cosine ephemeral 查詢實測 OK（match dist 0.0 / 正交 1.0）
- pip 本機 vendored resolvelib 壞了 → 全程用 `--use-deprecated=legacy-resolver`

## 設計

### 檔案
- `modules/knowledge/vector_loader.py` — 讀 RAG_Ultimate export（vectors.npy + chunks.jsonl + manifest.json，純 numpy+json）；adapter `{doc_id, chunk_index, text}` → `KnowledgeChunk`；驗證列數/維度對齊。**不 import chromadb/torch**（保持可測）
- `modules/knowledge/embedder.py` — `QueryEmbedder` 包 `SentenceTransformer`，lazy load，模型缺失 raise `EmbedderUnavailable`
- `modules/knowledge/chroma_retrieve.py` — `ChromaVectorRetriever`（`name="chroma_vector"`, `is_baseline=False`）；in-memory chroma collection 灌預算向量；query → encode → cosine top-k → `RetrievedChunk`
- `modules/knowledge/__init__.py` — 加 `build_chroma_alert_handler()`，失敗 graceful fallback baseline

### 路徑（可設定）
- 向量檔（244KB，小）→ **copy 進 repo** `modules/knowledge/data/wind_farm_vectors/` 並 commit
- 模型（95MB，大）→ copy 進 `modules/knowledge/models/Z72_WT_embed_small/`，**gitignore**（不入 git，走 deploy artifact）；路徑解析 env `WMOM_EMBED_MODEL_DIR` → 預設 shipped 位置

### retriever Protocol 契約
`name: str` / `is_baseline: bool` / `retrieve(query) -> list[RetrievedChunk]`

## 完成

### 新增 / 修改
- `modules/knowledge/vector_loader.py`（新）— 載入 RAG_Ultimate 預算向量檔（numpy+json）+ adapter + 驗證
- `modules/knowledge/embedder.py`（新）— `QueryEmbedder`（lazy SentenceTransformer，缺則 `EmbedderUnavailable`）
- `modules/knowledge/chroma_retrieve.py`（新）— `ChromaVectorRetriever`（實作 `Retriever`，cosine top-k）
- `modules/knowledge/__init__.py`（改）— `build_chroma_alert_handler()`（warmup + graceful fallback baseline）
- `modules/knowledge/routers/knowledge_router.py`（改）— env 開關 `WMOM_KNOWLEDGE_RETRIEVER=chroma`
- `modules/knowledge/data/wind_farm_vectors/`（新，入庫 244KB；manifest 絕對路徑已清洗）
- `modules/knowledge/models/Z72_WT_embed_small/`（92MB，gitignore，走 deploy artifact）
- `requirements.txt` — chromadb>=1.0 + sentence-transformers>=3.0
- tests：`test_vector_loader.py`（18）+ `test_chroma_retrieve.py`（skip-if-no-model）+ `test_knowledge_fallback.py`（2，必跑）

### Verify
- knowledge 94 passed / 全 backend **701 passed / 1 xfailed**（零 regression，原 696）
- env 開關實測：`WMOM_KNOWLEDGE_RETRIEVER=chroma` → `chroma_vector`（is_baseline False）；預設 → `baseline_keyword`
- 語意檢索實測：「軸承振動異常」命中 bearing_fault 文件；無 Any

### Code review（code-reviewer subagent）
3 must / 4 should / 2 nice → **採納 9/9（must+should+nice#1）**，nice#2（VectorExport 深 immutable）延後 M5-3：
- MF#1 `id=0` falsy 誤判缺 id → 改 `is None` 判斷 + 補測
- MF#2 fallback 測試被 chromadb importorskip 連坐 → 抽出 `test_knowledge_fallback.py` 必跑
- MF#3 ids/distances 取值不對稱靜默截斷 → 對稱 + 長度檢查
- SF#1 manifest 絕對路徑入庫 → 清洗 model_path/corpus_dir 為空字串
- SF#2 `EmbedderUnavailable` lazy 致首查 500 → build 後 warmup retrieve 提前 fallback
- SF#3 vector_dim float 跳過驗證 → int() 轉型 + 補測
- SF#4 行號含空行誤導 → 同報「檔案行號 + 第幾個非空 chunk」

## 踩坑
- pip vendored resolvelib 壞（`RequirementInformation`）→ 全程 `--use-deprecated=legacy-resolver`
- chromadb 0.5.0 用 `np.float_` 撞 numpy 2.4 → 升 1.5.9
- 多個 `EphemeralClient()` 共用記憶體後端 → collection 同名衝突 → 加 uuid 後綴隔離

## 下一步
- WMOM-20260608-02（Part B-2 現場完工：assignee 過濾 + 簽名/拍照）
- M5-3/4：接 RAG_Ultimate 完整 Z72 手冊向量檔（同格式，換 export_dir 即可）
- nice#2 follow-up：`VectorExport` 深 immutable（tuple chunks + readonly ndarray）
