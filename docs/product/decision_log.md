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
  ⚠️ **superseded（見 DEC-20260923-01）**：時序疊圖部分後來判定不需要「後端對齊端點」，改純前端算 `t − sim_start`；差異圖是否需要後端仍待評估。
- **A3 ·（選配）**：`history_events.session_id` 情境事件歸屬乾淨、匯出比較報表。

### 設計決策
- **呈現走「摘要＋時序都要」**（先 A0 摘要看整體差異、再時序鑽進去）——摘要是「整體差異」最高訊號、也是後續比較的共用地基。
- **比較指標先以通用量**（疲勞損傷/DEL/RUL、發電量、可用率、極限負載）落地；**Z72 直驅無齒輪箱**，齒輪箱相關指標對第一個客戶略過（指標集隨機型調整）。
- **順序**：DEC-20260720-01 的 **B（不自由跑，本 PR WMOM-20260720-07）→ A0（摘要）→ C 與 A1/A2 並進**。A0 資料已備、可獨立出價值，不必等 C。

### 已知資料層 caveat（於實作處理）
- **跨情境時間軸重疊**：各情境 sim clock 皆從生成當下 wall-clock 起算，絕對時間會重疊；跨情境比較必須用相對時間對齊（`sim_start` 已存情境 config）。
- **downsampling 表非 session-safe、events 非 session 隔離**：情境比較走 raw 表 + 時間窗事件（既有 `events_by_time_window` 旗標），A3 再徹底化。

---

## DEC-20260923-01 — A2 時序疊圖不需要新後端端點；純前端用既有 history 端點 + sim_start 算相對時間

**日期**：2026-09-23　**承接**：DEC-20260720-02（立 epic「情境比較分析」，A2 原文寫「後端對齊端點 + 前端」）
**觸發**：WMOM-20260922-03（A2 Part 1）與 WMOM-20260922-04（A2 Part 2）兩個 session 都把「相對時間對齊的時序疊圖」標成「後端可能需要多情境版本的歷史查詢端點」而延後；本 session（WMOM-20260923-03）重新檢視資料層，發現這個假設不成立。

### 關鍵前提探勘結論（決定不開新後端端點）
既有單情境端點 `GET /api/scenarios/{id}/turbines/{turbine_id}/history`（A1 的 `ScenarioTrendView` 已在用）已回傳該情境某機組的原始 timestamped 讀數；而每個情境的 `config.sim_start`（ISO 字串）早就隨 `GET /api/scenarios`（`SavedScenario.config.sim_start`）落在前端 `ScenarioPage` 的記憶體狀態裡，不需要額外 fetch。「相對時間對齊」（`t − sim_start`）純粹是「拿這兩份已存在的資料算差」，可以完全在前端做，不需要新的後端聚合/對齊邏輯。

### 決策
A2 時序疊圖（Part 3）以純前端功能實作，零後端變更：新增 `frontend/utils/scenarioTimeline.ts`（`simStartMs`/`buildTimelinePoints`/`formatElapsed` 純函式）+ `ScenarioCompareTimelineView.tsx`（消費既有 `history` 端點，每個選取情境各自 fetch 一次，用 `config.sim_start` 換算相對時間後疊在同一張圖）。`ScenarioCompareAcrossView` 新增第二個頁籤承載它，`ScenarioPage` 把已持有的 `savedScenarios`（含 `sim_start`）多傳一個 prop 過去，無新 API 呼叫。

### Rationale
- 避免不必要的後端工作：新聚合端點需要設計「多情境批次查詢」的 API 形狀、SQL 聚合/排序，而現有單情境端點配合前端運算就能達成同樣的使用者價值。
- 保持「一個情境一次 fetch」的簡單心智模型，跟 A1 的 `ScenarioTrendView` 一致，降低維護面。
- 代價：目前每個情境各自一次 HTTP 請求（2–5 個並發請求），比起單一後端批次端點多一點網路開銷；但情境比較上限本就是 5 個（`MAX_COMPARE_SCENARIOS`），且非高頻操作，可接受。

### Consequences
- `DEC-20260720-02` 原文「A2 · 跨情境比較（**後端對齊端點** + 前端）」中的「後端對齊端點」字樣就時序疊圖而言不再適用，已於該決策條目內加註 superseded 指回本條。
- **差異圖（A2 Part 4）是否需要後端**——已於 WMOM-20260923-06 解決：判定不需要，比照時序疊圖走純前端。做法：新增 `medianInterval`/`pickBinMs`/`binSeries`/`buildDiffSeries` 純函式，把多情境序列分桶重採樣（桶寬取選取情境中最粗的取樣間隔）後逐桶相減，兩邊都有值的桶才算得出差異，否則視為缺口（非 0）。見 `frontend/components/ScenarioCompareDiffView.tsx` 與 `work-logs/2026-09/2026-09-23-scenario-compare-a2-part4-diff.md`。
- 已知限制（非阻塞，記錄供未來讀者知悉）：recharts 的跨線 tooltip 用精確數值比對（非最近點）找每條線在游標位置的對應值，若情境取樣間隔不同，游標可能只命中部分情境的資料點；目前僅記錄為已知限制，未實作重採樣修正（見 `work-logs/2026-09/2026-09-23-scenario-compare-a2-part3-timeline.md`）。

---

## DEC-20260926-01 — PR C 子設計定案：情境掛載 app 走「與 broker 正交的唯讀端點 + 前端 Context」，不動 DataBroker 核心來源模型；工單/維護演練歸 Phase 2 另評估

**日期**：2026-09-26　**承接**：DEC-20260720-01 §3（PR C：broker＋端點＋前端，最大、需獨立子設計，`view` 語意 TBD）
**觸發**：`WMOM-20260926-01` 完成後，`TODO.md`/`ISSUES.md` 唯一剩下的「可立即接手」項目就是 PR C——但這一項自 2026-07-20 立案後，至少 8 個 autonomous session（`WMOM-20260922-03/04`、2026-09-25 系列多次）在 work-log 寫「維持前次 session 的候選清單不變」原地擱置，從未真正開工。本 session 決定花力氣把子設計寫完，解掉這個反覆被跳過的阻塞。

### Context

DEC-20260720-01 原文把 PR C 定義為「broker 新增『情境檢視』來源狀態——`get_all_turbines`/`get_turbine` 服務該情境的最終快照、history 預設該 session；總覽/風機細節掛上情境資料」，並留了一個從未解決的語意問題：「`view`（調閱過去情境）是否該升級為『載入某情境到全 app』，或另立 kind？」

本 session 用 Explore agent 徹底讀過現況（`modules/monitoring/server/data_broker.py` 全 1053 行、`routers/source.py` 全 94 行、`routers/turbines.py`、`app.py` WS broadcast loop、`routers/scenarios.py` 全 438 行、`ScenarioPage.tsx`/`App.tsx` 導覽），確認三個關鍵事實：

1. `DataBroker` 是**單一 active source** 模型：`get_all_turbines()`/`get_turbine()`（`data_broker.py:654-685`）硬性要求 `mode == SIMULATION and self.simulator`；`select_view_only()`（364-385）刻意讓兩者回空——今日「調閱情境」與「即時監控」走的是兩條完全平行、互不相交的資料路徑（前者是 `routers/scenarios.py` 的 `session_id` 隔離 storage 查詢，後者是 broker 的 live in-memory 狀態）。
2. `FarmOverview`/`TurbineDetail`/`MaintenanceHub` 這些主頁面全部直接吃 broker 的 live REST/WS 輸出，**沒有任何「資料來源可替換」的既有抽象層**可以插入。
3. `DataBroker` 的 `_lifecycle_lock`/單一 active source 假設，正是 `WMOM-20260720-04`/`-08`（M6 現場部署唯一硬阻塞）才剛用一整個 session + 4×30 併發壓測硬化完成的並發關鍵區。DEC-20260720-01 原案要求在這塊核心狀態機上疊加新語意（新增來源狀態、動 `select_view_only`），會在已知脆弱、剛硬化好的區塊上再引入變動面。

### Considered Options

- **A（DEC-20260720-01 原案）**：broker 新增「情境檢視」來源狀態，`get_all_turbines`/`select_view_only` 改服務指定情境的快照。`view` mode 升級承載此語意。
- **B（本次採用）**：完全不動 `DataBroker`/`source.py` 既有程式碼，新增與 broker 正交的唯讀、`scenario_id` 隔離端點；前端用獨立 Context 導覽到既有頁面但改吃新端點。
- **C**：把情境掛載做成 `FarmOverview`/`TurbineDetail` 的獨立分身頁面（不重用既有元件）。

### Decision

選 **B**。且明確把範圍切成 Phase 1（本次批准）/ Phase 2（deferred，不評估）：

1. **`view` mode 語意維持不變**——不升級、不擴充，仍是 `ScenarioPage` 系列既有「調閱過去情境」用法（DEC-20260720-01 §3 的語意問題到此定案：**不**把 `view` 升級成「掛載到全 app」）。
2. **新增 2 個唯讀端點**（純附加，`data_broker.py`/`routers/source.py` 一行不動）：
   - `GET /api/scenarios/{id}/turbines` — 每台機組最後一筆 reading，格式對齊既有 `server.models.TurbineReading`；重用 `get_history(limit=1, session_id=...)` 取末筆的既有模式（`routers/scenarios.py` 的 `get_scenario_turbine_history` 已示範同款查詢）。**注意**：`get_history()` 回傳的是 storage 扁平 DB row（`current_amp`/`scada_json` 混合形狀），不是 `_sim_output_to_reading()` 吃的即時 simulator 巢狀輸出——**需要新寫一個 row→`TurbineReading` 轉換 helper**（非重用 `_sim_output_to_reading`），且 DB `status` 欄位存的是原始 `operational_state` 字串（`RUNNING`/`STARTING`/`STOPPING`/`IDLE`/`FAULT`），必須重新套用等同 `_map_state()`（`data_broker.py:24-32`）的映射才能塞進 `TurbineReading.status`（`TurbineStatus` enum 只有 4 種值），否則會有 pydantic `ValidationError`（code-reviewer subagent review 指出此複雜度未被充分揭露，已補充）。
   - `GET /api/scenarios/{id}/farm-status` — 風場層 KPI，格式對齊既有 `server.models.FarmStatus`。**不可重用** `scenario_turbine_aggregates`（該聚合是情境全程平均/累積值，無「機組最終 status 分類」「瞬時 windSpeed」等 `FarmStatus` 必需欄位）；正確做法是建立在 `/turbines` 端點已經算出的「每機組最後一筆讀數」清單之上，套用與 `data_broker.py::get_farm_status()`（1027-1046，按 status 計數 operatingCount/idleCount/faultCount/offlineCount + sum powerOutput + avg windSpeed）相同的彙整邏輯——兩個端點可共用同一份底層資料組裝（code-reviewer subagent review 抓到此架構錯誤，已修正）。
3. **前端新增獨立 `ScenarioMountContext`**（不是新的 `/api/source/select` mode）：`ScenarioDetail` 提供「以此情境瀏覽總覽/機組細節」入口 → 設定 context、導覽到 `FarmOverview`/`TurbineDetail`；兩頁在 context 有值時改呼新端點、停用既有 WS 訂閱（情境資料是凍結快照、不會變）、頁面頂部常駐「情境檢視中：{name}（唯讀）」banner、**所有寫入操作一律 disabled**（curtail/dispatch/新工單...按鈕 + tooltip 說明）。與目前是否有 live/simulation 來源在跑**正交**——掛載情境不需要先切走 live，兩者可並存（使用者可能一邊看 live 總覽一邊另開分頁演練某情境）。
4. **Phase 1（本次唯一批准範圍）**：`FarmOverview` + `TurbineDetail` 兩頁的唯讀掛載。**Phase 2（deferred，本次不評估不批准）**：DEC-20260720-01 原文「工單/維護在這份資料上演練」——讓使用者在情境資料上建立/操作工單做 what-if 演練。這需要 workflow 模組加 `scenario_id` 隔離（`work_order` 表目前完全無此概念）+ 全新語意決策（演練工單算不算真工單、能不能轉正/棄置），是獨立、量級更大的設計題，故意不併入 Phase 1。`MaintenanceHub`/`ReportsPage`/`CostPage` 併入掛載模式也不在 Phase 1（這些頁面已有自己的 farmId/dataset selector 機制，非本次要解決的痛點）。

### Rationale

- **不動 `_lifecycle_lock` 保護的狀態轉換 = 不引入新的並發風險**：Option A 需要重新論證「情境掛載」如何與剛硬化好的 `_lifecycle_lock`/單一 active source 假設共存（例如：掛載情境時 live 來源該暫停嗎？`switch_mode` 併發呼叫怎麼互動？）——這些問題本身就是「需要獨立子設計」的根源。Option B 完全不碰 `start`/`stop`/`switch_mode`/`select_view_only`（`_lifecycle_lock` 保護的方法，見 `data_broker.py:291,310,344,370`），繞開這塊風險；新端點仍會共享既有 `b.storage` 讀取路徑（與 `get_scenario`/`get_scenario_summary`/`get_scenario_turbine_history` 同款、鎖外直接讀，理論上與多場切換间有既有已接受的極小 TOCTOU 窗口，非本次新增風險）——用詞收斂為「不共享可變的生命週期狀態」，而非「零耦合」。
- **正交設計更貼近實際使用情境**：情境調閱的本質是「回顧一份已凍結的資料」，沒有理由要求使用者先中斷正在監看的 live 畫面才能看歷史情境；Option A 的「單一 active source 服務情境快照」隱含兩者互斥，反而是不必要的限制。
- **重用既有查詢模式，工程風險低**：`/turbines` 端點的實作模式（`get_history(limit=1, session_id=...)`）在 `routers/scenarios.py` 已有現成先例（`get_scenario_turbine_history`），不是從零設計；`farm-status` 端點則建立在 `/turbines` 之上、套用既有 `get_farm_status()` 彙整邏輯（見上「新增 2 個唯讀端點」§2 已修正版本），同樣有明確可依循的既有模式。
- **Phase 1/2 切分避免範圍蔓延**：「工單演練」涉及的語意決策（演練工單是否算真工單）本質上是產品決策，混進本次會讓子設計又變成不可控的大題——這正是本 issue 被punt 8 次的根因（把「唯讀掛載」與「可操作的 what-if 演練」混在同一個「PR C」標籤下評估，導致每次評估都覺得太大而跳過）。拆開後 Phase 1 是純讀取端點 + 既有頁面條件式資料來源切換，量級與近期已完成的 `inspection_schedule`/`day_work_form` 單一功能 session 相當。

### Consequences

- `TODO.md`/`ISSUES.md` 的「PR C」條目改由 `WMOM-20260926-03`（Phase 1 實作，open，deliverable 已寫明）取代，未來 session 不必再重新調查/重新猶豫範圍。
- **若劉老師認為情境掛載本來就該與 live 互斥**（例如怕使用者混淆「現在看的是即時還是回放」），需要回頭修正本決策——Option A（broker 內建互斥的來源狀態）在那個前提下才是對的方案，本次的 banner + disabled 寫入操作是本 session 對「避免混淆」的替代解法，若被否決需另評估。
- Phase 2（工單演練）留待有明確產品需求時另立 issue + decision log 條目，不在 M6 前排期。
- 詳細探勘依據、逐檔案行號見 `work-logs/2026-09/2026-09-26-pr-c-scenario-mount-subdesign.md`。

---

## DEC-20261021-01 — 暫停商業時程與真實現場介接；主線改為「擬真資料源」，供外部 RAG 即時維修助手（學生專題）驗證

**日期**：2026-10-21　**狀態**：accepted　**Decision maker**：劉老師
**取代**：ROADMAP v0.8.1 Month 6（PoC + 第一筆合約）與「2026-Q4 第一個運維廠商客戶」目標；`docs/product/PRODUCT_VISION.md` 的商業時程部分保留為歷史，不再作為排程依據

### Context

2026-10-20 session 盤點專案時發現：工程面 M1–M4 已 100%、M5 ~75%，但 M6（10 月）只有 25%，剩下項目（現場部署、Z72 OPC tunnel、PostgreSQL、培訓、首份真實月報、簽約）全部依賴客戶或現場，且客戶接觸（WMOM-20260503-05）自 5 月以來沒有實際進展。

劉老師 2026-10-21 定調：

1. 雖然一開始想走產品路線，但改為**先把功能完備再說**，商業時程不再需要。
2. **實際接真實風場或 OPC 目前無法實現，暫緩**。
3. 新目標：讓系統產生**相對真實的資料**，餵給**另一個外部系統**——一個 **RAG 即時維修助手**——作為它驗證 RAG 功能的資料來源。該外部系統**尚未建立，交由學生專題完成**。
4. 輸出管道要三種都有：**檔案、串流、模仿 tag 的 OPC UA server**。

同一次盤點也查清了物理層與警報層的現況（細節見 [`EPIC-DS_realistic_data_source.md`](EPIC-DS_realistic_data_source.md) §3）：物理涵蓋面廣但精度淺、未曾與真實資料比對；更關鍵的是，模擬器的 24 個警報碼有多個與真實 Z72 清單（`docs/1040610-Z72_PLC_OPC_TAG_1040510.xlsx`，314 筆）不符，情境模式不產生警報事件，也沒有任何標準答案可供評分。

