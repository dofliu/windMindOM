# windMindOM 產品願景 v0.8.1

> 版本：v0.8.1（2026-05-02）— 取代 v0.5 之前所有版本
> 對應決策：[`decision_log.md`](decision_log.md) DEC-20260502-06
> 相關文件：[`MVP_ARCHITECTURE.md`](MVP_ARCHITECTURE.md) / [`ROADMAP.md`](ROADMAP.md)

---

## TL;DR

**「給離岸風場運維廠商：在一個 UI 看到 SCADA 監控、庫存派工、成本計算、警報手冊查詢——取代你現在的 Excel + LINE + 紙單組合。」**

- **產品**：windMindOM（從 digiWindTurbine 商業化升級）
- **ICP**：運維廠商（O&M service provider），同時服務管理層與**現場工程師**
- **5 大功能**：監控、庫存派工、成本（ECN-style）、報表、RAG 知識檢索
- **沒實場也能 demo**：物理模擬器產生擬真 SCADA 資料
- **外部介接**（不整進產品本體）：windAILab / RAG_Ultimate / InduSpect 走 API + research artifact
- **第一個客戶**：6 個月後（2026-Q4）一個 Z72 機型的運維廠商 PoC

---

## 1. 為什麼是現在

### 1.1 運維廠商的痛點（這是 ICP）

運維廠商（O&M service provider）的日常工作型態：

- 同時為 3-5 家業主服務
- 5-10 個風場、3 種 OEM 機型混搭
- 每月要報「這個月做了什麼維修、花了多少錢、出工幾人天」給業主
- 庫存散在各風場倉庫
- 派工靠 LINE 群組
- 成本估算靠 Excel
- 業主要 LCOE 報告時還要找會 ECN 的顧問

他們的競品是「Excel + LINE + 紙單」組合，**痛點清楚到不行，但沒有一個聚焦的工具**。

### 1.2 為什麼不是賣給業主

| | 風場業主 | 運維廠商 |
|---|---|---|
| 規模 | 大企業（年營收 NT$10B+） | 中小企業（NT$50-500M） |
| 銷售週期 | 12-24 個月 | **1-3 個月** |
| 決策層級 | CIO + 採購 + 技術 + 法務 | 老闆 + 技術主管 |
| 痛點明確度 | 模糊（「我想要 platform」） | **超明確** |
| 預算彈性 | 嚴格 | **較有彈性（賺錢工具直接買）** |
| 競品 | SAP PM / Bazefield（昂貴強競） | **Excel + LINE + 紙單**（極弱） |
| 對 AI 的需求 | 大、但要先驗證 | 中、但要立刻有用 |

對 1-2 人新創團隊，**運維廠商是更可實現的 ICP**。

### 1.3 國際/國內背景（為什麼是 2026）

- 2024-2025 國際 OEM 連番出包（SGRE 葉片召回、Vestas 齒輪箱集中故障）→ 業主自建監測動力上升 → 運維廠商開始接更多獨立委外案
- 第三階段風場 2026 起商轉 → 運維廠商需求量大增
- ECN Tool 5.0 是業界標準但只有 Excel + VBA，沒有 API → 我們的 Python 移植成為差異化

---

## 2. 產品定位

### 2.1 一句話

**「給運維廠商：把 SCADA 監控、庫存派工、成本計算、警報查手冊，整合在一個 UI——並且不需要你先給資料就能看 demo。」**

### 2.2 兩種 user persona

| Persona | 用法 | 看什麼 | 不續約原因 |
|---|---|---|---|
| 老闆 / 主管 | Web admin dashboard | ROI、報表能不能交差給業主 | 「沒幫我省錢」 |
| **現場工程師** | **Mobile-friendly view** | **「警報跳出來，我能不能 30 秒找到答案」** | **「比 LINE 群組問師傅還慢」** |

**現場工程師是高頻 user，是 PMF 的關鍵**。如果他們不愛用，老闆無論多買單，半年後一定 renewal 失敗。

### 2.3 5 大核心功能

```
windMindOM
├── 1. 監控（SCADA）
│   ├── 即時 PLC（Z72 連線：Bachmann M1）
│   └── 物理模擬器（無實場時 demo / 研究用）
├── 2. 庫存管理 + 維修派工
│   ├── 料件主檔 + 出入庫雙寫
│   ├── 工單 CRUD + 狀態機
│   └── 多階簽核
├── 3. 成本計算（ECN-style）
│   ├── 季度可用度 / LCOE
│   ├── Weather window 規劃
│   └── 預測 vs 實際對比
├── 4. 報表生成（給業主回報用）
│   ├── 月報（自動產出 PDF）
│   ├── 年度 O&M 預算
│   └── 排程 Gantt
└── 5. 知識檢索 RAG（給現場工程師）
    ├── 警報訊息 → 30 秒查到手冊段落 + 過往處置
    ├── OEM 手冊 + SOP + 過往警報處置 → vector store
    └── 內建（用 RAG_Ultimate 提供的策略檔 + 預計算向量檔）
```

