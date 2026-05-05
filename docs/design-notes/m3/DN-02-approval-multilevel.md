# DN-02: Approval Multi-level（簽核多階）

> Design note 對應 [WMOM-20260504-14](../../../ISSUES.md) 第二份。
> Status: done（2026-05-05 — walkthrough 一次完成）。
> Source: `windFarmMonitor/z72_SCADA_etech/yitai-corp-cms-download1140811/server/{leadersign,supervisorsign,employeesign,affairsign,materialsForm}.js`

---

## 1. etech onshore baseline（如何運作）

### 1.1 4 個獨立 sign collection（**設計反模式**）

| Collection | 對應 user group | 功能 |
|-----------|---------------|------|
| `employeesign` | `100` 員工 | 工單派工後員工要簽收 |
| `leadersign` | `300` 組長 | 工單完工後組長簽核 |
| `supervisorsign` | `500` 主管 | 跨組 / 高金額 / 異常單須上呈簽核 |
| `affairsign` | `666` 總務 | 領料單由總務 / 庫管確認出庫 |

每個 collection schema 大致相同：
```js
{
  totalformnumber: "...",       // 工單 business key（與 repair / repairTemp 共用）
  materialformnumber: "...",    // 領料單 business key（與 materialsForm 共用）
  name: "張三",                  // 待簽人 — PUT 把這個欄位「轉走」表示已簽
  date: "2026-05-04T...",
  // ... 其他依用途異
}
```

### 1.2 簽核怎麼推進？

- 系統把待簽單 insert 到對應 collection
- 待簽人開頁面查詢自己 group 對應的 collection（如 group=300 看 leadersign）
- 簽完後 PUT 改 `name = ""` 或 unset → frontend 視為「已簽走」

### 1.3 反模式清單（windMindOM 要避免）

| 反模式 | 為何不好 | windMindOM 對策 |
|-------|---------|----------------|
| 4 個獨立 collection 表達同一個邏輯（簽核） | 加新層級要動 schema + frontend 全部 | **單一 `signoff` 表 + `level` 欄位** |
| 用 `name` 欄位「轉走」表示已簽 | 失去歷史；無法區分「未簽」vs「拒簽」vs「已撤回」 | `signoff.status ∈ {pending, approved, rejected}` + 完整 `signoff_history` 表 |
| `materialformnumber` vs `totalformnumber` 並存 | business key 多軌制 | 統一用 `subject_type ∈ {work_order, material_request}` + `subject_id` UUID FK |
| 沒有「整 chain 視角」 | 看不到「這張工單到哪一階了」 | `signoff_chain` 父表 + 多筆 `signoff_step` 子表，可追整體進度 |

---

## 2. windMindOM 設計

### 2.1 Schema：3 表結構

```python
# modules/workflow/domain/signoff.py

class SignoffLevel(str, Enum):
    """4 個層級對應 etech user group（walkthrough D2-Q1 確認保留）。"""
    EMPLOYEE   = "employee"     # group 100 — 派工簽收
    LEADER     = "leader"       # group 300 — 組長
    SUPERVISOR = "supervisor"   # group 500 — 主管
    TREASURY   = "treasury"     # group 666 — 總務 / 庫管


class SignoffStatus(str, Enum):
    PENDING  = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED  = "skipped"        # farm config 關閉某層時


class SignoffSubjectType(str, Enum):
    """簽核對象（walkthrough D2-Q2：工單與領料單分不同 chain 但同一表）。"""
    WORK_ORDER       = "work_order"
    MATERIAL_REQUEST = "material_request"


@dataclass
class SignoffChain:
    """整個簽核流程實體 — 一張工單 / 領料單對應一個 chain。"""
    id: UUID
    subject_type: SignoffSubjectType
    subject_id: UUID                        # FK 到 work_order.id 或 material_request.id
    farm_id: str                            # 給 farm config policy 用
    levels: list[SignoffLevel]              # 此 chain 要走的層級順序
    current_level_index: int = 0            # 走到第幾階
    overall_status: SignoffStatus = SignoffStatus.PENDING
    started_at: datetime
    completed_at: datetime | None = None    # all approved / first reject 才設
    rejected_at_level: SignoffLevel | None = None  # reject 時記是被誰擋下


@dataclass
class SignoffStep:
    """單一階段的簽核任務 — chain 內每個 level 對應一筆。"""
    id: UUID
    chain_id: UUID                          # FK
    level: SignoffLevel
    sequence: int                           # chain 內順序（0, 1, 2...）
    parallel_group_id: UUID | None = None   # walkthrough D2-Q4：同 group 的並行多人簽（M3 預留，預設 None）
    assignee_id: UUID                       # 指派給誰（一個 step 可能有多個 step share 同 group_id）
    status: SignoffStatus = SignoffStatus.PENDING
    decided_at: datetime | None = None
    decided_by: UUID | None = None
    comment: str | None = None              # approve / reject 留言


@dataclass
class SignoffHistoryEntry:
    """完整簽核歷史（walkthrough D2-Q5：保留 reject 歷史給 KPI 用）。"""
    id: UUID
    chain_id: UUID
    step_id: UUID | None                    # 對應的 step（若為 chain-level 事件則 None）
    event_type: Literal["created", "assigned", "approved", "rejected", "reopened", "skipped"]
    actor_id: UUID | None                   # 操作者
    payload: dict                           # 額外欄位（reject_reason / approve_comment / ...）
    occurred_at: datetime
```

