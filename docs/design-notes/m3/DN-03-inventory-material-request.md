# DN-03: Inventory ↔ Material Request（庫存與物料請領）

> Design note 對應 [WMOM-20260504-14](../../../ISSUES.md) 第三份。
> Status: done（2026-05-05 — walkthrough 一次完成）。
> 實作目標：M4（Workflow Part 2 — Inventory），M3 只設計、不實作。
> Source: `windFarmMonitor/z72_SCADA_etech/yitai-corp-cms-download1140811/server/{materialsForm,inventory,inventoryclassify,inventoryclassifylog,inventorynotic,inventoryreturn}.js`

---

## 1. etech onshore baseline

### 1.1 Inventory 4 欄位

每個料件 in `inventory` collection 帶四個 stock 欄位：

| 欄位 | 意義 | etech 用途 |
|------|------|-----------|
| 新品 | new / 全新未拆 | 工單優先用新品 |
| 良品 | refurbished / 維修後可用 | 庫存週轉 |
| 維修中 | repairing / 拆下送修 | 暫時鎖定，不可派出 |
| 待檢驗 | pending_inspection / 收貨後未驗 | 進貨流程必經 |

### 1.2 領料流程（`materialsForm` + 通知）

```
員工填領料單 ─POST /api/materialsForm─→ materialsForm
                                          │
                                          ├─ insert allForm（audit）
                                          │
                          ┌──── 簽核 chain ────┐
                          │  leadersign        │
                          │  affairsign (總務) │
                          └────────────────────┘
                                          │
                            出庫成功後通知：
                            - materialsFormNotic     （給總務看）
                            - materialsFormNoticLed  （給組長看）
                                          │
                                  料件實際到工單現場
```

### 1.3 退料 (`inventoryreturn`)

無分類 — 任何理由都進同一個 collection，只有 `reason: string`。

### 1.4 反模式清單（windMindOM 要避免）

| 反模式 | 為何不好 | windMindOM 對策 |
|-------|---------|----------------|
| 4 欄位庫存（新品 / 良品 / 維修中 / 待檢驗） | 「待檢驗」業務上很模糊（未檢驗等於不能用，跟「維修中」差不多） | **縮成 3 欄位** `available_new / available_used / repairing`（walkthrough D3-Q1 確認） |
| `materialsFormNotic` + `materialsFormNoticLed` 兩個通知 collection | 同一份通知對不同角色顯示 | 統一 `material_request_notification` 表 + `recipient_role` 欄位 |
| 領料單 business key 與工單分開（`materialformnumber` vs `totalformnumber`） | 兩種 ID 並存難管 | 都用 surrogate UUID + 各自 business key（`MR-...` for material req） |
| 退料無分類（reason 自由文字） | 無法 KPI 統計 | `ReturnReason` enum 4 種（walkthrough D3-Q4） |
| Stock 異動寫庫存 + 寫 ledger 兩個動作非 atomic | 異動半路斷會帳目漂移 | **DB transaction 雙寫**（M4 主要技術點） |

---

## 2. windMindOM 設計

### 2.1 Schema：3 個核心 entity

```python
# modules/workflow/domain/inventory.py

class StockKind(str, Enum):
    """3 欄位庫存（walkthrough D3-Q1 確認 — 從 etech 4 欄位簡化）。

    etech「待檢驗」併入「維修中」；如客戶堅持要「待檢驗」獨立，再加 PENDING_INSPECTION。
    """
    NEW       = "new"        # 全新
    USED      = "used"       # 良品（previously refurbished）
    REPAIRING = "repairing"  # 維修中 / 拆下送修 / 進貨待檢


@dataclass
class InventoryItem:
    """料件主檔。"""
    id: UUID
    sku: str                              # 業務料號
    name: str
    description: str
    unit: str                             # 個 / 公升 / 公斤
    farm_id: str                          # 該料件屬於哪個 farm（多 farm 各自管庫存）
    warehouse_id: UUID                    # walkthrough D3-Q5：M3 預設 single warehouse；多倉預留
    stock_new: int = 0
    stock_used: int = 0
    stock_repairing: int = 0
    safety_stock: int = 0                 # 低於此值告警
    unit_cost: Decimal                    # EUR — 給 cost ledger 用
    last_received_at: datetime | None = None
    last_used_at: datetime | None = None


@dataclass
class Warehouse:
    """倉庫主檔（walkthrough D3-Q5：M3 預設只有 1 個 default warehouse）。"""
    id: UUID
    name: str                             # "彰化離岸基地倉" / "工作船倉"
    farm_id: str
    location_kind: Literal["onshore_base", "vessel_storage", "offshore_platform"]
    is_default: bool = False
```

