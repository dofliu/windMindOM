// windMindOM v0.8.1 Onepager builder — Journal theme, A4 portrait
// 用途：給 cold email 附件用的單頁宣傳。
// 用法：node tools/pitch_deck/build_v081_onepager.js
// 輸出：docs/sales/pitch_deck_v0.8.1_onepager.pptx
//        → 用戶在 PowerPoint「另存為 PDF」轉成 onepager.pdf

const pptxgen = require("pptxgenjs");
const path = require("path");

const C = {
  cream:        "F5F1E8",
  creamLight:   "FAF7F0",
  ink:          "1F2937",
  inkSoft:      "4B5563",
  inkMuted:     "8B8378",
  greenDark:    "1F3A2E",
  greenMid:     "2D4A3E",
  greenAccent:  "5C7A6A",
  green50:      "E8EDE9",
  rule:         "C9C2B0",
};
const F = { serif: "Noto Serif CJK TC", serifEn: "Georgia" };

const pres = new pptxgen();
// A4 portrait: 8.27" × 11.69"
pres.defineLayout({ name: "A4_PORTRAIT", width: 8.27, height: 11.69 });
pres.layout = "A4_PORTRAIT";
pres.author = "DOF Lab — 劉瑞弘";
pres.title = "windMindOM v0.8.1 Onepager";

const W = 8.27;
const H = 11.69;

const s = pres.addSlide();
s.background = { color: C.cream };

// ─────────────────────────────────────────────
// 頂部 banner（暗墨綠）
// ─────────────────────────────────────────────
s.addShape(pres.shapes.RECTANGLE, {
  x: 0, y: 0, w: W, h: 1.9,
  fill: { color: C.greenDark }, line: { color: C.greenDark, width: 0 },
});
s.addText("§  NCUT  ·  DOF LAB", {
  x: 0.5, y: 0.25, w: W - 1, h: 0.3,
  fontFace: F.serifEn, fontSize: 9, color: "B3C2B6",
  charSpacing: 6, valign: "middle", margin: 0,
});
s.addText("windMindOM", {
  x: 0.5, y: 0.55, w: W - 1, h: 0.7,
  fontFace: F.serifEn, fontSize: 36, color: "F5F1E8",
  charSpacing: 2, valign: "middle", margin: 0,
});
s.addText("離岸風場運維廠商工具 · Operator-focused Wind Farm O&M Tool", {
  x: 0.5, y: 1.25, w: W - 1, h: 0.4,
  fontFace: F.serif, fontSize: 14, color: "DCE3DD",
  charSpacing: 4, valign: "middle", margin: 0,
});

// ─────────────────────────────────────────────
// Tagline 區
// ─────────────────────────────────────────────
s.addText(
  "在一個 UI 看到 SCADA、庫存派工、成本計算、警報手冊查詢 — 取代你現在的 Excel + LINE + 紙單。",
  {
    x: 0.5, y: 2.05, w: W - 1, h: 0.6,
    fontFace: F.serif, fontSize: 12, color: C.ink,
    italic: true, valign: "middle", margin: 0,
  }
);
s.addShape(pres.shapes.LINE, {
  x: 0.5, y: 2.7, w: W - 1, h: 0,
  line: { color: C.greenAccent, width: 0.75 },
});

// ─────────────────────────────────────────────
// 5 modules 一橫排（簡化版）
// ─────────────────────────────────────────────
s.addText("§  FIVE MODULES  /  五大模組", {
  x: 0.5, y: 2.85, w: W - 1, h: 0.3,
  fontFace: F.serifEn, fontSize: 10, color: C.greenMid,
  bold: true, charSpacing: 6, valign: "middle", margin: 0,
});

