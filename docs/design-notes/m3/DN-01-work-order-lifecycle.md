# DN-01: Work Order Lifecycle

> Design note 對應 [WMOM-20260504-14](../../../ISSUES.md)。
> Status: 雛形 done（2026-05-04）— 待 walkthrough 確認後實作 [WMOM-20260504-16](../../../ISSUES.md) (domain) + [-17](../../../ISSUES.md) (CRUD/API)。
> Source: `windFarmMonitor/z72_SCADA_etech/yitai-corp-cms-download1140811/server/{repair,repairTemp,trackFrom,removeFrom}.js`

---

## 1. etech onshore baseline（如何運作）

etech 用 **4 個 MongoDB collection** 表達工單生命週期：

| Collection | 角色 | 關鍵欄位 | 生命週期 |
|-----------|------|---------|---------|
| `repairTemp` | **派工暫存單**（draft + dispatched + in_progress） | `Hnumber` (風機 ID), `totalformnumber` (跨表 business key), `repairname` (維修人), `errorinfo` | 維修進行中持續 PUT 同 `_id`，每次 PUT 等於一次「下一步」 |
| `repair` | **完工正式單** | `chooseschange ∈ {完成, 追蹤觀察, 需改善}`, `workfinish`, `nofinish`, `logformstate` | 工單完工時 POST 進來；同時 insert `allForm` 為 audit |
| `trackFrom` | **追蹤觀察單**（後續追蹤） | `Hnumber`, `totalformnumber` (parent), `problem` (= repair.nofinish), `readname[]` (已讀) | 工單 POST 時若 `chooseschange ∈ {追蹤觀察, 需改善}` → 自動 insert |
| `removeFrom` | **移除單** | `currentDate`, no totalformnumber visible | (use case 不明，**walkthrough 待確認**) |

外加：
- `allForm` — 全工單 audit collection，POST repair 時順便 insert（純複製，無 schema enforcement）

### 1.1 流程 step-by-step（典型工單）

```
T0  維修人開單                   POST /api/repairTemp
                                 → repairTemp doc with Hnumber, errorinfo, repairname
                                                                    │
T1  維修進行中（多次更新）         PUT /api/repairTemp/:id (or /totalForm/:totalformnumber)
                                 → 改 status / 補資料 / 加維修步驟
                                                                    │
T2  完工確認                     POST /api/repair
                                 ├─ insert repair doc (含 chooseschange)
                                 ├─ insert allForm doc (audit)
                                 └─ if chooseschange ∈ {追蹤觀察, 需改善}
                                       └─ insert trackFrom doc
                                                                    │
T3  簽核（4 個並行 collection）    詳見 DN-02
                                                                    │
T4  追蹤觀察（如有）              GET /api/trackFrom/tag/:Hnumber
                                 PUT /api/trackFrom/:id（補 readname）
```

### 1.2 chooseschange 三分類（onshore 業務語意）

| 值 | 意義 | 後續動作 |
|----|------|---------|
| `完成` | 工單已關閉 | 無 followup |
| `追蹤觀察` | 已修但需後續觀察（如剛換的零件） | 自動建 trackFrom |
| `需改善` | 尚未真正解決 | 自動建 trackFrom；下次再開新 repair 工單繼續 |

⚠ Walkthrough question: 「追蹤觀察」與「需改善」對 SLA / KPI 的差別是什麼？是不是該縮為布林 `needs_followup`？

### 1.3 etech 設計反模式（windMindOM 要避免）

| Anti-pattern | 為何不好 | windMindOM 對策 |
|-------------|---------|---------------|
| `repairTemp` + `repair` 兩個 collection | 同一份工單跨兩個 collection 表達狀態，前端 1674 行 if 串才能正確切換 | **單一 `work_order` 表** + `status` 欄位 + 狀態機 transitions |
| `trackFrom` 獨立 root entity | trackFrom 與 parent repair 用 `totalformnumber` 軟連結，沒 FK，可孤兒 | `work_order_followup` 子表 + 真 FK |
| `removeFrom` 獨立 root entity | use case 不明，無 frontend 入口 | **不做** — 移除工單 = `status = 'cancelled'` 不另開表 |
| `allForm` audit copy | 每次都複製整份 doc，不可序列化、無時間排序保證 | **event log 表** (event-sourcing-lite) — 紀錄狀態 transition + actor + timestamp |
| 4 個 sign collection | 是 DN-02 主題 — 應統合為 `signoff` + `level` | DN-02 |
| business key + ObjectId 雙軌 | etech 用 `totalformnumber` 跨 collection 軟連結 + `_id` 各 collection 內 hard link，雙寫易漂移 | **保留 business key 給人類讀**（list / report / 列印），對外 API 與 FK 全用 surrogate UUID |

