# Decision Log — windMindOM 產品決策紀錄

> 任何「動到架構 / 改變產品方向 / 重新定位」的決策都進這份。
> 格式：每個 decision 一個 `## DEC-{YYYYMMDD}-{NN}` 段落。
> 想反向決策（撤銷）時，在原 DEC 下加 `### Superseded by DEC-...`，**不要刪除原內容**。

---

## DEC-20260502-06 — 架構大轉向 v0.5 → v0.8.1：windMindOM 由「整合 platform」改為「digiWT 商業化升級版（運維廠商工具）」

**Date**: 2026-05-02
**Status**: accepted
**Version**: v0.8.1（現行 baseline）
**Decision maker**: Dof
**Trigger**: 用戶反思「v0.5 系統變得太複雜」+「我這些系統其實都可以獨立運作」+「windMindOM 應該定位為運維廠商工具」

### Context

2026-05-02 在 Cowork 階段做了 5 輪規劃迭代（v0.1 → v0.5），最終決定：
- v0.5 windMindOM 為獨立整合容器
- 含 Plugin SDK、Workflow Hub 獨立 service、Cost engine 雙向 webhook、4 類 Turbine Adapter ABC
- 估算 25-35 週 for 4 FTE → 1-2 人實際 12-18 個月才能 MVP

下午用戶反思幾件事：

1. **v0.5 對 1-2 人團隊太複雜**：12-18 個月才見第一個客戶風險太高
2. **每個 repo 其實可獨立成為產品**：digiWT、ECN、windAILab、RAG_Ultimate、InduSpect 都有獨立商品化潛力
3. **真正想要「整合」的動機是省維護時間**，不是賣 platform
4. **應該以 ICP 為中心思考**：目標客戶是「運維廠商」，他們需要的是「監控+庫存派工+成本+報表」聚焦工具，不是 AI 平台
5. **公司治理邊界**：windAILab 是另一間公司的業務，AI 診斷透過 API 介接即可，不必整進產品本體
6. **現場工程師也是 user**：警報跳出時要 30 秒內查到手冊答案——RAG 屬於核心功能

### Considered Options

#### A. 維持 v0.5（platform play，windMindOM 為新整合容器）
- ✅ 架構乾淨、適合 enterprise 銷售、VC pitch 故事好
- ❌ 12-18 個月 for 1-2 人；風險集中；客戶反饋進來前的工程量大

#### B. v0.6 — digiWT-evolution（digiWT 為主軸進化）
- ✅ 7 個月見收入、有 traction
- ❌ 架構不乾淨（digiWT 不是 platform-first 設計）；只解了一半問題

#### C. v0.7 — Monorepo（為「省維護時間」而整合）
- ✅ 共享 CI / docker / deps，每週省 7-8 小時維護時間
- ❌ 4-6 週重組成本；windAILab、RAG_Ultimate 的論文線會被影響

#### D. **v0.8.1 — Operator-focused product（本決策採納）**
- windMindOM = digiWT 商業化升級版（rebrand digiWT 為 windMindOM 對外名稱）
- ICP：運維廠商 + 現場工程師雙 persona
- 5 大功能：監控 + 庫存派工 + 成本（ECN 移植）+ 報表 + RAG 知識檢索
- 外部介接：windAILab / RAG_Ultimate / InduSpect 走 API + research artifact，不做 plugin SDK
- z72hmi 留外面（Z72 服務性，非通用）

### Decision

選 **D — v0.8.1 Operator-focused product**。

### Rationale

1. **ICP 切到運維廠商** vs 風場業主：
   - 運維廠商銷售週期 1-3 個月（vs 業主 12-24 個月）
   - 痛點明確（每月要報 SCADA + 成本 + 工時給業主）
   - 競品弱（Excel + LINE + 紙單）
   - 採購預算彈性高

2. **以 digiWT 為基礎**：
   - 90% 完成度，立刻可 demo
   - SCADA 平台這層工程量大，已寫好
   - 加 cost / workflow / RAG 三個 module 約 3-4 個月可以完成
   - 6 個月見第一個客戶 vs v0.5 的 12-18 個月

3. **公司治理邊界清楚**：
   - windAILab 是另一間公司的業務 — AI 故障診斷透過 API 介接，不必整進產品
   - RAG_Ultimate 是 research — 提供「策略檔 + 預計算向量檔」給 windMindOM 使用，runtime 不依賴 service
   - InduSpect 是獨立產品 — 同 windAILab 模式

4. **RAG 是核心功能不是 add-on**：
   - 現場工程師是高頻 user
   - 警報 → 查手冊是每日操作
   - RAG 是給工程師的甜頭、提升 PMF

5. **取捨接受**：
   - 放棄昨天 v0.5 的 windMindOM repo（GitHub 上的舊內容刪除，新 repo 從 digiWT clone 開始）
   - api/adapters/base.py 等 v0.5 程式廢棄（22 tests 仍是 design reference 但不繼續維護）
   - Plugin SDK / Workflow Hub 獨立 service / cost 雙向 webhook 等過度工程一律不做

### Consequences

