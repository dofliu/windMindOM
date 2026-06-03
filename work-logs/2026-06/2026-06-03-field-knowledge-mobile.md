# 2026-06-03 — `/field/` 現場工程師 mobile-first 知識查詢頁（EPIC-M5 M5-5 Part A）

> autonomous worker session（每 3 小時 cron）。接續 6/03 flywheel-activation handoff 的
> 建議 #3：回到 EPIC-M5 推進，挑 **M5-5 `/field/` mobile 前端串 knowledge router**
> （🔵 PMF 關鍵、net-new、與所有 stale PR 無 collision）。

---

## 1. 開工盤點（Preflight）

- `git checkout main && git pull`：拿到上個 session 的 flywheel-activation 成果（PR 已被 auto-merge 進 main，work-log 在 main 上 → **飛輪健康**）。
- backend baseline：`pytest modules/{workflow,cost,reporting,knowledge}/tests/` → **638 passed / 1 xfailed**（綠）。
- frontend baseline：`npx vitest run` → **59 passed**（綠）。
- **stack-aware 檢查**：`list_pull_requests` 仍有 22 個飛輪上線前的 stale PR（沿用上個 handoff §3 的 triage 清單）。本次工作是 **net-new 前端**（`/field/`），與所有 stale PR 無檔案 collision → 安全開工，不碰 triage（屬 outward-facing 判斷，留劉老師）。

→ 決策樹：無 blocker / 無 regression / 飛輪健康 → 命中第 4 條「挑乾淨 autonomous 工作」→ **M5-5**。

## 2. 認領

**WMOM-20260603-03** — `/field/` 現場 mobile 知識查詢頁（EPIC-M5 M5-5 Part A）。

M5-5 完整範圍是 alerts list / alert detail with RAG / my work orders / completion，範圍大。
本次切 **Part A：知識檢索查詢**（最核心 PMF slice，可獨立完整出貨），work order list /
completion 留 Part B 下個 session。

## 3. 本次完成（Implement）

新增 / 修改（純前端，**backend 完全沒動**）：

| 檔案 | 內容 |
|---|---|
| `frontend/services/knowledgeService.ts`（新） | knowledge API client：3 endpoint wrapper（`info` / `query` / `queryByAlert`）+ 型別嚴格對齊 `modules/knowledge/schemas.py`（KnowledgeChunk / RetrievedChunk / RetrievalQuery / AlertEvent / AlertRagResult / *Response）。錯誤處理沿用 reportingService 的 `readError`（抽 FastAPI `detail`）。 |
| `frontend/hooks/useKnowledge.ts`（新） | state hook：`info`（mount 載入一次 baseline badge）+ `search`（手動檢索）兩條獨立流；race 防護用單調遞增 `reqRef` 丟棄過期回應（連續快速送查的 stale-overwrites-fresh）。 |
| `frontend/components/field/FieldPage.tsx`（新） | mobile-first UI（maxWidth 560、單欄、大觸控目標）：關鍵字 + 告警碼 input、常用 Z72 告警碼一鍵 chips、結果卡（相關度 % + 繁中命中原因 + 文件來源 + 段落 + alarm code pills）、loading / error / 空結果狀態。全走 ui 元件庫 + theme palette，**零 hex**。 |
| `frontend/App.tsx`（改） | 新增 `field` ViewId + SECONDARY_NAV「現場查詢 / Field」+ render case。 |
| `frontend/components/ui/Logo.tsx`（改） | 新增 `field` NavIconId + 手機 + 放大鏡 SVG icon。 |
| `frontend/services/__tests__/knowledgeService.test.ts`（新） | 8 tests：3 endpoint method/path/body 契約 + 成功 parse + 錯誤 detail 抽取（字串 / Pydantic 422 陣列抽 msg / 多筆串接 / 無 body fallback `HTTP {status}`）+ queryByAlert 503 error path。fetch mock，零連線。 |
| `frontend/hooks/__tests__/useKnowledge.test.ts`（新） | 6 tests：mount loadInfo / info 失敗 / search happy / **race（舊查詢後到不蓋新）** / search 失敗 / clearSearch 丟棄 in-flight。service mock。 |

