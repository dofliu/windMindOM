/**
 * windMindOM v0.8.1 sales pitch deck builder.
 *
 * Theme: Navy (深藍科技風) — 頂部標題列 + 卡片網格 + 策略B 物件最小化。
 * Engine: pptxgenjs.
 * Output: ../../docs/sales/pitch_deck_v0.8.1.pptx
 *
 * Source-of-truth (依此撰寫，不自編數字):
 *   - docs/product/PRODUCT_VISION.md
 *   - docs/product/MVP_ARCHITECTURE.md
 *   - docs/product/ROADMAP.md
 *   - docs/product/decision_log.md DEC-20260502-06
 *
 * Issue: WMOM-20260503-04
 */

const path = require("path");
const PptxGenJS = require("pptxgenjs");

// ────────────────────────────────────────────
// Theme tokens — Navy (深藍科技風)
// ────────────────────────────────────────────
const C = {
  // Primary navy palette
  navyDeep: "0B2545",      // 主深色（封面背景、標題列）
  navyMid: "13315C",       // 次層深藍
  navyLite: "1E4E8C",      // 連結 / 強調
  // Accent
  cyan: "00B4D8",          // 科技感 cyan
  cyanSoft: "90E0EF",      // 柔化 cyan
  // Surface
  white: "FFFFFF",
  ivory: "F8FAFC",         // 卡片背景
  cardBorder: "E2E8F0",
  // Text
  textDark: "1E293B",
  textMid: "475569",
  textMute: "94A3B8",
  // Status
  success: "10B981",
  warn: "F59E0B",
  danger: "EF4444",
};

const FONT = "Microsoft JhengHei";

// 投影片尺寸 16:9 (13.33 × 7.5 inches)
const W = 13.33;
const H = 7.5;

// 標題列 (top bar) 規格
const BAR_H = 1.0;          // 高
const BAR_TITLE_PT = 26;
const BAR_SUB_PT = 13;

// Footer 規格
const FOOTER_H = 0.35;
const FOOTER_PT = 9;

const TOTAL = 10;

// ────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────

/** 內容頁的頂部 navy 標題列：標題 + 副標 + 章節編號（策略B：fill 直接在 text 上）*/
function addTitleBar(slide, title, subtitle, page) {
  // 一個 text 物件搞定整條 bar：fill = navy、左 padding 用 margin、右側放頁碼
  slide.addText(
    [
      { text: title, options: { bold: true, fontSize: BAR_TITLE_PT, color: C.white } },
      ...(subtitle ? [{ text: "  ", options: { fontSize: BAR_TITLE_PT } }, { text: subtitle, options: { fontSize: BAR_SUB_PT, color: C.cyanSoft } }] : []),
    ],
    {
      x: 0, y: 0, w: W, h: BAR_H,
      fill: { color: C.navyDeep },
      valign: "middle",
      align: "left",
      margin: [0, 0.5, 0, 0.5],
      fontFace: FONT,
    }
  );

  // 左側 cyan 強調條（純裝飾色塊例外，獨立 shape）
  slide.addShape("rect", {
    x: 0, y: 0, w: 0.18, h: BAR_H,
    fill: { color: C.cyan }, line: { type: "none" },
  });

  // 頁碼右上（策略B：直接 text 帶 fill 不必獨立）
  slide.addText(`${page} / ${TOTAL}`, {
    x: W - 1.2, y: 0.15, w: 1.0, h: 0.4,
    fontSize: 11, color: C.cyanSoft, fontFace: FONT,
    align: "right", valign: "middle",
  });
}

/** 內容頁底部 footer */
function addFooter(slide, leftText = "windMindOM v0.8.1 · DOF Lab") {
  slide.addText(leftText, {
    x: 0, y: H - FOOTER_H, w: W * 0.7, h: FOOTER_H,
    fontSize: FOOTER_PT, color: C.textMute, fontFace: FONT,
    align: "left", valign: "middle", margin: [0, 0, 0, 0.5],
  });
  slide.addText("dofliu / moredof@gmail.com", {
    x: W * 0.7, y: H - FOOTER_H, w: W * 0.3 - 0.5, h: FOOTER_H,
    fontSize: FOOTER_PT, color: C.textMute, fontFace: FONT,
    align: "right", valign: "middle", margin: [0, 0.5, 0, 0],
  });
}

// ════════════════════════════════════════════════
// Slide builders
// ════════════════════════════════════════════════