#### 立即變動
- **Repo reset**：`github.com/dofliu/windMindOM` 刪除重建，內容從 `digiWindTurbine` clone（2026-05-02 已完成）
- **本地資料夾**：`D:\...\windFarmOM\`（v0.5）保留作備份；`D:\...\windMindOM\`（新）為實際工作目錄
- **昨天 v0.5 的程式廢棄**：`api/adapters/base.py`、`pyproject.toml` 加的 deps 等不沿用；架構與設計可作 reference
- **v0.5 文件處理**：pitch deck、daily-workflow、claude-code-templates、templates 仍適用，搬入新 repo
- **v0.5 廢棄文件**：PRODUCT_VISION_v0.5、MVP_ARCHITECTURE_v0.5、ASSETS_MAP_v0.5、ISSUES_v0.5 不搬

#### 對 issue tracker 影響
- 昨天 10 個 WMOM-20260502-* issue 全部廢棄
- 從 0 重新編號 issue（前綴 `WMOM-` 沿用，從 2026-05-03 起新編）
- 已完成的歷史 issue（00 git init、01 pitch deck、02 review、03 adapter）保留為「廢棄但歷史」

#### 對既有 6 個 repo 命運影響
- **digiWindTurbine**：保留為「研究 / 教學版本」原 GitHub repo 不動；新 windMindOM 是它的商業化 fork
- **ECN**：M2-M3 階段內容移植進 windMindOM/modules/cost/，原 repo archive
- **z72_etech**：M3-M4 階段取設計重寫進 windMindOM/modules/workflow/，原 repo archive
- **z72hmiNew**：保持獨立 active（Z72 服務性 repo）
- **windAILab**：保持獨立 active（另一公司業務）
- **RAG_Ultimate**：保持獨立 active（research line + Phase 3 論文）
- **InduSpect**：保持獨立（independent product）

#### 對時程影響
- v0.5 估算 12-18 個月（1-2 人）→ v0.8.1 估算 6-7 個月
- 第一個運維廠商 PoC 從 2027 早段提前到 2026 Q4

---

## DEC-20260504-01 — v0.5 棄用資產清單明列化（檔案層級對應 DEC-20260502-06）

**Date**: 2026-05-04
**Status**: accepted
**Version**: v0.8.1
**Decision maker**: Dof（Claude session 紀錄）
**Trigger**: WMOM-20260503-02「搬入 v0.5 有用資產」執行時，需要把 DEC-20260502-06 的「v0.5 廢棄文件不搬」拍板下沉到「具體哪些檔案不搬」的層級

### Context

DEC-20260502-06 在概念層拍板「v0.5 → v0.8.1 整體 pivot」，但沒有明列哪些 v0.5
檔案要丟棄。本次搬資產時實際盤點 `../windFarmOM_bk/`，發現除了已知會丟的
PRODUCT_VISION_v0.5 / MVP_ARCHITECTURE_v0.5 之外，還有一批容器架構衍生的
程式 / 設計筆記同樣不適用。為避免未來 session 反覆討論「這個要不要從 v0.5 撿
回來」，把清單一次性紀錄。

### Decision

下列 v0.5 資產**不搬入** windMindOM v0.8.1，全部留在 `../windFarmOM_bk/`：

**設計文件**

- `docs/MIGRATION_TO_CLAUDE_CODE.md`（306 行容器架構遷移指引）
- `docs/ASSETS_MAP.md`（437 行 8-repo 整合容器資產地圖）
- `docs/PRODUCT_VISION.md`（v0.2 框架版）
- `docs/MVP_ARCHITECTURE.md`（v0.2 容器版）
- `docs/decision_log.md`（v0.5 部分）
- `docs/adapters/simulator_notes.md`（TurbineAdapter ABC 設計筆記）
- `docs/design_notes/README.md`（z72_etech 取材設計筆記殼）
- `docs/session_handoff.md`

**程式 / scaffolding**

- `api/adapters/`（SimulatorAdapter / Z72Adapter ABC 雛形）
- `api/main.py` / `api/auth.py` / `api/config.py` / `api/models/`（容器骨架）
- `alembic/` + `alembic.ini`（DB migration 框架）
- `infra/`（容器 infra 設定）
- `tests/`（v0.5 adapter ABC 的 unit tests）
- `windmindom.egg-info/`（過渡期 setuptools 產物）
- `pyproject.toml`（v0.5 plugin SDK 用 pyproject）

**文件流**

- `BOOTSTRAP.md`、`CHANGELOG.md`、`README.md`、`TODO.md`、`STATUS.yaml`、`ISSUES.md`、`CLAUDE.md`（v0.5 版本）
- `docker-compose.yml`、`work-logs/`（v0.5）

### Rationale

1. **DEC-20260502-06 已拍板廢棄整套容器/plugin 架構** — 對應的設計文件、ABC 程式、
   migration 指引在 v0.8.1 都失去 context；保留只會混淆未來 session
2. **windMindOM v0.8.1 自有對等版本** — daily-workflow / templates / claude-code-templates
   已單獨更新到 v1.1（早於本 session），不需要再從 v0.5 覆寫
3. **git history 已保留** — `windFarmOM_bk/` 與 GitHub 上的舊 windMindOM repo 都還在，
   隨時可回查；不需要把廢棄檔案複製到 windMindOM 內污染 codebase
4. **真要撿回來時走「新 issue + 走 DEC」** — 本決策不是「永遠不准撿」，而是「不主動搬」

### Consequences

- ✅ `docs/sales/v05_assets_inventory.md` 是本決策的可執行附件（明列搬入/已現代化/棄用）
- ✅ 本檔不再為 v0.5 廢棄物開新 DEC；除非有人想把某個檔案撿回來，才需要新 DEC 反向決策
- ⚠️ `windFarmOM_bk/` 暫不刪；M2 結束後評估是否搬到 archive 目錄或刪除（git 仍保留）

---

## v0.5 階段歷史決策摘要（DEC-01 ~ DEC-05）

下面是 2026-05-02 早段 v0.1 → v0.5 規劃過程中的 5 個決策，**內容已被 DEC-06 整體 supersede**，但保留作歷史與 design reference。

### DEC-20260502-01 — RAG_Ultimate 改為 sister product（v0.4 採納，v0.8.1 沿用）

**精神保留**：RAG_Ultimate 是 research，windMindOM 內 RAG 用其提供的「策略檔 + 預計算向量檔」。
**v0.8.1 修改**：RAG 從「sister product webhook」變更為「核心功能 + research artifact 模式」（細節見 PRODUCT_VISION v0.8.1 §3.5）。

### DEC-20260502-02 — 第一個 friendly 客戶定為 Z72 風場（v0.4 採納，v0.8.1 沿用）

**精神保留**：Z72 客戶為首發 reference，無 OEM 合作門檻。
**v0.8.1 修改**：Z72 客戶可能不再是「業主」而是「Z72 機型的運維廠商」，ICP 改變但首發機型相同。

### DEC-20260502-03 — z72_etech 取材方式選 A（dev team 讀程式）（v0.4 採納，v0.8.1 沿用）

**完全沿用**：M3-M4 階段 dev team 讀 z72_etech archive 程式產出 design notes，重寫進 modules/workflow/。

### DEC-20260502-04 — 規劃文件採增量編輯（v0.3+ 採納）

**精神保留**：增量編輯為主，但 v0.5 → v0.8.1 是大轉向不算增量。
**v0.8.1 修改**：v0.8.1 之後若要再大改，必須走 DEC + 重寫架構文件。

### DEC-20260502-05 — windFarmOM rebrand 為 windMindOM（v0.5 採納）

**精神保留**：windMindOM 為對外品牌名稱。
**v0.8.1 修改**：windMindOM 不再是「整合容器」名稱，而是 digiWT 商業化版本的對外名稱。

---

## DEC-20260505-01 — turbine_snapshots 預設 7 天 retention（取代既有 permanent）

**Date**: 2026-05-05
**Status**: accepted
**Version**: v0.8.1
**Decision maker**: Claude session（劉老師確認 hotfix 三件事一起做）
**Issue**: WMOM-20260505-01

### Context

彰化 farm `wind_farm.db` 17.5 天累積 41.9 GB（1,081 萬筆 turbine_snapshots）。
原 schema 註解寫 `turbine_snapshots: permanent`，但實作 `run_cleanup` 沒清此表 + broker 重複 retroactive 寫入 + simulator state machine flapping 三因子疊加，
變成「永久保存所有 1Hz event capture」事實上不可持續（每月可達 1+ TB）。

### Considered Options

- **A. 保持 permanent，靠手動 archive** — 客戶需要自建排程。對運維廠商門檻太高
- **B. 7 天 retention（預設）** — 平衡「事後幾天可調 snapshot 看細節」與磁碟控制
- **C. 30 天 retention** — 對 demo 期間（30 分鐘 demo）太多，正常運行的 14 turbines × 30 天估約 40-80 GB（依 event 頻率）
- **D. 完全不存 snapshots，全靠即時 trend** — 失去「事故後重看 1Hz 高頻」能力

### Decision

採 **B：7 天 retention 為預設**，可由 caller 覆寫（含 0 = 不清的 legacy 模式）。

### Rationale

1. M1 第一個目標客戶為 Z72 onshore 14 機，7 天足以涵蓋「事件當晚輪班 → 隔天主管查 → 一週內走檢修流程」的工作流
2. 7 天 retention + dedupe 修補後，14 機正常運轉預估每月 < 5 GB
3. 「想看 14 天前 1Hz 細節」的需求 rare 且可由業主臨時調 retention 處理（改 `data_broker.py` `SNAPSHOTS_RETENTION_DAYS = 30` 即可）
4. **更大的設計問題（offshore / 30+ 機 / 多月場景）已超 M1 PoC scope** — 留給 M5/M6 評估換 DuckDB / TimescaleDB

### Consequences

- `Storage.run_cleanup` 加 `snapshots_retention_days: int = 7` 參數
- `DataBroker.SNAPSHOTS_RETENTION_DAYS = 7` class const，可覆寫
- API 呼叫 `query_snapshots` 時，回傳資料只涵蓋 7 天內事件（前端可加 hint「snapshot 已過保留期」）
- **Trade-off accepted**：客戶若要查 2 週前事件 1Hz 細節要請 vendor 調 retention（可寫進客戶 SOP）
- M5/M6 評估：若客戶量級 > 30 機 / 跨年資料，考慮 columnar store（DuckDB 嵌入 / TimescaleDB）— 寫進 ROADMAP backlog
- **未來可能 supersede**：當客戶帶實際使用 retention 偏好（如某運維廠商堅持 30 天），改 default 後另開 DEC

### Reference

- WMOM-20260505-01 work-log: `work-logs/2026-05/2026-05-05-snapshots-hotfix.md`
- 修補程式碼：`modules/monitoring/server/storage.py` (`run_cleanup`) +
  `modules/monitoring/server/data_broker.py` (`_trigger_snapshot` dedupe)
- VACUUM 工具：`tools/vacuum_db.py`

---

## DEC-20260608-01 — M5-2 知識檢索上 ChromaDB：採 RAG_Ultimate 預算向量檔 + 內嵌 Z72_WT_embed_small query encoder

**Date**: 2026-06-08
**Status**: accepted
**Version**: v0.8.1 / M5
**Decision maker**: 劉老師（拍板）+ Claude（格式查證）

### Context

M5-1 已上線純 Python `BaselineKeywordRetriever`（告警碼 0.6 + 關鍵字 0.3 + Jaccard 0.1，零外部依賴），simulator 模式可 demo「警報 → 手冊段落」。M5-2 要升級為語意向量檢索。架構原則（CLAUDE.md §15）：windMindOM **不自己 re-embed 語料**，只載入 RAG_Ultimate 預算向量檔 + query。2026-06-08 RAG_Ultimate 交付 `exports/wind_farm_vectors/`（vectors.npy `(27,512)` float32 L2-normalized + chunks.jsonl + embeddings.jsonl + manifest.json，embedding_model = `Z72_WT_embed_small`）。

### Considered Options

- A. 過渡自嵌入：本機 Ollama embed baseline_corpus_z72.json 進 Chroma（違反 no-re-embed，僅當橋）
- B. 只上骨架不啟用：寫 ChromaVectorRetriever 但無向量檔暫不接
- C. **採 RAG_Ultimate 預算向量檔**：load vectors.npy + chunks 進 Chroma；query 端內嵌同一個 `Z72_WT_embed_small`（標準 sentence-transformers 格式）即時 encode query 做 cosine
- D. 改方向：windMindOM 自己當正式 embedding 來源（放棄研究端分工）

### Decision

選 **C**。向量檔到位後 A（過渡自嵌入）作廢。`ChromaVectorRetriever` 實作既有 `Retriever` Protocol（AlertHandler / schema / 前端不動），baseline retriever 保留為 fallback。

### Rationale

- 向量檔格式契約完整（manifest 宣告 dim/normalized/cosine/逐列對齊），vectors.npy 實測 row L2 norm = 1.0。
- query encoder `Z72_WT_embed_small` 是**標準 sentence-transformers**（config_sentence_transformers.json + 1_Pooling + 2_Normalize + model.safetensors 95MB），windMindOM 可 `SentenceTransformer(path).encode(query)` **離線**用，不必 HTTP 接 RAG_Ultimate → 守住 simulator-first / 客戶離線部署。
- 符合「研究端供向量檔、windMindOM 只載入+query」分工，不關死 RAG_Ultimate 路線。

### Consequences

- **新依賴**：`chromadb`（輕）+ `sentence-transformers` + `torch`（重，CPU 版數百 MB / GPU 版上看 2GB）+ ship 95MB `Z72_WT_embed_small` 進 windMindOM（建議放 `modules/knowledge/models/`）。劉老師 2026-06-08 確認「收進去」。
- **退路**：若要避 torch，可把模型轉 ONNX runtime 再 ship（多一道轉檔，列 M5-2 follow-up 選項）。
- **schema adapter**：RAG_Ultimate `{doc_id, chunk_index, text}` → windMindOM `KnowledgeChunk{document_source, section, alarm_codes=[], keywords=[]}`（doc_id→document_source；向量檢索用不到 alarm_codes/keywords 留空）。
- **語料規模**：此份為 RAG_Ultimate test fixture（5 文件 / 27 chunks），足夠打通管線 + demo；完整 Z72 手冊之後同格式補。
- **新 issue**：WMOM-20260608-01（M5-2 ChromaVectorRetriever 實作）。

### Reference

- 向量檔：`../RAG_Ultimate/exports/wind_farm_vectors/`（manifest.json 契約）
- 介面：`modules/knowledge/retrieve.py`（`Retriever` Protocol + 升級註解）
- 模型：`../RAG_Ultimate/legacy_projects/embedTunedforWT/models/Z72_WT_embed_small`

---

## DEC-20260608-02 — M5-5 Part B-2 現場完工流程：依 assignee_id 過濾工單 + 完工需簽名與拍照佐證

**Date**: 2026-06-08
**Status**: accepted
**Version**: v0.8.1 / M5
**Decision maker**: 劉老師（拍板）

### Context

`/field/` mobile 頁已有 Part A（知識查詢）+ Part B-1（alert detail with RAG）。Part B-2「我的工單 + 完工」未做，先前有兩處設計歧義需劉老師定。

### Decision

1. **「我的工單」依指派 `assignee_id` 過濾**（綁 WMOM-20260510-01 mock login persona — 現場工程師身分決定看到哪些單）。
2. **「完工」動作需「簽名 + 拍照」佐證**（不只是改狀態）。

### Consequences

- **Workflow schema 擴充**：work order 完工需新增 signature（簽名影像/資料）+ photo（佐證照片）欄位 + 儲存策略（檔案 vs base64 vs 物件儲存）。
- **與 inventory/cost 鏈整合**：完工填實際用料 `actual_qty` 是 [WMOM-20260519-01] 退料 guard（`physical_ceiling`）的上游輸入 — 完工流程欄位設計決定退料邊界與月報材料成本正確性。
- **persona 依賴**：assignee 過濾需 WMOM-20260510-01 mock login 提供現場工程師身分。
- **新 issue**：WMOM-20260608-02（Part B-2：我的工單列表 + 完工簽名/拍照流程）。

### Reference

- 前端：`frontend/components/field/FieldPage.tsx`
- 關聯：WMOM-20260510-01（mock login persona）、WMOM-20260519-01（退料 guard）

---

## DEC-20260716-01 — M6-4 真 auth：stdlib JWT + RBAC，漸進非破壞式導入

**Date**: 2026-07-16
**Status**: accepted
**Version**: v0.8.1
**Decision maker**: 劉老師（「按照建議逐步完成」授權）／ Claude 執行

### Context

現況身分靠 request body 的 `actor_id` + 前端 mock login，後端無驗證層 → 任何 client
可冒充任何人、無授權強制（`PROJECT_REVIEW_2026-07-16` F5）。M6 付費客戶多真實使用者，
身分可冒充會使簽核/完工佐證失去意義 → 真 auth 是交付前提。細節見
`M6_prep_decision_brief.md`。

### Considered Options

- A. 漸進非破壞式：加 user store + JWT login + `get_current_actor` dependency（無 token
  時 fallback dev 行為），router 分批遷移。
- B. 一次全量：所有 router 從 actor_id-in-body 改 JWT，一個大 PR。
- C. 只寫 DEC，不寫程式。

### Decision

選 **A**。技術選型：
- **HS256 JWT + PBKDF2-SHA256 密碼雜湊，純 Python stdlib**（不引 PyJWT/bcrypt/cryptography）。
- RBAC 角色對映既有 signoff 角色（EMPLOYEE/LEADER/SUPERVISOR/TREASURY）+ ADMIN，不重造。
- user store：dev_mode seed 4 個 demo user（對映 `mockUsers.ts`）；production 預設空（安全預設，
  待接 DB-backed store）。
- JWT 金鑰 `WMOM_JWT_SECRET`：production 未設即 raise（杜絕不安全預設）。

### Rationale

- A 非破壞（既有 router 未採用 dependency 前行為零改變）→ 可逐步驗證、可回退、每步 CI 綠。
- stdlib crypto **零新依賴、無原生 build**（sandbox 實測 bcrypt/cryptography 原生 build 失敗），
  且直接呼應 F5 的部署 footprint 顧慮（不往 image 疊 crypto 原生輪子）。HS256 對稱金鑰對
  單客戶 on-prem PoC 已足夠；未來要非對稱/金鑰輪替再換（介面已隔離在 `tokens.py`）。

### Consequences

- 新增 `modules/auth/`（roles/tokens/passwords/users/dependencies/schemas/router）+ 34 tests。
- `app.py` 掛 `/api/auth` router（`/login` + `/me`）；`ci.yml` 加 `modules/auth/tests/`。
- 非破壞：全 backend 迴歸 899 passed / 0 failed（含 e2e lifecycle）。
- **Follow-up（不在本增量）**：DB-backed user store + admin 建帳 API + 密碼政策；router 逐支
  改用 `get_current_actor`/`require_roles` 強制授權；前端 mock login 換真 `/api/auth/login`。

---

## DEC-20260716-02 — 部署 footprint：先量測，採 deploy 專用 CPU-torch pin

**Date**: 2026-07-16
**Status**: accepted
**Version**: v0.8.1
**Decision maker**: 劉老師 ／ Claude 量測

### Context

M5-2（DEC-20260608-01）query 端帶 `torch` + 95MB 模型；M6 要 docker-compose 部客戶現場，
image 過大（`PROJECT_REVIEW` F5）。

### Considered Options

- A. 維持帶 torch（最省事）。
- B. 直接輕量化（torch 不進 production image）。
- C. 先量測 image 體積 + 客戶硬體門檻再定。

### Decision

選 **C 先量測 → 據數據採「deploy 專用 CPU-torch pin」為近期做法**。量測結果：
`sentence-transformers` 在 linux 預設拉 **CUDA torch**，image 估 **~4–5 GB**，其中 torch+CUDA
libs ≈ 2.5–3 GB（無 GPU 的客戶機純浪費）。`.dockerignore` 已排除 `bachmann/`(38MB)/frontend/docs，
app code 本身精簡，**torch 為主要體積來源**。

### Rationale

CPU-only torch pin（deploy 專用、不碰 dev 的 RTX 4080 GPU 設定）可將 image 砍半至 ~2–2.5 GB，
**零架構風險**。完整輕量化（B，torch 不進 serving，image ~0.5–1 GB）需動 M5-2 檢索路徑，
待客戶硬體很吃緊再評估。

### Consequences

- **Follow-up 實作**：Dockerfile 於 `pip install -r requirements.txt` 前先
  `pip install torch --index-url https://download.pytorch.org/whl/cpu`，讓 requirements 的
  torch 依賴以 CPU wheel 滿足；主 `requirements.txt` 不動（保留 dev GPU 相容）。
