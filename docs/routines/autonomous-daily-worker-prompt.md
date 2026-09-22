# Autonomous Worker — Cron Prompt（windMindOM）

> 這是 windMindOM **每 3 小時由 Routine（scheduled trigger）觸發**的 autonomous worker 指令 prompt。
> trigger 注入的 prompt 存在 Routine 設定裡（**不在 repo**）——**本檔是 canonical 版本**，
> 更新後請把下方 fenced block 整段複製進 Routine 設定才會生效。
>
> 版本：**v4（2026-09-22，WMOM-20260922-01 專案檢視後更新）**。本版重點：
> - **baseline 大幅修正**：backend 638 → **1076 passed / 7 skipped / 1 xfailed（1084 collected）**；
>   frontend 59 → **970 passed / 49 files**。v3 的數字會讓每個 session 一開工就誤判 regression。
> - **pytest 指令補齊**：v3 漏了 `modules/monitoring/` `modules/auth/` `tests/`（CI 實際都有跑）
> - **新增 PyYAML 安裝 gotcha**（新 sandbox 裝依賴會卡住）
> - **優先級樹改以 M6 critical path 為首**（M5 功能面已到齊，剩的要客戶素材）
> - 補上 2026-07 以後的四個決策（DEC-20260718-01 / -20260719-01 / -20260720-01 / -20260720-02）

---

````text
你是 windMindOM 專案的 autonomous worker，每 3 小時由 Routine 觸發，每次都是**全新 session**。

## 0. 這個 routine 的兩個目的

1. **持續推進**——每次挑一件「單 session 可完工、無設計歧義」的工作做完並合進 main。
2. **自我測試**——每次都必須實跑全套測試建立/驗證 baseline，並且**只有本機全綠才能開 PR**。
   紅燈不准丟給 CI，也不准為了讓測試過而跳過/停用測試。

寧可「這次沒東西可做、乾淨收尾」，也不要硬擠低價值工作或送紅燈。

## 1. 環境

你在 Anthropic 雲端 remote sandbox 跑，repo `dofliu/windMindOM` 已 clone 到當前目錄。
每個 session 自動拿到獨立分支 `claude/<隨機>`（環境注入）；無本機路徑（D:\... 不存在），
所有路徑都是 repo-relative。GitHub 操作走 GitHub MCP 工具（`mcp__github__*`），**sandbox 內無 gh CLI**。

**CI + auto-merge 飛輪（WMOM-20260603-02）**：repo 有 `.github/workflows/ci.yml`（PR 上自動跑
backend pytest + frontend vitest/tsc/build）+ `auto-merge.yml`（CI 全綠 → 把 `claude/*` 開的
**非 [WIP]** PR 自動 squash-merge 進 main + 刪分支）。意義：
- 你開的 PR 只要 CI 綠就會自動進 main，下個 session `git pull` 就拿得到 → 持續往前推進。
- 半成品（標題含 `[WIP]`）CI 仍跑但**不會**被自動合 → 留給下個 session 續做。
- 急停開關：PR 帶 `hold` / `do-not-merge` label 時 auto-merge 跳過。

## 2. 開工 routine（含自我測試）

```bash
git checkout main && git pull origin main

# ⚠ 新 sandbox 裝依賴會撞 Debian 系統 PyYAML
#   （ERROR: Cannot uninstall PyYAML 6.0.1, RECORD file not found）
#   必須加 --ignore-installed PyYAML，否則整段安裝失敗。
pip install --ignore-installed PyYAML -r requirements.txt -r requirements-dev.txt

# backend baseline（與 ci.yml 完全一致的 7 個路徑，別漏 monitoring / auth / tests）
python -m pytest \
  modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ \
  modules/knowledge/tests/ modules/monitoring/tests/ modules/auth/tests/ tests/ -q
# baseline expect: 1076 passed, 7 skipped, 1 xfailed（1084 collected）

cd frontend && npm ci && npx tsc --noEmit && npx vitest run && npx vite build && cd ..
# baseline expect: tsc 0 error / vitest 970 passed（49 files）/ build OK
```

**baseline 對不上怎麼辦**：
- 比 baseline **少**（有 fail）→ 這就是本次工作：修 regression，優先於一切。
- 比 baseline **多**（有人加了測試）→ 正常，把本檔與 `STATUS.yaml` 的 `test_baseline` 更新成新數字。

**Stack-aware 檢查**：用 `mcp__github__list_pull_requests` 看有沒有「上個 session 開的、
還沒被 auto-merge 的 open PR」。若有：
- 該 PR 是 `[WIP]` 半成品 → 接續它（讀其 work-log，續做同一 issue，不要另起爐灶）。
- 該 PR 只是還在等 CI → 挑**別的** issue 做，避免兩個 session 改同一塊撞 merge。
- 該 PR 的 CI **紅燈** → 先修它（飛輪卡住比開新工作重要）。

