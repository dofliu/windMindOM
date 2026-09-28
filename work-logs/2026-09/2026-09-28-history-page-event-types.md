# 2026-09-28 — WMOM-20260928-05：`HistoryPage.tsx` 事件類型登記表遺漏 `fatigue`/`fault_lifecycle`

第二十二個 autonomous session。

## 背景 / 怎麼找到這個工作

前一個 session（`WMOM-20260505-25-a`）在 `TurbineDetail.tsx` fatigue tab 加了 RUL 倒數 +
疲勞警報 badge，過程中確認 `data_broker.py` 除了把 fatigue 相關 SCADA tag 透傳到
`scadaTags` 之外，還會在等級升降級時另外 `record_event(event_type="fatigue", ...)` 寫一筆
history event（供未來「觸發時間軸」用）。`WMOM-20260505-25` 母 issue 剩下的 Part
還包含「RUL 觸發時間軸」，本次接續盤點這條資料流時，做了全庫 `grep -rn 'event_type="'`：

```
modules/monitoring/server/*.py modules/monitoring/server/routers/*.py
```

實際命中 7 種：`fatigue / fault / fault_lifecycle / grid / operator / state / wind`。

再去看前端 `frontend/components/HistoryPage.tsx`（既有通用「歷史資料 + 事件標記」頁面，
`/api/turbines/{id}/history` 端點本就把 `events` 陣列完整回傳），發現它的
`EVENT_TYPES` 登記表只有 5 種：`grid/fault/operator/wind/state`——完全沒有
`fatigue`/`fault_lifecycle`。

往下追 `visibleEvents` 的 filter 邏輯：

```ts
.filter(e => enabledEventTypes[(e.event_type as EventType)] ?? false)
```

`enabledEventTypes` 是 `Record<EventType, boolean>`，`fatigue`/`fault_lifecycle` 從未被
初始化進這個 state，`enabledEventTypes['fatigue']` 在執行期永遠是 `undefined`，
`undefined ?? false` → `false`。也就是說**無論使用者怎麼點篩選 toggle**（反正畫面上根本
沒有這兩個 toggle 按鈕可以點），這兩種真實記錄下來的後端事件永遠不會出現在事件紀錄
清單、圖表 `ReferenceLine` 標記、或事件詳情面板——資料庫裡確實有資料，`/history` API
確實回傳了，但整組被前端靜默濾掉，沒有任何錯誤訊息或提示。

這比「RUL 觸發時間軸還沒做」更根本：後端其實已經在記錄「觸發」這件事本身
（`fatigue` event 的 title 就是「疲勞警報升級：塔架 Lv2 (警告)」這種人類可讀格式），
只是既有的通用事件時間軸頁面完全看不到它，equivalent 於一個真實存在的資料被 UI bug
吃掉。判斷這是比重建一個全新獨立元件更小、更低風險、且立刻讓既有真實資料可見的
單 session 候選——用既有通用事件時間軸「順便」補齊，而非另外造一個專屬 RUL 時間軸元件
（避免重複造輪子：既有 `HistoryPage.tsx` 的事件清單/詳情/篩選/圖表標記已經是成熟通用
機制，`fatigue` 事件的 title/detail 欄位本來就是為了人類閱讀寫的）。

`fault_lifecycle`（故障開始/階段轉換/結束的自動生命週期追蹤，跟手動/API 注入故障的
`fault` event 互補、非重複）是同一次 grep 順手發現的同款遺漏，修法完全相同（同一組
查表結構補 entry），故一併修掉，避免留下近乎相同的 follow-up issue。

## 修法

**零後端改動**——`GET /api/turbines/{id}/history` 早就把 `events` 完整回傳，純粹是前端
登記表沒跟上。`frontend/components/HistoryPage.tsx` 五處既有查表結構各自補
`fatigue`/`fault_lifecycle` 兩個 entry，貼合既有 5 種型別一模一樣的 pattern：

1. `EVENT_TYPES` 常數陣列（`as const` union 型別來源）
2. `eventTone()`：`fatigue → 'danger'`、`fault_lifecycle → 'warn'`
3. `EVENT_HEX`（chart ReferenceLine 顏色）：各配一組 light/dark hex，色調與既有 5 色區隔
4. `eventTypeLabel()` zh 分支：`fatigue → '疲勞'`、`fault_lifecycle → '故障週期'`
5. `enabledEventTypes` 初始 state：兩者預設 `true`（跟既有 5 型一致，預設全開）

