/**
 * FarmSelector component render 測試（WMOM-20260607-04，EPIC-M5 測試覆蓋擴大）。
 *
 * `FarmSelector.tsx`（532 行）是 sidebar 底部的「風場切換器 + 新增風場 modal」：
 *   - mount 時 GET `/api/farms` 取得 farms 清單 + active_farm_id
 *   - trigger 鈕顯示目前 active farm 名 + 額定 MW（無 active 時顯示「選擇風場 / Select farm」）
 *   - 點 trigger 向上彈出 dropdown（role=listbox）：列出每個 farm 名 / 台數 / MW / 地點，
 *     active farm 標 aria-selected + 「使用中 / Active」
 *   - 點非 active option → POST `/api/farms/{id}/activate` → 成功後 `window.location.reload()`；
 *     點 active option（farmId === activeFarmId）為 no-op（不打 API、不 reload）
 *   - 「+ 新增 / + New」開 CreateFarmModal（role=dialog）：機型 preset 4 顆（z72 預設 pressed）、
 *     風機數量 input（clamp 1–50）、離岸 checkbox、Create 鈕在 name 空時 disabled；
 *     送出 POST `/api/farms` → onCreated → 重新 fetchFarms + switchFarm
 *   - 關閉路徑：click-outside（mousedown）關 dropdown；modal 的 ✕ / 取消 / overlay 點擊關閉
 *
 * 本元件無資料 props（farms 全來自 fetch），僅 `lang`。故 **mock `global.fetch`**
 * 路由三個端點，並 stub `window.location.reload`（jsdom 未實作 navigation）；
 * `useTheme` 用真實 ThemeProvider。
 *
 * 守住契約：mount fetch / trigger 殼層（aria + label）/ 展開收合 / farm 清單（名·台數·MW·
 * 地點·active 標記）/ 空清單 / 切換接線（activate POST + reload·active option no-op）/
 * 關閉路徑（click-outside·再點 trigger）/ 新增 modal（開關·preset·name 驗證·送出 POST·
 * 離岸旗標）/ 語系（en/zh）/ 容錯（fetch reject 不崩潰）。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor, within } from '@testing-library/react';
import React from 'react';
import FarmSelector from '../FarmSelector';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { setAuthToken, clearAuthToken } from '../../services/authClient';

type Lang = 'en' | 'zh';

interface FarmFixture {
  farm_id: string;
  name: string;
  turbine_count: number;
  is_active: boolean;
  location: string;
  description: string;
  created_at: string;
  turbine_spec: Record<string, unknown>;
  is_offshore?: boolean;
}

// ─── fixtures ────────────────────────────────────────────────────────────────

function makeFarm(over: Partial<FarmFixture> = {}): FarmFixture {
  return {
    farm_id: 'f1',
    name: '彰化離岸風場',
    turbine_count: 14,
    is_active: true,
    location: '台灣海峽',
    description: '',
    created_at: '2026-01-01T00:00:00Z',
    turbine_spec: { rated_power_kw: 8000 },
    is_offshore: true,
    ...over,
  };
}

const FARM_A = makeFarm();
const FARM_B = makeFarm({
  farm_id: 'f2',
  name: '雲林陸域風場',
  turbine_count: 8,
  is_active: false,
  location: '雲林',
  turbine_spec: { rated_power_kw: 2000 },
  is_offshore: false,
});
const FARMS = [FARM_A, FARM_B];

// ─── fetch stub ──────────────────────────────────────────────────────────────

function jsonRes(body: unknown, ok = true): Promise<Response> {
  return Promise.resolve({ ok, json: () => Promise.resolve(body) } as Response);
}

let fetchMock: Mock;

/**
 * 安裝 fetch stub 路由三端點：
 *   - GET  `/api/farms`            → 列表 { farms, active_farm_id }
 *   - POST `/api/farms/{id}/activate` → 切換（預設 ok）
 *   - POST `/api/farms`            → 建立 { farm: { farm_id } }
 * opts.rejectAll：所有 fetch reject（驗 fetchFarms 容錯不崩潰）。
 * opts.listBody：覆寫列表回傳（驗空清單 / 無 active）。
 */
