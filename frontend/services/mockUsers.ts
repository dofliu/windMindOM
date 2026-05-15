/**
 * Mock user fixtures（WMOM-20260510-01 Part B — frontend mock login）。
 *
 * 目的：給 demo 操作者一個簡易 user switcher，可在 Alice / Bob / Carol / Owner
 * 之間切換以扮不同 signoff 階級（employee / leader / treasury）。
 *
 * 設計決策（見 work-logs/2026-05/2026-05-15-mock-login-frontend.md）：
 *   - 純 frontend constant；不做 backend user table（M5+ 真 auth 時再升級）
 *   - UUID 是 placeholder（不與既有 ledger 衝突，後端 `decided_by` 無 FK）
 *   - Owner 標 `dev_mode_only=true`：UI 顯示 (dev only) tag；production 模式跑
 *     signoff chain 會被後端 separation guard 擋（行為正確）
 *
 * Backend 對應：`shared/dev_mode.py` + `signoff_repository._check_actor_separation`。
 */

export type MockUserRole = 'employee' | 'leader' | 'treasury' | 'owner';

export interface MockUser {
  /** UUID v4 string，後端 signoff/dispatch action 帶此欄為 actor_id。 */
  id: string;
  /** 顯示名稱（中英 demo 皆用此）。 */
  name: string;
  /** Email（顯示用，無實際驗證）。 */
  email: string;
  /** 此 user 可扮的 signoff 階級。 */
  roles: ReadonlyArray<MockUserRole>;
  /** 是否啟用（false 不出現在 switcher）。 */
  is_active: boolean;
  /**
   * 是否僅 dev mode 可用。Owner=true（production 模式選 Owner 跑 chain
   * 會被後端 separation guard 擋）。其餘 fixture user 為 false。
   */
  dev_mode_only: boolean;
}

/** 4 個 fixture user，順序即 sidebar dropdown 顯示順序。 */
export const MOCK_USERS: ReadonlyArray<MockUser> = [
  {
    id: '00000000-0000-0000-0000-0000000000a1',
    name: 'Alice Chen',
    email: 'alice@wmom.dev',
    roles: ['employee'],
    is_active: true,
    dev_mode_only: false,
  },
  {
    id: '00000000-0000-0000-0000-0000000000a2',
    name: 'Bob Lin',
    email: 'bob@wmom.dev',
    roles: ['leader'],
    is_active: true,
    dev_mode_only: false,
  },
  {
    id: '00000000-0000-0000-0000-0000000000a3',
    name: 'Carol Wang',
    email: 'carol@wmom.dev',
    roles: ['treasury'],
    is_active: true,
    dev_mode_only: false,
  },
  {
    id: '00000000-0000-0000-0000-0000000000a4',
    name: 'Owner (dev)',
    email: 'owner@wmom.dev',
    roles: ['employee', 'leader', 'treasury', 'owner'],
    is_active: true,
    dev_mode_only: true,
  },
];

/** 預設 user（首次載入或 localStorage 無值時）— 選 Alice（最低權限，安全預設）。 */
export const DEFAULT_USER: MockUser = MOCK_USERS[0];

/** localStorage key — 持久化目前選的 actor_id。 */
export const ACTOR_ID_STORAGE_KEY = 'wmom_actor_id';

/**
 * 依 id 找 user；找不到回傳 null。
 *
 * @param id 要查的 actor_id（UUID）
 */
export const findMockUser = (id: string | null | undefined): MockUser | null => {
  if (!id) return null;
  return MOCK_USERS.find(u => u.id === id) ?? null;
};

/**
 * 同步讀目前 actor_id（給非 React 模組用，例如 service 層 callback）。
 *
 * 讀 localStorage；找不到或 SSR 環境 fallback 到 DEFAULT_USER.id。
 * React component 應改用 `useCurrentUser` hook 以訂閱變化。
 */
export const getCurrentActorId = (): string => {
  if (typeof window === 'undefined') return DEFAULT_USER.id;
  const stored = window.localStorage.getItem(ACTOR_ID_STORAGE_KEY);
  if (stored && findMockUser(stored)) return stored;
  return DEFAULT_USER.id;
};
