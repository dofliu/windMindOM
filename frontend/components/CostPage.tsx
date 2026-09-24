/**
 * CostPage — A · Calm Operator 改版。
 *
 * 版面：
 *   - PageHeader：成本模型 + 「LCOE · NPV · Monte Carlo · 20 年預測」+ Dataset 選擇 / Run scenario
 *   - 6 KPI 卡（3 欄 × 2 列）：Total Cost / LCOE 強調 / NPV / MC P50 / CapEx / Avg Annual
 *   - 主區：4 個原 panel（Forecast / LCOE / Monte Carlo / VarFluct）— 沿用 recharts 但走 theme 顏色
 *
 * **API / hooks 不動**：useCostData 4 endpoints + DatasetMetaBadge 行為一致。
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useCostData } from '../hooks/useCostData';
import { useI18n } from '../hooks/useI18n';
import type { DatasetMeta } from '../services/costService';
import {
  Card,
  Btn,
  PageHeader,
  StatusPill,
  Stat,
  Field,
  Input,
  Select,
} from './ui';
import { useTheme } from '../theme/ThemeProvider';
import { authFetch } from '../services/authClient';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

// ─── formatters ───────────────────────────────────────────────

const fmtMoney = (eur: number): string => {
  if (Math.abs(eur) >= 1e9) return `€${(eur / 1e9).toFixed(2)}B`;
  if (Math.abs(eur) >= 1e6) return `€${(eur / 1e6).toFixed(1)}M`;
  if (Math.abs(eur) >= 1e3) return `€${(eur / 1e3).toFixed(1)}k`;
  return `€${eur.toFixed(2)}`;
};
const fmtPct = (v: number): string => `${(v * 100).toFixed(1)}%`;
const fmtKwh = (v: number): string => `${(v * 100).toFixed(2)} ¢/kWh`;

// ─── DatasetMetaBadge ─────────────────────────────────────────

const DatasetMetaBadge: React.FC<{
  meta: DatasetMeta | null | undefined;
  ui: (en: string, zh: string) => string;
}> = ({ meta, ui }) => {
  if (!meta) return null;
  const labelMap: Record<DatasetMeta['source'], string> = {
    k13_baseline: ui('K13 baseline', 'K13 預設'),
    farm_overlay: ui('Farm overlay', '風場覆寫'),
    registry_derived: ui('Registry-derived', '風場註冊推導'),
    k13_fallback: ui('K13 fallback', 'K13 退回'),
  };
  const toneMap: Record<DatasetMeta['source'], 'muted' | 'accent' | 'amber' | 'warn'> = {
    k13_baseline: 'muted',
    farm_overlay: 'accent',
    registry_derived: 'amber',
    k13_fallback: 'warn',
  };
  return (
    <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
      <StatusPill tone={toneMap[meta.source]} title={`dataset_used = ${meta.dataset_used}`}>
        {labelMap[meta.source]}
        {meta.farm_id ? ` · ${meta.farm_id}` : ''}
      </StatusPill>
      {meta.warning && (
        <span style={{ fontSize: 11, color: '#B8A053' }}>⚠ {meta.warning}</span>
      )}
    </div>
  );
};

// ─── Panel wrapper ────────────────────────────────────────────

const Panel: React.FC<{
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
}> = ({ title, subtitle, children }) => {
  const { C } = useTheme();
  return (
    <Card>
      <div style={{ marginBottom: 14 }}>
        <h3
          style={{
            margin: 0,
            fontSize: 16,
            fontWeight: 600,
            color: C.text,
          }}
        >
          {title}
        </h3>
        {subtitle && (
          <div style={{ fontSize: 12, color: C.sub, marginTop: 4 }}>{subtitle}</div>
        )}
      </div>
      {children}
    </Card>
  );
};

const ErrorBox: React.FC<{ message: string }> = ({ message }) => {
  const { C } = useTheme();
  return (
    <div
      style={{
        marginTop: 12,
        background: C.warnSoft,
        border: `1px solid ${C.warn}`,
        color: C.warn,
        padding: '10px 12px',
        borderRadius: 8,
        fontSize: 13,
      }}
    >
      ⚠ {message}
    </div>
  );
};

// ─── Farm option ──────────────────────────────────────────────

interface FarmOption {
  farm_id: string;
  name: string;
  turbine_count: number;
  rated_kw: number | null;
}

// ─── Forecast panel ───────────────────────────────────────────

const ForecastPanel: React.FC<{
  forecast: ReturnType<typeof useCostData>['forecast'];
  dataset: string;
  ui: (en: string, zh: string) => string;
}> = ({ forecast, dataset, ui }) => {
  const { C } = useTheme();
  const k = useMemo(
    () => ({
      corrective: ui('Corrective', '矯正性'),
      preventive: ui('Preventive', '預防性'),
      revenueLoss: ui('Revenue Loss', '收入損失'),
      fixed: ui('Fixed', '固定'),
    }),
    [ui],
  );
  const seasonLabel = (s: string) => {
    const m: Record<string, string> = {
      winter: ui('Winter', '冬'),
      spring: ui('Spring', '春'),
      summer: ui('Summer', '夏'),
      autumn: ui('Autumn', '秋'),
    };
    return m[s] ?? s;
  };

  const data = useMemo(() => {
    if (!forecast.data) return [];
    return ['winter', 'spring', 'summer', 'autumn'].map(s => {
      const sr = forecast.data!.seasonal[s];
      return {
        season: seasonLabel(s),
        [k.corrective]:
          sr.corrective_wt_material + sr.corrective_wt_equipment + sr.corrective_wt_mob,
        [k.revenueLoss]: sr.corrective_wt_revenue_loss + sr.preventive_revenue_loss,
        [k.preventive]: sr.preventive_total,
        [k.fixed]: sr.fixed_cost,
      };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forecast.data, k.corrective, k.preventive, k.revenueLoss, k.fixed]);

  return (
    <Panel
      title={ui('Cost Forecast', '成本預測')}
      subtitle={ui('Annual breakdown · seasonal stacked bar', '年度分解・四季堆疊圖')}
    >
      <Btn
        variant="primary"
        onClick={() => forecast.run({ dataset })}
        disabled={forecast.loading}
        ariaLabel={ui('Run forecast', '執行預測')}
      >
        {forecast.loading ? ui('Loading…', '計算中…') : ui('Run forecast', '執行預測')}
      </Btn>
      {forecast.error && <ErrorBox message={forecast.error} />}
      <DatasetMetaBadge meta={forecast.data?.dataset_meta} ui={ui} />

      {forecast.data && (
        <>
          <div
            style={{
              marginTop: 16,
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 10,
            }}
          >
            <SmallStat
              label={ui('Avail. (time)', '可用度（時）')}
              value={fmtPct(forecast.data.availability_time)}
            />
            <SmallStat
              label={ui('Avail. (energy)', '可用度（能）')}
              value={fmtPct(forecast.data.availability_energy)}
            />
            <SmallStat
              label={ui('¢/kWh', '每度成本')}
              value={fmtKwh(forecast.data.cost_per_kwh)}
              highlight
            />
            <SmallStat label={ui('Total', '總成本')} value={fmtMoney(forecast.data.total_effort)} />
          </div>

          <div style={{ marginTop: 18, height: 280 }}>
            <ResponsiveContainer>
              <BarChart data={data} margin={{ top: 5, right: 12, bottom: 5, left: 0 }}>
                <CartesianGrid stroke={C.border} strokeDasharray="3 3" />
                <XAxis dataKey="season" stroke={C.sub} fontSize={11} />
                <YAxis
                  stroke={C.sub}
                  fontSize={11}
                  tickFormatter={v => `${(v / 1e6).toFixed(0)}M`}
                />
                <Tooltip
                  contentStyle={{
                    background: C.panel,
                    border: `1px solid ${C.border}`,
                    color: C.text,
                  }}
                  formatter={(v: number) => fmtMoney(v)}
                />
                <Legend wrapperStyle={{ paddingTop: 8, color: C.sub, fontSize: 11 }} />
                <Bar dataKey={k.corrective} stackId="a" fill={C.warn} />
                <Bar dataKey={k.preventive} stackId="a" fill={C.accent} />
                <Bar dataKey={k.revenueLoss} stackId="a" fill={C.amber} />
                <Bar dataKey={k.fixed} stackId="a" fill={C.faint} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Panel>
  );
};

// ─── LCOE panel ───────────────────────────────────────────────

const LCOEPanel: React.FC<{
  lcoe: ReturnType<typeof useCostData>['lcoe'];
  dataset: string;
  ui: (en: string, zh: string) => string;
}> = ({ lcoe, dataset, ui }) => {
  const [capex, setCapex] = useState(1250);
  const [discount, setDiscount] = useState(0.08);

  return (
    <Panel
      title={ui('LCOE Calculation', 'LCOE 計算')}
      subtitle={ui('Levelized cost · CAPEX + OPEX NPV / Energy NPV', '均化電力成本 · 現值算式')}
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'flex-end' }}>
        <Field label={ui('CAPEX (EUR/kW)', 'CAPEX EUR/kW')}>
          <Input
            type="number"
            value={capex}
            onChange={v => setCapex(Number(v))}
            width={140}
          />
        </Field>
        <Field label={ui('Discount', '折現率')}>
          <Input
            type="number"
            step="0.01"
            value={discount}
            onChange={v => setDiscount(Number(v))}
            width={100}
          />
        </Field>
        <Btn
          variant="primary"
          onClick={() => lcoe.run({ dataset, capex_per_kw: capex, discount_rate: discount })}
          disabled={lcoe.loading}
        >
          {lcoe.loading ? ui('Loading…', '計算中…') : ui('Calculate LCOE', '計算 LCOE')}
        </Btn>
      </div>
      {lcoe.error && <ErrorBox message={lcoe.error} />}
      <DatasetMetaBadge meta={lcoe.data?.dataset_meta} ui={ui} />

      {lcoe.data && (
        <div
          style={{
            marginTop: 16,
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: 10,
          }}
        >
          <SmallStat
            label="LCOE"
            value={`${lcoe.data.lcoe.toFixed(2)} EUR/MWh`}
            hint={ui('Lifetime avg', '生命週期平均')}
            highlight
          />
          <SmallStat label={ui('CAPEX', 'CAPEX 總額')} value={fmtMoney(lcoe.data.capex_total)} />
          <SmallStat label={ui('OPEX NPV', 'OPEX 現值')} value={fmtMoney(lcoe.data.opex_total_npv)} />
          <SmallStat
            label={ui('Energy NPV', '能量現值')}
            value={`${(lcoe.data.energy_total_npv / 1e6).toFixed(1)} M MWh`}
          />
          <SmallStat
            label={ui('Total cost NPV', '總成本現值')}
            value={fmtMoney(lcoe.data.total_cost_npv)}
          />
        </div>
      )}
    </Panel>
  );
};

// ─── Monte Carlo panel ────────────────────────────────────────

const MonteCarloPanel: React.FC<{
  monteCarlo: ReturnType<typeof useCostData>['monteCarlo'];
  dataset: string;
  ui: (en: string, zh: string) => string;
}> = ({ monteCarlo, dataset, ui }) => {
  const { C } = useTheme();
  const [nSim, setNSim] = useState(100);
  const [seed, setSeed] = useState(42);

  const data = useMemo(() => {
    if (!monteCarlo.data) return [];
    const c = monteCarlo.data.percentiles.cost;
    return [
      { name: 'P10', value: c.p10, color: C.ok },
      { name: 'P50', value: c.p50, color: C.accent },
      { name: ui('Mean', '平均'), value: c.mean, color: C.amber },
      { name: 'P90', value: c.p90, color: C.warn },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [monteCarlo.data, C.ok, C.accent, C.amber, C.warn]);

  return (
    <Panel
      title={ui('Monte Carlo Risk', '蒙地卡羅風險分析')}
      subtitle={ui('Stochastic sampling · P10 / P50 / P90', '隨機抽樣・P10 / P50 / P90')}
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'flex-end' }}>
        <Field label={ui('# sims (10–10000)', '模擬次數（10–10000）')}>
          <Input
            type="number"
            value={nSim}
            onChange={v => setNSim(Number(v))}
            min={10}
            max={10000}
            width={120}
          />
        </Field>
        <Field label={ui('Seed', '種子')}>
          <Input type="number" value={seed} onChange={v => setSeed(Number(v))} width={90} />
        </Field>
        <Btn
          variant="primary"
          onClick={() => monteCarlo.run({ dataset, n_simulations: nSim, seed })}
          disabled={monteCarlo.loading}
        >
          {monteCarlo.loading ? ui('Loading…', '計算中…') : ui('Run', '執行')}
        </Btn>
      </div>
      {monteCarlo.error && <ErrorBox message={monteCarlo.error} />}
      <DatasetMetaBadge meta={monteCarlo.data?.dataset_meta} ui={ui} />

      {monteCarlo.data && (
        <>
          <div
            style={{
              marginTop: 16,
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 10,
            }}
          >
            <SmallStat
              label={ui('Deterministic', '確定值')}
              value={fmtMoney(monteCarlo.data.deterministic.total_effort)}
            />
            <SmallStat
              label="P50"
              value={fmtMoney(monteCarlo.data.percentiles.cost.p50)}
              highlight
            />
            <SmallStat
              label={ui('P10–P90', 'P10–P90 區間')}
              value={fmtMoney(
                monteCarlo.data.percentiles.cost.p90 - monteCarlo.data.percentiles.cost.p10,
              )}
            />
            <SmallStat
              label={ui('Std dev', '標準差')}
              value={fmtMoney(monteCarlo.data.percentiles.cost.std)}
            />
          </div>

          <div style={{ marginTop: 18, height: 240 }}>
            <ResponsiveContainer>
              <BarChart data={data} margin={{ top: 5, right: 12, bottom: 5, left: 0 }}>
                <CartesianGrid stroke={C.border} strokeDasharray="3 3" />
                <XAxis dataKey="name" stroke={C.sub} fontSize={11} />
                <YAxis stroke={C.sub} fontSize={11} tickFormatter={v => `${(v / 1e6).toFixed(0)}M`} />
                <Tooltip
                  contentStyle={{
                    background: C.panel,
                    border: `1px solid ${C.border}`,
                    color: C.text,
                  }}
                  formatter={(v: number) => fmtMoney(v)}
                />
                <Bar dataKey="value">
                  {data.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Panel>
  );
};

// ─── VarFluct panel ───────────────────────────────────────────

const VarFluctPanel: React.FC<{
  varFluct: ReturnType<typeof useCostData>['varFluct'];
  dataset: string;
  ui: (en: string, zh: string) => string;
}> = ({ varFluct, dataset, ui }) => {
  const { C } = useTheme();
  const k = useMemo(
    () => ({
      total: ui('Total Effort (M EUR)', '總成本 (M EUR)'),
      mult: ui('Failure Multiplier', '故障倍率'),
      avail: ui('Availability (%)', '可用度 (%)'),
    }),
    [ui],
  );
  const data = useMemo(() => {
    if (!varFluct.data) return [];
    return varFluct.data.yearly.map(y => ({
      year: y.year,
      [k.total]: y.total_effort / 1e6,
      [k.mult]: y.failure_multiplier,
      [k.avail]: y.availability_time * 100,
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [varFluct.data, k.total, k.mult, k.avail]);

  return (
    <Panel
      title={ui('Lifetime Variation (VarFluct)', '生命週期變化')}
      subtitle={ui('20-year trace · bathtub failure rate', '20 年逐年・浴缸曲線')}
    >
      <Btn
        variant="primary"
        onClick={() => varFluct.run({ dataset })}
        disabled={varFluct.loading}
      >
        {varFluct.loading ? ui('Loading…', '計算中…') : ui('Run lifetime sim', '執行 20 年模擬')}
      </Btn>
      {varFluct.error && <ErrorBox message={varFluct.error} />}
      <DatasetMetaBadge meta={varFluct.data?.dataset_meta} ui={ui} />

      {varFluct.data && (
        <>
          <div
            style={{
              marginTop: 16,
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 10,
            }}
          >
            <SmallStat
              label={ui('NPV', 'NPV 總成本')}
              value={fmtMoney(varFluct.data.summary.npv_total_effort)}
              hint={ui('20-yr discounted', '20 年折現')}
              highlight
            />
            <SmallStat
              label={ui('Avg / yr', '年均')}
              value={fmtMoney(varFluct.data.summary.avg_annual_effort)}
            />
            <SmallStat
              label={ui('Min year', '最低年')}
              value={`${ui('Y', '第')}${varFluct.data.summary.min_year_index}: ${fmtMoney(
                varFluct.data.summary.min_year_effort,
              )}`}
            />
            <SmallStat
              label={ui('Max year', '最高年')}
              value={`${ui('Y', '第')}${varFluct.data.summary.max_year_index}: ${fmtMoney(
                varFluct.data.summary.max_year_effort,
              )}`}
            />
          </div>

          <div style={{ marginTop: 18, height: 320 }}>
            <ResponsiveContainer>
              <LineChart data={data} margin={{ top: 5, right: 16, bottom: 30, left: 0 }}>
                <CartesianGrid stroke={C.border} strokeDasharray="3 3" />
                <XAxis
                  dataKey="year"
                  stroke={C.sub}
                  fontSize={11}
                  label={{
                    value: ui('Year', '年'),
                    fill: C.sub,
                    position: 'insideBottom',
                    offset: -5,
                  }}
                />
                <YAxis
                  yAxisId="left"
                  stroke={C.accent}
                  fontSize={11}
                  tickFormatter={v => `${v.toFixed(0)}M`}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke={C.amber}
                  fontSize={11}
                  tickFormatter={v => `${v.toFixed(0)}`}
                />
                <Tooltip
                  contentStyle={{
                    background: C.panel,
                    border: `1px solid ${C.border}`,
                    color: C.text,
                  }}
                />
                <Legend
                  wrapperStyle={{ paddingTop: 8, fontSize: 11, color: C.sub }}
                  iconType="line"
                />
                <Line yAxisId="left" type="monotone" dataKey={k.total} stroke={C.accent} strokeWidth={2} dot={false} />
                <Line yAxisId="right" type="monotone" dataKey={k.mult} stroke={C.amber} strokeWidth={2} dot={false} />
                <Line yAxisId="right" type="monotone" dataKey={k.avail} stroke={C.ok} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Panel>
  );
};

// ─── Small stat reused inside panels ──────────────────────────

const SmallStat: React.FC<{
  label: React.ReactNode;
  value: React.ReactNode;
  hint?: React.ReactNode;
  highlight?: boolean;
}> = ({ label, value, hint, highlight }) => {
  const { C } = useTheme();
  return (
    <div
      style={{
        background: C.panelMuted,
        border: `1px solid ${highlight ? C.accent : C.border}`,
        borderRadius: 10,
        padding: '10px 12px',
      }}
    >
      <div style={{ fontSize: 11, color: C.sub, textTransform: 'uppercase', letterSpacing: 0.6 }}>
        {label}
      </div>
      <div
        style={{
          marginTop: 4,
          fontSize: 18,
          fontWeight: 600,
          color: highlight ? C.accent : C.text,
          fontFamily: 'JetBrains Mono, monospace',
        }}
      >
        {value}
      </div>
      {hint && <div style={{ fontSize: 11, color: C.sub, marginTop: 2 }}>{hint}</div>}
    </div>
  );
};

// ─── KPI strip ────────────────────────────────────────────────

const KpiStrip: React.FC<{
  cost: ReturnType<typeof useCostData>;
  ui: (en: string, zh: string) => string;
}> = ({ cost, ui }) => {
  const f = cost.forecast.data;
  const l = cost.lcoe.data;
  const m = cost.monteCarlo.data;
  const v = cost.varFluct.data;

  const items: { label: string; value: React.ReactNode; unit?: React.ReactNode; highlight?: boolean }[] = [
    {
      label: ui('Total Cost', '總成本'),
      value: f ? fmtMoney(f.total_effort) : '—',
    },
    {
      label: 'LCOE',
      value: l ? l.lcoe.toFixed(2) : '—',
      unit: 'EUR/MWh',
      highlight: true,
    },
    {
      label: 'NPV',
      value: v ? fmtMoney(v.summary.npv_total_effort) : '—',
    },
    {
      label: ui('MC P50', '蒙地卡羅 P50'),
      value: m ? fmtMoney(m.percentiles.cost.p50) : '—',
    },
    {
      label: ui('CapEx', 'CapEx'),
      value: l ? fmtMoney(l.capex_total) : '—',
    },
    {
      label: ui('Avg / yr', '年均成本'),
      value: v ? fmtMoney(v.summary.avg_annual_effort) : '—',
    },
  ];

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: 12,
        marginBottom: 20,
      }}
    >
      {items.map((it, i) => (
        <Card key={i} padding={16}>
          <Stat
            label={it.label}
            value={it.value}
            unit={it.unit}
            highlight={it.highlight}
            size={28}
          />
        </Card>
      ))}
    </div>
  );
};

// ─── Main ─────────────────────────────────────────────────────

interface CostPageProps {
  lang?: 'en' | 'zh';
}

const CostPage: React.FC<CostPageProps> = () => {
  const cost = useCostData();
  const { ui } = useI18n();
  const [dataset, setDataset] = useState('k13');
  const [farms, setFarms] = useState<FarmOption[]>([]);

  // Load farms list for dataset selector
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await authFetch(`${API_BASE}/api/farms`);
        if (!res.ok) return;
        const body = await res.json();
        if (cancelled) return;
        const opts: FarmOption[] = (body.farms || []).map((f: {
          farm_id: string;
          name: string;
          turbine_count?: number;
          turbine_spec?: Record<string, unknown>;
        }) => ({
          farm_id: f.farm_id,
          name: f.name,
          turbine_count: f.turbine_count ?? 0,
          rated_kw: (f.turbine_spec?.rated_power_kw as number | undefined) ?? null,
        }));
        setFarms(opts);
      } catch {
        /* silent */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // dataset 變動：自動跑 forecast，其他 panel 清空
  useEffect(() => {
    cost.forecast.run({ dataset });
    cost.lcoe.reset();
    cost.monteCarlo.reset();
    cost.varFluct.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset]);

  const datasetOptions = [
    { value: 'k13', label: ui('K13 demo', 'K13 範例') },
    ...farms.map(f => ({
      value: `farm:${f.farm_id}`,
      label: `${f.name}${f.rated_kw ? ` · ${(f.rated_kw / 1000).toFixed(1)} MW` : ''}`,
    })),
  ];

  const runAll = () => {
    cost.forecast.run({ dataset });
    cost.lcoe.run({ dataset, capex_per_kw: 1250, discount_rate: 0.08 });
    cost.monteCarlo.run({ dataset, n_simulations: 1000, seed: 42 });
    cost.varFluct.run({ dataset });
  };

  return (
    <div>
      <PageHeader
        title={ui('Cost Model', '成本模型')}
        sub={ui(
          'LCOE · NPV · Monte Carlo · 20-year forecast',
          'LCOE・NPV・蒙地卡羅・20 年預測',
        )}
        actions={
          <>
            <Select
              value={dataset}
              onChange={setDataset}
              options={datasetOptions}
              ariaLabel={ui('Dataset', '資料集')}
              width={200}
            />
            <Btn variant="primary" onClick={runAll} ariaLabel={ui('Run scenario', '執行情境')}>
              {ui('Run scenario', '執行情境')}
            </Btn>
          </>
        }
      />

      <KpiStrip cost={cost} ui={ui} />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))',
          gap: 16,
        }}
      >
        <ForecastPanel forecast={cost.forecast} dataset={dataset} ui={ui} />
        <LCOEPanel lcoe={cost.lcoe} dataset={dataset} ui={ui} />
        <MonteCarloPanel monteCarlo={cost.monteCarlo} dataset={dataset} ui={ui} />
        <VarFluctPanel varFluct={cost.varFluct} dataset={dataset} ui={ui} />
      </div>
    </div>
  );
};

export default CostPage;
