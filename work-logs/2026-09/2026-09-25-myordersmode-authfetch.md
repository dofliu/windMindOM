# 2026-09-25 — `MyOrdersMode.tsx` authFetch 缺口（WMOM-20260924-08）

> Session 類型：實作
> Session 長度：短
> 主導：autonomous worker（cron，v4.1）
> 結果：`WMOM-20260924-08` 完成——`components/field/MyOrdersMode.tsx` 內僅存的一處裸
> `fetch`（`fetchActiveFarmId()`，`GET /api/farms`）改 `authFetch`。**⚠ 但 review 過程中
> 主動遞迴重掃 `frontend/hooks/` 全樹，發現比本 issue 大得多的缺口**：`hooks/useSettings.ts`
> + `hooks/useMaintenanceData.ts` 內對 `SUPERVISOR`-only 端點的**寫入**呼叫也缺
> `Authorization` header，已開新 issue `WMOM-20260925-01`（high priority）追蹤，並回頭
> 取消勾選 cutover 檢查表「前端所有寫入 request 都帶 token」項目。

---

## 1. Session 目標

Preflight：`git checkout main && git pull`（fast-forward 34 commits，含
`WMOM-20260923-10` 全系列 + `WMOM-20260923-08` 皆已在 main）；`mcp__github__list_pull_
requests(state=open)` 回傳空陣列，無殘留 open PR、無 stack 衝突。切回環境注入分支
`claude/inspiring-mccarthy-pijovn`（與 main 同點，無需 merge）。

`TODO.md` + `STATUS.yaml` `next_milestone` 段落都指向同一件事：**WMOM-20260924-08**——
`WMOM-20260923-08` review 時遞迴重掃 `components/` 全樹發現的漏網之魚，
`components/field/MyOrdersMode.tsx:31` 仍是裸 `fetch`，估時 15 分鐘、🔵
autonomous-friendly、範圍單一無設計歧義，選為本次工作。

## 2. 實際完成

### 2.1 主要工作

- **Baseline 自我測試**（全綠，與既有基準一致，無 regression）：
  - backend：`pip install --ignore-installed PyYAML -r requirements.txt
    -r requirements-dev.txt` → `python -m pytest`（6 module + `tests/`）→
    **1103 passed, 7 skipped, 1 xfailed**。
  - frontend：`npm ci` → `npx tsc --noEmit` 0 error → `npx vitest run`
    **1254 passed**（58 files）→ `npx vite build` OK。
- **`frontend/components/field/MyOrdersMode.tsx`**：
  - 新增 `import { authFetch } from '../../services/authClient'`
  - `fetchActiveFarmId()` 內 `fetch(`${API_BASE}/api/farms`)` 改
    `authFetch(`${API_BASE}/api/farms`)`，其餘邏輯（`res.ok` 檢查、`active_farm_id`
    解析）完全不動
- **`frontend/components/field/__tests__/MyOrdersMode.test.tsx`**：新增
  `describe('MyOrdersMode — authFetch 稽核（WMOM-20260924-08）')` block，2 測試：
  1. 已登入（`setAuthToken('test-token-myorders')`）→ mount 觸發的 `GET /api/farms`
     帶 `Authorization: Bearer test-token-myorders` header
  2. 未登入（無 token）→ 同一 GET 不帶 Authorization header（驗證過渡期行為不變）

  沿用檔案既有的 `setFarmsFetch()` helper（`global.fetch` mock），新增測試直接檢查
  `global.fetch` 的 mock call args（`init.headers.Authorization`），比照
  `CostPage.test.tsx` 的 `authHeaderOf()` 手法。

### 2.2 卡住或延後的事

無（本次認領範圍完整完工）。但過程中主動擴大稽核範圍，發現的新缺口已獨立開 issue，見
§2.3 / §7。

### 2.3 重大決策（如有）

無新增架構決策。但因發現 cutover 檢查表的既有勾選項目（「前端所有寫入 request 都帶
token」）實際上不成立，已回頭修正 `docs/product/WMOM-20260716-05_auth_enforcement_
plan.md` §6 該勾選（取消勾選 + 說明根因 + 指向新 issue），避免未來 session 誤信該勾選
去執行 cutover。