---

## 2. windMindOM 設計

### 2.1 單一 `work_order` 表 + 狀態機

```python
# modules/workflow/domain/work_order.py

class WorkOrderStatus(str, Enum):
    DRAFT             = "draft"              # 維修人開單但還沒派工
    DISPATCHED        = "dispatched"         # 已派工，等待人員 / 船 / WW
    IN_PROGRESS       = "in_progress"        # 維修進行中
    AWAITING_SIGNOFF  = "awaiting_signoff"   # 完工等簽核（流程進 DN-02）
    CLOSED            = "closed"             # 完整關閉
    CANCELLED         = "cancelled"          # 取消（替代 etech removeFrom）
    REOPENED          = "reopened"           # 已關但因 followup 重開（chooseschange='需改善' 場景）


class WorkOrderType(str, Enum):
    CORRECTIVE   = "corrective"    # 故障維修
    PREVENTIVE   = "preventive"    # 預防性保養（PM）
    INSPECTION   = "inspection"    # 定檢
    COMMISSIONING = "commissioning" # 試運轉


class FollowupKind(str, Enum):
    NONE              = "none"            # 完工無後續
    OBSERVATION       = "observation"     # 追蹤觀察（onshore '追蹤觀察'）
    NEEDS_IMPROVEMENT = "needs_improvement"  # 需改善 → 會自動建 followup work_order
```

### 2.2 狀態機 transitions

```
                              ┌─────────────────────┐
                              │       DRAFT         │
                              │ 維修人 / SCADA 警報自動建單 │
                              └──────────┬──────────┘
                                         │ dispatch (派工人員 / 船 / WW)
                                         ▼
                              ┌─────────────────────┐
                              │     DISPATCHED      │
                              │ 已分配人 + 預計時間   │
                              └──┬───────────────┬──┘
                       cancel (─┘               │ start_work
                       任何前置                  ▼
                       階段都可)        ┌─────────────────────┐
                                      │    IN_PROGRESS      │
                                      │ 維修進行中（可多次更新） │
                                      └──┬───────────────┬──┘
                              cancel ────┘               │ finish + chooseschange
                                                         ▼
                                              ┌─────────────────────┐
                                              │  AWAITING_SIGNOFF   │
                                              │ 工單交簽核（DN-02）  │
                                              └──┬───────────────┬──┘
                                       reject ───┘               │ approve_all
                                       (回 IN_PROGRESS)            ▼
                                                          ┌─────────────────────┐
                                                          │       CLOSED        │
                                                          └──────────┬──────────┘
                                                                     │ reopen (followup '需改善' 觸發)
                                                                     ▼
                                                          ┌─────────────────────┐
                                                          │      REOPENED       │
                                                          └──────────┬──────────┘
                                                                     │ start_work（回 IN_PROGRESS）
                                                                     ▼
                                                                   (循環)

  CANCELLED (terminal)：對應 etech 「removeFrom」 use case，但不建獨立 collection
```

#### Transition table（domain layer 用）

| Transition | From | To | Guard 條件 | 觸發 actor |
|-----------|------|-----|-----------|----------|
| `dispatch` | DRAFT | DISPATCHED | `assignee_id` 非空 + `farm_id` 非空 | 班長 / dispatcher |
| `start_work` | DISPATCHED | IN_PROGRESS | （offshore 額外）`vessel_id`、`weather_window_id` 已綁 | 維修人 |
| `start_work` | REOPENED | IN_PROGRESS | — | 維修人 |
| `update_progress` | IN_PROGRESS | IN_PROGRESS | — | 維修人 |
| `finish` | IN_PROGRESS | AWAITING_SIGNOFF | `followup_kind` 已填 + `actual_hours` 已填 | 維修人 |
| `approve_all` | AWAITING_SIGNOFF | CLOSED | 所有必要 signoff 階段都 approved（DN-02） | system |
| `reject` | AWAITING_SIGNOFF | IN_PROGRESS | 任一 signoff 階段 rejected | 簽核人 |
| `cancel` | DRAFT \| DISPATCHED \| IN_PROGRESS | CANCELLED | 帶 `cancel_reason` | 班長 / 主管 |
| `reopen` | CLOSED | REOPENED | followup_kind == NEEDS_IMPROVEMENT 觸發；或人工 | system / 主管 |

### 2.3 Schema（含 offshore 延伸）

