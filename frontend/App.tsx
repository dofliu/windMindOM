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
import ScenarioPage from './components/ScenarioPage';
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
import GuidedTourPage from './components/tour/GuidedTourPage';
import { ThemeProvider, useTheme } from './theme/ThemeProvider';
import { UserProvider } from './hooks/useCurrentUser';
import { AuthProvider, useAuth } from './hooks/useAuth';
import LoginPage from './components/LoginPage';
import SourceSelectPage, { type SourceCardId } from './components/SourceSelectPage';
import { Btn, Sidebar, type NavItem } from './components/ui';
import { dataSourceLabel, parseActiveFarm, type ActiveFarmLite } from './utils/farmHeader';
import { sourceCardToMode } from './utils/sourceMode';
import { useSourceGate, type SourceMode, type SelectResult } from './hooks/useSourceGate';
import { authFetch } from './services/authClient';
import { ScenarioMountProvider, useScenarioMount } from './contexts/ScenarioMountContext';
import { type ScenarioMountRequest } from './components/ScenarioDetail';
import { wtIdToTurbineIndex } from './utils/turbineNaming';

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
  | 'scenario'
  | 'faults'
  | 'tour'
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
  { id: 'scenario', iconId: 'scenario', labelEn: 'Scenario', labelZh: '情境模擬' },
  { id: 'field', iconId: 'field', labelEn: 'Field', labelZh: '現場查詢' },
  { id: 'faults', iconId: 'faults', labelEn: 'Faults', labelZh: '故障模擬' },
  { id: 'tour', iconId: 'tour', labelEn: 'Guided Tour', labelZh: '情境導覽' },
  { id: 'settings', iconId: 'settings', labelEn: 'Settings', labelZh: '設定' },
];

/**
 * Sidebar footer 的登入狀態 chip（WMOM-20260716-05f-b）。
 * 已登入 → 顯示身分 + 登出；未登入 → 顯示「登入」鈕（開 overlay）。
 * 與 dev 的 UserSwitcher 並存（過渡期：token 走真登入、body actor_id 走 switcher）。
 */
const LoginStatus: React.FC<{ lang: 'zh' | 'en' }> = ({ lang }) => {
  const { C } = useTheme();
  const auth = useAuth();
  const t = (zh: string, en: string) => (lang === 'zh' ? zh : en);
  if (auth.isAuthenticated && auth.actor) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
        <span
          title={`${auth.actor.name}（${auth.actor.role}）`}
          style={{
            flex: 1,
            minWidth: 0,
            color: C.sub,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {t('登入：', 'As: ')}
          <span style={{ color: C.text, fontWeight: 600 }}>{auth.actor.name}</span>
        </span>
        <Btn size="sm" variant="ghost" onClick={auth.logout} ariaLabel={t('登出', 'Sign out')}>
          {t('登出', 'Sign out')}
        </Btn>
      </div>
    );
  }
  return (
    <Btn
      size="sm"
      variant="secondary"
      fullWidth
      onClick={auth.openLogin}
      ariaLabel={t('登入', 'Sign in')}
    >
      {t('登入', 'Sign in')}
    </Btn>
  );
};

