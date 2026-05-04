# windMindOM Pitch Deck v0.8.1 — Outline / Source of Truth

> 用途：對齊 deck 故事線；本檔是 source of truth，`pitch_deck_v0.8.1.pptx` 由本檔生成
> 版本：v0.8.1（2026-05-04 改自 v0.5 baseline `pitch_deck_v0.5_baseline.md`）
> 對應產品定位：[`docs/product/PRODUCT_VISION.md`](../product/PRODUCT_VISION.md) v0.8.1
> 主題：**Navy（科技類）** — 由 `pptx-jliu-style` skill 出
> 投影片數：主 deck 10 張 + 附錄 2 張（學術版用）
> 每張規則：標題 + 1 視覺主軸 + 不超過 3 條重點，不塞滿文字

---

## 故事線結構（10 張主 deck）

```
1. 標題          ─ 一句話定位
2. 痛點          ─ 運維廠商現況：Excel + LINE + 紙單
3. 解法          ─ 5 modules 一張圖 + 一句話價值
4. Why now      ─ 第三階段風場 + 出保潮 + ECN 落後
5. Killer       ─ Simulator-first demo（無實場可成立）
6. 競品矩陣      ─ 7 列 + 「沒有任何一家同時涵蓋」
7. 商業模式      ─ 三層套餐 + 預算錨點
8. 第一個客戶    ─ Z72 機型運維廠商
9. Roadmap      ─ 6 個月，一月一 module
10. Ask + 聯絡  ─ 找誰 + 聯絡資訊

附 A1（學術用）─ 兩條獨立論文線
附 A2（學術用）─ 計畫定位
```

---

## Slide 1 — 標題

### 視覺
- 大標：**windMindOM**
- 副標：**離岸風場運維廠商工具**
- Tagline：**「在一個 UI 看到 SCADA、庫存派工、成本、月報、警報手冊查詢」**
- 右下角：版本 v0.8.1 / 2026-05 / DOF Lab

### 講者 talking points（不放投影片）
- 不是 AI platform、不是顧問服務 — 是給運維廠商每天會用的 working tool
- 從 digiWindTurbine（已驗證的物理模擬器 + SCADA 平台）商業化升級而來

---

## Slide 2 — 痛點：運維廠商每天的工作型態

### 視覺
- 左半邊 ICP profile（運維廠商輪廓）
- 右半邊「現況工具組合」三件套

### 內容
- **ICP**：運維廠商（O&M service provider）
  - 同時服務 3-5 家業主、5-10 個風場、3 種 OEM 機型混搭
  - 每月要報「做了什麼維修、花了多少錢、出工幾人天」給業主
- **現況工具**：
  - 庫存散在各風場倉庫
  - 派工靠 LINE 群組
  - 成本估算靠 Excel
  - 業主要 LCOE 報告時還要找會 ECN 的顧問
- **痛點清楚到不行，但沒有一個聚焦的工具**

### 講者 talking points
- 為什麼不賣業主：銷售週期太長（12-24 個月 vs 1-3 個月）、痛點模糊
- 運維廠商：老闆 + 技術主管雙人決策，預算彈性高，「賺錢工具直接買」

---

## Slide 3 — 解法：5 modules 整合在一個 UI

### 視覺（這張是全 deck 的關鍵圖，要花心思）
中央 windMindOM box，向外輻射 5 個 module：

```
                ┌─────────────────┐
                │  windMindOM     │
                │  (5 modules)    │
                └────────┬────────┘
                         │
   ┌──────────┬──────────┼──────────┬──────────┐
   ▼          ▼          ▼          ▼          ▼
┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐
│ 監控  │  │庫存派工│  │成本計算│  │ 報表  │  │警報RAG│
│SCADA │  │工單簽核│  │ECN風格 │  │給業主 │  │給工程師│
└──────┘  └──────┘  └──────┘  └──────┘  └──────┘
```

