/**
 * MaintenanceHub component render 測試（WMOM-20260923-01，EPIC-M5 測試覆蓋擴大）。
 *
 * `/admin/maintenance` 維護中心（439 行）先前零 component 測試。本檔延續既有 render
 * 測試範式（ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup），守住
 * MaintenanceHub 的核心 UX 契約：
 *
 *   - PageHeader：標題 + 「N 張未結工單・M 位技師在崗」（未結＝status≠COMPLETED，
 *     在崗＝ON_DUTY 或 DISPATCHED，兩者皆算「全部工單/技師」而非目前篩選結果）
 *   - Filter Select：預設 all，切換 open/in_progress/completed 只影響左側工單表
 *   - WorkOrderTable：欄位（ID 末 6 碼 / 風機 / 問題首行截斷 60 字 / 技師名或 —（含
 *     technicianId 存在但查無此人的 fallback）/ 優先權 pill（依 createdAt 動態算）/
 *     狀態 pill / SLA 字串）+ 空狀態 + 點列呼 onSelectWorkOrder
 *   - RosterCard：技師卡（頭像/姓名/ID/狀態 pill/切換班別鈕）+ 空狀態 + DISPATCHED
 *     時切換鈕 disabled 且不可觸發 + 點鈕呼 toggleTechnicianStatus
 *   - WeekCalendar：本週 7 格 + 依 createdAt 落點的當日工單計數徽章
 *   - 語系：lang=en → 標題/表頭/pill 文案英文
 *
 * MaintenanceHub 純由 `maintenanceData`（`ReturnType<typeof useMaintenanceData>`）
 * 與 callback props 驅動，無 fetch / 無 timer，是本系列中最單純的一支（比照
 * DispatchModal 範式：不需 mock hook 本體，直接餵結構完整的假資料物件）。
 *
 * priority/SLA 皆以 `Date.now() - createdAt` 動態算，故 fixture 一律用「現在時刻
 * 往回推固定分鐘/小時數」構造，避開 fake timers（本系列 MonthlyReportPanel 已驗證
 * fake timers 會卡死非同步 render，本檔雖無非同步但仍統一用真實時間降低耦合）。
 *
 * `MaintenanceHub.tsx` 附帶 production 微調：`WeekCalendar` 每日格加
 * `data-testid="week-day-{i}"`（i=0 週一…6 週日），供「工單依 createdAt 正確分桶到
 * 該週幾格子」的測試精確 scope（純測試選取用，無視覺/邏輯影響）。
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import React from 'react';
import MaintenanceHub from '../MaintenanceHub';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { type WorkOrder, WorkOrderStatus, type Technician, TechnicianStatus } from '../../types';

// ─── 工廠 ──────────────────────────────────────────────────────────────────

const HOUR = 3_600_000;
const MIN = 60_000;

function makeWorkOrder(over: Partial<WorkOrder> = {}): WorkOrder {
  return {
    id: 'WO-2026-000123',
    turbineId: 1,
    turbineName: 'WTG-01',
    technicianId: null,
    status: WorkOrderStatus.OPEN,
    createdAt: Date.now() - 30 * MIN,
    faultDescription: '齒輪箱潤滑油溫偏高',
    notes: '',
    photos: [],
    ...over,
  };
}

function makeTechnician(over: Partial<Technician> = {}): Technician {
  return {
    id: 1,
    name: '王小明',
    status: TechnicianStatus.ON_DUTY,
    ...over,
  };
}

function makeTurbine(over: { id?: number; name?: string } = {}) {
  return { id: over.id ?? 1, name: over.name ?? 'WTG-01' };
}

interface MaintenanceDataOverrides {
  technicians?: Technician[];
  workOrders?: WorkOrder[];
  toggleTechnicianStatus?: (id: number) => void;
}

function makeMaintenanceData(over: MaintenanceDataOverrides = {}) {
  return {
    technicians: over.technicians ?? [makeTechnician()],
    workOrders: over.workOrders ?? [makeWorkOrder()],
    toggleTechnicianStatus: over.toggleTechnicianStatus ?? vi.fn(),
    createWorkOrder: vi.fn(),
    updateWorkOrder: vi.fn(),
  };
}

// ─── render wrapper ─────────────────────────────────────────────────────────

interface RenderOpts extends MaintenanceDataOverrides {
  onSelectWorkOrder?: (wo: WorkOrder) => void;
  turbines?: { id: number; name: string }[];
  lang?: 'en' | 'zh';
}

function renderHub(opts: RenderOpts = {}) {
  const onSelectWorkOrder = opts.onSelectWorkOrder ?? vi.fn();
  const toggleTechnicianStatus = opts.toggleTechnicianStatus ?? vi.fn();
  const turbines = opts.turbines ?? [makeTurbine({ id: 1, name: 'WTG-01' }), makeTurbine({ id: 2, name: 'WTG-02' })];
  const maintenanceData = makeMaintenanceData({
    technicians: opts.technicians,
    workOrders: opts.workOrders,
    toggleTechnicianStatus,
  });
  const utils = render(
    <ThemeProvider>
      <MaintenanceHub
        maintenanceData={maintenanceData}
        onSelectWorkOrder={onSelectWorkOrder}
        turbines={turbines}
        lang={opts.lang}
      />
    </ThemeProvider>,
  );
  return { ...utils, onSelectWorkOrder, toggleTechnicianStatus, maintenanceData, turbines };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ─── 殼層 / PageHeader ───────────────────────────────────────────────────────

describe('MaintenanceHub — 殼層 / PageHeader', () => {
  it('渲染標題「維護中心」（預設 zh）', () => {
    renderHub();
    expect(screen.getByRole('heading', { name: '維護中心' })).toBeInTheDocument();
  });

  it('lang=en → 標題 "Maintenance Hub"', () => {
    renderHub({ lang: 'en' });
    expect(screen.getByRole('heading', { name: 'Maintenance Hub' })).toBeInTheDocument();
  });

  it('sub 顯示未結工單數（status≠COMPLETED，計全部而非篩選後）+ 在崗技師數（ON_DUTY+DISPATCHED）', () => {
    renderHub({
      workOrders: [
        makeWorkOrder({ id: 'a', status: WorkOrderStatus.OPEN }),
        makeWorkOrder({ id: 'b', status: WorkOrderStatus.IN_PROGRESS }),
        makeWorkOrder({ id: 'c', status: WorkOrderStatus.COMPLETED }),
      ],
      technicians: [
        makeTechnician({ id: 1, status: TechnicianStatus.ON_DUTY }),
        makeTechnician({ id: 2, status: TechnicianStatus.DISPATCHED }),
        makeTechnician({ id: 3, status: TechnicianStatus.OFF_DUTY }),
      ],
    });
    expect(screen.getByText('2 張未結工單・2 位技師在崗')).toBeInTheDocument();
  });

  it('sub 在 en 語系顯示英文格式', () => {
    renderHub({ lang: 'en', workOrders: [makeWorkOrder({ status: WorkOrderStatus.OPEN })] });
    expect(screen.getByText('1 active work orders · 1 technicians on duty')).toBeInTheDocument();
  });

  it('顯示 Filter select（預設值 all）與「+ 新工單」按鈕', () => {
    renderHub();
    const select = screen.getByRole('combobox', { name: '篩選' });
    expect(select).toHaveValue('all');
    expect(screen.getByRole('button', { name: '新工單' })).toBeInTheDocument();
  });
});

// ─── Filter 篩選 ─────────────────────────────────────────────────────────────

describe('MaintenanceHub — Filter 篩選', () => {
  // 唯讀 fixture：MaintenanceHub 不會 mutate props，但仍改用工廠函式（而非 module-level
  // 共用陣列參照）與本檔其他 describe 區塊的慣例一致，避免未來若元件改把 workOrders 當
  // 可變陣列處理時，測試間互相污染卻不易察覺。
  const buildWorkOrders = () => [
    makeWorkOrder({ id: 'open-1', turbineName: 'WTG-A', status: WorkOrderStatus.OPEN }),
    makeWorkOrder({ id: 'prog-1', turbineName: 'WTG-B', status: WorkOrderStatus.IN_PROGRESS }),
    makeWorkOrder({ id: 'done-1', turbineName: 'WTG-C', status: WorkOrderStatus.COMPLETED }),
  ];

  it('預設 all → 表格顯示全部 3 筆', () => {
    renderHub({ workOrders: buildWorkOrders() });
    expect(screen.getByText('WTG-A')).toBeInTheDocument();
    expect(screen.getByText('WTG-B')).toBeInTheDocument();
    expect(screen.getByText('WTG-C')).toBeInTheDocument();
  });

  it('切到 open → select 值同步更新 + 只顯示 OPEN 工單', () => {
    renderHub({ workOrders: buildWorkOrders() });
    const select = screen.getByRole('combobox', { name: '篩選' });
    fireEvent.change(select, { target: { value: 'open' } });
    expect(select).toHaveValue('open');
    expect(screen.getByText('WTG-A')).toBeInTheDocument();
    expect(screen.queryByText('WTG-B')).not.toBeInTheDocument();
    expect(screen.queryByText('WTG-C')).not.toBeInTheDocument();
  });

  it('切到 in_progress → select 值同步更新 + 只顯示 IN_PROGRESS 工單', () => {
    renderHub({ workOrders: buildWorkOrders() });
    const select = screen.getByRole('combobox', { name: '篩選' });
    fireEvent.change(select, { target: { value: 'in_progress' } });
    expect(select).toHaveValue('in_progress');
    expect(screen.getByText('WTG-B')).toBeInTheDocument();
    expect(screen.queryByText('WTG-A')).not.toBeInTheDocument();
    expect(screen.queryByText('WTG-C')).not.toBeInTheDocument();
  });

  it('切到 completed → select 值同步更新 + 只顯示 COMPLETED 工單', () => {
    renderHub({ workOrders: buildWorkOrders() });
    const select = screen.getByRole('combobox', { name: '篩選' });
    fireEvent.change(select, { target: { value: 'completed' } });
    expect(select).toHaveValue('completed');
    expect(screen.getByText('WTG-C')).toBeInTheDocument();
    expect(screen.queryByText('WTG-A')).not.toBeInTheDocument();
    expect(screen.queryByText('WTG-B')).not.toBeInTheDocument();
  });

  it('篩選不影響 PageHeader sub 的未結工單計數（仍算全部工單）', () => {
    renderHub({ workOrders: buildWorkOrders(), technicians: [] });
    fireEvent.change(screen.getByRole('combobox', { name: '篩選' }), { target: { value: 'completed' } });
    expect(screen.getByText('2 張未結工單・0 位技師在崗')).toBeInTheDocument();
  });
});

// ─── WorkOrderTable ──────────────────────────────────────────────────────────

describe('MaintenanceHub — WorkOrderTable 欄位', () => {
  it('顯示表頭 7 欄', () => {
    renderHub();
    const header = screen.getAllByRole('row')[0];
    ['編號', '風機', '問題', '技師', '優先', '狀態', 'SLA'].forEach(h => {
      expect(within(header).getByText(h)).toBeInTheDocument();
    });
  });

  it('空工單清單 → 顯示「暫無工單。」', () => {
    renderHub({ workOrders: [] });
    expect(screen.getByText('暫無工單。')).toBeInTheDocument();
  });

  it('lang=en 空工單清單 → 顯示 "No work orders."', () => {
    renderHub({ workOrders: [], lang: 'en' });
    expect(screen.getByText('No work orders.')).toBeInTheDocument();
  });

  it('ID 欄顯示工單 id 末 6 碼（加 # 前綴）', () => {
    renderHub({ workOrders: [makeWorkOrder({ id: 'WO-2026-00ABCD' })] });
    expect(screen.getByText('#00ABCD')).toBeInTheDocument();
  });

  it('問題欄顯示 faultDescription 首行、超過 60 字截斷', () => {
    const longLine = 'A'.repeat(80);
    renderHub({
      workOrders: [makeWorkOrder({ faultDescription: `${longLine}\n第二行不應出現` })],
    });
    expect(screen.getByText('A'.repeat(60))).toBeInTheDocument();
    expect(screen.queryByText(/第二行不應出現/)).not.toBeInTheDocument();
  });

  it('faultDescription 空字串 → 問題欄顯示「—」（technicianId 對到既有技師，避免技師欄也顯示「—」造成多重命中）', () => {
    renderHub({
      technicians: [makeTechnician({ id: 1, name: '王小明' })],
      workOrders: [makeWorkOrder({ faultDescription: '', technicianId: 1 })],
    });
    const dataRow = screen.getAllByRole('row')[1];
    expect(within(dataRow).getByText('—')).toBeInTheDocument();
  });

  it('technicianId 對應到現有技師 → 顯示技師名（scope 到工單列，避免與 RosterCard 同名撞名）', () => {
    renderHub({
      technicians: [makeTechnician({ id: 5, name: '陳大文' })],
      workOrders: [makeWorkOrder({ technicianId: 5 })],
    });
    const dataRow = screen.getAllByRole('row')[1];
    expect(within(dataRow).getByText('陳大文')).toBeInTheDocument();
  });

  it('technicianId 對應到「目前非 ON_DUTY」的技師 → 表格技師欄仍正確顯示姓名（techMap 依 id 索引，不應受目前狀態影響）', () => {
    renderHub({
      technicians: [makeTechnician({ id: 5, name: '陳大文', status: TechnicianStatus.OFF_DUTY })],
      workOrders: [makeWorkOrder({ technicianId: 5 })],
    });
    const dataRow = screen.getAllByRole('row')[1];
    expect(within(dataRow).getByText('陳大文')).toBeInTheDocument();
  });

  it('technicianId 為 null → 技師欄顯示「—」', () => {
    renderHub({ workOrders: [makeWorkOrder({ technicianId: null })] });
    const dataRow = screen.getAllByRole('row')[1];
    expect(within(dataRow).getByText('—')).toBeInTheDocument();
  });

  it('technicianId 存在但查無此技師 → 技師欄仍 fallback「—」（非崩潰）', () => {
    renderHub({
      technicians: [makeTechnician({ id: 1 })],
      workOrders: [makeWorkOrder({ technicianId: 999 })],
    });
    const dataRow = screen.getAllByRole('row')[1];
    expect(within(dataRow).getByText('—')).toBeInTheDocument();
  });

  it('createdAt < 4 小時 → 優先權 HIGH', () => {
    renderHub({ workOrders: [makeWorkOrder({ createdAt: Date.now() - 30 * MIN })] });
    expect(screen.getByText('HIGH')).toBeInTheDocument();
  });

  it('createdAt 4~24 小時 → 優先權 MED', () => {
    renderHub({ workOrders: [makeWorkOrder({ createdAt: Date.now() - 10 * HOUR })] });
    expect(screen.getByText('MED')).toBeInTheDocument();
  });

  it('createdAt ≥ 24 小時 → 優先權 LOW', () => {
    renderHub({ workOrders: [makeWorkOrder({ createdAt: Date.now() - 48 * HOUR })] });
    expect(screen.getByText('LOW')).toBeInTheDocument();
  });

  it('createdAt < 1 小時 → SLA 顯示分鐘（如 5m）', () => {
    renderHub({ workOrders: [makeWorkOrder({ createdAt: Date.now() - 5 * MIN })] });
    expect(screen.getByText('5m')).toBeInTheDocument();
  });

  it('createdAt 1~24 小時 → SLA 顯示小時（如 10.0h）', () => {
    renderHub({ workOrders: [makeWorkOrder({ createdAt: Date.now() - 10 * HOUR })] });
    expect(screen.getByText('10.0h')).toBeInTheDocument();
  });

  it('createdAt ≥ 24 小時 → SLA 顯示天數（如 2.0d）', () => {
    renderHub({ workOrders: [makeWorkOrder({ createdAt: Date.now() - 48 * HOUR })] });
    expect(screen.getByText('2.0d')).toBeInTheDocument();
  });

  it('狀態 pill 依 WorkOrderStatus 顯示對應中文（OPEN→未結／IN_PROGRESS→處理中／COMPLETED→已完成，scope 到各自工單列避免與 Filter select 選項同字撞名）', () => {
    renderHub({
      workOrders: [
        makeWorkOrder({ id: 'a', turbineName: 'A', status: WorkOrderStatus.OPEN }),
        makeWorkOrder({ id: 'b', turbineName: 'B', status: WorkOrderStatus.IN_PROGRESS }),
        makeWorkOrder({ id: 'c', turbineName: 'C', status: WorkOrderStatus.COMPLETED }),
      ],
    });
    const rows = screen.getAllByRole('row');
    expect(within(rows[1]).getByText('未結')).toBeInTheDocument();
    expect(within(rows[2]).getByText('處理中')).toBeInTheDocument();
    expect(within(rows[3]).getByText('已完成')).toBeInTheDocument();
  });

  it('lang=en 狀態 pill 顯示英文（OPEN／IN PROGRESS／COMPLETED）', () => {
    renderHub({
      lang: 'en',
      workOrders: [
        makeWorkOrder({ id: 'a', turbineName: 'A', status: WorkOrderStatus.OPEN }),
        makeWorkOrder({ id: 'b', turbineName: 'B', status: WorkOrderStatus.IN_PROGRESS }),
        makeWorkOrder({ id: 'c', turbineName: 'C', status: WorkOrderStatus.COMPLETED }),
      ],
    });
    expect(screen.getByText('OPEN')).toBeInTheDocument();
    expect(screen.getByText('IN PROGRESS')).toBeInTheDocument();
    expect(screen.getByText('COMPLETED')).toBeInTheDocument();
  });

  it('點工單列 → 呼叫 onSelectWorkOrder 帶該工單物件', () => {
    const wo = makeWorkOrder({ id: 'target-1', turbineName: 'WTG-TARGET' });
    const { onSelectWorkOrder } = renderHub({ workOrders: [wo] });
    fireEvent.click(screen.getByText('WTG-TARGET'));
    expect(onSelectWorkOrder).toHaveBeenCalledTimes(1);
    expect(onSelectWorkOrder).toHaveBeenCalledWith(wo);
  });
});

// ─── RosterCard ──────────────────────────────────────────────────────────────

describe('MaintenanceHub — RosterCard 技師排班', () => {
  it('顯示標題「技師排班」（en: Technicians）', () => {
    renderHub();
    expect(screen.getByText('技師排班')).toBeInTheDocument();
  });

  it('空技師清單 → 顯示「暫無技師資料。」', () => {
    renderHub({ technicians: [] });
    expect(screen.getByText('暫無技師資料。')).toBeInTheDocument();
  });

  it('lang=en 空技師清單 → 顯示 "No technicians."', () => {
    renderHub({ technicians: [], lang: 'en' });
    expect(screen.getByText('No technicians.')).toBeInTheDocument();
  });

  it('每張技師卡顯示姓名 + ID + 狀態 pill（lang=en 下狀態 pill 文字與 TechnicianStatus enum 值同字，重命名時測試會有意義地失敗）', () => {
    renderHub({
      lang: 'en',
      technicians: [makeTechnician({ id: 7, name: '林小美', status: TechnicianStatus.ON_DUTY })],
    });
    expect(screen.getByText('林小美')).toBeInTheDocument();
    expect(screen.getByText('ID #7')).toBeInTheDocument();
    expect(screen.getByText(TechnicianStatus.ON_DUTY)).toBeInTheDocument();
  });

  it('ON_DUTY 技師的切換鈕文字為「下班」且可點', () => {
    renderHub({ technicians: [makeTechnician({ status: TechnicianStatus.ON_DUTY })] });
    const btn = screen.getByRole('button', { name: '切換班別' });
    expect(btn).toHaveTextContent('下班');
    expect(btn).not.toBeDisabled();
  });

  it('OFF_DUTY 技師的切換鈕文字為「上崗」且可點', () => {
    renderHub({ technicians: [makeTechnician({ status: TechnicianStatus.OFF_DUTY })] });
    const btn = screen.getByRole('button', { name: '切換班別' });
    expect(btn).toHaveTextContent('上崗');
    expect(btn).not.toBeDisabled();
  });

  it('DISPATCHED 技師的切換鈕 disabled（顯示「上崗」但不可點）', () => {
    renderHub({ technicians: [makeTechnician({ status: TechnicianStatus.DISPATCHED })] });
    const btn = screen.getByRole('button', { name: '切換班別' });
    expect(btn).toHaveTextContent('上崗');
    expect(btn).toBeDisabled();
  });

  it('lang=en 切換鈕 aria-label 為 "Toggle duty"，文字 Out/In', () => {
    renderHub({ lang: 'en', technicians: [makeTechnician({ status: TechnicianStatus.ON_DUTY })] });
    const btn = screen.getByRole('button', { name: 'Toggle duty' });
    expect(btn).toHaveTextContent('Out');
  });

  it('點可用的切換鈕 → 呼叫 toggleTechnicianStatus 帶該技師 id', () => {
    const { toggleTechnicianStatus } = renderHub({
      technicians: [makeTechnician({ id: 42, status: TechnicianStatus.ON_DUTY })],
    });
    fireEvent.click(screen.getByRole('button', { name: '切換班別' }));
    expect(toggleTechnicianStatus).toHaveBeenCalledTimes(1);
    expect(toggleTechnicianStatus).toHaveBeenCalledWith(42);
  });

  it('點 DISPATCHED 技師的 disabled 切換鈕 → 不呼叫 toggleTechnicianStatus', () => {
    const { toggleTechnicianStatus } = renderHub({
      technicians: [makeTechnician({ id: 42, status: TechnicianStatus.DISPATCHED })],
    });
    fireEvent.click(screen.getByRole('button', { name: '切換班別' }));
    expect(toggleTechnicianStatus).not.toHaveBeenCalled();
  });

  it('多名技師 → 各自獨立顯示，最後一位無底部分隔線（style.borderBottom 斷言，非僅內容存在）', () => {
    renderHub({
      technicians: [
        makeTechnician({ id: 1, name: '甲技師' }),
        makeTechnician({ id: 2, name: '乙技師' }),
      ],
    });
    // name div 的祖父層才是整列 row（name div → flex:1 容器 → row）
    const firstRow = screen.getByText('甲技師').parentElement!.parentElement as HTMLElement;
    const lastRow = screen.getByText('乙技師').parentElement!.parentElement as HTMLElement;
    expect(firstRow.style.borderBottom).not.toBe('');
    expect(lastRow.style.borderBottom).toBe('');
  });

  it('技師姓名為空字串 → Avatar fallback 顯示「?」', () => {
    renderHub({ technicians: [makeTechnician({ name: '' })] });
    expect(screen.getByText('?')).toBeInTheDocument();
  });
});

// ─── WeekCalendar ────────────────────────────────────────────────────────────

/**
 * 鏡射 `WeekCalendar` 內部「本週 Monday..Sunday」的日期推算，供測試建構「非今天但仍在
 * 本週內」的 fixture、並算出對應的 grid index（0=週一…6=週日，與元件 `days.map((_,i)=>…)`
 * 的 i 一致，對應 production 端新增的 `data-testid="week-day-{i}"`）。
 */
