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
2. `eventTone()`：`fatigue → 'danger'`、`fault_lifecycle → 'muted'`（review 後修正，見下方）
3. `EVENT_HEX`（chart ReferenceLine 顏色）：各配一組 light/dark hex，色調與既有 5 色區隔
4. `eventTypeLabel()` zh 分支：`fatigue → '疲勞'`、`fault_lifecycle → '故障週期'`
5. `enabledEventTypes` 初始 state：兩者預設 `true`（跟既有 5 型一致，預設全開）

**tone 選擇說明（review 後修正）**：初版把 `fault_lifecycle` 跟既有 `fault` 都給
`warn`，code review should-fix 指出這是本次新增事件類型裡第一次出現 tone 撞色——
`StatusPill` 的 tone 只對應固定一組色，`fault`/`fault_lifecycle` 在事件清單/詳情面板
的徽章會呈現完全相同顏色，只能靠文字辨識，跟圖表上 `ReferenceLine`/toggle 按鈕走
`EVENT_HEX`（兩者確實不同色）的體驗不一致。已改為 `fault_lifecycle → 'muted'`
（7 種 `PillTone` 扣掉既有 5 種 + 新增 `fatigue→danger`，`muted` 是唯一未被真實事件類型
佔用的剩餘 tone；`fault_lifecycle` 是模擬自動追蹤的背景生命週期事件，語意上也適合較不
搶眼的 muted，跟直接注入的 `fault` 用搶眼的 `warn` 區分開）。`fatigue` 維持 `danger`
（結構疲勞風險語意上比一般事件更需要引起注意）——**但 review 也指出**這個 tone 是對
「所有」疲勞事件（含 Lv1→Lv2 輕微升級）一律给最搶眼的紅色，並未依 `payload.toLevel`
分級，跟 `TurbineDetail.tsx::FATIGUE_ALARM_LEVELS`（`danger` 只給最高 Lv4，Lv1-3 走
`ok/info/warn/amber`）並非真正「分級邏輯一致」，只是 tone 名稱剛好都叫 danger——
初版 work-log「保持跨頁一致」的措辭有過度宣稱之嫌，已在此更正說法。改成依 level 分級
需要把 `eventTone(et: string)` 簽名改成能拿到完整事件物件（含 `payload`），是比「補查表
entry」更大的改動，刻意不在本次處理，已在 `ISSUES.md` `WMOM-20260928-05` 補記
follow-up（見該 issue 內文）。

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

**code-reviewer subagent（獨立 async review，43 次工具呼叫）：Approve，0 must-fix，
3 should-fix + 3 nice-to-have**。獨立重跑 `npx vitest run components/__tests__/
HistoryPage.test.tsx`（27 passed）與 mutation-verify（`git stash` 還原元件本體 → 4
新測試如預期全部 fail、23 舊測仍過 → 還原）完全重現我的驗證結論；另獨立重新 grep
`event_type="` 確認 7 種全數命中、`HistoryPage.tsx` 內 grep `EventType`/`event_type`
確認沒有第 6 個查表點被漏掉。3 個 should-fix：

1. **work-log 對 `fault_lifecycle` 的 `end_timestamp` 聲稱不準確，已修正**：初版
   work-log 誤寫「`fatigue`/`fault_lifecycle` 事件本身沒有 `end_timestamp`」，reviewer
   讀 `data_broker.py:854-859` + `storage.py:561-585` 發現 `fault_lifecycle` 的
   「start」事件在故障清除時會被 `close_open_events()` 回填 `end_timestamp`（具備真實
   區間語意），只有 `fatigue` 才是真的完全沒有 `end_timestamp`。已在下方「誠實揭露」
   段落更正這個技術陳述（結論「本次不擴大修復 `ReferenceArea`」不變，只是原本的理由
   前提有誤）。
