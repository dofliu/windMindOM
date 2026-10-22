# 2026-10-22 — WMOM-20261022-03：架構全貌圖更新與專案文件同步

> Session 類型：文件
> Session 長度：中
> 主導：Claude（劉老師要求「用一個架構圖說明專案功能與目前狀況，並更新專案文件」）
> 結果：WMOM-20261022-03 done

---

## 1. Session 目標

WMOM-20261022-01（全面檢查）合併後，劉老師想先整體了解專案的功能與現況。要做的事：

- 用架構圖說明專案功能與目前狀況；
- 把過時的專案文件更新到現況。

盤點時發現的過時處：

- `docs/architecture/windMindOM-architecture.md` 停在 2026-05（M3、v0.8.1 初版），沒有 EPIC-DS、knowledge / auth 模組，也沒有三條資料管道。
- README 仍寫「M5 進行中」：沒有 EPIC-DS，測試數停在 998 / 797，monitoring 寫「104 tag / 11 情境」，文件地圖缺合約與 starter kit。
- PRODUCT_VISION 沒提 2026-10-21 的方向調整。
- ROADMAP 的 EPIC-DS 表沒有狀態欄，也缺 -10 / -11 / -12、-08-a 與全面檢查。

## 2. 實際完成

### 2.1 架構說明頁（互動頁）

https://claude.ai/artifact/UrzWspWNw8GTmsz9fwxq7u

- **圖 1 分層架構**：使用者 → 前端 → 介面 → 六個功能模組 → 資料與外部系統，依完成狀態上色。
- **圖 2 EPIC-DS 資料流**：故障排程 → 物理 + PLC → 讀值 / 可觀測事件 → 三條管道 → 受測端 → 評分；圖上畫出標準答案與盲測資料的邊界。
- **其他內容**：各模組功能卡、EPIC-DS 各階段表、正式評測規則、進度條、最近一次全面檢查結果、下一步、文件地圖。

### 2.2 `docs/architecture/windMindOM-architecture.md` 全面改寫

| 節 | 內容 |
|---|---|
| 1 全貌 | 使用者 / 前端 / API 與資料出口（REST、WS 即時、Modbus、資料包、WS 回放、OPC UA）/ 六模組 / 儲存 / 外部系統 |
| 2 EPIC-DS | 資料流 + 盲測邊界、各項規則對照（標準答案、可觀測事件白名單、伺服器蓋時間、正式評測強制登入、總速率） |
| 3 monitoring 內部 | 一步模擬：風況 → 物理 → PLC 保護層 → 感測器模型 → SCADA tag，故障引擎如何介入 |
| 4–7 | 模組分層、工單狀態機、簽核鏈、與 7 個來源 repo 的關係（沿用並修正） |
| 8 儲存 | 改用實際表名（`turbine_data`、`history_events`、`scenario_ground_truth`、`replay_runs` 等） |
| 9 時程 | 原 6 個月路線圖 + EPIC-DS 甘特圖與現況表 |

驗證方式：9 張 mermaid 都經 mermaid-cli 10.9.1 渲染檢查，沒有錯誤。過程中修了兩個問題：

- 工單狀態機的標籤含冒號，造成解析失敗。
- 全貌圖原本用往上的邊，排版糾纏；改成全部往下的邊，加上 LR 子圖。

### 2.3 其他文件

| 檔案 | 變更 |
|---|---|
| `README.md` | 改寫：現況（EPIC-DS 主線、M1–M6）、六模組表、EPIC-DS 三條管道、常用環境變數、測試數（1963 / 1513）、文件地圖、repo 結構（`examples/`、`tools/`） |
| `docs/product/PRODUCT_VISION.md` | 頂部加 DEC-20261021-01 方向調整說明：定位與功能仍有效，商業時程保留為歷史 |
| `docs/product/ROADMAP.md` | EPIC-DS 表加狀態欄；補上 -10 / -11 / -12、全面檢查、-08-a、手冊保真度（下一步）；合約版本改 v1.3 |
| `CLAUDE.md` | 文件表的架構文件說明 |
| `ISSUES.md` / `STATUS.yaml` / `TODO.md` | 新增 -03 → done；統計 done 143 / total 154 |

### 2.4 順手修正：範例網址的 port

starter kit 與 OPC UA CLI 的說明與範例網址寫成 `ws://localhost:8000/ws/replay`。backend 預設是 8100（`BACKEND_PORT`、`.env.example`、`run.py`），照抄會連不上。已改成 8100：

- `examples/rag_starter_kit/stream_client.py`
- `examples/rag_starter_kit/opcua_client.py`
- `examples/rag_starter_kit/README.md`
- `tools/opcua_server.py`

這些地方只有 docstring 與說明文字改了，程式行為不變。

### 2.5 核對

- README 寫進去的環境變數、指令與數字逐項對過程式。
  - `WMOM_DEV_MODE` 的用途原本寫錯，已修正：它跳過職責分離檢查，並在沒設金鑰時改用隨機 dev 金鑰；「無 token 退回 dev 行為」其實是 `WMOM_AUTH_ENFORCE` 未開時的預設。
- ISSUES.md 的 header 逐條解析：open 7 / in_progress 2 / deferred 2 / done 143 = 154。

## 3. 產出清單

### 新增檔案

- `work-logs/2026-10/2026-10-22-architecture-docs.md`

### 修改檔案

- `docs/architecture/windMindOM-architecture.md`
- `README.md`
- `docs/product/PRODUCT_VISION.md`
- `docs/product/ROADMAP.md`
- `CLAUDE.md`
- `ISSUES.md`
- `STATUS.yaml`
- `TODO.md`
- `examples/rag_starter_kit/stream_client.py`
- `examples/rag_starter_kit/opcua_client.py`
- `examples/rag_starter_kit/README.md`
- `tools/opcua_server.py`

### 動了狀態的 issue

- WMOM-20261022-03：（新開）→ done

### 寫進 decision_log 的決策

- 無（只整理現況，沒有改方向）

## 4. 下次怎麼接手

1. **WMOM-20261022-02 手冊保真度**（劉老師排在 -08 其餘子項前）。接手方式見 `work-logs/2026-10/2026-10-22-epic-ds-verification.md` §4。
2. 之後做 -08 其餘子項，開工時先請劉老師挑順序。
3. 架構文件的維護方式：
   - 動到模組、資料出口或儲存表時，同步更新 §1 全貌圖與 §8 儲存結構。
   - EPIC-DS 有進度時，更新 §9 的現況表。
   - 改完用 mermaid-cli 渲染檢查。

## 5. 學到的事

- 文件過時最常發生在「方向調整」之後：每個 issue 都更新 STATUS / ISSUES，但 README、願景文件、架構圖這類入口文件沒有人負責跟著改。之後遇到 DEC 等級的方向調整，要把這三份列進收尾清單。
- mermaid 的標籤避免冒號與往上的邊：前者讓狀態圖解析失敗，後者讓 flowchart 排版糾纏。
