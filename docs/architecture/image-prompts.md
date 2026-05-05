# 生圖模型 prompt — 給 windMindOM 視覺化圖片

> Mermaid 是給 dev 看的結構圖；這份是給 **客戶 / partner / 投資人**用的視覺呈現。
> 用 ChatGPT / Gemini Imagen / Midjourney / Stable Diffusion 都能跑。

---

## 使用方式

| 模型 | 推薦 prompt 版本 | 備註 |
|------|----------------|------|
| **ChatGPT / GPT-4o image** | A 中文 prompt | 中文 prompt 處理 OK；長 prompt 可接受 |
| **Gemini 2.5 / Imagen** | A 中文 prompt | 中文 + 英文 keyword 混合最佳 |
| **Midjourney v6** | B 英文 prompt | 用 ``--ar 16:9 --style raw`` 加在尾巴 |
| **Stable Diffusion XL / Flux** | B 英文 prompt | 加 ``masterpiece, highly detailed`` 反向 prompt 寫 ``text, words`` 避免亂寫字 |

⚠ **生圖模型對中文文字渲染普遍差**。架構名稱、模組名讓圖**有 icon 即可**，文字部分後製用 PowerPoint / Figma 加。

---

## 主 prompt：windMindOM 系統架構 hero 圖（給 PRD / pitch deck cover 用）

### A. 中文 prompt（ChatGPT / Gemini）

> 請生成一張**離岸風場運維平台 windMindOM 系統架構圖**，乾淨的等距 (isometric) 視覺風格，淺色背景配深藍 + 青綠 + 暖橘三色主色調。
>
> 構圖：畫面中央是一個現代化的儀表板螢幕，螢幕內隱約看見風機監控介面（多個圓形儀表 + 趨勢曲線）。儀表板四周以等距方式環繞 5 個發光的方塊圖示，每個圖示代表一個功能模組（請以視覺隱喻呈現，不要寫字）：
>
> 1. **左上**：1-2 台旋轉中的離岸風機（代表 monitoring 即時監控）
> 2. **右上**：金幣 + 上升的折線圖（代表 cost 成本計算）
> 3. **中右**：紙本工單 + 工具扳手（代表 workflow 派工 / 簽核）
> 4. **右下**：PDF 報表 + 印章（代表 reporting 報表）
> 5. **左下**：放大鏡 + 對話氣泡 + 書本（代表 knowledge / RAG 警報手冊查詢）
>
> 螢幕下方左右兩側各站一位 minimal 風格的人物剪影：
> - 左側：戴安全帽的工程師（手持平板）— 代表現場 mobile 使用者
> - 右側：穿西裝的管理者（坐辦公桌前）— 代表管理層 desktop 使用者
>
> 整張圖要傳達的訊息：「**從風機資料 → 成本 / 工單 / 報表 / 知識，給管理者與工程師同時用的離岸風場運維平台**」。
>
> 風格參考：Notion / Linear / Stripe 的官網插畫風，乾淨、現代、科技感但不冷酷，保留些許工業感（風電產業）。
>
> 比例 16:9，適合放在簡報封面與網站 hero section。

### B. 英文 prompt（Midjourney / Stable Diffusion）

```
Isometric architecture diagram of an offshore wind farm operations platform,
clean modern flat design with subtle 3D depth, soft pastel background,
deep navy blue + teal + warm amber color palette,

Center: a sleek floating dashboard screen displaying turbine monitoring
(circular gauges, trend lines, abstract data visualization),

Surrounding the dashboard with 5 glowing module icons (no text labels):
- top-left: 2 stylized offshore wind turbines rotating, ocean horizon
- top-right: gold coin stack with rising line graph
- middle-right: clipboard work order with crossed wrench tools
- bottom-right: PDF document with official stamp seal
- bottom-left: magnifying glass over open manual book with chat bubble

Two minimal human silhouettes flanking the dashboard:
- left: field engineer with hard hat holding a tablet
- right: business manager at desk with monitor

Style: Notion illustrations, Linear app aesthetics, Stripe homepage style,
clean modern tech illustration with industrial wind energy hints,
soft glow effects, white background with subtle blue gradient,

--ar 16:9 --style raw --no text words letters typography
```

---

## 變化版 1：infographic 風格（給社群貼文 / 業務開發 onepager）

### A. 中文 prompt

> 請生成一張**直式 infographic 海報**，主題是「windMindOM — 離岸風場運維 5 大功能」，A4 直式比例。
>
> 上方 1/4 是標題區：寫 "windMindOM 風心智運維平台"（中英文），背景是俯瞰角度的離岸風場（淡藍色海面 + 排列整齊的風機剪影）。
>
> 中段 5 個功能區段垂直排列，每段一個圖示 + 一句說明（請保留中文文字位置但只畫框，文字後製貼）：
>
> 1. 即時監控（風機 icon）
> 2. 成本計算（金幣 + 圖表 icon）
> 3. 派工簽核（工單 + 扳手 icon）
> 4. 自動月報（PDF + 月曆 icon）
> 5. RAG 警報查詢（放大鏡 + 對話氣泡 icon）
>
> 下方 1/5 是 footer：「2026 Q4 第一個運維廠商客戶 PoC」字樣（保留位置，不寫字）+ 公司 logo 位置。
>
> 配色：海洋藍主色 + 沙灘米色背景 + 太陽橘點綴，避免黑色。
> 字體區域請用 placeholder 框，不要實際生成中文字（會亂）。
>
> 比例 9:16（直式 A4）。

