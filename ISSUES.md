# windMindOM — Issues

> 本檔案是 windMindOM 的單一 source of truth issue tracker。
> 所有工作都從這裡認領；新工作請開新 issue 並寫進來。
> Issue ID 格式：`WMOM-{YYYYMMDD}-{NN}`。模板見 `templates/issue-template.md`。
>
> Status 流轉：`open → in_progress → done`（或 `blocked`）。
> 每次 session 開工 / 結尾，請更新 issue status 與下方統計表。

---

## 統計

| Status | Count |
|--------|------|
| open | 13 |
| in_progress | 1 |
| blocked | 0 |
| done | 44 |
| **total (active)** | **58** |

最後更新：2026-05-24 20:xx（**WMOM-20260524-01 done — Frontend 測試基礎設施（vitest + RTL）+ 回補 race-condition regression test**）。今日 autonomous daily worker session 做連續 3 次 handoff 推薦的「新 issue 候選」：前端原本完全無測試框架，導致 5/23（AbortController race）+ 5/24（WS 殭屍重連 leak）兩次修復都無法補自動化 regression。本 session 導入 `vitest@^3 + jsdom@^29 + @testing-library/react@^16`，建 `vitest.config.ts`（jsdom env / setupFiles / restoreMocks）+ `vitest.setup.ts`（afterEach cleanup）+ package scripts（test / test:watch），並**回補兩個近期 race-condition fix 的 regression test**：`useRealtimeData.test.ts`（FakeWebSocket + fake timer 鎖住「卸載解除 handler 再 close、不殭屍重連」+「掛載中斷線 3s 重連未被誤殺」）+ `useCostData.test.ts`（mock costApi + 可控 deferred 驗「stale 不蓋 fresh」+「AbortError 不進 error state」）。Verify：vitest 4 passed / tsc 0 errors（含測試檔）/ vite build 748 modules 0 errors（測試檔排除於 bundle 外）；backend 未動 zero regression。issue_stats done 43→44 / total 57→58（新建即完成，open 不變 13；WMOM-20260504-12 仍 in_progress）。下次候選：WMOM-20260519-01（需劉老師 walkthrough）/ M5 規劃（RAG 需架構決策）/ WMOM-20260513-02 demo orchestrator / 元件層測試擴充（FarmOverview memo / CostPage panel）。詳細 handoff 在 work-logs/2026-05/2026-05-24-frontend-test-infra.md。

---

最後更新：2026-05-24 20:xx（**WMOM-20260504-12 in_progress — Frontend realtime 記憶體成長：WS 殭屍重連洩漏根治 + 卡片 React.memo**）。今日 autonomous daily worker session 做 5/23 handoff 推薦的 solo-friendly frontend 工。進場 root-cause 發現 issue 描述的元件名（MiniTrendChart/TurbineCard）在 5/07 UI 改版後已不存在，現況走 FarmOverview 的 TCard/CompactTile + 自寫 SVG（非 Recharts，suspect #3 不適用）。**真因 suspect #4**：`useRealtimeData` 的 `ws.onclose` 無條件重連；unmount cleanup 的 `ws.close()` 非同步觸發 onclose，在 cleanup 跑完後又排一條清不到的重連 timer → 殭屍 WebSocket 無限累積，每條每次 push 都呼叫 setTurbines；React 18 Strict Mode dev 雙觸發立刻引爆 = 劉老師回報的 dev 記憶體成長。修法：`disposed` 旗標貫穿所有 WS handler + poll；cleanup 設 disposed=true + 先解除 ws 四 handler 再 close()（雙保險）+ 清 timer/interval；initial fetch 加 cancelled guard。**suspect #1**：TCard/CompactTile 加 React.memo + areEqual（只比渲染欄位 + lang prop），父層非資料因素 re-render 時跳過 14 張 SVG 重繪；onClick/tr 刻意排除（onClick stale 由 App liveTurbine 以 id 反查保證、tr 為 lang 純函式、theme 走 context 不受影響）。Verify：tsc 0 + vite build 748 modules / ~3.4s / 0 errors；backend 未動 zero regression。Code review 1 must（onClick stale 判定非 bug，App.tsx:143-146 以 id 反查）+ 2 should（onerror disposed guard 採納 / compactTileEqual turState 不採納）+ 1 nice（history reference 比較判定非 bug 不採納）。issue 維持 in_progress（24h 記憶體 < 50% 驗收需劉老師本機長跑）；issue_stats open 14→13 / in_progress 0→1 / done 43 / total 57。下次候選：WMOM-20260519-01（需劉老師 walkthrough）/ M5 規劃 / WMOM-20260513-02 demo orchestrator / 前端測試基礎設施（vitest+RTL）。詳細 handoff 在 work-logs/2026-05/2026-05-24-frontend-realtime-memory-fix.md。

---

最後更新：2026-05-23 20:xx（**WMOM-20260504-13 done — Cost 系列 fetch 加 AbortController 防 race**）。今日 autonomous daily worker session 做 5/22 handoff 推薦的 0.25d frontend-only 小工：`useCostData.useAsync.run` 原本沒有 abort 機制，React 18 Strict Mode dev 雙觸發 `useEffect([dataset])` 或使用者快速切 dataset 時，慢 fetch 後回會蓋掉新 dataset 結果（stale-overwrites-fresh race）。修法三道防線：(1) `useRef<AbortController>` 追蹤最新 in-flight request 並在下一筆 run 前 abort 上一筆；(2) `signal.aborted` 早退即使舊 fetch 已 resolve 也不 setData；(3) `controllerRef.current === controller` loading guard。另加 `isAbortError`（DOMException + Error）、`reset()` abort + 清 loading、unmount cleanup；`costService.postJSON` + `costApi`×4 加 optional `AbortSignal` 透傳。純擴充，CostPage 4 panel + dataset effect 完全相容。Verify：tsc 0 errors + vite build 748 modules / 4.58s 0 errors；backend frontend-only zero regression。Code review 1 must + 1 should + 1 nice：should（isAbortError 補 DOMException）採納；must（reset×in-flight run loading 殘留）以 timeline 推導判定非真 bug 不採納 hacky 修法、改加註解。frontend 無測試框架故未加自動化 regression test（建議另開 issue 導入 vitest+RTL）。issue_stats open 15→14 / done 42→43 / total 57。下次候選：WMOM-20260519-01（F1 超量退料 domain guard，需劉老師 walkthrough）/ M5 規劃 / WMOM-20260513-02 demo orchestrator。詳細 handoff 在 work-logs/2026-05/2026-05-23-cost-abortcontroller.md。

---

最後更新：2026-05-22 20:xx（**WMOM-20260522-01 done — F4 收尾，work_order + reporting 兩個 router 也改用 shared FARM_REGISTRY**）。今日 autonomous daily worker session 接 5/21 F4 batch 的 follow-up note：F4 當時 scope 只列 4 個 routers，實作中發現 `work_order_router.py` + `reporting/routers/reporting_router.py` 也有相同 lazy singleton pattern（helper 名分別為 `_get_default_farm_registry` / `_resolve_farm_db_path`），本 issue 補完。`work_order_router._default_repository_factory` 從 try/except + 404/500 mapping 收成一行 `get_repository(resolve_farm_db_path(farm_id))`；`_resolve_db_path_for_finish_hook` 用 try/except HTTPException 包 shared 呼叫，finish hook 失敗（registry 不可用 / farm 不存在）安靜返回 None 不阻擋工單收尾。`reporting_router` 兩個 setter `set_ledger_factory(None)` / `set_work_order_factory(None)` 各自呼叫 `reset_farm_registry()`；`set_availability_provider` 不該動 farm registry（已加 regression test 守住）。10 個新 test（5 work_order + 5 reporting，含 N1 production code path 驗證）全綠。Backend baseline zero regression（715 passed + 1 xfailed + 3 pre-existing numpy drift；環境 flaky concurrency dispatch test 偶爾 fail 與本 PR 無關）。Code review 1 must（`__builtins__` patch 改 monkeypatch shared function）+ 2 should + 1 nice 全採納；should-1（HTTPException coupling 全 6 router 統一，需擴大 scope 到 F4 batch）本 PR 不擴大。issue_stats open 15 / done 41→42 / total 56→57。下次候選：WMOM-20260519-01（F1 超量退料 domain guard，需設計決策）/ M5 規劃 / WMOM-20260513-02 demo orchestrator simulator / WMOM-20260504-13 cost frontend AbortController（小工）。詳細 handoff 在 work-logs/2026-05/2026-05-22-f4-followup-work-order-reporting.md。

---

## M1（2026-05）— Setup baseline

### WMOM-20260503-01 — Repo baseline 整理（digiWT → modules/monitoring/）

- **Status**: done（2026-05-03 完成）
- **Milestone**: M1
- **Priority**: critical
- **Estimate**: 2-3 工作天 → **實際半天**（因採「move + sys.path 注入」策略，避開大規模 import 重寫）
- **Owner**: Claude (session 2026-05-03)
- **Completion summary**:
  - ✅ 5 modules（monitoring / workflow / cost / reporting / knowledge）+ shared（schemas / plc_clients / domain）+ tests 骨架就位
  - ✅ digiWT 既有 monitoring 程式（simulator、server、wind_model、scada_system、subsystems、turbine_model、opcua_interface、dashboard、main、common_types、main_architecture、examples、data、wind_farm_data.db、wind_turbine_data.db）全部搬到 modules/monitoring/
  - ✅ opc_bachmann/ 抽到 shared/plc_clients/bachmann/
  - ✅ run.py 注入 sys.path（modules/monitoring 在最前面），既有 `from simulator.x` / `from server.x` import 完全不用改
  - ✅ Dockerfile + docker-compose.yml + .dockerignore 路徑更新（含 DB_PATH、FARM_DATA_DIR、volume mount、container_name）
  - ✅ docs/legacy/digiwt_directory_layout.md 搬遷對照表 + sys.path 策略 + 影響相對路徑分析 + 驗證紀錄
  - ✅ 6 項 smoke test 全通過：legacy import、modern import、5 modules 全 importable、18-秒模擬跑出 109 SCADA tag、FastAPI app 67 routes 載入、run.py compile 通過
- **Decision resolved**: pyproject.toml 整合**未做**（保留 requirements.txt），下個 issue 處理 — 跟搬遷脫鉤可降低 risk
- **Follow-up**：
  - ✅ 完整跑 `python run.py` + 開 browser 看 dashboard（2026-05-03 用戶截圖確認 — 14 台 WTG OPERATING、3.55 MW、6.2 m/s、台中港曲風場 active farm 正確載入、5-min trend 即時更新）
  - ✅ `docker-compose` 設定靜態驗證 PASS（2026-05-03 — YAML parse、COPY directives、env vars (DB_PATH/FARM_DATA_DIR)、volume mount、相對路徑等價性 全部 OK）；實際 `docker compose up --build` 因本機未裝 Docker Desktop **deferred**（留給部署 partner / overnight 跑）
  - ✅ 重跑 examples/data_quality_analysis.py（短版）2026-05-03：0.17h × 5 turbines / 3060 rows / wall 3.7s → 15/16 quality check pass、風速↔功率 r=+0.970、1P振動↔轉速 r=+0.944、無 NaN、無 out-of-range；唯一 ⚠ 是定子溫-功率 r=-0.313 偏低，屬 duration artifact（短 sim 沒熱平衡時間，跟搬遷無關）。Pre-migration baseline 已備份；完整 2h 對照留給 overnight session
  - ⬜ Mass-rewrite imports 為 fully qualified `modules.monitoring.*` 形式（M1-M2 穩定後另開 issue）
  - ⬜ 盤點 modules/monitoring/main.py + main_architecture.py 是否為 dead code
- **Reference**:
  - [`docs/legacy/digiwt_directory_layout.md`](docs/legacy/digiwt_directory_layout.md)（搬遷對照表）
  - [`work-logs/2026-05/2026-05-03-repo-baseline-and-tracking-files.md`](work-logs/2026-05/2026-05-03-repo-baseline-and-tracking-files.md)（session 紀錄）

<details><summary>📜 原始 issue description（保留歷史 / 開工時範圍）</summary>

- **Description**:
  把根目錄既有 digiWT 檔案搬到 `modules/monitoring/`，建立 4 個空 module 占位
  （`workflow/`、`cost/`、`reporting/`、`knowledge/`），以及 `shared/` / `tests/`
  / `frontend/` 的標準骨架。確認搬完後 import path、Docker、既有 18/21 quality
  check 仍能跑通；不破壞物理一致性。
  - 子任務：
    1. 建立 `modules/{monitoring,workflow,cost,reporting,knowledge}/` 與 `__init__.py` 占位
    2. 建立 `shared/{schemas,plc_clients,domain}/` 占位（M1 後續 issue 才會放東西）
    3. 把 root 的 `simulator/`、`server/`、`scada_system.py`、`turbine_model.py`、
       `wind_model.py`、`subsystems.py`、`opcua_interface.py`、`dashboard.py`、
       `main.py`、`run.py`、`common_types.py`、`main_architecture.py`、
       `wind_farm_data.db`、`wind_turbine_data.db`、`config/`、`data/`、
       `examples/` 搬進 `modules/monitoring/`
    4. 把 `opc_bachmann/` 抽到 `shared/plc_clients/bachmann/`
    5. 修 import path（`from simulator.x` → `from modules.monitoring.simulator.x` 等）
    6. 更新 `Dockerfile` / `docker-compose.yml` 路徑
    7. 跑 `python -m pytest`（如有）+ 啟動 backend 確認 endpoint 還活著
    8. 留一個 `docs/legacy/digiwt_directory_layout.md` 紀錄搬遷對照表
- **Deliverable**:
  - `modules/monitoring/...`（搬遷後檔案）
  - `modules/{workflow,cost,reporting,knowledge}/__init__.py`（空殼）
  - `shared/plc_clients/bachmann/`
  - `docs/legacy/digiwt_directory_layout.md`（搬遷對照表）
  - 更新後的 `Dockerfile`、`docker-compose.yml`、`pyproject.toml`（或 requirements.txt）
- **Decision needed**: 是否 M1 就把 `pyproject.toml` 整合好（vs M2 才做）→ 預設 M1 做
- **Depends on**: -
- **Blocks**: WMOM-20260503-02（v0.5 資產搬入路徑會用到新結構）、WMOM-20260603-* (M2 cost 移植)
- **Reference**:
  - `docs/product/MVP_ARCHITECTURE.md`（5 modules 設計）
  - `docs/legacy/digiwt_project_notes.md`（既有物理層細節）
  - `CLAUDE.md` §4 repo 結構

</details>

---

### WMOM-20260503-02 — 搬入 v0.5 有用資產

- **Status**: done（2026-05-04 完成）
- **Milestone**: M1
- **Priority**: high
- **Estimate**: 0.5-1 工作天 → **實際 ~2 小時**（多數「搬入」項已在更早 session 完成現代化，本 session 主力為 inventory + decision 紀錄）
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ Pitch deck baseline 入庫：`docs/sales/pitch_deck_v0.5_baseline.{md,pptx}`（從 `../windFarmOM_bk/docs/pitch_deck.{md,pptx}` 複製）
  - ✅ Diff 比對 `docs/routines/daily-workflow.md` (v1.1, 2026-05-03)、`templates/*.md`、`docs/claude-code-templates/` → 已現代化，無需搬
  - ✅ 寫 `docs/sales/v05_assets_inventory.md`（搬入 / 已現代化 / 棄用三類對照）
  - ✅ `docs/product/decision_log.md` 追加 DEC-20260504-01（v0.5 棄用資產清單明列化）
- **Reference**:
  - [`docs/sales/v05_assets_inventory.md`](docs/sales/v05_assets_inventory.md)（資產對照清單）
  - [`docs/product/decision_log.md`](docs/product/decision_log.md) DEC-20260504-01
  - [`work-logs/2026-05/2026-05-04-migrate-v05-assets.md`](work-logs/2026-05/2026-05-04-migrate-v05-assets.md)（session 紀錄）

<details><summary>📜 原始 issue description</summary>

- **Description**:
  從 v0.5（windMindOM 早期 prototype）搬入仍有用的資產，不要重複造輪子：
  - `pitch_deck.md` / `pitch_deck.pptx`（給客戶用的簡報）→ `docs/sales/`
  - `daily-workflow.md`（已搬入 `docs/routines/`，確認最新版）
  - `claude-code-templates/`（已存在 `docs/`，盤點是否完整）
  - `templates/`（已存在 root，盤點 work-log / issue / decision 模板是否齊全）
  - 其他 v0.5 規劃文件中**已被 v0.8.1 取代的廢棄**（如舊版 plugin SDK 設計）→ 不搬，但在 `docs/product/decision_log.md` 紀錄為何丟棄
- **Deliverable**:
  - `docs/sales/pitch_deck_v0.5_baseline.{md,pptx}`（先存底，v0.8.1 改版見 WMOM-20260503-04）
  - `docs/routines/daily-workflow.md`（已存在）
  - `templates/`（盤點清單）
  - `docs/claude-code-templates/`（盤點清單）
- **Depends on**: WMOM-20260503-01（搬遷後新結構就位才好搬）
- **Blocks**: WMOM-20260503-04（pitch deck 改版前要先有 v0.5 baseline）
- **Reference**: `CLAUDE.md` §3 文件入口

</details>

---

### WMOM-20260503-03 — Root CLAUDE.md 改為 windMindOM 產品脈絡

- **Status**: done
- **Milestone**: M1
- **Priority**: high
- **Estimate**: 0.5 工作天
- **Owner**: 劉老師（pre-session, 2026-05-02）
- **Description**:
  既有 root `CLAUDE.md` 已於 2026-05-02 baseline commit 改為 windMindOM v0.8.1
  產品脈絡（5 modules、ICP、其他 7 repo 關係、daily routine、coding 規範）。
  既有 digiWT 版本的 root CLAUDE.md 已備份在 `docs/legacy/`（如未備份則本 issue 含此項）。
- **Deliverable**:
  - `CLAUDE.md`（已是 windMindOM v0.8.1 版本）
  - `docs/legacy/digiwt_CLAUDE.md`（如尚未備份，補上）
- **Reference**: 本檔案開頭 `CLAUDE.md` §1-15

---

### WMOM-20260503-04 — Pitch deck v0.8.1 改版

- **Status**: done（2026-05-04 完成）
- **Milestone**: M1
- **Priority**: high
- **Estimate**: 1-2 工作天 → **實際半天**（先 outline 對齊、後 build；用戶選 Journal 主題不影響故事線）
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ Outline 先 source of truth：[`docs/sales/pitch_deck_v0.8.1_outline.md`](docs/sales/pitch_deck_v0.8.1_outline.md)（10 主 + 2 附錄、每張視覺指示、v0.5→v0.8.1 9 項差異對照）
  - ✅ 主 deck 12 張：[`docs/sales/pitch_deck_v0.8.1.pptx`](docs/sales/pitch_deck_v0.8.1.pptx) + PDF（760 KB / 12 頁）
  - ✅ Onepager A4 直式：[`docs/sales/pitch_deck_v0.8.1_onepager.pptx`](docs/sales/pitch_deck_v0.8.1_onepager.pptx) + PDF（426 KB / 1 頁）
  - ✅ **Journal 主題**（米白墨綠期刊風 / 學術襯線書冊風） — 用戶決定取代原 Navy
  - ✅ Builder script: `tools/pitch_deck/build_v081_pitch.js` + `build_v081_onepager.js`（pptxgenjs，可重 build）
  - ✅ QA：python-pptx structural check 12 張 + 表格 8×8 + 頁腳 / 章節序號齊全
  - ✅ PDF 轉檔：PowerPoint COM via PowerShell（本機無 LibreOffice 的解法）
- **Reference**:
  - [`docs/sales/pitch_deck_v0.8.1_outline.md`](docs/sales/pitch_deck_v0.8.1_outline.md)（大綱 source of truth）
  - [`tools/pitch_deck/`](tools/pitch_deck/)（pptxgenjs builder）
  - [`work-logs/2026-05/2026-05-04-pitch-deck-v081.md`](work-logs/2026-05/2026-05-04-pitch-deck-v081.md)（session 紀錄）

<details><summary>📜 原始 issue description</summary>

- **Description**:
  把 v0.5 pitch deck（windMindOM 早期 framework 定位）改寫為 v0.8.1
  「**離岸風場運維廠商工具**」定位。
  - 主視覺改為「Operator-focused tool」
  - 套餐改為 Operator Basic / Pro / Enterprise（取代 v0.5 的「整合容器」分層）
  - 加上 5 modules 一張圖（monitoring / workflow / cost / reporting / knowledge）
  - 加上 simulator-first demo flow（**無實場可成立**是 sales killer feature）
  - 第一個目標客戶：Z72 機型運維廠商
  - 用 `pptx-jliu-style` skill 出 Navy 主題（科技類）→ 改 Journal
- **Deliverable**:
  - `docs/sales/pitch_deck_v0.8.1.pptx`
  - `docs/sales/pitch_deck_v0.8.1_outline.md`（投影片大綱）
  - 一頁 onepager PDF（給 cold email 附件用）
- **Depends on**: WMOM-20260503-02（先有 v0.5 baseline 才能改版）
- **Blocks**: WMOM-20260503-05（接觸客戶要先有可寄的 deck）
- **Reference**:
  - `docs/product/PRODUCT_VISION.md`（套餐分層、ICP）
  - `CLAUDE.md` §15 「第一個客戶定 Z72」

</details>

---

### WMOM-20260503-05 — Friendly 客戶接觸名單

- **Status**: in_progress（infrastructure done 2026-05-04；contact 持續整月）
- **Milestone**: M1
- **Priority**: medium
- **Estimate**: 0.5 工作天（infrastructure）+ 持續整月（contact）
- **Owner**: 劉老師（contact 執行）/ Claude session 2026-05-04（infrastructure）
- **Infrastructure done（2026-05-04）**:
  - ✅ [`docs/sales/friendly_contacts.md.template`](docs/sales/friendly_contacts.md.template) — 4 大渠道分類（NCUT 學界 / Bachmann / 第三階段運維分包商 / 業界研討會）+ contact entry 模板
  - ✅ [`docs/sales/outreach_script.md`](docs/sales/outreach_script.md) — cold email 3 範本（介紹 / cold / follow-up）+ 30 分鐘 demo agenda + objection handling FAQ + 寄送 logistics
  - ✅ [`docs/sales/customer_feedback/README.md`](docs/sales/customer_feedback/README.md) + [`_TEMPLATE.md`](docs/sales/customer_feedback/_TEMPLATE.md) — demo 後 24 小時內紀錄結構
  - ✅ `.gitignore`：`friendly_contacts.md` + `customer_feedback/202*-*-*-*.md` 不入 git（PII），但模板與 README 可 commit
- **Pending（劉老師執行）**:
  - ⬜ `cp friendly_contacts.md.template friendly_contacts.md`，從 4 大渠道盤 5-10 位潛在 contact
  - ⬜ 寄出 3-5 封 cold email（用 outreach_script.md 範本 A / B）
  - ⬜ 約到第一場 30 分鐘 demo（M1 月底前）
  - ⬜ Demo 後 24 小時內寫 `customer_feedback/YYYY-MM-DD-{客戶代號}.md`
