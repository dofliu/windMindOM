# 2026-09-22（session #2）— accelerated 模式 stop() 響應性收尾（WMOM-20260922-01）

> Session 類型：實作（小型 follow-up）
> Session 長度：短
> 主導：Claude（autonomous worker）
> 結果：補上同日 session #1（WMOM-20260720-04/-08，PR #156）work-log §7 open questions 留的
> 殘留問題，`_loop` accelerated 分支同款 mutation-verified；code-reviewer subagent review 0
> Must-fix（Approve），1 Should-fix 已採納；backend 1094 passed / frontend 957 passed 全綠回歸。
> **同 session 也確認 CI runner 基礎設施持續失效**，非本 repo 可修復範圍，見 §4。

---

## 1. Session 目標

依 §4 決策樹開工，preflight 發現：

1. Stack-aware 檢查：`WMOM-20260720-04`/`-08`（M6 現場部署唯一硬阻塞）已在同日稍早由另一個
   session 合進 main（PR #156）。唯一 open PR（#157，`WMOM-20260720-13` A1 round-2 follow-up）
   本機驗證早已全綠，但 CI 兩個 job 持續在 2-3 秒內 `runner_id: 0` 失敗——前一個 session 已在
   PR #157 留言完整診斷為帳號/組織層級 GitHub Actions 問題，非程式碼可修。本 session 重跑一次
   （`rerun_failed_jobs`）確認仍未恢復（見 §4），不重複診斷、不再留言（診斷未變）。
2. Docker daemon 在本 sandbox 不可用（`docker info` 連不到 `/var/run/docker.sock`），
   `WMOM-20260716-06`（footprint）與 `WMOM-20260509-F6`（PostgreSQL row-lock）两個 docker-
   dependent 項目本次仍無法接。
3. 讀 §1 work-log §7 open questions：`modules/monitoring/simulator/engine.py` `_loop()` 的
   **accelerated 分支**（`time_scale > 1` 時，第 337 行 `time.sleep(wall_sleep)`）與已修的
   real-time 分支同一根因（不可中斷睡眠讓 `stop()` 得等它自然結束才能 `join()`），當時因原 issue
   文字只點名 real-time 分支（第 310 行）而未動。`set_time_scale` API
   （`/api/config/time-scale`，`config.py:254`）可在模擬跑著時即時調高倍率到 86400，屬可從外部
   觸發的正常路徑，非邊角案例——認領為本次工作（`WMOM-20260922-01`）。

---

## 2. 實際完成

### 2.1 主要工作

`modules/monitoring/simulator/engine.py`：`_loop()` accelerated 分支的
`time.sleep(wall_sleep)` → `self._wake.wait(wall_sleep)`（與 real-time 分支完全對稱的修法，
`stop()` 既有的 `self._wake.set()` 一併喚醒兩條路徑）。`_wake` 欄位宣告處註解同步更新（review
should-fix，見 §2.3）。

### 2.2 Mutation 驗證

新增 `test_stop_returns_promptly_during_accelerated_wall_sleep`
（`modules/monitoring/tests/test_engine_stop_responsive.py`）：`time_scale=2.0`、
`time_step=5.0` → `wall_sleep = max(0.1, 5/2*2) = 5s`，驗證 `stop()` 於 1s 內返回。

把修正還原成 `time.sleep(wall_sleep)` → 該測試 fail（`4.95s < 1.0` assertion error）；還原修正
後 3 個測試（含既有 2 個 real-time 分支測試）全過。

### 2.3 Code review 一輪（`code-reviewer` subagent，Phase 6）

跑 diff review（`git diff origin/main`，2 檔案），回報 **0 Must-fix，Approve**；1 Should-fix +
2 Nice-to-have：

- 🟡 **Should-fix「`_wake` 欄位宣告處註解過時」**：宣告處（`__init__`）只描述 real-time 分支，
  未涵蓋這次擴大的 accelerated 分支職責——已採納，補一句涵蓋兩條路徑並引用 WMOM-20260922-01。
- 🟢 Nice-to-have「兩處 `_wake.wait()` 呼叫可抽 helper」：reviewer 自己建議不在本次順手做（一致性
  優先於此次刻意比照既有已核准寫法），故不動。
- 🟢 Nice-to-have「`set_time_scale` 本身不會喚醒正在等待的舊 wall_sleep」：reviewer 明確判斷這是
  「動態調整 time_scale 反應延遲」的**不同問題**，非本次「保證 stop() 即時性」的範圍，記錄但不處理。

Review 過程中 reviewer 揭露：用 `git checkout --` 做 mutation-test 還原時誤把整個未 commit working
tree 一併清空，已立即發現並用原始 diff 精確重建、重新驗證與原狀 byte-for-byte 一致才繼續完成
review。我在收到 review 後自行重新確認 `git diff origin/main --stat` 與 3 個測試全過，結果與
reviewer 的自我核對一致，working tree 正確無誤。

### 2.4 卡住或延後的事

無阻擋項（本次工作本身）。CI 飛輪問題見 §4，非本次可解。

