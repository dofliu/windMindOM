# windMindOM（風心智運維平台）

> **離岸風場運維廠商工具**：監控 + 庫存派工 + 成本計算 + 報表 + 警報手冊查詢。
> 給運維廠商**管理層 + 現場工程師**雙 persona 使用。
> 從 [digiWindTurbine](https://github.com/dofliu/digiWindTurbine)（物理模擬器 + SCADA 平台）商業化升級而來。

- **產品版本**：v0.8.1（2026-05 baseline）
- **目前狀態（2026-10-22）**：
  - 原路線圖：M1–M4 完成；M5（手冊查詢 + 現場頁）約 75%。
  - 商業時程（M6 PoC / 合約）與實場介接自 2026-10-21 暫緩（[DEC-20261021-01](docs/product/decision_log.md)）。
  - **現行主線是 EPIC-DS 擬真資料源**（進度 95%）：用模擬器產生附標準答案的擬真 Z72 運轉資料，透過三條管道餵給學生專題的 RAG 維修助手做驗證。
  - 以 [`STATUS.yaml`](STATUS.yaml) 為準。
- **參考機型**：Z72（2 MW，Bachmann PLC）
- **設計原則**：Simulator-first —— 所有功能都能在純模擬模式下 demo

一張圖看全貌：[`docs/architecture/windMindOM-architecture.md`](docs/architecture/windMindOM-architecture.md)。

---

## 六大功能 module

| Module | 內容 | 狀態 |
|---|---|---|
| **monitoring** | 14 台 Z72 物理模擬（118 個 SCADA tag）、PLC 保護層（Z72 真實警報目錄 315 碼，設定值依手冊 Appendix D）、16 種故障情境（真故障 10、感測器故障 6）＋ nuisance 情境與風場事件（電網擾動、風向快速變化）；即時模擬 / 產生情境 / 調閱三種資料來源；WS 即時推播、Modbus TCP；EPIC-DS 的標準答案、資料包、WS 回放、OPC UA | ✅（EPIC-DS 進行中） |
| **workflow** | 工單狀態機 + 多階簽核 + 庫存 + 領料派工（雙寫交易模型） | ✅ M3–M4 |
| **cost** | ECN 移植：K13 成本模型、LCOE、Monte Carlo、20 年變動，依風場切換資料集 | ✅ M2 |
| **reporting** | 月報 PDF + 年度預算，KPI + HTML 預覽 | ✅ M4 |
| **knowledge** | 警報碼查 Z72 手冊（研究端預計算的 531 段向量檔，平台只載入 + 查詢）、現場手機頁 | 🟡 M5 約 75% |
| **auth** | JWT（HS256）+ RBAC（員工 / 班長 / 主管 / 財務 / 管理員）+ 前端真登入頁 | ✅ |

產品脈絡見 [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md)。

---

## 現行主線：EPIC-DS 擬真資料源

模擬器產生附**標準答案**的情境（故障排程 → 物理模型 + PLC 保護層 → 讀值與可觀測事件），經三條管道交給外部 RAG 維修助手（學生專題，不在本 repo）；標準答案另外存放，只在評分時對照。

| 管道 | 內容 | 給誰 |
|---|---|---|
| ① 資料包 | `GET /api/scenarios/{id}/pack` 或 `tools/export_scenario_pack.py`：Parquet 讀值 + 10 分鐘統計 + `events.jsonl` | 老師下載後以檔案交付 |
| ② WebSocket 回放 | `/ws/replay`：依模擬時鐘送讀值 / 事件 / 統計，受測端在同一條連線送判斷（伺服器蓋時間） | 受測端用回放 token 連線 |
| ③ OPC UA | `tools/opcua_server.py`（回放）或 `WMOM_OPCUA_ENABLE=true`（即時模擬）：節點 ID＝真實 Bachmann item ID | 受測端匿名唯讀 |

- 介面合約：[`docs/integration/rag_assistant_data_contract_v1.md`](docs/integration/rag_assistant_data_contract_v1.md)（v1.5）
- 學生 starter kit：[`examples/rag_starter_kit/`](examples/rag_starter_kit/)（5 個範例資料包，含健康負樣本、讀取 / 基準助手 / 評分程式、WS 與 OPC UA 客戶端）
- 設計與各階段紀錄：[`docs/product/EPIC-DS_realistic_data_source.md`](docs/product/EPIC-DS_realistic_data_source.md)
- **正式評測**要伺服器開 `WMOM_AUTH_ENFORCE=true`（否則不能建立正式評測，[DEC-20261022-05](docs/product/decision_log.md)）

---

## Quick Start

### 本機開發

```bash
# Backend + simulator + Modbus TCP（預設 port 8100）
pip install -r requirements.txt          # runtime
pip install -r requirements-dev.txt      # 含 pytest / httpx（跑測試用）
python run.py

# Frontend（預設 port 3100，另開一個 terminal）
cd frontend
npm install
npm run dev
```

開 [http://localhost:3100](http://localhost:3100)。

> **登入方式**：前端已實作真登入頁（JWT），dev 模式預設帳號：
> | 帳號 | 密碼 | 角色 |
> |------|------|------|
> | `alice` | `alice123` | EMPLOYEE（現場工程師） |
> | `bob` | `bob123` | LEADER（班長） |
> | `carol` | `carol123` | SUPERVISOR（主管） |
> | `owner` | `owner123` | TREASURY（業主代表） |
>
> 生產環境需設 `WMOM_JWT_SECRET` 環境變數，未設會 raise（安全預設）。

左側選單：風場總覽、風機細節、維護中心、工單管理、成本模型、報表、歷史資料、情境模擬、現場查詢、故障模擬、情境導覽、設定。

### 常用環境變數

| 變數 | 用途 |
|---|---|
| `WMOM_JWT_SECRET` | JWT 簽章金鑰（未設且沒開 `WMOM_DEV_MODE` 時啟動會 raise） |
| `WMOM_AUTH_ENFORCE=true` | 全面強制登入（未開時沒帶 token 的請求退回 dev 行為）；**正式評測必開** |
| `WMOM_DEV_MODE=true` | 僅測試 / demo：跳過職責分離檢查（一人可走完建單到簽核）、沒設金鑰時用隨機 dev 金鑰；正式部署不要開 |
| `WMOM_OPCUA_ENABLE=true` | 即時模擬的 OPC UA server（預設只聽 `127.0.0.1:4840`；`WMOM_OPCUA_HOST` / `WMOM_OPCUA_PORT` 可改） |

### Docker Compose

```bash
docker compose up --build
```

Backend port 8100、Frontend 3100、Modbus TCP 5020。port 設定在 `.env`（從 `.env.example` 複製）。
預設 busy 時可 `python run.py --auto-port` 自動找 port。

---

## 測試

```bash
# Backend（6 module + monitoring/physics + e2e）
python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ \
                  modules/knowledge/tests/ modules/monitoring/tests/ modules/auth/tests/ \
                  tests/ -q
# 2026-10-23：1991 passed / 7 skipped / 1 xfailed（約 7–10 分鐘）

# Frontend（vitest + RTL）
cd frontend && npx vitest run        # 1513 passed
cd frontend && npx tsc --noEmit && npx vite build   # type check + production build
```

CI（`.github/workflows/ci.yml`）每個 PR 都跑以上全部；`auto-merge.yml` 在 CI 綠燈後自動合併 `claude/*` 分支的 PR（標題帶 `[WIP]` 不合併）。

---

## 文件地圖（按閱讀順序）

| 檔案 | 用途 |
|------|------|
| [`CLAUDE.md`](CLAUDE.md) | **開發守則**、repo 角色、commit 規範、各項守則（任何 AI / 新 session 第一個讀） |
| [`docs/architecture/windMindOM-architecture.md`](docs/architecture/windMindOM-architecture.md) | 一張圖看全貌 + EPIC-DS 資料流 + 模擬內部 + 工單狀態機 + 簽核 + 儲存結構 + 時程 |
| [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md) | 產品願景、ICP、功能模組、商業模式、競品 |
| [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md) | M1–M6 路線圖與現行主線 EPIC-DS |
| [`docs/product/EPIC-DS_realistic_data_source.md`](docs/product/EPIC-DS_realistic_data_source.md) | EPIC-DS 設計、各階段定案與已知限制 |
| [`docs/integration/rag_assistant_data_contract_v1.md`](docs/integration/rag_assistant_data_contract_v1.md) | 給受測端的介面合約 v1.5（資料包 / 事件 / 標準答案含 nuisance case / 預測 / 評分 / WS 回放 / OPC UA） |
| [`docs/product/decision_log.md`](docs/product/decision_log.md) | 重大決策 ADR 紀錄（最新 DEC-20261023-02） |
| [`docs/product/MVP_ARCHITECTURE.md`](docs/product/MVP_ARCHITECTURE.md) | modules 設計、外部介接、技術選型 |
| [`STATUS.yaml`](STATUS.yaml) / [`ISSUES.md`](ISSUES.md) / [`TODO.md`](TODO.md) | 進度 / 工作清單 / 短期 dashboard |
| [`docs/API_GUIDE.md`](docs/API_GUIDE.md) | REST / WebSocket 端點規格 |
| [`docs/physics_model_status.md`](docs/physics_model_status.md) | 物理模型完成度（動 monitoring 層時讀） |
| [`docs/legacy/`](docs/legacy/) | digiWT 既有技術筆記 / 搬遷對照 |

---

## Repo 結構

```
windMindOM/
├── modules/              ← 6 大功能 module
│   ├── monitoring/       ← SCADA + 物理模擬器 + PLC 保護層 + 故障引擎；EPIC-DS（標準答案、資料包、WS 回放、OPC UA）
│   ├── cost/             ← ECN K13 成本模型（LCOE / Monte Carlo / 20yr var-fluct）
│   ├── workflow/         ← 工單 + 簽核 + 庫存派工（雙寫交易模型 + 狀態機）
│   ├── reporting/        ← 月報 PDF / 年度預算 / KPI
│   ├── knowledge/        ← 警報查 Z72 手冊（預計算向量檔）
│   └── auth/             ← JWT + RBAC 授權（HS256 / PBKDF2 純 stdlib）
├── shared/               ← Z72 警報目錄、PLC tag 清單、RAG 詞彙、PLC clients
├── examples/
│   └── rag_starter_kit/  ← 學生 RAG 專題 starter kit（範例資料包、讀取 / 評分 / 連線範例）
├── frontend/             ← React + responsive（admin + field 雙路徑 + 真登入頁）
├── tools/                ← CLI：資料包匯出、回放管理、OPC UA 回放、starter kit 建置、警報目錄 / tag 清單建置
├── tests/                ← pytest（physics 驗證、e2e lifecycle、starter kit）
├── docs/                 ← 產品 / 架構 / 介面合約 / 設計 / legacy 文件
├── work-logs/            ← 每日 routine 紀錄
├── templates/            ← work-log / issue / decision 模板
└── .github/workflows/    ← CI（ci.yml：backend pytest + frontend vitest/tsc/build；auto-merge.yml）
```

與其他 7 個來源 repo（digiWindTurbine / ECN / z72_etech / windAILab / RAG_Ultimate / InduSpect / z72hmiNew）的關係，見 [`CLAUDE.md`](CLAUDE.md) §5 與架構文件 §7。
