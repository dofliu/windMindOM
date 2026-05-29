# windMindOM — TODO（短期工作板）

> 用途：本檔案是「**這週 / 這個月**正在做什麼」的快速 dashboard。
> 詳細 issue 規格在 [`ISSUES.md`](ISSUES.md)；完整路線圖在 [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md)；
> M5/M6 大目標 epic 拆解在 [`ISSUES.md`](ISSUES.md) 頂部「🎯 未來大目標」區塊。
>
> 規則：
> - 只列「進行中 + 下一個要做」的事，**不列已完成**（done 的事看 git log + ISSUES.md）
> - 每次 session 開頭 / 結尾更新本檔
> - 大局看 ROADMAP；今日工作看 ISSUES.md；本週/本月節奏看本檔

最後更新：2026-05-29（文件大整理：清掉 digiWT 時代過時/重複檔、ISSUES.md changelog 抽到 archive、新增 M5/M6 epic 區塊；baseline backend 570 / frontend vitest 59）

---

## 現況（2026-05）

- **M1-M4 全 done**：monitoring（既有）+ cost（M2）+ workflow（M3-M4）+ reporting（M4）皆完成
- **baseline 綠**：backend `pytest modules/{workflow,cost,reporting}/tests/` → **570 passed / 1 xfailed**；frontend vitest **59 passed** / tsc 0 / vite build OK
- **近期 autonomous daily worker** 在補測試覆蓋與工程基礎設施（vitest+RTL 導入、純函式回歸測試、CI baseline 容差、並發 dispatch 序列化）

---

## 下一個 milestone — M5：Knowledge / RAG + 現場 mobile UI（2026-09 target）

> 目標：警報 → RAG 查 Z72 手冊 → 給現場工程師可操作的處置建議；現場 mobile UI 是 PMF 關鍵。
> Done criteria：現場工程師手機掃到警報，能查到對應手冊段落 + 處置步驟。

詳細 epic 拆解見 [`ISSUES.md`](ISSUES.md) 頂部「🎯 未來大目標」。

### 可立即接手（autonomous-friendly，無設計歧義）

- [ ] **前端 component render 測試**（CostPage / FarmOverview / workflow Panel）—— 需先補 `vitest.config.ts` jsdom setupFiles + `npm i -D @testing-library/jest-dom`
- [ ] **WMOM-20260509-F6** — PostgreSQL row-lock integration test（M6 部署前，需 docker postgres）

### 需劉老師決策才能開工

- [ ] **WMOM-20260519-01** — `add_return` 超量退料 domain guard（需會計語意決策）
- [ ] **WMOM-20260513-02** — Demo Orchestrator full impl（含 INSPECTION over-use product decision）
- [ ] **WMOM-20260513-01** — UI 改版 v2（placeholder — 等劉老師補新設計交接書）

### 客戶接觸（持續）

- [ ] **WMOM-20260503-05** — Friendly 客戶接觸名單（infrastructure done；待劉老師執行 cold email + 約 demo）

---

## 物理模型強化（park 到有需要再評估的學術深度題）

> 既有 18/21 quality check 已通過，非 must-have；商業 demo 不依賴這些。

- [ ] **WMOM-20260505-23** — Physics 自我驗證框架（7 層 validator + health check CLI）
- [ ] **WMOM-20260505-24** — Data quality 3 項 fail 修正
- [ ] **WMOM-20260505-25** — Frontend RUL + 多 band alarm 視覺化
- [ ] WMOM-20260505-26/27/28 — SCADA tag 擴充 / 保護電驛協調 / 單齒 defect signature

---

## Parking lot（不在當前 milestone）

- M6 之後：windAILab AI 故障診斷 HTTP API 介接（Enterprise 套餐，另一公司業務、走 API）
- M6 之後：InduSpect AI 視覺定檢介接
- M6 之後：第二個 OEM PLC adapter（Vestas / SGRE）
- M5 之後：RAG_Ultimate Phase 3 升級（chunking 策略、評估指標）
- 物理模型升級：新 issue 從 `docs/legacy/digiwt_TODO.md` parking lot 找

---

## 已封存的歷史 TODO（digiWT 階段）

`docs/legacy/digiwt_TODO.md` ← 既有 244 條物理 / SCADA / fatigue / wake 細節改進清單。
未來如要動 monitoring 層，先翻這份找 reference，**不要重複造輪子**。
