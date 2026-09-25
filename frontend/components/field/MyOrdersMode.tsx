/**
 * MyOrdersMode — 現場工程師「我的工單 + 完工」（WMOM-20260608-02，EPIC-M5 M5-5 Part B-2）。
 *
 * DEC-20260608-02：
 *   - 「我的工單」依目前登入者（mock login）`assignee_id` 過濾
 *   - 「完工」須簽名 + 拍照佐證 → 兩者皆備才允許送出（前端強制；backend 設 optional）
 *
 * 流程：列出指派給我、進行中的工單 → 選一張 → 填工時 + 摘要 → 手寫簽名 + 拍照
 *   → 送出 finish（IN_PROGRESS → AWAITING_SIGNOFF）。
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { Lang } from '../../hooks/useI18n';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useTheme } from '../../theme/ThemeProvider';
import { workOrderApi } from '../../services/workOrderService';
import type { WorkOrderResponse } from '../../services/workOrderService';
import { authFetch } from '../../services/authClient';
import { Card, Btn, PageHeader, StatusPill, Field, Input } from '../ui';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

interface MyOrdersModeProps {
  lang: Lang;
}

/** 可完工的狀態（IN_PROGRESS 才能 finish；其餘僅顯示）。 */
const FINISHABLE = 'in_progress';

/** 取目前 active farm_id（與 FarmSelector / WorkflowPage 同來源 /api/farms）。 */
async function fetchActiveFarmId(): Promise<string | null> {
  const res = await authFetch(`${API_BASE}/api/farms`);
  if (!res.ok) throw new Error(`/api/farms ${res.status}`);
  const data = (await res.json()) as { active_farm_id?: string | null };
  return data.active_farm_id ?? null;
}

/** 把 File 讀成 base64 data URL。 */
function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error(reader.error?.message || 'FileReader error'));
    reader.readAsDataURL(file);
  });
}

/**
 * 手寫簽名板（canvas + pointer events）。
 * 變更時透過 onChange 回傳 dataURL；清除時回傳 null。
 */
const SignaturePad: React.FC<{
  lang: Lang;
  onChange: (dataUrl: string | null) => void;
}> = ({ lang, onChange }) => {
  const { C } = useTheme();
  const zh = lang === 'zh';
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawing = useRef(false);
  const dirty = useRef(false);

  const pos = (e: React.PointerEvent<HTMLCanvasElement>): [number, number] => {
    const rect = e.currentTarget.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top];
  };

  const start = (e: React.PointerEvent<HTMLCanvasElement>): void => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drawing.current = true;
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx) return;
    const [x, y] = pos(e);
    ctx.beginPath();
    ctx.moveTo(x, y);
  };

  const move = (e: React.PointerEvent<HTMLCanvasElement>): void => {
    if (!drawing.current) return;
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx) return;
    const [x, y] = pos(e);
    ctx.lineTo(x, y);
    ctx.strokeStyle = C.text;
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.stroke();
    dirty.current = true;
  };

  const end = (): void => {
    if (!drawing.current) return;
    drawing.current = false;
    if (dirty.current && canvasRef.current) {
      onChange(canvasRef.current.toDataURL('image/png'));
    }
  };

  const clear = (): void => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (canvas && ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    dirty.current = false;
    onChange(null);
  };

  return (
    <div>
      <canvas
        ref={canvasRef}
        width={500}
        height={160}
        aria-label={zh ? '簽名板' : 'Signature pad'}
        onPointerDown={start}
        onPointerMove={move}
        onPointerUp={end}
        onPointerLeave={end}
        onPointerCancel={end}
        style={{
          width: '100%',
          height: 160,
          border: `1px dashed ${C.border}`,
          borderRadius: 8,
          background: C.panelMuted,
          touchAction: 'none',
          cursor: 'crosshair',
        }}
      />
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 6 }}>
        <Btn size="sm" variant="ghost" ariaLabel={zh ? '清除簽名' : 'Clear signature'} onClick={clear}>
          {zh ? '清除簽名' : 'Clear'}
        </Btn>
      </div>
    </div>
  );
};