2. **`fault_lifecycle` 與既有 `fault` 共用 `warn` tone 在徽章上撞色，已修復**：改為
   `muted`（唯一未被真實事件類型佔用的剩餘 tone），圖表 `ReferenceLine`/toggle 按鈕仍
   走各自獨立的 `EVENT_HEX` 顏色不受影響。詳見上方「tone 選擇說明」。
3. **`fatigue` tone 對所有嚴重度一律 `danger`，未依 level 分級，且初版「跨頁一致」措辭
   過度宣稱**：reviewer 認同這需要改 `eventTone()` 簽名才能依 `payload.toLevel` 分級，
   超出本次「純粹補查表」的刻意收斂範圍，不強制修，但已更正 work-log 措辭 + 在
   `ISSUES.md` `WMOM-20260928-05` 補記 follow-up 子項。
3 個 nice-to-have：①`EventComparisonView.tsx` 有自己獨立一份 `eventTone()`，已內建
`fault_lifecycle` 但漏了 `fatigue`（fallback 到 `muted` 且 `Select` 篩選選項缺該項，
非本次 diff 觸碰的檔案，不是隱形只是顏色/篩選不完整，已在下方誠實揭露段落記錄具體
座標供後續 session 接手）；②`eventTypeLabel()` en 分支技術債（同意暫不修）；
③`fault_lifecycle`/`grid` 的 hex 色相偏近，純美觀建議未修。

修復 should-fix #2 後重新跑：`npx vitest run components/__tests__/HistoryPage.test.tsx`
→ 27 passed（無需改測試斷言，未針對特定 tone 值斷言）；`npx tsc --noEmit` 0 error。

## 誠實揭露 / 未修範圍

- `eventTypeLabel()` 對 `lang==='en'` 分支本來就是 `return et`（直接印原始英文字串，如
  `"grid"`/`"fault"`，並非真正翻譯過的英文標籤）——這是全部既有 5 型共享的既有技術債，
  非本次引入。`fatigue`/`fault_lifecycle` 沿用同款既有行為，未額外補齊英文翻譯，刻意
  把本次修復範圍聚焦在「登記表遺漏導致真實資料隱形」這單一問題，不蔓延到既有 i18n
  缺口（若劉老師認為值得修，建議另開 issue 一次盤點全部事件類型的英文標籤；
  `EventComparisonView.tsx` 已有現成翻譯 `u('Fault lifecycle', '故障生命週期')` 可抄，
  成本低）。
- **`EventComparisonView.tsx`（情境比較路徑，非本次 diff 觸碰的檔案）有自己獨立一份
  `eventTone()`（該檔第 32-39 行），已內建 `fault_lifecycle→warn`，但漏了
  `fatigue`（fallback 到 `muted`，且第 176-186 行附近的 `Select` 篩選選項清單也沒有
  `fatigue` 選項，使用者只能選「全部」才看得到，無法單獨篩選）——不是完全隱形（該頁
  `eventTypeFilter` 預設空字串＝全部，fatigue 事件仍會顯示），嚴重度遠低於本次修的
  bug，未修，留給後續 session。
- 圖表上的 `ReferenceArea`（用於渲染色帶的區間事件）目前只認 `grid`/`wind` 兩型。
  **更正**（初版此處聲稱有誤，經 code review 指正）：`fatigue` 事件確實沒有
  `end_timestamp`；但 `fault_lifecycle` 的「start」事件在故障清除時會被
  `data_broker.py` 呼叫的 `storage.py::close_open_events()` 回填 `end_timestamp`，
  具備真實區間語意——`ReferenceArea` 尚未支援渲染它的故障期間色帶，是既有限制。本次
  刻意聚焦在「登記表遺漏導致整組隱形」這個核心問題，未擴大處理 `ReferenceArea`（現況
  是「看得到瞬時標記，但看不到完整期間色帶」，比修復前「完全看不到」已是淨改善），
  建議另開 low-risk follow-up issue。

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
