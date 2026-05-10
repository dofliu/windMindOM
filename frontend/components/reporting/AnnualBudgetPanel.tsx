/**
 * AnnualBudgetPanel — A9 年度預算面板（WMOM-20260509-09）。
 *
 * Flow：
 *   1. 選 year + current_month → click Generate
 *   2. 取 12 個月 JSON forecast，畫 recharts BarChart + 詳細 table
 *   3. PDF download 按鈕
 *
 * 月份標籤 method 解讀：
 *   - actual：past month，actual=forecast（已結帳）
 *   - actual_partial：current month，actual 是截至今日的 confirmed 部分；forecast 走歷史平均
 *   - historical_average：future month，純預測
 */

import React, { useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Btn, Card, Field, Select, Stat, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import type { AnnualBudgetData } from '../../services/reportingService';
import { fmtMoneyDecimal } from './formatters';

type Lang = 'en' | 'zh';

interface Props {
  farmId: string;
  farmName: string;
  lang: Lang;
  data: AnnualBudgetData | null;
  loading: boolean;
  error: string | null;
  onGenerate: (year: number, currentMonth: number) => void;
  onDownloadPdf: (year: number, currentMonth: number) => Promise<void>;
}

const MONTHS_EN = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];
const MONTHS_ZH = [
  '1月', '2月', '3月', '4月', '5月', '6月',
  '7月', '8月', '9月', '10月', '11月', '12月',
];

const methodTone = (method: string): 'muted' | 'accent' | 'amber' => {
  if (method === 'actual') return 'accent';
  if (method === 'actual_partial') return 'amber';
  return 'muted';
};

const methodLabel = (method: string, lang: Lang): string => {
  const map: Record<string, [string, string]> = {
    actual: ['Actual', '實際'],
    actual_partial: ['Partial', '當月部分'],
    historical_average: ['Forecast', '預測'],
  };
  const m = map[method];
  return m ? (lang === 'zh' ? m[1] : m[0]) : method;
};

