// Variant A — Calm Operator. Light, friendly, sage greens, generous spacing.
// Renders any of: overview | turbine | maintenance | cost | history

const VA = ({ page = 'overview', lang = 'zh', theme = 'light' }) => {
  const { useState } = React;
  const [activePage, setActivePage] = useState(page);
  const [activeLang, setLang] = useState(lang);
  const [activeTheme, setTheme] = useState(theme);
  const D = window.WMOM_APP;
  const tr = (en, zh) => activeLang === 'zh' ? zh : en;

  // ── Palettes (light = sage editorial · dark = emerald cockpit, same layout) ──
  const C = activeTheme === 'dark' ? {
    bg: '#0E1815', panel: '#152320', border: 'rgba(255,255,255,0.10)',
    text: '#E8F0EC', sub: '#8FA39A', faint: '#566860',
    accent: '#3DDC97', accentSoft: 'rgba(61,220,151,0.16)',
    warn: '#FF8E72', warnSoft: 'rgba(255,142,114,0.18)',
    ok: '#3DDC97', okSoft: 'rgba(61,220,151,0.16)',
    isDark: true,
  } : {
    bg: '#F5F2EA', panel: '#FFFFFF', border: '#E5E0D2',
    text: '#1F2D24', sub: '#6B7669', faint: '#9BA39A',
    accent: '#3F6B53', accentSoft: '#E2EBE3',
    warn: '#C97B5A', warnSoft: '#FBE8DD',
    ok: '#5C8A5F', okSoft: '#DEEAD9',
    isDark: false,
  };

  return (
    <div data-screen-label={`VA ${activePage}`} style={{
      background: C.bg, color: C.text, minHeight: '100%', width: '100%',
      fontFamily: 'Manrope, system-ui, sans-serif', display: 'flex'
    }}>
      {/* Sidebar */}
      <aside style={{
        width: 220, background: C.panel, borderRight: `1px solid ${C.border}`,
        padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: 4
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 8px 20px', borderBottom: `1px solid ${C.border}`, marginBottom: 12 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: C.accent, display: 'grid', placeItems: 'center' }}>
            <Logo color="#FFF"/>
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700 }}>WMOM</div>
            <div style={{ fontSize: 11, color: C.sub }}>{tr('Operations', '營運平台')}</div>
          </div>
        </div>
        {D.pages.map(p => (
          <button key={p.id} onClick={() => setActivePage(p.id)} style={{
            display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
            borderRadius: 8, border: 'none', textAlign: 'left', cursor: 'pointer',
            background: activePage === p.id ? C.accentSoft : 'transparent',
            color: activePage === p.id ? C.accent : C.text, fontWeight: activePage === p.id ? 600 : 500,
            fontSize: 14, fontFamily: 'inherit'
          }}>
            <NavIcon id={p.id} color={activePage === p.id ? C.accent : C.sub}/>
            <span>{tr(p.en, p.zh)}</span>
          </button>
        ))}
        <div style={{ marginTop: 'auto', paddingTop: 16, borderTop: `1px solid ${C.border}`, fontSize: 12, color: C.sub }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: C.ok }}></span>
            {tr('Backend healthy', '後端正常')}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={() => setLang(activeLang === 'zh' ? 'en' : 'zh')}
              style={{ background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 6, padding: '4px 10px', fontSize: 11, cursor: 'pointer', color: C.sub, fontFamily: 'inherit' }}>
              {activeLang === 'zh' ? 'EN' : '中文'}
            </button>
            <button onClick={() => setTheme(activeTheme === 'dark' ? 'light' : 'dark')}
              title={tr('Theme', '主題')}
              style={{ background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 6, padding: '4px 8px', fontSize: 12, cursor: 'pointer', color: C.sub, fontFamily: 'inherit', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              {activeTheme === 'dark' ? '☀' : '☾'} {activeTheme === 'dark' ? tr('Light','日')  : tr('Dark','夜')}
            </button>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main style={{ flex: 1, padding: '28px 36px' }}>
        {activePage === 'overview' && <Overview C={C} D={D} tr={tr}/>}
        {activePage === 'turbine' && <Turbine C={C} D={D} tr={tr}/>}
        {activePage === 'maintenance' && <Maintenance C={C} D={D} tr={tr}/>}
        {activePage === 'cost' && <Cost C={C} D={D} tr={tr}/>}
        {activePage === 'history' && <History C={C} D={D} tr={tr}/>}
      </main>
    </div>
  );
};

// ── Helpers ──
const Card = ({ C, children, style, padding = 20 }) => (
  <div style={{ background: C.panel, border: `1px solid ${C.border}`, borderRadius: 14, padding, ...style }}>{children}</div>
);

const PageHeader = ({ C, title, sub, actions }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 24 }}>
    <div>
      <h1 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 38, lineHeight: 1, margin: 0, fontWeight: 400, letterSpacing: -0.8, color: C.text }}>{title}</h1>
      {sub && <div style={{ fontSize: 14, color: C.sub, marginTop: 6 }}>{sub}</div>}
    </div>
    <div style={{ display: 'flex', gap: 8 }}>{actions}</div>
  </div>
);