function buildCover(pres) {
  const s = pres.addSlide();
  // 全頁深 navy 背景
  s.background = { color: C.navyDeep };

  // 左側 cyan 強調縱條
  s.addShape("rect", { x: 0, y: 0, w: 0.25, h: H, fill: { color: C.cyan }, line: { type: "none" } });

  // 抽象圓點裝飾（右下角）— 模擬風機 / 散點
  for (let i = 0; i < 14; i++) {
    const cx = 9 + (i % 7) * 0.55;
    const cy = 5.6 + Math.floor(i / 7) * 0.55;
    s.addShape("ellipse", {
      x: cx, y: cy, w: 0.18, h: 0.18,
      fill: { color: i % 3 === 0 ? C.cyan : C.cyanSoft, transparency: 50 },
      line: { type: "none" },
    });
  }

  // 主標
  s.addText("windMindOM", {
    x: 0.8, y: 1.8, w: 11.5, h: 1.4,
    fontSize: 80, bold: true, color: C.white, fontFace: FONT,
    align: "left", valign: "middle",
  });

  // 副標
  s.addText("離岸風場運維廠商工具", {
    x: 0.8, y: 3.2, w: 11.5, h: 0.7,
    fontSize: 32, color: C.cyanSoft, fontFace: FONT,
    align: "left", valign: "middle",
  });

  // Tagline
  s.addText("從監控到月報，5 個 module 撐起運維廠商的一整天", {
    x: 0.8, y: 4.0, w: 11.5, h: 0.6,
    fontSize: 18, color: C.white, fontFace: FONT,
    align: "left", valign: "middle",
  });

  // 細分隔線（策略B：text 帶 fill 當薄分隔）
  s.addShape("rect", { x: 0.8, y: 5.0, w: 3.5, h: 0.04, fill: { color: C.cyan }, line: { type: "none" } });

  // 版本 / 作者資訊
  s.addText(
    [
      { text: "v0.8.1", options: { bold: true, color: C.cyan, fontSize: 14 } },
      { text: "  ·  2026-05-03", options: { color: C.cyanSoft, fontSize: 12 } },
      { text: "\nDof / DOF Lab", options: { color: C.white, fontSize: 14, bold: true } },
      { text: "  ·  國立勤益科技大學  智慧自動化工程系", options: { color: C.cyanSoft, fontSize: 12 } },
      { text: "\n副教授  劉瑞弘 (Juihung Liu)  ·  moredof@gmail.com", options: { color: C.cyanSoft, fontSize: 11 } },
    ],
    {
      x: 0.8, y: 5.2, w: 11.5, h: 1.6,
      fontFace: FONT, align: "left", valign: "top", paraSpaceBefore: 4,
    }
  );

  // 底部右下 confidential badge
  s.addText("CONFIDENTIAL  ·  for friendly customer demo", {
    x: 9.0, y: H - 0.45, w: 4.0, h: 0.3,
    fontSize: 9, color: C.textMute, fontFace: FONT,
    align: "right", valign: "middle", margin: [0, 0.3, 0, 0],
  });
}

function buildIcpPainPoints(pres) {
  const s = pres.addSlide();
  addTitleBar(s, "誰在用 windMindOM？", "離岸風場運維廠商，不是業主", 2);

  // 5 個痛點 — 左側編號 + 卡片
  const pains = [
    { num: "01", h: "SCADA 看了沒人用", b: "每天 200+ 條 alarm，沒有自動成本影響評估，工程師選擇性無視" },
    { num: "02", h: "警報靠 LINE 群組問師傅", b: "師傅請假就停擺，知識沒沉澱，新進工程師重複踩同一個坑" },
    { num: "03", h: "月報用 Excel 拼", b: "給業主前要熬夜整理 30+ 表，月底常通宵，錯一個數字要重做" },
    { num: "04", h: "庫存 / 派工 / 簽核分散在 3 套系統", b: "跨系統對帳困難，紙本與系統雙軌，月底盤點對不上" },
    { num: "05", h: "成本沒回寫", b: "明年預算抓不準，跟業主談判沒底氣，被砍價只能照單全收" },
  ];

  const startY = 1.3;
  const cardH = 0.92;
  const cardGap = 0.08;
  const cardW = 8.5;

  pains.forEach((p, i) => {
    const y = startY + i * (cardH + cardGap);
    // 編號方塊（策略B：text 帶 fill）
    s.addText(p.num, {
      x: 0.5, y, w: 0.9, h: cardH,
      fill: { color: C.navyDeep },
      color: C.cyan, fontSize: 24, bold: true,
      fontFace: FONT, align: "center", valign: "middle",
    });
    // 標題
    s.addText(p.h, {
      x: 1.5, y, w: cardW, h: cardH * 0.45,
      fontSize: 16, bold: true, color: C.textDark, fontFace: FONT,
      align: "left", valign: "bottom",
    });
    // 內容
    s.addText(p.b, {
      x: 1.5, y: y + cardH * 0.45, w: cardW, h: cardH * 0.55,
      fontSize: 11, color: C.textMid, fontFace: FONT,
      align: "left", valign: "top",
    });
  });

  // 右側 callout 區：市場脈絡
  const calX = 10.3;
  s.addText("市場時機", {
    x: calX, y: 1.3, w: 2.7, h: 0.4,
    fontSize: 12, bold: true, color: C.cyan, fontFace: FONT,
    align: "left", valign: "middle",
  });
  s.addText(
    [
      { text: "Formosa 1 / 2 (2025–2027)\n", options: { bold: true, fontSize: 14, color: C.white } },
      { text: "機組陸續出保 → 業主從 OEM 接受者轉為", options: { fontSize: 11, color: C.cyanSoft } },
      { text: "外包運維", options: { bold: true, fontSize: 11, color: C.white } },
      { text: "。\n\n", options: { fontSize: 11, color: C.cyanSoft } },
      { text: "運維廠商成為新 ICP，", options: { fontSize: 11, color: C.cyanSoft } },
      { text: "但市場上沒有為他們量身打造的工具。", options: { bold: true, fontSize: 11, color: C.white } },
    ],
    {
      x: calX, y: 1.7, w: 2.7, h: 5.0,
      fill: { color: C.navyDeep },
      fontFace: FONT, align: "left", valign: "top",
      margin: 14, paraSpaceBefore: 4,
    }
  );

  addFooter(s, "Slide 2  ·  ICP & Pain Points");
}

