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
    各自套用對應 theme palette 顏色（讀 `style` 屬性字串比對 hex，不用 `getComputedStyle`——本
    repo **首次**對 inline style 字串斷言計算後顏色，先前既有測試多不斷言計算後樣式；選這個
    做法是因為 jsdom 不支援 `getComputedStyle` 展開簡寫，不想為此另外引入套件）；`colorBg`/`colorFg`
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
  frontend `npx tsc --noEmit` 0 error；`npx vitest run` `1100→1148 passed`（53→55 files，
  +48 新測：`StatusPill.test.tsx` 27 + `Charts.test.tsx` 21）；build 用本地
  `./node_modules/.bin/vite build` OK。
- **Full baseline（review 後修復完）**：追加 1 個 nice-to-have（見下方 Review）並
  mutation-verified（`BigChart` events 的 `x = e.position * W` 改成 `+ 10` 位移 → 新增的
  `cx` 精確斷言 fail，還原後 `git diff --stat` 對 production 檔案乾淨）；frontend
  `npx vitest run` 仍 `1148 passed`（測項內容微調，總數不變，只是原本的存在性斷言改成精確
  座標斷言）；`npx tsc --noEmit` 0 error；backend 全程未動。

## 誠實回報：沒有自動化保護的部分

- **SVG 視覺正確性**（`MiniSparkline`/`BigChart` 畫出來的線條/漸層在瀏覽器裡是否好看、顏色是否
  正確套用主題）：測試只驗證 `path`/`line`/`circle`/`text` 等 DOM 結構與 `d`/`style` 屬性字串內容
  是否符合預期數學計算，未經人工瀏覽器渲染驗證（本 session 未做）。
- **`Sidebar.tsx` 完全未測試**（mobile drawer transform、badge 顯示、backend 健康狀態 dot、
  lang/theme 切換按鈕）——本次評估後判定範圍較大另開一支，非本次疏漏，是刻意延後的決定。
- **`Btn`/`Card`/`Field`/`Stat`/`PageHeader`/`Logo` 無獨立單元測試**——判定為純展示型、已被
  全站既有 page-level 測試間接覆蓋，ROI 低，本次刻意不做（見上方「認領理由」判斷依據）。

## Review

code-reviewer subagent 獨立跑（含自己重算 `hexToRgb` 全部 14 個 palette hex 驗證位數切分無誤、
自己 dump `HealthBar` 實際 render 出的 `innerHTML` 逐層確認 DOM 遍歷路徑非巧合命中、自己動手做
4 組 mutation testing 交叉驗證）：

**verdict：0 must-fix / 2 should-fix / 2 nice-to-have → Approve**

- 🟡 **should-fix #1（已修）**：`WMOM-20260923-04` 未登記進 `ISSUES.md`/`STATUS.yaml`（work-log
  當時仍是「收尾時補」佔位符）——已在本節之後補上。
- 🟡 **should-fix #2（已修）**：`StatusPill.test.tsx` 檔頭 docstring 原寫「比照專案內未見對計算後
  樣式斷言的既有慣例」，用詞容易誤解成「跟進既有慣例」；reviewer 獨立 grep 全 repo 確認這其實是
  **首次**引入此模式（先前 53 支既有測試檔案皆無此做法）。已改寫成明確講「本 repo 首次」+ 選擇
  原因（jsdom 不支援 `getComputedStyle` 展開簡寫），避免下次接手的人誤讀成沿用既有慣例。
- 🟢 **nice-to-have #1（已採納）**：`BigChart` 的 `events` 測試原本只驗證「至少一個 circle 存在」，
  改為精確斷言 `cx` 座標（`position=0.5 × W=800 = 400`），並 mutation-verified（`x` 計算式加
  `+10` 位移 → 新斷言 fail，還原後乾淨）。
- 🟢 **nice-to-have #2（不採納）**：兩支測試檔案各自複製一份 `hexToRgb` helper（12 行）；
  reviewer 自己也判斷「目前只有 2 處，不急著抽」，本次不動。

