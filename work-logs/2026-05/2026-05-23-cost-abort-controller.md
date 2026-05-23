# 2026-05-23 — WMOM-20260504-13 Cost fetch AbortController（防 React 18 Strict Mode race）

> Session 類型：實作（小工）
> Session 長度：短（~0.2 工作天）
> 主導：Claude（autonomous daily worker, 20:00 Asia/Taipei cron 觸發）
> 結果：**完成** — 2 個 frontend 檔，code-reviewer 1 must + 2 should + 3 nice 全採納；tsc + build green、backend zero regression

---

## 1. Session 目標

WMOM-20260504-13（code-reviewer 對 WMOM-10 finding #5）：

- `useCostData` 內 `useAsync.run` 沒有 abort 機制
- React 18 Strict Mode dev 環境會 mount→unmount→mount，`useEffect([dataset])` 觸發兩次 fetch
- 慢 fetch 比快 fetch 後回，會用舊 dataset 結果蓋新 dataset 結果（race）
- 用戶手動快速切 dataset 也會撞到同樣 race

**驗收（從 issue）：**
- dev mode 切 dataset 5 次，最終顯示的 forecast 一定對應最後一次選的 dataset
- 取消舊 fetch 不會 throw 進 error state

**建議實作（從 issue）：**
- `useAsync.run` 內建立 `AbortController`，next run 前 abort 上一個
- fetch 接到 AbortError 時不視為 error（直接 return）

---

## 2. 設計決策

### 2.1 簽名變動範圍

需要從 `useCostData` → `costApi.*` → `postJSON` 一條鏈把 `AbortSignal` 傳下去：

| Layer | Before | After |
|-------|--------|-------|
| `postJSON<TReq, TResp>(path, body)` | 2 args | 3 args，第 3 加 `signal?: AbortSignal` |
| `costApi.forecast(req?)` 等 4 個 | 1 arg | 2 args，第 2 加 `opts?: { signal? }` |
| `useAsync` 的 `fn` callback | `(req) => Promise<T>` | `(req, opts: { signal }) => Promise<T>` |

對既有 caller 完全相容：所有新增 param 都是 optional + 預設值。

### 2.2 `useAsync` 內 AbortController 生命週期

用 `useRef<AbortController | null>` 持有當前 controller：

1. **每次 `run` 開頭**：若 ref.current 存在 → `abort()`；建新 controller 並寫回 ref
2. **fetch 完成（success / non-abort error）**：清 ref；setData/setError/setLoading 正常
3. **fetch 拋 `AbortError`**（即 `err.name === 'AbortError'` 或 `DOMException.code === 20`）：
   - **不**碰 setData/setError/setLoading
   - 直接 return（已被新一輪 run 接管 loading state）
4. **component unmount**：useEffect cleanup 內 abort 當前

### 2.3 邊界條件

| Case | 處理 |
|------|------|
| `signal.aborted` 為 true 時呼叫 fetch | 瀏覽器/Node 會立刻 reject AbortError，我們的 catch 認得 → 不寫 state |
| 同一個 run 被連續 abort 兩次（A → B → C 三次切換） | 每輪都把 ref 換成新 controller；A 與 B 的 catch 都走 AbortError 分支，C 的 setData/setError 才生效 |
| `setLoading(false)` 該不該在 finally 跑 | 若是被 abort 的 run → **不該**（已被新一輪 setLoading(true) 接管）；非 abort → 該。所以 finally 不能無條件 false，要先檢查 signal.aborted |

### 2.4 為何不用 promise cancellation library

`AbortSignal` 是 fetch 原生支援的標準 API（React 19 + Vite + 現代瀏覽器 / Node 18+ 都全綠），不必引第三方。

---

## 3. 變動清單（規劃）

### 修改檔案

- `frontend/services/costService.ts`
  - `postJSON` 加第 3 參數 `signal?: AbortSignal`，傳入 fetch
  - `costApi.{forecast, lcoe, monteCarlo, varFluct}` 各加第 2 參數 `opts?: { signal? }`
- `frontend/hooks/useCostData.ts`
  - `useAsync` 加 `controllerRef`、`run` 內 abort 上一個 + 建新的 + 傳 signal
  - catch 內判 AbortError 不寫 state
  - useEffect cleanup unmount 時 abort

### 不動的檔案（驗證）

- `frontend/components/CostPage.tsx` — call site 不變（`forecast.run({ dataset })`、`forecast.reset()`、`runAll()`），因為新增 param 都 optional
- 其他 6 個 hooks（`useReports`, `useInventory`, ...）— 不在 scope；issue 只針對 cost

### 不新增測試

