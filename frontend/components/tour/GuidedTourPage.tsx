/**
 * GuidedTourPage — app 內「情境導覽模式」（WMOM-20260513-02 / 接 review DemoOrchestrator）。
 *
 * 目的：對運維廠商展示時，用**真實 UI 元件庫**（Card / Stat / StatusPill / Btn /
 * MiniSparkline）+ theme palette 演一遍情境，讓觀眾看到的就是產品本身的操作介面，
 * 而不是外掛的簡報 mockup。純前端、scripted demo 資料，不依賴 backend——simulator-first
 * 精神下，無實場也能演。
 *
 * 情境（比原 3 個更多）：監控總覽 → 告警 RAG → 工單閉環 → 安全庫存自動叫料 → 月報。
 * 導覽以「步驟」推進：上方章節列 + ← → 鍵 + 上下步。
 */

import React, { useCallback, useEffect, useState } from 'react';

import { useTheme } from '../../theme/ThemeProvider';
import type { Lang } from '../../hooks/useI18n';
import {
  Btn,
  Card,
  MiniSparkline,
  PageHeader,
  Stat,
  StatusPill,
} from '../ui';

interface Props {
  lang: Lang;
}

type Tri = 'pain' | 'move' | 'gain';

/** 情境舞台的左右分欄：左敘事、右模擬產品畫面。 */
const Split: React.FC<{ story: React.ReactNode; mock: React.ReactNode }> = ({ story, mock }) => (
  <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 28, alignItems: 'center' }}>
    <div>{story}</div>
    <div>{mock}</div>
  </div>
);