function buildSolution(pres) {
  const s = pres.addSlide();
  addTitleBar(s, "windMindOM = 一站式運維廠商工具", "3 個關鍵設計決策", 3);

  const decisions = [
    {
      no: "1",
      h: "5 個 monolithic modules",
      sub: "不是 plugin SDK",
      body: "monitoring / workflow / cost / reporting / knowledge 五件套\n→ 一個 dev 可維運的尺寸\n→ 不過度抽象、不造輪子",
    },
    {
      no: "2",
      h: "Simulator-first",
      sub: "killer feature for sales",
      body: "無實場可成立的 demo\n→ 客戶不用先簽合約 / 部署\n→ 14 台模擬風機 + 104 SCADA tags 隨時開跑",
    },
    {
      no: "3",
      h: "Z72 機型 reference",
      sub: "first paying customer",
      body: "digiWT 物理已驗證 18/21\n→ Bachmann PLC 已通\n→ 3 個 sister repos 吃過 Z72 真實資料",
    },
  ];

  const cardW = 4.0;
  const cardH = 4.5;
  const startX = 0.55;
  const gap = 0.28;
  const startY = 1.4;

  decisions.forEach((d, i) => {
    const x = startX + i * (cardW + gap);

    // 卡片底色（純裝飾，獨立 shape 例外）
    s.addShape("rect", {
      x, y: startY, w: cardW, h: cardH,
      fill: { color: C.ivory }, line: { color: C.cardBorder, pt: 1 },
    });

    // 大編號（策略B：text 帶 fill 為頂部色帶）
    s.addText(d.no, {
      x, y: startY, w: cardW, h: 0.95,
      fill: { color: C.navyDeep },
      color: C.cyan, fontSize: 44, bold: true,
      fontFace: FONT, align: "center", valign: "middle",
    });
    // 標題
    s.addText(d.h, {
      x: x + 0.2, y: startY + 1.05, w: cardW - 0.4, h: 0.55,
      fontSize: 18, bold: true, color: C.navyDeep, fontFace: FONT,
      align: "center", valign: "middle",
    });
    // 副標
    s.addText(d.sub, {
      x: x + 0.2, y: startY + 1.6, w: cardW - 0.4, h: 0.35,
      fontSize: 12, italic: true, color: C.textMid, fontFace: FONT,
      align: "center", valign: "middle",
    });
    // body
    s.addText(d.body, {
      x: x + 0.3, y: startY + 2.1, w: cardW - 0.6, h: cardH - 2.2,
      fontSize: 12, color: C.textDark, fontFace: FONT,
      align: "left", valign: "top", paraSpaceBefore: 6,
    });
  });

  // 底部 footnote
  s.addText("架構決策：DEC-20260502-06（v0.5 → v0.8.1 pivot — 廢除 plugin SDK / Workflow Hub / 4 類 Turbine Adapter）", {
    x: 0.55, y: 6.4, w: W - 1.1, h: 0.4,
    fontSize: 10, italic: true, color: C.textMid, fontFace: FONT,
    align: "center", valign: "middle",
  });

  addFooter(s, "Slide 3  ·  Solution Overview");
}

function buildModules(pres) {
  const s = pres.addSlide();
  addTitleBar(s, "5 Modules — 運維廠商工作鏈閉環", "monitoring · workflow · cost · reporting · knowledge", 4);

  const mods = [
    { name: "monitoring", icon: "M", oneLine: "SCADA + 物理模擬器", status: "✅ M1 ready", detail: "104 SCADA tags\n14 台模擬風機\nBachmann Z72 OPC", color: C.success },
    { name: "cost", icon: "$", oneLine: "成本計算 + LCOE", status: "M2 (2026-06)", detail: "從 ECN 移植\nforecast ⇄ actual\nMonte Carlo", color: C.cyan },
    { name: "workflow", icon: "W", oneLine: "庫存 + 派工 + 簽核", status: "M3-M4 (07-08)", detail: "Work order CRUD\n多階簽核\nInventory 雙寫", color: C.cyan },
    { name: "reporting", icon: "R", oneLine: "月報 PDF + 預算", status: "M4 (2026-08)", detail: "Monthly PDF\n年度預算\n業主交付", color: C.cyan },
    { name: "knowledge", icon: "K", oneLine: "警報手冊 RAG", status: "M5 (2026-09)", detail: "ChromaDB\n手冊檢索\nMobile-first", color: C.cyan },
  ];

  const cardW = 2.4;
  const cardH = 4.4;
  const gap = 0.15;
  const totalW = mods.length * cardW + (mods.length - 1) * gap;
  const startX = (W - totalW) / 2;
  const startY = 1.35;

  mods.forEach((m, i) => {
    const x = startX + i * (cardW + gap);

    // 卡片底
    s.addShape("rect", {
      x, y: startY, w: cardW, h: cardH,
      fill: { color: C.ivory }, line: { color: C.cardBorder, pt: 1 },
    });

    // 上半部 icon + name 區塊（策略B：text 帶 fill）
    s.addText(m.icon, {
      x, y: startY, w: cardW, h: 1.3,
      fill: { color: C.navyDeep },
      color: C.cyan, fontSize: 48, bold: true,
      fontFace: FONT, align: "center", valign: "middle",
    });

    // module name
    s.addText(m.name, {
      x: x + 0.1, y: startY + 1.4, w: cardW - 0.2, h: 0.5,
      fontSize: 17, bold: true, color: C.navyDeep, fontFace: FONT,
      align: "center", valign: "middle",
    });

    // one-liner
    s.addText(m.oneLine, {
      x: x + 0.1, y: startY + 1.95, w: cardW - 0.2, h: 0.45,
      fontSize: 11, color: C.textMid, fontFace: FONT,
      align: "center", valign: "middle",
    });

    // status badge（策略B：text 帶 fill）
    s.addText(m.status, {
      x: x + 0.3, y: startY + 2.5, w: cardW - 0.6, h: 0.38,
      fill: { color: m.color },
      color: C.white, fontSize: 10, bold: true,
      fontFace: FONT, align: "center", valign: "middle",
    });

    // detail
    s.addText(m.detail, {
      x: x + 0.2, y: startY + 3.0, w: cardW - 0.4, h: 1.3,
      fontSize: 10, color: C.textDark, fontFace: FONT,
      align: "center", valign: "top", paraSpaceBefore: 3,
    });
  });

  // 底部閉環流程 — 一條 text 表達
  s.addText("閉環流程：告警 → 工單 → 簽核 → 派工 → 完工 → 庫存扣帳 → cost actual → 月報自動產出", {
    x: 0.5, y: 6.2, w: W - 1.0, h: 0.6,
    fill: { color: C.navyDeep },
    fontSize: 13, bold: true, color: C.cyanSoft, fontFace: FONT,
    align: "center", valign: "middle",
  });

  addFooter(s, "Slide 4  ·  5 Modules");
}

