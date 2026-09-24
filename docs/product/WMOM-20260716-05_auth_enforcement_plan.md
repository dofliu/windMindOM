# WMOM-20260716-05 — 實作計畫：router 強制授權 + 前端真登入

> 狀態：**proposed（待劉老師拍板）** — 本檔只是計畫，**零程式碼變更**。
> 接 DEC-20260716-01 / #108（auth 基礎層）/ #110（DB user store）。
> 拍板後拆成子 issue 實作；每一步非破壞、CI 綠。

---

## 0. 為什麼要有計畫（而不是直接寫）

現況兩邊各走各的：

- **後端**：4 個 workflow router（approval / inventory / material_request / work_order，共 ~14 處）**信任 request body 的 `actor_id`**，不驗證、無授權。
- **前端**：`workOrderService` / `materialService` / `inventoryService` 把 `getCurrentActorId()`（localStorage mock login）塞進 body 送出。
- **已就位**（#108/#110）：`/api/auth/login` 發 JWT、`get_current_actor` / `require_roles` dependency、`SqlUserStore` + admin 建帳。

**天真做法會炸**：後端一旦「要 token」，前端還在送舊 `actor_id` → **全部登不進去**（flag day）。所以必須**前後端協調 + 可控切換**。本計畫用「雙模式 + 環境旗標 cutover」讓每一步都非破壞。

---

## 1. 核心策略：雙模式 → 平行改前端 → 旗標切換

引入環境旗標 **`WMOM_AUTH_ENFORCE`（預設 `false`）**：

| 階段 | `WMOM_AUTH_ENFORCE` | 後端行為 | 前端 | 可上線？ |
|---|---|---|---|---|
| 現況 | （未接） | 信任 body `actor_id` | 送 body `actor_id` | ✅ |
| **P1 後端雙模式** | `false` | 有 token→用 token；無 token→**沿用 body `actor_id`（舊行為）** | 不變 | ✅ 非破壞 |
| **P2 前端真登入** | `false` | 同上 | **登入拿 token + 每 request 帶 `Authorization`**；仍送 body actor_id | ✅ 非破壞 |
| **P3 切換** | `true` | 無 token→**401**；套 RBAC | 只靠 token（body actor_id 可留可清） | ✅ 一鍵 cutover |
| P4 清理 | `true` | — | 移除 body actor_id + UserSwitcher（dev 保留） | ✅ |

**關鍵**：P1、P2 各自都能單獨 merge 上線而不壞任何東西；真正「開始強制」只在 P3 把旗標翻成 `true` 那一刻，且可即時翻回 `false` 回滾。

---

## 2. 後端工作分解

### P1-a　`resolve_actor()` 雙模式解析（新，非破壞核心）
`modules/auth/dependencies.py` 加一個**函式**（非 dependency，因需讀 body 的 `actor_id`）：

```
resolve_actor(request, body_actor_id) -> Actor
  1. 有有效 Bearer token → Actor(id, role, name)（已驗證）
  2. 無/無效 token：
     - WMOM_AUTH_ENFORCE=true  → raise 401
     - 否則（legacy/dev）        → Actor(id=body_actor_id, role=UNKNOWN, name="")
```
+ `require_role(actor, *allowed)`：`WMOM_AUTH_ENFORCE=false` 時**放行**（role 尚未可信）；`true` 時檢查（ADMIN 全權）。

### P1-b　逐支 router 遷移（4 支，各自一個 PR，非破壞）
每支把 `req.actor_id` 換成 `actor = resolve_actor(request, req.actor_id)`，用 `actor.id`；並依權限矩陣掛 `require_role(...)`。順序（低風險→高風險）：
1. `work_order_router`（建單 / 派工 / 完工）
2. `material_request_router`
3. `inventory_router`（出入庫）
4. `approval_router`（簽核——與 signoff 既有 separation-of-duties 疊加，最需小心）

每支驗收：token 路徑、legacy 路徑（enforce=false）、enforce=true 下的 401/403。

