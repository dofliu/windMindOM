# 2026-09-26 — PR C（情境掛載 app）子設計

- **Issue**: WMOM-20260926-02（本 session，設計）+ WMOM-20260926-03（開新 follow-up，Phase 1 實作，open）
- **Branch**: `claude/inspiring-mccarthy-dwa9kf`
- **Milestone**: M5（DEC-20260720-02 情境比較分析 epic 收尾）

## 背景

`WMOM-20260926-01` 三項全數完成後，`ISSUES.md`/`TODO.md` 清點下一個「可立即接手」項目只剩
**PR C — 檢視情境掛載 app**（DEC-20260720-01 §3、DEC-20260720-02 A2 epic 最後剩餘項目）。
這一項從 2026-07-20 立案至今，已被至少 8 個 session（WMOM-20260922-03/04、
2026-09-25 系列等）在 work-log 寫「維持前次 session 的候選清單不變」原地punt，
從未真正動工，原因是 decision log 原文自己說「動核心來源模型，最重的一塊，實作前另寫子設計」，
且留了一個從未解決的語意問題：「`view` 是否升級成『載入某情境到全 app』，或另立 kind？」

## 本 session 做的事

**先用 Explore agent 徹底讀過現況**（`data_broker.py` 全文 1053 行、`routers/source.py`
全文、`routers/turbines.py`、`app.py` WS broadcast、`decision_log.md` DEC-20260720-01/-02
全文、`ScenarioPage.tsx`/`App.tsx` 導覽），確認：

1. `DataBroker` 只有**單一 active source** 模型（`self.simulator` + `source_kind`）；
   `get_all_turbines()`/`get_turbine()`（data_broker.py:654-685）硬性要求
   `mode == SIMULATION and self.simulator`，`view` mode 故意讓兩者回空——今日情境資料
   **完全走另一條、與 turbines 路由平行的 `session_id` 隔離 storage 查詢**（`/api/scenarios/{id}/summary`、
   `/turbines/{tid}/history`），兩條路徑目前零交集。
2. `FarmOverview`/`TurbineDetail`/`MaintenanceHub` 這些主頁面全部直接吃 broker 的 live 狀態
   （REST `/api/turbines*` + WS），沒有任何「資料來源可替換」的既有抽象層可插。
3. Decision log 原文設想的方案（「broker 新增情境檢視來源狀態」）會直接動到
   `DataBroker` 的 `_lifecycle_lock`／單一 active source 假設——這正是
   `WMOM-20260720-04`/`-08` 剛花一整個 session 才硬化好的並發關鍵區（見該 issue 的
   4×30 併發壓測）。在同一塊已知脆弱的核心狀態機上疊加新語意，風險與既有投資直接衝突。

## 設計決策（DEC-20260926-01，已寫入 `docs/product/decision_log.md`）

**拒絕原案**（broker 新增來源狀態 / 升級 `view` mode），改採**與 broker 狀態機完全正交**
的方案：

1. **`view` mode 語意不變**（仍是「調閱過去情境」的既有 ScenarioPage 系列用法，
   不升級、不擴充）。
2. **新增 2 個唯讀、`scenario_id` 隔離的端點**（純附加，不碰 `data_broker.py`/`source.py`
   既有程式碼一行）：
   - `GET /api/scenarios/{id}/turbines` — 每台機組最後一筆 reading，格式對齊既有
     `TurbineReading`（重用 `get_history(limit=1, session_id=...)` 取末筆的既有模式）。
   - `GET /api/scenarios/{id}/farm-status` — 風場層 KPI，格式對齊既有 `FarmStatus`
     （重用 `scenario_turbine_aggregates` 既有聚合）。
