# WMOM 介面改版交接書 — 給 Claude Code 用

> 目標：把現有 WMOM 介面替換為「A · Calm Operator」設計，並支援 **日 / 夜** 兩種主題（夜間採用 C · Glass Cockpit 的翡翠玻璃色系）。
> 來源設計檔（在這個 design 專案裡）：`app/VA.jsx`、`app/data.js`、`WMOM App UI.html`

---

## 0. 給 Claude Code 的開場指令（複製這段貼到 Claude Code 對話）

```
請依照本目錄下的「WMOM 介面改版交接書.md」改版整個 WMOM 前端：
1. 先讀完交接書全文與「來源設計檔」段落列出的檔案。
2. 提出實作計劃（todo list），等我確認後再動手。
3. 以最小幅度修改後端 / API 介面；只改 UI 層。
4. 完成後請示範 5 個頁面（總覽 / 風機 / 維護 / 成本 / 歷史）的截圖，並做日 / 夜兩種主題切換。
```

> **附帶請把這幾個檔案放到 Claude Code 工作目錄**：`app/VA.jsx`、`app/data.js`、`WMOM App UI.html`、`design-canvas.jsx`（後者可選，僅作為對照預覽用）。

---

## 1. 設計總覽

| 項目 | 日間 (Light) | 夜間 (Dark) |
|---|---|---|
| 風格 | 鼠尾草綠＋暖米白／DM Serif 大標題／雜誌式留白 | 翡翠玻璃／深森林背景／同一份排版骨架 |
| 主色 `accent` | `#3F6B53` | `#3DDC97` |
| 背景 `bg` | `#F5F2EA` | `#0E1815` |
| 面板 `panel` | `#FFFFFF` | `#152320` |
| 邊框 `border` | `#E5E0D2` | `rgba(255,255,255,0.10)` |
| 主文 `text` | `#1F2D24` | `#E8F0EC` |
| 次要 `sub` | `#6B7669` | `#8FA39A` |
| 弱化 `faint` | `#9BA39A` | `#566860` |
| 主色淺底 `accentSoft` | `#E2EBE3` | `rgba(61,220,151,0.16)` |
| 警示 `warn` | `#C97B5A` | `#FF8E72` |
| 警示淺底 `warnSoft` | `#FBE8DD` | `rgba(255,142,114,0.18)` |
| 健康 `ok` | `#5C8A5F` | `#3DDC97` |
| 健康淺底 `okSoft` | `#DEEAD9` | `rgba(61,220,151,0.16)` |
| 琥珀（IDLE / MED）| `#B8A053` | `#FFB347` |

字型：
- 標題：**DM Serif Display**（H1，38–86px，行高 1，letter-spacing −0.8 ~ −3）
- 內文 / UI：**Manrope** 400/500/600/700
- 數字 / 程式碼：**JetBrains Mono** 400/500/600

CDN（沒有的話加進 `<head>`）：
```html
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet"/>
```

---

## 2. 全域版面骨架

所有頁面共用：

```
┌────────┬───────────────────────────────────────┐
│        │  PageHeader  (h1 + sub + actions)     │
│ Sidebar│ ─────────────────────────────────     │
│ 220px  │  Page-specific content                 │
│        │                                       │
└────────┴───────────────────────────────────────┘
```

- **Sidebar**：寬 220 px、`background: panel`、右側 1px border、padding `24px 16px`、上方 logo + WMOM、中段五個頁面 nav button、底部「後端正常」狀態 + EN/中 + ☀/☾ 主題切換。
- **Main**：`padding: 28px 36px`，`flex: 1`。
- **PageHeader**：H1 用 DM Serif Display 38px，副標 Manrope 14px / `sub`，右側放 1–2 個 `Btn`。

主題狀態：
- 用一個 React Context 或全域 store 管理 `theme: 'light' | 'dark'`。
- 把上方那張色票表做成 `themes.ts`，根據 `theme` 回傳整個 `C` 物件。
- 所有元件接收 `C` 而不是寫死顏色。
- `<html data-theme="dark">` 也順便切，方便圖表庫 / 第三方套件吃 CSS variable。

切換鈕（位於 sidebar 底部）：
- 圖示用 `☀` / `☾`
- 切換時把 `theme` 寫進 `localStorage`，初始化讀回。

---

## 3. 共用元件

### `<Card>`
```jsx
<div style={{
  background: C.panel, border: `1px solid ${C.border}`,
  borderRadius: 14, padding: 20
}} />
```

### `<Btn primary>`
- 一般：`background: panel; border: 1px solid border; color: text`
- primary：`background: accent; color: 白(日)/#0A0F0E(夜); border: none`
- 共同：`borderRadius: 8; padding: 8px 14px; fontSize: 13`

### `<PageHeader title sub actions>`
見上節版面骨架。

### Status pill
```jsx
<span style={{
  fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 999,
  background: bgFor(status), color: colorFor(status), letterSpacing: 0.5
}}/>
```
狀態對應：
- OPERATING / 運轉中 → `okSoft` / `ok`
- FAULT / 故障 → `warnSoft` / `warn`
- IDLE / 待機 → 琥珀
- OFFLINE / 離線 → `bg` / `faint`

---

## 4. 五個頁面規格