const Btn = ({ C, primary, children, onClick }) => (
  <button onClick={onClick} style={{
    background: primary ? C.accent : C.panel,
    color: primary ? (C.isDark ? '#0A0F0E' : '#FFF') : C.text,
    border: primary ? 'none' : `1px solid ${C.border}`, borderRadius: 8,
    padding: '8px 14px', fontSize: 13, fontWeight: primary && C.isDark ? 600 : 500, cursor: 'pointer', fontFamily: 'inherit'
  }}>{children}</button>
);

// ── Pages ──
const Overview = ({ C, D, tr }) => {
  const total = D.turbines.reduce((s,t) => s+t.power, 0);
  const ops = D.turbines.filter(t => t.status==='OPERATING').length;
  const flt = D.turbines.filter(t => t.status==='FAULT').length;
  return (
    <div>
      <PageHeader C={C}
        title={tr('Good morning, Operator.', '早安，營運團隊。')}
        sub={tr('Changhua Coastal · 12 turbines · ' + new Date().toLocaleDateString(), '彰化沿海　12 機・' + new Date().toLocaleDateString('zh-TW'))}
        actions={<><Btn C={C}>{tr('Export', '匯出')}</Btn><Btn C={C} primary>{tr('+ New Report', '+ 新報告')}</Btn></>}
      />
      {/* Hero stat strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 20 }}>
        <Card C={C}>
          <div style={{ fontSize: 12, color: C.sub, letterSpacing: 1, textTransform: 'uppercase' }}>{tr('Farm Power', '風場功率')}</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 6 }}>
            <span style={{ fontFamily: '"DM Serif Display", serif', fontSize: 40, color: C.accent, lineHeight: 1, fontWeight: 400 }}>{total.toFixed(1)}</span>
            <span style={{ fontSize: 14, color: C.sub }}>MW</span>
          </div>
          <div style={{ fontSize: 12, color: C.sub, marginTop: 8 }}>{tr('of 24.0 MW rated', '額定 24.0 MW')}</div>
        </Card>
        <Card C={C}>
          <div style={{ fontSize: 12, color: C.sub, letterSpacing: 1, textTransform: 'uppercase' }}>{tr('Operating', '運轉中')}</div>
          <div style={{ fontFamily: '"DM Serif Display", serif', fontSize: 40, color: C.text, lineHeight: 1, marginTop: 6, fontWeight: 400 }}>{ops}<span style={{ fontSize: 18, color: C.sub }}> / 12</span></div>
          <div style={{ fontSize: 12, color: C.ok, marginTop: 8 }}>{tr('Healthy', '健康')}</div>
        </Card>
        <Card C={C} style={{ background: flt > 0 ? C.warnSoft : C.panel, borderColor: flt > 0 ? C.warn : C.border }}>
          <div style={{ fontSize: 12, color: C.sub, letterSpacing: 1, textTransform: 'uppercase' }}>{tr('Active Faults', '故障中')}</div>
          <div style={{ fontFamily: '"DM Serif Display", serif', fontSize: 40, color: flt > 0 ? C.warn : C.text, lineHeight: 1, marginTop: 6, fontWeight: 400 }}>{flt}</div>
          <div style={{ fontSize: 12, color: C.sub, marginTop: 8 }}>{flt > 0 ? tr('Needs attention →', '請關注 →') : tr('All clear', '一切順利')}</div>
        </Card>
        <Card C={C}>
          <div style={{ fontSize: 12, color: C.sub, letterSpacing: 1, textTransform: 'uppercase' }}>{tr('Avg Wind', '平均風速')}</div>
          <div style={{ fontFamily: '"DM Serif Display", serif', fontSize: 40, color: C.text, lineHeight: 1, marginTop: 6, fontWeight: 400 }}>{(D.turbines.reduce((s,t)=>s+t.wind,0)/12).toFixed(1)}<span style={{ fontSize: 18, color: C.sub }}> m/s</span></div>
          <div style={{ fontSize: 12, color: C.sub, marginTop: 8 }}>270° {tr('WSW', '西南')}</div>
        </Card>
      </div>

      {/* Trend */}
      <Card C={C} style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>{tr('Farm power, last 24 h', '風場功率　近 24 小時')}</div>
            <div style={{ fontSize: 12, color: C.sub, marginTop: 2 }}>{tr('Hover to inspect events', '滑入查看事件')}</div>
          </div>
          <div style={{ display: 'flex', gap: 4 }}>
            {['1H','6H','24H','7D'].map((p,i) => (
              <button key={p} style={{
                padding: '4px 10px', fontSize: 12, borderRadius: 6,
                background: i===2 ? C.accent : 'transparent', color: i===2 ? '#FFF' : C.sub,
                border: i===2 ? 'none' : `1px solid ${C.border}`, cursor: 'pointer', fontFamily: 'inherit'
              }}>{p}</button>
            ))}
          </div>
        </div>
        <BigChart C={C}/>
      </Card>

      {/* Turbine cards */}
      <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>{tr('Turbines', '風機列表')}</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {D.turbines.map(t => <TCard key={t.id} t={t} C={C} tr={tr}/>)}
      </div>
    </div>
  );
};

