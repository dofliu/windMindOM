# windMindOM MVP 架構 v0.8.1

> 版本：v0.8.1（2026-05-02）
> 對應願景：[`PRODUCT_VISION.md`](PRODUCT_VISION.md) v0.8.1
> 對應路線圖：[`ROADMAP.md`](ROADMAP.md)
> 決策來源：[`decision_log.md`](decision_log.md) DEC-20260502-06

---

## 1. 架構哲學

四個守則：

1. **digiWT 為基礎，不重寫**
   既有 `scada_system.py`、`main_architecture.py`、`opc_bachmann/`、`docs/API_GUIDE.md` 等都繼續用，windMindOM 是 digiWT 的擴增。

2. **Module 直接函式呼叫，不做 service mesh**
   5 個 modules 在同一個 Python process 內互相 import，不用 webhook、不用 plugin SDK、不用 message queue。
   M5 客戶上線後若需要拆 service 再拆。

3. **外部介接走 API + research artifact**
   windAILab / RAG_Ultimate / InduSpect 都不是 module，是「外部依賴」：
   - windAILab：HTTP API 介接
   - RAG_Ultimate：交付「策略檔 + 預計算向量檔」（不 runtime 介接）
   - InduSpect：HTTP API 介接

4. **Mobile-first 是現場工程師 view，不是另一個 app**
   用 React responsive design（同一 frontend 程式碼），手機開瀏覽器就能用。不做 native iOS/Android app。

---

## 2. 系統架構（高層）

```
windMindOM/
├── api/                          ← FastAPI（既有 + 擴充）
│   ├── routes/
│   │   ├── monitoring.py         (既有 digiWT 40+ endpoints)
│   │   ├── workflow.py           (新)
│   │   ├── cost.py               (新)
│   │   ├── reporting.py          (新)
│   │   └── knowledge.py          (新)
│   └── auth.py                   (新；JWT)
│
├── modules/
│   ├── monitoring/               ← digiWT 既有的 SCADA + simulator + history
│   │   └── (整 scada_system.py 等檔案搬進這層)
│   ├── workflow/                 ← 新做
│   │   ├── work_order.py
│   │   ├── inventory.py
│   │   ├── approval.py
│   │   └── models.py             (SQLAlchemy)
│   ├── cost/                     ← 移植自 ECN
│   │   ├── engine/               (cost_cal、waiting_time、monte_carlo、var_fluct)
│   │   └── adapter.py            (windMindOM 內部 schema ↔ ECN 計算 schema)
│   ├── reporting/                ← 新做
│   │   ├── monthly_report.py     (PDF 生成)
│   │   ├── annual_budget.py
│   │   └── gantt.py
│   └── knowledge/                ← 新做（RAG）
│       ├── ingest.py             (PDF/csv → chunk → embed → vector store)
│       ├── retrieve.py           (query → top-k chunks)
│       ├── strategy_loader.py    (讀 RAG_Ultimate 提供的策略檔)
│       └── alert_handler.py      (警報事件 → 自動 retrieve)
│
├── shared/                       ← 跨 module 共用
│   ├── scada_schema.py           (canonical SCADA tag、Quality enum 等)
│   ├── plc_clients/              (Z72 OPC client 從 opc_bachmann 抽出)
│   └── domain/                   (風電領域共用 model、單位換算)
│
├── frontend/                     ← React + responsive design
│   ├── admin/                    ← 給管理層 / 主管用（desktop-first）
│   │   ├── dashboard
│   │   ├── workflow            (派工 / 庫存 / 簽核)
│   │   ├── cost                (LCOE / 預算 / Gantt)
│   │   └── reports             (報表中心)
│   └── field/                    ← 給現場工程師用（mobile-first）
│       ├── alerts              (警報列表 + RAG 結果)
│       ├── work-orders         (我的工單)
│       ├── completion          (完工回報 + 拍照 + 庫存扣帳)
│       └── approval            (出庫核准)
│
├── deploys/
│   ├── single-farm/              docker-compose 1 風場
│   └── multi-farm/               docker-compose 多風場 + 多 OEM
│
├── docs/
│   ├── (既有 digiWT 技術文件不動)
│   ├── product/                  ← 本文所在
│   ├── work-logs/                ← 每日 routine 紀錄
│   └── routines/                 ← daily-workflow.md 等
│
├── tests/                        ← pytest
│   ├── modules/
│   │   ├── workflow/
│   │   ├── cost/
│   │   ├── reporting/
│   │   └── knowledge/
│   └── e2e/                      (端到端整合測試)
│
└── (root)
    ├── CLAUDE.md                 ← windMindOM 產品脈絡
    ├── pyproject.toml            ← 統一 Python 設定
    ├── docker-compose.yml        ← 開發用
    └── README.md

External（不在 repo 內）：
├── windAILab API                 (partner; M6+ 介接)
├── RAG_Ultimate artifacts        (research; M5 提供策略檔 + 向量檔)
├── InduSpect API                 (partner; M6+ 介接)
└── z72hmiNew                     (Z72 服務性 repo，留外面)
```

