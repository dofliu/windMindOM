// Variant B — Workshop Console. Warm paper, mono+serif type, industrial drafting feel.
// Same page registry as VA: overview | turbine | maintenance | cost | history

const VB = ({ page = 'overview', lang = 'zh' }) => {
  const { useState } = React;
  const [activePage, setActivePage] = useState(page);
  const [activeLang, setLang] = useState(lang);
  const D = window.WMOM_APP;
  const tr = (en, zh) => activeLang === 'zh' ? zh : en;

  const C = {
    bg: '#EFE9DD', paper: '#F8F3E6', ink: '#1A1814', sub: '#5C5448', faint: '#9C9384',
    accent: '#7C5A2B',     // burnt sienna
    leaf: '#4A6B3A',       // deep moss
    rust: '#A14A2A',       // alarm
    line: '#C9BFA8',
    grid: '#D9CFB6',
  };

  return (
    <div data-screen-label={`VB ${activePage}`} style={{
      background: C.bg, color: C.ink, minHeight: '100%', width: '100%',
      fontFamily: '"IBM Plex Sans", system-ui, sans-serif',
      backgroundImage: `linear-gradient(${C.grid} 1px, transparent 1px), linear-gradient(90deg, ${C.grid} 1px, transparent 1px)`,
      backgroundSize: '24px 24px', backgroundPosition: '-1px -1px',
    }}>
      {/* Top rail */}
      <header style={{
        background: C.paper, borderBottom: `1px solid ${C.line}`,
        display: 'flex', alignItems: 'center', padding: '14px 24px', gap: 28,
        position: 'sticky', top: 0, zIndex: 10
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 36, height: 36, border: `2px solid ${C.ink}`, display: 'grid', placeItems: 'center', background: C.paper }}>
            <Logo2 color={C.ink}/>
          </div>
          <div>
            <div style={{ fontFamily: '"Bodoni Moda", "Playfair Display", serif', fontSize: 18, fontWeight: 700, lineHeight: 1, letterSpacing: -0.3 }}>WMOM</div>
            <div style={{ fontSize: 9, letterSpacing: 2, color: C.sub, textTransform: 'uppercase', marginTop: 2 }}>Workshop · Est. 2024</div>
          </div>
        </div>
        <nav style={{ display: 'flex', gap: 2, marginLeft: 'auto' }}>
          {D.pages.map(p => (
            <button key={p.id} onClick={() => setActivePage(p.id)} style={{
              padding: '8px 16px', fontSize: 12, fontWeight: 600,
              background: activePage === p.id ? C.ink : 'transparent',
              color: activePage === p.id ? C.paper : C.ink,
              border: `1px solid ${activePage === p.id ? C.ink : C.line}`,
              cursor: 'pointer', fontFamily: 'inherit', letterSpacing: 0.5, textTransform: 'uppercase'
            }}>{tr(p.en, p.zh)}</button>
          ))}
        </nav>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center', borderLeft: `1px solid ${C.line}`, paddingLeft: 18 }}>
          <span style={{ fontSize: 11, fontFamily: 'JetBrains Mono, monospace', color: C.sub }}>
            <span style={{ display: 'inline-block', width: 6, height: 6, background: C.leaf, borderRadius: '50%', marginRight: 6 }}></span>
            LIVE 1.2s
          </span>
          <button onClick={() => setLang(activeLang === 'zh' ? 'en' : 'zh')} style={{
            padding: '4px 8px', fontSize: 11, border: `1px solid ${C.line}`, background: 'transparent', cursor: 'pointer', fontFamily: 'JetBrains Mono, monospace'
          }}>{activeLang === 'zh' ? 'EN' : '中'}</button>
        </div>
      </header>

      <main style={{ padding: '32px 40px' }}>
        {activePage === 'overview' && <Overview2 C={C} D={D} tr={tr}/>}
        {activePage === 'turbine' && <Turbine2 C={C} D={D} tr={tr}/>}
        {activePage === 'maintenance' && <Maintenance2 C={C} D={D} tr={tr}/>}
        {activePage === 'cost' && <Cost2 C={C} D={D} tr={tr}/>}
        {activePage === 'history' && <History2 C={C} D={D} tr={tr}/>}
      </main>
    </div>
  );
};

const Sheet = ({ C, label, children, style, span }) => (
  <div style={{ background: C.paper, border: `1px solid ${C.ink}`, position: 'relative', gridColumn: span ? `span ${span}` : undefined, ...style }}>
    {label && (
      <div style={{
        position: 'absolute', top: -10, left: 14, background: C.bg, padding: '0 8px',
        fontSize: 10, letterSpacing: 2, fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase', color: C.sub
      }}>{label}</div>
    )}
    {children}
  </div>
);

