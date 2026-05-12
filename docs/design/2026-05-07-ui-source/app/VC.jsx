// Variant C — Glass Cockpit. Modern dark, glassmorphism, premium emerald accents.

const VC = ({ page = 'overview', lang = 'zh' }) => {
  const { useState } = React;
  const [activePage, setActivePage] = useState(page);
  const [activeLang, setLang] = useState(lang);
  const D = window.WMOM_APP;
  const tr = (en, zh) => activeLang === 'zh' ? zh : en;

  const C = {
    bg0: '#0A0F0E',
    bg1: '#0E1815',
    glass: 'rgba(255,255,255,0.04)',
    glassStrong: 'rgba(255,255,255,0.07)',
    border: 'rgba(255,255,255,0.08)',
    borderStrong: 'rgba(255,255,255,0.14)',
    text: '#E8F0EC',
    sub: '#8FA39A',
    faint: '#566860',
    accent: '#3DDC97',     // emerald
    accentDim: 'rgba(61,220,151,0.15)',
    warn: '#FF6B6B',
    warnDim: 'rgba(255,107,107,0.15)',
    amber: '#FFB347',
  };

  return (
    <div data-screen-label={`VC ${activePage}`} style={{
      minHeight: '100%', width: '100%', color: C.text,
      fontFamily: '"Inter Tight", "Inter", system-ui, sans-serif',
      background: `radial-gradient(1200px 700px at 75% -10%, rgba(61,220,151,0.10), transparent 60%), radial-gradient(800px 500px at 0% 100%, rgba(80,120,255,0.06), transparent 60%), ${C.bg0}`,
      display: 'flex', position: 'relative', overflow: 'hidden'
    }}>
      {/* sidebar */}
      <aside style={{
        width: 76, padding: '20px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
        borderRight: `1px solid ${C.border}`, background: 'rgba(0,0,0,0.25)', backdropFilter: 'blur(20px)',
      }}>
        <div style={{ width: 40, height: 40, borderRadius: 12, background: `linear-gradient(135deg, ${C.accent}, #1A8E5C)`, display: 'grid', placeItems: 'center', marginBottom: 16, boxShadow: `0 0 20px ${C.accentDim}` }}>
          <Logo3 color="#0A0F0E"/>
        </div>
        {D.pages.map(p => (
          <button key={p.id} onClick={() => setActivePage(p.id)} title={tr(p.en, p.zh)} style={{
            width: 48, height: 48, borderRadius: 12, border: 'none', cursor: 'pointer',
            background: activePage === p.id ? C.accentDim : 'transparent',
            position: 'relative'
          }}>
            <NavIcon3 id={p.id} color={activePage === p.id ? C.accent : C.sub}/>
            {activePage === p.id && <div style={{ position: 'absolute', left: -16, top: '25%', height: '50%', width: 2, background: C.accent, borderRadius: 2 }}></div>}
          </button>
        ))}
        <div style={{ marginTop: 'auto' }}>
          <button onClick={() => setLang(activeLang === 'zh' ? 'en' : 'zh')} style={{
            width: 40, height: 40, borderRadius: 10, border: `1px solid ${C.border}`,
            background: 'transparent', color: C.sub, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit'
          }}>{activeLang === 'zh' ? 'EN' : '中'}</button>
        </div>
      </aside>

      <main style={{ flex: 1, padding: '28px 36px', overflow: 'hidden' }}>
        {/* Top bar */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <div>
            <div style={{ fontSize: 11, color: C.sub, letterSpacing: 2, textTransform: 'uppercase', marginBottom: 4 }}>WMOM · {tr('Cockpit','駕駛艙')}</div>
            <h1 style={{ fontSize: 28, fontWeight: 600, margin: 0, letterSpacing: -0.5 }}>{tr(D.pages.find(p=>p.id===activePage).en, D.pages.find(p=>p.id===activePage).zh)}</h1>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <div style={{ padding: '6px 12px', borderRadius: 999, border: `1px solid ${C.border}`, background: C.glass, fontSize: 11, color: C.sub, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: C.accent, boxShadow: `0 0 8px ${C.accent}` }}></span>
              LIVE · 1.2s
            </div>
            <Btn3 C={C}>{tr('Export','匯出')}</Btn3>
            <Btn3 C={C} primary>{tr('+ New','+ 新增')}</Btn3>
          </div>
        </div>

        {activePage === 'overview' && <Overview3 C={C} D={D} tr={tr}/>}
        {activePage === 'turbine' && <Turbine3 C={C} D={D} tr={tr}/>}
        {activePage === 'maintenance' && <Maintenance3 C={C} D={D} tr={tr}/>}
        {activePage === 'cost' && <Cost3 C={C} D={D} tr={tr}/>}
        {activePage === 'history' && <History3 C={C} D={D} tr={tr}/>}
      </main>
    </div>
  );
};

const Glass = ({ C, children, style, glow }) => (
  <div style={{
    background: C.glass, border: `1px solid ${C.border}`, borderRadius: 18,
    padding: 20, backdropFilter: 'blur(20px)',
    boxShadow: glow ? `0 0 40px ${C.accentDim}, inset 0 1px 0 rgba(255,255,255,0.05)` : 'inset 0 1px 0 rgba(255,255,255,0.04)',
    ...style
  }}>{children}</div>
);

const Btn3 = ({ C, primary, children, onClick }) => (
  <button onClick={onClick} style={{
    background: primary ? C.accent : C.glass, color: primary ? '#0A0F0E' : C.text,
    border: primary ? 'none' : `1px solid ${C.border}`, borderRadius: 10,
    padding: '8px 14px', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
    backdropFilter: 'blur(10px)',
    boxShadow: primary ? `0 0 20px ${C.accentDim}` : 'none'
  }}>{children}</button>
);

// ── Overview ──
const Overview3 = ({ C, D, tr }) => {
  const total = D.turbines.reduce((s,t) => s+t.power, 0);
  const ops = D.turbines.filter(t => t.status==='OPERATING').length;
  const flt = D.turbines.filter(t => t.status==='FAULT').length;
  const cap = (total / 24) * 100;
  return (
    <div>
      {/* Hero ring */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr 1fr', gap: 16, marginBottom: 18 }}>
        <Glass C={C} glow style={{ padding: 28, position: 'relative', overflow: 'hidden' }}>
          <div style={{ display: 'flex', gap: 24, alignItems: 'center' }}>
            <RingGauge C={C} pct={cap} size={140}/>
            <div>
              <div style={{ fontSize: 11, color: C.sub, letterSpacing: 2, textTransform: 'uppercase' }}>{tr('Farm Power Output','風場總功率')}</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 8 }}>
                <span style={{ fontSize: 64, fontWeight: 200, color: C.text, lineHeight: 1, letterSpacing: -3, fontFeatureSettings: '"tnum"' }}>{total.toFixed(1)}</span>
                <span style={{ fontSize: 18, color: C.accent, fontWeight: 500 }}>MW</span>
              </div>
              <div style={{ fontSize: 12, color: C.sub, marginTop: 6 }}>{cap.toFixed(0)}% {tr('of 24.0 MW capacity','額定容量')}</div>
              <div style={{ display: 'flex', gap: 12, marginTop: 14, fontSize: 11 }}>
                <Pill C={C} color={C.accent}>{tr('Healthy','健康')}</Pill>
                <span style={{ color: C.sub }}>· {tr('+3.2% vs avg','較均值')}</span>
              </div>
            </div>
          </div>
          {/* Decorative wave */}
          <svg width="100%" height="60" viewBox="0 0 600 60" preserveAspectRatio="none" style={{ position: 'absolute', bottom: 0, left: 0, opacity: 0.4 }}>
            <path d="M0,30 Q100,10 200,30 T400,30 T600,30 L600,60 L0,60 Z" fill={`url(#wgrad)`}/>
            <defs><linearGradient id="wgrad" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor={C.accent} stopOpacity="0.4"/><stop offset="100%" stopColor={C.accent} stopOpacity="0"/></linearGradient></defs>
          </svg>
        </Glass>

        <Glass C={C}>
          <div style={{ fontSize: 11, color: C.sub, letterSpacing: 2, textTransform: 'uppercase' }}>{tr('Operating','運轉中')}</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 8 }}>
            <span style={{ fontSize: 48, fontWeight: 300, lineHeight: 1, letterSpacing: -1.5 }}>{ops}</span>
            <span style={{ fontSize: 18, color: C.sub }}>/ 12</span>
          </div>
          <div style={{ display: 'flex', gap: 4, marginTop: 14 }}>
            {D.turbines.map(t => (
              <div key={t.id} style={{
                flex: 1, height: 24, borderRadius: 4,
                background: t.status === 'OPERATING' ? C.accent : t.status === 'FAULT' ? C.warn : t.status === 'IDLE' ? C.amber : C.faint,
                opacity: 0.85
              }}></div>
            ))}
          </div>
          <div style={{ fontSize: 11, color: C.sub, marginTop: 10, display: 'flex', justifyContent: 'space-between' }}>
            <span>WT01</span><span>WT12</span>
          </div>
        </Glass>

        <Glass C={C} style={{ background: flt > 0 ? `linear-gradient(135deg, ${C.warnDim}, ${C.glass})` : C.glass, borderColor: flt > 0 ? C.warn : C.border }}>
          <div style={{ fontSize: 11, color: C.sub, letterSpacing: 2, textTransform: 'uppercase' }}>{tr('Active Faults','故障告警')}</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 8 }}>
            <span style={{ fontSize: 48, fontWeight: 300, color: flt > 0 ? C.warn : C.text, lineHeight: 1 }}>{flt}</span>
          </div>
          {flt > 0 && (
            <div style={{ marginTop: 14, padding: 10, borderRadius: 10, background: 'rgba(255,107,107,0.08)', border: `1px solid rgba(255,107,107,0.2)` }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: C.warn }}>WT010 · {tr('Gearbox','齒輪箱')}</div>
              <div style={{ fontSize: 11, color: C.sub, marginTop: 2 }}>{tr('Overheat developing','過熱發展中')} · 92°C</div>
            </div>
          )}
        </Glass>
      </div>

      {/* Trend + side */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16, marginBottom: 18 }}>
        <Glass C={C} style={{ padding: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{tr('Generation · 24 h','24 小時發電')}</div>
              <div style={{ fontSize: 11, color: C.sub, marginTop: 2 }}>{tr('Smoothed 1-min averages','一分鐘平滑均值')}</div>
            </div>
            <div style={{ display: 'flex', gap: 4, padding: 3, borderRadius: 999, background: C.glass, border: `1px solid ${C.border}` }}>
              {['1H','6H','24H','7D'].map((p,i) => (
                <button key={p} style={{
                  padding: '4px 12px', fontSize: 11, borderRadius: 999, border: 'none', cursor: 'pointer', fontFamily: 'inherit',
                  background: i===2 ? C.accent : 'transparent', color: i===2 ? '#0A0F0E' : C.sub, fontWeight: i===2 ? 600 : 400
                }}>{p}</button>
              ))}
            </div>
          </div>
          <BigChart3 C={C}/>
        </Glass>
        <Glass C={C}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>{tr('Site map','風場配置')}</div>
          <FarmMap3 C={C} D={D}/>
        </Glass>
      </div>

      {/* Turbine grid */}
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, display: 'flex', justifyContent: 'space-between' }}>
        <span>{tr('Fleet','機隊')}</span>
        <span style={{ fontSize: 11, color: C.sub, fontWeight: 400 }}>12 {tr('units','台')}</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {D.turbines.map(t => <TCard3 key={t.id} t={t} C={C} tr={tr}/>)}
      </div>
    </div>
  );
};

