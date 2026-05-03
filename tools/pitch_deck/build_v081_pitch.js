// windMindOM Pitch Deck v0.8.1 builder — Journal theme
// 對應 outline: docs/sales/pitch_deck_v0.8.1_outline.md
// 主題：Journal（米白墨綠期刊風 / 學術襯線書冊風）
// 用法：node tools/pitch_deck/build_v081_pitch.js
//
// 設計原則（依 pptx-jliu-style skill SKILL.md）：
// - 物件最小化（策略 B）：fill 與文字合一
// - Journal: 米白 + 墨色 + 暗墨綠 三色，極簡留白
// - 全襯線字體 + 印刷符號（§ — · →）建立層次
// - 每頁雙語頁腳（封面除外）
// - rectRadius 0；無陰影；無漸層

const pptxgen = require("pptxgenjs");
const path = require("path");

// ─────────────────────────────────────────────
// 主題色與字型
// ─────────────────────────────────────────────
const C = {
  cream:        "F5F1E8",  // 米白主背景
  creamLight:   "FAF7F0",  // 更淺的米白（內容卡片）
  ink:          "1F2937",  // 主文字（墨色）
  inkSoft:      "4B5563",  // 次要文字
  inkMuted:     "8B8378",  // 頁腳 / 灰
  greenDark:    "1F3A2E",  // 深墨綠（封面 / 分隔頁背景）
  greenMid:     "2D4A3E",  // 中墨綠（強調）
  greenAccent:  "5C7A6A",  // 淺墨綠（線條 / 邊框）
  green50:      "E8EDE9",  // 極淺墨綠（表格底色）
  rule:         "C9C2B0",  // 細線（米黃灰）
};

const F = {
  serif:    "Noto Serif CJK TC",  // 中文襯線；user 端 fallback PMingLiU
  serifEn:  "Georgia",            // 英文襯線
  mono:     "Consolas",
};

const SLIDE_W = 13.33;
const SLIDE_H = 7.5;

// ─────────────────────────────────────────────
// pres 初始化
// ─────────────────────────────────────────────
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.author = "DOF Lab — 劉瑞弘";
pres.company = "NCUT";
pres.title = "windMindOM — 離岸風場運維廠商工具 (Pitch Deck v0.8.1)";

// ─────────────────────────────────────────────
// Helper：雙語頁腳（每頁套用，封面除外）
// ─────────────────────────────────────────────
function addJournalFooter(slide, pageNum, totalPages, sectionLabel) {
  // 細線
  slide.addShape(pres.shapes.LINE, {
    x: 0.6, y: 7.0, w: SLIDE_W - 1.2, h: 0,
    line: { color: C.rule, width: 0.5 },
  });
  // 左：品牌 + 版本
  slide.addText("windMindOM · v0.8.1 · 2026-05", {
    x: 0.6, y: 7.08, w: 4.5, h: 0.32,
    fontFace: F.serifEn, fontSize: 9, color: C.inkMuted,
    valign: "middle", margin: 0,
  });
  // 中：雙語標題（區塊小標）
  slide.addText(sectionLabel, {
    x: 4.5, y: 7.08, w: 4.33, h: 0.32,
    fontFace: F.serif, fontSize: 9, color: C.inkMuted,
    align: "center", valign: "middle", margin: 0, italic: true,
  });
  // 右：頁碼
  slide.addText(`§ ${pageNum} / ${totalPages}`, {
    x: SLIDE_W - 5.5, y: 7.08, w: 4.9, h: 0.32,
    fontFace: F.serifEn, fontSize: 9, color: C.inkMuted,
    align: "right", valign: "middle", margin: 0,
  });
}

// ─────────────────────────────────────────────
// Helper：頁面標題列（§ NN — 章名）
// ─────────────────────────────────────────────
function addJournalHeader(slide, sectionNum, sectionTitle) {
  slide.addText(`§ ${sectionNum.toString().padStart(2, "0")}  —  ${sectionTitle}`, {
    x: 0.6, y: 0.45, w: SLIDE_W - 1.2, h: 0.45,
    fontFace: F.serif, fontSize: 13, color: C.greenMid,
    bold: false, charSpacing: 4, valign: "middle", margin: 0,
  });
  // 標題下細線
  slide.addShape(pres.shapes.LINE, {
    x: 0.6, y: 0.95, w: SLIDE_W - 1.2, h: 0,
    line: { color: C.rule, width: 0.5 },
  });
}

// ─────────────────────────────────────────────
// Helper：大標題（每個內容頁的主 H1）
// ─────────────────────────────────────────────
function addPageTitle(slide, title, y = 1.2) {
  slide.addText(title, {
    x: 0.6, y: y, w: SLIDE_W - 1.2, h: 0.7,
    fontFace: F.serif, fontSize: 28, color: C.ink,
    bold: true, valign: "middle", margin: 0,
  });
}

const TOTAL = 12;