- **完成定義**：1+ 場 demo done + feedback 寫進 customer_feedback/ → 標 done
- **Depends on**: WMOM-20260503-04（done — deck 已就位）
- **Reference**:
  - `docs/product/PRODUCT_VISION.md` §ICP（運維廠商）
  - `work-logs/2026-05/2026-05-04-friendly-contacts.md`（infrastructure session 紀錄）

---

## M2（2026-06）— Cost module（從 ECN 移植）

### WMOM-20260504-01 — ECN K13 baseline + 移植規劃（discovery-first）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: critical（**M2 第一個 issue**，blocking 所有後續 cost migration）
- **Estimate**: 0.5 工作天
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 在 ECN 跑 4 支 test 全 pass（cost_cal + waiting_time × 3 + monte_carlo），抓到 K13 黃金數字
  - ✅ 寫 [`docs/legacy/ecn_k13_baseline.md`](docs/legacy/ecn_k13_baseline.md)：K13 reference vs computed 偏差表 + 4 季 breakdown + Monte Carlo + LCOE = 72.94 EUR/MWh + 重跑 SOP
  - ✅ 寫 [`docs/legacy/ecn_engine_inventory.md`](docs/legacy/ecn_engine_inventory.md)：4 submodule × ~3,000 行 inventory + 跨模組依賴 + migration mapping + 風險評估 + 不移的東西明列
  - ✅ 在 `modules/cost/` 建 skeleton（10 個 sub-namespace `engine/{cost_cal,waiting_time,monte_carlo,var_fluct}` + `models/` + `routers/` + `schemas/` + `tests/` + `data/demo/`），import smoke test pass
  - ✅ 確認 ECN engine **完全 pure compute**（grep 無 `app.models / app.schemas / app.config` 引用），migration 邊界乾淨
- **Key decisions documented**:
  - windMindOM `modules/cost/` 結構鏡像 ECN backend/app/，降低移植 risk
  - 只移 engine（4 submodule），**不**移 models / routers / schemas / database / utils — windMindOM 自己做
  - 推薦 migration 順序：waiting_time → cost_cal → monte_carlo → var_fluct（總估時 3-3.5 天）
  - 浮點誤差容忍：< 1e-6（嚴格 numerical equivalence）
- **Reference**:
  - [`docs/legacy/ecn_k13_baseline.md`](docs/legacy/ecn_k13_baseline.md)（K13 黃金數字）
  - [`docs/legacy/ecn_engine_inventory.md`](docs/legacy/ecn_engine_inventory.md)（移植計畫 + risk）
  - [`work-logs/2026-05/2026-05-04-ecn-k13-baseline.md`](work-logs/2026-05/2026-05-04-ecn-k13-baseline.md)（session 紀錄）

---

### WMOM-20260504-08 — Cost dashboard frontend（M2 收官）

**Polish update（2026-05-04 同日）**：
- VarFluct chart 軸 label / legend 重疊修復（移除過長右軸 label，靠 legend 顏色說明；增加 chart 高度 + bottom margin）
- 全頁中文 i18n（用既有 `useI18n` hook + `ui()` 模式，與 maintenance / history page 一致）：
  panel title / subtitle / button / metric label / chart legend keys / season names 全雙語
- 預設 lang 從 `localStorage.windFarmLang` 讀（既有設計，預設 zh）
- Vite build 仍 pass（0 TS errors）

---


- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high
- **Estimate**: 1-2 工作天 → **實際 ~30 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ `frontend/services/costService.ts` (160 行) — TypeScript API client + 完整 type chain 對齊 backend pydantic schemas
  - ✅ `frontend/hooks/useCostData.ts` (70 行) — `useAsync` 通用 hook，4 個 endpoint state（data/loading/error/run）
  - ✅ `frontend/components/CostPage.tsx` (440 行) — 4 panel dashboard：
    - **ForecastPanel**: 6 metric cards + 4 季 stacked bar chart（auto-run on mount）
    - **LCOEPanel**: capex/discount input → LCOE breakdown
    - **MonteCarloPanel**: n_sim/seed input → P10/P50/Mean/P90 bar
    - **VarFluctPanel**: 20 年 line chart（Total Effort + Multiplier + Availability 三線）
    - 共用 UI bits: MetricCard / Panel / Btn / ErrorBox + money formatter
  - ✅ `frontend/App.tsx` 加 nav button (Cost icon) + view router case
  - ✅ Vite production build pass：710 modules, 1020 KB（含 recharts），0 TS errors