const TCard3 = ({ t, C, tr }) => {
  const stColor = t.status === 'OPERATING' ? C.accent : t.status === 'FAULT' ? C.warn : t.status === 'IDLE' ? C.amber : C.faint;
  return (
    <Glass C={C} style={{ padding: 16, position: 'relative', overflow: 'hidden' }}>
      {t.status === 'FAULT' && <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(135deg, ${C.warnDim}, transparent 60%)`, pointerEvents: 'none' }}></div>}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, position: 'relative' }}>
        <span style={{ fontWeight: 600, fontSize: 14, letterSpacing: -0.3 }}>{t.name}</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 10, color: stColor, fontWeight: 600, letterSpacing: 1 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: stColor, boxShadow: `0 0 6px ${stColor}` }}></span>
          {t.status === 'OPERATING' ? tr('LIVE','運轉') : t.status === 'FAULT' ? tr('FAULT','故障') : t.status === 'IDLE' ? tr('IDLE','待機') : tr('OFF','離線')}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, position: 'relative' }}>
        <span style={{ fontSize: 28, fontWeight: 200, color: stColor, lineHeight: 1, letterSpacing: -1, fontFeatureSettings: '"tnum"' }}>{t.power.toFixed(2)}</span>
        <span style={{ fontSize: 11, color: C.sub }}>MW</span>
      </div>
      <svg width="100%" height="28" viewBox="0 0 100 28" preserveAspectRatio="none" style={{ marginTop: 6 }}>
        <defs><linearGradient id={`tgrad-${t.id}`} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor={stColor} stopOpacity="0.5"/><stop offset="100%" stopColor={stColor} stopOpacity="0"/></linearGradient></defs>
        <path d={`M0,${28-t.power*8} ${Array.from({length:24}).map((_,i)=>`L${i*4.2},${18-Math.sin(i*0.5+t.id)*5-(t.power*4)}`).join(' ')} L100,28 L0,28 Z`} fill={`url(#tgrad-${t.id})`}/>
        <polyline fill="none" stroke={stColor} strokeWidth="1.5"
          points={Array.from({length: 24}).map((_,i)=>`${i*4.2},${18-Math.sin(i*0.5+t.id)*5-(t.power*4)}`).join(' ')}/>
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: C.sub, marginTop: 6, fontFeatureSettings: '"tnum"' }}>
        <span>{t.wind} m/s</span><span>{t.rpm} rpm</span><span>{t.gearTemp.toFixed(0)}°</span>
      </div>
    </Glass>
  );
};

