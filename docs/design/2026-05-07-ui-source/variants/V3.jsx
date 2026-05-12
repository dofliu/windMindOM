// Variant 3: Garden of Wind - bright meadow, illustrated, playful + friendly

const V3 = ({ lang: initialLang = 'zh' }) => {
  const { useState } = React;
  const [lang, setLang] = useState(initialLang);
  const C = window.WMOM_CONTENT;
  const tr = (en, zh) => lang === 'zh' ? zh : en;

  return (
    <div data-screen-label="V3 Garden of Wind" style={{
      background: '#FBFAF4',
      color: '#2A3A2D',
      fontFamily: 'Manrope, system-ui, sans-serif',
      minHeight: '100%',
      width: '100%'
    }}>
      {/* NAV - pill nav */}
      <nav style={{ padding: '24px 40px', display: 'flex', justifyContent: 'center' }}>
        <div style={{
          background: '#FFFFFF',
          borderRadius: 999,
          padding: '8px 8px 8px 20px',
          display: 'flex', alignItems: 'center', gap: 24,
          boxShadow: '0 4px 20px rgba(42,58,45,0.06)',
          border: '1px solid rgba(42,58,45,0.06)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Sprout />
            <span style={{ fontWeight: 700, fontSize: 16 }}>digiWind</span>
          </div>
          <div style={{ display: 'flex', gap: 22, fontSize: 14 }}>
            {C.nav.map(n => (
              <a key={n.id} href={`#${n.id}`} style={{ color: '#2A3A2D', textDecoration: 'none', opacity: 0.75 }}>
                {tr(n.en, n.zh)}
              </a>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
              style={{ background: '#F2EFE2', border: 'none', borderRadius: 999, padding: '6px 12px', fontSize: 12, cursor: 'pointer', color: '#2A3A2D' }}>
              {lang === 'zh' ? 'EN' : '中文'}
            </button>
            <button style={{ background: '#2A3A2D', color: '#FBFAF4', border: 'none', borderRadius: 999, padding: '8px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
              {tr(C.cta.en, C.cta.zh)}
            </button>
          </div>
        </div>
      </nav>

      {/* HERO - illustrated landscape */}
      <section style={{ padding: '40px 40px 0', textAlign: 'center', position: 'relative', overflow: 'hidden' }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 14px', background: '#FFF1E5', color: '#C97B5A', borderRadius: 999, fontSize: 13, marginBottom: 28 }}>
          <span>🌱</span>
          <span>{tr('For wind farm operators in Asia', '專為亞太風場營運商打造')}</span>
        </div>
        <h1 style={{
          fontFamily: '"DM Serif Display", serif',
          fontSize: 96, lineHeight: 0.95, fontWeight: 400,
          letterSpacing: -3, margin: 0,
          maxWidth: 1100, marginInline: 'auto', textWrap: 'balance',
          color: '#1F3A2E'
        }}>
          {lang === 'zh' ? (
            <>讓您的風場，<br/>像花園一樣<em style={{ fontStyle: 'italic', color: '#5C8A5F' }}>好好照顧</em>。</>
          ) : (
            <>Tend your wind farm<br/>like a <em style={{ fontStyle: 'italic', color: '#5C8A5F' }}>garden</em>.</>
          )}
        </h1>
        <p style={{ fontSize: 19, color: '#5A6A5C', marginTop: 28, maxWidth: 620, marginInline: 'auto', textWrap: 'pretty', lineHeight: 1.55 }}>
          {tr(
            'A friendly digital twin platform that shows you what every turbine is feeling — wind, heat, vibration, fatigue — so you can decide what to do, calmly.',
            '一個友善的數位雙生平台，告訴您每一座風機的「感受」——風、熱、振動、疲勞——讓您從容地做決定。'
          )}
        </p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 36 }}>
          <button style={{ background: '#2A3A2D', color: '#FBFAF4', border: 'none', borderRadius: 999, padding: '14px 28px', fontSize: 15, fontWeight: 600, cursor: 'pointer' }}>
            {tr(C.cta.en, C.cta.zh)} →
          </button>
          <button style={{ background: 'transparent', color: '#2A3A2D', border: '1px solid rgba(42,58,45,0.2)', borderRadius: 999, padding: '14px 28px', fontSize: 15, cursor: 'pointer' }}>
            ▶ {tr(C.ctaSecondary.en, C.ctaSecondary.zh)}
          </button>
        </div>

        {/* Illustrated landscape */}
        <div style={{ position: 'relative', height: 280, marginTop: 60 }}>
          <Landscape />
        </div>
      </section>

      {/* STATS - rounded pills */}
      <section style={{ padding: '60px 40px', background: '#F2EFE2' }}>
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <div style={{ fontSize: 13, color: '#7A8A7C', letterSpacing: 2, textTransform: 'uppercase', fontWeight: 600 }}>
            {tr('In the soil', '紮實基礎')}
          </div>
          <h2 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 40, margin: '8px 0 0', letterSpacing: -1, fontWeight: 400 }}>
            {tr('Built on real, measurable substance.', '每一個數字，都是扎實的工程。')}
          </h2>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 18, maxWidth: 1100, marginInline: 'auto' }}>
          {C.stats.map((s, i) => (
            <div key={i} style={{
              background: '#FBFAF4',
              borderRadius: 24,
              padding: '28px 32px',
              display: 'flex', alignItems: 'center', gap: 20,
              boxShadow: '0 2px 8px rgba(42,58,45,0.04)',
              border: '1px solid rgba(42,58,45,0.06)'
            }}>
              <div style={{
                width: 64, height: 64,
                borderRadius: '50%',
                background: ['#E8F0DC', '#FFE9D5', '#DEE9DC', '#F4E5D0', '#E8F0DC', '#FFE9D5'][i],
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0
              }}>
                <span style={{ fontFamily: '"DM Serif Display", serif', fontSize: 22, color: '#2A3A2D' }}>{s.num}</span>
              </div>
              <div style={{ fontSize: 14, color: '#5A6A5C', textWrap: 'pretty' }}>{tr(s.label_en, s.label_zh)}</div>
            </div>
          ))}
        </div>
      </section>

      {/* DEMO */}
      <section id="demo" style={{ padding: '90px 40px' }}>
        <div style={{ textAlign: 'center', marginBottom: 48 }}>
          <div style={{ fontSize: 13, color: '#5C8A5F', letterSpacing: 2, textTransform: 'uppercase', fontWeight: 600 }}>
            {tr('Try it', '試試看')}
          </div>
          <h2 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 56, margin: '12px 0 0', letterSpacing: -1.5, fontWeight: 400, textWrap: 'balance' }}>
            {tr('A real turbine, in your browser.', '一座真的風機，就在您的瀏覽器。')}
          </h2>
          <p style={{ fontSize: 17, color: '#5A6A5C', marginTop: 16, maxWidth: 620, marginInline: 'auto', textWrap: 'pretty', lineHeight: 1.55 }}>
            {tr(
              'No video, no marketing fluff. Inject a fault below and watch the physics respond.',
              '不是影片、沒有花招——點下面的故障，看物理模型即時反應。'
            )}
          </p>
        </div>
        <div style={{ maxWidth: 720, marginInline: 'auto' }}>
          <window.MiniDashboard theme="cream" lang={lang} accent="#5C8A5F" />
        </div>
      </section>

      {/* FEATURES - alternating cards with illustrations */}
      <section id="features" style={{ padding: '60px 40px 100px', background: '#F4F0E1' }}>
        <div style={{ textAlign: 'center', marginBottom: 56 }}>
          <div style={{ fontSize: 13, color: '#5C8A5F', letterSpacing: 2, textTransform: 'uppercase', fontWeight: 600 }}>
            {tr('What grows here', '在這裡長出的')}
          </div>
          <h2 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 52, margin: '12px 0 0', letterSpacing: -1.5, fontWeight: 400, textWrap: 'balance' }}>
            {tr('Six promises we kept.', '六個我們做到的承諾。')}
          </h2>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20, maxWidth: 1180, marginInline: 'auto' }}>
          {C.features.map((f, i) => {
            const palettes = [
              { bg: '#E8F0DC', tag: '#5C8A5F' },
              { bg: '#FFE9D5', tag: '#C97B5A' },
              { bg: '#DEE9DC', tag: '#5C8A8A' },
              { bg: '#F4E5D0', tag: '#A88560' },
              { bg: '#E8F0DC', tag: '#5C8A5F' },
              { bg: '#FFE9D5', tag: '#C97B5A' }
            ][i];
            return (
              <div key={i} style={{
                background: '#FBFAF4',
                borderRadius: 24,
                padding: 28,
                border: '1px solid rgba(42,58,45,0.06)'
              }}>
                <div style={{
                  width: 56, height: 56, borderRadius: 16,
                  background: palettes.bg,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  marginBottom: 18
                }}>
                  <FeatureIllo3 icon={f.icon} color={palettes.tag} />
                </div>
                <div style={{ fontSize: 11, color: palettes.tag, letterSpacing: 1.5, textTransform: 'uppercase', fontWeight: 700 }}>
                  Nº 0{i + 1}
                </div>
                <h3 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 26, margin: '6px 0 12px', fontWeight: 400, lineHeight: 1.15, color: '#1F3A2E' }}>
                  {tr(f.title_en, f.title_zh)}
                </h3>
                <p style={{ fontSize: 14.5, lineHeight: 1.55, color: '#5A6A5C', margin: 0, textWrap: 'pretty' }}>
                  {tr(f.body_en, f.body_zh)}
                </p>
              </div>
            );
          })}
        </div>
      </section>

      {/* PHYSICS — illustrated chips */}
      <section id="physics" style={{ padding: '90px 40px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 60, maxWidth: 1180, marginInline: 'auto' }}>
          <div>
            <div style={{ fontSize: 13, color: '#5C8A5F', letterSpacing: 2, textTransform: 'uppercase', fontWeight: 600 }}>
              {tr('Roots', '根扎得深')}
            </div>
            <h2 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 52, margin: '12px 0 0', letterSpacing: -1.5, fontWeight: 400, lineHeight: 1.05, textWrap: 'balance' }}>
              {tr(C.physics.title_en, C.physics.title_zh)}
            </h2>
            <p style={{ fontSize: 16, color: '#5A6A5C', marginTop: 18, lineHeight: 1.6, textWrap: 'pretty' }}>
              {tr(
                'Eight academic-grade physics models, each named after the paper it came from. We did the homework so you don\'t have to.',
                '八項學術級物理模型，每一個都以原始論文命名。我們把功課做完，您只要享用結果。'
              )}
            </p>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignContent: 'flex-start' }}>
            {C.physics.items.map((p, i) => (
              <div key={i} style={{
                padding: '12px 18px',
                background: ['#E8F0DC', '#FFE9D5', '#DEE9DC', '#F4E5D0'][i % 4],
                borderRadius: 999,
                fontSize: 14, fontWeight: 500,
                color: '#1F3A2E',
                border: '1px solid rgba(42,58,45,0.05)'
              }}>
                {tr(p.en, p.zh)}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* TESTIMONIAL - editorial quote with illustration */}
      <section style={{ padding: '90px 40px', background: '#1F3A2E', color: '#FBFAF4', position: 'relative', overflow: 'hidden' }}>
        <div style={{ maxWidth: 900, marginInline: 'auto', textAlign: 'center', position: 'relative', zIndex: 1 }}>
          <div style={{ fontSize: 80, color: '#7BB07A', fontFamily: '"DM Serif Display", serif', lineHeight: 0.5, marginBottom: 8 }}>"</div>
          <p style={{ fontFamily: '"DM Serif Display", serif', fontSize: 40, lineHeight: 1.3, margin: 0, fontStyle: 'italic', textWrap: 'balance', fontWeight: 400 }}>
            {tr(C.testimonial.quote_en, C.testimonial.quote_zh)}
          </p>
          <div style={{ marginTop: 32 }}>
            <div style={{ fontSize: 15, fontWeight: 600 }}>— {tr(C.testimonial.author_en, C.testimonial.author_zh)}</div>
            <div style={{ fontSize: 13, color: '#9CAE92', marginTop: 4 }}>{tr(C.testimonial.org_en, C.testimonial.org_zh)}</div>
          </div>
        </div>
        {/* Decorative leaves */}
        <Leaf3 style={{ position: 'absolute', top: 40, left: 60, width: 80, opacity: 0.4 }}/>
        <Leaf3 style={{ position: 'absolute', bottom: 40, right: 60, width: 100, opacity: 0.3, transform: 'rotate(180deg)' }}/>
      </section>

      {/* API */}
      <section id="api" style={{ padding: '90px 40px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 50, maxWidth: 1180, marginInline: 'auto', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 13, color: '#5C8A5F', letterSpacing: 2, textTransform: 'uppercase', fontWeight: 600 }}>
              {tr('Easy to plant', '輕鬆種植')}
            </div>
            <h2 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 48, margin: '12px 0 0', letterSpacing: -1.5, fontWeight: 400, lineHeight: 1.05 }}>
              {tr(C.api.title_en, C.api.title_zh)}
            </h2>
            <p style={{ fontSize: 16, color: '#5A6A5C', marginTop: 16, lineHeight: 1.6, textWrap: 'pretty' }}>
              {tr(C.api.body_en, C.api.body_zh)}
            </p>
            <div style={{ display: 'flex', gap: 8, marginTop: 24, flexWrap: 'wrap' }}>
              {['REST', 'WebSocket', 'Modbus TCP', 'OPC DA'].map(p => (
                <span key={p} style={{ padding: '6px 14px', background: '#E8F0DC', borderRadius: 999, fontSize: 13, fontFamily: 'JetBrains Mono, monospace', color: '#2A3A2D' }}>{p}</span>
              ))}
            </div>
          </div>
          <pre style={{
            background: '#1F3A2E', color: '#C8D5BD',
            padding: 28, borderRadius: 20, fontSize: 14,
            fontFamily: 'JetBrains Mono, monospace', lineHeight: 1.7,
            margin: 0, whiteSpace: 'pre-wrap'
          }}>{C.api.snippet}</pre>
        </div>
      </section>

      {/* FINAL CTA - sunny garden */}
      <section id="contact" style={{ padding: '120px 40px', textAlign: 'center', background: 'linear-gradient(180deg, #FBFAF4 0%, #F2EFE2 100%)', position: 'relative', overflow: 'hidden' }}>
        {/* Decorative sun */}
        <div style={{
          position: 'absolute', top: 60, right: '50%', marginRight: -180,
          width: 220, height: 220, borderRadius: '50%',
          background: 'radial-gradient(circle, #FFE9D5 0%, transparent 70%)',
          filter: 'blur(20px)', pointerEvents: 'none'
        }}></div>
        <div style={{ position: 'relative' }}>
          <h2 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 84, lineHeight: 0.95, letterSpacing: -2.5, margin: 0, fontWeight: 400, textWrap: 'balance', color: '#1F3A2E' }}>
            {tr(C.finalCta.title_en, C.finalCta.title_zh)}
          </h2>
          <p style={{ fontSize: 18, color: '#5A6A5C', marginTop: 20, textWrap: 'balance' }}>
            {tr(C.finalCta.body_en, C.finalCta.body_zh)}
          </p>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 36 }}>
            <button style={{ background: '#2A3A2D', color: '#FBFAF4', border: 'none', borderRadius: 999, padding: '18px 36px', fontSize: 16, fontWeight: 600, cursor: 'pointer' }}>
              {tr(C.cta.en, C.cta.zh)} →
            </button>
            <button style={{ background: 'transparent', color: '#2A3A2D', border: '1px solid rgba(42,58,45,0.2)', borderRadius: 999, padding: '18px 28px', fontSize: 16, cursor: 'pointer' }}>
              {tr('Talk to a human', '與真人聊聊')}
            </button>
          </div>
        </div>
      </section>

      <footer style={{ padding: '40px 40px 60px', borderTop: '1px solid rgba(42,58,45,0.08)', display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#7A8A7C', maxWidth: 1180, marginInline: 'auto' }}>
        <span>© 2026 digiWindTurbine</span>
        <span>{tr('Grown patiently in Taiwan.', '在台灣，慢慢長大。')}</span>
      </footer>
    </div>
  );
};