function buildKillerFeature(pres) {
  const s = pres.addSlide();
  addTitleBar(s, "Killer Feature — 無實場可成立的 Demo", "Sales 殺手特性（競品做不到）", 5);

  // 左半：3 大 stat 卡片
  const stats = [
    { big: "104", unit: "SCADA tags", note: "與 Bachmann Z72 真實 PLC 一致\nIEC 61400-12-1/2 nacelle 校正" },
    { big: "14", unit: "台模擬風機", note: "完整物理：wake、fatigue、DEL、\nspectral vibration、yaw" },
    { big: "1", unit: "分鐘 demo", note: "不需先簽合約 / 部署 / 等實機資料\n打開 browser 就能 run" },
  ];

  const cardW = 4.0;
  const cardH = 1.7;
  const startX = 0.55;
  const startY = 1.4;

  stats.forEach((st, i) => {
    const y = startY + i * (cardH + 0.18);

    // 卡片底
    s.addShape("rect", {
      x: startX, y, w: cardW, h: cardH,
      fill: { color: C.ivory }, line: { color: C.cardBorder, pt: 1 },
    });

    // 左側大數字（策略B：text 帶 fill = navy 區塊）
    s.addText(st.big, {
      x: startX, y, w: 1.5, h: cardH,
      fill: { color: C.navyDeep },
      color: C.cyan, fontSize: 56, bold: true,
      fontFace: FONT, align: "center", valign: "middle",
    });
    // 單位
    s.addText(st.unit, {
      x: startX + 1.6, y: y + 0.15, w: cardW - 1.7, h: 0.5,
      fontSize: 16, bold: true, color: C.navyDeep, fontFace: FONT,
      align: "left", valign: "middle",
    });
    // note
    s.addText(st.note, {
      x: startX + 1.6, y: y + 0.65, w: cardW - 1.7, h: cardH - 0.7,
      fontSize: 11, color: C.textMid, fontFace: FONT,
      align: "left", valign: "top", paraSpaceBefore: 3,
    });
  });

  // 右半：3 個重點 + 競品對比
  const rX = 5.2;

  s.addText("為什麼這是 sales killer", {
    x: rX, y: 1.4, w: W - rX - 0.5, h: 0.45,
    fontSize: 16, bold: true, color: C.navyDeep, fontFace: FONT,
    align: "left", valign: "middle",
  });

  const points = [
    "客戶第一次見面 → 直接 demo，不用「等我們安裝」",
    "客戶內部評選 → 我們可以複製到他們會議室再 demo",
    "客戶 PoC 階段 → simulator 補實場資料缺口（前 6 個月）",
  ];

  points.forEach((p, i) => {
    const py = 1.95 + i * 0.55;
    s.addText("→", {
      x: rX, y: py, w: 0.4, h: 0.45,
      fontSize: 16, bold: true, color: C.cyan, fontFace: FONT,
      align: "center", valign: "middle",
    });
    s.addText(p, {
      x: rX + 0.5, y: py, w: W - rX - 1.0, h: 0.45,
      fontSize: 13, color: C.textDark, fontFace: FONT,
      align: "left", valign: "middle",
    });
  });

  // 競品 callout（策略B：text 帶 fill）
  s.addText(
    [
      { text: "競品對比：", options: { bold: true, fontSize: 12, color: C.cyan } },
      { text: "Bazefield / SkySpecs / ONYX InSight ", options: { fontSize: 11, color: C.cyanSoft } },
      { text: "全部需要實場 SCADA 才能 demo", options: { bold: true, fontSize: 11, color: C.white } },
      { text: "。客戶評選週期內，他們連「給看」都做不到。", options: { fontSize: 11, color: C.cyanSoft } },
    ],
    {
      x: rX, y: 5.4, w: W - rX - 0.5, h: 1.3,
      fill: { color: C.navyDeep },
      fontFace: FONT, align: "left", valign: "middle",
      margin: 14,
    }
  );

  addFooter(s, "Slide 5  ·  Killer Feature");
}

