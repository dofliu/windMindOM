// Shared bilingual content for digiWindTurbine product promo
window.WMOM_CONTENT = {
  brand: { en: "digiWindTurbine", zh: "digiWindTurbine" },
  tagline: {
    en: "A living digital twin for every turbine in your fleet.",
    zh: "為風場每一座風機，打造會呼吸的數位雙生。"
  },
  subTagline: {
    en: "Physics-grade simulation. SCADA-aligned data. One quiet, friendly platform.",
    zh: "物理級模擬・SCADA 規格對齊・一個安靜友善的營運平台。"
  },
  cta: { en: "Request a Demo", zh: "申請 Demo" },
  ctaSecondary: { en: "Watch 90s Tour", zh: "觀看 90 秒導覽" },

  stats: [
    { num: "104", label_en: "SCADA tags aligned", label_zh: "SCADA 標籤對齊" },
    { num: "7", label_en: "Fault scenarios", label_zh: "故障情境模擬" },
    { num: "10", label_en: "Thermal nodes modeled", label_zh: "熱力節點模型" },
    { num: "9", label_en: "Operating states", label_zh: "運轉狀態" },
    { num: "<1ms", label_en: "Realtime stream", label_zh: "即時串流延遲" },
    { num: "100%", label_en: "Bachmann Z72 mapped", label_zh: "對應 Bachmann Z72" }
  ],

  features: [
    {
      icon: "wind",
      title_en: "Believable wind",
      title_zh: "會呼吸的風",
      body_en: "Wake propagation, turbulence pockets, atmospheric stability, wind veer — every gust has a reason.",
      body_zh: "尾流傳遞、紊流口袋、大氣穩定度、風向漸轉——每一陣風都有它的物理原因。"
    },
    {
      icon: "fault",
      title_en: "Faults that feel real",
      title_zh: "像真的故障",
      body_en: "Bearing wear, gearbox overheat, pitch motor — faults change heat, vibration, and control before they trip.",
      body_zh: "軸承磨耗、齒輪箱過熱、變槳故障——先影響溫度、振動與控制，才跳機。"
    },
    {
      icon: "grid",
      title_en: "Grid that pushes back",
      title_zh: "會回應的電網",
      body_en: "Frequency-watt response, ride-through curves, per-turbine derate. The grid is a character, not a constant.",
      body_zh: "頻率—功率響應、低電壓穿越曲線、逐機降載。電網是角色，不是常數。"
    },
    {
      icon: "history",
      title_en: "History you can read",
      title_zh: "讀得懂的歷史",
      body_en: "Event-marked trends, focus windows, CSV export. Click any spike, see what happened underneath.",
      body_zh: "事件標記的趨勢圖、聚焦時窗、CSV 匯出。點任何尖峰，看見底下發生了什麼。"
    },
    {
      icon: "api",
      title_en: "Speaks every protocol",
      title_zh: "通用語言",
      body_en: "REST, WebSocket, Modbus TCP. Mock or real backend with one toggle. Drop into your stack in minutes.",
      body_zh: "REST、WebSocket、Modbus TCP。模擬與真實後端一鍵切換，幾分鐘內接入您的系統。"
    },
    {
      icon: "twin",
      title_en: "Twin per turbine",
      title_zh: "一機一雙生",
      body_en: "Per-turbine individuality — same wind, different turbines, different responses. Just like the field.",
      body_zh: "逐機個體差異——同樣的風、不同的風機、不同的反應。如同現場。"
    }
  ],

  physics: {
    title_en: "The physics that other twins skip",
    title_zh: "別人懶得做的物理",
    items: [
      { en: "Bastankhah-Porté-Agel Gaussian wake", zh: "Bastankhah-Porté-Agel 高斯尾流" },
      { en: "Larsen-DWM dynamic wake meandering", zh: "Larsen-DWM 動態尾流擺動" },
      { en: "Monin-Obukhov atmospheric stability", zh: "Monin-Obukhov 大氣穩定度" },
      { en: "Glauert skewed-wake correction", zh: "Glauert 斜流尾流修正" },
      { en: "IEC 61400-12-1/2 nacelle transfer functions", zh: "IEC 61400-12-1/2 機艙傳遞函數" },
      { en: "Rainflow fatigue + Miner's damage RUL", zh: "雨流疲勞累積 + Miner 損傷 RUL" },
      { en: "BPFO/BPFI bearing defect spectra", zh: "軸承內外環缺陷頻譜" },
      { en: "Crespo-Hernández wake-added turbulence", zh: "Crespo-Hernández 尾流附加紊流" }
    ]
  },

  testimonial: {
    quote_en: "We replaced a six-figure simulator and three Excel sheets with one URL.",
    quote_zh: "我們用一個網址，取代了一台六位數的模擬器和三份 Excel。",
    author_en: "Lin Chen-yu, Operations Director",
    author_zh: "林振宇　營運總監",
    org_en: "Coastal Energy Co. — 48 turbines, Changhua",
    org_zh: "彰化沿海能源　48 座機組"
  },

  api: {
    title_en: "Drop in, plug up, done.",
    title_zh: "接上即用",
    body_en: "REST + WebSocket + Modbus TCP. Switch between mock data and live OPC with one toggle.",
    body_zh: "REST、WebSocket、Modbus TCP 三軌齊發。模擬與真實 OPC，一鍵切換。",
    snippet: `GET /api/turbines/farm-status
ws://localhost:8100/ws/realtime
modbus://localhost:5020`
  },

  finalCta: {
    title_en: "Bring your fleet to life.",
    title_zh: "讓您的風場活過來。",
    body_en: "30-minute demo, walked through by an engineer who built it.",
    body_zh: "30 分鐘的 Demo，由親手打造它的工程師為您導覽。"
  },

  nav: [
    { id: "features", en: "Features", zh: "功能" },
    { id: "physics", en: "Physics", zh: "物理模型" },
    { id: "demo", en: "Live Preview", zh: "即時預覽" },
    { id: "api", en: "Integrate", zh: "整合" },
    { id: "contact", en: "Contact", zh: "聯絡" }
  ]
};
