# 2026-06-04 — FarmOverview component render 測試（EPIC-M5 測試覆蓋擴大）

> autonomous worker session（每 3 小時 cron）。接續 costpage-render-tests handoff #1：
> 「同範式續推 component render 測試：FarmOverview（730）/ SettingsPage（781）/ HistoryPage（809）/ workflow」。
> issue：**WMOM-20260604-04**（FarmOverview component render 測試）

---

## 1. 為什麼做這個

開工 preflight（決策樹）：

- 優先級 #1 known blocker / #2 baseline regression / #3 飛輪壞掉 → **皆無**。
  - backend `pytest` → **638 passed / 1 xfailed**（綠）
  - frontend `vitest` → **123 passed**（綠；上個 session CostPage 15 tests 已 auto-merge 進 main，PR #76）
  - 飛輪健康：CostPage render 測試 PR #76 已 squash-merge 進 main + 刪分支。
- stack-aware：`list_pull_requests` open=22，全為飛輪上線前的 stale PR（無 `[WIP]`、非本 session 系列、無 CI run 不會被誤合）。本次工作（net-new 測試檔）與它們**零 collision**。

→ 落到優先級 #4「乾淨 autonomous 工作」。前三個同日 session（FieldPage / ReportsPage / CostPage）連續 handoff **背書**「同範式續推 FarmOverview」。FarmOverview（`components/FarmOverview.tsx`，730 行）是 `/admin` 風場總覽落地頁，**純由 props 驅動**（turbines / settings / lang），唯二外部依賴是 `useTheme`（ThemeProvider 包裹）與 TrendCard 的 `/api/turbines/farm-trend` fetch，可乾淨 stub，**零設計歧義、單 session 可完工** → 選定。

## 2. 認領

**WMOM-20260604-04** — FarmOverview component render 測試（EPIC-M5 測試覆蓋擴大）。

## 3. 本次完成（Implement）

純測試，**不動任何 production 程式**：

| 檔案 | 內容 |
|---|---|
| `frontend/components/__tests__/FarmOverview.test.tsx`（新，18 tests） | FarmOverview render 測試。`makeTurbine` 工廠（核心欄位全列、無 `as` 強轉）+ SETTINGS_MOCK/SETTINGS_LIVE fixture。元件用 `ThemeProvider` 包裹（`useTheme` 無 Provider 會 throw）。`global.fetch` 以 `vi.stubGlobal` stub，路由 `/api/turbines/farm-trend`（未預期 URL reject，不靜默吞）。`renderOverview` async + `act(async)` 包 render + `flushAsync`（setTimeout 0）drain 多層 fetch chain（零 act 警告）。 |

### 18 tests 覆蓋的 UX 契約
- **PageHeader**：zh 預設「早安，營運團隊。」+ 風場副標 / en「Good morning, Operator.」/ `dataSource=MOCK` → MOCK 徽章現、SIMULATION → MOCK 徽章不現
- **HeroStats 計算**：全運轉 → 風場功率加總（2.1+1.0=3.1 MW）/ 平均風速（(8+6)/2=7.0）/「全部健康」/「一切順利」；有故障 → 「狀態混合」/「請關注 →」
- **三種檢視模式切換**：預設 cards（風機卡片名稱 + 卡片鈕 aria-pressed）/ summary（CompactTile fmtPower：0.5 MW → 500 kW）/ table（表頭「風機·狀態·功率 MW」+ 欄位值 toFixed + 缺值 4 欄「—」）
- **onSelectTurbine 接線**：cards 點卡片 / table 點 row → 帶正確 turbine（`toMatchObject {id,name}`）
- **TrendCard**：預設 24H aria-pressed + mount 觸發 `farm-trend?range=1d` fetch / 切 1H aria-pressed 翻轉 / 切 6H → `range=12h` fetch / 切 7D → `range=1d` fetch（守後端只支援至 1d 的刻意 cap）/ 無資料「資料收集中…」/ 有資料「資料收集中…」消失
- **語系**：lang=en → table 表頭 Turbine / Status / Power MW 英文

