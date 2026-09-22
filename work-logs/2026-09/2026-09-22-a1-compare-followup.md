# 2026-09-22 — WMOM-20260720-13：A1 比較視圖 4 個 Should-fix

> Session 類型：實作（follow-up 技術債清理）
> Session 長度：中
> 認領 issue：**WMOM-20260720-13**（A1 pre-merge follow-up，0 Must / 4 Should）
> 分支：`claude/jolly-curie-ts9t94`（本次交辦指定分支；非 routine 的
> `claude/issue-{N}-YYYY-MM-DD` 命名）
> 結果：4 項全收 + 2 項 🟢 nice（`key={scenario.id}`、消除重複 interface），
> frontend 957 → **970 passed**；code review 0 Must / 2 Should（皆已處理）→ Approve

---

## 1. 為什麼先做這個

A1（PR #150）在 round-2 review 回傳前就被合併。review 無 Must-fix（功能無損），
但點出 4 個 Should-fix，其中 **2 個是 round-1 修正時新引入的小回歸**。
範圍明確、半天可清，先清掉不讓它腐爛——接著才做 M6 硬阻塞（-04/-08）。

---

## 2. 四項修正

### (1) `scheduleMissing` 防呆 banner 誤報 — `ScenarioCompareView.tsx`

**問題**：原判法 `faultedIds.size === 0 && rows.some(r => r.faultEvents > 0)`
分不出兩種截然不同的情形：

| 情形 | `fault_schedule` | 該不該提醒 | 舊判法 |
|------|-----------------|-----------|--------|
| 真的沒帶排程 | `undefined` | ✅ 該（分群全落 healthy、不可信） | 只在剛好有 faultEvents 時才提醒 |
| 刻意空排程（純風況基準情境） | `[]` | ❌ 不該（本來就全 healthy） | **誤報** |

而 (b) 的 `faultEvents` 會被 `eventsByTimeWindow` 的時間窗滲入——緊接在有故障情境後
生成乾淨情境時尤然 → 對乾淨情境誤報「未帶排程」，誤導使用者以為資料壞了。

**修**：`scheduleMissing = scenario.config?.fault_schedule === undefined`。
只看欄位在不在，職責與既有 `eventsByTimeWindow` 提示（負責說明 faultEvents 的可信度）
就此分離、不再重疊。提示文案一併改寫（觸發條件已不含 faultEvents，原文案的
「雖有觀測到故障事件」不再成立）。

### (2) 切頁籤丟失所選機組 + 多打一次 API — `ScenarioDetail.tsx`

**問題**：A1 把 `ScenarioTrendView` 抽出後用 `{tab === 'trend' && <ScenarioTrendView/>}`
條件式渲染 → 切頁籤時子元件 unmount → `turbineId` 與已抓的 history 連同 state 銷毀，
切回趨勢頁重設回 WT001 並重抓一次（`HISTORY_LIMIT=12000`）。正打在 A1 主打的
「比較↔趨勢來回」核心動線上。

**修**：**lazy keep-alive** —— 造訪過的頁籤保持掛載、只切 `display`：

```tsx
const [visited, setVisited] = useState<Record<DetailTab, boolean>>({ trend: true, compare: false });
const openTab = (next: DetailTab) => { setVisited(v => (v[next] ? v : { ...v, [next]: true })); setTab(next); };
```

刻意「首次造訪才掛載」而不是一開始就全掛：如此每個子視圖的**第一次 mount 一定發生在
可見狀態下**——recharts `ResponsiveContainer` 於 mount 時量測容器尺寸，若在 `display:none`
下初次掛載會量到 0 而畫不出圖（issue 原文提醒的風險點）。之後轉成 `display:none` 不會
觸發 ResizeObserver（規格：display:none 的元素不被觀察），已量到的尺寸因此保留。

順帶收 🟢 nice：`ScenarioPage` 的 `<ScenarioDetail key={observing.id} …>`。keep-alive 保留
更多 state（頁籤 + 所選機組），換情境必須換 identity 強制重置，不依賴呼叫端「先回列表
才能開下一個」這條 control flow。

### (3) `handleGenerate` Must-fix 現場缺回歸測試 — `ScenarioPage.test.tsx`

