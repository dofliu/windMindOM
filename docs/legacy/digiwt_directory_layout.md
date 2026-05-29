# digiWT → windMindOM 目錄搬遷對照表

> Issue：[`WMOM-20260503-01`](../../ISSUES.md)
> 執行日期：2026-05-03
> 執行 commit：claude/issue-WMOM-20260503-01-2026-05-03 分支
> 哲學：**move + sys.path 注入，零行為變動**。內部既有的 `from simulator.x` /
> `from server.x` import 不大規模重寫，由 [`run.py`](../../run.py) 在啟動時把
> `modules/monitoring/` 注入 sys.path 最前面解決。

---

## 1. 對照表

### 1.1 monitoring → `modules/monitoring/`

| 原位置 | 新位置 | 備註 |
|--------|--------|------|
| `simulator/` | `modules/monitoring/simulator/` | 整顆樹（含 `physics/`） |
| `server/` | `modules/monitoring/server/` | 整顆樹（含 `routers/`） |
| `examples/` | `modules/monitoring/examples/` | `data_quality_analysis.py` 等；本身已用 `sys.path.insert(0, '..')`，搬完後 `..` 解析到 `modules/monitoring/` 仍可正確 import `simulator.engine` |
| `wind_model.py` | `modules/monitoring/wind_model.py` | |
| `turbine_model.py` | `modules/monitoring/turbine_model.py` | |
| `subsystems.py` | `modules/monitoring/subsystems.py` | |
| `scada_system.py` | `modules/monitoring/scada_system.py` | |
| `opcua_interface.py` | `modules/monitoring/opcua_interface.py` | |
| `dashboard.py` | `modules/monitoring/dashboard.py` | 標準離線 debug 工具，DB 路徑用 CWD-relative |
| `main.py` | `modules/monitoring/main.py` | digiWT 早期 entry point；現在生產 entry point 是 root `run.py` |
| `main_architecture.py` | `modules/monitoring/main_architecture.py` | |
| `common_types.py` | `modules/monitoring/common_types.py` | |
| `data/` | `modules/monitoring/data/` | farm registry 全部 SQLite + JSON config（`farms.db`、`farms/{id}/...`）。維持 `server/farm_registry.py:18-23` 的相對路徑 `Path(__file__).parent.parent / "data"` 解析正確 |
| `wind_farm_data.db`（root） | `modules/monitoring/wind_farm_data.db` | legacy DB；`server/app.py:26` `migrate_legacy_db()` 啟動時會偵測並轉入 farm registry |
| `wind_turbine_data.db`（root） | `modules/monitoring/wind_turbine_data.db` | 早期 SCADA history DB；`scada_system.py:14` 預設值為 CWD-relative |
| `config/`（空） | （刪除） | 既有為空殼；保留新的 `modules/monitoring/config/` 等之後有需要再建 |

### 1.2 PLC client → `shared/plc_clients/bachmann/`

| 原位置 | 新位置 | 備註 |
|--------|--------|------|
| `opc_bachmann/` | `shared/plc_clients/bachmann/` | Bachmann Z72 OPC DA client（含 OpenOPC2 binary、`opc_client.py`、`opc_data_reader.py` 等）。為什麼放 `shared/`：未來 cost / workflow / reporting / knowledge 都可能直接拉 PLC 資料，不只 monitoring 用 |

### 1.3 沒搬的東西

| Item | 為什麼留在 root |
|------|----------------|
| `run.py` | Entry point。改寫成在啟動時把 `modules/monitoring/` 注入 sys.path |
| `Dockerfile`、`docker-compose.yml` | Build / orchestration 設定。改寫 COPY 與環境變數路徑 |
| `requirements.txt` | Python deps。M1 後續 issue 會考慮整合進 `pyproject.toml` |
| `frontend/` | 獨立子專案，自己有 Dockerfile |
| `templates/` | work-log / issue / decision 模板 |
| `work-logs/` | session 紀錄；不在 image 內 |
| `docs/` | 文件 |
| `tests/`（新建） | pytest 入口 |
| 所有 tracking files | `STATUS.yaml`、`ISSUES.md`、`TODO.md`、`CLAUDE.md`、`README.md`、`AGENTS.md`、`GEMINI.md`、`idea.md`、`project.md` |
| `package-lock.json` | 看似 stray；之後盤點是否屬於 frontend |
| `z72SCADA_New/` | 既有未整理區，本 issue 不動 |

> ⚠ **2026-05-29 更新（WMOM-20260529-02）**：上表為 migration 當時快照。其後文件整理已：
> 重寫 `README.md`、`AGENTS.md`/`GEMINI.md` 改薄 pointer、刪除 `idea.md`/`project.md`/root `package-lock.json` 空殼、
> 移除 `z72SCADA_New/`（外部專案 dump）。本表保留作歷史紀錄。

---

## 2. sys.path 注入策略（核心）

[`run.py`](../../run.py) 啟動時做兩件事：

```python
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_MONITORING_ROOT = os.path.join(_PROJECT_ROOT, "modules", "monitoring")

sys.path.insert(0, _PROJECT_ROOT)       # 讓 `from modules.x` / `from shared.x` 解析
sys.path.insert(0, _MONITORING_ROOT)    # 讓 `from simulator.x` / `from server.x` legacy import 解析
```

