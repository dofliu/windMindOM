# 2026-09-01 — 用 intro-video 技能做出 3 分鐘專案介紹影片（含背景配樂）

> Session 類型：其他（對外素材製作）
> Session 長度：中
> 主導：Claude（intro-video 技能）+ 劉老師需求
> 結果：`promo/` 下 18 景 HTML 動畫 + storyboard + 180.0s 1080p30 MP4（安靜合成氛圍配樂）全數落地，可單景重渲、可換配樂

---

## 1. Session 目標

用 `intro-video` 技能把 windMindOM repo 做成一支 **3 分鐘**介紹影片，**加背景配樂**。
用途：對外 demo / 客戶接觸（M6 WMOM-20260503-05）/ partner 對接時的第一份素材。

---

## 2. 實際完成

### 2.1 主要工作

1. **來源盤點**（intro-video §A repo 路線）——從 `README.md` / `STATUS.yaml` / `CLAUDE.md` /
   `modules/workflow/domain/work_order.py` / `modules/auth/roles.py` 萃出：
   - 定位一句話：離岸風場運維廠商的一站式作業平台
   - 差異化主張（全片戲劇景）：**Simulator-first —— 沒有實場也能完整 demo**
   - 可用數字：6 modules / 998 backend tests / 957 frontend tests / 104 SCADA tags /
     11 fault scenarios / 40+ REST-WS endpoints / 531 RAG chunks / 7-state 工單狀態機 / 4 RBAC 角色
   - CTA：`github.com/dofliu/windMindOM`
2. **分鏡**：18 景 5 章（開場 → 六模組功能章 → 戲劇景 → 成果章 → CTA），
   每 3-4 景換一次色調當「換章」訊號（深海／青／金／紫／藍紫／綠／藍／高對比青）。
   全片唯一一次 `fadeblack` 用在進戲劇景前那一刀。
3. **場景實作**：寫 `promo/gen_scenes.py`（單一 source of truth，含 18 景文案 + 專屬 CSS +
   storyboard 定義），一次產出 18 支 standalone HTML + `storyboard.json`。
   自訂共用元件：`.mod` 模組卡、`.bar` 進度條、`.num`/`.cu` count-up、狀態機 pipeline、
   Gaussian wake 錐形 mock、20 年成本柱狀圖、faulted vs healthy SVG trace、M1-M6 甘特列。
4. **渲染 + 逐張抽查**：18 景各渲一支 MP4 + 85% 時間點 `check_*.png`，逐張檢查排版。
5. **出片**：xfade 0.6s 串接 + `--bed` 安靜合成氛圍（-23 LUFS），成片 **180.0s / 1080p30**。

### 2.2 卡住或延後的事

- **容器缺 ffmpeg 與 playwright**：`pip install playwright` +
  `apt-get update && apt-get install -y ffmpeg` 補上；Chromium 用 `/opt/pw-browsers` 既有的，
  以 `CHROMIUM_PATH` 指定執行檔（**不要** `playwright install`）。
- **容器缺繁中字型**：原本只有 WenQuanYi Zen Hei，補 `fonts-noto-cjk` 才拿到
  `Noto Sans CJK TC` / `Noto Sans Mono CJK TC`（模板字型堆疊的第一順位）。
- **repo 內沒有自家 UI 截圖**（只有 `shared/plc_clients/bachmann/openopc2-*/doc/assets/` 的
  第三方套件文件圖，版權與相關性都不宜入片）→ 全片走 CSS mock，反而更乾淨統一。
  **後續要拍真實 UI 截圖再嵌入，是這支片最大的升級空間**（見 §7）。
- **配樂用合成氛圍而非真實音樂**：使用者未附音檔。技能明載「真實音樂 >> 合成」，
  待取得免版稅音樂檔後重跑 assemble（秒級）即可換。

### 2.3 重大決策（如有）

無架構級決策，不寫 decision_log。`promo/` 定位為**對外素材目錄**（非產品程式碼），
不進 CI、不影響 module 邊界。

---

## 3. 產出清單

### 新增檔案

- `promo/gen_scenes.py` — 18 景文案 + CSS + storyboard 產生器（改文案的唯一入口）
- `promo/scene01_open.html` … `promo/scene18_cta.html` — 18 支 standalone 場景（由上者產生）
- `promo/storyboard.json` — fps/尺寸/xfade/每景秒數與轉場
- `promo/README.md` — 怎麼改文案、怎麼單景重渲、怎麼換配樂與響度
- `promo/windMindOM-intro-3min.mp4` — 成片（180.0s / 1920×1080 / 30fps）

### 修改檔案

- `ISSUES.md`（新增 WMOM-20260901-01，done）
- `STATUS.yaml`（記錄本 session）

### 動了狀態的 issue

- WMOM-20260901-01: open → done

### 寫進 decision_log 的決策

- 無

---

## 4. 下次怎麼接手

1. **最該做的事**：跑起 `python run.py` + `npm run dev`，抓 6-8 張真實 UI 截圖
   （監控儀表板 / 工單 lifecycle / 簽核 chain / 成本試算 / 月報預覽 / RAG 查詢 / mobile 派工），
   過 `prep_assets.py` 後用 `.shot` 版位替換對應景的 mock —— 說服力差很多。
2. **第二優先**：找一段免版稅音樂（YouTube 音樂庫等）→ `--music bgm.mp3 --loudness -18` 重跑
   assemble，取代目前的合成氛圍。
3. **選配**：從同一組場景剪一支 **30 秒短版**（挑 scene01 / 03 / 13 / 15 / 18 另寫一份
   storyboard 即可，場景不用重寫）給社群與 email 用。
4. **阻擋項**：無。

---

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 來源盤點 + 分鏡設計 | 25% |
| 寫場景 HTML / CSS 動畫 | 40% |
| 渲染 + 抽查格排版修正 | 25% |
| 環境修補（ffmpeg / 字型 / chromium） | 10% |

---

## 6. 學到的事

- **repo 類來源最省力**：README 第一段就是定位句，`STATUS.yaml` 的數字直接當「數據景」，
  domain enum（`WorkOrderStatus` 7 state、`Role` 4 角色）直接當畫面骨架 —— 不用自己編。
- **把 18 景寫成一支 generator 而不是 18 支手寫 HTML** 是這次最值得留下的做法：
  改一句文案只要改 `gen_scenes.py` 再單景重渲，不必在 18 個檔案裡找 CSS。
- **色調換章**比加轉場特效更能撐住 3 分鐘的注意力；戲劇景與 fadeblack 全片各只用一次，
  用多了就廉價（技能明載，實測確實如此）。
- 容器環境的 ffmpeg / 字型不能假設存在，`apt-get update` 要先跑（不跑會 404）。

---

## 7. Open questions（park）

- 要不要錄旁白（中文）？目前是純字卡 + 氛圍，加旁白會大幅提升 sales 說服力但需人聲錄製。
- 要不要出英文版？CTA 與功能景文案換掉即可，`gen_scenes.py` 加一個 `LANG` 分支就能雙語共用場景。
- MP4 進 git 是否合適？目前 commit 進 `promo/` 方便隨 repo 分發；若日後檔案變多，
  考慮改放 release asset 或外部儲存。
