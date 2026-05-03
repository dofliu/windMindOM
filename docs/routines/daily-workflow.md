# Daily Workflow Routine — windMindOM

> 版本：v1.1（2026-05-03 — 修正 windMindOM 路徑與 issue 前綴）
> 適用：Claude Code（也可在其他 LLM workflow 工具沿用）
> 哲學：**一日一項重要工作 → 完整跑完一個閉環 → code review → 收尾**
> 不貪多。完成一個 issue 比起跑半個 5 個 issue 有價值得多。

---

## TL;DR — 每天 8 個 phase

```
1. Preflight       讀 STATUS / handoff / ISSUES / ROADMAP（5 分鐘）
2. Claim           認領一個 open issue → in_progress
3. Branch + Log    開分支 + 開 work-log
4. Implement       寫 code（含 unit test）
5. Verify          跑 test、lint、type check
6. Review          self-review checklist + subagent code-review
7. Wrap-up         更新 STATUS / ISSUES / handoff / work-log
8. Commit & Push   commit (auto) → push (人工確認)
```

---

## Phase 1 — Preflight（5 分鐘）

開工前必讀：

```
1. STATUS.yaml             ← 5 分鐘看現況、milestone 進度
2. docs/product/ROADMAP.md ← 知道現在進到哪個 month / module
3. ISSUES.md               ← 找 open / in_progress 的 issue
4. (如有) docs/session_handoff.md ← 上一個 session 留下什麼
```

判斷：
- 有沒有 in_progress 但未完成的 issue？（如有，先收尾）
- 有沒有 blocker？

## Phase 2 — Claim（10 分鐘）

從 ISSUES.md 挑一個 issue。優先序：

1. status=in_progress 但未完成（先收尾）
2. priority=critical 且 blocking 其他
3. 該月 ROADMAP 的下一個 logical step

挑好後：

```
- ISSUES.md 標 in_progress + Owner: Claude (this session)
- 統計表 open -1, in_progress +1
```

**今日任務原則**：**一日一個 critical / high issue。** 若 issue 估算 > 3 工作天，拆 sub-issue 再認領。

## Phase 3 — Branch + Work-log（5 分鐘）

```bash
git checkout main
git pull
git checkout -b claude/issue-{N}-YYYY-MM-DD
```

複製 `templates/work-log-template.md` 為 `work-logs/YYYY-MM/YYYY-MM-DD-{slug}.md`。

寫 §1 Session 目標（從 issue description 摘要）。

## Phase 4 — Implement（核心時間，1-6 小時）

依 issue 寫程式。守則：

### 4.1 Test-first
寫小 test → fail → 寫 production code → pass。

### 4.2 一邊寫一邊跑 test
每 50-100 行跑一次。

### 4.3 工程規範（CLAUDE.md §7）
型別標註、Google docstring、繁中說明、不用 Any、snake_case / PascalCase。

### 4.4 出現的疑問
寫進 work-log §7 Open questions（park）；不打斷實作。

## Phase 5 — Verify（10-30 分鐘）

```bash
pytest tests/ -v
ruff check .
ruff format --check .
# M2+ 開啟 mypy
```

**Done criteria**：
- ✅ 所有 test pass
- ✅ ruff 0 error
- ✅ 新增程式有對應 test

如果 fail 不是這 issue 的問題：寫進 work-log §3 卡住或延後的事，**不在這 issue 修**。

## Phase 6 — Review（30 分鐘）

### 6.1 Self-review checklist

```
[ ] 函式命名清楚
[ ] Docstring 完整（args、returns、raises）
[ ] Type hints 完整且正確
[ ] 邊界條件有處理
[ ] 錯誤處理有意義
[ ] Test 涵蓋 happy + error + edge
[ ] 無 dead code / debug print / 未清 TODO
[ ] CHANGELOG / decision_log 該更新有更新
[ ] 沒違反 CLAUDE.md §12「不要做的事」
```

### 6.2 Subagent code review（**強制**）

Claude Code 用法：