// ═══════════════════════════════════════════════════════════
// Slide 1 — 封面
// ═══════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.greenDark };

  // 上方品牌標記
  s.addText("§  NCUT  ·  DOF LAB", {
    x: 0.8, y: 0.7, w: 6, h: 0.3,
    fontFace: F.serifEn, fontSize: 10, color: "B3C2B6",
    charSpacing: 8, valign: "middle", margin: 0,
  });

  // 主標
  s.addText("windMindOM", {
    x: 0.8, y: 2.4, w: SLIDE_W - 1.6, h: 1.3,
    fontFace: F.serifEn, fontSize: 72, color: "F5F1E8",
    bold: false, charSpacing: 2, valign: "middle", margin: 0,
  });

  // 中文副標
  s.addText("離岸風場運維廠商工具", {
    x: 0.8, y: 3.7, w: SLIDE_W - 1.6, h: 0.7,
    fontFace: F.serif, fontSize: 26, color: "DCE3DD",
    charSpacing: 8, valign: "middle", margin: 0,
  });

  // 細線分隔
  s.addShape(pres.shapes.LINE, {
    x: 0.8, y: 4.6, w: 3, h: 0,
    line: { color: "8FA89B", width: 0.75 },
  });

  // Tagline
  s.addText(
    "在一個 UI 看到 SCADA、庫存派工、成本計算、警報手冊查詢 — 取代你現在的 Excel + LINE + 紙單。",
    {
      x: 0.8, y: 4.85, w: SLIDE_W - 1.6, h: 1.0,
      fontFace: F.serif, fontSize: 14, color: "C9D2CC",
      italic: true, valign: "top", margin: 0,
    }
  );

  // 底部版本 + 聯絡（雙語）
  s.addShape(pres.shapes.LINE, {
    x: 0.8, y: 6.85, w: SLIDE_W - 1.6, h: 0,
    line: { color: "5C7A6A", width: 0.5 },
  });
  s.addText("Pitch Deck v0.8.1  ·  May 2026  ·  Operator-focused Wind Farm O&M Tool", {
    x: 0.8, y: 6.95, w: 8, h: 0.3,
    fontFace: F.serifEn, fontSize: 10, color: "9FB0A2",
    charSpacing: 4, valign: "middle", margin: 0,
  });
  s.addText("moredof@gmail.com", {
    x: SLIDE_W - 4.0, y: 6.95, w: 3.4, h: 0.3,
    fontFace: F.serifEn, fontSize: 10, color: "9FB0A2",
    align: "right", valign: "middle", margin: 0,
  });
}

// ═══════════════════════════════════════════════════════════
// Slide 2 — 痛點
// ═══════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream };
  addJournalHeader(s, 1, "PAIN POINT  —  痛點");
  addPageTitle(s, "運維廠商每天的工作型態", 1.15);

  // 副標
  s.addText("ICP：運維廠商（O&M service provider） · 競品 = Excel + LINE + 紙單", {
    x: 0.6, y: 1.95, w: SLIDE_W - 1.2, h: 0.4,
    fontFace: F.serif, fontSize: 13, color: C.inkSoft,
    italic: true, valign: "middle", margin: 0,
  });

  // 左欄：ICP 輪廓
  s.addText("§  WHO", {
    x: 0.6, y: 2.6, w: 6, h: 0.32,
    fontFace: F.serifEn, fontSize: 11, color: C.greenMid,
    charSpacing: 6, valign: "middle", margin: 0, bold: true,
  });
  s.addText([
    { text: "同時為 3-5 家業主服務", options: { bullet: { code: "2014" }, breakLine: true } },
    { text: "5-10 個風場、3 種 OEM 機型混搭", options: { bullet: { code: "2014" }, breakLine: true } },
    { text: "中小企業（年營收 NT$50-500M）", options: { bullet: { code: "2014" }, breakLine: true } },
    { text: "決策層級短：老闆 + 技術主管", options: { bullet: { code: "2014" } } },
  ], {
    x: 0.6, y: 3.0, w: 6, h: 2.5,
    fontFace: F.serif, fontSize: 13.5, color: C.ink,
    paraSpaceAfter: 6, valign: "top", margin: 0,
  });

  // 右欄：現況工具
  s.addText("§  WHAT THEY USE TODAY", {
    x: 7.0, y: 2.6, w: 6, h: 0.32,
    fontFace: F.serifEn, fontSize: 11, color: C.greenMid,
    charSpacing: 6, valign: "middle", margin: 0, bold: true,
  });
  s.addText([
    { text: "庫存散在各風場倉庫", options: { bullet: { code: "2014" }, breakLine: true } },
    { text: "派工靠 LINE 群組", options: { bullet: { code: "2014" }, breakLine: true } },
    { text: "成本估算靠 Excel", options: { bullet: { code: "2014" }, breakLine: true } },
    { text: "業主要 LCOE 報告 → 找會 ECN 的顧問", options: { bullet: { code: "2014" } } },
  ], {
    x: 7.0, y: 3.0, w: 5.6, h: 2.5,
    fontFace: F.serif, fontSize: 13.5, color: C.ink,
    paraSpaceAfter: 6, valign: "top", margin: 0,
  });

  // 底部結論引言框
  s.addShape(pres.shapes.LINE, {
    x: 0.6, y: 5.85, w: SLIDE_W - 1.2, h: 0,
    line: { color: C.greenAccent, width: 0.75 },
  });
  s.addText(
    "→  痛點清楚到不行，但沒有一個聚焦的工具。",
    {
      x: 0.6, y: 6.0, w: SLIDE_W - 1.2, h: 0.7,
      fontFace: F.serif, fontSize: 17, color: C.greenDark,
      italic: true, bold: true, charSpacing: 2,
      valign: "middle", margin: 0,
    }
  );

  addJournalFooter(s, 2, TOTAL, "§ Pain Point  /  痛點");
}