const mods = [
  { t: "監控\nSCADA", b: "Z72 PLC + 物理模擬器" },
  { t: "庫存派工", b: "工單 + 多階簽核" },
  { t: "成本\nECN-style", b: "可用度 / LCOE" },
  { t: "報表", b: "月報 PDF + Gantt" },
  { t: "警報\nRAG", b: "30 秒查到手冊" },
];
const modW = (W - 1 - 0.15 * 4) / 5;
const modY = 3.25;
const modH = 1.0;
mods.forEach((m, i) => {
  const x = 0.5 + i * (modW + 0.15);
  s.addText([
    { text: m.t, options: { fontSize: 11, bold: true, color: C.ink, breakLine: true } },
    { text: " ", options: { fontSize: 4, breakLine: true } },
    { text: m.b, options: { fontSize: 8.5, color: C.inkSoft, italic: true } },
  ], {
    x, y: modY, w: modW, h: modH,
    fontFace: F.serif,
    align: "center", valign: "middle", margin: 6,
    fill: { color: C.creamLight },
    line: { color: C.greenAccent, width: 0.5 },
  });
});

// ─────────────────────────────────────────────
// 套餐區
// ─────────────────────────────────────────────
s.addText("§  PRICING  /  套餐分層", {
  x: 0.5, y: 4.5, w: W - 1, h: 0.3,
  fontFace: F.serifEn, fontSize: 10, color: C.greenMid,
  bold: true, charSpacing: 6, valign: "middle", margin: 0,
});

const tiers = [
  {
    label: "Basic",
    body: "監控 + 庫存 + 派工 + 報表 + 基本 RAG",
    price: "NT$20-40k / turbine / 年",
    alt: "或 NT$2-4M 一次性",
  },
  {
    label: "Pro",
    body: "+ Cost engine（ECN-style）",
    price: "+ NT$10-20k / turbine / 年",
    alt: "可用度 / LCOE / 預測",
  },
  {
    label: "Enterprise",
    body: "+ AI 診斷 + 視覺定檢（API 整合）",
    price: "+ revenue share with partners",
    alt: "windAILab / InduSpect",
  },
];
const tW = (W - 1 - 0.2 * 2) / 3;
const tY = 4.85;
const tH = 1.5;
tiers.forEach((t, i) => {
  const x = 0.5 + i * (tW + 0.2);
  s.addText("OM-Operator " + t.label, {
    x, y: tY, w: tW, h: 0.4,
    fontFace: F.serif, fontSize: 11, color: "F5F1E8",
    bold: true, charSpacing: 3,
    align: "center", valign: "middle", margin: 0,
    fill: { color: i === 0 ? C.greenAccent : i === 1 ? C.greenMid : C.greenDark },
  });
  s.addText([
    { text: t.body, options: { fontSize: 9.5, color: C.inkSoft, italic: true, breakLine: true } },
    { text: " ", options: { fontSize: 4, breakLine: true } },
    { text: t.price, options: { fontSize: 11, bold: true, color: C.greenDark, breakLine: true } },
    { text: t.alt, options: { fontSize: 8.5, color: C.inkMuted, italic: true } },
  ], {
    x, y: tY + 0.4, w: tW, h: tH - 0.4,
    fontFace: F.serif,
    align: "center", valign: "middle", margin: 8,
    fill: { color: C.creamLight },
    line: { color: C.rule, width: 0.5 },
  });
});

// 預算錨點
s.addShape(pres.shapes.LINE, {
  x: 0.5, y: 6.5, w: W - 1, h: 0,
  line: { color: C.greenAccent, width: 1 },
});
s.addText('"  月費比少請半個工程師便宜  "', {
  x: 0.5, y: 6.6, w: W - 1, h: 0.45,
  fontFace: F.serif, fontSize: 14, color: C.greenDark,
  bold: true, italic: true, charSpacing: 4,
  align: "center", valign: "middle", margin: 0,
});

// ─────────────────────────────────────────────
// 三大殺手特色
// ─────────────────────────────────────────────
s.addText("§  WHY  /  獨家賣點", {
  x: 0.5, y: 7.2, w: W - 1, h: 0.3,
  fontFace: F.serifEn, fontSize: 10, color: C.greenMid,
  bold: true, charSpacing: 6, valign: "middle", margin: 0,
});

