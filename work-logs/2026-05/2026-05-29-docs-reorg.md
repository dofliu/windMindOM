# 2026-05-29 — 專案文件大整理（WMOM-20260529-02）

> 劉老師交辦的文件整理 session（同日稍早完成 WMOM-20260529-01 mockUsers 測試、PR #59 已 merged）。
> Branch：`claude/kind-faraday-CWVM3`。Issue：**WMOM-20260529-02**。

---

## 1. 劉老師交辦的 4 點需求

1. 更新專案說明 / 規劃 / 工作文件，移除無用 / 不相關 / 重複的文件
2. 清除資料夾暫存檔
3. 重新整理未來後續工作，明確定義大目標 / 開 issue（問是否可用 workflow）
4. 更新 routine 指令 prompt 內容

開工前先全面盤點，提出計畫 + 4 個判斷題（Q1-Q4），劉老師回覆後執行。

## 2. 劉老師對 Q1-Q4 的決定

- **Q1**：移除 `z72SCADA_New/`（沒用到了）
- **Q2**：`docs/design/2026-05-07-ui-source/` 只留 `WMOM 介面改版交接書.md`，移除 .jsx/.html/promo 原型
- **Q3**：維持 ISSUES.md（bot 友善）+ 整理「大目標」成清晰 M5/M6 epic 區塊
- **Q4**：ISSUES.md 累積 changelog 抽到 `docs/legacy/issues_changelog_archive.md`，頂部只留最近 1-2 筆

## 3. 完成內容

### 3.1 清過時 digiWT 重複檔（需求 1）

盤點發現 root 殘留大量 digiWindTurbine 時代沒隨 windMindOM 更新的檔：

| 檔案 | 問題 | 處置 |
|---|---|---|
| `README.md` | 標題還是 `# digiWindTurbine`、0 處提 WMOM | 重寫為 windMindOM（5-module 概覽 + 文件地圖 + quick start，physics 細節指向 physics_model_status.md） |
| `AGENTS.md` / `GEMINI.md` | digiWT 描述、port 8000、0 處提 WMOM | 改為指向 `CLAUDE.md` 的薄 pointer（避免多份守則分歧） |
| `project.md` / `idea.md` | digiWT 專案描述 / Idea Notes | 刪（被 `docs/product/PRODUCT_VISION.md` 取代） |
| `docs/daily_report.md` | digiWT 日報、停 2026-05-01 | 刪（被 work-logs/ 取代） |
| `docs/session_handoff.md` | 停 2026-05-07 | 刪（被 work-logs 每日 wrapup-handoff 取代） |
| `package-lock.json`（root, 94B） | `{"name":"digiWindTurbine", packages:{}}` 空殼 | 刪（frontend 有自己的） |
| `docs/product/pitch_deck_v0.4_todo_revise.pptx` | 舊 v0.4、放錯層 | 刪（被 docs/sales/v0.8.1 取代） |
| `TODO.md` | 停在 2026-05-05「本月 M1」 | 刷新為 M5 現況 |

### 3.2 移除外部專案 dump（需求 1）

- `z72SCADA_New/`（13 tracked 檔）：另一專案原始碼（`wind_farm_backend.js`、`opc_service (2).js`、`api_routes_controllers (1).js` 等，檔名帶 `(1)`/`(2)` 下載重複後綴 + influx/nginx 備份）。CLAUDE.md §12 明訂不 fork 他 repo 程式；M3 設計擷取已產出 `docs/design-notes/m3/`，raw dump 無用 → `git rm`。
- `.gitignore` 移除 `z72SCADA_New/wind-backup/Z72_Data` 行，改加通用 `node_modules/` + `frontend/dist/`。

### 3.3 UI 原型只留交接書（需求 1，Q2）

`docs/design/2026-05-07-ui-source/` 只留 `WMOM 介面改版交接書.md`（設計決策紀錄），刪 app/shared/variants 的 .jsx + `WMOM App UI.html` + `digiWindTurbine 產品推廣介面.html` + `design-canvas.jsx`（UI 已實作，WMOM-20260507-01 done）。