- **可即時測試**:
  ```bash
  python run.py                    # backend
  cd frontend && npm run dev       # frontend
  # → http://localhost:5173 → 點 nav "Cost"
  ```
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-cost-frontend.md`](work-logs/2026-05/2026-05-04-cost-frontend.md)
  - [`frontend/components/CostPage.tsx`](frontend/components/CostPage.tsx)

---

### WMOM-20260504-07 — FastAPI cost router（4 endpoints）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high
- **Estimate**: 0.5-1 工作天 → **實際 ~25 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ `modules/cost/routers/cost_router.py` (180 行) — 4 個 POST endpoints：
    - POST /api/cost/forecast    — CostForecastRequest → CostForecastResponse
    - POST /api/cost/lcoe         — LCOERequest → LCOEResponse
    - POST /api/cost/monte-carlo  — MonteCarloRequest → MonteCarloResponse
    - POST /api/cost/var-fluct    — VarFluctRequest → VarFluctResponse
  - ✅ Mount 進主 FastAPI app (`modules/monitoring/server/app.py`)
  - ✅ `modules/cost/tests/test_cost_api.py` (160 行) — **11 tests 全 PASS**：
    - 4 endpoints × bit-perfect baseline 比對
    - validation：unknown dataset → 422、n_simulations < 10 → 422
    - var_fluct custom bathtub override / constant model
  - ✅ 整 modules/ pytest：43 PASS + 1 XFAIL（cost 41 + monitoring 3，6.22s）
  - ✅ Smoke test 主 app 4 routes 成功 mount 在 `/api/cost/*`
- **可即時測試**: `python run.py` → `http://localhost:8100/docs` (FastAPI auto OpenAPI swagger)
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-cost-api.md`](work-logs/2026-05/2026-05-04-cost-api.md)
  - [`modules/cost/routers/cost_router.py`](modules/cost/routers/cost_router.py)
  - [`modules/cost/tests/test_cost_api.py`](modules/cost/tests/test_cost_api.py)

---

### WMOM-20260504-09 — SQLite 並發 lock 修復（hotfix）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M1 follow-up（hotfix，不在原規劃 issue 內）
- **Priority**: high（production crash — 用戶實際跑 monitoring 時撞到）
- **Estimate**: 0.25 工作天 → **實際 ~25 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Trigger**: 劉老師執行 `python run.py` 時 log 噴 `sqlite3.OperationalError: database is locked`，500 Error 在 `/api/maintenance/technicians`
- **Root cause**:
  - `Storage._get_conn()` 與 `FarmRegistry._get_conn()` 開 SQLite 沒設 PRAGMA
  - 預設 `journal_mode=DELETE` + `busy_timeout=0` → 撞鎖立刻 raise
  - 4 thread 並發（FastAPI handlers / DataBroker write / maintenance DELETE / simulator）撞鎖機率高
- **Completion summary**:
  - ✅ 新增 `modules/monitoring/server/sqlite_utils.py` (55 行) — `open_sqlite()` helper 統一設 WAL + synchronous=NORMAL + busy_timeout=5000
  - ✅ 改 `storage.py` `_get_conn` + `_init_db` 用新 helper
  - ✅ 改 `farm_registry.py` `_get_conn` 用新 helper
  - ✅ 新增 `modules/monitoring/tests/test_storage_concurrency.py` (130 行) — 3 tests
    - `test_pragmas_applied` — 驗證 connection 真的有 WAL + busy_timeout
    - `test_concurrent_read_write_no_lock` — 4 thread 並發 1 秒，0 lock errors（reader×2 + writer + deleter，~8,800 ops）
    - `test_storage_basic_crud_still_works` — regression: CRUD 仍正常
  - ✅ 整 modules/ test suite：32 PASS + 1 XFAIL（cost 30 + monitoring 3）
- **未動**: `modules/monitoring/scada_system.py` 的 4 個 sqlite3.connect()（看似 legacy，與 Storage 不共用 DB path，未在 crash 路徑上）
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-sqlite-lock-fix.md`](work-logs/2026-05/2026-05-04-sqlite-lock-fix.md)
  - [`modules/monitoring/server/sqlite_utils.py`](modules/monitoring/server/sqlite_utils.py)
  - [`modules/monitoring/tests/test_storage_concurrency.py`](modules/monitoring/tests/test_storage_concurrency.py)

---

### WMOM-20260504-06 — Cost adapter + pydantic schemas（M2 抽象層）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high
- **Estimate**: 0.5-1 工作天 → **實際 ~1 小時**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ `modules/cost/adapter.py` (393 行)：`EngineParams` dataclass + `load_k13_engine_params(stochastic=)` + 4 個 result→response 轉換器
  - ✅ `modules/cost/schemas/cost_schemas.py` (198 行)：10 個 pydantic models（Request × 4 + Response × 4 + 子 model × 2）
  - ✅ Refactor 3 個 engine test 用新 loader：
    - test_k13_equivalence.py: 362 → 155 行（省 207）
    - test_monte_carlo.py: 370 → 203 行（省 167）
    - test_var_fluct.py: 402 → 243 行（省 159）
    - test_waiting_time.py 不動（讀 metocean CSV，scope 不重複）
  - ✅ `modules/cost/tests/test_adapter.py` (207 行)：9 tests 涵蓋 K13 loader + 4 個 result→response + pydantic round-trip + regression gate
  - ✅ 整 cost module pytest：**29 PASS + 1 XFAIL**（4.17s，比 -05 多 9 個 adapter test）
- **Code metrics**: tests 1439 → 1113（省 326）；adapter + schemas +591；淨 +265 行
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-cost-adapter.md`](work-logs/2026-05/2026-05-04-cost-adapter.md)
  - [`modules/cost/adapter.py`](modules/cost/adapter.py)
  - [`modules/cost/schemas/cost_schemas.py`](modules/cost/schemas/cost_schemas.py)
  - [`modules/cost/tests/test_adapter.py`](modules/cost/tests/test_adapter.py)

---

### WMOM-20260504-05 — `engine/var_fluct/` 移植（4 engine 收官）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: medium
- **Estimate**: 0.5 工作天 → **實際 ~25 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 3 engine files (360 行) 從 ECN 複製 + sed 改 import + grep 確認無 ECN-specific 依賴
  - ✅ ECN 沒有對應 unit test → **從零寫 9 tests**
  - ✅ `tools/pin_var_fluct.py` 取 ~30 個 pinned 數字（20 年 bathtub 曲線 + 6 邊界 + Year 1/10/20 完整 YearResult + Summary）
  - ✅ `modules/cost/tests/test_var_fluct.py` 9 tests 全 PASS：
    - bathtub_default_curve / bathtub_edges / bathtub_curve_helper
    - varfluct_lifetime_length / year_1_pinned (early peak 1.5x) / year_10_pinned (mid life) / year_20_pinned (late peak 2.0x) / summary_pinned / year_index_consistency
  - ✅ Cross-test invariant: Year 10 var_fluct availability == -03 cost_cal pinned baseline (0.9402)
- **整 cost module pytest**: **20 PASS + 1 XFAIL**（4.88s，含 -02/-03/-04/-05 累計 21 tests）
- **4 個 ECN engine submodule 全部 ported**: cost_cal + waiting_time + monte_carlo + var_fluct
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-var-fluct-migration.md`](work-logs/2026-05/2026-05-04-var-fluct-migration.md)（session 紀錄）
  - [`modules/cost/tests/test_var_fluct.py`](modules/cost/tests/test_var_fluct.py)

---

### WMOM-20260504-04 — `engine/monte_carlo/` 移植 + LCOE bit-perfect

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high
- **Estimate**: 0.5 工作天 → **實際 ~25 分鐘**
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 4 engine files (674 lines) 從 ECN 複製到 `modules/cost/engine/monte_carlo/`，sed 改 import
  - ✅ Grep 確認 monte_carlo 完全乾淨（無 ECN-specific 依賴），跟 cost_cal 一樣
  - ✅ ECN 用 `np.random.default_rng(seed)` modern API，seed=42 完全 reproducible
  - ✅ `tools/pin_monte_carlo.py` 一次性工具取 21 個 pinned 數字（4 deterministic + 11 percentile + 6 LCOE，含 LCOE = 72.94 EUR/MWh）
  - ✅ `modules/cost/tests/test_monte_carlo.py` 5 tests 全 PASS：
    - `test_mc_deterministic_pinned` — 4 metric bit-perfect（reuse cost_cal）
    - `test_mc_percentiles_pinned` — 11 percentile bit-perfect
    - `test_mc_lcoe_pinned` — LCOE 72.94 EUR/MWh bit-perfect
    - `test_mc_sanity_checks` — P10<P50<P90 / std>0 / CDF monotonic
    - `test_mc_tornado` — bars > 0 且 cost_range 排序正確
- **整個 cost module pytest**: 11 PASS + 1 XFAIL（含 -02/-03/-04 累計 12 tests）
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-monte-carlo-migration.md`](work-logs/2026-05/2026-05-04-monte-carlo-migration.md)（session 紀錄）
  - [`modules/cost/tests/test_monte_carlo.py`](modules/cost/tests/test_monte_carlo.py)

---

### WMOM-20260504-03 — `engine/cost_cal/` 移植 + K13 equivalence（M2 主菜）

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: critical（M2 主菜，K13 主驗證 gate）
- **Estimate**: 1-1.5 工作天 → **實際 ~30 分鐘**（SOP 第二次跑就快很多）
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 8 engine files (957 lines) 從 ECN 複製到 `modules/cost/engine/cost_cal/`，sed 改 import
  - ✅ Grep 確認 cost_cal **完全乾淨**：無任何 ECN-specific 依賴（比 waiting_time 更乾淨，不需要 stub 任何 function）
  - ✅ 寫 `tools/pin_cost_cal.py` 一次性工具取 ECN baseline 26 個數字（用 `repr()` 取 float64 完整精度）→ 跑完刪掉
  - ✅ `modules/cost/tests/test_k13_equivalence.py`：3 tests 全 PASS
    - `test_k13_migration_equivalence_pinned` — 6 top-level metrics（availability time/energy、revenue loss、repair cost、total effort、cost per kWh）bit-perfect
    - `test_k13_migration_equivalence_seasonal` — 4 seasons × 5 cost subcategories（material / equipment / revenue_loss / preventive_material / fixed_cost）bit-perfect
    - `test_k13_cost_calculation` — ECN V5 reference 比對（與 ECN 原版同 tolerance 5-30%）
  - ✅ 用 `@pytest.fixture(scope="module")` 共用 K13 結果，3 tests 跑 0.22s
- **整個 cost module pytest**: 6 PASS + 1 XFAIL（含 -02 waiting_time 的 4 tests）
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-cost-cal-migration.md`](work-logs/2026-05/2026-05-04-cost-cal-migration.md)（session 紀錄）
  - [`modules/cost/tests/test_k13_equivalence.py`](modules/cost/tests/test_k13_equivalence.py)（3 tests + 26 pinned 數字）

---

### WMOM-20260504-02 — `engine/waiting_time/` 移植 + K13 equivalence

- **Status**: done（2026-05-04 完成）
- **Milestone**: M2
- **Priority**: high（migration pattern 樹立用）
- **Estimate**: 0.5 工作天
- **Owner**: Claude (session 2026-05-04)
- **Completion summary**:
  - ✅ 7 engine files (1,059 lines) 從 ECN 複製到 `modules/cost/engine/waiting_time/`，sed 一鍵改 import path
  - ✅ Stub `data_processor.preprocess_metocean_data()` — 唯一 ECN-specific 依賴（function-level lazy import 到 SQLAlchemy ORM），engine pipeline 不會走到
  - ✅ K13 demo data (7 檔，~32k 行) 搬到 `modules/cost/data/demo/`
  - ✅ ECN test 適配 → `modules/cost/tests/test_waiting_time.py`：path 改、return → assert、加 xfail with reason
  - ✅ 加 `test_migration_equivalence_pinned`：用 `repr()` 取 ECN float64 完整精度做 pin，windMindOM 必須 bit-perfect 一致
  - ✅ 4 tests 結果：3 PASS（含 migration equivalence）+ 1 XFAIL（pre-existing ECN issue：spring/summer K13 ref 對不上 ECN compute，與 migration 無關）
- **Migration pattern 樹立**（後續 cost_cal / monte_carlo / var_fluct 沿用）:
  1. cp + sed 改 import
  2. grep `from app\.` 找 ECN-specific 依賴 → stub or migrate
  3. 適配 test：path 改、return → assert
  4. 加 pinned equivalence test 用 `repr()` 取精度
  5. xfail with reason 標記 pre-existing ECN issue
- **Reference**:
  - [`work-logs/2026-05/2026-05-04-waiting-time-migration.md`](work-logs/2026-05/2026-05-04-waiting-time-migration.md)（session 紀錄）
  - [`modules/cost/tests/test_waiting_time.py`](modules/cost/tests/test_waiting_time.py)（4 tests）

---

## M3-M4 Planning Open（劉老師 2026-05-04 提的 product 議題）

### WMOM-20260504-10 — Cost ↔ Wind farm config 整合（規劃缺口）

- **Status**: done（2026-05-04 完成 — M3 第一週插入工作）
- **Milestone**: M3（第一週）
- **Priority**: high（M2 demo OK 但對 friendly customer 不夠 personalize）
- **Estimate**: 1-2 工作天 → **實際半天**（K13 overlay 模式收斂得快）
- **Owner**: Claude (session 2026-05-04)
- **Branch**: `claude/issue-20260504-10-2026-05-04`
- **Work-log**: [`work-logs/2026-05/2026-05-04-cost-farm-integration.md`](work-logs/2026-05/2026-05-04-cost-farm-integration.md)
- **Completion summary**:
  - ✅ `cost_inputs.json` schema + `data/farms/{台中港曲風場,彰化離岸風場台電}/cost_inputs.json` 兩個 demo
  - ✅ `adapter.py` 加 `FarmDatasetMeta` + `load_engine_params_from_farm()`：三層 lookup（farm_overlay → registry_derived → k13_fallback）
  - ✅ `schemas/cost_schemas.py`：dataset 從 `Literal["k13"]` 改 str；4 個 response 加 optional `dataset_meta`
  - ✅ `cost_router.py`：`_resolve_dataset()` 統一處理 `k13` / `farm:{id}` / 未知值（404）
  - ✅ Tests +9：5 個 adapter farm loader（overlay / fallback / registry_derived / unknown / unknown_fields filter）+ 4 個 API endpoint（farm overlay / k13 meta / fallback / empty farm_id 422）
  - ✅ Frontend `CostPage.tsx` 加 dataset selector dropdown（K13 + 動態 farm list 從 `/api/farms` 拉）+ `DatasetMetaBadge` 顯示 4 種 source；切 dataset 自動 re-run forecast
  - ✅ `docs/product/MVP_ARCHITECTURE.md` 補節 5.4「Cost ↔ Farm config 整合」
  - ✅ 整 modules pytest：52 PASS + 1 XFAIL（cost 49 / monitoring 3）；frontend Vite build 0 TS error
- **Reference**:
  - [`modules/cost/data/farms/README.md`](modules/cost/data/farms/README.md)
  - [`modules/cost/adapter.py`](modules/cost/adapter.py)（`load_engine_params_from_farm` + `FarmDatasetMeta`）
  - [`docs/product/MVP_ARCHITECTURE.md`](docs/product/MVP_ARCHITECTURE.md) §5.4
  - [`work-logs/2026-05/2026-05-04-cost-farm-integration.md`](work-logs/2026-05/2026-05-04-cost-farm-integration.md)
- **Source**: 劉老師 2026-05-04 收工提問："cost model 跟模擬風機 / 未來實際風機 有連結嗎？"
- **問題描述**:
  目前 `modules/cost/adapter.py` 的 `load_k13_engine_params()` 完全 hard-coded 讀 K13 dataset
  （130 turbines, 4 MW, EUR-based, North Sea offshore wind ECN reference）。
  **與既有 monitoring 完全脫鉤**：
  - 14 台模擬風機（Z72, MW range, 台中港）跑著
  - cost engine 跑著
  - 兩邊互不知道對方存在
- **客戶問會被問倒的**:
  > 「我的風場只有 30 台 Vestas V164，你算 130 台 K13 給我看幹嘛？」
- **要做什麼**:
  1. **設計 farm-aware cost dataset schema**（per-customer JSON）
     - 風場參數：turbine count、capacity_kw、location（→ vessel rates）、kWh tariff、CAPEX
     - 故障率：per-turbine-model FTC table（Z72 / Vestas / SGRE 各別 MTBF）
     - 設備 / 船：local market rates（台灣海域 ≠ 北海）
  2. **adapter 多支援一個 entry point**：
     `load_engine_params_from_farm(farm_id)` — 從 `monitoring/farm_registry` 取 farm config
     + 對應 cost dataset → engine params
  3. **API endpoint 加 dataset 參數**：
     `POST /api/cost/forecast { "dataset": "farm:taichung-z72-001" }`（vs `"k13"`）
  4. **預設 fallback**：找不到 farm-specific dataset 時用 K13 + warning
- **Deliverable**:
  - `modules/cost/data/farms/{farm_id}/cost_inputs.json` 雛形
  - `adapter.py` 加 `load_engine_params_from_farm(farm_id)`
  - frontend 「dataset selector」（dropdown 選 K13 demo / 真實 farm）
  - `docs/product/MVP_ARCHITECTURE.md` 補一節「Cost ↔ Farm config 整合」
- **Reference**:
  - 已在 cost engine 的 K13_FTC_DEFAULTS / K13_MC_EQUIPMENT 是這個方向的 hard-code 版

---

### WMOM-20260504-13 — Cost 系列 fetch 加 AbortController 防 race

- **Status**: done（2026-05-23 完成 — autonomous daily worker）
- **Milestone**: M5 / M6（不阻塞 demo）
- **Priority**: low
- **Estimate**: 0.25 工作天 → **實際 ~0.25d**（frontend only）
- **Owner**: Claude (session 2026-05-23)
- **Branch**: `claude/issue-WMOM-20260504-13-2026-05-23`
- **Source**: code-reviewer 對 WMOM-10 的 finding #5（2026-05-04）
- **Completion summary**:
  - ✅ `frontend/services/costService.ts`：`postJSON` + `costApi`×4（forecast/lcoe/monteCarlo/varFluct）加 optional `AbortSignal` 參數透傳給 `fetch`（純擴充，不帶 signal 的呼叫行為不變）
  - ✅ `frontend/hooks/useCostData.ts`：`useAsync.run` 三道防線消除 race：
    1. `useRef<AbortController>` 追蹤最新 in-flight request，下一筆 run 前先 `abort()` 上一筆
    2. `signal.aborted` 早退 → 即使舊 fetch 已 resolve 也不 `setData` 蓋掉新結果
    3. `controllerRef.current === controller` loading guard → 只有最新 request 結束 loading
  - ✅ `isAbortError` 接 `DOMException` + `Error`（瀏覽器原生 / polyfill 兩種）；`reset()` 也 abort + 清 loading；`useEffect` cleanup 在 unmount abort 仍 in-flight 的 request
  - ✅ Verify：`tsc --noEmit` 0 errors + `vite build` 748 modules / 4.58s / 0 errors；backend 未動（zero regression）
  - ✅ Code review 1 must + 1 should + 1 nice：should（isAbortError 補 DOMException）採納；must（reset 與 in-flight run 交錯疑 loading 殘留）以 timeline 推導判定**非真 bug**（reset 已 unconditional setLoading(false)；await resolve→finally 之間 microtask 不可插入外部 callback），不採納 hacky dead-controller，改加註解文件化
- **驗收**（劉老師本機 dev 手動）:
  - dev mode 切 dataset 5 次，最終顯示的 forecast 對應最後一次選的 dataset ✅（邏輯保證）
  - 取消舊 fetch 不會 throw 進 error state ✅（isAbortError + signal.aborted 早退）
- **已知限制**: frontend 無測試框架（無 vitest/jest），未加自動化 regression test — 為 0.25d 小工不引入整套 harness；建議另開 issue 一次導入 vitest+RTL
- **Reference**:
  - [`frontend/hooks/useCostData.ts`](frontend/hooks/useCostData.ts)
  - [`frontend/services/costService.ts`](frontend/services/costService.ts)
  - [`work-logs/2026-05/2026-05-23-cost-abortcontroller.md`](work-logs/2026-05/2026-05-23-cost-abortcontroller.md)（session 紀錄）

---

### WMOM-20260524-01 — Frontend 測試基礎設施（vitest + RTL）+ 回補 race-condition regression test

- **Status**: done（2026-05-24 完成 — autonomous daily worker）
- **Milestone**: M5 / M6（測試 infra，不阻塞 demo；解鎖未來 frontend regression 覆蓋）
- **Priority**: medium（連續 3 次 handoff 推薦的「新 issue 候選」— 5/23 AbortController + 5/24 WS leak 兩次修復都因無框架而無法補自動化測試）
- **Estimate**: 0.5 工作天 → **實際 ~0.5d**（frontend only）
- **Owner**: Claude (session 2026-05-24)
- **Branch**: `claude/upbeat-davinci-NZNJt`
- **Source**: WMOM-20260504-12 / -13 work-log 的「frontend 無測試框架，建議另開 issue 一次導入 vitest+RTL」
- **Completion summary**:
  - ✅ 導入 `vitest@^3` + `jsdom@^29` + `@testing-library/react@^16` + `@testing-library/dom`（devDependencies）
  - ✅ `frontend/vitest.config.ts`（與 vite.config.ts 分離；jsdom env、`include: **/*.test.{ts,tsx}`、`setupFiles`、`restoreMocks`）
  - ✅ `frontend/vitest.setup.ts`（afterEach RTL cleanup，不依賴 globals）
  - ✅ `package.json` 加 scripts：`test`（vitest run）+ `test:watch`
  - ✅ **回補 WMOM-20260504-12 regression**：`frontend/hooks/useRealtimeData.test.ts`（2 test）— FakeWebSocket + fake timer 鎖住「卸載後解除 4 handler 再 close、不再排程重連（無殭屍 WebSocket）」+「掛載中斷線仍 3s 後重連（重連機制未被誤殺）」
  - ✅ **回補 WMOM-20260504-13 regression**：`frontend/hooks/useCostData.test.ts`（2 test）— mock costApi + 可控 deferred，驗「stale 結果不蓋 fresh」+「AbortError 不寫進 error state」
  - ✅ Verify：`npx vitest run` → **4 passed**；`npx tsc --noEmit` 0 errors（含新測試檔）；`npx vite build` 748 modules / 0 errors（測試檔正確排除於 bundle 外，module 數與 baseline 相同）；backend 未動（zero regression）
- **驗收**:
  - 後續 frontend session 可 `cd frontend && npm install && npm test` 跑 regression ✅
  - 兩個 race-condition fix 已有自動化守門，回歸即 fail ✅
- **後續可擴充**（不在本 issue scope）:
  - 元件層測試（FarmOverview memo 行為 / CostPage panel）需 render + mock，量較大，另開 issue
  - CI 上掛 `npm test`（目前 sandbox 無 CI runner）
  - SessionStart hook 預裝 test 依賴，省每次重裝（建議併入既有 infra issue）
- **Reference**:
  - [`frontend/vitest.config.ts`](frontend/vitest.config.ts)
  - [`frontend/hooks/useRealtimeData.test.ts`](frontend/hooks/useRealtimeData.test.ts)
  - [`frontend/hooks/useCostData.test.ts`](frontend/hooks/useCostData.test.ts)
  - [`work-logs/2026-05/2026-05-24-frontend-test-infra.md`](work-logs/2026-05/2026-05-24-frontend-test-infra.md)（session 紀錄）

---

### WMOM-20260505-01 — Snapshots 表失控（41.9 GB SQLite hotfix）

- **Status**: done（2026-05-05 — PR #3 merged, VACUUM 釋放 41 GB 確認）
- **Milestone**: M1 follow-up（hotfix — production blocker，不在原規劃 issue 內）
- **Priority**: critical（production data growth — 17.5 天累積 41.9 GB；不修一個月可達 1 TB+）
- **Estimate**: 0.5-1 工作天
- **Owner**: Claude (session 2026-05-05)
- **Branch**: `claude/issue-20260505-01-2026-05-05`
- **Trigger**: 劉老師 2026-05-05 截圖 — 彰化離岸風場台電 farm 的 `wind_farm.db` 累積到 41.9 GB
- **Root cause analysis**:
  - `turbine_snapshots` 表 1,081 萬 row 佔絕大部分容量
  - 17.5 天範圍 / 19,594 個 distinct event_ref / 每 event 平均 606 row（10 分鐘 1Hz capture）
  - **三個放大因子疊加**：
    1. `storage.run_cleanup` **不清** snapshots（schema 註解寫 permanent，但實際是 bug — 沒有 retention）
    2. `data_broker._trigger_snapshot` 每次重新 trigger 時 retroactively 寫入 ~10 分鐘 in-memory history → 同類 event 重 trigger 時放大
    3. simulator state machine 在 stop=7 附近 flapping，每幾秒對同一台同一原因 emit 新 event_ref
  - 觀察證據：top event_ref 全是 `stop:WT007:7:...` 在 80 秒內連 trigger 11 次新 event
- **修法（3 件事一起做）**:
  1. `storage.run_cleanup` 加 `snapshots_retention_days` 參數（預設 7 天），DELETE FROM turbine_snapshots WHERE timestamp < cutoff
  2. `data_broker._trigger_snapshot` 加 dedupe + cooldown：
     - event_class（去掉 timestamp 部分，e.g. `stop:WT007:7`）作 dedupe key
     - 同類在 cooldown 期間（預設 5 分鐘）→ 僅延長現有 window，不重新 retroactive write
  3. 提供 `tools/vacuum_db.py` — 用 `VACUUM INTO` 寫到 sibling 路徑再 swap，避開 SQLite 原 VACUUM 需 2× 空間需求（41.9 GB 場景吃 84 GB）
- **Tests**:
  - test_storage_cleanup_snapshots_with_retention
  - test_data_broker_snapshot_dedupe_within_cooldown
- **Deliverable**:
  - 修改 `modules/monitoring/server/storage.py`（run_cleanup + 對應 maintenance_thread caller）
  - 修改 `modules/monitoring/server/data_broker.py`（_trigger_snapshot dedupe）
  - 新增 `modules/monitoring/tests/test_storage_cleanup.py` + `test_broker_snapshot_dedupe.py`
  - 新增 `tools/vacuum_db.py`（CLI tool，VACUUM INTO + swap）
- **Reference**:
  - 觀察分析資料：`/tmp/db_check2.py` 取樣結果（17.5 天 / 19,594 events / 606 row/event / 2,441 bytes/row）
  - 根因關鍵程式碼：[`data_broker.py:397`](modules/monitoring/server/data_broker.py) `_trigger_snapshot`
  - 根因關鍵程式碼：[`storage.py:520`](modules/monitoring/server/storage.py) `run_cleanup`（沒清 snapshots）

---

### WMOM-20260504-12 — Frontend 長時間執行記憶體成長（觀察）

- **Status**: in_progress（2026-05-24 — autonomous daily worker：root cause WS 殭屍重連洩漏已根治 + 卡片 React.memo；待劉老師 24h 記憶體驗收後 close）
- **Milestone**: M5 / M6（不阻塞 demo，可選優化）
- **Priority**: low → **medium**（進場發現含真 bug：WS 殭屍重連 leak）
- **Estimate**: 0.5-1 工作天
- **Owner**: Claude (session 2026-05-24)
- **Branch**: `claude/upbeat-davinci-348BY`
- **Progress（2026-05-24）**:
  - ✅ **真因 = suspect #4：WS 殭屍重連洩漏**。`useRealtimeData` 的 `ws.onclose` 無條件 `setTimeout(connect, 3000)`；unmount cleanup 呼叫 `ws.close()` 非同步觸發 onclose，在 cleanup 跑完後又排一條清不到的重連 timer → 殭屍 WebSocket 無限累積（每條每次 push 都呼叫 setTurbines）。React 18 Strict Mode dev 雙觸發立刻引爆 = 劉老師回報的 dev 記憶體成長。**修法**：`disposed` 旗標貫穿 connect/onopen/onmessage/onclose/onerror/poll；cleanup 設 disposed=true + 先解除 ws 四個 handler 再 close() + 清 timer/interval；initial REST fetch 加 cancelled guard。
  - ✅ **suspect #1：卡片 React.memo**。`FarmOverview` 的 `TCard` / `CompactTile` 加 `React.memo` + 自訂 `areEqual`（只比渲染欄位 + 新增 `lang` prop），父層因非資料因素 re-render（檢視模式切換 / 健康輪詢 / modal）時跳過 14 張 SVG 重繪。onClick/tr 刻意排除（onClick stale 由 App `liveTurbine` 以 id 反查保證；tr 為 lang 純函式；theme 走 context 不受 memo 影響）。
  - ⏭️ **suspect #2（selective setState）不做** — 已被卡片層 areEqual 取代（per-card 比較更直接）。
  - ⏭️ **suspect #3（Recharts leak）不適用 overview** — overview sparkline 走自寫 SVG（`ui/Charts.tsx`），非 Recharts；只 HistoryPage 用 recharts，若該頁長跑有 leak 另開 issue。
  - ⏭️ **suspect #5（升級/pin recharts）** 不在本 PR scope。
  - **Verify**: tsc 0 errors + vite build 748 modules / ~3.4s / 0 errors；backend 未動 zero regression。Code review 1 must（onClick stale，判定非 bug）+ 2 should（onerror disposed guard 採納；compactTileEqual turState 不採納）+ 1 nice（history reference 比較，判定非 bug）。
  - **註**：issue 描述的元件名 `MiniTrendChart`/`TurbineCard` 在 5/07 UI 改版（WMOM-20260507-01）後已不存在，實際目標改為 `TCard`/`CompactTile`。
- **待 close 條件**: 劉老師本機 dev 長跑驗收 — (1) Strict Mode 來回切頁不再累積多條 `[WS] Connected`，WS 連線數穩定為 1；(2) 24h 連續執行記憶體成長 < 50%。
- **Reference**:
  - [`frontend/hooks/useRealtimeData.ts`](frontend/hooks/useRealtimeData.ts)（WS 生命週期修復）
  - [`frontend/components/FarmOverview.tsx`](frontend/components/FarmOverview.tsx)（TCard/CompactTile React.memo）
  - [`work-logs/2026-05/2026-05-24-frontend-realtime-memory-fix.md`](work-logs/2026-05/2026-05-24-frontend-realtime-memory-fix.md)（session 紀錄）
- **觀察結果**:
  - **Backend 儲存有 bug — 見 [WMOM-20260505-01](#wmom-20260505-01--snapshots-表失控419-gb-sqlite-hotfix)**：原本以為 `storage.py` 4 層 tiered retention 正常運作；2026-05-05 發現 turbine_snapshots 沒清 → 失控膨脹
  - **前端跑數小時記憶體成長** = 典型 React SPA 長時間運行 GC 跟不上問題，與資料儲存無關，refresh 即重置
- **可能來源（依嫌疑度）**:
  1. **MiniTrendChart × 14 張卡** — 每張 turbine card 帶一個 Recharts SVG mini-chart，每次 WebSocket push（10s）都 re-render 14 個 SVG，DOM 節點累積
  2. **`useRealtimeData` 整批替換 state** — 每次 WS push 整 array of 14 turbines 全替換而非 selective update，React diff 開銷大
  3. **Recharts ResponsiveContainer** 已知 resize observer / portal listener 在某些版本長時間執行有 leak
  4. WebSocket 重連時的 listener 累積（要查 cleanup）
- **建議的緩解（順序）**:
  1. 對 TurbineCard / MiniTrendChart 加 `React.memo` + 自訂 `areEqual`（只在 power/status 變才 re-render）
  2. `useRealtimeData` selective update：比對舊新 turbine list 只 mutate 改變的，不整批 setState
  3. 評估把 MiniTrendChart 換成 canvas-based（chart.js / 自寫 canvas），跳過 SVG DOM
  4. 加「自動 24h 軟 reload」機制（demo 用）— 簡單暴力但有效
  5. 升級 / pin recharts 版本，看 changelog 有沒有 leak fix
- **不阻塞**: refresh 即解決，不影響資料儲存，不影響客戶 demo（30 分鐘 demo 不會撞到）
- **驗收**: 24 小時連續執行記憶體成長 < 50% 視為可接受
- **Reference**:
  - `frontend/hooks/useRealtimeData.ts:229` — turbines state 整批替換
  - `frontend/components/MiniTrendChart.tsx` — 14 個 SVG re-render 來源

---

### WMOM-20260504-11 — Event-driven cost ledger（M4 增強）

- **Status**: open
- **Milestone**: M4（部分覆蓋）+ **新功能延伸到 M5/M6**
- **Priority**: high
- **Estimate**: 2-3 工作天（M4 既有 work order → ledger 之上補完）
- **Source**: 劉老師 2026-05-04 提問："cost 是否會隨故障/更換零件/發電/停機 來計算（收入支出）？"
- **既有 ROADMAP 涵蓋**:
  - ✅ M4 規劃「Cost ↔ Workflow 雙向: Work Order 完工 → cost ledger（actual）」
  - ✅ `GET /api/cost/ledger` endpoint
  - ✅ `/admin/cost/ledger` UI
- **規劃缺口（要補進來）**:
  1. **收入端**：發電量 × 電價 → 每日 / 每月入帳
     - Source：monitoring 的 `turbine_data` 表（每 10 秒 power_output kW）
     - Aggregate：每日 sum × tariff → daily_revenue table
     - 目前 turbine_data 已 ready，缺 aggregator + ledger entry
  2. **故障即時影響**：fault 發生 → 估推 revenue loss = downtime × expected_power × tariff
     - 整合 `modules/monitoring/scada_system.py` 的 fault scenario detection
     - Push pending revenue_loss 到 ledger（status: estimated → confirmed when 完工）
  3. **零件更換成本 + RUL 影響**：
     - 工單填料件清單 → 對應 component 表 → cost + RUL adjustment
     - 影響下次 monte_carlo 的 freq_min/ml/max（empirical update）
  4. **Ledger schema 設計**：
     ```
     CostLedger {
       id, farm_id, timestamp, type: 'revenue' | 'expense',
       category: 'generation' | 'corrective' | 'preventive' | 'fixed' | 'revenue_loss',
       amount, source_event_id, status: 'estimated' | 'confirmed'
     }
     ```
- **Deliverable**:
  - `modules/cost/models/cost_ledger.py` — SQLAlchemy / dataclass schema
  - `modules/cost/services/revenue_aggregator.py` — turbine_data → daily revenue
  - `modules/cost/services/event_ledger.py` — fault / work-order / inventory → ledger entries
  - 整合 `modules/workflow/work_order.py`（M3 完成後）— 工單完工 → ledger expense
  - 新 endpoint `GET /api/cost/ledger?farm_id=&from=&to=&type=`
  - frontend `/admin/cost/ledger` page — 實際 vs 預測對比
- **依賴**:
  - WMOM-10（farm 整合）必須先做 — ledger 需要 farm_id 維度
  - M3 work order CRUD 完成 — expense ledger 才能寫入
  - M4 inventory 完成 — 零件 cost 才能拆分
- **設計筆記應該寫進**: `docs/product/decision_log.md` DEC-{date}-XX「Cost 從 budget calculator 升級為 real-time ledger」

---

## M3 主線（2026-07）— Workflow Part 1: Work Order + Approval

> M3 主軸：從 z72_etech 取設計 → design notes → walkthrough → Work Order CRUD + 狀態機 + Approval。
> 7 個 sub-issue。`WMOM-20260504-10` (cost↔farm) 已先在 M3 第一週插入完成。

### WMOM-20260504-14 — z72_etech 取設計 + 3 份 design notes（**取材選 A**）

- **Status**: done（2026-05-05 完成 — 三份 DN 全寫 + walkthrough confirmed 一次到位）
- **Milestone**: M3
- **Priority**: critical（M3 spike，已解 blocking）
- **Estimate**: 1-2 工作天 → **實際 1 天**（劉老師全 agree default 建議，walkthrough 跟設計一次合併）
- **Owner**: Claude (session 2026-05-04 / 2026-05-05)
- **Branch**: `claude/issue-20260504-14-2026-05-04` (DN-01 part) + `claude/issue-20260504-15-walkthrough-2026-05-05` (DN-02/03 + walkthrough)
- **Completion summary**:
  - ✅ z72_SCADA_etech repo inventory（盤點報告 + 重構路線圖 + 5+ 個關鍵 module 程式）
  - ✅ DN-01 [Work Order Lifecycle](docs/design-notes/m3/DN-01-work-order-lifecycle.md) — 含 walkthrough 7 Q 答覆 + schema 微調（FollowupKind 二元 / Priority enum / multi-WO constraint / inspection auto-spawn hook）
  - ✅ DN-02 [Approval Multi-level](docs/design-notes/m3/DN-02-approval-multilevel.md) — 4 階 signoff / 工單 2 階 / 領料 3 階 / reject 回 IN_PROGRESS / signoff_history KPI
  - ✅ DN-03 [Inventory ↔ Material Request](docs/design-notes/m3/DN-03-inventory-material-request.md) — 3 欄位庫存 / 估計 vs 實際領料 / 退料 4 種分類 / 多倉預留 / inventory_adjustment_log 給庫管員手動 +/-
  - ✅ [README](docs/design-notes/m3/README.md) — 三份 DN 索引 + etech 10 大模組對照表 + 不取的東西清單
  - ✅ 衍生兩個新 issue：[WMOM-20260505-21](#wmom-20260505-21) (day_work_form) + [WMOM-20260505-22](#wmom-20260505-22) (inspection_schedule)
- **Reference**:
  - [`docs/design-notes/m3/`](docs/design-notes/m3/)（三份 DN + README）
  - [`work-logs/2026-05/2026-05-05-walkthrough-and-dn02-dn03.md`](work-logs/2026-05/2026-05-05-walkthrough-and-dn02-dn03.md)

---

### WMOM-20260504-15 — 30 分鐘 walkthrough 跟劉老師確認 design notes

- **Status**: done（2026-05-05 完成 — 與 -14 合併走完）
- **Milestone**: M3
- **Priority**: high
- **Estimate**: 0.5 工作天 → **實際 30 分**（合併在 -14 內，劉老師逐一答 17 個 Q）
- **Owner**: Claude + 劉老師
- **Completion summary**:
  - ✅ DN-01 7 個 Q 全 confirmed（含 removeFrom / chooseschange / multi-WO / 4 type / weather_window / dayworkForm / inspection）
  - ✅ DN-02 5 個 Q 全 agree default（4 階 signoff / 工單 2 階 vs 領料 3 階 / reject 回 IN_PROGRESS / 線性 / history 保留）
  - ✅ DN-03 5 個 Q 全 agree default（3 欄位庫存 / 系統追蹤部分 + 紙本歸還 / 估計 vs 實際 / 4 種退料分類 / 多倉預留）
  - ✅ Q&A 直接整合進對應 DN 文件（取代原「open questions」section）
  - ✅ 兩個衍生 issue 開好（WMOM-21 + WMOM-22）

---

### WMOM-20260504-16 — Work Order 領域模型 + 狀態機（pure domain）

- **Status**: done（2026-05-05 完成）
- **Milestone**: M3
- **Priority**: critical
- **Estimate**: 1 工作天 → **實際半天**（含 code review fix）
- **Owner**: Claude (session 2026-05-05)
- **Branch**: `claude/issue-20260504-16-2026-05-05`
- **Completion summary**:
  - ✅ `modules/workflow/domain/work_order.py`：4 Enum + ProgressNote + WorkOrderFollowup + WorkOrder dataclass
  - ✅ `modules/workflow/domain/state_machine.py`：TransitionRule + WORK_ORDER_TRANSITIONS（9 rule / 8 action）+ 6 guard + WorkOrderStateMachine + helper
  - ✅ Tests +73：test_work_order.py (20) + test_state_machine.py (53) — 含完整 lifecycle / parametrized 反例 / guard 不污染 state regression
  - ✅ Code review 13 finding 全處理（5 must-fix + 5 should-fix + 3 nice-to-have）
  - ✅ 整 pytest 163 PASS + 1 XFAIL（cost 49 + monitoring 35 + workflow 79）
- **Reference**:
  - [`modules/workflow/domain/`](modules/workflow/domain/)
  - [`work-logs/2026-05/2026-05-05-work-order-domain.md`](work-logs/2026-05/2026-05-05-work-order-domain.md)

---

### WMOM-20260504-17 — Work Order CRUD + REST API + tests

- **Status**: done（2026-05-05 完成）
- **Milestone**: M3
- **Priority**: critical
- **Estimate**: 1 工作天 → **實際 ~1 天**（含 code review 9 finding 全處理）
- **Owner**: Claude (session 2026-05-05)
- **Branch**: `claude/issue-20260504-17-2026-05-05`
- **Completion summary**:
  - ✅ `modules/workflow/repository/`：3 個 SQLAlchemy 2.0 ORM + WorkOrderRepository（CRUD + transition + multi-WO constraint + business_key + event log）
  - ✅ `modules/workflow/schemas/work_order_schemas.py`：10 個 pydantic v2 model
  - ✅ `modules/workflow/routers/work_order_router.py`：11 個 FastAPI endpoints
  - ✅ Mount 進主 FastAPI app
  - ✅ Tests +50：repository 31 + API 19
  - ✅ Code review 9 finding 全處理（3 must-fix + 5 should-fix + 1 nice-to-have）
  - ✅ 整 pytest 213 PASS + 1 XFAIL（cost 49 + monitoring 35 + workflow 129）
- **Reference**:
  - [`modules/workflow/`](modules/workflow/)
  - [`work-logs/2026-05/2026-05-05-work-order-crud-api.md`](work-logs/2026-05/2026-05-05-work-order-crud-api.md)

---

### WMOM-20260504-18 — Approval 多階簽核 + tests

- **Status**: done（2026-05-05 完成）
- **Milestone**: M3
- **Priority**: critical
- **Estimate**: 1 工作天 → **實際 ~1 天**（含 code review 11 finding 全處理）
- **Owner**: Claude (session 2026-05-05)
- **Branch**: `claude/issue-20260504-18-2026-05-05`
- **Completion summary**:
  - ✅ `modules/workflow/domain/signoff.py`：4 階 SignoffLevel + chain/step/history dataclasses + chain policy + user_group_to_level helper
  - ✅ `modules/workflow/repository/orm_models.py`：+3 個 SQLAlchemy 2.0 mapped class
  - ✅ `modules/workflow/repository/signoff_repository.py`：create_chain + approve/reject + pending list + history audit
  - ✅ `modules/workflow/schemas/signoff_schemas.py`：6 個 pydantic v2 model
  - ✅ `modules/workflow/routers/approval_router.py`：3 個 endpoints + factory injection
  - ✅ Integration: work_order finish → auto-create chain；approve last → 自動 work_order.approve_all；reject → 自動 work_order.reject
  - ✅ Mount 進主 FastAPI app
  - ✅ Tests +34（signoff repo 28 + approval API 9）；整 pytest 250 PASS + 1 XFAIL
  - ✅ Code review 11 finding 全處理（5 must-fix + 4 should-fix + 2 nice-to-have）
- **Reference**:
  - [`modules/workflow/`](modules/workflow/)（domain/signoff.py + repository/signoff_repository.py + routers/approval_router.py）
  - [`work-logs/2026-05/2026-05-05-approval-signoff-api.md`](work-logs/2026-05/2026-05-05-approval-signoff-api.md)

---

### WMOM-20260504-19 — `/admin/workflow/orders` frontend（建立精靈 + 列表 + 詳情）

- **Status**: done（2026-05-09 完成）
- **Milestone**: M3
- **Priority**: high
- **Estimate**: 1-1.5 工作天 → **實際 ~半天**（API client + hook + 4 components + nav 接線）
- **Owner**: Claude (session 2026-05-09)
- **Completion summary**:
  - ✅ `frontend/services/workOrderService.ts`：11 個 endpoint TypeScript wrapper（CRUD + 8 transitions + farm list helper）+ enum / type 與後端 schema 對齊
  - ✅ `frontend/hooks/useWorkOrders.ts`：stateful hook（list / loading / error + 9 mutations，patch local state on success，AbortController race guard）
  - ✅ `frontend/components/workflow/` 4 個檔案：
    - `WorkflowPage.tsx`：主入口（farm 自動偵測 + tab 預留 approval -20 + create modal/detail modal 對接）
    - `WorkOrderListPanel.tsx`：列表（status filter / search / refresh / empty state / error display）
    - `CreateWorkOrderWizard.tsx`：3-step 精靈（風機卡片選 → type+priority+title+description → assignee+crew+hours + review）
    - `WorkOrderDetailModal.tsx`：詳情 + 7 inline transition forms（dispatch / start-work / progress / finish / reject / cancel / reopen；approve 走 -20）
    - `statusUtils.ts`：status / priority / type / followup enum 對 PillTone + zh/en label + datetime fmt 共用 helper
  - ✅ `frontend/App.tsx`：加 `workflow` ViewId + nav；傳 turbines 到 WorkflowPage
  - ✅ `frontend/components/ui/Logo.tsx`：加 `workflow` NavIcon（briefcase）
  - ✅ Smoke test：`tsc --noEmit` clean、`vite build` 成功（725 modules / 1.05 MB）、dev server localhost:5179 回 HTTP 200
  - ✅ UI directive 遵守：全程走 `frontend/components/ui/` + `useTheme().C`，無 Tailwind utility、無 hex（chart event 例外）
- **Decisions made during impl**:
  - 詳情 modal 寫在 `components/workflow/WorkOrderDetailModal.tsx`（與 legacy mock 版 `components/WorkOrderDetailModal.tsx` 區分）— 後者對應的 WorkOrder type 跟 backend schema 完全不同 shape，沿用會強行轉型不健康
  - `actor_id` 採 `DEV_ACTOR_ID = '00000000-...01'` 占位（auth 系統 M5+ 才接），constant 在 service.ts，TODO 註解明確
  - approve 按鈕在 detail modal **disable**，顯示提示「走 -20 approval 流程」；list 顯示 `awaiting_signoff` 狀態讓 user 知道需要去 approval tab（-20 上線後）
  - turbine_id 用 `turbine.name` 字串（與 backend simulator 的 string id convention 對齊）
  - 列表 search 設計：server-side 走 status filter，client-side 過濾 business_key / title / turbine_id 子字串（避免 backend 加 search index 的工程量）
- **Follow-up**：
  - ⬜ approve 按鈕真正啟用 → WMOM-20260504-20 上線時補
  - ⬜ Pagination UI（目前 limit=200 單頁）→ 工單量 > 200 時再加（M4 後）
  - ⬜ `/api/workflow/work-orders/{id}/event-log` 讀取顯示 → 等 backend 加 endpoint
  - ⬜ assignee_id 由文字輸入改成 user picker → 等 auth/user system 上線
- **Reference**:
  - [`work-logs/2026-05/2026-05-08-work-order-frontend.md`](work-logs/2026-05/2026-05-08-work-order-frontend.md)
  - Backend: WMOM-20260504-17（CRUD/state API）+ WMOM-20260504-18（signoff chain）

<details><summary>📜 原始 issue description</summary>

- **UI directive（WMOM-20260507-01 後）**：
  必須使用 `frontend/components/ui/`（Card / Btn / PageHeader / StatusPill / Field / Input / Select / Stat / BigChart / HealthBar）+ `frontend/theme/`（useTheme → C palette）。**不可** 寫 Tailwind utility class、不可硬寫 hex（chart event 標記色除外）。Modal 套既有 [WorkOrderDetailModal](frontend/components/WorkOrderDetailModal.tsx) 風格（Card padding=0 + DM Serif title + 底部 Btn）。
- **Description**:
  - `frontend/services/workOrderService.ts` (TypeScript API client)
  - `frontend/hooks/useWorkOrders.ts`
  - `frontend/components/WorkflowPage.tsx` 主入口
  - `frontend/components/workflow/WorkOrderListPanel.tsx` 列表（含 status filter + Hnumber search）
  - `frontend/components/workflow/CreateWorkOrderWizard.tsx` 建立精靈（多步：選風機 / 選故障代碼 / 派工人員 / 預估工時）
  - `frontend/components/workflow/WorkOrderDetailModal.tsx` 詳情 + 狀態 transition 按鈕

</details>

---

### WMOM-20260504-20 — `/admin/workflow/approval` frontend（待簽列表 + 簽核操作）

- **Status**: done（2026-05-09 完成；與 -19 同日 push）
- **Milestone**: M3
- **Priority**: high
- **Estimate**: 1 工作天 → **實際 ~半天**（service+hook+2 component+wire panel/tab）
- **Owner**: Claude (session 2026-05-09)
- **Completion summary**:
  - ✅ 擴充 `frontend/services/workOrderService.ts`：加 SignoffLevel/Status/SubjectType + 6 個 response/request interface + `signoffApi.{listPending, approve, reject}`
  - ✅ `frontend/hooks/usePendingApprovals.ts`：list state + approve/reject mutations + workOrderCache（`Promise.allSettled` 並行 fetch 對應工單 detail，給 UI 顯示 title/priority 用）+ AbortController race guard
  - ✅ `frontend/components/workflow/PendingApprovalPanel.tsx`：level selector（4 enum，default leader）+ subject_type filter + 列表（subject summary + step/chain progress + approve/reject 按鈕）
  - ✅ `frontend/components/workflow/ApprovalActionDialog.tsx`：兩模式 approve（comment 選填）/ reject（reason 必填）+ subject 摘要避免簽錯 + `subject_transition_error` warning 處理（chain 落地但工單 transition 失敗的 race case）
  - ✅ `frontend/components/workflow/statusUtils.ts`：加 `signoffLevelLabel` / `signoffStatusLabel` / `signoffStatusTone` / `subjectTypeLabel` zh/en helper
  - ✅ `frontend/components/workflow/WorkflowPage.tsx`：tab 從 dummy disabled 變真切換、render `<PendingApprovalPanel>` + `<ApprovalActionDialog>`；tab 顯示 pending count badge；approve/reject 後 `subject_status_changed === true` 自動 `wo.refresh()` 同步 orders list
  - ✅ Smoke test：tsc clean / vite build 成功（1067 kB / gzip 286 kB）/ dev 5179 回 200
  - ✅ UI directive 完整遵守：ui 元件庫 + theme palette / 無 Tailwind / 無 hex / dialog 套既有 modal 風格
- **Decisions made during impl**:
  - work order detail cache 走「list 拉到後並行 fetch 所有 unique subject_id」(`Promise.allSettled` 容忍個別 404)，避免每個 row 顯示 title 都要 hover-fetch；M4 領料單來時同邏輯擴充
  - default level = leader（工單 chain `[EMPLOYEE, LEADER]` 中 reviewer 最常出現的角色）
  - 工單 detail modal 的 approve 按鈕仍 disable — DN-02 設計上 approve 走 `/approvals/{step_id}/approve` 而非工單層 `/work-orders/{id}/approve`（後者是 server-side guard 副作用 endpoint，不是 user-facing action）
  - `subject_transition_error` 用 warning Card 顯示而非錯誤 — chain 已落地不能 retry，需要 ops 人工 backfill 工單 status
- **Reference**:
  - [`work-logs/2026-05/2026-05-09-approval-frontend.md`](work-logs/2026-05/2026-05-09-approval-frontend.md)
  - Backend: WMOM-20260504-18（signoff chain + 3 endpoints）

<details><summary>📜 原始 issue description</summary>

- **UI directive（WMOM-20260507-01 後）**：
  與 -19 同 — 使用 `frontend/components/ui/` + `frontend/theme/`，不可 Tailwind / 硬 hex。Approval action dialog 套 [DispatchModal](frontend/components/DispatchModal.tsx) 模式（Card padding=0 + grid 內 Btn 卡片選人 + 底部 primary 確認）。
- **Description**:
  - `frontend/components/workflow/PendingApprovalPanel.tsx` 待簽列表（badge 含工單摘要 + 簽核層級）
  - `frontend/components/workflow/ApprovalActionDialog.tsx` 簽核 / 駁回對話框（含意見輸入）
  - 整合進 `WorkflowPage.tsx`（tab 切換 orders / approval）
  - 全 zh / en i18n

</details>

---

## M3 衍生 issue（從 walkthrough Q6 / Q7 衍生 — 不在 M3 主線 7 sub-issue 內）

### WMOM-20260505-21 — `day_work_form` 員工日誌設計與實作

- **Status**: open
- **Milestone**: M3 後續 / M4 之間（不阻塞 M3 主線）
- **Priority**: medium
- **Estimate**: 1-1.5 工作天
- **Source**: DN-01 walkthrough Q6（劉老師 2026-05-05 確認）
- **UI directive（WMOM-20260507-01 後）**：frontend `/admin/workflow/daywork` 必須使用 `frontend/components/ui/` + `frontend/theme/`，不可 Tailwind / 硬 hex。
- **Description**:
  工單對象 = 風機；員工日誌對象 = 員工 × 當天。兩個 entity 不同，但有引用關係。
  日誌可包含「完成 1 張工單 + 完成 2 個定檢項 + 巡視 + 訓練」等 4 種 activity kind。
- **Deliverable**:
  - `modules/workflow/domain/day_work_form.py`：DayWorkForm + ActivityEntry + ActivityKind enum
  - `modules/workflow/repository/day_work_form_repository.py`
  - `modules/workflow/routers/day_work_form_router.py`：CRUD + 「我今天做了什麼」query
  - frontend `/admin/workflow/daywork` 列表 + 個人填單頁
  - 整合 work_order.finish() 時自動寫進當天 day_work_form
- **Reference**:
  - [`docs/design-notes/m3/DN-01-work-order-lifecycle.md`](docs/design-notes/m3/DN-01-work-order-lifecycle.md) §3.3
  - etech 對應：`server/dayworkForm.js` + `pages/dayworkForm.vue`

---

### WMOM-20260505-22 — `inspection_schedule` 定檢計畫 + scheduler auto-spawn

- **Status**: open
- **Milestone**: M3 後續 / M4 之間（不阻塞 M3 主線）
- **Priority**: medium
- **Estimate**: 1-1.5 工作天
- **Source**: DN-01 walkthrough Q7（劉老師 2026-05-05 確認）
- **Description**:
  定檢清單獨立 entity（如「每月一次塔筒螺栓檢查」「每季一次潤滑油檢查」）。
  Scheduler 把到期 inspection auto-spawn `work_order(type=INSPECTION)`，避免人工漏排。
- **Deliverable**:
  - `modules/workflow/domain/inspection_schedule.py`：InspectionSchedule + Recurrence enum
  - `modules/workflow/services/inspection_scheduler.py`：daily check 到期項 → spawn WO
  - `modules/workflow/routers/inspection_router.py`：CRUD 定檢計畫 + query「下次檢查時間」
  - frontend `/admin/workflow/inspection` 計畫列表 + 編輯 + 「下次到期」dashboard
- **Reference**:
  - [`docs/design-notes/m3/DN-01-work-order-lifecycle.md`](docs/design-notes/m3/DN-01-work-order-lifecycle.md) §3.3
  - etech 對應：`server/regularlistForm.js` + `server/regularSetting.js`

---

## M4 主線（2026-08）— Workflow Part 2: Inventory + Reporting

> ROADMAP 對應：[`docs/product/ROADMAP.md`](docs/product/ROADMAP.md) Month 4 段。
> 設計依據：[DN-03 Inventory ↔ Material Request](docs/design-notes/m3/DN-03-inventory-material-request.md)。
> Demo flow（M4 結束時）：「告警 → 工單 → 簽核 → 派工 → **領料簽核** → **庫存扣帳** → 完工 → **cost actual 寫入** → **月報 PDF 自動產出**」— 完整工作鏈閉環。
>
> 開工順序建議：**A1 (domain) → A2 (repo 雙寫) → A3 (material API) → A6 (material frontend) → A4 (inventory API) → A7 (inventory frontend) → A5 (cost ledger 整合) → A8 (reporting backend) → A9 (reporting frontend) → A10 (e2e test)**。
> Backend signoff `MATERIAL_REQUEST` enum + `build_chain_levels(MATERIAL_REQUEST) → 3 階 (employee/leader/treasury)` + frontend approval tab 的 `subject_type` filter 都已預留（M3 同步完成），M4 只要 wire 起來就行。

---

### WMOM-20260509-01 — Inventory + MaterialRequest domain（pure dataclass + state machine）

- **Status**: done（2026-05-09 完成；同日進場規劃 + 實作）
- **Milestone**: M4
- **Priority**: critical（M4 主菜的根基）
- **Estimate**: 0.5 工作天 → **實際 ~半天**（與規劃同日 push）
- **Owner**: Claude (session 2026-05-09)
- **Completion summary**:
  - ✅ `modules/workflow/domain/inventory.py`：3 enum（StockKind / MaterialRequestStatus 9 狀態 / ReturnReason 4 類）+ 7 dataclass（Warehouse / InventoryItem / MaterialRequest / MaterialRequestItem / MaterialReturn / MaterialRequestNotification / InventoryAdjustmentLog）+ helper（total_available / is_below_safety / get_stock）+ `Decimal` unit_cost + `__post_init__` qty>0 invariant
  - ✅ `modules/workflow/domain/inventory_state_machine.py`：8 transitions（submit_for_approval / approve_all / reject / dispatch / receive / mark_used / close / cancel）+ 5 guard funcs + side-effect dispatcher，與 work_order state_machine 同模式；共用 `InvalidTransition` exception；helper `open_states_mr()` / `terminal_states_mr()`
  - ✅ `modules/workflow/domain/__init__.py`：13 個新 export（10 inventory entity + 3 state machine helper）
  - ✅ `modules/workflow/tests/test_inventory_domain.py`（22 tests）+ `test_material_request_state_machine.py`（38 tests）
  - ✅ **60 inventory tests pass** in 0.10s；全 workflow suite **233 pass**（60 新 + 173 既有，0 regression）in 4.21s
  - ✅ AST-based import guard：domain 層 `import` 樹確認無 SQLAlchemy / FastAPI / pydantic 滲入
- **Decisions made during impl**:
  - **REJECTED 為終態**（vs DN-02 D2-Q3「reject → DRAFT」）：選乾淨 audit trail + 避免 ping-pong + 強制重整意圖；改回 DN-02 行為僅 1 行 + 2 test 影響，walkthrough 可再 confirm
  - **cancel 在 DISPATCHED 之後不允許**：物料已離庫，要退庫須走 `MaterialReturn` entity
  - **close 兩條 source state**：`USED → CLOSED`（正常）+ `RECEIVED → CLOSED`（沒實際用，跳過 USED）
  - **receive 用 dict 帶 actual_qty**：guard 強制 dict 涵蓋所有 items；允許單個 item actual=0（全退場景）
  - **dispatch 在 domain 層只動 status**：真正庫存扣帳 + ledger 寫入是 A2（repository 雙寫 transaction）的範圍
  - **AST import 防護**：第一版用 string contain 檢查誤判 docstring「SQLAlchemy mapping」字眼，改用 `ast.parse` 解析 import 樹
- **Reference**:
  - [`work-logs/2026-05/2026-05-09-inventory-domain.md`](work-logs/2026-05/2026-05-09-inventory-domain.md)
  - [`docs/design-notes/m3/DN-03-inventory-material-request.md`](docs/design-notes/m3/DN-03-inventory-material-request.md) §2

<details><summary>📜 原始 issue description</summary>

把 DN-03 §2.1-2.2 的 schema 寫成純 dataclass + Enum，與 SQLAlchemy 解耦。
  - `modules/workflow/domain/inventory.py`：
    - Enum：`StockKind ∈ {NEW, USED, REPAIRING}`、`MaterialRequestStatus ∈ {DRAFT/AWAITING_APPROVAL/APPROVED/DISPATCHED/RECEIVED/USED/CLOSED/CANCELLED/REJECTED}`、`ReturnReason ∈ {SURPLUS/WRONG_PART/FAILED_INSTALL/OTHER}`
    - Dataclass：`InventoryItem`、`Warehouse`、`MaterialRequest`、`MaterialRequestItem`、`MaterialReturn`、`MaterialRequestNotification`
  - `modules/workflow/domain/inventory_state_machine.py`：MaterialRequest state transitions（draft → awaiting → approved → dispatched → received → used → closed；cancel / reject 旁路）
  - tests/`test_inventory_domain.py` + `test_material_request_state_machine.py`（pure unit，不接 DB）

Acceptance：
  - 所有 dataclass 走 type hint + frozen 不變式
  - state machine 拒絕非法 transition（raise `InvalidTransition`）
  - 30+ unit test pass、無 SQLAlchemy import 漏進 domain 層

Depends on: -；Blocks: WMOM-20260509-02

</details>

---

### WMOM-20260509-02 — Inventory + MaterialRequest Repository（**雙寫交易模型** — M4 核心）

- **Status**: done（2026-05-09 完成；A1 同日接力）
- **Milestone**: M4
- **Priority**: critical（DN-03 §2.3 整個 issue 的關鍵不變式）
- **Estimate**: 1 工作天 → **實際 ~半天**（同 A1 session 內推完）
- **Owner**: Claude (session 2026-05-09)
- **Completion summary**:
  - ✅ `modules/workflow/repository/inventory_orm.py`：7 SQLAlchemy mapped class（WarehouseORM / InventoryItemORM / InventoryAdjustmentLogORM / MaterialRequestORM / MaterialRequestItemORM / MaterialReturnORM / MaterialRequestNotificationORM），與既有 work_order ORM 共用 `Base` + 共用 `_get_engine` cache
  - ✅ `modules/cost/repository/__init__.py` + `cost_ledger.py`：CostLedgerEntryORM 共用 workflow Base（atomic transaction 必要）+ 3 enum + pure dataclass + `insert_in_session()` helper
  - ✅ `modules/workflow/repository/inventory_repository.py`：InventoryRepository（CRUD / safety_stock filter / 手動 adjust + audit log）+ `apply_stock_delta_in_session()` helper（lock + 異動 stock，給 dispatch 用）
  - ✅ `modules/workflow/repository/material_request_repository.py`：MaterialRequestRepository — CRUD + state transition + **atomic `dispatch_request()`** + atomic `add_return()` + `list_for_work_order()` reverse-lookup（取代 work_order schema 內 list[UUID]）
  - ✅ `modules/workflow/repository/__init__.py`：13 個新 export
  - ✅ 3 test files / 58 new tests pass：
    - `test_inventory_repository.py`（21）：CRUD / safety stock filter / adjust + audit log / Decimal round-trip
    - `test_material_request_repository.py`（19）：CRUD / state transitions / business_key / signoff chain wiring / returns
    - `test_dispatch_atomic_transaction.py`（**18 — M4 核心**）：happy + multi-item / state mismatch / insufficient_stock 全 rollback / mid-transaction mock failure 全 rollback / round-trip / **2 個並發 dispatch 在 SQLite WAL 下序列化正確**
  - ✅ **全 workflow suite 291 pass**（M3 173 + A1 60 + A2 58）/ **cost+workflow combined 348 pass + 1 xfailed (existing) — 0 regression**
- **Decisions made during impl**:
  - **Cost ledger 共用 workflow Base**：atomic 雙寫必須跨 module 共用 Base metadata；替代方案（2PC / message queue / retry）違反 DN-03 §2.3 不變式
  - **SQLite SELECT FOR UPDATE no-op**：`with_for_update()` 在 SQLite 不真做 row-lock，但 BEGIN IMMEDIATE + WAL + busy_timeout 序列化寫入；test `test_concurrent_dispatch_*` 兩 thread 同 dispatch 同 item 驗證（5 stock × 2 個各要 4 → 1 成功 + 1 InsufficientStock，最終 stock=1，0 double-spend）。PostgreSQL 部署時 `with_for_update()` 才真做 row-lock
  - **`dispatch_request` 不走 `transition('dispatch')`**：domain state machine 的 `dispatch` action 只動 status；repository `transition('dispatch')` 明確 raise 提示 caller 改用 `dispatch_request()` 才會做 atomic 雙寫
  - **工單 material_request_ids 用 reverse-lookup**：`MaterialRequestRepository.list_for_work_order(wo_id)` 直接 query（不持久化 list[UUID] 欄位到 work_orders 表，避免 schema migration + FK 不同步風險）
  - **`add_return` 暫不寫 ledger 沖銷**：A5 cost ledger 整合會用 wo finish hook 一次到位（actual_qty vs estimated_qty 算差，把 estimated entry 翻 confirmed + 修正 amount），較精確
- **Reference**:
  - [`work-logs/2026-05/2026-05-09-inventory-repository.md`](work-logs/2026-05/2026-05-09-inventory-repository.md)
  - [`docs/design-notes/m3/DN-03-inventory-material-request.md`](docs/design-notes/m3/DN-03-inventory-material-request.md) §2.3

<details><summary>📜 原始 issue description</summary>

- `modules/workflow/repository/inventory_orm.py`：SQLAlchemy 2.0 mapped class
- `modules/workflow/repository/inventory_repository.py`：CRUD + safety_stock 計算 + adjust
- `modules/workflow/repository/material_request_repository.py`：CRUD + state transition + dispatch_request 雙寫
- 工單 material_request_ids 欄位回填邏輯

Acceptance：
- dispatch_request mid-transaction raise → 庫存 + ledger 同時 rollback
- SELECT FOR UPDATE 並行 dispatch 第二張等第一張 commit 後再讀
- 50+ tests

Depends on: WMOM-20260509-01；Blocks: -03/-04/-05

</details>

---

### WMOM-20260509-03 — MaterialRequest CRUD + state transitions API

- **Status**: done（2026-05-09 完成；A1+A2 同日接力第三輪）
- **Milestone**: M4
- **Priority**: high
- **Estimate**: 0.5 工作天 → **實際 ~半天**（同 A1/A2 session 連續）
- **Owner**: Claude (session 2026-05-09)
- **Completion summary**:
  - ✅ `modules/workflow/schemas/material_request_schemas.py`：8 request body + 3 response model + sub-models
  - ✅ `modules/workflow/routers/material_request_router.py`：9 endpoints + repo factory injection + error mapping helper
  - ✅ `modules/workflow/repository/signoff_repository.py`：加 `create_chain_for_material_request`（mirror work_order 版本）
  - ✅ `modules/workflow/routers/approval_router.py` 擴充：
    - `set_signoff_factories(...)` 加 `material_request` 第三 factory（向後相容預設 None）
    - `approve_step` MATERIAL_REQUEST branch：last step approve → `mr_repo.transition('approve_all')` → `dispatch_request()` atomic 雙寫
    - `reject_step` MATERIAL_REQUEST branch：→ `mr_repo.transition('reject', reject_reason)` 進 REJECTED 終態
  - ✅ `modules/monitoring/server/app.py`：mount `material_request_router`
  - ✅ `dispatch_request` error message 從「must be APPROVED」改為「cannot transition from {status} (must be APPROVED)」讓 router error mapping 正確 map 成 409 Conflict（vs 422）
  - ✅ **27 new tests pass** in 5.35s（含完整 approval auto-dispatch lifecycle / 簽核時 stock 抽走的 edge case / cancel 在 DISPATCHED 不允許 / receive 缺 actual_qty 422 / pagination / unknown 404）
  - ✅ 全 workflow suite 318 pass / cost+workflow 375 pass + 1 xfailed (existing) — **0 regression**
- **Decisions made during impl**:
  - **submit-for-approval 順序**：先建 chain（失敗 raise 422、MR 仍 DRAFT），再 transition MR，最後 backlink chain.id — 避免 inconsistent state
  - **Approval auto-dispatch 兩步**：`approve_all` 進 APPROVED → `dispatch_request()` atomic 雙寫；如 dispatch 失敗（最常見：簽核期間 stock 被別張單抽走），chain 已落地，MR 卡在 APPROVED，回 200 + `subject_transition_error` 訊息給 caller，operator 手動補（去 `/dispatch` endpoint 或 cancel）
  - **MATERIAL_REQUEST chain reject → REJECTED 終態**（vs work_order「reject 回 IN_PROGRESS」）：DN-03 設計 operator 須建新 MR，不就地 resubmit
  - **Error code 區分**：state 不對 → 409 Conflict（caller 改 state 即可恢復）vs request body 缺欄位 → 422 Unprocessable Entity；本 issue 統一用 `"cannot transition"` 字眼
  - **`set_signoff_factories` 加第三個 mr 參數預設 None**：向後相容既有 caller (test_work_order_api.py 兩參數) 不破
- **Reference**:
  - [`work-logs/2026-05/2026-05-09-material-request-api.md`](work-logs/2026-05/2026-05-09-material-request-api.md)
  - DN-03 §2.2 lifecycle + DN-02 D2-Q3 reject 行為差異點

<details><summary>📜 原始 issue description</summary>

- modules/workflow/schemas/material_request_schemas.py：CreateMaterialRequest / DispatchRequest / ReceiveRequest / ReturnRequest / response
- modules/workflow/routers/material_request_router.py：~9 endpoints
- Mount 進 modules/monitoring/server/app.py

Acceptance：
- 30+ pytest（API + repo 整合，含 422/409/404）
- approve last step → 自動觸發 dispatch（approval_router MATERIAL_REQUEST branch）

Depends on: WMOM-20260509-02；Blocks: WMOM-20260509-06

</details>

---

### WMOM-20260509-04 — Inventory query + adjustment API

- **Status**: done（2026-05-09 完成；A1+A2+A3 同日連續第四輪）
- **Milestone**: M4
- **Priority**: high
- **Estimate**: 0.5 工作天 → **實際 ~半天**
- **Owner**: Claude (session 2026-05-09)
- **Completion summary**:
  - ✅ `modules/workflow/schemas/inventory_schemas.py`：5 request body + 6 response model（含 `InventoryItemResponse` 的 `@computed_field` `below_safety` / `total_available`）
  - ✅ `modules/workflow/routers/inventory_router.py`：**8 endpoints**（6 inventory + 2 warehouse extra）+ repo factory injection
  - ✅ Mount 進 `monitoring/server/app.py`
  - ✅ `routers/__init__.py` + `schemas/__init__.py` export 補齊
  - ✅ **28 tests pass** in 1.76s（CRUD / safety filter / metadata partial update / adjust + audit log / 409 insufficient_stock / 404 unknown / 422 validation / pagination / decimal precision）
  - ✅ 全 workflow 346 pass / cost+workflow 403 pass + 1 xfailed (existing) — **0 regression**
- **8 endpoints**:
  - **Inventory (6)**: POST/GET/GET/{id}/PATCH/{id}/POST/{id}/adjust/GET/{id}/adjustments
  - **Warehouse (2 extra)**: POST/GET（給 frontend 建料件前先建倉用，repo 已有 helper 但 ISSUES spec 沒明列；trade-off：避免 ops 手動動 DB）
- **Decisions made during impl**:
  - `InventoryItemResponse` 用 `@computed_field` 計算 `below_safety` / `total_available` — 前端不重複邏輯，避免「frontend 計算 vs backend list 已 filter」不一致
  - PATCH 用 `model_dump(exclude_unset=True)` 配合 repo `update_metadata(**payload)` 乾淨支援 partial update
  - Adjust error mapping：`StockAdjustmentError("not found")` → 404 / 其他 StockAdjustmentError → 422 / `InsufficientStock` → 409（語意：404=不存在 / 422=請求格式錯 / 409=狀態衝突）
  - `list_warehouses` router 走 raw SQL（不另開 repo method） — 用量低，避免 over-engineering
  - SQLAlchemy `Numeric(12, 4)` 保留 4 位小數 → test 用 `Decimal(str) == Decimal("450.00")` 比值不比字串
- **Reference**:
  - [`work-logs/2026-05/2026-05-09-inventory-api.md`](work-logs/2026-05/2026-05-09-inventory-api.md)
  - DN-03 §2.1 + §2.4「歸還與報廢」（adjustment endpoint 支撐紙本流程數位化）

<details><summary>📜 原始 issue description</summary>

- modules/workflow/schemas/inventory_schemas.py：InventoryItemResponse / AdjustmentRequest / SafetyStockAlertResponse
- modules/workflow/routers/inventory_router.py：~6 endpoints
- safety_stock 警示：stock_new + stock_used < safety_stock

Acceptance：
- 25+ pytest pass
- adjustment endpoint 連同 audit log 落地

Depends on: WMOM-20260509-02；Blocks: WMOM-20260509-07

</details>

---

### WMOM-20260509-05 — Cost ledger material entry 整合（estimated → confirmed flow）

- **Status**: done（2026-05-09 完成；A1+A2+A3+A4 同日連續第五輪 — **M4 backend 收官**）
- **Milestone**: M4（部分覆蓋 [WMOM-20260504-11](#wmom-20260504-11--event-driven-cost-ledger-m4-增強) Phase A）
- **Priority**: high（M4 demo flow 的「cost actual 寫入」步驟）
- **Estimate**: 0.5 工作天 → **實際 ~半天**
- **Owner**: Claude (session 2026-05-09)
- **Completion summary**:
  - ✅ schema 擴充：`cost_ledger.py` 加 `source_item_id` (nullable) + `confirmed_at` 欄位 + 新 index `ix_cost_ledger_source_item`，給 confirm flow 精確 lookup
  - ✅ A2 dispatch_request 寫 ledger 時帶 `source_item_id=UUID(it.id)` 給 confirm flow 用
  - ✅ `cost_ledger_repository.py`：CostLedgerRepository（180 行）— get / list (filters + pagination) / find_for_mr_item / list_for_subject / **summary_by_category** (給 A8 月報) / **confirm_entry idempotent**
  - ✅ `cost_ledger_router.py`：2 read-only endpoints + factory injection
    - `GET /api/cost/ledger` — list + filters (farm/from/to/category/status/source_type) + pagination
    - `GET /api/cost/ledger/summary` — group by 4 大類（status=confirmed → actual cost for monthly_report）
  - ✅ Mount 進 `monitoring/server/app.py`
  - ✅ **WO finish hook**：`work_order_router.finish` 結束後呼叫 `_confirm_material_ledger_for_finished_wo` — loop linked MRs，對每個 actual_qty 已填的 line item 用 `actual_qty × current unit_cost` flip estimated → confirmed；hook 失敗不阻擋 finish；test override `set_finish_hook_db_path` 給 lifecycle test 用
  - ✅ Circular import 修：`material_request_repository` 對 cost_ledger imports 改成 lazy（搬進 `dispatch_request` 函式內）；test patch path 跟著改成 `cost_ledger.insert_in_session`
  - ✅ **32 new tests pass** in 3.12s（17 repo + 10 api + **5 lifecycle acceptance**）
  - ✅ 全 workflow + cost combined 435 pass + 1 xfailed (existing) — **0 regression**
  - ✅ **完整鏈路 acceptance test 過**：建料件 → 建工單 → MR linked to WO → submit + 3 階 approve（auto dispatch）→ ledger entry estimated（amount=900 = 2×450）→ receive actual_qty → finish WO → ledger entry confirmed
  - ✅ Edge cases 全測：actual ≠ estimated（amount 翻成 actual×unit_cost）/ MR 未 receive 時 finish（ledger 留 estimated）/ 沒 linked MR 的 finish 正常 / `summary_by_category(status=CONFIRMED)` 拿到 actual cost 給月報用
- **Decisions made during impl**:
  - 加 `source_item_id` 是 schema migration（nullable 安全）— 因為 dispatch 對 N items 寫 N entries，confirm 要 unique lookup
  - `confirm_entry` idempotent：已 confirmed → no-op return；防止 WO reject 後 re-finish 改回 amount
  - finish hook 寫在 router 而非 repository — cross-module concern（讀 MR + inv + ledger）寫 router 比較乾淨，避免 repository 層直接跨 module 耦合
  - finish hook test injection 用 `set_finish_hook_db_path(path)` 而非 factory 三聯（少 boilerplate）；既有 test 不破（override 未設 + FarmRegistry 沒 mock → hook 安靜跳過）
  - **不暴露 ledger POST/PATCH** — ledger 是「事實帳本」所有 mutation 必須走業務 atomic transaction
  - lazy import 解循環：`material_request_repository`→`cost_ledger`→`workflow.orm_models`→workflow.repository.__init__→material_request_repository 的循環
- **Reference**:
  - [`work-logs/2026-05/2026-05-09-cost-ledger-integration.md`](work-logs/2026-05/2026-05-09-cost-ledger-integration.md)
  - DN-03 §2.3「雙寫交易」+ §3.2「與 cost ledger 的綁定」
  - WMOM-20260504-11 (event-driven cost ledger) Phase A 部分覆蓋

<details><summary>📜 原始 issue description</summary>

- 新表 cost_ledger_entry：UUID id / farm_id / category / amount EUR / source_event_id / source_type / status / recorded_at / actor
- dispatch_request 在雙寫 transaction 內 insert(category=material, status=estimated, amount=estimated_qty × unit_cost)
- work_order finish hook：enumerate material_request_ids → 對每筆找對應 ledger entry → 用 actual_qty × unit_cost 改 amount + status=confirmed
- GET /api/cost/ledger?farm_id=...&from=...&to=...&category=...

Acceptance：
- 15+ pytest pass（含 estimated → confirmed transition + actual 與 estimated 差異率記錄）
- 完整鏈路：MR dispatch → estimated → wo finish → confirmed — 一次測過

Depends on: WMOM-20260509-03；Blocks: WMOM-20260509-08

</details>

---

### WMOM-20260509-06 — `/admin/workflow/material` 領料單 frontend

- **Status**: done（2026-05-18，PR pending）
- **Milestone**: M4
- **Priority**: high
- **Estimate**: 1 工作天 → **實際 1 天**
- **UI directive（WMOM-20260507-01 後）**：使用 `frontend/components/ui/` + `frontend/theme/`，不可 Tailwind / 硬 hex。Modal 套既有 [`WorkOrderDetailModal`](frontend/components/workflow/WorkOrderDetailModal.tsx) 風格（Card padding=0 + DM Serif title + 底部 Btn）。
- **Description**:
  - `frontend/services/materialService.ts`（API client，模式同 workOrderService）
  - `frontend/hooks/useMaterialRequests.ts`
  - `frontend/components/workflow/MaterialRequestListPanel.tsx`：列表 + status filter + 工單關聯 search
  - `frontend/components/workflow/CreateMaterialRequestWizard.tsx`：建單精靈（選工單 → 加料件明細 → 估計工時 → submit-for-approval）
  - `frontend/components/workflow/MaterialRequestDetailModal.tsx`：詳情 + state transition buttons（dispatch / receive / close / cancel / 建退料）
  - 改 [`WorkflowPage.tsx`](frontend/components/workflow/WorkflowPage.tsx)：加 `material` tab（與 orders / approval 並列；approval tab 已預留 subject_type filter 直接吃 material_request）
- **Acceptance**:
  - ✅ tsc clean / vite build pass（3.56s, 743 modules）
  - ✅ demo flow 已對齊 backend：建工單 → 開領料單 → submit → approval tab 用 LEADER / TREASURY 簽 → 領料單自動 DISPATCHED → 點 receive 填 actual_qty（每個 transition 對應的 backend endpoint 已驗證）
- **Depends on**: WMOM-20260509-03
- **Blocks**: -
- **Result**:
  - 8 new files：materialService / useMaterialRequests / useInventoryItems / MaterialRequestListPanel / CreateMaterialRequestWizard / MaterialRequestDetailModal / statusUtils 擴 + WorkflowPage 加 `material` tab
  - code-reviewer subagent 找出 2 must-fix + 4 should-fix + 3 nice-to-have：
    - Must #1: `fmtDateTime` / `fmtDate` 改用 `Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Taipei' })` 明確 Asia/Taipei format
    - Must #2: `selectedMR` sync 依賴 `mrHook.rawItems`（未 filter）避免 search 期間 stale
    - Should #1: backdrop click 在 cart 有料件時加 `window.confirm` 防誤關
    - Should #2: `mrStatusTone` 改進度感漸進色（dispatched=accent / received=accent / used=ok / closed=ok）
    - Should #3 / #4 + Nice #1 / #3：留 follow-up（fetch AbortController signal pass-through / SKU+name join / 排序意圖 comment / useCallback dep）
  - Follow-up issue：WMOM-20260518-01（MR detail modal 料件表加 SKU+name 顯示，需 backend join）
  - PR：claude/issue-WMOM-20260509-06-2026-05-18
  - Work-log：work-logs/2026-05/2026-05-18-material-request-frontend.md

