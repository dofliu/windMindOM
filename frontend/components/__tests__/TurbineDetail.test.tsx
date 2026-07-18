/**
 * TurbineDetail component render 測試（WMOM-20260606-05，EPIC-M5 測試覆蓋擴大）。
 *
 * `components/TurbineDetail.tsx`（1056 行）是 `/admin` 風機詳情頁（A · Calm Operator 改版）：
 *   - PageHeader 麵包屑（返回風場總覽）+ 機名 · TurState label + 狀態 pill + Curtail/Stop/Inspect actions
 *   - 故障 banner（僅 activeFaults 非空才渲染）
 *   - 4 大 hero 數字（Power / Wind / RPM / Gen °C）
 *   - 左欄：即時趨勢 4 通道、子系統健康 8 格、子系統明細 8 tabs、詳細趨勢（TrendChartPanel）
 *   - 右欄：OperatorControlCard（6 指令 + 限載）、最近事件、AI 故障診斷（僅 FAULT 才渲染）
 *
 * 本元件先前零 component 測試。延續既有 render 測試範式（ThemeProvider 包裹 +
 * jest-dom matcher + afterEach cleanup + async act flush）。
 *
 * 外部依賴的隔離策略：
 *   - `useTheme` → ThemeProvider 包裹。
 *   - `analyzeTurbineFault`（services/geminiService）→ `vi.mock` 注入可控 spy，
 *     避免真的打 Gemini API；驗 AI 診斷卡的 analyze / dispatch 流程。
 *   - `TrendChartPanel`（recharts + 多支 fetch 的重元件）→ `vi.mock` 換成輕量 stub，
 *     只驗「有掛載 + 收到 turbineId prop」，不重測它自身的 SCADA 圖表行為。
 *   - `global.fetch` → OperatorControlCard 掛載即 GET `/api/control/:id/status` + 每 3s 輪詢、
 *     指令走 POST。以 `vi.fn()` stub 接管：預設回空 status，個別測試覆寫回特定 status 驗 pill。
 *
 * ⚠️ OperatorControlCard 的 mount effect 會觸發 fetch→setState；所有 render 一律以
 * `await renderDetail(...)`（內部 `act(async)` 包 render + flush microtask）收尾，
 * 避免「state update not wrapped in act()」警告污染輸出。3s 輪詢用 real timer，
 * 快速測試內不會二次觸發；cleanup 卸載時 clearInterval。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, act, within, waitFor } from '@testing-library/react';
import React from 'react';
import {
  TurbineStatus,
  type TurbineData,
  type FaultInfo,
  type WorkOrder,
  WorkOrderStatus,
} from '../../types';

// ─── mock：AI 診斷服務（避免真打 Gemini）──────────────────────────────────
const mockAnalyze = vi.fn<(t: TurbineData) => Promise<string>>();
vi.mock('../../services/geminiService', () => ({
  analyzeTurbineFault: (t: TurbineData) => mockAnalyze(t),
}));

// ─── mock：TrendChartPanel（recharts + fetch 重元件）換輕量 stub ──────────
vi.mock('../TrendChartPanel', () => ({
  default: ({ turbineId, lang }: { turbineId: string; lang?: string }) => (
    <div data-testid="trend-chart-panel" data-turbine={turbineId} data-lang={lang ?? 'zh'}>
      trend-stub
    </div>
  ),
}));

import TurbineDetail, { noPowerReason } from '../TurbineDetail';
import { ThemeProvider } from '../../theme/ThemeProvider';

type Lang = 'en' | 'zh';

// ─── 工廠 ──────────────────────────────────────────────────────────────────

/** 結構完整的 TurbineData（不用 `as` 強轉），overrides 末尾 spread。 */
function makeTurbine(over: Partial<TurbineData> = {}): TurbineData {
  return {
    id: 7,
    name: 'WTG-07',
    status: TurbineStatus.OPERATING,
    turState: 6,
    powerOutput: 2.34,
    windSpeed: 8.5,
    rotorSpeed: 12.3,
    bladeAngle: 4,
    temperature: 48,
    vibration: 1.2,
    voltage: 690,
    current: 110,
    history: [],
    ...over,
  };
}