const TCard = ({ t, C, tr }) => {
  const stColor = t.status === 'OPERATING' ? C.ok : t.status === 'FAULT' ? C.warn : t.status === 'IDLE' ? (C.isDark ? '#FFB347' : '#B8A053') : C.faint;
  const stBg = t.status === 'OPERATING' ? C.okSoft : t.status === 'FAULT' ? C.warnSoft : t.status === 'IDLE' ? (C.isDark ? 'rgba(255,179,71,0.16)' : '#FAF3E0') : (C.isDark ? 'rgba(255,255,255,0.06)' : '#EFEFEC');
  return (
    <Card C={C} padding={16}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ fontWeight: 700, fontSize: 15 }}>{t.name}</span>
        <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 999, background: stBg, color: stColor, letterSpacing: 0.5 }}>
          {t.status === 'OPERATING' ? tr('OPERATING', '運轉中') : t.status === 'FAULT' ? tr('FAULT', '故障') : t.status === 'IDLE' ? tr('IDLE', '待機') : tr('OFFLINE', '離線')}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
        <span style={{ fontFamily: '"DM Serif Display", serif', fontSize: 32, color: C.accent, fontWeight: 400, lineHeight: 1 }}>{t.power.toFixed(2)}</span>
        <span style={{ fontSize: 12, color: C.sub }}>MW</span>
      </div>
      {/* sparkline */}
      <svg width="100%" height="32" viewBox="0 0 100 32" preserveAspectRatio="none" style={{ marginTop: 8 }}>
        <polyline fill="none" stroke={stColor} strokeWidth="1.5"
          points={Array.from({length: 24}).map((_,i)=>`${i*4.2},${20-Math.sin(i*0.5+t.id)*6-(t.power*4)}`).join(' ')}/>
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: C.sub, marginTop: 6 }}>
        <span>{t.wind} m/s</span><span>{t.rpm} rpm</span><span>{t.gearTemp.toFixed(0)}°C</span>
      </div>
    </Card>
  );
};

