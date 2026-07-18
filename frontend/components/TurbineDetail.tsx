/**
 * TurbineDetail — A · Calm Operator 改版。
 *
 * 版面：
 *   - 麵包屑「← 風場總覽 / WTxx」
 *   - PageHeader：機名 + Production label + actions（Curtail / Stop / Inspect）
 *   - 警告 Banner（if FAULT）
 *   - 4 大數字（Power / Wind / RPM / GenTemp）
 *   - Grid 2/3 + 1/3：
 *       Left：**主圖＝發電量 vs 風速 隨時間**（TrendChartPanel，#5 拉到最上）、子系統健康 8 格、
 *             子系統 detail tabs、四通道即時趨勢（降級到最下方）
 *       Right：操作控制 / 即時告警 / 最近事件 / AI 故障診斷
 *
 * **保留功能**：start/stop/emergency/reset/service/curtail 全部 6 個指令；AI 故障診斷；8 子系統 detail。
 * **保留 API**：`/api/control/*`、`/api/turbines/:id/trend`、`analyzeTurbineFault` 全不動。
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  type TurbineData,
  TurbineStatus,
  type WorkOrder,
  type FaultInfo,
} from '../types';
import { analyzeTurbineFault } from '../services/geminiService';
import {
  Card,
  Btn,
  PageHeader,
  StatusPill,
  Stat,
  HealthBar,
  MiniSparkline,
  Field,
  Input,
  turbineStatusTone,
} from './ui';
import { useTheme } from '../theme/ThemeProvider';
import TrendChartPanel from './TrendChartPanel';

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8100';

const TUR_STATE_LABELS: Record<number, { en: string; zh: string }> = {
  1: { en: 'Shutdown', zh: '自動停機' },
  2: { en: 'Standby', zh: '待機中' },
  3: { en: 'Wait Restart', zh: '等待重啟' },
  4: { en: 'Pre-Production', zh: '發電準備' },
  5: { en: 'Start Production', zh: '啟動發電' },
  6: { en: 'Production', zh: '正常發電' },
  7: { en: 'Emergency Stop', zh: '緊急停機' },
  8: { en: 'Restart', zh: '重新啟動' },
  9: { en: 'Normal Stop', zh: '正常停機' },
};

const fmt = (v: number | undefined | null, digits = 1): string =>
  v != null && Number.isFinite(v) ? v.toFixed(digits) : '—';

/**
 * 判斷「為何不發電」的原因（WMOM-20260718-04，#3 狀態可見性）。
 *
 * 使用者反映：機組沒發電時看不出原因（cut-out / 故障跳機 / 停機都長一樣）。此函式在
 * 幾乎不發電（<0.05 MW ≈ 50 kW）時回傳一個可讀原因，正常發電或資料未就緒回 `null`。
 *
 * 優先序（code review 後）：故障 > 緊急停機(7) > 正常停機(9) > 待機(2) > 切出風速 >
 * 低於切入 > 自動停機(1) > 等待重啟(3) > 離線 > 待命。**人為決定的停機（7/9/2）排在風速
 * 之前**——它們不是風況造成的，若恰逢高風而誤標「切出風速」比不解釋更糟；風速只解釋
 * turState 1(自動停機)/3(等待重啟) 這類與風況有因果的狀態。turState 文案複用
 * `TUR_STATE_LABELS` 保留細緻度。
 *
 * @param t 需含 powerOutput(MW) / windSpeed(m/s) / status / turState。
 * @returns 原因（en/zh + tone；OFFLINE 用 muted 與 turbineStatusTone 一致）或 null。
 */
export function noPowerReason(
  t: Pick<TurbineData, 'powerOutput' | 'windSpeed' | 'status' | 'turState'>,
): { en: string; zh: string; tone: 'warn' | 'amber' | 'muted' } | null {
  // 資料未就緒（NaN/未定義）不臆測原因，比照 fmt() 的有限值防禦。
  if (!Number.isFinite(t.powerOutput)) return null;
  if (t.powerOutput > 0.05) return null; // 有在發電（>50 kW）→ 不需解釋

  // turState 對應的細緻文案（複用 TUR_STATE_LABELS，避免另造一組更粗的分類）。
  const stateReason = (
    ts: number,
    tone: 'warn' | 'amber',
  ): { en: string; zh: string; tone: 'warn' | 'amber' } => {
    const l = TUR_STATE_LABELS[ts];
    return { en: l?.en ?? `State ${ts}`, zh: l?.zh ?? `狀態 ${ts}`, tone };
  };

  const hiWind = Number.isFinite(t.windSpeed) && t.windSpeed > 25;
  const loWind = Number.isFinite(t.windSpeed) && t.windSpeed < 3;

  if (t.status === TurbineStatus.FAULT)
    return { en: 'Fault trip — protective shutdown', zh: '故障跳機 — 保護停機中', tone: 'warn' };
  if (t.turState === 7) return stateReason(7, 'warn'); // 緊急停機
  if (t.turState === 9) return stateReason(9, 'amber'); // 正常停機（操作員主動）
  if (t.turState === 2) return stateReason(2, 'amber'); // 待機中
  if (hiWind)
    return { en: 'Cut-out wind (>25 m/s) — high-wind protection', zh: '切出風速（>25 m/s）— 高風保護停機', tone: 'amber' };
  if (loWind)
    return { en: 'Wind below cut-in (~3 m/s) — waiting for wind', zh: '風速低於切入（~3 m/s）— 待風中', tone: 'amber' };
  if (t.turState === 1) return stateReason(1, 'amber'); // 自動停機
  if (t.turState === 3) return stateReason(3, 'amber'); // 等待重啟
  if (t.status === TurbineStatus.OFFLINE)
    return { en: 'Offline', zh: '離線', tone: 'muted' };
  if (t.status === TurbineStatus.IDLE)
    return { en: 'Idle', zh: '待機', tone: 'amber' };
  return { en: 'Not producing', zh: '目前未發電', tone: 'amber' };
}

