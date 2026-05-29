# windMindOM（風心智運維平台）

> **離岸風場運維廠商工具**：監控 + 庫存派工 + 成本計算 + 報表 + 警報手冊查詢。
> 給運維廠商**管理層 + 現場工程師**雙 persona 使用。
> 從 [digiWindTurbine](https://github.com/dofliu/digiWindTurbine)（物理模擬器 + SCADA 平台）商業化升級而來。

- **產品版本**：v0.8.1（2026-05 baseline）
- **第一個目標客戶**：Z72 機型運維廠商 / 2026 Q4 PoC + 第一筆合約
- **設計原則**：Simulator-first —— 所有功能都能在純模擬模式下 demo（無實場是 sales killer feature）

---

## 五大功能 module

| Module | 內容 | 狀態 |
|---|---|---|
| **monitoring** | digiWT 既有 SCADA + 物理模擬器（104 SCADA tags、11 fault scenarios、wake / fatigue / RUL 模型） | ✅ 既有 |
| **cost** | ECN 移植：K13 成本模型、LCOE、Monte Carlo、20 年 var-fluct，farm-aware dataset | ✅ M2 done |
| **workflow** | 工單 + 多階簽核 + 庫存 + 領料派工（雙寫交易模型 + 狀態機） | ✅ M3-M4 done |
| **reporting** | 月報 PDF + 年度預算，KPI + iframe HTML preview | ✅ M4 done |
| **knowledge** | RAG 警報查手冊（研究端策略檔 + 預計算向量檔，平台只載入 + query） | 🔜 M5 |

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

開 [http://localhost:3100](http://localhost:3100)。左側選單可看到工單管理（建單→派工→完工→簽核全 lifecycle）、報表、成本、監控等頁。

> **Demo mock login**：`WMOM_DEV_MODE=true python run.py` 可一人扮 Alice/Bob/Carol/Owner 跑完整三階簽核 lifecycle（見 `frontend/services/mockUsers.ts`）。

### Docker Compose

```bash
docker compose up --build
```

Backend port 8100、Frontend 3100、Modbus TCP 5020。port 設定在 `.env`（從 `.env.example` 複製）。
預設 busy 時可 `python run.py --auto-port` 自動找 port。

---

## 測試

```bash
# Backend（workflow + cost + reporting baseline）
python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/
# baseline：570 passed, 1 xfailed

# Frontend（vitest + RTL）
cd frontend && npx vitest run        # 59 passed
cd frontend && npx tsc --noEmit && npx vite build   # type check + production build
```

---

## 文件地圖（按閱讀順序）

| 檔案 | 用途 |
|------|------|
| [`CLAUDE.md`](CLAUDE.md) | **開發守則**、repo 角色、commit 規範（任何 AI / 新 session 第一個讀） |
| [`docs/architecture/windMindOM-architecture.md`](docs/architecture/windMindOM-architecture.md) | 一張圖看全貌 + 7 張細節圖（系統 / 模組分層 / 工單狀態機 / 簽核 / DB schema / Gantt） |
| [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md) | 產品願景、ICP、5 大功能、商業模式、競品 |
| [`docs/product/MVP_ARCHITECTURE.md`](docs/product/MVP_ARCHITECTURE.md) | 5 modules 設計、外部介接、技術選型 |
| [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md) | M1-M6 六個月路線圖 |
| [`docs/product/decision_log.md`](docs/product/decision_log.md) | 重大決策 ADR 紀錄 |
| [`STATUS.yaml`](STATUS.yaml) / [`ISSUES.md`](ISSUES.md) / [`TODO.md`](TODO.md) | 進度 / 工作清單 / 短期 dashboard |
| [`docs/API_GUIDE.md`](docs/API_GUIDE.md) | digiWT 既有 40+ REST/WS endpoints 規格 |
| [`docs/physics_model_status.md`](docs/physics_model_status.md) | 物理模型完成度（動 monitoring 層時讀） |
| [`docs/legacy/`](docs/legacy/) | digiWT 既有技術筆記 / 搬遷對照 |

---

## Repo 結構

```
windMindOM/
├── api/                  ← FastAPI
├── modules/              ← 5 大功能 module
│   ├── monitoring/       ← digiWT SCADA + simulator
│   ├── cost/             ← ECN K13 成本模型
│   ├── workflow/         ← 工單 + 簽核 + 庫存派工
│   ├── reporting/        ← 月報 / 年度預算
│   └── knowledge/        ← RAG 警報查手冊（M5）
├── shared/               ← canonical schema、PLC clients、共用 domain model
├── frontend/             ← React + responsive（admin + field 雙路徑）
├── tests/                ← pytest（含 physics 驗證）
├── docs/                 ← 產品 / 架構 / 設計 / legacy 文件
├── work-logs/            ← 每日 routine 紀錄
└── deploys/              ← docker-compose
```

完整 architecture 與其他 7 個來源 repo（digiWindTurbine / ECN / z72_etech / windAILab / RAG_Ultimate / InduSpect / z72hmiNew）的關係，見 [`CLAUDE.md`](CLAUDE.md) §4-5。
