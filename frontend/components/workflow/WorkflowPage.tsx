/**
 * WorkflowPage — `/admin/workflow/*` 主入口（WMOM-20260504-19 + -20 + -20260509-06）。
 *
 * 結構：
 *   - PageHeader：標題 + Create primary 按鈕（依 tab 切 work order / material request）
 *   - Tab 切換：orders（-19）/ material（A6）/ approval（-20）
 *   - 主內容：依 tab 切到 WorkOrderListPanel / MaterialRequestListPanel / PendingApprovalPanel
 *   - Modal：CreateWorkOrderWizard / WorkOrderDetailModal /
 *           CreateMaterialRequestWizard / MaterialRequestDetailModal / ApprovalActionDialog
 *
 * 不接 farm_id 參數 — 內部跑 /api/farms 拿 active_farm_id（與 FarmSelector 同來源）。
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Btn, Card, PageHeader, StatusPill } from '../ui';
import { useTheme } from '../../theme/ThemeProvider';
import {
  farmApi,
  type CreateWorkOrderRequest,
  type FollowupKind,
  type PendingSignoffItem,
  type SignoffLevel,
  type SignoffSubjectType,
  type WorkOrderResponse,
  type WorkOrderStatus,
} from '../../services/workOrderService';
import {
  type CreateMaterialRequestPayload,
  type MaterialRequestResponse,
  type MaterialRequestStatus,
} from '../../services/materialService';
import { type InventoryItemResponse } from '../../services/inventoryService';
import { useWorkOrders } from '../../hooks/useWorkOrders';
import { usePendingApprovals } from '../../hooks/usePendingApprovals';
import { useMaterialRequests } from '../../hooks/useMaterialRequests';
import { useInventory } from '../../hooks/useInventory';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import WorkOrderListPanel from './WorkOrderListPanel';
import CreateWorkOrderWizard from './CreateWorkOrderWizard';
import WorkOrderDetailModal from './WorkOrderDetailModal';
import PendingApprovalPanel from './PendingApprovalPanel';
import ApprovalActionDialog, { type ApprovalMode } from './ApprovalActionDialog';
import MaterialRequestListPanel from './MaterialRequestListPanel';
import CreateMaterialRequestWizard from './CreateMaterialRequestWizard';
import MaterialRequestDetailModal from './MaterialRequestDetailModal';
import InventoryListPanel from './InventoryListPanel';
import InventoryDetailDrawer from './InventoryDetailDrawer';
import InspectionScheduleListPanel from './InspectionScheduleListPanel';
import CreateInspectionScheduleModal from './CreateInspectionScheduleModal';
import InspectionScheduleDetailModal from './InspectionScheduleDetailModal';
import { useInspectionSchedules } from '../../hooks/useInspectionSchedules';
import type {
  CreateInspectionSchedulePayload,
  InspectionScheduleResponse,
} from '../../services/inspectionScheduleService';
import { type TurbineData } from '../../types';

type Lang = 'en' | 'zh';
type Tab = 'orders' | 'material' | 'inventory' | 'inspection' | 'approval';

interface Props {
  lang: Lang;
  /** 從 AppShell 傳進來的目前 farm 內 turbine 列表（給 wizard 風機選單用）。 */
  turbines: TurbineData[];
  /**
   * 深連結：從 `TurbineDetail` header『安排檢查』鈕導覽進來時帶入，直接開
   * inspection 頁籤並預先過濾該風機（WMOM-20260925-05，`WMOM-20260507-02` sub-task d）。
   * 只在 mount 時讀一次（App.tsx 切換 view 時本元件會整個 remount，見該檔案 switch
   * render 慣例），非 controlled prop。
   */
  initialInspectionTurbineId?: string;
}

