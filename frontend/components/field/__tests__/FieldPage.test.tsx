/**
 * FieldPage component render 測試（WMOM-20260604-01，EPIC-M5 M5-5 測試覆蓋）。
 *
 * `/field/` 現場知識查詢頁是 PMF killer 頁，先前只有 useKnowledge hook 的單元測試，
 * 元件層（render / 模式切換 / 結果顯示 / 互動 disabled）零覆蓋。本檔補上第一批
 * component render 測試，守住 FieldPage 的 UX 契約：
 *
 *   - 預設渲染：標題 + 模式切換 + 關鍵字查詢表單
 *   - info badge 三態：baseline（amber）/ vector（ok）/ error（warn）
 *   - 模式切換：關鍵字查詢 ⇄ 警報檢索 切換對應表單
 *   - 結果區：query 有結果 → 渲染 chunk 卡（相關度 / 命中原因 / 來源）；空結果 → 查無提示
 *   - 警報結果：警報摘要 pill +「系統據此檢索」query 透明標示
 *   - 錯誤 / loading 回饋
 *   - 查詢按鈕 disabled 行為（無輸入 disabled、輸入後 enabled）
 *
 * 把整個 useKnowledge hook 換成可控 mock（零真連線、零真 useEffect）；
 * 元件用 ThemeProvider 包裹（useTheme 無 Provider 會 throw）。
 */

import { describe, it, expect, beforeEach, afterEach, vi, type Mock } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import React from 'react';
import FieldPage from '../FieldPage';
import { ThemeProvider } from '../../../theme/ThemeProvider';
import { useKnowledge } from '../../../hooks/useKnowledge';
import type {
  AlertRagResult,
  KnowledgeInfoResponse,
  KnowledgeQueryResponse,
  RetrievedChunk,
} from '../../../services/knowledgeService';

vi.mock('../../../hooks/useKnowledge');

const mockedUseKnowledge = useKnowledge as unknown as Mock;

// ─── fixtures（型別嚴格對齊 knowledgeService）───────────────────────────────

const INFO_BASELINE: KnowledgeInfoResponse = {
  strategy_name: 'baseline',
  oem: 'Bachmann',
  model: 'Z72',
  retriever: 'baseline_keyword',
  is_baseline: true,
  top_k: 5,
};

const INFO_VECTOR: KnowledgeInfoResponse = {
  ...INFO_BASELINE,
  retriever: 'chroma_z72',
  is_baseline: false,
};

function chunk(id: string, text: string, reason: string, score: number): RetrievedChunk {
  return {
    chunk: {
      id,
      document_source: 'Z72UserManual.pdf',
      section: '§5.3',
      page: 42,
      chunk_text: text,
      oem: 'Bachmann',
      model: 'Z72',
      alarm_codes: [21],
      keywords: ['converter'],
      embedding_vector_id: null,
    },
    score,
    match_reason: reason,
  };
}

const QUERY_RESULT: KnowledgeQueryResponse = {
  items: [chunk('c1', '變頻器冷卻水溫過高處置：檢查冷卻泵。', '關鍵字「變頻器」命中', 0.82)],
  retriever: 'baseline_keyword',
  is_baseline: true,
  total: 1,
};

const QUERY_EMPTY: KnowledgeQueryResponse = {
  items: [],
  retriever: 'baseline_keyword',
  is_baseline: true,
  total: 0,
};

const ALERT_RESULT: AlertRagResult = {
  alert: {
    alarm_code: 21,
    alarm_level: 'T1',
    turbine_id: 'WTG-07',
    oem: 'Bachmann',
    model: 'Z72',
    scenario_id: null,
    abnormal_tags: ['converter_temp'],
    description: null,
    severity: null,
    timestamp: '2026-06-04T10:00:00Z',
  },
  query: { text: '變頻器跳機 converter_temp', alarm_codes: [21] },
  chunks: [chunk('a1', '變頻器跳機 SOP：先確認 DC link 電壓。', '告警碼 21 命中', 0.91)],
  strategy_name: 'baseline',
  retriever: 'baseline_keyword',
  is_baseline: true,
};

/** useKnowledge 回傳的三條流預設值（loading=false / error=null / data=null）。 */
type KnowledgeReturn = ReturnType<typeof useKnowledge>;

function makeHook(overrides: Partial<KnowledgeReturn> = {}): KnowledgeReturn {
  // 八個欄位全列（含 loadInfo），不用 `as` 強轉——讓 tsc 守住與 hook 真實 signature 對齊；
  // 漏欄位會編譯失敗而非靜默假綠。
  return {
    info: { loading: false, error: null, data: INFO_BASELINE },
    search: { loading: false, error: null, data: null },
    alert: { loading: false, error: null, data: null },
    loadInfo: vi.fn(),
    runSearch: vi.fn(),
    clearSearch: vi.fn(),
    runAlert: vi.fn(),
    clearAlert: vi.fn(),
    ...overrides,
  };
}

function renderField(overrides: Partial<KnowledgeReturn> = {}): KnowledgeReturn {
  const hook = makeHook(overrides);
  mockedUseKnowledge.mockReturnValue(hook);
  render(
    <ThemeProvider>
      <FieldPage lang="zh" />
    </ThemeProvider>,
  );
  return hook;
}

