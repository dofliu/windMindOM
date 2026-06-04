# 2026-06-04 — FieldPage component render 測試 + 前端 render 測試基礎建設

> autonomous worker session（每 3 小時 cron）。EPIC-M5 M5-5 測試覆蓋。
> issue：**WMOM-20260604-01**（前端 component render 測試基礎建設 + FieldPage render 測試第一批）

---

## 1. 為什麼做這個

開工 preflight（決策樹）：

- 優先級 #1 known blocker / #2 baseline regression / #3 飛輪壞掉 → **皆無**。
  - backend `pytest` → **638 passed / 1 xfailed**（綠）
  - frontend `vitest` → **78 passed**（綠；routine prompt 寫的 59 已過時，main 現況 78）
  - 飛輪健康：上個 session 的 handoff PR #71 已 auto-merge 進 main；M5-5 Part A/B-1（commit 5532a32 / 0c09c9a）也在 main。
- stack-aware：22 個 stale PR 仍堆積（待劉老師 triage），但無 CI run 不會被誤合；本次工作與它們**零 collision**。

→ 落到優先級 #4「乾淨 autonomous 工作」。候選評估：
- **M5-5 Part B-2**（my work orders + completion）：需串 work_order router、涉及 persona/auth「who is me」**設計歧義** → 前次 worklog 已標「較重」，依 routine 不自行開工。
- **M5-2 ChromaDB**：給 CI 加 `chromadb` 重依賴，需評估安裝時間/runner 相容，風險較高。
- ✅ **前端 component render 測試覆蓋**：routine 優先級 #4 **明確背書**（「component render 測試需先補 vitest.config jsdom setupFiles + `npm i -D @testing-library/jest-dom`」）。FieldPage 是剛落地、最複雜（20KB、ModeToggle + 兩模式表單 + 結果區）、**零 render 覆蓋**的元件，最高 ROI。無設計歧義、單 session 可完工。

> 註：main 現有 8 個測試檔**全是** hook / util 單元測試，**零** component render 測試。本工作為純 net-new，與 stale PR #63/#64（早期 component 測試嘗試，未合且功能不在 main）不 collision。

## 2. 本次完成（Implement）

純測試 + 測試基礎設施，**不動任何 production 程式**：

| 檔案 | 內容 |
|---|---|
| `frontend/package.json`（改） | +devDep `@testing-library/jest-dom@^6`（`@testing-library/react`/`dom` 早已在）。 |
| `frontend/vitest.setup.ts`（新） | `import '@testing-library/jest-dom/vitest'` 啟用 DOM matcher（`toBeInTheDocument`/`toBeDisabled`/`toHaveAttribute`…）。 |
| `frontend/vitest.config.ts`（改） | `test.setupFiles: ['./vitest.setup.ts']`（取代原 TODO 註解）。setup 只 import matcher、對純 hook/util 測試無副作用。 |
| `frontend/components/field/__tests__/FieldPage.test.tsx`（新） | FieldPage 第一批 render 測試 **19 tests**：把整個 `useKnowledge` hook 換成可控 mock（`vi.mock` + `makeHook` 工廠回傳三條流 info/search/alert + 4 個 action spy），元件用 `ThemeProvider` 包裹（`useTheme` 無 Provider 會 throw）。 |

### 19 tests 覆蓋的 UX 契約
- 預設渲染（標題 / 模式切換兩鈕 / 關鍵字表單在場、alert 專屬欄位不在）
- 模式按鈕 `aria-pressed`（query active / alert inactive）
- info badge 三態：baseline（amber）/ vector（顯示 retriever 名）/ error（「RAG 服務異常」）
- 模式切換：關鍵字查詢 ⇄ 警報檢索 切換對應表單
- query 有結果 → chunk 卡（相關度 % / 正文 / 命中原因 / 來源行 `檔 · §章 · p.頁`）
- query 空結果 → 查無提示
- query error → 剝技術前綴只留繁中 detail（`stripErrorPrefix` 行為）
- query loading → 「檢索中…」
- alert 有結果 → 警報摘要 pill（告警碼/等級/機組）+「系統據此檢索」query 透明標示 + chunk
- 查詢按鈕 disabled：無輸入 disabled、輸入後 enabled
- 查詢點擊 → `runSearch` 帶 **trim 後**文字 + 告警碼 payload
- 常用告警碼 chip 一鍵帶入 → 按鈕 enabled
- alert `runAlert`：需告警碼 + 機組才 enabled、payload 帶 `DEFAULT_ALARM_LEVEL='A'` + `timestamp` 永遠帶 `Z`（UTC，防 422）
- 清除按鈕 → `clearSearch`
- 多段結果 → 渲染對應數量卡片 + 高/低相關度 pill 兩端

