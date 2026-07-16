# windMindOM — Issues

> 本檔案是 windMindOM 的單一 source of truth issue tracker。
> 所有工作都從這裡認領；新工作請開新 issue 並寫進來。
> Issue ID 格式：`WMOM-{YYYYMMDD}-{NN}`。模板見 `templates/issue-template.md`。
>
> Status 流轉：`open → in_progress → done`（或 `blocked`）。
> 每次 session 開工 / 結尾，請更新 issue status 與下方統計表。

---

## 統計

| Status | Count |
|--------|------|
| open | 15 |
| in_progress | 2 |
| blocked | 0 |
| done | 86 |
| **total (active)** | **103** |

最後更新：2026-07-16（**專案檢視 session — 4 PR 進 main #105-108**）。全 repo 檢視 → `docs/product/PROJECT_REVIEW_2026-07-16.md`（F1-F6）；P0 文件真相對齊 + CI 補 monitoring/physics（#106）；M6 決策簡報 + openopc2 GPL 標示（#107）；**M6-4 真 auth 基礎層 done**（#108，stdlib JWT+RBAC+login，非破壞，+34 tests，DEC-20260716-01）。全 backend **899 passed / 0 failed**。新增 issue：done WMOM-20260716-01/02/03、open WMOM-20260716-04/05/06（見下方 EPIC-M6）。**下一步**：auth follow-up（DB user store → router 強制授權 + 前端真登入）+ footprint CPU-torch pin（DEC-20260716-02）+ 客戶接觸（WMOM-20260503-05）。

> 📁 前一筆詳細 changelog（2026-06-07/08，FarmSelector render 測試 + M5 大推進）已封存到 work-logs/2026-06/；各 issue 詳細紀錄保留於下方 `### WMOM-*` 區段。

> 📁 更早一筆 changelog（WMOM-20260607-03 EventComparisonView）詳見 work-logs/2026-06/2026-06-07-eventcomparisonview-render-tests.md；各 issue 詳細紀錄仍保留於下方 `### WMOM-*` 區段，更早 session 的 changelog blurb 已封存到 `docs/legacy/issues_changelog_archive.md`。

---

> 📁 更早的 session changelog 已封存到 [`docs/legacy/issues_changelog_archive.md`](docs/legacy/issues_changelog_archive.md)（避免本檔無限膨脹；完整 work-log 在 `work-logs/`）。

---

## 📌 2026-07-16 session 新增 issue（專案檢視 follow-up）

**Done（#105-108）**
- **WMOM-20260716-01** — 專案檢視（`PROJECT_REVIEW_2026-07-16.md` F1-F6）+ P0 onboarding 文件真相對齊 + CI 補 monitoring/physics（#105 #106）✅
- **WMOM-20260716-02** — M6 部署決策簡報（auth/footprint）+ openopc2 GPL/體積標示 + footprint 量測（#107）✅
- **WMOM-20260716-03** — M6-4 真 auth 基礎層：stdlib JWT + RBAC + login，非破壞（#108，DEC-20260716-01）✅

**Open（auth / footprint follow-up）**
- **WMOM-20260716-04** — 🔵 auth follow-up：DB-backed user store + admin 建帳 API（換掉 seeded store；介面已預留 `build_default_store()`，非破壞）
- **WMOM-20260716-05** — 🟡 auth follow-up：router 逐支改 `get_current_actor`/`require_roles` 強制授權 + 前端 mock login 換真 `/api/auth/login`（**②③配套、會改行為，需劉老師在場排**）
- **WMOM-20260716-06** — 🔵 footprint CPU-torch pin（Dockerfile，DEC-20260716-02，image 砍半；本地無 docker，待部署環境驗）

---

## 🎯 未來大目標（M5 / M6 epics）

> M1-M4 已 100%。以下是接下來的「大局目標」拆解，給 session 規劃用。
> 詳細月度交付見 [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md) Month 5 / Month 6。
> 標 🔵 = autonomous-friendly（無設計歧義可自動接）；🟡 = 需劉老師決策 / 素材 / 現場。

### EPIC-M5 — Knowledge / RAG + 現場 mobile UI（2026-09，PMF 關鍵）

> 目標：警報跳出 → 30 秒內現場工程師手機看到「手冊對應段落 + 過去同類警報處置」。
> Demo killer：「這比 LINE 群組問師傅快嗎？」

| # | Epic 子目標 | 類型 | 依賴 / 備註 |
|---|---|---|---|
| M5-1 | ~~**Knowledge module 後端**：`retrieve.py` / `strategy_loader.py` / `alert_handler.py`~~ ✅ done（WMOM-20260601-01，baseline 檢索層） | 🔵 | 平台只載入 + query，不重新 embed |
| M5-2 | **ChromaDB 整合**（嵌入式、依 OEM 機型載入向量檔） | 🔵 | |
| M5-3 | **RAG_Ultimate strategy 對接**：拿 Phase 3 的 `strategy.yaml` + `z72_manual.parquet` | 🟡 | 需 RAG_Ultimate Phase 3 產出；未 ready 用 baseline placeholder |
| M5-4 | **灌 Z72 手冊 + 一年警報 csv** 跑通 ingest pipeline | 🟡 | 手冊已有 `docs/__Z72UserManual.pdf` |
| M5-5 | **`/field/` mobile-first frontend**：~~知識檢索查詢（Part A）~~ ✅ done（WMOM-20260603-03）/ ~~alert detail with RAG（Part B-1）~~ ✅ done（WMOM-20260603-04）/ my work orders · completion（Part B-2 待續） | 🔵 | 現場工程師 persona、PMF 關鍵 |
| M5-6 | ~~**Alert → RAG auto query**：警報事件觸發即 retrieve，前端顯示 top-3 chunks~~ ✅ done（WMOM-20260603-01，FastAPI knowledge router 3 endpoints） | 🔵 | 串 M5-1 + monitoring 告警 |

### EPIC-M6 — 第一個運維廠商 PoC + 第一筆合約（2026-10）

> Done criteria：客戶老闆說「下個月續用」+ 現場工程師 80% 警報走 RAG + 第一份月報沒被業主退件 + 收到合約金。

| # | Epic 子目標 | 類型 | 依賴 / 備註 |
|---|---|---|---|
| M6-1 | **Friendly 運維廠商現場部署**（docker-compose 在客戶端跑起來） | 🟡 | 需客戶現場 |
| M6-2 | **Z72 PLC 連線測試**（客戶端 OPC tunnel） | 🟡 | 需客戶 PLC |
| M6-3 | **PostgreSQL backend 切換 + row-lock 驗證**（WMOM-20260509-F6） | 🔵 | 部署前；需 docker postgres |
| M6-4 | **deployment hardening**：JWT / RBAC / HTTPS（取代 mock login）— **基礎層 done**（#108 WMOM-20260716-03，DEC-20260716-01）；剩 DB user store（-04）+ router 強制授權/前端真登入（-05）+ HTTPS | 🔵 | 基礎層非破壞已進 main；②③配套需在場排 |
| M6-5 | **培訓 + 第一個月運轉 + 收反饋** | 🟡 | 需客戶 |
| M6-6 | **第一份自動月報交業主** | 🔵 | reporting module 已 ready，需真資料驗證 |

### 跨 milestone 持續工作

- **WMOM-20260503-05** — Friendly 客戶接觸（infrastructure done，待劉老師 cold email + 約 demo）🟡
- **測試覆蓋持續擴大**：component render 測試（需 jsdom setupFiles）、E2E lifecycle 強化 🔵
- **物理模型強化**（學術深度，非商業 must-have）：WMOM-20260505-23~28 🔵

---

## M5（2026-09）— Knowledge / RAG + 現場 mobile UI

### WMOM-20260607-04 — FarmSelector component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-07 完成，第四輪）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；sidebar 風場切換器 + 新增風場 modal，先前零 render 覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-07 第四輪)
- **Completion summary**:
  - ✅ **`components/__tests__/FarmSelector.test.tsx`（新，39 tests，純測試零 production 變更）**：為 `FarmSelector.tsx`（532 行）補 component render 測試。本元件是 sidebar 底部「風場切換器 + 新增風場 modal」：mount GET `/api/farms` 取清單+active；trigger 顯目前 active farm 名+額定 MW（無 active 退 fallback）；點開向上彈 dropdown（role=listbox）列每個 farm 名/台數/MW/地點、active 標 aria-selected+「使用中」；點非 active option→POST activate→`window.location.reload()`，點 active 自己為 no-op；「+ 新增」開 CreateFarmModal（role=dialog，4 機型 preset、風機數量、離岸 checkbox、Create 鈕 name 空 disabled，送出 POST `/api/farms`→onCreated 重新 fetch+switchFarm）。
  - ✅ **Mock 策略**：`useTheme` 用真實 ThemeProvider；`global.fetch` 以 `vi.fn` 路由三端點（`GET /api/farms` 列表·`POST /api/farms/{id}/activate` 切換·`POST /api/farms` 建立），helper `installFetch({ listBody, activateOk, createBody, rejectAll })` 可逐測覆寫，用 `init.method` 區分同路徑 `/api/farms` 的 GET（list）vs POST（create），未預期 URL reject；`window.location` 整顆換成只有 `reload: vi.fn()` 的物件（jsdom 未實作 navigation 直呼會 throw），**afterEach 用 `originalLocation` 還原避免測試間洩漏**。所有 render 以 `await renderSelector(...)` / `openDropdown(...)` flush mount fetch effect。
  - ✅ **覆蓋契約**：mount fetch / trigger 殼層（mount GET 一次·aria-haspopup=listbox·初始 aria-expanded=false·active 落地顯名+8.0 MW·無 active fallback 選擇風場/Select farm·en label）/ 展開收合（初始無 listbox·點 trigger 展開+expanded=true·再點收合·標頭風場專案/+新增 zh+en·click-outside document mousedown 關閉）/ farm 清單（option 數=farms 數·名/台數/MW/地點·active aria-selected=true+「使用中」·非 active false 無標記·en Active/turbines·空清單尚未建立風場/No farms 且無 option）/ 切換（點非 active→POST `/api/farms/f2/activate`+reload 一次·點 active 自己 no-op 不打 API 不 reload·activate 非 ok 不 reload）/ 新增 modal（開 dialog+關 dropdown·4 preset z72 預設 aria-pressed=true·切 preset 轉移·name 空 Create disabled→輸入啟用·離岸 checkbox 預設未勾→點勾·送出 POST body 驗 name+preset+is_offshore·建立成功 onCreated 重新 fetchFarms GET≥2·✕/取消/overlay 三條關閉路徑·en 標題 Create wind farm/Create farm）/ 容錯（fetchFarms reject 不崩潰顯 fallback·reject 後仍可展開顯空狀態）。
  - ✅ **眉角**：同路徑 `/api/farms` GET（list）vs POST（create）撞 URL→用 `init.method` 分流；`window.location` 整顆替換需在 afterEach 還原 `originalLocation` 否則污染後續測試；MW/台數同字串可能多處出現→option 斷言用 farm 名 regex（`getByRole('option', { name: /雲林陸域風場/ })`）+ `within(option)` 縮範圍避多元素命中。
  - 🔍 **code-reviewer review**：回 **5 must-fix + 7 should-fix + 3 nice-to-have**，**採納 9 / 駁回誤判 1 / 婉拒 3**。採納：must#1 Create 鈕補斷言顯示文案「建立並啟用」（原僅命中 aria-label 有假綠風險）·must#3 activate 非 ok 測試補 `await act` flush microtask·must#4 兩條 activate 測試補驗 method=POST·`calls()` 統一兩參數 lambda·should#1 補測 onCreated 觸發 switchFarm（POST activate 新風場 f-new，建立後自動切換核心 side-effect）·should#2 補測 creating inflight（pending POST→disabled+「建立中…」）·should#3 補測 POST 失敗 error path（顯 detail+modal 不關）·should#5 補測「點 Card 內部不關 modal」守 stopPropagation·`openCreateModal` 移至 top-level helper·空清單 installFetch 排序注釋。駁回誤判：must#2 指單參數 lambda 為 TS 型別錯誤——TS 容許 fewer-params 賦值、`tsc` 0 error 實證（仍採一致性精神）。婉拒：must#5 `vi.spyOn(window.location,'reload')` 在本 jsdom throw「Cannot redefine property: reload」（probe 實證）→保留整顆 location 替換+afterEach 還原·must#6 module-level fetchMock 與既有 EventComparisonView 慣例一致·should#4/#6 switching 並發 guard（需可控 pending、易 flaky）/ aria-expanded=false（aria-* 一律序列化字串、現行正確）ROI 低。採納後 35→39 tests。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **790 passed**（751 baseline + 39 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：render 測試剩餘 untested 元件（MaintenanceHub 439 / FaultInjectionPanel 555 / ui primitives——接手前先 `ls components/ui` 確認哪些已覆蓋）；非 render 方向 M5-2 ChromaDB（🟡）/ M5-5 `/field/` mobile Part B-2（🟡）/ stale PR triage（#30–#68 共 21 筆）。
- **Reference**: [`work-logs/2026-06/2026-06-07-farmselector-render-tests.md`](work-logs/2026-06/2026-06-07-farmselector-render-tests.md)

### WMOM-20260607-03 — EventComparisonView component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-07 完成，第三輪）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；多風機事件比較分析面板，先前零 render 覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-07 第三輪)
- **Completion summary**:
  - ✅ **`components/__tests__/EventComparisonView.test.tsx`（新，32 tests，純測試零 production 變更）**：為 `EventComparisonView.tsx`（332 行）補 component render 測試。本元件是多風機事件比較分析面板：風機 toggle 選擇器（預設選前 4 台）+ 全選/清除 / 時間範圍（datetime-local）+ 事件類型 Select + 匯出 CSV / 狀態列（載入中·N 事件·M 台）/ 單機摘要（每台 total + by_type pills）/ 全場事件 / 事件時間線（含空狀態）。mount 即 fetch `/api/maintenance/events/compare`，filter 變更觸發 refetch。
  - ✅ **Mock 策略**：`useTheme` 用真實 ThemeProvider + ui 元件（驗實際渲染）；`global.fetch` 以 `vi.fn` 路由 `/api/maintenance/events/compare` 回 `{ timeline, summary, farm_events }`（未預期 URL reject 不靜默吞），helper `installFetch({ body, rejectAll })` 可逐測覆寫；`window.open` stub 成 `vi.fn`（jsdom 未實作，驗匯出 CSV URL 拼裝）。turbine fixture 5 台（id 1-5 → WT001-005，元件預設選前 4 台）。所有 render 以 `await renderView(...)` flush mount fetch effect。
  - ✅ **覆蓋契約**：殼層標題（zh 選擇風機/事件時間線·en Select turbines/Event timeline·預設 lang zh）/ 風機選擇器（5 顆 toggle 鈕·預設前 4 台 pressed 第 5 台 false·點選加入/取消·全選全 true·清除全 false+摘要隱藏·en All/None）/ filters 匯出（事件類型 Select 選項 zh/en·匯出 CSV→window.open 帶 `/api/export/events?format=csv`·en Export CSV）/ fetch 接線（mount compare 帶 turbine_ids+limit=500·選事件類型觸發 event_type fetch·變更開始時間觸發新 fetch·清除後 selectedIds 空不再 fetch）/ 狀態列（settle 後 N 事件·M 台·pending 顯載入中…·清除後 0 台）/ 單機摘要（summary 有資料顯 total+by_type pills·缺台退回 total=0 fallback 各顯一個 0）/ 全場事件（farm_events 有資料顯區塊+標題·空陣列不渲染）/ 時間線（有事件顯標題+severity pill·detail 行內細節·_turbine_id 優先+兩者皆缺「—」fallback·空狀態 zh「未找到事件。」en「No events found.」）/ 容錯（fetch reject 不崩潰仍渲染殼層+空狀態·空 turbines 無按鈕無 fetch）。
  - ✅ **眉角**：WT###（如 WT001）同時出現在選擇器按鈕/摘要卡/時間線欄→摘要與時間線斷言改用 distinctive total 數字/by_type pill 文字/事件標題避多元素命中；`turbine_ids` 逗號經 URLSearchParams encode 為 `%2C`→URL regex 同時容忍 `,`/`%2C`；event_type/datetime refetch 用 `countBefore`+`slice`+`waitFor` 確保斷言的是套用後那次。
  - 🔍 **code-reviewer review**：回 **0 must-fix + 4 should-fix + 6 nice-to-have**，**採納 8 / 婉拒 2**：should#1 摘要 test `waitFor` 等的是 mount 即存在的 section heading（恆真）→改等 fetch 產物（total 數字）本身，bare expects 入 async 保護；should#2 `getAllByText('0')` 弱斷言 `>0`→`toHaveLength(3)` 精確；should#3 en Select test 描述列 All 但未驗→補 All option 斷言；should#4 狀態列 test timeline fixture 殘缺欄位（只 id）會觸發 Invalid Date→補完整 ComparisonEvent 欄位；nice#1 補 `載入中…` loading 態（pending fetch）；nice#2 補 `ev.detail` 行內文字；nice#3 補 `_turbine_id` 優先+`—` fallback；nice#5 補 datetime 範圍變更 refetch。**婉拒 2**：nice#4 severity 缺席空 `<span/>` 佔位（無可斷言文字、價值低）；nice#6 farmEvents `slice(0,30)` 截斷（31 筆 fixture 噪音大、純展示細節非 regression 熱點）。採納後 28→32 tests。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **751 passed**（719 baseline + 32 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：render 測試剩餘 untested 元件（MaintenanceHub 439 / FarmSelector 532 / FaultInjectionPanel 555 / ui primitives——接手前先 `ls components/ui/__tests__` 確認哪些已覆蓋）；非 render 方向 M5-2 ChromaDB（🟡）/ M5-5 `/field/` mobile Part B-2（🟡）/ stale PR triage（#30–#68 共 22 筆）。
- **Reference**: [`work-logs/2026-06/2026-06-07-eventcomparisonview-render-tests.md`](work-logs/2026-06/2026-06-07-eventcomparisonview-render-tests.md)

### WMOM-20260607-02 — TrendChartPanel component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-07 完成，第二輪）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；風機詳情頁即時趨勢圖面板，先前零 render 覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-07 第二輪)
- **Completion summary**:
  - ✅ **`components/__tests__/TrendChartPanel.test.tsx`（新，27 tests）+ `TrendChartPanel.tsx` footer 加 `data-testid="trend-footer"`（穩定選取用微 production 變更）**：為 `TrendChartPanel.tsx`（225 行）補 component render 測試。本元件是風機詳情頁的「即時趨勢圖」面板：標題 / 7 個 tag preset 按鈕（預設 power active）/ 自訂 tag 輸入框（逗號分隔）+ 套用 / recharts LineChart / 底部「顯示標籤」列（i18n label）/ mount 兩條 fetch effect（i18n labels + trend）+ 每 2s 輪詢 + unmount clearInterval。
  - ✅ **Mock 策略**：`useTheme` 用真實 ThemeProvider；`recharts` 全 stub 成 marker div（與 CostPage.test 一致，避 jsdom 0 寬度 ResponsiveContainer 噪音）；`global.fetch` 以 `vi.fn` 依 URL 路由（`/api/i18n/tags` 回 tag label 對映、`/trend` 回 `{ data: [...] }`，未預期 URL reject 不靜默吞），helper `installFetch({labels, trendData})` 可逐測覆寫；輪詢/cleanup 專屬測試用 `vi.useFakeTimers()` + `advanceTimersByTimeAsync` 精確驗證。所有 render 以 `await renderPanel(...)` flush 兩條 mount fetch effect。
  - ✅ **覆蓋契約**：標題殼層（zh「即時趨勢圖」/en「Real-time trend」/預設 lang 走 zh）/ preset 按鈕（7 顆 zh+en label·預設 power aria-pressed=true 其餘 false·點選高亮轉移）/ 自訂 tag（placeholder+套用鈕 zh/en·輸入+套用切 tags 清 preset 高亮+footer 反映·自動 trim·空白純逗號 guard 不變更）/ fetch 接線（mount fetch i18n 帶 lang zh/en·mount fetch trend 帶 turbineId+power tags+limit=120·點 preset 觸發帶新 tags 的 trend fetch）/ i18n label 解析 footer（有 label 顯 label·無 label 退 raw tag·部分 label 混合·前綴 zh「顯示標籤」en「Showing」）/ 輪詢 cleanup（每 2s 輪詢一次·unmount clearInterval 不再輪詢）/ 容錯（i18n+trend 皆 reject 不崩潰仍渲染殼層+footer raw tags·trend 缺 data 欄位不崩潰）。
  - ✅ **眉角**：footer 列以「葉節點 div（`children.length===0`）且 textContent 以前綴開頭」matcher 精確抓，避開祖先 div 同 textContent 的多元素命中；自訂 tag trim 驗證同時斷言 footer 文字與送出的 trend fetch URL（`tags=FOO,BAR`），雙重守住 `handleCustomApply`。
  - 🔍 **code-reviewer review**：回 4 must-fix + 5 should-fix + 3 nice-to-have，**採納 8 / 婉拒 2**：must#1 `renderPanel` 補 `lang='zh'` 預設+回傳；must#2 unmount 包 `act` 防 flaky；must#3 footer 加 `data-testid` + 測試改 `getByTestId`（取代脆弱葉節點 predicate）；must#4 空 label 測試加 `waitFor` settle（去恆真命題）；should#5 `aria-pressed` 改 RTL `getByRole({pressed})` 語意查詢；should#6 trim 測試改 `countBefore`+`slice`+`waitFor`；should#8 容錯走 `installFetch` 加 `rejectAll`/`trendBody` 封裝；nice#9 guard 測試補「trend fetch 次數不變」斷言；nice#10/#11 補 turbineId/lang prop 變動 rerender 重 fetch 覆蓋。**婉拒 2**：should#7 recharts mock 補 CartesianGrid/Cell——本元件未 import，mock 應對齊 component 實際 import；nice#12 `WGDC_TrfCoreTmp` 命名——測試正確鏡射元件值，tag 命名是另案。採納後 25→27 tests。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **719 passed**（692 baseline + 27 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：render 測試剩餘 untested 元件（EventComparisonView 332 / MaintenanceHub 439 / FarmSelector 532 / FaultInjectionPanel 555 / 根 `WorkOrderDetailModal.tsx` 315 疑似 stale 重複——另有 `components/workflow/WorkOrderDetailModal.tsx` 已測，接手前先確認哪支實際被引用 / ui primitives）；非 render 方向 M5-2 ChromaDB（🟡）/ M5-5 `/field/` mobile Part B-2（🟡）/ stale PR triage（#30–#68 共 22 筆）。
- **Reference**: [`work-logs/2026-06/2026-06-07-trendchartpanel-render-tests.md`](work-logs/2026-06/2026-06-07-trendchartpanel-render-tests.md)

### WMOM-20260607-01 — UserSwitcher component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-07 完成，第一輪）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；sidebar mock-login 切換器，WMOM-20260510-01 Part B 雙 persona demo 關鍵元件，先前零 render 覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-07 第一輪)
- **Completion summary**:
  - ✅ **`components/__tests__/UserSwitcher.test.tsx`（新，27 tests，純測試零 production 變更）**：為 `UserSwitcher.tsx`（231 行）補 component render 測試。本元件是 sidebar 底部 mock-login 切換器：trigger 鈕顯示目前 user 名+主要 role，向上彈出 dropdown（listbox）列出所有 `is_active` fixture user，點選即切換；目前 user 標 aria-selected + 「使用中/Active」；`dev_mode_only` user 標「dev/dev only」tag；多角（Owner）role 以「 / 」join；無障礙 Escape/click-outside 關閉 + option Enter/Space 選取。
  - ✅ **Mock 策略**：元件 props 僅 `lang`、資料全來自 `useCurrentUser` context → **mock 掉該 hook**（注入 currentUser/availableUsers 含一名停用者驗 `is_active` filter + spy `setCurrentUser`），`useTheme` 用真實 ThemeProvider。provider 本體（localStorage 持久化/fixtures）已由既有 `services/__tests__/mockUsers.test.ts`（20 tests）獨立覆蓋，故 component 測試 mock hook 不犧牲整合保真度。工廠 `makeUser` 結構式滿足 `MockUser`（不用 `as`），衍生 ALICE/BOB/CAROL/OWNER/INACTIVE 五 fixture。
  - ✅ **覆蓋契約**：殼層（trigger aria-haspopup/expanded·名稱+role zh·多角 join·treasury 單角 Carol「財務」·初始不渲染 listbox）/ 展開收合（點開 aria-expanded+listbox·再點收合·listbox aria-label+標頭）/ 選項清單（每 active user 一 option·`is_active=false` filter·aria-selected 反映 currentUser·「使用中」唯一·dev tag 標/不標·role join+email「 · 」附後·email 空不附·`availableUsers=[]` 空陣列展開 0 option）/ 選取接線（click→setCurrentUser+收合·Enter·Space·自選自己仍觸發·Tab 不觸發且維持開）/ 關閉路徑（click-outside body mousedown 關·dropdown 內 mousedown 不關·Escape 關）/ 語系 en（trigger aria-label+role·標頭+aria-label+dev only+Active·多角 join）。
  - ✅ **眉角**：多元素命中防呆——殼層斷言一律 `within(trigger)`、option 斷言一律 `within(listbox)` 或 `closest('[role=option]')` scope；「使用中」用 `getAllByText().toHaveLength(1)` 守唯一；click-outside 用 `fireEvent.mouseDown(document.body)`（body 非 dropdownRef 後代 → contains 回 false → 關閉）。加 inline comment 說明 RTL `getByText` 以 `getNodeText` 只比對直接 text-node、不含巢狀 dev span。
  - 🔍 **code-reviewer review**：回 1 must-fix + 4 should-fix + 2 nice-to-have，**採納 5**：should#2 `clearAllMocks`→`restoreAllMocks` 與 DispatchModal 一致；should#3 補 Carol（treasury 單角）fixture+test 獨立守 `formatRoles` 財務標籤；should#5 補「自選自己 option」test 守無 guard 行為；nice#6 email-empty test 改用 BOB id（與 currentUser 不同）去 isActive 混淆；nice#7 補空陣列 edge case。**婉拒 2**：**must#1 誤判**——指 `getByText('Owner (dev)')` 在 dev_mode_only=true 必拋錯（理由 textContent 含巢狀 span），但 RTL 預設以 `getNodeText` 只比對直接 text-node 子節點、**不含**巢狀 element 內文，實證初版 24 tests 全綠含被點名 3 條（line 220/276/339），若真 throw 整 suite 會 error；should#4 移除冗餘 setCtx 為低價值 churn（顯式列 availableUsers 反而自我說明）。採納後 24→27 tests。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **692 passed**（665 baseline + 27 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：render 測試剩餘 untested 元件（TrendChartPanel 225 recharts / EventComparisonView 332 / MaintenanceHub 439 / FarmSelector 532 / FaultInjectionPanel 555 / ui primitives）；非 render 方向 M5-2 ChromaDB（🟡 需劉老師拍板 chromadb 依賴+向量檔來源）/ M5-5 `/field/` mobile Part B-2（🟡 需劉老師拍板現場工程師身分/完工流程）/ stale PR triage（#30–#68 共 22 筆）。
- **Reference**: [`work-logs/2026-06/2026-06-07-userswitcher-render-tests.md`](work-logs/2026-06/2026-06-07-userswitcher-render-tests.md)

### WMOM-20260606-08 — AnnualBudgetPanel component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-06 完成，同日第八輪）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；A9 年度預算面板，MonthlyReportPanel 姊妹面板，同樣**直接餵 M6-6「第一份自動月報 / 預算交業主」** deliverable，先前本面板本體零 render 覆蓋——頁面層 ReportsPage 把它 mock 掉、僅 formatters 有單元測試）
- **Owner**: Claude (autonomous worker, session 2026-06-06 第八輪)
- **Completion summary**:
  - ✅ **`components/reporting/__tests__/AnnualBudgetPanel.test.tsx`（新，37 tests，純測試零 production 變更）**：為 `AnnualBudgetPanel.tsx` 補 component render 測試。本面板是 `/admin/reports` 年度預算分頁：選 year + current month（結算邊界）→ Generate → KPI 卡（全年預測/實際合計）+ 12 月 forecast vs actual BarChart + 月份明細表（4 大類成本 + method pill 三態 + 年度合計列）+ PDF 下載。
  - ✅ **依賴隔離**：依賴僅 `useTheme` → ThemeProvider 包裹；純 props-driven，唯一 async 副作用 `onDownloadPdf`（prop 注入 Promise）→ 受控 Promise + `waitFor` 驗下載中態 + 失敗錯誤卡。`Btn`/`Card`/`Field`/`Select`/`Stat`/`StatusPill` 用真實 ui 元件不 mock；**recharts 全 stub 成 marker div**（對齊 CostPage 範式，避 jsdom 0 寬度噪音）。工廠 `makeMonth`/`makeMonths`/`makeData` 結構式滿足型別不用 `as`。
  - ✅ **時間眉角**：預設選「今年 + 本月」依賴 `new Date()`；不用 fake timers（卡死 waitFor polling），改用與元件相同邏輯動態算 `EXPECTED_YEAR`/`EXPECTED_MONTH`（`getMonth()+1`），跨月/跨年穩定。
  - ✅ **DOM scope 眉角**：月份標籤（`1月`/`Jan`）同時出現在「當月 Select 選項」與「明細表 cell」→ row 查詢先 `within(getByRole('table'))` scope 再取 row，避 multi-element error；loading 態因 `Btn` 的 aria-label 固定，以 aria-label 取鈕 + `toHaveTextContent` 驗中間態。
  - ✅ **覆蓋契約**：filter bar（年/當月 Select + Generate·farmId 空 disabled·預設今年+本月·年份 cur-4…cur+1 共 6）/ 生成接線（onGenerate 帶當前選擇·改選年份/當月帶新值·loading「生成中…」+disabled）/ empty state 四態 / KPI（farm/year/method scope 在 KPI header·farmName 空退 farmId·全年預測 €1.23M + 實際 €456.79k 各**恰 2 處** KPI+合計列·notes 條件顯示）/ 圖表（months 非空渲染標題·空陣列不渲染）/ 明細表（4 類別表頭·method pill 三態 actual→實際·partial→當月部分·forecast→預測·各類別成本 row scope·actual_total null **與 undefined** 均退 dash「—」·年度合計列）/ PDF 下載（無 data 無鈕·受控 Promise 驗下載中態恢復·失敗錯誤卡）/ 雙 error 獨立 / 語系（en filter/按鈕/KPI/表格/圖表標題·method pill 三態英文·空狀態英文）。
  - 🔍 **code-reviewer review**：回 2 must-fix + 3 should-fix + 3 nice-to-have，**採納 6**：must#1 KPI 年份斷言假綠（裸 `getByText('2026')` 誤命中年份 Select 的 `<option>2026</option>` 而非 KPI 卡）→ 改以 farm span 的 `closest('div')` scope 到 KPI header + `toHaveTextContent` 精確守住；must#2 `getAllByText(...).length >= 1` 過鬆 → 改 `toHaveLength(2)` 同時守 KPI Stat + 合計列兩渲染點；should#3 補 method pill en 三態（Partial/Forecast，原只測 Actual）；should#4 補 `actual_total: undefined`（欄位 omit）退 dash 路徑；should#5 補 null-guard 註解與姊妹測試一致；nice#7 補 en empty state 引導文字。**婉拒 2**（nice#6 vi.fn generic 形式提醒非問題；nice#8 forecast_by_category 缺 key 防禦路徑低價值）。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **665 passed**（628 baseline + 37 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：render 測試剩餘 untested 元件（UserSwitcher 231 / FarmSelector 532 / EventComparisonView 332 / MaintenanceHub 439 / FaultInjectionPanel 555 / TrendChartPanel recharts 重元件 / ui primitives）；非 render 方向 M5-2 ChromaDB（需劉老師拍板 chromadb 依賴+向量檔來源）/ M5-5 `/field/` mobile Part B-2（需劉老師拍板現場工程師身分/完工流程）/ stale PR triage（#30–#68 共 22 筆）。
- **Reference**: [`work-logs/2026-06/2026-06-06-annualbudgetpanel-render-tests.md`](work-logs/2026-06/2026-06-06-annualbudgetpanel-render-tests.md)

### WMOM-20260606-07 — MonthlyReportPanel component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-06 完成，同日第七輪）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；A9 月報生成面板，**直接餵 M6-6「第一份自動月報交業主」** deliverable，先前本面板本體零 render 覆蓋——頁面層 ReportsPage 把它 mock 掉、僅 formatters 有單元測試）
- **Owner**: Claude (autonomous worker, session 2026-06-06 第七輪)
- **Completion summary**:
  - ✅ **`components/reporting/__tests__/MonthlyReportPanel.test.tsx`（新，33 tests，純測試零 production 變更）**：為 `MonthlyReportPanel.tsx`（357 行）補 component render 測試。本面板是 `/admin/reports` 月報分頁：選 year/month → Generate → KPI 5 卡 + 4 大類成本明細表 + HTML iframe 預覽 + PDF 下載；filter bar farmId 空則 disabled、預設選上個月、generate/download 兩 error 各自獨立區塊。
  - ✅ **依賴隔離**：依賴僅 `useTheme` → ThemeProvider 包裹即可；純 props-driven，唯一 async 副作用 `onDownloadPdf`（prop 注入 Promise）→ 受控 Promise + `waitFor`/`findBy` 驗下載中態 + 失敗錯誤卡。`Btn`/`Card`/`Field`/`Select`/`Stat` 用真實 ui 元件不 mock（驗整合輸出）。工廠 `makeKpi`/`makeCategory`/`makeCost`/`makeData` 結構式滿足型別不用 `as`。
  - ✅ **時間眉角**：預設選「上個月」依賴元件內部 `new Date()`。初版誤用 `vi.useFakeTimers()` 固定系統時間 → fake timers 卡死 `waitFor`/`findBy` polling（5 個 async 測試 timeout）。改為**不 fake timers**、在測試裡用與元件相同邏輯動態算期望年/月（`EXPECTED_YEAR`/`EXPECTED_MONTH`），跨月跑也穩定（runner TZ 由 vitest.config 固定 UTC）。
  - ✅ **覆蓋契約**：filter bar（年/月 Select + Generate·farmId 空 disabled·非空 enabled·預設上月·年份 cur-4…cur+1）/ 生成接線（onGenerate 帶當前選擇·改選帶新值·loading 顯示「生成中…」+disabled）/ empty state 四態（未生成顯示·loading·有 data·error 各不顯示）/ KPI 5 卡格式化（總成本 €1.23M·確認比例 73.2%·完工 8 `within` scope·平均 4.50 h·可用率 96.1%）+ header（風場名·年月 zero-pad·產出時間 T→空白 slice19·farmName 空退 farmId）/ 成本表（4 大類繁中 label+合計列·合計三欄格式化·每類別 row `within` scope 三欄·非數字退 dash「—」）/ PDF 下載（無 data 無鈕·有 data 顯示·點下載帶 year+month·受控 Promise 驗下載中態恢復·失敗錯誤卡）/ 雙 error 獨立（generate error 卡·generate+download 同時各自顯示·再次生成清舊 download error）/ HTML preview（html 空不渲染·非空渲染 srcDoc+`sandbox=""` XSS 防護）/ 語系（lang=en 按鈕/標籤/空狀態·KPI+成本表英文標題+欄表頭·英文月名）/ KPI NaN 降級不 crash。
  - 🔍 **code-reviewer review**：回 3 must-fix + 4 should-fix + 3 nice-to-have，**採納 8**：must#2 `.closest('tr')!` 改 `expect(...).not.toBeNull()` + `as HTMLElement`（不靠 `!` 吞 null、結構變更給有意義失敗訊息）；must#3 download 中間態 `waitFor` 內每次重查按鈕（避快取舊 DOM 參考 re-render 後成 stale node）；should#4 `getByText('8')` 以 `within` 鎖定「完工工單」Stat 容器（避裸數字撞欄位）；should#5 移除無用 `farm_name: null` override（header 只讀 farmName prop）；should#6 同步呼叫 `onDownloadPdf` 去掉多餘 `waitFor`；should#7 補 `getMonth()` 0-indexed 換算註解；nice#8 加 KPI NaN edge case test；nice#9 補 en 欄表頭 Estimated/Confirmed 斷言。**婉拒 2**：must#1（regex `getByText` 多元素拋錯）為**誤判**——`getByText` 用 `getNodeText`（只取直接 text 子節點）非 `textContent`，父容器不命中，suite 實跑 33 全綠；nice#10（unhandled rejection 警告）未觀察到、catch 同步掛載。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **628 passed**（595 baseline + 33 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **給劉老師 follow-up（非阻塞）**：MonthlyReportPanel 對 KPI 降級資料（`average_repair_hours=NaN` / 比例 NaN）目前無 guard，會直接輸出「NaN h」「NaN%」（本輪以 test 守住現行行為）；若真資料偶有 SCADA 異常欄位，未來可在 `fmtMoneyDecimal`/`fmtPct`/`.toFixed` 層補 NaN→「—」fallback。
- **下次續做**：render 測試剩餘 untested 元件（AnnualBudgetPanel 姊妹面板 396 行 / UserSwitcher 231 / EventComparisonView 332 / MaintenanceHub 439 / FarmSelector 532 / FaultInjectionPanel 555 / TrendChartPanel recharts 重元件 / ui primitives）；非 render 方向 M5-2 ChromaDB（需劉老師拍板 chromadb 依賴+向量檔來源）/ M5-5 `/field/` mobile Part B-2（有設計歧義需劉老師拍板現場工程師身分/完工流程）/ stale PR triage（#30–#68 共 22 筆）。
- **Reference**: [`work-logs/2026-06/2026-06-06-monthlyreportpanel-render-tests.md`](work-logs/2026-06/2026-06-06-monthlyreportpanel-render-tests.md)

### WMOM-20260606-06 — DispatchModal component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-06 完成，同日第六輪）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；「AI 故障診斷 → 派工」確認對話框，與上輪 TurbineDetail onDispatch 接點直接相關，先前無任何測試覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-06 第六輪)
- **Completion summary**:
  - ✅ **`components/__tests__/DispatchModal.test.tsx`（新，21 tests，純測試零 production 變更）**：為 `DispatchModal.tsx`（194 行）補 component render 測試。本元件是「AI 故障診斷 → 派工」流程的確認對話框，自 TurbineDetail AI 診斷卡（onDispatch）或風場總覽觸發、於 App.tsx 掛載：header 標題「Dispatch Technician」+✕、目標風機名+狀態、AI fault analysis `<pre>` 卡、可用技師清單（僅 ON_DUTY 入選、逐張可點 aria-pressed、無人值班→警告卡）、footer Cancel + Confirm dispatch（未選 disabled）。是 detail modal 系列中**最單純**的一支（純 props-driven、無 fetch/async/lang prop）。
  - ✅ **依賴隔離**：依賴僅 `useTheme` → render wrapper 包 `ThemeProvider` 即可；`Btn`/`Card`/`StatusPill` 用真實 ui 元件不 mock（驗整合輸出）。無 fetch/timer/async callback，故不需 stubFetch/fake timer/await act 收尾。工廠 `makeTurbine`/`makeTech` 結構式滿足型別不用 `as`。
  - ✅ **覆蓋契約**：殼層靜態（dialog role+aria-modal·標題 heading·Close aria-label·目標風機名+狀態·AI fault analysis `<pre>` 原樣字串·區塊標題）/ 技師清單（只列 ON_DUTY 過濾 OFF_DUTY/DISPATCHED·每卡姓名+ON DUTY pill `within` scope·無 ON_DUTY 警告卡·空陣列警告卡·初始 aria-pressed=false·點選→true·改選互斥）/ Confirm gating+callback（未選 disabled·選後可按·`onConfirm(turbineId,technicianId,faultAnalysis)` 原樣透傳 `toHaveBeenCalledWith(42,9,text)`+不自動 onClose·無技師 disabled·id=0 falsy guard 邊界）/ 四關閉路徑（遮罩→onClose·內容點擊 stopPropagation 不關·✕·Cancel）。
  - 🔍 **code-reviewer review**：回 3 must-fix + 4 should-fix + 2 nice-to-have，採納 4：① dead `beforeEach` import 移除；② 新增 id=0 falsy guard 邊界 test（卡視覺選中 aria-pressed=true 但 Confirm 維持 disabled，守住兩 guard 一致行為）；③ `getByText('ON DUTY')` → `getByText(TechnicianStatus.ON_DUTY)` 與 enum 同步；④ Confirm 後補 `expect(onClose).not.toHaveBeenCalled()`。婉拒 5（遮罩/stopPropagation 已由 test pair 雙向覆蓋、regex partial match 為刻意、'FAULT' 碰撞投機、2 nice-to-have 低價值）。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **595 passed**（574 baseline + 21 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **給劉老師 follow-up（非阻塞）**：DispatchModal id=0 falsy guard 小瑕疵——技師 id=0 時卡顯示「已選中」卻按不下 Confirm（視覺/行為不一致）；實務技師 id 從 1 起不影響現況，若未來改 0-indexed 應改 guard 為 `!== null`。
- **下次續做**：render 測試剩餘 untested 元件（UserSwitcher / EventComparisonView / reporting 子面板 MonthlyReportPanel·AnnualBudgetPanel / MaintenanceHub / FarmSelector / FaultInjectionPanel / TrendChartPanel / ui primitives）；非 render 方向 M5-2 ChromaDB（需劉老師拍板 chromadb 依賴+向量檔來源）/ M5-5 `/field/` mobile Part B-2 / stale PR triage（#30–#68 共 22 筆）。
- **Reference**: [`work-logs/2026-06/2026-06-06-dispatchmodal-render-tests.md`](work-logs/2026-06/2026-06-06-dispatchmodal-render-tests.md)

### WMOM-20260606-05 — TurbineDetail component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-06 完成，同日第五輪）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；本系列至今最大元件 1056 行、monitoring 風機詳情頁，先前零 component 測試覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-06 第五輪)
- **Completion summary**:
  - ✅ **`components/__tests__/TurbineDetail.test.tsx`（新，49 tests，純測試零 production 變更）**：為 `TurbineDetail.tsx`（1056 行）補 component render 測試。本元件是 `/admin` 風機詳情頁（A · Calm Operator 改版）：PageHeader 麵包屑+機名·TurState label+狀態 pill+Curtail/Stop/Inspect actions、故障 banner（僅 activeFaults 非空才渲染）、4 hero 數字（Power/Wind/RPM/Gen °C）、左欄即時趨勢 4 通道+子系統健康 8 格+明細 8 tabs+詳細趨勢（TrendChartPanel）、右欄 OperatorControlCard（6 指令+限載+每 3s 輪詢 control status）+最近事件+AI 故障診斷（僅 FAULT 才渲染）。
  - ✅ **外部依賴隔離**（本元件比先前 detail modal 多 3 種外部副作用）：`useTheme`→ThemeProvider 包裹；`analyzeTurbineFault`（services/geminiService）→ `vi.mock` 注入 `mockAnalyze` spy（避免真打 Gemini，`beforeEach` reset+預設 resolve、個別測試 `mockResolvedValueOnce`/`mockRejectedValue` 覆寫）；`TrendChartPanel`（recharts+多支 fetch 重元件）→ `vi.mock` 換輕量 stub div（帶 `data-turbine`/`data-lang`，只驗接線）；`global.fetch` → `stubFetch(status)` helper 接管 control GET/POST（回 spy 斷言 body）。
  - ✅ **flakiness 對策**：所有 render 以 `await renderDetail`（內部 `act(async)` 包 render+flush microtask）收尾 → 消「state update not wrapped in act()」警告；3s 輪詢+2s 清訊息用 **real timer**（快速測試<1s 內不二次觸發）+ `afterEach(cleanup)` 卸載 clearInterval + `vi.restoreAllMocks()`。
  - ✅ **覆蓋契約**：殼層/header（機名·TurState label·未知→「State {n}」fallback·返回鈕 aria-label+onBack·三 action 按鈕·狀態 pill 四態·室外溫/風向 sub·lang=en 殼層+actions+breadcrumb）/ hero 4 數字+genStatorTemp1 缺漏退 temperature / 故障 banner（無故障不渲染·嚴重度%+phase·tripped→TRIPPED·alarms 逐筆 type+desc）/ 子系統健康 8 格（`within(healthCard)` scope）+明細 8 tab 切換+缺值「—」fallback+lang=en / TrendChartPanel padding 接線（WT007·id=12→WT012·lang）/ OperatorControlCard（GET padding id·6 指令+限載鈕·status-driven 5 pill：定檢·手動停機·緊急停機·限載+解除鈕·shutdown_cause 非 idle vs idle 不顯示·指令/限載 POST body：start/emergency_stop/service_on/parseFloat/空→null/解除→null+OK 訊息 pill）/ 最近事件 4 態（併網中·待機·高風速>12·無事件 placeholder）/ AI 診斷卡（非 FAULT 不渲染·FAULT 自動分析+結果回填·重新分析二次呼+更新·失敗→錯誤訊息·有結果無 WO→派遣鈕呼 onDispatch(turbine,result)·有 activeWorkOrder→工單處理中 pill 取代派遣鈕·lang=en）。
  - ✅ **實作眉角**：① 3 處 `getByText` 撞重複文字 →（a）IDLE「待機」header pill 與最近事件並存（b）hero 值 2.34/8.5/95 與 live-trends 通道 cur 同值（c）健康卡「發電機/變頻器」label 與明細 tab 按鈕同字 → 對策 (a)(b) 改 `getAllByText().length>0`、(c) 以 `within(healthCard)` scope（`screen.getByText('子系統健康').parentElement`）；② `vi.fn<[Args],Ret>()` 雙型別參數本 vitest 版不支援（TS2558）→ 改 `vi.fn<(t)=>Promise<string>>()` 函式型別式。工廠 `makeTurbine`/`makeFault`/`makeWorkOrder` 結構式滿足型別不用 `as`。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **574 passed**（525 baseline + 49 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：render 測試剩餘大元件（`FieldPage` 系列 / `KnowledgePage` / monitoring 其他面板）；detail modal（WorkOrder/MaterialRequest）+ wizard（WorkOrder/MaterialRequest）+ 列表面板 + TurbineDetail 已覆蓋。非 render 方向 M5-2 ChromaDB（需劉老師拍板 chromadb 依賴+向量檔來源）/ M5-5 `/field/` mobile Part B-2（my work orders·completion）/ stale PR triage（#30–#68 共 22 筆 pre-flywheel draft）。
- **Reference**: [`work-logs/2026-06/2026-06-06-turbinedetail-render-tests.md`](work-logs/2026-06/2026-06-06-turbinedetail-render-tests.md)

### WMOM-20260606-04 — MaterialRequestDetailModal component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-06 完成，同日第四輪）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；領料單狀態機 transition modal，WorkOrderDetailModal 姊妹元件，先前無任何測試覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-06 第四輪)
- **Completion summary**:
  - ✅ **`components/workflow/__tests__/MaterialRequestDetailModal.test.tsx`（新，42 tests，純測試零 production 變更）**：為 `MaterialRequestDetailModal.tsx`（902 行）補 component render 測試。本元件是 `/admin/workflow` 領料單詳情 + 狀態機 transition 控制 modal：依 `materialRequest.status` 顯示對應 footer action（submit_for_approval / dispatch / receive / close / cancel / createReturn），點按開 collapsible inline form 收必填欄位 → 呼對應 callback → 成功 patch 本地 MR + 收 form / 失敗回填錯誤卡；receive form 自動以 estimated_qty 預填 + 提交前驗證非負整數；return form 組裝 `CreateMaterialReturnPayload`。是前一輪 WorkOrderDetailModal（PR #90）的姊妹 detail modal。
  - ✅ **Mock 策略**：本元件不打 fetch、不依賴自訂資料 hook；依賴僅 `useTheme`（ThemeProvider）+ `useCurrentUser`（UserProvider）→ render wrapper 雙層包裹；6 個 transition callback 由 prop 傳入；`beforeEach` 清 localStorage 讓 UserProvider fallback 到 DEFAULT_USER（Alice Chen），各 transition 的 actor_id / returned_by fallback 斷言用 `DEFAULT_USER.id`。`makeItem` / `makeMR` 工廠結構式滿足型別（不用 `as`）；`resolveWith(base,patch)` 產回傳帶 status 變化 mock 驗成功後本地狀態更新。
  - ✅ **覆蓋契約**：殼層/靜態（dialog aria-label·h2 標題·business_key·status pill·關聯工單尾碼有 vs 無·timeline grid Asia/Taipei +8 格式 vs 未發生 dash·items table 有值 vs 缺漏 fallback `…item_id.slice(-12)`·(料件已不在主檔)·actual_qty 有值·cancel_reason 卡·reject_reason 卡·lang=en）/ status-driven 9 態（draft·awaiting_approval·approved·dispatched·received·used·closed·cancelled·rejected）/ submit·dispatch·close 確認流程（開→確認→callback(id,actor)·成功狀態更新·form open footer 鎖定·失敗錯誤卡不收合·submitting 中態 disabled·form 取消不呼）/ cancel（空·純空白 disabled·填→trim）/ receive（預填 estimated_qty·編輯·負數·空 NaN 驗證錯誤不呼·0 合法·多 item record）/ return（未選 disabled·payload trim·數量<1 disabled·空 note→null·失敗錯誤卡）/ 關閉路徑（backdrop·stopPropagation·footer Close·header ✕·lang=en）。
  - ✅ **實作眉角**：① 與 WorkOrderDetailModal 不同，本元件 footer 開啟鈕與 form 提交鈕 aria-label 互不相同（footer「派發」vs form「確認派發」）→ 多數直接 getByRole，**不需** formSubmit parentElement scope helper；② 唯一重複「關閉」（header ✕ + footer Close）→ `footerClose()` 以 getAllByRole 取最後一個（footer）、header ✕ 取第一個；③ `…${slice}` fallback 因「…」與 slice 屬不同 text node → 斷言改 substring regex；④ submitting 中態以受控 Promise 斷言中間態 + 收尾 `act(resolve)` 收 form 避免 act 警告。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **525 passed**（481 baseline + 44 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：`TurbineDetail`（1056，monitoring 大元件，需 mock 即時資料）；detail modal 系列（WorkOrder / MaterialRequest）已覆蓋完畢。非 render 方向 M5-2 ChromaDB（需劉老師拍板 chromadb 依賴 + 向量檔來源）/ stale PR triage（#30–#68 共 22 筆 pre-flywheel draft）。
- **Reference**: [`work-logs/2026-06/2026-06-06-materialrequestdetailmodal-render-tests.md`](work-logs/2026-06/2026-06-06-materialrequestdetailmodal-render-tests.md)

### WMOM-20260606-03 — WorkOrderDetailModal component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-06 完成，同日第三輪）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；工單狀態機 transition modal，detail modal 系列第一個，先前無任何測試覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-06 第三輪)
- **Completion summary**:
  - ✅ **`components/workflow/__tests__/WorkOrderDetailModal.test.tsx`（新，42 tests）**：為 `WorkOrderDetailModal.tsx`（933 行）補 component render 測試。本元件是 `/admin/workflow` 工單詳情 + 狀態機 transition 控制 modal：依 `work_order.status` 顯示對應 action 按鈕（draft→派工 / dispatched→開始作業 / in_progress→新增進度·完工 / awaiting_signoff→駁回 / closed→重開 + cancel 規則），點按開 collapsible inline form 收必填欄位 → 呼對應 callback（7 個 transition：dispatch/start_work/progress/finish/reject/cancel/reopen）→ 成功 patch 本地 WO + 收 form、失敗回填錯誤卡，含 offshore farm start_work 強制 weather_window_id 分支。是前份 handoff 點名的「detail modal」系列第一個。
  - ✅ **Mock 策略**：本元件不打 fetch、不依賴自訂資料 hook；依賴僅 `useTheme`（ThemeProvider）+ `useCurrentUser`（UserProvider）→ render wrapper 雙層包裹；7 個 transition callback 由 prop 傳入全部 `vi.fn().mockResolvedValue(makeWO(...))`；`beforeEach` 清 localStorage 讓 UserProvider fallback 到 DEFAULT_USER（Alice Chen）使 dispatch assignee fallback 斷言穩定。`makeWO` 工廠結構式滿足 `WorkOrderResponse`（不用 `as`，overrides 末尾 spread）；`resolveWith(base,patch)` 產「回傳同單帶 status 變化」mock 驗成功後本地狀態更新。
  - ✅ **覆蓋契約**：殼層/靜態（dialog aria-label·h2 標題·business_key·turbine·typeLabel·detail grid 有值 vs —·source alarm —·description·progress_notes 空不渲染 vs 有值計數+內容·完工摘要 closed·cancel/reject/reopen 原因卡·awaiting_signoff 待簽核提示·lang=en）/ status-driven 按鈕可見性（draft·dispatched·in_progress·awaiting_signoff 無取消·closed·reopened 6 態）/ dispatch form（空 assignee→fallback currentUser.id·已有 assignee 留空→既有·輸入 trim·成功本地狀態更新「已派工」·失敗錯誤卡且 form 不收合·submitting「派工中…」disabled）/ start_work form（onshore→onStartWork(id,false)·offshore 空 weather window Start disabled·填值→(id,true,wwid) trim）/ progress·finish（progress 空 disabled·填→onUpdateProgress trim·finish 空工時驗證錯誤不呼·填→onFinish 完整 payload trim·null 空值·followup_needed→額外欄位）/ reject·cancel·reopen（各空 reason disabled·填→對應 callback(id,reason)）/ 關閉路徑（backdrop→onClose·content stopPropagation 不關·footer Close→onClose）。
  - ✅ **實作眉角**：① 多個 footer 開啟按鈕與 form 提交按鈕 **aria-label 同字串**（駁回/開始作業/重開/取消工單）→ getByRole 多重命中 → 抽 `formSubmit(cancelName,submitName)` helper，以 form 內唯一 Cancel/返回 鈕的 `parentElement` 同層容器 `within(...)` scope 提交鈕；② footer Close 與 header ✕ 皆 aria-label「關閉」→ `getAllByRole` 取最後一個；③ submitting 中態以受控 Promise（手動 resolve）斷言中間態 + 收尾 `act(resolve)` 讓 form 收合避免 act 警告。
  - 🔧 **附帶 production 修正**（review must-fix）：finish 驗證 `!actualHours` → `!actualHours.trim()`，避免「只敲空白」的 `actual_hours` 被 `Number('   ')=0` 當成 0 工時靜默送出（與全 codebase 其他欄位 `.trim()` 慣例一致），補純空白 regression test。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **481 passed**（439 baseline + 42 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：`MaterialRequestDetailModal`（902，另一 detail modal，需 mock 多 action callback + 狀態機 tab）/ `TurbineDetail`（1056）；非 render 方向 M5-2 ChromaDB（需劉老師拍板 chromadb 依賴 + 向量檔來源）/ stale PR triage（#30–#68 共 22 筆 pre-flywheel draft）。
- **Reference**: [`work-logs/2026-06/2026-06-06-workorderdetailmodal-render-tests.md`](work-logs/2026-06/2026-06-06-workorderdetailmodal-render-tests.md)

---

### WMOM-20260606-02 — CreateMaterialRequestWizard component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-06 完成，同日第二輪）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；領料單 tab「建立領料單」3 步精靈，本系列第二個多步驟 wizard，首次需 mock 自訂 hook + cart 增刪 + confirm 守門關閉，先前無任何測試覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-06 第二輪)
- **Completion summary**:
  - ✅ **`components/workflow/__tests__/CreateMaterialRequestWizard.test.tsx`（新，41 tests）**：為 `CreateMaterialRequestWizard.tsx`（690 行）補 component render 測試。本元件是 `/admin/workflow` 領料單 tab 的「建立領料單」3 步精靈（Step 1 選關聯工單 → Step 2 左右 split 料件 picker + cart → Step 3 檢閱 + 送出）。是本系列第二個多步驟 wizard，**首次引入需 mock 自訂 hook（`useInventoryItems`，async picker 來源）** + cart 增刪同步 availableItems + `window.confirm` 守門的 backdrop 關閉路徑。以 `vi.hoisted` + `vi.mock` 注入可控 inventory 狀態（items/loading/error/refresh），`beforeEach` 重設預設 items 並重建 refresh spy；render wrapper 僅需 ThemeProvider（不依賴 useCurrentUser，requesterId 由 prop 傳入）。`makeItem/makeWorkOrder` 工廠結構式滿足型別（不用 `as`）。
  - ✅ **覆蓋契約**：殼層（dialog aria-label + h2 標題 zh/en 不外洩中文 / step indicator「第 N 步 / 共 3 步」/ footer 鈕各 step 出現規則）/ Step 1（「不關聯工單」預設選中·closed/cancelled filter·business_key 降冪排序·空清單提示卡 zh/en·preselectWorkOrderId 預選·點工單卡 aria-pressed 切換·Step 1 Next 無 gating）/ Step 2（進入呼 inv.refresh·清單 sku/name/N·U·R 庫存·below_safety→Low pill·loading/empty/error 態·加入移到 cart 並從左側消失·移除回左·qty 夾限 min 1·stock kind 三選項·canNext2 gating·Back）/ Step 3（summary 反映工單 business_key·無關聯→（無）·料件數·每行 sku·name×qty unit·庫存類型）/ 送出（buildRequest 序列化：farm_id·requester_id·無關聯→work_order_id null·items·qty/stock_kind 修改反映·submitting 中態「建立中…」+disabled·reject→⚠ 錯誤卡+不 onClose+鈕回復）/ 關閉路徑（✕·取消直呼 onClose 不彈 confirm·遮罩空 cart 直接關·遮罩有 cart 走 window.confirm OK→關 / Cancel→不關·content stopPropagation 不關）。
  - ✅ **實作眉角**：① 送出鈕 accessible name 恆為 aria-label「建立領料單」→ submitting 中態以 `findByText('建立中…').closest('button')` 驗；② backdrop 守門以 `vi.spyOn(window,'confirm')` 控回傳；③ ✕/取消鈕綁 `onClose` 直呼（非 handleBackdropClick）→ 即使 cart 有料件也不彈 confirm，為獨立契約測試。
  - ⚠️ **踩雷（已修）**：`makeWorkOrder` 初版結尾漏 `...overrides` spread → 所有 work order fall back 成 default（WO-2026-001），導致 5 個依賴多工單區分的 test 失敗；`tsc` 不報錯（overrides 僅未用 param）。靠「降冪排序」value-discriminating test 抓出。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **438 passed**（398 baseline + 41 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：detail modal（WorkOrderDetailModal 933 / MaterialRequestDetailModal 902，需 mock 多 action callback + 狀態機 tab）/ TurbineDetail（1056）；非 render 方向 M5-2 ChromaDB（需劉老師拍板 chromadb 依賴 + 向量檔來源）/ stale PR triage（#30–#68 共 22 筆 pre-flywheel draft）。
- **Reference**: [`work-logs/2026-06/2026-06-06-creatematerialrequestwizard-render-tests.md`](work-logs/2026-06/2026-06-06-creatematerialrequestwizard-render-tests.md)

---

### WMOM-20260606-01 — CreateWorkOrderWizard component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-06 完成）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；工單 tab「建立工單」3 步精靈，本系列首個多步驟 wizard 形態，先前無任何測試覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-06)
- **Completion summary**:
  - ✅ **`components/workflow/__tests__/CreateWorkOrderWizard.test.tsx`（新，32 tests）**：為 `CreateWorkOrderWizard.tsx`（466 行）補 component render 測試。本元件是 `/admin/workflow` 工單 tab 的「建立工單」3 步精靈（Step 1 選風機 → Step 2 工單細節 → Step 3 派工+工時 → 送出），是四個未測 workflow 元件中**最小最自包含**（不依賴 useCurrentUser，僅需 ThemeProvider），引入本系列尚未覆蓋的**多步驟 wizard 形態**（step machine + 逐步 gating + buildRequest 序列化 + async 送出）。`makeTurbine` 工廠結構式滿足 `TurbineData`（不用 `as`）；`selectTurbine/gotoStep2/gotoStep3` 步驟導覽 helper。
  - ✅ **覆蓋契約**：殼層（dialog aria-label + h2 標題 zh/en 不外洩中文 / step indicator「第 N 步 / 共 3 步」vs「Step N of 3」/ footer 鈕在各 step 出現規則）/ Step 1（空列表提示卡 zh/en·name localeCompare 排序·FAULT ⚠ 有無·功率風速 toFixed·未選 Next disabled→選後啟用+aria-pressed·preselectTurbineId 預選解鎖）/ Step 2（欄位齊備+step indicator 更新·title|description gating 任一空 disabled+純空白 trim 後不算·Back 回 Step 1 保留已選風機·type/priority Select 完整選項）/ Step 3（派工欄位+建立鈕無下一步·summary 卡反映風機·類型·標題·crew_size 夾限 >20→20·<1→1）/ 送出（完整 request：trim 值+空選填送 null+estimated_hours `Number` 轉型·estimated_hours 空→null+source_alarm_code·assignee trim 值·submitting 中態文字「建立中…」+disabled·onSubmit reject→⚠ 錯誤卡+不 onClose+鈕回復可按）/ 關閉路徑（遮罩·✕·取消→onClose·content stopPropagation 不 onClose）。
  - ✅ **實作眉角**：① 送出鈕 accessible name 恆為 aria-label「建立工單」（aria-label 蓋過可見文字）→ submitting 中態不能用 `getByRole('button',{name:'建立中…'})`，改 `findByText('建立中…').closest('button')`；② RTL `getByText` 比對元素「直接 text node」串接（getNodeText），summary 類型行 `{typeLabel} ·{StatusPill}` 會被拆成「故障維修 ·」→ 改 `toHaveTextContent` 子字串斷言。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **398 passed**（366 baseline + 32 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：CreateMaterialRequestWizard（690，另一多步驟 wizard）/ detail modal（WorkOrderDetailModal 933 / MaterialRequestDetailModal 902，需 mock 多 callback）/ TurbineDetail（1056）；非 render 方向 M5-2 ChromaDB（需劉老師拍板 chromadb 依賴 + 向量檔來源）/ stale PR triage（#30–#68 共 22 筆 pre-flywheel draft）。
- **Reference**: [`work-logs/2026-06/2026-06-06-createworkorderwizard-render-tests.md`](work-logs/2026-06/2026-06-06-createworkorderwizard-render-tests.md)

---

### WMOM-20260605-08 — InventoryDetailDrawer component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-05 完成）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；庫存料件詳情 drawer，含 async lazy-load lifecycle + 內嵌有狀態 adjust dialog，先前無任何測試覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-05)
- **Completion summary**:
  - ✅ **`components/workflow/__tests__/InventoryDetailDrawer.test.tsx`（新，21 tests）**：為 `InventoryDetailDrawer.tsx`（478 行）補 component render 測試。本元件是庫存頁右側 480px 滑出的料件詳情 drawer（identity / stocks / metadata / audit log），含本系列尚未覆蓋的 **async lifecycle**（mount useEffect → `loadAdjustments(item.id)` → logs/loading/error 三態、Refresh 再拉、adjust 成功 reload）+ **內嵌另一個有狀態 dialog**（`InventoryAdjustmentDialog`，z=300）。render wrapper **同包 ThemeProvider + UserProvider**（內嵌 dialog 依賴 useCurrentUser），`beforeEach` 清 `localStorage`；`settleInitialLoad` helper 集中 await mount lazy load 結算，避免 async setState 洩漏觸發 act 警告。`makeItem/makeLog/makeResult` 工廠結構式滿足型別（不用 `as`）。
  - ✅ **覆蓋契約**：dialog/關閉鈕 aria-label（zh「料件詳情」「關閉抽屜」vs en「Inventory item detail」「Close drawer」不外洩 zh）+ header sku·name / 庫存分項三欄（new/used/repairing label + qty，scope 進「庫存分項」Card 避誤命中 audit row 同 label）/ 可用總計·安全庫存 / below_safety=true→LOW pill·false→無 pill / metadata（unit·unit_cost·warehouse_id 末8碼 `…12345678`·description 空→「（無）」·四時間欄 `fmtDateTime` Asia/Taipei +8 換算驗算）/ audit log（mount 即以 item.id 呼 `loadAdjustments` 一次·空→「尚無異動紀錄。」+ header(0)·有 log→AuditRow `+5 全新`/`-2 良品`+reason+actor 末8碼+計數(2)·note 有無分支·reject→⚠ 錯誤卡且不顯空狀態）/ Refresh 鈕→`loadAdjustments` 再呼(2) / 內嵌 dialog（點「+ 調整庫存」→ 兩 dialog aria-label 並存·送出→`onAdjust` 收 `(item.id, payload)`+成功 reload `loadAdjustments`(2)）/ 關閉路徑（遮罩·✕→onClose；content wrapper + 子孫 stopPropagation 不 onClose）。
  - ✅ **code-reviewer 採納 2 must-fix + 2 should-fix + 1 nice-to-have**：must-fix（① `settleInitialLoad` 語意不完整只等 call 不等 setState flush → 改為再等 Refresh 鈕文案回「重新整理」確保 `setLogsLoading(false)` flush + lang-aware，去 act 洩漏；② below_safety / note 兩 test 單 `it` 內雙 render + cleanup 時序脆弱 → 各拆兩個獨立 `it`）；should-fix（③ `getStockCard` 的 `parentElement` 耦合 Card DOM + within scope 過寬 → 改 `getStockGrid()` 以 `closest('[style*="grid-template-columns"]')` 精確定位三欄、summary 測試改 screen-level；④ fmtDateTime test 補 last_received_at 斷言）；nice-to-have（⑤ error 態補驗 Refresh 鈕回復可按）。**不採納**：must-fix 3（遮罩 test 原碼已先 settle，reviewer 誤判）/ should-fix 3·4 與 nice-to-have 1·3（說明性或既有 test 已正確）。詳見 work-log。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **366 passed**（345 baseline + 21 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：Create*Wizard（多步驟）/ detail modal（WorkOrderDetailModal 933 / MaterialRequestDetailModal 902，需 mock 多 callback）/ TurbineDetail（1056）；非 render 方向 M5-2 ChromaDB（需劉老師拍板 chromadb 依賴 + 向量檔來源）/ stale PR triage（#30–#68 共 22 筆 pre-flywheel draft）。
- **Reference**: [`work-logs/2026-06/2026-06-05-inventorydetaildrawer-render-tests.md`](work-logs/2026-06/2026-06-05-inventorydetaildrawer-render-tests.md)

---

### WMOM-20260605-07 — InventoryAdjustmentDialog component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-05 完成）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；庫存「手動 +/- 調整」對話框，含 useCurrentUser 依賴 + 即時預覽計算 + async 送出，先前無任何測試覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-05)
- **Completion summary**:
  - ✅ **`components/workflow/__tests__/InventoryAdjustmentDialog.test.tsx`（新，23 tests）**：為 `InventoryAdjustmentDialog.tsx`（339 行）補 component render 測試。本元件是庫存頁「手動 +/- 調整」對話框（選 stock kind → 整數異動量允許負 → 必填原因 → 選填備註 → 送出呼 `useInventory.adjust`）。與 ApprovalActionDialog 同屬「有狀態 + async」對話框，但**多 useCurrentUser 依賴**（送出 payload 帶 actor_id）+ **即時預覽計算**（currentQty±delta=next、負庫存 ⚠409 警告）。render wrapper **同包 ThemeProvider + UserProvider**，`beforeEach` 清 `localStorage` 確保 currentUser 落 `DEFAULT_USER`（actor_id 斷言可預測）。`makeItem/makeLog/makeResult` 工廠結構式滿足型別（不用 `as`）；async 送出以受控 Promise + `waitFor` 收尾（無 act 警告）。
  - ✅ **覆蓋契約**：標題/dialog aria-label（zh 同字串「調整庫存」·en `Adjust inventory` vs `Adjust stock` 可區分且不外洩 zh）+ header 副標 sku·name / 三欄回顧（new/used/repairing label scope 進 grid 避誤命中 + qty）/ delta 預覽（new+1·負號·切 kind 改 currentQty·無效 0/NaN→「—」+ 鈕 disabled）/ 扣負數 ⚠409 警告但鈕仍可按（前端只警告交 backend 拒）/ gating（reason 空 disabled·填入 enabled·僅空白 trim 後仍 disabled）/ 送出空備註→`note=undefined`+`actor_id=DEFAULT_USER.id`+成功 `onAdjusted`+`onClose` / 送出換 kind(used)+負 delta(-3)+有備註→payload 反映+note trim / 拋錯→⚠ 回填且**不** onClose 鈕回復可按 / 拋錯後重試成功→舊錯誤卡清除（守 `setError(null)`）/ submitting 中→「送出中…/Submitting…」+ disabled（zh/en 對稱）/ 關閉路徑（遮罩·✕·取消→onClose；內容 wrapper 本身 + 子孫 stopPropagation 不 onClose）。
  - ✅ **code-reviewer 採納 4 must-fix + 2 should-fix**：must-fix（① `getPreviewCard` 去 `as` 改 null-guard；② 兩 submitting 測試 resolve 後改 await `onClose` 收尾，避免 act 警告洩漏；③ 三欄 grid locator 改 `closest('[style*="grid-template-columns"]')` + instanceof guard，去結構脆弱 + `as`；④ `onAdjusted` 斷言強化為 item.id + log 具體欄位）；should-fix（⑤ 遮罩測試補「overlay=role=dialog 節點」註解；⑥ 補測 `onAdjusted` 省略時送出仍不拋錯，守 optional chain，+1 test）。**不採納**：SF beforeEach 改 setItem（現狀 clear() 正確且簡潔）/ retry 泛型風格 / delta=0 與 NaN「重複」（實走不同分支）/ nice testid（會動產品碼）。詳見 work-log。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **345 passed**（322 baseline + 23 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：InventoryDetailDrawer（478）/ Create*Wizard / detail modal（WorkOrderDetailModal 933 / MaterialRequestDetailModal 902，需 mock dialog）/ TurbineDetail（1056）；非 render 方向 M5-2 ChromaDB（需劉老師拍板 chromadb 依賴 + 向量檔來源）/ stale PR triage（15 筆 pre-flywheel draft）。
- **Reference**: [`work-logs/2026-06/2026-06-05-inventoryadjustmentdialog-render-tests.md`](work-logs/2026-06/2026-06-05-inventoryadjustmentdialog-render-tests.md)

---

### WMOM-20260605-06 — ApprovalActionDialog component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-05 完成）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；簽核流程「最後一哩」對話框，系列首個含 internal state + async 送出的元件，先前無任何測試覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-05)
- **Completion summary**:
  - ✅ **`components/workflow/__tests__/ApprovalActionDialog.test.tsx`（新，24 tests）**：為 `ApprovalActionDialog.tsx`（309 行）補 component render 測試。本元件是 reviewer 從 PendingApprovalPanel 按 通過/駁回 後彈出的確認對話框，與先前覆蓋的三大列表面板 + PendingApprovalPanel（皆純 props）不同——**含 internal state（comment/reason/submitting/error/warning）+ async 送出 + 樂觀關閉 / 錯誤回填**，是 workflow render 測試系列首個「有狀態 + 非同步」元件。`makeStep/makeChain/makePending/makeWO/makeResult` 工廠結構式滿足型別（不用 `as`）；async 送出以受控 Promise + `waitFor` 收尾（無 act 警告）。
  - ✅ **覆蓋契約**：標題/dialog aria-label（mode approve/reject × lang zh/en 含 zh negative leak）/ subject 摘要（workOrder 命中 business_key·turbine·title·priority·status pill·typeLabel，以 `within` scope 精準斷言；vs cache miss fallback subjectTypeLabel·…subjectId8）/ step·chain context（層級 signoffLevelLabel·階段 seq+1/levels.length）/ approve·reject 輸入互斥（簽核備註 Input vs 駁回原因 textarea）/ 送出鈕 gating（approve 恆 enabled·reject reason 空→disabled·僅空白 trim 後仍 disabled）/ 送出 approve（空備註→`onApprove(id,null)`·有備註+workOrder 命中→trim 值·成功 onClose）/ 送出 reject（`onReject(id,reason.trim())`·成功 onClose）/ subject_transition_error→警告卡且**不** onClose 且鈕回復可按 / 送出拋錯→⚠ 回填且**不** onClose 且鈕回復可按 / 拋錯後重試成功→舊錯誤卡清除 / submitting 中→「送出中…/Submitting…」+ disabled（zh/en 對稱防重複送出）/ 關閉路徑（遮罩·✕·取消→onClose；內容 wrapper 本身 + 子孫點擊 stopPropagation 不 onClose）。
  - ✅ **code-reviewer 採納 3 must-fix + 3 should-fix + 1 nice**：must-fix（① en submitting 補 `toBeDisabled`，與 zh 對稱守防重複送出；② stopPropagation 測試改點內容 wrapper 節點本身（最精準），並保留子孫點擊；③ subject_transition_error 後補「鈕回復可按」斷言，半成功狀態使用者可補正）；should-fix（④ 加註 Btn `ariaLabel`→`aria-label` 假設；⑤ 1 個 approve submit 測試改走 workOrder 命中路徑，確認 onClose happy path 與 workOrder 無關；⑥ priority/status 斷言以 `within(summary)` scope 避免誤命中）；nice（⑦ 新增「拋錯→重試成功清除舊錯誤卡」測試，守 `setError(null)` 置於 handleSubmit 開頭的迴歸）。**不採納**：should-fix「工廠抽共用 factories.ts」——會動到已 auto-merged 的 `PendingApprovalPanel.test.tsx`，本 session scope creep，留待專門重構 session。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **322 passed**（298 baseline + 24 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：InventoryAdjustmentDialog（339）/ InventoryDetailDrawer（478）/ Create*Wizard / detail modal（WorkOrderDetailModal 933 / MaterialRequestDetailModal 902，需 mock dialog）/ TurbineDetail（1056）；非 render 方向 M5-2 ChromaDB（需劉老師拍板 chromadb 依賴 + 向量檔來源）/ stale PR triage（22 筆 pre-flywheel draft）。
- **Reference**: [`work-logs/2026-06/2026-06-05-approvalactiondialog-render-tests.md`](work-logs/2026-06/2026-06-05-approvalactiondialog-render-tests.md)

---

### WMOM-20260605-05 — PendingApprovalPanel component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-05 完成）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；`/admin/workflow` 簽核 tab 核心「簽核 signoff」流程主清單，先前無任何測試覆蓋本面板真實渲染）
- **Owner**: Claude (autonomous worker, session 2026-06-05)
- **Completion summary**:
  - ✅ **`components/workflow/__tests__/PendingApprovalPanel.test.tsx`（新，27 tests）**：延續 WorkOrder/MaterialRequest/Inventory 三大列表面板已落地的 render 測試範式（ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup），為 `PendingApprovalPanel.tsx`（270 行）補 component render 測試。本面板為簽核流程主清單（員工/組長/主管/總務各層看「輪到我簽的步驟」按 通過/駁回），與三大列表面板同構之純 props 元件（`items`/`total`/`loading`/`error`/`level`/`subjectType`/`workOrderCache` + 5 callback + `lang`），**無 hook / 無 fetch / 無 internal state** → 測試直接 render + fireEvent + 斷言。`makeStep()`/`makeChain()`/`makePending()`/`makeWO()` 工廠結構式滿足 `SignoffStepResponse`/`SignoffChainResponse`/`PendingSignoffItem`/`WorkOrderResponse`（不用 `as` 強轉）。
  - ✅ **覆蓋契約**：基本渲染 + 語系（zh「我的簽核層級/對象類型/重新整理」+ counter「顯示 1 / 3 筆 組長 待簽」；en「Acting as level/Subject type/Refresh/Showing 1 of 5 pending steps for Supervisor」含 zh negative leak 守住）+ level Select（員工/組長/主管/總務 4 層·value 反映 prop·onChange→onLevelChange）+ subject_type Select（「全部對象」+工單+領料單·value·onChange→onSubjectTypeChange·en 正向 All subjects/Work order/Material request）+ Refresh（onClick→onRefresh·loading→「載入中…」/「Loading…」**且 disabled**·disabled 點擊不觸發）+ counter（N/total+level 標籤）+ error warn card（⚠ + 訊息同節點合一斷言）+ empty 態（zh/en·loading·error 時不顯示）+ row（work_order 命中 cache：business_key·turbine·title·chain progress pill「組長 · 1/2」·priority/status pill·開啟時間時區 2026-06-02 16:30；非工單/cache miss fallback：subjectTypeLabel·…subjectId8 末 8 碼）+ 通過/駁回→onApproveClick/onRejectClick 帶該 pending item·多 row 按鈕順序對齊第 2 列帶第 2 筆。
  - ✅ **外加同型 1 行 production UX bug 修正**：`PendingApprovalPanel.tsx` Refresh `Btn` 漏傳 `loading` prop → 載入中按鈕未 disabled（可重複點擊重複觸發查詢）。補 `loading={loading}` 接上 Btn 既有 `isDisabled = disabled || loading`，與三大列表面板的同型修正一致。**至此 workflow 四大面板（WorkOrder/MaterialRequest/Inventory/PendingApproval）同型 bug 全數修正**。
  - ✅ **code-reviewer 0 must-fix / 採納 3 should-fix + 2 nice**：onChange 測試補 `toHaveBeenCalledTimes(1)`（#1）/ error 兩斷言指向同節點 → 合一為 `getByText(/⚠ 載入待簽失敗（500）/)`（#2）/ fallback row 改精準計數 `.filter(OPTION 排除).toHaveLength(2)`——修正 reviewer 漏算 subject_type Select 的 `<option>`（全域 3 次，row 內 2 次）（#3）/ 補 en 空狀態文案測試 + en 通過/駁回按鈕 aria-label 測試（nice）。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **298 passed**（271 baseline + 27 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：進入 detail modal（WorkOrderDetailModal 933 / MaterialRequestDetailModal 902，互動多需 mock dialog）/ TurbineDetail（1056）；或非 render 方向 M5-2 ChromaDB / stale PR triage。
- **Reference**: [`work-logs/2026-06/2026-06-05-pendingapprovalpanel-render-tests.md`](work-logs/2026-06/2026-06-05-pendingapprovalpanel-render-tests.md)

---

### WMOM-20260605-04 — InventoryListPanel component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-05 完成）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；`/admin/workflow` 庫存 tab 核心「庫存」模組清單，先前無任何測試覆蓋本面板真實渲染）
- **Owner**: Claude (autonomous worker, session 2026-06-05)
- **Completion summary**:
  - ✅ **`components/workflow/__tests__/InventoryListPanel.test.tsx`（新，29 tests）**：延續 WorkOrderListPanel / MaterialRequestListPanel 已落地的 render 測試範式（ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup），為 `InventoryListPanel.tsx`（286 行）補 component render 測試。本面板與前兩列表面板高度同構之純 props 元件（`items`/`total`/`loading`/`error`/`warehouses`/`warehouseId`/`belowSafetyOnly`/`search` + 5 callback + `lang`），**無 hook / 無 fetch / 無 internal state** → 測試直接 render + fireEvent + 斷言。多了 warehouse Select（★ default 倉前綴）+ below-safety toggle（aria-pressed）兩個過濾控件。`makeItem()`/`makeWarehouse()` 工廠結構式滿足 `InventoryItemResponse`/`WarehouseResponse`（不用 `as` 強轉；`total_available`/`below_safety` computed 欄位以 overrides 明確指定）。
  - ✅ **覆蓋契約**：基本渲染 + 語系（zh「倉別/搜尋（料號 / 名稱）/重新整理」+ counter「顯示 1 / 3 個料件」；en「Warehouse/Search (SKU / name)/Refresh/Showing 1 of 5 inventory items」含 zh negative leak 守住）+ warehouse Select（選項涵蓋「全部倉」+各倉 ★default 前綴·value 反映 prop·onChange→onWarehouseChange）+ below-safety toggle（文案「全部」↔「只顯示低於安全庫存」·aria-pressed 反映·onClick→onBelowSafetyChange 取反值）+ search Input（value+onChange→onSearchChange）+ Refresh（onClick→onRefresh·loading→「載入中…」/「Loading…」**且 disabled**·disabled 點擊不觸發）+ counter（N/total·filter 截斷 2/50）+ error warn card（⚠ + 訊息）+ empty 態（items=[] 顯示·loading·error 時不顯示）+ row（SKU·name·單位·三欄 stock 全新/良品/維修中·安全/可用·LOW pill below_safety 有/無·最後出庫時間 last_used_at 有 2026-06-02 16:30/null 不顯示·aria-label 鎖定）+ 點擊 row→onSelect objectContaining。
  - ✅ **外加同型 1 行 production UX bug 修正**：`InventoryListPanel.tsx` Refresh `Btn` 漏傳 `loading` prop → 載入中按鈕未 disabled（可重複點擊重複觸發查詢）。補 `loading={loading}` 接上 Btn 既有 `isDisabled = disabled || loading`，與 WorkOrderListPanel / MaterialRequestListPanel 的同型修正一致。**至此 workflow 三大列表面板同型 bug 全數修正**。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **271 passed**（242 baseline + 29 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：同範式推 PendingApprovalPanel（270，簽核核心）；或進入 detail modal（WorkOrderDetailModal 933 / MaterialRequestDetailModal 902，互動多需 mock dialog）/ TurbineDetail（1056）。
- **Reference**: [`work-logs/2026-06/2026-06-05-inventorylistpanel-render-tests.md`](work-logs/2026-06/2026-06-05-inventorylistpanel-render-tests.md)

---

### WMOM-20260605-03 — MaterialRequestListPanel component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-05 完成）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；`/admin/workflow` 領料 tab 核心「庫存派工」清單，先前無任何測試覆蓋本面板真實渲染）
- **Owner**: Claude (autonomous worker, session 2026-06-05)
- **Completion summary**:
  - ✅ **`components/workflow/__tests__/MaterialRequestListPanel.test.tsx`（新，22 tests）**：延續 WorkOrderListPanel 已落地的 render 測試範式（ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup），為 `MaterialRequestListPanel.tsx`（203 行）補 component render 測試。本面板與 WorkOrderListPanel 高度同構之純 props 元件（`items`/`total`/`loading`/`error`/`status`/`search` + 4 callback + `lang`），**無 hook / 無 fetch / 無 internal state** → 測試直接 render + fireEvent + 斷言。`makeMR()`/`makeItem()` 工廠結構式滿足 `MaterialRequestResponse`/`MaterialRequestItem`（不用 `as` 強轉）。
  - ✅ **code-reviewer 採納 must-fix 1 + should-fix 3 + nice 1**：`makeItem` JSDoc 補 null join 欄位說明（#2）/ `vitest.config.ts` 加 `process.env.TZ='UTC'` flaky 防護（#3）/ empty-error 斷言改比對訊息文字避免 `getByText(/⚠/)` 多元素脆點（#4）/ 新增「loading disabled 點擊不觸發 onRefresh」行為測試（#5）/ 新增 en status Select 選項 `toEqual` 守 en 拼字（#6）。
  - ✅ **覆蓋契約**：基本渲染 + 語系（zh「狀態/搜尋（領料編號 / 工單）/重新整理」+ counter「顯示 1 / 3 筆領料單」；en「Status/Search (key / work order)/Refresh/Showing 1 of 5 material requests」含 4 個 zh negative leak 守住）+ status filter Select（選項涵蓋「全部狀態」+ 9 status 順序鎖定 MaterialRequestStatusValues·value 反映 prop·onChange→onStatusChange）+ search Input（value+onChange→onSearchChange）+ Refresh（onClick→onRefresh·loading→「載入中…」/「Loading…」**且 disabled**）+ counter（N/total·filter 截斷 2/50）+ error warn card（⚠ + 訊息）+ empty 態（items=[] 顯示·loading·error 時不顯示）+ row（business_key·work_order 連結 有「工單 …{後8碼}」/null「（無關聯工單）」·料件項數+預估總量 reduce·更新於時區 2026-06-02 16:30·狀態 pill·en 單數 item·aria-label 鎖定）+ 點擊 row→onSelect objectContaining。
  - ✅ **外加同型 1 行 production UX bug 修正**：`MaterialRequestListPanel.tsx` Refresh `Btn` 漏傳 `loading` prop → 載入中按鈕未 disabled（可重複點擊重複觸發查詢）。補 `loading={loading}` 接上 Btn 既有 `isDisabled = disabled || loading`，與上個 session 對 WorkOrderListPanel 的同型修正一致。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **242 passed**（220 baseline + 23 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：同範式推 PendingApprovalPanel（270，簽核核心）/ InventoryListPanel（286）/ TurbineDetail（1056）；或較大的 WorkOrderDetailModal（933）/ MaterialRequestDetailModal（902）。
- **Reference**: [`work-logs/2026-06/2026-06-05-materialrequestlistpanel-render-tests.md`](work-logs/2026-06/2026-06-05-materialrequestlistpanel-render-tests.md)

---

### WMOM-20260605-02 — WorkOrderListPanel component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-05 完成）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；`/admin/workflow` 工單 tab 核心「派工」清單，先前僅被 WorkflowPage 測試 mock 成 marker、真實渲染零覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-05)
- **Completion summary**:
  - ✅ **`components/workflow/__tests__/WorkOrderListPanel.test.tsx`（新，20 tests）**：延續 CostPage / HistoryPage / WorkflowPage 已落地的 render 測試範式（ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup），為 `WorkOrderListPanel.tsx`（221 行）補 component render 測試。本面板為純 props 元件（`items`/`total`/`loading`/`error`/`status`/`search` + 4 callback + `lang`），**無 hook / 無 fetch / 無 internal state** → 測試直接 render + fireEvent + 斷言，不需 stub global.fetch / async act。`makeWO()` 工廠結構式滿足 `WorkOrderResponse`（不用 `as` 強轉）。
  - ✅ **覆蓋契約**：基本渲染 + 語系（zh「狀態/搜尋（編號 / 標題 / 風機）/重新整理」+ counter「顯示 1 / 3 筆工單」；en「Status/Search (key / title / turbine)/Refresh/Showing 1 of 5 work orders」含 4 個 zh negative leak 守住）+ status filter Select（選項涵蓋「全部狀態」+ 7 status 順序鎖定 WorkOrderStatusValues·value 反映 prop·onChange→onStatusChange）+ search Input（value+onChange→onSearchChange）+ Refresh（onClick→onRefresh·loading→「載入中…」/「Loading…」**且 disabled**）+ counter（N/total·filter 截斷 2/50）+ error warn card（⚠ + 訊息）+ empty 態（items=[] 顯示·loading·error 時不顯示）+ row（business_key·turbine·typeLabel·title·更新於時區 2026-06-02 16:30·預估工時 null 不顯示·優先級+狀態 pill·aria-label 鎖定）+ 點擊 row→onSelect objectContaining。
  - ✅ **外加 review must-fix #1 修 1 行 production UX bug**：`WorkOrderListPanel.tsx:105` Refresh `Btn` 漏傳 `loading` prop → 載入中按鈕未 disabled（可重複點擊重複觸發查詢）。補 `loading={loading}` 接上 Btn 既有 `isDisabled = disabled || loading`。
  - ✅ **Verify**：`tsc` 0 error + `vitest` **220 passed**（200 baseline + 20 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：同範式推 PendingApprovalPanel（270，簽核核心）/ MaterialRequestListPanel（203，與本面板同構）/ InventoryListPanel（286）/ TurbineDetail（1056）；或較大的 WorkOrderDetailModal（933）/ MaterialRequestDetailModal（902）。
- **Reference**: [`work-logs/2026-06/2026-06-05-workorderlistpanel-render-tests.md`](work-logs/2026-06/2026-06-05-workorderlistpanel-render-tests.md)

---

### WMOM-20260605-01 — HistoryPage component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-05 完成）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；`/admin/history` SCADA 歷史查詢 + 事件標記 + CSV 匯出 demo 主畫面，先前頁面層零覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-05)
- **Completion summary**:
  - ✅ **`components/__tests__/HistoryPage.test.tsx`（新，21 tests）**：延續 CostPage / FarmOverview / SettingsPage 已落地的 render 測試範式（ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup + `global.fetch` stub + `await act(async)` flush mount effect），為 `/admin/history`（`components/HistoryPage.tsx`，809 行）補第一批 component render 測試。HistoryPage 純 props（`turbines` / `lang`）+ 兩條 fetch（`/api/i18n/tags`、`/api/turbines/:id/history`）驅動；唯一重子元件 `EventComparisonView`（compare tab）mock 成 sentinel；recharts 圖表在 jsdom width=0 不渲染內部但不 crash → 斷言聚焦非圖表 UI。
  - ✅ **覆蓋契約**：基本渲染 + 語系（zh「歷史資料」+ CSV 按鈕「匯出區間/匯出聚焦」+ tab「單機歷史/多機比較」；en「History」/「Single turbine」/「Multi compare」/「Latest 20 rows」含 negative 守 zh 不外洩；en→i18n GET 帶 `lang=en`）+ 單機/比較 tab 切換（aria-pressed + 點「多機比較」掛 EventComparisonView + single 查詢卡消失）+ 查詢卡（風機 Select options 由 turbines props 生成 / mount 即 fetch WT001 / 切風機·筆數 Select→重新 fetch 帶新 id·limit）+ 歷史資料表（數值 toFixed(2) + 缺值「—」+ 表頭 startup 標籤）+ 事件清單（button role 鎖定避開詳情 div 同名）→詳情（detail + payload temp）+ 空事件 warn +「請從左側選擇事件。」+ 事件類型 toggle 過濾（關「故障」→ 故障事件消失·grid 仍在）+ 事件搜尋（關鍵字過濾）+ 標籤切換（預設 thermal→重新 fetch+表頭換 thermal 標籤·startup 消失；自訂套用→activeTags 換值）+ CSV 匯出（window.open 帶 `/api/export/history?...format=csv&turbine_id=WT001`）+ i18n 標籤對映（i18n 回 `{WTUR_TurSt:'渦輪狀態'}`→表頭顯示中文）。
  - ✅ **mock 策略**：`makeTurbine`/`makeHistoryPayload` 工廠結構式滿足型別（不用 `as` 強轉）；`global.fetch` stub 路由 i18n/tags + history，未預期 URL `reject('Unexpected fetch')` 不靜默吞；`window.open` 以 spy 取代（jsdom 未實作）；`tagLabels` per-test 覆寫（`beforeEach` reset），無跨測試殘留；HistoryPage 無 module-level 可變快取依賴 → 測試彼此獨立、`--randomize` 安全。
  - ✅ **零 production 程式改動**。**Verify**：`tsc` 0 error + `vitest` **200 passed**（179 baseline + 21 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：同範式推 TurbineDetail（1056）/ workflow 子面板（WorkOrderListPanel / PendingApprovalPanel 等 panel 級互動）；或補 HistoryPage focus window 深度斷言 / EventComparisonView 獨立測試。
- **Reference**: [`work-logs/2026-06/2026-06-05-historypage-render-tests.md`](work-logs/2026-06/2026-06-05-historypage-render-tests.md)

---

### WMOM-20260604-06 — SettingsPage component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-04 完成）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；`/admin/settings` 切資料源 / 風況電網覆寫 / 套機型規格 demo 操作面板，先前頁面層零覆蓋）
- **Owner**: Claude (autonomous worker, session 2026-06-04)
- **Completion summary**:
  - ✅ **`components/__tests__/SettingsPage.test.tsx`（新，17 tests）**：延續 CostPage / FarmOverview 已落地的 render 測試範式（ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup + `global.fetch` stub + `await act(async)` flush mount effect），為 `/admin/settings`（`components/SettingsPage.tsx`，781 行）補第一批 component render 測試。SettingsPage 純 props（`settings` / `onSave` / `lang`）+ fetch 驅動、**無 stateful hook 依賴**，ui primitive（Btn / Card / Field / Input / Select / PageHeader / StatusPill）真渲染，僅 stub `global.fetch`。
  - ✅ **覆蓋契約**：基本渲染 + 語系（zh「系統設定」/ en「Settings」+ Save 按鈕，含 negative 守 u() 映射未對調）+ dataSource 驅動條件區塊（MOCK→無模擬/OPC/Modbus；SIMULATION→模擬參數+風機規格+風況控制+電網控制；OPC_DA→含 ProgID；MODBUS_TCP→IP/埠號/Slave ID）+ Select 切換接線（MOCK→SIMULATION 即時出現模擬區塊）+ settings prop 同步（rerender→useEffect [settings]→setFormData）+ Save（type=submit）→ `onSave` 帶 formData +「已儲存」pill + backend down（wind GET reject→「無法連線到後端 API」warn card）+ wind status 顯示 + wind profile 按鈕（POST /api/config/wind {profile} + aria-pressed）+ custom wind 套用（POST 帶解析後數值 body）+ grid profile 按鈕（POST /api/config/grid）+ turbine spec presets 渲染 + apply spec（POST /api/config/turbine-spec 帶 editSpec payload）。
  - ✅ **mock 策略**：`makeSettings(dataSource)` 工廠結構式滿足 `AppSettings`（不用 `as` 強轉，欄位漂移 tsc 即失敗）；`global.fetch` stub 路由 4 GET config endpoint（presets 先於 turbine-spec 判斷避免超字串誤命中）+ 3 POST（turbine-spec 回 `{spec}`、wind/grid 回 ok），未預期 URL/method `reject('Unexpected fetch')` 不靜默吞；POST 斷言以 method 過濾 `fetchMock.mock.calls` 取 body，避開 mount 多次 GET。
  - ✅ **零 production 程式改動**。**Verify**：`tsc` 0 error + `vitest` **179 passed**（162 baseline + 17 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：同範式推 HistoryPage（809）/ TurbineDetail（1056）/ workflow 子面板（WorkOrderListPanel / PendingApprovalPanel 等 panel 級互動）。
- **Reference**: [`work-logs/2026-06/2026-06-04-settingspage-render-tests.md`](work-logs/2026-06/2026-06-04-settingspage-render-tests.md)

---

### WMOM-20260604-05 — WorkflowPage component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-04 完成）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；核心 workflow 模組主入口、商業價值最高；前四個同日 session handoff 背書「同範式續推 workflow 各 panel」）
- **Owner**: Claude (autonomous worker, session 2026-06-04)
- **Completion summary**:
  - ✅ **`components/workflow/__tests__/WorkflowPage.test.tsx`（新，21 tests）**：延續 FieldPage / ReportsPage / CostPage / FarmOverview 已落地的 render 測試範式（mock hook + 子元件 marker mock + ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup + async act flush），為核心「庫存派工簽核」模組主入口（`components/workflow/WorkflowPage.tsx`，502 行）補第一批 component render 測試（先前 workflow 目錄僅 `statusUtils` helper 測試、頁面層零覆蓋）。
  - ✅ **覆蓋契約**：active farm 載入三態（載入中 farmId null →「載入風場中…」/ fetch 失敗 → warn card「無法載入目前風場：」/ 成功 → header 風場名 + currentUser.name + 預設工單 tab）+ 四 tab 切換（工單 / 領料單 / 庫存 / 簽核）面板互斥 + aria-pressed 翻轉 + Create 按鈕依 tab（orders→建立工單 / material→建立領料單 / inventory·approval→無）+ 簽核 pending 徽章（total>0 顯示·=0 不顯示）+ 子面板 props wiring（total/loading/error 攤平斷言）+ row 點選開 4 種 modal·drawer（WorkOrderDetailModal / MaterialRequestDetailModal / InventoryDetailDrawer / ApprovalActionDialog）+ 建立 wizard onSubmit → `wo.create` 帶正確 req 接線 + 語系 en（tab/create aria-label 英文）。
  - ✅ **mock 策略**：5 個 stateful hook（useWorkOrders / useMaterialRequests / useInventory / usePendingApprovals / useCurrentUser）全 mock，`makeWO`/`makeMR`/`makeInv`/`makeApprovals` 結構式完整實作 `UseXxxResult` 介面（不用 `as` 強轉，欄位/簽章漂移 tsc 即失敗）；11 個子面板/wizard/modal 以輕量 marker 取代（攤平關鍵 props 到 data-* + 提供觸發回呼按鈕）；`global.fetch` stub 路由 `/api/farms`（未預期 URL reject 不靜默吞）；fixtures（makeWorkOrder / makeMaterialRequest / makeInventoryItem / makePending）全列必填欄位、enum 字面量 union 嚴格對齊 service signature。
  - ✅ **零 production 程式改動**。**Verify**：`tsc` 0 error + `vitest` **162 passed**（141 baseline + 21 新，零 regression、`--sequence.shuffle` 亦綠）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：同範式推 SettingsPage（781）/ HistoryPage（809）/ TurbineDetail（1056）/ workflow 子面板（WorkOrderListPanel / PendingApprovalPanel 等 panel 級互動）。
- **Reference**: [`work-logs/2026-06/2026-06-04-workflowpage-render-tests.md`](work-logs/2026-06/2026-06-04-workflowpage-render-tests.md)

---

### WMOM-20260604-04 — FarmOverview component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-04 完成）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；前三個同日 session handoff 背書「同範式續推 FarmOverview」）
- **Owner**: Claude (autonomous worker, session 2026-06-04 late-night2)
- **Completion summary**:
  - ✅ **`components/__tests__/FarmOverview.test.tsx`（新，18 tests）**：延續 FieldPage / ReportsPage / CostPage 已落地的 render 測試範式（ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup + async act flush），為 `/admin` 風場總覽落地頁（730 行）補第一批 component render 測試。
  - ✅ **覆蓋契約**：PageHeader（zh/en 標題 + `dataSource=MOCK` 才顯 MOCK 徽章）+ HeroStats KPI 計算（風場功率加總 / 平均風速 / 運轉計數「全部健康·狀態混合」/ 故障「請關注·一切順利」）+ cards·summary·table 三檢視切換 + aria-pressed + summary fmtPower（<1 MW → kW）+ table 欄位 toFixed·缺值 cell「—」+ 點卡片/點 row → onSelectTurbine 帶正確 turbine + TrendCard（預設 24H aria-pressed + mount 觸發 `farm-trend?range=1d` + 切 6H→`range=12h` + 切 7D→`range=1d`（守後端只支援至 1d 的刻意 cap）+ 收集中/有資料兩態）+ 語系 en 表頭。
  - ✅ **mock 策略**：純由 props（turbines / settings / lang）驅動，`makeTurbine` 工廠全列核心必填欄位不用 `as` 強轉（tsc 守住與 types.ts 對齊）；`global.fetch` 以 `vi.stubGlobal` 路由 farm-trend（未預期 URL reject 不靜默吞）；`jsonResponse` 含 ok/status；`flushAsync`（setTimeout 0）drain 多層 fetch chain。
  - ✅ **code review 7 must-fix**：採納 4（① 模組級 `_trendCache` 順序污染 → 改「有資料」測試先空 mount 再切 6H 隔離，`--sequence.shuffle` 佐證順序無關；② jsonResponse 補 ok/status；③ '—' 改 cell-specific 斷言；④ flushAsync drain 多 tick + 補 6H fetch 接線測試）；駁回 1 false-positive（reviewer 誤判 `RANGE_TO_API['7D']='1d'` 為 bug — 實查 `modules/monitoring/server/routers/turbines.py` 後端 farm-trend 只接受 5m/1h/12h/1d，改 '7d' 會 fallback 成 5m 而壞掉 → 改加測試守住刻意 cap）；其餘記錄理由（getByText 對歧義是大聲失敗非假綠 / 需動 production testid / 低 ROI 邊界）。
  - ✅ **零 production 程式改動**。**Verify**：`tsc` 0 error + `vitest` **141 passed**（123 baseline + 18 新，零 regression、`--sequence.shuffle` 亦綠）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **給劉老師小問題**：總覽趨勢圖「7D」時段實際只拉最近 1 天（前端 `RANGE_TO_API['7D']='1d'`，後端無 7d range）。若預期則 UI 標示待修；若應顯 7 天需開後端 issue 加 7d range + SQLite 查詢。
- **下次續做**：同範式推 SettingsPage（781 行）/ HistoryPage（809）/ workflow 各 panel（`components/workflow/` 11 元件，僅 statusUtils helper test）。
- **Reference**: [`work-logs/2026-06/2026-06-04-farmoverview-render-tests.md`](work-logs/2026-06/2026-06-04-farmoverview-render-tests.md)

---

### WMOM-20260604-03 — CostPage component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-04 完成）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；前兩個同日 session handoff 背書「同範式續推 CostPage」）
- **Owner**: Claude (autonomous worker, session 2026-06-04 late-night)
- **Completion summary**:
  - ✅ **`components/__tests__/CostPage.test.tsx`（新，15 tests）**：延續 FieldPage / ReportsPage 已落地的 render 測試範式（mock hook + ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup），為 `/admin/cost` 成本模型主入口（784 行）補第一批 component render 測試。
  - ✅ **覆蓋契約**：mount 自動接線（dataset effect 觸發 `forecast.run({dataset})` + `lcoe/monteCarlo/varFluct.reset()`）+ dataset 切換（選 farm → forecast.run 帶新 dataset + 其他 reset）+ farms 載入（`/api/farms` resolve → selector 出現 farm 選項）+ Run scenario 全跑（4 endpoint 帶正確 params）+ 各 panel run 接線（Forecast / LCOE 帶 capex·discount / MonteCarlo 帶 nSim·seed / VarFluct）+ loading·error 態（按鈕 disabled + 計算中… / ErrorBox）+ KPI strip 格式化（data present 正確 fmtMoney·LCOE 兩位小數；無資料「—」）+ DatasetMetaBadge + 語系 en。
  - ✅ **mock 策略**：`useCostData` hook 控 4 個 AsyncState（data/loading/error/run/reset spy）、`recharts` 輕量 stub 成 marker div（避免 jsdom 0-width 圖表噪音 + data-present 渲染穩定）、`global.fetch` 依 URL 路由 `/api/farms`·`/api/i18n`（零真連線）；`Slice<T>` / fixtures 工廠全列欄位不用 `as` 強轉（tsc 守住與 costService signature 對齊）。
  - ✅ **零 production 程式改動**。**Verify**：`tsc` 0 error + `vitest` **123 passed**（108 baseline + 15 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：同範式推 FarmOverview（730 行）/ SettingsPage（781）/ HistoryPage（809）/ workflow 各頁 component 測試。
- **Reference**: [`work-logs/2026-06/2026-06-04-costpage-render-tests.md`](work-logs/2026-06/2026-06-04-costpage-render-tests.md)

---

### WMOM-20260604-02 — ReportsPage component render 測試（EPIC-M5 測試覆蓋擴大）

- **Status**: done（2026-06-04 完成）
- **Milestone**: M5（測試覆蓋持續工作）
- **Priority**: medium（regression 防護網；前次 handoff 建議 #1 明確背書）
- **Owner**: Claude (autonomous worker, session 2026-06-04 night)
- **Completion summary**:
  - ✅ **`components/reporting/__tests__/ReportsPage.test.tsx`（新，11 tests）**：延續 FieldPage 已落地的 render 測試範式（mock hook + ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup），為 `/admin/reports` 主入口補第一批 component render 測試。
  - ✅ **覆蓋契約**：active farm 載入四態（載入中 / fetch 失敗剝技術前綴 / 無啟用風場引導 / 成功）+ tab 切換（月報 ⇄ 年度預算 + aria-pressed 翻轉）+ 子面板 props wiring（farmId / farmName / lang）+ onGenerate 接線（子面板觸發 → 帶 active `farm_id` 呼叫 `generateMonthly` / `generateAnnual`）+ 語系 en。
  - ✅ **mock 策略**：`farmApi.list` 控 active farm 載入態、`useReports` hook 控兩條 sub-state + 四個 action spy、兩個重量級子面板（MonthlyReportPanel / AnnualBudgetPanel 各 350+ 行）輕量 mock 成 marker div + 攤平 props 到 `data-*`，讓測試聚焦 ReportsPage 路由 / 接線；`makeReports` 六欄全列不用 `as` 強轉（tsc 守住與 hook signature 對齊）。
  - ✅ **零 production 程式改動**。**Verify**：`tsc` 0 error + `vitest` **108 passed**（97 baseline + 11 新，零 regression）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **下次續做**：同範式推 CostPage（784 行）/ FarmOverview（730 行）/ workflow 各頁 component 測試。
- **Reference**: [`work-logs/2026-06/2026-06-04-reportspage-render-tests.md`](work-logs/2026-06/2026-06-04-reportspage-render-tests.md)

---

### WMOM-20260603-04 — `/field/` 警報檢索模式（EPIC-M5 M5-5 Part B-1，killer feature）

- **Status**: done（2026-06-03 完成）
- **Milestone**: M5
- **Priority**: high（PMF killer feature：警報跳出 → 30 秒看到手冊處置）
- **Owner**: Claude (autonomous worker, session 2026-06-03)
- **Completion summary**:
  - ✅ **`/field/` 新增「警報檢索」模式**（串 Part A 已備好的 `knowledgeService.queryByAlert` → `POST /api/knowledge/alert`）：模擬 SCADA 警報事件（告警碼 / 等級 A·T1·T2 / 機組 / 異常標籤）→ 後端自動構造 query 檢索 top-k 手冊處置段落；結果先顯示警報摘要 + **透明標示「系統據此檢索」**的 auto-built query，再列 chunks。
  - ✅ **`hooks/useKnowledge.ts`**：新增第三條流 `alert`（`runAlert` / `clearAlert`），用**獨立** `alertReqRef` 單調遞增序號做 race 防護，與既有 `search` 流（`reqRef`）完全隔離。
  - ✅ **`components/field/FieldPage.tsx`**：重構為 `ModeToggle`（segmented，`aria-pressed`）+ `QueryMode`（Part A 抽出）+ `AlertMode`（新）+ 共用 `ResultList`/`ResultCard`；`timestamp` 用 `new Date().toISOString()` 避免 naive datetime 被 schema validator 擋 422（CLAUDE.md §B）；全走 ui 元件庫 **零 hex**。
  - ✅ **Verify**：`tsc` 0 error（無 `any`）+ `vitest` **78 passed**（73 baseline + 5 新：runAlert happy/race/error + clearAlert in-flight 丟棄 + search/alert 兩流獨立）+ `vite build` ✓；backend 未動 638 / 1 xfailed 不受影響。
- **不在本 issue 範圍**（Part B 續做）：my work orders list + completion flow（需串 `work_order` router，涉及 persona / auth）；alert detail 從真 monitoring 警報事件帶入（目前用表單模擬 demo）。
- **Reference**: [`work-logs/2026-06/2026-06-03-field-alert-rag.md`](work-logs/2026-06/2026-06-03-field-alert-rag.md)

---

### WMOM-20260601-01 — Knowledge module baseline 檢索層（EPIC-M5 M5-1）

- **Status**: done（2026-06-01 完成）
- **Milestone**: M5
- **Priority**: high（PMF 關鍵 epic 起手）
- **Owner**: Claude (autonomous daily worker, session 2026-06-01)
- **Completion summary**:
  - ✅ **Simulator-first baseline 檢索層**（不依賴 ChromaDB / RAG_Ultimate 真向量檔，純 Python）：
    - `modules/knowledge/schemas.py` — 6 個 pydantic v2 模型（RagStrategy[+chunking/embedding/retrieval] / KnowledgeChunk / RetrievalQuery / RetrievedChunk / AlertEvent / AlertRagResult）；`AlertEvent.timestamp` 強制 UTC-aware（CLAUDE.md §B）
    - `modules/knowledge/strategy_loader.py` — 載入 RAG 策略 yaml；檔案缺失 / 空檔 / 非 mapping → baseline default（M5-3 placeholder 契約，不丟例外）
    - `modules/knowledge/corpus.py` — `KnowledgeCorpus`（載入 baseline JSON + `by_alarm_code` / `filter(oem,model)`）；單筆 chunk 損毀 graceful skip + warning
    - `modules/knowledge/retrieve.py` — `Retriever` Protocol（`name` / `is_baseline` / `retrieve` 契約）+ `BaselineKeywordRetriever`（告警碼 0.6 + 關鍵字命中比例 0.3 + 文字 Jaccard 0.1，clamp 0..1，繁中可解釋 `match_reason`，確定性排序）
    - `modules/knowledge/alert_handler.py` — `AlertHandler.on_alert(event)`：警報 → 構造 query（告警碼 + 機型 + 異常 tag）→ retrieve top-k → `AlertRagResult`；只依賴 `Retriever` 介面（MVP_ARCHITECTURE §3.5 升級契約：換 retriever 不改 handler）
    - `modules/knowledge/__init__.py` — `build_baseline_alert_handler()` 便捷工廠（一行起手）
  - ✅ **baseline 資料**：`config/rag_strategy_z72_manual.yaml`（對齊 MVP_ARCHITECTURE §3.5 範例）+ `data/baseline_corpus_z72.json`（11 個 Z72/Bachmann fault scenario SOP，告警碼對齊 `modules/monitoring/simulator/physics/fault_engine.FAULT_SCENARIOS`）
  - ✅ **54 tests**（schemas / strategy_loader / corpus / retrieve / alert_handler）全 pass；backend 全套 624 passed / 1 xfailed 零 regression
  - ✅ **Code review**（code-reviewer subagent）：2 must / 7 should / 4 nice → must+should 全採納 + 便宜 nice 採納（NTH1 過早優化不採納）
- **不在本 issue 範圍**（後續 epic 子目標）：
  - M5-2 ChromaDB 整合（新增 `ChromaVectorRetriever` 實作 `Retriever`，`is_baseline=False`）🔵（需 chromadb 依賴）
  - M5-3 / M5-4 接 RAG_Ultimate Phase 3 真策略檔 + `z72_manual.parquet` 🟡（需研究端產出）
  - M5-5 `/field/` mobile-first frontend 🔵
  - ~~M5-6 Alert → RAG auto query 串前端 FastAPI knowledge router 🔵~~ ✅ done（WMOM-20260603-01）
- **Reference**: [`work-logs/2026-06/2026-06-01-knowledge-rag-foundation.md`](work-logs/2026-06/2026-06-01-knowledge-rag-foundation.md)

---

### WMOM-20260608-01 — M5-2 ChromaVectorRetriever（接 RAG_Ultimate 預算向量檔 + 內嵌 query encoder）

- **Status**: done（2026-06-08 完成；branch `claude/issue-WMOM-20260608-01-2026-06-08`）
- **Completion summary**:
  - ✅ `vector_loader.py`（載入 RAG_Ultimate 預算向量 27×512 + adapter + 驗證）/ `embedder.py`（lazy SentenceTransformer query encoder）/ `chroma_retrieve.py`（`ChromaVectorRetriever` 實作 `Retriever`，cosine top-k）
  - ✅ `build_chroma_alert_handler()`（warmup + 任一缺失 graceful fallback baseline）+ router env 開關 `WMOM_KNOWLEDGE_RETRIEVER=chroma`
  - ✅ 向量檔入庫 `data/wind_farm_vectors/`（244KB，manifest 絕對路徑已清洗）；模型 92MB gitignore 走 deploy artifact
  - ✅ requirements：chromadb>=1.0（需 >=1.0 相容 numpy 2.0）+ sentence-transformers>=3.0
  - ✅ tests：vector_loader 18 + chroma（skip-if-no-model）+ fallback 2 必跑；**全 backend 701 passed / 1 xfailed 零 regression**
  - ✅ code review 3 must + 4 should + 2 nice → 採納 9/9（nice#2 延後 M5-3）
  - 語意檢索實測：「軸承振動異常」命中 bearing_fault；env 開關實測切換 chroma/baseline OK
- **Reference**: [`work-logs/2026-06/2026-06-08-wmom-20260608-01-chroma-vector-retriever.md`](work-logs/2026-06/2026-06-08-wmom-20260608-01-chroma-vector-retriever.md)

<details><summary>📜 原始 issue description</summary>
- **Milestone**: M5（M5-2）
- **Priority**: high（語意檢索升級；PMF 關鍵的檢索品質）
- **Estimate**: 1.5-2 工作天
- **Source**: DEC-20260608-01（劉老師 2026-06-08 拍板「上 ChromaDB + 收 query encoder」）
- **Decision baseline**: 採 RAG_Ultimate 預算向量檔（C 方案），過渡自嵌入（A）作廢。`ChromaVectorRetriever` 實作既有 `Retriever` Protocol（`is_baseline=False`），baseline retriever 保留 fallback。
- **要做什麼**：
  1. **新依賴**：`chromadb` + `sentence-transformers` + `torch` 進 requirements；ship `Z72_WT_embed_small`（95MB ST 模型）到 `modules/knowledge/models/Z72_WT_embed_small/`
  2. **向量載入器**：讀 `../RAG_Ultimate/exports/wind_farm_vectors/`（vectors.npy `(27,512)` float32 L2-normalized + chunks.jsonl 逐列對齊 + manifest.json 契約）→ 灌進嵌入式 Chroma collection
  3. **schema adapter**：RAG_Ultimate `{doc_id, chunk_index, text}` → `KnowledgeChunk{document_source=doc_id, section, alarm_codes=[], keywords=[]}`
  4. **`ChromaVectorRetriever`**：query 端 `SentenceTransformer(model_path).encode(query)`（512 維 normalized）→ Chroma cosine top-k → `RetrievedChunk`（繁中 `match_reason`：語意相似度）；實作 `Retriever`（`name`/`is_baseline=False`/`retrieve`）
  5. **接線**：`build_baseline_alert_handler()` 旁加 `build_chroma_alert_handler()`；`knowledge_router` info endpoint 標示 retriever 來源（baseline vs chroma badge）
  6. **tests**：向量載入對齊驗證 / encode 維度 512 / cosine top-k 確定性 / fallback to baseline（模型或向量檔缺）/ adapter 映射
- **驗收**：
  - query「軸承振動異常」能語意命中 bearing_fault chunk（baseline keyword 可能漏）
  - 模型/向量檔缺失時 graceful fallback baseline、不崩
  - backend 全套零 regression
- **退路（follow-up 選項）**：避 torch → 模型轉 ONNX runtime 再 ship（多一道轉檔，另開 issue）
- **語料注意**：此份是 RAG_Ultimate test fixture（5 文件 / 27 chunks），打通管線 + demo 足夠；完整 Z72 手冊之後同格式補（M5-3/4）
- **Depends on**: WMOM-20260601-01（knowledge baseline，done）；RAG_Ultimate 向量檔（已交付 2026-06-08）
- **Reference**:
  - DEC-20260608-01（decision_log.md）
  - `../RAG_Ultimate/exports/wind_farm_vectors/manifest.json`
  - `modules/knowledge/retrieve.py`（`Retriever` Protocol + 升級註解）

</details>

---

### WMOM-20260608-02 — M5-5 Part B-2：我的工單列表 + 完工簽名/拍照流程（`/field/` mobile）

- **Status**: done（2026-06-08 完成；branch `claude/issue-WMOM-20260608-02-2026-06-08`）
- **Completion summary**:
  - ✅ Backend：domain/state_machine/ORM/schema/repo/router 加 `completion_signature`+`completion_photos`（optional）+ `list(assignee_id=)` 過濾 + 輕量 migration（既有 DB 補欄，try/except 防 multi-worker 鎖）
  - ✅ Frontend：`MyOrdersMode.tsx`（我的工單 assignee 過濾 + 完工表單 + 簽名 canvas + 拍照，**簽名+照片+工時齊備才送** = DEC 前端強制）+ reload race guard；接進 FieldPage 第三模式
  - ✅ tests：backend 11（round-trip / assignee 過濾+None 排除 / migration / API）+ frontend 7 render；**全 backend 711 / 1 xfailed + frontend tsc 0 / vitest 797 零 regression**
  - ✅ code review 2 must + 5 should + 4 nice → 採納 6（migration 鎖 / onPointerCancel / assignee=None test / reload race / 錯誤訊息 / ensure_ascii）
  - 設計：signature/photo backend optional（不破壞 office finish）+ 前端強制（現場語意）；base64 demo-first
- **Follow-up**: 完工佐證大小上限（base64 photo 無界，M6 前加 max_length + 物件儲存）
- **Reference**: [`work-logs/2026-06/2026-06-08-wmom-20260608-02-field-completion.md`](work-logs/2026-06/2026-06-08-wmom-20260608-02-field-completion.md)

<details><summary>📜 原始 issue description</summary>
- **Milestone**: M5（M5-5 Part B-2）
- **Priority**: high（現場工程師 persona、PMF 關鍵）
- **Estimate**: 2-3 工作天（含 workflow schema 擴充）
- **Source**: DEC-20260608-02（劉老師 2026-06-08 拍板）
- **Decision baseline**:
  1. 「我的工單」**依指派 `assignee_id` 過濾**（綁 WMOM-20260510-01 mock login persona）
  2. 「完工」需**簽名 + 拍照**佐證（不只改狀態）
- **要做什麼**：
  - **Backend**：work order 完工 schema 加 signature + photo 欄位 + 儲存策略（檔案 / base64 / 物件儲存擇一，先求 demo 可跑）；完工 API 收 actual_qty + signature + photo
  - **Frontend**（`frontend/components/field/FieldPage.tsx`）：「我的工單」列表（依 assignee_id 過濾）+ 工單詳情 + 完工流程（填實際用料 → 簽名 canvas → 拍照上傳 → 送出）
  - **整合注意**：完工填的 `actual_qty` 是 WMOM-20260519-01 退料 guard（`physical_ceiling`）的上游輸入 → 兩者欄位語意要對齊
- **驗收**：現場工程師（mock login persona）登入 → 只看到自己被指派的工單 → 完工含簽名+照片 → 後端落地 → 月報材料成本反映 actual_qty
- **Depends on**: WMOM-20260510-01（mock login persona / assignee 身分）；WMOM-20260603-04（Part B-1，done）
- **關聯**: WMOM-20260519-01（退料 guard，actual_qty 上游）
- **Reference**:
  - DEC-20260608-02（decision_log.md）
  - `frontend/components/field/FieldPage.tsx`

</details>

---

### WMOM-20260608-03 — M5-3/4 接完整 Z72 手冊向量檔（取代 27-chunk fixture）

- **Status**: done（2026-06-08 完成；branch `claude/issue-M5-3-4-z72-manual-2026-06-08`）
- **Milestone**: M5（M5-3/4）
- **Source**: M5-2 完成後接完整語料（option A — 進 RAG_Ultimate 跑 ingest pipeline）
- **Completion summary**:
  - ✅ RAG_Ultimate `build_vector_file.py`（chunking 500/50 + Z72_WT_embed_small，與線上同模型同切法）跑 `docs/__Z72UserManual.pdf`（135 頁 fitz 抽 238K 字 → txt corpus）→ **531 chunks / 512 dim / L2-norm** export
  - ✅ 複製進 `data/wind_farm_vectors/`（vectors.npy 1MB + chunks.jsonl + manifest；刪冗餘 embeddings.jsonl 3MB；manifest 清絕對路徑）
  - ✅ **windMindOM 程式碼零改動**（DEC-20260608-01 升級契約成立）；只改測試斷言 27→531
  - ✅ 實測檢索：emergency pitch / gearbox temp / safety instructions 皆語意命中；中文 query 跨語有命中
  - ✅ knowledge 94 passed / 全 backend 721 passed / 1 xfailed 零 regression
- **Reference**: [`work-logs/2026-06/2026-06-08-m5-3-4-z72-manual-vectors.md`](work-logs/2026-06/2026-06-08-m5-3-4-z72-manual-vectors.md)

---

### WMOM-20260603-01 — Knowledge RAG FastAPI router（EPIC-M5 M5-6）

- **Status**: done（2026-06-03 完成）
- **Milestone**: M5
- **Priority**: high（PMF 關鍵；為 M5-5 `/field/` 前端鋪路）
- **Owner**: Claude (autonomous daily worker, session 2026-06-03)
- **Completion summary**:
  - ✅ **`modules/knowledge/routers/knowledge_router.py`（新）— 3 endpoints**（串 M5-1 baseline 檢索層）：
    - `POST /api/knowledge/alert`（body `AlertEvent` → `AlertRagResult`）— **killer feature**：SCADA 警報事件即時檢索 top-k 手冊處置段落 + 繁中可解釋命中原因
    - `POST /api/knowledge/query`（body `RetrievalQuery` → `KnowledgeQueryResponse`）— 現場工程師手動關鍵字 / 告警碼查手冊
    - `GET /api/knowledge/info`（→ `KnowledgeInfoResponse`）— 前端標示 RAG 來源 / baseline 模式 badge
  - ✅ **DI pattern 對齊 reporting_router**：`set_handler_factory(factory|None)`（`None` 清快取，test 隔離）+ lazy 快取 singleton handler（baseline corpus / 策略檔程序生命週期內不變，避免每請求重讀 JSON+yaml）
  - ✅ **`AlertHandler` 加 `retriever` / `strategy` 唯讀 property** — router 透過 `Retriever` 契約屬性（`name`/`is_baseline`）標示來源，不碰私有狀態（維持 MVP_ARCHITECTURE §3.5 升級契約）
  - ✅ **`schemas.py` 加 `KnowledgeQueryResponse` / `KnowledgeInfoResponse`** 回傳包裝
  - ✅ **`modules/monitoring/server/app.py`** `include_router(knowledge_router)` 註冊
  - ✅ **14 tests**（`test_knowledge_api.py`）全 pass；knowledge 全套 68；backend 全套 **638 passed / 1 xfailed** 零 regression；`Any` 0
  - ✅ naive timestamp 經 schema validator → API 邊界回 422（UTC-aware 防線延伸）；`alarm_code` 加 `ge=1` 下界
  - ✅ **Code review**（code-reviewer subagent）：4 must / 5 should / 3 nice → must 全採納 + 便宜 should/nice 採納（S8 sys.path→conftest 不採納，記 backlog）。must 重點：handler 初始化失敗 → 503（非洩漏 traceback 的 500）+ error-path 測試 + DI singleton autouse reset fixture；S9：`KnowledgeQueryResponse.total` 改 `@computed_field` 保證與 items 一致
- **不在本 issue 範圍**（後續）：M5-5 `/field/` mobile 前端（串本 router）、M5-2 ChromaDB、M5-3/4 RAG_Ultimate 真向量檔
- **Reference**: [`work-logs/2026-06/2026-06-03-knowledge-rag-router.md`](work-logs/2026-06/2026-06-03-knowledge-rag-router.md)

---

### WMOM-20260603-03 — `/field/` 現場 mobile 知識查詢頁（EPIC-M5 M5-5 Part A）

- **Status**: done（2026-06-03 完成）
- **Milestone**: M5
- **Priority**: high（PMF 關鍵：現場工程師 persona + mobile UI）
- **Owner**: Claude (autonomous worker, session 2026-06-03)
- **Completion summary**:
  - ✅ **`frontend/services/knowledgeService.ts`（新）— knowledge API client**：3 endpoint wrapper（`info` / `query` / `queryByAlert`）+ 型別嚴格對齊 `modules/knowledge/schemas.py`（KnowledgeChunk / RetrievedChunk / RetrievalQuery / AlertEvent / AlertRagResult / KnowledgeQueryResponse / KnowledgeInfoResponse）；錯誤處理沿用 reportingService 的 `readError`（抽 FastAPI `detail`，fallback `HTTP {status}`）
  - ✅ **`frontend/hooks/useKnowledge.ts`（新）— state hook**：`info`（mount 載入一次 baseline badge）+ `search`（手動檢索）兩條獨立流；race 防護用單調遞增 `reqRef` 丟棄過期回應（連續快速送查的 stale-overwrites-fresh）；`clearSearch` 推進序號使 in-flight 回應視為 stale
  - ✅ **`frontend/components/field/FieldPage.tsx`（新）— mobile-first UI**（maxWidth 560、單欄、大觸控目標）：關鍵字 + 告警碼 input、常用 Z72 告警碼一鍵 chips、結果卡（相關度 % + 繁中命中原因 + 文件來源 §章節·頁碼 + 段落正文 + alarm code pills）、loading / error / 空結果狀態；全走 ui 元件庫 + theme palette，**零 hex**
  - ✅ **`App.tsx`**：新增 `field` ViewId + SECONDARY_NAV「現場查詢 / Field」+ render case；**`ui/Logo.tsx`**：新增 `field` NavIconId + 手機 + 放大鏡 SVG icon
  - ✅ **14 tests**（service 8 fetch-mocked：method/path/body 契約 + 錯誤 detail 抽取，含 Pydantic 422 detail 陣列抽 msg + queryByAlert 503 error path；hook 6 service-mocked：mount loadInfo / info 失敗 / search happy / **race 舊查詢後到不蓋新** / search 失敗 / clearSearch 丟棄 in-flight）→ frontend 全套 **73 passed**（59 baseline + 14 新，零 regression）；`tsc` 0 error（無 `any`）；`vite build` ✓
  - ✅ backend 完全沒動 → 638 / 1 xfailed 不受影響
- **不在本 issue 範圍**（Part B 待續）：my work orders list + completion flow（串 work_order router）、alert detail with RAG（串 `queryByAlert`，client 已備）、真正 mobile 獨立路徑（需引入 router）
- **Reference**: [`work-logs/2026-06/2026-06-03-field-knowledge-mobile.md`](work-logs/2026-06/2026-06-03-field-knowledge-mobile.md)

---

## 工程基礎設施 / DevOps

### WMOM-20260603-02 — CI（GitHub Actions）+ auto-merge 飛輪 + routine 改 3-hourly

- **Status**: done（2026-06-03 完成）
- **Milestone**: 跨 milestone（autonomous worker 基礎建設）
- **Priority**: high（高頻 autonomous 開發的前提；劉老師交辦）
- **Owner**: Claude (autonomous worker, session 2026-06-03)
- **Completion summary**:
  - ✅ **`.github/workflows/ci.yml`（新）**：PR + push main 觸發，2 jobs — backend pytest（workflow + cost + reporting + knowledge，baseline 638）+ frontend（`npm ci` → `tsc --noEmit` → `vitest run` → `vite build`）；`concurrency` 取消舊 run
  - ✅ **`.github/workflows/auto-merge.yml`（新）**：`workflow_run`（CI completed）觸發 — CI 全綠且 head 為 `claude/*` 且標題非 `[WIP]` 且無 `hold`/`do-not-merge` label → `gh pr ready` + `gh pr merge --squash --delete-branch` 自動合 main。用 `workflow_run`（workflow 檔取自 main）避免 PR 竄改合併邏輯
  - ✅ **routine prompt v3**（`docs/routines/autonomous-daily-worker-prompt.md`）：cadence 每日 20:00 → **每 3 小時**；baseline 570→638；新增 stack-aware preflight（高頻下避免與前一個未合併 session 重工）+ 「沒乾淨工作就 graceful 收尾不硬擠」；PR 收尾語意改為「完工→正常 PR（CI 綠自動合）/ 半成品→`[WIP]` draft（auto-merge 跳過）」
  - ✅ 急停開關：PR 加 `hold` / `do-not-merge` label 即可讓 auto-merge 跳過
- **劉老師需手動做的事**（repo 側無法代勞）：到 Claude Code on the web trigger 設定把排程改 **每 3 小時** + 貼上 routine v3 prompt（見 work-log §決策）
- **Reference**: [`work-logs/2026-06/2026-06-03-ci-automerge-flywheel.md`](work-logs/2026-06/2026-06-03-ci-automerge-flywheel.md)

---

## M1（2026-05）— Setup baseline

### WMOM-20260503-01 — Repo baseline 整理（digiWT → modules/monitoring/）

- **Status**: done（2026-05-03 完成）
- **Milestone**: M1
- **Priority**: critical
- **Estimate**: 2-3 工作天 → **實際半天**（因採「move + sys.path 注入」策略，避開大規模 import 重寫）
- **Owner**: Claude (session 2026-05-03)
- **Completion summary**:
  - ✅ 5 modules（monitoring / workflow / cost / reporting / knowledge）+ shared（schemas / plc_clients / domain）+ tests 骨架就位
  - ✅ digiWT 既有 monitoring 程式（simulator、server、wind_model、scada_system、subsystems、turbine_model、opcua_interface、dashboard、main、common_types、main_architecture、examples、data、wind_farm_data.db、wind_turbine_data.db）全部搬到 modules/monitoring/
  - ✅ opc_bachmann/ 抽到 shared/plc_clients/bachmann/
  - ✅ run.py 注入 sys.path（modules/monitoring 在最前面），既有 `from simulator.x` / `from server.x` import 完全不用改
  - ✅ Dockerfile + docker-compose.yml + .dockerignore 路徑更新（含 DB_PATH、FARM_DATA_DIR、volume mount、container_name）
  - ✅ docs/legacy/digiwt_directory_layout.md 搬遷對照表 + sys.path 策略 + 影響相對路徑分析 + 驗證紀錄
  - ✅ 6 項 smoke test 全通過：legacy import、modern import、5 modules 全 importable、18-秒模擬跑出 109 SCADA tag、FastAPI app 67 routes 載入、run.py compile 通過
- **Decision resolved**: pyproject.toml 整合**未做**（保留 requirements.txt），下個 issue 處理 — 跟搬遷脫鉤可降低 risk
- **Follow-up**：
  - ✅ 完整跑 `python run.py` + 開 browser 看 dashboard（2026-05-03 用戶截圖確認 — 14 台 WTG OPERATING、3.55 MW、6.2 m/s、台中港曲風場 active farm 正確載入、5-min trend 即時更新）
  - ✅ `docker-compose` 設定靜態驗證 PASS（2026-05-03 — YAML parse、COPY directives、env vars (DB_PATH/FARM_DATA_DIR)、volume mount、相對路徑等價性 全部 OK）；實際 `docker compose up --build` 因本機未裝 Docker Desktop **deferred**（留給部署 partner / overnight 跑）
  - ✅ 重跑 examples/data_quality_analysis.py（短版）2026-05-03：0.17h × 5 turbines / 3060 rows / wall 3.7s → 15/16 quality check pass、風速↔功率 r=+0.970、1P振動↔轉速 r=+0.944、無 NaN、無 out-of-range；唯一 ⚠ 是定子溫-功率 r=-0.313 偏低，屬 duration artifact（短 sim 沒熱平衡時間，跟搬遷無關）。Pre-migration baseline 已備份；完整 2h 對照留給 overnight session
  - ⬜ Mass-rewrite imports 為 fully qualified `modules.monitoring.*` 形式（M1-M2 穩定後另開 issue）
  - ⬜ 盤點 modules/monitoring/main.py + main_architecture.py 是否為 dead code
- **Reference**:
  - [`docs/legacy/digiwt_directory_layout.md`](docs/legacy/digiwt_directory_layout.md)（搬遷對照表）
  - [`work-logs/2026-05/2026-05-03-repo-baseline-and-tracking-files.md`](work-logs/2026-05/2026-05-03-repo-baseline-and-tracking-files.md)（session 紀錄）

<details><summary>📜 原始 issue description（保留歷史 / 開工時範圍）</summary>

- **Description**:
  把根目錄既有 digiWT 檔案搬到 `modules/monitoring/`，建立 4 個空 module 占位
  （`workflow/`、`cost/`、`reporting/`、`knowledge/`），以及 `shared/` / `tests/`
  / `frontend/` 的標準骨架。確認搬完後 import path、Docker、既有 18/21 quality
  check 仍能跑通；不破壞物理一致性。
  - 子任務：
    1. 建立 `modules/{monitoring,workflow,cost,reporting,knowledge}/` 與 `__init__.py` 占位
    2. 建立 `shared/{schemas,plc_clients,domain}/` 占位（M1 後續 issue 才會放東西）
    3. 把 root 的 `simulator/`、`server/`、`scada_system.py`、`turbine_model.py`、
       `wind_model.py`、`subsystems.py`、`opcua_interface.py`、`dashboard.py`、
       `main.py`、`run.py`、`common_types.py`、`main_architecture.py`、
       `wind_farm_data.db`、`wind_turbine_data.db`、`config/`、`data/`、
       `examples/` 搬進 `modules/monitoring/`
    4. 把 `opc_bachmann/` 抽到 `shared/plc_clients/bachmann/`
    5. 修 import path（`from simulator.x` → `from modules.monitoring.simulator.x` 等）
    6. 更新 `Dockerfile` / `docker-compose.yml` 路徑
    7. 跑 `python -m pytest`（如有）+ 啟動 backend 確認 endpoint 還活著
    8. 留一個 `docs/legacy/digiwt_directory_layout.md` 紀錄搬遷對照表
- **Deliverable**:
  - `modules/monitoring/...`（搬遷後檔案）
  - `modules/{workflow,cost,reporting,knowledge}/__init__.py`（空殼）
  - `shared/plc_clients/bachmann/`
  - `docs/legacy/digiwt_directory_layout.md`（搬遷對照表）
  - 更新後的 `Dockerfile`、`docker-compose.yml`、`pyproject.toml`（或 requirements.txt）
- **Decision needed**: 是否 M1 就把 `pyproject.toml` 整合好（vs M2 才做）→ 預設 M1 做
- **Depends on**: -
- **Blocks**: WMOM-20260503-02（v0.5 資產搬入路徑會用到新結構）、WMOM-20260603-* (M2 cost 移植)
- **Reference**:
  - `docs/product/MVP_ARCHITECTURE.md`（5 modules 設計）
  - `docs/legacy/digiwt_project_notes.md`（既有物理層細節）
  - `CLAUDE.md` §4 repo 結構

</details>

---

### WMOM-20260503-02 — 搬入 v0.5 有用資產

- **Status**: done（2026-05-04 完成）
- **Milestone**: M1
- **Priority**: high
- **Estimate**: 0.5-1 工作天 → **實際 ~2 小時**（多數「搬入」項已在更早 session 完成現代化，本 session 主力為 inventory + decision 紀錄）
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ Pitch deck baseline 入庫：`docs/sales/pitch_deck_v0.5_baseline.{md,pptx}`（從 `../windFarmOM_bk/docs/pitch_deck.{md,pptx}` 複製）
  - ✅ Diff 比對 `docs/routines/daily-workflow.md` (v1.1, 2026-05-03)、`templates/*.md`、`docs/claude-code-templates/` → 已現代化，無需搬
  - ✅ 寫 `docs/sales/v05_assets_inventory.md`（搬入 / 已現代化 / 棄用三類對照）
  - ✅ `docs/product/decision_log.md` 追加 DEC-20260504-01（v0.5 棄用資產清單明列化）
- **Reference**:
  - [`docs/sales/v05_assets_inventory.md`](docs/sales/v05_assets_inventory.md)（資產對照清單）
  - [`docs/product/decision_log.md`](docs/product/decision_log.md) DEC-20260504-01
  - [`work-logs/2026-05/2026-05-04-migrate-v05-assets.md`](work-logs/2026-05/2026-05-04-migrate-v05-assets.md)（session 紀錄）

<details><summary>📜 原始 issue description</summary>

- **Description**:
  從 v0.5（windMindOM 早期 prototype）搬入仍有用的資產，不要重複造輪子：
  - `pitch_deck.md` / `pitch_deck.pptx`（給客戶用的簡報）→ `docs/sales/`
  - `daily-workflow.md`（已搬入 `docs/routines/`，確認最新版）
  - `claude-code-templates/`（已存在 `docs/`，盤點是否完整）
  - `templates/`（已存在 root，盤點 work-log / issue / decision 模板是否齊全）
  - 其他 v0.5 規劃文件中**已被 v0.8.1 取代的廢棄**（如舊版 plugin SDK 設計）→ 不搬，但在 `docs/product/decision_log.md` 紀錄為何丟棄
- **Deliverable**:
  - `docs/sales/pitch_deck_v0.5_baseline.{md,pptx}`（先存底，v0.8.1 改版見 WMOM-20260503-04）
  - `docs/routines/daily-workflow.md`（已存在）
  - `templates/`（盤點清單）
  - `docs/claude-code-templates/`（盤點清單）
- **Depends on**: WMOM-20260503-01（搬遷後新結構就位才好搬）
- **Blocks**: WMOM-20260503-04（pitch deck 改版前要先有 v0.5 baseline）
- **Reference**: `CLAUDE.md` §3 文件入口

</details>

---

### WMOM-20260503-03 — Root CLAUDE.md 改為 windMindOM 產品脈絡

- **Status**: done
- **Milestone**: M1
- **Priority**: high
- **Estimate**: 0.5 工作天
- **Owner**: 劉老師（pre-session, 2026-05-02）
- **Description**:
  既有 root `CLAUDE.md` 已於 2026-05-02 baseline commit 改為 windMindOM v0.8.1
  產品脈絡（5 modules、ICP、其他 7 repo 關係、daily routine、coding 規範）。
  既有 digiWT 版本的 root CLAUDE.md 已備份在 `docs/legacy/`（如未備份則本 issue 含此項）。
- **Deliverable**:
  - `CLAUDE.md`（已是 windMindOM v0.8.1 版本）
  - `docs/legacy/digiwt_CLAUDE.md`（如尚未備份，補上）
- **Reference**: 本檔案開頭 `CLAUDE.md` §1-15

---

### WMOM-20260503-04 — Pitch deck v0.8.1 改版

- **Status**: done（2026-05-04 完成）
- **Milestone**: M1
- **Priority**: high
- **Estimate**: 1-2 工作天 → **實際半天**（先 outline 對齊、後 build；用戶選 Journal 主題不影響故事線）
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ Outline 先 source of truth：[`docs/sales/pitch_deck_v0.8.1_outline.md`](docs/sales/pitch_deck_v0.8.1_outline.md)（10 主 + 2 附錄、每張視覺指示、v0.5→v0.8.1 9 項差異對照）
  - ✅ 主 deck 12 張：[`docs/sales/pitch_deck_v0.8.1.pptx`](docs/sales/pitch_deck_v0.8.1.pptx) + PDF（760 KB / 12 頁）
  - ✅ Onepager A4 直式：[`docs/sales/pitch_deck_v0.8.1_onepager.pptx`](docs/sales/pitch_deck_v0.8.1_onepager.pptx) + PDF（426 KB / 1 頁）
  - ✅ **Journal 主題**（米白墨綠期刊風 / 學術襯線書冊風） — 用戶決定取代原 Navy
  - ✅ Builder script: `tools/pitch_deck/build_v081_pitch.js` + `build_v081_onepager.js`（pptxgenjs，可重 build）
  - ✅ QA：python-pptx structural check 12 張 + 表格 8×8 + 頁腳 / 章節序號齊全
  - ✅ PDF 轉檔：PowerPoint COM via PowerShell（本機無 LibreOffice 的解法）
- **Reference**:
  - [`docs/sales/pitch_deck_v0.8.1_outline.md`](docs/sales/pitch_deck_v0.8.1_outline.md)（大綱 source of truth）
  - [`tools/pitch_deck/`](tools/pitch_deck/)（pptxgenjs builder）
  - [`work-logs/2026-05/2026-05-04-pitch-deck-v081.md`](work-logs/2026-05/2026-05-04-pitch-deck-v081.md)（session 紀錄）

<details><summary>📜 原始 issue description</summary>

- **Description**:
  把 v0.5 pitch deck（windMindOM 早期 framework 定位）改寫為 v0.8.1
  「**離岸風場運維廠商工具**」定位。
  - 主視覺改為「Operator-focused tool」
  - 套餐改為 Operator Basic / Pro / Enterprise（取代 v0.5 的「整合容器」分層）
  - 加上 5 modules 一張圖（monitoring / workflow / cost / reporting / knowledge）
  - 加上 simulator-first demo flow（**無實場可成立**是 sales killer feature）
  - 第一個目標客戶：Z72 機型運維廠商
  - 用 `pptx-jliu-style` skill 出 Navy 主題（科技類）→ 改 Journal
- **Deliverable**:
  - `docs/sales/pitch_deck_v0.8.1.pptx`
  - `docs/sales/pitch_deck_v0.8.1_outline.md`（投影片大綱）
  - 一頁 onepager PDF（給 cold email 附件用）
- **Depends on**: WMOM-20260503-02（先有 v0.5 baseline 才能改版）
- **Blocks**: WMOM-20260503-05（接觸客戶要先有可寄的 deck）
- **Reference**:
  - `docs/product/PRODUCT_VISION.md`（套餐分層、ICP）
  - `CLAUDE.md` §15 「第一個客戶定 Z72」

</details>

---

### WMOM-20260503-05 — Friendly 客戶接觸名單

- **Status**: in_progress（infrastructure done 2026-05-04；contact 持續整月）
- **Milestone**: M1
- **Priority**: medium
- **Estimate**: 0.5 工作天（infrastructure）+ 持續整月（contact）
- **Owner**: 劉老師（contact 執行）/ Claude session 2026-05-04（infrastructure）
- **Infrastructure done（2026-05-04）**:
  - ✅ [`docs/sales/friendly_contacts.md.template`](docs/sales/friendly_contacts.md.template) — 4 大渠道分類（NCUT 學界 / Bachmann / 第三階段運維分包商 / 業界研討會）+ contact entry 模板
  - ✅ [`docs/sales/outreach_script.md`](docs/sales/outreach_script.md) — cold email 3 範本（介紹 / cold / follow-up）+ 30 分鐘 demo agenda + objection handling FAQ + 寄送 logistics
  - ✅ [`docs/sales/customer_feedback/README.md`](docs/sales/customer_feedback/README.md) + [`_TEMPLATE.md`](docs/sales/customer_feedback/_TEMPLATE.md) — demo 後 24 小時內紀錄結構
  - ✅ `.gitignore`：`friendly_contacts.md` + `customer_feedback/202*-*-*-*.md` 不入 git（PII），但模板與 README 可 commit
- **Pending（劉老師執行）**:
  - ⬜ `cp friendly_contacts.md.template friendly_contacts.md`，從 4 大渠道盤 5-10 位潛在 contact
  - ⬜ 寄出 3-5 封 cold email（用 outreach_script.md 範本 A / B）
  - ⬜ 約到第一場 30 分鐘 demo（M1 月底前）
  - ⬜ Demo 後 24 小時內寫 `customer_feedback/YYYY-MM-DD-{客戶代號}.md`
- **完成定義**：1+ 場 demo done + feedback 寫進 customer_feedback/ → 標 done
- **Depends on**: WMOM-20260503-04（done — deck 已就位）
- **Reference**:
  - `docs/product/PRODUCT_VISION.md` §ICP（運維廠商）
  - `work-logs/2026-05/2026-05-04-friendly-contacts.md`（infrastructure session 紀錄）

---

## M2（2026-06）— Cost module（從 ECN 移植）

### WMOM-20260504-01 — ECN K13 baseline + 移植規劃（discovery-first）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: critical（**M2 第一個 issue**，blocking 所有後續 cost migration）
- **Estimate**: 0.5 工作天
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 在 ECN 跑 4 支 test 全 pass（cost_cal + waiting_time × 3 + monte_carlo），抓到 K13 黃金數字
  - ✅ 寫 [`docs/legacy/ecn_k13_baseline.md`](docs/legacy/ecn_k13_baseline.md)：K13 reference vs computed 偏差表 + 4 季 breakdown + Monte Carlo + LCOE = 72.94 EUR/MWh + 重跑 SOP
  - ✅ 寫 [`docs/legacy/ecn_engine_inventory.md`](docs/legacy/ecn_engine_inventory.md)：4 submodule × ~3,000 行 inventory + 跨模組依賴 + migration mapping + 風險評估 + 不移的東西明列
  - ✅ 在 `modules/cost/` 建 skeleton（10 個 sub-namespace `engine/{cost_cal,waiting_time,monte_carlo,var_fluct}` + `models/` + `routers/` + `schemas/` + `tests/` + `data/demo/`），import smoke test pass
  - ✅ 確認 ECN engine **完全 pure compute**（grep 無 `app.models / app.schemas / app.config` 引用），migration 邊界乾淨
- **Key decisions documented**:
  - windMindOM `modules/cost/` 結構鏡像 ECN backend/app/，降低移植 risk
  - 只移 engine（4 submodule），**不**移 models / routers / schemas / database / utils — windMindOM 自己做
  - 推薦 migration 順序：waiting_time → cost_cal → monte_carlo → var_fluct（總估時 3-3.5 天）
  - 浮點誤差容忍：< 1e-6（嚴格 numerical equivalence）
- **Reference**:
  - [`docs/legacy/ecn_k13_baseline.md`](docs/legacy/ecn_k13_baseline.md)（K13 黃金數字）
  - [`docs/legacy/ecn_engine_inventory.md`](docs/legacy/ecn_engine_inventory.md)（移植計畫 + risk）
  - [`work-logs/2026-05/2026-05-04-ecn-k13-baseline.md`](work-logs/2026-05/2026-05-04-ecn-k13-baseline.md)（session 紀錄）

---

### WMOM-20260504-08 — Cost dashboard frontend（M2 收官）

**Polish update（2026-05-04 同日）**：
- VarFluct chart 軸 label / legend 重疊修復（移除過長右軸 label，靠 legend 顏色說明；增加 chart 高度 + bottom margin）
- 全頁中文 i18n（用既有 `useI18n` hook + `ui()` 模式，與 maintenance / history page 一致）：
  panel title / subtitle / button / metric label / chart legend keys / season names 全雙語
- 預設 lang 從 `localStorage.windFarmLang` 讀（既有設計，預設 zh）
- Vite build 仍 pass（0 TS errors）

---


- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high
- **Estimate**: 1-2 工作天 → **實際 ~30 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ `frontend/services/costService.ts` (160 行) — TypeScript API client + 完整 type chain 對齊 backend pydantic schemas
  - ✅ `frontend/hooks/useCostData.ts` (70 行) — `useAsync` 通用 hook，4 個 endpoint state（data/loading/error/run）
  - ✅ `frontend/components/CostPage.tsx` (440 行) — 4 panel dashboard：
    - **ForecastPanel**: 6 metric cards + 4 季 stacked bar chart（auto-run on mount）
    - **LCOEPanel**: capex/discount input → LCOE breakdown
    - **MonteCarloPanel**: n_sim/seed input → P10/P50/Mean/P90 bar
    - **VarFluctPanel**: 20 年 line chart（Total Effort + Multiplier + Availability 三線）
    - 共用 UI bits: MetricCard / Panel / Btn / ErrorBox + money formatter
  - ✅ `frontend/App.tsx` 加 nav button (Cost icon) + view router case
  - ✅ Vite production build pass：710 modules, 1020 KB（含 recharts），0 TS errors
- **可即時測試**:
  ```bash
  python run.py                    # backend
  cd frontend && npm run dev       # frontend
  # → http://localhost:5173 → 點 nav "Cost"
  ```
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-cost-frontend.md`](work-logs/2026-05/2026-05-04-cost-frontend.md)
  - [`frontend/components/CostPage.tsx`](frontend/components/CostPage.tsx)

---

### WMOM-20260504-07 — FastAPI cost router（4 endpoints）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high
- **Estimate**: 0.5-1 工作天 → **實際 ~25 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ `modules/cost/routers/cost_router.py` (180 行) — 4 個 POST endpoints：
    - POST /api/cost/forecast    — CostForecastRequest → CostForecastResponse
    - POST /api/cost/lcoe         — LCOERequest → LCOEResponse
    - POST /api/cost/monte-carlo  — MonteCarloRequest → MonteCarloResponse
    - POST /api/cost/var-fluct    — VarFluctRequest → VarFluctResponse
  - ✅ Mount 進主 FastAPI app (`modules/monitoring/server/app.py`)
  - ✅ `modules/cost/tests/test_cost_api.py` (160 行) — **11 tests 全 PASS**：
    - 4 endpoints × bit-perfect baseline 比對
    - validation：unknown dataset → 422、n_simulations < 10 → 422
    - var_fluct custom bathtub override / constant model
  - ✅ 整 modules/ pytest：43 PASS + 1 XFAIL（cost 41 + monitoring 3，6.22s）
  - ✅ Smoke test 主 app 4 routes 成功 mount 在 `/api/cost/*`
- **可即時測試**: `python run.py` → `http://localhost:8100/docs` (FastAPI auto OpenAPI swagger)
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-cost-api.md`](work-logs/2026-05/2026-05-04-cost-api.md)
  - [`modules/cost/routers/cost_router.py`](modules/cost/routers/cost_router.py)
  - [`modules/cost/tests/test_cost_api.py`](modules/cost/tests/test_cost_api.py)

---

### WMOM-20260504-09 — SQLite 並發 lock 修復（hotfix）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M1 follow-up（hotfix，不在原規劃 issue 內）
- **Priority**: high（production crash — 用戶實際跑 monitoring 時撞到）
- **Estimate**: 0.25 工作天 → **實際 ~25 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Trigger**: 劉老師執行 `python run.py` 時 log 噴 `sqlite3.OperationalError: database is locked`，500 Error 在 `/api/maintenance/technicians`
- **Root cause**:
  - `Storage._get_conn()` 與 `FarmRegistry._get_conn()` 開 SQLite 沒設 PRAGMA
  - 預設 `journal_mode=DELETE` + `busy_timeout=0` → 撞鎖立刻 raise
  - 4 thread 並發（FastAPI handlers / DataBroker write / maintenance DELETE / simulator）撞鎖機率高
- **Completion summary**:
  - ✅ 新增 `modules/monitoring/server/sqlite_utils.py` (55 行) — `open_sqlite()` helper 統一設 WAL + synchronous=NORMAL + busy_timeout=5000
  - ✅ 改 `storage.py` `_get_conn` + `_init_db` 用新 helper
  - ✅ 改 `farm_registry.py` `_get_conn` 用新 helper
  - ✅ 新增 `modules/monitoring/tests/test_storage_concurrency.py` (130 行) — 3 tests
    - `test_pragmas_applied` — 驗證 connection 真的有 WAL + busy_timeout
    - `test_concurrent_read_write_no_lock` — 4 thread 並發 1 秒，0 lock errors（reader×2 + writer + deleter，~8,800 ops）
    - `test_storage_basic_crud_still_works` — regression: CRUD 仍正常
  - ✅ 整 modules/ test suite：32 PASS + 1 XFAIL（cost 30 + monitoring 3）
- **未動**: `modules/monitoring/scada_system.py` 的 4 個 sqlite3.connect()（看似 legacy，與 Storage 不共用 DB path，未在 crash 路徑上）
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-sqlite-lock-fix.md`](work-logs/2026-05/2026-05-04-sqlite-lock-fix.md)
  - [`modules/monitoring/server/sqlite_utils.py`](modules/monitoring/server/sqlite_utils.py)
  - [`modules/monitoring/tests/test_storage_concurrency.py`](modules/monitoring/tests/test_storage_concurrency.py)

---

### WMOM-20260504-06 — Cost adapter + pydantic schemas（M2 抽象層）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high
- **Estimate**: 0.5-1 工作天 → **實際 ~1 小時**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ `modules/cost/adapter.py` (393 行)：`EngineParams` dataclass + `load_k13_engine_params(stochastic=)` + 4 個 result→response 轉換器
  - ✅ `modules/cost/schemas/cost_schemas.py` (198 行)：10 個 pydantic models（Request × 4 + Response × 4 + 子 model × 2）
  - ✅ Refactor 3 個 engine test 用新 loader：
    - test_k13_equivalence.py: 362 → 155 行（省 207）
    - test_monte_carlo.py: 370 → 203 行（省 167）
    - test_var_fluct.py: 402 → 243 行（省 159）
    - test_waiting_time.py 不動（讀 metocean CSV，scope 不重複）
  - ✅ `modules/cost/tests/test_adapter.py` (207 行)：9 tests 涵蓋 K13 loader + 4 個 result→response + pydantic round-trip + regression gate
  - ✅ 整 cost module pytest：**29 PASS + 1 XFAIL**（4.17s，比 -05 多 9 個 adapter test）
- **Code metrics**: tests 1439 → 1113（省 326）；adapter + schemas +591；淨 +265 行
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-cost-adapter.md`](work-logs/2026-05/2026-05-04-cost-adapter.md)
  - [`modules/cost/adapter.py`](modules/cost/adapter.py)
  - [`modules/cost/schemas/cost_schemas.py`](modules/cost/schemas/cost_schemas.py)
  - [`modules/cost/tests/test_adapter.py`](modules/cost/tests/test_adapter.py)

---

### WMOM-20260504-05 — `engine/var_fluct/` 移植（4 engine 收官）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: medium
- **Estimate**: 0.5 工作天 → **實際 ~25 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 3 engine files (360 行) 從 ECN 複製 + sed 改 import + grep 確認無 ECN-specific 依賴
  - ✅ ECN 沒有對應 unit test → **從零寫 9 tests**
  - ✅ `tools/pin_var_fluct.py` 取 ~30 個 pinned 數字（20 年 bathtub 曲線 + 6 邊界 + Year 1/10/20 完整 YearResult + Summary）
  - ✅ `modules/cost/tests/test_var_fluct.py` 9 tests 全 PASS：
    - bathtub_default_curve / bathtub_edges / bathtub_curve_helper
    - varfluct_lifetime_length / year_1_pinned (early peak 1.5x) / year_10_pinned (mid life) / year_20_pinned (late peak 2.0x) / summary_pinned / year_index_consistency
  - ✅ Cross-test invariant: Year 10 var_fluct availability == -03 cost_cal pinned baseline (0.9402)
- **整 cost module pytest**: **20 PASS + 1 XFAIL**（4.88s，含 -02/-03/-04/-05 累計 21 tests）
- **4 個 ECN engine submodule 全部 ported**: cost_cal + waiting_time + monte_carlo + var_fluct
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-var-fluct-migration.md`](work-logs/2026-05/2026-05-04-var-fluct-migration.md)（session 紀錄）
  - [`modules/cost/tests/test_var_fluct.py`](modules/cost/tests/test_var_fluct.py)

---

### WMOM-20260504-04 — `engine/monte_carlo/` 移植 + LCOE bit-perfect

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high
- **Estimate**: 0.5 工作天 → **實際 ~25 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 4 engine files (674 lines) 從 ECN 複製到 `modules/cost/engine/monte_carlo/`，sed 改 import
  - ✅ Grep 確認 monte_carlo 完全乾淨（無 ECN-specific 依賴），跟 cost_cal 一樣
  - ✅ ECN 用 `np.random.default_rng(seed)` modern API，seed=42 完全 reproducible
  - ✅ `tools/pin_monte_carlo.py` 一次性工具取 21 個 pinned 數字（4 deterministic + 11 percentile + 6 LCOE，含 LCOE = 72.94 EUR/MWh）
  - ✅ `modules/cost/tests/test_monte_carlo.py` 5 tests 全 PASS：
    - `test_mc_deterministic_pinned` — 4 metric bit-perfect（reuse cost_cal）
    - `test_mc_percentiles_pinned` — 11 percentile bit-perfect
    - `test_mc_lcoe_pinned` — LCOE 72.94 EUR/MWh bit-perfect
    - `test_mc_sanity_checks` — P10<P50<P90 / std>0 / CDF monotonic
    - `test_mc_tornado` — bars > 0 且 cost_range 排序正確
- **整個 cost module pytest**: 11 PASS + 1 XFAIL（含 -02/-03/-04 累計 12 tests）
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-monte-carlo-migration.md`](work-logs/2026-05/2026-05-04-monte-carlo-migration.md)（session 紀錄）
  - [`modules/cost/tests/test_monte_carlo.py`](modules/cost/tests/test_monte_carlo.py)

---

### WMOM-20260504-03 — `engine/cost_cal/` 移植 + K13 equivalence（M2 主菜）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: critical（M2 主菜，K13 主驗證 gate）
- **Estimate**: 1-1.5 工作天 → **實際 ~30 分鐘**（SOP 第二次跑就快很多）
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 8 engine files (957 lines) 從 ECN 複製到 `modules/cost/engine/cost_cal/`，sed 改 import
  - ✅ Grep 確認 cost_cal **完全乾淨**：無任何 ECN-specific 依賴（比 waiting_time 更乾淨，不需要 stub 任何 function）
  - ✅ 寫 `tools/pin_cost_cal.py` 一次性工具取 ECN baseline 26 個數字（用 `repr()` 取 float64 完整精度）→ 跑完刪掉
  - ✅ `modules/cost/tests/test_k13_equivalence.py`：3 tests 全 PASS
    - `test_k13_migration_equivalence_pinned` — 6 top-level metrics（availability time/energy、revenue loss、repair cost、total effort、cost per kWh）bit-perfect
    - `test_k13_migration_equivalence_seasonal` — 4 seasons × 5 cost subcategories（material / equipment / revenue_loss / preventive_material / fixed_cost）bit-perfect
    - `test_k13_cost_calculation` — ECN V5 reference 比對（與 ECN 原版同 tolerance 5-30%）
  - ✅ 用 `@pytest.fixture(scope="module")` 共用 K13 結果，3 tests 跑 0.22s
- **整個 cost module pytest**: 6 PASS + 1 XFAIL（含 -02 waiting_time 的 4 tests）
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-cost-cal-migration.md`](work-logs/2026-05/2026-05-04-cost-cal-migration.md)（session 紀錄）
  - [`modules/cost/tests/test_k13_equivalence.py`](modules/cost/tests/test_k13_equivalence.py)（3 tests + 26 pinned 數字）

---

### WMOM-20260504-02 — `engine/waiting_time/` 移植 + K13 equivalence

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high（migration pattern 樹立用）
- **Estimate**: 0.5 工作天
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 7 engine files (1,059 lines) 從 ECN 複製到 `modules/cost/engine/waiting_time/`，sed 一鍵改 import path
  - ✅ Stub `data_processor.preprocess_metocean_data()` — 唯一 ECN-specific 依賴（function-level lazy import 到 SQLAlchemy ORM），engine pipeline 不會走到
  - ✅ K13 demo data (7 檔，~32k 行) 搬到 `modules/cost/data/demo/`
  - ✅ ECN test 適配 → `modules/cost/tests/test_waiting_time.py`：path 改、return → assert、加 xfail with reason
  - ✅ 加 `test_migration_equivalence_pinned`：用 `repr()` 取 ECN float64 完整精度做 pin，windMindOM 必須 bit-perfect 一致
  - ✅ 4 tests 結果：3 PASS（含 migration equivalence）+ 1 XFAIL（pre-existing ECN issue：spring/summer K13 ref 對不上 ECN compute，與 migration 無關）
- **Migration pattern 樹立**（後續 cost_cal / monte_carlo / var_fluct 沿用）:
  1. cp + sed 改 import
  2. grep `from app\.` 找 ECN-specific 依賴 → stub or migrate
  3. 適配 test：path 改、return → assert
  4. 加 pinned equivalence test 用 `repr()` 取精度
  5. xfail with reason 標記 pre-existing ECN issue
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-waiting-time-migration.md`](work-logs/2026-05/2026-05-04-waiting-time-migration.md)（session 紀錄）
  - [`modules/cost/tests/test_waiting_time.py`](modules/cost/tests/test_waiting_time.py)（4 tests）

---

## M3-M4 Planning Open（劉老師 2026-05-04 提的 product 議題）

### WMOM-20260504-10 — Cost ↔ Wind farm config 整合（規劃缺口）

- **Status**: done（2026-05-04 完成 — M3 第一週插入工作）
- **Milestone**: M3（第一週）
- **Priority**: high（M2 demo OK 但對 friendly customer 不夠 personalize）
- **Estimate**: 1-2 工作天 → **實際半天**（K13 overlay 模式收斂得快）
- **Owner**: Claude (session 2026-05-04)
- **Branch**: `claude/issue-20260504-10-2026-05-04`
- **Work-log**: [`work-logs/2026-05/2026-05-04-cost-farm-integration.md`](work-logs/2026-05/2026-05-04-cost-farm-integration.md)
- **Completion summary**:
  - ✅ `cost_inputs.json` schema + `data/farms/{台中港曲風場,彰化離岸風場台電}/cost_inputs.json` 兩個 demo
  - ✅ `adapter.py` 加 `FarmDatasetMeta` + `load_engine_params_from_farm()`：三層 lookup（farm_overlay → registry_derived → k13_fallback）
  - ✅ `schemas/cost_schemas.py`：dataset 從 `Literal["k13"]` 改 str；4 個 response 加 optional `dataset_meta`
  - ✅ `cost_router.py`：`_resolve_dataset()` 統一處理 `k13` / `farm:{id}` / 未知值（404）
  - ✅ Tests +9：5 個 adapter farm loader（overlay / fallback / registry_derived / unknown / unknown_fields filter）+ 4 個 API endpoint（farm overlay / k13 meta / fallback / empty farm_id 422）
  - ✅ Frontend `CostPage.tsx` 加 dataset selector dropdown（K13 + 動態 farm list 從 `/api/farms` 拉）+ `DatasetMetaBadge` 顯示 4 種 source；切 dataset 自動 re-run forecast
  - ✅ `docs/product/MVP_ARCHITECTURE.md` 補節 5.4「Cost ↔ Farm config 整合」
  - ✅ 整 modules pytest：52 PASS + 1 XFAIL（cost 49 / monitoring 3）；frontend Vite build 0 TS error
- **Reference**:
  - [`modules/cost/data/farms/README.md`](modules/cost/data/farms/README.md)
  - [`modules/cost/adapter.py`](modules/cost/adapter.py)（`load_engine_params_from_farm` + `FarmDatasetMeta`）
  - [`docs/product/MVP_ARCHITECTURE.md`](docs/product/MVP_ARCHITECTURE.md) §5.4
  - [`work-logs/2026-05/2026-05-04-cost-farm-integration.md`](work-logs/2026-05/2026-05-04-cost-farm-integration.md)
- **Source**: 劉老師 2026-05-04 收工提問："cost model 跟模擬風機 / 未來實際風機 有連結嗎？"
- **問題描述**:
  目前 `modules/cost/adapter.py` 的 `load_k13_engine_params()` 完全 hard-coded 讀 K13 dataset
  （130 turbines, 4 MW, EUR-based, North Sea offshore wind ECN reference）。
  **與既有 monitoring 完全脫鉤**：
  - 14 台模擬風機（Z72, MW range, 台中港）跑著
  - cost engine 跑著
  - 兩邊互不知道對方存在
- **客戶問會被問倒的**:
  > 「我的風場只有 30 台 Vestas V164，你算 130 台 K13 給我看幹嘛？」
- **要做什麼**:
  1. **設計 farm-aware cost dataset schema**（per-customer JSON）
     - 風場參數：turbine count、capacity_kw、location（→ vessel rates）、kWh tariff、CAPEX
     - 故障率：per-turbine-model FTC table（Z72 / Vestas / SGRE 各別 MTBF）
     - 設備 / 船：local market rates（台灣海域 ≠ 北海）
  2. **adapter 多支援一個 entry point**：
     `load_engine_params_from_farm(farm_id)` — 從 `monitoring/farm_registry` 取 farm config
     + 對應 cost dataset → engine params
  3. **API endpoint 加 dataset 參數**：
     `POST /api/cost/forecast { "dataset": "farm:taichung-z72-001" }`（vs `"k13"`）
  4. **預設 fallback**：找不到 farm-specific dataset 時用 K13 + warning
- **Deliverable**:
  - `modules/cost/data/farms/{farm_id}/cost_inputs.json` 雛形
  - `adapter.py` 加 `load_engine_params_from_farm(farm_id)`
  - frontend 「dataset selector」（dropdown 選 K13 demo / 真實 farm）
  - `docs/product/MVP_ARCHITECTURE.md` 補一節「Cost ↔ Farm config 整合」
- **Reference**:
  - 已在 cost engine 的 K13_FTC_DEFAULTS / K13_MC_EQUIPMENT 是這個方向的 hard-code 版

---

### WMOM-20260504-13 — Cost 系列 fetch 加 AbortController 防 race

- **Status**: done（2026-05-23 完成 — autonomous daily worker）
- **Milestone**: M5 / M6（不阻塞 demo）
- **Priority**: low
- **Estimate**: 0.25 工作天 → **實際 ~0.25d**（frontend only）
- **Owner**: Claude (session 2026-05-23)
- **Branch**: `claude/issue-WMOM-20260504-13-2026-05-23`
- **Source**: code-reviewer 對 WMOM-10 的 finding #5（2026-05-04）
- **Completion summary**:
  - ✅ `frontend/services/costService.ts`：`postJSON` + `costApi`×4（forecast/lcoe/monteCarlo/varFluct）加 optional `AbortSignal` 參數透傳給 `fetch`（純擴充，不帶 signal 的呼叫行為不變）
  - ✅ `frontend/hooks/useCostData.ts`：`useAsync.run` 三道防線消除 race：
    1. `useRef<AbortController>` 追蹤最新 in-flight request，下一筆 run 前先 `abort()` 上一筆
    2. `signal.aborted` 早退 → 即使舊 fetch 已 resolve 也不 `setData` 蓋掉新結果
    3. `controllerRef.current === controller` loading guard → 只有最新 request 結束 loading
  - ✅ `isAbortError` 接 `DOMException` + `Error`（瀏覽器原生 / polyfill 兩種）；`reset()` 也 abort + 清 loading；`useEffect` cleanup 在 unmount abort 仍 in-flight 的 request
  - ✅ Verify：`tsc --noEmit` 0 errors + `vite build` 748 modules / 4.58s / 0 errors；backend 未動（zero regression）
  - ✅ Code review 1 must + 1 should + 1 nice：should（isAbortError 補 DOMException）採納；must（reset 與 in-flight run 交錯疑 loading 殘留）以 timeline 推導判定**非真 bug**（reset 已 unconditional setLoading(false)；await resolve→finally 之間 microtask 不可插入外部 callback），不採納 hacky dead-controller，改加註解文件化
- **驗收**（劉老師本機 dev 手動）:
  - dev mode 切 dataset 5 次，最終顯示的 forecast 對應最後一次選的 dataset ✅（邏輯保證）
  - 取消舊 fetch 不會 throw 進 error state ✅（isAbortError + signal.aborted 早退）
- **已知限制**: frontend 無測試框架（無 vitest/jest），未加自動化 regression test — 為 0.25d 小工不引入整套 harness；建議另開 issue 一次導入 vitest+RTL
- **Reference**:
  - [`frontend/hooks/useCostData.ts`](frontend/hooks/useCostData.ts)
  - [`frontend/services/costService.ts`](frontend/services/costService.ts)
  - [`work-logs/2026-05/2026-05-23-cost-abortcontroller.md`](work-logs/2026-05/2026-05-23-cost-abortcontroller.md)（session 紀錄）

---

### WMOM-20260505-01 — Snapshots 表失控（41.9 GB SQLite hotfix）

- **Status**: done（2026-05-05 — PR #3 merged, VACUUM 釋放 41 GB 確認）
- **Milestone**: M1 follow-up（hotfix — production blocker，不在原規劃 issue 內）
- **Priority**: critical（production data growth — 17.5 天累積 41.9 GB；不修一個月可達 1 TB+）
- **Estimate**: 0.5-1 工作天
- **Owner**: Claude (session 2026-05-05)
- **Branch**: `claude/issue-20260505-01-2026-05-05`
- **Trigger**: 劉老師 2026-05-05 截圖 — 彰化離岸風場台電 farm 的 `wind_farm.db` 累積到 41.9 GB
- **Root cause analysis**:
  - `turbine_snapshots` 表 1,081 萬 row 佔絕大部分容量
  - 17.5 天範圍 / 19,594 個 distinct event_ref / 每 event 平均 606 row（10 分鐘 1Hz capture）
  - **三個放大因子疊加**：
    1. `storage.run_cleanup` **不清** snapshots（schema 註解寫 permanent，但實際是 bug — 沒有 retention）
    2. `data_broker._trigger_snapshot` 每次重新 trigger 時 retroactively 寫入 ~10 分鐘 in-memory history → 同類 event 重 trigger 時放大
    3. simulator state machine 在 stop=7 附近 flapping，每幾秒對同一台同一原因 emit 新 event_ref
  - 觀察證據：top event_ref 全是 `stop:WT007:7:...` 在 80 秒內連 trigger 11 次新 event
- **修法（3 件事一起做）**:
  1. `storage.run_cleanup` 加 `snapshots_retention_days` 參數（預設 7 天），DELETE FROM turbine_snapshots WHERE timestamp < cutoff
  2. `data_broker._trigger_snapshot` 加 dedupe + cooldown：
     - event_class（去掉 timestamp 部分，e.g. `stop:WT007:7`）作 dedupe key
     - 同類在 cooldown 期間（預設 5 分鐘）→ 僅延長現有 window，不重新 retroactive write
  3. 提供 `tools/vacuum_db.py` — 用 `VACUUM INTO` 寫到 sibling 路徑再 swap，避開 SQLite 原 VACUUM 需 2× 空間需求（41.9 GB 場景吃 84 GB）
- **Tests**:
  - test_storage_cleanup_snapshots_with_retention
  - test_data_broker_snapshot_dedupe_within_cooldown
- **Deliverable**:
  - 修改 `modules/monitoring/server/storage.py`（run_cleanup + 對應 maintenance_thread caller）
  - 修改 `modules/monitoring/server/data_broker.py`（_trigger_snapshot dedupe）
  - 新增 `modules/monitoring/tests/test_storage_cleanup.py` + `test_broker_snapshot_dedupe.py`
  - 新增 `tools/vacuum_db.py`（CLI tool，VACUUM INTO + swap）
- **Reference**:
  - 觀察分析資料：`/tmp/db_check2.py` 取樣結果（17.5 天 / 19,594 events / 606 row/event / 2,441 bytes/row）
  - 根因關鍵程式碼：[`data_broker.py:397`](modules/monitoring/server/data_broker.py) `_trigger_snapshot`
  - 根因關鍵程式碼：[`storage.py:520`](modules/monitoring/server/storage.py) `run_cleanup`（沒清 snapshots）

---

### WMOM-20260504-12 — Frontend 長時間執行記憶體成長（觀察）

- **Status**: in_progress（2026-05-24 — autonomous daily worker：root cause WS 殭屍重連洩漏已根治 + 卡片 React.memo；待劉老師 24h 記憶體驗收後 close）
- **Milestone**: M5 / M6（不阻塞 demo，可選優化）
- **Priority**: low → **medium**（進場發現含真 bug：WS 殭屍重連 leak）
- **Estimate**: 0.5-1 工作天
- **Owner**: Claude (session 2026-05-24)
- **Branch**: `claude/upbeat-davinci-348BY`
- **Progress（2026-05-24）**:
  - ✅ **真因 = suspect #4：WS 殭屍重連洩漏**。`useRealtimeData` 的 `ws.onclose` 無條件 `setTimeout(connect, 3000)`；unmount cleanup 呼叫 `ws.close()` 非同步觸發 onclose，在 cleanup 跑完後又排一條清不到的重連 timer → 殭屍 WebSocket 無限累積（每條每次 push 都呼叫 setTurbines）。React 18 Strict Mode dev 雙觸發立刻引爆 = 劉老師回報的 dev 記憶體成長。**修法**：`disposed` 旗標貫穿 connect/onopen/onmessage/onclose/onerror/poll；cleanup 設 disposed=true + 先解除 ws 四個 handler 再 close() + 清 timer/interval；initial REST fetch 加 cancelled guard。
  - ✅ **suspect #1：卡片 React.memo**。`FarmOverview` 的 `TCard` / `CompactTile` 加 `React.memo` + 自訂 `areEqual`（只比渲染欄位 + 新增 `lang` prop），父層因非資料因素 re-render（檢視模式切換 / 健康輪詢 / modal）時跳過 14 張 SVG 重繪。onClick/tr 刻意排除（onClick stale 由 App `liveTurbine` 以 id 反查保證；tr 為 lang 純函式；theme 走 context 不受 memo 影響）。
  - ⏭️ **suspect #2（selective setState）不做** — 已被卡片層 areEqual 取代（per-card 比較更直接）。
  - ⏭️ **suspect #3（Recharts leak）不適用 overview** — overview sparkline 走自寫 SVG（`ui/Charts.tsx`），非 Recharts；只 HistoryPage 用 recharts，若該頁長跑有 leak 另開 issue。
  - ⏭️ **suspect #5（升級/pin recharts）** 不在本 PR scope。
  - **Verify**: tsc 0 errors + vite build 748 modules / ~3.4s / 0 errors；backend 未動 zero regression。Code review 1 must（onClick stale，判定非 bug）+ 2 should（onerror disposed guard 採納；compactTileEqual turState 不採納）+ 1 nice（history reference 比較，判定非 bug）。
  - **註**：issue 描述的元件名 `MiniTrendChart`/`TurbineCard` 在 5/07 UI 改版（WMOM-20260507-01）後已不存在，實際目標改為 `TCard`/`CompactTile`。
- **待 close 條件**: 劉老師本機 dev 長跑驗收 — (1) Strict Mode 來回切頁不再累積多條 `[WS] Connected`，WS 連線數穩定為 1；(2) 24h 連續執行記憶體成長 < 50%。
- **Reference**:
  - [`frontend/hooks/useRealtimeData.ts`](frontend/hooks/useRealtimeData.ts)（WS 生命週期修復）
  - [`frontend/components/FarmOverview.tsx`](frontend/components/FarmOverview.tsx)（TCard/CompactTile React.memo）
  - [`work-logs/2026-05/2026-05-24-frontend-realtime-memory-fix.md`](work-logs/2026-05/2026-05-24-frontend-realtime-memory-fix.md)（session 紀錄）
- **觀察結果**:
  - **Backend 儲存有 bug — 見 [WMOM-20260505-01](#wmom-20260505-01--snapshots-表失控419-gb-sqlite-hotfix)**：原本以為 `storage.py` 4 層 tiered retention 正常運作；2026-05-05 發現 turbine_snapshots 沒清 → 失控膨脹
  - **前端跑數小時記憶體成長** = 典型 React SPA 長時間運行 GC 跟不上問題，與資料儲存無關，refresh 即重置
- **可能來源（依嫌疑度）**:
  1. **MiniTrendChart × 14 張卡** — 每張 turbine card 帶一個 Recharts SVG mini-chart，每次 WebSocket push（10s）都 re-render 14 個 SVG，DOM 節點累積
  2. **`useRealtimeData` 整批替換 state** — 每次 WS push 整 array of 14 turbines 全替換而非 selective update，React diff 開銷大
  3. **Recharts ResponsiveContainer** 已知 resize observer / portal listener 在某些版本長時間執行有 leak
  4. WebSocket 重連時的 listener 累積（要查 cleanup）
- **建議的緩解（順序）**:
  1. 對 TurbineCard / MiniTrendChart 加 `React.memo` + 自訂 `areEqual`（只在 power/status 變才 re-render）
  2. `useRealtimeData` selective update：比對舊新 turbine list 只 mutate 改變的，不整批 setState
  3. 評估把 MiniTrendChart 換成 canvas-based（chart.js / 自寫 canvas），跳過 SVG DOM
  4. 加「自動 24h 軟 reload」機制（demo 用）— 簡單暴力但有效
  5. 升級 / pin recharts 版本，看 changelog 有沒有 leak fix
- **不阻塞**: refresh 即解決，不影響資料儲存，不影響客戶 demo（30 分鐘 demo 不會撞到）
- **驗收**: 24 小時連續執行記憶體成長 < 50% 視為可接受
- **Reference**:
  - `frontend/hooks/useRealtimeData.ts:229` — turbines state 整批替換
  - `frontend/components/MiniTrendChart.tsx` — 14 個 SVG re-render 來源

---

### WMOM-20260504-11 — Event-driven cost ledger（M4 增強）

- **Status**: open
- **Milestone**: M4（部分覆蓋）+ **新功能延伸到 M5/M6**
- **Priority**: high
- **Estimate**: 2-3 工作天（M4 既有 work order → ledger 之上補完）
- **Source**: 劉老師 2026-05-04 提問："cost 是否會隨故障/更換零件/發電/停機 來計算（收入支出）？"
- **既有 ROADMAP 涵蓋**:
  - ✅ M4 規劃「Cost ↔ Workflow 雙向: Work Order 完工 → cost ledger（actual）」
  - ✅ `GET /api/cost/ledger` endpoint
  - ✅ `/admin/cost/ledger` UI
- **規劃缺口（要補進來）**:
  1. **收入端**：發電量 × 電價 → 每日 / 每月入帳
     - Source：monitoring 的 `turbine_data` 表（每 10 秒 power_output kW）
     - Aggregate：每日 sum × tariff → daily_revenue table
     - 目前 turbine_data 已 ready，缺 aggregator + ledger entry
  2. **故障即時影響**：fault 發生 → 估推 revenue loss = downtime × expected_power × tariff
     - 整合 `modules/monitoring/scada_system.py` 的 fault scenario detection
     - Push pending revenue_loss 到 ledger（status: estimated → confirmed when 完工）
  3. **零件更換成本 + RUL 影響**：
     - 工單填料件清單 → 對應 component 表 → cost + RUL adjustment
     - 影響下次 monte_carlo 的 freq_min/ml/max（empirical update）
  4. **Ledger schema 設計**：
     ```
     CostLedger {
       id, farm_id, timestamp, type: 'revenue' | 'expense',
       category: 'generation' | 'corrective' | 'preventive' | 'fixed' | 'revenue_loss',
       amount, source_event_id, status: 'estimated' | 'confirmed'
     }
     ```
- **Deliverable**:
  - `modules/cost/models/cost_ledger.py` — SQLAlchemy / dataclass schema
  - `modules/cost/services/revenue_aggregator.py` — turbine_data → daily revenue
  - `modules/cost/services/event_ledger.py` — fault / work-order / inventory → ledger entries
  - 整合 `modules/workflow/work_order.py`（M3 完成後）— 工單完工 → ledger expense
  - 新 endpoint `GET /api/cost/ledger?farm_id=&from=&to=&type=`
  - frontend `/admin/cost/ledger` page — 實際 vs 預測對比
- **依賴**:
  - WMOM-10（farm 整合）必須先做 — ledger 需要 farm_id 維度
  - M3 work order CRUD 完成 — expense ledger 才能寫入
  - M4 inventory 完成 — 零件 cost 才能拆分
- **設計筆記應該寫進**: `docs/product/decision_log.md` DEC-{date}-XX「Cost 從 budget calculator 升級為 real-time ledger」

---

## M3 主線（2026-07）— Workflow Part 1: Work Order + Approval

> M3 主軸：從 z72_etech 取設計 → design notes → walkthrough → Work Order CRUD + 狀態機 + Approval。
> 7 個 sub-issue。`WMOM-20260504-10` (cost↔farm) 已先在 M3 第一週插入完成。

### WMOM-20260504-14 — z72_etech 取設計 + 3 份 design notes（**取材選 A**）

- **Status**: done（2026-05-05 完成 — 三份 DN 全寫 + walkthrough confirmed 一次到位）
- **Milestone**: M3
- **Priority**: critical（M3 spike，已解 blocking）
- **Estimate**: 1-2 工作天 → **實際 1 天**（劉老師全 agree default 建議，walkthrough 跟設計一次合併）
- **Owner**: Claude (session 2026-05-04 / 2026-05-05)
- **Branch**: `claude/issue-20260504-14-2026-05-04` (DN-01 part) + `claude/issue-20260504-15-walkthrough-2026-05-05` (DN-02/03 + walkthrough)
- **Completion summary**:
  - ✅ z72_SCADA_etech repo inventory（盤點報告 + 重構路線圖 + 5+ 個關鍵 module 程式）
  - ✅ DN-01 [Work Order Lifecycle](docs/design-notes/m3/DN-01-work-order-lifecycle.md) — 含 walkthrough 7 Q 答覆 + schema 微調（FollowupKind 二元 / Priority enum / multi-WO constraint / inspection auto-spawn hook）
  - ✅ DN-02 [Approval Multi-level](docs/design-notes/m3/DN-02-approval-multilevel.md) — 4 階 signoff / 工單 2 階 / 領料 3 階 / reject 回 IN_PROGRESS / signoff_history KPI
  - ✅ DN-03 [Inventory ↔ Material Request](docs/design-notes/m3/DN-03-inventory-material-request.md) — 3 欄位庫存 / 估計 vs 實際領料 / 退料 4 種分類 / 多倉預留 / inventory_adjustment_log 給庫管員手動 +/-
  - ✅ [README](docs/design-notes/m3/README.md) — 三份 DN 索引 + etech 10 大模組對照表 + 不取的東西清單
  - ✅ 衍生兩個新 issue：[WMOM-20260505-21](#wmom-20260505-21) (day_work_form) + [WMOM-20260505-22](#wmom-20260505-22) (inspection_schedule)
- **Reference**:
  - [`docs/design-notes/m3/`](docs/design-notes/m3/)（三份 DN + README）
  - [`work-logs/2026-05/2026-05-05-walkthrough-and-dn02-dn03.md`](work-logs/2026-05/2026-05-05-walkthrough-and-dn02-dn03.md)

---

### WMOM-20260504-15 — 30 分鐘 walkthrough 跟劉老師確認 design notes

- **Status**: done（2026-05-05 完成 — 與 -14 合併走完）
- **Milestone**: M3
- **Priority**: high
- **Estimate**: 0.5 工作天 → **實際 30 分**（合併在 -14 內，劉老師逐一答 17 個 Q）
- **Owner**: Claude + 劉老師
- **Completion summary**:
  - ✅ DN-01 7 個 Q 全 confirmed（含 removeFrom / chooseschange / multi-WO / 4 type / weather_window / dayworkForm / inspection）
  - ✅ DN-02 5 個 Q 全 agree default（4 階 signoff / 工單 2 階 vs 領料 3 階 / reject 回 IN_PROGRESS / 線性 / history 保留）
  - ✅ DN-03 5 個 Q 全 agree default（3 欄位庫存 / 系統追蹤部分 + 紙本歸還 / 估計 vs 實際 / 4 種退料分類 / 多倉預留）
  - ✅ Q&A 直接整合進對應 DN 文件（取代原「open questions」section）
  - ✅ 兩個衍生 issue 開好（WMOM-21 + WMOM-22）

---

### WMOM-20260504-16 — Work Order 領域模型 + 狀態機（pure domain）

- **Status**: done（2026-05-05 完成）
- **Milestone**: M3
- **Priority**: critical
- **Estimate**: 1 工作天 → **實際半天**（含 code review fix）
- **Owner**: Claude (session 2026-05-05)
- **Branch**: `claude/issue-20260504-16-2026-05-05`
- **Completion summary**:
  - ✅ `modules/workflow/domain/work_order.py`：4 Enum + ProgressNote + WorkOrderFollowup + WorkOrder dataclass
  - ✅ `modules/workflow/domain/state_machine.py`：TransitionRule + WORK_ORDER_TRANSITIONS（9 rule / 8 action）+ 6 guard + WorkOrderStateMachine + helper
  - ✅ Tests +73：test_work_order.py (20) + test_state_machine.py (53) — 含完整 lifecycle / parametrized 反例 / guard 不污染 state regression
  - ✅ Code review 13 finding 全處理（5 must-fix + 5 should-fix + 3 nice-to-have）
  - ✅ 整 pytest 163 PASS + 1 XFAIL（cost 49 + monitoring 35 + workflow 79）
- **Reference**:
  - [`modules/workflow/domain/`](modules/workflow/domain/)
  - [`work-logs/2026-05/2026-05-05-work-order-domain.md`](work-logs/2026-05/2026-05-05-work-order-domain.md)

---

### WMOM-20260504-17 — Work Order CRUD + REST API + tests

- **Status**: done（2026-05-05 完成）
- **Milestone**: M3
- **Priority**: critical
- **Estimate**: 1 工作天 → **實際 ~1 天**（含 code review 9 finding 全處理）
- **Owner**: Claude (session 2026-05-05)
- **Branch**: `claude/issue-20260504-17-2026-05-05`
- **Completion summary**:
  - ✅ `modules/workflow/repository/`：3 個 SQLAlchemy 2.0 ORM + WorkOrderRepository（CRUD + transition + multi-WO constraint + business_key + event log）
  - ✅ `modules/workflow/schemas/work_order_schemas.py`：10 個 pydantic v2 model
  - ✅ `modules/workflow/routers/work_order_router.py`：11 個 FastAPI endpoints
  - ✅ Mount 進主 FastAPI app
  - ✅ Tests +50：repository 31 + API 19
  - ✅ Code review 9 finding 全處理（3 must-fix + 5 should-fix + 1 nice-to-have）
  - ✅ 整 pytest 213 PASS + 1 XFAIL（cost 49 + monitoring 35 + workflow 129）
- **Reference**:
  - [`modules/workflow/`](modules/workflow/)
  - [`work-logs/2026-05/2026-05-05-work-order-crud-api.md`](work-logs/2026-05/2026-05-05-work-order-crud-api.md)

---

### WMOM-20260504-18 — Approval 多階簽核 + tests

- **Status**: done（2026-05-05 完成）
- **Milestone**: M3
- **Priority**: critical
- **Estimate**: 1 工作天 → **實際 ~1 天**（含 code review 11 finding 全處理）
- **Owner**: Claude (session 2026-05-05)
- **Branch**: `claude/issue-20260504-18-2026-05-05`
- **Completion summary**:
  - ✅ `modules/workflow/domain/signoff.py`：4 階 SignoffLevel + chain/step/history dataclasses + chain policy + user_group_to_level helper
  - ✅ `modules/workflow/repository/orm_models.py`：+3 個 SQLAlchemy 2.0 mapped class
  - ✅ `modules/workflow/repository/signoff_repository.py`：create_chain + approve/reject + pending list + history audit
  - ✅ `modules/workflow/schemas/signoff_schemas.py`：6 個 pydantic v2 model
  - ✅ `modules/workflow/routers/approval_router.py`：3 個 endpoints + factory injection
  - ✅ Integration: work_order finish → auto-create chain；approve last → 自動 work_order.approve_all；reject → 自動 work_order.reject
  - ✅ Mount 進主 FastAPI app
  - ✅ Tests +34（signoff repo 28 + approval API 9）；整 pytest 250 PASS + 1 XFAIL
  - ✅ Code review 11 finding 全處理（5 must-fix + 4 should-fix + 2 nice-to-have）
- **Reference**:
  - [`modules/workflow/`](modules/workflow/)（domain/signoff.py + repository/signoff_repository.py + routers/approval_router.py）
  - [`work-logs/2026-05/2026-05-05-approval-signoff-api.md`](work-logs/2026-05/2026-05-05-approval-signoff-api.md)

---

### WMOM-20260504-19 — `/admin/workflow/orders` frontend（建立精靈 + 列表 + 詳情）

- **Status**: done（2026-05-09 完成）
- **Milestone**: M3
- **Priority**: high
- **Estimate**: 1-1.5 工作天 → **實際 ~半天**（API client + hook + 4 components + nav 接線）
- **Owner**: Claude (session 2026-05-09)
- **Completion summary**:
  - ✅ `frontend/services/workOrderService.ts`：11 個 endpoint TypeScript wrapper（CRUD + 8 transitions + farm list helper）+ enum / type 與後端 schema 對齊
  - ✅ `frontend/hooks/useWorkOrders.ts`：stateful hook（list / loading / error + 9 mutations，patch local state on success，AbortController race guard）
  - ✅ `frontend/components/workflow/` 4 個檔案：
    - `WorkflowPage.tsx`：主入口（farm 自動偵測 + tab 預留 approval -20 + create modal/detail modal 對接）
    - `WorkOrderListPanel.tsx`：列表（status filter / search / refresh / empty state / error display）
    - `CreateWorkOrderWizard.tsx`：3-step 精靈（風機卡片選 → type+priority+title+description → assignee+crew+hours + review）
    - `WorkOrderDetailModal.tsx`：詳情 + 7 inline transition forms（dispatch / start-work / progress / finish / reject / cancel / reopen；approve 走 -20）
    - `statusUtils.ts`：status / priority / type / followup enum 對 PillTone + zh/en label + datetime fmt 共用 helper
  - ✅ `frontend/App.tsx`：加 `workflow` ViewId + nav；傳 turbines 到 WorkflowPage
  - ✅ `frontend/components/ui/Logo.tsx`：加 `workflow` NavIcon（briefcase）
  - ✅ Smoke test：`tsc --noEmit` clean、`vite build` 成功（725 modules / 1.05 MB）、dev server localhost:5179 回 HTTP 200
  - ✅ UI directive 遵守：全程走 `frontend/components/ui/` + `useTheme().C`，無 Tailwind utility、無 hex（chart event 例外）
- **Decisions made during impl**:
  - 詳情 modal 寫在 `components/workflow/WorkOrderDetailModal.tsx`（與 legacy mock 版 `components/WorkOrderDetailModal.tsx` 區分）— 後者對應的 WorkOrder type 跟 backend schema 完全不同 shape，沿用會強行轉型不健康
  - `actor_id` 採 `DEV_ACTOR_ID = '00000000-...01'` 占位（auth 系統 M5+ 才接），constant 在 service.ts，TODO 註解明確
  - approve 按鈕在 detail modal **disable**，顯示提示「走 -20 approval 流程」；list 顯示 `awaiting_signoff` 狀態讓 user 知道需要去 approval tab（-20 上線後）
  - turbine_id 用 `turbine.name` 字串（與 backend simulator 的 string id convention 對齊）
  - 列表 search 設計：server-side 走 status filter，client-side 過濾 business_key / title / turbine_id 子字串（避免 backend 加 search index 的工程量）
- **Follow-up**：
  - ⬜ approve 按鈕真正啟用 → WMOM-20260504-20 上線時補
  - ⬜ Pagination UI（目前 limit=200 單頁）→ 工單量 > 200 時再加（M4 後）
  - ⬜ `/api/workflow/work-orders/{id}/event-log` 讀取顯示 → 等 backend 加 endpoint
  - ⬜ assignee_id 由文字輸入改成 user picker → 等 auth/user system 上線
- **Reference**:
  - [`work-logs/2026-05/2026-05-08-work-order-frontend.md`](work-logs/2026-05/2026-05-08-work-order-frontend.md)
  - Backend: WMOM-20260504-17（CRUD/state API）+ WMOM-20260504-18（signoff chain）

<details><summary>📜 原始 issue description</summary>

- **UI directive（WMOM-20260507-01 後）**：
  必須使用 `frontend/components/ui/`（Card / Btn / PageHeader / StatusPill / Field / Input / Select / Stat / BigChart / HealthBar）+ `frontend/theme/`（useTheme → C palette）。**不可** 寫 Tailwind utility class、不可硬寫 hex（chart event 標記色除外）。Modal 套既有 [WorkOrderDetailModal](frontend/components/WorkOrderDetailModal.tsx) 風格（Card padding=0 + DM Serif title + 底部 Btn）。
- **Description**:
  - `frontend/services/workOrderService.ts` (TypeScript API client)
  - `frontend/hooks/useWorkOrders.ts`
  - `frontend/components/WorkflowPage.tsx` 主入口
  - `frontend/components/workflow/WorkOrderListPanel.tsx` 列表（含 status filter + Hnumber search）
  - `frontend/components/workflow/CreateWorkOrderWizard.tsx` 建立精靈（多步：選風機 / 選故障代碼 / 派工人員 / 預估工時）
  - `frontend/components/workflow/WorkOrderDetailModal.tsx` 詳情 + 狀態 transition 按鈕

</details>

---

### WMOM-20260504-20 — `/admin/workflow/approval` frontend（待簽列表 + 簽核操作）

- **Status**: done（2026-05-09 完成；與 -19 同日 push）
- **Milestone**: M3
- **Priority**: high
- **Estimate**: 1 工作天 → **實際 ~半天**（service+hook+2 component+wire panel/tab）
- **Owner**: Claude (session 2026-05-09)
- **Completion summary**:
  - ✅ 擴充 `frontend/services/workOrderService.ts`：加 SignoffLevel/Status/SubjectType + 6 個 response/request interface + `signoffApi.{listPending, approve, reject}`
  - ✅ `frontend/hooks/usePendingApprovals.ts`：list state + approve/reject mutations + workOrderCache（`Promise.allSettled` 並行 fetch 對應工單 detail，給 UI 顯示 title/priority 用）+ AbortController race guard
  - ✅ `frontend/components/workflow/PendingApprovalPanel.tsx`：level selector（4 enum，default leader）+ subject_type filter + 列表（subject summary + step/chain progress + approve/reject 按鈕）
  - ✅ `frontend/components/workflow/ApprovalActionDialog.tsx`：兩模式 approve（comment 選填）/ reject（reason 必填）+ subject 摘要避免簽錯 + `subject_transition_error` warning 處理（chain 落地但工單 transition 失敗的 race case）
  - ✅ `frontend/components/workflow/statusUtils.ts`：加 `signoffLevelLabel` / `signoffStatusLabel` / `signoffStatusTone` / `subjectTypeLabel` zh/en helper
  - ✅ `frontend/components/workflow/WorkflowPage.tsx`：tab 從 dummy disabled 變真切換、render `<PendingApprovalPanel>` + `<ApprovalActionDialog>`；tab 顯示 pending count badge；approve/reject 後 `subject_status_changed === true` 自動 `wo.refresh()` 同步 orders list
  - ✅ Smoke test：tsc clean / vite build 成功（1067 kB / gzip 286 kB）/ dev 5179 回 200
  - ✅ UI directive 完整遵守：ui 元件庫 + theme palette / 無 Tailwind / 無 hex / dialog 套既有 modal 風格
- **Decisions made during impl**:
  - work order detail cache 走「list 拉到後並行 fetch 所有 unique subject_id」(`Promise.allSettled` 容忍個別 404)，避免每個 row 顯示 title 都要 hover-fetch；M4 領料單來時同邏輯擴充
  - default level = leader（工單 chain `[EMPLOYEE, LEADER]` 中 reviewer 最常出現的角色）
  - 工單 detail modal 的 approve 按鈕仍 disable — DN-02 設計上 approve 走 `/approvals/{step_id}/approve` 而非工單層 `/work-orders/{id}/approve`（後者是 server-side guard 副作用 endpoint，不是 user-facing action）
  - `subject_transition_error` 用 warning Card 顯示而非錯誤 — chain 已落地不能 retry，需要 ops 人工 backfill 工單 status
- **Reference**:
  - [`work-logs/2026-05/2026-05-09-approval-frontend.md`](work-logs/2026-05/2026-05-09-approval-frontend.md)
  - Backend: WMOM-20260504-18（signoff chain + 3 endpoints）

<details><summary>📜 原始 issue description</summary>

- **UI directive（WMOM-20260507-01 後）**：
  與 -19 同 — 使用 `frontend/components/ui/` + `frontend/theme/`，不可 Tailwind / 硬 hex。Approval action dialog 套 [DispatchModal](frontend/components/DispatchModal.tsx) 模式（Card padding=0 + grid 內 Btn 卡片選人 + 底部 primary 確認）。
- **Description**:
  - `frontend/components/workflow/PendingApprovalPanel.tsx` 待簽列表（badge 含工單摘要 + 簽核層級）
  - `frontend/components/workflow/ApprovalActionDialog.tsx` 簽核 / 駁回對話框（含意見輸入）
  - 整合進 `WorkflowPage.tsx`（tab 切換 orders / approval）
  - 全 zh / en i18n

</details>

---

## M3 衍生 issue（從 walkthrough Q6 / Q7 衍生 — 不在 M3 主線 7 sub-issue 內）

### WMOM-20260505-21 — `day_work_form` 員工日誌設計與實作

- **Status**: open
- **Milestone**: M3 後續 / M4 之間（不阻塞 M3 主線）
- **Priority**: medium
- **Estimate**: 1-1.5 工作天
- **Source**: DN-01 walkthrough Q6（劉老師 2026-05-05 確認）
- **UI directive（WMOM-20260507-01 後）**：frontend `/admin/workflow/daywork` 必須使用 `frontend/components/ui/` + `frontend/theme/`，不可 Tailwind / 硬 hex。
- **Description**:
  工單對象 = 風機；員工日誌對象 = 員工 × 當天。兩個 entity 不同，但有引用關係。
  日誌可包含「完成 1 張工單 + 完成 2 個定檢項 + 巡視 + 訓練」等 4 種 activity kind。
- **Deliverable**:
  - `modules/workflow/domain/day_work_form.py`：DayWorkForm + ActivityEntry + ActivityKind enum
  - `modules/workflow/repository/day_work_form_repository.py`
  - `modules/workflow/routers/day_work_form_router.py`：CRUD + 「我今天做了什麼」query
  - frontend `/admin/workflow/daywork` 列表 + 個人填單頁
  - 整合 work_order.finish() 時自動寫進當天 day_work_form
- **Reference**:
  - [`docs/design-notes/m3/DN-01-work-order-lifecycle.md`](docs/design-notes/m3/DN-01-work-order-lifecycle.md) §3.3
  - etech 對應：`server/dayworkForm.js` + `pages/dayworkForm.vue`

---

### WMOM-20260505-22 — `inspection_schedule` 定檢計畫 + scheduler auto-spawn

- **Status**: open
- **Milestone**: M3 後續 / M4 之間（不阻塞 M3 主線）
- **Priority**: medium
- **Estimate**: 1-1.5 工作天
- **Source**: DN-01 walkthrough Q7（劉老師 2026-05-05 確認）
- **Description**:
  定檢清單獨立 entity（如「每月一次塔筒螺栓檢查」「每季一次潤滑油檢查」）。
  Scheduler 把到期 inspection auto-spawn `work_order(type=INSPECTION)`，避免人工漏排。
- **Deliverable**:
  - `modules/workflow/domain/inspection_schedule.py`：InspectionSchedule + Recurrence enum
  - `modules/workflow/services/inspection_scheduler.py`：daily check 到期項 → spawn WO
  - `modules/workflow/routers/inspection_router.py`：CRUD 定檢計畫 + query「下次檢查時間」
  - frontend `/admin/workflow/inspection` 計畫列表 + 編輯 + 「下次到期」dashboard
- **Reference**:
  - [`docs/design-notes/m3/DN-01-work-order-lifecycle.md`](docs/design-notes/m3/DN-01-work-order-lifecycle.md) §3.3
  - etech 對應：`server/regularlistForm.js` + `server/regularSetting.js`

---

## M4 主線（2026-08）— Workflow Part 2: Inventory + Reporting

> ROADMAP 對應：[`docs/product/ROADMAP.md`](docs/product/ROADMAP.md) Month 4 段。
> 設計依據：[DN-03 Inventory ↔ Material Request](docs/design-notes/m3/DN-03-inventory-material-request.md)。
> Demo flow（M4 結束時）：「告警 → 工單 → 簽核 → 派工 → **領料簽核** → **庫存扣帳** → 完工 → **cost actual 寫入** → **月報 PDF 自動產出**」— 完整工作鏈閉環。
>
> 開工順序建議：**A1 (domain) → A2 (repo 雙寫) → A3 (material API) → A6 (material frontend) → A4 (inventory API) → A7 (inventory frontend) → A5 (cost ledger 整合) → A8 (reporting backend) → A9 (reporting frontend) → A10 (e2e test)**。
> Backend signoff `MATERIAL_REQUEST` enum + `build_chain_levels(MATERIAL_REQUEST) → 3 階 (employee/leader/treasury)` + frontend approval tab 的 `subject_type` filter 都已預留（M3 同步完成），M4 只要 wire 起來就行。

---

### WMOM-20260509-01 — Inventory + MaterialRequest domain（pure dataclass + state machine）

- **Status**: done（2026-05-09 完成；同日進場規劃 + 實作）
- **Milestone**: M4
- **Priority**: critical（M4 主菜的根基）
- **Estimate**: 0.5 工作天 → **實際 ~半天**（與規劃同日 push）
- **Owner**: Claude (session 2026-05-09)
- **Completion summary**:
  - ✅ `modules/workflow/domain/inventory.py`：3 enum（StockKind / MaterialRequestStatus 9 狀態 / ReturnReason 4 類）+ 7 dataclass（Warehouse / InventoryItem / MaterialRequest / MaterialRequestItem / MaterialReturn / MaterialRequestNotification / InventoryAdjustmentLog）+ helper（total_available / is_below_safety / get_stock）+ `Decimal` unit_cost + `__post_init__` qty>0 invariant
  - ✅ `modules/workflow/domain/inventory_state_machine.py`：8 transitions（submit_for_approval / approve_all / reject / dispatch / receive / mark_used / close / cancel）+ 5 guard funcs + side-effect dispatcher，與 work_order state_machine 同模式；共用 `InvalidTransition` exception；helper `open_states_mr()` / `terminal_states_mr()`
  - ✅ `modules/workflow/domain/__init__.py`：13 個新 export（10 inventory entity + 3 state machine helper）
  - ✅ `modules/workflow/tests/test_inventory_domain.py`（22 tests）+ `test_material_request_state_machine.py`（38 tests）
  - ✅ **60 inventory tests pass** in 0.10s；全 workflow suite **233 pass**（60 新 + 173 既有，0 regression）in 4.21s
  - ✅ AST-based import guard：domain 層 `import` 樹確認無 SQLAlchemy / FastAPI / pydantic 滲入
- **Decisions made during impl**:
  - **REJECTED 為終態**（vs DN-02 D2-Q3「reject → DRAFT」）：選乾淨 audit trail + 避免 ping-pong + 強制重整意圖；改回 DN-02 行為僅 1 行 + 2 test 影響，walkthrough 可再 confirm
  - **cancel 在 DISPATCHED 之後不允許**：物料已離庫，要退庫須走 `MaterialReturn` entity
  - **close 兩條 source state**：`USED → CLOSED`（正常）+ `RECEIVED → CLOSED`（沒實際用，跳過 USED）
  - **receive 用 dict 帶 actual_qty**：guard 強制 dict 涵蓋所有 items；允許單個 item actual=0（全退場景）
  - **dispatch 在 domain 層只動 status**：真正庫存扣帳 + ledger 寫入是 A2（repository 雙寫 transaction）的範圍
  - **AST import 防護**：第一版用 string contain 檢查誤判 docstring「SQLAlchemy mapping」字眼，改用 `ast.parse` 解析 import 樹
- **Reference**:
  - [`work-logs/2026-05/2026-05-09-inventory-domain.md`](work-logs/2026-05/2026-05-09-inventory-domain.md)
  - [`docs/design-notes/m3/DN-03-inventory-material-request.md`](docs/design-notes/m3/DN-03-inventory-material-request.md) §2

<details><summary>📜 原始 issue description</summary>

把 DN-03 §2.1-2.2 的 schema 寫成純 dataclass + Enum，與 SQLAlchemy 解耦。
  - `modules/workflow/domain/inventory.py`：
    - Enum：`StockKind ∈ {NEW, USED, REPAIRING}`、`MaterialRequestStatus ∈ {DRAFT/AWAITING_APPROVAL/APPROVED/DISPATCHED/RECEIVED/USED/CLOSED/CANCELLED/REJECTED}`、`ReturnReason ∈ {SURPLUS/WRONG_PART/FAILED_INSTALL/OTHER}`
    - Dataclass：`InventoryItem`、`Warehouse`、`MaterialRequest`、`MaterialRequestItem`、`MaterialReturn`、`MaterialRequestNotification`
  - `modules/workflow/domain/inventory_state_machine.py`：MaterialRequest state transitions（draft → awaiting → approved → dispatched → received → used → closed；cancel / reject 旁路）
  - tests/`test_inventory_domain.py` + `test_material_request_state_machine.py`（pure unit，不接 DB）

Acceptance：
  - 所有 dataclass 走 type hint + frozen 不變式
  - state machine 拒絕非法 transition（raise `InvalidTransition`）
  - 30+ unit test pass、無 SQLAlchemy import 漏進 domain 層

Depends on: -；Blocks: WMOM-20260509-02

</details>

---

### WMOM-20260509-02 — Inventory + MaterialRequest Repository（**雙寫交易模型** — M4 核心）

- **Status**: done（2026-05-09 完成；A1 同日接力）
- **Milestone**: M4
- **Priority**: critical（DN-03 §2.3 整個 issue 的關鍵不變式）
- **Estimate**: 1 工作天 → **實際 ~半天**（同 A1 session 內推完）
- **Owner**: Claude (session 2026-05-09)
- **Completion summary**:
  - ✅ `modules/workflow/repository/inventory_orm.py`：7 SQLAlchemy mapped class（WarehouseORM / InventoryItemORM / InventoryAdjustmentLogORM / MaterialRequestORM / MaterialRequestItemORM / MaterialReturnORM / MaterialRequestNotificationORM），與既有 work_order ORM 共用 `Base` + 共用 `_get_engine` cache
  - ✅ `modules/cost/repository/__init__.py` + `cost_ledger.py`：CostLedgerEntryORM 共用 workflow Base（atomic transaction 必要）+ 3 enum + pure dataclass + `insert_in_session()` helper
  - ✅ `modules/workflow/repository/inventory_repository.py`：InventoryRepository（CRUD / safety_stock filter / 手動 adjust + audit log）+ `apply_stock_delta_in_session()` helper（lock + 異動 stock，給 dispatch 用）
  - ✅ `modules/workflow/repository/material_request_repository.py`：MaterialRequestRepository — CRUD + state transition + **atomic `dispatch_request()`** + atomic `add_return()` + `list_for_work_order()` reverse-lookup（取代 work_order schema 內 list[UUID]）
  - ✅ `modules/workflow/repository/__init__.py`：13 個新 export
  - ✅ 3 test files / 58 new tests pass：
    - `test_inventory_repository.py`（21）：CRUD / safety stock filter / adjust + audit log / Decimal round-trip
    - `test_material_request_repository.py`（19）：CRUD / state transitions / business_key / signoff chain wiring / returns
    - `test_dispatch_atomic_transaction.py`（**18 — M4 核心**）：happy + multi-item / state mismatch / insufficient_stock 全 rollback / mid-transaction mock failure 全 rollback / round-trip / **2 個並發 dispatch 在 SQLite WAL 下序列化正確**
  - ✅ **全 workflow suite 291 pass**（M3 173 + A1 60 + A2 58）/ **cost+workflow combined 348 pass + 1 xfailed (existing) — 0 regression**
- **Decisions made during impl**:
  - **Cost ledger 共用 workflow Base**：atomic 雙寫必須跨 module 共用 Base metadata；替代方案（2PC / message queue / retry）違反 DN-03 §2.3 不變式
  - **SQLite SELECT FOR UPDATE no-op**：`with_for_update()` 在 SQLite 不真做 row-lock，但 BEGIN IMMEDIATE + WAL + busy_timeout 序列化寫入；test `test_concurrent_dispatch_*` 兩 thread 同 dispatch 同 item 驗證（5 stock × 2 個各要 4 → 1 成功 + 1 InsufficientStock，最終 stock=1，0 double-spend）。PostgreSQL 部署時 `with_for_update()` 才真做 row-lock
  - **`dispatch_request` 不走 `transition('dispatch')`**：domain state machine 的 `dispatch` action 只動 status；repository `transition('dispatch')` 明確 raise 提示 caller 改用 `dispatch_request()` 才會做 atomic 雙寫
  - **工單 material_request_ids 用 reverse-lookup**：`MaterialRequestRepository.list_for_work_order(wo_id)` 直接 query（不持久化 list[UUID] 欄位到 work_orders 表，避免 schema migration + FK 不同步風險）
  - **`add_return` 暫不寫 ledger 沖銷**：A5 cost ledger 整合會用 wo finish hook 一次到位（actual_qty vs estimated_qty 算差，把 estimated entry 翻 confirmed + 修正 amount），較精確
- **Reference**:
  - [`work-logs/2026-05/2026-05-09-inventory-repository.md`](work-logs/2026-05/2026-05-09-inventory-repository.md)
  - [`docs/design-notes/m3/DN-03-inventory-material-request.md`](docs/design-notes/m3/DN-03-inventory-material-request.md) §2.3

<details><summary>📜 原始 issue description</summary>

- `modules/workflow/repository/inventory_orm.py`：SQLAlchemy 2.0 mapped class
- `modules/workflow/repository/inventory_repository.py`：CRUD + safety_stock 計算 + adjust
- `modules/workflow/repository/material_request_repository.py`：CRUD + state transition + dispatch_request 雙寫
- 工單 material_request_ids 欄位回填邏輯

Acceptance：
- dispatch_request mid-transaction raise → 庫存 + ledger 同時 rollback
- SELECT FOR UPDATE 並行 dispatch 第二張等第一張 commit 後再讀
- 50+ tests

Depends on: WMOM-20260509-01；Blocks: -03/-04/-05

</details>

---

### WMOM-20260509-03 — MaterialRequest CRUD + state transitions API

- **Status**: done（2026-05-09 完成；A1+A2 同日接力第三輪）
- **Milestone**: M4
- **Priority**: high
- **Estimate**: 0.5 工作天 → **實際 ~半天**（同 A1/A2 session 連續）
- **Owner**: Claude (session 2026-05-09)
- **Completion summary**:
  - ✅ `modules/workflow/schemas/material_request_schemas.py`：8 request body + 3 response model + sub-models
  - ✅ `modules/workflow/routers/material_request_router.py`：9 endpoints + repo factory injection + error mapping helper
  - ✅ `modules/workflow/repository/signoff_repository.py`：加 `create_chain_for_material_request`（mirror work_order 版本）
  - ✅ `modules/workflow/routers/approval_router.py` 擴充：
    - `set_signoff_factories(...)` 加 `material_request` 第三 factory（向後相容預設 None）
    - `approve_step` MATERIAL_REQUEST branch：last step approve → `mr_repo.transition('approve_all')` → `dispatch_request()` atomic 雙寫
    - `reject_step` MATERIAL_REQUEST branch：→ `mr_repo.transition('reject', reject_reason)` 進 REJECTED 終態
  - ✅ `modules/monitoring/server/app.py`：mount `material_request_router`
  - ✅ `dispatch_request` error message 從「must be APPROVED」改為「cannot transition from {status} (must be APPROVED)」讓 router error mapping 正確 map 成 409 Conflict（vs 422）
  - ✅ **27 new tests pass** in 5.35s（含完整 approval auto-dispatch lifecycle / 簽核時 stock 抽走的 edge case / cancel 在 DISPATCHED 不允許 / receive 缺 actual_qty 422 / pagination / unknown 404）
  - ✅ 全 workflow suite 318 pass / cost+workflow 375 pass + 1 xfailed (existing) — **0 regression**
- **Decisions made during impl**:
  - **submit-for-approval 順序**：先建 chain（失敗 raise 422、MR 仍 DRAFT），再 transition MR，最後 backlink chain.id — 避免 inconsistent state
  - **Approval auto-dispatch 兩步**：`approve_all` 進 APPROVED → `dispatch_request()` atomic 雙寫；如 dispatch 失敗（最常見：簽核期間 stock 被別張單抽走），chain 已落地，MR 卡在 APPROVED，回 200 + `subject_transition_error` 訊息給 caller，operator 手動補（去 `/dispatch` endpoint 或 cancel）
  - **MATERIAL_REQUEST chain reject → REJECTED 終態**（vs work_order「reject 回 IN_PROGRESS」）：DN-03 設計 operator 須建新 MR，不就地 resubmit
  - **Error code 區分**：state 不對 → 409 Conflict（caller 改 state 即可恢復）vs request body 缺欄位 → 422 Unprocessable Entity；本 issue 統一用 `"cannot transition"` 字眼
  - **`set_signoff_factories` 加第三個 mr 參數預設 None**：向後相容既有 caller (test_work_order_api.py 兩參數) 不破
- **Reference**:
  - [`work-logs/2026-05/2026-05-09-material-request-api.md`](work-logs/2026-05/2026-05-09-material-request-api.md)
  - DN-03 §2.2 lifecycle + DN-02 D2-Q3 reject 行為差異點

<details><summary>📜 原始 issue description</summary>

- modules/workflow/schemas/material_request_schemas.py：CreateMaterialRequest / DispatchRequest / ReceiveRequest / ReturnRequest / response
- modules/workflow/routers/material_request_router.py：~9 endpoints
- Mount 進 modules/monitoring/server/app.py

Acceptance：
- 30+ pytest（API + repo 整合，含 422/409/404）
- approve last step → 自動觸發 dispatch（approval_router MATERIAL_REQUEST branch）

Depends on: WMOM-20260509-02；Blocks: WMOM-20260509-06

</details>

---

### WMOM-20260509-04 — Inventory query + adjustment API

- **Status**: done（2026-05-09 完成；A1+A2+A3 同日連續第四輪）
- **Milestone**: M4
- **Priority**: high
- **Estimate**: 0.5 工作天 → **實際 ~半天**
- **Owner**: Claude (session 2026-05-09)
- **Completion summary**:
  - ✅ `modules/workflow/schemas/inventory_schemas.py`：5 request body + 6 response model（含 `InventoryItemResponse` 的 `@computed_field` `below_safety` / `total_available`）
  - ✅ `modules/workflow/routers/inventory_router.py`：**8 endpoints**（6 inventory + 2 warehouse extra）+ repo factory injection
  - ✅ Mount 進 `monitoring/server/app.py`
  - ✅ `routers/__init__.py` + `schemas/__init__.py` export 補齊
  - ✅ **28 tests pass** in 1.76s（CRUD / safety filter / metadata partial update / adjust + audit log / 409 insufficient_stock / 404 unknown / 422 validation / pagination / decimal precision）
  - ✅ 全 workflow 346 pass / cost+workflow 403 pass + 1 xfailed (existing) — **0 regression**
- **8 endpoints**:
  - **Inventory (6)**: POST/GET/GET/{id}/PATCH/{id}/POST/{id}/adjust/GET/{id}/adjustments
  - **Warehouse (2 extra)**: POST/GET（給 frontend 建料件前先建倉用，repo 已有 helper 但 ISSUES spec 沒明列；trade-off：避免 ops 手動動 DB）
- **Decisions made during impl**:
  - `InventoryItemResponse` 用 `@computed_field` 計算 `below_safety` / `total_available` — 前端不重複邏輯，避免「frontend 計算 vs backend list 已 filter」不一致
  - PATCH 用 `model_dump(exclude_unset=True)` 配合 repo `update_metadata(**payload)` 乾淨支援 partial update
  - Adjust error mapping：`StockAdjustmentError("not found")` → 404 / 其他 StockAdjustmentError → 422 / `InsufficientStock` → 409（語意：404=不存在 / 422=請求格式錯 / 409=狀態衝突）
  - `list_warehouses` router 走 raw SQL（不另開 repo method） — 用量低，避免 over-engineering
  - SQLAlchemy `Numeric(12, 4)` 保留 4 位小數 → test 用 `Decimal(str) == Decimal("450.00")` 比值不比字串
- **Reference**:
  - [`work-logs/2026-05/2026-05-09-inventory-api.md`](work-logs/2026-05/2026-05-09-inventory-api.md)
  - DN-03 §2.1 + §2.4「歸還與報廢」（adjustment endpoint 支撐紙本流程數位化）

<details><summary>📜 原始 issue description</summary>

- modules/workflow/schemas/inventory_schemas.py：InventoryItemResponse / AdjustmentRequest / SafetyStockAlertResponse
- modules/workflow/routers/inventory_router.py：~6 endpoints
- safety_stock 警示：stock_new + stock_used < safety_stock

Acceptance：
- 25+ pytest pass
- adjustment endpoint 連同 audit log 落地

Depends on: WMOM-20260509-02；Blocks: WMOM-20260509-07

</details>

---

### WMOM-20260509-05 — Cost ledger material entry 整合（estimated → confirmed flow）

- **Status**: done（2026-05-09 完成；A1+A2+A3+A4 同日連續第五輪 — **M4 backend 收官**）
- **Milestone**: M4（部分覆蓋 [WMOM-20260504-11](#wmom-20260504-11--event-driven-cost-ledger-m4-增強) Phase A）
- **Priority**: high（M4 demo flow 的「cost actual 寫入」步驟）
- **Estimate**: 0.5 工作天 → **實際 ~半天**
- **Owner**: Claude (session 2026-05-09)
- **Completion summary**:
  - ✅ schema 擴充：`cost_ledger.py` 加 `source_item_id` (nullable) + `confirmed_at` 欄位 + 新 index `ix_cost_ledger_source_item`，給 confirm flow 精確 lookup
  - ✅ A2 dispatch_request 寫 ledger 時帶 `source_item_id=UUID(it.id)` 給 confirm flow 用
  - ✅ `cost_ledger_repository.py`：CostLedgerRepository（180 行）— get / list (filters + pagination) / find_for_mr_item / list_for_subject / **summary_by_category** (給 A8 月報) / **confirm_entry idempotent**
  - ✅ `cost_ledger_router.py`：2 read-only endpoints + factory injection
    - `GET /api/cost/ledger` — list + filters (farm/from/to/category/status/source_type) + pagination
    - `GET /api/cost/ledger/summary` — group by 4 大類（status=confirmed → actual cost for monthly_report）
  - ✅ Mount 進 `monitoring/server/app.py`
  - ✅ **WO finish hook**：`work_order_router.finish` 結束後呼叫 `_confirm_material_ledger_for_finished_wo` — loop linked MRs，對每個 actual_qty 已填的 line item 用 `actual_qty × current unit_cost` flip estimated → confirmed；hook 失敗不阻擋 finish；test override `set_finish_hook_db_path` 給 lifecycle test 用
  - ✅ Circular import 修：`material_request_repository` 對 cost_ledger imports 改成 lazy（搬進 `dispatch_request` 函式內）；test patch path 跟著改成 `cost_ledger.insert_in_session`
  - ✅ **32 new tests pass** in 3.12s（17 repo + 10 api + **5 lifecycle acceptance**）
  - ✅ 全 workflow + cost combined 435 pass + 1 xfailed (existing) — **0 regression**
  - ✅ **完整鏈路 acceptance test 過**：建料件 → 建工單 → MR linked to WO → submit + 3 階 approve（auto dispatch）→ ledger entry estimated（amount=900 = 2×450）→ receive actual_qty → finish WO → ledger entry confirmed
  - ✅ Edge cases 全測：actual ≠ estimated（amount 翻成 actual×unit_cost）/ MR 未 receive 時 finish（ledger 留 estimated）/ 沒 linked MR 的 finish 正常 / `summary_by_category(status=CONFIRMED)` 拿到 actual cost 給月報用
- **Decisions made during impl**:
  - 加 `source_item_id` 是 schema migration（nullable 安全）— 因為 dispatch 對 N items 寫 N entries，confirm 要 unique lookup
  - `confirm_entry` idempotent：已 confirmed → no-op return；防止 WO reject 後 re-finish 改回 amount
  - finish hook 寫在 router 而非 repository — cross-module concern（讀 MR + inv + ledger）寫 router 比較乾淨，避免 repository 層直接跨 module 耦合
  - finish hook test injection 用 `set_finish_hook_db_path(path)` 而非 factory 三聯（少 boilerplate）；既有 test 不破（override 未設 + FarmRegistry 沒 mock → hook 安靜跳過）
  - **不暴露 ledger POST/PATCH** — ledger 是「事實帳本」所有 mutation 必須走業務 atomic transaction
  - lazy import 解循環：`material_request_repository`→`cost_ledger`→`workflow.orm_models`→workflow.repository.__init__→material_request_repository 的循環
- **Reference**:
  - [`work-logs/2026-05/2026-05-09-cost-ledger-integration.md`](work-logs/2026-05/2026-05-09-cost-ledger-integration.md)
  - DN-03 §2.3「雙寫交易」+ §3.2「與 cost ledger 的綁定」
  - WMOM-20260504-11 (event-driven cost ledger) Phase A 部分覆蓋

<details><summary>📜 原始 issue description</summary>

- 新表 cost_ledger_entry：UUID id / farm_id / category / amount EUR / source_event_id / source_type / status / recorded_at / actor
- dispatch_request 在雙寫 transaction 內 insert(category=material, status=estimated, amount=estimated_qty × unit_cost)
- work_order finish hook：enumerate material_request_ids → 對每筆找對應 ledger entry → 用 actual_qty × unit_cost 改 amount + status=confirmed
- GET /api/cost/ledger?farm_id=...&from=...&to=...&category=...

Acceptance：
- 15+ pytest pass（含 estimated → confirmed transition + actual 與 estimated 差異率記錄）
- 完整鏈路：MR dispatch → estimated → wo finish → confirmed — 一次測過

Depends on: WMOM-20260509-03；Blocks: WMOM-20260509-08

</details>

---

### WMOM-20260509-06 — `/admin/workflow/material` 領料單 frontend

- **Status**: done（2026-05-18，PR pending）
- **Milestone**: M4
- **Priority**: high
- **Estimate**: 1 工作天 → **實際 1 天**
- **UI directive（WMOM-20260507-01 後）**：使用 `frontend/components/ui/` + `frontend/theme/`，不可 Tailwind / 硬 hex。Modal 套既有 [`WorkOrderDetailModal`](frontend/components/workflow/WorkOrderDetailModal.tsx) 風格（Card padding=0 + DM Serif title + 底部 Btn）。
- **Description**:
  - `frontend/services/materialService.ts`（API client，模式同 workOrderService）
  - `frontend/hooks/useMaterialRequests.ts`
  - `frontend/components/workflow/MaterialRequestListPanel.tsx`：列表 + status filter + 工單關聯 search
  - `frontend/components/workflow/CreateMaterialRequestWizard.tsx`：建單精靈（選工單 → 加料件明細 → 估計工時 → submit-for-approval）
  - `frontend/components/workflow/MaterialRequestDetailModal.tsx`：詳情 + state transition buttons（dispatch / receive / close / cancel / 建退料）
  - 改 [`WorkflowPage.tsx`](frontend/components/workflow/WorkflowPage.tsx)：加 `material` tab（與 orders / approval 並列；approval tab 已預留 subject_type filter 直接吃 material_request）
- **Acceptance**:
  - ✅ tsc clean / vite build pass（3.56s, 743 modules）
  - ✅ demo flow 已對齊 backend：建工單 → 開領料單 → submit → approval tab 用 LEADER / TREASURY 簽 → 領料單自動 DISPATCHED → 點 receive 填 actual_qty（每個 transition 對應的 backend endpoint 已驗證）
- **Depends on**: WMOM-20260509-03
- **Blocks**: -
- **Result**:
  - 8 new files：materialService / useMaterialRequests / useInventoryItems / MaterialRequestListPanel / CreateMaterialRequestWizard / MaterialRequestDetailModal / statusUtils 擴 + WorkflowPage 加 `material` tab
  - code-reviewer subagent 找出 2 must-fix + 4 should-fix + 3 nice-to-have：
    - Must #1: `fmtDateTime` / `fmtDate` 改用 `Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Taipei' })` 明確 Asia/Taipei format
    - Must #2: `selectedMR` sync 依賴 `mrHook.rawItems`（未 filter）避免 search 期間 stale
    - Should #1: backdrop click 在 cart 有料件時加 `window.confirm` 防誤關
    - Should #2: `mrStatusTone` 改進度感漸進色（dispatched=accent / received=accent / used=ok / closed=ok）
    - Should #3 / #4 + Nice #1 / #3：留 follow-up（fetch AbortController signal pass-through / SKU+name join / 排序意圖 comment / useCallback dep）
  - Follow-up issue：WMOM-20260518-01（MR detail modal 料件表加 SKU+name 顯示，需 backend join）
  - PR：claude/issue-WMOM-20260509-06-2026-05-18
  - Work-log：work-logs/2026-05/2026-05-18-material-request-frontend.md

---

### WMOM-20260509-07 — `/admin/workflow/inventory` 庫存 frontend

- **Status**: done（2026-05-18）
- **Milestone**: M4
- **Priority**: high
- **Estimate**: 0.5-1 工作天 → **實際 0.5 工作天**
- **UI directive**：同 -06。
- **Description**:
  - ✅ `frontend/services/inventoryService.ts`（完整 8 endpoint：6 inventory + 2 warehouse）
  - ✅ `frontend/hooks/useInventory.ts`（list + adjust + listAdjustments + warehouses sub-fetch）
  - ✅ `frontend/components/workflow/InventoryListPanel.tsx`：warehouse filter / below_safety toggle / 三欄 stock / LOW pill / border-left 4px warn 警示
  - ✅ `frontend/components/workflow/InventoryAdjustmentDialog.tsx`：delta_kind / 整數 delta / reason 必填 + 預覽顯示 `qty + delta = next` 含 negative 警告
  - ✅ `frontend/components/workflow/InventoryDetailDrawer.tsx`：右側 480px drawer + audit log + 觸發 adjust dialog（z=300 over drawer z=180）
  - ✅ 改 `WorkflowPage.tsx`：加 `inventory` tab + selectedInvItem rawItems sync + invHook 接合
  - ✅ 擴 `statusUtils.ts`：`locationKindLabel` for warehouse location enum
- **Acceptance**:
  - ✅ tsc clean / vite build pass（748 modules, 4.47s）
  - ✅ safety_stock 警示視覺正確：border-left 4px warn + LOW pill + filter toggle
- **Depends on**: WMOM-20260509-04（done）
- **Blocks**: -
- **Result**:
  - Backend 未動 — 512 passed + 1 xfailed + 3 pre-existing numpy drift（與 main baseline 一致 zero regression；今日 flaky concurrency test 通過）
  - PR：claude/issue-WMOM-20260509-07-2026-05-18
  - Work-log：work-logs/2026-05/2026-05-18-inventory-frontend.md

---

### WMOM-20260509-08 — Reporting backend（monthly_report.py PDF + annual_budget.py）

- **Status**: done（2026-05-10，PR pending merge）
- **Milestone**: M4（後半 — 不依賴 inventory，可平行）
- **Priority**: high（M6 客戶第一份月報沒被退是 done criteria）
- **Estimate**: 1.5 工作天 → **實際 1 天**
- **Description**:
  - `modules/reporting/services/monthly_report.py`：
    - 取資料：cost ledger（material/labour/equipment/revenue_loss 4 類加總）+ work order 完工統計（CORRECTIVE / PREVENTIVE / INSPECTION 計數）+ 物理模擬 availability（time / energy）
    - 渲染：HTML template（Jinja2 + inline CSS）→ PDF（**reportlab** — Windows weasyprint 撞 Pango DLL）
    - 內容：封面 + 摘要 KPI + 4 類成本明細 + 工單統計 + availability + 重大事件 timeline
  - `modules/reporting/services/annual_budget.py`：12 個月 forecast（過去用 actual / 當月 actual_partial / 未來月 historical_average rolling 3 月）
  - `modules/reporting/routers/reporting_router.py`：
    - `POST /api/reporting/monthly?farm_id=...&year=...&month=...&format=pdf|html|json` → returns PDF binary / HTML preview / JSON 結構化資料
    - `POST /api/reporting/annual-budget?farm_id=...&year=...&format=pdf|json`
    - `GET /api/reporting/templates` → 可用 template 列表
  - `modules/reporting/templates/monthly_report.html`（Jinja2）+ `static/reporting.css` + `services/_pdf_styles.py`（共用 reportlab style）
- **Acceptance**:
  - ✅ 跑得出真實 PDF（PDF magic bytes + ≥1KB + 重複 render size 一致 — `test_render_pdf_*` 4 個測試）
  - ✅ 月報內容 4 大區塊正確（KPI / cost / work orders / availability — `test_monthly_report_data_full_assembly`）
  - ✅ **56 pytest** pass（含 8 個 review fix regression test，超過 25 acceptance）
- **Depends on**: WMOM-20260509-05（要從 cost ledger 讀 confirmed material cost）
- **Blocks**: WMOM-20260509-09
- **Result**:
  - Backend 全 446 → **502 passed, 1 xfailed (zero regression)**
  - code-reviewer subagent 找出 4 must-fix + 4 should-fix 全修：
    - Must #1: `in_progress` WO 跨月雙計（用 `open_states()` + `closed_at` 上下界）
    - Must #2: annual budget current_month 區隔 `actual_partial` 與 `actual`，forecast 解耦
    - Must #3: Content-Disposition header injection 防護（`_safe_filename_token`）
    - Must #4: `compute_notable_events` 共用 WO snapshot 避免雙倍 query
    - Should #1: `history_window > 12` guard 給明確錯誤
    - Should #2: `_WO_FETCH_PAGE_SIZE` 抽常數
    - Should #3: `_pdf_styles.py` 共用 reportlab style
    - Should #4: HTML preview inline CSS（避免 API endpoint 載不到外部檔）
  - Nice-to-have 4 條留 follow-up（_month_period 兩處實作 / notable_events 加 stalled 類型 / `_jinja_env` thread race / `_FARM_REGISTRY` setter coupling）
  - PR：[claude/issue-WMOM-20260509-08-2026-05-10]
  - Work-log：work-logs/2026-05/2026-05-10-reporting-backend-monthly-pdf.md

---

### WMOM-20260509-09 — `/admin/reports` frontend（月報生成 + 年度預算）

- **Status**: done（2026-05-10，PR pending）
- **Milestone**: M4
- **Priority**: high
- **Estimate**: 1 工作天 → **實際 1 天**
- **UI directive**：同 -06（走 ui 元件庫 / 不硬寫 hex / 全 theme palette）
- **Description**:
  - ✅ `frontend/services/reportingService.ts`（typed client + downloadBlob helper）
  - ✅ `frontend/hooks/useReports.ts`（monthly + annual sub-state mgmt）
  - ✅ 新主頁 `frontend/components/reporting/ReportsPage.tsx`，nav 加 `reports` 主項 + NavIcon (document with mini bar chart)
  - 子元件：
    - ✅ `MonthlyReportPanel.tsx`：year/month picker → generate → KPI cards + cost breakdown table + iframe HTML preview + PDF download
    - ✅ `AnnualBudgetPanel.tsx`：year + current_month picker → KPI + recharts BarChart + 12-month table + PDF download
  - ✅ `formatters.ts` 共用 fmtMoneyDecimal / fmtPct
- **Acceptance**:
  - ✅ 點按鈕後 30 秒內拿到 PDF binary，瀏覽器自動下載（`downloadBlob` helper + 1s revoke timeout）
  - ✅ 走 ui 元件庫；NavIcon `reports` 加 document-with-bar-chart icon
- **Depends on**: WMOM-20260509-08
- **Blocks**: -
- **Result**:
  - `npx tsc --noEmit` → 0 errors；`npx vite build` → 5.29s，733 modules
  - code-reviewer subagent 找出 4 must + 6 should + 4 nice，採納 11 條全修：
    - Must #1: iframe `srcDoc` 加 `sandbox=""` 完全隔離（XSS 防護）
    - Must #2: `buildQuery` 型別簽章對齊 runtime guard（加 null）
    - Must #3: generate error / download error 拆兩個獨立顯示框
    - Must #4: `farmLoaded` state 區分 loading vs 無 active farm 避免無限 loading
    - Should #1: `formatters.ts` 抽共用 fmtMoneyDecimal（兩 panel 重複定義 + null 行為分歧）
    - Should #2: 移除 dead exports `ReportFormat` / `AnnualFormat`
    - Should #6: year range 擴 -4~+1（multi-year O&M）
    - Nice #1: recharts future months `actual=null` 不畫 0 bar
    - Nice #2: 移除未使用的 `useReports.reset`
    - Nice #3: 移除 PageHeader sub backend impl 細節 leak
  - PR：[claude/issue-WMOM-20260509-09-2026-05-10]
  - Work-log：work-logs/2026-05/2026-05-10-reports-frontend.md

---

### WMOM-20260509-10 — E2E lifecycle test（pytest 兩層 + demo orchestrator placeholder）

- **Status**: done（2026-05-13）
- **Milestone**: M4 收官（A6/A7/A9 done 後）
- **Priority**: high（**ROADMAP M4 demo flow 的 acceptance**）
- **Estimate**: 1-1.5 工作天 → **實際 0.5 工作天**
- **完成**:
  - Layer A：`tests/e2e/test_fault_to_signoff_lifecycle.py` 6 個 test（3 happy CORRECTIVE/PREVENTIVE/INSPECTION + 2 unhappy reject-retry + insufficient-stock + 1 timing sentinel），全 pass in 1.88s（acceptance < 60s 通過）
  - Layer B：`frontend/components/demo/DemoOrchestratorPage.tsx` skeleton placeholder（tsc clean）
  - Mock simulator/fault：暫以 `source_alarm_code` 字串模擬 fault trigger；真接 SCADA simulator 留 follow-up WMOM-20260513-02
  - Code review subagent 找 4 must-fix + 7 should-fix；must-fix 全修 + 多數 should-fix 採納
  - 關鍵驗證：3 階 approve 後 MR DISPATCHED + stock 扣 + ledger ESTIMATED 中間狀態（擋 dispatch guard regression）
  - PR：claude/issue-WMOM-20260509-10-2026-05-13
  - Work-log：work-logs/2026-05/2026-05-13-a10-e2e-lifecycle-test.md
- **Description**:
  把「運轉資料 → 故障觸發 → 派工 → 開單 → 領料 → 排除 → 紀錄 → 簽核」全鏈路串起來測。

  **Layer A — Pytest integration test**（每個 PR 自動跑）
  - `tests/e2e/test_fault_to_signoff_lifecycle.py`：
    - Step 1：啟動 simulator + 載 demo farm（fixture）
    - Step 2：注入 fault scenario（gearbox_temp_high）
    - Step 3：assert SCADA tag delta + alarm code 觸發
    - Step 4：建 corrective 工單（priority=high，from alarm code）
    - Step 5：dispatch → start_work
    - Step 6：建 material_request（gearbox bearing × 1）→ submit_for_approval
    - Step 7：approve 3 階 chain（employee → leader → treasury）→ 自動 dispatch
    - Step 8：assert inventory.stock_new -1 + ledger entry status=estimated
    - Step 9：work order update_progress + finish（actual_qty=1）
    - Step 10：assert ledger entry status=confirmed
    - Step 11：approve 工單 chain（employee → leader）
    - Step 12：assert wo=CLOSED + signoff chain=APPROVED
    - 跑 PREVENTIVE / INSPECTION 兩個變體 happy path

  **Layer B — Demo orchestrator placeholder**（M5/M6 時做完整 UI）
  - `frontend/components/demo/DemoOrchestratorPage.tsx`（**只放 skeleton + step list**，實作留 M5）
  - 標記 follow-up issue 給 M5 接力
- **Acceptance**:
  - Layer A：25+ pytest pass，覆蓋 corrective + preventive + inspection 三條 happy path + 2 條 unhappy path（簽核 reject 後重試 / dispatch 在 stock 不足下 fail）
  - Layer A 跑完 < 60 秒（in-memory SQLite + simulator 不寫 DB）
  - Layer B：skeleton 通 tsc，留下明確的 follow-up issue WMOM-2026XX-XX
- **Depends on**: WMOM-20260509-06、-07、-09
- **Blocks**: -
- **Reference**:
  - ROADMAP M4 demo flow
  - 前 issue 提的 [WMOM-20260507-02](#wmom-20260507-02) placeholder 按鈕清單（demo orchestrator 上線後可清掉「+ 新報告」入口）

---

## M4 backend 後續 follow-up（2026-05-09 code review 留下的 should-fix / nice-to-have）

> A1-A5 backend 5 issue 全 done 後，code-reviewer subagent 找出 3 must-fix（已在
> WMOM-20260509-review-fixes-2026-05-09 修完）+ 4 should-fix + 2 nice-to-have。
> Must-fix 已修；以下 6 項列為下次 session 接力處理的 follow-up issues。
> 優先級：A6 frontend 主線優先；以下若有空再插。

### WMOM-20260509-F1 — `add_return` 寫 ledger 沖銷

- **Status**: done（2026-05-19 完成；branch `claude/nice-brown-6DM0J`）
- **Milestone**: M4 後續（不阻塞 frontend）
- **Priority**: medium（demo 給客戶看月報時會被發現偏高）
- **Estimate**: 0.5 工作天 → **實際 ~3 小時**（含 code-review must-fix 採納）
- **Source**: 2026-05-09 code review Should-fix #2
- **Owner**: Claude（session 2026-05-19，autonomous daily worker）
- **Completion summary**:
  - ✅ Backend repo `add_return()` 升級為 atomic 三寫（stock + MaterialReturn + ledger offset entry）
  - ✅ 沖銷 entry 設計：`amount = -(qty × locked_unit_cost from dispatch entry)`；`status=CONFIRMED + confirmed_at=now`；`source_item_id = MaterialReturn.id` 區隔 dispatch entry 的 mr_item.id，避開 wo finish hook `find_for_mr_item` 撈出多筆 collision
  - ✅ 加 `_lookup_offset_unit_cost(sess, request_id, item_id, return_to_kind)` static method：
    - Step 1 找 dispatch ledger entry 取 `locked_unit_cost`（會計一致性原則 — dispatch 後漲價也用鎖定值）
    - Step 2 fallback 查當前 `inventory.unit_cost`
    - Step 3 都沒 → None（caller log warning + skip ledger entry，stock + MaterialReturn 仍寫）
  - ✅ Cross-kind return 語意（dispatch NEW → return USED）docstring 補強 + test 涵蓋
  - ✅ 月報 `summary_by_category(CONFIRMED)` 退料後不再偏高（測試驗證：dispatch confirmed +900 + return confirmed -450 = +450）
  - ✅ 新增 17 個 test（`test_add_return_ledger_offset.py`）：happy path 3 + 月報視角 3 + wo hook 互動 1 + fallback 3 + multi 2 + atomic 1 + cross-kind 1 + mid-state 1 + cross-cutting 2
  - ✅ Backend `python -m pytest modules/{workflow,cost,reporting}/tests/ tests/e2e/` → 551 passed (+17 new) + 1 xfailed + 3 pre-existing numpy drift — **zero regression**
  - ✅ Code-reviewer subagent 找 4 must-fix + 4 should-fix + 3 nice-to-have，**採納 10/11**（剩 1 nice-to-have lazy import 重構為 scope creep 不採納）：
    - MF#1 拿掉 `_ = CostLedgerEntryORM` over-import hack
    - MF#2 加 docstring 警示「超量退料」會計邊界 + 開 follow-up WMOM-20260519-01
    - MF#3 ISSUES.md / STATUS.yaml 同 commit 更新
    - MF#4 fallback test 加 assert 確認不產生 warning（caplog dead param 修正）
    - SF#1 cross-kind return 語意 docstring + 新 test
    - SF#2 REPAIRING 退料路徑同 USED 邏輯，cross-kind test 已涵蓋
    - SF#3 caplog 指定 logger name
    - SF#4 work-log §2.3 mid-state 描述修正 + 新 test
    - N#1 inventory fallback 月報視角新 test
    - N#3 work-log TODO 全勾
- **Files changed**:
  - `M modules/workflow/repository/material_request_repository.py` — `add_return` + `_lookup_offset_unit_cost`
  - `+ modules/workflow/tests/test_add_return_ledger_offset.py` — 19 tests, 600+ lines
  - `+ work-logs/2026-05/2026-05-19-f1-add-return-ledger-offset.md`
- **Reference**: code review subagent 報告 Should-fix #2
- **Blocks**: -
- **Spawns**: WMOM-20260519-01（超量退料 domain guard 評估）

---

### WMOM-20260519-01 — `add_return` 超量退料 domain guard 評估（F1 follow-up）

- **Status**: done（2026-06-08 完成；branch `claude/issue-followups-2026-06-08`）
- **Completion summary**:
  - ✅ `_assert_return_within_physical_ceiling`（採 PR #41 review-後 semantic）：`physical_ceiling = actual_qty if set else estimated_qty`，聚合 by (request_id, item_id) 跨 stock_kind；`max_returnable = Σ ceiling − 已退`，超量 → `MaterialRequestRuleViolation`（router 對映 422）
  - ✅ add_return MR row `with_for_update` 序列化並發退料；三寫前先擋（atomic rollback）
  - ✅ tests：`test_add_return_over_return_guard.py` 7（estimated/cumulative/received-actual 降上限/not-in-MR/atomic + 2 happy）；修 1 個編碼 F1-bug 的舊測試（estimated 1→2）
  - ✅ 全 backend 721 passed / 1 xfailed 零 regression
- **Reference**: [`work-logs/2026-06/2026-06-08-followups.md`](work-logs/2026-06/2026-06-08-followups.md)
- **Milestone**: M4 後續
- **Priority**: medium-low（影響月報極端場景；正常 lifecycle 不觸發）
- **Estimate**: 0.5-1 工作天
- **Source**: 2026-05-19 WMOM-20260509-F1 code review Must-fix #2
- **Description**:
  WMOM-20260509-F1 完成「add_return 寫 ledger offset entry」後，發現一個會計邊界：
  - dispatch estimated 2 件 @ 300 = 600 estimated entry
  - wo finish 填 actual=1 → confirm 翻 dispatch entry 為 confirmed 300
  - **若退料 2 件**（合法呼叫，但業務上不該；qty ≤ stock 可派出量，stock 加回未 guard）→ return entry -600 confirmed
  - confirmed 視角 = 300 + (-600) = **-300**（負值材料成本，月報異常）

  F1 scope 不加 guard，docstring 標註「caller 責任」。本 follow-up issue 評估：
  1. 是否要在 domain 層加 guard：`qty <= (estimated_qty or dispatched_qty - already_returned_qty - actual_consumed)`
  2. 或在 router 層擋
  3. 或保留現狀 + 在 UI 層擋（field engineer 介面禁止超量輸入）
  4. 是否要查 wo finish hook 後 actual_qty 才能驗證「actual_consumed」

  決策後實作 + 加 negative path test。

- **決策（2026-06-08，PR triage salvage）**：採 **PR #41**（branch `claude/nice-brown-KxhlK`）的 review-後 semantic，**不**採 #40 的 `dispatched−consumed` 版。#40/#41 兩條 stale PR 已關（帶 2-3 週前 stale 追蹤檔、與 main 79-commit 落差會衝突），邏輯收進本 issue 之後在最新 main 上**重做乾淨分支**：
  - guard 公式：`physical_ceiling per-line = (actual_qty if set else estimated_qty)`；`max_returnable = Σ physical_ceiling − already_returned`
  - 聚合 by `(request_id, item_id)`，跨 stock_kind / return_to_kind 支援 cross-kind return（dispatch NEW → return USED）
  - 實作位置：`add_return` 內先對 MR row `SELECT FOR UPDATE`（序列化）→ `_assert_return_within_physical_ceiling` static helper guard → 失敗回 422 繁中錯誤，stock/return/ledger 三邊 atomic rollback
  - tests：11 negative+happy（單次/累進/已簽收/未在MR/DRAFT/cross-kind/multi-line/atomic 累計不變）+ 修 2 個編碼 F1-bug 的舊 test
  - 衍生 follow-up **WMOM-20260519-02**（`_guard_receive` 加 `actual_qty ≤ estimated_qty` 上限校驗）
  - 來源完整 review 紀錄：已關閉的 PR #41 body（3 MF + 6 SF + 3 NH，採納 9/12）
- **Files候選**：
  - `modules/workflow/repository/material_request_repository.py:add_return`
  - 或 `modules/workflow/domain/inventory.py:MaterialRequest`（新 domain method）
- **Depends on**: WMOM-20260509-F1（done）
- **Blocks**: 月報極端場景 demo（如果客戶 demo 時操作「過度退料」會看到負值）

---

### WMOM-20260509-F2 — `list_items` / `list` 用 `func.count` 而非 Python `len`

- **Status**: done（2026-05-21 完成；F2-F5 cleanup batch；branch `claude/blissful-turing-nR5qR`）
- **Milestone**: M4 後續
- **Priority**: low（資料量 < 1000 不影響）
- **Estimate**: 0.5 小時
- **Source**: 2026-05-09 code review Should-fix #1
- **Description**:
  `inventory_repository.list_items` 與 `material_request_repository.list` 用
  `total = len(sess.execute(count_stmt).scalars().all())` 把所有 id 撈回 Python 才算 `len`。改為 SQL-side count：
  ```python
  from sqlalchemy import func, select
  count_stmt = select(func.count()).select_from(base.subquery())
  total = sess.execute(count_stmt).scalar_one()
  ```
- **Files**（已改）：
  - `modules/workflow/repository/inventory_repository.py`（list_items）
  - `modules/workflow/repository/material_request_repository.py`（list）

---

### WMOM-20260509-F3 — `list_warehouses` 加 repo method（移出 router raw SQL）

- **Status**: done（2026-05-21 完成；F2-F5 cleanup batch）
- **Milestone**: M4 後續
- **Priority**: low（cosmetic）
- **Estimate**: 0.5 小時
- **Source**: 2026-05-09 code review Should-fix #4
- **Description**:
  `inventory_router.list_warehouses` 直接用 `repo._sessionmaker()` query ORM，violates repository 封裝。已在 `InventoryRepository` 加 `list_warehouses(farm_id) -> list[Warehouse]`；router 改用該 method（兩行收尾）。

---

### WMOM-20260509-F4 — `_FARM_REGISTRY` lazy singleton 抽 shared

- **Status**: done（2026-05-21 完成；F2-F5 cleanup batch）
- **Milestone**: M4 後續
- **Priority**: low（cosmetic refactor）
- **Estimate**: 1 小時
- **Source**: 2026-05-09 code review Should-fix #5
- **Description**:
  4 個 routers 各自重複 `_FARM_REGISTRY` lazy singleton + `_resolve_farm_db_path`：
  - `inventory_router.py`
  - `material_request_router.py`
  - `approval_router.py`
  - `cost_ledger_router.py`
  抽成 `shared/farm_registry_provider.py` 一個共用 singleton（lazy import + cached + threading.Lock）。
- **Follow-up note**：實作過程中發現 `work_order_router.py` 與 `reporting/routers/reporting_router.py` 也有相似 pattern（不同 helper 名 `_get_default_farm_registry` / 同名 `_resolve_farm_db_path`）。本 issue scope 只列 4，未動那兩個；後續若再次 review 可一併收進來。

---

### WMOM-20260509-F5 — `InventoryAdjustmentLog.actor_id` 改 Optional

- **Status**: done（2026-05-21 完成；F2-F5 cleanup batch）
- **Milestone**: M4 後續
- **Priority**: low
- **Estimate**: 15 分鐘
- **Source**: 2026-05-09 code review Nice-to-have #1
- **Description**:
  原 `actor_id: UUID` 必填。系統自動 adjust（hook / scheduler）被迫塞 fake UUID。已改 Optional：
  - `InventoryAdjustmentLog.actor_id: UUID | None = None`（domain dataclass）
  - `InventoryAdjustmentLogORM.actor_id` 改 nullable
  - `AdjustInventoryRequest.actor_id` + `AdjustmentLogResponse.actor_id` 改 `Optional[UUID]`
  - `InventoryRepository.adjust()` 簽名 + `_log_to_domain` 加 None 分支
  - SQLite 自動生效；PostgreSQL ALTER 留 M6 部署（F6 PG issue）。

---

### WMOM-20260509-F6 — PostgreSQL row-lock integration test

- **Status**: open
- **Milestone**: M6（生產部署前）
- **Priority**: medium
- **Estimate**: 0.5 工作天
- **Source**: 2026-05-09 code review Nice-to-have #2
- **Description**:
  目前並發 dispatch SQLite test 只能驗 SQLite WAL 序列化行為，**無法驗 PostgreSQL `SELECT FOR UPDATE` 真實 row-lock 語意**。M6 客戶部署前如選 PostgreSQL backend，需補：
  - 起 docker postgres 跑 integration test
  - 兩 client 同時 dispatch 同 item，驗第二個被 block 直到第一個 commit/rollback
  - test 在 CI（GitHub Actions）上跑

---

### WMOM-20260522-01 — F4 follow-up：`work_order_router` + `reporting_router` 也改用 shared FARM_REGISTRY

- **Status**: done（2026-05-22 完成；branch `claude/issue-WMOM-20260522-01-2026-05-22`）
- **Milestone**: M4 後續（F4 收尾）
- **Priority**: low（cosmetic refactor，純結構整理）
- **Estimate**: 0.5-1 小時 → **實際 ~1 小時**
- **Owner**: Claude（session 2026-05-22 autonomous daily worker）
- **Source**: WMOM-20260509-F4 follow-up note（2026-05-21 cleanup batch 實作時發現）
- **Completion summary**:
  - ✅ `work_order_router.py`：刪 `_FARM_REGISTRY` global + `_get_default_farm_registry()` 函式；
    `_default_repository_factory` 收成一行 `get_repository(resolve_farm_db_path(farm_id))`；
    `_resolve_db_path_for_finish_hook` 用 try/except HTTPException 包 shared 呼叫 — finish hook
    失敗（registry 不可用 / farm 不存在）安靜返回 None 不阻擋工單收尾；
    `set_repository_factory(None)` 改呼叫 `reset_farm_registry()`
  - ✅ `reporting_router.py`：刪 `_FARM_REGISTRY` global + `_resolve_farm_db_path()` 函式；
    `_get_ledger_repo` / `_get_wo_repo` 直接呼叫 shared；`set_ledger_factory(None)` /
    `set_work_order_factory(None)` 各自呼叫 `reset_farm_registry()`（與 4 個 F4 routers 對齊）；
    `set_availability_provider` **不** reset（與 farm 解析無關，已加 regression test 守住）
  - ✅ 10 個新 regression test（5 work_order + 5 reporting）：
    - setter None → shared singleton 被清
    - router 不再有 local `_FARM_REGISTRY` global（防止後續再加回 local cache）
    - finish hook 在 shared raise HTTPException(500) / 404 時安靜返回 None
    - finish hook override 仍優先於 shared lookup
    - reporting `set_availability_provider` 不動 shared registry
    - reporting `_get_ledger_repo` / `_get_wo_repo` 在 factory=None 真的走 shared 路徑（N1）
  - ✅ Backend baseline zero regression：715 passed + 1 xfailed + 3 pre-existing numpy drift（與 main 一致）；
    2 deselected = 環境 flaky concurrency dispatch tests（main baseline 也偶爾 fail，與本 PR 無關）
  - ✅ Code review 1 must + 2 should + 1 nice：採納 must（`__builtins__` patch 改 monkeypatch shared
    function）+ should-2（teardown 不重複 reset）+ nice-1（加 N1 test 驗 production code path）；
    should-1（HTTPException coupling 全 6 router 統一，shared 改 exception 需擴大 scope 到 F4 batch
    — 本 PR 不擴大）
- **Reference**:
  - [`work-logs/2026-05/2026-05-22-f4-followup-work-order-reporting.md`](work-logs/2026-05/2026-05-22-f4-followup-work-order-reporting.md)
  - WMOM-20260509-F4 follow-up note

---

## 物理模型強化（M3 並行 / 從 digiWT 階段延續未完工）

> 來源：`docs/physics_model_status.md` 「Still missing」段 + `examples/data_quality_report.txt` 3 項 fail + `docs/legacy/digiwt_TODO.md` 仍 open 項。
> 商業 demo 風險（P0）優先；學術深度（P2）可拖到 M5 之後。
> 開工順序建議：**-23（測試骨架）→ -24（data quality 修正）→ -25（前端可視化）→ 看 M3 frontend 進度再決定 -26/-27/-28**。

---

### WMOM-20260505-23 — Physics 自我驗證框架（self-validation framework）

- **Status**: done（Layer 1-7 全 2026-05-06 完成）
- **Milestone**: M3 並行（infrastructure，不卡 workflow）
- **Priority**: critical（**P0 — 物理正確性的根基；劉老師 2026-05-05 review 強調「不能只是說有採用，要知道結果是否準確」**）
- **Estimate**: 4-6 工作天 → **實際 1 天連跑完 7 layer**
- **Progress log**:
  - 2026-05-06：Layer 1（Conservation Laws）完成 — 36 tests pass（Betz / 能量 / 動量 / 角動量 / 熱平衡 / 質量守恆 + sentinel）；負向測試確認可 catch（將 `TurbineSpec.cp_max` 0.45→0.70 觸發 fail，回報 V=4.0 m/s 時 Cp=0.6270 > 0.5926）；`tests/physics/` 骨架（conftest.py + reports/README）就位
  - 2026-05-06：Layer 2（Literature/Standard Benchmarks）完成 — 35 tests pass（IEC 61400-1 Kaimal / Bastankhah-Niayifar wake / Glauert NTF / Tedric Harris BPFO/BPFI / ISO 10816-3 Class III / Walther viscosity decay / ISA air density）；負向測試 `_brg_n_elements` 23→30 → BPFO test 4 cases FAIL（rel_err 30%）。Layer 1+2 合計 71 tests pass in 1.45 s
  - 2026-05-06：Layer 3（Operating Envelope）完成 — 18 tests pass（cut-in/cut-out 行為、emergency stop 5s 衰減 50%、pitch rate ≤10°/s、yaw rate ≤0.5°/s、rotor overspeed software 保護、direct-drive + geared slip < 5%）。
  - 2026-05-06：Layer 4（Cross-module Consistency）完成 — 9 tests pass（Region 2 cubic R²>0.95 實測 0.99、stator-power lag-correlation 峰值在 240-600 s、inter-turbine spread > 0 且 < 50%、Region 3 power CV 結構性 bound、stability coupling 方向正確）。設計避開 calibration value（spread/CV）由 WMOM-24 收緊。
  - 2026-05-06：Layer 5（Fault Injection Signatures）完成 — 23 tests pass（11 個 fault scenarios 各驗 1-2 個 SCADA tag delta + healthy baseline ISO Zone A/B + power 偏離 lookup < 30%）。Layer 1-5 合計 121 tests pass。
  - 2026-05-06：Layer 6（Health Check CLI）完成 — `tools/physics_health_check.py` 一鍵體檢 entry，subprocess 跑 Layer 1-5 + 短模擬 5 turbines × 30 min（含 1 fault）+ 4 大健康分級 + markdown/JSON/figures 產出。Exit code 0/1 適合 CI。
  - 2026-05-06：code-reviewer subagent 對 Layer 1-6 做 review，找出 3 blockers + 6 suggestions；3 blockers + 3 suggestions 已修（B-1 Kaimal stable/unstable 重疊條件、B-2 settle_steps 不一致、B-3 mean_dict 缺 key 問題）。fix 後 121 tests 仍全 pass。
  - 2026-05-06：Layer 7（Test Report Persistence）完成 — `tests/physics/conftest.py` 加 pytest_sessionfinish hook，自動寫入 `reports/{YYYY}/{MM}/{ts}-pytest.{md,json}` 含 YAML metadata + baseline_drift 比對。`_baseline/pytest_baseline.{md,json}` 已建立。
  - **整體驗收**：121 pytest tests pass in ~25 s，health check CLI 4/4 PASS，Layer 1-7 全部 closed。
- **Source**:
  - 劉老師 2026-05-05 review：物理模型要有自我測試機制，要能驗證結果準確性
  - `docs/legacy/digiwt_TODO.md` Testing 段（issue #52 升級版）
- **Description**:
  既有物理模組 14 個 + 26 條進階修正（#61~#127），但只有 `examples/data_quality_analysis.py` 一個半自動 21 項 check。**痛點**：
  1. **不驗證物理定律 / 文獻 benchmark** — Betz 限、IEC 61400-1 Kaimal、ISO 10816、Bastankhah wake 文獻值都沒比對
  2. **不驗證故障注入 sanity** — `bearing_wear` 注入後 HF band 該升、`gearbox_overheat` 注入後 oil_temp 該升 — 沒人自動驗
  3. **不驗證跨模組一致性** — rotor power × η_drivetrain × η_converter ≈ P_elec 沒驗
  4. 改 physics 只能「憑感覺」 — 改完跑一次看儀表板，遺漏邊角 case 沒人發現
  
  **「regression test（鎖住現況）」與「validation（驗證物理正確）」是兩件事**，本 issue 兩者都要做，但**重點是後者**。

- **Deliverable**（6 層 validator，每層獨立 commit）：
  
  **Layer 1 — Conservation Laws / Physical Bounds（守恆律 + 物理上限）**
  - `tests/physics/test_invariants.py`
  - Betz 限：所有 (V, λ, β) 條件下 Cp ≤ 0.593
  - 能量守恆：P_aero × η_drivetrain × η_converter ≈ P_elec（容差 ±5%）
  - 動量平衡：thrust × V_∞ × A 與 aero power 透過動量定理對得上
  - 角動量：rotor_speed × gearbox_ratio ≈ generator_speed（含 slip 容差）
  - 熱平衡：input heat - removed heat = thermal mass × dT（熱慣性容差）
  - 質量守恆（冷卻液）：level decay 與 leak rate 對得上
  
  **Layer 2 — Literature / Standard Benchmarks（文獻 / 標準 benchmark）**
  - `tests/physics/test_benchmarks.py`
  - **IEC 61400-1 Kaimal**：σ_v / V_mean ≈ TI（強風下測）
  - **Bastankhah wake**：Ct=0.82, TI=8%, x=5D → deficit 落 25-35%（Niayifar & Porté-Agel 2016）
  - **Glauert NTF**：Region 2 a≈0.33 → V_raw/V_∞ ≈ 0.84（IEC 61400-12-1 Annex D）
  - **BPFO/BPFI**：n=23, d/D=0.18, α=10° → 計算值對應 Tedric Harris formula
  - **ISO 10816-3 Class III**：vibration RMS zone boundaries（A < 2.3, B 2.3-4.5, C 4.5-7.1, D > 7.1 mm/s）
  - **Walther viscosity**：cold-start 後 ~10 min decay 達 ~63% 穩態值
  - **Air density (ISA 15°C, dry)**：1.2250 kg/m³ ± 0.5%（WMOM #101）
  
  **Layer 3 — Operating Envelope（操作邊界）**
  - `tests/physics/test_envelope.py`
  - cut-in 以下 → power < 1 kW、rotor 漸停
  - cut-out 以上 → 30 s 內 power 歸零、進 stop 狀態
  - emergency stop → rotor speed 5 s 內降 50%、tower load 1.8× 衝擊出現
  - pitch rate ≤ 10 °/s（actuator 物理上限）
  - yaw rate ≤ 0.5 °/s
  - rotor overspeed margin：≤ rated × 1.2
  - generator slip：< 5%
  
  **Layer 4 — Cross-module Consistency（跨模組一致性）**
  - `tests/physics/test_consistency.py`
  - 風機個體 power spread 落 [10%, 25%]（與 -24 目標一致）
  - Region 3 power CV 落 [3%, 8%]
  - Region 2 power 對 wind 之 cubic fit R² > 0.95
  - Stator temp 與 power 之 lagged correlation：r > 0.5 但 lag > 60 s
  - 同一 grid event 下，不同 turbine 因 derate sensitivity 不同 → spread 在 [5%, 20%]
  - Atmospheric stability s × shear α 五重耦合：相關係數方向正確（#99/#109/#111/#113/#115）
  
  **Layer 5 — Fault Injection Signature（故障注入 sanity）**
  - `tests/physics/test_fault_signature.py`
  - 對 11 個 fault scenario 各跑短 sim，驗證 SCADA tag 該動的有動：
    - `bearing_wear` → HF band 升 ≥30%、crest factor ≥5
    - `gearbox_overheat` → oil_temp 升 ≥10°C、GMF sideband ratio 升
    - `pitch_imbalance` → 1P band 升、tower SS moment 升
    - `blade_icing` → 1P + 3P 都升、power 跌
    - `generator_overspeed` → HF band 升 + stator temp 升
    - `converter_cooling_fault` → power 跌 + cabin temp 升 + cooling level 降
    - `yaw_misalignment` → 3P band 升 + power 跌（cos³γ）
    - `stator_winding_degradation` → HF 升（電氣噪訊）
    - `hydraulic_leak` → broadband 升 + brake pressure 異常
    - `gearbox_oil_leak` → oil_level 降 + viscosity 異常
    - `grid_protection_trip`（如 -27 完成）→ relay status flip + emergency stop
  - 健康基線（無故障）：crest factor < 5, kurtosis < 4, RMS 落 ISO zone A/B
  
  **Layer 6 — Physics Health Check CLI（一鍵體檢報告）**
  - `tools/physics_health_check.py`：CLI 工具
    - 跑完 Layer 1-5 全 validator
    - 跑一次 30-min short sim 5 turbines（含 1 個 fault injection）
    - 產出 markdown 報告 + JSON + matplotlib 關鍵圖（Cp 曲面、wake deficit、ISO 10816 zones、fault signature）
    - exit code：失敗 → 1，全 pass → 0（適合 CI）
    - argparse `--save-report` (default on) / `--baseline-diff` / `--update-baseline`
  - 整進 [docs/routines/daily-workflow.md](docs/routines/daily-workflow.md)：每次改 physics 模組後 + 大版本發布前必跑
  - 寫入 README：`python tools/physics_health_check.py` 是「物理體檢」單一入口
  
  **Layer 7 — Test Report Persistence（測試紀錄保存機制）⭐ 劉老師 2026-05-05 要求**
  
  每次測試自動留下可追蹤的紀錄文件，避免「跑過就忘了」、無從查歷史軌跡。
  
  資料夾結構（**新增於 `tests/physics/reports/`**）：
  ```
  tests/physics/reports/
  ├── _baseline/                          ← 最新 baseline（人手動 review 後 commit）
  │   ├── pytest_baseline.md              ← 6 layer 全 pass 的 baseline 數值
  │   ├── pytest_baseline.json            ← machine-readable，diff 用
  │   └── health_baseline.md
  ├── 2026/05/                            ← 按月歸檔
  │   ├── 2026-05-05-1430-pytest.md       ← pytest 自動產
  │   ├── 2026-05-05-1430-pytest.json
  │   ├── 2026-05-06-0915-pytest.md
  │   └── 2026-05-06-1000-health/         ← health check CLI 產
  │       ├── report.md
  │       ├── report.json
  │       ├── baseline_diff.md
  │       └── figures/
  │           ├── cp_surface.png
  │           ├── wake_deficit.png
  │           ├── iso10816_zones.png
  │           └── fault_signatures.png
  └── README.md                           ← 怎麼讀報告 / 怎麼回滾 baseline / retention 規則
  ```
  
  每份紀錄頂端必含 YAML metadata：
  ```yaml
  ---
  timestamp: 2026-05-05T14:30:12+08:00
  git_commit: abc1234
  git_branch: claude/issue-20260505-23-2026-05-05
  git_dirty: false                        # working tree 是否有未 commit 變動
  python_version: 3.12.5
  test_type: pytest | health_check
  duration_sec: 42.3
  total_pass: 87
  total_fail: 0
  total_warn: 2
  baseline_compared: _baseline/pytest_baseline.json
  baseline_drift: see baseline_diff section below
  ---
  ```
  
  機制：
  - `tests/physics/conftest.py`：`pytest_sessionfinish` hook 自動產 `pytest-{ts}.md` + `.json`
  - `tools/physics_health_check.py`：CLI 預設寫入 `health-{ts}/` 子目錄
  - `tools/physics_baseline_update.py`：人手動 review 後 promote 為 baseline（**禁止自動 update**，避免 silent drift）
  - **Git 策略**：報告檔 commit 進 repo（這就是「紀錄」的意義）；`figures/*.png` 視大小決定（超過 1 MB 改 git-lfs 或 ignore）
  - **Retention**：保留近 6 個月每日；超過 6 個月只留每月最後一份；超過 1 年只留每年 release 對應的；baseline 永留
  - **README.md**：寫清楚「為什麼這個資料夾存在 / 怎麼比對兩份報告 / 怎麼決定該不該更新 baseline」
  
- **Acceptance**:
  - `pytest tests/physics/ -q` 100% PASS（7 層共 ~80-120 條 test）
  - 跑時間 < 60 s（不含 Layer 6 CLI 的 short sim）
  - `python tools/physics_health_check.py` 產出可讀的 markdown 體檢報告
  - **負向測試**：故意把 `power_curve.py` 一個常數改錯（例如把 Betz 限改成 0.7），framework 必須 catch 到並 fail
  - 既有 26 條物理修正（#61~#127）每條至少有 1 個 validator 對應
  - **Layer 7 驗收（測試紀錄保存）**：
    - 跑完 `pytest tests/physics/` → `tests/physics/reports/2026/MM/` 自動新增 `*-pytest.md` + `.json`
    - 跑完 `python tools/physics_health_check.py` → 自動新增 `health-{ts}/` 子目錄含 `report.md` + `report.json` + `figures/*.png`
    - 每份報告開頭都有 YAML metadata（timestamp / git_commit / git_branch / git_dirty / python_version / pass-fail counts）
    - `tests/physics/reports/_baseline/` 已 commit baseline，且 `baseline_diff` 段在新報告中能正確顯示「無漂移」或「漂移 X%」
    - `tests/physics/reports/README.md` 解釋資料夾用途 / 比對方法 / baseline update 流程
    - retention policy 至少寫成 docstring（實作可延到下次 cleanup）
  
- **Reference**:
  - 既有 `examples/data_quality_analysis.py`（21 check 已寫，可整合進 Layer 4/5）
  - `docs/physics_model_status.md`（每條 # issue 對應的 validation point 來源）
  - IEC 61400-1, IEC 61400-12-1/2, ISO 10816-3
  - Burton, Sharpe, Jenkins, Bossanyi (2011) *Wind Energy Handbook* 2nd ed.
  - Niayifar & Porté-Agel (2016) — wake deficit benchmark
  
- **Risk / Note**:
  - **不要過度收緊 acceptance** — 物理模型有隨機項（turbulence、AR(1)），驗證要用統計量（mean / std / 相關係數）+ 容差，不要硬 == 比對
  - 跑時間若爆掉 → Layer 5 fault sim 改成「先建 fixture 再跑 assertion」
  - 對應 -24 修正的目標（spread / CV）會在 Layer 4 體現，兩 issue 互相驗證

---

### WMOM-20260505-24 — Data quality 3 項 fail 修正（個體差異 spread + Region 3 CV）

- **Status**: open
- **Milestone**: M3 並行（demo 必修）
- **Priority**: high（P0 — demo 被客戶質疑會傷信任）
- **Estimate**: 0.5-1 工作天
- **Source**: `examples/data_quality_report.txt` 「待改善列表」3 項
- **Description**:
  最新 data quality run 仍有 3 項警告：
  1. **Wind 15-20 m/s region CV=0.9% 太低** — rated region 訊號過度平滑，pitch dead-band / lag 還是不夠
  2. **Wind 20-25 m/s region CV=0.8% 太低** — 同上
  3. **風機間平均功率差 36.8% (>30%)** — individuality 參數調太大，看起來像異常值不像真實 fleet
- **Deliverable**:
  - `simulator/physics/power_curve.py`：rated region 加更多 controller jitter（pitch micro-correction noise + power setpoint dither，幅度依 #61 Cp 模型回推合理範圍）
  - `simulator/turbine_individuality.py` 或對應位置：`per_turbine_power_offset` / `cp_offset` 從 ±15% 收斂到 ±10-12%（保留個體差但合理）
  - 重跑 `examples/data_quality_analysis.py` 短版 0.17h × 5 turbines，確認 3 項全 pass，且不破壞既有 18 項 pass
  - 同步更新 `data_quality_report.txt`（commit 進 repo）
- **Acceptance**:
  - 21/21 quality check pass（或至少 20/21，spread 落在 25-30% 區間）
  - 既有 #117/#119/#125/#127 物理鏈不被破壞
- **Reference**:
  - `modules/monitoring/examples/data_quality_report.txt`
  - `modules/monitoring/examples/_post_migration_quick_validate.py`
  - issue #61（Cp 模型升級 commit 應該已部分緩解，但 Region 3 仍偏平）

---

### WMOM-20260505-25 — Frontend：RUL 顯示 + 多 band alarm 視覺化（#57/#58 收尾）

- **Status**: open
- **Milestone**: M3 並行 / M5 demo 增值
- **Priority**: medium（P1 — M5 RAG demo 視覺化 PMF 關鍵）
- **Estimate**: 1.5-2 工作天
- **Source**: `docs/legacy/digiwt_TODO.md` Priority E + Priority F（issue #57 + #58 frontend 部分）
- **UI directive（WMOM-20260507-01 後）**：
  在 [TurbineDetail](frontend/components/TurbineDetail.tsx) 既有 8-tab 架構內加新 tab（建議 `health` 或擴充現有 `fatigue` tab）；多 band alarm 用 `<HealthBar>`（[Charts.tsx](frontend/components/ui/Charts.tsx)）；RUL 顯示用 `<Stat>` 大數字 + threshold 顏色（接 C.warn / C.amber / C.ok）。**不可** Tailwind / 硬 hex。
- **Description**:
  Backend 已完成：
  - #57：fatigue 4-level alarm + RUL（剩餘壽命）estimation + 自動寫進 history events
  - #58：vibration 5 band alarm（1P/3P/gear/HF/Bb）+ crest/kurtosis alarm + BPFO/BPFI + GMF sideband
  缺前端可視化 — M5 RAG demo 時客戶看不到「AI 預警」直觀畫面。
- **Deliverable**:
  - `frontend/components/turbine/RulPanel.tsx`：RUL 倒數（年/月/日）+ 4-level alarm badge（notice/warning/danger/shutdown）+ 觸發時間軸
  - `frontend/components/turbine/SpectralAlarmPanel.tsx`：5 band 動態 threshold curve（A/B/C/D zones）+ 即時 RMS 落在哪一區 + crest/kurtosis trend
  - `frontend/components/turbine/BearingDiagPanel.tsx`：BPFO/BPFI 即時頻率 + 軸承幾何來源說明 + GMF sideband ratio
  - 整合進既有 turbine detail page 為新 tab「Condition / RUL」
  - i18n（zh/en 雙語）
- **Acceptance**:
  - 3 個 panel 在 simulator 模式下能看到資料流動
  - 故障注入（bearing_wear / gearbox_overheat）時 alarm badge 會升級
  - M5 demo 時可直接 screenshot 進 pitch deck
- **Reference**:
  - 後端 API：`server/routers/turbines.py`（已 expose 對應 SCADA tag）
  - 既有 `frontend/components/turbine/LoadFatiguePanel.tsx`（pattern 參考）

---

### WMOM-20260505-26 — SCADA tag 深度擴充（protection / cooling loop / converter internal / service-state）

- **Status**: open
- **Milestone**: M3 後續 / M5 RAG 之前必須做
- **Priority**: medium（P1 — M5 RAG 警報多樣性的素材庫）
- **Estimate**: 3-5 工作天（可拆 4 個 sub-issue 分批）
- **Source**: `docs/physics_model_status.md` §3.5「Expanded SCADA Tag Set」
- **Description**:
  目前 104 SCADA tags 多在感測層（風速 / 溫度 / 振動 / 載荷）。M5 RAG demo 要對應 Z72 手冊的警報碼（數百條），但現況只有 ~20 種警報事件可觸發，警報 → 手冊 retrieval 的 demo 廣度不夠。
- **Deliverable**:
  - **Protection 層**：grid breaker status / under-voltage relay / over-current trip / earth fault relay / phase loss（5-8 tags）
  - **Cooling loop 深度**：3-way valve position / heat exchanger ΔT / coolant flow per branch / pump RPM / accumulator pressure（5-8 tags）
  - **Converter internal**：DC link voltage / IGBT junction temp / firing angle / harmonic distortion / common mode voltage（5-8 tags）
  - **Service / Maintenance state**：service mode flag / lockout-tagout state / manual override active / calibration mode / firmware version（4-6 tags）
  - 對應 OPC suffix 對齊 Bachmann Z72 命名規則
  - 寫進 `scada_registry.py` `_TAGS` + `turbine_physics.py::step()` 輸出
  - 物理耦合：能由現有 fault scenario（converter_cooling_fault / generator_overspeed / hydraulic_leak 等）自然觸發，不要手刻 mock
- **Acceptance**:
  - SCADA tag 從 104 擴到 ~125-130
  - 既有 18/21 quality check 不被破壞
  - 至少 5 條新 tag 能在 fault scenario 下看到變化
- **Reference**:
  - `docs/__Z72UserManual.pdf`（M5 餵 RAG，要先確認 tag 名稱對得上）
  - `docs/1040610-Z72_PLC_OPC_TAG_1040510.xlsx`

---

### WMOM-20260505-27 — 保護電驛協調模型（51 / 27 / 59 / 81）

- **Status**: open
- **Milestone**: M3 後續 / 也可 park 到 M5 後
- **Priority**: medium-low（P2 — academic paper 章節價值高，demo 直接價值中等）
- **Estimate**: 1-2 週
- **Source**: `docs/physics_model_status.md` §2.5「Still missing: protection coordination relay model」
- **Description**:
  既有 LVRT/HVRT envelope 是 ride-through curve 的 envelope 判定，沒有真實的保護電驛動作邏輯。發 paper 給 Applied Energy 的「grid integration」章節時，這層是 reviewer 通常會問的細節。
  四類保護電驛：
  - **51（過電流時間反延時）**：I × t curve，極反延時 / 一般反延時 / 中反延時
  - **27（低電壓）**：V < threshold + delay
  - **59（過電壓）**：V > threshold + delay
  - **81（頻率異常）**：df/dt + f range（U/F + O/F）
- **Deliverable**:
  - `simulator/physics/protection_relay.py`：4 個 relay class + coordination logic（main + backup + 動作時間 selectivity）
  - 與 `electrical_model.py` 串接：relay 動作 → trigger trip event → cascading 到 turbine state machine 的 emergency stop
  - 6-10 條新 SCADA tag（relay status / pickup current / trip count / last trip time）
  - 至少 3 個 demo grid event 能跑通（distant fault / nearby short circuit / frequency excursion）
  - 對應 fault scenario 至少 1 個（grid_protection_trip）
- **Acceptance**:
  - 4 relay 都有單元測試（依賴 -23 測試骨架）
  - 與 IEC 60255 / IEEE C37.112 inverse-time curve 標準對得上（不要求 bit-perfect）
  - 至少 2 種 selectivity 場景能驗證（main 先動 vs backup 接手）
- **Reference**:
  - IEC 60255 / IEEE C37.112（inverse-time overcurrent curve）
  - `simulator/physics/electrical_model.py` LVRT/HVRT 段是 baseline

---

### WMOM-20260505-28 — 單齒 pitting / spalling defect signature

- **Status**: open
- **Milestone**: park 到 M5 後（學術強化用）
- **Priority**: low（P2 — paper value 高，商業 demo value 低）
- **Estimate**: 1 工作週
- **Source**: `docs/physics_model_status.md` §2.2「Still missing: per-tooth pitting/spalling frequency model (individual tooth defect)」
- **Description**:
  目前 #76 已有 GMF + sideband + tooth wear scalar（aggregate），缺單顆齒缺陷的窄頻譜訊號。診斷論文裡軸承 BPFO/BPFI 已建（#58），齒輪單齒 defect 是配對的另一面。
- **Deliverable**:
  - `simulator/physics/drivetrain_model.py`：擴充 `tooth_defect` state（哪一階 / 哪一顆 / 缺陷嚴重度）
  - 對應頻譜 signature：GMF × shaft frequency 的 modulation pattern + envelope demodulation 可觀察的衝擊
  - 新 fault scenario：`gear_tooth_defect`（從 baseline 幾乎看不到，到 severe 時 GMF sideband 大幅升起 + crest factor 異常）
  - 1-2 條新 SCADA tag（`WDRV_TthDefSev` / `WDRV_TthDefHs`）
- **Acceptance**:
  - test_drivetrain.py 覆蓋（依 -23）
  - 與既有 11 fault scenario 相容（不破壞 fault_engine 邏輯）
  - 故障注入後 frontend SpectralAlarmPanel（依 -25）能看到 GMF 區段升起
- **Reference**:
  - Randall 2011 *Vibration-based Condition Monitoring* §6.4
  - 既有 #76 / #58 GMF sideband 為 baseline

---

## UX / Frontend revamp

### WMOM-20260507-01 — 前端 UI 改版（A · Calm Operator + 雙主題）

- **Status**: done（2026-05-07 完成）
- **Milestone**: M1 並行（前端基礎設施，不卡 M3 frontend issue -19/-20/-25）
- **Priority**: medium（劉老師對外 demo 與第一個客戶接觸需要更專業的視覺語言）
- **Estimate**: 1 工作天 → **實際 1 個 session**
- **Owner**: Claude (session 2026-05-07)
- **Source**: 劉老師提供 `WMOM 介面改版交接書.md` + `app/VA.jsx` design canvas（A · Calm Operator 風格 — 鼠尾草綠＋暖米白／雜誌式排版）
- **Description**:
  既有 frontend 是 dark cyan + Tailwind + Orbitron 風（從 digiWindTurbine 繼承），對運維廠商管理層而言過於「實驗室感」、與 v0.8.1 商業化定位不符。改版按交接書規範替換成：
  1. **220px 左 Sidebar**（5 主頁 nav + 工具區 secondary）取代頂部 header
  2. **雙主題系統**：日（鼠尾草綠 #3F6B53 + 暖米白 #F5F2EA）/ 夜（翡翠玻璃 #3DDC97 + 深森林 #0E1815）— 全元件走 theme palette，不寫死 hex
  3. **字型**：DM Serif Display（H1 38px）+ Manrope（內文）+ JetBrains Mono（數字 / SCADA tags）
  4. **5 大頁面重畫骨架**：FarmOverview / TurbineDetail / MaintenanceHub / CostPage / HistoryPage（按交接書 §4 規格）
  5. **保留全部 API / hooks 不動**：`useMockTurbineData` / `useRealtimeData` / `useMaintenanceData` / `useCostData` / `useI18n` / `useSettings` 全不動，OperatorControl 6 指令、AI fault diagnosis、Dispatch 流程、CSV 匯出、事件比較、4 個 cost endpoint 完全保留
- **Deliverable**:
  - `frontend/theme/` — `themes.ts`（兩套 palette）+ `ThemeProvider.tsx`（Context + localStorage + `data-theme` 同步）
  - `frontend/components/ui/` — `Card / Btn / PageHeader / StatusPill / Stat / Logo / NavIcon / Sidebar / BigChart / MiniSparkline / HealthBar / Field / Input / Select / ReadOnlyBox`（10 個共用元件 + index）
  - `frontend/App.tsx` — 重寫成 sidebar layout，包 ThemeProvider，保留所有 modal 與 view state
  - `frontend/components/{FarmOverview, TurbineDetail, MaintenanceHub, CostPage, HistoryPage}.tsx` — 5 大頁面照交接書規格重寫
  - `frontend/components/{FaultInjectionPanel, SettingsPage, DispatchModal, WorkOrderDetailModal, FarmSelector, TrendChartPanel, EventComparisonView}.tsx` — 沿用功能、套新樣式
  - `frontend/index.html` — 加 DM Serif / Manrope / JetBrains Mono CDN；移除 Tailwind CDN（已無使用）；CSS variable 預設值
  - 刪除 6 個孤兒：`DataCard / Gauge / StatusIndicator / MiniTrendChart / FarmTrendChart / icons.tsx`（被新 ui 元件取代）
- **驗收**：
  - ✅ `npx tsc --noEmit` 0 錯誤
  - ✅ Vite dev server 跑在 `http://127.0.0.1:5179/` 全 page module 200，5 大頁 + faults / settings 全可開
  - ✅ 劉老師於 5179 視覺 review 確認 OK（2026-05-07 截圖）
  - ✅ 響應式 grid 1280+ 4 欄 / 1024–1279 3 欄 / 1023– 2 欄 / 768– sidebar 收漢堡
  - ✅ 主題 ☀/☾ + EN/中切換寫 localStorage、reload 後狀態保留
  - ✅ 所有按鈕 `aria-label`、主題切換 `aria-pressed`
- **Decision**:
  - **Tailwind 全退**：原本規劃保留作 layout utility，但實作後發現所有 new code 都走 inline style + theme palette，Tailwind CDN 變成 dead weight，順手移除
  - **recharts 保留 in HistoryPage / CostPage / TrendChartPanel**：互動需求高（hover、zoom、reference line）走 recharts；overview / cost KPI 的趨勢圖改 SVG（跟 VA.jsx 一致）
  - **Faults / Settings 入 sidebar secondary group**：交接書 §6 only 列 5 主頁，但實際還是要保留入口；放在「工具」分組下方，與主題切換並列
- **Intentional placeholders（不是 bug，刻意保留）**：
  以下 7 個 PageHeader 按鈕**有 UI 但無 onClick**，作為設計稿視覺鷹架保留，等對應 API / 流程確定再逐步補上。劉老師 2026-05-07 確認「保留就好，之後一個一個補功能」。
  追蹤清單見 → `WMOM-20260507-02`。
  | 頁面 | 按鈕 | 設計稿來源 | 真實對應 |
  |---|---|---|---|
  | 維護中心 | `+ 新工單` | VA.jsx §4.3 | 風機細節 → AI 診斷 → 派遣技師（既有 dispatch flow） |
  | 風場總覽 | `匯出` / `+ 新報告` | VA.jsx §4.1 | `匯出` 可接 `/api/export/snapshot`；`+ 新報告` 暫無 API |
  | 風機細節 | `限載` / `停機` / `安排檢查` | VA.jsx §4.2 | 同頁右側「操作控制」卡片有完整 6 指令（重複入口） |
- **Reference**:
  - `docs/design/2026-05-07-ui-source/WMOM 介面改版交接書.md`（2026-05-12 歸檔保存）
  - `docs/design/2026-05-07-ui-source/app/VA.jsx`、`data.js`（design canvas）
  - `work-logs/2026-05/2026-05-07-ui-revamp-calm-operator.md`

---

### WMOM-20260507-02 — PageHeader placeholder 按鈕逐步補功能

- **Status**: open
- **Milestone**: 不卡 M2-M5 主線，可隨時挑著補
- **Priority**: low（UX polish；功能都可在 detail 頁完成）
- **Estimate**: 每個 0.5-2h，依 API 是否存在
- **Source**: WMOM-20260507-01 改版時依設計稿放上 UI 但無 handler
- **Description**:
  改版時依 VA.jsx 設計稿放了 7 個 PageHeader 裝飾按鈕，劉老師 2026-05-07 決定 placeholder 保留、之後逐項補功能。本 issue 作為清單追蹤；每個 sub-task 完成時直接打勾並 commit。
- **Sub-tasks**（按好做順序排）：
  - [ ] **a. 風場總覽 `匯出`** — 接既有 `GET /api/export/snapshot`（直接下載 JSON）。**估時 30 min**。**[salvage 待重做]** PR #58（branch `claude/upbeat-davinci-l1U9N`）已完整實作（`handleExportSnapshot`：fetch → Blob → anchor download `farm-snapshot-{date}.json`；按鈕走 `Btn` `loading` state；ariaLabel 修為「匯出風場快照」；`revokeObjectURL` 包 `setTimeout` 避 Firefox/Safari 取消下載；失敗 `console.error`）+ code review 過。PR 因帶 stale 追蹤檔（與 main 79-commit 落差）已關，**邏輯在最新 main 重做**——只動 `frontend/components/FarmOverview.tsx`，低風險。
  - [ ] **b. 風機細節 `停機`** — 對應 `OperatorControlCard` 的 stop 指令；點擊跳到右側卡片或直接呼叫 `POST /api/control/command { command: 'stop' }`。**估時 30 min**
  - [ ] **c. 風機細節 `限載`** — 開 inline modal 收 kW 值 → `POST /api/control/curtail`。**估時 1h**
  - [ ] **d. 風機細節 `安排檢查`** — 跳到 `/maintenance` + 預填 turbine 與 inspection scenario；依賴 WMOM-22 `inspection_schedule`。**估時 1h**（但要等 -22 done）
  - [ ] **e. 維護中心 `+ 新工單`** — 開 modal：選風機 + 描述 + 選技師 → `POST /api/maintenance/work-orders`（API 已存在）。**估時 2h**
  - [ ] **f. 風場總覽 `+ 新報告`** — 依賴 M4 reporting module；開 modal 選報告類型（月報 / 年度預算 / custom range）。**估時 2-3h**（要等 M4 backend）
- **Deliverable**:
  - 每完成一項，更新本 issue checkbox + commit 訊息帶 `feat(#WMOM-20260507-02): wire {sub-task name}`
  - 全勾完後本 issue close
- **Decision**:
  - 不要把這些按鈕通通砍掉重畫（會破壞跟設計稿的對齊）
  - 不要做「dummy alert / TODO 訊息」假裝有功能（劉老師 2026-05-07：「沒作用沒關係，開發階段」）

---

### WMOM-20260513-01 — UI 改版 v2（placeholder — 等劉老師補新設計交接書）

- **Status**: open (placeholder — **設計規範未提供前不開工**)
- **Milestone**: 未排（待 spec 後決定 M4 後半 / M5）
- **Priority**: TBD（依劉老師對外 demo 與客戶溝通的時程急迫度決定）
- **Estimate**: TBD（依改版幅度 — 微調 1d / 重畫 3-5d / 換主題系統 1 週）
- **Source**: 2026-05-12 劉老師提及「想修改 UI」；2026-05-07 WMOM-20260507-01 完成 Calm Operator 後，劉老師可能想做 v2 iteration

#### 背景

- 2026-05-07 已完成 WMOM-20260507-01「前端 UI 改版（A · Calm Operator + 雙主題）」
- 既有設計 source 已歸檔在 [`docs/design/2026-05-07-ui-source/`](docs/design/2026-05-07-ui-source/)（WMOM 介面改版交接書 / app/VA-VC.jsx / variants/V1-V3.jsx / shared/MiniDashboard / 各 HTML mockup）
- 劉老師 2026-05-12 表示有新 UI 想法

#### Description（待補）

下列為 placeholder，**劉老師需補完才能開工**：

- [ ] 新版設計交接書（類似 2026-05-07 那份 markdown）
- [ ] 主要要改哪幾頁？（FarmOverview / TurbineDetail / MaintenanceHub / CostPage / HistoryPage / Workflow / Reports 全動還是局部）
- [ ] 主題系統異動嗎？（保留鼠尾草綠+翡翠玻璃 / 換新色 / 加第三主題）
- [ ] 字型異動嗎？（保留 DM Serif + Manrope + JetBrains Mono / 換）
- [ ] 元件庫 (`frontend/components/ui/`) 要新增哪些？或重做哪些？
- [ ] 是否影響 backend schema 或 API contract？（默認否）

#### Acceptance（待補）

- [ ] `npx tsc --noEmit` 0 errors
- [ ] `npx vite build` 成功
- [ ] 全頁面在 light + dark 兩主題下 visually consistent
- [ ] 不破壞既有 functionality（hooks / API / modal flow 全保留）
- [ ] 留新版交接書到 `docs/design/{YYYY-MM-DD}-ui-source/`

#### Depends on
- 劉老師補 spec

#### Blocks
- 無（純美術 polish，不卡主線功能）

#### Notes for daily routine
- **此 issue 因缺 spec 暫時跳過** — daily autonomous worker 不要 pick 起來做
- 等劉老師補完 description 區塊後改 status，再進排程

---

### WMOM-20260513-02 — Demo Orchestrator full impl + simulator integration（A10 follow-up）

- **Status**: open
- **Milestone**: M5（2026-09）
- **Priority**: medium（demo polish；客戶 demo 時若想一鍵 replay lifecycle 需要這個）
- **Estimate**: 2-3 工作天
- **Source**: 2026-05-13 A10 (WMOM-20260509-10) 收尾留下的兩個延伸缺口

#### Description

A10 完成 Layer A pytest E2E（6 個 test 跑完整 lifecycle）+ Layer B 純靜態
`DemoOrchestratorPage.tsx` skeleton；此 follow-up 把兩個缺口補完：

**Part A — Demo Orchestrator UI 接 API（1-1.5d）**

- `frontend/components/demo/DemoOrchestratorPage.tsx` 從 skeleton 進化成可執行
- 「Run Full Demo」按鈕走 11 個 step：建單 → 派工 → 開始 → MR → 3 階 approve → receive → finish → 工單 2 階 approve → 月報
- 每 step 顯示 running / done / skipped + 可逐步暫停 / reset
- 確保 step list 與 `tests/e2e/test_fault_to_signoff_lifecycle.py::_walk_happy_lifecycle` 順序對齊（程式碼裡留 cross-reference comment）

**Part B — 真 simulator + canonical alarm code（1-1.5d）**

A10 為 mock 簡化用了字串 `"GBT_TEMP_HIGH"` 當 `source_alarm_code`，但 monitoring 層
（`modules/monitoring/simulator/physics/fault_engine.py`）的 alarm 結構是
`{type: "T1"|"T2"|"A", code: int}`。Follow-up：
- 抽 shared constant：`shared/alarm_codes.py` 定義 canonical Z72 alarm taxonomy
- E2E test 改用 canonical schema（e.g. `"T1:301"` for gearbox temp high）
- `tests/e2e/test_fault_to_signoff_lifecycle.py::_walk_happy_lifecycle` Step 1 改成
  真的呼叫 `simulator.inject_fault(scenario="gearbox_temp_high")` + assert SCADA tag delta
- 另加 INSPECTION over-use variant（`estimated_qty=1, actual_qty=2`），驗 receive
  endpoint 對「actual > estimated」的業務規則（cap at estimated vs allow over-use —
  需 product decision）

#### Acceptance
- [ ] DemoOrchestratorPage「Run Full Demo」按鈕端到端跑通 11 step → CLOSED + 月報
- [ ] Shared alarm code taxonomy 被 monitoring + workflow + E2E test 三方共用
- [ ] E2E test 改用真 simulator fault injection（不再用字串 mock）
- [ ] INSPECTION over-use variant 新增 1 個 test
- [ ] 全 backend + frontend 0 regression

#### Depends on
- WMOM-20260509-10（A10）已完成 ✓

#### Blocks
- 無（M5 demo polish）

---

### WMOM-20260526-01 — Frontend 測試基礎設施（vitest + RTL）導入 + 兩 hook 回歸測試

- **Status**: done（2026-05-26 完成 — autonomous daily worker）
- **Milestone**: M4 後續 / 工程基礎設施
- **Priority**: medium（不阻塞 demo，但是前 3 次 wrap-up 重複推薦的技術債）
- **Estimate**: 0.5 工作天 → **實際 ~0.5d**（frontend only）
- **Owner**: Claude（session 2026-05-26）
- **Branch**: `claude/upbeat-davinci-aDiqG`
- **Source**: 5/19 / 5/22 / 5/23 wrap-up 重複留的「建議另開 issue 導入 vitest+RTL」
- **Completion summary**:
  - ✅ 框架就位：`frontend/package.json` 加 `test` / `test:watch` script + devDeps
    （`vitest@^3` / `jsdom` / `@testing-library/react@^16` / `@testing-library/dom`，版本 pin 進
    `package-lock.json`）
  - ✅ `frontend/vitest.config.ts`（新）**刻意獨立於 vite.config.ts** → `vite build` 仍只讀
    vite.config.ts，production build 零變動；`globals: false` 讓 tsconfig 不需加
    `vitest/globals` types
  - ✅ `useCostData.test.ts`（5 tests）守 WMOM-20260504-13 AbortController 防 race：
    happy path / **race（舊 run 後到不蓋新結果）** / AbortError 不進 error / 一般 Error 進 error / reset 清空
  - ✅ `useRealtimeData.test.ts`（5 tests）守 WMOM-20260504-12 WS 殭屍重連洩漏：
    單一連線 / message 映射 / unmount 解除四 handler + close / **disposed guard（殭屍 onclose 不重連）** / 正常 3s 重連
  - ✅ Verify：`vitest run` 11 passed；`tsc --noEmit` 0 errors；`vite build` 748 modules / 0 errors
    （模組數與導入前一致 = 測試檔/設定未進 bundle）；backend frontend-only zero regression
  - ✅ Code review（code-reviewer subagent）0 must / 4 should / 4 nice：4 should 全採納
    （SF#1 拆出「reset 中止 in-flight」deferred 測試[原測試名稱聲稱守該路徑但 reset 時已無
    in-flight，abort 為 no-op]、SF#2 race 改 `await act(async)` 去 RTL warning、SF#3 補 race
    後 `loading===false` 斷言、SF#4 移除誤用 `waitFor`）+ 3 nice 採納（disposed StrictMode
    取捨註解 / fetch mock 去多餘 microtask / config setupFiles TODO）；#8 不採納（兩路徑各自有 test）
- **後續技術債（本 PR 觀察到）→ 已由 WMOM-20260527-01 解決（2026-05-27）**：
  1. ~~`requirements.txt` 未列 test deps~~ → 補 runtime 缺漏 + 新增 `requirements-dev.txt`
     （查證 openpyxl/aiosqlite 實際無 import，未列）
  2. ~~numpy 未 pin → cost pinned 測試 `!=` float drift~~ → 改 `math.isclose`/`pytest.approx`
     容差比對（pin numpy 不足以解決：實測跨平台 BLAS 在 numpy 1.x/2.x 下皆 drift）
- **Reference**:
  - [`frontend/vitest.config.ts`](frontend/vitest.config.ts)
  - [`frontend/hooks/__tests__/useCostData.test.ts`](frontend/hooks/__tests__/useCostData.test.ts)
  - [`frontend/hooks/__tests__/useRealtimeData.test.ts`](frontend/hooks/__tests__/useRealtimeData.test.ts)
  - [`work-logs/2026-05/2026-05-26-frontend-test-infra.md`](work-logs/2026-05/2026-05-26-frontend-test-infra.md)

---

### WMOM-20260528-01 — Frontend 元件層回歸測試擴充：workflow statusUtils + reporting formatters 純函式

- **Status**: done（2026-05-28 完成 — autonomous daily worker）
- **Milestone**: M4 後續 / 工程基礎設施（不阻塞 demo）
- **Priority**: medium（5/27-01 + 5/27-02 兩份 handoff + vitest.config.ts TODO 都列為候選的「擴大 frontend 元件層測試」）
- **Estimate**: 0.5 工作天 → **實際 ~0.4d**（frontend only）
- **Owner**: Claude（session 2026-05-28）
- **Branch**: `claude/upbeat-davinci-5K3LM`
- **Source**: WMOM-20260526-01（vitest+RTL 基礎設施）導入後的自然續作；handoff 反覆推薦
- **Completion summary**:
  - ✅ **切入點**：先測最高 ROI、零脆弱的**純函式層**（無 React / async / DOM → 確定性高、
    不脆弱），**不動 `vitest.config.ts`**（純函式不需 jsdom matcher / setupFiles → 基礎設施零變動）
  - ✅ `frontend/components/workflow/__tests__/statusUtils.test.ts`（**21 tests**）：
    - 10 個 label 函式 en/zh 雙語**窮舉**：用 service 匯出的 `*Values` runtime 陣列迭代 +
      `Record<Enum, [en, zh]>` 期望表 → **compile-time 窮舉**（新增 enum 漏補期望值 tsc 立刻紅）
    - 4 個 tone 函式窮舉（`Record<Enum, PillTone>`，確認 switch 無漏 case）
    - `fmtDateTime`/`fmtDate` 驗明確 Asia/Taipei（UTC+8）：`2026-01-15T18:30:00Z → 2026-01-16 02:30`
      （跨午夜進位證實套了時區、不隨 runner timezone 漂移；封存 WMOM-20260509-06 Must-fix #1）
      + null→「—」+ 無法解析→原樣回傳（附註解標明 source 現行 fallback）+ lang fallback 雙重 cast
  - ✅ `frontend/components/reporting/__tests__/formatters.test.ts`（**9 tests**）：
    `fmtMoneyDecimal` null/空/非有限→「—」契約、小額/千級/百萬級分級（含 1e3 / 1e6 上下界 +
    999_999.99 鄰界鎖門檻方向）、負值保留負號、parseFloat 寬鬆解析；`fmtPct` 百分比 + NaN 鎖現況
  - ✅ **Verify**：vitest 11→**39 passed**；`tsc --noEmit` 0 errors；`vite build` 918.27 kB
    （測試檔未進 production bundle、大小持平）；backend 未動 zero regression（baseline 570 passed / 1 xfailed）
  - ✅ **Code review**（code-reviewer subagent）2 must / 3 should / 2 nice → 全評估後採納：
    - MF#1 `fmtPct` NaN 無防禦 → 查 caller（MonthlyReportPanel KPI ratio 型別 `number`）確認
      null/undefined 被簽章擋住、非真 bug → **不動 source**（無真 bug + 無 product decision），
      補鎖現況 `NaN→'NaN%'` test + 註解使契約顯性
    - MF#2 `fmtDateTime` 原樣回傳 → 加註解說明為 source 現行 fallback（壞資料外顯）、鎖住防改動
    - SF#3 補負值 1e3 邊界 `-1000`；SF#4 lang fallback 雙重 cast 真正打退化分支；SF#5 補
      999_999.99 鄰界（k/M 分級方向）
    - SF#6 → reviewer 自降 nice（與既有 `useCostData.test.ts` describe 風格一致）；N#7 parseFloat
      副作用註解採納；N#8 environment pragma 不採納（與既有 hook 測試一致）
- **Reference**:
  - [`frontend/components/workflow/__tests__/statusUtils.test.ts`](frontend/components/workflow/__tests__/statusUtils.test.ts)
  - [`frontend/components/reporting/__tests__/formatters.test.ts`](frontend/components/reporting/__tests__/formatters.test.ts)
  - [`work-logs/2026-05/2026-05-28-frontend-statusutils-formatters-tests.md`](work-logs/2026-05/2026-05-28-frontend-statusutils-formatters-tests.md)
- **Depends on**: WMOM-20260526-01（done）
- **Blocks**: -

---

### WMOM-20260529-01 — Frontend mock login 身份核心回歸測試：mockUsers 純函式 + fixture 契約

- **Status**: done（2026-05-29 完成 — autonomous daily worker）
- **Milestone**: M4 後續 / 工程基礎設施（M6 demo-critical 身份層的測試守護）
- **Priority**: medium（mock login 是 M6 客戶 demo 跑完整 lifecycle 的關鍵，此前零測試）
- **Estimate**: 0.4 工作天 → **實際 ~0.4d**（frontend only）
- **Owner**: Claude（session 2026-05-29）
- **Branch**: `claude/kind-faraday-CWVM3`
- **Source**: WMOM-20260526-01（vitest+RTL 基礎設施）+ 5/28 純函式測試 pattern 的自然續作；挑 demo-critical 且零脆弱、零新依賴的目標
- **Completion summary**:
  - ✅ **切入點**：mock login 身份核心 `frontend/services/mockUsers.ts`（WMOM-20260510-01 Part B）。
    `getCurrentActorId()` 是**非 React 模組（service callback）唯一同步身份來源**，所有 dispatch /
    approve API call 的 actor_id 都從這裡來；M6 demo 三階簽核（employee→leader→treasury）全靠 4 個
    fixture user。此前零測試。只依賴 localStorage（vitest.config.ts `environment:'jsdom'` 已提供）→
    **零 DOM render、零新依賴、不動 `vitest.config.ts`**
  - ✅ `frontend/services/__tests__/mockUsers.test.ts`（**20 tests**，新建 `services/__tests__/` 目錄）：
    - **fixture 契約（8）**：4 user / id 唯一 / UUID 分段格式（placeholder） / 全 is_active（資料前提，
      非 UI） / email 唯一且 @wmom.dev / roles 用 `Record<string,ReadonlyArray<MockUserRole>>` 期望表
      窮舉（value=compile-time、key=runtime 兩層保護；sort 後比對鎖成員集合不鎖順序） /
      只有 Owner 標 dev_mode_only 且唯一含 owner role / 非 Owner 三人皆非 dev_mode_only
    - **DEFAULT_USER 與常數（2）**：DEFAULT_USER===MOCK_USERS[0]===Alice 且 roles 僅 `['employee']`
      （最低權限安全預設） / `ACTOR_ID_STORAGE_KEY==='wmom_actor_id'`（跨模組持久化契約）
    - **findMockUser（3）**：null/undefined/空字串→null / 每個合法 id→正確 user / 未知 id→null + 大小寫敏感
    - **getCurrentActorId（7）**：無值→Alice / 合法 id→原樣 / **Owner（dev_mode_only）id 仍回傳（不過濾）** /
      未知 id→fallback Alice（安全：拒絕非 fixture 身份進 API call） / 空字串→fallback / 回傳值恆為已知
      fixture id / **SSR（`typeof window==='undefined'`）→fallback（`vi.stubGlobal` 打到 source:95 guard）**
    - 型別層 sanity：`_typeGuard: MockUser` 編譯期鎖介面欄位結構
  - ✅ **Verify**：vitest 39→**59 passed**（+20）；`tsc --noEmit` 0 errors；`vite build` 918.27 kB
    （測試檔未進 production bundle、大小持平）；backend 未動 zero regression（baseline 570 passed / 1 xfailed）
  - ✅ **Code review**（code-reviewer subagent）1 must / 5 should / 3 nice → Needs revision → 全採納後 approve：
    - MF#1 SSR guard 不可達且零測試 → 加 `vi.stubGlobal('window',undefined)` test 真正打到分支
    - SF roles 順序過緊→改 sort 鎖集合；getCurrentActorId happy path 補 Owner 特例；is_active 命名改「資料前提」；
      expectedRoles 註解改正兩層保護描述；UUID_SHAPE→PLACEHOLDER_UUID_SHAPE 減混淆
    - nice：_typeGuard 限制註解、移除冗餘 afterEach（與 useCostData 風格對齊）
- **Reference**:
  - [`frontend/services/__tests__/mockUsers.test.ts`](frontend/services/__tests__/mockUsers.test.ts)
  - [`frontend/services/mockUsers.ts`](frontend/services/mockUsers.ts)（被測 source）
  - [`work-logs/2026-05/2026-05-29-mockusers-identity-tests.md`](work-logs/2026-05/2026-05-29-mockusers-identity-tests.md)
- **Depends on**: WMOM-20260526-01（done）/ WMOM-20260510-01 Part B（done — 被測 source）
- **Blocks**: -

---

### WMOM-20260529-02 — 專案文件大整理：清過時 digiWT 重複檔 + ISSUES changelog 抽 archive + M5/M6 epic + routine prompt

- **Status**: done（2026-05-29 完成 — 劉老師交辦）
- **Milestone**: 工程基礎設施 / 文件治理
- **Priority**: medium（文件債清理，提升新 session / 其他 AI 工具接手效率）
- **Estimate**: ~0.5 工作天
- **Owner**: Claude（session 2026-05-29，劉老師交辦）
- **Branch**: `claude/kind-faraday-CWVM3`
- **Source**: 劉老師 2026-05-29 交辦「重新整理專案文件」4 點需求
- **Completion summary**:
  - ✅ **清過時 digiWT 重複檔**（root 殘留未隨 windMindOM 更新者）：
    - `README.md` 重寫為 windMindOM（原標題還是 `# digiWindTurbine`、0 處提 WMOM）
    - `AGENTS.md` / `GEMINI.md` 改為指向 `CLAUDE.md` 的薄 pointer（原為 digiWT 描述、port 8000）
    - 刪 `project.md` / `idea.md`（digiWT 專案描述，被 PRODUCT_VISION 取代）
    - 刪 `docs/daily_report.md`（停 2026-05-01）/ `docs/session_handoff.md`（停 2026-05-07，被 work-logs 每日 wrapup 取代）
    - 刪 root `package-lock.json`（`{"name":"digiWindTurbine"}` 空殼 stray）/ `docs/product/pitch_deck_v0.4_todo_revise.pptx`（被 v0.8.1 取代且放錯層）
    - `TODO.md` 刷新為 M5 現況（原停在 2026-05-05「本月 M1」）
  - ✅ **移除外部專案 dump** `z72SCADA_New/`（13 tracked 檔，檔名帶 `(1)`/`(2)` 下載重複後綴，CLAUDE.md §12「不 fork 他 repo 程式」；M3 設計擷取已產出 `docs/design-notes/m3/`，raw dump 無用）+ 清 `.gitignore` 相關行
  - ✅ **`docs/design/2026-05-07-ui-source/`** 只留 `WMOM 介面改版交接書.md`（設計決策紀錄），刪 .jsx/.html/promo 原型（UI 已實作，WMOM-20260507-01 done）
  - ✅ **ISSUES.md 瘦身**：頂部累積 8 筆 session changelog → 抽最舊 7 筆到 `docs/legacy/issues_changelog_archive.md`、頂部只留最近 1-2 筆 + archive pointer
  - ✅ **新增「🎯 未來大目標（M5/M6 epics）」區塊**（維持 ISSUES.md 為 bot 友善 single source，大目標清晰拆解：M5-1~6 RAG + mobile、M6-1~6 PoC + 合約，標 🔵 autonomous / 🟡 需劉老師）
  - ✅ **routine prompt 更新**：新增 `docs/routines/autonomous-daily-worker-prompt.md`（修正 504→570 baseline、移除已 done 的 A6/A7/A10/WMOM-20260510-01、改讀最新 handoff 而非 5/10）+ 更新 `docs/routines/daily-workflow.md` 過時處
  - ✅ 清本機快取（`__pycache__`/`.pytest_cache`/`frontend/dist`，皆 gitignored、未進 repo）
  - ✅ **Verify**：backend 570 passed / 1 xfailed、frontend vitest 59 / tsc 0 / vite build OK（純文件 + 死碼移除，零 code regression）
- **Decision（劉老師 2026-05-29 回覆 Q1-Q4）**：Q1 移除 z72SCADA_New / Q2 只留交接書.md / Q3 維持 ISSUES.md + 加 epic 區塊 / Q4 changelog 抽 archive 留最近 1-2 筆
- **Reference**:
  - [`work-logs/2026-05/2026-05-29-docs-reorg.md`](work-logs/2026-05/2026-05-29-docs-reorg.md)
  - [`docs/legacy/issues_changelog_archive.md`](docs/legacy/issues_changelog_archive.md)
  - [`docs/routines/autonomous-daily-worker-prompt.md`](docs/routines/autonomous-daily-worker-prompt.md)

---

### WMOM-20260527-01 — CI/baseline 技術債清理：requirements-dev.txt + cost pinned 容差比對

- **Status**: done（2026-05-27 完成 — autonomous daily worker）
- **Milestone**: 工程基礎設施（不屬特定 milestone）
- **Priority**: high（known blocker — 擋住每個 daily session 的乾淨 baseline + 新 sandbox bootstrap）
- **Estimate**: 0.5 工作天 → **實際 ~0.5d**（測試 + 依賴宣告，未碰 production engine 邏輯）
- **Owner**: Claude（session 2026-05-27）
- **Branch**: `claude/upbeat-davinci-svpIQ`
- **Source**: WMOM-20260526-01 §後續技術債 1+2；STATUS.yaml next_milestone「requirements-dev.txt + numpy pin 小工」
- **Completion summary**:
  - ✅ **依賴宣告**：`requirements.txt` 補先前漏列、app 實際 import 的 runtime 依賴
    （`sqlalchemy>=2.0` / `pandas>=2.0` / `reportlab>=4.0` / `jinja2>=3.1`）；新增
    `requirements-dev.txt`（`-r requirements.txt` + `pytest>=8.0` / `pytest-asyncio>=0.23` /
    `httpx>=0.27`）。查證 `aiosqlite` / `openpyxl`（5/26 note 曾列）全 repo 無 import → 不列。
  - ✅ **root cause 確認**：cost 3 個 pinned 測試（var_fluct year_1 / monte_carlo percentiles /
    cost_api mc seed42）在本 sandbox 必紅，差異在 float64 最後一位。pin baseline 在 Windows
    量測、sandbox 為 Linux + OpenBLAS；**實測 numpy 1.26.4 與 2.4.6 在 Linux 下都與 Windows
    pin 差最後一位** → 是跨平台 BLAS 累加 ULP drift，非單純 numpy 版本（故「pin numpy」不足以解決）。
  - ✅ **修法**：新增 `modules/cost/tests/pin_tolerance.py`（`pin_approx` = `pytest.approx(rel=1e-9,
    abs=1e-6)` / `pin_equal` = `math.isclose(rel_tol=1e-9, abs_tol=1e-6)`，非數值退回 `==`）；
    5 個 cost 測試檔改容差比對（var_fluct / monte_carlo / k13_equivalence loop 用 `pin_equal`；
    cost_api / adapter direct-assert 用 `pin_approx`）。**刻意保留 exact `==`** 於整數
    （year/index/seed）、`failure_multiplier`（1.5/2.0/3.0）、engine round() 過的值
    （summary npv 2 位、lifetime_availability 6 位、整數值金額）—— 跨平台確定性。
    `rel_tol=1e-9` 仍守 **9 位有效數字** → 真 regression 攔截力不變，只吸收 ~1e-15 平台噪音。
  - ✅ **Verify**：cost 測試在 `numpy 1.26.4` 與 `numpy 2.4.6` 下**皆 84 passed / 1 xfailed**
    （證跨版本 robust）；完整 backend `pytest modules/{workflow,cost,reporting}/tests/`
    → **568 passed / 1 xfailed，3 個 numpy drift 消除**。唯一剩 fail
    `test_concurrent_dispatch_one_loses_when_stock_short` 是既有 SQLite WAL flaky concurrency
    （單跑通過已驗證，與本 PR 無關）→ 相較先前 baseline（本 sandbox 永遠 3 紅）**嚴格改善**。
  - ✅ Code review：code-reviewer subagent（採納情形見 work-log §4）
- **Reference**:
  - [`modules/cost/tests/pin_tolerance.py`](modules/cost/tests/pin_tolerance.py)
  - [`requirements-dev.txt`](requirements-dev.txt) / [`requirements.txt`](requirements.txt)
  - [`work-logs/2026-05/2026-05-27-ci-baseline-pin-tolerance.md`](work-logs/2026-05/2026-05-27-ci-baseline-pin-tolerance.md)

---

### WMOM-20260527-02 — 修復並發 dispatch flaky 測試：實作 BEGIN IMMEDIATE 寫入序列化

- **Status**: done（2026-05-27 完成 — autonomous daily worker，本日第二個 session）
- **Milestone**: 工程基礎設施 / M4 正確性（不屬特定 milestone）
- **Priority**: high（known blocker — baseline 唯一剩的 flaky 紅燈，污染每個 daily session preflight；同時是 single-farm 部署的庫存超扣正確性 bug）
- **Estimate**: 0.5 工作天 → **實際 ~0.4d**
- **Owner**: Claude（session 2026-05-27）
- **Branch**: `claude/upbeat-davinci-2imrR`
- **Source**: 開工 preflight — `test_concurrent_dispatch_one_loses_when_stock_short` 連跑 5 次 3 pass / 2 fail
- **Root cause**:
  - `dispatch_request()`（material_request_repository.py:355）對庫存做 read-modify-write：
    `SELECT stock` → Python 端算 → `UPDATE` 扣減 + 寫 cost_ledger → commit。
  - **`with_for_update()` 在 SQLite 是 no-op**；**pysqlite 預設 `BEGIN DEFERRED`**，寫鎖
    （RESERVED lock）延後到 transaction 內第一次寫才取得。
  - 兩個並發 dispatch 都先 SELECT 讀到同一份 `stock=5`、各扣 4 都通過 `≥0` 檢查、各自
    UPDATE commit → **lost update / 超扣**（兩個都成功，但庫存只夠一個）。
  - `inventory_repository.py:105` docstring + 本檔 A2 acceptance（line 1013）早已**聲稱**靠
    「BEGIN IMMEDIATE + WAL + busy_timeout 序列化」，但 `_get_engine` 從未真的接上 ——
    文件聲稱卻未實作的 invariant。
- **Completion summary**:
  - ✅ **修法**：`modules/workflow/repository/work_order_repository.py`（全 workflow repo:
    work_order / inventory / material_request / signoff 共用此單一 `_get_engine`）套 SQLAlchemy
    官方 pysqlite serializable recipe —— connect listener `_set_sqlite_pragmas` 加
    `dbapi_conn.isolation_level = None`（關掉 driver 自動 BEGIN，轉 autocommit，PRAGMA 仍生效）；
    新增 begin listener `_begin_immediate` 發 `BEGIN IMMEDIATE`（transaction 一開始 grab
    RESERVED 寫鎖）；`_get_engine` `sa_event.listen(eng, "begin", _begin_immediate)`。
    效果：第二個並發交易的 BEGIN 被 busy_timeout(5s) 擋到第一個 commit/rollback 後放行，
    屆時讀到已扣減的最新 stock → 正確 raise `InsufficientStock`。WAL 仍允許並發讀，只序列化寫入。
  - ✅ **regression test**：`test_dispatch_atomic_transaction.py` 新增
    `test_engine_serializes_writes_with_begin_immediate` —— 直接斷言 engine `isolation_level is None`
    + begin listener `_begin_immediate` 已註冊（不依賴 thread timing），防未來移掉 listener 又退回 flaky。
  - ✅ **Verify**：`test_concurrent_dispatch_one_loses_when_stock_short` 連跑 **20/20 pass**
    （改前約 60%）；dispatch 測試檔 15 passed（+1）；完整 backend
    `pytest modules/{workflow,cost,reporting}/tests/` → **569 passed / 1 xfailed 連跑 3 次確定性**；
    `tests/`（含 e2e + physics）→ **151 passed 零 regression**。baseline 自此完全綠且確定性。
  - ✅ Code review：code-reviewer subagent（採納情形見 work-log §4）
- **與 WMOM-20260509-F6 的關係**：F6 是 M6 若選 PostgreSQL backend 才補的「真實
  `SELECT FOR UPDATE` row-lock integration test」；本 issue 是 SQLite single-farm 路徑的
  正確性 + 測試確定性，兩者正交，本 PR 不碰 PG。
- **Reference**:
  - [`modules/workflow/repository/work_order_repository.py`](modules/workflow/repository/work_order_repository.py)
  - [`work-logs/2026-05/2026-05-27-dispatch-begin-immediate.md`](work-logs/2026-05/2026-05-27-dispatch-begin-immediate.md)

---

## 物理模型 parking lot（學術深度，等 M5 後再評估）

> 不開正式 issue，但記錄在這以避免反覆討論「為什麼還沒做」。
> 投入大、商業 demo 直接價值低；如果劉老師要投 paper 才考慮排期。

| Item | 為什麼 park | 投入估計 | 觸發條件 |
|------|------------|----------|----------|
| 完整 BEM aerodynamic loading distribution | Cp(λ,β) + tower shadow + wind shear + wind veer 已涵蓋 trend 級 demo；BEM 主要對應「葉片 root 細部載荷分布 paper」 | 2-3 週 | 投 Renewable Energy / Wind Energy 期刊章節需要時 |
| Curled-wake model（yaw skew 反向旋轉渦流對） | Bastankhah 2016 線性 deflection + DWM meander 已涵蓋 90% 場景；curled wake 補的是 yaw > 20° 時的細節 | 2 週 | 對齊 NREL FAST.Farm / Floris 比對驗證時 |
| Aeroelastic tower / blade FEM coupling | tower SDOF first-mode + blade 3P/1P modulation 已能看到關鍵特徵；FEM 是月級工程 | 1-2 個月 | 與材料力學 / 結構合作另開 paper 線時 |
| Cooling 系統 radiator fin 細部模型 | 整體換熱 + fouling 已能 demo cooling 故障；fin-level 細節是熱交換器論文用 | 1 週 | 投 Applied Thermal Engineering 時 |
| Sub-transient electrical X"d/X'd 行為 | LVRT/HVRT envelope + ride-through 已涵蓋 grid event；sub-transient 是 power system 細節 | 1 週 | 與 -27 保護電驛協調合併投 paper 時 |

---

## M5-M6 預留區

> ROADMAP 詳見 `docs/product/ROADMAP.md`。
> M4 已展開為 [WMOM-20260509-01..-10](#m4-主線2026-08-workflow-part-2-inventory--reporting)。

- M5 (2026-09)：RAG_Ultimate strategy 對接（Phase 3 ready 否則用 baseline placeholder）+ Demo Orchestrator UI 完整版（接 -10 placeholder）
- M6 (2026-10)：Friendly 廠商現場部署 + 第一份月報送業主沒被退件 + 簽 LOI/合約

---

### WMOM-20260518-01 — MR detail modal 料件表加 SKU+name 顯示（A6 follow-up）

- **Status**: done（2026-05-19 完成；branch `claude/nice-brown-kJDox`）
- **Milestone**: M4 後續 / M5 demo polish
- **Priority**: medium（demo 給現場工程師看更友善；不阻塞 M4 收官）
- **Estimate**: 0.5 工作天 → **實際 ~3 小時**（含 code-review must-fix 採納）
- **Source**: 2026-05-18 WMOM-20260509-06 code review Should-fix #4
- **Owner**: Claude（session 2026-05-19，autonomous daily worker）
- **Completion summary**:
  - ✅ Backend schema：`MaterialRequestItemResponse` 加 `sku/name/unit: Optional[str] = None`
  - ✅ Backend repo：`MaterialRequestRepository.resolve_item_metadata(item_ids)` batch SELECT FROM `inventory_items` WHERE id IN (...)，回 `dict[UUID, ItemMetadata]`；缺漏 item → key omit；空輸入 → `{}` 不打 SQL
  - ✅ Backend router：加 `_enrich_items` + `_build_mr_response` + `_build_mr_list_response` 三個 pure-function helper，用 pydantic v2 `model_copy(update=...)` 不可變 enrichment；9 個 endpoint call site 全切過去
  - ✅ Frontend types：`MaterialRequestItem` interface 加 `sku/name/unit?: string | null`
  - ✅ Frontend `MaterialRequestDetailModal` items table：4 欄改 6 欄 `SKU | Name | Stock kind | Est qty | Actual qty | Unit`，UUID fallback 保留 monospace title 顯示完整 ID
  - ✅ Frontend receive form：label 從 truncated UUID 改 `SKU · name (est. N unit)`
  - ✅ Frontend returns dropdown：item_id 選單從 UUID 切片改 `SKU · name · est. N unit`
  - ✅ Frontend wizard step 3 review：顯 `SKU · name × qty unit · stock_kind`
  - ✅ 新增 9 個 test（`test_mr_item_metadata.py`）：repo 3（resolve / empty / missing）+ router 3（create / get / list）+ transition smoke 2（dispatch+receive+close + cancel）+ data drift 1（item 刪除後 null fallback）
  - ✅ Backend `python -m pytest modules/{workflow,cost,reporting}/tests/ tests/e2e/` → 526 passed (+9 new) + 1 xfailed + 3 pre-existing numpy drift + 1 flaky concurrency — zero regression
  - ✅ Frontend `npx tsc --noEmit` exit=0；`npx vite build` 3.57s, 748 modules, 917.15 kB (gzip 264.94 kB)
  - ✅ Code-reviewer subagent 找 3 must-fix + 3 should-fix + 2 nice-to-have，**全採納**：
    - MF#1 改 `model_copy(update=...)` 而非 attribute mutation（pydantic frozen 安全）
    - MF#2 加 docstring 註明 enrichment 非 transactional（read-after-fetch 跨 session）
    - MF#3 補 dispatch/receive/close/cancel 4 transition smoke tests
    - SF#1 `Iterable[UUID]` docstring 註明「只消費一次」
    - SF#2 `sqlite3` import 移到頂層 + 註解 SQLite-only（PG 切換見 WMOM-20260509-F6）
    - SF#3 grid SKU 欄寬度 `1fr` → `1.2fr`
    - N#1 `_build_mr_list_response` 空 list 早 return
    - N#2 移除 wizard `InventoryItemSummary.name/unit` 多餘 null guard（types 已 required string）
- **Reference**:
  - [`work-logs/2026-05/2026-05-19-mr-item-sku-name.md`](work-logs/2026-05/2026-05-19-mr-item-sku-name.md)
- **Depends on**: WMOM-20260509-06（done）
- **Blocks**: -
- **Resolution**（2026-05-19 autonomous worker）：
  - Domain `MaterialRequestItem` dataclass 加 3 個 optional metadata 欄位（純 informational，不參與 state machine / dispatch）
  - ORM `MaterialRequestItemORM.inventory_item` viewonly + `lazy="joined"` 自動補 sku/name/unit
  - Repository `_to_domain` 經 relationship 填值，inventory_item None 時三欄保持 None（cross-DB defensive）
  - Schema + frontend TS type 3 欄全 optional 保證向後相容
  - 5 個新 backend test 涵蓋 get / list / transition / dispatch / cross-farm isolation；e2e 6 個全 pass；516 passed (= 511 baseline + 5) + 1 xfailed + 3 pre-existing numpy drift — zero regression
  - PR：claude/issue-WMOM-20260518-01-2026-05-19
  - Work-log：work-logs/2026-05/2026-05-19-mr-item-sku-name.md

---

### WMOM-20260510-01 — Identity / dev mode / mock login + farm `is_offshore` field

- **Status**: done（全 4 part 完成 2026-05-18）
- **Milestone**: M5（2026-09）
- **Priority**: high（demo-blocker — 沒有身份切換無法給客戶看完整 lifecycle）
- **Estimate**: 2-3 工作天
- **Source**: 劉老師 2026-05-10 操作 lifecycle UI 時提出的 3 個關連缺口
- **Progress**:
  - Part A — Backend dev mode：done（merged 2026-05-14, branch `claude/issue-WMOM-20260510-01A-2026-05-14`）
  - Part B — Frontend mock login：done（merged 2026-05-15, branch `claude/issue-WMOM-20260510-01B-2026-05-15`）
  - Part C — Farm `is_offshore` 後端欄位：done（2026-05-18, branch `claude/nice-brown-PTCla`）
  - Part D — Frontend auto-drive start_work weather_window：done（2026-05-18, 同 branch — Part C/D 合併 PR）

#### 背景

2026-05-10 dev session 中發現 3 個彼此相關的設計缺口：

1. **沒有 auth/login 系統** — 所有 actor / assignee / approver 都用 frontend hardcoded `DEV_ACTOR_ID = '00000000-...0001'`
2. **簽核流程需要多角色** — employee → leader → treasury 3 階，但目前同一 placeholder 無法扮多角（且 chain 設計上「同 actor 不能連簽 ≥ 1 階」會擋）
3. **離岸/陸上判斷 hardcoded 在 UI** — `start_work` 對話框讓 user 手動勾「需檢查氣象窗（離岸風場）」，反向 UX。Farm config 沒有 `is_offshore` 欄位

#### 目標

實作 **dev/owner mode + mock login** 讓劉老師（或任何 demo 操作者）可以一個人扮所有角色完整跑 lifecycle，並把 farm 屬性放回 farm config 自動驅動 UI。

#### Description

**Part A — Backend dev mode（0.5d）**
- 加環境變數 `WMOM_DEV_MODE=true` 進 backend
- 啟用時跳過：
  - signoff chain「同 actor 不能連簽 ≥ 1 階」guard
  - 任何「dispatcher 不可同時是 assignee」之類的職責分離 check
- 啟動時 log warning：`⚠ WMOM_DEV_MODE active — auth checks bypassed`
- Production 部署時必須 unset

**Part B — Mock login（1d）**
- 簡易 user table（無密碼）：`name / email / role(s) / is_active`
- 預載 4 fixture：`Alice (employee)` / `Bob (leader)` / `Carol (treasury)` / `Owner (all roles, dev mode only)`
- Frontend 加左下角 user switcher（取代 sidebar lang toggle 旁那個位置 OR 獨立 widget）
- 切換 user 後：`localStorage.actor_id` 換新值，所有後續 API call 帶新 actor_id
- **不做**：登入畫面 / 密碼驗證 / JWT — 那些留給 M5+ 真 auth (WMOM-20260510-02 placeholder)

**Part C — Farm `is_offshore` field（0.5d）**
- `FarmConfig` 加 `is_offshore: bool = False`
- `farms_router` POST/PATCH 接受此欄位
- Frontend：
  - 重新加回 `start_work` dialog 的 weather_window 邏輯 — **依 farm.is_offshore 自動決定**，不再讓 user 勾
  - Onshore：`require_weather_window=false` 直接送
  - Offshore：要求 user 先綁 weather_window_id（M3 設計但 frontend 沒接 — 此 issue 一併補上）

**Part D — Farm 設定頁加 is_offshore checkbox（0.5d）**
- `FarmManagementPage` 或 farm setting modal 加 toggle
- Migration：既有 3 個 farm 預設 false（劉老師 demo 用陸上）+ 「彰化離岸風場台電」手動切 true 驗證 offshore code path

#### Acceptance

- [ ] `WMOM_DEV_MODE=true python run.py`：劉老師一個 placeholder 跑完 corrective lifecycle（建單 → 派工 → 開始 → 領料 3 階簽核 → 完工 → 工單 2 階簽核 → 月報）成功
- [ ] Mock login user switcher 切換 user 後，dispatch / approve action 帶不同 actor_id
- [ ] Onshore farm 的 work order，`start_work` 不再顯示 weather_window 選項
- [ ] Offshore farm（彰化）`start_work` 提示「請先綁定 weather_window_id」並提供選擇 widget
- [ ] 全 backend tests + frontend build 0 regression

#### Depends on
- 無（純獨立功能）

#### Blocks
- M6 客戶 demo（沒有 mock login 給客戶看 demo 會看到「dev placeholder」很不專業）

#### Notes
- **不做** real JWT auth — 那是 WMOM-2026XX-XX（M6+ if customer 真要 PoC 上線）
- Mock login 的 4 fixture user 是 demo 用，production 模式應該被禁用
- Part C 也修「2026-05-10 hot fix 把 weather_window checkbox 拿掉」的暫時方案

---

## 廢棄 / 不做（避免反覆討論）

| Item | 為什麼不做 | 取代方案 |
|------|-----------|---------|
| windMindOM 整合容器（v0.5） | 過度工程；客戶要的是 working tool 不是 framework | Monolithic 5 modules（DEC-20260502-06） |
| Plugin SDK | 同上；M1-M6 內部就 5 個 module 不需要 plugin 抽象 | 直接寫進 `modules/` |
| 4 類 Turbine Adapter ABC | 第一個客戶只有 Z72；過早抽象 | M1 只做 Bachmann Z72；第二個 OEM 再考慮 |
| Workflow Hub 獨立 service | 一個 dev 維運不來 | 留在 monolith 內 `modules/workflow/` |

詳見 `docs/product/decision_log.md` DEC-20260502-06。