// ═══════════════════════════════════════════════════════════
// Slide 3 — 解法 (KEY VISUAL: 5 modules 中央輻射)
// ═══════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream };
  addJournalHeader(s, 2, "SOLUTION  —  解法");
  addPageTitle(s, "5 modules 整合在一個 UI", 1.15);
  s.addText('"取代你現在的 Excel + LINE + 紙單組合"', {
    x: 0.6, y: 1.95, w: SLIDE_W - 1.2, h: 0.4,
    fontFace: F.serif, fontSize: 13, color: C.inkSoft,
    italic: true, valign: "middle", margin: 0,
  });

  // ─── 中央輻射圖 ───
  // Center: windMindOM
  const cx = 6.66, cy = 4.4;
  const center = { x: cx - 1.4, y: cy - 0.45, w: 2.8, h: 0.9 };

  // Module positions (5 around center, clock 12 / 2 / 5 / 7 / 10)
  const modW = 2.2, modH = 0.75;
  const modules = [
    { label: "監控  SCADA",     sub: "Z72 PLC / 物理模擬器",  x: cx - modW/2,         y: cy - 2.7 },              // 12
    { label: "庫存派工",         sub: "工單 + 多階簽核",        x: cx + 2.5 - modW/2,   y: cy - 1.2 },              // 2
    { label: "成本  ECN",       sub: "可用度 / LCOE / 預測",    x: cx + 2.0 - modW/2,   y: cy + 1.5 },              // 5
    { label: "報表",            sub: "月報 PDF + Gantt",       x: cx - 2.0 - modW/2,   y: cy + 1.5 },              // 7
    { label: "警報  RAG",       sub: "30 秒查到手冊段落",       x: cx - 2.5 - modW/2,   y: cy - 1.2 },              // 10
  ];

  // 連線：center → 每個 module（在 module 之前畫，這樣覆蓋順序對）
  modules.forEach((m) => {
    const startX = cx;
    const startY = cy;
    const endX = m.x + modW / 2;
    const endY = m.y + modH / 2;
    s.addShape(pres.shapes.LINE, {
      x: Math.min(startX, endX), y: Math.min(startY, endY),
      w: Math.abs(endX - startX), h: Math.abs(endY - startY),
      line: { color: C.greenAccent, width: 0.5, dashType: "dash" },
      flipH: endX < startX, flipV: endY < startY,
    });
  });

  // Center node
  s.addText("windMindOM", {
    x: center.x, y: center.y, w: center.w, h: center.h,
    fontFace: F.serifEn, fontSize: 18, color: "F5F1E8",
    bold: false, charSpacing: 3,
    align: "center", valign: "middle", margin: 0,
    fill: { color: C.greenDark },
    line: { color: C.greenDark, width: 0.5 },
  });

  // 5 modules
  modules.forEach((m) => {
    s.addText([
      { text: m.label, options: { bold: true, fontSize: 13, breakLine: true } },
      { text: m.sub,   options: { fontSize: 9.5, color: C.inkSoft, italic: true } },
    ], {
      x: m.x, y: m.y, w: modW, h: modH,
      fontFace: F.serif, color: C.ink,
      align: "center", valign: "middle", margin: 4,
      fill: { color: C.creamLight },
      line: { color: C.greenAccent, width: 0.75 },
    });
  });

  // 底部一行強調
  s.addShape(pres.shapes.LINE, {
    x: 0.6, y: 6.45, w: SLIDE_W - 1.2, h: 0,
    line: { color: C.rule, width: 0.5 },
  });
  s.addText("Basic 套餐就含 RAG  —  給工程師的甜頭，提升 PMF。", {
    x: 0.6, y: 6.55, w: SLIDE_W - 1.2, h: 0.4,
    fontFace: F.serif, fontSize: 12, color: C.greenDark,
    italic: true, align: "center", valign: "middle", margin: 0,
  });

  addJournalFooter(s, 3, TOTAL, "§ Solution  /  五大模組");
}

// ═══════════════════════════════════════════════════════════
// Slide 4 — Why now
// ═══════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream };
  addJournalHeader(s, 3, "WHY NOW  —  為什麼是 2026");
  addPageTitle(s, "三條獨立 timeline，剛好交會", 1.15);

  // 三張卡片橫排
  const cards = [
    {
      label: "2024 — 2025",
      title: "OEM 連番出包",
      body: "SGRE 葉片召回、Vestas 齒輪箱集中故障 → 業主自建監測動力上升 → 運維廠商接更多獨立委外案。",
    },
    {
      label: "2026  — ",
      title: "第三階段風場商轉",
      body: "新風場大量投產，運維廠商需求量大增；機型混搭（Z72 / Vestas / SGRE / MingYang）成為日常。",
    },
    {
      label: "現況",
      title: "ECN Tool 5.0 的缺口",
      body: "業界事實標準 ECN Tool 5.0 只有 Excel + VBA、沒有 API。Python 移植 + workflow 整合 = 我們的差異化。",
    },
  ];
  const cardW = (SLIDE_W - 1.2 - 0.4 * 2) / 3;
  const cardY = 2.5;
  const cardH = 3.6;
  cards.forEach((c, i) => {
    const x = 0.6 + i * (cardW + 0.4);
    // 標籤色塊
    s.addText(c.label, {
      x, y: cardY, w: cardW, h: 0.5,
      fontFace: F.serifEn, fontSize: 11, color: "F5F1E8",
      bold: true, charSpacing: 6,
      align: "center", valign: "middle", margin: 0,
      fill: { color: C.greenMid },
    });
    // 卡片本體
    s.addText([
      { text: c.title, options: { fontSize: 18, bold: true, color: C.ink, breakLine: true } },
      { text: " ", options: { fontSize: 4, breakLine: true } },
      { text: c.body, options: { fontSize: 12, color: C.inkSoft, italic: false } },
    ], {
      x, y: cardY + 0.5, w: cardW, h: cardH - 0.5,
      fontFace: F.serif,
      align: "left", valign: "top", margin: 14,
      fill: { color: C.creamLight },
      line: { color: C.rule, width: 0.5 },
    });
  });

  // 底部一句
  s.addText("→  不是 me-too，是 timing 對 + 技術剛好 ready。", {
    x: 0.6, y: 6.3, w: SLIDE_W - 1.2, h: 0.4,
    fontFace: F.serif, fontSize: 14, color: C.greenDark,
    italic: true, bold: true, align: "center", valign: "middle", margin: 0,
  });

  addJournalFooter(s, 4, TOTAL, "§ Why Now  /  時機");
}

