# 2026-05-29 — Frontend mock login 身份核心回歸測試：mockUsers 純函式 + fixture 契約

> Autonomous daily worker session（2026-05-29 20:00 Asia/Taipei，雲端 sandbox）。
> Issue：**WMOM-20260529-01**（新開）。Branch：`claude/kind-faraday-CWVM3`。

---

## 1. 為什麼做這個

Preflight baseline 完全綠（backend `pytest modules/{workflow,cost,reporting}/tests/`
→ **570 passed / 1 xfailed**；frontend vitest **39 passed**；無 blocker、無 regression）——
決策樹第 1、2 條皆不觸發。

5/10 handoff 已過時（當時候選 A6/A7/A10/WMOM-20260510-01 全 done、M4 100%）。掃 ISSUES.md
剩餘 open：多需劉老師決策（WMOM-20260519-01 退料 guard 會計語意、WMOM-20260513-02 demo
orchestrator product decision、WMOM-20260513-01 UI v2 等設計交接書）或 M6 環境（F6
PostgreSQL row-lock 需 docker postgres）或物理模型強化（高風險、需參考 digiwt notes）。

依 5/26→5/28 三次 session 建立的「**擴大 frontend 測試覆蓋**」momentum，挑唯一無設計歧義、
完全 autonomous、單 session 可完工的續作。5/28 handoff 點名下一步「真 component render 測試」
但需先補 `vitest.config.ts` jsdom setupFiles + mock data hook / service（脆弱性較高、建議獨立
session）。**本 session 改先收一個更高 ROI、零脆弱的純函式層**：mock login 身份核心
`mockUsers.ts`。

### 為何選 mockUsers.ts

- **demo-critical**：WMOM-20260510-01 Part B 的身份核心。`getCurrentActorId()` 是**非 React
  模組（service 層 callback）唯一的同步身份來源**，所有 dispatch / approve API call 的
  actor_id 都從這裡來。M6 客戶 demo 跑完整 lifecycle（employee→leader→treasury 三階簽核）
  全靠 4 個 fixture user 與此 fallback 邏輯。
- **目前零測試**：`findMockUser` / `getCurrentActorId` + fixture 契約完全沒有自動化守護。
- **零脆弱、零新依賴**：只依賴 localStorage（vitest.config.ts `environment: 'jsdom'` 已提供）；
  不需 React render、不需 `@testing-library/jest-dom`（未安裝）、不動 `vitest.config.ts`。

---

## 2. 完成內容

### `frontend/services/__tests__/mockUsers.test.ts`（新，20 tests）

新建 `services/__tests__/` 測試目錄（既有測試分散在 `hooks/__tests__`、
`components/*/__tests__`，service 層此前無測試）。

- **fixture 契約（8 tests）**：4 個 user / id 唯一 / id 為 UUID 8-4-4-4-12 格式 /
  全 is_active / email 唯一且 @wmom.dev / **roles 用 `Record<string, ReadonlyArray<MockUserRole>>`
  型別化期望表窮舉**（改 fixture role 漏改表→runtime 紅；改 `MockUserRole` 型別漏補→tsc 紅）/
  只有 Owner 標 dev_mode_only 且為唯一含 owner role 者 / 非 Owner 三人皆非 dev_mode_only。
- **DEFAULT_USER 與常數（2 tests）**：DEFAULT_USER === MOCK_USERS[0] === Alice 且 roles 僅
  `['employee']`（**最低權限為安全預設**）/ `ACTOR_ID_STORAGE_KEY === 'wmom_actor_id'`
  （跨模組 / 跨 session 持久化契約，改動會使既有使用者 localStorage 失聯）。
- **findMockUser（3 tests）**：null/undefined/空字串→null（falsy guard）/ 每個合法 id→正確
  user / 未知 id→null + **大小寫敏感**（大寫 hex 不匹配）。
- **getCurrentActorId localStorage 互動（5 tests，beforeEach+afterEach clear 隔離）**：
  無值→Alice / 合法 id→原樣 / **未知 id→fallback Alice（安全契約：拒絕不在 fixture 的身份
  進到後續 API call）** / 空字串→fallback / 回傳值恆為已知 fixture id（不洩漏任意外部輸入）。
- **型別層 sanity**：`const _typeGuard: MockUser = {...}` 編譯期鎖住 MockUser 介面形狀。

---

## 3. Verify（zero regression）

