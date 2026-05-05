# 2026-05-05 — Walkthrough + DN-02 / DN-03（WMOM-20260504-14 / -15）

> Session 類型：取材 + 設計 + walkthrough（一次合併）
> Session 長度：中
> 主導：Claude + 劉老師（17 個 Q 逐一答覆）
> 結果：M3 設計階段全結束 — 三份 DN 全 done + walkthrough confirmed

---

## 1. Session 目標

接續上次（DN-01 雛形 done）：
- 補完 DN-02 Approval Multi-level + DN-03 Inventory ↔ Material Request
- 跑一次 walkthrough 跟劉老師確認三份 DN（共 17 個 Q）
- 結 WMOM-14 + WMOM-15

策略：一次合併 walkthrough 跟 design — 我給 default 建議 + 劉老師「✓ / 改」，不做兩階段。

---

## 2. 實際完成

### 2.1 主要工作

- ✅ **DN-01 修訂**：劉老師 7 Q 答覆寫進 §5（取代原 open questions）+ schema 微調：
  - FollowupKind 從 3 元縮成 2 元（NONE / FOLLOWUP_NEEDED）
  - 新增 `Priority` enum 取代 followup 的「嚴重度」
  - 加 multi-WO constraint 設計（unique on `(turbine_id, source_alarm_code)` + 應用層 ≤ 3 OPEN/turbine）
  - §3.3 加「inspection auto-spawn + day_work_form 對應」整合圖
  - §7 walkthrough notes 完整紀錄
- ✅ **DN-02 完整寫**：Approval Multi-level（4 階 signoff + 3 表結構 + chain policy + reject 行為 + 整合點）
  - 5 個 walkthrough Q 全 agree default
- ✅ **DN-03 完整寫**：Inventory + Material Request（3 欄位庫存 + MaterialRequest 狀態機 + 雙寫交易 + 退料 4 種分類 + 多倉預留）
  - 5 個 walkthrough Q 全 agree default + 補充「歸還流程紙本由庫管員填單管理」
- ✅ **README 更新**：三份 DN 全 done 標記 + walkthrough 完成記錄
- ✅ **ISSUES.md**：
  - WMOM-14 in_progress → done
  - WMOM-15 open → done
  - WMOM-01 in_progress → done（PR #3 確認 merged + VACUUM 釋放成功）
  - 新增 WMOM-21 day_work_form 衍生 issue
  - 新增 WMOM-22 inspection_schedule 衍生 issue
  - 統計：open 10 / in_progress 0 / done 17 / total 27
- ✅ **STATUS.yaml**：M3 progress 10 → 35（設計全結束）；project progress 54 → 60

### 2.2 17 個 walkthrough Q 結果

| DN | Q 數 | 全部結果 |
|----|------|---------|
| DN-01 | 7 | Q1-Q7 全 confirmed（含 Q2 採我建議「縮二元 + Priority enum」） |
| DN-02 | 5 | D2-Q1..Q5 全 agree default |
| DN-03 | 5 | D3-Q1..Q5 全 agree default + 補充 D3-Q2「紙本由庫管員填單」 |

### 2.3 卡住或延後的事

- 無

### 2.4 重大決策

- **WMOM-21** + **WMOM-22** 衍生 issue 為 M3 後續 / M4 之間做（不阻塞 M3 主線 7 sub-issue）
- DN-03 雙寫交易 + inventory adjustment endpoint 是 M4 主菜（M3 只先做 placeholder schema 給 work_order.material_request_ids 依賴）

---

## 3. 產出清單

### 新增檔案

- `docs/design-notes/m3/DN-02-approval-multilevel.md`（~240 行）
- `docs/design-notes/m3/DN-03-inventory-material-request.md`（~290 行）
- `work-logs/2026-05/2026-05-05-walkthrough-and-dn02-dn03.md`（本檔）

### 修改檔案

- `docs/design-notes/m3/DN-01-work-order-lifecycle.md`（walkthrough Q&A 整合 + schema 微調）
- `docs/design-notes/m3/README.md`（三份 DN 全 done 標記）
- `ISSUES.md`（WMOM-14/-15/-01 done + WMOM-21/-22 衍生 + 統計）
- `STATUS.yaml`（progress 60% / M3 35%）

### 動了狀態的 issue

- WMOM-20260504-14: in_progress → done
- WMOM-20260504-15: open → done
- WMOM-20260505-01: in_progress → done（追認 PR #3 merge + VACUUM 完成）
- WMOM-20260505-21: 新增 open（day_work_form 衍生）
- WMOM-20260505-22: 新增 open（inspection_schedule 衍生）

## 4. 下次怎麼接手

進 M3 主線實作：

1. **WMOM-20260504-16 — Work Order 領域模型 + 狀態機**（pure domain，1 工作天）
   - 依 DN-01 §2 寫 `modules/workflow/domain/work_order.py`
   - `WorkOrderStatus` / `WorkOrderType` / `FollowupKind` / `Priority` enum
   - State machine + transition guard + tests
2. **WMOM-20260504-17 — Work Order CRUD + REST API**（依賴 -16）
3. **WMOM-20260504-18 — Approval Signoff API**（依 DN-02）
4. **WMOM-20260504-19/-20 — frontend**（依賴 -17/-18）

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 寫 DN-02 | 30% |
| 寫 DN-03 | 30% |
| DN-01 修訂 + walkthrough 整合 | 20% |
| ISSUES / STATUS / work-log 維護 | 15% |
| Commit / PR | 5% |

## 6. 學到的事

- 「給 default 建議 + 用戶 ✓ / 改」遠比「列開放性 question 等用戶從零想答」高效。10 個 Q 用戶不到 2 分鐘答完，且結果跟我預期一致 → 表示我對 etech 的 inventory + 領域知識基礎夠
- DN-01 雛形跟 walkthrough 分兩階段是個錯覺需求 — 一次到位更乾淨（避免 schema 反覆改）
- 衍生 issue（WMOM-21/-22）不要硬塞進 M3 主線，標清「M3 後續 / M4 之間」更安全

## 7. Open questions（park）

- 何時跑 PR review？（劉老師確認後 merge 即可）
- WMOM-16 Work Order domain 落地是否要先做 SQLAlchemy ORM 或先 pure dataclass？（傾向 pure dataclass 先，CRUD 階段再加 ORM）
