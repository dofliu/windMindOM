# 2026-06-04 — SettingsPage component render 測試（EPIC-M5 測試覆蓋擴大）

> autonomous worker session（每 3 小時 cron）。接續同日 WorkflowPage handoff 建議：
> 「同範式續推 SettingsPage（781）/ HistoryPage（809）/ TurbineDetail（1056）/ workflow 子面板測試」。
> 挑 **SettingsPage**（候選中最小、純 props + fetch 驅動、零子元件複雜度）為本次目標。
> issue：**WMOM-20260604-06**（SettingsPage component render 測試）

---

## 1. 為什麼做這個

開工 preflight（決策樹）：

- 優先級 #1 known blocker / #2 baseline regression / #3 飛輪壞掉 → **皆無**。
  - backend `pytest` → **638 passed / 1 xfailed**（綠）
  - frontend `vitest` → **162 passed**（綠；上個 session WorkflowPage 21 tests 已 auto-merge 進 main，PR #78）
  - 飛輪健康：FieldPage→ReportsPage→CostPage→FarmOverview→WorkflowPage 連續五個 render 測試 PR（#74~#78）皆 auto-merge 進 main。
- stack-aware：`list_pull_requests` open=22，全為飛輪上線前的 stale PR（無 `[WIP]`、非本 session 系列）。本次工作（net-new 測試檔）與它們**零 collision**。

→ 落到優先級 #4「乾淨 autonomous 工作」。WorkflowPage handoff 背書「同範式續推 SettingsPage」。
選 **SettingsPage**（`components/SettingsPage.tsx`，781 行）：

- **零設計歧義、單 session 可完工**：純 props（`settings` / `onSave` / `lang`）+ `fetch` 驅動的 config 表單，
  無 stateful hook 依賴、無重子元件（只用 ui primitive Btn/Card/Field/Input/Select/PageHeader/StatusPill，可真渲染），
  只需 stub `global.fetch`。範式（CostPage / FarmOverview）已成熟。
- **覆蓋價值**：`/admin/settings` 是 demo「切資料源 / 改風況電網覆寫 / 套機型規格」的操作面板，
  先前頁面層零覆蓋。守住「dataSource 驅動條件區塊」「Save → onSave 接線」「wind/grid/spec POST 接線」核心契約。

## 2. 認領

**WMOM-20260604-06** — SettingsPage component render 測試（EPIC-M5 測試覆蓋擴大）。

## 3. 本次完成（Implement）

純測試，**不動任何 production 程式**：

| 檔案 | 內容 |
|---|---|
| `frontend/components/__tests__/SettingsPage.test.tsx`（新） | SettingsPage render 測試。stub `global.fetch` 路由 4 個 GET config endpoint（wind / grid / turbine-spec / presets）+ 3 個 POST；`makeSettings(dataSource)` 工廠結構式滿足 `AppSettings`（不用 `as` 強轉）。元件用 `ThemeProvider` 包裹、`await act(async)` flush mount 的 4 條 fetch effect。 |

### 覆蓋的 UX 契約
- **基本渲染 + 語系**：zh 標題「系統設定」+ Save 按鈕「儲存設定」/ en 「Settings」+「Save settings」；API 端點區塊恆在。
- **dataSource 驅動條件區塊**：MOCK → 無模擬/OPC/Modbus 區塊；SIMULATION → 模擬參數 + 風機規格 + 風況控制 + 電網控制；OPC_DA → OPC DA 區塊（含 ProgID）；MODBUS_TCP → Modbus 區塊（IP/埠號/Slave ID）。
- **dataSource 切換接線**：Select 改值（MOCK→SIMULATION）→ 模擬區塊即時出現（守 onChange→formData→條件渲染）。
- **settings prop 同步**：rerender 換 settings（dataSource 不同）→ 區塊隨之更新（守 useEffect [settings] → setFormData）。
- **Save 接線**：點「儲存設定」（type=submit）→ `onSave` 被呼叫帶 formData + 「已儲存」pill 出現。
- **backend down**：wind GET reject → apiConnected false → 「無法連線到後端 API」warn card。
- **wind status 顯示**：mount wind GET resolve → 「模式」+ mode 值顯示。
- **wind profile 按鈕**：點「平靜 (2 m/s)」→ POST /api/config/wind body `{profile:'calm'}` + aria-pressed 翻轉。
- **custom wind 套用**：點「套用自訂風況」→ POST /api/config/wind 帶解析後數值 body（windSpeed/windDirection/ambientTemp/turbulence）。
- **grid profile 按鈕**：點「標稱」→ POST /api/config/grid body `{profile:'nominal'}`。
- **turbine spec presets**：presets GET resolve → 預設機型按鈕（名稱 + kW）渲染。
- **apply spec**：點「套用風機規格」→ POST /api/config/turbine-spec 帶 editSpec payload（含 rated_power_kw）。