### 2.4 不做什麼（避免陷阱）

- **不做 AI 故障診斷**（windAILab 是另一公司業務，透過 API 介接即可）
- **不做 AI 視覺定檢**（InduSpect 是另一獨立產品）
- **不做 plugin SDK**（過度工程，1-2 人團隊無法維護）
- **不做 multi-tenant SaaS**（M5 之後客戶量起來再考慮）
- **不做控制系統**（保持 read-only / planning，不發送降載/停機指令）
- **不做 Z72 以外機型的 PLC adapter**（M5 之後客戶有需求才做）

---

## 3. 競品矩陣

|  | SCADA 即時 | 庫存 | 派工 | 簽核 | 成本/LCOE | 警報 RAG | 模擬器 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Excel + LINE + 紙單（運維廠商現況） | – | 散 | 慢 | 紙 | – | – | – |
| Bazefield (NO) | ✓✓ | – | ✓ | – | – | – | – |
| ONYX InSight (UK) | 部分 | – | – | – | – | – | – |
| ECN/TNO Tool 5.0 | – | – | – | – | ✓✓ | – | – |
| SAP PM / IBM Maximo | – | ✓✓ | ✓✓ | ✓✓ | – | – | – |
| Siemens MindSphere | ✓ | ✓ ERP | ✓ ERP | ✓ | – | – | – |
| OEM 自家 dashboard | ✓✓ 單品牌 | – | – | – | – | – | – |
| **windMindOM** | **✓** | **✓✓** | **✓✓** | **✓✓** | **✓✓** | **✓✓** | **✓✓** |

**沒有任何一家同時涵蓋這 7 列。**

特別是「警報 RAG」與「模擬器」兩列：
- **警報 RAG**：直接服務現場工程師，最高頻 user touch point。國際競品都把 RAG 視為 nice-to-have、放在「企業搜索」layer，沒人做警報直接觸發。
- **模擬器**：「客戶看 demo 不必先簽 NDA 給資料」是 sales killer feature。SAP / Bazefield 等都需要客戶先給資料才能做意義 demo。

---

## 4. 商業模式

### 4.1 三層套餐

| 套餐 | 內容 | 估價 |
|---|---|---|
| **OM-Operator Basic** | 監控 + 庫存 + 派工 + 報表 + **基本 RAG**（含內建） | NT$20-40k/turbine/年 或 NT$2-4M 一次性 + 維護 |
| **OM-Operator Pro** | + Cost engine（ECN-style） | +NT$10-20k/turbine/年 |
| **OM-Operator Enterprise** | + windAILab AI 診斷 + InduSpect 定檢（API 整合） | +revenue share with partners |

**Basic 套餐就含 RAG**——這是給工程師的甜頭，「進來就有」，提升 PMF。

### 4.2 對運維廠商的銷售話術

> 「你現在用 Excel + LINE + 紙單管理 5 個風場、20 個工程師、每月給業主一份報告。
> 我們把這些變成一個 UI。月費比你少請半個工程師還便宜。
> 而且警報跳出來時，現場工程師 30 秒看到手冊答案，不用打電話問師傅。」

「**月費比少請半個工程師便宜**」是預算的關鍵錨點。

### 4.3 第一筆收入的最短路徑

**3 個月部署 → NT$2-4M 合約**

- Month 1-3 開發 + 接洽 friendly 客戶
- Month 4-6 部署 + 培訓 + 第一個月運轉
- Month 7 第一筆合約

**單一客戶 LTV ≈ NT$5-10M（前 2 年）**——足夠養 1-2 人團隊。

3 家客戶就足以養 4 人團隊兩年。

---

## 5. 第一個客戶：Z72 機型運維廠商

### 5.1 為什麼選 Z72 機型

1. **三個 repo 都有 Z72 真實資料**（z72hmi、z72_SCADA_etech、digiWT 內 simulator）
2. **無 OEM 合作門檻**（Harakosan/Zephyros 已退出市場、Z72 客戶 100% 自運維）
3. **z72hmi 即實機運轉中** — Social proof：「我們已在運維他們同款機」
4. **PLC（Bachmann M1）已驗證** — Z72 監控立刻可上線

### 5.2 第一階段交付（3 個月）

✅ Dashboard：即時 SCADA + 告警 + 工單 + 成本檢視
✅ 工作流：派工 / 庫存 / 多階簽核全跑通
✅ 警報 RAG：現場工程師手機可查（mobile-friendly）
✅ 報表：依客戶歷史故障算出的「5 年 O&M 預算 + 排程 Gantt」
✅ 升級選項：未來可加 windAILab AI 診斷 / InduSpect 定檢

---

## 6. 學術價值（給國科會 / 計畫審查）

兩條獨立論文線：

### 6.1 windMindOM 線（產品自身）

