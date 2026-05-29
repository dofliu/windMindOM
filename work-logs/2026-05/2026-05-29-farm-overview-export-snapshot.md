# 2026-05-29 — 風場總覽「匯出」按鈕接上 GET /api/export/snapshot（JSON 下載）

> Autonomous daily worker session（2026-05-29 20:00 Asia/Taipei，雲端 sandbox）。
> Issue：**WMOM-20260507-02 sub-task a**。Branch：`claude/upbeat-davinci-l1U9N`。

---

## 1. 為什麼做這個

Preflight baseline 完全綠（backend `pytest modules/{workflow,cost,reporting}/tests/`
→ **570 passed / 1 xfailed**；frontend `vitest` 39 passed）—— 決策樹第 1、2 條（blocker /
regression）皆不觸發。

5/10 handoff 推薦的候選清單**已全部完工**：A10 E2E（WMOM-20260509-10 done）、
WMOM-20260510-01（4 part done）、A6/A7 領料庫存 frontend（done）、F1–F5（done）；
只剩 F6（PostgreSQL row-lock，M6、需 docker postgres，本 sandbox 不具備）。

從其餘 open issues 挑「**最高 ROI、完全 autonomous、無設計歧義、單 session 可完工**」者：
**WMOM-20260507-02 sub-task a** —— 把 `FarmOverview` PageHeader 上原本無 handler 的
「匯出 / Export」placeholder 按鈕接到既有後端 API `GET /api/export/snapshot`。
近 4 個 session（5/26 vitest 基礎設施、5/27-01 requirements、5/27-02 dispatch flaky、
5/28 元件層測試）皆為 test/infra/cleanup；本日選一個**真正 user-facing 的功能接線**，
推進實際追蹤 issue 而非僅補測試覆蓋。

### 為什麼選 sub-task a（而非 b–f）

WMOM-20260507-02 共 6 個 sub-task（a–f），sub-task a 是唯一**零依賴、API 現成、有既有
pattern 可參考**者：
- API 已存在：`modules/monitoring/server/routers/export.py:54` `export_snapshot()` 回 `{count, data}`
- 既有 pattern：`EventComparisonView.tsx:94` `exportEvents()` 已示範前端匯出
- 其餘：b/c 需 control 指令、d 依賴 WMOM-22 inspection、e 開新工單 modal（2h）、
  f 依賴 reporting modal（2–3h）—— 皆較大或有依賴。

---

## 2. 完成內容

### `frontend/components/FarmOverview.tsx`

- 新增 `handleExportSnapshot` async handler：`fetch(GET /api/export/snapshot)` →
  `JSON.stringify(payload, null, 2)`（pretty-print 供工程師閱讀）→ Blob →
  anchor download `farm-snapshot-{YYYY-MM-DD}.json`。
- 新增 `exporting` state，匯出期間按鈕走 `Btn` 既有 `loading` prop。
- 按鈕接 `onClick={handleExportSnapshot}`；ariaLabel 由不貼切的「匯出報告」改為
  「匯出風場快照 / Export farm snapshot」（更貼合實際行為，符合 WCAG accessible name）。
- 視覺 label「匯出 / Export」**不動**（保持與設計稿對齊，符合 issue 約束）。

### 為何用 fetch+Blob 而非 window.open

`/api/export/snapshot` 回 `application/json`（非附 download header 的 StreamingResponse），
`window.open` 只會把 JSON 顯示在新分頁、不會真的下載成檔案。fetch + Blob + anchor.download
才能產出 issue 要求的「直接下載 JSON」檔案體驗。

---

## 3. Verify（zero regression）

| 項目 | 改前 | 改後 |
|---|---|---|
| `tsc --noEmit` | 0 errors | **0 errors** |
| `vite build` | 918.27 kB / 748 modules | **918.76 kB / 748 modules**（+0.49 kB handler，成功） |
| frontend `vitest` | 39 passed | **39 passed**（未動測試檔，純函式 + hook 不受影響） |
| backend `pytest modules/{workflow,cost,reporting}/tests/` | 570 passed / 1 xfailed | **未動**（純 frontend，無 backend 變更） |

**瀏覽器點擊驗收**：本 sandbox 無頭環境，無法實際點按下載 — 留給劉老師本機 dev
（`python run.py` + `npm run dev` → 風場總覽點「匯出」確認下載 `farm-snapshot-*.json`）。
與既有 frontend session（WMOM-20260504-13 / -06 / -07）同樣慣例。

---

## 4. Code review

跑 `code-reviewer` subagent 對 staged diff：**0 must / 2 should / 2 nice，Needs revision → 採納後 Approve**。

| # | 級別 | 內容 | 處置 |
|---|---|---|---|
| 1 | should | `revokeObjectURL` 緊接 `click()` 同步呼叫，Firefox/舊 Safari 下載非同步可能被取消 | **採納**：改 `setTimeout(() => revoke, 100)` + 註解（業界標準作法） |
| 2 | should | 失敗靜默吃錯，運維人員無感知；fetch 會真 throw（與 window.open 不同，類比失當） | **部分採納**：加 `console.error`（與 `useSettings.ts` 既有慣例一致、不再 truly silent）；**不加 `window.alert`**（全 repo 無 alert 用例、無 toast 系統 → 加會破壞一致性）。user-facing toast 回饋待共用 notification 系統（cross-cutting，另議） |
| 3 | nice | `res.json()` 再 `stringify` 為 double-pass，可改 `res.text()` | **不採納**：後端回 compact JSON，`res.text()` 會得單行不可讀；`null, 2` pretty-print 是**刻意**讓下載檔人可讀。數百 KB 開銷可忽略 |
| 4 | nice | handler 無自動化測試 | **延後**：handler 為 component 內 inline、未 export；vitest.config.ts 尚無 jsdom DOM matcher setupFiles；真 component render 測試已在 5/28 handoff §5 明列為「脆弱性較高、建議獨立 session」。記為 test debt（見下） |

採納後重跑：tsc 0 errors / vite build 成功，零邏輯影響。

---

## 5. 下次 session 接手建議

- **WMOM-20260507-02 續做 sub-task b–f**：
  - sub-task b「停機」/ c「限載」需對應 control API（`POST /api/control/command` / `/curtail`）
  - sub-task e「+ 新工單」開 modal（API `POST /api/maintenance/work-orders` 已存在，est 2h）
  - sub-task f「+ 新報告」依賴 M4 reporting modal（est 2–3h）
  - sub-task d「安排檢查」需等 WMOM-22 inspection_schedule
- **Test debt（本 session 留）**：`handleExportSnapshot` 三條路徑（成功 / HTTP error /
  網路例外）值得補測；建議走 5/28 handoff 指向的方向——先在 `vitest.config.ts` 補
  `setupFiles: ['@testing-library/jest-dom/vitest']` 開 component render 測試，或把 handler
  抽成 `useExportSnapshot` hook 放 `frontend/hooks/`（可直接測 hook、符合既有 hook 測試慣例）。
- 其他候選同前：WMOM-20260519-01（退料 guard，需劉老師會計語意）/ WMOM-20260513-02
  demo orchestrator（含 product decision）/ WMOM-20260509-F6（PostgreSQL，M6 需 docker）。

---

## 6. 檔案異動清單

```
改  frontend/components/FarmOverview.tsx   （+exporting state +handleExportSnapshot +按鈕 onClick/loading + ariaLabel 更名）
新  work-logs/2026-05/2026-05-29-farm-overview-export-snapshot.md（本檔）
改  ISSUES.md / STATUS.yaml
```
