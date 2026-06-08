# WMOM-20260608-03 — M5-3/4 接完整 Z72 手冊向量檔

- **Date**: 2026-06-08
- **Branch**: `claude/issue-M5-3-4-z72-manual-2026-06-08`
- **目標**: 用真 Z72 手冊取代 27-chunk test fixture，完成 M5-3/4 production 語料

## 做法（option A — 進 RAG_Ultimate 跑 ingest）

1. **找到 export 腳本**：`RAG_Ultimate/RAG_Enterprise_Backend/build_vector_file.py`
   （重用 `chunking_service`（recursive 500/50）+ `embedding_service`（Z72_WT_embed_small），與線上 retrieve 同模型同切法）。腳本吃 `.md/.txt` corpus 資料夾，**不直接吃 PDF**。
2. **PDF → text**：`docs/__Z72UserManual.pdf`（135 頁，有文字層非掃描檔）用 fitz 抽 238,734 字
   → 清 PUA 私用區雜字 → 寫 `z72_user_manual.txt`（臨時 corpus）。
3. **跑 build_vector_file.py**：`--corpus <txt 夾> --out exports/z72_manual_vectors`
   → **531 chunks / dim 512 / L2-normalized / Z72_WT_embed_small**。
4. **複製進 windMindOM** `modules/knowledge/data/wind_farm_vectors/`（取代 fixture）：
   - 保留 `vectors.npy`（1MB）+ `chunks.jsonl`（360KB）+ `manifest.json`
   - **刪 `embeddings.jsonl`**（3MB，loader 不讀，省 git 空間）
   - manifest 清絕對路徑（model_path / corpus_dir → ""）+ files dict 移除 embeddings.jsonl
5. **驗證**：windMindOM 端**程式碼零改動**（DEC-20260608-01 升級契約：換 export_dir/語料即可），
   只改測試斷言（fixture 27 → 真手冊 531）。

## 實測檢索（真手冊）
- "emergency pitch system drive train" → 命中 "Emergency pitch system / pitch control drive train"（score 0.64）
- "gearbox temperature" → "Generator stator temperature 6 high"（0.58）
- "safety instructions" → 0.68；"軸承故障"（中文）→ 0.39（跨語有命中）

## 測試更新
- `test_vector_loader.py`：shipped export 27→531；manifest num_chunks 531、documents ["z72_user_manual"]
- `test_chroma_retrieve.py`：語意測試從「source 含 bearing」改為「top-5 文字含 pitch」（真手冊單一 doc_id）

## Verify
- knowledge 94 passed；全 backend **721 passed / 1 xfailed** 零 regression

## 註
- 模型版本 warning（model created with ST 5.2.0 / 本機 3.3.1）— benign，向量產出 / 載入 / 檢索皆正常
- RAG_Ultimate 端 export 留在 `RAG_Ultimate/exports/z72_manual_vectors`（研究端 artifact，未 commit 進該 repo）
- M5-3/4 完成 → M5 主要功能（檢索層 + 真語料 + 現場 UI）皆就位
