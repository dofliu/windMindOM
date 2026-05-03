# windMindOM — Pitch Deck

> 用途：業主／潛在客戶接洽 + 國科會計畫審查
> 雙頻道：每張 slide 同時提供「商業故事」與「技術／學術 backing」
> 版本：v0.4（2026-05-02）— 對應 PRODUCT_VISION.md v0.4
> 格式：本檔（.md）為 source of truth，誠意版見 `pitch_deck.pptx`

---

## Slide 1 — 標題

# windMindOM
## 離岸風場 O&M 決策中樞

把告警、AI 診斷、知識檢索、派工、備料、簽核、成本回寫，
串成業主每天會用的工作鏈。

> **商業 hook**：「Demo 不需要你先給資料」
> **學術 hook**：「Closed-loop SCADA → AI → Workflow → Cost — 國際無單一玩家做到」

---

## Slide 2 — 問題（Why now）

### 業主面對的痛點

- **首批機組陸續出保**（Formosa 1/2 2025-2027）— 業主從「OEM 服務的接受者」變成「獨立 O&M 主體」
- **年度 O&M 預算抓不準** — 颱風週期、weather window、跨機種失效率都靠 Excel 拼湊
- **告警太多分不清優先序** — SCADA 一天 200 條 alarm，沒有自動成本影響評估
- **跨機種資料整不起來** — Z72 / Vestas / SGRE / MingYang 各自鎖在原廠平台
- **知識散在 PDF 與老師傅腦袋裡** — 故障訊息 → 手冊 → SOP 全靠人工搜尋

### 國際 / 國內背景

- 2024-2025 年國際 OEM 連番出包（SGRE 葉片召回、Vestas 齒輪箱），業主自建 condition monitoring 動力上升
- 政府第三階段風場 2026 起陸續商轉，要求供應鏈在地化
- ECN（現 TNO）的 O&M Tool 5.0 是事實標準，但只有 Excel + VBA、沒有 API 版本

---

## Slide 3 — 解法（One-liner）

### 我們做什麼

> **「核心 4 模組 + 可插拔 AI/Inspection 模組 + 成熟資產 simulator-first demo + 在地化派工/庫存/簽核 + ECN 雙向成本回寫」**

### 為什麼能做

不是從零開發。我們手上已經有 **7 個既有 repo + 1 個 sister product**，每個都已驗證或有真實資料：

| 資產 | 完成度 | 角色 |
|-----|--------|------|
| digiWindTurbine（物理模擬器） | 90% | 雙模資料層 — 真機 / 模擬切換 |
| windAILab（AI 多代理） | 60% | AI plugin（25 個 Python agent） |
| ECN（O&M Tool 5.0 移植） | 75% | Cost & Planning Engine |
| z72hmiNew（Z72 PLC HMI） | 80% | Z72 機型 adapter reference |
| z72_SCADA_etech（派工/庫存/簽核） | archive | 工作流設計來源 |
| RAG_Ultimate v8.0（Phase 3 論文） | 829 tests | Sister product（鬆耦合） |

整合工作量比從零造輪子少 **60%**。

---

## Slide 4 — 產品結構（核心 + 可插拔）

```
        ┌──────────── windMindOM 核心（必裝）─────────────┐
        │                                                │
        │  Turbine Adapter Layer（4 類資料源）             │
        │     ├ LiveAdapter   (PLC, e.g. Z72)             │
        │     ├ DatabaseAdapter (客戶 historian)          │
        │     ├ FileBasedAdapter (OEM 入口 CSV)           │
        │     └ SimulatorAdapter (digiWT 物理模擬)        │
        │                                                │
        │  Workflow Hub（核心 USP）                       │
        │     ├ Work Order（派工）                         │
        │     ├ Inventory（庫存）                          │
        │     └ Approval（多階簽核）                        │
        │                                                │
        │  Cost & Planning Engine（ECN 移植 + 雙向）       │
        │     forecast 預算 ⇄ actual 工時/料件回寫         │
        │                                                │
        │  Unified Dashboard / API Gateway                │
        └────────────────────────────────────────────────┘
                       ⇕ Plugin SDK
        ┌──────────── 可選模組 ──────────────────────────┐
        │  AI Plugin（windAILab，含內建輕量 RAG）          │
        │  AI Inspection（InduSpect，M6+，AI 定檢報告）    │
        └────────────────────────────────────────────────┘

        ═══════ Sister Product（並行銷售）═══════════════
        │  RAG_Ultimate v8.0 — 企業級 RAG + 風電 Benchmark │
        │  webhook 鬆耦合、不可用時 fallback 內建 RAG      │
        ═════════════════════════════════════════════════
```

