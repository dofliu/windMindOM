# 2026-09-24 — CostPage.tsx authFetch 補齊（WMOM-20260923-10 sub-task 4/7）

## Issue

`WMOM-20260924-04`（`WMOM-20260923-10` 前端 authFetch 稽核清單第 4 項，M6 auth cutover
`WMOM-20260716-05i` 前置阻塞）

## Claim

Preflight：`git checkout main && git pull` 後在最新 main（`5bae625`）上開分支；stack-aware
檢查（GitHub MCP 可用）`mcp__github__list_pull_requests(state=open)` 回傳空陣列，無上個
session 遺留的 open PR，可直接挑新工作。自我測試 baseline 全綠：backend
**1103 passed / 7 skipped / 1 xfailed**、frontend **1244 passed（58 files）**、tsc 0、
build OK，與 `docs/routines/autonomous-daily-worker-prompt.md` 記錄的 baseline 一致，無
regression 需先修。

依 `TODO.md` / `STATUS.yaml` / `ISSUES.md` WMOM-20260923-10 建議順序，前 3 支
（`FaultInjectionPanel`/`FarmSelector`/`SettingsPage`，皆含 SUPERVISOR 寫入）已完成，
本次接續尚餘 4 支純讀取元件中排序第一的 `CostPage.tsx`。

## Implement

`frontend/components/CostPage.tsx` 僅 1 處裸 `fetch` 呼叫（行 693，mount 時
`GET ${API_BASE}/api/farms` 供 dataset/farm selector 用）改 `authFetch`：

- 後端確認（`modules/monitoring/server/routers/farms.py` `list_farms`）掛
  `require_authenticated()`（任何登入者可讀，非 SUPERVISOR-only）。
- `import { authFetch } from '../services/authClient'` 加在既有 import 區塊末。
- 只換 fetch 呼叫方式，不動 `!res.ok` early-return / payload 解析邏輯，比照姊妹 PR
  WMOM-20260923-07/-09/-20260924-01/-02/-03 手法。

## Verify

- 新增測試檔區塊 `describe('CostPage — authFetch 稽核（WMOM-20260923-10）')`（+2 測，比照
  `FarmSelector.test.tsx` 同名 describe 的 `authHeaderOf`/`callsMatching` 慣用法）：
  - 已登入 → mount GET `/api/farms` 帶 `Authorization: Bearer <token>`
  - 未登入 → mount GET `/api/farms` 不帶 header（過渡期行為不變對照組）
- **Mutation-verified**：`authFetch(...)` 手動改回 `fetch(...)` 後單獨跑
  `-t "authFetch"` 子集，2 測中「已登入」測如預期 fail（`expected undefined to be 'Bearer
  test-token-costpage'`）、「未登入」對照組維持 pass（預期行為，非測試盲區），確認後用
  `/tmp/CostPage.tsx.bak` 備份還原（非 `git checkout`，避免誤蓋掉尚未 commit 的新測試檔）。
- backend 未動：`pytest`（7 module 路徑 + tests/）**1103 passed, 7 skipped, 1 xfailed**
  不變。
- frontend：`tsc --noEmit` 0 error；`vitest run` **1244 → 1246 passed**（58 files 不變，
  +2 新測）；`vite build` OK（bundle size 無異動級距）。

## Review

`code-reviewer` subagent review：**Approve，0 must-fix**。

- 逐項核對：全檔僅 1 處 fetch 呼叫已全改 `authFetch`；`authFetch` 簽章與呼叫點吻合，
  `!res.ok` 既有邏輯不受影響。
- 獨立重跑 mutation-verify（reviewer 自己再做一次 revert→測試 fail→還原），結果與本次
  聲稱一致；確認新測試斷言真實 `RequestInit.headers.Authorization`，非空泛斷言。
- 與姊妹 PR `FarmSelector.test.tsx` 慣用法比對，結構一致（獨立 describe block、
  `authHeaderOf` helper、`setAuthToken`/`clearAuthToken`），規模對應本檔僅 1 處呼叫而簡化。
- 對既有 15 測無迴歸風險：新 describe block 有自己的 `beforeEach`/`afterEach`，不影響原
  `describe('CostPage 成本模型主入口')` 區塊；`localStorage.clear()` / `clearAuthToken()`
  避免 token 洩漏到其他測試。
- **附帶說明**：reviewer 過程中誤執行 `git checkout -- CostPage.tsx` 把working tree
  重置回 HEAD（wipe 掉本次未 commit 的修改），已自行發現並手動重建成一致的 diff；本
  session 事後獨立用 `git diff` 核對內容與原始修改逐行相同、並重跑
  `tsc --noEmit` + 全套 `vitest run`（1246 passed 不變）確認 working tree 未受影響。

## Wrap-up

`WMOM-20260923-10` 稽核清單（7 支元件）本次完成第 4 支：`FaultInjectionPanel`（done）/
`FarmSelector`（done）/`SettingsPage`（done）/`CostPage`（**本次 done**）→ 尚餘 3 支純讀取
元件 `EventComparisonView`/`HistoryPage`/`TrendChartPanel`。

**未自動化保護的部分**：本次修復純屬「fetch → authFetch」包裝置換，無新增業務邏輯；測試以
`Authorization` header 存在與否為斷言依據，未涵蓋「真實後端在 enforce=true 下是否真的回
401 並觸發導回登入頁」的端到端行為（該邏輯本身已由 `authClient.test.ts` 涵蓋，本檔不
重複驗證）。

**下次接手**：建議依序做 `EventComparisonView`/`HistoryPage`/`TrendChartPanel` 三支純讀取
元件收尾整份稽核清單；完成後回頭勾掉
`docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表對應項。

**附帶提醒**：canonical routine 文件 `docs/routines/autonomous-daily-worker-prompt.md`
本次讀取版本已是 v4.1（baseline backend 1103 / frontend 970，實際本次 frontend baseline
已到 1244，非 970——推測 v4.1 文件內 baseline 數字本身也已落後於近期多個 session 的累積
新增測試，非本 session 造成）；建議劉老師找時間把該檔 baseline 數字同步到最新，避免下次
session preflight 誤判「多出的測試數量是否正常」。