### Considered Options

- **A. 維持 M6 商業路線**：劉老師已否決。
- **B. 轉向高保真物理**（BEM、Kaimal/Mann 風場、閉迴路控制器、氣彈 FEM）：RAG 助手看到的是警報 + 狀態 + SCADA 趨勢，這些精進幾乎不改變它看到的東西，投入大、對目標貢獻小。
- **C.（採用）以「RAG 驗證」定義擬真**：警報與真實 Z72 一致 + 標準答案與可觀測資料分離 + 三條輸出管道；物理只修會改變特徵訊號的部分。

### Decision

選 **C**：

1. **商業時程暫停**：ROADMAP Month 6 的 PoC / 合約 / 培訓 / 首份真實月報（M6-1/2/3/5/6）與 WMOM-20260503-05（客戶接觸）、WMOM-20260509-F6（PostgreSQL row-lock）標為 **deferred**，不設恢復日期。M6-4（auth/RBAC）已完成部分保留。ROADMAP 剩餘工作不再按月排程。
2. **立 EPIC-DS「擬真資料源」為主線**，設計見 [`EPIC-DS_realistic_data_source.md`](EPIC-DS_realistic_data_source.md)，issue 為 WMOM-20261021-02 ~ -09。
3. **擬真優先序**：真實 Z72 警報目錄（xlsx + 手冊 Appendix C）為唯一 source of truth → 標準答案（ground truth）→ 可觀測資料像真實 SCADA（真實 tag 名、UTC、10-min stats）→ 警報行為（連鎖、重啟限制）→ 難度與多樣性 → 物理（僅限改變特徵訊號者）。
4. **三條輸出管道由同一份凍結情境驅動**：① 情境資料包檔案、② WebSocket 回放串流、③ 模仿 Bachmann Z72 tag 的 OPC UA server。可觀測資料不含答案（盲測），`ground_truth.json` 只給評分端。
5. **外部系統由學生專題建立**；windMindOM 負責提供資料、版本化的介面合約（v0 草案已寫在設計文件 §5）與範例資料包，**不實作 RAG 助手本身**。
6. **範圍限定 Z72**：其他機型待 `update_spec` 補完前不列入資料源；高保真物理維持在 ISSUES.md parking lot。

### Rationale

- 對 RAG 驗證，最致命的不是物理精度，而是「警報碼對不上手冊」——那會讓 RAG 答對反被判錯，整個驗證失真；而這也是成本最低、最該先修的地方。
- 真實風場資料最大的缺點是沒有答案卷；模擬器知道每筆異常的根因，標準答案是它作為驗證資料源最獨特的價值，必須在可觀測資料之外獨立保存。
- 三條管道共用同一份凍結情境（延續 DEC-20260720-01「情境＝凍結資料集」），可重現、可回放，學生端可先用檔案離線開發，再接串流 / OPC UA 做即時版。
- OPC UA 節點路徑對齊真實 Bachmann 讀取腳本，學生寫的介接層將來換成真實 PLC 時不必重寫，也替暫緩的真實現場介接保留了銜接點。

### Consequences

- 新增 [`docs/product/EPIC-DS_realistic_data_source.md`](EPIC-DS_realistic_data_source.md)（設計 + 介面合約 v0 + 分階段計畫）。
- `ISSUES.md`：新增 EPIC-DS 與 WMOM-20261021-01 ~ -09；EPIC-M6 標 deferred；WMOM-20260503-05、WMOM-20260509-F6 改 deferred；統計表新增 deferred 欄並更正既有計數。
- `docs/product/ROADMAP.md`、`STATUS.yaml`、`CLAUDE.md` §10/§15、`TODO.md` 同步更新方向。
- OPC UA server 需新增 `asyncua` 依賴（legacy `modules/monitoring/opcua_interface.py` 用的 `opcua` 套件不在 requirements 且已停止維護）。
- 若日後恢復商業路線，本 EPIC 的產出（真實警報目錄、擬真資料、OPC UA 介面）可直接作為 demo 與現場介接的基礎，不會白做。

---

## DEC-20261021-02 — 情境事件以 `session_id` 隔離；標準答案另存一張表，可觀測事件以白名單判定（盲測）

**日期**：2026-10-21　**狀態**：accepted　**Decision maker**：Claude（WMOM-20261021-04 實作，依 DEC-20261021-01 的盲測原則）
**取代**：DEC-20260719-01 的 trade-off「`history_events` 不加 `session_id`、情境事件靠時間窗比對」

### Context

EPIC-DS Phase 2 要讓批次情境帶可觀測事件（PLC 警報 / 跳機、狀態轉換）與標準答案。之前情境事件沒有 session，靠模擬時間窗撈，短時間連續生成的情境會互相混入；而事件量從「幾筆注入標記」變成「每情境數十到數千筆」後，時間窗比對也會把情境事件混進 Live 的時間軸。標準答案若放在情境 config 或事件裡，一般檢視者與資料匯出都會看到答案。

### Decision

1. `history_events` 加 `session_id`（舊 DB 自動補欄、舊列 NULL）。新情境以 `config.events_session_isolated: true` 標記、依 session 查；舊情境退回時間窗。Live 端（不指定 session）的查詢排除情境 session 的事件。
2. 標準答案存獨立的 `scenario_ground_truth` 表，經 `GET /api/scenarios/{id}/ground-truth` 取得，**永遠需要主管權限**（不受 `WMOM_AUTH_ENFORCE` 過渡開關影響）。
3. 可觀測事件以**白名單**判定（`storage.is_observable_event`）：PLC 事件與運轉狀態轉換；其餘（情境 / 測試計畫標記、故障生命週期、Live 的 FaultEngine 事件、操作 / 設定紀錄）一律不可觀測，新來源預設不可觀測。
4. 情境（凍結資料集）的 raw 讀值不受 3 天 retention 清除，刪除情境時一併刪事件與標準答案。

### Consequences

- 資料包匯出（-05）直接以 session 撈事件、`is_observable_event` 過濾、讀標準答案表；manifest 不得帶情境 config 的 `fault_schedule`。
- 情境的注入 / 跳機標記保留在 `history_events`（操作端情境頁的時間軸標記要用），但不屬於可觀測事件。
- 情境 raw 資料長期保留，DB 隨情境數量成長；需要時由使用者刪除情境。

---

## DEC-20261021-03 — 情境資料包排除 16 個模擬器內部量；盲測版以檔案交付，受測端不開帳號

**日期**：2026-10-21　**狀態**：accepted　**Decision maker**：Claude（WMOM-20261021-05 code review S3 / S4，依 DEC-20261021-01 / -02 的盲測原則）

### Context

模擬器輸出 116 個 tag，其中 71 個是依命名規則自創（真實 Z72 沒有）。自創 tag 有兩種：一種是現實中有感測器 / 系統量得到、只是 Z72 沒裝的（振動頻帶、負載彎矩、無功功率、冷卻液位…），另一種是模擬器的模型狀態或預測輸出（尾流虧損、大氣穩定度、疲勞累積損傷、剩餘壽命、齒面磨耗指數、轉子不平衡力）。後者沒有任何現場系統會提供，而且其中幾個等於直接報出劣化程度（`WDRV_GbxToothWear` 是齒面磨耗的累積狀態、齒輪箱過熱會加速它；疲勞損傷與剩餘壽命同理；`WROT_ImbForce` 是由各機組個體差異參數算出的不平衡力，現場只看得到 1P 振動）——盲測時等於把答案或模型參數放進資料。

另外，盲測版資料包的端點對任何登入者開放（比照情境調閱），但登入者本來就看得到情境清單（含出題者取的情境名稱）、情境 config 的 `fault_schedule` 與調閱頁的注入標記。

### Considered Options

- A. 全部 116 個 tag 都匯出，用 `source` 標明自創：最省事，但內部量洩漏答案、也不擬真。
- B. 只匯出 45 個真實 tag：最擬真，但丟掉兩個故障情境的 key signal（`WLOD_TwrSsMom`、`WLOD_DelTwrSs`）與振動 / CMS 特徵（多個情境靠它們），學生能練的題目大幅減少。
- C. 排除模型內部量，保留量得到的自創訊號並標 `source: synthetic`。

### Decision

1. 採 C。`scenario_pack.MODEL_INTERNAL_TAGS`（16 個）：`WMET_LocalTi`、`WMET_WakeDef`、`WMET_WakeMndr`、`WMET_WakeDefl`、`WMET_WakeTi`、`WMET_ShearAlpha`、`WMET_AtmStab`、`WLOD_DmgTwrFa`、`WLOD_DmgTwrSs`、`WLOD_DmgBldFlap`、`WLOD_DmgBldEdge`、`WLOD_RulHours`、`WLOD_AlmTwr`、`WLOD_AlmBld`、`WROT_ImbForce`、`WDRV_GbxToothWear`。資料包 100 欄＝45 真實＋55 自創。
2. 塔架 / 葉片彎矩與 DEL 保留：負載監測系統量得到，且是故障情境的 key signal。測試守住：排除的 tag 不得是真實 tag、不得是任何情境的 key signal。
3. 模擬語意與真實同名 tag 不同之處寫進 tag 字典的 `note`（`WMET_WSpeedNac` 是自由流風速而非風速計、`WMET_WDirAbs` 是風場真實風向）。
4. **盲測版以檔案交付**：出題者下載（或用 CLI 匯出）後交給受測端；受測端（學生 / 外部 RAG）不開本系統帳號。端點權限維持「任何登入者」不變——擋端點擋不住清單與調閱頁。

### Consequences

- 新增會洩漏故障的模擬量時，要加進 `MODEL_INTERNAL_TAGS`（或改成量得到的形式）；-08 加入新故障情境時，key signal 不能選排除的 tag（測試會擋）。
- Live / 情境頁仍顯示全部 116 個 tag（操作端與教學用），只有資料包排除。
- 若將來要讓受測端直接連線（-06 WS 回放、-07 OPC UA），要另設不看得到情境清單的角色或 token，不能沿用一般帳號。

---

## DEC-20261021-04 — RAG 助手介面合約 v1 定稿：評分以元件 + 類別、事件碼手冊引用、延遲與早期預警，各項分列

**日期**：2026-10-21　**狀態**：accepted　**Decision maker**：劉老師（評分欄位，2026-10-21 確認）＋ Claude（WMOM-20261021-09 實作與 code review 修正）

### Context

學生專題要開發外部 RAG 維修助手，需要穩定的資料格式與一致的評分方式。-04 / -05 實作了資料包與標準答案（合約 0.1 草案），但還沒有定義助手要輸出什麼、怎麼評分。評分欄位會決定學生把力氣花在哪裡。

### Considered Options

- **診斷標籤**：
  - A. 元件 + 類別（封閉詞彙）。
  - B. 模擬器的故障 ID：學生得先學模擬器的命名，與現場脫節。
  - C. 根因自由文字：要人工或 LLM 評，不易重現。
- **手冊引用**：事件碼（Appendix C 條目）、手冊頁碼（一頁多條目，太粗）、或兩者都評。
- **時效**：延遲 + 早期預警、只報延遲、或不評。
- **彙總**：各項分列，或另給加權總分。

### Decision

1. **診斷**以 `component`（封閉詞彙，`examples/rag_starter_kit/vocabulary.json`）＋ `category` 自動評分；另評元件群組（部分正確）。`root_cause` / `actions` 保留給人工或 LLM 評。
2. **手冊引用**以事件碼評：hit@1、hit@3、MRR@10。
3. **時效**：延遲（相對第一個預期警報）與早期預警。以「最後一段連續正確」的起點計，中途猜錯的元件另計誤診——code review 實測，若以「第一筆正確」計，狂猜全部元件可以在 5/5 case 拿到早期預警。
4. 各項指標**分列，不合成總分**；誤報以次數計（同機組同元件 30 分鐘內算一次，與輸出頻率無關）。
5. **版本規則**：`CONTRACT_VERSION` 1.0；加欄位升次版本，改名 / 刪欄位 / 改語意升主版本。0.1 時存的標準答案欄位相同，匯出時只把 0.1 這個舊標籤轉成 1.0。
6. starter kit 只給受測端 `examples/rag_starter_kit/` 目錄；開發集附答案，正式評測用沒看過的資料包。

### Consequences

- 新增故障情境要先把 `component` / `category` 加進詞彙檔（次版本），`tests/test_rag_starter_kit.py` 會擋。
- v1 的故障庫元件與類別一對一，類別正確率暫時等於元件正確率；-08 加入感測器故障變體、干擾與健康 case 後才會分開。`nuisance` 預測 v1 不評分。
- 離線評分無法驗證時間因果；-06 WS 回放上線後才能以收到資料的時刻保證。

---

## DEC-20261022-01 — 健康機組偶發 T2 336：修物理的葉片同步誤差，PLC 規則照手冊不動、不當成 nuisance

**日期**：2026-10-22　**狀態**：accepted　**Decision maker**：Claude（WMOM-20261021-12，issue 授權在三個方向中定案）

### Context

-04 code review 實測：健康風場長時間（12 h）偶發 T2 336（葉片 1–3 差異 5 s > 1°）。-03-b 的守門測試只跑 2 h。issue 列了三個方向：修規則的延時判定、修物理、或當成真實的 nuisance 留著（標準答案已列在 `unattributed_events`，-08 可做成 nuisance case）。

查證結果：
- 延時判定已正確，5 s 子步要兩個連續越限樣本。
- 根因是健康葉片同步誤差太大：零點校正誤差 σ 0.12° 加上死區 0.18°、雜訊 0.08°，尾端碰到 1°。
- 手冊把「5 s > 1°」列為 T2 故障，處置是檢查變槳驅動、軸承、潤滑、I2t。

### Considered Options

- A. **放寬規則**（加長延時或提高設定值）：偏離手冊。學生會把不存在的設定值當成真實。
- B. **當成 nuisance**：健康風場長時間運轉會隨機跳 T2（3 機 12 h 就出現一次），現場不會接受這種機組；而且是無法控制的隨機事件，不是可出題的干擾。
- C. **修物理**：健康誤差縮到遠小於 1°，規則照手冊。

### Decision

1. 採 C。規則不動。
   - 葉片零點 σ 0.12 → 0.06°。
   - 起動 / 緊急順槳以外的伺服死區 0.18 → 0.10°、雜訊 0.08 → 0.04°。
   - 起動 / 緊急順槳維持較大的追蹤誤差（PLC 在這些狀態不判定）。
2. 只改 σ、不改抽樣次數，主 `_rng` 序列不位移。
3. 健康風場無訊號事件的守門測試加長（原始重現點 12 h ＋ 冬季夜間 / 夏季清晨各 6 h），另加 14 支機組種子 × 12 h 的葉片同步機制測試，判定方式與 PLC 相同（延時從第一個越限樣本起算）。

### Consequences

- 葉片差異類的 nuisance（例：編碼器雜訊、單葉片校正偏差）若要出題，由 -08 以有標註的情境注入，不靠健康機組的隨機尾端。
- 葉片角度 3 個 tag 與葉片揮舞彎矩 / DEL / 損傷的健康輸出改變；其餘 tag 逐位元不變。starter kit 已重產。
- `pitch_imbalance` 在中等嚴重度（0.7）跳機變晚（7.2 → 19.6 分鐘）；滿嚴重度與 0.8 不變。嚴重度 < 約 0.85 時是否跳機依機組而定（code review：0.7 固定 40 分鐘，30 支種子中 14 支不跳），-08 做難度變體時要考慮。
- 改變槳模型（死區、雜訊、速率差、零點）後要跑 `test_healthy_blade_sync.py`。

---

## DEC-20261022-02 — WebSocket 回放：單次直播 + 練習模式、出題端定速度、預測走同一條連線由伺服器蓋時間、受測端用回放 token

**日期**：2026-10-22　**狀態**：accepted　**Decision maker**：劉老師（四個選項，2026-10-22 確認）＋ Claude（WMOM-20261021-06 實作）

### Context

合約 v1 的資料包是檔案，時間因果只能靠受測端自律（合約 §6）。-06 要讓同一份情境依模擬時鐘即時播給學生的 RAG 助手，需要決定四件事：

- 評測時回放怎麼跑。
- 速度由誰定。
- 預測怎麼交。
- 受測端用什麼身分連線（DEC-20261021-03 已說不能沿用一般帳號）。

### Considered Options

- **回放方式**：
  - A. 單次直播＋練習模式。
  - B. 每次連線都從頭播：學生可以先連一次看完，再重連作答。
  - C. 可暫停的單次回放：思考時間無上限。
- **速度**：出題端開回放時固定，或受測端連線時指定（有人會選慢速換思考時間）。
- **預測**：走同一條 WS、伺服器蓋時間，或照 v1 交檔案（時間因果靠自律）。
- **身分**：出題端發回放 token，或幫學生開一般帳號（看得到情境名稱）。

### Decision

1. **回放方式採 A**：
   - `evaluation`：時鐘從第一次連線起算（`replay_runs.started_at`，重啟伺服器也接得上），所有連線共用同一個「現在」。不能暫停或倒帶。重連可補送過去的資料，時間不倒回。播完後不能再連。
   - `practice`：每次連線從頭播。
