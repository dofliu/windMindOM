# 2026-09-26 — WMOM-20260926-05：`ScenarioMountBanner.tsx` component render 測試

- **Issue**: WMOM-20260926-05（第八個 autonomous session）
- **Branch**: `claude/inspiring-mccarthy-fwemn9`
- **Milestone**: 工程基礎設施 / 測試覆蓋擴大（EPIC-M5 測試覆蓋擴大系列延續）

## Preflight

- `git checkout main && git pull` — 乾淨、無殘留分支（無 GitHub MCP 降級模式不適用，本次
  MCP 可用；`mcp__github__list_pull_requests` 確認 open PR 為空，非 stack-aware 阻塞）。
- backend baseline：`1274 passed, 7 skipped, 1 xfailed`（與預期一致，零 regression）。
- frontend baseline：`npx tsc --noEmit` 0 error、`npx vitest run` **1461 passed**（69
  files，與預期一致）、`npx vite build` OK。
- `docs/routines/autonomous-daily-worker-prompt.md` 仍是 v3（baseline 638/59），落後於
  本次 cron 送入的 v4.1（baseline 1076/970，本 session 實測 backend 為 1274/frontend
  1461，已比 v4.1 記載的數字又往前進，純粹是 doc 落後未同步，不影響本次工作）；已連續多個
  session 提醒，本次不重複展開修，僅再次記錄提醒劉老師找時間同步。

## 背景

上個 session（WMOM-20260926-04）盤點 `frontend/components/**/*.tsx` 測試覆蓋率時，把
`components/ui/` 剩餘 7 支零測試 primitive 列為下次候選（`Btn`/`Card`/`Field`/`Logo`/
`PageHeader`/`Stat`/`ScenarioMountBanner`），並建議優先評估 `ScenarioMountBanner`（PR C
Phase 1 新增，較新、較可能有值得鎖的分支邏輯）。

本 session 開工前先讀過 `ScenarioMountBanner.tsx`（83 行，PR C Phase 1／
`WMOM-20260926-03` 新增）確認它不是純展示 wrapper：

- `tone={error ? 'warn' : 'accent'}` — 依 `error` 決定 `Card` 警示色調
- `loading && !error` — loading 文案只在無 error 時顯示（避免與 error 訊息並存造成混淆）
- `error` 非 null 時額外渲染 `role="alert"` 錯誤說明區塊
- `lang` 切換 en/zh 兩種文案（`aria-label`、按鈕文字、error/loading 說明皆有獨立字串）
- `onExit` callback 接到 `Btn` 的 `onClick`

用 `grep -rl "ScenarioMountBanner"` 確認消費端只有 `FarmOverview.tsx`/`TurbineDetail.tsx`
兩處（透過 `ScenarioMountContext` 分發 `loading`/`error`），且 `grep` 這兩支頁面既有
`__tests__` 檔案找不到任何 `ScenarioMountBanner`/`error`/`Loading…`/`Failed to load this
scenario` 字樣命中——確認 `loading`/`error` 這兩條分支**完全沒有被任何既有測試涵蓋**
（host page 測試多半只驗證「情境掛載時顯示 banner」的 happy path，未餵過 loading/error
props 給 context），是真正的覆蓋缺口而非為了補而補。

其餘 6 支 primitive（`Btn`/`Card`/`Field`/`Logo`/`PageHeader`/`Stat`）維持上次評估結論：
純展示、已被全站頁面測試間接涵蓋渲染路徑，本次不重複評估。

## 本 session 做的事

新增 `frontend/components/ui/__tests__/ScenarioMountBanner.test.tsx`（新檔，15 tests，
code review 後補 1 則變 16 tests），
**未修改元件本體任何一行**（`git diff` 對 `ScenarioMountBanner.tsx` 為空）。延續
`StatusPill.test.tsx`/`Charts.test.tsx` 既有 render 測試範式（`ThemeProvider` 包裹 +
jest-dom matcher + `afterEach cleanup`）。

涵蓋：

1. **基本顯示**：`role="status"` 容器 + `aria-label` 含情境名稱；情境名稱以 `<strong>`
   顯示；`(read-only)`/`（唯讀）` 說明文字。
2. **lang 切換**：預設 `zh`；`lang="en"` 時所有文案（狀態列、退出按鈕、loading、error）
   改用英文版本，中文版本不殘留。
3. **loading 分支**：`loading=true` 且無 `error` 時顯示 `Loading…`/`載入中…`；
   `loading=false`（預設）時不顯示。
4. **error 分支**：`error` 非 null 時——① `Card` `tone` 變成 `warn`（斷言 inline style
   套用 `C.warnSoft`/`C.warn`，比照 `StatusPill.test.tsx` 的 `hexToRgb` 手法）；②
   額外渲染 `role="alert"` 錯誤說明區塊；③ `loading` 即使同時為 `true` 也不顯示
   `Loading…`（`loading && !error` 短路，避免 loading 與 error 文案同時出現造成混淆）。
5. **error=null（預設）**：`Card` `tone` 為 `accent`（斷言 `C.accentSoft`/`C.accent`），
   無 `role="alert"` 元素。
