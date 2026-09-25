# 2026-09-25 — WMOM-20260505-22 定檢排程（InspectionSchedule + scheduler auto-spawn）

> Session 類型：實作
> Session 長度：長
> 主導：autonomous worker（cron）
> 結果：完成（後端；前端 wiring 拆成新 issue WMOM-20260925-05，見 §4）

---

## 1. Session 目標

Preflight：`git status` clean（分支 `claude/inspiring-mccarthy-abc6xh`，環境注入，與 origin/main
同一 commit `81a1777`）；`mcp__github__list_pull_requests(state=open)` 回傳空陣列，無殘留 open
PR、無 stack 衝突。

Baseline 自我測試全綠（與既有基準完全一致）：
- backend：`pip install --ignore-installed PyYAML -r requirements.txt -r requirements-dev.txt`
  → `python -m pytest`（6 module + `tests/`）→ **1103 passed, 7 skipped, 1 xfailed**。
- frontend：（見下方 Verify，baseline 沿用前次 1288 passed / 60 files）

依決策樹挑題：M6 critical path（-04/-08/-06）已全數完成；情境比較 A2 epic 全完成；PR C 需先寫
broker 子設計、非單 session 可清楚定義範圍；`WMOM-20260507-02` 清單僅剩 sub-task d（風機細節
『安排檢查』），卡在依賴 `WMOM-20260505-22`（inspection_schedule）尚未做。掃過 ISSUES.md 全部
open issue（10 項）：`WMOM-20260504-11`（event-driven cost ledger，2-3 天、需劉老師 tariff/
revenue 假設決策）太大且有設計歧義；`WMOM-20260505-21`（day_work_form）與本次同批但範圍獨立；
`WMOM-20260509-F6`（PostgreSQL row-lock）已標🟡需劉老師決策；`WMOM-20260505-24~28`（物理模型）
park；`WMOM-20260513-01`（UI v2）等設計交接書。**選定 `WMOM-20260505-22`**——design 已在 DN-01
walkthrough Q7（2026-05-05 劉老師確認）resolve，無設計歧義，且直接解開一個已連續 ~10 個
session 記錄「持續卡著」的長期 blocker（`WMOM-20260507-02` sub-task d）。

範圍界定（開工前決定）：完整做後端（domain + ORM + repository + service + router + 73 個
test，mutation-verified），**前端頁面與 sub-task d 的按鈕接線留給下次 session**——issue 原估
「1-1.5 工作天」對應的是「domain+service+router+frontend 全套」，本次判斷後端本身已是一個可
獨立驗收、可獨立測試的完整交付（reviewer 也會驗），frontend wiring 待後端穩定進 main 後另開。

## 2. 實際完成

### 2.1 主要工作

**Domain（`modules/workflow/domain/inspection_schedule.py`，新檔）**：
- `Recurrence` enum（`monthly`=30天 / `quarterly`=91天 / `semi_annual`=182天 / `annual`=365天 /
  `custom_days`=任意天數）
- `recurrence_interval_days()` / `compute_next_due()` 純函式（UTC-aware datetime 驗證）
- `InspectionSchedule` dataclass（沿襲 `WorkOrder` 命名慣例）+ `is_due(as_of)` helper

**ORM + Repository（`repository/inspection_orm.py` + `inspection_repository.py`，新檔）**：
- `InspectionScheduleORM`（`wmom_inspection_schedules` 表，2 個複合 index）
- `InspectionScheduleRepository`：`create` / `get` / `list`（含 `due_only` + `active_only` 過濾）
  / `update_metadata` / `set_active`（軟刪除慣例，比照其他 workflow entity）/ `record_spawn`
- 共用 `work_order_repository.py` 的 engine cache（沿襲 `InventoryRepository` 做法，避免同一
  farm DB 開兩條 connection pool）

**Service（`services/inspection_scheduler.py` + `services/__init__.py`，新增此 package）**：
- `run_inspection_scheduler(inspection_repo, work_order_repo, farm_id, as_of=None)`：找到期排程
  → `WorkOrderRepository.create(type=INSPECTION)` → `record_spawn` 推進 `next_due_at`
