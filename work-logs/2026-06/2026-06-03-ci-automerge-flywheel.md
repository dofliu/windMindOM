# 2026-06-03 — CI + auto-merge 飛輪 + routine 改 3-hourly（WMOM-20260603-02）

> 劉老師交辦：把 autonomous worker 從「每日 1 次」改成「**每 3 小時 1 次**」，
> 並導入 **CI + auto-merge 飛輪**（CI 綠自動合 main），授權 bot 自動 merge。

---

## 1. 背景 / 決策

劉老師希望提高 autonomous 開發頻率「往前精進」。直接把 cron 改每小時的 3 個結構性風險：
1. **repo 完全沒 CI**（`.github/workflows/` 空）→ 每個 session 開 PR 等人工 merge，高頻 = PR 堆積而非推進。
2. 固定分支撞車 —— **實測為非問題**：每個 session 本來就拿到獨立 `claude/<隨機>` 分支（git log:
   gifted-maxwell / kind-faraday / upbeat-davinci 各不同）。
3. autonomous 工作存量有限，過高頻會抽乾 🔵、逼出低價值工作。

→ 結論（與劉老師確認）：**先建 CI + auto-merge 讓 PR 自驗自合**，頻率定 **每 3 小時**（非每小時，
平衡飛輪速度與工作存量 / review 負擔），auto-merge **授權 bot**。

## 2. 範圍（本 session）

| 檔案 | 內容 |
|---|---|
| `.github/workflows/ci.yml`（新） | PR + push main 觸發；2 jobs：backend pytest（workflow+cost+reporting+knowledge，638）+ frontend（`npm ci`→`tsc --noEmit`→`vitest run`→`vite build`）；`concurrency` 取消同分支舊 run |
| `.github/workflows/auto-merge.yml`（新） | `workflow_run`(CI completed) 觸發；CI 綠 + head=`claude/*` + 標題非 `[WIP]` + 無 `hold`/`do-not-merge` label → `gh pr ready` + `gh pr merge --squash --delete-branch` |
| `docs/routines/autonomous-daily-worker-prompt.md` | routine prompt v2→**v3**：每日→每 3 小時、baseline 570→638、stack-aware preflight、graceful no-op、PR 收尾語意對齊 auto-merge |
| `ISSUES.md` / `STATUS.yaml` | 新增 issue 條目 + stats done 51→52 / total 65→66；6/01 changelog 搬 archive |

## 3. 設計要點

- **auto-merge 用 `workflow_run` 而非 `pull_request` 觸發**：workflow 檔一律取自 main（預設分支），
  惡意 / 出錯的 PR 改不到合併邏輯（安全）。`permissions: contents+pull-requests: write` 讓 GITHUB_TOKEN 能合。
- **4 重安全閘門**：CI success + `claude/*` 分支 + 標題非 `[WIP]` + 無 `hold`/`do-not-merge` label。
  半成品用 `[WIP]` 標題擋；人工急停加 `hold` label。
- **draft 相容**：auto-merge 先 `gh pr ready`（draft→ready）再 squash → routine 仍可開 draft PR，
  CI 綠後自動升 ready + 合併。
- **CI scope = 既有 green baseline**（workflow/cost/reporting/knowledge 638），不含 monitoring/physics
  重測（避免引入未知紅燈擋住飛輪；之後可另開 issue 擴 CI scope）。
- **squash merge + delete branch**：main 線性歷史、bot 分支自動清。

## 4. 落地流程（避免 stats 衝突）

#69（M5-6）與本 PR 都改 `ISSUES.md` / `STATUS.yaml` stats hotspot → 為免 merge 衝突：
1. 先把 #69 標 ready + **squash-merge** 進 main（已本機驗 638 passed）。
2. 本 CI 分支 `git rebase origin/main`（此時尚未碰 ISSUES/STATUS，rebase 無衝突）。
3. 在 post-#69 數字上補本 issue 的 tracking（done 51→52 / total 65→66）。

## 5. Verify

- `ci.yml` / `auto-merge.yml` YAML `yaml.safe_load` 解析通過、jobs 結構正確。
- backend baseline 本機重跑 **638 passed / 1 xfailed**（純 infra 變更、不動 code，零 regression）。
- CI workflow 本身會在「加入 ci.yml 的這個 PR」上首次運行（`pull_request` 讀 PR 分支的 workflow）→
  可在 merge 前驗證 CI 真的綠。
- **auto-merge.yml 對本 PR 不生效**（workflow_run 取 main 版，main 還沒有它）→ 本 bootstrap PR
  需**人工 merge**（劉老師授權，bot 自合）；merge 後飛輪對後續所有 PR 生效。

## 6. 劉老師需手動做的事（repo 側無法代勞）

1. **Claude Code on the web trigger 設定**：把排程從每日 20:00 改成**每 3 小時**，
   並把 `docs/routines/autonomous-daily-worker-prompt.md` 內 fenced block（v3）整段貼進 trigger prompt。
   （cron prompt 不在 repo，改檔不會自動生效。）
2. （可選）repo Settings 確認允許 **squash merge**（GitHub 預設開）。

## 7. 下次 session 接手建議

- 飛輪上線後，後續 PR 只要本機 Verify 綠 + 開正常標題 PR，CI 綠即自動合 main、自動刪分支。
- **下一步候選**（依 🎯 EPIC-M5）：M5-5 `/field/` mobile 前端串 knowledge router（🔵 PMF 關鍵）/
  M5-2 ChromaDB（🔵 需 chromadb 依賴）/ M5-3 RAG_Ultimate 真向量檔（🟡）。
- **CI scope 擴充**（技術債候選）：之後可評估把 monitoring/physics 測試納入 CI（先確認在 Linux runner green）。