### B. 英文 prompt

```
Vertical A4 infographic poster for "windMindOM offshore wind operations platform",

Top hero (25%): aerial view of offshore wind farm at golden hour,
neat rows of turbines on calm blue ocean, atmospheric perspective,

Middle stack (50%): 5 vertically arranged feature sections,
each with a circular icon badge and an empty caption box (placeholder for text):
1. real-time turbine monitoring (turbine icon)
2. cost calculation (gold coin + chart icon)
3. work order dispatch and signoff (clipboard + wrench icon)
4. monthly PDF reporting (document + calendar icon)
5. RAG alarm manual search (magnifying glass + chat bubble icon)

Bottom footer (15%): subtle space for tagline placeholder + logo area,

Color palette: ocean blue primary, beige sand background, sunset orange accents,
avoid pure black, soft gradient,
infographic style, modern flat design with light depth,

--ar 9:16 --style raw --no text words letters readable typography
```

---

## 變化版 2：pitch deck 封面圖（更戲劇化）

### A. 中文 prompt

> 請生成一張**離岸風場黎明航拍**畫面，作為 windMindOM pitch deck 封面：
>
> - 視角：高空 30° 俯視角，地平線在下 1/3
> - 場景：8-12 台離岸風機排列整齊，黎明陽光從右側打進來，風機葉片帶長長的陰影
> - 海面：深藍 + 微浪（非完全平靜），點綴幾條工作船航跡
> - 天空：粉紫 → 金黃漸層日出色調，飄幾片雲
> - 前景：左下角一艘 CTV 工作船正駛向風機，留下白色尾跡
> - 不要文字、不要 watermark、不要人物
>
> 風格：寫實攝影感（電影級調光），但有溫度（不冷酷）。
> 強調「stewardship 守護感」+「規模」+「黎明 = 新一天 = 維運開工」。
>
> 比例 16:9，4K 解析度。

### B. 英文 prompt

```
Cinematic aerial photograph of an offshore wind farm at dawn,
30-degree overhead view, horizon at lower third,

8-12 offshore wind turbines neatly aligned on calm deep blue ocean,
golden hour sunrise light from the right casting long blade shadows on water,
faint wave patterns, a CTV crew transfer vessel in the bottom-left
heading toward the turbines with white wake trail,

Sky: gradient from soft pink to amber to pale blue, few wispy clouds,

Mood: stewardship, scale, dawn-of-a-new-operation-day,
photorealistic style with cinematic color grading,
Sony Alpha look, ARRI Alexa color science,

--ar 16:9 --quality 2 --style raw --no text watermark people figures
```

---

## 進階：用 SVG 生成（給網站 hero 用）

如果要做**可縮放 + 後續可改色**的網站 hero 圖（不是 raster），用 ChatGPT / Claude 直接生 SVG：

> 「請給我一張 SVG 格式的離岸風場運維平台 hero 圖，用簡單幾何形狀（風機 = 三角形 + 線條，海洋 = 漸層長方形，太陽 = 半圓），主色 #0ea5e9（青藍）+ #f59e0b（金黃）+ #1e293b（深藍夜空）。viewBox 1920×1080，inline 直接用 SVG code 給我。」

SVG 比 PNG 小、清晰、可改色 — 適合 React 頁面直接 inline。

---

## 後製建議

生圖模型的成品都需要後製才能上 production：

1. **PowerPoint / Keynote**：生圖匯出 PNG → 進簡報 → 用文字框疊上中文功能名（5 大 module）
2. **Figma / Photopea**：開圖 → 加 logo / 標題 / footer / 標註
3. **網站使用**：raster 圖適合 hero / OG image；功能列表建議用 SVG icons + HTML 文字組合，不要整張用 raster

---

## 我的建議流程

1. 先用 **GPT-4o image / Gemini Imagen** 快速跑「主 prompt」3-5 張看風格哪個對
2. 喜歡的風格鎖定後，開 **Midjourney v6** 用 B 版精緻版重跑
3. 進 **Figma** 把中文文字補上（千萬不要靠 AI 寫中文字）
4. **PowerPoint** 簡報直接用整圖；網站 hero 抽圖內元素重排成 React component

---

## 給劉老師的快速 starter

如果只想快速試一張，**複製下面這段直接貼到 ChatGPT / Gemini**：

```
請生成一張離岸風場運維平台 windMindOM 的等距 (isometric) 系統架構圖，
中央一個浮在空中的儀表板螢幕（顯示風機監控介面），
四周環繞 5 個發光圖示：左上 2 台旋轉風機、右上 金幣+上升曲線、
中右 工單夾板+扳手、右下 PDF+印章、左下 放大鏡+對話氣泡+書本。
螢幕下方左右各站一個剪影人物：左邊戴安全帽工程師持平板、右邊西裝管理者。
配色：深藍 + 青綠 + 暖橘，淺色背景，Notion / Linear / Stripe 的科技插畫風格，
比例 16:9，不要寫字（避免中文亂碼）。
```
