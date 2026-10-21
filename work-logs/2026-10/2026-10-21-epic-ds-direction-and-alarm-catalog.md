# 2026-10-21 — 方向調整（EPIC-DS 擬真資料源）+ Phase 1a Z72 真實警報目錄

> Session 類型：規劃 + 實作
> Session 長度：長
> 主導：劉老師（定調）/ Claude（盤點、設計、實作）
> 結果：DEC-20261021-01 定案，EPIC-DS 立案（9 個 issue），Phase 1a（WMOM-20261021-02）完成

---

## 1. Session 目標

1. 回答劉老師：專案中「產生與真實系統一樣的風力機運轉資料」（結構、負載、物理）現況如何；整體進度與未來走向。
2. 依劉老師定調調整方向，並開始做第一個實作階段。

## 2. 實際完成

### 2.1 主要工作

- **現況盤點（2026-10-20）**：用 Explore 子代理分三條線調查（物理層、整體進度、警報 / 事件 / 對外介面），關鍵結論親自對原始碼與 xlsx 驗證。重點：
  - 物理涵蓋面廣、精度淺；未曾與真實 SCADA / OPC / OpenFAST 比對（`tests/physics/` 121 測幾乎都是自洽性檢查）
  - `update_spec`（`turbine_physics.py:303`）只重建 power curve / rotor / drivetrain，非 Z72 機型的電氣、熱、疲勞、振動仍用 Z72 值
  - 疲勞未校正、隨 dt 改變；風場為單一 AR(1)（f⁻² 頻譜，非 Kaimal）；Region 3 pitch 為 open-loop 查表
  - `routers/farms.py:344` 檢查從未 start 的 `sim._running`，資料集產生 0 筆
  - **模擬器 24 個警報碼多個與真實 Z72 不符**（350/351/311/30/32/241 意義不同、41/42/43 不存在、223/256/273 等級錯）
  - 情境（bulk）路徑不產生警報 / 跳機事件；`history_events` 無 `session_id`；沒有任何標準答案
- **劉老師定調（2026-10-21）**：商業時程不需要、先把功能完備；真實風場 / OPC 暫緩；系統要產生相對真實的資料，餵給外部 RAG 即時維修助手（學生專題建立）做驗證；輸出要檔案、串流、模仿 tag 的 OPC UA server 三種。
- **文件**：DEC-20261021-01；`docs/product/EPIC-DS_realistic_data_source.md`（擬真定義、現況盤點、三管道架構、介面合約 v0、分階段計畫）；ROADMAP / STATUS.yaml / CLAUDE.md §10、§15 / TODO.md / ISSUES.md 同步。
- **WMOM-20261021-02（Phase 1a）實作**：
  - `tools/build_z72_alarm_catalog.py`：xlsx「警告訊息列表」A-D 欄（314 筆）+ 手冊 Appendix C（pdfplumber 解析 p.104-130，307 筆）合併 → `shared/data/z72_alarm_catalog.json`（306 筆帶原因 / 處置 / 每小時重啟上限 / 頁碼）
  - `shared/alarm_codes.py`：`AlarmDef` + `get_alarm` / `find_alarm` / `is_known_code` / `all_alarms`
  - `fault_engine.py`：11 情境改用真實碼，`desc` 直接用目錄原文；門檻慣例 A < `auto_trip_severity`、T1/T2 == `auto_trip_severity`
  - 連帶：knowledge baseline 語料 9 個 chunk、`FieldPage.tsx` 一鍵告警碼、`turbine_physics.py` overspeed 註解

### 2.2 卡住或延後的事

- 警報仍由 severity 觸發，物理量級與真實判定條件不一致（pitch 偏差、風向標差、超速轉速、電網電壓）→ 併入 -03；清單見設計文件 §6.1
- 物理層自有跳機（overspeed / cut-out / grid / ride-through）仍只寫 `shutdown_cause` 字串，沒有事件碼 → Phase 1b / 2
- 跳機一律走 emergency stop，但 T1 應為正常伺服停機 → 併入 -03
- 變頻器相關碼（400-700）手冊只寫「See [ABB]」：RAG 只靠 Z72 手冊會查不到細節，ground truth 設計時要標註（-04）

### 2.3 重大決策

- DEC-20261021-01：暫停商業時程與真實現場介接；主線改為 EPIC-DS 擬真資料源

## 3. 產出清單

### 新增檔案

- `docs/product/EPIC-DS_realistic_data_source.md`
- `tools/build_z72_alarm_catalog.py`
- `shared/data/z72_alarm_catalog.json`
- `shared/alarm_codes.py`
- `tests/test_alarm_codes.py`
- `modules/monitoring/tests/test_fault_alarm_codes.py`
- 本 work-log

