# 2026-06-07 — FarmSelector component render 測試（WMOM-20260607-04，EPIC-M5 測試覆蓋擴大）

> autonomous worker session（每 3 小時 cron），2026-06-07 第四輪。
> 純測試新增、零 production 變更，延續「render 測試剩餘 untested 元件」清單。

---

## 1. 開工 / 決策

Preflight 全綠：backend 638 passed / 1 xfailed；frontend 751 passed（上輪 EventComparisonView PR #98
已 auto-merge 進 main，baseline 自 751 起算）。

Stack-aware：`mcp__github__list_pull_requests` 顯示 21 個 open PR **全為飛輪上線前 stale draft**
（#30–#68），無進行中 WIP，亦無只等 CI 的新 PR → 可安全另起新工作不撞 merge。

決策樹 #1（blocker）/ #2（baseline regression）/ #3（飛輪壞掉）皆無 → 落 **#4 乾淨 autonomous 工作**。
接上輪 handoff「render 測試剩餘 untested 元件」清單下一支——`components/FarmSelector.tsx`
（532 行，sidebar 風場切換器 + 新增風場 modal，先前零 render 覆蓋）。

## 2. 本次完成

**新增** `components/__tests__/FarmSelector.test.tsx`（初版 **35 tests** + code-reviewer 採納補測 4 → **39 tests**，純測試零 production 變更）。

### Mock 策略
- `useTheme`：用真實 `ThemeProvider`（與 UserSwitcher / EventComparisonView 一致）。
- `global.fetch`：以 `vi.fn` 路由三端點——
  - `GET /api/farms` → `{ farms, active_farm_id }`（列表）
  - `POST /api/farms/{id}/activate` → 切換（可控 ok / 非 ok）
  - `POST /api/farms` → 建立 `{ farm: { farm_id } }`
  - 未預期 URL reject；`rejectAll` 選項驗 `fetchFarms` 容錯。
  - 用 `init.method` 區分同路徑 `/api/farms` 的 GET（list）vs POST（create）。
- `window.location.reload`：jsdom 未實作 navigation，直接呼叫會 throw。整顆 `window.location`
  換成只有 `reload: vi.fn()` 的物件，**afterEach 用 `originalLocation` 還原**（避免測試間洩漏）。

### 覆蓋範圍（6 describe / 35 tests）
- **mount fetch / trigger 殼層**（6）：mount GET 一次·aria-haspopup/aria-expanded·active farm
  名+額定 MW·無 active fallback「選擇風場 / Select farm」·en label。
- **展開 / 收合**（6）：初始無 listbox·點 trigger 展開+aria-expanded=true·再點收合·標頭
  「風場專案 / +新增」zh+en·**click-outside（document mousedown）關閉**。
- **farm 清單**（7）：option 數=farms 數·名/台數/MW/地點·active 標 aria-selected+「使用中」·
  非 active 無標記·en「Active / turbines」·空清單「尚未建立風場 / No farms」。
- **切換 farm**（3）：點非 active → POST activate + `reload` 一次·**點 active 自己為 no-op**
  （不打 API/不 reload）·activate 非 ok 不 reload。
- **新增風場 modal**（11）：開 dialog+關 dropdown·4 顆 preset（z72 預設 pressed）·切 preset·
  name 空 Create disabled→輸入啟用·離岸 checkbox 勾選·**送出 POST body 驗 name+preset+is_offshore**·
  建立成功 onCreated 重新 fetch（GET≥2）·✕/取消/overlay 三條關閉路徑·en 標題。
- **容錯**（2）：fetch reject 不崩潰顯 fallback·reject 後仍可展開顯空狀態。

### 眉角
- 同路徑 `/api/farms` GET vs POST 用 `init.method` 分流（create 與 list 撞 URL）。
- `window.location` 整顆替換需在 afterEach 還原 `originalLocation`，否則污染後續測試。
- option name 用 farm 名 regex 比對（`getByRole('option', { name: /雲林陸域風場/ })`）；
  MW/台數同字串可能多處出現 → 用 `within(option)` 縮範圍斷言。