// ═══════════════════════════════════════════════════════════
// Slide 5 — Killer feature: Simulator-first demo
// ═══════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream };
  addJournalHeader(s, 4, "KILLER FEATURE  —  獨家賣點");
  addPageTitle(s, "Simulator-first  —  Demo 不需要你先給資料", 1.15);

  // 左右兩欄對比
  const colW = (SLIDE_W - 1.2 - 1.2) / 2;
  const colY = 2.5;
  const colH = 3.5;

  // 左：競品現況
  s.addText("競品現況", {
    x: 0.6, y: colY, w: colW, h: 0.5,
    fontFace: F.serif, fontSize: 14, color: C.inkSoft,
    bold: true, charSpacing: 4,
    align: "center", valign: "middle", margin: 0,
    fill: { color: C.green50 },
  });
  s.addText([
    { text: "1.  客戶簽 NDA", options: { breakLine: true } },
    { text: "2.  客戶提供 SCADA 歷史資料", options: { breakLine: true } },
    { text: "3.  我們花 2-4 週做 demo", options: { breakLine: true } },
    { text: "4.  客戶才看到產品實際運作", options: {} },
  ], {
    x: 0.6, y: colY + 0.5, w: colW, h: colH - 0.5,
    fontFace: F.serif, fontSize: 14, color: C.ink,
    paraSpaceAfter: 8, align: "left", valign: "middle", margin: 24,
    fill: { color: C.creamLight },
    line: { color: C.rule, width: 0.5 },
  });

  // 中央箭頭
  s.addText("→", {
    x: 0.6 + colW, y: colY + (colH / 2) - 0.5, w: 1.2, h: 1,
    fontFace: F.serifEn, fontSize: 48, color: C.greenMid,
    align: "center", valign: "middle", margin: 0,
  });

  // 右：windMindOM
  s.addText("windMindOM", {
    x: 0.6 + colW + 1.2, y: colY, w: colW, h: 0.5,
    fontFace: F.serifEn, fontSize: 14, color: "F5F1E8",
    bold: true, charSpacing: 4,
    align: "center", valign: "middle", margin: 0,
    fill: { color: C.greenDark },
  });
  s.addText([
    { text: "1.  打開 simulator", options: { breakLine: true } },
    { text: "2.  客戶當場看到 14 台風機運轉", options: { breakLine: true } },
    { text: "3.  即時 SCADA、power curve、告警全可看", options: { breakLine: true } },
    { text: "4.  切實機只需要換 adapter", options: {} },
  ], {
    x: 0.6 + colW + 1.2, y: colY + 0.5, w: colW, h: colH - 0.5,
    fontFace: F.serif, fontSize: 14, color: C.ink,
    paraSpaceAfter: 8, align: "left", valign: "middle", margin: 24,
    fill: { color: C.creamLight },
    line: { color: C.greenAccent, width: 0.75 },
  });

  // 底部技術備註
  s.addShape(pres.shapes.LINE, {
    x: 0.6, y: 6.3, w: SLIDE_W - 1.2, h: 0,
    line: { color: C.rule, width: 0.5 },
  });
  s.addText(
    "技術依據：digiWindTurbine 物理模擬器，14 台風機 · 109 SCADA tags · 11 fault scenarios · 18/21 quality check 通過。",
    {
      x: 0.6, y: 6.42, w: SLIDE_W - 1.2, h: 0.5,
      fontFace: F.serif, fontSize: 11, color: C.inkMuted,
      italic: true, align: "center", valign: "middle", margin: 0,
    }
  );

  addJournalFooter(s, 5, TOTAL, "§ Killer Feature  /  Simulator-first");
}

