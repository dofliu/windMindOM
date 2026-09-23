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