const WorkflowPage: React.FC<Props> = ({ lang, turbines, initialInspectionTurbineId }) => {
  const { C } = useTheme();
  const { currentUser } = useCurrentUser();
  const ui = (en: string, zh: string) => (lang === 'zh' ? zh : en);

  // ── Active farm（單次抓 + 監聽切換 reload） ──
  const [farmId, setFarmId] = useState<string | null>(null);
  const [farmName, setFarmName] = useState<string>('');
  // WMOM-20260510-01 Part D：driving start_work weather_window 必填的 UI 邏輯
  const [farmIsOffshore, setFarmIsOffshore] = useState<boolean>(false);
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
        setFarmIsOffshore(Boolean(active?.is_offshore));
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
  const [tab, setTab] = useState<Tab>(initialInspectionTurbineId ? 'inspection' : 'orders');

  // ── Orders tab state ──
  const [statusFilter, setStatusFilter] = useState<WorkOrderStatus | 'all'>('all');
  const [search, setSearch] = useState('');

  const wo = useWorkOrders({
    farmId,
    status: statusFilter === 'all' ? undefined : statusFilter,
    search,
  });

  // ── Material tab state ──
  const [mrStatusFilter, setMrStatusFilter] = useState<MaterialRequestStatus | 'all'>('all');
  const [mrSearch, setMrSearch] = useState('');

  const mrHook = useMaterialRequests({
    farmId,
    status: mrStatusFilter === 'all' ? undefined : mrStatusFilter,
    search: mrSearch,
  });

  // ── Inventory tab state ──
  const [invWarehouse, setInvWarehouse] = useState<string | 'all'>('all');
  const [invBelowSafetyOnly, setInvBelowSafetyOnly] = useState(false);
  const [invSearch, setInvSearch] = useState('');

  const invHook = useInventory({
    farmId,
    warehouseId: invWarehouse === 'all' ? undefined : invWarehouse,
    belowSafetyOnly: invBelowSafetyOnly,
    search: invSearch,
  });

  // ── Inspection tab state ──
  const [inspTurbineId, setInspTurbineId] = useState<string | 'all'>(
    initialInspectionTurbineId ?? 'all',
  );
  const [inspActiveOnly, setInspActiveOnly] = useState(false);

  const inspHook = useInspectionSchedules({
    farmId,
    turbineId: inspTurbineId === 'all' ? undefined : inspTurbineId,
    activeOnly: inspActiveOnly,
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
  const [showMRWizard, setShowMRWizard] = useState(false);
  const [selectedWO, setSelectedWO] = useState<WorkOrderResponse | null>(null);
  const [selectedMR, setSelectedMR] = useState<MaterialRequestResponse | null>(null);
  const [selectedInvItem, setSelectedInvItem] = useState<InventoryItemResponse | null>(null);
  const [showInspWizard, setShowInspWizard] = useState(false);
  const [selectedInspSchedule, setSelectedInspSchedule] =
    useState<InspectionScheduleResponse | null>(null);
  const [schedulerMsg, setSchedulerMsg] = useState('');

  const handleRunScheduler = useCallback(async () => {
    try {
      const result = await inspHook.runScheduler();
      setSchedulerMsg(
        result.spawned.length > 0
          ? ui(`Spawned ${result.spawned.length} work order(s)`, `已建立 ${result.spawned.length} 張工單`)
          : ui('No schedules due', '目前沒有到期的計畫'),
      );
    } catch (e) {
      setSchedulerMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setTimeout(() => setSchedulerMsg(''), 4000);
    }
  }, [inspHook.runScheduler, lang]);
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

  const handleCreateMR = useCallback(
    async (req: CreateMaterialRequestPayload) => {
      await mrHook.create(req);
      setShowMRWizard(false);
    },
    [mrHook],
  );

  const handleCreateInsp = useCallback(
    async (req: Omit<CreateInspectionSchedulePayload, 'farm_id'>) => {
      await inspHook.create(req);
      setShowInspWizard(false);
    },
    [inspHook],
  );

  // 把 selected detail 維持與 list 同步（list patch 後 re-select 最新一筆）
  useEffect(() => {
    if (!selectedWO) return;
    const fresh = wo.items.find(x => x.id === selectedWO.id);
    if (fresh && fresh !== selectedWO) {
      setSelectedWO(fresh);
    }
  }, [wo.items, selectedWO]);

  // 必須讀 rawItems（未經 client-side search filter）— 否則 user 在 detail modal
  // 開啟期間打字 search，filteredItems 把該 row 過濾掉時 selectedMR 會停在 stale。
  useEffect(() => {
    if (!selectedMR) return;
    const fresh = mrHook.rawItems.find(x => x.id === selectedMR.id);
    if (fresh && fresh !== selectedMR) {
      setSelectedMR(fresh);
    }
  }, [mrHook.rawItems, selectedMR]);

  // 同上：inventory drawer 開啟期間 adjust 完成後 list 會 patch，
  // 從 rawItems sync 拿最新 row（搜尋中也不會 stale）。
  useEffect(() => {
    if (!selectedInvItem) return;
    const fresh = invHook.rawItems.find(x => x.id === selectedInvItem.id);
    if (fresh && fresh !== selectedInvItem) {
      setSelectedInvItem(fresh);
    }
  }, [invHook.rawItems, selectedInvItem]);

  // 同上：inspection detail modal 開啟期間 activate/deactivate/save 完成後 list
  // 會 patch，從 items sync 拿最新 row。
  useEffect(() => {
    if (!selectedInspSchedule) return;
    const fresh = inspHook.items.find(x => x.id === selectedInspSchedule.id);
    if (fresh && fresh !== selectedInspSchedule) {
      setSelectedInspSchedule(fresh);
    }
  }, [inspHook.items, selectedInspSchedule]);

  const turbineOptions = useMemo(
    () => turbines.map(t => ({ value: t.name, label: t.name })),
    [turbines],
  );

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
            <span style={{ fontSize: 11 }}>
              {ui('Acting as', '目前身份')}:{' '}
              <span style={{ color: C.accent, fontWeight: 600 }}>{currentUser.name}</span>
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
          ) : tab === 'material' ? (
            <Btn
              variant="primary"
              onClick={() => setShowMRWizard(true)}
              ariaLabel={ui('Create material request', '建立領料單')}
            >
              + {ui('Create material request', '建立領料單')}
            </Btn>
          ) : tab === 'inspection' ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {schedulerMsg && (
                <StatusPill tone="accent" size="sm">
                  {schedulerMsg}
                </StatusPill>
              )}
              <Btn
                onClick={handleRunScheduler}
                ariaLabel={ui('Run scheduler', '執行排程檢查')}
              >
                {ui('Run scheduler', '執行排程檢查')}
              </Btn>
              <Btn
                variant="primary"
                onClick={() => setShowInspWizard(true)}
                ariaLabel={ui('Create inspection schedule', '建立定檢計畫')}
              >
                + {ui('Create inspection schedule', '建立定檢計畫')}
              </Btn>
            </div>
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
          variant={tab === 'material' ? 'primary' : 'ghost'}
          onClick={() => setTab('material')}
          ariaLabel={ui('Material requests tab', '領料單頁籤')}
          ariaPressed={tab === 'material'}
        >
          {ui('Material requests', '領料單')}
        </Btn>
        <Btn
          variant={tab === 'inventory' ? 'primary' : 'ghost'}
          onClick={() => setTab('inventory')}
          ariaLabel={ui('Inventory tab', '庫存頁籤')}
          ariaPressed={tab === 'inventory'}
        >
          {ui('Inventory', '庫存')}
        </Btn>
        <Btn
          variant={tab === 'inspection' ? 'primary' : 'ghost'}
          onClick={() => setTab('inspection')}
          ariaLabel={ui('Inspection schedules tab', '定檢計畫頁籤')}
          ariaPressed={tab === 'inspection'}
        >
          {ui('Inspection schedules', '定檢計畫')}
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

      {tab === 'material' && (
        <MaterialRequestListPanel
          items={mrHook.items}
          total={mrHook.total}
          loading={mrHook.loading}
          error={mrHook.error}
          status={mrStatusFilter}
          onStatusChange={setMrStatusFilter}
          search={mrSearch}
          onSearchChange={setMrSearch}
          onSelect={setSelectedMR}
          onRefresh={mrHook.refresh}
          lang={lang}
        />
      )}

      {tab === 'inventory' && (
        <InventoryListPanel
          items={invHook.items}
          total={invHook.total}
          loading={invHook.loading}
          error={invHook.error}
          warehouses={invHook.warehouses}
          warehouseId={invWarehouse}
          onWarehouseChange={setInvWarehouse}
          belowSafetyOnly={invBelowSafetyOnly}
          onBelowSafetyChange={setInvBelowSafetyOnly}
          search={invSearch}
          onSearchChange={setInvSearch}
          onSelect={setSelectedInvItem}
          onRefresh={invHook.refresh}
          lang={lang}
        />
      )}

      {tab === 'inspection' && (
        <InspectionScheduleListPanel
          items={inspHook.items}
          total={inspHook.total}
          loading={inspHook.loading}
          error={inspHook.error}
          turbineOptions={turbineOptions}
          turbineId={inspTurbineId}
          onTurbineIdChange={setInspTurbineId}
          activeOnly={inspActiveOnly}
          onActiveOnlyChange={setInspActiveOnly}
          onSelect={setSelectedInspSchedule}
          onRefresh={inspHook.refresh}
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
          farmIsOffshore={farmIsOffshore}
          onClose={() => setSelectedWO(null)}
          onDispatch={(id, assigneeId) =>
            wo.dispatch(id, { actor_id: currentUser.id, assignee_id: assigneeId })
          }
          onStartWork={(id, requireWeather, weatherWindowId) =>
            wo.startWork(id, {
              require_weather_window: requireWeather,
              weather_window_id: weatherWindowId ?? null,
            })
          }
          onUpdateProgress={(id, note) =>
            wo.updateProgress(id, { actor_id: currentUser.id, note })
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

      {showMRWizard && (
        <CreateMaterialRequestWizard
          farmId={farmId}
          requesterId={currentUser.id}
          workOrders={wo.items}
          onClose={() => setShowMRWizard(false)}
          onSubmit={handleCreateMR}
          lang={lang}
        />
      )}

      {selectedMR && (
        <MaterialRequestDetailModal
          materialRequest={selectedMR}
          onSubmitForApproval={(id, actorId) =>
            mrHook.submitForApproval(id, { actor_id: actorId })
          }
          onDispatch={(id, actorId) => mrHook.dispatch(id, { actor_id: actorId })}
          onReceive={(id, actorId, actual) =>
            mrHook.receive(id, { actor_id: actorId, actual_quantities: actual })
          }
          onClose={(id, actorId) => mrHook.close(id, { actor_id: actorId })}
          onCancel={(id, actorId, reason) =>
            mrHook.cancel(id, { actor_id: actorId, cancel_reason: reason })
          }
          onCreateReturn={async (id, payload) => {
            await mrHook.createReturn(id, payload);
            await mrHook.refresh();
          }}
          onCloseModal={() => setSelectedMR(null)}
          lang={lang}
        />
      )}

      {selectedInvItem && (
        <InventoryDetailDrawer
          item={selectedInvItem}
          onAdjust={invHook.adjust}
          loadAdjustments={invHook.listAdjustments}
          onClose={() => setSelectedInvItem(null)}
          lang={lang}
        />
      )}

      {showInspWizard && (
        <CreateInspectionScheduleModal
          turbineOptions={turbineOptions}
          preselectTurbineId={
            inspTurbineId === 'all' ? initialInspectionTurbineId : inspTurbineId
          }
          onClose={() => setShowInspWizard(false)}
          onSubmit={handleCreateInsp}
          lang={lang}
        />
      )}

      {selectedInspSchedule && (
        <InspectionScheduleDetailModal
          schedule={selectedInspSchedule}
          onClose={() => setSelectedInspSchedule(null)}
          onUpdate={inspHook.updateMetadata}
          onActivate={inspHook.activate}
          onDeactivate={inspHook.deactivate}
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
              actor_id: currentUser.id,
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
              actor_id: currentUser.id,
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
