# 2026-05-26 — Frontend 測試基礎設施（vitest + RTL）+ 兩 hook 回歸測試

> Autonomous daily worker session（2026-05-26 20:00 Asia/Taipei，雲端 sandbox）。
> Issue：**WMOM-20260526-01**（新開）。Branch：`claude/upbeat-davinci-aDiqG`。

---

## 1. 為什麼做這個

過去 3 個 session 的 wrap-up（5/19 / 5/22 / 5/23）都重複留同一句話：

> 「frontend 無測試框架故未加自動化 regression test（建議另開 issue 導入 vitest+RTL）」

最近兩個 frontend bug 修完後**完全沒有自動化測試守住**：

| Issue | 修了什麼 | 風險 |
|---|---|---|
| WMOM-20260504-13 | `useCostData` 的 `useAsync` 用 AbortController 防 stale-overwrites-fresh race | 未來重構 hook 很容易把 race guard 改回去而沒人發現 |
| WMOM-20260504-12 | `useRealtimeData` 的 WS 殭屍重連洩漏（disposed 旗標 + cleanup 解除 handler） | 同上，洩漏回歸無 CI 攔截 |

決策樹：M4 已 100%；WMOM-20260504-12 in_progress 等劉老師本機長跑驗收（非我可推進）；
其餘 open issue 多需劉老師 walkthrough / 設計決策（如 WMOM-20260519-01 退料 guard 的會計語意）。
測試基礎設施是**唯一無設計歧義、完全 autonomous、單 session 可完工、且被前面 3 次明確推薦**的工。

---

## 2. 完成內容

### 2.1 測試框架就位

- `frontend/package.json`：加 `"test": "vitest run"` + `"test:watch": "vitest"`；
  devDeps 加 `vitest@^3`、`jsdom`、`@testing-library/react@^16`、`@testing-library/dom`
  （版本 pin 進 `package-lock.json`）。
- `frontend/vitest.config.ts`（新）：**刻意獨立於 `vite.config.ts`**，讓 `vite build` 仍只讀
  vite.config.ts、production build 行為零變動。設定 `environment: 'jsdom'`、`globals: false`
  （各 test 檔顯式 `import { describe, it, expect } from 'vitest'`，tsconfig 不需加
  `vitest/globals` types 即可通過 `tsc --noEmit`）。

### 2.2 兩個 hook 的回歸測試（11 tests 全綠）

`frontend/hooks/__tests__/useCostData.test.ts`（6 tests）：
- happy path：run 成功寫進 data、清 loading/error
- **race（核心）**：deferred promise 讓較舊 run 後 resolve，驗證不蓋掉較新結果 + loading 結束
- AbortError 不寫進 error state
- 一般 Error 寫進 error state 並結束 loading
- reset 清空已完成 run 的 data/error
- **reset 中止 in-flight request（review SF#1 補）**：deferred，驗 signal.aborted 早退不寫 data

`frontend/hooks/__tests__/useRealtimeData.test.ts`（5 tests）：
- mount 建立單一 WS 連線
- 收到 message 後 payload 映射進 turbines（含 status enum 對映 + ping 已送）
- unmount 解除四個 handler 並 close（不留殭屍 handler）
- **disposed guard（核心）**：擷取 onclose 參考 → unmount → 觸發殭屍 onclose →
  advance timer 10s → 仍只有 1 條連線（不重連）
- 仍掛載時 onclose → 3 秒後重連一條新連線（正常重連路徑）

技法：`MockWebSocket` 替身（jsdom 無原生 WebSocket）記錄 instances/closeCalls、
手動觸發 handler；`vi.useFakeTimers()` 驅動 3s 重連 / 10s 不重連；`vi.stubGlobal` 注入
WebSocket + fetch。**踩雷**：`waitFor` 在 fake timer 下會卡死（內部輪詢無法 advance）→
改為「state 更新在 `act()` 內同步完成、直接斷言」。

---

## 3. Verify（zero regression）

- `npx vitest run` → **11 passed / 2 files**
- `npx tsc --noEmit` → **0 errors**（含新 test 檔 + vitest.config.ts）
- `npx vite build` → **748 modules / 0 errors / ~3.7s**（模組數與導入測試前一致 → 測試檔與設定未進 bundle，production 零影響）
- backend：**未動任何 backend 檔**。`python -m pytest modules/{workflow,cost,reporting}/tests/`
  維持已知 baseline（3 個 numpy pinned drift + flaky concurrency dispatch test 偶爾 fail，
  與 main 一致、與本 PR 無關 — 本 PR frontend-only）。

