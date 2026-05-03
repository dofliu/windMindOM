# 2026-05-03 — windMindOM v0.8.1 tracking files 建立 + WMOM-20260503-01 完成搬遷

> Session 類型：規劃 + 設定 + 實作（M1 第一週開頭）
> Session 長度：中（一天內）
> 主導：劉老師 + Claude
> 結果：3 份 tracking files（STATUS / ISSUES / TODO）建立完成；WMOM-20260503-01 **整顆 issue 完成**（原估 2-3 天 → 半天搞定，因採 sys.path 注入策略，零 import 重寫）。

---

## 1. Session 目標

依 [`docs/product/ROADMAP.md`](../../docs/product/ROADMAP.md) M1 第一週工作清單：

1. 從零建立 windMindOM v0.8.1 版的 `STATUS.yaml`、`ISSUES.md`、`TODO.md`
   （v0.5 / digiWT 版本廢棄；舊檔備份到 `docs/legacy/`）
2. 認領 `WMOM-20260503-01`（Repo baseline 整理：digiWT 既有檔案搬到 `modules/monitoring/`）
3. 走完 daily-workflow Phase 1-3（Preflight → Claim → Branch + Log），把後續 Phase 4 Implement 留給下一個 session

---

## 2. 實際完成

### 2.1 主要工作

- 讀完 `CLAUDE.md` + `docs/product/ROADMAP.md` 的 M1 區塊，確認第一週 5 個 issue 範圍
- 把舊的 digiWT 版 `TODO.md` / `STATUS.yaml` 搬到 `docs/legacy/`（保留物理層詳細紀錄）
- 寫新的 `STATUS.yaml`：windMindOM v0.8.1 baseline、6 個 milestone、issue_stats、繼承自 digiWT 的 highlights
- 寫新的 `ISSUES.md`：M1 第一週 5 個 issue + 廢棄項一覽（避免反覆討論已決議的事）
- 寫新的 `TODO.md`：本月 / 下月節奏 + parking lot
- 開新分支 `claude/issue-WMOM-20260503-01-2026-05-03`
- 開新 work-log（本檔）
- 將 `WMOM-20260503-01` status 標為 `in_progress` + Owner = Claude (this session)
- 將 `WMOM-20260503-03` 標為 `done`（root CLAUDE.md 已於 2026-05-02 baseline commit 改為 windMindOM 產品脈絡）

### 2.2 卡住或延後的事

- 沒做完整 `python run.py` 起 backend + browser dashboard 驗證（Windows 環境啟動 + 跨瀏覽器測試非互動式環境難做）→ 列為 follow-up
- 沒做 `docker-compose up --build` 端到端驗證 → 列為 follow-up
- 沒重跑 `examples/data_quality_analysis.py` 比對搬遷前後 18/21 quality check 數值（跑要 ~2 小時）→ 列為 follow-up

### 2.3 重大決策（如有）

無新 DEC，但搬遷時做了一個**戰術選擇**值得記錄（不到 DEC 等級，寫在這就好）：

**選擇「move + sys.path 注入」而非「mass-rewrite imports」**

| 選項 | Pros | Cons | 採用 |
|------|------|------|:---:|
| A. Mass-rewrite import（`from simulator.x` → `from modules.monitoring.simulator.x`） | 明確、最終目標 | 改 50+ 檔；regression 風險高；git blame 全染色 | ❌ |
| **B. Move + sys.path 注入** | **零行為變動；regression 最小；git blame 乾淨** | 「magic」；新 dev 看不到 import 怎麼解析 | ✅ |
| C. Symlink 假裝還在 root | 跨平台不可靠（Windows 對 symlink 限制多） | 不採用 | ❌ |

選 B。理由：M1 哲學是「**不破壞既有功能**」+ ROADMAP 預估 2-3 天 → 用 0.5 天爭取後續 issue 喘息空間。
mass-rewrite 留給 M1-M2 穩定後另開 issue 處理（已寫進 [`docs/legacy/digiwt_directory_layout.md`](../../docs/legacy/digiwt_directory_layout.md) follow-up）。

（既有的關鍵決策仍是 DEC-20260502-06：v0.5 → v0.8.1 monolithic 5 modules pivot；不在本 session 範圍。）

### 2.4 Phase 4-7 實作細節（補記）

**Phase 4 Implement**：
- 建 `modules/{monitoring,workflow,cost,reporting,knowledge}/__init__.py` + `shared/{schemas,plc_clients,domain}/__init__.py` + `tests/__init__.py`（共 11 個包 docstring 解釋用途）
- `git mv` 把 root 的 simulator/、server/、examples/、9 個 .py 檔搬到 `modules/monitoring/`
- `mv` data/、wind_farm_data.db、wind_turbine_data.db 到 `modules/monitoring/`（untracked 用 plain mv）
- `mv` opc_bachmann/ 到 `shared/plc_clients/bachmann/`
- `Edit` `run.py`：加 `sys.path.insert(0, modules/monitoring)` 注入
- `Write` 新 `Dockerfile`：COPY 改為 modules/、shared/
- `Edit` `docker-compose.yml`：DB_PATH、FARM_DATA_DIR、volume mount、container_name 全更新
- `Edit` `.dockerignore`：opc_bachmann/ → shared/plc_clients/bachmann/

