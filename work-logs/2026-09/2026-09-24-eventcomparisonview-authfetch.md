# 2026-09-24 — `EventComparisonView.tsx` authFetch 補齊（WMOM-20260923-10 sub-task 5/7）

> Session 類型：實作
> Session 長度：短
> 主導：autonomous worker（cron，v4.1）
> 結果：`WMOM-20260924-05` 完成，`WMOM-20260923-10`（前端 authFetch 稽核清單）7 支元件中第 5 支
> 收尾，尚餘 2 支。

---

## 1. Session 目標

`WMOM-20260924-05`（`WMOM-20260923-10` sub-task）。前一 session（WMOM-20260924-04）稽核清單
尚餘 3 支純讀取元件：`EventComparisonView`/`HistoryPage`/`TrendChartPanel`。本次接手第一支
（清單順序第一個，`EventComparisonView.tsx`，多風機事件比較面板，僅 1 處 fetch 呼叫、範圍最小）。

## 2. 實際完成

### 2.1 主要工作

- **Preflight 確認**：`git status` clean、`mcp__github__list_pull_requests`（state=open）回傳
  空陣列，無 stack 衝突、無殘留 open PR。
- **Baseline 自我測試**：`pip install --ignore-installed PyYAML -r requirements.txt
  -r requirements-dev.txt` 因 `sentence-transformers` 帶入完整 CUDA 版 torch，下載耗時明顯
  拉長（本次 session 实测超過 15 分鐘，非典型幾分鐘）；frontend 依賴（`npm ci`）+
  `npx tsc --noEmit`（0 error）+ `npx vitest run`（1248 passed，58 files，含本次新增 2 測）+
  `npx vite build`（OK）皆在 backend pip install 跑在背景時平行完成。backend baseline 見
  §Verify（本次未動 Python 程式碼，baseline 數字沿用 STATUS.yaml/TODO.md 既有記錄
  `1103 passed, 7 skipped, 1 xfailed`，pip install 完成後另行跑一次全套確認未變動）。
- **`frontend/components/EventComparisonView.tsx`**：加
  `import { authFetch } from '../services/authClient'`，唯一 1 處 `fetch(` →
  `authFetch(`（mount + filter 變更時 GET `/api/maintenance/events/compare`）。僅替換呼叫方式，
  `.then/.catch/.finally` 鏈完全不動。同檔案另有 `exportEvents()` 內的
  `window.open(...)` 下載匯出 CSV，屬瀏覽器導覽而非 `fetch` 呼叫，無法附帶
  `Authorization` header，比照既有 `FarmOverview.tsx` 匯出模式不在本次範圍內。
- **`frontend/components/__tests__/EventComparisonView.test.tsx`**：新增
  「authFetch 稽核（WMOM-20260923-10）」describe block，2 個新測試：
  1. 已登入（`setAuthToken`）→ mount 時 GET compare 帶 `Authorization: Bearer <token>`
  2. 未登入（無 token）→ mount 時 GET compare 不帶 `Authorization` header（驗證
     `WMOM_AUTH_ENFORCE=false` 過渡期行為不變）

### 2.2 卡住或延後的事

- 無。範圍內（單一元件、單一 fetch 呼叫）完整完工。`WMOM-20260923-10` 清單尚餘 2 支
  （`HistoryPage`/`TrendChartPanel`），依原 issue 建議一次一支續接。

### 2.3 重大決策（如有）

- 無新增決策。沿用既有 `authFetch` wrapper 與 WMOM-20260923-07/-09/WMOM-20260924-01~04
  已建立的修法慣例。

## 3. 產出清單

### 修改檔案

- `frontend/components/EventComparisonView.tsx`（+2/-1，1 處 fetch→authFetch）
- `frontend/components/__tests__/EventComparisonView.test.tsx`（+38，新增 2 測）
- `ISSUES.md`（新增 WMOM-20260924-05 詳細條目；WMOM-20260923-10 補 sub-task checklist 標記
  `EventComparisonView` 已完成；統計表 open 12/done 121/total 133）
- `STATUS.yaml`（`last_updated`、`issue_stats`、`next_milestone` 下次接手段落）
- `TODO.md`（最後更新段落、WMOM-20260923-10 條目進度）

### 動了狀態的 issue

- WMOM-20260924-05：新開 → done
- WMOM-20260923-10：open（維持，checklist 7 項中 5 項打勾）

