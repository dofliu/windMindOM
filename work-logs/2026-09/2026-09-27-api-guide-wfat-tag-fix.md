# 2026-09-27 — WMOM-20260927-05：`docs/API_GUIDE.md` 仍教學查詢不存在的 `WFAT_*` SCADA tag

## Claim

`ISSUES.md` open issue `WMOM-20260927-05`，priority low、估時 10-15 分鐘，acceptance
明確（`docs/API_GUIDE.md` 5 處 `WFAT_*` tag 名稱改成對應的 `WLOD_*`）。

Stack-aware 檢查：`mcp__github__list_pull_requests` 回傳空陣列，確認沒有上個
session 留下的未合併 PR（上個 session `WMOM-20260927-04` 的 PR #201 已 auto-merge
進 main）。M6 critical path 檢查：`WMOM-20260720-04`/`-08`（唯一硬阻塞）已於 PR #156
完成；`WMOM-20260716-06`（footprint CPU-torch pin）已完成；剩下的
`WMOM-20260509-F6`（PostgreSQL row-lock）與 HTTPS 部署配置皆需劉老師先決策，非本次
候選。情境比較分析 epic（A2/PR C/PR D/A3）已於前幾個 session 收尾。open issue 清單
（8 筆）逐一檢視：`WMOM-20260504-11`（多日新功能設計）、`WMOM-20260505-25~28`
（物理強化，皆多日工作）、`WMOM-20260513-01`（等劉老師交接書）皆非單 session 可完工
候選。`WMOM-20260927-05` 是本次唯一「單 session 可完工、無設計歧義」候選（前一 session
`WMOM-20260927-04` 的 code review 也建議續評估這個）。

## Implement

先重新核實 5 處引用位置與正確的新舊 tag 對應（不照單全收 issue 描述，自己重新查證）：

- `grep -n "WFAT_" docs/API_GUIDE.md` 確認確實有 5 處（第 108-114 區塊 7 個 tag +
  第 149、202、278、397 行各 1 處內嵌使用）。
- 核對 `modules/monitoring/simulator/physics/scada_registry.py`（348-398 行）：現行
  schema 只登記 `WLOD_*` 系列 **16 個** tag（`WLOD_TwrFaMom`/`WLOD_TwrSsMom`/
  `WLOD_BldFlapMom`/`WLOD_BldEdgeMom`/`WLOD_DelTwrFa`/`WLOD_DelTwrSs`/
  `WLOD_DelBldFlap`/`WLOD_DelBldEdge`/`WLOD_DmgTwrFa`/`WLOD_DmgTwrSs`/
  `WLOD_DmgBldFlap`/`WLOD_DmgBldEdge`/`WLOD_ProdHours`/`WLOD_AlmTwr`/`WLOD_AlmBld`/
  `WLOD_RulHours`），完全沒有 `WFAT_*` 定義。舊文件列出的 7 個 `WFAT_*` 沒有乾淨的
  1:1 對應——`WFAT_DELTwr`/`WFAT_DELBld`/`WFAT_DmgAccum` 這 3 個在現行 schema 已拆成
  Fore-Aft/Side-Side（塔架）與 Flapwise/Edgewise（葉片）各自獨立的 tag，不是簡單改名。
  **設計判斷**：與其把「參考清單」區塊硬湊成 7 個假的 1:1 映射（會漏掉 Ss/Edge
  對應項與 ProdHours/AlmTwr/AlmBld/RulHours 這幾個現行 schema 真實存在但舊清單完全
  沒提到的 tag），改成直接列出 `scada_registry.py` 現行真正註冊的完整 16 個
  `WLOD_*` tag（單位/中英文說明皆逐一核對 `ScadaTag(...)` 原始定義），對應
  acceptance 「範例程式碼裡的 tag 名稱與現行 scada_registry.py 實際註冊的 tag
  一致」的字面要求更精準。
- 4 處內嵌範例程式碼（第 149、202、278、397 行，皆用 `WFAT_TwrBsMy`）改成
  `WLOD_TwrFaMom`——對應關係沿用 `WMOM-20260927-02`/`WMOM-20260927-04` 已確認的
  映射（兩者皆代表「塔架前後彎矩 / Tower fore-aft moment」）。
  - 第 278 行原本的 f-string 標籤 `TwrMy=` 順手改成 `TwrFa=`，與
    `WMOM-20260927-04` 對 `fetch_scada_data.py` 做過的同款標籤一致性修正對齊。
