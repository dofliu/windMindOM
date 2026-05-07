# windMindOM — Issues

> 本檔案是 windMindOM 的單一 source of truth issue tracker。
> 所有工作都從這裡認領；新工作請開新 issue 並寫進來。
> Issue ID 格式：`WMOM-{YYYYMMDD}-{NN}`。模板見 `templates/issue-template.md`。
>
> Status 流轉：`open → in_progress → done`（或 `blocked`）。
> 每次 session 開工 / 結尾，請更新 issue status 與下方統計表。

---

## 統計

| Status | Count |
|--------|------|
| open | 13 |
| in_progress | 0 |
| blocked | 0 |
| done | 22 |
| **total (active)** | **35** |

最後更新：2026-05-07（**WMOM-20260507-01 前端 UI 改版完成 + 工作規劃整理** — A · Calm Operator + 雙主題；220 px sidebar、5 大頁重畫、共用 `frontend/components/ui/` 10 元件 + `frontend/theme/` system 就位；保留全部 API / hooks 不動。本次同步整理：placeholder 按鈕清單獨立成 WMOM-20260507-02 follow-up（low priority、依 API 成熟度逐項補）；M3 frontend WMOM-19/-20/-21 加上「使用新 ui 元件庫」directive。下一個主軸建議：M3 frontend 接力（-19 工單前端）或 WMOM-24 data quality 修正。）

---

## M1（2026-05）— Setup baseline

### WMOM-20260503-01 — Repo baseline 整理（digiWT → modules/monitoring/）

- **Status**: done（2026-05-03 完成）
- **Milestone**: M1
- **Priority**: critical
- **Estimate**: 2-3 工作天 → **實際半天**（因採「move + sys.path 注入」策略，避開大規模 import 重寫）
- **Owner**: Claude (session 2026-05-03)
- **Completion summary**:
  - ✅ 5 modules（monitoring / workflow / cost / reporting / knowledge）+ shared（schemas / plc_clients / domain）+ tests 骨架就位
  - ✅ digiWT 既有 monitoring 程式（simulator、server、wind_model、scada_system、subsystems、turbine_model、opcua_interface、dashboard、main、common_types、main_architecture、examples、data、wind_farm_data.db、wind_turbine_data.db）全部搬到 modules/monitoring/
  - ✅ opc_bachmann/ 抽到 shared/plc_clients/bachmann/
  - ✅ run.py 注入 sys.path（modules/monitoring 在最前面），既有 `from simulator.x` / `from server.x` import 完全不用改
  - ✅ Dockerfile + docker-compose.yml + .dockerignore 路徑更新（含 DB_PATH、FARM_DATA_DIR、volume mount、container_name）
  - ✅ docs/legacy/digiwt_directory_layout.md 搬遷對照表 + sys.path 策略 + 影響相對路徑分析 + 驗證紀錄
  - ✅ 6 項 smoke test 全通過：legacy import、modern import、5 modules 全 importable、18-秒模擬跑出 109 SCADA tag、FastAPI app 67 routes 載入、run.py compile 通過
- **Decision resolved**: pyproject.toml 整合**未做**（保留 requirements.txt），下個 issue 處理 — 跟搬遷脫鉤可降低 risk
- **Follow-up**：
  - ✅ 完整跑 `python run.py` + 開 browser 看 dashboard（2026-05-03 用戶截圖確認 — 14 台 WTG OPERATING、3.55 MW、6.2 m/s、台中港曲風場 active farm 正確載入、5-min trend 即時更新）
  - ✅ `docker-compose` 設定靜態驗證 PASS（2026-05-03 — YAML parse、COPY directives、env vars (DB_PATH/FARM_DATA_DIR)、volume mount、相對路徑等價性 全部 OK）；實際 `docker compose up --build` 因本機未裝 Docker Desktop **deferred**（留給部署 partner / overnight 跑）
  - ✅ 重跑 examples/data_quality_analysis.py（短版）2026-05-03：0.17h × 5 turbines / 3060 rows / wall 3.7s → 15/16 quality check pass、風速↔功率 r=+0.970、1P振動↔轉速 r=+0.944、無 NaN、無 out-of-range；唯一 ⚠ 是定子溫-功率 r=-0.313 偏低，屬 duration artifact（短 sim 沒熱平衡時間，跟搬遷無關）。Pre-migration baseline 已備份；完整 2h 對照留給 overnight session
  - ⬜ Mass-rewrite imports 為 fully qualified `modules.monitoring.*` 形式（M1-M2 穩定後另開 issue）
  - ⬜ 盤點 modules/monitoring/main.py + main_architecture.py 是否為 dead code
- **Reference**:
  - [`docs/legacy/digiwt_directory_layout.md`](docs/legacy/digiwt_directory_layout.md)（搬遷對照表）
  - [`work-logs/2026-05/2026-05-03-repo-baseline-and-tracking-files.md`](work-logs/2026-05/2026-05-03-repo-baseline-and-tracking-files.md)（session 紀錄）

<details><summary>📜 原始 issue description（保留歷史 / 開工時範圍）</summary>

- **Description**:
  把根目錄既有 digiWT 檔案搬到 `modules/monitoring/`，建立 4 個空 module 占位
  （`workflow/`、`cost/`、`reporting/`、`knowledge/`），以及 `shared/` / `tests/`
  / `frontend/` 的標準骨架。確認搬完後 import path、Docker、既有 18/21 quality
  check 仍能跑通；不破壞物理一致性。
  - 子任務：
    1. 建立 `modules/{monitoring,workflow,cost,reporting,knowledge}/` 與 `__init__.py` 占位
    2. 建立 `shared/{schemas,plc_clients,domain}/` 占位（M1 後續 issue 才會放東西）
    3. 把 root 的 `simulator/`、`server/`、`scada_system.py`、`turbine_model.py`、
       `wind_model.py`、`subsystems.py`、`opcua_interface.py`、`dashboard.py`、
       `main.py`、`run.py`、`common_types.py`、`main_architecture.py`、
       `wind_farm_data.db`、`wind_turbine_data.db`、`config/`、`data/`、
       `examples/` 搬進 `modules/monitoring/`
    4. 把 `opc_bachmann/` 抽到 `shared/plc_clients/bachmann/`
    5. 修 import path（`from simulator.x` → `from modules.monitoring.simulator.x` 等）
    6. 更新 `Dockerfile` / `docker-compose.yml` 路徑
    7. 跑 `python -m pytest`（如有）+ 啟動 backend 確認 endpoint 還活著
    8. 留一個 `docs/legacy/digiwt_directory_layout.md` 紀錄搬遷對照表
- **Deliverable**:
  - `modules/monitoring/...`（搬遷後檔案）
  - `modules/{workflow,cost,reporting,knowledge}/__init__.py`（空殼）
  - `shared/plc_clients/bachmann/`
  - `docs/legacy/digiwt_directory_layout.md`（搬遷對照表）
  - 更新後的 `Dockerfile`、`docker-compose.yml`、`pyproject.toml`（或 requirements.txt）
- **Decision needed**: 是否 M1 就把 `pyproject.toml` 整合好（vs M2 才做）→ 預設 M1 做
- **Depends on**: -
- **Blocks**: WMOM-20260503-02（v0.5 資產搬入路徑會用到新結構）、WMOM-20260603-* (M2 cost 移植)
- **Reference**:
  - `docs/product/MVP_ARCHITECTURE.md`（5 modules 設計）
  - `docs/legacy/digiwt_project_notes.md`（既有物理層細節）
  - `CLAUDE.md` §4 repo 結構

</details>

---

### WMOM-20260503-02 — 搬入 v0.5 有用資產

- **Status**: done（2026-05-04 完成）
- **Milestone**: M1
- **Priority**: high
- **Estimate**: 0.5-1 工作天 → **實際 ~2 小時**（多數「搬入」項已在更早 session 完成現代化，本 session 主力為 inventory + decision 紀錄）
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ Pitch deck baseline 入庫：`docs/sales/pitch_deck_v0.5_baseline.{md,pptx}`（從 `../windFarmOM_bk/docs/pitch_deck.{md,pptx}` 複製）
  - ✅ Diff 比對 `docs/routines/daily-workflow.md` (v1.1, 2026-05-03)、`templates/*.md`、`docs/claude-code-templates/` → 已現代化，無需搬
  - ✅ 寫 `docs/sales/v05_assets_inventory.md`（搬入 / 已現代化 / 棄用三類對照）
  - ✅ `docs/product/decision_log.md` 追加 DEC-20260504-01（v0.5 棄用資產清單明列化）
- **Reference**:
  - [`docs/sales/v05_assets_inventory.md`](docs/sales/v05_assets_inventory.md)（資產對照清單）
  - [`docs/product/decision_log.md`](docs/product/decision_log.md) DEC-20260504-01
  - [`work-logs/2026-05/2026-05-04-migrate-v05-assets.md`](work-logs/2026-05/2026-05-04-migrate-v05-assets.md)（session 紀錄）

<details><summary>📜 原始 issue description</summary>

- **Description**:
  從 v0.5（windMindOM 早期 prototype）搬入仍有用的資產，不要重複造輪子：
  - `pitch_deck.md` / `pitch_deck.pptx`（給客戶用的簡報）→ `docs/sales/`
  - `daily-workflow.md`（已搬入 `docs/routines/`，確認最新版）
  - `claude-code-templates/`（已存在 `docs/`，盤點是否完整）
  - `templates/`（已存在 root，盤點 work-log / issue / decision 模板是否齊全）
  - 其他 v0.5 規劃文件中**已被 v0.8.1 取代的廢棄**（如舊版 plugin SDK 設計）→ 不搬，但在 `docs/product/decision_log.md` 紀錄為何丟棄
- **Deliverable**:
  - `docs/sales/pitch_deck_v0.5_baseline.{md,pptx}`（先存底，v0.8.1 改版見 WMOM-20260503-04）
  - `docs/routines/daily-workflow.md`（已存在）
  - `templates/`（盤點清單）
  - `docs/claude-code-templates/`（盤點清單）
- **Depends on**: WMOM-20260503-01（搬遷後新結構就位才好搬）
- **Blocks**: WMOM-20260503-04（pitch deck 改版前要先有 v0.5 baseline）
- **Reference**: `CLAUDE.md` §3 文件入口

</details>

---

### WMOM-20260503-03 — Root CLAUDE.md 改為 windMindOM 產品脈絡

- **Status**: done
- **Milestone**: M1
- **Priority**: high
- **Estimate**: 0.5 工作天
- **Owner**: 劉老師（pre-session, 2026-05-02）
- **Description**:
  既有 root `CLAUDE.md` 已於 2026-05-02 baseline commit 改為 windMindOM v0.8.1
  產品脈絡（5 modules、ICP、其他 7 repo 關係、daily routine、coding 規範）。
  既有 digiWT 版本的 root CLAUDE.md 已備份在 `docs/legacy/`（如未備份則本 issue 含此項）。
- **Deliverable**:
  - `CLAUDE.md`（已是 windMindOM v0.8.1 版本）
  - `docs/legacy/digiwt_CLAUDE.md`（如尚未備份，補上）
- **Reference**: 本檔案開頭 `CLAUDE.md` §1-15

---

### WMOM-20260503-04 — Pitch deck v0.8.1 改版

- **Status**: done（2026-05-04 完成）
- **Milestone**: M1
- **Priority**: high
- **Estimate**: 1-2 工作天 → **實際半天**（先 outline 對齊、後 build；用戶選 Journal 主題不影響故事線）
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ Outline 先 source of truth：[`docs/sales/pitch_deck_v0.8.1_outline.md`](docs/sales/pitch_deck_v0.8.1_outline.md)（10 主 + 2 附錄、每張視覺指示、v0.5→v0.8.1 9 項差異對照）
  - ✅ 主 deck 12 張：[`docs/sales/pitch_deck_v0.8.1.pptx`](docs/sales/pitch_deck_v0.8.1.pptx) + PDF（760 KB / 12 頁）
  - ✅ Onepager A4 直式：[`docs/sales/pitch_deck_v0.8.1_onepager.pptx`](docs/sales/pitch_deck_v0.8.1_onepager.pptx) + PDF（426 KB / 1 頁）
  - ✅ **Journal 主題**（米白墨綠期刊風 / 學術襯線書冊風） — 用戶決定取代原 Navy
  - ✅ Builder script: `tools/pitch_deck/build_v081_pitch.js` + `build_v081_onepager.js`（pptxgenjs，可重 build）
  - ✅ QA：python-pptx structural check 12 張 + 表格 8×8 + 頁腳 / 章節序號齊全
  - ✅ PDF 轉檔：PowerPoint COM via PowerShell（本機無 LibreOffice 的解法）
