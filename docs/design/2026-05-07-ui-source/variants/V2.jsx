// Variant 2: Living Dashboard - dark forest, modern SaaS, dashboard-led

const V2 = ({ lang: initialLang = 'zh' }) => {
  const { useState } = React;
  const [lang, setLang] = useState(initialLang);
  const C = window.WMOM_CONTENT;
  const tr = (en, zh) => lang === 'zh' ? zh : en;

  const accent = '#7BB07A';

  return (
    <div data-screen-label="V2 Living Dashboard" style={{
      background: '#0E1812',
      color: '#E8EDE5',
      fontFamily: 'Manrope, system-ui, sans-serif',
      minHeight: '100%',
      width: '100%',
      position: 'relative',
      overflow: 'hidden'
    }}>
      {/* Ambient glow */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        background: 'radial-gradient(ellipse 80% 60% at 70% 0%, rgba(123,176,122,0.18) 0%, transparent 60%), radial-gradient(ellipse 60% 50% at 10% 100%, rgba(80,128,90,0.15) 0%, transparent 60%)',
        zIndex: 0
      }}></div>

      <div style={{ position: 'relative', zIndex: 1 }}>
        {/* NAV */}
        <nav style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '20px 48px', borderBottom: '1px solid rgba(232,237,229,0.08)',
          backdropFilter: 'blur(8px)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 36 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Logo2 />
              <span style={{ fontSize: 16, fontWeight: 700, letterSpacing: -0.3 }}>digiWind</span>
              <span style={{ fontSize: 11, color: accent, padding: '2px 8px', border: `1px solid ${accent}`, borderRadius: 4, marginLeft: 4 }}>v2.4</span>
            </div>
            <div style={{ display: 'flex', gap: 28, fontSize: 14 }}>
              {C.nav.map(n => (
                <a key={n.id} href={`#${n.id}`} style={{ color: '#B8C4B8', textDecoration: 'none' }}>
                  {tr(n.en, n.zh)}
                </a>
              ))}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <button onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
              style={{ background: 'transparent', border: '1px solid rgba(232,237,229,0.15)', borderRadius: 8, padding: '6px 12px', fontSize: 12, cursor: 'pointer', color: '#B8C4B8' }}>
              {lang === 'zh' ? 'EN' : '中文'}
            </button>
            <button style={{ background: 'transparent', color: '#E8EDE5', border: 'none', padding: '8px 14px', fontSize: 14, cursor: 'pointer' }}>
              {tr('Sign in', '登入')}
            </button>
            <button style={{
              background: accent, color: '#0E1812', border: 'none', borderRadius: 8,
              padding: '10px 18px', fontSize: 13, fontWeight: 600, cursor: 'pointer'
            }}>{tr(C.cta.en, C.cta.zh)}</button>
          </div>
        </nav>

        {/* HERO with embedded live dashboard */}
        <section style={{ padding: '80px 48px 40px', textAlign: 'center', position: 'relative' }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '6px 14px', borderRadius: 999, background: 'rgba(123,176,122,0.1)', border: `1px solid rgba(123,176,122,0.3)`,
            fontSize: 12, color: accent, marginBottom: 28
          }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: accent, boxShadow: `0 0 8px ${accent}` }}></span>
            {tr('Now serving 12 wind farms across Taiwan', '已服務全台 12 座風場')}
          </div>
          <h1 style={{
            fontSize: 72, lineHeight: 1.05, fontWeight: 700, margin: 0, letterSpacing: -2.5,
            maxWidth: 900, marginInline: 'auto', textWrap: 'balance'
          }}>
            {lang === 'zh' ? (
              <>把整個風場，<br/>裝進<span style={{ color: accent }}>一個瀏覽器分頁</span>。</>
            ) : (
              <>Your entire wind farm,<br/>in <span style={{ color: accent }}>one browser tab</span>.</>
            )}
          </h1>
          <p style={{ fontSize: 19, color: '#B8C4B8', marginTop: 24, maxWidth: 640, marginInline: 'auto', textWrap: 'pretty', lineHeight: 1.55 }}>
            {tr(
              'Physics-grade digital twin, SCADA-aligned data streams, and a dashboard your operators will actually open every morning.',
              '物理級數位雙生、SCADA 對齊資料流、以及您的營運團隊每天早上會主動打開的儀表板。'
            )}
          </p>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 36 }}>
            <button style={{ background: accent, color: '#0E1812', border: 'none', borderRadius: 10, padding: '14px 26px', fontSize: 15, fontWeight: 600, cursor: 'pointer' }}>
              {tr(C.cta.en, C.cta.zh)} →
            </button>
            <button style={{ background: 'rgba(232,237,229,0.06)', color: '#E8EDE5', border: '1px solid rgba(232,237,229,0.15)', borderRadius: 10, padding: '14px 26px', fontSize: 15, cursor: 'pointer' }}>
              ▶ {tr(C.ctaSecondary.en, C.ctaSecondary.zh)}
            </button>
          </div>

          {/* Embedded dashboard preview */}
          <div style={{ marginTop: 70, maxWidth: 1080, marginInline: 'auto', position: 'relative' }}>
            <div style={{
              position: 'absolute', inset: -40, pointerEvents: 'none',
              background: `radial-gradient(ellipse 70% 50% at 50% 50%, rgba(123,176,122,0.2), transparent 70%)`,
              filter: 'blur(40px)'
            }}></div>
            <div style={{ position: 'relative', display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 16 }}>
              <FullDashboardMock lang={lang} accent={accent} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <window.MiniDashboard theme="dark" lang={lang} accent={accent} />
              </div>
            </div>
          </div>
        </section>

        {/* STATS strip */}
        <section style={{ padding: '60px 48px', borderTop: '1px solid rgba(232,237,229,0.08)', borderBottom: '1px solid rgba(232,237,229,0.08)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 24 }}>
            {C.stats.map((s, i) => (
              <div key={i} style={{ textAlign: 'center', padding: '0 8px' }}>
                <div style={{ fontSize: 36, fontWeight: 700, color: accent, letterSpacing: -1 }}>{s.num}</div>
                <div style={{ fontSize: 12, color: '#9AA89A', marginTop: 6, textWrap: 'pretty' }}>{tr(s.label_en, s.label_zh)}</div>
              </div>
            ))}
          </div>
        </section>

        {/* FEATURES - bento grid */}
        <section id="features" style={{ padding: '90px 48px' }}>
          <div style={{ textAlign: 'center', marginBottom: 56 }}>
            <div style={{ fontSize: 13, color: accent, letterSpacing: 2, textTransform: 'uppercase', fontWeight: 600 }}>
              {tr('Features', '功能')}
            </div>
            <h2 style={{ fontSize: 48, fontWeight: 700, margin: '12px 0 0', letterSpacing: -1.5, textWrap: 'balance' }}>
              {tr('Built for operators. Loved by engineers.', '為營運打造，工程師愛用。')}
            </h2>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gridAutoRows: '180px', gap: 16 }}>
            {C.features.map((f, i) => {
              const spans = [
                { col: 'span 3', row: 'span 2' }, // wind - large
                { col: 'span 3', row: 'span 1' }, // fault
                { col: 'span 2', row: 'span 1' }, // grid
                { col: 'span 2', row: 'span 2' }, // history - tall
                { col: 'span 2', row: 'span 1' }, // api
                { col: 'span 3', row: 'span 1' }  // twin
              ][i];
              return (
                <div key={i} style={{
                  gridColumn: spans.col, gridRow: spans.row,
                  background: 'rgba(232,237,229,0.03)',
                  border: '1px solid rgba(232,237,229,0.08)',
                  borderRadius: 16,
                  padding: 24,
                  display: 'flex', flexDirection: 'column', gap: 10,
                  position: 'relative', overflow: 'hidden'
                }}>
                  <FeatIcon icon={f.icon} accent={accent} />
                  <h3 style={{ fontSize: 20, fontWeight: 600, margin: 0, color: '#E8EDE5' }}>{tr(f.title_en, f.title_zh)}</h3>
                  <p style={{ fontSize: 14, lineHeight: 1.5, color: '#9AA89A', margin: 0, textWrap: 'pretty' }}>
                    {tr(f.body_en, f.body_zh)}
                  </p>
                </div>
              );
            })}
          </div>
        </section>

        {/* PHYSICS */}
        <section id="physics" style={{ padding: '90px 48px', background: 'rgba(232,237,229,0.02)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.6fr', gap: 60 }}>
            <div style={{ position: 'sticky', top: 80, alignSelf: 'start' }}>
              <div style={{ fontSize: 13, color: accent, letterSpacing: 2, textTransform: 'uppercase', fontWeight: 600 }}>
                {tr('The science', '科學基礎')}
              </div>
              <h2 style={{ fontSize: 44, fontWeight: 700, margin: '12px 0 0', letterSpacing: -1.5, textWrap: 'balance' }}>
                {tr(C.physics.title_en, C.physics.title_zh)}
              </h2>
              <p style={{ fontSize: 16, color: '#9AA89A', marginTop: 18, lineHeight: 1.6, textWrap: 'pretty' }}>
                {tr(
                  'Eight peer-reviewed physics models, faithfully implemented. Not "AI-powered" — just careful engineering.',
                  '八項學術論文等級的物理模型，扎實實作。不是 AI 萬靈丹，而是嚴謹工程。'
                )}
              </p>
            </div>
            <div>
              {C.physics.items.map((p, i) => (
                <div key={i} style={{
                  display: 'grid', gridTemplateColumns: '60px 1fr auto', gap: 16, alignItems: 'center',
                  padding: '20px 0', borderBottom: '1px solid rgba(232,237,229,0.08)'
                }}>
                  <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 13, color: accent }}>
                    {String(i + 1).padStart(2, '0')}.
                  </span>
                  <span style={{ fontSize: 16, color: '#E8EDE5', textWrap: 'pretty' }}>{tr(p.en, p.zh)}</span>
                  <CheckIcon color={accent} />
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* TESTIMONIAL + API split */}
        <section style={{ padding: '90px 48px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 32 }}>
          {/* Testimonial card */}
          <div style={{
            background: 'linear-gradient(160deg, rgba(123,176,122,0.12), rgba(123,176,122,0.02))',
            border: `1px solid rgba(123,176,122,0.2)`,
            borderRadius: 20, padding: 40
          }}>
            <div style={{ fontSize: 60, color: accent, fontFamily: '"DM Serif Display", serif', lineHeight: 0.5, marginBottom: 12 }}>"</div>
            <p style={{ fontSize: 22, lineHeight: 1.45, margin: 0, fontWeight: 500, textWrap: 'pretty' }}>
              {tr(C.testimonial.quote_en, C.testimonial.quote_zh)}
            </p>
            <div style={{ marginTop: 28, display: 'flex', alignItems: 'center', gap: 14 }}>
              <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'linear-gradient(135deg, #C8D5BD, #5C7A60)' }}></div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600 }}>{tr(C.testimonial.author_en, C.testimonial.author_zh)}</div>
                <div style={{ fontSize: 13, color: '#9AA89A' }}>{tr(C.testimonial.org_en, C.testimonial.org_zh)}</div>
              </div>
            </div>
          </div>

          {/* API */}
          <div id="api" style={{
            background: 'rgba(232,237,229,0.03)',
            border: '1px solid rgba(232,237,229,0.08)',
            borderRadius: 20, padding: 40,
            display: 'flex', flexDirection: 'column', justifyContent: 'space-between'
          }}>
            <div>
              <div style={{ fontSize: 13, color: accent, letterSpacing: 2, textTransform: 'uppercase', fontWeight: 600 }}>
                {tr('Integration', '整合')}
              </div>
              <h3 style={{ fontSize: 28, fontWeight: 700, margin: '8px 0 0', textWrap: 'balance' }}>{tr(C.api.title_en, C.api.title_zh)}</h3>
              <p style={{ fontSize: 14, color: '#9AA89A', marginTop: 12, lineHeight: 1.6, textWrap: 'pretty' }}>
                {tr(C.api.body_en, C.api.body_zh)}
              </p>
            </div>
            <pre style={{
              background: '#0A1410', color: '#C8D5BD',
              padding: 18, borderRadius: 10, fontSize: 13,
              fontFamily: 'JetBrains Mono, monospace', lineHeight: 1.7,
              margin: '20px 0 0', whiteSpace: 'pre-wrap',
              border: '1px solid rgba(123,176,122,0.15)'
            }}>{C.api.snippet}</pre>
          </div>
        </section>

        {/* FINAL CTA */}
        <section id="contact" style={{ padding: '120px 48px', textAlign: 'center', position: 'relative' }}>
          <div style={{
            position: 'absolute', inset: '20% 30%', pointerEvents: 'none',
            background: `radial-gradient(ellipse, ${accent}33, transparent 70%)`,
            filter: 'blur(60px)'
          }}></div>
          <div style={{ position: 'relative' }}>
            <h2 style={{ fontSize: 68, fontWeight: 700, letterSpacing: -2.5, margin: 0, textWrap: 'balance' }}>
              {tr(C.finalCta.title_en, C.finalCta.title_zh)}
            </h2>
            <p style={{ fontSize: 18, color: '#9AA89A', marginTop: 18, textWrap: 'balance' }}>
              {tr(C.finalCta.body_en, C.finalCta.body_zh)}
            </p>
            <button style={{ marginTop: 36, background: accent, color: '#0E1812', border: 'none', borderRadius: 12, padding: '18px 36px', fontSize: 16, fontWeight: 700, cursor: 'pointer' }}>
              {tr(C.cta.en, C.cta.zh)} →
            </button>
            <div style={{ marginTop: 16, fontSize: 13, color: '#7C8B7C' }}>
              {tr('No credit card. 30-min walkthrough.', '無需信用卡，30 分鐘 Demo。')}
            </div>
          </div>
        </section>

        <footer style={{ padding: '32px 48px', borderTop: '1px solid rgba(232,237,229,0.08)', display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#7C8B7C' }}>
          <span>© 2026 digiWindTurbine</span>
          <span>{tr('Built in Taiwan, tuned for the wind.', '生於台灣，為風而調。')}</span>
        </footer>
      </div>
    </div>
  );
};

