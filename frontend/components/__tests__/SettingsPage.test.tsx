/**
 * SettingsPage component render 測試（WMOM-20260604-06，EPIC-M5 測試覆蓋擴大）。
 *
 * `/admin/settings` 系統設定面板先前頁面層零覆蓋。本檔延續 CostPage / FarmOverview
 * 已落地的 render 測試範式（ThemeProvider 包裹 + jest-dom matcher + afterEach
 * cleanup + global.fetch stub + `await act(async)` flush mount effect），守住
 * SettingsPage 的 UX 契約：
 *
 *   - 基本渲染 + 語系（zh / en 標題與 Save 按鈕）
 *   - dataSource 驅動條件區塊（MOCK / SIMULATION / OPC_DA / MODBUS_TCP）
 *   - dataSource Select 切換 → 條件區塊即時更新（onChange → formData）
 *   - settings prop 同步（rerender → useEffect [settings] → setFormData）
 *   - Save（type=submit）→ onSave 接線 + 「已儲存」pill
 *   - backend down → 「無法連線到後端 API」warn card
 *   - wind status 顯示 / wind profile 按鈕 POST + aria-pressed
 *   - custom wind 套用 POST（解析數值 body）
 *   - grid profile 按鈕 POST
 *   - turbine spec presets 渲染 / apply spec POST
 *
 * SettingsPage 純 props（settings / onSave / lang）+ fetch 驅動，無 stateful
 * hook 依賴；ui primitive（Btn / Card / Field / Input / Select / PageHeader /
 * StatusPill）真渲染（產生正確 role），僅 stub global.fetch（4 GET config
 * endpoint + 3 POST；未預期 URL/method 直接 reject，不靜默吞掉新 API 呼叫）。
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';
import React from 'react';
import SettingsPage from '../SettingsPage';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { type AppSettings, DataSourceType } from '../../types';
import type { SourceMode } from '../../hooks/useSourceGate';
import { setAuthToken, clearAuthToken } from '../../services/authClient';

// ─── fixtures（型別嚴格，不用 as 強轉）─────────────────────────────────────

/** 結構式滿足 AppSettings；任一欄位漂移 tsc 即編譯失敗，而非靜默假綠。 */
function makeSettings(dataSource: DataSourceType = DataSourceType.MOCK): AppSettings {
  return {
    dataSource,
    opcDa: { server: 'localhost', progId: 'BACHMANN.OPCEnterpriseServer.2' },
    modbusTcp: { ip: '10.128.1.12', port: 502, slaveId: 1 },
    simulation: { turbineCount: 21, baseWindSpeed: 8, turbulenceIntensity: 0.1 },
  };
}

const WIND_STATUS = { mode: 'profile', profile: 'moderate', override_wind_speed: 8 };
const GRID_STATUS = { mode: 'nominal', profile: 'nominal' };
const SPEC = {
  rated_power_kw: 5000,
  rotor_diameter: 126,
  cut_in_speed: 3,
  rated_speed: 12,
  cut_out_speed: 25,
  gear_ratio: 100,
  max_rotor_rpm: 15,
  nominal_voltage: 690,
  curtailment_kw: null,
};
const PRESETS = {
  'Z72-2MW': { ...SPEC, rated_power_kw: 2000 },
  'V90-3MW': { ...SPEC, rated_power_kw: 3000 },
};

// ─── global.fetch 路由 ─────────────────────────────────────────────────────

const fetchMock = vi.fn();

