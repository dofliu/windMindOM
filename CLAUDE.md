# CLAUDE.md — windMindOM 開發守則

> 給 Claude（與其他 AI 助理）在這個 repo 工作時用的精簡指引。
> 完整產品脈絡見 [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md)。
> 任何新 session 開工前**必讀本檔**。

---

## 1. 專案一句話

**離岸風場運維廠商工具**：監控 + 庫存派工 + 成本計算 + 報表 + 警報手冊查詢，給運維廠商管理層 + 現場工程師雙 persona 用。
從 digiWindTurbine（物理模擬器 + SCADA 平台）商業化升級而來。

---

## 2. 任何 session 接手的 3 步必做

1. **讀本檔 CLAUDE.md** — 知道工作守則
2. **讀 [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md)** — 產品定位、ICP、5 大功能
3. **讀 [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md)** + [`STATUS.yaml`](STATUS.yaml) — 知道現在進到哪個 month / module
4. （如有 ISSUES.md）從 `ISSUES.md` 找 `status: open` 的 WMOM-* 認領

---

## 3. 文件入口（按閱讀順序）

| 檔案 | 用途 | 何時讀 |
|------|------|--------|
| **本檔 `CLAUDE.md`** | 工作守則、repo 角色、commit 規範 | 任何新 session 第一個讀 |
| [`docs/architecture/windMindOM-architecture.md`](docs/architecture/windMindOM-architecture.md) | **一張圖看全貌** + 7 張細節圖（系統 / 模組分層 / 工單狀態機 / 簽核 / repo 關係 / DB schema / Gantt） | **第一次接觸 / 對外 demo / partner 對接** |
| [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md) | 產品願景、ICP（運維廠商）、5 大功能、商業模式、競品 | 對齊產品方向時 |
| [`docs/product/MVP_ARCHITECTURE.md`](docs/product/MVP_ARCHITECTURE.md) | 5 modules 設計、外部介接、技術選型 | 設計與實作時 |
| [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md) | M1-M6 6 個月路線圖、每月主要交付 | 規劃 sprint 時 |
| [`docs/product/decision_log.md`](docs/product/decision_log.md) | 重大決策 ADR 紀錄（含 v0.5 → v0.8.1 pivot） | 想改變方向前必讀 |
| [`docs/legacy/digiwt_project_notes.md`](docs/legacy/digiwt_project_notes.md) | 既有 digiWT 物理模型 / SCADA 技術筆記 | 動 monitoring 層時讀 |
| [`docs/API_GUIDE.md`](docs/API_GUIDE.md) | digiWT 既有 40+ REST/WS endpoints 規格 | 動 API 時讀 |
| [`docs/physics_model_status.md`](docs/physics_model_status.md) | 物理模型完成度 | 動物理模型時讀 |
| `STATUS.yaml` / `ISSUES.md` / `TODO.md` | （將於 M1 第一週重建為 windMindOM 版本） | 接手 + 找事做時 |

## 4. Repo 結構與角色

```
windMindOM/                          ← 本 repo（從 digiWindTurbine 進化）
├── api/                             ← FastAPI（既有 + 擴充）
├── modules/                         ← 5 大功能 module（M1 起逐月建立）
│   ├── monitoring/                  ← digiWT 既有 SCADA + simulator（M1 搬入）
│   ├── workflow/                    ← 庫存 + 派工 + 簽核（M3-M4 新做）
│   ├── cost/                        ← ECN 移植（M2）
│   ├── reporting/                   ← 報表生成（M4）
│   └── knowledge/                   ← RAG 警報查手冊（M5）
├── shared/                          ← canonical schema、PLC clients、共用 domain model
├── frontend/                        ← React + responsive design（admin + field 雙路徑）
├── opc_bachmann/                    ← Z72 OPC client（既有，M1 抽到 shared/plc_clients/）
├── tests/                           ← pytest
├── docs/
│   ├── product/                     ← v0.8.1 產品文件 ★ 主要 source of truth
│   ├── legacy/                      ← digiWT 既有技術筆記
│   ├── routines/                    ← daily-workflow.md（M1 從 v0.5 搬入）
│   ├── API_GUIDE.md                 ← digiWT 既有 API 規格（沿用）
│   ├── physics_model_status.md      ← digiWT 既有物理模型狀態（沿用）
│   ├── __Z72UserManual.pdf          ← Z72 手冊（M5 餵 RAG）
│   └── 1040610-Z72_PLC_OPC_TAG_1040510.xlsx ← Z72 PLC tag 對映表
├── work-logs/                       ← 每日 routine 紀錄（M1 起每日新建）
├── templates/                       ← work-log / issue / decision 模板
├── deploys/                         ← docker-compose（single-farm / multi-farm）
└── (root 既有 digiWT 檔案)            ← M1 第一週搬到 modules/monitoring/
```

