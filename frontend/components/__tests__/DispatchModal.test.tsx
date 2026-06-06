/**
 * DispatchModal component render 測試（WMOM-20260606-06，EPIC-M5 測試覆蓋擴大）。
 *
 * `DispatchModal.tsx`（194 行）是「AI 故障診斷 → 派工」流程的確認對話框：自 TurbineDetail
 * 的 AI 診斷卡（onDispatch）或風場總覽觸發，於 App.tsx 掛載。內容：
 *   - header：標題「Dispatch Technician」+ ✕ 關閉鈕
 *   - 目標風機名稱 + 目前狀態（turbine.status）
 *   - AI fault analysis 卡（<pre> 原樣顯示 faultAnalysis 字串）
 *   - 可用技師清單：僅 `TechnicianStatus.ON_DUTY` 入選，逐張可點（aria-pressed），
 *     無人值班 → 警告卡「No technicians are currently on duty.」
 *   - footer：Cancel + Confirm dispatch（未選技師前 disabled）
 *
 * 本元件純 props-driven、無 fetch / 無 async / 無 lang prop（英文固定字串），是 detail modal
 * 系列中最單純的一支。依賴僅 `useTheme` → render wrapper 包 `ThemeProvider` 即可。
 *
 * 守住對話框契約：殼層靜態 / 技師過濾 + 單選 + aria-pressed / Confirm gating 與 callback
 * 參數（turbineId·technicianId·faultAnalysis 原樣透傳）/ 四條關閉路徑（遮罩·✕·Cancel·
 * 內容點擊不關 stopPropagation）。工廠以結構式滿足型別（不用 `as` 強轉）。
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import React from 'react';
import DispatchModal from '../DispatchModal';
import { ThemeProvider } from '../../theme/ThemeProvider';
import {
  type TurbineData,
  type Technician,
  TurbineStatus,
  TechnicianStatus,
} from '../../types';

// ─── 工廠 ──────────────────────────────────────────────────────────────────

/** 產生結構完整的 TurbineData（必填欄位齊備，不用 `as` 強轉）。 */
function makeTurbine(over: Partial<TurbineData> = {}): TurbineData {
  return {
    id: 7,
    name: 'WTG-07',
    status: TurbineStatus.FAULT,
    powerOutput: 0,
    windSpeed: 8.5,
    rotorSpeed: 0,
    bladeAngle: 90,
    temperature: 52,
    vibration: 3.1,
    voltage: 690,
    current: 0,
    history: [],
    ...over,
  };
}

/** 產生一名技師。 */
function makeTech(over: Partial<Technician> = {}): Technician {
  return {
    id: 1,
    name: '王小明',
    status: TechnicianStatus.ON_DUTY,
    ...over,
  };
}

// ─── render wrapper ─────────────────────────────────────────────────────────

interface RenderOpts {
  turbine?: TurbineData;
  technicians?: Technician[];
  faultAnalysis?: string;
  onClose?: () => void;
  onConfirm?: (turbineId: number, technicianId: number, faultDescription: string) => void;
}