**業主可以分階購買**：先 OM-Core，6 個月後 upsell AI plugin，知識管理需求高時再採購 RAG_Ultimate。
**首單門檻低、LTV 高。**

---

## Slide 5 — 核心差異化

### 4 條 USP（國際無單一競品同時擁有）

1. **完整工作鏈閉環**
   告警 → AI 診斷 → 知識檢索 → 工單 → 庫存 → 簽核 → 派工 → 完工 → **成本回寫 → 修正下一輪預測**
   一條 SQL transaction 跑完。SAP PM、ECN tool、Bazefield 各缺至少 2 塊。

2. **Demo 不需實場**
   Adapter 介面讓 simulator 可作為任何客戶的初始資料源。「客戶看 demo 不必先簽 NDA 給資料」是 sales killer feature。

3. **可插拔 AI / RAG / Inspection**
   核心產品可獨立運作。客戶有需求時加 plugin 或採購 sister product，**不需要先吞下整套 AI**。

4. **在地化**
   - 台灣海峽颱風週期 + 季風 weather window 模型
   - 多 OEM 並存（Z72/Vestas/SGRE/MingYang/中車）的跨機型 dashboard
   - 中文 UI、政府電業法規相容

---

## Slide 6 — 競品矩陣

|  | SCADA 即時 | AI 診斷+RAG | **派工** | **庫存** | **簽核** | 成本/排程 | 模擬器 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| SkySpecs (US) | 部分 | ✓✓ 葉片視覺 | – | – | – | – | – |
| Bazefield (NO) | ✓✓ | ✓ | ✓ | – | – | – | – |
| ONYX InSight (UK) | 部分 | ✓✓ gearbox | – | – | – | – | – |
| ECN/TNO Tool 5.0 | – | – | – | – | – | ✓✓ | – |
| Siemens MindSphere | ✓ | ✓ | ✓（ERP） | ✓（SAP） | ✓ | – | – |
| SAP PM / IBM Maximo | – | – | ✓✓ | ✓✓ | ✓✓ | – | – |
| OEM 自家 dashboard | ✓✓ 單品牌 | ✓ | – | – | – | – | – |
| **windMindOM** | **✓ 4 類 adapter** | **✓ plugin** | **✓✓** | **✓✓** | **✓✓** | **✓✓** | **✓✓** |
| **+ RAG_Ultimate** | – | ✓✓✓ benchmark | – | – | – | – | – |

→ **沒有任何一家同時涵蓋這 8 列。** 最接近的是 SAP PM + 第三方 SCADA 拼湊，但缺風電專屬的 weather window / Monte Carlo / simulator demo。

---

## Slide 7 — 商業模式（套餐結構）

### 三層套餐 + 兩 Sister Products

| 套餐 | 內容 | 估價 |
|------|------|------|
| **OM-Core** | 核心 4 模組 | NT$30-80k/turbine/年 或一次性 NT$5-10M + 維護 |
| **+ AI** | windAILab 故障診斷 + RUL + 內建輕量 RAG | +NT$15-30k/turbine/年 |
| **+ AI + Inspection**（M6+） | 加 InduSpect AI 定檢 | +NT$20-40k/turbine/年 |

**Sister products（並行銷售，可單買也可套裝促銷）**

| 產品 | 客群 | 估價 |
|------|------|------|
| **RAG_Ultimate v8.0** | OEM 服務部門、學界、政府 | NT$3-15M/案 + 維護 |
| **InduSpect** | 定檢服務商、離岸風場 | TBD |

### 第一筆收入路徑

> **3 個月部署 OM-Core + Z72 → NT$3-5M**
> **6 個月後 upsell AI plugin → +NT$2-3M**
> **12 個月後客戶若需要進階 RAG → +NT$3-15M**
>
> **單一客戶 LTV ≈ NT$8-23M（前 2 年）**
> **3 家 pilot 客戶足以養活 4 人團隊兩年**

---

## Slide 8 — 第一個客戶：Z72 風場

### 為什麼選 Z72 為首發