### 踩到 + 修掉的三個雷
1. **`globals: false` 下 RTL 不自動 cleanup** → render 跨測試累積，`getByRole`/`getByText` 命中多個而失敗。補 `afterEach(cleanup)`（手動清 DOM）。
2. **錯誤訊息文字被拆成兩個 text node**（「查詢失敗：」+ detail 同 div）→ `getByText('後端忙碌')` 精確匹配失敗，改 regex `/後端忙碌/`。
3. alert 結果區「告警碼 21」會出現兩處（警報摘要 pill + chunk 的 alarm_codes pill）→ 改 `getAllByText(...).length >= 1`。

## 3. Verify（本機全綠才開 PR）

- `npx tsc --noEmit` → **0 error**（jest-dom 型別增強經 tsconfig 全量編譯生效，無 `any`）。
- `npx vitest run` → **97 passed**（78 baseline + 19 新；**零 regression**）。
- `npx vite build` → ✓ built（僅既有 chunk-size 提示，無新警告）。
- backend 未動 → **638 passed / 1 xfailed** 不受影響（開工已驗）。

## 4. Code review

用 `code-reviewer` subagent 對 staged diff 跑審查（聚焦測試正確性 / 假綠 / cleanup / 設定副作用）：
**2 must-fix / 4 should-fix / 3 nice-to-have**。設定層（jest-dom 入口 / globals+cleanup 一致性 / tsc 型別增強）確認無問題。

**採納**：
1. **[must]** `makeHook` 漏 `loadInfo`（`useKnowledge` 實際回傳 8 欄）、且用 `as KnowledgeReturn` 強轉遮蓋型別缺口 → 典型假綠前兆。補 `loadInfo: vi.fn()` + **移除 `as` 強轉**（讓 tsc 守住與 hook signature 對齊；漏欄位即編譯失敗）。移除後 `tsc` 仍 0 error，確認 mock shape 完全對齊。
2. **[must]** `getByRole('button', { name: '清除' })` 依賴 query/alert 兩模式互斥渲染才不歧義 → 加 comment 標明此假設（日後改 tab 保留 DOM 需改 `within()` 限縮）。
3. **[should]** 警報結果測試補 negative 斷言：切換前 query 模式下 `WTG-07` **不**可見（守住模式互斥契約，防 mode guard 失效假綠）。
4. **[should]** `beforeEach` 的 `mockReset` 加 comment 說明選擇原因（清 history + 移除 returnValue，每 test 由 renderField 重設）。
5. **[nice]** 新增 `info.loading` 中 badge 為 null 的測試（守住「loading 不顯示 badge」設計）。
6. **[nice]** 新增「無告警碼 → `runSearch` 帶空陣列 `[]` 而非 undefined」測試（守住 `RetrievalQuery.alarm_codes: number[]` 契約）。

**未採納（記錄理由）**：should-fix「`getByLabelText` 改 `getByRole('textbox')`」「error 測試拆 UI 結構契約」屬意圖清晰度建議，現有斷言正確且通過，不影響正確性 → 保留現狀避免過度改動。

**Verify（採納後）**：`tsc` 0 error + `vitest` **97 passed**（78 baseline + 19 新）+ `vite build` ✓。

## 5. 下次 session 接手建議

- **同模式擴大 component render 測試**：CostPage / FarmOverview / workflow 各頁（基礎設施已就位，照本檔 mock-hook + ThemeProvider 模式複製即可）。
- **M5-5 Part B-2**（my work orders + completion 串 work_order router）—— 仍需劉老師釐清 persona/auth「who is me」（🟡）。
- **M5-2 ChromaDB**（🔵；需評估 CI 加 `chromadb` 重依賴的安裝時間 / Linux runner 相容）。
- **22 個 stale PR triage**（待劉老師 / 後續 session；A 類 5 個明確 superseded）。

## 6. 給劉老師

- 純測試 + 測試基礎設施擴充，**零 production 程式改動**，無 schema / DB / 部署影響，CI 綠即 auto-merge。
- 自此前端有了 component render 測試的標準範式（mock hook + ThemeProvider 包裹 + jest-dom matcher），後續頁面補測試成本大降。