## 3. code-reviewer

跑 `code-reviewer` subagent 對 staged diff：回 **5 must-fix + 7 should-fix + 3 nice-to-have**。
逐點 triage（**採納 9 / 婉拒 3 / 駁回誤判 1**）：

**採納**
- must#1 Create 鈕只斷言 aria-label 不守顯示文案 → 補 `toHaveTextContent('建立並啟用')`。
- must#3 activate 非 ok 測試 `waitFor` 後同步斷言可能在 microtask 未落地 → 補 `await act(async () => {})` flush。
- must#4 activate 測試沒驗 method 是 POST（bug 改 GET 仍假綠）→ 兩條 activate 測試補 `&& m === 'POST'`。
- 一致性（must#2 衍生）→ `calls()` 全部用兩參數 lambda `(u, m)` / `(u, _m)`，閱讀統一。
- should#1 onCreated 的 `switchFarm`（建立後自動切換核心 side-effect）未測 → **補測** POST `/api/farms/f-new/activate`。
- should#2 creating inflight 狀態未測 → **補測**（pending POST → Create disabled + 「建立中…」）。
- should#3 POST 失敗 error path 未測 → **補測**（ok=false → 顯 detail + modal 不關）。
- should#5 stopPropagation 反向行為未測 → **補測**「點 Card 內部不關 modal」。
- 可讀性 `openCreateModal` 從 describe 內移到 **top-level helper**（與 `openDropdown` 一致、可跨 describe 重用）。
- nice 空清單 installFetch 排序 → 加注釋說明須在 renderSelector 前呼叫。

**駁回（誤判）**
- must#2 指 `calls(u => ...)` 單參數 lambda 是 TS 型別錯誤 → **誤判**：TS 容許「參數較少的函式」賦值給「參數較多的函式型別」（fewer-params-OK），`tsc --noEmit` 0 error 已實證。仍採其「一致性」精神統一成兩參數。

**婉拒**
- must#5 建議改 `vi.spyOn(window.location, 'reload')` → **婉拒並實證**：本 jsdom 的 `location.reload`
  是 non-configurable，`vi.spyOn` 直接 throw「Cannot redefine property: reload」（已用 probe test 驗證）。
  現行「整顆 location 換掉 + afterEach 還原 originalLocation」才是必要做法，已加注釋說明。
- must#6 module-level `let fetchMock` 脆弱 → **婉拒**：與既有 `EventComparisonView.test.tsx` 慣例一致，
  reviewer 亦自承「這一個測試實際不會出錯」，為一致性保留。
- should#4/should#6（switching 並發 guard / aria-expanded=false 版本差異）→ **婉拒**：前者需可控 pending
  promise 模擬連點、ROI 低且易 flaky；後者 aria-* attribute React 一律序列化為字串（非 boolean 省略），
  現行 `toHaveAttribute('aria-expanded','false')` 已正確。

採納後 35 → **39 tests**，並寫了對應 regression 守護（onCreated switchFarm / creating / error / stopPropagation）。

## 4. Verify

- `npx tsc --noEmit`：0 error
- `npx vitest run`：**790 passed**（751 baseline + 39 新，零 regression）
- `npx vite build`：✓ built（production code 未動，沿用初版綠燈）
- backend 未動（純新增 frontend 測試），638 passed / 1 xfailed 不受影響

## 5. 收尾 / 下次接手

- 完工開正常 PR（CI 綠 → auto-merge 自動合 main）。
- **render 測試剩餘 untested 元件**：`MaintenanceHub`（439）/ `FaultInjectionPanel`（555）/
  ui primitives（Btn / Field / Input / Select / Card / StatusPill…）/ Sidebar / Charts。
- 非 render 方向：M5-2 ChromaDB（🟡 需劉老師拍板 chromadb 依賴 + 向量檔來源）/
  M5-5 `/field/` mobile Part B-2（🟡 需劉老師拍板現場工程師完工流程）/
  **stale PR triage**（#30–#68 共 21 筆 pre-flywheel draft，建議劉老師批次關閉 superseded）。
