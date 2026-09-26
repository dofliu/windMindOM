# 2026-09-26 — WMOM-20260926-01 第 1 項：day_work_form 前端（工作日誌 tab，本人專用）

> Session 類型：實作
> Session 長度：長
> 主導：autonomous worker（cron）
> 結果：完成（本人日誌前端；work_order.finish() hook 與讀取端點 ownership 限制拆為
> 該 issue 剩餘 2 項，仍 open，見 §4）

---

## 1. Session 目標

Preflight：`git status` clean（分支 `claude/inspiring-mccarthy-irnqh0`，環境注入；
`mcp__github__list_pull_requests(state=open)` 回傳空陣列，無殘留 open PR、無 stack 衝突）。

Baseline 自我測試全綠：
- backend：`pip install --ignore-installed PyYAML -r requirements.txt -r requirements-dev.txt`
  → `python -m pytest`（6 module + `tests/`）→ **1237 passed, 7 skipped, 1 xfailed**（與
  `STATUS.yaml`/`TODO.md` 記載一致，非 regression）。
- frontend：`npm ci` → `npx tsc --noEmit` 0 error → `npx vitest run` **1354 passed**（63
  files）→ `npx vite build` OK。

依決策樹挑題：M6 critical path 已全數完成；情境比較 A2 epic 全完成；`WMOM-20260507-02`
清單全數完成。掃過 open issues：`WMOM-20260504-11`（event-driven cost ledger）需劉老師
tariff 假設決策，太大；`WMOM-20260509-F6`（PostgreSQL row-lock）已標🟡；
`WMOM-20260505-23~28`（物理模型）park；`WMOM-20260513-01`（UI v2）等交接書。**選定
`WMOM-20260926-01`**（前次 session `WMOM-20260505-21` 後端完成後拆出的 follow-up，API
已齊全，design 已確認），本次接手第 1 項（前端工作日誌 tab）。

範圍界定（比照 `inspection_schedule` 前後端拆兩 session 先例，本次已是前端）：`work_order.
finish()` 整合 hook 需先讀 `state_machine.py`/`approval_router.py` 決定掛點，涉及設計判斷；
讀取端點 ownership 限制（EMPLOYEE 限本人 vs LEADER/SUPERVISOR 查全員）也是 open decision。
兩者本次不做，只做「本人日誌」前端頁面。

## 2. 實際完成

### 2.1 主要工作

**`frontend/services/dayWorkFormService.ts`（新檔）**：API client，5 endpoints，沿用
`inspectionScheduleService.ts` pattern；`getByDate` 用 404→`null` 而非例外（比照後端
docstring：「尚未建立過回 404，前端可據此決定要不要呼叫建立」）；`readError` 比照
`knowledgeService.ts` 手法解析 FastAPI 422 陣列 detail（見 §2.2 should-fix #3）。

**`frontend/hooks/useDayWorkForm.ts`（新檔）**：`workDate` 為 driver 查當日日誌（`by-date`）
+ 最近歷史（`list`，僅本人 `employee_id`）；`appendActivity` 一律先呼叫 `getOrCreate`
（natural-key idempotent）取得正確 `form.id`，不信任本地 `form` state 是否仍對應目前
`workDate`（寫入端防 race）。

**`frontend/components/workflow/DayWorkFormPanel.tsx`（新檔）**：日期選擇（Asia/Taipei
曆日）+ 當日活動列表（唯讀）+ 新增活動表單（4 種 kind 各自必填欄位，`completed_wo` 從
本人工單選單挑，`item_id` 因無目錄可選維持自由輸入 UUID）+ 最近日誌歷史（僅本人）。

**`frontend/components/workflow/statusUtils.ts`**：新增 `activityKindLabel` +
`todayAsiaTaipei`（Asia/Taipei 曆日，非 UTC，呼應 domain docstring 建議）。

**`frontend/components/workflow/WorkflowPage.tsx`**：新增 `daywork` tab（比照
`inspection_schedule` 併入既有 tab 慣例，非獨立路由）；`myWorkOrderOptions` 供
`completed_wo` 選單使用。

第一輪驗證（review 前）：frontend 1354→**1387 passed**（63→64 files，+33，零
regression）；backend 未動 1237 passed 不變；tsc 0、build OK。

### 2.2 Code review 修復

code-reviewer subagent（讀全部新增/變更檔案全文 + 實際跑過測試）抓到 **1 must-fix +
3 should-fix + 3 nice-to-have**，must-fix 與 3 個 should-fix 全數已修復，2 個
nice-to-have 已採納（1 個記錄未改行為）：

