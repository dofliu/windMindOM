# ⚠ CRITICAL — main branch 疑似被回退（rollback），32 個已合併 PR 從 main 消失

- **日期**：2026-09-25
- **Session 類型**：autonomous worker routine（3 小時一次）
- **狀態**：🔴 完全卡住 — 已停止本輪正常工作，等待劉老師確認

## 發現什麼

Preflight 階段（`git fetch origin main` + 比對）發現：

- `origin/main` 目前指向 commit `5555112`（2026-09-01，PR #155「3 分鐘介紹影片成片」）。
- 但這個 session 拿到的環境注入分支 `claude/inspiring-mccarthy-ayxama`（fork 自當時的 main）
  領先 `origin/main` **40 個 commit**，最新到 commit `74495d4`（2026-09-25 16:31:15，
  PR #187「inspection_schedule 定檢計畫」）。
- 用 GitHub API 逐一確認 PR #187（以及 #156～#186，共 **32 個 PR**）都是 `merged: true`，
  由 `github-actions[bot]`（auto-merge 飛輪）在 2026-09-22 06:43 ～ 2026-09-25 16:31
  這段期間正常合併進 `main`。
- 但現在 `origin/main` 卻停在更早的 `5555112`，且 `5555112` 是 `74495d4` 的**直系祖先**
  （`git merge-base --is-ancestor origin/main 74495d4` → true）。
  → 這代表 **main 的 ref 被回退（force-push 或等效操作）**，不是正常的 3-way 分岔，
  而是乾淨地「往回指」，抹掉了 2026-09-22～09-25 這 3 天、40 個 commit、32 個 PR 的工作
  （WMOM-20260720-04/-08 live/OPC 硬化、A1 round-2 review、authFetch 稽核系列
  WMOM-20260923-xx～20260925-xx、inspection_schedule 後端等）。
- 這些已合併 PR 的來源分支（例如 PR #187 的 `claude/inspiring-mccarthy-abc6xh`）
  auto-merge 飛輪已依慣例刪除，**GitHub 上已無其他活分支保留這段歷史**。

## 已採取的緊急保全動作

- 立刻把這個 session 本地擁有完整歷史的分支 push 上 GitHub：
  `git push -u origin claude/inspiring-mccarthy-ayxama`（成功，tip = `74495d4`）
  → **這段歷史目前已經安全備份在 GitHub 上**，不會因為這個 sandbox session 結束而遺失。
- **沒有**對 `main` 做任何寫入（沒有 force-push、沒有 fast-forward、沒有開 PR 合併回去）。
  沒有足夠資訊判斷這次 main 回退是「意外」還是「劉老師故意要退回某個狀態」，
  這個判斷只有劉老師能做，所以刻意不自作主張還原。

## 建議的還原方式（若確認是意外）

`origin/main` 目前的 `5555112` 是 `74495d4` 的祖先，所以還原是**乾淨的 fast-forward**，
不需要 force、不會有 conflict：

```bash
git fetch origin claude/inspiring-mccarthy-ayxama
git push origin claude/inspiring-mccarthy-ayxama:main   # fast-forward，安全
```

或透過 GitHub 網頁把 `main` 的 branch ref 手動改回 `74495d4`。

## 本輪 routine 決定

依 §4 決策樹第 8 項「真的沒有乾淨 autonomous 工作」處理：這不是「沒事做」，
而是「有一件比任何 M6 工作都優先、但只有人類能決定怎麼處理」的事——
在 main 的真實狀態確認之前，繼續在（可能錯誤的）舊 main 基礎上開新 PR
只會讓修復更複雜（新工作會 base 在遺失了 3 天內容的 main 上）。

**本輪不開新 PR、不認領新 issue。** 已透過 PushNotification 通知劉老師。

## 給下一個 session 的交接

1. 先確認劉老師怎麼處理（是否要 fast-forward 還原 main）。
2. 若已還原：`git checkout main && git pull origin main` 應該會看到 `74495d4` 為 tip，
   之後正常走 §2 開工 routine 即可（baseline 測試數字請參考 PR #187 記錄的
   `1182 passed, 7 skipped, 1 xfailed`，而非本檔案開頭 prompt 裡舊的 1076/970 數字——
   看起來 `docs/routines/autonomous-daily-worker-prompt.md` 或 `STATUS.yaml` 的 baseline
   也需要跟著更新，之後再核對一次實際跑出來的數字）。
3. 若劉老師說是刻意回退：這份 work-log 保留備份分支資訊
   （`claude/inspiring-mccarthy-ayxama` @ `74495d4`）供之後想挑救回某些 commit 時使用，
   之後可以視情況 delete 這個備份分支或留著。
4. 建議順手調查一下**為什麼 main 會被回退**（GitHub Settings → branch protection 是否讓
   force-push 生效、有沒有 Actions log 可查、是不是有人在本地跑了
   `git push --force origin <舊分支>:main`），避免下次又發生。
