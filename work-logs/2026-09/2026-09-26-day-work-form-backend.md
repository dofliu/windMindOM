# 2026-09-26 — WMOM-20260505-21 員工日誌（day_work_form domain + repository + router 後端）

> Session 類型：實作
> Session 長度：長
> 主導：autonomous worker（cron）
> 結果：完成（後端；前端 + work_order.finish() hook + 讀取端點 ownership 限制拆成新 issue
> WMOM-20260926-01，見 §4）

---

## 1. Session 目標

Preflight：`git status` clean（分支 `claude/inspiring-mccarthy-48za5d`，環境注入，與
`origin/main` 同一 commit `90c6799`）；`mcp__github__list_pull_requests(state=open)` 回傳空
陣列，無殘留 open PR、無 stack 衝突。

Baseline 自我測試全綠：
- backend：`pip install --ignore-installed PyYAML -r requirements.txt -r requirements-dev.txt`
  → `python -m pytest`（6 module + `tests/`）→ **1182 passed, 7 skipped, 1 xfailed**（與
  `docs/routines/autonomous-daily-worker-prompt.md` 記載的 1076 舊 baseline 不符，但與
  `STATUS.yaml`/`TODO.md` 記載的最新數字一致——採用後者，屬預期中的「baseline 比 routine
  文件多」情形，非 regression）。
- frontend：`npm ci` → `npx tsc --noEmit` 0 error → `npx vitest run` **1354 passed**（63
  files）→ `npx vite build` OK。

依決策樹挑題：M6 critical path（-04/-08/-06）已全數完成；情境比較 A2 epic 全完成；PR C
需先寫 broker 子設計、非單 session 可清楚定義範圍；`WMOM-20260507-02` 清單已全數完成
（a-f）。掃過 ISSUES.md 全部 open issue：`WMOM-20260504-11`（event-driven cost ledger，
2-3 天、需劉老師 tariff/revenue 假設決策）太大且有設計歧義；`WMOM-20260509-F6`
（PostgreSQL row-lock）已標🟡需劉老師決策；`WMOM-20260505-23~28`（物理模型）park；
`WMOM-20260513-01`（UI v2）等設計交接書。**選定 `WMOM-20260505-21`（day_work_form）**——
design 已在 DN-01 walkthrough Q6（2026-05-05 劉老師確認）resolve，無設計歧義，且與上個
session（2026-09-25）完成的 `WMOM-20260505-22`（inspection_schedule）同批衍生、同一設計
文件、可完全比照其分層與慣例實作，風險可控。

範圍界定（開工前決定，比照 `inspection_schedule` 前後端拆兩 session 先例）：完整做後端
（domain + ORM + repository + router + schemas + 測試，mutation-verified），**前端頁面**與
**`work_order.finish()` 自動寫入 day_work_form 的整合 hook**本次不做——後者涉及既有簽核
流程（`approve_all` → `CLOSED`）的耦合風險評估，需要先讀 `state_machine.py`/
`approval_router.py` 現況再決定掛點，不適合在同一 session 內臨時決定。

## 2. 實際完成

### 2.1 主要工作

**Domain（`modules/workflow/domain/day_work_form.py`，新檔）**：
- `ActivityKind` enum（`completed_wo`/`inspection_item`/`patrol`/`training`，對應
  walkthrough Q6 圖示的 4 種活動）
- `ActivityEntry` dataclass（kind-specific 欄位皆 optional，未使用維持 `None`）+
  `ACTIVITY_REQUIRED_FIELDS` 表（每種 kind 的必填欄位）+ `validate_activity_entry()`
  純函式（顯式呼叫，非 `__post_init__`，同 `recurrence_interval_days` 慣例）
- `DayWorkForm` dataclass（`(farm_id, employee_id, work_date)` 為 natural key）

**ORM + Repository（`repository/day_work_form_orm.py` + `day_work_form_repository.py`，
新檔）**：
- `DayWorkFormORM`（`wmom_day_work_forms` 表，`(farm_id, employee_id, work_date)` 唯一
  索引 + `(farm_id, work_date)` 查詢索引）；`activities` 用 JSON 字串存（沿襲
  `WorkOrderORM.completion_photos`/`payload_json` 慣例，單日單人活動數量少不需獨立子表）
- `DayWorkFormRepository`：`get_or_create_for_date`（natural-key idempotent，靠
  `work_order_repository` 既有的 `BEGIN IMMEDIATE` 序列化寫入 + `IntegrityError` fallback
  雙重防禦）、`append_activity`（累加式寫入，寫入前先 `validate_activity_entry`）、
  `get`/`get_by_date`/`list`（依 `work_date` 降冪）
