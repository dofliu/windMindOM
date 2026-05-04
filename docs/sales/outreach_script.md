# Outreach Script — windMindOM friendly 客戶接觸

> 對應 issue：WMOM-20260503-05
> 用途：給劉老師接觸 friendly 運維廠商時直接用的 cold email 範本 + 30 分鐘 demo agenda + objection handling FAQ

---

## 1. Cold email 範本（中文）

### 範本 A — 透過共同朋友介紹（首選，回覆率最高）

```
主旨：{介紹人}提到貴司 Z72 機型運維 — 想分享一個工具

{對方姓名} 您好，

我是國立勤益科大智動系劉瑞弘。{介紹人} 提到貴司在 {風場名} 的
Z72 運維工作，建議我直接跟您聯絡。

我們最近做了一個叫 windMindOM 的工具，目標是把運維廠商現在散在
Excel + LINE + 紙單的工作（SCADA 監控、庫存派工、成本估算、警報
查手冊）整合在一個 UI。從 digiWindTurbine 物理模擬器商業化升級而來，
不需要您先給資料就能看 demo。

附 onepager（A4 一頁）給您快速看。如果有興趣，我可以**用 30 分鐘**
線上 demo 給您看 — 純展示，不用準備資料、無壓力。

下週二 / 四 上午方便嗎？

劉瑞弘 / DOF Lab
moredof@gmail.com
github.com/dofliu
```

附件：`pitch_deck_v0.8.1_onepager.pdf`

---

### 範本 B — 直接 cold（無介紹人，較難但仍可用）

```
主旨：給離岸風場運維廠商的工作整合工具 — 想 30 分鐘分享

{對方姓名} 您好，

我是國立勤益科大智動系劉瑞弘，過去 5 年研究風電 SCADA 與 AI/RAG
工業應用。最近我們做了一個工具 windMindOM，專門給「運維廠商」
（不是業主）使用 — 目標是取代你們現在 Excel + LINE + 紙單的組合。

5 大模組：監控 + 庫存派工 + 成本（ECN-style）+ 報表 + 警報手冊查詢
（後者讓現場工程師 30 秒內找到答案，不用打電話問師傅）。

第一個目標客戶是 Z72 機型運維廠商 — 我們手上已經有 Z72 真實資料 +
Bachmann M1 PLC 連線驗證 + 物理模擬器（無實場也能 demo）。

附 onepager 給您快速判斷有沒有興趣。如果方向 align，我可以**30 分鐘
線上 demo** — 純展示，不用準備任何資料。

下週二 / 四 上午方便嗎？

劉瑞弘 / DOF Lab
moredof@gmail.com
github.com/dofliu / doflab.cc
```

附件：`pitch_deck_v0.8.1_onepager.pdf`

---

### 範本 C — Follow-up（首封 7 天無回應後寄）

```
主旨：Re: {原 subject} — 重附 onepager

{對方姓名} 您好，

上週寄的 windMindOM 介紹不知道是否有看到？我猜可能被埋在信箱裡。

附件再發一次 — A4 一頁，30 秒就能看完。如果方向 align，30 分鐘 demo
隨時候教；如果暫時沒需求也沒關係，請當成沒這封即可。

劉瑞弘 / DOF Lab
moredof@gmail.com
```

附件：`pitch_deck_v0.8.1_onepager.pdf`

> **規則**：Follow-up **只寄一次**，第二次無回應就 park，不要 burn relationship。

---

## 2. 30 分鐘 demo agenda（線上 / 線下都適用）

### 0-5 min：背景與目的設定

- 自我介紹（1 分鐘）— 我是誰、為什麼做 windMindOM
- **這場 demo 的目的不是賣產品，是聽您**：「您現在怎麼做運維、最痛的是什麼」
- 邀請對方先講 5 分鐘現況

### 5-10 min：對方說現況（**這是 demo 真正的價值**）

> 「能不能說說貴司現在怎麼處理：每月給業主的報告、跨風場的庫存盤點、
>  班長派工、SCADA 資料查詢？」

聽他們說。**用 5 分鐘，不打斷**。

### 10-25 min：windMindOM demo（screen share）

按 deck 順序展示：

1. **打開 simulator**（30 秒）— 14 台風機跑起來，跟真實 SCADA 一模一樣
2. **5 modules 一張圖**（1 分鐘）— 解釋「整合在一個 UI」的價值
3. **痛點 → 對應功能**（5 分鐘）— 把對方剛說的痛點連回某個 module（即使該 module
   還沒做，誠實說「M3-M5 會做，現在是 monitoring + simulator 已 ready」）
4. **三層套餐 + 預算錨點**（3 分鐘）— Basic / Pro / Enterprise + 「比少請半個工程師
   便宜」