- 冪等設計：spawn 成功後立刻推進 `next_due_at`，同週期內重複呼叫不重複 spawn
- 撞 multi-WO constraint（`BusinessRuleViolation`，風機 OPEN 工單已滿 3 張）時 log warning 並
  跳過，**`next_due_at` 不推進**——下次呼叫會重試，不會悄悄漏掉這次定檢
- 刻意不加背景 thread/cron（見 module docstring）：本次範圍是手動觸發 API，比照 reporting/cost
  既有「on-demand 觸發」慣例，避免重蹈 WMOM-20260720-04/-08 那類背景執行緒生命週期硬化債

**Router（`routers/inspection_router.py`，新檔，7 endpoints）**：
- `POST/GET /api/workflow/inspection-schedules`、`GET/PATCH /{id}`、
  `POST /{id}/activate`、`POST /{id}/deactivate`、`POST /run-scheduler`
- 角色：CRUD（create/update/activate/deactivate）= LEADER/SUPERVISOR（比照派工權限）；
  list/get = 任何登入者；`run-scheduler` = SUPERVISOR only（會真的建工單，權限比查詢/更新更高）
- 註冊進 `modules/monitoring/server/app.py`（`app.include_router(inspection_router)`）

**Schemas（`schemas/inspection_schemas.py`，新檔）**：
- `CreateInspectionScheduleRequest`（`custom_days` 缺 `interval_days` → 422，`model_validator`
  提早擋，訊息比 domain ValueError 更明確）、`UpdateInspectionScheduleRequest`、
  `InspectionScheduleResponse`、`RunSchedulerResponse`

**Tests（4 新檔，79 tests，全數 mutation-verified）**：
- `test_inspection_schedule_domain.py`（22 tests）：純函式 + `is_due` 邊界（`<=` 而非 `<`）
- `test_inspection_repository.py`（30 tests）：CRUD + `due_only` 查詢 + `record_spawn` 推進基準 +
  must-fix regression（見 §2.3）
- `test_inspection_scheduler.py`（11 tests）：spawn / 冪等 / multi-WO constraint 跳過不推進 /
  多筆 / 跨 farm 隔離 + must-fix 第三層防禦
- `test_inspection_router_auth.py`（16 tests）：CRUD HTTP 層 + enforce=false 過渡期放行 +
  enforce=true 角色閘門（LEADER/SUPERVISOR vs SUPERVISOR-only run-scheduler）+ must-fix 422

**`__init__.py` wiring**：`domain/__init__.py`、`repository/__init__.py`、`schemas/__init__.py`、
`routers/__init__.py` 四處新增 export；`modules/monitoring/server/app.py` 註冊新 router（確認
`GET /openapi.json` 顯示全 7 個 endpoint，app 正常 boot，無 route 順序衝突）。

### 2.2 Code review 修復（must-fix，見 §Review 詳細）

code-reviewer subagent 抓到 **1 個 must-fix**（獨立寫 repro script 實測重現，不是憑空推測）：
`UpdateInspectionScheduleRequest`（PATCH）沒有像 `CreateInspectionScheduleRequest` 一樣驗證
「`recurrence=custom_days` 必須帶 `interval_days`」，可以把一個 `MONTHLY` 排程 PATCH 成
`custom_days` 卻不給 `interval_days`，靜默寫入無效狀態；等 scheduler 下次到期，
`work_order_repo.create()` 先成功建了真實工單，`record_spawn()` 才 raise `ValueError`（未被
catch）——工單已建但 `next_due_at` 沒推進，變成每次呼叫 `run-scheduler` 都重複 spawn 一張新
工單 + 500。reviewer 用 repro script 實測到「兩次呼叫 → 兩張重複工單 + 兩次 500」。

修法（三層防禦，全部補齊）：
1. `InspectionScheduleRepository.create()`：`recurrence_interval_days()` 驗證改成**無條件**
   呼叫（原本只在沒帶 `first_due_at` 才會經過 `compute_next_due` 順便驗證，帶了明確
   `first_due_at` 會繞過）——對應 reviewer 抓到的 should-fix。