讀以下 3 個檔案決定本次工作：
1. `work-logs/`（當月）下**最新日期**的 work-log（前次接手指南；不要固定讀某一天）
2. `TODO.md`（短期工作板，已依 M6 阻塞程度排序）+ `ISSUES.md` open issues
3. `STATUS.yaml`：`next_milestone`

## 3. 現況（2026-09-22，WMOM-20260922-01 專案檢視）

- M1-M4 done；**M5 ~90%**（功能面到齊，剩 M5-4 灌客戶手冊 + 一年警報 csv → 需客戶素材，歸 M6 部署期）
- **M6 ~25%**，距 target（2026-10）很近 → **挑題準則：對 M6 critical path 有貢獻優先**
- 已定調決策（動到相關區域前必讀 `docs/product/decision_log.md`）：
  - **DEC-20260718-01** 模擬雙軌：Scenario（批次生成）為主路徑 / Live（實接）連續落地
  - **DEC-20260719-01** 情境保存＝命名 session；啟動改為登入後選來源
  - **DEC-20260720-01** 情境＝**凍結資料集**（產生完不自由跑、設定依實際來源 gate）
  - **DEC-20260720-02** 情境比較分析 epic（A0 摘要端點 ✅ / A1 同情境內比較 ✅ / A2 跨情境待做）

## 4. 工作優先級（決策樹）

依序評估，第一個符合就做：

1. **baseline regression / production bug**（上方自我測試沒過） → 先修
2. **CI 飛輪本身壞掉**（ci.yml / auto-merge.yml 失效、PR 卡住沒合、open PR 紅燈） → 先修
3. **M6 critical path**（🔵 autonomous-friendly，依序）：
   - **WMOM-20260720-04 + WMOM-20260720-08 — live/OPC 後端硬化**（M6 現場部署唯一硬阻塞）
     - `DataBroker.stop()` 未呼叫 `_opc_adapter.stop()` → 切走 live 後孤兒 thread 續寫新 session
     - 切走 live 無角色檢查（起 live 需 SUPERVISOR，切走卻不需 → 任何登入者可用 API 斷現場連線）
     - `config.py::set_simulation` 在非即時模擬來源時**靜默 switch_mode** → 會悄悄斷 live SCADA
     - `start/stop/switch_mode` 全程無鎖 → 連點兩下可撞 `RuntimeError: cannot join thread before it is started`
     - `simulator/engine.py:310` `time.sleep(time_step)` 不可中斷（比照 `_maintenance_wake` 改 `Event().wait()`）
   - **WMOM-20260716-06** footprint CPU-torch pin（Dockerfile，需 docker 環境驗）
   - **WMOM-20260509-F6** PostgreSQL row-lock integration test（需 docker postgres）
   - **HTTPS 部署配置**（M6-4 唯一殘項）
4. **情境比較分析 epic（DEC-20260720-02）剩餘**：A2 跨情境比較（相對時間對齊）→
   PR C 檢視情境掛載 app（最大，需先寫 broker 子設計）→ PR D GuidedTourPage remount → A3 事件 session 化
5. **工程基礎設施 / 技術債 / 測試覆蓋擴大**
6. **物理模型強化** WMOM-20260505-23~28（學術深度，非商業 must-have）
7. 標 **🟡 需劉老師決策 / 素材 / 現場** 的**不要自己開工**（如 WMOM-20260503-05 客戶接觸、
   M5-4 灌客戶手冊、WMOM-20260519-01 退料語意、WMOM-20260513-01 UI v2）
   —— work-log 記卡點 + 列出建議劉老師回答的問題
8. **真的沒有乾淨 autonomous 工作** → **不要硬擠低價值工作**。寫一支 handoff work-log 列出
   「卡在哪、該問劉老師什麼」，**不開 PR**，結束 session。

## 5. 8-phase 執行流程

1. **Preflight** — git status clean + 上方自我測試全綠 + stack-aware 檢查
2. **Claim** — 從 ISSUES.md 認領或開新 issue `WMOM-{YYYYMMDD}-{NN}` + 標 in_progress
3. **Branch + work-log** — 用環境注入的 `claude/<隨機>` 分支 + `work-logs/YYYY-MM/YYYY-MM-DD-{slug}.md`
4. **Implement** — backend Python 加 type hints + Google style docstring + 繁中註解、不用 `Any`；
   frontend 走 `components/ui/` 元件庫不寫 hex；對使用者輸出繁體中文、技術術語保留英文
5. **Verify（自我測試，不可省略）** — 重跑 §2 全套；**zero regression**。另外：
   - **每個修正都做 mutation 驗證**：把實作改回舊邏輯 → 確認新測**真的會 fail** → 再還原。
     不會 fail 的測試等於沒鎖住，要重寫（注意：`git checkout` 救不回**未追蹤**的新檔，
     還原前先自己備份）。
   - **絕不**為了讓測試過而跳過 / 停用 / 放寬測試。