### 2.2 Chain policy（依 farm config 動態組）

```python
# modules/workflow/domain/signoff_policy.py

DEFAULT_CHAIN_POLICY = {
    SignoffSubjectType.WORK_ORDER: {
        # 工單：員工 → 組長（2 階）— walkthrough D2-Q2 確認
        "levels": [SignoffLevel.EMPLOYEE, SignoffLevel.LEADER],
        # 高金額 / 跨組 → 加上主管
        "escalate_to_supervisor_if": lambda wo: wo.estimated_hours > 40 or wo.priority == "critical",
    },
    SignoffSubjectType.MATERIAL_REQUEST: {
        # 領料單：員工 → 組長 → 總務（3 階）
        "levels": [SignoffLevel.EMPLOYEE, SignoffLevel.LEADER, SignoffLevel.TREASURY],
    },
}


def build_chain(subject_type, subject, farm_config) -> list[SignoffLevel]:
    """依 farm config 客製化 chain（如某客戶不需要組長層 → 移除 LEADER）。"""
    base = DEFAULT_CHAIN_POLICY[subject_type]["levels"][:]
    # farm_config.signoff_disabled_levels 可移除某層
    base = [lvl for lvl in base if lvl not in farm_config.get("signoff_disabled_levels", [])]
    # work_order escalation
    if subject_type == SignoffSubjectType.WORK_ORDER:
        if DEFAULT_CHAIN_POLICY[subject_type]["escalate_to_supervisor_if"](subject):
            base.append(SignoffLevel.SUPERVISOR)
    return base
```

### 2.3 狀態機 transitions

```
       chain created (subject 進 AWAITING_SIGNOFF)
                    │
                    ▼
   ┌────────────────────────────────────┐
   │  step[0] (level=EMPLOYEE) PENDING  │ ← assignee 在 /admin/workflow/approval
   │                                    │   看到「我的待簽」
   └─────────┬──────────────────┬───────┘
   approve ─┘                  │ reject
             │                  ▼
             ▼      chain.status = REJECTED
    ┌────────────────────────┐  rejected_at_level = EMPLOYEE
    │ step[1] (LEADER) ...   │  → work_order.reject() 回 IN_PROGRESS
    └─────────┬──────┬───────┘  （walkthrough D2-Q3 確認，給機會修正）
             │       │
       approve     reject ──▶ work_order 回 IN_PROGRESS（同上）
             │
            ...（依 chain.levels 走完）
             │
             ▼
   chain.overall_status = APPROVED
   → work_order / material_request 進 CLOSED
```

### 2.4 「我的待簽」query

```python
# modules/workflow/repository/signoff_repository.py

def list_pending_for_user(user_id: UUID, user_group: int) -> list[SignoffStep]:
    """User 在 /admin/workflow/approval 看到的待簽列表。

    1. 找 status='pending' 的 step
    2. 對應 chain.current_level_index 的 level 要符合 user_group
       - group 100 → EMPLOYEE
       - group 300 → LEADER
       - group 500 → SUPERVISOR
       - group 666 → TREASURY
    3. assignee_id 直接指派給 user_id 的優先（高層級可看「全部待簽」/ 員工只看「指給我的」）
    """
    ...
```

