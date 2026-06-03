/**
 * FieldPage — 現場工程師 mobile-first 知識查詢頁（WMOM-20260603-03，EPIC-M5 M5-5）。
 *
 * PMF 關鍵頁：警報跳出 → 30 秒內現場工程師手機看到「手冊對應段落 + 可解釋命中原因」。
 * Demo killer：「這比 LINE 群組問師傅快嗎？」
 *
 * 版面（單欄、窄寬度、大觸控目標，手機優先）：
 *   - PageHeader：現場知識查詢 + RAG 來源 / baseline badge
 *   - 搜尋區：關鍵字 input + 告警碼 input + 查詢 / 清除按鈕
 *   - 常用告警碼 chips（一鍵帶入，現場手套操作友善）
 *   - 結果：RetrievedChunk 卡片（相關度 % + 繁中命中原因 + 文件來源 + 段落正文）
 *
 * 資料流走 useKnowledge（GET /info 一次 + POST /query 手動檢索）；顏色全走 theme，不寫 hex。
 */

import React, { useMemo, useState } from 'react';
import { useKnowledge } from '../../hooks/useKnowledge';
import type { Lang } from '../../hooks/useI18n';
import type { RetrievedChunk } from '../../services/knowledgeService';
import { useTheme } from '../../theme/ThemeProvider';
import { Card, Btn, PageHeader, StatusPill, Field, Input } from '../ui';

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

export const FieldPage: React.FC<FieldPageProps> = ({ lang }) => {
  const { C } = useTheme();
  const { info, search, runSearch, clearSearch } = useKnowledge();
  const zh = lang === 'zh';

  const [text, setText] = useState('');
  const [alarmCode, setAlarmCode] = useState('');

  // 告警碼解析：空字串 / 非數字 → 不帶；正整數才帶入 query。
  const parsedAlarmCode = useMemo<number | null>(() => {
    const n = Number(alarmCode.trim());
    return Number.isInteger(n) && n > 0 ? n : null;
  }, [alarmCode]);

  // 至少要有文字或告警碼才能查（避免空查詢打 backend）。
  const canSearch = text.trim().length > 0 || parsedAlarmCode != null;

  const handleSearch = (): void => {
    if (!canSearch) return;
    void runSearch({
      text: text.trim(),
      alarm_codes: parsedAlarmCode != null ? [parsedAlarmCode] : [],
    });
  };

  const handleClear = (): void => {
    setText('');
    setAlarmCode('');
    clearSearch();
  };

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

  const results = search.data?.items ?? [];

  // 顯示給現場工程師的錯誤訊息：剝掉 service 層的 `POST /api/... failed:` 技術前綴，
  // 只留 backend 的繁中 detail（readError 已抽好）。
  const searchErrorMsg = search.error?.replace(/^(GET|POST)\s+\S+\s+failed:\s*/, '') ?? null;

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

      {/* ── 搜尋區 ── */}
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
              loading={search.loading}
              disabled={!canSearch}
              ariaLabel={zh ? '查詢手冊' : 'Search manual'}
              onClick={handleSearch}
            >
              {search.loading ? (zh ? '查詢中…' : 'Searching…') : zh ? '查詢手冊' : 'Search'}
            </Btn>
            <Btn
              variant="secondary"
              ariaLabel={zh ? '清除' : 'Clear'}
              onClick={handleClear}
            >
              {zh ? '清除' : 'Clear'}
            </Btn>
          </div>
        </div>
      </Card>

      {/* ── 狀態 / 結果 ── */}
      {searchErrorMsg && (
        <Card tone="warn" style={{ marginBottom: 12 }}>
          <div style={{ color: C.warn, fontSize: 13 }}>
            {zh ? '查詢失敗：' : 'Search failed: '}
            {searchErrorMsg}
          </div>
        </Card>
      )}

      {!search.loading && !search.error && search.data && results.length === 0 && (
        <Card tone="muted">
          <div style={{ color: C.sub, fontSize: 14, textAlign: 'center', padding: '12px 0' }}>
            {zh
              ? '查無對應手冊段落，請換個關鍵字或告警碼。'
              : 'No matching manual section. Try another keyword or alarm code.'}
          </div>
        </Card>
      )}

      {results.length > 0 && (
        <>
          <div style={{ fontSize: 12, color: C.sub, marginBottom: 10 }}>
            {/* backend total（computed_field）= items.length，此處 results 已非空，直接用其長度。 */}
            {zh
              ? `找到 ${results.length} 段相關處置`
              : `${results.length} matching section(s)`}
          </div>
          {results.map(item => (
            <ResultCard key={item.chunk.id} item={item} lang={lang} />
          ))}
        </>
      )}
    </div>
  );
};

export default FieldPage;