### 2.2 領料單：MaterialRequest + 子實體

```python
class MaterialRequestStatus(str, Enum):
    DRAFT             = "draft"             # 申請人剛建未送
    AWAITING_APPROVAL = "awaiting_approval" # DN-02 chain 跑中
    APPROVED          = "approved"          # 簽核通過，待出庫
    DISPATCHED        = "dispatched"        # 已出庫，待簽收
    RECEIVED          = "received"          # 領料人簽收
    USED              = "used"              # 工單關聯，已實際使用
    CLOSED            = "closed"            # 完工 + 退料 / 報廢處理完
    CANCELLED         = "cancelled"
    REJECTED          = "rejected"          # 簽核 reject 後（DN-02 D2-Q3）


@dataclass
class MaterialRequest:
    """領料申請單 — 對應 etech materialsForm。"""
    id: UUID
    business_key: str                     # "MR-{farm_id_short}-{yyyymm}-{nn}"
    farm_id: str
    work_order_id: UUID | None            # 關聯工單（可空 — 預備庫存補貨也可獨立發）
    requester_id: UUID                    # 申請人
    status: MaterialRequestStatus = MaterialRequestStatus.DRAFT

    # walkthrough D3-Q3：估計 vs 實際領料 都要記錄（給 cost ledger 算 actual vs predicted）
    items: list["MaterialRequestItem"] = field(default_factory=list)

    requested_at: datetime
    approved_at: datetime | None = None
    dispatched_at: datetime | None = None
    received_at: datetime | None = None
    closed_at: datetime | None = None

    # 簽核（DN-02）
    signoff_chain_id: UUID | None = None


@dataclass
class MaterialRequestItem:
    """單一料件請領明細（一張 MR 可帶多筆）。"""
    id: UUID
    request_id: UUID                      # FK
    item_id: UUID                         # FK to inventory_item
    estimated_qty: int                    # 申請時估計
    actual_qty: int | None = None         # 實際領用（簽收時填）— walkthrough D3-Q3
    stock_kind: StockKind = StockKind.NEW # 領哪個 stock 欄位（new vs used）


class ReturnReason(str, Enum):
    """退料原因分類（walkthrough D3-Q4 確認）。"""
    SURPLUS         = "surplus"          # 用剩
    WRONG_PART      = "wrong_part"       # 拿錯
    FAILED_INSTALL  = "failed_install"   # 試裝失敗
    OTHER           = "other"


@dataclass
class MaterialReturn:
    """退料記錄。"""
    id: UUID
    request_id: UUID                      # 對應領料單
    item_id: UUID
    qty: int
    reason: ReturnReason
    return_to_kind: StockKind             # 退回哪一欄（new / used / repairing）
    note: str | None = None
    returned_at: datetime
    returned_by: UUID
```

### 2.3 雙寫交易（M4 主菜）

關鍵不變式：**任一 stock 異動必須 atomic 寫 inventory + 寫 ledger entry**，否則帳目漂移。

```python
# modules/workflow/services/inventory_service.py

def dispatch_request(request_id: UUID) -> None:
    """出庫：扣 inventory + 寫 ledger，必須 atomic。"""
    with storage.transaction() as tx:
        req = tx.material_request.get(request_id)
        for item in req.items:
            inv = tx.inventory.lock_for_update(item.item_id)  # SELECT FOR UPDATE
            stock_attr = f"stock_{item.stock_kind.value}"
            current = getattr(inv, stock_attr)
            if current < item.estimated_qty:
                raise InsufficientStock(item)
            setattr(inv, stock_attr, current - item.estimated_qty)
            tx.inventory.update(inv)

            # ★ 同 transaction 內寫 ledger
            tx.cost_ledger.insert(CostLedgerEntry(
                farm_id=req.farm_id,
                category="material",
                amount=item.estimated_qty * inv.unit_cost,
                source_request_id=req.id,
                status="estimated",  # 待 actual_qty 填入後可改 confirmed
                ...
            ))
        req.status = MaterialRequestStatus.DISPATCHED
        tx.material_request.update(req)
        tx.commit()
```

### 2.4 紙本流程的「歸還與報廢」（walkthrough D3-Q2 補充）

> 劉老師補充：**歸還流程的紙本由倉庫管理人員填單管理**，系統不做自動化的「歸還流程」實體。

windMindOM 的對應：

