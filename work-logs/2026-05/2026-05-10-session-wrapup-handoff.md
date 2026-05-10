# 2026-05-10 Session Wrap-up + Handoff

> 給下次 session（2026-05-11+）從 main 接手用的 quick-start handoff。
> 本 session 是「**M4 客戶 demo flow 完整貫通日**」— 從早上 main 開始 →
> A8 backend → A9 frontend → 多輪 hotfix → 端到端 lifecycle 全打通可演。

---

## 1. 今日完成（2026-05-10）

| ID / Type | 名稱 | PR | Tests / Build |
|---|---|---|---|
| **A8** WMOM-20260509-08 | Reporting backend (monthly PDF + annual budget) | [#23](https://github.com/dofliu/windMindOM/pull/23) merged | 502 + 56 reporting |
| **A9** WMOM-20260509-09 | Reports frontend (`/admin/reports`) | [#24](https://github.com/dofliu/windMindOM/pull/24) merged | tsc 0 / vite 5.29s |
| **Hotfix** CORS + table collision | digiWT/WMOM `work_orders` 撞名 + CORS spec violation | [#25](https://github.com/dofliu/windMindOM/pull/25) merged | 502+1 |
| **Hotfix** Dispatch + assignee | dispatch 接受 kwargs assignee_id | [#26](https://github.com/dofliu/windMindOM/pull/26) merged | 504+1 |
| **Hotfix** weather_window UX | 拿掉 start_work checkbox + 開 WMOM-20260510-01 | cherry-picked 9c8f476 | tsc 0 / vite 6.06s |
| **Tool** | `tools/repair_workflow_schema.py` dev 修復工具 | (in #25) | — |

**累計**：4 PR + 1 cherry-pick / 504 backend tests + frontend build clean / 零 regression。

**重要里程碑**：M4 客戶 demo flow **端到端完整貫通**，劉老師實測 5 種 path 全 pass：
- ✅ 建工單 → 派工 → 開始作業 → 進度紀錄 → 完工
- ✅ 員工簽核（1 階通過）
- ✅ 組長簽核（2 階通過）
- ✅ 組長駁回 → 工單退回 IN_PROGRESS → 重新完工 → 重建簽核 chain
- ✅ 多張工單並行（CORRECTIVE + PREVENTIVE 兩類型）
- ✅ `/admin/reports` 月報生成 → KPI + iframe HTML preview + PDF download

---

## 2. main 狀態（2026-05-10 收工）

```bash
$ git log --oneline -5
9c8f476 hotfix: remove weather_window checkbox + open WMOM-20260510-01 (...)
ab7ef0e Merge pull request #26 from dofliu/claude/hotfix-dispatch-assignee-2026-05-10
6ee9716 hotfix: dispatch flow accepts assignee_id at dispatch time
f792066 Merge pull request #25 from dofliu/claude/hotfix-cors-and-schema-2026-05-10
b95eef6 hotfix: fix CORS preflight + work_orders table name collision
```

```bash
$ python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/
504 passed, 1 xfailed (zero regression)

$ cd frontend && npx tsc --noEmit && npx vite build
0 errors, 6.06s, 733 modules
```

**所有 PR branch 已刪除（local + remote），只剩 main。**

---

## 3. 下次 session 接手快速指南

### 3.1 開工 5 分鐘 routine

```bash
cd D:\Project_CodingSimulation\researchTopic\windMindOM
git status                                    # 應該 clean
git checkout main && git pull origin main     # 同步最新
python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/
# 應該看到 504 passed, 1 xfailed in ~25s
```

### 3.2 啟動 backend + frontend 完整 demo

```bash
# Terminal 1: backend
python run.py
# → http://localhost:8100 (FastAPI)
# → Modbus TCP on port 5020

# Terminal 2: frontend
cd frontend && npm run dev
# → http://localhost:3100 (Vite dev server)
```

打開 http://localhost:3100，左側選單可看到：
- 工單管理（建單 → 派工 → 完工 → 簽核全 lifecycle）
- 報表（月報 + 年度預算 PDF）
- 其他 monitoring / cost / history 頁

---

## 4. 下次工作候選（建議優先級排序）

### 主軸選項（M4 收尾）

| 選項 | 描述 | 估時 | 為什麼 |
|---|---|---|---|
| **A6** | `/admin/workflow/material` 領料單 frontend | 1d | 33 個 backend endpoints ready；可參考 ReportsPage pattern |
| **A7** | `/admin/workflow/inventory` 庫存 frontend | 0.5-1d | 與 A6 同 pattern |
| **A10** | E2E lifecycle test (pytest 兩層) | 1-1.5d | **避免今日這種 hotfix 風暴重演**；ROADMAP M4 acceptance |

### 中期重要（M5 demo polish）

| ID | 名稱 | 估時 | 為什麼 |
|---|---|---|---|
| **WMOM-20260510-01** | Identity / dev mode + mock login + farm `is_offshore` | 2-3d | M6 客戶 demo 看到 `00000000-...0001` placeholder 不專業 |

### Follow-up 小任務（可插）

| ID | 名稱 | 估時 |
|---|---|---|
| WMOM-20260509-F1 | `add_return` 寫 ledger 沖銷 | 0.5d |
| WMOM-20260509-F2 | `func.count` SQL-side count | 0.5h |
| WMOM-20260509-F3 | `list_warehouses` repo method | 0.5h |
| WMOM-20260509-F4 | shared `FARM_REGISTRY` provider | 1h |
| WMOM-20260509-F5 | `InventoryAdjustmentLog.actor_id` Optional | 15m |
| WMOM-20260509-F6 | PostgreSQL row-lock integration test | 0.5d |

**個人建議排序**：A10 → WMOM-20260510-01 → A6+A7 → F1-F6
- **A10 第一**：今日 hotfix 風暴源於沒有 lifecycle E2E test；先補上避免下次重演
- **WMOM-20260510-01 第二**：mock login + is_offshore 是 demo polish 必備
- **A6/A7 第三**：領料庫存 frontend 完整 M4 frontend
- **F1-F6 隨手清**：每個都很小，session 末尾插一個進去

---

## 5. 重要設計決策（今日新加，下次參考）

### 5.1 `wmom_` table prefix（hotfix #25）

WMOM workflow ORM 表全部用 `wmom_` prefix（目前只 rename 了 `wmom_work_orders`）避免跟 digiWT legacy `monitoring/server/storage.py` 撞名：

```python
class WorkOrderORM(Base):
    __tablename__ = "wmom_work_orders"  # ← 不是 "work_orders"
```

未來若 storage.py 加新表（material_requests / inventory 之類）撞名時，同 pattern 處理 — 別動 storage.py legacy 表。

### 5.2 Dispatch flow 雙來源 assignee_id（hotfix #26）

`dispatch` transition guard 接受 assignee 從 2 來源任一：

```python
def _guard_dispatch(wo, actor_id, kwargs):
    if wo.assignee_id is None and kwargs.get("assignee_id") is None:
        raise InvalidTransition("dispatch requires assignee_id (set on work order or pass in dispatch request)")
```

UX：建單 wizard 第 3 步 assignee 留空 → 派工時補帶（更符合運維廠商實際工作流）。

### 5.3 CORS 配置（hotfix #25）

`monitoring/server/app.py` CORS 不可用 `allow_origins=["*"] + allow_credentials=True`（W3C spec 衝突），必須列舉明確 origins。支援 `WMOM_CORS_ORIGINS` 環境變數覆寫。

### 5.4 Weather window 暫時繞掉（hotfix 9c8f476）

`start_work` dialog 拿掉「需檢查氣象窗（離岸風場）」checkbox，永遠送 `false`。等 WMOM-20260510-01 Part C 加 farm `is_offshore` field 後再加回（自動依 farm 屬性決定）。

---

## 6. 今日 hotfix 風暴的教訓

從早上 A8 PR merge → 中午 A9 PR merge → 下午連環 4 個 hotfix（#25 / #26 / cherry-pick / 設計討論）— **如果之前有 A10 E2E lifecycle test，這些 bug 會在 PR 之前就被抓到**：

1. CORS bug：E2E test 從 `localhost:3100` 打 `localhost:8100` 立刻會撞
2. work_orders table 撞名：E2E 開新 farm 跑 lifecycle 會直接 500
3. Dispatch assignee_id：E2E 跑「建單 → 派工」會撞
4. Weather window：E2E 跑「派工 → 開始作業」會撞

**強烈建議下次 session 第一件事就是 A10 E2E lifecycle test。**

---

## 7. ISSUES.md 異動

- **WMOM-20260509-08 / -09** 標 done
- **新加 WMOM-20260510-01**（M5）：Identity / dev mode + mock login + farm is_offshore
- issue_stats: open 21 / done 31

---

## 8. 重要文件入口（從 main 接手必讀）

| 檔案 | 為什麼 |
|---|---|
| `CLAUDE.md` | 工作守則、repo 角色、commit 規範 |
| `STATUS.yaml` | 目前 progress / next milestone |
| `ISSUES.md` | M4 sub-issues + 新 WMOM-20260510-01 + F1-F6 follow-up |
| `docs/product/ROADMAP.md` | M4-M6 整體 roadmap |
| **此檔** | 今日 wrap-up + 接手指南 |
| `work-logs/2026-05/2026-05-10-*.md` | 今日 4 個 PR 的詳細 work log |

---

## 9. 個人感想

今日節奏緊湊但有節奏：
- **早上**：A8 reporting backend 一氣呵成（cleanup phase 很乾淨）
- **下午**：A9 frontend 接 A8（review fix 11 條全修）
- **傍晚**：劉老師實測踩到一連串問題 — CORS、schema 撞名、dispatch guard、weather UX
- **每一個都修到 root cause**（不是表面 patch）— 而且都附帶 regression test 或 follow-up issue

最有價值的不是修了多少 bug，而是劉老師「沒登入怎麼知道 actor 是誰」這個問題逼出 WMOM-20260510-01 整個 identity story — 那是 M6 客戶 demo 真正的 polish 關鍵。

---

**Session 結束。M4 demo flow ready，下次見。**
