# 2026-09-24 — `FaultInjectionPanel.tsx` authFetch 補齊（WMOM-20260923-10 sub-task 1/7）

> Session 類型：實作
> Session 長度：短
> 主導：autonomous worker（cron，v4.1）
> 結果：`WMOM-20260924-01` 完成，`WMOM-20260923-10`（前端 authFetch 稽核清單）7 支元件中第 1 支
> 收尾，尚餘 6 支。

---

## 1. Session 目標

WMOM-20260924-01（`WMOM-20260923-10` sub-task）。上次 session（WMOM-20260923-09）稽核發現
7 支元件仍有裸 `fetch` 未帶 `Authorization` header，標記為 M6 auth cutover 前置阻塞。本次接手
第一支：`FaultInjectionPanel.tsx`（`/admin` 故障模擬頁，555 行），依 issue 建議優先序（含
SUPERVISOR/ADMIN 寫入的優先）挑選，因其 3 個寫入端點（inject/clear/run-plan）皆
`require_role(Role.SUPERVISOR)`，風險與已修復的 `OperatorControlCard` 同級。

## 2. 實際完成

### 2.1 主要工作

- **Preflight 確認**：`git status` clean、無殘留分支（`git ls-remote --heads origin 'claude/*'`
  略——本次有 GitHub MCP，`mcp__github__list_pull_requests` 確認無 open PR，無 stack 衝突）。
- **Baseline 自我測試**：backend `1103 passed, 7 skipped, 1 xfailed`；frontend `npx tsc --noEmit`
  0 error、`npx vitest run` `1227 passed`（58 files）、`npx vite build` OK——皆與
  STATUS.yaml/TODO.md 記錄的既有基準一致，非本次造成的 regression。
- **`frontend/components/FaultInjectionPanel.tsx`**：加
  `import { authFetch } from '../services/authClient'`，6 處 `fetch(` 全改 `authFetch(`：
  - mount 時 2 條 GET（`/api/faults/scenarios`、`/api/faults/test-plans`）
  - `refreshActive`（`/api/faults/active`，供 mount + 3 秒輪詢 + inject/clear 後重呼叫共用）
  - `handleInject`（POST `/api/faults/inject`，SUPERVISOR）
  - `handleClearAll`（POST `/api/faults/clear`，SUPERVISOR）
  - `handleRunPlan`（POST `/api/faults/test-plans/{id}/run`，SUPERVISOR）
  - 僅替換呼叫方式本身，method / headers（`Content-Type`）/ body（`JSON.stringify(...)`）參數
    完全不動。
- **`frontend/components/__tests__/FaultInjectionPanel.test.tsx`**：新增
  「authFetch 稽核（WMOM-20260923-10）」describe block，5 個新測試：
  1. 已登入（`setAuthToken`）→ mount 時 3 條 GET 皆帶 `Authorization: Bearer <token>`
  2. 已登入 → POST inject 帶 Authorization header
  3. 已登入 → POST clear 帶 Authorization header
  4. 已登入 → POST run-plan 帶 Authorization header
  5. 未登入（無 token）→ 6 處呼叫皆不帶 Authorization header（驗證 `WMOM_AUTH_ENFORCE=false`
     過渡期行為不變，未登入時 authFetch 與裸 fetch 行為一致）

### 2.2 卡住或延後的事

- 無。範圍內（單一元件）完整完工。`WMOM-20260923-10` 清單尚餘 6 支元件，依原 issue 建議一次
  一支續接。

### 2.3 重大決策（如有）

- 無新增決策。沿用既有 `authFetch` wrapper 與 WMOM-20260923-07/-09 已建立的修法慣例。

## 3. 產出清單

### 修改檔案

- `frontend/components/FaultInjectionPanel.tsx`（+7/-6，6 處 fetch→authFetch）
- `frontend/components/__tests__/FaultInjectionPanel.test.tsx`（+109，新增 5 測）
- `ISSUES.md`（新增 WMOM-20260924-01 詳細條目；WMOM-20260923-10 補 sub-task checklist 標記
  `FaultInjectionPanel` 已完成；統計表 open 12/done 117/total 129）
- `STATUS.yaml`（`last_updated`、`issue_stats`、`next_milestone` 下次接手段落）
- `TODO.md`（最後更新段落、WMOM-20260923-10 條目進度）

### 動了狀態的 issue

- WMOM-20260924-01：新開 → done
- WMOM-20260923-10：open（維持，checklist 7 項中 1 項打勾）

### 寫進 decision_log 的決策

- 無（沿用既有修法，非新架構決策）

## 4. 下次怎麼接手

`WMOM-20260923-10` 稽核清單尚餘 6 支，依風險排序：

1. **`FarmSelector.tsx`**（GET `/api/farms`、POST `/api/farms/{id}/activate`、POST `/api/farms`，
   建立/切換 farm 屬 SUPERVISOR/ADMIN 寫入）——**建議優先**
2. **`SettingsPage.tsx`**（多處 `/api/config/*`，SUPERVISOR 寫入：wind/grid/turbine-spec
   設定變更）——**建議優先**
