# windMindOM — TODO（短期工作板）

> 用途：本檔案是「**這週 / 這個月**正在做什麼」的快速 dashboard。
> 詳細 issue 規格在 [`ISSUES.md`](ISSUES.md)；完整路線圖在 [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md)；
> M5/M6 大目標 epic 拆解在 [`ISSUES.md`](ISSUES.md) 頂部「🎯 未來大目標」區塊。
>
> 規則：
> - 只列「進行中 + 下一個要做」的事，**不列已完成**（done 的事看 git log + ISSUES.md）
> - 每次 session 開頭 / 結尾更新本檔
> - 大局看 ROADMAP；今日工作看 ISSUES.md；本週/本月節奏看本檔

最後更新：2026-09-22（專案檢視 + 追蹤文件真相對齊 — WMOM-20260922-01）

---

## 現況（2026-09-22）

- **M1-M4 全 done**；**M5 ~90%**（Knowledge/RAG 後端 + ChromaDB + 531-chunk Z72 向量檔 + `/field/`
  mobile Part A/B-1/B-2 全到齊；剩 M5-4「灌客戶手冊 + 一年警報 csv」需**客戶素材**，歸 M6 部署期）；
  **M6 ~25%**（auth 全面完成，剩 HTTPS 配置 + 下列 critical path）。
- **baseline 綠（2026-09-22 實跑）**：backend **1076 passed / 7 skipped / 1 xfailed**（1084 collected）；
  frontend vitest **957 passed / 48 files**、`tsc --noEmit` 0 error、`vite build` OK。
- **repo 乾淨**：HEAD `5555112`（#155），**開啟中的 PR 0 支**，working tree 無未提交變更。
  最後一次 code 變更是 2026-07-20 arc（#142-#152）；2026-09-01 之後僅對外素材 `promo/`。
- **時程提醒**：**距 M6（2026-10）剩約 1 週**。挑題準則：**對 M6 critical path 有貢獻優先**。
- **環境提醒**：新 sandbox 裝依賴需 `pip install --ignore-installed PyYAML -r requirements-dev.txt`
  （Debian 系統 PyYAML 會讓 pip 卡在 `RECORD file not found`）。

---

## 下一個 milestone — M6：第一個運維廠商 PoC + 第一筆合約（2026-10 target）

> Done criteria：客戶老闆說「下個月續用」+ 現場工程師 80% 警報走 RAG + 第一份月報沒被業主退件 + 收到合約金。
> 三個推進方案與論據見 [`work-logs/2026-09/2026-09-22-project-review-docs-sync.md`](work-logs/2026-09/2026-09-22-project-review-docs-sync.md) §3。

### 🥇 建議順序（依 M6 阻塞程度排）

1. [x] **WMOM-20260720-13** — ✅ A1 比較視圖 4 個 Should-fix（2026-09-22 done；code review
   0 Must / 2 Should 皆收 → Approve。frontend 957 → 970 passed）
   - ⚠ **殘留**：keep-alive 的 recharts 行為需在**真實瀏覽器**手動驗一次（趨勢↔機組比較來回切換後
     圖表真的畫出來而非空白，Safari/WebKit 優先）。jsdom 無 ResizeObserver → 無自動化測試可把關；
     失準時使用者看到空白圖表而非報錯。
2. [ ] **WMOM-20260720-04 + WMOM-20260720-08** — 🟡 **live/OPC 後端硬化（M6 現場部署唯一硬阻塞，2-3 天）**
   - -04(1) `DataBroker.stop()` 未呼叫 `_opc_adapter.stop()` → 切走 live 後孤兒 thread 續寫新 session
   - -04(2) 切走 live 無角色檢查（起 live 需 SUPERVISOR，不對稱）
   - -04(3) `config.py::set_simulation` 非即時模擬來源時靜默 `switch_mode` → **會悄悄斷掉 live SCADA**
     （#146 前端 gate 只是 best-effort，definitive fix 在後端）
   - -08(1) `start/stop/switch_mode` 全程無鎖 → 連點兩下可撞 `RuntimeError: cannot join thread before it is started`
   - -08(2) `simulator/engine.py:310` `time.sleep(time_step)` 不可中斷 → `stop()` 得等滿一拍
3. [ ] **WMOM-20260716-06** — 🔵 footprint CPU-torch pin（Dockerfile，DEC-20260716-02，image 砍半；需 docker 環境驗）
4. [ ] **WMOM-20260509-F6** — 🔵 PostgreSQL row-lock integration test（M6-3；需 docker postgres）
5. [ ] **HTTPS 部署配置** — 🔵 M6-4 唯一殘項（auth 本體已全數合入 #108-#122）

### 並行 — 情境比較分析 epic（DEC-20260720-02，demo 說服力）

- [ ] **A2 跨情境比較**（相對時間對齊）— epic 中 demo 價值最高的一塊；建議排在確定有客戶之後
- [ ] **PR C 檢視情境掛載 app**（最大，需先寫 broker 子設計）
- [ ] **PR D** `GuidedTourPage` 同款 remount 修
- [ ] **A3** 事件 session 化 / 匯出

### 並行 — 非 code（劉老師）

- [ ] **WMOM-20260503-05** — 🟡 Friendly 客戶接觸（infrastructure done；素材已備妥：
  `promo/windMindOM-intro-3min.mp4` 3 分鐘介紹影片 + pitch deck v0.8.1）。
  **沒有客戶就沒有 M6-1/M6-2** — 這條決定整個 M6 時程。
- [ ] **M5-4 客戶手冊擴充 + 一年警報 csv 灌入** — 需客戶素材，隨部署一起做

### 需劉老師決策才能開工

- [ ] **WMOM-20260519-01** — `add_return` 超量退料 domain guard（需會計語意決策）
- [ ] **WMOM-20260513-01** — UI 改版 v2（placeholder — 等劉老師補新設計交接書）

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
