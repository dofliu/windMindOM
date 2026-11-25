# CLAUDE.md — windMindOM 開發守則

> 給 Claude（與其他 AI 助理）在這個 repo 工作時用的精簡指引。
> 完整產品脈絡見 [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md)。
> 任何新 session 開工前**必讀本檔**。

---

## 1. 專案一句話

**離岸風場運維廠商工具**：監控 + 庫存派工 + 成本計算 + 報表 + 警報手冊查詢，給運維廠商管理層 + 現場工程師雙 persona 用。
從 digiWindTurbine（物理模擬器 + SCADA 平台）商業化升級而來。

**2026-11-25 起的定位（DEC-20261125-01）：仿真運維風場**——像真實風場一樣持續運轉、資料循環保存、可設定故障與耗損、工單 / 定檢 / 可用率連動、成本計算，並提供對外資料 API 給外部的 RAG 運維助理做測試驗證；出發前助理保留為工單上的準備卡。上面那句運維廠商的商業定位保留為歷史，五個模組都留用。

---

## 2. 任何 session 接手的 3 步必做

1. **讀本檔 CLAUDE.md** — 知道工作守則
2. **讀 [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md)** — 產品定位、ICP、5 大功能
3. **讀 [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md)** + [`STATUS.yaml`](STATUS.yaml) — 知道現在進到哪個 month / module
4. （如有 ISSUES.md）從 `ISSUES.md` 找 `status: open` 的 WMOM-* 認領

---

## 3. 文件入口（按閱讀順序）

| 檔案 | 用途 | 何時讀 |
|------|------|--------|
| **本檔 `CLAUDE.md`** | 工作守則、repo 角色、commit 規範 | 任何新 session 第一個讀 |
| [`docs/architecture/windMindOM-architecture.md`](docs/architecture/windMindOM-architecture.md) | **一張圖看全貌** + 8 張細節圖（EPIC-DS 資料流與盲測邊界 / monitoring 內部 / 模組分層 / 工單狀態機 / 簽核 / repo 關係 / 儲存結構 / 時程與現況）；2026-10-22 更新 | **第一次接觸 / 對外 demo / partner 對接** |
| [`docs/architecture/research-framework.md`](docs/architecture/research-framework.md) | **仿真運維風場研究架構圖**（2026-11-26 定稿）：仿真風場、對外 API、運維閉環、出發前準備卡、自動評分的關係與建置順序 | **了解現行主線 EPIC-SF 時先看** |
| [`docs/product/PRODUCT_VISION.md`](docs/product/PRODUCT_VISION.md) | 產品願景、ICP（運維廠商）、5 大功能、商業模式、競品 | 對齊產品方向時 |
| [`docs/product/MVP_ARCHITECTURE.md`](docs/product/MVP_ARCHITECTURE.md) | 5 modules 設計、外部介接、技術選型 | 設計與實作時 |
| [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md) | M1-M6 6 個月路線圖、每月主要交付 | 規劃 sprint 時 |
| [`docs/product/decision_log.md`](docs/product/decision_log.md) | 重大決策 ADR 紀錄（含 v0.5 → v0.8.1 pivot） | 想改變方向前必讀 |
| [`docs/legacy/digiwt_project_notes.md`](docs/legacy/digiwt_project_notes.md) | 既有 digiWT 物理模型 / SCADA 技術筆記 | 動 monitoring 層時讀 |
| [`docs/API_GUIDE.md`](docs/API_GUIDE.md) | digiWT 既有 40+ REST/WS endpoints 規格 | 動 API 時讀 |
| [`docs/physics_model_status.md`](docs/physics_model_status.md) | 物理模型完成度 | 動物理模型時讀 |
| `STATUS.yaml` / `ISSUES.md` / `TODO.md` | （將於 M1 第一週重建為 windMindOM 版本） | 接手 + 找事做時 |

## 4. Repo 結構與角色

```
windMindOM/                          ← 本 repo（從 digiWindTurbine 進化）
├── api/                             ← FastAPI（既有 + 擴充）
├── modules/                         ← 6 大功能 module（M1 起逐月建立）
│   ├── monitoring/                  ← digiWT 既有 SCADA + simulator（M1 搬入）
│   ├── workflow/                    ← 庫存 + 派工 + 簽核（M3-M4 新做）
│   ├── cost/                        ← ECN 移植（M2）
│   ├── reporting/                   ← 報表生成（M4）
│   ├── knowledge/                   ← RAG 警報查手冊（M5）
│   └── auth/                        ← JWT + RBAC 授權（M6-4，純 stdlib）
├── shared/                          ← canonical schema、PLC clients、共用 domain model、Z72 警報 / tag 清單
├── examples/rag_starter_kit/        ← 給學生 RAG 專題的 starter kit（範例資料包、讀取 / 基準 / 評分程式、WS 回放客戶端）
├── frontend/                        ← React + responsive design（admin + field 雙路徑 + 真登入頁）
├── opc_bachmann/                    ← Z72 OPC client（既有，M1 抽到 shared/plc_clients/）
├── tests/                           ← pytest
├── docs/
│   ├── product/                     ← v0.8.1 產品文件 ★ 主要 source of truth
│   ├── integration/                 ← 對外介面合約（RAG 助手資料介面合約 v1.7、對外唯讀 API v1.1）
│   ├── legacy/                      ← digiWT 既有技術筆記
│   ├── routines/                    ← daily-workflow.md（M1 從 v0.5 搬入）
│   ├── API_GUIDE.md                 ← digiWT 既有 API 規格（沿用）
│   ├── physics_model_status.md      ← digiWT 既有物理模型狀態（沿用）
│   └── __Z72UserManual.pdf          ← Z72 手冊（M5 餵 RAG）
├── work-logs/                       ← 每日 routine 紀錄（M1 起每日新建）
├── templates/                       ← work-log / issue / decision 模板
├── deploys/                         ← docker-compose（single-farm / multi-farm）
└── (root 既有 digiWT 檔案)            ← M1 第一週搬到 modules/monitoring/
```