2. **速度**由出題端建回放時決定（0.1–10000×，預設 60），受測端不能改。
3. **預測走同一條 WS**：
   - `ts`＝伺服器收到時的回放模擬時間，受測端填的 `ts` / `pack_id` 不採用。
   - 情境結束（超過 `sim_end`）後收到的不收。評分規則本來就把這些算成對不到 case。
   - 評分端下載 `predictions.jsonl`，用同一個 `score.py` 評分。
4. **身分**：
   - 每個回放一組隨機 token（`wmr_…`），DB 只存 sha256，只能連這一個回放。
   - 可設到期、可撤銷。建回放 / 撤銷 / 下載預測要主管權限。
5. **合約升為 v1.1**（新增 §12，加訊息種類＝次版本）：資料包與標準答案格式不變。
6. **回放器 `server/replay.py` 給 -07 OPC UA server 共用**：訊息內容與資料包逐筆相同，同一套欄位、事件格式、10 分鐘統計算法。

### Consequences

- 受測端「收得慢或想得久」會反映在延遲上：伺服器照時鐘送，不等受測端。starter kit 的 `stream_client.py` 示範收與想分開。
- **回放存在風場 DB**：伺服器以目前風場查 token。出題端切換風場後，其他風場的回放連不上，切回來即可。
- **連線數上限是每個程序各算的**（每個回放 4 條）：目前是單一程序部署，夠用。
- **練習模式每次連線都存預測**：評分時要用 `connection` 只取一次連線。
- **正式評測與練習分開**：同一個情境同時有兩種模式（未撤銷）時，練習回放可以先看完正式評測的資料。code review 後由伺服器擋下：建回放時預設拒絕（409），`allow_overlap` 才放行。
- **試 token 不開始計時**：`?check=true` 只回報回放狀態。正式評測的時鐘從第一次正式連線起算。
- **正式評測的速度上限**：伺服器跟不上時，落後的時間會算在受測端頭上。所以限制「機組數 × 速度 ÷ 取樣週期 ≤ 1000 筆讀值 / 秒」，練習回放不受此限。


## DEC-20261022-03 — OPC UA server：回放與即時模擬兩種來源、全部 tag 掛上並標示合成、匿名唯讀、正式評測在 server 啟動時開播

**日期**：2026-10-22　**狀態**：accepted　**Decision maker**：劉老師（四個選項，2026-10-22 確認）＋ Claude（WMOM-20261021-07 實作）

### Context

真實 Z72 的資料走 Bachmann OPC（`shared/plc_clients/bachmann/opc_data_reader.py`，OPC DA）。-07 要讓學生的 RAG 助手用「接 PLC」的方式拿資料：節點路徑對齊真實的 item ID，資料來源是 -06 的回放器或即時模擬。舊的 `modules/monitoring/opcua_interface.py`（python-opcua、自訂路徑）不沿用。需要決定四件事：

- 資料來源。
- 真實 PLC 沒有的合成 tag 要不要掛。
- 連線身分。
- 正式評測什麼時候開始計時（OPC UA 沒有「第一次連線」可以當起點：client 隨時讀、讀幾次都可以）。

### Considered Options

- **來源**：回放＋即時模擬；只有回放；只有即時模擬。
- **合成 tag**：全部掛上並在節點說明標示；只掛真實 PLC 有的 tag（與 WS / 資料包不一致）。
- **身分**：匿名唯讀；帳號密碼（OPC UA 的 user token，學生要管帳號）。
- **開播**：出題端啟動 server 就開播；第一個 client 連上才開播（OPC UA 的 session 不帶回放 token，誰連上都會啟動時鐘）。

### Decision

1. **兩種來源**：
   - **回放**：`tools/opcua_server.py <db> <回放 id>` 綁一個 §12 的回放（`ScenarioReplay` + `ReplayClock`）。正式評測與 WS 共用 `replay_runs.started_at`：受測端用 OPC UA 讀資料、用 WS（`?stream=false`）送預測。
   - **即時模擬**：主程式以 `WMOM_OPCUA_ENABLE=true` 開啟，每秒寫入 simulator 的最新讀值與 PLC 狀態；選配，起不來只記警告。
2. **全部 tag 掛上**：欄位與資料包 / WS 同一組；`synthetic` tag 的節點說明寫明。另加真實讀取腳本會讀、模擬器沒有輸出的 `WSpeedNacAvg10m`：由 server 以 `WSpeedNac` 的 10 分鐘移動平均算出（節點說明寫 derived），讓真實讀取腳本的每個 item ID 都讀得到。
3. **匿名唯讀、不加密**：變數不可寫。給教室 / 實驗室網路用；不要開在公開網路上。
4. **正式評測在 server 啟動時開播**：節點建好、開始監聽後寫入開始時間；server 重啟接著播，播完不能再開。之後的 WS 連線加入同一個時鐘。
5. **事件碼陣列**（`ActiveAlarm` / `ActiveTrip1` / `ActiveTrip2`，SINT16[21]）依成立順序、空位 0。即時模擬由 `PlcProtection` 送事件時更新（`ActiveEventLists`），回放由事件流重建，兩邊同一套規則。
6. **合約升為 v1.2**（新增 §13；WS 加 `?stream=false` 與開播訊息的 `stream.data`）：資料包與標準答案格式不變。

### Consequences

- **OPC UA 只有目前值**：兩次讀取之間出現又消失的警報讀不到，速度越快越明顯（回放每 0.2 實際秒更新一次；60× 約 12 模擬秒）。要完整資料用 WS 或資料包。正式評測用 OPC UA 時，出題端要選受測端讀得過來的速度。
- **陣列排列是模擬的約定**：手冊沒寫真實 PLC 陣列怎麼排；接真實 PLC 時要再核對。
- **正式評測的計時從出題端啟動 server 起算**：受測端晚連就少看一段（與 WS 的「第一次連線」不同）。出題端要先確認受測端準備好再啟動。
- **一個 OPC UA server 播一個回放**：同時評測多組要開多個 server（不同埠）。
- **code review 後補上**：
  - 「匿名唯讀」要明確關掉 asyncua 的預設：只收匿名 identity token、關閉內建 admin、自訂唯讀 user manager（原本帳號填 admin 就能寫值、加節點）。
  - 練習回放用 WS `?stream=false` 時，時鐘改用 OPC UA server 這次開播時記下的起點（`replay_runs.started_at`，練習模式原本不用這一欄）；還沒播出時拒絕（4412）。
  - 即時模擬的 OPC UA 預設只聽 `127.0.0.1`；產生情境（批次）期間與批次留下的讀值不發布。批次注入的故障會留在即時模擬裡，所以有受測端連著時不要在同一個主程式出題。
  - 操作員復位（`PlcProtection.operator_reset`）解除鎖存時，每個解除的跳機另送 `trip_cleared`：事件流自己說清楚哪些跳機解除了，事件碼陣列就不必在復位時猜（維護清除故障的復位不解除鎖存）。批次路徑不會呼叫操作員復位，既有資料包不變。


## DEC-20261022-04 — 感測器故障情境：只改那支感測器的量測值、PLC 判定故障讀值；元件填被量測的元件、以類別區分

**日期**：2026-10-22　**狀態**：accepted　**Decision maker**：劉老師（四個選項，2026-10-22 確認）＋ Claude（WMOM-20261021-08-a 實作）

### Context

-08（難度與多樣性）拆成子項分 PR，劉老師選定先做「感測器故障 vs 真故障」。在這之前故障庫只有一個感測器故障（風向標 1 漂移），而且元件與類別一對一：只要從警報碼猜出元件，類別就自動對了，合約 §8 的「類別正確率」形同虛設。要做的事有三個衝突點：

- PLC 保護層判定的是**製程值**（感測器模型之前），感測器的雜訊 / 漂移不會觸發警報（DEC 於 -03-b 定下的守則）。
- Z72 手冊有兩類感測器相關事件：讀值錯但送出的是一般的溫度 / 壓力事件，以及「I/O 模組偵測到斷線」「編碼器角度超出範圍」的專屬故障碼。
- 標準答案的 `component` 該填感測器本身，還是被量測的元件。

### Considered Options

- **PLC 看什麼**：A. 只對被注入感測器故障的那支感測器改看量測值；B. PLC 全面改看感測器模型之後的值（最接近真實，但感測器雜訊幅度是為趨勢外觀調的，健康機組會誤報，需全面重調、既有資料全部改變）。
- **故障種類**（可複選）：讀值像真故障（漂移）；有專屬故障碼（斷線 / 編碼器）；卡值 / 斷線到極值。
- **component**：被量測的元件 + 類別區分；或感測器自成元件（詞彙多很多感測器 ID）。

### Decision

1. **PLC 只對注入的感測器改看量測值（A）**：`_get_fault_physics` 新增 `sensor_faults`（`offset` 漂移 / `pinned` 固定讀值），量測值同時給 PLC 與 SCADA；製程、控制與其他感測器完全不變（同種子下故障機組除了那支感測器，其他 tag 逐位元等於健康機組，測試會擋）。
2. **兩種感測器故障**：
   - 讀值像真故障：`main_bearing_temp_sensor_drift`（262 / 240，同主軸承磨耗）、`stator_temp_sensor_drift`（264 / 244，同定子繞組劣化）。物理上是 Pt100 量測回路接觸電阻增加，讀值比實際高、偏差逐漸變大。
   - 專屬故障碼：`main_bearing_temp_sensor_wire_break`（242）、`blade1_pitch_encoder_fault`（326，T2）、`yaw_brake_pressure_sensor_fault`（229）。PLC 依「讀值超出有效範圍」判定（手冊：I/O 模組偵測到斷線 / 角度超出範圍），失效的讀值不再參與越限判定（不連帶送出溫度過高、壓力過低、葉片差異）。
3. **component 填被量測的元件**，`category` 填 `sensor_fault`：同一元件會有真故障與感測器故障兩種答案，警報碼還可能相同，類別正確率才有意義（合約 §9 對照表）。
4. **補兩個真實 tag**：`WGEN_GnBrgTmp2`、`WGEN_GnStaTmp2`（真實 Z72 PLC 有，原本模擬器沒有輸出）。沒有第二支感測器，讀值像真故障的感測器故障就沒有公平的分辨依據；PLC 同時補上它們的規則（263 / 241 / 243、265 / 245 / 251）。真故障要「兩支一起變」：主軸承磨耗時軸承 2 升溫約三成、定子繞組劣化時定子 1 / 2 一起升（預期碼補上 265 / 245）。新感測器的隨機數走獨立的 `_rtd_rng`，既有 tag 的健康輸出逐位元不變。
5. **合約升 v1.3**（加欄位）；starter kit 加第四個範例資料包（同樣的 262 / 240，一台真故障、一台感測器故障）。

### Consequences

- 健康機組既有的 116 個 tag 逐位元不變（code review 後新感測器改用獨立的 `_rtd_rng`，原本走 `_aux_rng` 會讓風向標 2 與電網電壓的雜訊位移）；既有情境的事件不變。主軸承磨耗多一個 key signal（軸承溫度 2）、定子繞組劣化多兩個預期碼（265 / 245）。
- 資料包多兩欄（102 個 tag），讀取端照合約忽略不認得的欄位即可；範例資料包的資料檔全部重產。
- 斷線 / 編碼器故障的讀值（850 °C、−62.5 bar、135°）與有效範圍是模擬假設，手冊沒有數字；寫在 `TurbineSpec` 與標準答案的 `simulation_notes`。
- 斷線類故障在嚴重度到 0.5 時一次發生、之前完全看不到（沒有早期預警的空間，難度 easy）；間歇性斷線留給後續子項。
- 基準助手加一條規則：警報文字點名感測器才判 `sensor_fault`。專屬碼一看就懂，真正的難題留在讀值像真故障的那一類。

---

## DEC-20261022-05 — 正式評測要伺服器強制登入、批次生成移到背景執行緒、正式評測總速率上限、手冊保真度另開 issue

**日期**：2026-10-22　**狀態**：accepted　**Decision maker**：劉老師（四個選項，2026-10-22 確認）＋ Claude（WMOM-20261022-01 全面檢查）

### Context

-08 其餘子項前，劉老師要求對 EPIC-DS 至今的程式做一次整體程式碼檢查與功能驗證。三路 code review 與真伺服器的端到端驗證找到四個需要決策的問題：

1. **盲測靠登入保護，但預設沒開**：答案卷與評分端資料包用永遠強制的 `require_roles`，但情境清單 / 詳情（含 `config.fault_schedule`）、history（含注入標記與模型內部量）、盲測版資料包、刪除情境都跟著 `WMOM_AUTH_ENFORCE` 過渡開關。預設沒開、伺服器又聽 `0.0.0.0`：受測端拿著回放 token、甚至什麼都不帶，就能從 API 讀到故障排程，或在正式評測開播前下載資料包。
2. **產生情境會卡住整台伺服器**：`generate-bulk` 是 `async def` 卻同步跑整段物理模擬。實測 2 h 情境 31.5 s 內查狀態的請求等了 31.4 s、正在播的正式評測回放 31.6 s 沒有訊息；情境越長卡越久，超過 WS 的 20 s ping 就斷線，落後的時間算在受測端頭上。
3. **正式評測的速度上限是逐個回放算的**：6 組各 700×（各自在上限內）時伺服器落後 p50 7.6 s / p95 13.7 s；預設 60× 沒問題。
4. **手冊保真度**：Appendix D 的延遲 / 範圍（液壓 30 s、風向標差異 60 s、編碼器 −5–95°、機艙 45 °C、Pt100 10 s 濾波）與模擬器不同；自動重啟被擋時真實 Z72 送 A039；`yaw_sensor_drift` 在部分機組永遠不跳 233。修了都會改變資料的時間點。

### Considered Options

1. 盲測登入：A. 正式評測強制開登入（REST / CLI / OPC UA CLI 都擋）；B. 情境端點一律要登入（不受過渡開關影響）；C. 只寫文件。
2. 生成卡頓：A. 移到背景執行緒＋同時一個批次＋批次期間改模擬器的請求 409；B. 評測中禁止生成＋文件；C. 開新 issue。
3. 評測容量：A. 建立正式評測時檢查所有未結束正式評測的總速率；B. 開播時全域預算（新關閉碼）；C. 只寫文件。
4. 保真度：A. 開新 issue 下一步做；B. 這次一起做；C. 只修 yaw drift。

### Decision

1. **正式評測要伺服器強制登入（A）**：沒開 `WMOM_AUTH_ENFORCE` 時，`POST /api/scenarios/{id}/replay-runs`（mode=evaluation）回 409、`tools/replay_runs.py create`（預設就是 evaluation）與 `tools/opcua_server.py`（evaluation 回放）結束碼 1，不開播。練習回放照建，REST 回應帶 `warning`、CLI 印提醒。CLI 讀同一個環境變數：與伺服器用同一套設定執行。
2. **批次生成移到背景執行緒（A）**：`generate-bulk` 與 `test-plans/run` 以 `asyncio.to_thread` 執行；`server/batch_state.py` 同時只允許一個批次（第二個 409，佔位與釋放都在批次執行緒裡）；批次期間會改到模擬器的 16 個路由回 409（切換來源 / 風場、風況 / 電網 / 模擬設定、控制指令、注入 / 清除故障、刪除情境、儲存維護），測試鎖住清單。
3. **建立正式評測時檢查總速率（A）**：這一個加上所有未結束（還沒開播 / 進行中）的正式評測，機組數 × 速度 ÷ 取樣週期的總和不能超過 1000 筆 / 秒，超過回 409（CLI 結束碼 1）並列出佔用的回放。練習回放不計。
4. **手冊保真度另開 issue（A）**：WMOM-20261022-02，排在 -08 其餘子項前面，一起重建範例資料包、重量時間點。

### Consequences

- 正式評測的部署前提變成「伺服器開 `WMOM_AUTH_ENFORCE=true`」（合約 §12.1、§13.1、starter kit README 出題端說明）。過渡模式（沒開）下仍能做練習回放與展示。
- 生成期間伺服器照常回應：前端在生成時操作控制 / 故障注入會收到 409（原本是排隊等生成結束）；批次與即時模擬仍共用模型，「有受測端連著即時 OPC UA 時不要在同一個主程式產生考題」的提醒保留。
- 總速率檢查偏保守：還沒開播的正式評測也算（token 預設 7 天有效），提前一週建好所有組別的評測會被擋。做法是考前再建、或縮短 `expires_in_hours`、撤銷沒在用的評測。檢查只看目前風場的 DB（正式評測進行中不能切換風場）。
- 合約版本不變（1.3）：沒有新增或改名的欄位 / 關閉碼，只是出題端的建立條件與說明。

---

## DEC-20261023-01 — 手冊 Appendix C / D 衝突以 D 為準、自動重啟被封鎖送 A039、拿掉全域每小時啟動上限

**日期**：2026-10-23　**狀態**：accepted　**Decision maker**：劉老師（三個選項，2026-10-23 確認）＋ Claude（WMOM-20261022-02 手冊保真度）

### Context

WMOM-20261022-02 對照手冊修模擬器時，遇到三個需要決策的問題：

