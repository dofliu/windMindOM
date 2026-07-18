# windMindOM（風心智運維平台）

> **離岸風場運維廠商工具**：監控 + 庫存派工 + 成本計算 + 報表 + 警報手冊查詢。
> 給運維廠商**管理層 + 現場工程師**雙 persona 使用。
> 從 [digiWindTurbine](https://github.com/dofliu/digiWindTurbine)（物理模擬器 + SCADA 平台）商業化升級而來。

- **產品版本**：v0.8.1（2026-05 baseline）
- **目前進度**：M1–M4 done；M5（Knowledge/RAG + 現場 mobile UI）進行中 ~75%；M6（PoC + 合約）auth 基礎層 + 全 router 授權已完成。以 [`STATUS.yaml`](STATUS.yaml) 為準
- **第一個目標客戶**：Z72 機型運維廠商 / 2026 Q4 PoC + 第一筆合約
- **設計原則**：Simulator-first —— 所有功能都能在純模擬模式下 demo（無實場是 sales killer feature）

---

## 六大功能 module

| Module | 內容 | 狀態 |
|---|---|---|
| **monitoring** | digiWT 既有 SCADA + 物理模擬器（104 SCADA tags、11 fault scenarios、wake / fatigue / RUL 模型） | ✅ 既有 |
| **cost** | ECN 移植：K13 成本模型、LCOE、Monte Carlo、20 年 var-fluct，farm-aware dataset | ✅ M2 done |
| **workflow** | 工單 + 多階簽核 + 庫存 + 領料派工（雙寫交易模型 + 狀態機） | ✅ M3-M4 done |
| **reporting** | 月報 PDF + 年度預算，KPI + iframe HTML preview | ✅ M4 done |
| **knowledge** | RAG 警報查手冊（研究端策略檔 + 預計算向量檔，平台只載入 + query） | 🟡 M5 進行中 ~75% |
| **auth** | JWT（HS256）+ RBAC 角色授權 + DB-backed user store + 前端真登入（M6 前提） | ✅ M6-4 done |

詳細產品脈絡見 [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md)；一張圖看全貌見 [`docs/architecture/windMindOM-architecture.md`](docs/architecture/windMindOM-architecture.md)。

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

左側選單可看到工單管理（建單→派工→完工→簽核全 lifecycle）、報表、成本、監控、情境導覽等頁。

> **Demo mock login（legacy）**：`WMOM_DEV_MODE=true python run.py` 可在無 JWT token 時 fallback dev 行為（向下相容）。

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
# baseline：998 collected（含 auth 授權 + router enforcement 測試）

# Frontend（vitest + RTL）
cd frontend && npx vitest run        # ~797 passed（含 LoginPage、GuidedTour 等）
cd frontend && npx tsc --noEmit && npx vite build   # type check + production build
```

---

## 文件地圖（按閱讀順序）

| 檔案 | 用途 |
|------|------|
| [`CLAUDE.md`](CLAUDE.md) | **開發守則**、repo 角色、commit 規範（任何 AI / 新 session 第一個讀） |
| [`docs/architecture/windMindOM-architecture.md`](docs/architecture/windMindOM-architecture.md) | 一張圖看全貌 + 7 張細節圖（系統 / 模組分層 / 工單狀態機 / 簽核 / DB schema / Gantt） |
| [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md) | 產品願景、ICP、功能模組、商業模式、競品 |
| [`docs/product/MVP_ARCHITECTURE.md`](docs/product/MVP_ARCHITECTURE.md) | modules 設計、外部介接、技術選型 |
| [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md) | M1-M6 六個月路線圖 |
| [`docs/product/decision_log.md`](docs/product/decision_log.md) | 重大決策 ADR 紀錄（含 DEC-20260716-01 auth / DEC-20260716-02 footprint） |
| [`docs/product/PROJECT_REVIEW_2026-07-16.md`](docs/product/PROJECT_REVIEW_2026-07-16.md) | 2026-07-16 專案全面檢視報告（F1–F6 發現與建議） |
| [`STATUS.yaml`](STATUS.yaml) / [`ISSUES.md`](ISSUES.md) / [`TODO.md`](TODO.md) | 進度 / 工作清單 / 短期 dashboard |
| [`docs/API_GUIDE.md`](docs/API_GUIDE.md) | digiWT 既有 40+ REST/WS endpoints 規格 |
| [`docs/physics_model_status.md`](docs/physics_model_status.md) | 物理模型完成度（動 monitoring 層時讀） |
| [`docs/legacy/`](docs/legacy/) | digiWT 既有技術筆記 / 搬遷對照 |

---

## Repo 結構

```
windMindOM/
├── modules/              ← 6 大功能 module
│   ├── monitoring/       ← digiWT SCADA + simulator（104 tags、11 fault scenarios）
│   ├── cost/             ← ECN K13 成本模型（LCOE / Monte Carlo / 20yr var-fluct）
│   ├── workflow/         ← 工單 + 簽核 + 庫存派工（雙寫交易模型 + 狀態機）
│   ├── reporting/        ← 月報 PDF / 年度預算 / KPI
│   ├── knowledge/        ← RAG 警報查手冊（ChromaDB + Z72 手冊向量檔）
│   └── auth/             ← JWT + RBAC 授權（HS256 / PBKDF2 純 stdlib）
├── shared/               ← canonical schema、PLC clients、共用 domain model
├── frontend/             ← React + responsive（admin + field 雙路徑 + 真登入頁）
│   ├── components/       ← 含 LoginPage / GuidedTourPage / workflow / reporting / field / tour
│   ├── hooks/            ← useAuth（AuthProvider + JWT token 管理）
│   └── services/         ← authClient + 各模組 API client（自動帶 JWT token）
├── tests/                ← pytest（含 physics 驗證 + e2e lifecycle）
├── docs/                 ← 產品 / 架構 / 設計 / legacy 文件
├── work-logs/            ← 每日 routine 紀錄
├── tools/                ← 工具腳本（vacuum_db 等）
├── templates/            ← work-log / issue / decision 模板
├── .github/workflows/    ← CI（ci.yml: 6 module pytest + vitest/tsc/build；auto-merge.yml）
└── z72SCADA_New/         ← Z72 SCADA 新版資料
```

完整 architecture 與其他 7 個來源 repo（digiWindTurbine / ECN / z72_etech / windAILab / RAG_Ultimate / InduSpect / z72hmiNew）的關係，見 [`CLAUDE.md`](CLAUDE.md) §4-5。