function buildPricing(pres) {
  const s = pres.addSlide();
  addTitleBar(s, "商業模式 — Operator 三層套餐", "依運維廠商規模分層", 6);

  const tiers = [
    {
      name: "Operator Basic",
      target: "小型運維廠商\n單一風場",
      modules: ["monitoring", "reporting", "knowledge"],
      price: "NT$30–60k",
      unit: "/turbine/年",
      featured: false,
    },
    {
      name: "Operator Pro",
      target: "中型運維廠商\n多風場",
      modules: ["+ workflow", "+ cost", "(含 Basic)"],
      price: "NT$60–100k",
      unit: "/turbine/年",
      featured: true,   // 預期主流套餐
    },
    {
      name: "Operator Enterprise",
      target: "大型運維廠商\n跨 OEM 機型",
      modules: ["+ AI 介接 (windAILab)", "+ InduSpect 視覺定檢", "(含 Pro)"],
      price: "NT$100–180k",
      unit: "/turbine/年",
      featured: false,
    },
  ];

  const cardW = 4.0;
  const cardH = 4.6;
  const gap = 0.28;
  const totalW = tiers.length * cardW + (tiers.length - 1) * gap;
  const startX = (W - totalW) / 2;
  const startY = 1.4;

  tiers.forEach((t, i) => {
    const x = startX + i * (cardW + gap);
    const isFeat = t.featured;

    // 卡片底
    s.addShape("rect", {
      x, y: startY, w: cardW, h: cardH,
      fill: { color: isFeat ? C.navyDeep : C.ivory },
      line: { color: isFeat ? C.cyan : C.cardBorder, pt: isFeat ? 2 : 1 },
    });

    // 標題色帶
    if (isFeat) {
      s.addText("RECOMMENDED", {
        x, y: startY, w: cardW, h: 0.35,
        fill: { color: C.cyan },
        color: C.navyDeep, fontSize: 10, bold: true,
        fontFace: FONT, align: "center", valign: "middle",
        charSpacing: 2,
      });
    }

    const titleY = isFeat ? startY + 0.5 : startY + 0.3;

    // 套餐名稱
    s.addText(t.name, {
      x: x + 0.2, y: titleY, w: cardW - 0.4, h: 0.55,
      fontSize: 20, bold: true,
      color: isFeat ? C.cyan : C.navyDeep,
      fontFace: FONT, align: "center", valign: "middle",
    });

    // 對象
    s.addText(t.target, {
      x: x + 0.2, y: titleY + 0.6, w: cardW - 0.4, h: 0.7,
      fontSize: 12,
      color: isFeat ? C.cyanSoft : C.textMid,
      fontFace: FONT, align: "center", valign: "middle",
      paraSpaceBefore: 2,
    });

    // 分隔線（裝飾色塊例外）
    s.addShape("rect", {
      x: x + 1.0, y: titleY + 1.4, w: cardW - 2.0, h: 0.02,
      fill: { color: isFeat ? C.cyan : C.cardBorder }, line: { type: "none" },
    });

    // 包含 modules
    const mList = t.modules.map((m) => `· ${m}`).join("\n");
    s.addText(mList, {
      x: x + 0.4, y: titleY + 1.55, w: cardW - 0.8, h: 1.3,
      fontSize: 12,
      color: isFeat ? C.white : C.textDark,
      fontFace: FONT, align: "left", valign: "top",
      paraSpaceBefore: 4,
    });

    // 價格大字（策略B：text 帶 fill）
    s.addText(t.price, {
      x: x + 0.2, y: startY + cardH - 1.05, w: cardW - 0.4, h: 0.6,
      fontSize: 26, bold: true,
      color: isFeat ? C.cyan : C.navyDeep,
      fontFace: FONT, align: "center", valign: "middle",
    });
    s.addText(t.unit, {
      x: x + 0.2, y: startY + cardH - 0.45, w: cardW - 0.4, h: 0.35,
      fontSize: 11,
      color: isFeat ? C.cyanSoft : C.textMid,
      fontFace: FONT, align: "center", valign: "middle",
    });
  });

  // 底部 deal size note
  s.addText("第一筆合約目標：NT$ 2–4M（Basic 或 Pro 等級，14 台風機 × 1 年）  ·  目標時間：2026 Q4", {
    x: 0.55, y: 6.4, w: W - 1.1, h: 0.4,
    fontSize: 11, italic: true, color: C.textMid, fontFace: FONT,
    align: "center", valign: "middle",
  });

  addFooter(s, "Slide 6  ·  Pricing Tiers");
}

