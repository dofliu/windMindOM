/**
 * FieldPage — 現場工程師 mobile-first 知識查詢頁（WMOM-20260603-03/-04，EPIC-M5 M5-5）。
 *
 * PMF 關鍵頁：警報跳出 → 30 秒內現場工程師手機看到「手冊對應段落 + 可解釋命中原因」。
 * Demo killer：「這比 LINE 群組問師傅快嗎？」
 *
 * 兩種模式（mobile-first 單欄、窄寬度、大觸控目標）：
 *   - 關鍵字查詢（Part A）：手動打關鍵字 / 告警碼查手冊（POST /api/knowledge/query）
 *   - 警報檢索（Part B）：模擬 SCADA 警報事件 → 後端自動構造 query 檢索 top-k 處置段落
 *     （POST /api/knowledge/alert）；真整合時由 monitoring 警報直接帶入，此處提供表單模擬。
 *
 * 共用版面：
 *   - PageHeader：現場知識查詢 + RAG 來源 / baseline badge
 *   - 模式切換（segmented）：關鍵字查詢 / 警報檢索
 *   - 結果：RetrievedChunk 卡片（相關度 % + 繁中命中原因 + 文件來源 + 段落正文）
 *
 * 資料流走 useKnowledge（GET /info 一次 + POST /query 手動 + POST /alert 警報）；
 * 顏色全走 theme，不寫 hex。
 */

import React, { useMemo, useState } from 'react';
import { useKnowledge } from '../../hooks/useKnowledge';
import type { Lang } from '../../hooks/useI18n';
import type {
  AlarmLevel,
  AlertEvent,
  AlertRagResult,
  RetrievalQuery,
  RetrievedChunk,
} from '../../services/knowledgeService';
import { useTheme } from '../../theme/ThemeProvider';
import { Card, Btn, PageHeader, StatusPill, Field, Input, Select } from '../ui';

/** 頁面模式：手動關鍵字查詢 vs 警報事件檢索。 */
type FieldMode = 'query' | 'alert';

/**
 * 常用 Z72 告警碼 — 現場一鍵帶入。
 *
 * ⚠️ placeholder：以下碼為 baseline 示範值，**待用 `docs/__Z72UserManual.pdf` +
 * `docs/1040610-Z72_PLC_OPC_TAG_1040510.xlsx` 核實**（M5-4 灌真手冊 + 警報 csv 後
 * 應以實際資料取代，避免一鍵帶入後查無結果造成 false confidence）。
 */
const COMMON_ALARM_CODES: Array<{ code: number; labelZh: string; labelEn: string }> = [
  { code: 21, labelZh: '變頻器跳機', labelEn: 'Converter trip' },
  { code: 31, labelZh: '齒輪箱高溫', labelEn: 'Gearbox over-temp' },
  { code: 42, labelZh: '偏航異常', labelEn: 'Yaw fault' },
  { code: 53, labelZh: '變槳故障', labelEn: 'Pitch fault' },
];

/** 告警等級選項（對齊 schemas.AlarmLevel：A 警示 / T1 一級跳機 / T2 二級跳機）。 */
const ALARM_LEVELS: Array<{ value: AlarmLevel; labelZh: string; labelEn: string }> = [
  { value: 'A', labelZh: 'A · 警示', labelEn: 'A · Alert' },
  { value: 'T1', labelZh: 'T1 · 一級跳機', labelEn: 'T1 · Trip-1' },
  { value: 'T2', labelZh: 'T2 · 二級跳機', labelEn: 'T2 · Trip-2' },
];

/** 等級預設值 = backend AlertEvent.alarm_level 的 default（'A' 警示，最中性）；
 * 對齊 schema 預設語意，避免使用者未選時前端擅自帶入較嚴重的 T1（一級跳機）。 */
const DEFAULT_ALARM_LEVEL: AlarmLevel = 'A';

/** 合法告警等級集合 — Select onChange 的 narrow guard（防非法值強轉送進 backend）。 */
const VALID_ALARM_LEVELS = new Set<AlarmLevel>(['A', 'T1', 'T2']);

interface FieldPageProps {
  lang: Lang;
}

/** 相關度 0..1 → 百分比字串。clamp 0..1 防 M5-2 ChromaDB distance 轉換溢出邊界。 */
const fmtScore = (score: number): string =>
  `${Math.round(Math.min(Math.max(score, 0), 1) * 100)}%`;

