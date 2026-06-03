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
| `frontend/services/__tests__/knowledgeService.test.ts`（新） | 6 tests：3 endpoint method/path/body 契約 + 成功 parse + 錯誤 detail 抽取（字串 / 陣列 / 無 body fallback `HTTP {status}`）。fetch mock，零連線。 |
| `frontend/hooks/__tests__/useKnowledge.test.ts`（新） | 6 tests：mount loadInfo / info 失敗 / search happy / **race（舊查詢後到不蓋新）** / search 失敗 / clearSearch 丟棄 in-flight。service mock。 |

## 4. Verify

- `npx tsc --noEmit` → **0 error**（無 `any`，型別嚴格對齊 backend）。
- `npx vitest run` → **71 passed**（59 baseline + 12 新；零 regression）。
- `npx vite build` → ✓ built（751 modules，無新警告，僅既有 chunk-size 提示）。
- backend 未動 → 638 / 1 xfailed 不受影響。

## 5. Code review

用 `code-reviewer` subagent 對 staged diff 跑審查。（見下方 review 區）

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
