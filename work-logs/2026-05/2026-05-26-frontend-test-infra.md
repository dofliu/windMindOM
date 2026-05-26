# 2026-05-26 WMOM-20260526-01 — 前端測試基礎設施（vitest + RTL）+ 回補兩支 regression test

> **Issue**：WMOM-20260526-01 — 前端測試基礎設施落地（新開）
> **Branch**：`claude/upbeat-davinci-LPk4a`（autonomous daily worker, 5/26 20:00）
> **Goal**：為 frontend（React 19 + Vite 6 + TS）導入 vitest + @testing-library/react，並回補前兩次 session（5/23 cost AbortController、5/24 WS 記憶體 leak）因「無測試框架」而欠的 regression test。frontend-only，零 backend 風險。

---

## 1. 為什麼今天做這個

5/24 handoff 候選：WMOM-20260519-01（F1 超量退料 domain guard，**需劉老師 walkthrough** 決定 guard 層級，不適合 solo）/ M5 規劃（RAG 需架構決策 + 外部依賴 ChromaDB / RAG_Ultimate 策略檔）/ WMOM-20260513-02 demo orchestrator（2-3d 跨 session）/ **前端測試基礎設施（vitest+RTL）**。

選最後一項：5/23 與 5/24 兩次 session 結尾都明寫「frontend 無測試框架，未加自動化 regression test，建議另開 issue 導入 vitest+RTL」。這是 solo-friendly、單 session 可完成、可驗證、零 backend regression 的工，且能直接把兩個剛上線的修復鎖住——符合 daily routine「一日一項重要工作」。新開 issue WMOM-20260526-01。

---

## 2. 做了什麼

### 2.1 測試基礎設施

- `npm install -D vitest@^2.1.9 jsdom@^25 @testing-library/react@^16 @testing-library/dom@^10`
- `frontend/vitest.config.ts`：`environment: 'jsdom'`（提供 WebSocket / DOMException / DOM API）、`globals: true`（讓 RTL auto-cleanup 的 afterEach 生效）、`include: ['**/*.test.{ts,tsx}']`。
- `frontend/package.json` scripts：`"test": "vitest run"` + `"test:watch": "vitest"`。

### 2.2 回補 regression test

**`frontend/hooks/useRealtimeData.test.ts`（WMOM-20260504-12 WS 殭屍重連）**

- 受控 `MockWebSocket`：記錄所有被建立的實例；`close()` 同步觸發 `onclose`（模擬瀏覽器 close→close event 行為，正是舊版殭屍重連觸發點）。
- 測試 1：unmount 後快轉 30s，`instances` 仍為 1 → 證明無殭屍重連。
- 測試 2：掛載期間直接觸發 `instances[0].onclose()`（模擬 server 關閉），過 3s 後 `instances` 變 2 → 證明正常重連未被破壞。

**`frontend/hooks/useCostData.test.ts`（WMOM-20260504-13 AbortController race）**

- `vi.mock('../services/costService')` 把 `costApi` 換成可控 vi.fn；用 deferred promise 控制 resolve 時序。
- 測試 1：連 run('a')、run('b')；先 resolve 新的（B）→ data=RESP_B；再 resolve 舊的（A）→ data 仍為 RESP_B（舊 request signal 已 abort 被丟棄）；loading=false / error=null。
- 測試 2：`reset()` 後 loading=false / data=null / error=null；被 reset abort 的 request 後到也不寫回。

---

## 3. 設計取捨

### 3.1 vitest.config 不掛 @vitejs/plugin-react

vitest 2.1.9 **硬依賴 vite ^5.0.0**（nested 安裝 vite 5.4.21），而 app 用 vite 6.4.1。若在 vitest.config 掛 `react()` plugin，會引入兩份 vite 的 `Plugin` / `PluginOption` 型別衝突 → `npx tsc --noEmit` 報 TS2769。

因目前測試皆為 **.ts hook 測試（無 JSX）**，esbuild 直接轉 TS 即可，不需 react plugin（Fast Refresh / JSX automatic runtime 對 hook 測試無用）。故 config 不掛 plugin，tsc 0 errors。已在 config 註解：未來若加 .tsx 元件渲染測試，再評估升級 vitest 至支援 vite 6 的版本並掛回 react plugin。

> 替代方案評估過：(a) `defineConfig` from `vite` + 三斜線 `/// <reference types="vitest/config" />` → overload 仍不認 `test` 欄位（TS2769）；(b) `npm dedupe` → vitest 2.1.9 peer 就是 vite 5，無法 dedupe 成單一 vite。故採「不掛 plugin」最乾淨。

### 3.2 為什麼相信測試有抓 regression 的能力（mutation test）

對 `useRealtimeData.ts` 暫時還原成舊 bug（onclose 無條件 `setTimeout(connect)` + cleanup 不解除 handler + 移除 `disposed`），跑 `useRealtimeData.test.ts` → unmount 測試如預期 **fail**（`instances` length 2 vs 期望 1）。證明測試不是「永遠會過」的空測試。之後用 `git checkout -- frontend/hooks/useRealtimeData.ts` 完整還原原始碼（git diff 確認為空）。