function makeFault(over: Partial<FaultInfo> = {}): FaultInfo {
  return {
    scenario_id: 'sc-gearbox-wear',
    turbine_id: 'WT007',
    name_en: 'Gearbox bearing wear',
    name_zh: '齒輪箱軸承磨損',
    severity: 0.62,
    phase: 'developing',
    tripped: false,
    active_alarms: [{ type: 'WARN', code: 4011, desc: 'Bearing temp high' }],
    ...over,
  };
}

function makeWorkOrder(over: Partial<WorkOrder> = {}): WorkOrder {
  return {
    id: 'wo-abcd1234',
    turbineId: 7,
    turbineName: 'WTG-07',
    technicianId: null,
    status: WorkOrderStatus.IN_PROGRESS,
    createdAt: 0,
    faultDescription: '齒輪箱異音',
    notes: '',
    photos: [],
    ...over,
  };
}

// ─── fetch stub helper ──────────────────────────────────────────────────────

interface ControlStatus {
  service_mode?: boolean;
  operator_stop?: boolean;
  curtailment_kw?: number | null;
  stop_mode?: string;
  shutdown_cause?: string;
}

/**
 * 接管 global.fetch。GET status 回 `status`，其餘（POST 指令 / 限載）回空物件。
 * 回傳 spy 供斷言呼叫 body。
 */
function stubFetch(status: ControlStatus = {}): ReturnType<typeof vi.fn> {
  const spy = vi.fn((url: string) => {
    if (typeof url === 'string' && url.includes('/api/control/') && url.endsWith('/status')) {
      return Promise.resolve({ json: () => Promise.resolve(status) });
    }
    return Promise.resolve({ json: () => Promise.resolve({}) });
  });
  // 以 vi.stubGlobal 注入，afterEach 的 vi.unstubAllGlobals() 才能正確還原
  // （直接 `global.fetch = spy` 不受 restoreAllMocks 管理、會跨檔洩漏）。
  vi.stubGlobal('fetch', spy);
  return spy;
}

// ─── render helper（async act flush 掉 control status fetch effect）─────────

async function renderDetail(
  opts: {
    turbine?: TurbineData;
    lang?: Lang;
    activeWorkOrder?: WorkOrder;
    onBack?: () => void;
    onDispatch?: (t: TurbineData, fa: string) => void;
  } = {},
) {
  const onBack = opts.onBack ?? vi.fn();
  const onDispatch = opts.onDispatch ?? vi.fn();
  let utils!: ReturnType<typeof render>;
  await act(async () => {
    utils = render(
      <ThemeProvider>
        <TurbineDetail
          turbine={opts.turbine ?? makeTurbine()}
          onBack={onBack}
          onDispatch={onDispatch}
          activeWorkOrder={opts.activeWorkOrder}
          lang={opts.lang ?? 'zh'}
        />
      </ThemeProvider>,
    );
  });
  return { ...utils, onBack, onDispatch };
}