🔴 **Must-fix（已修）**：`useDayWorkForm.ts` 的 `appendActivity` 完成時 `setForm(updated)`
沒有比照 `fetchForm` 既有的 `abortRef` 防護——使用者送出活動期間若切換日期選擇器，
較慢的 append 回應後到時會把 `form` state 蓋回舊那天資料，且不會自我修正（`workDate`
已變，不會再觸發 `fetchForm`）。**寫入目標**本來就正確綁定送出當下的 `workDate`（review
確認無誤），但**讀取端 state** 缺對稱防護。修法：新增 `latestWorkDateRef`（隨每次 render
同步最新 `workDate`），`appendActivity` 捕捉送出當下的 `issuedForDate`，完成後比對
`latestWorkDateRef.current === issuedForDate` 才套用 `setForm`，不一致就跳過（`fetchHistory`
仍照常執行，因為歷史列表非日期綁定）。reviewer 也判定「`useInspectionSchedules` 無獨立
hook test」的既有慣例**不適用**本 hook（有跨請求 staleness 交互的日期綁定可變目標，
`useInspectionSchedules` 沒有這種模式）——採納建議，新增 `hooks/__tests__/
useDayWorkForm.test.ts`（10 測，比照 `useCostData.test.ts` 的 deferred promise + race
測試範式，含一支精準重現此 race 的回歸測試）。

🟡 **Should-fix（已修）**：`WorkflowPage.tsx` 的 `myWorkOrderOptions` 原本共用 Orders
tab 自己的 `useWorkOrders({ farmId, status: statusFilter, search })` 實例——`wo.items`
已被 Orders tab 目前的 `statusFilter`/`search` 過濾過，若使用者在 Orders tab 篩選後
切到工作日誌 tab，「完成工單」選單會悄悄顯示過濾後的子集（甚至空清單）而無任何提示。
修法：另掛一個獨立、無 filter 的 `useWorkOrders({ farmId })` instance（`dayWorkWoHook`）
專供工作日誌 tab 使用。新增 1 個 regression test（斷言兩次 `useWorkOrders` 呼叫的
參數形狀不同：一次只有 `farmId`，一次帶 `status`/`search`）。

🟡 **Should-fix（已修）**：`item_id`（`inspection_item` kind）無 UUID 格式驗證，送出
非法格式會打到後端 422，且 `readError` 原本對陣列型 `detail`（Pydantic v2 validation
error）只會 `JSON.stringify`，把技術性 JSON 丟給現場工程師看。修法：①`canSubmitActivity`
補 UUID regex 提早擋送出；②`readError` 比照 `knowledgeService.ts` 既有手法解析陣列
`detail` 抽每筆 `msg` 串接。新增 1 個 regression test（非法格式即使 result 已填仍
disabled）。

🟡 **Should-fix（已修）**：`workOrderOptions` 變動後、目前選中的 `woId` 若已不在清單內
（工單被重新指派、或列表 refetch 後消失），原本的 auto-select effect 只在 `!woId` 時補選，
不處理「有值但過期」的情況——原生 `<select>` 會自行 DOM 層 fallback 顯示第一個 option，
但 React state 仍停在舊值，使用者若未重新點選就送出，payload 會帶著畫面上看不到、卻
已過期的 `wo_id`。修法：effect 改比對 `workOrderOptions.some(o => o.id === woId)`，不符
就補選第一筆。**寫測試時發現這個 fix 本身還有一個邊界沒處理**：`workOrderOptions` 變成
**空陣列**時（例如全部指派工單今天都已記錄過，見下方 nice-to-have #6）原 effect 直接
`return` 不重置 `woId`，導致 `canSubmitActivity` 仍看到非空字串誤判可送出——已補上
`if (availableWorkOrderOptions.length === 0) { setWoId(''); return; }` 分支修正。
**另外，第一輪測試斷言方式本身有瑕疵**：原測試只斷言 `select.value`，但如 reviewer
所述，瀏覽器對「value 對不到任何 option」的原生 fallback 行為會讓 DOM 顯示值自我「假裝
正確」，掩蓋掉 React state 沒有真的修好的情況——本次驗證時mutation-test 該斷言竟然
在拔掉修法後仍 pass，證實斷言方式選錯了觀察channel。改用「送出時斷言 `onAppendActivity`
收到的 payload」重寫測試，才真正鎖住 React state 而非 DOM 顯示值，重新 mutation-verified
通過。

🟢 **Nice-to-have（已採納，改行為）**：已在今天日誌記錄過的 `completed_wo` 工單從選單
排除（新增 `availableWorkOrderOptions` 衍生自 `workOrderOptions` 過濾 `form.activities`
中 `kind==='completed_wo'` 的 `wo_id`），避免使用者沒注意到已經記過而重複記同一張工單；
全部记录完时顯示提示文案「指派給你的工單今天都已記錄過。」。2 個 regression test，
mutation-verified。

