/**
 * CostPage — windMindOM cost dashboard.
 *
 * 對應 backend 4 endpoints (modules/cost/routers/cost_router.py)。
 * 4 panel：
 *   1. Forecast — 6 top-level metric + 4 季 stacked bar
 *   2. LCOE — capex/discount input → LCOE 結果 + 拆解
 *   3. Monte Carlo — n_sim/seed input → P10/P50/P90 + std bar
 *   4. VarFluct — 20 年 lifetime line chart + summary
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

// ─── Formatters ───────────────────────────────────────────────────────────

const fmtMoney = (eur: number): string => {
  if (Math.abs(eur) >= 1e9) return `${(eur / 1e9).toFixed(2)} B EUR`;
  if (Math.abs(eur) >= 1e6) return `${(eur / 1e6).toFixed(2)} M EUR`;
  if (Math.abs(eur) >= 1e3) return `${(eur / 1e3).toFixed(1)} k EUR`;
  return `${eur.toFixed(2)} EUR`;
};

const fmtPct = (v: number): string => `${(v * 100).toFixed(1)}%`;

const fmtKwh = (v: number): string => `${(v * 100).toFixed(2)} ¢/kWh`;

// ─── Reusable bits ────────────────────────────────────────────────────────

interface MetricCardProps {
  label: string;
  value: string;
  hint?: string;
  highlight?: boolean;
}

const MetricCard: React.FC<MetricCardProps> = ({ label, value, hint, highlight }) => (
  <div
    className={`bg-gray-800 border ${
      highlight ? 'border-cyan-500/60' : 'border-gray-700'
    } rounded-lg p-4`}
  >
    <div className="text-xs text-gray-400 uppercase tracking-wide">{label}</div>
    <div className={`mt-1 text-2xl font-semibold ${highlight ? 'text-cyan-300' : 'text-gray-100'}`}>
      {value}
    </div>
    {hint && <div className="mt-1 text-xs text-gray-500">{hint}</div>}
  </div>
);

const Panel: React.FC<{ title: string; subtitle?: string; children: React.ReactNode }> = ({
  title,
  subtitle,
  children,
}) => (
  <section className="bg-gray-800/50 border border-gray-700 rounded-xl p-5">
    <div className="mb-4">
      <h2 className="text-lg font-semibold text-gray-100">{title}</h2>
      {subtitle && <p className="text-xs text-gray-400 mt-1">{subtitle}</p>}
    </div>
    {children}
  </section>
);

const Btn: React.FC<{
  onClick: () => void;
  loading?: boolean;
  loadingText?: string;
  children: React.ReactNode;
  variant?: 'primary' | 'secondary';
}> = ({ onClick, loading, loadingText, children, variant = 'primary' }) => {
  const cls =
    variant === 'primary'
      ? 'bg-cyan-600 hover:bg-cyan-500 text-white'
      : 'bg-gray-700 hover:bg-gray-600 text-gray-100';
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={`px-4 py-2 rounded-md text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${cls}`}
    >
      {loading ? (loadingText ?? 'Loading…') : children}
    </button>
  );
};

const ErrorBox: React.FC<{ message: string }> = ({ message }) => (
  <div className="mt-3 bg-red-900/30 border border-red-700 text-red-200 text-sm rounded p-3">
    ⚠ {message}
  </div>
);

// ─── Panel 1: Forecast ────────────────────────────────────────────────────

const ForecastPanel: React.FC<{
  forecast: ReturnType<typeof useCostData>['forecast'];
  ui: (en: string, zh: string) => string;
}> = ({ forecast, ui }) => {
  // 對應 zh / en 的 stack key（chart legend 用）
  const k = {
    corrective: ui('Corrective', '矯正性維修'),
    preventive: ui('Preventive', '預防性維修'),
    revenueLoss: ui('Revenue Loss', '收入損失'),
    fixed: ui('Fixed', '固定成本'),
  };
  const seasonLabel: Record<string, string> = {
    winter: ui('Winter', '冬'),
    spring: ui('Spring', '春'),
    summer: ui('Summer', '夏'),
    autumn: ui('Autumn', '秋'),
  };

  const seasonalChartData = useMemo(() => {
    if (!forecast.data) return [];
    const seasons = ['winter', 'spring', 'summer', 'autumn'];
    return seasons.map((s) => {
      const sr = forecast.data!.seasonal[s];
      return {
        season: seasonLabel[s] ?? s,
        [k.corrective]: sr.corrective_wt_material + sr.corrective_wt_equipment + sr.corrective_wt_mob,
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
      subtitle={ui(
        'K13 dataset · annual cost breakdown · seasonal stacked bar',
        'K13 資料集 · 年度成本分解 · 四季堆疊圖',
      )}
    >
      <Btn
        onClick={() => forecast.run()}
        loading={forecast.loading}
        loadingText={ui('Loading…', '計算中…')}
      >
        {ui('Run Forecast', '執行預測')}
      </Btn>
      {forecast.error && <ErrorBox message={forecast.error} />}

      {forecast.data && (
        <>
          <div className="mt-5 grid grid-cols-2 md:grid-cols-3 gap-3">
            <MetricCard
              label={ui('Availability (time)', '可用度（時間）')}
              value={fmtPct(forecast.data.availability_time)}
            />
            <MetricCard
              label={ui('Availability (energy)', '可用度（能量）')}
              value={fmtPct(forecast.data.availability_energy)}
            />
            <MetricCard
              label={ui('Cost per kWh', '每度電成本')}
              value={fmtKwh(forecast.data.cost_per_kwh)}
              highlight
            />
            <MetricCard
              label={ui('Total Effort', '總成本')}
              value={fmtMoney(forecast.data.total_effort)}
            />
            <MetricCard
              label={ui('Repair Cost', '維修成本')}
              value={fmtMoney(forecast.data.total_repair_cost)}
            />
            <MetricCard
              label={ui('Revenue Loss', '收入損失')}
              value={fmtMoney(forecast.data.total_revenue_loss)}
            />
          </div>

          <div className="mt-6 h-72">
            <ResponsiveContainer>
              <BarChart data={seasonalChartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid stroke="#374151" strokeDasharray="3 3" />
                <XAxis dataKey="season" stroke="#9ca3af" />
                <YAxis
                  stroke="#9ca3af"
                  tickFormatter={(v) => `${(v / 1e6).toFixed(0)}M`}
                />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151' }}
                  formatter={(v: number) => fmtMoney(v)}
                />
                <Legend wrapperStyle={{ paddingTop: 8 }} />
                <Bar dataKey={k.corrective} stackId="a" fill="#06b6d4" />
                <Bar dataKey={k.preventive} stackId="a" fill="#0891b2" />
                <Bar dataKey={k.revenueLoss} stackId="a" fill="#fbbf24" />
                <Bar dataKey={k.fixed} stackId="a" fill="#6b7280" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Panel>
  );
};

// ─── Panel 2: LCOE ────────────────────────────────────────────────────────

const LCOEPanel: React.FC<{
  lcoe: ReturnType<typeof useCostData>['lcoe'];
  ui: (en: string, zh: string) => string;
}> = ({ lcoe, ui }) => {
  const [capex, setCapex] = useState(1250);
  const [discount, setDiscount] = useState(0.08);

  return (
    <Panel
      title={ui('LCOE Calculation', 'LCOE 計算')}
      subtitle={ui(
        'Levelized Cost of Energy · CAPEX + OPEX NPV / Energy NPV',
        '均化電力成本 · CAPEX + OPEX 現值 / 能量現值',
      )}
    >
      <div className="flex flex-wrap gap-3 items-end">
        <label className="text-sm text-gray-300 block">
          {ui('CAPEX (EUR/kW)', '建置成本（EUR/kW）')}
          <input
            type="number"
            value={capex}
            onChange={(e) => setCapex(Number(e.target.value))}
            className="mt-1 block w-32 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-gray-100 text-sm"
          />
        </label>
        <label className="text-sm text-gray-300 block">
          {ui('Discount Rate', '折現率')}
          <input
            type="number"
            step="0.01"
            value={discount}
            onChange={(e) => setDiscount(Number(e.target.value))}
            className="mt-1 block w-24 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-gray-100 text-sm"
          />
        </label>
        <Btn
          onClick={() => lcoe.run({ capex_per_kw: capex, discount_rate: discount })}
          loading={lcoe.loading}
          loadingText={ui('Loading…', '計算中…')}
        >
          {ui('Calculate LCOE', '計算 LCOE')}
        </Btn>
      </div>
      {lcoe.error && <ErrorBox message={lcoe.error} />}

      {lcoe.data && (
        <div className="mt-5 grid grid-cols-2 md:grid-cols-3 gap-3">
          <MetricCard
            label="LCOE"
            value={`${lcoe.data.lcoe.toFixed(2)} EUR/MWh`}
            hint={ui('Lifetime average', '生命週期平均')}
            highlight
          />
          <MetricCard
            label={ui('CAPEX Total', 'CAPEX 總額')}
            value={fmtMoney(lcoe.data.capex_total)}
          />
          <MetricCard
            label={ui('OPEX NPV', 'OPEX 現值')}
            value={fmtMoney(lcoe.data.opex_total_npv)}
          />
          <MetricCard
            label={ui('Energy NPV', '能量現值')}
            value={`${(lcoe.data.energy_total_npv / 1e6).toFixed(1)} M MWh`}
          />
          <MetricCard
            label={ui('Total Cost NPV', '總成本現值')}
            value={fmtMoney(lcoe.data.total_cost_npv)}
          />
        </div>
      )}
    </Panel>
  );
};

// ─── Panel 3: Monte Carlo ─────────────────────────────────────────────────

const MonteCarloPanel: React.FC<{
  monteCarlo: ReturnType<typeof useCostData>['monteCarlo'];
  ui: (en: string, zh: string) => string;
}> = ({ monteCarlo, ui }) => {
  const [nSim, setNSim] = useState(100);
  const [seed, setSeed] = useState(42);

  const percentileChartData = useMemo(() => {
    if (!monteCarlo.data) return [];
    const c = monteCarlo.data.percentiles.cost;
    return [
      { name: 'P10', value: c.p10, color: '#10b981' },
      { name: ui('P50 (median)', 'P50（中位數）'), value: c.p50, color: '#06b6d4' },
      { name: ui('Mean', '平均'), value: c.mean, color: '#fbbf24' },
      { name: 'P90', value: c.p90, color: '#ef4444' },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [monteCarlo.data]);

  return (
    <Panel
      title={ui('Monte Carlo Risk Analysis', '蒙地卡羅風險分析')}
      subtitle={ui(
        'Stochastic sampling on failure rates / costs · P10 / P50 / P90',
        '對故障率 / 成本做隨機抽樣 · P10 / P50 / P90',
      )}
    >
      <div className="flex flex-wrap gap-3 items-end">
        <label className="text-sm text-gray-300 block">
          {ui('# Simulations (10–10000)', '模擬次數（10–10000）')}
          <input
            type="number"
            value={nSim}
            min={10}
            max={10000}
            onChange={(e) => setNSim(Number(e.target.value))}
            className="mt-1 block w-32 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-gray-100 text-sm"
          />
        </label>
        <label className="text-sm text-gray-300 block">
          {ui('Seed', '亂數種子')}
          <input
            type="number"
            value={seed}
            onChange={(e) => setSeed(Number(e.target.value))}
            className="mt-1 block w-24 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-gray-100 text-sm"
          />
        </label>
        <Btn
          onClick={() => monteCarlo.run({ n_simulations: nSim, seed })}
          loading={monteCarlo.loading}
          loadingText={ui('Loading…', '計算中…')}
        >
          {ui('Run Monte Carlo', '執行蒙地卡羅')}
        </Btn>
      </div>
      {monteCarlo.error && <ErrorBox message={monteCarlo.error} />}

      {monteCarlo.data && (
        <>
          <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard
              label={ui('Deterministic', '確定值')}
              value={fmtMoney(monteCarlo.data.deterministic.total_effort)}
              hint={ui('Single-point estimate', '單點估算')}
            />
            <MetricCard
              label={ui('P50 (median)', 'P50（中位數）')}
              value={fmtMoney(monteCarlo.data.percentiles.cost.p50)}
              highlight
            />
            <MetricCard
              label={ui('P10 → P90 spread', 'P10 → P90 區間')}
              value={fmtMoney(
                monteCarlo.data.percentiles.cost.p90 - monteCarlo.data.percentiles.cost.p10,
              )}
              hint={ui('Risk window', '風險範圍')}
            />
            <MetricCard
              label={ui('Std Deviation', '標準差')}
              value={fmtMoney(monteCarlo.data.percentiles.cost.std)}
            />
          </div>

          <div className="mt-6 h-64">
            <ResponsiveContainer>
              <BarChart data={percentileChartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid stroke="#374151" strokeDasharray="3 3" />
                <XAxis dataKey="name" stroke="#9ca3af" />
                <YAxis
                  stroke="#9ca3af"
                  tickFormatter={(v) => `${(v / 1e6).toFixed(0)}M`}
                />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151' }}
                  formatter={(v: number) => fmtMoney(v)}
                />
                <Bar dataKey="value">
                  {percentileChartData.map((entry, i) => (
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

// ─── Panel 4: VarFluct (lifetime year-by-year) ────────────────────────────

const VarFluctPanel: React.FC<{
  varFluct: ReturnType<typeof useCostData>['varFluct'];
  ui: (en: string, zh: string) => string;
}> = ({ varFluct, ui }) => {
  // Localised legend keys
  const k = {
    totalEffort: ui('Total Effort (M EUR)', '總成本（M EUR）'),
    failureMultiplier: ui('Failure Multiplier', '故障倍率'),
    availability: ui('Availability (%)', '可用度（%）'),
  };

  const yearlyChartData = useMemo(() => {
    if (!varFluct.data) return [];
    return varFluct.data.yearly.map((y) => ({
      year: y.year,
      [k.totalEffort]: y.total_effort / 1e6,
      [k.failureMultiplier]: y.failure_multiplier,
      [k.availability]: y.availability_time * 100,
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [varFluct.data, k.totalEffort, k.failureMultiplier, k.availability]);

  return (
    <Panel
      title={ui('Lifetime Variation (VarFluct)', '生命週期變化（VarFluct）')}
      subtitle={ui(
        'Year-by-year cost evolution · bathtub failure rate · NPV summary',
        '逐年成本變化 · 浴缸曲線故障率 · NPV 總結',
      )}
    >
      <Btn
        onClick={() => varFluct.run()}
        loading={varFluct.loading}
        loadingText={ui('Loading…', '計算中…')}
      >
        {ui('Run Lifetime Simulation', '執行生命週期模擬')}
      </Btn>
      {varFluct.error && <ErrorBox message={varFluct.error} />}

      {varFluct.data && (
        <>
          <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard
              label={ui('NPV Total Effort', 'NPV 總成本')}
              value={fmtMoney(varFluct.data.summary.npv_total_effort)}
              hint={ui('20-year discounted', '20 年折現')}
              highlight
            />
            <MetricCard
              label={ui('Avg Annual Effort', '年均成本')}
              value={fmtMoney(varFluct.data.summary.avg_annual_effort)}
            />
            <MetricCard
              label={ui('Min Year', '最低年')}
              value={`${ui('Year', '第')} ${varFluct.data.summary.min_year_index}${ui(
                '',
                ' 年',
              )}: ${fmtMoney(varFluct.data.summary.min_year_effort)}`}
            />
            <MetricCard
              label={ui('Max Year', '最高年')}
              value={`${ui('Year', '第')} ${varFluct.data.summary.max_year_index}${ui(
                '',
                ' 年',
              )}: ${fmtMoney(varFluct.data.summary.max_year_effort)}`}
            />
          </div>

          {/* Chart 給更多空間：h-80（下移 legend 不撞）+ 增加 right margin 給 right axis */}
          <div className="mt-6 h-80">
            <ResponsiveContainer>
              <LineChart
                data={yearlyChartData}
                margin={{ top: 5, right: 20, bottom: 30, left: 0 }}
              >
                <CartesianGrid stroke="#374151" strokeDasharray="3 3" />
                <XAxis
                  dataKey="year"
                  stroke="#9ca3af"
                  label={{
                    value: ui('Year', '年'),
                    fill: '#9ca3af',
                    position: 'insideBottom',
                    offset: -5,
                  }}
                />
                {/* 左軸：M EUR — 不放 axis label，靠 legend 顏色說明 */}
                <YAxis
                  yAxisId="left"
                  stroke="#06b6d4"
                  tickFormatter={(v) => `${v.toFixed(0)}M`}
                />
                {/* 右軸：multiplier 倍率 + availability %（共用刻度 0–100） */}
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke="#fbbf24"
                  tickFormatter={(v) => `${v.toFixed(0)}`}
                />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151' }}
                />
                <Legend
                  wrapperStyle={{ paddingTop: 8, fontSize: 12 }}
                  iconType="line"
                />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey={k.totalEffort}
                  stroke="#06b6d4"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey={k.failureMultiplier}
                  stroke="#fbbf24"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey={k.availability}
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Panel>
  );
};

