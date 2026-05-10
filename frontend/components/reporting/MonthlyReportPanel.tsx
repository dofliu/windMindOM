/**
 * MonthlyReportPanel — A9 月報生成面板（WMOM-20260509-09）。
 *
 * Flow：
 *   1. 選 year / month → click Generate
 *   2. 同時取 JSON (KPI snapshot) + HTML (iframe preview)
 *   3. PDF download 按鈕（拿 PDF blob 觸發瀏覽器下載）
 *
 * 走 ui 元件庫；無硬寫色；走 theme palette。
 */

import React, { useMemo, useState } from 'react';
import { Btn, Card, Field, Select, Stat } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import type {
  CostBreakdownItem,
  MonthlyReportData,
} from '../../services/reportingService';
import { fmtMoneyDecimal, fmtPct } from './formatters';

type Lang = 'en' | 'zh';

interface Props {
  farmId: string;
  farmName: string;
  lang: Lang;
  data: MonthlyReportData | null;
  html: string | null;
  loading: boolean;
  error: string | null;
  onGenerate: (year: number, month: number) => void;
  onDownloadPdf: (year: number, month: number) => Promise<void>;
}

const MONTHS_EN = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];
const MONTHS_ZH = [
  '一月', '二月', '三月', '四月', '五月', '六月',
  '七月', '八月', '九月', '十月', '十一月', '十二月',
];

const CategoryRow: React.FC<{ item: CostBreakdownItem; lang: Lang }> = ({ item, lang }) => {
  const { C } = useTheme();
  const labelMap: Record<CostBreakdownItem['category'], string> = lang === 'zh'
    ? {
        material: '物料',
        labour: '人力',
        equipment: '設備',
        revenue_loss: '收益損失',
      }
    : {
        material: 'Material',
        labour: 'Labour',
        equipment: 'Equipment',
        revenue_loss: 'Revenue loss',
      };
  return (
    <tr>
      <td style={{ padding: '6px 8px', color: C.text }}>{labelMap[item.category]}</td>
      <td style={{ padding: '6px 8px', textAlign: 'right', color: C.sub, fontVariantNumeric: 'tabular-nums' }}>
        {fmtMoneyDecimal(item.estimated)}
      </td>
      <td style={{ padding: '6px 8px', textAlign: 'right', color: C.sub, fontVariantNumeric: 'tabular-nums' }}>
        {fmtMoneyDecimal(item.confirmed)}
      </td>
      <td style={{ padding: '6px 8px', textAlign: 'right', color: C.text, fontVariantNumeric: 'tabular-nums' }}>
        {fmtMoneyDecimal(item.total)}
      </td>
    </tr>
  );
};