- 補充：Docker image 為 linux/CPU 且 `.dockerignore` 已排除 OPC-DA 路徑（openopc2），故 GPL/openopc2
  疑慮（見 `bachmann/README.md`）**不涉及此容器**，僅涉 Windows OPC-DA 部署。

---

## DEC-20260718-01 — 模擬運作模式改為雙軌：Scenario（情境批次生成）為模擬主路徑，Live（實際資料）保留連續落地

**Date**: 2026-07-18
**Status**: accepted
**Version**: v0.8.1
**Decision maker**: 劉老師 ／ Claude 評估
**Trigger**: 用戶實測機組資料後反思「連續即時模擬 + 持續落地」的運作模式是否合理

### Context

WMOM-20260718-01 修「Settings 改風速對 sim 無反應」時，用戶測試現行運作方式，提出更根本的
架構質疑（原文重點）：

1. **有必要把歷史資料一直存起來嗎？** 電腦總有關閉 / 暫停的時候，連續累積的資料本身很脆弱。
2. **就算持續落地，它的意義是什麼？** 我們其實有**物理模型**——設定一個半年的風況，理論上可以
   **一次性產生半年資料**，不必真的讓 sim 跑半年。這正是 IEC 61400 的做法（給定風況 bin，跑一次
   1 小時或 6×10 分鐘）。
