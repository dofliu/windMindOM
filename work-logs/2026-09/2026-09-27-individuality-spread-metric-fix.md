# 2026-09-27 — WMOM-20260505-24：Data quality 3 項 fail 修正

## Claim

`ISSUES.md` open issue `WMOM-20260505-24`（Data quality 3 項 fail 修正：個體差異 spread
+ Region 3 CV 太低），標記 P0/high、estimate 0.5-1 工作天、demo 必修。原文假設是
`power_curve.py`/`turbine_individuality` 的 individuality 參數範圍太誇張需收斂。

之所以挑這個 issue：M6 critical path 剩餘項（PostgreSQL row-lock、HTTPS 部署）皆 🟡
需劉老師先決策；情境比較分析 epic 只剩未拆分 issue 的 A3（需先寫子設計，非本次可做）；
`components/ui/` 剩餘測試覆蓋已多輪評估為低 ROI。`WMOM-20260505-24` 是唯一「有明確
deliverable/acceptance、估時 0.5-1 天、demo 信任度相關」的候選——雖然它跟同批
WMOM-20260505-23~28 一起被上層摘要表籠統標成「🔵 學術深度非商業 must-have」，但
issue 本文自己寫的優先級是 P0/high（demo 被客戶質疑會傷信任），不該被那個群組標籤蓋過。

## Implement

### 先重現現況（`docs/legacy/digiwt_project_notes.md` 未特別相關——這次改的是分析腳本
的統計方法，不是物理模型本身，仍先讀過確認沒有牴觸既有 18 項物理一致性 check）

跑 `python examples/data_quality_analysis.py`（官方 2 小時版本，非 issue 建議的
0.17h 短版——短版連 20-25 m/s 風速區間都湊不到樣本，無法驗證原文點名的 CV 問題）：

- **CV 太低（issue 原文 #1/#2）**：**這次重跑完全沒有觸發**——15-20/20-25 m/s
  CV 分別是 6.1%/2.3%，早就不低於 1% 門檻。合理推測：checked-in 的
  `data_quality_report.txt` 是很久以前（至少 2026-05）產生的舊快照，後續多輪
  physics 強化（dynamic stall、Cp surface 等）已經把這個問題順帶解掉了，只是沒人
  重新產生報告去確認。**本次沒有再對 pitch/power 曲線做任何改動**——不需要動，動了
  反而是無的放矢。
- **個體差異 spread（issue 原文 #3）**：舊報告寫 36.8%，這次重跑得到 **118%**——
  比原文嚴重 3 倍以上。深挖原因（見下）發現**根本不是 individuality 參數的問題**。

### 根本原因（跟原 issue 假設完全不同）

`examples/data_quality_analysis.py` 用的是 `TEST_PLANS["basic_validation"]`：
- `WT001`：t=0 注入 `bearing_wear`，severity_rate=0.002/s，~7 分鐘後 severity 超過
  `auto_trip_severity`（預設 0.85）
- `WT003`：t=3600s 注入 `converter_cooling_fault`，同樣的邏輯

追 `fault.tripped` 這個旗標：一旦 severity 越過門檻就**永久保持 True**（測試計畫沒有
清除步驟），而 `simulator/engine.py:245-246` 的邏輯是**只要 `fault.tripped`，每一步
都呼叫 `model.cmd_emergency_stop()`**——即使機組嘗試 restart，下一步立刻又被打回
emergency。實測 state 分布：WT001 在 7200 步的 2 小時模擬裡，5420 步停在 state 7
（emergency）、只有 399 步在 state 6（發電中）；WT003 同樣大比例卡在
emergency/recovery 循環。

`data_quality_analysis.py` §7「風機個體差異」直接對「發電中」列取每台機組平均功率算
spread——WT001/WT003 的「平均功率」被故障期間占了大部分時間的極低產出嚴重拉低，跟
individuality 完全無關，是**測試方法論的問題**：§5（故障前後信號變化）本來就專門
驗證故障對訊號的影響，§7 的用意應該是驗證「健康機組間」該有的細微差異（製造公差、
感測器偏移），兩者被錯誤地混在同一個指標裡。

驗證：把 WT001/WT003（本次測試計畫中曾被注入故障者）整台排除，只在 WT002/WT004/
WT005（真正全程健康）之間比較——spread 落到 **13.6%**，遠低於 30% 門檻，且**完全
沒有改動任何 individuality 參數**。這證明原 issue 的假設（individuality 範圍太誇張）
是誤診：問題出在分析腳本的機組篩選邏輯，不是物理模型。

### 修法

`modules/monitoring/examples/data_quality_analysis.py`：
- 新增純函式 `compute_healthy_individuality_spread(producing)`：排除本次測試計畫中
  「曾經」（不只是「當下」）被標記 `has_fault=True` 的機組整台，只在剩餘健康機組間
  計算 spread；健康機組 < 2 台或缺必要欄位時回傳 `None`（而非誤導性地算出單台
  「差異 0%」）。
- §7 報告文字調整：同時保留「全部機組（含故障）」的原始統計（資訊性，不做 pass/fail
  判定）+ 新增「健康機組（n=X）」的 spread 判定，兩者都印出來，不隱藏故障對原始數字
  的影響、只是不讓它污染 individuality 這個特定指標。

### 附帶發現並一併修正：`§4 載荷 (Fatigue/DEL)` 整節悄悄變空

