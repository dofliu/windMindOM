# 2026-05-24 WMOM-20260504-12 — Frontend realtime 記憶體成長：WS 殭屍重連洩漏 + 卡片 React.memo

> **Issue**：WMOM-20260504-12 — Frontend 長時間執行記憶體成長（觀察）
> **Branch**：`claude/upbeat-davinci-348BY`（autonomous daily worker, 5/24 20:00）
> **Goal**：根治 `useRealtimeData` WebSocket「殭屍重連」洩漏（記憶體成長真因），並對 overview 風機卡片加 `React.memo` 降低非資料因素 re-render 的 SVG 重繪。frontend only，低風險。

---

## 1. 為什麼今天做這個

5/23 handoff 推薦候選：WMOM-20260519-01（需劉老師 walkthrough，不適合 solo）/ M5 規劃（RAG，需架構決策 + 外部依賴）/ WMOM-20260513-02 demo orchestrator（2-3d 跨 session）/ **WMOM-20260504-12**（frontend 記憶體，0.5-1d，solo-friendly，不需設計決策）。

選 WMOM-20260504-12：符合「一日一項、solo、可驗證、零 regression」。**且進場 root-cause 後發現它其實藏了一個真 bug**（WS 殭屍重連），不只是 perf 觀察 → 從 priority tree step 1「known production bug」角度也站得住。

### 進場發現：issue 描述的元件名已過時

Issue 寫的 mitigation 目標 `MiniTrendChart` / `TurbineCard` 在 2026-05-07 UI 改版（WMOM-20260507-01）後已不存在。現況 overview 由 `FarmOverview.tsx` 內的 `TCard` / `CompactTile` / `TableView` 組成，sparkline 走自寫 SVG（`ui/Charts.tsx` 的 `MiniSparkline`），**非** Recharts。故 issue suspect #3（Recharts ResponsiveContainer leak）對 overview 不適用（只 HistoryPage 用 recharts）。

---

## 2. Root cause：WebSocket 殭屍重連（issue suspect #4）

`useRealtimeData` 永遠掛載在 App root，透過 WS 每隔數秒收 14 台風機資料 `setTurbines`。原本：

```ts
ws.onclose = () => {
  reconnectTimerRef.current = setTimeout(connect, 3000);   // 無條件重連
};
// cleanup:
return () => {
  if (wsRef.current) wsRef.current.close();                 // ← 觸發 onclose
  if (reconnectTimerRef.current) clearTimeout(...);         // ← 已先跑完，清不到下面排的
  clearInterval(pollInterval);
};
```

**洩漏時序**：

1. unmount → cleanup 呼叫 `ws.close()`（非同步）+ 清掉當下 timer。
2. cleanup 跑完後，`ws.close()` 觸發 `onclose` → 又排一條 `setTimeout(connect, 3000)`。這條 timer 沒人清。
3. 3 秒後 `connect()` 建新 WS（在已卸載的 effect 上）→ 新 WS 的 onclose 又排重連 → **殭屍 WebSocket 無限累積**，每條都在每次 push 呼叫 `setTurbines`。

React 18 Strict Mode dev 的 mount→unmount→mount 雙觸發會立刻引爆這個 loop——**這正是劉老師回報「記憶體不足、refresh 後就好」（dev 環境）的症狀**。

### 修法（`frontend/hooks/useRealtimeData.ts`）

- 加 `let disposed = false`；`connect` / `onopen` / `onmessage` / `onclose` / `onerror` / poll 全部先檢查 `disposed`。
- cleanup：設 `disposed = true` → 清 timer/interval → **先把 ws 四個 handler 設 null 再 `close()`**（雙保險：close() 引發的 onclose 不會重新排程）→ `wsRef.current = null`。
- initial REST fetch 加 `cancelled` guard，防卸載後 setState 警告。

---

## 3. 卡片 React.memo（issue suspect #1）

`FarmOverview` 的 `TCard` / `CompactTile` 原本無 memo。當父層因**非資料因素**re-render（檢視模式 cards/summary/table 切換、背景 `/api/farms` 健康輪詢每 30s 翻 state、modal 開關、nav badge 更新）時，14 張卡片連同各自的 SVG sparkline 全部重繪。

### 修法（`frontend/components/FarmOverview.tsx`）

- `TCard` / `CompactTile` 包 `React.memo` + 自訂 `turbineCardEqual` / `compactTileEqual`，只比對卡片實際渲染的欄位 + 新增 `lang` prop。
- `onClick`（`() => onSelectTurbine(t)`）與 `tr` 每次 render 都是新 reference，**刻意排除在比較外**：
  - **onClick stale 安全**：閉包捕捉的 turbine 物件即使過期，App 的 `liveTurbine`（App.tsx:143-146）以 `id` 反查最新資料，導航結果正確。已讀 App.tsx 確認。
  - **tr stale 安全**：`tr` 是 `lang` 的純函式，故只比 `lang`；同語言下舊 tr 輸出完全相同。`lang` 改變必重繪（`prev.lang !== next.lang → false`）。
  - **theme 安全**：`useTheme()` 走 context，context 變化強制子樹重繪，不受 memo 影響。

### 為什麼 memo 對「即時資料」不會誤跳過

live 風機每 tick 功率/風速都在變 → WS push 帶來新 turbine 物件 → areEqual 比到欄位不同 → 正常重繪（資料真的變了，重繪是對的）。memo 只在「父層 re-render 但 turbines array reference 未變」時生效（同一批物件 → 欄位/history reference 全等 → 跳過）。所以 `history` 用 reference 比較是正確的：沒有新 push 時 reference 穩定→跳過；有 push 時本來就該重繪。

