# 2026-09-23 — WMOM-20260923-02：`FaultInjectionPanel` component render 測試

## 認領理由

TODO.md「可立即接手」清單 + 前次 work-log（2026-09-23-maintenancehub-render-tests.md）「下次接手」
點名 `FaultInjectionPanel.tsx`（555 行，`/admin` 故障模擬頁面元件）：同批 untested 大元件（與
`MaintenanceHub` 同批被 TODO.md 多筆 session 點名）中尚未處理的最後一支，先前零 component render
測試。屬 M5 測試覆蓋擴大範疇，autonomous-friendly、無設計歧義。

## Preflight

- backend baseline：`1103 passed, 7 skipped, 1 xfailed` — 與 TODO.md 記錄一致，無 regression。
- frontend baseline：`npx tsc --noEmit` 0 error；`npx vitest run` `1027 passed`（50 files）；
  `npx vite build` OK。與 TODO.md 記錄一致。
- Stack-aware 檢查（GitHub MCP 可用）：`list_pull_requests(state=open)` 回傳空陣列，無殘留 PR。
- 分支：環境注入的 `claude/inspiring-mccarthy-wpz70d`，已與 `origin/main` 同步（fast-forward，
  無需 merge）。

## 範圍

`FaultInjectionPanel.tsx` 比 `MaintenanceHub` 複雜：有 3 條 mount-time fetch effect
（scenarios / test-plans / active faults）+ 3s 輪詢 `refreshActive` + 2 個 POST action
（inject / clear all）+ 1 個 POST action（run test plan）+ message toast（3s/8s 自動清除）。
延續 `TrendChartPanel.test.tsx` / `SettingsPage.test.tsx` 的 fetch mock + fake timers 範式。

## Implement

新增 `frontend/components/__tests__/FaultInjectionPanel.test.tsx`（40 tests，含 review 後補的
1 測），零 production 變更。

- **fetch stub**：`installFetch(opts)` 依 URL substring + method 路由（scenarios/test-plans/
  active GET、inject/clear/run POST），未預期的組合直接 reject 避免靜默吞掉新呼叫。`runHandler`
  可覆寫（含回傳可手動 resolve 的 pending Promise，用於觀測 `isRunning` 中間態，比照
  `EventComparisonView.test.tsx`/`ScenarioPage.test.tsx` 既有範式）。
- **計時器**：全檔 `vi.useFakeTimers()`（元件無 `Date.now()` 依賴不受影響），精確控制 3s 輪詢
  `refreshActive` 與 3s/8s 訊息自動清除，避免依賴真實時間流逝拖慢測試（比照 `SettingsPage.test.tsx`）。
- **涵蓋範圍**：PageHeader 殼層、注入參數 Fields（場景/風機 Select、速率 Input）、
  `handleInject`/`handleClearAll`（POST body 正確性、成功/失敗、`refreshActive` 觸發、訊息自動
  清除）、活躍故障表（僅非空渲染、嚴重度%/階段+TRIP 後綴/告警 join 或「—」）、診斷測試計畫卡片
  （難度 label 對映含未知 id fallback、風機 chips 排序、scenarios_used 超過 4 個顯示 `+N`）、
  `handleRunPlan`（執行中互斥 disable、成功結果卡 Stat 區塊+DB 大小缺值 fallback+可選最終故障
  狀態表、失敗訊息）、3s 輪詢與 unmount 後 `clearInterval` 生效。

## Verify

- **手動 mutation-verified 6 個關鍵邏輯分支**（逐一改production、跑對應測試確認 fail、再還原，
  最終 `git diff` 對 production 檔案乾淨）：
  1. Inject 按鈕 `disabled={!selectedScenario}` → 改 `disabled={false}` → 對應測試 fail
  2. 風機選項數固定 14（`Array.from({length:14},...)`）→ 改 10 → 對應測試 fail
  3. 執行中其他計畫按鈕同時 disable（`disabled={isRunning || runningPlan !== null}`）→ 改
     `disabled={isRunning}` → 對應測試 fail
  4. DB 大小 fallback「—」（`?? '—'`）→ 移除 fallback → 對應測試 fail（改拋 `getElementError`）
  5. 訊息 3s 自動清除（`setTimeout(...,3000)`）→ 改 6000 → 對應測試在 advance 3000ms 時仍看得到
     訊息，fail
  6. 3s 輪詢間隔（`setInterval(refreshActive,3000)`）→ 改 6000 → 對應測試在 advance 3000ms 時
     call count 仍是 1，fail
- **Full baseline**：backend 未動，`1103 passed, 7 skipped, 1 xfailed` 不變；frontend
  `npx tsc --noEmit` 0 error；`npx vitest run` `1067 passed`（51 files，1027→1067，+40）；
  `npx vite build` OK（bundle hash 不變，純測試變更符合預期）。