1. **手冊自相矛盾**：Appendix C（事件清單的說明文字）與 Appendix D（「控制系統最重要的可設定值及其實際設定」）有三處數字不同——液壓壓力低 260：C 寫 < 180 bar（額定 200 −10 %），D 寫 `SDHyPres_L` 170 bar、`SDHyPres_H` 190 bar 解除；切出陣風：C 寫 5 秒平均 > 35 m/s，D 寫 `SDVwind_hi_3s` 3 秒；233 的風速條件：C 寫 10 分鐘平均 > 4.5 m/s，D 的參數名是 `SDVw60sWndVnDiscr`（60 秒）。另外 §11.3 說每個跳機的出廠重啟設定是 0，Appendix C 的 Max #/hr 欄卻列了 1、2、5、10。
2. **自動重啟被封鎖怎麼表示**：手冊 §8.3 / Appendix C：同一跳機碼一小時內超過上限時 PLC 送 A 級 **A039「Auto restart blocked」**（xlsx 事件清單沒有這個碼）。模擬器送自創的 `restart_blocked` 事件並帶跳機碼，這個值已寫進合約 v1.0 的 `event_type`。
3. **物理層的全域上限**：digiWT 留下的「每小時最多啟動 3 次」把所有啟動都算進去，連低風速正常起停也算；手冊沒有這個機制（§6.8.1、§8.3、§11.3 都只講每個跳機碼各自的上限）。實測風速在切入風速附近擺動時，健康機組 3 小時內有 1–2.5 小時被卡在待機、而且沒有任何事件；物理層保護停機（超速、電網）也只靠它擋重複重啟、同樣沒事件。

### Considered Options

1. 手冊衝突：A. 以 Appendix D 為準（PLC 實際設定值）；B. C 有寫就以 C 為準，只有 C 沒寫的才用 D。
2. 重啟封鎖：A. 改送 A039 `alarm_raised` / `alarm_cleared`、不再送 `restart_blocked`（合約升 v1.4、列舉值保留）；B. 兩個都送。
3. 全域上限：A. 拿掉，物理層保護停機也照目錄每碼計數、超過送 A039；B. 保留，擋下時補送 A039。

### Decision

1. **以 Appendix D 為準（A）**：液壓 260 / 228 為 170 / 150 bar、> 190 bar 解除、延時 30 s（`SDYwHyBrkTm`）；切出陣風 3 s 平均；233 延時 60 s（`SDWndVnDiscrTm`）、風速條件 60 s 平均；機艙 273 為 45 °C（`SDNacTmp_H`，原假設值 46）；PLC 的溫度（Pt100）以 10 s 時間常數濾波後判定（`CDTauPT100`，取代原本假設的 10 s / 5 s 事件延時）；編碼器有效範圍 −5–95°（0–90° ± `SDVaneLimitTolerance` 5°）。重啟上限沿用 Appendix C 的 Max #/hr（§11.3 的 0 是出廠預設，Appendix C 是本機組的設定）。
2. **改送 A039（A）**：跳機碼超過每小時上限時保持鎖存、送 A039 `alarm_raised`（多個碼封鎖只送一次），機組進 SHUTDOWN（TurSt 1）；操作員復位（事件 008）與維護清除時送 `alarm_cleared`。A039 收進警報目錄（`manual_only`，315 碼）。合約 v1.4：`restart_blocked` 不再送出，列舉值保留給舊資料包。
3. **拿掉全域上限（A）**：`TurbineSpec.max_restarts_per_hour` 與物理層的啟動時間戳刪除；物理層保護停機的跳機與訊號判定的跳機共用每碼計數，超過上限時在跳機當下封鎖並送 A039。

### Consequences

- 事件時間點與 v1.3 不同（液壓多 30 s、233 多 60 s；溫度緩升時 10 s 濾波約落後 10 s，與原本 10 s / 5 s 的延時相近），範例資料包重建；RAG 查 Appendix C 會看到 180 bar / 5 秒 / 10 分鐘，與資料差幾 bar / 幾秒——合約 §10 註明。
- 風速在切入風速附近的時段，健康機組會比以前多起停幾次（不再被卡在待機）；重複的超速 / 電網跳機現在看得到 A039。
- 233 的風速條件是判定窗（Appendix D「enable wind vane discrepancy」）：風速掉到 4.5 m/s 以下只禁止新的成立，已鎖存的跳機不解除（code review S2：原本把差異訊號歸零，跳機後風速低谷會解除、風回來再跳，停機中的機組還會出現 Shutdown → Normal Stop）。
- 每小時重啟上限的判定時點：訊號判定的跳機在條件解除（要重啟）時、以解除時刻往前一小時計；物理層保護停機在跳機當下判定（條件由物理層處理）。同一個碼不分成因算同一種跳機（手冊「identical trips」以事件碼計）：021 伴隨所有變頻器跳機，一小時內先有冷卻水溫跳機（437 + 021）再有電網欠壓（481 + 021），第二次的 021 就會封鎖、送 A039。
- 命名情境開頭的乾淨機組也清每小時跳機計數（`PlcProtection.clear_trip_counts`，不動 RNG、不送事件）：Live 一小時內自動恢復過的跳機不能讓情境的第一次同碼跳機就送 A039（code review S1）。
- 既有風場存在 farms.db 的 turbine_spec 是建立當時完整的 `to_dict()`，會把舊的 180 bar 帶回來：載入風場改用 `TurbineSpec.from_farm_dict`，PLC 設定值一律用程式的值（spec 更新 API 仍可明確修改）。
- 仍未對上手冊、留給後續：236 塔架加速度（手冊 `SDNacVibR_HH` 1.75 m/s² 看合成加速度 `VibMsNacR`，模型的機艙振動是速度 mm/s，沿用假設值 7 mm/s）；Appendix D 的暴風等級（`SDVwind_Storm_10m` 27 m/s → 204 Storm park）沒有模擬。

---

## DEC-20261023-02 — 誤報 / 健康負樣本：干擾來源、nuisance case 標準答案、加新指標不改舊規則

**日期**：2026-10-23　**狀態**：accepted　**Decision maker**：劉老師（-08 先做誤報 / 健康負樣本，三組選項，2026-10-23 確認）＋ Claude（WMOM-20261021-08-b）

### Context

到 v1.4 為止，標準答案只有故障 case：評分只看「故障有沒有被診斷出來」，助手看到警報就報故障也不會被扣分（範例資料包裡健康機組幾乎沒有警報 / 跳機，`nuisance` 預測只統計不評分）。真實風場有大量不是故障的警報 / 跳機——電網擾動、風向變化快的偏航逾時、Pt100 鬆線（手冊 §11.3 點名的 nuisance trips）、暴風切出——RAG 維修助手要能說「這不是故障」，評分也要能量測誤報。

### Considered Options

1. 干擾來源：電網擾動（全場同時）、手冊 §11.3 的 nuisance 跳機、環境性停機的標記、全健康負樣本資料包——四個都做，或只做其中幾個。
2. 標準答案格式：A. nuisance case（與故障 case 同一個清單、`category: nuisance`，時間窗 + 成因）；B. 只把事件標成「無故障」（沒有 case）。
3. 評分：A. 加新指標、不改舊規則（故障指標只算故障 case）；B. 把干擾併進既有指標（例：偵測率分母含 nuisance case）。

### Decision

1. **四個都做**：
   - 風場層級事件（`simulator/farm_events.py`，`generate-bulk` 的 `farm_events`）：電網電壓驟降、電網頻率越界——走既有的電網保護 / LVRT，全場發電中的機組幾乎同時跳 482 / 481 / 489 + 021、恢復後自動重啟；風向快速變化——風向以 180 s 週期正弦擺動，偏航追不上而逾時。
   - 新 PLC 規則**偏航逾時 223**（Appendix D `SDYawTmOutFact` / `SDYawTmOutOffs`：對風開始時允許「factor × 偏航誤差 ÷ 偏航速度 + offset」秒，5 / 0 s，誤差下限 2°；解纜不算）。健康偏航實測最長 55 s，實際用時最多約為「誤差 ÷ 偏航速度」的 1.4 倍、允許時間的 0.29，factor 5 有足夠裕度。
   - 新 nuisance 情境 `main_bearing_temp_loose_contact`（手冊 §11.3「a loose wire in a generator Pt100」）：注入後 5–20 分鐘第一次、之後每 15–45 分鐘瞬斷 10–30 s，瞬斷時讀值同斷線（PLC 送 242 跳機），接回後自動重啟；不鎖機組（`FaultEngine.mark_tripped` 對 nuisance 不轉 tripped）。排程用自己的 RNG stream（`_contact_rng`），不動既有 RNG。
   - 環境性停機：沒有注入、模擬自己產生的事件（暴風切出 201、極端氣溫 256 / 273）由標準答案歸類。
   - 範例資料包 05（健康負樣本）：沒有故障，電網電壓驟降、頻率越界、風向快速變化、一台 Pt100 接點鬆動。
2. **nuisance case（A）**：`category: "nuisance"`、`nuisance_cause`（`grid_disturbance` / `wind_direction_change` / `loose_contact` / `environment`，詞彙加 `nuisance_causes`）、時間窗 `window_end_ts`（風場事件 / 環境性：最後一個相關事件 + 30 分鐘）、`farm_event_id`；頂層 `farm_events`。風場事件每台有反應的機組一個 case；注入的 nuisance 每次一個；其餘沒被認領、發生在沒有故障的機組（或故障開始前）的事件歸成環境性 case（同機組 30 分鐘內一群）。`healthy_turbines` 改為「沒有故障 case」；`unattributed_events` 只剩故障連帶事件。合約 v1.5（加欄位）。
3. **加新指標、不改舊規則（A）**：故障指標（偵測率…誤診）只算故障 case，規則不變；新增干擾辨識率（時間窗內有 `nuisance` 預測）、把干擾當故障（時間窗內的誤報）、誤報率（誤報次數 ÷ 沒有故障的機組時數 × 100）。`nuisance` 預測仍不撤回之前的故障診斷。

### Consequences

- 舊答案（v1.4 以前）照常評分：沒有 `window_end_ts` 一律到 `sim_end`、沒有 nuisance case。範例資料包 01–04 的資料逐位元不變（新規則 223 在這些情境不觸發），只有 manifest / 答案的版本與新欄位。
- 基準助手加了「同一個碼 60 秒內已在另一台機組出現 → nuisance」：在 05 上認出 12 個干擾中的 8 個，誤報 4 次（全場一起跳的第一台、Pt100 鬆線），誤報率 5.46 / 100 機組小時——學生的助手要從事件模式（全場同時、反覆短暫、讀值立刻恢復）與環境量（電壓、頻率、風向）分辨。
- 狂報故障會拉高誤報率與「把干擾當故障」；狂報 `nuisance` 拿得到辨識率，但干擾判定的準確率（落空的筆數）會很低、故障期間的 `nuisance` 也會列出（code review S4 補上準確率；這些都是並列的指標，不扣分）。
- 合約維持次版本 1.5（code review S3 提出語意變更要升主版本）：`nuisance` 從 v1.0 起就是保留的答案類別，`healthy_turbines` / `unattributed_events` 的定義文字不變；合約 §2 註明自己寫評分程式的人要把 `nuisance` case 分開。
- code review 修正：同種風場事件相隔不到寬限時，事件歸最晚開始的那個（S1）；事件進行中到結束後 10 分鐘的任何碼都歸事件、事件自己的碼到結束後 30 分鐘不讓故障 case 認領（S2；Codex review 指出保留窗原本只有 10 分鐘、與歸屬窗不一致）；A039 跟著前一次跳機歸屬（S6）。Codex review 另修：比物理子步短的事件以重疊判定照樣套用；電網事件只覆寫自己的量（recovery 等 profile 不被打斷）；Pt100 鬆線的瞬斷排程跟著注入編號（`ActiveFault.instance_id`），連續情境再注入重新起算；offset 0 的風場事件納入情境時間窗下界。S2 的重現（頻率 +1 Hz 未跳機時冷卻水溫一分鐘升 18 °C、送 420）根因在物理：下垂降載少送出的功率被算成變頻器發熱——改為只算效率損失（沒有降載時為 0，健康資料逐位元不變）。
- 模擬假設（合約 §10）：風場事件全場同時、同一個量；風向擺動是規則的正弦；Pt100 瞬斷時間隨機但與嚴重度無關。
- 留給後續：故障庫擴充；多重故障 + 早期徵兆（同機組多個 case 的評分規則要先定）；Appendix D 的暴風等級（204 Storm park）仍未模擬。

---

## DEC-20261023-03 — 故障庫擴充：四組新故障、刪除齒輪箱 alias、冷卻水導電度 tag 改正

**日期**：2026-10-23　**狀態**：accepted　**Decision maker**：劉老師（四組選項，2026-10-23 確認）＋ Claude（WMOM-20261021-08-c）

### Context

故障庫 17 個情境（11 真故障 / 5 感測器故障 / 1 nuisance），Z72 真實清單 315 碼。另有三個「有物理但不能注入」的 alias（`gearbox_overheat` / `pitch_motor_fault` / `yaw_misalignment`）。業界故障統計裡變槳系統、變頻器 / 冷卻、感測器是最常見的停機來源；RAG 維修助手也該遇到「沒有任何警報、只能從趨勢看出來」的劣化。調查另發現 `WCNV_IGCTWtrCond`（真實 tag，ABB 冷卻水導電度）一直被算成冷卻水流量比 0–1。

### Considered Options

1. 新增哪些故障：變槳驅動劣化（381 → 367）、冷卻水泵磨耗（422 → 439）、量測感測器三種（029 / 230 / 231）、靜態偏航失準（無警報）——可複選。
2. `gearbox_overheat`：A. 刪除（Z72 直驅、目錄與手冊沒有齒輪箱事件）；B. 保留但註明非 Z72。
3. `WCNV_IGCTWtrCond`：A. 改成導電度並加去離子劣化故障（423 → 440）；B. 這次不動、另開 issue。
4. 範例資料包：A. 加 06；B. 不加。

### Decision

1. **四組全做**，共 7 個新情境（17 → 24）：
   - `pitch_motor_fault`（升格 alias，物理改寫）：葉片 1 變槳軸承 / 齒輪摩擦增加 → 直流變槳馬達電流（新增真實 tag `WROT_PtMotCurBl1-3`，模型：通電時基本電流＋隨推力的氣動扭矩＋隨變槳速度）→ 驅動器 I2t 限流 A381 → 手冊 Appendix D 的過載限值（`CDOvrCurr10m` 18 A / `60s` 20 A / `5s` 22 A）→ T1 367。
   - `converter_cooling_pump_wear`：泵葉輪磨耗 → 流量（不是 tag，PLC 的內部輸入）與迴路壓力下降 → A422（< 90 %）→ A432 → T1 439 + 021（< 75 %）；水溫高幾度。
   - `cooling_water_deionizer_exhausted`：導電度上升 → A423（> 0.5 µS/cm）→ T1 440 + 021（> 1.0）。
   - 感測器故障：`rotor_speed_sensor_fault`（編碼器接線鬆動、讀值偏低 → 與變頻器轉速差 > 10 % → 029）、`anemometer_fault`（軸承磨耗讀值偏低 → 嚴重度 0.8 卡死讀 0 → 轉子 > 6.5 rpm 時 < 0.5 m/s 持續 60 s → 230，Appendix D）、`wind_vane1_stuck`（讀值凍結 → 1 分鐘平均風速 > 4 m/s 時凍結 60 s → 231）。
   - `yaw_misalignment`（升格 alias，物理改寫）：兩支風向標一起偏 16°，控制器照風向標對風 → 轉子長期偏離、發電 ∝ cos³、側向彎矩與 3P 振動增加，**沒有任何警報**。
2. **刪除 `gearbox_overheat`（A）**：物理、振動頻譜分支、傳動鏈的 `gearbox_overheat_severity` 參數一併拿掉；齒輪箱合成 tag 照舊（健康輸出逐位元不變）。
3. **導電度（A）**：`WCNV_IGCTWtrCond` 改為導電度 µS/cm（每台 0.15–0.25、約 +2 %/°C，新 RNG stream 抽每台基準）；感測器模型的抽樣次數不變，其他 tag 健康輸出逐位元不變。合約升次版本 1.6（tag 字典的單位 / 說明跟著變）。
4. **加範例資料包 06（A）**：8 台、5 h、額定風況，七個新故障各一台、一台健康。

### Consequences

