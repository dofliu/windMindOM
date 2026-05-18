# 2026-05-18 WMOM-20260510-01 Part C follow-up — frontend start_work 自動依 farm 分支

> **Issue**：WMOM-20260510-01 Part C — Frontend wiring（start_work 對話框依 farm.is_offshore 自動決定 require_weather_window + 提供 weather_window_id 綁定入口）
> **Branch**：`claude/issue-WMOM-20260510-01C-2026-05-18`
> **Base commit**：88262cf（並行 session push 的 backend-only Part C）
> **Goal**：把 issue 原本列在 Part C 但 backend-only commit 未實作的 frontend / workflow API 部分補完，完整收 Part C。

---

## 1. 為什麼今天做這個

今日 autonomous daily worker session 認領 WMOM-20260510-01 Part C 後，並行另一 session（commit 88262cf）已先 push backend-only 實作。我的工作（state_machine + WorkOrderDetailModal + WorkflowPage + workflow API schema）是 issue Part C 列出但 backend-only commit 未涵蓋的另外一半，重組成 follow-up commit 推上同一 branch 收尾 Part C。

issue Part C 原本同時包含 backend infra（is_offshore field）與 frontend wiring（start_work 對話框依 farm.is_offshore 自動分支 + offshore farm weather_window_id 綁定入口）。並行 session 完成前者，本 session 完成後者。

---

## 2. Scope 與設計決策

### 2.1 為什麼 `weather_window_id` 接到 `StartWorkRequest`（而非另外開 PATCH endpoint）

兩個方案：
- **方案 A**：start_work 前先呼叫 `PATCH /work-orders/{id}` 把 weather_window_id 寫進工單，再 start_work
- **方案 B**：直接把 `weather_window_id` 加進 `StartWorkRequest` body，state machine 在 apply 階段一併寫入工單

選了方案 B：
- 避免 frontend 兩段呼叫造成中間狀態
- workflow 既有 `start_work` 設計本來就以「一次完成」為目標
- guard 與 apply 共用同一 kwargs，邏輯內聚

### 2.2 guard 與 apply 條件必須一致（code review must-fix #1）

初版 apply 寫成「kwargs 有 ww_id 就寫入」，導致 onshore caller 偷塞 ww_id 也會污染工單欄位。code review 指出後修為：

```python
if (
    kwargs.get("require_weather_window")
    and kwargs.get("weather_window_id") is not None
):
    wo.weather_window_id = kwargs["weather_window_id"]
```

guard 與 apply 同條件：`require_weather_window=True` 才檢、才寫。補一個 regression test
`test_start_work_onshore_ignores_weather_window_id_in_kwargs` 鎖定行為。

### 2.3 WorkflowPage active farm 監聽（code review must-fix #2）

review 指出 `useEffect(..., [])` 是 mount-only，user 切 farm 後 `farmIsOffshore` 不會更新。
實際上 `FarmSelector.switchFarm` 會 `window.location.reload()`，所以下一個 mount 已抓最新值；
但為了不依賴此假設，加 `visibilitychange` 監聽，user 從別處 tab 切換 farm 回到本頁面也會重抓。

### 2.4 onshore 不送 `weather_window_id` field（code review should-fix #3）

`onStartWork` callback 在 WorkflowPage 改用 conditional spread：
```ts
...(weatherWindowId !== undefined ? { weather_window_id: weatherWindowId } : {})
```
避免依賴 `JSON.stringify` 對 `undefined` 的副作用，語意明確。

---

## 3. 檔案異動

### 3.1 Backend

```
M modules/workflow/schemas/work_order_schemas.py StartWorkRequest +weather_window_id: Optional[UUID]
M modules/workflow/routers/work_order_router.py  start_work pass weather_window_id
M modules/workflow/domain/state_machine.py       _guard_start_work（kwargs.ww_id OR wo.ww_id）
                                                 _apply_transition start_work（require_* && ww_id 才寫入）
M modules/workflow/tests/test_state_machine.py   +3 tests
M modules/workflow/tests/test_work_order_api.py  +1 test
```

### 3.2 Frontend

```
M frontend/services/workOrderService.ts          StartWorkRequest +weather_window_id?
M frontend/components/workflow/WorkflowPage.tsx  抓 active farm.is_offshore;
                                                 加 visibilitychange listener；
                                                 conditional spread weather_window_id
M frontend/components/workflow/WorkOrderDetailModal.tsx
                                                 +isOffshore prop +weatherWindowId state；
                                                 start_work form 依 isOffshore 分支
```

### 3.3 文件

```
M ISSUES.md          Part C status → 與 Part D 區分（Part C done by 並行 backend + 本 follow-up）
M STATUS.yaml        progress / last_updated / next_milestone
+ work-logs/2026-05/2026-05-18-farm-is-offshore-frontend.md（本檔）
```

---

## 4. Code review 採納（5/18 code-reviewer subagent）

跑 code-reviewer subagent 找出 **2 must-fix + 4 should-fix + 3 nice-to-have**。

### Must-fix 全採納（2/2）

1. ✅ `_apply_side_effects` start_work 階段「沒 require_weather_window 也寫 ww_id」 → 改為與 guard 一致（require_* && ww_id 都有才寫）；加 regression test `test_start_work_onshore_ignores_weather_window_id_in_kwargs`
2. ✅ WorkflowPage `farmIsOffshore` stale state → 加 `visibilitychange` listener，user tab 切換回頁面會重抓 active farm

### Should-fix（2/4 採納；2/4 n/a）

3. ✅ WorkflowPage `weather_window_id: undefined` → conditional spread，onshore 路徑不送該 field
4. ✅ `test_offshore_start_work_with_weather_window_id_in_body_passes` dispatch 沒 assert status → 加 `assert dispatch_resp.status_code == 200`
- ⏭ `_migrate_schema` 吞 OperationalError → **n/a**（並行 session 已用 `PRAGMA table_info` 偵測缺欄，不再用 try/except）
- ⏭ `field_map` `Dict[str, tuple[str, str]]` typing 不一致 → **n/a**（並行 session 用更簡單的 `dict[str, str]` + inline 分支）

### Nice-to-have（1/3 採納）

5. ⏭ Input autoFocus → 嘗試後發現 UI 元件庫 `Input` 沒此 prop，加上會擴展 prop interface 影響範圍；改修一個更嚴重的 bug：原本 `onChange={e => setWeatherWindowId(e.target.value)}` 違反 Input 的 `onChange(value: string)` 慣例（會把 weatherWindowId 設成 undefined），改回 `onChange={setWeatherWindowId}` + `ariaLabel`（camelCase）
6. ⏭ 每次實例化都跑 schema migration → 既有設計只在 `_init_db` 跑，量不大，留作未來 polish
7. ✅ label `'Weather window ID (UUID)'` → 改 `'Weather window ID (required)'`，避免暴露 UUID 技術名詞給現場工程師

---

## 5. Verify

- **Backend pytest**：551 passed + 1 xfailed（並行 session baseline 547 + 本 follow-up 新增 4 個 test，全綠）；3 條 numpy 精度漂移 pre-existing 環境問題
- **Frontend `tsc --noEmit`**：zero error
- **Frontend `vite build`**：成功（737 modules / 862 KB bundle）

---

## 6. Notes / 後續

- Part D（farm 設定 UI checkbox）下次 session 補完即可收滿 WMOM-20260510-01 全 4 part
- weather_window CRUD（dropdown 取代 UUID 貼上）排 M5+
- 本 follow-up commit 與並行 session backend commit 同 branch 共構成完整 Part C
