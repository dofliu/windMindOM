# 2026-09-26 — `day_work_form` 讀取端點 ownership 限制（WMOM-20260926-01 item 3）

## 認領

`WMOM-20260926-01`（第三個 autonomous session，接續前兩個 session：後端 domain/repo/router
`WMOM-20260505-21`、前端 `DayWorkFormPanel` tab）。issue 收攏 3 項延後工作，本次挑
**item 3：讀取端點 ownership 限制**（issue 內 `Priority` 欄位明文建議此項優先於 item 2
`work_order.finish()` hook，且設計歧義較低——不需要劉老師拍板）。

## 現況問題

`GET /day-work-forms`（list）/ `GET /day-work-forms/by-date` / `GET /day-work-forms/{id}`
三個讀取端點目前只掛 `require_authenticated()`（enforce=false 放行、enforce=true 也只檢查
「有沒有登入」，不檢查角色/身分），對任何登入角色開放——包含 TREASURY（庫管）也能查
任一員工任一天的完整工作日誌內容，違反「日誌是自填、隱私度接近私人記事」的設計初衷。

## 設計決策（無需劉老師介入，讀 code 可解）

讀了 `modules/auth/dependencies.py` 全部既有 dependency（`get_current_actor` /
`require_role` / `require_authenticated` / `resolve_actor_id` / `resolve_actor_id_optional`），
發現這個 repo 有兩種身分解析哲學並存：

1. **identity-resolution 族**（`resolve_actor_id` 等）：**無論 enforce 與否，一律優先信任
   token**——因為這類函式是給「誰執行了這個寫入」的 audit 身分用（如 signoff actor_id、
   day_work_form employee_id 代填檢查），就算 enforce=false 也要用真實 token 蓋掉 legacy
   body 值。
2. **access-control gate 族**（`require_role` / `require_authenticated`）：**enforce=false
   完全不觸碰 token**，直接放行——維持過渡期既有行為不變。

「讀取端點 ownership 限制」在語意上屬於第 2 類（access control，不是「這筆資料算誰的」
的 audit 身分），所以新加的 `resolve_actor_when_enforced()` 比照 `require_role` 的風格：
`enforce=false` 回 `None`（不限制，維持現有全開放行為，完全不解 token，避免 cutover 前
呼叫端剛好帶了 token 就意外被收窄）；`enforce=true` 才回傳已驗證的 `Actor`（token /
dev-fallback，同 `get_current_actor`）。

**視覺範圍**：只有 `LEADER` / `SUPERVISOR` / `ADMIN` 維持可查全員（`_FULL_VISIBILITY_ROLES`）；
`EMPLOYEE` 與 **`TREASURY`** 都收窄成只能查自己——issue 原文明確點名 TREASURY 是問題案例
（"TREASURY 庫管也能瀏覽任一員工任一天的完整工作日誌內容"），而建議的「維持可查全員」
清單只列了 LEADER/SUPERVISOR/ADMIN 三者，不含 TREASURY，故 TREASURY 這次一併收窄。

**行為差異（issue 原文給了兩個選項，依端點語意分別採用）**：
- `list`（`employee_id` 是可選 filter，不帶時本來就是「全員」）→ 收窄成**強制覆寫** 成
  自己（忽略帶入值），不報錯，維持「查得到東西」的體驗（沒有東西可覆寫就是空清單）。
- `by-date`（`employee_id` 是必填 query 參數，呼叫端明確指定了某人）→ 非本人 **403**
  （靜默覆寫會讓呼叫端誤以為拿到了他指定那個人的資料，實際上是別人的，更危險）。
- `{form_id}` detail（沒有 employee_id 參數，資料本身綁定 owner）→ 404 優先（不洩漏
  「這份存在但不是你的」），非本人 403，比照 `append_activity` 既有的 404-before-403 慣例。

## 實作

- `modules/auth/dependencies.py`：新增 `resolve_actor_when_enforced(request) -> Actor | None`。
- `modules/workflow/routers/day_work_form_router.py`：
  - `_FULL_VISIBILITY_ROLES = frozenset({Role.LEADER, Role.SUPERVISOR, Role.ADMIN})`
  - `_viewer_uuid(actor_id: str) -> UUID`（沿用既有 `_employee_uuid` 的 400 錯誤格式）
  - 3 個讀取端點各自補上 `request: Request` 參數 + ownership narrowing/403。
- `modules/workflow/tests/test_day_work_form_router_auth.py`：新增 regression tests（皆
  mutation-verified，見下方）。

## Mutation 驗證

TODO：完成後回填每個新測試的 mutation 結果（拔掉 narrowing/403 邏輯 → 確認測試真的 fail）。

## 驗證

TODO：backend / frontend 全套跑完回填數字。

## 下次接手

TODO（若跨 session）。