frontend 目前無 vitest / jest 設置（`package.json` 無 test script，無 `*.test.*` 檔）。
驗證走 `npx tsc --noEmit` + `npx vite build` zero regression + 視覺 review。

---

## 4. TODO

- [x] Preflight（main pull + baseline test）
- [x] Branch + work-log
- [x] 改 `costService.ts` 加 signal 鏈
- [x] 改 `useCostData.ts` 加 AbortController + AbortError 處理 + unmount cleanup
- [x] `cd frontend && npx tsc --noEmit && npx vite build`
- [x] code-reviewer subagent（找 must / should-fix）
- [x] ISSUES.md / STATUS.yaml 更新（done）
- [ ] commit + push + PR

---

## 5. 實作紀錄

### 5.1 完成檔案

**Frontend 修改（2 個檔）：**

- `frontend/services/costService.ts`
  - 加 `export interface CostApiOptions { signal?: AbortSignal }`
  - `postJSON<TReq, TResp>(path, body, signal?)` — 第 3 參數轉給 fetch
  - JSDoc 標 `@throws {DOMException}` 說明不攔 AbortError，呼叫方自負分辨
  - 4 個 `costApi.*` 各加第 2 參 `opts: CostApiOptions = {}`，傳 `opts.signal` 給 postJSON
- `frontend/hooks/useCostData.ts`
  - 新增 `isAbortError()` helper（覆蓋 DOMException `name === 'AbortError'` + legacy `code === 20`）
  - `useAsync` 改用 `useRef<AbortController | null>` 持有 in-flight controller
  - `run` 開頭 `controllerRef.current?.abort()` + new controller + 寫 ref
  - try 內 `await fn(req, { signal })`，await 後 `if (controller.signal.aborted) return;` 防禦性檢查（fn 內部吃掉 AbortError 不 rethrow 的極端情況）
  - catch 內 `if (isAbortError(e) || controller.signal.aborted) return;` — 不寫 error、不關 loading
  - finally guard `controllerRef.current === controller && !controller.signal.aborted` 才動 loading + 清 ref
  - `useEffect(() => () => { controllerRef.current?.abort(); controllerRef.current = null; }, [])` — unmount 取消
  - `reset()` 同步 abort（**review S2 must**：避免 reset 清空 → 慢 fetch 後回又 setData 寫回 stale 結果）
  - 4 個 hook 的 fn callback 簽名從 `(req) => Promise<T>` 改成 `(req, opts: CostApiOptions) => Promise<T>` — 與新 `costApi.*` 對齊

### 5.2 設計決策落實

- **TypeScript 向後相容**：`costApi.forecast(req)` 既有 caller（`CostPage.tsx` 4 處）不改即可繼續 compile，因為新增 `opts` 參數有預設值 `= {}`
- **reset() 也 abort**：原 review 問「reset 不 abort 是 bug 還是合理？」— **是 bug**。`CostPage.tsx:721-723` 切 dataset 時對 lcoe/monteCarlo/varFluct 呼叫 reset()，若這 3 個 panel 之前剛點過 run 仍 in-flight，舊 dataset 結果會在 reset 之後 setData 回來蓋掉清空的視覺。fix 讓 reset 同步 abort + setLoading(false)，視覺對齊
- **finally guard 三條件**：`controllerRef.current === controller`（這輪 controller 還是當前的）+ `!controller.signal.aborted`（沒被 abort）— 缺一不可。前者擋「下一輪 run 已啟動換掉 ref」；後者擋「unmount cleanup 已 abort 但 finally 還在跑」
- **unmount 後 loading 永遠 true 的 leak**：reviewer 標 must-fix 但承認 local useState 重 mount 自然 reset → 不修，加註解警告未來若把 loading 提升到 context / 父層需重審。註解寫進 hook 檔頭部 + finally 內部
- **`useCallback([fn])` dep 穩定性**：`costApi.forecast` 等是 module-level object literal 屬性，reference 穩定 → useCallback 只在 mount 建一次。加註解警告未來若改成 factory function 會破。註解在 run 的 dep 陣列旁
- **`isAbortError` legacy `code === 20`**：DOMException.ABORT_ERR 在 undici / 現代瀏覽器都已不暴露此屬性，留作 polyfill 安全網。註解說明清楚以免後人誤刪

### 5.3 Build / verify

