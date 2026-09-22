# 2026-09-22 — 情境比較分析 A2 Part 1：跨情境摘要比較端點（WMOM-20260922-03）

**Owner**: Claude (autonomous worker, 3-hourly session)
**分支**: `claude/inspiring-mccarthy-p37yvc`
**Issue**: WMOM-20260922-03

## 1. 背景 / 為什麼挑這個

Preflight 確認 baseline 綠（backend 1094 passed / 7 skipped / 1 xfailed；frontend 961 passed /
tsc 0 / build OK，與 main 最新狀態一致，無 regression）。`git ls-remote --heads origin 'claude/*'`
只看到本 session 自己的注入分支，代表上一輪（WMOM-20260922-02，PR #160）已被人工合併進 main、乾淨
收尾。依決策樹逐項核對：

1. baseline regression — 無。
2. CI 飛輪本身壞掉 — TODO.md / STATUS.yaml 已記載 CI runner 基礎設施帳號/組織層級問題持續中，非本
   repo 可修，且已充分留言記錄，不重複診斷。
3. M6 critical path：WMOM-20260720-04/-08（live/OPC 硬化）已於今日稍早合併完成，M6 現場部署唯一
   硬阻塞已清除。剩 WMOM-20260716-06（footprint CPU-torch pin）與 WMOM-20260509-F6（PostgreSQL
   row-lock）皆卡 docker daemon 不可用（本 sandbox 有 docker client 但無 daemon，`docker info` 會
   卡死或報錯），HTTPS 部署配置需先定部署目標/憑證策略——三者皆非本 session 可動。
4. 情境比較分析 epic（DEC-20260720-02）：A0（摘要端點，#148）、A1（同情境內比較，#150 + round-2
   follow-up #157）皆已 merged。`STATUS.yaml` 標注「下次接手：續 A2 跨情境比較（相對時間對齊）/
   PR C（需先寫 broker 子設計）」。PR C 依賴未寫的 broker 子設計，範圍不明；A2 的設計決策在
   decision_log.md DEC-20260720-02 已寫清楚（相對時間對齊用 `sim_start`、指標集比照 A0、raw 表 +
   時間窗事件），選 A2。

**範圍取捨**：A2 完整範圍是「後端對齊端點 + 前端（摘要並排長條/雷達 + 相對時間對齊時序疊圖 + 差異
圖）」——這是一個橫跨後端聚合、時間對齊演算法、前端多情境選擇 UI、疊圖繪製的大功能，不適合塞進單一
autonomous session（且沒有既有前端「選多個情境比較」UI 可以掛，需要新設計）。比照 A0 → A1 的既有
節奏（A0 先做純後端摘要端點、可獨立驗收，A1 才接前端），本 session 只做 **A2 Part 1：跨情境「摘要
並排」後端端點**——這部分不需要新的資料層工作（重用 A0 的 `_load_scenario_summary`），設計無歧義，
單 session 可完工且獨立可驗收。「相對時間對齊的時序疊圖 + 差異圖」（A2 Part 2）留給下個 session，
到時候有了摘要並排端點也才好抓「該疊哪幾條線」的候選情境。

## 2. 實作

### 2.1 `modules/monitoring/server/routers/scenarios.py`

- 新增 `GET /api/scenarios/compare?ids=1,2,3` 端點（`compare_scenarios`），回傳
  `ScenarioCompareResponse{ scenarios: ScenarioSummary[] }`，依請求 `ids` 的順序並排回傳多個情境
  的摘要。
- 把原本內嵌在 `get_scenario_summary` 端點函式體內的建構邏輯抽成 `_load_scenario_summary()`
  helper，供單情境端點與 `compare_scenarios` 共用，避免重複組裝。`get_scenario_summary` 現在只是
  一行 thin wrapper。
- 新增純函式 `_parse_compare_ids(ids: str) -> List[int]`：解析逗號分隔字串、去重（保留首次出現
  順序）、驗證數量介於 `[MIN_COMPARE_SCENARIOS=2, MAX_COMPARE_SCENARIOS=5]`（下限 2——少於 2 談不
  上比較；上限 5——留餘裕給更多情境並排、同時避免單次請求疊加過多長情境聚合掃描拖垮回應時間，長
  情境聚合可達分鐘級是 A0 端點既有的已知特性，見其 docstring）。非整數段落 / 數量超界 → 400；
  請求中任一 id 找不到情境 → 404（比照既有單情境端點行為，不靜默略過壞 id）。
