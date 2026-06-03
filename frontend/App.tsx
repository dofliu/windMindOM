/**
 * windMindOM 前端入口（A · Calm Operator 改版後）。
 *
 * 變更：
 *   - 頂部 header 拆掉，改為左側 220px Sidebar
 *   - 主題改走 ThemeProvider（light = 鼠尾草綠 / dark = 翡翠玻璃）
 *   - 5 主頁 nav：overview / turbine / maintenance / cost / history
 *   - 2 工具 nav：faults（含未結 badge）/ settings
 *
 * **API / 資料流不動**：所有 hooks（useMockTurbineData / useRealtimeData /
 * useMaintenanceData / useI18n / useSettings）以及 Modal 流程都保留原本連線。
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useMockTurbineData } from './hooks/useMockTurbineData';
import { useRealtimeData } from './hooks/useRealtimeData';
import { useMaintenanceData } from './hooks/useMaintenanceData';
import { useI18n } from './hooks/useI18n';
import { useSettings } from './hooks/useSettings';
import {
  type TurbineData,
  TurbineStatus,
  DataSourceType,
  type WorkOrder,
  WorkOrderStatus,
} from './types';
import FarmOverview from './components/FarmOverview';
import TurbineDetail from './components/TurbineDetail';
import MaintenanceHub from './components/MaintenanceHub';
import FaultInjectionPanel from './components/FaultInjectionPanel';
import DispatchModal from './components/DispatchModal';
import WorkOrderDetailModal from './components/WorkOrderDetailModal';
import SettingsPage from './components/SettingsPage';
import HistoryPage from './components/HistoryPage';
import FarmSelector from './components/FarmSelector';
import UserSwitcher from './components/UserSwitcher';
import CostPage from './components/CostPage';
import WorkflowPage from './components/workflow/WorkflowPage';
import ReportsPage from './components/reporting/ReportsPage';
import FieldPage from './components/field/FieldPage';
import { ThemeProvider, useTheme } from './theme/ThemeProvider';
import { UserProvider } from './hooks/useCurrentUser';
import { Sidebar, type NavItem } from './components/ui';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

type ViewId =
  | 'overview'
  | 'turbine'
  | 'maintenance'
  | 'workflow'
  | 'history'
  | 'cost'
  | 'reports'
  | 'field'
  | 'faults'
  | 'settings';

const PRIMARY_NAV: NavItem[] = [
  { id: 'overview', iconId: 'overview', labelEn: 'Farm Overview', labelZh: '風場總覽' },
  { id: 'turbine', iconId: 'turbine', labelEn: 'Turbine Detail', labelZh: '風機細節' },
  { id: 'maintenance', iconId: 'maintenance', labelEn: 'Maintenance', labelZh: '維護中心' },
  { id: 'workflow', iconId: 'workflow', labelEn: 'Workflow', labelZh: '工單管理' },
  { id: 'cost', iconId: 'cost', labelEn: 'Cost Model', labelZh: '成本模型' },
  { id: 'reports', iconId: 'reports', labelEn: 'Reports', labelZh: '報表' },
  { id: 'history', iconId: 'history', labelEn: 'History', labelZh: '歷史資料' },
];

const SECONDARY_NAV: NavItem[] = [
  { id: 'field', iconId: 'field', labelEn: 'Field', labelZh: '現場查詢' },
  { id: 'faults', iconId: 'faults', labelEn: 'Faults', labelZh: '故障模擬' },
  { id: 'settings', iconId: 'settings', labelEn: 'Settings', labelZh: '設定' },
];

const AppShell: React.FC = () => {
  const { C } = useTheme();
  const { settings, saveSettings } = useSettings();
  const { lang, setLang } = useI18n();

  // ── Data hooks（不動 API） ──
  const mockData = useMockTurbineData();
  const realtimeData = useRealtimeData();
  const useMock = settings.dataSource === DataSourceType.MOCK;
  const { turbines, updateTurbineStatus } = useMock ? mockData : realtimeData;
  const maintenance = useMaintenanceData();
  const { workOrders } = maintenance;

  // ── View state ──
  const [view, setView] = useState<ViewId>('overview');
  const [selectedTurbine, setSelectedTurbine] = useState<TurbineData | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // ── Modals ──
  const [isDispatchModalOpen, setIsDispatchModalOpen] = useState(false);
  const [turbineToDispatch, setTurbineToDispatch] = useState<TurbineData | null>(null);
  const [faultAnalysisForDispatch, setFaultAnalysisForDispatch] = useState('');
  const [selectedWorkOrder, setSelectedWorkOrder] = useState<WorkOrder | null>(null);

  // ── Backend health (poll /api/farms 一次) ──
  const [backendHealthy, setBackendHealthy] = useState<boolean>(true);
  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/farms`);
        if (!cancelled) setBackendHealthy(res.ok);
      } catch {
        if (!cancelled) setBackendHealthy(false);
      }
    };
    check();
    const id = setInterval(check, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // ── Nav handlers ──
  const handleSelectTurbine = useCallback((turbine: TurbineData) => {
    setSelectedTurbine(turbine);
    setView('turbine');
  }, []);

  const handleBackToOverview = useCallback(() => {
    setSelectedTurbine(null);
    setView('overview');
  }, []);

  const handleNavSelect = useCallback(
    (id: string) => {
      const next = id as ViewId;
      setView(next);
      if (next === 'turbine') {
        if (!selectedTurbine && turbines.length > 0) {
          setSelectedTurbine(turbines[0]);
        }
      } else if (next === 'overview') {
        setSelectedTurbine(null);
      }
    },
    [selectedTurbine, turbines],
  );

  // 把 selectedTurbine 同步到 turbines 的最新版本
  const liveTurbine = useMemo(() => {
    if (!selectedTurbine) return null;
    return turbines.find(t => t.id === selectedTurbine.id) || selectedTurbine;
  }, [selectedTurbine, turbines]);

  // ── Modal handlers (不動 API) ──
  const handleOpenDispatchModal = useCallback((turbine: TurbineData, faultAnalysis: string) => {
    setTurbineToDispatch(turbine);
    setFaultAnalysisForDispatch(faultAnalysis);
    setIsDispatchModalOpen(true);
  }, []);

  const handleCloseDispatchModal = useCallback(() => {
    setIsDispatchModalOpen(false);
    setTurbineToDispatch(null);
    setFaultAnalysisForDispatch('');
  }, []);

  const handleConfirmDispatch = useCallback(
    (turbineId: number, technicianId: number, faultDescription: string) => {
      maintenance.createWorkOrder(
        turbineId,
        turbines.find(t => t.id === turbineId)?.name || '',
        faultDescription,
        technicianId,
      );
      handleCloseDispatchModal();
    },
    [maintenance, turbines, handleCloseDispatchModal],
  );

  const handleCompleteWorkOrder = useCallback(
    (workOrder: WorkOrder) => {
      maintenance.updateWorkOrder(workOrder.id, {
        status: WorkOrderStatus.COMPLETED,
        notes: workOrder.notes,
        photos: workOrder.photos,
      });
      updateTurbineStatus(workOrder.turbineId, TurbineStatus.IDLE);
      setSelectedWorkOrder(null);
    },
    [maintenance, updateTurbineStatus],
  );

  // ── Active nav id（faults 帶 badge） ──
  const faultCount = useMemo(
    () => turbines.filter(t => t.status === TurbineStatus.FAULT).length,
    [turbines],
  );
  const activeNavId: string = view;

  const primaryNav: NavItem[] = PRIMARY_NAV;
  const secondaryNav: NavItem[] = useMemo(
    () =>
      SECONDARY_NAV.map(n =>
        n.id === 'faults' && faultCount > 0 ? { ...n, badge: faultCount } : n,
      ),
    [faultCount],
  );

  // ── Render content ──
  const renderContent = () => {
    switch (view) {
      case 'overview':
        return (
          <FarmOverview
            turbines={turbines}
            onSelectTurbine={handleSelectTurbine}
            settings={settings}
            lang={lang}
          />
        );
      case 'turbine':
        if (!liveTurbine) {
          return (
            <div style={{ color: C.sub, padding: 40, textAlign: 'center' }}>
              {lang === 'zh' ? '尚未選擇風機。' : 'No turbine selected.'}
            </div>
          );
        }
        return (
          <TurbineDetail
            turbine={liveTurbine}
            onBack={handleBackToOverview}
            onDispatch={handleOpenDispatchModal}
            activeWorkOrder={workOrders.find(
              wo => wo.turbineId === liveTurbine.id && wo.status !== WorkOrderStatus.COMPLETED,
            )}
            lang={lang}
          />
        );
      case 'maintenance':
        return (
          <MaintenanceHub
            maintenanceData={maintenance}
            onSelectWorkOrder={wo => setSelectedWorkOrder(wo)}
          />
        );
      case 'workflow':
        return <WorkflowPage lang={lang} turbines={turbines} />;
      case 'history':
        return <HistoryPage turbines={turbines} lang={lang} />;
      case 'cost':
        return <CostPage lang={lang} />;
      case 'reports':
        return <ReportsPage lang={lang} />;
      case 'field':
        return <FieldPage lang={lang} />;
      case 'faults':
        return <FaultInjectionPanel lang={lang} />;
      case 'settings':
        return <SettingsPage settings={settings} onSave={saveSettings} lang={lang} />;
      default:
        return null;
    }
  };

  return (
    <div
      style={{
        background: C.bg,
        color: C.text,
        minHeight: '100vh',
        fontFamily: 'Manrope, system-ui, sans-serif',
        display: 'flex',
        alignItems: 'stretch',
      }}
    >
      <Sidebar
        primary={primaryNav}
        secondary={secondaryNav}
        activeId={activeNavId}
        onSelect={handleNavSelect}
        lang={lang}
        onToggleLang={() => setLang(lang === 'zh' ? 'en' : 'zh')}
        backendHealthy={backendHealthy}
        mobileOpen={mobileMenuOpen}
        onMobileClose={() => setMobileMenuOpen(false)}
        footerExtra={
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <FarmSelector lang={lang} />
            <UserSwitcher lang={lang} />
          </div>
        }
      />

      <main
        style={{
          flex: 1,
          minWidth: 0,
          padding: '28px 36px',
        }}
      >
        {/* Mobile menu toggle */}
        <button
          onClick={() => setMobileMenuOpen(true)}
          aria-label={lang === 'zh' ? '開啟選單' : 'Open menu'}
          style={{
            display: 'none',
            background: C.panel,
            border: `1px solid ${C.border}`,
            color: C.text,
            borderRadius: 8,
            padding: '6px 10px',
            marginBottom: 16,
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
          className="wmom-mobile-menu-btn"
        >
          ☰
        </button>
        <style>{`
          @media (max-width: 767px) {
            .wmom-mobile-menu-btn { display: inline-flex !important; }
          }
        `}</style>

        {renderContent()}
      </main>

      {isDispatchModalOpen && turbineToDispatch && (
        <DispatchModal
          turbine={turbineToDispatch}
          technicians={maintenance.technicians}
          faultAnalysis={faultAnalysisForDispatch}
          onClose={handleCloseDispatchModal}
          onConfirm={handleConfirmDispatch}
        />
      )}

      {selectedWorkOrder && (
        <WorkOrderDetailModal
          workOrder={selectedWorkOrder}
          technicians={maintenance.technicians}
          onClose={() => setSelectedWorkOrder(null)}
          onUpdate={maintenance.updateWorkOrder}
          onComplete={handleCompleteWorkOrder}
        />
      )}
    </div>
  );
};

const App: React.FC = () => (
  <ThemeProvider>
    <UserProvider>
      <AppShell />
    </UserProvider>
  </ThemeProvider>
);

export default App;
