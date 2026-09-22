# windMindOM — TODO（短期工作板）

> ⚠ **2026-09-22 CI runner 基礎設施仍失效中（待劉老師檢查 GitHub Actions 帳號設定）**：當日**每一個**
> CI run 都在 2-8 秒內失敗、`runner_id: 0`、check output 全空（job 從未被排到 runner 上跑過任何測試），
> 含 PR #157 / #158 / #159 與**跟 PR 無關的 main push run**；多次重跑結果相同，非 flake。
> `.github/workflows/ci.yml` 內容正常、workflow 狀態 active，排除程式碼與 workflow 設定問題，
> 研判為帳號/組織層級 GitHub Actions runner 配額或計費限制（或平台事故）。
>
> **飛輪目前是停的**：`auto-merge.yml` 的 run 全部是 `skipped`（它要 CI 綠才動），**PR #157 / #158 是
> 劉老師人工合併的**（非 auto-merge），倚賴的是 autonomous session 的本機驗證結果。
>
> **對下個 session 的意義**：本機驗證（`pytest` + `vitest`/`tsc`/`build`）是目前唯一可信的把關，
> 照常做完整驗證再開 PR；但**不要等 auto-merge**，PR 會停在紅燈需人工合併。遇到同款秒退
> （秒退 + `runner_id: 0` + output 全空）不必反覆重跑或重複診斷——留言記錄一次即可，
> 且**絕不可為了繞過 CI 直接 push main**。
>
> 用途：本檔案是「**這週 / 這個月**正在做什麼」的快速 dashboard。
> 詳細 issue 規格在 [`ISSUES.md`](ISSUES.md)；完整路線圖在 [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md)；
> M5/M6 大目標 epic 拆解在 [`ISSUES.md`](ISSUES.md) 頂部「🎯 未來大目標」區塊。
>
> 規則：
> - 只列「進行中 + 下一個要做」的事，**不列已完成**（done 的事看 git log + ISSUES.md）
> - 每次 session 開頭 / 結尾更新本檔
> - 大局看 ROADMAP；今日工作看 ISSUES.md；本週/本月節奏看本檔

最後更新：2026-09-22（autonomous session #5：WMOM-20260922-03 — 情境比較分析 A2 Part 1：跨情境
摘要並排端點 `GET /api/scenarios/compare`（DEC-20260720-02），backend 1094→1103 passed，frontend
未動；session #4：WMOM-20260922-02 — PR D：`GuidedTourPage` inline
component remount 修（DEC-20260720-01），frontend 960→961 passed；session #3：WMOM-20260720-13
A1 round-2 follow-up 4 個 Should-fix 全修（PR #157 merged）；session #2：WMOM-20260922-01
accelerated 模式 stop() 響應性收尾（PR #158 merged）；session #1：WMOM-20260720-04 + -08 live/OPC
後端硬化收尾——M6 現場部署唯一硬阻塞已清除。**CI runner 基礎設施仍持續失效**，見上方警語）

> ⚠ 本檔其餘內文（現況段落、下方清單）大多還停在 2026-07-18 的狀態快照，比 `STATUS.yaml` / `ISSUES.md`
> 舊很多（M5 已到 ~90%、M6 已到 auth+live/OPC 硬化完成）。下次整理 TODO 時建議整份對照 `ISSUES.md`
> 「🎯 未來大目標」區塊重寫，而非逐次小補丁——本 session 範圍只做 WMOM-20260922-03，不在此展開。

---

## 現況（2026-07，內容已過時，見上方提醒）

- **M1-M4 全 done**：monitoring（既有）+ cost（M2）+ workflow（M3-M4）+ reporting（M4）皆完成；**M5（Knowledge/RAG + 現場 mobile UI）進行中 ~75%**（主功能到齊，剩客戶手冊擴充 + 一年警報 csv 灌入，屬 M6 部署期）；**M6-4 auth 模組已完成**（JWT + RBAC + 全 router 授權已全面強制執行 + 前端真登入頁面與 AuthProvider已對接）。
- **baseline 綠**：backend 全套（6 module + monitoring/physics + e2e）→ **1103 passed / 7 skipped / 1 xfailed**；frontend vitest **961 passed** / tsc 0 / vite build OK。CI 現已涵蓋 monitoring + physics 與 auth 測試（**惟 CI runner 基礎設施本身自 2026-09-22 起持續失效**，見上方提醒，本機驗證仍是唯一可信來源）。
- **節奏提醒**：autonomous 飛輪已重啟（每 3 小時），挑題準則為「對 M6 critical path 有貢獻優先」。

---

## 下一個 milestone — M5：Knowledge / RAG + 現場 mobile UI（2026-09 target）

> 目標：警報 → RAG 查 Z72 手冊 → 給現場工程師可操作的處置建議；現場 mobile UI 是 PMF 關鍵。
> Done criteria：現場工程師手機掃到警報，能查到對應手冊段落 + 處置步驟。

詳細 epic 拆解見 [`ISSUES.md`](ISSUES.md) 頂部「🎯 未來大目標」。

### 可立即接手（autonomous-friendly，無設計歧義）

- [ ] **前端 component render 測試**（CostPage / FarmOverview / workflow Panel）—— 需先補 `vitest.config.ts` jsdom setupFiles + `npm i -D @testing-library/jest-dom`
- [ ] **WMOM-20260716-06** — 🔵 footprint CPU-torch pin（Dockerfile，DEC-20260716-02，image 砍半；本地無 docker，待部署環境驗）
- [ ] **WMOM-20260509-F6** — PostgreSQL row-lock integration test（M6 部署前，需 docker postgres）

### 需劉老師決策才能開工

- [ ] **WMOM-20260519-01** — `add_return` 超量退料 domain guard（需會計語意決策）
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