- **路由註冊順序**（關鍵、易踩雷點）：`/compare` 是單一路徑段，若註冊在 `/{scenario_id}`
  （scenario_id: int）之後，FastAPI 會先用 `/{scenario_id}` 匹配、嘗試把 `"compare"` 解析成 int
  失敗 → 422，永遠打不到 compare_scenarios。已確認並在檔案內把 `_parse_compare_ids` +
  `compare_scenarios` 路由放在 `/{scenario_id}` 之前（`list_scenarios` 之後），並在
  `compare_scenarios` docstring 內寫明這個順序限制，供未來維護者不誤踩。
- 更新檔案頂部的 router 端點清單 docstring，補上新端點。

### 2.2 `modules/monitoring/tests/test_scenario_endpoints.py`（+8 tests）

- `test_compare_scenarios_returns_summaries_in_requested_order`：建 2 個真情境（走
  `generate_bulk` 真物理），驗證回傳順序與請求 `ids` 順序一致。
- `test_compare_scenarios_dedupes_repeated_ids`：重複 id 只回傳一次，保留首次出現位置。
- `test_compare_scenarios_404_for_unknown_id_among_valid`：混入不存在的 id → 404。
- `test_parse_compare_ids_dedupes_and_preserves_order` / `_rejects_non_integer` /
  `_rejects_too_few` / `_rejects_too_many`：純函式邊界（含「去重後剛好等於上限 5 則放行」的邊界
  案例）。
- `test_compare_route_is_reachable_over_real_http_routing`：**HTTP 層路由順序守門測試**——前面
  幾條測試都是直呼 `scenarios_ep.compare_scenarios()`（比照本檔既有慣例繞過 HTTP/auth），不會抓到
  「路由順序錯誤導致 422」這類 bug。本測試額外掛一個只含 `scenarios.router` 的最小 `FastAPI()` app
  + 真 `TestClient`，實際打 `GET /api/scenarios/compare`，驗證落地在 compare_scenarios（200）而非
  被 `/{scenario_id}` 攔截。

## 3. Mutation verification

1. **路由順序 bug**（最關鍯的一個）：用 script 把 `_parse_compare_ids` + `/compare` 路由整段搬到
   `/{scenario_id}/turbines/{turbine_id}/history` 之前（即 `/{scenario_id}` 與
   `/{scenario_id}/summary` 之後——重現「差點犯的錯」）→ 重跑
   `test_compare_route_is_reachable_over_real_http_routing`：**如預期 fail**，得到
   `422 int_parsing: unable to parse string as an integer, input="compare"`，訊息與 assert 訊息
   預期的失敗模式完全吻合。**重要發現**：其餘直呼 endpoint 函式的整合測試（
   `test_compare_scenarios_returns_summaries_in_requested_order` 等）在此 mutation 下**仍然全過**
   ——因為它們繞過真實 HTTP 路由匹配，直接呼叫 Python 函式物件，不會受路由註冊順序影響。這證實了
   為什麼需要額外補一條走真 `TestClient` 的測試，純直呼函式的測試對此類 bug 是盲區。還原後
   （`cp` 備份檔案還原）8 個相關測試全過。
2. **`_parse_compare_ids` 去重邏輯**：把 `deduped = []` + `seen` set 迴圈改成
   `deduped = list(parsed)`（不去重）→ 重跑 `-k dedupes`：`test_compare_scenarios_dedupes_repeated_ids`
   與 `test_parse_compare_ids_dedupes_and_preserves_order` 如預期各自 fail（回傳含重複 id）。還原
   後全過。

兩處 mutation 皆證實新測試會真的抓到對應的邏輯回歸，不是恆真斷言。

## 4. Verify（自我測試全套）

- **backend**：`python -m pytest modules/workflow/tests/ modules/cost/tests/
  modules/reporting/tests/ modules/knowledge/tests/ modules/monitoring/tests/
  modules/auth/tests/ tests/ -q` → **1102 passed / 7 skipped / 1 xfailed**（baseline 1094 + 8 新
  測，零 regression）。