- 不建「歸還流程」work-flow entity
- 但提供 **inventory adjustment endpoint** 給庫管員手動 +/- 調整：
  ```
  POST /api/workflow/inventory/{item_id}/adjust
  body: { delta_kind: "new", delta: +5, reason: "歸還良品", actor_id: "..." }
  ```
- 該 endpoint 必須寫 `inventory_adjustment_log` 表（who / when / why / amount）
- 庫管員填的紙本可掃描或拍照上傳當 attachment（M5+ 評估）

### 2.5 通知（簡化）

etech 的 `materialsFormNotic` + `materialsFormNoticLed` 兩個 collection 統合：

```python
@dataclass
class MaterialRequestNotification:
    id: UUID
    request_id: UUID
    recipient_role: SignoffLevel          # 對應 DN-02 — 替代 etech 兩個獨立 collection
    notification_type: Literal["awaiting_signoff", "stock_low", "received_pending"]
    read_at: datetime | None = None
    created_at: datetime
```

---

## 3. 與其他 module 的整合點

```
        work_order ─────┐
                        │   work_order_id
                        ▼
        material_request ─── signoff_chain (DN-02 領料 3 階)
                ├──→ items[] ──→ inventory (扣 stock + 寫 ledger atomic)
                ├──→ returns[] ──→ inventory (加回 stock + 寫 ledger 沖銷)
                └──→ ledger entries (estimated → confirmed)
```

### 3.1 與 work_order 的綁定（DN-01 §3）

- `material_request.work_order_id` 可 nullable — 既可獨立預備庫存補貨，也可關聯工單
- 工單 finish 時 enumerate `material_request_ids` 回填 `cost_ledger.confirmed`
- 估計 vs 實際差異記錄在 `MaterialRequestItem.estimated_qty` vs `actual_qty`

### 3.2 與 cost ledger 的綁定（M4 / WMOM-11）

material 是 cost ledger 4 種 entry 之一（labour / **material** / equipment / revenue_loss）：

| Cost ledger 維度 | 來自 |
|----------------|------|
| amount | `estimated_qty × unit_cost`（initial）→ `actual_qty × unit_cost`（confirmed at WO finish） |
| category | `"material"` |
| source_id | `material_request.id` |
| farm_id | `material_request.farm_id` |

---

## 4. Walkthrough Q&A（已 confirmed 2026-05-05）

| # | 問題 | 劉老師答覆 | 設計調整 |
|---|------|-----------|---------|
| D3-Q1 | 4 欄位 vs 簡化？ | agree 縮成 3 欄位 | `StockKind ∈ {NEW, USED, REPAIRING}`；客戶要 4 欄位再加 PENDING_INSPECTION |
| D3-Q2 | 哪幾步系統追蹤？ | agree 系統做請領→出庫→簽收→工單關聯；**歸還由庫管員紙本管理** | 系統側提供 inventory adjustment endpoint 給庫管員手動 +/- + 寫 audit log |
| D3-Q3 | 估計 vs 實際領料記錄？ | agree 都記 | `MaterialRequestItem.estimated_qty` + `actual_qty`；driveing actual vs predicted ledger |
| D3-Q4 | 退料分類？ | agree 4 種 | `ReturnReason ∈ {SURPLUS, WRONG_PART, FAILED_INSTALL, OTHER}` |
| D3-Q5 | 多倉？ | agree 預留 | `warehouse_id` schema 已加；M3 預設 single default warehouse；M5/M6 多倉場景再開 |

---

## 5. Open questions for future iterations

| # | 議題 | 影響 |
|---|------|------|
| F1 | 多倉之間的「調撥」（transfer）作業 | M5/M6 離岸場景時補（陸域單倉不需） |
| F2 | 報廢流程（scrap）— 跟退料 OTHER 分開？ | 客戶若要 KPI 區分，加 `scrapped_qty` 欄位 |
| F3 | 進貨流程（purchase order → receive → inspect → put away） | etech 沒有完整進貨流程；windMindOM M4 暫不做（先做出庫端） |
| F4 | 安全庫存自動補貨（reorder point alert） | M5+ 可加，需採購系統介接 |

---

## 6. 結論 / 下一步

- ✅ DN-03 done（2026-05-05 walkthrough）
- ⬜ **實作在 M4** — 不在 M3 主線 sub-issue 內
- M3 只先做 `MaterialRequest` 的 placeholder schema，讓 work_order 的 `material_request_ids` 欄位有依賴
- 真正的雙寫交易 + inventory adjustment endpoint 是 M4 主菜