5. **Roadmap 6 個月 + 第一個客戶 PoC**（2 分鐘）— 如果他們是首發客戶，他們得到
   什麼（priority feature input、合約折扣、case study 共享）
6. **Q&A**（剩餘時間）— 鼓勵問難問題；卡住的問題誠實說「不知道，我回去查」

### 25-30 min：Next step + 收尾

- **不要硬推合約** — 第一場是 discovery
- 問三個 closing 問題：
  1. 「這工具如果真做出來，您會用嗎？哪 1-2 個 module 對您最重要？」
  2. 「您身邊有沒有其他運維廠商的朋友，會對這個有興趣？」
  3. 「下次我做出 cost / workflow module 時，可以再來找您 review 嗎？」
- 結尾：「謝謝您的時間，今天聽您講比我講多。回頭我會把今天的回饋整理成
  M3-M5 設計輸入。」

---

## 3. Objection handling — FAQ

### Q1：「你們已經有客戶了嗎？」

> 「目前 0 個 paid 客戶，pilot 客戶在找 — 所以我才來找您。我們的優勢是 digiWindTurbine
> 平台已驗證，不是 0 → 1，是把研究產品商業化。如果您有興趣作 friendly pilot，
> 我們會給 reference customer 折扣 + 優先功能輸入。」

### Q2：「你跟 SAP PM / Bazefield 比怎麼樣？」

> 「我們不跟 SAP / Bazefield 競爭 enterprise 市場 — 那是大廠的戰場。我們瞄準
> 中小型運維廠商：他們買不起 SAP，但 Excel + LINE 又不夠用。windMindOM 的
> 月費是 SAP PM 的 1/10，但派工 + 庫存 + 成本 + RAG 都能做基本款。」

### Q3：「警報 RAG 是不是 ChatGPT 包裝？」

> 「不是。我們用的是 RAG_Ultimate（一個獨立 research line），核心是
> 把 OEM 手冊 + SOP + 過往警報處置餵成 vector store，警報觸發時直接拉
> 相關段落 — 不靠 GPT 生成，靠 retrieval + 結構化展示。如果有興趣，
> 可以 deep dive。」

### Q4：「你們是學校單位，能簽商業合約嗎？」

> 「劉老師個人有 DOF Lab 為對外品牌，可走產學合作或顧問合約模式；
> 第一階段是 NT$2-4M / 3 個月部署 + 維護，類似建置案。後續穩定後會
> 評估獨立公司化。」

### Q5：「如果你們 6 個月做不完怎麼辦？」

> 「最大風險。我們的 mitigation：
> 1) Monitoring + Simulator 已 ready，第一週就能 deliver
> 2) 一月一 module，每月有可 demo 的交付
> 3) 不貪多功能；如果某 module 來不及，砍 scope 不延期
> 4) 您作為 friendly pilot，可以先用 Basic 套餐（已 ready），Pro/Enterprise
>    晚 3-6 個月也不影響您日常運維」

### Q6：「我們已經用 OEM 自家 dashboard，幹嘛換？」

> 「OEM dashboard 只看自家機型 — 您運維 3 種 OEM 就要看 3 個 dashboard，
> 還沒包括庫存、派工、成本、給業主月報。我們的價值是**整合**：把您
> 跨機種的工作鏈打通，OEM dashboard 還是繼續看 single-source-of-truth，
> 但所有衍生工作（工單、成本、報表）跑 windMindOM。」

---

## 4. 寄送 logistics

### 寄送時段（最佳開信率）

- **週二 10:00-11:00 am** 或 **週四 2:00-3:00 pm**
- 避開：週一 morning rush、週五 afternoon、午餐時段、晚上

### 一次寄幾封？

- **3-5 封 / 週**（不要 batch 一次寄 20 封 — 個人化會失真）
- 每封都改 subject 與第一段（提及對方 specific 風場 / 機型 / 介紹人）

### 追蹤工具

- 普通 email 即可
- 如果想看開信率，可以用 Mailtrack（Gmail 擴充套件，免費版 ok）
- **不要用 mailmerge tool** — friendly pilot 階段，每封都要看起來像 1-on-1 寫的

### 第一封寄完後

- 進 `friendly_contacts.md` 的 contact entry，更新 Status: `reached_out`、Last touch: 今天
- 設 reminder：7 天後 follow-up（範本 C）
- 收到回覆 → Status: `replied`，回覆內容寫進 Notes

---

## 5. 第一場 demo 後

立刻（24 小時內）填 `customer_feedback/YYYY-MM-DD-{客戶代號}.md`，趁記憶熱用 `_TEMPLATE.md`
模板。**這份回饋是 M3-M5 design input 的關鍵原料**，不是內部備忘錄。