### 修改檔案

- `docs/product/decision_log.md`（DEC-20261021-01）
- `docs/product/ROADMAP.md`（暫停 banner、dashboard、現行主線一節）
- `STATUS.yaml`（M6 deferred、EPIC-DS milestone、issue_stats 重新核實）
- `CLAUDE.md`（§10 目前狀態、§15 參考機型）
- `TODO.md`、`ISSUES.md`
- `modules/monitoring/simulator/physics/fault_engine.py`（11 情境改真實碼）
- `modules/monitoring/simulator/physics/turbine_physics.py`（註解）
- `modules/knowledge/data/baseline_corpus_z72.json`（碼與文字）
- `frontend/components/field/FieldPage.tsx`（一鍵告警碼）

### 動了狀態的 issue

- WMOM-20261021-01：新增 → done
- WMOM-20261021-02：新增 → done
- WMOM-20261021-03 ~ -09：新增 open
- WMOM-20260503-05：in_progress → deferred
- WMOM-20260509-F6：open → deferred

### 寫進 decision_log 的決策

- DEC-20261021-01：暫停商業時程與真實現場介接；主線改為擬真資料源，供外部 RAG 即時維修助手（學生專題）驗證

## 4. 下次怎麼接手

1. **WMOM-20261021-03（Phase 1b）**：接上 `TurbineSpec` 溫度 / 壓力門檻並對應真實碼；修故障期間 7↔3 狀態跳動（跳機 latched + 每小時重啟上限，上限值可直接用目錄的 `max_per_hour`）；monitoring 時間戳改 UTC tz-aware
2. **WMOM-20261021-04（Phase 2）**：情境 metadata（根因 / 元件 / 預期警報序列 / 手冊條目 / 處置）+ bulk 路徑事件 + `session_id`
3. 阻擋項：無。`-09` 合約 v1 定稿前需劉老師確認 ground truth 評分欄位

## 4.1 Code review（code-reviewer subagent）

- 0 must-fix、5 should-fix、5 nice-to-have；下游無破壞（唯一消費者 `data_broker.py` 以 scenario:type:code 去重）
- 已處理：
  - generator_overspeed 351/027 → 351/320（對齊物理層兩道超速保護）
  - converter_cooling 加 432 靜水壓低（物理層有 O-ring 洩漏）
  - grid_voltage_sag 4 個同時跳機碼 → 481 + 021
  - hydraulic 260 門檻 0.3 → 0.4（對齊 180 bar）
  - builder：sanity guard（筆數下限、無法辨識的表格列直接報錯）、重複碼偵測、workbook close、空值統一 None、修 PDF 斷字
  - `alarm_codes.py`：載入時驗證等級，docstring 補 Returns
  - 設計文件 §3 標成 Phase 1a 前的快照，新增 §6.1 門檻慣例與已知限制
  - FieldPage chip 同時帶入真實等級（+1 測，mutation-verified）
- 併入後續 issue：警報對齊物理訊號、T1 正常停機（-03）；事件 title 帶碼（-04）
- 未採納：測試參數改 `Dict[str, object]`（會讓門檻比較在型別上不合法；維持與 `FaultScenario.alarm_codes: List[Dict]` 一致）；`AlarmLevel` 與 knowledge schema 合併（跨模組重構，非本 issue 範圍）

## 5. 驗證

- backend：`python -m pytest modules/*/tests/ tests/ -q` → **1435 passed / 7 skipped / 1 xfailed**（基準 1305；新增 `test_alarm_codes.py` 與 `test_fault_alarm_codes.py`；review 修正後情境警報數 25→24，參數化測試隨之變動）
- 來源漂移測試在本機（有 openpyxl + pdfplumber）實際執行並通過；CI 無這兩個套件時 skip
- mutation 檢查：把 `fault_engine.py` 還原成舊碼，`test_fault_alarm_codes.py` 46 項失敗
- frontend：`tsc --noEmit` 0 error；`vitest run` **1501 passed**（70 files；+1 FieldPage chip 帶等級）

## 6. 學到的事

- xlsx「警告訊息列表」E-H 欄是另一份錯位的對照表（Event ID 與 Code 不對齊），只能用 A-D 欄
- 手冊 Appendix C 的表格 pdfplumber 可以穩定抽出；chunks.jsonl 的 raw text 拆字太碎，不適合解析
- 舊情境把 T1 跳機碼門檻設在 auto-trip 之前（例 bearing_wear 240 @0.7、trip @0.85），會產生「跳機碼已出現但機組還在發電」的不真實資料

## 7. Open questions（park）

- 外部 RAG 助手的學生專題時程與介面需求（等劉老師提供後再定稿合約 v1）
