# v0.5 Assets Inventory（搬入 / 已現代化 / 棄用對照）

> 對應 issue：WMOM-20260503-02（搬入 v0.5 有用資產）
> v0.5 來源路徑：`D:\Project_CodingSimulation\researchTopic\windFarmOM_bk\`
> 本檔產生日期：2026-05-04
> 棄用決策依據：[`docs/product/decision_log.md`](../product/decision_log.md) DEC-20260502-06、DEC-20260504-01

---

## 1. 三類資產

| 類別 | 處理方式 |
|------|--------|
| 🟢 搬入 | 直接複製進 windMindOM v0.8.1 repo |
| 🟡 已現代化 | v0.5 → v0.8.1 過程中已單獨更新過，本 session 只比對確認，不再覆蓋 |
| 🔴 棄用 | 屬 v0.5 過度工程的副產物，被 DEC-20260502-06 取代，**不搬** |

---

## 2. 🟢 搬入清單（本 session 動的事）

| v0.5 路徑 | windMindOM 目的地 | 用途 |
|-----------|------------------|------|
| `docs/pitch_deck.md` | `docs/sales/pitch_deck_v0.5_baseline.md` | -04 改版的 narrative baseline |
| `docs/pitch_deck.pptx` | `docs/sales/pitch_deck_v0.5_baseline.pptx` | -04 改版的視覺 / 投影片結構參考 |

合計 2 檔，~66 KB。

---

## 3. 🟡 已現代化（diff 比對結果，無需動作）

| 檔案 | 現況版本 | v0.5 版本 | 結論 |
|------|---------|-----------|------|
| `docs/routines/daily-workflow.md` | v1.1（2026-05-03，路徑與 issue 前綴已修） | v1.0（2026-05-02） | 沿用現況 |
| `templates/issue-template.md` | M1-M6+（無 M0） | M0-M6+ | 沿用現況 |
| `templates/decision-template.md` | v0.8.1 對齊 | v0.5 | 沿用現況 |
| `templates/work-log-template.md` | v0.8.1 對齊 | v0.5 | 沿用現況 |
| `templates/design-note-template.md` | 兩邊內容相同 | 同 | 無 diff |
| `docs/claude-code-templates/README.md` | v0.8.1 | v0.5 | 沿用現況 |
| `docs/claude-code-templates/agents/code-reviewer.md` | v0.8.1 | v0.5 | 沿用現況 |
| `docs/claude-code-templates/commands/{daily-start,claim-issue,daily-wrapup,review}.md` | v0.8.1 | v0.5 | 沿用現況 |

---

## 4. 🔴 棄用清單（v0.5 有但 windMindOM v0.8.1 不要）

對應 [`decision_log.md`](../product/decision_log.md) DEC-20260502-06「v0.5 → v0.8.1 pivot」。
本檔把「決策面」拍板過的「具體檔案」明列出來，方便日後回溯。

### 4.1 過度工程的設計文件（被 monolithic 5 modules 取代）

| v0.5 檔案 | 為什麼不搬 | 取代方案 |
|-----------|----------|--------|
| `docs/MIGRATION_TO_CLAUDE_CODE.md`（306 行） | 描述「整合容器 → Claude Code 原生」的遷移路徑，但 v0.8.1 不再走容器架構 | `CLAUDE.md` 已寫清楚 v0.8.1 開發守則 |
| `docs/ASSETS_MAP.md`（437 行） | 描述「8 個來源 repo 的可重用模組」框架，預設容器/plugin 架構 | `CLAUDE.md` §5「與其他 7 個 repo 的關係」已用更精簡的方式列清楚 |
| `docs/PRODUCT_VISION.md`（v0.2 框架版） | 「核心 + 可插拔模組」框架定位 | `docs/product/PRODUCT_VISION.md` v0.8.1（運維廠商工具定位） |
| `docs/MVP_ARCHITECTURE.md`（v0.2 容器版） | 整合容器 + Plugin SDK 設計 | `docs/product/MVP_ARCHITECTURE.md` v0.8.1（5 modules monolith） |
| `docs/decision_log.md`（v0.5 部分） | 早期決策已被 DEC-20260502-06 翻案 | 新 `docs/product/decision_log.md` 從 DEC-20260502-06 起算 |
| `docs/adapters/simulator_notes.md` | 對應 v0.5「TurbineAdapter ABC + 4 類 plugin」框架 | M1 simulator 直接用 `modules/monitoring/` 既有 digiWT 程式，不抽 ABC |
| `docs/design_notes/README.md` | 預期裝 z72_etech 取材結果 | M3 真的取材時直接放 `docs/design_notes/` 即可，模板不重要 |
| `docs/session_handoff.md` | v0.5 框架時期的 session-to-session 接手紀錄 | windMindOM 改用 `work-logs/YYYY-MM/YYYY-MM-DD-{slug}.md` per-session |

### 4.2 對應的程式碼/scaffolding（不搬）

| v0.5 路徑 | 為什麼不搬 |
|-----------|----------|
| `api/adapters/`（SimulatorAdapter、Z72Adapter ABC 雛形） | v0.8.1 不抽 adapter ABC（只一個 OEM 用不到） |
| `api/main.py` / `api/auth.py` / `api/config.py` / `api/models/` | 整合容器骨架 — windMindOM 直接用 `modules/monitoring/server/` 既有 FastAPI |
| `alembic/` + `alembic.ini` | DB migration 框架 — M3-M4 真的需要時再導入 |
| `infra/` | 容器 infra 設定 — windMindOM 用 `modules/monitoring/` 既有 docker-compose |
| `windmindom.egg-info/` | 過渡期 setuptools 產物 — 不搬 |
| `pyproject.toml` | v0.5 的 pyproject 對 plugin SDK；v0.8.1 暫保 `requirements.txt`，pyproject 整合留 M2+ |
| `tests/` | 測試是 v0.5 adapter ABC 的 unit test — 與 v0.8.1 5 modules 不對應 |
| `work-logs/` | v0.5 的 session 紀錄 — 留在 `windFarmOM_bk/` 即可，不搬到本 repo |

### 4.3 文件流（不搬）

| v0.5 檔案 | 為什麼不搬 |
|-----------|----------|
| `BOOTSTRAP.md` | v0.5 開站文件 — 由 `CLAUDE.md` 取代 |
| `CHANGELOG.md` | v0.5 還沒進 release cycle — 暫不需要 |
| `STATUS.yaml` / `ISSUES.md` / `TODO.md` | 對應 v0.5 issue 編號與 milestone — windMindOM 已重建（M1-M6 + WMOM-* ID） |
| `README.md` | v0.5 容器架構 README — windMindOM v0.8.1 用 `CLAUDE.md` 替代主入口（README 之後再寫） |
| `CLAUDE.md`（v0.5 版） | v0.5 框架版守則 — 已被 windMindOM 根目錄 v0.8.1 `CLAUDE.md` 取代 |
| `docker-compose.yml` | v0.5 容器層編排 — windMindOM 用 `Dockerfile` + `docker-compose.yml`（已搬入 monitoring 後更新） |

---

## 5. v0.5 → v0.8.1 對應表（一目了然）

```
v0.5 框架（容器 + plugin）              v0.8.1 monolith（運維廠商工具）
────────────────────────────────       ─────────────────────────────────
docs/PRODUCT_VISION.md (v0.2)     →   docs/product/PRODUCT_VISION.md (v0.8.1)
docs/MVP_ARCHITECTURE.md (v0.2)   →   docs/product/MVP_ARCHITECTURE.md (v0.8.1)
docs/ASSETS_MAP.md                →   CLAUDE.md §5（精簡版）
docs/MIGRATION_TO_CLAUDE_CODE.md  →   CLAUDE.md §6 daily routine
docs/pitch_deck.{md,pptx}         →   docs/sales/pitch_deck_v0.5_baseline.{md,pptx}
                                       → -04 改版為 pitch_deck_v0.8.1.{md,pptx}
docs/adapters/simulator_notes.md  →   無（M1 直接用 digiWT 程式，不抽 ABC）
docs/design_notes/README.md       →   無（真要取材時再建）
api/adapters/{simulator,z72}.py   →   modules/monitoring/（既有 digiWT 程式）
docs/decision_log.md (v0.5)       →   docs/product/decision_log.md（DEC-20260502-06 起）
```

---

## 6. 後續建議（不在本 issue 範圍）

- 若 M2-M3 結束後 `windFarmOM_bk/` 確定無人引用，可整資料夾搬到外部歸檔目錄或刪除
  （git history 已保留，不會丟失）
- 本 inventory 不建議反覆刷新；只在「又從 v0.5 撿東西」或「決定動 archive」時更新

---

> 維護者：本檔案隨 WMOM-20260503-02 一起 commit；後續變動請在 commit message 帶 `#WMOM-20260503-02` 或新 issue 編號
