# 2026-06-03 — `/field/` 警報檢索模式（EPIC-M5 M5-5 Part B，killer feature）

> autonomous worker session（每 3 小時 cron）。接續同日 M5-5 Part A handoff 的建議 #1：
> 推進 M5-5 Part B — `/field/` 串 `queryByAlert`（Part A 已備好 client 但 UI 尚未用）。

---

## 1. 開工盤點（Preflight）

- `git checkout main && git pull`：拿到 Part A（PR #72）成果，已 auto-merge 進 main → **飛輪健康**。
- backend baseline：`pytest modules/{workflow,cost,reporting,knowledge}/tests/` → **638 passed / 1 xfailed**（綠）。
- frontend baseline：`npx vitest run` → **73 passed**（59 + Part A 14）。
- **stack-aware 檢查**：`list_pull_requests` open=22，全為飛輪上線前的 stale PR（無 `[WIP]`、非本 session 系列）。
  本次為 net-new 前端（`/field/` 擴充），與所有 stale PR 無檔案 collision → 安全開工，不碰 triage（outward-facing，留劉老師）。

→ 決策樹：無 blocker / 無 regression / 飛輪健康 → 第 4 條「挑乾淨 autonomous 工作」→ **M5-5 Part B**。

## 2. 認領

**WMOM-20260603-04** — `/field/` 警報檢索模式（EPIC-M5 M5-5 Part B）。

M5-5 Part B 完整範圍是 alert detail with RAG + my work orders + completion。本次切最核心、
最 net-new、無 backend 依賴的 **alert detail with RAG**（killer feature slice）：警報事件 →
後端自動檢索手冊處置。my work orders / completion（需串 work_order router）留下個 session。

## 3. 本次完成（Implement）

純前端，**backend 完全沒動**（沿用 Part A 已串好的 `POST /api/knowledge/alert`）：

| 檔案 | 內容 |
|---|---|
| `frontend/hooks/useKnowledge.ts`（改） | 新增第三條流 `alert`：`runAlert(event)` 串 `knowledgeApi.queryByAlert` + `clearAlert`。race 防護用**獨立** `alertReqRef`（與 search 的 `reqRef` 分開），兩條流互不干擾；同單調遞增序號丟棄過期回應的精神。 |
| `frontend/components/field/FieldPage.tsx`（改） | 重構為模組化：`ModeToggle`（segmented：關鍵字查詢 / 警報檢索，active=primary/inactive=ghost + `aria-pressed`）+ `QueryMode`（Part A 邏輯抽出）+ `AlertMode`（新）+ 共用 `ResultList`/`ResultCard`。`AlertMode` 表單：告警碼（必填 ge=1）+ 告警等級 Select（A/T1/T2）+ 機組代號（必填）+ 異常標籤（逗號/全形逗號/空白分隔→去重）+ 常用告警碼 chips。送出 `timestamp: new Date().toISOString()`（永遠帶 Z，避免 naive datetime 被 schema validator 擋 422，CLAUDE.md §B）。結果區先顯示警報摘要（告警碼 pill + 等級 + 機組）+ **系統自動構造的 query**（透明標示「系統據此檢索：…」），再列 chunks。全走 ui 元件庫 + theme，**零 hex**。 |
| `frontend/hooks/__tests__/useKnowledge.test.ts`（改） | +5 tests：runAlert happy / race（舊檢索後到不蓋新）/ error / clearAlert in-flight 丟棄 / **search 與 alert 兩流獨立**（互不污染）。service mock，零連線。 |

## 4. Verify

- `npx tsc --noEmit` → **0 error**（無 `any`，型別嚴格對齊 backend schema）。
- `npx vitest run` → **78 passed**（73 baseline + 5 新；零 regression）。
- `npx vite build` → ✓ built（無新警告，僅既有 chunk-size 提示）。
- backend 未動 → 638 / 1 xfailed 不受影響。

## 5. Code review

用 `code-reviewer` subagent 對 staged diff 跑審查（聚焦 race 隔離 / schema 契約 / 領域邏輯）：
3 must-fix / 5 should-fix / 0 nice。Hook 本體 race 防護（兩流 reqRef/alertReqRef 獨立、
clearAlert 對稱）確認無缺陷、型別契約嚴格對齊。

**已採納（全部）**：
1. **[must]** `AlertMode.handleClear` 漏 reset `alarmLevel` → 清除後等級殘留舊值，下次送查帶 stale。補 `setAlarmLevel(DEFAULT_ALARM_LEVEL)`。
2. **[must]** 前端 `alarmLevel` 預設 `'T1'`（一級跳機）與 backend `AlertEvent.alarm_level` default `'A'`（警示）語意不對齊 → 改 `DEFAULT_ALARM_LEVEL='A'` 對齊 schema，避免使用者未選時擅自帶較嚴重等級。
3. **[must]** `hasQueried` 命名語意不準（實為「目前有結果嗎」）→ 全面改名 `hasResult`（QueryMode/AlertMode/ResultList 三處一致）。
4. **[should]** `ResultList` 的 `loading` prop 從未渲染進度回饋 → 加「檢索中…」muted 行（弱訊號現場避免反覆點擊）。
5. **[should]** `Select` onChange `v as AlarmLevel` 不安全強轉 → 加 `VALID_ALARM_LEVELS` narrow guard。
6. **[should]** race test 加 `expect(alertMock).toHaveBeenCalledTimes(2)` 防禦性斷言（pin 住 mock 順序前提）。
7. **[should]** `alertResult` fixture 補 backend 回傳的 default 欄位（oem/model/scenario_id/description/severity/timestamp）比照實際 response shape。

**Verify（採納後）**：`tsc` 0 error、`vitest` **78 passed**、`vite build` ✓。

## 6. 下次 session 接手建議

- **M5-5 Part B 續做**：my work orders list + completion flow（需串 `work_order` router；
  涉及 persona / auth，較 alert slice 重）；以及 alert detail 從真 monitoring 警報帶入（目前用表單模擬）。
- M5-2 ChromaDB（🔵；需評估 CI 加 chromadb 重依賴）。
- 22 個 stale PR triage 仍待劉老師 / 後續 session。

## 7. 給劉老師

- 純前端擴充，無 schema / DB / 部署影響，CI 綠即 auto-merge。
- 「警報檢索」目前是**表單模擬** SCADA 警報（demo 用）；真整合時由 monitoring 告警事件直接帶入 `AlertEvent`。
- 常用告警碼仍是 placeholder（待 M5-4 灌真 Z72 手冊後核實），與 Part A 同一份清單。
