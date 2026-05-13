/**
 * DemoOrchestratorPage — Layer B placeholder（WMOM-20260509-10）。
 *
 * **狀態：skeleton-only**。M5/M6 接 follow-up issue WMOM-20260513-02 補完整 UI。
 *
 * 設計目的：給客戶 demo 時點一鍵跑完完整 lifecycle（建單 → 派工 → 領料 → 收料 → 完工 →
 * 簽核 → CLOSED + 月報），目前先放 step list + 狀態標籤，**不接 API**。
 *
 * 不註冊到 App router（避免 navigation 污染）；只當 placeholder reference。
 */

import React, { useState } from 'react';
import { Btn, Card, PageHeader, StatusPill } from '../ui';
import type { PillTone } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';

type Lang = 'en' | 'zh';
type StepStatus = 'pending' | 'running' | 'done' | 'skipped';

interface DemoStep {
  id: string;
  labelEn: string;
  labelZh: string;
  status: StepStatus;
}

const INITIAL_STEPS: DemoStep[] = [
  { id: 'fault', labelEn: 'Inject fault scenario (gearbox_temp_high)', labelZh: '注入故障情境（齒輪箱溫度過高）', status: 'pending' },
  { id: 'alarm', labelEn: 'Assert SCADA tag delta + alarm code', labelZh: '驗 SCADA tag 變動 + 告警碼', status: 'pending' },
  { id: 'create_wo', labelEn: 'Create corrective work order', labelZh: '建立矯正性工單', status: 'pending' },
  { id: 'dispatch', labelEn: 'Dispatch + start work', labelZh: '派工 + 開始作業', status: 'pending' },
  { id: 'mr_create', labelEn: 'Create material request', labelZh: '建立領料單', status: 'pending' },
  { id: 'mr_approve', labelEn: 'Approve material request (3 levels)', labelZh: '領料簽核（3 階）', status: 'pending' },
  { id: 'mr_dispatch', labelEn: 'Auto-dispatch (stock -N + ledger estimated)', labelZh: '自動派料（庫存扣 N + 預估帳）', status: 'pending' },
  { id: 'mr_receive', labelEn: 'Receive with actual qty', labelZh: '收料登記實際數量', status: 'pending' },
  { id: 'finish_wo', labelEn: 'Finish WO (ledger -> confirmed)', labelZh: '完工（帳目實際確認）', status: 'pending' },
  { id: 'wo_approve', labelEn: 'Approve work order (2 levels)', labelZh: '工單簽核（2 階）', status: 'pending' },
  { id: 'monthly_report', labelEn: 'Open monthly report PDF', labelZh: '開月報 PDF', status: 'pending' },
];

const statusTone = (s: StepStatus): PillTone => {
  if (s === 'done') return 'ok';
  if (s === 'running') return 'accent';
  if (s === 'skipped') return 'muted';
  return 'muted';
};

const statusLabel = (s: StepStatus, lang: Lang): string => {
  const map: Record<StepStatus, [string, string]> = {
    pending: ['Pending', '待執行'],
    running: ['Running', '執行中'],
    done: ['Done', '完成'],
    skipped: ['Skipped', '跳過'],
  };
  return lang === 'zh' ? map[s][1] : map[s][0];
};

interface Props {
  lang: Lang;
}

const DemoOrchestratorPage: React.FC<Props> = ({ lang }) => {
  const { C } = useTheme();
  const [steps] = useState<DemoStep[]>(INITIAL_STEPS);
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  return (
    <div style={{ padding: 20 }}>
      <PageHeader
        title={ui('Demo Orchestrator', '示範流程編排器')}
        subtitle={ui(
          'One-click full lifecycle replay (M5+ full implementation)',
          '一鍵重播完整生命週期（M5+ 完整實作）',
        )}
      />

      <Card style={{ marginTop: 16 }} tone="warn">
        <div style={{ fontSize: 13, color: C.sub }}>
          {ui(
            'Skeleton placeholder — wired up in WMOM-20260513-02. Step list is static; no API calls.',
            'Skeleton placeholder — 待 WMOM-20260513-02 接完整 API。目前步驟清單為靜態展示。',
          )}
        </div>
      </Card>

      <Card style={{ marginTop: 16 }} padding={0}>
        <ol
          style={{
            margin: 0,
            padding: 0,
            listStyle: 'none',
          }}
        >
          {steps.map((step, idx) => (
            <li
              key={step.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '12px 16px',
                borderBottom:
                  idx === steps.length - 1 ? 'none' : `1px solid ${C.border}`,
              }}
            >
              <div
                style={{
                  width: 28,
                  height: 28,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderRadius: '50%',
                  background: C.panelMuted,
                  color: C.sub,
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                {idx + 1}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, color: C.text }}>
                  {ui(step.labelEn, step.labelZh)}
                </div>
              </div>
              <StatusPill tone={statusTone(step.status)}>
                {statusLabel(step.status, lang)}
              </StatusPill>
            </li>
          ))}
        </ol>
      </Card>

      <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
        <Btn disabled tone="primary">
          {ui('Run Full Demo (M5+)', '執行完整示範（M5+）')}
        </Btn>
        <Btn disabled>{ui('Reset', '重設')}</Btn>
      </div>
    </div>
  );
};

export default DemoOrchestratorPage;