---

## 3. 5 大 module 詳細設計

### 3.1 Monitoring（既有 digiWT，擴充）

來源：digiWT 既有 `scada_system.py` + `main_architecture.py` + `opc_bachmann/` + frontend。

**保留**：
- 14-turbine 物理模擬器（Bastankhah wake、IEC 61400-12 NTF/WVTF 等）
- 11 個 fault scenario
- 104 SCADA tag canonical schema
- Z72 OPC client（Bachmann M1 PV via OpenOPC2）
- REST + WebSocket 40+ endpoints
- SQLite history（M2 升 PostgreSQL + TimescaleDB）

**M1 工作**：把根目錄的 digiWT 檔案搬到 `modules/monitoring/` 子目錄，import 路徑微調。

### 3.2 Workflow（新做，從 z72_etech 取設計）

依 [`decision_log.md`](decision_log.md) DEC-20260502-03，dev team 讀 z72_etech archive 程式碼產出 design notes，重寫 FastAPI + SQLAlchemy。

**3 個子模組**：

#### Work Order（工單）

```python
# modules/workflow/work_order.py 草稿
class WorkOrder(Base):
    id: UUID
    farm_id: UUID
    turbine_id: UUID | None
    fault_event_id: UUID | None
    title: str
    type: str                  # 'corrective' / 'preventive' / 'inspection'
    status: str                # 'draft'/'pending_approval'/'approved'/'in_progress'/'completed'/'cancelled'
    priority: int              # 1-5
    estimated_hours: float
    actual_hours: float | None
    estimated_parts: list[dict]    # [{part_no, qty}]
    actual_parts: list[dict]
    crew_assigned: list[str]
    weather_window_id: UUID | None
    created_by: str
    created_at: datetime
    completed_at: datetime | None
    cost_estimate_amount: float | None
    cost_actual_amount: float | None
    currency: str
```

狀態機：
```
draft → pending_approval → approved → in_progress → completed
                       ↘ rejected → (回 draft 或 cancelled)
```

#### Inventory（庫存）

雙寫設計（append-only InventoryTx + 即時 InventoryBalance 累積）：

```python
class Part(Base):
    id, part_no, name, oem, unit, safety_stock, unit_cost

class InventoryTx(Base):                # append-only
    id, part_id, location_id, tx_type ('in'/'out'/'adjust'/'transfer'),
    quantity, unit_cost_at_tx, work_order_id, timestamp, operator, note

class InventoryBalance(Base):           # 即時餘額（從 InventoryTx 累積）
    part_id, location_id, quantity, last_tx_id
```

#### Approval（簽核）

```python
class ApprovalRequest(Base):
    id, request_type ('work_order'/'inventory_release'/'overtime'),
    target_id, submitted_by, submitted_at, workflow_template_id, status

class ApprovalStep(Base):
    id, request_id, sequence, approver, decision ('pending'/'approved'/'rejected'),
    comment, decided_at
```

### 3.3 Cost（移植自 ECN）

ECN repo 內的 backend 整個搬進 `modules/cost/engine/`，保留：
- `cost_cal/aggregator.py`（成本聚合主流程）
- `cost_cal/{corrective,preventive,fixed,revenue_loss,lcoe}.py`
- `waiting_time/waiting_calculator.py`（VBA `CalcTwaitMission` 移植）
- `monte_carlo/runner.py`
- `var_fluct/bathtub.py`
- `models/`（SQLAlchemy 模型）

**新增**：`modules/cost/adapter.py` — windMindOM 內部 schema（`WorkOrder`、`MaintenanceLog`）⇄ ECN 計算所需的 `WindFarmParams` / `ComponentParams` 等資料結構轉換。

