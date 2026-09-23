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

（待 Verify 完成後補上最終測試數與 review 結果）
