# 2026-09-26 — WMOM-20260926-03：PR C Phase 1 實作（情境掛載唯讀端點 + FarmOverview/TurbineDetail 接線）

- **Issue**: WMOM-20260926-03（第六個 autonomous session）
- **Branch**: `claude/inspiring-mccarthy-5zk4cp`
- **Milestone**: M5（DEC-20260720-02 情境比較分析 epic 收尾，PR C 收尾）

## 背景

`WMOM-20260926-02`（設計定案，`DEC-20260926-01`）已把範圍切清楚：情境掛載＝與
`data_broker` 單一 active source 狀態機完全正交的唯讀端點 + 前端
`ScenarioMountContext`。本 session 是 Phase 1 實作本體，deliverable 已在 issue
寫清楚，直接照設計做，無需再重新調查。

## 本 session 做的事

### 1. 後端（`modules/monitoring/server/routers/scenarios.py` + `storage.py`）

- 新增 `Storage.scenario_turbine_ids(session_id)`：情境內出現過資料的機組 id 清單
  （`SELECT DISTINCT ... ORDER BY turbine_id`，字串排序＝數字排序，因 turbine_id
  皆 `WT{i:03d}` 固定寬度零填補）。
- 新增 `GET /api/scenarios/{id}/turbines`：該情境每台機組最後一筆讀數，格式對齊
  `TurbineReading`（重用 `get_history(limit=1, session_id=...)`）。
- 新增 `GET /api/scenarios/{id}/farm-status`：風場層 KPI，格式對齊 `FarmStatus`
  （在 `/turbines` 已算出的「每機組末筆讀數」之上套用與
  `data_broker.get_farm_status()` 相同的彙整邏輯，而非誤用
  `scenario_turbine_aggregates`——這正是 `WMOM-20260926-02` 設計審查時就已抓到並
  修正的 must-fix，本次照設計文字實作）。
- 兩者皆 `require_authenticated()`，情境不存在回 404。

### 2. 前端

- `contexts/ScenarioMountContext.tsx`（新）：`ScenarioMountProvider` + `useScenarioMount()`。
- `hooks/useScenarioMountData.ts`（新）：給定 scenarioId 一次性 fetch
  `/api/scenarios/{id}/turbines`，重用 `useRealtimeData.ts` 新匯出的
  `apiToTurbineData`/`ApiTurbineReading` 轉成 `TurbineData[]`（不 polling/WS，情境資料是
  凍結快照）。
- `components/ui/ScenarioMountBanner.tsx`（新）：「情境檢視中：{name}（唯讀）」常駐提示 +
  就地退出鈕。
- `ScenarioDetail.tsx`：新增「以此情境瀏覽總覽/機組細節」兩個入口，透過新
  `onMount` prop（`ScenarioMountRequest`）往上轉呼。
- `ScenarioPage.tsx`：新增 `onMountScenario` prop，單純轉呼給 `ScenarioDetail`。
- `App.tsx`：`ScenarioMountProvider` 掛載點；`handleMountScenario`（掛載 + 決定導覽到
  overview 或先記下待選機組 id、等資料到位後 effect 補選）；`effectiveTurbines`
  （掛載中改用情境快照，取代 `FarmOverview` 的 `turbines` prop 與 `liveTurbine`/
  自動選第一台的來源）；`handleNavSelect` 導覽到 overview/turbine 以外頁面時
  `scenarioMount.unmount()`。
- `FarmOverview.tsx`/`TurbineDetail.tsx`：掛載中顯示 banner；停用/替換所有寫入或即時資料
  入口——FarmOverview 的「匯出」鈕、farm-trend 趨勢圖 fetch；TurbineDetail 的
  header『限載/停機/安排檢查』三鈕、右欄 `OperatorControlCard`（整張換成停用說明卡，
  不只 disable 按鈕）、主圖 `TrendChartPanel`、AI 診斷卡的「派遣」鈕。
