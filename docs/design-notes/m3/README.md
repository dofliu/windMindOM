# M3 Design Notes — Workflow Part 1（Work Order + Approval）

> 對應 ROADMAP M3（2026-07）。
> 本目錄為 [WMOM-20260504-14](../../../ISSUES.md) 的產出 — 從 z72_etech repo 取設計，
> windMindOM 內部全部重寫（CLAUDE.md §15 「僅取設計、不取程式」）。

---

## 取材原則

- **Source**: `D:\Project_CodingSimulation\researchTopic\windFarmMonitor\z72_SCADA_etech\yitai-corp-cms-download1140811\` (2025-08-11 線上 baseline)
- **方針**: 讀 etech 程式 → 寫 design notes → windMindOM 重寫，**不 fork 程式碼**
- **Walkthrough**: 3 份 DN 完成後跟劉老師走一次（[WMOM-20260504-15](../../../ISSUES.md)），把確認 / 修正寫進 DN 文件 `## walkthrough notes` 區塊

---

## 三份 design notes

| ID | 標題 | 對應 etech module | windMindOM module | Status |
|----|------|-------------------|-------------------|--------|
| **DN-01** | [Work Order Lifecycle](DN-01-work-order-lifecycle.md) | `repair` / `repairTemp` / `trackFrom` / `removeFrom` / `allForm` | `modules/workflow/domain/work_order.py` | ✅ 雛形 done（2026-05-04） |
| **DN-02** | Approval Multi-level | `leadersign` / `supervisorsign` / `employeesign` / `affairsign` | `modules/workflow/domain/signoff.py` | ⬜ 待補（下次 session） |
| **DN-03** | Inventory ↔ Material Request | `materialsForm` / `materialsFormNotic{,Led}` / `inventory*` (×4) | `modules/workflow/domain/material_request.py` + M4 inventory | ⬜ 待補（下次 session） |

## etech repo 對照表（10 大功能模組 → windMindOM module）

| etech 模組 | windMindOM Milestone | windMindOM module | 取材重點 |
|-----------|----------------------|-------------------|---------|
| 3.5 維修派工（`repair*` × 4 collection） | M3 | `modules/workflow/` Work Order | DN-01 |
| 3.6 庫存與物料請領（`inventory*` × 4 + `materialsForm*`） | M4 Part 2 | `modules/workflow/inventory.py` | DN-03 |
| 3.7 簽核流程（`*sign` × 4 collection） | M3 | `modules/workflow/signoff.py` | DN-02 |
| 3.8 出勤打卡 / 排班 / 月結 | M3+ 後續（人員）| `modules/workflow/personnel.py` | (M3 之後評估，本次 not in scope) |
| 3.4 表單三聯（定期 / 每日 / 工作） | M3+ 後續（日誌）| `modules/workflow/log_form.py` | (合併入 work order 還是獨立 entity，DN-01 有討論) |
| 3.9 SCADA 遙測管線 | 已搬入 monitoring | `modules/monitoring/` | （windMindOM 已 done，etech 走 z72bridge 方向） |

## 不取的東西（要避免再爭論）

- ❌ etech 4 個 sign collection 的設計（明確 anti-pattern → DN-02 統合）
- ❌ etech repairTemp + repair 雙 collection 設計（→ DN-01 統合為單一 work_order + status）
- ❌ etech 的 `allForm` audit ad-hoc collection（→ DN-01 改為 event log / event sourcing 模式）
- ❌ etech 中文 typo（如 `cheakin` → `checkin`、`removeFrom` → `removeForm`）
- ❌ etech 3.10 server/index.js 硬編 cookie key / IP（windMindOM 從一開始就走 .env）