// ─── Main page ────────────────────────────────────────────────────────────

interface CostPageProps {
  lang?: 'en' | 'zh';
}

const CostPage: React.FC<CostPageProps> = () => {
  const cost = useCostData();
  const { ui } = useI18n();  // 取現時 lang，不靠 props（與既有 maintenance / history page 一致）

  // Auto-run forecast on first mount so user 一進來就有東西看
  useEffect(() => {
    cost.forecast.run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="p-4 md:p-6 space-y-6">
      <header className="mb-2">
        <h1 className="text-2xl font-bold text-gray-100">{ui('Cost Module', '成本模組')}</h1>
        <p className="text-sm text-gray-400 mt-1">
          {ui(
            'ECN-port engine · K13 demo dataset · 4 endpoints (forecast / LCOE / Monte Carlo / VarFluct)',
            'ECN 移植引擎 · K13 示範資料集 · 4 個端點（預測 / LCOE / 蒙地卡羅 / 生命週期）',
          )}
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ForecastPanel forecast={cost.forecast} ui={ui} />
        <LCOEPanel lcoe={cost.lcoe} ui={ui} />
        <MonteCarloPanel monteCarlo={cost.monteCarlo} ui={ui} />
        <VarFluctPanel varFluct={cost.varFluct} ui={ui} />
      </div>
    </div>
  );
};

export default CostPage;
