# windMindOM 系統架構全貌

> 版本：v0.8.1（2026-05-05 — M3 backend 完成）
> 受眾：第一次接觸專案的同仁、潛在客戶 demo、partner 對接窗口
> 一張圖看完整系統 → 然後依興趣往下看細節圖

---

## 1. 一張圖看全貌

```mermaid
graph TB
    %% ── User personas ─────────────────────────────────
    subgraph Users["👥 User Personas（雙路徑）"]
        Admin["管理層 / 班長 / 工程師<br/>desktop /admin/"]
        Field["現場工程師<br/>mobile /field/<br/>(M5)"]
    end

    %% ── Frontend ──────────────────────────────────────
    subgraph Frontend["🖥️ Frontend — React 18 + TypeScript + Tailwind + Vite"]
        AdminUI["Admin UI<br/>Dashboard / Cost / Workflow / Reporting"]
        FieldUI["Field UI<br/>Alerts + RAG + WO completion<br/>(M5)"]
        FarmSelector["FarmSelector — 14×Z72 / 7×V164...<br/>切換 farm 同時切 cost dataset"]
        i18n["i18n hook (zh / en) + ui() helper"]
    end

    %% ── API ───────────────────────────────────────────
    subgraph API["🌐 API Layer — FastAPI"]
        REST["~70+ REST endpoints<br/>turbines / cost / workflow / approval / farms / ..."]
        WS["WebSocket /ws/realtime<br/>每 2 秒 push 14 turbine 即時狀態"]
    end

    %% ── 5 大 modules ──────────────────────────────────
    subgraph Modules["📦 5 大功能 Modules"]
        Mon["monitoring ✅<br/>SCADA + Simulator + 14 turbines<br/>11 fault scenarios + WAL storage"]
        Cost["cost ✅<br/>ECN engine 4 套（cost_cal/MC/var_fluct/waiting_time）<br/>+ farm-aware overlay"]
        WF["workflow 🔄<br/>backend done: WO + Approval + DN-01/02/03<br/>frontend 進行中（WMOM-19/-20）"]
        Rep["reporting ⬜<br/>Monthly PDF + Annual budget<br/>(M4)"]
        Know["knowledge ⬜<br/>RAG + Alert search<br/>(M5)"]
    end

    %% ── Data ──────────────────────────────────────────
    subgraph Data["💾 Data Layer — SQLite WAL"]
        FarmDB[("per-farm DB<br/>wind_farm.db<br/>turbine_data + work_orders + signoff_chains + ledger...")]
        FarmReg[("farms.db<br/>FarmRegistry — 多風場管理")]
        Files["data/demo/<br/>K13 cost dataset / Z72 PLC tag map / RAG vector"]
    end

    %% ── External ──────────────────────────────────────
    subgraph External["🔌 External Integration"]
        PLC["Bachmann Z72 PLC<br/>OPC UA + Modbus TCP"]
        WindAI["windAILab<br/>AI 故障診斷 (M6+ HTTP)"]
        RAGStrat["RAG_Ultimate<br/>策略檔 + 預計算向量 (M5 artifact)"]
        InduSpect["InduSpect<br/>CV 定檢 (M6+ HTTP)"]
    end

    %% ── Connections ──────────────────────────────────
    Admin --> AdminUI
    Field --> FieldUI
    AdminUI --> REST
    AdminUI --> WS
    FieldUI --> REST
    FarmSelector --> REST

    REST --> Mon
    REST --> Cost
    REST --> WF
    WS --> Mon

    Mon --> FarmDB
    WF --> FarmDB
    Mon --> FarmReg
    WF --> FarmReg
    Cost --> FarmReg
    Cost --> Files
    Know -.M5.-> Files
    Know -.M5.-> RAGStrat

    Mon --> PLC
    WF -.M6+.-> WindAI
    WF -.M6+.-> InduSpect

    classDef done fill:#4ade80,color:#fff,stroke:#16a34a
    classDef inProgress fill:#fbbf24,color:#000,stroke:#d97706
    classDef planned fill:#cbd5e1,color:#475569,stroke:#64748b
    class Mon,Cost done
    class WF inProgress
    class Rep,Know planned
```

**圖例**：🟢 已完成 / 🟡 進行中 / ⚪ 規劃中

