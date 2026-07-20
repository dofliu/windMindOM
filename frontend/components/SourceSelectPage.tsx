/**
 * SourceSelectPage — 登入後的「選擇資料來源」全屏頁（WMOM-20260719-04, DEC-20260719-01 #3）。
 *
 * 後端開機不再自動跑預設風場（修「一進系統就自動產資料」）。使用者登入後先在此挑要幹嘛，
 * 選定才啟動對應來源 / 路由：
 *   - 實際資料對接（live）→ 連 OPC/Modbus 讀真實 SCADA → 總覽
 *   - 即時模擬（simulation）→ 物理模型即時自由跑 → 總覽
 *   - 產生新情境（simulation + 路由情境頁）→ 設定風況/時長/故障批次生成
 *   - 調閱過去情境（view，不啟動任何來源）→ 打開先前情境觀察分析
 *
 * 本元件只負責呈現 + 回呼 `onSelect(cardId)`；實際「打 /api/source/select + 路由」由 App 決定。
 */

import React, { useState } from 'react';
import { Btn, Card } from './ui';
import { useTheme } from '../theme/ThemeProvider';

export type SourceCardId = 'live' | 'simulation' | 'scenario' | 'observe';

interface SourceCard {
  id: SourceCardId;
  icon: string;
  titleZh: string;
  titleEn: string;
  descZh: string;
  descEn: string;
}

const CARDS: SourceCard[] = [
  {
    id: 'live',
    icon: '📡',
    titleZh: '實際資料對接',
    titleEn: 'Connect real data',
    descZh: '連接 OPC DA / Modbus，讀取現場真實 SCADA 資料。',
    descEn: 'Connect OPC DA / Modbus to stream real SCADA data.',
  },
  {
    id: 'simulation',
    icon: '▶️',
    titleZh: '即時模擬',
    titleEn: 'Live simulation',
    descZh: '以物理模型即時自由跑，產生連續資料（無實場也能 demo）。',
    descEn: 'Run the physics model live for continuous data (demo without a real site).',
  },
  {
    id: 'scenario',
    icon: '🧪',
    titleZh: '產生新情境',
    titleEn: 'Generate a scenario',
    descZh: '設定風況 + 時長 + 故障排程，一次生成可重現資料集來演練運維。',
    descEn: 'Define wind + duration + faults, batch-generate a reproducible dataset to practice O&M.',
  },
  {
    id: 'observe',
    icon: '📂',
    titleZh: '調閱過去情境',
    titleEn: 'Open a past scenario',
    descZh: '打開先前產生過的情境來觀察分析（不啟動任何即時來源）。',
    descEn: 'Open a previously generated scenario to observe & analyze (starts no live source).',
  },
];

interface Props {
  lang?: 'en' | 'zh';
  onSelect: (id: SourceCardId) => void | Promise<void>;
  onToggleLang?: () => void;
}

const SourceSelectPage: React.FC<Props> = ({ lang = 'zh', onSelect, onToggleLang }) => {
  const { C } = useTheme();
  const u = (en: string, zh: string) => (lang === 'zh' ? zh : en);
  const [busy, setBusy] = useState<SourceCardId | null>(null);

  const handle = async (id: SourceCardId) => {
    if (busy) return;
    setBusy(id);
    try {
      await onSelect(id);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div
      style={{
        background: C.bg,
        color: C.text,
        minHeight: '100vh',
        fontFamily: 'Manrope, system-ui, sans-serif',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '32px 20px',
      }}
    >
      <div style={{ width: '100%', maxWidth: 880 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: C.text }}>
            {u('Choose a data source', '選擇資料來源')}
          </div>
          {onToggleLang && (
            <Btn size="sm" variant="ghost" onClick={onToggleLang} ariaLabel={u('Toggle language', '切換語言')}>
              {lang === 'zh' ? 'EN' : '中'}
            </Btn>
          )}
        </div>
        <div style={{ fontSize: 13, color: C.sub, marginBottom: 22 }}>
          {u(
            'Pick how you want to work — nothing runs until you choose.',
            '先選這次要怎麼用——在你選擇前，系統不會自動產生任何資料。',
          )}
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 16,
          }}
        >
          {CARDS.map(card => (
            <Card key={card.id} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ fontSize: 28, lineHeight: 1 }} aria-hidden>
                {card.icon}
              </div>
              <div style={{ fontSize: 16, fontWeight: 600, color: C.text }}>
                {u(card.titleEn, card.titleZh)}
              </div>
              <div style={{ fontSize: 13, color: C.sub, flex: 1, lineHeight: 1.5 }}>
                {u(card.descEn, card.descZh)}
              </div>
              <Btn
                variant="primary"
                fullWidth
                onClick={() => handle(card.id)}
                disabled={busy !== null}
                ariaLabel={u(`Select: ${card.titleEn}`, `選擇：${card.titleZh}`)}
              >
                {busy === card.id ? u('Starting…', '啟動中…') : u('Select', '選擇')}
              </Btn>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
};

export default SourceSelectPage;