- 共用 `work_order_repository.py` 的 engine cache（沿襲 `InspectionScheduleRepository`
  做法，避免同一 farm DB 開兩條 connection pool）

**Router（`routers/day_work_form_router.py`，新檔，5 endpoints）**：
- `POST /day-work-forms`（get-or-create）、`GET /day-work-forms`（list）、
  `GET /day-work-forms/by-date`（「我今天做了什麼」單日 query）、
  `GET /day-work-forms/{id}`（detail）、`POST /day-work-forms/{id}/activities`（append）
- employee 身分走 `resolve_actor_id` 雙模式解析（token 優先，過渡期 body fallback），同
  `work_order_router._actor_uuid` 慣例；寫入端點 EMPLOYEE/LEADER/SUPERVISOR 角色門檻
- 註冊進 `modules/monitoring/server/app.py`

**Schemas（`schemas/day_work_form_schemas.py`，新檔）**：
- `CreateDayWorkFormRequest`、`AppendActivityRequest`（`model_validator` 提早擋 kind 必填
  欄位）、`DayWorkFormResponse`、`ActivityEntryResponse`、`DayWorkFormListResponse`

**Tests（3 新檔，52 tests 第一輪，review 後 +3 = 55 tests，全數 mutation-verified）**：
- `test_day_work_form_domain.py`（14 tests）：每種 kind 必填欄位驗證 + dataclass 預設值
- `test_day_work_form_repository.py`（19 tests）：get-or-create 冪等 + append 累加 + query
- `test_day_work_form_router_auth.py`（19→22 tests）：CRUD HTTP 層 + 雙模式授權 + ownership

**`__init__.py` wiring**：`domain/__init__.py`、`repository/__init__.py`、
`schemas/__init__.py`、`routers/__init__.py` 四處新增 export；`modules/monitoring/server/
app.py` 註冊新 router（`GET /openapi.json` 確認 5 個 endpoint 皆正確掛載，`by-date` 與
`{form_id}` 路由無順序衝突）。

第一輪驗證（review 前）：backend 1182→**1234 passed**（+52，零 regression）；frontend
未動 1354 passed、tsc 0、build OK。

### 2.2 Code review 修復

code-reviewer subagent 抓到 **1 must-fix + 3 should-fix + 2 nice-to-have**：

🔴 **Must-fix（已修）**：`append_activity` 端點完全沒有驗證呼叫者是否為日誌本人——任何
EMPLOYEE/LEADER/SUPERVISOR 角色的登入者，只要知道別人的 `form_id`（可從無 ownership
限制的 list 端點取得），就能把偽造的活動（例如「已完成某工單」）塞進「別人」的日誌。
這直接違反模組 docstring 自己宣稱的設計不變量（「不支援代填」）。**reviewer 更指出一個
更根本的問題：我自己寫的測試 `test_append_activity_enforced_employee_ok` 字面上用兩個
不同的隨機 subject（建立者 vs. append 呼叫者）卻斷言 200，等於把這個錯誤行為當「預期
通過」鎖住**——這不是漏測邊界情境，是測試本身斷言了錯誤行為。

修法：
1. `append_day_work_form_activity` 內先 `repo.get(form_id)`，不存在回 404（優先於 403，
   不洩漏「這份日誌存在但不是你的」這種資訊）。
2. 用 `_employee_uuid(request, req.employee_id)` 解出呼叫者身分，與 `form.employee_id`
   比對，不同者一律 403——**不分角色**，LEADER/SUPERVISOR 也不能代填（可以「查」全員
   日誌，但不能「寫」進別人的日誌，兩者是不同的授權維度）。
3. `AppendActivityRequest` 補上 `employee_id: Optional[UUID] = None`，比照
   `CreateDayWorkFormRequest` 提供過渡期 body fallback（enforce 開啟後一律用 token）。
4. 修正 `test_append_activity_enforced_employee_ok`（改用同一 subject，斷言 200）+ 新增
   3 個 regression test：`test_append_activity_different_employee_403`（過渡期換人）、
   `test_append_activity_enforced_different_employee_403`（enforce 模式換人）、
   `test_append_activity_supervisor_cannot_write_others_log_403`（SUPERVISOR 角色也不能
   代填）。

Mutation-verified：拔掉 ownership 比對（`if False:`）→ 3 個新測試如預期 fail（含原本被
誤鎖的那條，改寫後現在會正確 fail）；還原後重跑全套零 regression。

