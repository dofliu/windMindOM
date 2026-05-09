/**
 * WorkflowPage — `/admin/workflow/*` 主入口（WMOM-20260504-19 + -20）。
 *
 * 結構：
 *   - PageHeader：標題 + Create work order primary 按鈕
 *   - Tab 切換：orders（-19）/ approval（-20）
 *   - 主內容：依 tab 切到 WorkOrderListPanel 或 PendingApprovalPanel
 *   - Modal：CreateWorkOrderWizard / WorkOrderDetailModal / ApprovalActionDialog
 *
 * 不接 farm_id 參數 — 內部跑 /api/farms 拿 active_farm_id（與 FarmSelector 同來源）。
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Btn, Card, PageHeader, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  DEV_ACTOR_ID,
  farmApi,
  type CreateWorkOrderRequest,
  type FollowupKind,
  type PendingSignoffItem,
  type SignoffLevel,
  type SignoffSubjectType,
  type WorkOrderResponse,
  type WorkOrderStatus,
} from '../../services/workOrderService';
import { useWorkOrders } from '../../hooks/useWorkOrders';
import { usePendingApprovals } from '../../hooks/usePendingApprovals';
import WorkOrderListPanel from './WorkOrderListPanel';
import CreateWorkOrderWizard from './CreateWorkOrderWizard';
import WorkOrderDetailModal from './WorkOrderDetailModal';
import PendingApprovalPanel from './PendingApprovalPanel';
import ApprovalActionDialog, { type ApprovalMode } from './ApprovalActionDialog';
import { type TurbineData } from '../../types';

type Lang = 'en' | 'zh';
type Tab = 'orders' | 'approval';

interface Props {
  lang: Lang;
  /** 從 AppShell 傳進來的目前 farm 內 turbine 列表（給 wizard 風機選單用）。 */
  turbines: TurbineData[];
}

