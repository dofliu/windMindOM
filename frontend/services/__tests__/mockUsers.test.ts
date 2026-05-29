/**
 * mockUsers 純函式 + fixture 契約回歸測試（WMOM-20260529-01）。
 *
 * 為什麼測這個：`mockUsers.ts` 是 WMOM-20260510-01 Part B「frontend mock login」
 * 的身份核心 —— 4 個 fixture user（Alice/Bob/Carol/Owner）餵 signoff 多階扮演，
 * `getCurrentActorId()` 是**非 React 模組（service 層 callback）唯一的同步身份來源**，
 * 所有 dispatch / approve API call 的 actor_id 都從這裡來。是 M6 客戶 demo 跑完整
 * lifecycle 的關鍵（沒有身份切換無法演 employee→leader→treasury 三階簽核）。
 *
 * 測試切入點：純函式層 + fixture 契約，零 DOM render、零新依賴
 *   - `findMockUser` / `getCurrentActorId`：只依賴 localStorage（jsdom 已提供，
 *     vitest.config.ts `environment: 'jsdom'`），確定性高、不脆弱
 *   - fixture 契約：用 `MockUserRole` 型別宣告期望表 → compile-time 窮舉
 *     （未來改 fixture 的 role / 數量 / dev_mode_only 時 tsc 或 runtime 立刻紅，
 *     迫使刻意更新而非默默漂移）
 *
 * 不測 `useCurrentUser` hook（需 React render + Context，脆弱性較高，留獨立 session）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ACTOR_ID_STORAGE_KEY,
  DEFAULT_USER,
  MOCK_USERS,
  findMockUser,
  getCurrentActorId,
  type MockUser,
  type MockUserRole,
} from '../mockUsers';

// fixture 用 **placeholder** UUID（非真隨機 v4：version nibble 是 0 不是 4），故只驗
// 8-4-4-4-12 十六進位分段結構，不驗 version/variant nibble。命名刻意標 PLACEHOLDER
// 以免讀者誤以為這些是標準 v4 UUID。
const PLACEHOLDER_UUID_SHAPE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

describe('mockUsers / MOCK_USERS fixture 契約', () => {
  it('剛好 4 個 fixture user（Alice / Bob / Carol / Owner）', () => {
    expect(MOCK_USERS).toHaveLength(4);
  });

  it('所有 id 唯一（避免 switcher 撞 key / actor_id 解析歧義）', () => {
    const ids = MOCK_USERS.map(u => u.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('所有 id 都符合 UUID 8-4-4-4-12 分段格式（placeholder，非標準 v4）', () => {
    for (const u of MOCK_USERS) {
      expect(u.id, `${u.name} 的 id 不符 UUID 分段格式`).toMatch(PLACEHOLDER_UUID_SHAPE);
    }
  });

  // 注意：此處只鎖 service 層的「資料屬性」is_active=true，不測 UI render。
  // switcher dropdown 的 `.filter(u => u.is_active)` 顯示邏輯在 UserSwitcher.tsx；
  // 而 findMockUser / getCurrentActorId 本身**不**過濾 is_active（source 無此邏輯）。
  it('所有 fixture 的 is_active 為 true（switcher filter 的資料前提）', () => {
    for (const u of MOCK_USERS) {
      expect(u.is_active, `${u.name} 應 is_active`).toBe(true);
    }
  });

  it('email 唯一且皆為 @wmom.dev demo 網域', () => {
    const emails = MOCK_USERS.map(u => u.email);
    expect(new Set(emails).size).toBe(emails.length);
    for (const u of MOCK_USERS) {
      expect(u.email).toMatch(/@wmom\.dev$/);
    }
  });

  // 用 name→roles 的型別化期望表窮舉每個 fixture 的 role 集合。保護層級：
  //   - value（role 值）：`ReadonlyArray<MockUserRole>` 宣告 → 改 MockUserRole 型別漏補
  //     此表 = **compile-time 紅**（tsc）。
  //   - key（user name）：型別是 string、非 union，無 compile-time 保護 → 新增 fixture 漏補
  //     此表只由下方 `MOCK_USERS.map(name).sort()` vs `Object.keys` 的 **runtime 斷言**抓。
  // roles 比較刻意 sort 後比對：`MockUser.roles` 語義是「可扮的階級集合」（source 與
  // signoff_repository / UserSwitcher 皆只用 `.includes()`），不含順序契約 → 鎖成員不鎖順序，
  // 避免未來 source 調整 roles 排列（語義不變）卻誤判紅。
  it('每個 fixture 的 roles 集合與 demo 簽核階級設計一致', () => {
    const expectedRoles: Record<string, ReadonlyArray<MockUserRole>> = {
      'Alice Chen': ['employee'],
      'Bob Lin': ['leader'],
      'Carol Wang': ['treasury'],
      'Owner (dev)': ['employee', 'leader', 'treasury', 'owner'],
    };
    expect(MOCK_USERS.map(u => u.name).sort()).toEqual(
      Object.keys(expectedRoles).sort(),
    );
    for (const u of MOCK_USERS) {
      expect([...u.roles].sort(), `${u.name} roles 集合不符`).toEqual(
        [...expectedRoles[u.name]].sort(),
      );
    }
  });

  it('只有 Owner 標 dev_mode_only=true，且 Owner 是唯一含 owner role 者', () => {
    const devOnly = MOCK_USERS.filter(u => u.dev_mode_only);
    expect(devOnly).toHaveLength(1);
    expect(devOnly[0].name).toBe('Owner (dev)');

    const owners = MOCK_USERS.filter(u => u.roles.includes('owner'));
    expect(owners).toHaveLength(1);
    expect(owners[0]).toBe(devOnly[0]);
  });

  it('非 Owner 三人皆非 dev_mode_only（production 模式可正常扮三階）', () => {
    const normal = MOCK_USERS.filter(u => !u.roles.includes('owner'));
    expect(normal).toHaveLength(3);
    for (const u of normal) {
      expect(u.dev_mode_only, `${u.name} 不應 dev_mode_only`).toBe(false);
    }
  });
});

describe('mockUsers / DEFAULT_USER 與常數', () => {
  it('DEFAULT_USER 是清單第一個（Alice）—— 最低權限為安全預設', () => {
    expect(DEFAULT_USER).toBe(MOCK_USERS[0]);
    expect(DEFAULT_USER.name).toBe('Alice Chen');
    // 安全預設：預設身份只有 employee，不含 leader/treasury/owner 任何高權限 role。
    expect(DEFAULT_USER.roles).toEqual(['employee']);
  });

  it('ACTOR_ID_STORAGE_KEY 鎖定為 wmom_actor_id（跨模組 / 跨 session 持久化契約）', () => {
    // useCurrentUser.tsx 與此常數共用同一 key；改動會使既有使用者 localStorage 失聯。
    expect(ACTOR_ID_STORAGE_KEY).toBe('wmom_actor_id');
  });
});

describe('mockUsers / findMockUser', () => {
  it('null / undefined / 空字串 → null（falsy guard）', () => {
    expect(findMockUser(null)).toBeNull();
    expect(findMockUser(undefined)).toBeNull();
    expect(findMockUser('')).toBeNull();
  });

  it('每個合法 id 都對應回正確 user', () => {
    for (const u of MOCK_USERS) {
      expect(findMockUser(u.id)).toBe(u);
    }
  });

  it('未知 id → null（不亂回 fallback，由呼叫端決定預設）', () => {
    expect(findMockUser('00000000-0000-0000-0000-00000000ffff')).toBeNull();
    // 大小寫敏感：fixture id 為小寫 hex，大寫不匹配（避免「看起來相同」的混淆）。
    expect(findMockUser(MOCK_USERS[0].id.toUpperCase())).toBeNull();
  });
});

describe('mockUsers / getCurrentActorId（localStorage 互動）', () => {
  // beforeEach clear 已足夠隔離（即使前一 test 異常中止，下一 test 前仍會 clear）；
  // 與既有 useCostData.test.ts 只用 beforeEach 的風格一致，不另加 afterEach。
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('localStorage 無值 → 回 DEFAULT_USER.id（Alice）', () => {
    expect(getCurrentActorId()).toBe(DEFAULT_USER.id);
  });

  it('localStorage 存合法 id → 原樣回傳該 id', () => {
    const bob = MOCK_USERS.find(u => u.name === 'Bob Lin')!;
    window.localStorage.setItem(ACTOR_ID_STORAGE_KEY, bob.id);
    expect(getCurrentActorId()).toBe(bob.id);
  });

  it('dev_mode_only=true 的 Owner id 仍被正常回傳（getCurrentActorId 不過濾 dev_mode_only）', () => {
    // 防呆：source 對 dev_mode_only 無任何特殊過濾；若未來有人誤以為「dev user 不該被
    // getCurrentActorId 回傳」而加 filter，此 test 會紅。dev mode 的扮演限制由後端
    // separation guard 負責，非前端身份解析的責任。
    const owner = MOCK_USERS.find(u => u.dev_mode_only)!;
    window.localStorage.setItem(ACTOR_ID_STORAGE_KEY, owner.id);
    expect(getCurrentActorId()).toBe(owner.id);
  });

  it('localStorage 存未知 id → fallback DEFAULT_USER.id（安全：拒絕不在 fixture 的身份）', () => {
    // 防呆契約：若 localStorage 被竄改或殘留舊版 id，不可放行未知 actor_id
    // 進到後續 dispatch / approve API call，而是退回安全預設 Alice。
    window.localStorage.setItem(
      ACTOR_ID_STORAGE_KEY,
      '00000000-0000-0000-0000-00000000dead',
    );
    expect(getCurrentActorId()).toBe(DEFAULT_USER.id);
  });

  it('localStorage 存空字串 → fallback DEFAULT_USER.id', () => {
    window.localStorage.setItem(ACTOR_ID_STORAGE_KEY, '');
    expect(getCurrentActorId()).toBe(DEFAULT_USER.id);
  });

  it('回傳值恆為已知 fixture 的 id（不洩漏任意外部輸入）', () => {
    const knownIds = new Set(MOCK_USERS.map(u => u.id));
    // 無值情境
    expect(knownIds.has(getCurrentActorId())).toBe(true);
    // 竄改情境
    window.localStorage.setItem(ACTOR_ID_STORAGE_KEY, 'not-a-uuid');
    expect(knownIds.has(getCurrentActorId())).toBe(true);
  });

  it('SSR 環境（typeof window === "undefined"）→ fallback DEFAULT_USER.id', () => {
    // source mockUsers.ts:95 的 SSR guard 在 jsdom 下（window 恆存在）一般不可達；
    // 用 vi.stubGlobal 暫時拔掉 window 真正打到該分支，確保未來 refactor 拿掉 guard 會被抓到。
    vi.stubGlobal('window', undefined);
    try {
      expect(getCurrentActorId()).toBe(DEFAULT_USER.id);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

// 型別層 sanity：鎖住 MockUser 介面「欄位結構」未被悄悄刪改（編譯期檢查，無 runtime 斷言）。
// 若欄位被刪除 / 改名 / 收窄到不相容型別，下列賦值會在 tsc --noEmit 階段紅。
// 注意：此 guard 不偵測 string literal 型別收窄（如 email 由 string 改 `${string}@${string}`）。
const _typeGuard: MockUser = {
  id: '00000000-0000-0000-0000-000000000000',
  name: 'x',
  email: 'x@wmom.dev',
  roles: ['employee'],
  is_active: true,
  dev_mode_only: false,
};
void _typeGuard;
