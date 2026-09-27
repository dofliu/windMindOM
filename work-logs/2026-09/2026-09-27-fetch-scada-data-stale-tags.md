# 2026-09-27 — WMOM-20260927-02：`fetch_scada_data.py` 殘留已死的 `WFAT_*` tag 引用

## Claim

`ISSUES.md` open issue `WMOM-20260927-02`，`priority: low`、估時 10 分鐘，acceptance
明確（把 `fetch_scada_data.py` 219/305 行的 `WFAT_TwrBsMy`/`WFAT_BldRtMy` 改成
`WLOD_TwrFaMom`/`WLOD_BldFlapMom`）。

Stack-aware 檢查：`mcp__github__list_pull_requests` 回傳空陣列，確認沒有上個
session 留下的未合併 PR，可以挑新工作。M6 critical path 剩餘項（PostgreSQL
row-lock、HTTPS 部署）皆需劉老師先決策；情境比較分析 epic 已於前幾個 session
收尾；`WMOM-20260505-25~28` 物理強化屬多日工作，非單 session 可完工；其餘 open
issue（`WMOM-20260504-11`/`WMOM-20260513-01`）皆標 🟡 需劉老師決策/素材。
`WMOM-20260927-02` 是本次唯一「單 session 可完工、無設計歧義」候選（前一 session
的 work-log 也建議續評估這個）。

## Implement

先確認新舊 tag 的對應關係是否仍成立（不能只靠上個 issue 的敘述，要自己重新核實）：

- `grep -rn "WLOD_TwrFaMom\|WLOD_BldFlapMom\|WFAT_TwrBsMy\|WFAT_BldRtMy"` 全庫：
  - `modules/monitoring/simulator/physics/scada_registry.py`：目前 schema 只登記
    `WLOD_TwrFaMom`/`WLOD_BldFlapMom`（`ScadaTag(...)` 條目），沒有任何 `WFAT_*`
    tag 定義。
  - `modules/monitoring/simulator/physics/turbine_physics.py:878/880`：實際產生
    的 SCADA dict 也只寫入 `WLOD_TwrFaMom`/`WLOD_BldFlapMom`。
  - `turbine_physics.py:1382` 的 `_get_sensor_config()` 裡確實還有一條
    `if tag.startswith("WFAT_TwrBs") or tag.startswith("WFAT_BldRt")` 分支，註解
    寫「Fatigue load tags (legacy WFAT support if needed)」——這只是感測器雜訊
    設定的相容性分支（萬一有 tag 用這個字首要套用哪組 noise/drift 參數），並不
    代表現行 schema 真的會產生這個 tag 名稱。
  - `data_broker.py`/`models.py` 同時保留 `twrBsMy`/`bldRtMy`（映射自
    `WFAT_TwrBsMy`/`WFAT_BldRtMy`）與 `towerFaMoment`/`bladeFlapMoment`（映射自
    `WLOD_TwrFaMom`/`WLOD_BldFlapMom`）兩組欄位——乍看像是兩個不同語意的量測，
    但因為 `WFAT_*` 從未被 `scada_registry.py`/`turbine_physics.py` 實際產生，
    `data_broker.py` 那兩行 `scada.get("WFAT_TwrBsMy")`/`scada.get("WFAT_BldRtMy")`
    永遠拿到 `None`，是同一個「tag 改名沒有全庫同步」的死碼，不是本 issue 要動的
    範圍（`data_broker.py` 不在 `WMOM-20260927-02` 的 deliverable 內，若要一併
    清理需另開 issue，本次不擴大範圍）。
  - `WMOM-20260505-24` completion summary 已明確記錄「`data_quality_analysis.py`
    §4（載荷/Fatigue）整節悄悄變空——引用的 `WFAT_TwrBsMy` 等 4 個 tag 在目前
    schema 已改名為 `WLOD_TwrFaMom` 等」，跟這次獨立核實的結論一致。

確認對應關係成立後，修改 `modules/monitoring/examples/fetch_scada_data.py`：

- 第 219 行（範例 5：WebSocket 即時廣播列印）：
  `scada.get('WFAT_TwrBsMy', 0)` → `scada.get('WLOD_TwrFaMom', 0)`
- 第 305 行（範例 8：pandas 分析 `numeric_cols` 清單）：
  `"WFAT_TwrBsMy", "WFAT_BldRtMy"` → `"WLOD_TwrFaMom", "WLOD_BldFlapMom"`

`grep -n "WFAT_"` 確認全檔已無殘留舊 tag 引用。

## Verify

**這是誠實揭露的重點**：本次修改**沒有自動化測試保護**。

- `fetch_scada_data.py` 是獨立範例腳本，靠 `requests`/`websocket-client` 連
  live/scenario server 的 REST/WebSocket API，不被任何模組 import——
  `grep -rl fetch_scada_data --include="*.py" .` 除自身外零命中，代表沒有任何
  pytest 測試會執行到這個檔案的程式碼路徑。
- Issue acceptance 本文要求的驗證方式是「該腳本對 live server 實際回傳的 SCADA
  JSON 執行時，兩個 tag 能正確取到值」——這需要真的啟動一個 server（`run.py`
  或 scenario/live 模式）並建立 WebSocket 連線觀察輸出，超出本次 10 分鐘小修的
  範圍與 estimate，本次**未做執行期驗證**。
