/**
 * 風場事件（WMOM-20261126-07，DEC-20261127-10）：電網電壓驟降、電網頻率越界、風向快速變化在即時風場裡依機率發生。
 *
 * 每種事件設「整座風場平均幾天一次」，空白＝不產生；強度與時長沿用目前的設定（後端的 PUT 沒給的欄位會重設成
 * 預設值，所以送完整的設定）。發生過的事件只給主管看：那是答案，外部助理要自己從讀值與事件碼判斷。
 */

import React, { useEffect, useState } from 'react';
import { Btn, Card, Field, Input } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  fetchFarmEvents,
  saveFarmEvents,
  type FarmEventConfig,
  type FarmEventKindConfig,
  type FarmEventState,
} from '../../services/operationsService';
import { ErrorNote, explainError, fmtTime, pick, Toggle, type Lang } from './shared';

interface Props {
  lang: Lang;
}

const FarmEventsCard: React.FC<Props> = ({ lang }) => {
  const { C } = useTheme();
  const ui = pick(lang);
  const [state, setState] = useState<FarmEventState | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [days, setDays] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const show = (next: FarmEventState) => {
    setState(next);
    setEnabled(next.config.enabled);
    setDays(
      Object.fromEntries(
        Object.entries(next.config.kinds).map(([kind, cfg]) => [
          kind,
          cfg.mean_days_between === null ? '' : String(cfg.mean_days_between),
        ]),
      ),
    );
  };

  useEffect(() => {
    let cancelled = false;
    fetchFarmEvents()
      .then(s => !cancelled && show(s))
      .catch(e => !cancelled && setError(e));
    return () => {
      cancelled = true;
    };
  }, []);

  const name = (kind: string) => {
    const info = state?.kinds[kind];
    return info ? ui(info.name_en, info.name_zh) : kind;
  };

  const save = async () => {
    if (!state) return;
    const kinds: FarmEventConfig['kinds'] = {};
    for (const kind of Object.keys(state.config.kinds)) {
      const cfg: FarmEventKindConfig = state.config.kinds[kind];
      const text = (days[kind] ?? '').trim();
      const value = text === '' ? null : Number(text);
      if (value !== null && (!Number.isFinite(value) || value <= 0)) {
        setError(new Error(ui(`${name(kind)}: days must be a positive number`, `${name(kind)}：天數要是正數`)));
        return;
      }
      kinds[kind] = { ...cfg, mean_days_between: value };
    }
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      show(await saveFarmEvents({ ...state.config, enabled, kinds }));
      setSaved(true);
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card padding={20}>
      <div data-testid="farm-events" style={{ display: 'grid', gap: 12 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            gap: 12,
            flexWrap: 'wrap',
          }}
        >
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, color: C.text }}>{ui('Farm events', '風場事件')}</div>
            <div style={{ fontSize: 12, color: C.sub, marginTop: 4 }}>
              {ui(
                'Grid disturbances and rapid wind direction changes happen at random on the live farm. They are not turbine faults; trips they cause are recorded as nuisance.',
                '電網擾動、風向快速變化在即時風場裡隨機發生。它們不是機組故障，造成的跳機在答案裡記成干擾。',
              )}
            </div>
          </div>
          {state && (
            <div style={{ fontSize: 12, color: C.sub }}>
              {ui('Happened so far', '目前為止發生了')}{' '}
              <span style={{ color: C.text, fontWeight: 600 }}>{state.generated}</span> {ui('times', '次')}
            </div>
          )}
        </div>
        {error !== null && <ErrorNote>{explainError(error, lang)}</ErrorNote>}
        {state && (
          <>
            <Toggle
              checked={enabled}
              onChange={v => {
                setEnabled(v);
                setSaved(false);
              }}
              label={ui('Enable farm events', '開啟風場事件')}
            />
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                gap: 14,
              }}
            >
              {Object.keys(state.config.kinds)
                .sort()
                .map(kind => (
                  <Field
                    key={kind}
                    label={`${name(kind)}：${ui('mean days between (whole farm)', '整座風場平均幾天一次')}`}
                    hint={ui('Leave blank to turn this event off', '空白＝不產生這種事件')}
                  >
                    <Input
                      type="number"
                      value={days[kind] ?? ''}
                      onChange={v => {
                        setDays(d => ({ ...d, [kind]: v }));
                        setSaved(false);
                      }}
                      ariaLabel={name(kind)}
                      fullWidth
                    />
                  </Field>
                ))}
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <Btn variant="primary" onClick={save} loading={saving}>
                {ui('Save farm event settings', '儲存風場事件設定')}
              </Btn>
              {saved && <span style={{ fontSize: 12, color: C.ok }}>{ui('Saved', '已儲存')}</span>}
            </div>
            {state.events.length > 0 && (
              <div style={{ fontSize: 12, color: C.sub, display: 'grid', gap: 2 }}>
                <div>{ui('Recent (still being recorded):', '最近發生（還在記錄期間）：')}</div>
                {state.events.map(e => (
                  <div key={`${e.kind}-${e.start}`}>
                    {fmtTime(e.start)} · {name(e.kind)} · {e.magnitude}
                    {' · '}
                    {e.duration_s.toFixed(0)} {ui('s', '秒')}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </Card>
  );
};

export default FarmEventsCard;
