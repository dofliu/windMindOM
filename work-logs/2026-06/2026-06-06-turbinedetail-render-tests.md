# Work Log — 2026-06-06 — TurbineDetail component render 測試

**Issue**: WMOM-20260606-05
**Milestone**: M5（測試覆蓋持續工作 / EPIC-M5 測試覆蓋擴大）
**Branch**: claude/exciting-cori-q13WR
**Owner**: Claude (autonomous worker, session 2026-06-06 第五輪)

---

## 目標

延續 component render 測試系列，為 `components/TurbineDetail.tsx`（1056 行，本系列至今最大的元件）
補 render 測試。前份 handoff 點名的「下一個」：monitoring 大元件，需 mock 即時資料。

本元件是 `/admin` 風機詳情頁（A · Calm Operator 改版），結構：
- PageHeader 麵包屑（返回風場總覽）+ 機名 · TurState label + 狀態 pill + Curtail/Stop/Inspect actions
- 故障 banner（僅 activeFaults 非空才渲染）
- 4 大 hero 數字（Power / Wind / RPM / Gen °C）
- 左欄：即時趨勢 4 通道、子系統健康 8 格、子系統明細 8 tabs、詳細趨勢（TrendChartPanel 重元件）
- 右欄：OperatorControlCard（6 指令 + 限載，每 3s 輪詢 control status）、最近事件、AI 故障診斷（僅 FAULT 才渲染）

## Preflight

- `git status` clean，自 `main`（d16ff6a）reset designated 分支 `claude/exciting-cori-q13WR`
- backend baseline：638 passed / 1 xfailed ✓
- frontend baseline：**525 passed**（25 files）✓（上輪 MaterialRequestDetailModal PR #91 已 auto-merge 進 main；baseline 自 481 推進到 525，含 FarmOverview/CostPage/HistoryPage/SettingsPage 等同日先前合入）
- stack-aware：`list_pull_requests` 22 筆 open 全為飛輪上線前 stale draft（#30–#68），無進行中 WIP → 安全開新工
- 決策樹 #1/#2/#3 皆無 → 落 #4 乾淨 autonomous 工作（測試覆蓋擴大 🔵）

## 實作

新增 `components/__tests__/TurbineDetail.test.tsx`（最終 **49 tests**，純測試、零 production 變更）。

**外部依賴隔離策略**（本元件比先前 detail modal 多了 3 種外部副作用）：
- `useTheme` → ThemeProvider 包裹（沿用範式）
- `analyzeTurbineFault`（services/geminiService）→ `vi.mock` 注入 `mockAnalyze` spy，避免真打 Gemini；
  `beforeEach` reset + 預設 resolve 一段診斷字串，個別測試以 `mockResolvedValueOnce` / `mockRejectedValue` 覆寫
- `TrendChartPanel`（recharts + 多支 fetch 的重元件）→ `vi.mock` 換成輕量 stub div（帶 `data-turbine` / `data-lang`），
  只驗「有掛載 + 收到 padding 後 turbineApiId（WT007）+ lang」，不重測它自身 SCADA 圖表行為
- `global.fetch` → OperatorControlCard 掛載即 GET `/api/control/:id/status` + 每 3s 輪詢、指令走 POST。
  `stubFetch(status)` helper 接管：GET status 路徑回指定 status、其餘（POST 指令/限載）回空物件，回傳 spy 供斷言 body

**flakiness 對策**：
- 所有 render 以 `await renderDetail(...)`（內部 `act(async)` 包 render + flush microtask）收尾 → flush 掉
  control status fetch effect 的 setState，避免「state update not wrapped in act()」警告
- 3s 輪詢 + 2s 清訊息 setTimeout 用 **real timer**：快速測試（<1s）內不會二次觸發；`afterEach(cleanup)` 卸載 clearInterval
- `afterEach` 同時 `vi.restoreAllMocks()`；`stubFetch` 每個測試重設 `global.fetch`，`beforeEach` 先給預設空 status

**覆蓋契約**（49 tests）：
- **殼層/header**（11）：機名·TurState label（正常發電/未知→「State {n}」fallback）/ 返回鈕 aria-label + onBack /
  三 action 按鈕 / 狀態 pill 四態（運轉中·故障·待機·離線）/ 室外溫·風向 sub / lang=en 殼層+actions+breadcrumb
- **hero 數字**（2）：四格 label + 格式化值（getAllByText 容 hero 與 live-trends/明細同值）/ genStatorTemp1 缺漏退 temperature
- **故障 banner**（4）：無故障不渲染 / 有故障 banner 含嚴重度% + phase / tripped→TRIPPED pill / active_alarms 逐筆 type+desc
- **子系統健康/明細**（5）：健康 8 格 label（scope 在健康卡內查，因發電機·變頻器與 tab 按鈕同字）/
  明細 8 tab + 預設總覽 aria-pressed / 點 tab 切換 + 內容 / 缺值「—」fallback / lang=en tab 英文
- **TrendChartPanel 接線**（3）：turbineApiId padding（WT007 / id=12→WT012）/ lang 傳遞
- **OperatorControlCard**（13）：掛載 GET padding id / 6 指令+限載鈕 / status-driven pill 五態（定檢·手動停機·
  緊急停機·限載+解除鈕·shutdown_cause 非 idle vs idle 不顯示）/ 指令 POST body（start·emergency_stop·
  service_on）/ 限載 POST（parseFloat 值·空值→null·解除→null）+ OK 訊息 pill
