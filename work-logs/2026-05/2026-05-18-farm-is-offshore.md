# 2026-05-18 WMOM-20260510-01 Part C+D — Farm `is_offshore` 欄位

> **Issue**：WMOM-20260510-01 Part C + Part D — farm `is_offshore` field + 設定頁 checkbox
> **Branch**：`claude/issue-WMOM-20260510-01CD-2026-05-18`
> **Goal**：M5 demo polish 第三+四步 — 把「離岸/陸上」從 frontend hardcoded `false` 移到 farm config，
> `start_work` 對話框依 farm 屬性自動決定是否要求 weather_window，並在新建風場 modal 加 offshore toggle。

---

## 1. 為什麼今天做這個

依 2026-05-15 Part B 收尾的 handoff 建議：「下次候選：Part C farm `is_offshore` field（0.5d）+ Part D farm 設定 UI checkbox（0.5d）以收滿 WMOM-20260510-01 全 4 part」。

5/10 hotfix 把 `start_work` 的 weather_window checkbox 拿掉（反向 UX — user 不該被問「這是不是離岸風場」）並留下註解「等 Part C 加 farm.is_offshore 後再加回」。今日把這個 IOU 還清。

合併 Part C + D 為一個 PR 的理由：兩者緊耦合 — Part C 純改 schema/API 但若 UI 沒切 checkbox 入口，就只能靠 PATCH /api/farms/{id} 手動測；Part D 在 UI 上沒接 backend 等於 dead control。一起做有完整 end-to-end demo path（建風場 → 勾 offshore → 工單 start_work 自動觸發 offshore 流程）。

---

## 2. Scope 與設計決策

### 2.1 Migration 策略

既有 SQLite `farms` table 沒有 `is_offshore` 欄位。新建 DB（`CREATE TABLE IF NOT EXISTS`）會帶新欄位；既有 DB 需要 `ALTER TABLE ADD COLUMN`。

採 PRAGMA table_info 檢查 column 存不存在的標準 SQLite migration pattern，放在 `_init_db()` 內保持冪等。

`is_offshore` 預設 `0`（onshore），既有 3 個 farm 自動帶 false — 符合 issue 描述「既有 3 個 farm 預設 false（劉老師 demo 用陸上）」。

### 2.2 為什麼不做 weather_window 完整 registry

issue spec 寫「Offshore：要求 user 先綁 weather_window_id（M3 設計但 frontend 沒接 — 此 issue 一併補上）」。

但實際 grep 後發現：
- 後端沒有 `weather_windows` table / endpoints — `weather_window_id` 只是 work_orders table 上的 UUID 欄位
- M3 設計確實留了 `weather_window_id`，但沒有 weather_window source-of-truth
- 完整 weather_window registry（建立 / 查詢 / 綁定 / 過期管理）至少另開一個 1-1.5d issue

權衡：今日不擴大到完整 registry，而是在 offshore `start_work` 對話框：
1. 顯示「此風場為離岸風場，需綁定 weather window」提示
2. 提供 UUID input 欄位讓 user 手動貼上 weather_window_id（demo 用 placeholder UUID）
3. 後端 state machine 早已支援 `require_weather_window=True` + 檢查 `wo.weather_window_id` 是否已綁

這樣 offshore code path 可被完整測試，full registry 留作 WMOM-20260518-XX follow-up（明確開新 issue 不在本 PR）。

### 2.3 weather_window_id 從哪來

兩個選項：
- **A**：start_work 對話框讓 user 輸入 UUID（pain — 4 個 fixture UUID 給 demo 用）
- **B**：start_work 對話框先呼叫 work order PATCH 寫入 weather_window_id，再 start_work

選 A 的擴張版：input + 「使用 demo placeholder UUID」快捷按鈕。理由：
- 暫沒 PATCH /api/workflow/work-orders/{id} 可改 weather_window_id（M3 設計留了欄位但沒 update endpoint）
- 為 demo 加 PATCH 屬於 scope 蔓延
- demo 用：placeholder UUID `00000000-0000-0000-0000-000000000099` 走完 chain 即可