const MonthlyReportPanel: React.FC<Props> = ({
  farmId,
  farmName,
  lang,
  data,
  html,
  loading,
  error,
  onGenerate,
  onDownloadPdf,
}) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  // 預設選擇：上個月
  const now = useMemo(() => new Date(), []);
  const defaultYear = now.getMonth() === 0 ? now.getFullYear() - 1 : now.getFullYear();
  const defaultMonth = now.getMonth() === 0 ? 12 : now.getMonth(); // getMonth() 0-11 → 上月就是 getMonth()
  const [year, setYear] = useState<number>(defaultYear);
  const [month, setMonth] = useState<number>(defaultMonth);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // Review fix (should-fix #6)：3 年範圍對 multi-year O&M 客戶不夠，擴至 5 年
  // 歷史 + 1 年 forecast。未來真要更早可改 input type=number。
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

  // Review fix (must-fix #3)：generate 時清掉舊 download error，避免兩種 error 互相
  // 覆蓋。Display 也改為兩個 error 各自獨立顯示（見下方 JSX）。
  const handleGenerate = () => {
    setDownloadError(null);
    onGenerate(year, month);
  };

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      await onDownloadPdf(year, month);
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
          <Field label={ui('Month', '月份')}>
            <Select
              value={String(month)}
              options={monthOpts}
              onChange={v => setMonth(Number(v))}
              ariaLabel={ui('Month', '月份')}
              width={120}
            />
          </Field>
          <Btn
            variant="primary"
            onClick={handleGenerate}
            disabled={loading || !farmId}
            ariaLabel={ui('Generate report', '生成月報')}
          >
            {loading
              ? ui('Generating…', '生成中…')
              : ui('Generate report', '生成月報')}
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
              'Pick a month above and click "Generate report" to render KPIs and preview the report.',
              '請於上方選擇月份並點「生成月報」，將顯示 KPI 摘要與預覽。',
            )}
          </div>
        </Card>
      )}

      {/* ── KPI cards ─────────────────────────────────────────── */}
      {data && (
        <Card padding={20} style={{ marginBottom: 16 }}>
          <div style={{ marginBottom: 14, fontSize: 13, color: C.sub }}>
            {ui('Farm', '風場')}{': '}
            <span style={{ color: C.accent, fontWeight: 600 }}>{farmName || farmId}</span>
            {'  ·  '}
            {data.year} / {String(data.month).padStart(2, '0')}
            {'  ·  '}
            {ui('Generated at', '產出時間')}{': '}
            <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
              {data.generated_at.replace('T', ' ').slice(0, 19)}
            </span>
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
              gap: 12,
            }}
          >
            <Stat label={ui('Grand total cost', '總成本')} value={fmtMoneyDecimal(data.kpi.grand_total_cost)} />
            <Stat
              label={ui('Confirmed ratio', '實際確認比例')}
              value={fmtPct(data.kpi.confirmed_cost_ratio)}
            />
            <Stat
              label={ui('Work orders finished', '完工工單')}
              value={`${data.kpi.work_orders_finished}`}
            />
            <Stat
              label={ui('Avg repair hrs', '平均維修工時')}
              value={`${data.kpi.average_repair_hours.toFixed(2)} h`}
            />
            <Stat
              label={ui('Time availability', '時間可用率')}
              value={fmtPct(data.kpi.time_availability)}
            />
          </div>
        </Card>
      )}

      {/* ── Cost breakdown table ──────────────────────────────── */}
      {data && (
        <Card padding={20} style={{ marginBottom: 16 }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 14, fontWeight: 600, color: C.text }}>
            {ui('Cost breakdown (4 categories)', '成本明細（4 大類）')}
          </h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${C.border}`, color: C.sub }}>
                <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 500 }}>
                  {ui('Category', '類別')}
                </th>
                <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 500 }}>
                  {ui('Estimated', '估計')}
                </th>
                <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 500 }}>
                  {ui('Confirmed', '確認')}
                </th>
                <th style={{ padding: '6px 8px', textAlign: 'right', fontWeight: 500 }}>
                  {ui('Total', '合計')}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.cost.by_category.map(item => (
                <CategoryRow key={item.category} item={item} lang={lang} />
              ))}
              <tr style={{ borderTop: `1px solid ${C.border}`, fontWeight: 600 }}>
                <td style={{ padding: '8px', color: C.text }}>{ui('Total', '合計')}</td>
                <td style={{ padding: '8px', textAlign: 'right', color: C.text, fontVariantNumeric: 'tabular-nums' }}>
                  {fmtMoneyDecimal(data.cost.estimated_total)}
                </td>
                <td style={{ padding: '8px', textAlign: 'right', color: C.text, fontVariantNumeric: 'tabular-nums' }}>
                  {fmtMoneyDecimal(data.cost.confirmed_total)}
                </td>
                <td style={{ padding: '8px', textAlign: 'right', color: C.accent, fontVariantNumeric: 'tabular-nums' }}>
                  {fmtMoneyDecimal(data.cost.grand_total)}
                </td>
              </tr>
            </tbody>
          </table>
        </Card>
      )}

      {/* ── HTML preview iframe ───────────────────────────────── */}
      {html && (
        <Card padding={0} style={{ marginBottom: 16, overflow: 'hidden' }}>
          <div
            style={{
              padding: '8px 16px',
              background: C.panelMuted,
              borderBottom: `1px solid ${C.border}`,
              fontSize: 12,
              color: C.sub,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span>{ui('HTML preview', 'HTML 預覽')}</span>
            <span style={{ fontSize: 11 }}>
              {ui('Identical layout to the PDF (same Jinja2 template).', '與 PDF 同 layout（共用 Jinja2 template）')}
            </span>
          </div>
          <iframe
            title={ui('Monthly report HTML preview', '月報 HTML 預覽')}
            srcDoc={html}
            // Review fix (must-fix #1)：sandbox 不含 allow-scripts，iframe 內 JS 完全
            // 無法執行；不含 allow-same-origin，iframe 內 DOM 與 parent 隔離（XSS 防護）。
            // CSS 已 inline 在 backend 回傳的 HTML 中，不需 same-origin 也能 render。
            sandbox=""
            style={{
              width: '100%',
              height: 720,
              border: 'none',
              background: '#fff',
            }}
          />
        </Card>
      )}
    </>
  );
};

export default MonthlyReportPanel;