> 註：本 sandbox 為新 clone，需先 `pip install -r requirements.txt pytest pytest-asyncio
> httpx pandas reportlab openpyxl sqlalchemy aiosqlite`（requirements.txt 未列 test deps）。
> numpy 未 pin → 跑出 `numpy 2.4.x`，3 個 cost pinned 數字測試在最後一位 float drift（`!=` 嚴格
> 比對）。**這是既有環境問題（5/22 wrapup 已記為 pre-existing），非本 PR 造成。** 詳見 §5。

---

## 4. Code review

跑 `code-reviewer` subagent 對 staged diff：**0 must-fix / 4 should-fix / 4 nice-to-have**。
採納 4 個 should-fix 全部 + 3 個 nice-to-have（#5/#6/#7），跳過 #8（複合情境，兩條路徑已各自有測試）。

| # | 級別 | 內容 | 處置 |
|---|---|---|---|
| 1 | should | `reset` 測試名稱聲稱「中止 in-flight」但 reset 時已無 in-flight（abort 是 no-op，未測到該路徑）| **採納**：拆成兩個 test — 「reset 清空已完成 run」+ 新增「reset 中止 in-flight request（deferred，驗 signal.aborted 早退 + finally guard 不重設 loading）」|
| 2 | should | race 測試用 sync `act()` 啟動 async `run()` → RTL act warning | **採納**：改 `await act(async () => {...})` |
| 3 | should | race 測試結束未斷言 `loading === false`（finally guard 未守）| **採納**：補斷言 |
| 4 | should | reset 測試用 `waitFor` 等同步 state（誤用 + 慢）| **採納**：改 `act()` 內直接斷言，移除 `waitFor` import |
| 5 | nice | disposed guard 測試未跑真實 StrictMode 雙觸發 | **採納**：加註解說明是刻意取捨（語意等價）|
| 6 | nice | fetch mock `json: async () => []` 多一個 microtask tick | **採納**：改 `json: () => []` |
| 7 | nice | vitest.config `include` 全域；未來 component 測試需 setupFiles | **採納**：加 TODO 註解 |
| 8 | nice | 未覆蓋「race + fn 真的拋 AbortError」複合情境 | **不採納**：兩條路徑（signal.aborted / catch AbortError）已各自有 test，整體 guard 完整 |

採納後重跑：**vitest 11 passed**（useCostData 5→6）/ `tsc --noEmit` 0 errors。無 act warning。

---

## 5. 觀察到的環境/技術債（留給後續，非本 PR scope）

1. **requirements.txt 未列 test deps**：pytest / sqlalchemy / pandas / httpx / reportlab /
   openpyxl / aiosqlite 全靠手動補裝。建議補一個 `requirements-dev.txt` 或在
   requirements.txt 分段列出，讓新 sandbox / CI 一鍵就緒。
2. **numpy 等數值套件未 pin 版本**：`modules/cost` 的 pinned-number 測試用 `!=` 嚴格比對
   float，對 numpy patch 版本敏感（已觀察到最後一位 drift）。建議 (a) pin numpy 版本，或
   (b) 把 pinned 比對改 `math.isclose(rel_tol=1e-9)`。這會反覆讓不同環境的 CI 紅燈。
3. **concurrency dispatch 測試 flaky**：SQLite WAL 並發序列化測試偶爾 fail（單跑會過），
   PostgreSQL row-lock 真語意驗證見 WMOM-20260509-F6。

---

## 6. 下次 session 接手建議

測試基礎設施已就位，後續任何 frontend 工都應**附帶測試**。候選：
- **擴大覆蓋**：CostPage / FarmOverview 元件層測試（component test，現在 jsdom + RTL 已可寫）。
- **WMOM-20260519-01**（退料超量 domain guard）：仍需劉老師決定「退料是否以 actual_consumed
  為上限」的會計語意；決定後 backend 加 guard + negative-path test。
- **WMOM-20260513-02**（Demo Orchestrator UI 接 API）：M5 demo polish，2-3d。
- **技術債**：§5 的 requirements-dev.txt + numpy pin（小工，可順手清，能止住 CI 紅燈）。

---

## 7. 檔案異動清單

```
新增  frontend/vitest.config.ts
新增  frontend/hooks/__tests__/useCostData.test.ts
新增  frontend/hooks/__tests__/useRealtimeData.test.ts
改    frontend/package.json          （test script + 4 devDeps）
改    frontend/package-lock.json     （pin 版本）
新增  work-logs/2026-05/2026-05-26-frontend-test-infra.md（本檔）
改    ISSUES.md / STATUS.yaml
```