const Turbine = ({ C, D, tr }) => {
  const t = D.turbines[1];
  return (
    <div>
      <div style={{ fontSize: 12, color: C.sub, marginBottom: 8 }}>
        ← {tr('Farm Overview', '風場總覽')} / {t.name}
      </div>
      <PageHeader C={C}
        title={`${t.name} · ${tr('Production', '正常發電')}`}
        sub={tr('Bachmann Z72 · TurState 6 · ' + 'Healthy', 'Bachmann Z72 · 狀態 6 · 健康')}
        actions={<><Btn C={C}>{tr('Curtail', '限載')}</Btn><Btn C={C}>{tr('Stop', '停機')}</Btn><Btn C={C} primary>{tr('Inspect', '安排檢查')}</Btn></>}
      />
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
        <div>
          {/* Big metrics */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 14 }}>
            {[
              { k: tr('Power','功率'), v: t.power.toFixed(2), u: 'MW', accent: true },
              { k: tr('Wind','風速'), v: t.wind, u: 'm/s' },
              { k: 'RPM', v: t.rpm, u: 'rpm' },
              { k: tr('Gear Temp','齒輪溫'), v: t.gearTemp.toFixed(0), u: '°C' },
            ].map((m,i) => (
              <Card C={C} key={i} padding={14}>
                <div style={{ fontSize: 11, color: C.sub, textTransform: 'uppercase', letterSpacing: 1 }}>{m.k}</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginTop: 4 }}>
                  <span style={{ fontFamily: '"DM Serif Display", serif', fontSize: 28, color: m.accent ? C.accent : C.text, fontWeight: 400 }}>{m.v}</span>
                  <span style={{ fontSize: 11, color: C.sub }}>{m.u}</span>
                </div>
              </Card>
            ))}
          </div>
          {/* Trends */}
          <Card C={C} style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>{tr('Live trends · 4 channels', '即時趨勢　四通道')}</div>
            {['Power MW','Wind m/s','Gear °C','Vib mm/s'].map((label,i) => (
              <div key={label} style={{ display: 'grid', gridTemplateColumns: '90px 1fr 50px', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                <div style={{ fontSize: 11, color: C.sub, fontFamily: 'JetBrains Mono, monospace' }}>{label}</div>
                <svg width="100%" height="36" viewBox="0 0 200 36" preserveAspectRatio="none">
                  <polyline fill="none" stroke={i===0?C.accent:i===3?C.warn:C.sub} strokeWidth="1.5"
                    points={Array.from({length: 50}).map((_,k)=>`${k*4},${18+Math.sin(k*0.4+i)*8+(i===3?Math.sin(k*1.2)*3:0)}`).join(' ')}/>
                </svg>
                <span style={{ fontSize: 11, color: C.text, fontFamily: 'JetBrains Mono, monospace', textAlign: 'right' }}>
                  {[t.power.toFixed(2), t.wind, t.gearTemp.toFixed(0), t.vib.toFixed(1)][i]}
                </span>
              </div>
            ))}
          </Card>
          {/* Subsystems */}
          <Card C={C}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>{tr('Subsystem health', '子系統健康')}</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
              {[
                { k: tr('Generator','發電機'), s: 92 },
                { k: tr('Gearbox','齒輪箱'), s: 78 },
                { k: tr('Pitch','變槳'), s: 88 },
                { k: tr('Yaw','偏航'), s: 95 },
                { k: tr('Tower','塔筒'), s: 90 },
                { k: tr('Blades','葉片'), s: 84 },
                { k: tr('Converter','變頻器'), s: 91 },
                { k: tr('Cooling','冷卻'), s: 87 },
              ].map(s => (
                <div key={s.k}>
                  <div style={{ fontSize: 12, color: C.sub, marginBottom: 6 }}>{s.k}</div>
                  <div style={{ height: 6, borderRadius: 3, background: C.bg, overflow: 'hidden' }}>
                    <div style={{ width: `${s.s}%`, height: '100%', background: s.s > 85 ? C.ok : s.s > 75 ? (C.isDark ? '#FFB347' : '#B8A053') : C.warn, borderRadius: 3 }}></div>
                  </div>
                  <div style={{ fontSize: 11, color: C.text, marginTop: 4, fontFamily: 'JetBrains Mono, monospace' }}>{s.s}%</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
        <div>
          <Card C={C} style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>{tr('Active alarms', '即時告警')}</div>
            <div style={{ fontSize: 13, color: C.sub, lineHeight: 1.6 }}>{tr('No active alarms.', '目前無告警。')}</div>
          </Card>
          <Card C={C} style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>{tr('Recent events', '最近事件')}</div>
            {[
              { t: '08:42', en: 'Wind ramp +3 m/s', zh: '風速上升 +3 m/s', tag: 'wind' },
              { t: '07:15', en: 'Yaw realigned −1.2°', zh: '偏航修正 −1.2°', tag: 'yaw' },
              { t: '06:00', en: 'Synchronized', zh: '併網成功', tag: 'state' },
              { t: '05:45', en: 'Startup begin', zh: '啟動開始', tag: 'state' },
            ].map(e => (
              <div key={e.t} style={{ display: 'flex', gap: 10, padding: '8px 0', borderBottom: `1px solid ${C.border}`, fontSize: 12 }}>
                <span style={{ color: C.sub, fontFamily: 'JetBrains Mono, monospace' }}>{e.t}</span>
                <span style={{ flex: 1 }}>{tr(e.en, e.zh)}</span>
                <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: C.accentSoft, color: C.accent }}>{e.tag}</span>
              </div>
            ))}
          </Card>
          <Card C={C}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>{tr('Operator control', '操作控制')}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <Btn C={C}>{tr('▶ Start', '▶ 啟動')}</Btn>
              <Btn C={C}>{tr('■ Normal stop', '■ 正常停機')}</Btn>
              <Btn C={C}>{tr('⚠ Emergency stop', '⚠ 緊急停機')}</Btn>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};

const Maintenance = ({ C, D, tr }) => {
  const amber = C.isDark ? '#FFB347' : '#B8A053';
  const amberSoft = C.isDark ? 'rgba(255,179,71,0.16)' : '#FAF3E0';
  const stColor = (s) => s === 'IN_PROGRESS' ? amber : s === 'COMPLETED' ? C.ok : s === 'OPEN' ? C.accent : C.sub;
  const stBg = (s) => s === 'IN_PROGRESS' ? amberSoft : s === 'COMPLETED' ? C.okSoft : s === 'OPEN' ? C.accentSoft : C.bg;
  const prColor = (p) => p === 'HIGH' ? C.warn : p === 'MED' ? amber : C.sub;
  return (
    <div>
      <PageHeader C={C}
        title={tr('Maintenance Hub', '維護中心')}
        sub={tr(D.workOrders.filter(w=>w.status!=='COMPLETED').length + ' active work orders · 4 technicians on duty', D.workOrders.filter(w=>w.status!=='COMPLETED').length + ' 張未結工單・4 位技師在崗')}
        actions={<><Btn C={C}>{tr('Filter', '篩選')}</Btn><Btn C={C} primary>+ {tr('New work order', '新工單')}</Btn></>}
      />
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
        <Card C={C} padding={0}>
          <div style={{ padding: '14px 18px', borderBottom: `1px solid ${C.border}`, fontSize: 14, fontWeight: 600 }}>
            {tr('Work orders', '工單列表')}
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: C.bg }}>
                {[tr('ID','編號'), tr('Turbine','風機'), tr('Issue','問題'), tr('Tech','技師'), tr('Priority','優先'), tr('Status','狀態'), 'SLA'].map(h=>(
                  <th key={h} style={{ textAlign: 'left', padding: '10px 14px', fontSize: 11, color: C.sub, fontWeight: 500, letterSpacing: 0.5, textTransform: 'uppercase' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {D.workOrders.map(w => (
                <tr key={w.id} style={{ borderBottom: `1px solid ${C.border}` }}>
                  <td style={{ padding: '12px 14px', fontFamily: 'JetBrains Mono, monospace', color: C.sub }}>{w.id.slice(-6)}</td>
                  <td style={{ padding: '12px 14px', fontWeight: 600 }}>{w.tid}</td>
                  <td style={{ padding: '12px 14px' }}>{tr(w.issue_en, w.issue_zh)}</td>
                  <td style={{ padding: '12px 14px', color: C.sub }}>{tr(w.techEn, w.tech)}</td>
                  <td style={{ padding: '12px 14px' }}>
                    <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, color: prColor(w.priority), background: prColor(w.priority) + '20', fontWeight: 600 }}>{w.priority}</span>
                  </td>
                  <td style={{ padding: '12px 14px' }}>
                    <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 999, color: stColor(w.status), background: stBg(w.status), fontWeight: 600 }}>{w.status}</span>
                  </td>
                  <td style={{ padding: '12px 14px', fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: C.sub }}>{w.sla}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <div>
          <Card C={C} style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>{tr('Technicians', '技師排班')}</div>
            {D.technicians.map(t => (
              <div key={t.name} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 0', borderBottom: `1px solid ${C.border}` }}>
                <div style={{ width: 36, height: 36, borderRadius: '50%', background: C.isDark ? `linear-gradient(135deg, ${C.accent}, #1A8E5C)` : 'linear-gradient(135deg, #C8D5BD, #5C7A60)', display: 'grid', placeItems: 'center', color: C.isDark ? '#0A0F0E' : '#FFF', fontWeight: 600, fontSize: 13 }}>
                  {tr(t.nameEn, t.name).charAt(0)}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{tr(t.nameEn, t.name)}</div>
                  <div style={{ fontSize: 11, color: C.sub }}>{t.skill}</div>
                </div>
                <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 999,
                  background: t.status === 'ON_DUTY' ? C.okSoft : t.status === 'DISPATCHED' ? C.accentSoft : C.bg,
                  color: t.status === 'ON_DUTY' ? C.ok : t.status === 'DISPATCHED' ? C.accent : C.sub,
                  fontWeight: 600
                }}>{t.status === 'ON_DUTY' ? tr('ON DUTY','在崗') : t.status === 'DISPATCHED' ? tr('DISPATCHED','派遣中') : tr('OFF DUTY','下班')}</span>
              </div>
            ))}
          </Card>
          <Card C={C}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>{tr('Calendar (this week)', '本週行程')}</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 4 }}>
              {['一','二','三','四','五','六','日'].map((d,i) => (
                <div key={d} style={{ fontSize: 10, color: C.sub, textAlign: 'center' }}>{d}</div>
              ))}
              {Array.from({length: 7}).map((_,i) => (
                <div key={i} style={{
                  aspectRatio: '1', borderRadius: 8,
                  background: i === 1 ? C.warnSoft : i === 3 ? C.accentSoft : (C.isDark ? 'rgba(255,255,255,0.04)' : C.bg),
                  border: i === 1 ? `1px solid ${C.warn}` : 'none',
                  display: 'grid', placeItems: 'center', fontSize: 12, fontWeight: 600,
                  color: i === 1 ? C.warn : C.text
                }}>{4+i}</div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};

const Cost = ({ C, D, tr }) => {
  return (
    <div>
      <PageHeader C={C}
        title={tr('Cost Model', '成本模型')}
        sub={tr('LCOE · NPV · Monte Carlo · 20-year forecast', '均化成本・淨現值・蒙地卡羅・20 年預測')}
        actions={<><Btn C={C}>{tr('Dataset: Changhua', '資料集：彰化')}</Btn><Btn C={C} primary>{tr('Run scenario', '執行情境')}</Btn></>}
      />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 16 }}>
        {D.cost.metrics.map((m,i) => (
          <Card C={C} key={i}>
            <div style={{ fontSize: 11, color: C.sub, textTransform: 'uppercase', letterSpacing: 1 }}>{tr(m.label_en, m.label_zh)}</div>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: 6 }}>
              <span style={{ fontFamily: '"DM Serif Display", serif', fontSize: 28, fontWeight: 400, color: i===1 ? C.accent : C.text }}>{m.val}</span>
              {m.delta && <span style={{ fontSize: 12, color: m.delta.startsWith('+') ? C.ok : m.delta.startsWith('−') ? C.accent : C.sub }}>{m.delta}</span>}
            </div>
          </Card>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
        <Card C={C}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>{tr('20-year revenue forecast', '20 年營收預測')}</div>
            <div style={{ fontSize: 12, color: C.sub }}>P10 · P50 · P90</div>
          </div>
          <BigChart C={C} kind="forecast"/>
        </Card>
        <Card C={C}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>{tr('Monte Carlo · 5,000 sims', '蒙地卡羅　5,000 次')}</div>
          {[
            { k: 'P10', v: D.cost.monteCarlo.p10, c: C.ok },
            { k: 'P50', v: D.cost.monteCarlo.p50, c: C.accent },
            { k: 'P90', v: D.cost.monteCarlo.p90, c: C.warn },
          ].map(r => (
            <div key={r.k} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '12px 0', borderBottom: `1px solid ${C.border}` }}>
              <span style={{ fontWeight: 600, color: r.c }}>{r.k}</span>
              <span style={{ fontFamily: '"DM Serif Display", serif', fontSize: 22 }}>{r.v}<span style={{ fontSize: 12, color: C.sub }}> ¢/kWh</span></span>
            </div>
          ))}
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 12, fontSize: 12, color: C.sub }}>
            <span>σ (std dev)</span>
            <span style={{ fontFamily: 'JetBrains Mono, monospace' }}>{D.cost.monteCarlo.sigma}</span>
          </div>
        </Card>
      </div>
    </div>
  );
};

