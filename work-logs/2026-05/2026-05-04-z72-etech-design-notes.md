# 2026-05-04 — z72_etech 取設計：DN-01 Work Order Lifecycle（WMOM-20260504-14）

> Session 類型：取材 + 設計
> Session 長度：中
> 主導：Claude
> 結果：z72_etech repo 完成 inventory；DN-01 Work Order Lifecycle 第一份 design note 雛形產出

---

## 1. Session 目標

進 M3 主線：把 etech 的工單 / 簽核 / 領料 / 日誌設計在 windMindOM 重做。
本 session 重點：
- 對 z72_SCADA_etech repo 做 inventory（依劉老師「取材選 A」方針：讀程式產出 design notes，不取程式）
- 產出 3 份 design notes 中第一份 DN-01 Work Order Lifecycle
- 開 7 個 M3 sub-issue (WMOM-14..20) 切分大份量

劉老師 2026-05-04 給的 domain 軸線：
> etech = onshore 簡化版（故障 → 派工單 → 檢修 + 每日工作日誌 + 簽核 + 領料連庫存 → 連結人員 → work order）；
> windMindOM 延伸 = 離岸風場派工（vessel / weather window / crew / 安全）

---

## 2. 實際完成

### 2.1 主要工作

- ✅ 讀完 z72_SCADA_etech 兩份既有 inventory：
  - `專案盤點報告_2026-04-30.md`（10 大功能模組地圖 + 重大風險）
  - `重構路線圖_2026-04-30.md`（業主 2026-04-30 縮減 scope，etech 後續走 bug-fix + UI + PLC 直連 + 風場運維新功能）
- ✅ 讀完 etech 5 個關鍵 module 程式：
  - `server/repair.js` — 工單正式單（48 行）
  - `server/repairTemp.js` — 工單暫存單（103 行）
  - `server/trackFrom.js` — 追蹤觀察單（54 行）
  - `server/removeFrom.js` — 移除單（39 行）
  - `server/leadersign.js` + `supervisorsign.js` + `materialsForm.js` — 簽核 + 領料
- ✅ ISSUES.md 開 M3 主線 7 個 sub-issue（WMOM-14..20）
- ✅ Claim WMOM-14 + 開 work-log + 開 design-notes/m3/ 目錄
- ✅ 產出 [`docs/design-notes/m3/DN-01-work-order-lifecycle.md`](../../docs/design-notes/m3/DN-01-work-order-lifecycle.md)（**今日主產出**）

### 2.2 卡住或延後的事

- DN-02（Approval Multi-level）+ DN-03（Inventory ↔ Material Request）留下次 session 寫
- removeFrom 的真實 use case 不確定（看似「廢棄申請」但程式碼裡無明顯生產者）→ 開列為 walkthrough 問題

### 2.3 重大決策（在 DN-01 內紀錄）

- etech 的 4 collection（repairTemp / repair / trackFrom / removeFrom）→ windMindOM 統合為單一 `work_order` 表 + 狀態機
- etech `totalformnumber` business key → windMindOM 沿用人類可讀格式：`WO-{farm_id}-{yyyymm}-{nn}`
- offshore 延伸欄位明列：`vessel_id`、`weather_window_id`、`crew_size`、`logistic_hours`（與 K13 cost engine 同維度）

---

## 3. 產出清單

### 新增檔案

- `docs/design-notes/m3/DN-01-work-order-lifecycle.md`
- `docs/design-notes/m3/README.md`（3 份 DN 索引 + etech repo 對照表）
- `work-logs/2026-05/2026-05-04-z72-etech-design-notes.md`（本檔）

### 修改檔案

- `ISSUES.md`（M3 主線 7 個 sub-issue + WMOM-14 claim）

### 動了狀態的 issue

- WMOM-20260504-14: open → in_progress（DN-01 done，DN-02 / DN-03 待補）
- WMOM-20260504-15..20: 全部 open（依賴 -14 完成）

## 4. 下次怎麼接手

1. 第一優先：補 DN-02（Approval Multi-level）+ DN-03（Inventory ↔ Material Request）→ WMOM-14 才能 done
2. 第二優先：30 分鐘 walkthrough 跟劉老師確認 3 份 DN（WMOM-15）— 之後才能寫 code
3. 阻擋項：DN-01 內列的 walkthrough 問題（如 removeFrom use case、追蹤觀察 vs 需改善的 SLA 差異）需要劉老師回答

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 讀 etech repo（盤點 + 程式） | 35% |
| 寫 DN-01 design note | 50% |
| ISSUES.md 切 7 個 sub-issue | 10% |
| Wrap-up / commit | 5% |

## 6. 學到的事

- **單一 collection + 狀態機 prevails over 多 collection + ad-hoc transitions**：etech repairTemp/repair 雙 collection 是 anti-pattern，可從 PUT body 半自動推狀態看出設計沒收斂
- **business key vs surrogate ID**：etech 走 `totalformnumber` (yymm 格式) + `_id` ObjectId 雙軌，windMindOM 應沿用 business key 給人類用，但對外 API 與 FK 全用 surrogate UUID
- **「故事」型流程靠 frontend if 串 = 設計偷懶**：repair.vue 1674 行靠 chooseschange 分支 → 後端只是 dumb storage。windMindOM 應後端帶完整狀態機 + transition rules，frontend 只 render

## 7. Open questions（park）

- removeFrom collection 真的是「移除請求」還是「批量清理」？沒看到 frontend 入口點，要 walkthrough 確認
- etech 的 `chooseschange ∈ {完成, 追蹤觀察, 需改善}` 三分類，windMindOM 是否要保留還是簡化為布林 `needs_followup`？
- M5 alarm event 與 M3 work order 的綁定點：alarm_id → work_order.source_alarm_id 還是反向？（暫定前者）