- `grep -n "WFAT_" docs/API_GUIDE.md` 確認全檔已無殘留舊 tag 引用。

## Verify

**誠實揭露**：本次修改**沒有自動化測試保護**——`docs/API_GUIDE.md` 是純 Markdown
文件，不被任何 pytest/vitest 解析或執行，沒有「改回舊邏輯讓測試 fail」這個概念可驗
（不適用 mutation-verify）。驗證方式僅止於：

1. 逐一核對 `scada_registry.py` 348-398 行的 `ScadaTag(...)` 原始定義，確認新增的
   16 個 `WLOD_*` tag 名稱、單位（kNm / h / 無單位）、alarm level 範圍（0-4）皆與
   registry 一致。
2. `grep -n "WFAT_" docs/API_GUIDE.md` 確認零殘留。
3. 讀修改後的 4 處範例程式碼上下文（trend tags 逗號分隔字串、`.describe()` 欄位
   list、f-string 格式）確認語法與周圍程式碼慣例一致。

**刻意不修的範圍外項目**：文件第 141 行附近「`scada = t['scadaTags']  # dict of 74
tag_id -> float`」這個「74」的數字，實測 `grep -c '^\s*ScadaTag(' scada_registry.py`
目前是 **109**，與文件不符——但這是另一個獨立、與本 issue「WFAT_* tag 名稱錯誤」
無關的既有數字漂移問題（全部 tag 家族的總數，不只 Fatigue/Load 這一組），不在本次
acceptance 範圍內，未修正，留待劉老師或未來 session 評估是否要開新 follow-up。

Backend/frontend 全套自我測試（本次唯一改動的檔案是文件，不在任何測試匯入路徑內，
預期零影響，仍照 routine 全套重跑確認無 regression）：

- 環境設置：`pip install --ignore-installed PyYAML -r requirements.txt
  -r requirements-dev.txt`（新 sandbox，符合已知限制）。
- backend：`pytest modules/workflow/tests/ modules/cost/tests/
  modules/reporting/tests/ modules/knowledge/tests/ modules/monitoring/tests/
  modules/auth/tests/ tests/` → **1293 passed, 7 skipped, 1 xfailed**（比
  `docs/routines/autonomous-daily-worker-prompt.md` 記載的 baseline 1076 多，
  屬正常累積漂移，非 regression——與過去多個 session 的觀察一致：該檔案內文
  仍停在 v3、baseline 數字早已過時，`STATUS.yaml`/`ISSUES.md` 也未維護獨立的
  `test_baseline` 欄位，本次沿用既有慣例不動該檔案，只在此誠實記錄目前實測
  數字，並在下方繼續提醒劉老師同步 cron trigger 內文）。
- frontend：`npm ci` + `npx tsc --noEmit`（0 error）+ `npx vitest run`
  （**1477 passed，70 files**，同樣比記載 baseline 970 多，正常漂移）+
  `npx vite build`（成功，僅既有的 chunk size 警告，非本次改動引入）。

## Review

`code-reviewer` subagent review 在背景執行，本次 session 收尾提交（commit）後才
回報（詳見下方「已知限制」，非跳過 review——是驅動 PR 到綠燈的正常流程，發現後立刻
補 follow-up commit）。

**Review 結果：1 must-fix 已修復、1 should-fix 已登記新 issue、1 nice-to-have 已
記錄**：

1. 🔴 **must-fix（已修復）**：reviewer 用「裸 subsystem 代碼」正規表達式（不只是
   帶底線的完整 tag id）額外掃出本次 diff 完全沒觸及的第 69 行——`## SCADA Tag
   System` 底下的 subsystem breakdown table 仍有一列
   `WFAT | 7 | Fatigue loads...`，緊接在剛修好的「Structural Load & Fatigue」
   段落正下方，讀者會看到自相矛盾的資訊。這是我第一輪只 grep `WFAT_`（帶底線）
   漏掉的同類殘留（裸 subsystem 代碼沒有底線+tag 名）。已修正為
   `WLOD | 7 | Structural load & fatigue...`——**刻意只改 subsystem 代碼與敘述，
   不動 count 數字**（見下方 should-fix 說明為何 7 這個數字本身不在本次範圍）。