6. **onExit 接線**：點擊退出按鈕觸發 `onExit`，且不論 `lang` 為何都能透過同一個
   `aria-label`（en/zh 對應字串）找到按鈕並觸發。

## Mutation-verify 記錄

逐項「改回舊邏輯 → 確認新測真的會 fail → 再還原」，用 `/tmp/wom-mutation-backup/` 備份
（新檔尚未 commit 前用 `cp` 而非 `git checkout`）：

1. 把 `tone={error ? 'warn' : 'accent'}` 改成恆為 `'accent'` → error 分支的 tone 斷言
   如預期 fail（其餘測試仍過）。
2. 把 `loading && !error` 改成單純 `loading` → 「error 且 loading 同時為 true 時不顯示
   Loading…」測試如預期 fail。
3. 把 `{error && (...)}` 的 `role="alert"` 區塊拿掉（改成恆不渲染）→ error 說明區塊存在
   性斷言如預期 fail。
4. 把 `tr()` 內 `lang === 'zh'` 改成恆真 → `lang="en"` 情境下所有文案斷言（狀態列/按鈕/
   loading/error）皆如預期 fail（一次性驗證整組 lang 分支，非逐字串拆測）。
5. 把 `onClick={onExit}` 拿掉 → onExit 接線測試如預期 fail。

每次還原後重跑本測試檔確認回到 15 passed 全綠再進行下一項。

## code-reviewer subagent review

**Approve，0 must-fix，0 should-fix，2 nice-to-have，1 個 nice-to-have 已採納**：

1. 🟢（已採納）：`error?: string | null` 型別上允許空字串 `''`，元件的
   `error ? 'warn' : 'accent'` 與 `{error && (...)}` 皆把空字串當 falsy 處理、等同
   `null`，原 15 測只餵過 `null`/非空字串，沒鎖住這個冷門邊界（若上游未來把「有錯誤但
   訊息未帶回」表示成 `error: ''` 而非 `null`，會靜默退回無錯誤 UI，恰是元件自己
   docstring 點名的風險）。新增 1 則測試（`error=''` 時 tone 仍 accent、無 alert 區塊）
   明確鎖住此為既有/接受行為，而非遺漏（15→16 tests）。
2. 🟢（未採納）：「error=null 時 tone 為 accent + 無 alert 區塊」單一測試同時斷言兩件事，
   純風格建議、因果關聯合理，不影響正確性，維持現狀。

reviewer 獨立核對：`container.querySelector('[role="status"] > div')` 精準命中 `Card`
的 div（`Card.tsx` 只 render 一層 div，是 `role="status"` 的唯一直接子元素，非內層
flex-row div 或 alert div）；`hexToRgb` 手法對 `Card` 的 `background`/`border` shorthand
屬性同樣適用（jsdom cssstyle 會正規化內嵌 hex）；`getByText('(唯讀)')`/`getByText('測試
情境A')` 精準命中對應節點、無跨檔案 theme/localStorage 污染。並實際重跑本測試檔（獨立 +
與其餘 `components/ui/__tests__` 一起跑）確認 15/15（review 當下版本）全過、無 console
warning/act() error。

## 自我測試

- backend：未動，`1274 passed, 7 skipped, 1 xfailed` 不變。
- frontend：`npx tsc --noEmit`（0 error）+ `npx vitest run`（**1461 → 1477 passed**，
  69→70 files，+16，零 regression，含 code review 後補的 1 則）+ `npx vite build`（OK）。

## 誠實揭露

- 本次是純測試新增，元件本體零修改，無新的生產邏輯風險。
- `FarmOverview.tsx`/`TurbineDetail.tsx` 實際掛載 `ScenarioMountBanner` 時如何把
  `ScenarioMountContext` 的 `loading`/`error` 傳進來，仍只由這兩支頁面自己的既有測試
  （happy path 為主）間接涵蓋，本次新增的是 `ScenarioMountBanner` 元件自身的 props →
  渲染結果直接測試，不覆蓋「context 是否正確把 fetch 狀態往下傳」這條路徑——若之後
  `useScenarioMountData`/`ScenarioMountContext` 的傳遞邏輯有 regression，仍需靠
  `contexts/__tests__/ScenarioMountContext.test.tsx`（既有）或 host page 測試才抓得到，
  本次新增測試單純鎖住 banner 元件本身「收到 props 之後畫什麼」。

## 下次接手

`components/ui/` 剩餘 6 支（`Btn`/`Card`/`Field`/`Logo`/`PageHeader`/`Stat`）維持既有
評估結論（純展示、ROI 低，暫不主動補測試，除非之後發現獨立分支邏輯）。M6 critical path
剩餘項（PostgreSQL row-lock 需 docker、HTTPS 部署配置需先定部署目標）與物理模型強化
（WMOM-20260505-23~28）維持既有阻塞狀態；`WMOM-20260504-11`（event-driven cost
ledger，M4 增強）仍 open 但屬 2-3 工作天的多日新功能且涉及新 schema 設計，非單 session
可完工、無設計歧義的候選，本次評估後略過，留待劉老師決定是否排入或需要先寫 decision log。
⚠ `docs/routines/autonomous-daily-worker-prompt.md` 仍停留 v3，已連續多個 session
提醒，建議劉老師找時間同步 cron trigger 設定內文（v4.1）回 repo。
