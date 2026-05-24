# 2026-05-24 WMOM-20260524-01 — Frontend 測試基礎設施（vitest + RTL）+ 回補 race-condition regression test

> **Issue**：WMOM-20260524-01（本 session 新建，frontend 測試 infra）
> **Branch**：`claude/upbeat-davinci-NZNJt`（autonomous daily worker, 5/24 20:00）
> **Goal**：為前端導入 vitest + React Testing Library 測試框架，並回補 5/23 / 5/24 兩個近期 race-condition 修復的 regression test。frontend only，可在 sandbox 內完整驗證（自己跑 vitest）。

---

## 1. 為什麼今天做這個

優先級決策樹逐項評估：

1. **production bug / blocker**：無。
2. **504 backend 測試 regression**：無。開工 baseline `pytest modules/{workflow,cost,reporting}/tests/` → **566 passed / 1 xfailed / 3 failed**；3 個 fail 是已記錄的 sandbox numpy 2.4.6 BLAS 末位 drift（`test_monte_carlo_k13_seed_42` / `test_mc_percentiles_pinned` / `test_varfluct_year_1_pinned`），非 regression。
3. **handoff 推薦順序**：5/24 handoff 的候選 #1（WMOM-20260519-01）需劉老師 walkthrough、#2（M5 RAG）需架構決策 + 外部依賴、#3（demo orchestrator）2-3d 跨 session 易半成品；唯 **#4「前端測試基礎設施（vitest+RTL）」** 是 solo-friendly、單 session 可完整完工、且**可在 sandbox 內自我驗證**（純 UI feature 無法 browser 驗證，但測試框架本身跑 vitest 就是驗證）。

這條候選在 5/22 / 5/23 / 5/24 連三次 handoff 都被列為「新 issue 候選」——前端無框架導致每次 frontend fix 都裸奔上線。今天把它落地並順手鎖住兩個已修的 race bug。

---

## 2. 做了什麼

### 2.1 測試框架

- devDependencies：`vitest@^3` + `jsdom@^29` + `@testing-library/react@^16` + `@testing-library/dom`（React 19 對應 RTL 16）。
- `frontend/vitest.config.ts`：與 `vite.config.ts` **分離**（vitest 優先讀本檔，避免 build/test 設定互相干擾）。`environment: jsdom`（hook 需 document / WebSocket / timer）、`include: **/*.test.{ts,tsx}`、`setupFiles`、`restoreMocks: true`。
- `frontend/vitest.setup.ts`：`afterEach(cleanup)`，以 explicit import 寫（不依賴 `globals`，故不動 tsconfig 的 `types`）。
- `package.json` scripts：`test`（`vitest run`）+ `test:watch`（`vitest`）。

### 2.2 回補 WMOM-20260504-12（WS 殭屍重連）regression — `hooks/useRealtimeData.test.ts`

用自寫 `FakeWebSocket`（記錄 instances、可 `emitClose()` 模擬瀏覽器非同步觸發 onclose）+ `vi.useFakeTimers()`：

- **test 1（核心 regression）**：render → 確認建 1 條 WS → `unmount()` → 斷言 `close()` 被呼叫且 4 個 handler 都已設 null → 模擬 `emitClose()` + 推進 10s → **instances 仍為 1**（殭屍重連回歸時這裡會變 2+ 而 fail）。
- **test 2（反向保證）**：掛載中 `emitClose()` + 推進 3s → **instances 變 2**（證明 disposed guard 沒有把正常重連也誤殺）。

### 2.3 回補 WMOM-20260504-13（AbortController race）regression — `hooks/useCostData.test.ts`

`vi.mock('../services/costService')` 把 `costApi` 換成 4 個 `vi.fn()`，用可控 `deferred` 操縱回應時序：

- **test 1（stale-overwrite）**：連發 run(A) → run(B)（B 會 abort A 的 controller，斷言 `calls[0].signal.aborted === true`）→ 先 resolve B 再 resolve A → `data` 始終 === B（stale A 被 `signal.aborted` 早退丟棄）。
- **test 2（abort 不進 error）**：run(A) → run(B) → A reject `DOMException('AbortError')` → `error` 仍為 `null`。

---

## 3. 檔案異動

```
M frontend/package.json          + 4 devDeps + test/test:watch scripts
M frontend/package-lock.json      lockfile
+ frontend/vitest.config.ts        jsdom / include / setupFiles / restoreMocks
+ frontend/vitest.setup.ts         afterEach cleanup
+ frontend/hooks/useRealtimeData.test.ts   2 test（WS 生命週期）
+ frontend/hooks/useCostData.test.ts        2 test（useAsync race）
M ISSUES.md                        新建 WMOM-20260524-01（done）+ 統計 done 43→44 / total 57→58
M STATUS.yaml                      last_updated / next_milestone
+ work-logs/2026-05/2026-05-24-frontend-test-infra.md   本檔
```

> 注：`node_modules` / `dist` 已在 `frontend/.gitignore`，不入 git；`package.json` + `package-lock.json` 入 git，後續 session `npm install` 即得測試工具鏈。

---

## 4. Verify

