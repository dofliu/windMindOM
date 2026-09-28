# 2026-09-28 — WMOM-20260928-03：Preflight 全綠、無新單 session 可行候選；接續前一 session 建議，草擬 `WMOM-20260505-26` Service/Maintenance state 子項降低版 acceptance 具體提案

## Preflight

- `git status`：working tree clean，分支已在環境注入的 `claude/inspiring-mccarthy-qa812s`，
  且已與 `origin/main`（`99f7f87`，即前一 session `WMOM-20260928-02` 合併後的 head）同步，
  無需額外 pull。
- `pip install --ignore-installed PyYAML -r requirements.txt -r requirements-dev.txt` 成功。
- backend `pytest`（7 條路徑，與 `ci.yml` 一致）：**1295 passed, 7 skipped, 1 xfailed** —
  與 baseline 完全一致，零 regression。
- frontend `npm ci && npx tsc --noEmit`（0 error）`&& npx vitest run`（**1477 passed，
  70 files**）`&& npx vite build`（成功，僅既有 chunk size 警告）：與 baseline 完全一致，
  零 regression。
- Stack-aware 檢查：`mcp__github__list_pull_requests`（state=open）回傳空陣列，無上個
  session 遺留未合併 PR，CI 飛輪本身正常。
- `docs/routines/autonomous-daily-worker-prompt.md` 版本仍是 v4.1，與本次注入 cron
  prompt 一致，無需再同步。

## Claim

這是本日第三個 autonomous session（第十九個 autonomous session 總計）。前一個 session
（`WMOM-20260928-02`）已逐一核對全部 7 個 open + 2 個 in_progress issue，結論與本次
preflight 重新確認一致：無新的單 session 可完工、無設計歧義候選工作。work-log 明確
留下具體建議：「下個 session 建議直接評估『是否要正式拆 `WMOM-20260505-26` 的
Service/Maintenance state 子項為獨立 issue（自訂降低版 acceptance）』作為打破僵局的
具體提案，而非再次重複本次的『逐一核對後結論相同』流程」。

本次不再重複第三次同款「逐一核對 7 個 open issue」流程（已由 `-01`/`-02` 兩個 session
充分記錄），改為**執行前一 session 交辦的具體任務**：草擬 `WMOM-20260505-26` 的
Service/Maintenance state 子項降低版提案。

**重要邊界**：依 routine §4 item 7「標 🟡 需劉老師決策的不要自己開工」，本次僅**草擬
提案文字**（含技術可行性調查），**不實作、不動任何 production 程式碼**——降低驗收
門檻本身是產品品質決策，必須由劉老師核准後才能有 session 據此開工。

## 技術調查（為讓提案不是空談，先查證可行性）

讀 `WMOM-20260505-26` 原文（`ISSUES.md`），Service/Maintenance state 子項要求
4-6 個 tag：service mode flag / lockout-tagout state / manual override active /
calibration mode / firmware version。母 issue acceptance 要求「至少 5 條新 tag
能在 fault scenario 下看到變化」——但這類 tag 本質是**操作/管理狀態**，不是感測器
讀數，多數不會因物理故障而變化（例如 firmware version 不會因故障改變；lockout
狀態是操作程序觸發，不是物理故障觸發），這正是前一 session 判定「無前例可循、
會引入設計歧義」的根本原因。

實地查證現有程式碼後發現母 issue 描述有**過時之處**：