beforeEach(() => {
  stubFetch();
  mockAnalyze.mockReset();
  mockAnalyze.mockResolvedValue('診斷結果：建議檢查 NDE 側軸承潤滑。');
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ─── 殼層 / header ──────────────────────────────────────────────────────────

describe('TurbineDetail — 殼層與 header', () => {
  it('渲染機名 + TurState label（正常發電）於標題', async () => {
    await renderDetail({ turbine: makeTurbine({ name: 'WTG-07', turState: 6 }) });
    expect(screen.getByText(/WTG-07 · 正常發電/)).toBeInTheDocument();
  });

  it('麵包屑返回鈕 aria-label 正確，點按呼 onBack', async () => {
    const { onBack } = await renderDetail({});
    const back = screen.getByRole('button', { name: '返回風場總覽' });
    fireEvent.click(back);
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('header 三個 action 按鈕（限載 / 停機 / 安排檢查）皆渲染', async () => {
    await renderDetail({});
    expect(screen.getByRole('button', { name: '限載' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '停機' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '安排檢查' })).toBeInTheDocument();
  });

  it('狀態 pill 依 status 顯示對應文字（運轉中）', async () => {
    await renderDetail({ turbine: makeTurbine({ status: TurbineStatus.OPERATING }) });
    expect(screen.getByText('運轉中')).toBeInTheDocument();
  });

  it('狀態 pill：FAULT → 故障', async () => {
    await renderDetail({ turbine: makeTurbine({ status: TurbineStatus.FAULT }) });
    expect(screen.getByText('故障')).toBeInTheDocument();
  });

  it('狀態 pill：IDLE → 待機', async () => {
    await renderDetail({ turbine: makeTurbine({ status: TurbineStatus.IDLE }) });
    // IDLE 下「待機」會出現兩處：header status pill + 最近事件卡的待機事件。
    // 斷言 >=2 同時守住兩處渲染（若 header pill 退化成別字，count 掉到 1 即抓到）。
    expect(screen.getAllByText('待機').length).toBeGreaterThanOrEqual(2);
  });

  it('狀態 pill：OFFLINE → 離線', async () => {
    await renderDetail({ turbine: makeTurbine({ status: TurbineStatus.OFFLINE }) });
    expect(screen.getByText('離線')).toBeInTheDocument();
  });

  it('未知 turState → fallback「State {n}」', async () => {
    await renderDetail({ turbine: makeTurbine({ turState: 99 }) });
    expect(screen.getByText(/State 99/)).toBeInTheDocument();
  });

  it('室外溫 / 風向有值時於 sub 顯示', async () => {
    await renderDetail({ turbine: makeTurbine({ outsideTemp: 18.4, windDirection: 230 }) });
    expect(screen.getByText(/室外/)).toBeInTheDocument();
    expect(screen.getByText(/風向/)).toBeInTheDocument();
  });

  it('lang=en → header 與 actions 走英文', async () => {
    await renderDetail({ lang: 'en', turbine: makeTurbine({ turState: 6 }) });
    expect(screen.getByText(/WTG-07 · Production/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Curtail' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Inspect' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Back to farm overview' })).toBeInTheDocument();
  });
});

// ─── 4 hero 數字 ────────────────────────────────────────────────────────────

describe('TurbineDetail — hero 數字', () => {
  it('Power / Wind / RPM / Gen °C 四格皆渲染並格式化', async () => {
    await renderDetail({
      turbine: makeTurbine({ powerOutput: 2.34, windSpeed: 8.5, rotorSpeed: 12.3, genStatorTemp1: 95 }),
    });
    // 4 個 hero Stat label 皆在（功率 與 overview 明細 DataRow 同字 → getAllByText）
    expect(screen.getAllByText('功率').length).toBeGreaterThan(0);
    expect(screen.getByText('風速')).toBeInTheDocument();
    expect(screen.getByText('RPM')).toBeInTheDocument();
    // 格式化後的值（hero 與 live-trends / 明細可能同值 → getAllByText 容許多處）
    expect(screen.getAllByText('2.34').length).toBeGreaterThan(0); // Power MW（2 位）
    expect(screen.getAllByText('8.5').length).toBeGreaterThan(0); // Wind（1 位）
    expect(screen.getAllByText('12.3').length).toBeGreaterThan(0); // RPM（1 位）
    expect(screen.getAllByText('95').length).toBeGreaterThan(0); // Gen °C（0 位）
  });

  it('genStatorTemp1 缺漏時 Gen °C 退回 temperature', async () => {
    await renderDetail({ turbine: makeTurbine({ genStatorTemp1: undefined, temperature: 48 }) });
    // hero Gen °C 以 0 位顯示 → 48
    expect(screen.getAllByText('48').length).toBeGreaterThan(0);
  });
});

// ─── 故障 banner ────────────────────────────────────────────────────────────

describe('TurbineDetail — 故障 banner', () => {
  it('無 activeFaults → 不渲染「即時告警」banner', async () => {
    await renderDetail({ turbine: makeTurbine({ activeFaults: [] }) });
    expect(screen.queryByText('即時告警')).not.toBeInTheDocument();
  });

  it('有 activeFaults → 渲染 banner 含故障名稱 + 嚴重度百分比 + phase', async () => {
    await renderDetail({
      turbine: makeTurbine({
        activeFaults: [makeFault({ name_en: 'Gearbox bearing wear', severity: 0.62, phase: 'developing' })],
      }),
    });
    expect(screen.getByText('即時告警')).toBeInTheDocument();
    // FaultBanner 以 navigator.language 決定名稱語系；jsdom 預設 'en-US' → 顯示 name_en
    expect(screen.getByText('Gearbox bearing wear')).toBeInTheDocument();
    expect(screen.getByText(/62\.0%/)).toBeInTheDocument();
    expect(screen.getByText('developing')).toBeInTheDocument();
  });

  it('tripped 故障 → 顯示 TRIPPED pill', async () => {
    await renderDetail({ turbine: makeTurbine({ activeFaults: [makeFault({ tripped: true })] }) });
    expect(screen.getByText('TRIPPED')).toBeInTheDocument();
  });

  it('active_alarms 逐筆顯示 type + desc', async () => {
    await renderDetail({
      turbine: makeTurbine({
        activeFaults: [makeFault({ active_alarms: [{ type: 'WARN', code: 4011, desc: 'Bearing temp high' }] })],
      }),
    });
    expect(screen.getByText(/\[WARN\] Bearing temp high/)).toBeInTheDocument();
  });
});

// ─── 子系統健康 + 明細 tabs ─────────────────────────────────────────────────

describe('TurbineDetail — 子系統健康與明細', () => {
  it('子系統健康 8 格 label 皆渲染', async () => {
    await renderDetail({});
    const healthCard = screen.getByText('子系統健康').parentElement as HTMLElement;
    // HealthBar label：發電機 / 齒輪箱 / 變槳 / 偏航 / 塔筒 / 葉片 / 變頻器 / 冷卻
    // （發電機·變頻器 與明細 tab 按鈕同字 → 必須 scope 在健康卡內查）
    ['發電機', '齒輪箱', '變槳', '偏航', '塔筒', '葉片', '變頻器', '冷卻'].forEach(l => {
      expect(within(healthCard).getByText(l)).toBeInTheDocument();
    });
  });

  it('明細 8 個 tab 皆渲染，預設「總覽」aria-pressed', async () => {
    await renderDetail({});
    const overviewTab = screen.getByRole('button', { name: '總覽' });
    expect(overviewTab).toHaveAttribute('aria-pressed', 'true');
    ['發電機', '旋角系統', '變頻器', '機艙', '轉向系統', '電網/氣象', '載荷/疲勞'].forEach(l => {
      expect(screen.getByRole('button', { name: l })).toBeInTheDocument();
    });
  });

  it('點明細 tab → 切換 aria-pressed + 顯示該 tab 內容', async () => {
    await renderDetail({ turbine: makeTurbine({ genSpeed: 1500, voltage: 690 }) });
    const genTab = screen.getByRole('button', { name: '發電機' });
    fireEvent.click(genTab);
    expect(genTab).toHaveAttribute('aria-pressed', 'true');
    // generator tab 標題（SubsystemSection title）
    expect(screen.getByText('WGEN Generator')).toBeInTheDocument();
    // 轉速值（0 位）
    expect(screen.getByText(/1500 RPM/)).toBeInTheDocument();
  });

  it('明細缺值 → DataRow 顯示「—」fallback', async () => {
    await renderDetail({ turbine: makeTurbine({ genPower: undefined, genSpeed: undefined }) });
    // overview WGEN Power（fmt undefined → —）
    expect(screen.getAllByText(/—/).length).toBeGreaterThan(0);
  });

  it('lang=en → 明細 tab 走英文', async () => {
    await renderDetail({ lang: 'en' });
    expect(screen.getByRole('button', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Load/Fatigue' })).toBeInTheDocument();
  });
});

// ─── TrendChartPanel 接線 ───────────────────────────────────────────────────

describe('TurbineDetail — 詳細趨勢面板接線', () => {
  it('TrendChartPanel 收到 padding 後的 turbineApiId（WT007）', async () => {
    await renderDetail({ turbine: makeTurbine({ id: 7 }) });
    const panel = screen.getByTestId('trend-chart-panel');
    expect(panel).toHaveAttribute('data-turbine', 'WT007');
  });

  it('id padding 至三位（id=12 → WT012）', async () => {
    await renderDetail({ turbine: makeTurbine({ id: 12 }) });
    expect(screen.getByTestId('trend-chart-panel')).toHaveAttribute('data-turbine', 'WT012');
  });

  it('lang prop 傳遞給 TrendChartPanel', async () => {
    await renderDetail({ lang: 'en' });
    expect(screen.getByTestId('trend-chart-panel')).toHaveAttribute('data-lang', 'en');
  });
});

// ─── OperatorControlCard ────────────────────────────────────────────────────

describe('TurbineDetail — 操作控制卡', () => {
  it('掛載即以 padding 後 id GET 控制狀態', async () => {
    const spy = stubFetch({});
    await renderDetail({ turbine: makeTurbine({ id: 7 }) });
    expect(spy).toHaveBeenCalledWith('http://localhost:8100/api/control/WT007/status');
  });

  it('6 個指令按鈕 + 限載設定鈕皆渲染', async () => {
    await renderDetail({});
    expect(screen.getByRole('button', { name: '▶ 啟動' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '■ 正常停機' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '⚠ 緊急停機' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '復位' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '進入定檢' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '設定限載' })).toBeInTheDocument();
  });

  it('service_mode=true → 顯示定檢模式 pill + 按鈕變「結束定檢」', async () => {
    stubFetch({ service_mode: true });
    await renderDetail({});
    expect(screen.getByText('定檢模式')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '結束定檢' })).toBeInTheDocument();
  });

  it('operator_stop=true → 手動停機 pill', async () => {
    stubFetch({ operator_stop: true });
    await renderDetail({});
    expect(screen.getByText('手動停機')).toBeInTheDocument();
  });

  it('stop_mode=emergency → 緊急停機 pill', async () => {
    stubFetch({ stop_mode: 'emergency' });
    await renderDetail({});
    expect(screen.getByText('緊急停機')).toBeInTheDocument();
  });

  it('curtailment_kw 有值 → 限載 pill + 解除鈕', async () => {
    stubFetch({ curtailment_kw: 1500 });
    await renderDetail({});
    expect(screen.getByText('限載 1500 kW')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '解除' })).toBeInTheDocument();
  });

  it('shutdown_cause 非 idle → 顯示原因 pill', async () => {
    stubFetch({ shutdown_cause: 'grid_loss' });
    await renderDetail({});
    expect(screen.getByText('原因：grid_loss')).toBeInTheDocument();
  });

  it('shutdown_cause=idle → 不顯示原因 pill', async () => {
    stubFetch({ shutdown_cause: 'idle' });
    await renderDetail({});
    expect(screen.queryByText(/原因：/)).not.toBeInTheDocument();
  });

  it('點啟動 → POST start 指令 + 顯示 OK 訊息 pill', async () => {
    const spy = stubFetch({});
    await renderDetail({ turbine: makeTurbine({ id: 7 }) });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '▶ 啟動' }));
    });
    expect(spy).toHaveBeenCalledWith(
      'http://localhost:8100/api/control/command',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ turbineId: 'WT007', command: 'start' }),
      }),
    );
    expect(screen.getByText('start OK')).toBeInTheDocument();
  });

  it('點緊急停機 → POST emergency_stop 指令', async () => {
    const spy = stubFetch({});
    await renderDetail({ turbine: makeTurbine({ id: 7 }) });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '⚠ 緊急停機' }));
    });
    expect(spy).toHaveBeenCalledWith(
      'http://localhost:8100/api/control/command',
      expect.objectContaining({
        body: JSON.stringify({ turbineId: 'WT007', command: 'emergency_stop' }),
      }),
    );
  });

  it('進入定檢 → POST service_on（service_mode=false 時）', async () => {
    const spy = stubFetch({ service_mode: false });
    await renderDetail({ turbine: makeTurbine({ id: 7 }) });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '進入定檢' }));
    });
    expect(spy).toHaveBeenCalledWith(
      'http://localhost:8100/api/control/command',
      expect.objectContaining({
        body: JSON.stringify({ turbineId: 'WT007', command: 'service_on' }),
      }),
    );
  });

  it('設定限載 → POST curtail 帶 parseFloat 後的 powerLimitKw', async () => {
    const spy = stubFetch({});
    await renderDetail({ turbine: makeTurbine({ id: 7 }) });
    const input = screen.getByPlaceholderText('限載 kW');
    fireEvent.change(input, { target: { value: '1200' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '設定限載' }));
    });
    expect(spy).toHaveBeenCalledWith(
      'http://localhost:8100/api/control/curtail',
      expect.objectContaining({
        body: JSON.stringify({ turbineId: 'WT007', powerLimitKw: 1200 }),
      }),
    );
  });

  it('空限載值設定 → powerLimitKw 送 null（解除）', async () => {
    const spy = stubFetch({});
    await renderDetail({ turbine: makeTurbine({ id: 7 }) });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '設定限載' }));
    });
    expect(spy).toHaveBeenCalledWith(
      'http://localhost:8100/api/control/curtail',
      expect.objectContaining({
        body: JSON.stringify({ turbineId: 'WT007', powerLimitKw: null }),
      }),
    );
  });

  it('點解除限載 → POST curtail null', async () => {
    const spy = stubFetch({ curtailment_kw: 1500 });
    await renderDetail({ turbine: makeTurbine({ id: 7 }) });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '解除' }));
    });
    expect(spy).toHaveBeenCalledWith(
      'http://localhost:8100/api/control/curtail',
      expect.objectContaining({
        body: JSON.stringify({ turbineId: 'WT007', powerLimitKw: null }),
      }),
    );
  });
});

