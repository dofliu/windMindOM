# Work Log — 2026-06-06 — WorkOrderDetailModal component render 測試

**Issue**: WMOM-20260606-03
**Milestone**: M5（測試覆蓋持續工作 / EPIC-M5 測試覆蓋擴大）
**Branch**: claude/issue-WMOM-20260606-03-2026-06-06
**Owner**: Claude (autonomous worker, session 2026-06-06 第三輪)

---

## 目標

延續 component render 測試系列，為 `components/workflow/WorkOrderDetailModal.tsx`（933 行）
補 render 測試。本元件是 `/admin/workflow` 工單詳情 + 狀態機 transition 控制 modal：

- 依 `work_order.status` 顯示對應 action 按鈕（draft→派工 / dispatched→開始作業 /
  in_progress→新增進度·完工 / awaiting_signoff→駁回 / closed→重開 + cancel 規則）
- 點按開 collapsible inline form 收必填欄位 → 呼對應 callback（7 個 transition）→
  成功 patch 本地 WO + 收 form、失敗回填錯誤卡
- offshore farm 的 start_work 強制 weather_window_id 分支

是前份 handoff（CreateMaterialRequestWizard）點名的「detail modal」系列第一個。

## Preflight

- `git status` clean，分支 `claude/issue-WMOM-20260606-03-2026-06-06`（自環境 `main` 開）
- backend baseline：638 passed / 1 xfailed ✓
- frontend baseline：439 passed（23 files）✓（上輪 CreateMaterialRequestWizard PR #89 已 auto-merge 進 main）
- stack-aware：open PR 全為 pre-flywheel stale draft（#30–#68），無進行中 WIP → 安全開新工

## 實作

新增 `components/workflow/__tests__/WorkOrderDetailModal.test.tsx`（**42 tests**）。

另含一行 **production 修正**（review must-fix）：`WorkOrderDetailModal.tsx` finish 驗證
`!actualHours` → `!actualHours.trim()`。原邏輯下「只敲空白」的 `actual_hours`，`Number('   ')`
回 0 並通過 `hours < 0` 檢查 → 被當成 0 工時靜默送出，與全 codebase 其他欄位一律 `.trim()` 的
慣例不一致。改先 trim 再判空，純空白會正確觸發「實際工時必填」驗證。

**Mock 策略**：本元件不打 fetch、不依賴自訂資料 hook，依賴僅
- `useTheme`（ThemeProvider）+ `useCurrentUser`（UserProvider）→ render wrapper 雙層包裹
- 7 個 transition callback 由 prop 傳入 → 全部 `vi.fn().mockResolvedValue(makeWO(...))`
- `beforeEach` 清 `localStorage` 讓 UserProvider 一律 fallback 到 DEFAULT_USER（Alice Chen），
  dispatch form 的 assignee fallback 斷言才穩定

`makeWO` 工廠結構式滿足 `WorkOrderResponse`（不用 `as`，overrides 末尾 spread）；
`resolveWith(base, patch)` 產生「回傳同單帶 status 變化」的 mock，驗成功後本地狀態更新。

**覆蓋契約**：
- 殼層 / 靜態展示：dialog aria-label / h2 標題 / business_key / turbine / typeLabel /
  detail grid（crew·est hours 有值 vs —、source alarm —）/ description /
  progress_notes（空不渲染 vs 有值渲染計數+內容）/ 完工摘要區（closed 顯示實際工時·後續處理·摘要·未完事項）/
  cancel·reject·reopen 原因卡 / awaiting_signoff 待簽核提示 / lang=en 殼層與 pill
- status-driven 按鈕可見性：draft（派工+取消，無開始/完工/重開）/ dispatched（開始作業+取消）/
  in_progress（新增進度+完工+取消）/ awaiting_signoff（只有駁回、無取消）/ closed（只有重開）/ reopened（開始作業）
- dispatch form：空 assignee→fallback currentUser.id / 已有 assignee 留空→用既有 / 輸入→trim /
  成功→本地狀態更新為已派工（派工鈕消失·開始作業出現）/ 失敗→錯誤卡且 form 不收合 /
  submitting 中態「派工中…」+disabled（受控 Promise）