const usps = [
  {
    h: "Simulator-first",
    b: "Demo 不需要客戶先給資料 — 物理模擬器跑出和真實 SCADA 一樣的 14 台風機",
  },
  {
    h: "整合度沒人達到",
    b: "SCADA + 庫存 + 派工 + 簽核 + 成本 + 警報 RAG + 模擬器，7 列無單一競品同時涵蓋",
  },
  {
    h: "現場工程師高頻 user",
    b: "警報跳出 → 30 秒查到手冊段落（mobile /field/ UI）— PMF 關鍵",
  },
];
const uY = 7.55;
const uH = 0.65;
usps.forEach((u, i) => {
  const y = uY + i * (uH + 0.1);
  s.addText([
    { text: "→  ", options: { fontSize: 13, bold: true, color: C.greenDark } },
    { text: u.h + "  ·  ", options: { fontSize: 12, bold: true, color: C.ink } },
    { text: u.b, options: { fontSize: 10.5, color: C.inkSoft, italic: true } },
  ], {
    x: 0.5, y, w: W - 1, h: uH,
    fontFace: F.serif,
    align: "left", valign: "middle", margin: 8,
    fill: { color: C.creamLight },
    line: { color: C.rule, width: 0.5 },
  });
});

// ─────────────────────────────────────────────
// 第一個客戶 + 路線圖（合併為一行）
// ─────────────────────────────────────────────
s.addShape(pres.shapes.LINE, {
  x: 0.5, y: 9.85, w: W - 1, h: 0,
  line: { color: C.greenAccent, width: 0.75 },
});
s.addText("§  FIRST CUSTOMER  ·  Z72 機型運維廠商  /  6 個月  ·  M1 → M6 (2026-05 → 2026-10)", {
  x: 0.5, y: 9.95, w: W - 1, h: 0.35,
  fontFace: F.serif, fontSize: 11, color: C.greenDark,
  bold: true, charSpacing: 3, valign: "middle", margin: 0,
});
s.addText(
  "三個 repo 都有 Z72 真資料 · 無 OEM 合作門檻 · z72hmi 已實機運轉 · Bachmann M1 PLC 已驗證",
  {
    x: 0.5, y: 10.3, w: W - 1, h: 0.35,
    fontFace: F.serif, fontSize: 10, color: C.inkSoft,
    italic: true, valign: "middle", margin: 0,
  }
);

// ─────────────────────────────────────────────
// 底部聯絡
// ─────────────────────────────────────────────
s.addShape(pres.shapes.RECTANGLE, {
  x: 0, y: 10.85, w: W, h: 0.84,
  fill: { color: C.greenDark }, line: { color: C.greenDark, width: 0 },
});
s.addText("劉瑞弘  Juihung Liu  ·  DOF Lab  ·  NCUT 智動系", {
  x: 0.5, y: 10.95, w: W - 1, h: 0.35,
  fontFace: F.serif, fontSize: 12, color: "F5F1E8",
  bold: true, charSpacing: 3, valign: "middle", margin: 0,
});
s.addText("moredof@gmail.com   ·   github.com/dofliu   ·   doflab.cc   ·   詳細版 deck on request", {
  x: 0.5, y: 11.3, w: W - 1, h: 0.32,
  fontFace: F.serifEn, fontSize: 9, color: "B3C2B6",
  italic: true, valign: "middle", margin: 0,
});

// 寫檔
const outPath = path.resolve(__dirname, "../../docs/sales/pitch_deck_v0.8.1_onepager.pptx");
pres.writeFile({ fileName: outPath }).then((file) => {
  console.log(`✓ onepager 已生成：${file}`);
  console.log("→ 用戶在 PowerPoint 開啟後選「檔案 → 匯出 → 建立 PDF/XPS 文件」即可轉成 PDF");
});
