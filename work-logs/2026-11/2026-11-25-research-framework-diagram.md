# 2026-11-25 — 研究架構圖草稿 v0.1；劉老師確認規劃

> Session 類型：規劃（只動文件、不寫 code）
> Session 長度：短
> 主導：劉老師要求，Claude 繪製
> 結果：研究架構圖草稿 v0.1 已發布，等劉老師看過。劉老師確認開發順序與預設值；看過圖之後才開始 WMOM-20261125-02。

---

## 1. Session 目標

劉老師回覆「同意你的規劃，開始之前先製作一個研究架構圖讓我看一下」。

認領 issue：WMOM-20261125-08（本 session 新開）。

## 2. 實際完成

### 2.1 主要工作

- **研究架構圖草稿 v0.1**：<https://claude.ai/artifact/4uZ6VgrG7wcBPRLYvVWFt4>
  - 主張：仿真風場一次產生兩份東西。看得到的資料往右走，給對外 API、工單與準備卡、可用率與成本；故障的真正原因往下另存，只有評分端拿得到，所以外部助理與準備卡的對錯可以自動核對。
  - 畫了什麼：風場設定 → 仿真風場（故障產生器 → 物理模型 → PLC 保護層 → 機組狀態）→ 資料循環保存 → 對外唯讀 API → 外部 RAG 運維助理；警報開單 → 工單 → 出發前準備卡 → 維修與定檢 → 完工才修復（回到機組狀態）；運轉狀態 → 可用率 → 成本；故障真相紀錄、題庫、準備卡內容、助理輸出 → 自動評分；真實風場以點線標為日後。
  - 標記：實線框＝已有、虛線框＝整塊待建、數字＝建置順序、紅線＝不對外的故障真相。
  - 圖下附建置順序（對應 issue）與「這個架構能回答的問題」四條草稿。
- **記錄劉老師的確認**：開發順序、10 秒原始資料保留半年、對外以 REST 為主並保留 OPC UA、外部身分用長效 API 金鑰對應唯讀角色。DEC-20261125-01、ISSUES、ROADMAP、CLAUDE.md、TODO、STATUS 裡「尚未逐項確認」「暫採」的字樣都已改掉。

### 2.2 卡住或延後的事

- 圖是草稿，還沒收進 repo。定稿後放進 `docs/architecture/`，並在更新 `windMindOM-architecture.md` 時引用。
- 「這個架構能回答的問題」四條是 Claude 依六項定位寫的草稿，不是劉老師給的研究問題，要請劉老師修改。
- WMOM-20261125-04 的修復規則（完工即修好，或處置對了才修好）尚未決定。
- 版面只在亮色主題下截圖檢查過一次。

### 2.3 重大決策

- 無新決策；DEC-20261125-01 補上劉老師的確認。

## 3. 產出清單

### 新增檔案

- `work-logs/2026-11/2026-11-25-research-framework-diagram.md`

### 修改檔案

- `docs/product/decision_log.md`（DEC-20261125-01：決策者與第 4、5 點改為已確認，加上外部身分的形式）
- `ISSUES.md`（新增 WMOM-20261125-08；-02、-03 的待決事項更新；統計表）
- `docs/product/ROADMAP.md`、`CLAUDE.md` §10、`TODO.md`、`STATUS.yaml`（確認狀態）

### 動了狀態的 issue

- WMOM-20261125-08：新開 → in_progress

### 寫進 decision_log 的決策

- 無

## 4. 下次怎麼接手

- 等劉老師看過研究架構圖。有修改就更新同一個 Artifact；定稿後收進 `docs/architecture/`，WMOM-20261125-08 改 done。
- 之後認領 `WMOM-20261125-02`（對外唯讀 API）。外部身分的形式已定：長效 API 金鑰對應唯讀角色。
- 沒有程式變更，測試沒有跑。

## 5. 2026-11-26 定稿

劉老師回覆「架構圖可以定稿，開始第 1 項」。

- Artifact 更新為 v1.0（拿掉草稿字樣）。
- 收進 repo：`docs/architecture/research-framework.md`（說明、圖例、建置順序、可回答的問題）與 `docs/architecture/research-framework.svg`（由 Artifact 的圖抽出的獨立 SVG，亮色、樣式內嵌）。
- `docs/architecture/windMindOM-architecture.md` 頂部與 `CLAUDE.md` §3 加上連結。
- WMOM-20261125-08：in_progress → done。
- `windMindOM-architecture.md` 的內容還沒依 EPIC-SF 改寫，留到 EPIC-SF 有功能完成時一起更新。