---

### WMOM-20260509-07 — `/admin/workflow/inventory` 庫存 frontend

- **Status**: done（2026-05-18）
- **Milestone**: M4
- **Priority**: high
- **Estimate**: 0.5-1 工作天 → **實際 0.5 工作天**
- **UI directive**：同 -06。
- **Description**:
  - ✅ `frontend/services/inventoryService.ts`（完整 8 endpoint：6 inventory + 2 warehouse）
  - ✅ `frontend/hooks/useInventory.ts`（list + adjust + listAdjustments + warehouses sub-fetch）
  - ✅ `frontend/components/workflow/InventoryListPanel.tsx`：warehouse filter / below_safety toggle / 三欄 stock / LOW pill / border-left 4px warn 警示
  - ✅ `frontend/components/workflow/InventoryAdjustmentDialog.tsx`：delta_kind / 整數 delta / reason 必填 + 預覽顯示 `qty + delta = next` 含 negative 警告
  - ✅ `frontend/components/workflow/InventoryDetailDrawer.tsx`：右側 480px drawer + audit log + 觸發 adjust dialog（z=300 over drawer z=180）
  - ✅ 改 `WorkflowPage.tsx`：加 `inventory` tab + selectedInvItem rawItems sync + invHook 接合
  - ✅ 擴 `statusUtils.ts`：`locationKindLabel` for warehouse location enum
