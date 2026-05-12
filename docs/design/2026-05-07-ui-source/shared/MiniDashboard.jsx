// Shared interactive mini-dashboard preview for the landing pages.
// Simulates a live wind turbine readout with selectable fault injection.
// Self-contained: provide a `theme` prop ('light'|'dark'|'cream') and `lang`.

const MiniDashboard = ({ theme = 'cream', lang = 'zh', accent = '#1F3A2E' }) => {
  const { useState, useEffect, useRef } = React;
  const [turbineId, setTurbineId] = useState(2);
  const [fault, setFault] = useState(null); // null | 'bearing' | 'gearbox' | 'pitch'
  const [t, setT] = useState(0);
  const [history, setHistory] = useState([]);
  const rafRef = useRef();

  // Animate
  useEffect(() => {
    let last = performance.now();
    const tick = (now) => {
      const dt = (now - last) / 1000;
      last = now;
      setT(prev => prev + dt);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  // Compute simulated values
  const baseWind = 8.4 + Math.sin(t * 0.6) * 1.6 + Math.sin(t * 2.1) * 0.4;
  const wind = Math.max(2, baseWind);
  const faultPenalty = fault === 'bearing' ? 0.92 : fault === 'gearbox' ? 0.85 : fault === 'pitch' ? 0.78 : 1;
  const power = Math.max(0, Math.min(2.0, 0.0042 * Math.pow(wind, 3))) * faultPenalty;
  const rpm = 6 + (wind - 4) * 1.1 * faultPenalty;
  const tempBase = 62 + (power * 8);
  const temp = tempBase + (fault === 'gearbox' ? 22 + Math.sin(t * 0.4) * 4 : fault === 'bearing' ? 8 : 0);
  const vib = 1.2 + Math.abs(Math.sin(t * 3.1)) * 0.4 +
              (fault === 'bearing' ? 2.6 + Math.abs(Math.sin(t * 7)) * 1.2 : 0) +
              (fault === 'gearbox' ? 0.8 : 0);

  // Track history for sparkline
  useEffect(() => {
    setHistory(h => {
      const next = [...h, { t, p: power }];
      return next.slice(-60);
    });
  }, [Math.floor(t * 4)]); // ~4hz sampling

  const isDark = theme === 'dark';
  const palette = isDark
    ? { bg: '#0F1A14', panel: '#1A2A22', text: '#E8EDE5', subtle: '#7C8B82', accent, border: '#22332A' }
    : theme === 'light'
    ? { bg: '#FFFFFF', panel: '#F7F8F5', text: '#1F3A2E', subtle: '#6E7A6E', accent, border: '#E5E7E0' }
    : { bg: '#F7F4ED', panel: '#FFFFFF', text: '#1F3A2E', subtle: '#7C8B82', accent, border: '#E8E2D5' };

  const tr = (en, zh) => lang === 'zh' ? zh : en;

  // Sparkline path
  const sparkW = 280, sparkH = 60;
  const maxP = 2.0;
  const points = history.map((d, i) => {
    const x = (i / Math.max(1, history.length - 1)) * sparkW;
    const y = sparkH - (d.p / maxP) * sparkH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  // Spinning rotor angle
  const rotorAngle = (t * 360 * (rpm / 60)) % 360;

  return (
    <div style={{
      background: palette.bg,
      color: palette.text,
      borderRadius: 16,
      border: `1px solid ${palette.border}`,
      overflow: 'hidden',
      fontFamily: 'Manrope, system-ui, sans-serif',
      boxShadow: isDark ? '0 30px 80px -20px rgba(0,0,0,0.5)' : '0 24px 60px -20px rgba(31,58,46,0.18)'
    }}>
      {/* Header */}
      <div style={{
        padding: '14px 18px',
        borderBottom: `1px solid ${palette.border}`,
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        background: palette.panel
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#7BB07A', boxShadow: '0 0 0 4px rgba(123,176,122,0.18)' }}></span>
          <span style={{ fontWeight: 600, fontSize: 13, letterSpacing: 0.3 }}>
            {tr('LIVE · Turbine WT00' + turbineId, '即時 · 風機 WT00' + turbineId)}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {[1, 2, 3, 4].map(id => (
            <button key={id}
              onClick={() => setTurbineId(id)}
              style={{
                width: 26, height: 22, borderRadius: 6,
                border: `1px solid ${turbineId === id ? palette.accent : palette.border}`,
                background: turbineId === id ? palette.accent : 'transparent',
                color: turbineId === id ? '#fff' : palette.subtle,
                fontSize: 11, cursor: 'pointer', fontFamily: 'JetBrains Mono, monospace'
              }}>
              {id}
            </button>
          ))}
        </div>
      </div>

      {/* Main grid */}
      <div style={{ padding: 18, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        {/* Power - hero metric */}
        <div style={{ gridColumn: '1 / -1', padding: '14px 16px', background: palette.panel, borderRadius: 12, border: `1px solid ${palette.border}` }}>
          <div style={{ fontSize: 11, color: palette.subtle, letterSpacing: 1, textTransform: 'uppercase' }}>
            {tr('Power Output', '即時功率')}
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 4 }}>
            <span style={{ fontFamily: '"DM Serif Display", serif', fontSize: 44, lineHeight: 1, color: palette.accent, fontWeight: 400 }}>
              {power.toFixed(2)}
            </span>
            <span style={{ fontSize: 14, color: palette.subtle }}>MW</span>
            <span style={{ marginLeft: 'auto', fontSize: 11, color: palette.subtle, fontFamily: 'JetBrains Mono, monospace' }}>
              {((power / 2.0) * 100).toFixed(0)}% {tr('of rated', '額定功率')}
            </span>
          </div>
          <svg width="100%" height={sparkH} viewBox={`0 0 ${sparkW} ${sparkH}`} preserveAspectRatio="none" style={{ marginTop: 8 }}>
            <defs>
              <linearGradient id={`sparkGrad-${theme}`} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor={palette.accent} stopOpacity="0.35" />
                <stop offset="100%" stopColor={palette.accent} stopOpacity="0" />
              </linearGradient>
            </defs>
            {history.length > 1 && (
              <>
                <polygon
                  points={`0,${sparkH} ${points} ${sparkW},${sparkH}`}
                  fill={`url(#sparkGrad-${theme})`}
                />
                <polyline points={points} fill="none" stroke={palette.accent} strokeWidth="1.6" strokeLinejoin="round" />
              </>
            )}
          </svg>
        </div>

        {/* Wind speed */}
        <Metric palette={palette} label={tr('Wind Speed', '風速')} value={wind.toFixed(1)} unit="m/s" sub={
          <RotorIcon angle={rotorAngle} color={palette.accent} />
        }/>

        {/* RPM */}
        <Metric palette={palette} label="RPM" value={rpm.toFixed(1)} unit={tr('rpm', '轉/分')} sub={null}/>

        {/* Temperature */}
        <Metric palette={palette} label={tr('Gearbox Temp', '齒輪箱溫度')} value={temp.toFixed(0)} unit="°C"
          alert={temp > 85}
          sub={null}/>

        {/* Vibration */}
        <Metric palette={palette} label={tr('Vibration', '振動')} value={vib.toFixed(2)} unit="mm/s"
          alert={vib > 2.5}
          sub={null}/>

        {/* Fault injection controls */}
        <div style={{ gridColumn: '1 / -1', padding: '12px 14px', background: palette.panel, borderRadius: 12, border: `1px solid ${palette.border}` }}>
          <div style={{ fontSize: 11, color: palette.subtle, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 8 }}>
            {tr('Try injecting a fault →', '試試注入故障 →')}
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {[
              { id: null, en: 'Normal', zh: '正常' },
              { id: 'bearing', en: 'Bearing wear', zh: '軸承磨耗' },
              { id: 'gearbox', en: 'Gearbox overheat', zh: '齒輪箱過熱' },
              { id: 'pitch', en: 'Pitch motor', zh: '變槳故障' }
            ].map(opt => (
              <button key={String(opt.id)}
                onClick={() => setFault(opt.id)}
                style={{
                  padding: '6px 12px', borderRadius: 999, fontSize: 12,
                  border: `1px solid ${fault === opt.id ? palette.accent : palette.border}`,
                  background: fault === opt.id ? palette.accent : 'transparent',
                  color: fault === opt.id ? '#fff' : palette.text,
                  cursor: 'pointer', fontFamily: 'inherit', fontWeight: 500,
                  transition: 'all 0.15s'
                }}>
                {tr(opt.en, opt.zh)}
              </button>
            ))}
          </div>
          {fault && (
            <div style={{ marginTop: 10, fontSize: 12, color: '#C97B5A', display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#C97B5A' }}></span>
              {tr(
                'Watch temperature & vibration drift — fault propagates through the physics model.',
                '看溫度與振動如何漂移——故障正透過物理模型擴散。'
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const Metric = ({ palette, label, value, unit, sub, alert }) => (
  <div style={{
    padding: '12px 14px',
    background: palette.panel,
    borderRadius: 12,
    border: `1px solid ${alert ? '#C97B5A' : palette.border}`,
    transition: 'border-color 0.3s'
  }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
      <div style={{ fontSize: 11, color: palette.subtle, letterSpacing: 0.6, textTransform: 'uppercase' }}>{label}</div>
      {sub}
    </div>
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginTop: 4 }}>
      <span style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 22, fontWeight: 500,
        color: alert ? '#C97B5A' : palette.text,
      }}>{value}</span>
      <span style={{ fontSize: 11, color: palette.subtle }}>{unit}</span>
    </div>
  </div>
);

const RotorIcon = ({ angle, color }) => (
  <svg width="22" height="22" viewBox="0 0 22 22" style={{ transform: `rotate(${angle}deg)`, transition: 'transform 0.05s linear' }}>
    <circle cx="11" cy="11" r="2" fill={color} />
    {[0, 120, 240].map(a => (
      <ellipse key={a} cx="11" cy="4" rx="1" ry="6"
        fill={color} opacity="0.7"
        transform={`rotate(${a} 11 11)`} />
    ))}
  </svg>
);

window.MiniDashboard = MiniDashboard;