// ─── 最近事件 ────────────────────────────────────────────────────────────────

describe('TurbineDetail — 最近事件', () => {
  it('OPERATING + 無故障 + 低風速 → 顯示「併網中」事件', async () => {
    await renderDetail({
      turbine: makeTurbine({ status: TurbineStatus.OPERATING, windSpeed: 6, activeFaults: [] }),
    });
    expect(screen.getByText('併網中')).toBeInTheDocument();
  });

  it('IDLE → 顯示「待機」事件', async () => {
    await renderDetail({
      turbine: makeTurbine({ status: TurbineStatus.IDLE, windSpeed: 6, activeFaults: [] }),
    });
    // header pill +「最近事件」待機事件兩處皆「待機」→ 斷言 >=2 同時守住事件卡渲染
    expect(screen.getAllByText('待機').length).toBeGreaterThanOrEqual(2);
  });

  it('高風速（>12）→ 顯示「高風速」事件', async () => {
    await renderDetail({ turbine: makeTurbine({ windSpeed: 14, activeFaults: [] }) });
    expect(screen.getByText('高風速')).toBeInTheDocument();
  });

  it('OFFLINE + 無故障 + 低風速 → 無事件 placeholder', async () => {
    await renderDetail({
      turbine: makeTurbine({ status: TurbineStatus.OFFLINE, windSpeed: 5, activeFaults: [] }),
    });
    expect(screen.getByText('目前無事件。')).toBeInTheDocument();
  });
});