- **frontend**：本 session 未動任何前端檔案。仍完整跑一輪確認零 regression：`npm ci` 正常、
  `npx tsc --noEmit` 0 error、`npx vitest run` **961 passed**（48 files，與 main 現狀一致）、
  `npx vite build` OK（僅既有的 chunk size 警告，非本次引入）。

## 5. code-reviewer subagent review

**0 must-fix / 1 should-fix / 3 nice-to-have，Approve。**

- ✅ **Should-fix（採納）**：`compare_scenarios` 原本用 list comprehension 逐一 `await
  _load_scenario_summary(sid)`，等於序列化等待——與程式碼自己在 `MAX_COMPARE_SCENARIOS` 註解裡寫的
  「避免疊加過多長情境聚合掃描拖垮回應時間」設計意圖矛盾（每個摘要已經把阻塞 SQLite 工作丟
  `asyncio.to_thread`、彼此不互相佔用事件迴圈，序列 await 白白浪費了本可平行的部分）。改用
  `asyncio.gather(*(...))`，保留輸入順序（回傳契約不變），worst case 從「N 個摘要的延遲總和」降到
  「最長那個摘要的延遲」。mutation-verify：沿用既有 `test_compare_scenarios_returns_summaries_in_
  requested_order` 驗證 gather 後順序仍正確（該測試在 gather 化前後都跑過，行為一致）。
- ✅ **Nice-to-have（採納，補 HTTP 層 400 測試）**：原本 `_parse_compare_ids` 的驗證錯誤路徑
  （非整數/數量不足/超界）只有純函式測試，沒有走真 HTTP 管線確認 `HTTPException(400, ...)` 真的會
  從 FastAPI 請求週期正確浮現成 400。新增 `test_compare_route_returns_400_over_real_http_for_
  invalid_ids`，mutation-verify：拿掉下限檢查的 `raise HTTPException(400, ...)` 一行 → 測試如預期
  fail（實得 404，因為驗證被跳過、直接掉進 `_load_scenario_summary(5)` 的「找不到情境」404 路徑，
  而非預期的驗證層 400）——證實新測試真的守住這條驗證，不是恆真斷言。還原後全過。
- ✅ **Nice-to-have（採納，低成本）**：`MIN_COMPARE_SCENARIOS`/`MAX_COMPARE_SCENARIOS` 原本宣告在
  response models 區塊、離唯一使用它們的 `_parse_compare_ids` 有 ~130 行距離，搬到 `_parse_compare_
  ids` 定義正上方，可讀性小幅改善。
- ⚪ **Nice-to-have（婉拒，已是刻意行為且已寫進 docstring）**：`_parse_compare_ids` 靜默忽略空段落
  （如 `ids=1,,3` 或結尾逗號），reviewer 指出這可能讓前端拼字串的 bug 被默默吞掉而非在開發期就浮現
  成 400。本次判斷：這是刻意選擇（docstring 已明寫「前後空白與空段落會被忽略」），且目前唯一消費者
  是尚未開始寫的前端（本 session 未做），沒有實際回歸風險；若未來真的踩到前端拼字串 bug 再收緊即可，
  不在本次無使用場景佐證下預先加嚴驗證。
- **route ordering 確認**：reviewer 額外執行 `test_compare_route_is_reachable_over_real_http_
  routing` 實測（非只讀程式碼），確認 `/compare` 確實註冊在 `/{scenario_id}` 之前、走真 FastAPI app
  拿到 200（非 422），與本 session 自己的 mutation-verify 結論一致。

Verify（review 後重跑，含 gather 化 + 新 400 測試）：`modules/monitoring/tests/test_scenario_
endpoints.py` 21 passed；backend 全套 **1103 passed / 7 skipped / 1 xfailed**（baseline 1094 + 9
新測，零 regression）；frontend 本輪未再動任何檔案，沿用 §4 已驗證的 961 passed / tsc 0 / build OK
（`git status` 確認本次異動僅 `scenarios.py` + `test_scenario_endpoints.py` 兩個 backend 檔案）。

## 6. 範圍內未做（誠實揭露）

