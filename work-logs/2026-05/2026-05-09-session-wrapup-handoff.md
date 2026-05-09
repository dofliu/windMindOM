# 2026-05-09 Session Wrap-up + Handoff

> 給下次 session（2026-05-10+）從 main 接手用的 quick-start handoff。
> 本 session 一日推完 M4 backend 5 issue + code review fixes — backend 全收。

---

## 1. 今日完成（2026-05-09）

| ID | 名稱 | PR | Tests |
|---|---|---|---|
| WMOM-20260509-M4-planning | 10 個 sub-issue 寫進場 | #16 | — |
| WMOM-20260509-01 | A1 Inventory + MaterialRequest **domain** | #17 | 60 |
| WMOM-20260509-02 | A2 Repository + **atomic dispatch** (M4 核心) | #18 | 58 |
| WMOM-20260509-03 | A3 MaterialRequest **API + signoff 整合** | #19 | 27 |
| WMOM-20260509-04 | A4 **Inventory API** | #20 | 28 |
| WMOM-20260509-05 | A5 **Cost ledger 整合** (estimated → confirmed) | #21 | 32 |
| WMOM-20260509-review-fixes | code review 3 must-fix 修正 | (本 PR) | 11 |
| **小計** | | **7 PRs** | **216** |

**M4 backend 100% 完工**：33 endpoints + 完整 lifecycle 鏈路就位。
**M4 milestone progress: 5% → 65%。**

---

## 2. 完整 lifecycle 鏈路（已 acceptance test 過）

```
建料件 (unit_cost=450) →
建工單 →
建 MR linked to WO (qty=2) →
submit + 3 階 approve (employee/leader/treasury, auto dispatch) →
✓ ledger entry [estimated, amount=900, locked_unit_cost=450, source_item_id=mr_item.id]
✓ stock 扣 (10 → 8) →
[供應商漲價：unit_cost 450 → 600] ← review fix #1 場景
receive (actual_qty=2) →
finish WO →
✓ A5 hook: ledger entry [confirmed, amount = 2 × 450 = 900 (用 locked_unit_cost), confirmed_at filled]
                                    ↑ 不是 2 × 600 = 1200，會計做帳一致
```

---

## 3. 從 main 接手的快速指南

### 3.1 main 狀態確認

```bash
cd D:\Project_CodingSimulation\researchTopic\windMindOM
git status            # 應該 clean
git log --oneline -10 # 看最近 commits
git branch -a         # 應該只剩 main + 1 個 review-fixes branch（或全清）
```

### 3.2 跑一次完整測試確認本地 OK

```bash
python -m pytest modules/workflow/tests/ modules/cost/tests/
# 應該看到: 446 passed, 1 xfailed in ~25s
```

### 3.3 開新工作 branch 從 main

```bash
git checkout main && git pull origin main
git checkout -b claude/issue-WMOM-20260509-XX-2026-05-10
```

---

## 4. 下次 session 候選工作（建議優先級排序）

### 主軸選項

| 選項 | 描述 | 估時 | 為什麼 |
|---|---|---|---|
| **A6** | `/admin/workflow/material` 領料單 frontend | 1d | 33 個 backend endpoints 已 ready，frontend 接最直接 |
| **A8** | Reporting backend (monthly_report.py PDF) | 1.5d | 收尾 backend；A5 ledger summary 已就緒可直接拼月報；M6 demo killer feature |
| **A7** | `/admin/workflow/inventory` 庫存 frontend | 0.5-1d | 與 A6 同 pattern，可一起做 |

**個人建議**：先 A8 reporting backend（與 frontend 平行可進行），然後 A6+A7 frontend 一起做（共用 ui 元件）。理由：
1. 月報 PDF 是 M6 客戶 demo 的最大亮點，越早做完越早 demo
2. A6/A7/A9 三個 frontend 用同一套 UI directives，一起做避免重複決策

### Follow-up 小任務（可插）

| ID | 名稱 | 估時 | 從哪來 |
|---|---|---|---|
| WMOM-20260509-F1 | `add_return` 寫 ledger 沖銷 | 0.5d | code review |
| WMOM-20260509-F2 | `func.count` SQL-side count | 0.5h | code review |
| WMOM-20260509-F3 | `list_warehouses` repo method | 0.5h | code review |
| WMOM-20260509-F4 | shared `FARM_REGISTRY` provider | 1h | code review |
| WMOM-20260509-F5 | `InventoryAdjustmentLog.actor_id` Optional | 15m | code review |
| WMOM-20260509-F6 | PostgreSQL row-lock integration test | 0.5d | M6 部署前 |

