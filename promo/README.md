# promo/ — windMindOM 對外介紹影片素材

這裡放**對外 demo 用的介紹影片**與它的全部原始素材。不是產品程式碼，不進 CI，
不影響 `modules/` 邊界。用 [`intro-video`](../CLAUDE.md) 技能製作。

| 檔案 | 是什麼 |
|---|---|
| `windMindOM-intro-3min.mp4` | **成片** — 180.0s / 1920×1080 / 30fps / 安靜合成氛圍配樂（-23 LUFS） |
| `gen_scenes.py` | **唯一該編輯的檔案** — 18 景文案 + 專屬 CSS + storyboard 定義 |
| `scene01_open.html` … `scene18_cta.html` | 由 `gen_scenes.py` 產生的 standalone 場景，**不要手改** |
| `storyboard.json` | fps / 尺寸 / xfade / 每景秒數與轉場 |
| `work/` | 逐景 MP4 + `check_*.png` 抽查格（未進 git） |

---

## 分鏡（18 景 / 5 章 / 180.0s）

色調每 3-4 景換一次當「換章」訊號。全片唯一一次 `fadeblack` 用在進戲劇景前那一刀。

| # | 場景 | 內容 | 秒 | 轉場 | 色調 |
|---|---|---|---|---|---|
| 1 | `scene01_open` | windMindOM / 風心智運維平台 + 定位句 | 10 | fade | 深海 |
| 2 | `scene02_problem` | 運維資料散在 SCADA / Excel / 成本表 / PDF 手冊 | 10 | smoothleft | 深海 |
| 3 | `scene03_platform` | 一個平台，六個模組（六宮格 + 完成狀態） | 11 | circleopen | 深海 |
| 4 | `scene04_monitoring` | 看得見的不只是數字 — SCADA × 模擬器同源 | 10 | fade | 青 |
| 5 | `scene05_physics` | 104 tags / 11 故障情境 + 尾流面板 + RUL count-up | 11 | smoothup | 青 |
| 6 | `scene06_cost` | 這場維修值得嗎 — ECN K13 移植 | 10 | fade | 金 |
| 7 | `scene07_cost_mock` | LCOE + 20 年 Monte Carlo 柱狀圖 | 11 | circleopen | 金 |
| 8 | `scene08_workflow` | 從發現故障到簽核完工，一條龍 | 10 | fade | 紫 |
| 9 | `scene09_statemachine` | 7-state 工單狀態機逐段點亮 + 簽核 chain | 11 | smoothleft | 紫 |
| 10 | `scene10_reporting` | 月報 PDF + KPI / 年度預算 | 10 | fade | 藍紫 |
| 11 | `scene11_knowledge` | 警報碼 → 手冊段落（RAG，531 chunks） | 11 | smoothup | 綠 |
| 12 | `scene12_auth` | JWT + RBAC 四角色與 level | 10 | **fadeblack** | 藍 |
| 13 | `scene13_drama` | **戲劇景：沒有實場也能完整 demo（Simulator-first）** | 12 | fade | 高對比青 |
| 14 | `scene14_scenario` | 情境＝凍結資料集，faulted vs healthy 比較 | 11 | smoothleft | 青 |
| 15 | `scene15_numbers` | 6 modules / 998+957 tests / 104 tags / 40+ endpoints | 11 | circleopen | 青 |
| 16 | `scene16_persona` | 一套系統兩種現場（管理層 vs 現場工程師） | 10 | fade | 青 |
| 17 | `scene17_roadmap` | M1→M6 甘特 + 2026 Q4 第一筆合約 | 10.2 | fade | 深海 |
| 18 | `scene18_cta` | 專案名回歸 + 三連特點 + repo 連結 | 11 | — | 深海 |

成片長度 = 各景秒數總和 − (景數−1) × xfade = 190.2 − 10.2 = **180.0s**。

---

## 怎麼改

技能腳本路徑（下面用 `$S` 代表）：

```bash
S=~/.claude/skills/synced/*/intro-video          # 或技能實際安裝位置
export CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome   # 容器環境
```

### 改某一景的文案

1. 編輯 `gen_scenes.py` 裡那一景的 `content=`（**不要直接改 `.html`，會被蓋掉**）
2. `python promo/gen_scenes.py`
3. 只重渲該景 → 看抽查格 → 重組片：

```bash
python $S/scripts/render_scenes.py promo/storyboard.json --workdir promo/work --only scene07_cost_mock
# 檢查 promo/work/check_scene07_cost_mock.png 的排版
python $S/scripts/assemble_video.py promo/storyboard.json --workdir promo/work \
       --out promo/windMindOM-intro-3min.mp4 --bed
```

### 換配樂 / 調響度（秒級，不用重渲）

```bash
# 換成真實音樂（推薦；短於片長會自動 1.5s 交叉淡接循環，尾 3s 淡出）
python $S/scripts/assemble_video.py promo/storyboard.json --workdir promo/work \
       --out promo/windMindOM-intro-3min.mp4 --music bgm.mp3 --loudness -18

# 交無聲版（要自己後製配樂 / 加旁白時用這個）
python $S/scripts/assemble_video.py promo/storyboard.json --workdir promo/work \
       --out promo/windMindOM-intro-silent.mp4
```

### 剪一支 30 秒短版

**場景不用重寫** —— 複製 `storyboard.json` 成 `storyboard_30s.json`，只留
`scene01 / scene03 / scene13 / scene15 / scene18`（各 6-7s），重跑 assemble 即可。

### 嵌入真實 UI 截圖（下一步最有價值的升級）

目前全片是 CSS mock（repo 內沒有自家 UI 截圖）。有截圖後：

```bash
python $S/scripts/prep_assets.py --out promo/assets shot_monitor.png shot_workorder.png ...
```

再把對應景的 mock 換成模板的 `.shot` 版位（`<img src="assets/asset_01.png">`，
相對路徑；場景以 `file://` 載入，外連 URL 會變白框）。

---

## 環境需求

- `pip install playwright`（瀏覽器用系統既有的，**不要**跑 `playwright install`）
- `ffmpeg` / `ffprobe` 在 PATH（容器：`apt-get update && apt-get install -y ffmpeg`）
- 繁中字型 `Noto Sans CJK TC`（容器：`apt-get install -y fonts-noto-cjk`）—— 缺了中文字會變豆腐框

製作紀錄與後續規劃見 [`work-logs/2026-09/2026-09-01-intro-video-3min.md`](../work-logs/2026-09/2026-09-01-intro-video-3min.md)。
