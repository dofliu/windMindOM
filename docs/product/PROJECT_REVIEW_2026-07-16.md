# windMindOM 專案檢視與後續建議 — 2026-07-16

> 檢視者：Claude（project-review session）
> 範圍：全 repo 現況盤點 + 健康度實測 + 策略/工程風險 + 可執行建議
> 對象：劉老師（決策）＋後續 autonomous / 人工 session（執行）
> 一句話結論：**程式碼健康、進度超前；但工程已跑在商業驗證前面，且「開工必讀」的文件全面過期。下一步的重點不是再寫功能，而是（1）對齊文件真相（2）把飛輪轉向 M6 收入路徑（3）啟動已擱置兩個月的客戶接觸。**

---

## 1. 總評（TL;DR）

| 面向 | 評分 | 說明 |
|------|:----:|------|
| 程式碼健康度 | 🟢 強 | 5 模組全綠，實測 backend 778+ tests passed、frontend ~797 vitest、物理一致性維持 |
| 產品完整度 | 🟢 強 | M1–M4 100%、M5 75%；監控/成本/工單/簽核/庫存/報表/RAG 主功能皆到齊 |
| 文件真相對齊 | 🔴 差 | CLAUDE.md / ROADMAP dashboard / README / TODO / STATUS 全部停在「M1、v0.8.1 2026-05」，與實際 M5 75% 脫節 6 週 |
| 商業進度 | 🔴 落後 | M6（收入里程碑）0%；客戶接觸 issue 自 2026-05 open 至今未執行；瓶頸在人不在程式 |
| 工程節奏 | 🟠 停擺 | autonomous 飛輪 2026-06-08 後停擺 5.5 週；停擺前兩週在補低價值 render 測試 |

**核心矛盾**：目標是 **2026-Q4 第一個客戶 PoC + 第一筆合約（NT$2–4M）**。現在是 7 月中，離 target 剩 ~3.5 個月。技術上 M5 幾乎完成、程式庫綠燈可 demo；但 M6 的每一個 gating item（客戶接觸、現場部署、PLC 連線、真 auth）都卡在「需劉老師執行 / 需客戶現場」，**不是再多寫程式能推進的**。專案的風險已經從「做不做得出來」轉移到「賣不賣得出去、部不部署得了」。

---

## 2. 現況盤點（本次實測，非引用舊 STATUS）

- **分支/git**：main 乾淨；最後一次 commit `77ccdc0` 於 **2026-06-08**（距今 5.5 週無活動）。
- **模組規模（非測試 Python 行數）**：monitoring 14,142｜workflow 7,154｜cost 4,841｜reporting 1,620｜knowledge 1,408。
- **測試實跑結果**（本 session 於乾淨環境安裝核心依賴後實測）：
  - `workflow + cost + reporting`：**590 passed, 1 xfailed**（CI 涵蓋）
  - `monitoring + tests/physics`：**188 passed**（⚠️ **CI 未涵蓋**）
  - `knowledge`：需 torch/chromadb，測試以 `importorskip` 設計，CI 無模型權重仍可過
- **里程碑**：M1 85%（infra done、客戶接觸待執行）／M2 M3 M4 100%／M5 75%／M6 0%。
- **Issue 統計**：open 12｜in_progress 2｜done 83。
- **銷售素材**：pitch deck v0.8.1（PDF/PPTX/one-pager）、outreach_script.md、friendly_contacts 範本 — **皆已就緒**，缺的是執行。

---

## 3. 主要發現（依優先級）

