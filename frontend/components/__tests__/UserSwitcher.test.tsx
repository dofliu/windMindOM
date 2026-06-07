/**
 * UserSwitcher component render 測試（WMOM-20260607-01，EPIC-M5 測試覆蓋擴大）。
 *
 * `UserSwitcher.tsx`（231 行）是 sidebar 底部 mock-login 切換器（WMOM-20260510-01 Part B）：
 *   - trigger 鈕顯示目前 user 名 + 主要 role pill，向上彈出 dropdown（listbox）
 *   - dropdown 列出所有 `is_active` fixture user（filter 掉停用者），點選即切換
 *   - 目前 user 標 aria-selected + 「使用中 / Active」；`dev_mode_only` user 標「dev / dev only」tag
 *   - 多角 user（Owner）role 以「 / 」join；email 以「 · 」附後
 *   - 無障礙：trigger aria-haspopup/aria-expanded、Escape 關閉、click-outside 關閉、
 *     option Enter/Space 觸發選取
 *
 * 本元件 props 僅 `lang`，資料全來自 `useCurrentUser` context。為精確控制 currentUser /
 * availableUsers（含一名停用者驗 filter）並 spy `setCurrentUser` 接線，**mock 掉
 * `useCurrentUser` hook**；`useTheme` 用真實 ThemeProvider。`Btn`/ui 不涉入（純內聯樣式）。
 *
 * 守住契約：殼層（trigger aria + 名稱 + roles）/ 展開收合 / 選項清單（filter is_active·
 * aria-selected·dev tag·多角 join·email）/ 選取接線（click·Enter·Space → setCurrentUser +
 * 關閉）/ 關閉路徑（click-outside·Escape·dropdown 內 mousedown 不關）/ 語系（en/zh 全標籤）。
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import React from 'react';
import UserSwitcher from '../UserSwitcher';
import { ThemeProvider } from '../../theme/ThemeProvider';
import type { MockUser } from '../../services/mockUsers';

// ─── mock useCurrentUser ────────────────────────────────────────────────────
// 本元件唯一資料來源是 useCurrentUser context。mock 之以注入 currentUser /
// availableUsers（含停用者驗 filter）並 spy setCurrentUser，避免依賴 localStorage。

interface MockCtx {
  currentUser: MockUser;
  setCurrentUser: (u: MockUser) => void;
  availableUsers: ReadonlyArray<MockUser>;
}

// 每個測試前由 setCtx(...) 重設；mock factory 於 call time 讀此變數（lazy）。
let mockCtx: MockCtx;

vi.mock('../../hooks/useCurrentUser', () => ({
  useCurrentUser: () => mockCtx,
}));

// ─── 工廠 ──────────────────────────────────────────────────────────────────

/** 產生結構完整的 MockUser（不用 `as` 強轉）。 */
function makeUser(over: Partial<MockUser> = {}): MockUser {
  return {
    id: '00000000-0000-0000-0000-0000000000a1',
    name: 'Alice Chen',
    email: 'alice@wmom.dev',
    roles: ['employee'],
    is_active: true,
    dev_mode_only: false,
    ...over,
  };
}

const ALICE = makeUser();
const BOB = makeUser({
  id: '00000000-0000-0000-0000-0000000000a2',
  name: 'Bob Lin',
  email: 'bob@wmom.dev',
  roles: ['leader'],
});
const CAROL = makeUser({
  id: '00000000-0000-0000-0000-0000000000a3',
  name: 'Carol Wang',
  email: 'carol@wmom.dev',
  roles: ['treasury'],
});
const OWNER = makeUser({
  id: '00000000-0000-0000-0000-0000000000a4',
  name: 'Owner (dev)',
  email: 'owner@wmom.dev',
  roles: ['employee', 'leader', 'treasury', 'owner'],
  dev_mode_only: true,
});
/** 停用 user — 應被 is_active filter 排除（dropdown 不顯示）。 */
const INACTIVE = makeUser({
  id: '00000000-0000-0000-0000-0000000000a9',
  name: 'Ghost User',
  email: 'ghost@wmom.dev',
  roles: ['employee'],
  is_active: false,
});