interface TurbineDetailProps {
  turbine: TurbineData;
  onBack: () => void;
  onDispatch: (turbine: TurbineData, faultAnalysis: string) => void;
  activeWorkOrder?: WorkOrder;
  lang?: 'en' | 'zh';
}

// ─── Operator Control Panel（保留所有指令）─────────────────────

interface ControlStatus {
  service_mode?: boolean;
  operator_stop?: boolean;
  curtailment_kw?: number | null;
  stop_mode?: string;
  shutdown_cause?: string;
}

const OperatorControlCard: React.FC<{
  turbineApiId: string;
  tr: (en: string, zh: string) => string;
}> = ({ turbineApiId, tr }) => {
  const { C } = useTheme();
  const [status, setStatus] = useState<ControlStatus | null>(null);
  const [curtailValue, setCurtailValue] = useState('');
  const [msg, setMsg] = useState('');

  const refresh = useCallback(() => {
    fetch(`${API_BASE}/api/control/${turbineApiId}/status`)
      .then(r => r.json())
      .then(setStatus)
      .catch(() => {});
  }, [turbineApiId]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, [refresh]);

  const sendCmd = async (command: string) => {
    await fetch(`${API_BASE}/api/control/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ turbineId: turbineApiId, command }),
    });
    setMsg(`${command} OK`);
    refresh();
    setTimeout(() => setMsg(''), 2000);
  };

  const setCurtail = async () => {
    const val = curtailValue === '' ? null : parseFloat(curtailValue);
    await fetch(`${API_BASE}/api/control/curtail`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ turbineId: turbineApiId, powerLimitKw: val }),
    });
    setMsg(val ? `${tr('Curtail', '限載')}: ${val} kW` : tr('Curtailment removed', '已解除限載'));
    refresh();
    setTimeout(() => setMsg(''), 2000);
  };

  const clearCurtail = async () => {
    setCurtailValue('');
    await fetch(`${API_BASE}/api/control/curtail`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ turbineId: turbineApiId, powerLimitKw: null }),
    });
    setMsg(tr('Cleared', '已解除'));
    refresh();
    setTimeout(() => setMsg(''), 2000);
  };

  const isServiceMode = !!status?.service_mode;
  const curtailKw = status?.curtailment_kw;

  return (
    <Card style={{ marginBottom: 14 }}>
      <div
        style={{
          fontSize: 14,
          fontWeight: 600,
          marginBottom: 12,
          color: C.text,
        }}
      >
        {tr('Operator control', '操作控制')}
      </div>

      {/* Status pills */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 6,
          marginBottom: 12,
          minHeight: 22,
        }}
      >
        {isServiceMode && (
          <StatusPill tone="amber">{tr('Service mode', '定檢模式')}</StatusPill>
        )}
        {status?.operator_stop && (
          <StatusPill tone="warn">{tr('Manual stop', '手動停機')}</StatusPill>
        )}
        {status?.stop_mode === 'emergency' && (
          <StatusPill tone="warn">{tr('Emergency stop', '緊急停機')}</StatusPill>
        )}
        {curtailKw != null && (
          <StatusPill tone="amber">
            {tr(`Curtail ${curtailKw} kW`, `限載 ${curtailKw} kW`)}
          </StatusPill>
        )}
        {status?.shutdown_cause && status.shutdown_cause !== 'idle' && (
          <StatusPill tone="muted">
            {tr(`Cause: ${status.shutdown_cause}`, `原因：${status.shutdown_cause}`)}
          </StatusPill>
        )}
        {msg && <StatusPill tone="accent">{msg}</StatusPill>}
      </div>

      {/* Buttons */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
        <Btn variant="primary" onClick={() => sendCmd('start')} fullWidth>
          {tr('▶ Start', '▶ 啟動')}
        </Btn>
        <Btn variant="warn" onClick={() => sendCmd('stop')} fullWidth>
          {tr('■ Normal stop', '■ 正常停機')}
        </Btn>
        <Btn variant="danger" onClick={() => sendCmd('emergency_stop')} fullWidth>
          {tr('⚠ Emergency stop', '⚠ 緊急停機')}
        </Btn>
        <div style={{ display: 'flex', gap: 6 }}>
          <Btn onClick={() => sendCmd('reset')} fullWidth>
            {tr('Reset', '復位')}
          </Btn>
          <Btn
            variant={isServiceMode ? 'warn' : 'secondary'}
            onClick={() => sendCmd(isServiceMode ? 'service_off' : 'service_on')}
            fullWidth
          >
            {isServiceMode ? tr('Exit service', '結束定檢') : tr('Service mode', '進入定檢')}
          </Btn>
        </div>
      </div>

      {/* Curtail */}
      <div
        style={{
          borderTop: `1px solid ${C.border}`,
          paddingTop: 10,
        }}
      >
        <Field label={tr('Curtailment (kW)', '限載 (kW)')}>
          <div style={{ display: 'flex', gap: 6 }}>
            <Input
              type="number"
              value={curtailValue}
              onChange={setCurtailValue}
              placeholder={tr('kW limit', '限載 kW')}
              fullWidth
            />
            <Btn onClick={setCurtail} ariaLabel={tr('Set curtail', '設定限載')}>
              {tr('Set', '設定')}
            </Btn>
            {curtailKw != null && (
              <Btn onClick={clearCurtail} variant="ghost">
                {tr('Clear', '解除')}
              </Btn>
            )}
          </div>
        </Field>
      </div>
    </Card>
  );
};

// ─── Fault badge ───────────────────────────────────────────────

const FaultBanner: React.FC<{ faults: FaultInfo[]; tr: (en: string, zh: string) => string }> = ({
  faults,
  tr,
}) => {
  const { C } = useTheme();
  if (!faults.length) return null;
  const phaseTone = (phase: string) => {
    if (phase === 'critical' || phase === 'advanced') return C.warn;
    if (phase === 'developing') return C.amber;
    return C.amber;
  };
  return (
    <Card tone="warn" style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 12, color: C.warn, fontWeight: 600, marginBottom: 8 }}>
        {tr('Active faults', '即時告警')}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {faults.map((f, i) => (
          <div
            key={i}
            style={{
              padding: '10px 12px',
              borderRadius: 8,
              border: `1px solid ${phaseTone(f.phase)}`,
              background: C.warnSoft,
            }}
          >
            <div style={{ fontWeight: 700, color: C.text }}>
              {/* fallback to en if zh missing */}
              {(typeof navigator !== 'undefined' && navigator.language?.startsWith('zh'))
                ? f.name_zh
                : f.name_en}
            </div>
            <div style={{ fontSize: 12, marginTop: 4, color: C.sub, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <span>
                {tr('Severity', '嚴重度')}: {(f.severity * 100).toFixed(1)}%
              </span>
              <span style={{ textTransform: 'capitalize' }}>{f.phase}</span>
              {f.tripped && (
                <StatusPill tone="warn" size="sm">
                  TRIPPED
                </StatusPill>
              )}
            </div>
            {f.active_alarms.length > 0 && (
              <div style={{ marginTop: 6, fontSize: 11, color: C.sub }}>
                {f.active_alarms.map((a, j) => (
                  <div key={j}>
                    [{a.type}] {a.desc}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
};

// ─── Subsystem health (8) ───────────────────────────────────────

function score(value: number | undefined, opts: { warn: number; alert: number; ok?: number }): number {
  if (value == null || !Number.isFinite(value)) return 90;
  const { warn, alert, ok = 0 } = opts;
  if (value <= ok) return 100;
  if (value >= alert) return 30;
  if (value >= warn) return 60 + (1 - (value - warn) / (alert - warn)) * 25;
  return 90 - ((value - ok) / (warn - ok)) * 10;
}

const useSubsystemScores = (t: TurbineData) =>
  useMemo(
    () => [
      { label_en: 'Generator', label_zh: '發電機', s: score(t.genStatorTemp1, { warn: 90, alert: 130, ok: 60 }) },
      { label_en: 'Gearbox', label_zh: '齒輪箱', s: score(t.temperature, { warn: 75, alert: 95, ok: 45 }) },
      { label_en: 'Pitch', label_zh: '變槳', s: score(Math.abs(t.bladeAngle ?? 0), { warn: 25, alert: 45, ok: 0 }) },
      { label_en: 'Yaw', label_zh: '偏航', s: score(Math.abs(t.yawError ?? 0), { warn: 8, alert: 15, ok: 0 }) },
      { label_en: 'Tower', label_zh: '塔筒', s: score(t.delTowerFa, { warn: 4000, alert: 6000, ok: 1000 }) },
      { label_en: 'Blades', label_zh: '葉片', s: score(t.delBladeFlap, { warn: 2000, alert: 3000, ok: 500 }) },
      { label_en: 'Converter', label_zh: '變頻器', s: score(t.cnvCabinetTemp, { warn: 40, alert: 50, ok: 25 }) },
      { label_en: 'Cooling', label_zh: '冷卻', s: score(t.igctWaterTemp, { warn: 35, alert: 45, ok: 25 }) },
    ],
    [t],
  );

// ─── Live trends (4 channels) ─────────────────────────────────

const LiveTrendsCard: React.FC<{
  t: TurbineData;
  tr: (en: string, zh: string) => string;
}> = ({ t, tr }) => {
  const { C } = useTheme();
  // pseudo time-series: prefer history, fallback to deterministic synth
  const baseHistory = (t.history ?? []).slice(-50).map(h => h.power);
  const synth = (offset: number, amp: number) =>
    Array.from({ length: 50 }).map((_, k) => Math.sin(k * 0.4 + offset) * amp + amp * 1.2);

  const channels: {
    label: React.ReactNode;
    color: string;
    values: number[];
    cur: string;
    unit: string;
  }[] = [
    {
      label: 'Power MW',
      color: C.accent,
      values: baseHistory.length > 4 ? baseHistory : synth(t.id, 0.8),
      cur: t.powerOutput.toFixed(2),
      unit: 'MW',
    },
    {
      label: 'Wind m/s',
      color: C.info,
      values: synth(t.id + 1, 1.5).map(v => v + t.windSpeed * 0.6),
      cur: t.windSpeed.toFixed(1),
      unit: 'm/s',
    },
    {
      label: tr('Gen °C', '發電機 °C'),
      color: C.amber,
      values: synth(t.id + 2, 4).map(v => v + (t.genStatorTemp1 ?? t.temperature)),
      cur: fmt(t.genStatorTemp1 ?? t.temperature, 0),
      unit: '°C',
    },
    {
      label: 'Vib mm/s',
      color: C.warn,
      values: synth(t.id + 3, 0.6).map(v => Math.max(0, v + (t.vibrationX ?? t.vibration))),
      cur: fmt(t.vibrationX ?? t.vibration, 1),
      unit: 'mm/s',
    },
  ];
  return (
    <Card style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: C.text }}>
        {tr('Live trends · 4 channels', '即時趨勢　四通道')}
      </div>
      {channels.map((ch, i) => (
        <div
          key={i}
          style={{
            display: 'grid',
            gridTemplateColumns: '110px 1fr 80px',
            alignItems: 'center',
            gap: 12,
            marginBottom: 8,
          }}
        >
          <div style={{ fontSize: 11, color: C.sub, fontFamily: 'JetBrains Mono, monospace' }}>
            {ch.label}
          </div>
          <MiniSparkline values={ch.values} color={ch.color} height={36} />
          <span
            style={{
              fontSize: 12,
              color: C.text,
              fontFamily: 'JetBrains Mono, monospace',
              textAlign: 'right',
            }}
          >
            {ch.cur} <span style={{ color: C.sub, fontSize: 10 }}>{ch.unit}</span>
          </span>
        </div>
      ))}
    </Card>
  );
};

// ─── Subsystem detail tabs（沿用既有資料）──────────────────

type DetailTab = 'overview' | 'generator' | 'pitch' | 'converter' | 'nacelle' | 'yaw' | 'grid' | 'fatigue';

const DETAIL_TABS: { id: DetailTab; en: string; zh: string }[] = [
  { id: 'overview', en: 'Overview', zh: '總覽' },
  { id: 'generator', en: 'Generator', zh: '發電機' },
  { id: 'pitch', en: 'Pitch/Rotor', zh: '旋角系統' },
  { id: 'converter', en: 'Converter', zh: '變頻器' },
  { id: 'nacelle', en: 'Nacelle', zh: '機艙' },
  { id: 'yaw', en: 'Yaw', zh: '轉向系統' },
  { id: 'grid', en: 'Grid/Met', zh: '電網/氣象' },
  { id: 'fatigue', en: 'Load/Fatigue', zh: '載荷/疲勞' },
];

const DataRow: React.FC<{
  label: React.ReactNode;
  value: React.ReactNode;
  warn?: boolean;
  alert?: boolean;
}> = ({ label, value, warn, alert }) => {
  const { C } = useTheme();
  const color = alert ? C.warn : warn ? C.amber : C.text;
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        padding: '6px 0',
        borderBottom: `1px solid ${C.border}`,
      }}
    >
      <span style={{ fontSize: 12, color: C.sub }}>{label}</span>
      <span
        style={{
          fontSize: 13,
          fontWeight: 600,
          color,
          fontFamily: 'JetBrains Mono, monospace',
        }}
      >
        {value}
      </span>
    </div>
  );
};

const SubsystemSection: React.FC<{
  title: React.ReactNode;
  children: React.ReactNode;
}> = ({ title, children }) => {
  const { C } = useTheme();
  return (
    <div>
      <div
        style={{
          fontSize: 11,
          color: C.accent,
          textTransform: 'uppercase',
          letterSpacing: 1,
          fontWeight: 600,
          marginBottom: 8,
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
};

const SubsystemDetailCard: React.FC<{
  t: TurbineData;
  tr: (en: string, zh: string) => string;
}> = ({ t, tr }) => {
  const { C } = useTheme();
  const [tab, setTab] = useState<DetailTab>('overview');

  const renderTab = () => {
    switch (tab) {
      case 'overview':
        return (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
            <SubsystemSection title="WGEN">
              <DataRow label={tr('Power', '功率')} value={`${fmt(t.genPower)} kW`} />
              <DataRow label={tr('Speed', '轉速')} value={`${fmt(t.genSpeed, 0)} RPM`} />
              <DataRow
                label={tr('Stator °C', '定子溫度')}
                value={`${fmt(t.genStatorTemp1)}°C`}
                warn={(t.genStatorTemp1 || 0) > 100}
                alert={(t.genStatorTemp1 || 0) > 130}
              />
              <DataRow
                label={tr('Bearing °C', '軸承溫度')}
                value={`${fmt(t.genBearingTemp1)}°C`}
                warn={(t.genBearingTemp1 || 0) > 70}
                alert={(t.genBearingTemp1 || 0) > 90}
              />
            </SubsystemSection>
            <SubsystemSection title="WNAC">
              <DataRow label={tr('Nacelle °C', '機艙溫度')} value={`${fmt(t.nacelleTemp)}°C`} />
              <DataRow
                label={tr('Vib X/Y', '振動 X/Y')}
                value={`${fmt(t.vibrationX, 2)} / ${fmt(t.vibrationY, 2)} mm/s`}
                warn={(t.vibrationX || 0) > 4 || (t.vibrationY || 0) > 4}
              />
            </SubsystemSection>
            <SubsystemSection title="WROT">
              <DataRow
                label={tr('Blades', '葉片角度')}
                value={`${fmt(t.bladeAngle1)}° / ${fmt(t.bladeAngle2)}° / ${fmt(t.bladeAngle3)}°`}
              />
              <DataRow
                label={tr('Locked / Brake', '鎖固 / 剎車')}
                value={`${t.rotorLocked ? 'L' : '-'} / ${t.brakeActive ? 'A' : '-'}`}
              />
            </SubsystemSection>
          </div>
        );
      case 'generator':
        return (
          <SubsystemSection title="WGEN Generator">
            <DataRow label={tr('Power', '功率')} value={`${fmt(t.genPower)} kW`} />
            <DataRow label={tr('Speed', '轉速')} value={`${fmt(t.genSpeed, 0)} RPM`} />
            <DataRow label={tr('Voltage', '電壓')} value={`${fmt(t.voltage, 0)} V`} />
            <DataRow label={tr('Current', '電流')} value={`${fmt(t.current, 0)} A`} />
            <DataRow
              label={tr('Stator °C', '定子溫度')}
              value={`${fmt(t.genStatorTemp1)}°C`}
              warn={(t.genStatorTemp1 || 0) > 100}
              alert={(t.genStatorTemp1 || 0) > 130}
            />
            <DataRow
              label={tr('Air gap °C', '氣隙溫度')}
              value={`${fmt(t.genAirTemp1)}°C`}
              warn={(t.genAirTemp1 || 0) > 80}
            />
            <DataRow
              label={tr('Bearing °C', '軸承溫度')}
              value={`${fmt(t.genBearingTemp1)}°C`}
              warn={(t.genBearingTemp1 || 0) > 70}
              alert={(t.genBearingTemp1 || 0) > 90}
            />
          </SubsystemSection>
        );
      case 'pitch':
        return (
          <SubsystemSection title="WROT Rotor / Pitch">
            <DataRow label={tr('Rotor RPM', '葉輪轉速')} value={`${fmt(t.rotorSpeed, 2)} RPM`} />
            <DataRow label={tr('Blade 1°', '葉片1')} value={`${fmt(t.bladeAngle1)}°`} />
            <DataRow label={tr('Blade 2°', '葉片2')} value={`${fmt(t.bladeAngle2)}°`} />
            <DataRow label={tr('Blade 3°', '葉片3')} value={`${fmt(t.bladeAngle3)}°`} />
            <DataRow label={tr('Rotor °C', '轉子溫度')} value={`${fmt(t.rotorTemp)}°C`} />
            <DataRow label={tr('Hub Cabin °C', '輪轂櫃溫')} value={`${fmt(t.hubCabinetTemp)}°C`} />
          </SubsystemSection>
        );
      case 'converter':
        return (
          <SubsystemSection title="WCNV Converter">
            <DataRow label={tr('Gen power', '發電機功率')} value={`${fmt(t.cnvGenPower)} kW`} />
            <DataRow label={tr('Grid power', '電網功率')} value={`${fmt(t.cnvGridPower)} kW`} />
            <DataRow label={tr('Frequency', '頻率')} value={`${fmt(t.cnvGenFreq, 2)} Hz`} />
            <DataRow label={tr('DC voltage', 'DC 電壓')} value={`${fmt(t.cnvDcVoltage, 0)} V`} />
            <DataRow
              label={tr('Cabinet °C', '控制櫃溫度')}
              value={`${fmt(t.cnvCabinetTemp)}°C`}
              warn={(t.cnvCabinetTemp || 0) > 45}
            />
            <DataRow
              label={tr('IGCT water °C', 'IGCT 水溫')}
              value={`${fmt(t.igctWaterTemp)}°C`}
              warn={(t.igctWaterTemp || 0) > 40}
            />
            <DataRow label={tr('Reactive power', '無功功率')} value={`${fmt(t.reactivePower)} kvar`} />
            <DataRow label={tr('Power factor', '功率因數')} value={fmt(t.powerFactor, 3)} />
          </SubsystemSection>
        );
      case 'nacelle':
        return (
          <SubsystemSection title="WNAC Nacelle">
            <DataRow label={tr('Nacelle °C', '機艙溫度')} value={`${fmt(t.nacelleTemp)}°C`} />
            <DataRow label={tr('Cabinet °C', '控制櫃溫度')} value={`${fmt(t.nacelleCabTemp)}°C`} />
            <DataRow
              label={tr('Vib X', 'X 振動')}
              value={`${fmt(t.vibrationX, 2)} mm/s`}
              warn={(t.vibrationX || 0) > 4}
              alert={(t.vibrationX || 0) > 8}
            />
            <DataRow
              label={tr('Vib Y', 'Y 振動')}
              value={`${fmt(t.vibrationY, 2)} mm/s`}
              warn={(t.vibrationY || 0) > 4}
              alert={(t.vibrationY || 0) > 8}
            />
            <DataRow label={tr('Crest factor', '峰值因子')} value={fmt(t.vibCrestFactor, 2)} />
            <DataRow label={tr('Kurtosis', '峰度')} value={fmt(t.vibKurtosis, 2)} />
          </SubsystemSection>
        );
      case 'yaw':
        return (
          <SubsystemSection title="WYAW Yaw System">
            <DataRow
              label={tr('Yaw error', '風向誤差')}
              value={`${fmt(t.yawError)}°`}
              warn={Math.abs(t.yawError || 0) > 10}
            />
            <DataRow label={tr('Brake pressure', '剎車液壓')} value={`${fmt(t.yawBrakePressure, 0)} bar`} />
            <DataRow
              label={tr('Cable windup', '纜線圈數')}
              value={`${fmt(t.cableWindup, 2)} turns`}
              warn={Math.abs(t.cableWindup || 0) > 3}
            />
          </SubsystemSection>
        );
      case 'grid':
        return (
          <SubsystemSection title="WGDC / WMET">
            <DataRow
              label={tr('Transformer °C', '變壓器溫度')}
              value={`${fmt(t.transformerTemp)}°C`}
              warn={(t.transformerTemp || 0) > 80}
            />
            <DataRow label={tr('Wind speed', '風速')} value={`${fmt(t.windSpeed)} m/s`} />
            <DataRow label={tr('Wind dir', '風向')} value={`${fmt(t.windDirection, 0)}°`} />
            <DataRow label={tr('Outside °C', '室外溫度')} value={`${fmt(t.outsideTemp)}°C`} />
          </SubsystemSection>
        );
      case 'fatigue':
        return (
          <SubsystemSection title="WLOD Load & Fatigue">
            <DataRow label={tr('Tower FA', '塔架 FA')} value={`${fmt(t.towerFaMoment, 1)} kNm`} />
            <DataRow label={tr('Tower SS', '塔架 SS')} value={`${fmt(t.towerSsMoment, 1)} kNm`} />
            <DataRow label={tr('Blade flap', '葉片揮舞')} value={`${fmt(t.bladeFlapMoment, 1)} kNm`} />
            <DataRow label={tr('Blade edge', '葉片擺振')} value={`${fmt(t.bladeEdgeMoment, 1)} kNm`} />
            <DataRow
              label={tr('DEL tower FA', 'DEL 塔架 FA')}
              value={fmt(t.delTowerFa, 1)}
              warn={(t.delTowerFa || 0) > 4000}
              alert={(t.delTowerFa || 0) > 6000}
            />
            <DataRow
              label={tr('DEL blade flap', 'DEL 葉片揮舞')}
              value={fmt(t.delBladeFlap, 1)}
              warn={(t.delBladeFlap || 0) > 2000}
              alert={(t.delBladeFlap || 0) > 3000}
            />
            <DataRow label={tr('Production hours', '發電時數')} value={`${fmt(t.productionHours, 1)} h`} />
          </SubsystemSection>
        );
    }
  };

  return (
    <Card>
      <div
        style={{
          fontSize: 14,
          fontWeight: 600,
          marginBottom: 12,
          color: C.text,
        }}
      >
        {tr('Subsystem detail', '子系統明細')}
      </div>
      <div
        style={{
          display: 'flex',
          gap: 4,
          flexWrap: 'wrap',
          marginBottom: 14,
          padding: 4,
          background: C.panelMuted,
          borderRadius: 8,
        }}
      >
        {DETAIL_TABS.map(t2 => {
          const active = tab === t2.id;
          return (
            <button
              key={t2.id}
              onClick={() => setTab(t2.id)}
              aria-pressed={active}
              style={{
                padding: '6px 12px',
                fontSize: 12,
                borderRadius: 6,
                border: 'none',
                background: active ? C.accent : 'transparent',
                color: active ? C.accentInk : C.sub,
                cursor: 'pointer',
                fontFamily: 'inherit',
                fontWeight: active ? 600 : 500,
              }}
            >
              {tr(t2.en, t2.zh)}
            </button>
          );
        })}
      </div>
      {renderTab()}
    </Card>
  );
};

// ─── Recent events (mock — backend 沒有 per-turbine event API)──

const RecentEventsCard: React.FC<{
  t: TurbineData;
  tr: (en: string, zh: string) => string;
}> = ({ t, tr }) => {
  const { C } = useTheme();
  // 從 turbine data 推導出可顯示事件（無事件就顯示 placeholder）
  const events = useMemo(() => {
    const out: { time: string; en: string; zh: string; tag: string; tone: 'accent' | 'warn' | 'amber' | 'ok' }[] = [];
    if (t.activeFaults && t.activeFaults.length > 0) {
      t.activeFaults.forEach(f => {
        out.push({
          time: '–:–',
          en: `${f.name_en} (${f.phase})`,
          zh: `${f.name_zh}（${f.phase}）`,
          tag: 'fault',
          tone: 'warn',
        });
      });
    }
    if (t.windSpeed > 12) {
      out.push({ time: '–:–', en: 'High wind', zh: '高風速', tag: 'wind', tone: 'accent' });
    }
    if (t.status === TurbineStatus.OPERATING) {
      out.push({ time: '–:–', en: 'Synchronized', zh: '併網中', tag: 'state', tone: 'ok' });
    } else if (t.status === TurbineStatus.IDLE) {
      out.push({ time: '–:–', en: 'Standby', zh: '待機', tag: 'state', tone: 'amber' });
    }
    return out.slice(0, 4);
  }, [t]);

  return (
    <Card style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 10, color: C.text }}>
        {tr('Recent events', '最近事件')}
      </div>
      {events.length === 0 ? (
        <div style={{ fontSize: 12, color: C.sub }}>{tr('No recent events.', '目前無事件。')}</div>
      ) : (
        events.map((e, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              gap: 10,
              padding: '8px 0',
              borderBottom: i < events.length - 1 ? `1px solid ${C.border}` : undefined,
              fontSize: 12,
              alignItems: 'center',
            }}
          >
            <span style={{ color: C.sub, fontFamily: 'JetBrains Mono, monospace', minWidth: 36 }}>
              {e.time}
            </span>
            <span style={{ flex: 1, color: C.text }}>{tr(e.en, e.zh)}</span>
            <StatusPill tone={e.tone}>{e.tag}</StatusPill>
          </div>
        ))
      )}
    </Card>
  );
};

// ─── AI fault diagnosis ────────────────────────────────────────

const AIDiagnosisCard: React.FC<{
  turbine: TurbineData;
  activeWorkOrder?: WorkOrder;
  onDispatch: (turbine: TurbineData, faultAnalysis: string) => void;
  tr: (en: string, zh: string) => string;
}> = ({ turbine, activeWorkOrder, onDispatch, tr }) => {
  const { C } = useTheme();
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const analyze = useCallback(async () => {
    setAnalyzing(true);
    setResult(null);
    setError(null);
    try {
      const r = await analyzeTurbineFault(turbine);
      setResult(r);
    } catch {
      setError(tr('Analysis failed. Please retry.', '分析失敗，請重試。'));
    } finally {
      setAnalyzing(false);
    }
  }, [turbine, tr]);

  // Auto analyze on first FAULT
  useEffect(() => {
    if (turbine.status === TurbineStatus.FAULT && !result && !analyzing) {
      analyze();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turbine.status]);

  return (
    <Card tone="warn" style={{ marginBottom: 14 }}>
      <div
        style={{
          fontSize: 14,
          fontWeight: 600,
          marginBottom: 4,
          color: C.warn,
        }}
      >
        {tr('AI Fault Diagnosis', 'AI 故障診斷')}
      </div>
      <div style={{ fontSize: 12, color: C.sub, marginBottom: 12 }}>
        {tr('Experimental analysis to assist diagnosis.', '實驗性 AI 分析協助故障診斷。')}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <Btn variant="secondary" onClick={analyze} disabled={analyzing} fullWidth>
          {analyzing ? tr('Analyzing…', '分析中…') : tr('Re-analyze', '重新分析')}
        </Btn>
        {activeWorkOrder ? (
          <StatusPill tone="amber" size="md" style={{ textAlign: 'center', justifyContent: 'center' }}>
            {tr(`WO #${activeWorkOrder.id.slice(-4)} in progress`, `工單 #${activeWorkOrder.id.slice(-4)} 處理中`)}
          </StatusPill>
        ) : (
          <Btn
            variant="warn"
            onClick={() => onDispatch(turbine, result || 'Awaiting analysis...')}
            disabled={analyzing || !result}
            fullWidth
          >
            {tr('Dispatch technician', '派遣技術員')}
          </Btn>
        )}
      </div>
      {error && (
        <div
          style={{
            marginTop: 10,
            background: C.warnSoft,
            color: C.warn,
            padding: '8px 10px',
            borderRadius: 8,
            fontSize: 12,
          }}
        >
          {error}
        </div>
      )}
      {result && (
        <div
          style={{
            marginTop: 10,
            background: C.panelMuted,
            color: C.text,
            padding: 12,
            borderRadius: 8,
            fontSize: 12,
            fontFamily: 'JetBrains Mono, monospace',
            whiteSpace: 'pre-wrap',
            maxHeight: 280,
            overflowY: 'auto',
          }}
        >
          {result}
        </div>
      )}
    </Card>
  );
};