const SectionHead = ({ C, num, title, sub, right }) => (
  <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 24, borderBottom: `2px solid ${C.ink}`, paddingBottom: 14 }}>
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 20 }}>
      {num && <div style={{ fontFamily: '"Bodoni Moda", serif', fontSize: 64, lineHeight: 0.8, color: C.accent, fontWeight: 700, fontStyle: 'italic' }}>{num}</div>}
      <div>
        <div style={{ fontSize: 10, letterSpacing: 3, color: C.sub, textTransform: 'uppercase', fontFamily: 'JetBrains Mono, monospace' }}>{sub}</div>
        <h1 style={{ fontFamily: '"Bodoni Moda", serif', fontSize: 42, lineHeight: 1, margin: '4px 0 0', fontWeight: 700, letterSpacing: -1 }}>{title}</h1>
      </div>
    </div>
    {right && <div>{right}</div>}
  </div>
);

const Btn2 = ({ C, primary, children, onClick }) => (
  <button onClick={onClick} style={{
    background: primary ? C.ink : 'transparent', color: primary ? C.paper : C.ink,
    border: `1.5px solid ${C.ink}`, padding: '8px 16px', fontSize: 11, fontWeight: 700,
    cursor: 'pointer', fontFamily: 'JetBrains Mono, monospace', letterSpacing: 1, textTransform: 'uppercase'
  }}>{children}</button>
);