- `utils/turbineNaming.ts`（新）：`wtIdToTurbineIndex`，把 ScenarioDetail 選取的
  WT-id 換算成 `TurbineData.id`，供 App.tsx 在情境資料到位後找到對應機組。

### 3. 為何連 `OperatorControlCard`/`TrendChartPanel`/farm-trend 都要停用（設計判斷，非過度工程）

情境內機組 id（WT001, WT002, ...）與即時 simulator 的機組 id 共用**同一套命名**
（皆源自 `WT{i:03d}`）。若這些子面板在情境掛載中維持照常運作，它們會用
`turbineApiId = WT{同編號}` 打 `/api/control/*`、`/api/turbines/{id}/trend`、
`/api/turbines/farm-trend` 這些**即時**端點——使用者以為在唯讀檢視某個凍結情境，
實際上看到/能操作的是**剛好同編號的真實即時風機**。這是嚴重的資料錯置與潛在誤操作
風險，比「寫入按鈕忘記 disable」更隱蔽（因為 GET 輪詢會正常回應、畫面看起來正常）。
判斷：與其局部 disable 單一按鈕，不如整張卡片/整段主圖替換成停用說明，杜絕任何殘留
即時 fetch。

## code-reviewer subagent review（獨立審查，Async agent，46 tool calls）

跑 `code-reviewer` subagent 對完整 diff 做審查（含交叉核對 decision log / 子設計
work-log），抓到 **1 must-fix + 3 should-fix + 2 nice-to-have**，全數已修復並
mutation-verified：

1. 🔴 **Must-fix（已修復）**：**情境掛載後永遠無法回報 FAULT 狀態**——`_scenario_row_to_reading`
   只套用 `_map_state(operational_state)`，但 `simulator.engine._tur_state_to_str`
   的映射表結構上永遠不會產生 "FAULT"（即時路徑的 FAULT 覆寫靠的是記憶體內
   `FaultEngine` 當下狀態，批次生成完那份記憶體狀態就消失了，DB 也沒有為每筆
   reading 存 tripped 旗標）。本 session 獨立重讀 `_tur_state_to_str`（IDLE/
   STARTING/RUNNING/STOPPING 四種，無 FAULT 分支）+ `data_broker._sim_output_to_reading`
   （兩段式：先映射運轉狀態、再視 `fault_info` 是否 tripped 覆寫）確認 reviewer
   論述無誤——一個刻意注入故障的情境，掛載後會整面顯示「健康」，直接牴觸同一情境
   自己的「趨勢」頁籤看到的故障標記，是核心用途的正確性回歸。**修法**：新增
   `_tripped_fault_turbine_ids()` 純函式，依已持久化的故障注入事件（`history_events`，
   `event_type=="fault"`，含 payload 的 `severityRate`/`initialSeverity`）用與
   `FaultEngine.step()` **完全相同的公式**（`severity = min(1, initial + rate*elapsed)`，
   `tripped = severity >= FAULT_SCENARIOS[id].auto_trip_severity`）離線重算——不需要
   新 schema/欄位，重用既有已記錄資料。`_scenario_row_to_reading` 新增 `force_fault`
   參數，`_scenario_latest_readings` 算出 tripped 集合後逐機組套用（比照即時路徑的
   覆寫順序）。新增 8 個測試（2 個整合測試用真 `generate_bulk` 注入高/低嚴重度故障、
   1 個無排程回歸、5 個 `_tripped_fault_turbine_ids` 純函式測試涵蓋 dedup/時序/
   未知情境/缺欄位），皆 mutation-verified（拔掉覆寫邏輯 → 兩個整合測試如預期
   fail；把 dedup 改成「取第一次」→ dedup 測試如預期 fail）。
2. 🟡 **Should-fix（已修復）**：`turState=int(row.get("tur_state") or 6)` 用 `or`
   會把 storage 真實會存的 `0`（scada 缺 `WTUR_TurSt` tag 時的預設值）誤判成缺值、
   silently 捏造成 `6`（正常發電）。改用 `is not None` 判斷，新增 2 個 regression
   test（`tur_state=0` 保留 / 缺欄位才 fallback 6），mutation-verified。
