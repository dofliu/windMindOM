# 2026-05-31 — 前端 component render 測試基礎建設 + UI primitive 覆蓋

> Autonomous daily worker session（2026-05-31 20:00 Asia/Taipei，雲端 sandbox）。
> Issue：**WMOM-20260531-01**（新開）。Branch：`claude/gifted-maxwell-0LIq0`。

---

## 1. 為什麼做這個

Preflight baseline 完全綠（backend `pytest modules/{workflow,cost,reporting}/tests/`
→ **570 passed / 1 xfailed**；frontend vitest **59 passed**；tsc 0、vite build OK；
無 blocker、無 regression）—— 決策樹第 1、2 條皆不觸發。

5/26→5/29 連續四個 session 建立「擴大 frontend 測試覆蓋」momentum，但截至昨日全是**純函式 /
hook 層**（statusUtils / formatters / mockUsers / useCostData / useRealtimeData）。5/28、5/29
handoff 反覆點名下一階段是「**真 component render 測試**」，但卡在前置：需補
`@testing-library/jest-dom` + vitest `setupFiles`，被標為「脆弱性較高、建議獨立 session」。

本 session 就是那個獨立 session：**把 component render 測試的基礎建設一次立起來，並用最低
脆弱度的 `components/ui/*` primitive library 當第一批驗證對象**。屬 ISSUES.md 頂部「🎯 未來
大目標 → 跨 milestone 持續工作 → 測試覆蓋持續擴大（component render 測試）」🔵 autonomous。

### 為何選 `components/ui/*` 當第一批

- **零資料依賴**：Btn / StatusPill / Stat / Card / PageHeader / Field 全是 props-in →
  DOM-out 的純展示元件，不碰 fetch / hook / service，render 測試最穩、不脆。
- **全 app 最高複用**：這層是 dispatch / approve / cost / reporting / workflow 各頁的共用骨架，
  一旦行為回歸（onClick 不觸發、disabled 失效、受控 onChange 契約被改成傳 event）會大面積污染。
- **此前零測試**：UI primitive 與 StatusPill 的三個 status→tone 純函式（turbine / workOrder /
  technician）完全沒有自動化守護。
- **先立 pattern**：之後測 CostPage / FarmOverview 等重元件可直接複用本 session 建的
  `renderWithTheme` helper 與 setup，降低後續 session 起步成本。

---

## 2. 完成內容

### 基礎建設（3 檔）

- **`frontend/test/setup.ts`**（新）：vitest `setupFiles`。
  - `import '@testing-library/jest-dom/vitest'` → 注入 `toBeInTheDocument` / `toHaveAttribute`
    / `toBeDisabled` 等 DOM matcher + 觸發型別 augmentation（tsc 認得）。
  - **手動 `afterEach(cleanup)`**：本專案刻意 `globals: false`，RTL 的自動 unmount 只在
    `globals: true` 時自動掛 afterEach；不補的話跨 test render 殘留 → getByRole 命中多個元素
    報「Found multiple elements」（實作過程真的撞到，補上後解決）。
- **`frontend/test/renderWithTheme.tsx`**（新）：包 `<ThemeProvider>` 再 render 的 helper。
  `components/ui/*` 全呼叫 `useTheme()`，不套 provider 直接 render 會 throw；統一走此 helper
  避免每檔重複包。
- **`frontend/vitest.config.ts`**（改）：加 `setupFiles: ['./test/setup.ts']`，移除舊 TODO 註解。
- **`package.json` / `package-lock.json`**：加 `@testing-library/jest-dom@^6.9.1`（`react` +
  `dom` 早已在 devDeps）。

### 測試檔（4 檔，+38 tests）

- **`components/ui/__tests__/Btn.test.tsx`**（8）：render 為 `<button>` / type 預設 button 可改
  submit / 點擊觸發 onClick / **disabled 與 loading 皆 disable 且不觸發 onClick** / ariaLabel
  → accessible name / ariaPressed toggle / title 透傳。
- **`components/ui/__tests__/StatusPill.test.tsx`**（15）：render children / title / **colorBg+colorFg
  自訂色蓋過 tone**（用 rgb 驗自訂行為、不綁 theme 預設色）+ 三個 tone 純函式 `it.each` 窮舉
  已知 status + **未知值走 default 分支**（switch 無漏接、不回 undefined）。
- **`components/ui/__tests__/layout.test.tsx`**（7）：Stat（label/value、unit+hint 缺省不顯示）/
  Card（children、onClick、className 透傳）/ PageHeader（**title 渲染為 h1**、sub/breadcrumb/actions
  缺省不顯示帶入才顯示）。
- **`components/ui/__tests__/Field.test.tsx`**（8）：Field（label/children/hint）/ Input（受控 value、
  undefined→空字串、**onChange 收到的是新值字串而非 event**、disabled）/ Select（option 全 render、
  受控 value、切換帶新 value）/ ReadOnlyBox。

---

## 3. Verify（zero regression）