// ═══════════════════════════════════════════════════════════
// Slide 6 — 競品矩陣
// ═══════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream };
  addJournalHeader(s, 5, "COMPETITIVE LANDSCAPE  —  競品矩陣");
  addPageTitle(s, "沒有任何一家同時涵蓋這 7 列", 1.15);

  // 表格資料
  const headerOpts = {
    fill: { color: C.greenDark }, color: "F5F1E8", bold: true,
    fontFace: F.serif, fontSize: 11, align: "center", valign: "middle",
  };
  const cellOpts = {
    fontFace: F.serif, fontSize: 11, color: C.ink,
    align: "center", valign: "middle",
  };
  const labelOpts = {
    fontFace: F.serif, fontSize: 11, color: C.ink, bold: true,
    align: "left", valign: "middle",
  };
  const highlightOpts = {
    fill: { color: C.green50 }, color: C.greenDark, bold: true,
    fontFace: F.serif, fontSize: 11.5,
    align: "center", valign: "middle",
  };
  const highlightLabel = {
    fill: { color: C.green50 }, color: C.greenDark, bold: true,
    fontFace: F.serif, fontSize: 11.5,
    align: "left", valign: "middle",
  };

  const rows = [
    [
      { text: "", options: headerOpts },
      { text: "SCADA", options: headerOpts },
      { text: "庫存", options: headerOpts },
      { text: "派工", options: headerOpts },
      { text: "簽核", options: headerOpts },
      { text: "成本", options: headerOpts },
      { text: "警報 RAG", options: headerOpts },
      { text: "模擬器", options: headerOpts },
    ],
    [
      { text: "Excel + LINE + 紙單（現況）", options: labelOpts },
      "—", "散", "慢", "紙", "—", "—", "—",
    ].map((c, i) => i === 0 ? c : { text: c, options: cellOpts }),
    [
      { text: "Bazefield (NO)", options: labelOpts },
      "✓✓", "—", "✓", "—", "—", "—", "—",
    ].map((c, i) => i === 0 ? c : { text: c, options: cellOpts }),
    [
      { text: "ONYX InSight (UK)", options: labelOpts },
      "部分", "—", "—", "—", "—", "—", "—",
    ].map((c, i) => i === 0 ? c : { text: c, options: cellOpts }),
    [
      { text: "ECN / TNO Tool 5.0", options: labelOpts },
      "—", "—", "—", "—", "✓✓", "—", "—",
    ].map((c, i) => i === 0 ? c : { text: c, options: cellOpts }),
    [
      { text: "SAP PM / IBM Maximo", options: labelOpts },
      "—", "✓✓", "✓✓", "✓✓", "—", "—", "—",
    ].map((c, i) => i === 0 ? c : { text: c, options: cellOpts }),
    [
      { text: "Siemens MindSphere", options: labelOpts },
      "✓", "✓", "✓", "✓", "—", "—", "—",
    ].map((c, i) => i === 0 ? c : { text: c, options: cellOpts }),
    [
      { text: "OEM 自家 dashboard", options: labelOpts },
      "✓✓", "—", "—", "—", "—", "—", "—",
    ].map((c, i) => i === 0 ? c : { text: c, options: cellOpts }),
    [
      { text: "windMindOM", options: highlightLabel },
      "✓", "✓✓", "✓✓", "✓✓", "✓✓", "✓✓", "✓✓",
    ].map((c, i) => i === 0 ? c : { text: c, options: highlightOpts }),
  ];

  s.addTable(rows, {
    x: 0.6, y: 2.05, w: SLIDE_W - 1.2,
    colW: [3.6, 1.18, 1.18, 1.18, 1.18, 1.18, 1.42, 1.21],
    rowH: 0.42,
    border: { pt: 0.5, color: C.rule },
    fontFace: F.serif,
  });

  // 底部重點
  s.addShape(pres.shapes.LINE, {
    x: 0.6, y: 6.4, w: SLIDE_W - 1.2, h: 0,
    line: { color: C.rule, width: 0.5 },
  });
  s.addText(
    "→  重點不是「我們最強」，是「整合度」沒人達到。警報 RAG + 模擬器是兩個獨家欄。",
    {
      x: 0.6, y: 6.5, w: SLIDE_W - 1.2, h: 0.4,
      fontFace: F.serif, fontSize: 12, color: C.greenDark,
      italic: true, align: "center", valign: "middle", margin: 0,
    }
  );

  addJournalFooter(s, 6, TOTAL, "§ Competitive  /  競品");
}

// ═══════════════════════════════════════════════════════════
// Slide 7 — 商業模式：三層套餐階梯
// ═══════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream };
  addJournalHeader(s, 6, "BUSINESS MODEL  —  商業模式");
  addPageTitle(s, "三層套餐 + 預算錨點", 1.15);

  // 階梯：Basic（最矮）→ Pro → Enterprise（最高）
  const stairs = [
    {
      label: "OM-Operator  Basic",
      content: "監控 + 庫存 + 派工 + 報表 + 基本 RAG",
      price: "NT$20-40k / turbine / 年",
      priceAlt: "或 NT$2-4M 一次性 + 維護",
    },
    {
      label: "OM-Operator  Pro",
      content: "+ Cost engine（ECN-style）",
      price: "+ NT$10-20k / turbine / 年",
      priceAlt: "可用度 / LCOE / 預測 vs 實際",
    },
    {
      label: "OM-Operator  Enterprise",
      content: "+ windAILab AI 診斷 + InduSpect 定檢",
      price: "+ revenue share with partners",
      priceAlt: "API 整合，不重做 AI",
    },
  ];

  // 階梯位置（左到右遞增高度）
  const baseY = 5.4;     // 最低點
  const heights = [2.0, 2.5, 3.0];
  const stairW = 3.7;
  const gap = 0.25;
  const startX = (SLIDE_W - (stairW * 3 + gap * 2)) / 2;

  stairs.forEach((st, i) => {
    const x = startX + i * (stairW + gap);
    const h = heights[i];
    const y = baseY - h;

    // 階梯主體（一塊純色加文字）
    s.addText([
      { text: st.label, options: { fontSize: 14, bold: true, color: "F5F1E8", breakLine: true, charSpacing: 4 } },
      { text: " ", options: { fontSize: 4, breakLine: true } },
      { text: st.content, options: { fontSize: 11, color: "DCE3DD", italic: true, breakLine: true } },
      { text: " ", options: { fontSize: 8, breakLine: true } },
      { text: st.price, options: { fontSize: 12, color: "F5F1E8", bold: true, breakLine: true } },
      { text: st.priceAlt, options: { fontSize: 9.5, color: "B3C2B6", italic: true } },
    ], {
      x, y, w: stairW, h,
      fontFace: F.serif,
      align: "center", valign: "middle", margin: 14,
      fill: { color: i === 0 ? C.greenAccent : i === 1 ? C.greenMid : C.greenDark },
    });
  });

  // 底部預算錨點（強調框）
  s.addShape(pres.shapes.LINE, {
    x: 0.6, y: 5.85, w: SLIDE_W - 1.2, h: 0,
    line: { color: C.greenAccent, width: 1.0 },
  });
  s.addText('"  月費比少請半個工程師便宜  "', {
    x: 0.6, y: 5.95, w: SLIDE_W - 1.2, h: 0.55,
    fontFace: F.serif, fontSize: 20, color: C.greenDark,
    italic: true, bold: true, charSpacing: 4,
    align: "center", valign: "middle", margin: 0,
  });
  s.addText("第一筆收入路徑：3 個月部署 Basic → NT$2-4M / 單一客戶 LTV ≈ NT$5-10M（前 2 年）", {
    x: 0.6, y: 6.55, w: SLIDE_W - 1.2, h: 0.35,
    fontFace: F.serif, fontSize: 11, color: C.inkSoft,
    align: "center", valign: "middle", margin: 0,
  });

  addJournalFooter(s, 7, TOTAL, "§ Business Model  /  套餐");
}

