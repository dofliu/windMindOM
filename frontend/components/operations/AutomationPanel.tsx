/**
 * 自動運轉（WMOM-20261127-01）：機率式故障產生器與模擬維修班的設定（DEC-20261126-08）、自動定檢計畫
 * （WMOM-20261127-03，DEC-20261127-05），以及風場事件（WMOM-20261126-07，`FarmEventsCard`）。
 *
 * 兩者都存在風場的資料庫、重啟後照舊；只作用在即時模擬。後端的 PUT 沒給的欄位會用預設值，所以存的時候送
 * 完整的設定——畫面上沒列的欄位（情境 / 機組權重、耗損參考值）沿用目前的值。
 */

import React, { useEffect, useState } from 'react';
import { Btn, Card, Field, Input } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  fetchCrew,
  fetchFaultGenerator,
  fetchInspectionPlan,
  saveCrew,
  saveFaultGenerator,
  saveInspectionPlan,
  type CrewConfig,
  type FaultGeneratorConfig,
  type FaultGeneratorState,
  type InspectionPlanState,
} from '../../services/operationsService';
import { ErrorNote, explainError, fmtTime, pick, Toggle, useTableStyles, type Lang } from './shared';
import FarmEventsCard from './FarmEventsCard';

interface Props {
  lang: Lang;
}

type NumberDraft = Record<string, string>;

function toNumber(text: string): number {
  return text.trim() === '' ? NaN : Number(text);
}

const GENERATOR_FIELDS: { key: keyof FaultGeneratorConfig; en: string; zh: string; hintEn: string; hintZh: string; int?: boolean }[] = [
  {
    key: 'mean_days_between_faults',
    en: 'Mean days between faults (per turbine)',
    zh: '平均幾天一個故障（每台機組）',
    hintEn: 'Default 30: about one fault every two days on 14 turbines.',
    hintZh: '預設 30：14 台約兩天一個。',
  },
  {
    key: 'min_hours_to_full',
    en: 'Fastest hours to full severity',
    zh: '最快幾小時劣化到最嚴重',
    hintEn: 'Each fault picks a speed between the fastest and the slowest.',
    hintZh: '每個故障在最快與最慢之間抽一個速度。',
  },
  {
    key: 'max_hours_to_full',
    en: 'Slowest hours to full severity',
    zh: '最慢幾小時劣化到最嚴重',
    hintEn: '',
    hintZh: '',
  },
  {
    key: 'max_active_per_turbine',
    en: 'Faults at the same time (per turbine)',
    zh: '一台機組同時最多幾個故障',
    hintEn: 'Latent faults (full severity, no alarm) do not count.',
    hintZh: '潛伏的故障（到頂卻沒有警報）不算。',
    int: true,
  },
  {
    key: 'wear_gain',
    en: 'Wear gain',
    zh: '耗損放大',
    hintEn: 'How much fatigue / fouling raises the rate of related faults.',
    hintZh: '疲勞與結垢讓相關故障增加的倍數。',
  },
  {
    key: 'seed',
    en: 'Random seed',
    zh: '亂數種子',
    hintEn: 'Changing it starts a different sequence of faults.',
    hintZh: '換了之後的故障序列就不同。',
    int: true,
  },
];

const CREW_FIELDS: { key: keyof CrewConfig; en: string; zh: string; int?: boolean }[] = [
  { key: 'response_minutes', en: 'Minutes before the crew takes an order', zh: '工單建立後幾分鐘維修班接手' },
  { key: 'repair_minutes', en: 'Repair minutes', zh: '故障維修要幾分鐘' },
  { key: 'inspection_minutes', en: 'Inspection / maintenance minutes', zh: '定檢 / 保養要幾分鐘' },
  { key: 'crews', en: 'Crews working at the same time', zh: '同時幾組在施工', int: true },
];

