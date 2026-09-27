# 2026-09-27 — WMOM-20260927-04：`data_broker.py` WFAT (Legacy) 永遠 `None` 欄位清理

## Claim

`ISSUES.md` open issue `WMOM-20260927-04`，前一 session（WMOM-20260927-02）code
review 發現的 follow-up：`priority: low`、估時 20-30 分鐘，deliverable 明講「二選一，
需先查證」。

Stack-aware 檢查：`mcp__github__list_pull_requests` 回傳空陣列，確認沒有上個
session 留下的未合併 PR，可以挑新工作。開工先跑過 §2 baseline，backend
1293 passed / 7 skipped / 1 xfailed、frontend tsc 0 / vitest 1477 passed（70
files）/ build OK，皆與 `ISSUES.md` 記載一致，無 regression 待修。

候選中 `WMOM-20260927-04` 是唯一「單 session 可完工、範圍已由 issue 本身定義清楚」
的項目：`WMOM-20260505-25~28`（物理模型加強）屬多日工作；`WMOM-20260509-F6`/
`WMOM-20260513-01` 皆標 🟡 需劉老師決策；`WMOM-20260504-11`（event-driven cost
ledger）是 M4 增強，範圍未定義（無明確 deliverable/acceptance），需要先設計，不符
「無設計歧義」原則。

## Implement

### 查證（deliverable 要求的前置步驟）

1. `grep -rn "twrBsMy\|twrBsMx\|bldRtMy\|bldRtMx\|delTwr\b\|delBld\b\|dmgAccum"`
   全庫（排除 tests/node_modules）→ 只有 4 個檔案引用這 7 個欄位：
   - `modules/monitoring/server/data_broker.py`（issue 本體，寫入）
   - `modules/monitoring/server/models.py`（`TurbineReading` 欄位定義）
   - `frontend/hooks/useRealtimeData.ts`（`ApiTurbineReading` interface + `apiToTurbineData()` passthrough 對應）
   - `frontend/types.ts`（`TurbineData` interface 欄位定義）
   - `modules/monitoring/examples/fetch_scada_data.py:62`（範例腳本顯示欄位，`t.get('twrBsMy', 0)`）
2. 額外確認：`grep -rln` 這 7 個欄位名於 `modules/reporting/` `modules/cost/`
   `modules/workflow/` `modules/knowledge/` `tests/` → **零命中**。前端也只在
   interface 定義 + passthrough 對應出現，UI 元件（`grep -rn "\.twrBsMy\|..."`
   排除 `useRealtimeData.ts`/`types.ts`）**零命中**——沒有任何畫面實際讀取/顯示
   這 7 個值。
3. 確認根因：`modules/monitoring/simulator/physics/scada_registry.py` 現行 tag
   registry 只註冊 `WLOD_*`（結構負載/疲勞新標準），從未註冊任何 `WFAT_*` tag，
   與 WMOM-20260927-02 的結論一致——這 7 個 `.get("WFAT_*")` 呼叫確定永遠回傳
   `None`，非測試環境巧合。

**結論**：完全未被消費 → 走 deliverable 的「移除整段 legacy 區塊」路徑（非「改連到
正確 WLOD_* 對應」路徑，因為 WLOD_* 對應在同一份 model 裡已經存在獨立欄位
`towerFaMoment`/`bladeFlapMoment` 等，不是「這 7 個欄位改名接上」的關係，而是本來
就是兩組平行欄位，legacy 那組整組是死碼）。

### 修改範圍

- `modules/monitoring/server/models.py`：移除 `TurbineReading` 的
  `# ── WFAT — Fatigue / Load Monitoring ──` 區塊（7 個 `Optional[float] = None`
  欄位 + 註解，緊接在 WVIB alarm threshold 區塊之後、WGDC 之前）。
- `modules/monitoring/server/data_broker.py`：移除 `_to_turbine_reading()`（或等效
  轉換函式）內 `# ── WFAT — Fatigue / Load Monitoring (Legacy) ──` 區塊（7 個
  `scada.get("WFAT_*")` 呼叫）。
- `frontend/hooks/useRealtimeData.ts`：移除 `ApiTurbineReading` interface 的
  對應 7 個 `?: number` 欄位 + `apiToTurbineData()` 內的 7 行 passthrough
  （`// Fatigue / load monitoring (Legacy Standard)` 註解區塊）。
- `frontend/types.ts`：移除 `TurbineData` interface 的
  `// ── WFAT — Fatigue / Load Monitoring ──` 區塊（同款 7 個欄位）。
- `modules/monitoring/examples/fetch_scada_data.py:62`：範例 1（即時快照）的
  `TwrMy(kNm)` 欄位改讀 `towerFaMoment`（`WLOD_TwrFaMom`，實際會產生數值的新標準
  對應欄位）取代永遠是 0 的 `twrBsMy`，欄位標題同步改成 `TwrFa(kNm)` 避免誤導
  （跟 WMOM-20260927-02 同一份檔案、同一個「WFAT→WLOD」修法一致，範圍內順手修正
  避免留下指向剛被移除欄位的死引用）。

