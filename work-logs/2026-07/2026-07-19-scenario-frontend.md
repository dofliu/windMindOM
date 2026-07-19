# 2026-07-19 — 情境保存/調閱（前端）｜DEC-20260718-01 #4 收尾

> Session 類型：#4 前端（承後端 #138 merged）
> 產出：本 PR（ScenarioPage 命名 + 過去情境清單 + ScenarioDetail 調閱視圖）
> 對應 issue：WMOM-20260719-02（前端部分，完成整個 #4）｜DEC-20260719-01

---

## 做了什麼

用戶回報「回頭點情境模擬看不到之前產生過的情境」。後端（#138）已把情境存成命名 session；
本 PR 把調閱體驗接到前端：

1. **ScenarioPage.tsx**：
   - 加「情境名稱」輸入；`generate-bulk` body 帶 `name`（**留空自動以時間戳命名**——確保 ScenarioPage
     的每次產物都可調閱，正是修「情境調不回來」）+ `wind_profile`。
   - 新增「**過去情境**」清單卡（`GET /api/scenarios`）：每列顯示名稱/產生時間/風況/時長/筆數/注入數
     + 「觀察 →」+「刪除」；生成成功後即時刷新清單。
   - **observe 模式**：選某情境 → 早 return 顯示 `ScenarioDetail`（其他 hooks 均在 return 前宣告）。
   - 結果卡帶 `scenario_id` 時，主行動改「觀察此情境 →」（找 saved 清單 → 進 ScenarioDetail）。
   - 刪除需 ADMIN；403 顯示「需系統管理員權限」而非靜默。
2. **ScenarioDetail.tsx（新）**：讀 `/api/scenarios/{id}/turbines/{tid}/history`（session 隔離）→
   「發電量 vs 風速」**雙軸趨勢**（複用 `utils/chartAxes.rightAxisTags`）+ **故障事件** ReferenceLine
   標記與清單 + 機組選擇 + 返回。全程 `authFetch`。
3. **測試**：ScenarioPage +8（命名/body 帶 name+profile/自動命名/清單/空狀態/觀察/刪除/結果卡觀察）；
   新增 ScenarioDetail 6（詮釋資料/mount 抓 history/事件清單/換機組重抓/返回/空資料）。
   前端 **905 全綠**、tsc 乾淨、vite build 通過。

## 眉角 / 決策

- **一律命名**：ScenarioPage 的產物一律存成命名情境（留空自動命名），而非沿用「寫 active session」的
  舊路徑——因為使用者的心智模型是「在情境模擬產生的東西就該能調回來」。快速批次（不存）走
  FaultInjectionPanel，非本頁。
- **調閱走自建 ScenarioDetail 而非改 HistoryPage**：HistoryPage 用裸 fetch + 時間範圍/比較分頁，與
  「固定資料集的情境」語意不合；自建 ScenarioDetail 走 authFetch（enforce-ready、與 ScenarioPage 一致）
  且直接吃後端的 `readings`/`events` 形狀，回歸風險低。
- **雙軸複用 #132 的 `rightAxisTags`**：發電量（百 kW）與風速（個位數 m/s）同軸看不到風速，複用既有純
  函式判定移右軸。
- **events 非 session 隔離**：後端回 `events_by_time_window` 旗標（時間窗重疊可能混入），ScenarioDetail
  只取 `event_type==='fault'` 呈現，範圍可控。

## code review 結果（code-reviewer subagent）

- **Needs revision → 已收**：2 Must-fix（1 個是 CI tsc 已於 bac8ddf 修）+ 6 Should-fix + 7 Nice-to-have。
  - **Must-fix（CI）**：`ScenarioConfig` 漏 `kind` → tsc TS2353 擋 CI（bac8ddf 補 `kind?`）。教訓：**新增/大改
    test fixture 型別後一定要跑 `tsc --noEmit`**（vitest 不做型別檢查）。
  - **Must-fix（開放）**：`ScenarioDetail` 寫死 `limit=3000` → 預設 168h/60s 情境=1万筆/機組，只回最新
    3000（約最後 50h），排在 atHour=84（中段）的故障被靜默截掉、看不到——正打在本頁目的。修：
    `limit=12000`（覆蓋常見情境全長）+ 命中上限時顯示截斷提示。
  - **Should-fix**：「觀察此情境」原靠 `savedScenarios.find` 有競態且測試假綠 → 改用生成輸入就地組
    `lastScenario`（不依賴非同步刷新），測試改 `saved:[]` 真正守住；清單觀察/刪除 aria-label 併入
    情境名（多列不再撞名）；`wind_profile` 走 `windProfileLabel`（抽 `utils/windProfiles.ts`，兩元件共用，
    避免顯示原始代碼）；刪除改 `variant="danger"` + `window.confirm` 二次確認；補刪除 403/取消 兩分支
    測試；`ScenarioDetail` 故障事件明確按時間排序（對齊圖表左→右）。
  - **Nice-to-have**：生成後清空情境名（避免疊同名）。
- tsc / 前端 **908 全綠** / build 通過。

## 卡在哪 / 下次怎麼接手

- **本 PR（#4 前端）**：review 收完 → 移除 hold → flywheel 自動合。合併後 **#4 整個完成**。
- **接下來 #3 啟動 gate**（DEC-20260719-01 交付分階段 3）：`app.py` lifespan 不自動
  `broker.start(SIMULATION)`；前端強制登入後出「選資料來源」頁（實接 / 即時模擬 / 產生情境 /
  調閱過去情境——後者用本 PR 的過去情境清單）。