3. `CostPage.tsx`（GET `/api/farms`，讀取）
4. `EventComparisonView.tsx`（GET `/api/maintenance/events/compare`，讀取）
5. `HistoryPage.tsx`（`/api/i18n/tags`、`/api/turbines/{id}/history`，讀取）
6. `TrendChartPanel.tsx`（`/api/i18n/tags`、`/api/turbines/{id}/trend`，讀取）

修法比照本次 + WMOM-20260923-07/-09：改 `authFetch` + 補 5 類測試（mount GET header 斷言 /
寫入端點 header 斷言 / 未登入行為不變對照組）+ mutation-verified。全部 7 支完成後回頭勾掉
`docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表對應項。

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 與用戶對話、釐清方向 | 0%（autonomous，無即時對話） |
| 寫程式 / 寫文件 | 45% |
| Code review / 驗證 | 45% |
| 其他（環境安裝等） | 10% |

## 6. 學到的事

- 本檔既有測試（`callsTo` 只比對 URL + method/body，不檢查 headers）對「裸 fetch vs authFetch」
  完全不敏感——這是本 issue（WMOM-20260923-10）系列的共同根因：功能測試綠燈不代表 auth header
  有被正確帶上，必須額外補「header 內容」層級的專測才鎖得住。這個模式已在 WMOM-20260923-07/-09
  出現過，本次是第三次確認，值得在未來剩餘 6 支元件的接手時繼續套用同一張檢查清單。
- `refreshActive` 這類「定義在元件函式體內、被 `useEffect` 內的 `setInterval` 與多個 handler
  共用呼叫」的輔助函式，換成 `authFetch` 後不會有 stale-token closure 問題——因為
  `authFetch`/`authHeaders()` 每次呼叫當下才動態讀 `getAuthToken()`，不是在函式定義時就固定住
  token 值。這點在動類似輪詢邏輯的檔案（如剩餘清單裡任何一支有輪詢的元件）時可以放心套用同一
  修法，不需要額外處理。

## 7. Open questions（park）

- 無。

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline：backend `1103 passed, 7 skipped, 1 xfailed`；frontend `npx tsc --noEmit` 0
  error、`npx vitest run` `1227 passed`（58 files）、`npx vite build` OK。
- 本次新增/修改後：backend 未動（無 Python 變更，未重跑）；frontend `npx tsc --noEmit` 0 error、
  `npx vitest run` `1227→1232 passed`（58 files 不變，+5 新測）、`npx vite build` OK。
- **Mutation-verified**：暫時把 `FaultInjectionPanel.tsx` 6 處 `authFetch(` 用 `sed` 改回
  `fetch(`（保留 import 行不動），重跑此檔測試 → 4 個新測試（mount 3 GET header 斷言 + inject +
  clear + run-plan）如預期 fail（`未登入` 那個測試維持 pass，符合預期：該測試本就只驗證「無
  token 時兩種寫法行為一致」，不區分 fetch vs authFetch，非鎖住本次修復的測試——已在 ISSUES.md
  條目與測試檔內註解誠實揭露此侷限）。已從備份還原，`git diff --stat` 確認乾淨、6 處 `authFetch`
  呼叫皆在。

## Review

用 `Agent` tool 跑 `code-reviewer` subagent 對 diff review：**0 must-fix、0 should-fix、
2 nice-to-have（皆記錄性說明，reviewer 判定不需改動）**，Approve。

- Nice-to-have 1：「未登入」測試對 fetch/authFetch 不敏感，測試內註解已誠實揭露此侷限，屬合理
  設計選擇，無需改動。
- Nice-to-have 2：`authFetch` 在 GET 場景固定傳入 `{headers: {}}` 第二參數（裸 `fetch(url)`
  則完全不帶第二參數），此為 wrapper 既有行為、非本次改動引入，測試已用「URL 子字串比對、不
  假設 `init` 是否存在」的寫法正確適應，無須處理。
- reviewer 額外獨立驗證（非只信任本次回報）：自行 `grep` 確認 6 處替換無遺漏、逐行核對 diff
  只動到 `fetch`→`authFetch` 字面未動參數、讀 `authClient.ts` 確認 `refreshActive` 輪詢場景
  無 stale-token 問題、獨立重跑一次 mutation test（sed 還原測試）得到與本次一致的結果、全 repo
  grep `/api/faults/` 確認無其他遺漏呼叫點（`ScenarioPage.tsx` 也打 `/api/faults/scenarios`
  但已正確使用 `authFetch`，非本次範圍內問題）、比對姊妹 PR（`TurbineDetail.test.tsx`）確認
  手法與命名風格一致。

## Wrap-up

- ISSUES.md / STATUS.yaml / TODO.md 已同步更新（見上方「產出清單」）。
- 本次沒有引入未受自動化測試保護的邏輯。既有限制沿用先前 session 的說明：本檔案
  `.parentElement` DOM 遍歷 scoping 屬既有技術債（WMOM-20260923-02 review 標註優先度低），本次
  新增的 5 個測試皆改用既有 `callsTo`/header 斷言 helper，未引入新的脆弱寫法。