| 項目 | 改前 | 改後 |
|---|---|---|
| vitest | 59 passed（5 檔） | **99 passed（9 檔：+40 component/primitive tests，含 code review 補的 2 個）** |
| `tsc --noEmit` | 0 errors | **0 errors**（jest-dom 型別 augmentation 經 setup 生效） |
| `vite build` | 918.27 kB | **918.24 kB**（test 不進 bundle；唯一 source 改動是 Field.tsx Select option 簡化，省 ~30 bytes） |
| backend `pytest modules/{workflow,cost,reporting}/tests/` | 570 / 1 xfailed | **570 / 1 xfailed**（未動 backend） |

---

## 4. Code review

跑 `code-reviewer` subagent 對 staged diff：**1 must / 4 should / 3 nice，Needs revision → 處置後可 approve**。處置：

| # | 級別 | 內容 | 處置 |
|---|---|---|---|
| 1 | **must** | `renderWithTheme` 用 `{ wrapper, ...options }`，呼叫端誤傳 `options.wrapper` 會靜默蓋掉 ThemeProvider → useTheme throw | **採納**：改 `{ ...options, wrapper }`（wrapper 放最後恆存在）+ 併入 nice#6 把 Wrapper 提到模組層級（避免 rerender 重建參照） |
| 2 | should | workOrderStatusTone 用虛構的 `'ON_HOLD'` 當 default 樣本，與真實狀態脫節 | **採納**：改用 `'CANCELLED'`（statusUtils.ts 真實存在但 switch 未列 case 的 WorkOrderStatus）+ 註解說明，將來給專屬 tone 會被迫更新 |
| 3 | should | 缺 Field+Input 組合的隱式 label 關聯（無障礙）測試 | **採納**：補一個 `<Field label><Input ariaLabel/></Field>` → `getByLabelText` 命中 input 的 test |
| 4 | should | `SelectOption.label: ReactNode` 但 render 是 `typeof==='string'?...:''`，傳 JSX 會靜默成空字串（假綠 footgun） | **採納（option 1，最乾淨）**：查證全 app 4 個 Select 呼叫端皆傳 string → 把型別收成 `label: string` + render 簡化為 `{o.label}`，型別層擋住非字串 |
| 5 | should | Btn loading 只驗 disabled，未鎖 loading 視覺回饋 | **採納（調整版）**：加 test 鎖「loading 時仍顯示 children 文字」（比斷言 spinner 不存在更有意義）+ 註解標明日後加 spinner 需更新 |
| 6 | nice | Wrapper 每次呼叫重建參照 | **採納**：併入 #1，提模組層級 |
| 7 | nice | setup 未清 localStorage 跨 test 污染（ThemeProvider 讀寫 `wmom.theme`） | **採納**：`afterEach` 加 `localStorage.clear()` 防禦 |
| 8 | nice | turbineStatusTone 字面量未與後端 canonical turbine status 共用常數 | **不採納（記錄）**：需在 shared 層建 `TURBINE_STATUS` 常數並前後端共用，屬 source/shared 重構、超出本 test PR scope，留後續 issue |

採納後重跑：vitest 97→**99 passed**（+2：Field+Input 組合、Btn loading children）、tsc 0、vite build 918.24 kB；backend 未動 zero regression。

---

## 5. 下次 session 接手建議

- 基礎建設已就位：之後任何 component render 測試直接 `import { renderWithTheme } from '../../../test/renderWithTheme'`
  + jest-dom matcher 即可，不需再動 vitest.config / 裝套件。
- **下一階段重元件**：CostPage / FarmOverview / workflow Panel。注意這些需 mock hook / service
  （useCostData / costService / fetch），脆弱性比 primitive 高，建議一次只攻一個元件 + 集中 mock。
  CostPage 的 `fmtMoney`/`fmtPct`/`fmtKwh`（CostPage.tsx）未 export，若要單測 formatter 需先抽出。
- 其他 open 候選（多需劉老師）：WMOM-20260519-01（退料 guard 會計語意）/ WMOM-20260513-02
  demo orchestrator product decision / WMOM-20260509-F6（PostgreSQL，M6、需 docker）。

---

## 6. 檔案異動清單

```
新  frontend/test/setup.ts                                （jest-dom matcher + afterEach cleanup）
新  frontend/test/renderWithTheme.tsx                     （ThemeProvider render helper）
新  frontend/components/ui/__tests__/Btn.test.tsx         （8 tests）
新  frontend/components/ui/__tests__/StatusPill.test.tsx  （15 tests：render + 3 tone 純函式）
新  frontend/components/ui/__tests__/layout.test.tsx      （7 tests：Stat/Card/PageHeader）
新  frontend/components/ui/__tests__/Field.test.tsx       （8 tests：Field/Input/Select/ReadOnlyBox）
改  frontend/vitest.config.ts                             （加 setupFiles）
改  frontend/components/ui/Field.tsx                       （code review SF#4：SelectOption.label ReactNode→string + render 簡化）
改  frontend/package.json / package-lock.json             （+@testing-library/jest-dom）
改  work-logs/2026-05/2026-05-31-ui-component-render-tests.md（本檔）
改  ISSUES.md / STATUS.yaml
```
