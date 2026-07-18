# 2026-07-18 — Scenario 模式實作（後端 primitive + 前端情境頁）

> Session 類型：DEC 拍板後依交付分階段 build（承 DEC-20260718-01）
> 產出：PR #125（後端 generate_bulk 排程故障，merged）+ 本 PR（前端 ScenarioPage）
> 對應 issue：WMOM-20260718-03｜DEC-20260718-01

---

## 做了什麼

1. **後端 primitive（#125，merged）** — `WindFarmSimulator.generate_bulk` 新增 `fault_schedule`
   （一組 `TestPlanStep`，各於自身 `offset_seconds` 注入）+ `on_fault_injected` 回呼；
   `POST /api/config/simulation/generate-bulk` 端點以 `_parse_fault_schedule` 驗證使用者排程
   （`{scenario_id, turbine_id, at_hour|offset_seconds, severity_rate?}`）後接上；`run_test_plan`
   重構為委派給 `generate_bulk`，消掉重複的批次迴圈。
   - **code review 修正**（同 PR 第二 commit）：事件用**模擬時間戳**（原 wall-clock now → 事件標記
     與資料時間軸對不上）；`_parse_fault_schedule` 畸形數值/非陣列 → 乾淨 400（原打穿成 500）；
     `faults_injected` 改回報實際注入數；尊重 `inject()` 回傳值。共 19 tests。
2. **前端情境頁（本 PR）** — 用戶選「新增『情境』獨立頁」。新增 `frontend/components/ScenarioPage.tsx`：
   - 情境設定：目前風場（側邊欄切換）+ 風況 profile（calm…storm/gusty/ramp）+ 時長（小時，含
     1天/1週/1月 preset）+ 解析度 time_step。
   - 故障排程：可增可刪，每列 {場景 / 風機 / 第幾小時 / 發展速率}；at_hour ≥ 時長顯示「不會被注入」警告。
   - 生成：先 `POST /api/config/wind {profile}` 再 `POST generate-bulk {duration_hours, time_step,
     fault_schedule}` → 結果卡（筆數 / 注入數 / 最終故障狀態）+「查看歷史資料 →」跳 history。
   - 全走 `authFetch`（enforce-ready，不同於舊 `FaultInjectionPanel` 的裸 fetch）。
   - App.tsx 接 `scenario` view + SECONDARY_NAV「情境」；Logo.tsx 加 `scenario` 燒瓶圖示。
   - +18 render tests；tsc / 847 前端測試 / vite build 全綠。

## 眉角 / 決策

- **情境頁 = FaultInjectionPanel 的一般化**：既有「故障模擬」頁已能對 5 個預設 test plan 批次生成；
  情境頁讓使用者建**自訂**排程（自己的風況+時長+故障）。兩頁並存（故障模擬保留給快速注入/預設計畫）。
- **風況先套再生成**：`POST /api/config/wind` 設 profile → `generate_bulk` 的 `_run_one_step` 每步
  由 wind_model 取風速，故 profile 於批次全程生效。兩請求循序（await），無 race。
- **Live/Scenario 並行取捨**：generate-bulk 帶排程會 `fault_engine.clear()`（含 Live 故障）且與背景
  free-run loop 共用未加鎖狀態——此為**既有** `run_test_plan` 就有的行為，本頁沿用不擴大。完整的
  「停 Live → 跑 Scenario」流程留待後續（已於 #125 docstring 標註）。
- **enforce-ready**：新元件一律 `authFetch`；舊 `FaultInjectionPanel` 仍裸 fetch（未來可一併換）。

## 卡在哪 / 下次怎麼接手

- **本 PR 待審 merge**（draft + `hold`）。合併後 WMOM-20260718-03（scenario-setup 流程）即完成。
- **接下來依 DEC 交付分階段**：
  - **WMOM-20260718-04** #3 狀態可見性 — 🔵 turbine 顯示「為何不發電」（cut-out/故障跳機/停機）+
    header 顯示當前風場。
  - **WMOM-20260718-05** #5 turbine 顯示重設計 — 🔵 發電量 vs 風速 主圖，降級四色 mini-trend。
- **接手指引**：情境頁 API 契約見 `ScenarioPage.tsx` 頂部註解；後端排程參數見 `_parse_fault_schedule`
  與 `generate_bulk` docstring。舊 `FaultInjectionPanel` 換 `authFetch` 可順手納入未來 PR。
