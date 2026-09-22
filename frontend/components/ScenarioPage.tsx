/**
 * ScenarioPage — Scenario 模式的「情境設定」頁（WMOM-20260718-04, DEC-20260718-01）。
 *
 * DEC-20260718-01 把模擬主路徑定為 Scenario：使用者定義「風場 + 風況 + 時長 + 故障排程」
 * → 一次批次生成可重現資料集 → 探索 + 練運維。本頁即該「情境設定精靈」：
 *   1. 情境設定：目前風場（側邊欄切換）+ 風況 profile + 時長 + 解析度
 *   2. 故障排程：一列一支排定故障（場景 / 風機 / 第幾小時發生 / 發展速率），可增可刪
 *   3. 生成：先套風況（POST /api/config/wind）再批次生成（POST /api/config/simulation/generate-bulk
 *      帶 fault_schedule）→ 顯示結果（資料筆數 / 注入故障數 / 最終故障狀態）
 *   4. 生成後可一鍵跳去「歷史資料」探索該情境
 *
 * 全程走 `authFetch`（enforce-ready：generate-bulk / wind / faults 端點需 SUPERVISOR / 登入）。
 * free-run 即時模擬保留為預設落地（輕量看一眼），正式的情境練運維走本頁批次。
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Btn, Card, Field, Input, PageHeader, Select, Stat, StatusPill, type PillTone } from './ui';
import { useTheme } from '../theme/ThemeProvider';
import { authFetch } from '../services/authClient';
import { toFaultScheduleEntries, type ScheduledFaultInput } from '../utils/faultSchedule';
import ScenarioDetail, { type SavedScenario } from './ScenarioDetail';
import { WIND_PROFILES, windProfileLabel } from '../utils/windProfiles';
import type { SourceMode } from '../hooks/useSourceGate';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

interface ScenarioOption {
  id: string;
  name_en: string;
  name_zh: string;
}

interface FarmLite {
  farm_id: string;
  name: string;
  turbine_count: number;
}

interface FinalFaultStatus {
  turbine_id: string;
  scenario_id?: string;
  name_en?: string;
  name_zh?: string;
  severity: number;
  phase: string;
  tripped: boolean;
}

interface GenerateResult {
  status: string;
  scenario_id?: number | null;
  duration_hours: number;
  time_step: number;
  total_readings: number;
  faults_injected: number;
  final_fault_status: FinalFaultStatus[];
  storage_stats: { db_size_mb?: number };
}

/**
 * 一列排定故障（前端狀態；送出時由 `toFaultScheduleEntries` 轉為後端 fault_schedule 條目）。
 *
 * 領域欄位 extend `ScheduledFaultInput`（定義在 utils/faultSchedule）——共用欄位只有一份定義，
 * 本型別只多加 UI 記帳用的 `key`（React list identity，不送後端）。
 */
interface ScheduledFault extends ScheduledFaultInput {
  key: number;
}

const DURATION_PRESETS: { hours: number; en: string; zh: string }[] = [
  { hours: 24, en: '1 day', zh: '1 天' },
  { hours: 168, en: '1 week', zh: '1 週' },
  { hours: 720, en: '1 month', zh: '1 月' },
];

const RESOLUTIONS: { value: number; en: string; zh: string }[] = [
  { value: 10, en: '10s (high-res)', zh: '10 秒（高解析）' },
  { value: 60, en: '60s (standard)', zh: '60 秒（標準）' },
  { value: 300, en: '300s (fast)', zh: '300 秒（快速）' },
];

const phaseTone = (phase: string): PillTone => {
  if (phase === 'critical' || phase === 'advanced') return 'warn';
  return 'amber';
};

interface Props {
  lang?: 'en' | 'zh';
  /** 生成後「查看歷史資料」的跳頁回呼（App 接到 history view）。 */
  onExplore?: () => void;
}