/** 設定本測試使用的 context（含 spy setCurrentUser）。回傳 spy 供斷言。 */
function setCtx(opts: { currentUser?: MockUser; availableUsers?: ReadonlyArray<MockUser> } = {}) {
  const setCurrentUser = vi.fn();
  mockCtx = {
    currentUser: opts.currentUser ?? ALICE,
    setCurrentUser,
    availableUsers: opts.availableUsers ?? [ALICE, BOB, OWNER],
  };
  return setCurrentUser;
}

// ─── render wrapper ─────────────────────────────────────────────────────────

function renderSwitcher(lang: 'en' | 'zh' = 'zh') {
  return render(
    <ThemeProvider>
      <UserSwitcher lang={lang} />
    </ThemeProvider>,
  );
}

/** 展開 dropdown（點 trigger）並回傳 listbox 元素。 */
function openDropdown(lang: 'en' | 'zh' = 'zh') {
  const triggerName = lang === 'zh' ? '切換使用者' : 'Switch user';
  fireEvent.click(screen.getByRole('button', { name: triggerName }));
  return screen.getByRole('listbox');
}

beforeEach(() => {
  setCtx();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ─── 殼層 / 關閉態 ───────────────────────────────────────────────────────────

describe('UserSwitcher — 殼層 / 關閉態', () => {
  it('trigger 鈕有 aria-haspopup=listbox 與初始 aria-expanded=false', () => {
    renderSwitcher();
    const trigger = screen.getByRole('button', { name: '切換使用者' });
    expect(trigger).toHaveAttribute('aria-haspopup', 'listbox');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('顯示目前 user 名稱與主要 role（zh）', () => {
    renderSwitcher();
    const trigger = screen.getByRole('button', { name: '切換使用者' });
    expect(within(trigger).getByText('Alice Chen')).toBeInTheDocument();
    expect(within(trigger).getByText('員工')).toBeInTheDocument();
  });

  it('初始未展開時不渲染 listbox', () => {
    renderSwitcher();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('多角 user（Owner）role 以「 / 」join 顯示於 trigger', () => {
    setCtx({ currentUser: OWNER });
    renderSwitcher();
    const trigger = screen.getByRole('button', { name: '切換使用者' });
    expect(within(trigger).getByText('員工 / 組長 / 財務 / 老闆')).toBeInTheDocument();
  });

  it('treasury 單角 user（Carol）trigger 顯示「財務」role（zh）', () => {
    setCtx({ currentUser: CAROL });
    renderSwitcher();
    const trigger = screen.getByRole('button', { name: '切換使用者' });
    expect(within(trigger).getByText('Carol Wang')).toBeInTheDocument();
    expect(within(trigger).getByText('財務')).toBeInTheDocument();
  });
});

// ─── 展開 / 收合 ─────────────────────────────────────────────────────────────

describe('UserSwitcher — 展開 / 收合', () => {
  it('點 trigger 展開 dropdown（aria-expanded=true + listbox 出現）', () => {
    renderSwitcher();
    const listbox = openDropdown();
    expect(listbox).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '切換使用者' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('再點 trigger 收合 dropdown', () => {
    renderSwitcher();
    const trigger = screen.getByRole('button', { name: '切換使用者' });
    fireEvent.click(trigger);
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    fireEvent.click(trigger);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('listbox 有 aria-label「模擬使用者」與「模擬登入（dev）」標頭（zh）', () => {
    renderSwitcher();
    const listbox = openDropdown();
    expect(listbox).toHaveAttribute('aria-label', '模擬使用者');
    expect(screen.getByText('模擬登入（dev）')).toBeInTheDocument();
  });
});

// ─── 選項清單 ────────────────────────────────────────────────────────────────

describe('UserSwitcher — 選項清單', () => {
  it('每個 active user 各一個 role=option', () => {
    setCtx({ availableUsers: [ALICE, BOB, OWNER] });
    renderSwitcher();
    openDropdown();
    expect(screen.getAllByRole('option')).toHaveLength(3);
  });

  it('過濾掉 is_active=false 的 user（不出現在 dropdown）', () => {
    setCtx({ availableUsers: [ALICE, BOB, INACTIVE] });
    renderSwitcher();
    const listbox = openDropdown();
    expect(screen.getAllByRole('option')).toHaveLength(2);
    expect(within(listbox).queryByText('Ghost User')).not.toBeInTheDocument();
  });

  it('目前 user 的 option aria-selected=true、其餘為 false', () => {
    setCtx({ currentUser: BOB, availableUsers: [ALICE, BOB, OWNER] });
    renderSwitcher();
    const listbox = openDropdown();
    const bobOption = within(listbox).getByText('Bob Lin').closest('[role="option"]');
    const aliceOption = within(listbox).getByText('Alice Chen').closest('[role="option"]');
    expect(bobOption).not.toBeNull();
    expect(bobOption).toHaveAttribute('aria-selected', 'true');
    expect(aliceOption).toHaveAttribute('aria-selected', 'false');
  });

  it('目前 user 標「使用中」且僅出現一次', () => {
    setCtx({ currentUser: ALICE, availableUsers: [ALICE, BOB, OWNER] });
    renderSwitcher();
    openDropdown();
    expect(screen.getAllByText('使用中')).toHaveLength(1);
  });

  it('dev_mode_only user 顯示「dev」tag、非 dev user 不顯示', () => {
    setCtx({ availableUsers: [ALICE, OWNER] });
    renderSwitcher();
    const listbox = openDropdown();
    // getByText 預設以 getNodeText 比對「直接 text-node 子節點」串接值，不含巢狀 element
    // 內文；故 name div「Owner (dev)<span>dev</span>」的可比對文字僅為「Owner (dev)」，
    // 巢狀 dev tag span 不干擾此 exact match。
    const ownerOption = within(listbox).getByText('Owner (dev)').closest('[role="option"]');
    const aliceOption = within(listbox).getByText('Alice Chen').closest('[role="option"]');
    expect(ownerOption).not.toBeNull();
    expect(within(ownerOption as HTMLElement).getByText('dev')).toBeInTheDocument();
    expect(within(aliceOption as HTMLElement).queryByText('dev')).not.toBeInTheDocument();
  });

  it('option 內顯示 role join 與 email（以「 · 」附後）', () => {
    setCtx({ availableUsers: [ALICE] });
    renderSwitcher();
    const listbox = openDropdown();
    // formatRoles + ` · ${email}` 同一文字節點
    expect(within(listbox).getByText('員工 · alice@wmom.dev')).toBeInTheDocument();
  });

  it('email 為空字串時不附「 · 」', () => {
    // 用 BOB（與 currentUser ALICE 不同 id）避免隱式 isActive=true 混淆判讀
    setCtx({ availableUsers: [makeUser({ ...BOB, email: '' })] });
    renderSwitcher();
    const listbox = openDropdown();
    expect(within(listbox).getByText('組長')).toBeInTheDocument();
    expect(within(listbox).queryByText(/·/)).not.toBeInTheDocument();
  });

  it('availableUsers 為空陣列時 dropdown 展開但無任何 option', () => {
    setCtx({ availableUsers: [] });
    renderSwitcher();
    const listbox = openDropdown();
    expect(listbox).toBeInTheDocument();
    expect(within(listbox).queryAllByRole('option')).toHaveLength(0);
    // 標頭仍渲染
    expect(screen.getByText('模擬登入（dev）')).toBeInTheDocument();
  });
});

// ─── 選取接線 ────────────────────────────────────────────────────────────────

describe('UserSwitcher — 選取接線', () => {
  it('點 option → setCurrentUser(該 user) 且 dropdown 收合', () => {
    const setCurrentUser = setCtx({ currentUser: ALICE, availableUsers: [ALICE, BOB, OWNER] });
    renderSwitcher();
    const listbox = openDropdown();
    fireEvent.click(within(listbox).getByText('Bob Lin'));
    expect(setCurrentUser).toHaveBeenCalledTimes(1);
    expect(setCurrentUser).toHaveBeenCalledWith(BOB);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '切換使用者' })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
  });

  it('option 上按 Enter → setCurrentUser + 收合', () => {
    const setCurrentUser = setCtx({ availableUsers: [ALICE, BOB, OWNER] });
    renderSwitcher();
    const listbox = openDropdown();
    const bobOption = within(listbox).getByText('Bob Lin').closest('[role="option"]');
    expect(bobOption).not.toBeNull();
    fireEvent.keyDown(bobOption as HTMLElement, { key: 'Enter' });
    expect(setCurrentUser).toHaveBeenCalledWith(BOB);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('option 上按 Space → setCurrentUser + 收合', () => {
    const setCurrentUser = setCtx({ availableUsers: [ALICE, BOB, OWNER] });
    renderSwitcher();
    const listbox = openDropdown();
    const ownerOption = within(listbox).getByText('Owner (dev)').closest('[role="option"]');
    expect(ownerOption).not.toBeNull();
    fireEvent.keyDown(ownerOption as HTMLElement, { key: ' ' });
    expect(setCurrentUser).toHaveBeenCalledWith(OWNER);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('點選目前 user 的 option → 仍觸發 setCurrentUser 且 dropdown 收合（無自選 guard）', () => {
    const setCurrentUser = setCtx({ currentUser: ALICE, availableUsers: [ALICE, BOB, OWNER] });
    renderSwitcher();
    const listbox = openDropdown();
    fireEvent.click(within(listbox).getByText('Alice Chen'));
    expect(setCurrentUser).toHaveBeenCalledWith(ALICE);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('option 上按其他鍵（如 Tab）不觸發 setCurrentUser', () => {
    const setCurrentUser = setCtx({ availableUsers: [ALICE, BOB] });
    renderSwitcher();
    const listbox = openDropdown();
    const bobOption = within(listbox).getByText('Bob Lin').closest('[role="option"]');
    fireEvent.keyDown(bobOption as HTMLElement, { key: 'Tab' });
    expect(setCurrentUser).not.toHaveBeenCalled();
    // dropdown 維持開啟
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });
});

// ─── 關閉路徑 ────────────────────────────────────────────────────────────────

describe('UserSwitcher — 關閉路徑', () => {
  it('click outside（document.body mousedown）關閉 dropdown', () => {
    renderSwitcher();
    openDropdown();
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('dropdown 內 mousedown 不關閉', () => {
    renderSwitcher();
    const listbox = openDropdown();
    fireEvent.mouseDown(listbox);
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('Escape 鍵關閉 dropdown', () => {
    renderSwitcher();
    openDropdown();
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
});

// ─── 語系（en）────────────────────────────────────────────────────────────────

describe('UserSwitcher — 語系（en）', () => {
  it('trigger aria-label 與 role 標籤英文化', () => {
    setCtx({ currentUser: BOB });
    renderSwitcher('en');
    const trigger = screen.getByRole('button', { name: 'Switch user' });
    expect(within(trigger).getByText('leader')).toBeInTheDocument();
  });

  it('dropdown 標頭、aria-label、dev tag、使用中標籤英文化', () => {
    setCtx({ currentUser: ALICE, availableUsers: [ALICE, OWNER] });
    renderSwitcher('en');
    const listbox = openDropdown('en');
    expect(listbox).toHaveAttribute('aria-label', 'Mock users');
    expect(screen.getByText('Mock login (dev)')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    const ownerOption = within(listbox).getByText('Owner (dev)').closest('[role="option"]');
    expect(within(ownerOption as HTMLElement).getByText('dev only')).toBeInTheDocument();
  });

  it('多角 user role 以「 / 」join 英文化', () => {
    setCtx({ availableUsers: [OWNER] });
    renderSwitcher('en');
    const listbox = openDropdown('en');
    expect(
      within(listbox).getByText('employee / leader / treasury / owner · owner@wmom.dev'),
    ).toBeInTheDocument();
  });
});