### P1-c　其他 router 的授權（讀多寫少）
monitoring（turbines/faults/farms/control）、cost、reporting、knowledge：多為讀，enforce 後至少要「已登入」；寫入類（farm 建立、fault inject、control）掛較高角色。可在 P3 前補。

---

## 3. 前端工作分解（P2）

1. **登入頁 / 流程**：呼叫 `POST /api/auth/login` → 存 token → 導回。
2. **API client 統一帶 token**：所有 fetch 加 `Authorization: Bearer <token>`（有 token 才帶）。過渡期**仍送 body actor_id**（讓後端 legacy 模式續跑）。
3. **401 處理**：收到 401 → 清 token → 導回登入頁。
4. **`useCurrentUser` / `UserSwitcher`**：production 換成「顯示登入者（來自 token / `/api/auth/me`）」；**dev_mode 保留 switcher**（demo 單人跑 lifecycle）。
5. **`/field/` 現場**：現場工程師登入（見決策 D5）。

---

## 4. 草案 RBAC 權限矩陣（**待你確認/修改**）

角色（對映既有簽核）：`ADMIN`（全權）/ `SUPERVISOR` 主管 / `LEADER` 組長 / `TREASURY` 總務庫管 / `EMPLOYEE` 現場工程師。

| 端點 / 動作 | ADMIN | SUPERVISOR | LEADER | TREASURY | EMPLOYEE |
|---|:--:|:--:|:--:|:--:|:--:|
| `/api/auth/login`,`/me` | 公開 / 任何登入者 | | | | |
| `/api/auth/users`（建帳/列帳） | ✅ | — | — | — | — |
| Work Order 建立 | ✅ | ✅ | ✅ | — | ✅（自建自派受限） |
| Work Order 派工 dispatch | ✅ | ✅ | ✅ | — | — |
| Work Order 完工申報 | ✅ | ✅ | ✅ | — | ✅（限本人被指派） |
| 簽核 approve/reject | ✅ | 對映 step 層級（既有 signoff level 決定），角色須符該層 | | | |
| Material Request 建立 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Inventory 出入庫/調整 | ✅ | ✅ | — | ✅ | — |
| Inventory 查詢 | 任何登入者 | | | | |
| Cost / Reporting 檢視 | ✅ | ✅ | 讀？ | — | — |
| Knowledge / 警報 RAG | 任何登入者（現場工程師必需） | | | | |
| Monitoring 檢視 | 任何登入者 | | | | |
| Monitoring control / fault inject / farm 建立 | ✅ | ✅ | — | — | — |

> 這是**提案**。實際「誰能做什麼」是你的營運決策——請逐列確認或改。空格處尤其要你定（例：EMPLOYEE 能否建工單、LEADER 能否看成本）。

### 4.1 已實作端點的 RBAC（隨 router 遷移逐支落地，enforce=false 時全放行）

下表是**已寫進程式**的 gate（`require_role` / `require_authenticated`），依「動作性質」歸類。
cutover（翻 `WMOM_AUTH_ENFORCE=true`）前請對此表逐列確認；`ADMIN` 一律全權，故不另列。

| 端點 / 動作 | gate | 理由（動作性質） |
|---|---|---|
| Inventory 出入庫 `/adjust`（-05b） | `TREASURY` | 動 stock ＝ 總務庫管 |
| Material Request 建單 `create`（-05c） | 任何登入者 | 現場工程師發起 |
| Material Request 送簽 `submit-for-approval`（-05c） | 任何登入者 | 發起人自送 |
| Material Request 發料 `dispatch`（-05c） | `TREASURY` | 出庫（atomic stock-out）＝庫管 |
| Material Request 收料 `receive`（-05c） | 任何登入者 | 現場工程師收料確認 |
| Material Request 結案 `close`（-05c） | `LEADER` / `SUPERVISOR` | 生命週期收尾＝管理者 |
| Material Request 取消 `cancel`（-05c） | `LEADER` / `SUPERVISOR` | 撤單＝管理者 |
| Material Request 退料 `returns`（-05c） | `TREASURY` | 退料入庫（atomic stock-in）＝庫管；`returned_by` 沿用 body（可代登記） |
| Work Order 建單 `create`（-05d） | `EMPLOYEE` / `LEADER` / `SUPERVISOR` | 現場+管理層可建，庫管不建 |
| Work Order 派工 `dispatch`（-05d） | `LEADER` / `SUPERVISOR` | 派工＝管理層；actor 由 token 解析 |
| Work Order 開工 `start-work`、進度 `update-progress`（-05d） | 任何登入者 | 現場 assignee（update-progress actor 由 token 解析）|
| Work Order 完工 `finish`（-05d） | `EMPLOYEE` / `LEADER` / `SUPERVISOR` | 完工申報＝現場+管理層 |
| Work Order 結案 `approve` / 駁回 `reject` / 取消 `cancel` / 重開 `reopen`（-05d） | `LEADER` / `SUPERVISOR` | 生命週期管控＝管理層 |
| Approval 待簽列表 `/approvals/pending`（-05e） | 任何登入者 | 讀取自己的待簽 |
| Approval 簽核 `/approve`、駁回 `/reject`（-05e） | 任何登入者 + **token 身分** | 見下方註記 |

