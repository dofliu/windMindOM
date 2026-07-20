/**
 * sourceMode — 「選擇資料來源」卡片 id → 後端 source mode 的純對應（PR #147 review, DEC-20260720-01）。
 *
 * 抽成純函式以便單元測試（App.tsx 難以整體 render 測，比照 utils/farmHeader）。這個對應是
 * DEC-20260720-01 整條 PR 鏈的關鍵：'scenario' 卡（產生新情境）必須送 'scenario'（simulator 供批次、
 * 不自由跑），若誤還原成 'simulation' 會 silent 重新引入「產生新情境自由跑 + 起 Modbus」的原始 bug。
 * 原本內嵌在 App.tsx 的三元運算子被 mutate 回舊行為時全前端測試無一轉紅——抽出來補測補上這個缺口。
 */

import { type SourceCardId } from '../components/SourceSelectPage';
import { type SourceMode } from '../hooks/useSourceGate';

/**
 * 「選擇資料來源」卡片 id → 後端 `/api/source/select` 的 mode。
 *
 * 用涵蓋全 4 張卡的 lookup table（不用 else 兜底猜測），確保每張卡的 mode 語意明確、
 * 且新增卡片時 TypeScript 會強制補上對應：
 *   - live 卡 → live（實接 OPC/Modbus）
 *   - observe 卡（調閱過去情境）→ view（不啟動任何來源，只讀 storage）
 *   - scenario 卡（產生新情境）→ scenario（simulator 供批次生成、**不自由跑**）
 *   - simulation 卡（即時模擬）→ simulation（自由跑連續產資料）
 */
export function sourceCardToMode(id: SourceCardId): SourceMode {
  const table: Record<SourceCardId, SourceMode> = {
    live: 'live',
    observe: 'view',
    scenario: 'scenario',
    simulation: 'simulation',
  };
  return table[id];
}