## 5. 與其他 7 個 repo 的關係

| Repo | windMindOM 對它做什麼 |
|------|---------------------|
| **digiWindTurbine**（原 repo） | 不動，留作研究 / 教學版本；windMindOM 是它的商業化 fork |
| **ECN** | M2 移植進 `modules/cost/`，原 repo archive |
| **z72_etech** | M3-M4 取設計重寫進 `modules/workflow/`（**僅取設計、不取程式**），原 repo archive |
| **z72hmiNew** | 留外面（Z72 服務性 repo） |
| **windAILab** | 留外面（**另一公司業務**）；M6+ HTTP API 介接 AI 故障診斷 |
| **RAG_Ultimate** | 留外面（research line）；M5 提供「策略檔 + 預計算向量檔」給 windMindOM/modules/knowledge/ |
| **InduSpect** | 留外面（independent product）；M6+ HTTP API 介接 AI 視覺定檢 |

## 6. 工作流（每個 session）

### 6.1 開工

```
1. 讀 CLAUDE.md（本檔）+ PRODUCT_VISION + ROADMAP + STATUS.yaml + ISSUES.md
2. 從 ISSUES.md 認領一個 issue（或從 ROADMAP 該月 deliverable 拆 sub-issue）
3. 開新 git 分支：claude/issue-{N}-YYYY-MM-DD
4. 開新 work-log：work-logs/YYYY-MM/YYYY-MM-DD-{slug}.md
5. 進 routine（見 docs/routines/daily-workflow.md）
```

### 6.2 結尾

```
1. work-log 收尾（完成什麼、卡在哪、下次怎麼接手）
2. 更新 STATUS.yaml + ISSUES.md
3. Commit：type(#WMOM-{N}): 描述
4. （人工確認後）git push
```

### 6.3 重大決策

任何「動到架構 / 改變方向 / 重新定位」必須寫進 `docs/product/decision_log.md` 為 DEC-{YYYYMMDD}-{NN}。

## 7. Coding 規範

- **Python**：型別標註必加；docstring Google style；繁中說明
- **命名**：snake_case 變數函式、PascalCase class、UPPER_SNAKE 常數
- **不用 `Any`**（必要時 `# type: ignore[原因]` 並註明）
- **對使用者輸出繁體中文，技術術語保留英文**
- **編輯前先 Read**；CRLF 行尾保留原樣
- **Test-first 原則**（不嚴格 TDD，但每個 module 都要有 test）

## 8. Git / commit 規範

- 主分支：`main`（單 dev 階段直接 push）
- Feature 分支：`claude/issue-{N}-YYYY-MM-DD`
- Commit 訊息：`type(#WMOM-{N}): 描述`
- type ∈ feat / fix / docs / refactor / chore / test
- 帶 `#WMOM-{N}` 編號自動關聯本 repo 的 ISSUES.md

## 9. 任務 ID 格式

- Issue：`WMOM-{YYYYMMDD}-{NN}` （例：WMOM-20260503-01）
- Work-log：`work-logs/YYYY-MM/YYYY-MM-DD-{slug}.md`
- Decision：`docs/product/decision_log.md` 內以 `## DEC-{YYYYMMDD}-{NN}` 標號