3. **但我們不是純結構分析**——windMindOM 還有「**運維**」這層（派工 / 簽核 / 成本 / 報表），這是
   產品差異化所在。
4. **我們保留了「可外接實際資料」的選項**，所以純批次生成跟「接真實 SCADA 持續進資料」之間有矛盾。
5. **提案**：模擬狀態下可以有一種模式，讓使用者先**設定一個情境**（例：這次用 A 風場 → 選 B 風況 →
   一個月 → 產生液壓系統故障 → 然後來看怎麼處理），再進場探索。

現況盤點（本次於 codebase 確認）：

- `generate_bulk`（`POST /api/config/simulation/generate-bulk`）**已能一次批次生成最多 1 年資料**
  （`duration_hours ≤ 8760`），寫入該風場 SQLite——即「物理模型是算力、不是等待」已具備。
- 每個風場**已有各自的 DB**（`data/farms/{farm_id}/wind_farm.db`，含 `turbine_data` + `events`
  歷史），全域 `data/farms.db` 存 metadata。
- **故障目前是 runtime-only**（`fault_engine._active_faults` 記憶體清單，未落地，重啟 / 換風場即清空）
  ——這也是用戶反映「故障卡住 / 換風場後隔離」困惑的根因。

### Considered Options

#### A. 維持現狀：連續即時模擬 + 每步落地持久化
- ✅ 不用改架構
- ❌ 用戶反映的所有問題都在這：資料脆弱（關機即斷）、持續落地的語意不清、故障 runtime-only 不可重現、
  「跑著的一條時間線」對運維演練無再現性

