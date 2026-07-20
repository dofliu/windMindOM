# 2026-07-19 — 啟動 gate：開機不自動跑、登入後選資料來源｜DEC-20260719-01 #3

> Session 類型：#3（承 #4 完成；DEC-20260719-01 交付分階段 3，收尾整個 Scenario 實測 follow-up）
> 產出：本 PR（後端 idle 開機 + /api/source + 前端 SourceSelectPage gate）
> 對應 issue：WMOM-20260719-04｜DEC-20260719-01

---

## 做了什麼

用戶回報「一進系統就自動以預設風場模擬直接產生資料」。用戶選 **A（專用模式選擇頁）**。

1. **後端開機 idle**（`app.py` lifespan）：不再 `broker.start(SIMULATION)`——開機只確定 farm、
   起 WS loop，**不啟動任何來源、不建 simulator、不產資料**。新增模組函式
   `activate_simulation()` / `activate_live()` / `_stop_modbus()` 供 router 呼叫（把原 lifespan
   的 sim + spec + Modbus 啟動邏輯移入，可重入：切換來源會先停舊 Modbus 再 switch_mode）。
2. **broker 狀態機**（`data_broker.py`）：加 `_source_active` / `_source_kind`（simulation / live /
   view / None）+ `source_active` / `source_kind` property；`start()` 設、`stop()` 清；新增
   `select_view_only()`（標記已選但**不起任何來源**——調閱過去情境只讀 storage，避免又產資料）。
3. **`/api/source` router（新）**：`GET /status`（前端據此決定是否顯示選擇頁）、
   `POST /select {simulation|live|view}`（授權 require_authenticated——登入後選來源是含現場工程師的
   必經入口）。
4. **前端 SourceSelectPage（新）**：四卡全屏選擇頁（實接 / 即時模擬 / 產生新情境 / 調閱過去情境）。
   `App.tsx` 加 `sourceActive` 狀態 + 查 `/api/source/status`（依 `auth.isAuthenticated` 重查）+
   早 return gate（null→載入中 / false→選擇頁 / true→dashboard）+ `handleSelectSource`（四卡映射
   到 mode + 目標 view：observe→view+情境頁、scenario→simulation+情境頁、live→live+總覽、
   simulation→simulation+總覽）；401 未登入 → authClient 彈登入頁，登入後重查。
5. **測試**：後端 `test_source_selection.py` 7（狀態機 + 端點 + enforce 需登入）；前端
   `SourceSelectPage.test.tsx` 5。monitoring **96** / 前端 **913** / tsc / build 全綠。
6. **端到端 verify**（真 app + TestClient lifespan）：開機 `source_active=False`、`simulator=None`
   （不自動產資料）；select view → active，simulator 仍 None；overview 在 view 模式回空不崩；
   未知 mode → 400。全通過。

## 眉角 / 決策

- **blast radius ~0**：查過既有測試——`test_monitoring_routers_auth` 自建 app（不跑 lifespan）；
  e2e 用**裸 `TestClient`**（不跑 lifespan）且 mock simulator。故「開機不自動起 sim」不破壞既有測試。
- **view 模式不起 sim**：調閱過去情境只讀 storage（session 隔離），不需要跑 simulator——若又起
  sim 就等於違反「不自動產資料」的初衷。overview 在 view 下自然為空（`get_all_turbines` 已防呆回 []）。
- **select 授權放寬到 require_authenticated**：兩個 persona（管理層 + 現場工程師）登入後都要選來源；
  用 SUPERVISOR 會擋住現場工程師。selection 是全域（單 broker），屬單租戶假設，未來多租戶再收緊。
- **gate 依 source 狀態、非 auth**：前端 auth 過渡期仍可未登入操作；gate 直接依
  `/api/source/status`，enforce 下 401 由 authClient 彈登入頁銜接。

## 卡在哪 / 下次怎麼接手

- **本 PR（#3）**：draft + `hold`（待 review）→ 收 review → 移除 hold → flywheel 自動合。
  合併後 **DEC-20260719-01 三階段全完成**、整個「Scenario 上線實測 follow-up」收尾。
- 後續可選：`activate_live` 目前只接 OPC DA；Modbus-client 對接、多來源並存、view 模式的 UX 微調
  （如 header 標「唯讀情境檢視」）可另案。