| 項目 | 改前 | 改後 |
|---|---|---|
| vitest | 39 passed（4 檔） | **59 passed（5 檔：+20 mockUsers）** |
| `tsc --noEmit` | 0 errors | **0 errors** |
| `vite build` | 918.27 kB | **918.27 kB**（測試檔未進 production bundle，大小持平） |
| backend `pytest modules/{workflow,cost,reporting}/tests/` | 570 passed / 1 xfailed | **未動**（純 frontend 新增） |

---

## 4. Code review

跑 `code-reviewer` subagent 對 staged diff（含讀 source + 既有 statusUtils.test.ts 對齊風格）：
**1 must / 5 should / 3 nice，Needs revision → 採納後可 approve**。reviewer 確認測試結構清晰、
fixture 契約覆蓋度高、localStorage 隔離正確、與 5/28 風格高度一致。處置（must + 全 should + 便宜 nice 全採納）：

| # | 級別 | 內容 | 處置 |
|---|---|---|---|
| 1 | **must** | `getCurrentActorId` 的 SSR guard（`typeof window === 'undefined'`，source:95）在 jsdom 下不可達、零測試零說明 | **採納**：加 `vi.stubGlobal('window', undefined)` test 真正打到該分支（+1 test），未來拿掉 guard 會被抓到 |
| 2 | should | Owner roles `toEqual` 順序敏感、過緊鎖陣列順序（roles 語義是集合非有序） | **採納**：改 `sort()` 後比對鎖成員不鎖順序 + 註解說明 roles 集合語義 |
| 3 | should | `getCurrentActorId` happy path 只驗 Bob（1/4），漏 dev_mode_only=true 的 Owner 特例 | **採納**：加 Owner id 回傳 test（+1）驗 getCurrentActorId 不過濾 dev_mode_only |
| 4 | should | `is_active` test 命名混淆 service 資料屬性與 UI render（file 自稱不測 hook） | **採納**：改名「switcher filter 的資料前提」+ 註解指明 UI filter 在 UserSwitcher.tsx |
| 5 | should | `expectedRoles` 註解誇大 compile-time 保護（key 是 string 無 union 保護，只 runtime 抓） | **採納**：改註解精確描述 value=compile-time / key=runtime 兩層 |
| 6 | should→nice | `UUID_SHAPE` regex 不驗 v4（reviewer 自評後降為 nice） | **採納**：rename `PLACEHOLDER_UUID_SHAPE` + test 名標「placeholder，非標準 v4」減混淆 |
| 7 | nice | `_typeGuard` 不偵測 string literal 型別收窄 | **採納**：加註解標明此限制 |
| 8 | nice | `beforeEach`+`afterEach` 雙重 clear 冗餘（與 useCostData 只用 beforeEach 不一致） | **採納**：移除 afterEach + 註解說明 beforeEach 已足夠隔離 |

採納後重跑：mockUsers 18→**20 tests**、全 vitest **59 passed**、tsc 0 errors、vite build 918.27 kB 持平，零邏輯影響。

---

## 5. 下次 session 接手建議

- 本 PR 後 frontend 測試 57 passed（hook 2 檔 + util 2 檔 + service 1 檔）。
- **純函式層測試續推**：service 層尚未測的純邏輯仍有空間（例如各 service 的 request
  builder / response 正規化），但多數 service 是薄 API client（fetch + JSON），純邏輯不多。
- **真 component render 測試**（CostPage / FarmOverview / workflow Panel）仍是 5/28 點名的
  下一階段，需先在 `vitest.config.ts` 補 `setupFiles: ['@testing-library/jest-dom/vitest']`
  （**注意 `@testing-library/jest-dom` 未在 devDependencies，需先 `npm i -D`**）+ mock data
  hook / service，脆弱性較高、建議獨立 session。CostPage 的 `fmtMoney`/`fmtPct`/`fmtKwh`
  （CostPage.tsx:45-52）未 export，若要測需先抽出。
- 其他候選：WMOM-20260519-01（需劉老師會計語意決策）/ WMOM-20260513-02 demo orchestrator
  （含 INSPECTION over-use product decision）/ WMOM-20260509-F6（PostgreSQL，M6、需 docker）。

---

## 6. 檔案異動清單

```
新  frontend/services/__tests__/mockUsers.test.ts   （20 tests：fixture 契約 + findMockUser + getCurrentActorId localStorage 互動 + SSR fallback）
改  work-logs/2026-05/2026-05-29-mockusers-identity-tests.md（本檔）
改  ISSUES.md / STATUS.yaml
```