## 3. 產出清單

- `frontend/components/field/MyOrdersMode.tsx`（1 行 `fetch` → `authFetch` + 1 行 import）
- `frontend/components/field/__tests__/MyOrdersMode.test.tsx`（+43 行，2 新測試）
- `ISSUES.md`：`WMOM-20260924-08` 標 done + completion summary；新增
  `WMOM-20260925-01`（hooks 層 authFetch 稽核缺口，high priority）；統計表 done
  125→126、total 136→137
- `STATUS.yaml`：`last_updated` / `issue_stats` / M6 progress 同步
- `TODO.md`：最後更新段落 + 可立即接手清單同步
- `docs/product/WMOM-20260716-05_auth_enforcement_plan.md`：§6 cutover 檢查表取消勾選
  「前端所有寫入 request 都帶 token」，改為指向 `WMOM-20260925-01`
- 本 work-log

## 4. 給下個 session 的話

- **優先接手 `WMOM-20260925-01`**（hooks 層 authFetch 稽核缺口，M6 auth cutover
  真正的前置阻塞，比 `WMOM-20260924-08` 嚴重很多——涉及 SUPERVISOR 寫入端點）。issue
  內已列風險排序建議拆法：`useSettings.ts`（sub-task 1，注意「SettingsPage 本身已修，
  但透過 hook 呼叫的部分未修」這個陷阱）→ `useMaintenanceData.ts`（sub-task 2）→
  `useRealtimeData.ts` + `useI18n.ts`（sub-task 3，純讀取可合併）。
- `WMOM-20260507-02` 清單仍餘 c~f（限載/安排檢查/維護中心新工單/風場總覽新報告）；
  PR C（檢視情境掛載 app，需先寫 broker 子設計）——皆可在 `WMOM-20260925-01` 之後續接。
- ⚠ 附帶再次提醒（已連續多個 session 提醒）：`docs/routines/autonomous-daily-worker-
  prompt.md` canonical 文件內文仍停在舊版本，落後於實際 cron trigger 送入的 prompt，
  建議劉老師找時間同步。

## 5. 時間分配（概估）

| 項目 | 比例 |
|------|------|
| Preflight + baseline 自我測試 | 20% |
| Implement（1 行修改 + 2 測試） | 15% |
| 主動擴大稽核（發現 hooks/ 缺口 + 追查後端 router 角色設定） | 35% |
| Verify + mutation-verify | 10% |
| 追蹤檔案更新（ISSUES/STATUS/TODO/enforcement plan） | 15% |
| Code review | 5% |

## 6. 學到的事

- 這是本 repo 第 9 次重複同款「裸 fetch → authFetch + 2 測 + mutation-verified」修法，
  單一 fetch 呼叫、單一元件，15 分鐘估時準確。
- **稽核範圍界定教訓（延續 `WMOM-20260924-08` 自己揭露的教訓）**：`WMOM-20260923-10`
  當初的稽核指令不只是「沒遞迴 `components/` 子目錄」，而是**完全沒有掃描
  `frontend/hooks/`**——但好幾個大型頁面元件（`MaintenanceHub`/`SettingsPage`）的實際
  網路呼叫邏輯是委派給自訂 hook（`useMaintenanceData`/`useSettings`），元件本身只是
  render + 呼叫 hook 提供的 handler。只看元件檔案容易誤判「這個元件已經全部 authFetch
  化」，因為元件檔案裡確實一個裸 `fetch` 都沒有——問題藏在它 import 的 hook 裡。
  **未來任何「稽核某個資料夾底下的 X」工作，應該先問一次「這個資料夾的檔案是否會委派
  邏輯給外部 hook / helper」，而不能只信任「這個目錄掃完了」的宣稱。**
- 本次也是第一次在 review 階段主動擴大搜尋範圍而非被動等 code-reviewer 抓到——因為
  `WMOM-20260924-08` issue 本身的描述已經提到「`WMOM-20260923-10` 原稽核未遞迴」的
  根因，讀完這段描述後自然會想「那還有沒有別的目錄也被漏掉」，順手多跑一次遞迴 grep
  就在 `hooks/` 找到更大的缺口。**下次遇到「A 稽核漏掉 B」這種 issue，值得花 5 分鐘
  多問一次「還有沒有 C 也被漏掉」，成本很低但價值很高。**

