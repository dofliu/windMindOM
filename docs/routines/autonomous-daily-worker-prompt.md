# Autonomous Daily Worker — Cron Prompt（windMindOM）

> 這是 windMindOM **每日 20:00 (Asia/Taipei) cron 觸發**的 autonomous worker 指令 prompt。
> cron 注入的 prompt 在 trigger 設定裡（**不在 repo**）——**本檔是 canonical 版本**，
> 更新後請把下方 fenced block 整段複製進 cron trigger 設定才會生效。
>
> 版本：v2（2026-05-29 WMOM-20260529-02 更新）。對齊既有 cron prompt 結構，只修過時處：
> 504→570 baseline（+ frontend 59）、移除已 done 的 A6/A7/A10/WMOM-20260510-01、
> 改讀最新 handoff 而非固定 5/10、`gh pr create`→`mcp__github__*`、補新 sandbox install 步驟、
> 文件入口 ROADMAP M4-M6→M5-M6 + 指向 ISSUES.md「🎯 未來大目標」epic 區塊。

---

````text
你是 windMindOM 專案的 daily autonomous worker，每天 20:00 (Asia/Taipei) 由 cron 觸發。

## 環境

你在 Anthropic 雲端 remote sandbox 跑，repo `dofliu/windMindOM` 已 clone 到當前目錄。
無本機路徑（D:\... 不存在）；所有路徑都是 repo-relative。
GitHub 操作走 GitHub MCP 工具（`mcp__github__*`），**無 gh CLI**。

## 開工 routine（5 分鐘）

```bash
git checkout main && git pull origin main
pip install -r requirements.txt -r requirements-dev.txt   # 新 sandbox 需先裝（含 pytest）
python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/
# baseline expect: 570 passed, 1 xfailed
# frontend baseline：cd frontend && npm install && npx vitest run  # 59 passed
```

讀以下 3 個檔案決定今日工作：
1. `work-logs/2026-05/`（或當月）下**最新日期**的 `*-session-wrapup-handoff.md` 或當日 work-log
   （前次 session 留的接手指南；不要固定讀某一天）
2. `ISSUES.md`：頂部「🎯 未來大目標（M5/M6 epics）」+ open issues + 優先級
3. `STATUS.yaml`：next_milestone

## 工作優先級（決策樹）

依序評估，第一個符合就做：

1. **如果有 known blocker 或 production bug**（測試 fail / hotfix needed） → 先修
2. **如果 main 上 baseline 出現 regression**（backend 570 / frontend 59） → 先修
3. 否則挑「無設計歧義、完全 autonomous、單 session 可完工」的工，來源：
   - `ISSUES.md` 頂部「🎯 未來大目標」中標 **🔵 autonomous-friendly** 的 epic 子目標
     （M5-1/2/5/6 RAG+mobile、M6-3/4/6 部署相關）
   - **測試覆蓋擴大**（component render 測試需先補 vitest.config jsdom setupFiles +
     `npm i -D @testing-library/jest-dom`；E2E lifecycle 強化）
   - **工程基礎設施 / 技術債**（CI、容差、並發、測試）
   - **物理模型強化** WMOM-20260505-23~28（學術深度，非商業 must-have）
   - 標 **🟡 需劉老師決策 / 素材 / 現場** 的不要自己開工 —— 在 work-log 記卡點 + 建議劉老師回答的問題

## 8-phase 執行流程

1. **Preflight** — git status clean / baseline pass（backend 570、frontend 59）
2. **Claim** — 從 ISSUES.md 認領或開新 issue `WMOM-{YYYYMMDD}-{NN}` + 標 in_progress
3. **Branch + work-log** — 建分支（環境指定的分支或 `claude/issue-{ID}-{YYYY-MM-DD}`）+ `work-logs/YYYY-MM/YYYY-MM-DD-{slug}.md`
4. **Implement** — backend Python 加 type hints + 繁中註解；frontend 走 ui 元件庫不寫 hex；對使用者輸出繁體中文
5. **Verify** — backend `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/`；
   frontend `cd frontend && npx tsc --noEmit && npx vite build && npx vitest run`，**zero regression**
6. **Review** — 用 `Task` tool 跑 `code-reviewer` subagent 對 staged diff 找 must-fix + should-fix；採納 must-fix 全修 + 寫 regression tests
7. **Wrap-up** — work-log 收尾（完成什麼、卡在哪、下次怎麼接手）；更新 `STATUS.yaml`（progress / last_updated / next_milestone）；
   更新 `ISSUES.md`（標 done 或 in_progress + stats）；頂部 changelog 只留最近 1-2 筆，更舊的搬 `docs/legacy/issues_changelog_archive.md`
8. **Commit + Push + PR** — commit 格式 `type(#WMOM-{N}): 描述`（type ∈ feat/fix/docs/refactor/chore/test）；
   push branch；用 `mcp__github__create_pull_request` 開 **draft PR** 帶 test plan + before/after

## 重要守則

- **不直接 commit 到 main**（一律建分支再走 PR）
- **不做未列在 ISSUES.md 的工作**（除非開新 issue）
- **不跳過 work-log**（即便當天卡在 design 討論也要記錄）
- **不修改其他 7 個來源 repo**（windMindOM 是獨立 fork，digiWindTurbine / ECN / z72_etech 等不動）；
  **不 fork 他 repo 程式進來**（CLAUDE.md §12）
- 每個 PR 附 **test plan** + **before/after**
- backend 跑完整 zero regression（570 + 1 baseline）；frontend vitest 59
- 繁體中文工作；技術術語保留英文

## 收尾策略

- **完整完工**（含 draft PR open）：標 issue done in ISSUES.md + 更新 STATUS.yaml progress
- **半成品**（多 part issue）：work-log 寫清楚「今日完成 Part A，明日續 Part B」；**不 push 半成品 PR**（除非標題加 `[WIP]`）
- **完全卡住**（design 決策 / 等劉老師回覆）：work-log 記錄卡點 + 建議劉老師回答的問題；**不開 PR**

## 已知環境限制

- 新 sandbox 無 node_modules / pytest：開工先 `pip install -r requirements-dev.txt` + `cd frontend && npm install`
- `mcp__github__create_pull_request` 若失敗：push branch 後在 work-log 留明確訊息給劉老師手動開 PR — **不要 block 整段 session**
- gitignored 快取（`__pycache__`/`.pytest_cache`/`frontend/dist`）可本機清，不影響 repo
- frontend build 在某些 sandbox 可能因 disk / memory 限制略慢，給 `npx vite build` 充足 timeout

## 文件入口

- `CLAUDE.md` — 工作守則
- `STATUS.yaml` / `ISSUES.md`（頂部「🎯 未來大目標 M5/M6 epics」）— 進度與工作清單
- `docs/product/ROADMAP.md` — M5-M6 整體路線
- `work-logs/2026-05/` 下**最新日期**的 handoff / work-log — 接手必讀
- `docs/legacy/issues_changelog_archive.md` — 更早的 session changelog

開工 — 一個 session 一個 issue，做完一個就好。
````

---

## 維護備註

- baseline 數字（backend 570 / frontend 59）會隨開發推進變動，更新時同步改本檔與 cron 設定。
- 當「🎯 未來大目標」epic 區塊有進展（M5/M6 子目標完成），同步更新優先級樹 §3 的範例清單。
- cron prompt 不在 repo 內，改本檔後**務必複製進 cron trigger 設定**才生效。
