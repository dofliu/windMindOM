# 2026-05-15 WMOM-20260510-01 Part B — Mock login frontend

> **Issue**：WMOM-20260510-01 Part B — frontend mock login + user switcher
> **Branch**：`claude/issue-WMOM-20260510-01B-2026-05-15`
> **Goal**：M5 demo polish 第二步 — 讓 demo 操作者可以一鍵切換 4 個 fixture user，
> 把 actor_id 從 hardcoded `DEV_ACTOR_ID` 改成可動態切換的「目前登入者」。

---

## 1. 為什麼今天做這個

依 2026-05-14 handoff doc 建議：「下次 session 直接接 Part B 就好（frontend mock login widget），這時 backend 已 ready 不再擋」。

5/14 Part A 已上線 backend separation-of-duties guard + `WMOM_DEV_MODE` bypass。但 frontend 仍寫死 `DEV_ACTOR_ID = '00000000-...0001'` — 一個 placeholder UUID 跑全 chain，無法演 demo。

Part B 是 4-part WMOM-20260510-01 的第二階段（1d 估時，純 frontend infra）。

---

## 2. Scope 與設計決策

### 2.1 為什麼用 frontend constant（不做 backend user table）

issue 描述提到「簡易 user table（無密碼）：name / email / role(s) / is_active」。但：

- 估時 1d，加 backend SQLAlchemy model + migration + router + tests 至少 1.5d
- spec 明確「**不做**：登入畫面 / 密碼驗證 / JWT」— 表示 minimal infra
- 4 個 fixture user 的 UUID 即使 hardcoded 在 frontend 也不會與既有資料衝突（既有 actor_id 全是 placeholder UUID 寫進 ledger）
- 後端 signoff repository 的 `decided_by` 欄位只是個 UUID string，無 FK，不需要 user table 對映

決議：純 frontend constant + React Context 管 current user state；localStorage 持久化跨 session。

如果未來真要 user table（M6+ 真 PoC 上線時），再做 WMOM-20260510-02（real auth），fixture user 改成 seed data。

### 2.2 為什麼不擋 Owner user

Notes 寫「Mock login 的 4 fixture user 是 demo 用，production 模式應該被禁用」— 意思是 `WMOM_DEV_MODE` 在 production 應 off，不是說 Owner 在 frontend 要被擋。

實作上：
- Owner user 永遠出現在 switcher，加 `(dev only)` 灰字 tag 提示
- 若 production 模式（dev_mode 關）時 user 選 Owner 跑 signoff chain，後端 separation guard 會擋 — 行為正確，無 silent fail
- 不加 backend `/api/system/dev-mode` endpoint（避免 Part B scope 蔓延）

### 2.3 React Context vs localStorage event

兩個方案：
- **Context**：reactive，所有 mounted component 訂閱即可
- **localStorage event**：跨 tab 同步，但同 tab 內無事件

選了 Context（同 tab 內使用情境），localStorage 只做 persistence。`getCurrentActorId()` 同步函式 fallback localStorage 給非 React 模組（例如 service 層）用。

### 2.4 為什麼 `getCurrentActorId()` 而不直接用 hook

WorkflowPage 的 callback 形如 `wo.dispatch(id, { actor_id: DEV_ACTOR_ID, assignee_id })` — 是 inline function 不一定走 hook。改成 `getCurrentActorId()` 同步讀 localStorage，行為等價於 `currentUser.id`，但不需要為了 1 個 actor_id 把整個 callback chain 改成 hook closure。

權衡：localStorage 同步讀有 ~0.1ms cost，但 dispatch action 本身就是 user click，無感。

---

## 3. 檔案異動（規劃）

### 3.1 新增

```
+ frontend/services/mockUsers.ts              4 個 fixture user constants + types
+ frontend/hooks/useCurrentUser.tsx           UserProvider + useCurrentUser hook
+ frontend/components/UserSwitcher.tsx        Sidebar 底部 dropdown widget
```

### 3.2 修改

```
M frontend/services/workOrderService.ts       加 getCurrentActorId() helper（DEV_ACTOR_ID 仍保留 backward-compat）
M frontend/components/workflow/WorkflowPage.tsx       4 處 DEV_ACTOR_ID → getCurrentActorId()
M frontend/components/workflow/WorkOrderDetailModal.tsx  3 處 DEV_ACTOR_ID 顯示 → currentUser.name
M frontend/App.tsx                            包 UserProvider + sidebar footerExtra 加 UserSwitcher
M ISSUES.md                                   Part B status → in_progress（合併後改 done）
M STATUS.yaml                                 progress / next_milestone / last_updated
```

---

## 4. TODO（implementation checklist）

- [x] Read existing code（WorkflowPage / WorkOrderDetailModal / Sidebar / FarmSelector / App.tsx）
- [x] 寫 `frontend/services/mockUsers.ts`
- [x] 寫 `frontend/hooks/useCurrentUser.tsx`
- [x] 寫 `frontend/components/UserSwitcher.tsx`
- [x] 加 `getCurrentActorId()` 進 `workOrderService.ts`
- [x] 替換 `WorkflowPage` 的 4 處 + 顯示 currentUser.name（最終統一改用 `currentUser.id` 而非 helper，避免雙軌讀法）
- [x] 替換 `WorkOrderDetailModal` 的 3 處 + 顯示 currentUser.name
- [x] App.tsx 包 UserProvider + sidebar footerExtra 多塞 UserSwitcher
- [x] `cd frontend && npx tsc --noEmit` zero error
- [x] `cd frontend && npx vite build` zero error（737 modules / 860 KB bundle）
- [x] backend pytest zero new regression（3 條 numpy 精度漂移 + 1-2 條 dispatch concurrent flake 均 pre-existing）
- [x] code-reviewer subagent 跑：2 must-fix + 4 should-fix 全採納（border 順序、checklist、雙軌讀法、@deprecated、Escape key、ARIA listbox option role）
- [x] 更新 STATUS.yaml + ISSUES.md
- [ ] commit + push + PR

## 5. Code review 採納

Code-reviewer subagent 找出 **2 must-fix + 4 should-fix + 2 nice-to-have**。

**Must-fix 全採納（2/2）**：
1. ✅ `UserSwitcher` option `<button>` 的 `borderLeft` 被後一行 `border: 'none'` shorthand 重置，active 高亮線消失 → 把 `border: 'none'` 移到 `borderLeft` 前 + 加 boxSizing 註記
2. ✅ work-log checklist 全 `[ ]` 未勾 → 完成項目改 `[x]`，未跑項目（commit/push/PR）保留 `[ ]`

**Should-fix 全採納（4/4）**：
3. ✅ WorkflowPage 雙軌讀法（display 用 hook、action 用 `getCurrentActorId()` 直讀 localStorage） → 統一改 `currentUser.id`，`getCurrentActorId()` 只剩非 React 模組用
4. ✅ `DEV_ACTOR_ID` 缺 `@deprecated` JSDoc tag → 加上，IDE 可顯示刪除線
5. ✅ `UserSwitcher` 缺 Escape 鍵關閉 dropdown → useEffect 加 `keydown` listener
6. ✅ `<button role="option">` 違反 WAI-ARIA listbox children must be option role → 改 `<div role="option" tabIndex={0} onKeyDown(Enter/Space)>`

**Nice-to-have 暫不採納（0/2）**：
- ⏭ Nice-to-have 7（useEffect 補寫 localStorage 加 comment 解釋）：行為正確，留作未來 polish
- ⏭ Nice-to-have 8（`availableUsers` 不必要 useMemo dep）：影響極小，邏輯正確

