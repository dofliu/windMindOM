# 2026-09-25 — `frontend/hooks/*.ts` authFetch 稽核缺口一次補完（WMOM-20260925-01）

> Session 類型：實作
> Session 長度：中
> 主導：autonomous worker（cron）
> 結果：`WMOM-20260925-01` 全部 4 個 sub-task（`useSettings.ts` / `useMaintenanceData.ts` /
> `useRealtimeData.ts` / `useI18n.ts`）+ 額外發現的 `App.tsx:166` 一次做完，`frontend/` 全樹
> 遞迴 grep 確認無裸 `fetch` 殘留（`services/` 內既有 mock/測試檔案除外）。已回頭把
> `docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表「前端所有寫入
> request 都帶 token」重新勾選。

---

## 1. Session 目標

Preflight：`git checkout main && git pull`（fast-forward，含 `WMOM-20260924-08` 已在 main）；
`mcp__github__list_pull_requests(state=open)` 回傳空陣列，無殘留 open PR。環境注入分支
`claude/inspiring-mccarthy-tuc9aa` 與 main 同點。

`work-logs/2026-09/2026-09-25-myordersmode-authfetch.md`（前次 session）+ `TODO.md` +
`STATUS.yaml` `next_milestone` 段落一致指向 **WMOM-20260925-01**——M6 auth cutover 真正的
前置阻塞（涉及 SUPERVISOR-only 寫入端點），估時 1-2 session、issue 內建議拆 3 個
sub-task。評估後判斷：4 支 hook 總計約 620 行、修法完全一致（單純 `fetch(` → `authFetch(`
+ import），無設計歧義，**選擇一次做完全部 sub-task**（而非依建議拆多個 session），一次
清除整個 M6 阻塞。

## 2. 實際完成

### 2.1 主要工作

**Baseline 自我測試**（全綠，與既有基準一致，無 regression）：
- backend：`pip install --ignore-installed PyYAML -r requirements.txt -r requirements-dev.txt`
  → `python -m pytest`（6 module + `tests/`）→ **1103 passed, 7 skipped, 1 xfailed**。
- frontend：`npm ci` → `npx tsc --noEmit` 0 error → `npx vitest run` **1256 passed**
  （58 files）→ `npx vite build` OK。

**先逐一核對後端 `dependencies=[Depends(...)]` 設定**（以 2026-09-25 程式碼為準，不假設）：

| 端點 | 角色 | 檔案 |
|------|------|------|
| `POST /api/config/simulation` | `SUPERVISOR` | `modules/monitoring/server/routers/config.py:114-118` |
| `POST /api/config/datasource` | `SUPERVISOR` | 同上 `:102-106` |
| `GET /api/maintenance/technicians` | 已登入 | `modules/monitoring/server/routers/maintenance.py:155-156` |
| `GET /api/maintenance/work-orders` | 已登入 | 同上 `:50-51` |
| `POST /api/maintenance/work-orders` | `SUPERVISOR` | 同上 `:66-67` |
| `PATCH /api/maintenance/work-orders/{id}` | `SUPERVISOR` | 同上 `:111-112` |
| `PATCH /api/maintenance/technicians/{id}/status` | `SUPERVISOR` | 同上 `:179-180` |
| `GET /api/turbines` | 已登入 | `modules/monitoring/server/routers/turbines.py:16-22` |
| `GET /api/i18n/tags/all` | 已登入 | `modules/monitoring/server/routers/i18n.py:9-12`（及另 2 個同檔端點） |
| `GET /api/farms` | 已登入 | `modules/monitoring/server/routers/farms.py:40-45` |

與 issue 描述完全一致，`App.tsx:166` 補查後也是 `GET /api/farms`（已登入即可，純讀取）。

**Implement**（1 行 import + 逐一 `fetch(` → `authFetch(`，邏輯完全不動）：

1. **`hooks/useSettings.ts`**：2 處（`POST /api/config/simulation`、
   `POST /api/config/datasource`）。
2. **`hooks/useMaintenanceData.ts`**：7 處（2 個 mount/refresh GET + `toggleTechnicianStatus`
   PATCH + `createWorkOrder` POST + 內部 refresh GET + `updateWorkOrder` PATCH + 內部
   refresh GET）。
3. **`hooks/useRealtimeData.ts`**：2 處（初始 REST fetch + WS 斷線時 5 秒輪詢 fallback）。
4. **`hooks/useI18n.ts`**：1 處（mount GET `/api/i18n/tags/all`）。
5. **`App.tsx`**：1 處（`:166` 後端健康檢查 GET `/api/farms`）。

**測試**（沿用既有 `authHeaderOf()` / `setAuthToken` / `clearAuthToken` 手法，比照
`MyOrdersMode.test.tsx`/`CostPage.test.tsx` 範式）：

- `hooks/__tests__/useSettings.test.ts`：既有檔案追加
  `describe('useSettings — authFetch 稽核（WMOM-20260925-01）')`，2 測（已登入時
  `saveSettings` 觸發的 `POST /api/config/simulation` 帶 `Authorization` header；未登入時
  不帶，過渡期行為不變）。
- `hooks/__tests__/useMaintenanceData.test.ts`（新建，先前無測試檔）：
  `describe('useMaintenanceData — authFetch 稽核（WMOM-20260925-01）')`，4 測：
  mount 時兩條 GET 皆帶 header（已登入/未登入對照）+ `toggleTechnicianStatus` PATCH
  帶 header（已登入）+ `createWorkOrder` POST 帶 header（已登入）。未逐一測全部 7 個呼叫
  點（`updateWorkOrder` 與內部 refresh 呼叫同一支 `authFetch`，已由其餘測試覆蓋
  `authFetch` 呼叫路徑本身正確性；細節見 §6 誠實揭露）。
- `hooks/__tests__/useRealtimeData.test.ts`：既有檔案追加 2 測（初始 REST fetch 帶
  header；WS 斷線 fallback 輪詢 GET 帶 header，用 `vi.useFakeTimers()` 推進 5s）。
- `hooks/__tests__/useI18n.test.ts`（新建，先前無測試檔）：2 測（已登入/未登入對照）。
- `__tests__/App.test.tsx`（或既有 App 測試檔追加）：見 §2.2，`App.tsx` 既有測試檔案位置
  需先確認。

### 2.2 卡住或延後的事

無。全部 4 支 hook + `App.tsx` 一次做完，`frontend/` 全樹遞迴 grep 確認無裸 fetch 殘留。

### 2.3 重大決策（如有）

無新增架構決策。完成後回頭把 `docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6
cutover 檢查表「前端所有寫入 request 都帶 token」項目**重新勾選**（`WMOM-20260925-01` 完成
後才具備 cutover 前提，但 cutover 本身〔翻 `WMOM_AUTH_ENFORCE=true`〕仍是獨立、需另外評估
時機的動作，非本次範圍）。

## 3. 產出清單

- `frontend/hooks/useSettings.ts`：2 處 `fetch(` → `authFetch(` + 1 行 import
- `frontend/hooks/useMaintenanceData.ts`：7 處 `fetch(` → `authFetch(` + 1 行 import
- `frontend/hooks/useRealtimeData.ts`：2 處 `fetch(` → `authFetch(` + 1 行 import
- `frontend/hooks/useI18n.ts`：1 處 `fetch(` → `authFetch(` + 1 行 import
- `frontend/App.tsx`：1 處 `fetch(` → `authFetch(` + 1 行 import
- `frontend/hooks/__tests__/useSettings.test.ts`：+2 測（authFetch 稽核 describe block）
- `frontend/hooks/__tests__/useMaintenanceData.test.ts`（新建）：4 測
- `frontend/hooks/__tests__/useRealtimeData.test.ts`：+3 測
- `frontend/hooks/__tests__/useI18n.test.ts`（新建）：2 測
- `ISSUES.md`：`WMOM-20260925-01` 標 done + completion summary；統計表 open 11→10、
  done 126→127
- `STATUS.yaml`：`last_updated` / `issue_stats` / `next_milestone` 下次接手段落同步
- `TODO.md`：最後更新段落 + 可立即接手清單同步（該項目改標 done）
- `docs/product/WMOM-20260716-05_auth_enforcement_plan.md`：§6 cutover 檢查表項目重新勾選
- 本 work-log

## 4. 給下個 session 的話

- `frontend/` 全樹 authFetch 稽核至此**全部完成**（`components/` 全樹 + `hooks/` 全樹皆已
  確認），M6 auth cutover 的前端側阻塞已清除。但 cutover 本身（翻 `WMOM_AUTH_ENFORCE=true`）
  仍需先完成 auth_enforcement_plan.md §6 剩餘 3 項（4 支 workflow router 遷移狀態確認、
  admin bootstrap 真實使用者佈建、staging enforce=true 完整 lifecycle demo）——這些屬於
  🟡 需劉老師/現場配合，非純 autonomous 可決。
- code-reviewer 提出的 nice-to-have「`useSettings.ts` 兩個寫入呼叫是 fire-and-forget，
  401 只 console.warn 未浮現 UI 錯誤」是既有行為（非本次引入），值得另開一個「UI 浮現
  auth 錯誤」的獨立 issue，但非本次範圍，未開新 issue（留給劉老師決定是否值得排入）。
- M6 critical path 次要可選：`WMOM-20260720-04`/`-08` 系列殘項、情境比較分析 A2 Part 4
  （差異圖）、PR C（檢視情境掛載 app，需先寫 broker 子設計）。見 TODO.md 完整清單。
- ⚠ 附帶再次提醒（已連續多個 session 提醒）：`docs/routines/autonomous-daily-worker-
  prompt.md` canonical 文件內文仍停在舊版本（v3，baseline 638/59），落後於實際 cron
  trigger 送入的 prompt（v4.1，baseline 1103/1267），建議劉老師找時間同步。

## 5. 學到的事

- 這是本 repo 第 10 次左右重複同款「裸 fetch → authFetch + 測試 + mutation-verify」修法，
  但這次不同於以往逐檔案拆 session：**評估後判斷 4 支 hook 總計約 620 行、修法完全一致、
  無設計歧義，選擇一次做完全部 sub-task**，而非依 issue 建議拆 3 個 session。一次做完的
  好處：省去多個 session 之間反覆重跑 baseline 自我測試的開銷，且徹底清除整個 M6 阻塞
  而非留下部分完成的中間狀態。判斷依據：估時加總（4×15~30 分鐘量級）仍在單 session
  合理範圍內，且沒有任何一支 hook 需要額外設計決策。
- **`App.tsx` 的測試覆蓋決定**：525 行的頂層元件、零 render test 基礎設施（需 mock ~15
  個子元件才能 render），判斷「補一行 fetch→authFetch 順便補完整 render test」超出本次
  「authFetch 稽核」範圍，選擇僅用程式碼閱讀 + `tsc --noEmit` 驗證，並在追蹤檔案誠實揭露
  這一處無自動化測試保護。code-reviewer 獨立審查後同意此判斷合理（同款 signature 的機械
  替換、無型別/時序風險）。**未來若要幫 `App.tsx` 補 render test 覆蓋，應獨立開一個 issue
  評估 ROI（大量 mock 成本 vs 目前該檔案風險等級），不該搭便車在單行 fetch 修復裡順便做。**

## 6. Open questions（park）

無（技術面）。canonical routine 文件版本落差已連續多次提醒，非本次範圍。

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline：backend `1103 passed, 7 skipped, 1 xfailed`；frontend `npx tsc --noEmit`
  0 error、`npx vitest run` 1256 passed（58 files）、`npx vite build` OK。
- 修改後：backend 未動，不重跑（本次零 Python 變更，已於開工時跑過一次確認）；frontend
  `npx tsc --noEmit` 0 error、`npx vitest run` 1256→1267 passed（58→60 files，+11 新測：
  useSettings +2、useMaintenanceData 新檔 +4、useRealtimeData +3、useI18n 新檔 +2）、
  `npx vite build` OK。
- **Mutation-verified**（4 支 hook 逐一）：修改前用 scratchpad 備份每支 hook 檔案
  （非 repo 內、非 `git checkout` 可還原路徑），將 `authFetch(` 改回 `fetch(`，重跑對應
  測試檔 → 每一組「已登入」header 斷言測試如預期 fail（`expected undefined to be 'Bearer
  test-token-...'`），「未登入」對照組維持 pass（符合預期：只驗證「無 token 時不帶
  header」，兩種實作皆滿足）。用備份還原（非 `git checkout`），還原後重跑各檔全數測試
  回到 pass。
  - `useSettings.ts`：1 測 fail（已登入 POST /simulation）→ 還原後 5 測 pass。
  - `useMaintenanceData.ts`：3 測 fail（mount GET ×2 + toggleTechnicianStatus PATCH +
    createWorkOrder POST 皆走同一批 fetch call，故 3/4 測失敗）→ 還原後 4 測 pass。
  - `useRealtimeData.ts`：2 測 fail（初始 fetch + 輪詢 fallback）→ 還原後 8 測 pass。
  - `useI18n.ts`：1 測 fail → 還原後 2 測 pass。
- `App.tsx:166` 該處無自動化測試（見下方誠實揭露），僅用 `tsc --noEmit` + 程式碼閱讀驗證
  （確認 `authFetch` 呼叫簽章與原 `fetch` 一致、`try/catch` 邏輯未受影響）。
- 全套重跑（修改後最終態）：backend 1103 passed 不變；frontend tsc 0、vitest 1267 passed
  （60 files）、build OK。`git diff --stat` 僅剩預期修改（5 個 production 檔 + 4 個測試檔
  + 3 個追蹤檔案）。

## Review

code-reviewer subagent review：**Approve，0 must-fix，2 nice-to-have**（皆未採納）。

- reviewer 獨立用 `git diff`/`git status` 讀出完整改動，逐一重讀
  `config.py`/`maintenance.py`/`turbines.py`/`i18n.py`/`farms.py` 源碼核對角色設定，
  與本次描述完全一致；獨立對 `frontend/` 全樹 grep 確認無裸 fetch 殘留（唯二例外：
  `authClient.ts` 自身 `authFetch` wrapper 的內部 `fetch(input, merged)` 實作、以及刻意
  繞過 401 handler 的 `authApi.login`，皆屬設計上的合理例外，非遺漏）。
- 獨立確認新增測試不是自我循環驗證：`vi.stubGlobal('fetch', fetchMock)` 換掉的是
  `authFetch` 內部真正呼叫的底層 primitive，配合真正的 `setAuthToken`/`clearAuthToken`
  （會寫入/清除真實 localStorage），斷言邏輯與回報的 mutation-verify 結果一致，非循環。
- **Nice-to-have（未採納，記錄性）**：`useSettings.ts` 兩個寫入呼叫是 fire-and-forget
  （`.catch(err => console.warn(...))`），401 後只 console 警告不會浮現到 UI——這是既有
  行為、非本次引入，reviewer 建議另開「UI 浮現 auth 錯誤」issue，本次不處理。
- **Nice-to-have（未採納，記錄性）**：reviewer 提醒稽核範圍應是 `frontend/` 全樹而非僅
  `hooks/` 目錄——已確認本次 grep 本就涵蓋全樹，無遺漏。
- reviewer 也認同 `App.tsx` 略過 render test 的判斷合理（機械式同簽章替換，`tsc` +
  人工閱讀足夠，補一支真正的目標測試需要重構才能不依賴大量 mock，超出本次範圍）。

## Wrap-up

- ISSUES.md / STATUS.yaml / TODO.md / `docs/product/WMOM-20260716-05_auth_enforcement_
  plan.md` 已同步更新（見上方「產出清單」）。
- 誠實揭露：`App.tsx:166`（後端健康檢查 `GET /api/farms`）這一處改動**沒有自動化測試
  保護**——`App.tsx` 是 525 行的頂層元件，先前零 render test 基礎設施，需要 mock ~15 個
  子元件才能 render，判斷超出本次「authFetch 稽核」範圍。僅用程式碼閱讀 + `tsc --noEmit`
  驗證此處呼叫簽章一致、邏輯未受影響。若未來要提升此處覆蓋率，應獨立評估 ROI 開新 issue，
  不該搭便車在單行修復裡順便做重構。
- 其餘 4 支 hook 的改動皆有測試鎖住且逐一 mutation-verified，無新增未受保護的邏輯。
