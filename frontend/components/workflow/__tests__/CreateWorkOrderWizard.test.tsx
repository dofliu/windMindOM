/**
 * CreateWorkOrderWizard component render 測試（WMOM-20260606-01，EPIC-M5 測試覆蓋擴大）。
 *
 * `CreateWorkOrderWizard.tsx`（466 行）是 `/admin/workflow` 工單 tab 的「建立工單」3 步精靈：
 *   Step 1 選風機 → Step 2 工單細節（type / priority / title* / description* / 來源警報碼選填）
 *   → Step 3 派工 + 工時（assignee 選填 / crew_size 夾限 / estimated_hours 選填）→ 送出。
 *
 * 與本系列先前覆蓋的「單畫面對話框 / 純展示列表面板」不同，本元件是**多步驟 wizard**：
 * 核心契約在 **step machine（1↔2↔3 Next/Back）+ 逐步 gating（canNext1 / canNext2）+
 * buildRequest 序列化（trim / null 空值 / Number 轉型 / crew_size 夾限）+ async 送出
 * （submitting 中態 / onSubmit reject 回填錯誤卡且不關閉）**。先前無任何測試覆蓋。
 *
 * 延續既有 render 測試範式（ThemeProvider 包裹 + jest-dom matcher + afterEach cleanup）。
 * 本元件不依賴 useCurrentUser，故僅需 ThemeProvider。工廠以結構式滿足型別（不用 `as` 強轉）；
 * async 送出以受控 Promise 斷言中間態並一律 await 收尾（resolve + waitFor）以免 act 警告。
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import React from 'react';
import CreateWorkOrderWizard from '../CreateWorkOrderWizard';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import { type TurbineData, TurbineStatus } from '../../../types';
import type { CreateWorkOrderRequest } from '../../../services/workOrderService';

// ─── 工廠 ──────────────────────────────────────────────────────────────────

/** 產生結構完整的 TurbineData（僅填精靈用得到的欄位，其餘以合理 default 補齊；不用 `as`）。 */
function makeTurbine(overrides: Partial<TurbineData> = {}): TurbineData {
  return {
    id: 1,
    name: 'WT-01',
    status: TurbineStatus.OPERATING,
    powerOutput: 1.5,
    windSpeed: 12,
    rotorSpeed: 14.2,
    bladeAngle: 2.1,
    temperature: 45,
    vibration: 1.2,
    voltage: 690,
    current: 800,
    history: [],
    ...overrides,
  };
}

// id 故意與 name 序號錯開（WT-02 帶 id=1、WT-01 帶 id=2），用以驗證元件以 t.name
// 而非 t.id 作為 turbine_id 的契約（見 preselectTurbineId 反例測試）。
const DEFAULT_TURBINES: TurbineData[] = [
  makeTurbine({ id: 1, name: 'WT-02', status: TurbineStatus.OPERATING, powerOutput: 2.0, windSpeed: 11.3 }),
  makeTurbine({ id: 2, name: 'WT-01', status: TurbineStatus.FAULT, powerOutput: 0, windSpeed: 8.5 }),
];

type Lang = 'en' | 'zh';

interface RenderOpts {
  turbines?: TurbineData[];
  preselectTurbineId?: string;
  onClose?: () => void;
  onSubmit?: (req: CreateWorkOrderRequest) => Promise<void>;
  lang?: Lang;
}

function renderWizard(opts: RenderOpts = {}) {
  const onClose = opts.onClose ?? vi.fn();
  const onSubmit = opts.onSubmit ?? vi.fn().mockResolvedValue(undefined);
  render(
    <ThemeProvider>
      <CreateWorkOrderWizard
        farmId="farm-a"
        turbines={opts.turbines ?? DEFAULT_TURBINES}
        preselectTurbineId={opts.preselectTurbineId}
        onClose={onClose}
        onSubmit={onSubmit}
        lang={opts.lang ?? 'zh'}
      />
    </ThemeProvider>,
  );
  return { onClose, onSubmit };
}

// ─── 步驟導覽 helper（lang-aware，避免硬編碼 label 與 renderWizard lang 脫鉤） ──

/** 各 helper 用得到的 label，依 lang 取對應字串。 */
const L = (lang: Lang) => ({
  next: lang === 'zh' ? '下一步' : 'Next',
  title: lang === 'zh' ? '標題' : 'Title',
  desc: lang === 'zh' ? '說明' : 'Description',
});

/** Step 1：點某風機卡（以 name regex 命中，因 accessible name 含 status + power 文字）。 */
function selectTurbine(name: string) {
  fireEvent.click(screen.getByRole('button', { name: new RegExp(name) }));
}

/** 走到 Step 2（選風機 + Next）。 */
function gotoStep2(turbineName = 'WT-01', lang: Lang = 'zh') {
  selectTurbine(turbineName);
  fireEvent.click(screen.getByRole('button', { name: L(lang).next }));
}

