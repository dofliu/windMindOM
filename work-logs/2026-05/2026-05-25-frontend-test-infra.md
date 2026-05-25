# 2026-05-25 WMOM-20260525-01 — Frontend 測試基礎設施（vitest + RTL）+ 回補 WS / AbortController regression test

> **Issue**：WMOM-20260525-01 — 導入前端測試框架，回補近期修復的 regression test
> **Branch**：`claude/upbeat-davinci-s7U7O`（autonomous daily worker, 5/25 20:00）
> **Goal**：前端首次導入 vitest + React Testing Library 測試基礎設施，並回補 WMOM-20260504-12（WS 殭屍重連根治）與 WMOM-20260504-13（cost AbortController race）兩個近期修復的 regression test。frontend only，backend 零風險。

---

## 1. 為什麼今天做這個

5/24 handoff 候選：
1. WMOM-20260519-01（F1 超量退料 domain guard）— 需劉老師 walkthrough 決定 guard 層級，**不適合 solo**。
2. M5 規劃（RAG）— 需架構決策 + 外部依賴（ChromaDB / RAG_Ultimate 策略檔），**不適合單 session solo**。
3. WMOM-20260513-02 demo orchestrator — 2-3d 跨 session。
4. **前端測試基礎設施（vitest + RTL）** — 連續 3 份 handoff（5/22 / 5/23 / 5/24）都點名的反覆缺口。

選 #4：**solo-friendly、零設計決策、backend 零風險、可在單 session 完整交付且自我驗證**，且直接解決「過去每個前端修復都無法補 regression test」的痛點。這是新工作，故先在 ISSUES.md 開 WMOM-20260525-01 再開工（符合 CLAUDE.md §12「不創建沒列在 ISSUES.md 的工作」）。

---

## 2. 做了什麼

### 2.1 測試基礎設施（infra）

| 檔案 | 變更 |
|------|------|
| `frontend/package.json` | 加 `vitest` / `jsdom` / `@testing-library/{react,dom,jest-dom}` devDependencies；加 `test`（`vitest run`）+ `test:watch`（`vitest`）scripts |
| `frontend/package-lock.json` | lockfile 更新（35 packages） |
| `frontend/vite.config.ts` | `defineConfig` 改從 `vitest/config` import（型別含 `test` 欄位）；加 `test` 區塊：`globals` / `environment: jsdom` / `setupFiles` / `include: **/*.{test,spec}.{ts,tsx}` / `exclude: node_modules,dist` |
| `frontend/tsconfig.json` | `types` 加 `vitest/globals`，讓 tsc 認得 describe/it/expect/vi |
| `frontend/test/setup.ts` | 註冊 `@testing-library/jest-dom/vitest` matcher + `afterEach(cleanup)` |

版本：vitest 3.2.4 / @testing-library/react 16.3.2（相容 React 19）/ jsdom 29 / jest-dom 6.9.1。

### 2.2 Regression tests（回補近期修復）

**`hooks/useRealtimeData.test.ts`（3 tests）— 守 WMOM-20260504-12 WS 殭屍重連根治**
- `卸載後不再排程重連、不再建立新 WebSocket`：以 `FakeWebSocket`（記錄所有實例 + handler）取代全域 WebSocket，fake timer 推進 10s；卸載後 instances 必須維持 1。
- `連線中斷（仍掛載）時 3 秒後自動重連`：正常重連行為不可被誤殺（推進 3s → instances=2）。
- `收到 WS 訊息會解析並更新 turbines`：onmessage → `apiToTurbineData` → state。

**`hooks/useCostData.test.ts`（3 tests）— 守 WMOM-20260504-13 AbortController race**
- `快速切換時舊 fetch 後到不會蓋掉新結果`：mock costService，手動控制 A/B 兩筆 promise 完成順序；先 resolve B 再 resolve A，data 必須是 B（A 因 `signal.aborted` 早退）。
- `被取消的 fetch 拋 AbortError 不會寫進 error state`。
- `reset() 清空 data/error 並 abort in-flight request`。

---

## 3. Verify

- `npx vitest run` → **6 tests 全 pass**（2 files）
- `npx tsc --noEmit` → **0 errors**（含新 test 檔；initial cast error 已用 `as unknown as` 修正）
- `npx vite build` → **0 errors**（既有 recharts chunk size warning 與本 PR 無關）
- Backend 完全未動 → `pytest modules/{workflow,cost,reporting}/tests/` = **565 passed / 1 xfailed / 4 pre-existing 環境性 fail**（3 numpy float 末位 drift + 1 flaky concurrency，與 5/24 baseline 一致），zero regression。

### Mutation test（證明測試有抓 bug 的能力）

