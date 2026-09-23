# 2026-09-23 — WMOM-20260716-06：footprint CPU-torch pin

> ⚠ 附帶提醒（承接自 WMOM-20260923-05 work-log）：canonical routine 文件
> `docs/routines/autonomous-daily-worker-prompt.md` 內文仍停在 v3（baseline backend 638 /
> frontend 59），已明顯落後於本次 cron trigger 實際送進來的 prompt（v4.1，baseline 1076/970，
> 本次實測又已進到 1103/1216）。建議劉老師找時間把 cron trigger 目前設定的完整 prompt貼回這份
> 文件同步，避免未來 session 讀到舊版誤判 baseline regression。

## Preflight

- `git checkout main && git pull origin main` → fast-forward 23 commits（前次 session 已推進到
  WMOM-20260923-06）。
- 目前 session 分支 `claude/inspiring-mccarthy-g168l6` 環境注入時已是 main tip 的 ancestor（零
  獨有 commit），直接 checkout 續用，不需另開分支。
- **Stack-aware 檢查**：`mcp__github__list_pull_requests`（state=open）→ 空清單，無殘留未合併 PR，
  無需接續半成品或避讓同塊修改。
- **自我測試 baseline**：
  - `pip install --ignore-installed PyYAML -r requirements.txt -r requirements-dev.txt` 成功
    （確認了本 issue 的問題現場——`torch-2.14.0` 連同一整批 `nvidia-cu13*` CUDA 動態庫一起被拉下來，
    與 DEC-20260716-02 量測記錄的「linux 預設拉 CUDA torch」現象一致）。
  - backend：`1103 passed, 7 skipped, 1 xfailed`（與 STATUS.yaml 記錄的最新 baseline 一致）。
  - frontend：`npx tsc --noEmit` 0 error；`npx vitest run` `1216 passed`（58 files）；
    `npx vite build` OK。
  - 皆與追蹤檔案記錄的目前 baseline 一致，非 regression，可以往下挑題。

## Claim

- 候選盤點（依 §4 決策樹）：
  - baseline / CI 飛輪本身 → 皆綠，無需修。
  - M6 critical path 的 live/OPC 硬化（WMOM-20260720-04/-08）→ 上次 session 已收尾完成。
  - **WMOM-20260716-06**（footprint CPU-torch pin）與 **WMOM-20260509-F6**（PostgreSQL row-lock
    integration test）過去多個 session 皆因「本地無 docker daemon」被列為卡住候選——本次
    preflight 意外發現 `dockerd` 實際可以在本 sandbox 手動啟動成功（`docker ps` 有回應），值得
    重新評估兩者是否真的可解。
  - **先用一支 Explore subagent 調查 F6 的真實範圍**（見下方「F6 調查與擱置」）——結論是 F6 遠比
    ISSUES.md 標注的「0.5 工作天」大得多：repo 目前完全沒有任何 PostgreSQL 連線路徑
    （`_get_engine()` 寫死 `sqlite:///`、`_begin_immediate()`/`_set_sqlite_pragmas()` 皆 SQLite
    專屬語法、requirements 無 `psycopg2`/`asyncpg`、docker-compose.yml 無 postgres service、
    decision_log 零筆 postgres 決策紀錄），F6 實際上需要「先決定 M6 真的要選 PostgreSQL backend
    →打通一條全新的 dialect-branch 連線層 →才輪到補這支 integration test」，是多天且帶架構決策
    的工作，不符合本 routine 「單 session 可完工、無設計歧義」的挑題準則，本次**不接**，見下方
    「F6 調查與擱置」段落記錄調查結果供未來 session 參考、避免重工。
  - **WMOM-20260716-06** 相對單純：DEC-20260716-02 已經拍板方案（deploy 專用 CPU-torch pin，
    Dockerfile 內 `pip install -r requirements.txt` 前先裝 CPU wheel torch），只欠「實測驗證」
    這個 follow-up 動作，且 docker 現在真的能跑——**本次認領此題**。
- 認領 **WMOM-20260716-06**，ISSUES.md 標記 `in_progress`（見上方 diff）。

### F6 調查與擱置（不開工，僅記錄供未來參考）

用 Explore subagent 調查 `WMOM-20260509-F6`（PostgreSQL row-lock integration test）的真實範圍，
結論摘要：

- **已具備、零額外工作**：`inventory_repository.py::apply_stock_delta_in_session()`、
  `material_request_repository.py::dispatch_request()`/`add_return`、
  `signoff_repository.py` 皆已用 SQLAlchemy `.with_for_update()`／`with_for_update=True`
  的 dialect-agnostic ORM API，對 Postgres engine 會直接發出真正的 `SELECT ... FOR UPDATE`，
  程式碼本身不用改。