function mondayOfCurrentWeek(): Date {
  const monday = new Date();
  const dow = monday.getDay() || 7; // Sun=0 → 7
  monday.setDate(monday.getDate() - (dow - 1));
  monday.setHours(0, 0, 0, 0);
  return monday;
}

function weekDayTimestamp(index: number, hour = 10): number {
  const d = new Date(mondayOfCurrentWeek());
  d.setDate(d.getDate() + index);
  d.setHours(hour, 0, 0, 0);
  return d.getTime();
}

function todayWeekIndex(): number {
  const dow = new Date().getDay() || 7;
  return dow - 1;
}

describe('MaintenanceHub — WeekCalendar 本週行程', () => {
  it('顯示標題「本週行程」（en: Calendar (this week)）', () => {
    renderHub();
    expect(screen.getByText('本週行程')).toBeInTheDocument();
  });

  it('lang=en 標題為 "Calendar (this week)"', () => {
    renderHub({ lang: 'en' });
    expect(screen.getByText('Calendar (this week)')).toBeInTheDocument();
  });

  it('顯示 7 個星期標籤（一二三四五六日）', () => {
    renderHub();
    ['一', '二', '三', '四', '五', '六', '日'].forEach(l => {
      expect(screen.getByText(l)).toBeInTheDocument();
    });
  });

  it('lang=en 顯示 7 個星期標籤（M T W T F S S，重複字母各驗證出現次數）', () => {
    renderHub({ lang: 'en' });
    expect(screen.getAllByText('M')).toHaveLength(1);
    expect(screen.getAllByText('T')).toHaveLength(2);
    expect(screen.getAllByText('W')).toHaveLength(1);
    expect(screen.getAllByText('F')).toHaveLength(1);
    expect(screen.getAllByText('S')).toHaveLength(2);
  });

  it('今天有一筆工單 → 當日格（依 todayWeekIndex scope）顯示「×1」計數徽章', () => {
    renderHub({ workOrders: [makeWorkOrder({ createdAt: Date.now() })] });
    const todayCell = screen.getByTestId(`week-day-${todayWeekIndex()}`);
    expect(within(todayCell).getByText('×1')).toBeInTheDocument();
  });

  it('今天有兩筆工單 → 當日格顯示「×2」', () => {
    renderHub({
      workOrders: [
        makeWorkOrder({ id: 'a', createdAt: Date.now() }),
        makeWorkOrder({ id: 'b', createdAt: Date.now() }),
      ],
    });
    const todayCell = screen.getByTestId(`week-day-${todayWeekIndex()}`);
    expect(within(todayCell).getByText('×2')).toBeInTheDocument();
  });

  it('工單 createdAt 落在本週非今天的某一天 → 計數徽章只出現在該天格子，今天格子維持 0（守住依星期分桶而非全域出現）', () => {
    const todayIdx = todayWeekIndex();
    const otherIdx = (todayIdx + 1) % 7; // 本週內、與今天不同的另一天
    renderHub({
      workOrders: [makeWorkOrder({ createdAt: weekDayTimestamp(otherIdx) })],
    });
    const otherCell = screen.getByTestId(`week-day-${otherIdx}`);
    const todayCell = screen.getByTestId(`week-day-${todayIdx}`);
    expect(within(otherCell).getByText('×1')).toBeInTheDocument();
    expect(within(todayCell).queryByText(/×\d/)).not.toBeInTheDocument();
  });

  it('沒有任何工單 → 不顯示計數徽章', () => {
    renderHub({ workOrders: [] });
    expect(screen.queryByText(/×\d/)).not.toBeInTheDocument();
  });
});