const Sprout = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
    <path d="M12 22V12M12 12C12 8 8 6 4 7C5 11 8 13 12 12ZM12 12C12 8 16 6 20 7C19 11 16 13 12 12Z" stroke="#2A3A2D" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const Leaf3 = ({ style }) => (
  <svg viewBox="0 0 100 100" style={style}>
    <path d="M50 10 Q80 30 80 60 Q80 85 50 90 Q20 85 20 60 Q20 30 50 10Z" fill="#7BB07A"/>
    <path d="M50 10 L50 90" stroke="#1F3A2E" strokeWidth="1" opacity="0.3"/>
  </svg>
);

const Landscape = () => (
  <svg viewBox="0 0 1200 280" preserveAspectRatio="xMidYMax slice" style={{ width: '100%', height: '100%' }}>
    {/* Hills - back */}
    <path d="M0,180 Q200,120 400,150 T800,140 T1200,160 L1200,280 L0,280 Z" fill="#DEE9DC"/>
    {/* Hills - mid */}
    <path d="M0,210 Q300,160 600,180 T1200,190 L1200,280 L0,280 Z" fill="#C8D8C0"/>
    {/* Ground */}
    <path d="M0,240 L1200,240 L1200,280 L0,280Z" fill="#A8C2A4"/>

    {/* Sun */}
    <circle cx="950" cy="80" r="40" fill="#FFE9D5"/>
    <circle cx="950" cy="80" r="28" fill="#FFD4A8"/>

    {/* Turbines */}
    {[200, 420, 640, 880].map((x, i) => {
      const scale = 1 - i * 0.08;
      const y = 240 - 90 * scale;
      const speeds = [6, 8, 7, 9];
      return (
        <g key={i} transform={`translate(${x},${y}) scale(${scale})`}>
          {/* Tower */}
          <path d="M-3,0 L3,0 L5,90 L-5,90 Z" fill="#FBFAF4"/>
          {/* Hub */}
          <circle cx="0" cy="0" r="6" fill="#FBFAF4"/>
          {/* Blades - rotating */}
          <g style={{ transformOrigin: '0 0', animation: `spin${i} ${speeds[i]}s linear infinite` }}>
            <ellipse cx="0" cy="-30" rx="3" ry="32" fill="#FBFAF4"/>
            <ellipse cx="0" cy="-30" rx="3" ry="32" fill="#FBFAF4" transform="rotate(120)"/>
            <ellipse cx="0" cy="-30" rx="3" ry="32" fill="#FBFAF4" transform="rotate(240)"/>
          </g>
        </g>
      );
    })}

    {/* Foreground grass tufts */}
    {[100, 250, 400, 580, 720, 850, 1000, 1130].map((x, i) => (
      <g key={i} transform={`translate(${x},255)`}>
        <path d="M-3,5 Q0,-5 3,5" stroke="#5C8A5F" strokeWidth="1.5" fill="none"/>
        <path d="M-6,5 Q-3,-3 0,5" stroke="#5C8A5F" strokeWidth="1.5" fill="none"/>
        <path d="M0,5 Q3,-3 6,5" stroke="#5C8A5F" strokeWidth="1.5" fill="none"/>
      </g>
    ))}

    <style>{`
      @keyframes spin0 { to { transform: rotate(360deg); } }
      @keyframes spin1 { to { transform: rotate(360deg); } }
      @keyframes spin2 { to { transform: rotate(360deg); } }
      @keyframes spin3 { to { transform: rotate(360deg); } }
    `}</style>
  </svg>
);