- **完全不存在、需要新建**：`work_order_repository.py::_get_engine()` 寫死
  `create_engine(f"sqlite:///{abs_path}")`；`_begin_immediate()`（SQLite `BEGIN IMMEDIATE`
  event listener）與 `_set_sqlite_pragmas()`（WAL/busy_timeout PRAGMA）皆 SQLite 專屬語法，
  對 Postgres 需要整套 dialect 分支（或至少 skip）；requirements.txt/requirements-dev.txt
  完全沒有 `psycopg2`/`psycopg`/`asyncpg`；`docker-compose.yml` 沒有 postgres service 可重用；
  `_migrate_completion_columns()` 用 SQLite 專屬 `PRAGMA table_info`，repo 內無 Alembic 或任何
  跨 dialect migration 工具。
  - `docs/product/decision_log.md` 全文 grep `postgres`（不分大小寫）**零命中**——M6 是否真的選
    PostgreSQL backend 目前完全是「若選」的假設語氣（ISSUES.md 多處原文："M6 若選 PostgreSQL
    backend 才補"），並非已拍板的方向。
- **建議**：F6 的 ISSUES.md estimate（0.5 工作天）需要更正為「需先有架構決策 + 多天實作」，且應
  該歸類到「🟡 需劉老師決策」而非目前標注的「🔵 autonomous-friendly」——這個決策本質是「M6 客戶
  部署要不要上 PostgreSQL」，屬於 CLAUDE.md §6.3「動到架構 / 改變方向」等級的決策，本 session
  不會擅自拍板、也不會只做一半（例如只加 psycopg2 依賴但不解決 migration/PRAGMA 分支問題）
  留下架構半成品。本次僅更正 ISSUES.md 標注與估時，並在此記錄調查結果，供劉老師決策後的未來
  session 接手時省去重工。

## Branch + work-log

- 沿用環境注入分支 `claude/inspiring-mccarthy-g168l6`（已確認是 main tip 的直接後代，無需另開）。
- 本檔即本次 work-log。

## Implement

1. **`Dockerfile`**：在 `COPY requirements.txt .` 之後、`pip install -r requirements.txt` 之前，
   新增一行 `RUN pip install --no-cache-dir torch --index-url
   https://download.pytorch.org/whl/cpu`——讓 `requirements.txt` 內 `sentence-transformers>=3.0`
   隱含的 `torch` 依賴在被安裝前就已被 CPU-only wheel 滿足，pip 解析依賴時看到已安裝版本符合
   規格就不會再另外抓 CUDA 版本（`requirements.txt` 本身不動，維持 dev 端 GPU 相容，與
   DEC-20260716-02 的 Consequences 段落規格一致）。
2. 未動 `requirements.txt` / `docker-compose.yml`——DEC-20260716-02 明確要求「主
   requirements.txt 不動（保留 dev GPU 相容）」，改動範圍僅限 production Docker build 路徑。

## Verify（含 docker 實測）

- **Before（現況重現，量測 baseline image 體積）**：`docker build` 現有（未改前）Dockerfile。
- **After（套用 fix）**：`docker build` 套用 CPU-torch pin 後的 Dockerfile，比較兩者 `docker
  images` 回報的 size，確認符合 DEC-20260716-02 估計的「砍半，~4-5GB → ~2-2.5GB」量級。
- **功能性 smoke test**：容器內 `python -c "import torch; print(torch.__version__);
  print(torch.cuda.is_available())"` 確認裝到的是 CPU-only wheel（`torch.version.cuda is
  None` 或 `cuda.is_available()==False`）；再 `python -c "import
  sentence_transformers, chromadb"` 確認 CPU torch 不影響套件可正常 import（實際 encode 需要
  下載模型權重，若 sandbox 網路可達則一併驗證，否則以 import 成功 + docker-compose healthcheck
  作為替代驗證，此處視實測結果補完）。
- 本機 backend/frontend 自我測試套件本身不涉及 Docker（純 host Python/Node 環境），Dockerfile
  變更不影響其結果，故不需要重跑；Verify 的證據以 docker build/run 的實測輸出為準，記錄於下方。

### 實測結果