## 5. 與其他 7 個 repo 的關係

| Repo | windMindOM 對它做什麼 |
|------|---------------------|
| **digiWindTurbine**（原 repo） | 不動，留作研究 / 教學版本；windMindOM 是它的商業化 fork |
| **ECN** | M2 移植進 `modules/cost/`，原 repo archive |
| **z72_etech** | M3-M4 取設計重寫進 `modules/workflow/`（**僅取設計、不取程式**），原 repo archive |
| **z72hmiNew** | 留外面（Z72 服務性 repo） |
| **windAILab** | 留外面（**另一公司業務**）；M6+ HTTP API 介接 AI 故障診斷 |
| **RAG_Ultimate** | 留外面（research line）；M5 提供「策略檔 + 預計算向量檔」給 windMindOM/modules/knowledge/ |
| **InduSpect** | 留外面（independent product）；M6+ HTTP API 介接 AI 視覺定檢 |

## 6. 工作流（每個 session）

### 6.1 開工

```
1. 讀 CLAUDE.md（本檔）+ PRODUCT_VISION + ROADMAP + STATUS.yaml + ISSUES.md
2. 從 ISSUES.md 認領一個 issue（或從 ROADMAP 該月 deliverable 拆 sub-issue）
3. 開新 git 分支：claude/issue-{N}-YYYY-MM-DD
4. 開新 work-log：work-logs/YYYY-MM/YYYY-MM-DD-{slug}.md
5. 進 routine（見 docs/routines/daily-workflow.md）
```

### 6.2 結尾

```
1. work-log 收尾（完成什麼、卡在哪、下次怎麼接手）
2. 更新 STATUS.yaml + ISSUES.md
3. Commit：type(#WMOM-{N}): 描述
4. （人工確認後）git push
```

### 6.3 重大決策

任何「動到架構 / 改變方向 / 重新定位」必須寫進 `docs/product/decision_log.md` 為 DEC-{YYYYMMDD}-{NN}。

## 7. Coding 規範

- **Python**：型別標註必加；docstring Google style；繁中說明
- **命名**：snake_case 變數函式、PascalCase class、UPPER_SNAKE 常數
- **不用 `Any`**（必要時 `# type: ignore[原因]` 並註明）
- **對使用者輸出繁體中文，技術術語保留英文**
- **編輯前先 Read**；CRLF 行尾保留原樣
- **Test-first 原則**（不嚴格 TDD，但每個 module 都要有 test）

## 8. Git / commit 規範

- 主分支：`main`（單 dev 階段直接 push）
- Feature 分支：`claude/issue-{N}-YYYY-MM-DD`
- Commit 訊息：`type(#WMOM-{N}): 描述`
- type ∈ feat / fix / docs / refactor / chore / test
- 帶 `#WMOM-{N}` 編號自動關聯本 repo 的 ISSUES.md

## 9. 任務 ID 格式

- Issue：`WMOM-{YYYYMMDD}-{NN}` （例：WMOM-20260503-01）
- Work-log：`work-logs/YYYY-MM/YYYY-MM-DD-{slug}.md`
- Decision：`docs/product/decision_log.md` 內以 `## DEC-{YYYYMMDD}-{NN}` 標號

WMOM = WindMindOM 縮寫。

## 10. 目前狀態（簡要）

> 進度以 [`STATUS.yaml`](STATUS.yaml) 為準；本節為快照，更新時請同步。

