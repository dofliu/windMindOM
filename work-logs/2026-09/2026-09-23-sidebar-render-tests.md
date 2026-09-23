# 2026-09-23 — WMOM-20260923-05：`Sidebar.tsx` component render 測試

## 認領理由

前一 session（WMOM-20260923-04，`components/ui` primitives 測試補齊）逐檔評估 9 支 UI
primitive 檔案時，判定 `Sidebar.tsx` 範圍較大（mobile drawer transform + badge + backend
健康狀態 dot + lang/theme 切換 + `window.innerWidth` 多個 responsive 分支），適合另開一支
獨立處理，並在 work-log「下次接手」明確點名。本次接手。

其他候選（A2 Part 4 差異圖需先解決取樣點插值/分桶設計；PR C 需先寫 broker 子設計；docker
阻塞兩項 WMOM-20260716-06/WMOM-20260509-F6 本 sandbox 僅有 docker client 無 daemon 仍卡；
HTTPS 部署配置需先定部署目標非 autonomous 可決）皆非本次單 session 可無歧義完工範圍，故依
決策樹選「測試覆蓋擴大」類別的 `Sidebar.tsx`。

`Sidebar.tsx`（220px 主導覽，294 行）目前完全零 `__tests__`，且是全站唯一的主導覽入口，
邏輯分支包含：
- `NavButton` active/inactive 樣式 + badge（`item.badge > 0` 才顯示）
- `primary`/`secondary` 兩組導覽項目渲染 + secondary 為空時不顯示「工具」標題
- mobile drawer：`window.innerWidth < 768` 判定 + `mobileOpen` 控制 `transform`/`position`/
  `zIndex` + 點擊遮罩 `onMobileClose`
- 點擊 nav item 同時觸發 `onSelect` + `onMobileClose?.()`（desktop 下 `onMobileClose` 未傳，
  需確認 optional chaining 不會炸）
- backend 健康狀態 dot 顏色（healthy→`C.ok` / unhealthy→`C.warn`）+ 文字 zh/en
- lang toggle 按鈕文字（`zh`→顯示「EN」／`en`→顯示「中文」）
- theme toggle 按鈕（呼叫 `useTheme().toggle`，`aria-pressed`/圖示/文字隨 `mode` 變化）
- `footerExtra` 有值才渲染

## Preflight

- backend baseline：`python -m pytest modules/workflow/tests/ modules/cost/tests/
  modules/reporting/tests/ modules/knowledge/tests/ modules/monitoring/tests/
  modules/auth/tests/ tests/ -q` → `1103 passed, 7 skipped, 1 xfailed`（與 STATUS.yaml 記錄
  一致，全程未動 backend 檔案）。
- frontend baseline：`npx tsc --noEmit` 0 error；`npx vitest run` `1148 passed`（55 files）；
  `./node_modules/.bin/vite build` OK（沿用前次 session 記錄的 gotcha：不加參數的 `npx vite
  build` 可能解析到快取的全新版本而非 lockfile 版本，改用本地 binary）。
- Stack-aware 檢查（GitHub MCP 可用）：`mcp__github__list_pull_requests(state=open)` 回傳空
  陣列，無殘留待處理 PR。
- 分支：環境注入的 `claude/inspiring-mccarthy-opj1iv`。
- 附帶觀察：canonical routine 文件 `docs/routines/autonomous-daily-worker-prompt.md` 內文仍是
  v3（baseline 638/59、8-phase 流程無「自我測試」框架），已明顯落後於本次收到的 cron prompt
  （v4.1，baseline 1076/970，含 mutation 驗證/降級模式/決策樹擴充）。依本次 prompt 指示「以較新
  版本為準」，本 session 遵循收到的 v4.1 prompt 執行；已在下方「Wrap-up」提醒劉老師更新該文件
  避免下次 session 讀到過時版本。

## Implement

零 production 變更，純測試新增：