**環境限制**：本 sandbox 的 outbound HTTPS 走 TLS 攔截代理（`/root/.ccr/README.md` 所述），
container 內預設不信任該代理 CA，直接 `docker build` 會在 `pip install` 階段 SSL 驗證失敗。
量測用的 image 額外加了「安裝 sandbox 代理 CA + `--network host`」兩個步驟（README 建議的標準
work-around），**這兩行純粹是本 sandbox 才需要的量測腳手架，不會、也沒有進到 commit 的
`Dockerfile`**——實際部署環境走真正的 pypi.org/download.pytorch.org，沒有這個攔截代理，不需要
這兩行。

- **Before（現有 Dockerfile，未改前）**：`docker images` 回報 `footprint-test:baseline`
  content size **3.37GB**（disk usage 10.1GB，含 build 中間層）。`Successfully installed` 清單
  含 `torch-2.14.0`、`triton-3.8.0`（247.9MB wheel）與整批 `nvidia-cu13*`（cublas/cudnn/cufft/
  cusolver/cusparse/nccl/nvjitlink/nvshmem/nvtx/curand/cufile/cuda-runtime/cuda-nvrtc/
  cuda-cupti/cusparselt）——與 DEC-20260716-02 量測記錄的「linux 預設拉 CUDA torch」現象一致，
  本次於本 sandbox 重現確認。容器內 `torch.__version__` = `2.14.0+cu130`、
  `torch.version.cuda` = `13.0`。
- **After（套用本次 Dockerfile 改動）**：`docker images` 回報 `footprint-test:fixed` content
  size **550MB**（disk usage 2.57GB）——比 before **省下 ~2.8GB**，降幅遠優於 DEC-20260716-02
  原估「砍半到 2-2.5GB」（本次量測的基底更小，可能與量測當下 CPU wheel/相依版本已比 2026-07
  當時更精簡有關）。`Successfully installed` 清單確認**完全不含** `torch`/`triton`/任何
  `nvidia-cu13*` 套件（torch 已被先裝的 CPU wheel 滿足，pip 解析 `sentence-transformers` 的
  torch 依賴時視為已滿足不再另抓）。容器內 `torch.__version__` = `2.14.0+cpu`、
  `torch.version.cuda` = `None`、`torch.cuda.is_available()` = `False`（符合預期：deploy
  容器本來就沒有 GPU）。
- **功能性 smoke test（After）**：容器內 `import sentence_transformers, chromadb` 皆成功
  （`sentence_transformers==6.1.0`、`chromadb==1.5.9`），CPU-only torch 不影響套件可正常載入。
- **End-to-end 驗證（After，真正的 app image，含 `run.py` + `modules/` + `shared/`）**：
  `docker run` 起容器（`windmindom-backend:verify`，基底沿用已驗證過的 fixed 依賴層 + 疊上
  app 程式碼層，避開 sandbox 內 Docker Hub 匿名 pull rate limit 429 的重複拉取問題）→
  `curl http://localhost:18100/api/health` 回應
  `{"status":"ok","mode":"simulation","sourceActive":false,...}`（200 OK）；容器 log 顯示
  `Uvicorn running` + `Migrated legacy database to farm 'legacy'` 正常啟動流程，無例外。
  確認這不只是「pip install 成功」，而是**整個 FastAPI app 在 CPU-only torch 的 image 裡能正常
  啟動並回應請求**。
- **清理**：驗證用的 docker image/container/build cache 全數清除（`docker rm -f` +
  `docker image rm` + `docker builder prune -af`），量測用的臨時 `Dockerfile.verify*` /
  `ca-bundle-verify.crt` 已刪除，`git status` 確認 repo 內僅 `Dockerfile`/`ISSUES.md`/本
  work-log 有異動，無其他殘留檔案。
- 本機 backend/frontend 自我測試套件（純 host 環境，不涉及 Docker）維持 Preflight 記錄的
  `1103 passed, 7 skipped, 1 xfailed` / frontend `1216 passed`（58 files）/ tsc 0 / build OK，
  本次改動不影響其結果。

## Review

🔍 **code-reviewer subagent review**（`Dockerfile` + `ISSUES.md` diff + 本 work-log）：

- **0 must-fix**。Dockerfile 改動本身判定正確且已用真實 build/run 驗證（非僅理論推導）；
  inline 註解用詞準確、未過度宣稱；`modules/knowledge/embedder.py` 檢查確認
  `SentenceTransformer(...)` 未指定 `device=`（自動偵測，容器內無 GPU 自動走 CPU），production
  無任何 GPU 專屬 code path，與 DEC-20260716-02 判斷一致；`docker-compose.yml` 的 `backend`
  service 直接 build 這支 `Dockerfile`，自動繼承此修復不需額外改動；CI（`ci.yml`）完全不
  build Docker image，故無 CI 風險、也無遺漏的 CI 更新項目。