#### B. **雙軌：Scenario 批次生成為模擬主路徑 + Live 保留連續落地（本決策採納）**
- 模擬（Scenario）：使用者**定義情境**（風場 + 風況 profile + 時長 + 故障排程）→ 物理模型
  **一次批次生成整段可重現資料集** → 進場探索 + 跑運維流程
- 實際（Live）：接 SCADA / OPC / Modbus，**維持連續即時 + 落地**（真實世界不可重現，本來就該持續存）

#### C. 純即時、完全不落地（ephemeral only）
- ✅ 最單純、無持久化脆弱性
- ❌ 完全放棄歷史 → 報表 / 趨勢 / 運維演練全部無資料可用，與產品定位衝突

### Decision

選 **B — 雙軌模式**。以「資料是否可重現」切分兩條路徑：

| 模式 | 資料性質 | 生成方式 | 落地策略 |
|------|---------|---------|---------|
| **Live** | 真實、不可重現 | 外接 SCADA/OPC/Modbus 連續串流 | 持續落地（必要，真實世界只有一次） |
| **Scenario** | 模擬、**可重現**（seed deterministic） | 情境定義 → `generate_bulk` 一次批次 | 落地為「一份具名情境資料集」，可刪可重生 |

### Rationale

1. **物理模型是「算力」不是「等待」**：`generate_bulk` 已可幾秒生成半年資料，讓 sim 真的跑半年
   毫無意義。批次生成把「時間」從 wall-clock 解耦。
