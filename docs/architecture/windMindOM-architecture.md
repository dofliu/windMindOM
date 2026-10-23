# windMindOM 系統架構全貌

> 版本：v0.8.1 產品基線；狀態截至 **2026-10-23**（EPIC-DS 誤報 / 健康負樣本 WMOM-20261021-08-b 後）
> 受眾：第一次接觸專案的同仁、對外 demo、partner / 學生專題對接
> 先看 §1 一張圖看全貌、§2 現行主線 EPIC-DS 的資料流，再依興趣往下看細節圖。
> 同內容的互動說明頁（含模組卡與進度條）連結記在 [`work-logs/2026-10/2026-10-22-architecture-docs.md`](../../work-logs/2026-10/2026-10-22-architecture-docs.md) §2.1。

---

## 1. 一張圖看全貌

```mermaid
flowchart TB
    subgraph Users["👥 使用者"]
        direction LR
        Admin["管理層・班長・主管<br/>桌機 /admin"]
        Field["現場工程師<br/>手機 /field"]
        Teacher["出題老師（EPIC-DS）<br/>產生情境・建回放・評分"]
        RAG["學生的 RAG 維修助手<br/>（外部專題，不在本 repo）"]
    end

    subgraph Frontend["🖥️ 前端 — React + TypeScript + Vite（中英雙語、真登入頁）"]
        UI["風場總覽・風機細節・維護中心・工單・成本・報表<br/>歷史・情境模擬・故障模擬・現場查詢・導覽・設定"]
    end

    subgraph API["🌐 介面"]
        direction LR
        REST["REST API（FastAPI，約 140 端點）<br/>JWT 角色授權"]
        WSRT["WS /ws/realtime<br/>每 2 秒推播"]
        MB["Modbus TCP :5020"]
        PACK["① 資料包<br/>Parquet + events.jsonl"]
        WSRP["② WS /ws/replay<br/>回放 token・收判斷"]
        OPCUA["③ OPC UA :4840<br/>Bachmann Z72 item ID"]
    end

    subgraph Modules["📦 六個功能模組（monolith）"]
        direction LR
        WF["workflow ✅<br/>工單・多階簽核・庫存・領料"]
        Cost["cost ✅<br/>K13・LCOE・Monte Carlo"]
        Rep["reporting ✅<br/>月報 PDF・年度預算"]
        Know["knowledge 🟡 75%<br/>警報查 Z72 手冊"]
        Auth["auth ✅<br/>JWT + RBAC"]
        Mon["monitoring ✅ / EPIC-DS 🟡<br/>14 台 Z72 物理模擬・118 tag<br/>PLC 保護層（315 碼）・16 故障 + 1 nuisance 情境・風場事件<br/>情境・標準答案・回放・OPC UA"]
    end

    subgraph Data["💾 資料（SQLite WAL）與外部系統"]
        direction LR
        FarmReg[("farms.db<br/>風場登錄")]
        FarmDB[("每風場 wind_farm.db<br/>讀值・事件・情境・標準答案<br/>回放・工單・庫存・成本帳")]
        Vec[("手冊向量檔<br/>Z72 手冊 531 段")]
        PLC["Bachmann Z72 PLC<br/>實場 OPC DA（暫緩）"]
        AI["windAILab・InduSpect<br/>M6+ API（暫緩）"]
    end

    Admin --> UI
    Field --> UI
    Teacher --> UI
    UI -->|呼叫| REST
    UI -->|訂閱即時數據| WSRT

    RAG <-->|收資料・送判斷| WSRP
    RAG -->|讀目前值| OPCUA
    RAG -.->|讀老師交付的檔案| PACK

    REST --> WF & Cost & Rep & Know & Auth & Mon
    WSRT & MB & PACK & WSRP & OPCUA --- Mon

    Mon --> FarmDB & FarmReg
    WF --> FarmDB
    Cost --> FarmDB
    Know --> Vec
    Mon -.->|實場對接（暫緩）| PLC
    WF -.->|M6+| AI

    classDef done fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef wip fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef deferred fill:#f1f5f9,stroke:#94a3b8,color:#475569,stroke-dasharray:5 4
    classDef ext fill:#ffffff,stroke:#334155,stroke-dasharray:5 4
    class UI,REST,WSRT,MB,PACK,WSRP,OPCUA,WF,Cost,Rep,Auth,FarmReg,FarmDB,Vec done
    class Mon,Know wip
    class PLC,AI deferred
    class RAG ext
```

**圖例**：🟢 已完成 / 🟡 進行中 / 灰色虛線 暫緩 / 白色虛線 外部系統

- monitoring 一個模組提供五個介面：WS 即時、Modbus，以及 EPIC-DS 給受測端的三條管道（資料包、WS 回放、OPC UA）。其他模組只經 REST。
- 學生的 RAG 助手不經前端、不開帳號：WS 回放與 OPC UA 用回放 token（OPC UA 匿名唯讀），資料包由老師下載後以檔案交付。