## 4. Verify

- `npx tsc --noEmit` → **0 error**（無 `any`，型別嚴格對齊 backend）。
- `npx vitest run` → **73 passed**（59 baseline + 14 新；零 regression；含 review-fix +2 service 測試）。
- `npx vite build` → ✓ built（751 modules，無新警告，僅既有 chunk-size 提示）。
- backend 未動 → 638 / 1 xfailed 不受影響。

## 5. Code review

用 `code-reviewer` subagent 對 staged diff 跑審查（兩次：staged diff + commit 3c3c468）。
共識：**正確性無 must-fix**（schema 契約全欄位對齊、race 防護 reqRef 設計正確、
parsedAlarmCode 過濾邏輯正確均經確認），但有數個值得採納的 UX should-fix。

**已採納（commit follow-up）**：
1. `readError` 對 Pydantic v2 422 `detail` **陣列抽 `msg`**（多筆以「；」串接）—— 不再把
   `[{"type":"missing",...}]` 原始 JSON 丟給現場工程師；+2 測試（單筆抽 msg、多筆串接）。
2. FieldPage 顯示層**剝掉 `POST /api/... failed:` 技術前綴**，只留 backend 繁中 detail。
3. `/info` 失敗時顯示 **「RAG 服務異常」warn badge**（不讓狀態靜默消失，demo 場景關鍵）。
4. `fmtScore` **clamp 0..1**（防 M5-2 ChromaDB distance 轉換溢出邊界顯示 >100%）。
5. alarm code pills **`new Set` 去重**（backend schema 不保證唯一，防 React duplicate key）。
6. `COMMON_ALARM_CODES` 加 **placeholder 注釋 + Z72 手冊核實提醒**（M5-4 後以真資料取代，
   避免一鍵帶入查無結果的 false confidence）。
7. `AlertEvent.timestamp` 註解強化（Part B 串警報用 `toISOString()` 避免 422 時區陷阱）。
8. service 測試：500→**503** 命名對齊 backend 語意；補 `queryByAlert` 503 error-path 測試。
9. `total ?? results.length` 冗餘 fallback 簡化為 `results.length`（computed_field 保證一致）。

**未採納（記 backlog / Part B）**：
- FieldPage component-level render 測試（需 jsdom setupFiles + `@testing-library/jest-dom`，
  與 stale PR #63/#64 的測試基礎設施重疊，留待該基礎設施落地後一併補；本次靠 service + hook
  單元測試覆蓋邏輯）。
- `loadInfo` 暴露於 return：保留給 Part B pull-to-refresh / retry 用。

**Verify（採納後）**：`tsc` 0 error、`vitest` **73 passed**（59 baseline + 14 新）、`vite build` ✓。

## 6. 下次 session 接手建議

- **M5-5 Part B**：`/field/` 加 my work orders list + completion flow（串 work_order router）；
  以及 alert detail with RAG（串 `POST /api/knowledge/alert` 的 `queryByAlert`，client 已備好）。
- `knowledgeService.queryByAlert` 已寫好但 UI 尚未用 → Part B 接「警報跳出 → 自動帶入告警碼檢索」。
- （沿用上個 handoff）22 個 stale PR triage 仍待劉老師 / 後續 session 處理。
- M5-2 ChromaDB（🔵 需評估 CI 加 chromadb 重依賴）。

## 7. 給劉老師

- 純前端新增，無 schema / DB / 部署影響，CI 綠即 auto-merge。
- `/field/` 目前掛在 SECONDARY_NAV（側欄「現場查詢」）。未來若要做真正的 mobile 獨立路徑
  （手機掃 QR 直達 `/field/`），需引入 router —— 屬 Part B / 之後決策，本次先用既有 view-state 導覽。
