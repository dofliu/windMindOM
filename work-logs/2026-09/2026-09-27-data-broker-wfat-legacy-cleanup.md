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

（待 code-reviewer subagent review 後補上結論）

## Wrap-up

（待 review 後收尾）