describe('FieldPage 現場知識查詢頁', () => {
  beforeEach(() => {
    // mockReset 清 call history + 移除所有 mockReturnValue；每個 test 都透過
    // renderField() 重新設定回傳值，故 reset 比 clear 安全（不殘留上一 test 的 state）。
    mockedUseKnowledge.mockReset();
  });

  // globals:false 時 RTL 不會自動 cleanup，需手動清 DOM 避免跨測試 render 累積
  // （否則同名元素重複 → getByRole/getByText 命中多個而失敗）。
  afterEach(() => {
    cleanup();
  });

  it('預設渲染標題、模式切換、關鍵字查詢表單', () => {
    renderField();
    expect(screen.getByText('現場知識查詢')).toBeInTheDocument();
    // 模式切換兩顆按鈕
    expect(screen.getByRole('button', { name: '關鍵字查詢' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '警報檢索' })).toBeInTheDocument();
    // 預設在 query 模式 → 關鍵字 input 在場、機組代號（alert 專屬）不在
    expect(screen.getByLabelText('關鍵字')).toBeInTheDocument();
    expect(screen.queryByLabelText('機組代號')).not.toBeInTheDocument();
  });

  it('預設模式按鈕 aria-pressed 正確（query active / alert inactive）', () => {
    renderField();
    expect(screen.getByRole('button', { name: '關鍵字查詢' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: '警報檢索' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('info badge：baseline 模式顯示「示範檢索（baseline）」', () => {
    renderField({ info: { loading: false, error: null, data: INFO_BASELINE } });
    expect(screen.getByText('示範檢索（baseline）')).toBeInTheDocument();
  });

  it('info badge：向量檢索模式顯示 retriever 名稱', () => {
    renderField({ info: { loading: false, error: null, data: INFO_VECTOR } });
    expect(screen.getByText(/向量檢索 · chroma_z72/)).toBeInTheDocument();
  });

  it('info badge：/info 失敗顯示「RAG 服務異常」', () => {
    renderField({ info: { loading: false, error: '503', data: null } });
    expect(screen.getByText('RAG 服務異常')).toBeInTheDocument();
  });

  it('info badge：loading 中（error/data 皆 null）不顯示任何 badge', () => {
    renderField({ info: { loading: true, error: null, data: null } });
    expect(screen.queryByText('示範檢索（baseline）')).not.toBeInTheDocument();
    expect(screen.queryByText('RAG 服務異常')).not.toBeInTheDocument();
    expect(screen.queryByText(/向量檢索/)).not.toBeInTheDocument();
  });

  it('切換到警報檢索模式渲染 alert 表單（機組代號出現、關鍵字消失）', () => {
    renderField();
    fireEvent.click(screen.getByRole('button', { name: '警報檢索' }));
    expect(screen.getByLabelText('機組代號')).toBeInTheDocument();
    expect(screen.getByLabelText('告警等級')).toBeInTheDocument();
    expect(screen.queryByLabelText('關鍵字')).not.toBeInTheDocument();
  });

  it('query 模式有結果時渲染 chunk 卡（相關度 / 正文 / 命中原因 / 來源）', () => {
    renderField({ search: { loading: false, error: null, data: QUERY_RESULT } });
    expect(screen.getByText('找到 1 段相關處置')).toBeInTheDocument();
    expect(screen.getByText('變頻器冷卻水溫過高處置：檢查冷卻泵。')).toBeInTheDocument();
    expect(screen.getByText(/關鍵字「變頻器」命中/)).toBeInTheDocument();
    expect(screen.getByText('相關度 82%')).toBeInTheDocument();
    // 來源行：來源檔 · §章節 · p.頁碼
    expect(screen.getByText(/Z72UserManual\.pdf · §5\.3 · p\.42/)).toBeInTheDocument();
  });

  it('query 模式空結果顯示查無提示', () => {
    renderField({ search: { loading: false, error: null, data: QUERY_EMPTY } });
    expect(
      screen.getByText('查無對應手冊段落，請換個關鍵字或告警碼。'),
    ).toBeInTheDocument();
  });

  it('query 模式 error 顯示查詢失敗訊息（剝技術前綴）', () => {
    renderField({
      search: { loading: false, error: 'POST /api/knowledge/query failed: 後端忙碌', data: null },
    });
    // stripErrorPrefix 後只剩 backend 繁中 detail（與「查詢失敗：」前綴同 div 內兩個 text node，用 regex 匹配）
    expect(screen.getByText(/後端忙碌/)).toBeInTheDocument();
    expect(screen.queryByText(/failed:/)).not.toBeInTheDocument();
  });

  it('query 模式 loading 顯示「檢索中…」回饋', () => {
    renderField({ search: { loading: true, error: null, data: null } });
    expect(screen.getByText('檢索中…')).toBeInTheDocument();
  });

  it('警報模式有結果時渲染警報摘要 +「系統據此檢索」query + chunk', () => {
    renderField({ alert: { loading: false, error: null, data: ALERT_RESULT } });
    // 切換前：預設 query 模式下，即使 alert.data 已存在也不該渲染（守住模式互斥契約）。
    expect(screen.queryByText(/WTG-07/)).not.toBeInTheDocument();
    // 切到 alert 模式才看得到結果摘要區
    fireEvent.click(screen.getByRole('button', { name: '警報檢索' }));
    // 「告警碼 21」會出現兩處：警報摘要 pill + chunk 的 alarm_codes pill。
    expect(screen.getAllByText('告警碼 21').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('WTG-07')).toBeInTheDocument();
    expect(screen.getByText(/系統據此檢索：/)).toBeInTheDocument();
    expect(screen.getByText('變頻器跳機 SOP：先確認 DC link 電壓。')).toBeInTheDocument();
  });

  it('查詢按鈕：無輸入時 disabled、輸入關鍵字後 enabled', () => {
    renderField();
    const searchBtn = screen.getByRole('button', { name: '查詢手冊' });
    expect(searchBtn).toBeDisabled();
    fireEvent.change(screen.getByLabelText('關鍵字'), {
      target: { value: '變頻器' },
    });
    expect(searchBtn).toBeEnabled();
  });

  it('查詢按鈕點擊呼叫 runSearch 帶 trim 後文字與告警碼', () => {
    const hook = renderField();
    fireEvent.change(screen.getByLabelText('關鍵字'), { target: { value: '  變頻器  ' } });
    fireEvent.change(screen.getByLabelText('告警碼'), { target: { value: '21' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢手冊' }));
    expect(hook.runSearch).toHaveBeenCalledWith({ text: '變頻器', alarm_codes: [21] });
  });

  it('查詢（無告警碼）：runSearch 帶空陣列 alarm_codes 而非 undefined', () => {
    const hook = renderField();
    fireEvent.change(screen.getByLabelText('關鍵字'), { target: { value: '變頻器' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢手冊' }));
    // handleSearch 在無告警碼時固定送 []（對齊 RetrievalQuery.alarm_codes: number[]）。
    expect(hook.runSearch).toHaveBeenCalledWith({ text: '變頻器', alarm_codes: [] });
  });

  it('常用告警碼 chip 一鍵帶入後查詢按鈕 enabled', () => {
    renderField();
    // chip aria-label = 「帶入告警碼 21」
    fireEvent.click(screen.getByRole('button', { name: '帶入告警碼 21' }));
    expect(screen.getByRole('button', { name: '查詢手冊' })).toBeEnabled();
  });

  it('警報模式 runAlert：需告警碼 + 機組代號才 enabled，點擊帶正確 payload', () => {
    const hook = renderField();
    fireEvent.click(screen.getByRole('button', { name: '警報檢索' }));
    const runBtn = screen.getByRole('button', { name: '檢索處置' });
    expect(runBtn).toBeDisabled();
    fireEvent.change(screen.getByLabelText('告警碼'), { target: { value: '21' } });
    fireEvent.change(screen.getByLabelText('機組代號'), { target: { value: 'WTG-07' } });
    expect(runBtn).toBeEnabled();
    fireEvent.click(runBtn);
    expect(hook.runAlert).toHaveBeenCalledTimes(1);
    const payload = (hook.runAlert as Mock).mock.calls[0][0];
    expect(payload).toMatchObject({
      alarm_code: 21,
      alarm_level: 'A', // DEFAULT_ALARM_LEVEL
      turbine_id: 'WTG-07',
    });
    // timestamp 永遠帶 Z（UTC，避免 422 時區陷阱）
    expect(payload.timestamp).toMatch(/Z$/);
  });

  it('清除按鈕呼叫 clearSearch', () => {
    const hook = renderField();
    // 依賴 query / alert 兩模式互斥渲染（同時只有一個「清除」在 DOM）；
    // 若日後改成保留 DOM 的 tab 實作，需改用 within() 限縮到 query 區塊。
    fireEvent.click(screen.getByRole('button', { name: '清除' }));
    expect(hook.clearSearch).toHaveBeenCalledTimes(1);
  });

  it('多段結果渲染對應數量的卡片', () => {
    const multi: KnowledgeQueryResponse = {
      items: [
        chunk('m1', '處置一', '原因一', 0.9),
        chunk('m2', '處置二', '原因二', 0.5),
        chunk('m3', '處置三', '原因三', 0.2),
      ],
      retriever: 'baseline_keyword',
      is_baseline: true,
      total: 3,
    };
    renderField({ search: { loading: false, error: null, data: multi } });
    expect(screen.getByText('找到 3 段相關處置')).toBeInTheDocument();
    expect(screen.getByText('處置一')).toBeInTheDocument();
    expect(screen.getByText('處置三')).toBeInTheDocument();
    // 三張卡片各自的命中原因都在
    const reasons = ['原因一', '原因二', '原因三'];
    reasons.forEach(r => expect(screen.getByText(new RegExp(r))).toBeInTheDocument());
    // 相關度 pill 高低兩端都渲染
    expect(screen.getByText('相關度 90%')).toBeInTheDocument();
    expect(screen.getByText('相關度 20%')).toBeInTheDocument();
  });
});