- **產品版本**：v0.8.1（2026-05-02 baseline）
- **方向（2026-11-25 DEC-20261125-01）**：重新定位為**仿真運維風場**，現行主線 = **EPIC-SF**。六項：擬真物理、持續運轉與資料循環保存、可設定的故障與耗損、工單 / 定檢 / 可用率連動、成本、對外資料 API 給外部的 RAG 運維助理；出發前助理保留為工單上的準備卡（故障出勤卡先做），只用可觀測資料、不判定根因，用不對外的故障紀錄核對。順序（劉老師 2026-11-25 確認）：WMOM-20261125-02 對外唯讀 API → -03 長時間運轉的基礎 → -04 運維閉環 → -05 出發前準備卡 → -06 機率式故障產生器 → WMOM-20260504-11 成本 → -07 實測風況匯入。已確認的預設：10 秒原始資料保留半年、對外以 REST 為主、OPC UA 並存、外部系統用長效 API 金鑰對應唯讀角色。研究架構圖已定稿：[`docs/architecture/research-framework.md`](docs/architecture/research-framework.md)。商業時程與真實風場 / OPC 介接仍暫緩；RAG 運維助理本身仍在 windMindOM 之外；EPIC-DS 已完成、保留為題庫，它的守則（盲測、資料包、合約、回放、OPC UA）照舊，對外 API 與準備卡給出去的資料同樣不得帶故障原因或注入資訊
- **前一次方向（2026-10-21 DEC-20261021-01）**：商業時程（M6 PoC / 合約 / 客戶接觸）與真實風場 / OPC 介接**暫緩**，先把功能完備。**現行主線 = EPIC-DS 擬真資料源**：模擬器產生附標準答案（ground truth）的擬真 Z72 運轉資料，經 ① 檔案 ② WebSocket 串流 ③ 模仿 Bachmann tag 的 OPC UA server 餵給外部 **RAG 即時維修助手**（學生專題建立，windMindOM 不實作）做驗證。設計與介面合約 v0：[`docs/product/EPIC-DS_realistic_data_source.md`](docs/product/EPIC-DS_realistic_data_source.md)
- **EPIC-SF 進度**：第 1 項 done（WMOM-20261125-02，2026-11-26：對外唯讀 API `/api/ext/v1` 九個 `GET` ＋ 外部系統的 API 金鑰，DEC-20261126-01；文件 [`docs/integration/external_api_v1.md`](docs/integration/external_api_v1.md)，管理用 `tools/external_api_keys.py` 或 `/api/auth/api-keys`）；第 2 項 done（WMOM-20261125-03，2026-11-26：-03-a Live 時鐘單調 / 固定取樣間隔、-03-b 重啟續跑，DEC-20261126-02；-03-c 保留期可設定與分層儲存——原始讀值預設留半年，最近 3 天在 SQLite、較舊的在每日 Parquet 檔，DEC-20261126-03；72 小時連續運轉測試與歷史回填另開 WMOM-20261126-01 / -02）；第 3 項 done（WMOM-20261125-04，2026-11-26：運維閉環——跳機自動開單、工單開工讓機組進維修模式、完工才修好、可用率由運轉狀態紀錄計算，DEC-20261126-04）；第 4–7 項未開始
- **Milestone**：M1–M4 done；M5 ~75%（剩客戶手冊 / 一年警報 csv，隨 M6 暫緩）；M6 deferred（auth 全面完成部分保留）；**EPIC-DS Phase 1a done**（WMOM-20261021-02：Z72 真實警報目錄 `shared/alarm_codes.py` + 11 故障情境改用真實碼）；**Phase 1b-a done**（WMOM-20261021-03-a：故障物理校正到真實保護設定值，`TurbineSpec` 設定值、+5 真實 tag 111→116）；**Phase 1b-b done**（WMOM-20261021-03-b：PLC 保護層 `simulator/physics/plc_protection.py`，警報 / 跳機由訊號觸發、T1/T2 停機、鎖存與重啟上限、修 7↔3）；**Phase 1b-c done**（WMOM-20261021-03-c：monitoring 時間戳全面 UTC tz-aware，既有 DB 開檔一次性轉換）；**-10 done**（切出風速依手冊事件 201：10 分鐘 / 5 秒平均判定、正常停機、20 m/s 回切）；**-11 done**（風場時區 `FarmConfig.timezone`，日夜 / 季節循環依風場當地時刻，資料可跨機器重現）；**Phase 2 done**（WMOM-20261021-04：故障情境標準答案 metadata、批次路徑可觀測事件、`history_events.session_id`、標準答案 `scenario_ground_truth` 表與 `GET /api/scenarios/{id}/ground-truth`）；**Phase 3a done**（WMOM-20261021-05：情境資料包匯出 `server/scenario_pack.py`、`GET /api/scenarios/{id}/pack` / `pack/full`、CLI `tools/export_scenario_pack.py`）；**-12 done**（健康機組偶發 T2 336：修葉片同步誤差、規則照手冊，DEC-20261022-01）；**Phase 3b done**（WMOM-20261021-06：WebSocket 回放 `server/replay.py` + `/ws/replay`、回放 token、單次直播＋練習、伺服器蓋預測 ts，DEC-20261022-02；合約 v1.1 §12）；**Phase 3c done**（WMOM-20261021-07：模仿 Bachmann Z72 tag 的 OPC UA server `server/opcua_server.py`，回放 CLI `tools/opcua_server.py` ＋ 即時模擬 `WMOM_OPCUA_ENABLE`，DEC-20261022-03；合約 v1.2 §13）；**Phase 4 in_progress**（-08 拆子項；**-08-a done**：感測器故障 vs 真故障，PLC 只對注入的感測器看量測值、5 個感測器故障情境、新增真實 tag `WGEN_GnBrgTmp2` / `GnStaTmp2`，DEC-20261022-04；合約 v1.3；**-08-b done**：誤報 / 健康負樣本——風場事件〔電網擾動、風向快速變化〕、PLC 偏航逾時 223、nuisance 情境 Pt100 接點鬆動、標準答案 nuisance case、評分加干擾辨識率 / 把干擾當故障 / 誤報率、健康負樣本資料包 05，DEC-20261023-02；合約 v1.5；**-08-c done**：故障庫擴充 17 → 24——變槳驅動過載 381 → 367〔新增真實 tag `WROT_PtMotCurBl1-3`〕、冷卻水泵磨耗 422 → 439、去離子樹脂耗盡 423 → 440、轉速感測器 029 / 風速計 230 / 風向標 1 卡住 231、沒有警報的靜態偏航失準；刪 `gearbox_overheat`；`WCNV_IGCTWtrCond` 改正為導電度；範例資料包 06，DEC-20261023-03；合約 v1.6；**-08-d done**：多重故障＋早期徵兆——同機組多 case 歸屬不變＋新指標診斷精確率、早期徵兆 case〔有預期碼、情境內沒到警報〕分開列、排程 `max_severity` 把故障壓在警報門檻下、範例資料包 07，DEC-20261026-01；合約 v1.7；**-08 母 issue done**）；**WMOM-20261023-01 done**（直驅 `WGEN_GnSpd` 偏離轉子轉速：傳動鏈扭轉的顯式 Euler 在批次子步 5 s 數值不穩定，改以 ≤ 1 s 子步積分，dt 1 s 逐位元不變、範例資料包重建，DEC-20261025-01）；**手冊保真度 done**（WMOM-20261022-02，DEC-20261023-01：手冊 Appendix C / D 衝突以 D 為準——液壓 170 / 150 bar、30 s、190 bar 解除，233 延時 60 s＋60 s 平均風速，Pt100 10 s 濾波，切出陣風 3 s，273 為 45 °C，編碼器 −5–95°；自動重啟被封鎖改送 A039、拿掉全域每小時 3 次啟動上限；`yaw_sensor_drift` 每台機組都跳 233；合約 v1.4）；**全面檢查 done**（WMOM-20261022-01：三路 code review＋真伺服器端到端三條管道；DEC-20261022-05：正式評測要伺服器強制登入、批次生成移到背景執行緒、建立正式評測檢查總速率、手冊保真度另開 -02）；**Phase 3d done**（WMOM-20261021-09：介面合約 v1 定稿 [`docs/integration/rag_assistant_data_contract_v1.md`](docs/integration/rag_assistant_data_contract_v1.md)、學生 starter kit `examples/rag_starter_kit/`）
- **警報碼守則**：模擬器、語料、前端用到的 Z72 警報碼一律以 `shared/data/z72_alarm_catalog.json`（xlsx 314 筆 + 手冊 Appendix C；手冊獨有的 A039 也收錄、標 `manual_only`，共 315 筆）為準，不自創碼或描述；`tests/test_alarm_codes.py`、`modules/monitoring/tests/test_fault_alarm_codes.py` 會擋
- **物理改動守則補充**：新增感測器 / tag 的隨機數不可動既有的 RNG 序列——主 `_rng`（所有已校準的健康輸出）與 `_aux_rng`（風向標 2、電網電壓）都不行；新的感測器開自己的 stream（例：-08-a 的第二支 Pt100 用 `_rtd_rng`、-08-c 的變槳馬達電流與導電度基準用 `_ext_rng`），`test_fault_threshold_reach.py` 的守門測試要涵蓋；改既有 tag 的讀值（例：-08-c 的 `WCNV_IGCTWtrCond`）時感測器模型的抽樣次數不可變（`_get_sensor_config` 的 drift > 0、stuck_prob 照舊）；物理積分的穩定性要在**批次子步 dt 5 s**（`engine._MAX_PHYSICS_DT`）驗證，不只 Live 的 1 s——二階 / 剛性的動態（例：傳動鏈扭轉）在模型內再切子步（`drivetrain_model._TORSION_MAX_DT`），不要放寬 `_MAX_PHYSICS_DT`（`test_invariants.py` 14 種子 × dt 2.5 / 5 守門）；熱模型的發熱以 Z72 額定功率正規化（`thermal_heat_scale`，Z72＝1.0）：非 Z72 機型共用 Z72 的 PLC 設定值與警報目錄（簡化），健康機組不得被跳機（`test_plc_integration.py`）
- **批次守則**：產生情境 / 測試計畫在背景執行緒跑（`asyncio.to_thread`），`server/batch_state.py` 同時只允許一個；批次期間會改到模擬器的路由要掛 `reject_during_batch`（新增這類路由要加，`test_scenario_endpoints.py` 鎖住清單）；命名情境 / 測試計畫開頭用 `WindFarmSimulator.start_clean_scenario()`（清故障＋重設帶 Live 殘留 PLC 狀態的機組，乾淨的機組不動 RNG）
- **PLC 保護層守則**：警報 / 跳機只由 `PlcProtection` 依 `TurbineSpec` 設定值判定**製程值**（感測器模型之前）送出——唯一例外是注入的感測器故障（`_get_fault_physics` 的 `sensor_faults`），那支感測器的故障讀值同時給 PLC 與 SCADA，製程與其他感測器不得改變（`test_fault_threshold_reach.py` 逐位元比對）；讀值超出有效範圍只送感測器故障碼、不參與越限判定；不是 SCADA tag 的 PLC 輸入走 `evaluate(..., internal=)`（-08-c：029 比對的變頻器轉速＝轉子實際轉速——模擬的 `WGEN_GnSpd` 有扭轉暫態，不拿它比；ABB 冷卻水流量；風向標凍結 231 / 232 看的是含雜訊的 I/O 讀值，製程值在固定風向下本來就不變）；設定值與延時以手冊 Appendix D 為準（與 Appendix C 衝突時，DEC-20261023-01），PLC 的溫度（Pt100）先過 10 s 濾波、斷線判定用未濾波讀值；每小時重啟上限是**每個跳機碼**各自計數（訊號判定與物理層保護停機共用），超過送 A039、機組進 SHUTDOWN 等操作員復位——沒有全域啟動次數上限，不要再送 `restart_blocked`；PLC 設定值是 Z72 手冊常數，載入風場用 `TurbineSpec.from_farm_dict`（存檔裡的舊設定值不覆寫，`Z72_PLC_SETPOINT_FIELDS`）；`FaultEngine.alarm_codes` 是情境的預期碼（ground truth），不再有 severity 門檻；故障 tripped 期間以 `model.maintenance_lock` 擋重啟，復位不等於修好（`test_reset_keeps_fault.py`）；改規則或物理後須確認健康風場無訊號事件（`test_plc_integration.py`；12 h 長時間、多起點與 14 種子葉片同步機制見 `test_healthy_blade_sync.py`——健康誤差要遠小於手冊設定值，不靠放寬規則）
- **時間戳守則**：monitoring 一律用 `simulator/time_utils.py`——內部 `utc_now()`（不要再寫 naive 的 `datetime.now()`）、落庫 / API 字串用 `iso_utc()`（固定 `...ffffff+00:00`，SQLite 靠字串字典序比較時間）、外部傳入的字串用 `normalize_iso` / `parse_iso`（naive＝伺服器本地時間）；需要當地時刻的物理輸入（日夜 / 季節循環）用 `to_site_naive(ts, site_tz)`——風場時區（`FarmConfig.timezone`，預設 Asia/Taipei），不是伺服器時區；它把 naive 輸入視為已是風場牆鐘時間（例外於上一條）；建模擬器要帶 `site_timezone=`（broker / 資料集產生都要）
- **風況設定守則**（WMOM-20261126-03）：`wind_model.py` 不讀實際時間（不匯入 `utc_now`），它知道的時間只有引擎傳給 getter 的模擬時間；`set_override` / `set_profile` 需要「現在的自動風況」或 profile 的起點時只標記待定（`_transition_from_pending`、`_profile_start_pending`），由下一次 `get_wind_speed` 用那一步的模擬時間定下來——批次與 Live 走同一條路；取自動風況會讓天氣系統與中尺度狀態前進一步，抽樣次數不可變；設定在 API 執行緒、`get_wind_speed` 在 Live 執行緒，物件會進狀態存檔所以不放鎖——設定的一方先寫待定旗標才寫終點與開始，`get_wind_speed` 先讀開始與終點、再定起點、最後才讀起點，這個順序不要改；同樣的設定在任何實際時間產生的批次要逐位元相同（`test_wind_setting_sim_time.py`：用替換 `simulator.time_utils` 的 `datetime` 來改實際時間，新增會影響讀值的風況設定方式要加進它的 `SETTINGS`）；要產生可重產的資料只需要釘批次起點（`simulator.engine.utc_now`）；電網模型的 recovery profile 起點還在讀實際時間（WMOM-20261126-04，尚未修）
- **盲測守則**：故障根因 / 注入資訊只能進標準答案（`scenario_ground_truth`）；給外部 RAG 的事件一律以 `storage.is_observable_event` 過濾（白名單：PLC 事件與運轉狀態轉換，新事件來源預設不可觀測）；答案卷端點用永遠強制的 `require_roles`；新增故障情境要補 `FaultScenario` 的答案欄位（`test_fault_ground_truth.py` 會擋），`key_signals` 要真的偏離健康機組（`test_fault_threshold_reach.py`）
- **資料包守則**：給受測端的資料只走盲測版資料包（`/pack`，不含 `ground_truth.json`），以檔案交付、受測端不開帳號；manifest 不得帶情境名稱 / 故障排程 / 自訂文字；資料包的 tag 真實性以 `shared/data/z72_plc_tags.json`（`tools/build_z72_plc_tags.py` 從 xlsx 產生）為準；會透露劣化程度或模型參數的模擬量加進 `scenario_pack.MODEL_INTERNAL_TAGS`，key signal 不能選它們（DEC-20261021-03，測試會擋）
- **干擾守則**（-08-b，DEC-20261023-02）：風場事件（`simulator/farm_events.py`）只在批次套用，事件前的資料不得改變（電網覆寫維持同樣的亂數抽樣次數）、批次結束電網 / 風向要復原；新干擾來源的事件碼要列進 `FARM_EVENT_KINDS.event_codes`，否則標準答案會把它們歸成環境性 case；nuisance 情境用 `category="nuisance"` ＋ `nuisance_cause`（先加進詞彙的 `nuisance_causes`），不鎖機組（`mark_tripped` 不轉 tripped）；`healthy_turbines` 只看故障 case；評分的故障指標只算故障 case，干擾指標另列；風場事件排程只進情境設定與標準答案，不進資料包 / 回放 / OPC UA
- **合約守則**：資料包 / 事件 / 標準答案 / 預測格式以合約 v1 為準；同機組多 case 的評分規則與早期徵兆 case 見合約 §8 規則 7 / 8（DEC-20261026-01：歸屬不變、診斷精確率抓亂槍打鳥；出題端用 `max_severity` 壓在門檻下，範例資料包同機組兩個故障不得共用預期碼——`check_pack` 擋）；加欄位升次版本（`CONTRACT_VERSION`）、改名 / 刪欄位升主版本並更新合約文件；新增故障情境的 `component` / `category` 要先加進 `shared/data/rag_assistant_vocabulary.json`（唯一來源；kit 的 `vocabulary.json` 由 `tools/build_rag_starter_kit.py` 同步，`tests/test_rag_starter_kit.py` 會擋）；改了 tag 註冊表或資料包格式要重建範例（`python tools/build_rag_starter_kit.py`）
- **回放守則**：正式評測要伺服器 `WMOM_AUTH_ENFORCE=true`（REST / `tools/replay_runs.py` / `tools/opcua_server.py` 都擋，DEC-20261022-05）；建立正式評測時檢查整台伺服器未結束正式評測的總速率（≤ 1000 筆 / 秒）；受測端只用回放 token 連 `/ws/replay`（不開帳號、看不到情境清單）；回放訊息與盲測版資料包逐筆相同，新增訊息內容要走 `ScenarioReplay` 並維持「與資料包相同、不含答案」（`test_replay.py` 會擋）；預測的 `ts` 一律由伺服器蓋，不接受受測端給的時間；正式評測與練習回放不要開在同一個情境（建回放時預設擋下，`allow_overlap` 才放行）；正式評測的速度受「機組數 × 速度 ÷ 取樣週期 ≤ 1000 筆 / 秒」限制
- **OPC UA 守則**：節點 ID＝真實 OPC DA item ID（`opc_data_reader.py` 的 `BASE_TAGS` 每個都要讀得到，`test_opcua_server.py` 會擋）；讀值欄位與盲測版資料包同一組、值逐位元相同，不加答案或模型內部量；事件碼陣列（`ActiveEventLists`）即時模擬與回放同一套規則，且每一步等於 `PlcProtection.active_codes()`（操作員復位當下到下一步之間除外；解除鎖存一律送 `trip_cleared`，不要在復位時清清單）；只收匿名、關閉 asyncua 內建 admin、唯讀（`test_opcua_server.py` 會擋），只開在教室 / 實驗室網路，即時模擬的 OPC UA 預設只聽 `127.0.0.1`、批次期間不發布；正式評測在 server 建好節點並開始監聽後才開播（`tools/opcua_server.py` 的 `load_run` → `start` → `start_clock`），練習回放的 WS `stream=false` 以 OPC UA 記下的起點對時
- **對外 API 守則**（WMOM-20261125-02，DEC-20261126-01）：`/api/ext/v1` 只收 API 金鑰（`X-API-Key`，`modules/auth/api_keys.py`）、一律強制、只有 `GET`——金鑰不是角色，不要讓 `get_current_actor` / `require_role` 認它，也不要讓對外端點改收 JWT；新增對外端點掛在 `external.router` 上（router 層的 dependency 會帶到金鑰），並加進 `test_external_api.py` 的 `_ENDPOINTS`（測試鎖住清單與方法）；給出去的東西與盲測版資料包同一套——讀值欄位＝`pack_columns()`、事件逐筆過 `is_observable_event` 再 `pack_event`、不給風場名稱 / 情境名稱 / 風況設定等自訂文字；只取 Live（`storage.live_readings` / `live_events` 排除情境 session），最新讀值取自 `broker.latest_stored_readings()`（最近一次寫進 storage 的那一批），不讀 simulator 記憶體；目前成立的警報在即時模擬沒跑或批次期間不給；游標依寫入順序（id），不要改成依時間；10 分鐘統計的窗「收齊了沒」看 `storage.last_live_reading_timestamp` / broker 記下的最新讀值時間，不看實際時間；`/status`、`/farm` 的欄位是白名單（測試鎖住），不回報管理端在做什麼；端點與參數的版本是 `EXTERNAL_API_VERSION`，資料格式跟著 `CONTRACT_VERSION`，改了要更新 `docs/integration/external_api_v1.md`；盲測要伺服器開 `WMOM_AUTH_ENFORCE=true`（`/status` 的 `other_endpoints_require_login` 回報）
- **Live 時鐘與續跑守則**（WMOM-20261125-03-a / -b，DEC-20261126-02）：即時模擬只有一個時間——`WindFarmSimulator.sim_clock`，每步推進剛好一個 `time_step`、只往前走；Live 迴圈裡不要再用 `utc_now()` 當讀值或事件的時間，Live 的事件走 `DataBroker.record_event`（沒給時間時用 `live_clock()`）；寫進 storage 依讀值的模擬時間對齊 10 秒時段（`_write_slot`），不要改回依實際時間節流；callback 每一步都會被呼叫（加速與補跑時也是），裡面不要做依實際時間計數的事；會隨時間演變的新狀態要掛在 `_CHECKPOINT_FIELDS` 列的物件底下、而且要能 pickle（不要放執行緒、鎖、lambda、開著的檔案）——`test_live_resume.py` 檢查還原後接著跑與沒有中斷的那一份逐位元相同；存檔格式改了升 `CHECKPOINT_VERSION`；模擬器程式一改，舊存檔就不還原（程式指紋），風場狀態重來、`live_epoch` 改變；會重建子模型的操作（`update_spec`）不要對還原出來的機組無條件呼叫；批次端點一律包在 `pause_live_for_batch` 裡（它在批次前後保存 / 還原 Live 的狀態）；存檔與開機自動啟動預設關（`WMOM_LIVE_RESUME`、`WMOM_AUTOSTART_SOURCE`），測試不要依賴預設路徑的存檔；Live 執行緒送出的事件，內容與時間都要只由模擬狀態決定（事件參照用 `_live_stamp()`，不要用 `iso_utc()` 的現在時刻）——伺服器被強制關閉後重跑同一步要得到同一筆，去重才對得上（`storage.live_event_exists`）；快照的視窗用 `_snapshot_clock()`；批次端點要回報批次結束時的模擬器狀態，就在 `pause_live_for_batch` 的區塊裡面取
- **分層儲存守則**（WMOM-20261125-03-c，DEC-20261126-03）：Live 的原始讀值分兩層——最近幾天在 SQLite（`turbine_data`），較舊的在每日 Parquet 檔（`server/live_archive.py`，風場 DB 旁邊的 `live_archive/`）。要讀 Live 的歷史用 `broker.live_history.readings(...)`，不要直接查 `storage.live_readings`（只有最近幾天）；兩層給的值都經過 `server/plc_types.py` 的同一套轉換（REAL＝float32、整數取整、超出型別範圍＝缺值），新增讀取或寫入路徑時不要讓兩層的值不同；`turbine_data` 只有 `(turbine_id, timestamp)` 與 `(session_id)` 索引，時間範圍的查詢要帶機組（`live_span`、`delete_live_readings_before` 的寫法），不帶機組會掃整張表（14 台一天約 0.5 GB）；刪 Live 讀值只走 `run_retention`（有鎖，同一時間只有一方）：先歸檔（`sync`）、再記界線（`mark_hot_from`）、最後才刪，而且每一天只刪 id 不大於該日檔最大 id 的列（`delete_ranges` → `delete_archived_live_readings`）；歸檔的索引讀不出來時丟 `ArchiveIndexError`，不要當成「沒有歸檔」（寫的一方會把舊日檔丟掉、讀的一方會漏掉整段）——`sync` 從日檔重建，對外 API 回 503；保留期看資料時鐘（即時模擬在跑時是模擬時鐘，否則是最近寫入的 Live 讀值時間），不看實際時間；歸檔留全部 tag 與 `session_id`，給出去時由呼叫端挑欄位（對外仍只給 `pack_columns()`）；只歸檔 Live，情境 session 的讀值不進歸檔；Live 的歷史在時間上不往回（`_continue_after_stored_data`）——新增會寫 Live 讀值的路徑時，時間早於 `hot_from` 的列不會進歸檔
- **運維閉環守則**（WMOM-20261125-04，DEC-20261126-04）：即時風場和工單的連動都在 `server/om_loop.py`（`OmLoop`）；workflow 不 import monitoring——要在工單建立 / 狀態改變時做事，用 `modules/workflow/hooks.py` 登記 listener（寫進資料庫之後才通知，listener 出錯不影響工單）；自動開的工單只寫看得到的東西（事件碼、PLC 文字、訊號值與設定值），不寫故障情境——它之後會給外部；修了哪些故障只記在 `source="workflow"` 的事件，這個來源不可加進可觀測事件的白名單；完工修什麼由 `FaultScenario.alarm_codes` 決定（帶警報碼的工單只修預期會送出那個碼的故障），新增故障情境時預期碼要列全；「復位不等於修好」不變，`/api/faults/*` 是出題用的後門；閉環只作用在即時模擬——批次期間的工單動作先記在 `_pending`、批次結束後才套用，重跑段不開單；可用率只由 `availability_hourly`（運轉狀態紀錄）計算，分類用到 `maintenance_lock` 這個內部狀態，所以 `/api/operations/availability` 不對外；伺服器預設開（`WMOM_OM_LOOP`），直接建立的 broker 預設關、沒開就不載入工單模組（熱路徑用 `_om_loop_if_enabled()`）；舊的 `/api/maintenance/*` 工單表是舊介面，新功能不要接
- **下次工作**：EPIC-SF 第 4 項 `WMOM-20261125-05`（出發前準備卡），接著第 5 項 `WMOM-20261125-06`（機率式故障產生器與模擬維修班）。第 1、2、3 項已完成。另有約半天的小修 `WMOM-20261126-04`（電網 recovery profile 的起點讀實際時間，`WMOM-20261126-03` 的同類問題）。順序與各 issue 規格見 [`ISSUES.md`](ISSUES.md) 的「2026-11-25 session 新增 issue」。EPIC-DS 全部 phase 已完成（-08 四個子項 done）
- **測試**：backend 新增 26 項（風況設定只用模擬時間，WMOM-20261126-03）與 43 項（運維閉環；其中 6 個故障情境在測試的風況下不會鎖住機組、自動略過）；本機 2472 passed / 7 skipped / 1 xfailed（2026-11-26，本機沒裝 chromadb / sentence-transformers，knowledge 的部分測試整檔略過；完整數字以 CI 為準，前次 CI 是 2240 passed / 7 skipped / 1 xfailed）；frontend vitest 1513 passed（2026-10-26，這次沒動前端）。以各 module `tests/` 為準

