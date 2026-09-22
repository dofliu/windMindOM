# 2026-09-22 — WMOM-20260720-13：A1 比較視圖 4 個 Should-fix

> Session 類型：實作（follow-up 技術債清理）
> Session 長度：中
> 認領 issue：**WMOM-20260720-13**（A1 pre-merge follow-up，0 Must / 4 Should）
> 分支：`claude/jolly-curie-ts9t94`（本次交辦指定分支；非 routine 的
> `claude/issue-{N}-YYYY-MM-DD` 命名）
> 結果：4 項全收 + 1 項 🟢 nice（`key={scenario.id}`），frontend 957 → **969 passed**

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
| `npx vitest run` | **969 passed / 49 files**（原 957 / 48，+12 測 +1 檔） |
| `npx vite build` | OK |
| backend `pytest modules/monitoring/tests/` | 131 passed（`at_hour → offset_seconds` 切換無回歸） |

### Mutation 驗證（每項修正都確認新測會抓）

| 把實作改回 | 失敗的測試 |
|-----------|-----------|
| `scheduleMissing` 舊判法 | 2 個（空排程誤報 + 欄位缺失無故障仍須提醒） |
| 頁籤條件式渲染 | 4 個（keep-alive 全組） |
| `lastScenario.config` 不帶排程（A1 原 bug） | 1 個（新的端到端測試） |
| `offset_seconds` 換算漏乘 3600 | 3 個（util 2 + ScenarioPage 1） |

---

## 4. 下次接手

**WMOM-20260720-04 + WMOM-20260720-08 — live/OPC 後端硬化**（M6 現場部署唯一硬阻塞）：
1. `DataBroker.stop()` 補 `self._opc_adapter.stop(); self._opc_adapter = None`
2. 切走 live 的角色檢查（起 live 需 SUPERVISOR，切走卻不需 → 不對稱）
3. `config.py::set_simulation` 在 source 非即時模擬時拒絕/要求明確確認，不再靜默 `switch_mode`
4. `start/stop/switch_mode` 外包 `threading.Lock`
5. `simulator/engine.py:310` `time.sleep(time_step)` → `threading.Event().wait(time_step)`

環境提醒：裝依賴需 `pip install --ignore-installed PyYAML -r requirements-dev.txt`。
