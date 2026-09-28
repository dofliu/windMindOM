# 2026-09-28 — WMOM-20260505-25-a：`TurbineDetail.tsx` fatigue tab 新增 RUL 倒數 + 疲勞警報 badge + 累積損傷比例

## Claim

Preflight：`git checkout main && git pull` 遇到本機 `main` 停在 2026-09-01（5555112），
與 `origin/main`（8eab233，2026-09-28 #208）因 squash-merge 歷史重塑而「分岔」
（`git rev-list --left-right --count` 顯示 83/51），非真正衝突——`git reset --hard
origin/main` 同步（本機 main 只作追蹤用，非開發分支）。

GitHub MCP 這次有掛載，`list_pull_requests` 確認無殘留 open PR（不需降級模式）。

逐一核對 `ISSUES.md` 全部 7 open + 2 in_progress issue：已連續 4+ 個 session
（`WMOM-20260928-01~04`）得出「皆需劉老師決策或跨日大工」的結論。本次沒有重複
第 5 次相同的全量核對，改依前一 session（`-04`）work-log 的具體建議——評估能否
比照 `WMOM-20260505-26-a` 的手法，對 `WMOM-20260505-27`/`-28`（保護電驛/單齒
defect）切出無歧義的降低版子項。

查證後判斷 `-27`/`-28` 不適用同款手法：`-26-a` 之所以可行，是因為
`operator_stop`/`tur_state==7` 等**既有真實狀態**只是沒被暴露成獨立 tag；但
`-27`（保護電驛協調）與 `-28`（單齒 defect signature）都需要**全新物理建模**
（IEC 60255 inverse-time curve、GMF modulation pattern），沒有等價的「既有狀態
只是沒曝光」捷徑可用，仍屬需要多 session 的實質新功能開發。

同時也重新確認前幾個 session 引用的「PR C（需先寫 broker 子設計，仍卡）」已經
過時——`WMOM-20260926-02`（PR C 子設計）、`WMOM-20260926-03`（Phase 1 實作）、
`WMOM-20260922-02`（PR D）、`WMOM-20260923-06`（A2 Part 4，情境比較分析 epic
A0-A2 全數完成）皆已 done，DEC-20260720-02 epic 的可立即接手項目已全數清空
（`TODO.md`「可立即接手」段落全部 `[x]`），只剩選配的 A3（`history_events.
session_id` 情境化，範圍模糊、未開 issue）。

於是把注意力轉向重新盤點 `WMOM-20260505-25`（Frontend RUL/alarm 視覺化，估
1.5-2 天）。母 issue 描述假設「需要 3 個新元件 + 新 tab」，但實地查證程式碼
發現這個假設已過時：

- `modules/monitoring/simulator/physics/turbine_physics.py:891-893` 把
  `WLOD_AlmTwr`/`WLOD_AlmBld`/`WLOD_RulHours` 寫進 `scada` dict。
- `modules/monitoring/server/data_broker.py:207`
  `scadaTags=scada if scada else None` 把**完整** `scada` dict 透傳進
  `TurbineReading.scadaTags`（`models.py:142` 早已型別為 `Optional[Dict[str,
  float]]`，註解寫「Raw SCADA dict, for advanced views」）。
- `frontend/types.ts` 的 `TurbineData.scadaTags?: Record<string, number>`
  也早已型別化。

也就是說 RUL/疲勞警報等級**不需要任何後端改動**——資料已經全程流到前端，
只是 `TurbineDetail.tsx` 既有的 `fatigue` tab（`DETAIL_TABS` inline
`case 'fatigue':` 分支，issue 原文引用的
`frontend/components/turbine/LoadFatiguePanel.tsx` 根本不存在，是另一處過時
描述）從未把它畫出來，連同樣已型別化的 `damageTowerFa`/`damageTowerSs`/
`damageBladeFlap`/`damageBladeEdge`（累積損傷比例）也是。這使得「顯示 RUL +
警報 + 累積損傷」是零後端風險、零設計歧義的純前端顯示任務，拆出來當
「Part A」單 session 完工。

## Implement

`frontend/components/TurbineDetail.tsx`：

