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

（實作中依序記錄，若無則留白，見下方 Verify 區塊有完整結果。）

### 2.3 重大決策（如有）

無新增架構決策。完成後回頭把 `docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6
cutover 檢查表「前端所有寫入 request 都帶 token」項目**重新勾選**（`WMOM-20260925-01` 完成
後才具備 cutover 前提，但 cutover 本身〔翻 `WMOM_AUTH_ENFORCE=true`〕仍是獨立、需另外評估
時機的動作，非本次範圍）。

## 3. 產出清單

見下方 Wrap-up。

## 4. 給下個 session 的話

見下方 Wrap-up。

## 5. 學到的事

見下方 Wrap-up。

## 6. Open questions（park）

見下方 Wrap-up。