3. 🟡 **Should-fix（已修復）**：`handleMountScenario` 的「瀏覽總覽」分支沒有清
   `pendingMountTurbineDataId`——若使用者先點「瀏覽機組細節」（設下待選 id）又在
   資料到位前改點「瀏覽總覽」，稍後補選 effect 仍會找到該 id 並強制導去
   TurbineDetail，蓋掉使用者最後一次「總覽」的選擇。已在該分支補
   `setPendingMountTurbineDataId(null)`。**誠實揭露**：App.tsx 無 render 測試基礎
   設施（既有限制，需 mock ~15 個子元件），此修復僅靠程式碼閱讀驗證，未能
   mutation-verify。
4. 🟡 **Should-fix（已修復）**：`useScenarioMountData` 的 `error` 算出來後從未浮現
   在畫面上——情境被刪除（404）或網路失敗時，banner 仍自信顯示「情境檢視中」卻是
   空資料，使用者無從得知哪裡出錯。**順便做了架構改善**：把 `useScenarioMountData`
   從 App.tsx 移進 `ScenarioMountContext` Provider 內部呼叫（單一 fetch 來源），
   `turbines`/`loading`/`error` 隨 context 一起分發，`FarmOverview`/`TurbineDetail`
   可直接讀 `error` 在 banner 顯示「載入這個情境失敗…」，不需要 App.tsx 額外 prop
   drilling。新增 9 個 context 測試（含 mock fetch 驗證 turbines/loading/error 正確
   隨 mount() 傳遞、unmount 後清空）+ 2 個 banner 錯誤顯示整合測試，皆
   mutation-verified。
5. 🟢 **Nice-to-have（已採納）**：`handleOpenDispatchModal` 補一道獨立防線
   （`if (scenarioMount.mounted) return;`）——派遣目前唯一入口已在 TurbineDetail
   disabled，但不依賴呼叫端自律，避免未來新增派遣入口忘記檢查。
6. 🟢 **Nice-to-have（已採納）**：`_scenario_row_to_reading` 的 turbine_id 格式異常
   時補 `logger.warning`（原本靜默 fallback 成 idx=1，會與真正的 WT001 撞名）。

Reviewer 也核實通過（無問題）：`scenario_turbine_ids` 的 DISTINCT+ORDER BY 對
`WT{i:03d}` 固定寬度零填補是安全的字串排序＝數字排序；`get_history(limit=1,...)`
正確依賴 `ORDER BY timestamp DESC`；404 處理與 N+1 查詢模式如設計文件所接受；
`CurtailModal`/趨勢圖/匯出/`OperatorControlCard` 在所有掛載渲染路徑上都正確替換掉。

## 自我測試

- backend：`python -m pytest modules/workflow/tests/ modules/cost/tests/
  modules/reporting/tests/ modules/knowledge/tests/ modules/monitoring/tests/
  modules/auth/tests/ tests/ -q`
  → **1255 → 1274 passed**（+19，7 skipped, 1 xfailed，零 regression）
- frontend：`npx tsc --noEmit`（0 error）+ `npx vitest run`（**1402 → 1443
  passed**，65→68 files，+41，零 regression）+ `npx vite build`（OK）

## Mutation-verify 記錄

逐項對關鍵修復做「改回舊邏輯 → 確認新測真的會 fail → 再還原」：
- 後端 `_map_state()` 狀態映射（若省略會 pydantic `ValidationError`）
- 後端 farm-status 彙整（若改成 `len()` 而非 `sum(powerOutput)`）
- storage `scenario_turbine_ids` 的 DISTINCT（若拿掉會回重複列）
- **FAULT 覆寫邏輯**（拔掉 `force_fault` 套用 → 整合測試如預期 fail，證實重現了
  reviewer 描述的回歸）
- **dedup 取最後一次注入**（改成「取第一次」→ dedup 測試如預期 fail）
- `turState` 的 `is not None` 判斷（改回 `or 6` → `tur_state=0` 測試如預期 fail）
- 前端 `OperatorControlCard`/`TrendChartPanel` 條件式替換（拿掉 `mounted` 分支 →
  對應測試如預期 fail）
