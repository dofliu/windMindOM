import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import { useTheme } from '../theme/ThemeProvider';
import { rightAxisTags } from '../utils/chartAxes';
import { authFetch } from '../services/authClient';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8100';

// Commonly used tag groups
const TAG_PRESETS: Record<string, { label_en: string; label_zh: string; tags: string[] }> = {
  power: {
    label_en: 'Power & Wind',
    label_zh: '功率與風速',
    tags: ['WTUR_TotPwrAt', 'WMET_WSpeedNac'],
  },
  temperature: {
    label_en: 'Temperatures',
    label_zh: '溫度監控',
    tags: ['WGEN_GnStaTmp1', 'WGEN_GnBrgTmp1', 'WGEN_GnAirTmp1', 'WCNV_CnvCabinTmp', 'WGDC_TrfCoreTmp'],
  },
  vibration: {
    label_en: 'Vibration & RPM',
    label_zh: '振動與轉速',
    tags: ['WNAC_VibMsNacXDir', 'WNAC_VibMsNacYDir', 'WROT_RotSpd'],
  },
  pitch: {
    label_en: 'Blade Angles',
    label_zh: '葉片角度',
    tags: ['WROT_PtAngValBl1', 'WROT_PtAngValBl2', 'WROT_PtAngValBl3'],
  },
  converter: {
    label_en: 'Converter',
    label_zh: '變頻器',
    tags: ['WCNV_CnvGnPwr', 'WCNV_CnvGnFrq', 'WCNV_IGCTWtrTmp', 'WCNV_IGCTWtrPres1'],
  },
  yaw: {
    label_en: 'Yaw System',
    label_zh: '轉向系統',
    tags: ['WYAW_YwVn1AlgnAvg5s', 'WYAW_YwBrkHyPrs', 'WYAW_CabWup'],
  },
  fatigue: {
    label_en: 'Load & Fatigue',
    label_zh: '載荷與疲勞',
    tags: ['WLOD_TwrFaMom', 'WLOD_BldFlapMom', 'WLOD_DelTwrFa', 'WLOD_DelBldFlap'],
  },
};

interface TrendChartPanelProps {
  turbineId: string;  // e.g. "WT001"
  lang?: 'en' | 'zh';
}

