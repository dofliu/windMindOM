# 2026-06-01 — Knowledge module baseline 後端骨架（WMOM-20260601-01）

> Autonomous daily worker session（cron 20:00 Asia/Taipei）。
> Branch：`claude/gifted-maxwell-Lv1VJ`。Issue：**WMOM-20260601-01**（新開）。
> Milestone：M5（Knowledge / RAG + 現場 mobile UI），EPIC-M5 子目標 **M5-1**。

---

## 1. 開工脈絡（決策樹）

- Preflight baseline 完全綠：backend **570 passed / 1 xfailed**、git tree clean。
  → 決策樹第 1（blocker / bug）、第 2（regression）皆不觸發。
- 最新 handoff = `2026-05-29-docs-reorg.md`（文件整理 session，無未竟 code 工）。
  ISSUES.md 頂部「🎯 未來大目標」是挑工入口。
- 連續多個 session 都在「擴大 frontend 測試覆蓋」（5/26→5/29）。今日改推進
  **新 epic 的第一塊**：M5-1 Knowledge module 後端（標 🔵 autonomous-friendly，
  epic 備註明寫「未 ready 用 baseline placeholder」→ 無設計歧義、單 session 可完工）。
- `modules/knowledge/` 此前僅一個空 `__init__.py`。

## 2. 認領 / 範圍

**WMOM-20260601-01 — Knowledge module 後端 baseline（M5-1）**

嚴格對齊 EPIC-M5 的 M5-1 四檔（`ingest.py` / `retrieve.py` / `strategy_loader.py`
/ `alert_handler.py`）+ schemas + baseline 語料 + tests。

**刻意不做**（屬其他 M5 子目標，避免 scope creep + 保證零 regression）：
- ChromaDB 整合 → M5-2
- 真實 parquet 語料 / RAG_Ultimate Phase 3 策略 → M5-3 / M5-4
- API router + 前端 → M5-5 / M5-6（**不動 monitoring/server/app.py，570 baseline 零風險**）

設計約束（CLAUDE.md §15）：平台只「載入 + query，不重新 embed」；**simulator-first**
（零重量級依賴，純 Python，無 ChromaDB / embedding 也能跑通 demo）。

## 3. 完成內容

### 3.1 Schemas（`schemas/knowledge_schemas.py`）

5 個 Pydantic v2 model：`ManualChunk`（手冊切塊：text + keywords + fault_codes +
oem_model）/ `RetrievedChunk`（chunk + score + matched_terms）/ `AlertContext`
（警報情境，欄位對齊 monitoring fault scenario）/ `KnowledgeQuery` / `KnowledgeResponse`。

### 3.2 strategy_loader（`strategy_loader.py`）

`RagStrategy`（embedding / retrieval / corpus 三段）+ `default_strategy()`
（內建 baseline placeholder，不讀檔永遠可用）+ `load_strategy(path)`（YAML →
驗證，缺檔/壞YAML/schema 錯顯性拋）+ `load_strategy_or_baseline(path)`
（None/缺檔回退 baseline、schema 錯仍拋 = autonomous 友善但不吞 bug）。

### 3.3 retrieve（`retrieve.py`）— BaselineLexicalRetriever

純 Python、決定性、零重量級依賴。重點：
- `_extract_terms()`：英文/代碼走 alnum token（保留底線如 `wgen_gnbrgtmp1`），
  中文走 **bigram**（單字過於發散），中英混合語料友善。
- `_normalize_code()`：`A-262` / `A 262` / `a_262` → `a262`，吸收 monitoring 與
  手冊端格式差異。
- 加權計分：fault_code 精準命中 **+10** > keyword **+3** > 內文 **+1**，反映精準度遞減。
- 排序 `(-score, chunk_id)` 確保決定性；score>0 才回傳（無命中不硬塞）；oem_model 過濾。

### 3.4 ingest（`ingest.py`）

`load_chunks_from_jsonl()`（空行略過、壞 JSON / schema 錯帶**行號**拋 ValueError）
+ `build_retriever(strategy, base_dir)`（依策略解析 corpus 路徑、非 jsonl 拒絕）。

### 3.5 alert_handler（`alert_handler.py`）— AlertHandler

`build_query_text(alert)`（message + subsystem + alert_code 串接，空欄略過）+
`AlertHandler.handle(alert, top_k)`（警報 → 查詢 → 檢索 → `KnowledgeResponse`）+
`.query(KnowledgeQuery)`。`clock` 可注入 → `retrieved_at` 測試決定性。不 import
simulator（可獨立單測）。

### 3.6 baseline 語料（`data/baseline/`）

- `strategy.yaml`：baseline-0.1 placeholder 策略。
- `z72_manual_baseline.jsonl`：**12 筆**手冊 chunk，**對齊 monitoring 真實
  FAULT_SCENARIOS 的 alarm_codes**（bearing_wear A-262/T1-240/241、generator_overspeed
  T1-27/41、converter_cooling A-32/T1-21、transformer_overheat A-350/T2-351、
  pitch_imbalance A-43/T1-311、yaw_sensor_drift A-223、stator A-264/T1-244、
  hydraulic_leak A-260/261/T1-228、blade_icing A-42/T1-236、grid_voltage_sag A-30/T1-24、
  nacelle_cooling A-256/T1-273/258 + 1 筆重啟通則）。每碼同時收「A-262」與「262」
  兩式，吸收 caller 格式差異。→ **M5-6 告警→RAG 可直接餵 monitoring alert code**。

### 3.7 依賴

`requirements.txt` 加 `pyyaml>=6.0`（先前為 transitive，strategy_loader 顯式 import）。

## 4. Verify（零 code regression）

| 項目 | 結果 |
|---|---|
| 新增 `modules/knowledge/tests/`（4 檔 42 tests） | **42 passed** |
| backend baseline `pytest modules/{workflow,cost,reporting}/tests/` | **570 passed / 1 xfailed**（零 regression） |
| frontend | 未動（本 session 純 backend 新 module，不影響 vitest 59） |

## 5. Code review

（見下方收尾補記：code-reviewer subagent 對 staged diff 的 must/should-fix 處置）

## 6. 下次 session 接手建議

- **M5-2**：ChromaDB 整合 —— 新增 `ChromaRetriever`（與 `BaselineLexicalRetriever`
  共用 `ManualChunk`/`RetrievedChunk` schema，可平滑替換）。需 `pip install chromadb`。
- **M5-6**：API router（`modules/knowledge/routers/knowledge_router.py`）+ 接 monitoring
  告警事件 → `AlertHandler.handle()` → 前端 top-3。wiring 進 `app.py`（additive include_router）。
  alert_code 直接用 monitoring `alarm_codes` 的 `{type}-{code}`（語料已對齊）。
- **M5-5**：`/field/` mobile 前端 alert detail 渲染 `KnowledgeResponse.chunks`。
- **M5-3/M5-4**（🟡 需 RAG_Ultimate Phase 3 / 真手冊）：把 baseline strategy.yaml +
  jsonl 換成 Phase 3 的 strategy.yaml + z72_manual.parquet，`RagStrategy` schema 不變。
