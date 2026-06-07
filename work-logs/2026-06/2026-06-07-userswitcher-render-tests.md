# Work Log — 2026-06-07 — UserSwitcher component render 測試

**Issue**: WMOM-20260607-01
**Milestone**: M5（測試覆蓋持續工作 / EPIC-M5 測試覆蓋擴大）
**Branch**: claude/issue-WMOM-20260607-01-2026-06-07
**Owner**: Claude (autonomous worker, session 2026-06-07 第一輪)

---

## 目標

延續 component render 測試系列，為 `components/UserSwitcher.tsx`（231 行）補 render 測試。
本元件是 sidebar 底部 mock-login 切換器（WMOM-20260510-01 Part B）：

- trigger 鈕顯示目前 user 名 + 主要 role pill，向上彈出 dropdown（listbox）
- dropdown 列出所有 `is_active` fixture user（filter 掉停用者），點選即切換
- 目前 user 標 `aria-selected` + 「使用中 / Active」；`dev_mode_only` user 標「dev / dev only」tag
- 多角 user（Owner）role 以「 / 」join；email 以「 · 」附後
- 無障礙：trigger `aria-haspopup`/`aria-expanded`、Escape 關閉、click-outside 關閉、
  option Enter/Space 觸發選取

是前份 handoff（AnnualBudgetPanel）點名「render 測試剩餘 untested 元件」清單首位（UserSwitcher 231 行，最小一支）。

## Preflight

- `git status` clean，分支 `claude/issue-WMOM-20260607-01-2026-06-07`（自 `main` 開）
- backend baseline：638 passed / 1 xfailed ✓
- frontend baseline：665 passed（29 files）✓（上輪 AnnualBudgetPanel PR #95 已 auto-merge 進 main）
- stack-aware：open PR 全為 flywheel 上線前 stale draft（#30–#68 共 22 筆），無進行中 WIP → 安全開新工

## 實作

新增 `components/__tests__/UserSwitcher.test.tsx`（**27 tests**——初版 24 + code review 採納補 3，
純測試零 production 變更）。

**Mock 策略**：本元件 props 僅 `lang`，資料全來自 `useCurrentUser` context。為精確控制
currentUser / availableUsers（含一名停用者驗 `is_active` filter）並 spy `setCurrentUser`
接線，**mock 掉 `useCurrentUser` hook**（`vi.mock` factory 於 call time 讀 module-level
`mockCtx`，每測試前 `setCtx(...)` 重設）；`useTheme` 用真實 ThemeProvider。
provider 本體行為（localStorage 持久化、fixtures）已由既有 `services/__tests__/mockUsers.test.ts`
（20 tests）獨立覆蓋，故 component 測試 mock hook 不犧牲整合保真度。

工廠 `makeUser` 結構式滿足 `MockUser`（不用 `as`）；衍生 ALICE / BOB / OWNER / INACTIVE 四 fixture。
`openDropdown(lang)` helper 點 trigger 後回傳 listbox。

**覆蓋契約**：
- 殼層 / 關閉態：trigger `aria-haspopup=listbox` + 初始 `aria-expanded=false` / 目前 user 名+role（zh）/
  初始不渲染 listbox / Owner 多角「員工 / 組長 / 財務 / 老闆」join 顯示於 trigger
- 展開 / 收合：點開（`aria-expanded=true`+listbox）/ 再點收合 / listbox `aria-label`+「模擬登入（dev）」標頭
- 選項清單：每 active user 一 option / `is_active=false` 被 filter / `aria-selected` 反映 currentUser /
  「使用中」僅一次 / `dev_mode_only` 標 dev tag（非 dev 不標）/ role join + email「 · 」附後 / email 空不附「 · 」
- 選取接線：click option → `setCurrentUser(user)` + 收合 / Enter / Space → 同 / 其他鍵（Tab）不觸發且維持開啟
- 關閉路徑：click-outside（body mousedown）關 / dropdown 內 mousedown 不關 / Escape 關
- 語系（en）：trigger aria-label + role 英文 / 標頭+aria-label+dev only+Active 英文 / 多角 join 英文