const ScenarioPage: React.FC<Props> = ({ lang = 'zh', onExplore }) => {
  const { C } = useTheme();
  const u = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [scenarios, setScenarios] = useState<ScenarioOption[]>([]);
  const [farm, setFarm] = useState<FarmLite | null>(null);

  const [windProfile, setWindProfile] = useState('moderate');
  const [durationHours, setDurationHours] = useState(168);
  const [timeStep, setTimeStep] = useState(60);
  const [faults, setFaults] = useState<ScheduledFault[]>([]);

  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  // 情境命名 + 過去情境清單（WMOM-20260719-02 前端）
  const [scenarioName, setScenarioName] = useState('');
  const [savedScenarios, setSavedScenarios] = useState<SavedScenario[]>([]);
  const [observing, setObserving] = useState<SavedScenario | null>(null);
  const [lastScenario, setLastScenario] = useState<SavedScenario | null>(null);

  // 來源種類（WMOM-20260720-02）：情境生成需 simulation 來源（後端要有 simulator）。若使用者
  // 從「調閱過去情境」(view) 或其他來源進到本頁，simulator=None → 生成會 400 "Simulator not
  // running"（＝使用者回報的「無法啟用」）。故偵測來源種類，非 simulation 時停用生成並提供一鍵啟動。
  // undefined＝載入中（不顯示提示、避免閃動）；null＝尚未起任何來源。用 SourceMode 而非裸 string
  // → 比對字串打錯（如 'Live'/'veiw'）會被 tsc 抓到，不會安靜落到 default 分支。
  const [sourceKind, setSourceKind] = useState<SourceMode | null | undefined>(undefined);
  const [activating, setActivating] = useState(false);

  const nextKey = useRef(1);

  const loadScenarios = () => {
    authFetch(`${API_BASE}/api/scenarios`)
      .then(r => (r.ok ? r.json() : { scenarios: [] }))
      .then((data: { scenarios?: SavedScenario[] }) =>
        setSavedScenarios(Array.isArray(data?.scenarios) ? data.scenarios : []),
      )
      .catch(() => {});
  };

  const loadFarm = () => {
    authFetch(`${API_BASE}/api/farms`)
      .then(r => (r.ok ? r.json() : null))
      .then((data: { farms?: FarmLite[]; active_farm_id?: string } | null) => {
        if (!data?.farms) return;
        const active = data.farms.find(f => f.farm_id === data.active_farm_id) ?? data.farms[0] ?? null;
        setFarm(active);
      })
      .catch(() => {});
  };

  useEffect(() => {
    authFetch(`${API_BASE}/api/faults/scenarios`)
      .then(r => (r.ok ? r.json() : []))
      .then((data: ScenarioOption[]) => setScenarios(Array.isArray(data) ? data : []))
      .catch(() => {});
    loadFarm();
    // 目前來源種類（GET /api/source/status）——決定是否需要提示「啟動模擬以生成」。
    authFetch(`${API_BASE}/api/source/status`)
      .then(r => (r.ok ? r.json() : null))
      .then((data: { kind?: SourceMode | null } | null) => setSourceKind(data ? data.kind ?? null : null))
      .catch(() => setSourceKind(null));
    // 過去情境清單（GET /api/scenarios）
    authFetch(`${API_BASE}/api/scenarios`)
      .then(r => (r.ok ? r.json() : { scenarios: [] }))
      .then((data: { scenarios?: SavedScenario[] }) =>
        setSavedScenarios(Array.isArray(data?.scenarios) ? data.scenarios : []),
      )
      .catch(() => {});
  }, []);

  const turbineCount = farm?.turbine_count ?? 14;
  const turbineOptions = useMemo(
    () => Array.from({ length: turbineCount }, (_, i) => `WT${String(i + 1).padStart(3, '0')}`),
    [turbineCount],
  );

  // 估算資料筆數（給使用者對生成量的直覺）：步數 × 風機數。
  const estimatedReadings = Math.round((durationHours * 3600) / timeStep) * turbineCount;

  const scenarioLabel = (id: string): string => {
    const s = scenarios.find(x => x.id === id);
    return s ? (lang === 'zh' ? s.name_zh : s.name_en) : id;
  };

  const addFault = () => {
    const firstScenario = scenarios[0]?.id ?? '';
    setFaults(prev => [
      ...prev,
      {
        key: nextKey.current++,
        scenarioId: firstScenario,
        turbineId: turbineOptions[0] ?? 'WT001',
        atHour: Math.max(0, Math.round(durationHours / 2)),
        severityRate: 0.002,
      },
    ]);
  };

  const removeFault = (key: number) => setFaults(prev => prev.filter(f => f.key !== key));

  const updateFault = (key: number, patch: Partial<ScheduledFault>) =>
    setFaults(prev => prev.map(f => (f.key === key ? { ...f, ...patch } : f)));

  const requestDelete = (s: SavedScenario) => {
    // 刪除跨 5 張表、不可逆 → 二次確認（對齊全站破壞性操作的謹慎程度）。
    const name = s.config?.name ?? `#${s.id}`;
    if (
      window.confirm(
        u(`Delete scenario "${name}"? This cannot be undone.`, `確定刪除情境「${name}」？此操作不可復原。`),
      )
    ) {
      void deleteScenario(s.id);
    }
  };

  const deleteScenario = async (id: number) => {
    try {
      const res = await authFetch(`${API_BASE}/api/scenarios/${id}`, { method: 'DELETE' });
      if (res.ok) {
        setSavedScenarios(prev => prev.filter(s => s.id !== id));
        if (observing?.id === id) setObserving(null);
      } else {
        // 刪除需 ADMIN；被擋時給提示而非靜默。
        setError(
          res.status === 403
            ? u('Delete needs admin rights.', '刪除情境需要系統管理員權限。')
            : u(`Delete failed: HTTP ${res.status}`, `刪除失敗：HTTP ${res.status}`),
        );
      }
    } catch {
      setError(u('Network error while deleting.', '刪除時發生網路錯誤。'));
    }
  };

  const sourceKindLabel = (kind: SourceMode | null | undefined): string => {
    if (kind === 'view') return u('viewing past scenarios', '調閱過去情境');
    if (kind === 'live') return u('live data connection', '實際資料對接');
    // scenario：目前唯一呼叫點被 `!simActive`（已含 scenario）保護、走不到這裡，但補上分支求穩，
    // 避免此 helper 日後被重用時 scenario 悄悄 fall through 成「尚未啟動來源」的錯誤文案。
    if (kind === 'scenario') return u('generating a scenario', '產生情境');
    return u('none started', '尚未啟動來源');
  };

  /** 從非 ok response 盡量解析後端 detail；失敗則回退 HTTP 狀態碼（與 handleGenerate 共用）。 */
  const parseErrorDetail = async (res: Response): Promise<string> => {
    try {
      const body = await res.json();
      if (body?.detail) return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore parse error */
    }
    return `HTTP ${res.status}`;
  };

  // 一鍵啟動即時模擬（WMOM-20260720-02）：讓使用者不必繞「先 activate 一個風場（順帶起 live
  // 迴圈、正是撞 #4 的路）」——直接於情境頁把 simulation 來源起來即可生成。
  const handleActivateSim = async () => {
    // ⚠️ 若目前是「實際資料對接」(live)：切到 simulation 會 stop() 掉現場 SCADA 連線，且介面上
    // 沒有再切回 live 的入口（App 只在 sourceActive===false 時顯示選源頁）。故對 live 加二次確認，
    // 比照本檔刪除情境的謹慎程度——避免現場工程師手滑點到、無預警斷掉真實監控（WMOM-20260720-03）。
    if (
      sourceKind === 'live' &&
      !window.confirm(
        u(
          'You are on the live SCADA connection. Starting simulation will disconnect it, and there is no in-app way to switch back to live. Continue?',
          '目前為「實際資料對接」。啟動模擬將中斷與現場 SCADA 的連線，且介面上無法再切回實接。確定要繼續嗎？',
        )
      )
    ) {
      return;
    }
    setActivating(true);
    setError('');
    try {
      // 啟動「產生情境」模式（scenario：simulator 供批次、不自由跑）——非「即時模擬」（自由跑）。
      // 我們在情境頁要做的就是批次生成，不需要連續自由跑（DEC-20260720-01 PR B）。
      const res = await authFetch(`${API_BASE}/api/source/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'scenario' }),
      });
      if (res.ok) {
        setSourceKind('scenario');
        loadFarm(); // activate_simulation 會 ensure_default_farm → 風場資訊即時更新
      } else {
        // 401 由 authClient 攔（彈登入）；其餘給明確回饋而非靜默（解析後端 detail，與生成一致）。
        const detail = await parseErrorDetail(res);
        setError(u(`Could not start simulation: ${detail}`, `啟動模擬失敗：${detail}`));
      }
    } catch {
      setError(u('Network error while starting simulation.', '啟動模擬時發生網路錯誤。'));
    } finally {
      setActivating(false);
    }
  };

  const handleGenerate = async () => {
    // 排程只映射一次：送出的 request body 與就地組出的 lastScenario.config 共用這一份，
    // 形狀即後端落地形狀（WMOM-20260720-13(4)）。
    const scheduleEntries = toFaultScheduleEntries(faults);
    setGenerating(true);
    setResult(null);
    setError('');
    setMessage(u('Applying wind & generating scenario…', '套用風況並生成情境資料集…（時長越長越久）'));
    try {
      // 1. 套風況 profile（讓批次以此風況跑）。若失敗必須中止——否則會用「殘留風況」
      //    生成卻顯示成功，資料與畫面選的 profile 不符（破壞情境可重現的核心承諾）。
      const windRes = await authFetch(`${API_BASE}/api/config/wind`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: windProfile }),
      });
      if (!windRes.ok) {
        setError(u('Failed to apply wind profile — nothing generated.', '套用風況失敗，未生成資料。'));
        setMessage('');
        return;
      }

      // 2. 批次生成（帶故障排程 + 情境名稱 → 存成可調閱的專屬 session）。
      //    ScenarioPage 的產物一律存成命名情境（名稱留空則自動帶時間戳），這樣使用者事後
      //    才能在「過去情境」把它調回來——正是本次要修的「產生過的情境調不回來」。
      const finalName =
        scenarioName.trim() ||
        `${u('Scenario', '情境')} ${new Date().toLocaleString(lang === 'zh' ? 'zh-TW' : 'en-US')}`;
      const res = await authFetch(`${API_BASE}/api/config/simulation/generate-bulk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: finalName,
          wind_profile: windProfile,
          duration_hours: durationHours,
          time_step: timeStep,
          fault_schedule: scheduleEntries,
        }),
      });
      if (!res.ok) {
        const detail = await parseErrorDetail(res);
        setError(u(`Generation failed: ${detail}`, `生成失敗：${detail}`));
        setMessage('');
        return;
      }
      const data = (await res.json()) as GenerateResult;
      setResult(data);
      loadScenarios(); // 新情境即時出現在「過去情境」
      // 直接用生成輸入 + 回傳組出剛存的情境物件（不依賴 loadScenarios 這個非同步刷新），
      // 讓結果卡「觀察此情境」不受清單刷新競態影響——一定觀察得到剛生成的那個。
      if (data.scenario_id != null) {
        setLastScenario({
          id: data.scenario_id,
          started_at: new Date().toISOString(),
          turbine_count: turbineCount,
          config: {
            kind: 'scenario',
            name: finalName,
            wind_profile: windProfile,
            duration_hours: durationHours,
            time_step: timeStep,
            total_readings: data.total_readings,
            faults_injected: data.faults_injected,
            status: 'ok',
            // 帶上排程——否則「觀察此情境」→ 機組比較（A1）少了 fault_schedule 會把所有機組都當
            // 健康（faulted 判別靠排程，非時間窗的 faultEvents）。與 request body **共用同一份**
            // `scheduleEntries`（WMOM-20260720-13(4)）：先前兩處各自映射且形狀不同（at_hour vs
            // offset_seconds），正是這個 bug 的成因模式。
            fault_schedule: scheduleEntries,
          },
        });
      }
      setScenarioName(''); // 清空，避免重複點生成疊出多個同名情境
      // 結果卡本身即成功訊號 → 清掉「生成中…」訊息，避免頂部訊息永遠不消失且與結果卡重複。
      setMessage('');
    } catch {
      setError(u('Network error during generation.', '生成時發生網路錯誤。'));
      setMessage('');
    } finally {
      setGenerating(false);
    }
  };

  // 觀察模式：選了某過去情境 → 顯示該情境的隔離調閱視圖（ScenarioDetail）。
  // `key={observing.id}`：ScenarioDetail 現在 keep-alive 保留頁籤與所選機組（WMOM-20260720-13(2)），
  // 故換情境必須換 identity 強制重置，不依賴呼叫端「先回列表才能開下一個」這條 control flow。
  if (observing) {
    return <ScenarioDetail key={observing.id} scenario={observing} lang={lang} onBack={() => setObserving(null)} />;
  }

  // 生成需「有 simulator」的來源——即時模擬(simulation) 或產生情境(scenario) 皆有 simulator。
  // view/live/未起 時停用並提示一鍵啟動（會啟動 scenario 模式，見 handleActivateSim）。
  const simActive = sourceKind === 'simulation' || sourceKind === 'scenario';
  const canGenerate = !generating && scenarios.length > 0 && simActive;

  return (
    <div>
      <PageHeader
        title={u('Scenario Simulation', '情境模擬')}
        sub={u(
          'Define farm · wind · duration · scheduled faults → generate one reproducible dataset → explore & practice O&M',
          '定義風場・風況・時長・排定故障 → 一次生成可重現資料集 → 探索並演練運維',
        )}
        actions={
          <Btn
            variant="primary"
            onClick={handleGenerate}
            disabled={!canGenerate}
            ariaLabel={u('Generate scenario', '生成情境')}
          >
            {generating ? u('Generating…', '生成中…') : u('Generate scenario', '生成情境')}
          </Btn>
        }
      />

      {message && (
        <div style={{ marginBottom: 14 }}>
          <StatusPill tone="accent" size="md">
            {message}
          </StatusPill>
        </div>
      )}
      {error && (
        <div
          style={{
            marginBottom: 14,
            background: C.warnSoft,
            color: C.warn,
            border: `1px solid ${C.warn}`,
            borderRadius: 8,
            padding: '10px 14px',
            fontSize: 13,
          }}
          role="alert"
        >
          {error}
        </div>
      )}

      {/* 尚未啟動模擬 → 引導一鍵啟動（WMOM-20260720-02）。undefined＝載入中不顯示。 */}
      {sourceKind !== undefined && !simActive && (
        <div
          style={{
            marginBottom: 14,
            background: C.panelMuted,
            border: `1px solid ${C.accent}`,
            borderRadius: 8,
            padding: '12px 14px',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 12,
            justifyContent: 'space-between',
          }}
          role="status"
        >
          <div style={{ fontSize: 13, color: C.text, flex: 1, minWidth: 220 }}>
            {u(
              `Generating a scenario needs the simulation engine — current source: ${sourceKindLabel(sourceKind)}. Start it to generate.`,
              `產生新情境需要「即時模擬」引擎 — 目前來源：${sourceKindLabel(sourceKind)}。點右側啟動即可生成。`,
            )}
          </div>
          <Btn
            variant="primary"
            onClick={handleActivateSim}
            disabled={activating}
            ariaLabel={u('Start simulation to generate', '啟動模擬以生成')}
          >
            {activating ? u('Starting…', '啟動中…') : u('Start simulation to generate', '啟動模擬以生成')}
          </Btn>
        </div>
      )}

      {/* ── 情境設定 ── */}
      <Card style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14, color: C.text }}>
          {u('Scenario definition', '情境設定')}
        </div>

        <div style={{ marginBottom: 14, fontSize: 13, color: C.sub }}>
          {u('Wind farm', '風場')}：
          <span style={{ color: C.text, fontWeight: 600 }}>
            {farm ? `${farm.name}（${farm.turbine_count} ${u('turbines', '台')}）` : u('loading…', '載入中…')}
          </span>
          <span style={{ color: C.faint, marginLeft: 8 }}>
            {u('· switch via the sidebar', '· 用側邊欄切換風場')}
          </span>
        </div>

        <div style={{ marginBottom: 14 }}>
          <Field label={u('Scenario name', '情境名稱')}>
            <Input
              value={scenarioName}
              onChange={setScenarioName}
              placeholder={u(
                'e.g. Storm + hydraulic leak (auto-named if blank)',
                '例：暴風 + 液壓洩漏（留空會自動命名）',
              )}
              fullWidth
              ariaLabel={u('Scenario name', '情境名稱')}
            />
          </Field>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 12,
          }}
        >
          <Field label={u('Wind profile', '風況')}>
            <Select
              value={windProfile}
              onChange={setWindProfile}
              options={WIND_PROFILES.map(p => ({ value: p.value, label: u(p.en, p.zh) }))}
              ariaLabel={u('Wind profile', '風況')}
              fullWidth
            />
          </Field>
          <Field label={u('Duration (hours)', '時長（小時）')}>
            <Input
              type="number"
              min={1}
              max={8760}
              value={String(durationHours)}
              onChange={v => setDurationHours(Math.max(1, Math.min(8760, parseInt(v) || 1)))}
              fullWidth
              monospace
              ariaLabel={u('Duration hours', '時長小時')}
            />
          </Field>
          <Field label={u('Resolution', '解析度')}>
            <Select
              value={String(timeStep)}
              onChange={v => setTimeStep(parseInt(v) || 60)}
              options={RESOLUTIONS.map(r => ({ value: String(r.value), label: u(r.en, r.zh) }))}
              ariaLabel={u('Resolution', '解析度')}
              fullWidth
            />
          </Field>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: C.sub }}>{u('Presets:', '快速設定：')}</span>
          {DURATION_PRESETS.map(p => (
            <Btn
              key={p.hours}
              size="sm"
              variant={durationHours === p.hours ? 'primary' : 'secondary'}
              onClick={() => setDurationHours(p.hours)}
              ariaLabel={u(p.en, p.zh)}
            >
              {u(p.en, p.zh)}
            </Btn>
          ))}
          <span style={{ fontSize: 11, color: C.faint, marginLeft: 'auto', fontFamily: 'JetBrains Mono, monospace' }}>
            ≈ {estimatedReadings.toLocaleString()} {u('readings', '筆資料')}
          </span>
        </div>
      </Card>

      {/* ── 故障排程 ── */}
      <Card style={{ marginBottom: 14 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 14,
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>
            {u('Fault schedule', '故障排程')}{' '}
            <span style={{ color: C.faint, fontWeight: 400 }}>({faults.length})</span>
          </div>
          <Btn
            size="sm"
            variant="secondary"
            onClick={addFault}
            disabled={scenarios.length === 0}
            ariaLabel={u('Add fault', '新增故障')}
          >
            + {u('Add fault', '新增故障')}
          </Btn>
        </div>

        {faults.length === 0 ? (
          <div style={{ fontSize: 13, color: C.faint, padding: '8px 0' }}>
            {u(
              'No scheduled faults — generates a clean wind-only dataset. Add a fault to practice O&M on a reproducible case.',
              '無排定故障 — 生成純風況資料集。加一支故障即可在可重現案例上演練運維。',
            )}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {faults.map(f => {
              const outOfRange = f.atHour >= durationHours;
              return (
                <div
                  key={f.key}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'minmax(160px, 2fr) minmax(110px, 1fr) minmax(120px, 1fr) minmax(120px, 1fr) auto',
                    gap: 8,
                    alignItems: 'end',
                    padding: '10px',
                    background: C.panelMuted,
                    borderRadius: 8,
                  }}
                >
                  <Field label={u('Fault scenario', '故障場景')}>
                    <Select
                      value={f.scenarioId}
                      onChange={v => updateFault(f.key, { scenarioId: v })}
                      options={scenarios.map(s => ({ value: s.id, label: lang === 'zh' ? s.name_zh : s.name_en }))}
                      ariaLabel={u('Fault scenario', '故障場景')}
                      fullWidth
                    />
                  </Field>
                  <Field label={u('Turbine', '風機')}>
                    <Select
                      value={f.turbineId}
                      onChange={v => updateFault(f.key, { turbineId: v })}
                      options={turbineOptions.map(t => ({ value: t, label: t }))}
                      ariaLabel={u('Turbine', '風機')}
                      fullWidth
                    />
                  </Field>
                  <Field label={u('At hour', '第幾小時')}>
                    <Input
                      type="number"
                      min={0}
                      max={durationHours}
                      value={String(f.atHour)}
                      onChange={v => updateFault(f.key, { atHour: Math.max(0, parseInt(v) || 0) })}
                      fullWidth
                      monospace
                      ariaLabel={u('At hour', '第幾小時')}
                    />
                  </Field>
                  <Field label={u('Severity rate', '發展速率')}>
                    <Input
                      type="number"
                      step="0.0001"
                      min={0.00001}
                      max={0.1}
                      value={String(f.severityRate)}
                      onChange={v => {
                        // 夾限到 [0.00001, 0.1]（同 duration/at_hour）。用 Number.isFinite 而非
                        // `|| 0.0002`：否則使用者輸入 0 會被靜默換成預設、負值更會直接送到後端。
                        const n = parseFloat(v);
                        const rate = Number.isFinite(n) ? Math.max(0.00001, Math.min(0.1, n)) : 0.0002;
                        updateFault(f.key, { severityRate: rate });
                      }}
                      fullWidth
                      monospace
                      ariaLabel={u('Severity rate', '發展速率')}
                    />
                  </Field>
                  <Btn
                    size="sm"
                    variant="ghost"
                    onClick={() => removeFault(f.key)}
                    ariaLabel={u('Remove fault', '移除故障')}
                  >
                    ✕
                  </Btn>
                  {outOfRange && (
                    <div style={{ gridColumn: '1 / -1', fontSize: 11, color: C.warn }}>
                      {u(
                        `At-hour ${f.atHour} ≥ duration ${durationHours}h — this fault will not be injected.`,
                        `第 ${f.atHour} 小時 ≥ 時長 ${durationHours}h — 此故障不會被注入。`,
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* ── 結果 ── */}
      {result && (
        <Card>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 14,
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 600, color: C.accent }}>
              {u('Scenario dataset', '情境資料集')}
            </div>
            {result.scenario_id != null ? (
              <Btn
                size="sm"
                variant="primary"
                onClick={() => (lastScenario ? setObserving(lastScenario) : onExplore?.())}
                ariaLabel={u('Observe this scenario', '觀察此情境')}
              >
                {u('Observe this scenario →', '觀察此情境 →')}
              </Btn>
            ) : (
              onExplore && (
                <Btn size="sm" variant="primary" onClick={onExplore} ariaLabel={u('View history', '查看歷史資料')}>
                  {u('Explore history →', '查看歷史資料 →')}
                </Btn>
              )
            )}
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: 14,
              marginBottom: result.final_fault_status?.length ? 16 : 0,
            }}
          >
            <Stat label={u('Duration', '時長')} value={`${result.duration_hours}h`} size={24} />
            <Stat
              label={u('Readings', '資料筆數')}
              value={result.total_readings.toLocaleString()}
              highlight
              size={24}
            />
            <Stat label={u('Faults injected', '注入故障數')} value={result.faults_injected} size={24} />
            <Stat
              label={u('DB size', '資料庫大小')}
              value={`${result.storage_stats?.db_size_mb ?? '—'}`}
              unit="MB"
              size={24}
            />
          </div>

          {result.final_fault_status?.length > 0 && (
            <>
              <div style={{ fontSize: 12, color: C.sub, marginBottom: 6 }}>
                {u('Final fault status', '最終故障狀態')}
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ color: C.sub }}>
                      {[u('Turbine', '風機'), u('Scenario', '場景'), u('Severity', '嚴重度'), u('Phase', '階段'), u('Tripped', '跳脫')].map(h => (
                        <th
                          key={h}
                          style={{
                            textAlign: 'left',
                            padding: '6px 10px',
                            fontSize: 10,
                            color: C.faint,
                            fontWeight: 500,
                            letterSpacing: 0.5,
                            textTransform: 'uppercase',
                            borderBottom: `1px solid ${C.border}`,
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.final_fault_status.map((f, i) => (
                      <tr key={i} style={{ borderBottom: `1px solid ${C.border}` }}>
                        <td style={{ padding: '6px 10px', fontFamily: 'JetBrains Mono, monospace', color: C.text }}>
                          {f.turbine_id}
                        </td>
                        <td style={{ padding: '6px 10px', color: C.text }}>
                          {f.scenario_id ? scenarioLabel(f.scenario_id) : f.name_zh ?? f.name_en}
                        </td>
                        <td style={{ padding: '6px 10px' }}>
                          <span
                            style={{
                              fontFamily: 'JetBrains Mono, monospace',
                              color: f.severity > 0.7 ? C.warn : f.severity > 0.4 ? C.amber : C.ok,
                            }}
                          >
                            {(f.severity * 100).toFixed(0)}%
                          </span>
                        </td>
                        <td style={{ padding: '6px 10px' }}>
                          <StatusPill tone={phaseTone(f.phase)}>{f.phase}</StatusPill>
                        </td>
                        <td style={{ padding: '6px 10px' }}>
                          {f.tripped ? (
                            <StatusPill tone="warn">TRIP</StatusPill>
                          ) : (
                            <span style={{ color: C.sub }}>—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Card>
      )}

      {/* ── 過去情境（可調閱 / 刪除）── */}
      <Card style={{ marginTop: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14, color: C.text }}>
          {u('Saved scenarios', '過去情境')}{' '}
          <span style={{ color: C.faint, fontWeight: 400 }}>({savedScenarios.length})</span>
        </div>
        {savedScenarios.length === 0 ? (
          <div style={{ fontSize: 13, color: C.faint, padding: '8px 0' }}>
            {u(
              'No saved scenarios yet — generate one above to keep it here for later observation.',
              '還沒有保存的情境 — 上方生成一個，之後就能在這裡調回來觀察分析。',
            )}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {savedScenarios.map(s => {
              const cfg = s.config ?? {};
              return (
                <div
                  key={s.id}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1.4fr) auto',
                    gap: 12,
                    alignItems: 'center',
                    padding: '10px 12px',
                    background: C.panelMuted,
                    borderRadius: 8,
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: C.text,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {cfg.name || u('(unnamed)', '（未命名）')}
                      {cfg.status === 'error' && (
                        <StatusPill tone="warn" size="sm">
                          {u('failed', '失敗')}
                        </StatusPill>
                      )}
                    </div>
                    <div style={{ fontSize: 11, color: C.sub, marginTop: 2 }}>
                      {new Date(s.started_at).toLocaleString()}
                      {cfg.wind_profile ? ` · ${windProfileLabel(cfg.wind_profile, lang)}` : ''}
                    </div>
                  </div>
                  <div style={{ fontSize: 11, color: C.sub, fontFamily: 'JetBrains Mono, monospace' }}>
                    {cfg.duration_hours ?? '—'}h · {(cfg.total_readings ?? 0).toLocaleString()}{' '}
                    {u('rows', '筆')} · {cfg.faults_injected ?? 0} {u('faults', '故障')}
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <Btn
                      size="sm"
                      variant="primary"
                      onClick={() => setObserving(s)}
                      ariaLabel={u(`Observe scenario: ${cfg.name ?? s.id}`, `觀察情境：${cfg.name ?? s.id}`)}
                    >
                      {u('Observe →', '觀察 →')}
                    </Btn>
                    <Btn
                      size="sm"
                      variant="danger"
                      onClick={() => requestDelete(s)}
                      ariaLabel={u(`Delete scenario: ${cfg.name ?? s.id}`, `刪除情境：${cfg.name ?? s.id}`)}
                    >
                      {u('Delete', '刪除')}
                    </Btn>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
};

export default ScenarioPage;