function okJson(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

/**
 * 已知 config endpoint 回對應 body；未知 URL/method reject（不靜默吞）。
 * 注意：presets 是 turbine-spec 的超字串，先判 presets 避免誤命中。
 */
function defaultFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = String(input);
  const method = (init?.method ?? 'GET').toUpperCase();
  if (method === 'GET') {
    // 預設來源＝simulation → 風況/電網/機組即時調整可用（既有 SIMULATION 測試維持有效）。
    if (url.includes('/api/source/status')) return Promise.resolve(okJson({ active: true, kind: 'simulation', mode: 'simulation' }));
    if (url.includes('/api/config/wind')) return Promise.resolve(okJson(WIND_STATUS));
    if (url.includes('/api/config/grid')) return Promise.resolve(okJson(GRID_STATUS));
    if (url.includes('/api/config/turbine-spec/presets')) return Promise.resolve(okJson(PRESETS));
    if (url.includes('/api/config/turbine-spec')) return Promise.resolve(okJson(SPEC));
  } else if (method === 'POST') {
    // turbine-spec POST 回 { spec }（handleSetPreset / handleApplySpec 讀 data.spec）；
    // wind / grid POST 只需 ok。
    if (url.includes('/api/config/turbine-spec')) return Promise.resolve(okJson({ spec: SPEC }));
    if (url.includes('/api/config/wind') || url.includes('/api/config/grid')) {
      return Promise.resolve(okJson({}));
    }
  }
  return Promise.reject(new Error(`Unexpected fetch in test: ${method} ${url}`));
}

/** 從 fetchMock 過濾出某 URL 片段的 POST 呼叫之 body（避開 mount 的多次 GET）。 */
function postBodies(urlPart: string): Array<Record<string, unknown>> {
  return fetchMock.mock.calls
    .filter(
      ([u, init]) =>
        String(u).includes(urlPart) &&
        ((init as RequestInit | undefined)?.method ?? 'GET').toUpperCase() === 'POST',
    )
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)) as Record<string, unknown>);
}

function lastPostBody(urlPart: string): Record<string, unknown> | null {
  const bodies = postBodies(urlPart);
  return bodies.length ? bodies[bodies.length - 1] : null;
}

/**
 * 有狀態的 config fetch：POST {profile} 後，後續 wind/grid GET 反映新 profile，
 * 模擬真實後端（套用情境後狀態變更）。供 profile 按鈕測試守住「切換後舊 active
 * 按鈕變 inactive」的互斥契約——若用固定 mock，舊 profile 會永遠 active，
 * 雙重 active 的 bug 會被靜默放行。
 */
function statefulConfigFetch(): typeof defaultFetch {
  let windProfile = WIND_STATUS.profile;
  let gridProfile = GRID_STATUS.profile;
  return (input, init) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    if (method === 'POST' && url.includes('/api/config/wind')) {
      const body = init?.body ? (JSON.parse(String(init.body)) as { profile?: string }) : {};
      if (typeof body.profile === 'string') windProfile = body.profile;
      return Promise.resolve(okJson({}));
    }
    if (method === 'POST' && url.includes('/api/config/grid')) {
      const body = init?.body ? (JSON.parse(String(init.body)) as { profile?: string }) : {};
      if (typeof body.profile === 'string') gridProfile = body.profile;
      return Promise.resolve(okJson({}));
    }
    if (method === 'GET' && url.includes('/api/config/wind')) {
      return Promise.resolve(okJson({ mode: 'profile', profile: windProfile, override_wind_speed: 8 }));
    }
    if (method === 'GET' && url.includes('/api/config/grid')) {
      return Promise.resolve(okJson({ mode: 'profile', profile: gridProfile }));
    }
    return defaultFetch(input, init);
  };
}

/** defaultFetch 但 /api/source/status 回指定 kind（測「風況/電網/機組依實際來源 gate」）。 */
function sourceKindFetch(kind: SourceMode): typeof defaultFetch {
  return (input, init) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    if (method === 'GET' && url.includes('/api/source/status')) {
      return Promise.resolve(okJson({ active: true, kind, mode: kind === 'view' ? null : kind }));
    }
    return defaultFetch(input, init);
  };
}

// ─── render helper ─────────────────────────────────────────────────────────

interface RenderResult {
  onSave: ReturnType<typeof vi.fn>;
  rerender: (settings: AppSettings, lang?: 'en' | 'zh') => Promise<void>;
}

/**
 * 以 ThemeProvider 包裹 render，`act(async)` flush mount 的 4 條 config fetch
 * effect（wind / grid / turbine-spec / presets），避免 setState not wrapped in
 * act() 警告污染輸出。回傳 onSave spy 與 rerender helper（測 settings prop 同步）。
 */
