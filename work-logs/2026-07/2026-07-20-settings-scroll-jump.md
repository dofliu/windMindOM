# 2026-07-20 — 設定頁改任何選項就跳回頁頂（remount bug）｜WMOM-20260720-05

> Session 類型：使用者實測回報 UI bug（設定頁）
> 產出：本 PR（`Section` 元件移到 module scope，止住每次 re-render 重建整個表單）
> 對應 issue：WMOM-20260720-05

---

## 使用者回報

> 「在設定頁面，無論我選擇哪個選項，他會自動跳回頁頂 top，導致畫面無法停留在我選擇的那個地方。
> 比如我按一下電網控制修改成不一樣的、或是我修改不同風況…他都會跳回 top。」

## 根因（remount，與任何模式無關）

`SettingsPage.tsx` 的 `Section`（卡片式區塊）**定義在 render body 內**。React 以元件 `type`
（函式參照）diff：inline 定義每次 render 都是**新參照** → 視為不同型別 → 卸載舊 Section 子樹、
掛載新的 → 整個表單 DOM 被重建 → 瀏覽器捲動位置與輸入焦點重置回頁頂。

觸發時機：改任何設定（`setWindProfile` / `setCustomWind` / `setEditSpec` …）都 re-render；
另外每 5 秒的 wind/grid 狀態輪詢也 re-render。故「改任何選項就跳回 top」。

全 repo grep 無 `scrollTo`／`window.scroll`——確認不是顯式捲動，就是 remount。

## 做了什麼

- `Section` 移到 **module scope**（改用 `useTheme()` 自取主題色，不再靠 closure 抓 `C`）。
  identity 穩定 → 就地 reconcile → 不再重建 → 捲動/焦點保留。純機械式重構，渲染輸出不變。

## 驗證

- **tsc --noEmit** 全綠；既有 SettingsPage 17 測全過（渲染/API 契約不變）。
- **+1 回歸測試**：抓恆在的「資料源」heading 當哨兵 → 點風況 profile 觸發 re-render → 斷言
  `after` 與 `before` 為**同一 DOM 節點**（`toBe`）。
- **mutation 自驗**：把 `Section` 退回 inline（shadow module 版）→ 回歸測試轉紅（哨兵節點被
  remount 成新參照）→ 確認非假綠。
- 全前端 **930** passed、**vite build** 成功。

## 使用者另問的設計問題（未在本 PR 動，待對齊）

- 「情境模式下其餘功能可用還是失效？」+「情境模式下設定是否應無作用（不應產新資料）？」
  → 屬**模式語意的產品決策**（現況：`產生情境`＝simulation 後端＋仍在 free-run 生成；設定頁的
  `isSim` 依前端 AppSettings 而非實際 source_kind）。已在回覆整理現況＋建議，待劉老師定方向後再做
  「依實際來源 gate 設定/功能」。本 PR 只修與模式無關的 remount bug。

## 卡在哪 / 下次怎麼接手

- 本 PR：draft + `hold` 待 review → 移除 hold → 自動合。
- 待對齊：情境/檢視模式的功能與設定 gating（見上）；WMOM-20260720-04 live/OPC 後端硬化（排 M6）。