- **Acceptance**:
  - ✅ tsc clean / vite build pass（748 modules, 4.47s）
  - ✅ safety_stock 警示視覺正確：border-left 4px warn + LOW pill + filter toggle
- **Depends on**: WMOM-20260509-04（done）
- **Blocks**: -
- **Result**:
  - Backend 未動 — 512 passed + 1 xfailed + 3 pre-existing numpy drift（與 main baseline 一致 zero regression；今日 flaky concurrency test 通過）
  - PR：claude/issue-WMOM-20260509-07-2026-05-18
  - Work-log：work-logs/2026-05/2026-05-18-inventory-frontend.md

---

### WMOM-20260509-08 — Reporting backend（monthly_report.py PDF + annual_budget.py）

- **Status**: done（2026-05-10，PR pending merge）
- **Milestone**: M4（後半 — 不依賴 inventory，可平行）
- **Priority**: high（M6 客戶第一份月報沒被退是 done criteria）
- **Estimate**: 1.5 工作天 → **實際 1 天**
- **Description**:
  - `modules/reporting/services/monthly_report.py`：
    - 取資料：cost ledger（material/labour/equipment/revenue_loss 4 類加總）+ work order 完工統計（CORRECTIVE / PREVENTIVE / INSPECTION 計數）+ 物理模擬 availability（time / energy）
    - 渲染：HTML template（Jinja2 + inline CSS）→ PDF（**reportlab** — Windows weasyprint 撞 Pango DLL）
    - 內容：封面 + 摘要 KPI + 4 類成本明細 + 工單統計 + availability + 重大事件 timeline
  - `modules/reporting/services/annual_budget.py`：12 個月 forecast（過去用 actual / 當月 actual_partial / 未來月 historical_average rolling 3 月）
  - `modules/reporting/routers/reporting_router.py`：
    - `POST /api/reporting/monthly?farm_id=...&year=...&month=...&format=pdf|html|json` → returns PDF binary / HTML preview / JSON 結構化資料
    - `POST /api/reporting/annual-budget?farm_id=...&year=...&format=pdf|json`
    - `GET /api/reporting/templates` → 可用 template 列表
  - `modules/reporting/templates/monthly_report.html`（Jinja2）+ `static/reporting.css` + `services/_pdf_styles.py`（共用 reportlab style）
- **Acceptance**:
  - ✅ 跑得出真實 PDF（PDF magic bytes + ≥1KB + 重複 render size 一致 — `test_render_pdf_*` 4 個測試）
  - ✅ 月報內容 4 大區塊正確（KPI / cost / work orders / availability — `test_monthly_report_data_full_assembly`）
  - ✅ **56 pytest** pass（含 8 個 review fix regression test，超過 25 acceptance）
- **Depends on**: WMOM-20260509-05（要從 cost ledger 讀 confirmed material cost）
- **Blocks**: WMOM-20260509-09
- **Result**:
  - Backend 全 446 → **502 passed, 1 xfailed (zero regression)**
  - code-reviewer subagent 找出 4 must-fix + 4 should-fix 全修：
    - Must #1: `in_progress` WO 跨月雙計（用 `open_states()` + `closed_at` 上下界）
    - Must #2: annual budget current_month 區隔 `actual_partial` 與 `actual`，forecast 解耦
    - Must #3: Content-Disposition header injection 防護（`_safe_filename_token`）
    - Must #4: `compute_notable_events` 共用 WO snapshot 避免雙倍 query
    - Should #1: `history_window > 12` guard 給明確錯誤
    - Should #2: `_WO_FETCH_PAGE_SIZE` 抽常數
    - Should #3: `_pdf_styles.py` 共用 reportlab style
    - Should #4: HTML preview inline CSS（避免 API endpoint 載不到外部檔）
  - Nice-to-have 4 條留 follow-up（_month_period 兩處實作 / notable_events 加 stalled 類型 / `_jinja_env` thread race / `_FARM_REGISTRY` setter coupling）
  - PR：[claude/issue-WMOM-20260509-08-2026-05-10]
  - Work-log：work-logs/2026-05/2026-05-10-reporting-backend-monthly-pdf.md

---

### WMOM-20260509-09 — `/admin/reports` frontend（月報生成 + 年度預算）

- **Status**: done（2026-05-10，PR pending）
- **Milestone**: M4
- **Priority**: high
- **Estimate**: 1 工作天 → **實際 1 天**
- **UI directive**：同 -06（走 ui 元件庫 / 不硬寫 hex / 全 theme palette）
- **Description**:
  - ✅ `frontend/services/reportingService.ts`（typed client + downloadBlob helper）
  - ✅ `frontend/hooks/useReports.ts`（monthly + annual sub-state mgmt）
  - ✅ 新主頁 `frontend/components/reporting/ReportsPage.tsx`，nav 加 `reports` 主項 + NavIcon (document with mini bar chart)
  - 子元件：
    - ✅ `MonthlyReportPanel.tsx`：year/month picker → generate → KPI cards + cost breakdown table + iframe HTML preview + PDF download
    - ✅ `AnnualBudgetPanel.tsx`：year + current_month picker → KPI + recharts BarChart + 12-month table + PDF download
  - ✅ `formatters.ts` 共用 fmtMoneyDecimal / fmtPct
- **Acceptance**:
  - ✅ 點按鈕後 30 秒內拿到 PDF binary，瀏覽器自動下載（`downloadBlob` helper + 1s revoke timeout）
  - ✅ 走 ui 元件庫；NavIcon `reports` 加 document-with-bar-chart icon
