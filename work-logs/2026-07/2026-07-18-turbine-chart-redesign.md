# 2026-07-18 — 顯示重設計：發電量 vs 風速 拉為主圖

> Session 類型：DEC 交付分階段 #5（**收尾** DEC-20260718-01 全 5 階段）
> 產出：本 PR（TurbineDetail 左欄重排）
> 對應 issue：WMOM-20260718-05｜回應用戶實測 6 點之 #5

---

## 做了什麼

用戶：「進機組顯示四個資料的狀態趨勢，實際意義不大。感覺不如直接把下面的拿到上面來。
一般看風機就是直接看過去到現在的發電量與風速的關係圖最直接。」

**關鍵發現**：既有 `TrendChartPanel` 預設 preset 就是 `'power'`＝`WTUR_TotPwrAt + WMET_WSpeedNac`
（功率與風速），讀真實 `/api/turbines/{id}/trend`、畫真實時間序列——**用戶要的「發電量 vs 風速
關係圖」本來就存在，只是被放在左欄最下面**。四色 mini-trend（LiveTrendsCard）反而在最上，且
其中 3/4 通道是合成 sine 假資料（難怪「實際意義不大」）。

所以 #5 主要是**重排**：
1. `TrendChartPanel` 從左欄最下 → **拉到最上當主圖**，重下標題「發電量 vs 風速 · 過去到現在」
   + 副標「切換下方預設可看溫度/振動/其他 SCADA 通道」。
2. 四色 mini-trend（`LiveTrendsCard`）→ **降級到左欄最下**（發電量/風速已在主圖 + hero 4 數字呈現）。
3. +3 render tests（DOM 順序：主圖在四通道之前 / 主圖掛載 TrendChartPanel / en 標題）。

tsc / 883 前端測試 / vite build 全綠。

## 眉角 / 決策

- **重排而非重寫**：用戶說「把下面的拿到上面來」——最直接的實作就是把既有真實圖表提到頂端，
  不必新造一個 power-vs-wind 圖（TrendChartPanel 預設即是）。改動小、風險低、完全對得上訴求。
- **四色降級而非刪除**：用戶說「實際意義不大」但沒明說刪除。降級到最下方（可逆、不動 import/測試），
  仍達成「主圖置頂」的核心。**若要整個移除四色（含其合成假資料），是一行 follow-up**——留給用戶決定。
- TrendChartPanel 的 preset 鈕保留：主視圖預設 Power & Wind，power-user 可切其他通道。

## 卡在哪 / 下次怎麼接手

- **本 PR 待審 merge**。合併後 **DEC-20260718-01（模擬雙軌）全 5 階段收尾**：
  #1 風速 bug（#123）→ DEC（#124）→ scenario 後端（#125）+ 前端（#126）+ review fix（#127）→
  #3 狀態可見性（#128 + #129）→ #5 顯示重設計（本 PR）。
- **Scenario 線之後**：回到 M5 收尾（客戶手冊擴充 + 一年警報 csv）+ WMOM-20260716-06（footprint
  CPU-torch pin）+ M6 客戶接觸；或用戶指定新方向。
- **可選 follow-up**：若用戶要移除四色 mini-trend（合成假資料）→ 刪 `LiveTrendsCard` usage + 定義
  + 清 `MiniSparkline` import（若無其他用途）。

---

## Follow-up：雙 Y 軸（WMOM-20260718-06，同日）

主圖上線後用戶立刻反映：功率（數百 kW）與風速（個位數 m/s）**同一個 Y 軸**，風速被壓到貼底
完全看不見。修法＝雙 Y 軸：

- 抽 `frontend/utils/chartAxes.ts` 的 `rightAxisTags(tags, data, ratio=10)` 純函式：算每個 tag 的
  maxAbs，量級 < 全體最大 /10（差一個數量級）的移右軸，其餘左軸；量級相近（多條溫度）則右軸空＝單軸。
- `TrendChartPanel` 渲染左軸 +（有右軸 tag 時）右軸；每條 Line 依判定給 `yAxisId`；單一線的軸用
  該線顏色標示（一眼看出哪軸配哪線）。
- +8 unit tests（功率vs風速分軸 / 溫度單軸 / 最大 tag 恆左 / 無資料 / 全0 / null / ratio 可調 / 負值）。
- tsc / 891 前端測試 / build 全綠。既有 TrendChartPanel.test（recharts 全 stub）不受影響。