## 11. v0.5 → v0.8.1 重大轉變（必知）

2026-05-02 經過 1 天 5 輪規劃迭代，最終決定：

- ❌ **廢棄**：v0.5 的「windMindOM 整合容器」「Plugin SDK」「4 類 Turbine Adapter ABC」「Workflow Hub 獨立 service」等過度工程
- ✅ **採納**：windMindOM = digiWT 商業化升級版，monolithic 5 modules，外部介接走 API/artifact

詳見 [`docs/product/decision_log.md`](docs/product/decision_log.md) DEC-20260502-06。

## 12. 不要做的事

- **不要在 master/main 直接做 risky 工作**（建分支再合）
- **不要修改其他 7 個來源 repo 的 master 分支**（windMindOM 是獨立 fork）
- **不要 fork 其他 repo 的程式碼進 windMindOM**（用 git submodule / pip install / npm link）
- **不要創建沒列在 ISSUES.md 的工作**（除非開新 issue + 寫進 work-log）
- **不要跳過 work-log**（即使是「只討論不寫 code」的 session 也要有紀錄）
- **不要在 monitoring 層動物理模型而不參考 [`docs/legacy/digiwt_project_notes.md`](docs/legacy/digiwt_project_notes.md)**（避免破壞既有 18/21 quality check 通過的物理一致性）
- **不要動 `geminiService.ts`** ← 但這是 RAG_Ultimate 的事，與本 repo 無關（提醒避免混淆）