### 技術要點
- **fetch stub 不靜默**：未預期 URL/method `reject(Error('Unexpected fetch'))`，新增 API 呼叫不會被靜默吞掉。
- **GET 路由 presets 先於 turbine-spec**：`/api/config/turbine-spec/presets` 是 `/api/config/turbine-spec` 的超字串，先判 presets 避免誤命中。
- **POST 斷言用 method 過濾**：`postBody(urlPart)` 從 `fetchMock.mock.calls` 過濾 method==='POST' 取 body，避開 mount 的多次 GET。
- **async handler 包 act**：profile/custom/apply 按鈕 handler 是 `await fetch`，點擊以 `await act(async)` flush，零 act() 警告。

## 4. Verify（本機全綠才開 PR）

- `npx tsc --noEmit` → **0 error**（無 `any`，settings fixture 與 AppSettings 嚴格對齊）。
- `npx vitest run` → **179 passed**（162 baseline + 17 新，**零 regression**）。
- `npx vite build` → ✓ built（僅既有 chunk-size 提示）。
- backend 未動 → **638 passed / 1 xfailed** 不受影響。

## 5. Code review

用 `code-reviewer` subagent 對 staged diff 跑審查（聚焦假綠 / mock 漂移 / flaky / cleanup）：
**2 must-fix / 3 should-fix / 3 nice-to-have，verdict Needs revision**。**全數採納**（16 tests → 17 tests）：

1. **[must-1 flaky]** handler 內 standalone `setTimeout`（清訊息 / saveStatus 回 idle）未受控，測試結束後仍對已 unmount 元件 setState（CI 平行 runner flaky）→ `beforeEach` 加 `vi.useFakeTimers()`、`afterEach` 改 `cleanup()`（先 unmount 清 interval）→ `vi.clearAllTimers()`（丟棄 pending setTimeout 不執行）→ `vi.useRealTimers()`。fake timers 只攔 timer 不動 Promise microtask，`await act(async)` 仍正常 flush。
2. **[must-2 假綠]** Save 測試未改欄位即斷言 `onSave` 帶 `settings`，因 formData 初值即 settings 拷貝、deep-equal 通過 → 無法區分 `onSave(formData)` 與 bug 的 `onSave(prop)`。改為先 Select 改 dataSource（SIMULATION→OPC_DA）再 submit，斷言 `objectContaining({dataSource: OPC_DA})`，守住「提交 formData 而非 prop」契約。
3. **[should-3 互斥未守]** wind profile aria-pressed 只斷言「平靜 true」，未守「中等（原 active）變 false」→ 固定 mock 會讓舊 profile 永遠 active、雙重 active bug 靜默放行。新增 `statefulConfigFetch()`（POST {profile} 後 GET 反映新 profile），斷言切換後「中等」aria-pressed false。
4. **[should-4]** `let result` 缺 definite assignment → 加 `!`。
5. **[should-5]** `postBodies` 內 `init2` 多餘間接層 → inline cast。
6. **[nice-6]** wind status 測試只斷言 mode 值 → 加「模式」標籤斷言（`getAllByText(/模式/)`，wind+grid 兩區塊皆有）。
7. **[nice-7]** 缺 `handleSetCustomGrid` POST body 測試（與 custom wind 對稱）→ 新增「套用自訂電網」→ POST `{frequencyHz, voltageV}`。
8. **[nice-8]** 缺 grid profile aria-pressed 測試 → grid profile 測試改點「低頻」+ 用 statefulConfigFetch 守互斥（低頻 true / 標稱 false）。

**Verify（採納後）**：`tsc` 0 error + `vitest` **179 passed**（162 baseline + 17 新，零 regression）+ `vite build` ✓。

## 6. 下次 session 接手建議

- **同範式續推 component render 測試**：HistoryPage（809）/ TurbineDetail（1056）/ workflow 子面板（WorkOrderListPanel / PendingApprovalPanel 等 panel 級互動）。基礎設施 + 六個範例（FieldPage / ReportsPage / CostPage / FarmOverview / WorkflowPage / SettingsPage）已就位。
- **M5-5 Part B-2**（my work orders + completion）—— 仍需劉老師釐清 persona/auth「who is me」（🟡）。
- **M5-2 ChromaDB**（🔵；需評估 CI 加 `chromadb` 重依賴的安裝時間 / Linux runner 相容，謹慎勿動搖飛輪）。
- **22 個 stale PR triage**（待劉老師 / 後續 session）。

## 7. 給劉老師小問題

- （無新增。）