🟢 **Nice-to-have（已採納，文件化未改行為）**：`fmtDate` 重用在 bare `date`
字串（無時間，如 `work_date`）的安全性補充 docstring 說明——目前安全純因 Asia/Taipei
是**正** UTC 偏移，未來若照抄這個手法給負偏移時區（例如美洲）會反向跨日出 bug，明文
警告不可照抄。

🟢 **Nice-to-have（記錄，未修）**：送出中按鈕的 `aria-label` 不會隨「新增中…」視覺文案
變化（螢幕報讀器聽不到忙碌狀態）。需要在共用 `Btn` primitive 加 `aria-busy`/動態
accessible name 支援，牽動全站所有使用 `Btn` 的地方，blast radius 超出本次範圍，
本次不改，於此記錄。

**Scope-narrowing 驗證**（reviewer 獨立核對）：「本人限定」的前端範圍安全——
`WorkflowPage.tsx` 一律傳 `currentUser.id` 給 `useDayWorkForm`，UI 無任何路徑可覆寫；
後端 `append_day_work_form_activity` 也獨立對非本人 append 一律 403（不論角色），
本次改動未隱含比預期更寬的存取權限。讀取端點對任何登入角色開放（`employee_id` query
param 無 ownership 限制）是既有後端行為，正確地標記為本次範圍外（見 §4）。

### 2.3 卡住或延後的事

`work_order.finish()` 整合 hook 與讀取端點 ownership 限制皆延續前次 session 判斷，
仍留給 `WMOM-20260926-01` 後續 session（見 §4）。

## 3. 產出清單

新增 5 個 production 檔案（service 1 + hook 1 + component 1 + statusUtils 修改 +
WorkflowPage 修改）+ 4 個 test 檔（`DayWorkFormPanel.test.tsx` 新增、`useDayWorkForm.
test.ts` 新增、`statusUtils.test.ts`/`WorkflowPage.test.tsx` 追加）。

## 4. 給下個 session 的話

- **`WMOM-20260926-01` 第 1 項（前端本人日誌）已完成**，API + UI 已可端到端操作
  （`/admin/workflow` 工作日誌 tab）。**剩餘 2 項仍 open**：
  1. `work_order.finish()` → day_work_form 自動寫入 hook：先讀 `state_machine.py` +
     `approval_router.py` 現況再拍板掛點（`approve_all` action 轉 `CLOSED` 才是實際
     完工路徑，不是叫 `finish()`），不要照抄 `inspection_scheduler` 的 auto-spawn
     模式（方向相反：那是「排程到期建新工單」，這裡是「工單完工回寫日誌」）。
  2. 讀取端點 ownership 限制（`list`/`by-date`/`{form_id}` 目前對任何登入角色開放）：
     EMPLOYEE 應限本人、LEADER/SUPERVISOR/ADMIN 可查全員；需先確認
     `require_authenticated()` dependency 能否在 handler 內取得 role/actor（目前簽章
     只回傳 `None`，需改用 `get_current_actor(request)`，注意過渡期 `enforce=false`
     下的行為需與既有雙模式慣例相容，不能讓未登入呼叫在過渡期整批 401）。
- **未受自動化測試保護的部分**：無重大缺口。`useDayWorkForm.ts`/`dayWorkFormService.ts`
  已補 10 個 hook 測試（含 race 回歸），`DayWorkFormPanel.tsx` 30 測涵蓋所有分支，
  `WorkflowPage.tsx` 的 daywork tab 接線 32 測涵蓋。**Nice-to-have #7（送出中按鈕
  aria-busy）未修**，若要修需動共用 `Btn` primitive，牽動全站，留給日後專門評估。
- **附帶記錄**：`myWorkOrderOptions` 現在走獨立 `dayWorkWoHook = useWorkOrders({ farmId
  })`（無 filter），與 Orders tab 的 `wo` 是兩個獨立 instance——若未來要優化網路請求數
  （目前同一 farm 的工單列表會打兩次 API），可以考慮把「全部工單」提升到更高層共用，
  但目前架構（每個 tab 各自掛 hook instance，不論是否為目前 active tab）本就是既有
  `mrHook`/`invHook`/`inspHook`/`approvals` 的慣例，非本次新增的反模式。

## 5. Open questions（park，同前次 session）

- `work_order.finish()` hook 應該掛在 `WorkOrderRepository.transition()` 內部還是
  `approval_router` 的 `approve_all` 專屬路徑？留給下個 session 讀完現況程式碼再決定。
- 讀取端點的角色分級是否也要延伸到 TREASURY/ADMIN？本次未深究。

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline：backend `1237 passed, 7 skipped, 1 xfailed`；frontend `npx tsc
  --noEmit` 0 error、`npx vitest run` **1354 passed**（63 files）、`npx vite build`
  OK。
