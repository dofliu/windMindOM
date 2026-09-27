# 2026-09-27 — WMOM-20260927-06：`docs/API_GUIDE.md` SCADA Tag System 章節 tag 總數/subsystem breakdown 全面重新盤點

## Claim

`ISSUES.md` open issue `WMOM-20260927-06`（`WMOM-20260927-05` code review should-fix
登記），priority low、estimate 0.5-1 工作天、acceptance 明確（文件總數與 breakdown
table 每一列皆與 `scada_registry.py` 實測結果一致，且無遺漏 subsystem）。

Stack-aware 檢查：`mcp__github__list_pull_requests` 回傳空陣列，確認沒有上個 session
留下的未合併 PR（上個 session `WMOM-20260927-05` 的 PR #202 已 auto-merge 進 main）。
M6 critical path 檢查：`WMOM-20260720-04`/`-08`（唯一硬阻塞）與 `WMOM-20260716-06`
（footprint CPU-torch pin）皆已完成；剩下 `WMOM-20260509-F6`（PostgreSQL row-lock，
需 docker）與 HTTPS 部署配置皆需劉老師先決策。情境比較分析 epic（A0-A3/PR C/PR D）
已於前幾個 session 收尾。逐一檢視其餘 7 個 open issue：`WMOM-20260504-11`（多日新
功能設計）、`WMOM-20260505-25~28`（物理強化，皆多日工作，非商業 must-have）、
`WMOM-20260513-01`（等劉老師交接書）皆非單 session 可完工候選。`WMOM-20260927-06`
是本次唯一「單 session 可完工、acceptance 明確」候選——虽然 estimate 寫 0.5-1
工作天，但範圍就是重新核對 14 個 subsystem 的 tag 數量並更新一張表格，實際判斷單
session 可完工。

## Implement

先獨立重新驗證 issue 描述的數字（不照單全收），`grep -oP 'ScadaTag\("\K[A-Za-z0-9]+
(?=_)' scada_registry.py | sort | uniq -c`：

```
30 WVIB   16 WLOD   16 WCNV   14 WMET   10 WROT
 7 WGEN    4 WNAC    3 WYAW    2 WTUR    2 WDRV
 2 WCOL    1 WSRV    1 WGDC    1 MBUS
```

總計 109（`grep -c 'ScadaTag('` 確認一致）。與 issue 描述的每一項數字完全吻合
（WROT 10、WMET 14、WVIB 30、WLOD 16、缺漏的 WCOL/WDRV 各 2）。

逐一讀 `scada_registry.py` 各 subsystem 區塊的 tag 定義（含英文/繁中說明欄位）
確認新描述文字準確，而非只是改數字：

- `docs/API_GUIDE.md` 第 56 行「74 SCADA tags」→「109 SCADA tags」
- 第 58-70 行整張 breakdown table 重寫（14 列，`WSRV`/`MBUS` 從原本合併一列
  拆成各自獨立列，因為兩者是不同 subsystem 代碼，合併寫法本身就不夠精確）：
  - `WROT` 9→10（新增「imbalance force」，對應 `WROT_ImbForce` #72）
  - `WMET` 3→14（原文字只提 wind speed/direction/ambient temp，實際還有
    humidity、wake deficit/meander/deflection/TI、turbulence intensity、
    shear exponent、atmospheric stability、air density、pressure、raw
    anemometer reading，描述文字一併補齊）
  - `WVIB` 20→30（新增 bearing/gear fault frequency `Bpfo`/`Bpfi`/`Gmf` +
    sideband 系列，描述文字補上「bearing/gear fault frequencies + sidebands」）
  - `WLOD` 7→16（`WMOM-20260927-05` 已修正代碼名稱但沿用舊 count；補齊
    production hours/RUL/alarms 描述）
  - 新增 `WCOL`（coolant level & alarm）、`WDRV`（gearbox oil temp/tooth wear）
    兩列——文件先前完全沒提到這兩個 subsystem
- 第 160 行行內註解 `scada = t['scadaTags']  # dict of 74 tag_id -> float`
  同一份文件內另一處相同的過時數字，一併修正為 109（與本 issue「tag 總數過時」
  的 acceptance 精神一致，非擴大範圍——同一個數字、同一份文件）

## Nice-to-have（一併處理）

