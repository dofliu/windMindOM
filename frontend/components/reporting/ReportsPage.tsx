/**
 * ReportsPage — `/admin/reports` 主入口（WMOM-20260509-09）。
 *
 * Tab 切換：
 *   - monthly：MonthlyReportPanel（month picker → KPI + HTML preview + PDF）
 *   - annual：AnnualBudgetPanel（year picker → 12-month chart + table + PDF）
 *
 * 不接 farm_id 參數 — 內部跑 /api/farms 拿 active_farm_id，與 WorkflowPage 同 pattern。
 */

import React, { useEffect, useState } from 'react';
import { Btn, Card, PageHeader } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import { farmApi } from '../../services/workOrderService';
import { useReports } from '../../hooks/useReports';
import MonthlyReportPanel from './MonthlyReportPanel';
import AnnualBudgetPanel from './AnnualBudgetPanel';

type Lang = 'en' | 'zh';
type Tab = 'monthly' | 'annual';

interface Props {
  lang: Lang;
}

const ReportsPage: React.FC<Props> = ({ lang }) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  // ── Active farm ───────────────────────────────────────────
  // Review fix (must-fix #4)：分離「fetch 尚未完成」與「fetch 完成但無 active farm」
  // 兩個狀態，避免無啟用風場時無限顯示 loading spinner。
  const [farmId, setFarmId] = useState<string | null>(null);
  const [farmName, setFarmName] = useState<string>('');
  const [farmFetchError, setFarmFetchError] = useState<string | null>(null);
  const [farmLoaded, setFarmLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await farmApi.list();
        if (cancelled) return;
        setFarmId(resp.active_farm_id);
        const active = resp.farms.find(f => f.farm_id === resp.active_farm_id);
        setFarmName(active?.name ?? '');
      } catch (e) {
        if (cancelled) return;
        setFarmFetchError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setFarmLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Tab + reports state ─────────────────────────────────────
  const [tab, setTab] = useState<Tab>('monthly');
  const reports = useReports();

  // ── No farm fallback ──
  if (farmFetchError) {
    return (
      <>
        <PageHeader
          title={ui('Reports', '報表')}
          sub={ui('Monthly PDF & annual budget', '月報 PDF 與年度預算')}
        />
        <Card tone="warn" padding={20}>
          <div style={{ color: C.warn, fontSize: 13 }}>
            ⚠ {ui('Failed to load active farm:', '無法載入目前風場：')} {farmFetchError}
          </div>
        </Card>
      </>
    );
  }

  if (!farmLoaded) {
    return (
      <>
        <PageHeader
          title={ui('Reports', '報表')}
          sub={ui('Monthly PDF & annual budget', '月報 PDF 與年度預算')}
        />
        <Card tone="muted" padding={20}>
          <div style={{ color: C.faint, fontSize: 13, textAlign: 'center' }}>
            {ui('Loading active farm…', '載入風場中…')}
          </div>
        </Card>
      </>
    );
  }

  if (!farmId) {
    return (
      <>
        <PageHeader
          title={ui('Reports', '報表')}
          sub={ui('Monthly PDF & annual budget', '月報 PDF 與年度預算')}
        />
        <Card tone="warn" padding={20}>
          <div style={{ color: C.warn, fontSize: 13, textAlign: 'center' }}>
            {ui(
              'No active farm. Please create or activate a farm in the sidebar before generating reports.',
              '目前沒有啟用的風場。請先從左側選單建立或啟用風場後再生成報表。',
            )}
          </div>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={ui('Reports', '報表')}
        sub={
          <span>
            {ui('Active farm', '目前風場')}:{' '}
            <span style={{ color: C.accent, fontWeight: 600 }}>{farmName || farmId}</span>
          </span>
        }
      />

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
        <Btn
          variant={tab === 'monthly' ? 'primary' : 'ghost'}
          onClick={() => setTab('monthly')}
          ariaLabel={ui('Monthly report tab', '月報頁籤')}
          ariaPressed={tab === 'monthly'}
        >
          {ui('Monthly report', '月報')}
        </Btn>
        <Btn
          variant={tab === 'annual' ? 'primary' : 'ghost'}
          onClick={() => setTab('annual')}
          ariaLabel={ui('Annual budget tab', '年度預算頁籤')}
          ariaPressed={tab === 'annual'}
        >
          {ui('Annual budget', '年度預算')}
        </Btn>
      </div>

      {tab === 'monthly' && (
        <MonthlyReportPanel
          farmId={farmId}
          farmName={farmName}
          lang={lang}
          data={reports.monthly.data}
          html={reports.monthly.html}
          loading={reports.monthly.loading}
          error={reports.monthly.error}
          onGenerate={(year, month) =>
            reports.generateMonthly({ farm_id: farmId, year, month, farm_name: farmName })
          }
          onDownloadPdf={(year, month) =>
            reports.downloadMonthlyPdf({ farm_id: farmId, year, month, farm_name: farmName })
          }
        />
      )}

      {tab === 'annual' && (
        <AnnualBudgetPanel
          farmId={farmId}
          farmName={farmName}
          lang={lang}
          data={reports.annual.data}
          loading={reports.annual.loading}
          error={reports.annual.error}
          onGenerate={(year, currentMonth) =>
            reports.generateAnnual({
              farm_id: farmId,
              year,
              farm_name: farmName,
              current_month: currentMonth,
            })
          }
          onDownloadPdf={(year, currentMonth) =>
            reports.downloadAnnualPdf({
              farm_id: farmId,
              year,
              farm_name: farmName,
              current_month: currentMonth,
            })
          }
        />
      )}
    </>
  );
};

export default ReportsPage;
