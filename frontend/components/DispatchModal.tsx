/**
 * DispatchModal — A · Calm Operator 改版（功能不動，套新樣式）。
 */

import React, { useState } from 'react';
import { type TurbineData, type Technician, TechnicianStatus } from '../types';
import { Btn, Card, StatusPill } from './ui';
import { useTheme } from '../theme/ThemeProvider';

interface DispatchModalProps {
  turbine: TurbineData;
  technicians: Technician[];
  faultAnalysis: string;
  onClose: () => void;
  onConfirm: (turbineId: number, technicianId: number, faultDescription: string) => void;
}

const DispatchModal: React.FC<DispatchModalProps> = ({
  turbine,
  technicians,
  faultAnalysis,
  onClose,
  onConfirm,
}) => {
  const { C } = useTheme();
  const [selectedTechnicianId, setSelectedTechnicianId] = useState<number | null>(null);
  const available = technicians.filter(t => t.status === TechnicianStatus.ON_DUTY);

  const handleConfirm = () => {
    if (selectedTechnicianId) {
      onConfirm(turbine.id, selectedTechnicianId, faultAnalysis);
    }
  };

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
      <div onClick={e => e.stopPropagation()} style={{ width: '100%', maxWidth: 640 }}>
        <Card padding={0}>
          <div
            style={{
              padding: '16px 20px',
              borderBottom: `1px solid ${C.border}`,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
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
              Dispatch Technician
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

          <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <h3 style={{ margin: 0, color: C.accent, fontSize: 16, fontWeight: 600 }}>
                Target turbine: {turbine.name}
              </h3>
              <div style={{ marginTop: 6, fontSize: 13, color: C.sub }}>
                Current status:{' '}
                <span style={{ color: C.warn, fontWeight: 600 }}>{turbine.status}</span>
              </div>
            </div>

            <Card tone="muted">
              <h4 style={{ margin: 0, fontSize: 13, fontWeight: 600, color: C.text }}>
                AI fault analysis
              </h4>
              <pre
                style={{
                  marginTop: 8,
                  fontSize: 12,
                  color: C.sub,
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'JetBrains Mono, monospace',
                  margin: 0,
                  paddingTop: 8,
                }}
              >
                {faultAnalysis}
              </pre>
            </Card>

            <div>
              <h4 style={{ margin: 0, marginBottom: 10, fontSize: 13, fontWeight: 600, color: C.text }}>
                Select available technician
              </h4>
              {available.length > 0 ? (
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                    gap: 8,
                  }}
                >
                  {available.map(tech => {
                    const active = selectedTechnicianId === tech.id;
                    return (
                      <button
                        key={tech.id}
                        type="button"
                        onClick={() => setSelectedTechnicianId(tech.id)}
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
                        <div style={{ fontWeight: 700, color: C.text, fontSize: 14 }}>
                          {tech.name}
                        </div>
                        <div style={{ marginTop: 4 }}>
                          <StatusPill tone="ok" size="sm">
                            {tech.status}
                          </StatusPill>
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <Card tone="warn">
                  <div style={{ color: C.warn, fontSize: 13 }}>
                    No technicians are currently on duty.
                  </div>
                </Card>
              )}
            </div>
          </div>

          <div
            style={{
              padding: '14px 20px',
              borderTop: `1px solid ${C.border}`,
              display: 'flex',
              justifyContent: 'flex-end',
              gap: 8,
            }}
          >
            <Btn onClick={onClose}>Cancel</Btn>
            <Btn
              variant="primary"
              onClick={handleConfirm}
              disabled={!selectedTechnicianId}
              ariaLabel="Confirm dispatch"
            >
              Confirm dispatch
            </Btn>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default DispatchModal;