const WorkflowPage: React.FC<Props> = ({ lang, turbines }) => {
  const { C } = useTheme();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  // ── Active farm（單次抓 + 監聽切換 reload） ──
  const [farmId, setFarmId] = useState<string | null>(null);
  const [farmName, setFarmName] = useState<string>('');
  const [farmFetchError, setFarmFetchError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await farmApi.list();
        if (cancelled) return;
        setFarmId(resp.active_farm_id);
        const active = resp.farms.find(f => f.farm_id === resp.active_farm_id);
        setFarmName(active?.name ?? '');
      } catch (e) {
        if (cancelled) return;
        setFarmFetchError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Tab state ──
  const [tab, setTab] = useState<Tab>('orders');

  // ── Orders tab state ──
  const [statusFilter, setStatusFilter] = useState<WorkOrderStatus | 'all'>('all');
  const [search, setSearch] = useState('');

  const wo = useWorkOrders({
    farmId,
    status: statusFilter === 'all' ? undefined : statusFilter,
    search,
  });

  // ── Approval tab state ──
  const [signoffLevel, setSignoffLevel] = useState<SignoffLevel>('leader');
  const [subjectTypeFilter, setSubjectTypeFilter] = useState<SignoffSubjectType | 'all'>('all');

  const approvals = usePendingApprovals({
    farmId,
    level: signoffLevel,
    subjectType: subjectTypeFilter === 'all' ? undefined : subjectTypeFilter,
  });

  // ── Modals ──
  const [showWizard, setShowWizard] = useState(false);
  const [selectedWO, setSelectedWO] = useState<WorkOrderResponse | null>(null);
  const [approvalAction, setApprovalAction] = useState<{
    mode: ApprovalMode;
    pending: PendingSignoffItem;
  } | null>(null);

  const handleCreate = useCallback(
    async (req: CreateWorkOrderRequest) => {
      await wo.create(req);
      setShowWizard(false);
    },
    [wo],
  );

  // 把 selected detail 維持與 list 同步（list patch 後 re-select 最新一筆）
  useEffect(() => {
    if (!selectedWO) return;
    const fresh = wo.items.find(x => x.id === selectedWO.id);
    if (fresh && fresh !== selectedWO) {
      setSelectedWO(fresh);
    }
  }, [wo.items, selectedWO]);

  // ── No farm fallback ──
  if (farmFetchError) {
    return (
      <>
        <PageHeader
          title={ui('Workflow', '工單管理')}
          sub={ui('Work orders & approvals', '工單與簽核')}
        />
        <Card tone="warn" padding={20}>
          <div style={{ color: C.warn, fontSize: 13 }}>
            ⚠ {ui('Failed to load active farm:', '無法載入目前風場：')} {farmFetchError}
          </div>
        </Card>
      </>
    );
  }

  if (!farmId) {
    return (
      <>
        <PageHeader
          title={ui('Workflow', '工單管理')}
          sub={ui('Work orders & approvals', '工單與簽核')}
        />
        <Card tone="muted" padding={20}>
          <div style={{ color: C.faint, fontSize: 13, textAlign: 'center' }}>
            {ui(
              'Loading active farm… If this persists, create or activate a farm in the sidebar.',
              '載入風場中…若持續顯示，請從左側選單建立或啟用風場。',
            )}
          </div>
        </Card>
      </>
    );
  }

  const pendingCount = approvals.total;

  return (
    <>
      <PageHeader
        title={ui('Workflow', '工單管理')}
        sub={
          <span>
            {ui('Active farm', '目前風場')}:{' '}
            <span style={{ color: C.accent, fontWeight: 600 }}>{farmName || farmId}</span>
            {' · '}
            <span style={{ fontSize: 11, fontFamily: 'JetBrains Mono, monospace' }}>
              actor {DEV_ACTOR_ID.slice(0, 8)}…
            </span>
          </span>
        }
        actions={
          tab === 'orders' ? (
            <Btn
              variant="primary"
              onClick={() => setShowWizard(true)}
              ariaLabel={ui('Create work order', '建立工單')}
            >
              + {ui('Create work order', '建立工單')}
            </Btn>
          ) : null
        }
      />

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
        <Btn
          variant={tab === 'orders' ? 'primary' : 'ghost'}
          onClick={() => setTab('orders')}
          ariaLabel={ui('Work orders tab', '工單頁籤')}
          ariaPressed={tab === 'orders'}
        >
          {ui('Work orders', '工單')}
        </Btn>
        <Btn
          variant={tab === 'approval' ? 'primary' : 'ghost'}
          onClick={() => setTab('approval')}
          ariaLabel={ui('Approval tab', '簽核頁籤')}
          ariaPressed={tab === 'approval'}
        >
          {ui('Approval', '簽核')}
          {pendingCount > 0 && (
            <StatusPill tone="amber" size="sm" style={{ marginLeft: 6 }}>
              {pendingCount}
            </StatusPill>
          )}
        </Btn>
      </div>

      {tab === 'orders' && (
        <WorkOrderListPanel
          items={wo.items}
          total={wo.total}
          loading={wo.loading}
          error={wo.error}
          status={statusFilter}
          onStatusChange={setStatusFilter}
          search={search}
          onSearchChange={setSearch}
          onSelect={setSelectedWO}
          onRefresh={wo.refresh}
          lang={lang}
        />
      )}

      {tab === 'approval' && (
        <PendingApprovalPanel
          items={approvals.items}
          total={approvals.total}
          loading={approvals.loading}
          error={approvals.error}
          level={signoffLevel}
          onLevelChange={setSignoffLevel}
          subjectType={subjectTypeFilter}
          onSubjectTypeChange={setSubjectTypeFilter}
          workOrderCache={approvals.workOrderCache}
          onApproveClick={pending => setApprovalAction({ mode: 'approve', pending })}
          onRejectClick={pending => setApprovalAction({ mode: 'reject', pending })}
          onRefresh={approvals.refresh}
          lang={lang}
        />
      )}

      {showWizard && (
        <CreateWorkOrderWizard
          farmId={farmId}
          turbines={turbines}
          onClose={() => setShowWizard(false)}
          onSubmit={handleCreate}
          lang={lang}
        />
      )}

      {selectedWO && (
        <WorkOrderDetailModal
          workOrder={selectedWO}
          onClose={() => setSelectedWO(null)}
          onDispatch={id => wo.dispatch(id, { actor_id: DEV_ACTOR_ID })}
          onStartWork={(id, requireWeather) =>
            wo.startWork(id, { require_weather_window: requireWeather })
          }
          onUpdateProgress={(id, note) =>
            wo.updateProgress(id, { actor_id: DEV_ACTOR_ID, note })
          }
          onFinish={(id, payload) =>
            wo.finish(id, {
              actual_hours: payload.actual_hours,
              followup_kind: payload.followup_kind as FollowupKind,
              work_summary: payload.work_summary,
              unfinished_items: payload.unfinished_items,
              followup_note: payload.followup_note,
            })
          }
          onReject={(id, reject_reason) => wo.reject(id, { reject_reason })}
          onCancel={(id, cancel_reason) => wo.cancel(id, { cancel_reason })}
          onReopen={(id, reopen_reason) => wo.reopen(id, { reopen_reason })}
          lang={lang}
        />
      )}

      {approvalAction && (
        <ApprovalActionDialog
          mode={approvalAction.mode}
          pending={approvalAction.pending}
          workOrder={
            approvalAction.pending.chain.subject_type === 'work_order'
              ? approvals.workOrderCache.get(approvalAction.pending.chain.subject_id) ?? null
              : null
          }
          onClose={() => setApprovalAction(null)}
          onApprove={async (stepId, comment) => {
            const result = await approvals.approve(stepId, {
              actor_id: DEV_ACTOR_ID,
              comment,
            });
            // approve 完成可能讓 chain 結案 → 若是工單 subject 且 closed，list 也要重 fetch
            if (result.subject_status_changed) {
              wo.refresh();
            }
            return result;
          }}
          onReject={async (stepId, reason) => {
            const result = await approvals.reject(stepId, {
              actor_id: DEV_ACTOR_ID,
              reason,
            });
            // reject 會把工單 IN_PROGRESS 回退 → 同步 orders list
            if (result.subject_status_changed) {
              wo.refresh();
            }
            return result;
          }}
          lang={lang}
        />
      )}
    </>
  );
};

export default WorkflowPage;