- **時序相對時間對齊疊圖 + 差異圖**（decision_log DEC-20260720-02 對 A2 的完整範圍）：本 session
  只做摘要並排；時序對齊需要新的資料聚合思路（`t − sim_start`）+ 前端疊圖元件，留給下個 session。
- **前端消費本端點的 UI**：目前 `/compare` 端點沒有任何前端呼叫方，純後端就緒（比照 A0 當初也是
  先純後端、A1 才接前端的節奏）。下個 session 若接手 A2 前端，可以先用這個端點做「多選情境 → 摘要
  並排長條圖」，再視情況疊時序圖。
- **併發抓取多個情境摘要**：目前 `compare_scenarios` 對每個 id **依序** await
  `_load_scenario_summary`，非並發（`asyncio.gather`）。刻意選擇：單情境摘要端點本身对長情境可能
  達分鐘級（`scenario_turbine_aggregates` 全表掃描丟 `asyncio.to_thread`），若改並發，同時觸發多個
  長情境的 SQLite 讀取聚合，雖然 SQLite 讀取本身不互斥，但仍會疊加 worker thread pool 的負載且沒
  有既有 benchmark 驗證安全性；依序執行行為更可預期、與既有单情境端點的效能特性一致。若之後前端
  UX 上真的覺得依序等待太慢，可以再開 follow-up 評估併發化，本 session 不在無 benchmark 基礎下貿然
  改。
- **測試覆蓋的自動化保護範圍**：路由順序這類「FastAPI 內部路由匹配優先序」問題，本次已補 HTTP 層
  測試守住；但若未來又在 `/api/scenarios/` 下加其他單一路徑段的新端點（例如某天想加
  `/api/scenarios/export` 之類），仍需要開發者自己意識到要放在 `/{scenario_id}` 之前——這條規則本身
  沒有更通用的自動化機制強制（例如沒有寫一個「掃描 router 內所有 literal path 是否都排在對應
  parametrized path 之前」的 meta-test）。若之後這類端點變多，值得考慮加一個通用的 route-ordering
  sanity check，本次範圍不做（YAGNI，目前只有一個 `/compare`）。

## 6.1 給劉老師的提醒（routine 文件過時）

`docs/routines/autonomous-daily-worker-prompt.md`（檔案內自稱 v3、2026-06-03、baseline 638
passed）明顯落後於本 session 收到的注入 prompt（v4.1，baseline 1076/1084、7 個測試路徑含
monitoring/auth）。依注入 prompt 自己的指示「開工後若發現該檔比本 prompt 新，以該檔為準」——但這次
是**反過來**：注入 prompt 比檔案新很多。本 session 範圍是 WMOM-20260922-03（A2 backend），未含
routine 文件整理，故不在本次動它；提醒下次若有餘裕、或劉老師方便時，把 cron trigger 目前實際使用的
prompt 內容同步寫回 `docs/routines/autonomous-daily-worker-prompt.md`，讓檔案重新成為 canonical
來源（目前兩者已分岔一段時間，繼續分岔會讓「canonical 版本」這句話失去意義）。

## 7. 下次接手

- **A2 Part 2**：相對時間對齊的時序疊圖 + 差異圖（後端可能需要一個新端點，例如
  `/api/scenarios/{id}/turbines/{turbine_id}/history` 的多情境版本，取 `t − sim_start` 對齊；
  前端則需要新的「選 2-3 情境 → 疊圖」UI，可以考慮長在 `ScenarioPage.tsx` 或新開一個
  `ScenarioCompareAcrossView.tsx`，比照既有 `ScenarioCompareView.tsx`（A1 同情境內比較）的元件
  風格）。
- **PR C**：檢視情境掛載 app，需先寫 broker 子設計——仍卡在需要先產出設計文件，非本 session 範圍。
- 並行仍待：WMOM-20260716-06（footprint，卡 docker daemon）/ WMOM-20260509-F6（PostgreSQL
  row-lock，同卡 docker daemon）/ M5 收尾（客戶手冊擴充，需客戶素材）/ M6 部署前置（HTTPS，需部署
  目標決策）。
- **CI runner 基礎設施**仍持續失效中（帳號/組織層級問題），本 PR 開出後本機驗證綠即可，預期不會
  自動合併，需劉老師人工確認/合併。
