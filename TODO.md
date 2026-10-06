# windMindOM — TODO（短期工作板）

> ✅ **2026-09-23：CI runner 基礎設施確認恢復穩定**——2026-09-22 稍早（PR #157-#159）曾連續全數
> `runner_id: 0` 秒退失敗，19:20 UTC 起（PR #162 起）恢復正常跑測試。截至本次更新已累積連續 3 個
> PR（#162 / #163 / #164）真實跑完 CI 並自動 `auto-merge` 進 main，符合先前訂下的「連續 2-3 個
> session 都綠燈視為問題已解」門檻，故清除舊警語段落。**若日後再度出現同款秒退**（數秒內失敗 +
> `runner_id: 0` + check output 全空），因應方式：本機驗證（`pytest` + `vitest`/`tsc`/`build`）
> 為準、不等 auto-merge、不反覆重跑、PR 留言記錄一次即可，絕不可為了繞過 CI 直接 push main。
>
> 用途：本檔案是「**這週 / 這個月**正在做什麼」的快速 dashboard。
> 詳細 issue 規格在 [`ISSUES.md`](ISSUES.md)；完整路線圖在 [`docs/product/ROADMAP.md`](docs/product/ROADMAP.md)；
> M5/M6 大目標 epic 拆解在 [`ISSUES.md`](ISSUES.md) 頂部「🎯 未來大目標」區塊。
>
> 規則：
> - 只列「進行中 + 下一個要做」的事，**不列已完成**（done 的事看 git log + ISSUES.md）
> - 每次 session 開頭 / 結尾更新本檔
> - 大局看 ROADMAP；今日工作看 ISSUES.md；本週/本月節奏看本檔

最後更新：2026-10-06（**WMOM-20260505-25-c 完成**：振動 tab 軸承/齒輪診斷區塊，Part C 已做完；`-25` 剩 RUL 觸發時間軸。前次：**WMOM-20260505-26-a 完成**：SCADA 新增 `WSRV_ManualOverride`/
`WSRV_LockoutState`）。**劉老師 2026-10-06 回覆，下個 session 起依此挑題**：
- ✅ `WMOM-20260505-25` Part B（振動頻譜 tab）已完成（`-25-b`，2026-10-06）；Part C（`BearingDiagPanel`：BPFO/BPFI + GMF sideband）已核准 → **下個 session 優先認領 Part C**
- 🏠 HTTPS 部署配置：劉老師本機自測，**移出 autonomous 佇列**
- 🚫 docker 環境無法提供：`WMOM-20260509-F6`（PG row-lock）維持卡住，不要再嘗試

