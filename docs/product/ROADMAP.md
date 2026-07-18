# windMindOM Roadmap v0.8.1 — 6 個月路線圖

> 版本：v0.8.1（2026-05-02）
> 目標：2026-Q4 第一個運維廠商客戶 PoC + 第一筆合約
> 節奏：一日一項重要工作，**一月一 module**

---

## TL;DR — 6 個月里程碑

```
Month 1 (2026-05) — Setup：repo baseline、規劃文件就位、第一個 friendly 客戶接觸
Month 2 (2026-06) — Cost module（從 ECN 移植）
Month 3 (2026-07) — Workflow Part 1（Work Order + Approval）
Month 4 (2026-08) — Workflow Part 2（Inventory）+ Reporting
Month 5 (2026-09) — Knowledge / RAG module + mobile /field/ UI
Month 6 (2026-10) — 第一個運維廠商 PoC + 第一筆合約
```

每月有「可 demo 的交付」，避免到 Month 6 才發現方向錯了。

---

## Month 1（2026-05）— Setup baseline

### 主要交付

| 交付 | Sub-task |
|------|---------|
| Repo baseline 整理 | 把 digiWT 既有檔案搬到 `modules/monitoring/`；建 4 個空 module 占位 |
| 統一 pyproject.toml | 整合既有 digiWT deps + 預留 cost/workflow/RAG 用 lib |
| Root CLAUDE.md 改為 windMindOM 產品脈絡 | 既有 digiWT CLAUDE.md 移到 `docs/legacy/` 保留 |
| 搬入 v0.5 有用資產 | pitch_deck.md/.pptx、daily-workflow.md、claude-code-templates、templates |
| ISSUES.md / STATUS.yaml / TODO.md / CHANGELOG.md | 從零重新建立（v0.5 版本廢棄） |
| 接觸 1-2 個 friendly 運維廠商 | 透過學界人脈、demo simulator 給他們看 |
| Pitch deck v0.8.1 改版 | 主視覺改為「運維廠商工具」、套餐改為 Operator Basic / Pro / Enterprise |
| **前端 UI 改版**（WMOM-20260507-01）— **新增** | A · Calm Operator 設計（鼠尾草綠 / 翡翠玻璃雙主題）；220 px sidebar、5 大頁重畫；建立 `frontend/components/ui/` + `frontend/theme/` 共用元件庫；M3+ 所有 frontend issue 走新元件 |

### 「無實場 demo」可成立的標準

Month 1 結束時，要能對 friendly 客戶說：

> 「這是我們的產品，跑起來給你看。下面這 14 台風機是模擬的，但跟真實 SCADA 一模一樣。
> 你看：實時監控、歷史曲線、告警、power curve...
> 後面 5 個月會加上：庫存派工、成本、月報、警報查手冊。」

→ digiWT 既有功能 + 規劃故事，先行 sales 用。

### Issue 預估（第一週）

- WMOM-20260503-01 — repo baseline 整理
- WMOM-20260503-02 — 搬入 v0.5 有用資產
- WMOM-20260503-03 — root CLAUDE.md 改為產品脈絡
- WMOM-20260503-04 — pitch deck v0.8.1 改版
- WMOM-20260503-05 — Friendly 客戶接觸名單

---

## Month 2（2026-06）— Cost module

### 主要交付

| 交付 | Sub-task |
|------|---------|
| ECN backend 移植進 modules/cost/ | engine/{cost_cal, waiting_time, monte_carlo, var_fluct} |
| K13 demo dataset 跑通 | 驗證移植後的 ECN 計算結果與原 ECN tool 對得上（**第一週就要做**） |
| Cost adapter | windMindOM 內 schema ⇄ ECN 計算 schema 轉換 |
| /admin/cost/ frontend | budget view + ledger view + LCOE dashboard |
| API endpoint | POST /api/cost/forecast、GET /api/cost/ledger |

### Demo flow（Month 2 結束時）