### 2.5 Reject 行為（walkthrough D2-Q3 確認）

當任一階 step.reject：
1. `chain.overall_status = REJECTED`，`rejected_at_level` 記下
2. `signoff_history` 寫一筆 `event_type=rejected` + payload 含 reject_reason
3. **subject 回退狀態**：
   - WORK_ORDER：`status` 從 AWAITING_SIGNOFF 回 IN_PROGRESS（給機會修正）
   - MATERIAL_REQUEST：`status` 從 AWAITING_APPROVAL 回 DRAFT（讓申請人改後重送）
4. 後續若申請人修改後重送，**新建一條 chain**（不 resume 舊 chain），舊 chain 留 audit
5. work_order timeline 上會看到「曾被 X 階 reject — 理由 Y」（walkthrough D2-Q5 補充）

---

## 3. 與其他 module 的整合點

```
work_order.finish()           material_request.submit()
       │                              │
       ▼                              ▼
 _create_chain(subject_type=WO)    _create_chain(subject_type=MR)
       │                              │
       └──────────────┬───────────────┘
                      ▼
              SignoffChain 表
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   SignoffStep   SignoffHistory   pending list query
                                    (給 frontend 用)
```

### 3.1 與 work_order 的綁定

- `work_order.finish()` 在 transition AWAITING_SIGNOFF 時呼叫 `signoff_service.create_chain(work_order)` 建 chain + 第一階 step
- `signoff_step.approve()` 若是 chain 最後一階 → 呼叫 `work_order.approve_all()` 進 CLOSED
- `signoff_step.reject()` → 呼叫 `work_order.reject(reason=...)` 回 IN_PROGRESS

### 3.2 與 day_work_form 的綁定（衍生 issue WMOM-20260505-21）

- 簽核行為（approve / reject）會被計入該員工當天的 day_work_form `activities[]`
- 主管簽核工作量 = day_work_form 的可量化指標之一

### 3.3 與 cost ledger 的綁定（M4 / WMOM-11）

- 「簽核停滯時間」（chain.started_at → chain.completed_at）會被算進 work_order 的 wait_hours，影響 `revenue_loss` 計算
- chain 在 SUPERVISOR 階卡很久 → operational KPI 警示來源

---

## 4. Walkthrough Q&A（已 confirmed 2026-05-05）

| # | 問題 | 劉老師答覆 | 設計調整 |
|---|------|-----------|---------|
| D2-Q1 | 4 階 vs 3 階？ | agree 4 階 | EMPLOYEE / LEADER / SUPERVISOR / TREASURY；farm config 可關某層 |
| D2-Q2 | 工單 chain vs 領料 chain 同？ | agree 不同 | 工單 2 階 / 領料 3 階；可由 farm config 覆寫 |
| D2-Q3 | Reject 怎麼走？ | agree 回 IN_PROGRESS | reject 觸發 work_order.reject() 回 IN_PROGRESS + reject_reason；後續重送是新 chain |
| D2-Q4 | 並行 vs 線性？ | agree 線性 | 主流程線性；schema 預留 `parallel_group_id` 給未來 |
| D2-Q5 | 簽核歷史保留？ | agree 保留 | `signoff_history` 表完整紀錄 + `signoff_step` 留 reject 痕；timeline 視覺化 |

---

## 5. Open questions for future iterations

| # | 議題 | 影響 |
|---|------|------|
| F1 | 並行多人簽核（D2-Q4 預留）的真實場景？ | 若客戶有「同層級 N 人都要簽過半才算」需求，schema 可擴；M3 不做 |
| F2 | 簽核 SLA 自動 escalate？（如 SUPERVISOR 24h 沒簽自動往上送） | M5+ KPI module 階段考慮 |
| F3 | 簽核行為的 audit log 對外揭露顆粒度？（客戶老闆 vs 員工視角的可見度） | 客戶 onboarding 時定 |

---

## 6. 結論 / 下一步

- ✅ DN-02 done（2026-05-05 walkthrough）
- ⬜ 實作 [WMOM-20260504-18](../../../ISSUES.md) — Approval domain + REST API + tests（依本 DN）
- 依賴：WMOM-16 (work_order domain) + WMOM-17 (work_order CRUD/API) 先做完
