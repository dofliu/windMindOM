/**
 * WorkOrderDetailModal — A · Calm Operator 改版（功能不動，套新樣式）。
 */

import React, { useState } from 'react';
import { type WorkOrder, type Technician, WorkOrderStatus } from '../types';
import { Btn, Card, StatusPill, workOrderStatusTone } from './ui';
import { useTheme } from '../theme/ThemeProvider';

interface Props {
  workOrder: WorkOrder;
  technicians: Technician[];
  onClose: () => void;
  onUpdate: (workOrderId: string, updates: Partial<Pick<WorkOrder, 'notes' | 'photos' | 'status'>>) => void;
  onComplete: (workOrder: WorkOrder) => void;
}

const WorkOrderDetailModal: React.FC<Props> = ({
  workOrder,
  technicians,
  onClose,
  onUpdate,
  onComplete,
}) => {
  const { C } = useTheme();
  const [notes, setNotes] = useState(workOrder.notes);
  const [photos, setPhotos] = useState<string[]>(workOrder.photos);

  const isCompleted = workOrder.status === WorkOrderStatus.COMPLETED;
  const techName =
    technicians.find(t => t.id === workOrder.technicianId)?.name || 'N/A';

  const handlePhotoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    for (let i = 0; i < files.length; i++) {
      const file = files.item(i);
      if (!file) continue;
      const reader = new FileReader();
      reader.onloadend = () => {
        if (typeof reader.result === 'string') {
          const newPhoto = reader.result;
          setPhotos(prev => [...prev, newPhoto]);
        }
      };
      reader.readAsDataURL(file);
    }
  };

  const removePhoto = (i: number) => setPhotos(prev => prev.filter((_, j) => j !== i));

  const handleSave = () => onUpdate(workOrder.id, { notes, photos });

  const handleComplete = () => {
    if (photos.length > 0) {
      onComplete({
        ...workOrder,
        notes,
        photos,
        status: WorkOrderStatus.COMPLETED,
      });
    }
  };

  const statusLabel = (s: WorkOrderStatus) =>
    s === WorkOrderStatus.IN_PROGRESS ? 'IN PROGRESS' : s === WorkOrderStatus.COMPLETED ? 'COMPLETED' : 'OPEN';

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
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
        style={{ width: '100%', maxWidth: 880, maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}
      >
        <Card padding={0} style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', maxHeight: '90vh' }}>
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
            <h2
              style={{
                margin: 0,
                fontFamily: '"DM Serif Display", serif',
                fontSize: 24,
                fontWeight: 400,
                color: C.text,
              }}
            >
              Work order <span style={{ color: C.accent }}>#{workOrder.id.slice(-6)}</span>
            </h2>
            <button
              onClick={onClose}
              aria-label="Close"
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

          <div style={{ padding: 20, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Detail grid */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: 12,
              }}
            >
              <Card tone="muted" padding={12}>
                <div style={{ fontSize: 11, color: C.sub, textTransform: 'uppercase' }}>Turbine</div>
                <div style={{ fontWeight: 700, color: C.text, fontSize: 16, marginTop: 4 }}>
                  {workOrder.turbineName}
                </div>
              </Card>
              <Card tone="muted" padding={12}>
                <div style={{ fontSize: 11, color: C.sub, textTransform: 'uppercase' }}>Technician</div>
                <div style={{ fontWeight: 700, color: C.text, fontSize: 16, marginTop: 4 }}>{techName}</div>
              </Card>
              <Card tone="muted" padding={12}>
                <div style={{ fontSize: 11, color: C.sub, textTransform: 'uppercase' }}>Status</div>
                <div style={{ marginTop: 6 }}>
                  <StatusPill tone={workOrderStatusTone(workOrder.status)} size="md">
                    {statusLabel(workOrder.status)}
                  </StatusPill>
                </div>
              </Card>
            </div>

            {/* Fault description */}
            <Card tone="muted">
              <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 6 }}>
                Fault description
              </div>
              <pre
                style={{
                  margin: 0,
                  fontSize: 12,
                  color: C.sub,
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'JetBrains Mono, monospace',
                }}
              >
                {workOrder.faultDescription}
              </pre>
            </Card>

            {/* Notes */}
            <div>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 6 }}>
                Maintenance notes
              </label>
              <textarea
                value={notes}
                onChange={e => setNotes(e.target.value)}
                rows={5}
                disabled={isCompleted}
                placeholder="Add notes..."
                style={{
                  width: '100%',
                  background: C.panel,
                  border: `1px solid ${C.border}`,
                  borderRadius: 8,
                  padding: 10,
                  fontSize: 13,
                  color: C.text,
                  fontFamily: 'inherit',
                  resize: 'vertical',
                  outline: 'none',
                  boxSizing: 'border-box',
                  opacity: isCompleted ? 0.6 : 1,
                }}
              />
            </div>

            {/* Photos */}
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 6 }}>
                Site photos
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
                  gap: 10,
                }}
              >
                {photos.map((p, i) => (
                  <div key={i} style={{ position: 'relative' }}>
                    <img
                      src={p}
                      alt={`Photo ${i + 1}`}
                      style={{
                        width: '100%',
                        height: 120,
                        objectFit: 'cover',
                        borderRadius: 8,
                        border: `1px solid ${C.border}`,
                      }}
                    />
                    {!isCompleted && (
                      <button
                        onClick={() => removePhoto(i)}
                        aria-label="Remove photo"
                        style={{
                          position: 'absolute',
                          top: 4,
                          right: 4,
                          background: C.warn,
                          color: '#FFFFFF',
                          border: 'none',
                          borderRadius: '50%',
                          width: 24,
                          height: 24,
                          cursor: 'pointer',
                          fontSize: 14,
                        }}
                      >
                        ✕
                      </button>
                    )}
                  </div>
                ))}
                {!isCompleted && (
                  <label
                    style={{
                      height: 120,
                      borderRadius: 8,
                      border: `2px dashed ${C.border}`,
                      background: C.panelMuted,
                      display: 'grid',
                      placeItems: 'center',
                      cursor: 'pointer',
                      color: C.sub,
                      fontSize: 12,
                      transition: 'border-color 160ms ease',
                    }}
                  >
                    <span>+ Upload</span>
                    <input
                      type="file"
                      accept="image/*"
                      multiple
                      onChange={handlePhotoUpload}
                      style={{ display: 'none' }}
                    />
                  </label>
                )}
              </div>
              {!isCompleted && (
                <div style={{ marginTop: 6, fontSize: 11, color: C.faint }}>
                  At least one photo is required to complete the work order.
                </div>
              )}
              {isCompleted && photos.length === 0 && (
                <div style={{ fontSize: 12, color: C.faint }}>No photos uploaded.</div>
              )}
            </div>
          </div>

          {!isCompleted && (
            <div
              style={{
                padding: '14px 20px',
                borderTop: `1px solid ${C.border}`,
                display: 'flex',
                justifyContent: 'flex-end',
                gap: 8,
                flexShrink: 0,
              }}
            >
              <Btn onClick={handleSave} ariaLabel="Save notes and photos">
                Save
              </Btn>
              <Btn
                variant="primary"
                onClick={handleComplete}
                disabled={photos.length === 0}
                ariaLabel="Complete work order"
              >
                Complete work order
              </Btn>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};

export default WorkOrderDetailModal;
