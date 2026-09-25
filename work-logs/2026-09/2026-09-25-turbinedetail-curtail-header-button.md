# 2026-09-25 — `TurbineDetail.tsx` header『限載』鈕接線（WMOM-20260925-02）

> Session 類型：實作
> Session 長度：短
> 主導：autonomous worker（cron）
> 結果：進行中——見下方持續更新。

---

## 1. Session 目標

Preflight：`git checkout main && git pull`（fast-forward，含 `WMOM-20260925-01` 已在 main，
`git log -1` 確認 head 為 `55b68be`）；`mcp__github__list_pull_requests(state=open)` 回傳空
陣列，無殘留 open PR、無 stack 衝突。切回環境注入分支 `claude/inspiring-mccarthy-4idpg1`
（fast-forward 到 main 同點）。

Baseline 自我測試全綠（與既有基準一致）：
- backend：`pip install --ignore-installed PyYAML -r requirements.txt -r requirements-dev.txt`
  → `python -m pytest`（6 module + `tests/`）→ **1103 passed, 7 skipped, 1 xfailed**。
- frontend：`npm ci` → `npx tsc --noEmit` 0 error → `npx vitest run` **1267 passed**
  （60 files）→ `npx vite build` OK。

`TODO.md`「可立即接手」清單所列項目（PR C 需先寫 broker 子設計、情境比較 A2 已全數完成）
皆非單 session 可清楚定義範圍；M6 critical path 項目（`WMOM-20260720-04`/`-08` 系列、
`WMOM-20260716-06`）已全數完成；`WMOM-20260509-F6`（PostgreSQL）需劉老師架構決策，非
autonomous 可決。改查 `WMOM-20260507-02`（PageHeader placeholder 按鈕清單）尚餘 sub-task
c~f，其中 **c（風機細節『限載』）已有明確 API 對應（`POST /api/control/curtail`，後端
`modules/monitoring/server/routers/control.py` 已存在）+ 估時 1h + 無設計歧義**（同頁右欄
`OperatorControlCard` 已有完整限載輸入可參照複製語意，且 sub-task b『停機』header 鈕已建立
「重複入口直接呼叫同一支 command endpoint」的先例可依循）——選為本次工作，開新 issue
`WMOM-20260925-02` 追蹤。

## 2. 實際完成

### 2.1 主要工作

- **`frontend/components/TurbineDetail.tsx`**：新增 `CurtailModal`（比照 `FarmSelector.tsx`
  的 `CreateFarmModal` 遮罩 + `role="dialog"` + `Card` 樣式慣例）：單一 kW 數字輸入框
  （留空 = 解除限載，語意與 `OperatorControlCard.setCurtail` 一致：
  `trimmed === '' ? null : parseFloat(trimmed)`）+ 前端擋負值/非數字 + 取消 / 確認按鈕，
  送出打 `authFetch POST /api/control/curtail`（`SUPERVISOR`-only，非 2xx 顯示後端 `detail`
  或 fallback 訊息、不關窗）。PageHeader「限載」鈕 `onClick` 開啟 modal，成功送出後關閉
  （`OperatorControlCard` 自身 3s 輪詢會反映最新狀態，不在此另外維護狀態顯示，比照
  sub-task b『停機』header 鈕先例）。
- **aria-label 去重**：modal 內確認按鈕特意命名 `確認限載`/`確認`（而非沿用
  `OperatorControlCard` 既有的「設定限載」/「設定」），避免 modal 開啟時（`OperatorControlCard`
  仍掛載於背景）`getByRole('button', { name: ... })` 對到兩個同名按鈕。
- **`frontend/components/__tests__/TurbineDetail.test.tsx`**：新增 8 測（開啟 dialog、取消/✕
  關閉不打 API、輸入 kW 送出打對 endpoint+body、留空送出 `powerLimitKw: null`、前端擋負值顯示
  錯誤、後端非 2xx 顯示 `detail` 且 dialog 不關、已登入帶 `Authorization` header）。另修
  `stubFetch()` 共用 helper：原本回傳的 mock response 缺 `ok` 欄位，會讓新寫的
  `if (!res.ok)` 分支誤判任何成功回應為失敗——加 `ok: true` 後其餘既有 75 測不受影響
  （既有 production 路徑 `sendCmd`/`setCurtail`/`refresh` 本來就不檢查 `res.ok`）。

### 2.2 卡住或延後的事

無（本次認領範圍完整完工）。

### 2.3 重大決策（如有）

無新增架構決策。

## 3. 產出清單

- `frontend/components/TurbineDetail.tsx`：+175 行（`CurtailModal` component + state +
  header 按鈕接線）
- `frontend/components/__tests__/TurbineDetail.test.tsx`：+134 行（8 新測 +
  `stubFetch()` helper 補 `ok: true`）
- `ISSUES.md`：新增 `WMOM-20260925-02` + 回頭在 `WMOM-20260507-02` sub-task c 標記
  in_progress；統計表 in_progress 0→1
- 本 work-log

## 4. 給下個 session 的話

- `WMOM-20260507-02` 尚餘 sub-task d~f（`d` 依賴 `WMOM-20260505-22` `inspection_schedule`
  尚未做；`e` 維護中心 `+ 新工單`／`f` 風場總覽 `+ 新報告` 皆無阻塞，可繼續認領）。
- ⚠ 附帶再次提醒（已連續多個 session 提醒）：`docs/routines/autonomous-daily-worker-
  prompt.md` canonical 文件內文仍停在舊版本（v3，baseline 638/59），落後於實際 cron
  trigger 送入的 prompt（v4.1，baseline 1103/1267→1275），建議劉老師找時間同步。

## 5. Open questions（park）

- ⚠ 附帶再次提醒（已連續多個 session 提醒）：`docs/routines/autonomous-daily-worker-
  prompt.md` canonical 文件內文仍停在舊版本（v3，baseline 638/59），落後於實際 cron
  trigger 送入的 prompt（v4.1，baseline 1103/1267），建議劉老師找時間同步。

---

## Implement

見上方 §2.1。

## Verify

- 開工 baseline：backend `1103 passed, 7 skipped, 1 xfailed`；frontend `npx tsc --noEmit`
  0 error、`npx vitest run` 1267 passed（60 files）、`npx vite build` OK。
- 修改後：backend 未動，不重跑（本次零 Python 變更，已於開工時跑過一次確認）；frontend
  `npx tsc --noEmit` 0 error、`npx vitest run` 1267→1275 passed（60 files 不變，+8 新測，
  零 regression）、`npx vite build` OK。
- **Mutation-verified**：修改前用 scratchpad 備份 `TurbineDetail.tsx`（非 repo 內、非
  `git checkout` 可還原路徑），將 header「限載」鈕的 `onClick={() => setCurtailModalOpen(true)}`
  移除（模擬回到 placeholder），重跑 `TurbineDetail.test.tsx` → 新增的 8 個測試如預期全部
  fail（`getByRole('dialog')` 找不到元素），其餘既有 75 測維持 pass。用備份還原（非
  `git checkout`），還原後重跑單檔 83 測全數 pass。
- **`stubFetch()` helper 改動的獨立驗證**：加 `ok: true` 後重跑整份 `TurbineDetail.test.tsx`
  （83 測全 pass）與全套 vitest（1275 passed，60 files 不變）確認未影響既有測試的假設。

## Review

（待補——code-reviewer subagent review 進行中，結果回填後補齊本節 + 視 must-fix 補一輪
verify）

## Wrap-up

（待 review 完成後補齊：ISSUES.md/STATUS.yaml/TODO.md 最終同步 + 誠實揭露段落）