const AutomationPanel: React.FC<Props> = ({ lang }) => {
  const { C } = useTheme();
  const ui = pick(lang);

  const [generator, setGenerator] = useState<FaultGeneratorState | null>(null);
  const [genEnabled, setGenEnabled] = useState(false);
  const [genDraft, setGenDraft] = useState<NumberDraft>({});
  const [genError, setGenError] = useState<unknown>(null);
  const [genSaving, setGenSaving] = useState(false);
  const [genSaved, setGenSaved] = useState(false);

  const [crew, setCrew] = useState<CrewConfig | null>(null);
  const [crewEnabled, setCrewEnabled] = useState(false);
  const [crewClose, setCrewClose] = useState(true);
  const [crewDraft, setCrewDraft] = useState<NumberDraft>({});
  const [crewError, setCrewError] = useState<unknown>(null);
  const [crewSaving, setCrewSaving] = useState(false);
  const [crewSaved, setCrewSaved] = useState(false);

  const [plan, setPlan] = useState<InspectionPlanState | null>(null);
  const [planEnabled, setPlanEnabled] = useState(false);
  const [planDays, setPlanDays] = useState('');
  const [planError, setPlanError] = useState<unknown>(null);
  const [planSaving, setPlanSaving] = useState(false);
  const [planSaved, setPlanSaved] = useState(false);
  const table = useTableStyles();

  const showPlan = (state: InspectionPlanState) => {
    setPlan(state);
    setPlanEnabled(state.config.enabled);
    setPlanDays(String(state.config.interval_days));
  };

  const showGenerator = (state: FaultGeneratorState) => {
    setGenerator(state);
    setGenEnabled(state.config.enabled);
    setGenDraft(Object.fromEntries(GENERATOR_FIELDS.map(f => [f.key, String(state.config[f.key])])));
  };

  const showCrew = (config: CrewConfig) => {
    setCrew(config);
    setCrewEnabled(config.enabled);
    setCrewClose(config.close_after_finish);
    setCrewDraft(Object.fromEntries(CREW_FIELDS.map(f => [f.key, String(config[f.key])])));
  };

  useEffect(() => {
    let cancelled = false;
    fetchFaultGenerator()
      .then(s => !cancelled && showGenerator(s))
      .catch(e => !cancelled && setGenError(e));
    fetchCrew()
      .then(r => !cancelled && showCrew(r.config))
      .catch(e => !cancelled && setCrewError(e));
    fetchInspectionPlan()
      .then(s => !cancelled && showPlan(s))
      .catch(e => !cancelled && setPlanError(e));
    return () => {
      cancelled = true;
    };
  }, []);

  const saveGenerator = async () => {
    if (!generator) return;
    const next: FaultGeneratorConfig = { ...generator.config, enabled: genEnabled };
    for (const f of GENERATOR_FIELDS) {
      const value = toNumber(genDraft[f.key] ?? '');
      if (!Number.isFinite(value) || (f.int && !Number.isInteger(value))) {
        setGenError(new Error(ui(`${f.en}: not a valid number`, `${f.zh}：不是有效的數字`)));
        return;
      }
      (next as unknown as Record<string, number | boolean>)[f.key] = value;
    }
    setGenSaving(true);
    setGenError(null);
    setGenSaved(false);
    try {
      showGenerator(await saveFaultGenerator(next));
      setGenSaved(true);
    } catch (e) {
      setGenError(e);
    } finally {
      setGenSaving(false);
    }
  };

  const saveCrewSettings = async () => {
    if (!crew) return;
    const next: CrewConfig = { ...crew, enabled: crewEnabled, close_after_finish: crewClose };
    for (const f of CREW_FIELDS) {
      const value = toNumber(crewDraft[f.key] ?? '');
      if (!Number.isFinite(value) || (f.int && !Number.isInteger(value))) {
        setCrewError(new Error(ui(`${f.en}: not a valid number`, `${f.zh}：不是有效的數字`)));
        return;
      }
      (next as unknown as Record<string, number | boolean>)[f.key] = value;
    }
    setCrewSaving(true);
    setCrewError(null);
    setCrewSaved(false);
    try {
      showCrew((await saveCrew(next)).config);
      setCrewSaved(true);
    } catch (e) {
      setCrewError(e);
    } finally {
      setCrewSaving(false);
    }
  };

  const savePlan = async () => {
    if (!plan) return;
    const days = toNumber(planDays);
    if (!Number.isInteger(days) || days < 1 || days > 730) {
      setPlanError(new Error(ui('Interval: a whole number of days, 1–730', '週期：1–730 的整數天數')));
      return;
    }
    setPlanSaving(true);
    setPlanError(null);
    setPlanSaved(false);
    try {
      showPlan(await saveInspectionPlan({ ...plan.config, enabled: planEnabled, interval_days: days }));
      setPlanSaved(true);
    } catch (e) {
      setPlanError(e);
    } finally {
      setPlanSaving(false);
    }
  };

  const grid: React.CSSProperties = {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
    gap: 14,
    marginTop: 14,
  };

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <Card padding={20}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, color: C.text }}>
              {ui('Fault generator', '機率式故障產生器')}
            </div>
            <div style={{ fontSize: 12, color: C.sub, marginTop: 4 }}>
              {ui(
                'Faults appear at random on the live farm; wear raises the rate. Saved in the farm database.',
                '即時風場的機組隨機發生故障，耗損越大越常發生。設定存在風場資料庫。',
              )}
            </div>
          </div>
          {generator && (
            <div style={{ fontSize: 12, color: C.sub }}>
              {ui('Generated so far', '目前為止產生了')}{' '}
              <span style={{ color: C.text, fontWeight: 600 }}>{generator.generated}</span> {ui('faults', '個故障')}
            </div>
          )}
        </div>
        {genError !== null && (
          <div style={{ marginTop: 12 }}>
            <ErrorNote>{explainError(genError, lang)}</ErrorNote>
          </div>
        )}
        {generator && (
          <>
            <div style={{ marginTop: 14 }}>
              <Toggle checked={genEnabled} onChange={setGenEnabled} label={ui('Enabled', '開啟')} />
            </div>
            <div style={grid}>
              {GENERATOR_FIELDS.map(f => (
                <Field key={f.key} label={ui(f.en, f.zh)} hint={ui(f.hintEn, f.hintZh) || undefined}>
                  <Input
                    type="number"
                    value={genDraft[f.key] ?? ''}
                    onChange={v => {
                      setGenDraft(d => ({ ...d, [f.key]: v }));
                      setGenSaved(false);
                    }}
                    ariaLabel={ui(f.en, f.zh)}
                    fullWidth
                  />
                </Field>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 16 }}>
              <Btn variant="primary" onClick={saveGenerator} loading={genSaving}>
                {ui('Save generator settings', '儲存產生器設定')}
              </Btn>
              {genSaved && <span style={{ fontSize: 12, color: C.ok }}>{ui('Saved', '已儲存')}</span>}
            </div>
          </>
        )}
      </Card>

      <FarmEventsCard lang={lang} />

      <Card padding={20}>
        <div style={{ fontSize: 15, fontWeight: 600, color: C.text }}>{ui('Simulated crew', '模擬維修班')}</div>
        <div style={{ fontSize: 12, color: C.sub, marginTop: 4 }}>
          {ui(
            'Takes work orders nobody has started, works them and closes them. Times are farm-clock minutes; orders a person started are left alone.',
            '沒人處理的工單由維修班接手、施工、結案。時間是風場時鐘的分鐘；人已經開工的工單不碰。',
          )}
        </div>
        {crewError !== null && (
          <div style={{ marginTop: 12 }}>
            <ErrorNote>{explainError(crewError, lang)}</ErrorNote>
          </div>
        )}
        {crew && (
          <>
            <div style={{ marginTop: 14, display: 'flex', gap: 20, flexWrap: 'wrap' }}>
              <Toggle checked={crewEnabled} onChange={setCrewEnabled} label={ui('Enabled', '開啟')} />
              <Toggle
                checked={crewClose}
                onChange={setCrewClose}
                label={ui('Close the order when finished', '完工後直接結案')}
              />
            </div>
            <div style={grid}>
              {CREW_FIELDS.map(f => (
                <Field key={f.key} label={ui(f.en, f.zh)}>
                  <Input
                    type="number"
                    value={crewDraft[f.key] ?? ''}
                    onChange={v => {
                      setCrewDraft(d => ({ ...d, [f.key]: v }));
                      setCrewSaved(false);
                    }}
                    ariaLabel={ui(f.en, f.zh)}
                    fullWidth
                  />
                </Field>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 16 }}>
              <Btn variant="primary" onClick={saveCrewSettings} loading={crewSaving}>
                {ui('Save crew settings', '儲存維修班設定')}
              </Btn>
              {crewSaved && <span style={{ fontSize: 12, color: C.ok }}>{ui('Saved', '已儲存')}</span>}
            </div>
          </>
        )}
      </Card>

      <Card padding={20}>
        <div style={{ fontSize: 15, fontWeight: 600, color: C.text }}>
          {ui('Routine inspection plan', '自動定檢計畫')}
        </div>
        <div style={{ fontSize: 12, color: C.sub, marginTop: 4 }}>
          {ui(
            'Opens an inspection work order for each turbine every few days (farm clock, staggered across the farm). Finishing it repairs the faults on that turbine, including latent ones that raise no alarm. A turbine that already has an open inspection is not given another.',
            '每台機組每隔幾天（風場時鐘、全場錯開）開一張定檢工單；完工修掉那台機組的故障，包括沒有警報的潛伏故障。已經有未結案定檢工單的機組不再開。',
          )}
        </div>
        {planError !== null && (
          <div style={{ marginTop: 12 }}>
            <ErrorNote>{explainError(planError, lang)}</ErrorNote>
          </div>
        )}
        {plan && (
          <>
            <div style={{ marginTop: 14 }}>
              <Toggle checked={planEnabled} onChange={setPlanEnabled} label={ui('Enabled', '開啟')} />
            </div>
            <div style={grid}>
              <Field
                label={ui('Days between inspections (per turbine)', '每台機組幾天定檢一次')}
                hint={ui('Default 182 (twice a year).', '預設 182（半年一次）。')}
              >
                <Input
                  type="number"
                  value={planDays}
                  onChange={v => {
                    setPlanDays(v);
                    setPlanSaved(false);
                  }}
                  ariaLabel={ui('Days between inspections (per turbine)', '每台機組幾天定檢一次')}
                  fullWidth
                />
              </Field>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 16, flexWrap: 'wrap' }}>
              <Btn variant="primary" onClick={savePlan} loading={planSaving}>
                {ui('Save inspection plan', '儲存定檢計畫')}
              </Btn>
              {planSaved && (
                <span style={{ fontSize: 12, color: C.ok }}>
                  {ui(
                    'Saved. Schedules are updated with the next batch of readings.',
                    '已儲存。排程在即時模擬的下一批讀值時整理。',
                  )}
                </span>
              )}
            </div>
            {plan.schedules.length > 0 ? (
              <div style={{ overflowX: 'auto', marginTop: 16 }}>
                <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                  <thead>
                    <tr>
                      <th style={table.th}>{ui('Turbine', '機組')}</th>
                      <th style={table.th}>{ui('Status', '狀態')}</th>
                      <th style={table.th}>{ui('Next due (farm clock)', '下一次到期（風場時鐘）')}</th>
                      <th style={table.th}>{ui('Last opened', '上次開單')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plan.schedules.map(s => (
                      <tr key={s.turbine_id}>
                        <td style={table.td}>{s.turbine_id}</td>
                        <td style={{ ...table.td, color: s.overdue ? C.warn : s.active ? C.text : C.sub }}>
                          {s.overdue
                            ? ui('Due, not opened yet', '到期、還沒開單')
                            : s.active
                              ? ui('Active', '啟用')
                              : ui('Paused', '暫停')}
                        </td>
                        <td style={table.td}>{fmtTime(s.next_due_at)}</td>
                        <td style={table.td}>{fmtTime(s.last_spawned_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div style={{ fontSize: 12, color: C.sub, marginTop: 14 }}>
                {ui('No schedules yet.', '還沒有排程。')}
              </div>
            )}
            {plan.clock && (
              <div style={{ fontSize: 11, color: C.sub, marginTop: 8 }}>
                {ui('Farm clock now', '風場時鐘現在')}: {fmtTime(plan.clock)}
                {plan.schedules.some(s => s.overdue) &&
                  ui(
                    '. Checked every 15 farm-clock minutes; if a turbine stays due, its three open-order slots are full.',
                    '。每 15 分鐘（風場時鐘）看一次；一直停在到期的機組，是未結案工單已經滿三張。',
                  )}
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
};

export default AutomationPanel;
