# Session Handoff — 給下次 session 用

> 最後更新：2026-05-07（end of session — 前端 UI 改版 + 工作規劃整理）
> 本檔在 routine 收尾時更新；新 session 開工讀完 CLAUDE.md / ROADMAP / ISSUES 後可看這份知道「上次卡在哪、下次怎麼接」。

---

## 1. 今天（2026-05-07）的 session 整體軸線

**整個 frontend 視覺 baseline 換成 A · Calm Operator 設計 + 雙主題系統**，外加把這次的決策都寫進工作規劃文件，避免 regression。

今天 2 個 PR 全 merged 進 main：

### 1.1 WMOM-20260507-01 — 前端 UI 改版（**done** — PR #12）

依劉老師 `WMOM 介面改版交接書.md` + `app/VA.jsx` 設計稿改版整個 frontend：

- **基礎設施**：建立 `frontend/theme/`（鼠尾草綠 / 翡翠玻璃雙 palette + ThemeProvider + localStorage）+ `frontend/components/ui/`（10 個共用元件 — Card / Btn / PageHeader / StatusPill / Stat / Logo / NavIcon / Sidebar / BigChart / MiniSparkline / HealthBar / Field / Input / Select / ReadOnlyBox）
- **5 大頁面重畫骨架**：FarmOverview / TurbineDetail / MaintenanceHub / CostPage / HistoryPage 全部按交接書 §4 規格重寫；220 px 左 sidebar 取代頂部 header；DM Serif H1 + Manrope 內文 + JetBrains Mono 數字
- **沿用頁套新樣式**：FaultInjectionPanel / SettingsPage / DispatchModal / WorkOrderDetailModal / FarmSelector / TrendChartPanel / EventComparisonView 全套新 ui 元件，**功能完全不動**
- **刪除 6 孤兒**：DataCard / Gauge / StatusIndicator / MiniTrendChart / FarmTrendChart / icons.tsx
- **API / hooks 全不動**：useMockTurbineData / useRealtimeData / useMaintenanceData / useCostData / useI18n / useSettings 與 OperatorControl 6 指令、AI fault diagnosis、Dispatch 流程、CSV 匯出、4 cost endpoint 完整保留
- 規模：35 檔 / +7273 / -3659；`npx tsc --noEmit` 0 錯誤；劉老師於 5179 視覺 review 通過

### 1.2 docs(#WMOM-20260507-01) 整理工作規劃（**done** — PR #13）

- WMOM-20260507-01 issue 加「Intentional placeholders」段，列 7 個無 onClick 的 PageHeader 按鈕（劉老師 2026-05-07 確認保留作開發階段視覺鷹架）
- 新增 **WMOM-20260507-02**（open / low）作為逐項補功能的 check list — 6 個 sub-task 排好順序與 estimate
- M3+ frontend issue（WMOM-19/-20/-21/-25）全部加上「使用新 ui 元件庫」directive，避免後續 frontend 工作 regress 回 Tailwind / cyan dark
- ROADMAP Month 1 主要交付表格新增「前端 UI 改版」一行

---

## 2. main 狀態（2 個 PR 都 merged）

```
main HEAD（最新）
 ├ PR #13 docs: 工作規劃整理                    ✅ merged 2026-05-07
 ├ PR #12 feat: 前端 UI 改版（Calm Operator）   ✅ merged 2026-05-07
 ├ PR #11 docs: WMOM-23 全 Layer 1-7 完成       ✅ merged 2026-05-06
 └ … 之前的 PR
```

**整 pytest**: 上次（2026-05-06）257 PASS + 1 XFAIL；本次只動 frontend，未動 backend，預期不變。新 session 第一步可重跑驗證。

---

## 3. 下次 session 第一件事：WMOM-20260504-19 frontend orders

### 為什麼是這個

- M3 backend 100% done（PR #5/#6/#7 已合）
- 現在有完整的 `frontend/components/ui/` + `frontend/theme/` 元件庫可用
- 工單前端是 M3 demo 必要的最後一塊

### 範圍（依 ISSUES.md WMOM-20260504-19）

- `frontend/services/workOrderService.ts` — TypeScript API client（對應 `/api/workflow/work-orders/*` 11 endpoints）
- `frontend/hooks/useWorkOrders.ts` — stateful hook（CRUD + transition）
- `frontend/components/WorkflowPage.tsx` — 主入口（tab 切換 orders / approval）
- `frontend/components/workflow/WorkOrderListPanel.tsx` — 列表（含 status filter + Hnumber search + 分頁）
- `frontend/components/workflow/CreateWorkOrderWizard.tsx` — 建立精靈（多步：選風機 / 選故障代碼 / 派工人員 / 預估工時）
- `frontend/components/workflow/WorkOrderDetailModal.tsx` — 詳情 + 狀態 transition 按鈕

### **UI directive**（重要 — WMOM-20260507-01 後新增）

**必須使用** `frontend/components/ui/`（Card / Btn / PageHeader / StatusPill / Field / Input / Select / Stat / BigChart / HealthBar）+ `frontend/theme/`（`useTheme()` → `C` palette）。

