/**
 * farmHeader — App header 「當前風場 / 資料來源」strip 的純邏輯（WMOM-20260718-04）。
 *
 * 抽成純函式以便單元測試（App.tsx 難以整體 render 測）。code review 指出原本內嵌的
 * `dataSourceLabel` 三分支 ternary 把 `MODBUS_TCP`（真實場域連線）誤落到「模擬」分支——
 * 這裡改用涵蓋全部 4 個 `DataSourceType` 的 lookup table 杜絕漏標。
 */

import { DataSourceType } from '../types';

export type HeaderLang = 'en' | 'zh';

/** header strip 顯示的當前風場摘要。 */
export interface ActiveFarmLite {
  name: string;
  turbine_count: number;
}

/**
 * 資料來源標籤（header strip 用）。涵蓋全部 4 個 `DataSourceType`，不用 else 兜底，
 * 確保真實資料源（`OPC_DA` / `MODBUS_TCP`）不會被誤標成「模擬」。
 */
export function dataSourceLabel(dataSource: DataSourceType, lang: HeaderLang): string {
  const table: Record<DataSourceType, string> = {
    [DataSourceType.MOCK]: lang === 'zh' ? 'Demo 資料' : 'Demo data',
    [DataSourceType.SIMULATION]: lang === 'zh' ? '模擬' : 'Simulation',
    [DataSourceType.OPC_DA]: 'OPC-DA',
    [DataSourceType.MODBUS_TCP]: 'Modbus TCP',
  };
  return table[dataSource] ?? (lang === 'zh' ? '模擬' : 'Simulation');
}

/**
 * 從 `/api/farms` 回應（`{ farms, active_farm_id }`）解析出當前風場摘要。
 * 找不到 active farm（空清單 / active_farm_id 對不到 / 欄位缺）時回 `null`（strip 不顯示）。
 */
export function parseActiveFarm(data: unknown): ActiveFarmLite | null {
  if (!data || typeof data !== 'object') return null;
  const d = data as { farms?: unknown; active_farm_id?: unknown };
  if (!Array.isArray(d.farms)) return null;
  const active = (d.farms as Array<Record<string, unknown>>).find(
    f => f && f.farm_id === d.active_farm_id,
  );
  if (!active) return null;
  const name = typeof active.name === 'string' ? active.name : '';
  const turbine_count = typeof active.turbine_count === 'number' ? active.turbine_count : 0;
  if (!name) return null;
  return { name, turbine_count };
}