未動 `modules/monitoring/simulator/physics/turbine_physics.py:1381-1383` 的
`WFAT_TwrBs`/`WFAT_BldRt` sensor noise config 分支——這是完全獨立的 dead branch
（tag registry 從未產生 `WFAT_*` tag，此分支永遠不會被觸發），但屬於 simulator 物理
模型檔案的一部分，動它需要先讀
`docs/legacy/digiwt_project_notes.md`（CLAUDE.md §12 規範）且超出本 issue 定義的
「API response 欄位」範圍，不在本次驗收範圍內，未另開新 issue（純 dead code，無
功能影響，優先級低於已排隊的 M6 critical path）。

## Verify

- backend 全套：`pytest modules/workflow/tests/ modules/cost/tests/
  modules/reporting/tests/ modules/knowledge/tests/ modules/monitoring/tests/
  modules/auth/tests/ tests/` → **1293 passed**（7 skipped, 1 xfailed，與開工
  baseline 完全一致，零 regression——本次是純刪除死碼，沒有新增測試案例，因為
  acceptance 是「回應不再含有永遠 None 的欄位」，這件事由 Pydantic model 少了這些
  欄位就直接保證，不需要額外測試來鎖住「刪除」這個動作本身）。
- frontend：`npx tsc --noEmit`（0 error，interface 少了 7 個 optional 欄位，
  passthrough 對應同步移除，型別檢查通過確認沒有任何地方還引用這 7 個已刪除欄位）
  + `npx vitest run` → **1477 passed（70 files）**，與 baseline 一致，零
  regression + `npx vite build` → build OK。
- **誠實揭露**：`fetch_scada_data.py` 的欄位標題/對應修正跟 WMOM-20260927-02 一樣
  沒有自動化測試保護——該腳本是獨立範例，走 live server REST，未被任何 pytest
  匯入，僅以讀原始碼層級驗證（確認 `towerFaMoment` 是 `TurbineReading`/
  `data_broker.py` 目前實際會填值的欄位、非另一個死欄位），未做執行期驗證（需真的
  起 server 才能看到欄位真的有非零值）。
- Mutation 驗證不適用於本次修法：本次是「刪除死碼」而非「新增行為由測試鎖住」，
  沒有新測試可做 mutation-verify；用 tsc/pytest 全綠 + grep 二次確認零殘留引用
  取代（`grep -rn "twrBsMy\|twrBsMx\|bldRtMy\|bldRtMx\|delTwr\b\|delBld\b\|dmgAccum"`
  修改後只剩 `git log`/`ISSUES.md`/`work-logs/` 的歷史紀錄與本文件本身命中，程式碼
  路徑零殘留）。

## Review

`code-reviewer` subagent review：**Approve，0 must-fix**，1 should-fix（登記
follow-up）、2 nice-to-have（1 個採納、1 個記錄不處理）。

1. 🟡 **should-fix（未修，登記 WMOM-20260927-05）**：`docs/API_GUIDE.md`
   第 108-114、149、202、278、397 行仍教學使用者查詢不存在的 `WFAT_TwrBsMy`
   等 7 個 SCADA tag——這是 `scadaTags`（原始 SCADA dict）這個資料面的引用，
   跟本 issue 修的 `TurbineReading` 扁平化欄位是不同資料面，不在本 issue 範圍
   內。第 149 行範例程式碼對 `scadaTags` dict 做**直接 key 存取**（非
   `.get()`），照著文件寫程式的人跑起來會 `KeyError`，比本次修的「靜默回傳
   `None`」更糟。Reviewer 建議另開 issue 而非塞進本次 diff（會擴大本次已在
   work-log 界定清楚的驗收範圍）——已採納，登記 `WMOM-20260927-05`。
2. 🟢 **nice-to-have（已採納）**：`fetch_scada_data.py` 同檔案內範例 1（本次改的
   第 56/62 行）改成語意正確的 `TwrFa(kNm)` 標籤，但範例 5（`stream_realtime()`
   第 219 行）沿用舊標籤 `TwrMy=`，兩者底層都是同一個 `WLOD_TwrFaMom` tag 卻標籤
   不一致——已一併改成 `TwrFa=` 統一用語。
3. 🟢 **nice-to-have（記錄不處理）**：移除 public API response 欄位理論上有
   相容性風險（外部客戶端若寫死解析這些 key，即使值恆為 `None`，多的 key 消失
   仍是行為改變）。目前產品仍在 M5/M6（PoC 前、無正式客戶合約），且已查證所有
   已知消費端（前端/reporting/cost/workflow/knowledge modules）零依賴，risk
   可接受，未特別處理（`docs/product/decision_log.md`/`API_GUIDE.md` 皆無
   changelog 段落可掛，暫以本 work-log + `ISSUES.md` completion summary 作為
   紀錄）。

Reviewer 額外針對我在 prompt 裡提出的具體問題給出獨立驗證（非我自己聲稱）：
- 重跑字面 grep（含 word-boundary、大小寫不敏感版本），排除掉 `storage.py`/
  `export.py`/`TrendChartPanel.tsx`/`test_scenario_persistence.py`/
  `test_non_finite_guard.py` 等因為含有 `WLOD_DelTwrFa`/`WLOD_DmgBldFlap`
  等**完全不同**欄位而在寬鬆比對下產生的假陽性命中，確認全庫（含 tests、前端
  元件、reporting/cost/workflow/knowledge modules）零消費判斷成立。