順序：`_MONITORING_ROOT` 在最前面，所以遇到 `from simulator.engine` 會先在 `modules/monitoring/simulator/engine.py` 找到。

### 為什麼選這個策略

| 選項 | Pros | Cons | 採用 |
|------|------|------|:---:|
| A. Mass-rewrite import（`from simulator.x` → `from modules.monitoring.simulator.x`） | 明確、最終目標 | 改 50+ 檔；regression 風險高；git blame 全染色 | ❌ |
| **B. Move + sys.path 注入** | **零行為變動；regression 最小；git blame 乾淨** | 「magic」；新 dev 看不到 import 怎麼解析 | ✅ |
| C. Symlink 假裝還在 root | 跨平台不可靠（Windows 對 symlink 限制多） | 不採用 | ❌ |

選 B。長期重構（另開 issue）會把 import 改為明確 `modules.monitoring.*` 形式，但目前優先「**M1 不破壞既有功能**」。

---

## 3. 影響到的相對路徑（關鍵 sanity）

下面這些相對路徑寫法在搬遷後仍正確解析，**不需修改**：

| 檔案:行 | 寫法 | 搬遷前解析 | 搬遷後解析 |
|---------|------|-----------|-----------|
| [`server/farm_registry.py:18-21`](../../modules/monitoring/server/farm_registry.py) | `Path(__file__).parent.parent / "data"` | `<root>/data/` | `modules/monitoring/data/` ✓ |
| [`server/storage.py:11`](../../modules/monitoring/server/storage.py) | `Path(__file__).parent.parent / "wind_farm_data.db"` | `<root>/wind_farm_data.db` | `modules/monitoring/wind_farm_data.db` ✓ |
| [`server/app.py:26`](../../modules/monitoring/server/app.py) | `Path(__file__).parent.parent / "wind_farm_data.db"` | `<root>/wind_farm_data.db` | `modules/monitoring/wind_farm_data.db` ✓ |
| [`examples/data_quality_analysis.py:14`](../../modules/monitoring/examples/data_quality_analysis.py) | `sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))` | `<root>/` | `modules/monitoring/` ✓ |

→ 因為 monitoring 整套是「等比例平移」（root → `modules/monitoring/`），所有 `__file__` 起算的相對 offset 都自然平移，不需改 code。

---

## 4. Docker 路徑變動

### Dockerfile

```diff
- COPY run.py .
- COPY wind_model.py .
- COPY common_types.py .
- COPY server/ server/
- COPY simulator/ simulator/
+ COPY run.py .
+ COPY modules/ modules/
+ COPY shared/ shared/
```

### docker-compose.yml

```diff
- container_name: digiwindfarm-backend
+ container_name: windmindom-backend
- - DB_PATH=/app/data/wind_farm_data.db
+ - DB_PATH=/app/modules/monitoring/wind_farm_data.db
+ - FARM_DATA_DIR=/app/modules/monitoring/data
- - db-data:/app/data
+ - db-data:/app/modules/monitoring/data
- container_name: digiwindfarm-frontend
+ container_name: windmindom-frontend
```

### .dockerignore

```diff
- opc_bachmann/
+ shared/plc_clients/bachmann/
+ work-logs/
```

`shared/plc_clients/bachmann/` 內含 OpenOPC2 二進位 + DLL（Windows-only），Linux container 用不到，繼續排除。

---

## 5. 驗證紀錄（2026-05-03）

| 階段 | 測試 | 結果 |
|------|------|:---:|
| Pre-move | `from simulator.engine import WindFarmSimulator; from server.app import app` | ✓ OK |
| Post-move | 同上（透過 `run.py` 注入的 sys.path） | ✓ OK |
| Post-move | 5 modules + shared 4 子套件全部 importable | ✓ OK |
| Post-move | `WindFarmSimulator(turbine_count=3).generate_bulk(0.005, 1.0)` → 54 readings | ✓ OK |
| Post-move | 109 SCADA tags / turbine 仍輸出 | ✓ OK |
| Post-move | `server.app:app` FastAPI app 載入，67 routes | ✓ OK |
| Post-move | `python -m py_compile run.py` | ✓ OK |

未驗證（留給後續 session）：
- 完整 `python run.py` 起 backend + 開 browser 看 dashboard
- `docker-compose up --build` 真的 build 起來
- `python modules/monitoring/examples/data_quality_analysis.py` 重新跑 18/21 quality check（確認所有物理量值與搬遷前一致）

---

## 6. 已知 follow-up

1. **Mass-rewrite imports** to fully qualified form — 等 M1-M2 穩定後另開 issue
2. **`pyproject.toml` 整合** — 在 ISSUES.md `WMOM-20260503-01` Decision needed 列為「M1 vs M2」未決；目前先沿用 `requirements.txt`
3. **Frontend 內如有寫死 `/app/data/...` 等 absolute container path** — 未盤點；不過 frontend 走 HTTP API，理論上不依賴後端目錄結構
4. **`scada_system.py:14` / `dashboard.py:13` 的 DB 預設路徑用 CWD-relative literal** — 跑 from `modules/monitoring/` 時相容，跑 from root 時會在 root 建空 DB；M2 時統一走 env var
5. **`modules/monitoring/main.py`、`modules/monitoring/main_architecture.py`** — digiWT 早期 entry，可能是 dead code；M1 Week 2 盤點是否可刪