---

## 2. 模組內部分層（典型 pattern — 以 workflow 為例）

每個 module 走相同四層分層，pure Python → 漸增 framework 依賴：

```mermaid
graph LR
    A["domain/<br/>📦 pure dataclass + Enum<br/>State machine + business rules<br/>不接 SQLAlchemy / FastAPI"] --> B
    B["repository/<br/>🗄️ SQLAlchemy 2.0 ORM<br/>+ engine cache + WAL pragma<br/>+ multi-WO constraint enforcement"] --> C
    C["schemas/<br/>📋 pydantic v2<br/>request / response models<br/>str-Enum 透明序列化"] --> D
    D["routers/<br/>🌐 FastAPI endpoints<br/>error mapping (404 / 409 / 422)<br/>factory injection point for testing"] --> E
    E["main app.py<br/>🚀 FastAPI mount + middleware"]
```

**為什麼分這四層**：
- **domain** 純 Python 可單獨測試（73 tests），未來換 ORM/框架不影響邏輯
- **repository** 集中 DB 細節 + business rule（如「一台風機 ≤ 3 OPEN 工單」）
- **schemas** 對外 API contract，與 domain 對齊但不共用 class（pydantic vs dataclass）
- **routers** 薄層 — 只做 HTTP / DI / error mapping

---

## 3. Work Order 狀態機（M3 主軸）

```mermaid
stateDiagram-v2
    [*] --> DRAFT: 維修人開單<br/>or SCADA alarm-driven
    DRAFT --> DISPATCHED: dispatch<br/>(actor_id audit)
    DISPATCHED --> IN_PROGRESS: start_work<br/>(offshore guard: weather window)
    REOPENED --> IN_PROGRESS: start_work
    IN_PROGRESS --> IN_PROGRESS: update_progress<br/>(append ProgressNote)
    IN_PROGRESS --> AWAITING_SIGNOFF: finish<br/>↓ 自動建 signoff chain<br/>backlink chain_id 到 wo
    AWAITING_SIGNOFF --> CLOSED: approve_all<br/>(only chain 全通過才放行)
    AWAITING_SIGNOFF --> IN_PROGRESS: reject<br/>(清 signoff_chain_id)
    CLOSED --> REOPENED: reopen<br/>(同部件再故障)

    DRAFT --> CANCELLED: cancel
    DISPATCHED --> CANCELLED: cancel
    IN_PROGRESS --> CANCELLED: cancel

    note right of AWAITING_SIGNOFF
        signoff chain：4 階對應 etech user group
        - EMPLOYEE (100) → LEADER (300)
        - 工單 chain 2 階；領料 3 階（+TREASURY）
        - critical priority 自動 escalate +SUPERVISOR
        - reject 任一階 → 回 IN_PROGRESS 給機會修
    end note
```

**整合點**：
- 工單 finish → `signoff_repository.create_chain_for_work_order()` 自動建 chain
- 簽核 last step approved → 自動觸發 `work_order.approve_all()` → CLOSED
- 簽核任一階 reject → 自動 `work_order.reject(reason)` → IN_PROGRESS
- 失敗時 API 回 200 + `subject_transition_error` 欄位（不藏 chain 已決定的事實）

---

## 4. Approval 4 階 signoff chain

```mermaid
graph LR
    Wo["WorkOrder<br/>finish()"] -->|auto-create| Ch
    subgraph Ch["SignoffChain<br/>(per work order / per material request)"]
        S1["step[0]<br/>EMPLOYEE<br/>group 100"]
        S2["step[1]<br/>LEADER<br/>group 300"]
        S3["step[2]<br/>SUPERVISOR<br/>group 500<br/>(只 critical 工單)"]
        S4["step[3]<br/>TREASURY<br/>group 666<br/>(領料單才有)"]
        S1 --> S2
        S2 -.escalate.-> S3
        S3 -.MR only.-> S4
    end
    Ch --> Hist[("signoff_history<br/>每事件一筆 audit")]
    Ch -->|all approved| Close["WorkOrder → CLOSED"]
    Ch -->|any rejected| Back["WorkOrder → IN_PROGRESS<br/>清 signoff_chain_id"]
```