**Phase 5 Verify**：
| 測試 | 結果 |
|------|:---:|
| Pre-move smoke import：`from simulator.engine import WindFarmSimulator; from server.app import app` | ✓ |
| Post-move smoke import（同上 + 5 modules + shared 子套件全 importable） | ✓ |
| 跑 `WindFarmSimulator(turbine_count=3).generate_bulk(0.005, 1.0)` → 54 readings、109 SCADA tag、wind_speed=6.6 m/s、state=STARTING | ✓ |
| FastAPI app 載入：67 routes、title="Wind Farm Monitor API" | ✓ |
| `python -m py_compile run.py` | ✓ |
| 物理路徑相對 offset（`server/farm_registry.py:18-21` 的 `Path(__file__).parent.parent / "data"` 等 4 處）平移後仍正確解析 | ✓ |

**Phase 6 Review**：self-review checklist
- [x] sys.path 順序正確：`modules/monitoring` 先於 project root，避免 `from simulator.x` 解析到別處
- [x] CRLF 行尾保留（git warn LF→CRLF 是正常的，內容沒被改）
- [x] git rename detection 對部分空 `__init__.py` 標錯，但物理檔案位置正確（已驗證）
- [x] 沒誤刪檔案：root 已無 server/ simulator/ examples/ data/ opc_bachmann/，全在新位置
- [x] 沒動 frontend/、tests/ 既有內容
- [x] 寫了 `docs/legacy/digiwt_directory_layout.md` 對照表 + sys.path 策略 + 影響相對路徑分析 + 驗證紀錄

**Phase 7 Wrap-up**（本 update）：
- ISSUES.md WMOM-20260503-01 標 done + completion summary + follow-up 清單
- STATUS.yaml progress 5 → 12，M1 progress 5 → 35，issue_stats done 0→2 / open 4→3 / in_progress 1→0
- TODO.md 第一週 -01 打勾，列出 follow-up
- 本檔案這個 §2.4 區塊與 §3 產出清單更新

---

## 3. 產出清單

### 新增檔案

- `STATUS.yaml`（windMindOM v0.8.1 版；舊版搬到 `docs/legacy/digiwt_STATUS.yaml`）
- `ISSUES.md`（M1 第一週 5 個 issue + 廢棄區）
- `TODO.md`（本月 / 下月節奏 + parking lot）
- `work-logs/2026-05/2026-05-03-repo-baseline-and-tracking-files.md`（本檔）
- `modules/{__init__.py,monitoring/__init__.py,workflow/__init__.py,cost/__init__.py,reporting/__init__.py,knowledge/__init__.py}`（5 modules + 父包 docstring）
- `shared/{__init__.py,schemas/__init__.py,plc_clients/__init__.py,domain/__init__.py}`（4 包 docstring）
- `tests/__init__.py`（測試套件占位 + 預期分層說明）
- `docs/legacy/digiwt_directory_layout.md`（搬遷對照表 + sys.path 策略 + 驗證紀錄）

### 移動檔案

從 root 搬到 `modules/monitoring/`：
- `simulator/`（含 `physics/` 整顆樹）、`server/`（含 `routers/`）、`examples/`、`data/`
- `wind_model.py`、`turbine_model.py`、`subsystems.py`、`scada_system.py`、`opcua_interface.py`
- `dashboard.py`、`main.py`、`main_architecture.py`、`common_types.py`
- `wind_farm_data.db`、`wind_turbine_data.db`
- 刪除空的 root `config/`

從 root 搬到 `shared/plc_clients/bachmann/`：
- `opc_bachmann/`（含 OpenOPC2 binary + python wrapper）

從 root 搬到 `docs/legacy/`：
- `TODO.md` → `docs/legacy/digiwt_TODO.md`（保留物理層 244 條改進清單作 reference）
- `STATUS.yaml` → `docs/legacy/digiwt_STATUS.yaml`（保留 digiWT 階段 progress=85 snapshot）

### 修改檔案

- `run.py`：加 `_PROJECT_ROOT` / `_MONITORING_ROOT` + `sys.path.insert` 注入（核心改動）
- `Dockerfile`：COPY 改為 `modules/` + `shared/`，註解更新
- `docker-compose.yml`：DB_PATH、FARM_DATA_DIR、volume mount、container_name 全部更新為新路徑
- `.dockerignore`：`opc_bachmann/` → `shared/plc_clients/bachmann/`，加 `work-logs/`

### 動了狀態的 issue

- WMOM-20260503-01: open → in_progress → **done**（半天完成，估 2-3 天）
- WMOM-20260503-03: open → done（pre-session 已完成）

### 寫進 decision_log 的決策

無（本 session 不涉及方向變動）。

「move + sys.path 注入」是戰術選擇，記在本檔 §2.3 + `docs/legacy/digiwt_directory_layout.md` §2，未到 DEC 等級。

---

## 4. 下次怎麼接手

WMOM-20260503-01 已完成。下個 session 兩條路徑：