```python
@dataclass
class WorkOrder:
    # ── primary identity ─────────────────────────
    id: UUID                                # surrogate (FK 用)
    business_key: str                       # 人類可讀 "WO-{farm_id}-{yyyymm}-{nn}"
                                            # 對應 etech totalformnumber

    # ── core ─────────────────────────────────────
    farm_id: str                            # = monitoring/farm_registry farm_id
    turbine_id: str                         # 14 台中哪一台（etech Hnumber 對應）
    type: WorkOrderType
    status: WorkOrderStatus
    title: str                              # 一句話描述
    description: str                        # 詳細問題

    # ── 來源（可選 — alarm-driven）────────────────
    source_alarm_id: UUID | None            # M5 alarm event 觸發的工單會帶
    source_alarm_code: str | None           # 同 SCADA 警報碼（給 RAG 用）

    # ── 派工 ─────────────────────────────────────
    assignee_id: UUID | None                # 維修人 (≡ etech repairname)
    crew_size: int = 1                      # 人數 (offshore 通常 ≥ 2)
    estimated_hours: float | None = None
    dispatched_at: datetime | None = None
    dispatched_by: UUID | None = None

    # ── offshore 延伸 ────────────────────────────
    vessel_id: UUID | None = None           # CTV / SOV / Jack-up（M3 reserved，M6 才用）
    weather_window_id: UUID | None = None   # 對應 K13 cost engine WW index
    logistic_hours: float | None = None     # 來回航程（給 cost ledger M4 用）

    # ── 進行 ─────────────────────────────────────
    started_at: datetime | None = None
    progress_notes: list[ProgressNote] = field(default_factory=list)
                                            # 維修人多次 update 寫進來（取代 etech 原地 PUT）

    # ── 完工 ─────────────────────────────────────
    finished_at: datetime | None = None
    actual_hours: float | None = None
    work_summary: str | None = None         # ≡ etech workfinish
    unfinished_items: str | None = None     # ≡ etech nofinish
    followup_kind: FollowupKind = FollowupKind.NONE  # ≡ etech chooseschange
    followup_note: str | None = None        # ≡ etech logformstate / errorinfo

    # ── 領料 / 物料（DN-03 補完，這裡先列佔位）────
    material_request_ids: list[UUID] = field(default_factory=list)

    # ── 簽核（DN-02）─────────────────────────────
    signoff_chain_id: UUID | None = None    # 對應的 signoff workflow

    # ── 取消 / 結案 ──────────────────────────────
    closed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None

    # ── audit（取代 etech allForm collection）────
    created_at: datetime
    created_by: UUID
    updated_at: datetime
    # 完整 transition history 不在這個 dataclass，去查 work_order_event_log 表
```

### 2.4 衍生 entity

```python
@dataclass
class WorkOrderFollowup:
    """≡ etech trackFrom，但用真 FK 連到 parent。"""
    id: UUID
    parent_work_order_id: UUID              # FK 強制
    kind: FollowupKind                      # OBSERVATION | NEEDS_IMPROVEMENT
    problem: str                            # ≡ trackFrom.problem (= parent.nofinish)
    read_by: list[UUID] = field(default_factory=list)  # ≡ trackFrom.readname
    resolved: bool = False
    resolved_at: datetime | None = None
    spawned_work_order_id: UUID | None = None  # 若 kind==NEEDS_IMPROVEMENT 自動建新工單，連回來


@dataclass
class WorkOrderEventLog:
    """≡ etech allForm，但是真 event log（不是 doc copy）。"""
    id: UUID
    work_order_id: UUID
    event_type: str                         # "created" | "dispatched" | "started" | ...
    from_status: WorkOrderStatus | None
    to_status: WorkOrderStatus | None
    actor_id: UUID | None
    payload: dict                           # 額外欄位（如 cancel_reason、reject_comment）
    occurred_at: datetime
```

### 2.5 Business key 規則

```
WO-{farm_id_short}-{YYYYMM}-{NN}

範例：
  WO-Z72TC-202607-01     # 台中港曲風場（Z72 / TC short code）2026-07 第 1 張
  WO-OFFC1-202607-15     # 彰化離岸 1（OFFC1 short code）2026-07 第 15 張
```

- `farm_id_short`：farm 的短碼（從 farm registry config 帶；無則退到 hash 前 5 碼）
- `NN`：當月流水序，每月歸零
- 全系統用 surrogate UUID 做 FK，business key 只給 UI / report / 列印用
- 與 etech `totalformnumber` 的設計一致（人類友善）但底層更乾淨

---

## 3. 與其他 module 的整合點