const Pill = ({ C, color, children }) => (
  <span style={{ padding: '2px 10px', borderRadius: 999, fontSize: 10, fontWeight: 600, background: color + '25', color, letterSpacing: 0.5 }}>{children}</span>
);

const RingGauge = ({ C, pct, size = 120 }) => {
  const r = size/2 - 8;
  const circ = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <defs>
        <linearGradient id="ringg" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor={C.accent}/>
          <stop offset="100%" stopColor="#1A8E5C"/>
        </linearGradient>
      </defs>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={C.border} strokeWidth="6"/>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="url(#ringg)" strokeWidth="6" strokeLinecap="round"
        strokeDasharray={`${(pct/100)*circ} ${circ}`} transform={`rotate(-90 ${size/2} ${size/2})`}/>
      <text x={size/2} y={size/2-2} textAnchor="middle" fontSize="22" fill={C.text} fontWeight="300" letterSpacing="-1">{pct.toFixed(0)}<tspan fontSize="12" fill={C.sub}>%</tspan></text>
      <text x={size/2} y={size/2+18} textAnchor="middle" fontSize="9" fill={C.sub} letterSpacing="2">CAPACITY</text>
    </svg>
  );
};

// ── Turbine ──
const Turbine3 = ({ C, D, tr }) => {
  const t = D.turbines[1];
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 16, marginBottom: 16 }}>
        <Glass C={C} glow style={{ padding: 28, position: 'relative' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
            <div>
              <div style={{ fontSize: 11, color: C.sub, letterSpacing: 2, textTransform: 'uppercase' }}>{t.name} · Bachmann Z72</div>
              <div style={{ fontSize: 22, fontWeight: 600, marginTop: 4 }}>{tr('Production','正常發電')}</div>
            </div>
            <Pill C={C} color={C.accent}>● {tr('OPERATING','運轉中')}</Pill>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
            {[
              { k: tr('Power','功率'), v: t.power.toFixed(2), u: 'MW', big: true },
              { k: tr('Wind','風速'), v: t.wind, u: 'm/s' },
              { k: 'RPM', v: t.rpm, u: 'rpm' },
              { k: tr('Gear','齒輪'), v: t.gearTemp.toFixed(0), u: '°C' },
            ].map((m, i) => (
              <div key={i}>
                <div style={{ fontSize: 10, color: C.sub, letterSpacing: 1.5, textTransform: 'uppercase' }}>{m.k}</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginTop: 6 }}>
                  <span style={{ fontSize: m.big ? 36 : 24, fontWeight: m.big ? 200 : 300, color: m.big ? C.accent : C.text, lineHeight: 1, letterSpacing: -1, fontFeatureSettings: '"tnum"' }}>{m.v}</span>
                  <span style={{ fontSize: 11, color: C.sub }}>{m.u}</span>
                </div>
              </div>
            ))}
          </div>
        </Glass>
        <Glass C={C}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>{tr('Quick Actions','快速操作')}</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
            <Btn3 C={C}>▶ {tr('Start','啟動')}</Btn3>
            <Btn3 C={C}>■ {tr('Stop','停機')}</Btn3>
            <Btn3 C={C}>{tr('Curtail','限載')}</Btn3>
            <Btn3 C={C} primary>{tr('Inspect','檢查')}</Btn3>
          </div>
          <div style={{ padding: 10, borderRadius: 10, background: C.warnDim, border: `1px solid rgba(255,107,107,0.2)`, fontSize: 11, color: C.warn, textAlign: 'center', cursor: 'pointer' }}>
            ⚠ {tr('Emergency Stop','緊急停機')}
          </div>
        </Glass>
      </div>

      {/* Channels */}
      <Glass C={C} style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>{tr('Live Telemetry · 4 channels','即時遙測　四通道')}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 18 }}>
          {[
            { l: 'Power · MW', v: t.power.toFixed(2), c: C.accent, amp: 1 },
            { l: 'Wind · m/s', v: t.wind, c: '#7BB6FF', amp: 0.7 },
            { l: 'Gearbox · °C', v: t.gearTemp.toFixed(0), c: C.amber, amp: 0.5 },
            { l: 'Vibration · mm/s', v: t.vib.toFixed(2), c: C.warn, amp: 1.4 },
          ].map((ch, i) => (
            <div key={i} style={{ background: 'rgba(0,0,0,0.2)', borderRadius: 12, padding: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 11, color: C.sub, letterSpacing: 1, textTransform: 'uppercase' }}>{ch.l}</span>
                <span style={{ fontSize: 14, fontWeight: 600, color: ch.c, fontFeatureSettings: '"tnum"' }}>{ch.v}</span>
              </div>
              <ChannelChart3 C={C} color={ch.c} amp={ch.amp} seed={i}/>
            </div>
          ))}
        </div>
      </Glass>

      {/* Subsystems */}
      <Glass C={C} style={{ padding: 24 }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>{tr('Subsystem Health','子系統健康')}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: 14 }}>
          {[
            { k: tr('Generator','發電機'), s: 92 }, { k: tr('Gearbox','齒輪箱'), s: 78 },
            { k: tr('Pitch','變槳'), s: 88 }, { k: tr('Yaw','偏航'), s: 95 },
            { k: tr('Tower','塔筒'), s: 90 }, { k: tr('Blades','葉片'), s: 84 },
            { k: tr('Converter','變頻'), s: 91 }, { k: tr('Cooling','冷卻'), s: 87 },
          ].map(s => {
            const col = s.s > 85 ? C.accent : s.s > 75 ? C.amber : C.warn;
            return (
              <div key={s.k} style={{ textAlign: 'center' }}>
                <div style={{ position: 'relative', width: 60, height: 60, margin: '0 auto' }}>
                  <RingGauge C={C} pct={s.s} size={60}/>
                </div>
                <div style={{ fontSize: 11, color: C.sub, marginTop: 4 }}>{s.k}</div>
              </div>
            );
          })}
        </div>
      </Glass>
    </div>
  );
};