> 「給定一年 SCADA + maintenance log → 算出 LCOE = X.X NT$/kWh + 成本拆解 → 顯示在 dashboard」

### Risk

- ECN 計算結果如果跟原 tool 對不上，第一週就要發現並修；不能拖到 Month 5
- 解法：第一週內把 K13 demo 跑通，數字一致才繼續

---

## Month 3（2026-07）— Workflow Part 1

### 主要交付

| 交付 | Sub-task |
|------|---------|
| 從 z72_etech 取設計 | dev team 讀 archive 程式碼 5-7 天，產出 3 份 design notes |
| 30 分鐘 user walkthrough | 跟 Dof 確認 design notes 沒誤解（[`decision_log.md`](decision_log.md) DEC-03） |
| Work Order CRUD + 狀態機 | modules/workflow/work_order.py + tests |
| Approval 多階簽核 | modules/workflow/approval.py + tests |
| /admin/workflow/orders frontend | 工單建立精靈 + 列表 + 詳情 |
| /admin/workflow/approval frontend | 我的待簽 + 簽核操作 |

### Demo flow

> 「告警 → 一鍵生工單 → 送多階簽核 → 班長核准 → 派工 → 完工」

（庫存還沒做，工單裡的料件先用文字記錄，Month 4 接 Inventory）

---

## Month 4（2026-08）— Workflow Part 2 + Reporting

### 主要交付

| 交付 | Sub-task |
|------|---------|
| Inventory 主檔 + 雙寫交易模型 | modules/workflow/inventory.py + tests |
| Inventory ↔ Work Order 整合 | 工單完工 → 庫存自動扣帳 |
| /admin/workflow/inventory frontend | 庫存查詢 + 出入庫 + 安全庫存告警 |
| Cost ↔ Workflow 雙向 | Work Order 完工 → cost ledger（actual） |
| Reporting module | monthly_report.py（PDF）+ annual_budget.py |
| /admin/reports frontend | 月報生成 + 年度預算 |

### Demo flow

> 「告警 → 工單 → 簽核 → 派工 → 完工 → 庫存扣帳 → cost actual 寫入 → 月底自動產 PDF 月報給業主」

→ 完整工作鏈閉環。

---

## Month 5（2026-09）— Knowledge / RAG + 現場 UI

### 主要交付

| 交付 | Sub-task |
|------|---------|
| Knowledge module 後端 | ingest.py、retrieve.py、strategy_loader.py、alert_handler.py |
| ChromaDB 整合 | 嵌入式模式、依 OEM 機型載入向量檔 |
| RAG_Ultimate strategy 對接 | 拿 Phase 3 提供的 strategy.yaml + z72_manual.parquet |
| 灌客戶手冊 + 一年警報 csv | 用 RAG_Ultimate 策略走 ingest pipeline |
| /field/ frontend（mobile-first） | alerts list、alert detail with RAG、my work orders、completion |
| Alert → RAG auto query | 警報事件觸發即查 retrieve，前端顯示 top-3 chunks |

### Demo flow（**Month 5 結束時是 PMF 關鍵時刻**）

> 「告警跳出 → 30 秒內現場工程師手機上看到：
> - 手冊 §4.3 段落（Z72 Bachmann gearbox temperature alarm 處理 SOP）
> - 過去 6 個月 5 次同類警報，3 次是冷卻液不足（建議先檢查）」

→ 找真實工程師試用，問「這比 LINE 群組問師傅快嗎？」

### Risk & 緩解

- Phase 3 strategy 如果還沒 ready：用 baseline（chunking=512、bge-small embedding、top-k=5）做 placeholder；等 Phase 3 升級
- 客戶手冊 PDF 解析品質不穩：先處理 Z72 手冊（已有 docs/__Z72UserManual.pdf），跑通流程再擴

---

## Month 6（2026-10）— 第一個 PoC + 第一筆合約

### 主要交付