function buildCompetitors(pres) {
  const s = pres.addSlide();
  addTitleBar(s, "沒有競品同時涵蓋這 8 列", "市場上沒有 windMindOM-equivalent 工具", 7);

  // pptxgenjs 表格
  const headerStyle = { bold: true, color: C.white, fill: { color: C.navyDeep }, fontSize: 11, valign: "middle", align: "center" };
  const rowHeaderStyle = { bold: true, color: C.navyDeep, fill: { color: C.ivory }, fontSize: 11, valign: "middle", align: "left" };
  const cellStyle = { fontSize: 11, color: C.textMid, valign: "middle", align: "center" };
  const ourCellStyle = { fontSize: 11, bold: true, color: C.navyDeep, fill: { color: C.cyanSoft }, valign: "middle", align: "center" };

  const rows = [
    [
      { text: "能力 \\ 競品", options: headerStyle },
      { text: "SkySpecs\n(US)", options: headerStyle },
      { text: "Bazefield\n(NO)", options: headerStyle },
      { text: "ONYX InSight\n(UK)", options: headerStyle },
      { text: "SAP PM", options: headerStyle },
      { text: "windMindOM", options: { ...headerStyle, fill: { color: C.cyan }, color: C.navyDeep } },
    ],
    [
      { text: "SCADA 監控", options: rowHeaderStyle },
      { text: "部分", options: cellStyle },
      { text: "✓✓", options: cellStyle },
      { text: "部分", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "✓✓", options: ourCellStyle },
    ],
    [
      { text: "AI 故障診斷 + RAG", options: rowHeaderStyle },
      { text: "✓ 葉片", options: cellStyle },
      { text: "✓", options: cellStyle },
      { text: "✓ gearbox", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "✓ Z72", options: ourCellStyle },
    ],
    [
      { text: "派工 / 工單", options: rowHeaderStyle },
      { text: "—", options: cellStyle },
      { text: "✓", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "✓✓", options: cellStyle },
      { text: "✓ M3", options: ourCellStyle },
    ],
    [
      { text: "庫存", options: rowHeaderStyle },
      { text: "—", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "✓✓", options: cellStyle },
      { text: "✓ M4", options: ourCellStyle },
    ],
    [
      { text: "多階簽核", options: rowHeaderStyle },
      { text: "—", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "✓", options: cellStyle },
      { text: "✓ M3", options: ourCellStyle },
    ],
    [
      { text: "成本回寫 LCOE", options: rowHeaderStyle },
      { text: "—", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "部分", options: cellStyle },
      { text: "✓ M2", options: ourCellStyle },
    ],
    [
      { text: "Simulator demo", options: rowHeaderStyle },
      { text: "—", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "✓✓ killer", options: { ...ourCellStyle, fill: { color: C.cyan } } },
    ],
    [
      { text: "月報自動化", options: rowHeaderStyle },
      { text: "—", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "—", options: cellStyle },
      { text: "✓ M4", options: ourCellStyle },
    ],
  ];

  s.addTable(rows, {
    x: 0.5, y: 1.35, w: W - 1.0,
    colW: [3.0, 1.65, 1.65, 1.83, 1.55, 2.65],
    rowH: 0.42,
    fontFace: FONT,
    border: { type: "solid", color: C.cardBorder, pt: 0.5 },
  });

  // 底部 USP 結論
  s.addText(
    [
      { text: "4 條 USP：", options: { bold: true, fontSize: 13, color: C.cyan } },
      { text: "完整工作鏈閉環  ·  Simulator-first demo  ·  在地化派工簽核  ·  ECN 成本雙向回寫", options: { bold: true, fontSize: 12, color: C.white } },
    ],
    {
      x: 0.5, y: 6.4, w: W - 1.0, h: 0.55,
      fill: { color: C.navyDeep },
      fontFace: FONT, align: "center", valign: "middle",
    }
  );

  addFooter(s, "Slide 7  ·  Competitive Matrix");
}

function buildZ72(pres) {
  const s = pres.addSlide();
  addTitleBar(s, "第一個客戶：Z72 機型運維廠商", "為什麼選 Z72 為首發？", 8);

  const reasons = [
    {
      tag: "01",
      h: "digiWT 物理已驗證",
      b: "18 / 21 quality check 通過\n104 SCADA tags 對齊真實 Bachmann Z72 PLC\nIEC 61400-12-1/2 nacelle anemometer / vane 校正完整",
    },
    {
      tag: "02",
      h: "無 OEM 阻擋",
      b: "Harakosan / Zephyros 已退出市場\n沒有原廠擋客戶\nbundle 銷售壓力 = 0",
    },
    {
      tag: "03",
      h: "Bachmann PLC 連線已通",
      b: "z72hmiNew 實機運轉中\nopc_bachmann 模組可直接用\n從 simulator → 實場切換最快",
    },
    {
      tag: "04",
      h: "3 個 sister repos 吃過真實資料",
      b: "z72_etech (派工設計參考)\nz72hmiNew (HMI / 真實 PLC)\ndigiWindTurbine (物理 baseline)",
    },
  ];

  // 2x2 grid
  const cardW = 6.0;
  const cardH = 2.05;
  const gapX = 0.3;
  const gapY = 0.2;
  const startX = (W - 2 * cardW - gapX) / 2;
  const startY = 1.35;

  reasons.forEach((r, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = startX + col * (cardW + gapX);
    const y = startY + row * (cardH + gapY);

    // 卡片底
    s.addShape("rect", {
      x, y, w: cardW, h: cardH,
      fill: { color: C.ivory }, line: { color: C.cardBorder, pt: 1 },
    });

    // tag 數字（策略B：text 帶 fill）
    s.addText(r.tag, {
      x, y, w: 0.95, h: cardH,
      fill: { color: C.navyDeep },
      color: C.cyan, fontSize: 30, bold: true,
      fontFace: FONT, align: "center", valign: "middle",
    });

    // 標題
    s.addText(r.h, {
      x: x + 1.1, y: y + 0.15, w: cardW - 1.2, h: 0.55,
      fontSize: 15, bold: true, color: C.navyDeep, fontFace: FONT,
      align: "left", valign: "middle",
    });
    // body
    s.addText(r.b, {
      x: x + 1.1, y: y + 0.7, w: cardW - 1.2, h: cardH - 0.8,
      fontSize: 11, color: C.textMid, fontFace: FONT,
      align: "left", valign: "top", paraSpaceBefore: 3,
    });
  });

  // 底部時間軸
  s.addText(
    [
      { text: "時間軸：", options: { bold: true, fontSize: 12, color: C.cyan } },
      { text: "2026 Q3 friendly pilot 上線", options: { fontSize: 12, color: C.white } },
      { text: "  →  ", options: { fontSize: 12, color: C.cyan, bold: true } },
      { text: "2026 Q4 第一筆合約 NT$ 2–4M", options: { bold: true, fontSize: 12, color: C.white } },
    ],
    {
      x: 0.55, y: 6.3, w: W - 1.1, h: 0.55,
      fill: { color: C.navyDeep },
      fontFace: FONT, align: "center", valign: "middle",
    }
  );

  addFooter(s, "Slide 8  ·  First Customer (Z72)");
}