const AnnualBudgetPanel: React.FC<Props> = ({
  farmId,
  farmName,
  lang,
  data,
  loading,
  error,
  onGenerate,
  onDownloadPdf,
}) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const now = useMemo(() => new Date(), []);
  const [year, setYear] = useState<number>(now.getFullYear());
  const [currentMonth, setCurrentMonth] = useState<number>(now.getMonth() + 1);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // Review fix (should-fix #6)：擴大年份範圍給 multi-year O&M 客戶查歷史。
  const yearOpts = useMemo(() => {
    const cur = now.getFullYear();
    const years: number[] = [];
    for (let y = cur - 4; y <= cur + 1; y += 1) years.push(y);
    return years.map(y => ({ value: String(y), label: String(y) }));
  }, [now]);

  const monthOpts = useMemo(
    () => Array.from({ length: 12 }, (_, i) => ({
      value: String(i + 1),
      label: lang === 'zh' ? MONTHS_ZH[i] : MONTHS_EN[i],
    })),
    [lang],
  );

  const chartData = useMemo(() => {
    if (!data) return [];
    // Review fix (nice-to-have #1)：future months 的 actual 用 null 而非 0，
    // recharts 會 skip 該 bar，避免「全 0 actual bars 視覺噪音」。
    return data.months.map(m => ({
      month: lang === 'zh' ? MONTHS_ZH[m.month - 1] : MONTHS_EN[m.month - 1],
      forecast: parseFloat(m.forecast_total),
      actual: m.actual_total != null ? parseFloat(m.actual_total) : null,
    }));
  }, [data, lang]);

  const handleGenerate = () => {
    setDownloadError(null);
    onGenerate(year, currentMonth);
  };

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      await onDownloadPdf(year, currentMonth);
    } catch (e) {
      setDownloadError(e instanceof Error ? e.message : String(e));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <>
      {/* ── Filter bar ────────────────────────────────────────── */}
      <Card padding={16} style={{ marginBottom: 16 }}>
        <div
          style={{
            display: 'flex',
            gap: 16,
            alignItems: 'flex-end',
            flexWrap: 'wrap',
          }}
        >
          <Field label={ui('Year', '年份')}>
            <Select
              value={String(year)}
              options={yearOpts}
              onChange={v => setYear(Number(v))}
              ariaLabel={ui('Year', '年份')}
              width={100}
            />
          </Field>
          <Field
            label={ui('Current month (cutoff)', '當月（結算邊界）')}
            hint={ui(
              'Months ≤ this use confirmed actual; current month uses partial; later months forecast.',
              '此月以前用實際 confirmed；當月用 partial；之後月份用 forecast。',
            )}
          >
            <Select
              value={String(currentMonth)}
              options={monthOpts}
              onChange={v => setCurrentMonth(Number(v))}
              ariaLabel={ui('Current month', '當月')}
              width={120}
            />
          </Field>
          <Btn
            variant="primary"
            onClick={handleGenerate}
            disabled={loading || !farmId}
            ariaLabel={ui('Generate annual budget', '生成年度預算')}
          >
            {loading
              ? ui('Generating…', '生成中…')
              : ui('Generate annual budget', '生成年度預算')}
          </Btn>
          {data && (
            <Btn
              variant="ghost"
              onClick={handleDownload}
              disabled={downloading}
              ariaLabel={ui('Download PDF', '下載 PDF')}
            >
              {downloading
                ? ui('Downloading…', '下載中…')
                : ui('↓ Download PDF', '↓ 下載 PDF')}
            </Btn>
          )}
        </div>
        {error && (
          <div
            style={{
              marginTop: 12,
              padding: '8px 12px',
              background: C.warnSoft,
              border: `1px solid ${C.warn}`,
              borderRadius: 8,
              color: C.warn,
              fontSize: 13,
            }}
          >
            ⚠ {ui('Generate failed', '生成失敗')}: {error}
          </div>
        )}
        {downloadError && (
          <div
            style={{
              marginTop: 8,
              padding: '8px 12px',
              background: C.warnSoft,
              border: `1px solid ${C.warn}`,
              borderRadius: 8,
              color: C.warn,
              fontSize: 13,
            }}
          >
            ⚠ {ui('Download failed', '下載失敗')}: {downloadError}
          </div>
        )}
      </Card>

      {/* ── Empty state ───────────────────────────────────────── */}
      {!data && !loading && !error && (
        <Card tone="muted" padding={32}>
          <div style={{ textAlign: 'center', color: C.faint, fontSize: 13 }}>
            {ui(
              'Pick a year and current month above and click "Generate annual budget".',
              '請於上方選擇年份與當月，並點「生成年度預算」。',
            )}
          </div>
        </Card>
      )}

      {/* ── KPI summary ───────────────────────────────────────── */}
      {data && (
        <Card padding={20} style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 14, fontSize: 13, color: C.sub }}>
            {ui('Farm', '風場')}{': '}
            <span style={{ color: C.accent, fontWeight: 600 }}>{farmName || farmId}</span>
            {'  ·  '}
            {data.year}
            {'  ·  '}
            {ui('Method', '預測法')}{': '}
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
              {data.method}
            </span>
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: 12,
            }}
          >
            <Stat
              label={ui('Annual forecast total', '全年預測合計')}
              value={fmtMoneyDecimal(data.annual_forecast_total)}
              highlight
            />
            <Stat
              label={ui('Annual actual total', '全年實際合計')}
              value={fmtMoneyDecimal(data.annual_actual_total)}
            />
          </div>
          {data.notes && (
            <div style={{ marginTop: 12, fontSize: 12, color: C.faint }}>
              {data.notes}
            </div>
          )}
        </Card>
      )}

      {/* ── Chart ─────────────────────────────────────────────── */}
      {data && chartData.length > 0 && (
        <Card padding={20} style={{ marginBottom: 16 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 14, fontWeight: 600, color: C.text }}>
            {ui('Monthly forecast vs actual', '12 個月預測 vs 實際')}
          </h3>
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={C.border} strokeDasharray="3 3" />
                <XAxis dataKey="month" tick={{ fill: C.sub, fontSize: 12 }} />
                <YAxis
                  tick={{ fill: C.sub, fontSize: 11 }}
                  tickFormatter={(v: number) =>
                    Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`
                  }
                />
                <Tooltip
                  contentStyle={{
                    background: C.panel,
                    border: `1px solid ${C.border}`,
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  formatter={(v: number) => `€${v.toLocaleString()}`}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="forecast" fill={C.accent} name={ui('Forecast', '預測')} />
                <Bar dataKey="actual" fill={C.sub} name={ui('Actual', '實際')} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {/* ── Table ─────────────────────────────────────────────── */}
      {data && (
        <Card padding={20}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 14, fontWeight: 600, color: C.text }}>
            {ui('Monthly breakdown', '月份明細')}
          </h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, minWidth: 720 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${C.border}`, color: C.sub }}>
                  <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 500 }}>
                    {ui('Month', '月份')}
                  </th>
                  <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 500 }}>
                    {ui('Method', '類型')}
                  </th>
                  <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 500 }}>
                    {ui('Material', '物料')}
                  </th>
                  <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 500 }}>
                    {ui('Labour', '人力')}
                  </th>
                  <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 500 }}>
                    {ui('Equipment', '設備')}
                  </th>
                  <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 500 }}>
                    {ui('Revenue loss', '收益損失')}
                  </th>
                  <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 500 }}>
                    {ui('Forecast', '預測')}
                  </th>
                  <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 500 }}>
                    {ui('Actual', '實際')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.months.map(m => (
                  <tr key={m.month} style={{ borderBottom: `1px solid ${C.border}` }}>
                    <td style={{ padding: '6px 8px', color: C.text }}>
                      {lang === 'zh' ? MONTHS_ZH[m.month - 1] : MONTHS_EN[m.month - 1]}
                    </td>
                    <td style={{ padding: '6px 8px' }}>
                      <StatusPill tone={methodTone(m.method)} size="sm">
                        {methodLabel(m.method, lang)}
                      </StatusPill>
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', color: C.sub, fontVariantNumeric: 'tabular-nums' }}>
                      {fmtMoneyDecimal(m.forecast_by_category.material)}
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', color: C.sub, fontVariantNumeric: 'tabular-nums' }}>
                      {fmtMoneyDecimal(m.forecast_by_category.labour)}
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', color: C.sub, fontVariantNumeric: 'tabular-nums' }}>
                      {fmtMoneyDecimal(m.forecast_by_category.equipment)}
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', color: C.sub, fontVariantNumeric: 'tabular-nums' }}>
                      {fmtMoneyDecimal(m.forecast_by_category.revenue_loss)}
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', color: C.text, fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                      {fmtMoneyDecimal(m.forecast_total)}
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', color: C.text, fontVariantNumeric: 'tabular-nums' }}>
                      {fmtMoneyDecimal(m.actual_total)}
                    </td>
                  </tr>
                ))}
                <tr style={{ fontWeight: 600 }}>
                  <td colSpan={6} style={{ padding: '8px', color: C.text }}>
                    {ui('Annual total', '年度合計')}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'right', color: C.accent, fontVariantNumeric: 'tabular-nums' }}>
                    {fmtMoneyDecimal(data.annual_forecast_total)}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'right', color: C.text, fontVariantNumeric: 'tabular-nums' }}>
                    {fmtMoneyDecimal(data.annual_actual_total)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  );
};

export default AnnualBudgetPanel;
