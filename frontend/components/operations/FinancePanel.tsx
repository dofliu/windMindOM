/**
 * 收支與可用率（WMOM-20261127-01）：一段時間的發電量、收入、停機少收、運維支出、淨額、可用率，每台機組一列。
 *
 * 收入與少收的錢由運轉狀態紀錄 × 電價算，支出是成本帳本裡工單完工寫進去的人工與料件（DEC-20261127-02）。
 * 時間看風場時鐘：先不帶時間問一次（後端給最近 30 天、回傳風場時鐘的 end），之後的區間都從那個 end 往前算，
 * 時間倍率大時也對得上。
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Btn, Card, Stat } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  fetchAvailability,
  fetchFinance,
  type AvailabilityMetrics,
  type AvailabilityResponse,
  type FinanceResponse,
} from '../../services/operationsService';
import {
  ErrorNote,
  explainError,
  fmtEnergy,
  fmtHours,
  fmtMoney,
  fmtPct,
  fmtTime,
  pick,
  useTableStyles,
  type Lang,
} from './shared';

const RANGES = [
  { days: 1, en: 'Last 24 h', zh: '最近 24 小時' },
  { days: 7, en: 'Last 7 days', zh: '最近 7 天' },
  { days: 30, en: 'Last 30 days', zh: '最近 30 天' },
] as const;

const SOURCE_LABELS: Record<string, { en: string; zh: string }> = {
  farm_overlay: { en: "farm's own cost settings", zh: '風場自己的成本設定' },
  registry_derived: { en: 'K13 reference (turbine count / rating from the farm)', zh: 'K13 參考值（機組數與額定功率取自風場）' },
  k13_fallback: { en: 'K13 reference', zh: 'K13 參考值' },
};

interface Props {
  lang: Lang;
}

const FinancePanel: React.FC<Props> = ({ lang }) => {
  const { C } = useTheme();
  const ui = pick(lang);
  const { th, num, thNum, td } = useTableStyles();
  const [days, setDays] = useState<number>(30);
  const [farmEnd, setFarmEnd] = useState<string | null>(null);
  const [finance, setFinance] = useState<FinanceResponse | null>(null);
  const [availability, setAvailability] = useState<AvailabilityResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (rangeDays: number, end: string | null) => {
    setLoading(true);
    setError(null);
    try {
      let start: string | undefined;
      let stop: string | undefined;
      if (end) {
        stop = end;
        start = new Date(Date.parse(end) - rangeDays * 86400_000).toISOString();
      }
      const fin = await fetchFinance(start, stop);
      // 第一次不帶時間：後端給最近 30 天；記下風場時鐘的 end，其他區間從它往前算
      if (!end) {
        setFarmEnd(fin.end);
        if (rangeDays !== 30) {
          await load(rangeDays, fin.end);
          return;
        }
      }
      const avail = await fetchAvailability(fin.start, fin.end);
      setFinance(fin);
      setAvailability(avail);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(30, null);
  }, [load]);

  const choose = (d: number) => {
    setDays(d);
    void load(d, farmEnd);
  };

  const refresh = () => {
    setFarmEnd(null);
    void load(days, null);
  };

  const currency = finance?.rates.currency ?? '';
  const farm = availability?.farm;
  const byTurbine = new Map<string, AvailabilityMetrics>(
    (availability?.turbines ?? []).map(t => [t.turbine_id ?? '', t]),
  );
  const source = finance ? SOURCE_LABELS[finance.rates.source] : undefined;

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        {RANGES.map(r => (
          <Btn
            key={r.days}
            size="sm"
            variant={days === r.days ? 'primary' : 'ghost'}
            ariaPressed={days === r.days}
            onClick={() => choose(r.days)}
          >
            {ui(r.en, r.zh)}
          </Btn>
        ))}
        <Btn size="sm" variant="secondary" onClick={refresh} loading={loading}>
          {ui('Refresh', '重新整理')}
        </Btn>
        {finance && (
          <span style={{ fontSize: 12, color: C.faint }}>
            {ui('Farm clock', '風場時鐘')} {fmtTime(finance.start)} – {fmtTime(finance.end)}
          </span>
        )}
      </div>

      {error !== null && <ErrorNote>{explainError(error, lang)}</ErrorNote>}

      {finance && !finance.enabled && (
        <ErrorNote>
          {ui(
            'The O&M loop is off: no operating record is being kept, so revenue and availability are empty.',
            '運維閉環沒有開：沒有記運轉狀態，收入與可用率都是空的。',
          )}
        </ErrorNote>
      )}

      {finance && (
        <>
          <Card padding={20}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                gap: 20,
              }}
            >
              <Stat size={28} label={ui('Energy', '發電量')} value={fmtEnergy(finance.energy_kwh)} />
              <Stat
                size={28}
                highlight
                label={ui('Revenue', '發電收入')}
                value={fmtMoney(finance.revenue)}
                unit={currency}
              />
              <Stat
                size={28}
                label={ui('Lost (unplanned stops)', '非計畫停機少收')}
                value={fmtMoney(finance.lost_revenue.unplanned)}
                unit={currency}
                valueColor={finance.lost_revenue.unplanned > 0 ? C.warn : undefined}
                hint={`${ui('Planned', '計畫停機')} ${fmtMoney(finance.lost_revenue.planned)} ${currency}`}
              />
              <Stat
                size={28}
                label={ui('O&M expenses', '運維支出')}
                value={fmtMoney(finance.expenses.total)}
                unit={currency}
                hint={`${ui('Labour', '人工')} ${fmtMoney(finance.expenses.labour)} · ${ui('Parts', '料件')} ${fmtMoney(finance.expenses.material)} · ${ui('Equipment', '設備')} ${fmtMoney(finance.expenses.equipment)}`}
              />
              <Stat
                size={28}
                label={ui('Net', '淨額')}
                value={fmtMoney(finance.net)}
                unit={currency}
                valueColor={finance.net < 0 ? C.danger : undefined}
              />
              <Stat
                size={28}
                label={ui('Availability (time)', '時間可用率')}
                value={fmtPct(farm?.time_availability)}
                hint={`${ui('Energy', '發電量可用率')} ${fmtPct(farm?.energy_availability)}`}
              />
            </div>
            {finance.fixed_costs && (
              <div
                data-testid="fixed-costs"
                style={{ marginTop: 14, fontSize: 13, color: C.sub, display: 'grid', gap: 4 }}
              >
                <div>
                  {ui('Fixed costs over', '固定成本：攤')} {finance.fixed_costs.days.toFixed(1)}{' '}
                  {ui('days of operation', '天運轉')} — {ui('staff', '人員')} {fmtMoney(finance.fixed_costs.staff)}（
                  {finance.fixed_costs.technicians} {ui('technicians ×', '位技師 × 年薪')}{' '}
                  {fmtMoney(finance.fixed_costs.yearly_salary)}）· {ui('equipment', '設備')}{' '}
                  {fmtMoney(finance.fixed_costs.equipment)}（
                  {finance.fixed_costs.equipment_items.map(item => item.name).join('、')}）{' '}
                  {currency}
                </div>
                {finance.work_order_labour && !finance.work_order_labour.counted && (
                  <div>
                    {ui(
                      `Work-order hours (${fmtMoney(finance.work_order_labour.amount)} ${currency}) are covered by the salaries and not counted again; major repairs add a crane job under equipment.`,
                      `工單工時折算 ${fmtMoney(finance.work_order_labour.amount)} ${currency}，技師領年薪、已含在人員固定成本裡，不另算；拆大件的修復另記一筆吊車動員在設備裡。`,
                    )}
                  </div>
                )}
              </div>
            )}
            <div style={{ marginTop: 14, fontSize: 12, color: C.faint }}>
              {ui('Tariff', '電價')} {finance.rates.kwh_price} {currency}/kWh · {ui('Labour', '人事費')}{' '}
              {fmtMoney(finance.rates.hourly_labour_rate)} {currency}/{ui('h per person', '人時')} ·{' '}
              {ui('Rates from', '費率來源')}：{source ? ui(source.en, source.zh) : finance.rates.source}
              {finance.fixed_costs?.source === 'onshore_default' &&
                ui(' · fixed costs: onshore assumptions', ' · 固定成本：陸域假設值')}
            </div>
          </Card>

          <Card padding={0}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }} aria-label={ui('Per turbine', '每台機組')}>
                <thead>
                  <tr>
                    <th style={th}>{ui('Turbine', '機組')}</th>
                    <th style={thNum}>{ui('Energy', '發電量')}</th>
                    <th style={thNum}>{ui('Revenue', '收入')}</th>
                    <th style={thNum}>{ui('Lost (unplanned)', '非計畫少收')}</th>
                    <th style={thNum}>{ui('Lost (planned)', '計畫少收')}</th>
                    <th style={thNum}>{ui('Availability', '時間可用率')}</th>
                    <th style={thNum}>{ui('Unplanned stop (h)', '非計畫停機（時）')}</th>
                    <th style={thNum}>{ui('Planned stop (h)', '計畫停機（時）')}</th>
                  </tr>
                </thead>
                <tbody>
                  {finance.turbines.length === 0 && (
                    <tr>
                      <td style={{ ...td, color: C.faint }} colSpan={8}>
                        {ui('No operating record in this period.', '這段時間沒有運轉紀錄。')}
                      </td>
                    </tr>
                  )}
                  {finance.turbines.map(t => {
                    const a = byTurbine.get(t.turbine_id);
                    return (
                      <tr key={t.turbine_id}>
                        <td style={td}>{t.turbine_id}</td>
                        <td style={num}>{fmtEnergy(t.energy_kwh)}</td>
                        <td style={num}>{fmtMoney(t.revenue)}</td>
                        <td style={{ ...num, color: t.lost_unplanned > 0 ? C.warn : C.text }}>
                          {fmtMoney(t.lost_unplanned)}
                        </td>
                        <td style={num}>{fmtMoney(t.lost_planned)}</td>
                        <td style={num}>{fmtPct(a?.time_availability)}</td>
                        <td style={num}>{fmtHours(a?.unplanned_downtime_hours)}</td>
                        <td style={num}>{fmtHours(a?.planned_downtime_hours)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
};

export default FinancePanel;
