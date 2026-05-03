---
description: 開啟今日工作流程（Preflight + Claim + Branch + Work-log）
---

執行 `docs/routines/daily-workflow.md` 的 Phase 1-3。

## 1. Preflight（5 分鐘）

請依序讀取並摘要給我：

1. `STATUS.yaml` — 現況、milestone 進度、blockers
2. `docs/product/ROADMAP.md` — 知道現在進到哪個 month / module
3. `ISSUES.md` — open / in_progress 的 issue 清單
4. （如有）`docs/session_handoff.md` — 上次 session 留下什麼

判斷：
- 有沒有 in_progress 但未完成的 issue？（如有，先收尾）
- 有沒有 blocker？

## 2. 推薦 issue（候選 2-3 個）

依下列優先序從 ISSUES.md 挑 2-3 個候選：

1. status=in_progress 但未完成
2. priority=critical 且 blocking 其他
3. ROADMAP 該月的下一個 logical step

對每個候選列出：
- WMOM-{ID}
- 一句話 description
- estimate / dependencies
- 為什麼它是好候選

然後問我要選哪一個。

## 3. 認領 + 開工

我選定後，幫我：

1. ISSUES.md 該 issue 從 open → in_progress
2. 加 Owner: Claude (this session YYYY-MM-DD-{slug})
3. 統計表 open -1, in_progress +1
4. `git checkout main && git pull && git checkout -b claude/issue-{N}-YYYY-MM-DD`
5. 從 `templates/work-log-template.md` 複製為 `work-logs/YYYY-MM/YYYY-MM-DD-{slug}.md`
6. 在 work-log §1 寫 Session 目標 + 計畫的實作切點

完成後告訴我：
- 開好的分支名稱
- 開好的 work-log 路徑
- 接下來進入 Phase 4（Implement）

## 注意

- 整個流程不超過 15 分鐘
- 不要主動寫 production code，等我說「OK 開始實作」再進 Phase 4