- **新增 `frontend/components/ui/__tests__/Sidebar.test.tsx`（新檔，23 tests）**：
  - **primary/secondary 導覽項目**：lang zh/en label 渲染；secondary 為空陣列時不顯示
    「工具」標題與任何 secondary 項目；`activeId` 對應項目有 `aria-current="page"`、
    其餘沒有；active 項目套用 `C.accentSoft` 背景 + `C.accent` 文字色，非 active 維持
    一般樣式；badge `>0` 才顯示數字、`badge=0`（falsy）不顯示；點擊項目呼叫 `onSelect`
    帶正確 id（含 desktop 下未傳 `onMobileClose` 時 optional chaining 不會炸）+ 同時
    呼叫 `onMobileClose`。
  - **backend 健康狀態**：`backendHealthy=true/false` 分別顯示「後端正常」/「後端離線」
    + dot 顏色 `C.ok`/`C.warn`；lang=en 時文字改英文。
  - **lang/theme 切換按鈕**：lang=zh 顯示「EN」按鈕、點擊呼叫 `onToggleLang`；lang=en
    顯示「中文」；主題按鈕預設 light（「夜」+ ☾ + `aria-pressed=false`），點擊後透過
    真實 `useTheme().toggle()` 切到 dark（「日」+ ☀ + `aria-pressed=true`）。
  - **footerExtra**：未傳不渲染額外節點；傳入時渲染在 footer 區塊內。
  - **mobile drawer（`window.innerWidth < 768`）**：`mobileOpen=false` 時
    `transform: translateX(-100%)` + `position: fixed`；`mobileOpen=true` 時
    `translateX(0)` 並渲染 `role="presentation"` 遮罩；`mobileOpen=false` 時不渲染
    遮罩；點擊遮罩呼叫 `onMobileClose`。
  - **desktop（`window.innerWidth >= 768`）**：`position: sticky`、`transform` 恆為
    `translateX(0)`（不受 `mobileOpen` 影響）；即使 `mobileOpen=true` 也不渲染遮罩
    （因 `showAsDrawer=false`）。
  - `window.innerWidth` 用 `Object.defineProperty` 在 render 前設定（元件在 render body
    內同步讀取一次，非 resize listener，故不需模擬 resize 事件）。

## Verify

- **5 個關鍵邏輯分支手動 mutation-verified**（逐一改 production、跑對應測試確認 fail、
  再還原，`git diff` 對 `Sidebar.tsx` 最終乾淨）：
  1. badge 顯示條件 `item.badge && item.badge > 0` 改成永遠 `true` → 「badge=0 視為
     falsy，不顯示」測試 fail。
  2. active 背景色 `active ? C.accentSoft : 'transparent'` 改成永遠 `'transparent'` →
     「active 項目套用 accent 顏色」測試 fail。
  3. mobile transform 條件 `showAsDrawer && !mobileOpen ? 'translateX(-100%)' :
     'translateX(0)'` 改成永遠 `'translateX(0)'` → 「mobileOpen=false 時 transform
     收起」測試 fail。
  4. 遮罩渲染條件 `showAsDrawer && mobileOpen` 改成只看 `mobileOpen`（拿掉 `showAsDrawer`
     檢查）→「desktop 下即使 mobileOpen=true 也不渲染遮罩」測試 fail。
  5. 主題按鈕 `aria-pressed={mode === 'dark'}` 改成永遠 `false` → 「點擊後切到 dark
     顯示…aria-pressed=true」測試 fail。
- **Full baseline（review 前）**：backend 未動，`1103 passed, 7 skipped, 1 xfailed`；
  frontend `npx tsc --noEmit` 0 error；`npx vitest run` `1148→1171 passed`（55→56
  files，+23 新測，零 regression）；`./node_modules/.bin/vite build` OK。

## Review

code-reviewer subagent 獨立跑（另外自行做 3 組 mutation spot-check、確認
`window.innerWidth` 判定方式與 production 一致、確認 production 檔案零變更）：

**verdict：1 must-fix / 2 should-fix / 1 nice-to-have → Needs revision → 已全數處理**

- 🔴 **must-fix（已修）**：本 work-log 原稿在「Preflight」後直接斷掉，缺 Implement/
  Verify/Review/Wrap-up/Commit 段落，且結尾自我指向一個不存在的「下方 Wrap-up」——本節
  即補齊（即本次重寫的完整版本）。
