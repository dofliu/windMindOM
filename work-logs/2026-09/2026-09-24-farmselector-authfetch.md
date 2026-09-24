# 2026-09-24 — `FarmSelector.tsx` authFetch 補齊（WMOM-20260923-10 sub-task 2/7）

> Session 類型：實作
> Session 長度：短
> 主導：autonomous worker（cron，v4.1）
> 結果：`WMOM-20260924-02` 完成，`WMOM-20260923-10`（前端 authFetch 稽核清單）7 支元件中第 2 支
> 收尾，尚餘 5 支。

---

## 1. Session 目標

WMOM-20260924-02（`WMOM-20260923-10` sub-task）。上次 session（WMOM-20260924-01）修復
`FaultInjectionPanel.tsx` 後，`WMOM-20260923-10` 清單建議優先序第二項為 `FarmSelector.tsx`
（sidebar 底部風場切換器 + 建立風場 modal），因其 2 個寫入端點（切換 farm activate / 建立
farm）皆 `require_role(Role.SUPERVISOR)`，風險與已修復的 `OperatorControlCard`/
`FaultInjectionPanel` 同級。

## 2. 實際完成

### 2.1 主要工作

- **Preflight 確認**：`git status` clean；`mcp__github__list_pull_requests` 確認無 open PR
  （GitHub MCP 本次可用，非降級模式），無 stack 衝突。
- **Baseline 自我測試**：backend `1103 passed, 7 skipped, 1 xfailed`；frontend
  `npx tsc --noEmit` 0 error、`npx vitest run` `1232 passed`（58 files）、`npx vite build`
  OK——皆與 STATUS.yaml/TODO.md 記錄的既有基準一致。
- **`frontend/components/FarmSelector.tsx`**：加
  `import { authFetch } from '../services/authClient'`，3 處 `fetch(` 全改 `authFetch(`：
  - `fetchFarms`（GET `/api/farms`，mount 時取列表 + active_farm_id）
  - `switchFarm`（POST `/api/farms/{farmId}/activate`，SUPERVISOR/ADMIN 寫入）
  - `handleCreate`（`CreateFarmModal` 內，POST `/api/farms`，SUPERVISOR/ADMIN 寫入）
  - 僅替換呼叫方式本身，method / headers（`Content-Type`）/ body（`JSON.stringify(...)`）參數
    完全不動。
- **`frontend/components/__tests__/FarmSelector.test.tsx`**（本檔既有 39 測，來自
  WMOM-20260607-04）：新增「authFetch 稽核（WMOM-20260923-10）」describe block，4 個新測試：
  1. 已登入（`setAuthToken`）→ mount 時 GET `/api/farms` 帶 `Authorization: Bearer <token>`
  2. 已登入 → 切換 farm 的 POST `/api/farms/{id}/activate` 帶 header
  3. 已登入 → 建立風場的 POST `/api/farms` 帶 header
  4. 未登入（無 token）→ 三處呼叫皆不帶 header（驗證 `WMOM_AUTH_ENFORCE=false` 過渡期行為不變）

### 2.2 卡住或延後的事

- 無。範圍內（單一元件）完整完工。`WMOM-20260923-10` 清單尚餘 5 支元件，依原 issue 建議一次
  一支續接。

### 2.3 重大決策（如有）

- 無新增決策。沿用既有 `authFetch` wrapper 與 WMOM-20260923-07/-09/WMOM-20260924-01 已建立的
  修法慣例。

## 3. 產出清單

### 修改檔案

- `frontend/components/FarmSelector.tsx`（+4/-3，3 處 fetch→authFetch + 1 行 import）
- `frontend/components/__tests__/FarmSelector.test.tsx`（+85，新增 4 測 + import
  `setAuthToken`/`clearAuthToken`）
- `ISSUES.md`（新增 WMOM-20260924-02 詳細條目；WMOM-20260923-10 補 sub-task checklist 標記
  `FarmSelector` 已完成；統計表 open 12/done 118/total 130）
- `STATUS.yaml`（`last_updated`、`issue_stats`）
- `TODO.md`（最後更新段落、WMOM-20260923-10 條目進度）

### 動了狀態的 issue

- WMOM-20260924-02：新開 → done
- WMOM-20260923-10：open（維持，checklist 7 項中 2 項打勾）

### 寫進 decision_log 的決策

- 無（沿用既有修法，非新架構決策）

## 4. 下次怎麼接手

`WMOM-20260923-10` 稽核清單尚餘 5 支，依風險排序：

1. **`SettingsPage.tsx`**（多處 `/api/config/*`，SUPERVISOR 寫入：wind/grid/turbine-spec
   設定變更）——**建議優先**
