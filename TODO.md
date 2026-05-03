# windMindOM — TODO（短期工作板）

> 用途：本檔案是「**這週 / 這個月**正在做什麼」的快速 dashboard。
> 詳細 issue 規格在 [`ISSUES.md`](ISSUES.md)；完整路線圖在 [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md)。
>
> 規則：
> - 只列「進行中 + 下一個要做」的事，**不列已完成**（done 的事看 git log + ISSUES.md）
> - 每次 session 開頭 / 結尾更新本檔
> - 大局看 ROADMAP；今日工作看 ISSUES.md；本週/本月節奏看本檔

最後更新：2026-05-03（WMOM-20260503-01 完成）

---

## 本月（2026-05）— M1：Setup baseline

> 目標：repo baseline + 規劃文件就位 + friendly 客戶接觸
> Done criteria：M1 月底能對 friendly 客戶 demo「跑起來的 simulator + 5 modules 規劃故事」

### 第一週（2026-05-03 ~ 2026-05-09）

- [x] 建立 windMindOM 版 STATUS.yaml / ISSUES.md / TODO.md
- [x] **WMOM-20260503-01** — Repo baseline 整理（digiWT 搬到 `modules/monitoring/`）✅ 半天完成（採 sys.path 注入策略）
- [ ] **WMOM-20260503-02** — 搬入 v0.5 有用資產（pitch deck baseline、templates 盤點）⬅ next
- [x] **WMOM-20260503-03** — Root CLAUDE.md 改為 windMindOM 產品脈絡（已於 2026-05-02 baseline commit 完成）
- Follow-up（不卡 -02 / -04 / -05）：
  - [x] 完整 `python run.py` + browser dashboard 驗證 ✅ 2026-05-03 用戶截圖確認：14 台 WTG OPERATING、3.55 MW、6.2 m/s、台中港曲風場 active、5-min trend 即時更新、WTG-01~14 個別 130~420 kW 散布合理
  - [x] `docker-compose` 設定驗證（**靜態**） ✅ 2026-05-03：YAML parse + COPY directives + env vars (DB_PATH, FARM_DATA_DIR) + volume mount + 相對路徑等價性 全部 PASS。實際 `docker compose up --build` deferred — 本機未裝 Docker Desktop，留給之後（部署 partner / 客戶端 / overnight 跑）做
  - [x] 重跑 `examples/data_quality_analysis.py` ✅ 2026-05-03：跑短版 0.17h × 5 turbines（3060 rows）→ 15/16 quality check pass，風速↔功率 r=+0.970、1P振動↔轉速 r=+0.944、無 NaN、無 out-of-range，物理鏈完整。完整 2h baseline 對照留給之後 overnight 跑。Driver：`modules/monitoring/examples/_post_migration_quick_validate.py`、Pre-migration baseline 已備份 `*_pre_migration_baseline.{txt,csv}`

### 第一週收尾（提前完成）

- [x] **WMOM-20260503-04** — Pitch deck v0.8.1（從零畫，A2 路線）✅ 2026-05-03 完成 — `docs/sales/pitch_deck_v0.8.1.pptx`（10 頁 Navy）+ outline.md + build script

### 第二、三週（2026-05-10 ~ 2026-05-23）

- [ ] **WMOM-20260503-02** — templates 盤點（範圍縮小：只剩盤點 templates/ + claude-code-templates/，pitch_deck 已併入 -04）
- [ ] 整合 `pyproject.toml`（既有 digiWT deps + 預留 cost/workflow/RAG lib）
- [ ] CHANGELOG.md 從零建立（記錄 v0.8.1 baseline 之後的變動）
- [ ] 確認 `docs/routines/daily-workflow.md` 與本月實際跑的流程一致
- [ ] **WMOM-20260503-05** — Friendly 客戶接觸名單（盤點 + 至少 1 場 demo）—— deck 已就位

### 第四週（2026-05-24 ~ 2026-05-30）

- [ ] M1 月底 retro：更新 STATUS.yaml + ROADMAP M1 → done、決定 M2 第一週要先做哪個 risk validation

---

## 下個月（2026-06）— M2：Cost module 移植

> 目標：ECN backend 移植進 `modules/cost/` + K13 demo dataset 跑通
> Done criteria：給定一年 SCADA + maintenance log → 算出 LCOE = X.X NT$/kWh + 成本拆解 dashboard

### M2 第一週風險清單（**不能拖**）

- [ ] **K13 demo dataset 跑通**（第一週就要做；不過則 ECN 移植數字錯了不能拖到 M5 才發現）
- [ ] 確認 ECN 計算結果與原 ECN tool 數字一致（容忍 ±0.5%）

詳見 [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md) Month 2。

---

## Parking lot（park 起來的 idea / 不在當前 milestone）

不丟掉，但也不在當前 sprint 排程：

- M6 之後：windAILab AI 故障診斷 HTTP API 介接（Enterprise 套餐）
- M6 之後：InduSpect AI 視覺定檢介接（如有客戶要）
- M6 之後：第二個 OEM PLC adapter（Vestas / SGRE）
- M5 之後：RAG_Ultimate Phase 3 升級（chunking 策略、評估指標）
- 任何時候：物理模型升級（既有 18/21 quality 已通過，非 must-have；新 issue 從 `docs/legacy/digiwt_TODO.md` parking lot 找）

---

## 已封存的歷史 TODO（digiWT 階段）

`docs/legacy/digiwt_TODO.md` ← 既有 244 條物理 / SCADA / fatigue / wake 細節改進清單。
未來如要動 monitoring 層，先翻這份找 reference，**不要重複造輪子**。
