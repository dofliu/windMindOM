# 2026-09-26 — `work_order.finish()` → day_work_form 自動寫入 hook（WMOM-20260926-01 item 2，第四個 autonomous session）

## 認領

`WMOM-20260926-01` 剩餘唯一項目：**item 2 `work_order.finish()` → day_work_form 自動寫入
hook**。第三個 session（讀取端點 ownership 限制）已把設計歧義解完並寫進
`work-logs/2026-09/2026-09-26-day-work-form-read-ownership.md` 下次接手段落，本次直接
照該設計實作，無需再詢問劉老師。

## 設計回顧（沿用前一 session 已拍板的答案）

讀了 `state_machine.py`（`approve_all`：`AWAITING_SIGNOFF → CLOSED`，`guard=None`）+
`approval_router.py`（簽核鏈最後一階自動觸發 `wo_repo.transition(chain.subject_id,
"approve_all")`，**不經過** `work_order_router._run_transition`）+
`work_order_router.py`（`/work-orders/{id}/approve` 直接入口的
`_run_transition(repo, work_order_id, "approve_all")` 最終也是呼叫同一個
`repo.transition()`）。確認**唯一能同時覆蓋兩條完工路徑的掛點**是
`WorkOrderRepository.transition()` 內部，`action == "approve_all"` 時觸發——本次照此實作。

## 實作

- `modules/workflow/repository/work_order_repository.py`：
  - `transition()` 收尾：`sess.commit()` + `sess.refresh(orm)` 後**先跳出 `with
    self._sessionmaker()` block**（讓工單本身的寫入 transaction 先結束/釋放鎖）才呼叫
    新增的 `_record_completed_wo_activity(result)`——避免 day_work_form 的獨立 write
    transaction 跟工單自己的 write transaction 疊在一起造成 SQLite `BEGIN IMMEDIATE`
    自我鎖死。
  - 新增 `_record_completed_wo_activity(wo)`：
    - `wo.assignee_id is None` → 直接 return（不報錯）。理論上 `start_work` guard
      已強制 assignee_id 非 None 才能進入 `IN_PROGRESS`（`approve_all` 唯一 from_state
      是 `AWAITING_SIGNOFF`，必經 `IN_PROGRESS`），但 `approve_all` 本身
      `guard=None`，屬防禦性檢查。
    - Lazy import `DayWorkFormRepository`（module-level 會循環 import——
      `day_work_form_repository.py` 已從 `work_order_repository.py` 匯入
      `_ENGINE_LOCK`/`_SCHEMA_INITIALIZED`/`_get_engine`）。
    - `DayWorkFormORM.__table__.create(bind=self._engine, checkfirst=True)` 補建
      schema（`DayWorkFormORM`/day_work_form 純 domain 的
      `ActivityEntry`/`ActivityKind` 兩者皆無循環 import 風險，改在檔案頂層直接
      import）——因為共用 engine 的 schema 可能在 day_work_form 模組被 import
      之前就已經跑過 `create_all()`，該 table 不會被建立。
    - `work_date` 用 `datetime.now(tz=ZoneInfo("Asia/Taipei")).date()`（新增
      `_TAIPEI_TZ` module 常數），比照前端 `todayAsiaTaipei()` 慣例，非 UTC 曆日。
    - `get_or_create_for_date` 取當天日誌 → `append_activity` 累加一筆
      `ActivityKind.COMPLETED_WO`（`wo_id=wo.id`、`note=wo.business_key` 方便日後
      UI 顯示可讀識別碼而非裸 UUID）。
    - 整段包 `try/except Exception`，失敗只 `_logger.exception(...)` 不 raise——
      比照 `approval_router.approve_step` 既有「chain 已落地但 subject transition
      失敗」的 catch + log 模式：day_work_form 寫入失敗（如 DB lock）不應該讓已經
      `sess.commit()` 落地的工單關閉本身失敗或回滾。
- `modules/workflow/tests/test_work_order_finish_day_work_form_hook.py`（新檔）：
  5 個測試，見下方。

## Mutation 驗證