const History = ({ C, D, tr }) => (
  <div>
    <PageHeader C={C}
      title={tr('History', '歷史資料')}
      sub={tr('Search SCADA tags · marked events · CSV export', '搜尋 SCADA 標籤・事件標記・CSV 匯出')}
      actions={<><Btn C={C}>{tr('CSV', '匯出 CSV')}</Btn><Btn C={C} primary>{tr('Compare', '比較')}</Btn></>}
    />
    <Card C={C} style={{ marginBottom: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {[
          { l: tr('Turbine','風機'), v: 'WT002' },
          { l: tr('Range','時間範圍'), v: '2026-05-01 → 05-07' },
          { l: tr('Tags','標籤'), v: 'WTUR_TotPwrAt + 3 more' },
          { l: tr('Events','事件'), v: 'Faults, Grid, Wind' },
        ].map(f => (
          <div key={f.l}>
            <div style={{ fontSize: 11, color: C.sub, marginBottom: 4 }}>{f.l}</div>
            <div style={{ padding: '8px 12px', background: C.bg, borderRadius: 8, fontSize: 13 }}>{f.v}</div>
          </div>
        ))}
      </div>
    </Card>
    <Card C={C} style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>{tr('Power output, with events', '功率輸出　含事件標記')}</div>
      <BigChart C={C} kind="events"/>
    </Card>
    <Card C={C}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>{tr('Event log', '事件紀錄')}</div>
      {[
        { t: '05/06 09:14:22', tag: 'FAULT', en: 'Gearbox overheat — phase: developing', zh: '齒輪箱過熱　階段：發展中', sev: C.warn },
        { t: '05/06 08:42:11', tag: 'WIND', en: 'Wind ramp +3.2 m/s in 60s', zh: '風速急升 +3.2 m/s（60 秒）', sev: C.accent },
        { t: '05/06 06:00:04', tag: 'STATE', en: 'WT002 synchronized to grid', zh: 'WT002 併網成功', sev: C.ok },
        { t: '05/06 05:45:18', tag: 'STATE', en: 'WT002 startup begin', zh: 'WT002 啟動開始', sev: C.sub },
        { t: '05/05 22:08:56', tag: 'OFFLINE', en: 'WT012 communications lost', zh: 'WT012 通訊離線', sev: C.warn },
      ].map(e => (
        <div key={e.t} style={{ display: 'grid', gridTemplateColumns: '160px 80px 1fr', alignItems: 'center', gap: 14, padding: '10px 0', borderBottom: `1px solid ${C.border}`, fontSize: 13 }}>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: C.sub }}>{e.t}</span>
          <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 4, background: e.sev + '20', color: e.sev, fontWeight: 600, textAlign: 'center', letterSpacing: 0.5 }}>{e.tag}</span>
          <span>{tr(e.en, e.zh)}</span>
        </div>
      ))}
    </Card>
  </div>
);