- **1 should-fix（已修）**：ISSUES.md 統計表（open/in_progress/done 計數）在草稿階段未同步本次
  status 變更——已在 Wrap-up 一併更正（open 11→10、done 113→114，見下方）。
- **1 nice-to-have（已採納）**：原草稿用不成慣例的裸 `in_progress` 字串標記狀態，已改成專案慣用的
  `✅` + completion summary 格式（比照 WMOM-20260716-04/-05 等鄰近條目寫法）。
- **附帶非阻塞觀察**（供未來參考，非本次需解決）：目前作法依賴 pip「已滿足依賴不重裝」的
  resolver 行為——若未來 `sentence-transformers`/`chromadb` 升級要求比 CPU wheel index 當下
  更新的 torch 版本，pip 理論上可能 backtrack 改從預設 index 重裝回 CUDA 版本，且因 CI 不
  build image 而無自動偵測訊號。這是 DEC-20260716-02 本來就接受的風險（deploy 專用 pin，非
  完整輕量化），本次不擴大範圍處理，僅記錄於此供未來若真的踩到再評估（例如明確 pin torch
  版本，或日後 CI 若開始 build image 時補一個 image smoke test）。

**Overall verdict：Approve**（0 must-fix，2 項已全數採納）。

## Wrap-up

- **本次完成**：WMOM-20260716-06（footprint CPU-torch pin）full done——Dockerfile 3 行新增，
  真實 docker build/run 驗證（image 3.37GB→550MB，app 可正常開機 + `/api/health` 200 OK），
  code review 0 must-fix、2 項 should/nice-to-have 全數採納。
- **附帶完成**：重新調查並更正 WMOM-20260509-F6（PostgreSQL row-lock test）的範圍與估時
  （0.5 工作天 → 多天 + 需先有架構決策），標記 🟡 需劉老師決策，避免未來 session 誤判成小題
  重工調查；M6-3 epic table 同步更正標記。
- **STATUS.yaml**：本次更新 `last_updated`（見下方 diff）、baseline 數字維持
  backend `1103 passed, 7 skipped, 1 xfailed` / frontend `1216 passed`（58 files）不變
  （本次改動不影響測試數量），並更新 canonical routine 文件版本落後提醒的追蹤狀態。
- **ISSUES.md**：WMOM-20260716-06 標記 done + 統計表更正（open 10 / done 114）；
  WMOM-20260509-F6 標記 🟡 需劉老師決策 + 估時更正 + M6-3 epic table 同步。
- **TODO.md**：待更新「最後更新」摘要與候選清單（見下方 commit 前的 TODO.md 編輯）。
- **哪些部分沒有自動化測試保護**（誠實揭露）：
  - Dockerfile 變更**沒有 CI 自動化保護**——`.github/workflows/ci.yml` 完全不 build Docker
    image，所以這次的驗證（image size 量測 + app 開機 + health check）全部只在本 session 手動
    跑過一次，之後若有人不小心改動 `requirements.txt` 或 `Dockerfile` 導致 CPU pin 失效
    （例如 pip resolver 因版本升級 backtrack 回 CUDA 版本，見上方 Review 附帶觀察），不會有
    任何自動訊號告警，需要人工重新 build 才會發現。這是本次刻意不處理的已知限制（DEC-20260716-02
    本身也沒有要求補 CI image build），留給未來若真的需要才評估。
  - docker-compose 完整 `docker compose up` 多容器（backend+frontend）串接未在本次驗證範圍內
    （只驗證了 backend 單容器起 + health check），frontend 容器本身未受本次改動影響（不同
    Dockerfile），判斷不需要額外驗證。
- **下次接手候選**：PR C（檢視情境掛載 app，需先寫 broker 子設計）／M6 部署前置 HTTPS 配置
  （需先定部署目標/憑證策略）／WMOM-20260509-F6（需劉老師先拍板是否選 PostgreSQL backend，
  拍板後才適合 autonomous session 接手實作）。
- ⚠ **附帶提醒（沿用自前次 session）**：`docs/routines/autonomous-daily-worker-prompt.md`
  canonical 版本仍停在 v3（baseline backend 638 / frontend 59），已落後本次 cron trigger 實際
  送入的 prompt（v4.1，baseline 本次實測 1103/1216）。建議劉老師找時間同步。

## Commit + Push

- Commit 訊息：`fix(#WMOM-20260716-06): Dockerfile CPU-only torch pin，image 3.37GB→550MB`
- Push 到環境注入分支 `claude/inspiring-mccarthy-g168l6`，開正常標題 PR（非 `[WIP]`，工作已
  完整收尾）。