// Logo
const Logo2 = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
    <circle cx="12" cy="12" r="3" fill="#7BB07A"/>
    <ellipse cx="12" cy="5" rx="2" ry="6" fill="#7BB07A" opacity="0.9"/>
    <ellipse cx="12" cy="5" rx="2" ry="6" fill="#7BB07A" opacity="0.9" transform="rotate(120 12 12)"/>
    <ellipse cx="12" cy="5" rx="2" ry="6" fill="#7BB07A" opacity="0.9" transform="rotate(240 12 12)"/>
  </svg>
);

const CheckIcon = ({ color }) => (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <circle cx="9" cy="9" r="9" fill={color} fillOpacity="0.15"/>
    <path d="M5 9l3 3 5-6" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const FeatIcon = ({ icon, accent }) => {
  const stroke = accent;
  const map = {
    wind: <path d="M2 8h13a3 3 0 1 0-3-3M2 14h17a3 3 0 1 1-3 3M2 11h10" stroke={stroke} strokeWidth="1.5" strokeLinecap="round"/>,
    fault: <path d="M12 3l9 16H3l9-16zm0 6v5m0 3v.01" stroke={stroke} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>,
    grid: <g stroke={stroke} strokeWidth="1.5" fill="none"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/></g>,
    history: <g stroke={stroke} strokeWidth="1.5" fill="none" strokeLinecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></g>,
    api: <g stroke={stroke} strokeWidth="1.5" fill="none" strokeLinecap="round"><path d="M8 8L4 12l4 4M16 8l4 4-4 4M14 4L10 20"/></g>,
    twin: <g stroke={stroke} strokeWidth="1.5" fill="none"><circle cx="8" cy="12" r="5"/><circle cx="16" cy="12" r="5"/></g>
  };
  return (
    <div style={{
      width: 40, height: 40, borderRadius: 10,
      background: `${accent}15`, display: 'flex', alignItems: 'center', justifyContent: 'center',
      marginBottom: 4
    }}>
      <svg width="22" height="22" viewBox="0 0 24 24">{map[icon]}</svg>
    </div>
  );
};

// Larger illustrative dashboard mock — turbine farm map view
const FullDashboardMock = ({ lang, accent }) => {
  const tr = (en, zh) => lang === 'zh' ? zh : en;
  return (
    <div style={{
      background: '#0E1812',
      border: '1px solid rgba(232,237,229,0.1)',
      borderRadius: 16,
      overflow: 'hidden',
      boxShadow: '0 30px 80px -20px rgba(0,0,0,0.6)',
      fontFamily: 'Manrope, sans-serif'
    }}>
      {/* Window chrome */}
      <div style={{ display: 'flex', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid rgba(232,237,229,0.08)', gap: 8 }}>
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#FF5F57' }}></span>
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#FEBC2E' }}></span>
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#28C840' }}></span>
        <span style={{ marginLeft: 16, fontSize: 12, color: '#7C8B7C', fontFamily: 'JetBrains Mono, monospace' }}>
          digiwind.app/farm/changhua-coastal
        </span>
      </div>
      <div style={{ padding: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 11, color: '#7C8B7C', letterSpacing: 1.5, textTransform: 'uppercase' }}>
              {tr('Farm Overview', '風場總覽')}
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, marginTop: 2 }}>
              {tr('Changhua Coastal · 48 turbines', '彰化沿海　48 機')}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12, fontSize: 12 }}>
            <Stat2 label={tr('Total', '總和')} val="74.2 MW" accent={accent} />
            <Stat2 label={tr('Online', '上線')} val="46/48" accent={accent} />
            <Stat2 label={tr('Faults', '故障')} val="1" warn />
          </div>
        </div>
        {/* Mini turbine grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: 6 }}>
          {Array.from({ length: 48 }).map((_, i) => {
            const isFault = i === 17;
            const isOff = i === 33 || i === 41;
            const color = isFault ? '#C97B5A' : isOff ? '#3A4A3A' : accent;
            return (
              <div key={i} style={{
                aspectRatio: '1',
                background: isFault ? `${color}25` : 'rgba(232,237,229,0.04)',
                border: `1px solid ${color}40`,
                borderRadius: 6,
                position: 'relative',
                display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
                padding: 4
              }}>
                <span style={{ fontSize: 8, color: '#7C8B7C', fontFamily: 'JetBrains Mono, monospace' }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <div style={{ width: 4, height: 4, borderRadius: '50%', background: color, alignSelf: 'flex-end', boxShadow: isFault ? `0 0 6px ${color}` : 'none' }}></div>
              </div>
            );
          })}
        </div>
        {/* Trend chart placeholder */}
        <div style={{ marginTop: 14, height: 100, position: 'relative', background: 'rgba(232,237,229,0.03)', borderRadius: 8, padding: 10 }}>
          <div style={{ fontSize: 10, color: '#7C8B7C', letterSpacing: 1, textTransform: 'uppercase' }}>
            {tr('Farm Power, last 24h', '風場功率　近 24 小時')}
          </div>
          <svg width="100%" height="70" viewBox="0 0 400 70" preserveAspectRatio="none">
            <defs>
              <linearGradient id="farmGrad" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor={accent} stopOpacity="0.4"/>
                <stop offset="100%" stopColor={accent} stopOpacity="0"/>
              </linearGradient>
            </defs>
            <path d="M0,55 Q40,45 80,30 T160,40 T240,15 T320,25 T400,20 L400,70 L0,70 Z" fill="url(#farmGrad)"/>
            <path d="M0,55 Q40,45 80,30 T160,40 T240,15 T320,25 T400,20" stroke={accent} strokeWidth="1.5" fill="none"/>
          </svg>
        </div>
      </div>
    </div>
  );
};

const Stat2 = ({ label, val, accent, warn }) => (
  <div>
    <div style={{ fontSize: 10, color: '#7C8B7C', letterSpacing: 1, textTransform: 'uppercase' }}>{label}</div>
    <div style={{ fontSize: 14, fontWeight: 600, color: warn ? '#C97B5A' : accent || '#E8EDE5' }}>{val}</div>
  </div>
);

window.V2 = V2;
