# tests/physics/reports/

> 物理自我驗證框架的「測試紀錄保存」資料夾（WMOM-20260505-23 Layer 7）。

## 目的

每次跑 `pytest tests/physics/` 或 `python tools/physics_health_check.py` 都會在這裡留下一份可追溯的紀錄，避免「跑過就忘了」、無從查歷史軌跡。

> ⚠ Layer 1 commit 期：本資料夾骨架就位，但**自動報告產生尚未實作** — 等後續 Layer 7 完成 `conftest.py` 的 `pytest_sessionfinish` hook 與 `tools/physics_baseline_update.py`。

## 規劃結構

```
tests/physics/reports/
├── _baseline/                          ← 最新 baseline（人手動 review 後 commit）
│   ├── pytest_baseline.md
│   ├── pytest_baseline.json
│   └── health_baseline.md
├── 2026/05/                            ← 按月歸檔
│   ├── 2026-05-06-1430-pytest.md
│   ├── 2026-05-06-1430-pytest.json
│   └── 2026-05-06-1500-health/
│       ├── report.md
│       ├── report.json
│       ├── baseline_diff.md
│       └── figures/
│           ├── cp_surface.png
│           ├── wake_deficit.png
│           ├── iso10816_zones.png
│           └── fault_signatures.png
└── README.md                           ← 本檔
```

## 報告檔案格式

每份報告頂端必含 YAML metadata：

```yaml
---
timestamp: 2026-05-06T14:30:12+08:00
git_commit: abc1234
git_branch: claude/issue-20260505-23-2026-05-06
git_dirty: false
python_version: 3.12.5
test_type: pytest | health_check
duration_sec: 42.3
total_pass: 87
total_fail: 0
total_warn: 2
baseline_compared: _baseline/pytest_baseline.json
baseline_drift: see baseline_diff section below
---
```

## 怎麼比對兩份報告

兩種方式：

1. **人讀**：用任何 diff 工具開兩份 `*-pytest.md`，看 markdown table 的數字差異
2. **機讀**：用 `tools/physics_baseline_diff.py {old.json} {new.json}`（之後實作），輸出統計差異 + 觸發 threshold warning

## 怎麼決定該不該更新 baseline

baseline 是「目前公認正確的物理模型輸出」。**不能自動 update**，必須：

1. 物理模型有意義變更（例：升級 Cp 模型、修正 thrust 公式）
2. 新數值經過 cross-check 確認比舊 baseline 更貼近文獻 / 真實風機
3. 跑 `python tools/physics_baseline_update.py --confirm` 手動 promote

## Retention 政策

- 近 6 個月：保留每日紀錄
- 6 個月 ~ 1 年：每月只留最後一份
- 超過 1 年：只留每年 release 對應的紀錄
- `_baseline/` 永遠保留（不適用 retention）

實作延後：retention CLI 等 Layer 7 收尾時再寫。