- PLC 新規則 029 / 230 / 231 / 232 / 367–369 / 381–383 / 422 / 439 / 423 / 440（+021）。健康機組不觸發（`test_fault_threshold_reach.py` 健康上限、`test_plc_integration.py` 健康風場、`test_healthy_blade_sync.py` 12 h）。
- **029 的比對基準**：模擬的 `WGEN_GnSpd` 是傳動鏈模型的發電機轉速，與轉子轉速有差異——第一版直接比，健康機組併網後 24 秒就跳 029；code review 另查到有的健康機組長期偏離（範例資料包 05 / 06 有機組平均 54–59 rpm 對轉子 22 rpm，既有問題，另開 WMOM-20261023-01）。直驅 PMSG 的變頻器由電氣頻率算轉速＝轉子實際轉速，所以 PLC 比對用「變頻器轉速」（不是 SCADA tag 的內部輸入，沒給就不判定）；029 的處置建議改看轉速讀值與發電 / 風速的關係，不叫人比 `WGEN_GnSpd`。
- **231 的凍結判定看 I/O 讀值（含量測雜訊）**：其他 PLC 規則判製程值；製程的風向誤差在固定風向下本來就不變，判製程值會讓健康機組誤跳。感測器模型的卡值事件最長 20 s，到不了 60 s。
- **偏航失準的發電損失套在功率上**：若改成減少轉子面對的風，本模型全載時的變槳依風速決定，反而會少變槳、多發電。
- 沒有警報的故障：`expected_alarm_codes` 為空、`manual_coverage` 新增 `none`、first_alarm / trip 為 null；評分既有規則（不評延遲、偵測到算早期預警）不變。`test_fault_alarm_codes.py` 的「每個情境都有跳機碼」改為允許明列的無警報情境。
- 元件詞彙加 `rotor_speed_sensor`、`nacelle_anemometer`、`wind_vane_alignment`；`yaw` 群組名稱改為「偏航系統與機艙測風儀器」。風速計 / 轉速感測器 / 風向標的感測器故障沒有對應的真故障元件（量測儀器本身就是元件）。
- 模擬假設（各情境的 `simulation_notes`）：變槳馬達電流模型、I2t 連續電流 14 A / 60 s、冷卻水流量 90 % / 75 %、導電度 0.5 / 1.0 µS/cm 與健康值、029 的最低轉速與延時；I2t 限流不會讓葉片變慢；感測器故障時模擬的控制器（偏航、切入 / 切出）仍依實際值運作。
- 留給後續：多重故障 + 早期徵兆（同機組多個 case 的評分規則要先定）。

---

## DEC-20261025-01 — 傳動鏈扭轉改以子步積分：修直驅 `WGEN_GnSpd` 偏離（批次資料改變）

**日期**：2026-10-25　**狀態**：accepted　**Decision maker**：Claude（WMOM-20261023-01；劉老師指定修此 issue）

### Context

-08-c 的 code review 查到範例資料包裡有健康機組的 `WGEN_GnSpd` 長期是轉子轉速的 2.5–2.7 倍（或接近 0）。Z72 是直驅，兩者剛性連接。調查結果不是模型的穩態偏差，而是**數值不穩定**：傳動鏈的 LSS 扭轉＋發電機轉速是二階阻尼振盪系統（週期約 36 s），顯式 Euler 在批次的物理子步 dt 5 s（`engine._MAX_PHYSICS_DT`）對剛性 / 阻尼抽得高的個體（`drivetrain_stiffness_scale` ≳ 1.09）放大誤差，被 `max(0, …)` 與轉子夾住後鎖進二週期振盪（gen 0 ↔ 60.3 rpm、rotor 22.9 ↔ 22.3）；資料包每 10 s 取樣（每兩個子步）剛好看到同一相位，才像穩定的偏離。dt 1 s（Live）所有種子都穩定。

### Considered Options

1. **模型內子步積分（採用）**：`DrivetrainModel.step` 把扭轉（LSS / HSS）＋發電機轉速以 ≤ 1 s 的子步積分，步內的輸入（氣動轉速、煞車扭矩、嚙合激振）不變。dt ≤ 1 s 子步數為 1、算式逐位元相同。
2. 把 `_MAX_PHYSICS_DT` 降到 1 s：批次慢 5 倍，所有模型都跟著變。
3. 改成隱式 / 解析離散化：dt 1 s 的健康輸出也會變，Live 與既有校準都要重驗。

### Decision

選 1。dt 1 s 的健康輸出逐位元不變（seed 1 / 7 / 42 × 1500 步比對）；dt 5 s 的健康輸出改變——發電機轉速進電氣頻率、功率與熱模型，所以**批次生成的資料全部改變**（所有種子，不只出問題的三個）。範例資料包 01–06 重建。029 的比對基準維持變頻器轉速（-08-c 的設計，直驅＝轉子實際轉速），不改回 `WGEN_GnSpd`。

### Consequences

- 守門：`tests/physics/test_invariants.py` 14 個種子 × dt 2.5 / 5 s 每一步 |gen − rotor| / rotor < 1 %（舊程式 6 組失敗）；`DrivetrainModel` 在個體差異上限（剛性 +16 % / 阻尼 +18 %）dt 5 s 收斂。
- 守則：物理積分的穩定性要在批次子步 dt 5 s 驗證，二階 / 剛性的動態在模型內切子步，不放寬 `_MAX_PHYSICS_DT`。
- 齒輪箱 spec（非 Z72 的 `vestas_v90_3mw`）在 dt 5 s 更糟：預設個體差異就在 28–98 rpm 振盪、剛性 / 阻尼上限時發散到 1e72，批次路徑的非 Z72 機型資料此前是壞的；修正後 h 1 s 的放大率 0.77–0.84，整個個體差異範圍都穩定（守門測試三組 scale）。
- 順帶修到一個被掩蓋的 bug：齒輪箱機型的併網門檻要求發電機機械頻率在電網頻率 ±0.25 Hz 內，V90 轉子到上限 16.7 rpm 是 58.2 Hz 對 60 Hz 永遠併不上，舊程式只因數值不穩定讓轉速掃過那個窗才碰巧併網。改為 DFIG 轉差帶（電網頻率的 0.7–1.3 倍）。Z72 走直驅分支，不受影響。
- 停機時的減速夾值改為每個子步套一次：dt 5 s 的停機暫態不再一步歸零（只影響 dt > 1 s 的批次資料）。`_TORSION_MAX_DT` 的子步數沒有上限，依賴 `engine._MAX_PHYSICS_DT` = 5 s 的上限。
- 既有以批次資料產生的情境 / 正式評測若要與新程式比對，須重新生成。

---

## DEC-20261026-01 — 同機組多重故障的評分規則與早期徵兆題（合約 v1.7）

**日期**：2026-10-26　**狀態**：accepted　**Decision maker**：Claude 建議、劉老師授權（「同一台機組多個 case 的評分規則請你建議就好」，2026-10-26）

### Context

-08 最後一個子項：多重故障＋早期徵兆。評分（合約 §8）到 v1.6 的歸屬規則是「預測先對同元件的 case，否則歸最晚開始的 case」，每個 case 以最後一筆評；同機組有 k 個 case 時「每個元件猜一遍」可拿到每個 case 的元件分、誤報 0（EPIC-DS 文件早就記下這個漏洞）。另外沒有「故障停在門檻下」的出題方式：早期徵兆只能靠情境在警報前結束。

### Considered Options

1. **維持歸屬規則、加「診斷精確率」指標（採用）**：對到 case 的診斷裡元件正確的比例。單 case 時等於 1 − 誤診比例；多 case 時專抓亂槍打鳥。既有的單 case 成績與基準數字不變。
2. 猜錯的元件記到**每個**進行中的 case：會讓先前已對的 case 的「最後一筆」變成錯的，助手就不能對一台機組維持多條診斷；與「每個 case 以最後一筆評」衝突。
3. 把機組的診斷當成一個集合評（集合精確率 / 召回率）：要定義「集合在什麼時候算定案」，對學生太複雜。

早期徵兆：排程加 `max_severity`（嚴重度上限，預設 1.0）——故障停在門檻之下、訊號已偏離但不出警報；標準答案記在 `injection.max_severity`。替代方案「用很慢的 severity_rate 讓情境在警報前結束」不保證（風況不同警報時點就不同）。

### Decision

- 歸屬規則加一級：元件相同 → 同群組 → 最晚開始的（基準助手只猜到「變槳系統」時，診斷要歸到變槳的 case，不是同機組較晚開始的導電度 case）；新指標 `diagnosis_precision`；早期徵兆 case（開始時間已知、有預期碼、情境內沒到警報；`pre_existing` 不算）在報告分開列 `early_sign_cases` / `early_sign_detected`，元件診斷正確＝早期預警（既有規則）、不評延遲、手冊引用照常。它與 v1.6 的「沒有警報的故障」（預期碼為空）不同。
- 同機組多個 case 預期同一個碼時，標準答案把碼歸給每一個（維持 -08-a 的規則）；範例資料包不放共用碼的組合（`tools/build_rag_starter_kit.py::check_pack` 擋）。沒有故障的機組時數重疊窗只扣一次（維持）。
- `max_severity` 走排程（`fault_schedule`）與 `FaultEngine.inject`，(0, 1] 且不小於 `initial_severity`（> 1 的 `initial_severity` 照舊夾到 1）；跳機後嚴重度凍結的規則不變。Live 的 `POST /api/faults/inject` 不開 `maxSeverity`（早期徵兆是出題用，走批次）。
- 合約升 1.7（加欄位、加指標）；範例資料包 07（6 台、6 h、額定風況）：WT001 主軸承磨耗壓在 0.5（262 約 0.88 才出）＋ 90 分鐘後冷卻水泵磨耗（會跳機）、WT002 偏航失準（沒有警報）＋ 2 h 後液壓洩漏、WT003 只有定子劣化早期徵兆（上限 0.6）、WT004 變槳驅動過載（會跳機）＋ 導電度上升壓在 0.3（423 約 0.45 才出）、WT005 只有 Pt100 漂移早期徵兆（上限 0.5）、WT006 健康。額定風速下各故障出警報的嚴重度實測後再定上限。

### Consequences

- 基準助手在 07 只抓得到 3 / 8 個 case（只看警報），早期徵兆 0 個——這正是專題要超越的地方。
- 既有 01–06 的評分與基準數字不變（精確率只是多報一欄）。
- 早期徵兆 case 的 `first_alarm_ts` 為 null：kit 測試改為「`max_severity` < 1 的 case 不得出警報」，其餘仍要求在情境內出警報。
- 留給後續：同機組兩個故障共用碼時的歸屬仍是「都記」；跳機後第二個故障的訊號在停機狀態下未必能發展（範例以「會跳機的 ＋ 不會出警報的」搭配避開）。

---

## DEC-20261125-01 — 重新定位為「仿真運維風場」：持續運轉、機率式故障、運維閉環、對外資料 API；出發前助理保留為工單上的功能

**日期**：2026-11-25　**狀態**：accepted　**Decision maker**：劉老師（定位六項、保留出發前助理）；開發順序、兩個預設值、外部身分的形式由 Claude 建議，劉老師 2026-11-25 回覆「同意你的規劃」確認
**延續 / 調整**：DEC-20261021-01——商業時程與真實風場介接仍暫緩；主線由 EPIC-DS（已完成）換成 EPIC-SF

### Context

- 2026-11-23 的「風場運維出發前助理可行性企劃」審查版 v0.1 提出：出發前把監控、警報、維修紀錄整理成準備卡（例行巡檢、故障出勤兩張）。11-24 審查的主要疑慮是階段 B 需要授權的真實案例，而真實風場資料正是 M6 卡住的同一個瓶頸（`work-logs/2026-11/2026-11-24-predeparture-assistant-review.md`）。
- 2026-11-25 劉老師提出重新定位，六項：
  1. 擬真的風場風機系統，具備真實物理模型，依不同風況環境輸入產生愈來愈擬真的資料。
  2. 啟動後像真實風場持續運轉、持續產生資料；資料循環保存（一個月到半年，視空間盡量拉長），到期移除最舊的。
  3. 可設定故障觸發的方式、機率、種類，以及設備故障與耗損，觸發帶警報代碼的警報。
  4. 可派工單排除故障、做定檢，並與停機、發電、可用率連動計算。
  5. 成本計算模組繼續沿用。
  6. 提供 API 讓外部系統取資料（像外部監控）；劉老師另外開發的 RAG 運維助理以它作為類真實風場的資料與警報來源，做測試驗證。
- 同日對照程式碼的缺口分析（`work-logs/2026-11/2026-11-25-repositioning-gap-analysis.md`）：物理、成本、工單與定檢排程都有；缺的是四個沒接起來的地方——
  - Live 沒有機率式故障觸發，只有手動注入與批次排程。
  - `modules/workflow` 沒有接模擬器：警報不會開單、工單完工不會修好機組（修復只能 `POST /api/faults/clear`）；可用率由工單工時推估。
  - 原始資料保留期寫死 3 天（`data_broker.RAW_RETENTION_DAYS`），模擬器狀態不存檔，長時間運轉未驗證。
  - 沒有給外部系統的唯讀身分；`/api/export/events` 會回傳「Fault injected: 情境名稱」，`/api/faults/active` 任何登入者可讀。
- 儲存實測（14 台、10 秒取樣）：現行 SQLite 每列約 4.2 KB，約 15 GB / 月、91 GB / 半年；資料包用的 Parquet 每列約 113 bytes，約 0.4 GB / 月、2.5 GB / 半年（由 6 小時範例檔外推）。
- 同日劉老師補充：出發前的運維助理仍然需要——在仿真運維風場裡，工單派出來時要有這份資訊協助檢視判斷；之後若能接上真實風場，對驗證更有利。

### Considered Options

- **A. 維持 EPIC-DS（凍結情境）為唯一主線**：題庫已完成，但沒有持續運轉、沒有運維閉環，無法當「類真實風場」給 RAG 運維助理長期接。
- **B. 出發前助理當獨立產品，先找真實案例驗證**：卡在真實資料，最可能停在模擬驗證。
- **C.（採用）仿真運維風場為主線，出發前助理作為工單上的功能在仿真風場內先做、先驗證**：資料來源自己掌握；仿真風場知道每筆故障的真正原因，可以大量、自動地核對準備卡的內容，真實風場做不到這一點。

### Decision

選 **C**。

1. **定位**：windMindOM 是一座**仿真運維風場**——上面六項。EPIC-SF（Simulated Farm）為現行主線。
2. **出發前助理保留**，改為工單上的功能：
   - 工單建立時產生準備卡。故障出勤卡先做（警報 / 跳機開出的工單），例行巡檢卡後做（定檢排程開出的工單）。
   - 企劃 v0.1 的原則照用：只用可觀測資料、以資料截止點為界、每條可回查、證據不足就不下判斷、不判定根因。
   - 規則版放在 windMindOM（要用到工單、庫存、警報目錄、手冊檢索）。外部 RAG 運維助理經對外 API 取得同一批資料與工單，可以產生自己的摘要做對照（企劃裡規則版對語言模型版的比較）。這一點是 Claude 建議。
   - 評分用仿真風場不對外的故障紀錄自動核對。真實風場驗證留待日後有機會介接時再做。
3. **與既有決策的關係**：
   - 商業時程、真實風場 / OPC 介接仍暫緩（DEC-20261021-01 不變）。
   - EPIC-DS 已完成，保留為可重複評分的題庫；它的警報目錄、PLC 保護層、可觀測事件白名單、資料包欄位是 EPIC-SF 的基礎。盲測邊界照舊：故障原因與注入資訊不得出現在給外部系統的資料裡。
   - RAG 運維助理本身仍在 windMindOM 之外（DEC-20261021-01 第 5 點不變）。
   - `PRODUCT_VISION.md` 的運維廠商商業定位保留為歷史；五個模組都留用。
4. **開發順序（Claude 建議，劉老師 2026-11-25 確認）**：
   1. 對外唯讀 API 與外部系統身分——RAG 運維助理可立刻接上現有的 Live。
   2. 長時間運轉的基礎——保留期可設定、分層儲存、重啟續跑、長時間穩定性。
   3. 運維閉環——警報開單、工單完工才修復、定檢造成計畫停機、可用率由運轉狀態計算。
   4. 出發前準備卡。
   5. 機率式故障產生器、不對外的故障紀錄、模擬維修班。
   6. 成本模組吃模擬結果（既有 WMOM-20260504-11）。
   7. 實測風況匯入與物理加深，持續進行、不擋前面。
5. **預設值（Claude 建議，劉老師 2026-11-25 確認）**：10 秒原始資料保留半年；外部系統以 REST 取資料為主，OPC UA 並存；外部系統用長效 API 金鑰對應一個唯讀角色連線，不走人員登入。

### Rationale

- 第 6 項最小、最快，而且劉老師的 RAG 運維助理已經在開發，先讓它有東西可接。
- 機率式故障排在運維閉環之後：跳機的機組要等修復才解鎖（`maintenance_lock`），沒有修復路徑時，隨機故障只會讓機組一台一台停下來。
- 準備卡回看 7 到 30 天，而原始資料目前只留 3 天，所以長時間運轉的基礎要先做。
- 11-24 審查提的兩個疑慮在仿真風場內不成立：資料自己產生；樣本數可以由機率式故障長時間累積，不再是 5 到 10 件。準備時間能省多少，仍要等真人或真實風場才量得到。

### Consequences

- `ISSUES.md`：新增 EPIC-SF 與 WMOM-20261125-01 ~ -07；成本一項沿用 WMOM-20260504-11。
- `docs/product/ROADMAP.md`、`docs/product/PRODUCT_VISION.md`、`CLAUDE.md` §1 / §10、`STATUS.yaml`、`TODO.md` 同步方向。
- 之後要補：`docs/architecture/windMindOM-architecture.md` 與 `README.md` 在 EPIC-SF 第一項完成時一起更新；對外 API 要寫進介面合約。
- 企劃 v0.1 提到的雙卡原型、長跑紀錄不在 repo；它記的兩個現象（雲端長跑約 57 分停止寫入、十分鐘彙整重疊計數）併入長時間運轉的 issue 重現。

---

## DEC-20261126-01 — 對外唯讀 API：金鑰不是角色、一律強制；只給 Live 的可觀測資料；API 自己編版本

