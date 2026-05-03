# 2026-05-03 — WMOM-20260503-04 Pitch deck v0.8.1（從零畫，A2 路線）

> Session 類型：實作（pitch deck 製作）
> Session 長度：中（~1.5 小時 含 build script 撰寫 + npm install + QA）
> 主導：劉老師 + Claude
> 結果：✅ 10 頁 Navy 主題 deck 完成（`docs/sales/pitch_deck_v0.8.1.pptx`）+ outline + build script 永久化

---

## 1. Session 目標

依 [`ISSUES.md`](../../ISSUES.md) `WMOM-20260503-04` 與用戶 A2 決議：
**從零畫 v0.8.1 pitch deck**（不沿用 v0.4 任何 slide），用 `pptx-jliu-style`
skill 出 Navy 主題（科技類），10 頁，繁中為主，技術詞保留英文。

10 頁結構：

| # | Slide | Source 對照 |
|---|-------|----------|
| 1 | Cover — windMindOM v0.8.1 / 離岸風場運維廠商工具 | PRODUCT_VISION.md §1 |
| 2 | ICP 與痛點（運維廠商，不是業主） | PRODUCT_VISION.md §ICP + §痛點 |
| 3 | 解法一頁 | PRODUCT_VISION.md §解法 + ROADMAP.md TL;DR |
| 4 | 5 Modules 圖 | MVP_ARCHITECTURE.md §1.modules |
| 5 | Killer Feature：Simulator-first demo | PRODUCT_VISION.md §killer feature |
| 6 | 三層套餐 Operator Basic / Pro / Enterprise | PRODUCT_VISION.md §商業模式 |
| 7 | 競品矩陣 | PRODUCT_VISION.md §競品 |
| 8 | 第一個客戶：Z72 機型運維廠商 | CLAUDE.md §15 + ROADMAP.md M6 |
| 9 | 6 個月 Roadmap (M1-M6) | ROADMAP.md TL;DR |
| 10 | Ask（friendly pilot / 業主介紹 / 計畫資源） | （新寫） |

## 2. 實際完成

### 2.1 主要工作

- 用 `Skill` tool invoke `anthropic-skills:pptx-jliu-style`（取得 SKILL.md 規範）
- 建 `tools/pitch_deck/` 永久工具夾 + `package.json`（pptxgenjs ^3.12 dep）
- `npm install` 取得 pptxgenjs（19 packages，3s）
- 寫 `tools/pitch_deck/build_v0.8.1.js`（580 行，含 helpers + 10 個 slide builder）
- 一次 build 成功，421 KB pptx 輸出
- python-pptx QA：10 slides 文字內容全部正確、無亂碼
- 寫 `docs/sales/pitch_deck_v0.8.1_outline.md`（設計決策、每頁 source 對照、後續微調建議、重產指令）
- 更新 ISSUES.md / STATUS.yaml / TODO.md（-04 done、-02 範圍縮小、進度提升）

### 2.2 卡住或延後的事

- LibreOffice / soffice 本機未裝 → 無法自動 pptx → PDF 預覽
  - 用戶要在 PowerPoint 開啟手動 visual review
- pptx-jliu-style skill 的 `references/theme-navy.md` + `example_ch6_navy.js` 沒包進 skill bundle（只有 SKILL.md）
  - → 自己依 SKILL.md 高層描述（Navy = 深藍科技風 / 頂部標題列 / 卡片網格）設計色票與排版
  - 結果視覺仍符合 Navy 精神（深 navy + cyan accent + 白底卡片）

### 2.3 重大決策（如有）

無新 DEC（A2 決議延續 DEC-20260502-06 的 pivot 精神）。

戰術選擇：
- **Build script 永久化** vs 一次性產出 — 選永久化。理由：未來 v0.8.2 / v0.9 改版只改 script 重 build，不從 pptx 拉。Build script 進 git，pptx 也進 git（小 421 KB）
- **採 npm 在 `tools/pitch_deck/` 隔離** vs 全局裝 vs frontend/ 共用 — 選隔離。理由：不污染 frontend deps、不影響 production runtime

## 3. 產出清單

### 新增檔案