function buildRoadmap(pres) {
  const s = pres.addSlide();
  addTitleBar(s, "6 個月 Roadmap", "M1 → M6 / 2026-05 → 2026-10  ·  一日一項重要工作", 9);

  const months = [
    { m: "M1", d: "2026-05", title: "Setup", deliv: "repo baseline\n規劃文件就位\nfriendly 客戶接觸", status: "✅ 進行中" },
    { m: "M2", d: "2026-06", title: "Cost", deliv: "K13 demo 跑通\nLCOE dashboard\n從 ECN 移植", status: "⏳ 排程中" },
    { m: "M3", d: "2026-07", title: "Workflow Pt1", deliv: "Work Order CRUD\n多階簽核\n從 z72_etech 取設計", status: "⏳ 排程中" },
    { m: "M4", d: "2026-08", title: "Workflow Pt2 + Reporting", deliv: "Inventory 雙寫\n月報 PDF 自動化\nCost ↔ Workflow 雙向", status: "⏳ 排程中" },
    { m: "M5", d: "2026-09", title: "Knowledge / RAG", deliv: "警報 → 30 秒查手冊\nMobile-first UI\nChromaDB 整合", status: "⏳ 排程中" },
    { m: "M6", d: "2026-10", title: "PoC + 第一筆合約", deliv: "Z72 運維廠商部署\n第一份月報送業主\nLOI / 簽合約", status: "🎯 KPI" },
  ];

  // Horizontal timeline — 6 columns
  const cardW = 1.95;
  const cardH = 4.6;
  const gap = 0.13;
  const totalW = months.length * cardW + (months.length - 1) * gap;
  const startX = (W - totalW) / 2;
  const startY = 1.4;

  // 整條 timeline 底色橫條（裝飾）
  s.addShape("rect", {
    x: startX - 0.1, y: startY + 0.5, w: totalW + 0.2, h: 0.04,
    fill: { color: C.cyan }, line: { type: "none" },
  });

  months.forEach((mo, i) => {
    const x = startX + i * (cardW + gap);

    // 上方圓點（裝飾）
    s.addShape("ellipse", {
      x: x + cardW / 2 - 0.15, y: startY + 0.4, w: 0.3, h: 0.3,
      fill: { color: C.cyan }, line: { color: C.white, pt: 2 },
    });

    // M 編號 + 月份
    s.addText(mo.m, {
      x, y: startY + 0.85, w: cardW, h: 0.5,
      fontSize: 22, bold: true, color: C.navyDeep, fontFace: FONT,
      align: "center", valign: "middle",
    });
    s.addText(mo.d, {
      x, y: startY + 1.35, w: cardW, h: 0.32,
      fontSize: 10, color: C.textMid, fontFace: FONT,
      align: "center", valign: "middle",
    });

    // 卡片本體
    s.addShape("rect", {
      x, y: startY + 1.75, w: cardW, h: cardH - 1.85,
      fill: { color: C.ivory }, line: { color: C.cardBorder, pt: 1 },
    });

    // module 標題（策略B：fill on text）
    s.addText(mo.title, {
      x, y: startY + 1.75, w: cardW, h: 0.5,
      fill: { color: C.navyDeep },
      color: C.cyan, fontSize: 11, bold: true, fontFace: FONT,
      align: "center", valign: "middle",
    });

    // deliverable 內文
    s.addText(mo.deliv, {
      x: x + 0.1, y: startY + 2.3, w: cardW - 0.2, h: 1.55,
      fontSize: 9.5, color: C.textDark, fontFace: FONT,
      align: "left", valign: "top", paraSpaceBefore: 3,
    });

    // status badge（策略B）
    s.addText(mo.status, {
      x: x + 0.1, y: startY + 3.95, w: cardW - 0.2, h: 0.35,
      fontSize: 9, bold: true, color: i === 0 ? C.success : (i === 5 ? C.warn : C.textMid),
      fontFace: FONT, align: "center", valign: "middle",
    });
  });

  // 底部 philosophy
  s.addText("每月一個 demo-able deliverable — 避免到 Month 6 才發現方向錯", {
    x: 0.55, y: 6.4, w: W - 1.1, h: 0.4,
    fontSize: 11, italic: true, color: C.textMid, fontFace: FONT,
    align: "center", valign: "middle",
  });

  addFooter(s, "Slide 9  ·  Roadmap M1-M6");
}