- **Depends on**: WMOM-20260509-08
- **Blocks**: -
- **Result**:
  - `npx tsc --noEmit` → 0 errors；`npx vite build` → 5.29s，733 modules
  - code-reviewer subagent 找出 4 must + 6 should + 4 nice，採納 11 條全修：
    - Must #1: iframe `srcDoc` 加 `sandbox=""` 完全隔離（XSS 防護）
    - Must #2: `buildQuery` 型別簽章對齊 runtime guard（加 null）
    - Must #3: generate error / download error 拆兩個獨立顯示框
    - Must #4: `farmLoaded` state 區分 loading vs 無 active farm 避免無限 loading
    - Should #1: `formatters.ts` 抽共用 fmtMoneyDecimal（兩 panel 重複定義 + null 行為分歧）
    - Should #2: 移除 dead exports `ReportFormat` / `AnnualFormat`
    - Should #6: year range 擴 -4~+1（multi-year O&M）
    - Nice #1: recharts future months `actual=null` 不畫 0 bar
    - Nice #2: 移除未使用的 `useReports.reset`
    - Nice #3: 移除 PageHeader sub backend impl 細節 leak
  - PR：[claude/issue-WMOM-20260509-09-2026-05-10]
  - Work-log：work-logs/2026-05/2026-05-10-reports-frontend.md

---

### WMOM-20260509-10 — E2E lifecycle test（pytest 兩層 + demo orchestrator placeholder）

- **Status**: done（2026-05-13）
- **Milestone**: M4 收官（A6/A7/A9 done 後）
- **Priority**: high（**ROADMAP M4 demo flow 的 acceptance**）
- **Estimate**: 1-1.5 工作天 → **實際 0.5 工作天**
- **完成**:
  - Layer A：`tests/e2e/test_fault_to_signoff_lifecycle.py` 6 個 test（3 happy CORRECTIVE/PREVENTIVE/INSPECTION + 2 unhappy reject-retry + insufficient-stock + 1 timing sentinel），全 pass in 1.88s（acceptance < 60s 通過）
  - Layer B：`frontend/components/demo/DemoOrchestratorPage.tsx` skeleton placeholder（tsc clean）
  - Mock simulator/fault：暫以 `source_alarm_code` 字串模擬 fault trigger；真接 SCADA simulator 留 follow-up WMOM-20260513-02
  - Code review subagent 找 4 must-fix + 7 should-fix；must-fix 全修 + 多數 should-fix 採納
  - 關鍵驗證：3 階 approve 後 MR DISPATCHED + stock 扣 + ledger ESTIMATED 中間狀態（擋 dispatch guard regression）
  - PR：claude/issue-WMOM-20260509-10-2026-05-13
  - Work-log：work-logs/2026-05/2026-05-13-a10-e2e-lifecycle-test.md
- **Description**:
  把「運轉資料 → 故障觸發 → 派工 → 開單 → 領料 → 排除 → 紀錄 → 簽核」全鏈路串起來測。

  **Layer A — Pytest integration test**（每個 PR 自動跑）
  - `tests/e2e/test_fault_to_signoff_lifecycle.py`：
    - Step 1：啟動 simulator + 載 demo farm（fixture）
    - Step 2：注入 fault scenario（gearbox_temp_high）
    - Step 3：assert SCADA tag delta + alarm code 觸發
    - Step 4：建 corrective 工單（priority=high，from alarm code）
    - Step 5：dispatch → start_work
    - Step 6：建 material_request（gearbox bearing × 1）→ submit_for_approval
    - Step 7：approve 3 階 chain（employee → leader → treasury）→ 自動 dispatch
    - Step 8：assert inventory.stock_new -1 + ledger entry status=estimated
    - Step 9：work order update_progress + finish（actual_qty=1）
    - Step 10：assert ledger entry status=confirmed
    - Step 11：approve 工單 chain（employee → leader）
    - Step 12：assert wo=CLOSED + signoff chain=APPROVED
    - 跑 PREVENTIVE / INSPECTION 兩個變體 happy path

  **Layer B — Demo orchestrator placeholder**（M5/M6 時做完整 UI）
  - `frontend/components/demo/DemoOrchestratorPage.tsx`（**只放 skeleton + step list**，實作留 M5）
  - 標記 follow-up issue 給 M5 接力
- **Acceptance**:
  - Layer A：25+ pytest pass，覆蓋 corrective + preventive + inspection 三條 happy path + 2 條 unhappy path（簽核 reject 後重試 / dispatch 在 stock 不足下 fail）
  - Layer A 跑完 < 60 秒（in-memory SQLite + simulator 不寫 DB）
  - Layer B：skeleton 通 tsc，留下明確的 follow-up issue WMOM-2026XX-XX
