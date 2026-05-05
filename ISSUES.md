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
| open | 9 |
| in_progress | 3 |
| blocked | 0 |
| done | 14 |
| **total (active)** | **26** |

最後更新：2026-05-05（WMOM-20260505-01 hotfix 開工 — snapshots 表失控 41.9 GB；WMOM-14 並行 in_progress 在 PR #2 內）

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

- **Status**: in_progress（2026-05-05 開工）
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

- **Status**: in_progress（2026-05-04 開工 — 第一份 DN-01 雛形）
- **Milestone**: M3
- **Priority**: critical（**M3 spike**，blocking 後續 -16 / -17 / -18 設計決策）
- **Estimate**: 1-2 工作天（單人讀完 ~20 個 module + 3 份 design notes）
- **Owner**: Claude (session 2026-05-04 / 2026-05-05)
- **Etech repo 路徑**: `D:\Project_CodingSimulation\researchTopic\windFarmMonitor\z72_SCADA_etech`
- **Etech baseline**: `yitai-corp-cms-download1140811/`（2025-08-11 線上抓回）
- **取材原則**：**僅取設計、不取程式**（CLAUDE.md §5）；產出 design notes 寫進 `docs/design-notes/m3/`，windMindOM 內全部重寫
- **Description**:
  劉老師 2026-05-04 給的 domain summary：
  > etech 是 onshore 簡化版：故障 → 派工單 → 檢修 + 每日工作日誌 + 簽核 + (領料連庫存) → 連結人員 → work order；offshore 延伸 = vessel / weather window logistics

  3 份 design notes：
  1. **DN-01: Work Order Lifecycle** — repair/repairTemp/trackFrom/removeFrom 四 collection 的工單流程；onshore baseline + offshore 延伸 (vessel / WW / crew)
  2. **DN-02: Approval Multi-level** — leadersign / supervisorsign / employeesign / affairsign 四個 sign collection 的權限分流（500/666/300/100 group）；windMindOM 統合為單表 + level 設計
  3. **DN-03: Inventory ↔ Material Request** — `materialsForm` + `materialsFormNotic{,Led}` + 4 欄位（新品/良品/維修中/待檢驗）庫存模型（M4 主菜的前置）

- **Deliverable**:
  - [ ] `docs/design-notes/m3/DN-01-work-order-lifecycle.md`（**今天主軸**）
  - [ ] `docs/design-notes/m3/DN-02-approval-multilevel.md`
  - [ ] `docs/design-notes/m3/DN-03-inventory-material-request.md`
  - [ ] `docs/design-notes/m3/README.md`（3 份 DN 索引 + etech repo 對照表）
- **Reference**:
  - 盤點報告：[`z72_SCADA_etech/專案盤點報告_2026-04-30.md`](../windFarmMonitor/z72_SCADA_etech/專案盤點報告_2026-04-30.md)
  - 重構路線圖：[`z72_SCADA_etech/重構路線圖_2026-04-30.md`](../windFarmMonitor/z72_SCADA_etech/重構路線圖_2026-04-30.md)
  - CLAUDE.md §5（z72_etech 取材選 A）
  - CLAUDE.md §15（windMindOM 重寫不 fork etech 程式）

---

### WMOM-20260504-15 — 30 分鐘 walkthrough 跟劉老師確認 design notes

- **Status**: open（依賴 -14 三份 DN 完成）
- **Milestone**: M3
- **Priority**: high
- **Estimate**: 0.5 工作天
- **Description**:
  把 -14 的 3 份 DN 跑一遍，請劉老師驗證：
  - 我對 etech 流程的理解有沒有誤解
  - windMindOM 的 offshore 延伸方向（vessel / WW / crew / 雙 persona）對齊真實客戶需求
  - 任何「etech 沒有的設計」是否該補（如 mobile field UX、RAG 警報整合 hook）
  - 用「30 分鐘 walkthrough」的形式記錄問答進 DN 文件（增 `## walkthrough notes` 區塊）

---

### WMOM-20260504-16 — Work Order 領域模型 + 狀態機（pure domain）

- **Status**: open（依賴 -14 DN-01 + -15 walkthrough confirm）
- **Milestone**: M3
- **Priority**: critical
- **Estimate**: 1 工作天
- **Description**:
  根據 DN-01 寫 Python 領域模型（pure dataclass + enum + 狀態機 transitions）：
  - `modules/workflow/domain/work_order.py`：`WorkOrder` dataclass / `WorkOrderStatus` Enum
  - `modules/workflow/domain/state_machine.py`：states + allowed transitions + guard 條件
  - `modules/workflow/tests/test_state_machine.py`：所有 transition 正例 / 反例
  - **不接 SQLAlchemy / FastAPI**，純 domain 層；下個 issue 才 wrap

---

### WMOM-20260504-17 — Work Order CRUD + REST API + tests

- **Status**: open（依賴 -16 domain model）
- **Milestone**: M3
- **Priority**: critical
- **Estimate**: 1 工作天
- **Description**:
  - `modules/workflow/repository/work_order_repository.py`：SQLAlchemy / SQLite
  - `modules/workflow/routers/work_order_router.py`：CRUD + 狀態 transition endpoints
    - `POST /api/workflow/work-orders` (create draft)
    - `POST /api/workflow/work-orders/{id}/dispatch` (transition)
    - `POST /api/workflow/work-orders/{id}/start-work`
    - `POST /api/workflow/work-orders/{id}/finish` + 含 followup 分支 (≡ etech `chooseschange`)
    - `POST /api/workflow/work-orders/{id}/close`
    - `GET /api/workflow/work-orders` (list with filter: status / farm_id / Hnumber)
  - `modules/workflow/tests/test_work_order_api.py`

---

### WMOM-20260504-18 — Approval 多階簽核 + tests

- **Status**: open（依賴 -14 DN-02 + -17 work order endpoints）
- **Milestone**: M3
- **Priority**: critical
- **Estimate**: 1 工作天
- **Description**:
  根據 DN-02 把 etech 的 4 個 sign collection 統合：
  - `modules/workflow/domain/signoff.py`：`Signoff` + `SignoffLevel` enum (employee / leader / supervisor / admin)
  - `modules/workflow/routers/approval_router.py`：
    - `GET /api/workflow/approvals/pending?user_role=...&user_id=...`（"我的待簽"）
    - `POST /api/workflow/approvals/{id}/approve`
    - `POST /api/workflow/approvals/{id}/reject`
  - 工單完工 → 自動建 signoff entries (依 work order type + farm policy)
  - tests: 單階簽核 / 多階串接 / reject / 並行多人

---

### WMOM-20260504-19 — `/admin/workflow/orders` frontend（建立精靈 + 列表 + 詳情）

- **Status**: open（依賴 -17 API）
- **Milestone**: M3
- **Priority**: high
- **Estimate**: 1-1.5 工作天
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
- **Description**:
  - `frontend/components/workflow/PendingApprovalPanel.tsx` 待簽列表（badge 含工單摘要 + 簽核層級）
  - `frontend/components/workflow/ApprovalActionDialog.tsx` 簽核 / 駁回對話框（含意見輸入）
  - 整合進 `WorkflowPage.tsx`（tab 切換 orders / approval）
  - 全 zh / en i18n

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