> 完整可執行原始碼在 `app/VA.jsx`，這裡只列必要資訊。實作時請把 `app/VA.jsx` 當作 single source of truth — 樣式、間距、SVG 圖表全部照抄。

### 4.1 風場總覽 (`overview`)
1. PageHeader：「早安，營運團隊。」+「彰化沿海　12 機・<日期>」。
2. Hero stat strip：4 等分卡片 — 風場功率（巨大數字 + 額定）／運轉中（n/12）／故障中（紅色背景 if >0）／平均風速。
3. 24h 趨勢圖：時段切換（1H/6H/24H/7D），SVG 漸層折線。
4. 風機卡片網格（4 欄 × 3 列）：`<TCard>` — 名稱、狀態 pill、巨大功率、迷你 sparkline、底部 wind/rpm/temp。

### 4.2 風機細節 (`turbine`)
1. 麵包屑「← 風場總覽 / WTxx」。
2. PageHeader：機名 +「正常發電」。
3. 主區（左 2/3）：4 個大數字 → 即時趨勢 4 通道（功率 / 風速 / 齒輪 / 振動）→ 子系統健康 8 格進度條。
4. 側區（右 1/3）：即時告警卡 → 最近事件清單 → 操作控制（▶ 啟動 / ■ 停機 / ⚠ 緊急停機）。

### 4.3 維護中心 (`maintenance`)
1. PageHeader：「維護中心」+「N 張未結工單・4 位技師在崗」。
2. 主區（左 2/3）：工單表格 — ID / 風機 / 問題 / 技師 / 優先 / 狀態 / SLA。
3. 側區（右 1/3）：技師排班（圓形頭像漸層 + ON DUTY / DISPATCHED / OFF DUTY pill） → 本週日曆（7 格，事件用色塊 + 邊框）。

### 4.4 成本模型 (`cost`)
1. PageHeader：「成本模型」+「LCOE · NPV · Monte Carlo · 20 年預測」。
2. 6 個 KPI 卡（3 欄 × 2 列）：Lifetime Revenue / LCOE（強調色）/ NPV / Payback / CapEx / OpEx。
3. 主區：20 年營收預測（P10/P50/P90 帶狀）+ 蒙地卡羅 5,000 次（P10/P50/P90 三排）。

### 4.5 歷史資料 (`history`)
1. PageHeader：「歷史資料」+「搜尋 SCADA 標籤・事件標記・CSV 匯出」。
2. 查詢條件卡（4 欄）：風機 / 時間範圍 / 標籤 / 事件。
3. 帶事件標記的功率輸出折線圖（FAULT 紅、WIND 綠、SYNC 藍三色虛線豎線）。
4. 事件紀錄表：時間（mono）+ 標籤 pill + 描述。

---

## 5. 國際化

- 所有字串維護在一個 `i18n.ts`，提供 `tr(en, zh)` helper（也可改成 i18next）。
- 預設 `zh-Hant`，sidebar 底部有 EN/中 切換。
- 數字、單位（MW、m/s、°C、rpm、¢/kWh）兩語通用，不需翻譯。

---

## 6. 替換步驟（給 Claude Code 的 to-do 範本）

```
[ ] 1. 加入字型 CDN（DM Serif Display / Manrope / JetBrains Mono）
[ ] 2. 建立 src/theme/themes.ts（兩套 C palette + theme provider）
[ ] 3. 建立 src/components/ 共用：Card、Btn、PageHeader、StatusPill、RingGauge、ChannelChart、BigChart
[ ] 4. 重寫 Sidebar：220px、五頁 nav、底部 EN/中 + ☀/☾
[ ] 5. 替換 Overview 頁
[ ] 6. 替換 Turbine 頁
[ ] 7. 替換 Maintenance 頁
[ ] 8. 替換 Cost 頁
[ ] 9. 替換 History 頁
[ ] 10. 接回原本的 SCADA / API（保留欄位名稱）
[ ] 11. 跑一次端到端，截 5 頁 × 2 主題 共 10 張圖確認
```

---

## 7. 注意事項

- **不要改 API / 後端 schema**。本次只改 UI。
- **保留現有資料欄位名稱**（power / wind / rpm / gearTemp / vib / pitch / yawErr 等）。
- **故障注入頁**未在本次設計中重畫，請沿用既有功能、套上新元件樣式（Card / Btn / Pill）即可。
- 所有顏色 **必須走 theme palette**，不可硬寫 hex。例外：圖表內事件標記色（紅 / 藍 / 綠）可以保留 hex，但要記得做日夜對應。
- 響應式：1280 px 以上保持目前 4 欄；1024–1279 改 3 欄；1023 以下 2 欄；768 以下 sidebar 收成漢堡。
- 無障礙：所有按鈕要有 `aria-label`，主題切換鈕加 `aria-pressed`。

---

## 8. 驗收標準

- [ ] 五個頁面在日 / 夜兩種主題下都能正常顯示，無破版。
- [ ] 主題切換能即時生效，且重新整理後狀態保留。
- [ ] 中英切換能即時生效。
- [ ] 所有圖表 / sparkline 在兩主題下顏色合理（不會出現深色背景上的深色線）。
- [ ] 既有的 SCADA 即時資料、故障注入、CSV 匯出功能維持運作。

---

完成後請貼出截圖給我確認 🌿