2. `InspectionScheduleRepository.update_metadata()`：commit 前用**合併後的最終狀態**驗證
   （必須在 repository 層，因為 schema 層看不到資料庫現有欄位，PATCH 只帶 `interval_days`
   沿用既有 `custom_days` 是合法的，schema 層無法單獨判斷）；`inspection_router.py` 的
   `update_inspection_schedule` 新增 `except ValueError` → 422。
3. `run_inspection_scheduler()`：在建工單前先驗證排程的 recurrence 組合合法，無效直接跳過
   （不建工單、不推進 `next_due_at`）——這是最後一道防線，防的是「未來任何繞過 repository
   公開 API 直接寫 DB」的路徑（例如手動 migration/管理工具），不只是本次兩個 endpoint。

新增 6 個 regression test（repository 3 + scheduler 1 + router 1 + repository 正向案例 1），
逐一 mutation-verified（改回沒有驗證的版本 → 對應新測 fail，其中 scheduler 層的 mutation
精確重現了 reviewer repro script 的同一個 `ValueError` traceback），還原後重跑全套零
regression。

### 2.3 卡住或延後的事

**前端 wiring 留給下次**（本次刻意範圍界定，見 §1）：
- `WMOM-20260507-02` sub-task d（`TurbineDetail.tsx` header『安排檢查』鈕）仍待接線——
  現在依賴已解除（`inspection_schedule` API 已存在），但按鈕本身「跳到 /maintenance + 預填
  turbine 與 inspection scenario」的前端邏輯本次未做
- `/admin/workflow/inspection` 定檢計畫管理頁（列表 + 建立 + 編輯）未做——目前只有後端 API，
  現場/管理層還沒有 UI 可以直接建立定檢計畫
- `run-scheduler` 目前無背景排程呼叫（純手動觸發 API），若要做到「真正自動化」需要外部 cron 或
  未來評估背景排程框架——本次刻意不做（見 service module docstring 理由）

### 2.4 重大決策（如有）

**範圍切割：後端優先，前端另開**——本次未寫進 `decision_log.md`（非架構層級變動，是單一 issue
內的「先做後端再做前端」排序決策，且 issue 本身在 ISSUES.md 已標記清楚哪部分完成）。

**不加背景排程框架**——`run-scheduler` 設計為手動觸發 API 而非背景 cron/thread，理由記在
`services/inspection_scheduler.py` module docstring：(1) repo 目前無 APScheduler 等排程框架；
(2) reporting/cost 模組既有週期性彙總也都是 on-demand 觸發模式，與此設計一致；(3) 避免重蹈
WMOM-20260720-04/-08 那類「多一條背景執行緒就多一類生命週期硬化債」的覆轍。未來若要做到真正
自動觸發，可用 OS-level cron 呼叫這支 API，不需要應用層再造一套排程機制。

## 3. 產出清單

見 §2.1/§2.2 逐檔清單。共新增 7 個 production 檔案（domain 1 + repository 2 + services 2 +
schemas 1 + router 1）+ 4 個 test 檔（79 tests）+ 5 個既有檔案的 wiring 修改（4 個 `__init__.py`
+ `app.py`）。

## 4. 給下個 session 的話

- **`WMOM-20260505-22` 後端已完成**，`WMOM-20260507-02` sub-task d 的依賴已解除，但**前端仍未
  接線**——下次可接手：(a) `TurbineDetail.tsx` header『安排檢查』鈕接線（sub-task d 本體）；
  (b) 定檢計畫管理頁（列表/建立/編輯，目前完全無 UI）。兩者可以是同一 session 或分開。
- 新 API 一覽（供前端串接參考）：
  - `POST /api/workflow/inspection-schedules`（LEADER/SUPERVISOR）
  - `GET /api/workflow/inspection-schedules?farm_id=&turbine_id=&active_only=`（任何登入者）
  - `GET/PATCH /api/workflow/inspection-schedules/{id}`
  - `POST /api/workflow/inspection-schedules/{id}/{activate|deactivate}`
  - `POST /api/workflow/inspection-schedules/run-scheduler?farm_id=`（SUPERVISOR only）
