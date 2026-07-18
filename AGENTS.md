# AGENTS.md — windMindOM

> 給 AI coding agent（Codex / Cursor / Jules / Copilot 等）的入口檔。
> **本專案的 canonical 開發守則在 [`CLAUDE.md`](CLAUDE.md)** —— 任何 agent 開工前請先讀它。
> 本檔只放各 agent 工具共通的最精簡 orientation，避免與 CLAUDE.md 重複。

## 一句話

**離岸風場運維廠商工具**：監控 + 庫存派工 + 成本計算 + 報表 + 警報手冊查詢 + 權限驗證。
Monolithic 6 modules（monitoring / cost / workflow / reporting / knowledge / auth），從 digiWindTurbine 商業化升級而來。

## 必讀順序

1. [`CLAUDE.md`](CLAUDE.md) — 開發守則、repo 角色、commit 規範、不要做的事
2. [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md) — 產品定位、ICP、5 大功能
3. [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md) + [`STATUS.yaml`](STATUS.yaml) + [`ISSUES.md`](ISSUES.md) — 現在進到哪、找事做

## 最低限度規範（細節見 CLAUDE.md §7-8）

- **分支**：不直接 commit 到 `main`；建 feature 分支再走 PR
- **Commit**：`type(#WMOM-{N}): 描述`（type ∈ feat/fix/docs/refactor/chore/test）
- **Python**：型別標註必加、docstring Google style、繁中說明、不用 `Any`
- **Frontend**：走 UI 元件庫、不寫 hex；對使用者輸出繁體中文，技術術語保留英文
- **Test-first**：每個 module 都要有 test；編輯前先讀檔

## 開發環境

```bash
pip install -r requirements.txt -r requirements-dev.txt && python run.py   # backend :8100
cd frontend && npm install && npm run dev                                  # frontend :3100
# 測試執行指令 (含 6 模組 + e2e 測試，基準約 998 案)
python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ \
                  modules/knowledge/tests/ modules/monitoring/tests/ modules/auth/tests/ \
                  tests/ -q
```