> 原則：**動 stock（出/入庫）= TREASURY**、**現場動作（建單/送簽/收料/開工/回報）= 任何登入者或含 EMPLOYEE**、
> **派工 / 生命週期管控（結案/取消/駁回/重開）= LEADER/SUPERVISOR**、**建單/完工 = 現場+管理層（庫管除外）**。
> 4 支 workflow router（inventory / material_request / approval / work_order）皆已依此分類遷移。

**-05h-1（workflow 收尾）**：補上 workflow router 的讀取端點與 inventory 料件管理寫入：
- `work_order` / `material_request` / `inventory` 的 `list` / `get`（含 warehouses / adjustments）→ 任何登入者
- `inventory` 建倉 `create_warehouse` / 建料件 `create_inventory_item` / 改 metadata `update_inventory_metadata` → `TREASURY`（庫管管理料件主檔）

**-05h-3（cost / reporting / knowledge）**：
- `cost`（forecast / lcoe / monte-carlo / var-fluct / ledger / ledger-summary）→ `SUPERVISOR`（成本檢視＝管理層；劉老師 2026-07-17 拍板 D 決策）
- `reporting`（templates / monthly / annual-budget）→ `SUPERVISOR`（報表檢視＝管理層）
- `knowledge`（alert / query / info）→ 任何登入者（警報 RAG，現場工程師必需）

**-05h-2（monitoring 9 支 router，61 端點）**：
- 讀取（turbines / faults·scenarios·active / farms 檢視+export / config 檢視 / export / i18n / control status / modbus status / maintenance 檢視）→ **任何登入者**（34 端點）
- 控制 / 故障注入 / farm 建立·clone / 資料集生成 / 設定變更 / 派工建單改單（control command·curtail、faults inject·clear·test-run、farms create·patch·activate·clone·datasets、config 各 POST、maintenance create·patch）→ `SUPERVISOR`（23 端點）
- 破壞性 / infra（farms `DELETE`、config `storage/maintenance`、modbus `start`·`stop`）→ `ADMIN`（4 端點）

> **-05h 全數完成**：4 支 workflow router + inventory 料件管理 + cost/reporting/knowledge + monitoring 9 支，
> 各 router 讀寫端點皆已掛 enforce-aware gate（enforce=false 全放行）。cutover（-05i，翻 `WMOM_AUTH_ENFORCE=true`）
> 前請對本 §4.1 逐列確認。**尚未做**：`/field/` 現場登入（-05g，需 D5）、cutover（-05i，需你在場）。

#### 註記：approval 的授權分兩層（-05e）

1. **router 層（本 PR 已做）**：`require_authenticated` + 簽核 `actor_id` 改由**已驗證 token** 決定
   （不再信任 body）。這讓既有「職責分離」（`_check_actor_separation`：同一人不可連簽同 chain
   先前階）建立在**可信身分**上——是本 PR 的核心安全增益。`test_approval_router_auth.py` 以
   「同一 token 連簽兩階 → 第二階 409」實測反證。
