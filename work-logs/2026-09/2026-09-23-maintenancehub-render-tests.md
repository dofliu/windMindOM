# 2026-09-23 — `MaintenanceHub` component render 測試（WMOM-20260923-01）

> Session 類型：實作（單一 issue，純前端測試覆蓋擴大）
> Session 長度：中
> 主導：Claude（autonomous worker）
> 結果：`/admin/maintenance` 頁面元件（439 行）先前零 component render 測試，比照
> `DispatchModal` 範式補上 49 測。code-reviewer subagent review：0 must-fix，3
> should-fix（皆為 reviewer 親自 mutation testing 抓到的具體覆蓋率缺口）全數採納並
> mutation-verified，另採納 4 nice-to-have，Approve。backend 未動 1103 passed 不變；
> frontend 978→1027 passed（+49 新測）、tsc 0、build OK。

---

## 1. Session 目標

依 §4 決策樹（v4.1 injected prompt）開工：

1. **baseline regression**：無。backend `1103 passed / 7 skipped / 1 xfailed`；frontend
   `978 passed` / tsc 0 / build OK，與 STATUS.yaml 記錄的基準完全吻合。
2. **CI 飛輪狀態**：`mcp__github__list_pull_requests`（open）→ 空。查最近 5 個 `ci.yml` run
   → 全數 `conclusion: success`，含上一 session（WMOM-20260922-04，PR #164）——`git fetch
   origin main` 確認該 commit 已在 `origin/main`（`git merge --ff-only` 顯示 already up to
   date）。累積 PR #162/#163/#164 連續 3 筆真實跑完 CI 並 auto-merge，符合 TODO.md 自己訂的
   「連續 2-3 個 session 綠燈視為問題已解」門檻，已清除 TODO.md 頂部舊 CI 失效警語（見 §4）。
3. **docker daemon**：仍不可用（`docker info` 連得到 client、`/var/run/docker.sock` 不存在）
   ——`WMOM-20260716-06`（footprint）、`WMOM-20260509-F6`（PostgreSQL row-lock）本次仍無法接。
4. **M6 critical path**：live/OPC 後端硬化（WMOM-20260720-04/-08）已於先前 session 收尾，
   HTTPS 部署配置需先定部署目標/憑證策略（🟡 非 autonomous 可決），本次不接。
5. **情境比較分析 epic 剩餘**（A2 Part 2 相對時間對齊時序疊圖 / PR C 檢視情境掛載 app）：兩者
   皆明確標註「需先寫設計」（新後端端點的 downsampling 策略 / broker 子設計），不符合「單
   session 可完工、無設計歧義」的決策樹門檻，本次不接，留給專門的設計 session。
6. **測試覆蓋擴大**（決策樹 §5 工程基礎設施）：讀 `ISSUES.md` 過去多筆 2026-06 session 的
   「下次續做」，發現 `MaintenanceHub`（439 行）與 `FaultInjectionPanel`（555 行）從 2026-06-07
   起就被反覆點名為 untested 大元件，但沒有任何後續 session 接手（同一句話被複製貼上了 6 次都
   沒人做）。TODO.md 也有一條同款過時項目（`前端 component render 測試（CostPage / FarmOverview
   / workflow Panel）—— 需先補 vitest.config.ts jsdom setupFiles`）——**先確認發現這條 TODO 早已
   過時**：`CostPage.test.tsx`、`FarmOverview.test.tsx`、`workflow/__tests__/*Panel.test.tsx`
   全部已存在，`vitest.config.ts` 也早已配好 `jsdom` + `@testing-library/jest-dom` setupFiles。
   真正還缺的是 `MaintenanceHub`（本次認領）與 `FaultInjectionPanel`；ui primitives
   （`components/ui/*.tsx`）也是零測試但屬另一類別，未評估。
   認領 `MaintenanceHub`（較小、設計無歧義、無外部依賴，比 `FaultInjectionPanel` 更適合單一
   session），編號 `WMOM-20260923-01`。

---

## 2. 實際完成

### 2.1 設計

讀 `MaintenanceHub.tsx` 確認元件形狀：純由 `maintenanceData`
（`ReturnType<typeof useMaintenanceData>`）與 `onSelectWorkOrder`/`lang` props 驅動，元件
本身**不 fetch、無 timer**——data hook 的 fetch/輪詢邏輯已在 `useMaintenanceData` 自己的
單元測試裡覆蓋，不需要在這裡重複 mock。這使它成為本系列裡最單純的一支，比照 `DispatchModal`
範式：不 mock hook 本體，直接餵結構完整的假資料物件（`makeWorkOrder`/`makeTechnician`/
`makeMaintenanceData` 工廠）。

三個子元件（`WorkOrderTable`/`RosterCard`/`WeekCalendar`）都是純展示、依 props 計算：
- `priorityFromAge`/`slaFromAge`：用 `Date.now() - createdAt` 動態算。fixture 一律用「現在
  時刻往回推固定分鐘/小時數」構造（不用 fake timers，本系列 `MonthlyReportPanel` 已驗證 fake
  timers 會卡死非同步 render 的 `waitFor` polling；本檔雖無非同步，仍統一用真實時間降低耦合，
  且各門檻值都留有數十秒到數小時的安全邊際，不受一般 CI 執行延遲影響）。
- `WeekCalendar`：依「今天」算本週 Monday..Sunday，逐日計算 `workOrders` 落在該日的筆數。

### 2.2 新增

- `components/__tests__/MaintenanceHub.test.tsx`（新檔）：初版 46 tests，涵蓋：
  - **PageHeader 殼層**：標題 zh/en、sub 文字（未結工單數 `status≠COMPLETED` + 在崗技師數
    `ON_DUTY|DISPATCHED`，皆計「全部」而非篩選後結果）、Filter select 預設值、新工單按鈕。
  - **Filter 篩選**：all/open/in_progress/completed 四態，並驗證篩選不影響 sub 計數。
  - **WorkOrderTable**：7 欄表頭、空狀態 zh/en、ID 末 6 碼、問題首行截斷 60 字、
    faultDescription 空字串 fallback、technicianId 查表（含存在但查無此人的邊界）、
    createdAt 動態算優先權 HIGH/MED/LOW、SLA 字串（分/時/天三態）、狀態 pill zh/en、
    點列呼 `onSelectWorkOrder`。
  - **RosterCard**：標題、空狀態 zh/en、技師卡內容、切換班別鈕文字+disabled（DISPATCHED 不可
    點）zh/en、callback 接線、DISPATCHED disabled 鈕不觸發 callback。
  - **WeekCalendar**：標題 zh/en、星期標籤、計數徽章（今天 1 筆/2 筆/無工單）。

### 2.3 code-reviewer subagent review（Phase 6）

回報 0 must-fix，**3 should-fix（皆明確標註「confirmed via mutation testing」——reviewer 自己
改壞生產碼重跑驗證過，不是空談）**：

1. **「多名技師→最後一位無底部分隔線」測試名不副實**：測試名稱宣稱驗證分隔線邏輯，body 卻只
   斷言兩位技師的姓名文字都存在，完全沒檢查 `borderBottom` 樣式。reviewer 把生產碼
   `borderBottom: i < technicians.length - 1 ? ... : undefined` 改成永遠加線後重跑，46 測
   全數通過——確切的 false positive。
   **修法**：`screen.getByText('乙技師').parentElement!.parentElement` 取得整列 row（name
   div → flex:1 容器 → row），改斷言 `row.style.borderBottom`。
2. **`WeekCalendar` 星期分桶邏輯完全沒被鎖住**：三個計數徽章測試都用 `screen.getByText('×N')`
   全域查找，沒有 scope 到「今天」對應的格子，也沒有測試「非今天的某一天」是否正確計數。
   reviewer 把 `counts` 陣列整體位移一天（模擬 off-by-one 分桶 bug，今天的工單被畫到明天格）
   後重跑，46 測仍全數通過——這是最明顯的核心行為覆蓋缺口（不是 hover 這類 presentational
   細節）。
   **修法**：production 加一行 `data-testid="week-day-{i}"`（i=0 週一…6 週日，純測試選取用，
   無視覺/邏輯影響）；測試鏡射元件內部「本週 Monday..Sunday」的日期推算邏輯
   （`mondayOfCurrentWeek`/`weekDayTimestamp`/`todayWeekIndex` helper），建構一筆 createdAt
   落在「本週內但非今天」的工單，用 `within(getByTestId(...))` 精確斷言徽章只出現在正確的
   星期格、今天格子維持 0。同時把既有兩則「今天 1 筆/2 筆」測試也改用 `within(todayCell)`
   scope（原本用全域 `getByText`，雖然當時能過但精確度不足）。
3. **技師目前非 ON_DUTY 時，工單表格技師欄查表 fallback 未覆蓋**：唯一「technicianId 對應到
   現有技師」測試的技師 `status` 都是預設值 `ON_DUTY`，沒測過技師目前 `OFF_DUTY`/
   `DISPATCHED` 時 `techMap`（純依 id 建索引，理論上不該管技師當下狀態）是否仍正確顯示姓名。
   reviewer 把 `techMap` 建構時加上 `status===ON_DUTY` 過濾（模擬「已離班技師的歷史指派紀錄
   被誤判為查無此人」的邏輯錯誤）後重跑，46 測仍全數通過。
   **修法**：新增技師為 `OFF_DUTY` 的對照測試。

3 個 should-fix 逐一改回舊邏輯（連同 reviewer 描述的 3 種 mutation）**mutation-verified**：
確認新測會 fail，再還原（`git diff`/`diff` 對照確認生產碼與還原前位元組相同）。

另採納 4 個 nice-to-have：
- Avatar 空姓名 → fallback `?` 補測試。
- Filter 描述區塊的 `WORK_ORDERS` module-level 共用陣列改成 `buildWorkOrders()` 工廠函式
  （與本檔其他 describe 區塊的慣例一致，避免未來若元件邏輯改動導致跨測試互相污染卻不易察覺）。
- `lang=en` 星期標籤原本只驗證 M/W/F 至少出現一次（規避 T/S 重複字母），改用
  `toHaveLength(1|2)` 精確計數全部 5 個字母。
- Filter 切換測試補上 `expect(select).toHaveValue(...)` 斷言，與殼層測試的既有寫法對稱。

最終 **49 tests**（46 + should-fix #2/#3 各一則新測 + nice-to-have Avatar 一則新測；
should-fix #1 與其餘 nice-to-have 是修改既有斷言，不增加 `it` 數）。

### 2.4 卡住或延後的事

無阻擋項。`FaultInjectionPanel.tsx`（555 行）是同批 untested 大元件的最後一支，留給下個
session（比 `MaintenanceHub` 大、需先讀懂它的故障注入互動流程，適合另開一個 session 專心做）。

### 2.5 重大決策

無。純執行既有測試覆蓋擴大方向，非架構級決策。

---

## 3. 產出清單

### 修改檔案

- `frontend/components/MaintenanceHub.tsx` — 加一行 `data-testid="week-day-{i}"`（`WeekCalendar`
  日期格，純測試選取用，無其他變更）
- `frontend/components/__tests__/MaintenanceHub.test.tsx` — 新檔，49 tests

### 動了狀態的 issue

- WMOM-20260923-01：新開直接收（open → done）

### 追蹤檔案更新

- `ISSUES.md`：統計表 done 107→108、total 118→119；新增 WMOM-20260923-01 詳細條目
- `STATUS.yaml`：`last_updated`/`next_milestone` 記錄本次；`issue_stats.done` 107→108
- `TODO.md`：清除頂部已過時的 CI 失效舊警語（累積 PR #162/#163/#164 連續 3 筆綠燈，符合先前
  訂下的清除門檻）；baseline 數字更新（frontend 978→1027）；「前端 component render 測試」項目
  更正為只剩 `FaultInjectionPanel` + ui primitives 未評估（`CostPage`/`FarmOverview`/workflow
  Panel/jsdom setupFiles 皆已確認完成，這條 TODO 從 2026-07 就沒更新過）

### 寫進 decision_log 的決策

- 無

---

## 4. CI runner 基礎設施狀態

透過 GitHub MCP 確認：`git fetch origin main` 後 `origin/main` HEAD 已包含上一 session（PR
#164，WMOM-20260922-04）的 commit，`git merge --ff-only` 顯示 already up to date（自動
`auto-merge.yml` 成功執行，無需人工介入）。加計本次 session 開工前確認的最近 5 個 `ci.yml`
run 全數 `conclusion: success`，累積 PR #162（session #5）/ #163（session #6）/ #164（session
#7）連續 3 筆真實跑完 CI 並自動合併，符合 TODO.md 自己訂下的「連續 2-3 個 session 都綠燈視為
問題已解」門檻——已將 TODO.md 頂部的舊 CI 失效警語（`<details>` 摺疊區塊）整段清除，改為一段
簡短的「已確認恢復」記錄 + 若復發的因應方式提醒。

---

## 5. 下次怎麼接手

1. **`FaultInjectionPanel.tsx`（555 行）component render 測試**：同批 untested 大元件的最後
   一支，本次因範圍考量（挑較小、較單純的先做）留給下個 session。開工前先讀懂其故障注入互動
   流程（可能比 `MaintenanceHub` 複雜，需先確認是否有 fetch/timer 等外部依賴）。
2. **ui primitives**（`components/ui/*.tsx`）：目前零 `__tests__` 目錄，是否需要獨立測試
   （目前透過所有頁面/元件測試間接覆蓋）尚未評估，非急迫。
3. **情境比較分析 A2 Part 2 剩餘**（相對時間對齊時序疊圖 + 差異圖）：需要新後端端點（downsampling
   策略設計，見 `docs/product/decision_log.md` DEC-20260720-02 caveat）+ 新前端元件，不適合
   單一 autonomous session 直接實作，建議專門排一個「設計優先」的 session。
4. **PR C**（檢視情境掛載 app）：需先寫 broker 子設計，仍卡。
5. **持續卡住（環境限制）**：`WMOM-20260716-06`（footprint CPU-torch pin）、`WMOM-20260509-F6`
   （PostgreSQL row-lock）——本 sandbox 仍只有 docker client、無 daemon（`docker info` 確認
   `/var/run/docker.sock` 不存在）。

---

## 6. 誠實回報：測試覆蓋的已知限制

- **CSS 視覺樣式**（hover 效果、色彩對比、圖示外觀）本檔案完全未覆蓋——jsdom 不渲染實際樣式
  計算，這類驗證只能靠瀏覽器人工檢查，本 session 未做（無法啟動瀏覽器截圖比對）。
- **WeekCalendar 的「今天」判斷**用真實 `new Date()`（非注入時鐘），若測試剛好卡在跨日午夜
  瞬間有極低機率的 flaky（reviewer review 意見中也提到這點，屬於元件本身設計，不是測試檔案
  能在不動生產碼架構的前提下修掉的問題，留作資訊性註記）。
- **`toggleTechnicianStatus`/`onSelectWorkOrder` 之後的實際 API 呼叫行為**由 `useMaintenanceData`
  自己的單元測試覆蓋（本檔案只驗證 `MaintenanceHub` 正確呼叫這些 callback，不重複驗證 hook
  內部邏輯）。

---

## 7. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| Preflight（baseline 驗證、stack-aware 檢查、選題、確認 TODO 過時項目） | 20% |
| 讀 `MaintenanceHub.tsx` + 既有範式 + 設計測試 | 15% |
| 寫初版 46 tests + 除錯（4 個因 DOM 多重命中失敗的測試） | 25% |
| code-reviewer review + 3 should-fix + 4 nice-to-have 修復 + mutation-verified | 25% |
| 全套 baseline 驗證 + 追蹤檔案更新 + work-log 收尾 | 15% |

---

## 8. 學到的事

- **舊 TODO 項目要先驗證是否還成立，不要照抄**：TODO.md 那條「前端 component render 測試
  （CostPage / FarmOverview / workflow Panel）—— 需先補 jsdom setupFiles」從 2026-07 起就沒
  更新過，實際上這些工作早在更早的 session 就完成了。若沒有先用 `find`/`grep` 確認現狀，會
  浪費一整個 session 去重做已經做完的事，或誤判「setupFiles 未配置」而重複造輪子。
- **code-reviewer 的「confirmed via mutation testing」比單純「我覺得這裡少測」更有說服力，
  也更值得照單全收**：本次 3 個 should-fix reviewer 都附上了「我改壞了生產碼、重跑、46 測全過」
  的具體證據，這代表它們是真實的假陽性測試（測試名稱宣稱保護某行為，但實際上沒有），而不是
  reviewer 主觀認為「可以測更多」的錦上添花建議。這類有 mutation 證據的 finding 應該視同
  must-fix 等級處理（即使 reviewer 標的是 should-fix），因為不修的話這些測試會給後續開發者
  錯誤的安全感。
- **測試名稱做出的承諾要對得上斷言內容**：「最後一位無底部分隔線」這個測試名稱本身沒有錯，
  錯在斷言沒有真的去檢查這件事。寫測試時若测试名稱提到了某個具體的視覺/邏輯行為，斷言就該
  直接針對那個行為（style 屬性、DOM 結構），而不是退而求其次驗證「內容有渲染出來」這種恆真
  命題。
- **時間相依的分桶邏輯（依星期/日期把資料分配到不同格子）容易只驗證「有沒有出現」而漏驗「出現
  在哪裡」**：這類 bug（off-by-one、時區偏移、週起始日算錯）在只用全域 `getByText` 查找的
  測試下完全不會被抓到，因為文字內容本身沒變、只是渲染的容器錯了。之後寫這類「依時間/類別分桶
  展示資料」的測試，都應該優先考慮幫每個桶加穩定的選取用屬性（如 `data-testid`），再用
  `within()` scope 斷言。