const AppShell: React.FC = () => {
  const { C } = useTheme();
  const { settings, saveSettings } = useSettings();
  const { lang, setLang } = useI18n();
  const auth = useAuth();

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
  // `TurbineDetail` header『安排檢查』鈕深連結（WMOM-20260925-05）：帶入的
  // turbine_id 只在下一次 `view === 'workflow'` mount 時讀一次（見 WorkflowPage
  // `initialInspectionTurbineId` prop docstring），故不需要在切走後清空。
  const [inspectionDeepLinkTurbineId, setInspectionDeepLinkTurbineId] = useState<
    string | undefined
  >(undefined);

  // ── 情境掛載（PR C Phase 1，DEC-20260926-01 / WMOM-20260926-03）──
  // 有值時 FarmOverview/TurbineDetail 改吃該情境的凍結快照（不即時更新），與是否有
  // live/simulation 在跑正交。
  const scenarioMount = useScenarioMount();
  const effectiveTurbines = scenarioMount.mounted ? scenarioMount.turbines : turbines;
  // 「以此情境瀏覽機組細節」入口：情境資料是非同步 fetch，掛載當下還選不到目標機組，
  // 記下想選的 turbine id（TurbineData.id，由 WT{n} 換算），資料到位後由下方 effect 補選。
  const [pendingMountTurbineDataId, setPendingMountTurbineDataId] = useState<number | null>(null);
  useEffect(() => {
    if (pendingMountTurbineDataId === null || scenarioMount.loading) return;
    const match = scenarioMount.turbines.find(t => t.id === pendingMountTurbineDataId);
    if (match) {
      setSelectedTurbine(match);
      setView('turbine');
    }
    setPendingMountTurbineDataId(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingMountTurbineDataId, scenarioMount.turbines, scenarioMount.loading]);

  const handleMountScenario = useCallback(
    (request: ScenarioMountRequest) => {
      scenarioMount.mount({ id: request.scenarioId, name: request.scenarioName });
      if (request.target === 'turbine' && request.turbineWtId) {
        const wtIndex = wtIdToTurbineIndex(request.turbineWtId);
        setSelectedTurbine(null);
        setPendingMountTurbineDataId(wtIndex);
        setView('overview'); // 資料到位前先停在總覽，避免「尚未選擇風機」空畫面閃一下
      } else {
        // code review should-fix：先前這裡沒清 pendingMountTurbineDataId——若使用者先點了
        // 「瀏覽機組細節」（設下 pending id）又在資料到位前改點「瀏覽總覽」，上方 effect
        // 稍後仍會找到該 id 並強制導去 TurbineDetail，蓋掉使用者最後一次「總覽」的選擇。
        setPendingMountTurbineDataId(null);
        setSelectedTurbine(null);
        setView('overview');
      }
    },
    [scenarioMount],
  );

  // ── Modals ──
  const [isDispatchModalOpen, setIsDispatchModalOpen] = useState(false);
  const [turbineToDispatch, setTurbineToDispatch] = useState<TurbineData | null>(null);
  const [faultAnalysisForDispatch, setFaultAnalysisForDispatch] = useState('');
  const [selectedWorkOrder, setSelectedWorkOrder] = useState<WorkOrder | null>(null);

  // ── Backend health + active farm (poll /api/farms) ──
  // 同一支 /api/farms 順便取當前風場 → header 顯示（#3 狀態可見性，避免另開 fetch）。
  const [backendHealthy, setBackendHealthy] = useState<boolean>(true);
  const [activeFarm, setActiveFarm] = useState<ActiveFarmLite | null>(null);
  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      let res: Response;
      try {
        res = await authFetch(`${API_BASE}/api/farms`);
      } catch {
        if (!cancelled) setBackendHealthy(false);
        return;
      }
      if (cancelled) return;
      setBackendHealthy(res.ok);
      if (!res.ok) return;
      // farm-strip 資料解析獨立包一層 → 其失敗不可反過來把健康的後端標成不健康。
      try {
        setActiveFarm(parseActiveFarm(await res.json()));
      } catch {
        /* farm strip 資料解析失敗，維持 backendHealthy=res.ok，strip 不更新 */
      }
    };
    check();
    const id = setInterval(check, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // ── 資料來源選擇 gate（WMOM-20260719-04/-05, DEC-20260719-01 #3）──
  // 後端開機 idle（不自動起來源）。狀態機抽到 useSourceGate（可測 + 含登出防呆）。
  const { sourceActive, selectMode } = useSourceGate(auth.isAuthenticated);
  const handleSelectSource = async (id: SourceCardId): Promise<SelectResult> => {
    // id→mode 抽到 utils/sourceMode 的純函式（可測 + 涵蓋全 4 卡）：'scenario' 卡→scenario（simulator
    // 供批次、不自由跑，DEC-20260720-01 PR B）、simulation→simulation（自由跑）、observe→view、live→live。
    const mode: SourceMode = sourceCardToMode(id);
    const targetView: ViewId = id === 'scenario' || id === 'observe' ? 'scenario' : 'overview';
    const result = await selectMode(mode);
    if (result.ok) setView(targetView);
    return result; // 交回 SourceSelectPage 顯示失敗回饋（如 403）
  };

  // 資料來源標籤（header 顯示）——用涵蓋全 4 值的 lookup（見 utils/farmHeader）。
  const dsLabel = dataSourceLabel(settings.dataSource, lang);

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
    (id: string, opts?: { inspectionTurbineId?: string }) => {
      const next = id as ViewId;
      setView(next);
      if (next === 'turbine') {
        if (!selectedTurbine && effectiveTurbines.length > 0) {
          setSelectedTurbine(effectiveTurbines[0]);
        }
      } else if (next === 'overview') {
        setSelectedTurbine(null);
      }
      // 情境掛載的離開機制（PR C Phase 1，WMOM-20260926-03）：導覽到 overview/turbine 以外
      // 的任何頁面都清空 context——這是正確性/資訊安全要求（避免使用者切頁後仍背景殘留掛載
      // 中的凍結情境資料、混淆即時/回放），不是可省略的既有慣例（比照下方深連結欄位不同，
      // 見 ScenarioMountContext docstring）。overview↔turbine 之間互相導覽不清空。
      if (next !== 'overview' && next !== 'turbine') {
        scenarioMount.unmount();
      }
      // 深連結過濾只在明確帶 `opts.inspectionTurbineId` 時才設（`onNavigateInspection`
      // 呼叫點），其餘所有一般導覽（含 sidebar 直接點擊、`onNavigateReports` 等零參數
      // 呼叫）一律清空——單一 `setState` 呼叫、依當次呼叫的 `opts` 決定值，不再依賴
      // 「呼叫端要記得用對的順序呼叫兩個各自獨立的 setState」這種容易寫反的隱性
      // 前提（WMOM-20260925-05 code review 抓到的 must-fix：原本用「先設值、再讓
      // 這裡蓋回 undefined，靠呼叫端事後再設一次」的寫法，同一個 event handler 內
      // React state 更新會 batch，呼叫順序寫反時最終值恆為 undefined，深連結整個
      // 是 no-op）。
      setInspectionDeepLinkTurbineId(opts?.inspectionTurbineId);
    },
    [selectedTurbine, effectiveTurbines, scenarioMount],
  );

  // 把 selectedTurbine 同步到目前有效資料源的最新版本——情境掛載中須比對
  // `mountedScenarioData.turbines`（凍結快照），不能落回即時 `turbines`，否則會在有 banner
  // 標示「唯讀回放」的畫面上悄悄顯示真正即時的資料（見 id 與 WT{n} 命名共用的碰撞風險，
  // `DisabledOperatorControlCard` docstring 有詳述同一個風險）。
  const liveTurbine = useMemo(() => {
    if (!selectedTurbine) return null;
    return effectiveTurbines.find(t => t.id === selectedTurbine.id) || selectedTurbine;
  }, [selectedTurbine, effectiveTurbines]);

  // ── Modal handlers (不動 API) ──
  const handleOpenDispatchModal = useCallback(
    (turbine: TurbineData, faultAnalysis: string) => {
      // code review nice-to-have：派遣屬於「所有寫入操作一律 disabled」清單內，目前唯一入口
      // （AIDiagnosisCard 的派遣鈕）已在 TurbineDetail.tsx disabled，這裡加一道獨立防線——
      // 不依賴呼叫端自律，避免未來新增的派遣入口忘記檢查 mounted 就悄悄對即時風機派工。
      if (scenarioMount.mounted) return;
      setTurbineToDispatch(turbine);
      setFaultAnalysisForDispatch(faultAnalysis);
      setIsDispatchModalOpen(true);
    },
    [scenarioMount.mounted],
  );

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
            turbines={effectiveTurbines}
            onSelectTurbine={handleSelectTurbine}
            settings={settings}
            lang={lang}
            onNavigateReports={() => handleNavSelect('reports')}
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
            // 情境掛載中不對照即時工單——scenario turbine id 與 live turbine id 共用同一套
            // 編號（皆 index+1），照常比對會把某張真實在途工單顯示在「唯讀回放」的畫面上，
            // 是與 DisabledOperatorControlCard 同款的 id 碰撞風險（工單概念本身也不在
            // Phase 1 範圍內，見 issue「範圍邊界」）。
            activeWorkOrder={
              scenarioMount.mounted
                ? undefined
                : workOrders.find(
                    wo => wo.turbineId === liveTurbine.id && wo.status !== WorkOrderStatus.COMPLETED,
                  )
            }
            lang={lang}
            onNavigateInspection={turbineId =>
              handleNavSelect('workflow', { inspectionTurbineId: turbineId })
            }
          />
        );
      case 'maintenance':
        return (
          <MaintenanceHub
            maintenanceData={maintenance}
            onSelectWorkOrder={wo => setSelectedWorkOrder(wo)}
            turbines={turbines}
            lang={lang}
          />
        );
      case 'workflow':
        return (
          <WorkflowPage
            lang={lang}
            turbines={turbines}
            initialInspectionTurbineId={inspectionDeepLinkTurbineId}
          />
        );
      case 'history':
        return <HistoryPage turbines={turbines} lang={lang} />;
      case 'cost':
        return <CostPage lang={lang} />;
      case 'reports':
        return <ReportsPage lang={lang} />;
      case 'field':
        return <FieldPage lang={lang} />;
      case 'scenario':
        return (
          <ScenarioPage
            lang={lang}
            onExplore={() => setView('history')}
            onMountScenario={handleMountScenario}
          />
        );
      case 'faults':
        return <FaultInjectionPanel lang={lang} />;
      case 'tour':
        return <GuidedTourPage lang={lang} />;
      case 'settings':
        return <SettingsPage settings={settings} onSave={saveSettings} lang={lang} />;
      default:
        return null;
    }
  };

  // ── 資料來源 gate：未選 → 全屏來源選擇頁（開機 idle 的入口，取代 dashboard）──
  if (sourceActive === null) {
    return (
      <div
        style={{
          background: C.bg,
          color: C.sub,
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'Manrope, system-ui, sans-serif',
          fontSize: 14,
        }}
      >
        {lang === 'zh' ? '載入中…' : 'Loading…'}
      </div>
    );
  }
  if (!sourceActive) {
    return (
      <>
        <SourceSelectPage
          lang={lang}
          onSelect={handleSelectSource}
          onToggleLang={() => setLang(lang === 'zh' ? 'en' : 'zh')}
        />
        {auth.loginOpen && (
          <LoginPage
            lang={lang}
            onLogin={auth.login}
            onClose={auth.closeLogin}
            sessionExpired={auth.sessionExpired}
          />
        )}
      </>
    );
  }

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
            <LoginStatus lang={lang} />
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

        {/* Farm context strip（#3 狀態可見性：header 顯示當前風場 + 資料來源） */}
        {activeFarm && (
          <div
            aria-label={lang === 'zh' ? '當前風場' : 'Active farm'}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              flexWrap: 'wrap',
              marginBottom: 18,
              padding: '6px 12px',
              background: C.panelMuted,
              border: `1px solid ${C.border}`,
              borderRadius: 999,
              fontSize: 12,
              color: C.sub,
            }}
          >
            <span aria-hidden>🌊</span>
            <span style={{ color: C.text, fontWeight: 600 }}>{activeFarm.name}</span>
            <span>· {activeFarm.turbine_count} {lang === 'zh' ? '台' : 'turbines'}</span>
            <span aria-hidden style={{ color: C.border }}>|</span>
            <span>{dsLabel}</span>
          </div>
        )}

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

      {auth.loginOpen && (
        <LoginPage
          lang={lang}
          onLogin={auth.login}
          onClose={auth.closeLogin}
          sessionExpired={auth.sessionExpired}
        />
      )}
    </div>
  );
};

const App: React.FC = () => (
  <ThemeProvider>
    <UserProvider>
      <AuthProvider>
        <ScenarioMountProvider>
          <AppShell />
        </ScenarioMountProvider>
      </AuthProvider>
    </UserProvider>
  </ThemeProvider>
);

export default App;