**問題**：A1 round-1 的 Must-fix 是「`handleGenerate` 把 `fault_schedule` 補進
`lastScenario.config`」，但新測全在 `ScenarioCompareView` 層、**繞過 handleGenerate**
→ 補丁被改壞沒有測抓得到。

**修**：新增端到端測試，從「生成 → 觀察此情境 → 機組比較」一路點下去，斷言排程真的被
帶過去（不顯示防呆 banner + WT001 被判為 faulted）。summary fixture 裡三台機組
`faultEvents` 皆 0，故唯一可能的判別來源就是情境 config 的 `fault_schedule`——不假綠。

### (4) `fault_schedule` 映射兩次、形狀不同 — 新 `utils/faultSchedule.ts`

**問題**：`handleGenerate` 把同一份排程映射兩次且形狀不同——request body 用 `at_hour`，
就地組 `lastScenario.config` 用 `offset_seconds`。兩份各自演化**正是這次 bug 的成因模式**。

**修**：抽 `toFaultScheduleEntries(faults)`，兩處共用；產出單一形狀
`{scenario_id, turbine_id, offset_seconds, severity_rate}`，**與後端落地形狀逐欄位對齊**
（`modules/monitoring/server/routers/config.py`：`_parse_fault_schedule` 優先吃
`offset_seconds`，寫進 `config_json.fault_schedule` 亦為此形狀）。
`FaultScheduleEntry` 的 `severity_rate` 設選填是為讀取端——#125 之前的舊情境可能沒這欄。

---

## 3. Verify

| 項目 | 結果 |
|------|------|
| `npx tsc --noEmit` | 0 error |
| `npx vitest run` | **970 passed / 49 files**（原 957 / 48，+13 測 +1 檔；含 review 後補的 sentinel 測試） |
| `npx vite build` | OK |
| backend `pytest modules/monitoring/tests/` | 131 passed（`at_hour → offset_seconds` 切換無回歸） |

### Mutation 驗證

| 把實作改回 | 失敗的測試 |
|-----------|-----------|
| `scheduleMissing` 舊判法 | 2 個（空排程誤報 + 欄位缺失無故障仍須提醒） |
| 頁籤條件式渲染 | 4 個（keep-alive 全組） |
| `lastScenario.config` 不帶排程（A1 原 bug） | 1 個（端到端測試） |
| `offset_seconds` 換算漏乘 3600 | 3 個（util 2 + ScenarioPage 1） |
| config 改回**獨立映射但形狀正確** | 1 個（sentinel 測試，見下） |
| request body 改回 inline 映射 | 1 個（同上） |

---

## 4. Review 回饋與修正（code-reviewer，0 Must / 2 Should / 2 Nice → Approve）

reviewer 自己重跑了獨立的 mutation 驗證，指出我原本「4 項修正皆 mutation 驗證」的說法
**有兩處對不上實況**。實測確認 reviewer 說得對，兩處都已處理：

### Should-fix 1 — (4) 的 DRY 不變量原本沒被鎖住（已補測）

我原本的 mutation 是「把 `lastScenario.config` 的 `fault_schedule` **整個拿掉**」（那確實會 fail）。
但 reviewer 改成「保留欄位、只是改回**獨立映射且形狀正確**」→ **56 測全過**。我重跑確認如此。

根因：`utils/scenarioCompare.ts` 的 `faultedTurbineIds()` 只讀 `turbine_id`，完全不看
`offset_seconds` / `severity_rate`。所以「兩處映射形狀不同」在今天的 UI 下**不會反映成任何
可觀察差異**（`severity_rate` 目前前端無任何消費端）。原本的端到端測試只驗 faulted 分群，
而分群對這個 bug 不敏感 → 等於沒鎖住。

**修**：新增 sentinel 測試——`toFaultScheduleEntries` 被 mock 成回傳「UI 狀態不可能產出」的值
（排定的是 WT001，helper 硬回 WT003），然後斷言 **(a)** request body 等於該 sentinel、
**(b)** 比較頁把 **WT003** 判為 faulted（而非 UI 狀態的 WT001）、**(c)** 整個生成流程只映射一次。
任一處改回自己 inline 映射，那一處就會出現 WT001 → 測試失敗。兩個方向都 mutation 驗證過
（見上表末兩列）。mock 用 `mockReturnValueOnce` 包住真實實作，不外洩到其他測試。