**核心介面**：
```python
def forecast_annual_cost(farm: Farm, year: int) -> CostCalResult: ...
def writeback_actual_cost(work_order: WorkOrder) -> CostLedgerEntry: ...
```

### 3.4 Reporting（新做）

3 個輸出：

#### Monthly Report
給業主回報用的月報。包含：
- 該月 SCADA 可用度
- 完成的工單數 + 工時
- 庫存出入庫摘要
- 警報統計
- LCOE actual vs forecast

實作：用 ReportLab 生 PDF + Jinja 模板。

#### Annual Budget
依歷史失效率 + 預定 PM schedule + weather window，跑 ECN forecast 出年度預算。

#### Gantt
維修排程視覺化（年度層級 + 月份 zoom）。前端用 dhtmlx-gantt 或自製 D3。

### 3.5 Knowledge / RAG（新做）

**核心模型：RAG_Ultimate 提供「策略檔 + 預計算向量檔」，windMindOM 只負責載入 + 查詢。**

```
RAG_Ultimate（research）          →  windMindOM（產品）
─────────────────────────────────────────────────
1. strategy.yaml                  →  讀策略檔
   chunking / embedding / top-k
2. z72_manual_v2026-05.parquet    →  載入向量檔到 ChromaDB
   chunks + embeddings + metadata
3. 指定 embedding model           →  query 時用相同 model encode 問題
─────────────────────────────────────────────────
windMindOM 自己跑：
- 客戶內部 SOP 文件用同一策略 chunk + embed（補充自有知識庫）
- 警報事件 → query → retrieve top-k → 回傳給 frontend
```

#### Strategy 檔範例

```yaml
# config/rag_strategy_z72_manual.yaml （由 RAG_Ultimate 提供）
chunking:
  method: semantic
  size: 512
  overlap: 50
embedding:
  model: BAAI/bge-large-zh-v1.5
  dimension: 1024
retrieval:
  algorithm: hybrid_bm25_vector
  top_k: 5
  rerank: true
  rerank_model: bge-reranker-v2-m3
```

#### Alert handler 流程

```
1. SCADA 監控觸發警報（如 gearbox_temp_high）
2. 警報事件 → AlertHandler.on_alert(event)
3. 構造 query：警報碼 + 機型 + 異常 tag
4. retrieve.py → vector store → top-5 chunks
5. 回傳給 /field/alerts/{id} view
6. 現場工程師手機看到「手冊 §4.3 處置：」+ 相關段落
```

#### 客戶端 vector store

ChromaDB 嵌入式模式（單檔 sqlite-style，部署簡單，不需要外部服務）。客戶端不需要 GPU，只跑 query encode。

#### 升級流程

| 變動 | 影響 | 動作 |
|------|------|------|
| Retrieval params 改（top-k / weight） | 小 | 改 windMindOM 的 strategy.yaml，重啟 service |
| Chunking 改 | 中 | RAG_Ultimate 重切 + 重新交付向量檔；客戶下載新檔 |
| Embedding model 改 | 大 | RAG_Ultimate 重 embed；客戶下載新檔；query 端也要更新 model；可漸進升級（保留舊版直到所有客戶遷移完） |

---

## 4. 兩種 user persona 的 UI 路由

### 4.1 /admin/* — Web admin（管理層）

```
/admin/dashboard         即時 SCADA + 整體 KPI
/admin/farms             多風場列表
/admin/farms/{id}/...    單一風場詳情
/admin/workflow/orders   工單管理
/admin/workflow/inventory 庫存管理
/admin/workflow/approval 簽核中心
/admin/cost/budget       年度預算
/admin/cost/ledger       成本流水
/admin/reports/monthly   月報生成
/admin/settings/...      系統設定（user / role / RAG strategy 切換 等）
```

Desktop-first design（最低支援 1280×720），複雜表格與 dashboard 使用。

### 4.2 /field/* — Mobile-friendly（現場工程師）

```
/field/                   今日待辦 (mobile home)
/field/alerts             警報列表（按優先序）
/field/alerts/{id}        警報詳情 + RAG 處置建議 ★ 核心 view
/field/orders             我的工單
/field/orders/{id}        工單詳情
/field/orders/{id}/done   完工回報（拍照 + 簡單填表）
/field/inventory/quick    快速出庫（QR scan or 搜尋）
/field/approval           我的待簽
```

Mobile-first design（最佳化 375-414px 寬度），支援 web app 加桌面 icon（PWA），不做 native app。

