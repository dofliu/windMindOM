/**
 * WorkOrderDetailModal（legacy mock 版，`components/WorkOrderDetailModal.tsx`）
 * component render 測試（EPIC-M5 測試覆蓋擴大，延續 MaintenanceHub/FaultInjectionPanel 系列）。
 *
 * 此元件掛在 `App.tsx` 'maintenance' 導覽路徑（`MaintenanceHub` → `onSelectWorkOrder`），
 * 與 `components/workflow/WorkOrderDetailModal.tsx`（backend `WorkOrderResponse` 版本，已有
 * 獨立測試）是兩支不同元件，本檔不重複——見該檔頂端註解的 legacy/workflow 區分說明。
 *
 * 涵蓋：
 *   - 標題（工單 id 末 6 碼）/ 風機 / 技師名（含 technicianId 查無此人 fallback 'N/A'）/
 *     狀態 pill / 故障描述
 *   - 點擊遮罩 / Close 按鈕觸發 onClose；點擊內容區不冒泡觸發 onClose
 *   - 備註可編輯（非 completed）、Save 呼叫 onUpdate 帶 notes + photos
 *   - 照片上傳（FileReader 轉 base64，非 jsdom 原生支援故 mock）/ 移除照片
 *   - Complete 按鈕：無照片時 disabled 且點擊不觸發 onComplete；有照片時可點擊，
 *     onComplete 收到 status=COMPLETED 的更新後物件
 *   - status=COMPLETED 時：備註唯讀、無上傳/移除/Save/Complete 控制、無照片時顯示
 *     'No photos uploaded.' 提示
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import React from 'react';
import WorkOrderDetailModal from '../WorkOrderDetailModal';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { type WorkOrder, WorkOrderStatus, type Technician, TechnicianStatus } from '../../types';

// ─── 工廠 ──────────────────────────────────────────────────────────────────

function makeWorkOrder(over: Partial<WorkOrder> = {}): WorkOrder {
  return {
    id: 'WO-2026-000123',
    turbineId: 1,
    turbineName: 'WTG-01',
    technicianId: 1,
    status: WorkOrderStatus.OPEN,
    createdAt: Date.now() - 30 * 60_000,
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

interface RenderOpts {
  workOrder?: Partial<WorkOrder>;
  technicians?: Technician[];
  onClose?: () => void;
  onUpdate?: (id: string, updates: Partial<Pick<WorkOrder, 'notes' | 'photos' | 'status'>>) => void;
  onComplete?: (wo: WorkOrder) => void;
}

function renderModal(opts: RenderOpts = {}) {
  const workOrder = makeWorkOrder(opts.workOrder);
  const technicians = opts.technicians ?? [makeTechnician()];
  const onClose = opts.onClose ?? vi.fn();
  const onUpdate = opts.onUpdate ?? vi.fn();
  const onComplete = opts.onComplete ?? vi.fn();
  const utils = render(
    <ThemeProvider>
      <WorkOrderDetailModal
        workOrder={workOrder}
        technicians={technicians}
        onClose={onClose}
        onUpdate={onUpdate}
        onComplete={onComplete}
      />
    </ThemeProvider>,
  );
  return { ...utils, workOrder, onClose, onUpdate, onComplete };
}

// jsdom 無原生 FileReader.readAsDataURL 結果，逐一 mock 成同步觸發 onloadend。
class FakeFileReader {
  result: string | null = null;
  onloadend: (() => void) | null = null;
  readAsDataURL(file: File) {
    this.result = `data:image/png;base64,fake-${file.name}`;
    this.onloadend?.();
  }
}

// 本環境 jsdom 無 `DataTransfer` global，手刻符合 `FileList` 讀取介面（`length` +
// 索引存取 + `item()`）的最小 stub，供 `<input type="file">` 的 change event 使用。
function makeFileList(files: File[]): FileList {
  const list = files as unknown as FileList & { item: (i: number) => File | null };
  list.item = (i: number) => files[i] ?? null;
  return list;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ─── 標題 / 詳情 / 狀態 ──────────────────────────────────────────────────────

describe('WorkOrderDetailModal — 標題與詳情', () => {
  it('標題顯示工單 id 末 6 碼', () => {
    renderModal({ workOrder: { id: 'WO-2026-000123' } });
    expect(screen.getByRole('heading', { name: /Work order #000123/ })).toBeInTheDocument();
  });

  it('顯示風機名稱 / 技師名稱 / 故障描述', () => {
    renderModal({
      workOrder: { turbineName: 'WTG-07', technicianId: 5, faultDescription: '齒輪箱過熱' },
      technicians: [makeTechnician({ id: 5, name: '陳大文' })],
    });
    expect(screen.getByText('WTG-07')).toBeInTheDocument();
    expect(screen.getByText('陳大文')).toBeInTheDocument();
    expect(screen.getByText('齒輪箱過熱')).toBeInTheDocument();
  });

  it('technicianId 查無對應技師時，技師名 fallback 為 N/A', () => {
    renderModal({ workOrder: { technicianId: 999 }, technicians: [makeTechnician({ id: 1 })] });
    expect(screen.getByText('N/A')).toBeInTheDocument();
  });

  it('依狀態顯示對應 pill 文字：OPEN', () => {
    renderModal({ workOrder: { status: WorkOrderStatus.OPEN } });
    expect(screen.getByText('OPEN')).toBeInTheDocument();
  });

  it('依狀態顯示對應 pill 文字：IN_PROGRESS', () => {
    renderModal({ workOrder: { status: WorkOrderStatus.IN_PROGRESS } });
    expect(screen.getByText('IN PROGRESS')).toBeInTheDocument();
  });

  it('依狀態顯示對應 pill 文字：COMPLETED', () => {
    renderModal({ workOrder: { status: WorkOrderStatus.COMPLETED } });
    expect(screen.getByText('COMPLETED')).toBeInTheDocument();
  });
});

// ─── 關閉互動 ────────────────────────────────────────────────────────────────

describe('WorkOrderDetailModal — 關閉互動', () => {
  it('點擊遮罩（dialog 本身）觸發 onClose', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點擊 Close 按鈕觸發 onClose', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點擊內容卡片區域不冒泡觸發 onClose', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByText('Maintenance notes'));
    expect(onClose).not.toHaveBeenCalled();
  });
});

// ─── 備註 + 照片 + Save ──────────────────────────────────────────────────────

describe('WorkOrderDetailModal — 備註與 Save', () => {
  it('可編輯備註；Save 呼叫 onUpdate 帶 workOrder id 與最新 notes/photos', () => {
    const { onUpdate, workOrder } = renderModal({ workOrder: { notes: '', photos: ['data:img1'] } });
    const textarea = screen.getByPlaceholderText('Add notes...');
    fireEvent.change(textarea, { target: { value: '已更換齒輪箱油封' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save notes and photos' }));
    expect(onUpdate).toHaveBeenCalledWith(workOrder.id, {
      notes: '已更換齒輪箱油封',
      photos: ['data:img1'],
    });
  });

  it('上傳照片後渲染成圖片並可移除', () => {
    const originalFileReader = global.FileReader;
    // @ts-expect-error 測試環境替換非完整型別的 FileReader stub
    global.FileReader = FakeFileReader;
    try {
      renderModal({ workOrder: { photos: [] } });
      const file = new File(['x'], 'site.png', { type: 'image/png' });
      const input = screen.getByLabelText('+ Upload') as HTMLInputElement;
      fireEvent.change(input, { target: { files: makeFileList([file]) } });

      expect(screen.getByAltText('Photo 1')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'Remove photo' }));
      expect(screen.queryByAltText('Photo 1')).not.toBeInTheDocument();
    } finally {
      global.FileReader = originalFileReader;
    }
  });

  it('無照片時顯示「至少需要一張照片」提示，且 Complete 按鈕 disabled', () => {
    renderModal({ workOrder: { photos: [] } });
    expect(
      screen.getByText('At least one photo is required to complete the work order.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Complete work order' })).toBeDisabled();
  });

  // code-reviewer subagent should-fix：此提示文字在元件原始碼只受 `!isCompleted` 控制
  // （與 photos.length 無關），故「有照片」不會讓它消失——鎖住這個實際行為，避免未來
  // 誤以為它是依照片數量 gating。
  it('有照片時（非 completed）「至少需要一張照片」提示仍然顯示（非依照片數量 gating）', () => {
    renderModal({ workOrder: { photos: ['data:img1'] } });
    expect(
      screen.getByText('At least one photo is required to complete the work order.'),
    ).toBeInTheDocument();
  });
});

// ─── Complete 流程 ───────────────────────────────────────────────────────────

describe('WorkOrderDetailModal — Complete 流程', () => {
  // 已知限制（code-reviewer subagent 確認）：本測試只鎖住 DOM 層 `disabled` 屬性擋下
  // 點擊；jsdom 對原生 disabled `<button>` 不會派發 click 事件的 React handler，故
  // `handleComplete` 內部 `if (photos.length > 0)` 邏輯層 guard 無法經由此測試獨立
  // 驗證（mutation-verify 證實拿掉該 guard、只留 disabled 屬性，本測試仍會通過）。
  // 該內部 guard 是防禦性重複，非本測試涵蓋範圍。
  it('無照片時點擊 Complete 不觸發 onComplete（disabled 阻擋）', () => {
    const { onComplete } = renderModal({ workOrder: { photos: [] } });
    fireEvent.click(screen.getByRole('button', { name: 'Complete work order' }));
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('有照片時點擊 Complete，onComplete 收到 status=COMPLETED 的更新後工單（含目前 notes/photos）', () => {
    const { onComplete, workOrder } = renderModal({
      workOrder: { notes: '初步檢查完成', photos: ['data:img1'] },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Complete work order' }));
    expect(onComplete).toHaveBeenCalledWith({
      ...workOrder,
      notes: '初步檢查完成',
      photos: ['data:img1'],
      status: WorkOrderStatus.COMPLETED,
    });
  });
});

// ─── status=COMPLETED 唯讀模式 ───────────────────────────────────────────────

describe('WorkOrderDetailModal — COMPLETED 唯讀模式', () => {
  it('備註 textarea disabled，無 Save/Complete 按鈕、無上傳/移除控制', () => {
    renderModal({ workOrder: { status: WorkOrderStatus.COMPLETED, photos: ['data:img1'] } });
    expect(screen.getByPlaceholderText('Add notes...')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Save notes and photos' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Complete work order' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('+ Upload')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove photo' })).not.toBeInTheDocument();
  });

  it('COMPLETED 且無照片時顯示 "No photos uploaded."', () => {
    renderModal({ workOrder: { status: WorkOrderStatus.COMPLETED, photos: [] } });
    expect(screen.getByText('No photos uploaded.')).toBeInTheDocument();
  });

  it('COMPLETED 且有照片時仍渲染圖片，但不顯示「至少需要一張照片」提示', () => {
    renderModal({ workOrder: { status: WorkOrderStatus.COMPLETED, photos: ['data:img1'] } });
    expect(screen.getByAltText('Photo 1')).toBeInTheDocument();
    expect(
      screen.queryByText('At least one photo is required to complete the work order.'),
    ).not.toBeInTheDocument();
  });
});