- **未受自動化測試保護的部分**：無（本次純後端，79 tests 涵蓋 domain/repository/service/router
  四層，皆 mutation-verified；FastAPI app boot + route 註冊用 `GET /openapi.json` 人工核對過，
  非自動化測試涵蓋，但風險低——純 wiring，且既有 6 個 module 的全套 backend test 本身就是
  「app 能 import 成功」的間接驗證，因為部分 test 走真實 app import 路徑）。
- **給下次 review 的提醒**：code-reviewer 這次抓到的 must-fix 根因是「schema 層驗證（create）
  沒有同步到 repository 層（update）」——本次修法刻意把驗證下沉到 repository（三層防禦），
  未來若再加其他「有互相依賴欄位」的 entity，記得從一開始就在 repository 層做合併後驗證，
  不要只靠 schema 層 `model_validator`（它看不到資料庫現有狀態，天生只能擋「單次 request 內部
  不一致」，擋不住「這次 PATCH 沒問題、但合併既有資料後才有問題」的情況）。

## 5. Open questions（park）

- 是否需要在 M6 部署前決定「真正自動觸發 run-scheduler」的機制（OS cron 呼叫 API vs 應用層排程
  框架）？本次刻意不做決定，留給部署規劃階段（HTTPS 配置那批工作）一併考慮。

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline：backend `1103 passed, 7 skipped, 1 xfailed`；frontend `npx tsc --noEmit` 0
  error、`npx vitest run` **1288 passed**（60 files）、`npx vite build` OK（沿用前次數字，
  本次全套重跑確認一致，frontend 零變更）。
- 新增後（第一輪，review 前）：backend `1176 passed, 7 skipped, 1 xfailed`（+73 新測，零
  regression）。
- must-fix 修復後（第二輪，最終）：backend **1182 passed, 7 skipped, 1 xfailed**（+79 新測
  總計，零 regression）；frontend 未動，`1288 passed`（60 files）不變、tsc 0、build OK。
- app boot 驗證：`GET /openapi.json` 確認 7 個 inspection-schedule endpoint 皆正確註冊，
  method/path 無 route 順序衝突（`run-scheduler` 與 `{schedule_id}` 同路徑深度但方法不同，
  reviewer 也獨立用 `router.routes` dump 驗證過同一結論）。
- **Mutation-verified**（`cp` 備份 + md5sum 核對還原，非 `git checkout`，因新檔為 working tree
  未追蹤檔案）：**共 7 處關鍵邏輯**逐一改回錯誤版本確認對應測試如預期 fail，還原後 md5sum 核對
  與備份一致，重跑全套零 regression：
  1. `InspectionSchedule.is_due` 邊界 `<=`→`<`：`test_is_due_true_when_exactly_at_boundary` fail
  2. `record_spawn` 推進基準改用舊 `next_due_at` 而非 `spawned_at`：
     `test_record_spawn_advances_next_due_at` + `test_record_spawn_uses_spawned_at_not_old_due_date`
     + scheduler 層 2 個依賴測試 fail
  3. scheduler 撞 `BusinessRuleViolation` 時移除 `continue`（改繼續往下跑）：
     `test_skips_schedule_when_turbine_already_has_max_open_work_orders` fail（`UnboundLocalError`）
  4. `run-scheduler` role gate 從 `require_role(SUPERVISOR)` 改成 `require_authenticated()`：
     `test_run_scheduler_enforced_leader_403` fail（LEADER 變成可通過）
  5.（must-fix 修復）`create()` 移除無條件驗證 → `test_create_custom_days_requires_interval_
     even_with_explicit_first_due_at` + `test_update_metadata_custom_days_without_interval_
     raises`（後者連帶失敗，因為兩處驗證邏輯有共用路徑）fail
  6.（must-fix 修復）`update_metadata()` 移除合併後驗證 → 上述同一測試單獨 fail（`DID NOT
     RAISE ValueError`）
  7.（must-fix 修復）scheduler 移除第三層防禦檢查 → `test_skips_schedule_with_invalid_
     recurrence_config_without_crashing` fail，且 traceback **精確重現 reviewer repro script
     的同一個 `ValueError`**（`record_spawn` → `compute_next_due` → `recurrence_interval_days`
     未擋住），證實修法真的堵住 reviewer 發現的那個洞，不是修了另一個問題
  8.（must-fix 修復）router `update_inspection_schedule` 移除 `except ValueError` → 422 對應
     測試 fail，實際回應變成未處理的 500（`test_update_metadata_custom_days_without_interval_
     422`）