- 新增純函式 `fatigueAlarmInfo(level)`（0-4 級 → `{en, zh, tone}`，tone 對映
  `ok/info/warn/amber/danger`，語意對齊 `fatigue_model.py::_damage_to_alarm`
  與 `data_broker.py` 的 `alarm_names` dict）與 `formatRul(hours, tr)`（小時數
  換算「年+月」/「月+日」/「日」，`hours < 0` 或缺值回傳 `—`）。
- `case 'fatigue':` 從單一 `SubsystemSection` 改成兩欄 grid（比照 `overview`
  tab 既有寫法）：左欄原 `WLOD Load & Fatigue` 內容不動；右欄新增
  `Cumulative Damage & RUL` section——4 個累積損傷比例（>50%/>80% 走
  warn/alert 顏色，比照既有 DEL 欄位慣例）、塔架/葉片 2 個 `StatusPill`
  警報 badge、RUL 倒數（<1 年 warn、<30 天 alert）。
- 不新增 tab、不新增獨立元件檔——刻意貼合實際程式碼結構（inline case
  分支）而非母 issue 過時假設的「新 tab + 3 個獨立檔案」。
- i18n 沿用既有 `tr()` pattern，中英文皆有。

## Verify

> 本節記錄 code review 前的第一輪驗證數字（1483/6 測）；review 後依 must-fix/
> should-fix 補測 3 個，最終數字是 **1486 passed（9 個新測試）**，見下方
> Review 段落與 Wrap-up 最終統計。

**Frontend 全套（review 前）**：
- `npx tsc --noEmit` → 0 error
- `npx vitest run` → **1483 passed**（70 files，baseline 1477 + 新增 6，
  零 regression）
- `npx vite build` → 成功（僅既有 chunk size 警告，與本次改動無關）

**新增測試（review 前，6 個）**：
1. 無 `scadaTags` → 兩個警報 badge 皆顯示「正常」、RUL 顯示「—」
2. `scadaTags` 帶塔架/葉片警報等級 → 顯示對應中文標籤 + RUL 4000h→「5月 16天」
3. RUL 跨年（40000h）→「4年 6月」（不顯示日）
4. `rulHours = -1`（尚無足夠發電時數估算損傷速率的 sentinel）→ 顯示「—」而非
   負數
5. 累積損傷比例（`damageTowerFa`/`damageBladeFlap`）正確換算成百分比
6. `lang=en` → 警報 badge 與 RUL 標籤走英文（含跨月 RUL 換算）

**寫測試過程踩到的坑**：第一版 `getByText('—')` 斷言誤中既有 `DEL tower FA`/
`DEL blade flap` 兩個 DataRow 缺值時的 fallback（它們原本就是裸 `fmt(...)`
不接單位字串，缺值時渲染出獨立的「—」文字節點，與 RUL 那格同款 DataRow
value span 樣式完全相同）——`getByText` 抓到 3 個相符元素而非預期的 1 個。
改用 `screen.getByText('預估剩餘壽命').closest('div')` 先定位到 RUL 那一列，
再 `within(rulRow).getByText('—')` scope 查詢解決。

**Mutation-verify**：`git stash push -- frontend/components/TurbineDetail.tsx`
暫時把元件本體還原成修正前版本（測試檔案不動），只跑新增的 6 測——
**6 個全部 fail**（`getByText`/`getByRole` 找不到對應內容，符合預期：
警報 badge/RUL/累積損傷 section 在舊版本完全不存在）。`git stash pop` 還原後
重跑全部 99 個 `TurbineDetail.test.tsx` 測試 → 皆綠，確認還原正確無殘留差異。

**Backend**：本次未動任何後端檔案（核心發現正是「不需要」）。開工 preflight
已完整跑過一次確認 baseline：
`pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/
modules/knowledge/tests/ modules/monitoring/tests/ modules/auth/tests/ tests/`
→ **1295 passed, 7 skipped, 1 xfailed**（與 baseline 一致），與本次改動範圍
無關，未重跑。

## Review

`code-reviewer` subagent review（背景執行，約 4 分鐘完成）：**Needs revision，
1 must-fix + 3 should-fix + 1 nice-to-have，全數已修復**：

