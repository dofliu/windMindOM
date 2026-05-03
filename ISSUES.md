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
| open | 2 |
| in_progress | 0 |
| blocked | 0 |
| done | 3 |
| **total (active)** | **5** |

最後更新：2026-05-03（WMOM-04 done；-02 範圍縮小，待認領；-05 待認領）

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

### WMOM-20260503-02 — 搬入 v0.5 有用資產（範圍縮小）

- **Status**: open（範圍 2026-05-03 縮小）
- **Milestone**: M1
- **Priority**: medium（從 high 降）
- **Estimate**: 0.5 工作天
- **Owner**: -
- **Scope correction (2026-05-03)**:
  原 description 預設 v0.5 有 pitch deck baseline 可搬。**事實上 `docs/product/`
  只有 `pitch_deck_v0.4_todo_revise.pptx` 一份 v0.4 舊版**，v0.5 無 deck，
  v0.8.1 經 DEC-20260502-06 已決定**棄用** v0.4 / v0.5 全部 deck 思維。
  → pitch_deck 部分**從本 issue 移除**，併入 WMOM-20260503-04（從零畫 v0.8.1 deck）
  → 本 issue 剩下：盤點 `templates/` + `docs/claude-code-templates/` 是否完整
- **Description（縮小後）**:
  盤點 root `templates/`（work-log / issue / decision 模板）和
  `docs/claude-code-templates/` 是否完整、能否直接給後續 daily-workflow 用。
  缺什麼補什麼，多餘的不動。
- **Deliverable**:
  - 一張清單寫進本 issue 或 work-log，列出兩個 templates 資料夾的內容、缺漏項
- **Depends on**: -（WMOM-20260503-01 已 done）
- **Blocks**: -（pitch deck 已從本 issue 移除）
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

### WMOM-20260503-04 — Pitch deck v0.8.1（從零畫，A2 路線）

- **Status**: done（2026-05-03 完成）
- **Milestone**: M1
- **Priority**: high
- **Estimate**: 1-2 工作天 → **實際 ~1 小時 build + driver setup**（pptxgenjs 程式化生成代替手動拉投影片）
- **Owner**: Claude (session 2026-05-03)
- **Completion summary**:
  - ✅ 10 頁 Navy 主題 deck 產出 — `docs/sales/pitch_deck_v0.8.1.pptx`（421 KB）
  - ✅ 對照大綱寫入 `docs/sales/pitch_deck_v0.8.1_outline.md`（每頁 source 對照、設計決策、後續微調建議、重產指令）
  - ✅ Build script 永久化 — `tools/pitch_deck/build_v0.8.1.js`（pptxgenjs，未來改版只改 script 重 build）
  - ✅ 採 pptx-jliu-style skill 規範：Navy theme、Microsoft JhengHei、16:9（13.33×7.5）、策略B 物件最小化（fill 直接綁 text）
  - ✅ python-pptx QA：10 slides 全部含正確內容、頁碼、footer、競品矩陣表格、roadmap timeline 卡片都正確渲染、無亂碼
- **Visual verification**: 待用戶在 PowerPoint 開啟確認視覺（本機未裝 LibreOffice 無法自動轉 PDF）
- **Scope correction (2026-05-03)**:
  與用戶討論後決定走 **A2 = 從零畫**，不沿用 v0.4 任何 slide
  （包括競品矩陣、USPs 也重做以對齊 v0.8.1 narrative）。理由：v0.4 ICP
  寫「業主」與 v0.8.1 「運維廠商」完全衝突，slide 4「核心 4 模組 + plugins」
  與 v0.8.1 monolithic 5 modules 衝突，slide 7 套餐結構也要全換
  （OM-Core+addon → Operator Basic/Pro/Enterprise）。改寫成本 ≥ 從零畫，
  乾脆從 PRODUCT_VISION.md / ROADMAP.md / MVP_ARCHITECTURE.md 重抽 source-of-truth
- **Description**:
  以 v0.8.1 「**離岸風場運維廠商工具**」定位，做 10 頁 sales deck：
  Cover / ICP & 痛點 / 解法 / 5 modules 圖 / Simulator-first killer feature /
  三層套餐 / 競品矩陣 / Z72 first customer / 6-month Roadmap / Ask
- **Approach**:
  - 用 `pptx-jliu-style` skill（用戶 global CLAUDE.md 預設）
  - **Navy 主題（科技類）**
  - 每 slide 重點 ≤ 3 條、繁中為主、技術詞保留英文
- **Deliverable**:
  - `docs/sales/pitch_deck_v0.8.1.pptx`
  - `docs/sales/pitch_deck_v0.8.1_outline.md`（投影片大綱與每頁 source 對照）
  - （optional）一頁 onepager PDF — 列為 follow-up
- **Depends on**: -（與 -02 解耦後即可）
- **Blocks**: WMOM-20260503-05（接觸客戶要先有可寄的 deck）
- **Reference**:
  - [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md)（ICP、5 modules、商業模式、競品）
  - [`docs/product/MVP_ARCHITECTURE.md`](docs/product/MVP_ARCHITECTURE.md)（5 modules 設計）
  - [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md)（M1-M6 6 個月路線圖）
  - [`docs/product/decision_log.md`](docs/product/decision_log.md) DEC-20260502-06（v0.5→v0.8.1 pivot）
  - `CLAUDE.md` §15 「第一個客戶定 Z72」

---

### WMOM-20260503-05 — Friendly 客戶接觸名單

- **Status**: open
- **Milestone**: M1
- **Priority**: medium
- **Estimate**: 0.5 工作天（盤點）+ 持續整月（接觸）
- **Owner**: -
- **Description**:
  整理 1-2 個 friendly 運維廠商接觸名單（透過學界人脈、demo simulator 給他們看）。
  - 來源：NCUT 學界人脈、台電/中能/CIP 風場運維分包商、Bachmann Taiwan 客戶
  - 目標：M1 月底前約到 1 場 30 分鐘 demo
  - 不需要 commit；目的是收集真實 pain points 餵 M3-M5 設計
- **Deliverable**:
  - `docs/sales/friendly_contacts.md`（私密清單，contact 資訊 + 接觸狀態 + 對應 pain points）
  - 至少 1 場 demo 的回饋紀錄寫進 `docs/sales/customer_feedback/{YYYY-MM-DD}-{slug}.md`
- **Depends on**: WMOM-20260503-04（先有 deck）
- **Reference**: `docs/product/PRODUCT_VISION.md` §ICP（運維廠商）

---

## M2-M6 預留區（規劃時開新 issue）

> 不在 M1 範圍。等 M1 結束時 / 每月最後一個 session 開新 issue。
> ROADMAP 詳見 `docs/product/ROADMAP.md`。

- M2 (2026-06)：ECN 移植 + K13 demo dataset 跑通（**第一週就要做**，避開最大 risk）
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