// ═══════════════════════════════════════════════════════════
// Slide 8 — 第一個客戶：Z72 機型運維廠商
// ═══════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream };
  addJournalHeader(s, 7, "FIRST CUSTOMER  —  首發客戶");
  addPageTitle(s, "Z72 機型運維廠商", 1.15);
  s.addText("為什麼選 Z72 為首發 + 3 個月可交付什麼", {
    x: 0.6, y: 1.95, w: SLIDE_W - 1.2, h: 0.4,
    fontFace: F.serif, fontSize: 13, color: C.inkSoft,
    italic: true, valign: "middle", margin: 0,
  });

  // 上半：4 個理由（4 卡橫排）
  const reasons = [
    { num: "01", t: "三 repo 都有 Z72 真資料", b: "z72hmi · z72_etech · digiWT simulator" },
    { num: "02", t: "無 OEM 合作門檻", b: "Harakosan/Zephyros 已退出市場" },
    { num: "03", t: "z72hmi 即實機運轉", b: '"我們已在運維他們同款機"' },
    { num: "04", t: "PLC 已驗證", b: "Bachmann M1 立刻可上線" },
  ];
  const rW = (SLIDE_W - 1.2 - 0.3 * 3) / 4;
  const rY = 2.5;
  const rH = 1.7;
  reasons.forEach((r, i) => {
    const x = 0.6 + i * (rW + 0.3);
    s.addText(r.num, {
      x, y: rY, w: rW, h: 0.4,
      fontFace: F.serifEn, fontSize: 10, color: C.greenMid,
      bold: true, charSpacing: 6, align: "left", valign: "middle", margin: 12,
      fill: { color: C.green50 },
    });
    s.addText([
      { text: r.t, options: { fontSize: 13.5, bold: true, color: C.ink, breakLine: true } },
      { text: " ", options: { fontSize: 4, breakLine: true } },
      { text: r.b, options: { fontSize: 10.5, color: C.inkSoft, italic: true } },
    ], {
      x, y: rY + 0.4, w: rW, h: rH - 0.4,
      fontFace: F.serif,
      align: "left", valign: "top", margin: 12,
      fill: { color: C.creamLight },
      line: { color: C.rule, width: 0.5 },
    });
  });

  // 下半：3 個月交付
  s.addText("§  3-MONTH DELIVERABLES", {
    x: 0.6, y: 4.55, w: SLIDE_W - 1.2, h: 0.35,
    fontFace: F.serifEn, fontSize: 11, color: C.greenMid,
    bold: true, charSpacing: 6, valign: "middle", margin: 0,
  });
  s.addText([
    { text: "Dashboard：即時 SCADA + 告警 + 工單 + 成本檢視", options: { bullet: { code: "2014" }, breakLine: true } },
    { text: "工作流：派工 / 庫存 / 多階簽核全跑通", options: { bullet: { code: "2014" }, breakLine: true } },
    { text: "警報 RAG：現場工程師手機可查（mobile-friendly /field/）", options: { bullet: { code: "2014" }, breakLine: true } },
    { text: "報表：5 年 O&M 預算 + 排程 Gantt（PDF 月報）", options: { bullet: { code: "2014" } } },
  ], {
    x: 0.6, y: 4.95, w: SLIDE_W - 1.2, h: 1.7,
    fontFace: F.serif, fontSize: 13.5, color: C.ink,
    paraSpaceAfter: 4, valign: "top", margin: 0,
  });

  addJournalFooter(s, 8, TOTAL, "§ First Customer  /  Z72");
}

// ═══════════════════════════════════════════════════════════
// Slide 9 — Roadmap 6 個月 timeline
// ═══════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream };
  addJournalHeader(s, 8, "ROADMAP  —  6 個月路線圖");
  addPageTitle(s, "一日一項重要工作  ·  一月一 module", 1.15);

  // 6 個月 timeline 橫排
  const months = [
    { m: "Month 1", date: "2026-05", title: "Setup", body: "repo baseline · friendly 客戶接觸" },
    { m: "Month 2", date: "2026-06", title: "Cost",  body: "ECN 移植 · K13 dataset 跑通" },
    { m: "Month 3", date: "2026-07", title: "Workflow Pt.1", body: "Work Order + Approval" },
    { m: "Month 4", date: "2026-08", title: "Workflow Pt.2", body: "Inventory + Reporting" },
    { m: "Month 5", date: "2026-09", title: "Knowledge", body: "RAG + mobile /field/ UI" },
    { m: "Month 6", date: "2026-10", title: "PoC", body: "Z72 運維廠商 · 第一筆合約" },
  ];
  const tlY = 2.5;
  const tlW = (SLIDE_W - 1.2) / 6;
  const tlH = 3.4;

  // 底線（timeline 軸）
  s.addShape(pres.shapes.LINE, {
    x: 0.6, y: tlY + 0.85, w: SLIDE_W - 1.2, h: 0,
    line: { color: C.greenAccent, width: 1.5 },
  });

  months.forEach((mo, i) => {
    const x = 0.6 + i * tlW;
    // 月份標籤（軸上）
    s.addText(mo.m, {
      x, y: tlY, w: tlW, h: 0.4,
      fontFace: F.serifEn, fontSize: 11, color: C.greenMid,
      bold: true, charSpacing: 4, align: "center", valign: "middle", margin: 0,
    });
    s.addText(mo.date, {
      x, y: tlY + 0.4, w: tlW, h: 0.3,
      fontFace: F.serifEn, fontSize: 9, color: C.inkMuted,
      align: "center", valign: "middle", margin: 0,
    });
    // 軸上點（圓）
    s.addShape(pres.shapes.OVAL, {
      x: x + tlW / 2 - 0.07, y: tlY + 0.78, w: 0.14, h: 0.14,
      fill: { color: i === 5 ? C.greenDark : C.greenMid },
      line: { color: C.greenDark, width: 0.5 },
    });
    // 月份內容卡（軸下）
    s.addText([
      { text: mo.title, options: { fontSize: 14, bold: true, color: C.ink, breakLine: true } },
      { text: " ", options: { fontSize: 4, breakLine: true } },
      { text: mo.body, options: { fontSize: 10, color: C.inkSoft, italic: true } },
    ], {
      x: x + 0.05, y: tlY + 1.15, w: tlW - 0.1, h: tlH - 1.15,
      fontFace: F.serif,
      align: "center", valign: "top", margin: 8,
      fill: { color: i === 5 ? C.green50 : C.creamLight },
      line: { color: i === 5 ? C.greenAccent : C.rule, width: i === 5 ? 0.75 : 0.5 },
    });
  });

  // 底部一句
  s.addShape(pres.shapes.LINE, {
    x: 0.6, y: 6.4, w: SLIDE_W - 1.2, h: 0,
    line: { color: C.rule, width: 0.5 },
  });
  s.addText(
    "→  6 個月 vs v0.5 估算的 12-18 個月 — 因為砍掉 plugin SDK / Workflow Hub 等過度工程。",
    {
      x: 0.6, y: 6.5, w: SLIDE_W - 1.2, h: 0.4,
      fontFace: F.serif, fontSize: 11, color: C.greenDark,
      italic: true, align: "center", valign: "middle", margin: 0,
    }
  );

  addJournalFooter(s, 9, TOTAL, "§ Roadmap  /  6 個月");
}