2. `CostPage.tsx`（GET `/api/farms`，讀取）
3. `EventComparisonView.tsx`（GET `/api/maintenance/events/compare`，讀取）
4. `HistoryPage.tsx`（`/api/i18n/tags`、`/api/turbines/{id}/history`，讀取）
5. `TrendChartPanel.tsx`（`/api/i18n/tags`、`/api/turbines/{id}/trend`，讀取）

修法比照本次 + WMOM-20260923-07/-09/WMOM-20260924-01：改 `authFetch` + 補測試（mount GET
header 斷言 / 寫入端點 header 斷言 / 未登入行為不變對照組）+ mutation-verified。全部 7 支完成
後回頭勾掉 `docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表對應項。

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 與用戶對話、釐清方向 | 0%（autonomous，無即時對話） |
| 寫程式 / 寫文件 | 40% |
| Code review / 驗證 | 50% |
| 其他（環境安裝等） | 10% |

## 6. 學到的事

- `FarmSelector.test.tsx` 本身已有 39 個既有測試（WMOM-20260607-04），皆用 `calls()` helper
  只比對 URL + method，同款「對 header 不敏感」根因在此檔案再次確認——本次新增的
  `callsMatching`/`authHeaderOf` 走獨立路徑直接檢查 `RequestInit.headers.Authorization`，才
  真正鎖住 authFetch 遷移。這個模式已在 WMOM-20260923-07/-09/-20260924-01 出現過，本次是第四次
  確認。
- `switchFarm`/`handleCreate` 皆非輪詢邏輯（一次性呼叫，非 `setInterval` 共用），換
  `authFetch` 沒有 stale-closure 疑慮，比 `FaultInjectionPanel` 的 `refreshActive` 更單純。

## 7. Open questions（park）

- 無。

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline：backend `1103 passed, 7 skipped, 1 xfailed`；frontend `npx tsc --noEmit` 0
  error、`npx vitest run` `1232 passed`（58 files）、`npx vite build` OK。
- 本次新增/修改後：backend 未動（無 Python 變更，未重跑）；frontend `npx tsc --noEmit` 0 error、
  `npx vitest run` `1232→1236 passed`（58 files 不變，+4 新測）、`npx vite build` OK。
- **Mutation-verified**：暫時把 `FarmSelector.tsx` 3 處 `authFetch(` 用 `sed` 改回 `fetch(`
  （保留 import 行不動），重跑此檔測試（43 測）→ 3 個「已登入」新測試（mount + 切換 + 建立）
  如預期 fail、「未登入」測試維持 pass（符合預期：該測試本就只驗證「無 token 時三種寫法行為
  一致」，不區分 fetch vs authFetch，非鎖住本次修復的測試——已在測試檔內註解誠實揭露此侷限）。
  已從備份還原，`git diff --stat` 確認乾淨、3 處 `authFetch` 呼叫皆在，重跑此檔測試回到
  43/43 全綠。

## Review

用 `Agent` tool 跑 `code-reviewer` subagent 對 diff review：**0 must-fix、0 should-fix、
2 nice-to-have（皆記錄性說明，reviewer 判定不需改動）**，Approve。

- Nice-to-have 1：「未登入」測試對 fetch/authFetch 不敏感（兩者皆產生 `undefined` header），
  測試內容本身承認此侷限，作為過渡期行為回歸守門仍有效，不需改動。
- Nice-to-have 2：測試檔內 `callsMatching`/`authHeaderOf` 與姊妹既有 `calls()` helper 邏輯些微
  重複，屬測試檔案內部瑣事，無害。
- reviewer 額外獨立驗證（非只信任本次回報）：自行 `grep` 確認 3 處替換無遺漏（含
  `CreateFarmModal` 子元件）、逐行核對 diff 只動 `fetch`→`authFetch` 字面未動參數、讀
  `authClient.ts` 確認 `authFetch` header 合併邏輯與測試假設一致、交叉核對後端
  `modules/monitoring/server/routers/farms.py` 的 `require_authenticated()`/`require_role`
  標註與本次風險分類相符、獨立重跑 `FarmSelector.test.tsx` 得到與本次一致的 43/43 全綠結果。

## Wrap-up

- ISSUES.md / STATUS.yaml / TODO.md 已同步更新（見上方「產出清單」）。
- 本次沒有引入未受自動化測試保護的邏輯。既有限制沿用先前 session 的說明：本檔案
  `window.location.reload` stub 手法（整顆 `Location` 換掉再還原）屬既有測試技術債
  （WMOM-20260607-04 既有寫法），本次新增的 4 個測試皆改用既有 `calls`/header 斷言 helper
  的延伸寫法，未引入新的脆弱寫法。