function buildAsk(pres) {
  const s = pres.addSlide();
  addTitleBar(s, "我們需要什麼", "3 大 ask  ·  讓 windMindOM 走出實驗室", 10);

  const asks = [
    {
      h: "Friendly Pilot 客戶  1–2 家",
      sub: "Z72 機型運維廠商優先",
      give: "• simulator demo\n• 9 個月免費 PoC\n• 第一份月報協助製作",
      want: "• 實場 SCADA 連線\n• 1 位現場工程師參與測試\n• 真實警報資料用作 RAG 訓練",
    },
    {
      h: "業主介紹",
      sub: "建立運維廠商信任",
      give: "• 介紹費 / 共同 marketing\n• 業主端報表客製\n• 學界品牌背書",
      want: "• 介紹給已外包維運的業主\n• 引介到風電產業協會\n• 競爭對手分析資料",
    },
    {
      h: "計畫資源",
      sub: "國科會整合型計畫",
      give: "• 共同申請 PI / co-PI\n• 學術發表（Q1 期刊）\n• 學生人力支援",
      want: "• 共同申請 2026 下半年計畫\n• 加速 M5 RAG / M6 部署\n• 跨領域團隊資源",
    },
  ];

  const cardW = 4.0;
  const cardH = 4.5;
  const gap = 0.28;
  const totalW = asks.length * cardW + (asks.length - 1) * gap;
  const startX = (W - totalW) / 2;
  const startY = 1.35;

  asks.forEach((a, i) => {
    const x = startX + i * (cardW + gap);

    // 卡片底
    s.addShape("rect", {
      x, y: startY, w: cardW, h: cardH,
      fill: { color: C.ivory }, line: { color: C.cardBorder, pt: 1 },
    });

    // 標題色帶（策略B：fill on text）
    s.addText(`${i + 1}`, {
      x, y: startY, w: 0.9, h: 0.95,
      fill: { color: C.navyDeep },
      color: C.cyan, fontSize: 32, bold: true,
      fontFace: FONT, align: "center", valign: "middle",
    });

    // 主標
    s.addText(a.h, {
      x: x + 1.0, y: startY + 0.1, w: cardW - 1.1, h: 0.55,
      fontSize: 15, bold: true, color: C.navyDeep, fontFace: FONT,
      align: "left", valign: "middle",
    });
    // 副標
    s.addText(a.sub, {
      x: x + 1.0, y: startY + 0.55, w: cardW - 1.1, h: 0.4,
      fontSize: 11, italic: true, color: C.textMid, fontFace: FONT,
      align: "left", valign: "middle",
    });

    // give / want 雙欄
    const giveY = startY + 1.15;
    s.addText("我們提供", {
      x: x + 0.2, y: giveY, w: cardW - 0.4, h: 0.35,
      fill: { color: C.cyan },
      color: C.navyDeep, fontSize: 11, bold: true, fontFace: FONT,
      align: "center", valign: "middle",
      charSpacing: 1,
    });
    s.addText(a.give, {
      x: x + 0.25, y: giveY + 0.4, w: cardW - 0.5, h: 1.25,
      fontSize: 10.5, color: C.textDark, fontFace: FONT,
      align: "left", valign: "top", paraSpaceBefore: 3,
    });

    const wantY = giveY + 1.75;
    s.addText("您協助", {
      x: x + 0.2, y: wantY, w: cardW - 0.4, h: 0.35,
      fill: { color: C.navyDeep },
      color: C.cyan, fontSize: 11, bold: true, fontFace: FONT,
      align: "center", valign: "middle",
      charSpacing: 1,
    });
    s.addText(a.want, {
      x: x + 0.25, y: wantY + 0.4, w: cardW - 0.5, h: 1.25,
      fontSize: 10.5, color: C.textDark, fontFace: FONT,
      align: "left", valign: "top", paraSpaceBefore: 3,
    });
  });

  // 底部 contact 條
  s.addText(
    [
      { text: "Dof  ·  DOF Lab  ·  ", options: { fontSize: 12, color: C.cyanSoft } },
      { text: "國立勤益科技大學  智慧自動化工程系", options: { bold: true, fontSize: 12, color: C.white } },
      { text: "    |    ", options: { fontSize: 12, color: C.textMute } },
      { text: "副教授  劉瑞弘 (Juihung Liu)", options: { bold: true, fontSize: 12, color: C.white } },
      { text: "    |    ", options: { fontSize: 12, color: C.textMute } },
      { text: "moredof@gmail.com", options: { fontSize: 12, color: C.cyan } },
      { text: "  ·  github.com/dofliu  ·  doflab.cc", options: { fontSize: 12, color: C.cyanSoft } },
    ],
    {
      x: 0.3, y: 6.3, w: W - 0.6, h: 0.55,
      fill: { color: C.navyDeep },
      fontFace: FONT, align: "center", valign: "middle",
    }
  );

  addFooter(s, "Slide 10  ·  Ask & Contact");
}

// ════════════════════════════════════════════════
// Main
// ════════════════════════════════════════════════

async function main() {
  const pres = new PptxGenJS();
  pres.layout = "LAYOUT_WIDE";   // 13.33 × 7.5 (16:9)
  pres.title = "windMindOM v0.8.1 Pitch Deck";
  pres.author = "Dof / DOF Lab · 劉瑞弘";
  pres.subject = "離岸風場運維廠商工具 — sales pitch deck";
  pres.company = "DOF Lab · 國立勤益科技大學";

  buildCover(pres);
  buildIcpPainPoints(pres);
  buildSolution(pres);
  buildModules(pres);
  buildKillerFeature(pres);
  buildPricing(pres);
  buildCompetitors(pres);
  buildZ72(pres);
  buildRoadmap(pres);
  buildAsk(pres);

  const outPath = path.resolve(__dirname, "..", "..", "docs", "sales", "pitch_deck_v0.8.1.pptx");
  await pres.writeFile({ fileName: outPath });
  console.log(`[pitch_deck] wrote ${outPath}`);
}

main().catch((e) => {
  console.error("[pitch_deck] FAIL:", e);
  process.exit(1);
});