// ═══════════════════════════════════════════════════════════
// Slide 10 — Ask + 聯絡
// ═══════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream };
  addJournalHeader(s, 9, "ASK  —  我們需要的幫助");
  addPageTitle(s, "三個目標群組", 1.15);

  const asks = [
    {
      label: "Friendly 客戶",
      title: "找 1-2 家 Z72 機型運維廠商作 pilot",
      body: "3 個月 NT$2-4M 部署 Basic 套餐，先用 simulator demo，再切實機。失敗風險低，因為 Z72 整套技術鏈已驗證。",
    },
    {
      label: "國科會 / 計畫",
      title: "送「能源科技整合型計畫」（2026 H2）",
      body: "主題：「離岸風場運維廠商整合決策工具」。跨領域組合（電機 + AI + 工管），論文線已 ready。",
    },
    {
      label: "投資人 / 共創",
      title: "首輪 NT$3-5M 開發預算",
      body: "1-2 人團隊 6 個月，配合 1-2 家 pilot 客戶 LTV NT$5-10M × 2-3 = NT$10-30M。顧問案先建立 case study，再轉訂閱制。",
    },
  ];

  const askW = (SLIDE_W - 1.2 - 0.3 * 2) / 3;
  const askY = 2.45;
  const askH = 3.3;
  asks.forEach((a, i) => {
    const x = 0.6 + i * (askW + 0.3);
    s.addText(a.label, {
      x, y: askY, w: askW, h: 0.45,
      fontFace: F.serif, fontSize: 12, color: "F5F1E8",
      bold: true, charSpacing: 4,
      align: "center", valign: "middle", margin: 0,
      fill: { color: C.greenDark },
    });
    s.addText([
      { text: a.title, options: { fontSize: 14, bold: true, color: C.ink, breakLine: true } },
      { text: " ", options: { fontSize: 6, breakLine: true } },
      { text: a.body, options: { fontSize: 11, color: C.inkSoft, italic: false } },
    ], {
      x, y: askY + 0.45, w: askW, h: askH - 0.45,
      fontFace: F.serif,
      align: "left", valign: "top", margin: 14,
      fill: { color: C.creamLight },
      line: { color: C.rule, width: 0.5 },
    });
  });

  // 底部聯絡資訊
  s.addShape(pres.shapes.LINE, {
    x: 0.6, y: 6.0, w: SLIDE_W - 1.2, h: 0,
    line: { color: C.greenAccent, width: 1 },
  });
  s.addText("劉瑞弘  Juihung Liu  ·  DOF Lab  ·  NCUT", {
    x: 0.6, y: 6.12, w: SLIDE_W - 1.2, h: 0.4,
    fontFace: F.serif, fontSize: 14, color: C.greenDark,
    bold: true, charSpacing: 4, align: "center", valign: "middle", margin: 0,
  });
  s.addText("moredof@gmail.com   ·   github.com/dofliu   ·   doflab.cc", {
    x: 0.6, y: 6.5, w: SLIDE_W - 1.2, h: 0.35,
    fontFace: F.serifEn, fontSize: 11, color: C.inkSoft,
    italic: true, align: "center", valign: "middle", margin: 0,
  });

  addJournalFooter(s, 10, TOTAL, "§ Ask  /  Contact");
}

