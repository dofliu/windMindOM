# 2026-10-06 — WMOM-20260505-26-a：SCADA Service state tag（`WSRV_ManualOverride` / `WSRV_LockoutState`）

## Preflight

- main @ `7799569`，無 open PR（GitHub MCP 可用）。
- backend 7 路徑：1295 passed / 7 skipped / 1 xfailed（= baseline）。
- 本 session 前半為 cron 觸發，判定無乾淨 autonomous 工作；隨後**劉老師在 session 內回覆**
  09-29 handoff 的三個問題，解鎖本次工作。

## 劉老師 2026-10-06 回覆（決策紀錄）

1. **HTTPS 部署**：「沒關係，我在本機測試就好」→ 移出 autonomous 佇列。
2. **`-25` Part B/C、`-26-a`**：「可以採納」→ 兩者皆核准。本次做 `-26-a`（範圍最小、無歧義）；
   `-25` Part B/C 留給下個 session。
3. **docker 環境**：「沒辦法提供」→ `WMOM-20260509-F6` 維持卡住。

## 實作

- `scada_registry.py`：新增 `WSRV_ManualOverride`、`WSRV_LockoutState`（`SINT16`，範圍 0/1）。
- `turbine_physics.py::step()`：`operator_stop` → ManualOverride；`tur_state == 7` → LockoutState。
  兩者都加進 `_integer_tags`，避免 sensor model 加雜訊。
- `export.py`：CSV 匯出欄位加入兩個 tag。`docs/API_GUIDE.md`：tag 數 109→111，WSRV 從 1 改成 3。
- 確認**不需要**改的地方：frontend（scadaTags 是動態 dict）、i18n（由 registry 動態產生）、
  `opc_adapter.py`（自有 `TAG_MAPS`，不讀 registry）、modbus server、storage（`scada_json` blob）。

## Verify

- 新測試 `modules/monitoring/tests/test_scada_service_state_tags.py`：10 passed。
- Mutation：
  - 移除 `_integer_tags` 項目 → 6 fail
  - 映射改成常數或 service_mode → 5 fail
  - 還原 registry → 2 fail
  - 還原 export.py → 1 fail
- 全套 backend：**1305 passed / 7 skipped / 1 xfailed**（+10）。
- frontend：tsc 0 / vitest 1492 passed（70 files）/ vite build OK。
- `examples/data_quality_analysis.py`：20 通過 / 0 待改善，與 main 上已 commit 的報告一致。
  執行時被覆寫的 `data_quality_report.txt` / `simulated_scada_2h.csv` 已還原，不入 commit。

## Review（code-reviewer subagent）

- must-fix：0。
- should-fix 已全修：
  1. API_GUIDE tag 數同步。
  2. LockoutState 的 label 由「閉鎖」改為「緊急停機狀態」，並加註解說明它不是 latched 狀態。
  3. 兩個 OPC 名稱標註為 simulator-only placeholder。
  4. 補 CSV 欄位測試。
- 未採納：pin `WindFarmSimulator` seed，因為它的建構子不接受 seed。引擎層測試沿用
  `test_reset_keeps_fault.py` 的同款寫法。

## 沒有自動化保護 / 已知限制

- **LockoutState 不是 latch**：故障持續時 state 會在 7↔3 間擺盪，tag 也跟著擺盪。
  這就是「直接映射 tur_state==7」這項已核准 acceptance 的結果。若劉老師要真正 latch-until-reset
  的 LOTO 語意，需要另開 issue 新增狀態。
- **OPC 名稱沒有現場依據**：Bachmann Z72 tag 表（xlsx）查無對應項。接真實 PLC 前必須重新對齊。
- **grid-trip 路徑沒有獨立測試**：經由 grid-trip 進入 state 7 的路徑沒單獨測。它和 fault-trip
  共用同一個 `cmd_emergency_stop` → `_enter_state(7)`，所以只有讀原始碼層級的把關。
- 前端目前**沒有任何地方**顯示這兩個 tag（只有 registry、API、CSV 帶出來）。如需 UI 顯示要另開工作。

## 下次接手

- **優先**：`WMOM-20260505-25` Part B（`SpectralAlarmPanel`，5-band 頻譜 + crest/kurtosis），
  已核准，資料應已在 `scadaTags`（`WVIB_*` 30 tags）。做法比照 Part A，就地擴充 `TurbineDetail`。
- HTTPS 不再列入 autonomous 工作；F6 不要再嘗試 docker。