---

## 2. 現行主線：EPIC-DS 擬真資料源

情境一次生成後凍結。讀值與可觀測事件經三條管道給受測端；標準答案另外存放，只在評分時與受測端的預測對照。

```mermaid
graph LR
    Sched["出題<br/>故障排程・風況"] -->|驅動| Phys["物理模型 + PLC 保護層<br/>警報・跳機由訊號觸發"]
    Phys -->|逐步| Bulk["批次生成<br/>背景執行緒・同時一個"]
    Bulk -->|寫入| Sess[("情境 session<br/>讀值・可觀測事件")]
    Sess --> P1["① 資料包"]
    Sess --> P2["② WS 回放"]
    Sess --> P3["③ OPC UA"]
    P1 --> RAG["學生 RAG 助手"]
    P2 <--> RAG
    P3 --> RAG

    Bulk -->|記下注入・首次警報・跳機| GT[("標準答案<br/>scenario_ground_truth<br/>只限主管")]
    RAG -->|"預測（伺服器蓋時間）"| Score["score.py 評分<br/>偵測・元件・類別・提前量"]
    GT -->|評分端版資料包| Score

    subgraph Blind["盲測邊界：答案不經過三條管道"]
        GT
        Score
    end

    classDef done fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef ext fill:#ffffff,stroke:#334155,stroke-dasharray:5 4
    class Phys,Bulk,Sess,P1,P2,P3,GT done
    class RAG ext
```

| 規則 | 怎麼做到 |
|---|---|
| 受測端看不到答案 | 根因 / 注入資訊只進 `scenario_ground_truth`；給外部的事件一律經 `storage.is_observable_event` 白名單；manifest 不帶情境名稱與故障排程 |
| 三條管道內容一致 | 資料包、WS 回放、OPC UA 讀值逐位元相同（2026-10-22 以真伺服器驗證：12600 筆讀值、43 筆事件、224 窗統計） |
| 時間因果 | 預測的 `ts` 由伺服器在收到時蓋上；判斷得慢，提前量就少 |
| 正式評測的前提 | 伺服器 `WMOM_AUTH_ENFORCE=true`（否則不能建立）；單次直播不能暫停 / 倒帶；整台伺服器正式評測總速率 ≤ 1000 筆讀值 / 秒（DEC-20261022-05） |
| 擬真 | 警報碼、文字、等級以 Z72 真實目錄為準（xlsx 314 碼＋手冊獨有的 A039）；PLC 設定值依手冊 Appendix D；資料包 102 欄 = 47 個真實 Bachmann tag + 55 個合成 tag |

介面合約：[`docs/integration/rag_assistant_data_contract_v1.md`](../integration/rag_assistant_data_contract_v1.md)（v1.5）；設計與各階段紀錄：[`docs/product/EPIC-DS_realistic_data_source.md`](../product/EPIC-DS_realistic_data_source.md)；學生 starter kit：[`examples/rag_starter_kit/`](../../examples/rag_starter_kit/)。

---

## 3. monitoring 內部：一步模擬做了什麼

```mermaid
graph LR
    Wind["風況模型<br/>風場時區的日夜 / 季節循環"] --> Model
    FE["故障引擎<br/>16 情境（真故障 10・感測器 6）"] -->|故障物理 / 感測器故障| Model
    subgraph Model["TurbinePhysicsModel（每台一個）"]
        Phy["氣動・傳動・熱・振動・電氣<br/>（製程值）"] --> Sensor["感測器模型<br/>雜訊・漂移"]
        Phy -->|製程值| PLCP["PLC 保護層<br/>設定值・延時・鎖存・重啟上限"]
    end
    PLCP -->|跳機 / T1・T2 停機| Phy
    PLCP -->|PLC 事件| Ev["事件：警報・跳機・解除・復位"]
    Sensor --> Out["118 個 SCADA tag"]
    PLCP -->|跳機碼| FE
```

- **PLC 只看製程值**（感測器模型之前）；唯一例外是注入的感測器故障：那支感測器的故障讀值同時給 PLC 與 SCADA。
- **資料來源**：即時模擬（Live 迴圈）、產生情境（批次，背景執行緒）、調閱過去情境；實場 OPC DA 暫緩。
- **熱模型**以 Z72 額定功率正規化：其他機型（前端可選的 Vestas、SG、Goldwind）共用 Z72 的 PLC 設定值與警報目錄，健康機組不會被誤跳機。

---