### 🔴 F1 — 「開工必讀」文件全面過期，新 session 會被誤導
CLAUDE.md §2 要求每個新 session 先讀 CLAUDE.md → PRODUCT_VISION → ROADMAP → STATUS，但：
- **CLAUDE.md §10「目前狀態」**：仍寫「Milestone: M1 Setup（2026-05）」「下次工作見 ROADMAP M1」。§13/§14 把 daily-workflow、slash commands 寫成「M1 第一週**將**搬入」——實際 `.claude/commands/` 早已存在。
- **ROADMAP.md 進度 dashboard（L204–213）**：M2–M6 全標 ⚪（未開始）、M1 標 🟡 in_progress——與 STATUS 的 M1–M4 done 直接矛盾。
- **README.md**：knowledge 標「🔜 M5」、產品版本「v0.8.1 2026-05 baseline」。
- **TODO.md**：最後更新 2026-05-29、「現況（2026-05）」。
- **後果**：新接手者（人或 AI）會用錯誤的「我們還在 M1」心智模型開工，或對客戶講出低估自己的話術。這是**最便宜、最該先修**的問題。

### 🔴 F2 — 工程超前、商業落後；M6 卡在人不在碼
- M6-1 現場部署、M6-2 Z72 PLC 連線、**WMOM-20260503-05 客戶接觸**（自 5 月 open 至今）全部 🟡，等劉老師 / 客戶。
- decision_log 自 2026-06-08 後**零新決策**——代表這段期間沒有任何方向性推進。
- 「Simulator-first」的設計初衷就是為了**無實場也能 demo**。素材已備齊，卻沒有走出去接觸客戶。**這是目前對 Q4 目標威脅最大的單一風險。**

### 🟠 F3 — Autonomous 飛輪停擺，且停擺前在補低價值工作
- 6/04–6/08 的 commit 幾乎全是 `test(...): XxxPanel component render 測試`（WMOM-20260604~0607 共 ~20 個近乎同質 issue）。
- 飛輪的 auto-merge 閘門（CI 綠就合）獎勵了「乾淨、無設計歧義、可自動接」的工作 → 系統性地挑 render 測試，而**迴避了高價值但需人決策的 critical path**（客戶、部署、真語料、auth）。
- 然後在 6/08 完全停下。**飛輪需要重新啟動，並改用「對 M6 有貢獻」為挑題準則，而非「autonomous-friendly」。**

### 🟠 F4 — CI 未涵蓋最大且最關鍵的模組
- `ci.yml` 只跑 workflow/cost/reporting/knowledge；**monitoring（14K 行、物理/SCADA 核心）+ tests/physics（共 188 tests）完全不在 CI**。
- 任何改動打壞物理一致性或 SCADA 層，CI 不會擋，auto-merge 還會直接合進 main。**與「不要破壞既有物理一致性」的守則直接衝突。**

### 🟠 F5 — M6 出貨硬前提尚未動工
- **真 auth 缺席**：身分靠 request body 的 `actor_id` + 前端 localStorage mock login，任何 client 可冒充任何人、無授權強制。已追蹤為 **M6-4（JWT/RBAC/HTTPS）但未開工**。對付費客戶多租戶部署，這是**不可妥協的前提**，且牽動每個 router 的 signature，越晚做越痛。
- **部署 footprint**：M5-2 引入 torch + sentence-transformers + 95MB 模型（DEC-20260608-01）。M6 要 docker-compose 部到客戶現場，torch image 體積可觀。需確認客戶端硬體 / GPU，或評估改用「純預算向量 + 輕量 query 端」以縮小 footprint。

### 🟡 F6 — 工程衛生 / 可維護性
- **ISSUES.md 已 3,090 行 / 292KB**，仍當「single source of truth」；每筆 changelog blurb inline 塞入，膨脹到不利檢索。
- **STATUS.yaml `next_milestone`** 是一個數百字的巨型 run-on 段落，早已不是「status 欄位」該有的樣子。
- **DemoOrchestratorPage 仍是 skeleton placeholder**（WMOM-20260513-02）——一鍵劇本式 demo 對客戶展示價值高，但需劉老師拍板產品決策。
- **vendored openopc2**（`shared/plc_clients/bachmann/openopc2-0.1.18/` 整包含測試）——CLAUDE.md §12 明訂「不要 fork 其他 repo 程式碼進來（用 submodule / pip）」；此為 Windows OPC-DA 限制下的權衡，建議至少加註 README 說明來源與為何 vendored。