---

## 5. 目前 main 狀態（測試入口給劉老師）

從 main 啟動 backend 測試 lifecycle：

```bash
# Terminal 1: 啟 backend
python run.py
# → http://localhost:8100 (FastAPI)
# → Modbus TCP server on port 5020

# Terminal 2: 啟 frontend (沒新 frontend 但 backend 可單獨用 Swagger 測)
cd frontend && npm run dev
# → http://localhost:5179 (Vite dev server)
```

打開 **Swagger UI**: http://localhost:8100/docs

可以 manual 跑 lifecycle：
1. `POST /api/farms` — 建 farm（如已存在 default farm 跳過）
2. `POST /api/workflow/warehouses?farm_id=...` — 建 warehouse
3. `POST /api/workflow/inventory` — 建料件
4. `POST /api/workflow/work-orders` — 建工單 → `dispatch` → `start-work`
5. `POST /api/workflow/material-requests` — 建 MR linked to WO
6. `POST /api/workflow/material-requests/{id}/submit-for-approval` → 自動建 chain
7. `GET /api/workflow/approvals/pending?level=employee/leader/treasury` → 3 階 `POST /approve` 完成
8. → MR 自動進 DISPATCHED + ledger estimated entry 寫入
9. `POST /api/workflow/material-requests/{id}/receive` 填 actual_qty
10. `POST /api/workflow/work-orders/{id}/finish` → ledger confirmed
11. `GET /api/cost/ledger?farm_id=...&status=confirmed` 看月度成本

或更簡單：跑 lifecycle test 直接看完整流程：

```bash
python -m pytest modules/workflow/tests/test_lifecycle_ledger_confirmation.py -v
```

---

## 6. 重要文件（從 main 接手必讀）

| 檔案 | 為什麼 |
|---|---|
| `CLAUDE.md` | 工作守則、repo 角色、commit 規範 |
| `STATUS.yaml` | 目前 progress / next milestone |
| `ISSUES.md` | M4 sub-issues + F1-F6 follow-up |
| `docs/product/ROADMAP.md` | M4-M6 整體 roadmap |
| `docs/design-notes/m3/DN-03-inventory-material-request.md` | inventory + MR 設計依據 |
| `work-logs/2026-05/2026-05-09-*.md` | 今日 5 個 backend issue 詳細 work log |

---

## 7. 重點設計決策（給下次 session 參考）

從今日 5 個 issue + review fixes 累積的關鍵設計決策：

1. **Atomic dispatch 雙寫**（A2）：cost_ledger 共用 workflow Base，必要才能同 transaction 寫多表
2. **`source_item_id` + `locked_unit_cost`**（A2 + review fix）：讓 confirm flow 用 dispatch 當下的快照算 amount，會計做帳要求
3. **不暴露 ledger POST/PATCH**（A5）：事實帳本所有 mutation 必須走業務 atomic transaction
4. **`MATERIAL_REQUEST` reject → REJECTED 終態**（A3，與 work_order「reject 回 IN_PROGRESS」不同）：DN-03 設計，operator 須建新 MR
5. **`InvalidTransition.reason` 屬性**（review fix）：精確 status code mapping，不依賴字串匹配
6. **`set_finish_hook_db_path` 改 dict**（review fix）：multi-farm safe
7. **lazy import 解循環**（A5）：material_request_repository 對 cost_ledger 改 lazy；cost_ledger_repository 對 workflow.repository 改 lazy

---

## 8. 個人建議

下次 session 開工 5 分鐘 routine：

```
1. cd windMindOM && git status (clean)
2. python -m pytest modules/workflow/tests/ modules/cost/tests/ (446 pass)
3. cat ISSUES.md | grep -A 1 "Status\\*\\*: open" | head -20  (看 open issues)
4. 決定 A6 / A7 / A8 / F1 開工
5. git checkout -b claude/issue-WMOM-...
6. 開做
```

A6 frontend 開做要用 WMOM-20260507-01 的 ui 元件庫（Card / Btn / PageHeader / StatusPill / Field / Input / Select），不可寫 Tailwind / 硬寫 hex。可參考 `frontend/components/workflow/WorkflowPage.tsx` 既有 pattern。

---

**今日 session 結束。從 main 接手 OK。下次見。**
