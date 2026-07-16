# M6 部署前置 — 決策簡報（待劉老師拍板）

> 產出：project-review follow-up（接 `PROJECT_REVIEW_2026-07-16.md` P1）
> 狀態：**proposed** — 以下兩項為 M6 客戶部署的硬前提，各需一個方向決策。
> 決策後：把選定案落成 `decision_log.md` 的正式 DEC，再開 issue 實作。
> 格式：每項給「現況 → 為何是 M6 前提 → 選項 → 我的推薦」，你只要選 A/B/C（或改）。

---

## 決策 1 — M6-4 真 auth（取代 mock login）

### 現況（實測）
- 身分來源：前端 `getCurrentActorId()` 讀 localStorage（`wmom_actor_id`）→ **放進 request body 的 `actor_id`** 送後端。
- 後端**無任何驗證層**（grep：0 個 jwt/oauth/authenticate 命中）；任何 client 可送任意 `actor_id` 冒充任何人、無授權強制。
- 角色模型（已存在，別重造）：`modules/workflow/domain/signoff.py` 定義 **4 階簽核 `EMPLOYEE / LEADER / SUPERVISOR / TREASURY`**，由 PLC group 號對映（500→SUPERVISOR…），另有 group 999＝系統管理員（非簽核角色）。前端 `mockUsers.ts` 有 4 個 fixture（Alice/Bob/Carol/Owner）餵這套多階簽核。
- 現場工程師 persona 走 `/field/`（完工簽名/拍照），身分同樣靠 mock actor_id。

### 為何是 M6 前提
付費客戶＝多真實使用者。身分可冒充 → 簽核形同虛設、完工佐證無法歸屬、跨風場資料無隔離。**這是「能不能交付給付費客戶」的門檻，不是 nice-to-have。** 且 `actor_id` 目前散在每個 router 的 request body，越晚接、signature 改動面越大。

### 需要你定的子決策
1. **登入機制**：seeded 帳密表（username+password，最簡、適合單客戶 on-prem）／ 客戶 AD/SSO 介接 ／ 單一共享 token（PoC 應急）。
2. **M6 首個 PoC 要多完整**：只要「真登入、不可冒充」即可，還是第一版就要完整 per-role 授權強制？
3. **角色收斂**：是否統一為 `admin / management(owner) / supervisor / leader / employee(含 field)` 並對映既有 4 階簽核？

### 選項
- **A（推薦）— 漸進、不破壞既有**：新增後端 user 表 + `POST /auth/login` 發 JWT + `get_current_actor` FastAPI dependency（**無 token 時 fallback 到現有 dev/actor_id 行為**，既有測試零改）。角色對映既有簽核階。前端 mock login 換真登入表單 + token 儲存。router 逐支從「body actor_id」遷到「dependency 注入」，分批 PR。→ 可審可逆、每步 CI 綠。
- **B — 一次全量**：user 表 + 全 router 改 JWT dependency + 前端真登入，一個大 PR 到位。快但 PR 巨大、審查重、迴歸風險高。
- **C — 只發正式 DEC 不寫碼**：我把選定設計寫成 DEC，你排期後另開實作。

**我的推薦：A**，登入用 seeded 帳密表（單客戶 on-prem 最簡），M6 首版先做到「真登入 + 不可冒充 + 現場工程師只看自己工單」，完整 per-endpoint 授權強制排 A 的後續批次。理由：符合 §6.3「架構改動先 DEC」、非破壞式可逐步驗證、對映既有簽核角色不重造輪子。

---

## 決策 2 — 部署 footprint（knowledge/RAG 上客戶現場）

### 現況
- M5-2（DEC-20260608-01）query 端內嵌 `Z72_WT_embed_small` encoder，收 `chromadb + sentence-transformers + torch`（torch 自動帶入）+ ~95MB 模型權重（走 deploy artifact，不入 git）。
- M6-1 要 docker-compose 部到客戶現場；含 torch 的 production image 體積可觀（常 2–4 GB＋）。

### 為何是 M6 前提
客戶現場硬體未知（有無 GPU、磁碟、離線與否）。image 太大 → 部署/傳輸/更新都痛，且 torch 在無 GPU 機器上只用 CPU inference 也是重依賴。

### 選項
- **A — 維持現狀（帶 torch）**：最省事、已驗證可跑。先量測實際 image 大小 + 確認客戶硬體能吃。
- **B — 輕量化**：query encode 改輕量方案（預算好查詢向量／改極小 encoder／或 encode 走外部服務），**torch 不進 production image**。image 大幅縮小，但要動 M5-2 檢索路徑 + 加驗證。
- **C — 先量測再定**：先在 CI/本地 build 出 image 量體積 + 列客戶硬體需求清單，數據到手再選 A/B。

**我的推薦：C 先量測**。這題本質是「客戶硬體 vs image 體積」的取捨，沒有實際數字前選 A/B 都是猜。我可以先跑一次 image build 量體積、列出「若客戶無 GPU / 磁碟 < X」的門檻，你拿數據 + 客戶現場資訊拍板。

---

## 附註 — 客戶接觸（review P1-3）不缺素材，缺執行
`docs/sales/outreach_script.md` 已有現成 cold email 範本（範本 A 介紹人 / 範本 B 直接）+ 30 分鐘 demo agenda + objection FAQ，`pitch_deck_v0.8.1_onepager.pdf` 也在。**WMOM-20260503-05 的瓶頸是「寄出 + 約 demo」這個動作本身**，不是要我再寫一份草稿。若你要我協助，能幫的是：針對特定對象客製 email、或準備 demo 腳本；但寄出這一步是你的。