3. **前端用獨立 `ScenarioMountContext`**（非新 `/api/source/select` mode）：
   `ScenarioDetail` 提供「以此情境瀏覽總覽/機組細節」入口 → 導覽到 `FarmOverview`/
   `TurbineDetail`，該 context 有值時兩頁改吃上述新端點、停用 WS 訂閱（情境資料不會變）、
   頁面頂部常駐「情境檢視中：{name}（唯讀）」banner、**所有寫入操作一律停用**
   （curtail/dispatch/新工單...按鈕 disabled + tooltip）。與目前是否有 live/simulation
   在跑**正交**（不互斥、不需要「先退出 live」）。
4. **分階段範圍**：本設計只批准 **Phase 1**（唯讀掛載，FarmOverview + TurbineDetail 兩頁）。
   Decision log 原文「工單/維護在這份資料上演練」（讓使用者在情境資料上建立/操作工單做
   what-if 演練）**明確歸為 Phase 2，本次不評估、不批准**——這需要 workflow 模組加
   `scenario_id` 隔離（`work_order` 表目前無此概念）+ 全新語意決策（演練工單算不算真工單、
   能不能轉正），是完全獨立的更大設計題。MaintenanceHub/ReportsPage/CostPage 併入掛載
   模式也不在 Phase 1 範圍（這些頁面已有自己的 farmId/dataset selector 機制）。

完整理由 + 拒絕原案的具體風險分析寫在 `docs/product/decision_log.md` `DEC-20260926-01`。

## 產出

- `docs/product/decision_log.md`：新增 `DEC-20260926-01`。
- `ISSUES.md`：`WMOM-20260926-02`（本 issue，done）+ 新開 `WMOM-20260926-03`
  （Phase 1 實作，open，deliverable 已寫清楚：2 後端端點 + `ScenarioMountContext` +
  兩頁面接線 + banner + 寫入停用 + 測試，供下個 session 直接接手，無需再讀一次
  decision log 或重新調查）。
- 本 work-log。

**未做**：任何程式碼變更（本 session 純設計/文件）。backend/frontend 皆維持
baseline 不變（見下）。

## 自我測試（baseline，無程式碼變更故僅需確認未退步，未重新 mutation-verify 任何東西）

- backend: `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ modules/knowledge/tests/ modules/monitoring/tests/ modules/auth/tests/ tests/ -q`
  → **1255 passed, 7 skipped, 1 xfailed**（與 STATUS.yaml 上次記錄一致，零變化）
- frontend: `npx tsc --noEmit`（0 error）+ `npx vitest run`（**1402 passed, 65 files**）+
  `npx vite build`（OK）→ 與上次記錄一致，零變化

## 誠實揭露

- 本 session 完全沒有寫測試/程式碼，是 docs-only PR——按 CLAUDE.md §6.3「動到架構/改變
  方向」規則走完整 decision log 流程，但**沒有**因此免除下一個實作 session 仍需自行
  mutation-verify 新增的 2 個端點 + 前端接線。
- Explore agent 的探勘結論（單一 active source 模型、無既有可插抽象層）是本設計決策的
  事實依據，已交叉核對其引用的檔案/行號（`data_broker.py:654-685`、`select_view_only`
  364-385、`routers/source.py` 全文、`routers/turbines.py` 開頭）與本 session 自己讀
  `routers/scenarios.py` 全文（438 行）的結果一致，未發現矛盾。
- 「與 broker 狀態機正交」的判斷是本 session 的工程取捨，非劉老師拍板——如果劉老師認為
  情境掛載**應該**要能影響/替代目前的 live 顯示（而非平行共存），需要回頭修正本設計，
  已在 decision log 條目末段列出這個備選方案與其取捨供劉老師否決/確認。

## 下次接手

**優先接手 `WMOM-20260926-03`**（Phase 1 實作，deliverable 已在 issue 條目寫清楚，
無設計歧義，預期單 session 可完工）。其餘候選：`WMOM-20260509-F6`（PostgreSQL row-lock，
仍卡「是否選 PostgreSQL」需劉老師決策）、HTTPS 部署配置（需先定部署目標/憑證策略）、
物理模型強化 WMOM-20260505-23~28（學術深度，非商業 must-have）。