實作上：start_work onClick handler 先確認 weather_window_id 有值（若 wo 上沒綁，從 input 取），用「綁定後 start_work」的 backend 還沒有 PATCH endpoint — 怎辦？

→ **修正方案**：在 backend 加 `start_work` 接受 optional `weather_window_id` 一次設好。這比起加一個全新 PATCH endpoint 範圍小很多，也符合 state machine 的「transition with side data」設計。

### 2.4 為什麼把 weather_window_id 塞進 start_work payload

state machine `start_work` transition 目前已支援 `require_weather_window` kwarg；既有 work order 若沒綁 `weather_window_id` 直接 raise。

但 user flow 是「開啟 start_work 對話框 → 看到 offshore farm → 選一個 weather window」— 在同一個動作裡。讓 `StartWorkRequest` 額外接 `weather_window_id` 欄位，state machine 在開檢查前先把欄位寫到 wo 上，就能達到「同一個 click 完成綁定 + 啟動」。

backend 變動：
- `StartWorkRequest` schema：加 optional `weather_window_id: UUID | None`
- `state_machine.start_work`：若 kwargs 有 `weather_window_id`，先寫 `wo.weather_window_id`；再做 require_weather_window 檢查

---

## 3. 檔案異動（規劃）

### 3.1 Backend 新增

無新檔案。

### 3.2 Backend 修改

```
M modules/monitoring/server/farm_registry.py
  - FarmConfig：加 is_offshore: bool = False
  - to_dict() 自動帶
  - from_row() 加讀 is_offshore（int 0/1 → bool）
  - _init_db()：加 ALTER TABLE 冪等 migration
  - create_farm()：accept is_offshore param + INSERT 帶進去
  - update_farm()：field_map 加 is_offshore

M modules/monitoring/server/routers/farms.py
  - POST /api/farms：accept body.is_offshore
  - PATCH /api/farms/{id}：透傳 is_offshore

M modules/workflow/schemas/work_order_schemas.py
  - StartWorkRequest：加 optional weather_window_id: UUID | None

M modules/workflow/domain/state_machine.py
  - start_work：若 kwargs 有 weather_window_id 先寫到 wo

M modules/workflow/routers/work_order_router.py
  - start_work endpoint：透傳 weather_window_id
```

### 3.3 Backend 新增測試

```
+ modules/monitoring/tests/test_farm_registry.py
  - test_create_farm_default_onshore
  - test_create_farm_explicit_offshore
  - test_update_farm_toggle_offshore
  - test_legacy_db_migration_adds_is_offshore（重點 — ALTER TABLE 冪等性）

修改：
M modules/workflow/tests/test_state_machine.py
  - test_start_work_with_weather_window_id_payload — start_work 同步綁 weather_window_id
M modules/workflow/tests/test_work_order_api.py
  - test_start_work_offshore_binds_weather_window_in_one_call
```

### 3.4 Frontend 修改

```
M frontend/services/workOrderService.ts
  - FarmInfo interface：加 is_offshore: boolean
  - StartWorkRequest type：加 weather_window_id?: string

M frontend/components/FarmSelector.tsx
  - Farm interface：加 is_offshore?: boolean
  - CreateFarmModal：加「離岸風場」checkbox（Part D）
  - POST body 透傳 is_offshore

M frontend/components/workflow/WorkflowPage.tsx
  - fetchFarms 完後存 active farm 的 is_offshore 到 state
  - 傳 isOffshore prop 給 WorkOrderDetailModal

M frontend/components/workflow/WorkOrderDetailModal.tsx
  - 加 isOffshore prop
  - start_work 對話框：
    - onshore：保留現行（require_weather_window=false 直送）
    - offshore：顯示 weather_window_id 提示 + input + 快捷 placeholder button
  - onStartWork callback type 加 weather_window_id 參數

M frontend/services/workOrderService.ts → wo.startWork API
  - StartWorkRequest 透傳 weather_window_id

M frontend/components/workflow/WorkflowPage.tsx 的 onStartWork callback
  - 把 weather_window_id 透到 wo.startWork
```

