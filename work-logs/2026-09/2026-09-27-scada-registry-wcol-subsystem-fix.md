# 2026-09-27 — WMOM-20260927-07：`scada_registry.py` 內 `WCOL_*` 兩個 tag 的 `subsystem` 欄位誤植為 `WCNV`

## Claim

`ISSUES.md` open issue `WMOM-20260927-07`（`WMOM-20260927-06` code review
nice-to-have 登記），priority low、estimate 10-15 分鐘、acceptance 明確
（`ScadaRegistry.by_subsystem("WCOL")` 回傳該兩個 tag + 現有測試維持 pass）。

Stack-aware 檢查：`mcp__github__list_pull_requests` 回傳空陣列，確認沒有上個
session 留下的未合併 PR（上個 session `WMOM-20260927-06` 的 PR #203 已
auto-merge 進 main）。逐一檢視其餘 open issue：`WMOM-20260505-25~28`（物理
強化，皆多日工作，非商業 must-have）、`WMOM-20260504-11`（多日新功能設計，
需劉老師決策）、`WMOM-20260513-01`（等劉老師交接書）皆非單 session 可完工
候選。M6 critical path 剩餘項（`WMOM-20260509-F6` PostgreSQL row-lock 需
docker、HTTPS 部署配置需先定部署目標）皆需劉老師先決策，本次無法自行開工。
`WMOM-20260927-07` 是本次唯一「單 session 可完工、acceptance 明確」候選。

## Implement

先讀 `scada_registry.py` 全文確認 issue 描述的 bug：410-414 行
`WCOL_CoolantLvl`/`WCOL_CoolantAlm` 兩個 `ScadaTag(...)` 定義的第三個
positional 參數（`subsystem` 欄位）確實誤寫成 `"WCNV"`，對照 429-433 行
`WDRV_*` 兩個 tag 正確寫成 `"WDRV"` 可見是複製貼上疏漏。

修正：
- 410/413 行 `"WCNV"` → `"WCOL"`
- `ScadaTag` dataclass 上方（24 行）`subsystem` 欄位行內註解列舉補上 `WCOL`、
  `WDRV`

## Verify

**Test-first**：`modules/monitoring/tests/` 內原本沒有任何 `scada_registry.py`
的專屬測試檔案，這個 bug 完全無測試覆蓋（這正是它能存在到現在才被 code
review 發現的原因）。新增
`modules/monitoring/tests/test_scada_registry_subsystem.py`（2 tests）：
- `test_wcol_tags_have_wcol_subsystem`：`SCADA_REGISTRY["WCOL_CoolantLvl"/
  "WCOL_CoolantAlm"].subsystem == "WCOL"`
- `test_by_subsystem_wcol_returns_both_tags`：`by_subsystem("WCOL")` 回傳
  兩個 tag 的 id 集合，且交叉驗證這兩個 id 不出現在 `by_subsystem("WCNV")`
  的結果內（避免只驗證正面案例、漏掉「誤入其他分組」這個實際 bug 症狀）

Import 寫法比照同目錄 `test_rng_seeding_determinism.py` 慣例（`sys.path`
insert `PROJECT_ROOT` + `MONITORING_ROOT`，`from simulator.physics.
scada_registry import SCADA_REGISTRY`）——第一版直接寫
`from modules.monitoring.simulator.physics...` 因為 `physics/__init__.py`
內部用 `from simulator.physics...` 這種假設 `MONITORING_ROOT` 在 sys.path
上的寫法，導致 `ModuleNotFoundError: No module named 'simulator'`，改用
目錄慣例後修正。

**Mutation-verify**：`git checkout -- scada_registry.py` 還原成誤植版本
（保留新測試不動），重跑新測試：兩個 test 皆 fail
（`AssertionError: assert 'WCNV' == 'WCOL'` /
`by_subsystem` 回傳空 set，非預期的兩個 id），確認測試真的鎖住這個 bug、
不是空判斷。還原修正（從備份複製回正確版本）後兩測皆綠。

**Backend 全套**（與 preflight baseline 一致的 7 個路徑）：
`pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/
modules/knowledge/tests/ modules/monitoring/tests/ modules/auth/tests/
tests/` → **1295 passed, 7 skipped, 1 xfailed**（baseline 1293 + 新增 2 個
test，零 regression）。

**Frontend**：本次未動任何前端檔案。開工 preflight 已完整跑過一次確認
baseline（`npm ci` → `npx tsc --noEmit` 0 error / `npx vitest run` 1477
passed，70 files / `npx vite build` 成功，僅既有 chunk size 警告），改動
範圍與前端完全無關，不重跑。

## Review

`code-reviewer` subagent review（非同步背景執行，約 52 秒完成）：
**Approve，0 must-fix，1 should-fix 已修復**：