/** 走到 Step 3（Step 2 + 填 title/description + Next）。title/description 可覆寫供 summary 斷言。 */
function gotoStep3(
  turbineName = 'WT-01',
  lang: Lang = 'zh',
  title = '齒輪箱軸承更換',
  description = '更換 NDE 軸承並校正對心',
) {
  gotoStep2(turbineName, lang);
  fireEvent.change(screen.getByLabelText(L(lang).title), { target: { value: title } });
  fireEvent.change(screen.getByLabelText(L(lang).desc), { target: { value: description } });
  fireEvent.click(screen.getByRole('button', { name: L(lang).next }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ─── 1. 殼層 / dialog / header / step indicator ──────────────────────────────

describe('CreateWorkOrderWizard — 殼層與 step indicator', () => {
  it('dialog aria-label 與標題隨 lang 切換（zh）', () => {
    renderWizard({ lang: 'zh' });
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', '建立工單');
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('建立工單');
  });

  it('dialog aria-label 與標題隨 lang 切換（en，不外洩中文）', () => {
    renderWizard({ lang: 'en' });
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'Create work order');
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Create work order');
    expect(screen.queryByText('建立工單')).not.toBeInTheDocument();
  });

  it('step indicator 起始於第 1 步 / 共 3 步（zh）', () => {
    renderWizard({ lang: 'zh' });
    expect(screen.getByText('第 1 步 / 共 3 步')).toBeInTheDocument();
  });

  it('step indicator 起始於 Step 1 of 3（en）', () => {
    renderWizard({ lang: 'en' });
    expect(screen.getByText('Step 1 of 3')).toBeInTheDocument();
  });

  it('footer 一律有取消鈕；step 1 無上一步、有下一步、無建立鈕', () => {
    renderWizard();
    expect(screen.getByRole('button', { name: '取消' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下一步' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '上一步' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '建立工單' })).not.toBeInTheDocument();
  });
});

// ─── 2. Step 1：選風機 ───────────────────────────────────────────────────────

describe('CreateWorkOrderWizard — Step 1 選風機', () => {
  it('空風機列表顯示提示卡（zh）', () => {
    renderWizard({ turbines: [] });
    expect(screen.getByText('目前風場沒有可選的風機。')).toBeInTheDocument();
  });

  it('空風機列表顯示提示卡（en）', () => {
    renderWizard({ turbines: [], lang: 'en' });
    expect(screen.getByText('No turbines available in active farm.')).toBeInTheDocument();
  });

  it('風機依 name localeCompare 排序（WT-01 排在 WT-02 前）', () => {
    renderWizard();
    const cards = screen.getAllByRole('button', { name: /WT-0/ });
    expect(cards[0]).toHaveTextContent('WT-01');
    expect(cards[1]).toHaveTextContent('WT-02');
  });

  it('FAULT 風機卡顯示 ⚠ 警示符、OPERATING 卡不顯示', () => {
    renderWizard();
    const fault = screen.getByRole('button', { name: /WT-01/ }); // FAULT
    const ok = screen.getByRole('button', { name: /WT-02/ }); // OPERATING
    expect(within(fault).getByText('⚠')).toBeInTheDocument();
    expect(within(ok).queryByText('⚠')).not.toBeInTheDocument();
  });

  it('風機卡顯示功率 / 風速摘要（toFixed 格式）', () => {
    renderWizard();
    const ok = screen.getByRole('button', { name: /WT-02/ });
    expect(within(ok).getByText('2.00 MW · 11.3 m/s')).toBeInTheDocument();
  });

  it('未選風機時下一步 disabled；選後啟用並 aria-pressed', () => {
    renderWizard();
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    const card = screen.getByRole('button', { name: /WT-01/ });
    fireEvent.click(card);
    expect(card).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });

  it('preselectTurbineId 預選對應風機卡並解鎖下一步', () => {
    renderWizard({ preselectTurbineId: 'WT-01' });
    expect(screen.getByRole('button', { name: /WT-01/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /WT-02/ })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });

  it('preselectTurbineId 以 name 比對高亮：傳數字 id 字串無任何卡被選（但值原樣帶入）', () => {
    // turbineId 直接初始化為 preselectTurbineId；高亮邏輯 turbineId === t.name。
    // WT-01 帶 t.id=2，若元件誤用 id 比對 name 會誤亮 WT-01 → 此處驗證兩卡皆未高亮。
    renderWizard({ preselectTurbineId: '2' });
    expect(screen.getByRole('button', { name: /WT-01/ })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: /WT-02/ })).toHaveAttribute('aria-pressed', 'false');
    // turbineId 非空（'2' 原樣帶入）→ 下一步仍解鎖（preselect 值由呼叫端負責正確性）
    expect(screen.getByRole('button', { name: '下一步' })).toBeEnabled();
  });
});

// ─── 3. Step 2：工單細節 + gating ────────────────────────────────────────────

describe('CreateWorkOrderWizard — Step 2 工單細節', () => {
  it('Next 進到 Step 2 顯示細節欄位與 step indicator 更新', () => {
    renderWizard();
    gotoStep2();
    expect(screen.getByText('第 2 步 / 共 3 步')).toBeInTheDocument();
    expect(screen.getByLabelText('工單類型')).toBeInTheDocument();
    expect(screen.getByLabelText('優先級')).toBeInTheDocument();
    expect(screen.getByLabelText('標題')).toBeInTheDocument();
    expect(screen.getByLabelText('說明')).toBeInTheDocument();
    expect(screen.getByLabelText('來源警報碼')).toBeInTheDocument();
  });

  it('title 或 description 任一空白 → 下一步 disabled；皆填 → 啟用', () => {
    renderWizard();
    gotoStep2();
    const next = screen.getByRole('button', { name: '下一步' });
    expect(next).toBeDisabled();

    fireEvent.change(screen.getByLabelText('標題'), { target: { value: '更換軸承' } });
    expect(next).toBeDisabled(); // description 仍空

    fireEvent.change(screen.getByLabelText('說明'), { target: { value: '詳細說明' } });
    expect(next).toBeEnabled();
  });

  it('純空白 title 不算填寫（trim 後為空）→ 下一步維持 disabled', () => {
    renderWizard();
    gotoStep2();
    fireEvent.change(screen.getByLabelText('標題'), { target: { value: '   ' } });
    fireEvent.change(screen.getByLabelText('說明'), { target: { value: '有內容' } });
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
  });

  it('純空白 description 不算填寫（trim 後為空）→ 下一步維持 disabled', () => {
    renderWizard();
    gotoStep2();
    fireEvent.change(screen.getByLabelText('標題'), { target: { value: '有標題' } });
    fireEvent.change(screen.getByLabelText('說明'), { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
  });

  it('Back 從 Step 2 回 Step 1 並保留已選風機', () => {
    renderWizard();
    gotoStep2('WT-01');
    fireEvent.click(screen.getByRole('button', { name: '上一步' }));
    expect(screen.getByText('第 1 步 / 共 3 步')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /WT-01/ })).toHaveAttribute('aria-pressed', 'true');
  });

  it('type / priority select 提供完整選項', () => {
    renderWizard();
    gotoStep2();
    const type = screen.getByLabelText('工單類型');
    expect(within(type).getByRole('option', { name: '故障維修' })).toBeInTheDocument();
    expect(within(type).getByRole('option', { name: '預防保養' })).toBeInTheDocument();
    expect(within(type).getByRole('option', { name: '定檢' })).toBeInTheDocument();
    expect(within(type).getByRole('option', { name: '試運轉' })).toBeInTheDocument();
    const prio = screen.getByLabelText('優先級');
    expect(within(prio).getByRole('option', { name: '緊急' })).toBeInTheDocument();
  });
});

// ─── 4. Step 3：派工 + 工時 + summary ────────────────────────────────────────

describe('CreateWorkOrderWizard — Step 3 派工與工時', () => {
  it('Next 進到 Step 3 顯示派工欄位與建立鈕（無下一步）', () => {
    renderWizard();
    gotoStep3();
    expect(screen.getByText('第 3 步 / 共 3 步')).toBeInTheDocument();
    expect(screen.getByLabelText('派工人員 UUID')).toBeInTheDocument();
    expect(screen.getByLabelText('工班人數')).toBeInTheDocument();
    expect(screen.getByLabelText('預估工時')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '建立工單' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '下一步' })).not.toBeInTheDocument();
  });

  it('summary 卡反映已選風機 / 類型 / 標題', () => {
    renderWizard();
    gotoStep3('WT-01', 'zh', '齒輪箱軸承更換');
    // summary 行文字被 <strong> 標籤 + StatusPill 拆成多段，改以 toHaveTextContent 做子字串斷言
    const review = screen.getByText('檢閱').parentElement;
    if (!review) throw new Error('summary 檢閱卡未找到');
    expect(review).toHaveTextContent('WT-01');
    expect(review).toHaveTextContent('故障維修'); // default type=corrective
    expect(review).toHaveTextContent('齒輪箱軸承更換');
  });

  it('crew_size 夾限：>20 夾到 20、<1 夾到 1（DOM 即時反映）', () => {
    renderWizard();
    gotoStep3();
    const crew = screen.getByLabelText('工班人數');
    fireEvent.change(crew, { target: { value: '25' } });
    expect(crew).toHaveValue(20);
    fireEvent.change(crew, { target: { value: '0' } });
    expect(crew).toHaveValue(1);
  });

  it('crew_size 夾限值真的寫進送出 request（>20 → 序列化為 20）', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderWizard({ onSubmit });
    gotoStep3('WT-01');
    fireEvent.change(screen.getByLabelText('工班人數'), { target: { value: '25' } });
    fireEvent.click(screen.getByRole('button', { name: '建立工單' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect((onSubmit.mock.calls[0][0] as CreateWorkOrderRequest).crew_size).toBe(20);
  });
});

// ─── 5. 送出（buildRequest 序列化 + async 中間態 + 錯誤） ──────────────────────

describe('CreateWorkOrderWizard — 送出', () => {
  it('送出帶完整 request：trim 值、空選填欄送 null、estimated_hours Number 轉型', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderWizard({ onSubmit });
    gotoStep2('WT-01');
    fireEvent.change(screen.getByLabelText('標題'), { target: { value: '  更換軸承  ' } });
    fireEvent.change(screen.getByLabelText('說明'), { target: { value: '  詳細說明  ' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    fireEvent.change(screen.getByLabelText('預估工時'), { target: { value: '4.5' } });
    fireEvent.click(screen.getByRole('button', { name: '建立工單' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      farm_id: 'farm-a',
      turbine_id: 'WT-01',
      type: 'corrective',
      title: '更換軸承',
      description: '詳細說明',
      priority: 'normal',
      source_alarm_code: null,
      assignee_id: null,
      crew_size: 1,
      estimated_hours: 4.5,
    });
  });

  it('estimated_hours 空白送 null；source_alarm_code / assignee 有填則送 trim 值', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderWizard({ onSubmit });
    gotoStep2('WT-02');
    fireEvent.change(screen.getByLabelText('標題'), { target: { value: '定檢' } });
    fireEvent.change(screen.getByLabelText('說明'), { target: { value: '年度定檢' } });
    fireEvent.change(screen.getByLabelText('來源警報碼'), { target: { value: '  ALM_GEN_TEMP_HIGH  ' } });
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));

    fireEvent.change(screen.getByLabelText('派工人員 UUID'), {
      target: { value: '  00000000-0000-0000-0000-000000000001  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: '建立工單' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const req = onSubmit.mock.calls[0][0] as CreateWorkOrderRequest;
    expect(req.estimated_hours).toBeNull();
    expect(req.source_alarm_code).toBe('ALM_GEN_TEMP_HIGH');
    expect(req.assignee_id).toBe('00000000-0000-0000-0000-000000000001');
  });

  it('送出中：建立鈕文案改「建立中…」且 disabled（防重複送出）', async () => {
    let resolveSubmit: () => void = () => {};
    const onSubmit = vi.fn(
      () => new Promise<void>(res => { resolveSubmit = res; }),
    );
    renderWizard({ onSubmit });
    gotoStep3('WT-01');
    fireEvent.click(screen.getByRole('button', { name: '建立工單' }));

    // 送出鈕 aria-label 恆為「建立工單」，submitting 中態只反映在可見文字 → 以 text 查詢
    const submittingBtn = (await screen.findByText('建立中…')).closest('button');
    expect(submittingBtn).toBeDisabled();

    resolveSubmit();
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  });

  it('onSubmit reject → 顯示 ⚠ 錯誤卡、不關閉、建立鈕回復可按', async () => {
    const onClose = vi.fn();
    const onSubmit = vi.fn().mockRejectedValue(new Error('後端拒絕：風機不存在'));
    renderWizard({ onSubmit, onClose });
    gotoStep3('WT-01');
    fireEvent.click(screen.getByRole('button', { name: '建立工單' }));

    expect(await screen.findByText('⚠ 後端拒絕：風機不存在')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '建立工單' })).toBeEnabled();
  });

  it('onSubmit resolve → 元件不自動 onClose（關閉由呼叫端負責）', async () => {
    const { onClose, onSubmit } = renderWizard();
    gotoStep3('WT-01');
    fireEvent.click(screen.getByRole('button', { name: '建立工單' }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onClose).not.toHaveBeenCalled();
  });
});

// ─── 6. 關閉路徑 ─────────────────────────────────────────────────────────────

describe('CreateWorkOrderWizard — 關閉路徑', () => {
  it('遮罩點擊 → onClose', () => {
    const { onClose } = renderWizard();
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('✕ 鈕 → onClose', () => {
    const { onClose } = renderWizard();
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('取消鈕 → onClose', () => {
    const { onClose } = renderWizard();
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('對話框內容點擊（stopPropagation）→ 不 onClose', () => {
    const { onClose } = renderWizard();
    fireEvent.click(screen.getByRole('heading', { level: 2 }));
    expect(onClose).not.toHaveBeenCalled();
  });
});