### 4.3 共用 vs 分離程式碼

- 同一個 React app（同一個 build），路由分 /admin 與 /field
- 共用元件：login、user profile、global notification
- 各自的 layout、design system

---

## 5. 外部介接（API + Artifact）

### 5.1 windAILab AI 故障診斷（partner）

```
windMindOM                       windAILab (另一公司)
──────────                       ─────────────
警報事件 + 近期 SCADA  ──HTTPS POST──→ /api/diagnose
                                           │
                                           ▼
                                       AI agent
                                       fault_diagnostician
                                           │
                       ◀──JSON 回應──    根因 + 建議處置 + RUL
        ↓
顯示在 /field/alerts/{id} 的 "AI 分析" tab
（與 RAG 檢索結果並列）
```

**取捨**：
- ✅ 兩家公司商業邊界清楚
- ✅ AI 模型 windAILab 自己升級不影響 windMindOM
- ✅ Pricing 可拆（windMindOM Basic 不含 AI、Enterprise 含）
- ❌ windAILab API 不可用時，windMindOM 的 /field/alerts/{id} 看不到 AI tab（要 graceful degrade）

### 5.2 RAG_Ultimate（research artifact）

不做 runtime API 介接。改為「artifact 交付」：

```
RAG_Ultimate Phase 3 階段成果       →  windMindOM 引用
─────────────────────────────────       ─────────────────
config/strategy_v3.0.yaml          →  config/rag_strategy.yaml
artifacts/z72_manual_v2026-05.parquet →  data/vector_stores/z72_manual.parquet
artifacts/v174_manual_v2026-08.parquet →  (未來支援 Vestas 時)
docs/embedding_model_notes.md      →  reference
```

windMindOM 在啟動時：
1. 讀 strategy.yaml 知道用哪個 embedding model
2. 載入對應 OEM 的 .parquet 檔到 ChromaDB
3. 客戶內部 SOP 用同一策略補進去

### 5.3 InduSpect AI 視覺定檢（partner）

```
windMindOM                       InduSpect (另一獨立產品)
──────────                       ─────────────
工程師上傳定檢照片  ──HTTPS POST──→  /api/inspect/blade
                                          │
                                          ▼
                                     CV model
                                          │
                       ◀──JSON 回應──   缺陷類型 + 位置 + 嚴重度
        ↓
自動生成定檢報告 PDF（windMindOM/modules/reporting）
```

實作時程：M6+，Enterprise 套餐獨立加值。

---

## 6. 資料模型（核心 SQLAlchemy schema）

```python
# modules/shared/models.py（彙總所有 module 的核心 entity）

# ── 既有（從 digiWT 沿用）─────────────────────────
class Farm: ...
class Turbine: ...
class TagMapping: ...      # canonical_tag ↔ oem_tag
class ScadaSample: ...     # TimescaleDB hypertable

# ── 新增（v0.8.1）──────────────────────────────
class FaultEvent:
    id, turbine_id, event_type, severity, triggered_at, cleared_at,
    source ('scada'/'manual'), component, sub_component

class WorkOrder: ...       # 見 §3.2
class Part: ...
class InventoryTx: ...
class InventoryBalance: ...
class ApprovalRequest: ...
class ApprovalStep: ...

class CostLedger:
    id, farm_id, season, year, cost_type, component,
    kind ('forecast'/'actual'), source, material_amount, labour_amount,
    equipment_amount, mob_amount, revenue_loss_amount, downtime_h,
    currency, created_at

class KnowledgeChunk:      # 給 RAG 用（ChromaDB 內存，但 SQLAlchemy 同步 metadata）
    id, document_source, page, chunk_text, embedding_vector_id, oem, model
```

### Database

| 用途 | 技術 |
|------|------|
| 主交易（Workflow / Cost / Approval） | PostgreSQL |
| 時序資料（ScadaSample） | TimescaleDB extension |
| Vector store（KnowledgeChunk embeddings） | ChromaDB 嵌入式 |
| 既有 digiWT history | M1 從 SQLite 升 TimescaleDB |

---

## 7. 部署形態

### 7.1 Demo Mode（Simulator-only）

```
單機 docker-compose:
- postgres + timescale (主交易 + 時序)
- chromadb (內嵌)
- windmindom-api (FastAPI)
- windmindom-frontend (React build static)
- digiwt-simulator (within api process)
```

用於：銷售 demo、培訓、開發測試。**不需要任何客戶資料**。

