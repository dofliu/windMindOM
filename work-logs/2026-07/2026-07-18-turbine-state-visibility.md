# 2026-07-18 — 狀態可見性：為何不發電 + header 當前風場

> Session 類型：DEC 交付分階段 #3（承 DEC-20260718-01）
> 產出：本 PR（TurbineDetail「為何不發電」chip + App header 風場 strip）
> 對應 issue：WMOM-20260718-04｜回應用戶實測 6 點之 #3「看不到反應」

---

## 做了什麼

1. **`noPowerReason`（TurbineDetail.tsx，exported 純函式）** — 功率≈0（<0.05 MW）時判斷原因，
   優先序：故障跳機 > 緊急停機(turState 7) > 切出風速(>25) > 低於切入(<3) > 停機(1/9) > 待機(2/3)
   > 離線 > 待命。正常發電回 null（不顯示）。
2. **「為何不發電」chip** — TurbineDetail 在故障 banner 下、hero 數字上，功率≈0 時顯示 StatusPill
   （warn=故障/緊急、amber=風況/停機）+ 雙語說明。直接回應「機組沒發電時看不出是 cut-out / 跳機 / 停機」。
3. **header 當前風場 strip（App.tsx）** — 復用既有每 30s 的 `/api/farms` health poll，順便取 active
   farm → 主內容區頂端顯示「🌊 風場名 · N 台 · 資料來源(模擬/Demo/OPC-DA)」。不另開 fetch。
4. **+12 tests** — `noPowerReason` 8 個分支單元測試 + TurbineDetail 4 個 render 測試（正常不顯示 /
   cut-out / 故障 / en）。tsc / 866 前端測試 / vite build 全綠。

## 眉角 / 決策

- **cut-out 優先於「停機」**：wind>25 且 turState=1（auto-shutdown）時，顯示「切出風速」比「停機中」
  更有資訊量（高風才是根因）。故 wind 檢查排在 turState 1/9 之前。
- **故障時 chip 與 FaultBanner 並存**：banner 說「哪個故障」、chip 說「因此不發電」，互補不衝突；
  未跳機的低嚴重度故障仍在發電（power>0.05）→ chip 不顯示。
- **header strip 復用 health poll**：避免為了顯示風場名另開一支 fetch；farm 資料附在既有 /api/farms
  回應裡（`farms` + `active_farm_id`），解析出 active 即可。

## 卡在哪 / 下次怎麼接手

- **本 PR 待審 merge**（draft）。合併後 WMOM-20260718-04 完成。
- **DEC 最後一階段**：**WMOM-20260718-05** #5 turbine 顯示重設計 — 🔵 把「發電量 vs 風速 隨時間」
  拉成主圖、降級現有四色 mini-trend（用戶：「一般看風機就是直接看過去到現在的發電量與風速關係」）。
- **接手指引**：`noPowerReason` 是 exported 純函式、好擴充（未來可接後端 `shutdown_cause`）；
  header strip 在 App.tsx `<main>` 頂端。
