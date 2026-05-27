# 2026-05-27 — CI/baseline 技術債清理：requirements-dev + cost pinned 容差比對

> Autonomous daily worker session（2026-05-27 20:00 Asia/Taipei，雲端 sandbox）。
> Issue：**WMOM-20260527-01**（新開）。Branch：`claude/upbeat-davinci-svpIQ`。

---

## 1. 為什麼做這個

開工 preflight 跑 baseline 就撞到兩個反覆出現的環境 blocker：

1. **requirements.txt 未列 test/部分 runtime 依賴** → 新 sandbox 跑 `pytest` 直接
   `No module named pytest`，接著一路缺 `sqlalchemy` / `pandas` / `reportlab` / `jinja2`，
   全靠手動 `pip install` 補裝。5/22、5/24、5/26 三次 wrap-up 都記了這條。
2. **cost 模組 3 個 pinned 數字測試在本 sandbox 必紅**：
   - `test_var_fluct.py::test_varfluct_year_1_pinned`
   - `test_monte_carlo.py::test_mc_percentiles_pinned`
   - `test_cost_api.py::test_monte_carlo_k13_seed_42`

   差異都在 float64 **最後一位**（如 `preventive: 3909712.3287671236` vs pin `...671230`；
   `cost p10: 64947395.46655479` vs pin `...5548`）。

   **root cause 確認**：pin baseline 在 Windows 量測；雲端 sandbox 是 Linux + OpenBLAS。
   實測 `numpy 1.26.4` 與 `numpy 2.4.6` 在 Linux 下**都**與原 Windows pin 有最後一位差異
   → 不是單純 numpy 版本問題，是跨平台 BLAS 累加順序的 ULP drift。嚴格 `==` 比對讓
   「程式碼零變動也紅燈」，5/22 起已被記為 pre-existing。

這正是 5/26 handoff §5 + §6 明確點名、列為下次「順手清的小工」的技術債（STATUS.yaml
next_milestone 也列了「requirements-dev.txt + numpy pin 小工」）。它是唯一無設計歧義、
完全 autonomous、單 session 可完工、且能**一次止住所有後續 session 的 CI 紅燈**的工。

> 決策樹：M4 已 100%；WMOM-20260504-12 等劉老師本機 24h 記憶體長跑驗收（非我可推進）；
> WMOM-20260519-01 退料超量 guard 需劉老師決定會計語意。本技術債優先級最高（決策樹第 1 條
> known blocker：它擋住每個 daily session 的乾淨 baseline）。

---

## 2. 完成內容

### 2.1 依賴宣告補齊

- **requirements.txt**（runtime）補先前漏列、但 app 實際 import 的：
  `sqlalchemy>=2.0`（workflow/cost/reporting ORM）、`pandas>=2.0`（cost waiting_time）、
  `reportlab>=4.0`（reporting PDF）、`jinja2>=3.1`（reporting 模板）。
- **requirements-dev.txt**（新）：`-r requirements.txt` + `pytest>=8.0` /
  `pytest-asyncio>=0.23` / `httpx>=0.27`（TestClient 後端）。新 sandbox / CI 一鍵就緒。
- 查證：`aiosqlite` / `openpyxl`（5/26 note 曾列）實際**全 repo 無 import**，不列入。

### 2.2 cost pinned 測試改容差比對

新增 `modules/cost/tests/pin_tolerance.py`：

- `pin_approx(expected)` → `pytest.approx(expected, rel=1e-9, abs=1e-6)`（給 direct-assert 風格）
- `pin_equal(actual, expected)` → `math.isclose(rel_tol=1e-9, abs_tol=1e-6)`，非數值退回 `==`
  （給 loop-accumulate 風格，保留一次回報所有 drift 欄位的行為）

**tolerance 設計**：`rel_tol=1e-9` 仍守住 **9 位有效數字** —— 任何真實 ECN regression
（漏項 / 公式錯 / 單位錯）量級都遠大於此，攔截能力不變；只吸收平台 float 噪音（~1e-15）。
`abs_tol=1e-6` 處理近零 pinned 值（如 `corrective_bop=0.0`，rel_tol 對 0 無效）。

套用範圍（5 檔）：

| 檔案 | 風格 | 改法 |
|---|---|---|
| `test_var_fluct.py` | loop | 6 處 `if actual != expected` → `if not pin_equal(...)` |
| `test_monte_carlo.py` | loop | 3 處同上 |
| `test_k13_equivalence.py` | loop | 2 處同上（含 print 的 OK/DRIFT 判定）+ 檔頭 docstring 更新 |
| `test_cost_api.py` | assert | 全精度 pinned 改 `== pin_approx(...)` |
| `test_adapter.py` | assert | 同上 |

**刻意保留 exact `==`**：整數（year / index / n_simulations / seed）、`failure_multiplier`
（1.5 / 2.0 / 3.0，exact）、engine 內 `round()` 過的值（summary npv round 2 位、
lifetime_availability round 6 位）、整數值金額（`capex_total=650000000.0`、`fixed_cost=5550000.0`）
—— 這些跨平台確定性，不需 tolerance（加了也只是 no-op 噪音）。