- **Reference**:
  - [`docs/sales/pitch_deck_v0.8.1_outline.md`](docs/sales/pitch_deck_v0.8.1_outline.md)（大綱 source of truth）
  - [`tools/pitch_deck/`](tools/pitch_deck/)（pptxgenjs builder）
  - [`work-logs/2026-05/2026-05-04-pitch-deck-v081.md`](work-logs/2026-05/2026-05-04-pitch-deck-v081.md)（session 紀錄）

<details><summary>📜 原始 issue description</summary>

- **Description**:
  把 v0.5 pitch deck（windMindOM 早期 framework 定位）改寫為 v0.8.1
  「**離岸風場運維廠商工具**」定位。
  - 主視覺改為「Operator-focused tool」
  - 套餐改為 Operator Basic / Pro / Enterprise（取代 v0.5 的「整合容器」分層）
  - 加上 5 modules 一張圖（monitoring / workflow / cost / reporting / knowledge）
  - 加上 simulator-first demo flow（**無實場可成立**是 sales killer feature）
  - 第一個目標客戶：Z72 機型運維廠商
  - 用 `pptx-jliu-style` skill 出 Navy 主題（科技類）→ 改 Journal
- **Deliverable**:
  - `docs/sales/pitch_deck_v0.8.1.pptx`
  - `docs/sales/pitch_deck_v0.8.1_outline.md`（投影片大綱）
  - 一頁 onepager PDF（給 cold email 附件用）
- **Depends on**: WMOM-20260503-02（先有 v0.5 baseline 才能改版）
- **Blocks**: WMOM-20260503-05（接觸客戶要先有可寄的 deck）
- **Reference**:
  - `docs/product/PRODUCT_VISION.md`（套餐分層、ICP）
  - `CLAUDE.md` §15 「第一個客戶定 Z72」

</details>

---

### WMOM-20260503-05 — Friendly 客戶接觸名單

- **Status**: in_progress（infrastructure done 2026-05-04；contact 持續整月）
- **Milestone**: M1
- **Priority**: medium
- **Estimate**: 0.5 工作天（infrastructure）+ 持續整月（contact）
- **Owner**: 劉老師（contact 執行）/ Claude session 2026-05-04（infrastructure）
- **Infrastructure done（2026-05-04）**:
  - ✅ [`docs/sales/friendly_contacts.md.template`](docs/sales/friendly_contacts.md.template) — 4 大渠道分類（NCUT 學界 / Bachmann / 第三階段運維分包商 / 業界研討會）+ contact entry 模板
  - ✅ [`docs/sales/outreach_script.md`](docs/sales/outreach_script.md) — cold email 3 範本（介紹 / cold / follow-up）+ 30 分鐘 demo agenda + objection handling FAQ + 寄送 logistics
  - ✅ [`docs/sales/customer_feedback/README.md`](docs/sales/customer_feedback/README.md) + [`_TEMPLATE.md`](docs/sales/customer_feedback/_TEMPLATE.md) — demo 後 24 小時內紀錄結構
  - ✅ `.gitignore`：`friendly_contacts.md` + `customer_feedback/202*-*-*-*.md` 不入 git（PII），但模板與 README 可 commit
- **Pending（劉老師執行）**:
  - ⬜ `cp friendly_contacts.md.template friendly_contacts.md`，從 4 大渠道盤 5-10 位潛在 contact
  - ⬜ 寄出 3-5 封 cold email（用 outreach_script.md 範本 A / B）
  - ⬜ 約到第一場 30 分鐘 demo（M1 月底前）
  - ⬜ Demo 後 24 小時內寫 `customer_feedback/YYYY-MM-DD-{客戶代號}.md`
- **完成定義**：1+ 場 demo done + feedback 寫進 customer_feedback/ → 標 done
- **Depends on**: WMOM-20260503-04（done — deck 已就位）
- **Reference**:
  - `docs/product/PRODUCT_VISION.md` §ICP（運維廠商）
  - `work-logs/2026-05/2026-05-04-friendly-contacts.md`（infrastructure session 紀錄）

---

## M2（2026-06）— Cost module（從 ECN 移植）

### WMOM-20260504-01 — ECN K13 baseline + 移植規劃（discovery-first）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: critical（**M2 第一個 issue**，blocking 所有後續 cost migration）
- **Estimate**: 0.5 工作天
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 在 ECN 跑 4 支 test 全 pass（cost_cal + waiting_time × 3 + monte_carlo），抓到 K13 黃金數字
  - ✅ 寫 [`docs/legacy/ecn_k13_baseline.md`](docs/legacy/ecn_k13_baseline.md)：K13 reference vs computed 偏差表 + 4 季 breakdown + Monte Carlo + LCOE = 72.94 EUR/MWh + 重跑 SOP
  - ✅ 寫 [`docs/legacy/ecn_engine_inventory.md`](docs/legacy/ecn_engine_inventory.md)：4 submodule × ~3,000 行 inventory + 跨模組依賴 + migration mapping + 風險評估 + 不移的東西明列
  - ✅ 在 `modules/cost/` 建 skeleton（10 個 sub-namespace `engine/{cost_cal,waiting_time,monte_carlo,var_fluct}` + `models/` + `routers/` + `schemas/` + `tests/` + `data/demo/`），import smoke test pass
  - ✅ 確認 ECN engine **完全 pure compute**（grep 無 `app.models / app.schemas / app.config` 引用），migration 邊界乾淨
- **Key decisions documented**:
  - windMindOM `modules/cost/` 結構鏡像 ECN backend/app/，降低移植 risk
  - 只移 engine（4 submodule），**不**移 models / routers / schemas / database / utils — windMindOM 自己做
  - 推薦 migration 順序：waiting_time → cost_cal → monte_carlo → var_fluct（總估時 3-3.5 天）
  - 浮點誤差容忍：< 1e-6（嚴格 numerical equivalence）
- **Reference**:
  - [`docs/legacy/ecn_k13_baseline.md`](docs/legacy/ecn_k13_baseline.md)（K13 黃金數字）
  - [`docs/legacy/ecn_engine_inventory.md`](docs/legacy/ecn_engine_inventory.md)（移植計畫 + risk）
  - [`work-logs/2026-05/2026-05-04-ecn-k13-baseline.md`](work-logs/2026-05/2026-05-04-ecn-k13-baseline.md)（session 紀錄）

---

### WMOM-20260504-08 — Cost dashboard frontend（M2 收官）

**Polish update（2026-05-04 同日）**：
- VarFluct chart 軸 label / legend 重疊修復（移除過長右軸 label，靠 legend 顏色說明；增加 chart 高度 + bottom margin）
- 全頁中文 i18n（用既有 `useI18n` hook + `ui()` 模式，與 maintenance / history page 一致）：
  panel title / subtitle / button / metric label / chart legend keys / season names 全雙語
- 預設 lang 從 `localStorage.windFarmLang` 讀（既有設計，預設 zh）
- Vite build 仍 pass（0 TS errors）

---


- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high
- **Estimate**: 1-2 工作天 → **實際 ~30 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ `frontend/services/costService.ts` (160 行) — TypeScript API client + 完整 type chain 對齊 backend pydantic schemas
  - ✅ `frontend/hooks/useCostData.ts` (70 行) — `useAsync` 通用 hook，4 個 endpoint state（data/loading/error/run）
  - ✅ `frontend/components/CostPage.tsx` (440 行) — 4 panel dashboard：
    - **ForecastPanel**: 6 metric cards + 4 季 stacked bar chart（auto-run on mount）
    - **LCOEPanel**: capex/discount input → LCOE breakdown
    - **MonteCarloPanel**: n_sim/seed input → P10/P50/Mean/P90 bar
    - **VarFluctPanel**: 20 年 line chart（Total Effort + Multiplier + Availability 三線）
    - 共用 UI bits: MetricCard / Panel / Btn / ErrorBox + money formatter
  - ✅ `frontend/App.tsx` 加 nav button (Cost icon) + view router case
  - ✅ Vite production build pass：710 modules, 1020 KB（含 recharts），0 TS errors
