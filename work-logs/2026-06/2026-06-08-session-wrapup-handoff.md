# 2026-06-08 Session Wrap-up Handoff

> 一日多項：從「檢視專案 / 評估 workflow vs routine」一路推到 **M5 主功能全到齊**。
> 5 個 PR 進 main，0 open PR，全綠零 regression。

## 這個 session 做了什麼（時序）

1. **盤點 + 同步**（chore `21d7a9d`）
   - 發現本地 main 落後 origin **79 commits**（雲端有 autonomous 飛輪在跑）→ pull 同步
   - **清 21 筆 stale PR → 0 open**：17 超越關閉 + 1 落選（#40）+ 2 salvage（#41 退料 guard / #58 匯出按鈕，邏輯收進既有 issue）+ 補抓 #51
   - **健康度盤點 workflow**（4 agent 並行）：backend 675 + frontend 790 + 物理 15/16 → main production-ready
   - **C 決策落 2 DEC**：DEC-20260608-01（ChromaDB 採 RAG_Ultimate 預算向量檔 + 內嵌 query encoder）、DEC-20260608-02（Part B-2 assignee 過濾 + 簽名/拍照）
   - 未追蹤檔處置：WindCAE md 移出 repo、poster + z72SCADA_New(1.7G) gitignore

2. **#100** WMOM-20260608-01 — M5-2 `ChromaVectorRetriever` 語意向量檢索（chromadb + sentence-transformers + Z72_WT_embed_small；env 開關 `WMOM_KNOWLEDGE_RETRIEVER=chroma`；graceful fallback baseline）

3. **#101** WMOM-20260608-02 — M5-5 Part B-2 現場完工（`MyOrdersMode`：assignee 過濾「我的工單」+ 完工表單 + 簽名 canvas + 拍照；backend completion_signature/photos + migration + assignee 過濾）

4. **#102** — 完工佐證大小上限（FinishRequest max_length）+ 退料 guard 重做（WMOM-20260519-01，`physical_ceiling` guard + FOR UPDATE）

5. **#103** WMOM-20260608-03 — M5-3/4 完整 Z72 手冊向量檔：進 RAG_Ultimate 跑 `build_vector_file.py`（手冊 PDF → 531 chunks export），複製進 windMindOM，**程式零改動**驗證 M5-2 升級契約

## 現在狀態（main = #103 merged 後）

- **M5 progress 55 → 75%**；issue **done 79 → 83 / open 12 / in_progress 2 / 0 open PR**
- **全 backend 721 passed / 1 xfailed** + frontend **tsc 0 / vitest 797**
- M5 主功能就位：檢索層 + ChromaDB 語意 + 真手冊語料 + 現場完工 UI

## 如何啟動 / 測試（給下次 / 劉老師）

```powershell
# 後端（repo 根）
$env:WMOM_KNOWLEDGE_RETRIEVER = "chroma"   # 語意檢索；不設則 baseline 關鍵字
python run.py                               # http://localhost:8100（/docs 有 Swagger）
# 前端（另一終端）
cd frontend; npm run dev                     # http://localhost:5173
```
- 語意檢索：`/field/` → 警報檢索 → 看回真手冊段落 + badge「向量檢索 chroma_vector」
- 現場完工：`/field/` →「我的工單」→ UserSwitcher 切身分 → 完工須簽名+拍照
- 純測試：`python -m pytest modules/ -q`（721）+ `cd frontend; npm test`（797）
- 前提（本機已就位）：嵌入模型 `modules/knowledge/models/Z72_WT_embed_small/`（gitignore，走 deploy artifact）+ chromadb/torch

## 下次接手候選

- **M6 部署期**：客戶現場手冊擴充 + 一年實際警報 csv 灌入（同 RAG_Ultimate ingest pipeline，windMindOM 端換 `export_dir` 即可）
- **backlog 低優先**：WMOM-20260504-11（event-driven cost ledger）/-12（前端記憶體 in_progress）/-13（AbortController）；physics 強化群 WMOM-23~28
- **sales**：WMOM-20260503-05 客戶接觸收尾（in_progress）

## 注意 / 已知

- 嵌入模型版本 warning（ST 5.2.0 vs 本機 3.3.1）— benign，產出/載入/檢索皆正常
- 完工佐證 base64 進 DB 為 demo-first；M6 前可改物件儲存（已加 max_length 防炸）
- RAG_Ultimate 端 export 留 `exports/z72_manual_vectors`（研究端 artifact，未 commit 進該 repo）
