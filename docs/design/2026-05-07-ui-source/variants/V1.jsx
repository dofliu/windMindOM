// Variant 1: Organic Editorial - magazine-style, large serif, warm cream + moss

const V1 = ({ lang: initialLang = 'zh' }) => {
  const { useState } = React;
  const [lang, setLang] = useState(initialLang);
  const C = window.WMOM_CONTENT;
  const tr = (en, zh) => lang === 'zh' ? zh : en;

  return (
    <div data-screen-label="V1 Organic Editorial" style={{
      background: '#F4EFE3',
      color: '#1F3A2E',
      fontFamily: 'Manrope, system-ui, sans-serif',
      minHeight: '100%',
      width: '100%'
    }}>
      {/* Subtle paper texture overlay */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        backgroundImage: 'radial-gradient(circle at 20% 30%, rgba(156,174,146,0.12) 0%, transparent 50%), radial-gradient(circle at 80% 70%, rgba(201,123,90,0.08) 0%, transparent 50%)',
        zIndex: 0
      }}></div>

      <div style={{ position: 'relative', zIndex: 1 }}>
        {/* NAV */}
        <nav style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '28px 56px', borderBottom: '1px solid rgba(31,58,46,0.1)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Leaf size={24} color="#1F3A2E" />
            <span style={{ fontFamily: '"DM Serif Display", serif', fontSize: 22, letterSpacing: -0.3 }}>digiWind</span>
          </div>
          <div style={{ display: 'flex', gap: 32, fontSize: 14 }}>
            {C.nav.map(n => (
              <a key={n.id} href={`#${n.id}`} style={{ color: '#1F3A2E', textDecoration: 'none', opacity: 0.7 }}>
                {tr(n.en, n.zh)}
              </a>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
            <button onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
              style={{ background: 'transparent', border: '1px solid rgba(31,58,46,0.2)', borderRadius: 999, padding: '6px 14px', fontSize: 12, cursor: 'pointer', color: '#1F3A2E' }}>
              {lang === 'zh' ? 'EN' : '中文'}
            </button>
            <button style={{
              background: '#1F3A2E', color: '#F4EFE3', border: 'none', borderRadius: 999,
              padding: '10px 20px', fontSize: 13, fontWeight: 500, cursor: 'pointer'
            }}>{tr(C.cta.en, C.cta.zh)}</button>
          </div>
        </nav>

        {/* HERO - magazine cover style */}
        <section style={{ padding: '80px 56px 60px', display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 60, alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 12, letterSpacing: 3, textTransform: 'uppercase', color: '#7C8B82', marginBottom: 20 }}>
              {tr('Issue Nº 01 · Wind Operations Atlas', '第 01 期 · 風電營運圖鑑')}
            </div>
            <h1 style={{
              fontFamily: '"DM Serif Display", serif',
              fontSize: 88, lineHeight: 0.95, fontWeight: 400, margin: 0,
              letterSpacing: -2,
              color: '#1F3A2E'
            }}>
              {lang === 'zh' ? (
                <>會呼吸的<br/><em style={{ fontStyle: 'italic', color: '#5C7A60' }}>風機數位</em><br/>雙生。</>
              ) : (
                <>A living<br/><em style={{ fontStyle: 'italic', color: '#5C7A60' }}>digital twin</em><br/>for the wind.</>
              )}
            </h1>
            <p style={{ fontSize: 19, lineHeight: 1.55, color: '#3A4F42', maxWidth: 480, marginTop: 28, textWrap: 'pretty' }}>
              {tr(C.subTagline.en, C.subTagline.zh)}
            </p>
            <div style={{ display: 'flex', gap: 14, marginTop: 36 }}>
              <button style={{ background: '#1F3A2E', color: '#F4EFE3', border: 'none', borderRadius: 999, padding: '14px 28px', fontSize: 15, fontWeight: 500, cursor: 'pointer' }}>
                {tr(C.cta.en, C.cta.zh)} →
              </button>
              <button style={{ background: 'transparent', color: '#1F3A2E', border: '1px solid rgba(31,58,46,0.25)', borderRadius: 999, padding: '14px 28px', fontSize: 15, cursor: 'pointer' }}>
                {tr(C.ctaSecondary.en, C.ctaSecondary.zh)}
              </button>
            </div>
          </div>

          {/* Hero illustration - stylized turbine made of soft shapes */}
          <div style={{ position: 'relative', aspectRatio: '4/5' }}>
            <div style={{
              position: 'absolute', inset: 0,
              background: 'linear-gradient(160deg, #C8D5BD 0%, #9CAE92 60%, #5C7A60 100%)',
              borderRadius: '50% 50% 50% 50% / 60% 60% 40% 40%',
              boxShadow: '0 40px 80px -30px rgba(31,58,46,0.4)'
            }}></div>
            <svg viewBox="0 0 400 500" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
              <line x1="200" y1="180" x2="200" y2="450" stroke="#F4EFE3" strokeWidth="6" strokeLinecap="round" opacity="0.85"/>
              <circle cx="200" cy="180" r="14" fill="#F4EFE3"/>
              <g style={{ transformOrigin: '200px 180px', animation: 'spin 8s linear infinite' }}>
                <ellipse cx="200" cy="100" rx="6" ry="80" fill="#F4EFE3" opacity="0.95"/>
                <ellipse cx="200" cy="260" rx="6" ry="80" fill="#F4EFE3" opacity="0.95" transform="rotate(120 200 180)"/>
                <ellipse cx="200" cy="260" rx="6" ry="80" fill="#F4EFE3" opacity="0.95" transform="rotate(240 200 180)"/>
              </g>
              <circle cx="80" cy="80" r="40" fill="#C97B5A" opacity="0.4"/>
              <circle cx="340" cy="380" r="24" fill="#F4EFE3" opacity="0.5"/>
            </svg>
            <div style={{ position: 'absolute', bottom: 20, left: 20, right: 20, color: '#F4EFE3', fontSize: 11, letterSpacing: 1.5, textTransform: 'uppercase', display: 'flex', justifyContent: 'space-between' }}>
              <span>{tr('Field, March', '三月　現場')}</span>
              <span>WT001 — 2.0 MW</span>
            </div>
          </div>
        </section>

        {/* STATS - editorial figures */}
        <section style={{ padding: '60px 56px', borderTop: '1px solid rgba(31,58,46,0.12)', borderBottom: '1px solid rgba(31,58,46,0.12)' }}>
          <div style={{ fontSize: 12, letterSpacing: 3, textTransform: 'uppercase', color: '#7C8B82', marginBottom: 32 }}>
            {tr('By the numbers', '數據說話')}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 48 }}>
            {C.stats.map((s, i) => (
              <div key={i} style={{ paddingRight: 24, borderLeft: i % 3 !== 0 ? 'none' : 'none' }}>
                <div style={{ fontFamily: '"DM Serif Display", serif', fontSize: 64, lineHeight: 1, color: '#1F3A2E' }}>{s.num}</div>
                <div style={{ fontSize: 14, color: '#5C7A60', marginTop: 8, textWrap: 'pretty' }}>{tr(s.label_en, s.label_zh)}</div>
              </div>
            ))}
          </div>
        </section>

        {/* DEMO */}
        <section id="demo" style={{ padding: '90px 56px', background: '#EDE7D8' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 60, alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 12, letterSpacing: 3, textTransform: 'uppercase', color: '#7C8B82', marginBottom: 16 }}>
                {tr('Live Preview', '即時預覽')}
              </div>
              <h2 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 52, lineHeight: 1.05, margin: 0, letterSpacing: -1 }}>
                {tr('Touch a fault. Feel the model.', '點一個故障，感受模型。')}
              </h2>
              <p style={{ fontSize: 17, lineHeight: 1.6, color: '#3A4F42', marginTop: 20, maxWidth: 440, textWrap: 'pretty' }}>
                {tr(
                  'This is not a video — it is the real physics model running in your browser. Inject a fault and watch the temperature, vibration, and power respond exactly as a physical drivetrain would.',
                  '這不是影片，這是真的物理模型在您瀏覽器中運行。注入一個故障，看溫度、振動、功率如何如同實體驅動鏈一般回應。'
                )}
              </p>
            </div>
            <window.MiniDashboard theme="cream" lang={lang} accent="#1F3A2E" />
          </div>
        </section>

        {/* PHYSICS */}
        <section id="physics" style={{ padding: '90px 56px', display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: 60 }}>
          <div>
            <div style={{ fontSize: 12, letterSpacing: 3, textTransform: 'uppercase', color: '#7C8B82', marginBottom: 16 }}>
              {tr('The science', '科學基礎')}
            </div>
            <h2 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 48, lineHeight: 1.05, margin: 0, letterSpacing: -1 }}>
              {tr(C.physics.title_en, C.physics.title_zh)}
            </h2>
            <p style={{ fontSize: 16, color: '#3A4F42', marginTop: 20, lineHeight: 1.6, textWrap: 'pretty' }}>
              {tr(
                'Most digital twins polish the surface. We modeled what is underneath — every paper, every standard.',
                '多數數位雙生只把表面磨亮，我們把底下的物理一條一條建出來——每一篇論文、每一條規範。'
              )}
            </p>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px 24px' }}>
            {C.physics.items.map((p, i) => (
              <div key={i} style={{
                padding: '18px 20px',
                background: '#FFFCF5',
                borderRadius: 12,
                border: '1px solid rgba(31,58,46,0.08)',
                fontSize: 14, lineHeight: 1.4, color: '#1F3A2E',
                display: 'flex', gap: 12, alignItems: 'flex-start'
              }}>
                <span style={{ color: '#C97B5A', fontFamily: 'JetBrains Mono, monospace', fontSize: 11, paddingTop: 2 }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span style={{ textWrap: 'pretty' }}>{tr(p.en, p.zh)}</span>
              </div>
            ))}
          </div>
        </section>

        {/* FEATURES */}
        <section id="features" style={{ padding: '90px 56px', background: '#1F3A2E', color: '#F4EFE3' }}>
          <div style={{ fontSize: 12, letterSpacing: 3, textTransform: 'uppercase', color: '#9CAE92', marginBottom: 16 }}>
            {tr('What it does', '產品特色')}
          </div>
          <h2 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 56, lineHeight: 1, margin: 0, letterSpacing: -1.5, maxWidth: 820 }}>
            {tr('Six things your operators will notice on day one.', '六件事，您的營運團隊第一天就會發現。')}
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 32, marginTop: 60 }}>
            {C.features.map((f, i) => (
              <div key={i} style={{ paddingTop: 24, borderTop: '1px solid rgba(244,239,227,0.2)' }}>
                <div style={{ fontFamily: '"DM Serif Display", serif', fontSize: 28, marginBottom: 6 }}>0{i + 1}</div>
                <h3 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 26, margin: '8px 0 12px', fontWeight: 400 }}>
                  {tr(f.title_en, f.title_zh)}
                </h3>
                <p style={{ fontSize: 15, lineHeight: 1.55, color: '#C8D5BD', textWrap: 'pretty' }}>
                  {tr(f.body_en, f.body_zh)}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* TESTIMONIAL */}
        <section style={{ padding: '120px 56px', textAlign: 'center' }}>
          <div style={{ maxWidth: 880, margin: '0 auto' }}>
            <div style={{ fontFamily: '"DM Serif Display", serif', fontSize: 44, lineHeight: 1.25, color: '#1F3A2E', fontStyle: 'italic', textWrap: 'balance' }}>
              "{tr(C.testimonial.quote_en, C.testimonial.quote_zh)}"
            </div>
            <div style={{ marginTop: 32, fontSize: 14, color: '#5C7A60' }}>
              <div style={{ fontWeight: 600 }}>— {tr(C.testimonial.author_en, C.testimonial.author_zh)}</div>
              <div style={{ marginTop: 4, opacity: 0.8 }}>{tr(C.testimonial.org_en, C.testimonial.org_zh)}</div>
            </div>
          </div>
        </section>

        {/* API */}
        <section id="api" style={{ padding: '80px 56px', background: '#EDE7D8', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 60, alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 12, letterSpacing: 3, textTransform: 'uppercase', color: '#7C8B82', marginBottom: 12 }}>
              {tr('Integration', '整合')}
            </div>
            <h2 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 44, lineHeight: 1.05, margin: 0, letterSpacing: -1 }}>
              {tr(C.api.title_en, C.api.title_zh)}
            </h2>
            <p style={{ fontSize: 16, lineHeight: 1.6, color: '#3A4F42', marginTop: 18, textWrap: 'pretty' }}>
              {tr(C.api.body_en, C.api.body_zh)}
            </p>
          </div>
          <pre style={{
            background: '#1F3A2E', color: '#C8D5BD',
            padding: 28, borderRadius: 14, fontSize: 14,
            fontFamily: 'JetBrains Mono, monospace', lineHeight: 1.7,
            margin: 0, whiteSpace: 'pre-wrap'
          }}>{C.api.snippet}</pre>
        </section>

        {/* FINAL CTA */}
        <section id="contact" style={{ padding: '120px 56px', textAlign: 'center', background: '#F4EFE3' }}>
          <h2 style={{ fontFamily: '"DM Serif Display", serif', fontSize: 80, lineHeight: 1, letterSpacing: -2.5, margin: 0, textWrap: 'balance' }}>
            {tr(C.finalCta.title_en, C.finalCta.title_zh)}
          </h2>
          <p style={{ fontSize: 18, color: '#5C7A60', marginTop: 24, textWrap: 'balance' }}>
            {tr(C.finalCta.body_en, C.finalCta.body_zh)}
          </p>
          <button style={{ marginTop: 36, background: '#1F3A2E', color: '#F4EFE3', border: 'none', borderRadius: 999, padding: '18px 36px', fontSize: 16, fontWeight: 500, cursor: 'pointer' }}>
            {tr(C.cta.en, C.cta.zh)} →
          </button>
        </section>

        <footer style={{ padding: '32px 56px', borderTop: '1px solid rgba(31,58,46,0.1)', display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#7C8B82' }}>
          <span>© 2026 digiWindTurbine</span>
          <span>{tr('Made with care for the wind.', '為風而做。')}</span>
        </footer>
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
};

const Leaf = ({ size = 24, color = '#1F3A2E' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <path d="M3 21C3 12 9 4 21 3C20 15 12 21 3 21Z" fill={color}/>
    <path d="M3 21L12 12" stroke="#F4EFE3" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);

window.V1 = V1;
