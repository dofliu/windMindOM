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
  children: React.ReactNode;
  variant?: 'primary' | 'secondary';
}> = ({ onClick, loading, children, variant = 'primary' }) => {
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
      {loading ? '計算中…' : children}
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
}> = ({ forecast }) => {
  const seasonalChartData = useMemo(() => {
    if (!forecast.data) return [];
    const seasons = ['winter', 'spring', 'summer', 'autumn'];
    return seasons.map((s) => {
      const sr = forecast.data!.seasonal[s];
      return {
        season: s,
        Corrective: sr.corrective_wt_material + sr.corrective_wt_equipment + sr.corrective_wt_mob,
        'Revenue Loss': sr.corrective_wt_revenue_loss + sr.preventive_revenue_loss,
        Preventive: sr.preventive_total,
        Fixed: sr.fixed_cost,
      };
    });
  }, [forecast.data]);

  return (
    <Panel
      title="Cost Forecast"
      subtitle="K13 dataset · annual cost breakdown · seasonal stacked bar"
    >
      <Btn onClick={() => forecast.run()} loading={forecast.loading}>
        Run Forecast
      </Btn>
      {forecast.error && <ErrorBox message={forecast.error} />}

      {forecast.data && (
        <>
          <div className="mt-5 grid grid-cols-2 md:grid-cols-3 gap-3">
            <MetricCard
              label="Availability (time)"
              value={fmtPct(forecast.data.availability_time)}
            />
            <MetricCard
              label="Availability (energy)"
              value={fmtPct(forecast.data.availability_energy)}
            />
            <MetricCard
              label="Cost per kWh"
              value={fmtKwh(forecast.data.cost_per_kwh)}
              highlight
            />
            <MetricCard label="Total Effort" value={fmtMoney(forecast.data.total_effort)} />
            <MetricCard label="Repair Cost" value={fmtMoney(forecast.data.total_repair_cost)} />
            <MetricCard label="Revenue Loss" value={fmtMoney(forecast.data.total_revenue_loss)} />
          </div>

          <div className="mt-6 h-72">
            <ResponsiveContainer>
              <BarChart data={seasonalChartData}>
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
                <Legend />
                <Bar dataKey="Corrective" stackId="a" fill="#06b6d4" />
                <Bar dataKey="Preventive" stackId="a" fill="#0891b2" />
                <Bar dataKey="Revenue Loss" stackId="a" fill="#fbbf24" />
                <Bar dataKey="Fixed" stackId="a" fill="#6b7280" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Panel>
  );
};

// ─── Panel 2: LCOE ────────────────────────────────────────────────────────

const LCOEPanel: React.FC<{ lcoe: ReturnType<typeof useCostData>['lcoe'] }> = ({ lcoe }) => {
  const [capex, setCapex] = useState(1250);
  const [discount, setDiscount] = useState(0.08);

  return (
    <Panel
      title="LCOE Calculation"
      subtitle="Levelized Cost of Energy · CAPEX + OPEX NPV / Energy NPV"
    >
      <div className="flex flex-wrap gap-3 items-end">
        <label className="text-sm text-gray-300 block">
          CAPEX (EUR/kW)
          <input
            type="number"
            value={capex}
            onChange={(e) => setCapex(Number(e.target.value))}
            className="mt-1 block w-32 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-gray-100 text-sm"
          />
        </label>
        <label className="text-sm text-gray-300 block">
          Discount Rate
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
        >
          Calculate LCOE
        </Btn>
      </div>
      {lcoe.error && <ErrorBox message={lcoe.error} />}

      {lcoe.data && (
        <div className="mt-5 grid grid-cols-2 md:grid-cols-3 gap-3">
          <MetricCard
            label="LCOE"
            value={`${lcoe.data.lcoe.toFixed(2)} EUR/MWh`}
            hint="Lifetime average"
            highlight
          />
          <MetricCard label="CAPEX Total" value={fmtMoney(lcoe.data.capex_total)} />
          <MetricCard label="OPEX NPV" value={fmtMoney(lcoe.data.opex_total_npv)} />
          <MetricCard
            label="Energy NPV"
            value={`${(lcoe.data.energy_total_npv / 1e6).toFixed(1)} M MWh`}
          />
          <MetricCard
            label="Total Cost NPV"
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
}> = ({ monteCarlo }) => {
  const [nSim, setNSim] = useState(100);
  const [seed, setSeed] = useState(42);

  const percentileChartData = useMemo(() => {
    if (!monteCarlo.data) return [];
    const c = monteCarlo.data.percentiles.cost;
    return [
      { name: 'P10', value: c.p10, color: '#10b981' },
      { name: 'P50 (median)', value: c.p50, color: '#06b6d4' },
      { name: 'Mean', value: c.mean, color: '#fbbf24' },
      { name: 'P90', value: c.p90, color: '#ef4444' },
    ];
  }, [monteCarlo.data]);

  return (
    <Panel
      title="Monte Carlo Risk Analysis"
      subtitle="Stochastic sampling on failure rates / costs · P10 / P50 / P90"
    >
      <div className="flex flex-wrap gap-3 items-end">
        <label className="text-sm text-gray-300 block">
          # Simulations (10–10000)
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
          Seed
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
        >
          Run Monte Carlo
        </Btn>
      </div>
      {monteCarlo.error && <ErrorBox message={monteCarlo.error} />}

      {monteCarlo.data && (
        <>
          <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard
              label="Deterministic"
              value={fmtMoney(monteCarlo.data.deterministic.total_effort)}
              hint="Single-point estimate"
            />
            <MetricCard
              label="P50 (median)"
              value={fmtMoney(monteCarlo.data.percentiles.cost.p50)}
              highlight
            />
            <MetricCard
              label="P10 → P90 spread"
              value={fmtMoney(
                monteCarlo.data.percentiles.cost.p90 - monteCarlo.data.percentiles.cost.p10,
              )}
              hint="Risk window"
            />
            <MetricCard
              label="Std Deviation"
              value={fmtMoney(monteCarlo.data.percentiles.cost.std)}
            />
          </div>

          <div className="mt-6 h-64">
            <ResponsiveContainer>
              <BarChart data={percentileChartData}>
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
}> = ({ varFluct }) => {
  const yearlyChartData = useMemo(() => {
    if (!varFluct.data) return [];
    return varFluct.data.yearly.map((y) => ({
      year: y.year,
      'Total Effort': y.total_effort / 1e6,
      'Failure Multiplier': y.failure_multiplier,
      Availability: y.availability_time * 100,
    }));
  }, [varFluct.data]);

  return (
    <Panel
      title="Lifetime Variation (VarFluct)"
      subtitle="Year-by-year cost evolution · bathtub failure rate · NPV summary"
    >
      <Btn onClick={() => varFluct.run()} loading={varFluct.loading}>
        Run Lifetime Simulation
      </Btn>
      {varFluct.error && <ErrorBox message={varFluct.error} />}

      {varFluct.data && (
        <>
          <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard
              label="NPV Total Effort"
              value={fmtMoney(varFluct.data.summary.npv_total_effort)}
              hint="20-year discounted"
              highlight
            />
            <MetricCard
              label="Avg Annual Effort"
              value={fmtMoney(varFluct.data.summary.avg_annual_effort)}
            />
            <MetricCard
              label="Min Year"
              value={`Year ${varFluct.data.summary.min_year_index}: ${fmtMoney(
                varFluct.data.summary.min_year_effort,
              )}`}
            />
            <MetricCard
              label="Max Year"
              value={`Year ${varFluct.data.summary.max_year_index}: ${fmtMoney(
                varFluct.data.summary.max_year_effort,
              )}`}
            />
          </div>

          <div className="mt-6 h-72">
            <ResponsiveContainer>
              <LineChart data={yearlyChartData}>
                <CartesianGrid stroke="#374151" strokeDasharray="3 3" />
                <XAxis dataKey="year" stroke="#9ca3af" label={{ value: 'Year', fill: '#9ca3af', position: 'bottom' }} />
                <YAxis
                  yAxisId="left"
                  stroke="#06b6d4"
                  label={{ value: 'M EUR', fill: '#06b6d4', angle: -90, position: 'insideLeft' }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke="#fbbf24"
                  label={{ value: 'Multiplier × Avail %', fill: '#fbbf24', angle: 90, position: 'insideRight' }}
                />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid #374151' }}
                />
                <Legend />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="Total Effort"
                  stroke="#06b6d4"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="Failure Multiplier"
                  stroke="#fbbf24"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="Availability"
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

  // Auto-run forecast on first mount so user 一進來就有東西看
  useEffect(() => {
    cost.forecast.run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="p-4 md:p-6 space-y-6">
      <header className="mb-2">
        <h1 className="text-2xl font-bold text-gray-100">Cost Module</h1>
        <p className="text-sm text-gray-400 mt-1">
          ECN-port engine · K13 demo dataset · 4 endpoints (forecast / LCOE / Monte Carlo / VarFluct)
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ForecastPanel forecast={cost.forecast} />
        <LCOEPanel lcoe={cost.lcoe} />
        <MonteCarloPanel monteCarlo={cost.monteCarlo} />
        <VarFluctPanel varFluct={cost.varFluct} />
      </div>
    </div>
  );
};

export default CostPage;