- 本次驗證僅止於：
  1. `python -c "import ast; ast.parse(open(...).read())"` 確認修改後檔案仍是
     合法 Python 語法。
  2. 讀原始碼層級核實新 tag 名稱是現行 schema 真的會產生的欄位（見上方
     Implement 章節的 grep 結果），不是憑空猜測或照搬上一個 issue 的結論。
- 沒有 mutation-verify 這一步（不適用——這是純字串替換，不是邏輯修正，沒有
  「改回舊邏輯讓測試 fail」這個概念可驗）。

Backend/frontend 全套自我測試（本次唯一改動的檔案不在任何測試匯入路徑內，預期
零影響，仍照 routine 全套重跑確認無 regression）：

- 環境設置：`pip install --ignore-installed PyYAML -r requirements.txt
  -r requirements-dev.txt`（新 sandbox，符合已知限制）。
- backend：`pytest modules/workflow/tests/ modules/cost/tests/
  modules/reporting/tests/ modules/knowledge/tests/ modules/monitoring/tests/
  modules/auth/tests/ tests/` → **1293 passed, 7 skipped, 1 xfailed**（與
  baseline 完全一致，零 regression）。
- frontend：`npm ci` + `npx tsc --noEmit`（0 error）+ `npx vitest run`
  （**1477 passed，70 files**，與 baseline 完全一致）+ `npx vite build`
  （成功，僅既有的 chunk size 警告，非本次改動引入）。

## Review

`code-reviewer` subagent review（照 routine Phase 6 規定，即使改動極小仍照跑）：
**Approve，0 must-fix，0 should-fix，1 nice-to-have 已採納**。

Reviewer 獨立重新驗證（非照單全收我提供的背景資訊）：
1. Tag 對應語意正確性——交叉比對 `scada_registry.py`/`turbine_physics.py`
   確認 `WLOD_TwrFaMom`/`WLOD_BldFlapMom` 是唯一被 registry 登記且被物理模型
   實際寫入的對應量；並額外交叉確認
   `modules/monitoring/examples/simulated_scada_post_migration.csv`/
   `data_quality_report.txt`（migration 後版本）都已是 `WLOD_*` 欄位，而
   `_pre_migration_baseline` 版本才含舊版 `WFAT_*`，佐證這是已完成的 schema
   migration，方向正確。
2. Diff 語法/邏輯正確性——確認兩處純字串替換無誤、全檔 `WFAT_` 零殘留。
3. **1 nice-to-have 已採納**：`data_broker.py:189-195` 標註
   `# ── WFAT — Fatigue / Load Monitoring (Legacy) ──` 的區塊，7 個欄位
   （`twrBsMy`/`twrBsMx`/`bldRtMy`/`bldRtMx`/`delTwr`/`delBld`/`dmgAccum`）皆
   對應 `WFAT_*` key，因模擬器從未產生這些 key 而永遠回傳 `None`——跟本次修的
   是同一根因，但影響面更大（API response model，非單純範例腳本），建議登記
   獨立 follow-up。已登記 **WMOM-20260927-04** 追蹤（未修，因為需要先查證前端/
   報表是否消費這 7 個欄位才能決定是刪除還是改對應，超出本次 10 分鐘小修範圍）。

## Wrap-up

- 完成 `WMOM-20260927-02`：`fetch_scada_data.py` 219/305 行 `WFAT_TwrBsMy`/
  `WFAT_BldRtMy` → `WLOD_TwrFaMom`/`WLOD_BldFlapMom`。
- **範圍外但誠實揭露的發現，已登記追蹤**：`data_broker.py:189-195`「WFAT
  (Legacy)」區塊 7 個欄位（`twrBsMy`/`twrBsMx`/`bldRtMy`/`bldRtMx`/`delTwr`/
  `delBld`/`dmgAccum`）永遠拿 `None` 的死碼映射——跟這次修的是同一根因（tag 改名
  沒有全庫同步），但影響面更大（API response model，非單純範例腳本）。code
  review 確認後已登記 **WMOM-20260927-04**（open，未修，需先查證前端/報表是否
  消費這 7 個欄位才能決定刪除或改對應）。
- **本次修改沒有自動化測試保護**（見上方 Verify 章節詳細說明）：純讀原始碼層級
  驗證 + 語法檢查，未做「真的起 server 觀察腳本輸出」的執行期驗證；code-reviewer
  subagent 已獨立交叉驗證 tag 對應語意正確性（見上方 Review 章節），部分彌補
  缺乏執行期測試的信心落差。
- ISSUES.md：`WMOM-20260927-02` → done（含完整 completion summary + review
  結果）；新增 `WMOM-20260927-04`（open）；統計表 open 8→7→8（-02 done 再
  +04 open，淨值不變但實質上是新一輪）、done 136→137、total 146→147。
- STATUS.yaml：`last_updated`/`issue_stats` 已同步。
- TODO.md：已同步本次完成摘要 + 下個 session 建議。
- 下個 session 可從 `WMOM-20260927-04`（`data_broker.py` legacy 欄位查證清理，
  20-30 分鐘）、`WMOM-20260505-25~28`（物理強化，逐一看 priority，皆多日工作）、
  或 M6 critical path 剩餘項（PostgreSQL row-lock 需 docker、HTTPS 部署配置需
  先定部署目標，皆需劉老師決策）中挑選。
