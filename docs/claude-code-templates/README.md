# Claude Code Templates

> 這個資料夾的檔案是 **要複製到 `.claude/` 的範本**。
> Cowork 對 `.claude/` 有寫入保護（類似 `.git/`），故先放本目錄為 source of truth；
> Claude Code 內執行下方一行 PowerShell 一次到位。

## 安裝（在 Windows PowerShell）

```powershell
cd D:\Project_CodingSimulation\researchTopic\windMindOM
New-Item -ItemType Directory -Force -Path .claude\commands, .claude\agents | Out-Null
Copy-Item docs\claude-code-templates\commands\*.md .claude\commands\ -Force
Copy-Item docs\claude-code-templates\agents\*.md .claude\agents\ -Force
git add .claude
git commit -m "chore: install Claude Code commands & agents"
git push
```

之後可在 Claude Code 用：
- `/daily-start` — 開啟今日工作流程
- `/claim-issue {N}` — 認領一個 issue
- `/review` — 對 git diff 跑 code review
- `/daily-wrapup` — 收尾今日工作

Sub-agent：
- `code-reviewer` — Python async + 風電領域 + FastAPI 專長

## 為什麼用範本而不直接放 .claude/

1. **Cowork 寫入保護**：本 session 在 Cowork 內，無法直接寫 `.claude/`
2. **可審視**：用戶可以 review 範本內容後再 copy
3. **版本控制清楚**：範本獨立 commit，未來改進時 diff 一目了然

範本與 `.claude/` 內容應同步；改其中一個記得同步另一個。