function installFetch(
  opts: {
    listBody?: { farms: FarmFixture[]; active_farm_id: string | null };
    activateOk?: boolean;
    createBody?: { farm: { farm_id: string } };
    rejectAll?: boolean;
  } = {},
) {
  const listBody = opts.listBody ?? { farms: FARMS, active_farm_id: 'f1' };
  const activateOk = opts.activateOk ?? true;
  const createBody = opts.createBody ?? { farm: { farm_id: 'f-new' } };
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (opts.rejectAll) return Promise.reject(new Error(`network down: ${url}`));
    const method = (init?.method ?? 'GET').toUpperCase();
    if (url.includes('/activate')) return jsonRes({}, activateOk);
    if (url.endsWith('/api/farms') && method === 'POST') return jsonRes(createBody, true);
    if (url.endsWith('/api/farms')) return jsonRes(listBody, true);
    return Promise.reject(new Error(`unexpected fetch: ${method} ${url}`));
  });
  vi.stubGlobal('fetch', fetchMock);
}

/** 取得符合 predicate 的 fetch 呼叫（URL/method）。 */
function calls(pred: (url: string, method: string) => boolean): Array<[string, string]> {
  return fetchMock.mock.calls
    .map(c => [String(c[0]), String((c[1] as RequestInit | undefined)?.method ?? 'GET').toUpperCase()] as [string, string])
    .filter(([u, m]) => pred(u, m));
}

// ─── window.location.reload stub ─────────────────────────────────────────────
// FarmSelector.switchFarm 成功後呼叫 window.location.reload()；jsdom 未實作
// navigation，直接呼叫會 throw「Not implemented」。
// 注意：jsdom 的 location.reload 是 non-configurable property，`vi.spyOn(window.location,
// 'reload')` 會 throw「Cannot redefine property: reload」，故無法用 spyOn。改成整顆
// location 換成只有 reload 的物件，afterEach 還原 originalLocation（避免 descriptor 洩漏）。

let reloadMock: Mock;
let originalLocation: Location;

// ─── render helper（flush mount fetch effect）────────────────────────────────

async function renderSelector(lang: Lang = 'zh') {
  let utils!: ReturnType<typeof render>;
  await act(async () => {
    utils = render(
      <ThemeProvider>
        <FarmSelector lang={lang} />
      </ThemeProvider>,
    );
  });
  return utils;
}

/** 渲染後展開 dropdown（等 mount fetch 落地 active label 再點）。 */
async function openDropdown(lang: Lang = 'zh') {
  const utils = await renderSelector(lang);
  const trigger = screen.getByRole('button', { name: lang === 'zh' ? '切換風場' : 'Switch wind farm' });
  await act(async () => {
    fireEvent.click(trigger);
  });
  return { ...utils, trigger };
}

/** 展開 dropdown 後點「+ 新增 / + New」開 CreateFarmModal，回傳 dialog 節點。 */
async function openCreateModal(lang: Lang = 'zh') {
  await openDropdown(lang);
  const newBtn = within(screen.getByRole('listbox')).getByText(lang === 'zh' ? /\+\s*新增/ : /\+\s*New/);
  await act(async () => {
    fireEvent.click(newBtn);
  });
  return screen.getByRole('dialog');
}

// ─── 共用 setup ──────────────────────────────────────────────────────────────

beforeEach(() => {
  installFetch();
  originalLocation = window.location;
  reloadMock = vi.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: { reload: reloadMock },
  });
});

afterEach(() => {
  cleanup();
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: originalLocation,
  });
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ═════════════════════════════════════════════════════════════════════════════

describe('FarmSelector — mount fetch / trigger 殼層', () => {
  it('mount 時 GET /api/farms 一次', async () => {
    await renderSelector('zh');
    const listCalls = calls((u, m) => u.endsWith('/api/farms') && m === 'GET');
    expect(listCalls).toHaveLength(1);
  });

  it('trigger 鈕帶 aria-haspopup=listbox + 初始 aria-expanded=false', async () => {
    await renderSelector('zh');
    const trigger = screen.getByRole('button', { name: '切換風場' });
    expect(trigger).toHaveAttribute('aria-haspopup', 'listbox');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('active farm 落地後 trigger 顯示名稱 + 額定 MW', async () => {
    await renderSelector('zh');
    // FARM_A rated_power_kw=8000 → 8.0 MW
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '切換風場' })).toHaveTextContent('彰化離岸風場 · 8.0 MW');
    });
  });

  it('lang=en trigger aria-label = Switch wind farm', async () => {
    await renderSelector('en');
    expect(screen.getByRole('button', { name: 'Switch wind farm' })).toBeInTheDocument();
  });

  it('無 active farm（active_farm_id=null）顯示 fallback「選擇風場」', async () => {
    installFetch({ listBody: { farms: FARMS, active_farm_id: null } });
    await renderSelector('zh');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '切換風場' })).toHaveTextContent('選擇風場');
    });
  });

  it('lang=en 無 active farm fallback = Select farm', async () => {
    installFetch({ listBody: { farms: FARMS, active_farm_id: null } });
    await renderSelector('en');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Switch wind farm' })).toHaveTextContent('Select farm');
    });
  });
});

