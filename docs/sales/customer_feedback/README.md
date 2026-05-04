# Customer Feedback — windMindOM friendly 客戶 demo / 訪談紀錄

> 對應 issue：WMOM-20260503-05
> 用途：每場 demo / 訪談後**24 小時內**寫紀錄，作為 M3-M5 設計 input。

---

## 為什麼要做這個

第一個目標是**收集真實 pain points 餵 M3-M5 設計**，不是備忘錄。
寫紀錄的時候要想：

1. 對方說的哪些痛點，是 windMindOM 5 modules **已涵蓋**的？
2. 哪些痛點是 **roadmap 內但還沒做**的？對方期待的優先序為何？
3. 哪些痛點是 **roadmap 外**的？要不要列為 M6+ 候選？
4. 對方對 simulator demo 的反應 — 真的覺得 killer 嗎，還是「噢，挺有趣」這種禮貌敷衍？
5. 預算反應 — 對「比少請半個工程師便宜」的錨點是接受、嫌貴、嫌便宜（懷疑品質）？

---

## 檔名格式

```
YYYY-MM-DD-{客戶代號}.md
```

- `YYYY-MM-DD`：demo 當天日期
- `客戶代號`：3-6 字母英文代號（避免直接用公司名 — 屬於敏感資訊）
  - 例：`tpc-formosa1`、`bachmann-tw`、`xyz-om`

範例：`2026-05-15-tpc-formosa1.md`

---

## 模板使用方式

```bash
cp _TEMPLATE.md YYYY-MM-DD-{客戶代號}.md
# 編輯填入內容
```

---

## 隱私 / Git 規則

- **`_TEMPLATE.md`、`README.md` 入 git**（公開模板）
- **具名場次紀錄（`YYYY-MM-DD-*.md`）不入 git**（已在 root `.gitignore`）
- 如果要分享某次 feedback 給共同創辦人 / 投資人，**用匿名化版本**：客戶代號改成
  `Customer-A`、刪掉個人姓名，再 export 為單一 PDF 寄送

---

## M1 結束時的盤點問題

如果 M1 月底有 1+ 場 demo done：

- [ ] 客戶 most-painful 那 1 件事，windMindOM 5 modules 哪一個能解？
- [ ] 客戶提到的「原來不知道你們有 X」是哪個 feature？要不要在 deck 裡放更前面？
- [ ] 客戶提到的「我們現在用 Y 工具」是哪些？需不需要更新競品矩陣？
- [ ] 客戶覺得 simulator demo 是 killer 還是 nice-to-have？影響 M5 sales narrative
- [ ] 客戶對 NT$2-4M 預算的反應？影響 M6 合約定價
