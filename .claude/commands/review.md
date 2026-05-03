---
description: 對 git diff（vs main）跑 code review，使用 code-reviewer subagent
---

執行 `docs/routines/daily-workflow.md` 的 Phase 6.2。

## 步驟

1. 跑 `git status` + `git diff main..HEAD --stat` 看本分支動了什麼
2. 對每個檔案列出新增/修改行數
3. invoke `code-reviewer` subagent，餵以下資訊：
   - 本分支對應的 issue ID（從 work-log 摘要）
   - 修改的檔案清單與類別（module / shared / api / test / config）
   - 重點 review 項目（依 module 性質）：
     * `modules/cost/`：ECN 計算結果是否與原 K13 demo 對得上、async 處理、例外 hierarchy
     * `modules/workflow/`：狀態機 transition 完整、雙寫 idempotency、簽核權限檢查
     * `modules/knowledge/`：strategy.yaml 載入正確、ChromaDB 操作 safe、retrieval 結果格式
     * `modules/monitoring/` (digiWT 既有改動)：物理一致性、SCADA tag schema 符合
     * `tests/`：覆蓋度、async fixture 正確、假資料合理
4. 收到 reviewer 回應後，整理為 3 類：
   - **Must-fix**：當下要修
   - **Should-fix**：當下修或開 new issue
   - **Nice-to-have**：寫進 work-log §6 學到的事

## 處理 reviewer 反饋

每個 must-fix：
- 修改檔案
- 解釋為什麼這樣修

每個 should-fix：
- 問我「當下修還是開 new issue」
- 依答覆執行

每個 nice-to-have：
- 寫進 work-log §6
- 不修

修完後重跑 Phase 5 確認沒有 regression。

## 如果 review 反饋極多（> 50% 改動）

先暫停，告訴我：
- 找到的問題數
- 主要 pattern
- 建議：分次修 vs 重寫

由我決定。