2. **對齊 IEC 61400 方法論**：「給定風況 → 跑一次（1hr / 6×10min bin）」本就是標準流程，Scenario
   模式是把這個方法論產品化。
3. **化解持久化脆弱性**：關機 / 暫停不再是問題——情境資料集是 deterministic（同 seed 同風況可重生），
   「存」的是**情境定義**而非一條易斷的時間線。
4. **最大化「運維」差異化**：情境 + **排定故障** → 在**可重現案例**上練整條運維流程（派工 → 簽核 →
   成本 → 報表）。這正是 windMindOM 相對純結構分析工具的差異化，也直接回應用戶的「液壓故障 →
   看怎麼處理」訴求。
5. **化解「外接實際資料」矛盾**：Live 與 Scenario 各司其職——真實資料本來就不可重現、該持續落地；
   模擬資料改為可重現批次、不需脆弱地持續累積。兩者不再互相牽制。

### Consequences

#### 對用戶反映 6 點問題的收斂
- **#1 Settings 改風速無反應** → 已於 WMOM-20260718-01（PR #123）修掉，獨立於本決策。
- **#2 啟動流程** → **升級為「情境設定精靈」**：選風場 → 選風況 profile → 設時長 → （選）排故障 →
  批次生成 → 進場。取代原本「開機即進一條 free-run 時間線」。
- **#3 狀態可見性** → **不變，照原計畫做**：turbine 顯示「為何不發電」（cut-out / 故障跳機 / 停機），
  header 顯示當前風場。
- **#4 故障持久化** → **自然被吸收**：故障成為**情境定義的一部分**（排定注入 sim-time），批次生成時
  寫入該情境資料集的 `events` → 天生可重現、換風場不再莫名清空。
- **#5 turbine 顯示重設計** → **不變，照原計畫做**：以「發電量 vs 風速 隨時間」為主圖，降級四色 mini-trend。

#### 新增 / 變動實作
- `generate_bulk` **加「故障排程」參數**：接受 `[{sim_time, turbine_id, fault_type}, ...]`，於批次生成
  時在指定時點注入故障事件（寫 `events` + 影響該時段 physics/tags）。
- 新增 **scenario-setup 前端流程**（風場 / 風況 / 時長 / 故障排程 → 生成 → 進場）。
- 新增「**本次情境**」資料視圖 + 運維入口（從情境直接開工單 / 走簽核）。
- **Live 模式維持既有**連續模擬 / 實接路徑不動；「即時 free-run 模擬」保留為輕量「看一眼」選項，
  正式的「情境練運維」走 Scenario 批次。

#### 交付分階段（依序）
1. **本 DEC**（方向拍板，PR 掛 `hold` 待審）。
2. **#2 scenario-setup 流程**（含 `generate_bulk` 故障排程參數）。
3. **#3 狀態可見性**。
4. **#5 turbine 顯示重設計**。

#### 接受的 trade-off
- 模擬不再有「真的一直跑」的即時感（改為批次 + 回放）——但這正是要的：可重現 > 即時感。
- 需維護兩條資料路徑（Live / Scenario）的分歧——以「同一套 farm DB schema + tags」收斂，
  差異只在「資料怎麼進來」，下游（監控 / 報表 / 運維）共用。

