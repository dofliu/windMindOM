# windMindOM v0.8.1 Pitch Deck — Outline

> **檔案**: [`pitch_deck_v0.8.1.pptx`](pitch_deck_v0.8.1.pptx)（同資料夾）
> **製作**: 2026-05-03 / Issue WMOM-20260503-04
> **主題**: Navy（深藍科技風）/ 16:9 / 10 頁
> **Build script**: [`tools/pitch_deck/build_v0.8.1.js`](../../tools/pitch_deck/build_v0.8.1.js)（執行 `cd tools/pitch_deck && node build_v0.8.1.js` 重產）
> **Engine**: pptxgenjs ^3.12（依 [`pptx-jliu-style`](https://) skill 規範，策略B 物件最小化）

---

## 設計決策一覽

| 項目 | 決定 | 理由 |
|------|------|------|
| 主題 | Navy 深藍科技風 | 用戶 global CLAUDE.md 預設「Navy 科技類」；對風電工業客戶適合 |
| 結構 | 從零畫，**不沿用 v0.4 任何 slide** | A2 路線（用戶 2026-05-03 決議）；v0.4 ICP 寫業主 / slide 4 寫 4 modules + plugins 與 v0.8.1 衝突 |
| 字體 | Microsoft JhengHei | 中文閱讀效果穩、跨機台可用 |
| 物件最少化 | 是（策略B：fill 直接綁 text） | 客戶手動編輯時點一下選到完整區塊，不需逐層解開 |
| 頁碼 / footer | 全部頁面（封面除外）有 N/10 + footer | 簡報投影時 audience 知道進度 |
| 色帶 / accent | navyDeep + cyan + cyanSoft | 高對比、科技感、easy on eye |

---

## 10 頁逐頁對照

### Slide 1 — Cover
- **主視覺**: 全 navy 背景 + 左側 cyan 縱條 + 右下角 14 點散點（呼應 14 台模擬風機）
- **內容**: windMindOM / 離岸風場運維廠商工具 / Tagline / 版本與作者
- **Source**: PRODUCT_VISION.md §1（「離岸風場運維廠商工具」定位 + DOF Lab）

### Slide 2 — 誰在用：運維廠商，不是業主
- **5 個痛點**:
  1. SCADA 看了沒人用（200+ alarm/天）
  2. 警報靠 LINE 群組
  3. 月報用 Excel 拼
  4. 庫存/派工/簽核分散 3 套系統
  5. 成本沒回寫
- **右側 callout**: Formosa 1/2 (2025–2027) 出保 → 業主轉外包運維 → 運維廠商成為新 ICP
- **Source**: PRODUCT_VISION.md §ICP + §痛點

### Slide 3 — 解法（一頁總覽）
- **3 個關鍵設計決策**:
  1. 5 個 monolithic modules（不是 plugin SDK）
  2. Simulator-first（killer feature）
  3. Z72 機型 reference customer
- **Footnote**: DEC-20260502-06（v0.5→v0.8.1 pivot）
- **Source**: ROADMAP.md TL;DR + decision_log.md DEC-20260502-06

### Slide 4 — 5 Modules 圖
- **5 卡片橫排**: monitoring (M, ✅) / cost ($) / workflow (W) / reporting (R) / knowledge (K)
- **每卡片**: icon + name + one-liner + status badge + detail
- **底部**: 閉環流程「告警 → 工單 → 簽核 → 派工 → 完工 → 庫存扣帳 → cost actual → 月報」
- **Source**: MVP_ARCHITECTURE.md §1.modules + ROADMAP.md M1-M5

### Slide 5 — Killer Feature: Simulator-first
- **左側 3 大 stat 卡**:
  - 104 SCADA tags
  - 14 台模擬風機
  - 1 分鐘 demo
- **右側 3 條應用場景** + 競品對比 callout（Bazefield / SkySpecs / ONYX 都需實場）
- **Source**: PRODUCT_VISION.md §killer feature + digiWT TODO.md（IEC 61400-12-1/2 校正細節）

### Slide 6 — 三層套餐
- **Operator Basic** (NT$30–60k/turbine/年): monitoring + reporting + knowledge
- **Operator Pro** (NT$60–100k/turbine/年): + workflow + cost ← **RECOMMENDED**（cyan 色突顯）
- **Operator Enterprise** (NT$100–180k/turbine/年): + windAILab AI + InduSpect 視覺定檢
- **底部**: 第一筆合約目標 NT$ 2–4M（14 台 × 1 年 Basic 或 Pro）
- **Source**: PRODUCT_VISION.md §商業模式

### Slide 7 — 競品矩陣
- **8 列 × 6 欄表格**: SkySpecs (US) / Bazefield (NO) / ONYX InSight (UK) / SAP PM / windMindOM
- 8 能力列：SCADA / AI+RAG / 派工 / 庫存 / 簽核 / 成本回寫 / Simulator demo / 月報自動化
- windMindOM 欄用 cyanSoft 高亮，Simulator demo 列用 cyan 高亮（killer）
- **底部**: 4 條 USP
- **Source**: PRODUCT_VISION.md §競品

### Slide 8 — 第一個客戶：Z72 機型運維廠商
- **2×2 grid 4 個理由**:
  1. digiWT 物理已驗證（18/21 quality + IEC 校正）
  2. 無 OEM 阻擋（Harakosan/Zephyros 已退出）
  3. Bachmann PLC 已通（z72hmiNew + opc_bachmann）
  4. 3 個 sister repos 吃過 Z72 真實資料
- **底部 timeline**: 2026 Q3 friendly pilot → 2026 Q4 第一筆合約 NT$ 2–4M
- **Source**: CLAUDE.md §15 + ROADMAP.md M6

### Slide 9 — 6 個月 Roadmap
- **6 月份 horizontal timeline**: M1 (2026-05) ~ M6 (2026-10)
- 每月一個 cards：M / 月份 / 章節名 / deliverables / status badge
  - M1 ✅ 進行中（綠）
  - M2-M5 ⏳ 排程中
  - M6 🎯 KPI（橘黃）
- **Source**: ROADMAP.md TL;DR + Month 1-6 章節

### Slide 10 — Ask
- **3 大 ask（give / want 雙欄）**:
  1. Friendly Pilot 1-2 家（我們：simulator + 9 個月免費 PoC + 月報協助 ↔ 您：實場 SCADA + 工程師 + 警報資料）
  2. 業主介紹（我們：介紹費 / marketing / 學界品牌 ↔ 您：介紹外包業主 / 協會 / 競品資料）
  3. 計畫資源（我們：共同申請 / 學術發表 / 學生人力 ↔ 您：共同申請 / 加速 M5/M6 / 跨領域團隊）
- **底部 contact 條**: Dof / DOF Lab / 國立勤益科技大學 / 副教授 劉瑞弘 / moredof@gmail.com / github.com/dofliu / doflab.cc

---

## 後續微調建議（不在 WMOM-04 範圍）

如果用戶 demo 後發現需要：

1. **加圖**: cover 加風場照片、slide 5 加 dashboard 截圖、slide 9 加 timeline 視覺
2. **加 onepager PDF**: 給 cold email 用 — follow-up issue（M1 第二週可做）
3. **加英文版**: 給國際客戶（如 CIP / Ørsted Taiwan）— follow-up issue
4. **加細節版（30 頁）**: 給技術評選 / RFP 用，每 module 1-2 頁細節 — follow-up issue

---

## 重產

```bash
cd tools/pitch_deck
node build_v0.8.1.js
# → 寫到 docs/sales/pitch_deck_v0.8.1.pptx
```

Build script 是 source-of-truth，pptx 是產出物。日後改寫只動 build script，不直接編 pptx
（除非是個別文字微調可以在 PowerPoint 直接改後另存）。

任何重大內容修正應同步更新 build script，避免下次重產時誤差。