第一輪（整份 diff）：`git show HEAD:modules/workflow/repository/work_order_repository.py`
覆寫回修法前版本（先備份現有版本到 `/tmp`），5 測全數如預期 fail（`_TAIPEI_TZ` 等新增
symbol 不存在，collection error）。

第二輪（更精準：只關掉 hook 呼叫本身，其餘實作/import 都保留）：把
`if action == "approve_all":` 改成 `if action == "approve_all_DISABLED_FOR_MUTATION_TEST":`，
其餘不動：
- `test_approve_all_appends_completed_wo_activity` — fail（無日誌可查）
- `test_approve_all_via_work_order_router_approve_endpoint_also_appends` — fail
- `test_approve_all_two_work_orders_same_day_accumulates_activities` — fail
- `test_approve_all_day_work_form_failure_does_not_break_transition` — fail
  （`caplog` 抓不到「自動寫入失敗」訊息，因為 hook 根本沒被呼叫）
- `test_approve_all_without_assignee_does_not_raise_and_creates_no_form` — **仍 pass**
  （預期內：此測試直接呼叫私有方法 `repo._record_completed_wo_activity(wo)`，不經過
  `transition()` 的 `if action == ...` 分支，本來就不受這處 mutation 影響）

改回 `if action == "approve_all":`，`git diff --stat` 確認復原後與原始實作完全一致
（67 insertions / 1 deletion，無漏改），5 測全數 pass。

## 驗證

- backend baseline（`modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/
  modules/knowledge/tests/ modules/monitoring/tests/ modules/auth/tests/ tests/`）：
  開工前 **1250 passed**（7 skipped, 1 xfailed）→ 本次收尾 **1255 passed**（+5，零
  regression）。
- frontend：本次未動 frontend 程式碼（純 backend repository 變更）。開工前已跑過
  baseline 確認健康：`npx tsc --noEmit` 0 error、`npx vitest run` **1402 passed**
  （65 files）、`npx vite build` OK。收尾前重跑 `npx tsc --noEmit` 再次確認 0 error
  （純 backend 改動不影響 TS 型別，未重跑 vitest/build）。

## code-reviewer subagent review

（收尾時回填）

## 沒有自動化保護的部分

- 本次測試皆走 `WorkOrderRepository`/`DayWorkFormRepository` 直接呼叫，**未經過**
  `approval_router.py` 的 FastAPI endpoint（`test_approval_api.py` 等既有 HTTP 層測試
  未特別驗證 day_work_form 這個新 side-effect 有沒有被觸發）。因為 hook 掛在
  `WorkOrderRepository.transition()`（repository 層，唯一交會點），HTTP 層兩條路徑
  （`approval_router`/`work_order_router`）本質上都是呼叫同一段程式碼，理論上不需要
  額外重複測，但若未來有人在 router 層加了「跳過 repo.transition() 直接改 ORM」的
  捷徑，這裡不會有測試抓到（可能性低，目前沒有這類 code path）。
- `_TAIPEI_TZ`（`ZoneInfo("Asia/Taipei")`）的行為依賴系統時區資料庫（`tzdata`）；測試
  沒有針對「日界線交接時刻」（例如 UTC 15:59/16:00 剛好跨過 Asia/Taipei 午夜）寫專門
  的 freeze-time 測試，只驗證「呼叫當下」的今天日期正確累加，屬於已知但低風險的覆蓋
  空白（前端 `todayAsiaTaipei()` 也是同款未特別測邊界的慣例）。

## 下次接手

`WMOM-20260926-01` 三項全數完成，issue 可標 done。`WMOM-20260926-01` 系列告一段落。

下個工作優先順序（見 TODO.md / ISSUES.md）：
- 情境比較分析 epic 剩餘：A2 跨情境比較「相對時間對齊」，或 PR C（檢視情境掛載 app，
  需先寫 broker 子設計）
- M6 critical path 殘項：WMOM-20260716-06（footprint CPU-torch pin，需 docker）、
  WMOM-20260509-F6（PostgreSQL row-lock integration test，需 docker postgres）、
  HTTPS 部署配置
