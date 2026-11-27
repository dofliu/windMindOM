# 2026-11-27 — 例行巡檢卡（WMOM-20261126-05）

> Session 類型：實作
> 主導：Claude（劉老師：「照你的建議做例行巡檢卡」）
> 結果：done，DEC-20261127-04。另開 WMOM-20261127-03。

---

## 1. 決定了什麼

issue 列的三件事：

1. **清單從哪裡來**：定檢工單沒有逐項清單，所以定一份固定的 Z72 清單（11 項，技師上塔的路線），放在 `server/inspection_checklist.py`。每一項看哪些量測是手冊層級的知識；事件碼屬於哪一項由 PLC 的判定規則推出來，不手寫、不讀故障情境。
2. **依什麼排**：最近 30 天的警報 / 跳機、量測和同場發電中的機組比偏高 / 偏低（6 小時或最後 1 小時）、未結案的故障維修工單。有證據的往前，沒有的維持原訂順序。
3. **怎麼評分**：答案是建單當下這台機組實際的故障（含還沒到門檻的劣化、潛伏的故障），看它的項目有沒有往前、有沒有標注意；沒有故障卻標注意算誤報。

## 2. 改了什麼

- `server/inspection_checklist.py`（新）：清單、`code_items`（事件碼 → 項目）、`item_of_component`（評分用）。
- `server/briefing.py`：`build_inspection_card`、`score_inspection_card`、`card_kind_for`、`score_any_card`；`_signal_items` 可以指定時間窗（故障出勤卡用預設值，行為不變）；`CARD_VERSION` 1.2。
- `server/om_loop.py`：定檢 / 預防保養工單建立時產生例行巡檢卡；補卡與定期檢查也涵蓋這兩種。
- `server/routers/operations.py`：評分端點依卡種核對。
- 前端：`briefingService.ts` 加例行巡檢卡的型別；`BriefingCard.tsx` 加 `InspectionCardView`；工單詳情與現場的「我的工單」對定檢 / 預防保養工單也顯示卡片。
- `docs/integration/external_api_v1.md` §3.10：例行巡檢卡的格式與旗標，版本表加一列修訂（端點沒變）。

## 3. 驗證

- `test_inspection_card.py` 8 項：每個 PLC 事件碼都對得到一項、量測給得出去、部件涵蓋所有故障情境、做卡的程式不讀故障情境；健康機組維持原訂順序、不標注意；**潛伏的變壓器過熱（沒有任何警報）讓變壓器從第 2 排到第 1**、其他項目不標注意、評分 moved_up / flagged；定子溫度感測器漂移的 264 警報與未結案的 240 工單把發電機與主軸承排到前三；卡片沒有故障情境與工單的自由文字；預防保養工單同一種卡、評分端點依卡種。
- `test_briefing.py` 改三處：定檢工單現在有卡（試運轉沒有）。
- 前端 vitest 1536 passed（`BriefingCard.test.tsx` 加 3 項）、`tsc` 無錯。

## 4. 下次接手

- WMOM-20261127-03：依風場時鐘定期開定檢工單——不然仿真風場自己運轉時不會有定檢，潛伏故障不會被發現。
- 清單、權重、時間窗是第一版，請劉老師看過。