`modules/monitoring/simulator/physics/turbine_physics.py:1381-1383`
`_get_sensor_config()` 內 `if tag.startswith("WFAT_TwrBs") or
tag.startswith("WFAT_BldRt")` 分支：`grep -rn "WFAT_TwrBs\|WFAT_BldRt"` 全庫
（`modules/` + `tests/` + `frontend/`）確認唯一命中處就是這行本身，`scada_registry.py`
109 個 tag 無一以 `WFAT_` 開頭（`WMOM-20260927-01~05` 系列已確認現行 schema 只產生
`WLOD_*`），確定是永遠打不到的死碼分支。檢查 `modules/monitoring/tests/` 無任何測試
引用 `_get_sensor_config`，移除該分支後重跑 `modules/monitoring/tests/` 全綠
（196 passed），確認移除安全。

## Verify

**誠實揭露**：`docs/API_GUIDE.md` 的修改是純 Markdown 文件，不被任何 pytest/vitest
解析或執行，沒有「改回舊邏輯讓測試 fail」這個概念可驗（不適用 mutation-verify）。
驗證方式僅止於逐一核對 `scada_registry.py` 原始碼定義（見上）+
`grep -oP` 重新統計交叉確認。

`turbine_physics.py` 死碼移除**同樣不適用 mutation-verify**——它本來就沒有測試
覆蓋（`_get_sensor_config` 完全沒被任何 test 直接呼叫），移除前先用全庫 grep
確認該分支永遠不可達（見上），移除後跑 `modules/monitoring/tests/` 確認零 regression，
而非「把它改回來看測試會不會 fail」（沒有測試可以 fail，因為原本就沒被鎖住——
這正是「死碼」的定義）。

- backend 全套：`pytest modules/workflow/tests/ modules/cost/tests/
  modules/reporting/tests/ modules/knowledge/tests/ modules/monitoring/tests/
  modules/auth/tests/ tests/` → **1293 passed, 7 skipped, 1 xfailed**
  （與 session 開工時的 preflight baseline 完全一致，零 regression）
- frontend：本次未動任何前端檔案。開工 preflight 已跑過一次確認 baseline
  （`npx tsc --noEmit` 0 error / `npx vitest run` 1477 passed，70 files /
  `npx vite build` 成功，僅既有 chunk size 警告），改動範圍與前端完全無關，
  不重跑（避免浪費時間重跑一定不變的東西——改動的檔案不在任何前端 import 路徑內）

## Review

`code-reviewer` subagent review 進行中（背景執行）。

## Wrap-up

- 完成 `WMOM-20260927-06`：`docs/API_GUIDE.md` SCADA Tag System 章節總數
  74→109、breakdown table 14 列（原 11 列）全數核實更新，補齊 `WCOL`/`WDRV`
  兩個先前完全遺漏的 subsystem；同檔案第 160 行行內註解過時數字一併修正。
  順手清理 `turbine_physics.py` 內確認永遠打不到的 `WFAT_TwrBs`/`WFAT_BldRt`
  死碼分支（issue 描述的 nice-to-have，非必要但同批處理成本低）。
- **已知限制**：純文件修改無自動化測試保護；死碼移除因原本就無測試覆蓋，
  同樣無法 mutation-verify，改用「全庫 grep 確認不可達」的靜態驗證取代。
- ISSUES.md：`WMOM-20260927-06` → done（待補 completion summary，見下方 code
  review 結果後更新）；統計表同步。
- STATUS.yaml：`last_updated`/`issue_stats` 待同步。
- TODO.md：待同步本次完成摘要。
- 下個 session 可從 `WMOM-20260505-25~28`（物理強化，逐一看 priority，皆多日
  工作）或 M6 critical path 剩餘項（`WMOM-20260509-F6` PostgreSQL row-lock 需
  docker、HTTPS 部署配置需先定部署目標，皆需劉老師決策）中挑選；其餘 open
  issue（`WMOM-20260504-11`/`WMOM-20260513-01`）皆標 🟡 需劉老師決策/素材，
  不宜自行開工。
  ⚠ `docs/routines/autonomous-daily-worker-prompt.md` 內文仍停留 v3（已連續
  多個 session 提醒），建議劉老師找時間同步 cron trigger 設定內文（v4.1，即
  本次實際收到的 prompt）回 repo。
