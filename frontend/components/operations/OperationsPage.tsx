/**
 * 營運（WMOM-20261127-01）：仿真風場自己運轉時，管理端要看、要設定的東西。
 *
 * 三個分頁：
 *   - 收支與可用率：發電收入、停機少收、運維支出、淨額、可用率（`/api/operations/finance`、`/availability`）
 *   - 自動運轉：機率式故障產生器與模擬維修班的設定（`/api/operations/fault-generator`、`/crew`）
 *   - 實測風況：匯入 CSV、套用、停掉（`/api/config/wind/series`）
 *
 * 大多是主管才能看或改；沒登入或不是主管時，各分頁顯示後端的說明。
 */

import React, { useState } from 'react';
import { Btn, PageHeader } from '../ui';
import FinancePanel from './FinancePanel';
import AutomationPanel from './AutomationPanel';
import WindSeriesPanel from './WindSeriesPanel';
import { pick, type Lang } from './shared';

type Tab = 'finance' | 'automation' | 'wind';

interface Props {
  lang: Lang;
}

const TABS: { id: Tab; en: string; zh: string }[] = [
  { id: 'finance', en: 'Revenue & availability', zh: '收支與可用率' },
  { id: 'automation', en: 'Automatic operation', zh: '自動運轉' },
  { id: 'wind', en: 'Measured wind', zh: '實測風況' },
];

const OperationsPage: React.FC<Props> = ({ lang }) => {
  const ui = pick(lang);
  const [tab, setTab] = useState<Tab>('finance');

  return (
    <>
      <PageHeader
        title={ui('Operations', '營運')}
        sub={ui(
          'The simulated farm running on its own: money, availability, faults, crews and wind.',
          '仿真風場自己運轉：收支、可用率、故障、維修班與風況。',
        )}
      />
      <div style={{ display: 'flex', gap: 6, marginBottom: 16, flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <Btn
            key={t.id}
            variant={tab === t.id ? 'primary' : 'ghost'}
            onClick={() => setTab(t.id)}
            ariaPressed={tab === t.id}
          >
            {ui(t.en, t.zh)}
          </Btn>
        ))}
      </div>
      {tab === 'finance' && <FinancePanel lang={lang} />}
      {tab === 'automation' && <AutomationPanel lang={lang} />}
      {tab === 'wind' && <WindSeriesPanel lang={lang} />}
    </>
  );
};

export default OperationsPage;