- start_work form：onshore→onStartWork(id,false) / offshore→空 weather window Start disabled /
  offshore→填值→onStartWork(id,true,wwid) 且 trim
- progress / finish form：progress 空 note→Add disabled、填→onUpdateProgress(id,trim) /
  finish 空工時→驗證錯誤不呼 onFinish / 填工時→onFinish 完整 payload（trim·null 空值）/
  followup_needed→顯示未完事項·追蹤備註欄位
- reject / cancel / reopen form：各自空 reason→disabled、填→對應 callback(id, reason)
- 關閉路徑：點 backdrop→onClose / 點 content（標題）→stopPropagation 不 onClose / footer Close→onClose

**眉角**：
- 多個 footer 開啟按鈕與 form 提交按鈕 **aria-label 同字串**（如 footer「駁回」撞 form 提交「駁回」、
  footer「開始作業」撞 onshore form「開始作業」、「重開」「取消工單」同理）→ getByRole 會多重命中。
  解法：抽 `formSubmit(cancelName, submitName)` helper，以 **form 內 Cancel/返回 按鈕**
  （名稱皆唯一、不與 footer 撞）的 `parentElement` 同層容器 `within(...)` scope 提交按鈕。
- footer Close 與 header ✕ 皆 aria-label「關閉」→ `getAllByRole` 取最後一個（footer）。
- submitting 中態以受控 Promise（手動 resolve）斷言中間態 + 收尾 resolve 讓 form 收合避免 act 警告。

## Code review（code-reviewer subagent）

對 staged diff 跑兩輪 code-reviewer。彙整後採納情形：

**must-fix（採納）**
- finish `actual_hours` 純空白被當 0 工時送出 → production 改 `!actualHours.trim()` + 補
  「純空白 → 驗證錯誤不呼 onFinish」regression test。
- `footerBtn` 在 form open 後與 form 提交鈕同名會多重命中 → 加 helper 文件 comment 明確限定
  「僅 form 未開時可用」。
- `actual_hours = 0` 合法 happy path 未覆蓋 → 補 test 驗 0 工時可送出（守 `< 0` 而非 `<= 0`）。

**should-fix（採納）**
- offshore 空 weather window 的 disabled gating 改用 `formSubmit('取消','開始作業')` scope（穩健）
  + 啟用按鈕 `find` 加 `expect(enabled).toBeDefined()` 防呆。
- `cancelled` 狀態按鈕可見性完全缺漏 → 補「無任何 action、只剩 header ✕ + footer Close」test。
- 非 dispatch transition 的共用 error path 未覆蓋 → 補 cancel reject → 錯誤卡 + form 不收合 test。
- `cancel` / `reopen` 空 reason disabled gating 缺漏 → 補 disabled 斷言。
- progress note 純空白 disabled、dispatch assignee 純空白 fallback → 補對稱 test。

**nice-to-have（採納）**
- `followup_note` trim 行為併入 finish happy path 驗證。
- lang=en footer action 按鈕英文化（Dispatch / Cancel）。
- `reopened` 不顯示取消工單。
- dispatch 失敗後點 form Cancel → `resetForms` 清除錯誤卡。

**未採納（記錄理由）**
- footer Close 改 `data-testid` / 不同 aria-label：需動 production 僅為測試便利（anti-pattern）；
  現以 `getAllByRole(...)` 取最後一個（header ✕ + footer 共 2 件）已足夠穩定且有註解說明。

## Verify

- `npx tsc --noEmit`：0 error
- `npx vitest run`：481 passed（439 baseline + 42 新，零 regression）
- `npx vite build`：✓
- backend 未動（僅一行 frontend tsx production 修正），638 / 1 xfailed 不受影響

## 收尾 / 下次接手

- 完工開正常 PR（CI 綠 → auto-merge）。
- 剩餘未測 workflow 元件：`MaterialRequestDetailModal`（902，detail modal，需 mock 多 action callback +
  狀態機 tab）/ `TurbineDetail`（1056，monitoring 大元件）。
- 非 render 方向：M5-2 ChromaDB（需劉老師拍板 chromadb 依賴 + 向量檔來源）/
  stale PR triage（#30–#68 共 22 筆 pre-flywheel draft）。
