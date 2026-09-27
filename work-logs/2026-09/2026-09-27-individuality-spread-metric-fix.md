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
WT005（真正全程健康）之間比較——spread 落到 **~13-15% 區間**（每次重跑數字略有
浮動，見下方「非決定性根因」發現），遠低於 30% 門檻，且**完全沒有改動任何
individuality 參數**。這證明原 issue 的假設（individuality 範圍太誇張）是誤診：
問題出在分析腳本的機組篩選邏輯，不是物理模型。

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

新增 `modules/monitoring/tests/test_data_quality_individuality_spread.py`（初版 4
測，純函式測試、不需要跑完整 simulator，快，見上方 mutation 結果；review 後補
2 測見下方，共 6 測）。

- backend 全套：`pytest modules/workflow/tests/ modules/cost/tests/
  modules/reporting/tests/ modules/knowledge/tests/ modules/monitoring/tests/
  modules/auth/tests/ tests/` → 1274→**1278 passed**（+4，7 skipped, 1 xfailed，
  零 regression）
- frontend：本次未動任何前端檔案，`npx tsc --noEmit` + `npx vitest run` + `npx vite
  build` → 1477 passed（70 files）不變、tsc 0、build OK（零 regression，確認未動
  前端也沒有意外副作用）

## Review

`code-reviewer` subagent review（獨立讀過 `fatigue_model.py`/`fault_engine.py`/
`engine.py`/`turbine_physics.py` 逐項核對本次論述）：**Approve，0 must-fix，5
should-fix 全數採納，3 nice-to-have**：
1. 🟡 `compute_healthy_individuality_spread` 對「健康機組平均功率算出 NaN」（例如
   感測器全程掉線）沒有防呆——跟本次修復想解決的「污染樣本混入指標」是同一種問題
   （只是污染源從「故障」換成「NaN」），且若剩下只有 1 台有效機組會誤算成假的
   「差異 0%」而非誠實回傳 `None`。修法：`groupby().mean()` 後加 `.dropna()`。新增
   `test_excludes_healthy_turbine_with_all_nan_power` 鎖住，mutation-verified（拿掉
   `dropna()` → 新測如預期 fail → 已還原確認）。
2. 🟡 報告只印健康機組數量（`n=3`），未列出哪些機組被排除，缺乏可追溯性——report
   文字補印健康機組 ID 清單 + 已排除機組 ID 清單。
3. 🟡 回傳型別用裸 `dict` 混合 4 個 float + 1 個 `List[str]`，呼叫端 `healthy['min_kw']`
   打錯 key 不會被型別檢查抓到——改成 `@dataclass HealthyIndividualitySpread`（欄位含
   新增的 `excluded_turbine_ids`），呼叫端與測試改用屬性存取。
4. 🟡 work-log/ISSUES.md 寫「spread 落到 13.6%」，但最終 commit 的報告顯示 13.5%——
   深入追查後發現這不是筆誤，是真正的執行間非決定性（見下方發現①），已把敘事文字
   改成誠實的區間描述，不再宣稱單一精確數字。
5. 🟡 work-log 原寫「STATUS.yaml / TODO.md：待補」——reviewer 讀到的是我在完成
   ISSUES.md 但還沒做 STATUS.yaml/TODO.md 時的中間狀態；已在 review 期間完成兩者
   同步，本節文字已更新反映實際狀態（非隱瞞，純粹是 review 啟動時機早於我的
   wrap-up 順序）。
6. 🟢 排除「整台」而非「僅故障當下那幾列」的設計判斷（避免用不對等時間窗比較）
   獲 reviewer 獨立確認合理，維持不變。
7. 🟢 補 `test_returns_none_when_producing_df_is_empty` 邊界測試（原本邏輯已正確
   處理，只是沒有顯式測試鎖住）。
8. 🟢 `fetch_scada_data.py` 有同款 stale `WFAT_*` tag 殘留（該腳本走 live server
   API，非本 issue 驗收範圍）——登記為新 follow-up，見下方。

