# 2026-09-22 — A1 round-2 follow-up 全修（WMOM-20260720-13）

> Session 類型：實作（第二個 autonomous session，接續本日稍早的 live/OPC 後端硬化 session）
> Session 長度：中
> 主導：Claude（autonomous worker）
> 結果：A1（情境比較視圖，PR #150）round-2 review 回報的 4 個 Should-fix 全修，逐項
> mutation-verified；純前端，frontend 957→960 passed、backend 1093 不變（本次未動後端）；PR 已開，
> 等 CI 綠 auto-merge。

---

## 1. Session 目標

依 §4 決策樹認領 `WMOM-20260720-13`——上個 session（live/OPC 硬化）work-log 明確列為「最該做的事」，
`ISSUES.md` 已有明確 diagnosis + 修法草案，屬 autonomous-friendly，且直接延續 M6 前置的情境比較分析
epic（DEC-20260720-02）。4 個 Should-fix：

1. `ScenarioCompareView.tsx` 的 `scheduleMissing` 防呆 banner 誤報（round-1 修正時新引入的小回歸）。
2. `ScenarioDetail.tsx` 條件式渲染頁籤，切「機組比較」再切回「趨勢」會丟失所選機組（同為 round-1 新增
   `ScenarioTrendView` 抽出時引入的回歸）。
3. `ScenarioPage.handleGenerate` 組 `lastScenario.config.fault_schedule` 這段邏輯缺端到端回歸測試。
4. `fault_schedule` 在 `handleGenerate` 映射兩次、兩種不同形狀（`at_hour` vs `offset_seconds`）→
   漂移風險。

---

## 2. 實際完成

### 2.1 主要工作

1. **(1) `scheduleMissing` 判定改用 `fault_schedule === undefined`**：原邏輯
   `faultedIds.size === 0 && rows.some(faultEvents > 0)` 無法區分「真的沒帶排程」與「刻意生成的純風況
   乾淨情境，`fault_schedule` 正確為空陣列 `[]`」——緊接在有故障情境後生成的乾淨情境，`faultEvents` 可能
   被時間窗污染帶進非 0 殘值，觸發誤報。改判 `scenario.config?.fault_schedule === undefined`，只有欄位
   真的不存在才視為「缺」。

2. **(2) `turbineId` 提升到 `ScenarioDetail`（controlled）**：`ScenarioDetail` 用
   `{tab === 'trend' && <ScenarioTrendView/>}` 條件式渲染頁籤，切去「機組比較」會把 `ScenarioTrendView`
   整個 unmount，其原本自管的 `turbineId`（`useState(turbineOptions[0])`）連同已抓資料一起銷毀，切回
   「趨勢」重新 mount 又重設回 WT001、重抓 history——打在 A1「比較↔趨勢來回」這條核心動線。改把
   `turbineId` 提升到 `ScenarioDetail` 層（`useState('WT001')`），以 controlled prop `turbineId` +
   `onTurbineIdChange` 傳給 `ScenarioTrendView`（移除其內部 `useState`）。`ScenarioTrendView` 仍會在切
   頁籤時 unmount/remount（未做 keep-alive + CSS display 切換那個更完整但有 recharts ResponsiveContainer
   尺寸風險的選項），但 remount 後立刻用保留下來的正確 `turbineId` 重抓，不再有「先重設回 WT001 → 使用者
   重選 → 又打一次 API」這段浪費，兩個症狀（丟失選取 + 多打一次 API）皆解。

3. **(3) 端到端回歸測試補上**：原本所有 `fault_schedule` 相關測試都直接在 `ScenarioCompareView` 層手造
   `SavedScenario` prop，繞過 `handleGenerate` 本身。新增
   `ScenarioPage.test.tsx`「生成帶排定故障 → 觀察此情境 → 機組比較頁正確標出排定故障的機組」，從 UI 操作
   走完整條路徑（點「生成情境」→ 點「觀察此情境」→ 點「機組比較」頁籤 → 斷言明細表該機組顯示
   「排定未觸發」標記），直接守住 `handleGenerate` 組 `lastScenario.config.fault_schedule` 這段邏輯。

4. **(4) 抽 `toFaultScheduleEntries` 共用 helper**：`handleGenerate` 原本把 `faults: ScheduledFault[]`
   獨立映射兩次——一次給 `generate-bulk` 請求 body（`{scenario_id, turbine_id, at_hour, severity_rate}`），
   一次給本地 `lastScenario.config.fault_schedule`（`{scenario_id, turbine_id, offset_seconds}`）。兩處
   各自轉換正是本次要修的漂移風險成因模式。讀 `modules/monitoring/server/routers/config.py`
   `_parse_fault_schedule` 確認後端本就優先吃 `offset_seconds`（見其
   `if "offset_seconds" in item: ... else: offset = at_hour * 3600`），故抽出單一 helper
   `toFaultScheduleEntries` 產出 `{scenario_id, turbine_id, offset_seconds, severity_rate}`，兩處共用
   同一次映射結果。既有「生成時把排定故障轉成 fault_schedule」測試同步改斷言 `offset_seconds`
   （`84 * 3600`）而非 `at_hour`（`84`）。