// ── Overview ──
const Overview2 = ({ C, D, tr }) => {
  const total = D.turbines.reduce((s,t) => s+t.power, 0);
  const ops = D.turbines.filter(t => t.status==='OPERATING').length;
  const flt = D.turbines.filter(t => t.status==='FAULT').length;
  return (
    <div>
      <SectionHead C={C}
        num="01"
        sub={tr('Site Brief · Changhua Coastal', '場址簡報　彰化沿海')}
        title={tr('Today on the floor', '今日廠內動態')}
        right={<div style={{ display: 'flex', gap: 8 }}><Btn2 C={C}>{tr('Print','列印')}</Btn2><Btn2 C={C} primary>{tr('Brief','彙整')}</Btn2></div>}
      />
      {/* Hero ledger */}
      <Sheet C={C} label={tr('SITE LEDGER · 1m','現場帳冊　每分')} style={{ marginBottom: 28, padding: '32px 36px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 0, alignItems: 'center' }}>
          <div style={{ borderRight: `1px dashed ${C.line}`, paddingRight: 24 }}>
            <div style={{ fontSize: 10, letterSpacing: 2, color: C.sub, fontFamily: 'JetBrains Mono, monospace' }}>{tr('FARM POWER','風場功率')}</div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 8 }}>
              <span style={{ fontFamily: '"Bodoni Moda", serif', fontSize: 86, lineHeight: 0.85, fontWeight: 700, color: C.ink, fontStyle: 'italic', letterSpacing: -3 }}>{total.toFixed(1)}</span>
              <span style={{ fontSize: 18, color: C.sub, fontFamily: 'JetBrains Mono, monospace' }}>MW</span>
            </div>
            <div style={{ height: 6, background: C.bg, marginTop: 14, position: 'relative', border: `1px solid ${C.line}` }}>
              <div style={{ width: `${(total/24)*100}%`, height: '100%', background: C.leaf }}></div>
              <div style={{ position: 'absolute', top: -2, left: '70%', width: 1, height: 10, background: C.ink }}></div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: C.sub, marginTop: 4, fontFamily: 'JetBrains Mono, monospace' }}>
              <span>0</span><span>16.8 ← BUDGET</span><span>24.0 RATED</span>
            </div>
          </div>
          {[
            { l: tr('Operating','運轉'), v: `${ops}/12`, c: C.leaf },
            { l: tr('Faulted','故障'), v: flt, c: flt > 0 ? C.rust : C.ink },
            { l: tr('Avg Wind','均風速'), v: (D.turbines.reduce((s,t)=>s+t.wind,0)/12).toFixed(1) + ' m/s', c: C.ink, small: true },
          ].map((m,i) => (
            <div key={i} style={{ paddingLeft: 24, borderRight: i < 2 ? `1px dashed ${C.line}` : 'none' }}>
              <div style={{ fontSize: 10, letterSpacing: 2, color: C.sub, fontFamily: 'JetBrains Mono, monospace' }}>{m.l}</div>
              <div style={{ fontFamily: '"Bodoni Moda", serif', fontSize: m.small ? 36 : 56, fontWeight: 700, color: m.c, lineHeight: 0.9, marginTop: 8, letterSpacing: -1, fontStyle: 'italic' }}>{m.v}</div>
            </div>
          ))}
        </div>
      </Sheet>

      {/* Trend + map */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 18, marginBottom: 28 }}>
        <Sheet C={C} label={tr('GENERATION CURVE · 24h','發電曲線　24 小時')} style={{ padding: '28px 24px 20px' }}>
          <BigChart2 C={C}/>
        </Sheet>
        <Sheet C={C} label={tr('LAYOUT · A→D ROWS','配置圖　A→D 列')} style={{ padding: '24px', position: 'relative' }}>
          <FarmMap C={C} D={D}/>
        </Sheet>
      </div>

      {/* Turbine ledger */}
      <Sheet C={C} label={tr('FLEET STATUS','機隊狀態')} style={{ padding: 0 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, fontFamily: 'JetBrains Mono, monospace' }}>
          <thead>
            <tr style={{ background: C.ink, color: C.paper }}>
              {['#', 'STATUS', tr('POWER MW','功率'), tr('WIND','風速'), 'RPM', tr('GEAR °C','齒輪溫'), tr('VIB','振動'), tr('YAW ERR','偏航誤差')].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '8px 14px', fontSize: 10, fontWeight: 600, letterSpacing: 1 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {D.turbines.map((t, i) => (
              <tr key={t.id} style={{ borderBottom: `1px solid ${C.line}`, background: i % 2 === 0 ? C.paper : '#FCF8EE' }}>
                <td style={{ padding: '10px 14px', fontWeight: 700, fontFamily: '"Bodoni Moda", serif', fontSize: 14 }}>{t.name}</td>
                <td style={{ padding: '10px 14px' }}>
                  <span style={{
                    display: 'inline-block', width: 8, height: 8, marginRight: 8,
                    background: t.status === 'OPERATING' ? C.leaf : t.status === 'FAULT' ? C.rust : t.status === 'IDLE' ? C.accent : C.faint
                  }}></span>
                  <span style={{ fontSize: 10, fontWeight: 700 }}>{t.status}</span>
                </td>
                <td style={{ padding: '10px 14px', fontWeight: 600, color: t.status === 'OPERATING' ? C.leaf : C.sub }}>{t.power.toFixed(2)}</td>
                <td style={{ padding: '10px 14px' }}>{t.wind}</td>
                <td style={{ padding: '10px 14px' }}>{t.rpm}</td>
                <td style={{ padding: '10px 14px', color: t.gearTemp > 85 ? C.rust : C.ink }}>{t.gearTemp.toFixed(0)}</td>
                <td style={{ padding: '10px 14px', color: t.vib > 3 ? C.rust : C.ink }}>{t.vib.toFixed(2)}</td>
                <td style={{ padding: '10px 14px' }}>{t.yawErr.toFixed(1)}°</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Sheet>
    </div>
  );
};

// ── Turbine ──
const Turbine2 = ({ C, D, tr }) => {
  const t = D.turbines[1];
  return (
    <div>
      <SectionHead C={C}
        num="02"
        sub={tr('Worksheet · ' + t.name + ' · Bachmann Z72', '工作表　' + t.name + '　Bachmann Z72')}
        title={tr('Turbine in production', '正常發電中')}
        right={<div style={{ display: 'flex', gap: 8 }}><Btn2 C={C}>{tr('Curtail','限載')}</Btn2><Btn2 C={C}>{tr('Stop','停機')}</Btn2><Btn2 C={C} primary>{tr('Inspect','檢查')}</Btn2></div>}
      />
      {/* Diagram + side */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 18, marginBottom: 28 }}>
        <Sheet C={C} label={tr('TECHNICAL CROSS-SECTION','技術剖面圖')} style={{ padding: '32px', minHeight: 380 }}>
          <TurbineDiagram C={C} t={t} tr={tr}/>
        </Sheet>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <Sheet C={C} label={tr('LIVE READOUT','即時讀值')} style={{ padding: '20px 24px' }}>
            {[
              { k: tr('Power','功率'), v: t.power.toFixed(2) + ' MW', big: true, c: C.leaf },
              { k: tr('Wind','風速'), v: t.wind + ' m/s' },
              { k: 'RPM', v: t.rpm },
              { k: tr('Gear °C','齒輪溫'), v: t.gearTemp.toFixed(0) },
              { k: tr('Vib mm/s','振動'), v: t.vib.toFixed(2) },
              { k: tr('Pitch','槳距'), v: t.blade.toFixed(1) + '°' },
            ].map((r, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '6px 0', borderBottom: i < 5 ? `1px dashed ${C.line}` : 'none' }}>
                <span style={{ fontSize: 11, color: C.sub, letterSpacing: 1, fontFamily: 'JetBrains Mono, monospace', textTransform: 'uppercase' }}>{r.k}</span>
                <span style={{ fontFamily: r.big ? '"Bodoni Moda", serif' : 'JetBrains Mono, monospace', fontSize: r.big ? 24 : 14, fontWeight: r.big ? 700 : 600, color: r.c || C.ink, fontStyle: r.big ? 'italic' : 'normal' }}>{r.v}</span>
              </div>
            ))}
          </Sheet>
          <Sheet C={C} label={tr('OPERATOR CONTROL','操作控制')} style={{ padding: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <Btn2 C={C}>{tr('▶ START','▶ 啟動')}</Btn2>
              <Btn2 C={C}>{tr('■ STOP','■ 停機')}</Btn2>
              <Btn2 C={C}>{tr('LOCK','上鎖')}</Btn2>
              <Btn2 C={C}>{tr('TEST','測試')}</Btn2>
            </div>
            <div style={{ marginTop: 10, padding: '10px 12px', background: C.bg, border: `1px solid ${C.rust}`, fontSize: 11, color: C.rust, fontFamily: 'JetBrains Mono, monospace' }}>
              ⚠ {tr('EMERGENCY STOP','緊急停機')}
            </div>
          </Sheet>
        </div>
      </div>

      {/* Channels */}
      <Sheet C={C} label={tr('SIGNAL CHANNELS · 4-up','訊號通道　四聯')} style={{ padding: '24px 28px', marginBottom: 28 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 24 }}>
          {[
            { label: 'POWER · MW', val: t.power.toFixed(2), c: C.leaf, amp: 1 },
            { label: 'WIND · m/s', val: t.wind, c: C.ink, amp: 0.7 },
            { label: 'GEARBOX · °C', val: t.gearTemp.toFixed(0), c: C.accent, amp: 0.4 },
            { label: 'VIB · mm/s', val: t.vib.toFixed(2), c: C.rust, amp: 1.4 },
          ].map((ch, i) => (
            <div key={i}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, fontFamily: 'JetBrains Mono, monospace', letterSpacing: 1, marginBottom: 6 }}>
                <span style={{ color: C.sub }}>{ch.label}</span>
                <span style={{ fontWeight: 700, color: ch.c }}>{ch.val}</span>
              </div>
              <ChannelChart C={C} color={ch.c} amp={ch.amp} seed={i}/>
            </div>
          ))}
        </div>
      </Sheet>

      {/* Subsystems matrix */}
      <Sheet C={C} label={tr('SUBSYSTEM HEALTH MATRIX','子系統健康矩陣')} style={{ padding: '24px 28px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: 12 }}>
          {[
            { k: tr('Generator','發電機'), s: 92 }, { k: tr('Gearbox','齒輪箱'), s: 78 },
            { k: tr('Pitch','變槳'), s: 88 }, { k: tr('Yaw','偏航'), s: 95 },
            { k: tr('Tower','塔筒'), s: 90 }, { k: tr('Blades','葉片'), s: 84 },
            { k: tr('Converter','變頻'), s: 91 }, { k: tr('Cooling','冷卻'), s: 87 },
          ].map(s => (
            <div key={s.k}>
              <div style={{ width: 60, height: 60, margin: '0 auto', border: `2px solid ${C.ink}`, position: 'relative', background: 'repeating-linear-gradient(45deg, transparent 0 4px, ' + (s.s > 85 ? C.leaf : s.s > 75 ? C.accent : C.rust) + '40 4px 5px)' }}>
                <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: `${s.s}%`, background: s.s > 85 ? C.leaf : s.s > 75 ? C.accent : C.rust }}></div>
              </div>
              <div style={{ textAlign: 'center', fontSize: 10, color: C.sub, marginTop: 6, fontFamily: 'JetBrains Mono, monospace', letterSpacing: 0.5 }}>{s.k}</div>
              <div style={{ textAlign: 'center', fontSize: 13, fontFamily: '"Bodoni Moda", serif', fontWeight: 700, fontStyle: 'italic' }}>{s.s}%</div>
            </div>
          ))}
        </div>
      </Sheet>
    </div>
  );
};