**日期**：2026-11-26　**狀態**：accepted　**Decision maker**：Claude（依 DEC-20261125-01 與 WMOM-20261125-02 的規格；劉老師 2026-11-26 指示「開始第 1 項」）。下面是實作時的設計選擇，劉老師尚未逐項看過
**延續**：DEC-20261125-01 第 4 點第 1 項與第 5 點（外部系統用長效 API 金鑰、唯讀、以 REST 為主）

### Context

EPIC-SF 第 1 項：讓外部系統（劉老師的 RAG 運維助理）像外部監控一樣，向持續運轉的仿真風場取資料與警報。動工前的現況有兩個洞：`GET /api/export/events` 會回傳 `Fault injected: {scenarioId}`；`GET /api/faults/active` 任何登入者可讀。外部系統照現有的方式接，等於看到答案。

### Considered Options 與 Decision

1. **外部身分怎麼做**
   - A. 在 RBAC 加一個角色（例 `Role.EXTERNAL`）、發 JWT。問題：現有幾十個端點掛的是 `require_authenticated`（任何登入者），新角色一拿到 token 就全部讀得到，包含故障狀態。要逐一改每個端點，漏一個就破功。
   - **B.（採用）金鑰是另一種憑證，不是角色。** 放在 `X-API-Key`，只有 `/api/ext/v1` 的 dependency 認它；`get_current_actor` / `require_role` / `require_authenticated` 都不看它。DEC-20261125-01 寫的「對應唯讀角色」，實作成金鑰上的權限範圍 `external:read`。新增端點預設就碰不到，不必記得去擋。
2. **金鑰一律強制**，不受 `WMOM_AUTH_ENFORCE` 與 dev mode 影響，沒有 fallback 身分。開發時與正式時的接法相同。
3. **盲測要伺服器開 `WMOM_AUTH_ENFORCE=true`，但沒開時不拒絕服務。** 沒開的時候其他端點本來就不用登入，金鑰擋不住。做法是在 `GET /status` 回報 `other_endpoints_require_login`、CLI 發金鑰時提醒。拒絕服務會讓開發期的介接變麻煩，而且擋不住真正的問題（其他端點是開的）。
4. **金鑰存 SQL（與使用者同一個 auth DB），dev mode 也是。** 使用者帳號在 dev mode 用記憶體裡的 demo 資料，金鑰不能這樣：伺服器重啟後外部系統手上的金鑰要還能用。只存 sha256，金鑰只在建立時顯示一次。管理走 admin 端點或 CLI（`tools/external_api_keys.py`）。
5. **給出去的東西與盲測版資料包同一套**：讀值欄位＝`pack_columns()`、事件只取 `is_observable_event`、格式用 `pack_event` / `json_values` / `stats_message`。不另外定義格式，也不給風場名稱等自訂文字。
6. **只給 Live**：排除情境 session。最新讀值取自最近一次寫進 storage 的那一批，不讀 simulator 記憶體——產生情境時那裡是情境的值。目前成立的警報取自 PLC 的清單（與 OPC UA 同一份），即時模擬沒在跑時不給。
7. **游標依寫入順序（id），不依時間。** 外部系統的用法是「上次看到哪、之後有什麼新的」。時間倍率改變時 Live 的時間戳會前後跳，依時間翻頁會漏。
8. **API 自己編版本（1.0），資料介面合約維持 1.7。** WebSocket 回放（v1.1）與 OPC UA（v1.2）加入時升了合約版本，這次不照做：資料格式沒有任何改變；合約版本寫在 7 個範例資料包與標準答案裡，升版要全部重建而內容不變；這個 API 的對象與生命週期（端點、金鑰、翻頁）也和學生專題的合約不同。文件另立 `docs/integration/external_api_v1.md`。
9. **10 分鐘統計即時計算**，一次最多 24 小時；殘缺窗以相鄰讀值間隔的中位數判定（Live 的寫入間隔實測約 10.1–10.2 秒，不是精確的 10 秒）。窗「收齊了沒」看這台機組最近一次寫進歷史的讀值的時間，不看實際時間：讀值每個取樣週期才寫一次，用實際時間會把最後一筆還沒進來的窗放出去，之後值又變；時間倍率大於 1 時讀值的時間也跑在實際時間前面（code review 指出）。
10. **`/status` 只說即時資料在不在、連不連續**（`live`、`live_epoch`），不說原因。原本有 `batch_running`，審查指出它等於告訴外部系統「管理端正在出題」，而 `live: false` 已經夠用，所以拿掉。
11. **`session_id` 為 NULL 的舊事件視為 Live。** WMOM-20261021-04 之前 Live 的事件都沒有 session；那時候產生情境只寫 `source="scenario"` 的注入 / 跳機標記（不是可觀測事件，不會被放出去），可觀測的情境事件與 session 隔離是同一版加入的。若改用情境時間窗排除這些舊列，會把同一段實際時間的 Live 事件一起藏掉。

### Consequences

- 新增：`modules/auth/api_keys.py`、`auth_api_keys` 表、`/api/auth/api-keys`（admin）、`modules/monitoring/server/routers/external.py`（9 個 `GET`）、`tools/external_api_keys.py`、`docs/integration/external_api_v1.md`。
- dev mode 下 `/api/auth/api-keys` 與使用者管理端點一樣不用登入（dev fallback 身分是管理員）；金鑰的驗證本身不受 dev mode 影響。dev mode 不能用來做盲測。
- 有時間下限的讀值查詢仍要把範圍內的列依寫入順序排序，成本隨範圍內的列數成長；輪詢（沒有時間下限）已改成從游標沿主鍵往後掃。保留期拉長後要在 WMOM-20261125-03 一起看。
- 舊的兩個洞沒有補在原端點上：`/api/export/events` 與 `/api/faults/active` 照舊給登入的人員看（操作端需要）。外部系統碰不到它們，前提是伺服器強制登入。
- 實測發現、留給 WMOM-20261125-03 的限制：伺服器重啟後模擬器狀態歸零，重啟前鎖存的跳機不會有解除事件；重啟後要有人重新選定資料來源；原始讀值只留 3 天；Live 的寫入間隔帶抖動；時間倍率大於 1 時資料變稀疏、時間戳會前後跳。
- `CLAUDE.md` §10 加「對外 API 守則」。

---

## DEC-20261126-02 — 即時模擬的時鐘只往前走、寫入對齊 10 秒；狀態存檔以 pickle＋程式指紋、要明確開啟

**日期**：2026-11-26　**狀態**：accepted　**Decision maker**：Claude（依 DEC-20261125-01 與 WMOM-20261125-03 的規格；劉老師 2026-11-26 指示「開始第 2+3+4 項」）。下面是實作時的設計選擇，劉老師尚未逐項看過

### Context

WMOM-20261125-02 的真伺服器檢查找出幾件讓即時資料不連續的事：寫入間隔約 10.15 秒；伺服器重啟後風場狀態歸零，鎖存的跳機沒有解除事件；重啟後要有人登入選來源；時間倍率改變時時間戳前後跳；產生情境會重設即時風場的狀態。

### Decision

1. **模擬時鐘是 Live 的唯一時間，只往前走。** 每一步把時鐘推進剛好一個 `time_step`，物理的 dt 與時鐘一致（原本時鐘讀實際時間、dt 固定 1 秒，每步的計算時間讓模擬慢慢落後）。時間倍率調回 1 之後維持領先的量，不跳回實際時間。Live 的事件預設用這個時鐘。
2. **落後就補跑，太多就跳過。** 重啟還原、產生情境、程序被暫停之後，Live 迴圈不等待、全速跑到現在；落後超過 6 小時（`WindFarmSimulator.MAX_CATCH_UP_S`）改成跳到現在、留下缺口——缺口那段時間風場沒有被模擬，疲勞、結垢、故障的劣化程度都停在缺口前的值。考慮過一律留缺口（像通訊中斷）：補跑讓歷史連續，而且就是原本規劃的「歷史回填」的小型版本。上限是為了啟動時不要連續佔用 CPU 太久（14 台實測約 75 倍速，補 6 小時約 5 分鐘）。
3. **寫入對齊模擬時間的 10 秒時段**，不看實際時間。一個 10 分鐘窗剛好 60 筆；加速時每 10 模擬秒也寫一筆，不再變稀疏。
4. **狀態存檔用 pickle，前面加一段 JSON 檔頭（版本、程式指紋、機組、時區）。** 考慮過替十幾個物理模型各寫一套狀態匯出 / 匯入：工作量大，漏一個欄位就是難查的錯。pickle 一次帶走全部，實測還原後接著跑與沒有中斷的那一份逐位元相同。代價是類別改過之後舊物件不能用，所以檔頭記下模擬器程式與警報目錄的 sha256，對不上就不解開後面的 pickle、風場從頭開始。**每次更新模擬器程式，風場狀態會重來一次。** 存檔有任何問題（壞檔、截斷、欄位讀不懂、還原途中出錯）都當成沒有存檔，不讓伺服器起不來。
5. **存檔與開機自動啟動都要明確開啟**（`WMOM_LIVE_RESUME`、`WMOM_AUTOSTART_SOURCE=simulation`），預設照舊。開機不自動啟動來源是 WMOM-20260719-04 的決定；存檔若預設開，測試與一次性的 broker 會讀到上一次留下的狀態。開了續跑之後，選即時模擬預設接著上次的狀態；要從頭開始，`POST /api/source/select` 帶 `fresh: true`。存檔時若正在加速，還原後時間倍率回到 1（時鐘維持領先的量）。
6. **存檔時機**：Live 迴圈每 30 秒在兩步之間存一次；操作員動過風場（來源是 `faults` / `control` / `config` / `maintenance` / `workflow` / `test_plan` 的 Live 事件）後下一步就存；正常停止時再存一次。伺服器被強制關閉時，存檔點之後已經寫進 storage 的讀值與事件不重寫：到最後一筆已寫入的讀值為止是重跑段（事件偵測照跑、什麼都不寫）；再往後到下一個 10 秒時段開始是去重段（讀值每 10 秒才寫、事件每一步都記，這幾步的事件逐筆對 storage 查重）。最後一筆讀值離存檔點超過 120 秒就不當成重跑的依據（那是別的來源寫的列）。
7. **產生情境不動到即時風場。** 批次前把 Live 的狀態留在記憶體、批次後還原，不必開存檔。原本批次會清掉 Live 的故障、把模型留在情境結束時的狀態。批次端點回報的「結束時故障狀態」在還原之前取。還原失敗時從批次留下的狀態接著跑，`live_epoch` 改變。考慮過另建一個模擬器跑批次：要改每個批次端點取用模擬器的方式，留給之後。
8. **`live_epoch` 是這份風場狀態從頭開始的那個 session 的 id**，寫在存檔裡。還原沿用，所以重啟續跑與產生情境都不改變它；只有狀態真的重來才會變。原本用批次計數，每產生一次情境就加 1。

### Consequences

- `simulator/engine.py` 的 Live 迴圈改寫；`simulator/checkpoint.py`（新）；`data_broker.py` 的寫入節奏、事件時間、存檔 / 還原、批次前後的狀態保存；`server/app.py` 讀兩個環境變數。
- 套用風場規格時，規格相同就不呼叫 `update_spec`：它會重建 PLC 保護層，把還原的鎖存清掉。
- 對外 API 的端點與欄位沒有變；`docs/integration/external_api_v1.md` §5 改寫。
- 快照（事件前後的 1 秒資料）的視窗與冷卻改用模擬時間計算，事件參照的時間字串也跟模擬時鐘。
- 尚未做：保留期與分層儲存（-03-c）、72 小時連續運轉測試、比 6 小時更長的歷史回填。風場狀態重來時，前一段鎖存的跳機沒有解除事件（以 `live_epoch` 標示）。
- 已知的限制：伺服器被強制關閉時正在進行的快照視窗，重啟後不會接著擷取；存檔連續失敗超過 2 分鐘又被強制關閉時，那一段的讀值重啟後會重寫一次。
- 風險：pickle 只能讀自己寫的檔。存檔與風場 DB 放在同一個目錄，能改那個目錄的人本來就能改 DB。

---

## DEC-20261126-03 — 原始讀值分兩層保存：SQLite 留最近幾天、每日 Parquet 歸檔留半年；保留期看資料的時間

**日期**：2026-11-26　**狀態**：accepted　**Decision maker**：Claude（依 DEC-20261125-01「10 秒原始資料保留半年」與 WMOM-20261125-03 的規格）。下面是實作時的設計選擇，劉老師尚未逐項看過

### Context

SQLite 的 `turbine_data` 把整包 SCADA 值存成 JSON，實測每列約 4.2 KB：14 台機組、10 秒取樣一天 505 MB，半年約 91 GB。原本原始讀值只留 3 天（寫死）。出發前準備卡要回看 7 到 30 天，外部的 RAG 運維助理也要拿得到夠長的歷史。

### Decision

1. **兩層。** 最近幾天留在 SQLite（熱資料，預設 3 天），較舊的依 UTC 日期轉成 Parquet 日檔（`<風場目錄>/live_archive/raw/YYYY-MM-DD.parquet`，每台機組一個 row group）。實測一整天 14 台 120,960 列是 15.9 MB（每列 131 bytes），半年約 2.9 GB；加上 SQLite 的 3 天約 1.5 GB。考慮過只把 SQLite 的保留期調長：半年要 91 GB。考慮過把 SQLite 的 JSON 欄位換成欄式或壓縮：要改每一條讀寫路徑。
2. **保留期可設定**：`WMOM_RAW_RETENTION_DAYS`（總天數，預設 183；0＝不歸檔、照舊）與 `WMOM_RAW_HOT_DAYS`（留在 SQLite 的天數，預設 3）。循環保存＝刪最舊的日檔。
3. **保留期看資料自己的時間，不看實際時間。** 「哪一天過完了」「哪些列超過熱資料天數」都以資料時鐘為準：即時模擬在跑時是它的模擬時鐘，否則是 storage 裡最近寫入的 Live 讀值時間。即時模擬在跑時不看 storage 裡最後寫入的那一列，是因為別的來源可能寫進時間在未來的列（沒有命名的批次），拿它當現在的話半年的日檔會被當成過期刪掉。原因：時間倍率大於 1 之後模擬時鐘跑在實際時間前面，照實際時間算的話，加速產生的幾個月資料會全部留在 SQLite。
4. **先歸檔、再記界線、最後才刪，而且只刪確定在日檔裡的列。** 索引記兩個時間：`archived_through`（這之前的日子都處理過了）與 `hot_from`（SQLite 已經刪到這裡）。SQLite 那邊每一天只刪 id 不大於該日檔最大 id 的列——那天後來才寫進來、還沒進日檔的列留著。歸檔失敗時界線退到失敗的那一天。同一時間只有一方在做這件事（鎖）：maintenance 執行緒每小時一次，管理端可以手動觸發。
4a. **索引讀不出來不當成「沒有歸檔」。** 當成沒有歸檔的話，下一次寫索引會把舊日檔丟掉，查詢也會整段漏掉（code review 重現過）。寫的一方從日檔重建索引；讀的一方報錯，對外 API 回 503，不回一份缺了舊資料的結果。歸檔裡的讀值 id 比風場 DB 發過的還大（DB 被重建、歸檔卻留著）時拒絕使用。
5. **查詢跨兩層、同一個游標。** `hot_from` 之前的由歸檔給、之後的由 SQLite 給，每一列只給一次，依 `turbine_data.id` 合併。考慮過以 id 分界（比 SQLite 最小 id 還小的在歸檔）：id 的順序不一定等於時間的順序（同一段時間的列可能分兩次寫進來），會漏列。
6. **歸檔照 PLC 資料型別存**（REAL＝float32、整數取整、BOOL；超出型別範圍的值當成缺值），和情境資料包的 raw Parquet 一樣；SQLite 那一層的值在查詢時經過同一套轉換（`server/plc_types.py`）。兩層給的值因此相同，同一個 10 分鐘窗的統計不會因為資料搬進歸檔而改變。代價：`/stats-10min` 個別統計值的最後一位有效數字可能和 API 1.0 不同（原本由 float64 計算）。考慮過歸檔存 float64：檔案大約兩倍，而且感測器值不需要那個精度。
7. **歸檔留全部 tag（含模擬器內部量）與 `session_id`。** 這是自己的歷史；給出去時由呼叫端挑欄位，對外 API 仍只給 `pack_columns()`。只歸檔 Live，情境 session 的讀值留在 SQLite 直到情境被刪。
8. **即時模擬從頭開始時，模擬時鐘接在已存的 Live 讀值之後。** 用過時間倍率之後風場狀態重來（沒開續跑、程式更新、選擇從頭開始），原本時鐘會跳回實際時間，同一段時間就有兩份讀值，依時間的查詢、10 分鐘統計、每日歸檔都會混在一起。現在 Live 的歷史在時間上不往回。代價：風場的時間一旦被加速推到未來，就一直在未來，要回到現在只能換一個風場資料目錄。
9. **`/status` 加 `raw_retention_days`**，`api_version` 1.0 → 1.1。

### Consequences

