# 2026-09-23 — WMOM-20260923-04：`components/ui` primitives（`StatusPill`/`Charts`）測試補齊

## 認領理由

TODO.md「可立即接手」清單標記「ui primitives（`components/ui/*.tsx`）目前零 `__tests__`，尚未
評估是否需要」——本次先做評估：9 支檔案（`Btn`/`Card`/`Charts`/`Field`/`Logo`/`PageHeader`/
`Sidebar`/`Stat`/`StatusPill`，共 1220 行），逐檔讀過。

- `Btn`/`Card`/`Field`/`Stat`/`PageHeader`：純展示型 wrapper，條件邏輯僅止於「有 prop 才顯示」
  等單層 truthy 分支，且已被全站幾十個既有 page-level component 測試以真實元件（非 mock）間接
  渲染覆蓋，直接補獨立測試 ROI 低——**本次不動**。
- `Logo`/`Sidebar`：`Logo` 是純 SVG icon 對照表；`Sidebar` 有 mobile drawer + badge 邏輯但依賴
  `window.innerWidth`/`useTheme`，範圍較大、涉及多個 responsive 分支，適合另開一支獨立 issue，
  **本次不動**（留待下次評估是否要做）。
- `StatusPill.tsx`：3 支**匯出的純函式**（`turbineStatusTone`/`workOrderStatusTone`/
  `technicianStatusTone`）是全站狀態顏色語意的唯一來源，目前完全零直接測試——只能靠呼叫端頁面
  測試間接命中，覆蓋不保證完整（例如 fallback default 分支）。
- `Charts.tsx`：`MiniSparkline`/`BigChart`/`HealthBar` 是純 SVG path 數學（正規化座標、
  range=0 除以零防呆、`Math.max(len-1,1)` 防呆、`HealthBar` 的 clamp + 顏色門檻），這類邊界條件
  正是最容易被日後小重構悄悄破壞、卻無任何頁面測試會剛好命中的分支（例如「全部數值相同」
  「只有一筆資料」「clamp 到 0/100」）。

判定：後兩支值得補測試，前五支/兩支暫不動。零後端變更，純測試新增。

Docker 阻塞兩項（WMOM-20260716-06 / WMOM-20260509-F6）與 HTTPS 部署配置仍卡（同前次 session
記錄，本次環境同樣只有 docker client 無 daemon）；A2 Part 4 需先決定取樣點插值/分桶設計，非本次
單 session 無歧義可做範圍。故依決策樹選本項（第 5 類：測試覆蓋擴大）。

## Preflight

- backend baseline：`1103 passed, 7 skipped, 1 xfailed`（與 STATUS.yaml 記錄一致，全程未動任何
  backend 檔案）。
- frontend baseline：`npx tsc --noEmit` 0 error；`npx vitest run` `1100 passed`（53 files）；
  build 用 `./node_modules/.bin/vite build` OK（見下方環境備註）。
- Stack-aware 檢查（GitHub MCP 可用）：`list_pull_requests(state=open)` 回傳空陣列，無殘留 PR；
  `git fetch origin main` 後本地分支與 `origin/main` 同步（無需 merge）。
- 分支：環境注入的 `claude/inspiring-mccarthy-xvio1d`。
- ⚠ 環境備註：`npx vite build`（無參數指定版本）這次解析成 npx 快取的 `vite@8.3.0`（訊息
  「The following package was not found and will be installed」，等於重新從 registry 抓一個
  全新版本），而非專案 `node_modules` 裡鎖定的 `vite@^6.2.0`，導致找不到 `index.html` entry
  build 失敗——**非程式碼 regression**，改用 `./node_modules/.bin/vite build`（或
  `npm run build`，package.json script 同款）直呼本地鎖定版本即可正常 build。供下次 session
  若遇到同款「Cannot resolve entry module index.html」錯誤時參考。

## Implement

零 production 變更，純測試新增：

- **`components/ui/__tests__/StatusPill.test.tsx`（新檔）**：
  - 元件渲染：children 顯示；7 種 tone（`ok`/`warn`/`amber`/`info`/`accent`/`muted`/`danger`）
    各自套用對應 theme palette 顏色（讀 `style` 屬性字串比對 hex，不用 `getComputedStyle`——
    比照全站既有測試慣例不斷言計算後樣式，只斷言 inline style 字串內容）；`colorBg`/`colorFg`
    覆蓋 tone 對照表；`size='md'` vs 預設 `'sm'` 兩種 padding/fontSize；`title` 屬性透傳。
  - 純函式（逐一測完整分支，含 default fallback）：
    - `turbineStatusTone`：OPERATING→ok / FAULT→warn / IDLE→amber / OFFLINE→muted /
      未知字串→muted（default 分支）。
    - `workOrderStatusTone`：IN_PROGRESS→amber / COMPLETED→ok / OPEN→accent /
      未知字串→accent（default 分支）。
    - `technicianStatusTone`：ON_DUTY→ok / 'ON DUTY'（含空格變體）→ok / DISPATCHED→accent /
      未知字串→muted（default 分支）。