2. **domain 層（後續強化，未做）**：「該角色能否簽此 level」——step level（100/300/500/666）
   → 對映 EMPLOYEE/LEADER/SUPERVISOR/TREASURY 的逐階角色檢查。目前 `approve_step` 只驗身分
   （不驗角色），故 enforce 後任何登入者仍可簽任一階（只要沒連簽）。要補此檢查需讓 signoff
   domain 取得 actor 角色（注入 user store 或由 router 傳入），屬**架構性變更**，cutover 前若
   要收緊需單獨拆 issue（暫記 `WMOM-20260716-05e-followup`）。

---

## 5. 需要你拍板的決策

- **D1 Token 儲存**：`localStorage`（最簡，PoC 建議；XSS 風險）vs `httpOnly cookie`（防 XSS，需後端 cookie + CSRF 處理）。**建議 PoC 先 localStorage，合約前再評估 cookie 硬化。**
- **D2 RBAC 矩陣**：確認/修改 §4。
- **D3 Token TTL / refresh**：現 12h、無 refresh token。PoC 建議「12h + 過期回登入頁」，不做 refresh。
- **D4 登入 UX**：獨立登入頁 vs modal；要不要「記住我」。
- **D5 現場工程師 `/field/` 登入**：同一套帳密登入頁，還是簡化（PIN / 長效 token）？（現場手套操作，UX 要輕。）
- **D6 dev/demo**：`dev_mode` 保留 `UserSwitcher` + fallback（單人跑完整 lifecycle demo）——建議保留。
- **D7 切換時機**：P1+P2 全上、驗過後再翻 `WMOM_AUTH_ENFORCE=true`。誰在什麼環境翻（staging 先）。

---

## 6. 測試 & cutover 檢查表

- 每支 router 遷移 PR：`enforce=false` legacy 綠 + token 路徑綠 + `enforce=true` 下 401/403 綠。
- 前端：登入流程、token attach、401 導回登入。
- **cutover 前檢查**（翻 `true` 前）：
  - [ ] 4 支 workflow router 全遷移
  - [x] 前端所有寫入 request 都帶 token（2026-09-24，`WMOM-20260923-10` 稽核清單 7 支元件
    〔`FaultInjectionPanel`/`FarmSelector`/`SettingsPage`/`CostPage`/`EventComparisonView`/
    `HistoryPage`/`TrendChartPanel`〕全數改 `authFetch`，`WMOM-20260924-01~07` 逐檔完成）
  - [ ] admin 已用 `WMOM_ADMIN_USER/PASSWORD` bootstrap + 佈建真實使用者
  - [ ] staging 以 `enforce=true` 跑完整 lifecycle demo 通過
  - [ ] 回滾方案：翻回 `false` 即恢復（已驗證）

---

## 7. 建議子 issue 拆解（拍板後開）

| 子 issue | 內容 | 類型 |
|---|---|---|
| -05a | 後端 `resolve_actor()` + `require_role()` 雙模式 + `WMOM_AUTH_ENFORCE` 旗標 + tests | 🔵 |
| -05b | work_order_router 遷移 + RBAC | 🔵 |
| -05c | material_request_router 遷移 | 🔵 |
| -05d | inventory_router 遷移 | 🔵 |
| -05e | approval_router 遷移（+ signoff 疊加最小心） | 🔵 |
| -05f | 前端登入頁 + API client 帶 token + 401 處理 | 🔵（需 D1/D4） |
| -05g | 前端 `/field/` 登入 | 🟡（需 D5） |
| -05h | 其他 router（monitoring/cost/reporting）授權 | 🔵 |
| -05i | cutover：staging 驗證 + 翻 enforce + 清理 body actor_id | 🟡（需你在場） |

**建議節奏**：-05a → -05b（示範一支跑通模式）→ 你 review 確認模式 OK → 其餘 router 批次 + 前端平行 → 最後 -05i cutover。

---

## 8. 一句話

**先讓後端「能收 token 也能收舊 actor_id」、前端「登入拿 token 但也還送舊的」——兩邊都非破壞地上線後，再用一個環境旗標把「強制」一次打開、隨時可關回去。** 沒有 flag day，沒有登不進去的空窗。
