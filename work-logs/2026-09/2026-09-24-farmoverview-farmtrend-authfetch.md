# 2026-09-24 — `FarmOverview.tsx` farm-trend fetch 補 `authFetch`（WMOM-20260923-08）

> Session 類型：實作
> Session 長度：短
> 主導：autonomous worker（cron，v4.1）
> 結果：`WMOM-20260923-08` 完成——`FarmOverview.tsx` 內僅存的一處裸 `fetch`（`TrendCard` 的
> `/api/turbines/farm-trend`）改 `authFetch`，該檔案「所有 fetch 都走 authFetch」的一致性
> 技術債清空。

---

## 1. Session 目標

Preflight 讀 `TODO.md` + `STATUS.yaml` `next_milestone` 段落，確認 `WMOM-20260923-10`（前端
authFetch 稽核清單，7 支元件）已於 2026-09-24 稍早（WMOM-20260924-01~07）全數完成並標
done。`git ls-remote` / `mcp__github__list_pull_requests`（state=open）確認無殘留 open PR、
無 stack 衝突。

下一個候選是 `WMOM-20260923-08`——`WMOM-20260923-07`（匯出鈕接線）review 時的 nice-to-have
follow-up：`FarmOverview.tsx` 同檔案內 `TrendCard` 的 `/api/turbines/farm-trend` fetch 仍是
裸 `fetch`，與剛接好的 `/api/export/snapshot` 一樣掛
`Depends(require_authenticated())`，過渡期（`WMOM_AUTH_ENFORCE=false`）行為相同，但 enforce
開啟後未登入使用者會被靜默 401（`.catch(() => {/* ignore */})` 吞掉），UI 卡在「資料收集
中…」而非導向登入頁。估時 15 分鐘，🔵 autonomous-friendly，範圍單一、無設計歧義，選為本次
工作。

## 2. 實際完成

### 2.1 主要工作

- **Preflight**：`git checkout main && git pull`（已是最新，32+ commits 皆在，含
  `WMOM-20260923-10` 全系列）；切到環境注入分支 `claude/inspiring-mccarthy-nwrw8t` 並
  fast-forward 對齊 main。`git status` clean。
- **Baseline 自我測試**：
  - backend：`pip install --ignore-installed PyYAML -r requirements.txt
    -r requirements-dev.txt` → `python -m pytest`（6 module + tests/）→
    **1103 passed, 7 skipped, 1 xfailed**，與既有基準一致。
  - frontend：`npm ci` → `npx tsc --noEmit` 0 error → `npx vitest run` **1252 passed**
    （58 files）→ `npx vite build` OK。
  - 全數與 `docs/routines/autonomous-daily-worker-prompt.md` v4.1 記載基準一致，無 regression
    待修。
- **`frontend/components/FarmOverview.tsx`**：`TrendCard` 內 `fetchData`（約第 174 行）的
  `fetch(...)` 改 `authFetch(...)`（`authFetch` 已在檔案頂部 import，因為同檔案的匯出鈕
  `handleExportSnapshot` 已在用）。`.then(r => r.json())` 與後續 `.catch(() => {/* ignore
  */})` 鏈完全不動。`grep -n "[^a-zA-Z.]fetch\("` 確認全檔無其他漏改的裸 fetch。
- **`frontend/components/__tests__/FarmOverview.test.tsx`**：在既有 `FarmOverview —
  TrendCard` describe block 內新增 2 測試（比照同檔案「匯出風場快照」describe block 內
  WMOM-20260923-07 已建立的 auth header 測試手法）：
  1. 已登入（`setAuthToken`）→ mount 觸發的 farm-trend fetch 帶正確 `Authorization: Bearer
     <token>` header
  2. 未登入（無 token）→ farm-trend fetch 不帶 Authorization header（驗證過渡期行為不變）

### 2.2 卡住或延後的事

- 無。單一元件、單一 fetch 呼叫，範圍完整完工。

### 2.3 重大決策（如有）

- 無新增架構決策，沿用既有 `authFetch` wrapper 與 WMOM-20260923-07/-09/WMOM-20260924-01~07
  已建立的修法慣例。

## 3. 產出清單

### 修改檔案