/** 依相關度給 pill tone（高=ok、中=amber、低=muted）。 */
function scoreTone(score: number): 'ok' | 'amber' | 'muted' {
  if (score >= 0.6) return 'ok';
  if (score >= 0.3) return 'amber';
  return 'muted';
}

/**
 * 剝掉 service 層 `GET/POST /api/... failed:` 技術前綴，只留 backend 繁中 detail
 * （readError 已抽好）；給現場工程師看的錯誤不該帶 HTTP method/path 雜訊。
 */
function stripErrorPrefix(msg: string | null): string | null {
  return msg?.replace(/^(GET|POST)\s+\S+\s+failed:\s*/, '') ?? null;
}

/** 正整數解析：空 / 非數字 / 非正整數 → null（避免空查詢或負碼打 backend）。 */
function parsePositiveInt(raw: string): number | null {
  const n = Number(raw.trim());
  return Number.isInteger(n) && n > 0 ? n : null;
}

const ResultCard: React.FC<{ item: RetrievedChunk; lang: Lang }> = ({ item, lang }) => {
  const { C } = useTheme();
  const { chunk, score, match_reason } = item;
  const zh = lang === 'zh';

  // 文件來源行：來源檔 · §章節 · p.頁碼（缺的略過）。
  const sourceParts: string[] = [chunk.document_source];
  if (chunk.section) sourceParts.push(chunk.section);
  if (chunk.page != null) sourceParts.push(`p.${chunk.page}`);

  return (
    <Card style={{ marginBottom: 12 }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 8,
          marginBottom: 8,
        }}
      >
        <StatusPill tone={scoreTone(score)} size="md">
          {zh ? '相關度' : 'Match'} {fmtScore(score)}
        </StatusPill>
        <span style={{ fontSize: 11, color: C.faint, textAlign: 'right', minWidth: 0 }}>
          {sourceParts.join(' · ')}
        </span>
      </div>

      <div style={{ fontSize: 15, lineHeight: 1.6, color: C.text, marginBottom: 10 }}>
        {chunk.chunk_text}
      </div>

      <div
        style={{
          fontSize: 12,
          color: C.sub,
          background: C.panelMuted,
          borderRadius: 8,
          padding: '6px 10px',
        }}
      >
        <span style={{ fontWeight: 600 }}>{zh ? '命中原因：' : 'Why: '}</span>
        {match_reason}
      </div>

      {chunk.alarm_codes.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 10 }}>
          {/* dedupe：backend schema 不保證 alarm_codes 唯一，去重避免 React duplicate key。 */}
          {[...new Set(chunk.alarm_codes)].map(code => (
            <StatusPill key={code} tone="info">
              {zh ? '告警碼' : 'Alarm'} {code}
            </StatusPill>
          ))}
        </div>
      )}
    </Card>
  );
};

/**
 * 結果區共用：loading / error / 空結果 / chunk 列表（query 與 alert 兩模式共用）。
 * `hasResult` = 「目前有結果可顯示嗎」（data != null），用來區分「尚未查」與「查了但空」。
 */
const ResultList: React.FC<{
  chunks: RetrievedChunk[];
  loading: boolean;
  error: string | null;
  hasResult: boolean;
  lang: Lang;
}> = ({ chunks, loading, error, hasResult, lang }) => {
  const { C } = useTheme();
  const zh = lang === 'zh';
  const errorMsg = stripErrorPrefix(error);

  return (
    <>
      {errorMsg && (
        <Card tone="warn" style={{ marginBottom: 12 }}>
          <div style={{ color: C.warn, fontSize: 13 }}>
            {zh ? '查詢失敗：' : 'Search failed: '}
            {errorMsg}
          </div>
        </Card>
      )}

      {/* loading 回饋：弱訊號（現場 4G）下結果區不該靜止，給 busy 提示避免反覆點擊。 */}
      {loading && (
        <div style={{ color: C.sub, textAlign: 'center', padding: '16px 0', fontSize: 13 }}>
          {zh ? '檢索中…' : 'Retrieving…'}
        </div>
      )}

      {!loading && !error && hasResult && chunks.length === 0 && (
        <Card tone="muted">
          <div style={{ color: C.sub, fontSize: 14, textAlign: 'center', padding: '12px 0' }}>
            {zh
              ? '查無對應手冊段落，請換個關鍵字或告警碼。'
              : 'No matching manual section. Try another keyword or alarm code.'}
          </div>
        </Card>
      )}

      {chunks.length > 0 && (
        <>
          <div style={{ fontSize: 12, color: C.sub, marginBottom: 10 }}>
            {zh
              ? `找到 ${chunks.length} 段相關處置`
              : `${chunks.length} matching section(s)`}
          </div>
          {chunks.map(item => (
            <ResultCard key={item.chunk.id} item={item} lang={lang} />
          ))}
        </>
      )}
    </>
  );
};

