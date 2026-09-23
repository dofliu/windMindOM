/**
 * MaintenanceHub — A · Calm Operator 改版。
 *
 * 版面：
 *   - PageHeader：維護中心 + 「N 張未結工單・M 位技師在崗」+ Filter / + New
 *   - Grid 2/3 + 1/3：
 *       Left 工單表格（ID / 風機 / 問題 / 技師 / 優先 / 狀態 / SLA）
 *       Right 技師排班（漸層頭像 + 狀態 pill + clock in/out）+ 本週行程（簡易 7 格）
 *
 * 保留：onSelectWorkOrder、toggleTechnicianStatus；priority / SLA 由 createdAt 動態推算。
 */

import React, { useMemo, useState } from 'react';
import { type useMaintenanceData } from '../hooks/useMaintenanceData';
import {
  type WorkOrder,
  WorkOrderStatus,
  TechnicianStatus,
  type Technician,
} from '../types';
import {
  Btn,
  Card,
  PageHeader,
  StatusPill,
  Select,
  workOrderStatusTone,
  technicianStatusTone,
  type PillTone,
} from './ui';
import { useTheme } from '../theme/ThemeProvider';

type MaintenanceData = ReturnType<typeof useMaintenanceData>;

interface MaintenanceHubProps {
  maintenanceData: MaintenanceData;
  onSelectWorkOrder: (workOrder: WorkOrder) => void;
  lang?: 'en' | 'zh';
}

// ─── helpers ───────────────────────────────────────────────────

function priorityFromAge(createdAt: number): { code: 'HIGH' | 'MED' | 'LOW'; tone: PillTone } {
  const ageH = (Date.now() - createdAt) / 3_600_000;
  if (ageH < 4) return { code: 'HIGH', tone: 'warn' };
  if (ageH < 24) return { code: 'MED', tone: 'amber' };
  return { code: 'LOW', tone: 'muted' };
}

function slaFromAge(createdAt: number): string {
  const ageH = Math.max(0, (Date.now() - createdAt) / 3_600_000);
  if (ageH < 1) return `${(ageH * 60).toFixed(0)}m`;
  if (ageH < 24) return `${ageH.toFixed(1)}h`;
  return `${(ageH / 24).toFixed(1)}d`;
}

const statusLabel = (s: WorkOrderStatus, tr: (en: string, zh: string) => string) => {
  if (s === WorkOrderStatus.IN_PROGRESS) return tr('IN PROGRESS', '處理中');
  if (s === WorkOrderStatus.COMPLETED) return tr('COMPLETED', '已完成');
  return tr('OPEN', '未結');
};

const techStatusLabel = (s: TechnicianStatus, tr: (en: string, zh: string) => string) => {
  if (s === TechnicianStatus.ON_DUTY) return tr('ON DUTY', '在崗');
  if (s === TechnicianStatus.DISPATCHED) return tr('DISPATCHED', '派遣中');
  return tr('OFF DUTY', '下班');
};

// ─── Avatar (漸層) ─────────────────────────────────────────────

const Avatar: React.FC<{ name: string }> = ({ name }) => {
  const { C } = useTheme();
  const initial = (name?.charAt(0) || '?').toUpperCase();
  return (
    <div
      aria-hidden
      style={{
        width: 36,
        height: 36,
        borderRadius: '50%',
        background: C.isDark
          ? `linear-gradient(135deg, ${C.accent}, #1A8E5C)`
          : 'linear-gradient(135deg, #C8D5BD, #5C7A60)',
        display: 'grid',
        placeItems: 'center',
        color: C.isDark ? C.accentInk : '#FFFFFF',
        fontWeight: 700,
        fontSize: 14,
        flexShrink: 0,
      }}
    >
      {initial}
    </div>
  );
};

// ─── Calendar (本週) ───────────────────────────────────────────

