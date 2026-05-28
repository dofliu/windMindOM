# 2026-05-28 — Frontend 元件層回歸測試擴充：workflow statusUtils + reporting formatters 純函式

> Autonomous daily worker session（2026-05-28 20:00 Asia/Taipei，雲端 sandbox）。
> Issue：**WMOM-20260528-01**（新開）。Branch：`claude/upbeat-davinci-5K3LM`。

---

## 1. 為什麼做這個

Preflight baseline 完全綠（backend `pytest modules/{workflow,cost,reporting}/tests/` →
**570 passed / 1 xfailed**；無 blocker、無 regression）—— 決策樹第 1、2 條皆不觸發。

依 handoff 候選清單，5/27-01 與 5/27-02 兩份 wrap-up 都把「**擴大 frontend 元件層測試
（CostPage / FarmOverview）**」列為下次候選；`frontend/vitest.config.ts` 本身也留了 TODO
指向同一方向。這是 5/26 導入 vitest + RTL 基礎設施（WMOM-20260526-01）後唯一自然的續作：
**完全 autonomous、無設計歧義、單 session 可完工**（M4 已 100%；WMOM-20260504-12 等劉老師
本機長跑驗收；WMOM-20260519-01 退料 guard 需劉老師會計語意決策；WMOM-20260513-02
demo orchestrator 2-3d 且含 product decision，過大）。

### 切入點選擇：先測「最高 ROI、零脆弱」的純函式層

目前只有 2 個 hook 測試。元件層測試最大的價值與最小的脆弱性，落在**被各畫面共用的純函式**：

- `frontend/components/workflow/statusUtils.ts`：**16 個 exported 純函式**，餵 workflow 全部
  4 個 tab（orders / approval / material / inventory）的 enum→label（雙語）、enum→tone
  （StatusPill 配色）、Asia/Taipei 日期格式化。封存了 WMOM-20260509-06 code review
  **Must-fix #1**（`fmtDateTime`/`fmtDate` 改用明確 `Intl.DateTimeFormat(..., timeZone:'Asia/Taipei')`
  防 browser timezone 漂移）。
- `frontend/components/reporting/formatters.ts`：`fmtMoneyDecimal` / `fmtPct`，是
  WMOM-20260509-09 code review **Should-fix #1** 抽出的共用層（原本兩個 panel 各自定義、
  null 行為分歧）。

這層純函式無 React / 無 async / 無 DOM → 測試確定性高、不脆弱，且**不需動 vitest.config.ts**
（不引入 jsdom DOM matcher / setupFiles），保持基礎設施零變動。

---

## 2. 完成內容

### 2.1 `frontend/components/workflow/__tests__/statusUtils.test.ts`（新，19 tests）

- **label 雙語窮舉**（10 個 label 函式）：用 service 匯出的 `*Values` runtime 陣列
  （`WorkOrderStatusValues` / `PriorityValues` / `MaterialRequestStatusValues` …）迭代窮舉，
  期望值用 `Record<Enum, [en, zh]>` 型別宣告 → **compile-time 窮舉**：未來新增 enum 值卻
  漏補期望字串時 `tsc` 立刻紅；改文案則 runtime 立刻紅（迫使刻意更新）。
- **tone 窮舉**（4 個 tone 函式）：`Record<Enum, PillTone>` 期望表，確認 switch 對每個
  enum 值都回明確 tone（無漏 case → 不回 undefined）。
- **日期格式化**：`fmtDateTime` / `fmtDate` 驗明確 Asia/Taipei（UTC+8、無 DST）：
  `2026-01-15T18:30:00Z` → `2026-01-16 02:30`（**跨午夜進位**證實套了時區，不隨 runner
  timezone 漂移）+ null→「—」+ 無法解析→原樣回傳（含註解標明此為 source 現行 fallback）。
- lang fallback：用雙重 cast 餵型別外 lang 值，真正打到「非 'zh' → en」分支。

### 2.2 `frontend/components/reporting/__tests__/formatters.test.ts`（新，9 tests）

- `fmtMoneyDecimal`：null / undefined / 空字串 / 非有限值 → 「—」契約；小額 / 千級 / 百萬級
  分級（含 **1e3 與 1e6 上下界 + 999_999.99 鄰界** 鎖住分級門檻方向）；負值保留負號依絕對值
  分級；`parseFloat` 寬鬆解析（附註解說明為副作用、非設計）。
