# 2026-09-22 — 專案檢視 + 追蹤文件真相對齊（M5 → M6 交棒）

> Session 類型：專案檢視 / 文件同步（無 production code 變更）
> Session 長度：中
> 主導：Claude + 劉老師需求「檢視目前專案 → 更新專案文件 → 討論下一步」
> 結果：實跑全套測試建立真實 baseline、四份追蹤檔（STATUS.yaml / ISSUES.md / TODO.md / ROADMAP.md）
> 與 CLAUDE.md §4/§10 對齊現況，並提出 M6 推進方案供決策

---

## 1. Session 目標

1. **檢視**：repo 現況（分支 / PR / 測試 / 模組完成度）到底在哪，而不是照抄文件宣稱
2. **更新專案文件**：追蹤檔已停在 2026-07-18 ~ 2026-09-01，與實況脫節
3. **討論下一步**：2026-09-22 距 M6（2026-10）僅剩一週，需要決定 critical path

---

## 2. 檢視結果（實測，非文件宣稱）

### 2.1 Repo / 分支 / PR

| 項目 | 實況 |
|------|------|
| HEAD | `5555112 feat(#WMOM-20260901-01): 3 分鐘介紹影片成片 MP4 + 成片規格說明 (#155)` |
| 分支 | 本 session 工作分支 `claude/jolly-curie-ts9t94`，與 `origin/main` 同點起步 |
| working tree | 乾淨（無未提交變更） |
| 開啟中的 PR | **0**（#142-#155 全數已合併） |
| 最後一次 code 變更 | 2026-07-20 arc（#142-#152）；2026-09-01 之後僅對外素材 `promo/` |

→ **沒有半成品掛在半空中**。可以乾淨地起新 arc。

### 2.2 測試 baseline（本 session 實跑）

| 層 | 指令 | 結果 |
|----|------|------|
| Backend | `pytest modules/{workflow,cost,reporting,knowledge,monitoring,auth}/tests/ tests/ -q` | **1076 passed / 7 skipped / 1 xfailed**（1084 collected，66s） |
| Frontend 型別 | `npx tsc --noEmit` | **0 error** |
| Frontend 單元 | `npx vitest run` | **957 passed / 48 files**（36s） |
| Frontend build | `npx vite build` | **OK**（僅 chunk >500kB 警告） |

→ 文件先前記載的 backend「997 passed / 998 collected」已過時；真實數字為 **1084 collected**。
→ 環境注意：`pip install -r requirements-dev.txt` 在本 sandbox 會撞 Debian 系統 PyYAML
（`Cannot uninstall PyYAML 6.0.1, RECORD file not found`），需 `pip install --ignore-installed PyYAML -r ...`。

### 2.3 模組完成度（實際程式碼量）

| Module | Python LOC | 狀態 |
|--------|-----------:|------|
| `modules/monitoring/` | 18,272 | M1 既有 + 情境模式深化 |
| `modules/workflow/` | 17,172 | M3-M4 done |
| `modules/cost/` | 7,025 | M2 done |
| `modules/reporting/` | 2,996 | M4 done |
| `modules/knowledge/` | 2,829 | M5，531-chunk Z72 向量檔已就位 |
| `modules/auth/` | 1,583 | M6-4 done |

`modules/knowledge/data/wind_farm_vectors/`（chunks.jsonl + vectors.npy + manifest.json）與
`config/rag_strategy_z72_manual.yaml` 皆在 repo 內；`frontend/components/field/`
（FieldPage + MyOrdersMode）存在，M5-5 Part A / B-1 / B-2 已落地。

### 2.4 issue board 真實計數（腳本掃 ISSUES.md，129 個有宣告的 issue）

| Status | Count | 來源 |
|--------|------:|------|
| done | 112 | 83 個 `### ` 段落標 done + `WMOM-20260504-08`（M2 收官，漏標 status）+ 28 個 2026-07/09 條列式已合併項 |
| open | 15 | 11 個 `### ` 段落 + 4 個條列式（-20260716-06 / -20260720-04 / -08 / -13） |
| in_progress | 2 | WMOM-20260503-05（客戶接觸）、WMOM-20260504-12（前端記憶體觀察） |
| **total** | **129** | |

→ 先前 ISSUES.md 表（open 15 / in_progress 3 / done 96）與 STATUS.yaml（open 13 / in_progress 1 /
done 100）兩邊互相矛盾，且皆與實況不符；本次以腳本計數為準統一。

### 2.5 文件漂移（本次修正）

| 檔案 | 漂移 | 處理 |
|------|------|------|
| `CLAUDE.md` §4 | 列了不存在的 `deploys/` 與 `opc_bachmann/`（OPC client 早已在 `shared/plc_clients/`）；未列 `promo/`、`tools/` | 改寫成實際樹狀 |
| `CLAUDE.md` §10 | 停在「#150 in review」；M5/M6 百分比與測試數過時 | 更新為 2026-09-22 快照 |
| `STATUS.yaml` | `next_milestone` 已膨脹成單行長文、`last_updated` 2026-09-01、issue_stats 錯 | 重寫為分段可讀格式 + 真實計數 |
| `ISSUES.md` | 統計表 + 「最後更新：2026-07-18」與內文（已寫到 2026-09-01）不一致 | 更新統計 + blurb + 新增本 session 段落 |
| `TODO.md` | 「最後更新：2026-07-18」、baseline 997/797、下一個 milestone 仍寫 M5 | 重寫現況與工作板，改以 M6 critical path 排序 |
| `ROADMAP.md` | dashboard 快照停在 2026-07-20、M5 標 75% | 更新快照段 + M5/M6 狀態 |