1. **三個 repo 都吃過 Z72 真實資料**（z72hmiNew / z72_SCADA_etech / digiWindTurbine）— **整合最快**
2. **無 OEM 合作門檻**（Harakosan/Zephyros 已退出市場，Z72 客戶 100% 自運維）— **不會被 OEM 阻擋**
3. **z72hmiNew 即實機運轉中** — 可作為「我們已在運維他們同款機」的 social proof
4. **PLC（Bachmann M1）通訊已驗證** — Z72LiveAdapter 兩週內可上線

### 第一階段交付（3 個月）

✅ Dashboard：即時 SCADA + 告警 + 工單 + 成本檢視
✅ 工作流：派工 / 庫存 / 多階簽核全跑通
✅ 報告：依客戶歷史故障算出的「5 年 O&M 預算 + 排程 Gantt」
✅ AI plugin（升級選項）：fault diagnosis + 內建 RAG 拉手冊

### 後續擴張

Z72 跑通後 → 透過 FileBasedAdapter 接 Vestas / SGRE 客戶（**不需要 OEM 配合**）→ M6+ 接入 InduSpect 視覺定檢。

---

## Slide 9 — 學術價值（給國科會 / 計畫審查）

### 兩條獨立論文線

#### A. RAG_Ultimate 線（Phase 3 進行中）

- **"Industrial Knowledge-Base RAG Benchmark for Wind Turbine O&M: Methodology and Baselines"**
  IEEE Trans. Industrial Informatics / Information Sciences
  學界目前 RAG benchmark 都是通用任務（HotpotQA、MS-MARCO），**工業特化幾乎沒有**。

#### B. windMindOM 線（4 篇）

- **"Closed-loop Integration of SCADA Anomaly → AI Diagnosis → Workflow → Cost"**（Applied Energy / Energy）
- **"Multi-Tier Adapter Pattern for Wind Farm Data Integration: From Live PLC to OEM-Portal CSV"**（軟工 + 風能跨域）
- **"Inventory and Crew Schedule Coupled Wind Farm O&M Cost Model: Extending ECN Tool 5.0 with Real-time Workflow Data"**（ECN tool 學界引用很高，我們是擴展者）
- **"AI-Generated Inspection Reports for Wind Turbine Internal Components: Integration with Maintenance Workflow"**（M6+ 接 InduSpect 後）

### 計畫定位

- **國科會「能源科技整合型計畫」**：跨領域（控制 + AI + 海洋工程 + 經濟模型）剛好打中
- **能源署「離岸風電在地化第三階段」**：派工/庫存/簽核 = 在地化軟體少數還能搶位置的技術項目
- **教育部 USR**：simulator 模式可打包成大學風能實驗室教材

---

## Slide 10 — Roadmap & Ask

### 12 個月路線圖

```
2026-Q2  M1 ─ 核心抽象與資料模型（Turbine Adapter / SQLAlchemy schema）
2026-Q3  M2 ─ Workflow Hub（派工 / 庫存 / 簽核）+ z72_etech 取材
2026-Q3  M3 ─ Cost Engine 雙向整合 + Z72LiveAdapter
2026-Q4  M4 ─ Plugin SDK + AI plugin v1
2026-Q4  M5 ─ 第一個 friendly 客戶 PoC + 國科會送審
2027-Q1+ M6 ─ InduSpect plugin + 跨 OEM adapter
```

### 我們需要的（Ask）

#### 業主 / 客戶

> **找一家 Z72 風場業主作 friendly pilot**
> 3 個月 NT$3-5M 部署 OM-Core，先用 simulator demo，再切實機。
> 失敗風險低，因為 Z72 整套技術鏈已驗證。

#### 國科會 / 計畫合作夥伴

> **送整合型計畫 2026 下半年截止前**
> 主題：「離岸風場 AI-RAG-工作流-成本決策中樞」
> 跨領域組合（電機 + AI + 工管 + 海洋工程），論文線已 ready。

#### 投資人 / 共同創辦人

> **首輪資金需求 TBD（依 SaaS vs 顧問模式選擇而異）**
> 4 人團隊 6 個月 ≈ NT$8-12M，配合 3 家 pilot 客戶 LTV NT$24-45M，
> 以顧問案先建立 case study，再轉訂閱制規模化。

---

### 聯絡

**Dof（DOF Lab）**
moredof@gmail.com

> 詳細產品文件：[`docs/PRODUCT_VISION.md`](PRODUCT_VISION.md)
> 詳細架構文件：[`docs/MVP_ARCHITECTURE.md`](MVP_ARCHITECTURE.md)
> 8 個來源 repo 資產地圖：[`docs/ASSETS_MAP.md`](ASSETS_MAP.md)
