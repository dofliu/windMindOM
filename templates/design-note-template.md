# Design Note: {主題}

> 從既有 repo（如 z72_etech）讀程式取材後的 design notes。
> 用途：把舊系統的設計搬進 windMindOM 前的中介產物。
> 路徑：`docs/design_notes/{slug}.md`

---

## 1. 來源

- **Repo**: 來源 repo 名稱
- **Path**: 來源檔案路徑（相對於 repo 根）
- **Stack**: 來源技術 stack（如 Vue 2 + element-ui + Koa）
- **Author of original**: 如果可考
- **Date scanned**: YYYY-MM-DD

## 2. 模組角色

這個模組在原系統中的角色、輸入輸出、誰用它。

## 3. 資料模型

### 3.1 資料表

| 表名 | 主鍵 | 主要欄位 | 用途 |
|-----|------|---------|------|
| ... | ... | ... | ... |

### 3.2 ER 關係（用 mermaid 或 ASCII）

```
{ER 圖}
```

## 4. 狀態機（如適用）

```
{狀態機 diagram}
```

每個 transition 的條件 / 觸發者 / 副作用。

## 5. 主要流程（用 sequence diagram）

```
{流程圖}
```

## 6. 業務邏輯重點

- 規則 A
- 規則 B
- 邊界情境（edge case）

## 7. windMindOM 重寫對照

| 原 | windMindOM 版 | 變動原因 |
|---|--------------|---------|
| ... | ... | ... |

## 8. 已知不對的地方 / 想丟掉的設計

- 設計 X 在 windMindOM 不採用，因為 ...

## 9. Open questions（要與用戶 walkthrough 確認）

- ?
- ?
- ?

## 10. References

- 來源檔案逐個列出
- 相關 PR / commit（如可考）