## 13. Daily Routine

完整 routine 在 [`docs/routines/daily-workflow.md`](docs/routines/daily-workflow.md)（已於 M1 從 v0.5 搬入）。
精簡版 8 phase：Preflight → Claim → Branch+Log → Implement → Verify → Review → Wrap-up → Commit。

哲學：**一日一項重要工作**。不貪多。

## 14. Claude Code 專屬

如果在 Claude Code 內工作（推薦）：

- 啟動：`cd D:\Project_CodingSimulation\researchTopic\windMindOM && claude`
- Slash commands（`.claude/commands/`，已就緒）：`/daily-start`、`/claim-issue {ID}`、`/review`、`/daily-wrapup`
- Sub-agents（`.claude/agents/`，已就緒）：`code-reviewer`（Python async + 風電領域 + FastAPI 專長）

範本在 `docs/claude-code-templates/`（已就緒）。

## 15. 小提醒

- **參考機型定 Z72** — 設計時先以 Z72 為 reference；EPIC-DS 資料源只支援 Z72（手冊與真實警報清單都是 Z72）
- **Simulator-first** — 任何功能都要能在純 simulator 模式下 demo（無實場是 sales killer feature）
- **RAG 走「研究端策略檔 + 預計算向量檔」** — windMindOM 內只負責載入 + query，不重新 embed
- **z72_etech 取材選 A** — dev team 自己讀程式產出 design notes（M3-M4 排定）
- **windAILab 是另一公司業務** — AI 故障診斷透過 API 介接，不要嘗試把它整進 windMindOM 內部
- **現場工程師也是 user** — 警報 RAG 與 mobile UI 是 PMF 關鍵，不是 nice-to-have