- 新增 `server/live_archive.py`、`server/live_history.py`；`storage.py` 加走 `(turbine_id, timestamp)` 索引的查詢與逐台機組的刪除（`turbine_data` 沒有純時間的索引，不帶機組的時間範圍查詢會掃整張表）；`data_broker.run_retention` 由 maintenance 執行緒每小時呼叫，管理端也可以用 `POST /api/config/storage/maintenance` 手動觸發。
- 實測（一整天 14 台、0.5 GB 的 DB）：歸檔一天 5.0 秒，沒有變動時再檢查一次 0.16 秒；清理一天 4.1 秒，其間另一條執行緒的寫入最久等 0.38 秒；從歸檔讀一頁 1000 筆 0.05 秒、掃一台機組 24 小時 0.10 秒。
- SQLite 檔刪除後不會縮小（空間重複使用），所以磁碟用量大約是「熱資料天數 × 0.5 GB」加「歸檔天數 × 16 MB」（14 台）。
- 已知的限制：時間早於 `hot_from` 的列若之後才寫進 Live（把很久以前的資料補進來），不會進歸檔、也查不到，留在 SQLite 直到超過總保留期才刪——歷史回填要另外處理（WMOM-20261126-02）。刪掉風場 DB 時要一併刪掉 `live_archive/`。1 分鐘彙整（留 90 天）與事件快照（留 7 天）仍照實際時間清理；10 分鐘彙整與事件永久保留。沒有命名的批次仍會把模擬時間的列寫進 Live session。
- 72 小時連續運轉測試還沒做（WMOM-20261126-01）。

---

## DEC-20261126-04 — 運維閉環第一版：跳機自動開單、工單完工即修好、可用率由運轉狀態紀錄計算

**日期**：2026-11-26　**狀態**：accepted　**Decision maker**：Claude（依 DEC-20261125-01 與 WMOM-20261125-04 的規格）。issue 列的待決事項「完工即修好，還是處置對了才修好」採建議的前者；其餘是實作時的設計選擇，劉老師尚未逐項看過

### Context

工單模組和模擬器原本互不相干：警報不會開單，工單完工不影響機組（修復只能由管理端 `POST /api/faults/clear`），可用率由工單工時推估（程式自己註明工時不等於停機時間）。仿真運維風場要讓派工、修復、停機、發電、可用率是同一件事的不同面。

### Decision

1. **哪些事件開單：跳機（T1 / T2）與自動重啟被封鎖（A039）。** 一般警報（A 級）不開單。開的是故障維修工單、狀態 draft、帶警報碼；T2 與 A039 的優先級是 high。同機組同碼已有未結案工單、或那台機組已有三張未結案工單時不開（工單模組既有的規則）。**誤報與外部原因的跳機也會開單**（電網擾動讓整場跳機時每台一張）：這是自動規則的真實樣子，也正是出發前準備卡與外部助理要幫忙判斷的情況。考慮過機組自己恢復就自動撤單，留給之後。**鎖著的機組一定有一張未結案的工單**：工單被撤、跳機當下那台機組的工單已達上限、或開單那一刻伺服器被強制關閉時，每 10 分鐘（風場時鐘）的檢查會補開一張——PLC 的跳機事件不會再送一次。只有 A 級警報、沒有跳機的故障（例：還在早期的軸承磨耗）不會有工單，要靠定檢或人工開單。
2. **完工即修好，修復發生在現場完工（`finish`），不等簽核。** 簽核是文書。第一版不看現場做了什麼處置。修什麼：
   - 帶警報碼的故障維修工單：修掉預期會送出這個碼的故障（`FaultScenario.alarm_codes`）。沒有這樣的故障就只復位。
   - A039 開的工單：修掉已經跳機鎖住機組的故障（A039 不是獨立的故障，是某個跳機碼超過每小時重啟上限）。
   - 沒帶警報碼的故障維修、定檢、預防保養、試運轉：修掉該機組全部的故障。定檢因此有實際效果：還沒到警報的劣化會在定檢時被處理掉。
   - 簽核退回視同重新開工，機組再進維修模式。完工時只對停著或鎖著的機組復位：復位會把發電機轉速與併網狀態歸零，不能對正常在發電的機組做。
3. **開工＝機組進維修模式**（正常停機）；完工或撤單時放掉。定檢 / 預防保養 / 試運轉的停機算計畫停機，故障維修的算非計畫停機。同一台機組有多張工單在進行時，最後一張完工才放掉；其中有故障維修就算非計畫。
4. **「復位不等於修好」不變**（WMOM-20260719-01）。管理端的故障注入 / 清除（`/api/faults/*`）是出題用的後門，照舊；它不是運維的路徑。
5. **可用率由運轉狀態紀錄計算。** 每次把讀值寫進歷史時（模擬時間的每 10 秒），每台機組歸到四種狀態之一，累加進 `availability_hourly`（每台每小時一列，永久保留）：
   - 計畫 / 非計畫停機：因工單在維修模式（依工單類型）；沒有工單的維修模式算計畫。
   - 非計畫停機：PLC 有鎖存的跳機、自動重啟被封鎖，或故障跳機後等待維修。
   - 發電中；其餘算「可發電但沒在發電」（待機、起動、風太小或太大）——不算機組的停機。
   - 時間可用率＝1 −（計畫＋非計畫）÷ 有紀錄的時間；發電量可用率＝發電量 ÷（發電量＋停機少發的電）。停機少發的電以同一時刻發電中機組的平均功率估計，沒有機組在發電就算 0。
   考慮過事後由原始讀值重算：超過保留期就算不出來，而且「這段停機是計畫還是非計畫」要對工單，當下記最單純。
6. **模組之間的方向**：workflow 不 import monitoring。workflow 提供掛鉤（`modules/workflow/hooks.py`），工單建立或狀態改變寫進資料庫之後通知；monitoring 的閉環（`server/om_loop.py`）登記進去，並直接用工單的 repository 開單。listener 出錯不影響工單的操作。
7. **伺服器預設開**（`WMOM_OM_LOOP`，設 `false` 關掉）；直接建立的 broker（測試、工具）預設關，沒開就不載入工單模組。只作用在即時模擬：產生情境的批次期間收到的開工 / 完工先記著，批次結束、即時風場的狀態還原之後才套用。
8. **盲測邊界**：自動開的工單只寫事件碼、PLC 文字、訊號值與設定值。完工時修了哪些故障記在 `source="workflow"` 的事件裡，那不在可觀測事件的白名單。可用率的分類用到「故障跳機後等待維修」這個內部狀態，端點只給登入的管理端，對外 API 沒有。
9. **舊的 `work_orders` 表**（`/api/maintenance/*`）標示為舊介面，不整併：既有畫面還在用，閉環只接正式的工單。

### Consequences

- 新增 `modules/workflow/hooks.py`、`modules/monitoring/server/om_loop.py`、`server/routers/operations.py`（`GET /api/operations/availability`）；`storage.py` 加 `availability_hourly`；月報的可用率改由運轉狀態紀錄提供（`set_availability_provider`），沒有紀錄時退回由工單工時推估。
- 工單的時間（建立、派工、完工）用實際時間，讀值與事件用風場時鐘。時間倍率是 1 時兩者一致；加速時不一致——可用率用的是風場時鐘，不受影響，自動開的工單把風場時鐘的發生時間寫在說明裡。
- 沒有人處理工單時，跳機的機組會一直停著、工單會累積到每台三張的上限。模擬維修班排在 WMOM-20261125-06。
- 尚未做：「處置對了才修好」；機組自己恢復時自動撤單；前端顯示可用率與自動開單的標記；定檢排程自動觸發（目前仍要呼叫 `run-scheduler`）；對外 API 的唯讀工單端點（排在 WMOM-20261125-05，和準備卡一起）。

---

## DEC-20261126-05 — 出發前準備卡第一版：故障出勤卡只用可觀測資料、訊號由 PLC 判定邏輯挑、卡片不可變、答案另存

**日期**：2026-11-26　**狀態**：accepted　**Decision maker**：Claude（依 DEC-20261125-01 與 WMOM-20261125-05 的規格）。與 issue 規格不同的三處（不引用知識庫、不列料件、例行巡檢卡沒做）與其餘的設計選擇，劉老師尚未逐項看過

### Context

運維閉環（DEC-20261126-04）讓跳機會自動開工單，但工單上只有一行事件碼。劉老師 2026-11-25 確認保留出發前助理：工單派出來時，要有一張整理好的證據協助檢視判斷。企劃 v0.1 的原則是只用可觀測資料、以資料截止點為界、可回查、缺資料要降級、不判定根因。這張卡同時要給外部的 RAG 運維助理當對照，所以它給出去的每一個字都受盲測守則管。

### Decision

1. **什麼時候產生：故障維修工單建立當下**，由工單的掛鉤觸發（自動開的與手動開的都有）。資料截止點＝那一刻的風場時鐘；卡上的事件、讀值都只取截止點以前的。定檢 / 保養 / 試運轉的工單、對不到機組的工單沒有卡。手動開的單沒帶事件碼時照樣給卡，只列背景量測並標 `no_alarm_code`。
2. **卡片存了就不換**（`briefing_cards`，一張工單一張，`ON CONFLICT DO NOTHING`）。出發前看到什麼，事後評分就對什麼；重新產生會把修復之後的資料混進去。沒有卡、還沒完工的故障維修工單可以補一張（批次結束時、每 10 分鐘的定期檢查、或管理端 `POST`），補的卡標 `generated_late`、截止點是補的那一刻。已經完工的不補。
3. **相關訊號從 PLC 的判定邏輯來，不從故障情境來。** 每個事件碼看哪些量測，取自 `build_rules()` 裡那個碼的規則用的訊號，再經一張手寫的對應表（PLC 訊號 → 給得出去的 tag，`SIGNAL_TAGS`）。PLC 沒有訊號判定規則的碼（物理層保護停機：351、320、475、481、482、489）另有一張小表（`CODE_TAGS`）。這是手冊層級的知識（哪個碼看哪個量測），和這台機組實際有什麼故障無關——考慮過直接用故障情境的 `key_signals`，那等於把答案寫在卡上。背景量測固定三個：機艙風速、功率、轉速。
4. **和同場比，只和發電中的機組比。** 這台機組截止點前 1 小時的平均，對同場其他機組同一小時的平均：中位數與絕對中位差，偏離 3 倍算偏高 / 偏低；離散程度至少取中位數的 2 % 與量測範圍的 0.5 %（同場太一致時不要把雜訊當偏離）。那一小時發電不到一半時間的機組不拿來比（停機的機組溫度、轉速本來就不同）。**最後 10 分鐘另外再比一次，任一個偏離就算偏離**——最後才飆高的訊號在 1 小時平均裡會被稀釋（實測：軸承溫度 1 小時平均 44 °C、最後 10 分鐘 81 °C）。可比的機組少於 3 台就不比，標 `too_few_peers`。另給自己前 6 小時的平均當基準。
5. **手冊只引警報目錄（Z72 手冊 Appendix C）的原因與處置，不引用知識庫。** issue 規格寫了「knowledge 模組的檢索」，沒有照做：知識庫目前的語料（`baseline_corpus_z72.json`）是對照故障情境寫的佔位內容，有鑑別診斷、甚至寫明是模擬，不是手冊原文。把它放上卡等於把答案的線索送給外部。等真的手冊語料進來（M5 剩下的那部分）再接。
6. **不列料件。** issue 規格寫了「所需料件的庫存」，沒有照做：目前沒有「警報碼 → 料件」的對應表，自己編一張就是在判定根因。卡上固定寫 `inventory.status = "no_mapping"`。
7. **缺資料要標明並降級**：`data_quality.flags`（沒有事件碼、找不到事件、事件沒掃完、沒有對應量測、沒有讀值、讀值太舊、可比機組太少、沒有基準），有任何一項 `degraded` 就是 true，畫面上顯示「資料不完整，請保守判讀」。
8. **機組狀態連讀值的時間一起給**（`turbine_state` ＋ `turbine_state_ts`）。讀值每 10 秒一筆，跳機當下產生的卡，最後一筆讀值還是跳機前的「發電中」；只寫狀態會誤導。
9. **評分：答案另外存，只給主管。** 工單建立當下這台機組實際有哪些故障（情境、類別、重點訊號、是否跳機）記在同一列的 `answer_json`，不在卡片裡。沒有存到答案的卡不評分（回 409）——把「沒記到答案」當成「沒有故障」會算出假的誤報。`GET /api/operations/work-orders/{id}/briefing/score` 用它核對，永遠要主管角色（不看 `WMOM_AUTH_ENFORCE`，同標準答案端點）：
   - `key_signal_flagged`：卡上標成偏高 / 偏低的主要 / 相關訊號裡有沒有故障的重點訊號（主要指標）。
   - `false_escalation`：機組其實沒有故障（誤報、外部原因），卡上卻把主要 / 相關訊號標成偏離。
   - `degraded_when_missing`：資料有缺時有沒有降級。
   - `key_signal_listed`：重點訊號被列在卡上的比例——只當檢查用，卡上的訊號本來就來自 PLC 看的量測，這個比例區辨不出好壞。
   背景量測不算分：機組一跳機，功率與轉速本來就和別台不同。準備時間能省多少，要等真人或真實風場才量得到。
10. **讀卡片的端點只讀。** `GET /api/operations/work-orders/{id}/briefing` 回白名單欄位（沒有答案），沒有卡回 404，不會順手產生；補卡是 `POST`（組長 / 主管）。考慮過 `GET` 時沒有就產生：讀的動作不該寫資料庫，而且那樣截止點會變成「第一次有人看的時候」。風場不是目前啟用的那一座回 409（和「沒有卡」分開，畫面才分得出來）；補卡時卡片做不出來回 500，不報成「即時模擬沒在跑」。
11. **不能停下來等的執行緒不等卡片。** 一張卡要讀同場每台機組幾小時的讀值。跳機自動開單是在即時模擬的執行緒上，整場一起跳機時會讓模擬停好幾秒；API 建單的路由是 `async def`、直接呼叫 repository，在事件迴圈上做卡會讓整個伺服器的請求都等它（第二輪 code review 找到）。這兩種執行緒開的單，截止點、答案、要讀寫的那座風場在開單當下記下來，卡片排到背景執行緒做（實測建單回應 15 ms，卡片不到 1 秒後出現）；一般的執行緒（工具、測試、補卡的 `POST`）當下做完。排著的時候風場換了就不做，換回來之後由定期檢查補（標 `generated_late`）。同一張工單不重複排；連續 3 次做不出來，定期檢查就不再替它排（管理端仍可手動補）。批次結束時的補卡一律排到背景，批次端點的回應不等它。
12. **對外 API 1.2**：`GET /api/ext/v1/work-orders`（只有結構化欄位：編號、機組、類型、狀態、優先級、警報碼、各階段的時間；標題、說明、施工摘要不給；只列對得到機組的；工單上的警報碼欄位是自由文字，只給純數字的——卡上「以前的工單」也一樣）與 `GET /api/ext/v1/work-orders/{business_key}/briefing`（同一張卡，原樣）。工單清單依建立順序、用 `(建立時間, 工單編號)` 的字串游標往後翻——工單沒有遞增的整數 id，同一時刻建立的多張以編號分先後；游標只含可以直接放進網址的字元。
13. **「以前的工單」只列這張工單之前開的。** 工單的時間是實際時間、沒辦法和風場時鐘的截止點比，所以用工單自己的建立時間當界線；卡片在背景做的那一點延遲裡才開的單不算。事後補的卡（`generated_late`）列到補的那一刻。
14. **例行巡檢卡沒有做**，另開 issue。

### Consequences

- 新增 `modules/monitoring/server/briefing.py`、`briefing_cards` 表、`OmLoop.make_briefing` / `ensure_briefings`、`/api/operations/work-orders/{id}/briefing`（GET / POST）與 `/briefing/score`、對外兩個端點、`WorkOrderRepository.list_forward`；前端 `BriefingCard`（管理端工單視窗與 `/field/` 的我的工單都看得到）。
- 卡片的欄位有自己的版本（`CARD_VERSION`，目前 1.0），跟對外 API 的版本分開。
- 卡片是規則整理的，沒有語言模型。它對「PLC 看的那個量測自己就偏離」的故障很有用（軸承、冷卻、液壓）；對量測本身壞掉的情況（斷線、卡住）只能指出「這個讀值和別台不一樣」，分不出是感測器還是真的；沒有警報的劣化不會有工單，也就沒有卡。
- 工單的時間是實際時間、卡片的截止點是風場時鐘（DEC-20261126-04 留下的不一致），卡上與對外文件都寫明了。
- 工單編號（`WO-LEGAC-202611-001`）裡有風場 ID 的前五個字，會跟著工單給外部。風場 ID 是管理端建風場時取的代號，不是風場名稱；做盲測時不要把它取成會透露題目的字。
- API 建單的回應回來時卡片可能還沒做完（不到 1 秒）；畫面是打開工單時才讀卡片，對外端點在卡片存好之前回 404、清單的 `has_briefing` 是 false。
- 尚未做：例行巡檢卡；料件對應；接真的手冊語料；把多張卡的評分彙整成報表（目前一次看一張）；`/field/` 離線時的卡片快取。

---

## DEC-20261126-06 — 準備卡的資料截止點改為「建單之後第一批讀值」；停好的機組留在 SHUTDOWN

**日期**：2026-11-26　**狀態**：accepted　**Decision maker**：劉老師看過情境測試報告後指示「先修第 1、2 個，第 3 個查清楚」；做法由 Claude 定

### Context

第 1–4 項完成後在真伺服器跑了一次端到端情境（14 台、軸承磨耗＋量測回路斷線＋定檢）。整條鏈走得通，找到四個問題，見 `work-logs/2026-11/2026-11-26-scenario-test.md`。