### 7.2 Pilot Mode（單一客戶）

```
與 Demo Mode 相同，但：
- digiwt-simulator 改為 z72-live-adapter
- 加 OPC tunnel / firewall rule 連到客戶 PLC
- 載入客戶歷史 maintenance_log
- 載入該風場手冊向量檔
- 開 windAILab / InduSpect partner API（如客戶採購 Enterprise）
```

### 7.3 SaaS Mode（M5 之後客戶 ≥ 3 才考慮）

K8s + 多租戶 schema；每個運維廠商獨立 namespace。**不在 v0.8.1 範圍**。

---

## 8. 與其他 repo 的工作切分

| Repo | windMindOM v0.8.1 中的角色 | 我們對它做什麼 |
|------|--------------------------|---------------|
| **windMindOM**（本 repo） | 產品本體 | 加 4 個 module（workflow / cost / reporting / knowledge） |
| **digiWindTurbine**（原 repo） | 研究 / 教學版本 | 不動 |
| **ECN** | 設計 reference | M2 內容移植進 modules/cost/，原 repo archive |
| **z72_etech** | 設計 reference | M3-M4 取設計重寫，原 repo archive |
| **z72hmiNew** | Z72 服務性 repo | 維持獨立 |
| **windAILab** | 另一公司業務 | 不動，M6+ API 介接 |
| **RAG_Ultimate** | research | 不動，M5 提供 strategy.yaml + .parquet |
| **InduSpect** | 獨立產品 | 不動，M6+ API 介接 |

---

## 9. 為什麼這些事**不**做

| 不做 | 為什麼 |
|------|--------|
| Plugin SDK | 過度工程；1-2 人團隊無法維護；M5 客戶上線後若有 partner 才考慮 |
| Workflow Hub 獨立 service | 同一 process 內 import 就好；M5 後若拆 multi-tenant 再拆 service |
| Cost engine 雙向 webhook | 同一 process function call 即可；不必跨 service |
| Multi-tenant SaaS | 第一個客戶都還沒 onboard 不討論 |
| 跨機型 Adapter ABC（v0.5 設計） | digiWT 既有 PLC client 模式直接擴；ABC 留作 design reference 但不寫成 code |
| Native iOS/Android app | React responsive design 夠用；資源不夠維持兩個 codebase |
| AI 故障診斷 / 視覺定檢內建 | 是 partner / independent 產品；介接 API 即可 |
| Z72 以外的 OEM PLC adapter | 第一個客戶跑通再說；不預先建抽象 |

---

## 10. 技術風險與緩解

| 風險 | 機率 | 影響 | 緩解 |
|------|-----|------|------|
| 6 月做不完 | 高 | 高 | 嚴守一月一 module；每月有可 demo 的東西 |
| z72_etech 取設計花太久 | 中 | 中 | 先讀程式骨架，design notes 不必完美；邊寫邊改 |
| RAG_Ultimate Phase 3 strategy 還沒 ready 就要交 artifact | 中 | 中 | 先用 baseline strategy（小參數小模型）做 placeholder；等 Phase 3 出來再升級 |
| 客戶 PLC OPC 連線在現場有 DCOM 問題 | 高 | 中 | digiWT 既有 DCOM 指南；最壞 fallback 用 csv 匯入（adapter 一行 config 切換） |
| Mobile-first /field UI 在低階手機不順 | 中 | 中 | 用 React responsive + 簡單樣式；不依賴重型 lib |
| ECN 移植時遇到計算結果與原 ECN tool 對不上 | 中 | 高 | M2 第一週做 K13 demo dataset 驗證；數字對得上才繼續 |
| 第一個客戶要某個我們沒做的功能（如 Vestas adapter） | 中 | 中 | 簽合約前 scope 寫清楚；超出 scope 的功能加價或下個版本 |

---

## 11. 下一步

依 [`ROADMAP.md`](ROADMAP.md) 進入 M1 Setup phase。

第一個 issue 建議：
- **WMOM-20260503-01 — repo baseline 整理**
  - 把 root 既有 digiWT 檔案搬到 modules/monitoring/
  - 建 modules/{workflow,cost,reporting,knowledge}/__init__.py 占位
  - 建 shared/__init__.py 占位
  - 統一 pyproject.toml（既有 + 新增 deps）
  - root CLAUDE.md 改為 windMindOM 產品脈絡
  - first commit + push