- **最近事件**（4）：OPERATING+低風→併網中 / IDLE→待機 / 高風速>12→高風速 / OFFLINE+低風+無故障→無事件 placeholder
- **AI 診斷卡**（6）：非 FAULT 不渲染 / FAULT 渲染+自動分析呼 analyze+結果回填 / 重新分析二次呼+更新 /
  失敗→錯誤訊息 / 有結果無 WO→派遣鈕呼 onDispatch(turbine, result) / 有 activeWorkOrder→工單處理中 pill 取代派遣鈕 / lang=en

**踩雷（已修）**：
1. 三處 `getByText` 撞重複文字 →（a）IDLE「待機」header pill 與最近事件並存（b）hero 值 2.34/8.5/95
   與 live-trends 通道 cur 同值（c）健康卡「發電機/變頻器」label 與明細 tab 按鈕同字。對策：(a)(b) 改 `getAllByText().length>0`、
   (c) 以 `within(healthCard)` scope（`screen.getByText('子系統健康').parentElement`）。
2. `vi.fn<[Args], Return>()` 雙型別參數在本 vitest 版本不支援（TS2558）→ 改 `vi.fn<(t: TurbineData) => Promise<string>>()` 函式型別式。

工廠 `makeTurbine` / `makeFault` / `makeWorkOrder` 結構式滿足型別（不用 `as`），overrides 末尾 spread。

## Verify

- `npx tsc --noEmit`：0 error ✓
- `npx vitest run`：**574 passed**（525 baseline + 49 新，零 regression）✓
- `npx vite build`：built ✓
- backend 未動：638 passed / 1 xfailed 不受影響

## Review

用 `code-reviewer` subagent 對 staged diff 審查，回 6 must-fix + 6 should-fix。逐項 triage：

**採納（6）**：
- Issue 1（must）：`global.fetch = spy` 直接賦值不受 `restoreAllMocks` 管理 → 改 `vi.stubGlobal('fetch', spy)` + `afterEach` 加 `vi.unstubAllGlobals()`，杜絕跨檔洩漏。
- Issue 4 + 12（must/should）：IDLE「待機」`getAllByText().length>0` 太鬆（header pill 與最近事件無法區分）→ 改 `>=2`，header pill 退化成別字時 count 掉到 1 即抓到。
- Issue 5（must）：FaultBanner 故障名稱完全未覆蓋 → banner 測試加 `name_en`（jsdom navigator.language='en-US'）斷言。
- Issue 7（should）：hero 漏驗 RPM 12.3 格式化值 → 補 `getAllByText('12.3')`。
- Issue 9（should）：派遣鈕 `not.toBeDisabled()` 在 auto-analyze effect 鏈未必 settle → 包 `await waitFor(...)`。

**婉拒（6，理由記錄）**：
- Issue 2 / 10：建議改 `toHaveBeenNthCalledWith` / `toHaveBeenLastCalledWith`。實際上 `sendCmd`/`setCurtail` 後生產碼會再 `refresh()` 發一次 GET → **最後一次呼叫是 GET 而非 POST**，`toHaveBeenLastCalledWith(POST)` 會誤判失敗；現行 `toHaveBeenCalledWith` 以 `method:'POST'` + 完整 body 比對，GET 無此 method 故已不存在假綠。維持不動。
- Issue 3：建議對指令測試啟 fake timer 收 2s setTimeout 殘留。但全套 574 測試跑綠、**零 act 警告**（React 18 對卸載後 setState 為 no-op），且 fake timer 會與 await act 的 async fetch flush 互相打架，引入風險大於收益。維持 real timer + `afterEach(cleanup)`。
- Issue 6 / 8：建議改 `vitest.config` 加 `define` 固定 API_BASE、生產碼加 `data-testid`。皆動到共用設定 / 生產碼僅為測試便利，屬 scope creep 且 reviewer 自承「目前不算假綠」。維持 fallback + `parentElement` scope。
- Issue 11：curtail `parseFloat('abc')=NaN` 為**生產碼**邊界缺陷（JSON.stringify(NaN)='null' 靜默變解除限載），修它屬行為變更需劉老師決策，超出本次純測試範圍 → 記此處 follow-up。

**Verify（採納後重跑）**：`tsc` 0 error + `vitest` **574 passed**（不變，零 regression）+ `vite build` ✓。

## 給劉老師的 follow-up（非阻塞）

- **OperatorControlCard 限載 NaN 缺陷**：使用者於限載輸入框打非數字（如 `abc`），`parseFloat` 回 NaN，
  `JSON.stringify({powerLimitKw: NaN})` 序列化成 `null` → 後端誤判為「解除限載」。建議生產碼加 `Number.isFinite` 防護
  （另開 issue 修 + 補 regression test）。本次 render 測試先不擅自改生產行為。

## 收尾

- 完整完工，開正常標題 PR（CI 綠 → auto-merge 自動合 main）
- issue_stats done 72→73 / total 86→87

## 下一步（給下個 session）

- **render 測試剩餘大元件**：`FieldPage` 系列 / `KnowledgePage`（若未覆蓋）/ monitoring 其他面板；
  detail modal（WorkOrder / MaterialRequest）+ wizard（WorkOrder / MaterialRequest）+ 列表面板 + TurbineDetail 已覆蓋
- **非 render 方向**：M5-2 ChromaDB（需劉老師拍板 chromadb 依賴 + 向量檔來源 🟡）/ M5-5 `/field/` mobile Part B-2
  （my work orders·completion 🔵）/ stale PR triage（#30–#68 共 22 筆 pre-flywheel draft）