- **"Operator-focused Wind Farm O&M Tool: Integrating SCADA, Inventory, Cost, and RAG-based Knowledge Retrieval"**
  - Applied Energy / Energy
  - 重點：跨領域（SCADA + workflow + cost + AI knowledge）整合 case study

- **"Inventory and Crew Schedule Coupled Wind Farm O&M Cost Model: Extending ECN Tool 5.0 with Real-time Workflow Data"**
  - 拿真實運維廠商資料寫 — 這是 ECN tool 學界沒有的延伸

### 6.2 RAG_Ultimate 線（partner research）

- **"Industrial Knowledge-Base RAG Benchmark for Wind Turbine O&M"**
  - IEEE Trans. Industrial Informatics
  - 已是 Phase 3 進行中，windMindOM 提供應用場景驗證

兩條線可彼此引用、共享資料集，但獨立投稿，不互相依賴。

### 6.3 計畫定位

- **國科會「能源科技整合型計畫」**：跨領域（電機 + AI + 工管 + 海洋工程）剛好打中
- **能源署「離岸風電在地化第三階段」**：派工/庫存/簽核 = 在地化軟體可搶位置的項目
- **教育部 USR**：simulator 模式可打包成大學風能實驗室教材

---

## 7. Roadmap 摘要

```
2026-Q2 (Month 1)  ─ Setup + 規劃 baseline
2026-Q3 (Month 2)  ─ Cost module（ECN 移植）
2026-Q3 (Month 3-4)─ Workflow module（庫存 + 派工 + 簽核）
2026-Q4 (Month 5)  ─ RAG / Knowledge module（含 mobile-friendly /field/）
2026-Q4 (Month 6)  ─ 第一個運維廠商 PoC + 第一筆合約
```

完整路線圖見 [`ROADMAP.md`](ROADMAP.md)。

---

## 8. 與既有 8 個 repo 的關係

| 既有 repo | windMindOM v0.8.1 中的角色 |
|---|---|
| **digiWindTurbine** | windMindOM 的本體（已 clone 為 windMindOM）；原 repo 留作研究/教學版本 |
| **ECN** | M2 內容移植進 windMindOM/modules/cost/；原 repo archive |
| **z72_etech** | M3-M4 取設計重寫進 windMindOM/modules/workflow/；原 repo archive |
| **z72hmiNew** | 留外面（Z72 服務性 repo） |
| **windAILab** | 留外面（另一公司業務）；M6+ 透過 API 介接 |
| **RAG_Ultimate** | 留外面（research line）；M5 提供「策略檔 + 預計算向量檔」給 windMindOM |
| **InduSpect** | 留外面（independent product）；M6+ 透過 API 介接 |
| **windFarmOM**（v0.5 archived） | 已廢棄；本機 D:\...\windFarmOM 作備份 |

---

## 9. 風險與弱點（誠實版）

| 風險 | 影響 | 緩解 |
|---|---|---|
| 6 個月做不完 | 高 | 不貪多功能；M2-M5 嚴守一月一 module；先求基本款 demo 出來 |
| 找不到 friendly 運維廠商客戶 | 高 | M1 開始就接觸（不要等 product 完才找）；先給 free trial 換 reference |
| 現場工程師覺得不好用 | 中 | M5 的 mobile UI 一定要找真實工程師試用；不只 dev 自己用 |
| RAG 答案品質不穩 | 中 | 用 RAG_Ultimate 提供的成熟策略；初期人工挑 top-3 結果做 quality check |
| Z72 PLC 連線在現場有問題 | 中 | digiWT 既有 opc_bachmann 已驗證；最壞 fallback 用客戶歷史 csv 匯入 |
| 客戶想要 AI 診斷但 windAILab 還沒 ready | 中 | 把 AI 列為「Enterprise 加值」，basic + Pro 都能獨立運作 |
| 運維廠商市場規模比想像小 | 中 | 台灣 + 日韓擴張；備案是轉戰學術市場（賣 simulator 給研究機構） |

---

## 10. 立刻可動的 3 件事（next 7 days）

1. **新 windMindOM repo baseline 整理**
   - docs/product/ 4 份文件就位（本檔 + decision_log + MVP_ARCHITECTURE + ROADMAP）
   - 搬入 v0.5 有用資產（pitch deck、daily-workflow、templates、claude-code-templates）
   - root CLAUDE.md 改為 windMindOM 產品脈絡
   - 第一個 commit + push

2. **接觸 1-2 個 friendly 運維廠商**
   - 透過學界人脈找 Z72 機型運維廠商
   - 給「無實場 demo」（用 simulator 跑）
   - 收集需求 + 報價反應

3. **Pitch deck v0.8.1 改版**（從 v0.4 pitch_deck.md 改）
   - 主視覺改為「運維廠商工具」
   - 套餐改為 Operator Basic / Pro / Enterprise
   - 競品矩陣加 RAG 與模擬器列