const WeekCalendar: React.FC<{
  workOrders: WorkOrder[];
  tr: (en: string, zh: string) => string;
}> = ({ workOrders, tr }) => {
  const { C } = useTheme();
  const today = new Date();
  const monday = new Date(today);
  const dow = monday.getDay() || 7; // Sun=0 → 7
  monday.setDate(monday.getDate() - (dow - 1));
  const days = Array.from({ length: 7 }).map((_, i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    return d;
  });
  const dayLabels = lang =>
    lang === 'zh' ? ['一', '二', '三', '四', '五', '六', '日'] : ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
  const labels = dayLabels(tr('en', 'zh'));

  // count work orders per day
  const counts = days.map(d => {
    const start = d.setHours(0, 0, 0, 0);
    const end = start + 86_400_000;
    return workOrders.filter(w => w.createdAt >= start && w.createdAt < end).length;
  });

  return (
    <Card>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: C.text }}>
        {tr('Calendar (this week)', '本週行程')}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 6 }}>
        {labels.map((l, i) => (
          <div key={i} style={{ fontSize: 10, color: C.sub, textAlign: 'center' }}>
            {l}
          </div>
        ))}
        {days.map((d, i) => {
          const isToday = d.toDateString() === new Date().toDateString();
          const has = counts[i] > 0;
          return (
            <div
              key={i}
              data-testid={`week-day-${i}`}
              style={{
                aspectRatio: '1 / 1',
                borderRadius: 8,
                background: isToday ? C.accentSoft : has ? C.warnSoft : C.panelMuted,
                border: isToday ? `1px solid ${C.accent}` : has ? `1px solid ${C.warn}` : 'none',
                display: 'grid',
                placeItems: 'center',
                fontSize: 12,
                fontWeight: 600,
                color: isToday ? C.accent : has ? C.warn : C.text,
                position: 'relative',
              }}
            >
              {d.getDate()}
              {has && (
                <span
                  style={{
                    position: 'absolute',
                    bottom: 2,
                    fontSize: 9,
                    fontFamily: 'JetBrains Mono, monospace',
                    color: C.warn,
                  }}
                >
                  ×{counts[i]}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
};

// ─── Technician roster ─────────────────────────────────────────

const RosterCard: React.FC<{
  technicians: Technician[];
  onToggle: (id: number) => void;
  tr: (en: string, zh: string) => string;
}> = ({ technicians, onToggle, tr }) => {
  const { C } = useTheme();
  return (
    <Card style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: C.text }}>
        {tr('Technicians', '技師排班')}
      </div>
      {technicians.length === 0 ? (
        <div style={{ fontSize: 12, color: C.sub }}>{tr('No technicians.', '暫無技師資料。')}</div>
      ) : (
        technicians.map((t, i) => (
          <div
            key={t.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '10px 0',
              borderBottom: i < technicians.length - 1 ? `1px solid ${C.border}` : undefined,
            }}
          >
            <Avatar name={t.name} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{t.name}</div>
              <div style={{ fontSize: 11, color: C.sub }}>ID #{t.id}</div>
            </div>
            <StatusPill tone={technicianStatusTone(t.status)}>
              {techStatusLabel(t.status, tr)}
            </StatusPill>
            <button
              onClick={() => onToggle(t.id)}
              disabled={t.status === TechnicianStatus.DISPATCHED}
              aria-label={tr('Toggle duty', '切換班別')}
              style={{
                background: 'transparent',
                border: `1px solid ${C.border}`,
                borderRadius: 6,
                padding: '4px 8px',
                fontSize: 11,
                color: t.status === TechnicianStatus.DISPATCHED ? C.faint : C.sub,
                cursor: t.status === TechnicianStatus.DISPATCHED ? 'not-allowed' : 'pointer',
                fontFamily: 'inherit',
              }}
            >
              {t.status === TechnicianStatus.ON_DUTY ? tr('Out', '下班') : tr('In', '上崗')}
            </button>
          </div>
        ))
      )}
    </Card>
  );
};

// ─── Work-order table ─────────────────────────────────────────

const WorkOrderTable: React.FC<{
  workOrders: WorkOrder[];
  technicians: Technician[];
  onSelect: (wo: WorkOrder) => void;
  tr: (en: string, zh: string) => string;
}> = ({ workOrders, technicians, onSelect, tr }) => {
  const { C } = useTheme();
  const techMap = useMemo(() => {
    const m = new Map<number, string>();
    technicians.forEach(t => m.set(t.id, t.name));
    return m;
  }, [technicians]);

  const cols = [
    tr('ID', '編號'),
    tr('Turbine', '風機'),
    tr('Issue', '問題'),
    tr('Tech', '技師'),
    tr('Priority', '優先'),
    tr('Status', '狀態'),
    'SLA',
  ];

  return (
    <Card padding={0}>
      <div
        style={{
          padding: '14px 18px',
          borderBottom: `1px solid ${C.border}`,
          fontSize: 14,
          fontWeight: 600,
          color: C.text,
        }}
      >
        {tr('Work orders', '工單列表')}
      </div>
      {workOrders.length === 0 ? (
        <div style={{ padding: 24, fontSize: 13, color: C.sub, textAlign: 'center' }}>
          {tr('No work orders.', '暫無工單。')}
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: C.panelMuted }}>
                {cols.map(h => (
                  <th
                    key={h}
                    style={{
                      textAlign: 'left',
                      padding: '10px 14px',
                      fontSize: 11,
                      color: C.sub,
                      fontWeight: 500,
                      letterSpacing: 0.5,
                      textTransform: 'uppercase',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {workOrders.map(wo => {
                const pri = priorityFromAge(wo.createdAt);
                const techName = wo.technicianId ? techMap.get(wo.technicianId) || '—' : '—';
                const issue = (wo.faultDescription || '').split('\n')[0].slice(0, 60) || '—';
                return (
                  <tr
                    key={wo.id}
                    onClick={() => onSelect(wo)}
                    style={{
                      borderTop: `1px solid ${C.border}`,
                      cursor: 'pointer',
                      transition: 'background 120ms ease',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = C.panelMuted)}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                  >
                    <td style={{ padding: '12px 14px', fontFamily: 'JetBrains Mono, monospace', color: C.sub }}>
                      #{wo.id.slice(-6)}
                    </td>
                    <td style={{ padding: '12px 14px', fontWeight: 600, color: C.text }}>
                      {wo.turbineName}
                    </td>
                    <td style={{ padding: '12px 14px', color: C.text, maxWidth: 320 }}>
                      <div
                        style={{
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {issue}
                      </div>
                    </td>
                    <td style={{ padding: '12px 14px', color: C.sub }}>{techName}</td>
                    <td style={{ padding: '12px 14px' }}>
                      <StatusPill tone={pri.tone}>{pri.code}</StatusPill>
                    </td>
                    <td style={{ padding: '12px 14px' }}>
                      <StatusPill tone={workOrderStatusTone(wo.status)}>
                        {statusLabel(wo.status, tr)}
                      </StatusPill>
                    </td>
                    <td
                      style={{
                        padding: '12px 14px',
                        fontFamily: 'JetBrains Mono, monospace',
                        fontSize: 11,
                        color: C.sub,
                      }}
                    >
                      {slaFromAge(wo.createdAt)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
};

// ─── Main ──────────────────────────────────────────────────────

const MaintenanceHub: React.FC<MaintenanceHubProps> = ({
  maintenanceData,
  onSelectWorkOrder,
  lang = 'zh',
}) => {
  const tr = (en: string, zh: string) => (lang === 'zh' ? zh : en);
  const { technicians, workOrders, toggleTechnicianStatus } = maintenanceData;
  const [filter, setFilter] = useState<'all' | 'open' | 'in_progress' | 'completed'>('all');

  const filtered = useMemo(() => {
    if (filter === 'all') return workOrders;
    if (filter === 'open') return workOrders.filter(w => w.status === WorkOrderStatus.OPEN);
    if (filter === 'in_progress')
      return workOrders.filter(w => w.status === WorkOrderStatus.IN_PROGRESS);
    return workOrders.filter(w => w.status === WorkOrderStatus.COMPLETED);
  }, [workOrders, filter]);

  const activeCount = workOrders.filter(w => w.status !== WorkOrderStatus.COMPLETED).length;
  const onDutyCount = technicians.filter(
    t => t.status === TechnicianStatus.ON_DUTY || t.status === TechnicianStatus.DISPATCHED,
  ).length;

  return (
    <div>
      <PageHeader
        title={tr('Maintenance Hub', '維護中心')}
        sub={tr(
          `${activeCount} active work orders · ${onDutyCount} technicians on duty`,
          `${activeCount} 張未結工單・${onDutyCount} 位技師在崗`,
        )}
        actions={
          <>
            <Select
              value={filter}
              onChange={v => setFilter(v as typeof filter)}
              options={[
                { value: 'all', label: tr('All', '全部') },
                { value: 'open', label: tr('Open', '未結') },
                { value: 'in_progress', label: tr('In progress', '處理中') },
                { value: 'completed', label: tr('Completed', '已完成') },
              ]}
              ariaLabel={tr('Filter', '篩選')}
              width={140}
            />
            <Btn variant="primary" ariaLabel={tr('New work order', '新工單')}>
              + {tr('New work order', '新工單')}
            </Btn>
          </>
        }
      />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 2fr) minmax(280px, 1fr)',
          gap: 16,
        }}
      >
        <WorkOrderTable
          workOrders={filtered}
          technicians={technicians}
          onSelect={onSelectWorkOrder}
          tr={tr}
        />
        <div>
          <RosterCard technicians={technicians} onToggle={toggleTechnicianStatus} tr={tr} />
          <WeekCalendar workOrders={workOrders} tr={tr} />
        </div>
      </div>
    </div>
  );
};

export default MaintenanceHub;
