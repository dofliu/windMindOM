/**
 * 實測風況（WMOM-20261127-01）：匯入 CSV、看匯入過的序列、套用到即時風場、停掉回到模型（DEC-20261127-03）。
 *
 * 匯入與套用分開：匯入只存進風場資料庫；套用後風場從下一步開始依序列運轉（從當時的風速漸變過去）。手動的
 * 風況設定優先於實測序列；「回到模型的風況」會一併停掉序列與手動設定。
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Btn, Card, Field, Input, Select } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  applyWindSeries,
  clearWind,
  deleteWindSeries,
  fetchWindStatus,
  importWindSeries,
  listWindSeries,
  type WindAlignment,
  type WindAtEnd,
  type WindSeriesItem,
  type WindStatus,
} from '../../services/operationsService';
import { ErrorNote, explainError, fmtTime, pick, useTableStyles, type Lang } from './shared';

interface Props {
  lang: Lang;
}

const QUANTITY_LABELS: Record<string, { en: string; zh: string }> = {
  wind_speed: { en: 'speed', zh: '風速' },
  wind_direction: { en: 'direction', zh: '風向' },
  ambient_temp: { en: 'temperature', zh: '氣溫' },
  turbulence_intensity: { en: 'TI', zh: '紊流強度' },
  humidity: { en: 'humidity', zh: '濕度' },
  pressure_hpa: { en: 'pressure', zh: '氣壓' },
};

function fmtStep(seconds: number): string {
  if (seconds >= 3600 && seconds % 3600 === 0) return `${seconds / 3600} h`;
  if (seconds >= 60) return `${Math.round(seconds / 60)} min`;
  return `${seconds} s`;
}

const WindSeriesPanel: React.FC<Props> = ({ lang }) => {
  const { C } = useTheme();
  const ui = pick(lang);
  const { th, td, num, thNum } = useTableStyles();

  const [status, setStatus] = useState<WindStatus | null>(null);
  const [series, setSeries] = useState<WindSeriesItem[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // 匯入
  const [name, setName] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [heightM, setHeightM] = useState('');
  const [timezone, setTimezone] = useState('');
  const [imported, setImported] = useState<WindSeriesItem | null>(null);

  // 套用
  const [alignment, setAlignment] = useState<WindAlignment>('replay');
  const [atEnd, setAtEnd] = useState<WindAtEnd>('loop');
  const [offsetHours, setOffsetHours] = useState('0');

  const reload = useCallback(async () => {
    const [st, list] = await Promise.allSettled([fetchWindStatus(), listWindSeries()]);
    if (st.status === 'fulfilled') setStatus(st.value);
    if (list.status === 'fulfilled') setSeries(list.value.series);
    const failed = [st, list].find(r => r.status === 'rejected') as PromiseRejectedResult | undefined;
    setError(failed ? failed.reason : null);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const run = async (key: string, action: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    try {
      await action();
      await reload();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const doImport = () =>
    run('import', async () => {
      if (!file) throw new Error(ui('Choose a CSV file first.', '請先選一個 CSV 檔。'));
      const height = heightM.trim() === '' ? undefined : Number(heightM);
      if (height !== undefined && !(height > 0)) {
        throw new Error(ui('Measurement height must be a positive number.', '量測高度要是大於 0 的數字。'));
      }
      const text = await file.text();
      const made = await importWindSeries({
        name: name.trim() || file.name,
        csv: text,
        heightM: height,
        timezone: timezone.trim() || undefined,
      });
      setImported(made);
      setFile(null);
      setName('');
    });

  const doApply = (id: number) =>
    run(`apply-${id}`, async () => {
      const offset = Number(offsetHours || '0');
      if (!(offset >= 0)) throw new Error(ui('Start offset must be ≥ 0.', '從第幾小時開始要 ≥ 0。'));
      setStatus(await applyWindSeries(id, { alignment, atEnd, startOffsetHours: offset }));
    });

  const doDelete = (item: WindSeriesItem) => {
    const sure = typeof window !== 'undefined' && typeof window.confirm === 'function'
      ? window.confirm(ui(`Delete "${item.name}"?`, `刪除「${item.name}」？`))
      : true;
    if (!sure) return;
    void run(`delete-${item.id}`, () => deleteWindSeries(item.id));
  };

  const quantities = (keys: string[]) =>
    keys.map(k => (QUANTITY_LABELS[k] ? ui(QUANTITY_LABELS[k].en, QUANTITY_LABELS[k].zh) : k)).join('、');

  const measured = status?.measured ?? null;
  const modeLabel =
    status?.mode === 'measured'
      ? ui('Measured series', '依實測序列')
      : status?.mode === 'manual'
        ? ui(`Manual (${status.profile ?? ''})`, `手動設定（${status.profile ?? ''}）`)
        : ui('Model', '模型的風況');

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {error !== null && <ErrorNote>{explainError(error, lang)}</ErrorNote>}

      <Card padding={20}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 12, color: C.sub }}>{ui('Wind now follows', '目前的風況')}</div>
            <div style={{ fontSize: 18, fontWeight: 600, color: C.text, marginTop: 4 }} data-testid="wind-mode">
              {status ? modeLabel : '—'}
            </div>
            {measured && (
              <div style={{ fontSize: 12, color: C.sub, marginTop: 6 }}>
                {measured.name} · {measured.alignment === 'replay' ? ui('replay', '從現在開始播') : ui('absolute time', '絕對時間')} ·{' '}
                {ui('at the end', '播完')}：
                {measured.at_end === 'loop' ? ui('loop', '從頭再播') : measured.at_end === 'hold' ? ui('hold', '停在最後一筆') : ui('back to the model', '回到模型')}
                {measured.pending ? ` · ${ui('applies at the next step', '下一步套用')}` : ''}
                {measured.started_at ? ` · ${ui('started', '開始於')} ${fmtTime(measured.started_at)}` : ''}
              </div>
            )}
          </div>
          <Btn
            variant="secondary"
            onClick={() => run('clear', clearWind)}
            loading={busy === 'clear'}
            disabled={!status || status.mode === 'auto'}
          >
            {ui('Back to the model wind', '回到模型的風況')}
          </Btn>
        </div>
      </Card>

      <Card padding={20}>
        <div style={{ fontSize: 15, fontWeight: 600, color: C.text }}>{ui('Import a measured series', '匯入實測序列')}</div>
        <div style={{ fontSize: 12, color: C.sub, marginTop: 4, lineHeight: 1.6 }}>
          {ui(
            'CSV with column names in the first row. Time and wind speed are required; direction, temperature, TI (or wind-speed std), humidity and pressure (hPa) are optional. Times without a time zone are read in the farm time zone.',
            'CSV，第一列是欄名。時間與風速必填；風向、氣溫、紊流強度（或風速標準差）、濕度、氣壓（hPa）可有可無。沒有時區的時間視為風場時區。',
          )}
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 14,
            marginTop: 14,
          }}
        >
          <Field label={ui('CSV file', 'CSV 檔')}>
            <input
              type="file"
              accept=".csv,text/csv"
              aria-label={ui('CSV file', 'CSV 檔')}
              onChange={e => setFile(e.target.files?.[0] ?? null)}
              style={{ fontSize: 13, color: C.text }}
            />
          </Field>
          <Field label={ui('Name', '名稱')} hint={ui('Defaults to the file name.', '沒填就用檔名。')}>
            <Input value={name} onChange={setName} ariaLabel={ui('Name', '名稱')} fullWidth />
          </Field>
          <Field
            label={ui('Measurement height (m)', '量測高度（m）')}
            hint={ui('Optional: scales the speed to hub height.', '選填：給了會換算到輪轂高度。')}
          >
            <Input type="number" value={heightM} onChange={setHeightM} ariaLabel={ui('Measurement height', '量測高度')} fullWidth />
          </Field>
          <Field label={ui('Time zone', '時區')} hint={ui('Optional, e.g. UTC. Default: the farm’s.', '選填，例：UTC。預設是風場時區。')}>
            <Input value={timezone} onChange={setTimezone} ariaLabel={ui('Time zone', '時區')} fullWidth />
          </Field>
        </div>
        <div style={{ marginTop: 16 }}>
          <Btn variant="primary" onClick={doImport} loading={busy === 'import'} disabled={!file}>
            {ui('Import', '匯入')}
          </Btn>
        </div>
        {imported && (
          <div style={{ marginTop: 14, fontSize: 13, color: C.text, lineHeight: 1.7 }} data-testid="import-summary">
            {ui('Imported', '已匯入')}「{imported.name}」：{imported.summary.rows} {ui('rows', '筆')}，
            {fmtTime(imported.summary.start)} – {fmtTime(imported.summary.end)}，{ui('every', '每')} {fmtStep(imported.summary.step_s)}，
            {quantities(imported.summary.quantities)}。
            {imported.summary.long_gaps > 0 &&
              ` ${ui(`${imported.summary.long_gaps} long gaps fall back to the model.`, `${imported.summary.long_gaps} 段缺太久，那幾段回到模型。`)}`}
            {(imported.summary.warnings ?? []).map(w => (
              <div key={w} style={{ color: C.warn }}>⚠ {w}</div>
            ))}
          </div>
        )}
      </Card>

      <Card padding={20}>
        <div style={{ fontSize: 15, fontWeight: 600, color: C.text }}>{ui('How to apply', '套用方式')}</div>
        <div style={{ fontSize: 12, color: C.sub, marginTop: 4 }}>
          {ui(
            'Used when you press Apply on a series below. The farm switches at the next step, blending from the current wind.',
            '按下面序列的「套用」時用這些設定。風場從下一步開始換，從當時的風速漸變過去。',
          )}
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 14,
            marginTop: 14,
          }}
        >
          <Field label={ui('Time alignment', '對時方式')}>
            <Select
              value={alignment}
              onChange={v => setAlignment(v as WindAlignment)}
              ariaLabel={ui('Time alignment', '對時方式')}
              fullWidth
              options={[
                { value: 'replay', label: ui('Replay from now', '從現在開始播') },
                { value: 'absolute', label: ui('Absolute (farm time = series time)', '絕對時間（模擬時間＝序列時間）') },
              ]}
            />
          </Field>
          <Field label={ui('At the end of the series', '播完之後')}>
            <Select
              value={atEnd}
              onChange={v => setAtEnd(v as WindAtEnd)}
              ariaLabel={ui('At the end of the series', '播完之後')}
              fullWidth
              options={[
                { value: 'loop', label: ui('Loop', '從頭再播') },
                { value: 'hold', label: ui('Hold the last value', '停在最後一筆') },
                { value: 'auto', label: ui('Back to the model', '回到模型') },
              ]}
            />
          </Field>
          <Field label={ui('Start this many hours in (replay)', '從第幾小時開始（重播）')}>
            <Input
              type="number"
              value={offsetHours}
              onChange={setOffsetHours}
              ariaLabel={ui('Start offset hours', '從第幾小時開始')}
              fullWidth
            />
          </Field>
        </div>
      </Card>

      <Card padding={0}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }} aria-label={ui('Imported series', '匯入過的序列')}>
            <thead>
              <tr>
                <th style={th}>{ui('Name', '名稱')}</th>
                <th style={th}>{ui('Period', '期間')}</th>
                <th style={thNum}>{ui('Rows', '筆數')}</th>
                <th style={th}>{ui('Every', '間隔')}</th>
                <th style={th}>{ui('Quantities', '量')}</th>
                <th style={thNum}>{ui('Mean speed', '平均風速')}</th>
                <th style={th} />
              </tr>
            </thead>
            <tbody>
              {series.length === 0 && (
                <tr>
                  <td style={{ ...td, color: C.faint }} colSpan={7}>
                    {ui('Nothing imported yet.', '還沒有匯入任何序列。')}
                  </td>
                </tr>
              )}
              {series.map(item => {
                const playing = measured?.series_id === item.id;
                return (
                  <tr key={item.id}>
                    <td style={td}>
                      {item.name}
                      {playing && (
                        <span style={{ marginLeft: 8, fontSize: 11, color: C.accent }}>{ui('playing', '播放中')}</span>
                      )}
                    </td>
                    <td style={td}>
                      {item.summary.start.slice(0, 10)} – {item.summary.end.slice(0, 10)}
                    </td>
                    <td style={num}>{item.summary.rows.toLocaleString('en-US')}</td>
                    <td style={td}>{fmtStep(item.summary.step_s)}</td>
                    <td style={td}>{quantities(item.summary.quantities)}</td>
                    <td style={num}>{item.summary.wind_speed_mean.toFixed(1)} m/s</td>
                    <td style={{ ...td, textAlign: 'right' }}>
                      <span style={{ display: 'inline-flex', gap: 6 }}>
                        <Btn size="sm" variant="primary" onClick={() => doApply(item.id)} loading={busy === `apply-${item.id}`}>
                          {ui('Apply', '套用')}
                        </Btn>
                        <Btn size="sm" variant="ghost" onClick={() => doDelete(item)} loading={busy === `delete-${item.id}`}>
                          {ui('Delete', '刪除')}
                        </Btn>
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};

export default WindSeriesPanel;
