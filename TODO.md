# windMindOM — TODO（短期工作板）

> ✅ **2026-09-23：CI runner 基礎設施確認恢復穩定**——2026-09-22 稍早（PR #157-#159）曾連續全數
> `runner_id: 0` 秒退失敗，19:20 UTC 起（PR #162 起）恢復正常跑測試。截至本次更新已累積連續 3 個
> PR（#162 / #163 / #164）真實跑完 CI 並自動 `auto-merge` 進 main，符合先前訂下的「連續 2-3 個
> session 都綠燈視為問題已解」門檻，故清除舊警語段落。**若日後再度出現同款秒退**（數秒內失敗 +
> `runner_id: 0` + check output 全空），因應方式：本機驗證（`pytest` + `vitest`/`tsc`/`build`）
> 為準、不等 auto-merge、不反覆重跑、PR 留言記錄一次即可，絕不可為了繞過 CI 直接 push main。
>
> 用途：本檔案是「**這週 / 這個月**正在做什麼」的快速 dashboard。
> 詳細 issue 規格在 [`ISSUES.md`](ISSUES.md)；完整路線圖在 [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md)；
> M5/M6 大目標 epic 拆解在 [`ISSUES.md`](ISSUES.md) 頂部「🎯 未來大目標」區塊。
>
> 規則：
> - 只列「進行中 + 下一個要做」的事，**不列已完成**（done 的事看 git log + ISSUES.md）
> - 每次 session 開頭 / 結尾更新本檔
> - 大局看 ROADMAP；今日工作看 ISSUES.md；本週/本月節奏看本檔

最後更新：2026-09-23（WMOM-20260923-02 — `FaultInjectionPanel` component render 測試：555 行的
`/admin` 故障模擬頁面元件先前零 component 測試，比照 `TrendChartPanel`/`SettingsPage` 範式（fetch
mock + fake timers）補上 40 測（PageHeader/注入參數 Fields/inject·clear all/活躍故障表/診斷
測試計畫卡片/執行測試計畫+結果卡/3s 輪詢與 unmount cleanup），frontend 1027→1067 passed，
backend 未動；`MaintenanceHub`/`FaultInjectionPanel` 同批 untested 大元件兩支皆已處理完畢。）
前一 session：WMOM-20260923-01 — `MaintenanceHub` component render 測試：439 行的
`/admin/maintenance` 頁面元件先前零 component 測試，補上 49 測（PageHeader/Filter/
WorkOrderTable 全欄位/RosterCard/WeekCalendar），frontend 978→1027 passed，backend 未動；
PR #164（WMOM-20260922-04）確認 auto-merge 成功，累積連續 3 筆 CI 綠燈樣本，已清除上方舊
CI 失效警語。
session #7：WMOM-20260922-04 — 情境比較分析 A2 Part 2 前端：
`ScenarioCompareAcrossView`（跨情境風場層 rollup 摘要並排）+ `ScenarioPage` 勾選/比較 UI，
frontend 961→978 passed（+17 新測，含開發中自行抓到並修正的 2 個真實 bug），backend 未動。
session #6：WMOM-20260922-03 的 PR #162 **CI 全綠、auto-merge
自動合併**（非人工）——CI runner 基礎設施疑似恢復，見上方新警語；本次僅更正追蹤檔案的 CI 狀態敘述，
無程式碼變更。session #5：WMOM-20260922-03 — 情境比較分析 A2 Part 1：跨情境
摘要並排端點 `GET /api/scenarios/compare`（DEC-20260720-02），backend 1094→1103 passed，frontend
未動；session #4：WMOM-20260922-02 — PR D：`GuidedTourPage` inline
component remount 修（DEC-20260720-01），frontend 960→961 passed；session #3：WMOM-20260720-13
A1 round-2 follow-up 4 個 Should-fix 全修（PR #157 merged）；session #2：WMOM-20260922-01
accelerated 模式 stop() 響應性收尾（PR #158 merged）；session #1：WMOM-20260720-04 + -08 live/OPC
後端硬化收尾——M6 現場部署唯一硬阻塞已清除。）

> ⚠ 本檔其餘內文（現況段落、下方清單）大多還停在 2026-07-18 的狀態快照，比 `STATUS.yaml` / `ISSUES.md`
> 舊很多（M5 已到 ~90%、M6 已到 auth+live/OPC 硬化完成）。下次整理 TODO 時建議整份對照 `ISSUES.md`
> 「🎯 未來大目標」區塊重寫，而非逐次小補丁——本 session 範圍只做 WMOM-20260922-03，不在此展開。

---

## 現況（2026-07，內容已過時，見上方提醒）

- **M1-M4 全 done**：monitoring（既有）+ cost（M2）+ workflow（M3-M4）+ reporting（M4）皆完成；**M5（Knowledge/RAG + 現場 mobile UI）進行中 ~75%**（主功能到齊，剩客戶手冊擴充 + 一年警報 csv 灌入，屬 M6 部署期）；**M6-4 auth 模組已完成**（JWT + RBAC + 全 router 授權已全面強制執行 + 前端真登入頁面與 AuthProvider已對接）。
- **baseline 綠**：backend 全套（6 module + monitoring/physics + e2e）→ **1103 passed / 7 skipped / 1 xfailed**；frontend vitest **1027 passed** / tsc 0 / vite build OK。CI runner 基礎設施已確認恢復穩定（見上方）。
- **節奏提醒**：autonomous 飛輪已重啟（每 3 小時），挑題準則為「對 M6 critical path 有貢獻優先」。

---

## 下一個 milestone — M5：Knowledge / RAG + 現場 mobile UI（2026-09 target）

> 目標：警報 → RAG 查 Z72 手冊 → 給現場工程師可操作的處置建議；現場 mobile UI 是 PMF 關鍵。
> Done criteria：現場工程師手機掃到警報，能查到對應手冊段落 + 處置步驟。

詳細 epic 拆解見 [`ISSUES.md`](ISSUES.md) 頂部「🎯 未來大目標」。

### 可立即接手（autonomous-friendly，無設計歧義）

- [ ] **前端 component render 測試**（jsdom setupFiles / jest-dom / CostPage / FarmOverview / workflow Panel / MaintenanceHub / FaultInjectionPanel 皆已補齊，同批 untested 大元件已全數處理完畢）—— ui primitives（`components/ui/*.tsx`）目前零 `__tests__`，尚未評估是否需要；`FaultInjectionPanel.test.tsx` review 留下的 `.parentElement` DOM 遍歷 scoping 技術債（見 ISSUES.md WMOM-20260923-02）可留待日後統一改用 `data-testid`
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
