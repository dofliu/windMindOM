# Work-log — WMOM-20260606-01 CreateWorkOrderWizard component render 測試

- **日期**：2026-06-06
- **Issue**：WMOM-20260606-01（EPIC-M5 測試覆蓋擴大）
- **分支**：`claude/issue-WMOM-20260606-01-2026-06-06`
- **類型**：test（前端 component render 測試）
- **persona**：autonomous worker（cron 觸發 session）

---

## 背景 / 決策樹

- Preflight 全綠：backend 638 passed / 1 xfailed、frontend 366 passed（baseline）。
- 飛輪健康：上個 session InventoryDetailDrawer render 測試 PR #87 已 auto-merge 進 main。
- Stack-aware：22 筆 open PR 全為飛輪上線前 stale draft（#30–#68），**無進行中 WIP**，無需接續他人半成品。
- 決策樹 #1（blocker）/ #2（baseline regression）/ #3（CI 飛輪壞）皆無 → 落 **#4 乾淨 autonomous 工作**。
- 依前份 handoff（WMOM-20260605-08）next-step 候選清單，挑 **CreateWorkOrderWizard**
  （`components/workflow/CreateWorkOrderWizard.tsx`，466 行）—— 四個未測 workflow 元件中**最小、
  最自包含**（不依賴 useCurrentUser，僅 ThemeProvider），且引入本系列尚未覆蓋的
  **多步驟 wizard 形態**（step machine + 逐步 gating + buildRequest 序列化）。

## 元件契約（被測重點）

`CreateWorkOrderWizard` 是 `/admin/workflow` 工單 tab 的「建立工單」3 步精靈：
- **Step 1 選風機**：從 active farm turbines 列表（依 name localeCompare 排序）；FAULT 卡顯 ⚠；
  顯示功率/風速摘要；`turbineId = t.name`（後端 turbine_id 用 name string）；未選 → Next disabled。
  支援 `preselectTurbineId` 預帶入。
- **Step 2 工單細節**：type / priority Select（完整選項）+ title* / description*（trim 後皆需非空才解鎖 Next）
  + 來源警報碼（選填）。
- **Step 3 派工 + 工時**：assignee UUID（選填）/ crew_size（夾限 1–20）/ estimated_hours（選填）
  + summary 檢閱卡（風機 / 類型·優先級 / 標題）。
- **buildRequest 序列化**：所有字串 trim；空選填欄（source_alarm_code / assignee_id / estimated_hours）
  送 `null`；estimated_hours 非空走 `Number()`；crew_size 夾限。
- **async 送出**：submitting 中態（可見文字「建立中…」、鈕 disabled 防重送）；onSubmit reject →
  ⚠ 錯誤卡 + **不關閉** + 鈕回復可按。
- **關閉路徑**：遮罩（role=dialog overlay 本身）/ ✕ / 取消 → onClose；content wrapper `stopPropagation`。

## 本次完成

**新增** `components/workflow/__tests__/CreateWorkOrderWizard.test.tsx`（**32 tests**，含 code-reviewer 採納後補的 4 筆）：

- 工廠 `makeTurbine` 結構式滿足 `TurbineData`（僅填精靈用得到欄位，其餘合理 default；不用 `as`）。
- render wrapper 僅需 `ThemeProvider`（本元件不依賴 useCurrentUser）。
- 步驟導覽 helper：`selectTurbine`（以 name regex 命中，因 accessible name 含 status pill + power 文字）/
  `gotoStep2` / `gotoStep3`。
- 覆蓋契約：
  - 殼層：dialog aria-label + h2 標題 zh/en（en 不外洩中文）/ step indicator「第 N 步 / 共 3 步」vs
    「Step N of 3」/ footer 鈕在各 step 的出現規則（step 1 無上一步·無建立鈕）
  - Step 1：空列表提示卡 zh/en / localeCompare 排序（WT-01 在 WT-02 前）/ FAULT ⚠ 有無 /
    功率風速 toFixed 格式 / 未選 Next disabled→選後啟用 + aria-pressed / preselectTurbineId 預選解鎖
  - Step 2：欄位齊備 + step indicator 更新 / title|description gating（任一空 disabled、純空白 trim 後不算）/
    Back 回 Step 1 保留已選風機 / type·priority Select 完整選項
  - Step 3：派工欄位 + 建立鈕（無下一步）/ summary 卡反映風機·類型·標題 / crew_size 夾限 >20→20、<1→1
  - 送出：完整 request（trim 值 + 空選填送 null + estimated_hours Number 轉型）/ estimated_hours 空→null
    + source_alarm_code·assignee trim 值 / submitting 中態文字「建立中…」+ disabled / onSubmit reject →
    ⚠ 錯誤卡 + 不 onClose + 鈕回復可按
  - 關閉路徑：遮罩 / ✕ / 取消 → onClose；content（h2）點擊 stopPropagation 不 onClose

