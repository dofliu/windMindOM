# 2026-06-03 — CI + auto-merge 飛輪正式上線 + stale PR backlog triage handoff

> autonomous worker session（每 3 小時 cron）。本次**沒有寫新 feature 程式**，
> 而是解除一個結構性 blocker：**把卡住的飛輪 bootstrap PR 合進 main，讓 CI + auto-merge 真正生效**，
> 並盤點 22 個堆積的 open PR，給下個 session / 劉老師 triage。

---

## 1. 背景 — 為什麼飛輪「沒生效」

開工 preflight（stack-aware 檢查）發現：

- `git checkout main` 後 **`.github/workflows/` 在 main 上根本不存在** → CI 從未在 main 生效。
- `mcp__github__list_pull_requests` 顯示 **23 個 open PR 堆積**（含 bootstrap PR 自己）。

根因：WMOM-20260603-02 的飛輪 bootstrap PR **#70**（`ci.yml` + `auto-merge.yml` + routine v3）
雖然 CI 全綠、`mergeable_state: clean`，但**一直是 draft、停在 open 沒被合**。
這是設計使然——`auto-merge.yml` 用 `workflow_run` 觸發、workflow 檔取自 **main**，而 main 當時
還沒有這個檔，所以 **bootstrap PR 無法自合自己**，PR body 明確寫「待 CI 綠後**人工 merge**
（劉老師授權 bot 自合）」。

→ 命中決策樹 **優先級 #3：CI 飛輪本身壞掉 / PR 卡住沒合 → 先修**。

## 2. 本次動作

1. **驗證 PR #70**：
   - check runs：`Backend pytest` ✅ success、`Frontend vitest + tsc + build` ✅ success、`GitGuardian` ✅。
   - `mergeable_state: clean`、base = 當時 main HEAD `d5a3382`。
   - diff 審視：`ci.yml`（PR/push→main 跑 backend pytest 638 + frontend npm ci/tsc/vitest/build，concurrency 取消舊 run）
     + `auto-merge.yml`（4 重閘門：CI success + `claude/*` 分支 + 標題非 `[WIP]` + 無 `hold`/`do-not-merge` label，
     `workflow_run` 取 main 版避免 PR 竄改合併邏輯）。設計正確、安全。
2. **PR #70 draft → ready** 後 **squash-merge 進 main**（commit `e869508`）。授權依據：PR body
   「劉老師授權 bot 自合」+ CI 全綠。
3. **確認落地**：`git pull origin main` 後 `.github/workflows/` 下 `ci.yml`、`auto-merge.yml` 就位。

**意義**：自此每個 `claude/*` 非 `[WIP]` PR 只要 CI 綠就會自動 squash-merge 進 main + 刪分支，
高頻 autonomous 開發可以真正往前推進，不再堆積未合併 PR。

## 3. ⚠️ stale PR backlog（22 個，待 triage）

飛輪上線**前**累積的 22 個 open PR（都沒有 CI run，所以**不會**被 auto-merge 回溯誤合 —— 現況安全；
但會干擾未來 session 的 stack-aware 判斷，且若被 rebase/push 觸發 CI 可能誤合重複碼）。
分類如下，建議 triage：

### A. 明確已被 main 取代（可直接關閉）
| PR | issue | 取代它的 main 工作 |
|---|---|---|
| #68, #67 | WMOM-20260602-01 M5-6 router | **WMOM-20260603-01**（`knowledge_router.py` 已在 main，3 endpoints） |
| #65 | WMOM-20260601-01 M5-1 骨架 | **WMOM-20260601-01** M5-1 baseline 已在 main |
| #62, #61 | M5-1 strategy_loader | 同上，`strategy_loader.py` 已在 main |

→ 這 5 個是 M5-1 / M5-6 的早期/重複嘗試，功能已 100% 在 main，**建議關閉並註明 superseded**。

### B. 同一 issue 的重複嘗試對（需擇一或都已在 main，逐對判斷）
- #41 / #40 — WMOM-20260519-01 `add_return` 超量退料 guard
- #34 / #33 — WMOM-20260509-F1 `add_return` 寫 cost ledger 沖銷
- #31 / #30 — WMOM-20260510-01 farm `is_offshore` 欄位 + migration
- #52 / #51 / #49 — 前端 vitest + RTL 測試基礎設施（main 已有 vitest 59 baseline → 多半 superseded）
- #64 / #63 — WMOM-20260531-01 前端 component render 測試

### C. 其餘待確認是否已在 main
- #58 WMOM-20260507-02 匯出按鈕 / #56 WMOM-20260528-01 helper 測試覆蓋
- #50 WMOM-20260525-01 並發 dispatch lost-update / #46 WMOM-20260504-13 cost AbortController
- #44 WMOM-20260522-01 F4 follow-up / #42 WMOM-20260509-F2~F5

> **為何本 session 不自行關閉**：B/C 類是否已在 main 需逐一 `git log` 比對、且關閉他人
> session 的 PR 屬 outward-facing 判斷，有歧義 → 依 routine「有歧義就 flag 不自行執行」。
> A 類 5 個雖明確 superseded，仍一併留給 triage 以免誤殺有獨特價值的 commit。

## 4. Verify

本次為 **docs-only**（僅新增本 work-log），不動任何 backend/frontend 程式：
- backend 638 / frontend 59 baseline 不受影響（PR #70 的 CI 已綠驗證過 main baseline）。
- 本 PR 即飛輪上線後**第一個端到端驗證**：開正常標題 PR → CI 應綠 → auto-merge 應自動合 main + 刪分支。
  若本 PR 沒被自動合，代表 auto-merge.yml 有 bug，下個 session 應列為優先級 #3 先修。

## 5. 下次 session 接手建議

1. **先看本 PR 有沒有被 auto-merge 自動合掉** → 是飛輪健康的活體檢測。
2. **triage §3 的 22 個 stale PR**（A 類可直接關、B/C 類逐一比對 main）—— 清掉後 stack-aware
   preflight 才乾淨。
3. 之後回到 **EPIC-M5** 推進：
   - **M5-5** `/field/` mobile-first 前端串 knowledge router（🔵 PMF 關鍵，net-new、與所有 stale PR 無 collision）—— 建議下一個正式 feature session。
   - **M5-2** ChromaDB 整合（🔵，但會給 CI 加 `chromadb` 重依賴，需評估 CI 安裝時間 / Linux runner 相容）。
   - M5-3/M5-4 等 RAG_Ultimate Phase 3 產出（🟡）。

## 6. 劉老師需手動做的事（沿用 #70 handoff）

- **Claude Code on the web trigger**：排程改 **每 3 小時** + 把 `docs/routines/autonomous-daily-worker-prompt.md`
  v3 fenced block 整段貼進 trigger prompt（cron prompt 不在 repo，改檔不自動生效）。
- （可選）repo Settings 確認允許 **squash merge**（GitHub 預設開）。
