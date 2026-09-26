# 2026-09-26 — `day_work_form` 讀取端點 ownership 限制（WMOM-20260926-01 item 3）

## 認領

`WMOM-20260926-01`（第三個 autonomous session，接續前兩個 session：後端 domain/repo/router
`WMOM-20260505-21`、前端 `DayWorkFormPanel` tab）。issue 收攏 3 項延後工作，本次挑
**item 3：讀取端點 ownership 限制**（issue 內 `Priority` 欄位明文建議此項優先於 item 2
`work_order.finish()` hook，且設計歧義較低——不需要劉老師拍板）。

## 現況問題

`GET /day-work-forms`（list）/ `GET /day-work-forms/by-date` / `GET /day-work-forms/{id}`
三個讀取端點目前只掛 `require_authenticated()`（enforce=false 放行、enforce=true 也只檢查
「有沒有登入」，不檢查角色/身分），對任何登入角色開放——包含 TREASURY（庫管）也能查
任一員工任一天的完整工作日誌內容，違反「日誌是自填、隱私度接近私人記事」的設計初衷。

## 設計決策（無需劉老師介入，讀 code 可解）

讀了 `modules/auth/dependencies.py` 全部既有 dependency（`get_current_actor` /
`require_role` / `require_authenticated` / `resolve_actor_id` / `resolve_actor_id_optional`），
發現這個 repo 有兩種身分解析哲學並存：

1. **identity-resolution 族**（`resolve_actor_id` 等）：**無論 enforce 與否，一律優先信任
   token**——因為這類函式是給「誰執行了這個寫入」的 audit 身分用（如 signoff actor_id、
   day_work_form employee_id 代填檢查），就算 enforce=false 也要用真實 token 蓋掉 legacy
   body 值。
2. **access-control gate 族**（`require_role` / `require_authenticated`）：**enforce=false
   完全不觸碰 token**，直接放行——維持過渡期既有行為不變。

「讀取端點 ownership 限制」在語意上屬於第 2 類（access control，不是「這筆資料算誰的」
的 audit 身分），所以新加的 `resolve_actor_when_enforced()` 比照 `require_role` 的風格：
`enforce=false` 回 `None`（不限制，維持現有全開放行為，完全不解 token，避免 cutover 前
呼叫端剛好帶了 token 就意外被收窄）；`enforce=true` 才回傳已驗證的 `Actor`（token /
dev-fallback，同 `get_current_actor`）。

**視覺範圍**：只有 `LEADER` / `SUPERVISOR` / `ADMIN` 維持可查全員（`_FULL_VISIBILITY_ROLES`）；
`EMPLOYEE` 與 **`TREASURY`** 都收窄成只能查自己——issue 原文明確點名 TREASURY 是問題案例
（"TREASURY 庫管也能瀏覽任一員工任一天的完整工作日誌內容"），而建議的「維持可查全員」
清單只列了 LEADER/SUPERVISOR/ADMIN 三者，不含 TREASURY，故 TREASURY 這次一併收窄。

**行為差異（issue 原文給了兩個選項，依端點語意分別採用）**：
- `list`（`employee_id` 是可選 filter，不帶時本來就是「全員」）→ 收窄成**強制覆寫** 成
  自己（忽略帶入值），不報錯，維持「查得到東西」的體驗（沒有東西可覆寫就是空清單）。
- `by-date`（`employee_id` 是必填 query 參數，呼叫端明確指定了某人）→ 非本人 **403**
  （靜默覆寫會讓呼叫端誤以為拿到了他指定那個人的資料，實際上是別人的，更危險）。
- `{form_id}` detail（沒有 employee_id 參數，資料本身綁定 owner）→ 404 優先（不洩漏
  「這份存在但不是你的」），非本人 403，比照 `append_activity` 既有的 404-before-403 慣例。

## 實作

- `modules/auth/dependencies.py`：新增 `resolve_actor_when_enforced(request) -> Actor | None`。
- `modules/workflow/routers/day_work_form_router.py`：
  - `_FULL_VISIBILITY_ROLES = frozenset({Role.LEADER, Role.SUPERVISOR, Role.ADMIN})`
  - `_viewer_uuid(actor_id: str) -> UUID`（沿用既有 `_employee_uuid` 的 400 錯誤格式）
  - 3 個讀取端點各自補上 `request: Request` 參數 + ownership narrowing/403。
