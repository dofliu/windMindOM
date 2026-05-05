# windMindOM Architecture Diagrams

> 給人「一張圖看完整系統」的入口。所有圖用 **Mermaid**（純文字 + GitHub / VSCode 直接 render）。

## 文件清單

| 檔案 | 內容 | 何時看 |
|------|------|--------|
| [windMindOM-architecture.md](windMindOM-architecture.md) | **主文件** — 系統架構全貌（一張圖）+ 7 張補充細節圖 | 第一次接觸專案 / 客戶 demo / partner 對接 |

## 主文件涵蓋的 8 章

1. **一張圖看全貌** — Users / Frontend / API / 5 modules / Data / External 的全層 graph
2. **模組內部分層** — domain → repository → schemas → routers 4 層 pattern
3. **Work Order 狀態機** — 7 status / 9 transition + signoff 整合點
4. **Approval 4 階 signoff chain** — 對應 etech user group 100/300/500/666
5. **與 7 個來源 repo 的關係** — 哪些 fork、哪些介接、哪些不動
6. **Storage 結構** — per-farm DB schema 雙 source（monitoring raw sqlite3 + workflow SQLAlchemy）並存
7. **6-month roadmap timeline** — Gantt 圖 M1-M6
8. **一句話總結** — windMindOM 是什麼

## 為什麼選 Mermaid

- 純文字、版本控制友善（git diff 看得到圖的演進）
- GitHub / GitLab / VSCode / Obsidian / Notion 都能 render
- 不需任何繪圖工具或外部 dependency
- 改一個 connection 不用重畫整張圖

## 其他選項（已評估、未採用）

| 工具 | 為何沒選 |
|------|---------|
| draw.io / diagrams.net | 圖形編輯好但 source 是 XML，git diff 不友善 |
| PlantUML | 文字也好，但 Mermaid 在 GitHub render 範圍更廣 |
| C4 model 工具（Structurizr 等） | 對 5-module monolith 過度工程；C4 適合微服務或大型企業系統 |
| 截圖貼 PNG | 改一次要重畫整張，文件容易過時 |
