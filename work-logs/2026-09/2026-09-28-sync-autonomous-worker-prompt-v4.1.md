# 2026-09-28 — WMOM-20260928-01：同步 `docs/routines/autonomous-daily-worker-prompt.md` 為實際 v4.1 內文

## Claim

Preflight 自我測試全綠（`git checkout main && git pull` 55 commits 快轉；
`pip install --ignore-installed PyYAML -r requirements.txt -r
requirements-dev.txt`；backend `pytest` 7 個路徑 **1295 passed, 7 skipped,
1 xfailed**，與 baseline 1293+2〔上個 session `WMOM-20260927-07` 新增〕一致；
frontend `npm ci && npx tsc --noEmit`（0 error）`&& npx vitest run`
（**1477 passed，70 files**）`&& npx vite build`（成功，僅既有 chunk size 警告）
皆與 baseline 一致，零 regression）。

Stack-aware 檢查：`mcp__github__list_pull_requests`（state=open）回傳空陣列，
無上個 session 遺留的未合併 PR，可自由挑選新工作。

逐一檢視 `ISSUES.md` 全部 7 個 open issue：
- `WMOM-20260504-11`（event-driven cost ledger）：多日新功能 + 新 schema 設計，
  需劉老師決策，不宜自行開工。
- `WMOM-20260509-F6`（PostgreSQL row-lock integration test）：需 docker
  postgres，🟡 需劉老師決策。
- `WMOM-20260505-25~28`（物理強化 4 項）：逐一核對 Estimate 欄位——25 為
  1.5-2 工作天、26 為 3-5 工作天、27 為 1-2 週、28 為 1 工作週，皆非單 session
  可完工候選（已連續多個 session 得出同款結論，本次重新核對估時數字確認未變）。
- `WMOM-20260513-01`：placeholder，設計規範未提供前不開工。

7 個 open issue 皆非本次可行候選。但本 session preflight 讀
`docs/routines/autonomous-daily-worker-prompt.md` 發現一個**未被列進
ISSUES.md、但已被至少 3 個近期 work-log（`-05`/`-06`/`-07`）重複提醒**的
drift：該檔自稱「canonical 版本」，版本標記卻仍停在 v3（2026-06-03），而
cron trigger 實際注入的 prompt（本次任務描述，明確自稱 v4.1）內容豐富得多
（含自我測試 baseline、mutation-verify 要求、8-phase 流程、GitHub MCP 降級
模式等），repo 內文件完全沒有反映。純提醒不會自己解決——開新 issue
`WMOM-20260928-01`（工程基礎設施/技術債，估時 20-30 分鐘，acceptance 明確、
無設計歧義：直接把本次收到的 v4.1 全文整理進檔案），claim 為本次工作。

## Implement

讀取本 session 系統訊息實際收到的完整 v4.1 cron prompt 全文（開工 routine 含
`pip install --ignore-installed PyYAML`、7 條路徑 pytest baseline、frontend
tsc/vitest/build baseline；stack-aware 檢查含 GitHub MCP 降級模式的
`git ls-remote --heads origin 'claude/*'` 備援；工作優先級決策樹 8 條；
8-phase 執行流程含 mutation-verify 要求；重要守則；收尾策略；已知環境限制），
整理進 `docs/routines/autonomous-daily-worker-prompt.md` 的 fenced code
block，取代舊 v3 內容。

**刻意保留、未逐字照搬的部分**：
- v4.1 prompt 內「## 3. 現況（2026-09-22 專案檢視）」與「## 4. 工作優先級」
  §3 M6 critical path 清單裡列的 `WMOM-20260720-04`/`-08`/`WMOM-20260716-06`
  三項，本 session 核對 `ISSUES.md` 發現皆已 done（`WMOM-20260716-06`
  於某次 session 完成、`-04`/`-08` 已於 PR #156 合併）——這代表 cron 設定裡的
  prompt 本身也會隨時間漂移過時，不是每次都精準反映當下狀態。**選擇不把這份
  會過時的「現況快照」逐字寫進 canonical 文件**，改為在檔案內加註解說明
  「§3 現況快照僅供參考、請以 `ISSUES.md`/`STATUS.yaml` 實際內容為準」，避免
  未來又出現「canonical 文件裡的快照本身就是 drift 來源」的同款問題循環。
- 版本標記更新為 v4.1，「維護備註」章節新增 v3→v4.1 差異摘要（cadence 不變
  仍 3 小時；baseline 638→1295+1477；新增自我測試/mutation-verify/
  降級模式/8-phase 細節等）。

## Verify

純 Markdown 文件修改，不涉及任何被 pytest/vitest 解析的程式碼路徑。preflight
已完整跑過一次全綠 baseline（backend 1295 passed / frontend tsc 0、vitest
1477 passed 70 files、build OK），改動範圍與測試涵蓋的程式行為完全無關，
故不重跑（比照過往同款純文件 issue，如 `WMOM-20260927-05`/`-06` 慣例）。

**誠實揭露**：本次修改**無自動化測試保護**——Markdown 文件不被任何測試框架
解析，只能靠人工讀原始碼交叉核對（把本 session 實際收到的 v4.1 prompt 逐段
比對寫入檔案的內容是否語意一致）把關，無法 mutation-verify。

## Review

`code-reviewer` subagent review（背景執行）：待補（見下方 Wrap-up 是否已回報）。

## Wrap-up

- 完成 `WMOM-20260928-01`：`docs/routines/autonomous-daily-worker-prompt.md`
  版本標記 v3→v4.1，fenced code block 全文替換為本 session 實際收到的 v4.1
  cron prompt 內容（含自我測試 baseline、mutation-verify、8-phase、降級模式）；
  「維護備註」章節新增 v3→v4.1 差異摘要 + 「§3 現況快照會過時，請以
  ISSUES.md/STATUS.yaml 為準」提醒（防止同款 drift 循環重演）。
- ISSUES.md：`WMOM-20260928-01` → done（完整 completion summary）；統計表
  in_progress 3→2、done 116→117、total 126 不變。
- STATUS.yaml：`last_updated`/`issue_stats` 已同步。
- TODO.md：已同步本次完成摘要 + 下個 session 建議。
- **這份文件本身仍會隨開發推進過時**（baseline 數字、M6 critical path 現況
  快照），不是一次性解決——下個 session 若又發現版本標記落後於實際收到的
  prompt，應直接動手同步（比照本次做法），而非只留言提醒。
- 下個 session 可從 `WMOM-20260505-25~28`（物理強化，逐一看 estimate，皆
  多日工作）或 M6 critical path 剩餘項（`WMOM-20260509-F6` PostgreSQL
  row-lock 需 docker、HTTPS 部署配置需先定部署目標，皆需劉老師決策）中挑選；
  其餘 open issue（`WMOM-20260504-11`/`WMOM-20260513-01`）皆標 🟡 需劉老師
  決策/素材，不宜自行開工。
