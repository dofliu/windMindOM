# 2026-05-04 — Friendly 客戶接觸 infrastructure（WMOM-20260503-05）

> Session 類型：sales infrastructure / 文件
> Session 長度：短
> 主導：Claude（劉老師指示「可以繼續-05」）
> 結果：接觸名單模板 + cold email 腳本 + 30 分鐘 demo agenda + 回饋紀錄結構就位

---

## 1. Session 目標

WMOM-20260503-05 — 整理 1-2 個 friendly 運維廠商接觸名單。

Issue 預估「0.5 工作天（盤點）+ 持續整月（接觸）」，本 session 做前者：建立
infrastructure 讓劉老師接下來能直接用，不卡技術細節。

特別處理：實際聯絡資訊（PII / 商業敏感）**不入 git**，只 commit 模板 + 公開渠道清單 + 腳本。

## 2. 實際完成

### 2.1 主要工作

- ✅ `docs/sales/friendly_contacts.md.template` — contact entry 結構 + 4 大渠道分類
  + 每個渠道的具體建議來源（公開資訊，無 PII）
- ✅ `docs/sales/outreach_script.md` — cold email 腳本（中文）+ 30 分鐘 demo agenda
  + objection handling FAQ
- ✅ `docs/sales/customer_feedback/README.md` — 回饋紀錄模板說明
- ✅ `docs/sales/customer_feedback/_TEMPLATE.md` — 單場 demo / 訪談的紀錄範本
- ✅ `.gitignore` 追加：`docs/sales/friendly_contacts.md`（實際填寫版）+
  `docs/sales/customer_feedback/202*-*-*-*.md`（具名場次）— 私密內容不入 git，
  只在本機保存
- ✅ ISSUES.md WMOM-05 標記 `in_progress`（infrastructure done，contact gathering ongoing）

### 2.2 卡住或延後的事

- 實際聯絡名單 → 劉老師執行（NCUT 學界、Bachmann Taiwan、台電/中能/CIP 分包商）
- 第一場 30 分鐘 demo → M1 月底前約

### 2.3 重大決策

- 無新 DEC，但決定**不 commit 實際聯絡資訊** — 屬於 PII / 商業敏感，與
  product privacy & user trust 一致

## 3. 產出清單

### 新增檔案

- `docs/sales/friendly_contacts.md.template`
- `docs/sales/outreach_script.md`
- `docs/sales/customer_feedback/README.md`
- `docs/sales/customer_feedback/_TEMPLATE.md`
- `work-logs/2026-05/2026-05-04-friendly-contacts.md`（本檔）

### 修改檔案

- `.gitignore`（追加 friendly_contacts.md + customer_feedback/202*-*-*-*.md 排除規則）
- `ISSUES.md`（WMOM-05 open → in_progress；統計表更新）
- `STATUS.yaml`（M1 progress 75→85，next_milestone 改為「持續接觸 + M2 開工」）

### 動了狀態的 issue

- WMOM-20260503-05: open → in_progress

## 4. 下次怎麼接手

兩條平行路：

**Sales 線（劉老師執行）**：
1. 複製 `friendly_contacts.md.template` → `friendly_contacts.md`（本機 only）
2. 從 4 大渠道盤 5-10 位潛在 contact，填進去
3. 用 `outreach_script.md` 的 cold email 範本寄出 3-5 封
4. 第一場 demo 後用 `customer_feedback/_TEMPLATE.md` 寫紀錄（檔名 `YYYY-MM-DD-{客戶代號}.md`，本機 only）

**Dev 線（下個 session）**：
- 進 **M2 — Cost module（從 ECN 移植）**
- 第一週要做 K13 demo dataset 跑通（最大 risk，必須提早暴露）
- 開新 issue：`WMOM-20260601-01 — ECN engine 移植到 modules/cost/`
- 路線圖見 [`docs/product/ROADMAP.md`](../../docs/product/ROADMAP.md) Month 2

阻擋項：無（M1 5 個 issue 都已解鎖）

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 規劃 .gitignore 策略（PII vs 模板） | 10% |
| 寫 contacts template + 渠道分類 | 25% |
| 寫 outreach script（cold email + demo agenda + FAQ） | 40% |
| 寫 customer_feedback README + template | 15% |
| 收尾（ISSUES / STATUS / commit） | 10% |

## 6. 學到的事

- **「Sales infrastructure」不是「sales」** — Claude 能做的是給工具與腳本，實際接觸與
  關係維護是劉老師的事；分清楚 boundary 才不會交付不負責任的產出
- **「不入 git」要靠 .gitignore 強制** — 光在文件裡寫「請勿 commit」沒用，第一次
  `git add .` 就會誤入；防呆要寫進 .gitignore
- **Cold email 腳本要短**（< 100 字）+ 留可量化的 demo offer + 留低承諾退出條款
  （「30 分鐘無壓力，不用準備資料」）

## 7. Open questions（park）

- 是否要做英文版 cold email（給 Bachmann Taiwan 的歐洲總部聯絡）？暫不做，先中文
- 是否做電話訪談 script（vs cold email）？目前先 email-first，視回應率再加
- Demo 後是否要寄 NDA/MoU？目前先口頭信任，第一場 demo 純 discovery，回饋紀錄即可