把 `useRealtimeData.ts` 臨時退回成**原始 bug**（移除整個 `disposed` 機制 + cleanup handler 解除）：
- `卸載後不再重連` 測試 → **FAIL**（殭屍 WS 讓 instances 變 2）。
- 還原 fix 後 → pass。

→ 證明此 regression test 確實守得住 5/24 的修復，不是空轉的 always-green 測試。（過程用 `git checkout --` 還原，未污染 production code。）

---

## 4. 環境備忘（sandbox 每次重置）

sandbox 初始無 Python / frontend 測試依賴。開工需先：

```bash
pip install pytest pytest-asyncio httpx sqlalchemy jinja2 pandas reportlab pytz
pip install -r requirements.txt
npm install --prefix frontend                 # node_modules 不在 repo
npm install --prefix frontend -D vitest jsdom @testing-library/react @testing-library/dom @testing-library/jest-dom
```

本 PR 已把 vitest 等寫進 `frontend/package.json` devDependencies，故**之後只要 `npm install --prefix frontend` 即含測試依賴**（不需再手動加 -D）。backend 測試依賴仍建議另開 issue 補 `requirements-dev.txt` + SessionStart hook（見下次候選）。

---

## 5. Code review 採納

用 code-reviewer subagent 對 staged diff review：1 must-fix + 5 should-fix + 2 nice-to-have，**全部採納**。

| 級別 | 議題 | 處置 |
|------|------|------|
| Must-fix | `useCostData.test.ts` reset() 的 `act()` 為 sync 未 await，後接 3 個斷言（升版可能 flaky） | **採納** — 改 `await act(async () => {...})` |
| Should-fix | `useRealtimeData.test.ts` 6 處 sync `act()` 未 await | **採納** — test fn 改 async，全部改 `await act(async () => {...})` |
| Should-fix | `vite.config.ts` triple-slash `/// <reference vitest/config>` 與 import 重複 | **採納** — 刪 triple-slash（import 已帶型別） |
| Should-fix | `exclude` 完全覆蓋 vitest `defaultExclude`（單星 `node_modules/**` 無法 match 巢狀） | **採納** — 改 `[...configDefaults.exclude, 'dist/**']` |
| Should-fix | `test/setup.ts` 手動 `cleanup()` 與 RTL 16 globals:true auto-cleanup 重複 + docstring 誤導 | **採納** — 移除手動 cleanup，改正確說明（RTL auto-clean） |
| Should-fix | `FakeWebSocket.close()` 同步觸發 onclose 與真實異步行為不符（reviewer 自承非當前 bug） | **採納（文件化）** — 加註「同步為刻意簡化，要驗的是 null-before-close 順序，同步/異步不影響斷言」 |
| Nice | `run({dataset:'A'} as never)` 不必要的型別逃逸（`DatasetName = string`，本就合法） | **採納** — 移除 `as never` |
| Nice | `Handler` 型別名稱涵蓋不完整（onmessage 另宣告） | **採納** — 改名 `VoidHandler` |

Re-verify（採納後）：vitest 6 pass / tsc 0 / vite build 0，全綠。

---

## 6. 下次接手指南

### 已完成（push 到 origin/claude/upbeat-davinci-s7U7O）

- 前端 vitest + RTL 測試基礎設施（config / setup / scripts / tsconfig types）。
- 2 個 hook 的 6 個 regression test，守住 WS 殭屍重連 + AbortController race 兩個近期修復。
- ISSUES.md / STATUS.yaml 更新；本 work-log。

### 建議下次 session 工作（依優先級）

1. **回補更多 regression test**：基礎設施已就位，可逐步補 `useWorkOrders` / `useMaterialRequests` / `useInventory` 等 hook 的 test；或對 `FarmOverview` 的 `TCard`/`CompactTile` React.memo（5/24）補 areEqual 行為 test。
2. **`requirements-dev.txt` + SessionStart hook**（新 issue 候選）— 把 backend 測試依賴（pytest/sqlalchemy/pandas…）固定下來，省去每次 sandbox 重裝；可搭配 `session-start-hook` skill。
3. **WMOM-20260519-01**（F1 超量退料 domain guard）— 需劉老師 walkthrough 決定 guard 層級。
4. **M5 規劃**（Knowledge/RAG + 現場 mobile UI）— 需與劉老師對齊先做 Knowledge skeleton 還是 mobile /field/ UI。
5. **WMOM-20260513-02** demo orchestrator + simulator（2-3d 跨 session）。

### 給劉老師的話

- 前端現在可以跑測試了：`cd frontend && npm test`（一次性）或 `npm run test:watch`（watch 模式）。
- 本 PR 純加測試 + 測試框架，**沒有改任何功能程式碼**，對 demo / production 行為零影響。