async function renderSettings(
  settings: AppSettings = makeSettings(),
  lang: 'en' | 'zh' = 'zh',
): Promise<RenderResult> {
  const onSave = vi.fn();
  // definite assignment（!）：result 在 await act 完成後才被 rerender 閉包引用，
  // 明確告知 TS 此處保證已賦值，不依賴編譯器對 await-through closure 的容忍。
  let result!: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      <ThemeProvider>
        <SettingsPage settings={settings} onSave={onSave} lang={lang} />
      </ThemeProvider>,
    );
  });
  const rerender = async (next: AppSettings, nextLang: 'en' | 'zh' = lang) => {
    await act(async () => {
      result.rerender(
        <ThemeProvider>
          <SettingsPage settings={next} onSave={onSave} lang={nextLang} />
        </ThemeProvider>,
      );
    });
  };
  return { onSave, rerender };
}

describe('SettingsPage 系統設定面板', () => {
  beforeEach(() => {
    // fake timers：攔截 handler 內的 standalone setTimeout（清訊息 / saveStatus 回 idle）
    // 與元件的 5s setInterval，避免測試結束後真實計時器仍對已 unmount 元件 setState
    // （CI 平行 runner flaky 來源）。fake timers 只攔截 timer，不動 Promise microtask，
    // 故 `await act(async)` 仍能正常 flush fetch mock 的 .then 鏈。
    vi.useFakeTimers();
    fetchMock.mockReset();
    fetchMock.mockImplementation(defaultFetch);
    vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);
  });

  afterEach(() => {
    // 先 cleanup（unmount → 觸發 clearInterval 清除輪詢），再 clearAllTimers 丟棄
    // 仍 pending 的 handler setTimeout（不執行其 setState），最後還原真實計時器。
    cleanup();
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  // ── 基本渲染 + 語系 ────────────────────────────────────────────────────

  it('預設渲染（zh）：標題「系統設定」+ Save 按鈕 +「資料源」與「API 端點」區塊', async () => {
    await renderSettings();
    expect(screen.getByText('系統設定')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '儲存設定' })).toBeInTheDocument();
    // Section 標題「資料源」與恆在的「API 端點」資訊區塊
    expect(screen.getByRole('heading', { name: '資料源' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'API 端點' })).toBeInTheDocument();
    expect(screen.getByText('GET /api/turbines — All turbines')).toBeInTheDocument();
  });

  it('lang=en → 標題與 Save 按鈕顯示英文', async () => {
    await renderSettings(makeSettings(), 'en');
    expect(screen.getByText('Settings')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save settings' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Data source' })).toBeInTheDocument();
    // negative：不應出現中文標題（守 u() 映射未對調）
    expect(screen.queryByText('系統設定')).not.toBeInTheDocument();
  });

  // ── dataSource 驅動條件區塊 ────────────────────────────────────────────

  it('MOCK → 不渲染 模擬 / OPC / Modbus 條件區塊', async () => {
    await renderSettings(makeSettings(DataSourceType.MOCK));
    expect(screen.queryByRole('heading', { name: '模擬參數' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'OPC DA 伺服器' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Modbus TCP 閘道' })).not.toBeInTheDocument();
  });

  it('SIMULATION → 渲染 模擬參數 + 風機規格 + 風況控制 + 電網控制 四區塊', async () => {
    await renderSettings(makeSettings(DataSourceType.SIMULATION));
    expect(screen.getByRole('heading', { name: '模擬參數' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '風機規格' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '風況控制' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '電網控制' })).toBeInTheDocument();
    // 非 OPC/Modbus
    expect(screen.queryByRole('heading', { name: 'OPC DA 伺服器' })).not.toBeInTheDocument();
  });

  it('OPC_DA → 渲染 OPC DA 區塊（含 ProgID）、不渲染模擬區塊', async () => {
    await renderSettings(makeSettings(DataSourceType.OPC_DA));
    expect(screen.getByRole('heading', { name: 'OPC DA 伺服器' })).toBeInTheDocument();
    expect(screen.getByText('ProgID')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '模擬參數' })).not.toBeInTheDocument();
  });

  it('MODBUS_TCP → 渲染 Modbus 區塊（IP / 埠號 / Slave ID）', async () => {
    await renderSettings(makeSettings(DataSourceType.MODBUS_TCP));
    expect(screen.getByRole('heading', { name: 'Modbus TCP 閘道' })).toBeInTheDocument();
    expect(screen.getByText('Slave ID')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '模擬參數' })).not.toBeInTheDocument();
  });

  // ── dataSource Select 切換 → 條件區塊更新 ──────────────────────────────

  it('Select 改 dataSource（MOCK→SIMULATION）→ 模擬參數區塊即時出現', async () => {
    await renderSettings(makeSettings(DataSourceType.MOCK));
    expect(screen.queryByRole('heading', { name: '模擬參數' })).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.change(screen.getByRole('combobox', { name: '資料源' }), {
        target: { value: DataSourceType.SIMULATION },
      });
    });
    expect(screen.getByRole('heading', { name: '模擬參數' })).toBeInTheDocument();
  });

  // ── settings prop 同步（useEffect [settings]）──────────────────────────

  it('rerender 換 settings（MOCK→OPC_DA）→ 條件區塊隨 prop 同步更新', async () => {
    const { rerender } = await renderSettings(makeSettings(DataSourceType.MOCK));
    expect(screen.queryByRole('heading', { name: 'OPC DA 伺服器' })).not.toBeInTheDocument();
    await rerender(makeSettings(DataSourceType.OPC_DA));
    expect(screen.getByRole('heading', { name: 'OPC DA 伺服器' })).toBeInTheDocument();
  });

  // ── Save 接線 ──────────────────────────────────────────────────────────

  it('點「儲存設定」（type=submit）→ onSave 帶「已套用 formData 的值（非原始 prop）」+「已儲存」pill', async () => {
    const settings = makeSettings(DataSourceType.SIMULATION);
    const { onSave } = await renderSettings(settings);

    // 先改一個欄位（dataSource SIMULATION→OPC_DA），讓 formData 與原始 settings prop
    // 產生可量測差異——否則 formData 初值即 settings 拷貝，deep-equal 會讓
    // onSave(settings_prop) 的 bug 也通過（false positive）。
    await act(async () => {
      fireEvent.change(screen.getByRole('combobox', { name: '資料源' }), {
        target: { value: DataSourceType.OPC_DA },
      });
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '儲存設定' }));
    });

    expect(onSave).toHaveBeenCalledTimes(1);
    // 守住「提交的是 formData（已含使用者改動）而非原始 prop」契約。
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ dataSource: DataSourceType.OPC_DA }),
    );
    expect(screen.getByText('已儲存')).toBeInTheDocument();
  });

  // ── backend down ───────────────────────────────────────────────────────

  it('wind GET reject → apiConnected false → 顯示「無法連線到後端 API」warn card', async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? 'GET').toUpperCase();
      if (method === 'GET' && url.includes('/api/config/wind')) {
        return Promise.reject(new Error('backend down'));
      }
      return defaultFetch(input, init);
    });
    await renderSettings();
    expect(screen.getByText('無法連線到後端 API')).toBeInTheDocument();
  });

  // ── wind status 顯示 + wind profile 按鈕 ───────────────────────────────

  it('mount wind GET resolve → 風況控制顯示「模式」標籤與 mode 值', async () => {
    await renderSettings(makeSettings(DataSourceType.SIMULATION));
    // 同時守標籤節點（模式）與 windStatus.mode='profile' 值，避免拿掉標籤仍假綠。
    // 風況控制 + 電網控制兩區塊都顯示「模式」標籤 → getAllByText（≥1）；mode 值 'profile'
    // 為 wind 獨有（grid mode 為 'nominal'）故 getByText 精確命中。
    expect(screen.getAllByText(/模式/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('profile')).toBeInTheDocument();
  });

  it('點 wind profile 按鈕「平靜 (2 m/s)」→ POST {profile:calm}；切換後「平靜」pressed、「中等」不再 pressed', async () => {
    // 用有狀態 fetch：POST 後 wind GET 反映新 profile，守住切換互斥（舊 active 變 inactive）。
    fetchMock.mockImplementation(statefulConfigFetch());
    await renderSettings(makeSettings(DataSourceType.SIMULATION));
    // mount 後 windStatus.profile='moderate' → 「中等 (8 m/s)」初始 active。
    expect(screen.getByRole('button', { name: '中等 (8 m/s)' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '平靜 (2 m/s)' }));
    });
    expect(lastPostBody('/api/config/wind')).toEqual({ profile: 'calm' });
    // 重新查詢取 re-render 後最新節點：平靜 pressed、中等不再 pressed（互斥）。
    expect(screen.getByRole('button', { name: '平靜 (2 m/s)' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: '中等 (8 m/s)' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('點「套用自訂風況」→ POST /api/config/wind 帶解析後數值 body', async () => {
    await renderSettings(makeSettings(DataSourceType.SIMULATION));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '套用自訂風況' }));
    });
    // customWind 預設 { speed:'10', direction:'270', temp:'25', turbulence:'0.1' }
    expect(lastPostBody('/api/config/wind')).toEqual({
      windSpeed: 10,
      windDirection: 270,
      ambientTemp: 25,
      turbulence: 0.1,
    });
  });

  // ── grid profile / custom grid 按鈕 ────────────────────────────────────

  it('點 grid profile 按鈕「低頻」→ POST {profile:low_freq}；切換後「低頻」pressed、「標稱」不再 pressed', async () => {
    // 同 wind：有狀態 fetch 守住 grid profile 切換互斥（gridStatus.profile 初始 nominal）。
    fetchMock.mockImplementation(statefulConfigFetch());
    await renderSettings(makeSettings(DataSourceType.SIMULATION));
    expect(screen.getByRole('button', { name: '標稱' })).toHaveAttribute('aria-pressed', 'true');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '低頻' }));
    });
    expect(lastPostBody('/api/config/grid')).toEqual({ profile: 'low_freq' });
    expect(screen.getByRole('button', { name: '低頻' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '標稱' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('點「套用自訂電網」→ POST /api/config/grid 帶解析後數值 body', async () => {
    await renderSettings(makeSettings(DataSourceType.SIMULATION));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '套用自訂電網' }));
    });
    // customGrid 預設 { frequency:'50.0', voltage:'690' }
    expect(lastPostBody('/api/config/grid')).toEqual({ frequencyHz: 50.0, voltageV: 690 });
  });

  // ── turbine spec presets + apply ───────────────────────────────────────

  it('presets GET resolve → 預設機型按鈕（名稱 + kW）渲染', async () => {
    await renderSettings(makeSettings(DataSourceType.SIMULATION));
    expect(screen.getByRole('button', { name: /Z72-2MW \(2000kW\)/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /V90-3MW \(3000kW\)/ })).toBeInTheDocument();
  });

  it('點「套用風機規格」→ POST /api/config/turbine-spec 帶 editSpec payload（含 rated_power_kw）', async () => {
    await renderSettings(makeSettings(DataSourceType.SIMULATION));
    // Btn 的 accessible name 取 ariaLabel（'套用規格'），非可見文字（'套用風機規格'）。
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '套用規格' }));
    });
    const body = lastPostBody('/api/config/turbine-spec');
    expect(body).not.toBeNull();
    // editSpec 由 mount turbine-spec GET（SPEC）填充 → payload 含 rated_power_kw=5000、
    // 空字串的 curtailment_kw 轉 null。
    expect(body).toMatchObject({ rated_power_kw: 5000, curtailment_kw: null });
  });

  // ── 模擬設定（模擬參數/風況/電網/機組）依實際來源 gate（WMOM-20260720-06 / DEC-20260720-01）──
  it('來源為 view → 顯示「模擬設定目前不可調整」提示、隱藏模擬參數/風況/電網/機組四區塊', async () => {
    fetchMock.mockImplementation(sourceKindFetch('view'));
    await renderSettings(makeSettings(DataSourceType.SIMULATION));
    expect(screen.getByRole('heading', { name: '模擬設定目前不可調整' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '風況控制' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '電網控制' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '風機規格' })).not.toBeInTheDocument();
    // 模擬參數也一併 gate（review Must-fix）：view/live 下按儲存若 sim 參數有變會 POST
    // /api/config/simulation → 後端 switch_mode 悄悄把來源切回 simulation。藏起就無從觸發。
    expect(screen.queryByRole('heading', { name: '模擬參數' })).not.toBeInTheDocument();
  });

  it('來源為 live → 提示文案點明「會中斷現場 SCADA 連線」', async () => {
    fetchMock.mockImplementation(sourceKindFetch('live'));
    await renderSettings(makeSettings(DataSourceType.SIMULATION));
    const notice = screen.getByRole('heading', { name: '模擬設定目前不可調整' });
    expect(notice).toBeInTheDocument();
    expect(screen.getByText(/中斷現場 SCADA 連線/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '模擬參數' })).not.toBeInTheDocument();
  });

  it('來源為 scenario（產生情境）→ 同樣擋掉即時調整（情境風況於生成時設定）', async () => {
    fetchMock.mockImplementation(sourceKindFetch('scenario'));
    await renderSettings(makeSettings(DataSourceType.SIMULATION));
    expect(screen.getByRole('heading', { name: '模擬設定目前不可調整' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '模擬參數' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '風況控制' })).not.toBeInTheDocument();
  });

  it('來源為 simulation → 顯示模擬參數/風況/電網/機組區塊、不顯示 gate 提示', async () => {
    // defaultFetch 已回 kind=simulation。
    await renderSettings(makeSettings(DataSourceType.SIMULATION));
    expect(screen.getByRole('heading', { name: '模擬參數' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '風況控制' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '電網控制' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '模擬設定目前不可調整' })).not.toBeInTheDocument();
  });

  it('來源查詢失敗（fail-open）→ 仍顯示模擬參數/風況控制，不因查不到就藏掉', async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? 'GET').toUpperCase();
      if (method === 'GET' && url.includes('/api/source/status')) return Promise.reject(new Error('down'));
      return defaultFetch(input, init);
    });
    await renderSettings(makeSettings(DataSourceType.SIMULATION));
    expect(screen.getByRole('heading', { name: '模擬參數' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '風況控制' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '模擬設定目前不可調整' })).not.toBeInTheDocument();
  });

  it('編輯模擬參數後來源在背景被切走（5 秒輪詢翻轉 gate）→ 儲存不夾帶 stale 值', async () => {
    // review Must-fix 回歸 + 覆蓋 5 秒輪詢：先 simulation（模擬參數可編輯）→ 改風機數 99（未存）→
    // 輪詢後來源改回 view（gate 翻真、Section 隱藏）→ 儲存時應把模擬參數還原成 settings，避免
    // useSettings 偵測到 simChanged → POST /api/config/simulation → 後端 switch_mode 切回 simulation。
    let kind = 'simulation';
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? 'GET').toUpperCase();
      if (method === 'GET' && url.includes('/api/source/status')) {
        return Promise.resolve(okJson({ active: true, kind, mode: kind === 'view' ? null : kind }));
      }
      return defaultFetch(input, init);
    });
    const { onSave } = await renderSettings(makeSettings(DataSourceType.SIMULATION));
    // 模擬參數可見 → 把「風機數」改成 99（未存）。
    await act(async () => {
      fireEvent.change(screen.getByLabelText('風機數'), { target: { value: '99' } });
    });
    expect(screen.getByRole('heading', { name: '模擬參數' })).toBeInTheDocument();
    // 來源被別處切走 → view；推進 5 秒讓輪詢抓到 → gate 翻轉、Section 隱藏。
    kind = 'view';
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(screen.queryByRole('heading', { name: '模擬參數' })).not.toBeInTheDocument();
    // 按儲存 → onSave 收到的 simulation 應為原始 settings（21），非 stale 的 99。
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '儲存設定' }));
    });
    expect(onSave).toHaveBeenCalledTimes(1);
    const saved = onSave.mock.calls[0][0] as AppSettings;
    expect(saved.simulation.turbineCount).toBe(21);
  });

  // ── 改設定不重建表單 DOM（WMOM-20260720-05 回歸：捲動/焦點不被重置回頁頂）─────────
  it('改設定觸發 re-render → Section 不被 remount（同一 DOM 節點）', async () => {
    // 根因：Section 若定義在 render body 內，每次 re-render 產生新元件 identity → React 卸載並
    // 重建整個表單 DOM → 捲動位置/輸入焦點被重置回頁頂。用「恆在的『資料源』heading」當哨兵：
    // 觸發一次 re-render 後，若表單被重建，此節點會換成新的 DOM 參照。
    fetchMock.mockImplementation(statefulConfigFetch());
    await renderSettings(makeSettings(DataSourceType.SIMULATION));
    const before = screen.getByRole('heading', { name: '資料源' });
    // 點一個風況 profile 鈕 → setWindProfile → SettingsPage re-render（不改變區塊顯隱）。
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '平靜 (2 m/s)' }));
    });
    const after = screen.getByRole('heading', { name: '資料源' });
    // Section 穩定（module scope）→ 就地 reconcile → 同一節點；若退回 inline 定義則會是新節點。
    expect(after).toBe(before);
  });

  // ── authFetch 稽核（WMOM-20260923-10）────────────────────────────────────
  //
  // 上方既有測試皆用 `lastPostBody` / `defaultFetch` 比對 URL + method，對「裸 fetch
  // vs authFetch」不敏感（同款根因見 WMOM-20260923-07/-09/-20260924-01/-02）。故另補
  // 這組直接檢查 `Authorization` header 內容的專測，鎖住本次修復（11 處 fetch 呼叫皆
  // 改用 `authFetch`：5 條 GET 讀取端點後端掛 `require_authenticated()`，6 個 POST
  // 皆 `require_role(SUPERVISOR)` 寫入——風況/電網/機組規格設定變更）。

  function callsExact(urlSuffix: string, method: string): Array<[string, RequestInit | undefined]> {
    return fetchMock.mock.calls
      .filter(
        ([u, init]) =>
          String(u).endsWith(urlSuffix) &&
          ((init as RequestInit | undefined)?.method ?? 'GET').toUpperCase() === method,
      )
      .map(([u, init]) => [String(u), init as RequestInit | undefined]);
  }

  function authHeaderOf(init: RequestInit | undefined): string | undefined {
    return (init?.headers as Record<string, string> | undefined)?.Authorization;
  }

  describe('SettingsPage — authFetch 稽核（WMOM-20260923-10）', () => {
    it('已登入（有 token）→ mount 時 5 條 GET（wind/grid/source-status/turbine-spec/presets）皆帶 Authorization header', async () => {
      setAuthToken('test-token-mount');
      try {
        await renderSettings(makeSettings(DataSourceType.SIMULATION));
        for (const suffix of [
          '/api/config/wind',
          '/api/config/grid',
          '/api/source/status',
          '/api/config/turbine-spec',
          '/api/config/turbine-spec/presets',
        ]) {
          const calls = callsExact(suffix, 'GET');
          expect(calls).toHaveLength(1);
          expect(authHeaderOf(calls[0][1])).toBe('Bearer test-token-mount');
        }
      } finally {
        clearAuthToken();
      }
    });

    it('已登入（有 token）→ 套用風況 profile POST /api/config/wind 帶 Authorization header', async () => {
      setAuthToken('test-token-wind-profile');
      try {
        await renderSettings(makeSettings(DataSourceType.SIMULATION));
        await act(async () => {
          fireEvent.click(screen.getByRole('button', { name: '平靜 (2 m/s)' }));
        });
        const calls = callsExact('/api/config/wind', 'POST');
        expect(calls).toHaveLength(1);
        expect(authHeaderOf(calls[0][1])).toBe('Bearer test-token-wind-profile');
      } finally {
        clearAuthToken();
      }
    });

    it('已登入（有 token）→ 套用自訂風況 POST /api/config/wind 帶 Authorization header', async () => {
      setAuthToken('test-token-wind-custom');
      try {
        await renderSettings(makeSettings(DataSourceType.SIMULATION));
        await act(async () => {
          fireEvent.click(screen.getByRole('button', { name: '套用自訂風況' }));
        });
        const calls = callsExact('/api/config/wind', 'POST');
        expect(calls).toHaveLength(1);
        expect(authHeaderOf(calls[0][1])).toBe('Bearer test-token-wind-custom');
      } finally {
        clearAuthToken();
      }
    });

    it('已登入（有 token）→ 套用電網 profile POST /api/config/grid 帶 Authorization header', async () => {
      setAuthToken('test-token-grid-profile');
      try {
        await renderSettings(makeSettings(DataSourceType.SIMULATION));
        await act(async () => {
          fireEvent.click(screen.getByRole('button', { name: '低頻' }));
        });
        const calls = callsExact('/api/config/grid', 'POST');
        expect(calls).toHaveLength(1);
        expect(authHeaderOf(calls[0][1])).toBe('Bearer test-token-grid-profile');
      } finally {
        clearAuthToken();
      }
    });

    it('已登入（有 token）→ 套用自訂電網 POST /api/config/grid 帶 Authorization header', async () => {
      setAuthToken('test-token-grid-custom');
      try {
        await renderSettings(makeSettings(DataSourceType.SIMULATION));
        await act(async () => {
          fireEvent.click(screen.getByRole('button', { name: '套用自訂電網' }));
        });
        const calls = callsExact('/api/config/grid', 'POST');
        expect(calls).toHaveLength(1);
        expect(authHeaderOf(calls[0][1])).toBe('Bearer test-token-grid-custom');
      } finally {
        clearAuthToken();
      }
    });

    it('已登入（有 token）→ 套用機型 preset POST /api/config/turbine-spec 帶 Authorization header', async () => {
      setAuthToken('test-token-preset');
      try {
        await renderSettings(makeSettings(DataSourceType.SIMULATION));
        await act(async () => {
          fireEvent.click(screen.getByRole('button', { name: /Z72-2MW \(2000kW\)/ }));
        });
        const calls = callsExact('/api/config/turbine-spec', 'POST');
        expect(calls).toHaveLength(1);
        expect(authHeaderOf(calls[0][1])).toBe('Bearer test-token-preset');
      } finally {
        clearAuthToken();
      }
    });

    it('已登入（有 token）→ 套用風機規格 POST /api/config/turbine-spec 帶 Authorization header', async () => {
      setAuthToken('test-token-spec');
      try {
        await renderSettings(makeSettings(DataSourceType.SIMULATION));
        await act(async () => {
          fireEvent.click(screen.getByRole('button', { name: '套用規格' }));
        });
        const calls = callsExact('/api/config/turbine-spec', 'POST');
        expect(calls).toHaveLength(1);
        expect(authHeaderOf(calls[0][1])).toBe('Bearer test-token-spec');
      } finally {
        clearAuthToken();
      }
    });

    it('未登入（無 token）→ 5 條 GET + 6 個 POST 呼叫皆不帶 Authorization header（過渡期行為不變）', async () => {
      fetchMock.mockImplementation(statefulConfigFetch());
      await renderSettings(makeSettings(DataSourceType.SIMULATION));
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: '平靜 (2 m/s)' }));
      });
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: '套用自訂風況' }));
      });
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: '低頻' }));
      });
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: '套用自訂電網' }));
      });
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /Z72-2MW \(2000kW\)/ }));
      });
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: '套用規格' }));
      });
      const checks: Array<[string, string]> = [
        ['/api/config/wind', 'GET'],
        ['/api/config/grid', 'GET'],
        ['/api/source/status', 'GET'],
        ['/api/config/turbine-spec', 'GET'],
        ['/api/config/turbine-spec/presets', 'GET'],
        ['/api/config/wind', 'POST'],
        ['/api/config/grid', 'POST'],
        ['/api/config/turbine-spec', 'POST'],
      ];
      for (const [suffix, method] of checks) {
        const calls = callsExact(suffix, method);
        expect(calls.length).toBeGreaterThan(0);
        calls.forEach(([, init]) => expect(authHeaderOf(init)).toBeUndefined());
      }
    });
  });
});