// ── Charts ──
const BigChart = ({ C, kind = 'power' }) => {
  const W = 800, H = 200;
  const points = Array.from({length: 80}).map((_,i) => ({
    x: i * (W/79),
    y: H/2 + Math.sin(i*0.2)*30 + Math.sin(i*0.5)*15 + (i > 40 && i < 50 ? -25 : 0)
  }));
  const path = points.map((p,i) => `${i===0?'M':'L'}${p.x},${p.y}`).join(' ');
  const area = path + ` L${W},${H} L0,${H} Z`;
  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={`bgrad-${kind}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={C.accent} stopOpacity="0.25"/>
          <stop offset="100%" stopColor={C.accent} stopOpacity="0"/>
        </linearGradient>
      </defs>
      {[0, 50, 100, 150].map(y => (
        <line key={y} x1="0" x2={W} y1={y+25} y2={y+25} stroke={C.border} strokeWidth="0.5"/>
      ))}
      <path d={area} fill={`url(#bgrad-${kind})`}/>
      <path d={path} stroke={C.accent} strokeWidth="2" fill="none"/>
      {kind === 'events' && [
        { x: 200, c: C.warn },
        { x: 380, c: C.accent },
        { x: 560, c: C.ok },
      ].map(e => (
        <g key={e.x}>
          <line x1={e.x} x2={e.x} y1="10" y2={H-10} stroke={e.c} strokeWidth="1" strokeDasharray="3,3" opacity="0.7"/>
          <circle cx={e.x} cy="20" r="4" fill={e.c}/>
        </g>
      ))}
    </svg>
  );
};

// ── Icons ──
const Logo = ({ color = '#1F2D24' }) => (
  <svg width="18" height="18" viewBox="0 0 24 24"><circle cx="12" cy="12" r="2.5" fill={color}/><ellipse cx="12" cy="6" rx="1.6" ry="5" fill={color}/><ellipse cx="12" cy="6" rx="1.6" ry="5" fill={color} transform="rotate(120 12 12)"/><ellipse cx="12" cy="6" rx="1.6" ry="5" fill={color} transform="rotate(240 12 12)"/></svg>
);
const NavIcon = ({ id, color }) => {
  const m = {
    overview: <g stroke={color} strokeWidth="1.6" fill="none"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></g>,
    turbine: <g stroke={color} strokeWidth="1.6" fill="none"><circle cx="12" cy="9" r="2"/><path d="M12 11v10M12 9V3M12 9l5-3M12 9l-5-3"/></g>,
    maintenance: <g stroke={color} strokeWidth="1.6" fill="none" strokeLinecap="round"><path d="M14 4l-3 3 5 5 3-3a3.5 3.5 0 1 0-5-5z"/><path d="M11 7L4 14l3 3 7-7"/></g>,
    cost: <g stroke={color} strokeWidth="1.6" fill="none" strokeLinecap="round"><path d="M12 4v16M8 8h6a2 2 0 1 1 0 4H10a2 2 0 1 0 0 4h7"/></g>,
    history: <g stroke={color} strokeWidth="1.6" fill="none" strokeLinecap="round"><circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/></g>,
  };
  return <svg width="18" height="18" viewBox="0 0 24 24">{m[id]}</svg>;
};

window.VA = VA;