- `WSRV_SrvOn`（Service Mode On）**已存在**於
  [`scada_registry.py:420`](modules/monitoring/simulator/physics/scada_registry.py#L420)，
  由 [`turbine_physics.py`](modules/monitoring/simulator/physics/turbine_physics.py) 內
  真實的 `self.service_mode` 布林狀態驅動（非手刻 mock）——母 issue 列的「service mode
  flag」其實已經做了，只是母 issue 文字沒更新。
- `operator_stop`（[`turbine_physics.py:294`](modules/monitoring/simulator/physics/turbine_physics.py#L294)）
  是既有真實狀態，由 `cmd_stop()`/`cmd_start()` 等真實控制路徑翻轉，目前**未**單獨
  暴露成 SCADA tag——可對應母 issue 的「manual override active」。
- `tur_state == 7`（emergency stop，見
  [`turbine_physics.py:377`](modules/monitoring/simulator/physics/turbine_physics.py#L377)
  `cmd_emergency_stop(cause=...)`）是既有真實狀態機狀態，目前也**未**單獨暴露成
  SCADA tag——可對應母 issue 的「lockout-tagout state」（emergency-stop 待人工重置，
  語意上等同輕量版 lockout）。
- `calibration mode` 與 `firmware version` **在現有程式碼中完全找不到對應概念**
  （grep 全庫零命中）——這兩項若要做，calibration mode 需要全新設計一套觸發機制
  （無前例可循，仍屬設計歧義），firmware version 則只能是靜態常數（無「變化」可言）。

## 提案內容（草案，待劉老師核准）

**提議新開 `WMOM-20260505-26-a`（母 issue `WMOM-20260505-26` 的降低版子項，僅涵蓋
2 個新 tag，不涵蓋 calibration mode / firmware version）**：

- **Deliverable**：
  - 新 tag 對齊既有 `WSRV_*` 命名慣例：`WSRV_ManualOverride`（映射既有
    `operator_stop`）、`WSRV_LockoutState`（映射既有 `tur_state == 7`）
  - 寫入 `scada_registry.py` `_TAGS` + `turbine_physics.py::step()` 輸出
    （比照 `WSRV_SrvOn` 既有寫法）
- **提議的降低版 acceptance**（取代母 issue「5 條新 tag 於 fault scenario 下變化」
  這一條，僅對本子項適用；母 issue 其餘 3 類〔protection / cooling / converter
  internal〕的原 acceptance 完全不變）：
  1. 兩個新 tag 皆註冊在 `scada_registry.py`，schema/type/subsystem 正確
  2. 兩個新 tag 的值**必須**由既有真實狀態（`operator_stop` / `tur_state==7`）
     直接映射，不得手刻新的獨立布林旗標（避免與既有狀態語意分裂）
  3. 整合測試證明：呼叫既有真實控制路徑（`cmd_stop()`/`cmd_start()` 翻轉
     `operator_stop`；`cmd_emergency_stop()` 進入 `tur_state==7`）時，對應 tag
     值同步翻轉
  4. 既有 18/21 quality check 不被破壞
- **明確排除**（本子項不含）：calibration mode、firmware version——因兩者在現有
  系統內無對應真實狀態可映射，做了也只是手刻 mock 或靜態常數，價值低於工作量，
  且若要做仍需劉老師先拍板要不要新建一套 calibration-mode 觸發機制。母 issue
  對這兩個 tag 的原始需求維持不變、留在母 issue 範圍內，**未來若劉老師認為需要
  可另立提案**。
- **對母 issue 整體驗收的影響**：此子項只交付 2 個 tag（非母 issue 寫的 4-6 個），
  對 104→125-130 的總數目標貢獻較小，需搭配母 issue其餘 3 類一起做才能真正達標——
  本提案**只解決「Service/Maintenance state 這一類要求物理耦合驗收但語意不通」
  的設計歧義**，不代表做完這個子項母 issue 就算收尾。

**給劉老師的具體問題（可一行回覆）**：
> 是否核准開 `WMOM-20260505-26-a`（`WSRV_ManualOverride` + `WSRV_LockoutState`
> 兩個新 tag，映射既有 `operator_stop`/`tur_state==7` 真實狀態，降低版 acceptance
> 如上）？核准後下個 autonomous session 可直接單 session 完工，不再卡住。

若核准，下個 session 可直接依上述提案認領 `WMOM-20260505-26-a`，範圍/acceptance
已無歧義，屬單 session 可完工工作。

## 誠實回報

- 本次 preflight 自我測試完整重跑且全綠（backend/frontend 數字皆列於上），非跳過。
- 本次**未實作任何程式碼**、**未新增測試**——本 session 的產出是「可行性調查 +
  草擬提案文字」，不是程式碼交付，因此無自動化測試保護，也不需要 mutation-verify
  （沒有邏輯變更可驗證）。
- 提案內的 `operator_stop`/`tur_state==7` 對應關係僅透過讀原始碼 + grep 交叉驗證，
  未實際跑一次 `cmd_stop()`→ tag 翻轉的端到端驗證（因為 tag 尚未存在，無法驗證，
  這正是提案要交付的內容）。
- `WMOM-20260504-11`（cost ledger）/ `WMOM-20260509-F6`（PostgreSQL docker）/
  `WMOM-20260505-27`/`-28`（保護電驛、單齒缺陷模型）/ `WMOM-20260513-01`（UI v2）
  這 5 項仍維持 `-01`/`-02` 兩個 session 的既有結論，本次未重新展開調查（避免
  第三次重複相同分析，相關細節見前兩份 work-log）。

## Wrap-up

- 無程式碼變更；`ISSUES.md`：在 `WMOM-20260505-26` 本文附加上述提案內容（供劉老師
  直接在該 issue 內看到具體提案），另新增本次 session 記錄 issue
  `WMOM-20260928-03`（Status: done——本 session 的交付物「調查 + 提案文字」已完成）。
- `STATUS.yaml` / `TODO.md` 同步更新統計與最新摘要。
- **下個 session**：
  1. 若劉老師已核准 `WMOM-20260505-26-a` → 直接認領，範圍已無歧義，預期單 session
     可完工。
  2. 若劉老師尚未回覆 → 累積的 4 個決策問題（本次的 `-26-a` 提案 + 前兩個 session
     列出的 cost ledger / PostgreSQL docker / 物理模型深化排程 / UI v2）已經是
     連續三個 session 的卡點，建議下個 session 不要再重複展開同款調查，改為
     **也對 `WMOM-20260505-27`/`WMOM-20260505-28`（保護電驛、單齒缺陷）比照本次
     手法，看能否切出類似「小而無歧義」的降低版子項**，持續嘗試打破僵局，而非
     單純等待。