WMOM = WindMindOM 縮寫。

## 10. 目前狀態（簡要）

> 進度以 [`STATUS.yaml`](STATUS.yaml) 為準；本節為快照，更新時請同步。

- **產品版本**：v0.8.1（2026-05-02 baseline）
- **Milestone**：**M1–M4 done**（monitoring 既有 + cost + workflow + reporting 皆 100%）；**M5（Knowledge/RAG + 現場 mobile UI）進行中 ~75%**；M6（PoC + 第一筆合約）未開始
- **下次工作**：M5 收尾（客戶手冊擴充 + 一年警報 csv 灌入）+ M6 部署前置；見 [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md) 與 [`ISSUES.md`](ISSUES.md) open 項目
- **第一個客戶目標**：Z72 機型運維廠商 / 2026 Q4 / NT$2-4M 合約

## 11. v0.5 → v0.8.1 重大轉變（必知）

2026-05-02 經過 1 天 5 輪規劃迭代，最終決定：

- ❌ **廢棄**：v0.5 的「windMindOM 整合容器」「Plugin SDK」「4 類 Turbine Adapter ABC」「Workflow Hub 獨立 service」等過度工程
- ✅ **採納**：windMindOM = digiWT 商業化升級版，monolithic 5 modules，外部介接走 API/artifact

詳見 [`docs/product/decision_log.md`](docs/product/decision_log.md) DEC-20260502-06。

## 12. 不要做的事

- **不要在 master/main 直接做 risky 工作**（建分支再合）
- **不要修改其他 7 個來源 repo 的 master 分支**（windMindOM 是獨立 fork）
- **不要 fork 其他 repo 的程式碼進 windMindOM**（用 git submodule / pip install / npm link）
- **不要創建沒列在 ISSUES.md 的工作**（除非開新 issue + 寫進 work-log）
- **不要跳過 work-log**（即使是「只討論不寫 code」的 session 也要有紀錄）
- **不要在 monitoring 層動物理模型而不參考 [`docs/legacy/digiwt_project_notes.md`](docs/legacy/digiwt_project_notes.md)**（避免破壞既有 18/21 quality check 通過的物理一致性）
- **不要動 `geminiService.ts`** ← 但這是 RAG_Ultimate 的事，與本 repo 無關（提醒避免混淆）

## 13. Daily Routine

完整 routine 在 [`docs/routines/daily-workflow.md`](docs/routines/daily-workflow.md)（已於 M1 從 v0.5 搬入）。
精簡版 8 phase：Preflight → Claim → Branch+Log → Implement → Verify → Review → Wrap-up → Commit。

哲學：**一日一項重要工作**。不貪多。

## 14. Claude Code 專屬

如果在 Claude Code 內工作（推薦）：

- 啟動：`cd D:\Project_CodingSimulation\researchTopic\windMindOM && claude`
- Slash commands（`.claude/commands/`，已就緒）：`/daily-start`、`/claim-issue {ID}`、`/review`、`/daily-wrapup`
- Sub-agents（`.claude/agents/`，已就緒）：`code-reviewer`（Python async + 風電領域 + FastAPI 專長）

範本在 `docs/claude-code-templates/`（已就緒）。

## 15. 小提醒

- **第一個客戶定 Z72** — 設計時先以 Z72 為 reference
- **Simulator-first** — 任何功能都要能在純 simulator 模式下 demo（無實場是 sales killer feature）
- **RAG 走「研究端策略檔 + 預計算向量檔」** — windMindOM 內只負責載入 + query，不重新 embed
- **z72_etech 取材選 A** — dev team 自己讀程式產出 design notes（M3-M4 排定）
- **windAILab 是另一公司業務** — AI 故障診斷透過 API 介接，不要嘗試把它整進 windMindOM 內部
- **現場工程師也是 user** — 警報 RAG 與 mobile UI 是 PMF 關鍵，不是 nice-to-have
