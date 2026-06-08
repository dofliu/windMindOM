# 2026-06-08 Follow-ups — 完工佐證大小上限 + 退料 guard 重做

- **Branch**: `claude/issue-followups-2026-06-08`
- **Issues**: WMOM-20260608-02 follow-up（佐證大小上限）+ WMOM-20260519-01（退料 guard，salvage #41）

## #2 完工佐證大小上限（WMOM-20260608-02 follow-up / review must#3）

- `FinishRequest` 加 `max_length`：signature 3M（~2.2MB base64）/ 每張 photo 10M（~7.5MB）/ 最多 8 張
- 防 base64 無界炸 request body + SQLite
- +2 tests（oversized signature / too many photos → 422）

## #3 退料 guard 重做（WMOM-20260519-01，採 PR #41 semantic）

- `_assert_return_within_physical_ceiling`：`physical_ceiling = actual_qty if set else estimated_qty`，
  聚合 by (request_id, item_id) 跨 stock_kind；`max_returnable = Σ ceiling − 已退`，超量 → `MaterialRequestRuleViolation`（router 422）
- add_return MR row `with_for_update` 序列化；三寫前先擋（atomic rollback）
- docstring 從「⚠ caller 責任」改為「✅ guard 已加」
- tests：`test_add_return_over_return_guard.py` 7（estimated/cumulative/received-actual 降上限/not-in-MR/atomic + 2 happy）
- 修 1 個編碼 F1-bug 的舊測試（`test_add_return_increments_stock` estimated 1→2）

## Verify
- 全 backend **721 passed / 1 xfailed**（零 regression）

## 踩坑
- `MaterialRequestRuleViolation` 定義在 `material_request_repository.py`（非 domain.inventory）
- `ReturnReason` 無 UNUSED，值為 SURPLUS/WRONG_PART/FAILED_INSTALL/OTHER

## M5-3/4（未做，blocked）
RAG_Ultimate 只有 27-chunk test fixture，無完整 Z72 手冊向量檔。windMindOM 端已 ready（換 export_dir 即可），
需 RAG_Ultimate 用 `docs/__Z72UserManual.pdf` 跑 ingest 產出 export（研究端任務，待劉老師拍板）。
