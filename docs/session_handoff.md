# Session Handoff — 給下次 session 用

> 最後更新：2026-05-04（end of session）
> 本檔在 routine 收尾時更新；新 session 開工讀完 CLAUDE.md / ROADMAP / ISSUES 後可看這份知道「上次卡在哪、下次怎麼接」。

---

## 1. 今天（2026-05-04）的 session 整體軸線

進到 **M3 主線**（Workflow Part 1）。本日做了兩件事：

### 1.1 WMOM-20260504-10 — Cost ↔ Farm config 整合（**done**）

- M3 第一週插入工作 — 補 M2 demo 對 friendly customer 不夠 personalize 的缺口
- Branch: `claude/issue-20260504-10-2026-05-04`
- Commit: `f21fb1a`
- Code review: 7 finding 全處理（3 must-fix + 3 should-fix + 1 nice-to-have）
- Race condition follow-up: WMOM-20260504-13（low priority，M5/M6 再做）
- Tests: 60 PASS + 1 XFAIL（pre-existing），frontend Vite build 0 TS error
- 詳見：[`work-logs/2026-05/2026-05-04-cost-farm-integration.md`](../work-logs/2026-05/2026-05-04-cost-farm-integration.md)

### 1.2 WMOM-20260504-14 — z72_etech 取設計 + design notes（**in_progress**）

- M3 主線開工：依 CLAUDE.md §15「取材選 A — 讀程式產 design notes，不取程式」
- Branch: `claude/issue-20260504-14-2026-05-04`（從 -10 branch 接續）
- Commit: `1ff6626`
- 已完成：
  - z72_SCADA_etech repo inventory（盤點報告 + 重構路線圖 + 5 個關鍵 module 程式）
  - ISSUES.md 開 M3 主線 7 個 sub-issue（WMOM-14..20）
  - DN-01 Work Order Lifecycle design note 雛形 → [`docs/design-notes/m3/DN-01-work-order-lifecycle.md`](design-notes/m3/DN-01-work-order-lifecycle.md)
  - DN 索引 + etech 對照表 → [`docs/design-notes/m3/README.md`](design-notes/m3/README.md)
- **未完成（下次 session 主軸）**：
  - DN-02 Approval Multi-level
  - DN-03 Inventory ↔ Material Request

---

## 2. 兩個 branch 狀態

```
main
 ↓
 └─ claude/issue-20260504-10-2026-05-04   (commit f21fb1a — WMOM-10 done)
       ↓
       └─ claude/issue-20260504-14-2026-05-04   (commit 1ff6626 — DN-01 done) ← HEAD
```

兩個 branch 都尚未 push。劉老師確認後可：

```bash
# 都是 fast-forward push，先 -10 後 -14
git checkout claude/issue-20260504-10-2026-05-04
git push -u origin claude/issue-20260504-10-2026-05-04

git checkout claude/issue-20260504-14-2026-05-04
git push -u origin claude/issue-20260504-14-2026-05-04
```

或者直接 merge 進 main：

```bash
git checkout main
git merge claude/issue-20260504-14-2026-05-04   # 會帶入 -10 的 commits（鏈式接續）
git push origin main
```

---

## 3. 下次 session 第一件事

### 接續 WMOM-20260504-14：補 DN-02 + DN-03

優先順序：
1. **DN-02 Approval Multi-level** — etech 4 個 sign collection（`leadersign` / `supervisorsign` / `employeesign` / `affairsign`）統合為 `signoff` + `level`
   - Source 已讀（`server/leadersign.js` + `server/supervisorsign.js`）— 主要重點：
     - User group 500 / 666 / 300 / 100 對應四種簽核者
     - 用 `name` 欄位「轉走」表示這個人已簽（非常 hacky）
     - `materialformnumber` vs `totalformnumber` 兩種 business key 並存（前者是領料單）
   - DN-02 要寫：
     - signoff 表 schema（含 level enum）
     - chain 設計（依 work order type 決定要幾階）
     - "我的待簽" query 邏輯
     - approve / reject 行為（reject 回退 work_order 到 IN_PROGRESS）