// ─── + 新工單 modal（WMOM-20260507-02 sub-task e）───────────────────────────

describe('MaintenanceHub — 「+ 新工單」modal', () => {
  it('點擊 header「+ 新工單」鈕 → 開啟 dialog', () => {
    renderHub();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '新工單' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('點擊 ✕ 關閉 dialog，不呼叫 createWorkOrder', () => {
    const { maintenanceData } = renderHub();
    fireEvent.click(screen.getByRole('button', { name: '新工單' }));
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(maintenanceData.createWorkOrder).not.toHaveBeenCalled();
  });

  it('點擊「取消」關閉 dialog，不呼叫 createWorkOrder', () => {
    const { maintenanceData } = renderHub();
    fireEvent.click(screen.getByRole('button', { name: '新工單' }));
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(maintenanceData.createWorkOrder).not.toHaveBeenCalled();
  });

  it('未選風機時「建立工單」鈕 disabled，選了風機但描述空白仍 disabled', () => {
    renderHub();
    fireEvent.click(screen.getByRole('button', { name: '新工單' }));
    const createBtn = screen.getByRole('button', { name: '建立工單' });
    expect(createBtn).toBeDisabled();

    fireEvent.change(screen.getByLabelText('風機'), { target: { value: '1' } });
    expect(createBtn).toBeDisabled(); // 描述仍空白

    fireEvent.change(screen.getByLabelText('問題描述'), { target: { value: '   ' } });
    expect(createBtn).toBeDisabled(); // 純空白視同空
  });

  it('選風機 + 輸入描述 + 不選技師 → 送出呼叫 createWorkOrder(turbineId, turbineName, description, undefined) 並關閉 dialog', () => {
    const { maintenanceData } = renderHub({
      turbines: [makeTurbine({ id: 2, name: 'WTG-02' })],
    });
    fireEvent.click(screen.getByRole('button', { name: '新工單' }));
    fireEvent.change(screen.getByLabelText('風機'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('問題描述'), { target: { value: '齒輪箱異音' } });
    fireEvent.click(screen.getByRole('button', { name: '建立工單' }));

    expect(maintenanceData.createWorkOrder).toHaveBeenCalledWith(2, 'WTG-02', '齒輪箱異音', undefined);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('選風機 + 描述 + 選技師 → technicianId 以 number 型別傳遞', () => {
    const { maintenanceData } = renderHub({
      technicians: [makeTechnician({ id: 7, name: '陳大文', status: TechnicianStatus.ON_DUTY })],
    });
    fireEvent.click(screen.getByRole('button', { name: '新工單' }));
    fireEvent.change(screen.getByLabelText('風機'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('問題描述'), { target: { value: '葉片結冰' } });
    fireEvent.change(screen.getByLabelText('技師（可留空）'), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: '建立工單' }));

    expect(maintenanceData.createWorkOrder).toHaveBeenCalledWith(1, 'WTG-01', '葉片結冰', 7);
  });

  it('技師下拉只列出 ON_DUTY 技師（DISPATCHED / OFF_DUTY 不出現），確認為分派安全的把關（mutation-verified）', () => {
    renderHub({
      technicians: [
        makeTechnician({ id: 1, name: '在崗甲', status: TechnicianStatus.ON_DUTY }),
        makeTechnician({ id: 2, name: '派遣中乙', status: TechnicianStatus.DISPATCHED }),
        makeTechnician({ id: 3, name: '下班丙', status: TechnicianStatus.OFF_DUTY }),
      ],
    });
    fireEvent.click(screen.getByRole('button', { name: '新工單' }));
    const select = screen.getByLabelText('技師（可留空）') as HTMLSelectElement;
    const optionLabels = Array.from(select.options).map(o => o.textContent);
    expect(optionLabels).toEqual(['未指派', '在崗甲']);
    expect(optionLabels).not.toContain('派遣中乙');
    expect(optionLabels).not.toContain('下班丙');
  });

  it('風機下拉選項來自 turbines prop（非固定寫死清單）', () => {
    renderHub({
      turbines: [makeTurbine({ id: 5, name: 'WTG-05' }), makeTurbine({ id: 6, name: 'WTG-06' })],
    });
    fireEvent.click(screen.getByRole('button', { name: '新工單' }));
    const select = screen.getByLabelText('風機') as HTMLSelectElement;
    const optionLabels = Array.from(select.options).map(o => o.textContent);
    expect(optionLabels).toEqual(['請選擇風機', 'WTG-05', 'WTG-06']);
  });

  it('lang=en → dialog 標題與按鈕文案為英文', () => {
    renderHub({ lang: 'en' });
    fireEvent.click(screen.getByRole('button', { name: 'New work order' }));
    expect(screen.getByText('New work order')).toBeInTheDocument();
    expect(screen.getByLabelText('Turbine')).toBeInTheDocument();
    expect(screen.getByLabelText('Description')).toBeInTheDocument();
    expect(screen.getByLabelText('Technician (optional)')).toBeInTheDocument();
  });
});