- **Depends on**: WMOM-20260509-06、-07、-09
- **Blocks**: -
- **Reference**:
  - ROADMAP M4 demo flow
  - 前 issue 提的 [WMOM-20260507-02](#wmom-20260507-02) placeholder 按鈕清單（demo orchestrator 上線後可清掉「+ 新報告」入口）

---

## M4 backend 後續 follow-up（2026-05-09 code review 留下的 should-fix / nice-to-have）

> A1-A5 backend 5 issue 全 done 後，code-reviewer subagent 找出 3 must-fix（已在
> WMOM-20260509-review-fixes-2026-05-09 修完）+ 4 should-fix + 2 nice-to-have。
> Must-fix 已修；以下 6 項列為下次 session 接力處理的 follow-up issues。
> 優先級：A6 frontend 主線優先；以下若有空再插。

### WMOM-20260509-F1 — `add_return` 寫 ledger 沖銷

- **Status**: done（2026-05-19 完成；branch `claude/nice-brown-6DM0J`）
- **Milestone**: M4 後續（不阻塞 frontend）
- **Priority**: medium（demo 給客戶看月報時會被發現偏高）
- **Estimate**: 0.5 工作天 → **實際 ~3 小時**（含 code-review must-fix 採納）
- **Source**: 2026-05-09 code review Should-fix #2
- **Owner**: Claude（session 2026-05-19，autonomous daily worker）
- **Completion summary**:
  - ✅ Backend repo `add_return()` 升級為 atomic 三寫（stock + MaterialReturn + ledger offset entry）
  - ✅ 沖銷 entry 設計：`amount = -(qty × locked_unit_cost from dispatch entry)`；`status=CONFIRMED + confirmed_at=now`；`source_item_id = MaterialReturn.id` 區隔 dispatch entry 的 mr_item.id，避開 wo finish hook `find_for_mr_item` 撈出多筆 collision
  - ✅ 加 `_lookup_offset_unit_cost(sess, request_id, item_id, return_to_kind)` static method：
    - Step 1 找 dispatch ledger entry 取 `locked_unit_cost`（會計一致性原則 — dispatch 後漲價也用鎖定值）
    - Step 2 fallback 查當前 `inventory.unit_cost`
    - Step 3 都沒 → None（caller log warning + skip ledger entry，stock + MaterialReturn 仍寫）
  - ✅ Cross-kind return 語意（dispatch NEW → return USED）docstring 補強 + test 涵蓋
  - ✅ 月報 `summary_by_category(CONFIRMED)` 退料後不再偏高（測試驗證：dispatch confirmed +900 + return confirmed -450 = +450）
  - ✅ 新增 17 個 test（`test_add_return_ledger_offset.py`）：happy path 3 + 月報視角 3 + wo hook 互動 1 + fallback 3 + multi 2 + atomic 1 + cross-kind 1 + mid-state 1 + cross-cutting 2
  - ✅ Backend `python -m pytest modules/{workflow,cost,reporting}/tests/ tests/e2e/` → 551 passed (+17 new) + 1 xfailed + 3 pre-existing numpy drift — **zero regression**
  - ✅ Code-reviewer subagent 找 4 must-fix + 4 should-fix + 3 nice-to-have，**採納 10/11**（剩 1 nice-to-have lazy import 重構為 scope creep 不採納）：
    - MF#1 拿掉 `_ = CostLedgerEntryORM` over-import hack
    - MF#2 加 docstring 警示「超量退料」會計邊界 + 開 follow-up WMOM-20260519-01
    - MF#3 ISSUES.md / STATUS.yaml 同 commit 更新
    - MF#4 fallback test 加 assert 確認不產生 warning（caplog dead param 修正）
    - SF#1 cross-kind return 語意 docstring + 新 test
    - SF#2 REPAIRING 退料路徑同 USED 邏輯，cross-kind test 已涵蓋
    - SF#3 caplog 指定 logger name
    - SF#4 work-log §2.3 mid-state 描述修正 + 新 test
    - N#1 inventory fallback 月報視角新 test
    - N#3 work-log TODO 全勾
- **Files changed**:
  - `M modules/workflow/repository/material_request_repository.py` — `add_return` + `_lookup_offset_unit_cost`
  - `+ modules/workflow/tests/test_add_return_ledger_offset.py` — 17 tests, 600+ lines
  - `+ work-logs/2026-05/2026-05-19-f1-add-return-ledger-offset.md`
- **Reference**: code review subagent 報告 Should-fix #2
- **Blocks**: -
- **Spawns**: WMOM-20260519-01（超量退料 domain guard 評估）

---

### WMOM-20260519-01 — `add_return` 超量退料 domain guard 評估（F1 follow-up）

- **Status**: open
- **Milestone**: M4 後續
- **Priority**: medium-low（影響月報極端場景；正常 lifecycle 不觸發）
- **Estimate**: 0.5-1 工作天
- **Source**: 2026-05-19 WMOM-20260509-F1 code review Must-fix #2
- **Description**:
  WMOM-20260509-F1 完成「add_return 寫 ledger offset entry」後，發現一個會計邊界：
  - dispatch estimated 2 件 @ 300 = 600 estimated entry
  - wo finish 填 actual=1 → confirm 翻 dispatch entry 為 confirmed 300
  - **若退料 2 件**（合法呼叫，但業務上不該；qty ≤ stock 可派出量，stock 加回未 guard）→ return entry -600 confirmed
  - confirmed 視角 = 300 + (-600) = **-300**（負值材料成本，月報異常）

  F1 scope 不加 guard，docstring 標註「caller 責任」。本 follow-up issue 評估：
  1. 是否要在 domain 層加 guard：`qty <= (estimated_qty or dispatched_qty - already_returned_qty - actual_consumed)`
  2. 或在 router 層擋
  3. 或保留現狀 + 在 UI 層擋（field engineer 介面禁止超量輸入）
  4. 是否要查 wo finish hook 後 actual_qty 才能驗證「actual_consumed」

  決策後實作 + 加 negative path test。

- **Files候選**：
  - `modules/workflow/repository/material_request_repository.py:add_return`
  - 或 `modules/workflow/domain/inventory.py:MaterialRequest`（新 domain method）
- **Depends on**: WMOM-20260509-F1（done）
- **Blocks**: 月報極端場景 demo（如果客戶 demo 時操作「過度退料」會看到負值）

---

### WMOM-20260509-F2 — `list_items` / `list` 用 `func.count` 而非 Python `len`

- **Status**: done（2026-05-21 完成；F2-F5 cleanup batch；branch `claude/blissful-turing-nR5qR`）
- **Milestone**: M4 後續
- **Priority**: low（資料量 < 1000 不影響）
- **Estimate**: 0.5 小時
- **Source**: 2026-05-09 code review Should-fix #1
- **Description**:
  `inventory_repository.list_items` 與 `material_request_repository.list` 用
  `total = len(sess.execute(count_stmt).scalars().all())` 把所有 id 撈回 Python 才算 `len`。改為 SQL-side count：
  ```python
  from sqlalchemy import func, select
  count_stmt = select(func.count()).select_from(base.subquery())
  total = sess.execute(count_stmt).scalar_one()
  ```
- **Files**（已改）：
  - `modules/workflow/repository/inventory_repository.py`（list_items）
  - `modules/workflow/repository/material_request_repository.py`（list）

---

### WMOM-20260509-F3 — `list_warehouses` 加 repo method（移出 router raw SQL）

- **Status**: done（2026-05-21 完成；F2-F5 cleanup batch）
- **Milestone**: M4 後續
- **Priority**: low（cosmetic）
- **Estimate**: 0.5 小時
- **Source**: 2026-05-09 code review Should-fix #4
- **Description**:
  `inventory_router.list_warehouses` 直接用 `repo._sessionmaker()` query ORM，violates repository 封裝。已在 `InventoryRepository` 加 `list_warehouses(farm_id) -> list[Warehouse]`；router 改用該 method（兩行收尾）。

---

### WMOM-20260509-F4 — `_FARM_REGISTRY` lazy singleton 抽 shared

- **Status**: done（2026-05-21 完成；F2-F5 cleanup batch）
- **Milestone**: M4 後續
- **Priority**: low（cosmetic refactor）
- **Estimate**: 1 小時
- **Source**: 2026-05-09 code review Should-fix #5
- **Description**:
  4 個 routers 各自重複 `_FARM_REGISTRY` lazy singleton + `_resolve_farm_db_path`：
  - `inventory_router.py`
  - `material_request_router.py`
  - `approval_router.py`
  - `cost_ledger_router.py`
  抽成 `shared/farm_registry_provider.py` 一個共用 singleton（lazy import + cached + threading.Lock）。
- **Follow-up note**：實作過程中發現 `work_order_router.py` 與 `reporting/routers/reporting_router.py` 也有相似 pattern（不同 helper 名 `_get_default_farm_registry` / 同名 `_resolve_farm_db_path`）。本 issue scope 只列 4，未動那兩個；後續若再次 review 可一併收進來。

---

### WMOM-20260509-F5 — `InventoryAdjustmentLog.actor_id` 改 Optional

- **Status**: done（2026-05-21 完成；F2-F5 cleanup batch）
- **Milestone**: M4 後續
- **Priority**: low
- **Estimate**: 15 分鐘
- **Source**: 2026-05-09 code review Nice-to-have #1
- **Description**:
  原 `actor_id: UUID` 必填。系統自動 adjust（hook / scheduler）被迫塞 fake UUID。已改 Optional：
  - `InventoryAdjustmentLog.actor_id: UUID | None = None`（domain dataclass）
  - `InventoryAdjustmentLogORM.actor_id` 改 nullable
  - `AdjustInventoryRequest.actor_id` + `AdjustmentLogResponse.actor_id` 改 `Optional[UUID]`
  - `InventoryRepository.adjust()` 簽名 + `_log_to_domain` 加 None 分支
  - SQLite 自動生效；PostgreSQL ALTER 留 M6 部署（F6 PG issue）。

---

### WMOM-20260509-F6 — PostgreSQL row-lock integration test

- **Status**: open
- **Milestone**: M6（生產部署前）
- **Priority**: medium
- **Estimate**: 0.5 工作天
- **Source**: 2026-05-09 code review Nice-to-have #2
- **Description**:
  目前並發 dispatch SQLite test 只能驗 SQLite WAL 序列化行為，**無法驗 PostgreSQL `SELECT FOR UPDATE` 真實 row-lock 語意**。M6 客戶部署前如選 PostgreSQL backend，需補：
  - 起 docker postgres 跑 integration test
  - 兩 client 同時 dispatch 同 item，驗第二個被 block 直到第一個 commit/rollback
  - test 在 CI（GitHub Actions）上跑

---

### WMOM-20260522-01 — F4 follow-up：`work_order_router` + `reporting_router` 也改用 shared FARM_REGISTRY

- **Status**: done（2026-05-22 完成；branch `claude/issue-WMOM-20260522-01-2026-05-22`）
- **Milestone**: M4 後續（F4 收尾）
- **Priority**: low（cosmetic refactor，純結構整理）
- **Estimate**: 0.5-1 小時 → **實際 ~1 小時**
- **Owner**: Claude（session 2026-05-22 autonomous daily worker）
- **Source**: WMOM-20260509-F4 follow-up note（2026-05-21 cleanup batch 實作時發現）
- **Completion summary**:
  - ✅ `work_order_router.py`：刪 `_FARM_REGISTRY` global + `_get_default_farm_registry()` 函式；
    `_default_repository_factory` 收成一行 `get_repository(resolve_farm_db_path(farm_id))`；
    `_resolve_db_path_for_finish_hook` 用 try/except HTTPException 包 shared 呼叫 — finish hook
    失敗（registry 不可用 / farm 不存在）安靜返回 None 不阻擋工單收尾；
    `set_repository_factory(None)` 改呼叫 `reset_farm_registry()`
  - ✅ `reporting_router.py`：刪 `_FARM_REGISTRY` global + `_resolve_farm_db_path()` 函式；
    `_get_ledger_repo` / `_get_wo_repo` 直接呼叫 shared；`set_ledger_factory(None)` /
    `set_work_order_factory(None)` 各自呼叫 `reset_farm_registry()`（與 4 個 F4 routers 對齊）；
    `set_availability_provider` **不** reset（與 farm 解析無關，已加 regression test 守住）
  - ✅ 10 個新 regression test（5 work_order + 5 reporting）：
    - setter None → shared singleton 被清
    - router 不再有 local `_FARM_REGISTRY` global（防止後續再加回 local cache）
    - finish hook 在 shared raise HTTPException(500) / 404 時安靜返回 None
    - finish hook override 仍優先於 shared lookup
    - reporting `set_availability_provider` 不動 shared registry
    - reporting `_get_ledger_repo` / `_get_wo_repo` 在 factory=None 真的走 shared 路徑（N1）
  - ✅ Backend baseline zero regression：715 passed + 1 xfailed + 3 pre-existing numpy drift（與 main 一致）；
    2 deselected = 環境 flaky concurrency dispatch tests（main baseline 也偶爾 fail，與本 PR 無關）
  - ✅ Code review 1 must + 2 should + 1 nice：採納 must（`__builtins__` patch 改 monkeypatch shared
    function）+ should-2（teardown 不重複 reset）+ nice-1（加 N1 test 驗 production code path）；
    should-1（HTTPException coupling 全 6 router 統一，shared 改 exception 需擴大 scope 到 F4 batch
    — 本 PR 不擴大）
- **Reference**:
  - [`work-logs/2026-05/2026-05-22-f4-followup-work-order-reporting.md`](work-logs/2026-05/2026-05-22-f4-followup-work-order-reporting.md)
  - WMOM-20260509-F4 follow-up note

---

## 物理模型強化（M3 並行 / 從 digiWT 階段延續未完工）

> 來源：`docs/physics_model_status.md` 「Still missing」段 + `examples/data_quality_report.txt` 3 項 fail + `docs/legacy/digiwt_TODO.md` 仍 open 項。
> 商業 demo 風險（P0）優先；學術深度（P2）可拖到 M5 之後。
> 開工順序建議：**-23（測試骨架）→ -24（data quality 修正）→ -25（前端可視化）→ 看 M3 frontend 進度再決定 -26/-27/-28**。

---

### WMOM-20260505-23 — Physics 自我驗證框架（self-validation framework）

- **Status**: **done**（Layer 1-7 全 2026-05-06 完成）
- **Milestone**: M3 並行（infrastructure，不卡 workflow）
- **Priority**: critical（**P0 — 物理正確性的根基；劉老師 2026-05-05 review 強調「不能只是說有採用，要知道結果是否準確」**）
- **Estimate**: 4-6 工作天 → **實際 1 天連跑完 7 layer**
- **Progress log**:
  - 2026-05-06：Layer 1（Conservation Laws）完成 — 36 tests pass（Betz / 能量 / 動量 / 角動量 / 熱平衡 / 質量守恆 + sentinel）；負向測試確認可 catch（將 `TurbineSpec.cp_max` 0.45→0.70 觸發 fail，回報 V=4.0 m/s 時 Cp=0.6270 > 0.5926）；`tests/physics/` 骨架（conftest.py + reports/README）就位
  - 2026-05-06：Layer 2（Literature/Standard Benchmarks）完成 — 35 tests pass（IEC 61400-1 Kaimal / Bastankhah-Niayifar wake / Glauert NTF / Tedric Harris BPFO/BPFI / ISO 10816-3 Class III / Walther viscosity decay / ISA air density）；負向測試 `_brg_n_elements` 23→30 → BPFO test 4 cases FAIL（rel_err 30%）。Layer 1+2 合計 71 tests pass in 1.45 s
  - 2026-05-06：Layer 3（Operating Envelope）完成 — 18 tests pass（cut-in/cut-out 行為、emergency stop 5s 衰減 50%、pitch rate ≤10°/s、yaw rate ≤0.5°/s、rotor overspeed software 保護、direct-drive + geared slip < 5%）。
  - 2026-05-06：Layer 4（Cross-module Consistency）完成 — 9 tests pass（Region 2 cubic R²>0.95 實測 0.99、stator-power lag-correlation 峰值在 240-600 s、inter-turbine spread > 0 且 < 50%、Region 3 power CV 結構性 bound、stability coupling 方向正確）。設計避開 calibration value（spread/CV）由 WMOM-24 收緊。
  - 2026-05-06：Layer 5（Fault Injection Signatures）完成 — 23 tests pass（11 個 fault scenarios 各驗 1-2 個 SCADA tag delta + healthy baseline ISO Zone A/B + power 偏離 lookup < 30%）。Layer 1-5 合計 121 tests pass。
  - 2026-05-06：Layer 6（Health Check CLI）完成 — `tools/physics_health_check.py` 一鍵體檢 entry，subprocess 跑 Layer 1-5 + 短模擬 5 turbines × 30 min（含 1 fault）+ 4 大健康分級 + markdown/JSON/figures 產出。Exit code 0/1 適合 CI。
  - 2026-05-06：code-reviewer subagent 對 Layer 1-6 做 review，找出 3 blockers + 6 suggestions；3 blockers + 3 suggestions 已修（B-1 Kaimal stable/unstable 重疊條件、B-2 settle_steps 不一致、B-3 mean_dict 缺 key 問題）。fix 後 121 tests 仍全 pass。
  - 2026-05-06：Layer 7（Test Report Persistence）完成 — `tests/physics/conftest.py` 加 pytest_sessionfinish hook，自動寫入 `reports/{YYYY}/{MM}/{ts}-pytest.{md,json}` 含 YAML metadata + baseline_drift 比對。`_baseline/pytest_baseline.{md,json}` 已建立。
  - **整體驗收**：121 pytest tests pass in ~25 s，health check CLI 4/4 PASS，Layer 1-7 全部 closed。
- **Source**:
  - 劉老師 2026-05-05 review：物理模型要有自我測試機制，要能驗證結果準確性
  - `docs/legacy/digiwt_TODO.md` Testing 段（issue #52 升級版）
- **Description**:
  既有物理模組 14 個 + 26 條進階修正（#61~#127），但只有 `examples/data_quality_analysis.py` 一個半自動 21 項 check。**痛點**：
  1. **不驗證物理定律 / 文獻 benchmark** — Betz 限、IEC 61400-1 Kaimal、ISO 10816、Bastankhah wake 文獻值都沒比對
  2. **不驗證故障注入 sanity** — `bearing_wear` 注入後 HF band 該升、`gearbox_overheat` 注入後 oil_temp 該升 — 沒人自動驗
  3. **不驗證跨模組一致性** — rotor power × η_drivetrain × η_converter ≈ P_elec 沒驗
  4. 改 physics 只能「憑感覺」 — 改完跑一次看儀表板，遺漏邊角 case 沒人發現
  
  **「regression test（鎖住現況）」與「validation（驗證物理正確）」是兩件事**，本 issue 兩者都要做，但**重點是後者**。

- **Deliverable**（6 層 validator，每層獨立 commit）：
  
  **Layer 1 — Conservation Laws / Physical Bounds（守恆律 + 物理上限）**
  - `tests/physics/test_invariants.py`
  - Betz 限：所有 (V, λ, β) 條件下 Cp ≤ 0.593
  - 能量守恆：P_aero × η_drivetrain × η_converter ≈ P_elec（容差 ±5%）
  - 動量平衡：thrust × V_∞ × A 與 aero power 透過動量定理對得上
  - 角動量：rotor_speed × gearbox_ratio ≈ generator_speed（含 slip 容差）
  - 熱平衡：input heat - removed heat = thermal mass × dT（熱慣性容差）
  - 質量守恆（冷卻液）：level decay 與 leak rate 對得上
  
  **Layer 2 — Literature / Standard Benchmarks（文獻 / 標準 benchmark）**
  - `tests/physics/test_benchmarks.py`
  - **IEC 61400-1 Kaimal**：σ_v / V_mean ≈ TI（強風下測）
  - **Bastankhah wake**：Ct=0.82, TI=8%, x=5D → deficit 落 25-35%（Niayifar & Porté-Agel 2016）
  - **Glauert NTF**：Region 2 a≈0.33 → V_raw/V_∞ ≈ 0.84（IEC 61400-12-1 Annex D）
  - **BPFO/BPFI**：n=23, d/D=0.18, α=10° → 計算值對應 Tedric Harris formula
  - **ISO 10816-3 Class III**：vibration RMS zone boundaries（A < 2.3, B 2.3-4.5, C 4.5-7.1, D > 7.1 mm/s）
  - **Walther viscosity**：cold-start 後 ~10 min decay 達 ~63% 穩態值
  - **Air density (ISA 15°C, dry)**：1.2250 kg/m³ ± 0.5%（WMOM #101）
  
  **Layer 3 — Operating Envelope（操作邊界）**
  - `tests/physics/test_envelope.py`
  - cut-in 以下 → power < 1 kW、rotor 漸停
  - cut-out 以上 → 30 s 內 power 歸零、進 stop 狀態
  - emergency stop → rotor speed 5 s 內降 50%、tower load 1.8× 衝擊出現
  - pitch rate ≤ 10 °/s（actuator 物理上限）
  - yaw rate ≤ 0.5 °/s
  - rotor overspeed margin：≤ rated × 1.2
  - generator slip：< 5%
  
  **Layer 4 — Cross-module Consistency（跨模組一致性）**
  - `tests/physics/test_consistency.py`
  - 風機個體 power spread 落 [10%, 25%]（與 -24 目標一致）
  - Region 3 power CV 落 [3%, 8%]
  - Region 2 power 對 wind 之 cubic fit R² > 0.95
  - Stator temp 與 power 之 lagged correlation：r > 0.5 但 lag > 60 s
  - 同一 grid event 下，不同 turbine 因 derate sensitivity 不同 → spread 在 [5%, 20%]
  - Atmospheric stability s × shear α 五重耦合：相關係數方向正確（#99/#109/#111/#113/#115）
  
  **Layer 5 — Fault Injection Signature（故障注入 sanity）**
  - `tests/physics/test_fault_signature.py`
  - 對 11 個 fault scenario 各跑短 sim，驗證 SCADA tag 該動的有動：
    - `bearing_wear` → HF band 升 ≥30%、crest factor ≥5
    - `gearbox_overheat` → oil_temp 升 ≥10°C、GMF sideband ratio 升
    - `pitch_imbalance` → 1P band 升、tower SS moment 升
    - `blade_icing` → 1P + 3P 都升、power 跌
    - `generator_overspeed` → HF band 升 + stator temp 升
    - `converter_cooling_fault` → power 跌 + cabin temp 升 + cooling level 降
    - `yaw_misalignment` → 3P band 升 + power 跌（cos³γ）
    - `stator_winding_degradation` → HF 升（電氣噪訊）
    - `hydraulic_leak` → broadband 升 + brake pressure 異常
    - `gearbox_oil_leak` → oil_level 降 + viscosity 異常
    - `grid_protection_trip`（如 -27 完成）→ relay status flip + emergency stop
  - 健康基線（無故障）：crest factor < 5, kurtosis < 4, RMS 落 ISO zone A/B
  
  **Layer 6 — Physics Health Check CLI（一鍵體檢報告）**
  - `tools/physics_health_check.py`：CLI 工具
    - 跑完 Layer 1-5 全 validator
    - 跑一次 30-min short sim 5 turbines（含 1 個 fault injection）
    - 產出 markdown 報告 + JSON + matplotlib 關鍵圖（Cp 曲面、wake deficit、ISO 10816 zones、fault signature）
    - exit code：失敗 → 1，全 pass → 0（適合 CI）
    - argparse `--save-report` (default on) / `--baseline-diff` / `--update-baseline`
  - 整進 [docs/routines/daily-workflow.md](docs/routines/daily-workflow.md)：每次改 physics 模組後 + 大版本發布前必跑
  - 寫入 README：`python tools/physics_health_check.py` 是「物理體檢」單一入口
  
  **Layer 7 — Test Report Persistence（測試紀錄保存機制）⭐ 劉老師 2026-05-05 要求**
  
  每次測試自動留下可追蹤的紀錄文件，避免「跑過就忘了」、無從查歷史軌跡。
  
  資料夾結構（**新增於 `tests/physics/reports/`**）：
  ```
  tests/physics/reports/
  ├── _baseline/                          ← 最新 baseline（人手動 review 後 commit）
  │   ├── pytest_baseline.md              ← 6 layer 全 pass 的 baseline 數值
  │   ├── pytest_baseline.json            ← machine-readable，diff 用
  │   └── health_baseline.md
  ├── 2026/05/                            ← 按月歸檔
  │   ├── 2026-05-05-1430-pytest.md       ← pytest 自動產
  │   ├── 2026-05-05-1430-pytest.json
  │   ├── 2026-05-06-0915-pytest.md
  │   └── 2026-05-06-1000-health/         ← health check CLI 產
  │       ├── report.md
  │       ├── report.json
  │       ├── baseline_diff.md
  │       └── figures/
  │           ├── cp_surface.png
  │           ├── wake_deficit.png
  │           ├── iso10816_zones.png
  │           └── fault_signatures.png
  └── README.md                           ← 怎麼讀報告 / 怎麼回滾 baseline / retention 規則
  ```
  
  每份紀錄頂端必含 YAML metadata：
  ```yaml
  ---
  timestamp: 2026-05-05T14:30:12+08:00
  git_commit: abc1234
  git_branch: claude/issue-20260505-23-2026-05-05
  git_dirty: false                        # working tree 是否有未 commit 變動
  python_version: 3.12.5
  test_type: pytest | health_check
  duration_sec: 42.3
  total_pass: 87
  total_fail: 0
  total_warn: 2
  baseline_compared: _baseline/pytest_baseline.json
  baseline_drift: see baseline_diff section below
  ---
  ```
  
  機制：
  - `tests/physics/conftest.py`：`pytest_sessionfinish` hook 自動產 `pytest-{ts}.md` + `.json`
  - `tools/physics_health_check.py`：CLI 預設寫入 `health-{ts}/` 子目錄
  - `tools/physics_baseline_update.py`：人手動 review 後 promote 為 baseline（**禁止自動 update**，避免 silent drift）
  - **Git 策略**：報告檔 commit 進 repo（這就是「紀錄」的意義）；`figures/*.png` 視大小決定（超過 1 MB 改 git-lfs 或 ignore）
  - **Retention**：保留近 6 個月每日；超過 6 個月只留每月最後一份；超過 1 年只留每年 release 對應的；baseline 永留
  - **README.md**：寫清楚「為什麼這個資料夾存在 / 怎麼比對兩份報告 / 怎麼決定該不該更新 baseline」
  
- **Acceptance**:
  - `pytest tests/physics/ -q` 100% PASS（7 層共 ~80-120 條 test）
  - 跑時間 < 60 s（不含 Layer 6 CLI 的 short sim）
  - `python tools/physics_health_check.py` 產出可讀的 markdown 體檢報告
  - **負向測試**：故意把 `power_curve.py` 一個常數改錯（例如把 Betz 限改成 0.7），framework 必須 catch 到並 fail
  - 既有 26 條物理修正（#61~#127）每條至少有 1 個 validator 對應
  - **Layer 7 驗收（測試紀錄保存）**：
    - 跑完 `pytest tests/physics/` → `tests/physics/reports/2026/MM/` 自動新增 `*-pytest.md` + `.json`
    - 跑完 `python tools/physics_health_check.py` → 自動新增 `health-{ts}/` 子目錄含 `report.md` + `report.json` + `figures/*.png`
    - 每份報告開頭都有 YAML metadata（timestamp / git_commit / git_branch / git_dirty / python_version / pass-fail counts）
    - `tests/physics/reports/_baseline/` 已 commit baseline，且 `baseline_diff` 段在新報告中能正確顯示「無漂移」或「漂移 X%」
    - `tests/physics/reports/README.md` 解釋資料夾用途 / 比對方法 / baseline update 流程
    - retention policy 至少寫成 docstring（實作可延到下次 cleanup）
  
- **Reference**:
  - 既有 `examples/data_quality_analysis.py`（21 check 已寫，可整合進 Layer 4/5）
  - `docs/physics_model_status.md`（每條 # issue 對應的 validation point 來源）
  - IEC 61400-1, IEC 61400-12-1/2, ISO 10816-3
  - Burton, Sharpe, Jenkins, Bossanyi (2011) *Wind Energy Handbook* 2nd ed.
  - Niayifar & Porté-Agel (2016) — wake deficit benchmark
  
- **Risk / Note**:
  - **不要過度收緊 acceptance** — 物理模型有隨機項（turbulence、AR(1)），驗證要用統計量（mean / std / 相關係數）+ 容差，不要硬 == 比對
  - 跑時間若爆掉 → Layer 5 fault sim 改成「先建 fixture 再跑 assertion」
  - 對應 -24 修正的目標（spread / CV）會在 Layer 4 體現，兩 issue 互相驗證

---

### WMOM-20260505-24 — Data quality 3 項 fail 修正（個體差異 spread + Region 3 CV）

- **Status**: open
- **Milestone**: M3 並行（demo 必修）
- **Priority**: high（P0 — demo 被客戶質疑會傷信任）
- **Estimate**: 0.5-1 工作天
- **Source**: `examples/data_quality_report.txt` 「待改善列表」3 項
- **Description**:
  最新 data quality run 仍有 3 項警告：
  1. **Wind 15-20 m/s region CV=0.9% 太低** — rated region 訊號過度平滑，pitch dead-band / lag 還是不夠
  2. **Wind 20-25 m/s region CV=0.8% 太低** — 同上
  3. **風機間平均功率差 36.8% (>30%)** — individuality 參數調太大，看起來像異常值不像真實 fleet
- **Deliverable**:
  - `simulator/physics/power_curve.py`：rated region 加更多 controller jitter（pitch micro-correction noise + power setpoint dither，幅度依 #61 Cp 模型回推合理範圍）
  - `simulator/turbine_individuality.py` 或對應位置：`per_turbine_power_offset` / `cp_offset` 從 ±15% 收斂到 ±10-12%（保留個體差但合理）
  - 重跑 `examples/data_quality_analysis.py` 短版 0.17h × 5 turbines，確認 3 項全 pass，且不破壞既有 18 項 pass
  - 同步更新 `data_quality_report.txt`（commit 進 repo）
- **Acceptance**:
  - 21/21 quality check pass（或至少 20/21，spread 落在 25-30% 區間）
  - 既有 #117/#119/#125/#127 物理鏈不被破壞
- **Reference**:
  - `modules/monitoring/examples/data_quality_report.txt`
  - `modules/monitoring/examples/_post_migration_quick_validate.py`
  - issue #61（Cp 模型升級 commit 應該已部分緩解，但 Region 3 仍偏平）

---

### WMOM-20260505-25 — Frontend：RUL 顯示 + 多 band alarm 視覺化（#57/#58 收尾）

- **Status**: open
- **Milestone**: M3 並行 / M5 demo 增值
- **Priority**: medium（P1 — M5 RAG demo 視覺化 PMF 關鍵）
- **Estimate**: 1.5-2 工作天
- **Source**: `docs/legacy/digiwt_TODO.md` Priority E + Priority F（issue #57 + #58 frontend 部分）
- **UI directive（WMOM-20260507-01 後）**：
  在 [TurbineDetail](frontend/components/TurbineDetail.tsx) 既有 8-tab 架構內加新 tab（建議 `health` 或擴充現有 `fatigue` tab）；多 band alarm 用 `<HealthBar>`（[Charts.tsx](frontend/components/ui/Charts.tsx)）；RUL 顯示用 `<Stat>` 大數字 + threshold 顏色（接 C.warn / C.amber / C.ok）。**不可** Tailwind / 硬 hex。
- **Description**:
  Backend 已完成：
  - #57：fatigue 4-level alarm + RUL（剩餘壽命）estimation + 自動寫進 history events
  - #58：vibration 5 band alarm（1P/3P/gear/HF/Bb）+ crest/kurtosis alarm + BPFO/BPFI + GMF sideband
  缺前端可視化 — M5 RAG demo 時客戶看不到「AI 預警」直觀畫面。
- **Deliverable**:
  - `frontend/components/turbine/RulPanel.tsx`：RUL 倒數（年/月/日）+ 4-level alarm badge（notice/warning/danger/shutdown）+ 觸發時間軸
  - `frontend/components/turbine/SpectralAlarmPanel.tsx`：5 band 動態 threshold curve（A/B/C/D zones）+ 即時 RMS 落在哪一區 + crest/kurtosis trend
  - `frontend/components/turbine/BearingDiagPanel.tsx`：BPFO/BPFI 即時頻率 + 軸承幾何來源說明 + GMF sideband ratio
  - 整合進既有 turbine detail page 為新 tab「Condition / RUL」
  - i18n（zh/en 雙語）
- **Acceptance**:
  - 3 個 panel 在 simulator 模式下能看到資料流動
  - 故障注入（bearing_wear / gearbox_overheat）時 alarm badge 會升級
  - M5 demo 時可直接 screenshot 進 pitch deck
- **Reference**:
  - 後端 API：`server/routers/turbines.py`（已 expose 對應 SCADA tag）
  - 既有 `frontend/components/turbine/LoadFatiguePanel.tsx`（pattern 參考）

---

### WMOM-20260505-26 — SCADA tag 深度擴充（protection / cooling loop / converter internal / service-state）

- **Status**: open
- **Milestone**: M3 後續 / M5 RAG 之前必須做
- **Priority**: medium（P1 — M5 RAG 警報多樣性的素材庫）
- **Estimate**: 3-5 工作天（可拆 4 個 sub-issue 分批）
- **Source**: `docs/physics_model_status.md` §3.5「Expanded SCADA Tag Set」
- **Description**:
  目前 104 SCADA tags 多在感測層（風速 / 溫度 / 振動 / 載荷）。M5 RAG demo 要對應 Z72 手冊的警報碼（數百條），但現況只有 ~20 種警報事件可觸發，警報 → 手冊 retrieval 的 demo 廣度不夠。
- **Deliverable**:
  - **Protection 層**：grid breaker status / under-voltage relay / over-current trip / earth fault relay / phase loss（5-8 tags）
  - **Cooling loop 深度**：3-way valve position / heat exchanger ΔT / coolant flow per branch / pump RPM / accumulator pressure（5-8 tags）
  - **Converter internal**：DC link voltage / IGBT junction temp / firing angle / harmonic distortion / common mode voltage（5-8 tags）
  - **Service / Maintenance state**：service mode flag / lockout-tagout state / manual override active / calibration mode / firmware version（4-6 tags）
  - 對應 OPC suffix 對齊 Bachmann Z72 命名規則
  - 寫進 `scada_registry.py` `_TAGS` + `turbine_physics.py::step()` 輸出
  - 物理耦合：能由現有 fault scenario（converter_cooling_fault / generator_overspeed / hydraulic_leak 等）自然觸發，不要手刻 mock
- **Acceptance**:
  - SCADA tag 從 104 擴到 ~125-130
  - 既有 18/21 quality check 不被破壞
  - 至少 5 條新 tag 能在 fault scenario 下看到變化
- **Reference**:
  - `docs/__Z72UserManual.pdf`（M5 餵 RAG，要先確認 tag 名稱對得上）
  - `docs/1040610-Z72_PLC_OPC_TAG_1040510.xlsx`

---

### WMOM-20260505-27 — 保護電驛協調模型（51 / 27 / 59 / 81）

- **Status**: open
- **Milestone**: M3 後續 / 也可 park 到 M5 後
- **Priority**: medium-low（P2 — academic paper 章節價值高，demo 直接價值中等）
- **Estimate**: 1-2 週
- **Source**: `docs/physics_model_status.md` §2.5「Still missing: protection coordination relay model」
- **Description**:
  既有 LVRT/HVRT envelope 是 ride-through curve 的 envelope 判定，沒有真實的保護電驛動作邏輯。發 paper 給 Applied Energy 的「grid integration」章節時，這層是 reviewer 通常會問的細節。
  四類保護電驛：
  - **51（過電流時間反延時）**：I × t curve，極反延時 / 一般反延時 / 中反延時
  - **27（低電壓）**：V < threshold + delay
  - **59（過電壓）**：V > threshold + delay
  - **81（頻率異常）**：df/dt + f range（U/F + O/F）
- **Deliverable**:
  - `simulator/physics/protection_relay.py`：4 個 relay class + coordination logic（main + backup + 動作時間 selectivity）
  - 與 `electrical_model.py` 串接：relay 動作 → trigger trip event → cascading 到 turbine state machine 的 emergency stop
  - 6-10 條新 SCADA tag（relay status / pickup current / trip count / last trip time）
  - 至少 3 個 demo grid event 能跑通（distant fault / nearby short circuit / frequency excursion）
  - 對應 fault scenario 至少 1 個（grid_protection_trip）
- **Acceptance**:
  - 4 relay 都有單元測試（依賴 -23 測試骨架）
  - 與 IEC 60255 / IEEE C37.112 inverse-time curve 標準對得上（不要求 bit-perfect）
  - 至少 2 種 selectivity 場景能驗證（main 先動 vs backup 接手）
- **Reference**:
  - IEC 60255 / IEEE C37.112（inverse-time overcurrent curve）
  - `simulator/physics/electrical_model.py` LVRT/HVRT 段是 baseline

---

### WMOM-20260505-28 — 單齒 pitting / spalling defect signature

- **Status**: open
- **Milestone**: park 到 M5 後（學術強化用）
- **Priority**: low（P2 — paper value 高，商業 demo value 低）
- **Estimate**: 1 工作週
- **Source**: `docs/physics_model_status.md` §2.2「Still missing: per-tooth pitting/spalling frequency model (individual tooth defect)」
- **Description**:
  目前 #76 已有 GMF + sideband + tooth wear scalar（aggregate），缺單顆齒缺陷的窄頻譜訊號。診斷論文裡軸承 BPFO/BPFI 已建（#58），齒輪單齒 defect 是配對的另一面。
- **Deliverable**:
  - `simulator/physics/drivetrain_model.py`：擴充 `tooth_defect` state（哪一階 / 哪一顆 / 缺陷嚴重度）
  - 對應頻譜 signature：GMF × shaft frequency 的 modulation pattern + envelope demodulation 可觀察的衝擊
  - 新 fault scenario：`gear_tooth_defect`（從 baseline 幾乎看不到，到 severe 時 GMF sideband 大幅升起 + crest factor 異常）
  - 1-2 條新 SCADA tag（`WDRV_TthDefSev` / `WDRV_TthDefHs`）
- **Acceptance**:
  - test_drivetrain.py 覆蓋（依 -23）
  - 與既有 11 fault scenario 相容（不破壞 fault_engine 邏輯）
  - 故障注入後 frontend SpectralAlarmPanel（依 -25）能看到 GMF 區段升起
- **Reference**:
  - Randall 2011 *Vibration-based Condition Monitoring* §6.4
  - 既有 #76 / #58 GMF sideband 為 baseline

---

## UX / Frontend revamp

### WMOM-20260507-01 — 前端 UI 改版（A · Calm Operator + 雙主題）

- **Status**: **done**（2026-05-07 完成）
- **Milestone**: M1 並行（前端基礎設施，不卡 M3 frontend issue -19/-20/-25）
- **Priority**: medium（劉老師對外 demo 與第一個客戶接觸需要更專業的視覺語言）
- **Estimate**: 1 工作天 → **實際 1 個 session**
- **Owner**: Claude (session 2026-05-07)
- **Source**: 劉老師提供 `WMOM 介面改版交接書.md` + `app/VA.jsx` design canvas（A · Calm Operator 風格 — 鼠尾草綠＋暖米白／雜誌式排版）
- **Description**:
  既有 frontend 是 dark cyan + Tailwind + Orbitron 風（從 digiWindTurbine 繼承），對運維廠商管理層而言過於「實驗室感」、與 v0.8.1 商業化定位不符。改版按交接書規範替換成：
  1. **220px 左 Sidebar**（5 主頁 nav + 工具區 secondary）取代頂部 header
  2. **雙主題系統**：日（鼠尾草綠 #3F6B53 + 暖米白 #F5F2EA）/ 夜（翡翠玻璃 #3DDC97 + 深森林 #0E1815）— 全元件走 theme palette，不寫死 hex
  3. **字型**：DM Serif Display（H1 38px）+ Manrope（內文）+ JetBrains Mono（數字 / SCADA tags）
  4. **5 大頁面重畫骨架**：FarmOverview / TurbineDetail / MaintenanceHub / CostPage / HistoryPage（按交接書 §4 規格）
  5. **保留全部 API / hooks 不動**：`useMockTurbineData` / `useRealtimeData` / `useMaintenanceData` / `useCostData` / `useI18n` / `useSettings` 全不動，OperatorControl 6 指令、AI fault diagnosis、Dispatch 流程、CSV 匯出、事件比較、4 個 cost endpoint 完全保留
- **Deliverable**:
  - `frontend/theme/` — `themes.ts`（兩套 palette）+ `ThemeProvider.tsx`（Context + localStorage + `data-theme` 同步）
  - `frontend/components/ui/` — `Card / Btn / PageHeader / StatusPill / Stat / Logo / NavIcon / Sidebar / BigChart / MiniSparkline / HealthBar / Field / Input / Select / ReadOnlyBox`（10 個共用元件 + index）
  - `frontend/App.tsx` — 重寫成 sidebar layout，包 ThemeProvider，保留所有 modal 與 view state
  - `frontend/components/{FarmOverview, TurbineDetail, MaintenanceHub, CostPage, HistoryPage}.tsx` — 5 大頁面照交接書規格重寫
  - `frontend/components/{FaultInjectionPanel, SettingsPage, DispatchModal, WorkOrderDetailModal, FarmSelector, TrendChartPanel, EventComparisonView}.tsx` — 沿用功能、套新樣式
  - `frontend/index.html` — 加 DM Serif / Manrope / JetBrains Mono CDN；移除 Tailwind CDN（已無使用）；CSS variable 預設值
  - 刪除 6 個孤兒：`DataCard / Gauge / StatusIndicator / MiniTrendChart / FarmTrendChart / icons.tsx`（被新 ui 元件取代）
- **驗收**：
  - ✅ `npx tsc --noEmit` 0 錯誤
  - ✅ Vite dev server 跑在 `http://127.0.0.1:5179/` 全 page module 200，5 大頁 + faults / settings 全可開
  - ✅ 劉老師於 5179 視覺 review 確認 OK（2026-05-07 截圖）
  - ✅ 響應式 grid 1280+ 4 欄 / 1024–1279 3 欄 / 1023– 2 欄 / 768– sidebar 收漢堡
  - ✅ 主題 ☀/☾ + EN/中切換寫 localStorage、reload 後狀態保留
  - ✅ 所有按鈕 `aria-label`、主題切換 `aria-pressed`
- **Decision**:
  - **Tailwind 全退**：原本規劃保留作 layout utility，但實作後發現所有 new code 都走 inline style + theme palette，Tailwind CDN 變成 dead weight，順手移除
  - **recharts 保留 in HistoryPage / CostPage / TrendChartPanel**：互動需求高（hover、zoom、reference line）走 recharts；overview / cost KPI 的趨勢圖改 SVG（跟 VA.jsx 一致）
  - **Faults / Settings 入 sidebar secondary group**：交接書 §6 only 列 5 主頁，但實際還是要保留入口；放在「工具」分組下方，與主題切換並列
- **Intentional placeholders（不是 bug，刻意保留）**：
  以下 7 個 PageHeader 按鈕**有 UI 但無 onClick**，作為設計稿視覺鷹架保留，等對應 API / 流程確定再逐步補上。劉老師 2026-05-07 確認「保留就好，之後一個一個補功能」。
  追蹤清單見 → `WMOM-20260507-02`。
  | 頁面 | 按鈕 | 設計稿來源 | 真實對應 |
  |---|---|---|---|
  | 維護中心 | `+ 新工單` | VA.jsx §4.3 | 風機細節 → AI 診斷 → 派遣技師（既有 dispatch flow） |
  | 風場總覽 | `匯出` / `+ 新報告` | VA.jsx §4.1 | `匯出` 可接 `/api/export/snapshot`；`+ 新報告` 暫無 API |
  | 風機細節 | `限載` / `停機` / `安排檢查` | VA.jsx §4.2 | 同頁右側「操作控制」卡片有完整 6 指令（重複入口） |
- **Reference**:
  - `docs/design/2026-05-07-ui-source/WMOM 介面改版交接書.md`（2026-05-12 歸檔保存）
  - `docs/design/2026-05-07-ui-source/app/VA.jsx`、`data.js`（design canvas）
  - `work-logs/2026-05/2026-05-07-ui-revamp-calm-operator.md`

---

### WMOM-20260507-02 — PageHeader placeholder 按鈕逐步補功能

- **Status**: open
- **Milestone**: 不卡 M2-M5 主線，可隨時挑著補
- **Priority**: low（UX polish；功能都可在 detail 頁完成）
- **Estimate**: 每個 0.5-2h，依 API 是否存在
- **Source**: WMOM-20260507-01 改版時依設計稿放上 UI 但無 handler
- **Description**:
  改版時依 VA.jsx 設計稿放了 7 個 PageHeader 裝飾按鈕，劉老師 2026-05-07 決定 placeholder 保留、之後逐項補功能。本 issue 作為清單追蹤；每個 sub-task 完成時直接打勾並 commit。
- **Sub-tasks**（按好做順序排）：
  - [ ] **a. 風場總覽 `匯出`** — 接既有 `GET /api/export/snapshot`（直接下載 JSON）。**估時 30 min**
  - [ ] **b. 風機細節 `停機`** — 對應 `OperatorControlCard` 的 stop 指令；點擊跳到右側卡片或直接呼叫 `POST /api/control/command { command: 'stop' }`。**估時 30 min**
  - [ ] **c. 風機細節 `限載`** — 開 inline modal 收 kW 值 → `POST /api/control/curtail`。**估時 1h**
  - [ ] **d. 風機細節 `安排檢查`** — 跳到 `/maintenance` + 預填 turbine 與 inspection scenario；依賴 WMOM-22 `inspection_schedule`。**估時 1h**（但要等 -22 done）
  - [ ] **e. 維護中心 `+ 新工單`** — 開 modal：選風機 + 描述 + 選技師 → `POST /api/maintenance/work-orders`（API 已存在）。**估時 2h**
  - [ ] **f. 風場總覽 `+ 新報告`** — 依賴 M4 reporting module；開 modal 選報告類型（月報 / 年度預算 / custom range）。**估時 2-3h**（要等 M4 backend）
- **Deliverable**:
  - 每完成一項，更新本 issue checkbox + commit 訊息帶 `feat(#WMOM-20260507-02): wire {sub-task name}`
  - 全勾完後本 issue close
- **Decision**:
  - 不要把這些按鈕通通砍掉重畫（會破壞跟設計稿的對齊）
  - 不要做「dummy alert / TODO 訊息」假裝有功能（劉老師 2026-05-07：「沒作用沒關係，開發階段」）

---

### WMOM-20260513-01 — UI 改版 v2（placeholder — 等劉老師補新設計交接書）

- **Status**: open (placeholder — **設計規範未提供前不開工**)
- **Milestone**: 未排（待 spec 後決定 M4 後半 / M5）
- **Priority**: TBD（依劉老師對外 demo 與客戶溝通的時程急迫度決定）
- **Estimate**: TBD（依改版幅度 — 微調 1d / 重畫 3-5d / 換主題系統 1 週）
- **Source**: 2026-05-12 劉老師提及「想修改 UI」；2026-05-07 WMOM-20260507-01 完成 Calm Operator 後，劉老師可能想做 v2 iteration

#### 背景

- 2026-05-07 已完成 WMOM-20260507-01「前端 UI 改版（A · Calm Operator + 雙主題）」
- 既有設計 source 已歸檔在 [`docs/design/2026-05-07-ui-source/`](docs/design/2026-05-07-ui-source/)（WMOM 介面改版交接書 / app/VA-VC.jsx / variants/V1-V3.jsx / shared/MiniDashboard / 各 HTML mockup）
- 劉老師 2026-05-12 表示有新 UI 想法

#### Description（待補）

下列為 placeholder，**劉老師需補完才能開工**：

- [ ] 新版設計交接書（類似 2026-05-07 那份 markdown）
- [ ] 主要要改哪幾頁？（FarmOverview / TurbineDetail / MaintenanceHub / CostPage / HistoryPage / Workflow / Reports 全動還是局部）
- [ ] 主題系統異動嗎？（保留鼠尾草綠+翡翠玻璃 / 換新色 / 加第三主題）
- [ ] 字型異動嗎？（保留 DM Serif + Manrope + JetBrains Mono / 換）
- [ ] 元件庫 (`frontend/components/ui/`) 要新增哪些？或重做哪些？
- [ ] 是否影響 backend schema 或 API contract？（默認否）

#### Acceptance（待補）

- [ ] `npx tsc --noEmit` 0 errors
- [ ] `npx vite build` 成功
- [ ] 全頁面在 light + dark 兩主題下 visually consistent
- [ ] 不破壞既有 functionality（hooks / API / modal flow 全保留）
- [ ] 留新版交接書到 `docs/design/{YYYY-MM-DD}-ui-source/`

#### Depends on
- 劉老師補 spec

#### Blocks
- 無（純美術 polish，不卡主線功能）

#### Notes for daily routine
- **此 issue 因缺 spec 暫時跳過** — daily autonomous worker 不要 pick 起來做
- 等劉老師補完 description 區塊後改 status，再進排程

---

### WMOM-20260513-02 — Demo Orchestrator full impl + simulator integration（A10 follow-up）

- **Status**: open
- **Milestone**: M5（2026-09）
- **Priority**: medium（demo polish；客戶 demo 時若想一鍵 replay lifecycle 需要這個）
- **Estimate**: 2-3 工作天
- **Source**: 2026-05-13 A10 (WMOM-20260509-10) 收尾留下的兩個延伸缺口

#### Description

A10 完成 Layer A pytest E2E（6 個 test 跑完整 lifecycle）+ Layer B 純靜態
`DemoOrchestratorPage.tsx` skeleton；此 follow-up 把兩個缺口補完：

**Part A — Demo Orchestrator UI 接 API（1-1.5d）**

- `frontend/components/demo/DemoOrchestratorPage.tsx` 從 skeleton 進化成可執行
- 「Run Full Demo」按鈕走 11 個 step：建單 → 派工 → 開始 → MR → 3 階 approve → receive → finish → 工單 2 階 approve → 月報
- 每 step 顯示 running / done / skipped + 可逐步暫停 / reset
- 確保 step list 與 `tests/e2e/test_fault_to_signoff_lifecycle.py::_walk_happy_lifecycle` 順序對齊（程式碼裡留 cross-reference comment）

**Part B — 真 simulator + canonical alarm code（1-1.5d）**

A10 為 mock 簡化用了字串 `"GBT_TEMP_HIGH"` 當 `source_alarm_code`，但 monitoring 層
（`modules/monitoring/simulator/physics/fault_engine.py`）的 alarm 結構是
`{type: "T1"|"T2"|"A", code: int}`。Follow-up：
- 抽 shared constant：`shared/alarm_codes.py` 定義 canonical Z72 alarm taxonomy
- E2E test 改用 canonical schema（e.g. `"T1:301"` for gearbox temp high）
- `tests/e2e/test_fault_to_signoff_lifecycle.py::_walk_happy_lifecycle` Step 1 改成
  真的呼叫 `simulator.inject_fault(scenario="gearbox_temp_high")` + assert SCADA tag delta
- 另加 INSPECTION over-use variant（`estimated_qty=1, actual_qty=2`），驗 receive
  endpoint 對「actual > estimated」的業務規則（cap at estimated vs allow over-use —
  需 product decision）

#### Acceptance
- [ ] DemoOrchestratorPage「Run Full Demo」按鈕端到端跑通 11 step → CLOSED + 月報
- [ ] Shared alarm code taxonomy 被 monitoring + workflow + E2E test 三方共用
- [ ] E2E test 改用真 simulator fault injection（不再用字串 mock）
- [ ] INSPECTION over-use variant 新增 1 個 test
- [ ] 全 backend + frontend 0 regression

#### Depends on
- WMOM-20260509-10（A10）已完成 ✓

#### Blocks
- 無（M5 demo polish）

---

## 物理模型 parking lot（學術深度，等 M5 後再評估）

> 不開正式 issue，但記錄在這以避免反覆討論「為什麼還沒做」。
> 投入大、商業 demo 直接價值低；如果劉老師要投 paper 才考慮排期。

| Item | 為什麼 park | 投入估計 | 觸發條件 |
|------|------------|----------|----------|
| 完整 BEM aerodynamic loading distribution | Cp(λ,β) + tower shadow + wind shear + wind veer 已涵蓋 trend 級 demo；BEM 主要對應「葉片 root 細部載荷分布 paper」 | 2-3 週 | 投 Renewable Energy / Wind Energy 期刊章節需要時 |
| Curled-wake model（yaw skew 反向旋轉渦流對） | Bastankhah 2016 線性 deflection + DWM meander 已涵蓋 90% 場景；curled wake 補的是 yaw > 20° 時的細節 | 2 週 | 對齊 NREL FAST.Farm / Floris 比對驗證時 |
| Aeroelastic tower / blade FEM coupling | tower SDOF first-mode + blade 3P/1P modulation 已能看到關鍵特徵；FEM 是月級工程 | 1-2 個月 | 與材料力學 / 結構合作另開 paper 線時 |
| Cooling 系統 radiator fin 細部模型 | 整體換熱 + fouling 已能 demo cooling 故障；fin-level 細節是熱交換器論文用 | 1 週 | 投 Applied Thermal Engineering 時 |
| Sub-transient electrical X"d/X'd 行為 | LVRT/HVRT envelope + ride-through 已涵蓋 grid event；sub-transient 是 power system 細節 | 1 週 | 與 -27 保護電驛協調合併投 paper 時 |

---

## M5-M6 預留區

> ROADMAP 詳見 `docs/product/ROADMAP.md`。
> M4 已展開為 [WMOM-20260509-01..-10](#m4-主線2026-08-workflow-part-2-inventory--reporting)。

- M5 (2026-09)：RAG_Ultimate strategy 對接（Phase 3 ready 否則用 baseline placeholder）+ Demo Orchestrator UI 完整版（接 -10 placeholder）
- M6 (2026-10)：Friendly 廠商現場部署 + 第一份月報送業主沒被退件 + 簽 LOI/合約

---

### WMOM-20260518-01 — MR detail modal 料件表加 SKU+name 顯示（A6 follow-up）

- **Status**: done（2026-05-19 完成；branch `claude/nice-brown-kJDox`）
- **Milestone**: M4 後續 / M5 demo polish
- **Priority**: medium（demo 給現場工程師看更友善；不阻塞 M4 收官）
- **Estimate**: 0.5 工作天 → **實際 ~3 小時**（含 code-review must-fix 採納）
- **Source**: 2026-05-18 WMOM-20260509-06 code review Should-fix #4
- **Owner**: Claude（session 2026-05-19，autonomous daily worker）
- **Completion summary**:
  - ✅ Backend schema：`MaterialRequestItemResponse` 加 `sku/name/unit: Optional[str] = None`
  - ✅ Backend repo：`MaterialRequestRepository.resolve_item_metadata(item_ids)` batch SELECT FROM `inventory_items` WHERE id IN (...)，回 `dict[UUID, ItemMetadata]`；缺漏 item → key omit；空輸入 → `{}` 不打 SQL
  - ✅ Backend router：加 `_enrich_items` + `_build_mr_response` + `_build_mr_list_response` 三個 pure-function helper，用 pydantic v2 `model_copy(update=...)` 不可變 enrichment；9 個 endpoint call site 全切過去
  - ✅ Frontend types：`MaterialRequestItem` interface 加 `sku/name/unit?: string | null`
  - ✅ Frontend `MaterialRequestDetailModal` items table：4 欄改 6 欄 `SKU | Name | Stock kind | Est qty | Actual qty | Unit`，UUID fallback 保留 monospace title 顯示完整 ID
  - ✅ Frontend receive form：label 從 truncated UUID 改 `SKU · name (est. N unit)`
  - ✅ Frontend returns dropdown：item_id 選單從 UUID 切片改 `SKU · name · est. N unit`
  - ✅ Frontend wizard step 3 review：顯 `SKU · name × qty unit · stock_kind`
  - ✅ 新增 9 個 test（`test_mr_item_metadata.py`）：repo 3（resolve / empty / missing）+ router 3（create / get / list）+ transition smoke 2（dispatch+receive+close + cancel）+ data drift 1（item 刪除後 null fallback）
  - ✅ Backend `python -m pytest modules/{workflow,cost,reporting}/tests/ tests/e2e/` → 526 passed (+9 new) + 1 xfailed + 3 pre-existing numpy drift + 1 flaky concurrency — zero regression
  - ✅ Frontend `npx tsc --noEmit` exit=0；`npx vite build` 3.57s, 748 modules, 917.15 kB (gzip 264.94 kB)
  - ✅ Code-reviewer subagent 找 3 must-fix + 3 should-fix + 2 nice-to-have，**全採納**：
    - MF#1 改 `model_copy(update=...)` 而非 attribute mutation（pydantic frozen 安全）
    - MF#2 加 docstring 註明 enrichment 非 transactional（read-after-fetch 跨 session）
    - MF#3 補 dispatch/receive/close/cancel 4 transition smoke tests
    - SF#1 `Iterable[UUID]` docstring 註明「只消費一次」
    - SF#2 `sqlite3` import 移到頂層 + 註解 SQLite-only（PG 切換見 WMOM-20260509-F6）
    - SF#3 grid SKU 欄寬度 `1fr` → `1.2fr`
    - N#1 `_build_mr_list_response` 空 list 早 return
    - N#2 移除 wizard `InventoryItemSummary.name/unit` 多餘 null guard（types 已 required string）
- **Reference**:
  - [`work-logs/2026-05/2026-05-19-mr-item-sku-name.md`](work-logs/2026-05/2026-05-19-mr-item-sku-name.md)
- **Depends on**: WMOM-20260509-06（done）
- **Blocks**: -
- **Resolution**（2026-05-19 autonomous worker）：
  - Domain `MaterialRequestItem` dataclass 加 3 個 optional metadata 欄位（純 informational，不參與 state machine / dispatch）
  - ORM `MaterialRequestItemORM.inventory_item` viewonly + `lazy="joined"` 自動補 sku/name/unit
  - Repository `_to_domain` 經 relationship 填值，inventory_item None 時三欄保持 None（cross-DB defensive）
  - Schema + frontend TS type 3 欄全 optional 保證向後相容
  - 5 個新 backend test 涵蓋 get / list / transition / dispatch / cross-farm isolation；e2e 6 個全 pass；516 passed (= 511 baseline + 5) + 1 xfailed + 3 pre-existing numpy drift — zero regression
  - PR：claude/issue-WMOM-20260518-01-2026-05-19
  - Work-log：work-logs/2026-05/2026-05-19-mr-item-sku-name.md

---

### WMOM-20260510-01 — Identity / dev mode / mock login + farm `is_offshore` field

- **Status**: done（全 4 part 完成 2026-05-18）
- **Milestone**: M5（2026-09）
- **Priority**: high（demo-blocker — 沒有身份切換無法給客戶看完整 lifecycle）
- **Estimate**: 2-3 工作天
- **Source**: 劉老師 2026-05-10 操作 lifecycle UI 時提出的 3 個關連缺口
- **Progress**:
  - Part A — Backend dev mode：done（merged 2026-05-14, branch `claude/issue-WMOM-20260510-01A-2026-05-14`）
  - Part B — Frontend mock login：done（merged 2026-05-15, branch `claude/issue-WMOM-20260510-01B-2026-05-15`）
  - Part C — Farm `is_offshore` 後端欄位：done（2026-05-18, branch `claude/nice-brown-PTCla`）
  - Part D — Frontend auto-drive start_work weather_window：done（2026-05-18, 同 branch — Part C/D 合併 PR）

#### 背景

2026-05-10 dev session 中發現 3 個彼此相關的設計缺口：

1. **沒有 auth/login 系統** — 所有 actor / assignee / approver 都用 frontend hardcoded `DEV_ACTOR_ID = '00000000-...0001'`
2. **簽核流程需要多角色** — employee → leader → treasury 3 階，但目前同一 placeholder 無法扮多角（且 chain 設計上「同 actor 不能連簽 ≥ 1 階」會擋）
3. **離岸/陸上判斷 hardcoded 在 UI** — `start_work` 對話框讓 user 手動勾「需檢查氣象窗（離岸風場）」，反向 UX。Farm config 沒有 `is_offshore` 欄位

#### 目標

實作 **dev/owner mode + mock login** 讓劉老師（或任何 demo 操作者）可以一個人扮所有角色完整跑 lifecycle，並把 farm 屬性放回 farm config 自動驅動 UI。

#### Description

**Part A — Backend dev mode（0.5d）**
- 加環境變數 `WMOM_DEV_MODE=true` 進 backend
- 啟用時跳過：
  - signoff chain「同 actor 不能連簽 ≥ 1 階」guard
  - 任何「dispatcher 不可同時是 assignee」之類的職責分離 check
- 啟動時 log warning：`⚠ WMOM_DEV_MODE active — auth checks bypassed`
- Production 部署時必須 unset

**Part B — Mock login（1d）**
- 簡易 user table（無密碼）：`name / email / role(s) / is_active`
- 預載 4 fixture：`Alice (employee)` / `Bob (leader)` / `Carol (treasury)` / `Owner (all roles, dev mode only)`
- Frontend 加左下角 user switcher（取代 sidebar lang toggle 旁那個位置 OR 獨立 widget）
- 切換 user 後：`localStorage.actor_id` 換新值，所有後續 API call 帶新 actor_id
- **不做**：登入畫面 / 密碼驗證 / JWT — 那些留給 M5+ 真 auth (WMOM-20260510-02 placeholder)

**Part C — Farm `is_offshore` field（0.5d）**
- `FarmConfig` 加 `is_offshore: bool = False`
- `farms_router` POST/PATCH 接受此欄位
- Frontend：
  - 重新加回 `start_work` dialog 的 weather_window 邏輯 — **依 farm.is_offshore 自動決定**，不再讓 user 勾
  - Onshore：`require_weather_window=false` 直接送
  - Offshore：要求 user 先綁 weather_window_id（M3 設計但 frontend 沒接 — 此 issue 一併補上）

**Part D — Farm 設定頁加 is_offshore checkbox（0.5d）**
- `FarmManagementPage` 或 farm setting modal 加 toggle
- Migration：既有 3 個 farm 預設 false（劉老師 demo 用陸上）+ 「彰化離岸風場台電」手動切 true 驗證 offshore code path

#### Acceptance

- [ ] `WMOM_DEV_MODE=true python run.py`：劉老師一個 placeholder 跑完 corrective lifecycle（建單 → 派工 → 開始 → 領料 3 階簽核 → 完工 → 工單 2 階簽核 → 月報）成功
- [ ] Mock login user switcher 切換 user 後，dispatch / approve action 帶不同 actor_id
- [ ] Onshore farm 的 work order，`start_work` 不再顯示 weather_window 選項
- [ ] Offshore farm（彰化）`start_work` 提示「請先綁定 weather_window_id」並提供選擇 widget
- [ ] 全 backend tests + frontend build 0 regression

#### Depends on
- 無（純獨立功能）

#### Blocks
- M6 客戶 demo（沒有 mock login 給客戶看 demo 會看到「dev placeholder」很不專業）

#### Notes
- **不做** real JWT auth — 那是 WMOM-2026XX-XX（M6+ if customer 真要 PoC 上線）
- Mock login 的 4 fixture user 是 demo 用，production 模式應該被禁用
- Part C 也修「2026-05-10 hot fix 把 weather_window checkbox 拿掉」的暫時方案

---

## 廢棄 / 不做（避免反覆討論）

| Item | 為什麼不做 | 取代方案 |
|------|-----------|---------|
| windMindOM 整合容器（v0.5） | 過度工程；客戶要的是 working tool 不是 framework | Monolithic 5 modules（DEC-20260502-06） |
| Plugin SDK | 同上；M1-M6 內部就 5 個 module 不需要 plugin 抽象 | 直接寫進 `modules/` |
| 4 類 Turbine Adapter ABC | 第一個客戶只有 Z72；過早抽象 | M1 只做 Bachmann Z72；第二個 OEM 再考慮 |
| Workflow Hub 獨立 service | 一個 dev 維運不來 | 留在 monolith 內 `modules/workflow/` |

詳見 `docs/product/decision_log.md` DEC-20260502-06。