```
我已完成 WMOM-{N} 的實作。
請 invoke code-reviewer subagent 對以下檔案做 review：
- modules/cost/aggregator.py（新增）
- tests/cost/test_aggregator.py（新增）

重點關注：
- ECN 計算結果是否與原 K13 demo 對得上
- async / lifecycle 處理
- 例外處理依 hierarchy
```

### 6.3 處理 review 反饋

- **Must-fix**：當下修
- **Should-fix**：當下修或開 new issue
- **Nice-to-have**：寫進 work-log §6

修完後**重跑 Phase 5**。

## Phase 7 — Wrap-up（15 分鐘）

更新四份追蹤檔案：

### 7.1 ISSUES.md
- in_progress → done + Resolution 段
- 統計表 in_progress -1, done +1
- unblock 其他 issue
- 移到「過往已完成」區

### 7.2 STATUS.yaml
```yaml
milestones:
  M{X}_xxx:
    deliverables:
      - "[done] 這個 issue 的 deliverable"
    completion: 更新百分比
current_focus:
  this_session: 一句話
  next_session: 建議
```

### 7.3 work-log
填完整 §3 - §7。

### 7.4 docs/session_handoff.md（如有）
更新「最新 cursor」+ Session log 表格。

## Phase 8 — Commit & Push

### 8.1 Auto commit

```bash
git add .
git commit -m "type(#WMOM-{N}): 一句話描述

詳細說明：
- bullet 1
- bullet 2

Tests: X pass / 0 fail
"
```

Type ∈ feat / fix / docs / refactor / chore / test。

### 8.2 Push（**人工確認**）

不自動 push。給用戶看 commit message 後說：

> 已 commit。請 review 後手動執行 `git push origin claude/issue-{N}-YYYY-MM-DD`。

或單 dev 階段直接 `git push origin main`。

### 8.3 切回 main

```bash
git checkout main
git pull origin main
```

---

## 失敗恢復守則

session 中斷時：

```
1. 不要 reset / revert
2. 開新 session：
   a. 讀 ISSUES.md 找 in_progress
   b. 讀對應 work-log
   c. git status / git diff 看實際改動
   d. 從 work-log §3.2 往下接
3. 把 work-log 拆「上一段 / 本段」
4. 完成後正常走 Phase 5-8
```

---

## 常見場景

### A. 今天 issue 比預期大
- 30 分鐘 spike → 發現 > 3 天 → 拆 sub-issue → 本日只完成 sub-issue {a}

### B. 發現現存 issue 可順手解
- 不要順手做。寫 work-log §7 → 明天認領

### C. Subagent 找到大量問題
- 修 must-fix + should-fix。如果修完 > 50% 改動：拆 PR

### D. 重大架構決策浮現
- 立刻停實作 → 寫 DEC → 視需要拆 sub-issue

---

## Slash Commands

| 指令 | phase | 作用 |
|------|------|------|
| `/daily-start` | 1-3 | preflight + 提示 claim issue + 開分支與 work-log |
| `/claim-issue {N}` | 2 | 認領指定 issue |
| `/review` | 6 | invoke code-reviewer subagent |
| `/daily-wrapup` | 7-8 | 收尾 + auto commit + 提示 push |

詳見 `docs/claude-code-templates/`。

---

## 例外原則：何時可以**不**走完整 routine

| 情境 | 簡化 |
|------|------|
| 純文件 typo / 補 docstring | Phase 4 → Phase 8（跳 test/review） |
| 純設定檔 | Phase 4 → Phase 5（lint）→ Phase 8 |
| 學習 / 探索 spike | Phase 4 → Phase 7（記錄），不 commit |
| 純 review 別人 PR | 只做 Phase 6 |

碰到產品邏輯（modules/）一律走完整 routine。

---

## Routine 改進機制

每月最後一個 session：

1. Review 過去一月 work-log
2. 找出 bottleneck，改進本檔
3. 開 DEC 紀錄改進

預期 v1.x 大改點：
- M2 後可能加「跨 module e2e 測試」phase
- M3 z72_etech 取設計後可能加「設計取材」routine 章節
- M5 客戶 PoC 後可能加「客戶資料安全」checklist
- M5 後若有合作開發者進來，加「PR review」phase
