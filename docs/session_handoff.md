# Session Handoff — 給下次 session 用

> 最後更新：2026-05-05（end of session — M3 backend 100% done + 架構圖到位）
> 本檔在 routine 收尾時更新；新 session 開工讀完 CLAUDE.md / ROADMAP / ISSUES 後可看這份知道「上次卡在哪、下次怎麼接」。

---

## 1. 今天（2026-05-05）的 session 整體軸線

**M3 主線 backend 100% 完成 + 架構圖到位**，剩 frontend (-19/-20)。

今天連跑 6 個 issue + 1 個 docs，**5 個 PR 全 merged 進 main**：

### 1.1 WMOM-20260505-01 — Snapshots 表失控 hotfix（**done** — 早段做的）

- 彰化 farm `wind_farm.db` 17.5 天累積 41.9 GB 處理 + dedupe + VACUUM 工具
- 先前 PR #3 已 merged；劉老師執行 `--purge-snapshots` 釋放 41 GB ✓

### 1.2 WMOM-20260504-14 / -15 — z72_etech 取設計 + walkthrough（**done** — PR #4）

- 3 份 design notes（DN-01/02/03）一次完成 + 17 個 walkthrough Q 全 confirmed
- 2 個衍生 issue 開好（WMOM-21 day_work_form / WMOM-22 inspection_schedule）

### 1.3 WMOM-20260504-16 — Work Order domain + 狀態機（**done** — PR #5）

- 4 Enum + dataclass + 9-transition state machine + 73 tests
- Code review 13 finding 全處理（含 UTC datetime / kw_only Followup / regex 強化）

### 1.4 WMOM-20260504-17 — Work Order CRUD + REST API（**done** — PR #6）

- SQLAlchemy 2.0 ORM + 11 endpoints + repository factory + multi-WO constraint
- Code review 9 finding 全處理（含 business_key collision / FarmRegistry singleton）

### 1.5 WMOM-20260504-18 — Approval signoff API + 整合（**done** — PR #7）

- 4 階 signoff chain + step + history + 與 work_order finish/approve/reject 自動整合
- Code review 11 finding 全處理（兩輪 review，第 2 輪含 security bypass / stale chain pointer / business_key 03d 等 14 個）

### 1.6 docs: 系統架構圖 + 生圖 prompts（**done** — PR #8）

- Mermaid 主架構圖（1 全貌 + 7 補充）— 給 dev / partner / 客戶 demo
- 生圖模型 prompts（hero / infographic / pitch cover）— 給簡報 / 行銷物用

---

## 2. main 狀態（PR #4-#8 全 merged）

```
main HEAD（最新）
 ├ PR #8 docs(architecture)               ✅ merged
 ├ PR #7 fix: code review 第 2 輪 14 finding ✅ merged
 ├ PR #7 feat: WMOM-18 signoff API         ✅ merged
 ├ PR #6 feat: WMOM-17 CRUD/REST API       ✅ merged
 ├ PR #5 feat: WMOM-16 domain + 狀態機      ✅ merged
 └ PR #4 docs: DN-02/03 + walkthrough       ✅ merged
```

整 pytest: **257 PASS + 1 XFAIL**（cost 49 + monitoring 35 + workflow 173）

---

## 3. 下次 session 第一件事：WMOM-20260504-19 frontend orders

開始 **/admin/workflow/orders frontend**。

### 範圍（依 ISSUES.md WMOM-20260504-19）

- `frontend/services/workOrderService.ts` — TypeScript API client（對應 `/api/workflow/work-orders/*` 11 endpoints）
- `frontend/hooks/useWorkOrders.ts` — stateful hook（CRUD + transition）
- `frontend/components/WorkflowPage.tsx` — 主入口（tab 切換 orders / approval）
- `frontend/components/workflow/WorkOrderListPanel.tsx` — 列表（含 status filter + Hnumber search + 分頁）
- `frontend/components/workflow/CreateWorkOrderWizard.tsx` — 建立精靈（多步：選風機 / 選故障代碼 / 派工人員 / 預估工時）
- `frontend/components/workflow/WorkOrderDetailModal.tsx` — 詳情 + 狀態 transition 按鈕
- 估時：1-1.5 工作天