const TrendChartPanel: React.FC<TrendChartPanelProps> = ({ turbineId, lang = 'zh' }) => {
  const [activePreset, setActivePreset] = useState('power');
  const [customTags, setCustomTags] = useState('');
  const [chartData, setChartData] = useState<any[]>([]);
  const [activeTags, setActiveTags] = useState<string[]>(TAG_PRESETS.power.tags);
  const [tagLabels, setTagLabels] = useState<Record<string, string>>({});

  // Fetch i18n labels
  useEffect(() => {
    authFetch(`${API_BASE}/api/i18n/tags?lang=${lang}`)
      .then(r => r.json()).then(setTagLabels).catch(() => {});
  }, [lang]);

  // Fetch trend data
  const fetchTrend = useCallback(() => {
    if (!activeTags.length) return;
    const tagsParam = activeTags.join(',');
    authFetch(`${API_BASE}/api/turbines/${turbineId}/trend?tags=${tagsParam}&limit=120`)
      .then(r => r.json())
      .then(res => {
        if (res.data) {
          setChartData(res.data.map((d: any) => ({
            ...d,
            _time: d.timestamp ? new Date(d.timestamp).getTime() : 0,
          })));
        }
      })
      .catch(() => {});
  }, [turbineId, activeTags]);

  useEffect(() => {
    fetchTrend();
    const iv = setInterval(fetchTrend, 2000);
    return () => clearInterval(iv);
  }, [fetchTrend]);

  const handlePreset = (presetId: string) => {
    setActivePreset(presetId);
    setActiveTags(TAG_PRESETS[presetId].tags);
  };

  const handleCustomApply = () => {
    const tags = customTags.split(',').map(t => t.trim()).filter(Boolean);
    if (tags.length) {
      setActivePreset('');
      setActiveTags(tags);
    }
  };

  const getLabel = (tag: string) => tagLabels[tag] || tag;
  const { C } = useTheme();
  const lineColors = [C.accent, C.amber, C.ok, C.warn, C.info, C.chartState, C.accent, C.amber];

  // 雙 Y 軸：把量級差一個數量級以上的 tag 分到右軸（功率 vs 風速才能同時看清）。
  const rightTags = useMemo(() => rightAxisTags(activeTags, chartData), [activeTags, chartData]);
  const hasRightAxis = rightTags.size > 0;
  const colorFor = (tag: string) => lineColors[activeTags.indexOf(tag) % lineColors.length];
  const leftOnly = activeTags.filter(t => !rightTags.has(t));
  const rightOnly = activeTags.filter(t => rightTags.has(t));
  // 單一條線的軸就用該線顏色標示（一眼看出哪軸配哪線）；多條則用中性色。
  const leftAxisColor = leftOnly.length === 1 ? colorFor(leftOnly[0]) : C.sub;
  const rightAxisColor = rightOnly.length === 1 ? colorFor(rightOnly[0]) : C.sub;

  return (
    <div>
      <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 10 }}>
        {lang === 'zh' ? '即時趨勢圖' : 'Real-time trend'}
      </div>

      {/* Preset buttons */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
        {Object.entries(TAG_PRESETS).map(([id, preset]) => {
          const active = activePreset === id;
          return (
            <button
              key={id}
              onClick={() => handlePreset(id)}
              aria-pressed={active}
              style={{
                padding: '4px 10px',
                fontSize: 12,
                borderRadius: 6,
                border: `1px solid ${active ? C.accent : C.border}`,
                background: active ? C.accentSoft : C.panelMuted,
                color: active ? C.accent : C.sub,
                cursor: 'pointer',
                fontFamily: 'inherit',
                fontWeight: active ? 600 : 500,
              }}
            >
              {lang === 'zh' ? preset.label_zh : preset.label_en}
            </button>
          );
        })}
      </div>

      {/* Custom tag input */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
        <input
          type="text"
          value={customTags}
          onChange={e => setCustomTags(e.target.value)}
          placeholder={lang === 'zh' ? '自訂標籤（逗號分隔）' : 'Custom tags (comma-separated)'}
          style={{
            flex: 1,
            background: C.panel,
            border: `1px solid ${C.border}`,
            borderRadius: 8,
            padding: '6px 10px',
            fontSize: 12,
            color: C.text,
            fontFamily: 'JetBrains Mono, monospace',
            outline: 'none',
          }}
        />
        <button
          onClick={handleCustomApply}
          style={{
            background: C.panel,
            border: `1px solid ${C.border}`,
            color: C.text,
            borderRadius: 8,
            padding: '6px 12px',
            fontSize: 12,
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
        >
          {lang === 'zh' ? '套用' : 'Apply'}
        </button>
      </div>

      {/* Chart */}
      <div style={{ background: C.panelMuted, borderRadius: 8, padding: 8 }}>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
            <XAxis
              dataKey="_time"
              tickFormatter={t =>
                t ? new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''
              }
              stroke={C.sub}
              fontSize={10}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              yAxisId="left"
              stroke={leftAxisColor}
              fontSize={10}
              axisLine={false}
              tickLine={false}
              width={44}
            />
            {hasRightAxis && (
              <YAxis
                yAxisId="right"
                orientation="right"
                stroke={rightAxisColor}
                fontSize={10}
                axisLine={false}
                tickLine={false}
                width={44}
              />
            )}
            <Tooltip
              contentStyle={{
                backgroundColor: C.panel,
                border: `1px solid ${C.border}`,
                borderRadius: 8,
                color: C.text,
              }}
              labelFormatter={t => (t ? new Date(t).toLocaleTimeString() : '')}
              formatter={(value: number, name: string) => [
                value != null ? value.toFixed(2) : '—',
                getLabel(name),
              ]}
            />
            <Legend formatter={value => getLabel(value as string)} wrapperStyle={{ fontSize: 11, color: C.sub }} />
            {activeTags.map((tag, i) => (
              <Line
                key={tag}
                yAxisId={rightTags.has(tag) ? 'right' : 'left'}
                type="monotone"
                dataKey={tag}
                stroke={lineColors[i % lineColors.length]}
                strokeWidth={1.6}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div data-testid="trend-footer" style={{ marginTop: 6, fontSize: 11, color: C.faint }}>
        {lang === 'zh' ? '顯示標籤' : 'Showing'}: {activeTags.map(t => getLabel(t)).join(' · ')}
      </div>
    </div>
  );
};

export default TrendChartPanel;