**設計重點（DN-02 walkthrough confirmed）**：
- 線性簽核（schema 預留 `parallel_group_id` 給未來並行簽，目前 NotImplementedError）
- 完整 `signoff_history` 給 KPI 用（誰退最多 / 哪類常被退）
- POST `/work-orders/{id}/approve` 強制檢查 `chain.overall_status == APPROVED`（review fix #4 — 防 bypass）

---

## 5. 與 7 個來源 repo 的關係

```mermaid
graph TB
    subgraph Source["7 個來源 repo（在外面）"]
        DigiWT["digiWindTurbine<br/>研究/教學版（不動）"]
        ECN["ECN<br/>O&M cost engine（archive 後）"]
        Etech["z72_etech<br/>onshore workflow baseline"]
        Z72HMI["z72hmiNew<br/>z72bridge PLC 服務"]
        WindAI["windAILab<br/>AI 故障診斷產品"]
        RAG["RAG_Ultimate<br/>research strategy"]
        Indu["InduSpect<br/>CV 定檢產品"]
    end

    WMOM["windMindOM<br/>商業化版本"]

    DigiWT ==>|"M1 商業化升級<br/>(fork + 改 root context)"| WMOM
    ECN ==>|"M2 engine 移植<br/>(僅取 engine，schema 重寫)"| WMOM
    Etech -.->|"M3 取設計<br/>(僅讀程式產 design notes)"| WMOM
    Z72HMI -->|"M6 PLC client 介接<br/>(remain 外部 service)"| WMOM
    RAG -.->|"M5 artifact 交付<br/>(strategy.yaml + parquet)"| WMOM
    WindAI -.->|"M6+ HTTPS API 介接"| WMOM
    Indu -.->|"M6+ HTTPS API 介接"| WMOM
```

| Repo | 角色 | windMindOM 對它做什麼 |
|------|------|---------------------|
| **digiWindTurbine** | 物理模擬 + SCADA 平台 | 不動，留作研究 / 教學版本 |
| **ECN** | O&M cost calculation engine | M2 完成移植進 `modules/cost/`；原 repo archive |
| **z72_etech** | 益泰運維廠商 onshore workflow | M3 取設計（design notes 在 `docs/design-notes/m3/`），**不取程式** |
| **z72hmiNew** | z72bridge PLC service | 留外面（z72 服務性 repo）；M1 已整合 OPC UA client |
| **windAILab** | AI 故障診斷產品 | 留外面（**另一公司業務**）；M6+ HTTP API 介接 |
| **RAG_Ultimate** | research RAG strategy | 留外面（research line）；M5 artifact 交付 |
| **InduSpect** | CV 定檢產品 | 留外面（independent product）；M6+ HTTP API 介接 |

---

## 6. Storage 結構（per-farm）

```mermaid
graph TB
    Reg[("farms.db<br/>FarmRegistry")]
    Reg -->|1 farm = 1 DB file| F1[("台中港曲風場/<br/>wind_farm.db")]
    Reg -->|...| F2[("彰化離岸風場台電/<br/>wind_farm.db")]
    Reg -->|...| Fn[("...其他 farm")]

    subgraph Tables["wind_farm.db 內部表結構"]
        subgraph MonTables["monitoring (raw sqlite3)"]
            M1["turbine_data<br/>1Hz raw / 3 day"]
            M2["turbine_data_1m<br/>1-min agg / 90 day"]
            M3["turbine_data_10m<br/>10-min agg / permanent"]
            M4["turbine_snapshots<br/>event 高頻 / 7 day ⚠ WMOM-01 fix"]
            M5["history_events<br/>alarm / fault / state"]
            M6["sessions<br/>simulator metadata"]
        end
        subgraph WfTables["workflow (SQLAlchemy 2.0) — M3"]
            W1["work_orders<br/>狀態機 7 status"]
            W2["work_order_progress_notes<br/>維修筆記"]
            W3["work_order_event_log<br/>完整 transition audit"]
            W4["signoff_chains<br/>4 階 chain"]
            W5["signoff_steps<br/>每階狀態"]
            W6["signoff_history<br/>事件 audit"]
        end
        subgraph M4Tables["M4 預留"]
            R1["cost_ledger<br/>actual vs predicted"]
            R2["material_requests<br/>領料單"]
            R3["inventory_items<br/>庫存"]
        end
    end

    F1 -.含.-> Tables

    classDef done fill:#dcfce7,stroke:#16a34a
    classDef m3 fill:#fef9c3,stroke:#ca8a04
    classDef planned fill:#f3f4f6,stroke:#9ca3af
    class M1,M2,M3,M4,M5,M6 done
    class W1,W2,W3,W4,W5,W6 m3
    class R1,R2,R3 planned
```