// ── Maintenance ──
const Maintenance3 = ({ C, D, tr }) => (
  <div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 18 }}>
      {[
        { l: tr('Open','未結'), v: D.workOrders.filter(w=>w.status!=='COMPLETED').length, c: C.accent },
        { l: tr('High priority','高優先'), v: D.workOrders.filter(w=>w.priority==='HIGH').length, c: C.warn },
        { l: tr('On duty','在崗'), v: D.technicians.filter(t=>t.status!=='OFF_DUTY').length, c: C.text },
        { l: tr('Avg SLA','平均 SLA'), v: '4.2', u: 'h', c: C.amber },
      ].map((m,i) => (
        <Glass key={i} C={C}>
          <div style={{ fontSize: 11, color: C.sub, letterSpacing: 1.5, textTransform: 'uppercase' }}>{m.l}</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginTop: 6 }}>
            <span style={{ fontSize: 36, fontWeight: 200, color: m.c, lineHeight: 1, letterSpacing: -1 }}>{m.v}</span>
            {m.u && <span style={{ fontSize: 12, color: C.sub }}>{m.u}</span>}
          </div>
        </Glass>
      ))}
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '1.6fr 1fr', gap: 16 }}>
      <Glass C={C} style={{ padding: 0 }}>
        <div style={{ padding: '16px 20px', borderBottom: `1px solid ${C.border}`, fontSize: 14, fontWeight: 600 }}>{tr('Work Orders','工單')}</div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ color: C.sub }}>
              {[tr('ID','編號'), tr('Turbine','風機'), tr('Issue','問題'), tr('Tech','技師'), 'PRI', 'SLA'].map(h=>(
                <th key={h} style={{ textAlign: 'left', padding: '12px 16px', fontSize: 10, fontWeight: 500, letterSpacing: 1.5, textTransform: 'uppercase', borderBottom: `1px solid ${C.border}` }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {D.workOrders.map(w => {
              const pc = w.priority === 'HIGH' ? C.warn : w.priority === 'MED' ? C.amber : C.faint;
              return (
                <tr key={w.id} style={{ borderBottom: `1px solid ${C.border}` }}>
                  <td style={{ padding: '14px 16px', fontFamily: 'JetBrains Mono, monospace', color: C.sub, fontSize: 11 }}>{w.id.slice(-6)}</td>
                  <td style={{ padding: '14px 16px', fontWeight: 600 }}>{w.tid}</td>
                  <td style={{ padding: '14px 16px' }}>{tr(w.issue_en, w.issue_zh)}</td>
                  <td style={{ padding: '14px 16px', color: C.sub }}>{tr(w.techEn, w.tech)}</td>
                  <td style={{ padding: '14px 16px' }}><Pill C={C} color={pc}>{w.priority}</Pill></td>
                  <td style={{ padding: '14px 16px', fontSize: 11, color: C.sub }}>{w.sla}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Glass>
      <Glass C={C}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>{tr('Crew','技師')}</div>
        {D.technicians.map(t => (
          <div key={t.name} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 0', borderBottom: `1px solid ${C.border}` }}>
            <div style={{ width: 38, height: 38, borderRadius: '50%', background: `linear-gradient(135deg, ${C.accent}, #1A8E5C)`, display: 'grid', placeItems: 'center', color: '#0A0F0E', fontWeight: 700, fontSize: 13, boxShadow: `0 0 12px ${C.accentDim}` }}>
              {tr(t.nameEn, t.name).charAt(0)}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{tr(t.nameEn, t.name)}</div>
              <div style={{ fontSize: 11, color: C.sub }}>{t.skill}</div>
            </div>
            <Pill C={C} color={t.status === 'ON_DUTY' ? C.accent : t.status === 'DISPATCHED' ? C.amber : C.faint}>
              {t.status === 'ON_DUTY' ? tr('ON','在崗') : t.status === 'DISPATCHED' ? tr('OUT','派遣') : tr('OFF','下班')}
            </Pill>
          </div>
        ))}
      </Glass>
    </div>
  </div>
);

// ── Cost ──
const Cost3 = ({ C, D, tr }) => (
  <div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 16 }}>
      {D.cost.metrics.map((m, i) => (
        <Glass key={i} C={C} glow={i===1}>
          <div style={{ fontSize: 11, color: C.sub, letterSpacing: 1.5, textTransform: 'uppercase' }}>{tr(m.label_en, m.label_zh)}</div>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: 8 }}>
            <span style={{ fontSize: 30, fontWeight: 300, color: i===1 ? C.accent : C.text, lineHeight: 1, letterSpacing: -0.8, fontFeatureSettings: '"tnum"' }}>{m.val}</span>
            {m.delta && <Pill C={C} color={m.delta.startsWith('+') ? C.accent : m.delta.startsWith('−') ? C.accent : C.sub}>{m.delta}</Pill>}
          </div>
        </Glass>
      ))}
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
      <Glass C={C} style={{ padding: 24 }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>{tr('20-yr Revenue Forecast · P10/P50/P90','20 年營收預測　P10/P50/P90')}</div>
        <BigChart3 C={C} kind="forecast"/>
      </Glass>
      <Glass C={C}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>{tr('Monte Carlo · 5,000','蒙地卡羅　5,000')}</div>
        <MonteHist3 C={C}/>
        {[
          { k: 'P10', v: D.cost.monteCarlo.p10, c: C.accent },
          { k: 'P50', v: D.cost.monteCarlo.p50, c: C.text },
          { k: 'P90', v: D.cost.monteCarlo.p90, c: C.warn },
        ].map(r => (
          <div key={r.k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '10px 0', borderBottom: `1px solid ${C.border}` }}>
            <Pill C={C} color={r.c}>{r.k}</Pill>
            <span style={{ fontSize: 18, fontWeight: 300, fontFeatureSettings: '"tnum"' }}>{r.v}<span style={{ fontSize: 11, color: C.sub }}> ¢/kWh</span></span>
          </div>
        ))}
      </Glass>
    </div>
  </div>
);

// ── History ──
const History3 = ({ C, D, tr }) => (
  <div>
    <Glass C={C} style={{ marginBottom: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
        {[
          { l: tr('Turbine','風機'), v: 'WT002' },
          { l: tr('Range','時間'), v: '2026-05-01 → 05-07' },
          { l: tr('Tags','標籤'), v: 'TotPwrAt + 3' },
          { l: tr('Events','事件'), v: 'Faults · Wind' },
        ].map(f => (
          <div key={f.l}>
            <div style={{ fontSize: 10, color: C.sub, letterSpacing: 1.5, textTransform: 'uppercase', marginBottom: 6 }}>{f.l}</div>
            <div style={{ padding: '8px 12px', background: 'rgba(0,0,0,0.25)', borderRadius: 8, fontSize: 13, border: `1px solid ${C.border}` }}>{f.v}</div>
          </div>
        ))}
      </div>
    </Glass>
    <Glass C={C} style={{ padding: 24, marginBottom: 16 }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>{tr('Power output with events','功率輸出與事件')}</div>
      <BigChart3 C={C} kind="events"/>
    </Glass>
    <Glass C={C} style={{ padding: 0 }}>
      <div style={{ padding: '16px 20px', borderBottom: `1px solid ${C.border}`, fontSize: 14, fontWeight: 600 }}>{tr('Event log','事件日誌')}</div>
      {[
        { t: '05/06 09:14:22', tag: 'FAULT', en: 'Gearbox overheat — phase: developing', zh: '齒輪箱過熱　階段：發展中', sev: C.warn },
        { t: '05/06 08:42:11', tag: 'WIND',  en: 'Wind ramp +3.2 m/s in 60s', zh: '風速急升 +3.2 m/s（60 秒）', sev: '#7BB6FF' },
        { t: '05/06 06:00:04', tag: 'STATE', en: 'WT002 synchronized', zh: 'WT002 併網成功', sev: C.accent },
        { t: '05/06 05:45:18', tag: 'STATE', en: 'WT002 startup begin', zh: 'WT002 啟動開始', sev: C.sub },
        { t: '05/05 22:08:56', tag: 'OFFL',  en: 'WT012 communications lost', zh: 'WT012 通訊離線', sev: C.warn },
      ].map(e => (
        <div key={e.t} style={{ display: 'grid', gridTemplateColumns: '180px 80px 1fr', gap: 14, padding: '14px 20px', borderBottom: `1px solid ${C.border}`, alignItems: 'center' }}>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: C.sub }}>{e.t}</span>
          <Pill C={C} color={e.sev}>{e.tag}</Pill>
          <span style={{ fontSize: 13 }}>{tr(e.en, e.zh)}</span>
        </div>
      ))}
    </Glass>
  </div>
);

// ── Charts/maps ──
const BigChart3 = ({ C, kind = 'power' }) => {
  const W = 800, H = 220;
  const points = Array.from({ length: 80 }).map((_,i) => ({
    x: i * (W/79),
    y: H/2 + Math.sin(i*0.2) * 30 + Math.sin(i*0.5) * 12 - (i > 40 && i < 50 ? 25 : 0)
  }));
  const path = points.map((p,i) => `${i===0?'M':'L'}${p.x},${p.y}`).join(' ');
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id="bg3" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={C.accent} stopOpacity="0.4"/>
          <stop offset="100%" stopColor={C.accent} stopOpacity="0"/>
        </linearGradient>
      </defs>
      {[0,1,2,3,4].map(g => <line key={g} x1="0" x2={W} y1={g*55} y2={g*55} stroke={C.border} strokeWidth="0.5"/>)}
      {kind === 'forecast' && (
        <path d={`M0,${H/2-50} ${points.map(p=>`L${p.x},${p.y-30}`).join(' ')} L${W},${H/2+50} ${points.slice().reverse().map(p=>`L${p.x},${p.y+30}`).join(' ')} Z`} fill={C.accent} fillOpacity="0.1"/>
      )}
      <path d={`${path} L${W},${H} L0,${H} Z`} fill="url(#bg3)"/>
      <path d={path} stroke={C.accent} strokeWidth="2" fill="none" style={{ filter: `drop-shadow(0 0 4px ${C.accent})` }}/>
      {kind === 'events' && [
        { x: 200, c: C.warn, l: 'FAULT' },
        { x: 380, c: '#7BB6FF', l: 'WIND' },
        { x: 560, c: C.accent, l: 'SYNC' },
      ].map(e => (
        <g key={e.x}>
          <line x1={e.x} x2={e.x} y1="20" y2={H-10} stroke={e.c} strokeWidth="1" strokeDasharray="3,3" opacity="0.6"/>
          <circle cx={e.x} cy="14" r="5" fill={e.c}/>
        </g>
      ))}
    </svg>
  );
};

const ChannelChart3 = ({ C, color, amp = 1, seed = 0 }) => {
  const W = 400, H = 70;
  const pts = Array.from({length: 60}).map((_,i) => `${i*(W/59)},${H/2 + Math.sin(i*0.3 + seed) * 18 * amp + Math.sin(i*0.7) * 6 * amp}`).join(' ');
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={`cg-${seed}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.4"/>
          <stop offset="100%" stopColor={color} stopOpacity="0"/>
        </linearGradient>
      </defs>
      <polyline points={`0,${H} ${pts} ${W},${H}`} fill={`url(#cg-${seed})`}/>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" style={{ filter: `drop-shadow(0 0 3px ${color})` }}/>
    </svg>
  );
};

const FarmMap3 = ({ C, D }) => (
  <svg width="100%" height="220" viewBox="0 0 320 220">
    <defs>
      <radialGradient id="seaG" cx="50%" cy="100%" r="80%">
        <stop offset="0%" stopColor="rgba(80,160,255,0.2)"/>
        <stop offset="100%" stopColor="rgba(80,160,255,0)"/>
      </radialGradient>
    </defs>
    <rect x="0" y="0" width="320" height="220" fill="url(#seaG)"/>
    <path d="M0,40 Q60,50 110,80 T220,140 T320,200" stroke={C.border} strokeWidth="1" fill="none" strokeDasharray="3,2"/>
    {D.turbines.map((t, i) => {
      const x = 50 + (i % 4) * 65;
      const y = 60 + Math.floor(i / 4) * 60;
      const c = t.status === 'OPERATING' ? C.accent : t.status === 'FAULT' ? C.warn : t.status === 'IDLE' ? C.amber : C.faint;
      return (
        <g key={t.id}>
          <circle cx={x} cy={y} r="10" fill={c} fillOpacity="0.15"/>
          <circle cx={x} cy={y} r="5" fill={c} style={{ filter: `drop-shadow(0 0 4px ${c})` }}/>
          <text x={x + 8} y={y - 8} fontSize="8" fill={C.sub} fontFamily="monospace">{t.name}</text>
        </g>
      );
    })}
  </svg>
);

const MonteHist3 = ({ C }) => {
  const bars = [3, 6, 12, 22, 38, 55, 70, 78, 70, 55, 38, 22, 12, 6, 3];
  const W = 280, H = 90;
  const bw = W / bars.length;
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} style={{ marginBottom: 12 }}>
      {bars.map((v, i) => (
        <rect key={i} x={i*bw + 1} y={H - v} width={bw - 2} height={v}
          rx="2" fill={i < 3 ? C.accent : i > 11 ? C.warn : C.amber} opacity={i===7 ? 1 : 0.6}/>
      ))}
    </svg>
  );
};

const Logo3 = ({ color }) => (
  <svg width="22" height="22" viewBox="0 0 24 24"><circle cx="12" cy="12" r="2" fill={color}/><path d="M12 12 L12 4" stroke={color} strokeWidth="2.5" strokeLinecap="round"/><path d="M12 12 L19 16" stroke={color} strokeWidth="2.5" strokeLinecap="round"/><path d="M12 12 L5 16" stroke={color} strokeWidth="2.5" strokeLinecap="round"/></svg>
);

const NavIcon3 = ({ id, color }) => {
  const m = {
    overview: <g stroke={color} strokeWidth="1.6" fill="none"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></g>,
    turbine: <g stroke={color} strokeWidth="1.6" fill="none"><circle cx="12" cy="9" r="2"/><path d="M12 11v10M12 9V3M12 9l5-3M12 9l-5-3"/></g>,
    maintenance: <g stroke={color} strokeWidth="1.6" fill="none" strokeLinecap="round"><path d="M14 4l-3 3 5 5 3-3a3.5 3.5 0 1 0-5-5z"/><path d="M11 7L4 14l3 3 7-7"/></g>,
    cost: <g stroke={color} strokeWidth="1.6" fill="none" strokeLinecap="round"><path d="M12 4v16M8 8h6a2 2 0 1 1 0 4H10a2 2 0 1 0 0 4h7"/></g>,
    history: <g stroke={color} strokeWidth="1.6" fill="none" strokeLinecap="round"><circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/></g>,
  };
  return <svg width="22" height="22" viewBox="0 0 24 24">{m[id]}</svg>;
};

window.VC = VC;
