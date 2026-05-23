# 2026-05-23 WMOM-20260504-13 — Cost 系列 fetch 加 AbortController 防 race

> **Issue**：WMOM-20260504-13 — Cost 系列 fetch 加 AbortController 防 race
> **Branch**：`claude/issue-WMOM-20260504-13-2026-05-23`（autonomous daily worker, 5/23 20:00）
> **Goal**：`useCostData.useAsync.run` 加 AbortController，消除 React 18 Strict Mode 雙觸發 / 快速切 dataset 造成的 stale-overwrites-fresh race；frontend only，低風險。

---

## 1. 為什麼今天做這個

5/22 handoff 推薦下次優先做 WMOM-20260504-13（0.25d，single-session 友善，frontend only，low risk）。符合 daily worker「一日一項小工」哲學，且不需劉老師設計決策（不像 WMOM-20260519-01 超量退料 guard 要 walkthrough）。

問題來源是 WMOM-20260504-10 的 code-reviewer finding #5：

- `useCostData` 的 `useAsync.run` 沒有 abort 機制。
- React 18 Strict Mode dev 環境 mount→unmount→mount，`useEffect([dataset])` 觸發兩次 fetch。
- 慢 fetch 比快 fetch 後回 → 用舊 dataset 結果蓋掉新 dataset 結果（race）。
- 使用者手動快速切 dataset 也撞同樣問題。

**驗收標準**：dev mode 切 dataset 5 次，最終顯示的 forecast 一定對應最後一次選的 dataset；取消的舊 fetch 不會 throw 進 error state。

---

## 2. 設計決策

### 2.1 signal 透傳（costService.ts）

`postJSON` 加 optional `signal?: AbortSignal` 參數，傳給 `fetch({ ..., signal })`；`costApi` 4 個 method（forecast / lcoe / monteCarlo / varFluct）各加 optional `signal` 第二參數轉傳。純擴充，既有呼叫端（不帶 signal）行為不變。

### 2.2 useAsync.run 的 AbortController（useCostData.ts）

核心是用 `useRef<AbortController | null>` 追蹤「目前最新一筆 in-flight request」：

```ts
const run = useCallback(async (req?) => {
  controllerRef.current?.abort();          // 先 abort 上一筆
  const controller = new AbortController();
  controllerRef.current = controller;
  setLoading(true); setError(null);
  try {
    const result = await fn((req ?? {}) as TReq, controller.signal);
    if (controller.signal.aborted) return; // 已被取代 → 丟棄 stale 結果
    setData(result);
  } catch (e) {
    if (isAbortError(e) || controller.signal.aborted) return; // 取消不算錯
    setError(...);
  } finally {
    if (controllerRef.current === controller) setLoading(false); // 只有最新 request 結束 loading
  }
}, [fn]);
```

三道防線確保「最後一次選的 dataset 結果勝出」：

1. **下一筆 run 前 abort 上一筆** → 慢 fetch 被取消，underlying fetch reject AbortError。
2. **`signal.aborted` 早退** → 即使舊 fetch 已 resolve（abort 太晚），also 不會 `setData` 蓋掉新結果。
3. **`controllerRef.current === controller` loading guard** → 被取代的 run 不亂動 loading state。

`reset()` 也 abort 並清 loading（dataset 切換時其他三 panel reset）。`useEffect` cleanup 在 unmount 時 abort 仍 in-flight 的 request，避免 unmounted setState 警告。

### 2.3 backward compat

純擴充 / 行為強化。Public API 不變：`useCostData()` 回傳 shape 不變（data/loading/error/run/reset），CostPage 4 個 panel 按鈕 + dataset 切換 effect 完全相容（已 tsc + build 驗證）。唯一行為差異：被取代的舊 fetch 結果不再寫進 state（這正是修復目標）。

---

## 3. 檔案異動

```
M frontend/services/costService.ts   postJSON + costApi×4 加 optional AbortSignal 透傳
M frontend/hooks/useCostData.ts       useAsync 加 controllerRef + abort + signal.aborted guard + isAbortError + unmount cleanup
M ISSUES.md                           WMOM-20260504-13 標 done；stats open 15→14 / done 42→43
M STATUS.yaml                         last_updated / issue_stats / next_milestone
+ work-logs/2026-05/2026-05-23-cost-abortcontroller.md  本檔
```

---

## 4. Verify

- `cd frontend && npx tsc --noEmit` → **0 errors**
- `npx vite build` → **748 modules / 4.58s / 0 errors**（chunk size warning 為既有 recharts，與本 PR 無關）
- Backend baseline（未動，僅參考）：`pytest modules/{workflow,cost,reporting}/tests/` → 566 passed / 1 xfailed / **3 pre-existing numpy float drift**（test_cost_api monte_carlo_seed_42 / test_monte_carlo percentiles / test_var_fluct year_1 — 末位浮點差異，環境 numpy/BLAS 版本飄移，非本 PR 引入；5/22 handoff 已記錄此 3 項）。本 PR frontend only，**zero backend regression**。