2. 🟡 **should-fix（已登記新 issue，未修）**：reviewer 獨立實測
   `grep -c 'ScadaTag(' scada_registry.py` 目前是 **109**，逐一比對
   per-subsystem 統計後發現整張 breakdown table（含「74 SCADA tags」表頭）多處
   與現行 registry 不符（`WROT` 9→10、`WMET` 3→14、`WVIB` 20→30，且完全沒列
   `WCOL`/`WDRV` 兩個現行存在的 subsystem）。這是遠超本 issue「WFAT→WLOD 改名」
   範圍的全面重新盤點（14 個 subsystem 逐一核對），reviewer 建議不要只在
   work-log 私下記一筆，需正式登記可認領的 issue——已開 **WMOM-20260927-06**
   （open，估時 0.5-1 工作天）。
3. 🟢 **nice-to-have（記錄於新 issue，未修）**：
   `turbine_physics.py:1381-1383` 的 `_get_sensor_config()` 內有一段對
   `WFAT_TwrBs`/`WFAT_BldRt` 字首的死碼分支（registry 從不產生此字首，永遠打不
   到），記錄於 `WMOM-20260927-06` 供未來一併清理，非本次範圍。

Reviewer 也建議了一支一次性驗證 script（同時檢查完整 tag-id 與裸 subsystem
代碼兩種模式，因為只檢查其中一種會像我第一輪一樣漏掉另一種）；因為是一次性用途
非常駐測試，未納入本次 PR，留給下次維護此文件時參考。

## Wrap-up

- 完成 `WMOM-20260927-05`：`docs/API_GUIDE.md` 6 處 `WFAT`/`WFAT_*` 引用全部改成
  `WLOD`/`WLOD_*`（Fatigue/Load 參考清單區塊改列現行完整 16 個真實 tag；4 處範例
  程式碼改用 `WLOD_TwrFaMom`；code review 抓到的第 5 處第 69 行 subsystem
  breakdown table 殘留列，已用 follow-up commit 修復）。
- **本 session 額外發現並登記新 issue**：`docs/API_GUIDE.md` SCADA Tag System
  章節整張 tag 總數/subsystem breakdown 表過時（109 vs 74，缺 WCOL/WDRV），開
  **WMOM-20260927-06**（open，估時 0.5-1 天，需劉老師或未來 session 認領——本次
  不展開，超出「改名」範圍）。
- **已知限制**：純文件修改，無自動化測試保護；code-reviewer subagent review 為
  背景非同步任務，本次收尾時尚未回報，must-fix 是以獨立 follow-up commit 補上
  同一 PR（而非另開一輪 review）。
- ISSUES.md：`WMOM-20260927-05` → done（含完整 completion summary，含 review
  結果）；新增 `WMOM-20260927-06`（open）；統計表 open 8→7（-05 done）→8（+06
  open）、done 113→114、total 123→124。
- STATUS.yaml：`last_updated`/`issue_stats` 已同步。
- TODO.md：已同步本次完成摘要 + 下個 session 建議。
- 下個 session 可從 `WMOM-20260927-06`（本文件 tag 總數全面重新盤點，0.5-1 天）、
  `WMOM-20260505-25~28`（物理強化，逐一看 priority，皆多日工作），或 M6
  critical path 剩餘項（`WMOM-20260509-F6` PostgreSQL row-lock 需 docker、
  HTTPS 部署配置需先定部署目標，皆需劉老師決策）中挑選；其餘 open issue
  （`WMOM-20260504-11`/`WMOM-20260513-01`）皆標 🟡 需劉老師決策/素材，不宜自行開工。
  ⚠ `docs/routines/autonomous-daily-worker-prompt.md` 內文仍停留 v3，已連續多個
  session 提醒，建議劉老師找時間同步 cron trigger 設定內文（v4.1，即本次實際收到
  的 prompt）回 repo。