### Should-fix 2 — `key={observing.id}` 目前不可達（已改為誠實標註）

reviewer 拿掉該行重跑 `ScenarioPage.test.tsx` → 45 測全過。原因：`observing` 為真時
`ScenarioPage` 提早 `return`，三個能改 `observing` 的呼叫點都只存在於 `observing` falsy 時才
渲染的 JSX 裡 → 換情境**必經 `observing=null` 的完整 unmount**。

所以這行是**面向未來重構的防禦性 no-op，今日 control flow 下無測試能覆蓋**（寫紅測試得先破壞
早退邏輯，等於測一個假設情境，投報率低）。此處明確記錄，避免後續接手者誤以為「換情境時
`turbineId` 不會殘留」有自動化保護——它目前**完全靠「先回列表」這條 unmount/remount 路徑撐著**。

### Nice 3 — keep-alive 的 recharts 假設：需人工瀏覽器驗證（**未做，列為待辦**）

reviewer 去讀了實際安裝的 `recharts@3.8.1` 原始碼
（`node_modules/recharts/es6/component/ResponsiveContainer.js`）確認我的推論成立：
`SizeDetectorContainer` 在 mount 的 `useEffect` 裡會先**同步** `getBoundingClientRect()` 量一次
存進 state，才 `observer.observe(...)`；父層之後轉 `display:none` 不會清掉那份 state。
故「首次掛載必須在可見狀態」這個設計前提是對的，切回來會直接用那份尺寸重繪。

**但這條路徑目前沒有任何自動化測試在把關**：jsdom 沒有 `ResizeObserver`，recharts 的 effect
一開頭就 `if (typeof ResizeObserver === 'undefined') return noop` 直接短路——這也是跑
`ScenarioCompareView` / `ScenarioDetail` 測試時 console 印一堆 `width(-1) height(-1)` 的原因。

→ **待辦（本 session 未做，無瀏覽器環境）**：在真實瀏覽器手動驗一次「趨勢 → 機組比較 → 趨勢」
來回切換後長條圖與趨勢圖**真的畫出來而非空白**，Safari/WebKit 尤其要看（其 ResizeObserver 對
`display:none` 歷史上 edge case 較多）。現場工程師用的行動裝置瀏覽器版本可能較舊
（CLAUDE.md §15「現場工程師也是 user」），此處若失準，使用者看到的是**空白圖表而非報錯**，
不容易自己發現。**未驗證前不建議視為完全結案。**

### Nice 4 — 重複的 interface（已消除）

reviewer 指出 `utils/faultSchedule.ts` 註解說「刻意不 import 以免循環依賴」**不準確**：
`import type` 在 Vite/esbuild 下會被完全抹除、不產生 runtime import。而兩份手刻同形狀
interface，正是本模組想消除的那種平行維護風險。

**修**：`ScheduledFaultInput`（領域欄位）留在 utils，`ScenarioPage` 的 `ScheduledFault` 改為
`extends ScheduledFaultInput { key: number }`——共用欄位只剩一份定義，型別住 utils 不 import
任何 component 故確實無循環依賴。註解一併改成正確敘述。

---

## 5. 下次接手

**WMOM-20260720-04 + WMOM-20260720-08 — live/OPC 後端硬化**（M6 現場部署唯一硬阻塞）：
1. `DataBroker.stop()` 補 `self._opc_adapter.stop(); self._opc_adapter = None`
2. 切走 live 的角色檢查（起 live 需 SUPERVISOR，切走卻不需 → 不對稱）
3. `config.py::set_simulation` 在 source 非即時模擬時拒絕/要求明確確認，不再靜默 `switch_mode`
4. `start/stop/switch_mode` 外包 `threading.Lock`
5. `simulator/engine.py:310` `time.sleep(time_step)` → `threading.Event().wait(time_step)`

環境提醒：裝依賴需 `pip install --ignore-installed PyYAML -r requirements-dev.txt`。