- `npx vitest run` → **4 passed (2 files)** / ~1.4s。
- `npx tsc --noEmit` → **0 errors**（測試檔會被 tsc 檢查；已確認型別乾淨）。
- `npx vite build` → **748 modules / ~4.4s / 0 errors**，module 數與 baseline 完全相同 → 測試檔正確排除於 production bundle 外。
- Backend **完全未動**（frontend only）→ zero backend regression。

---

## 5. Code review 採納

用 code-reviewer subagent 對 staged diff review，4 must / 4 should / 1 nice：

| 級別 | 議題 | 處置 |
|------|------|------|
| **Must** | **useRealtimeData test 1 的 `emitClose()` 在 handler 已被設 null 之後才呼叫 → no-op，沒真的驗到「殭屍重連」** | **採納（核心修正）**：把 `FakeWebSocket.close()` 改成以 `setTimeout(onclose, 0)` **非同步**觸發 onclose（忠實還原瀏覽器行為，也正是 bug 的時序本質）。卸載後推進 timer 才放出 onclose；handler 已 null + disposed guard → 不重連。 |
| **Must** | useCostData 未斷言 `loading` 最終值，finally 的 controller-identity 判斷被破壞時抓不到 | **採納**：流程結束後加 `expect(forecast.loading).toBe(false)`。 |
| Must | test 2 應在 advance timer 後即斷言重連發生 | **已有** `expect(instances).toHaveLength(2)`，視為已覆蓋。 |
| Must | signal 接收與 prod 不符疑慮 | reviewer 自己複查後結論「正確、無問題」→ 不需改。 |
| Should | `vitest.config.ts` include pattern 過寬 | **不採納**：vitest v3 預設 `exclude` 已含 `node_modules`/`dist`，`**/*.test.{ts,tsx}` 安全且涵蓋未來 services/ 等目錄；改窄反而漏。 |
| Should | 另立 `tsconfig.test.json` 加 `vitest/globals` | **不採納（YAGNI）**：本 setup 以 explicit import 寫測試、未開 `globals`，主 tsconfig 已能乾淨 type-check（tsc 0 error 實證）。需要 globals 時再分離。 |
| Should | 加 coverage 依賴 / `test:coverage` script | **不採納（YAGNI）**：導入 infra 的最小可用集合；coverage 工具待真要看覆蓋率時再加，避免裝了不用的相依。 |
| Should | unmount 未包 act | **採納**：test 1 的 `unmount()` 包進 `act()`。 |
| Nice | `close()` 用 queueMicrotask 模擬非同步 | **採納其精神**：改用 `setTimeout(…,0)`（可被 fake timer 驅動，比 microtask 更好控）。 |

### 修法有效性驗證（mutation test）

不只「測試通過」，另以 mutation 確認**測試真的會在 bug 回歸時失敗**（避免 false-confidence）：

- 把 `useRealtimeData.ts` 還原成 **pre-fix 版本**（無 disposed flag、無 handler nulling、onclose 無條件重連）→ `useRealtimeData.test.ts` **FAIL**（onclose 未被解除）。✅
- 移除 `useCostData.ts` 的 `if (controller.signal.aborted) return` stale-drop guard → `useCostData.test.ts` **FAIL**（stale A 蓋掉 B）。✅
- 兩個 mutation 驗證後皆 `git checkout` 還原，prod hook 檔保持 0 異動（git status 確認）。

---

## 6. Issue 狀態：done

本 session 新建並完整完工 WMOM-20260524-01（infra + 2 個 regression 模組共 4 test 全綠 + 三項 verify 通過）。非半成品，直接標 done。

WMOM-20260504-12 維持 in_progress（待劉老師 24h 記憶體長跑驗收）；本次新增的 `useRealtimeData.test.ts` 已替它的「WS 不殭屍重連」修法上了自動化守門。

---

## 7. 下次接手指南

### 已完成（push 到 origin/claude/upbeat-davinci-NZNJt）

- vitest + jsdom + RTL 測試框架就位（config / setup / scripts）。
- 兩個 race-condition fix 的 regression test（WS 殭屍重連 / AbortController race）。
- ISSUES.md / STATUS.yaml 更新；本 work-log。

### 建議下次 session 工作（依優先級）

1. **WMOM-20260519-01**（F1 超量退料 domain guard）— 需劉老師 walkthrough，不適合 solo。
2. **M5 規劃**（Knowledge/RAG + 現場 mobile UI）— RAG 依賴 ChromaDB + RAG_Ultimate 策略檔/向量檔，建議先與劉老師對齊「先做 Knowledge skeleton 還是 mobile /field/ UI」。
3. **WMOM-20260513-02** demo orchestrator + simulator（2-3d 跨 session）。
4. **元件層測試擴充**（接續本 infra）— 用 `render` + mock 測 `FarmOverview` 的 memo 行為、`CostPage` 各 panel；量較大，可另開 sub-issue。

### 環境備忘（給下次 sandbox session）

sandbox 初始無 Python / frontend 測試依賴。開工需先：

```bash
pip install pytest pytest-asyncio httpx sqlalchemy jinja2 pandas reportlab pytz scipy
pip install -r requirements.txt
npm install --prefix frontend      # 現含 vitest/jsdom/RTL（本 session 加入）
```

跑 frontend 測試：`cd frontend && npm test`（= `vitest run`）。

（仍建議另開 issue 把 test 依賴補進 `requirements-dev.txt` + SessionStart hook，省每次重裝。）