### 2.2 Mutation 驗證（Phase 5 規定，逐項做）

- **(1)**：把 `scheduleMissing` 判定復原成舊版 `faultedIds.size===0 && ...`，新增的「情境刻意帶空排程
  但 faultEvents 被時間窗污染 → 不誤報」測試如預期 fail（斷言 banner 不該出現，卻出現了）；還原後綠。
- **(2)**：把傳給 `ScenarioTrendView` 的 `turbineId` prop 硬寫死 `'WT001'`（模擬「切回趨勢永遠重設」的
  舊行為），`ScenarioDetail.test.tsx` 既有的「換機組 → 重抓該機組 history」測試 + 新增的「切到機組比較再
  切回趨勢 → 保留原選取機組」測試皆如預期 fail（2 個測試失敗）；還原後綠。
- **(4)**：把 `generate-bulk` 請求 body 的 `fault_schedule` 復原成獨立映射（重新手打 `at_hour` 版本，
  不用 `toFaultScheduleEntries`），既有「生成時把排定故障轉成 fault_schedule」測試（已改斷言
  `offset_seconds`）如預期 fail（收到 `undefined`）；還原後綠。另外把 `lastScenario.config.fault_schedule`
  復原成 `undefined`（模擬漏帶整段排程的回歸），新增的端到端回歸測試（(3) 補的那條）如預期 fail（機組比較
  頁找不到「排定未觸發」標記）；還原後綠。
- **(3)** 本身即是新增測試，其驗證效力已透過 (4) 的 mutation 間接證實（該測試確實會抓到
  `lastScenario.config.fault_schedule` 被改壞）。

四項逐一復原 → 對應測試 fail → 還原，確認新/改測試真的鎖住了修正，非空測。

### 2.3 code review

用 `Agent` tool 跑 `code-reviewer` subagent 對本次 diff（4 個 production 檔案 + 3 個測試檔案）review，
聚焦：React state/effect 時序、`fault_schedule === undefined` 邊界情況、`toFaultScheduleEntries` 是否
真的兩處都改到、`ScenarioTrendView` 是否還有其他未更新的呼叫端、新測試是否鎖住正確的東西。

**結果：0 Must-fix、1 Should-fix、1 Nice-to-have，皆已採納修復：**

- 🟡 Should-fix：`scheduleMissing` 判定用 `=== undefined` 而非 `== null`——目前所有 producer（後端
  `_parse_fault_schedule`、前端 `toFaultScheduleEntries`）都只會給陣列不給 `null`，非立即可觸發，但
  reviewer 指出這正是本次要修的「loose vs strict 比對造成漏判」同類問題，防禦性改 `== null` 同時擋
  `undefined` 與 `null`，不留漏洞。已採納（`ScenarioCompareView.tsx`）。
- 🟢 Nice-to-have：`ScenarioConfig.fault_schedule` 型別漏宣告 `severity_rate`（兩個 producer 都有填、
  但型別沒宣告，屬不完整契約）。已採納補上 `severity_rate?: number`（`ScenarioDetail.tsx`）。

reviewer 也重跑了 `tsc --noEmit` + 全套 vitest（960 passed）+ 手動追蹤後端 `_parse_fault_schedule` 確認
`offset_seconds` 優先權 + grep 確認 `ScenarioTrendView` 僅一個呼叫端 + 確認 `toFaultScheduleEntries`
確實是唯一映射點，獨立驗證了本次宣稱的正確性，而非只憑靜態讀碼判斷。採納兩項建議後，本 session 重跑
tsc + 全套 vitest（960 passed）+ vite build 皆綠，收尾。

### 2.4 卡住或延後的事

- 無阻擋項。
- 🟢 Nice-to-have（ISSUES.md 原條目列的，未動，留待之後有餘裕再做）：abort-race 專屬測、
  `ScenarioConfig`/`SavedScenario` 抽 `types.ts` 消循環 import、`ScenarioDetail` 加
  `key={scenario.id}` 讓 tab 重置不依賴呼叫端 control flow。

### 2.5 重大決策（如有）

無架構級決策，不寫 decision_log。純 bug-fix + 測試補強，符合原 issue 的修法方向。

---

## 3. 產出清單

### 修改檔案

- `frontend/components/ScenarioCompareView.tsx` — `scheduleMissing` 判定改用
  `scenario.config?.fault_schedule === undefined`
- `frontend/components/ScenarioDetail.tsx` — `turbineId` 提升為 controlled state，傳給
  `ScenarioTrendView`