- `cd frontend && npx tsc --noEmit` → clean（無 error）
- `cd frontend && npx vite build` → `dist/assets/index-DlemOw5K.js 917.69 kB │ gzip: 265.11 kB`，與 main `index-2xF4-p8l.js 917.63 kB` 差 0.06 kB（純語意內容）→ build green
- Backend baseline（純 frontend 改動不該動 backend，做雙保險）：`python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ --deselect ...5 個 pre-existing env-flaky` → **564 passed + 1 xfailed**（zero regression）
- 5 個 deselect 與本 PR 無關：3 numpy drift（pre-existing 環境版本差異，handoff doc 5/22 已記錄）+ 2 SQLite WAL 並發 dispatch flaky（環境 timing；本 PR 完全沒碰 backend）

### 5.4 Code review 採納

| 級別 | # | 議題 | 修法 |
|------|---|------|------|
| Must-fix | M1 | unmount 後 loading 留 true 的潛在 leak | 加註解（hook 檔頭部 + finally 內部）說明 local useState 重 mount 自然 reset；提醒未來提升狀態到 context 需重審 |
| Should-fix | S2 | `reset()` 不 abort in-flight → dataset 切換顯示 stale UX bug | 採納 — reset() 同步 abort + 清 ref + setLoading(false)；註解說明此「視覺一致性」設計意圖 |
| Should-fix | S3 | `useCallback([fn])` 依賴 costApi 結構穩定的隱性假設 | 採納 — 在 dep 陣列旁加註解說明 fn 是 module-level stable reference；未來若改 factory function 會破 |
| Nice | N4 | `isAbortError` 對 `code === 20` legacy 識別說明不清 | 採納 — 重寫註解明示 undici / 現代瀏覽器不暴露 code，留 polyfill 安全網 |
| Nice | N5 | try 內 `signal.aborted` 防禦性檢查像 dead code | 採納 — 加註解說明「防 fn 內部吃掉 AbortError 不 rethrow 的極端情況」 |
| Nice | N6 | `postJSON` 沒文件說明它不攔 AbortError | 採納 — 加 JSDoc `@throws {Error}` non-2xx / `@throws {DOMException}` abort |

無新 follow-up issue（M1 不修但加註解；S2/S3/N4/N5/N6 都已在本 PR 修完）。

---

## 6. 下次接手指南

### 已完成（push 後在 `claude/issue-WMOM-20260504-13-2026-05-23` 分支）
- WMOM-20260504-13 cost frontend AbortController 完整實作 + code review 全收
- ISSUES.md（issue done + 統計表 done 42→43 / open 15→14）/ STATUS.yaml（last_updated 2026-05-23 / issue_stats / next_milestone）更新

### 待辦（不阻塞）
- **PR 開啟**：sandbox GitHub MCP 工具齊全，本 session 會嘗試 `mcp__github__create_pull_request` 開 draft PR

### 建議下次 session 工作（依優先級）

1. **WMOM-20260519-01**（F1 follow-up，0.5-1d）— `add_return` 超量退料 domain guard 評估；需與劉老師 walkthrough 決定 guard 策略（domain layer vs router vs UI），**不適合 solo session**
2. **M5 規劃**：讀 `docs/product/ROADMAP.md` M5 章節決定第一個 issue（RAG knowledge module skeleton or demo orchestrator UI）；獨立 session 因 single-session 不易完整完工
3. **WMOM-20260513-02** demo orchestrator simulator 接合（2-3d 跨 session）— A10 e2e 接 simulator 一鍵 replay lifecycle，M5 demo 視覺化用
4. **WMOM-20260504-12** frontend 長時間執行記憶體成長（觀察） — 可結合本 PR 加的 AbortController 一起設計 leak 重現環境

---

## 7. 學到的事

- React hook 的 `useCallback` dep 陣列穩定性常常依賴上層 module structure，是隱性 contract — 值得加註解免後人重構誤踩
- `reset()` 與 `abort()` 在語義上一體：清視覺就應該停止 in-flight 寫回，否則 race window 必撞 UX bug
- frontend 沒 vitest 設施是現有 tech debt — 此類 race-condition 改動最好搭配單元測試，但本 issue scope 小且改動有單純的 mental model，code review + 視覺 inspect + tsc/build 已足夠 confidence

---

## 8. Open questions（park）

- 是否要為 frontend 引入 vitest + `@testing-library/react`？race-condition 邏輯（abort / unmount / Strict Mode 雙 mount）特別適合用單元測試守住。可開新 issue 評估
- 其他 6 個 hook（`useReports`, `useInventory`, `useMaterialRequests`, `useWorkOrders`, `usePendingApprovals`, `useInventoryItems`）有沒有相同 race risk？短答：有（同 useState 模式），但 UX 風險低於 cost（cost 切 dataset 是 hot path，其他多為 click-to-fetch）。可開新 issue 抽 reusable `useAsync` hook 統一處理