- `modules/workflow/tests/test_day_work_form_router_auth.py`：新增 13 個 regression tests
  （皆 mutation-verified，見下方）。

## code-reviewer subagent review

**Approve，0 must-fix，2 should-fix，2 nice-to-have**：
1. 🟡 Should-fix：新測試都只用 TREASURY 當「非本人」代表角色，沒有任何一個用 EMPLOYEE
   token 查別人（EMPLOYEE 才是這三支端點最主要的實際呼叫者，是本次修法要防的核心場景之一
   卻沒有直接測到）——**已修復**：補 3 個 EMPLOYEE 版本測試（list 覆寫 / by-date 403 /
   detail 403），皆 mutation-verified（見下方）。
2. 🟡 Should-fix：work-log「Mutation 驗證」「驗證」兩節仍是 TODO——**已修復**（本次回填）。
3. 🟢 Nice-to-have：`_viewer_uuid` 與既有 `_employee_uuid` 幾乎重複（同款 try/UUID/400
   pattern）——**已採納**：抽出共用 `_to_uuid(label, value)` helper，兩處改呼叫它。
4. 🟢 Nice-to-have（非本次 diff 範圍）：cutover（`WMOM_AUTH_ENFORCE=true`）正式打開前，
   建議順手確認前端沒有依賴「TREASURY 瀏覽全員日誌」舊行為的畫面——記錄於此供 M6 部署前
   checklist 參考，本次不動前端（目前 enforce 預設仍是 false，無 blast radius）。

reviewer 獨立追蹤了完整授權邏輯鏈路（`resolve_actor_when_enforced` → `get_current_actor` →
`_FULL_VISIBILITY_ROLES` gating）+ repository 層 `employee_id=None` 語意，確認：
`resolve_actor_when_enforced` 在 enforce=true 時沒有任何「靜默失敗開放」的路徑（dev-mode
fallback 仍回傳 Actor，只是 role=ADMIN，屬刻意設計的全權）；`_viewer_uuid`/`_to_uuid` 失敗
一律 fail-closed（400）；list 端點的覆寫對「明確帶入 employee_id」與「完全不帶」兩種情況
都無差別覆寫，沒有「不帶參數就能看全員」的漏洞（issue 原文點名的問題）；list=覆寫 /
by-date=403 / detail=404-then-403 的三種行為差異是刻意設計的 UX/資訊洩漏 tradeoff，不是
不一致的安全缺口（by-date 的 403 在不確定命中的情況下完全不碰 DB，反而是三者中最保守的）。

## Mutation 驗證

第一輪（10 測，第一次 review 前）：`git stash` 暫存 `modules/auth/dependencies.py` +
`modules/workflow/routers/day_work_form_router.py`（保留測試檔），重跑
`test_day_work_form_router_auth.py`，確認以下 4 個測試如預期 fail（其餘 28 個測試因未涉及
ownership 限制邏輯，維持 pass 不受影響）：
- `test_list_enforced_treasury_narrowed_to_self`
- `test_list_enforced_treasury_cannot_override_employee_id_filter`
- `test_by_date_enforced_treasury_other_employee_403`
- `test_detail_enforced_treasury_other_employee_403`

`git stash pop` 回復後 32 測全數 pass。

第二輪（review should-fix #1 補的 3 個 EMPLOYEE 版本測試）：由於此時 router 實作已 commit
（含 ownership 邏輯），改用 `git show <上一個 commit>:modules/workflow/routers/
day_work_form_router.py` 把 router 檔覆寫回**修法前**版本（先備份現有版本到 `/tmp`，
`git stash` 對已 commit 內容無效，直接檔案覆寫更直接），只跑新加的 3 個測試，確認皆如預期
fail：
- `test_list_enforced_employee_narrowed_to_self`
- `test_by_date_enforced_employee_other_employee_403`
- `test_detail_enforced_employee_other_employee_403`

