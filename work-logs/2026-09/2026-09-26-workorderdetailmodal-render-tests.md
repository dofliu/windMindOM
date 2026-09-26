# 2026-09-26 — WMOM-20260926-04：`WorkOrderDetailModal.tsx`（legacy mock 版）component render 測試

- **Issue**: WMOM-20260926-04（第七個 autonomous session）
- **Branch**: `claude/inspiring-mccarthy-l3cu69`
- **Milestone**: 工程基礎設施 / 測試覆蓋擴大（EPIC-M5 測試覆蓋擴大系列延續）

## 背景

上個 session（WMOM-20260926-03）把 `DEC-20260720-02` 情境比較分析 epic 的 PR C Phase 1
完整收尾，M6 critical path 上其餘可自動接手項目（PostgreSQL row-lock 測試需 docker、
HTTPS 部署配置需先定部署目標）都卡在需要 docker 環境或人工決策。物理模型強化
（WMOM-20260505-23~28）依 routine 優先級排在工程基礎設施之後（學術深度非商業
must-have）。

本 session 開工前先確認 M5-5「/field/ mobile Part B-2」在 TODO.md 頂部摘要表被標記為
「待續」其實是**過期資訊**——實查 `WMOM-20260608-02` 該 issue 早在 2026-06-08 就已完成
（含 backend signature/photo 欄位 + frontend `MyOrdersMode.tsx` 完工流程），只是
`ISSUES.md` 頂部「未來大目標」摘要表的那一行沒有回頭更新成 ✅ done。同樣，
`WMOM-20260505-21` 的 Status 欄位仍停在 `in_progress`（標註「前端待補」），但其
follow-up `WMOM-20260926-01`（前端 + hook + ownership 限制三項）已在稍早 session 全數
完成並標 done——這也是尚未回頭同步的過期狀態（本次一併更正，見下方）。

轉向逐檔盤點 `frontend/components/**/*.tsx` 是否每支都有對應 `__tests__/*.test.tsx`，
找到 8 支缺測試的檔案，其中多數是 `components/ui/` 的極薄純展示 primitive
（`Btn`/`Card`/`Field`/`Logo`/`PageHeader`/`Stat`/`ScenarioMountBanner`，多半靠其宿主頁
面測試間接涵蓋渲染路徑，非本次目標）與 `ScenarioTrendView.tsx`（情境比較 A1 的既有子元
件，已有 `ScenarioCompareView`/`ScenarioDetail` 系列測試間接覆蓋主要邏輯）。真正獨立、
高風險、零覆蓋的是 `components/WorkOrderDetailModal.tsx`（315 行）——**先確認它不是
死碼**：grep 確認 `App.tsx:33` import + `App.tsx:595` 實際渲染（`selectedWorkOrder` 由
`MaintenanceHub` 的 `onSelectWorkOrder` 觸發），是 'maintenance' 導覽路徑下真實可達的
生產程式碼，且與 `components/workflow/WorkOrderDetailModal.tsx`（backend
`WorkOrderResponse` 版本，已有獨立測試，`workflow/WorkOrderDetailModal.tsx:4` 註解本身
就寫明兩者要區分）是完全不同的兩支元件、不是重複程式碼可以刪除。認領此檔補測試。

## 本 session 做的事

新增 `frontend/components/__tests__/WorkOrderDetailModal.test.tsx`（新檔，18 tests，
含 code review 後補的 1 則），**未修改元件本體任何一行**（`git diff` 對
`WorkOrderDetailModal.tsx` 為空）。延續 `MaintenanceHub.test.tsx`/
`FaultInjectionPanel.test.tsx` 系列既有 render 測試範式（`ThemeProvider` 包裹 +
jest-dom matcher + `afterEach cleanup`）。元件純由 props 驅動（`workOrder`/
`technicians`/3 個 callback）、無 fetch/hook，是本系列中最單純的一支。

涵蓋：

1. **標題與詳情**：標題含工單 id 末 6 碼；風機名稱/技師名稱/故障描述正確顯示；
   `technicianId` 查無對應技師時 fallback 顯示 `N/A`；狀態 pill 依 `OPEN`/
   `IN_PROGRESS`/`COMPLETED` 三態顯示對應文字。