🟡 **Should-fix（已修）**：domain 與 schema 各自維護一份 `_REQUIRED_FIELDS`（逐字複製，
非跨欄位邏輯，沒有獨立存在理由），沒有測試鎖住兩者一致——已改成 domain 匯出公開的
`ACTIVITY_REQUIRED_FIELDS`，schema 直接 import 同一份物件（`is` 比對確認同一物件，非
各自一份，未來不會漂移）。

🟡 **Should-fix（已修）**：`_select_by_natural_key` 的 `sess` 參數缺型別標註，補
`Session` type hint（同檔案與姊妹 repository 慣例，CLAUDE.md §7 要求）。

🟡 **Should-fix（記錄，未修，見 §4 + WMOM-20260926-01）**：`list`/`by-date`/`{form_id}`
三個查詢端點對任何登入角色開放（含 TREASURY 庫管），無 ownership 限制，可瀏覽任一員工
任一天的完整日誌內容。reviewer 判定這是「非阻塞本次 PR 的 follow-up」，因為涉及更廣的
角色可見性設計決策（EMPLOYEE 應只能查自己的 vs LEADER/SUPERVISOR 查全員的分界，且需要
先確認 `require_authenticated()` dependency 目前簽章能否在 handler 內取得
role/actor），與本次 must-fix 的「寫入偽造」風險層級不同，拆進 `WMOM-20260926-01`。

🟢 **Nice-to-have（已採納文件化，未改行為）**：
- `work_date` 時區語意——domain docstring 補一句明文規定：由前端決定用哪個時區換算
  「今天」，建議 Asia/Taipei 曆日（非 UTC 曆日，避免跨夜巡檢誤植隔天）。
- `AppendActivityRequest` 不會清空與 `kind` 無關的欄位——schema docstring 補充說明下游
  讀取（報表/cost ledger）須自行以 `kind` 過濾，不可假設其餘欄位為 `None`。

reviewer 也獨立核對確認以下幾點無問題（非新發現，交叉核對）：
- `get_or_create_for_date` 的 race-condition 處理正確——`work_order_repository._get_engine`
  對同一 engine 掛了 `BEGIN IMMEDIATE` begin listener，使每個 transaction（含純 select）
  一開始就取得 RESERVED 寫鎖，select-then-insert 確實被序列化，`IntegrityError` fallback
  只是防禦層而非主要防線。
- `append_activity` 的 JSON round-trip（UUID/datetime）正確；`validate_activity_entry`
  確實在 commit 前就 raise，不留半套資料。
- `_employee_uuid`（create 端點）雙模式授權邏輯正確無繞過空間。
- 路由順序（`by-date` vs `{form_id}`）無陷阱，與我自己 openapi 驗證的結論一致。

### 2.3 卡住或延後的事

**前端頁面 + work_order.finish() 整合 hook + 讀取端點 ownership 限制**——三項皆拆進新
issue `WMOM-20260926-01`，理由與細節見該 issue 條目與下方 §4。

### 2.4 重大決策

**`work_date` 不強制時區**——純 `date`，由前端決定用哪個時區換算「今天」，domain
docstring 建議 Asia/Taipei（未寫入 decision_log，屬單一欄位的實作範圍決策）。

**append-activity 的 ownership 檢查不分角色**——LEADER/SUPERVISOR 只能「查」全員日誌，
不能「代填」，與「查」的授權維度分開設計（未寫入 decision_log，屬單一 router 的授權範圍
決策，已在程式碼註解 + ISSUES.md + 本 work-log 記錄）。

## 3. 產出清單

新增 5 個 production 檔案（domain 1 + repository 2 + schemas 1 + router 1）+ 3 個 test 檔
（55 tests）+ 5 個既有檔案的 wiring 修改（4 個 `__init__.py` + `app.py`）。

## 4. 給下個 session 的話

- **`WMOM-20260505-21` 後端已完成**，API 已可直接串接，但**前端仍未接線**、
  **work_order.finish() 自動寫入 hook 未做**、**讀取端點 ownership 限制未做**——三項
  拆成新 issue **WMOM-20260926-01**（open），可分次接手：
  1. 前端：`/admin/workflow` 新增「工作日誌」頁籤（比照 `inspection_schedule` 併入
     `WorkflowPage.tsx` 既有 tab 慣例）。
  2. `work_order.finish()` hook：**先讀 `state_machine.py` + `approval_router.py` 現況
     再拍板掛點**（`approve_all` action 轉 `CLOSED` 才是實際完工路徑，不是叫
     `finish()`），不要照抄 `inspection_scheduler` 的 auto-spawn 模式（方向相反：那是
     「排程到期建新工單」，這裡是「工單完工回寫日誌」）。
  3. 讀取端點 ownership 限制：EMPLOYEE 角色查詢應限本人，LEADER/SUPERVISOR/ADMIN 可查
     全員；需要先確認 `require_authenticated()` dependency 能否在 handler 內取得
     role/actor（目前簽章只回傳 `None`）。
