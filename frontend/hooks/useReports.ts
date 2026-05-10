/**
 * useReports — Reports page state hook（WMOM-20260509-09）。
 *
 * 兩個獨立 sub-state：
 *   - monthly：選 farm/year/month → JSON KPI + HTML preview + PDF download
 *   - annual：選 farm/year → JSON 12 個月 + PDF download
 *
 * 所有 fetch 失敗都丟 error 字串到對應 sub-state，UI 顯示 ErrorBox。
 */

import { useCallback, useState } from 'react';
import {
  type AnnualBudgetData,
  type AnnualQuery,
  type MonthlyQuery,
  type MonthlyReportData,
  downloadBlob,
  reportingApi,
} from '../services/reportingService';

interface MonthlyState {
  loading: boolean;
  error: string | null;
  data: MonthlyReportData | null;
  html: string | null;
}

interface AnnualState {
  loading: boolean;
  error: string | null;
  data: AnnualBudgetData | null;
}

const INITIAL_MONTHLY: MonthlyState = {
  loading: false, error: null, data: null, html: null,
};
const INITIAL_ANNUAL: AnnualState = {
  loading: false, error: null, data: null,
};

export function useReports() {
  const [monthly, setMonthly] = useState<MonthlyState>(INITIAL_MONTHLY);
  const [annual, setAnnual] = useState<AnnualState>(INITIAL_ANNUAL);

  const generateMonthly = useCallback(async (q: MonthlyQuery): Promise<void> => {
    setMonthly({ loading: true, error: null, data: null, html: null });
    try {
      // 平行抓 JSON + HTML（PDF 只在使用者按下載時才打）
      const [data, html] = await Promise.all([
        reportingApi.monthlyJson(q),
        reportingApi.monthlyHtml(q),
      ]);
      setMonthly({ loading: false, error: null, data, html });
    } catch (e) {
      setMonthly({
        loading: false,
        error: e instanceof Error ? e.message : String(e),
        data: null,
        html: null,
      });
    }
  }, []);

  const downloadMonthlyPdf = useCallback(async (q: MonthlyQuery): Promise<void> => {
    const blob = await reportingApi.monthlyPdf(q);
    const safeName = q.farm_id.replace(/[^a-zA-Z0-9_-]/g, '_');
    downloadBlob(blob, `monthly_report_${safeName}_${q.year}${String(q.month).padStart(2, '0')}.pdf`);
  }, []);

  const generateAnnual = useCallback(async (q: AnnualQuery): Promise<void> => {
    setAnnual({ loading: true, error: null, data: null });
    try {
      const data = await reportingApi.annualJson(q);
      setAnnual({ loading: false, error: null, data });
    } catch (e) {
      setAnnual({
        loading: false,
        error: e instanceof Error ? e.message : String(e),
        data: null,
      });
    }
  }, []);

  const downloadAnnualPdf = useCallback(async (q: AnnualQuery): Promise<void> => {
    const blob = await reportingApi.annualPdf(q);
    const safeName = q.farm_id.replace(/[^a-zA-Z0-9_-]/g, '_');
    downloadBlob(blob, `annual_budget_${safeName}_${q.year}.pdf`);
  }, []);

  return {
    monthly,
    annual,
    generateMonthly,
    downloadMonthlyPdf,
    generateAnnual,
    downloadAnnualPdf,
  };
}
