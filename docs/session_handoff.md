# Session Handoff — 給下次 session 用

> 最後更新：2026-05-05（end of session — M3 設計階段全結束）
> 本檔在 routine 收尾時更新；新 session 開工讀完 CLAUDE.md / ROADMAP / ISSUES 後可看這份知道「上次卡在哪、下次怎麼接」。

---

## 1. 今天（2026-05-05）的 session 整體軸線

進到 **M3 主線設計收官 + 實作前夕**。本日做了三件事：

### 1.1 WMOM-20260505-01 — Snapshots 表失控 hotfix（**done**）

- 彰化 farm `wind_farm.db` 17.5 天累積 41.9 GB（1080 萬筆 turbine_snapshots，98.9% 是 retroactive write 重複）
- 三個放大因子（cleanup 沒清 + broker 重 retroactive + simulator stop=7 flapping）全修
- VACUUM 工具加 `--purge-snapshots` 救火 flag
- PR #3 merged，劉老師執行 `--purge-snapshots` 釋放 41 GB ✓
- DEC-20260505-01 寫進 decision_log

### 1.2 WMOM-20260504-14 — z72_etech 取設計 + 3 份 DN（**done**）

- DN-01 Work Order Lifecycle（含 walkthrough Q&A 整合 + schema 微調）
- DN-02 Approval Multi-level（4 階 signoff + chain 設計 + reject 行為）
- DN-03 Inventory ↔ Material Request（3 欄位庫存 + 雙寫交易 + 退料分類）
- 詳見：[`docs/design-notes/m3/`](design-notes/m3/)

### 1.3 WMOM-20260504-15 — Walkthrough（**done — 與 -14 合併走完**）

- 17 個 Q（DN-01 7 + DN-02 5 + DN-03 5）劉老師全 agree default
- 唯一補充：DN-03 D3-Q2「歸還流程紙本由庫管員填單管理」（系統不做歸還流程，但提供 inventory adjustment endpoint）
- 衍生兩個 issue：
  - **WMOM-20260505-21** — `day_work_form` 員工日誌（DN-01 Q6 衍生）
  - **WMOM-20260505-22** — `inspection_schedule` 定檢計畫 + auto-spawn PM 工單（DN-01 Q7 衍生）

---

## 2. Branch / PR 狀態

```
main (HEAD = c5491fc — PR #2 + PR #3 merged)
 │
 └─ claude/issue-20260504-15-walkthrough-2026-05-05  ← 本 session 工作（待 push）
       └ DN-01 修訂 + DN-02 + DN-03 + walkthrough notes + ISSUES/STATUS update
```

下個動作：commit + push + 開 PR #4

---

## 3. 下次 session 第一件事：M3 實作開工

設計階段全結束，沒卡點。直接進 M3 主線實作：

### 優先順序

| Issue | 預估 | 依賴 | 重點 |
|-------|------|------|------|
| **WMOM-20260504-16** Work Order domain + 狀態機 | 1 天 | 無（DN-01 已寫完） | 純 dataclass + Enum + state machine + tests，不接 SQLAlchemy/FastAPI |
| WMOM-20260504-17 Work Order CRUD + REST API | 1 天 | -16 | SQLAlchemy ORM + FastAPI router + 完整 tests |
| WMOM-20260504-18 Approval signoff API | 1 天 | -14 DN-02 + -17 | signoff_chain + signoff_step + reject 回退邏輯 |
| WMOM-20260504-19 frontend orders | 1-1.5 天 | -17 | 建立精靈 + 列表 + 詳情 |
| WMOM-20260504-20 frontend approval | 1 天 | -18 + -19 | 待簽列表 + 簽核 dialog |

→ 預計 5-6 個工作日跑完 M3 主線實作。

### 不做的事（避免反覆討論）

- 不在 M3 做 inventory 雙寫交易（DN-03 設計但 M4 才實作）
- 不在 M3 做 day_work_form / inspection_schedule（衍生 WMOM-21/-22，M3 後續再開）
- 不對 etech 8 萬行 Vue 程式做任何引用（取材選 A 原則）

---

## 4. 已不需要 walkthrough（17 個 Q 全 confirmed）

| DN | Q 數 | 結果 |
|----|------|------|
| DN-01 | 7 | 全 confirmed（含 Q2 採我建議「縮二元 + Priority enum」） |
| DN-02 | 5 | 全 agree default |
| DN-03 | 5 | 全 agree default + 1 補充 |

詳見對應 DN 文件 §「Walkthrough Q&A」表格。

---

## 5. M3 後續 backlog（不阻塞主線）

| Issue | Status | 何時做 |
|-------|--------|--------|
| WMOM-20260505-21 day_work_form | open | M3 主線跑完後 / M4 之間 |
| WMOM-20260505-22 inspection_schedule | open | 同上 |
| WMOM-20260504-13 cost dataset race condition (low) | open | M5 / M6 |
| WMOM-20260504-12 frontend memory leak 觀察 | open | M5 / M6 |

---

## 6. 環境狀態提示

- Git: clean working tree on `claude/issue-20260504-15-walkthrough-2026-05-05`，待 commit + push
- Pytest: 84 PASS + 1 XFAIL（cost 49 + monitoring 35 含 hotfix 19 個）
- Frontend: Vite build pass
- DB: 彰化 farm `wind_farm.db` ~50 MB（VACUUM 後正常運作中）
- 三份 DN 全 done — 設計層面 source of truth 已 stable
