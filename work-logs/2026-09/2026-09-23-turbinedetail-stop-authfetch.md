# 2026-09-23 — WMOM-20260923-09：`TurbineDetail.tsx` 停機鈕接線 + `OperatorControlCard` authFetch 補齊

## 認領理由

TODO.md「可立即接手」清單列 `WMOM-20260507-02` 尚餘 sub-task b~f，b 項（風機細節「停機」按鈕接
`POST /api/control/command`）估時 30 min、無設計歧義，選定接手。

Stack-aware 檢查（GitHub MCP 可用）：`list_pull_requests(state=open)` 回傳空陣列，無殘留 PR。

讀 `TurbineDetail.tsx` 準備接線時，發現右側「操作控制」卡片（`OperatorControlCard`）本身 4 處
`fetch` 呼叫（GET `/api/control/{id}/status` 輪詢 + POST `/api/control/command` + POST
`/api/control/curtail` ×2 call site）**全部裸 `fetch`，未帶 `Authorization` header**——與
WMOM-20260923-08（`FarmOverview.tsx` farm-trend）同款缺口，但風險更高：`command`/`curtail` 兩
端點皆掛 `require_role(SUPERVISOR)`（非僅 `require_authenticated`），`WMOM_AUTH_ENFORCE=true`
cutover 後這是**真正的操作控制面板整面失效**（啟動/停機/緊急停機/復位/定檢/限載全部指令都會
401/403 靜默失敗，無 `resp.ok` 檢查、無錯誤提示，現場工程師會誤以為指令送出成功）。

由於要接的 header 停機鈕本身就是呼叫同一支 `/api/control/command`，且與 `OperatorControlCard`
同一檔案、同一次編輯範圍，判定「wiring + authFetch 修復」合併為同一個 issue（新開
`WMOM-20260923-09`，因為不只是 sub-task b 原始範圍）一次做完是合理範圍，不算 scope creep。