## Review

code-reviewer subagent（獨立跑 repro script + 實際 route dump，非純靜態閱讀）：
**1 must-fix，1 should-fix，1 nice-to-have（純資訊性，非扣分項），7 項獨立核對 confirmed
no finding**。

- 🔴 **Must-fix**（已修，見上方 §2.2 + Verify #5-8）：`UpdateInspectionScheduleRequest`
  （PATCH）缺少 `recurrence=custom_days` 必須帶 `interval_days` 的驗證，可寫入無效狀態，
  scheduler 到期時才炸開——工單已建、`next_due_at` 沒推進，導致每次 `run-scheduler` 都重複
  spawn。reviewer 用獨立 repro script 實測「兩次呼叫 → 兩張重複工單 + 兩次 500」。
- 🟡 **Should-fix**（已修，見上方 §2.2 + Verify #5）：`create()` 的驗證只在沒帶 `first_due_at`
  時才會經過 `compute_next_due` 順路驗證，帶了明確 `first_due_at` 會繞過——repository 是可
  被直接呼叫的公開元件，不該依賴呼叫端已經擋過一次。
- 🟢 **Nice-to-have / 提問**（未修，屬設計確認）：`run-scheduler` 用 SUPERVISOR-only，比同模組
  其他「會建立/改動 WorkOrder」的 endpoint（`POST /work-orders` 是 EMPLOYEE/LEADER/SUPERVISOR、
  dispatch/approve/reject/cancel/reopen 都是 LEADER/SUPERVISOR）更嚴格。**本次確認為刻意決策**
  （router 內已有註解說明：「會建立真實工單，權限比照查詢/更新更高」）——`run-scheduler` 一次
  呼叫可能對多台風機批次建工單（vs 逐台手動建單），且是「觸發自動化流程」而非「單一動作」，
  拉高門檻合理；已在本 work-log 記錄供未來 session 或劉老師覆核，未列入 issue 追蹤。
- **7 項獨立核對確認無問題**（reviewer 逐項重新推導，非照單全收我的宣稱）：multi-WO
  constraint 撞到時確實不推進 `next_due_at`（真的會重試，不會悄悄漏掉）；`record_spawn`
  用 `spawned_at` 而非舊 `next_due_at` 的設計理由成立且與實作一致；engine/schema-init 共用
  無 race（`repository/__init__.py` 在任何 factory 呼叫前就已無條件 import `inspection_orm`，
  `Base.metadata` 保證先註冊完）；角色設計與其餘 3 個 sibling router 一致；無 SQL injection /
  UUID / naive-datetime 問題（`assert_utc`/`ensure_utc` 用法正確）；`run-scheduler` 與
  `{schedule_id}` 路由無 method/path 衝突（獨立 dump `router.routes` 驗證）；程式碼品質（型別
  標註、docstring、無裸 `Any`）與既有姊妹檔案一致。

## Wrap-up

- must-fix + should-fix 已修復並 mutation-verified；nice-to-have 為設計確認，已記錄決策理由
  不需改動程式碼。
- `ISSUES.md`（新增 `WMOM-20260925-05`，完整 completion summary + review 修復記錄）、
  `STATUS.yaml`（`last_updated`/`issue_stats`/M3 milestone 段落）、`TODO.md`（最後更新段落 +
  可立即接手清單，補上 sub-task d 依賴已解除但前端未做的說明）已同步更新。
- 誠實揭露：本次純後端交付，前端（`TurbineDetail.tsx` 安排檢查鈕接線 + 定檢計畫管理頁）完全
  未做，見 §4 給下個 session 的話。
