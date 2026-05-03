# 2026-05-04 — 搬入 v0.5 有用資產（WMOM-20260503-02）

> Session 類型：取材 + 文件整理
> Session 長度：短
> 主導：Claude（劉老師指示「繼續下一項工作」）
> 結果：v0.5 baseline pitch deck 入庫；routines/templates/agents 已現代化（v0.5→v0.8.1 diff 確認），補 inventory 紀錄；decision_log 補棄用清單

---

## 1. Session 目標

WMOM-20260503-02 — 把 v0.5 prototype（路徑：`../windFarmOM_bk/`）裡仍有用的資產搬進來，
不重複造輪子；同時記錄哪些 v0.5 設計被 v0.8.1 取代而不搬。

具體交付（issue 描述）：

- `docs/sales/pitch_deck_v0.5_baseline.{md,pptx}`（先存底，v0.8.1 改版見 WMOM-20260503-04）
- `docs/routines/daily-workflow.md`（已存在 → 確認最新版）
- `templates/`（盤點清單）
- `docs/claude-code-templates/`（盤點清單）

## 2. 實際完成

### 2.1 主要工作

- ✅ 建立 `docs/sales/`，複製 v0.5 pitch deck（`pitch_deck.md` + `pitch_deck.pptx`）
  → `docs/sales/pitch_deck_v0.5_baseline.{md,pptx}`，作為 -04 改版的 baseline
- ✅ Diff 比對 `docs/routines/daily-workflow.md`、`templates/*.md`、`docs/claude-code-templates/`
  與 v0.5（`../windFarmOM_bk/`）對應檔案 → 結論：
  - `daily-workflow.md` 已是 **v1.1（2026-05-03）**，比 v0.5 v1.0 新；無需搬
  - `templates/issue-template.md` 已去掉 `M0` 選項（v0.5 還有 M0 planning），無需搬
  - `templates/decision-template.md` / `work-log-template.md` 也已是 v0.8.1 對齊版本
  - `docs/claude-code-templates/` 4 個 commands + agents/code-reviewer.md 已現代化
- ✅ 寫 `docs/sales/v05_assets_inventory.md`，紀錄「哪些搬 / 哪些已現代化 / 哪些棄用」
- ✅ `docs/product/decision_log.md` 補 DEC-20260504-01：v0.5 棄用資產清單與理由
  （ASSETS_MAP / MIGRATION_TO_CLAUDE_CODE / adapter ABC / Workflow Hub design notes
  → 已被 DEC-20260502-06 取代）

### 2.2 卡住或延後的事

- 無

### 2.3 重大決策

- DEC-20260504-01：v0.5 棄用資產清單（決策面已在 DEC-20260502-06 拍板，本筆只是
  把「對應的檔案」明列出來）

## 3. 產出清單

### 新增檔案

- `docs/sales/pitch_deck_v0.5_baseline.md`（11.5 KB，從 v0.5 複製）
- `docs/sales/pitch_deck_v0.5_baseline.pptx`（53 KB，從 v0.5 複製）
- `docs/sales/v05_assets_inventory.md`（搬入/棄用對照清單）
- `work-logs/2026-05/2026-05-04-migrate-v05-assets.md`（本檔）

### 修改檔案

- `docs/product/decision_log.md`（追加 DEC-20260504-01）
- `ISSUES.md`（WMOM-20260503-02: open → done；統計表 +1 done / -1 open）
- `STATUS.yaml`（M1 progress 35→55、issue_stats、last_updated、next_milestone）

### 動了狀態的 issue

- WMOM-20260503-02: open → done

### 寫進 decision_log 的決策

- DEC-20260504-01：v0.5 棄用資產清單明列化（plugin SDK / adapter ABC / Workflow Hub
  / ASSETS_MAP / MIGRATION_TO_CLAUDE_CODE 不搬，理由見 DEC-20260502-06 v0.5→v0.8.1 pivot）

## 4. 下次怎麼接手

下一個 issue：**WMOM-20260503-04 — Pitch deck v0.8.1 改版**

1. 讀 `docs/sales/pitch_deck_v0.5_baseline.md` 知道 v0.5 的故事
2. 讀 `docs/product/PRODUCT_VISION.md` 確認 v0.8.1 套餐分層、ICP（運維廠商）
3. 用 `pptx-jliu-style` skill / Navy 主題出新版（5 modules 一張圖、simulator-first
   demo flow、第一目標客戶 Z72）
4. 同時產出 `docs/sales/pitch_deck_v0.8.1_outline.md` + onepager PDF

阻擋項：無（-02 已 done，-04 解鎖）

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 與用戶對話、釐清方向 | 5% |
| 文件 diff / 盤點 | 30% |
| 寫文件（inventory / decision_log / work-log） | 50% |
| 收尾（ISSUES / STATUS / commit） | 15% |

## 6. 學到的事

- 「搬資產」不一定要真的搬檔案 — 大多數 v0.5 routines/templates 在更早的 session
  就已現代化。本 session 真正的價值是把「盤點結果」寫成可追溯的 inventory 文件
  而不是無腦複製。
- v0.5 → v0.8.1 的關鍵棄用清單只有四項（plugin SDK / adapter ABC / Workflow Hub
  / 兩份 migration 文件），都是過度工程的副產物，與 DEC-20260502-06 拍板一致。

## 7. Open questions（park）

- 是否要把 `../windFarmOM_bk/` archive 到 `docs/legacy/v0.5_snapshot/`？
  → 暫不搬（git history 已保留），等 M2 完成後再評估清理時機