---

## 4. 後續建議（可執行、附負責人與優先級）

### P0 — 本週就做（低成本、高槓桿）
1. **對齊 onboarding 文件真相**〔autonomous 可做〕
   同步 CLAUDE.md §10/§13/§14、ROADMAP dashboard、README 狀態欄、TODO.md、STATUS `next_milestone` 至「M5 75%、M1–M4 done」。開 issue `WMOM-2026xxxx-xx — 文件真相對齊`。
2. **把 monitoring + physics 加進 CI**〔autonomous 可做〕
   `ci.yml` backend job 補 `modules/monitoring/tests/ tests/`。實測本地 188 passed，加進去即可堵住物理迴歸缺口。
3. **重啟飛輪，改挑題準則**〔劉老師定調〕
   若要續跑 3-hourly autonomous worker，把挑題準則從「autonomous-friendly」改為「對 M6 critical path 有貢獻優先」；render 測試已足夠，停止再補。

### P1 — 本月內（推動 M6 收入路徑）
4. **啟動客戶接觸**（WMOM-20260503-05）〔**劉老師，最高商業優先**〕
   素材齊備，只差執行：用 outreach_script 寄 3–5 封 cold email、約 1 場 simulator demo。這是解鎖 M6 的唯一鑰匙。
5. **決定並開工 M6-4 真 auth**〔劉老師定方案 → autonomous 實作〕
   選最小可行方案（建議：FastAPI JWT dependency + 3 角色 RBAC：管理層/班長/現場工程師，對映既有簽核角色）。越早接、router 改動越小。
6. **部署 footprint 決策**〔劉老師〕
   確認 knowledge 模組上客戶現場的形態：帶 torch 的完整 image vs. 輕量向量檔方案；牽動 docker-compose 與 M6-1。寫成 DEC。

### P2 — 擇機處理（衛生 / 體驗）
7. **文件瘦身**：ISSUES.md 的 changelog 全面移進 `docs/legacy/issues_changelog_archive.md`（已有此檔），主檔只留「當前 open + epic」；STATUS `next_milestone` 縮成 1–2 句 + 指向 work-log。
8. **DemoOrchestrator 決策**（WMOM-20260513-02）：若走客戶 demo，值得把 skeleton 接成劇本式一鍵演示。
9. **openopc2 vendored 加註來源說明**；physics 強化群（WMOM-20260505-23~28）維持 park，非商業必需。

---

## 5. 建議的下一個 sprint（具體 issue 清單）

| 優先 | 建議 issue | 類型 | 負責 |
|:---:|---|---|---|
| P0 | 文件真相對齊（CLAUDE/ROADMAP/README/TODO/STATUS） | 🔵 autonomous | AI |
| P0 | CI 補 monitoring + physics 測試 | 🔵 autonomous | AI |
| P1 | 客戶 cold email + 約 demo（WMOM-20260503-05） | 🟡 商業 | 劉老師 |
| P1 | M6-4 真 auth 方案 DEC + JWT/RBAC 骨架 | 🟡→🔵 | 劉老師定案 / AI 實作 |
| P1 | 部署 footprint DEC（torch vs 輕量） | 🟡 | 劉老師 |
| P2 | ISSUES.md / STATUS 瘦身 | 🔵 autonomous | AI |

---

## 6. 一句話給下一個 session

> 程式庫已經夠好了。**接下來每一個「再寫一個功能 / 再補一個測試」的衝動，都該先問一句：這對「2026-Q4 拿到第一筆合約」有幫助嗎？** 如果沒有，先去對齊文件、把飛輪轉向 M6、然後幫劉老師把客戶約出來看 demo。