---

## 3. Verify（zero regression / 跨版本驗證）

- **cost 測試**：`numpy 1.26.4` → 84 passed / 1 xfailed；切到 `numpy 2.4.6` → **同樣 84 passed**。
  → 證明容差修法在原本會 fail 的兩個 numpy 版本下都 robust。
- **完整 backend baseline**：`pytest modules/{workflow,cost,reporting}/tests/`
  → **568 passed / 1 xfailed**，**3 個 numpy drift 失敗已消除**。
  唯一剩的 fail `test_concurrent_dispatch_one_loses_when_stock_short` 是既有 SQLite WAL
  並發 flaky（單跑通過已驗證，與本 PR 無關 —— 本 PR 只動 cost 測試 + requirements，
  完全沒碰 workflow dispatch）。
- 相較先前 baseline（本 sandbox 永遠 3 紅），本 PR 是**嚴格改善**：zero regression + 消 3 紅。

---

## 4. Code review

跑 `code-reviewer` subagent 對 staged diff：**0 must-fix / 4 should-fix / 1 nice-to-have，Approve**。
reviewer 核心結論：tolerance 設計（rel_tol=1e-9 / abs_tol=1e-6）對金額/比率/LCOE 三類數字
全部合理；bool 與 numpy float64 型別判斷無功能 bug；round() 後確定性假設安全
（最小 rounding margin 5e-7 vs ULP 1.11e-16，比值 ~4500x，安全）；requirements 拆分正確。

### 4.1 採納情形（全採納，皆為文件/語意清晰度，無邏輯變動）

| # | 級別 | 內容 | 處置 |
|---|---|---|---|
| 1 | should | `pin_equal` 的 int/bool/numpy 型別判斷路徑未在 docstring 說明 | **採納**：`pin_equal` 加 Notes 說明三條型別邊界（Python int 走 isclose、numpy.int64 走 strict ==、bool 不建議用） |
| 2 | should | loop 對 failure_multiplier/year 等精確值也套 pin_equal，與「保留 exact ==」意圖看似不一致 | **採納（集中式）**：module docstring 加「容差是 `==` 的 superset」設計取捨段，說明 loop 一律套容差安全、direct-assert 保留 == 是可讀性訊號，兩者並存刻意（比逐檔加註解更乾淨） |
| 3 | should | cost_api（strict ==）與 var_fluct（pin_equal）對同批 summary 圓整值策略不同 | **採納**：同 #2 的 superset 段一併解釋 |
| 4 | should | httpx 分類 + pytest-asyncio 相容性 | **採納（修正版）**：查證**全測試套件無任何 async test**（async 只在 FastAPI router，TestClient 同步驅動）→ `pytest-asyncio` 是我多裝的 dead weight，**直接移除**（而非加「預留」註解）；httpx 確認為測試專用（TestClient 後端，production 用 uvicorn 不需），保留在 dev 並改清楚註解 |
| 5 | nice | `pin_approx` 回傳型別 `Any` | **採納**：docstring 註明「pytest 未正式 export ApproxBase 型別」 |

採納後重跑 cost 測試：**84 passed / 1 xfailed**（docstring/註解變動，零邏輯影響）。
移除 pytest-asyncio 後完整 backend 重跑 567 passed（差異僅 flaky concurrency 測試本次多跳一個，
單跑 14 dispatch tests 全綠已驗證）。

---

## 5. 下次 session 接手建議

- 本 PR 後，新 sandbox 開工只需 `pip install -r requirements-dev.txt` 即可跑全部測試，
  且 cost pinned 測試不再因平台 float drift 紅燈。
- flaky 並發測試（`test_concurrent_dispatch_one_loses_when_stock_short`）仍是 SQLite WAL
  限制，真語意驗證見 WMOM-20260509-F6（PostgreSQL row-lock）；非阻塞。
- 候選工：WMOM-20260519-01（需劉老師會計語意決策）/ WMOM-20260513-02 demo orchestrator /
  擴大 frontend 元件層測試（CostPage / FarmOverview）。

---

## 6. 檔案異動清單

```
新增  modules/cost/tests/pin_tolerance.py      （pin_approx / pin_equal helper）
新增  requirements-dev.txt                      （-r requirements.txt + pytest/asyncio/httpx）
改    requirements.txt                          （補 sqlalchemy/pandas/reportlab/jinja2 runtime）
改    modules/cost/tests/test_var_fluct.py      （6 處 pin_equal）
改    modules/cost/tests/test_monte_carlo.py    （3 處 pin_equal）
改    modules/cost/tests/test_k13_equivalence.py（2 處 pin_equal + docstring）
改    modules/cost/tests/test_cost_api.py       （pin_approx）
改    modules/cost/tests/test_adapter.py        （pin_approx）
改    work-logs/2026-05/2026-05-27-ci-baseline-pin-tolerance.md（本檔）
改    ISSUES.md / STATUS.yaml
```