### 預估技術選型對齊既有 cost frontend pattern

| 既有 (cost frontend) | workflow frontend |
|------|---|
| `services/costService.ts` (TS API client) | `services/workOrderService.ts` |
| `hooks/useCostData.ts` (useAsync) | `hooks/useWorkOrders.ts` |
| `components/CostPage.tsx` (4 panel) | `components/WorkflowPage.tsx` (tab) |
| `recharts` 圖表 | 工單列表 + table |
| `useI18n` zh/en hook | 同 |
| `FarmSelector` 整合 | 同（共用 farm_id） |

### 之後接 WMOM-20

`/admin/workflow/approval` frontend — 待簽列表 + 簽核 dialog（依 PR #7 的 signoff API）

---

## 4. M3 進度

```
M3 主線 7 sub-issue:
 ✅ WMOM-14 z72_etech 取設計
 ✅ WMOM-15 walkthrough
 ✅ WMOM-16 Work Order domain + 狀態機
 ✅ WMOM-17 Work Order CRUD + REST API
 ✅ WMOM-18 Approval signoff API
 ⬜ WMOM-19 frontend orders                  ← 下一個
 ⬜ WMOM-20 frontend approval

M3 衍生 issue（M3 後續 / M4 之間做）:
 ⬜ WMOM-21 day_work_form 員工日誌
 ⬜ WMOM-22 inspection_schedule 定檢計畫
```

**M3 backend 100% done**；frontend 預估 5-6 個工作日跑完 -19/-20，之後就能跑完整 demo（建工單 → 派工 → 簽核 → 結案）。

---

## 5. 環境狀態提示

- **Git**: clean working tree on main（HEAD = PR #8 merge）
- **Pytest**: 257 PASS + 1 XFAIL（cost 49 / monitoring 35 / workflow 173）
- **Frontend Vite build**: pass
- **DB**: 彰化 farm `wind_farm.db` ~50 MB（VACUUM 後正常運作）
- **設計文件**: 三份 DN 全 done + 架構圖到位 + walkthrough 17 Q 全 confirmed

---

## 6. 進入 -19 前可看的東西

| 想知道 | 看哪 |
|---|---|
| 整體架構（一張圖） | [`docs/architecture/windMindOM-architecture.md`](architecture/windMindOM-architecture.md) |
| Work Order 11 endpoints API | `python run.py` → `http://localhost:8100/docs` workflow tag |
| 工單狀態機 / signoff chain | DN-01 / DN-02 |
| 既有 frontend pattern（cost） | `frontend/components/CostPage.tsx` + `services/costService.ts` |
| FarmSelector 切 farm 行為 | `frontend/components/FarmSelector.tsx` |

---

## 7. 給下次 session claude 的明確 first action

```bash
# 1. sync main + 確認狀態
cd D:\Project_CodingSimulation\researchTopic\windMindOM
git checkout main
git pull --ff-only
python -m pytest modules/cost/ modules/monitoring/ modules/workflow/ -q
# 預期：257 passed

# 2. 開 -19 branch
git checkout -b claude/issue-20260504-19-2026-XX-XX  # 替換 XX-XX 為當天日期

# 3. 開 work-log
# work-logs/2026-XX/2026-XX-XX-workflow-frontend-orders.md

# 4. 進 routine：domain pattern 對齊既有 cost frontend
```

---

## 8. 重要決策回顧（這個 session 內）

- **WMOM-18 整合策略**：work_order finish → 自動建 chain；approve last → 自動 wo.approve_all；reject → 自動 wo.reject。失敗時不 raise 500，回 200 + `subject_transition_error` 欄位
- **Security bypass fix**：POST `/work-orders/{id}/approve` 強制檢查 chain status APPROVED
- **business_key 03d 三位零填補** — 預留 100+ 張/月場景
- **架構圖**用 Mermaid（純文字 / GitHub render / 版控友善）— 不採 draw.io / PNG 截圖
- **生圖 prompts** 給 hero / infographic / pitch deck 三用途分別寫 prompt（中英文版本）
