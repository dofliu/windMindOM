# 2026-09-24 — `HistoryPage.tsx` authFetch 補齊（WMOM-20260923-10 sub-task 6/7）

> Session 類型：實作
> Session 長度：短
> 主導：autonomous worker（cron，v4.1）
> 結果：`WMOM-20260924-06` 完成，`WMOM-20260923-10`（前端 authFetch 稽核清單）7 支元件中第 6 支
> 收尾，尚餘 1 支（`TrendChartPanel`）。

---

## 1. Session 目標

`WMOM-20260924-06`（`WMOM-20260923-10` sub-task）。前一 session（WMOM-20260924-05）稽核清單
尚餘 2 支純讀取元件：`HistoryPage`/`TrendChartPanel`。本次接手第一支（清單順序第一個，
`HistoryPage.tsx`，歷史資料頁，2 處 fetch 呼叫）。

## 2. 實際完成

### 2.1 主要工作

- **Preflight 確認**：`git checkout main && git pull` 快轉 31 commits（含前 5 個 sub-task 已
  merge）；`git status` clean；`mcp__github__list_pull_requests`（state=open）回傳空陣列，
  無 stack 衝突、無殘留 open PR。GitHub MCP 本次可用（非降級模式）。
- **Baseline 自我測試**：`pip install --ignore-installed PyYAML -r requirements.txt
  -r requirements-dev.txt` 因 `sentence-transformers` 帶入完整 CUDA 版 torch/cudnn（同
  WMOM-20260924-05 work-log 記錄的已知環境限制），下載+安裝耗時約 5 分鐘；frontend
  （`npm ci` + `npx tsc --noEmit` 0 error + `npx vitest run` 1248 passed（58 files）+
  `npx vite build` OK）在 backend pip install 跑在背景時平行完成，未讓自我測試流程卡住。
  backend pip install 完成後補跑全套：`1103 passed, 7 skipped, 1 xfailed`（與 STATUS.yaml/
  TODO.md 既有基準一致，未變動）。
- **`frontend/components/HistoryPage.tsx`**：加
  `import { authFetch } from '../services/authClient'`，2 處 `fetch(` → `authFetch(`：
  1. mount 時（`useEffect([lang])`）GET `/api/i18n/tags?lang=...`（標籤 i18n 對映）
  2. mount + 篩選條件變更時（`useEffect([selectedTurbineId, activeTags, limit, rangeStart,
     rangeEnd])`）GET `/api/turbines/{id}/history?...`（帶 `AbortController` signal）——
     交叉核對 `authFetch` 簽章（`authClient.ts`）確認第二參數 `RequestInit`（含 `signal`）
     原樣透傳給底層 `fetch`，abort 語意不受影響。
  僅替換呼叫方式，`.then/.catch/.finally` 鏈與 `AbortController` 完全不動。同檔案
  `exportCsv()` 內兩處 `window.open(...)`（CSV 區間/聚焦匯出）屬瀏覽器導覽而非 `fetch`
  呼叫，無法附帶 `Authorization` header，比照既有 `FarmOverview.tsx`/`EventComparisonView.tsx`
  匯出模式不在本次範圍內。
- **`frontend/components/__tests__/HistoryPage.test.tsx`**：新增
  「authFetch 稽核（WMOM-20260923-10）」describe block，2 個新測試（涵蓋兩處 fetch 呼叫）：
  1. 已登入（`setAuthToken`）→ mount 時 i18n/tags 與 history 兩條 GET 皆帶
     `Authorization: Bearer <token>`
  2. 未登入（無 token）→ mount 時兩條 GET 皆不帶 `Authorization` header（驗證
     `WMOM_AUTH_ENFORCE=false` 過渡期行為不變）

### 2.2 卡住或延後的事

- 無。範圍內（單一元件、2 處 fetch 呼叫）完整完工。`WMOM-20260923-10` 清單尚餘 1 支
  （`TrendChartPanel`），依原 issue 建議下個 session 續接，全部完成後回頭勾掉
  `docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表對應項。

### 2.3 重大決策（如有）

- 無新增決策。沿用既有 `authFetch` wrapper 與 WMOM-20260923-07/-09/WMOM-20260924-01~05
  已建立的修法慣例。

## 3. 產出清單

### 修改檔案

- `frontend/components/HistoryPage.tsx`（+3/-2，2 處 fetch→authFetch + import）
- `frontend/components/__tests__/HistoryPage.test.tsx`（+53，新增 2 測 + import）
- `ISSUES.md`（新增 WMOM-20260924-06 詳細條目；WMOM-20260923-10 補 sub-task checklist 標記
  `HistoryPage` 已完成；統計表 open 12/done 122/total 134）
- `STATUS.yaml`（`last_updated`、`issue_stats`、`next_milestone` 下次接手段落）
- `TODO.md`（最後更新段落、WMOM-20260923-10 條目進度）

### 動了狀態的 issue

- WMOM-20260924-06：新開 → done
- WMOM-20260923-10：open（維持，checklist 7 項中 6 項打勾）

### 寫進 decision_log 的決策

- 無（沿用既有修法，非新架構決策）

## 4. 下次怎麼接手

`WMOM-20260923-10` 稽核清單尚餘 1 支，純讀取元件：

1. `TrendChartPanel.tsx:61,69` — `/api/i18n/tags`、`/api/turbines/{id}/trend`

修法比照本次 + WMOM-20260923-07/-09/WMOM-20260924-01~06：改 `authFetch` + 補 header 斷言測試
（mount GET header 斷言 / 未登入行為不變對照組）+ mutation-verified。估時 20-30 min。完成後
`WMOM-20260923-10` 可標 done，回頭勾掉
`docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表對應項。

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 與用戶對話、釐清方向 | 0%（autonomous，無即時對話） |
| 寫程式 / 寫文件 | 35% |
| Code review / 驗證 | 40% |
| 其他（環境安裝等待） | 25% |