// ── Maintenance ──
const Maintenance2 = ({ C, D, tr }) => (
  <div>
    <SectionHead C={C}
      num="03"
      sub={tr('Crew Roster & Open Tickets', '人員班表與工單')}
      title={tr('Maintenance Workshop', '維護工坊')}
      right={<Btn2 C={C} primary>+ {tr('NEW WORK ORDER','新工單')}</Btn2>}
    />
    <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 18 }}>
      {/* Tickets */}
      <Sheet C={C} label={tr('OPEN TICKETS · WO LEDGER','未結工單　帳本')} style={{ padding: 0 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: C.ink, color: C.paper, fontFamily: 'JetBrains Mono, monospace' }}>
              {['WO #', tr('TURBINE','風機'), tr('ISSUE','問題'), tr('TECH','技師'), 'PRI', 'SLA'].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '8px 12px', fontSize: 10, fontWeight: 600, letterSpacing: 1 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {D.workOrders.map((w, i) => (
              <tr key={w.id} style={{ borderBottom: `1px solid ${C.line}`, background: i % 2 === 0 ? C.paper : '#FCF8EE' }}>
                <td style={{ padding: '14px 12px', fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>{w.id.slice(-6)}</td>
                <td style={{ padding: '14px 12px', fontFamily: '"Bodoni Moda", serif', fontWeight: 700, fontSize: 14 }}>{w.tid}</td>
                <td style={{ padding: '14px 12px' }}>
                  <div>{tr(w.issue_en, w.issue_zh)}</div>
                  <div style={{ fontSize: 10, color: C.sub, fontFamily: 'JetBrains Mono, monospace', marginTop: 2 }}>{w.created}</div>
                </td>
                <td style={{ padding: '14px 12px', color: C.sub }}>{tr(w.techEn, w.tech)}</td>
                <td style={{ padding: '14px 12px' }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: '2px 6px', letterSpacing: 1,
                    background: w.priority === 'HIGH' ? C.rust : w.priority === 'MED' ? C.accent : C.faint,
                    color: C.paper
                  }}>{w.priority}</span>
                </td>
                <td style={{ padding: '14px 12px', fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: C.sub }}>{w.sla}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Sheet>
      {/* Crew */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        <Sheet C={C} label={tr('CREW ROSTER','技師名冊')} style={{ padding: '20px 24px' }}>
          {D.technicians.map((t, i) => (
            <div key={t.name} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 0', borderBottom: i < 3 ? `1px dashed ${C.line}` : 'none' }}>
              <div style={{ width: 40, height: 40, border: `1.5px solid ${C.ink}`, display: 'grid', placeItems: 'center', fontFamily: '"Bodoni Moda", serif', fontWeight: 700, fontSize: 18, fontStyle: 'italic', background: C.paper }}>
                {tr(t.nameEn, t.name).charAt(0)}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{tr(t.nameEn, t.name)}</div>
                <div style={{ fontSize: 10, color: C.sub, fontFamily: 'JetBrains Mono, monospace', letterSpacing: 0.5, marginTop: 2 }}>{t.skill}</div>
              </div>
              <div style={{
                fontSize: 9, padding: '3px 8px', letterSpacing: 1, fontWeight: 700,
                background: t.status === 'ON_DUTY' ? C.leaf : t.status === 'DISPATCHED' ? C.accent : C.faint,
                color: C.paper
              }}>{t.status}</div>
            </div>
          ))}
        </Sheet>
        <Sheet C={C} label={tr('THIS WEEK · 5/04→5/10','本週　5/04→5/10')} style={{ padding: 18 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 4, marginBottom: 8 }}>
            {['MON','TUE','WED','THU','FRI','SAT','SUN'].map(d => (
              <div key={d} style={{ fontSize: 9, color: C.sub, textAlign: 'center', fontFamily: 'JetBrains Mono, monospace', letterSpacing: 1 }}>{d}</div>
            ))}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 4 }}>
            {[
              { d: 4 }, { d: 5, e: { c: C.rust, n: 'WO-014' } }, { d: 6, e: { c: C.accent, n: 'PM' } },
              { d: 7, e: { c: C.leaf, n: '✓' } }, { d: 8 }, { d: 9 }, { d: 10 }
            ].map((c, i) => (
              <div key={i} style={{ aspectRatio: 1, border: `1px solid ${C.line}`, padding: 6, position: 'relative', background: c.e ? C.paper : 'transparent' }}>
                <div style={{ fontSize: 11, fontFamily: '"Bodoni Moda", serif', fontWeight: 700 }}>{c.d}</div>
                {c.e && <div style={{ position: 'absolute', bottom: 4, left: 4, right: 4, fontSize: 8, padding: '1px 4px', background: c.e.c, color: C.paper, textAlign: 'center', fontFamily: 'JetBrains Mono, monospace' }}>{c.e.n}</div>}
              </div>
            ))}
          </div>
        </Sheet>
      </div>
    </div>
  </div>
);

// ── Cost ──
const Cost2 = ({ C, D, tr }) => (
  <div>
    <SectionHead C={C}
      num="04"
      sub={tr('Financial Worksheet · 20-yr horizon', '財務工作表　二十年')}
      title={tr('Cost & Yield', '成本與產量')}
      right={<Btn2 C={C} primary>{tr('RUN SCENARIO','執行情境')}</Btn2>}
    />
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 18, marginBottom: 28 }}>
      {D.cost.metrics.map((m, i) => (
        <Sheet C={C} key={i} label={tr(m.label_en, m.label_zh).toUpperCase()} style={{ padding: '24px 28px' }}>
          <div style={{ fontFamily: '"Bodoni Moda", serif', fontSize: 36, fontWeight: 700, fontStyle: 'italic', color: i===1 ? C.leaf : C.ink, lineHeight: 1, letterSpacing: -1 }}>{m.val}</div>
          {m.delta && <div style={{ fontSize: 11, marginTop: 8, color: m.delta.startsWith('+') ? C.leaf : m.delta.startsWith('−') ? C.leaf : C.sub, fontFamily: 'JetBrains Mono, monospace' }}>{m.delta}</div>}
        </Sheet>
      ))}
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 18 }}>
      <Sheet C={C} label={tr('20-YR REVENUE PROJECTION · P10/P50/P90','20 年營收預測　P10/P50/P90')} style={{ padding: '24px 24px 20px' }}>
        <BigChart2 C={C} kind="forecast"/>
      </Sheet>
      <Sheet C={C} label={tr('MONTE CARLO · 5,000 SIMS','蒙地卡羅　5,000 模擬')} style={{ padding: '24px 28px' }}>
        <MonteHist C={C}/>
        <div style={{ marginTop: 14 }}>
          {[
            { k: 'P10', v: D.cost.monteCarlo.p10, c: C.leaf },
            { k: 'P50', v: D.cost.monteCarlo.p50, c: C.ink },
            { k: 'P90', v: D.cost.monteCarlo.p90, c: C.rust },
          ].map(r => (
            <div key={r.k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '8px 0', borderBottom: `1px dashed ${C.line}` }}>
              <span style={{ fontSize: 11, fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: r.c, letterSpacing: 1 }}>{r.k}</span>
              <span style={{ fontFamily: '"Bodoni Moda", serif', fontSize: 20, fontStyle: 'italic', fontWeight: 700 }}>{r.v}<span style={{ fontSize: 10, color: C.sub, fontFamily: 'JetBrains Mono, monospace' }}> ¢/kWh</span></span>
            </div>
          ))}
        </div>
      </Sheet>
    </div>
  </div>
);