2. **DN-03 Inventory ↔ Material Request** — M4 前置
   - Source: `server/materialsForm.js` + `server/inventory.js` + `server/inventoryclassify*.js` + `server/inventoryreturn.js`
   - DN-03 要寫：
     - etech 4 欄位庫存（新品 / 良品 / 維修中 / 待檢驗）→ windMindOM 簡化方案
     - materialsForm 兩通知 collection（總務用 / 組長用）→ 統合
     - 雙寫交易模型（領料 = 工單批次 → 庫存扣帳 + ledger entry，DN-03 設計但 M4 才實作）

### 完成 WMOM-14 後的下一個 issue

**WMOM-20260504-15 — 30 分鐘 walkthrough 跟劉老師確認 design notes**

DN-01 已列 7 個待確認問題（在 DN-01 §5），DN-02 / DN-03 補完後會再加問題。
walkthrough 後把確認 / 修正寫進 DN 文件 `## walkthrough notes` 區塊。

---

## 4. 需要劉老師回答的 walkthrough 問題（已知）

從 DN-01 §5：

| # | 問題 | 為何要問 |
|---|------|---------|
| Q1 | etech `removeFrom` 真實 use case？ | 決定 windMindOM CANCELLED state 的 cancel_reason 欄位設計 |
| Q2 | `chooseschange` 「追蹤觀察」vs「需改善」SLA / KPI 差別？ | FollowupKind enum 要 3 還是 2 值 |
| Q3 | 一台風機可同時有多張 OPEN 工單？ | unique constraint 設計 |
| Q4 | etech 沒有 PM / inspection 工單，windMindOM 是否一次預留 4 種 type？ | schema 一次設計到位 |
| Q5 | 離岸 weather_window block 工單，`weather_window_id` hard FK 還是可空？ | 決定 onshore / offshore 共用同一表 vs 分表 |
| Q6 | dayworkForm（每日工作日誌）合併 work_order.progress_notes 還是獨立？ | 影響表結構設計 |
| Q7 | 工單與「定檢清單 regularlistForm」的關係？etech 並行兩系統 | 決定本次 M3 是否合併 |

DN-02 / DN-03 補完會再多 5-8 個問題。預計 walkthrough 1 次共 12-15 個問題，30 分鐘可走完。

---

## 5. 整體 M3 後續 issue 鏈

| Issue | Status | 預估 | 依賴 |
|-------|--------|------|------|
| WMOM-14 | in_progress（DN-01 done） | 半天補完 DN-02 / DN-03 | — |
| WMOM-15 | open | 0.5 天 walkthrough | -14 done |
| WMOM-16 | open | 1 天 Work Order domain + 狀態機 | -14 + -15 done |
| WMOM-17 | open | 1 天 Work Order CRUD + REST API | -16 done |
| WMOM-18 | open | 1 天 Approval signoff API | -14 DN-02 + -17 |
| WMOM-19 | open | 1-1.5 天 frontend orders | -17 done |
| WMOM-20 | open | 1 天 frontend approval | -18 + -19 |

→ M3 總時程約 6-7 個工作日（與 ROADMAP 預估一致）。

---

## 6. 需要從外面拿的 input（不是 Claude 能解決的）

- 劉老師走 30 分鐘 walkthrough 確認 3 份 DN（WMOM-15 — 必須 in person / chat）
- WMOM-20260503-05 friendly 客戶 demo / contact（infrastructure 已就位，contact 動作是劉老師自己做）

---

## 7. 環境狀態提示

- Git: clean working tree on `claude/issue-20260504-14-2026-05-04`，HEAD = 1ff6626
- Pytest: cost+monitoring 60 PASS + 1 XFAIL
- Frontend: Vite build pass，CostPage 跑得起來，可 demo `dataset:k13 / farm:台中港曲風場 / farm:彰化離岸風場台電` 三選
- 兩個 demo farm cost_inputs.json 已存於 `modules/cost/data/farms/`