### 技術要點 — 模組級可變快取的順序穩定處理
FarmOverview.tsx 有 module-level 可變快取（`_trendCache` / `_liveTrend` / `_lastLiveAt`）會跨 render 存活，naïve 寫法會讓「有資料 vs 收集中」測試**跨測試順序 flaky**。對策：
- **預設 fetch stub 回空 trend 資料**（`{ data: [] }`）→ `_trendCache['24H']` 維持空 → 「資料收集中…」**穩定出現且順序無關**。
- 唯一驗「有資料 → 圖表渲染（收集中消失）」的測試**置於檔尾最後一個 describe**，其 fetch override 回資料只汙染 24H 快取，不影響前面任何測試。
- TrendCard 的 `BigChart`/`MiniSparkline` 是固定 viewBox 的 SVG（不依賴 clientWidth），jsdom 下穩定渲染，故用「`資料收集中…` 文字是否在場」判斷圖表態，而非脆弱的 SVG 尺寸斷言。

### fixtures 型別嚴格
`makeTurbine` 工廠列出 TurbineData 全部核心必填欄位（id/name/status/powerOutput/windSpeed/rotorSpeed/bladeAngle/temperature/vibration/voltage/current/history），不用 `as` 強轉；table 用的 optional 欄位（genStatorTemp1 等）透過 `over` 注入，讓 tsc 守住與 `types.ts` 對齊（漏欄位編譯失敗而非靜默假綠）。

## 4. Verify（本機全綠才開 PR）

- `npx tsc --noEmit` → **0 error**（無 `any`、無 `as` 強轉）
- `npx vitest run` → **141 passed**（123 baseline + 18 新，零 regression、零 act() 警告）
  - 額外 `--sequence.shuffle` 跑亦 18 passed → 證明已脫離模組級快取的執行順序依賴（見 Issue 1 修正）
- `npx vite build` → ✓ built（僅既有 chunk-size 提示）
- backend 未動 → **638 passed / 1 xfailed** 不受影響（開工已驗）

## 5. Code review

用 `code-reviewer` subagent 對 staged diff 跑審查（聚焦測試正確性 / 假綠 / 模組快取 flake / act 警告 / cleanup）：
**7 must-fix / 5 should-fix / 3 nice-to-have**（reviewer verdict: needs revision）。逐一審視後，**採納 4 個真有價值的**、**駁回 1 個 false-positive**、其餘 must-fix 經判斷非真缺陷或屬 maximalist 過度防禦（getByText 對歧義是「大聲失敗」而非假綠），記錄理由：

**已採納（高價值修正）**：
1. **[Issue 1 · 模組快取跨測試污染]** `_trendCache` 是模組級可變狀態，原「把有資料測試置於檔尾」策略依賴執行順序、在 `--randomize`/watch 局部重跑會 flaky。**改法**：所有「有資料→渲染圖表」驗證都先以空資料 mount（24H 快取維持空）後，再切到 **6H** 並回資料 → 只填充 6H 快取、24H 始終為空，與「無資料」測試彼此獨立、順序無關。實測 `--sequence.shuffle` 18 passed 佐證。（不採 reviewer 建議的 `vi.resetModules()`+dynamic import：會讓 test 檔靜態 import 的 React/ThemeProvider 與動態 import 的 FarmOverview 來自不同 module 實例 → React context 身分不一致 / invalid hook call。）
2. **[Issue 2 · jsonResponse 缺 ok/status]** 對齊 CostPage.test 的 okJson，補 `ok:true, status:200`（TrendCard 目前未檢查 `r.ok`，但日後加守衛時 stub 仍走 happy path 而非靜默）。
3. **[Issue 4 · '—' 計數魔術數字]** 原 `getAllByText('—').toHaveLength(4)` 在新增欄位時會「對錯誤理由」失敗 → 改針對資料 row 的特定 cell index（vibrationX/bladeAngle1/cnvGenFreq/yawError）逐一 `toHaveTextContent('—')`，更精確。
4. **[Issue 6/8/15 · async flush 不足]** fetch chain 是 fetch→json→setState 多個 microtask tick，單一 `await Promise.resolve()` 不保證 drain → 抽 `flushAsync`（`setTimeout 0`）用於 renderOverview 與切換時段的 act 內；並補「切 6H 發 range=12h fetch」測試（明確覆蓋會觸發 fetch 的時段切換 + act 包覆）。