2. **關閉互動**：點擊遮罩（`role="dialog"` 本身）觸發 `onClose`；點擊 Close 按鈕觸發
   `onClose`；點擊內容卡片區域（`onClick={e => e.stopPropagation()}`）不冒泡、不觸發
   `onClose`。
3. **備註與 Save**：備註 textarea 可編輯；Save 呼叫 `onUpdate(workOrder.id, {notes,
   photos})` 帶最新值；照片上傳（`FileReader` 轉 base64）後渲染成 `<img>` 並可移除；
   無照片時顯示「至少需要一張照片」提示且 Complete 按鈕 `disabled`。
4. **Complete 流程**：無照片時點擊 Complete 不觸發 `onComplete`（disabled 阻擋）；有
   照片時點擊，`onComplete` 收到 `{...workOrder, notes, photos, status: COMPLETED}`。
5. **COMPLETED 唯讀模式**：textarea disabled；無 Save/Complete 按鈕、無上傳/移除控制；
   無照片時顯示 `No photos uploaded.`；有照片時仍渲染圖片但不顯示「至少需要一張照片」
   提示。

### jsdom 環境限制與繞過手法

- 本環境 jsdom 版本沒有原生 `DataTransfer` global（`new DataTransfer()` 會
  `ReferenceError`），無法用一般教學手法建構 `<input type="file">` 的 change event。
  改手刻 `makeFileList(files: File[])`：把 `File[]` 陣列補上 `item(i)` 方法，滿足
  `FileList` 介面的最小讀取需求（元件 `handlePhotoUpload` 用
  `files.length`/`files.item(i)` 走訪，未用到其他 `FileList` API）。
- `FileReader.readAsDataURL` 原生是非同步（`onloadend` 在下個 microtask/macrotask
  才觸發），測試用 `FakeFileReader` 替換 `global.FileReader`，同步呼叫 `onloadend`
  簡化斷言（元件邏輯本身對「非同步或同步觸發 onloadend」無差異依賴，不影響覆蓋真實性）。

## Mutation-verify 記錄

逐項「改回舊邏輯 → 確認新測真的會 fail → 再還原」，全部用 `/tmp/wom-mutation-backup/`
備份（非 `git checkout`，因新檔尚未 commit 前用 `cp` 更保險）：

1. 拿掉 `disabled={photos.length === 0}` → 「Complete 按鈕 disabled」測試如預期 fail
   （其餘 16 測皆過，包含「無照片時點擊不觸發 onComplete」——見下方誠實揭露）。
2. 把 `handleComplete` 內 `if (photos.length > 0)` 改成 `if (true)`（拿掉邏輯層 guard，
   只留 DOM 層 `disabled`）→ **17 測全過，無測試偵測到此變更**（見下方誠實揭露）。
3. 拿掉技師 `|| 'N/A'` fallback → fallback 測試如預期 fail。
4. 把內容卡片 `onClick={e => e.stopPropagation()}` 改成 `onClick={() => {}}` → 2 個
   測試如預期 fail（「不冒泡」測試 + 遮罩點擊測試，因為此時所有點擊都會冒泡到遮罩層）。
5. 把 `statusLabel` 的 `IN_PROGRESS` 分支拿掉（改成恆真條件）→ IN_PROGRESS pill 文字
   測試如預期 fail。

每次還原後重跑本測試檔確認回到 17 passed 全綠再進行下一項。

## code-reviewer subagent review

**Approve，0 must-fix，2 should-fix + 3 nice-to-have，2 個 should-fix 已採納修復**：

1. 🟡 **Should-fix（已修復）**：reviewer 獨立跑 mutation 實驗發現「At least one photo
   is required…」提示文字在元件原始碼只受 `!isCompleted` 控制（與 `photos.length`
   完全無關），但原測試只在「無照片」情境斷言其出現，測試名稱易誤導成「依照片數量
   gating」。新增 1 則測試明確鎖住「有照片、非 completed 狀態下提示仍然顯示」的真實
   行為（+1 測，17→18）。
