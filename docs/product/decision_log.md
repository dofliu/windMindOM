# Decision Log — windMindOM 產品決策紀錄

> 任何「動到架構 / 改變產品方向 / 重新定位」的決策都進這份。
> 格式：每個 decision 一個 `## DEC-{YYYYMMDD}-{NN}` 段落。
> 想反向決策（撤銷）時，在原 DEC 下加 `### Superseded by DEC-...`，**不要刪除原內容**。

---

## DEC-20260502-06 — 架構大轉向 v0.5 → v0.8.1：windMindOM 由「整合 platform」改為「digiWT 商業化升級版（運維廠商工具）」

**Date**: 2026-05-02
**Status**: accepted
**Version**: v0.8.1（現行 baseline）
**Decision maker**: Dof
**Trigger**: 用戶反思「v0.5 系統變得太複雜」+「我這些系統其實都可以獨立運作」+「windMindOM 應該定位為運維廠商工具」

### Context

2026-05-02 在 Cowork 階段做了 5 輪規劃迭代（v0.1 → v0.5），最終決定：
- v0.5 windMindOM 為獨立整合容器
- 含 Plugin SDK、Workflow Hub 獨立 service、Cost engine 雙向 webhook、4 類 Turbine Adapter ABC
- 估算 25-35 週 for 4 FTE → 1-2 人實際 12-18 個月才能 MVP

下午用戶反思幾件事：

1. **v0.5 對 1-2 人團隊太複雜**：12-18 個月才見第一個客戶風險太高
2. **每個 repo 其實可獨立成為產品**：digiWT、ECN、windAILab、RAG_Ultimate、InduSpect 都有獨立商品化潛力
3. **真正想要「整合」的動機是省維護時間**，不是賣 platform
4. **應該以 ICP 為中心思考**：目標客戶是「運維廠商」，他們需要的是「監控+庫存派工+成本+報表」聚焦工具，不是 AI 平台
5. **公司治理邊界**：windAILab 是另一間公司的業務，AI 診斷透過 API 介接即可，不必整進產品本體
6. **現場工程師也是 user**：警報跳出時要 30 秒內查到手冊答案——RAG 屬於核心功能

### Considered Options

#### A. 維持 v0.5（platform play，windMindOM 為新整合容器）
- ✅ 架構乾淨、適合 enterprise 銷售、VC pitch 故事好
- ❌ 12-18 個月 for 1-2 人；風險集中；客戶反饋進來前的工程量大

#### B. v0.6 — digiWT-evolution（digiWT 為主軸進化）
- ✅ 7 個月見收入、有 traction
- ❌ 架構不乾淨（digiWT 不是 platform-first 設計）；只解了一半問題

#### C. v0.7 — Monorepo（為「省維護時間」而整合）
- ✅ 共享 CI / docker / deps，每週省 7-8 小時維護時間
- ❌ 4-6 週重組成本；windAILab、RAG_Ultimate 的論文線會被影響

#### D. **v0.8.1 — Operator-focused product（本決策採納）**
- windMindOM = digiWT 商業化升級版（rebrand digiWT 為 windMindOM 對外名稱）
- ICP：運維廠商 + 現場工程師雙 persona
- 5 大功能：監控 + 庫存派工 + 成本（ECN 移植）+ 報表 + RAG 知識檢索
- 外部介接：windAILab / RAG_Ultimate / InduSpect 走 API + research artifact，不做 plugin SDK
- z72hmi 留外面（Z72 服務性，非通用）

### Decision

選 **D — v0.8.1 Operator-focused product**。

### Rationale

1. **ICP 切到運維廠商** vs 風場業主：
   - 運維廠商銷售週期 1-3 個月（vs 業主 12-24 個月）
   - 痛點明確（每月要報 SCADA + 成本 + 工時給業主）
   - 競品弱（Excel + LINE + 紙單）
   - 採購預算彈性高

2. **以 digiWT 為基礎**：
   - 90% 完成度，立刻可 demo
   - SCADA 平台這層工程量大，已寫好
   - 加 cost / workflow / RAG 三個 module 約 3-4 個月可以完成
   - 6 個月見第一個客戶 vs v0.5 的 12-18 個月

3. **公司治理邊界清楚**：
   - windAILab 是另一間公司的業務 — AI 故障診斷透過 API 介接，不必整進產品
   - RAG_Ultimate 是 research — 提供「策略檔 + 預計算向量檔」給 windMindOM 使用，runtime 不依賴 service
   - InduSpect 是獨立產品 — 同 windAILab 模式

4. **RAG 是核心功能不是 add-on**：
   - 現場工程師是高頻 user
   - 警報 → 查手冊是每日操作
   - RAG 是給工程師的甜頭、提升 PMF