/** 完工表單（選定工單後展開）。 */
const CompletionForm: React.FC<{
  lang: Lang;
  order: WorkOrderResponse;
  farmId: string;
  onDone: () => void;
  onCancel: () => void;
}> = ({ lang, order, farmId, onDone, onCancel }) => {
  const { C } = useTheme();
  const zh = lang === 'zh';
  const [hours, setHours] = useState('');
  const [summary, setSummary] = useState('');
  const [followup, setFollowup] = useState(false);
  const [signature, setSignature] = useState<string | null>(null);
  const [photos, setPhotos] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsedHours = Number(hours.trim());
  const hoursValid = Number.isFinite(parsedHours) && parsedHours >= 0 && hours.trim() !== '';
  // DEC-20260608-02：現場完工強制簽名 + 至少一張照片。
  const canSubmit = hoursValid && signature != null && photos.length > 0 && !submitting;

  const addPhotos = useCallback(async (files: FileList | null): Promise<void> => {
    if (!files || files.length === 0) return;
    try {
      const urls = await Promise.all(Array.from(files).map(fileToDataUrl));
      setPhotos(prev => [...prev, ...urls]);
    } catch {
      setError(zh ? '照片讀取失敗，請重試。' : 'Failed to read photo.');
    }
  }, [zh]);

  const submit = async (): Promise<void> => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await workOrderApi.finish(order.id, farmId, {
        actual_hours: parsedHours,
        followup_kind: followup ? 'followup_needed' : 'none',
        work_summary: summary.trim() || null,
        completion_signature: signature,
        completion_photos: photos,
      });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSubmitting(false);
    }
  };

  return (
    <Card style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ fontWeight: 600, color: C.text }}>
          {zh ? '完工回報' : 'Complete work order'} · {order.business_key}
        </div>
        <div style={{ fontSize: 13, color: C.sub }}>
          {order.turbine_id} · {order.title}
        </div>

        <Field label={zh ? '實際工時（小時）' : 'Actual hours'} fullWidth>
          <Input
            value={hours}
            onChange={setHours}
            type="number"
            min={0}
            placeholder={zh ? '例：3.5' : 'e.g. 3.5'}
            ariaLabel={zh ? '實際工時' : 'Actual hours'}
            fullWidth
          />
        </Field>

        <Field label={zh ? '工作摘要（可選）' : 'Work summary (optional)'} fullWidth>
          <Input
            value={summary}
            onChange={setSummary}
            placeholder={zh ? '例：更換主軸承，測試正常' : 'e.g. replaced main bearing'}
            ariaLabel={zh ? '工作摘要' : 'Work summary'}
            fullWidth
          />
        </Field>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: C.sub }}>
          <input
            type="checkbox"
            checked={followup}
            onChange={e => setFollowup(e.target.checked)}
            aria-label={zh ? '需後續追蹤' : 'Needs follow-up'}
          />
          {zh ? '需後續追蹤' : 'Needs follow-up'}
        </label>

        {/* 簽名（必填）。 */}
        <Field label={zh ? '簽名（必填）' : 'Signature (required)'} fullWidth>
          <SignaturePad lang={lang} onChange={setSignature} />
        </Field>

        {/* 拍照（必填，至少一張）。 */}
        <Field label={zh ? '佐證照片（必填，至少一張）' : 'Photos (required, ≥1)'} fullWidth>
          <input
            type="file"
            accept="image/*"
            capture="environment"
            multiple
            aria-label={zh ? '拍照或選照片' : 'Take or pick photos'}
            onChange={e => void addPhotos(e.target.files)}
          />
          {photos.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
              {photos.map((p, i) => (
                <div key={i} style={{ position: 'relative' }}>
                  <img
                    src={p}
                    alt={`${zh ? '佐證照片' : 'photo'} ${i + 1}`}
                    style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: 6 }}
                  />
                  <Btn
                    size="sm"
                    variant="ghost"
                    ariaLabel={`${zh ? '移除照片' : 'Remove photo'} ${i + 1}`}
                    onClick={() => setPhotos(prev => prev.filter((_, j) => j !== i))}
                  >
                    ✕
                  </Btn>
                </div>
              ))}
            </div>
          )}
        </Field>

        {error && (
          <div style={{ color: C.warn, fontSize: 13 }}>
            {zh ? '送出失敗：' : 'Submit failed: '}
            {error}
          </div>
        )}

        {/* 未簽 / 未拍時提示為何不能送（透明，不讓 disabled 無解釋）。 */}
        {!canSubmit && !submitting && (
          <div style={{ fontSize: 12, color: C.faint }}>
            {zh
              ? '完工需填工時、簽名、並至少拍一張照片。'
              : 'Completion needs hours, signature, and ≥1 photo.'}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8 }}>
          <Btn
            variant="primary"
            fullWidth
            loading={submitting}
            disabled={!canSubmit}
            ariaLabel={zh ? '送出完工' : 'Submit completion'}
            onClick={() => void submit()}
          >
            {submitting ? (zh ? '送出中…' : 'Submitting…') : zh ? '送出完工' : 'Submit'}
          </Btn>
          <Btn variant="secondary" ariaLabel={zh ? '取消' : 'Cancel'} onClick={onCancel}>
            {zh ? '取消' : 'Cancel'}
          </Btn>
        </div>
      </div>
    </Card>
  );
};

