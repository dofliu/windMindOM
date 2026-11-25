# 2026-11-25 — 重新定位定案：仿真運維風場（DEC-20261125-01），出發前助理保留

> Session 類型：規劃（只動文件、不寫 code）
> Session 長度：中
> 主導：劉老師定調，Claude 記錄與拆解
> 結果：重新定位寫成 DEC-20261125-01，立 EPIC-SF，開 6 個 issue，文件同步。下一項是 WMOM-20261125-02（對外唯讀 API）。

---

## 1. Session 目標

承接同日的缺口分析（`2026-11-25-repositioning-gap-analysis.md`）。劉老師回覆：出發前的運維助理仍然需要——在仿真運維風場裡，工單派出來時要有這份資訊協助檢視判斷；之後若能接上真實風場，對驗證更有利。

認領 issue：WMOM-20261125-01（本 session 新開）。

## 2. 實際完成

### 2.1 主要工作

- **DEC-20261125-01**：重新定位為仿真運維風場（六項），出發前助理保留為工單上的準備卡。
- **出發前助理怎麼排進來**：
  - 掛在工單上：警報 / 跳機開出的工單配故障出勤卡（先做），定檢工單配例行巡檢卡（後做）。
  - 企劃 v0.1 的原則照用：只用可觀測資料、資料截止點、可回查、證據不足不下判斷、不判定根因。
  - 仿真風場知道每筆故障的真正原因，所以準備卡的內容可以自動核對，樣本數由機率式故障長時間累積。這解掉了 11-24 審查的兩個疑慮（真實資料、樣本太少）。準備時間能省多少，仍要等真人或真實風場。
  - 規則版放 windMindOM；外部 RAG 運維助理經對外 API 取得同一張工單與同一批資料，可產生自己的摘要做對照。這一點是 Claude 建議。
- **開發順序調整**（相對於同日稍早的建議）：
  - 運維閉環（-04）提前到機率式故障（-06）之前。原因：跳機的機組要等修復才解鎖，沒有修復路徑時，隨機故障只會讓機組一台一台停下來；準備卡也要先有警報開出的工單。
  - 準備卡（-05）排在運維閉環之後、機率式故障之前：開發期用手動注入就能做，大量核對等 -06。
  - -06 加上「模擬維修班」：沒有人處理工單時自動完工，否則無人值守的風場會停光。
- **EPIC-SF 與 issue**：WMOM-20261125-01（done）、-02 對外唯讀 API、-03 長時間運轉的基礎、-04 運維閉環、-05 出發前準備卡、-06 機率式故障產生器、-07 實測風況匯入；成本一項沿用既有的 WMOM-20260504-11。
- **文件同步**：ROADMAP（新主線一節）、PRODUCT_VISION（頂部說明）、CLAUDE.md §1 / §10、STATUS.yaml、TODO.md。
- **ISSUES.md 統計表更正**：表格先前停在 157（open 7 / in_progress 2 / done 146），逐條解析 header 的實際值是 158（open 6 / in_progress 1 / deferred 2 / done 149）。本次更新為 165（open 12 / in_progress 1 / deferred 2 / done 150）。

### 2.2 卡住或延後的事

- 劉老師明確確認的只有兩件：六項定位、保留出發前助理。開發順序、保留期半年、對外以 REST 為主，都是 Claude 建議、暫採，DEC 與各文件都照這樣標示。
- `docs/architecture/windMindOM-architecture.md` 與 `README.md` 還沒跟上新定位，留到 EPIC-SF 第一項完成時一起更新。
- 企劃 v0.1 的雙卡原型與長跑紀錄不在 repo。它記的兩個現象（雲端長跑約 57 分停止寫入、十分鐘彙整重疊計數）併入 -03 重現。

### 2.3 重大決策

- DEC-20261125-01

## 3. 產出清單

### 新增檔案

- `work-logs/2026-11/2026-11-25-repositioning-decision.md`

### 修改檔案

- `docs/product/decision_log.md`（DEC-20261125-01）
- `ISSUES.md`（EPIC-SF、WMOM-20261125-01 ~ -07、統計表）
- `docs/product/ROADMAP.md`（頂部說明、「現行主線（2026-11-25 起）」一節；EPIC-DS 一節改標為前一條主線）
- `docs/product/PRODUCT_VISION.md`（頂部說明）
- `CLAUDE.md`（§1 定位、§10 方向與下次工作）
- `STATUS.yaml`（last_updated、EPIC-SF、EPIC-DS 改 completed、issue_stats、next_milestone 前綴）
- `TODO.md`（最後更新區塊）

### 動了狀態的 issue

- WMOM-20261125-01：新開 → done
- WMOM-20261125-02 ~ -07：新開（open）

### 寫進 decision_log 的決策

- DEC-20261125-01：重新定位為仿真運維風場；出發前助理保留為工單上的功能

## 4. 下次怎麼接手

- 認領 `WMOM-20261125-02`（對外唯讀 API 與外部系統身分）。開工前請劉老師定外部身分的形式——建議長效 API 金鑰對應一個唯讀角色。
- 要先讀：盲測守則、資料包守則（`CLAUDE.md` §10）；`server/storage.py` 的 `is_observable_event`、`server/scenario_pack.py` 的 `pack_columns()` 與 `MODEL_INTERNAL_TAGS`。
- 現況的洞：`GET /api/export/events` 會回傳 `Fault injected: {scenarioId}`，`GET /api/faults/active` 任何登入者可讀。
- 沒有程式變更，測試沒有跑；backend / frontend 測試數照 2026-10-26 的紀錄。