describe('FarmSelector — 展開 / 收合', () => {
  it('初始不渲染 listbox', async () => {
    await renderSelector('zh');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('點 trigger 展開 listbox + aria-expanded=true', async () => {
    const { trigger } = await openDropdown('zh');
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
  });

  it('再點 trigger 收合 listbox', async () => {
    const { trigger } = await openDropdown('zh');
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(trigger);
    });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('展開後標頭顯示「風場專案」+「+ 新增」', async () => {
    await openDropdown('zh');
    const list = screen.getByRole('listbox');
    expect(within(list).getByText('風場專案')).toBeInTheDocument();
    expect(within(list).getByText(/\+\s*新增/)).toBeInTheDocument();
  });

  it('lang=en 標頭顯示 Wind farms + + New', async () => {
    await openDropdown('en');
    const list = screen.getByRole('listbox');
    expect(within(list).getByText('Wind farms')).toBeInTheDocument();
    expect(within(list).getByText(/\+\s*New/)).toBeInTheDocument();
  });

  it('點 dropdown 外部（document mousedown）關閉 listbox', async () => {
    await openDropdown('zh');
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    await act(async () => {
      fireEvent.mouseDown(document.body);
    });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
});

describe('FarmSelector — farm 清單', () => {
  it('展開後列出每個 farm（option 數 = farms 數）', async () => {
    await openDropdown('zh');
    expect(screen.getAllByRole('option')).toHaveLength(2);
  });

  it('option 顯示 farm 名稱 / 台數 / MW / 地點', async () => {
    await openDropdown('zh');
    const optB = screen.getByRole('option', { name: /雲林陸域風場/ });
    // FARM_B turbine_count=8, rated 2000 → 2.0 MW, location 雲林
    expect(optB).toHaveTextContent('8 台');
    expect(optB).toHaveTextContent('2.0 MW');
    expect(optB).toHaveTextContent('雲林');
  });

  it('active farm option 標 aria-selected=true +「使用中」', async () => {
    await openDropdown('zh');
    const optA = screen.getByRole('option', { name: /彰化離岸風場/ });
    expect(optA).toHaveAttribute('aria-selected', 'true');
    expect(within(optA).getByText('使用中')).toBeInTheDocument();
  });

  it('非 active farm option aria-selected=false 且無「使用中」', async () => {
    await openDropdown('zh');
    const optB = screen.getByRole('option', { name: /雲林陸域風場/ });
    expect(optB).toHaveAttribute('aria-selected', 'false');
    expect(within(optB).queryByText('使用中')).not.toBeInTheDocument();
  });

  it('lang=en active option 標「Active」+ 台數用 turbines', async () => {
    await openDropdown('en');
    const optA = screen.getByRole('option', { name: /彰化離岸風場/ });
    expect(within(optA).getByText('Active')).toBeInTheDocument();
    expect(optA).toHaveTextContent('14 turbines');
  });

  it('空清單顯示「尚未建立風場」', async () => {
    // installFetch 必須在 openDropdown(→renderSelector) 前呼叫，才能影響 mount 時的 fetchFarms
    installFetch({ listBody: { farms: [], active_farm_id: null } });
    await openDropdown('zh');
    expect(screen.getByText('尚未建立風場')).toBeInTheDocument();
    expect(screen.queryByRole('option')).not.toBeInTheDocument();
  });

  it('lang=en 空清單顯示 No farms', async () => {
    installFetch({ listBody: { farms: [], active_farm_id: null } });
    await openDropdown('en');
    expect(screen.getByText('No farms')).toBeInTheDocument();
  });
});

describe('FarmSelector — 切換 farm', () => {
  it('點非 active option → POST activate + window.location.reload', async () => {
    await openDropdown('zh');
    const optB = screen.getByRole('option', { name: /雲林陸域風場/ });
    await act(async () => {
      fireEvent.click(optB);
    });
    // 斷言方法為 POST（守住「切換走 POST activate」契約，避免 bug 改成 GET 仍假綠）
    await waitFor(() => {
      expect(calls((u, m) => u.includes('/api/farms/f2/activate') && m === 'POST').length).toBeGreaterThan(0);
    });
    await waitFor(() => expect(reloadMock).toHaveBeenCalledTimes(1));
  });

  it('點 active option（自己）為 no-op：不打 activate、不 reload', async () => {
    await openDropdown('zh');
    const optA = screen.getByRole('option', { name: /彰化離岸風場/ });
    await act(async () => {
      fireEvent.click(optA);
    });
    expect(calls((u, _m) => u.includes('/activate'))).toHaveLength(0);
    expect(reloadMock).not.toHaveBeenCalled();
  });

  it('activate 回非 ok 時不 reload（保持當前 farm）', async () => {
    installFetch({ activateOk: false });
    await openDropdown('zh');
    const optB = screen.getByRole('option', { name: /雲林陸域風場/ });
    await act(async () => {
      fireEvent.click(optB);
    });
    await waitFor(() => {
      expect(calls((u, m) => u.includes('/api/farms/f2/activate') && m === 'POST').length).toBeGreaterThan(0);
    });
    // 讓 activate fetch 的 finally（setSwitching(false)）等 microtask 落地後再斷言 reload 未被呼叫
    await act(async () => {});
    expect(reloadMock).not.toHaveBeenCalled();
  });
});

describe('FarmSelector — 新增風場 modal', () => {
  it('點「+ 新增」開 dialog 並關閉 dropdown', async () => {
    await openDropdown('zh');
    const newBtn = within(screen.getByRole('listbox')).getByText(/\+\s*新增/);
    await act(async () => {
      fireEvent.click(newBtn);
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('建立新風場')).toBeInTheDocument();
    // dropdown 已關
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('modal 渲染 4 顆機型 preset，z72 預設 aria-pressed=true', async () => {
    await openCreateModal('zh');
    const z72 = screen.getByRole('button', { name: /Z72 2MW/ });
    expect(z72).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /Vestas V90 3MW/ })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: /SG 8MW/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Goldwind 2.5MW/ })).toBeInTheDocument();
  });

  it('點另一 preset 切換 aria-pressed', async () => {
    await openCreateModal('zh');
    const vestas = screen.getByRole('button', { name: /Vestas V90 3MW/ });
    await act(async () => {
      fireEvent.click(vestas);
    });
    expect(vestas).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /Z72 2MW/ })).toHaveAttribute('aria-pressed', 'false');
  });

  it('name 空時 Create 鈕 disabled，輸入後啟用；顯示文字為「建立並啟用」', async () => {
    await openCreateModal('zh');
    const createBtn = screen.getByRole('button', { name: '建立風場' });
    // ariaLabel='建立風場' 但 button 顯示文字是「建立並啟用」——一併斷言文案避免假綠
    expect(createBtn).toHaveTextContent('建立並啟用');
    expect(createBtn).toBeDisabled();
    fireEvent.change(screen.getByLabelText('風場名稱'), { target: { value: '新風場' } });
    expect(createBtn).not.toBeDisabled();
  });

  it('離岸 checkbox 預設未勾，點擊勾選', async () => {
    await openCreateModal('zh');
    const cb = screen.getByRole('checkbox');
    expect(cb).not.toBeChecked();
    fireEvent.click(cb);
    expect(cb).toBeChecked();
  });

  it('填名稱送出 → POST /api/farms 帶 name + preset + is_offshore', async () => {
    await openCreateModal('zh');
    fireEvent.change(screen.getByLabelText('風場名稱'), { target: { value: '測試風場' } });
    fireEvent.click(screen.getByRole('checkbox')); // 勾離岸
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '建立風場' }));
    });
    await waitFor(() => {
      expect(calls((u, m) => u.endsWith('/api/farms') && m === 'POST').length).toBe(1);
    });
    const [, postInit] = fetchMock.mock.calls.find(
      c => String(c[0]).endsWith('/api/farms') && (c[1] as RequestInit | undefined)?.method === 'POST',
    ) as [string, RequestInit];
    const body = JSON.parse(String(postInit.body));
    expect(body.name).toBe('測試風場');
    expect(body.preset).toBe('z72_2mw');
    expect(body.is_offshore).toBe(true);
  });

  it('建立成功 → onCreated 觸發重新 fetchFarms（list GET ≥ 2 次）', async () => {
    await openCreateModal('zh');
    fireEvent.change(screen.getByLabelText('風場名稱'), { target: { value: '測試風場' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '建立風場' }));
    });
    await waitFor(() => {
      // mount 1 次 + onCreated 內 fetchFarms 1 次
      expect(calls((u, m) => u.endsWith('/api/farms') && m === 'GET').length).toBeGreaterThanOrEqual(2);
    });
  });

  it('建立成功 → onCreated 觸發 switchFarm（POST activate 新風場 f-new）', async () => {
    // onCreated 除了 fetchFarms 還會 switchFarm(新 farmId)——守住「建立後自動切換」核心 side-effect
    await openCreateModal('zh');
    fireEvent.change(screen.getByLabelText('風場名稱'), { target: { value: '測試風場' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '建立風場' }));
    });
    await waitFor(() => {
      expect(calls((u, m) => u.includes('/api/farms/f-new/activate') && m === 'POST').length).toBe(1);
    });
  });

  it('送出中 creating 狀態：Create 鈕 disabled + 顯示「建立中…」', async () => {
    // POST create 掛起（pending）以觀察 inflight 狀態，守住防重複點擊契約
    let resolveCreate!: (v: Response) => void;
    const pending = new Promise<Response>(r => {
      resolveCreate = r;
    });
    fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase();
      if (url.endsWith('/api/farms') && method === 'POST') return pending;
      if (url.endsWith('/api/farms')) return jsonRes({ farms: FARMS, active_farm_id: 'f1' });
      return Promise.reject(new Error(`unexpected fetch: ${method} ${url}`));
    });
    vi.stubGlobal('fetch', fetchMock);
    await openCreateModal('zh');
    fireEvent.change(screen.getByLabelText('風場名稱'), { target: { value: '測試風場' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '建立風場' }));
    });
    const createBtn = screen.getByRole('button', { name: '建立風場' });
    expect(createBtn).toBeDisabled();
    expect(createBtn).toHaveTextContent('建立中…');
    // 收尾 resolve 避免懸掛 promise 在 afterEach 後才 settle
    await act(async () => {
      resolveCreate({ ok: true, json: () => Promise.resolve({ farm: { farm_id: 'f-new' } }) } as Response);
    });
  });

  it('建立失敗（POST 非 ok）→ modal 保持開啟並顯示 error detail', async () => {
    fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase();
      if (url.endsWith('/api/farms') && method === 'POST') return jsonRes({ detail: '風場名稱重複' }, false);
      if (url.endsWith('/api/farms')) return jsonRes({ farms: FARMS, active_farm_id: 'f1' });
      return Promise.reject(new Error(`unexpected fetch: ${method} ${url}`));
    });
    vi.stubGlobal('fetch', fetchMock);
    await openCreateModal('zh');
    fireEvent.change(screen.getByLabelText('風場名稱'), { target: { value: '測試風場' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '建立風場' }));
    });
    await waitFor(() => {
      expect(screen.getByText('風場名稱重複')).toBeInTheDocument();
    });
    // modal 不關閉（讓使用者修正後重試）
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('點 ✕ 關閉 modal', async () => {
    await openCreateModal('zh');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('點「取消」關閉 modal', async () => {
    await openCreateModal('zh');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '取消' }));
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('點 overlay（dialog 容器）關閉 modal', async () => {
    const dialog = await openCreateModal('zh');
    await act(async () => {
      fireEvent.click(dialog);
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('點 modal 內容區域（Card 內）不關閉 modal — 守住 stopPropagation', async () => {
    // Card 內層 onClick stopPropagation 阻止冒泡到 overlay onClose；移除後本測試應失敗
    await openCreateModal('zh');
    await act(async () => {
      fireEvent.click(screen.getByLabelText('風場名稱'));
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('lang=en modal 標題 = Create wind farm', async () => {
    await openCreateModal('en');
    expect(screen.getByText('Create wind farm')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create farm' })).toBeInTheDocument();
  });
});

// ─── authFetch 稽核（WMOM-20260923-10）──────────────────────────────────────────
//
// 上方既有測試皆用 `calls()`（只比對 URL + method）比對 fetch 呼叫，對「裸 fetch vs
// authFetch」不敏感（同款根因見 WMOM-20260923-07/-09/-20260924-01）。故另補這組直接
// 檢查 `Authorization` header 內容的專測，鎖住本次修復（3 處 fetch 呼叫皆改用
// `authFetch`：GET `/api/farms` 列表讀取、POST `.../activate` 與 POST `/api/farms`
// 建立皆屬 `SUPERVISOR`/`ADMIN` 寫入，風險與 `FaultInjectionPanel` 同級）。

function authHeaderOf(init: RequestInit | undefined): string | undefined {
  return (init?.headers as Record<string, string> | undefined)?.Authorization;
}

function callsMatching(pred: (url: string, method: string) => boolean): Array<[string, RequestInit | undefined]> {
  return fetchMock.mock.calls
    .map(c => [String(c[0]), c[1] as RequestInit | undefined] as [string, RequestInit | undefined])
    .filter(([u, init]) => pred(u, String(init?.method ?? 'GET').toUpperCase()));
}

describe('FarmSelector — authFetch 稽核（WMOM-20260923-10）', () => {
  it('已登入（有 token）→ mount 時 GET /api/farms 帶 Authorization header', async () => {
    setAuthToken('test-token-mount');
    try {
      await renderSelector('zh');
      const listCalls = callsMatching((u, m) => u.endsWith('/api/farms') && m === 'GET');
      expect(listCalls).toHaveLength(1);
      expect(authHeaderOf(listCalls[0][1])).toBe('Bearer test-token-mount');
    } finally {
      clearAuthToken();
    }
  });

  it('已登入（有 token）→ 切換 farm POST /api/farms/{id}/activate 帶 Authorization header', async () => {
    setAuthToken('test-token-activate');
    try {
      await openDropdown('zh');
      const optB = screen.getByRole('option', { name: /雲林陸域風場/ });
      await act(async () => {
        fireEvent.click(optB);
      });
      await waitFor(() => {
        expect(callsMatching((u, m) => u.includes('/api/farms/f2/activate') && m === 'POST')).toHaveLength(1);
      });
      const activateCalls = callsMatching((u, m) => u.includes('/api/farms/f2/activate') && m === 'POST');
      expect(authHeaderOf(activateCalls[0][1])).toBe('Bearer test-token-activate');
    } finally {
      clearAuthToken();
    }
  });

  it('已登入（有 token）→ 建立風場 POST /api/farms 帶 Authorization header', async () => {
    setAuthToken('test-token-create');
    try {
      await openCreateModal('zh');
      fireEvent.change(screen.getByLabelText('風場名稱'), { target: { value: '測試風場' } });
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: '建立風場' }));
      });
      await waitFor(() => {
        expect(callsMatching((u, m) => u.endsWith('/api/farms') && m === 'POST')).toHaveLength(1);
      });
      const createCalls = callsMatching((u, m) => u.endsWith('/api/farms') && m === 'POST');
      expect(authHeaderOf(createCalls[0][1])).toBe('Bearer test-token-create');
    } finally {
      clearAuthToken();
    }
  });

  it('未登入（無 token）→ 列表 / 切換 / 建立 皆不帶 Authorization header（過渡期行為不變）', async () => {
    await openCreateModal('zh');
    fireEvent.change(screen.getByLabelText('風場名稱'), { target: { value: '測試風場' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '建立風場' }));
    });
    await waitFor(() => {
      expect(callsMatching((u, m) => u.endsWith('/api/farms') && m === 'POST')).toHaveLength(1);
    });
    const listCalls = callsMatching((u, m) => u.endsWith('/api/farms') && m === 'GET');
    const createCalls = callsMatching((u, m) => u.endsWith('/api/farms') && m === 'POST');
    expect(listCalls.length).toBeGreaterThan(0);
    listCalls.forEach(([, init]) => expect(authHeaderOf(init)).toBeUndefined());
    createCalls.forEach(([, init]) => expect(authHeaderOf(init)).toBeUndefined());
  });
});

describe('FarmSelector — 容錯', () => {
  it('fetchFarms reject 時不崩潰，顯示 fallback「選擇風場」', async () => {
    installFetch({ rejectAll: true });
    await renderSelector('zh');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '切換風場' })).toHaveTextContent('選擇風場');
    });
  });

  it('fetchFarms reject 後仍可展開 dropdown，顯示空狀態', async () => {
    installFetch({ rejectAll: true });
    await renderSelector('zh');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '切換風場' }));
    });
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(screen.getByText('尚未建立風場')).toBeInTheDocument();
  });
});