重新產生報告過程中發現 `§4`/`§5`/`§6`/`§8` 引用的 `WFAT_TwrBsMy`/`WFAT_TwrBsMx`/
`WFAT_BldRtMy`/`WFAT_BldRtMx` 這幾個 tag **在目前的 schema 裡已經不存在**（`fatigue_
model.py` 目前實際輸出的是 `WLOD_TwrFaMom`/`WLOD_TwrSsMom`/`WLOD_BldFlapMom`/
`WLOD_BldEdgeMom`）。因為對應的檢查都是 `if tag in df.columns` 這種 guard，tag 消失
時**靜默跳過**，不會報錯也不會被列成待改善項目——上次跑報告後這個重新命名沒人發現，
`§4` 整節在目前程式碼下直接印出空白、`§5`/`§8` 對應項目也悄悄消失，卻沒有任何警訊。

雖然不在原 issue 範圍內，但既然本次就是在重跑並要 commit 這份報告，放著一節整個
安靜消失的品質檢查不管，等於明知報告失真還簽字放行，違反「誠實回報」原則——已一併
把全部 4 個 tag 名稱改成對應的 `WLOD_*`（範圍/欄位語意逐一核對後對應：`TwrBsMy`→
`TwrFaMom` 塔基前後向彎矩、`TwrBsMx`→`TwrSsMom` 塔基左右向彎矩、`BldRtMy`→
`BldFlapMom` 葉片揮舞彎矩、`BldRtMx`→`BldEdgeMom` 葉片擺振彎矩），`§4`/`§5`/`§6`/
`§8` 對應檢查全部恢復運作。

### 重新產生並 commit `data_quality_report.txt`

依 issue acceptance 規定「同步更新 data_quality_report.txt（commit 進 repo）」，用
官方 `python examples/data_quality_analysis.py`（2 小時版本，跟原報告的產生方式一致）
重新產生，結果：**20/20 全數 pass，0 項待改善**（原報告 18 pass/3 fail；本次除了
§7 spread 修正 + §4 復活的 4 項 check，實際「原本就正確、只是被遮住」的項目也回來
了）。

**刻意不 commit** 同批產生的 `simulated_scada_2h.csv`（36000 列原始資料，27MB）——
`generate_data()` 的 `timestamp` 欄位灌的是 `datetime.now()`，每次重新產生整份 CSV
36001 行 diff 全部不同（純粹因為起始時間戳不同，不代表資料內容真的變了），committing
只會讓 repo history 無謂膨脹，且 acceptance 只要求更新 `.txt` 報告，未要求 CSV 同步。

## Verify

**Mutation-verified**（改回舊邏輯 → 確認新測會 fail → 已還原，非 `git checkout`，
用 scratchpad 備份 diff 還原確認內容一致）：
把 `compute_healthy_individuality_spread` 內的 `ever_faulted = set(...)` 改成
`ever_faulted = set()`（停用排除邏輯），4 個新測試中 2 個如預期 fail
（`test_excludes_turbines_ever_faulted_during_run`、
`test_returns_none_when_fewer_than_two_healthy_turbines`），另 2 個（缺欄位 /
全健康）維持 pass（符合預期，這兩個測試本來就不依賴排除邏輯）——確認測試真的鎖住了
這次的修復，不是同義反覆。

新增 `modules/monitoring/tests/test_data_quality_individuality_spread.py`（4 測，
純函式測試、不需要跑完整 simulator，快，見上方 mutation 結果）。

- backend 全套：`pytest modules/workflow/tests/ modules/cost/tests/
  modules/reporting/tests/ modules/knowledge/tests/ modules/monitoring/tests/
  modules/auth/tests/ tests/` → 1274→**1278 passed**（+4，7 skipped, 1 xfailed，
  零 regression）
- frontend：本次未動任何前端檔案，`npx tsc --noEmit` + `npx vitest run` + `npx vite
  build` 仍需跑一次確認零 regression（見下方，執行中/待補）

## Review

（`code-reviewer` subagent 待跑，見下方或下次更新本檔）

## Wrap-up

- `data_quality_analysis.py` 的改動範圍：只動分析腳本的統計方法（機組篩選邏輯）+
  復活已死掉的 tag 名稱引用，**沒有改動任何物理模型參數**（`turbine_physics.py`/
  `power_curve.py`/`fatigue_model.py` 皆未觸碰）。
- **誠實揭露：本次未修復的相關發現**——`fault.tripped` 恆真後每步呼叫
  `cmd_emergency_stop()` 造成機組在 emergency/recovery 間反覆循環、產電時間暴跌，
  這本身可能是值得另開 issue 檢視的行為（真實現場的「重大故障後應該卡在 emergency
  直到人工重置」邏輯是否應該讓 restart 嘗試完全停止、而不是每步被打回、導致 SCADA
  歷史資料在很長時間內混雜大量無意義的 emergency⇄recovery 抖動）——這次判斷這是
  獨立於本 issue 範圍的行為問題（fault engine 設計，不是 data quality 分析方法），
  未展開處理，留給劉老師評估是否要開新 issue。
- **原 issue 的兩個 CV 太低項目最終判定「已被後續 physics 工作間接解決、無需改動」**
  ——這代表 `WMOM-20260505-24` 過去可能一直「看起來還沒做」，實際上部分子項早就
  自然解決了，只是沒人重新產生報告去確認、也沒人回頭把 issue 更新掉。
- `WMOM-20260505-23~28` 群組被上層摘要表籠統標成「學術深度非商業 must-have」——
  這個標籤對 -24 是誤導（-24 本文明寫 P0/demo 信任），建議之後再挑這批 issue 時
  逐一看本文的 Priority 欄位，不要只看群組標籤。

## Handoff

- ISSUES.md：`WMOM-20260505-24` → done（見下方統計表更新）
- STATUS.yaml / TODO.md：待補（本檔案完成後同步）
- 下個 session 可評估：是否要為上述「fault.tripped 恆真後 emergency 抖動」開新
  issue（需先問劉老師：現場真實 SCADA 遇到重大故障鎖死後，restart 嘗試應該完全
  停止還是持續嘗試——這是行為設計決策，不是純技術問題）。