- 🟡 **should-fix #1（已修）**：主題切換測試會透過真實 `ThemeProvider.toggle()` 把
  `'dark'` 寫進真實 `localStorage['wmom.theme']`；vitest 預設 `isolate: true` 只做
  per-file 隔離，同檔案內排在其後的測試若渲染新 `ThemeProvider` 會讀到已污染的值。
  目前恰好無害（本檔後續測試不斷言依賴 theme 顏色的 style），但這是僥倖非設計，本檔又是
  本 repo 第一支真正呼叫 `toggle()` 的測試。修法：`afterEach` 加 `localStorage.clear()`，
  並在檔頭 docstring 補充說明原因；tsc/vitest 重跑仍 23 passed 不變。
- 🟡 **should-fix #2（已修）**：backend 健康狀態 dot 測試原用
  `container.querySelector('span[aria-hidden]')` 全域抓取，但 `Sidebar.tsx` 有兩個
  `aria-hidden` span（health dot + theme 按鈕圖示）——測試通過只是因為 dot 在 DOM 順序
  排在圖示前面，屬隱性耦合渲染順序而非語意。修法：改用 `getByText('後端正常'/'後端離線')`
  找到該文字所在的 row 元素，再從 row 內 `querySelector` 找 dot，不需碰 production code；
  重跑仍 23 passed。
- 🟢 **nice-to-have（不採納）**：`NavIcon` active/inactive 顏色分支（`color={active ?
  C.accent : C.sub}`）目前只驗證了 button 本身的 style，未驗證傳給 `NavIcon` 的 `color`
  prop 是否反應到 svg。reviewer 自己也標註「不影響本次 review 結論」，屬未來可選補項，
  本次不動。
- **Verify（review 後修復完）**：`npx vitest run components/ui/__tests__/Sidebar.test.tsx`
  仍 23 passed；`npx tsc --noEmit` 0 error；全套 `npx vitest run` 仍 `1171 passed`（56
  files）；backend 未動。

## Wrap-up

- `ISSUES.md`：新增 WMOM-20260923-05 done 條目；stats `done 111→112`、`total
  122→123`。
- `STATUS.yaml`：`issue_stats.done` 111→112；`last_updated` 追加本 session 摘要；
  `next_milestone` 維持既有候選（A2 Part 4 / PR C / docker 阻塞兩項 / HTTPS 部署）不變，
  本次是額外插入的測試覆蓋擴大項目，`components/ui/*.tsx` 系列（`StatusPill`/`Charts`/
  `Sidebar`）自此全數評估完畢。
- `TODO.md`：從「可立即接手」清單移除 `Sidebar.tsx` 這行候選項目，更新「最後更新」摘要。
- ⚠ **提醒劉老師**：`docs/routines/autonomous-daily-worker-prompt.md`（canonical routine
  文件）內文仍停在 v3（baseline backend 638 / frontend 59，且無「自我測試」/mutation
  驗證/降級模式框架），已明顯落後於本次 cron trigger 實際送進來的 prompt（v4.1，baseline
  1076/970）。建議下次找時間把 cron trigger 目前設定的完整 prompt 貼回這份文件，讓兩者
  重新同步，避免未來某次 session 意外讀到舊版並依過時 baseline 數字誤判 regression。
- 分支：環境注入的 `claude/inspiring-mccarthy-opj1iv`；純測試新增（+23 測，55→56
  files），零 production 變更；已 push；PR 待開（見下）。

**下次接手**：A2 Part 4（差異圖，需先解決多序列取樣點不完全對齊的插值/分桶問題）/ PR C
（檢視情境掛載 app，需先寫 broker 子設計）；`components/ui/*.tsx` 全 9 支檔案的測試評估
現已全數完成（`Btn`/`Card`/`Field`/`Stat`/`PageHeader`/`Logo` 判定 ROI 低不動、
`StatusPill`/`Charts`/`Sidebar` 已補測試）。M6 critical path 的 docker 阻塞兩項
（footprint pin / PostgreSQL row-lock）與 HTTPS 部署配置仍待部署環境/劉老師決策，非本次
可解。
