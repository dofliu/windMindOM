# 2026-09-24 — SettingsPage.tsx authFetch 補齊（WMOM-20260923-10 sub-task 3/7）

## Issue

`WMOM-20260924-03`（`WMOM-20260923-10` 前端 authFetch 稽核清單第 3 項，M6 auth cutover
`WMOM-20260716-05i` 前置阻塞）

## Claim

前一 session（WMOM-20260924-02）完成 `FarmSelector.tsx` 後，STATUS.yaml / ISSUES.md /
TODO.md 一致建議下一支優先接 `SettingsPage.tsx`（含多處 `SUPERVISOR` 寫入，enforce 開啟後
`/admin/settings` 整頁設定會靜默 401 失效，風險同 `FaultInjectionPanel`/`FarmSelector`）。

## Implement

`frontend/components/SettingsPage.tsx` 11 處裸 `fetch` 呼叫（行號 134/143/151/170/187/
198/216/239/250/264/294，與 ISSUES.md 稽核清單記錄一致）全改 `authFetch`：

- 5 條 GET（`refreshWindStatus`/`refreshGridStatus`/`refreshSourceKind`/mount 時
  turbine-spec + presets）——後端皆掛 `require_authenticated()`
- 6 個 POST（`handleSetProfile`/`handleSetCustomWind`（皆 `/api/config/wind`）、
  `handleSetGridProfile`/`handleSetCustomGrid`（皆 `/api/config/grid`）、
  `handleSetPreset`/`handleApplySpec`（皆 `/api/config/turbine-spec`））——後端逐一確認
  （`modules/monitoring/server/routers/config.py`）皆掛 `require_role(Role.SUPERVISOR)`，
  風險與 `OperatorControlCard`/`FaultInjectionPanel` 同級。

比照姊妹 PR（WMOM-20260923-07/-09/-20260924-01/-02）手法：只換 fetch 呼叫方式，不動業務
邏輯 / payload / 錯誤處理。

## Verify

- 新增測試檔 `frontend/components/__tests__/SettingsPage.test.tsx` 新描述區塊
  「SettingsPage — authFetch 稽核（WMOM-20260923-10）」，+8 測：
  - 已登入 → mount 5 條 GET 皆帶 `Authorization: Bearer <token>`（合併一測，逐一斷言）
  - 已登入 → 風況 profile POST / 自訂風況 POST / 電網 profile POST / 自訂電網 POST /
    機型 preset POST / 套用規格 POST，各 1 測直接斷言該次呼叫的 header
  - 未登入（無 token）→ 上述 5 GET + 6 POST 呼叫皆不帶 header（過渡期行為不變對照組）
- **Mutation-verified**：`sed -i 's/authFetch(/fetch(/g'` 全部改回裸 fetch 後單獨跑
  `-t "authFetch"` 子集，8 測中 7 測如預期 fail（唯一「未登入」對照組本質斷言
  `toBeUndefined()`，改回裸 fetch 仍為 undefined，故維持通過——這是預期行為，非測試盲區），
  確認後已用備份還原（`cp /tmp/SettingsPage.tsx.bak` 回正確版本，非 `git checkout`——
  避免誤蓋掉尚未 commit 的新檔案）。
- backend 未動：`pytest`（7 module 路徑 + tests/）**1103 passed, 7 skipped, 1 xfailed**
  不變。
- frontend：`tsc --noEmit` 0 error；`vitest run` **1236 → 1244 passed**（58 files 不變，
  +8 新測）；`vite build` OK（bundle size 無異動級距）。

## Review

code-reviewer subagent review：0 must-fix、0 should-fix、2 nice-to-have，**Approve**。

- 逐一交叉核對後端 `require_authenticated()`/`require_role(SUPERVISOR)` 標註與本次改動的
  11 處呼叫皆吻合，確認 `grep -n "fetch("` 無殘留裸 fetch。
- 驗證新增 8 測非空泛斷言：`setAuthToken`/`clearAuthToken` 走真實 `authClient.ts`（非
  mock），`callsExact` 用 `endsWith` 避免 `turbine-spec` 與 `turbine-spec/presets`
  URL 前綴誤判；交叉核對本次 mutation-verified 的說法屬實（工作記錄的 7/8 fail 結果與
  獨立重新推演一致）。
- 對既有 24 測無迴歸風險：既有測試用 `postBodies`/`lastPostBody`（URL 子字串 + method）
  比對，不斷言 `fetchMock` 呼叫的完整參數簽章，故 `authFetch` 額外帶入的 `{ headers: {} }`
  不影響既有斷言。
- 2 個 nice-to-have（皆不需本次修改）：
  1. `refreshWindStatus`/`refreshGridStatus`/mount 時 turbine-spec 相關 fetch effect 未檢查
     `r.ok` 就呼叫 `.json()`（`refreshSourceKind` 已有 `r.ok ? r.json() : null` 防護，其餘
     沒有）——**此為既有行為、非本次引入**，但隨 M6 cutover 逼近漸成真實缺口：enforce 開啟後
     真實 401 會被當成正常回應解析，`refreshWindStatus` 甚至會在 401 時仍把 `apiConnected`
     設 `true`。建議在 `WMOM-20260716-05i` cutover 前另開一輪，把 `SettingsPage.tsx` 現有的
     fetch effect 統一補上 `r.ok` guard（不只本次改動的呼叫點）。本次不修，已記錄於此供
     cutover 前參考。
  2. 提醒 `ISSUES.md` 當下 staging 狀態（review 當下尚未一併 commit）——已確認為時序問題，
     所有檔案已在同一個 commit（`6b2dc11`）內一併送出，非遺漏。

## Wrap-up

`WMOM-20260923-10` 稽核清單（7 支元件）本次完成第 3 支：`FaultInjectionPanel`（done）/
`FarmSelector`（done）/`SettingsPage`（**本次 done**）→ 尚餘 4 支純讀取元件
`CostPage`/`EventComparisonView`/`HistoryPage`/`TrendChartPanel`（風險較低，enforce 後
仍可用但 401 會被吞、UI 卡在載入態不會導回登入頁）。

**未自動化保護的部分**：本次修復純屬「fetch → authFetch」包裝置換，無新增業務邏輯；
測試以 `Authorization` header 存在與否為斷言依據，未涵蓋「真實後端在 enforce=true 下
是否真的回 401 並觸發導回登入頁」的端到端行為（該邏輯本身已由 `authClient.test.ts` 涵蓋，
本檔不重複驗證）。

**下次接手**：建議依序做 `CostPage`/`EventComparisonView`/`HistoryPage`/`TrendChartPanel`
四支純讀取元件收尾整份稽核清單；完成後回頭勾掉
`docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表對應項。

**附帶提醒**：canonical routine 文件 `docs/routines/autonomous-daily-worker-prompt.md`
仍停在 v3（baseline backend 638 / frontend 59），已落後於本次 cron 送入的 prompt（v4.1，
baseline backend 1103 / frontend 1236，含「自我測試」/mutation 驗證/降級模式框架），前一
session 已提醒過，再次提醒劉老師找時間把 cron trigger 目前設定同步回這份文件。
