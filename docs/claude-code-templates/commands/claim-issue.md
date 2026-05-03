---
description: 認領一個指定 ID 的 issue（用 /claim-issue WMOM-20260503-01）
---

把 ISSUES.md 內 ID 為 $ARGUMENTS 的 issue：

1. status: open → in_progress
2. 加 Owner: Claude (session YYYY-MM-DD-{slug})
3. 加 Started: YYYY-MM-DD HH:MM
4. 統計表 open -1, in_progress +1

接著：

5. `git checkout main && git pull`
6. `git checkout -b claude/issue-{N}-YYYY-MM-DD`
7. 從 `templates/work-log-template.md` 複製為 `work-logs/YYYY-MM/YYYY-MM-DD-{slug}.md`
8. 在 work-log §1 寫入：
   - Session 目標（從 issue description 摘要）
   - 預計的實作切點

最後告訴我：
- 認領的 issue 標題
- 開好的分支名稱
- work-log 路徑
- 預計第一步要做什麼

如果 $ARGUMENTS 為空或找不到 issue，列出當下所有 open issue 讓我選。