1. 🟡 **should-fix（已修復）**：reviewer 指出我編輯的 24 行 subsystem 列舉
   註解雖然補上了 `WCOL`/`WDRV`，卻仍漏掉早已存在於 `_TAGS` 的 `WVIB`
   （~20 tags）與 `WLOD`（~17 tags）——這個缺漏不是本次 diff 造成的，但既然
   這行註解本身就是本次編輯目標（「補完整列舉」），應一次補齊而非留半成品。
   已加入 `WVIB`、`WLOD`。

Reviewer 也獨立重新驗證了核心聲稱（非照單全收）：
- 讀完整份 `scada_registry.py`（504 行），逐一核對所有 14 個 subsystem 區塊
  每個 `ScadaTag(...)` 定義的 `subsystem` 欄位與其 id/OPC tag 字首是否一致，
  確認修正後全檔案只有先前這兩個 `WCOL_*` tag 有誤植，無其他遺漏案例。
- 全庫 grep `by_subsystem(...)` 與 `.subsystem` 用法，發現除了
  `ScadaRegistry` 內部分組字典外，還有一個實際呼叫端：
  `modules/monitoring/server/routers/i18n.py` 的
  `GET /api/i18n/tags/registry` 端點會逐 tag 讀取 `.subsystem` 欄位直接
  回傳給前端——**這代表修正前該 API 對 `WCOL_CoolantLvl`/`WCOL_CoolantAlm`
  兩個 tag 會回傳錯誤的 `"WCNV"`，是真實（雖輕微）的 API 正確性 bug，並非
  本 issue 原描述「全庫無任何呼叫端依賴、不影響任何現有行為」那樣完全無
  影響**。本次修正一併糾正了這個 API 回應層級的既有錯誤。
- 獨立重跑新測試確認皆 pass；確認 negative assertion（`WCOL` id 不該出現在
  `by_subsystem("WCNV")` 結果內）具備實際鎖 bug 效力、無 false positive
  風險（讀取的是 production code 用的同一個 `SCADA_REGISTRY` singleton，
  非 mock）。
- import 寫法與同目錄其他測試檔案（`test_legacy_subsystems_rng_seeding.py`、
  `test_farm_registry_is_offshore.py`）慣例一致。

Should-fix 修正後**未重跑 backend/frontend**：純註解文字調整，未涉及任何
被測試涵蓋的邏輯行為（`subsystem` 欄位本身值不變，只是行內註解補字）。

## Wrap-up

- 完成 `WMOM-20260927-07`：`scada_registry.py` 410/413 行 `WCOL_*` 兩個 tag
  的 `subsystem` 欄位 `"WCNV"`→`"WCOL"`；dataclass docstring subsystem 列舉
  補齊 `WCOL`/`WDRV`/`WVIB`/`WLOD`（后二者為 code review should-fix，非本次
  diff 原範圍但同一行同批處理）。新增 regression test（2 tests），
  mutation-verify 確認測試真的鎖住此 bug。
- **修正 issue 原描述的誤判**：本 issue 開單時描述「全庫無任何呼叫端依賴
  `subsystem` 欄位分組，不影響任何現有行為」——code-reviewer subagent 全庫
  grep 後發現這個判斷不準確：`i18n.py` 的 `GET /api/i18n/tags/registry`
  端點確實會把 `.subsystem` 原樣回傳給前端，修正前對這兩個 tag 是錯誤回應。
  已在 ISSUES.md completion summary 誠實記錄這個更正。
- **已知限制**：`i18n.py` 該端點回傳的 `subsystem` 欄位正確性目前無端對端
  測試覆蓋（只驗證了 `ScadaRegistry` 本身的資料正確性，未驗證 API response
  層級），屬於「讀原始碼交叉核對層級的把關，非端對端測試鎖住」。
- ISSUES.md：`WMOM-20260927-07` → done（含完整 completion summary，含 review
  結果與誤判更正）；統計表 open 8→7、done 115→116、total 125 不變。
- STATUS.yaml：`last_updated`/`issue_stats` 已同步。
- TODO.md：已同步本次完成摘要 + 下個 session 建議。
- 下個 session 可從 `WMOM-20260505-25~28`（物理強化，逐一看 priority，皆
  多日工作）或 M6 critical path 剩餘項（`WMOM-20260509-F6` PostgreSQL
  row-lock 需 docker、HTTPS 部署配置需先定部署目標，皆需劉老師決策）中挑選；
  其餘 open issue（`WMOM-20260504-11`/`WMOM-20260513-01`）皆標 🟡 需劉老師
  決策/素材，不宜自行開工。
  ⚠ `docs/routines/autonomous-daily-worker-prompt.md` 內文仍停留 v3（已連續
  多個 session 提醒），建議劉老師找時間同步 cron trigger 設定內文（v4.1，即
  本次實際收到的 prompt）回 repo。