1. 🔴 **must-fix（已修復）**：`fatigueAlarmInfo(level)` 只檢查
   `level >= 0 && level <= 4` 範圍但未 `round`，`scadaTags` 型別是
   `Record<string, number>`，無法在型別層保證乾淨整數——一個範圍內的**非整數**
   值（如 `2.5`）會通過範圍檢查、直接當陣列索引用在
   `FATIGUE_ALARM_LEVELS[2.5]`，JS 陣列非整數索引取到 `undefined`，後續
   `almTwr.tone` 直接 `TypeError` 炸掉整個 `SubsystemDetailCard` render（不只是
   badge 本身）。reviewer 實測重現：`scadaTags: { WLOD_AlmTwr: 2.5 }` → 整個
   fatigue tab crash。雖然目前後端（`_damage_to_alarm` 回傳值恆為整數）不會產生
   這種輸入，但這是現場工程師事故排查時會盯著看的頁面，任何未來後端調整/通訊
   異常/測試假資料產生非整數值都會讓頁面整個掛掉，屬於真實的防禦性輸入處理
   缺口。修法：`Math.min(4, Math.max(0, Math.round(level)))`（`frontend/
   components/TurbineDetail.tsx:71-78`）。
2. 🟡 **should-fix（已修復）**：塔架/葉片警報兩列手刻 `<div>` 複製
   `DataRow` 的 flex/border/字型樣式卻用 `alignItems: 'center'`（`DataRow`
   本身是 `'baseline'`），與同 tab 其他列視覺不一致；`DataRow` 的 `value`
   本就是 `React.ReactNode` 可直接吃 `<StatusPill>`。已改用
   `<DataRow value={<StatusPill .../>} />`。
3. 🟡 **should-fix（已修復）**：4 個累積損傷比例欄位的 warn/alert 門檻
   （原 0.5/0.8）與後端 `FatigueSpec` 真實 alarm 門檻
   （`alarm_notice=0.30`/`alarm_warning=0.60`/`alarm_danger=0.80`/
   `alarm_shutdown=0.95`）不一致——例如塔架 FA 損傷 0.35 已足以讓
   `WLOD_AlmTwr` 升到 1 級「注意」，但原始百分比那一列完全不會變色，同一 section
   內兩個視覺指標對同一份資料給出不一致的嚴重度判斷。已改為 `>= 0.3`/
   `>= 0.8`（對齊 `alarm_notice`/`alarm_danger`），並加註解說明門檻來源
   （DataRow 只有二級 warn/alert，無法完整對齊 4 級，故取 notice/danger 作為
   兩個切點）。
4. 🟡 **should-fix（已修復）**：新增測試補齊兩個 reviewer 點名的風險缺口——
   非整數/超出範圍警報等級（`2.5`→3「危險」clamp+round 驗證；另補負數 `-1`
   →0「正常」的防禦性回歸測試）、RUL 介於 0-24 小時（未滿 1 天）目前顯示
   「0天」而非小時數的已知顯示粒度限制（`formatRul` 加註解說明，測試明確
   pin 住這個已知行為而非隱性錯誤）。
5. 🟢 **nice-to-have（已修復）**：`FATIGUE_ALARM_LEVELS` 的 `tone` 型別原本
   手動重複宣告 `'ok' | 'info' | 'warn' | 'amber' | 'danger'`，與
   `StatusPill.tsx` 已匯出的 `PillTone` 型別會逐漸漂移不同步。改用
   `Extract<PillTone, ...>` 複用既有型別。

Reviewer 也獨立驗證了非須修正項：`formatRul` 手算覆核 4000h→166 天→
「5月 16天」、40000h→1666 天→「4年 6月」皆與 diff 內測試相符；`-1`/`null`/
`undefined`/`NaN` 皆正確短路到「—」；未改動的 `WLOD` section 無 regression
風險（既有測試未對該區塊 DOM 結構斷言）；`tsc --noEmit` clean；後端已把
`damage_*` clamp 到 `[0,1]`，前端 `(t.damageX || 0) * 100` 不會出現負數或
>100% 顯示。

