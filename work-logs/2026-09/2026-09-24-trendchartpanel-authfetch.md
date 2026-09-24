# 2026-09-24 — `TrendChartPanel.tsx` authFetch 補齊（WMOM-20260923-10 sub-task 7/7，清單收尾）

> Session 類型：實作
> Session 長度：短
> 主導：autonomous worker（cron，v4.1）
> 結果：`WMOM-20260924-07` 完成，`WMOM-20260923-10`（前端 authFetch 稽核清單）7 支元件**全數
> 完成**，父 issue 標 done，`docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6
> cutover 檢查表「前端所有寫入 request 都帶 token」項目已勾選。

---

## 1. Session 目標

`WMOM-20260924-07`（`WMOM-20260923-10` sub-task，清單最後一項）。前一 session
（WMOM-20260924-06）完成 `HistoryPage.tsx` 後，清單只剩最後一支純讀取元件
`TrendChartPanel.tsx`（`TurbineDetail` 頁面右側即時趨勢圖面板，2 處裸 fetch）。

## 2. 實際完成

### 2.1 主要工作

- **Preflight**：`git checkout main && git pull` 快轉 32 commits（含前 6 個 sub-task 已
  merge，最新為 #179 `HistoryPage` authFetch）；`git status` clean。GitHub MCP 本次可用
  （非降級模式）；`mcp__github__list_pull_requests`（state=open）回傳空陣列，無 stack 衝突、
  無殘留 open PR。
- **Baseline 自我測試**：`pip install --ignore-installed PyYAML -r requirements.txt
  -r requirements-dev.txt`（含 `sentence-transformers` 帶入 CUDA 版 torch/cudnn，約 3-4
  分鐘）在背景跑的同時，先完成 frontend 全套（`npm ci` + `npx tsc --noEmit` 0 error +
  `npx vitest run` 1252 passed（58 files）+ `npx vite build` OK，此時基準為修改前）；backend
  pip install 完成後補跑全套：`1103 passed, 7 skipped, 1 xfailed`，與既有基準一致。
- **`frontend/components/TrendChartPanel.tsx`**：加
  `import { authFetch } from '../services/authClient'`，2 處 `fetch(` → `authFetch(`：
  1. mount 時（`useEffect([lang])`）GET `/api/i18n/tags?lang=...`（圖表圖例 i18n 對映）
  2. mount + preset/自訂 tag/turbineId 變更時，且每 2 秒輪詢（`setInterval(fetchTrend, 2000)`）
     GET `/api/turbines/{id}/trend?tags=...&limit=120`（趨勢資料）。
  兩者皆後端 `require_authenticated()`（任何登入者可讀），僅替換呼叫方式，`.then/.catch`
  鏈完全不動。`grep -n "[^a-zA-Z]fetch\("` 確認全檔無漏改的裸 fetch。
- **`frontend/components/__tests__/TrendChartPanel.test.tsx`**：新增
  `import { setAuthToken, clearAuthToken } from '../../services/authClient'` + 「authFetch
  稽核（WMOM-20260923-10）」describe block（`authHeaderOf`/`callsMatching` helper，複製自
  `HistoryPage.test.tsx` 等姊妹 PR 的同款模式），2 個新測試：
  1. 已登入（`setAuthToken`）→ mount 時 i18n/tags 與 trend 兩條 GET 皆帶
     `Authorization: Bearer <token>`
  2. 未登入（無 token）→ 兩條 GET 皆不帶 `Authorization` header（驗證
     `WMOM_AUTH_ENFORCE=false` 過渡期行為不變）

### 2.2 卡住或延後的事

- 無。範圍內（單一元件、2 處 fetch 呼叫）完整完工，`WMOM-20260923-10` 清單至此**全部 7 支
  元件完成**。GitHub MCP 本次可用，開工時已用 `mcp__github__list_pull_requests` 確認無 open
  PR、無 stack 衝突，收尾時走正常飛輪（push + `mcp__github__create_pull_request` 開 PR）。

### 2.3 重大決策（如有）

- 無新增架構決策。沿用既有 `authFetch` wrapper 與 WMOM-20260923-07/-09/WMOM-20260924-01~06
  已建立的修法慣例。
- 順手把 `docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表「前端
  所有寫入 request 都帶 token」項目勾選（因本次是清單最後一項，7 支元件全數清空後此條件
  才成立）。

## 3. 產出清單

### 修改檔案

- `frontend/components/TrendChartPanel.tsx`（+3/-2，2 處 fetch→authFetch + import）
- `frontend/components/__tests__/TrendChartPanel.test.tsx`（+53，新增 2 測 + import）
- `ISSUES.md`（新增 WMOM-20260924-07 詳細條目；WMOM-20260923-10 checklist 全勾選 + Status
  改 done；統計表 open 12→11、done 122→124、total 134→135）
- `STATUS.yaml`（`last_updated`、`issue_stats`、`next_milestone` 下次接手段落）
- `TODO.md`（最後更新段落、WMOM-20260923-10 條目收尾）
- `docs/product/WMOM-20260716-05_auth_enforcement_plan.md`（§6 cutover 檢查表「前端所有寫入
  request 都帶 token」打勾）

### 動了狀態的 issue

- WMOM-20260924-07：新開 → done
- WMOM-20260923-10：open → done（7 支子項全數完成）

### 寫進 decision_log 的決策

- 無（沿用既有修法，非新架構決策）

## 4. 下次怎麼接手

`WMOM-20260923-10` 已全數完成。下個 session 可從以下項目挑選（依 `TODO.md`/`STATUS.yaml`
`next_milestone` 優先序）：

1. `WMOM-20260507-02` 清單尚餘 c~f（限載/安排檢查/維護中心新工單/風場總覽新報告），皆已有
   明確 API/估時，🔵 autonomous-friendly。
2. 情境比較分析 epic 的 PR C（檢視情境掛載 app，需先寫 broker 子設計，範圍較大）。
3. auth cutover 檢查表尚餘 3 項（4 支 workflow router 遷移狀態確認、admin bootstrap 真實
   使用者佈建、staging `enforce=true` 完整 lifecycle demo）——這些多半需要劉老師配合或現場
   環境，下個 session 應先確認是否已具備條件，不要貿然自行推進 `enforce=true`。
4. ⚠ **提醒劉老師**：`docs/routines/autonomous-daily-worker-prompt.md` 內文仍停在 v3（舊
   baseline backend 638 / frontend 59），已連續多個 session（至少從 WMOM-20260923-05 起）
   落後於實際 cron trigger 送入的 prompt（v4.1，baseline 1103/1252）。建議找時間把 cron
   trigger 目前設定同步回這份文件，避免文件與實際行為的落差持續累積。

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 與用戶對話、釐清方向 | 0%（autonomous，無即時對話） |
| 寫程式 / 寫文件 | 35% |
| Code review / 驗證 | 40% |
| 其他（環境安裝等待） | 25% |

## 6. 學到的事

- `WMOM-20260923-10` 這種「盤點清單 + 逐檔 sub-issue」的 epic 拆解模式（比照
  `WMOM-20260507-02`）在跨 7 個 session 的執行中維持了穩定的修法模板（authFetch 替換 + N×2
  測 + mutation-verified），是 autonomous worker 處理「明確範圍、無設計歧義」工作的良好
  範例——每個 sub-issue 都能在單一 session 內乾淨完工，不需要跨 session 協調。
- 本次是第 7 次重複同款修法，過程中沒有發現新的邊界情況（沒有 AbortController、沒有
  SUPERVISOR 寫入），是清單裡最簡單的一支，符合先前 session 判斷「最後一支純讀取元件」的
  預期。

## 7. Open questions（park）

- 無（技術面）。上方 §4 第 4 點的 routine 文件版本落差已連續多次提醒，非本次程式碼工作
  範圍，留待劉老師處理。

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline（frontend）：`npx tsc --noEmit` 0 error；`npx vitest run` 修改前 1252
  passed（58 files）；`npx vite build` OK。backend pip install 完成後：`1103 passed, 7
  skipped, 1 xfailed`（未變動，本次未動任何 Python 檔案）。
- 修改後：`npx tsc --noEmit` 0 error；`npx vitest run` `1252→1254`（單檔 29 測全數 pass；
  全套因新增 2 測，58 files 不變）；`npx vite build` OK。
- **Mutation-verified**：把 `TrendChartPanel.tsx` 備份至 `/tmp/TrendChartPanel.tsx.bak`，用
  `sed` 將兩處 `authFetch(` 改回 `fetch(`，重跑此檔測試（`-t "authFetch 稽核"`）→「已登入」
  新測試如預期 fail（`expected undefined to be 'Bearer test-token-trend'`），「未登入」對照
  組維持 pass（符合預期：該測試只驗證「無 token 時行為不變」，不區分 fetch vs authFetch，非
  鎖住本次修復的測試）。用備份還原（非 `git checkout`），還原後重跑全檔 29 測全數 pass、
  `git diff` 僅剩預期修改（2 行 fetch→authFetch + 1 行 import）。

## Review

code-reviewer subagent review：**Approve，0 must-fix，0 should-fix**。

- 確認 `authFetch`（`authClient.ts:84-99`）回傳原始 `Response`，只在 merge headers + 401
  side-effect 上動手腳，兩處呼叫方的 `.then(r => r.json())` 鏈與 `.catch(() => {})` 吞錯
  行為與裸 `fetch` 完全一致，無 regression。
- 檢查 2 秒輪詢（`setInterval(fetchTrend, 2000)`）與 `authFetch` 401 handler 的交互：確認
  `TurbineDetail.tsx`（3 秒輪詢）已有同款模式，是既有跨元件已接受的特性（重複 401 觸發
  `onUnauthorized` 為冪等的導回登入頁行為），非本次新增問題。
- 重新 grep 全檔 `[^a-zA-Z.]fetch\(` 確認無漏改。
- 新增測試結構與 6 個已 merge 的姊妹 PR 一致，`authHeaderOf`/`callsMatching` helper 邏輯
  正確對應 `authFetch` 的 header merge 邏輯。

## Wrap-up

- ISSUES.md / STATUS.yaml / TODO.md / `WMOM-20260716-05_auth_enforcement_plan.md` 已同步
  更新（見上方「產出清單」）。
- 本次沒有引入未受自動化測試保護的邏輯。新增的 2 個測試沿用既有 `installFetch`/`fetchMock`
  系列 helper 的變體（多加 headers 擷取），未引入新的脆弱寫法。