- **可即時測試**:
  ```bash
  python run.py                    # backend
  cd frontend && npm run dev       # frontend
  # → http://localhost:5173 → 點 nav "Cost"
  ```
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-cost-frontend.md`](work-logs/2026-05/2026-05-04-cost-frontend.md)
  - [`frontend/components/CostPage.tsx`](frontend/components/CostPage.tsx)

---

### WMOM-20260504-07 — FastAPI cost router（4 endpoints）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high
- **Estimate**: 0.5-1 工作天 → **實際 ~25 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ `modules/cost/routers/cost_router.py` (180 行) — 4 個 POST endpoints：
    - POST /api/cost/forecast    — CostForecastRequest → CostForecastResponse
    - POST /api/cost/lcoe         — LCOERequest → LCOEResponse
    - POST /api/cost/monte-carlo  — MonteCarloRequest → MonteCarloResponse
    - POST /api/cost/var-fluct    — VarFluctRequest → VarFluctResponse
  - ✅ Mount 進主 FastAPI app (`modules/monitoring/server/app.py`)
  - ✅ `modules/cost/tests/test_cost_api.py` (160 行) — **11 tests 全 PASS**：
    - 4 endpoints × bit-perfect baseline 比對
    - validation：unknown dataset → 422、n_simulations < 10 → 422
    - var_fluct custom bathtub override / constant model
  - ✅ 整 modules/ pytest：43 PASS + 1 XFAIL（cost 41 + monitoring 3，6.22s）
  - ✅ Smoke test 主 app 4 routes 成功 mount 在 `/api/cost/*`
- **可即時測試**: `python run.py` → `http://localhost:8100/docs` (FastAPI auto OpenAPI swagger)
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-cost-api.md`](work-logs/2026-05/2026-05-04-cost-api.md)
  - [`modules/cost/routers/cost_router.py`](modules/cost/routers/cost_router.py)
  - [`modules/cost/tests/test_cost_api.py`](modules/cost/tests/test_cost_api.py)

---

### WMOM-20260504-09 — SQLite 並發 lock 修復（hotfix）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M1 follow-up（hotfix，不在原規劃 issue 內）
- **Priority**: high（production crash — 用戶實際跑 monitoring 時撞到）
- **Estimate**: 0.25 工作天 → **實際 ~25 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Trigger**: 劉老師執行 `python run.py` 時 log 噴 `sqlite3.OperationalError: database is locked`，500 Error 在 `/api/maintenance/technicians`
- **Root cause**:
  - `Storage._get_conn()` 與 `FarmRegistry._get_conn()` 開 SQLite 沒設 PRAGMA
  - 預設 `journal_mode=DELETE` + `busy_timeout=0` → 撞鎖立刻 raise
  - 4 thread 並發（FastAPI handlers / DataBroker write / maintenance DELETE / simulator）撞鎖機率高
- **Completion summary**:
  - ✅ 新增 `modules/monitoring/server/sqlite_utils.py` (55 行) — `open_sqlite()` helper 統一設 WAL + synchronous=NORMAL + busy_timeout=5000
  - ✅ 改 `storage.py` `_get_conn` + `_init_db` 用新 helper
  - ✅ 改 `farm_registry.py` `_get_conn` 用新 helper
  - ✅ 新增 `modules/monitoring/tests/test_storage_concurrency.py` (130 行) — 3 tests
    - `test_pragmas_applied` — 驗證 connection 真的有 WAL + busy_timeout
    - `test_concurrent_read_write_no_lock` — 4 thread 並發 1 秒，0 lock errors（reader×2 + writer + deleter，~8,800 ops）
    - `test_storage_basic_crud_still_works` — regression: CRUD 仍正常
  - ✅ 整 modules/ test suite：32 PASS + 1 XFAIL（cost 30 + monitoring 3）
- **未動**: `modules/monitoring/scada_system.py` 的 4 個 sqlite3.connect()（看似 legacy，與 Storage 不共用 DB path，未在 crash 路徑上）
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-sqlite-lock-fix.md`](work-logs/2026-05/2026-05-04-sqlite-lock-fix.md)
  - [`modules/monitoring/server/sqlite_utils.py`](modules/monitoring/server/sqlite_utils.py)
  - [`modules/monitoring/tests/test_storage_concurrency.py`](modules/monitoring/tests/test_storage_concurrency.py)

---

### WMOM-20260504-06 — Cost adapter + pydantic schemas（M2 抽象層）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high
- **Estimate**: 0.5-1 工作天 → **實際 ~1 小時**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ `modules/cost/adapter.py` (393 行)：`EngineParams` dataclass + `load_k13_engine_params(stochastic=)` + 4 個 result→response 轉換器
  - ✅ `modules/cost/schemas/cost_schemas.py` (198 行)：10 個 pydantic models（Request × 4 + Response × 4 + 子 model × 2）
  - ✅ Refactor 3 個 engine test 用新 loader：
    - test_k13_equivalence.py: 362 → 155 行（省 207）
    - test_monte_carlo.py: 370 → 203 行（省 167）
    - test_var_fluct.py: 402 → 243 行（省 159）
    - test_waiting_time.py 不動（讀 metocean CSV，scope 不重複）
  - ✅ `modules/cost/tests/test_adapter.py` (207 行)：9 tests 涵蓋 K13 loader + 4 個 result→response + pydantic round-trip + regression gate
  - ✅ 整 cost module pytest：**29 PASS + 1 XFAIL**（4.17s，比 -05 多 9 個 adapter test）
- **Code metrics**: tests 1439 → 1113（省 326）；adapter + schemas +591；淨 +265 行
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-cost-adapter.md`](work-logs/2026-05/2026-05-04-cost-adapter.md)
  - [`modules/cost/adapter.py`](modules/cost/adapter.py)
  - [`modules/cost/schemas/cost_schemas.py`](modules/cost/schemas/cost_schemas.py)
  - [`modules/cost/tests/test_adapter.py`](modules/cost/tests/test_adapter.py)

---

### WMOM-20260504-05 — `engine/var_fluct/` 移植（4 engine 收官）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: medium
- **Estimate**: 0.5 工作天 → **實際 ~25 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 3 engine files (360 行) 從 ECN 複製 + sed 改 import + grep 確認無 ECN-specific 依賴
  - ✅ ECN 沒有對應 unit test → **從零寫 9 tests**
  - ✅ `tools/pin_var_fluct.py` 取 ~30 個 pinned 數字（20 年 bathtub 曲線 + 6 邊界 + Year 1/10/20 完整 YearResult + Summary）
  - ✅ `modules/cost/tests/test_var_fluct.py` 9 tests 全 PASS：
    - bathtub_default_curve / bathtub_edges / bathtub_curve_helper
    - varfluct_lifetime_length / year_1_pinned (early peak 1.5x) / year_10_pinned (mid life) / year_20_pinned (late peak 2.0x) / summary_pinned / year_index_consistency
  - ✅ Cross-test invariant: Year 10 var_fluct availability == -03 cost_cal pinned baseline (0.9402)
- **整 cost module pytest**: **20 PASS + 1 XFAIL**（4.88s，含 -02/-03/-04/-05 累計 21 tests）
- **4 個 ECN engine submodule 全部 ported**: cost_cal + waiting_time + monte_carlo + var_fluct
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-var-fluct-migration.md`](work-logs/2026-05/2026-05-04-var-fluct-migration.md)（session 紀錄）
  - [`modules/cost/tests/test_var_fluct.py`](modules/cost/tests/test_var_fluct.py)

---

### WMOM-20260504-04 — `engine/monte_carlo/` 移植 + LCOE bit-perfect

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high
- **Estimate**: 0.5 工作天 → **實際 ~25 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 4 engine files (674 lines) 從 ECN 複製到 `modules/cost/engine/monte_carlo/`，sed 改 import
  - ✅ Grep 確認 monte_carlo 完全乾淨（無 ECN-specific 依賴），跟 cost_cal 一樣
  - ✅ ECN 用 `np.random.default_rng(seed)` modern API，seed=42 完全 reproducible
  - ✅ `tools/pin_monte_carlo.py` 一次性工具取 21 個 pinned 數字（4 deterministic + 11 percentile + 6 LCOE，含 LCOE = 72.94 EUR/MWh）
  - ✅ `modules/cost/tests/test_monte_carlo.py` 5 tests 全 PASS：
    - `test_mc_deterministic_pinned` — 4 metric bit-perfect（reuse cost_cal）
    - `test_mc_percentiles_pinned` — 11 percentile bit-perfect
    - `test_mc_lcoe_pinned` — LCOE 72.94 EUR/MWh bit-perfect
    - `test_mc_sanity_checks` — P10<P50<P90 / std>0 / CDF monotonic
    - `test_mc_tornado` — bars > 0 且 cost_range 排序正確
- **整個 cost module pytest**: 11 PASS + 1 XFAIL（含 -02/-03/-04 累計 12 tests）
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-monte-carlo-migration.md`](work-logs/2026-05/2026-05-04-monte-carlo-migration.md)（session 紀錄）
  - [`modules/cost/tests/test_monte_carlo.py`](modules/cost/tests/test_monte_carlo.py)

---

### WMOM-20260504-03 — `engine/cost_cal/` 移植 + K13 equivalence（M2 主菜）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: critical（M2 主菜，K13 主驗證 gate）
- **Estimate**: 1-1.5 工作天 → **實際 ~30 分鐘**（SOP 第二次跑就快很多）
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 8 engine files (957 lines) 從 ECN 複製到 `modules/cost/engine/cost_cal/`，sed 改 import
  - ✅ Grep 確認 cost_cal **完全乾淨**：無任何 ECN-specific 依賴（比 waiting_time 更乾淨，不需要 stub 任何 function）
  - ✅ 寫 `tools/pin_cost_cal.py` 一次性工具取 ECN baseline 26 個數字（用 `repr()` 取 float64 完整精度）→ 跑完刪掉
  - ✅ `modules/cost/tests/test_k13_equivalence.py`：3 tests 全 PASS
    - `test_k13_migration_equivalence_pinned` — 6 top-level metrics（availability time/energy、revenue loss、repair cost、total effort、cost per kWh）bit-perfect
    - `test_k13_migration_equivalence_seasonal` — 4 seasons × 5 cost subcategories（material / equipment / revenue_loss / preventive_material / fixed_cost）bit-perfect
    - `test_k13_cost_calculation` — ECN V5 reference 比對（與 ECN 原版同 tolerance 5-30%）
  - ✅ 用 `@pytest.fixture(scope="module")` 共用 K13 結果，3 tests 跑 0.22s
- **整個 cost module pytest**: 6 PASS + 1 XFAIL（含 -02 waiting_time 的 4 tests）
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-cost-cal-migration.md`](work-logs/2026-05/2026-05-04-cost-cal-migration.md)（session 紀錄）
  - [`modules/cost/tests/test_k13_equivalence.py`](modules/cost/tests/test_k13_equivalence.py)（3 tests + 26 pinned 數字）

---

### WMOM-20260504-02 — `engine/waiting_time/` 移植 + K13 equivalence

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high（migration pattern 樹立用）
- **Estimate**: 0.5 工作天
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 7 engine files (1,059 lines) 從 ECN 複製到 `modules/cost/engine/waiting_time/`，sed 一鍵改 import path
  - ✅ Stub `data_processor.preprocess_metocean_data()` — 唯一 ECN-specific 依賴（function-level lazy import 到 SQLAlchemy ORM），engine pipeline 不會走到
  - ✅ K13 demo data (7 檔，~32k 行) 搬到 `modules/cost/data/demo/`
  - ✅ ECN test 適配 → `modules/cost/tests/test_waiting_time.py`：path 改、return → assert、加 xfail with reason
  - ✅ 加 `test_migration_equivalence_pinned`：用 `repr()` 取 ECN float64 完整精度做 pin，windMindOM 必須 bit-perfect 一致
  - ✅ 4 tests 結果：3 PASS（含 migration equivalence）+ 1 XFAIL（pre-existing ECN issue：spring/summer K13 ref 對不上 ECN compute，與 migration 無關）
- **Migration pattern 樹立**（後續 cost_cal / monte_carlo / var_fluct 沿用）:
  1. cp + sed 改 import
  2. grep `from app\.` 找 ECN-specific 依賴 → stub or migrate
  3. 適配 test：path 改、return → assert
  4. 加 pinned equivalence test 用 `repr()` 取精度
  5. xfail with reason 標記 pre-existing ECN issue
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-waiting-time-migration.md`](work-logs/2026-05/2026-05-04-waiting-time-migration.md)（session 紀錄）
  - [`modules/cost/tests/test_waiting_time.py`](modules/cost/tests/test_waiting_time.py)（4 tests）

---

## M3-M4 Planning Open（劉老師 2026-05-04 提的 product 議題）

### WMOM-20260504-10 — Cost ↔ Wind farm config 整合（規劃缺口）

- **Status**: done（2026-05-04 完成 — M3 第一週插入工作）
- **Milestone**: M3（第一週）
- **Priority**: high（M2 demo OK 但對 friendly customer 不夠 personalize）
- **Estimate**: 1-2 工作天 → **實際半天**（K13 overlay 模式收斂得快）
- **Owner**: Claude (session 2026-05-04)
- **Branch**: `claude/issue-20260504-10-2026-05-04`
- **Work-log**: [`work-logs/2026-05/2026-05-04-cost-farm-integration.md`](work-logs/2026-05/2026-05-04-cost-farm-integration.md)
- **Completion summary**:
  - ✅ `cost_inputs.json` schema + `data/farms/{台中港曲風場,彰化離岸風場台電}/cost_inputs.json` 兩個 demo
  - ✅ `adapter.py` 加 `FarmDatasetMeta` + `load_engine_params_from_farm()`：三層 lookup（farm_overlay → registry_derived → k13_fallback）
  - ✅ `schemas/cost_schemas.py`：dataset 從 `Literal["k13"]` 改 str；4 個 response 加 optional `dataset_meta`
  - ✅ `cost_router.py`：`_resolve_dataset()` 統一處理 `k13` / `farm:{id}` / 未知值（404）
  - ✅ Tests +9：5 個 adapter farm loader（overlay / fallback / registry_derived / unknown / unknown_fields filter）+ 4 個 API endpoint（farm overlay / k13 meta / fallback / empty farm_id 422）
  - ✅ Frontend `CostPage.tsx` 加 dataset selector dropdown（K13 + 動態 farm list 從 `/api/farms` 拉）+ `DatasetMetaBadge` 顯示 4 種 source；切 dataset 自動 re-run forecast
  - ✅ `docs/product/MVP_ARCHITECTURE.md` 補節 5.4「Cost ↔ Farm config 整合」
  - ✅ 整 modules pytest：52 PASS + 1 XFAIL（cost 49 / monitoring 3）；frontend Vite build 0 TS error
- **Reference**:
  - [`modules/cost/data/farms/README.md`](modules/cost/data/farms/README.md)
  - [`modules/cost/adapter.py`](modules/cost/adapter.py)（`load_engine_params_from_farm` + `FarmDatasetMeta`）
  - [`docs/product/MVP_ARCHITECTURE.md`](docs/product/MVP_ARCHITECTURE.md) §5.4
  - [`work-logs/2026-05/2026-05-04-cost-farm-integration.md`](work-logs/2026-05/2026-05-04-cost-farm-integration.md)
- **Source**: 劉老師 2026-05-04 收工提問："cost model 跟模擬風機 / 未來實際風機 有連結嗎？"
- **問題描述**:
  目前 `modules/cost/adapter.py` 的 `load_k13_engine_params()` 完全 hard-coded 讀 K13 dataset
  （130 turbines, 4 MW, EUR-based, North Sea offshore wind ECN reference）。
  **與既有 monitoring 完全脫鉤**：
  - 14 台模擬風機（Z72, MW range, 台中港）跑著
  - cost engine 跑著
  - 兩邊互不知道對方存在
- **客戶問會被問倒的**:
  > 「我的風場只有 30 台 Vestas V164，你算 130 台 K13 給我看幹嘛？」
- **要做什麼**:
  1. **設計 farm-aware cost dataset schema**（per-customer JSON）
     - 風場參數：turbine count、capacity_kw、location（→ vessel rates）、kWh tariff、CAPEX
     - 故障率：per-turbine-model FTC table（Z72 / Vestas / SGRE 各別 MTBF）
     - 設備 / 船：local market rates（台灣海域 ≠ 北海）
  2. **adapter 多支援一個 entry point**：
     `load_engine_params_from_farm(farm_id)` — 從 `monitoring/farm_registry` 取 farm config
     + 對應 cost dataset → engine params
  3. **API endpoint 加 dataset 參數**：
     `POST /api/cost/forecast { "dataset": "farm:taichung-z72-001" }`（vs `"k13"`）
  4. **預設 fallback**：找不到 farm-specific dataset 時用 K13 + warning
- **Deliverable**:
  - `modules/cost/data/farms/{farm_id}/cost_inputs.json` 雛形
  - `adapter.py` 加 `load_engine_params_from_farm(farm_id)`
  - frontend 「dataset selector」（dropdown 選 K13 demo / 真實 farm）
  - `docs/product/MVP_ARCHITECTURE.md` 補一節「Cost ↔ Farm config 整合」
- **Reference**:
  - 已在 cost engine 的 K13_FTC_DEFAULTS / K13_MC_EQUIPMENT 是這個方向的 hard-code 版

---

### WMOM-20260504-13 — Cost 系列 fetch 加 AbortController 防 race

- **Status**: open
- **Milestone**: M5 / M6（不阻塞 demo）
- **Priority**: low
- **Estimate**: 0.25 工作天
- **Source**: code-reviewer 對 WMOM-10 的 finding #5（2026-05-04）
- **問題**:
  - `useCostData` 的 `useAsync.run` 沒有 abort 機制
  - React 18 Strict Mode dev 環境會 mount→unmount→mount，`useEffect([dataset])` 觸發兩次 fetch
  - 若慢 fetch 比快 fetch 後回，會用舊 dataset 結果蓋新 dataset 結果（race）
  - 用戶手動快速切 dataset 也會撞到同樣問題
- **驗收**:
  - 在 dev mode 切 dataset 5 次，最終顯示的 forecast 一定對應最後一次選的 dataset
  - 取消舊 fetch 不會 throw 進 error state
- **建議實作**:
  - `useAsync.run` 內建立 `AbortController`，next run 前 abort 上一個
  - fetch 受 AbortError 時不視為 error（直接 return）
- **Reference**:
  - `frontend/hooks/useCostData.ts`
  - `frontend/services/costService.ts:postJSON`
  - 本 review: WMOM-10 code-reviewer report finding #5

---

### WMOM-20260505-01 — Snapshots 表失控（41.9 GB SQLite hotfix）

- **Status**: done（2026-05-05 — PR #3 merged, VACUUM 釋放 41 GB 確認）
- **Milestone**: M1 follow-up（hotfix — production blocker，不在原規劃 issue 內）
- **Priority**: critical（production data growth — 17.5 天累積 41.9 GB；不修一個月可達 1 TB+）
- **Estimate**: 0.5-1 工作天
- **Owner**: Claude (session 2026-05-05)
- **Branch**: `claude/issue-20260505-01-2026-05-05`
- **Trigger**: 劉老師 2026-05-05 截圖 — 彰化離岸風場台電 farm 的 `wind_farm.db` 累積到 41.9 GB
- **Root cause analysis**:
  - `turbine_snapshots` 表 1,081 萬 row 佔絕大部分容量
  - 17.5 天範圍 / 19,594 個 distinct event_ref / 每 event 平均 606 row（10 分鐘 1Hz capture）
  - **三個放大因子疊加**：
    1. `storage.run_cleanup` **不清** snapshots（schema 註解寫 permanent，但實際是 bug — 沒有 retention）
    2. `data_broker._trigger_snapshot` 每次重新 trigger 時 retroactively 寫入 ~10 分鐘 in-memory history → 同類 event 重 trigger 時放大
    3. simulator state machine 在 stop=7 附近 flapping，每幾秒對同一台同一原因 emit 新 event_ref
  - 觀察證據：top event_ref 全是 `stop:WT007:7:...` 在 80 秒內連 trigger 11 次新 event
- **修法（3 件事一起做）**:
  1. `storage.run_cleanup` 加 `snapshots_retention_days` 參數（預設 7 天），DELETE FROM turbine_snapshots WHERE timestamp < cutoff
  2. `data_broker._trigger_snapshot` 加 dedupe + cooldown：
     - event_class（去掉 timestamp 部分，e.g. `stop:WT007:7`）作 dedupe key
     - 同類在 cooldown 期間（預設 5 分鐘）→ 僅延長現有 window，不重新 retroactive write
  3. 提供 `tools/vacuum_db.py` — 用 `VACUUM INTO` 寫到 sibling 路徑再 swap，避開 SQLite 原 VACUUM 需 2× 空間需求（41.9 GB 場景吃 84 GB）
- **Tests**:
  - test_storage_cleanup_snapshots_with_retention
  - test_data_broker_snapshot_dedupe_within_cooldown
- **Deliverable**:
  - 修改 `modules/monitoring/server/storage.py`（run_cleanup + 對應 maintenance_thread caller）
  - 修改 `modules/monitoring/server/data_broker.py`（_trigger_snapshot dedupe）
  - 新增 `modules/monitoring/tests/test_storage_cleanup.py` + `test_broker_snapshot_dedupe.py`
  - 新增 `tools/vacuum_db.py`（CLI tool，VACUUM INTO + swap）
- **Reference**:
  - 觀察分析資料：`/tmp/db_check2.py` 取樣結果（17.5 天 / 19,594 events / 606 row/event / 2,441 bytes/row）
  - 根因關鍵程式碼：[`data_broker.py:397`](modules/monitoring/server/data_broker.py) `_trigger_snapshot`
  - 根因關鍵程式碼：[`storage.py:520`](modules/monitoring/server/storage.py) `run_cleanup`（沒清 snapshots）

---

### WMOM-20260504-12 — Frontend 長時間執行記憶體成長（觀察）

- **Status**: open
- **Milestone**: M5 / M6（不阻塞 demo，可選優化）
- **Priority**: low
- **Estimate**: 0.5-1 工作天
- **Source**: 劉老師 2026-05-04 跑長時間測試 →「記憶體不足、refresh 後就好」
- **觀察結果**:
  - **Backend 儲存有 bug — 見 [WMOM-20260505-01](#wmom-20260505-01--snapshots-表失控419-gb-sqlite-hotfix)**：原本以為 `storage.py` 4 層 tiered retention 正常運作；2026-05-05 發現 turbine_snapshots 沒清 → 失控膨脹
  - **前端跑數小時記憶體成長** = 典型 React SPA 長時間運行 GC 跟不上問題，與資料儲存無關，refresh 即重置
- **可能來源（依嫌疑度）**:
  1. **MiniTrendChart × 14 張卡** — 每張 turbine card 帶一個 Recharts SVG mini-chart，每次 WebSocket push（10s）都 re-render 14 個 SVG，DOM 節點累積
  2. **`useRealtimeData` 整批替換 state** — 每次 WS push 整 array of 14 turbines 全替換而非 selective update，React diff 開銷大
  3. **Recharts ResponsiveContainer** 已知 resize observer / portal listener 在某些版本長時間執行有 leak
  4. WebSocket 重連時的 listener 累積（要查 cleanup）
- **建議的緩解（順序）**:
  1. 對 TurbineCard / MiniTrendChart 加 `React.memo` + 自訂 `areEqual`（只在 power/status 變才 re-render）
  2. `useRealtimeData` selective update：比對舊新 turbine list 只 mutate 改變的，不整批 setState
  3. 評估把 MiniTrendChart 換成 canvas-based（chart.js / 自寫 canvas），跳過 SVG DOM
  4. 加「自動 24h 軟 reload」機制（demo 用）— 簡單暴力但有效
  5. 升級 / pin recharts 版本，看 changelog 有沒有 leak fix
- **不阻塞**: refresh 即解決，不影響資料儲存，不影響客戶 demo（30 分鐘 demo 不會撞到）
- **驗收**: 24 小時連續執行記憶體成長 < 50% 視為可接受
- **Reference**:
  - `frontend/hooks/useRealtimeData.ts:229` — turbines state 整批替換
  - `frontend/components/MiniTrendChart.tsx` — 14 個 SVG re-render 來源

---

### WMOM-20260504-11 — Event-driven cost ledger（M4 增強）

- **Status**: open
- **Milestone**: M4（部分覆蓋）+ **新功能延伸到 M5/M6**
- **Priority**: high
- **Estimate**: 2-3 工作天（M4 既有 work order → ledger 之上補完）
- **Source**: 劉老師 2026-05-04 提問："cost 是否會隨故障/更換零件/發電/停機 來計算（收入支出）？"
- **既有 ROADMAP 涵蓋**:
  - ✅ M4 規劃「Cost ↔ Workflow 雙向: Work Order 完工 → cost ledger（actual）」
  - ✅ `GET /api/cost/ledger` endpoint
  - ✅ `/admin/cost/ledger` UI
- **規劃缺口（要補進來）**:
  1. **收入端**：發電量 × 電價 → 每日 / 每月入帳
     - Source：monitoring 的 `turbine_data` 表（每 10 秒 power_output kW）
     - Aggregate：每日 sum × tariff → daily_revenue table
     - 目前 turbine_data 已 ready，缺 aggregator + ledger entry
  2. **故障即時影響**：fault 發生 → 估推 revenue loss = downtime × expected_power × tariff
     - 整合 `modules/monitoring/scada_system.py` 的 fault scenario detection
     - Push pending revenue_loss 到 ledger（status: estimated → confirmed when 完工）
  3. **零件更換成本 + RUL 影響**：
     - 工單填料件清單 → 對應 component 表 → cost + RUL adjustment
     - 影響下次 monte_carlo 的 freq_min/ml/max（empirical update）
  4. **Ledger schema 設計**：
     ```
     CostLedger {
       id, farm_id, timestamp, type: 'revenue' | 'expense',
       category: 'generation' | 'corrective' | 'preventive' | 'fixed' | 'revenue_loss',
       amount, source_event_id, status: 'estimated' | 'confirmed'
     }
     ```
- **Deliverable**:
  - `modules/cost/models/cost_ledger.py` — SQLAlchemy / dataclass schema
  - `modules/cost/services/revenue_aggregator.py` — turbine_data → daily revenue
  - `modules/cost/services/event_ledger.py` — fault / work-order / inventory → ledger entries
  - 整合 `modules/workflow/work_order.py`（M3 完成後）— 工單完工 → ledger expense
  - 新 endpoint `GET /api/cost/ledger?farm_id=&from=&to=&type=`
  - frontend `/admin/cost/ledger` page — 實際 vs 預測對比
- **依賴**:
  - WMOM-10（farm 整合）必須先做 — ledger 需要 farm_id 維度
  - M3 work order CRUD 完成 — expense ledger 才能寫入
  - M4 inventory 完成 — 零件 cost 才能拆分
- **設計筆記應該寫進**: `docs/product/decision_log.md` DEC-{date}-XX「Cost 從 budget calculator 升級為 real-time ledger」

---

## M3 主線（2026-07）— Workflow Part 1: Work Order + Approval

> M3 主軸：從 z72_etech 取設計 → design notes → walkthrough → Work Order CRUD + 狀態機 + Approval。
> 7 個 sub-issue。`WMOM-20260504-10` (cost↔farm) 已先在 M3 第一週插入完成。

### WMOM-20260504-14 — z72_etech 取設計 + 3 份 design notes（**取材選 A**）

- **Status**: done（2026-05-05 完成 — 三份 DN 全寫 + walkthrough confirmed 一次到位）
- **Milestone**: M3
- **Priority**: critical（M3 spike，已解 blocking）
- **Estimate**: 1-2 工作天 → **實際 1 天**（劉老師全 agree default 建議，walkthrough 跟設計一次合併）
- **Owner**: Claude (session 2026-05-04 / 2026-05-05)
- **Branch**: `claude/issue-20260504-14-2026-05-04` (DN-01 part) + `claude/issue-20260504-15-walkthrough-2026-05-05` (DN-02/03 + walkthrough)
- **Completion summary**:
  - ✅ z72_SCADA_etech repo inventory（盤點報告 + 重構路線圖 + 5+ 個關鍵 module 程式）
  - ✅ DN-01 [Work Order Lifecycle](docs/design-notes/m3/DN-01-work-order-lifecycle.md) — 含 walkthrough 7 Q 答覆 + schema 微調（FollowupKind 二元 / Priority enum / multi-WO constraint / inspection auto-spawn hook）
  - ✅ DN-02 [Approval Multi-level](docs/design-notes/m3/DN-02-approval-multilevel.md) — 4 階 signoff / 工單 2 階 / 領料 3 階 / reject 回 IN_PROGRESS / signoff_history KPI
  - ✅ DN-03 [Inventory ↔ Material Request](docs/design-notes/m3/DN-03-inventory-material-request.md) — 3 欄位庫存 / 估計 vs 實際領料 / 退料 4 種分類 / 多倉預留 / inventory_adjustment_log 給庫管員手動 +/-
  - ✅ [README](docs/design-notes/m3/README.md) — 三份 DN 索引 + etech 10 大模組對照表 + 不取的東西清單
  - ✅ 衍生兩個新 issue：[WMOM-20260505-21](#wmom-20260505-21) (day_work_form) + [WMOM-20260505-22](#wmom-20260505-22) (inspection_schedule)
- **Reference**:
  - [`docs/design-notes/m3/`](docs/design-notes/m3/)（三份 DN + README）
  - [`work-logs/2026-05/2026-05-05-walkthrough-and-dn02-dn03.md`](work-logs/2026-05/2026-05-05-walkthrough-and-dn02-dn03.md)

---

### WMOM-20260504-15 — 30 分鐘 walkthrough 跟劉老師確認 design notes

- **Status**: done（2026-05-05 完成 — 與 -14 合併走完）
- **Milestone**: M3
- **Priority**: high
- **Estimate**: 0.5 工作天 → **實際 30 分**（合併在 -14 內，劉老師逐一答 17 個 Q）
- **Owner**: Claude + 劉老師
- **Completion summary**:
  - ✅ DN-01 7 個 Q 全 confirmed（含 removeFrom / chooseschange / multi-WO / 4 type / weather_window / dayworkForm / inspection）
  - ✅ DN-02 5 個 Q 全 agree default（4 階 signoff / 工單 2 階 vs 領料 3 階 / reject 回 IN_PROGRESS / 線性 / history 保留）
  - ✅ DN-03 5 個 Q 全 agree default（3 欄位庫存 / 系統追蹤部分 + 紙本歸還 / 估計 vs 實際 / 4 種退料分類 / 多倉預留）
  - ✅ Q&A 直接整合進對應 DN 文件（取代原「open questions」section）
  - ✅ 兩個衍生 issue 開好（WMOM-21 + WMOM-22）

---

### WMOM-20260504-16 — Work Order 領域模型 + 狀態機（pure domain）

- **Status**: done（2026-05-05 完成）
- **Milestone**: M3
- **Priority**: critical
- **Estimate**: 1 工作天 → **實際半天**（含 code review fix）
- **Owner**: Claude (session 2026-05-05)
- **Branch**: `claude/issue-20260504-16-2026-05-05`
- **Completion summary**:
  - ✅ `modules/workflow/domain/work_order.py`：4 Enum + ProgressNote + WorkOrderFollowup + WorkOrder dataclass
  - ✅ `modules/workflow/domain/state_machine.py`：TransitionRule + WORK_ORDER_TRANSITIONS（9 rule / 8 action）+ 6 guard + WorkOrderStateMachine + helper
  - ✅ Tests +73：test_work_order.py (20) + test_state_machine.py (53) — 含完整 lifecycle / parametrized 反例 / guard 不污染 state regression
  - ✅ Code review 13 finding 全處理（5 must-fix + 5 should-fix + 3 nice-to-have）
  - ✅ 整 pytest 163 PASS + 1 XFAIL（cost 49 + monitoring 35 + workflow 79）
- **Reference**:
  - [`modules/workflow/domain/`](modules/workflow/domain/)
  - [`work-logs/2026-05/2026-05-05-work-order-domain.md`](work-logs/2026-05/2026-05-05-work-order-domain.md)

---

### WMOM-20260504-17 — Work Order CRUD + REST API + tests

- **Status**: done（2026-05-05 完成）
- **Milestone**: M3
- **Priority**: critical
- **Estimate**: 1 工作天 → **實際 ~1 天**（含 code review 9 finding 全處理）
- **Owner**: Claude (session 2026-05-05)
- **Branch**: `claude/issue-20260504-17-2026-05-05`
- **Completion summary**:
  - ✅ `modules/workflow/repository/`：3 個 SQLAlchemy 2.0 ORM + WorkOrderRepository（CRUD + transition + multi-WO constraint + business_key + event log）
  - ✅ `modules/workflow/schemas/work_order_schemas.py`：10 個 pydantic v2 model
  - ✅ `modules/workflow/routers/work_order_router.py`：11 個 FastAPI endpoints
  - ✅ Mount 進主 FastAPI app
  - ✅ Tests +50：repository 31 + API 19
  - ✅ Code review 9 finding 全處理（3 must-fix + 5 should-fix + 1 nice-to-have）
  - ✅ 整 pytest 213 PASS + 1 XFAIL（cost 49 + monitoring 35 + workflow 129）
- **Reference**:
  - [`modules/workflow/`](modules/workflow/)
  - [`work-logs/2026-05/2026-05-05-work-order-crud-api.md`](work-logs/2026-05/2026-05-05-work-order-crud-api.md)

---

### WMOM-20260504-18 — Approval 多階簽核 + tests

- **Status**: done（2026-05-05 完成）
- **Milestone**: M3
- **Priority**: critical
- **Estimate**: 1 工作天 → **實際 ~1 天**（含 code review 11 finding 全處理）
- **Owner**: Claude (session 2026-05-05)
- **Branch**: `claude/issue-20260504-18-2026-05-05`
- **Completion summary**:
  - ✅ `modules/workflow/domain/signoff.py`：4 階 SignoffLevel + chain/step/history dataclasses + chain policy + user_group_to_level helper
  - ✅ `modules/workflow/repository/orm_models.py`：+3 個 SQLAlchemy 2.0 mapped class
  - ✅ `modules/workflow/repository/signoff_repository.py`：create_chain + approve/reject + pending list + history audit
  - ✅ `modules/workflow/schemas/signoff_schemas.py`：6 個 pydantic v2 model
  - ✅ `modules/workflow/routers/approval_router.py`：3 個 endpoints + factory injection
  - ✅ Integration: work_order finish → auto-create chain；approve last → 自動 work_order.approve_all；reject → 自動 work_order.reject
  - ✅ Mount 進主 FastAPI app
  - ✅ Tests +34（signoff repo 28 + approval API 9）；整 pytest 250 PASS + 1 XFAIL
  - ✅ Code review 11 finding 全處理（5 must-fix + 4 should-fix + 2 nice-to-have）
- **Reference**:
  - [`modules/workflow/`](modules/workflow/)（domain/signoff.py + repository/signoff_repository.py + routers/approval_router.py）
  - [`work-logs/2026-05/2026-05-05-approval-signoff-api.md`](work-logs/2026-05/2026-05-05-approval-signoff-api.md)

---

### WMOM-20260504-19 — `/admin/workflow/orders` frontend（建立精靈 + 列表 + 詳情）

- **Status**: open（依賴 -17 API）
- **Milestone**: M3
- **Priority**: high
- **Estimate**: 1-1.5 工作天
- **UI directive（WMOM-20260507-01 後）**：
  必須使用 `frontend/components/ui/`（Card / Btn / PageHeader / StatusPill / Field / Input / Select / Stat / BigChart / HealthBar）+ `frontend/theme/`（useTheme → C palette）。**不可** 寫 Tailwind utility class、不可硬寫 hex（chart event 標記色除外）。Modal 套既有 [WorkOrderDetailModal](frontend/components/WorkOrderDetailModal.tsx) 風格（Card padding=0 + DM Serif title + 底部 Btn）。
- **Description**:
  - `frontend/services/workOrderService.ts` (TypeScript API client)
  - `frontend/hooks/useWorkOrders.ts`
  - `frontend/components/WorkflowPage.tsx` 主入口
  - `frontend/components/workflow/WorkOrderListPanel.tsx` 列表（含 status filter + Hnumber search）
  - `frontend/components/workflow/CreateWorkOrderWizard.tsx` 建立精靈（多步：選風機 / 選故障代碼 / 派工人員 / 預估工時）
  - `frontend/components/workflow/WorkOrderDetailModal.tsx` 詳情 + 狀態 transition 按鈕

---

### WMOM-20260504-20 — `/admin/workflow/approval` frontend（待簽列表 + 簽核操作）

- **Status**: open（依賴 -18 API + -19 frontend baseline）
- **Milestone**: M3
- **Priority**: high
- **Estimate**: 1 工作天
- **UI directive（WMOM-20260507-01 後）**：
  與 -19 同 — 使用 `frontend/components/ui/` + `frontend/theme/`，不可 Tailwind / 硬 hex。Approval action dialog 套 [DispatchModal](frontend/components/DispatchModal.tsx) 模式（Card padding=0 + grid 內 Btn 卡片選人 + 底部 primary 確認）。
- **Description**:
  - `frontend/components/workflow/PendingApprovalPanel.tsx` 待簽列表（badge 含工單摘要 + 簽核層級）
  - `frontend/components/workflow/ApprovalActionDialog.tsx` 簽核 / 駁回對話框（含意見輸入）
  - 整合進 `WorkflowPage.tsx`（tab 切換 orders / approval）
  - 全 zh / en i18n

---

## M3 衍生 issue（從 walkthrough Q6 / Q7 衍生 — 不在 M3 主線 7 sub-issue 內）

### WMOM-20260505-21 — `day_work_form` 員工日誌設計與實作

- **Status**: open
- **Milestone**: M3 後續 / M4 之間（不阻塞 M3 主線）
- **Priority**: medium
- **Estimate**: 1-1.5 工作天
- **Source**: DN-01 walkthrough Q6（劉老師 2026-05-05 確認）
- **UI directive（WMOM-20260507-01 後）**：frontend `/admin/workflow/daywork` 必須使用 `frontend/components/ui/` + `frontend/theme/`，不可 Tailwind / 硬 hex。
- **Description**:
  工單對象 = 風機；員工日誌對象 = 員工 × 當天。兩個 entity 不同，但有引用關係。
  日誌可包含「完成 1 張工單 + 完成 2 個定檢項 + 巡視 + 訓練」等 4 種 activity kind。
- **Deliverable**:
  - `modules/workflow/domain/day_work_form.py`：DayWorkForm + ActivityEntry + ActivityKind enum
  - `modules/workflow/repository/day_work_form_repository.py`
  - `modules/workflow/routers/day_work_form_router.py`：CRUD + 「我今天做了什麼」query
  - frontend `/admin/workflow/daywork` 列表 + 個人填單頁
  - 整合 work_order.finish() 時自動寫進當天 day_work_form
- **Reference**:
  - [`docs/design-notes/m3/DN-01-work-order-lifecycle.md`](docs/design-notes/m3/DN-01-work-order-lifecycle.md) §3.3
  - etech 對應：`server/dayworkForm.js` + `pages/dayworkForm.vue`

---

### WMOM-20260505-22 — `inspection_schedule` 定檢計畫 + scheduler auto-spawn

- **Status**: open
- **Milestone**: M3 後續 / M4 之間（不阻塞 M3 主線）
- **Priority**: medium
- **Estimate**: 1-1.5 工作天
- **Source**: DN-01 walkthrough Q7（劉老師 2026-05-05 確認）
- **Description**:
  定檢清單獨立 entity（如「每月一次塔筒螺栓檢查」「每季一次潤滑油檢查」）。
  Scheduler 把到期 inspection auto-spawn `work_order(type=INSPECTION)`，避免人工漏排。
- **Deliverable**:
  - `modules/workflow/domain/inspection_schedule.py`：InspectionSchedule + Recurrence enum
  - `modules/workflow/services/inspection_scheduler.py`：daily check 到期項 → spawn WO
  - `modules/workflow/routers/inspection_router.py`：CRUD 定檢計畫 + query「下次檢查時間」
  - frontend `/admin/workflow/inspection` 計畫列表 + 編輯 + 「下次到期」dashboard
- **Reference**:
  - [`docs/design-notes/m3/DN-01-work-order-lifecycle.md`](docs/design-notes/m3/DN-01-work-order-lifecycle.md) §3.3
  - etech 對應：`server/regularlistForm.js` + `server/regularSetting.js`

---

## 物理模型強化（M3 並行 / 從 digiWT 階段延續未完工）

> 來源：`docs/physics_model_status.md` 「Still missing」段 + `examples/data_quality_report.txt` 3 項 fail + `docs/legacy/digiwt_TODO.md` 仍 open 項。
> 商業 demo 風險（P0）優先；學術深度（P2）可拖到 M5 之後。
> 開工順序建議：**-23（測試骨架）→ -24（data quality 修正）→ -25（前端可視化）→ 看 M3 frontend 進度再決定 -26/-27/-28**。

---

### WMOM-20260505-23 — Physics 自我驗證框架（self-validation framework）

- **Status**: **done**（Layer 1-7 全 2026-05-06 完成）
- **Milestone**: M3 並行（infrastructure，不卡 workflow）
- **Priority**: critical（**P0 — 物理正確性的根基；劉老師 2026-05-05 review 強調「不能只是說有採用，要知道結果是否準確」**）
- **Estimate**: 4-6 工作天 → **實際 1 天連跑完 7 layer**
- **Progress log**:
  - 2026-05-06：Layer 1（Conservation Laws）完成 — 36 tests pass（Betz / 能量 / 動量 / 角動量 / 熱平衡 / 質量守恆 + sentinel）；負向測試確認可 catch（將 `TurbineSpec.cp_max` 0.45→0.70 觸發 fail，回報 V=4.0 m/s 時 Cp=0.6270 > 0.5926）；`tests/physics/` 骨架（conftest.py + reports/README）就位
  - 2026-05-06：Layer 2（Literature/Standard Benchmarks）完成 — 35 tests pass（IEC 61400-1 Kaimal / Bastankhah-Niayifar wake / Glauert NTF / Tedric Harris BPFO/BPFI / ISO 10816-3 Class III / Walther viscosity decay / ISA air density）；負向測試 `_brg_n_elements` 23→30 → BPFO test 4 cases FAIL（rel_err 30%）。Layer 1+2 合計 71 tests pass in 1.45 s
  - 2026-05-06：Layer 3（Operating Envelope）完成 — 18 tests pass（cut-in/cut-out 行為、emergency stop 5s 衰減 50%、pitch rate ≤10°/s、yaw rate ≤0.5°/s、rotor overspeed software 保護、direct-drive + geared slip < 5%）。
  - 2026-05-06：Layer 4（Cross-module Consistency）完成 — 9 tests pass（Region 2 cubic R²>0.95 實測 0.99、stator-power lag-correlation 峰值在 240-600 s、inter-turbine spread > 0 且 < 50%、Region 3 power CV 結構性 bound、stability coupling 方向正確）。設計避開 calibration value（spread/CV）由 WMOM-24 收緊。
  - 2026-05-06：Layer 5（Fault Injection Signatures）完成 — 23 tests pass（11 個 fault scenarios 各驗 1-2 個 SCADA tag delta + healthy baseline ISO Zone A/B + power 偏離 lookup < 30%）。Layer 1-5 合計 121 tests pass。
  - 2026-05-06：Layer 6（Health Check CLI）完成 — `tools/physics_health_check.py` 一鍵體檢 entry，subprocess 跑 Layer 1-5 + 短模擬 5 turbines × 30 min（含 1 fault）+ 4 大健康分級 + markdown/JSON/figures 產出。Exit code 0/1 適合 CI。
  - 2026-05-06：code-reviewer subagent 對 Layer 1-6 做 review，找出 3 blockers + 6 suggestions；3 blockers + 3 suggestions 已修（B-1 Kaimal stable/unstable 重疊條件、B-2 settle_steps 不一致、B-3 mean_dict 缺 key 問題）。fix 後 121 tests 仍全 pass。
  - 2026-05-06：Layer 7（Test Report Persistence）完成 — `tests/physics/conftest.py` 加 pytest_sessionfinish hook，自動寫入 `reports/{YYYY}/{MM}/{ts}-pytest.{md,json}` 含 YAML metadata + baseline_drift 比對。`_baseline/pytest_baseline.{md,json}` 已建立。
  - **整體驗收**：121 pytest tests pass in ~25 s，health check CLI 4/4 PASS，Layer 1-7 全部 closed。
- **Source**:
  - 劉老師 2026-05-05 review：物理模型要有自我測試機制，要能驗證結果準確性
  - `docs/legacy/digiwt_TODO.md` Testing 段（issue #52 升級版）
- **Description**:
  既有物理模組 14 個 + 26 條進階修正（#61~#127），但只有 `examples/data_quality_analysis.py` 一個半自動 21 項 check。**痛點**：
  1. **不驗證物理定律 / 文獻 benchmark** — Betz 限、IEC 61400-1 Kaimal、ISO 10816、Bastankhah wake 文獻值都沒比對
  2. **不驗證故障注入 sanity** — `bearing_wear` 注入後 HF band 該升、`gearbox_overheat` 注入後 oil_temp 該升 — 沒人自動驗
  3. **不驗證跨模組一致性** — rotor power × η_drivetrain × η_converter ≈ P_elec 沒驗
  4. 改 physics 只能「憑感覺」 — 改完跑一次看儀表板，遺漏邊角 case 沒人發現
  
  **「regression test（鎖住現況）」與「validation（驗證物理正確）」是兩件事**，本 issue 兩者都要做，但**重點是後者**。

- **Deliverable**（6 層 validator，每層獨立 commit）：
  
  **Layer 1 — Conservation Laws / Physical Bounds（守恆律 + 物理上限）**
  - `tests/physics/test_invariants.py`
  - Betz 限：所有 (V, λ, β) 條件下 Cp ≤ 0.593
  - 能量守恆：P_aero × η_drivetrain × η_converter ≈ P_elec（容差 ±5%）
  - 動量平衡：thrust × V_∞ × A 與 aero power 透過動量定理對得上
  - 角動量：rotor_speed × gearbox_ratio ≈ generator_speed（含 slip 容差）
  - 熱平衡：input heat - removed heat = thermal mass × dT（熱慣性容差）
  - 質量守恆（冷卻液）：level decay 與 leak rate 對得上
  
  **Layer 2 — Literature / Standard Benchmarks（文獻 / 標準 benchmark）**
  - `tests/physics/test_benchmarks.py`
  - **IEC 61400-1 Kaimal**：σ_v / V_mean ≈ TI（強風下測）
  - **Bastankhah wake**：Ct=0.82, TI=8%, x=5D → deficit 落 25-35%（Niayifar & Porté-Agel 2016）
  - **Glauert NTF**：Region 2 a≈0.33 → V_raw/V_∞ ≈ 0.84（IEC 61400-12-1 Annex D）
  - **BPFO/BPFI**：n=23, d/D=0.18, α=10° → 計算值對應 Tedric Harris formula
  - **ISO 10816-3 Class III**：vibration RMS zone boundaries（A < 2.3, B 2.3-4.5, C 4.5-7.1, D > 7.1 mm/s）
  - **Walther viscosity**：cold-start 後 ~10 min decay 達 ~63% 穩態值
  - **Air density (ISA 15°C, dry)**：1.2250 kg/m³ ± 0.5%（WMOM #101）
  
  **Layer 3 — Operating Envelope（操作邊界）**
  - `tests/physics/test_envelope.py`
  - cut-in 以下 → power < 1 kW、rotor 漸停
  - cut-out 以上 → 30 s 內 power 歸零、進 stop 狀態
  - emergency stop → rotor speed 5 s 內降 50%、tower load 1.8× 衝擊出現
  - pitch rate ≤ 10 °/s（actuator 物理上限）
  - yaw rate ≤ 0.5 °/s
  - rotor overspeed margin：≤ rated × 1.2
  - generator slip：< 5%
  
  **Layer 4 — Cross-module Consistency（跨模組一致性）**
  - `tests/physics/test_consistency.py`
  - 風機個體 power spread 落 [10%, 25%]（與 -24 目標一致）
  - Region 3 power CV 落 [3%, 8%]
  - Region 2 power 對 wind 之 cubic fit R² > 0.95
  - Stator temp 與 power 之 lagged correlation：r > 0.5 但 lag > 60 s
  - 同一 grid event 下，不同 turbine 因 derate sensitivity 不同 → spread 在 [5%, 20%]
  - Atmospheric stability s × shear α 五重耦合：相關係數方向正確（#99/#109/#111/#113/#115）
  
  **Layer 5 — Fault Injection Signature（故障注入 sanity）**
  - `tests/physics/test_fault_signature.py`
  - 對 11 個 fault scenario 各跑短 sim，驗證 SCADA tag 該動的有動：
    - `bearing_wear` → HF band 升 ≥30%、crest factor ≥5
    - `gearbox_overheat` → oil_temp 升 ≥10°C、GMF sideband ratio 升
    - `pitch_imbalance` → 1P band 升、tower SS moment 升
    - `blade_icing` → 1P + 3P 都升、power 跌
    - `generator_overspeed` → HF band 升 + stator temp 升
    - `converter_cooling_fault` → power 跌 + cabin temp 升 + cooling level 降
    - `yaw_misalignment` → 3P band 升 + power 跌（cos³γ）
    - `stator_winding_degradation` → HF 升（電氣噪訊）
    - `hydraulic_leak` → broadband 升 + brake pressure 異常
    - `gearbox_oil_leak` → oil_level 降 + viscosity 異常
    - `grid_protection_trip`（如 -27 完成）→ relay status flip + emergency stop
  - 健康基線（無故障）：crest factor < 5, kurtosis < 4, RMS 落 ISO zone A/B
  
  **Layer 6 — Physics Health Check CLI（一鍵體檢報告）**
  - `tools/physics_health_check.py`：CLI 工具
    - 跑完 Layer 1-5 全 validator
    - 跑一次 30-min short sim 5 turbines（含 1 個 fault injection）
    - 產出 markdown 報告 + JSON + matplotlib 關鍵圖（Cp 曲面、wake deficit、ISO 10816 zones、fault signature）
    - exit code：失敗 → 1，全 pass → 0（適合 CI）
    - argparse `--save-report` (default on) / `--baseline-diff` / `--update-baseline`
  - 整進 [docs/routines/daily-workflow.md](docs/routines/daily-workflow.md)：每次改 physics 模組後 + 大版本發布前必跑
  - 寫入 README：`python tools/physics_health_check.py` 是「物理體檢」單一入口
  
  **Layer 7 — Test Report Persistence（測試紀錄保存機制）⭐ 劉老師 2026-05-05 要求**
  
  每次測試自動留下可追蹤的紀錄文件，避免「跑過就忘了」、無從查歷史軌跡。
  
  資料夾結構（**新增於 `tests/physics/reports/`**）：
  ```
  tests/physics/reports/
  ├── _baseline/                          ← 最新 baseline（人手動 review 後 commit）
  │   ├── pytest_baseline.md              ← 6 layer 全 pass 的 baseline 數值
  │   ├── pytest_baseline.json            ← machine-readable，diff 用
  │   └── health_baseline.md
  ├── 2026/05/                            ← 按月歸檔
  │   ├── 2026-05-05-1430-pytest.md       ← pytest 自動產
  │   ├── 2026-05-05-1430-pytest.json
  │   ├── 2026-05-06-0915-pytest.md
  │   └── 2026-05-06-1000-health/         ← health check CLI 產
  │       ├── report.md
  │       ├── report.json
  │       ├── baseline_diff.md
  │       └── figures/
  │           ├── cp_surface.png
  │           ├── wake_deficit.png
  │           ├── iso10816_zones.png
  │           └── fault_signatures.png
  └── README.md                           ← 怎麼讀報告 / 怎麼回滾 baseline / retention 規則
  ```
  
  每份紀錄頂端必含 YAML metadata：
  ```yaml
  ---
  timestamp: 2026-05-05T14:30:12+08:00
  git_commit: abc1234
  git_branch: claude/issue-20260505-23-2026-05-05
  git_dirty: false                        # working tree 是否有未 commit 變動
  python_version: 3.12.5
  test_type: pytest | health_check
  duration_sec: 42.3
  total_pass: 87
  total_fail: 0
  total_warn: 2
  baseline_compared: _baseline/pytest_baseline.json
  baseline_drift: see baseline_diff section below
  ---
  ```
  
  機制：
  - `tests/physics/conftest.py`：`pytest_sessionfinish` hook 自動產 `pytest-{ts}.md` + `.json`
  - `tools/physics_health_check.py`：CLI 預設寫入 `health-{ts}/` 子目錄
  - `tools/physics_baseline_update.py`：人手動 review 後 promote 為 baseline（**禁止自動 update**，避免 silent drift）
  - **Git 策略**：報告檔 commit 進 repo（這就是「紀錄」的意義）；`figures/*.png` 視大小決定（超過 1 MB 改 git-lfs 或 ignore）
  - **Retention**：保留近 6 個月每日；超過 6 個月只留每月最後一份；超過 1 年只留每年 release 對應的；baseline 永留
  - **README.md**：寫清楚「為什麼這個資料夾存在 / 怎麼比對兩份報告 / 怎麼決定該不該更新 baseline」
  
- **Acceptance**:
  - `pytest tests/physics/ -q` 100% PASS（7 層共 ~80-120 條 test）
  - 跑時間 < 60 s（不含 Layer 6 CLI 的 short sim）
  - `python tools/physics_health_check.py` 產出可讀的 markdown 體檢報告
  - **負向測試**：故意把 `power_curve.py` 一個常數改錯（例如把 Betz 限改成 0.7），framework 必須 catch 到並 fail
  - 既有 26 條物理修正（#61~#127）每條至少有 1 個 validator 對應
  - **Layer 7 驗收（測試紀錄保存）**：
    - 跑完 `pytest tests/physics/` → `tests/physics/reports/2026/MM/` 自動新增 `*-pytest.md` + `.json`
    - 跑完 `python tools/physics_health_check.py` → 自動新增 `health-{ts}/` 子目錄含 `report.md` + `report.json` + `figures/*.png`
    - 每份報告開頭都有 YAML metadata（timestamp / git_commit / git_branch / git_dirty / python_version / pass-fail counts）
    - `tests/physics/reports/_baseline/` 已 commit baseline，且 `baseline_diff` 段在新報告中能正確顯示「無漂移」或「漂移 X%」
    - `tests/physics/reports/README.md` 解釋資料夾用途 / 比對方法 / baseline update 流程
    - retention policy 至少寫成 docstring（實作可延到下次 cleanup）
  
- **Reference**:
  - 既有 `examples/data_quality_analysis.py`（21 check 已寫，可整合進 Layer 4/5）
  - `docs/physics_model_status.md`（每條 # issue 對應的 validation point 來源）
  - IEC 61400-1, IEC 61400-12-1/2, ISO 10816-3
  - Burton, Sharpe, Jenkins, Bossanyi (2011) *Wind Energy Handbook* 2nd ed.
  - Niayifar & Porté-Agel (2016) — wake deficit benchmark
  
- **Risk / Note**:
  - **不要過度收緊 acceptance** — 物理模型有隨機項（turbulence、AR(1)），驗證要用統計量（mean / std / 相關係數）+ 容差，不要硬 == 比對
  - 跑時間若爆掉 → Layer 5 fault sim 改成「先建 fixture 再跑 assertion」
  - 對應 -24 修正的目標（spread / CV）會在 Layer 4 體現，兩 issue 互相驗證

---

### WMOM-20260505-24 — Data quality 3 項 fail 修正（個體差異 spread + Region 3 CV）

- **Status**: open
- **Milestone**: M3 並行（demo 必修）
- **Priority**: high（P0 — demo 被客戶質疑會傷信任）
- **Estimate**: 0.5-1 工作天
- **Source**: `examples/data_quality_report.txt` 「待改善列表」3 項
- **Description**:
  最新 data quality run 仍有 3 項警告：
  1. **Wind 15-20 m/s region CV=0.9% 太低** — rated region 訊號過度平滑，pitch dead-band / lag 還是不夠
  2. **Wind 20-25 m/s region CV=0.8% 太低** — 同上
  3. **風機間平均功率差 36.8% (>30%)** — individuality 參數調太大，看起來像異常值不像真實 fleet
- **Deliverable**:
  - `simulator/physics/power_curve.py`：rated region 加更多 controller jitter（pitch micro-correction noise + power setpoint dither，幅度依 #61 Cp 模型回推合理範圍）
  - `simulator/turbine_individuality.py` 或對應位置：`per_turbine_power_offset` / `cp_offset` 從 ±15% 收斂到 ±10-12%（保留個體差但合理）
  - 重跑 `examples/data_quality_analysis.py` 短版 0.17h × 5 turbines，確認 3 項全 pass，且不破壞既有 18 項 pass
  - 同步更新 `data_quality_report.txt`（commit 進 repo）
- **Acceptance**:
  - 21/21 quality check pass（或至少 20/21，spread 落在 25-30% 區間）
  - 既有 #117/#119/#125/#127 物理鏈不被破壞
- **Reference**:
  - `modules/monitoring/examples/data_quality_report.txt`
  - `modules/monitoring/examples/_post_migration_quick_validate.py`
  - issue #61（Cp 模型升級 commit 應該已部分緩解，但 Region 3 仍偏平）

---

### WMOM-20260505-25 — Frontend：RUL 顯示 + 多 band alarm 視覺化（#57/#58 收尾）

- **Status**: open
- **Milestone**: M3 並行 / M5 demo 增值
- **Priority**: medium（P1 — M5 RAG demo 視覺化 PMF 關鍵）
- **Estimate**: 1.5-2 工作天
- **Source**: `docs/legacy/digiwt_TODO.md` Priority E + Priority F（issue #57 + #58 frontend 部分）
- **UI directive（WMOM-20260507-01 後）**：
  在 [TurbineDetail](frontend/components/TurbineDetail.tsx) 既有 8-tab 架構內加新 tab（建議 `health` 或擴充現有 `fatigue` tab）；多 band alarm 用 `<HealthBar>`（[Charts.tsx](frontend/components/ui/Charts.tsx)）；RUL 顯示用 `<Stat>` 大數字 + threshold 顏色（接 C.warn / C.amber / C.ok）。**不可** Tailwind / 硬 hex。
- **Description**:
  Backend 已完成：
  - #57：fatigue 4-level alarm + RUL（剩餘壽命）estimation + 自動寫進 history events
  - #58：vibration 5 band alarm（1P/3P/gear/HF/Bb）+ crest/kurtosis alarm + BPFO/BPFI + GMF sideband
  缺前端可視化 — M5 RAG demo 時客戶看不到「AI 預警」直觀畫面。
- **Deliverable**:
  - `frontend/components/turbine/RulPanel.tsx`：RUL 倒數（年/月/日）+ 4-level alarm badge（notice/warning/danger/shutdown）+ 觸發時間軸
  - `frontend/components/turbine/SpectralAlarmPanel.tsx`：5 band 動態 threshold curve（A/B/C/D zones）+ 即時 RMS 落在哪一區 + crest/kurtosis trend
  - `frontend/components/turbine/BearingDiagPanel.tsx`：BPFO/BPFI 即時頻率 + 軸承幾何來源說明 + GMF sideband ratio
  - 整合進既有 turbine detail page 為新 tab「Condition / RUL」
  - i18n（zh/en 雙語）
- **Acceptance**:
  - 3 個 panel 在 simulator 模式下能看到資料流動
  - 故障注入（bearing_wear / gearbox_overheat）時 alarm badge 會升級
  - M5 demo 時可直接 screenshot 進 pitch deck
- **Reference**:
  - 後端 API：`server/routers/turbines.py`（已 expose 對應 SCADA tag）
  - 既有 `frontend/components/turbine/LoadFatiguePanel.tsx`（pattern 參考）

---

### WMOM-20260505-26 — SCADA tag 深度擴充（protection / cooling loop / converter internal / service-state）

- **Status**: open
- **Milestone**: M3 後續 / M5 RAG 之前必須做
- **Priority**: medium（P1 — M5 RAG 警報多樣性的素材庫）
- **Estimate**: 3-5 工作天（可拆 4 個 sub-issue 分批）
- **Source**: `docs/physics_model_status.md` §3.5「Expanded SCADA Tag Set」
- **Description**:
  目前 104 SCADA tags 多在感測層（風速 / 溫度 / 振動 / 載荷）。M5 RAG demo 要對應 Z72 手冊的警報碼（數百條），但現況只有 ~20 種警報事件可觸發，警報 → 手冊 retrieval 的 demo 廣度不夠。
- **Deliverable**:
  - **Protection 層**：grid breaker status / under-voltage relay / over-current trip / earth fault relay / phase loss（5-8 tags）
  - **Cooling loop 深度**：3-way valve position / heat exchanger ΔT / coolant flow per branch / pump RPM / accumulator pressure（5-8 tags）
  - **Converter internal**：DC link voltage / IGBT junction temp / firing angle / harmonic distortion / common mode voltage（5-8 tags）
  - **Service / Maintenance state**：service mode flag / lockout-tagout state / manual override active / calibration mode / firmware version（4-6 tags）
  - 對應 OPC suffix 對齊 Bachmann Z72 命名規則
  - 寫進 `scada_registry.py` `_TAGS` + `turbine_physics.py::step()` 輸出
  - 物理耦合：能由現有 fault scenario（converter_cooling_fault / generator_overspeed / hydraulic_leak 等）自然觸發，不要手刻 mock
- **Acceptance**:
  - SCADA tag 從 104 擴到 ~125-130
  - 既有 18/21 quality check 不被破壞
  - 至少 5 條新 tag 能在 fault scenario 下看到變化
- **Reference**:
  - `docs/__Z72UserManual.pdf`（M5 餵 RAG，要先確認 tag 名稱對得上）
  - `docs/1040610-Z72_PLC_OPC_TAG_1040510.xlsx`

---

### WMOM-20260505-27 — 保護電驛協調模型（51 / 27 / 59 / 81）

- **Status**: open
- **Milestone**: M3 後續 / 也可 park 到 M5 後
- **Priority**: medium-low（P2 — academic paper 章節價值高，demo 直接價值中等）
- **Estimate**: 1-2 週
- **Source**: `docs/physics_model_status.md` §2.5「Still missing: protection coordination relay model」
- **Description**:
  既有 LVRT/HVRT envelope 是 ride-through curve 的 envelope 判定，沒有真實的保護電驛動作邏輯。發 paper 給 Applied Energy 的「grid integration」章節時，這層是 reviewer 通常會問的細節。
  四類保護電驛：
  - **51（過電流時間反延時）**：I × t curve，極反延時 / 一般反延時 / 中反延時
  - **27（低電壓）**：V < threshold + delay
  - **59（過電壓）**：V > threshold + delay
  - **81（頻率異常）**：df/dt + f range（U/F + O/F）
- **Deliverable**:
  - `simulator/physics/protection_relay.py`：4 個 relay class + coordination logic（main + backup + 動作時間 selectivity）
  - 與 `electrical_model.py` 串接：relay 動作 → trigger trip event → cascading 到 turbine state machine 的 emergency stop
  - 6-10 條新 SCADA tag（relay status / pickup current / trip count / last trip time）
  - 至少 3 個 demo grid event 能跑通（distant fault / nearby short circuit / frequency excursion）
  - 對應 fault scenario 至少 1 個（grid_protection_trip）
- **Acceptance**:
  - 4 relay 都有單元測試（依賴 -23 測試骨架）
  - 與 IEC 60255 / IEEE C37.112 inverse-time curve 標準對得上（不要求 bit-perfect）
  - 至少 2 種 selectivity 場景能驗證（main 先動 vs backup 接手）
- **Reference**:
  - IEC 60255 / IEEE C37.112（inverse-time overcurrent curve）
  - `simulator/physics/electrical_model.py` LVRT/HVRT 段是 baseline

---

### WMOM-20260505-28 — 單齒 pitting / spalling defect signature

- **Status**: open
- **Milestone**: park 到 M5 後（學術強化用）
- **Priority**: low（P2 — paper value 高，商業 demo value 低）
- **Estimate**: 1 工作週
- **Source**: `docs/physics_model_status.md` §2.2「Still missing: per-tooth pitting/spalling frequency model (individual tooth defect)」
- **Description**:
  目前 #76 已有 GMF + sideband + tooth wear scalar（aggregate），缺單顆齒缺陷的窄頻譜訊號。診斷論文裡軸承 BPFO/BPFI 已建（#58），齒輪單齒 defect 是配對的另一面。
- **Deliverable**:
  - `simulator/physics/drivetrain_model.py`：擴充 `tooth_defect` state（哪一階 / 哪一顆 / 缺陷嚴重度）
  - 對應頻譜 signature：GMF × shaft frequency 的 modulation pattern + envelope demodulation 可觀察的衝擊
  - 新 fault scenario：`gear_tooth_defect`（從 baseline 幾乎看不到，到 severe 時 GMF sideband 大幅升起 + crest factor 異常）
  - 1-2 條新 SCADA tag（`WDRV_TthDefSev` / `WDRV_TthDefHs`）
- **Acceptance**:
  - test_drivetrain.py 覆蓋（依 -23）
  - 與既有 11 fault scenario 相容（不破壞 fault_engine 邏輯）
  - 故障注入後 frontend SpectralAlarmPanel（依 -25）能看到 GMF 區段升起
- **Reference**:
  - Randall 2011 *Vibration-based Condition Monitoring* §6.4
  - 既有 #76 / #58 GMF sideband 為 baseline

---

## UX / Frontend revamp

### WMOM-20260507-01 — 前端 UI 改版（A · Calm Operator + 雙主題）

- **Status**: **done**（2026-05-07 完成）
- **Milestone**: M1 並行（前端基礎設施，不卡 M3 frontend issue -19/-20/-25）
- **Priority**: medium（劉老師對外 demo 與第一個客戶接觸需要更專業的視覺語言）
- **Estimate**: 1 工作天 → **實際 1 個 session**
- **Owner**: Claude (session 2026-05-07)
- **Source**: 劉老師提供 `WMOM 介面改版交接書.md` + `app/VA.jsx` design canvas（A · Calm Operator 風格 — 鼠尾草綠＋暖米白／雜誌式排版）
- **Description**:
  既有 frontend 是 dark cyan + Tailwind + Orbitron 風（從 digiWindTurbine 繼承），對運維廠商管理層而言過於「實驗室感」、與 v0.8.1 商業化定位不符。改版按交接書規範替換成：
  1. **220px 左 Sidebar**（5 主頁 nav + 工具區 secondary）取代頂部 header
  2. **雙主題系統**：日（鼠尾草綠 #3F6B53 + 暖米白 #F5F2EA）/ 夜（翡翠玻璃 #3DDC97 + 深森林 #0E1815）— 全元件走 theme palette，不寫死 hex
  3. **字型**：DM Serif Display（H1 38px）+ Manrope（內文）+ JetBrains Mono（數字 / SCADA tags）
  4. **5 大頁面重畫骨架**：FarmOverview / TurbineDetail / MaintenanceHub / CostPage / HistoryPage（按交接書 §4 規格）
  5. **保留全部 API / hooks 不動**：`useMockTurbineData` / `useRealtimeData` / `useMaintenanceData` / `useCostData` / `useI18n` / `useSettings` 全不動，OperatorControl 6 指令、AI fault diagnosis、Dispatch 流程、CSV 匯出、事件比較、4 個 cost endpoint 完全保留
- **Deliverable**:
  - `frontend/theme/` — `themes.ts`（兩套 palette）+ `ThemeProvider.tsx`（Context + localStorage + `data-theme` 同步）
  - `frontend/components/ui/` — `Card / Btn / PageHeader / StatusPill / Stat / Logo / NavIcon / Sidebar / BigChart / MiniSparkline / HealthBar / Field / Input / Select / ReadOnlyBox`（10 個共用元件 + index）
  - `frontend/App.tsx` — 重寫成 sidebar layout，包 ThemeProvider，保留所有 modal 與 view state
  - `frontend/components/{FarmOverview, TurbineDetail, MaintenanceHub, CostPage, HistoryPage}.tsx` — 5 大頁面照交接書規格重寫
  - `frontend/components/{FaultInjectionPanel, SettingsPage, DispatchModal, WorkOrderDetailModal, FarmSelector, TrendChartPanel, EventComparisonView}.tsx` — 沿用功能、套新樣式
  - `frontend/index.html` — 加 DM Serif / Manrope / JetBrains Mono CDN；移除 Tailwind CDN（已無使用）；CSS variable 預設值
  - 刪除 6 個孤兒：`DataCard / Gauge / StatusIndicator / MiniTrendChart / FarmTrendChart / icons.tsx`（被新 ui 元件取代）
- **驗收**：
  - ✅ `npx tsc --noEmit` 0 錯誤
  - ✅ Vite dev server 跑在 `http://127.0.0.1:5179/` 全 page module 200，5 大頁 + faults / settings 全可開
  - ✅ 劉老師於 5179 視覺 review 確認 OK（2026-05-07 截圖）
  - ✅ 響應式 grid 1280+ 4 欄 / 1024–1279 3 欄 / 1023– 2 欄 / 768– sidebar 收漢堡
  - ✅ 主題 ☀/☾ + EN/中切換寫 localStorage、reload 後狀態保留
  - ✅ 所有按鈕 `aria-label`、主題切換 `aria-pressed`
- **Decision**:
  - **Tailwind 全退**：原本規劃保留作 layout utility，但實作後發現所有 new code 都走 inline style + theme palette，Tailwind CDN 變成 dead weight，順手移除
  - **recharts 保留 in HistoryPage / CostPage / TrendChartPanel**：互動需求高（hover、zoom、reference line）走 recharts；overview / cost KPI 的趨勢圖改 SVG（跟 VA.jsx 一致）
  - **Faults / Settings 入 sidebar secondary group**：交接書 §6 only 列 5 主頁，但實際還是要保留入口；放在「工具」分組下方，與主題切換並列
- **Intentional placeholders（不是 bug，刻意保留）**：
  以下 7 個 PageHeader 按鈕**有 UI 但無 onClick**，作為設計稿視覺鷹架保留，等對應 API / 流程確定再逐步補上。劉老師 2026-05-07 確認「保留就好，之後一個一個補功能」。
  追蹤清單見 → `WMOM-20260507-02`。
  | 頁面 | 按鈕 | 設計稿來源 | 真實對應 |
  |---|---|---|---|
  | 維護中心 | `+ 新工單` | VA.jsx §4.3 | 風機細節 → AI 診斷 → 派遣技師（既有 dispatch flow） |
  | 風場總覽 | `匯出` / `+ 新報告` | VA.jsx §4.1 | `匯出` 可接 `/api/export/snapshot`；`+ 新報告` 暫無 API |
  | 風機細節 | `限載` / `停機` / `安排檢查` | VA.jsx §4.2 | 同頁右側「操作控制」卡片有完整 6 指令（重複入口） |
- **Reference**:
  - `WMOM 介面改版交接書.md`（劉老師主 repo 根目錄，未進 worktree）
  - `app/VA.jsx`、`app/data.js`（design canvas，未進 worktree）
  - `work-logs/2026-05/2026-05-07-ui-revamp-calm-operator.md`

---

### WMOM-20260507-02 — PageHeader placeholder 按鈕逐步補功能

- **Status**: open
- **Milestone**: 不卡 M2-M5 主線，可隨時挑著補
- **Priority**: low（UX polish；功能都可在 detail 頁完成）
- **Estimate**: 每個 0.5-2h，依 API 是否存在
- **Source**: WMOM-20260507-01 改版時依設計稿放上 UI 但無 handler
- **Description**:
  改版時依 VA.jsx 設計稿放了 7 個 PageHeader 裝飾按鈕，劉老師 2026-05-07 決定 placeholder 保留、之後逐項補功能。本 issue 作為清單追蹤；每個 sub-task 完成時直接打勾並 commit。
- **Sub-tasks**（按好做順序排）：
  - [ ] **a. 風場總覽 `匯出`** — 接既有 `GET /api/export/snapshot`（直接下載 JSON）。**估時 30 min**
  - [ ] **b. 風機細節 `停機`** — 對應 `OperatorControlCard` 的 stop 指令；點擊跳到右側卡片或直接呼叫 `POST /api/control/command { command: 'stop' }`。**估時 30 min**
  - [ ] **c. 風機細節 `限載`** — 開 inline modal 收 kW 值 → `POST /api/control/curtail`。**估時 1h**
  - [ ] **d. 風機細節 `安排檢查`** — 跳到 `/maintenance` + 預填 turbine 與 inspection scenario；依賴 WMOM-22 `inspection_schedule`。**估時 1h**（但要等 -22 done）
  - [ ] **e. 維護中心 `+ 新工單`** — 開 modal：選風機 + 描述 + 選技師 → `POST /api/maintenance/work-orders`（API 已存在）。**估時 2h**
  - [ ] **f. 風場總覽 `+ 新報告`** — 依賴 M4 reporting module；開 modal 選報告類型（月報 / 年度預算 / custom range）。**估時 2-3h**（要等 M4 backend）
- **Deliverable**:
  - 每完成一項，更新本 issue checkbox + commit 訊息帶 `feat(#WMOM-20260507-02): wire {sub-task name}`
  - 全勾完後本 issue close
- **Decision**:
  - 不要把這些按鈕通通砍掉重畫（會破壞跟設計稿的對齊）
  - 不要做「dummy alert / TODO 訊息」假裝有功能（劉老師 2026-05-07：「沒作用沒關係，開發階段」）

---

## 物理模型 parking lot（學術深度，等 M5 後再評估）

> 不開正式 issue，但記錄在這以避免反覆討論「為什麼還沒做」。
> 投入大、商業 demo 直接價值低；如果劉老師要投 paper 才考慮排期。

| Item | 為什麼 park | 投入估計 | 觸發條件 |
|------|------------|----------|----------|
| 完整 BEM aerodynamic loading distribution | Cp(λ,β) + tower shadow + wind shear + wind veer 已涵蓋 trend 級 demo；BEM 主要對應「葉片 root 細部載荷分布 paper」 | 2-3 週 | 投 Renewable Energy / Wind Energy 期刊章節需要時 |
| Curled-wake model（yaw skew 反向旋轉渦流對） | Bastankhah 2016 線性 deflection + DWM meander 已涵蓋 90% 場景；curled wake 補的是 yaw > 20° 時的細節 | 2 週 | 對齊 NREL FAST.Farm / Floris 比對驗證時 |
| Aeroelastic tower / blade FEM coupling | tower SDOF first-mode + blade 3P/1P modulation 已能看到關鍵特徵；FEM 是月級工程 | 1-2 個月 | 與材料力學 / 結構合作另開 paper 線時 |
| Cooling 系統 radiator fin 細部模型 | 整體換熱 + fouling 已能 demo cooling 故障；fin-level 細節是熱交換器論文用 | 1 週 | 投 Applied Thermal Engineering 時 |
| Sub-transient electrical X"d/X'd 行為 | LVRT/HVRT envelope + ride-through 已涵蓋 grid event；sub-transient 是 power system 細節 | 1 週 | 與 -27 保護電驛協調合併投 paper 時 |

---

## M2 後續 / M4-M6 預留區

> ROADMAP 詳見 `docs/product/ROADMAP.md`。

- M4 (2026-08)：Inventory 雙寫交易模型 + Cost ↔ Workflow 雙向（依 DN-03）
- M5 (2026-09)：RAG_Ultimate strategy 對接（Phase 3 ready 否則用 baseline placeholder）
- M6 (2026-10)：Friendly 廠商現場部署 + 第一份月報送業主沒被退件 + 簽 LOI/合約

---

## 廢棄 / 不做（避免反覆討論）

| Item | 為什麼不做 | 取代方案 |
|------|-----------|---------|
| windMindOM 整合容器（v0.5） | 過度工程；客戶要的是 working tool 不是 framework | Monolithic 5 modules（DEC-20260502-06） |
| Plugin SDK | 同上；M1-M6 內部就 5 個 module 不需要 plugin 抽象 | 直接寫進 `modules/` |
| 4 類 Turbine Adapter ABC | 第一個客戶只有 Z72；過早抽象 | M1 只做 Bachmann Z72；第二個 OEM 再考慮 |
| Workflow Hub 獨立 service | 一個 dev 維運不來 | 留在 monolith 內 `modules/workflow/` |

詳見 `docs/product/decision_log.md` DEC-20260502-06。