---

## 4. 檔案異動

```
+ frontend/vitest.config.ts               vitest 設定（jsdom + globals）
+ frontend/hooks/useRealtimeData.test.ts  WS 殭屍重連 2 tests
+ frontend/hooks/useCostData.test.ts      AbortController race 2 tests
M frontend/package.json                   test / test:watch scripts + 4 devDeps
M frontend/package-lock.json              npm install lock
M ISSUES.md                               新增 WMOM-20260526-01（done）+ 統計
M STATUS.yaml                             last_updated / next_milestone
+ work-logs/2026-05/2026-05-26-frontend-test-infra.md  本檔
```

未動任何 app source（hooks / components / services），亦未動 backend。

---

## 5. Verify

- `npx vitest run` → **2 files / 4 tests passed**
- `npx tsc --noEmit` → **0 errors**
- `npx vite build` → **748 modules / 5.07s / 0 errors**（chunk size warning 為既有 recharts，與本 PR 無關）
- Backend 完全未動 → zero backend regression。
- 開工 backend baseline（參考）：`pytest modules/{workflow,cost,reporting}/tests/` → 564 passed / 1 xfailed / 5 環境性 fail（3 numpy float 末位 drift + 2 SQLite concurrency flaky，其中 `test_concurrent_dispatch_one_loses_when_stock_short` 單獨複跑仍 fail，屬 sandbox SQLite 序列化限制；皆與本 PR 無關、5/22-5/24 handoff 已記錄）。

---

## 6. Code review 採納

code-reviewer subagent 對 staged diff（vs main）review：**0 must-fix / 2 should-fix / 3 nice-to-have，verdict Approve**。

| 級別 | 議題 | 處置 |
|------|------|------|
| Should-fix | `vi.restoreAllMocks()` 對 `vi.mock()` factory 的 vi.fn 無效，清理實際靠 beforeEach | **採納** — 改用 `vitest.config` 的 `mockReset: true` 統一清理，移除 useCostData 的 beforeEach/afterEach |
| Should-fix | 重連測試「timer 未到期仍一條」有註解無斷言（若改成 `setTimeout(connect,0)` 測試仍過） | **採納** — onclose 後立即 assert 仍 1 條 + 推進 2999ms assert 仍 1 條 + 補 1ms assert 變 2 條，精確鎖住 3s 邊界 |
| Nice | `flushMicrotasks` 單一 microtask tick 不足以結算 fetch().then().then() 鏈 | **採納** — 改 3 ticks + 註解 fake timers 下不可用 setTimeout flush |
| Nice | 缺 `fn()` 拋真實錯誤的 error path test（`isAbortError` 非 abort 分支未覆蓋） | **採納** — 新增 `mockRejectedValueOnce(Error('API 500'))` → assert error state（測試數 4→5） |
| Nice | `globals:true` 但 tsconfig types 無 `vitest/globals` | **不採納** — 測試一律顯式 import，tsc 0 errors；加 `vitest/globals` 到 app tsconfig 會污染整個 app 型別空間，比現狀更糟 |

採納後重跑：vitest **5 passed** / tsc 0 errors / vite build 748 modules 0 errors。

---

## 7. 下次接手指南

### 已完成（push 到 origin/claude/upbeat-davinci-LPk4a）

- vitest + jsdom + RTL 基礎設施就位；`npm run test` 可跑。
- 兩支 hook regression test 鎖住 5/23 + 5/24 的修復。

### 建議下次 session 工作（依優先級）

1. **WMOM-20260519-01**（F1 超量退料 domain guard，0.5-1d）— 需劉老師 walkthrough 決定 guard 層級（domain / router / UI），不適合 solo。
2. **M5 規劃** — 讀 ROADMAP M5（Knowledge/RAG + 現場 mobile UI）；RAG 依賴 ChromaDB + RAG_Ultimate 策略檔/向量檔，建議先與劉老師對齊「先做 Knowledge skeleton 還是 mobile /field/ UI」。
3. **WMOM-20260513-02** demo orchestrator + simulator（2-3d 跨 session）。
4. **元件層測試擴充**（接續本次）— 若要測 .tsx 元件渲染，需升級 vitest 至支援 vite 6 的版本（或評估把 app 降到單一 vite）並掛回 @vitejs/plugin-react；可補：FarmOverview 卡片 React.memo areEqual 的 stale-render 測試、CostPage dataset 切換流程測試。

### 環境備忘（給下次 sandbox session）

sandbox 初始無 Python / frontend 依賴。開工需先：

```bash
pip install pytest pytest-asyncio httpx sqlalchemy jinja2 pandas reportlab pytz scipy
pip install -r requirements.txt
npm install --prefix frontend      # 含 vitest 等 devDeps（已在 package.json）
```

跑前端測試：`cd frontend && npm run test`。