## 7. Open questions（park）

- 無（技術面）。canonical routine 文件版本落差已連續多次提醒，非本次範圍。

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline：backend `1103 passed, 7 skipped, 1 xfailed`；frontend `npx tsc --noEmit`
  0 error、`npx vitest run` 1254 passed（58 files）、`npx vite build` OK。
- 修改後：backend 未動、不重跑（本次零 Python 變更）；frontend `npx tsc --noEmit` 0
  error、`npx vitest run` `1254→1256`（單檔 `MyOrdersMode.test.tsx` 7→9 測全數 pass；
  全套 58 files 不變，+2 新測）、`npx vite build` OK。
- **Mutation-verified**：修改前備份 `MyOrdersMode.tsx` 至 scratchpad（非 repo 內、非
  `git checkout` 可還原路徑），將 `authFetch(` 改回 `fetch(`，重跑
  `MyOrdersMode.test.tsx` → 「已登入」新測試如預期 fail（`expected undefined to be
  'Bearer test-token-myorders'`，因為裸 `fetch` 未帶任何 header），「未登入」對照組
  維持 pass（符合預期：該測試只驗證「無 token 時不帶 header」，兩種實作皆滿足）。用
  備份還原（非 `git checkout`），還原後重跑單檔 9 測全數 pass，`git diff` 僅剩預期
  修改（1 行 fetch→authFetch + 1 行 import，測試檔 +43 行）。

## Review

code-reviewer subagent review：**Approve，0 must-fix，1 should-fix、2 nice-to-have**。

- **Should-fix（已修）**：review 當下 ISSUES.md/STATUS.yaml/work-log 尚未更新——reviewer
  抓到的時序問題是「先跑 review 再收尾」，本次已在收到 review 結果後補齊全部追蹤檔案
  （即本 work-log 与下方 Wrap-up 所列）。
- **Nice-to-have（未採納）**：新 describe block 的 `beforeEach`/`afterEach` 與檔案頂層既有
  的重複（皆會執行但不衝突，reviewer 自己驗證過 hook 疊加順序無害）。維持現狀，不因為
  重複而增加修改風險。
- **Nice-to-have（獨立確認 + 已處理）**：reviewer 也獨立用 repo 全樹 recursive grep 找到
  `hooks/useRealtimeData.ts`/`useMaintenanceData.ts`/`useSettings.ts`/`useI18n.ts`
  （以及 `App.tsx:166`）內的裸 fetch，與本 session 主動稽核發現的範圍一致——**獨立驗證
  確認 `WMOM-20260925-01` 的認定正確**，未重複開 issue。`App.tsx:166` 這一處先前未列入
  `WMOM-20260925-01` 描述，已回頭在該 issue 補一句提醒下個 session 一併確認。
- reviewer 也獨立重跑 mutation test（revert authFetch→fetch）得到與本 session 一致的
  fail 訊息，並確認 `tsc --noEmit` 0 error、`components/field/` 全樹遞迴 grep 無殘留裸
  fetch、後端 `/api/farms` 端點合約（`require_authenticated()`）與宣稱一致。

## Wrap-up

- ISSUES.md / STATUS.yaml / TODO.md / `docs/product/WMOM-20260716-05_auth_enforcement_
  plan.md` 已同步更新（見上方「產出清單」）。
- 本次沒有引入未受自動化測試保護的邏輯；新增的 2 個測試沿用既有
  `global.fetch` mock 手法（與 `CostPage.test.tsx` 的 `authHeaderOf()` 同款），未引入
  新的脆弱寫法。
- ⚠ 誠實揭露：本次發現的 `WMOM-20260925-01`（hooks 層缺口）**尚未修復**，只完成調查 +
  開 issue + 更正 cutover 檢查表勾選；`useSettings.ts`/`useMaintenanceData.ts` 內的
  SUPERVISOR 寫入呼叫目前仍缺 auth header，`WMOM_AUTH_ENFORCE=true` 尚未在任何環境開啟
  故暫無實際影響，但在該 issue 修復前**不應該**翻這個環境變數。