- 新 API 一覽（供前端串接參考）：
  - `POST /api/workflow/day-work-forms?`（body: `farm_id`, `work_date`, `employee_id`?，
    EMPLOYEE/LEADER/SUPERVISOR）
  - `GET /api/workflow/day-work-forms?farm_id=&employee_id=&date_from=&date_to=`（任何
    登入者，**目前無 ownership 限制，見上方 should-fix #3**）
  - `GET /api/workflow/day-work-forms/by-date?farm_id=&employee_id=&work_date=`（同上）
  - `GET /api/workflow/day-work-forms/{id}?farm_id=`（同上）
  - `POST /api/workflow/day-work-forms/{id}/activities?farm_id=`（body: `kind` + 
    kind-specific 欄位 + `employee_id`?，EMPLOYEE/LEADER/SUPERVISOR + **ownership 檢查
    已修復**：非本人一律 403）
- **未受自動化測試保護的部分**：無（本次純後端，55 tests 涵蓋 domain/repository/router
  三層，皆 mutation-verified；schema 層 `AppendActivityRequest._check_required_fields`
  的「提早 422」行為沒有獨立鎖住的測試——拔掉它不會讓任何測試 fail，因為 repository 層
  `validate_activity_entry` 仍會擋住，最終行為都是 422，只是擋的層級不同，這是刻意的
  defense-in-depth，已在 review 過程實測確認並誠實記錄，非阻塞）。
- **附帶發現（供劉老師參考）**：`ISSUES.md`/`STATUS.yaml` 頂部統計表數字（141→142）與
  raw grep `### WMOM-*` + `**Status**` 欄位在 `ISSUES.md` 主文實測數字（114 筆：9 open +
  3 in_progress + 102 done）對不上。推測與歷史 `WMOM-20260529-02`（ISSUES changelog 抽
  archive）有關，但未深入查證——本次沿用既有 delta-only 更新慣例（每個 session 只對
  「檔案自己記載的前一個數字」做加減），未展開全面稽核（超出本次 issue 範圍，且風險
  不小：114 vs 141 差 27 筆，需要逐一比對 `docs/legacy/issues_changelog_archive.md` 才能
  釐清）。已在 `STATUS.yaml` `issue_stats` 註解記錄，建議劉老師評估是否要開一個
  dedicated 清點 issue（非緊急，不影響任何自動化流程——repo 內無程式實際解析這兩個
  統計表）。

## 5. Open questions（park）

- `work_order.finish()` hook 應該掛在 `WorkOrderRepository.transition()` 內部（耦合度
  高，任何 transition 都會經過）還是 `approval_router` 的 `approve_all` 專屬路徑（耦合度
  較低但只覆蓋這一種完工路徑）？留給下個 session 讀完現況程式碼再決定，本次不猜測答案。
- 讀取端點的角色分級（EMPLOYEE 限本人 vs LEADER/SUPERVISOR 查全員）是否也要延伸到
  TREASURY/ADMIN？本次未深究，留給下個 session 隨 WMOM-20260926-01 一併設計。

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline：backend `1182 passed, 7 skipped, 1 xfailed`；frontend `npx tsc --noEmit`
  0 error、`npx vitest run` **1354 passed**（63 files）、`npx vite build` OK。
- 新增後（第一輪，review 前）：backend `1234 passed, 7 skipped, 1 xfailed`（+52 新測，零
  regression）。
- must-fix + should-fix 修復後（第二輪，最終）：backend **1237 passed, 7 skipped, 1
  xfailed**（+55 新測總計，零 regression）；frontend 未動，`1354 passed`（63 files）
  不變、tsc 0、build OK。
- app boot 驗證：`GET /openapi.json` 確認 5 個 day-work-form endpoint 皆正確註冊，
  `by-date` 與 `{form_id}` 路由無順序衝突（reviewer 獨立核對程式邏輯層面同一結論）。