reviewer 對 5 個面向（正確性/tautological 檢查、hexToRgb 邏輯、HealthBar DOM 遍歷、
`ThemeProvider`/`localStorage` 測試間污染風險、work-log 誠實度）逐一確認：測試非 tautological
（6 個關鍵分支各自可被 mutate 出 fail）；`hexToRgb` 位數切分正確；`getByText('90%')
.previousElementSibling?.firstElementChild` 精確對應 production 三層巢狀（label / track+fill /
percentage），非巧合命中；`vitest.config.ts` 維持預設 `test.isolate: true`
+ `ThemeProvider` 只在 `toggle`/`setMode` 才寫 `localStorage`，兩支新測試皆未呼叫，確定全程
停留在 light mode 無汙染風險；work-log「誠實回報」段落屬實。

## Wrap-up

- `ISSUES.md`：新增 WMOM-20260923-04 done 條目；stats `done 110→111`、`total 121→122`。
- STATUS.yaml：`issue_stats.done` 110→111；`last_updated` 追加本 session 摘要；
  `next_milestone` 維持上次接手建議不變（A2 Part 4 / PR C / docker 阻塞兩項 / HTTPS 部署仍是
  下次候選，本次是額外插入的測試覆蓋擴大項目）。
- TODO.md：更新「最後更新」摘要，補上「ui primitives 評估完成：`StatusPill`/`Charts` 已補測試，
  其餘 7 支判定 ROI 低或範圍另計，暫不動」，並從「可立即接手」清單移除該行 placeholder。
- 分支：`claude/inspiring-mccarthy-xvio1d`；純測試新增（+48 測，53→55 files），零 production
  變更；code commit 已 push（含 review 後的 should-fix/nice-to-have 追加 commit）；PR 待開
  （見下）。

**下次接手**：A2 Part 4（差異圖，需先解決多序列取樣點不完全對齊的插值/分桶問題）/ PR C（檢視
情境掛載 app，需先寫 broker 子設計）/ `Sidebar.tsx` component 測試（本次評估後判定範圍較大，
獨立開一支：mobile drawer transform + badge + backend 健康狀態 dot + lang/theme 切換）。
M6 critical path 的 docker 阻塞兩項（footprint pin / PostgreSQL row-lock）與 HTTPS 部署配置
仍待部署環境/劉老師決策，非本次可解。

⚠ **附帶發現（本次未動，供劉老師知悉）**：`STATUS.yaml` 的 `last_updated` 欄位目前不是合法 YAML
（`python3 -c "import yaml; yaml.safe_load(open('STATUS.yaml'))"` 會拋 `ScannerError`）——
`last_updated: "2026-09-23"` 後面接的長篇 changelog 文字本意是 inline comment，但橫跨許多
「實體行」卻只有第一行有 `#`，其餘行沒有 `#` 前綴，對嚴格 YAML parser 而言是語法錯誤。用
`git show origin/main:STATUS.yaml` 確認**這個問題在本 session 開工前就已存在於 main**（非本次
造成），且目前 repo 內沒有任何程式/CI 會實際 `yaml.safe_load()` 這個檔案（純人工/session 閱讀
用），故不影響任何自動化流程，本次維持既有格式慣例（每個 session 直接接續文字，不加 `#`）續寫，
未嘗試修復（風險：這是一份持續增長的巨型變更記錄，要修成嚴格合法 YAML 需要決定新格式並改寫
一大段既有內容，範圍超出本次任務，且 ISSUES.md 已記錄過一次因格式問題「YAML 直接無法解析」的
合併事故，貿然大改容易重蹈覆轍）。建議下次若要修，開一支獨立 issue 專門處理（例如把巨型
changelog 挪到獨立的 CHANGELOG 檔案，`STATUS.yaml` 本身只留精簡摘要）。
