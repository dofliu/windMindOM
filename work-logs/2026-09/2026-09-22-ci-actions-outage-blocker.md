# 2026-09-22 — CI（GitHub Actions）infra-level 紅燈，飛輪整條卡住

> Session 類型：autonomous worker（3 小時 cron）
> Session 長度：短
> 結果：**完全卡住，未開新 PR**。診斷出 CI 飛輪本身壞在 GitHub Actions runner 排程層級（非任何 PR
> 的程式問題），需劉老師到 GitHub 網頁 Settings 檢查 Actions 用量 / 權限。已在 PR #156 留言記錄診斷。

---

## 1. 開工狀態

- `git status` clean，分支 `claude/inspiring-mccarthy-0nxczg`（環境注入）。
- **Stack-aware 檢查**（有 GitHub MCP）：`mcp__github__list_pull_requests` 看到唯一一個 open PR
  **#156**（`fix(#WMOM-20260720-04): live/OPC 後端硬化——收尾 M6 現場部署唯一硬阻塞`），
  head branch `claude/inspiring-mccarthy-mgelcq`，由上一個 3 小時 cycle 的 session 在
  `2026-09-22T06:43` 開出，內容已完成 §4 決策樹第 3 項的 M6 critical path 工作
  （WMOM-20260720-04 + -08 live/OPC 生命週期硬化 5 個子問題），PR body 聲稱本機驗證
  backend 1093 passed / frontend 957 passed 全綠。
- 依決策樹「該 PR 的 CI 紅燈 → 先修它（飛輪卡住比開新工作重要）」：檢查該 PR 的 CI，發現兩個 job
  都是紅燈，**優先處理這個，本次 session 沒有再往下挑新 issue**。

## 2. CI 紅燈診斷

`mcp__github__actions_list` 查 `ci.yml` 在該分支的 run：

| Run | Attempt | 觸發方式 | 結果 | 耗時 |
|---|---|---|---|---|
| #35696159147（run #140） | 1 | PR push | failure | `created_at` → `completed_at` 僅 **6 秒** |
| #35696186866（run #141） | 2 | 後續 push（補連結 commit） | failure | 僅 **~3 秒** |
| #35696186866（run #141） | 3 | 本 session 手動 `rerun_failed_jobs` | failure | 僅 **~6 秒** |

三次的兩個 job（`Backend pytest` / `Frontend vitest + tsc + build`）皆：
- `runner_id: 0`、`runner_name: ""` —— **從未被排上 runner**，甚至沒跑到 `actions/checkout`。
- `get_check_run` 的 `output.summary/text/title` 全空 —— 沒有任何測試輸出可看，代表不是斷言失敗。
- `get_job_logs` 直接 404（連 log 檔都沒產生）。

排除本 PR 程式問題的依據：
- `git diff main...origin/claude/inspiring-mccarthy-mgelcq -- .github/workflows/` **無輸出** ——
  `ci.yml` 未被這個 PR 動過。
- `mcp__github__actions_get(get_workflow, ci.yml)` 回 `state: "active"` —— workflow 本身沒被停用。
- 往前查 `ci.yml` 的完整 run 歷史（141 筆），**最近一次成功是 2026-09-01 run #139**（intro-video PR），
  在那之後到今天 3 週內沒有其他 CI 活動，本次是這個週期第一個 PR 就直接卡死。
- 手動 rerun 一次（依 CLAUDE.md routine 的「flake 只重跑一次」原則），行為與前兩次完全相同
  （instant failure、無 runner）—— 不是單次跑者調度抖動，是持續性的。

**結論**：這是 GitHub Actions **runner 排程層級的 infra 問題**，最可能成因是
**Actions usage/spending limit 已耗盡**，或 repo/org 層級的 Actions 執行權限被關閉／限制。
兩者都只能在 GitHub 網頁的 **repo Settings → Actions**（是否被停用）或
**org/帳號 Settings → Billing → Actions usage / spending limit**（額度是否用完、是否設了上限）
檢查與調整——autonomous session 手上的 GitHub MCP 工具沒有這層權限可查或可改。

## 3. 已採取行動

- 在 PR #156 留言記錄完整診斷（run 編號、症狀、排除依據、建議劉老師檢查方向），
  見 https://github.com/dofliu/windMindOM/pull/156#issuecomment-5772450207。
- **沒有**對 PR #156 做任何程式改動——它的本機驗證已由上一個 session 完成且記錄在 PR body，
  問題不在它的程式碼。
- **沒有另開新 PR**：CI 整條飛輪卡住時，開新 PR 只會製造第二個卡在同一個紅燈的待合項，
  對飛輪沒有幫助，且違反「本機 Verify 綠才開 PR」的精神（本機綠但 CI 层級本身跑不動，
  auto-merge 永遠不會觸發）。

## 4. 給劉老師：需要的動作與建議問題

1. 到 GitHub 網頁確認 **repo Settings → Actions → General** 的「Actions permissions」是否仍為
   允許執行（有沒有被意外改成 disabled / restricted）。
2. 到帳號或 org 的 **Settings → Billing and plans → Plans and usage → Actions** 確認
   **included minutes / spending limit** 是否已用完（免費額度用盡且沒設 spending limit 時，
   Actions 會直接靜默失敗，症狀就是本次看到的「runner 從未分配、無 log」）。
3. 確認後若是額度問題：提高 spending limit 或等下個計費週期重置；若是權限被關：重新開啟。
   **不需要改任何程式碼**，這純粹是帳號/repo 設定層級。
4. 修好後，PR #156 應該只要在 GitHub 網頁按 **Re-run all jobs** 就會照正常流程跑過並讓
   auto-merge 接手（前提是 CI 綠），不需要 push 新 commit。

## 5. 下次接手

- 先確認 PR #156 的 CI 是否已恢復（`mcp__github__list_pull_requests` 或直接看 PR 頁面）。
  - 若已合併：正常往下走決策樹（A2 跨情境比較 / PR C / WMOM-20260716-06 等）。
  - 若還是紅燈但這次有真實 log：代表根因不是本文診斷的 infra 問題，改照 log 內容處理。
  - 若還沒人处理 §4 的帳號設定：**不要**在同一個死掉的 CI 前再開新 PR 堆疊，先等或再次留言提醒。

## 6. 哪些部分沒有自動化測試保護

不適用（本 session 未動任何程式碼，純診斷 + 留言 + work-log）。