---

## DEC-20260719-01 — 情境保存＝命名 session（承 DEC-20260718-01 #4）；啟動改為登入後選模式（#3，待建）

**Date**: 2026-07-19
**Status**: accepted
**Version**: v0.8.1
**Decision maker**: 劉老師（選「先 #4 再 #3」）／ Claude 設計
**Trigger**: Scenario 模式上線後用戶實測，回報「產生過的情境調不回來、融進歷史了」（#4）+「進系統就自動跑預設風場」（#3）

### Context

DEC-20260718-01 拍板 Scenario 批次生成後，`generate-bulk` 把資料寫進「當前 active session」、
無情境識別；`query_history` 也不依 session 過濾 → 每個情境的資料融進同一條歷史，事後無法單獨調閱。
storage 其實早有 `sessions` 表（每筆帶 `data_source` + 彈性 `config_json`，且 `turbine_data`/1m/10m/
snapshots 皆以 `session_id` 為單位），只是讀取端從未用到。

### Decision

- **情境 ＝ 一個以 `config_json.kind == "scenario"` 標記的專屬、已結束（ended）session。**
  `generate-bulk` 帶 `name` 時開新情境 session、批次資料寫該 session_id、生成後回填統計/模擬時間窗
  並 `end_session`（不帶 name 沿用舊行為，保留快速批次用法）。
- **讀取端以 `session_id` 隔離**：`query_history(session_id=...)` + `/api/scenarios`（list / get /
  history / delete）讓某情境的資料與 Live/其他歷史分開調閱。events（無 session_id、全域 sim-time 戳）
  以情境的 `sim_start..sim_end` 時間窗撈取（跨情境窗重疊時可能混入，屬已知取捨）。
- **#3 啟動流程**（本次未建，先定方向）：開機不再自動跑預設風場模擬；強制登入後先讓使用者選
  「① 實接 ② 即時模擬 ③ 產生新情境 ④ 調閱過去情境（用本 DEC 的情境清單）」，選定才進 dashboard。

### 交付分階段

1. **#4 後端（#138 merged）✅**：scenario session 模型 + session_id 隔離讀取 + `/api/scenarios` +
   11 tests（7 storage + 4 endpoint）。
2. **#4 前端（本 PR）✅**：ScenarioPage 加情境命名 + 「過去情境」清單 + observe 模式 + `ScenarioDetail`
   調閱視圖（發電量 vs 風速雙軸 + 故障事件）+ 14 render tests。
3. **#3 啟動 gate（本 PR）✅**：後端 lifespan idle（不自動起模擬）+ `/api/source`（status/select）+
   broker `source_active/kind` 狀態機 + 前端 `SourceSelectPage` 四卡全屏 + App gate。**三階段全完成。**

### 接受的 trade-off

- 沿用 `sessions` 表存情境（不另立 scenarios 表）：零 schema 遷移、複用既有清理/aggregation；
  代價是情境與 Live session 同表、靠 `config_json.kind` 區分。
- events 靠時間窗而非 session_id 關聯：省一次 schema 遷移。代價**不小**——情境的 sim-time 皆從
  生成當下 wall-clock 起算，**短時間內連續產生的情境時間窗會大幅重疊**，調閱時 events 可能混入
  其他情境（readings 走 session_id 隔離、不受影響）。故 `/api/scenarios/{id}/.../history` 回傳帶
  `events_by_time_window: true` 旗標明示此限制；徹底解法是補 `history_events.session_id`（follow-up）。

---

## DEC-20260720-01 — 情境模式收斂為「凍結資料集」：產生完不自由跑、進入情境整個 app 掛上去、設定依實際來源 gate

**日期**：2026-07-20　**承接**：DEC-20260718-01（模擬雙軌）、DEC-20260719-01（登入後選模式）
**觸發**：使用者實測回報 —「情境模式下其他功能該可用還是失效？」「情境模式下設定是否應無作用（不該再產新資料）？」+ 發現設定頁改任何選項就跳回頁頂（WMOM-20260720-05，已修）。

### 背景 / 現況落差
今日「產生新情境」＝後端 `activate_simulation`：物理引擎的 **free-run 迴圈持續在產資料**（與「即時模擬」同一條路），只是畫面停在情境設定頁。故「情境」其實**仍持續產生新資料**，不符使用者對「情境＝可重現、凍結」的直覺（也與 DEC-20260718-01 的 Scenario＝可重現批次相悖）。且「調閱過去情境」(view) 下總覽/風機細節是空的（無 active 來源餵），情境資料只在 ScenarioDetail 看得到；設定頁的風況/電網控制依**前端 AppSettings** 而非**實際 source_kind** 顯示，故在 view/情境下仍讓人改、卻無作用。

### 決策
把「情境」收斂為乾淨的**凍結資料集**模式：
1. **產生情境不自由跑**：`產生新情境` 只負責批次「造」資料集，造完**不留 free-run 迴圈**；造完落地到「檢視該情境」。
2. **進入某情境 → 整個 app 掛上去**：總覽/風機細節顯示該情境的最終狀態、歷史顯示其時間軸、工單/維護在這份資料上**演練**——全程**不產生新資料**。
3. **設定依實際來源 gate**：風況/電網/機組即時調整＝「即時模擬」專屬；view/情境/live 下停用並註明「情境風況於生成時設定」。
4. **成本/報表** 在情境模式＝反映該情境（演練 / what-if 定位），可用但非真實營運帳。