**不可**：
- 寫 Tailwind utility class（`bg-gray-800` / `text-cyan-400` 等）
- 硬寫 hex（chart event 標記色除外）
- 引用任何 `frontend/components/icons.tsx` 之類的舊孤兒（已刪）

模板可參考：
| 想做的事 | 看哪個現有檔案當範例 |
|---|---|
| 列表頁 + 表格 + 篩選 | [MaintenanceHub.tsx](../frontend/components/MaintenanceHub.tsx)（工單表格 + 技師排班） |
| Modal（含表單） | [DispatchModal.tsx](../frontend/components/DispatchModal.tsx)（單欄）/ [WorkOrderDetailModal.tsx](../frontend/components/WorkOrderDetailModal.tsx)（多欄 + 照片上傳） |
| 多 step wizard | 沒有現成的；建議新建一個 `Wizard` ui 元件，或在 modal 內用 step state（簡單 case） |
| API client + async hook | [services/costService.ts](../frontend/services/costService.ts) + [hooks/useCostData.ts](../frontend/hooks/useCostData.ts) — 已是改版相容的 pattern |

### 估時：1-1.5 工作天

接著做 **WMOM-20260504-20 frontend approval**（待簽列表 + 簽核 dialog），同樣套新元件，1 工作天。

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

**M3 backend 100% + frontend baseline 已備**；剩 -19/-20 跑完就能跑完整 demo（建工單 → 派工 → 簽核 → 結案）。

---

## 5. 環境狀態提示

- **Git**: 主 repo `main` 已合到 PR #13；本 worktree 在 `claude/issue-20260507-01-planning-cleanup` 分支（兩個 PR 合完即可移除 worktree）
- **Frontend dev server**:
  - `cd frontend && npm run dev` 預設 port 3100（package.json `dev` script）
  - 現在 main 上的 frontend 已是新 UI（劉老師 2026-05-07 確認）
- **Frontend deps**: `package.json` 沒變動，`npm install` 已跑過；之後不需要重跑除非 deps 改變
- **沒動到的東西**: backend 全部 / DB schema / API endpoints / hooks 邏輯 / pytest

---

## 6. 開新 session 前可看的東西

| 想知道 | 看哪 |
|---|---|
| 改版後 UI 視覺語言 | 跑 `npm run dev` 自己點一輪；或看 [VA.jsx](../app/VA.jsx)（在主 repo 根目錄，不在 worktree） |
| 共用 ui 元件 API | [frontend/components/ui/index.ts](../frontend/components/ui/index.ts) 一覽匯出 |
| Theme palette（兩套色票） | [frontend/theme/themes.ts](../frontend/theme/themes.ts) |
| 改版 session 紀錄 | [work-logs/2026-05/2026-05-07-ui-revamp-calm-operator.md](../work-logs/2026-05/2026-05-07-ui-revamp-calm-operator.md) |
| 整體架構（一張圖） | [docs/architecture/windMindOM-architecture.md](architecture/windMindOM-architecture.md) |
| Work Order 11 endpoints API | `python run.py` → `http://localhost:8100/docs` workflow tag |
| Cost frontend pattern（M3 frontend 模板） | [frontend/components/CostPage.tsx](../frontend/components/CostPage.tsx) + [services/costService.ts](../frontend/services/costService.ts) |

---

## 7. 給下次 session claude 的明確 first action

```bash
# 1. 進主 repo 並切到 main
cd D:\Project_CodingSimulation\researchTopic\windMindOM
git checkout main
git pull --ff-only

# 2. 確認 backend 沒被破壞（純 frontend session 也建議跑一下）
python -m pytest modules/cost/ modules/monitoring/ modules/workflow/ -q
# 預期：257 passed + 1 xfailed

# 3. 確認 frontend 跑得起來
cd frontend
npm run dev
# 開 http://localhost:3100 看新 UI 沒事

# 4. 認領 WMOM-20260504-19，開 branch + worktree
cd ..
git worktree add .claude/worktrees/wo-frontend-{slug} -b claude/issue-20260504-19-2026-XX-XX
cd .claude/worktrees/wo-frontend-{slug}

# 5. 開 work-log
# work-logs/2026-05/2026-05-XX-workflow-frontend-orders.md

# 6. 進 routine：依本檔 §3「UI directive」遵守新元件規範
```

---

## 8. 重要決策回顧（這個 session 內）

- **Tailwind 全退**：原規劃保留作 layout utility，但實作後 0 處使用，CDN 變 dead weight 順手移除（影響 first-paint，不大但乾淨）
- **recharts 局部保留**：HistoryPage / CostPage / TrendChartPanel 互動需求高（hover / zoom / reference line）保留 recharts 但走 theme 顏色；overview / cost KPI 趨勢圖改 SVG 跟 VA.jsx 一致
- **Placeholder 按鈕保留 + WMOM-20260507-02 follow-up 追蹤**：劉老師 2026-05-07：「沒作用沒關係，開發階段，之後一個一個補」。不寫假的 alert / TODO 訊息
- **M3+ frontend issue 全加 UI directive**：避免下次 dev / Claude 接 frontend 時把 cyan dark / Tailwind 寫回去
- **單一 ui 元件庫 source of truth**：以後新元件加到 `frontend/components/ui/` + index.ts 匯出，page 級元件不可寫死樣式
