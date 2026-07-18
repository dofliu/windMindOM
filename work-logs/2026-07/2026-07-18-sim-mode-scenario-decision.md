# 2026-07-18 — 機組資料實測修正 + 模擬運作模式雙軌決策

> Session 類型：實測 → bug 修正 → 架構決策（改變方向 → 進 decision_log）
> 產出：PR #123（wind fix，待審）+ 本 PR（DEC-20260718-01 決策文件，待審）
> 對應 issue：WMOM-20260718-01~05｜DEC-20260718-01
> 前段 session context：auth 批次收尾（#115-#122，全 5 module router 授權 + 前端真登入）+ 風機物理模型盤點

---

## 做了什麼

1. **auth 批次收尾**（承前段）：workflow（material_request / approval / work_order）+ inventory + cost/reporting（SUPERVISOR＋）+ knowledge + monitoring 9 支 router 全部 enforce-aware 授權遷移，前端 authClient/useAuth/LoginPage 真登入落地（#115-#122 皆 merge）。
2. **物理模型盤點**：讀 `docs/physics_model_status.md`（602 行）→ 結論**已達 research-grade 完整**（Bastankhah-Porté-Agel wake、Larsen DWM、Glauert、Monin-Obukhov、IEC 61400-12-1/2、fatigue/DEL/RUL；121 tests pass）。深化屬學術性、暫 park；建議「把已算好的 RUL surface 出來」優先於再深化模型。
3. **實測機組資料** → 用戶反映 6 點（開機預設狀態、Settings 改風速無反應、故障卡住、換風場隔離、看不到反應、要求驗證「資料產生」正確性）。
4. **WMOM-20260718-01 修風速 bug（PR #123）**：
   - 根因＝`baseWindSpeed` 前後端**雙重被丟**：前端 `useSettings.simChanged` 變更偵測漏掉 baseWindSpeed（只改風速不 POST）＋後端 `config.set_simulation` in-place 分支只套 turbulence、丟掉 base wind。
   - 修法：前端 `simChanged` 補 baseWindSpeed 比較；後端改呼叫 `wind_model.set_override(wind_speed=, turbulence=)`。
   - +6 tests（後端 `test_wind_config_apply.py` 3：override 記風速/turbulence、clear 回 auto、**風速→發電**鏈路 14m/s≈額定 vs 2m/s≈0；前端 `useSettings.test.ts` 3：只改風速也 POST / turbineCount 未回歸 / 無變更不 POST）。
5. **架構質疑 → DEC-20260718-01**：用戶深挖「連續即時模擬 + 持續落地」是否合理（電腦會關/暫停、物理模型可一次批次生成、IEC 61400「給定風況跑一次」、但我們還有運維這層、又保留了外接實際資料選項）。
   - 盤點確認：`generate_bulk` 已可批次生成最多 1 年（`duration_hours≤8760`）；每風場已有各自 DB（`data/farms/{id}/wind_farm.db`）；但**故障 runtime-only 未落地**（`_active_faults` 記憶體，重啟/換場即清）。
   - **拍板雙軌**：**Scenario**（模擬）＝情境定義（風場+風況+時長+故障排程）→ 批次生成可重現資料集 → 進場探索 + 跑運維；**Live**（實接）＝SCADA/OPC/Modbus 連續落地。以「資料是否可重現」切分。

## 眉角 / 決策

- **改變方向等級**：模擬主路徑從「連續 free-run」改「情境批次」屬產品方向變更 → 依 CLAUDE.md §6.3 先寫 `DEC-20260718-01` 再動工，PR 掛 `hold` 待劉老師審。
- **用戶 6 點問題如何收斂**：#1 已修（PR #123）；#2 啟動流程升級為「情境設定精靈」；#3 狀態可見性照原計畫（顯示為何不發電 + header 顯示風場）；#4 故障持久化**被 Scenario 自然吸收**（故障成情境定義一部分）；#5 turbine 顯示重設計照原計畫（發電-風速主圖）。
- **cut-out / 故障 ephemeral 是「對但易混淆」非 bug**：>25m/s 停機、故障 runtime-only 都是既有設計；真正的 bug 只有 #1 風速雙丟。Scenario 模式順帶讓故障變可重現。
- **generate_bulk 需加故障排程參數**：`[{sim_time, turbine_id, fault_type}]`，批次生成時於指定時點注入 → 寫 events + 影響該時段 physics。

## 卡在哪 / 下次怎麼接手

- **本 PR（DEC 決策）待審**：劉老師 review DEC-20260718-01 的 Consequences / 交付分階段後放行 → 才動 build。
- **PR #123（wind fix）待審 merge**（`hold`）。
- **依序 build**（DEC 拍板後）：
  1. **WMOM-20260718-03** #2 scenario-setup 流程（含 `generate_bulk` 故障排程參數）— 🟡 最大塊，前後端都動。
  2. **WMOM-20260718-04** #3 狀態可見性 — 🔵 前端 turbine 顯示 + header。
  3. **WMOM-20260718-05** #5 turbine 顯示重設計 — 🔵 前端圖表主次調整。
- **接手指引**：先讀 `decision_log` DEC-20260718-01 全文（兩軌切分表 + 交付分階段）+ 本檔。scenario-setup 動工前先確認 `generate_bulk` 現有簽章（`server/routers/config.py`）與故障注入點（`fault_engine`）。
