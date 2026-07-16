# shared/plc_clients/bachmann/ — Z72 OPC-DA client（vendored）

> 來源說明，回應 `docs/product/PROJECT_REVIEW_2026-07-16.md` F6。
> CLAUDE.md §12 原則是「不要 fork 其他 repo 程式碼進來（用 submodule / pip）」；
> 本目錄是該原則下的**明列例外**——原因與範圍如下。

## 這是什麼

Bachmann Z72 PLC 走 **OPC-DA**（COM/DCOM，Windows-only、需 32-bit Python），
沒有可靠的純 pip 跨平台方案，故 vendored 一份客戶端與工具：

- `openopc2-0.1.18/` — OpenOPC2 函式庫完整原始碼（vendored，非 pip）
- `opc_data_reader*.py` / `opc_client.py` / `opc_list_tags.py` … — 現場擷取/診斷腳本
- `OpenOpc*.exe`、`openopc2-0.1.18.zip`、`OPC DA環境建立/`、`*.docx`、`*.md` 指南 — 環境建置素材

## 產品如何使用

- 執行期由 `modules/monitoring/server/opc_adapter.py` **lazy import**（`import openopc2` 在
  連線方法內），只在**接真實 Z72 PLC**時走到；**simulator 模式完全不需要**。
- `requirements.txt` **不含** openopc2 —— 依賴這份 vendored 副本在 sys.path 上
  （`opc_data_reader_fixed.py` 以 `sys.path.insert` 掛入）。

## 兩個待劉老師留意的事項（來自 review F6）

1. **授權**：OpenOPC2 為 **GPL-2.0-or-later**（見 `openopc2-0.1.18/LICENSE.txt`）。
   windMindOM 以商業合約（NT$2-4M）散布時，若隨附含 OPC-DA 能力的版本，GPL copyleft
   義務可能觸發。建議在第一筆合約前確認：(a) 交付版本是否含真-PLC 路徑；(b) 若含，
   如何符合 GPL（例：openopc2 以獨立進程/服務隔離、或改用授權相容的 OPC gateway）。
   ⚠️ 此為法務/商業判斷，本 README 僅標示，不代為決定。
2. **體積**：本目錄約 38 MB，含三個 ~11 MB 的 Windows `.exe` 與 926 KB zip。若確認
   `.exe`/zip 可由 `openopc2-0.1.18/` 原始碼重建或由環境另配，可考慮移出 git（改放
   deploy artifact / release asset）以縮小 repo。

## 動它之前

- 不要升級/改寫 openopc2 內部；要換版請整包替換並更新本檔版本號（現：0.1.18）。
- 真-PLC 連線調試看 `DCOM權限檢查指南.md` / `修正AddItems卡住問題.md`。