## 6. 學到的事

- 純讀取端點（`require_authenticated()`，任何登入者可讀）的 authFetch 修復模式現在已經
  重複驗證到第 6 次，改動範圍與測試套路已高度穩定：N 處 fetch → authFetch + 2N 測（每處
  fetch 各一組「已登入 header 斷言 + 未登入行為不變對照組」）+ mutation-verified，可視為
  此類 sub-task 的標準模板。
- 本次首次遇到帶 `AbortController` signal 的 fetch 呼叫（`{ signal: ctrl.signal }` 作為第二
  參數），需額外確認 `authFetch` 的 `RequestInit` 透傳不吞掉/覆寫呼叫方傳入的欄位（讀
  `authClient.ts` 原始碼確認為 merge 而非整個取代）。

## 7. Open questions（park）

- 無。

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline（frontend，backend pip install 進行中）：`npx tsc --noEmit` 0 error；
  `npx vitest run` 修改前 1248 passed（58 files）；`npx vite build` OK。backend pip install
  完成後：`1103 passed, 7 skipped, 1 xfailed`（未變動，本次未動任何 Python 檔案）。
- 修改後：`npx tsc --noEmit` 0 error；`npx vitest run` `1248→1250 passed`（58 files 不變，
  +2 新測）；`npx vite build` OK。
- **Mutation-verified**：把 `HistoryPage.tsx` 備份至 `/tmp/HistoryPage.tsx.bak`，用 `sed`
  將兩處 `authFetch(` 改回 `fetch(`，重跑此檔測試（`-t "authFetch 稽核"`）→「已登入」新測試
  如預期 fail（`expected undefined to be 'Bearer test-token-history'`），「未登入」對照組
  維持 pass（符合預期：該測試只驗證「無 token 時行為不變」，不區分 fetch vs authFetch，非
  鎖住本次修復的測試）。已用備份還原（非 `git checkout`），還原後重跑全檔 23 測全數 pass、
  `git diff --stat` 僅剩預期修改。

## Review

code-reviewer subagent review：**Approve，0 must-fix，0 should-fix，2 nice-to-have**。

- 確認 `authFetch`（`authClient.ts:84-99`）簽章為 `...init` 先展開、僅 `headers` 額外
  merge，`{ signal: ctrl.signal }` 原樣透傳，unmount abort 語意不受影響；未登入時
  `authHeaders()` 回傳 `{}` 而非 `undefined`，故 `merged.headers` 仍是「已定義但空」物件，
  與測試斷言 `toBeUndefined()`（比對 `.Authorization` 這個 key）語意一致，非偽陰性。
- 重新 grep 全檔 `fetch(`/`window.open(` 確認無漏改，`exportCsv()` 兩處 `window.open` 排除
  範圍與 issue 條列一致。
- 新增測試結構與 5 個已 merge 的姊妹 PR（`CostPage`/`EventComparisonView`/`SettingsPage`/
  `FarmSelector`）一致（`authHeaderOf`/`callsMatching` helper + 已登入/未登入配對），
  mutation-verified 流程已獨立確認合理。
- 2 個 nice-to-have（皆未採納，非阻塞，範圍與 5 個已 merge 姊妹 PR 一致）：
  1. `exportCsv()` 的 `window.open` CSV 匯出在 cutover 後無法帶 auth header（結構性限制，
     `FarmOverview.tsx` 已有 fetch+Blob 下載的替代模式可參考），建議另開 issue 涵蓋
     `HistoryPage.tsx`/`EventComparisonView.tsx` 兩處匯出，非本次 `WMOM-20260923-10`
     （只涵蓋裸 fetch）範圍。
  2. 檔案頂部 docstring 未提及新增的 `authFetch` 依賴——同款缺口存在於已 merge 的
     `CostPage.tsx` 等姊妹檔案，屬整個 epic 的既有慣例缺口，非本次 diff 特有。

## Wrap-up

- ISSUES.md / STATUS.yaml / TODO.md 已同步更新（見上方「產出清單」）。
- 本次沒有引入未受自動化測試保護的邏輯。新增的 2 個測試沿用既有 `fetchedUrls()`/
  `fetchMock` 系列 helper 的變體（多加 headers 擷取），未引入新的脆弱寫法。同檔案
  `exportCsv()` 的兩處 `window.open` CSV 匯出（無法附帶 auth header）維持既有行為不變，非
  本次範圍，亦非 regression。
