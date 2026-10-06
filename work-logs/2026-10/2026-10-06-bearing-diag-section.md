# 2026-10-06 — WMOM-20260505-25-c：軸承 / 齒輪診斷區塊

## Preflight
- main @ da4e5d5，無 open PR。backend 1305 passed / 7 skipped / 1 xfailed；frontend tsc 0 / vitest 1497 / build OK。
- 後端測試用 `/usr/bin/python3 -m pytest`（`python` 為 3.11 無 pytest）。

## 實作
- `TurbineDetail.tsx` vibration tab 加第三區塊：BPFO/BPFI 頻率+振幅、GMF、邊帶 1/2、邊帶能量比。零後端改動，缺值「—」。
- 測試 +2（vitest 1497→1499）；mutation（BPFO 讀 BPFI tag）fail 確認後還原。

## 沒有自動化保護 / 限制
- 純 DOM 文字斷言；版面未經瀏覽器驗證。
- 後端無這些項目的警報等級 → 無 badge；軸承幾何來源說明未做。

## 下次接手
- `WMOM-20260505-25` 剩 RUL 觸發時間軸（可選）。