// ─── AI 故障診斷卡 ───────────────────────────────────────────────────────────

describe('TurbineDetail — AI 故障診斷卡', () => {
  it('非 FAULT → 不渲染 AI 診斷卡', async () => {
    await renderDetail({ turbine: makeTurbine({ status: TurbineStatus.OPERATING }) });
    expect(screen.queryByText('AI 故障診斷')).not.toBeInTheDocument();
  });

  it('FAULT → 渲染 AI 診斷卡並自動分析（呼 analyzeTurbineFault）', async () => {
    const t = makeTurbine({ status: TurbineStatus.FAULT });
    await renderDetail({ turbine: t });
    expect(screen.getByText('AI 故障診斷')).toBeInTheDocument();
    expect(mockAnalyze).toHaveBeenCalledTimes(1);
    expect(mockAnalyze).toHaveBeenCalledWith(t);
    // 自動分析結果回填
    expect(screen.getByText(/建議檢查 NDE 側軸承潤滑/)).toBeInTheDocument();
  });

  it('點重新分析 → 再呼 analyze 並更新結果', async () => {
    mockAnalyze.mockResolvedValueOnce('第一次結果').mockResolvedValueOnce('第二次結果');
    await renderDetail({ turbine: makeTurbine({ status: TurbineStatus.FAULT }) });
    expect(screen.getByText('第一次結果')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '重新分析' }));
    });
    expect(mockAnalyze).toHaveBeenCalledTimes(2);
    expect(screen.getByText('第二次結果')).toBeInTheDocument();
  });

  it('分析失敗 → 顯示錯誤訊息', async () => {
    mockAnalyze.mockRejectedValue(new Error('boom'));
    await renderDetail({ turbine: makeTurbine({ status: TurbineStatus.FAULT }) });
    expect(screen.getByText('分析失敗，請重試。')).toBeInTheDocument();
  });

  it('有結果且無 activeWorkOrder → 派遣鈕可用，點按帶結果呼 onDispatch', async () => {
    mockAnalyze.mockResolvedValue('診斷：軸承磨損');
    const t = makeTurbine({ status: TurbineStatus.FAULT });
    const { onDispatch } = await renderDetail({ turbine: t });
    const dispatchBtn = screen.getByRole('button', { name: '派遣技術員' });
    // 派遣鈕在 auto-analyze 結果寫入 state 後才解除 disabled → waitFor 等 effect 鏈 settle
    await waitFor(() => expect(dispatchBtn).not.toBeDisabled());
    fireEvent.click(dispatchBtn);
    expect(onDispatch).toHaveBeenCalledWith(t, '診斷：軸承磨損');
  });

  it('有 activeWorkOrder → 顯示「工單處理中」pill 取代派遣鈕', async () => {
    await renderDetail({
      turbine: makeTurbine({ status: TurbineStatus.FAULT }),
      activeWorkOrder: makeWorkOrder({ id: 'wo-abcd1234' }),
    });
    expect(screen.getByText(/工單 #1234 處理中/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '派遣技術員' })).not.toBeInTheDocument();
  });

  it('lang=en → AI 卡走英文標題與按鈕', async () => {
    await renderDetail({ turbine: makeTurbine({ status: TurbineStatus.FAULT }), lang: 'en' });
    expect(screen.getByText('AI Fault Diagnosis')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dispatch technician' })).toBeInTheDocument();
  });
});

// ─── 為何不發電（#3 狀態可見性，WMOM-20260718-04）───────────────────────────

describe('noPowerReason（純函式）', () => {
  const base = { powerOutput: 0, windSpeed: 10, status: TurbineStatus.IDLE, turState: 1 };

  it('有發電（>0.05 MW）→ null（不解釋）', () => {
    expect(noPowerReason({ ...base, powerOutput: 1.5 })).toBeNull();
  });

  it('故障 → warn「故障跳機」（優先於風速/狀態）', () => {
    const r = noPowerReason({ ...base, status: TurbineStatus.FAULT, windSpeed: 27 });
    expect(r?.tone).toBe('warn');
    expect(r?.zh).toContain('故障跳機');
  });

  it('緊急停機（turState 7）→ warn', () => {
    const r = noPowerReason({ ...base, turState: 7 });
    expect(r?.tone).toBe('warn');
    expect(r?.zh).toContain('緊急停機');
  });

  it('切出風速（>25）→ amber「切出風速」', () => {
    const r = noPowerReason({ ...base, windSpeed: 27 });
    expect(r?.tone).toBe('amber');
    expect(r?.zh).toContain('切出風速');
  });

  it('低於切入（<3）→ amber「待風」', () => {
    const r = noPowerReason({ ...base, windSpeed: 2 });
    expect(r?.tone).toBe('amber');
    expect(r?.zh).toContain('待風');
  });

  it('停機（turState 9）→ amber「停機中」', () => {
    expect(noPowerReason({ ...base, turState: 9 })?.zh).toContain('停機中');
  });

  it('待機（turState 2）→ amber「待機中」', () => {
    expect(noPowerReason({ ...base, turState: 2 })?.zh).toContain('待機中');
  });

  it('離線（status OFFLINE，無其他線索）→ amber「離線」', () => {
    expect(noPowerReason({ ...base, status: TurbineStatus.OFFLINE, turState: 6 })?.zh).toContain('離線');
  });
});

describe('TurbineDetail — 為何不發電 chip', () => {
  it('正常發電 → 不顯示 chip', async () => {
    await renderDetail({ turbine: makeTurbine({ powerOutput: 2.34 }) });
    expect(screen.queryByText(/為何不發電/)).not.toBeInTheDocument();
  });

  it('切出風速（power 0 + wind 27）→ 顯示 chip 說明', async () => {
    await renderDetail({ turbine: makeTurbine({ powerOutput: 0, windSpeed: 27, status: TurbineStatus.IDLE }) });
    expect(screen.getByText(/為何不發電/)).toBeInTheDocument();
    expect(screen.getByText(/切出風速/)).toBeInTheDocument();
  });

  it('故障跳機（power 0 + FAULT）→ 顯示 chip', async () => {
    await renderDetail({ turbine: makeTurbine({ powerOutput: 0, status: TurbineStatus.FAULT }) });
    expect(screen.getByText(/故障跳機/)).toBeInTheDocument();
  });

  it('lang=en cut-out → 英文說明', async () => {
    await renderDetail({ turbine: makeTurbine({ powerOutput: 0, windSpeed: 27, status: TurbineStatus.IDLE }), lang: 'en' });
    expect(screen.getByText(/Why no power/)).toBeInTheDocument();
    expect(screen.getByText(/Cut-out wind/)).toBeInTheDocument();
  });
});