should-fix 修復後測試由 4 個增至 **6 個**，全數 mutation-verified；重新產生
`data_quality_report.txt`（新增健康/已排除機組 ID 清單），20/20 pass 不變。backend
全套重跑：1274→**1280 passed**（+6，7 skipped, 1 xfailed，零 regression）；
frontend 未動、1477 passed（70 files）不變、tsc 0、build OK。

## Wrap-up

- `data_quality_analysis.py` 的改動範圍：只動分析腳本的統計方法（機組篩選邏輯）+
  復活已死掉的 tag 名稱引用，**沒有改動任何物理模型參數**（`turbine_physics.py`/
  `power_curve.py`/`fatigue_model.py` 皆未觸碰）。
- **誠實揭露：本次未修復的相關發現**：
  1. `fault.tripped` 恆真後每步呼叫 `cmd_emergency_stop()` 造成機組在
     emergency/recovery 間反覆循環、產電時間暴跌，這本身可能是值得另開 issue 檢視
     的行為（真實現場的「重大故障後應該卡在 emergency 直到人工重置」邏輯是否應該
     讓 restart 嘗試完全停止、而不是每步被打回、導致 SCADA 歷史資料在很長時間內
     混雜大量無意義的 emergency⇄recovery 抖動）——這次判斷這是獨立於本 issue 範圍
     的行為問題（fault engine 設計，不是 data quality 分析方法），未展開處理，留給
     劉老師評估是否要開新 issue。
  2. **新發現（spread 數字非決定性根因）**：同一套測試計畫重跑多次，spread 數字
     每次略有不同（12.5%/13.5%/13.6%/14.8% 皆出現過，結論不變，皆穩定 <30%）。追查
     發現 `simulator/grid_model.py`（grid frequency/voltage 噪聲）與
     `simulator/physics/yaw_model.py`（`brake_pressure` 噪聲）直接呼叫全域未種子化
     的 `np.random.normal(...)`——跟其餘整個 codebase 一律用每台機組各自種子化的
     `self._rng`（`np.random.RandomState(seed)`）不一致，導致同樣的
     `WindFarmSimulator(seed=i)` 重跑兩次結果不同。已登記 **WMOM-20260927-01** 追蹤
     （非本 issue 範圍，未修）。
  3. `fetch_scada_data.py` 219/305 行殘留已死的 `WFAT_TwrBsMy`/`WFAT_BldRtMy`
     引用（code-reviewer nice-to-have，該腳本走 live server API，非
     `generate_data()` 路徑，不影響本次驗收）。已登記 **WMOM-20260927-02** 追蹤
     （非本 issue 範圍，未修）。
- **原 issue 的兩個 CV 太低項目最終判定「已被後續 physics 工作間接解決、無需改動」**
  ——這代表 `WMOM-20260505-24` 過去可能一直「看起來還沒做」，實際上部分子項早就
  自然解決了，只是沒人重新產生報告去確認、也沒人回頭把 issue 更新掉。
- `WMOM-20260505-23~28` 群組被上層摘要表籠統標成「學術深度非商業 must-have」——
  這個標籤對 -24 是誤導（-24 本文明寫 P0/demo 信任），建議之後再挑這批 issue 時
  逐一看本文的 Priority 欄位，不要只看群組標籤。

## Handoff

- ISSUES.md：`WMOM-20260505-24` → done；新增 `WMOM-20260927-01`/`WMOM-20260927-02`
  兩個小 follow-up（皆 open，低優先，見上方 Wrap-up）
- STATUS.yaml：`issue_stats`（open 8→9、done 137→138）+ `last_updated` 已同步
- TODO.md：已同步本次完成摘要 + 下個 session 建議
- 下個 session 可評估：①是否要為「fault.tripped 恆真後 emergency 抖動」開新 issue
  （需先問劉老師：現場真實 SCADA 遇到重大故障鎖死後，restart 嘗試應該完全停止還是
  持續嘗試——這是行為設計決策，不是純技術問題）；②`WMOM-20260927-01`/`-02` 皆是
  15-30 分鐘可完工的小修，可作為下次「順手清一個小技術債」的候選。