const GuidedTourPage: React.FC<Props> = ({ lang }) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);
  const [step, setStep] = useState(0);

  const chapters = [
    ui('Start', '開場'),
    ui('Farm Overview', '監控總覽'),
    ui('Alarm → Manual', '告警查手冊'),
    ui('Work Order Loop', '工單閉環'),
    ui('Low Stock', '安全庫存'),
    ui('Monthly Report', '月報'),
    ui('Five Modules', '五模組'),
  ];
  const N = chapters.length;

  const go = useCallback((n: number) => setStep(Math.max(0, Math.min(N - 1, n))), [N]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') { e.preventDefault(); setStep((s) => Math.min(N - 1, s + 1)); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); setStep((s) => Math.max(0, s - 1)); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [N]);

  // ── small presentational helpers ────────────────────────────────
  const Eyebrow: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <div style={{ fontSize: 11, letterSpacing: 2, textTransform: 'uppercase', color: C.sub, fontWeight: 600 }}>
      {children}
    </div>
  );

  const ModChip: React.FC<{ children: React.ReactNode; lit?: boolean }> = ({ children, lit }) => (
    <span style={{
      fontSize: 11, padding: '3px 9px', borderRadius: 999,
      background: lit ? C.accentSoft : C.panelMuted,
      color: lit ? C.accent : C.sub,
      border: `1px solid ${lit ? 'transparent' : C.border}`,
      fontWeight: lit ? 600 : 400,
    }}>{children}</span>
  );

  const Beat: React.FC<{ kind: Tri; children: React.ReactNode }> = ({ kind, children }) => {
    const map = {
      pain: { fg: C.danger, bg: C.dangerSoft, t: ui('NOW', '現在') },
      move: { fg: C.accent, bg: C.accentSoft, t: ui('WITH', '用了之後') },
      gain: { fg: C.ok, bg: C.okSoft, t: ui('WIN', '幫到廠商') },
    }[kind];
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 12, alignItems: 'start' }}>
        <span style={{
          fontSize: 10.5, letterSpacing: 1, textTransform: 'uppercase', fontWeight: 700,
          padding: '4px 8px', borderRadius: 7, color: map.fg, background: map.bg, marginTop: 2, whiteSpace: 'nowrap',
        }}>{map.t}</span>
        <p style={{ margin: 0, fontSize: 14.5, color: C.text }}>{children}</p>
      </div>
    );
  };

  const Story: React.FC<{
    mods: [string, boolean][]; kicker: string; title: string; lede: string;
    beats: [Tri, React.ReactNode][];
  }> = ({ mods, kicker, title, lede, beats }) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {mods.map(([m, lit]) => <ModChip key={m} lit={lit}>{m}</ModChip>)}
      </div>
      <div>
        <Eyebrow>{kicker}</Eyebrow>
        <h2 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 30, lineHeight: 1.12, letterSpacing: '-0.01em', margin: '6px 0 10px', color: C.text }}>{title}</h2>
        <p style={{ margin: 0, fontSize: 15, color: C.sub, maxWidth: '46ch' }}>{lede}</p>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {beats.map(([k, txt], i) => <Beat key={i} kind={k}>{txt}</Beat>)}
      </div>
    </div>
  );

  const Row: React.FC<{ label: React.ReactNode; value: React.ReactNode }> = ({ label, value }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', border: `1px solid ${C.border}`, borderRadius: 10, background: C.panelMuted, fontSize: 13 }}>
      <span style={{ color: C.sub }}>{label}</span>
      <span style={{ marginLeft: 'auto', fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{value}</span>
    </div>
  );

  const mono: React.CSSProperties = { fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace', fontVariantNumeric: 'tabular-nums' };

  // ── stage per step ──────────────────────────────────────────────
  const stage = (): React.ReactNode => {
    switch (step) {
      case 0:
        return (
          <div style={{ textAlign: 'center', maxWidth: 720, margin: '0 auto', padding: 8 }}>
            <Eyebrow>{ui('Offshore wind O&M tool', '離岸風場運維廠商工具')}</Eyebrow>
            <h1 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 'clamp(30px,5vw,50px)', lineHeight: 1.05, letterSpacing: '-0.02em', margin: '10px 0 14px', color: C.text }}>
              {ui('An operator console your team can actually read.', '把散在 Excel＋LINE＋紙單的運維，收進一個看得懂的操作台')}
            </h1>
            <p style={{ fontSize: 16, color: C.sub, maxWidth: '52ch', margin: '0 auto 22px' }}>
              {ui('Monitoring, dispatch, cost, reports and alarm-manual search — five modules, one flow. Here is a real vendor day in five scenes.', '監控、派工、成本、報表、警報查手冊——五個模組串成一條龍。以下用運維廠商真實的一天，走五個情境。')}
            </p>
            <div style={{ display: 'flex', gap: 9, flexWrap: 'wrap', justifyContent: 'center', marginBottom: 24 }}>
              <StatusPill tone="accent">{ui('👷 Field engineer', '👷 現場工程師')}</StatusPill>
              <StatusPill tone="info">{ui('🧑‍💼 Management', '🧑‍💼 管理層')}</StatusPill>
            </div>
            <Btn variant="primary" onClick={() => go(1)}>{ui('Start tour →', '開始導覽 →')}</Btn>
            <p style={{ fontSize: 11, color: C.faint, marginTop: 18 }}>{ui('Use ← → keys, or the chapters above', '用 ← → 方向鍵，或點上方章節')}</p>
          </div>
        );
      case 1:
        return (
          <Split
            story={<Story
              mods={[['monitoring', true], ['SCADA', true], ['physics sim', true]]}
              kicker={ui('Scene 1 · The console', '情境一 · 監控總覽')}
              title={ui('14 turbines, live — even without a real farm', '14 台機組即時上線，連真實風場都不用先接')}
              lede={ui('SCADA + a physics simulator drive the whole console, so you can demo before any site is wired.', 'SCADA ＋物理模擬器撐起整個操作台，沒接實場也能先 demo。')}
              beats={[
                ['pain', ui('Data scattered across screens; no single place to see the farm.', '資料散在各處，沒有一個地方看得到整場。')],
                ['move', ui('One overview: availability, output, alarms — turbine by turbine.', '一頁總覽：稼動率、發電、告警，逐台看。')],
                ['gain', ui('Simulator-first: a full demo without touching the customer PLC.', 'Simulator-first：不碰客戶 PLC 就能完整展示。')],
              ]}
            />}
            mock={
              <Card padding={16}>
                <PageHeader title={ui('Farm Overview', '風場總覽')} sub="CH-Offshore-01" />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10, marginBottom: 12 }}>
                  <Stat label={ui('Availability', '稼動率')} value="97.2" unit="%" highlight />
                  <Stat label={ui('Output', '總發電')} value="42.6" unit="MW" />
                  <Stat label={ui('Active alarms', '告警')} value="1" valueColor={C.warn} />
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
                  <StatusPill tone="ok">WT-01 ~ 06 · {ui('Running', '運轉')}</StatusPill>
                  <StatusPill tone="warn">WT-07 · {ui('Alarm', '告警')}</StatusPill>
                  <StatusPill tone="info">WT-08 ~ 14 · {ui('Running', '運轉')}</StatusPill>
                </div>
                <div style={{ fontSize: 11, color: C.sub, marginBottom: 6 }}>{ui('Farm output · last 24h', '全場出力 · 近 24h')}</div>
                <MiniSparkline values={[38, 40, 39, 42, 44, 43, 45, 42, 41, 43, 46, 44]} color={C.accent} height={40} fill />
              </Card>
            }
          />
        );
      case 2:
        return (
          <Split
            story={<Story
              mods={[['monitoring', true], ['knowledge · RAG', true], ['field mobile', true]]}
              kicker={ui('Scene 2 · The 3am alarm', '情境二 · 凌晨的告警')}
              title={ui('Alarm at night → the fix in 30 seconds', '半夜跳告警，30 秒查到怎麼處理')}
              lede={ui('A gearbox alarm fires. The scary part is not the repair — it is not knowing whether to act, with no one to ask.', '齒輪箱告警跳出。最怕的不是修，是不知道該不該動、又找不到人問。')}
              beats={[
                ['pain', ui('Photo to the LINE group; the senior tech is asleep / off-site / gone. Machine sits idle for 30 min.', '拍照丟 LINE 問師傅——師傅在睡覺／在別的場／已離職，機組掛著等半小時。')],
                ['move', ui('The alarm auto-searches the Z72 manual (531-chunk vectors) and returns the SOP + past-alarm history in 30s.', '告警自動查 Z72 手冊（531 段向量），30 秒給出 SOP＋過去同類告警歷史。')],
                ['gain', ui('Judge without the veteran — less downtime, fewer wrong tear-downs.', '不靠老師傅也能判斷——縮短停機、少誤拆。')],
              ]}
            />}
            mock={
              <Card tone="warn" padding={16}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <StatusPill colorBg={C.dangerSoft} colorFg={C.danger}>● Critical</StatusPill>
                  <span style={{ marginLeft: 'auto', ...mono, fontSize: 12, color: C.sub }}>WT-07 · 08:12</span>
                </div>
                <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 2, color: C.text }}>{ui('Gearbox bearing temp high', '齒輪箱軸承溫度過高')}</div>
                <div style={{ fontSize: 13, color: C.sub, marginBottom: 14 }}>Gearbox Brg Temp High · <span style={{ ...mono, color: C.danger, fontWeight: 700 }}>87.4°C</span> ({ui('limit', '門檻')} 82°C)</div>
                <Card tone="accent" padding={13}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <span style={{ fontWeight: 700, color: C.accent, fontSize: 13 }}>📖 {ui('Manual · instant', '手冊即時查詢')}</span>
                    <span style={{ marginLeft: 'auto', ...mono, fontSize: 11, color: C.accent }}>RAG · 0.8s</span>
                  </div>
                  <div style={{ ...mono, fontSize: 10.5, color: C.accent, fontWeight: 700, marginBottom: 3 }}>Z72 User Manual · §4.3</div>
                  <div style={{ fontSize: 12.5, color: C.text }}>{ui('Check coolant level and pump first; if low, top up and watch 10 min before deciding to stop.', '先確認冷卻液液位與循環泵；若液位偏低，補充後觀察 10 分鐘再決定是否停機。')}</div>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 10, paddingTop: 10, borderTop: `1px dashed ${C.border}` }}>
                    <span style={{ ...mono, fontSize: 20, fontWeight: 800, color: C.text }}>5</span>
                    <span style={{ fontSize: 12, color: C.sub }}>{ui('same alarm in 6 mo — 3× was low coolant → check that first', '近 6 月同類 5 次 · 其中 3 次是冷卻液不足 → 建議先查')}</span>
                  </div>
                </Card>
                <div style={{ marginTop: 12 }}><Btn variant="primary" fullWidth onClick={() => go(3)}>{ui('Create work order →', '一鍵生工單 →')}</Btn></div>
              </Card>
            }
          />
        );
      case 3:
        return (
          <Split
            story={<Story
              mods={[['workflow', true], ['inventory', true], ['cost', true]]}
              kicker={ui('Scene 3 · Dispatch to close', '情境三 · 派工到閉環')}
              title={ui('One work order — parts, cost and sign-off all on the record', '一張工單，料、錢、簽核全程有帳可查')}
              lede={ui('From alarm to work order: dispatch, deduct stock, book cost, multi-stage sign-off — every step has state and an audit trail.', '從告警一鍵生工單，走派工、扣料、算成本、多階簽核——每步都有狀態、有人、有稽核。')}
              beats={[
                ['pain', ui('Verbal dispatch, paper picking, stock unknown, cost guessed in Excel at month end.', '口頭派工、紙本領料、料剩幾顆沒人清楚、成本月底用 Excel 湊。')],
                ['move', ui('Sign + photo on completion; stock deducts instantly; cost books at the price locked on dispatch.', '完工簽名＋拍照；出庫即時扣帳；成本鎖派工當下單價寫回帳本。')],
                ['gain', ui('Parts stop being a black hole, cost is real-time, accountability is clear.', '料不再黑洞、成本即時、責任清楚。')],
              ]}
            />}
            mock={
              <Card padding={16}>
                <PageHeader title={<span style={mono}>WO-2026-0142</span>} sub={ui('WT-07 gearbox coolant top-up', 'WT-07 齒輪箱冷卻液補充')} />
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                  {['DRAFT', 'DISPATCHED', 'IN_PROGRESS'].map((s) => <StatusPill key={s} tone="ok" size="sm">{s} ✓</StatusPill>)}
                  <StatusPill tone="accent" size="sm">AWAITING_SIGNOFF</StatusPill>
                  <StatusPill tone="info" size="sm">CLOSED</StatusPill>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <Row label={ui('🧊 Pick · coolant GL-32', '🧊 領料 · 冷卻液 GL-32')} value={<span>×2 <span style={{ color: C.warn }}>{ui('stock 12 → 10', '庫存 12 → 10')}</span></span>} />
                  <Row label={ui('💰 Cost (parts + 2.0h labor)', '💰 本單成本（料＋工時 2.0h）')} value={<span>NT$ 3,240 <span style={{ color: C.ok }}>✓</span></span>} />
                </div>
                <div style={{ fontSize: 11, color: C.sub, textTransform: 'uppercase', letterSpacing: 1, margin: '14px 0 8px' }}>{ui('Sign-off chain', '多階簽核鏈')}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  <StatusPill tone="ok" size="sm">{ui('Employee ✓', '員工 ✓')}</StatusPill><span style={{ color: C.faint }}>→</span>
                  <StatusPill tone="ok" size="sm">{ui('Leader ✓', '組長 ✓')}</StatusPill><span style={{ color: C.faint }}>→</span>
                  <StatusPill tone="accent" size="sm">{ui('Supervisor ◔', '主管 ◔')}</StatusPill><span style={{ color: C.faint }}>→</span>
                  <StatusPill tone="info" size="sm">{ui('Treasury', '總務')}</StatusPill>
                </div>
              </Card>
            }
          />
        );
      case 4:
        return (
          <Split
            story={<Story
              mods={[['inventory', true], ['workflow', true]]}
              kicker={ui('Scene 4 · Never run dry', '情境四 · 安全庫存')}
              title={ui('Stock dips below safety line → reorder before you run out', '料件低於安全庫存 → 用光前就先補')}
              lede={ui('The dual-write ledger tracks every in/out, so low stock surfaces the moment it happens — not when a job stalls offshore.', '雙寫交易帳追蹤每筆進出，低於安全庫存當下就跳，不會等海上開工才發現沒料。')}
              beats={[
                ['pain', ui('"Use it to find it is gone" — a job stalls on the turbine for a missing part.', '「用到才發現沒了」——為缺一顆料在機上卡住。')],
                ['move', ui('Below safety stock → flagged on the console, one tap to raise a material request.', '低於安全庫存 → 操作台跳燈，一鍵開領料單叫料。')],
                ['gain', ui('Fewer wasted trips, no offshore surprises.', '少跑冤枉船、海上不開天窗。')],
              ]}
            />}
            mock={
              <Card padding={16}>
                <PageHeader title={ui('Inventory', '庫存')} sub={ui('CH-Offshore-01 · main store', 'CH-Offshore-01 · 主倉')} />
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <Row label={ui('Gearbox bearing GBR-001', '齒輪箱軸承 GBR-001')} value={<span>8 · <span style={{ color: C.ok }}>{ui('OK', '安全')}</span></span>} />
                  <Card tone="warn" padding={12} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div>
                      <div style={{ fontWeight: 700, color: C.text }}>{ui('Coolant GL-32', '冷卻液 GL-32')}</div>
                      <div style={{ fontSize: 12, color: C.sub }}>{ui('on hand', '現貨')} <b style={{ ...mono, color: C.warn }}>2</b> · {ui('safety', '安全庫存')} <b style={mono}>3</b></div>
                    </div>
                    <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
                      <StatusPill tone="warn" size="sm">{ui('Below safety', '低於安全')}</StatusPill>
                      <Btn variant="primary" size="sm" onClick={() => go(5)}>{ui('Reorder', '自動叫料')}</Btn>
                    </div>
                  </Card>
                  <Row label={ui('Pitch seal PS-11', '變槳密封 PS-11')} value={<span>15 · <span style={{ color: C.ok }}>{ui('OK', '安全')}</span></span>} />
                </div>
              </Card>
            }
          />
        );
      case 5:
        return (
          <Split
            story={<Story
              mods={[['reporting', true], ['cost · LCOE', true]]}
              kicker={ui('Scene 5 · Month-end', '情境五 · 月底交代')}
              title={ui('One-tap monthly report — stronger footing at renewal', '一鍵產出專業月報，續約更有底氣')}
              lede={ui('The vendor is the contractor; every month you owe the asset owner a what/how-much/how-healthy report.', '運維廠商是乙方，每月要跟業主交代做了什麼、花多少、機組健康度如何。')}
              beats={[
                ['pain', ui('Manager stitches a PPT from Excel + screenshots; numbers rarely match the actual jobs.', '主管用 Excel＋截圖拼 PPT，數字還常對不上實際工單。')],
                ['move', ui('Month-end rolls up jobs, actual part cost and KPIs into a PDF — all sourced from real work orders.', '月底把工單、實際用料成本、KPI 彙整成 PDF，全部源自真實工單。')],
                ['gain', ui('Report is not bounced, renewal has leverage, bids can speak in LCOE.', '月報不被退件、續約有籌碼、投標用 LCOE 說話。')],
              ]}
            />}
            mock={
              <Card padding={16}>
                <PageHeader title={ui('June 2026 · O&M Report', '2026 年 6 月 · 運維月報')} sub="CH-Offshore-01" actions={<Btn variant="primary" size="sm">{ui('Export PDF', '產出 PDF')}</Btn>} />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 9, marginBottom: 14 }}>
                  <Stat label={ui('Availability', '稼動率')} value="97.2" unit="%" size={19} />
                  <Stat label={ui('Orders done', '完成工單')} value="18" size={19} />
                  <Stat label="MTTR" value="4.1" unit="h" size={19} />
                  <Stat label={ui('Cost', '成本')} value="41.2" unit={ui('万', '萬')} size={19} />
                </div>
                {([['Corrective', '故障維修', 54, C.warn], ['Preventive', '預防保養', 31, C.info], ['Inventory', '庫存料件', 15, C.amber]] as [string, string, number, string][]).map(([en, zh, w, col]) => (
                  <div key={en} style={{ display: 'grid', gridTemplateColumns: '84px 1fr auto', gap: 10, alignItems: 'center', fontSize: 12, marginBottom: 8 }}>
                    <span style={{ color: C.sub }}>{ui(en, zh)}</span>
                    <span style={{ height: 10, borderRadius: 6, background: C.panelMuted, border: `1px solid ${C.border}`, overflow: 'hidden' }}>
                      <span style={{ display: 'block', height: '100%', width: `${w}%`, background: col }} />
                    </span>
                    <span style={{ ...mono, fontWeight: 700 }}>{w}%</span>
                  </div>
                ))}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12, paddingTop: 12, borderTop: `1px solid ${C.border}` }}>
                  <span style={{ fontSize: 12, color: C.sub }}>⚡ {ui('LCOE', 'LCOE 每度電成本')}</span>
                  <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
                    <MiniSparkline values={[2.6, 2.55, 2.5, 2.42, 2.38, 2.31]} color={C.accent} height={24} />
                    <span style={{ ...mono, fontWeight: 800 }}>2.31 <span style={{ fontSize: 11, color: C.sub, fontWeight: 600 }}>NT$/kWh</span></span>
                  </span>
                </div>
              </Card>
            }
          />
        );
      default:
        return (
          <div style={{ maxWidth: 940, margin: '0 auto' }}>
            <div style={{ textAlign: 'center', marginBottom: 6 }}>
              <Eyebrow>{ui('Five modules · one flow', '五個模組 · 一條龍')}</Eyebrow>
              <h2 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 'clamp(24px,4vw,36px)', margin: '8px 0 4px', color: C.text }}>
                {ui('Judge in the moment · book as you work · report with proof', '出事能判斷 · 做事有帳 · 交代有據')}
              </h2>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 10, margin: '18px 0' }}>
              {([['📡', 'monitoring', ui('SCADA + sim', 'SCADA＋模擬器')], ['🗂', 'workflow', ui('orders · sign-off · stock', '工單·簽核·庫存')], ['💰', 'cost', ui('cost · LCOE', '成本·LCOE')], ['📄', 'reporting', ui('report PDF', '月報 PDF')], ['📖', 'knowledge', ui('alarm RAG', '警報 RAG')]] as [string, string, string][]).map(([ic, name, desc]) => (
                <Card key={name} padding={14}>
                  <div style={{ width: 34, height: 34, borderRadius: 9, background: C.accentSoft, display: 'grid', placeItems: 'center', fontSize: 17, marginBottom: 9 }}>{ic}</div>
                  <div style={{ fontWeight: 700, fontSize: 14, color: C.text }}>{name}</div>
                  <div style={{ fontSize: 12, color: C.sub }}>{desc}</div>
                </Card>
              ))}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14 }}>
              {([[ui('Less reliance on veterans', '降低對老師傅的依賴'), ui('Manual in 30s, not a LINE reply.', '現場查手冊 30 秒，不等 LINE。')], [ui('Cost & parts under control', '成本與料件即時可控'), ui('Every order books on the spot.', '每張工單當下出帳。')], [ui('Professional reports for owners', '對業主拿得出專業報表'), ui('Leverage at renewal, data at bid.', '續約有籌碼、投標用數據。')]] as [string, string][]).map(([b, s]) => (
                <div key={b} style={{ borderLeft: `3px solid ${C.accent}`, padding: '2px 0 2px 14px' }}>
                  <b style={{ display: 'block', fontSize: 14.5, marginBottom: 2, color: C.text }}>{b}</b>
                  <span style={{ fontSize: 13, color: C.sub }}>{s}</span>
                </div>
              ))}
            </div>
            <div style={{ textAlign: 'center', marginTop: 24 }}>
              <StatusPill tone="accent">✨ {ui('Simulator-first · demo without a live farm', 'Simulator-first · 不用真實風場就能 demo')}</StatusPill>
            </div>
          </div>
        );
    }
  };

  return (
    <div style={{ padding: '8px 4px 40px' }}>
      {/* chapter rail */}
      <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginBottom: 22 }}>
        {chapters.map((ch, i) => (
          <button key={ch} type="button" onClick={() => go(i)} aria-current={i === step}
            style={{
              appearance: 'none', cursor: 'pointer', fontFamily: 'inherit', fontSize: 12.5,
              padding: '6px 12px', borderRadius: 999,
              border: `1px solid ${i === step ? 'transparent' : C.border}`,
              background: i === step ? C.accent : C.panel,
              color: i === step ? C.accentInk : C.sub,
              fontWeight: i === step ? 600 : 400,
            }}>
            <span style={{ ...mono, fontSize: 11, opacity: 0.7, marginRight: 6 }}>{i + 1}</span>{ch}
          </button>
        ))}
      </div>

      {/* stage */}
      <div style={{ minHeight: 380 }}>{stage()}</div>

      {/* controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 26, maxWidth: 1040, marginLeft: 'auto', marginRight: 'auto' }}>
        <Btn variant="ghost" onClick={() => go(step - 1)} disabled={step === 0}>← {ui('Back', '上一步')}</Btn>
        <div style={{ flex: 1, textAlign: 'center', fontSize: 12.5, color: C.sub }}>
          {ui('Scene', '情境')} <span style={{ ...mono, color: C.text }}>{step + 1}</span> / <span style={mono}>{N}</span>
        </div>
        <Btn variant="primary" onClick={() => go(step + 1)} disabled={step === N - 1}>
          {step === N - 1 ? ui('Done ✓', '完成 ✓') : `${ui('Next', '下一步')} →`}
        </Btn>
      </div>
    </div>
  );
};

export default GuidedTourPage;