### 為什麼沒有 frontend 自動化 regression test

frontend 目前**無測試框架**（package.json 只有 dev/build/preview，無 vitest/jest/testing-library，無 node_modules 測試依賴）。為 0.25d 小工引入整套 test harness 屬 scope creep。本次驗證走：

1. tsc 型別檢查 + vite production build 雙綠。
2. race 消除邏輯以 timeline 推導驗證（見 §5 code review）。

建議：若未來要補 frontend 測試基礎設施，另開 issue 一次導入 vitest + RTL，再回頭補 `useCostData` 的 race regression test（mock 兩筆不同回應時間的 fetch，斷言最後選的 dataset 勝出）。

---

## 5. Code review 採納

用 code-reviewer subagent 對 diff（vs main）review，結果 1 must + 1 should + 1 nice：

| 級別 | 議題 | 處置 |
|------|------|------|
| Must-fix | `reset()` 設 `controllerRef.current = null` 後，in-flight run 的 finally guard false → 疑 loading 殘留 | **判定非真 bug，不採納 hacky 修法**（見下） |
| Should-fix | `isAbortError` 補 `DOMException` 型別保護 | **採納** — 改 `(e instanceof DOMException \|\| e instanceof Error) && e.name === 'AbortError'` |
| Nice | `fn` 在 `useCallback` deps 假設文件化 | 略（fn 是 module-level 常數，reference 穩定；現況無問題） |

### Must-fix 為何判定非真 bug（timeline 推導）

`finally` 跳過 `setLoading(false)` 只有兩種情況，兩種都已妥善處理：

- **(a) 被更新的 run 取代**：`controllerRef.current` 指向更新的 controller。那筆新 run 自己 `setLoading(true)` 並會在自己 finally `setLoading(false)`。✓
- **(b) 被 `reset()` 取代**（`controllerRef.current = null`）：`reset()` 自身已 unconditionally `setLoading(false)`。✓

reviewer 擔心的「fnA resolve 之後、finally 之前 reset 插入」在 JS **不可能發生**：`await fn()` resolve 後到 finally 之間沒有 await，是同一個 microtask 連續執行，外部 callback（reset）無法在 microtask 中段插入。code-reviewer 自己在結論段也走回頭路確認「實際上沒有殘留」。

因此不採納其建議的「dead controller」hacky 寫法（多一次 allocation 又模糊語義），改為在 `finally` 加註解文件化兩種 guard-false 情況都安全，避免未來讀者 / reviewer 再誤判。

---

## 6. 下次接手指南

### 已完成（push 到 origin/claude/issue-WMOM-20260504-13-2026-05-23）

- `useCostData.useAsync` 三道防線消除 cost dashboard 切 dataset 的 stale-overwrites-fresh race。
- WMOM-20260504-13 issue done；ISSUES.md / STATUS.yaml 更新。

### 待辦（不阻塞）

- **PR 開啟**：sandbox 若無 gh / MCP 權限，branch 已 push，劉老師從 GitHub 介面開 PR。
- **手動驗收**（劉老師本機 dev）：開 `/admin/cost`，快速切 dataset selector 5 次（k13 ↔ farm:...），確認最終 forecast 對應最後一次選的，無殘影、無 console error。

### 建議下次 session 工作（依優先級）

1. **WMOM-20260519-01**（F1 超量退料 domain guard，0.5-1d）— 需與劉老師 walkthrough 決定 guard 策略（domain layer vs router vs UI），**不適合 solo session**，建議劉老師在場時做。
2. **M5 規劃** — 讀 `docs/product/ROADMAP.md` M5 章節（Knowledge/RAG + 現場 mobile UI）決定第一個 issue（RAG knowledge module skeleton or mobile UI）。
3. **WMOM-20260513-02** demo orchestrator + simulator 接合（2-3d 跨 session）— A10 e2e 接 simulator 一鍵 replay lifecycle，M5 demo 視覺化用。
4. **WMOM-20260504-12** frontend 長時間記憶體成長（0.5-1d，low priority，不阻塞 demo）。

### 環境備忘（給下次 sandbox session）

本 sandbox 初始無 Python / frontend 測試依賴。開工需先：

```bash
pip install pytest pytest-asyncio httpx sqlalchemy jinja2 pandas reportlab pytz scipy
# requirements.txt 只含 runtime（fastapi/uvicorn/websockets/pydantic/numpy/pymodbus），未含 test/db/pdf 依賴
npm install --prefix frontend   # frontend node_modules 不在 repo
```

（可考慮另開 issue 把 test 依賴補進 requirements-dev.txt + SessionStart hook，省去每次 sandbox 重裝。）
