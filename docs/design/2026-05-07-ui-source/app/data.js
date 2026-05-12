// Shared mock data + bilingual labels for WMOM app UI variants
window.WMOM_APP = {
  pages: [
    { id: 'overview', en: 'Farm Overview', zh: '風場總覽' },
    { id: 'turbine', en: 'Turbine Detail', zh: '風機細節' },
    { id: 'maintenance', en: 'Maintenance', zh: '維護中心' },
    { id: 'cost', en: 'Cost Model', zh: '成本模型' },
    { id: 'history', en: 'History', zh: '歷史資料' },
  ],
  turbines: Array.from({length: 12}).map((_, i) => {
    const states = ['OPERATING','OPERATING','OPERATING','OPERATING','OPERATING','OPERATING','OPERATING','IDLE','OPERATING','FAULT','OPERATING','OFFLINE'];
    const status = states[i];
    const wind = 7.2 + Math.sin(i * 1.3) * 1.6 + (i % 3) * 0.4;
    const power = status === 'OPERATING' ? Math.max(0, Math.min(2.0, 0.0042 * Math.pow(wind, 3))) :
                  status === 'IDLE' ? 0.05 : status === 'FAULT' ? 0.0 : 0;
    return {
      id: i + 1,
      name: `WT0${String(i+1).padStart(2,'0')}`,
      status,
      power: +power.toFixed(2),
      wind: +wind.toFixed(1),
      rpm: status === 'OPERATING' ? +(11 + Math.sin(i)*1.5).toFixed(1) : 0,
      gearTemp: status === 'FAULT' ? 92 : 64 + i * 1.4,
      vib: status === 'FAULT' ? 4.2 : 1.2 + Math.sin(i)*0.3,
      blade: 4.5 + (i % 4) * 0.8,
      yawErr: ((i % 5) - 2) * 1.2,
    };
  }),
  workOrders: [
    { id: 'WO-2406-018', tid: 'WT010', tech: '陳建文', techEn: 'C. Wen', issue_zh: '齒輪箱過熱告警', issue_en: 'Gearbox overheat alarm', status: 'IN_PROGRESS', priority: 'HIGH', created: '5/06 09:14', sla: '4h' },
    { id: 'WO-2406-017', tid: 'WT003', tech: '林佩芸', techEn: 'P. Lin', issue_zh: '葉片角度感測器漂移', issue_en: 'Pitch sensor drift', status: 'OPEN', priority: 'MED', created: '5/06 07:42', sla: '24h' },
    { id: 'WO-2406-016', tid: 'WT008', tech: '王志豪', techEn: 'C. Wang', issue_zh: '偏航軸承定期保養', issue_en: 'Yaw bearing service', status: 'OPEN', priority: 'LOW', created: '5/05 16:00', sla: '7d' },
    { id: 'WO-2406-015', tid: 'WT012', tech: '—', techEn: '—', issue_zh: '通訊離線排查', issue_en: 'Comms offline diag', status: 'OPEN', priority: 'HIGH', created: '5/05 22:08', sla: '2h' },
    { id: 'WO-2406-014', tid: 'WT002', tech: '陳建文', techEn: 'C. Wen', issue_zh: '振動 1P 警告閾值', issue_en: 'Vib 1P warning', status: 'COMPLETED', priority: 'MED', created: '5/04 10:30', sla: '24h' },
  ],
  technicians: [
    { name: '陳建文', nameEn: 'Chen Wen', status: 'DISPATCHED', skill: '齒輪箱・發電機' },
    { name: '林佩芸', nameEn: 'Lin Pei-yun', status: 'ON_DUTY', skill: '電氣・變頻器' },
    { name: '王志豪', nameEn: 'Wang Chih-hao', status: 'ON_DUTY', skill: '結構・偏航' },
    { name: '蔡淑芬', nameEn: 'Tsai Shu-fen', status: 'OFF_DUTY', skill: '葉片・複合材' },
  ],
  cost: {
    metrics: [
      { label_en: 'Lifetime Revenue', label_zh: '生命週期營收', val: '€ 142.3M', delta: '+3.2%' },
      { label_en: 'LCOE', label_zh: '均化成本', val: '5.84 ¢/kWh', delta: '−0.18' },
      { label_en: 'NPV (8%)', label_zh: '淨現值', val: '€ 38.6M', delta: '+€2.1M' },
      { label_en: 'Payback', label_zh: '回收年限', val: '7.2 yr', delta: '−0.4' },
      { label_en: 'CapEx', label_zh: '資本支出', val: '€ 76.4M', delta: '' },
      { label_en: 'OpEx / yr', label_zh: '年營運支出', val: '€ 2.8M', delta: '' },
    ],
    monteCarlo: { p10: '4.91', p50: '5.84', p90: '6.92', sigma: '0.61' },
  },
  faults: [
    { en: 'Bearing wear', zh: '軸承磨耗' },
    { en: 'Gearbox overheat', zh: '齒輪箱過熱' },
    { en: 'Pitch motor fault', zh: '變槳馬達故障' },
    { en: 'Converter cooling fault', zh: '變頻器冷卻故障' },
    { en: 'Yaw misalignment', zh: '偏航偏差' },
    { en: 'Generator overspeed', zh: '發電機超速' },
    { en: 'Transformer overheat', zh: '變壓器過熱' },
  ]
};