### 內容
- 一句話：**「取代你現在的 Excel + LINE + 紙單組合」**
- 5 modules 一行字介紹：
  - **監控**：即時 PLC（Z72 Bachmann M1）+ 物理模擬器
  - **庫存派工**：料件主檔 + 工單狀態機 + 多階簽核
  - **成本計算**：可用度 / LCOE / Weather window / 預測 vs 實際
  - **報表**：月報 PDF + 年度預算 + Gantt
  - **警報 RAG**：警報訊息 → 30 秒查到手冊段落 + 過往處置

### 講者 talking points
- 5 modules 每個都不複雜，但**整合在一起的價值**才是 USP
- Basic 套餐就含 RAG（給工程師的甜頭）

---

## Slide 4 — Why now（為什麼是 2026）

### 視覺
- 三條 timeline 上的 bullet（OEM 出包 / 第三階段商轉 / ECN tool 缺 API）

### 內容
- **2024-2025 OEM 連番出包**（SGRE 葉片召回、Vestas 齒輪箱）→ 業主自建監測動力上升 → 運維廠商接更多獨立委外案
- **第三階段風場 2026 起商轉** → 運維廠商需求量大增、機型混搭成常態
- **ECN Tool 5.0 是業界標準但只有 Excel + VBA、沒有 API** → 我們的 Python 移植 + workflow 整合 = 差異化

### 講者 talking points
- 不是 me-too — 是 timing 對 + 技術剛好已經 ready
- 6 個月可以 demo 出第一版，不用 18 個月

---

## Slide 5 — Killer feature: Simulator-first demo

### 視覺
- 左：「現況」客戶 demo 流程（簽 NDA → 給資料 → 我們做 demo → 客戶才看到）
- 右：「windMindOM」流程（直接打開模擬器 → 客戶當場看到 14 台風機運轉）
- 中間箭頭：「Demo 不需要你先給資料」

### 內容
- 物理模擬器（digiWT 既有，已驗證 18/21 quality check）跑出**和真實 SCADA 一模一樣的資料**
- 14 台風機、109 SCADA tags、11 fault scenarios、Bastankhah-Porté-Agel 尾流耦合
- 客戶當場看到實時 dashboard、power curve、告警、跨機台比較
- 切換實機只需要換 adapter（既有 PLC client 已驗證）

### 講者 talking points
- SAP / Bazefield 等競品**都需要客戶先給資料才能 demo**
- 這直接降低 sales 阻力 — 第一次拜訪就能展示
- 同時是研究 / 教學工具（USR 計畫加分）

---

## Slide 6 — 競品矩陣

### 視覺
- 一張 7 列 × 8 行的對照表（淡灰色背景，windMindOM 那行加深色 highlight）

### 內容

|  | SCADA | 庫存 | 派工 | 簽核 | 成本/LCOE | 警報 RAG | 模擬器 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Excel + LINE + 紙單（現況） | – | 散 | 慢 | 紙 | – | – | – |
| Bazefield (NO) | ✓✓ | – | ✓ | – | – | – | – |
| ONYX InSight (UK) | 部分 | – | – | – | – | – | – |
| ECN/TNO Tool 5.0 | – | – | – | – | ✓✓ | – | – |
| SAP PM / IBM Maximo | – | ✓✓ | ✓✓ | ✓✓ | – | – | – |
| Siemens MindSphere | ✓ | ✓ | ✓ | ✓ | – | – | – |
| OEM 自家 dashboard | ✓✓ | – | – | – | – | – | – |
| **windMindOM** | **✓** | **✓✓** | **✓✓** | **✓✓** | **✓✓** | **✓✓** | **✓✓** |

→ **沒有任何一家同時涵蓋這 7 列**

### 講者 talking points
- 重點不是「我們最強」，是「**整合度**沒人達到」
- 特別點兩列：警報 RAG（直接服務工程師）+ 模擬器（demo killer）

---

## Slide 7 — 商業模式：三層套餐 + 預算錨點

### 視覺
- 三層階梯（Basic → Pro → Enterprise），每層底下顯示估價區間
- 底部一句話錨點

### 內容