// ── History ──
const History2 = ({ C, D, tr }) => (
  <div>
    <SectionHead C={C}
      num="05"
      sub={tr('Archive · SCADA tags · CSV export', '檔案室　SCADA 標籤　CSV')}
      title={tr('Historical Records', '歷史紀錄')}
    />
    <Sheet C={C} label={tr('QUERY','查詢')} style={{ padding: '24px 28px', marginBottom: 18 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 18 }}>
        {[
          { l: tr('TURBINE','風機'), v: 'WT002' },
          { l: tr('RANGE','時間'), v: '2026-05-01 → 05-07' },
          { l: tr('TAGS','標籤'), v: 'TotPwrAt + 3' },
          { l: tr('EVENTS','事件'), v: 'Faults · Wind' },
        ].map(f => (
          <div key={f.l}>
            <div style={{ fontSize: 9, letterSpacing: 2, color: C.sub, fontFamily: 'JetBrains Mono, monospace', marginBottom: 4 }}>{f.l}</div>
            <div style={{ padding: '8px 12px', background: C.bg, border: `1px solid ${C.line}`, fontSize: 13, fontFamily: 'JetBrains Mono, monospace' }}>{f.v}</div>
          </div>
        ))}
      </div>
    </Sheet>
    <Sheet C={C} label={tr('POWER OUTPUT WITH EVENT MARKERS','功率輸出與事件標記')} style={{ padding: '24px 24px 20px', marginBottom: 18 }}>
      <BigChart2 C={C} kind="events"/>
    </Sheet>
    <Sheet C={C} label={tr('EVENT JOURNAL','事件日誌')} style={{ padding: 0 }}>
      {[
        { t: '05/06 09:14:22', tag: 'FAULT', en: 'Gearbox overheat — phase: developing', zh: '齒輪箱過熱　階段：發展中', sev: C.rust },
        { t: '05/06 08:42:11', tag: 'WIND',  en: 'Wind ramp +3.2 m/s in 60s', zh: '風速急升 +3.2 m/s（60 秒）', sev: C.accent },
        { t: '05/06 06:00:04', tag: 'STATE', en: 'WT002 synchronized', zh: 'WT002 併網成功', sev: C.leaf },
        { t: '05/06 05:45:18', tag: 'STATE', en: 'WT002 startup begin', zh: 'WT002 啟動開始', sev: C.sub },
        { t: '05/05 22:08:56', tag: 'OFFL',  en: 'WT012 communications lost', zh: 'WT012 通訊離線', sev: C.rust },
      ].map(e => (
        <div key={e.t} style={{ display: 'grid', gridTemplateColumns: '180px 80px 1fr 80px', alignItems: 'center', gap: 14, padding: '14px 24px', borderBottom: `1px dashed ${C.line}` }}>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: C.sub }}>{e.t}</span>
          <span style={{ fontSize: 9, fontWeight: 700, padding: '3px 8px', background: e.sev, color: C.paper, textAlign: 'center', letterSpacing: 1, fontFamily: 'JetBrains Mono, monospace' }}>{e.tag}</span>
          <span style={{ fontSize: 13 }}>{tr(e.en, e.zh)}</span>
          <button style={{ background: 'none', border: `1px solid ${C.line}`, padding: '4px 8px', fontSize: 10, fontFamily: 'JetBrains Mono, monospace', cursor: 'pointer', letterSpacing: 1 }}>VIEW →</button>
        </div>
      ))}
    </Sheet>
  </div>
);

