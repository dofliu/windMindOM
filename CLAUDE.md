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
├── modules/                         ← 6 大功能 module（M1 起逐月建立）
│   ├── monitoring/                  ← digiWT 既有 SCADA + simulator（M1 搬入）
│   ├── workflow/                    ← 庫存 + 派工 + 簽核（M3-M4 新做）
│   ├── cost/                        ← ECN 移植（M2）
│   ├── reporting/                   ← 報表生成（M4）
│   ├── knowledge/                   ← RAG 警報查手冊（M5）
│   └── auth/                        ← JWT + RBAC 授權（M6-4，純 stdlib）
├── shared/                          ← canonical schema、PLC clients、共用 domain model、Z72 警報 / tag 清單
├── examples/rag_starter_kit/        ← 給學生 RAG 專題的 starter kit（範例資料包、讀取 / 基準 / 評分程式、WS 回放客戶端）
├── frontend/                        ← React + responsive design（admin + field 雙路徑 + 真登入頁）
├── opc_bachmann/                    ← Z72 OPC client（既有，M1 抽到 shared/plc_clients/）
├── tests/                           ← pytest
├── docs/
│   ├── product/                     ← v0.8.1 產品文件 ★ 主要 source of truth
│   ├── integration/                 ← 對外介面合約（RAG 助手資料介面合約 v1.2）
│   ├── legacy/                      ← digiWT 既有技術筆記
│   ├── routines/                    ← daily-workflow.md（M1 從 v0.5 搬入）
│   ├── API_GUIDE.md                 ← digiWT 既有 API 規格（沿用）
│   ├── physics_model_status.md      ← digiWT 既有物理模型狀態（沿用）
│   └── __Z72UserManual.pdf          ← Z72 手冊（M5 餵 RAG）
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
- **方向（2026-10-21 DEC-20261021-01）**：商業時程（M6 PoC / 合約 / 客戶接觸）與真實風場 / OPC 介接**暫緩**，先把功能完備。**現行主線 = EPIC-DS 擬真資料源**：模擬器產生附標準答案（ground truth）的擬真 Z72 運轉資料，經 ① 檔案 ② WebSocket 串流 ③ 模仿 Bachmann tag 的 OPC UA server 餵給外部 **RAG 即時維修助手**（學生專題建立，windMindOM 不實作）做驗證。設計與介面合約 v0：[`docs/product/EPIC-DS_realistic_data_source.md`](docs/product/EPIC-DS_realistic_data_source.md)
- **Milestone**：M1–M4 done；M5 ~75%（剩客戶手冊 / 一年警報 csv，隨 M6 暫緩）；M6 deferred（auth 全面完成部分保留）；**EPIC-DS Phase 1a done**（WMOM-20261021-02：Z72 真實警報目錄 `shared/alarm_codes.py` + 11 故障情境改用真實碼）；**Phase 1b-a done**（WMOM-20261021-03-a：故障物理校正到真實保護設定值，`TurbineSpec` 設定值、+5 真實 tag 111→116）；**Phase 1b-b done**（WMOM-20261021-03-b：PLC 保護層 `simulator/physics/plc_protection.py`，警報 / 跳機由訊號觸發、T1/T2 停機、鎖存與重啟上限、修 7↔3）；**Phase 1b-c done**（WMOM-20261021-03-c：monitoring 時間戳全面 UTC tz-aware，既有 DB 開檔一次性轉換）；**-10 done**（切出風速依手冊事件 201：10 分鐘 / 5 秒平均判定、正常停機、20 m/s 回切）；**-11 done**（風場時區 `FarmConfig.timezone`，日夜 / 季節循環依風場當地時刻，資料可跨機器重現）；**Phase 2 done**（WMOM-20261021-04：故障情境標準答案 metadata、批次路徑可觀測事件、`history_events.session_id`、標準答案 `scenario_ground_truth` 表與 `GET /api/scenarios/{id}/ground-truth`）；**Phase 3a done**（WMOM-20261021-05：情境資料包匯出 `server/scenario_pack.py`、`GET /api/scenarios/{id}/pack` / `pack/full`、CLI `tools/export_scenario_pack.py`）；**-12 done**（健康機組偶發 T2 336：修葉片同步誤差、規則照手冊，DEC-20261022-01）；**Phase 3b done**（WMOM-20261021-06：WebSocket 回放 `server/replay.py` + `/ws/replay`、回放 token、單次直播＋練習、伺服器蓋預測 ts，DEC-20261022-02；合約 v1.1 §12）；**Phase 3c done**（WMOM-20261021-07：模仿 Bachmann Z72 tag 的 OPC UA server `server/opcua_server.py`，回放 CLI `tools/opcua_server.py` ＋ 即時模擬 `WMOM_OPCUA_ENABLE`，DEC-20261022-03；合約 v1.2 §13）；**Phase 3d done**（WMOM-20261021-09：介面合約 v1 定稿 [`docs/integration/rag_assistant_data_contract_v1.md`](docs/integration/rag_assistant_data_contract_v1.md)、學生 starter kit `examples/rag_starter_kit/`）
- **警報碼守則**：模擬器、語料、前端用到的 Z72 警報碼一律以 `shared/data/z72_alarm_catalog.json`（xlsx 314 筆 + 手冊 Appendix C）為準，不自創碼或描述；`tests/test_alarm_codes.py`、`modules/monitoring/tests/test_fault_alarm_codes.py` 會擋
- **物理改動守則補充**：新增感測器 / tag 的隨機數一律走 `TurbinePhysicsModel._aux_rng`，不可動主 `_rng` 序列（否則所有已校準的健康輸出都會位移）
- **PLC 保護層守則**：警報 / 跳機只由 `PlcProtection` 依 `TurbineSpec` 設定值判定**製程值**（感測器模型之前）送出；`FaultEngine.alarm_codes` 是情境的預期碼（ground truth），不再有 severity 門檻；故障 tripped 期間以 `model.maintenance_lock` 擋重啟，復位不等於修好（`test_reset_keeps_fault.py`）；改規則或物理後須確認健康風場無訊號事件（`test_plc_integration.py`；12 h 長時間、多起點與 14 種子葉片同步機制見 `test_healthy_blade_sync.py`——健康誤差要遠小於手冊設定值，不靠放寬規則）
- **時間戳守則**：monitoring 一律用 `simulator/time_utils.py`——內部 `utc_now()`（不要再寫 naive 的 `datetime.now()`）、落庫 / API 字串用 `iso_utc()`（固定 `...ffffff+00:00`，SQLite 靠字串字典序比較時間）、外部傳入的字串用 `normalize_iso` / `parse_iso`（naive＝伺服器本地時間）；需要當地時刻的物理輸入（日夜 / 季節循環）用 `to_site_naive(ts, site_tz)`——風場時區（`FarmConfig.timezone`，預設 Asia/Taipei），不是伺服器時區；它把 naive 輸入視為已是風場牆鐘時間（例外於上一條）；建模擬器要帶 `site_timezone=`（broker / 資料集產生都要）
- **盲測守則**：故障根因 / 注入資訊只能進標準答案（`scenario_ground_truth`）；給外部 RAG 的事件一律以 `storage.is_observable_event` 過濾（白名單：PLC 事件與運轉狀態轉換，新事件來源預設不可觀測）；答案卷端點用永遠強制的 `require_roles`；新增故障情境要補 `FaultScenario` 的答案欄位（`test_fault_ground_truth.py` 會擋），`key_signals` 要真的偏離健康機組（`test_fault_threshold_reach.py`）
- **資料包守則**：給受測端的資料只走盲測版資料包（`/pack`，不含 `ground_truth.json`），以檔案交付、受測端不開帳號；manifest 不得帶情境名稱 / 故障排程 / 自訂文字；資料包的 tag 真實性以 `shared/data/z72_plc_tags.json`（`tools/build_z72_plc_tags.py` 從 xlsx 產生）為準；會透露劣化程度或模型參數的模擬量加進 `scenario_pack.MODEL_INTERNAL_TAGS`，key signal 不能選它們（DEC-20261021-03，測試會擋）
- **合約守則**：資料包 / 事件 / 標準答案 / 預測格式以合約 v1 為準；加欄位升次版本（`CONTRACT_VERSION`）、改名 / 刪欄位升主版本並更新合約文件；新增故障情境的 `component` / `category` 要先加進 `shared/data/rag_assistant_vocabulary.json`（唯一來源；kit 的 `vocabulary.json` 由 `tools/build_rag_starter_kit.py` 同步，`tests/test_rag_starter_kit.py` 會擋）；改了 tag 註冊表或資料包格式要重建範例（`python tools/build_rag_starter_kit.py`）
- **回放守則**：受測端只用回放 token 連 `/ws/replay`（不開帳號、看不到情境清單）；回放訊息與盲測版資料包逐筆相同，新增訊息內容要走 `ScenarioReplay` 並維持「與資料包相同、不含答案」（`test_replay.py` 會擋）；預測的 `ts` 一律由伺服器蓋，不接受受測端給的時間；正式評測與練習回放不要開在同一個情境（建回放時預設擋下，`allow_overlap` 才放行）；正式評測的速度受「機組數 × 速度 ÷ 取樣週期 ≤ 1000 筆 / 秒」限制
- **OPC UA 守則**：節點 ID＝真實 OPC DA item ID（`opc_data_reader.py` 的 `BASE_TAGS` 每個都要讀得到，`test_opcua_server.py` 會擋）；讀值欄位與盲測版資料包同一組、值逐位元相同，不加答案或模型內部量；事件碼陣列（`ActiveEventLists`）即時模擬與回放同一套規則；匿名唯讀，只開在教室 / 實驗室網路；正式評測在 server 建好節點並開始監聽後才開播（`tools/opcua_server.py` 的 `load_run` → `start` → `start_clock`）
- **下次工作**：EPIC-DS Phase 4（-08 難度與多樣性：連鎖、感測器故障、多重故障、誤報、負樣本）；見 [`ISSUES.md`](ISSUES.md) EPIC-DS
- **測試**：backend 1833 passed / 7 skipped / 1 xfailed；frontend vitest 1513 passed（2026-10-22）。以各 module `tests/` 為準

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

- **參考機型定 Z72** — 設計時先以 Z72 為 reference；EPIC-DS 資料源只支援 Z72（手冊與真實警報清單都是 Z72）
- **Simulator-first** — 任何功能都要能在純 simulator 模式下 demo（無實場是 sales killer feature）
- **RAG 走「研究端策略檔 + 預計算向量檔」** — windMindOM 內只負責載入 + query，不重新 embed
- **z72_etech 取材選 A** — dev team 自己讀程式產出 design notes（M3-M4 排定）
- **windAILab 是另一公司業務** — AI 故障診斷透過 API 介接，不要嘗試把它整進 windMindOM 內部
- **現場工程師也是 user** — 警報 RAG 與 mobile UI 是 PMF 關鍵，不是 nice-to-have