- 確認 `scada_registry.py` 零 `WFAT_*` 命中，且進一步追蹤到
  `turbine_physics.py:878` 確認 `WLOD_TwrFaMom` 真的由
  `fatigue_out["tower_fa_moment_knm"]` 物理計算賦值（非空殼欄位），
  `towerFaMoment` 因此是真實會非 `None` 的欄位；並確認已在
  `frontend/components/TrendChartPanel.tsx:44` 生產環境使用，非孤兒欄位。
- 沒有發現查證方法遺漏：沒有動態 `obj[fieldName]`、序列化 snapshot 測試、
  OpenAPI schema 快照測試、E2E 測試依賴這 7 個欄位存在；前端也沒有
  `Object.keys()`/`Object.entries()` 泛型欄位迭代邏輯會因欄位數量變化受影響。
- 4 個檔案的 diff 乾淨移除，區塊邊界精準對齊「WFAT 區塊」header comment 到下一
  section 之間，無語法錯誤、無多餘逗號、無孤兒註解，前後 WVIB/WGDC 區塊完全
  未受影響。

## Wrap-up

- 本次改動範圍：`modules/monitoring/server/models.py`（`TurbineReading` 移除 7
  欄位）、`modules/monitoring/server/data_broker.py`（對應 7 個賦值移除）、
  `frontend/hooks/useRealtimeData.ts`（interface + passthrough 移除）、
  `frontend/types.ts`（interface 移除）、`modules/monitoring/examples/
  fetch_scada_data.py`（範例 1 欄位改用 `towerFaMoment` + 兩處標籤統一為
  `TwrFa`）。**沒有改動任何物理模型參數或 SCADA tag registry**，純屬 API
  response 死欄位清理。
- **未修範圍（誠實揭露）**：
  1. **新登記 WMOM-20260927-05**（`docs/API_GUIDE.md` 仍教學查詢不存在的
     `WFAT_*` tag），open，未修——留給下個 session（10-15 分鐘小修，無設計
     歧義）。
  2. `simulator/physics/turbine_physics.py:1381-1383` 的 `WFAT_TwrBs`/
     `WFAT_BldRt` sensor noise config 死分支未動（超出本 issue 範圍，屬物理
     模型檔案，且已確認永遠不會被觸發，無功能影響）。
  3. API 相容性 changelog 記錄未做（見 Review 章節第 3 點，判斷 risk 可接受）。
- **測試覆蓋誠實說明**：本次是「刪除死碼」，沒有新增自動化測試——acceptance
  「回應不再含有永遠 `None` 的欄位」由 Pydantic model/TS interface 少了這些
  欄位直接保證，非由測試斷言鎖住。若之後有人不小心把這 7 個欄位加回來，不會有
  任何測試 fail 去阻擋（這是「刪除死碼」類 issue 的固有限制，非本次疏漏）。
  `fetch_scada_data.py` 的欄位替換一如既往沒有自動化測試保護（獨立範例，走
  live server REST，未被任何 pytest 匯入），僅讀原始碼層級驗證（tsc/pytest
  全綠 + reviewer 追蹤到 `towerFaMoment` 確實有物理賦值），未做執行期驗證。
- ISSUES.md：`WMOM-20260927-04` → done（含完整 completion summary）；新增
  `WMOM-20260927-05`（open）；統計表**額外發現並更正**：`grep -c "^### WMOM-"`
  實際 123 筆，先前寫 147/149（長期 drift，2026-09-26 session 已留下提醒但未
  展開全面稽核），本次逐項核實更正為 open 8 / in_progress 2 / done 113 /
  total 123，非本次 issue 造成。
- STATUS.yaml：`last_updated`/`issue_stats`/`test_baseline` 已同步（`test_baseline`
  數字本身不變，backend 1293 passed 已是既有 baseline，無需更新該數字）。
- TODO.md：已同步本次完成摘要 + 下個 session 建議。
- 下個 session 可從 `WMOM-20260927-05`（10-15 分鐘小修）、`WMOM-20260505-25~28`
  （逐一看 priority）、或 M6 critical path 剩餘項（皆需劉老師決策）中挑選。
- **提醒劉老師（沿用 2026-09-23 已留下的同款提醒，至今仍未同步）**：canonical
  routine 文件 `docs/routines/autonomous-daily-worker-prompt.md` 內文仍停在
  v3（baseline backend 638 / frontend 59，無「自我測試」/mutation 驗證/降級
  模式框架），本次 session 開工時實測本次 cron trigger 實際送入的 prompt 已是
  更新版本（baseline backend 1076/970，含 8-phase 執行流程 + GitHub MCP 降級
  模式），落差比 2026-09-23 當時記錄的更大——建議找時間把 cron trigger 目前
  設定同步回這份文件，避免下次有人只看 repo 內文件誤以為還在用舊版 routine。