進一步用 `grep -rn "await fetch(\|fetch(\`\${API_BASE}" frontend/components/*.tsx` 排除
`authFetch`/測試檔案，發現**還有 7 支元件**（`CostPage`/`EventComparisonView`/`FarmSelector`/
`FaultInjectionPanel`/`HistoryPage`/`SettingsPage`/`TrendChartPanel`）同樣裸 `fetch`，其中
`FarmSelector`（建立/切換 farm）、`FaultInjectionPanel`（故障注入/清除/測試計畫）、
`SettingsPage`（設定變更）多處是 `SUPERVISOR`/`ADMIN` 專屬寫入，風險同 `OperatorControlCard`。
範圍遠超單一 session（20+ 處呼叫、7 支檔案），故**本次只修 `TurbineDetail.tsx`**，另開
`WMOM-20260923-10` 登記剩餘範圍為 M6 auth cutover（`WMOM-20260716-05i`）前置阻塞項，供未來
session 逐檔認領（比照 `WMOM-20260507-02` 清單模式），並在 `docs/product/
WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表對照下標記「目前不成立」。

## Preflight

- backend baseline：`python -m pytest modules/{workflow,cost,reporting,knowledge,monitoring,auth}/tests/ tests/ -q`
  → `1103 passed, 7 skipped, 1 xfailed`（與 STATUS.yaml 記錄一致）。
- frontend baseline：`npx tsc --noEmit` 0 error；`npx vitest run` `1220 passed`（58 files）；
  build 用 `./node_modules/.bin/vite build`（本地鎖定 `vite@^6.2.0`，避免 `npx vite build`
  誤抓 registry 最新版導致 entry 解析失敗，見前次 session 環境備註）OK。
- Stack-aware 檢查：`mcp__github__list_pull_requests(state=open)` 回傳 `[]`，無殘留 PR/半成品需接續。
- 分支：環境注入的 `claude/inspiring-mccarthy-6uaebe`。

## Implement

**`frontend/components/TurbineDetail.tsx`**：

1. 新增 `import { authFetch } from '../services/authClient';`
2. `OperatorControlCard` 4 處 `fetch` → `authFetch`：
   - `refresh()`（GET `/api/control/{id}/status`，掛載 + 3s 輪詢）
   - `sendCmd()`（POST `/api/control/command`，6 個指令共用）
   - `setCurtail()`（POST `/api/control/curtail`，設定限載）
   - `clearCurtail()`（POST `/api/control/curtail`，解除限載）
3. 新增 `handleHeaderStop`（`TurbineDetail` 主元件層級）+ `headerStopPending` state：走
   `authFetch` POST `/api/control/command { command: 'stop' }`，`try/finally` 確保 loading
   state 一定恢復（維持與 `OperatorControlCard.sendCmd` 一致：不額外加 `resp.ok` 檢查或錯誤
   提示，因為那是既有卡片本身就沒有的行為，本次只補 auth header，不擴大行為變更範圍）。
4. PageHeader「停機」placeholder 按鈕接上 `onClick={handleHeaderStop}` +
   `loading={headerStopPending}`（沿用 `Btn` 既有 `loading` prop，比照 WMOM-20260923-07 匯出
   鈕模式）。

**設計決定**：header「停機」與 `OperatorControlCard` 的「■ 正常停機」是刻意重複入口（VA.jsx
設計交接書原文：「風機細節 | 限載/停機/安排檢查 | 同頁右側『操作控制』卡片有完整 6 指令（重複
入口）」），故直接各自呼叫同一支 endpoint 而非提升共用 state/回呼——header 按鈕本身不維護
「stop OK」訊息 pill，指令送出後 `OperatorControlCard` 的 3s 輪詢會在 ≤3 秒內自然反映最新狀態
（例如「手動停機」pill），不需要額外在 header 重複顯示成功/失敗訊息。

## Verify

- **7 個關鍵路徑逐一 mutation-verified**（每次改回舊邏輯 → 對應測試 fail → 還原 →
  `git diff --stat` 確認 production 檔案乾淨）：
  1. header 停機鈕拿掉 `onClick`/`loading` prop → 3 支新測試（點擊觸發 POST、loading 態
     disabled-恢復、auth header）全數 fail。
  2. `OperatorControlCard.refresh()` 退回裸 `fetch` → GET status auth header 測試 fail。
  3. `handleHeaderStop` 內部退回裸 `fetch` → header 停機鈕 auth header 測試 fail（與 #2 是
     不同程式碼路徑，各自獨立驗證，避免其中一處退化而另一處測試誤判通過）。
  4. `OperatorControlCard.sendCmd()` 退回裸 `fetch` → 指令(啟動) auth header 測試 fail。
  5. `OperatorControlCard.setCurtail()` 退回裸 `fetch` → 限載設定 auth header 測試 fail。
  6. `OperatorControlCard.clearCurtail()` 退回裸 `fetch` → 解除限載 auth header 測試 fail
     （原本沒有任何既有測試會因這處退化而 fail——既有的「點解除限載 → POST curtail null」測試
     只驗 method/body，不驗 headers，故對 headers 退化不敏感，屬於本次補的測試缺口）。
- 既有 GET status 斷言（原本精確比對單一參數 `expect(spy).toHaveBeenCalledWith(url)`）改用
  `expect.objectContaining` 比對第二參數，因為 `authFetch` 內部恆傳 `init`（至少 `{headers}`）
  給底層 `fetch`，即使未登入也是如此——原本的單參數精確比對在改用 `authFetch` 後必然 fail，
  已確認修正後仍能正確反映呼叫發生（配合下方新增的 auth header 專測驗證 header 內容本身）。
- **Full baseline（review 前）**：
  - `frontend/components/__tests__/TurbineDetail.test.tsx` 單檔：`75 passed`（68→75，+7 新測）。
  - backend 未動，重跑仍 `1103 passed, 7 skipped, 1 xfailed`。
  - frontend 全量：`npx tsc --noEmit` 0 error；`npx vitest run` `1220→1227 passed`（58 files
    不變）；build 用本地 `./node_modules/.bin/vite build` OK。

## 誠實回報：沒有自動化保護的部分

- **`OperatorControlCard`/header 停機鈕在瀏覽器內真實登入後的端到端行為**（`WMOM_AUTH_ENFORCE=
  true` + 真實 SUPERVISOR token + 真實後端）未經人工瀏覽器驗證，僅單元測試層級驗證
  `authFetch` 有被呼叫、header 內容正確；`WMOM_AUTH_ENFORCE` 目前預設 `false`，production
  行為本次未變（過渡期無 token 一樣放行，與改動前行為相同）。
- **`handleHeaderStop`/`OperatorControlCard.sendCmd` 皆無 `resp.ok`/錯誤處理**——這是修改前就
  存在的既有行為（未特別為本次新增），本次刻意不擴大範圍去補這塊，只補 auth header。若
  `WMOM-20260923-10` 後續要動這 7 支元件時，建議一併重新評估是否該加基本錯誤提示（現況是
  「指令失敗使用者不會知道」，隨著 cutover 逼近風險會提高）。
- **`WMOM-20260923-10`（其餘 7 支元件 authFetch 缺口）本次只登記未動**——已在 ISSUES.md 詳列
  逐檔逐行盤點結果 + 優先序建議，但未驗證該清單窮盡（僅用一次 grep pattern，可能有
  `XMLHttpRequest` 或其他 fetch 變體未被此 pattern 捕捉，未逐檔人工複查排除法）。

## Review

code-reviewer subagent 獨立跑（讀 `git diff` + 交叉核對 `control.py`/`authClient.ts`/`Btn.tsx`/
`farms.py`/`faults.py`/`config.py`）：

**verdict：0 must-fix / 1 should-fix / 1 nice-to-have → Approve**

- 🟡 **should-fix（已修）**：`ISSUES.md` 的 `WMOM-20260507-02` 父 issue checklist sub-task b 仍是
  `[ ]` 未勾選，與新開的 `WMOM-20260923-09`（已標 done）+ work-log 內容矛盾——已改 `[x]` 並補上
  完成摘要，比照 sub-task a 的收尾格式。
- 🟢 **nice-to-have（不採納，維持現狀）**：`handleHeaderStop`/`OperatorControlCard.sendCmd` 皆
  無 `resp.ok`/錯誤處理，reviewer 確認這是修改前既有行為（非本次引入的 regression），
  work-log「誠實回報」段落已誠實標註此限制並建議併入 `WMOM-20260923-10` 一併評估，本次不動。

reviewer 另外驗證：`handleHeaderStop` 的 `try/finally` 在成功/失敗兩種情況下都會正確重置
`headerStopPending`（無 bug）；`Btn` 的 `disabled={disabled || loading}` 確認 header 停機鈕真的
會在請求期間 disable；`authFetch` 的 header merge 邏輯不會覆蓋既有 `Content-Type`、GET 呼叫無
`init.headers` 時也能正確 no-op；新測試非 tautological（皆檢查 header 內容而非僅呼叫存在性）；
既有 GET status 斷言從單參數精確比對改 `objectContaining` 並非弱化——URL 仍被鎖住，且新增的
auth header 專測才是真正鎖住該端點 auth 行為的測試，兩者合計等同或強於原本單一斷言；獨立重新
`grep` 驗證 `WMOM-20260923-10` 列出的 7 支檔案行號與 role-gate 主張（`farms.py`/`faults.py`/
`config.py`）皆準確；5 支呼叫 `setAuthToken` 的新測試皆用 `try/finally` 包 `clearAuthToken()`，
無跨測試 `localStorage` 污染風險；安全性面向確認 `authFetch` 本身未被修改（只是新增呼叫點）、
header 格式與後端 `modules/auth/dependencies.py` 預期一致，無新增攻擊面。

## Wrap-up

- `ISSUES.md`：新增 `WMOM-20260923-09`（done）+ `WMOM-20260923-10`（open，M6 auth cutover
  前置阻塞，逐檔盤點）；`WMOM-20260507-02` sub-task b 打勾。
- `STATUS.yaml`：`issue_stats` 更新；`last_updated` 追加本 session 摘要；`next_milestone` 加入
  `WMOM-20260923-10` 為下次候選（標記 high priority，因為是 cutover 阻塞項）。
- `TODO.md`：更新「最後更新」摘要 + 「可立即接手」清單更新 `WMOM-20260507-02` 剩餘項（b 已完成，
  尚餘 c~f）+ 新增 `WMOM-20260923-10` 條目。
- 分支：`claude/inspiring-mccarthy-6uaebe`；commit 待 push（見下）。

**下次接手**：`WMOM-20260923-10`（7 支元件 authFetch 稽核，建議先做
`FaultInjectionPanel`/`SettingsPage`/`FarmSelector` 三支含 SUPERVISOR/ADMIN 寫入的，風險最高）；
`WMOM-20260507-02` 尚餘 c（限載 inline modal）/e（維護中心 + 新工單）/f（風場總覽 + 新報告）；
PR C（檢視情境掛載 app，需先寫 broker 子設計）；docker 阻塞項（`WMOM-20260509-F6` 需劉老師拍板
PostgreSQL）與 HTTPS 部署配置仍待決策，非本次可解。
