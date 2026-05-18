/**
 * CreateMaterialRequestWizard — 3 步建立領料單精靈（WMOM-20260509-06）。
 *
 * Step 1：選關聯工單（list active work orders；可跳過 — backend 容許 null）
 * Step 2：選料件 + 估計數量（左右 split：左 picker / 右 cart）
 * Step 3：檢閱 + submit
 *
 * 與 WorkOrderWizard 同視覺骨架（Card padding=0 + DM Serif title + 底部 Btn）。
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Btn, Card, Field, Input, Select, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  StockKindValues,
  type CreateMaterialRequestItemPayload,
  type CreateMaterialRequestPayload,
  type InventoryItemSummary,
  type StockKind,
} from '../../services/materialService';
import type { WorkOrderResponse } from '../../services/workOrderService';
import { useInventoryItems } from '../../hooks/useInventoryItems';
import { stockKindLabel, typeLabel } from './statusUtils';

type Lang = 'en' | 'zh';

interface CartLine {
  item: InventoryItemSummary;
  estimated_qty: number;
  stock_kind: StockKind;
}

interface Props {
  farmId: string;
  /** 目前操作者 UUID — 寫進 requester_id；caller 從 useCurrentUser 傳入。 */
  requesterId: string;
  /** 預載 active work orders（給 step 1 picker；caller 可傳已 fetch 過的工單列表）。 */
  workOrders: WorkOrderResponse[];
  /** 預先帶入的關聯工單 id（從工單詳情點「+ 開領料單」時用，不在本 issue 加但預留 API）。 */
  preselectWorkOrderId?: string | null;
  onClose: () => void;
  onSubmit: (req: CreateMaterialRequestPayload) => Promise<void>;
  lang: Lang;
}

