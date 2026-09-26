/**
 * ScenarioMountContext — 情境掛載（PR C Phase 1，DEC-20260926-01 / WMOM-20260926-03）。
 *
 * 讓使用者從已保存情境（ScenarioDetail）「以此情境瀏覽總覽/機組細節」，把 FarmOverview/
 * TurbineDetail 暫時改吃該情境的凍結快照（`GET /api/scenarios/{id}/turbines`），而非即時
 * live/simulation 資料。與 DataBroker 的單一 active source 狀態機正交——不呼叫
 * `/api/source/select`，不影響目前是否有 live/simulation 在跑（見 decision log
 * `DEC-20260926-01`）。
 *
 * 離開機制：`App.tsx::handleNavSelect` 導覽到非 overview/turbine 頁面時呼叫 `unmount()`
 * 清空——這是正確性/資訊安全要求（避免使用者切頁後仍背景殘留掛載中的凍結情境資料、混淆
 * 即時/回放），不是單純可省略的程式碼手法（WMOM-20260926-03 issue 明確澄清）。
 *
 * 資料抓取（`useScenarioMountData`）內建在本 Provider 裡（而非各自在 App.tsx／
 * `FarmOverview`/`TurbineDetail` 分開呼叫）：單一 fetch 來源，`turbines`/`loading`/`error`
 * 隨 context 一起分發——`FarmOverview`/`TurbineDetail` 才能直接讀 `error`/`loading` 在
 * banner 顯示「情境已被刪除/載入失敗」，不需要 App.tsx 額外 prop drilling（code review
 * should-fix：原本 `useScenarioMountData` 的 `error` 只在 App.tsx 算出來，從未浮現在畫面上，
 * 情境被刪除/網路失敗時 banner 仍自信顯示「情境檢視中」卻是空資料）。
 */

import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { useScenarioMountData } from '../hooks/useScenarioMountData';
import { type TurbineData } from '../types';

export interface MountedScenario {
  id: number;
  name: string;
}

interface ScenarioMountContextValue {
  /** 目前掛載的情境；`null` = 未掛載（FarmOverview/TurbineDetail 走一般即時/模擬資料）。 */
  mounted: MountedScenario | null;
  mount: (scenario: MountedScenario) => void;
  unmount: () => void;
  /** 掛載情境的機組快照（未掛載時為空陣列）——`App.tsx` 用它組 `effectiveTurbines`。 */
  turbines: TurbineData[];
  /** 掛載情境的 fetch 是否進行中。 */
  loading: boolean;
  /** 掛載情境的 fetch 失敗訊息（含情境已被刪除的 404）；成功或未掛載時為 `null`。 */
  error: string | null;
}

const ScenarioMountContext = createContext<ScenarioMountContextValue | null>(null);

interface ProviderProps {
  children: React.ReactNode;
  /**
   * 測試用 seed——讓測試能在「已掛載」狀態下完成初始 render，避免用
   * `useEffect(() => mount(...))` 在子元件掛載後才補呼叫：React 的 effect 執行順序是
   * 子元件先於父元件，若情境掛載改用 post-mount effect 觸發，`FarmOverview`/
   * `TurbineDetail` 內部依賴 `mounted` 決定是否發起 fetch 的 effect 會在初次 render
   * （`mounted` 仍是初始值 `null`）就先跑一次，等父層的 `mount()` effect 才補上第二次
   * render——這一次「先污染」正是本欄位要避免的競態。production 呼叫端（App.tsx）
   * 不傳，維持預設 `null`。
   */
  initialMounted?: MountedScenario | null;
}

export const ScenarioMountProvider: React.FC<ProviderProps> = ({
  children,
  initialMounted = null,
}) => {
  const [mounted, setMounted] = useState<MountedScenario | null>(initialMounted);
  const { turbines, loading, error } = useScenarioMountData(mounted?.id ?? null);

  const mount = useCallback((scenario: MountedScenario) => setMounted(scenario), []);
  const unmount = useCallback(() => setMounted(null), []);

  const value = useMemo<ScenarioMountContextValue>(
    () => ({ mounted, mount, unmount, turbines, loading, error }),
    [mounted, mount, unmount, turbines, loading, error],
  );

  return (
    <ScenarioMountContext.Provider value={value}>{children}</ScenarioMountContext.Provider>
  );
};

/**
 * 取情境掛載 state。必須在 `<ScenarioMountProvider>` 內呼叫（比照 `useAuth`/`useTheme`
 * fail-fast 慣例）。
 *
 * @throws Error 若沒有 `ScenarioMountProvider` 包裹。
 */
export function useScenarioMount(): ScenarioMountContextValue {
  const ctx = useContext(ScenarioMountContext);
  if (!ctx) {
    throw new Error('useScenarioMount must be used within <ScenarioMountProvider>');
  }
  return ctx;
}