// ─── Main ──────────────────────────────────────────────────────

const TurbineDetail: React.FC<TurbineDetailProps> = ({
  turbine,
  onBack,
  onDispatch,
  activeWorkOrder,
  lang = 'zh',
}) => {
  const { C } = useTheme();
  const tr = (en: string, zh: string) => (lang === 'zh' ? zh : en);
  const turbineApiId = `WT${String(turbine.id).padStart(3, '0')}`;
  const turStateLabel = TUR_STATE_LABELS[turbine.turState || 0];
  const turStateText = turStateLabel
    ? lang === 'zh'
      ? turStateLabel.zh
      : turStateLabel.en
    : `State ${turbine.turState}`;
  const hasFaults = turbine.activeFaults && turbine.activeFaults.length > 0;
  const subScores = useSubsystemScores(turbine);

  return (
    <div>
      <PageHeader
        breadcrumb={
          <button
            onClick={onBack}
            aria-label={tr('Back to farm overview', '返回風場總覽')}
            style={{
              background: 'transparent',
              border: 'none',
              color: C.sub,
              cursor: 'pointer',
              fontSize: 12,
              fontFamily: 'inherit',
              padding: 0,
            }}
          >
            ← {tr('Farm overview', '風場總覽')} / <span style={{ color: C.text }}>{turbine.name}</span>
          </button>
        }
        title={`${turbine.name} · ${turStateText}`}
        sub={
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            Bachmann Z72 · {tr('TurState', '狀態')} {turbine.turState ?? '—'}
            <StatusPill tone={turbineStatusTone(turbine.status)}>
              {turbine.status === TurbineStatus.OPERATING
                ? tr('OPERATING', '運轉中')
                : turbine.status === TurbineStatus.FAULT
                  ? tr('FAULT', '故障')
                  : turbine.status === TurbineStatus.IDLE
                    ? tr('IDLE', '待機')
                    : tr('OFFLINE', '離線')}
            </StatusPill>
            {turbine.outsideTemp != null && (
              <span style={{ color: C.sub }}>
                {tr('Outside', '室外')} {fmt(turbine.outsideTemp)}°C
              </span>
            )}
            {turbine.windDirection != null && (
              <span style={{ color: C.sub }}>
                {tr('Wind dir', '風向')} {fmt(turbine.windDirection, 0)}°
              </span>
            )}
          </span>
        }
        actions={
          <>
            <Btn ariaLabel={tr('Curtail', '限載')}>{tr('Curtail', '限載')}</Btn>
            <Btn ariaLabel={tr('Stop', '停機')}>{tr('Stop', '停機')}</Btn>
            <Btn variant="primary" ariaLabel={tr('Inspect', '安排檢查')}>
              {tr('Inspect', '安排檢查')}
            </Btn>
          </>
        }
      />

      {/* Active fault banner */}
      {hasFaults && <FaultBanner faults={turbine.activeFaults!} tr={tr} />}

      {/* 為何不發電（#3 狀態可見性）：功率≈0 時說明 cut-out / 跳機 / 停機 */}
      {(() => {
        const reason = noPowerReason(turbine);
        if (!reason) return null;
        return (
          <div style={{ marginBottom: 16 }} role="status">
            <StatusPill tone={reason.tone} size="md">
              {tr('Why no power', '為何不發電')}：{tr(reason.en, reason.zh)}
            </StatusPill>
          </div>
        );
      })()}

      {/* 4 hero metrics */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <Card padding={14}>
          <Stat label={tr('Power', '功率')} value={fmt(turbine.powerOutput, 2)} unit="MW" highlight size={28} />
        </Card>
        <Card padding={14}>
          <Stat label={tr('Wind', '風速')} value={fmt(turbine.windSpeed, 1)} unit="m/s" size={28} />
        </Card>
        <Card padding={14}>
          <Stat label="RPM" value={fmt(turbine.rotorSpeed, 1)} unit="rpm" size={28} />
        </Card>
        <Card padding={14}>
          <Stat
            label={tr('Gen °C', '發電機 °C')}
            value={fmt(turbine.genStatorTemp1 ?? turbine.temperature, 0)}
            unit="°C"
            size={28}
          />
        </Card>
      </div>

      {/* Main grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 2fr) minmax(280px, 1fr)',
          gap: 16,
        }}
      >
        <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* 主圖：發電量 vs 風速 隨時間（#5 顯示重設計，WMOM-20260718-05）。
              看風機最直接的就是「過去到現在的發電量與風速關係」→ 拉到最上面當主視圖。
              TrendChartPanel 預設 preset 即 'power'（WTUR_TotPwrAt + WMET_WSpeedNac），
              下方 preset 鈕可切溫度/振動/葉片角等其他通道。 */}
          <Card padding={0}>
            <div
              style={{
                padding: '14px 18px',
                borderBottom: `1px solid ${C.border}`,
              }}
            >
              <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>
                {tr('Power vs Wind · over time', '發電量 vs 風速 · 過去到現在')}
              </div>
              <div style={{ fontSize: 11, color: C.sub, marginTop: 2 }}>
                {tr(
                  'The most direct view of a turbine. Switch presets below for temperature / vibration / other channels.',
                  '看風機最直接的視圖。切換下方預設可看溫度 / 振動 / 其他 SCADA 通道。',
                )}
              </div>
            </div>
            <div style={{ padding: 12 }}>
              <TrendChartPanel turbineId={turbineApiId} lang={lang} />
            </div>
          </Card>

          <Card>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14, color: C.text }}>
              {tr('Subsystem health', '子系統健康')}
            </div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
                gap: 14,
              }}
            >
              {subScores.map(s => (
                <HealthBar key={s.label_en} label={tr(s.label_en, s.label_zh)} value={s.s} />
              ))}
            </div>
          </Card>

          <SubsystemDetailCard t={turbine} tr={tr} />

          {/* 四通道即時趨勢（降級到最下方；發電量/風速已在頂端主圖 + hero 數字呈現） */}
          <LiveTrendsCard t={turbine} tr={tr} />
        </div>

        <div style={{ minWidth: 0 }}>
          <OperatorControlCard turbineApiId={turbineApiId} tr={tr} />
          <RecentEventsCard t={turbine} tr={tr} />
          {turbine.status === TurbineStatus.FAULT && (
            <AIDiagnosisCard
              turbine={turbine}
              activeWorkOrder={activeWorkOrder}
              onDispatch={onDispatch}
              tr={tr}
            />
          )}
        </div>
      </div>
    </div>
  );
};

export default TurbineDetail;