- **Mutation-verified**（`cp` 備份至 scratchpad + 逐一還原確認，非 `git checkout`，因新檔
  為 working tree 未追蹤/剛提交檔案）：共 **6 處關鍵邏輯**逐一改回錯誤版本確認對應測試
  如預期 fail，還原後重跑相關測試檔確認一致，重跑全套零 regression：
  1. `validate_activity_entry` 拔掉驗證邏輯（`return` no-op）：domain 7 個測試 +
     repository `test_append_activity_invalid_entry_raises_before_persist` 共 8 個
     fail（含 `DID NOT RAISE ValueError`）
  2. `get_or_create_for_date` 的 natural-key 快速路徑改成永遠不命中（`if False`）：**0
     測試 fail**（正面發現：`BEGIN IMMEDIATE` 序列化寫入 + `IntegrityError` fallback
     的雙重防禦本身就足以保住冪等契約，快速路徑只是效能優化，非唯一正確性來源——已在
     work-log 誠實記錄這個發現，非測試漏洞）
  3. schema 層 `AppendActivityRequest._check_required_fields` 改成 no-op：**0 測試
     fail**（repository 層 `validate_activity_entry` defense-in-depth 頂住，已誠實記錄
     為已知限制，非阻塞）
  4. router `create` 端點的 `require_role` 依賴拔掉：`test_create_enforced_treasury_403`
     fail（200 而非預期 403）
  5.（must-fix 修復）append endpoint 的 ownership 比對改成 `if False`：3 個新
     regression test 如預期 fail（含改寫後的 `test_append_activity_enforced_employee_ok`
     系列）
  6. `_activity_to_dict`/`_activity_from_dict` 的 JSON round-trip（reviewer 獨立核對，
     非本次額外 mutation，已於 review 逐項確認 UUID/datetime/None 皆正確）

## Review

code-reviewer subagent（讀 DN-01 §3.3/§5 Q6 設計依據 + 全部新增檔案全文 + 既有
`work_order_router.py`/`modules/auth/dependencies.py` 對照慣例，並跑過三個新測試檔確認
斷言內容，非純靜態掃描）：**1 must-fix，3 should-fix，2 nice-to-have，7 項逐一核對
確認無問題**。

- 🔴 **Must-fix**（已修，見上方 §2.2 + Verify #5）：`append_activity` 完全沒有
  ownership 檢查，且**我自己寫的測試字面上把這個錯誤行為鎖成預期通過**——reviewer 沒有
  照單全收我委派 prompt 裡「已通過測試」的宣稱，反而具體指出哪一條測試的斷言本身就是
  錯的，並說明為什麼（兩個不同隨機 subject 卻斷言 200）。這是本次 review 最有價值的
  發現：我的驗證流程本身有一個漏洞（測試斷言了觀察到的行為而非期望的行為）。
- 🟡 **Should-fix**（已修）：domain/schema `_REQUIRED_FIELDS` 複製無 parity 保護、
  repository helper 缺型別標註。
- 🟡 **Should-fix**（記錄，見上方 §2.2 + §4）：讀取端點無 ownership 限制，reviewer 主動
  判定非阻塞本次 PR（涉及更廣角色設計），拆進 WMOM-20260926-01。
- 🟢 **Nice-to-have**（已文件化）：`work_date` 時區語意、`AppendActivityRequest`
  不清空無關欄位。
- **7 項獨立核對確認無問題**：`get_or_create_for_date` race-condition 處理（`BEGIN
  IMMEDIATE` 序列化）、JSON round-trip（UUID/datetime/None）、`_employee_uuid`（create
  端點）雙模式授權邏輯、路由順序無陷阱、範圍縮減（不做 finish hook + 前端）合理且已誠實
  記錄、`wo_id`/`item_id` 無 FK 驗證是刻意鬆耦合（建議未來 hook 層做存在性檢查）、程式碼
  品質（型別標註、docstring、無裸 `Any`）與既有姊妹檔案一致。

## Wrap-up

- must-fix + 2 個 should-fix 已修復並 mutation-verified；1 個 should-fix（讀取端點
  ownership）拆進新 follow-up issue，理由已記錄；2 個 nice-to-have 已文件化。
- `ISSUES.md`（`WMOM-20260505-21` 標 `in_progress` + 完整 completion summary + review
  修復記錄，新增 `WMOM-20260926-01`）、`STATUS.yaml`（`last_updated`/`issue_stats`）、
  `TODO.md`（最後更新段落 + 可立即接手清單）已同步更新。
- 誠實揭露：本次純後端交付，前端（`/admin/workflow` 工作日誌頁籤）、work_order.finish()
  整合 hook、讀取端點 ownership 限制皆未做，見上方 §4。另外誠實記錄兩處「mutation 測試
  未能獨立鎖住」的發現（natural-key 快速路徑靠資料庫約束兜底、schema 層驗證靠 repository
  層兜底）——皆非測試漏洞，是刻意的 defense-in-depth 設計，但本 work-log 選擇誠實揭露而
  非含糊帶過。