從 `/tmp` 備份復原後，35 測全數 pass（`git diff --stat` 確認復原後的 diff 只剩 `_to_uuid`
重構的 +11/-8，功能邏輯無誤丟）。

## 驗證

- backend baseline（`modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/
  modules/knowledge/tests/ modules/monitoring/tests/ modules/auth/tests/ tests/`）：
  開工前 1237 passed（7 skipped, 1 xfailed）→ 本次收尾 **1250 passed**（7 skipped, 1
  xfailed，**+13，零 regression**）。
- frontend：本次未動 frontend 程式碼（純 backend 授權/路由變更）。開工前已跑過
  baseline 確認健康：`npx tsc --noEmit` 0 error、`npx vitest run` **1402 passed**（65
  files，1 個既有 `TurbineDetail.test.tsx` teardown 後 timeout 印出 `window is not
  defined` 的已知環境雜訊，非本次改動、退出碼仍是 0）、`npx vite build` OK。本次改動
  未觸及任何 frontend 檔案，故未重跑。

## 沒有自動化保護的部分

- `resolve_actor_when_enforced` 只在 `WMOM_AUTH_ENFORCE=true` 才生效——目前 production
  預設仍是 `false`（過渡期），這條 ownership 限制**尚未在真實流量上驗證過**，只在測試
  環境用 `monkeypatch.setenv` 模擬 enforce=true。cutover 排程時建議先在 staging 打開
  `WMOM_AUTH_ENFORCE=true` 手動 smoke test 一次三支讀取端點（尤其是 TREASURY 帳號），
  不要只依賴這批單元測試。

## 下次接手

`WMOM-20260926-01` 剩 **item 2：`work_order.finish()` → day_work_form 自動寫入 hook**
仍 open。已讀過 `state_machine.py` + `approval_router.py`：完工的真正動作是
`approve_step`（`approval_router.py`）簽核鏈最後一階時內部呼叫
`wo_repo.transition(chain.subject_id, "approve_all")`（AWAITING_SIGNOFF → CLOSED），
`work_order_router.py` 另有一支 `/work-orders/{id}/approve` endpoint 也會呼叫同一個
`repo.transition(id, "approve_all")`（見其 docstring："正常流程...由 approval_router
內部呼叫...跳過此 router endpoint"——代表這是給非簽核鏈路徑用的备用/直接入口，兩者都要
覆蓋到）。**建議掛點**：`WorkOrderRepository.transition()`（`modules/workflow/repository/
work_order_repository.py:424`）内部、`action == "approve_all"` 時觸發——這是唯一能同時
覆蓋 `approval_router` 自動觸發與 `work_order_router` 直接 endpoint 兩條路徑的地方（掛在
`_run_transition` 只會蓋到 `work_order_router`，approval_router 是直接呼叫 repo，不經過
`_run_transition`）。需注意：
- day_work_form 的 employee = `wo.assignee_id`（None 時跳過，不報錯——不是每張工單都保證
  有 assignee，雖然 `start_work` guard 理論上已強制）。
- `work_date` 用 Asia/Taipei 曆日（比照 domain docstring 慣例 + 前端 `todayAsiaTaipei()`），
  非 UTC 曆日。
- day_work_form 的 side-effect 失敗（如 DB lock）不應該讓已經 commit 的工單關閉本身失敗
  或回滾——比照 `approval_router.approve_step` 既有模式（catch + log，不 raise 500）。
- 需注意 circular import：`day_work_form_repository.py` 已 import
  `work_order_repository.py` 的 `_ENGINE_LOCK`/`_SCHEMA_INITIALIZED`/`_get_engine`；
  反向 import 需寫成 method 內 local import，並額外呼叫
  `DayWorkFormORM.__table__.create(bind=self._engine, checkfirst=True)` 確保 schema
  已存在（`Base.metadata.create_all()` 在 `get_repository()` 跑的當下，若
  `day_work_form_orm` 模組還沒被其他地方 import 過，該表不會被建立）。

item 3（讀取端點 ownership 限制）**至此完成**，本 session 只做 item 3。