---

## 4. 檔案異動

```
M frontend/hooks/useRealtimeData.ts    disposed guard + 解除 handler 再 close + cancelled guard
M frontend/components/FarmOverview.tsx  TCard/CompactTile React.memo + areEqual + lang prop
M ISSUES.md                             WMOM-20260504-12 in_progress + 今日進度
M STATUS.yaml                           last_updated / next_milestone
+ work-logs/2026-05/2026-05-24-frontend-realtime-memory-fix.md  本檔
```

---

## 5. Verify

- `npx tsc --noEmit` → **0 errors**
- `npx vite build` → **748 modules / ~3.4s / 0 errors**（chunk size warning 為既有 recharts，與本 PR 無關）
- Backend **完全未動**（frontend only）→ zero backend regression。
- 開工 baseline（參考，未動）：`pytest modules/{workflow,cost,reporting}/tests/` → 565 passed / 1 xfailed / **4 pre-existing 環境性 fail**：3 個 numpy float 末位 drift（test_cost_api monte_carlo_seed_42 / test_monte_carlo percentiles / test_var_fluct year_1，sandbox numpy 2.4.6 BLAS 飄移，5/22-5/23 handoff 已記錄）+ 1 個 flaky concurrency（`test_concurrent_dispatch_one_loses_when_stock_short`，單獨複跑即 pass）。皆非本 PR 引入。

### 為什麼沒有 frontend 自動化 regression test

frontend 仍無測試框架（無 vitest/jest）。延續 5/23 結論：不為單一修復引入整套 harness。WS 殭屍 race 以時序推導驗證；memo 安全性以 areEqual 欄位審查 + App.tsx 合約確認驗證。建議另開 issue 一次導入 vitest+RTL，再補：(a) WS unmount 不再重連的 fake-timer test；(b) memo areEqual 的 stale-render regression。

---

## 6. Code review 採納

用 code-reviewer subagent 對 diff（vs main）review：

| 級別 | 議題 | 處置 |
|------|------|------|
| Must-fix? | onClick stale closure 導航錯誤（待 App 合約確認） | **判定非 bug** — App.tsx:143-146 `liveTurbine` 以 id 反查，已於 docstring 文件化 |
| Should-fix | `onerror` 缺 `disposed` guard，與其他 handler 不一致 | **採納** — 加 `if (disposed) return` |
| Should-fix | `compactTileEqual` 未比 `turState` | **不採納** — CompactTile 不渲染 turState，加了只會造成多餘重繪（reviewer 自己也說非 current bug） |
| Nice | `history` reference 比較「使 memo 失效」 | **不採納** — reviewer 誤判情境；見 §3「為什麼 memo 對即時資料不會誤跳過」，reference 比較對 memo 目的是正確的 |

---

## 7. Issue 狀態：in_progress（非 done）

今日交付是**完整、已驗證的 bug-fix + 優化**，但 WMOM-20260504-12 的驗收標準是「24 小時連續執行記憶體成長 < 50%」，需劉老師本機長跑驗證才能 close。

- ✅ suspect #4（WS 殭屍重連）— 根治
- ✅ suspect #1（卡片 React.memo）— 完成
- ⏭️ suspect #2（useRealtimeData selective setState）— **不做**：已被卡片層 areEqual 取代（per-card 比較更直接，不需在 hook 再做一次 reference reuse）
- ⏭️ suspect #3（Recharts leak）— 不適用 overview（自寫 SVG）；若 HistoryPage 長跑有 leak 另開 issue
- ⏭️ suspect #5（升級/pin recharts）— 不在本 PR scope

### 劉老師驗收（本機 dev）

1. `python run.py` + `cd frontend && npm run dev`，開 overview。
2. dev console 確認：切頁面來回（觸發 Strict Mode unmount/remount）後，**不再**出現多條 `[WS] Connected` 累積；WS 連線數穩定為 1。
3. 連續跑數小時，記憶體成長 < 50% → 即可把 issue 標 done。

---

## 8. 下次接手指南

### 已完成（push 到 origin/claude/upbeat-davinci-348BY）

- `useRealtimeData` WS 生命週期正確性（disposed guard + handler 解除順序），根治 dev 記憶體成長真因。
- `FarmOverview` TCard/CompactTile React.memo。
- ISSUES.md / STATUS.yaml 更新；本 work-log。

### 建議下次 session 工作（依優先級）

1. **WMOM-20260519-01**（F1 超量退料 domain guard，0.5-1d）— 需劉老師 walkthrough 決定 guard 層級，不適合 solo。
2. **M5 規劃** — 讀 ROADMAP M5（Knowledge/RAG + 現場 mobile UI）。RAG 依賴 ChromaDB + RAG_Ultimate 策略檔/向量檔，建議先與劉老師對齊「先做 Knowledge skeleton 還是 mobile /field/ UI」再開第一個 issue。
3. **WMOM-20260513-02** demo orchestrator + simulator（2-3d 跨 session）。
4. **前端測試基礎設施**（新 issue 候選）— 導入 vitest + RTL，回補本次與 5/23 AbortController 的 regression test。

### 環境備忘（給下次 sandbox session）

sandbox 初始無 Python / frontend 測試依賴。開工需先：

```bash
pip install pytest pytest-asyncio httpx sqlalchemy jinja2 pandas reportlab pytz scipy
pip install -r requirements.txt   # fastapi/uvicorn/pydantic/numpy/pymodbus 等 runtime
npm install --prefix frontend      # frontend node_modules 不在 repo
```

（仍建議另開 issue 把 test 依賴補進 requirements-dev.txt + SessionStart hook，省去每次重裝。）