**眉角**：
- 多元素命中防呆：trigger 內名稱/role 與 dropdown option 內同字串會撞 → 殼層斷言一律
  `within(trigger)` scope；option 內斷言一律 `within(listbox)` 或 `closest('[role="option"]')` scope。
- 「使用中」用 `getAllByText(...).toHaveLength(1)` 守「僅 active option 顯示」而非裸 `getByText`（避假綠）。
- click-outside：`fireEvent.mouseDown(document.body)`——body 非 dropdownRef 後代 → `contains` 回 false → 關閉。

## Code review（code-reviewer subagent）

對 staged diff 跑 code-reviewer，回 1 must-fix + 4 should-fix + 2 nice-to-have。

**must-fix（婉拒 — 誤判）**
- #1 指 `getByText('Owner (dev)')` 在 `dev_mode_only=true` 時必拋錯（理由：name div textContent
  含巢狀 dev span = `'Owner (dev)dev'`，exact match 不命中）。**婉拒**：RTL 預設 `getByText` 以
  `getNodeText` 比對「直接 text-node 子節點」串接值，**不含**巢狀 element 內文，故可比對文字僅
  `'Owner (dev)'`，nested dev span 不干擾。**實證**：初版 24 tests 全綠（含 line 220/276/339
  三條被點名「必拋錯」的測試），若真 throw 整 suite 會 error。已加 inline comment 防後人混淆。
  （與 MonthlyReportPanel review must#1 同類 `getByText` vs `textContent` 誤判。）

**should-fix（採納 3 / 婉拒 1）**
- #2 `vi.clearAllMocks()` → `vi.restoreAllMocks()` 與 DispatchModal.test 一致 → **採納**。
- #3 缺 Carol（treasury 單角）fixture → **採納**：補 CAROL fixture + 「treasury 單角 trigger 顯示
  『財務』」test，獨立守住 `formatRoles` treasury 標籤（原僅在 OWNER 多角 join 間接覆蓋）。
- #5 「點選目前 user 自己 option」行為未測 → **採納**：補 test 守住「無自選 guard、仍呼 setCurrentUser
  + 收合」，未來若加 guard 會被捕捉。
- #4 移除與 beforeEach 預設相同的冗餘 `setCtx()` → **婉拒**：list 行為測試顯式列 availableUsers
  反而自我說明意圖，churn 低價值。

**nice-to-have（採納 2）**
- #6 email-empty test 的 `makeUser({email:''})` 沿用 ALICE id 造成隱式 isActive=true → **採納**：
  改用 BOB id（與 currentUser 不同）斷言 `組長`，移除混淆。
- #7 `availableUsers=[]` edge case 未測 → **採納**：補 test 驗 dropdown 展開但 0 option + 標頭仍渲染。

採納後新增 3 tests（Carol / 空陣列 / 自選自己）→ 24 → 27。

## Verify

- `npx tsc --noEmit`：0 error
- `npx vitest run`：692 passed（665 baseline + 27 新，零 regression）
- `npx vite build`：✓
- backend 未動（純新增 frontend 測試），638 / 1 xfailed 不受影響

## 收尾 / 下次接手

- 完工開正常 PR（CI 綠 → auto-merge）。
- render 測試剩餘 untested 元件：`TrendChartPanel`（225，recharts 重元件）/ `EventComparisonView`（332）/
  `MaintenanceHub`（439）/ `FarmSelector`（532）/ `FaultInjectionPanel`（555）/ ui primitives。
- 非 render 方向：M5-2 ChromaDB（🟡 需劉老師拍板 chromadb 依賴 + 向量檔來源）/
  M5-5 `/field/` mobile Part B-2（🟡 需劉老師拍板現場工程師身分 / 完工流程）/
  stale PR triage（#30–#68 共 22 筆 pre-flywheel draft）。