5. **取捨接受**：
   - 放棄昨天 v0.5 的 windMindOM repo（GitHub 上的舊內容刪除，新 repo 從 digiWT clone 開始）
   - api/adapters/base.py 等 v0.5 程式廢棄（22 tests 仍是 design reference 但不繼續維護）
   - Plugin SDK / Workflow Hub 獨立 service / cost 雙向 webhook 等過度工程一律不做

### Consequences

#### 立即變動
- **Repo reset**：`github.com/dofliu/windMindOM` 刪除重建，內容從 `digiWindTurbine` clone（2026-05-02 已完成）
- **本地資料夾**：`D:\...\windFarmOM\`（v0.5）保留作備份；`D:\...\windMindOM\`（新）為實際工作目錄
- **昨天 v0.5 的程式廢棄**：`api/adapters/base.py`、`pyproject.toml` 加的 deps 等不沿用；架構與設計可作 reference
- **v0.5 文件處理**：pitch deck、daily-workflow、claude-code-templates、templates 仍適用，搬入新 repo
- **v0.5 廢棄文件**：PRODUCT_VISION_v0.5、MVP_ARCHITECTURE_v0.5、ASSETS_MAP_v0.5、ISSUES_v0.5 不搬

#### 對 issue tracker 影響
- 昨天 10 個 WMOM-20260502-* issue 全部廢棄
- 從 0 重新編號 issue（前綴 `WMOM-` 沿用，從 2026-05-03 起新編）
- 已完成的歷史 issue（00 git init、01 pitch deck、02 review、03 adapter）保留為「廢棄但歷史」

#### 對既有 6 個 repo 命運影響
- **digiWindTurbine**：保留為「研究 / 教學版本」原 GitHub repo 不動；新 windMindOM 是它的商業化 fork
- **ECN**：M2-M3 階段內容移植進 windMindOM/modules/cost/，原 repo archive
- **z72_etech**：M3-M4 階段取設計重寫進 windMindOM/modules/workflow/，原 repo archive
- **z72hmiNew**：保持獨立 active（Z72 服務性 repo）
- **windAILab**：保持獨立 active（另一公司業務）
- **RAG_Ultimate**：保持獨立 active（research line + Phase 3 論文）
- **InduSpect**：保持獨立（independent product）

#### 對時程影響
- v0.5 估算 12-18 個月（1-2 人）→ v0.8.1 估算 6-7 個月
- 第一個運維廠商 PoC 從 2027 早段提前到 2026 Q4

---

## v0.5 階段歷史決策摘要（DEC-01 ~ DEC-05）

下面是 2026-05-02 早段 v0.1 → v0.5 規劃過程中的 5 個決策，**內容已被 DEC-06 整體 supersede**，但保留作歷史與 design reference。

### DEC-20260502-01 — RAG_Ultimate 改為 sister product（v0.4 採納，v0.8.1 沿用）

**精神保留**：RAG_Ultimate 是 research，windMindOM 內 RAG 用其提供的「策略檔 + 預計算向量檔」。
**v0.8.1 修改**：RAG 從「sister product webhook」變更為「核心功能 + research artifact 模式」（細節見 PRODUCT_VISION v0.8.1 §3.5）。

### DEC-20260502-02 — 第一個 friendly 客戶定為 Z72 風場（v0.4 採納，v0.8.1 沿用）

**精神保留**：Z72 客戶為首發 reference，無 OEM 合作門檻。
**v0.8.1 修改**：Z72 客戶可能不再是「業主」而是「Z72 機型的運維廠商」，ICP 改變但首發機型相同。

### DEC-20260502-03 — z72_etech 取材方式選 A（dev team 讀程式）（v0.4 採納，v0.8.1 沿用）

**完全沿用**：M3-M4 階段 dev team 讀 z72_etech archive 程式產出 design notes，重寫進 modules/workflow/。

### DEC-20260502-04 — 規劃文件採增量編輯（v0.3+ 採納）

**精神保留**：增量編輯為主，但 v0.5 → v0.8.1 是大轉向不算增量。
**v0.8.1 修改**：v0.8.1 之後若要再大改，必須走 DEC + 重寫架構文件。

### DEC-20260502-05 — windFarmOM rebrand 為 windMindOM（v0.5 採納）

**精神保留**：windMindOM 為對外品牌名稱。
**v0.8.1 修改**：windMindOM 不再是「整合容器」名稱，而是 digiWT 商業化版本的對外名稱。

---

## 範本（複製此塊新增 decision）

```markdown
## DEC-{YYYYMMDD}-{NN} — 一句話描述

**Date**: YYYY-MM-DD
**Status**: proposed | accepted | superseded | rejected
**Version**: 對應的規劃版本
**Decision maker**: 誰

### Context

問題的背景。為什麼需要做這個決定。

### Considered Options

- A. ...
- B. ...
- C. ...

### Decision

選 X。

### Rationale

為什麼選 X。

### Consequences

這個決策帶來的影響：哪些檔案要改、哪些任務新增、哪些 trade-off 接受。
```