---

## 3. 下一步方向（提案，待劉老師拍板）

2026-09-22 → M6（2026-10）只剩一週。M5 主功能（RAG 檢索 + `/field/` mobile）已到齊，
**剩下的 M5 項目（M5-4 灌客戶手冊 + 一年警報 csv）本質上要客戶素材，屬 M6 部署期工作**。
因此建議把 M5 標為「功能面 done，資料面隨 M6 部署落地」，把力氣移到 M6 critical path。

### 方案 A — M6 部署前置硬化（建議優先）

> 論據：M6-1/M6-2 一旦真的進客戶現場，踩到的就是 live/OPC 路徑，而那條路徑目前有**已知且已定位**的 bug。

1. **WMOM-20260720-04** — live/OPC 後端硬化（🟡，M6 實接前必做）
   - (1) `DataBroker.stop()` 沒呼叫 `_opc_adapter.stop()` → 切走 live 後孤兒 thread 續寫新 session
   - (2) 切走 live 無角色檢查（起 live 需 SUPERVISOR，不對稱）
   - (3) `config.py::set_simulation` 在非即時模擬來源時靜默 `switch_mode` → **live 會被悄悄斷線**
     （#146 前端 gate 只是 best-effort，definitive fix 在後端）
2. **WMOM-20260720-08** — 切換來源生命週期硬化（併入 -04 一起做）
   - `start/stop/switch_mode` 全程無鎖 → 連點兩下可撞 `RuntimeError: cannot join thread before it is started`
   - `simulator/engine.py:310` `time.sleep(time_step)` 不可中斷 → `stop()` 得等滿一拍
3. **WMOM-20260716-06** — footprint CPU-torch pin（Dockerfile，image 砍半；需 docker 環境驗）
4. **WMOM-20260509-F6** — PostgreSQL row-lock integration test（M6-3，需 docker postgres）
5. **HTTPS 部署配置**（M6-4 唯一殘項）

→ 產出：一份「可以帶去客戶現場」的部署包。**這是唯一會擋住 M6-1/M6-2 的東西。**

### 方案 B — 情境比較分析 epic 收尾（DEC-20260720-02）

> 論據：這是 demo 的說服力來源（「有故障 vs 健康機組差多少」自動出圖），對 sales 有直接價值。

1. **WMOM-20260720-13** — A1 的 4 個 Should-fix（其中 2 個是 round-1 修正時新引入的小回歸）
   - (1) `scheduleMissing` banner 對「刻意空排程」誤報
   - (2) 切頁籤丟失所選機組 + 多打一次 API（打在 A1 核心動線上）
   - (3) `ScenarioPage.handleGenerate` Must-fix 現場缺回歸測試
   - (4) `fault_schedule` 映射兩次形狀不同 → 抽共用 helper
2. **A2 跨情境比較**（相對時間對齊）— epic 中最有 demo 價值的一塊
3. **PR C 檢視情境掛載 app**（需先寫 broker 子設計，最大）

### 方案 C — 對外 / 客戶接觸（WMOM-20260503-05）

`promo/windMindOM-intro-3min.mp4` 已就緒，pitch deck 也有。這條是**劉老師的工作**（cold email + 約 demo），
不是 code 工作，但它決定 M6-1/M6-2 的時程——**沒有客戶就沒有 M6**。

### 建議順序

```
A1（WMOM-20260720-13，半天，把已知回歸收乾淨）
  → A（部署前置硬化 -04 + -08，2-3 天，M6 硬需求）
  → B2（A2 跨情境比較，demo 說服力）
並行：C（客戶接觸，劉老師）
```

理由：-13 是「已經欠下的技術債且範圍明確」，先清掉不讓它腐爛；接著 -04/-08 是 M6 唯一的硬阻塞；
A2 屬於加分項，排在確定有客戶之後做才不會做白工。

---

## 4. 本 session 實際變更

- 新增 `work-logs/2026-09/2026-09-22-project-review-docs-sync.md`（本檔）
- 更新 `STATUS.yaml`、`ISSUES.md`、`TODO.md`、`docs/product/ROADMAP.md`、`CLAUDE.md`
- **零 production code 變更**（純檢視 + 文件）

---

## 5. 下次接手

1. 等劉老師對 §3 三個方案表態（或直接照「建議順序」走）
2. 若走建議順序：開 `claude/issue-WMOM-20260720-13-2026-09-XX` 分支，先做 A1 的 4 個 Should-fix
3. 環境提醒：新 sandbox 裝依賴要加 `--ignore-installed PyYAML`（見 §2.2）