**Mutation-verify must-fix**：`git stash push -- frontend/components/
TurbineDetail.tsx` 暫時只還原元件本體（保留測試檔案的新測試），重跑「非整數
警報等級」那條新測試 → **確認拋出與 reviewer 重現完全相同的
`TypeError: Cannot read properties of undefined (reading 'tone')`**，證實測試
真的鎖住這個 bug。「負數 clamp 到 0」那條測試在舊碼下**碰巧也通過**（舊版
三元判斷式對超出範圍值本就 fallback 到 0，只有「範圍內但非整數」才會踩雷）——
誠實記錄：這條測試對舊碼而言不是 bug-pinning，是替未來重構留的防禦性回歸測試。
`git stash pop` 還原修正後重跑全部 102 測皆綠。

## Wrap-up

- 完成 `WMOM-20260505-25-a`（`-25` 母 issue 降低版子項 Part A）：RUL 倒數 +
  塔架/葉片疲勞警報 badge + 4 個累積損傷比例，就地擴充 `TurbineDetail.tsx`
  既有 `fatigue` tab，零後端改動。
- `-25` 母 issue 保持 open，標註「Part A 已完成」，剩餘範圍
  （`SpectralAlarmPanel`/`BearingDiagPanel`/RUL 觸發時間軸）留給未來 session。
- **修正 `-25` 母 issue 原文兩處過時描述**：①`frontend/components/turbine/
  LoadFatiguePanel.tsx`（issue 引用的 pattern 參考）在程式碼庫內根本不存在，
  實際是 `TurbineDetail.tsx` 的 inline `case 'fatigue':` 分支；②Deliverable
  假設需要 3 個新元件 + 新 tab，但 RUL/警報資料早已透過既有 `scadaTags` 欄位
  全程到達前端，不需要新後端 API 或新資料流。
- **誠實揭露 / 未驗證範圍**：只驗證了「給定警報等級/RUL 值 → 顯示正確」這層
  UI 邏輯，**未做「故障注入 → 長時間模擬 → 等級真的隨時間從 0 升到 4」的
  端到端驗證**——`fatigue_model.py` 的損傷累積速率在 1x 時間尺度下需要數小時
  模擬時間才會有感變化，非本次單 session 範圍能覆蓋，且母 issue acceptance
  原文「故障注入時 alarm badge 會升級」嚴格來說仍待未來 session 用長時間
  模擬或加速時間尺度驗證。RUL 觸發時間軸（母 issue 提到的另一個 deliverable）
  也未實作，只顯示當下瞬時值；`data_broker.py:899-930` 既有的
  `event_type="fatigue"` history event 邏輯可作為未來 Part B 的資料來源。
- **最終驗證數字（review 修復 must-fix/should-fix 後重跑全套）**：
  `npx tsc --noEmit` 0 error；`npx vitest run` → **1486 passed**（70 files，
  baseline 1477 + 最終 9 個新測試，零 regression）；`npx vite build` 成功。
  backend 未動，1295 passed（7 skipped, 1 xfailed）不變。
- ISSUES.md：新增 `WMOM-20260505-25-a`（done，含完整 completion summary）；
  `WMOM-20260505-25` 母 issue status 改註記「Part A 已完成」；統計表
  open 7（不變，母 issue仍 open）、done 120→121、total 129→130（已用
  `grep -c "^### WMOM-"` 核對一致）。
- STATUS.yaml：`last_updated`/`issue_stats`（done 120→121、total 129→130）
  已同步。
- TODO.md：已同步本次完成摘要 + 順手修正「物理模型強化」段落過時的
  `-23`/`-24` 未勾選（實際皆早已 done）+ `-25` Part A 完成註記。
- 下次接手：`-25` Part B（`SpectralAlarmPanel` 5-band 頻譜視覺化，需要決定
  頻譜動態 threshold curve 的視覺呈現方式，比 Part A 更需要圖表設計判斷）或
  Part C（`BearingDiagPanel` BPFO/BPFI）；或繼續 `-27`/`-28`
  （物理強化，仍是多 session 大工，未找到降低版子項捷徑）；或等劉老師回覆
  `-26-a` 核准請求後直接認領。