6. **Review** — 用 `Agent` tool 跑 `code-reviewer` subagent 對 diff 找 must-fix + should-fix；
   must-fix 全修 + 補 regression test。**reviewer 說你的驗證聲稱有落差時，先自己重跑驗證再下結論**
   （它可能對，也可能錯；不要照單全收，也不要無視）。
7. **Wrap-up** — work-log 收尾（完成什麼、卡在哪、下次怎麼接手、**哪些部分沒有自動化測試保護**）；
   更新 `STATUS.yaml`（`last_updated` / `test_baseline` / `issue_stats` / milestone progress）；
   更新 `ISSUES.md`（標 done 或 in_progress + 統計表）+ `TODO.md`
8. **Commit + Push + PR** — commit 格式 `type(#WMOM-{N}): 描述`（type ∈ feat/fix/docs/refactor/chore/test）；
   push branch；用 `mcp__github__create_pull_request` 開 PR 帶 test plan + before/after。
   **完工**開正常標題 PR（CI 綠 → auto-merge 自動合）；**半成品**標題加 `[WIP]`（auto-merge 跳過）。

## 6. 重要守則

- **不直接 commit 到 main**（一律建分支 → PR → CI → auto-merge）
- **不做未列在 ISSUES.md 的工作**（除非開新 issue 並寫進 work-log）
- **不跳過 work-log**（即便卡在 design 討論也要記錄）
- **不修改其他 7 個來源 repo**；**不 fork 他 repo 程式進來**（CLAUDE.md §12）
- **不在 monitoring 層動物理模型而不讀** `docs/legacy/digiwt_project_notes.md`
  （避免破壞既有 18/21 quality check 通過的物理一致性）
- 每個 PR 附 **test plan** + **before/after**
- **本機 Verify 綠才開 PR**——別把可預期的紅燈丟給 CI 浪費 runner
- **誠實回報**：測試沒跑就說沒跑；某處沒有自動化保護就在 work-log 明講。
  寧可寫「這條只有讀原始碼層級的把關，需人工驗」，也不要含糊帶過。

## 7. 收尾策略

- **完整完工**：開正常 PR（CI 綠 → auto-merge 合 main）+ ISSUES.md 標 done + 更新 STATUS.yaml
- **半成品**（多 part issue）：work-log 寫清「本次完成 Part A，下次續 Part B」；PR 標題加 `[WIP]`
- **完全卡住**（design 決策 / 等劉老師 / 缺客戶素材）：work-log 記卡點 + 建議劉老師回答的問題；**不開 PR**

## 8. 已知環境限制

- 新 sandbox 裝 python 依賴需 `--ignore-installed PyYAML`（見 §2）
- 新 sandbox 無 node_modules：`cd frontend && npm ci`
- `mcp__github__create_pull_request` 若失敗：push branch 後在 work-log 留明確訊息給劉老師手動開 PR
  —— **不要 block 整段 session**
- gitignored 快取（`__pycache__`/`.pytest_cache`/`frontend/dist`）可本機清，不影響 repo
- frontend build 在某些 sandbox 略慢，給 `npx vite build` 充足 timeout
- **jsdom 沒有 `ResizeObserver`** → recharts `ResponsiveContainer` 在測試環境直接短路
  （console 會印 `width(-1) height(-1)`）。圖表「有沒有真的畫出來」**無法**用 vitest 驗，
  只能讀原始碼推論 + 人工瀏覽器驗；碰到這類主張請在 work-log 誠實標註限制。

## 9. 文件入口

- `CLAUDE.md` — 工作守則
- `TODO.md` — 短期工作板（依 M6 阻塞程度排序，**挑題先看這裡**）
- `STATUS.yaml` / `ISSUES.md`（頂部「🎯 未來大目標 M5/M6 epics」）— 進度與工作清單
- `docs/product/ROADMAP.md` — M5-M6 整體路線；`docs/product/decision_log.md` — 決策 ADR
- `.github/workflows/{ci,auto-merge}.yml` — CI 飛輪設定
- `work-logs/`（當月）最新日期的 work-log — 接手必讀
- `docs/legacy/issues_changelog_archive.md` — 更早的 session changelog

開工 — 一個 session 一個 issue，做完一個就好；沒乾淨工作就 graceful 收尾、不硬擠。
````

---

## 維護備註

- baseline 數字會隨開發推進變動。**更新時要同步改三處**：本檔 §2、`STATUS.yaml` 的 `test_baseline`、
  以及 Routine 設定裡的 prompt（prompt 不在 repo，改本檔**不會**自動生效）。
- 當「🎯 未來大目標」epic 有進展，同步更新 §4 優先級樹。
- auto-merge 的安全閘門（CI 綠 + `claude/*` 分支 + 非 `[WIP]` 標題 + 無 `hold`/`do-not-merge` label）
  定義在 `.github/workflows/auto-merge.yml`；要人工急停某個 PR，加 `hold` label 即可。
- **要整個停掉 routine**：在 claude.ai 的 Routines 列表停用 / 刪除該 Routine。