```
┌──────────────────┐  alarm-driven       ┌──────────────────┐
│  M5 Alarm /      │ ──────────────────► │  M3 Work Order   │
│  RAG (knowledge) │  (source_alarm_id)  │                  │
└──────────────────┘                     └────────┬─────────┘
                                                  │
                       ┌──────────────────────────┼──────────────────────────┐
                       │                          │                          │
                       ▼                          ▼                          ▼
              ┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
              │  M3 Signoff      │      │  M4 Material     │      │  M4 Cost Ledger  │
              │  (DN-02)         │      │  Request →       │      │  (WMOM-11 +      │
              │                  │      │  Inventory       │      │   WMOM-10 farm)  │
              │  signoff_chain_id │      │  (DN-03)         │      │                  │
              └──────────────────┘      └──────────────────┘      └──────────────────┘
                                                                            ▲
                                              completion of WO emits        │
                                              actual cost entries ──────────┘
                                              (labour + material + equipment + revenue_loss)
```

### 3.1 與 M4 cost ledger 的綁定（前置設計）

工單 closed 時應 emit 4 種 ledger entry：

| Ledger entry | 從 work order 哪裡算 |
|-------------|-------------------|
| `labour` | `actual_hours × crew_size × tech_hourly_rate` |
| `material` | sum of material_requests 對應 inventory cost |
| `equipment / vessel` | `logistic_hours + actual_hours × vessel.day_rate` (offshore only) |
| `revenue_loss` | `(closed_at - source_alarm.occurred_at) × turbine.expected_power × farm.kwh_price` |

⚠ 這些公式直接對應 K13 cost engine seasonal_results 的 corrective_wt_* 欄位（cost engine 算的是預測，這裡算的是實際 = 給 actual vs predicted 對比）。

### 3.2 與 M5 RAG 的綁定

- 工單建立時帶 `source_alarm_code`（SCADA 警報碼）
- 工單 detail page 上有 "RAG 建議" 區塊：用 `source_alarm_code` 查 vector store
- 工單 closed 後可選擇把 `work_summary` 餵回 RAG（成為 corpus 的一部分；M6+）

---

## 4. 對應劉老師 onshore → offshore 軸線

| 事項 | onshore（etech baseline） | offshore（windMindOM 延伸） |
|-----|--------------------------|---------------------------|
| 故障 → 派工單 | repairTemp 建單 | 同 + 增 `vessel_id` 預留 |
| 檢修 | 維修人原地 PUT | progress_notes append（不就地覆寫，留追蹤） |
| 每日工作日誌 | dayworkForm 獨立 collection | M3+ 後續評估：合併 work_order.progress_notes 還是獨立 |
| 簽核 | leadersign / supervisorsign 等 | DN-02：統一 signoff + level |
| 領料連庫存 | materialsForm + 4 欄位 inventory | DN-03 + M4 雙寫交易 |
| 連結人員 | repair.repairname (string!) | UUID FK 到 personnel |
| **離岸延伸** | — | weather_window / vessel / crew_size / logistic_hours（K13 cost 維度對齊） |

---

## 5. Open questions（walkthrough 待確認）

| # | 問題 | 影響 |
|---|------|------|
| Q1 | etech `removeFrom` 的真實 use case 是什麼？看不到 frontend 入口 | 決定 windMindOM CANCELLED state 是否要保留 cancel_reason 強制欄位 |
| Q2 | `chooseschange` 的「追蹤觀察」vs「需改善」業務上 SLA 差異？需保留二分還是縮成布林？ | 決定 FollowupKind enum 要 3 還是 2 值 |
| Q3 | 一台風機可同時有多張 OPEN 工單嗎？（ECN K13 假設一機一機停） | M3 unique constraint 設計 |
| Q4 | etech 沒有 PM / inspection 工單，全是 corrective — windMindOM 是否預留 4 種 type？ | M3 schema 是否一次設計到位（建議是） |
| Q5 | 離岸案例 weather_window block 工單，但 etech 沒這概念。`weather_window_id` 是 hard FK 還是可空？ | 我設計可空（onshore 不用），但 offshore start_work guard 強制要求 |
| Q6 | dayworkForm（每日工作日誌）是 work_order 的子實體，還是獨立 entity？etech 是獨立 | 預設保留獨立 entity 不合併 work_order，等 M3 後續評估 |
| Q7 | 工單與「定檢清單 regularlistForm」的關係？etech 是並行兩個系統 | M3 暫不合併；設計 work_order.type=INSPECTION 預留入口 |

---

## 6. 結論 / 下一步

- ✅ DN-01 雛形 done
- ⬜ DN-02 Approval Multi-level（下次 session）
- ⬜ DN-03 Inventory ↔ Material Request（下次 session）
- ⬜ Walkthrough 7 個 Q（[WMOM-20260504-15](../../../ISSUES.md)）
- ⬜ 實作 [WMOM-20260504-16](../../../ISSUES.md) domain model + state machine（依本 DN）

## 7. Walkthrough notes

> 待 [WMOM-20260504-15](../../../ISSUES.md) walkthrough 後填入劉老師確認 / 修正內容。