### 3.4 清暫存檔（需求 2）

`__pycache__`/`.pytest_cache`/`frontend/dist` 本機 `rm`（皆 gitignored、本就未進 repo）。

### 3.5 ISSUES.md 瘦身 + M5/M6 epic（需求 3，Q3+Q4）

- 頂部累積 8 筆 session changelog → 抽最舊 7 筆到 `docs/legacy/issues_changelog_archive.md`（新增此檔 + 維護慣例：超過 2 筆就把最舊的搬過去），頂部只留最近 2 筆（5-29-02 / 5-29-01）+ archive pointer。
- 新增「🎯 未來大目標（M5 / M6 epics）」區塊：把 ROADMAP Month 5/6 拆成 EPIC-M5（M5-1~6 RAG + mobile）+ EPIC-M6（M6-1~6 PoC + 合約）+ 跨 milestone 持續工作，每項標 🔵 autonomous-friendly / 🟡 需劉老師。**維持 ISSUES.md 為 single source**（不轉 GitHub Issues），bot routine 不變。

### 3.6 routine prompt 更新（需求 4）

- 新增 `docs/routines/autonomous-daily-worker-prompt.md`（canonical 版 cron prompt）：修正 504→570 baseline、加 frontend 59 baseline、移除已 done 的 A6/A7/A10/WMOM-20260510-01、改「讀最新日期的 handoff」而非固定 5/10、優先級樹改指向 ISSUES.md 的 🎯 epic 區塊 + 🔵/🟡 標記、GitHub 操作改 mcp__github__*、加新 sandbox npm/pip install 提示。
- `docs/routines/daily-workflow.md`：檢查無過時 port/baseline 標記（通用流程文件，不動）。
- `docs/legacy/digiwt_directory_layout.md`：加歷史註記指向本 issue（不改寫 migration 快照）。

## 4. Verify（零 code regression）

| 項目 | 結果 |
|---|---|
| backend `pytest modules/{workflow,cost,reporting}/tests/` | 570 passed / 1 xfailed（純文件 + 死碼移除，未動 code） |
| frontend `vitest run` | 59 passed |
| frontend `tsc --noEmit` | 0 errors |
| frontend `vite build` | OK |
| 刪除檔是否被 import / 引用 | 已查：z72SCADA_New 僅被 digiwt_directory_layout.md（legacy 快照）引用、已加註記；其餘 .md 互引已更新 |

## 5. 下次 session 接手建議

- routine prompt 已更新版在 `docs/routines/autonomous-daily-worker-prompt.md` —— **劉老師需把該 fenced block 複製進 cron trigger 設定**（cron prompt 不在 repo 內，無法自動生效）。
- ISSUES.md 頂部「🎯 未來大目標」是之後 session 挑工的入口；標 🔵 的可自動接，🟡 的需劉老師。
- 維護慣例：每次 session 收尾時 ISSUES.md changelog 只留最近 1-2 筆，更舊的搬 `docs/legacy/issues_changelog_archive.md`。

## 6. 檔案異動清單

```
重寫  README.md / AGENTS.md / GEMINI.md / TODO.md
刪    project.md / idea.md / package-lock.json / docs/daily_report.md / docs/session_handoff.md
刪    docs/product/pitch_deck_v0.4_todo_revise.pptx
刪    z72SCADA_New/（13 檔）
刪    docs/design/2026-05-07-ui-source/ 的 .jsx/.html 原型（留交接書.md）
新    docs/legacy/issues_changelog_archive.md
新    docs/routines/autonomous-daily-worker-prompt.md
新    work-logs/2026-05/2026-05-29-docs-reorg.md（本檔）
改    ISSUES.md（瘦身 + epic 區塊 + WMOM-20260529-02 entry + stats）/ STATUS.yaml / .gitignore
改    docs/legacy/digiwt_directory_layout.md（歷史註記）
```