- `docs/sales/pitch_deck_v0.8.1.pptx`（421 KB，10 頁 Navy 主題）
- `docs/sales/pitch_deck_v0.8.1_outline.md`（設計決策 + 每頁 source 對照 + 後續微調建議 + 重產指令）
- `tools/pitch_deck/package.json`（pptxgenjs ^3.12 dep）
- `tools/pitch_deck/build_v0.8.1.js`（pptxgenjs build script，580 行）
- `tools/pitch_deck/.gitignore` 機制：`tools/pitch_deck/node_modules/` 加進 root `.gitignore`

### 修改檔案

- `ISSUES.md`：WMOM-20260503-02 範圍縮小 + WMOM-20260503-04 → done + completion summary
- `STATUS.yaml`：progress 14 → 22；M1 progress 35 → 60；issue_stats done 2→3 / in_progress 1→0
- `TODO.md`：第一週清單 -04 打勾 + 重排第二三週順序
- `.gitignore`：補 `tools/pitch_deck/node_modules/`（順手修了一個既有的換行 bug）

### 動了狀態的 issue

- WMOM-20260503-04: in_progress → done
- WMOM-20260503-02: open → open（範圍縮小說明寫進 ISSUES.md，priority 從 high 降為 medium）

### 寫進 decision_log 的決策

無新 DEC。

## 4. 下次怎麼接手

M1 第一週主軸基本打完。剩 -02（templates 盤點）+ -05（friendly 客戶名單）。

### 4.1 主線：認領 WMOM-20260503-02（範圍縮小版）

- 0.5 天工作量：盤點 `templates/` + `docs/claude-code-templates/`
- 缺什麼補什麼，多餘的不動
- 寫一張清單到該 issue 或新 work-log

### 4.2 備線：認領 WMOM-20260503-05

- 整理 friendly 廠商名單（學界人脈、Bachmann Taiwan 客戶、台電/中能/CIP 分包商）
- 不需要 commit；目的是收集真實 pain points 餵 M3-M5 設計

### 4.3 visual review pitch deck

- 用戶請開 `docs/sales/pitch_deck_v0.8.1.pptx` in PowerPoint
- 視覺檢查：
  - Navy 色帶是否乾淨
  - 字體 Microsoft JhengHei 顯示正確（無 fallback 到 Arial / 細明體）
  - 表格 cell 是否對齊（slide 7 競品矩陣）
  - 卡片排版是否擠（slide 6 三層套餐）
- 任何修正 → 改 `tools/pitch_deck/build_v0.8.1.js` 再 re-run，**不要直接編 pptx**
（除非是極小的字句微調可在 PowerPoint 改後另存）

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 與用戶討論（A1/A2/A3 + ICP/Roadmap pivot 釐清） | 15% |
| 讀 SKILL.md + 規劃 10 頁結構 + Navy 色票設計 | 20% |
| 寫 build_v0.8.1.js（10 個 slide builder + helpers） | 50% |
| QA（python-pptx 文字提取 + 嘗試 LibreOffice） | 10% |
| 寫 outline.md + 更新 tracking + work-log | 5% |

## 6. 學到的事

- **pptx-jliu-style skill 的 references/ 沒打包進 bundle** — 只有 SKILL.md。需要自己依高層 guidance 設計細節。Skill 的價值是「設計哲學 + 策略B 物件最小化」這些 meta 層，不是直接給色票
- **Build script 永久化是巨大勝利** — 未來改版只動 JS，不需手動投影片。Source-of-truth 是 build script，pptx 是產出物
- **pptxgenjs `addText` 的 fill 屬性** = 策略B 核心。一個 text 物件搞定背景色 + 文字 + 邊框，使用者點一下就選到完整區塊
- **python-pptx 是純 Python 的好 QA 工具** — 不需 LibreOffice / Office 安裝，文字提取 + 結構檢查就能 catch 90% 排版問題
- **客戶端視覺確認終究要人工做** — 沒有 LibreOffice 自動 PDF 也 OK，PowerPoint 直接開最快

## 7. Open questions（park）

- onepager PDF 給 cold email 用 — follow-up issue（可開 WMOM-20260503-06）
- 英文版 deck 給國際客戶 — follow-up issue
- 細節版（30 頁）給技術評選 / RFP 用 — follow-up issue
- pitch deck 內視覺資產（風機照片、dashboard 截圖）何時補 — 等實際 pilot 客戶談了之後再決定要不要客製