| 交付 | Sub-task |
|------|---------|
| Friendly 運維廠商現場部署 | docker-compose 在客戶端跑起來 |
| Z72 PLC 連線測試 | 客戶端 OPC tunnel 正常運作 |
| 客戶手冊 + 歷史警報 csv 灌入 | 用 ingest pipeline 處理 |
| 培訓 | 老闆 + 主管 + 現場工程師各 1 場 |
| 第一個月運轉 | 收集使用反饋 + bug |
| 第一筆合約 | NT$2-4M（Operator Basic 或 Pro） |
| 第一份月報 | 由 windMindOM 自動產出，給該運維廠商交給業主 |

### Done criteria

✅ 客戶老闆說「下一個月也續用」
✅ 客戶現場工程師至少 80% 警報用 RAG 查詢（不是 LINE）
✅ 第一份月報送給業主沒被退件
✅ 收到合約金（簽 LOI 也算）

---

## Month 7+（2026-11 之後）— 規模化

不在本 ROADMAP 範圍，但建議方向：

- 第二、第三個運維廠商客戶（target NT$10-20M ARR）
- windAILab AI 介接（Enterprise 套餐）
- InduSpect 介接（如有客戶要）
- 第二個 OEM PLC adapter（依客戶需求 Vestas / SGRE）
- 國科會整合型計畫送審
- 第一篇期刊論文投稿

---

## 每月節奏（routine cadence）

每月內：

| 週 | 主要工作 |
|----|---------|
| Week 1 | 該月最關鍵的 spike / risk validation（如 ECN 數字驗證、RAG 策略對接） |
| Week 2-3 | 主開發 + test |
| Week 4 | 整合 + demo + 回顧、為下個月做準備 |

每週內依 [`docs/routines/daily-workflow.md`](../routines/daily-workflow.md)（從 v0.5 搬入）的 8 phase routine 跑：preflight → claim → branch → implement → verify → review → wrap-up → commit。

---

## 進度檢視 dashboard

> 狀態快照（2026-07-18）：實際執行進度領先原訂月曆——M2–M5 提前於 6–7 月推進。以 [`STATUS.yaml`](../../STATUS.yaml) 為準。

| Month | Module | Done criteria | Status |
|-------|--------|--------------|:------:|
| 1 (2026-05) | Setup | repo baseline + 規劃就位 + friendly 客戶接觸 | ✅ done（infra；客戶接觸持續中） |
| 2 (2026-06) | Cost | K13 demo 跑通 + LCOE dashboard | ✅ done |
| 3 (2026-07) | Workflow Part 1 | Work Order + Approval 跑通 | ✅ done |
| 4 (2026-08) | Workflow Part 2 + Reporting | Inventory + 月報 PDF | ✅ done |
| 5 (2026-09) | Knowledge / RAG | 警報 → 30 秒 RAG | 🟡 in_progress (~75%) |
| 6 (2026-10) | PoC + 合約 | 第一筆收入（M6-4 auth 全面完成） | 🟡 in_progress (~20%) |

每月最後一個 session 更新本表 + work-log + STATUS.yaml。

---

## 路線圖修正機制

每月最後一個 session：

1. Review 該月 work-log，找出 bottleneck
2. 改進本檔（更新該月已完成、下月計畫微調）
3. 重大 scope 改動 → 開 DEC（[`decision_log.md`](decision_log.md)）

預期可能的修正點：
- ECN 移植比預期複雜 → Month 2 拉長 0.5 個月，Month 3-6 各延 0.5
- z72_etech 取設計困難 → Month 3 改採「自己設計簡化版」
- 找不到 friendly 客戶 → Month 4-5 改 plan B（學術市場 / 教育部門）
- 第一個客戶要 Vestas adapter → Month 6 加 1 個 sprint，第一筆合約延到 Month 7

**ROADMAP 不是契約，是預估。** 真實開發中允許每月微調，但每改動必須寫進 decision_log + 通知合作對象。