- `fmtPct`：0-1 → 一位小數百分比；NaN → `'NaN%'`（鎖住 source 目前未防禦行為，附註解：
  呼叫端型別已保證有限數、無真實缺值風險，加 guard 時此測試會提醒同步）。

---

## 3. Verify（zero regression）

| 項目 | 改前 | 改後 |
|---|---|---|
| vitest | 11 passed（2 hook 檔） | **39 passed（4 檔：+19 statusUtils +9 formatters）** |
| `tsc --noEmit` | 0 errors | **0 errors** |
| `vite build` | 918 kB / 成功 | **918.27 kB / 成功**（測試檔未進 production bundle，大小持平） |
| backend `pytest modules/{workflow,cost,reporting}/tests/` | 570 passed / 1 xfailed | **未動**（純 frontend 新增，無 backend 變更） |

---

## 4. Code review

跑 `code-reviewer` subagent 對 staged diff：**2 must-fix / 3 should-fix / 2 nice-to-have，
Needs revision → 採納後 Approve**。reviewer 確認 UTC+8 時區計算數學正確、窮舉機制
（`*Values` + `Record` 期望表）設計良好可真正保護完整性。

| # | 級別 | 內容 | 處置 |
|---|---|---|---|
| 1 | must | `fmtPct` 對 NaN 無防禦且無測試點出 | **折衷採納**：查 caller（MonthlyReportPanel KPI ratio，型別 `number`）確認 null/undefined 被簽章擋住、非真 bug；**不動 source**（無真 bug + 無 product decision），補 1 條鎖住現況 `NaN→'NaN%'` 的 regression test + 註解使契約顯性 |
| 2 | must | `fmtDateTime('not-a-date')` 原樣回傳被測試確認但未標注語意 | **採納**：加註解說明此為 source 現行 fallback（壞資料外顯而非隱藏），鎖住防非預期改動、非最終文案決策。不動 source |
| 3 | should | 缺負值 1e3 邊界（-1000） | **採納**：加 `-1000 → €-1.00k` |
| 4 | should | lang fallback 兩條都測 'en'，未打到退化邏輯 | **採納**：加雙重 cast 型別外 lang 值真正打 fallback |
| 5 | should | 缺 999_999.99 鄰界（k/M 分級方向） | **採納**：加 `999_999.99 → €1000.00k` |
| 6 | should→nice | describe 前綴英文斜線風格 | reviewer 自行降級（與既有 `useCostData.test.ts` 一致），不動 |
| 7 | nice | parseFloat 寬鬆解析測試加警告註解 | **採納**：加註解標明為副作用 |
| 8 | nice | 缺 environment pragma | **不採納**：與既有 hook 測試一致（無 pragma），加反而不一致 |

採納後重跑：vitest **39 passed** / tsc 0 errors，零邏輯影響。

---

## 5. 下次 session 接手建議

- 本 PR 後 frontend 測試 39 passed（hook 2 檔 + util 2 檔）；backend baseline
  `570 passed / 1 xfailed` 完全確定性，preflight 應一次就綠。
- **元件層測試續作**：純函式層已覆蓋；下一步可往「真 component render 測試」推進
  （CostPage / FarmOverview / 各 workflow Panel），但需先在 `vitest.config.ts` 補
  `setupFiles: ['@testing-library/jest-dom/vitest']`（config 內 TODO 已標）+ 處理元件的
  data hook / service mock，脆弱性較高、建議獨立 session。CostPage 的 `fmtMoney`/`fmtPct`/
  `fmtKwh`（CostPage.tsx:45-52）目前未 export，若要測需先抽出。
- 其他候選：WMOM-20260513-02 demo orchestrator（含 INSPECTION over-use product decision，
  需劉老師）/ WMOM-20260519-01 退料 guard（需劉老師會計語意）/ WMOM-20260509-F6
  PostgreSQL row-lock（M6、需 docker postgres）。

---

## 6. 檔案異動清單

```
新  frontend/components/workflow/__tests__/statusUtils.test.ts   （19 tests：label 雙語窮舉 + tone 窮舉 + Asia/Taipei 日期）
新  frontend/components/reporting/__tests__/formatters.test.ts   （9 tests：fmtMoneyDecimal 分級/邊界/null + fmtPct）
改  work-logs/2026-05/2026-05-28-frontend-statusutils-formatters-tests.md（本檔）
改  ISSUES.md / STATUS.yaml
```