## Review

code-reviewer subagent（獨立 mutation 複核 + 交叉比對 production）：**0 must-fix**，
**2 should-fix 全數採納**：

1. `final_fault_status` 的 `scenario_id ?? name_en` fallback 測試原本只用
   `scenario_id: undefined` 一種輸入——reviewer 把 production 邏輯反轉成
   `f.name_en ?? f.scenario_id` 重跑，39 測仍全過，證實只驗證了「有 fallback」而非「優先順序」。
   修法：新增 `scenario_id` 有明確值且與 `name_en` 不同的對照測試（`scenario_id:
   'bearing_overheat'` vs `name_en: 'Something Else'`），斷言優先顯示 `scenario_id`。已用
   相同反轉手法 mutation-verified 會 fail，再還原（production `git diff` 乾淨）。
2. `planCardByName` 等多處靠 `nameEl.parentElement!.parentElement!.parentElement`（或單層
   `.parentElement`）找 `Card` DOM 容器，對元件結構變動零抵抗力（隱性契約：依賴 JSX 巢狀層數
   而非顯式標記）。reviewer 明確標註「優先度低、可留到之後統一處理、不必卡此 PR」，且與既有
   `MaintenanceHub.test.tsx`/`TrendChartPanel.test.tsx` 等測試同款寫法（非本次新增問題）——
   **本次刻意不修**，留待日後若 `components/ui/Card.tsx` 等 primitives 加 `data-testid` 支援
   時，全 repo 統一改用 `getByTestId` 收斂（技術債已記錄於 ISSUES.md WMOM-20260923-02 與
   TODO.md）。

**3 nice-to-have 未採納**（皆屬「目前行為正確但未鎖 regression test」的次要覆蓋率缺口，留待未來
需要時再補，不影響本次合併）：
- `active_alarms` 多筆告警的 `join(' ')` 分隔符號目前只測 1 筆，mutate 成 `join(',')` 不會被抓到
- `active_alarms`/`storage_stats` 為 `undefined`（而非 `[]`/`{}`）兩種缺值變體未各自測過
- `callsTo()` 只依 URL substring 過濾，未篩 HTTP method（目前 3 個 mount 端點皆只有 GET 版本，
  不會誤判，但若未來同一 URL 也被其他 method 呼叫則會失準）

reviewer 也額外複核我原本的 6 項 mutation-test 結論一致，並額外驗證 `plan.turbines_affected
.sort()` 排序測試品質沒問題（附帶一提：該 `.sort()` 是既有 production 的原地 mutate 小地雷，
非本次引入，僅供未來動到該段程式碼時留意）。

Overall verdict：**Approve**。

## 誠實回報：沒有自動化保護的部分

- **`.parentElement` DOM 遍歷型 test scoping**（should-fix #2，刻意不修）：若未來
  `components/ui/Card.tsx` 或計畫卡的 JSX 巢狀層數改變，這些測試可能靜默 scope 到錯誤節點而非
  「大聲失敗」，尤其 `resultCard = screen.getByText(...).parentElement`（單層）涵蓋整個 Stat
  區塊 + 最終故障狀態表，範圍較寬。這只是讀原始碼層級推論出的風險，非本次測試涵蓋範圍。
- **`active_alarms` join 分隔符 / undefined 變體 / `storage_stats` undefined 變體**：目前行為
  正確但無 regression test 鎖住（見上方 nice-to-have）。
- **視覺層**（recharts 渲染、CSS 顏色/佈局）一律未驗證，僅涵蓋文字內容 / DOM 結構 / callback
  觸發，符合本系列既有測試範式的已知限制（jsdom 無法驗證真實渲染像素）。

## Wrap-up

- ISSUES.md：stats `done 108→109`、`total 119→120`；新增 WMOM-20260923-02 done 條目 + 更新
  「最後更新」blurb。
- STATUS.yaml：`issue_stats.done` 108→109；`last_updated` 追加本 session 摘要。
- TODO.md：「可立即接手」清單移除 `FaultInjectionPanel.tsx`（同批 untested 大元件兩支皆已處理
  完畢），更新「最後更新」摘要。
- 分支：`claude/inspiring-mccarthy-wpz70d`；commit 已 push（含 review 後的 should-fix 追加）。

**下次接手**：ui primitives（`components/ui/*.tsx`）目前零 `__tests__`，尚未評估是否需要；
`.parentElement` DOM 遍歷 scoping 技術債（見上方 Review §2）可留待有需要時統一改用
`data-testid`。M6 critical path（footprint CPU-torch pin / PostgreSQL row-lock 皆卡 docker
daemon；HTTPS 部署配置需先定部署目標）與情境比較分析 A2 Part 2 剩餘（相對時間對齊時序疊圖）/
PR C（檢視情境掛載 app，需先寫 broker 子設計）仍是下個 session 的候選。