- `frontend/components/ScenarioTrendView.tsx` — 移除內部 `useState(turbineId)`，改吃
  `turbineId`/`onTurbineIdChange` props
- `frontend/components/ScenarioPage.tsx` — 抽出 `toFaultScheduleEntries` helper，
  `generate-bulk` 請求 body 與 `lastScenario.config.fault_schedule` 共用
- `frontend/components/__tests__/ScenarioCompareView.test.tsx` — +1 回歸測（空排程 + 污染
  faultEvents 不誤報）
- `frontend/components/__tests__/ScenarioDetail.test.tsx` — +1 回歸測（切頁籤保留選取機組）+
  `/summary` fetch mock 支援
- `frontend/components/__tests__/ScenarioPage.test.tsx` — +1 端到端回歸測（handleGenerate →
  機組比較頁）+ `/summary` fetch mock 支援；既有「生成時把排定故障轉成 fault_schedule」測試改斷言
  `offset_seconds`
- `ISSUES.md` — WMOM-20260720-13 標 done（統計表 in_progress 1→0、done 102→103）
- `STATUS.yaml` — `last_updated`、`next_milestone` 補本 session 摘要
- `TODO.md` — 更新最後更新時間 + baseline 數字（frontend 957→960）

### 動了狀態的 issue

- WMOM-20260720-13: in_progress → done

### 寫進 decision_log 的決策

- 無

---

## 4. 下次怎麼接手

1. **最該做的事**：續 **A2 跨情境比較**（相對時間對齊）或 **PR C**（檢視情境掛載 app，需先寫 broker
   子設計）——DEC-20260720-02 情境比較分析 epic 剩餘項目。
2. **第二優先**：`WMOM-20260716-06`（footprint CPU-torch pin，需 docker 環境驗）或
   `WMOM-20260509-F6`（PostgreSQL row-lock integration test，需 docker postgres）——兩者都卡在本
   sandbox 無 docker，若下個 session 有 docker 環境可挑。
3. **阻擋項**：無。GitHub MCP 這次可用；PR 已開，CI 綠後 auto-merge 會自動合進 main + 刪分支。
4. **誠實揭露**：本次 4 項修正皆純前端邏輯 + DOM 斷言測試，vitest 對 recharts 圖表本身能否正確渲染
   （jsdom 無 `ResizeObserver`）無法驗證——但本次改動不涉及圖表渲染邏輯本身，只動選取機組的 state 管理
   與資料映射，風險低。fix (2) 未做「兩頁常駐 + display 切換」這個更完整、能同時避免每次切頁籤都重抓
   history 的方案，因為該方案在真瀏覽器下 ResizeObserver 對 `display:none→block` 的行為無法用 vitest
   驗證，選擇 risk 較低的 controlled-state 方案；此為已知取捨，非遺漏。

---

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 讀 issue + 定位 4 個子問題的相關程式碼 | 20% |
| 寫修正（4 處） | 25% |
| 寫新測 + 既有測試改斷言 | 25% |
| Mutation 驗證 | 20% |
| 全套 baseline 驗證 + 文件收尾 | 10% |

---

## 6. 學到的事

- **round-2 review 若在 PR 合併後才回報，容易被下個 session 才處理**——這次驗證了上個 session 把它明確
  記在 work-log「下次接手」欄位、且 ISSUES.md 有完整 diagnosis + 修法草案的做法有效：本 session 開工
  幾乎不用重新分析問題，直接照案執行。**跨 session 交接品質直接決定下一輪的起跑速度**，值得持續維持
  這個習慣。
- **`undefined` vs 空陣列 `[]` 是很容易被忽略但语意完全不同的兩種「無資料」**——`fault_schedule` 的
  bug 正是典型案例：`[]` 代表「使用者明確選擇不排故障」（合法、正確的狀態），`undefined` 才代表「這條
  路徑真的沒帶這個欄位」（異常、需要防呆提示的狀態）。用 `.length === 0` 或衍生集合的 `.size === 0`
  做判斷會抹掉這個區別，要判斷「欄位是否存在」時應直接對原始欄位做 `=== undefined` 檢查。
- **條件式渲染（`{cond && <Comp/>}`）等同每次切換都 unmount/remount，元件內部 state 不會存活**——這是
  React 的基本行為，但很容易在重構抽元件時忽略（本次的 round-1 就是抽出 `ScenarioTrendView` 時踩到）。
  若某個 state 需要跨條件式渲染的切換存活，兩個選項：(a) 提升到不會被卸載的父層（本次採用，風險低）、
  (b) 改用「兩者都常駐 + CSS display 切換」做 keep-alive（能同時省掉 remount 的重複請求，但若子元件內
  有依賴容器尺寸的第三方元件如 recharts `ResponsiveContainer`，`display:none → block` 的尺寸重算行為
  在 jsdom 測試環境無法驗證，只能人工瀏覽器驗——遇到這類取捨要老實記在 work-log，不要含糊帶過）。