- **`components/ui/__tests__/Charts.test.tsx`（新檔）**：
  - `MiniSparkline`：空陣列→只渲染 placeholder `<div>`（無 `<svg>`）；單一數值→不崩潰、path
    `d` 屬性不含 `NaN`；多筆數值正常路徑；`fill=true`→多渲染 1 個 `<path>`（gradient area）
    + `<linearGradient>` 存在，`fill=false`→只有 1 個 `<path>`；全部數值相同（range=0）→
    fallback range=1 防呆，path 不含 `NaN`。
  - `BigChart`：全空（無 series 或 series 內都是空陣列）→渲染 `—` placeholder、無 `<svg>`；
    單一 series 無 `upper`/`lower`→只 1 條 `<path>`（無 band）；`upper`+`lower`
    長度相等→多 1 條 band `<path>`；`fill=true`→再多 1 條 area `<path>`（band+area+line
    共 3 條）；`grid=true`（預設）→5 條格線 `<line>`，`grid=false`→0 條；`events`
    帶 `label`→對應 `<circle>` + `<text>` 內容存在。
  - `HealthBar`：值域夾範圍（`110`→顯示 `100%`；`-10`→顯示 `0%`）；顏色門檻三段（`90`→ok 色、
    `80`→amber 色、`50`→warn 色，各自用 `style` 字串比對 `C.ok`/`C.amber`/`C.warn` hex）；
    邊界值 `85`（不大於 85→非 ok 走 amber 分支）與 `75`（不大於 75→非 amber 走 warn 分支）
    各自驗證條件是 `>` 而非 `>=`。

## Verify

- **6 個關鍵分支手動 mutation-verified**（逐一改 production、跑對應測試確認 fail、再還原，
  `git diff` 對 production 檔案最終乾淨）：
  1. `turbineStatusTone` 的 `IDLE` 分支改回傳 `'ok'`（而非 `'amber'`）→ 對應測試 fail。
  2. `workOrderStatusTone` default 分支改回傳 `'muted'`（而非 `'accent'`）→ default fallback
     測試 fail。
  3. `MiniSparkline` 的 `range = max - min || 1` 改成 `range = max - min`（拿掉防呆）→
     「全部數值相同」測試從「path 不含 NaN」變成 fail（除以 0 產生 `NaN`）。
  4. `BigChart` 的 band 渲染條件 `s.upper && s.lower && s.upper.length === s.lower.length`
     改成永遠 `true`（拿掉長度相等檢查）→「upper/lower 長度不等時不應渲染 band」的測試 fail。
  5. `HealthBar` 顏色門檻 `pct > 85` 改成 `pct >= 85`→ 邊界值 85 測試（預期非 ok 色）fail。
  6. `HealthBar` 的 `Math.max(0, Math.min(100, value))` clamp 拿掉下限 `Math.max(0, ...)`
     （只留上限 clamp）→ 負值測試（預期顯示 `0%`）fail（變成顯示負數）。
- **Full baseline（review 前）**：backend 未動，重跑仍 `1103 passed, 7 skipped, 1 xfailed`；
  frontend `npx tsc --noEmit` 0 error；`npx vitest run` `1100→1100+N passed`（見下方 Wrap-up
  實際數字，本段先寫流程）；build 用本地 `./node_modules/.bin/vite build` OK。

## 誠實回報：沒有自動化保護的部分

- **SVG 視覺正確性**（`MiniSparkline`/`BigChart` 畫出來的線條/漸層在瀏覽器裡是否好看、顏色是否
  正確套用主題）：測試只驗證 `path`/`line`/`circle`/`text` 等 DOM 結構與 `d`/`style` 屬性字串內容
  是否符合預期數學計算，未經人工瀏覽器渲染驗證（本 session 未做）。
- **`Sidebar.tsx` 完全未測試**（mobile drawer transform、badge 顯示、backend 健康狀態 dot、
  lang/theme 切換按鈕）——本次評估後判定範圍較大另開一支，非本次疏漏，是刻意延後的決定。
- **`Btn`/`Card`/`Field`/`Stat`/`PageHeader`/`Logo` 無獨立單元測試**——判定為純展示型、已被
  全站既有 page-level 測試間接覆蓋，ROI 低，本次刻意不做（見上方「認領理由」判斷依據）。

## Wrap-up

（收尾時補：新增測試數、code-reviewer review 結果、ISSUES.md/STATUS.yaml/TODO.md 更新、
下次接手建議。）