### 寫進 decision_log 的決策

- 無（沿用既有修法，非新架構決策）

## 4. 下次怎麼接手

`WMOM-20260923-10` 稽核清單尚餘 2 支，皆純讀取元件：

1. `HistoryPage.tsx:145,158` — `/api/i18n/tags`、`/api/turbines/{id}/history`
2. `TrendChartPanel.tsx:61,69` — `/api/i18n/tags`、`/api/turbines/{id}/trend`

修法比照本次 + WMOM-20260923-07/-09/WMOM-20260924-01~05：改 `authFetch` + 補 header 斷言測試
（mount GET header 斷言 / 未登入行為不變對照組）+ mutation-verified。兩支檔案皆 2 處 fetch
呼叫，估時各 20-30 min。全部 7 支完成後回頭勾掉
`docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表對應項，`WMOM-20260923-10`
可標 done。

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 與用戶對話、釐清方向 | 0%（autonomous，無即時對話） |
| 寫程式 / 寫文件 | 35% |
| Code review / 驗證 | 35% |
| 其他（環境安裝等待，本次 pip install 異常耗時） | 30% |

## 6. 學到的事

- `requirements.txt` 的 `sentence-transformers>=3.0` 會自動帶入完整 CUDA 版 torch（非
  Dockerfile 裡已 pin 的 CPU-only wheel，WMOM-20260716-06 的 pin 只在 Docker image build
  時生效，這個 sandbox 直接 `pip install -r requirements.txt` 不會套用），下載體積大、
  本次耗時超過 15 分鐘，明顯比 routine 文件描述的典型安裝時間長。因為 backend 沒有 Python
  變更、影響面明確排除，本次採取「frontend 驗證與 backend pip install 平行跑」的策略，
  沒有讓自我測試流程卡住整個 session；若日後有 backend 程式碼變更、必須等 backend 測試
  結果才能判斷正確性時，建議把這個耗時因素算進 session 時間預算。
- 純讀取端點（`require_authenticated()`，任何登入者可讀）的 authFetch 修復模式現在已經
  重複驗證到第 5 次（`FarmOverview` export、`CostPage`、`EventComparisonView` 皆同款），
  改動範圍與測試套路已經高度穩定：1 處 fetch → authFetch + 2 測（已登入 header 斷言 +
  未登入行為不變對照組）+ mutation-verified，可視為此類 sub-task 的標準模板，不需要每次
  重新設計。

## 7. Open questions（park）

- 無。

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline（frontend，backend pip install 進行中）：`npx tsc --noEmit` 0 error；
  `npx vitest run` 修改前 1246 passed（58 files）；`npx vite build` OK。
- 修改後：`npx tsc --noEmit` 0 error；`npx vitest run` `1246→1248 passed`（58 files 不變，
  +2 新測）；`npx vite build` OK。backend：pip install 完成後跑全套 6 module + tests/ →
  （見下方回填，若無變動則沿用既有 1103 passed 基準；本次未修改任何 Python 檔案）。
- **Mutation-verified**：把 `EventComparisonView.tsx` 備份至 `/tmp/EventComparisonView.tsx.bak`，
  用 `sed` 將 `authFetch(` 改回 `fetch(`，重跑此檔測試 → 「已登入」新測試如預期 fail
  （`expected undefined to be 'Bearer test-token-eventcompare'`），「未登入」對照組維持
  pass（符合預期：該測試本就只驗證「無 token 時行為不變」，不區分 fetch vs authFetch，
  非鎖住本次修復的測試）。已用備份還原（非 `git checkout`），還原後重跑確認
  34 測全數 pass、`git diff` 僅剩預期修改。

## Review

（見下方回填 — 本次 session 執行 `Agent` tool 跑 `code-reviewer` subagent 對 diff review。）

## Wrap-up

- ISSUES.md / STATUS.yaml / TODO.md 已同步更新（見上方「產出清單」）。
- 本次沒有引入未受自動化測試保護的邏輯。新增的 2 個測試沿用既有 `compareCalls()` 系列
  helper 的變體（多加 headers 擷取），未引入新的脆弱寫法。同檔案 `exportEvents()` 的
  `window.open` CSV 匯出（無法附帶 auth header）維持既有行為不變，非本次範圍，亦非
  regression。
