# 2026-10-06 — WMOM-20260505-25-b：振動頻譜 tab

## Preflight
- main @ a5963a9，無 open PR。backend 1305 passed / 7 skipped / 1 xfailed、frontend tsc 0 / vitest 1492（= baseline）。
- 環境注意：`pip` 裝進 python3.13（`/usr/bin/python3`），`python` 是 3.11 無 pytest → 後端測試用 `/usr/bin/python3 -m pytest`。

## 實作
- `TurbineDetail.tsx` 新增 `vibration` tab：5 頻帶 RMS X/Y + 警報 badge、1P 門檻、crest/kurtosis/overall 警報（`vibAlarmInfo` clamp 0-2）。零後端改動。
- 測試 +5；mutation（移除 clamp、alarm tag 對調）皆 fail。

## Review（code-reviewer）
- must-fix 0。should-fix 已修：缺值顯示 muted「無資料」而非「正常」（+mutation 驗證）、加註 badge 與數值不完全對應（門檻縮放/遲滯）、補缺值測試。
- 未處理（記錄）：直驅機型 gear 列恆為 0（前端無 drivetrain 欄位可判斷）；轉速 <2 rpm 時 crest/kurtosis 實為「未評估」卻顯示正常；3P/HF/Bb 數值斷言僅部分涵蓋。

## 沒有自動化保護 / 限制
- 純 DOM 文字斷言；版面與視覺未經瀏覽器驗證。
- 未做 HealthBar/zone curve/trend（資料未對外）；Part C 與 RUL 時間軸待做。

## 下次接手
- `WMOM-20260505-25` Part C：`BearingDiagPanel`（`WVIB_Bpfo/BpfiFreq/Amp`、`GmfFreq`、`Sideband1/2Amp`、`SidebandRatio`），比照本次就地擴充。