### 拆成小 PR（逐一 review、可獨立合併）
- **PR A（本 issue WMOM-20260720-06，純前端，低風險先做）**：設定頁的**模擬參數 / 風況 / 電網 / 機組**四區塊依 `/api/source/status` 的 `source_kind` gate——非 `simulation` 時以明確說明取代互動控制。（模擬參數初版誤判為「不需 gate」，review 指出 view/live 下按儲存若 sim 參數有變 → `POST /api/config/simulation` → 後端 `switch_mode` 悄悄把來源切回 simulation、live 時斷 SCADA，破壞力反而最大，故一併 gate。）獨立於 B/C，先落地「設定該無作用就真的無作用」。
- **PR B（後端＋小前端）**：`產生新情境` 不啟 free-run 迴圈（simulator 供批次用但不自由跑）；生成後導向「檢視該情境」。需處理 activate/來源狀態機。
- **PR C（後端 broker＋端點＋前端，最大、需獨立子設計）**：broker 新增「情境檢視」來源狀態——`get_all_turbines/get_turbine` 服務該情境的最終快照、history 預設該 session；總覽/風機細節掛上情境資料。**動核心來源模型，實作前另寫子設計。**
- **PR D（獨立小修）**：`GuidedTourPage` 同款 inline-component remount（客戶展示頁，#145 review 發現）+ 可選加 `react/no-unstable-nested-components` lint 防同類回歸。

### 取捨 / 風險
- PR C 動 broker 單一 active source 模型，是本決策最重的一塊；先靠 PR A/B 拿到大部分價值，C 前另立子設計 + 端到端 verify。
- 「情境檢視」與既有 `view`（調閱過去情境）語意需釐清：可能 `view` 就升級為「載入某情境到全 app」，或另立 kind。於 PR C 子設計定案。

---

## DEC-20260720-02 — 立 epic「情境比較分析」：跨情境/跨機組/有無故障，比較所有物理輸出並自動產圖

**日期**：2026-07-20　**承接**：DEC-20260718-01（情境＝可重現批次）、DEC-20260720-01（情境＝凍結資料集）
**觸發**：劉老師提出情境的更大作用——(1) 了解某風況下風機/風場運轉 + 有無注入故障的差異；(2) 能**比較分析**不同風況情境的整體差異（同情境內機組×機組、有故障 vs 無故障；跨情境同/異機組）；(3) 貫穿**所有物理模型輸出**（疲勞破壞、極限負載、葉片、轉向…）比較後直接產分析圖表。

### 關鍵前提探勘結論（決定不用先補後端資料落地）
探勘（Explore agent）確認：**所有物理輸出已逐筆落地在 `turbine_data.scada_json`**，可用 `query_history(session_id)` 依情境+機組取回。可做情境級比較的**累積指標**（最終累積損傷 `WLOD_Dmg*`、DEL `WLOD_Del*`、RUL `WLOD_RulHours`、傳動齒面磨耗 `WDRV_GbxToothWear`）皆已落地，取情境最後一筆＝最終值。唯一未預存的**極限/最大負載**可由已落地的瞬時彎矩序列 `MAX()` 求得。故此功能是**讀取/聚合/對齊/UI**工作，**不需重新落地或改 simulator**。

### 決策：立 epic「情境比較分析」，疊在 DEC-20260720-01（凍結情境）之上，分階段：
- **A0 · 情境摘要（後端純讀，地基）**：`/api/scenarios/{id}/summary` → 每機組+全場的關鍵數（最終累積損傷/DEL/RUL/發電量/可用率/跳機數/MAX 負載）。把原始情境變成「可比的數」。
- **A1 · 同情境內比較（前端）**：機組×機組（尤其**有故障 vs 沒故障**）→ 摘要表/長條 + 鑽時序。
- **A2 · 跨情境比較（後端對齊端點 + 前端）**：挑 2–3 情境 → 摘要並排（長條/雷達）+ **相對時間**（`t − sim_start`）對齊的時序疊圖 + 差異圖。
- **A3 ·（選配）**：`history_events.session_id` 情境事件歸屬乾淨、匯出比較報表。

### 設計決策
- **呈現走「摘要＋時序都要」**（先 A0 摘要看整體差異、再時序鑽進去）——摘要是「整體差異」最高訊號、也是後續比較的共用地基。
- **比較指標先以通用量**（疲勞損傷/DEL/RUL、發電量、可用率、極限負載）落地；**Z72 直驅無齒輪箱**，齒輪箱相關指標對第一個客戶略過（指標集隨機型調整）。
- **順序**：DEC-20260720-01 的 **B（不自由跑，本 PR WMOM-20260720-07）→ A0（摘要）→ C 與 A1/A2 並進**。A0 資料已備、可獨立出價值，不必等 C。

### 已知資料層 caveat（於實作處理）
- **跨情境時間軸重疊**：各情境 sim clock 皆從生成當下 wall-clock 起算，絕對時間會重疊；跨情境比較必須用相對時間對齊（`sim_start` 已存情境 config）。
- **downsampling 表非 session-safe、events 非 session 隔離**：情境比較走 raw 表 + 時間窗事件（既有 `events_by_time_window` 旗標），A3 再徹底化。

---

## 範本（複製此塊新增 decision）

```markdown
## DEC-{YYYYMMDD}-{NN} — 一句話描述

**Date**: YYYY-MM-DD
**Status**: proposed | accepted | superseded | rejected
**Version**: 對應的規劃版本
**Decision maker**: 誰

### Context

問題的背景。為什麼需要做這個決定。

### Considered Options

- A. ...
- B. ...
- C. ...

### Decision

選 X。

### Rationale

為什麼選 X。

### Consequences

這個決策帶來的影響：哪些檔案要改、哪些任務新增、哪些 trade-off 接受。
```
