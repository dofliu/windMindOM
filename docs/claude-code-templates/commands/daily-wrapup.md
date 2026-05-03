---
description: 收尾今日工作（更新追蹤檔案 + auto commit + 提示手動 push）
---

執行 `docs/routines/daily-workflow.md` 的 Phase 7-8。

## Phase 7 — Wrap-up

### 7.1 更新 ISSUES.md

對本 session 的 in_progress issue：

1. 確認 deliverable 真的都完成（`git diff main..HEAD --stat` 對照 issue Deliverable）
2. status: in_progress → done + Resolution 段（2-3 行說明 + test 結果）
3. 統計表 in_progress -1, done +1
4. 移到「過往已完成」區
5. unblock 其他 issue

### 7.2 更新 STATUS.yaml

```yaml
milestones:
  M{X}_xxx:
    deliverables:
      - "[done] 這個 issue 的 deliverable"
    completion: 更新百分比

current_focus:
  this_session: 今天做了什麼（一句話）
  next_session: 建議下次做什麼（具體 issue ID）
```

### 7.3 完成 work-log

填完整 §3 - §7。

### 7.4 更新 docs/session_handoff.md（如有）

「最新 cursor」+ Session log 表格。

## Phase 8 — Commit

```bash
git status
git diff --stat   # 用戶 sanity check
git add .
git commit -m "type(#WMOM-{N}): 一句話描述

詳細說明：
- bullet 1
- bullet 2

Tests: X pass / 0 fail
Closes #WMOM-{N}
"
```

## Phase 9 — Push（**人工確認**）

不自動 push。給用戶看 commit message 後說：

> 已 commit。請 review 後手動執行：
>
> ```powershell
> git push origin claude/issue-{N}-YYYY-MM-DD
> ```
>
> 或單 dev 階段直接 push 到 main：
>
> ```powershell
> git checkout main
> git merge --no-ff claude/issue-{N}-YYYY-MM-DD
> git push origin main
> ```

## 結尾

最後給一段 Daily Summary：

```
📅 YYYY-MM-DD Daily Summary

Issue:       WMOM-{N} ({status})
Branch:      claude/issue-{N}-YYYY-MM-DD
Work-log:    work-logs/YYYY-MM/YYYY-MM-DD-{slug}.md
Tests:       X pass / 0 fail (X new)
LoC changed: +XXX / -YY across N files
Decision:    DEC-{ID} (if any)
Next:        WMOM-{下一個} 建議

Action required: git push（review commit message 後手動）
```