| 套餐 | 內容 | 估價 |
|---|---|---|
| **OM-Operator Basic** | 監控 + 庫存 + 派工 + 報表 + **基本 RAG** | NT$20-40k/turbine/年 或 NT$2-4M 一次性 + 維護 |
| **OM-Operator Pro** | + Cost engine（ECN-style） | +NT$10-20k/turbine/年 |
| **OM-Operator Enterprise** | + windAILab AI 診斷 + InduSpect 定檢（API 整合） | + revenue share with partners |

**預算錨點**：
> 「月費比少請半個工程師便宜」

**第一筆收入路徑**：
- 3 個月部署 Basic → NT$2-4M 合約
- 6 個月後 upsell Pro → +NT$1-2M
- 第二年 Enterprise（接 AI 診斷） → +NT$1-3M
- 單一客戶 LTV ≈ NT$5-10M（前 2 年）

### 講者 talking points
- Basic 含 RAG 是故意的 — 給工程師甜頭，提升續約率
- 3 家客戶足夠養 4 人團隊兩年

---

## Slide 8 — 第一個客戶：Z72 機型運維廠商

### 視覺
- 上半：四個小卡片（為什麼選 Z72 的 4 個理由）
- 下半：3 個月交付清單

### 內容

**為什麼選 Z72**：
1. **三個 repo 都有 Z72 真實資料**（z72hmi、z72_etech、digiWT 內 simulator）
2. **無 OEM 合作門檻**（Harakosan/Zephyros 已退出市場、Z72 客戶 100% 自運維）
3. **z72hmi 即實機運轉中** — Social proof：「我們已在運維他們同款機」
4. **PLC（Bachmann M1）已驗證** — Z72 監控立刻可上線

**3 個月交付**：
- ✅ Dashboard：即時 SCADA + 告警 + 工單 + 成本檢視
- ✅ 工作流：派工 / 庫存 / 多階簽核全跑通
- ✅ 警報 RAG：現場工程師手機可查（mobile-friendly）
- ✅ 報表：依客戶歷史故障算出的「5 年 O&M 預算 + 排程 Gantt」

### 講者 talking points
- Z72 跑通後 → 透過 CSV adapter 接 Vestas / SGRE 客戶（不需 OEM 配合）
- M6+ 接入 windAILab AI 診斷（已 ready 的 sister product）

---

## Slide 9 — Roadmap：6 個月，一月一 module

### 視覺
- 一條時間軸 6 個月，每月一個方塊

### 內容

```
Month 1 (2026-05) ─ Setup + 接觸 friendly 客戶
Month 2 (2026-06) ─ Cost module（從 ECN 移植）
Month 3 (2026-07) ─ Workflow Part 1（Work Order + Approval）
Month 4 (2026-08) ─ Workflow Part 2（Inventory）+ Reporting
Month 5 (2026-09) ─ Knowledge / RAG + mobile /field/ UI
Month 6 (2026-10) ─ 第一個運維廠商 PoC + 第一筆合約
```

**每月有可 demo 的交付** — 避免到 Month 6 才發現方向錯。

### 講者 talking points
- 不貪多功能；嚴守一月一 module
- Month 1 結束時就能對 friendly 客戶 demo simulator + 講故事
- 6 個月 vs v0.5 估算的 12-18 個月 — 因為砍掉 plugin SDK / Workflow Hub 等過度工程

---

## Slide 10 — Ask + 聯絡

### 視覺
- 三個目標群組（Friendly 客戶 / 國科會 / 投資人）各一段
- 底部聯絡資訊 + QR code（指向 PRODUCT_VISION.md）

### 內容

**找 1-2 家 Z72 機型運維廠商作 friendly pilot**
> 3 個月 NT$2-4M 部署 Basic 套餐，先用 simulator demo，再切實機。
> 失敗風險低，因為 Z72 整套技術鏈已驗證。

**送國科會「能源科技整合型計畫」（2026 下半年）**
> 主題：「離岸風場運維廠商整合決策工具」
> 跨領域組合（電機 + AI + 工管），論文線已 ready。

**投資人 / 共同創辦人**
> 1-2 人團隊 6 個月 ≈ NT$3-5M 開發預算，
> 配合 1-2 家 pilot 客戶 LTV NT$5-10M × 2-3 = NT$10-30M，
> 顧問案先建立 case study，再轉訂閱制。