**tone 選擇說明**：`fault_lifecycle` 跟既有 `fault` 都給 `warn`（同屬「故障」大類、
語意上合理共用同一 tone，用不同 hex 顏色區分「手動/情境注入的故障」vs「模擬自動追蹤的
故障生命週期」，而非發明第三種 tone 製造認知負擔）；`fatigue` 給 `danger`（結構疲勞
風險語意上比一般 grid/wind/operator 事件更需要引起注意，且與既有 `TurbineDetail.tsx`
fatigue tab 的高等級警報視覺語言〔`-25-a` 用 danger tone 標示 4 級警報〕保持跨頁一致）。

## 測試

`frontend/components/__tests__/HistoryPage.test.tsx` 新增 4 測（同一個新 `describe` 區塊）：

1. 事件清單渲染 `fatigue`/`fault_lifecycle` 事件的 title（先前完全濾掉，現在出現）
2. 點 `fatigue` 事件 → 詳情面板顯示中文 type label「疲勞」+ detail 文字
3. 關掉「疲勞」toggle → 只有 fatigue 事件消失，`fault_lifecycle` 事件仍在（互不干擾）
4. 關掉「故障週期」toggle → 只有 fault_lifecycle 事件消失，fatigue 事件仍在（互不干擾）

**Mutation-verify**：`git stash push -- frontend/components/HistoryPage.tsx`（只暫存元件
本體，測試檔案不動）→ 重跑 `HistoryPage.test.tsx` → 4 個新測試如預期**全部 fail**（`getByRole`
找不到對應 title button / `getAllByText('故障週期')` 找不到任何符合的元素），既有 23 測
仍全過 → `git stash pop` 還原 → 27 測全過。

## 驗證結果

- `npx tsc --noEmit`：0 error
- `npx vitest run`：70 files / **1490 passed**（baseline 1486 + 新增 4，零 regression）
- `npx vite build`：OK
- backend `pytest`（7 個既有路徑，本次未動任何 backend 檔案）：**1295 passed**（7 skipped,
  1 xfailed），與 baseline 完全一致

## Code review

（code-reviewer subagent 審查中，結論將在下方補上；若審查後有 must-fix/should-fix
修正，會在此段落更新並重跑對應驗證。）

## 誠實揭露 / 未修範圍

- `eventTypeLabel()` 對 `lang==='en'` 分支本來就是 `return et`（直接印原始英文字串，如
  `"grid"`/`"fault"`，並非真正翻譯過的英文標籤）——這是全部既有 5 型共享的既有技術債，
  非本次引入。`fatigue`/`fault_lifecycle` 沿用同款既有行為，未額外補齊英文翻譯，刻意
  把本次修復範圍聚焦在「登記表遺漏導致真實資料隱形」這單一問題，不蔓延到既有 i18n
  缺口（若劉老師認為值得修，建議另開 issue 一次盤點全部事件類型的英文標籤）。
- 未驗證這兩種事件在「情境比較」（`EventComparisonView.tsx`/`ScenarioCompareTimelineView.tsx`
  等 A1/A2 情境比較元件）路徑上是否有類似遺漏——本次只查證並修復 `HistoryPage.tsx`
  這條即時檢視路徑，情境比較路徑走的是完全不同元件與資料流，未展開檢查，非本 issue
  範圍。
- 圖表上的 `ReferenceArea`（用於有 `end_timestamp` 的區間事件）目前只認 `grid`/`wind`
  兩型；`fatigue`/`fault_lifecycle` 事件本身沒有 `end_timestamp`（後端記錄時未帶），
  故不需要、也未加入 `ReferenceArea` 判斷式，只會以 `ReferenceLine`（瞬時標記）顯示，
  行為正確。

## 下個 session

- `WMOM-20260505-25` 母 issue 仍 open：剩 `SpectralAlarmPanel`（5-band 頻譜）、
  `BearingDiagPanel`（BPFO/BPFI），評估是否有類似「資料已存在、只差前端顯示」的
  低風險子項可拆。
- `WMOM-20260505-26-a`（SCADA Service/Maintenance state 降低版子項）仍在等劉老師核准，
  自動排程無真人回覆，維持不接。
- 其餘決策樹狀態與前次 session 一致：`WMOM-20260504-11`（cost ledger）/
  `WMOM-20260513-01`（UI v2）/ `WMOM-20260509-F6`（PostgreSQL）皆需劉老師決策或素材，
  `WMOM-20260505-27`/`-28`（保護電驛/齒輪缺陷模型）皆多日工作，未評估是否可切降低版
  子項（可仿 `-25-a`/本次手法評估看看）。