2. 🟡 **Should-fix（已修復）**：「無照片時點擊 Complete 不觸發 onComplete」測試旁補
   程式碼註解，明講此測試只鎖住 DOM 層 `disabled` 屬性、`handleComplete` 內部邏輯層
   guard 因 jsdom 對 disabled button 不派發 click handler 而無法被此測試獨立驗證
   （reviewer 用獨立 mutation 實驗重新驗證同一結論）。
3. 🟢 3 個 nice-to-have（未採納，記錄供未來第二輪測試參考）：`technicianId: null`
   情境（型別允許但目前只測非法 id 999，行為結果相同但型別分支未覆蓋）；一次上傳多張
   照片 / `files` 為 `null` / `reader.result` 非 string 等邊界分支；Save 不觸發
   onClose/不改 status 的反向斷言。

reviewer 也獨立確認：jsdom `FileList`/`FileReader` mock 手法合理、未製造假陽性或縮小
涵蓋範圍；其餘 16 則既有測試依賴實際動態邏輯分支、非同義反覆。

## 誠實揭露

- **`handleComplete` 內部 `if (photos.length > 0)` 邏輯層 guard 目前沒有測試獨立鎖住**
  （mutation #2，reviewer 獨立驗證同一結論）。原因：`fireEvent.click` 在原生
  `disabled` 的 `<button>` 上，jsdom 不會派發 `click` 事件的 React handler（瀏覽器
  原生行為，非 testing-library 限制），所以只要 DOM 層 `disabled` 屬性還在，測試無法
  觸發到內部 guard 真正執行的路徑。內部邏輯層 guard 是防禦性重複（defense-in-depth），
  此元件現況下無法脫離 `disabled` 屬性單獨測到——已在測試檔對應 `it()` 名稱與程式碼
  註解誠實標註此限制。若未來重構移除 `disabled` 屬性，現有測試會需要重新設計才能鎖住
  該邏輯。
- 本次是純測試新增，元件本體零修改，**無新的生產邏輯風險**。

## 自我測試

- backend：`python -m pytest modules/workflow/tests/ modules/cost/tests/
  modules/reporting/tests/ modules/knowledge/tests/ modules/monitoring/tests/
  modules/auth/tests/ tests/ -q` → **1274 passed, 7 skipped, 1 xfailed**（未動，零
  regression）
- frontend：`npx tsc --noEmit`（0 error）+ `npx vitest run`（**1443 → 1461 passed**，
  68→69 files，+18，零 regression）+ `npx vite build`（OK）

## 附帶發現（housekeeping，已於 ISSUES.md 更正）

- `WMOM-20260505-21` 的 `Status` 欄位仍寫 `in_progress`（前端待補），但其 follow-up
  `WMOM-20260926-01`（前端 + `work_order.finish()` hook + 讀取端點 ownership 限制）已於
  本日稍早 session 全數完成並標 `done`——本次回頭把 `WMOM-20260505-21` 狀態更正為
  `done`（後端 + 前端 + 整合 hook + ownership 限制皆已完整交付，無殘留 sub-task）。
- `ISSUES.md` 頂部「🎯 未來大目標」摘要表 M5-5 行仍寫「my work orders · completion
  （Part B-2 待續）」，但 `WMOM-20260608-02` 早於 2026-06-08 完成該項——本次一併更正該
  摘要表行文字為已完成敘述，避免未來 session 誤判仍有工作可接。

## 下次接手

`components/ui/` 剩餘 7 支零測試 primitive（`Btn`/`Card`/`Field`/`Logo`/`PageHeader`/
`Stat`/`ScenarioMountBanner`）多半是極薄展示元件、已被宿主頁面測試間接涵蓋渲染路徑，
獨立補測試的邊際價值需評估（`ScenarioMountBanner` 較新、較值得優先，其餘 6 支建議先讀
`components/ui/__tests__/StatusPill.test.tsx`/`Charts.test.tsx` 判斷是否有独立分支邏輯
值得鎖，而非為了補而補）；`ScenarioTrendView.tsx` 已有間接覆蓋，優先度低。M6 critical
path 剩餘項（PostgreSQL row-lock 需 docker、HTTPS 部署配置需先定部署目標）與物理模型強化
（WMOM-20260505-23~28）維持既有阻塞狀態，見 ISSUES.md/TODO.md。