const FeatureIllo3 = ({ icon, color }) => {
  const map = {
    wind: <path d="M4 12h14a3 3 0 1 0-3-3M4 18h18a3 3 0 1 1-3 3M4 15h12" stroke={color} strokeWidth="2" strokeLinecap="round" fill="none"/>,
    fault: <path d="M14 4l-9 12h7l-2 8 9-12h-7l2-8z" stroke={color} strokeWidth="2" strokeLinejoin="round" fill="none"/>,
    grid: <g stroke={color} strokeWidth="2" fill="none"><circle cx="14" cy="8" r="4"/><path d="M14 12v8M10 16h8M8 22h12"/></g>,
    history: <g stroke={color} strokeWidth="2" fill="none" strokeLinecap="round"><circle cx="14" cy="14" r="9"/><path d="M14 8v6l4 2"/></g>,
    api: <g stroke={color} strokeWidth="2" fill="none" strokeLinecap="round"><path d="M9 9L4 14l5 5M19 9l5 5-5 5M16 5L12 23"/></g>,
    twin: <g stroke={color} strokeWidth="2" fill="none"><circle cx="10" cy="14" r="6"/><circle cx="18" cy="14" r="6"/></g>
  };
  return <svg width="28" height="28" viewBox="0 0 28 28">{map[icon]}</svg>;
};

window.V3 = V3;