- 前端 header 三鈕 `disabled` prop（拿掉 → disabled 斷言如預期 fail）
- 前端 farm-trend/export 停用（拿掉 disabled guard → 對應測試如預期 fail）
- 前端 banner 錯誤顯示區塊（拿掉 → `role="alert"` 斷言如預期 fail）
- `wtIdToTurbineIndex` 正規表達式簡化（`/^WT0*(\d+)$/` → `/^WT(\d+)$/`）：
  mutation 測試證實兩者行為完全等價（`\d+` 貪婪匹配已隱含吸收零填補，`Number()`
  解析零填補字串結果相同）——**不是可忽略的假陰性，而是抓出原正則表達式的
  `0*` 前綴本身就是死碼**，已採用簡化版本並在程式碼與測試中說明。

全部 backup/restore 走 `cp` 到 scratchpad 外的 `/tmp` 暫存（非 `git checkout`），
每次還原後重跑對應測試檔確認回到全綠再進行下一項。

## 誠實揭露

- **App.tsx 本身無 render 測試基礎設施**（既有限制，需 mock ~15 個子元件，多個
  過往 session 已多次記錄同一限制）。本 session 新增的 `handleMountScenario`、
  `handleNavSelect` 的 `scenarioMount.unmount()` 清空邏輯、`liveTurbine`/
  `effectiveTurbines` 衍生、`handleOpenDispatchModal` 的 mounted guard，皆僅透過
  程式碼閱讀 + 獨立驗證邏輯正確性，未能用自動化測試鎖住。`wtIdToTurbineIndex`
  已抽成純函式獨立測試以縮小這塊無保護範圍，但呼叫端（`handleMountScenario`
  如何使用其結果）仍在無保護區。
- **前端刻意不消費新的 `GET /api/scenarios/{id}/farm-status` 端點**：`FarmOverview`
  的風場層數字本來就從 `turbines` prop 自行加總（既有 live 路徑也從未呼叫
  `/api/turbines/farm-status`），與新端點算出的數字理論上一致，多打一次 API 是
  純粹的重複往返。該端點仍完整測試於後端（10 個測試涵蓋整合/404/彙整自洽），
  供未來若有獨立風場層查詢需求時使用。
- **FAULT 重算依賴 `history_events` 的既有時間窗限制**：該表無 `session_id`
  欄位（`DEC-20260719-01` 已知 trade-off），事件靠情境模擬時間窗撈取，短時間內
  連續產生的情境可能混入其他情境的事件——本次的 tripped 重算繼承這個既有限制，
  非本次新引入的風險，與 `/summary`、`/turbines/{id}/history` 端點的
  `eventsByTimeWindow` 旗標是同一份技術債。
- **N+1 查詢模式**（`_scenario_latest_readings` 對每台機組各跑一次
  `get_history(limit=1,...)`）維持設計文件標註的 nice-to-have、非本次強制範圍；
  `_tripped_fault_turbine_ids` 目前對每台機組各重算一次完整 tripped 集合（可优化
  但相對成本低，未優化）。

## 下次接手

`WMOM-20260926-03` 三個 deliverable（後端 2 端點 + 前端 Context + 兩頁接線）皆已
完成，issue 標 done。`DEC-20260720-01`/`DEC-20260720-02` 的 PR C 至此完整收尾
（Phase 1 唯讀掛載）；Phase 2（工單/維護 what-if 演練）維持明確 deferred，未評估。

下個 session 可選：M6 critical path 剩餘項（`WMOM-20260716-06` footprint 已完成；
`WMOM-20260509-F6` PostgreSQL row-lock 仍卡「是否選 PostgreSQL」需劉老師決策；
HTTPS 部署配置需先定部署目標/憑證策略）、物理模型強化
WMOM-20260505-23~28（學術深度，非商業 must-have），或見 ISSUES.md「需劉老師決策」
清單。