// ── Diagrams & charts ──
const TurbineDiagram = ({ C, t, tr }) => (
  <svg width="100%" height="320" viewBox="0 0 500 320">
    {/* Tower */}
    <line x1="250" y1="60" x2="250" y2="290" stroke={C.ink} strokeWidth="2"/>
    <line x1="250" y1="60" x2="250" y2="290" stroke={C.ink} strokeWidth="6" strokeOpacity="0.1"/>
    {/* Ground */}
    <line x1="120" y1="290" x2="380" y2="290" stroke={C.ink} strokeWidth="1.5"/>
    <line x1="100" y1="294" x2="400" y2="294" stroke={C.ink} strokeWidth="0.5" strokeDasharray="3,3"/>
    {/* Nacelle */}
    <rect x="220" y="50" width="60" height="22" fill={C.paper} stroke={C.ink} strokeWidth="1.5"/>
    {/* Hub */}
    <circle cx="216" cy="61" r="6" fill={C.accent} stroke={C.ink} strokeWidth="1.5"/>
    {/* Blades */}
    {[0, 120, 240].map(a => {
      const rad = (a * Math.PI) / 180;
      const x = 216 + Math.cos(rad - Math.PI/2) * 90;
      const y = 61 + Math.sin(rad - Math.PI/2) * 90;
      return <line key={a} x1="216" y1="61" x2={x} y2={y} stroke={C.leaf} strokeWidth="3" strokeLinecap="round"/>;
    })}
    {/* Annotations */}
    {[
      { x: 320, y: 55, l: 'NACELLE', v: t.gearTemp.toFixed(0) + '°C', tx: 380, ty: 55 },
      { x: 230, y: 130, l: 'TOWER', v: t.vib.toFixed(1) + ' mm/s', tx: 60, ty: 130 },
      { x: 108, y: 80, l: 'BLADE A', v: t.blade.toFixed(1) + '°', tx: 60, ty: 80 },
      { x: 350, y: 200, l: 'YAW', v: t.yawErr.toFixed(1) + '°', tx: 380, ty: 200 },
      { x: 250, y: 285, l: 'BASE', v: 'PWR ' + t.power.toFixed(2) + ' MW', tx: 380, ty: 270 },
    ].map((a, i) => (
      <g key={i}>
        <circle cx={a.x} cy={a.y} r="3" fill={C.ink}/>
        <line x1={a.x} y1={a.y} x2={a.tx > a.x ? a.tx - 5 : a.tx + 5} y2={a.ty} stroke={C.ink} strokeWidth="0.5" strokeDasharray="2,2"/>
        <text x={a.tx} y={a.ty} textAnchor={a.tx < 200 ? 'start' : 'start'} fontSize="9" fontFamily="JetBrains Mono, monospace" letterSpacing="1" fill={C.sub}>{a.l}</text>
        <text x={a.tx} y={a.ty + 12} textAnchor={a.tx < 200 ? 'start' : 'start'} fontSize="13" fontFamily="Bodoni Moda, serif" fontWeight="700" fontStyle="italic" fill={C.ink}>{a.v}</text>
      </g>
    ))}
    {/* Wind arrow */}
    <g transform="translate(50, 200)">
      <text x="0" y="0" fontSize="9" fontFamily="JetBrains Mono, monospace" fill={C.sub} letterSpacing="1">WIND {t.wind} m/s</text>
      <line x1="0" y1="10" x2="50" y2="10" stroke={C.accent} strokeWidth="2"/>
      <polygon points="50,5 60,10 50,15" fill={C.accent}/>
    </g>
  </svg>
);