## 實作中兩個查詢眉角（記錄供下個 session）

1. **送出鈕 accessible name 恆為 aria-label「建立工單」**（aria-label 蓋過可見文字）→ 不能用
   `getByRole('button', {name:'建立中…'})` 驗 submitting 中態；改以 `findByText('建立中…').closest('button')`
   再斷言 disabled。getByRole('button',{name:'建立工單'}) 在其他 test 仍可用（命中 aria-label）。
2. **RTL `getByText` 比對的是元素的「直接 text node」串接**（getNodeText），summary 類型行
   `{typeLabel} ·{StatusPill}` 會被拆成「故障維修 ·」→ `getByText('故障維修')` exact 失敗；
   改用 `expect(review).toHaveTextContent('故障維修')` 做子字串斷言。

## Verify

- `npx tsc --noEmit` → 0 error
- `npx vitest run`（full）→ **398 passed**（366 baseline + 32 新，零 regression）
- `npx vite build` → OK
- backend 未動：638 passed / 1 xfailed 不受影響

## code-reviewer（採納情形）

對 staged diff 跑 `code-reviewer` subagent，回報 3 must-fix / 5 should-fix / 3 nice-to-have，採納如下：

- **採納 must-fix 1**（summary 斷言用 `as HTMLElement` 違反本檔 no-cast 宣示 + null 靜默失敗）：
  改為 `parentElement` 取值後 `if (!review) throw`，移除 `as`。
- **採納 must-fix 2**（crew_size 夾限只驗 DOM value 未驗序列化契約 → 可能 false positive）：
  保留 DOM 即時反映 test，**另加** 一筆「夾限值真的寫進送出 request」（>20 → 點建立 → onSubmit 收
  crew_size=20），驗證 buildRequest 讀的是夾限後 state。
- **採納 must-fix 3**（gotoStep2/gotoStep3 helper 硬編碼繁中 label，與 renderWizard lang 脫鉤）：
  加 `L(lang)` label 對照 + helper 收 `lang` 參數（default 'zh'），解除隱性耦合。
- **採納 should-fix 1**（preselectTurbineId 缺數字 id 反例）：補一筆——但**修正 reviewer 的錯誤前提**：
  元件把 preselectTurbineId 直接當 turbineId 初值（非與 turbine 列表比對），故傳 '2' 時兩卡皆不高亮、
  **但 Next 仍解鎖**（turbineId 非空）。test 改為斷言「無卡高亮 + Next enabled」，正確文件化此契約。
- **採納 should-fix 2**（description 純空白 trim 對稱測試）：補一筆 description 全空白 → Next disabled。
- **採納 should-fix 4**（DEFAULT_TURBINES id/name 倒置無說明）：加 comment 說明刻意錯開以驗 name-as-id 契約。
- **採納 should-fix 5**（gotoStep3 title/desc 與 summary 斷言耦合）：gotoStep3 加可覆寫 title/description 參數。
- **採納 nice-to-have 1**（成功 resolve 不自動 onClose）：補一筆 onSubmit resolve → onClose 未被呼。
- **不採納 should-fix 3**（estimated_hours NaN guard path 漏測）：經實證 jsdom 對 `type="number"` input
  的 `fireEvent.change('abc')` 會**值清空為 `''`**（同真實瀏覽器 sanitization），estimatedHours 落 ''
  → 走 null 分支，**NaN guard 無法經 UI 觸發**（屬防禦性 dead-code）。寫 reviewer 建議的 test 反而會
  得到 false 結果。故不寫此脆弱測試（探針驗證見下）。
- **不採納 nice-to-have 2/3**（Step 2 state 保留再進、en step indicator step2/3）：低價值，既有 Back 測試
  已驗風機 state 保留、zh step indicator 已覆蓋三 step 切換，不重複。

**探針驗證 must-not（NaN guard）**：臨時測試 `<input type="number">` + `fireEvent.change({value:'abc'})`
→ captured value 為 `''`，證實 jsdom sanitize 行為，故 SF3 不可經 UI 觸發。

## 下一步（給下個 session）

同系列剩餘未測 workflow 元件（render 測試方向，由小到大）：
- `CreateMaterialRequestWizard.tsx`（690）—— 另一個多步驟 wizard，狀態較複雜（料件選擇 + 數量）
- `MaterialRequestDetailModal.tsx`（902）/ `WorkOrderDetailModal.tsx`（933）—— 全螢幕 detail modal，
  含多 section + 動作鈕，需 mock 多個 callback
- `TurbineDetail`（1056，monitoring 側）

非 render 方向：
- M5-2 ChromaDB 整合 🔵（需劉老師拍板嵌入式依賴 + 向量檔來源）
- stale PR triage（#30–#68 共 22 筆 pre-flywheel draft，建議劉老師決定批次關閉或逐一 rebase）