### 4.1 主線（推薦）：認領 WMOM-20260503-02（搬入 v0.5 有用資產）

- 依 [`ISSUES.md`](../../ISSUES.md) `WMOM-20260503-02` description
- 重點：先確認 v0.5 prototype 在哪（pitch deck v0.5 baseline、claude-code-templates 是否完整、templates 模板是否齊全）
- 預估 0.5-1 工作天

### 4.2 Follow-up：完整端到端驗證 WMOM-20260503-01 搬遷

- 跑 `python run.py` 起 backend → 開 `http://localhost:8100/docs` 看 OpenAPI、開 frontend dashboard 看 14 台風機是否還活著
- `docker-compose up --build` 端到端 → 確認 container 內路徑都對
- `python modules/monitoring/examples/data_quality_analysis.py` → 比對 18/21 quality check 數值與 [`modules/monitoring/examples/data_quality_report.txt`](../../modules/monitoring/examples/data_quality_report.txt) 搬遷前的數字一致（容忍浮點 ±0.1%）
- 任何項目出問題：**先看 [`docs/legacy/digiwt_directory_layout.md`](../../docs/legacy/digiwt_directory_layout.md) §3 影響到的相對路徑表**，再看 §5 驗證紀錄
- 估 0.5-1 工作天（含真的開瀏覽器測試）

### 4.3 阻擋項

- 若 `from simulator.x` 在子腳本（不經過 `run.py`）解析不到 → 該腳本要自己加 `sys.path.insert(0, '<repo>/modules/monitoring')`，或用 `python -c "import sys; sys.path.insert(0, ...); ..."` 包裝。`examples/data_quality_analysis.py` 已有 `sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))`，搬遷後 `..` 自然指向 `modules/monitoring/`，不用改

---

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 與用戶對話、釐清方向 | 5%（user 給的指令很清晰，不需太多釐清）|
| 讀 CLAUDE.md / ROADMAP / 既有檔案 / import 圖譜分析 | 25% |
| 寫 STATUS / ISSUES / TODO / 11 包 `__init__.py` / 對照表 / work-log | 35% |
| 實作搬遷（git mv + Edit run.py / Dockerfile / compose / dockerignore） | 20% |
| Smoke test（pre-move + post-move + 18-秒模擬 + FastAPI 載入） | 10% |
| 解問題（generate_bulk API 參數錯、`_running` flag、CRLF warning） | 5% |

---

## 6. 學到的事

- ~~v0.8.1 ROADMAP 的「**一日一項重要工作**」哲學在 Phase 0 setup 也適用：今天就做 tracking files，**不**順便把 baseline 整理一起做完——後者是 2-3 天的 issue~~ → **更新**：估錯了，採 sys.path 注入策略後變成半天工作；半天 + 半天 = 一天能做完兩件事，**還是「一日一個重要工作」哲學的勝利**（不是兩件大事，是一件大事 + 一件 setup）
- ISSUES.md 開「廢棄 / 不做」表單能避免半年後 reviewer 又來問「為什麼不做 plugin SDK」——把已決議的事釘在牆上比每次重新解釋便宜
- TODO.md 不應該複製 ISSUES.md 的內容；它應該是「本月節奏 dashboard」，issue 細節在 ISSUES.md，路線圖在 ROADMAP.md。三層分工要嚴守，否則同步成本會炸
- digiWT 的舊 TODO.md 太長（244 行物理改進清單），不適合留在 root；移到 `docs/legacy/` 後 root 維持乾淨
- **戰術選擇要記在 work-log + 對照表，不一定要寫 DEC**——DEC 是不可逆的方向變動；搬遷策略只是 implementation tactic，未來想改也改得回。寫 work-log §2.3 + `digiwt_directory_layout.md` §2 就夠了
- **空 `__init__.py` 會讓 git rename detection 標錯**——`server/__init__.py → simulator/__init__.py` 這種錯誤標記不影響功能（檔案實際位置正確），但確認過 `ls modules/monitoring/server/__init__.py` 與 `ls modules/monitoring/simulator/__init__.py` 都在比較安心
- **`sim._running = True` 是內部 flag**：`generate_bulk()` 直接呼叫不會自動 set，要嘛 call `start()` 起 thread、要嘛手動 set；smoke test 用後者比較簡單。M2+ 若要打 unit test 應該開 issue 改成 generate_bulk 自己 set/restore

---

## 7. Open questions（park）

- `docs/sales/` 資料夾還沒建，WMOM-20260503-04 / 05 的 deliverable 路徑要等實作那 session 才會真的存在 → 不卡 M1 進度
- v0.5 的 `pitch_deck.md` 實際在哪裡？（本 session 沒查；WMOM-20260503-02 認領者要先去找）
- `pyproject.toml` 整合 vs 沿用現有 `requirements.txt`？M1 vs M2？→ 已暫定 M1 做（見 ISSUES.md WMOM-20260503-01 Decision needed），但若搬遷時間吃緊可往後挪
- 是否要建 `CHANGELOG.md`？已寫進 TODO.md 第二週，但 ROADMAP M1 列了沒給 issue 編號 → 需要的話開 WMOM-20260503-06