// ═══════════════════════════════════════════════════════════
// Appendix A1 — 兩條獨立論文線（學術版用）
// ═══════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream };
  addJournalHeader(s, "A1", "APPENDIX  —  兩條獨立論文線");
  addPageTitle(s, "Academic Track  ·  學術版補充", 1.15);

  // 兩欄
  const colW = (SLIDE_W - 1.2 - 0.4) / 2;
  const colY = 2.3;
  const colH = 4.0;

  // A. windMindOM 線
  s.addText("A.  windMindOM 線（產品自身）", {
    x: 0.6, y: colY, w: colW, h: 0.5,
    fontFace: F.serif, fontSize: 14, color: "F5F1E8",
    bold: true, charSpacing: 3,
    align: "left", valign: "middle", margin: 14,
    fill: { color: C.greenMid },
  });
  s.addText([
    {
      text: "Operator-focused Wind Farm O&M Tool: Integrating SCADA, Inventory, Cost, and RAG-based Knowledge Retrieval",
      options: { italic: true, fontSize: 12, color: C.ink, breakLine: true },
    },
    { text: " ", options: { fontSize: 4, breakLine: true } },
    { text: "→  Applied Energy", options: { fontSize: 10, color: C.greenDark, breakLine: true } },
    { text: " ", options: { fontSize: 12, breakLine: true } },
    {
      text: "Inventory and Crew Schedule Coupled Wind Farm O&M Cost Model: Extending ECN Tool 5.0 with Real-time Workflow Data",
      options: { italic: true, fontSize: 12, color: C.ink, breakLine: true },
    },
    { text: " ", options: { fontSize: 4, breakLine: true } },
    { text: "→  Energy / Renewable Energy", options: { fontSize: 10, color: C.greenDark } },
  ], {
    x: 0.6, y: colY + 0.5, w: colW, h: colH - 0.5,
    fontFace: F.serifEn,
    align: "left", valign: "top", margin: 14,
    fill: { color: C.creamLight },
    line: { color: C.rule, width: 0.5 },
  });

  // B. RAG_Ultimate 線
  s.addText("B.  RAG_Ultimate 線（partner research）", {
    x: 0.6 + colW + 0.4, y: colY, w: colW, h: 0.5,
    fontFace: F.serif, fontSize: 14, color: "F5F1E8",
    bold: true, charSpacing: 3,
    align: "left", valign: "middle", margin: 14,
    fill: { color: C.greenMid },
  });
  s.addText([
    {
      text: "Industrial Knowledge-Base RAG Benchmark for Wind Turbine O&M",
      options: { italic: true, fontSize: 13, color: C.ink, breakLine: true },
    },
    { text: " ", options: { fontSize: 6, breakLine: true } },
    { text: "→  IEEE Trans. Industrial Informatics", options: { fontSize: 11, color: C.greenDark, breakLine: true } },
    { text: " ", options: { fontSize: 12, breakLine: true } },
    {
      text: "Phase 3 進行中，windMindOM 提供應用場景驗證。",
      options: { fontSize: 11, color: C.inkSoft, italic: true, breakLine: true },
    },
    { text: " ", options: { fontSize: 8, breakLine: true } },
    {
      text: "兩條線可彼此引用、共享資料集，但獨立投稿，不互相依賴。",
      options: { fontSize: 11, color: C.inkSoft, italic: true },
    },
  ], {
    x: 0.6 + colW + 0.4, y: colY + 0.5, w: colW, h: colH - 0.5,
    fontFace: F.serif,
    align: "left", valign: "top", margin: 14,
    fill: { color: C.creamLight },
    line: { color: C.rule, width: 0.5 },
  });

  addJournalFooter(s, 11, TOTAL, "§ Appendix A1  /  論文線");
}

// ═══════════════════════════════════════════════════════════
// Appendix A2 — 計畫定位（學術版用）
// ═══════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.cream };
  addJournalHeader(s, "A2", "APPENDIX  —  計畫定位");
  addPageTitle(s, "Funding & Programme Fit", 1.15);

  const items = [
    {
      label: "國科會",
      title: "能源科技整合型計畫",
      body: "跨領域（電機 + AI + 工管 + 海洋工程）剛好打中。windMindOM 5 modules 對應「資料 + 決策 + 成本 + 知識」整合主題。",
    },
    {
      label: "能源署",
      title: "離岸風電在地化第三階段",
      body: "派工 / 庫存 / 簽核 = 在地化軟體可搶位置的技術項目。台灣供應鏈在地化評分有此類軟體加分項。",
    },
    {
      label: "教育部",
      title: "USR 大學社會責任",
      body: "Simulator 模式可打包成大學風能實驗室教材 — 配合 NCUT 智動系既有風能課程。",
    },
  ];

  const itY = 2.4;
  const itH = 1.25;
  items.forEach((it, i) => {
    const y = itY + i * (itH + 0.2);
    // 左：標籤
    s.addText(it.label, {
      x: 0.6, y, w: 1.6, h: itH,
      fontFace: F.serif, fontSize: 14, color: "F5F1E8",
      bold: true, charSpacing: 4,
      align: "center", valign: "middle", margin: 0,
      fill: { color: C.greenDark },
    });
    // 右：內容
    s.addText([
      { text: it.title, options: { fontSize: 16, bold: true, color: C.ink, breakLine: true } },
      { text: " ", options: { fontSize: 4, breakLine: true } },
      { text: it.body, options: { fontSize: 11, color: C.inkSoft } },
    ], {
      x: 2.3, y, w: SLIDE_W - 2.9, h: itH,
      fontFace: F.serif,
      align: "left", valign: "middle", margin: 14,
      fill: { color: C.creamLight },
      line: { color: C.rule, width: 0.5 },
    });
  });

  // 底部結語
  s.addShape(pres.shapes.LINE, {
    x: 0.6, y: 6.3, w: SLIDE_W - 1.2, h: 0,
    line: { color: C.rule, width: 0.5 },
  });
  s.addText("→  學術價值與商業價值不衝突 — 同一份 codebase，兩條 narrative。", {
    x: 0.6, y: 6.42, w: SLIDE_W - 1.2, h: 0.45,
    fontFace: F.serif, fontSize: 12, color: C.greenDark,
    italic: true, align: "center", valign: "middle", margin: 0,
  });

  addJournalFooter(s, 12, TOTAL, "§ Appendix A2  /  計畫");
}

// ─────────────────────────────────────────────
// 寫檔
// ─────────────────────────────────────────────
const outPath = path.resolve(__dirname, "../../docs/sales/pitch_deck_v0.8.1.pptx");
pres.writeFile({ fileName: outPath }).then((file) => {
  console.log(`✓ pptx 已生成：${file}`);
});
