# GEMINI.md — windMindOM

> 給 Gemini CLI 的入口檔。
> **本專案的 canonical 開發守則在 [`CLAUDE.md`](CLAUDE.md)** —— 開工前請先讀它（與其他 AI 工具共用同一份守則，避免分歧）。

## 專案一句話

**windMindOM（風心智運維平台）** —— 離岸風場運維廠商工具：監控 + 庫存派工 + 成本計算 + 報表 + 警報手冊查詢。
Monolithic 5 modules（monitoring / cost / workflow / reporting / knowledge），從 digiWindTurbine（物理模擬器 + SCADA 平台）商業化升級而來。

## 必讀順序

1. [`CLAUDE.md`](CLAUDE.md) — 開發守則、repo 角色、commit 規範
2. [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md) — 產品定位、ICP、5 大功能
3. [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md) + [`STATUS.yaml`](STATUS.yaml) + [`ISSUES.md`](ISSUES.md) — 進度與工作清單

## 開發環境

```bash
pip install -r requirements.txt -r requirements-dev.txt && python run.py   # backend :8100
cd frontend && npm install && npm run dev                                  # frontend :3100
python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/   # 570 passed / 1 xfailed
```

## 守則摘要（細節見 CLAUDE.md）

- 不直接 commit 到 `main`；建分支走 PR；commit `type(#WMOM-{N}): 描述`
- Python 型別標註必加、繁中說明；對使用者輸出繁體中文，技術術語保留英文
- 每個 module 都要有 test；編輯前先讀檔