### Decision

1. **準備卡的資料截止點**（修訂 DEC-20261126-05 第 1 點）：由「工單建立當下」改為「建單之後第一批寫進歷史的讀值的時間」，最多晚一個取樣週期（10 秒）。讀值每 10 秒存一筆，跳機可能落在兩筆之間；量測回路斷線在 4 秒內跳機，異常讀值（850 °C）還沒進歷史，馬上做的卡五個訊號全是「相近」。歷史已經涵蓋到現在時仍然馬上做。評分用的答案照舊在建單當下取。訊號的視窗含截止點那一筆；每個訊號另給最後一筆讀值（`last_value`），卡片版本 1.1。考慮過把 PLC 觸發當下的訊號值與設定值放上卡：那是 `/events` 目前沒有給外部的欄位，要動資料合約，這次不做。
2. **操作員停機 / 維修模式的機組停好之後留在 SHUTDOWN。** 以前狀態機每一步都重新要求停機，機組在 SHUTDOWN 與 NORMAL STOP 之間每 13 秒來回一次（情境測試的 50 筆事件裡有 29 筆是這種）。這是既有的行為，不是閉環帶進來的；操作員停機也一樣。只影響被停住的機組，健康機組的輸出不變。
3. **跳機鎖存在沒有人處理時解除，不改。** 查過不是重啟造成的（不重啟也在跳機後約 100 秒重現）：PLC 照手冊在條件消失、沒超過每小時上限時自動解除，機組仍由 `maintenance_lock` 鎖著等維修（「復位不等於修好」）。後果是這段時間 `/alarms/active` 沒有那個碼、機組卻停著；真實機組會自動重啟再跳一次。留給第 5 項（機率式故障）一起看要不要讓它真的重啟再跳。
4. **時間倍率 60 實際約 32 倍，不處理。** 記錄下來；歷史回填（WMOM-20261126-02）要用批次生成，不靠加速。

### Consequences

- 工單建立到卡片出現，最多約一個取樣週期；對外文件的說法跟著改。
- 既有的卡片（1.0）沒有 `last_value`，前端顯示「—」。

---

## DEC-20261126-07 — 即時模擬裡跳過機的故障不鎖機組：自動重啟、再跳、A039 封鎖

**日期**：2026-11-26　**狀態**：accepted　**Decision maker**：劉老師（2026-11-26 回覆「同意，照這個方向開始第五項」）；做法由 Claude 定

### Context

情境測試（DEC-20261126-06 第 3 點）看到：軸承溫度跳機後約 100 秒，PLC 照手冊解除鎖存，但機組被 `maintenance_lock` 擋著不重啟。這段時間外部的 `/alarms/active` 沒有那個跳機碼，機組卻停著——真實機組不會這樣，它會自動重啟、故障還在就再跳一次。

### Decision

1. **即時模擬**：跳過機的故障照樣作用在機組上（`FaultEngine.keep_tripped_active`），維護鎖不擋重啟（`lock_blocks_restart = False`）。之後全照 PLC 既有的規則走：鎖存解除 → 自動重啟 → 故障還在就再跳 → 同一個碼一小時內超過手冊上限時送 A039、機組進 SHUTDOWN 等人復位。實測軸承磨耗：跳機 → 80 秒後解除 → 重啟發電約 5 分鐘 → 再跳 → A039。量測回路斷線這類條件不會消失的故障，鎖存本來就不解除，行為不變。
2. **批次情境（題庫）不變。** 開關只在即時模擬生效（`retrip_after_restart and not _bulk_running`）。EPIC-DS 的資料包、標準答案、範例資料都是在「跳機後停到維護清除」的規則下產生與校準的，改了要全部重建並重新驗證，這次不動。
3. **「復位不等於修好」仍然成立**，而且變得更真實：復位之後機組重啟、故障還在、過幾分鐘再跳。工單完工才真的修好。
4. **A039 不另開工單**，如果那台機組已經有未結案的故障維修工單。A039 是同一個跳機碼跳太多次的結果，不是另一件事；以前會開出兩張。沒有未結案工單時照舊開一張（優先級 high）。
5. **可用率**：帶著故障重啟、還沒再跳的那幾分鐘機組在發電，照實算發電，不算停機。
6. 伺服器預設開（`WMOM_LIVE_RETRIP`，設 `false` 關掉）；直接建立的 broker / 模擬器預設關，既有的測試不受影響。

### Consequences

- 外部看到的事件流多了「解除 → 重啟 → 再跳 → A039」這一段，和真實風場一致；外部助理可以用「重啟後又跳」當線索。
- 準備卡在第一次跳機時產生，不會因為再跳而重做（卡片不可變）。
- 模擬器程式變了，既有的狀態存檔不相容，升級後風場狀態會從頭開始一次。

---

## DEC-20261126-08 — 機率式故障產生器、不對外的故障紀錄、模擬維修班

**日期**：2026-11-26　**狀態**：accepted　**Decision maker**：Claude（依 DEC-20261125-01 與 WMOM-20261125-06 的規格）。預設值與下面列的取捨，劉老師尚未逐項看過

### Context

到第 4 項為止，故障都要人手動注入，工單也要人處理；沒有人在的時候風場什麼事都不會發生，或者機組一台一台停下來。EPIC-SF 的完成條件是「風場無人值守連續運轉一個月以上，自己發生故障、開單、修復」。

### Decision

1. **故障產生器是每台機組一個卜瓦松過程**（`simulator/fault_generator.py`）。基本發生率＝每台機組平均幾天一次（預設 30 天；14 台約兩天一個），乘上機組權重與耗損的放大。每 60 模擬秒檢查一次，發生時依權重抽情境，劣化速度在「0.5–48 小時到最嚴重」之間取對數均勻。一台機組預設同時最多一個故障。
2. **亂數用自己的 stream，抽樣次數固定。** `random.Random(seed)`，每次檢查每台機組固定抽三個數（有沒有發生、哪一種、多快），不論結果與設定。關著的時候完全不抽。物件跟著即時模擬的狀態存檔，重啟後接著同一條序列。不碰模擬器既有的任何 RNG（開著但發生率極低時，讀值與關著逐位元相同，測試守著）。
3. **只作用在即時模擬。** 批次情境（題庫）的故障由排程決定，引擎在批次期間不呼叫產生器。
4. **耗損提高發生率，而且偏向相關的故障。** 冷卻類情境（變頻器冷卻、機艙通風、變壓器）看熱交換器結垢，其餘看疲勞累積損傷；情境的權重乘上 `1 + wear_gain × 耗損`（預設 4）。耗損是「累積量 ÷ 參考值」封頂在 1。實測疲勞損傷約每年 0.4、結垢約每年 0.044，所以參考值預設取疲勞 0.1（約三個月）、結垢 0.02（約半年）——直接用 0–1 的原始值的話，幾個月內的放大只有幾個百分點，等於沒有作用。
5. **四個情境預設不產生**（權重 0，可以自己打開）：結冰（看天氣）、靜態偏航失準（沒有任何警報，不會有工單）、電網電壓驟降（不是單一機組的事）、接點鬆動（nuisance，自己會恢復、多半沒有工單可以修掉它）。後兩種留在機組上會一直佔著那台的名額。
6. **故障紀錄是 Live 版的標準答案**（`fault_records` 表、`server/fault_record.py`）：每筆故障的來源（產生器 / 手動）、發生時間、第一次送出預期碼的時間、第一次跳機與跳機次數、期間這台機組所有的警報 / 跳機、被哪張工單修好；答案欄位（根因、元件、處置、重點訊號）用批次情境同一個 `scenario_answer`。時間是風場時鐘。**只給主管，端點永遠強制**（`GET /api/operations/fault-records`）；不進對外 API、準備卡、可觀測事件。重啟後重跑與去重的那幾步不記。
7. **模擬維修班處理「一直沒有人處理」的工單**（`server/crew.py`）：工單建立後過了反應時間（預設 120 分鐘）沒人開工就接手，開工後過了修復時間（預設 240 分鐘）完工並直接結案；同時最多幾組（預設 2），優先級高的先、同一台機組一次一張。時間算風場時鐘。它走工單的狀態機，和人從畫面操作同一條路——機組的停機與修復仍由運維閉環處理。
   - 人已經開工的不碰；維修班開工之後人接手的，放手。
   - 有簽核鏈的工單（人從畫面完工的）不代簽，留給簽核流程。
   - 結案直接呼叫 `approve_all`，不走多階簽核；維修班不是真人，結案時不寫當日工作表。
   - 由關轉開時，積壓的工單從那一刻起算反應時間。
8. **設定存在風場 DB**（`farm_settings`），`PUT /api/operations/fault-generator`、`/crew` 修改，重啟後照舊。兩者預設都關；`WMOM_FAULT_GENERATOR` / `WMOM_CREW` 只決定「還沒存過設定的風場」的預設。批次期間不能改（批次結束時即時模擬的狀態會還原）；批次結束後設定會從風場 DB 再套一次。
9. **風場事件（電網擾動、風向快速變化）的機率觸發沒有做。** 它們目前只在批次套用，要先讓它們能在即時模擬套用，另開 WMOM-20261126-07。

### Consequences

- 把產生器與維修班都打開，風場就會自己故障、開單、修復；測試裡 5 台機組跑 5 小時、產生 5 個以上的故障、最後全部修好回到發電。
- 準備卡的評分現在有成批的資料可以算了，但彙整的報表還沒做。
- 沒有警報的故障、被關掉的維修班、手動注入後忘了清的故障，都會讓那台機組不再產生新的故障（每台同時一個）。
- 工單上的時間仍是實際時間；維修班的反應與修復時間算的是風場時鐘，時間倍率大時兩者對不上。

---

## DEC-20261126-09 — 一次停機一張工單；復位時有判定窗的規則重新判定；加速時重跑段的範圍跟著倍率

**日期**：2026-11-26　**狀態**：accepted　**Decision maker**：Claude（WMOM-20261126-01 長跑找到的 bug 的修法）。劉老師尚未看過

### Context

72 小時長跑（故障產生器＋模擬維修班開著、倍率 200、中間正常重啟與強制關閉各一次）找到三個會讓資料或可用率出錯的問題：(1) 冷卻類故障同時送出兩個跳機碼（439 ＋ 021），各開一張工單，一張修好之後另一張又把機組停下來修一次；(2) 完工復位的下一步馬上再跳 021 / 439，多開一張沒有故障的工單——439 只在發電時判定，成立之後停機時解不掉；(3) 加速時被強制關閉，存檔點之後已經寫過的 9 分多鐘讀值又寫一次——判斷重跑段的上限 120 秒是照 1 倍速設的。

### Decision

1. **機組已經有未結案的故障維修工單，跳機就不再開單**（原本只有 A039 這樣）。那張工單修不到的故障，完工後機組仍鎖著，PLC 會再跳（那時沒有未結案工單，照常開），或由 `ensure_work_orders` 補開。代價：人手動開的故障維修工單也會擋住自動開單。
2. **操作員復位時，有判定窗的 PLC 規則（`producing_only` / `gate`）重新判定**：要等窗打開、延時到了才會再跳。沒有判定窗的規則照舊：條件仍成立，復位下一步就再跳（「復位不等於修好」不變）。
3. **還原存檔時，重跑段的範圍乘上存檔時的時間倍率**（模擬時鐘每實際秒走「倍率」秒，存檔每 30 實際秒一次）；改倍率時要求盡快存檔，讓存檔裡的倍率涵蓋存檔點之後跑的那一段。

### Consequences

- 長跑裡 WT012 / WT003 / WT005 多算的不計畫停機（每次多 4 小時以上）不會再出現；準備卡評分裡「把沒事當有事」的那兩張卡也不會再有。
- 倍率 200 時重跑段最長可到 120 × 200 秒；「別的來源寫進 Live session 的遠處讀值」只有在比這更遠時才會被認出來。
- 長跑找到的其他問題（彙整表、潛伏故障、警報不開單、WAL 不縮）另開 WMOM-20261126-08 到 -11。

---

## DEC-20261127-01 — 潛伏的故障不佔機組的故障名額

**日期**：2026-11-27　**狀態**：accepted　**Decision maker**：劉老師（2026-11-27 同意 Claude 的建議：「按照你的建議繼續」）

### Context

72 小時長跑（WMOM-20261126-01）產生的 15 個故障有 5 個嚴重度早就到頂、訊號卻到不了警報門檻（11 月、平均風速 8 m/s 下，變壓器最高 68 °C、門檻 80）。沒有警報就沒有工單、修不掉；故障產生器每台機組同時只放一個，那幾台從此不再發生故障。可選：(a) 只產生到得了門檻的；(b) 例行巡檢發現並修掉；(c) 潛伏太久自己消失；(d) 潛伏的不佔名額。

### Decision

1. **先做 (d)**：嚴重度到頂、從沒跳過機、現在也沒有預期碼成立的故障算「潛伏」（`fault_generator.is_latent`），不算進 `max_active_per_turbine`。故障照樣留在機組上；條件變了（季節、負載）開始報警或跳機時，它又算回名額，只影響之後要不要再產生。
2. **(b) 之後接**：併進例行巡檢卡（WMOM-20261126-05）。定檢工單完工本來就會修掉那台機組的全部故障，所以潛伏故障已經修得掉；巡檢卡要處理的是怎麼把它的徵兆往前排。
3. 不做 (a)：潛伏的劣化是真實風場會有的情況，也是巡檢卡評分要的資料。不做 (c)：故障自己消失不像真的，答案也會變得難對。

### Consequences

- 長跑裡被卡住的 5 台機組之後會再發生故障；一台機組上可能同時有一個潛伏的和一個在劣化的故障。
- 抽樣次數不變（每台每次檢查固定三個數），只有「抽到了之後放不放」的判斷改了：同樣的種子在機組有潛伏故障時，產生的序列會和之前不同。
- 故障紀錄照樣記潛伏的故障（沒有第一次警報時間、沒有工單），之後可以拿來對巡檢卡。

---

## DEC-20261127-02 — 仿真風場的收支：收入由運轉狀態紀錄算，工單完工才把人工與料件寫進帳本

**日期**：2026-11-27　**狀態**：accepted　**Decision maker**：Claude（EPIC-SF 第 6 項，劉老師 2026-11-27「按照你的建議繼續」）。預設值與修復等級對應表劉老師尚未逐項看過

### Context

EPIC-SF 第 6 項要讓成本模組「吃模擬結果」：發電收入、故障與停機的損失、維修支出。WMOM-20260504-11 原本的規格（2026-05）是把收入、少收的錢、支出全部寫進成本帳本。現在監控已經有運轉狀態紀錄（`availability_hourly`：每台機組每小時的發電量、計畫 / 非計畫停機少發的電，可用率就是由它算的，DEC-20261126-04）。

### Decision

1. **收入與少收的錢不寫進帳本，由運轉狀態紀錄 × 電價算**：只有一份來源，和可用率同一個時間基準（風場時鐘），不會兩邊對不上；改電價後重算就好。電價、幣別、人事費率讀成本模組既有的農場設定（K13 為底、`cost_inputs.json` 覆寫）。
2. **工單完工時把支出寫進帳本**（運維閉環 `OmLoop._finish`，人完工與模擬維修班完工都算）：
   - 人工＝實際工時 × 人數 × 每小時人事費；人數取工單人數、修復等級的人數、2 人（爬塔作業）三者最大；農場只給年薪時（K13 的時薪是 0）用年薪 ÷ 1800 小時。
   - 料件＝修掉的故障對應的 K13 修復等級（FTC）的料件費。對應表 `modules/cost/data/z72_repair_classes.json` 是假設值：感測器 2–3（耗材 500）、泵 / 風扇 / 液壓 / 變槳 4–5（5,000）、定子繞組 11（100,000）、主軸承 8（250,000）、沒東西要換的 1（0）。K13 是 4 MW 離岸參考，Z72 2 MW 陸域實際可能較低。
   - 工單有領料單時料件不另算（領料出庫時已入帳）。
   - 每張工單只寫一次（同一個交易裡先查後寫），都是 confirmed；入帳時間用風場時鐘。
   - 帳本只給管理端；備註只寫工單編號、工時、修復等級，不寫故障情境。寫不進去只記 log，不影響完工。
3. **`GET /api/operations/finance`**（主管、永遠強制）：一段時間的發電量、收入、計畫 / 非計畫停機少收的錢、帳本的支出（人工、料件、設備）、淨額，每台機組的收入。帳本的 `revenue_loss` 類不算支出（少收的錢已由運轉狀態紀錄算）。
4. **月報加「發電收入與淨額」**：由 `revenue_provider` 提供（伺服器接到運轉狀態紀錄），沒有資料時不顯示。
5. **這次不做**：設備 / 船機與固定成本（K13 的設備是離岸船機、以年費計，陸域 Z72 要另外定）、料件更換對 RUL 與蒙地卡羅參數的回饋、前端畫面。另開 WMOM-20261127-01。

### Consequences

- 風場自己故障、修復之後，管理端可以直接看到這段時間賺了多少、停機少收多少、修了多少錢。
- 帳本的時間有兩種：領料單用實際時間、工單完工用風場時鐘；時間倍率大時兩者在月報上會落在不同的月份。
- 修復等級表要隨新增故障情境補上（測試會擋）。

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
