/**
 * ScenarioMountBanner — 情境掛載中的常駐提示（PR C Phase 1，WMOM-20260926-03）。
 *
 * `FarmOverview`/`TurbineDetail` 在 `ScenarioMountContext` 有值時各自渲染一份，提醒使用者
 * 目前看到的是某個已保存情境的凍結快照（唯讀），而非即時資料；並提供就地退出掛載的入口
 * （不必特地導覽到其他頁面才能清空 context）。
 *
 * `error`/`loading` 反映 `ScenarioMountContext` 內建的 `useScenarioMountData` fetch 狀態
 * （code review should-fix：原本這兩個欄位算出來後從未浮現在畫面上——情境在掛載後被刪除、
 * 或網路失敗時，banner 仍自信顯示「情境檢視中」卻是一份空資料，使用者無從得知哪裡出錯）。
 */

import React from 'react';
import { Btn } from './Btn';
import { Card } from './Card';
import { useTheme } from '../../theme/ThemeProvider';

interface Props {
  scenarioName: string;
  onExit: () => void;
  lang?: 'en' | 'zh';
  /** 掛載情境的 fetch 是否仍在進行中（首次掛載瞬間）。 */
  loading?: boolean;
  /** 掛載情境的 fetch 失敗訊息（含情境已被刪除的 404）；非 `null` 時顯示錯誤說明。 */
  error?: string | null;
}

export const ScenarioMountBanner: React.FC<Props> = ({
  scenarioName,
  onExit,
  lang = 'zh',
  loading = false,
  error = null,
}) => {
  const { C } = useTheme();
  const tr = (en: string, zh: string) => (lang === 'zh' ? zh : en);
  return (
    <div role="status" aria-label={`${tr('Scenario view', '情境檢視中')}: ${scenarioName}`}>
      <Card
        tone={error ? 'warn' : 'accent'}
        padding={12}
        style={{ marginBottom: 16 }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <span style={{ fontSize: 13, color: C.text }}>
            {tr('Scenario view', '情境檢視中')}：<strong>{scenarioName}</strong>{' '}
            <span style={{ color: C.sub }}>({tr('read-only', '唯讀')})</span>
            {loading && !error && (
              <span style={{ color: C.sub, marginLeft: 8 }}>{tr('Loading…', '載入中…')}</span>
            )}
          </span>
          <Btn
            size="sm"
            variant="ghost"
            onClick={onExit}
            ariaLabel={tr('Exit scenario view, back to live data', '結束情境檢視，返回即時資料')}
          >
            {tr('Exit scenario view · back to live', '結束情境檢視，返回即時資料')}
          </Btn>
        </div>
        {error && (
          <div style={{ fontSize: 12, color: C.warn, marginTop: 8 }} role="alert">
            {tr(
              'Failed to load this scenario (it may have been deleted, or a network error occurred). ' +
                'The numbers shown below may be empty or stale.',
              '載入這個情境失敗（可能已被刪除，或發生網路錯誤）。下方顯示的數字可能是空的或過期。',
            )}
          </div>
        )}
      </Card>
    </div>
  );
};

export default ScenarioMountBanner;