前次最後更新：2026-09-28（**WMOM-20260928-05 完成（第二十二個 autonomous
session）：`HistoryPage.tsx` 事件類型登記表補上 `fatigue`/`fault_lifecycle`，
修復真實後端事件整組隱形的 bug** — 接續前一 session 盤點 fatigue 資料流，
全庫 grep `event_type="` 發現後端實際記錄 7 種事件（`fatigue/fault/
fault_lifecycle/grid/operator/state/wind`），但 `HistoryPage.tsx` 的
`EVENT_TYPES` 登記表只認 5 種；`visibleEvents` 的
`enabledEventTypes[e.event_type] ?? false` 對未登記的兩型恆為 `false`——
無論篩選 toggle 狀態為何，這兩種真實資料永遠從事件清單/圖表標記/詳情面板
整組消失，且無任何錯誤提示（靜默失效）。純前端修復（五處既有查表結構各補
一 entry），零後端改動，貼合既有 pattern 不新增邏輯分支。**code-reviewer
subagent review：Approve，0 must-fix，3 should-fix 已處理**（work-log 對
`fault_lifecycle` `end_timestamp` 的技術陳述不準確已更正；`fault_lifecycle`
與既有 `fault` 共用 `warn` tone 在徽章上撞色，已改 `muted` 修復；`fatigue`
tone 對所有嚴重度一律 `danger`、未依 level 分級，初版「跨頁一致」措辭過度
宣稱已更正，改 code 超出本次刻意收斂範圍列 follow-up），3 個 nice-to-have
（`EventComparisonView.tsx` 情境比較路徑同款查表漏 `fatigue`；en 標籤技術
債；hex 色相相近，皆記錄 follow-up 未修）。新增 4 測，mutation-verified
（`git stash` 還原元件本體確認 4 測如預期全部 fail、23 舊測仍過，reviewer
獨立重現一致）。frontend 1486→**1490 passed**（70 files 不變，零
regression）/ tsc 0 / build OK；backend 未動 1295 passed（7 skipped, 1
xfailed）不變。詳見
`work-logs/2026-09/2026-09-28-history-page-event-types.md`。
**前一 session：WMOM-20260505-25-a 完成（第二十一個 autonomous
session）：`TurbineDetail.tsx` fatigue tab 新增 RUL 倒數 + 塔架/葉片疲勞警報
badge + 4 個累積損傷比例，零後端改動** — 重新盤點母 issue `WMOM-20260505-25`
發現其「需要新 tab + 3 新元件」描述已過時，RUL/警報資料早已透過既有
`scadaTags` 全程到前端，只是 `fatigue` tab 從未畫出來；拆出零風險 Part A
單 session 完工，母 issue 保持 open（剩 SpectralAlarmPanel/BearingDiagPanel/
RUL 觸發時間軸）。**code-reviewer subagent 抓到 1 must-fix（非整數警報等級
會 crash 整個 tab）+ 3 should-fix，皆已修復**。最終新增 9 測
mutation-verified。frontend 1477→**1486 passed**（70 files 不變，零
regression）/ tsc 0 / build OK；backend 未動 1295 passed（7 skipped, 1
xfailed）不變。**誠實揭露**：僅驗證顯示層邏輯，
未做故障注入長時間模擬的端到端驗證。詳見
`work-logs/2026-09/2026-09-28-rul-fatigue-alarm-frontend.md`。
**前一 session：WMOM-20260928-04 完成（第二十個 autonomous session）：
preflight 全綠，重新確認本 sandbox docker daemon 可用（需手動啟動 dockerd），
仍無可行 autonomous 工作，乾淨收尾** — backend 1295 passed（7 skipped, 1
xfailed）/ frontend tsc 0 / vitest 1477 passed（70 files）/ build OK，與
baseline 一致零 regression；無開放 PR。**新發現**：前兩個 session（`-01`/
`-02`）判定「本 sandbox 無 docker」只是沒人手動啟動 `dockerd`——用
`run_in_background` 啟動後 `docker ps`/`docker info` 正常回應，與
`WMOM-20260716-06`（2026-09-23）既有發現一致，非環境硬限制。重新檢視兩個
「需 docker」issue：`WMOM-20260716-06` 已於 2026-09-23 完成（routine prompt
快照過時仍列著）；`WMOM-20260509-F6`（PostgreSQL row-lock test）確認 docker
可用與否非決定性因素，真正卡點是 M6 是否上 PostgreSQL 的架構決策未拍板 +
需要全新 dialect 連線層，維持 🟡 不接。其餘 6 個 open + 2 個 in_progress issue
逐一重新核對，結論與前三個連續 session 一致，`WMOM-20260505-26-a` 仍在等劉
老師核准（自動排程無真人回覆，不可自行視為核准）。**未實作任何程式碼**，
未開功能性 PR，僅提交稽核結論文件更新。**給劉老師的問題（累積，可一行
回覆任一項即可解鎖）**：①是否核准 `WMOM-20260505-26-a`（最具體、最快可
解鎖）②cost ledger（`WMOM-20260504-11`）設計方向 ③`WMOM-20260509-F6`
的 M6 PostgreSQL 架構方向 ④`WMOM-20260505-25`/`-27`/`-28`（物理模型深化剩餘
3 項）是否排入 sprint ⑤`WMOM-20260513-01` UI v2 設計交接書是否已備妥。
**下個 session**：若 `-26-a` 已核准直接認領（單 session 可完工）；若無回覆，
不建議再重複第 5 次「逐一核對全部 open/in_progress issue」完整流程，改評估
是否能比照 `-26-a` 手法對 `WMOM-20260505-27`/`-28` 也切出小而無歧義的降低版
子項。詳見
`work-logs/2026-09/2026-09-28-docker-daemon-reconfirm-no-actionable-work.md`。
前一 session：2026-09-28（**WMOM-20260928-03 完成（第十九個 autonomous
session）：preflight 全綠，接續前一 session 建議草擬 `WMOM-20260505-26`
Service/Maintenance state 子項降低版提案（`WMOM-20260505-26-a`）** —
backend 1295 passed（7 skipped, 1 xfailed）/ frontend tsc 0 / vitest 1477
passed（70 files）/ build OK，與 baseline 一致零 regression；無開放 PR。
不再第三次重複「逐一核對 7 個 open issue」流程，改為實地查證
`WMOM-20260505-26` 可行性：發現母 issue 描述已過時——`WSRV_SrvOn`（service
mode flag）已存在且由真實 `service_mode` 狀態驅動；`operator_stop`/
`tur_state==7`（emergency stop）是既有真實狀態但未單獨暴露成 tag；
`calibration mode`/`firmware version` 則零命中無真實狀態可映射。據此提案
只做 `WSRV_ManualOverride`/`WSRV_LockoutState` 兩個新 tag、映射既有真實
狀態、acceptance 改用「整合測試證明既有控制路徑觸發時 tag 同步翻轉」，已
寫入 `ISSUES.md` `WMOM-20260505-26` 本文，附一行可核准的問題給劉老師。
**未實作任何程式碼**（依 routine §4 item 7 不自行開工），**本次除稽核記錄
issue 外未開其餘新工作 issue、未開 PR**。詳見
`work-logs/2026-09/2026-09-28-scada-26-service-maintenance-subscope-proposal.md`。
前一 session：2026-09-28（**WMOM-20260928-02 完成（第十八個 autonomous
session）：preflight 全綠，逐一核對 7 個 open issue 後本次無單 session 可行
候選，乾淨收尾**）。詳見
`work-logs/2026-09/2026-09-28-preflight-only-no-actionable-work.md`。
前一 session：2026-09-28（**WMOM-20260928-01 完成（第十七個 autonomous session）** —
`docs/routines/autonomous-daily-worker-prompt.md`（canonical routine 文件）版本
長期停在 v3（2026-06-03），已被至少 3 個具名 session work-log（`-05`/`-06`/
`-07`）提醒卻從未真正同步，本次把實際收到的 v4.1 cron prompt 全文整理進檔案
取代舊內容：版本標記 v3→v4.1；baseline 638/59→1295/1477 全面更新；補上 v4.1
既有但 v3 缺漏的自我測試/mutation-verify/GitHub MCP 降級模式/誠實回報等章節；
「## 3. 現況」章節與「維護備註」加註解說明該節是快照會過時、決策樹改依
`ISSUES.md`/`STATUS.yaml` 實際內容判斷，避免同款 drift 循環重演。純文件修改，
backend 1295 passed（7 skipped, 1 xfailed）/frontend tsc 0/vitest 1477
passed（70 files）/build OK 皆為 preflight baseline（未改動任何測試涵蓋的
程式碼，未重跑）。**code-reviewer subagent review：Needs revision，0
must-fix，3 should-fix 皆已修復**（work-log/ISSUES.md 收尾敘述本身的統計
落差與跨檔案數字矛盾，非 canonical 文件本體問題）。**下個
session**：可從 `WMOM-20260505-25~28`（物理強化，逐一看 estimate，皆多日
工作）或 M6 critical path 剩餘項（`WMOM-20260509-F6` PostgreSQL row-lock 需
docker、HTTPS 部署配置需先定部署目標，皆需劉老師決策）中挑選；其餘 open
issue（`WMOM-20260504-11`/`WMOM-20260513-01`）皆標 🟡 需劉老師決策/素材，
不宜自行開工。詳見
`work-logs/2026-09/2026-09-28-sync-autonomous-worker-prompt-v4.1.md`。
前一 session：2026-09-27（**WMOM-20260927-07 完成（第十六個 autonomous session）** —
`scada_registry.py` 內 `WCOL_CoolantLvl`/`WCOL_CoolantAlm` 兩個 tag 的
`subsystem` 欄位誤植修正：410/413 行 `"WCNV"`→`"WCOL"`（複製貼上疏漏），
dataclass docstring subsystem 列舉補上 `WCOL`/`WDRV`。新增 regression test
`test_scada_registry_subsystem.py`（2 tests），mutation-verify 確認還原修正後
兩測皆 fail。backend 1295 passed（baseline 1293 + 新增 2）零 regression；
frontend 未動（preflight baseline 確認 tsc 0/vitest 1477 passed 70 files/
build OK）。**code-reviewer subagent review：Approve，0 must-fix，1 should-fix
已修復**（subsystem 列舉註解一併補上早已缺漏的 `WVIB`/`WLOD`）。**reviewer
額外糾正本 issue 原描述的誤判**：`modules/monitoring/server/routers/i18n.py`
的 `GET /api/i18n/tags/registry` 端點直接回傳 `.subsystem` 欄位給前端，修正前
該 API 對這兩個 tag 實際回傳錯誤的 `"WCNV"`，並非「全庫零呼叫端依賴」，本次
一併糾正此 API 層級既有錯誤。**下個 session**：可從 `WMOM-20260505-25~28`
（物理強化，皆多日工作）或 M6 critical path 剩餘項（`WMOM-20260509-F6`
PostgreSQL row-lock 需 docker、HTTPS 部署配置需先定部署目標，皆需劉老師決策）
中挑選；其餘 open issue（`WMOM-20260504-11`/`WMOM-20260513-01`）皆標 🟡 需劉
老師決策/素材，不宜自行開工。詳見
`work-logs/2026-09/2026-09-27-scada-registry-wcol-subsystem-fix.md`。
前一 session：2026-09-27（**WMOM-20260927-06 完成（第十五個 autonomous session）** —
`docs/API_GUIDE.md` SCADA Tag System 章節 tag 總數/subsystem breakdown 全面
重新盤點：獨立重新核對 `scada_registry.py` 全部 14 個 subsystem 的實際 tag
數量，文件總數 74→109，breakdown table 全數重寫（新增 `WCOL`/`WDRV` 兩個先前
完全遺漏的 subsystem，`WROT`/`WMET`/`WVIB`/`WLOD` 的數字與描述文字皆核實
更新），同檔案第 160 行另一處相同過時數字一併修正。順手清理
`turbine_physics.py` 內確認永遠打不到的 `WFAT_TwrBs`/`WFAT_BldRt` 死碼分支
（全庫 grep 確認無其他引用，`modules/monitoring/tests/` 196 passed 零
regression）。純文件修改 + 1 處死碼移除，backend 1293 passed（7 skipped, 1
xfailed）零 regression、frontend 未動（preflight baseline 1477 passed/70
files/tsc 0/build OK）。**誠實揭露**：純文件修改無自動化測試保護；死碼移除
因原本無測試覆蓋，同樣無法 mutation-verify，改用全庫 grep 確認不可達的靜態
驗證。**code-reviewer subagent review：Approve，0 must-fix，1 should-fix 已
修復**（`WMET` 描述文字漏了仍存在的 ambient temp/atmospheric stability/raw
anemometer reading，且與 work-log 自述不符）**，2 nice-to-have**（1 已採納：
`WLOD` tower fore-aft/side-side 與 blade flapwise/edgewise 力矩用語拆開；
1 已登記新 issue **WMOM-20260927-07**：`scada_registry.py` 內 `WCOL_*` 兩個
tag 的 `subsystem` 欄位誤植為 `WCNV`，目前無呼叫端依賴不影響行為，未修）。
**下個 session**：可從 `WMOM-20260927-07`（10-15 分鐘小修）、
`WMOM-20260505-25~28`（物理強化，逐一看 priority，皆多日工作）或 M6 critical
path 剩餘項（`WMOM-20260509-F6` PostgreSQL row-lock 需 docker、HTTPS 部署
配置需先定部署目標，皆需劉老師決策）中挑選；其餘 open issue
（`WMOM-20260504-11`/`WMOM-20260513-01`）皆標 🟡 需劉老師決策/素材，不宜自行
開工。⚠ `docs/routines/
autonomous-daily-worker-prompt.md` 內文仍停留 v3，已連續多個 session 提醒，
建議劉老師找時間同步 cron trigger 設定內文（v4.1）回 repo。詳見
`work-logs/2026-09/2026-09-27-api-guide-tag-count-audit.md`。
前一 session：2026-09-27（**WMOM-20260927-05 完成（第十四個 autonomous session）** —
`docs/API_GUIDE.md` 仍教學查詢不存在的 `WFAT_*` SCADA tag 修正：核對
`scada_registry.py` 發現現行 schema 實際登記 16 個 `WLOD_*` tag（非簡單 7 對 7
改名——3 個舊 tag 現行已各自拆成 Fore-Aft/Side-Side 與 Flapwise/Edgewise），
「Fatigue / Load」參考清單區塊整段換成「Structural Load & Fatigue」列出全部現行
tag；4 處內嵌範例程式碼 `WFAT_TwrBsMy`→`WLOD_TwrFaMom`。純文件修改，backend/
frontend 皆未動、零 regression（1293 passed / 1477 passed 70 files / tsc 0 /
build OK 不變）。**code-reviewer subagent review（背景非同步，收尾提交後才
回報）：1 must-fix 已用 follow-up commit 修復**——文件第 69 行 subsystem
breakdown table 仍殘留一列不存在的 `WFAT` subsystem，緊接在剛修好段落正下方會
自相矛盾，已改為 `WLOD`；**1 should-fix 已登記新 issue WMOM-20260927-06**
（該表整張 tag 總數/subsystem breakdown 與現行 registry 實測 109〔非文件寫的
74〕差距很大，且缺 `WCOL`/`WDRV` 兩個 subsystem，遠超本次改名範圍，需另開
0.5-1 天 issue 重新盤點）；1 nice-to-have（`turbine_physics.py` 死碼分支）記錄
於新 issue。**誠實揭露**：純 Markdown 文件修改無自動化測試保護，僅讀原始碼
層級核對 `scada_registry.py` 定義驗證正確性。**下個 session**：可續評估
`WMOM-20260927-06`（`docs/API_GUIDE.md` tag 總數全面重新盤點，0.5-1 天）、
`WMOM-20260505-25~28`（物理強化，皆多日工作），或 M6 critical path 剩餘項
（`WMOM-20260509-F6` PostgreSQL row-lock 需 docker、HTTPS 部署配置需先定部署
目標，皆需劉老師決策）；其餘 open issue（`WMOM-20260504-11`/`WMOM-20260513-01`）
皆標 🟡 需劉老師決策/素材，不宜自行開工。詳見
`work-logs/2026-09/2026-09-27-api-guide-wfat-tag-fix.md`。
前一 session：2026-09-27（**WMOM-20260927-04 完成（第十三個 autonomous session）** —
`data_broker.py`/`models.py` 「WFAT (Legacy)」區塊 7 個永遠 `None` 欄位
（`twrBsMy`/`twrBsMx`/`bldRtMy`/`bldRtMx`/`delTwr`/`delBld`/`dmgAccum`）清理：
全庫查證確認完全未被前端/報表消費後，從 `models.py`/`data_broker.py`/
`frontend/hooks/useRealtimeData.ts`/`frontend/types.ts` 四處整組移除；順手修正
`fetch_scada_data.py` 範例 1 改讀實際有值的 `towerFaMoment`。backend 1293
passed（零 regression）；frontend tsc 0/vitest 1477 passed（70 files）/build
OK（零 regression）。**code-reviewer subagent review：Approve，0 must-fix**，
1 should-fix 登記 **WMOM-20260927-05** 追蹤（`docs/API_GUIDE.md` 仍教學查詢
不存在的 `WFAT_*` tag，範圍外未修），2 nice-to-have（標籤一致性已採納；API
相容性記錄）。**本 session 額外發現並更正**：`ISSUES.md`/`STATUS.yaml` 的
issue 統計數字長期與實際脫節（`grep -c "^### WMOM-"` 實際 123 筆，先前寫
147/149），已核實更正為準確數字（open 8 / in_progress 2 / done 113 /
total 123）。**下個 session**：可續評估 `WMOM-20260927-05`
（`docs/API_GUIDE.md` stale tag，10-15 分鐘小修）、`WMOM-20260505-25~28`
（物理強化，皆多日工作）、或 M6 critical path 剩餘項（PostgreSQL row-lock 需
docker、HTTPS 部署配置需先定部署目標，皆需劉老師決策）；其餘 open issue
（`WMOM-20260504-11`/`WMOM-20260513-01`）皆標 🟡 需劉老師決策/素材，不宜自行
開工。詳見
`work-logs/2026-09/2026-09-27-data-broker-wfat-legacy-cleanup.md`。
**前一 session：2026-09-27（WMOM-20260927-02 完成，第十二個 autonomous session）** —
`fetch_scada_data.py` 殘留已死 `WFAT_TwrBsMy`/`WFAT_BldRtMy` tag 引用改成現行
`WLOD_TwrFaMom`/`WLOD_BldFlapMom`（第 219、305 行）：確認 `scada_registry.py`/
`turbine_physics.py` 現行 schema 只實際產生 `WLOD_*` tag（`WFAT_*` 只是 sensor
noise config 裡「legacy support if needed」的相容分支），沿用
`WMOM-20260505-24` 已確認的同款對應。**誠實揭露**：本次修改**無自動化測試保護**
——該腳本走 live server REST/WebSocket、未被任何 pytest 匯入，issue acceptance
要求的「對 live server 實際資料執行」需要真的起 server，超出本次 10 分鐘小修
範圍，僅讀原始碼層級驗證（語法檢查 + 對照現行 schema）。**code-reviewer
subagent review：Approve，0 must-fix，0 should-fix**（獨立交叉驗證 tag 對應
語意正確性），1 nice-to-have 已採納：`data_broker.py:189-195`「WFAT (Legacy)」
區塊同款 7 個永遠 `None` 的欄位，影響面比範例腳本更大（API response model），
登記 **WMOM-20260927-04** 追蹤，未修。backend/frontend 皆零改動、零
regression：1293 passed（7 skipped, 1 xfailed）/ 1477 passed（70
files）/tsc 0/build OK 全部不變。**下個 session**：可續評估
`WMOM-20260927-04`（`data_broker.py` legacy 欄位查證清理，20-30 分鐘）、
`WMOM-20260505-25~28`（物理強化，皆多日工作）、或 M6 critical path 剩餘項
（PostgreSQL row-lock 需 docker、HTTPS 部署配置需先定部署目標，皆需劉老師決策）；
其餘 open issue（`WMOM-20260504-11`/`WMOM-20260513-01`）皆標 🟡 需劉老師決策/
素材，不宜自行開工。詳見
`work-logs/2026-09/2026-09-27-fetch-scada-data-stale-tags.md`。
**前一 session：2026-09-27（WMOM-20260927-03 完成，第十一個 autonomous session）** —
legacy `subsystems.py`（`WindTurbine`/`main.py` 路徑，`WMOM-20260927-01` code
review 登記的 follow-up）未種子化 RNG 修正：先全庫 grep 確認這條路徑完全未被
`run.py`/`api/`/Docker/任何既有測試引用（純歷史原型），但整條 legacy 檔案樹共 8
檔，全刪除遠超出本 issue「修 RNG」的範圍——選擇比照 -01 只做種子化，不刪檔案、
不動 `main.py`。`GearboxSystem`/`HydraulicSystem` 建構子新增 `seed` 參數，
`WindTurbine.__init__` 往下傳。**code-reviewer subagent review：Approve，0
must-fix，1 should-fix 已採納**（原本同一 `seed` 同時餵給 gearbox/hydraulic 兩個
獨立 `RandomState`，reviewer 實測出兩條物理無關噪聲會鎖死成固定比例 5.0——比照
`simulator/wind_field.py` 既有 seed+1000/+2000 偏移慣例改用 seed+1/+2）+ 1
nice-to-have 已採納。新增 8 測皆 mutation-verified（其一精準抓到
`5.0 != 5.0` fail，與 reviewer 預測完全吻合）。backend 1285→**1293
passed**（+8，零 regression）；frontend 未動，1477 passed（70 files）/tsc
0/build OK 不變。**誠實揭露**：reviewer 同時發現 **live** 路徑
`turbine_physics.py` 的 `VibrationModel`/`YawModel` 也共用同一 `_seed`，目前
只靠建構順序巧合才沒有同款相關性問題，是脆弱的 latent 風險——超出本 issue 範圍，
未修、未另開新 issue（純觀察記錄）。**下個 session**：可續評估
`WMOM-20260927-02`（`fetch_scada_data.py` stale tag，10 分鐘小修）、
`WMOM-20260505-25~28`（物理強化，皆多日工作）、或 M6 critical path 剩餘項
（PostgreSQL row-lock 需 docker、HTTPS 部署配置需先定部署目標，皆需劉老師決策）。
詳見 `work-logs/2026-09/2026-09-27-legacy-subsystems-rng-seeding.md`。
**前一 session：2026-09-27（WMOM-20260927-01 完成，第十個 autonomous session）** —
全域未種子化 RNG 造成模擬結果非決定性修正：`grid_model.py`（grid frequency/
voltage 噪聲）與 `physics/yaw_model.py`（brake_pressure 噪聲）先前直接呼叫全域
`np.random.normal`，跟其餘 codebase 一律用 `np.random.RandomState(seed)` 建立各自
種子化 `self._rng` 的慣例不一致（前一 session WMOM-20260505-24 修復過程中發現：
同一測試計畫重跑，個體差異 spread 數字每次略有浮動）。修法：兩者建構子新增 `seed`
參數；`turbine_physics.py` 把既有 per-turbine `_seed` 一併傳給
`YawModel(seed=_seed)`（沿用 `VibrationModel` 同款慣例）；`engine.py` farm-level
共用的 `GridEnvironmentModel` 改帶固定 seed。新增 `test_rng_seeding_determinism.py`
（5 測，含 farm-level 整合測試：兩個獨立 `WindFarmSimulator` 對同一序列
`_run_one_step()` 逐欄逐列比對），皆 mutation-verified。**誠實揭露**：
`GridEnvironmentModel` 的 `recovery` grid profile 分支用 `datetime.now()`（真實
牆鐘時間）算 elapsed，是與 RNG 種子化完全獨立的另一種非決定性來源，測試刻意排除
該分支，未修（判斷可能是刻意設計，非本 issue 範圍）。**code-reviewer subagent
review：Approve，0 must-fix，1 should-fix 已採納**（原選的 farm-level 共用
seed=7 落在逐風機 seed 範圍 1..14 內、與某風機撞號，雖不影響功能但違反設計意圖——
改用具名常數 `_GRID_MODEL_SEED = 1042` 並加註解說明必須落在風機 seed 範圍外的
不變量）+ 2 nice-to-have（issue acceptance 誤引用不存在的 `generate_data(...)`
方法已更正為 `_run_one_step()`；`subsystems.py` legacy `WindTurbine` 路徑同款
未種子化 RNG 確認是獨立 code path、非本 issue 範圍，登記 **WMOM-20260927-03**
追蹤未修）。backend 1280→**1285 passed**（+5，零 regression）；frontend 未動，
1477 passed（70 files）/tsc 0/build OK 不變。**下個 session**：可續評估
`WMOM-20260927-02`（`fetch_scada_data.py` 殘留 stale tag，10 分鐘小修）、
`WMOM-20260927-03`（legacy `subsystems.py` 同款 RNG 種子化）、`WMOM-20260505-25~28`
剩餘物理強化項目（逐一看本文 priority）、或 M6 critical path 剩餘項
（PostgreSQL row-lock 需 docker、HTTPS 部署配置需先定部署目標，皆需劉老師決策）。
詳見 `work-logs/2026-09/2026-09-27-rng-seeding-determinism.md`。
**前一 session：2026-09-27（WMOM-20260505-24 完成，第九個 autonomous session）** —
Data quality 3 項 fail 修正（個體差異 spread + Region 3 CV）：重跑官方 2 小時版
`examples/data_quality_analysis.py` 發現原文兩個 CV 太低項目已不重現（後續 physics
強化間接解決，未改動任何 power curve/individuality 參數），個體差異 spread 反而重跑
得到 118%（比原文 36.8% 更嚴重）——深挖後根本原因跟 individuality 參數無關：
`basic_validation` 測試計畫對 WT001/WT003 注入的故障一旦 severity 超過
`auto_trip_severity` 便永久 `tripped=True`，`simulator/engine.py` 之後每步都對其
呼叫 `cmd_emergency_stop()`，導致這兩台機組 2 小時內大部分時間卡在
emergency/recovery 迴圈（WT001 僅 399/7200 步在發電），「平均功率」被故障期間的
低產出嚴重污染，是分析腳本的測試方法論問題，不是 individuality 太誇張。修法：新增
純函式 `compute_healthy_individuality_spread()`，排除本次測試計畫中「曾經」（整台，
不只當下）被標記故障的機組，只在真正健康機組間比較——spread 落到 ~13-15% 區間
（每次重跑數字略有浮動，見下方非決定性發現），完全沒有改動任何物理模型參數即
通過。**附帶修正**：重新產生報告過程中發現 §4（載荷/Fatigue）整節悄悄變空——
引用的 `WFAT_TwrBsMy` 等 4 個 tag 在目前 schema 已改名為 `WLOD_TwrFaMom` 等
（`if tag in df.columns` guard 靜默跳過，無警訊），一併改名復原 §4/§5/§6/§8
對應檢查。**code-reviewer subagent review：Approve，0 must-fix，5 should-fix
全數採納**（NaN 平均功率的健康機組需一併 `dropna()` 排除；報告文字補印健康/
已排除機組 ID 清單；回傳型別由裸 `dict` 改 `@dataclass`；work-log 數字誤植已
更正為誠實區間描述；STATUS.yaml/TODO.md 已補同步）+ 3 nice-to-have（設計判斷
獲確認合理；補 empty-df 邊界測試；`fetch_scada_data.py` 同款 stale tag 登記新
follow-up）。新增 6 測（純函式，不需跑完整 simulator）皆 mutation-verified
（停用排除邏輯/`dropna()` → 對應新測如預期 fail → 已還原確認）。重新產生並
commit `data_quality_report.txt`：**20/20 全數 pass，0 項待改善**（原 18 pass/3
fail）。刻意不 commit 同批 `simulated_scada_2h.csv`（`timestamp` 欄位含
`datetime.now()`，每次重跑整份 36000 列 diff 全不同，純噪音，acceptance 未要求
同步 CSV）。backend 1274→**1280 passed**（+6，零 regression）；frontend 未動
1477 passed（70 files）不變、tsc 0、build OK。**誠實揭露/未修範圍**：①
`fault.tripped` 恆真後每步觸發 `cmd_emergency_stop()` 造成機組在 emergency/recovery
間反覆循環、產電時間暴跌，這本身是否為預期行為（重大故障後應完全停止 restart
嘗試 vs 持續嘗試）是行為設計決策，非本 issue 範圍，未展開處理，留待劉老師評估是否
需要另開 issue。②**新發現**：`simulator/grid_model.py`/`simulator/physics/
yaw_model.py` 直接呼叫全域未種子化的 `np.random.normal(...)`（其餘 codebase 皆用
每台機組種子化的 `self._rng`），是 spread 數字每次重跑略有浮動的根因——登記
**WMOM-20260927-01** 追蹤（未修）。③`fetch_scada_data.py` 殘留同款 stale
`WFAT_*` tag——登記 **WMOM-20260927-02** 追蹤（未修）。**上層摘要表提醒**：
`WMOM-20260505-23~28` 群組被籠統標成「學術深度非商業 must-have」，但 -24 本文
明寫 P0/demo 信任——之後評估這批 issue 建議逐一看本文 Priority 欄位，不要只看
群組標籤。**下個 session**：可續評估 -25~28 剩餘物理強化項目（逐一看本文
priority，不要照群組標籤全部跳過）、`WMOM-20260927-01`/`-02`（皆 15-30 分鐘可
完工的小修）、或 M6 critical path 剩餘項（PostgreSQL row-lock 需 docker、HTTPS
部署配置需先定部署目標，皆需劉老師決策）。詳見
`work-logs/2026-09/2026-09-27-individuality-spread-metric-fix.md`。
前一 session：2026-09-26（**WMOM-20260926-05 完成（第八個 autonomous session）** —
`ScenarioMountBanner.tsx` component render 測試：`components/ui/` 剩餘 7 支零測試
primitive 中優先評估的一支（PR C Phase 1 新增，有真正條件邏輯：`error` 決定 `Card`
tone/是否顯示錯誤說明、`loading && !error` 短路、lang en/zh 切換），先確認
`FarmOverview.tsx`/`TurbineDetail.tsx` host page 既有測試從未餵過 `loading`/`error`
props、這兩條分支完全零覆蓋，非為了補而補。新增
`frontend/components/ui/__tests__/ScenarioMountBanner.test.tsx`（16 tests，含 code
review 後補的 1 則），**未修改元件本體任何一行**。5 項關鍵邏輯 mutation-verified。
**code-reviewer subagent review：Approve，0 must-fix，0 should-fix，2
nice-to-have，1 個已採納**（補 `error=''` falsy 邊界測試明確鎖住既有行為；1 個未採納
純風格建議）。backend 1274 passed 不變；frontend tsc 0、1461→**1477 passed**（69→70
files，+16，零 regression）、build OK。`components/ui/` 剩餘 6 支（`Btn`/`Card`/
`Field`/`Logo`/`PageHeader`/`Stat`）維持既有評估結論（純展示、ROI 低，暫不主動補
測試）。**評估但略過**：`WMOM-20260504-11`（event-driven cost ledger，M4 增強）
仍 open，但 2-3 工作天多日新功能且涉及新 ledger schema 設計，非單 session 可完工、
無設計歧義的候選，留待劉老師決定是否排入或需先寫 decision log。**下個 session**：
`components/ui/` 測試覆蓋評估至此告一段落，可轉向 M6 critical path 剩餘項
（PostgreSQL row-lock 需 docker、HTTPS 部署配置需先定部署目標，皆需劉老師決策）或
物理模型強化（WMOM-20260505-23~28，學術深度非商業 must-have）；⚠
`docs/routines/autonomous-daily-worker-prompt.md` 仍停留 v3，已連續多個 session
提醒，建議劉老師找時間同步 cron trigger 設定內文（v4.1）回 repo。詳見
`work-logs/2026-09/2026-09-26-scenariomountbanner-render-tests.md`。**前一
session：2026-09-26（WMOM-20260926-04 完成，第七個 autonomous session）** —
`WorkOrderDetailModal.tsx`（legacy mock 版，`App.tsx` 'maintenance' 導覽路徑，由
`MaintenanceHub.onSelectWorkOrder` 觸發，與 backend `WorkOrderResponse` 版本的
`components/workflow/WorkOrderDetailModal.tsx` 是兩支不同元件）先前零 component render
測試，新增 `components/__tests__/WorkOrderDetailModal.test.tsx`（17 tests），**未修改
元件本體任何一行**。涵蓋標題/詳情/技師名稱 fallback、狀態 pill 三態、關閉互動（遮罩/
Close 鈕/內容區不冒泡）、備註編輯+Save、照片上傳（jsdom 無原生 `DataTransfer`，手刻
`makeFileList()` stub 繞過）/移除、Complete 流程（無照片 disabled 阻擋/有照片送出正確
更新後物件）、COMPLETED 唯讀模式。5 項關鍵邏輯 mutation-verified。**code-reviewer
subagent review：Approve，0 must-fix，2 should-fix 已採納**（補 1 測鎖住「有照片時
提示文字仍顯示」的真實行為〔原只受 isCompleted 控制、與照片數量無關〕+ 補程式碼註解
說明 disabled button 測試無法獨立驗證內部邏輯層 guard），3 個 nice-to-have 未採納。
**誠實揭露**：`handleComplete` 內部邏輯層 guard（`if (photos.length>0)`）無法獨立於
DOM 層 `disabled` 屬性被測到（jsdom 對 disabled button 不派發 click handler，
reviewer 獨立驗證同一結論），是防禦性重複、非本次新增缺口，已誠實標註於測試名稱與
work-log。backend 1274 passed 不變；frontend tsc 0、1443→**1461 passed**（68→69
files，+18，零 regression）、build OK。**附帶 housekeeping**：`WMOM-20260505-21` Status 過期未同步（其 follow-up
`WMOM-20260926-01` 早已全數完成）已更正為 done；`ISSUES.md` 頂部「🎯 未來大目標」
摘要表 M5-5 行過期敘述（誤寫「Part B-2 待續」，實則 `WMOM-20260608-02` 早於
2026-06-08 完成）已更正。**下個 session**：`components/ui/` 剩餘 7 支零測試
primitive（`Btn`/`Card`/`Field`/`Logo`/`PageHeader`/`Stat`/`ScenarioMountBanner`）
多半是極薄展示元件、已被宿主頁面測試間接涵蓋，邊際價值需評估（`ScenarioMountBanner`
較新較值得優先）；M6 critical path 剩餘項（PostgreSQL row-lock 需 docker、HTTPS
部署配置需先定部署目標）與物理模型強化（WMOM-20260505-23~28）維持既有阻塞狀態。
詳見 `work-logs/2026-09/2026-09-26-workorderdetailmodal-render-tests.md`。**前一
session：2026-09-26（WMOM-20260926-03 完成，第六個 autonomous session）** —
PR C Phase 1 實作：情境掛載唯讀端點 + FarmOverview/TurbineDetail 接線。後端新增
`Storage.scenario_turbine_ids()` + `GET /api/scenarios/{id}/turbines`/
`farm-status` 兩個唯讀端點（格式對齊即時 `/api/turbines*`）；前端新增
`ScenarioMountContext`（內建 `useScenarioMountData` 單次 fetch，`turbines`/
`loading`/`error` 隨 context 分發）+ `ScenarioMountBanner` +
`ScenarioDetail`/`ScenarioPage`/`App.tsx` 掛載入口串接 + `FarmOverview`/
`TurbineDetail` 停用所有即時資料/寫入子面板（含 `OperatorControlCard` 整張替換、
`TrendChartPanel`/farm-trend 停用——因情境機組 id 與即時機組 id 共用同一套
`WT{n}` 命名，不停用會讀到/能操作到真正的即時風機）。**code-reviewer subagent
review 抓到 1 must-fix + 3 should-fix + 2 nice-to-have，全數已修復並
mutation-verified**：🔴 must-fix——情境掛載後永遠無法回報 FAULT 狀態（DB 的
`operational_state` 結構上不會是 "FAULT"，即時路徑的 FAULT 覆寫靠記憶體內
`FaultEngine`，批次生成完就消失），改依已持久化的故障注入事件（`history_events`
payload）用與 `FaultEngine.step()` 相同公式離線重算 tripped 狀態，不需新
schema；3 個 should-fix（`turState` 的 `or 6` 誤把真實 `0` 捏造成 `6`；
`handleMountScenario` 「瀏覽總覽」分支未清 pending turbine id 導致競態；
`useScenarioMountData` 的 `error` 從未浮現在畫面上，順便把 fetch 移進
`ScenarioMountProvider` 內建）；2 個 nice-to-have（dispatch handler 補獨立
mounted guard；異常 turbine_id 補 warning log）。backend 1255→**1274 passed**
（+19）；frontend tsc 0、1402→**1443 passed**（65→68 files，+41）、build OK，
皆零 regression。`DEC-20260720-01`/`DEC-20260720-02` 的 PR C 至此完整收尾
（Phase 2 工單演練維持明確 deferred，未評估）。詳見
`work-logs/2026-09/2026-09-26-scenario-mount-phase1.md`。**前一 session
（WMOM-20260926-02 完成，PR C 子設計定案，第五個 autonomous session）** —
`WMOM-20260926-01` 完成後唯一剩下的「可立即接手」項目 PR C 自 2026-07-20 立案
以來被至少 8 個 session 因「需獨立子設計」原地擱置。用 Explore agent 讀過
`data_broker.py`/`routers/source.py`/`routers/scenarios.py`/decision log 全文，
確認掛載情境若照原案動 `DataBroker` 單一 active source 狀態機會與
`WMOM-20260720-04`/`-08` 剛硬化好的並發關鍵區衝突，改採「與 broker 正交的唯讀
端點 + 前端 `ScenarioMountContext`」方案，寫入 `docs/product/decision_log.md`
`DEC-20260926-01` 定案。詳見
`work-logs/2026-09/2026-09-26-pr-c-scenario-mount-subdesign.md`。**前一 session
（WMOM-20260926-01 三項全數完成，issue 標 done，第四個 autonomous session）** —
`work_order.finish()` → day_work_form 自動寫入 hook：工單
完工（`approve_all`：`AWAITING_SIGNOFF → CLOSED`）時，自動幫該工單 `assignee_id`
對應員工當天日誌 append 一筆 `completed_wo` activity。掛在
`WorkOrderRepository.transition()` 內部 `action == "approve_all"`——唯一能同時覆蓋
`approval_router` 簽核鏈自動觸發與 `work_order_router` 直接 `/approve` 入口兩條完工
路徑的地方。`work_date` 用 Asia/Taipei 曆日；day_work_form 寫入失敗只 log 不影響已
commit 的工單關閉。**code-reviewer subagent review：Approve，0 must-fix，2
should-fix + 2 nice-to-have，2 個 should-fix 皆已修復**：①補建 schema 的
`DayWorkFormORM.__table__.create(checkfirst=True)` 呼叫其實已多餘（reviewer 追出
package `__init__.py` import 順序保證 table 早已註冊），且在完工熱路徑上每次多一次
engine 連線 + 寫鎖 round trip——已刪除，本 session 獨立驗證 import 順序後才動手；
②一個測試名稱宣稱測 `work_order_router` 直接入口實際是複製 repository 層測試的假
覆蓋——已刪除，改在 `test_approval_api.py` 新增走完整簽核鏈 HTTP 流程的端到端整合
測試；③`created_by` 比照 router 慣例補齊。新增/調整測試皆 mutation-verified。
backend 1250→**1255 passed**（+5，零 regression）；frontend 未動 1402 passed 不變、
tsc 0、build OK。**前一 session（WMOM-20260926-01 第 3 項完成，第三個 autonomous
session）** — 讀取端點 ownership 限制：`list`/`by-date`/`{form_id}` 3 個讀取端點原只檢查「有沒有
登入」，未限制查詢範圍（含 TREASURY 也能瀏覽任一員工任一天完整日誌）。新增
`modules/auth/dependencies.py::resolve_actor_when_enforced`（enforce=false 過渡期不
限制，比照 `require_role`/`require_authenticated` 風格）；`_FULL_VISIBILITY_ROLES =
{LEADER, SUPERVISOR, ADMIN}` 維持可查全員，EMPLOYEE/TREASURY 收窄成只能查自己（list
靜默覆寫 filter、by-date 非本人 403、detail 404-before-403）。**code-reviewer
subagent review：Approve，0 must-fix，2 should-fix + 2 nice-to-have，皆已處理**（補
3 個 EMPLOYEE 版本測試涵蓋先前只測 TREASURY 的交集空白、work-log TODO 回填、
`_to_uuid` 共用 helper、cutover 前端 checklist 記錄）。新增 13 測皆
mutation-verified。backend 1237→**1250 passed**（+13，零 regression）；frontend 未動
1402 passed 不變、tsc 0、build OK。`WMOM-20260926-01` 維持 `in_progress`（第 1、3 項
完成，第 2 項 `work_order.finish()` hook 仍 open）。**下個 session**：優先接手
`WMOM-20260926-01` 第 2 項——設計答案已寫入 work-log（掛點：
`WorkOrderRepository.transition()` 內部 `action == "approve_all"`），或見下方「需
劉老師決策」清單、PR C（需先寫 broker 子設計）。）
前一 session：2026-09-26（**WMOM-20260926-01 第 1 項完成（第二個 autonomous session）**
— `day_work_form` 前端（工作日誌 tab，本人專用）：`services/dayWorkFormService.ts`（新檔）+
`hooks/useDayWorkForm.ts`（新檔）+ `components/workflow/DayWorkFormPanel.tsx`（新檔，
日期選擇 + 當日活動列表 + 新增活動表單 4 kind + 最近日誌歷史僅本人）+ `statusUtils.ts`
（`activityKindLabel`/`todayAsiaTaipei`）+ `WorkflowPage.tsx`（新增 daywork tab）。
**code-reviewer subagent review 抓到 1 must-fix + 3 should-fix + 3 nice-to-have，
must-fix 與 3 個 should-fix 全數已修復**：①`useDayWorkForm.appendActivity` 的
`setForm` 缺對稱 race 防護（送出期間切日期，較慢回應後到會蓋回舊資料且不自我修正）—
補 `latestWorkDateRef` 比對，並補 `hooks/__tests__/useDayWorkForm.test.ts`（10 測，
reviewer 判定 `useInspectionSchedules` 無專屬測試的慣例不適用本 hook）；②
`myWorkOrderOptions` 誤共用 Orders tab 已過濾的 `wo.items`——改掛獨立
`useWorkOrders({ farmId })`；③`item_id` 缺 UUID 格式驗證 + 錯誤訊息不友善——補 regex
前置驗證 + `readError` 比照 `knowledgeService.ts` 解析陣列 422 detail；④過期 `woId`
未重新對齊——補 `stillValid` 比對（mutation test 過程中額外發現並修正這個修法本身漏
處理清單變空的邊界、以及第一版測試斷言 channel 選錯無法真正鎖住的問題）。2 個
nice-to-have 已採納（已記錄過工單排除選單 + `fmtDate` docstring 補充）。frontend
1354→**1402 passed**（63→65 files，+48，零 regression）；backend 未動 1237 passed
不變、tsc 0、build OK。`WMOM-20260926-01` 標 `in_progress`（第 1 項完成，第 2 項
`work_order.finish()` hook + 第 3 項讀取端點 ownership 限制仍 open，皆需設計決策）。
**下個 session**：優先接手 `WMOM-20260926-01` 剩餘 2 項（先讀
`state_machine.py`/`approval_router.py` 決定 hook 掛點），或見下方「需劉老師決策」
清單、PR C（需先寫 broker 子設計）。）
前一 session：2026-09-26（**WMOM-20260505-21 後端完成** — `day_work_form` 員工當天工作日誌：
domain（`ActivityKind` enum + `ActivityEntry`/`DayWorkForm` dataclass + `validate_activity_
entry` 純函式 + `ACTIVITY_REQUIRED_FIELDS` 表）+ repository（`DayWorkFormRepository`：
`(farm_id, employee_id, work_date)` 唯一索引 natural-key `get_or_create_for_date` + 累加式
`append_activity`）+ router（5 endpoints：get-or-create/list/by-date/detail/append-activity）
全數完成，55 個新測試皆 mutation-verified。**code-reviewer subagent review 抓到 1 must-fix +
3 should-fix + 2 nice-to-have，must-fix 與前兩項 should-fix 已修復**：①`append_activity`
完全沒有 ownership 檢查，任何在職員工可竄改別人的日誌，且**我自己寫的測試字面上把這個錯誤
行為鎖成預期通過**（`test_append_activity_enforced_employee_ok` 建立者與 append 呼叫者用
兩個不同隨機 subject 卻斷言 200）——reviewer 用既有測試斷言反證出 bug，修法：先 404 查無
日誌，再比對呼叫者身分與 `form.employee_id`，不同者一律 403（不分角色，LEADER/SUPERVISOR
也不能代填）；②domain/schema 兩份 `_REQUIRED_FIELDS` 逐字複製、無 parity 測試——已改成
domain 匯出公開 `ACTIVITY_REQUIRED_FIELDS`，schema 直接 import 同一物件；③repository helper
缺型別標註已補。讀取端點（list/by-date/detail）無 ownership 限制（reviewer 判定非阻塞本
PR）+ work_order.finish() 整合 hook + 前端頁面，拆成新 follow-up **WMOM-20260926-01**（open，
API 已齊全可直接接手，但需先讀 `state_machine.py`/`approval_router.py` 決定 hook 掛點）。
新增 3 個 regression test 鎖住 ownership 修復，皆 mutation-verified。backend 1182→**1237
passed**（+55，零 regression）；frontend 未動 1354 passed（63 files）不變、tsc 0、build OK。
**附帶發現**：`ISSUES.md`/`STATUS.yaml` 頂部統計表數字（141/142）與 raw grep `### WMOM-*` +
`**Status**` 欄位在 `ISSUES.md` 主文實測數字（114 筆：9 open + 3 in_progress + 102 done）對
不上，推測與歷史 `WMOM-20260529-02` changelog 抽 archive 有關；本次沿用既有 delta-only 更新
慣例未展開全面稽核，已在 `STATUS.yaml` `issue_stats` 註解記錄，供劉老師或未來 session 決定
是否要開一個 dedicated 清點 issue。**下個 session**：優先接手 **WMOM-20260926-01**（前端 +
finish hook + 讀取端點 ownership 限制，三項可分次做），或見下方「需劉老師決策」清單、PR C
（需先寫 broker 子設計）。）
前一 session：2026-09-25（**WMOM-20260925-05 完成** — `WMOM-20260505-22` 前端收尾：`inspection_
schedule` 定檢計畫管理併入既有 `WorkflowPage.tsx`（新增第 5 個 tab「定檢計畫」，非獨立路由）+
`TurbineDetail.tsx` header『安排檢查』鈕接上 `onNavigateInspection(turbine.name)` 深連結。新增
`inspectionScheduleService.ts` API client + `useInspectionSchedules` hook（沿用
`useInventory` 模式，create/activate/deactivate/runScheduler 完成後皆 refetch 整列表以維持
`next_due_at` 排序正確）+ `InspectionScheduleListPanel`/`CreateInspectionScheduleModal`/
`InspectionScheduleDetailModal` 三支元件。`App.tsx` 新增 `inspectionDeepLinkTurbineId` state，
`handleNavSelect` 一般導覽時清空避免深連結過濾殘留跨 session。新增 66 測皆
mutation-verified。**code-reviewer subagent review 抓到 2 must-fix + 2 should-fix，
must-fix 與 should-fix 全數已修復**：①`onNavigateInspection` 呼叫順序寫反，同一
event handler 內兩個 `setState` 被 React batch 導致深連結恆為 no-op（永遠停在預設
tab、不帶風機過濾）——改成 `handleNavSelect(id, opts)` 單一 setState 呼叫的結構性
修法，非僅調換順序；②`useInspectionSchedules` 的 `activate`/`deactivate` 誤用
`patchLocal` 違反自己 docstring 宣稱的 refetch 行為，`active_only` filter 下暫停
計畫不會即時從列表消失——已改為 `fetchList()`；③`CreateInspectionScheduleModal`
的 `canSubmit` 只檢查 turbineId 非空字串未驗證是否仍在 turbineOptions 內，已改
`turbineOptions.some(...)` 並補 1 個 regression test。backend 未動；frontend
tsc 0、`npx vitest run` 63 files **1354 passed**（零 regression）、`npx vite
build` OK。`WMOM-20260505-22`（後端+前端）與 `WMOM-20260507-02`（PageHeader
placeholder 按鈕清單，6 個 sub-task 全數完成）皆標 done。**誠實揭露**：`App.tsx`
深連結 state 管理無自動化測試保護（`App.tsx` 本身無 test 檔，既有慣例——這正是
must-fix #1 沒被自動化測試抓到、只能靠 code review 人工發現的根本原因）；
`useInspectionSchedules` hook 內部邏輯無獨立單元測試（沿用同款 workflow CRUD hook
既有模式，只透過 `WorkflowPage.test.tsx` mock 間接驗證接線）。**下個 session**：見
下方「需劉老師決策」清單、PR C（檢視情境掛載 app，需先寫 broker 子設計），或評估
M6 critical path 剩餘項（WMOM-20260720-04/-08 殘項、footprint、PostgreSQL
row-lock、HTTPS 部署）。）
前一 session：2026-09-25（**WMOM-20260505-22 後端完成** — `inspection_schedule` 定檢計畫 +
scheduler auto-spawn：domain（`Recurrence` enum + 純函式）+ repository
（`InspectionScheduleRepository`）+ service（`run_inspection_scheduler`，手動觸發 API、冪等、
撞 multi-WO constraint 跳過不漏排，刻意不加背景 cron）+ router（7 endpoints）全套完成，79 測
皆 mutation-verified。code-reviewer subagent review 抓到 **1 must-fix + 1 should-fix**（PATCH
可寫入 `recurrence=custom_days` 卻缺 `interval_days` 的無效狀態，scheduler 到期時才炸開，造成
重複 spawn 工單 + 500，reviewer 有獨立 repro script 實測重現；`create()` 驗證原本可被明確帶
`first_due_at` 繞過），皆已用三層防禦修復（`create()`/`update_metadata()`/scheduler 各自驗證）
並補 6 個 regression test mutation-verified。backend 1103→**1182 passed**（+79，零
regression）；frontend 未動 1288 passed（60 files）不變、tsc 0、build OK。**前端未做**
（`TurbineDetail.tsx` 安排檢查鈕接線 + `/admin/workflow/inspection` 定檢計畫管理頁），拆成新
**WMOM-20260925-05**（open，API 已齊全可直接接手）。`WMOM-20260505-22` 標 `in_progress`
（非 `done`，後端完成前端未完成）。**下個 session**：優先接手 **WMOM-20260925-05**（無設計
歧義，`WMOM-20260507-02` sub-task d 也順便解掉），或見下方「需劉老師決策」清單、PR C（需先
寫 broker 子設計）。）
前一 session：2026-09-25（**WMOM-20260925-04 完成** — `FarmOverview.tsx` PageHeader
『+ 新報告』鈕接線（`WMOM-20260507-02` sub-task f）：認領前先讀
`modules/reporting/routers/reporting_router.py` 摸清報告類型（僅
`monthly`/`annual-budget` 兩種），發現 `/admin/reports`（`ReportsPage.tsx`，M4
`WMOM-20260509-09` 早已完整實作 monthly/annual 兩 tab + PDF 下載）已涵蓋 issue 原文
「開 modal 選報告類型」所需功能，**刻意偏離原文寫法**改把按鈕接到既有頁面導覽
（`FarmOverviewProps` 新增必填 `onNavigateReports`，`App.tsx` 傳入
`() => handleNavSelect('reports')`，與 sidebar nav 同路徑），避免重造功能較弱的
重複子集 modal（已於 ISSUES.md/work-log 明確記錄化解未來誤判重複開工的風險）。+2
vitest（zh/en aria-label 點擊接線）皆 mutation-verified。backend 未動 1103 passed
不變；frontend tsc 0、1286→1288 passed（60 files，零 regression）、build OK。
code-reviewer review：Approve，0 must-fix，0 should-fix（獨立核對必填 prop 慣例、
`handleNavSelect('reports')` 無副作用、測試非同義反覆）。**`WMOM-20260507-02` 清單
至此僅剩 sub-task d**（依賴 `WMOM-20260505-22` `inspection_schedule` 尚未做，持續
卡著）。**下個 session**：見下方「需劉老師決策」清單、PR C（需先寫 broker 子設計），
或評估是否要動 `WMOM-20260505-22` 解開 sub-task d 最後一項阻塞。）
前一 session：2026-09-25（**WMOM-20260925-03 完成** — `MaintenanceHub.tsx` PageHeader
『+ 新工單』鈕接線（`WMOM-20260507-02` sub-task e）：新增 `NewWorkOrderModal`（比照
`TurbineDetail.tsx` `CurtailModal`/`DispatchModal`/`FarmSelector.tsx` `CreateFarmModal`
遮罩/`role="dialog"` 慣例）：風機 `Select`（新增 `turbines` prop）+ 問題描述 + 技師
`Select`（僅列 `ON_DUTY`，比照 `DispatchModal` 既有規則）。送出打既有
`maintenanceData.createWorkOrder`（`useMaintenanceData.ts` 早已實作供 `DispatchModal`
使用，`POST /api/maintenance/work-orders`，`SUPERVISOR`-only），成功後關窗。
`createWorkOrder` 第 4 參數 `technicianId` 型別改選填（對齊後端 `Optional[int]`）。
`App.tsx` 補 `turbines`/`lang`（`lang` 為附帶發現的既有缺口一併修正）。+11 vitest 皆
mutation-verified（本 session 4 輪 + code review 後補的 should-fix #1 校驗 1 輪）。
backend 未動 1103 passed 不變；frontend tsc 0、1275→1286 passed（60 files，零
regression）、build OK。code-reviewer review：Approve，0 must-fix，2 should-fix（技師
選取與 10s 輪詢資料脫節可能送出過期 id，已修＋補測；沿用 `DispatchModal` 較弱的
fire-and-forget 模式而非 `CurtailModal` 完整 error state，reviewer 確認不阻塞未修）。
`WMOM-20260507-02` 清單至此僅剩 sub-task d（依賴 `WMOM-20260505-22` 尚未做）與 f（需先
確認 reporting module 報告類型 API）。**下個 session**：可續接 `WMOM-20260507-02`
sub-task f（風場總覽 `+ 新報告`，建議先讀 `modules/reporting/routers/*.py` 摸清可選
報告類型清單再動工），或見下方「需劉老師決策」清單、PR C（需先寫 broker 子設計）。）
前一 session（WMOM-20260925-02）：`TurbineDetail.tsx` PageHeader『限載』鈕
接線（`WMOM-20260507-02` sub-task c）：新增 `CurtailModal`（比照 `FarmSelector.tsx` 的
`CreateFarmModal` 遮罩/`role="dialog"` 慣例）收 kW 值後打 `authFetch POST
/api/control/curtail`（`SUPERVISOR`-only），是右欄 `OperatorControlCard` 限載輸入的重複
入口（比照 sub-task b『停機』header 鈕先例）。留空 = 解除限載、前端擋負值、後端非 2xx 顯示
`detail` 不關窗。+8 vitest 皆 mutation-verified（本 session 1 輪 + code-reviewer 獨立
2 輪）。backend 未動 1103 passed 不變；frontend tsc 0、1267→1275 passed（60 files，零
regression）、build OK。code-reviewer review：Approve，0 must-fix。
前一 session（WMOM-20260925-01）：`frontend/hooks/*.ts` authFetch 稽核
缺口一次做完全部 sub-task（未依建議拆多 session，因修法完全一致無設計歧義）：
`useSettings.ts`（`POST /api/config/simulation`+`/datasource`，皆 SUPERVISOR）、
`useMaintenanceData.ts`（2 GET + 3 個 SUPERVISOR 寫入 + 2 內部 refresh GET）、
`useRealtimeData.ts`（初始 REST fetch + WS 斷線輪詢 fallback）、`useI18n.ts`
（`GET /api/i18n/tags/all`）、額外發現的 `App.tsx:166`（`GET /api/farms` 健康檢查）共
13 處 `fetch(` 改 `authFetch(`。逐一重讀後端 router 源碼核對角色設定與 issue 描述一致。
新增/追加測試 11 個（`useMaintenanceData`/`useI18n` 新建測試檔），皆逐一
mutation-verified（改回裸 fetch → 對應已登入 header 斷言如預期 fail，scratchpad 備份
還原）。`frontend/` 全樹遞迴 grep 確認無裸 fetch 殘留。`App.tsx` 該處因元件零 render
test 基礎設施（需 mock ~15 個子元件，超出本次範圍）僅程式碼閱讀 + tsc 驗證，已誠實記錄。
已回頭把 `docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表
「前端所有寫入 request 都帶 token」**重新勾選**——`WMOM-20260925-01` 完成，M6 auth cutover
的前端側阻塞已清除（cutover 本身〔翻 `WMOM_AUTH_ENFORCE=true`〕仍是獨立、需另評估時機的
動作）。backend 未動 1103 passed 不變；frontend tsc 0、1256→1267 passed（58→60 files，
+11 新測，零 regression）、build OK。code-reviewer subagent review：**Approve，0
must-fix**，2 nice-to-have（`useSettings.ts` 寫入失敗未浮現 UI 錯誤——既有行為非本次引入，
宜另開 issue；reviewer 獨立確認全樹無殘留裸 fetch），皆未採納/非本次範圍。
**下個 session**：見下方「需劉老師決策」與「可立即接手」清單，M6 critical path 優先
`WMOM-20260720-04`/`-08` 系列殘項或情境比較 A2 Part 4（差異圖）/ PR C。）
前一 session（WMOM-20260924-08）：`MyOrdersMode.tsx` fetchActiveFarmId() 補
`authFetch`（一致性技術債，`WMOM-20260923-08` review 登記的 follow-up）。GET `/api/farms`
（後端 `require_authenticated()`）改 `authFetch`，新增 2 測皆 mutation-verified。backend
未動 1103 passed 不變；frontend 1254→1256 passed（+2 新測）、tsc 0、build OK。
code-reviewer review：Approve，0 must-fix。**⚠ 重大發現**：本 session 主動遞迴重掃
`frontend/hooks/*.ts`（`WMOM-20260923-10` 系列稽核從未涵蓋此目錄，只掃了
`components/*.tsx`），發現 `hooks/useSettings.ts`（`POST /api/config/simulation` +
`POST /api/config/datasource`，皆 `require_role(SUPERVISOR)`）與
`hooks/useMaintenanceData.ts`（`PATCH .../technicians/{id}/status`、
`POST`/`PATCH /work-orders`，皆 `require_role(SUPERVISOR)`）內的裸 fetch **寫入呼叫**仍缺
`Authorization` header——嚴重度高於已修復的純讀取缺口，`WMOM_AUTH_ENFORCE=true` cutover
後會讓 `MaintenanceHub`/`SettingsPage` 的寫入操作整面靜默 401。code-reviewer subagent 獨立
recursive grep 得到相同結論（另補一處 `App.tsx:166` 待核對）。已開新 issue
**WMOM-20260925-01**（high priority，M6 auth cutover 前置阻塞）追蹤，並回頭把
`docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表「前端所有寫入
request 都帶 token」**取消勾選**——完成 WMOM-20260925-01 前不得翻
`WMOM_AUTH_ENFORCE=true`。**下個 session 優先接手 WMOM-20260925-01**（見 ISSUES.md 建議
拆法：`useSettings.ts` → `useMaintenanceData.ts` → `useRealtimeData.ts`+`useI18n.ts`）。）
前一 session：WMOM-20260923-08 — `FarmOverview.tsx` farm-trend fetch 補
`authFetch`（一致性技術債，`WMOM-20260923-07` review 登記的 nice-to-have follow-up）。
`TrendCard` 內僅存的一處裸 fetch（`/api/turbines/farm-trend`，後端
`require_authenticated()` 任何登入者可讀）改 `authFetch`，比照同檔案匯出鈕已建立的手法。
新增 2 測（已登入時 mount GET 帶 `Authorization` header；未登入時驗證過渡期行為不變），皆
mutation-verified（authFetch 改回裸 fetch → 已登入測試如預期 fail，用 scratchpad 備份而非
`git checkout` 還原確認）。backend 未動 1103 passed 不變；frontend 1252→1254 passed（+2
新測，58 files 不變）、tsc 0、build OK。`FarmOverview.tsx` 全檔至此無裸 `fetch` 殘留。
code-reviewer review：Approve，0 must-fix，1 should-fix（範圍外發現：遞迴重掃
`frontend/components/` 全樹找到 `components/field/MyOrdersMode.tsx:31` 仍是裸
fetch——`WMOM-20260923-10` 原稽核指令未遞迴子目錄漏掉這支現場工程師頁面，登記新 follow-up
**WMOM-20260924-08**、估時 15 min、🔵 autonomous-friendly，非本次範圍）。）
前一 session：WMOM-20260924-07 — `WMOM-20260923-10` sub-task 7/7（清單收尾）：
`TrendChartPanel.tsx` authFetch 補齊。即時趨勢圖面板 2 處裸 fetch（mount 時 GET `/api/i18n/tags`
+ mount/preset/自訂 tag/turbineId 變更時且每 2 秒輪詢 GET `/api/turbines/{id}/trend`，皆後端
`require_authenticated()` 任何登入者可讀）改 `authFetch`，比照姊妹 PR
WMOM-20260923-07/-09/-20260924-01~06 手法。新增 2 測（已登入時兩條 mount GET 皆帶
`Authorization` header；未登入時驗證過渡期行為不變），皆 mutation-verified（authFetch 改回
裸 fetch → 已登入測試如預期 fail → 用備份還原，非 `git checkout`）。backend 未動 1103
passed 不變；frontend 1250→1252 passed（+2 新測）、tsc 0、build OK。code-reviewer review：
Approve，0 must-fix、0 should-fix（確認 2 秒輪詢下 `authFetch` 401 handler 重複觸發為既有跨
元件已接受特性，非本次新增問題；`.then/.catch` 鏈無行為影響；grep 確認無漏改）。
**`WMOM-20260923-10` 稽核清單（7 支元件）至此全數完成，已標 done**，並回頭勾掉
`docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表「前端所有寫入
request 都帶 token」項目。⚠ 附帶再次提醒：`docs/routines/autonomous-daily-worker-prompt.md`
內文仍停在 v3（舊 baseline），已連續多個 session 落後於實際 cron trigger prompt（v4.1），
建議劉老師找時間同步。）
前一 session：WMOM-20260924-06 — `WMOM-20260923-10` sub-task 6/7：
`HistoryPage.tsx` authFetch 補齊。歷史資料頁 2 處裸 fetch（mount 時 GET `/api/i18n/tags` +
mount/篩選變更時 GET `/api/turbines/{id}/history`，後者帶 `AbortController` signal，皆後端
`require_authenticated()` 任何登入者可讀）改 `authFetch`，比照姊妹 PR
WMOM-20260923-07/-09/-20260924-01~05 手法。新增 2 測（已登入時兩條 mount GET 皆帶
`Authorization` header；未登入時驗證過渡期行為不變），皆 mutation-verified（authFetch 改回
裸 fetch → 已登入測試如預期 fail → 用備份還原，非 `git checkout`）。backend 未動 1103
passed 不變；frontend 1248→1250 passed（+2 新測）、tsc 0、build OK。code-reviewer review：
Approve，0 must-fix、0 should-fix、2 nice-to-have（CSV 匯出 `window.open` 無法附帶 auth
header 屬另案，已記錄；docstring 未提 authFetch 依賴為既有慣例缺口，非本次範圍），皆未採納
（非阻塞）。`WMOM-20260923-10` 稽核清單尚餘 1 支純讀取元件：`TrendChartPanel`。）
前一 session：WMOM-20260924-05 — `WMOM-20260923-10` sub-task 5/7：`EventComparisonView.tsx`
authFetch 補齊。多風機事件比較面板 1 處裸 fetch（mount + filter 變更時 GET
`/api/maintenance/events/compare`，後端 `require_authenticated()` 任何登入者可讀）改
`authFetch`，比照姊妹 PR WMOM-20260923-07/-09/-20260924-01~04 手法。新增 2 測皆
mutation-verified。backend 未動 1103 passed 不變；frontend 1246→1248 passed（+2 新測）、
tsc 0、build OK。
前一 session：WMOM-20260924-04 — `WMOM-20260923-10` sub-task 4/7：`CostPage.tsx`
authFetch 補齊。`/admin/cost` 成本模型頁 1 處裸 fetch（mount 時 GET `/api/farms`，供
dataset/farm selector，後端 `require_authenticated()` 任何登入者可讀）改 `authFetch`，比照
姊妹 PR WMOM-20260923-07/-09/-20260924-01/-02/-03 手法。新增 2 測（已登入時 mount GET 帶
`Authorization` header；未登入時驗證過渡期行為不變），皆 mutation-verified（authFetch 改回
裸 fetch → 已登入測試如預期 fail → 用備份還原，非 `git checkout`）。backend 未動 1103
passed 不變；frontend 1244→1246 passed（+2 新測）、tsc 0、build OK。code-reviewer review：
Approve，0 must-fix（附帶說明：reviewer 過程中誤執行 `git checkout` 重置 working tree，已
自行發現並手動重建，本 session 事後獨立以 `git diff` + 全套重跑確認未受影響）。
前一 session：WMOM-20260924-03 — `WMOM-20260923-10` sub-task 3/7：`SettingsPage.tsx`
authFetch 補齊。`/admin/settings` 系統設定面板 11 處裸 fetch（5 條 GET + 6 個
`SUPERVISOR`-only 寫入）全改 `authFetch`，新增 8 測皆 mutation-verified。backend 未動
1103 passed 不變；frontend 1236→1244 passed（+8 新測）、tsc 0、build OK。）
前一 session：WMOM-20260924-02 — `WMOM-20260923-10` sub-task 2/7：`FarmSelector.tsx`
authFetch 補齊。sidebar 底部風場切換器 3 處裸 fetch（GET `/api/farms` 列表 + POST
`/api/farms/{id}/activate` 切換 + POST `/api/farms` 建立，後兩者皆 `SUPERVISOR`-only 寫入）全改
`authFetch`，比照姊妹 PR WMOM-20260923-07/-09/WMOM-20260924-01 手法。新增 4 測（已登入時 mount
GET + 切換 POST + 建立 POST 皆帶 `Authorization` header；未登入時驗證過渡期行為不變），皆
mutation-verified（sed 改回裸 fetch → 3 測如預期 fail、未登入測試維持 pass → 已還原）。
code-reviewer review：0 must-fix、0 should-fix、2 nice-to-have（皆記錄性說明，不需改動），
Approve。backend 未動 1103 passed 不變；frontend 1232→1236 passed（+4 新測）、tsc 0、build OK。
`WMOM-20260923-10` 稽核清單尚餘 5 支：`SettingsPage`（含 SUPERVISOR 寫入，優先）>
`CostPage`/`EventComparisonView`/`HistoryPage`/`TrendChartPanel`（純讀取，風險較低）。）
前一 session：WMOM-20260924-01 — `WMOM-20260923-10` sub-task 1/7：`FaultInjectionPanel.tsx`
authFetch 補齊。`/admin` 故障模擬頁 6 處裸 fetch（GET scenarios/test-plans/active + POST
inject/clear/test-plans-run，後 3 個皆 `SUPERVISOR`-only 寫入）全改 `authFetch`，比照姊妹 PR
WMOM-20260923-07/-09 手法。新增 5 測（已登入時 mount 3 GET + 3 寫入端點皆帶 `Authorization`
header；未登入時驗證過渡期行為不變），皆 mutation-verified（sed 改回裸 fetch → 4 測如預期 fail
→ 已還原）。code-reviewer review：0 must-fix、0 should-fix、2 nice-to-have（皆記錄性說明，
不需改動），Approve。backend 未動 1103 passed 不變；frontend 1227→1232 passed（+5 新測）、
tsc 0、build OK。）
前一 session：WMOM-20260923-09 — `WMOM-20260507-02` sub-task b：`TurbineDetail.tsx`
PageHeader「停機」鈕接上 `POST /api/control/command { command: 'stop' }`（走 `authFetch`）。
認領時追查右側「操作控制」卡片（`OperatorControlCard`）本身 4 處既有 `fetch`（GET status 輪詢 +
POST command + POST curtail ×2）全裸 `fetch` 未帶 `Authorization` header，且 command/curtail
兩端點皆 `require_role(SUPERVISOR)`——風險高於先前 WMOM-20260923-08 的 farm-trend（純讀取），
enforce 開啟後操作控制面板會整面失效；同次一併修復 4 處。新增 7 測皆 mutation-verified（逐一
退回裸 `fetch` 確認對應測試 fail，含此前完全未被鎖住的 `clearCurtail` 缺口）。code-reviewer
review：0 must-fix，1 should-fix（`ISSUES.md` 父 issue `WMOM-20260507-02` checklist 未同步
勾選）已採納，1 nice-to-have（既有 `resp.ok` 缺錯誤處理，非本次引入的既有行為）未採納維持現狀，
Approve。backend 未動 1103 passed 不變；frontend 1220→1227 passed（+7 新測）、tsc 0、build
OK。⚠ 稽核過程發現**另有 7 支元件同款 authFetch 缺口**（`CostPage`/`EventComparisonView`/
`FarmSelector`/`FaultInjectionPanel`/`HistoryPage`/`SettingsPage`/`TrendChartPanel`，其中
`FarmSelector`/`FaultInjectionPanel`/`SettingsPage` 含 SUPERVISOR/ADMIN 寫入），登記為新
follow-up **WMOM-20260923-10**，標記為 M6 auth cutover（`WMOM-20260716-05i`）**前置阻塞項**
（`docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表「前端所有寫入
request 都帶 token」目前不成立），未在本次修復，建議下次優先接手。）
前一 session：WMOM-20260923-07 — `WMOM-20260507-02` sub-task a：風場總覽「匯出」鈕接線。
清單第一項先前是零功能 placeholder，本次接 `GET /api/export/snapshot`（後端
`require_authenticated()` 閘門）：`handleExportSnapshot` 走既有 `authFetch`（正確帶
Authorization header）→ `resp.blob()` → 沿用 reporting module 既有 `downloadBlob` 工具觸發下載
`farm-snapshot-{YYYY-MM-DD}.json`，失敗僅 `console.error`（沿用劉老師既有決定不彈 alert）。新增
4 測皆 mutation-verified。code-reviewer review：0 must-fix，2 should-fix 全數採納（happy-path
原測試無法區分 `authFetch` 與裸 `fetch`，補專測直接斷言 header 並 mutation-verified；一則誤導性
測試註解已更正）+ 3 nice-to-have（同檔案 farm-trend fetch 同款缺口登記為新 follow-up
`WMOM-20260923-08`、不阻塞），Approve。backend 未動 1103 passed 不變；frontend 1216→1220
passed（+4 新測）、tsc 0、build OK。`WMOM-20260507-02` 清單尚餘 b~f，皆已有明確 API/估時可續接。）
前一 session：WMOM-20260716-06 — footprint CPU-torch pin：多個 session 因「本地無 docker
daemon」擱置的 follow-up，本次 preflight 發現本 sandbox 這次可手動啟動 dockerd 成功，接手實測
收尾。Dockerfile 新增 1 行 CPU-only torch wheel pin，真實 docker build/run 驗證 image
3.37GB→550MB（省 ~2.8GB）+ app 正常開機 `/api/health` 200 OK，code-reviewer review 0 must-fix。
附帶重新調查 WMOM-20260509-F6（PostgreSQL row-lock test），判定範圍遠比原估「0.5 工作天」大
（repo 完全無 Postgres 連線路徑，需先有架構決策），更正估時並標記 🟡 需劉老師決策、本次不接。
backend/frontend 測試數量不變（純 Dockerfile 變更，CI 不 build image）。）
前一 session：WMOM-20260923-06 — 情境比較分析 A2 Part 4：跨情境差異圖：DEC-20260720-02
A2 epic 完整範圍至此全數完成，判定差異圖不需後端、純前端分桶重採樣解決多情境序列取樣點不對齊
問題，frontend 1171→1216 passed（+45 新測）。詳見 ISSUES.md WMOM-20260923-06。）
前一 session：WMOM-20260923-05 — `Sidebar.tsx` component render 測試：前一 session
（WMOM-20260923-04）逐檔評估 `components/ui/*.tsx` 時點名 `Sidebar.tsx`（220px 主導覽，294
行，全站唯一主導覽入口，先前完全零 `__tests__`）範圍較大另開一支，本次接手。新增 23 測（
primary/secondary 導覽項目/badge/active 樣式、backend 健康狀態 dot、lang/theme 切換按鈕、
footerExtra、mobile drawer 響應式行為），5 個關鍵分支 mutation-verified，零 production 變更。
code-reviewer review：1 must-fix（work-log 缺 Implement/Verify/Review/Wrap-up 段落，已補齊）
+ 2 should-fix 全數採納（主題切換測試補 `localStorage.clear()` 避免同檔案 isolation 洩漏；
backend 健康狀態 dot 測試改用 `getByText` scope 查詢避免誤中 theme 按鈕圖示的同款 `aria-hidden`
屬性）+ 1 nice-to-have 未採納，Approve。backend 未動 1103 passed 不變；frontend 1148→1171
passed（55→56 files）、tsc 0、build OK。`components/ui/*.tsx` 9 支 primitive 檔案測試評估至此
全數完成。⚠ 附帶提醒：canonical routine 文件 `docs/routines/autonomous-daily-worker-prompt.md`
仍停在 v3（baseline 638/59），已落後於本次 cron 送入的 v4.1（baseline 1076/970），建議劉老師
找時間同步。）
前一 session：WMOM-20260923-04 — `components/ui` primitives（`StatusPill`/`Charts`）
測試補齊：9 支 UI primitive 檔案（`Btn`/`Card`/`Charts`/`Field`/`Logo`/`PageHeader`/`Sidebar`/
`Stat`/`StatusPill`，1220 行）先前完全零 `__tests__`（前兩個 session 都點名「尚未評估是否需要」），
本次逐檔讀過評估：`Btn`/`Card`/`Field`/`Stat`/`PageHeader` 純展示型、已被全站既有 page-level
測試間接覆蓋，ROI 低；`Logo`/`Sidebar` 範圍較大（`Sidebar` 有 mobile drawer + badge + 多個
responsive 分支）另開一支；`StatusPill.tsx`（3 支狀態顏色映射純函式）+ `Charts.tsx`
（`MiniSparkline`/`BigChart`/`HealthBar` SVG path 數學 + clamp + 顏色門檻）值得補測試，新增
48 測，6 個關鍵分支 mutation-verified，零 production 變更。code-reviewer review：0 must-fix，
2 should-fix 全數採納（issue 補登記進 ISSUES.md/STATUS.yaml；docstring 用詞澄清為本 repo 首次
引入此測試模式）+ 1 nice-to-have 採納（`BigChart` events 測試改精確 `cx` 座標斷言），Approve。
backend 未動 1103 passed 不變；frontend 1100→1148 passed（53→55 files）、tsc 0、build OK。
⚠ 附帶發現：`STATUS.yaml` 的 `last_updated` 欄位目前不是合法 YAML（`yaml.safe_load` 會拋錯，
確認 main 本來就如此、非本次造成，repo 內無任何程式實際解析這個檔案，故不影響 CI/自動化，本次
維持既有格式慣例續寫未修復，詳見 work-log 附帶發現段落）。）
前一 session：WMOM-20260923-03 — 情境比較分析 A2 Part 3：跨情境相對時間對齊時序疊圖：
連續兩個 session 把此項標成「需要新後端端點」而延後，本次判定不需要——既有單情境 history 端點
+ 前端已持有的 `sim_start` 就足以純前端算相對時間對齊，零後端變更（決策翻案見
`docs/product/decision_log.md` DEC-20260923-01）。新增 `ScenarioCompareTimelineView.tsx`
（機組+指標選擇器疊圖，`ScenarioCompareAcrossView` 新增頁籤承載），只做疊圖、差異圖（Part 4）
留給下次。code-reviewer review 抓到 1 must-fix（decision_log 補件）+ 2 should-fix（tooltip 精確
比對 caveat 說明、fetch 失敗獨立提示）皆已修復，frontend 1067→1100 passed，backend 未動。）
前一 session：WMOM-20260923-02 — `FaultInjectionPanel` component render 測試：555 行的
`/admin` 故障模擬頁面元件先前零 component 測試，比照 `TrendChartPanel`/`SettingsPage` 範式（fetch
mock + fake timers）補上 40 測（PageHeader/注入參數 Fields/inject·clear all/活躍故障表/診斷
測試計畫卡片/執行測試計畫+結果卡/3s 輪詢與 unmount cleanup），frontend 1027→1067 passed，
backend 未動；`MaintenanceHub`/`FaultInjectionPanel` 同批 untested 大元件兩支皆已處理完畢。
session #8：WMOM-20260923-01 — `MaintenanceHub` component render 測試：439 行的
`/admin/maintenance` 頁面元件先前零 component 測試，補上 49 測（PageHeader/Filter/
WorkOrderTable 全欄位/RosterCard/WeekCalendar），frontend 978→1027 passed，backend 未動；
PR #164（WMOM-20260922-04）確認 auto-merge 成功，累積連續 3 筆 CI 綠燈樣本，已清除上方舊
CI 失效警語。
session #7：WMOM-20260922-04 — 情境比較分析 A2 Part 2 前端：
`ScenarioCompareAcrossView`（跨情境風場層 rollup 摘要並排）+ `ScenarioPage` 勾選/比較 UI，
frontend 961→978 passed（+17 新測，含開發中自行抓到並修正的 2 個真實 bug），backend 未動。
session #6：WMOM-20260922-03 的 PR #162 **CI 全綠、auto-merge
自動合併**（非人工）——CI runner 基礎設施疑似恢復，見上方新警語；本次僅更正追蹤檔案的 CI 狀態敘述，
無程式碼變更。session #5：WMOM-20260922-03 — 情境比較分析 A2 Part 1：跨情境
摘要並排端點 `GET /api/scenarios/compare`（DEC-20260720-02），backend 1094→1103 passed，frontend
未動；session #4：WMOM-20260922-02 — PR D：`GuidedTourPage` inline
component remount 修（DEC-20260720-01），frontend 960→961 passed；session #3：WMOM-20260720-13
A1 round-2 follow-up 4 個 Should-fix 全修（PR #157 merged）；session #2：WMOM-20260922-01
accelerated 模式 stop() 響應性收尾（PR #158 merged）；session #1：WMOM-20260720-04 + -08 live/OPC
後端硬化收尾——M6 現場部署唯一硬阻塞已清除。）

> ⚠ 本檔其餘內文（現況段落、下方清單）大多還停在 2026-07-18 的狀態快照，比 `STATUS.yaml` / `ISSUES.md`
> 舊很多（M5 已到 ~90%、M6 已到 auth+live/OPC 硬化完成）。下次整理 TODO 時建議整份對照 `ISSUES.md`
> 「🎯 未來大目標」區塊重寫，而非逐次小補丁——本 session 範圍只做 WMOM-20260922-03，不在此展開。

---

## 現況（2026-07，內容已過時，見上方提醒）

- **M1-M4 全 done**：monitoring（既有）+ cost（M2）+ workflow（M3-M4）+ reporting（M4）皆完成；**M5（Knowledge/RAG + 現場 mobile UI）進行中 ~75%**（主功能到齊，剩客戶手冊擴充 + 一年警報 csv 灌入，屬 M6 部署期）；**M6-4 auth 模組已完成**（JWT + RBAC + 全 router 授權已全面強制執行 + 前端真登入頁面與 AuthProvider已對接）。
- **baseline 綠**：backend 全套（6 module + monitoring/physics + e2e）→ **1103 passed / 7 skipped / 1 xfailed**；frontend vitest **1027 passed** / tsc 0 / vite build OK。CI runner 基礎設施已確認恢復穩定（見上方）。
- **節奏提醒**：autonomous 飛輪已重啟（每 3 小時），挑題準則為「對 M6 critical path 有貢獻優先」。

---

## 下一個 milestone — M5：Knowledge / RAG + 現場 mobile UI（2026-09 target）

> 目標：警報 → RAG 查 Z72 手冊 → 給現場工程師可操作的處置建議；現場 mobile UI 是 PMF 關鍵。
> Done criteria：現場工程師手機掃到警報，能查到對應手冊段落 + 處置步驟。

詳細 epic 拆解見 [`ISSUES.md`](ISSUES.md) 頂部「🎯 未來大目標」。

### 可立即接手（autonomous-friendly，無設計歧義）

- [x] ~~**前端 component render 測試**（jsdom setupFiles / jest-dom / CostPage / FarmOverview / workflow Panel / MaintenanceHub / FaultInjectionPanel 皆已補齊，同批 untested 大元件已全數處理完畢）~~ —— `components/ui/*.tsx` 原 9 支 primitive（`StatusPill`/`Charts`/`Sidebar` 已補測試，其餘 6 支 `Btn`/`Card`/`Field`/`Stat`/`PageHeader`/`Logo` 判定 ROI 低暫不動）+ 之後新增的 `ScenarioMountBanner`（✅ WMOM-20260926-05 完成，見上方「最後更新」）測試評估至此**全數完成**；`FaultInjectionPanel.test.tsx` review 留下的 `.parentElement` DOM 遍歷 scoping 技術債（見 ISSUES.md WMOM-20260923-02）可留待日後統一改用 `data-testid`
- [x] ~~**情境比較分析 · A2 Part 4（差異圖）**~~ — ✅ WMOM-20260923-06 完成，DEC-20260720-02 A2 epic
  完整範圍（摘要並排＋疊圖＋差異圖）至此全數完成。ScenarioCompareTimelineView review 留下的
  recharts 跨線 tooltip 精確比對 caveat 仍是已知限制（非阻塞，見該頁籤底部說明文字）。
- [x] ~~**PR C 子設計**~~ — ✅ 2026-09-26 完成（`WMOM-20260926-02`）：拒絕 DEC-20260720-01
  原案（broker 新增情境檢視來源狀態），改採與 broker 正交的唯讀端點 + 前端
  `ScenarioMountContext` 方案，見 `docs/product/decision_log.md` `DEC-20260926-01`。
- [x] ~~**WMOM-20260926-03** — PR C Phase 1 實作（情境掛載唯讀端點 + FarmOverview/
  TurbineDetail 接線）~~ — ✅ 2026-09-26 完成，見上方「最後更新」。`DEC-20260720-01`/
  `DEC-20260720-02` 的 PR C 至此完整收尾（Phase 2 deferred）。
- [x] ~~**WMOM-20260716-06** — footprint CPU-torch pin~~ — ✅ 2026-09-23 完成，image
  3.37GB→550MB，見上方「最後更新」。
- [x] ~~**WMOM-20260507-02 sub-task a/b/c/e/f** — 風場總覽「匯出」/風機細節「停機」/風機
  細節「限載」/維護中心「+ 新工單」/風場總覽「+ 新報告」鈕接線~~ — ✅ WMOM-20260923-07（a）+
  WMOM-20260923-09（b）+ WMOM-20260925-02（c）+ WMOM-20260925-03（e）+
  WMOM-20260925-04（f）完成，見上方「最後更新」。**`WMOM-20260507-02` 清單僅剩 d**
  （風機細節 `安排檢查`——依賴的 WMOM-20260505-22 `inspection_schedule` 後端已於
  2026-09-25 完成，**依賴已解除**，但前端本身尚未接線，見下方 WMOM-20260925-05；
  f 判定不需重造 modal，改導向既有 `/admin/reports` 頁，見 WMOM-20260925-04
  completion summary）
- [x] ~~**WMOM-20260923-08** — `FarmOverview.tsx` farm-trend fetch 補 `authFetch`（一致性
  技術債）~~ — ✅ 2026-09-24 完成，見上方「最後更新」。`FarmOverview.tsx` 全檔至此無裸
  `fetch` 殘留。
- [x] ~~**WMOM-20260923-10**（M6 auth cutover 前置阻塞）— 前端 authFetch 稽核（7 支元件）~~ —
  ✅ 2026-09-24（WMOM-20260924-01~07）全數完成並標 done，
  `docs/product/WMOM-20260716-05_auth_enforcement_plan.md` §6 cutover 檢查表「前端所有寫入
  request 都帶 token」已勾選。**⚠ 但該稽核指令未遞迴子目錄，實際並未窮盡**——見下方
  WMOM-20260924-08。
- [x] ~~**WMOM-20260924-08**（M6 auth cutover 前置阻塞）— `MyOrdersMode.tsx` authFetch
  缺口~~ — ✅ 2026-09-25 完成，見上方「最後更新」。`components/field/` 全樹至此無裸
  `fetch` 殘留。
- [x] ~~**WMOM-20260925-01**（M6 auth cutover 真正前置阻塞）— `frontend/hooks/*.ts`
  authFetch 稽核缺口~~ — ✅ 2026-09-25 完成，見上方「最後更新」。4 支 hook + `App.tsx`
  一次做完，`frontend/` 全樹至此無裸 `fetch` 殘留；cutover 檢查表已重新勾選。
- [x] ~~**WMOM-20260925-02**（`WMOM-20260507-02` sub-task c）— `TurbineDetail.tsx` header
  『限載』鈕接線~~ — ✅ 2026-09-25 完成，見上方「最後更新」。
- [x] ~~**WMOM-20260925-03**（`WMOM-20260507-02` sub-task e）— `MaintenanceHub.tsx`
  header『+ 新工單』鈕接線~~ — ✅ 2026-09-25 完成，見上方「最後更新」。
- [x] ~~**WMOM-20260925-04**（`WMOM-20260507-02` sub-task f）— `FarmOverview.tsx`
  header『+ 新報告』鈕接線~~ — ✅ 2026-09-25 完成，見上方「最後更新」。判定不需重造
  modal，改導向既有 `/admin/reports` 頁。`WMOM-20260507-02` 清單僅剩 d（依賴
  WMOM-20260505-22，持續卡著）。
- [x] ~~**WMOM-20260505-22**（`WMOM-20260507-02` sub-task d 的阻塞依賴）— `inspection_schedule`
  定檢計畫 + scheduler auto-spawn 後端~~ — ✅ 2026-09-25 **後端**完成（domain + repository +
  service + router，79 測 mutation-verified，code review 1 must-fix + 1 should-fix 皆已修
  復），見上方「最後更新」。**前端未做**，拆成新 issue，見下一項。
- [x] ~~**WMOM-20260925-05**（`WMOM-20260507-02` sub-task d 本體）— `inspection_schedule` 前端~~ —
  ✅ 2026-09-25 完成，見上方「最後更新」。`WMOM-20260507-02` 6 個 sub-task 全數完成，該 issue
  已標 done。
- [x] ~~**WMOM-20260505-21** — `day_work_form` 員工日誌後端~~ — ✅ 2026-09-26 **後端**完成
  （domain + repository + router + schemas，55 測 mutation-verified，code review 1
  must-fix + 2 should-fix 皆已修復），見上方「最後更新」。**前端 + work_order.finish()
  hook + 讀取端點 ownership 限制未做**，拆成新 issue，見下一項。
- [x] ~~**WMOM-20260926-01 第 1 項**（`WMOM-20260505-21` 收尾）— day_work_form
  前端頁面（`/admin/workflow` 工作日誌 tab，本人專用）~~ — ✅ 2026-09-26 完成，見上方
  「最後更新」。
- [x] ~~**WMOM-20260926-01 剩餘 2 項** — work_order.finish() 自動寫入 hook + 讀取端點
  ownership 限制~~ — ✅ 2026-09-26 兩項皆完成（第 3 項第三個 session、第 2 項第四個
  session），見上方「最後更新」。`WMOM-20260926-01` 三項全數完成，該 issue 已標 done。

### 需劉老師決策才能開工

- [ ] **WMOM-20260509-F6** — PostgreSQL row-lock integration test：2026-09-23 重新調查後更正——
  repo 完全無 Postgres 連線路徑（engine 建構/transaction-begin/migration 皆 SQLite 專屬語法，
  無 psycopg2 依賴，decision_log 無任何 postgres 決策），需先拍板「M6 是否真的選 PostgreSQL
  backend」才能動工，非 0.5 天小題，詳見 ISSUES.md 該 issue 條目
- [ ] **WMOM-20260519-01** — `add_return` 超量退料 domain guard（需會計語意決策）
- [ ] **WMOM-20260513-01** — UI 改版 v2（placeholder — 等劉老師補新設計交接書）

### 客戶接觸（持續）

- [ ] **WMOM-20260503-05** — Friendly 客戶接觸名單（infrastructure done；待劉老師執行 cold email + 約 demo）

---

## 物理模型強化（park 到有需要再評估的學術深度題）

> 既有 18/21 quality check 已通過，非 must-have；商業 demo 不依賴這些。

- [x] ~~**WMOM-20260505-23** — Physics 自我驗證框架（7 層 validator + health check CLI）~~ —
  ✅ 2026-05-06 完成（本清單過時未勾）
- [x] ~~**WMOM-20260505-24** — Data quality 3 項 fail 修正~~ — ✅ 2026-09-27 完成
  （本清單過時未勾）
- [ ] **WMOM-20260505-25** — Frontend RUL + 多 band alarm 視覺化 —
  **Part A（RUL 倒數 + 疲勞警報 badge + 累積損傷比例）已於 2026-09-28 完成
  （`WMOM-20260505-25-a`）**；剩 SpectralAlarmPanel（5-band 頻譜）/
  BearingDiagPanel（BPFO/BPFI）/ RUL 觸發時間軸
- [ ] WMOM-20260505-26/27/28 — SCADA tag 擴充 / 保護電驛協調 / 單齒 defect signature

---

## Parking lot（不在當前 milestone）

- M6 之後：windAILab AI 故障診斷 HTTP API 介接（Enterprise 套餐，另一公司業務、走 API）
- M6 之後：InduSpect AI 視覺定檢介接
- M6 之後：第二個 OEM PLC adapter（Vestas / SGRE）
- M5 之後：RAG_Ultimate Phase 3 升級（chunking 策略、評估指標）
- 物理模型升級：新 issue 從 `docs/legacy/digiwt_TODO.md` parking lot 找

---

## 已封存的歷史 TODO（digiWT 階段）

`docs/legacy/digiwt_TODO.md` ← 既有 244 條物理 / SCADA / fatigue / wake 細節改進清單。
未來如要動 monitoring 層，先翻這份找 reference，**不要重複造輪子**。