## 4. 模組內部分層（典型 pattern — 以 workflow 為例）

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
- **domain** 純 Python 可單獨測試，未來換 ORM/框架不影響邏輯
- **repository** 集中 DB 細節 + business rule（如「一台風機 ≤ 3 OPEN 工單」）
- **schemas** 對外 API contract，與 domain 對齊但不共用 class（pydantic vs dataclass）
- **routers** 薄層 — 只做 HTTP / DI / error mapping

monitoring 是 digiWT 搬入的既有結構（`simulator/` + `server/`，raw sqlite3），沒有套這四層。

---

## 5. Work Order 狀態機（M3）

```mermaid
stateDiagram-v2
    [*] --> DRAFT: 維修人開單<br/>or SCADA alarm-driven
    DRAFT --> DISPATCHED: dispatch<br/>(actor_id audit)
    DISPATCHED --> IN_PROGRESS: start_work<br/>(offshore guard，看天候窗口)
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

## 6. Approval 4 階 signoff chain

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
- POST `/work-orders/{id}/approve` 強制檢查 `chain.overall_status == APPROVED`（防 bypass）

---

## 7. 與 7 個來源 repo 的關係

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

    DigiWT ==>|"M1 商業化升級 ✅"| WMOM
    ECN ==>|"M2 engine 移植 ✅"| WMOM
    Etech -.->|"M3 取設計 ✅<br/>(僅讀程式產 design notes)"| WMOM
    Z72HMI -->|"實場 PLC 介接（暫緩）"| WMOM
    RAG -.->|"M5 artifact 交付<br/>(strategy.yaml + 向量檔)"| WMOM
    WindAI -.->|"M6+ HTTPS API（暫緩）"| WMOM
    Indu -.->|"M6+ HTTPS API（暫緩）"| WMOM
```

| Repo | 角色 | windMindOM 對它做什麼 |
|------|------|---------------------|
| **digiWindTurbine** | 物理模擬 + SCADA 平台 | 不動，留作研究 / 教學版本 |
| **ECN** | O&M cost calculation engine | M2 完成移植進 `modules/cost/`；原 repo archive |
| **z72_etech** | 益泰運維廠商 onshore workflow | M3 取設計（design notes 在 `docs/design-notes/m3/`），**不取程式** |
| **z72hmiNew** | z72bridge PLC service | 留外面；實場 OPC DA 介接隨 M6 暫緩（`shared/plc_clients/bachmann/` 有讀取程式） |
| **windAILab** | AI 故障診斷產品 | 留外面（**另一公司業務**）；M6+ HTTP API 介接（暫緩） |
| **RAG_Ultimate** | research RAG strategy | 留外面（research line）；M5 artifact 交付 |
| **InduSpect** | CV 定檢產品 | 留外面（independent product）；M6+ HTTP API 介接（暫緩） |

另有**學生專題的 RAG 即時維修助手**（不在本 repo）：只透過 EPIC-DS 的介面合約與三條管道取資料。

---

## 8. Storage 結構（per-farm）

```mermaid
graph TB
    Reg[("farms.db<br/>FarmRegistry（含風場時區）")]
    Reg -->|1 farm = 1 DB file| F1[("風場 A / wind_farm.db")]
    Reg -->|...| Fn[("...其他 farm")]

    subgraph Tables["wind_farm.db 內部表結構"]
        subgraph MonTables["monitoring（raw sqlite3）"]
            M1["turbine_data<br/>raw（情境 session 保留到刪除）"]
            M2["turbine_data_1m / _10m<br/>降頻統計"]
            M3["turbine_snapshots<br/>事件前後快照 / 7 天"]
            M4["history_events<br/>PLC 事件・狀態轉換（含 session_id）"]
            M5["sessions<br/>Live / 情境 session"]
            M6["technicians・work_orders<br/>（monitoring 舊維護中心）"]
        end
        subgraph DSTables["EPIC-DS"]
            D1["scenario_ground_truth<br/>標準答案（只限主管）"]
            D2["replay_runs<br/>回放（token 只存 sha256）"]
            D3["replay_predictions<br/>受測端預測"]
        end
        subgraph WfTables["workflow / cost（SQLAlchemy 2.0）"]
            W1["wmom_work_orders・progress_notes・event_log"]
            W2["signoff_chains・steps・history"]
            W3["warehouses・inventory_items・adjustment_log"]
            W4["material_requests・items・returns・notifications"]
            W5["wmom_inspection_schedules・day_work_forms"]
            W6["cost_ledger_entries"]
        end
    end

    F1 -.含.-> Tables
    Auth[("auth_users<br/>（auth 模組）")]
```