- 第一輪（review 前）：frontend `1387 passed`（64 files，+33 新測，零 regression）；
  backend 未動。
- Review 修復後（最終）：frontend **1402 passed**（65 files，+15 新測：`useDayWorkForm.
  test.ts` 新檔 10 測 + `DayWorkFormPanel.test.tsx` +4 + `WorkflowPage.test.tsx` +1，
  零 regression）；tsc 0、build OK；backend 重跑確認未動 `1237 passed` 不變。
- **Mutation-verified**（`cp` 備份至 scratchpad/tmp + 逐一還原確認，非 `git checkout`，
  因新檔為 working tree 未追蹤/剛提交檔案）：
  1. `canSubmitActivity`（completed_wo/inspection_item/patrol/training 皆改回
     `return true`）：5 個測試如預期 fail（workOrderOptions 為空提示、自動補選、
     inspection_item/patrol/training 未填齊 disabled）。
  2. `resetFields()` 拔掉：「送出成功後表單欄位重置」測試如預期 fail。
  3. 送出 payload 改成不分 kind 全帶欄位：「onAppendActivity 帶正確 payload」測試如
     預期 fail。
  4. `WorkflowPage.tsx` `myWorkOrderOptions` filter 拔掉：「只含 assignee_id 等於
     目前使用者的工單」測試如預期 fail。
  5. `onWorkDateChange={setDayWorkDate}` 改 no-op：「切換工作日誌面板日期」測試如
     預期 fail。
  6.（review must-fix 修復）`useDayWorkForm.ts` 的 `latestWorkDateRef` 比對拔掉、
     直接 `setForm(updated)`：新增的 race regression test 如預期 fail（`work_date`
     斷言錯誤，證實 must-fix 修法確實堵住那個洞）。
  7.（review should-fix #2 修復）`dayWorkWoHook = wo`（改回共用同一 instance）：
     「工作日誌面板的工單選單走獨立 useWorkOrders instance」測試如預期 fail。
  8.（review should-fix #3 修復）UUID regex 拔掉：「item_id 非合法 UUID 格式」測試
     如預期 fail。
  9.（review should-fix #4 修復）`stillValid` 比對拔掉（改回只判斷 `!woId`）：
     - 「指派的工單今天都已記錄過（選單為空）」測試如預期 fail（確認空清單分支的
       獨立防護有效）。
     - 「已選 woId 消失」測試**第一版斷言 `select.value` 未能抓到這個 mutation**
       （瀏覽器原生 `<select>` 對過期 value 的 DOM fallback 顯示掩蓋了 React state
       未修好的事實）——誠實記錄這個測試設計失誤，已改用「斷言送出 payload」重寫，
       重新 mutation-verified 通過（fail 訊息正確顯示 `wo_id: "wo-2"` 而非
       `"wo-3"`）。
  10.（review nice-to-have #6 修復）「已記錄過濾除」邏輯改成 no-op filter：2 個
      regression test 如預期 fail。

## Review

code-reviewer subagent（讀全部新增/變更檔案全文，非純靜態掃描；實際跑測試 79 個）：
**1 must-fix，3 should-fix，3 nice-to-have**，詳見上方 §2.2。獨立核對「本人限定」
scope-narrowing 前後端一致無漏洞（見 §2.2 末段）；獨立判定 `useInspectionSchedules`
「無專屬 hook test」的既有慣例不適用本 hook（有跨請求 staleness 交互），建議之後
若再遇到「日期/單一可變目標 + 並行讀寫」這類 hook，優先考慮補專屬 hook test 而非
沿用「純過濾清單」類 hook 的慣例。

## Wrap-up

- must-fix 全修 + 3 個 should-fix 全修 + 2 個 nice-to-have 採納（1 個記錄未改行為），
  皆 mutation-verified（含發現並修正自己第一版某個 should-fix 修法本身的邊界缺口、
  以及某個測試斷言 channel 選錯導致測不出問題的自我修正，詳見上方 Verify #9）。
- `ISSUES.md`（`WMOM-20260926-01` 更新 completion summary，標記前端 part 完成、
  剩餘 2 項仍 open）、`STATUS.yaml`（`last_updated`/`issue_stats`）、`TODO.md`
  （最後更新段落）已同步更新。
- 誠實揭露：`work_order.finish()` hook 與讀取端點 ownership 限制仍未做（設計待決，
  見 §4）；送出中按鈕 `aria-busy` 未修（需動共用 Btn primitive，blast radius 較大，
  記錄為已知限制）；`myWorkOrderOptions` 現在多打一次 `/api/workflow/work-orders`
  （同 farm 的工單列表在 Orders tab 與工作日誌 tab 各自獨立 fetch 一次），屬既有
  架構慣例的延伸而非新反模式，已在 §4 記錄供未來評估是否合併。