function renderModal(opts: RenderOpts = {}) {
  const onClose = opts.onClose ?? vi.fn();
  const onConfirm = opts.onConfirm ?? vi.fn();
  const utils = render(
    <ThemeProvider>
      <DispatchModal
        turbine={opts.turbine ?? makeTurbine()}
        technicians={opts.technicians ?? [makeTech()]}
        faultAnalysis={opts.faultAnalysis ?? 'AI 研判：齒輪箱潤滑油溫偏高，建議派員檢查。'}
        onClose={onClose}
        onConfirm={onConfirm}
      />
    </ThemeProvider>,
  );
  return { ...utils, onClose, onConfirm };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ─── 殼層 / 靜態內容 ─────────────────────────────────────────────────────────

describe('DispatchModal — 殼層 / 靜態內容', () => {
  it('渲染 dialog（role=dialog + aria-modal）與標題', () => {
    renderModal();
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByRole('heading', { name: 'Dispatch Technician' })).toBeInTheDocument();
  });

  it('header 有 aria-label="Close" 的關閉鈕', () => {
    renderModal();
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
  });

  it('顯示目標風機名稱與目前狀態', () => {
    renderModal({ turbine: makeTurbine({ name: 'WTG-12', status: TurbineStatus.FAULT }) });
    expect(screen.getByText(/WTG-12/)).toBeInTheDocument();
    expect(screen.getByText('FAULT')).toBeInTheDocument();
  });

  it('AI fault analysis 卡原樣顯示 faultAnalysis 字串', () => {
    const text = 'AI 研判：發電機定子溫度逼近上限，立即派工。';
    renderModal({ faultAnalysis: text });
    expect(screen.getByText('AI fault analysis')).toBeInTheDocument();
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it('顯示「Select available technician」區塊標題', () => {
    renderModal();
    expect(screen.getByText('Select available technician')).toBeInTheDocument();
  });
});

// ─── 技師清單過濾 / 單選 ─────────────────────────────────────────────────────

describe('DispatchModal — 技師清單', () => {
  it('只列出 ON_DUTY 技師（過濾掉 OFF_DUTY / DISPATCHED）', () => {
    renderModal({
      technicians: [
        makeTech({ id: 1, name: '在班甲', status: TechnicianStatus.ON_DUTY }),
        makeTech({ id: 2, name: '休假乙', status: TechnicianStatus.OFF_DUTY }),
        makeTech({ id: 3, name: '出勤中丙', status: TechnicianStatus.DISPATCHED }),
        makeTech({ id: 4, name: '在班丁', status: TechnicianStatus.ON_DUTY }),
      ],
    });
    expect(screen.getByText('在班甲')).toBeInTheDocument();
    expect(screen.getByText('在班丁')).toBeInTheDocument();
    expect(screen.queryByText('休假乙')).not.toBeInTheDocument();
    expect(screen.queryByText('出勤中丙')).not.toBeInTheDocument();
  });

  it('每張技師卡顯示姓名 + ON DUTY 狀態 pill', () => {
    renderModal({ technicians: [makeTech({ id: 1, name: '王小明' })] });
    const card = screen.getByRole('button', { name: /王小明/ });
    expect(within(card).getByText('王小明')).toBeInTheDocument();
    // 用 enum 值而非字面字串，enum 一旦重命名測試會有意義地失敗
    expect(within(card).getByText(TechnicianStatus.ON_DUTY)).toBeInTheDocument();
  });

  it('無 ON_DUTY 技師 → 顯示警告卡', () => {
    renderModal({
      technicians: [
        makeTech({ id: 2, status: TechnicianStatus.OFF_DUTY }),
        makeTech({ id: 3, status: TechnicianStatus.DISPATCHED }),
      ],
    });
    expect(screen.getByText('No technicians are currently on duty.')).toBeInTheDocument();
  });

  it('空技師陣列 → 顯示警告卡', () => {
    renderModal({ technicians: [] });
    expect(screen.getByText('No technicians are currently on duty.')).toBeInTheDocument();
  });

  it('技師卡初始 aria-pressed=false', () => {
    renderModal({ technicians: [makeTech({ id: 1, name: '王小明' })] });
    expect(screen.getByRole('button', { name: /王小明/ })).toHaveAttribute('aria-pressed', 'false');
  });

  it('點選技師 → 該卡 aria-pressed=true', () => {
    renderModal({ technicians: [makeTech({ id: 1, name: '王小明' })] });
    const card = screen.getByRole('button', { name: /王小明/ });
    fireEvent.click(card);
    expect(card).toHaveAttribute('aria-pressed', 'true');
  });

  it('改選另一技師 → 選擇互斥（前一張回 false、後一張 true）', () => {
    renderModal({
      technicians: [
        makeTech({ id: 1, name: '甲技師' }),
        makeTech({ id: 2, name: '乙技師' }),
      ],
    });
    const first = screen.getByRole('button', { name: /甲技師/ });
    const second = screen.getByRole('button', { name: /乙技師/ });
    fireEvent.click(first);
    expect(first).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(second);
    expect(first).toHaveAttribute('aria-pressed', 'false');
    expect(second).toHaveAttribute('aria-pressed', 'true');
  });
});

// ─── Confirm gating / callback ──────────────────────────────────────────────

describe('DispatchModal — Confirm 派工', () => {
  it('未選技師時 Confirm dispatch 鈕 disabled', () => {
    renderModal({ technicians: [makeTech({ id: 1, name: '王小明' })] });
    expect(screen.getByRole('button', { name: 'Confirm dispatch' })).toBeDisabled();
  });

  it('選技師後 Confirm dispatch 鈕變為可按', () => {
    renderModal({ technicians: [makeTech({ id: 1, name: '王小明' })] });
    fireEvent.click(screen.getByRole('button', { name: /王小明/ }));
    expect(screen.getByRole('button', { name: 'Confirm dispatch' })).not.toBeDisabled();
  });

  it('點 Confirm → onConfirm(turbineId, technicianId, faultAnalysis) 原樣透傳，且不自動 onClose', () => {
    const text = 'AI 研判：建議派工檢查偏航系統。';
    const { onConfirm, onClose } = renderModal({
      turbine: makeTurbine({ id: 42 }),
      technicians: [makeTech({ id: 9, name: '指定技師' })],
      faultAnalysis: text,
    });
    fireEvent.click(screen.getByRole('button', { name: /指定技師/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm dispatch' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith(42, 9, text);
    // 關閉由父層（App.tsx）負責，元件本身不自動 onClose —— 守住此契約
    expect(onClose).not.toHaveBeenCalled();
  });

  it('無 ON_DUTY 技師時 Confirm dispatch 鈕 disabled（無從選取）', () => {
    renderModal({ technicians: [] });
    expect(screen.getByRole('button', { name: 'Confirm dispatch' })).toBeDisabled();
  });

  it('技師 id=0 → 卡視覺選中（aria-pressed=true）但 Confirm 仍 disabled（falsy guard 邊界）', () => {
    // 生產碼以 `if (selectedTechnicianId)` / `disabled={!selectedTechnicianId}` 做 truthy 判斷，
    // id=0 被視同「未選」→ 卡的 `selectedTechnicianId === tech.id`（0===0）為 true 顯示選中，
    // 但 Confirm 因 `!0===true` 維持 disabled。守住此（兩 guard 一致的）現行行為；
    // 若未來技師 id 改 0-indexed 需改 guard 為 `!== null`（見 work-log follow-up）。
    const { onConfirm } = renderModal({ technicians: [makeTech({ id: 0, name: '零號技師' })] });
    const card = screen.getByRole('button', { name: /零號技師/ });
    fireEvent.click(card);
    expect(card).toHaveAttribute('aria-pressed', 'true');
    const confirm = screen.getByRole('button', { name: 'Confirm dispatch' });
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

// ─── 關閉路徑 ───────────────────────────────────────────────────────────────

describe('DispatchModal — 關閉路徑', () => {
  it('點遮罩（dialog 外層）→ onClose', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點對話框內容 → 不 onClose（stopPropagation）', () => {
    const { onClose } = renderModal();
    // 點標題（位於 stopPropagation 容器內）不應冒泡到遮罩
    fireEvent.click(screen.getByRole('heading', { name: 'Dispatch Technician' }));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('點 header ✕ → onClose', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('點 footer Cancel → onClose', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
