# Product Documentation — windMindOM

> 這個資料夾放的是 **windMindOM 作為「運維廠商工具」的產品文件**。
> 與 `docs/` 根目錄下的 digiWT 技術文件（API_GUIDE / physics_model_status / Z72UserManual / OPC TAG xlsx）區分。

## 為什麼分兩層

windMindOM 從 digiWindTurbine 進化而來：

```
digiWindTurbine               →  windMindOM
─────────────────                 ─────────────
研究 / 教學定位                    商業產品定位
物理模擬器                         運維廠商工具
SCADA 平台                         監控 + 庫存派工 + 成本 + 報表 + RAG
─────────────────                 ─────────────
docs/API_GUIDE.md                 docs/product/PRODUCT_VISION.md
docs/physics_model_status.md      docs/product/MVP_ARCHITECTURE.md
docs/__Z72UserManual.pdf          docs/product/decision_log.md
                                  docs/product/ROADMAP.md
```

**digiWT 技術文件不刪、不改、不搬**——它們是 windMindOM 的「monitoring 模組」的技術 reference，繼續維護。

**新增的 `docs/product/` 是商業產品文件**——架構、商業模式、roadmap、決策歷史。

## 文件入口

| 檔案 | 用途 | 適合誰 |
|------|------|--------|
| [`PRODUCT_VISION.md`](PRODUCT_VISION.md) | 產品定位、ICP（運維廠商）、商業模式、競品比較 | 共同創辦人、投資人、客戶 |
| [`MVP_ARCHITECTURE.md`](MVP_ARCHITECTURE.md) | 5 modules（監控+庫存派工+成本+報表+RAG）、外部介接、技術選型 | 開發團隊、技術合作夥伴 |
| [`ROADMAP.md`](ROADMAP.md) | M1-M6 6 個月路線圖、每月主要交付 | 排 sprint、安排 milestone |
| [`decision_log.md`](decision_log.md) | 重大決策 ADR 紀錄（v0.5 → v0.8.1 pivot 在 DEC-06） | 想改變方向前必讀 |

## 版本歷史

- **v0.1 ~ v0.5**（2026-05-02 早段，廢棄）：windMindOM 為獨立整合容器、Plugin SDK、4 類 Adapter 等架構。經過 1 天討論後判斷對 1-2 人團隊太複雜，v0.8.1 重來。
- **v0.8.1**（2026-05-02 晚段，**現行**）：windMindOM 為 digiWT 商業化升級版；ICP = 運維廠商；5 大功能 monolithic；外部介接（windAILab、RAG_Ultimate、InduSpect）走 API/research artifact，不做 plugin SDK。

詳見 [`decision_log.md`](decision_log.md) DEC-20260502-06。

## 與其他系統的關係

```
windMindOM（產品）
├── 內部
│   ├── 監控（digiWT 既有 SCADA + simulator）
│   ├── 庫存派工（從 z72_etech 設計重寫）
│   ├── 成本計算（從 ECN 移植）
│   ├── 報表
│   └── RAG 知識檢索（用 RAG_Ultimate 提供的策略檔 + 向量檔）
│
└── 外部介接（皆為 API 或 artifact，不做 code 整合）
    ├── windAILab（partner company，AI 故障診斷）
    ├── RAG_Ultimate（research，best RAG strategy + 預計算向量檔）
    ├── InduSpect（independent product，AI 視覺定檢）
    └── z72hmiNew（Z72 服務性 repo，留外面）
```