- `frontend/components/FarmOverview.tsx`（+1/-1，1 處 fetch→authFetch）
- `frontend/components/__tests__/FarmOverview.test.tsx`（新增 2 測）
- `ISSUES.md`（WMOM-20260923-08 標 done + 補完成摘要；統計表更新）
- `STATUS.yaml`（`last_updated`、`issue_stats`、`next_milestone` 下次接手段落）
- `TODO.md`（最後更新段落）

### 動了狀態的 issue

- WMOM-20260923-08：open → done

### 寫進 decision_log 的決策

- 無（沿用既有修法，非新架構決策）

## 4. 下次怎麼接手

下個 session 可從以下項目挑選（依 `TODO.md`/`STATUS.yaml` `next_milestone` 優先序）：

1. `WMOM-20260507-02` 清單尚餘 c~f（限載/安排檢查/維護中心新工單/風場總覽新報告），皆已有
   明確 API/估時，🔵 autonomous-friendly（`c. 限載` 與 `e. + 新工單` 無阻塞，可任選其一；
   `d. 安排檢查` 依賴 WMOM-22 `inspection_schedule` 尚未做；`f. + 新報告` 需 M4 reporting
   module，M4 已 done 可視情況評估）。
2. 情境比較分析 epic 的 PR C（檢視情境掛載 app，需先寫 broker 子設計，範圍較大）。
3. auth cutover 檢查表尚餘 3 項（4 支 workflow router 遷移狀態確認、admin bootstrap 真實
   使用者佈建、staging `enforce=true` 完整 lifecycle demo）——多半需要劉老師配合或現場
   環境，下個 session 應先確認是否已具備條件，不要貿然自行推進 `enforce=true`。
4. ⚠ **提醒劉老師**：`docs/routines/autonomous-daily-worker-prompt.md` 內文仍停在 v3（舊
   baseline backend 638 / frontend 59），已連續多個 session（至少從 WMOM-20260923-05 起）
   落後於實際 cron trigger 送入的 prompt（v4.1，baseline 1103/1252→1254）。建議找時間把
   cron trigger 目前設定同步回這份文件，避免文件與實際行為的落差持續累積（本次是第 N 次
   重複提醒）。

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 與用戶對話、釐清方向 | 0%（autonomous，無即時對話） |
| 寫程式 / 寫文件 | 30% |
| Code review / 驗證 | 45% |
| 其他（環境安裝等待） | 25% |

## 6. 學到的事

- 這是本 repo 第 8 次重複同款「裸 fetch → authFetch + 2 測（已登入/未登入對照）+
  mutation-verified」修法（前 7 次是 `WMOM-20260923-10` 系列 + `WMOM-20260923-07`），
  模式已經非常穩定，單一 session 內可乾淨完工，無需跨 session 協調。
- 這個 follow-up 之所以被獨立列為 issue（而非在 WMOM-20260923-07 當次一起改），是因為
  reviewer 判斷「同檔案但不同函式的既存缺口」屬於範圍外變更，應該獨立追蹤——這次驗證了
  這個判斷是對的：修法本身確實與匯出鈕的修法完全獨立（不同 `useEffect`、不同 fetch
  呼叫），拆開追蹤不會造成額外負擔，反而讓每個 PR 的 diff 保持最小。

## 7. Open questions（park）

- 無（技術面）。上方 §4 第 4 點的 routine 文件版本落差已連續多次提醒，非本次程式碼工作
  範圍，留待劉老師處理。

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline：backend `1103 passed, 7 skipped, 1 xfailed`；frontend `npx tsc --noEmit`
  0 error、`npx vitest run` 1252 passed（58 files）、`npx vite build` OK。
- 修改後：backend 未動、不重跑（本次零 Python 變更）；frontend `npx tsc --noEmit` 0
  error、`npx vitest run` `1252→1254`（單檔 `FarmOverview.test.tsx` 22→24 測全數
  pass；全套 58 files 不變，+2 新測）、`npx vite build` OK。