export const MyOrdersMode: React.FC<MyOrdersModeProps> = ({ lang }) => {
  const { C } = useTheme();
  const { currentUser } = useCurrentUser();
  const zh = lang === 'zh';

  const [farmId, setFarmId] = useState<string | null>(null);
  const [orders, setOrders] = useState<WorkOrderResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<WorkOrderResponse | null>(null);
  // 請求序號：切換登入者時並發 reload，只套用「最新一次」的結果（防慢網路下
  // stale 回應覆寫新資料 — 現場 4G 弱訊號場景）。
  const reqId = useRef(0);

  const reload = useCallback(async (): Promise<void> => {
    const myId = ++reqId.current;
    setLoading(true);
    setError(null);
    try {
      const fid = await fetchActiveFarmId();
      if (myId !== reqId.current) return; // 已有更新的 reload，丟棄本次
      setFarmId(fid);
      if (!fid) {
        setOrders([]);
        return;
      }
      // 「我的工單」= 指派給目前登入者的工單。
      const resp = await workOrderApi.list({ farm_id: fid, assignee_id: currentUser.id });
      if (myId !== reqId.current) return;
      setOrders(resp.items);
    } catch (e) {
      if (myId === reqId.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (myId === reqId.current) setLoading(false);
    }
  }, [currentUser.id]);

  // 切換登入者 / 首次掛載時重抓（assignee 變 → 我的工單變）。
  useEffect(() => {
    setSelected(null);
    void reload();
  }, [reload]);

  if (selected && farmId) {
    return (
      <CompletionForm
        lang={lang}
        order={selected}
        farmId={farmId}
        onDone={() => {
          setSelected(null);
          void reload();
        }}
        onCancel={() => setSelected(null)}
      />
    );
  }

  return (
    <>
      <div style={{ fontSize: 12, color: C.faint, marginBottom: 12 }}>
        {zh ? '目前身分：' : 'Signed in as: '}
        <span style={{ fontWeight: 600, color: C.sub }}>{currentUser.name}</span>
      </div>

      {error && (
        <Card tone="warn" style={{ marginBottom: 12 }}>
          <div style={{ color: C.warn, fontSize: 13 }}>
            {zh ? '載入失敗：' : 'Load failed: '}
            {error}
          </div>
        </Card>
      )}

      {loading && (
        <div style={{ color: C.sub, textAlign: 'center', padding: '16px 0', fontSize: 13 }}>
          {zh ? '載入中…' : 'Loading…'}
        </div>
      )}

      {!loading && !error && orders.length === 0 && (
        <Card tone="muted">
          <div style={{ color: C.sub, fontSize: 14, textAlign: 'center', padding: '12px 0' }}>
            {zh ? '目前沒有指派給你的工單。' : 'No work orders assigned to you.'}
          </div>
        </Card>
      )}

      {orders.map(o => {
        const finishable = o.status === FINISHABLE;
        return (
          <Card key={o.id} style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 600, color: C.text }}>{o.title}</div>
                <div style={{ fontSize: 12, color: C.sub }}>
                  {o.business_key} · {o.turbine_id}
                </div>
              </div>
              <StatusPill tone={finishable ? 'ok' : 'muted'} size="md">
                {o.status}
              </StatusPill>
            </div>
            {finishable && (
              <div style={{ marginTop: 10 }}>
                <Btn
                  variant="primary"
                  fullWidth
                  ariaLabel={`${zh ? '完工回報' : 'Complete'} ${o.business_key}`}
                  onClick={() => setSelected(o)}
                >
                  {zh ? '完工回報' : 'Complete'}
                </Btn>
              </div>
            )}
          </Card>
        );
      })}
    </>
  );
};

export default MyOrdersMode;