const FarmMap = ({ C, D }) => (
  <svg width="100%" height="240" viewBox="0 0 320 240">
    {/* Coast */}
    <path d="M0,40 Q60,50 110,80 T220,140 T320,200" stroke={C.line} strokeWidth="1.5" fill="none" strokeDasharray="4,2"/>
    <text x="20" y="30" fontSize="9" fill={C.sub} fontFamily="JetBrains Mono, monospace" letterSpacing="1">SHORE</text>
    <text x="240" y="220" fontSize="9" fill={C.sub} fontFamily="JetBrains Mono, monospace" letterSpacing="1">SEA</text>
    {/* Turbines */}
    {D.turbines.map((t, i) => {
      const x = 50 + (i % 4) * 65;
      const y = 60 + Math.floor(i / 4) * 60;
      const c = t.status === 'OPERATING' ? C.leaf : t.status === 'FAULT' ? C.rust : t.status === 'IDLE' ? C.accent : C.faint;
      return (
        <g key={t.id}>
          <line x1={x} y1={y} x2={x + 14} y2={y - 14} stroke={C.ink} strokeWidth="0.5"/>
          <circle cx={x} cy={y} r="6" fill={c} stroke={C.ink} strokeWidth="1"/>
          <text x={x + 16} y={y - 14} fontSize="8" fill={C.ink} fontFamily="JetBrains Mono, monospace">{t.name}</text>
        </g>
      );
    })}
    {/* Compass */}
    <g transform="translate(280, 30)">
      <circle cx="0" cy="0" r="12" fill="none" stroke={C.ink} strokeWidth="0.8"/>
      <line x1="0" y1="-12" x2="0" y2="12" stroke={C.ink} strokeWidth="0.5"/>
      <line x1="-12" y1="0" x2="12" y2="0" stroke={C.ink} strokeWidth="0.5"/>
      <text x="0" y="-15" textAnchor="middle" fontSize="8" fill={C.ink} fontFamily="JetBrains Mono, monospace">N</text>
    </g>
  </svg>
);