**設計重點**：
- **per-farm DB** — 每個風場 `wind_farm.db`（在 `modules/monitoring/data/farms/{farm_id}/`），由 `FarmRegistry` 集中管理；回放與 token 也存在目前風場的 DB（正式評測進行中不能切換風場）。
- **monitoring 用 raw sqlite3 + WAL**；**workflow / cost 用 SQLAlchemy 2.0 + 同 WAL**，並存無衝突。
- **時間戳一律 UTC**（`...ffffff+00:00`，SQLite 靠字串字典序比較）；舊 DB 開檔時一次性轉換。
- **Retention**：Live 的 raw 3 天 / 1m 90 天 / 10m 永久；情境 session 的 raw 保留到情境刪除。

---

## 9. 時程（原 6 個月路線圖 + 現行主線）

```mermaid
gantt
    title windMindOM 時程（截至 2026-10-22）
    dateFormat YYYY-MM-DD
    axisFormat %Y-%m

    section 原路線圖
    M1 基線（客戶接觸延後）       :done, m1, 2026-05-01, 30d
    M2 成本模組                  :done, m2, 2026-05-15, 30d
    M3 工單與簽核                 :done, m3, 2026-05-05, 70d
    M4 庫存與報表                 :done, m4, 2026-06-01, 60d
    M5 手冊查詢與現場頁（約 75%） :active, m5, 2026-06-01, 120d
    M6 PoC 與合約（暫緩）         :crit, m6, 2026-10-01, 20d

    section EPIC-DS（2026-10-21 起現行主線）
    1a 真實警報目錄               :done, ds1a, 2026-10-21, 1d
    1b 物理校正・PLC・UTC・切出    :done, ds1b, 2026-10-21, 1d
    2 標準答案                    :done, ds2, 2026-10-21, 1d
    3a–3d 資料包・回放・OPC UA・kit :done, ds3, 2026-10-21, 2d
    4-a 感測器故障                 :done, ds4a, 2026-10-22, 1d
    全面檢查                       :done, chk, 2026-10-22, 1d
    手冊保真度（-02）              :done, ds02, 2026-10-23, 1d
    4 其餘子項                     :ds4, 2026-10-24, 3d
```

| 項目 | 狀態 |
|---|---|
| M1 基線建置 | 85%（技術基線完成；客戶接觸隨 M6 延後） |
| M2 成本 / M3 工單 / M4 庫存與報表 | 100% |
| M5 手冊查詢與現場頁 | 75%（剩客戶手冊、一年警報資料，隨 M6 暫緩） |
| M6 PoC 與合約 | 暫緩（DEC-20261021-01）；auth 已完成部分保留 |
| EPIC-DS | 95%：Phase 1a–3d、4-a、4-b（誤報 / 健康負樣本）、全面檢查、手冊保真度完成；下一步 -08 其餘子項（多重故障 + 早期徵兆、故障庫擴充，先請劉老師挑） |

測試：backend 2051 passed / 7 skipped / 1 xfailed；frontend vitest 1513 passed（2026-10-23）。

---

## 10. 一句話總結

> **windMindOM = digiWindTurbine 商業化升級**：物理模擬 + SCADA 平台加上運維模組（monitoring / workflow / cost / reporting / knowledge / auth）與雙 persona UI。2026-10-21 起商業時程暫停，現行主線是 **EPIC-DS**：用 Z72 物理模擬器 + PLC 保護層產生附標準答案的擬真資料，經資料包、WebSocket 回放、OPC UA 三條管道給外部 RAG 維修助手做盲測。

---

## 11. 進一步閱讀

| 想知道 | 看哪 |
|---|---|
| 產品定位 / ICP / 功能模組 | [`docs/product/PRODUCT_VISION.md`](../product/PRODUCT_VISION.md) |
| 模組詳細設計 + 整合 | [`docs/product/MVP_ARCHITECTURE.md`](../product/MVP_ARCHITECTURE.md) |
| 路線圖與現行主線 | [`docs/product/ROADMAP.md`](../product/ROADMAP.md) |
| EPIC-DS 設計與各階段紀錄 | [`docs/product/EPIC-DS_realistic_data_source.md`](../product/EPIC-DS_realistic_data_source.md) |
| 給受測端的介面合約（v1.5） | [`docs/integration/rag_assistant_data_contract_v1.md`](../integration/rag_assistant_data_contract_v1.md) |
| 學生 starter kit | [`examples/rag_starter_kit/`](../../examples/rag_starter_kit/) |
| 重大決策（最新 DEC-20261022-05） | [`docs/product/decision_log.md`](../product/decision_log.md) |
| M3 工單 / 簽核 / 庫存設計 | [`docs/design-notes/m3/`](../design-notes/m3/) |
| 既有 digiWT 物理模型細節 | [`docs/legacy/digiwt_project_notes.md`](../legacy/digiwt_project_notes.md) |
| API endpoint 規格 | [`docs/API_GUIDE.md`](../API_GUIDE.md) |
| 任務追蹤 | [`ISSUES.md`](../../ISSUES.md) + [`STATUS.yaml`](../../STATUS.yaml) |
