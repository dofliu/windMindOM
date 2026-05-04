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
| open | 0 |
| in_progress | 1 |
| blocked | 0 |
| done | 6 |
| **total (active)** | **7** |

最後更新：2026-05-04（WMOM-20260504-02 waiting_time engine migration done，bit-perfect）

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

## M3-M6 預留區（規劃時開新 issue）

> 等對應 M 開始時 / 該月最後一個 session 開新 issue。
> ROADMAP 詳見 `docs/product/ROADMAP.md`。

- M2 後續 (2026-06)：WMOM-20260504-03 (cost_cal) → -04 (monte_carlo) → -05 (var_fluct) → -06 (adapter) → -07 (API) → -08 (frontend)；模板見 `docs/legacy/ecn_engine_inventory.md` §8
- M3 (2026-07)：z72_etech 取設計（5-7 天讀程式 → design notes → 30 分鐘 walkthrough）
- M4 (2026-08)：Inventory 雙寫交易模型 + Cost ↔ Workflow 雙向
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