- **Mutation-verified**：修改前備份 `FarmOverview.tsx` 至 scratchpad（非 repo 內、非
  `git checkout` 可還原路徑），將 `authFetch(` 改回 `fetch(`，重跑
  `FarmOverview.test.tsx` → 「已登入」新測試如預期 fail
  （`TypeError: Cannot read properties of undefined (reading 'headers')`，因為裸 `fetch`
  只傳一個參數、`init` 為 `undefined`），「未登入」對照組維持 pass（符合預期：該測試只驗證
  「無 token 時不帶 header」，兩種實作皆滿足，非鎖住本次修復的測試，作用是防止未來有人在
  「未登入」情境誤加了 Authorization header）。用備份還原（非 `git checkout`），還原後重跑
  單檔 24 測全數 pass，`git diff` 僅剩預期修改（1 行 fetch→authFetch，測試檔 +2 測）。

## Review

code-reviewer subagent review：**Approve，0 must-fix，1 should-fix（範圍外發現，非本 PR
必修）**。

- 確認 `FarmOverview.tsx` 全檔 `grep -n "fetch("` 後只剩這一處改動，符合「全檔至此無裸
  fetch 殘留」的宣稱。
- 確認 `authFetch` 的 401 攔截 / merge header 邏輯不變，輪詢行為不受影響——每次輪詢呼叫的
  仍是同一個 `fetchData` closure，`authHeaders()` 即時查 `localStorage`，沒有把 token
  快取進 closure 造成登入狀態變化後失步的風險。
- 核對新增測試確實走真實 `authFetch`（本檔案未 mock `authClient`，只 stub 底層
  `global.fetch`），「已登入」測試會在裸 fetch 下如實 fail（`init` 為 `undefined`），與
  手動 mutation-verify 結果一致，非巧合通過；「未登入」對照組雖單獨看不能證明修正生效，
  但搭配「已登入」測試合起來完整覆蓋 happy path + 過渡期不變兩種狀態。
- 401 行為與輪詢交互皆判斷為既有邏輯（`authClient.test.ts` 已覆蓋 401 攔截本身），不需要
  為此小修正額外補測試，範圍控制合理。
- **Should-fix（範圍外發現）**：`grep -rln` 遞迴重掃 `frontend/components/` 全樹後，找到
  `components/field/MyOrdersMode.tsx:31`（現場工程師「我的工單」頁）仍是裸 `fetch`
  （GET `/api/farms`）。根因是 `WMOM-20260923-10`（2026-09-23 稽核）當時的掃描指令只對
  `frontend/components/*.tsx` 一層跑 grep，未遞迴進 `components/field/` 子目錄，導致該
  頁面從一開始就不在稽核範圍內、未被登記為 follow-up。已獨立驗證（`grep -rln` 全樹掃描確認
  這是唯一殘留）並登記為新 issue **WMOM-20260924-08**（見 ISSUES.md），不塞進本次 PR
  （範圍已明確界定在 `FarmOverview.tsx`）。

## Wrap-up

- ISSUES.md / STATUS.yaml / TODO.md 已同步更新（見上方「產出清單」），並新增
  WMOM-20260924-08 追蹤 review 發現的稽核盲區。
- 本次沒有引入未受自動化測試保護的邏輯。新增的 2 個測試沿用既有
  `fetchMock.mock.calls.find(...)` 手法（與 WMOM-20260923-07 匯出鈕 auth header 測試同款），
  未引入新的脆弱寫法。
- ⚠ 誠實揭露既有限制（非本次引入）：`TrendCard` 的 2 秒/12H/1D 輪詢與 `authFetch` 的
  401 handler 交互（多次輪詢觸發多次 401 → 多次 `onUnauthorized()` 呼叫）僅靠讀原始碼層級
  推論其為冪等操作（`clearAuthToken()` + 導回登入頁 handler 重複呼叫無副作用），未被任何
  自動化測試直接鎖住這個交互路徑本身；此為 WMOM-20260924-07（TrendChartPanel）review 時
  已確認過的既有跨元件特性，非本次新增問題。
- ⚠ 誠實揭露稽核完整性教訓：`WMOM-20260923-10` 當初宣稱「7 支元件全數清空」並非真正窮盡
  ——本次 review 用遞迴 grep 才發現 `components/field/` 子目錄從未被掃描過。已在
  WMOM-20260924-08 記錄根因（掃描指令未遞迴），供未來類似稽核工作參考：**清單型稽核工作
  應優先用遞迴 grep 界定範圍，而非假設扁平目錄結構**。