/** 模式切換 segmented control（兩顆 Btn：active=primary、inactive=ghost）。 */
const ModeToggle: React.FC<{
  mode: FieldMode;
  onChange: (m: FieldMode) => void;
  lang: Lang;
}> = ({ mode, onChange, lang }) => {
  const zh = lang === 'zh';
  const tabs: Array<{ id: FieldMode; labelZh: string; labelEn: string }> = [
    { id: 'query', labelZh: '關鍵字查詢', labelEn: 'Keyword' },
    { id: 'alert', labelZh: '警報檢索', labelEn: 'Alert' },
  ];
  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
      {tabs.map(tab => (
        <Btn
          key={tab.id}
          variant={mode === tab.id ? 'primary' : 'ghost'}
          fullWidth
          ariaLabel={zh ? tab.labelZh : tab.labelEn}
          ariaPressed={mode === tab.id}
          onClick={() => onChange(tab.id)}
        >
          {zh ? tab.labelZh : tab.labelEn}
        </Btn>
      ))}
    </div>
  );
};

/** 關鍵字查詢模式（Part A）。 */
const QueryMode: React.FC<{
  lang: Lang;
  loading: boolean;
  error: string | null;
  chunks: RetrievedChunk[];
  hasResult: boolean;
  onSearch: (q: RetrievalQuery) => void;
  onClear: () => void;
}> = ({ lang, loading, error, chunks, hasResult, onSearch, onClear }) => {
  const zh = lang === 'zh';
  const [text, setText] = useState('');
  const [alarmCode, setAlarmCode] = useState('');

  const parsedAlarmCode = useMemo<number | null>(
    () => parsePositiveInt(alarmCode),
    [alarmCode],
  );
  const canSearch = text.trim().length > 0 || parsedAlarmCode != null;

  const handleSearch = (): void => {
    if (!canSearch) return;
    onSearch({
      text: text.trim(),
      alarm_codes: parsedAlarmCode != null ? [parsedAlarmCode] : [],
    });
  };

  const handleClear = (): void => {
    setText('');
    setAlarmCode('');
    onClear();
  };

  return (
    <>
      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Field label={zh ? '關鍵字 / 警報描述' : 'Keyword / alarm description'} fullWidth>
            <Input
              value={text}
              onChange={setText}
              placeholder={zh ? '例：變頻器冷卻水溫過高' : 'e.g. converter cooling over-temp'}
              ariaLabel={zh ? '關鍵字' : 'Keyword'}
              fullWidth
            />
          </Field>

          <Field label={zh ? '告警碼（可選）' : 'Alarm code (optional)'} fullWidth>
            <Input
              value={alarmCode}
              onChange={setAlarmCode}
              type="number"
              min={1}
              placeholder={zh ? '例：21' : 'e.g. 21'}
              ariaLabel={zh ? '告警碼' : 'Alarm code'}
              fullWidth
            />
          </Field>

          {/* 常用告警碼 chips（一鍵帶入告警碼 + 描述）。 */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {COMMON_ALARM_CODES.map(a => (
              <Btn
                key={a.code}
                size="sm"
                variant="ghost"
                ariaLabel={`${zh ? '帶入告警碼' : 'Use alarm'} ${a.code}`}
                onClick={() => {
                  setAlarmCode(String(a.code));
                  setText(zh ? a.labelZh : a.labelEn);
                }}
              >
                {a.code} · {zh ? a.labelZh : a.labelEn}
              </Btn>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <Btn
              variant="primary"
              fullWidth
              loading={loading}
              disabled={!canSearch}
              ariaLabel={zh ? '查詢手冊' : 'Search manual'}
              onClick={handleSearch}
            >
              {loading ? (zh ? '查詢中…' : 'Searching…') : zh ? '查詢手冊' : 'Search'}
            </Btn>
            <Btn variant="secondary" ariaLabel={zh ? '清除' : 'Clear'} onClick={handleClear}>
              {zh ? '清除' : 'Clear'}
            </Btn>
          </div>
        </div>
      </Card>

      <ResultList
        chunks={chunks}
        loading={loading}
        error={error}
        hasResult={hasResult}
        lang={lang}
      />
    </>
  );
};

/** 警報檢索模式（Part B，killer feature）。 */
const AlertMode: React.FC<{
  lang: Lang;
  loading: boolean;
  error: string | null;
  result: AlertRagResult | null;
  onRun: (event: AlertEvent) => void;
  onClear: () => void;
}> = ({ lang, loading, error, result, onRun, onClear }) => {
  const { C } = useTheme();
  const zh = lang === 'zh';
  const [alarmCode, setAlarmCode] = useState('');
  const [alarmLevel, setAlarmLevel] = useState<AlarmLevel>(DEFAULT_ALARM_LEVEL);
  const [turbineId, setTurbineId] = useState('');
  const [tagsRaw, setTagsRaw] = useState('');

  const parsedAlarmCode = useMemo<number | null>(
    () => parsePositiveInt(alarmCode),
    [alarmCode],
  );
  // 異常 tag：逗號 / 全形逗號 / 空白分隔 → 去空白去重。
  const abnormalTags = useMemo<string[]>(() => {
    const parts = tagsRaw
      .split(/[,，\s]+/)
      .map(s => s.trim())
      .filter(s => s.length > 0);
    return [...new Set(parts)];
  }, [tagsRaw]);

  // 警報檢索至少要有告警碼（backend AlertEvent.alarm_code 為必填 ge=1）+ 機組代號。
  const canRun = parsedAlarmCode != null && turbineId.trim().length > 0;

  const handleRun = (): void => {
    if (parsedAlarmCode == null || turbineId.trim().length === 0) return;
    onRun({
      alarm_code: parsedAlarmCode,
      alarm_level: alarmLevel,
      turbine_id: turbineId.trim(),
      abnormal_tags: abnormalTags,
      // 永遠帶 Z（UTC）避免 naive datetime 被 schema validator 擋成 422（CLAUDE.md §B）。
      timestamp: new Date().toISOString(),
    });
  };

  const handleClear = (): void => {
    setAlarmCode('');
    setAlarmLevel(DEFAULT_ALARM_LEVEL); // 清除須恢復初始等級，否則殘留舊值下次送查帶入 stale。
    setTurbineId('');
    setTagsRaw('');
    onClear();
  };

  return (
    <>
      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ fontSize: 12, color: C.faint }}>
            {zh
              ? '模擬 SCADA 警報事件 → 系統自動查手冊處置（真整合時由監控警報直接帶入）。'
              : 'Simulate a SCADA alert → auto-retrieve manual sections (wired from monitoring in production).'}
          </div>

          <div style={{ display: 'flex', gap: 12 }}>
            <Field label={zh ? '告警碼' : 'Alarm code'} fullWidth>
              <Input
                value={alarmCode}
                onChange={setAlarmCode}
                type="number"
                min={1}
                placeholder={zh ? '例：21' : 'e.g. 21'}
                ariaLabel={zh ? '告警碼' : 'Alarm code'}
                fullWidth
              />
            </Field>
            <Field label={zh ? '告警等級' : 'Level'} fullWidth>
              <Select
                value={alarmLevel}
                onChange={v => {
                  // narrow guard：只接受合法等級，防 ALARM_LEVELS 之外的值強轉送進 backend。
                  if (VALID_ALARM_LEVELS.has(v as AlarmLevel)) setAlarmLevel(v as AlarmLevel);
                }}
                ariaLabel={zh ? '告警等級' : 'Alarm level'}
                fullWidth
                options={ALARM_LEVELS.map(l => ({
                  value: l.value,
                  label: zh ? l.labelZh : l.labelEn,
                }))}
              />
            </Field>
          </div>

          <Field label={zh ? '機組代號' : 'Turbine ID'} fullWidth>
            <Input
              value={turbineId}
              onChange={setTurbineId}
              placeholder={zh ? '例：WTG-07' : 'e.g. WTG-07'}
              ariaLabel={zh ? '機組代號' : 'Turbine ID'}
              fullWidth
            />
          </Field>

          <Field label={zh ? '異常標籤（可選，逗號分隔）' : 'Abnormal tags (optional, comma-separated)'} fullWidth>
            <Input
              value={tagsRaw}
              onChange={setTagsRaw}
              placeholder={zh ? '例：converter_temp, cooling' : 'e.g. converter_temp, cooling'}
              ariaLabel={zh ? '異常標籤' : 'Abnormal tags'}
              fullWidth
            />
          </Field>

          {/* 常用告警碼 chips（一鍵帶入告警碼 + 描述塞進異常標籤）。 */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {COMMON_ALARM_CODES.map(a => (
              <Btn
                key={a.code}
                size="sm"
                variant="ghost"
                ariaLabel={`${zh ? '帶入告警碼' : 'Use alarm'} ${a.code}`}
                onClick={() => {
                  setAlarmCode(String(a.code));
                  setTagsRaw(zh ? a.labelZh : a.labelEn);
                }}
              >
                {a.code} · {zh ? a.labelZh : a.labelEn}
              </Btn>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <Btn
              variant="primary"
              fullWidth
              loading={loading}
              disabled={!canRun}
              ariaLabel={zh ? '檢索處置' : 'Retrieve actions'}
              onClick={handleRun}
            >
              {loading ? (zh ? '檢索中…' : 'Retrieving…') : zh ? '檢索處置' : 'Retrieve'}
            </Btn>
            <Btn variant="secondary" ariaLabel={zh ? '清除' : 'Clear'} onClick={handleClear}>
              {zh ? '清除' : 'Clear'}
            </Btn>
          </div>
        </div>
      </Card>

      {/* 警報摘要 + 系統自動構造的 query（透明標示「系統據此檢索」）。 */}
      {result && (
        <Card tone="muted" style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
            <StatusPill tone="warn" size="md">
              {zh ? '告警碼' : 'Alarm'} {result.alert.alarm_code}
            </StatusPill>
            {result.alert.alarm_level && (
              <StatusPill tone="info" size="md">
                {result.alert.alarm_level}
              </StatusPill>
            )}
            <span style={{ fontSize: 12, color: C.sub }}>{result.alert.turbine_id}</span>
          </div>
          <div style={{ fontSize: 12, color: C.faint, marginTop: 8 }}>
            <span style={{ fontWeight: 600 }}>{zh ? '系統據此檢索：' : 'Auto-query: '}</span>
            {result.query.text || (zh ? '（僅告警碼）' : '(alarm code only)')}
          </div>
        </Card>
      )}

      <ResultList
        chunks={result?.chunks ?? []}
        loading={loading}
        error={error}
        hasResult={result != null}
        lang={lang}
      />
    </>
  );
};

export const FieldPage: React.FC<FieldPageProps> = ({ lang }) => {
  const { info, search, alert, runSearch, clearSearch, runAlert, clearAlert } = useKnowledge();
  const zh = lang === 'zh';

  const [mode, setMode] = useState<FieldMode>('query');

  // baseline badge：is_baseline=true 表示 placeholder 檢索（非真向量），現場可見地標示。
  // /info 失敗（例：handler 初始化 503）時改顯示警示 badge，不讓狀態靜默消失（demo 場景關鍵）。
  const infoBadge = info.error ? (
    <StatusPill tone="warn" size="md">
      {zh ? 'RAG 服務異常' : 'RAG unavailable'}
    </StatusPill>
  ) : info.data ? (
    <StatusPill tone={info.data.is_baseline ? 'amber' : 'ok'} size="md">
      {info.data.is_baseline
        ? zh
          ? '示範檢索（baseline）'
          : 'Baseline retrieval'
        : zh
          ? `向量檢索 · ${info.data.retriever}`
          : `Vector · ${info.data.retriever}`}
    </StatusPill>
  ) : null;

  return (
    <div style={{ maxWidth: 560, margin: '0 auto' }}>
      <PageHeader
        title={zh ? '現場知識查詢' : 'Field Knowledge'}
        sub={
          zh
            ? '輸入警報描述或告警碼，即時查手冊處置段落'
            : 'Search the manual by alarm description or code'
        }
        actions={infoBadge}
      />

      <ModeToggle mode={mode} onChange={setMode} lang={lang} />

      {mode === 'query' ? (
        <QueryMode
          lang={lang}
          loading={search.loading}
          error={search.error}
          chunks={search.data?.items ?? []}
          hasResult={search.data != null}
          onSearch={runSearch}
          onClear={clearSearch}
        />
      ) : (
        <AlertMode
          lang={lang}
          loading={alert.loading}
          error={alert.error}
          result={alert.data}
          onRun={runAlert}
          onClear={clearAlert}
        />
      )}
    </div>
  );
};

export default FieldPage;