const CreateMaterialRequestWizard: React.FC<Props> = ({
  farmId,
  requesterId,
  workOrders,
  preselectWorkOrderId,
  onClose,
  onSubmit,
  lang,
}) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 1：關聯工單
  const [workOrderId, setWorkOrderId] = useState<string | null>(
    preselectWorkOrderId ?? null,
  );

  // Step 2：料件
  const [itemSearch, setItemSearch] = useState('');
  const [cart, setCart] = useState<CartLine[]>([]);
  const inv = useInventoryItems({ farmId, search: itemSearch });

  // Step 3：error 顯示

  // ── 把已加進 cart 的 item filter 掉 ──
  const cartIds = useMemo(() => new Set(cart.map(c => c.item.id)), [cart]);
  const availableItems = useMemo(
    () => inv.items.filter(it => !cartIds.has(it.id)),
    [inv.items, cartIds],
  );

  const canNext2 = cart.length > 0 && cart.every(c => c.estimated_qty > 0);

  // ── 切到 step 2 自動 refresh inventory ──
  useEffect(() => {
    if (step === 2) {
      inv.refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step]);

  const addItem = (it: InventoryItemSummary) => {
    setCart(prev => [
      ...prev,
      { item: it, estimated_qty: 1, stock_kind: 'new' },
    ]);
  };

  const removeItem = (itemId: string) => {
    setCart(prev => prev.filter(c => c.item.id !== itemId));
  };

  const updateLine = (itemId: string, patch: Partial<CartLine>) => {
    setCart(prev =>
      prev.map(c => (c.item.id === itemId ? { ...c, ...patch } : c)),
    );
  };

  const buildRequest = (): CreateMaterialRequestPayload => ({
    farm_id: farmId,
    requester_id: requesterId,
    work_order_id: workOrderId,
    items: cart.map<CreateMaterialRequestItemPayload>(c => ({
      item_id: c.item.id,
      estimated_qty: c.estimated_qty,
      stock_kind: c.stock_kind,
    })),
  });

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit(buildRequest());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  // 顯示「未結案」工單供關聯（closed / cancelled 不顯示，避免關聯死案）
  const sortedWorkOrders = useMemo(
    () =>
      [...workOrders]
        .filter(wo => wo.status !== 'closed' && wo.status !== 'cancelled')
        .sort((a, b) => (a.business_key < b.business_key ? 1 : -1)),
    [workOrders],
  );

  // backdrop click：若 cart 有未送出料件，先 confirm 才關閉
  const handleBackdropClick = () => {
    if (cart.length > 0) {
      const ok = window.confirm(
        ui(
          'Discard this material request? Selected items will be lost.',
          '要放棄此領料單嗎？已選料件會遺失。',
        ),
      );
      if (!ok) return;
    }
    onClose();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={ui('Create material request', '建立領料單')}
      onClick={handleBackdropClick}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.55)',
        zIndex: 200,
        display: 'grid',
        placeItems: 'center',
        padding: 16,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 820, maxHeight: '90vh', display: 'flex' }}
      >
        <Card
          padding={0}
          style={{
            width: '100%',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            maxHeight: '90vh',
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: '16px 20px',
              borderBottom: `1px solid ${C.border}`,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexShrink: 0,
            }}
          >
            <div>
              <h2
                style={{
                  margin: 0,
                  fontFamily: '"DM Serif Display", serif',
                  fontSize: 24,
                  fontWeight: 400,
                  color: C.text,
                }}
              >
                {ui('Create material request', '建立領料單')}
              </h2>
              <div style={{ fontSize: 12, color: C.sub, marginTop: 4 }}>
                {ui(`Step ${step} of 3`, `第 ${step} 步 / 共 3 步`)}
              </div>
            </div>
            <button
              onClick={onClose}
              aria-label={ui('Close', '關閉')}
              style={{
                background: 'transparent',
                border: 'none',
                color: C.sub,
                fontSize: 20,
                cursor: 'pointer',
              }}
            >
              ✕
            </button>
          </div>

          {/* Body */}
          <div
            style={{
              padding: 20,
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: 14,
            }}
          >
            {step === 1 && (
              <>
                <h3 style={{ margin: 0, fontSize: 14, color: C.text }}>
                  {ui('Link to work order (optional)', '關聯工單（選填）')}
                </h3>
                <div style={{ fontSize: 12, color: C.sub }}>
                  {ui(
                    'You can create a material request without linking to a work order. Ad-hoc stock requests are allowed.',
                    '可不關聯工單建立領料單；臨時補料請領亦允許。',
                  )}
                </div>

                {/* No-link option */}
                <button
                  type="button"
                  onClick={() => setWorkOrderId(null)}
                  aria-pressed={workOrderId === null}
                  style={{
                    padding: 12,
                    textAlign: 'left',
                    borderRadius: 10,
                    border: `2px solid ${workOrderId === null ? C.accent : C.border}`,
                    background: workOrderId === null ? C.accentSoft : C.panel,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    color: C.text,
                    fontSize: 13,
                  }}
                >
                  <strong>{ui('No linked work order', '不關聯工單')}</strong>
                  <div style={{ marginTop: 4, fontSize: 11, color: C.sub }}>
                    {ui('Ad-hoc / standalone material request', '臨時 / 獨立領料單')}
                  </div>
                </button>

                {sortedWorkOrders.length === 0 ? (
                  <Card tone="muted" padding={20}>
                    <div style={{ textAlign: 'center', color: C.faint, fontSize: 13 }}>
                      {ui(
                        'No open work orders available to link.',
                        '目前沒有可關聯的進行中工單。',
                      )}
                    </div>
                  </Card>
                ) : (
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                      gap: 8,
                      maxHeight: 320,
                      overflowY: 'auto',
                      padding: 2,
                    }}
                  >
                    {sortedWorkOrders.map(wo => {
                      const active = workOrderId === wo.id;
                      return (
                        <button
                          key={wo.id}
                          type="button"
                          onClick={() => setWorkOrderId(wo.id)}
                          aria-pressed={active}
                          style={{
                            padding: 12,
                            textAlign: 'left',
                            borderRadius: 10,
                            border: `2px solid ${active ? C.accent : C.border}`,
                            background: active ? C.accentSoft : C.panel,
                            cursor: 'pointer',
                            fontFamily: 'inherit',
                          }}
                        >
                          <div
                            style={{
                              fontFamily: 'JetBrains Mono, monospace',
                              fontWeight: 700,
                              color: C.text,
                              fontSize: 13,
                            }}
                          >
                            {wo.business_key}
                          </div>
                          <div style={{ fontSize: 11, color: C.sub, marginTop: 4 }}>
                            {wo.turbine_id} · {typeLabel(wo.type, lang)}
                          </div>
                          <div
                            style={{
                              fontSize: 12,
                              color: C.text,
                              marginTop: 4,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {wo.title}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </>
            )}

            {step === 2 && (
              <>
                <h3 style={{ margin: 0, fontSize: 14, color: C.text }}>
                  {ui('Select items', '選擇料件')}
                </h3>

                <Field label={ui('Search items', '搜尋料件')}>
                  <Input
                    value={itemSearch}
                    onChange={setItemSearch}
                    placeholder={ui('SKU or name', 'SKU 或名稱')}
                    fullWidth
                    ariaLabel={ui('Search inventory items', '搜尋料件')}
                  />
                </Field>

                {inv.error && (
                  <Card tone="warn" padding={12}>
                    <div style={{ fontSize: 12, color: C.warn }}>⚠ {inv.error}</div>
                  </Card>
                )}

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 12,
                    minHeight: 320,
                  }}
                >
                  {/* Left：available items */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <div style={{ fontSize: 11, color: C.sub, marginBottom: 4 }}>
                      {ui(
                        `Available · ${availableItems.length} item${availableItems.length === 1 ? '' : 's'}`,
                        `可選 · ${availableItems.length} 項`,
                      )}
                    </div>
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 6,
                        maxHeight: 320,
                        overflowY: 'auto',
                        padding: 2,
                      }}
                    >
                      {inv.loading && availableItems.length === 0 ? (
                        <div style={{ fontSize: 12, color: C.faint }}>
                          {ui('Loading…', '載入中…')}
                        </div>
                      ) : availableItems.length === 0 ? (
                        <div style={{ fontSize: 12, color: C.faint }}>
                          {ui('No items match.', '沒有符合的料件。')}
                        </div>
                      ) : (
                        availableItems.map(it => (
                          <button
                            key={it.id}
                            type="button"
                            onClick={() => addItem(it)}
                            aria-label={`${ui('Add', '加入')} ${it.sku}`}
                            style={{
                              textAlign: 'left',
                              padding: '10px 12px',
                              borderRadius: 8,
                              border: `1px solid ${C.border}`,
                              background: C.panel,
                              cursor: 'pointer',
                              fontFamily: 'inherit',
                            }}
                          >
                            <div
                              style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                gap: 8,
                              }}
                            >
                              <span
                                style={{
                                  fontFamily: 'JetBrains Mono, monospace',
                                  fontSize: 12,
                                  fontWeight: 600,
                                  color: C.text,
                                }}
                              >
                                {it.sku}
                              </span>
                              {it.below_safety && (
                                <StatusPill tone="warn" size="sm">
                                  {ui('Low', '不足')}
                                </StatusPill>
                              )}
                            </div>
                            <div style={{ fontSize: 12, color: C.text, marginTop: 2 }}>
                              {it.name}
                            </div>
                            <div style={{ fontSize: 11, color: C.sub, marginTop: 2 }}>
                              {ui('Stock', '庫存')}:{' '}
                              <span style={{ fontFamily: 'JetBrains Mono, monospace' }}>
                                N {it.stock_new} / U {it.stock_used} / R {it.stock_repairing}
                              </span>
                            </div>
                          </button>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Right：cart */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <div style={{ fontSize: 11, color: C.sub, marginBottom: 4 }}>
                      {ui(
                        `Selected · ${cart.length} line${cart.length === 1 ? '' : 's'}`,
                        `已選 · ${cart.length} 項`,
                      )}
                    </div>
                    {cart.length === 0 ? (
                      <Card tone="muted" padding={20}>
                        <div
                          style={{ textAlign: 'center', color: C.faint, fontSize: 12 }}
                        >
                          {ui(
                            'Pick items from the left to add to the request.',
                            '從左側挑選料件加入領料單。',
                          )}
                        </div>
                      </Card>
                    ) : (
                      <div
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          gap: 6,
                          maxHeight: 320,
                          overflowY: 'auto',
                          padding: 2,
                        }}
                      >
                        {cart.map(line => (
                          <div
                            key={line.item.id}
                            style={{
                              padding: '10px 12px',
                              borderRadius: 8,
                              border: `1px solid ${C.border}`,
                              background: C.panelMuted,
                              display: 'flex',
                              flexDirection: 'column',
                              gap: 8,
                            }}
                          >
                            <div
                              style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                              }}
                            >
                              <span
                                style={{
                                  fontFamily: 'JetBrains Mono, monospace',
                                  fontSize: 12,
                                  fontWeight: 600,
                                  color: C.text,
                                }}
                              >
                                {line.item.sku}
                              </span>
                              <button
                                type="button"
                                onClick={() => removeItem(line.item.id)}
                                aria-label={`${ui('Remove', '移除')} ${line.item.sku}`}
                                style={{
                                  background: 'transparent',
                                  border: 'none',
                                  color: C.warn,
                                  cursor: 'pointer',
                                  fontSize: 13,
                                }}
                              >
                                ✕
                              </button>
                            </div>
                            <div style={{ fontSize: 12, color: C.text }}>
                              {line.item.name}
                            </div>
                            <div
                              style={{
                                display: 'grid',
                                gridTemplateColumns: '1fr 1fr',
                                gap: 6,
                              }}
                            >
                              <Field label={ui('Qty', '數量')}>
                                <Input
                                  type="number"
                                  min={1}
                                  value={line.estimated_qty}
                                  onChange={v =>
                                    updateLine(line.item.id, {
                                      estimated_qty: Math.max(1, parseInt(v) || 1),
                                    })
                                  }
                                  fullWidth
                                  ariaLabel={ui('Estimated qty', '預估數量')}
                                />
                              </Field>
                              <Field label={ui('Stock kind', '庫存類型')}>
                                <Select
                                  value={line.stock_kind}
                                  options={StockKindValues.map(k => ({
                                    value: k,
                                    label: stockKindLabel(k, lang),
                                  }))}
                                  onChange={v =>
                                    updateLine(line.item.id, {
                                      stock_kind: v as StockKind,
                                    })
                                  }
                                  ariaLabel={ui('Stock kind', '庫存類型')}
                                  fullWidth
                                />
                              </Field>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}

            {step === 3 && (
              <>
                <h3 style={{ margin: 0, fontSize: 14, color: C.text }}>
                  {ui('Review', '檢閱')}
                </h3>
                <Card tone="muted" padding={12}>
                  <div
                    style={{ fontSize: 13, color: C.text, display: 'grid', gap: 6 }}
                  >
                    <div>
                      <strong>{ui('Linked work order', '關聯工單')}:</strong>{' '}
                      {workOrderId
                        ? workOrders.find(w => w.id === workOrderId)?.business_key ??
                          `…${workOrderId.slice(-8)}`
                        : ui('(none)', '（無）')}
                    </div>
                    <div>
                      <strong>{ui('Items', '料件')}:</strong> {cart.length}
                    </div>
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 4,
                        marginTop: 4,
                      }}
                    >
                      {cart.map(line => (
                        <div
                          key={line.item.id}
                          style={{ fontSize: 12, color: C.sub }}
                        >
                          <span
                            style={{ fontFamily: 'JetBrains Mono, monospace' }}
                          >
                            {line.item.sku}
                          </span>{' '}
                          × {line.estimated_qty} · {stockKindLabel(line.stock_kind, lang)}
                        </div>
                      ))}
                    </div>
                  </div>
                </Card>
                {error && (
                  <Card tone="warn" padding={12}>
                    <div style={{ fontSize: 12, color: C.warn }}>⚠ {error}</div>
                  </Card>
                )}
                <div style={{ fontSize: 11, color: C.faint }}>
                  {ui(
                    'After creation, the request stays in DRAFT — submit for approval from the detail dialog.',
                    '建立後領料單為 DRAFT，需在詳情視窗點「送出簽核」啟動 3 階簽核 chain。',
                  )}
                </div>
              </>
            )}
          </div>

          {/* Footer */}
          <div
            style={{
              padding: '14px 20px',
              borderTop: `1px solid ${C.border}`,
              display: 'flex',
              justifyContent: 'space-between',
              gap: 8,
              flexShrink: 0,
            }}
          >
            <Btn onClick={onClose} ariaLabel={ui('Cancel', '取消')}>
              {ui('Cancel', '取消')}
            </Btn>
            <div style={{ display: 'flex', gap: 8 }}>
              {step > 1 && (
                <Btn
                  onClick={() => setStep(s => (s > 1 ? ((s - 1) as 1 | 2 | 3) : s))}
                  ariaLabel={ui('Back', '上一步')}
                >
                  {ui('Back', '上一步')}
                </Btn>
              )}
              {step < 3 && (
                <Btn
                  variant="primary"
                  onClick={() => setStep(s => (s < 3 ? ((s + 1) as 1 | 2 | 3) : s))}
                  disabled={step === 2 && !canNext2}
                  ariaLabel={ui('Next', '下一步')}
                >
                  {ui('Next', '下一步')}
                </Btn>
              )}
              {step === 3 && (
                <Btn
                  variant="primary"
                  onClick={handleSubmit}
                  disabled={submitting || cart.length === 0}
                  ariaLabel={ui('Create material request', '建立領料單')}
                >
                  {submitting
                    ? ui('Creating…', '建立中…')
                    : ui('Create material request', '建立領料單')}
                </Btn>
              )}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default CreateMaterialRequestWizard;