**駁回（false-positive，記錄理由）**：
- **[Issue 7 · 宣稱 `RANGE_TO_API['7D']='1d'` 是 production bug]** reviewer 未核對後端即斷言「7D 應送 range=7d」。實查 `modules/monitoring/server/routers/turbines.py:29,39`：後端 farm-trend **只接受 `5m/1h/12h/1d`**，`range_map.get(time_range, 300)` 對未知值 fallback 成 5m。故 `7D→'1d'` 是**刻意的 cap**（前端封頂到後端最大 1 天窗），照 reviewer 改成 `'7d'` 反而會讓 7D 視圖靜默退化成 5m → **引入真 bug**。屬 production 行為 + 產品語義（7D 是否該顯示 7 天）議題，非本 pure-test PR 範圍。**改採**：新增「切 7D → 送 `range=1d` 且**不**送 `range=7d`」測試，把這個刻意映射轉成 regression 守衛（而非按 reviewer 改壞它）。若劉老師確認 7D 應顯示完整 7 天，再開後端 issue 加 `7d` range 支援。

**未採納（非真缺陷 / 需動 production / 過度防禦，記錄理由）**：
- **[Issue 3/10 · hero 數值斷言建議用 within(testid) 範圍化]**：`getByText('3.1')/'7.0'` 在當前 fixture 下唯一；`getByText` 對歧義是 throw（大聲失敗）而非假綠，故非正確性漏洞。範圍化需在 production HeroStats 加 `data-testid`（純測試 PR 不動 production）。保留現狀。
- **[Issue 5/12 · 點 span/td 而非 Card/tr]**：`fireEvent.click` 在 jsdom 會冒泡到 Card/tr 的 onClick，且 `afterEach(cleanup)` 已隔離跨測試 DOM；這是 RTL 標準實務。Card 無 role/testid，改法需動 production。已加註解說明點擊冒泡意圖。
- **[Issue 9/11 · lang=en+table onSelect 變體 / OPC_DA·MODBUS_TCP 徽章]**：覆蓋盲點而非缺陷；`isMock === DataSourceType.MOCK` 是單一相等判斷，SIMULATION 變體已足以守住「非 MOCK 不顯徽章」契約。低 ROI，略過。
- **[Issue 13/14 · 空 turbines 邊界 / `let utils!` non-null]**：邊界值與防禦性 micro-nit，現有 18 tests 已覆蓋主要契約，不擴張。

**Verify（採納後）**：`tsc` 0 error + `vitest` **141 passed**（含 `--sequence.shuffle` 亦綠）+ `vite build` ✓。

## 6. 下次 session 接手建議

- **同範式續推 component render 測試**：SettingsPage（781 行）/ HistoryPage（809 行）/ workflow 各 panel（`components/workflow/` 下 11 個元件，目前只有 statusUtils helper test）。基礎設施 + 四個範例（FieldPage / ReportsPage / CostPage / FarmOverview）已就位。
- **M5-5 Part B-2**（my work orders + completion）—— 仍需劉老師釐清 persona/auth「who is me」（🟡）。
- **M5-2 ChromaDB**（🔵；需評估 CI 加 `chromadb` 重依賴的安裝時間 / Linux runner 相容）。
- **22 個 stale PR triage**（待劉老師 / 後續 session）。

## 7. 給劉老師

- 純測試擴充，**零 production 程式改動**，無 schema / DB / 部署影響，CI 綠即 auto-merge。
- FarmOverview 是 admin 進系統第一眼看到的風場總覽（hero KPI + 趨勢圖 + 風機卡片/列表），現有 render 測試守住「KPI 計算 + 三檢視切換 + 點風機導航 + 趨勢接線 + 語系」核心契約，日後改版有 regression 防護網。
- **需劉老師確認的小產品問題（從 code review 帶出）**：總覽趨勢圖的「**7D**」時段目前實際只拉**最近 1 天**資料（前端 `RANGE_TO_API['7D']='1d'`，因後端 farm-trend 只支援到 1d）。亦即「7D」按鈕顯示的不是 7 天趨勢。若這是預期（UI 標示待修）就無事；若 7D 應顯示完整 7 天，需開後端 issue 在 farm-trend 加 `7d` range + SQLite 查詢支援。本次先以測試把現況（送 range=1d、不送 7d）鎖成 regression 守衛，未擅改 production 行為。