### 3.5 ISSUES.md / STATUS.yaml

- ISSUES.md WMOM-20260510-01：Part C done / Part D done / 整個 issue 標 done
- STATUS.yaml：progress / last_updated / next_milestone

---

## 4. TODO（implementation checklist）

- [x] Read 既有 FarmConfig / farms_router / WorkflowPage / WorkOrderDetailModal
- [x] Backend：FarmConfig + migration + farms_router POST/PATCH
- [x] Backend：start_work 接受 weather_window_id payload
- [x] Backend：新增 test_farm_registry.py + state_machine offshore test
- [x] Backend：pytest zero regression（504+1 baseline + 4 new test = 508 passed）
- [x] Frontend：FarmInfo + StartWorkRequest types
- [x] Frontend：CreateFarmModal is_offshore checkbox
- [x] Frontend：WorkflowPage 抓 active farm is_offshore
- [x] Frontend：WorkOrderDetailModal start_work offshore branch
- [x] Frontend：tsc --noEmit + vite build zero error
- [x] code-reviewer subagent：採納 must-fix
- [x] 更新 STATUS.yaml + ISSUES.md
- [x] commit + push + PR

---

## 5. Code review 採納

Code-reviewer subagent 找出 **2 must-fix + 3 should-fix + 2 nice-to-have**。

**Must-fix 全採納（2/2）**：
1. ✅ `clone_farm` 沒傳 `is_offshore` — 此 PR 直接引入的 regression（clone offshore farm 結果是 onshore）。已修：`create_farm(...)` 加 `is_offshore=source.is_offshore` + 新 test `test_clone_farm_preserves_is_offshore`。
2. ✅ `WorkflowPage` `farmIsOffshore` stale after farm switch — useEffect 空 dep array 只 mount 一次跑；雖然 FarmSelector 切 farm 會 `window.location.reload()`，但 PATCH 帶外修改或 hot-update 仍有風險，且此 PR 讓 stale state 從「顯示問題」升格為「行為問題」（require_weather_window 傳錯值）。已修：抽 `fetchActiveFarm` callback，selectedWO 開啟時重抓。

**Should-fix 全採納（3/3）**：
3. ✅ PATCH `/api/farms/{id}` body `{"is_offshore": "false"}` 走 Python truthiness `bool("false")=True` 會把陸上誤設成離岸。已修：`update_farm` 加 `isinstance(val, bool)` 強制 check + raise TypeError；farms_router PATCH 加 422 guard + 新 test `test_update_farm_is_offshore_rejects_non_bool_string`。
4. ✅ Frontend weather_window_id 缺 UUID 格式 inline validation — 後端 Pydantic 422 之前不會即時回饋。已修：start_work 對話框加 RFC 4122 regex 即時 check，無效時顯示警告 + disable confirm button。
5. ✅ `FarmSelector` 私有 `Farm` interface 與 `workOrderService.FarmInfo` 並存，is_offshore 兩處維護易分歧。已修：`type Farm = FarmInfo` import shared type。

**Nice-to-have 暫不採納（0/2）**：
- ⏭ Nice-to-have 1（legacy schema test 也帶 `is_active` — 已 default 0 不影響）：純測試精確度，行為正確。
- ⏭ Nice-to-have 2（`canConfirm`/`bindId` 計算邏輯抽 const）：實作上已用 IIFE wrap 提供 derived const（canConfirm/needsWindow/inlineUuidError/trimmed），可讀性已 OK。

---

## 6. 環境 baseline note

開工時 sandbox 內 5 條 pytest fail 為 pre-existing 環境問題（numpy 2.4.5 太新導致 floating-point 精度漂移 + concurrent dispatch test 偶發 flake）：

- `test_concurrent_dispatch_same_item_serialized_correctly`
- `test_concurrent_dispatch_one_loses_when_stock_short`
- `test_monte_carlo_k13_seed_42`
- `test_mc_percentiles_pinned`
- `test_varfluct_year_1_pinned`

baseline `504 passed, 1 xfailed` 仍符合預期。本 PR 不引入新 regression — verify 時觀察這 5 個維持原狀即可。