**設計重點**：
- **per-farm DB** — 每個風場 `wind_farm.db`（在 `modules/monitoring/data/farms/{farm_id}/`），由 `FarmRegistry` 集中管理
- **monitoring 用 raw sqlite3 + WAL pragma**；**workflow 用 SQLAlchemy 2.0 + 同 WAL**，並存無衝突
- **WAL mode + busy_timeout=5s** 給多 thread / 多 connection 並發讀寫
- **Retention 政策**（WMOM-20260505-01 hotfix 後）：
  - turbine_data raw 3 天 / 1m agg 90 天 / 10m permanent
  - turbine_snapshots **7 天**（避免 retroactive write 失控膨脹）

---

## 7. 6-month roadmap timeline

```mermaid
gantt
    title windMindOM v0.8.1 Roadmap (6 months)
    dateFormat YYYY-MM
    axisFormat %Y-%m

    section M1 Setup
    repo baseline + pitch deck    :done, m1, 2026-05, 1M
    cost↔farm 整合 (插入)         :done, ifix, 2026-05-04, 2d
    snapshots hotfix              :done, hotfix, 2026-05-05, 1d

    section M2 Cost
    ECN engine port (4 套)        :done, m2, 2026-06, 1M

    section M3 Workflow Part 1
    z72_etech 取設計 + DN-01/02/03 :done, dn, 2026-05-05, 2d
    Work Order domain + 狀態機     :done, wo, 2026-05-05, 1d
    Work Order CRUD + REST API     :done, woa, 2026-05-05, 1d
    Approval signoff API           :done, sig, 2026-05-05, 1d
    Frontend orders + approval     :active, fe, 2026-07, 15d

    section M4 Workflow Part 2
    Inventory + Material Request   :m4, 2026-08, 1M
    Reporting (PDF 月報)           :rep, 2026-08, 15d

    section M5 RAG + Field UI
    Knowledge module + RAG         :m5k, 2026-09, 20d
    /field mobile UI               :m5f, 2026-09, 15d

    section M6 PoC
    Friendly 客戶部署               :m6, 2026-10, 15d
    第一筆合約                     :crit, m6c, 2026-10, 15d
```

---

## 8. 一句話總結

> **windMindOM = digiWindTurbine 商業化升級**：原本物理模擬 + SCADA 平台 → 加上 5 大運維模組（monitoring / cost / workflow / reporting / knowledge）+ 雙 persona UI（管理 desktop + 現場 mobile）+ simulator-first demo（無實場可成立 = sales killer feature）+ 與 6 個 partner repo 的清楚邊界（API / artifact 介接，不 fork 程式碼）。

---

## 9. 進一步閱讀

| 想知道 | 看哪 |
|---|---|
| 產品定位 / ICP / 5 大功能 | [`docs/product/PRODUCT_VISION.md`](../product/PRODUCT_VISION.md) |
| 5 modules 詳細設計 + 整合 | [`docs/product/MVP_ARCHITECTURE.md`](../product/MVP_ARCHITECTURE.md) |
| 6 個月路線圖 | [`docs/product/ROADMAP.md`](../product/ROADMAP.md) |
| 重大架構決策（v0.5 → v0.8.1 pivot 等） | [`docs/product/decision_log.md`](../product/decision_log.md) |
| M3 工單 / 簽核 / 庫存設計 | [`docs/design-notes/m3/`](../design-notes/m3/) |
| 既有 digiWT 物理模型細節 | [`docs/legacy/digiwt_project_notes.md`](../legacy/digiwt_project_notes.md) |
| API endpoint 規格 | [`docs/API_GUIDE.md`](../API_GUIDE.md) |
| 工單實際 lifecycle code | [`modules/workflow/`](../../modules/workflow/) |
| 任務追蹤 | [`ISSUES.md`](../../ISSUES.md) + [`STATUS.yaml`](../../STATUS.yaml) |
