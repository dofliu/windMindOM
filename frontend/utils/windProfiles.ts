/**
 * windProfiles — 風況 profile 的顯示標籤（WMOM-20260719-02）。
 *
 * 抽成共用檔，讓「情境設定」（ScenarioPage）與「情境調閱」（ScenarioDetail）共用同一份
 * 中英對照，避免 ScenarioDetail 顯示原始後端代碼（如 `storm`）而與頁面其他地方不一致，
 * 也避免兩元件互相 import 造成循環。
 */

export interface WindProfileOption {
  value: string;
  en: string;
  zh: string;
}

export const WIND_PROFILES: WindProfileOption[] = [
  { value: 'calm', en: 'Calm (~4 m/s)', zh: '微風（~4 m/s）' },
  { value: 'moderate', en: 'Moderate (~10 m/s)', zh: '中風（~10 m/s）' },
  { value: 'rated', en: 'Rated (~13 m/s)', zh: '額定風（~13 m/s）' },
  { value: 'strong', en: 'Strong (~18 m/s)', zh: '強風（~18 m/s）' },
  { value: 'storm', en: 'Storm (>25 m/s, cut-out)', zh: '暴風（>25 m/s 停機）' },
  { value: 'gusty', en: 'Gusty', zh: '陣風' },
  { value: 'ramp_up', en: 'Ramp up', zh: '風速漸增' },
  { value: 'ramp_down', en: 'Ramp down', zh: '風速漸減' },
];

/** 取風況的顯示標籤；查無對照時 fallback 原始值（不失真）。 */
export function windProfileLabel(value: string | undefined | null, lang: string): string {
  if (!value) return '';
  const p = WIND_PROFILES.find(x => x.value === value);
  return p ? (lang === 'zh' ? p.zh : p.en) : value;
}