const BigChart2 = ({ C, kind = 'power' }) => {
  const W = 800, H = 220;
  const points = Array.from({ length: 80 }).map((_,i) => ({
    x: i * (W/79),
    y: H/2 + Math.sin(i*0.2) * 30 + Math.sin(i*0.5) * 12 - (i > 40 && i < 50 ? 25 : 0)
  }));
  const path = points.map((p,i) => `${i===0?'M':'L'}${p.x},${p.y}`).join(' ');
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      {/* gridlines */}
      {[0,1,2,3,4].map(g => <line key={g} x1="0" x2={W} y1={g*55} y2={g*55} stroke={C.line} strokeWidth="0.5"/>)}
      {[0,1,2,3,4,5,6,7].map(g => <line key={g} x1={g*100} x2={g*100} y1="0" y2={H} stroke={C.line} strokeWidth="0.5" strokeDasharray="2,3"/>)}
      {/* axes labels */}
      {[0,1,2,3].map(g => <text key={g} x="4" y={g*55+10} fontSize="9" fill={C.sub} fontFamily="JetBrains Mono, monospace">{(2.0 - g*0.5).toFixed(1)}</text>)}
      {/* P10/P90 band for forecast */}
      {kind === 'forecast' && (
        <path d={`M0,${H/2-50} ${points.map((p,i)=>`L${p.x},${p.y-30}`).join(' ')} L${W},${H/2+50} ${points.slice().reverse().map(p=>`L${p.x},${p.y+30}`).join(' ')} Z`} fill={C.leaf} fillOpacity="0.12"/>
      )}
      <path d={path} stroke={C.leaf} strokeWidth="2" fill="none"/>
      {kind === 'events' && [
        { x: 200, c: C.rust, l: 'FAULT' },
        { x: 380, c: C.accent, l: 'WIND' },
        { x: 560, c: C.leaf, l: 'SYNC' },
      ].map(e => (
        <g key={e.x}>
          <line x1={e.x} x2={e.x} y1="20" y2={H-20} stroke={e.c} strokeWidth="1" strokeDasharray="3,3"/>
          <rect x={e.x - 18} y="6" width="36" height="14" fill={e.c}/>
          <text x={e.x} y="16" textAnchor="middle" fontSize="8" fill={C.paper} fontFamily="JetBrains Mono, monospace" fontWeight="700">{e.l}</text>
        </g>
      ))}
    </svg>
  );
};

const ChannelChart = ({ C, color, amp = 1, seed = 0 }) => {
  const W = 400, H = 80;
  const pts = Array.from({length: 60}).map((_,i) => `${i*(W/59)},${H/2 + Math.sin(i*0.3 + seed) * 20 * amp + Math.sin(i*0.7) * 8 * amp}`).join(' ');
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      {[0,1,2,3].map(g => <line key={g} x1="0" x2={W} y1={g*(H/3)} y2={g*(H/3)} stroke={C.line} strokeWidth="0.5"/>)}
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5"/>
    </svg>
  );
};

const MonteHist = ({ C }) => {
  const bars = [3, 6, 12, 22, 38, 55, 70, 78, 70, 55, 38, 22, 12, 6, 3];
  const W = 280, H = 100;
  const bw = W / bars.length;
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`}>
      {bars.map((v, i) => (
        <rect key={i} x={i*bw + 1} y={H - v} width={bw - 2} height={v}
          fill={i < 3 ? C.leaf : i > 11 ? C.rust : C.accent} opacity="0.8"/>
      ))}
      <line x1={bw*7.5} y1="0" x2={bw*7.5} y2={H} stroke={C.ink} strokeWidth="1" strokeDasharray="3,3"/>
      <text x={bw*7.5+4} y="12" fontSize="9" fill={C.ink} fontFamily="JetBrains Mono, monospace">P50</text>
    </svg>
  );
};

const Logo2 = ({ color }) => (
  <svg width="20" height="20" viewBox="0 0 24 24"><circle cx="12" cy="12" r="2" fill={color}/><path d="M12 12 L12 4" stroke={color} strokeWidth="2.5" strokeLinecap="round"/><path d="M12 12 L19 16" stroke={color} strokeWidth="2.5" strokeLinecap="round"/><path d="M12 12 L5 16" stroke={color} strokeWidth="2.5" strokeLinecap="round"/></svg>
);

window.VB = VB;