### 2.5 重大決策（如有）

無架構級決策，純 bug-fix，範圍延續同日 session #1 已定調的修法模式（第三次套用 Event.wait()
pattern）。

---

## 3. 產出清單

### 修改檔案

- `modules/monitoring/simulator/engine.py` — accelerated 分支 `time.sleep` → `Event.wait`；
  `_wake` 欄位宣告處註解更新
- `modules/monitoring/tests/test_engine_stop_responsive.py` — +1 測
  （mutation-verified）+ 檔案頂部 docstring 補充背景
- `ISSUES.md` — 新增 `📌 2026-09-22 session` 區塊記 WMOM-20260922-01 done + CI 基礎設施狀態；
  統計表 done 102→103、total 114→115
- `STATUS.yaml` — `last_updated` 追加本 session 摘要、`next_milestone` 更新下次接手指引（提醒
  查 PR #157 CI 是否恢復）、`issue_stats.done` 102→103
- `TODO.md` — 更新最後更新時間 + baseline 數字（1090→1094）+ CI 基礎設施失效提醒

### 動了狀態的 issue

- WMOM-20260922-01: open → done（新開直接收）

### 寫進 decision_log 的決策

- 無

---

## 4. CI runner 基礎設施狀態（誠實記錄，非本次修復範圍）

PR #157（`WMOM-20260720-13`）兩個 CI job（Backend pytest / Frontend vitest+tsc+build）持續失敗：

- 本 session 對 run #35715611000 觸發 `rerun_failed_jobs`：queued 後仍在 2 秒內完成、失敗，
  `runner_id` 未變。
- 對照 `main` 分支 push-triggered run（PR #156 merge commit，run #35699865215）也是同款
  4 秒內失敗，排除「這是 PR #157 程式碼問題」的可能性（那是已測過、已合併的 merge commit）。
- `.github/workflows/ci.yml` 內容本身無異動、無語法問題。
- 前一個 session（PR #157 留言 2 則）已完整診斷並記錄：研判為帳號/組織層級 GitHub Actions
  runner 配額或計費限制，需人工檢查 GitHub 帳號設定或 https://www.githubstatus.com/ 平台事故。

本次僅重新確認診斷仍成立（未再留新言，因診斷內容未變），未嘗試繞過（不跳過測試、不停用 CI、
不直接 push main）。**PR #157 的變更本身（A1 round-2 的 4 個 Should-fix）本機已完整驗證通過**，
一旦 CI runner 恢復，auto-merge 應會自動合併，不需要重新開發。

**給劉老師的提醒**：這是連續第二個 session 遇到同款 CI 秒退失敗，已排除是本 repo 程式碼/workflow
設定問題，需要人工介入檢查 GitHub Actions 帳號用量或帳單設定。

---

## 5. 下次怎麼接手

1. **最優先**：檢查 PR #157 的 CI 是否已恢復（`gh pr checks 157` 或 GitHub UI）。若綠，
   auto-merge 應已自動處理；若仍秒退失敗，此為人工待辦（帳號層級），autonomous session 不需要
   再重複診斷或重跑，直接跳過去找下一件事做。
2. **第二優先**：`WMOM-20260716-06`（footprint CPU-torch pin）或 `WMOM-20260509-F6`
   （PostgreSQL row-lock），兩者都需要 docker daemon——本 sandbox 目前只有 docker **client**、
   無 daemon（`docker info` 連不到 socket），若未來 sandbox 有 daemon 可挑。
3. **阻擋項**：CI runner 基礎設施（見 §4），非 autonomous session 可解，已充分記錄待人工處理。

---

## 6. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| Preflight（含確認 CI 基礎設施現況、docker 可用性排除） | 20% |
| 定位殘留問題 + 寫修正 | 15% |
| 寫新測 + mutation 驗證 | 20% |
| Code review + 採納 should-fix | 15% |
| 全套 baseline 驗證（backend 兩輪 + frontend）+ 文件收尾 | 30% |

---

## 7. 學到的事

- **work-log 的「open questions」區塊是下一個 session 的現成工作來源**：本次工作完全來自前一個
  session 明確記錄「範圍外但已知」的殘留問題，無需重新探索或猜測，是 autonomous worker 決策樹中
  「M6 critical path」與「無設計歧義」兩個條件都滿足的理想候選——比翻閱整份 ISSUES.md 找新工作
  更省時、風險更低（修法已有先例三次驗證過）。
- **CI 基礎設施失效時的正確反應是「確認仍持續、記錄、繼續做別的事」，不是「反覆重跑到綠」**：
  per repo 的 babysit 規則，flaky 只重跑一次；本次確認診斷未變後就不再糾結，把心力放回可控的
  工作項目。

---

## 8. Open questions（park）

- （沿用自 session #1 §7，本次未展開）`config.py::set_datasource` 沒有比照 `set_simulation`
  加來源守門；`set_time_scale` 本身不會喚醒正在等待的舊 wall_sleep（reviewer 本次指出，見 §2.3）。
