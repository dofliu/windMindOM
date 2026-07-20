# 2026-07-19 — 修「調閱過去情境讀錯 DB」+ 收 #140 review｜WMOM-20260719-05

> Session 類型：#140 merged 後的 follow-up（code review 在合併後才回，抓到 Must-fix）
> 產出：本 PR（select_view_only storage 修正 + #140 review 的 should-fix/nice-to-have）
> 對應 issue：WMOM-20260719-05（follow-up of WMOM-20260719-04 / #140）

---

## 為什麼有這個 PR

#140（啟動 gate）合併**後**，code-reviewer 才回報，抓到一個 **Must-fix**：`select_view_only()`
（「調閱過去情境」路徑）從未把 `broker.storage` 重指向 active farm 的 DB——`DataBroker.__init__`
的 `Storage()` 綁預設 legacy 路徑，只有 `start()`/`_init_farm_storage()` 會重指。**改動前**開機必
`broker.start()` 所以早已重指；改成開機 idle 後，若第一個動作就是 view，`broker.storage` 就停在
legacy → `list_scenarios()`/`get_history` 全讀到空的錯 DB → **情境清單空掉**（正是 #4 要修的「情境
調不回來」以新根因重現）。#140 已 merged，故走 follow-up fix PR（非 reopen）。

## 做了什麼

- **Must-fix**：`select_view_only()` 加 `if self._active_farm_id is None: self._init_farm_storage()`
  （idempotent，`CREATE TABLE IF NOT EXISTS`）→ view 後 storage 指向 active farm DB。
  - 回歸測試 `test_view_only_reads_active_farm_scenarios`：在 farm DB 塞情境 → 全新 broker view →
    斷言 `storage._db_path == farm_db` 且 list 得回該情境（**會因舊 bug fail**）。
  - app-level e2e verify：boot=legacy → view-select 後 = `data/farms/legacy/wind_farm.db` ✔。
- **Should-fix**：
  - `test_source_selection` fixture 不再手動覆蓋 `.storage`（原本遮蔽了上面的 bug）+ 改
    `FarmRegistry(data_dir=tmp_path)` 隔離（比照 test_farm_registry_is_offshore 慣例）。
  - `/api/source/select` 的 `live` 比照 farm-activate 需 SUPERVISOR——**enforce 開時**才強制
    （`is_auth_enforced()` 守門；enforce 關的過渡期維持開放、不破壞 no-token 操作）。+authz 測試。
  - 前端 gate 狀態機抽成 `hooks/useSourceGate.ts`（可測）+ **登出防呆**（登出 true→false 不重查
    status，否則 enforce 下 401 會把主動登出誤標成 session 過期）。+6 hook 測試（status 三態 /
    selectMode 成敗 / 登出不重查）。
- **Nice-to-have**：`/api/health` 加回 `sourceActive` / `sourceKind`（idle 期 `mode` 會誤導）。

## 卡在哪 / 下次怎麼接手

- **本 PR**：draft + `hold`（本次無另跑 review——變更皆為 reviewer 已明列的修正 + 對應測試；
  backend 98 / 前端 919 / tsc / build / e2e 全綠）。CI 綠 → 移除 hold → flywheel 自動合。
- 仍未收的 #140 nice-to-have（皆非阻塞、可另案）：`activate_*` 用 `asyncio.to_thread` 避免阻塞
  event loop；view 模式隱藏註定 400 的 nav（Faults/Settings）；`settings.dataSource`(MOCK) 與新
  gate 的一致性校正。