### 聯絡

**劉瑞弘（Juihung Liu）/ DOF Lab**
moredof@gmail.com
github.com/dofliu / doflab.cc

> 詳細產品文件：`docs/product/PRODUCT_VISION.md`
> 詳細路線圖：`docs/product/ROADMAP.md`

---

## 附錄 A1（學術版加進來）— 兩條獨立論文線

### 視覺
- 兩欄（windMindOM 線 / RAG_Ultimate 線）

### 內容

**A. windMindOM 線（產品自身）**
- "Operator-focused Wind Farm O&M Tool: Integrating SCADA, Inventory, Cost, and RAG-based Knowledge Retrieval"（Applied Energy）
- "Inventory and Crew Schedule Coupled Wind Farm O&M Cost Model: Extending ECN Tool 5.0 with Real-time Workflow Data"

**B. RAG_Ultimate 線（partner research）**
- "Industrial Knowledge-Base RAG Benchmark for Wind Turbine O&M"（IEEE Trans. Industrial Informatics, Phase 3 進行中）

兩條線可彼此引用、共享資料集，但獨立投稿。

---

## 附錄 A2（學術版加進來）— 計畫定位

### 內容
- **國科會「能源科技整合型計畫」**：跨領域（電機 + AI + 工管 + 海洋工程）剛好打中
- **能源署「離岸風電在地化第三階段」**：派工/庫存/簽核 = 在地化軟體可搶位置
- **教育部 USR**：simulator 模式可打包成大學風能實驗室教材

---

## v0.5 → v0.8.1 主要差異（給審視者參考）

| 面向 | v0.5 | v0.8.1 |
|---|---|---|
| ICP | 風場業主 + 國科會雙頻道 | 運維廠商 + 雙 persona（老闆 + 現場工程師） |
| 產品定位 | 整合 platform / 4 + plugin 框架 | 5 modules 整合 monolith / 工作 tool |
| 套餐分層 | OM-Core + AI plugin + Inspection + RAG sister | Basic / Pro / Enterprise 階梯 |
| 競品矩陣 | 8 列（強調 plugin 可組合） | 7 列（強調整合度） |
| 第一筆收入 | NT$3-5M / 3 個月 + LTV NT$8-23M | NT$2-4M / 3 個月 + LTV NT$5-10M |
| Roadmap | 12 個月（M1-M6） | 6 個月（M1-M6） |
| 第一個客戶 | Z72 風場業主 | Z72 機型運維廠商 |
| 學術線 | 主 deck 一張 slide（4 篇論文） | 移到附錄 2 張（2 篇主線 + 1 篇 partner） |
| Killer feature | 4 條 USP 並列 | 1 條獨立 slide（Simulator-first） |

關鍵 narrative shift：v0.5 是「賣 platform 給業主」；v0.8.1 是「賣 working tool 給運維廠商」。

---

## Onepager（A4 一頁 PDF）內容摘要

從主 deck 抽 4 個區塊：

1. **頭部**：windMindOM 大字 + tagline + 一句話定位
2. **5 modules 視覺**（Slide 3 那張圖縮小）
3. **三層套餐**（Slide 7 表格 + 預算錨點）
4. **聯絡 + QR**（指向 PRODUCT_VISION.md github raw）

格式：A4 直式、Navy 主題、留白多、單頁完成。

---

## 待用戶確認的決策點

1. **學術線是否進主 deck？** outline 把它放附錄（不在主 10 張內），給運維廠商看 deck 時更聚焦
2. **預算錨點數字**「比少請半個工程師便宜」是否需要更具體（例：寫成「月費 NT$X 萬，比一個工程師月薪低 50%」）
3. **Slide 3 的 5 modules 視覺**是否走「中央輻射」還是「水平 5 欄」？
4. **Slide 5 Simulator demo** 是否要附上實際 dashboard 截圖（如果你手上有）
5. **Onepager** 配色與主 deck 同 Navy，還是另出一個更輕量的 light 版（給冷郵件附件用）
