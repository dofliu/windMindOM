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

## 卡在哪 / 下次怎麼接手

- **本 PR（#4 前端）**：draft + `hold`（待 code review）→ 收 review → 移除 hold → flywheel 自動合。
  合併後 **#4（WMOM-20260719-02）整個完成**。
- **接下來 #3 啟動 gate**（DEC-20260719-01 交付分階段 3）：`app.py` lifespan 不自動
  `broker.start(SIMULATION)`；前端強制登入後出「選資料來源」頁（實接 / 即時模擬 / 產生情境 /
  調閱過去情境——後者用本 PR 的過去情境清單）。
