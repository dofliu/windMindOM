#!/usr/bin/env python3
"""產生 windMindOM 介紹影片（3 分鐘 / 18 景）的場景 HTML 與 storyboard.json。

用法：
    python promo/gen_scenes.py            # 重新產出 promo/scene*.html + storyboard.json

改文案就改本檔的 SCENES 定義後重跑，再用 render_scenes.py --only <scene> 單景重渲。
場景視覺語言沿用 intro-video 技能的 scene_template.html（深海底 + 極光暈 + 鏡頭慢推）。
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent

# ─────────────────────────────────────────────────────────────────────────
# 色調章（每 3-4 景換一次當「換章」訊號，維持同一暗度）
# ─────────────────────────────────────────────────────────────────────────
TONES: dict[str, str] = {
    # 深海（開場 / 路線圖 / CTA）— 沿用模板預設
    "deep": "",
    # 青（monitoring / scenario / 數據）
    "cyan": """
.bg{background:
 radial-gradient(1200px 800px at 22% 16%,rgba(56,189,248,.16),transparent 62%),
 radial-gradient(1100px 760px at 80% 84%,rgba(45,212,191,.14),transparent 60%),
 linear-gradient(160deg,#08192b 0%,#060e19 58%,#04070d 100%)}
.aur.a{background:radial-gradient(circle,rgba(56,189,248,.30),transparent 62%)}
.aur.b{background:radial-gradient(circle,rgba(45,212,191,.28),transparent 62%)}
""",
    # 金（cost）
    "amber": """
.bg{background:
 radial-gradient(1200px 800px at 24% 18%,rgba(251,191,36,.13),transparent 62%),
 radial-gradient(1100px 760px at 78% 82%,rgba(249,115,22,.11),transparent 60%),
 linear-gradient(160deg,#1c1608 0%,#100c06 58%,#080603 100%)}
.aur.a{background:radial-gradient(circle,rgba(251,191,36,.26),transparent 62%)}
.aur.b{background:radial-gradient(circle,rgba(249,115,22,.22),transparent 62%)}
.kicker{color:#fbbf24}.accent{color:#fbbf24}
.h1{background:linear-gradient(100deg,#fffaf0 20%,#fcd34d 52%,#fdba74 82%);-webkit-background-clip:text;background-clip:text;
 filter:drop-shadow(0 8px 40px rgba(251,191,36,.18))}
.badge{background:rgba(251,191,36,.13);border-color:rgba(251,191,36,.42);color:#fde09a}
""",
    # 紫（workflow）
    "violet": """
.bg{background:
 radial-gradient(1200px 800px at 24% 18%,rgba(167,139,250,.17),transparent 62%),
 radial-gradient(1100px 760px at 78% 82%,rgba(99,102,241,.15),transparent 60%),
 linear-gradient(160deg,#151130 0%,#0b0a1c 58%,#06050e 100%)}
.aur.a{background:radial-gradient(circle,rgba(167,139,250,.30),transparent 62%)}
.aur.b{background:radial-gradient(circle,rgba(99,102,241,.26),transparent 62%)}
.kicker{color:#c4b5fd}.accent{color:#c4b5fd}
.h1{background:linear-gradient(100deg,#f7f5ff 20%,#c4b5fd 52%,#a5b4fc 82%);-webkit-background-clip:text;background-clip:text;
 filter:drop-shadow(0 8px 40px rgba(167,139,250,.20))}
.badge{background:rgba(167,139,250,.14);border-color:rgba(167,139,250,.45);color:#ddd3ff}
""",
    # 藍紫（reporting）
    "indigo": """
.bg{background:
 radial-gradient(1200px 800px at 24% 18%,rgba(129,140,248,.15),transparent 62%),
 radial-gradient(1100px 760px at 78% 82%,rgba(56,189,248,.13),transparent 60%),
 linear-gradient(160deg,#0e1430 0%,#080c1c 58%,#05060f 100%)}
.aur.a{background:radial-gradient(circle,rgba(129,140,248,.28),transparent 62%)}
.aur.b{background:radial-gradient(circle,rgba(56,189,248,.24),transparent 62%)}
.kicker{color:#a5b4fc}.accent{color:#a5b4fc}
.h1{background:linear-gradient(100deg,#f5f7ff 20%,#a5b4fc 52%,#7dd3fc 82%);-webkit-background-clip:text;background-clip:text}
.badge{background:rgba(129,140,248,.14);border-color:rgba(129,140,248,.45);color:#ccd4ff}
""",
    # 綠（knowledge / RAG）
    "green": """
.bg{background:
 radial-gradient(1200px 800px at 24% 18%,rgba(52,211,153,.15),transparent 62%),
 radial-gradient(1100px 760px at 78% 82%,rgba(45,212,191,.13),transparent 60%),
 linear-gradient(160deg,#08221c 0%,#051411 58%,#030807 100%)}
.aur.a{background:radial-gradient(circle,rgba(52,211,153,.28),transparent 62%)}
.aur.b{background:radial-gradient(circle,rgba(45,212,191,.24),transparent 62%)}
.kicker{color:#34d399}.accent{color:#34d399}
.h1{background:linear-gradient(100deg,#f0fff9 20%,#6ee7b7 52%,#99f6e4 82%);-webkit-background-clip:text;background-clip:text}
.badge{background:rgba(52,211,153,.14);border-color:rgba(52,211,153,.45);color:#a7f3d0}
""",
    # 藍（auth）
    "blue": """
.bg{background:
 radial-gradient(1200px 800px at 24% 18%,rgba(56,189,248,.16),transparent 62%),
 radial-gradient(1100px 760px at 78% 82%,rgba(139,92,246,.12),transparent 60%),
 linear-gradient(160deg,#071a2e 0%,#050d1a 58%,#03060d 100%)}
.aur.a{background:radial-gradient(circle,rgba(56,189,248,.30),transparent 62%)}
.aur.b{background:radial-gradient(circle,rgba(139,92,246,.22),transparent 62%)}
.kicker{color:#7dd3fc}.accent{color:#7dd3fc}
.h1{background:linear-gradient(100deg,#f2faff 20%,#7dd3fc 52%,#c4b5fd 82%);-webkit-background-clip:text;background-clip:text}
""",
    # 高對比青（戲劇景）
    "blast": """
.bg{background:
 radial-gradient(1500px 1000px at 50% 46%,rgba(45,212,191,.22),transparent 58%),
 linear-gradient(160deg,#04141a 0%,#03090f 60%,#000203 100%)}
.aur.a{background:radial-gradient(circle,rgba(45,212,191,.40),transparent 60%);opacity:.7}
.aur.b{background:radial-gradient(circle,rgba(20,184,166,.32),transparent 60%);opacity:.6}
.vig{background:radial-gradient(1500px 950px at 50% 46%,transparent 50%,rgba(0,0,0,.72) 100%)}
""",
}

HEAD = """<!doctype html>
<!-- 由 promo/gen_scenes.py 產生，請改 gen_scenes.py 後重跑，不要直接改本檔。 -->
<html lang="zh-Hant"><head><meta charset="utf-8"><title>@@TITLE@@</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1920px;height:1080px;overflow:hidden;background:#070d17}
body{font-family:"Noto Sans CJK TC","Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif;color:#e8eef7;position:relative}
.bg{position:absolute;inset:0;background:
 radial-gradient(1200px 800px at 24% 18%,rgba(45,212,191,.14),transparent 62%),
 radial-gradient(1100px 760px at 78% 82%,rgba(139,92,246,.15),transparent 60%),
 linear-gradient(160deg,#0d1b2e 0%,#070d17 58%,#05070d 100%)}
.aur{position:absolute;width:1500px;height:1500px;border-radius:50%;filter:blur(90px);opacity:.5;mix-blend-mode:screen}
.aur.a{background:radial-gradient(circle,rgba(45,212,191,.32),transparent 62%);left:-460px;top:-560px;animation:drift1 22s ease-in-out infinite alternate}
.aur.b{background:radial-gradient(circle,rgba(139,92,246,.30),transparent 62%);right:-520px;bottom:-620px;animation:drift2 26s ease-in-out infinite alternate}
@keyframes drift1{to{transform:translate(150px,90px) scale(1.12)}}
@keyframes drift2{to{transform:translate(-130px,-80px) scale(1.08)}}
.vig{position:absolute;inset:0;background:radial-gradient(1600px 1000px at 50% 46%,transparent 58%,rgba(0,0,0,.5) 100%);pointer-events:none}
.grid{position:absolute;inset:0;opacity:.05;background-image:linear-gradient(rgba(232,238,247,.5) 1px,transparent 1px),linear-gradient(90deg,rgba(232,238,247,.5) 1px,transparent 1px);background-size:64px 64px}
.stage{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
 --dur:@@DUR@@s;animation:cam var(--dur) ease-in-out both}
@keyframes cam{from{transform:scale(1)}to{transform:scale(1.055)}}
.kicker{font-size:30px;font-weight:700;letter-spacing:.55em;text-indent:.55em;color:#2dd4bf;text-transform:uppercase;white-space:nowrap}
.h1{font-size:112px;font-weight:900;line-height:1.14;text-align:center;letter-spacing:.01em;
 background:linear-gradient(100deg,#f4f8ff 20%,#9be8db 50%,#c4b5fd 80%);-webkit-background-clip:text;background-clip:text;color:transparent;
 filter:drop-shadow(0 8px 40px rgba(45,212,191,.18))}
.sub{font-size:40px;font-weight:400;color:rgba(232,238,247,.78);text-align:center;line-height:1.6}
.accent{color:#2dd4bf;font-weight:700}
.chip{display:inline-flex;align-items:center;gap:16px;padding:20px 38px;border-radius:999px;font-size:36px;font-weight:700;white-space:nowrap;
 background:rgba(20,32,52,.82);border:1.5px solid rgba(150,200,255,.22);box-shadow:0 14px 40px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.07)}
.card{background:linear-gradient(165deg,rgba(24,38,62,.92),rgba(12,20,36,.94));border:1.5px solid rgba(150,200,255,.20);
 border-radius:26px;box-shadow:0 30px 80px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.08)}
.badge{display:inline-block;padding:12px 26px;border-radius:12px;font-size:28px;font-weight:700;white-space:nowrap;
 background:rgba(45,212,191,.14);border:1.5px solid rgba(45,212,191,.45);color:#7ff0df}
.in{opacity:0;animation:rise 1s cubic-bezier(.16,1,.3,1) both;animation-delay:var(--d,0s)}
@keyframes rise{from{opacity:0;transform:translateY(56px)}to{opacity:1;transform:none}}
.pop{opacity:0;animation:pop .8s cubic-bezier(.2,1.4,.35,1) both;animation-delay:var(--d,0s)}
@keyframes pop{from{opacity:0;transform:scale(.55)}to{opacity:1;transform:scale(1)}}
.glow{animation:glow 2.6s ease-in-out infinite}
@keyframes glow{0%,100%{filter:drop-shadow(0 0 18px rgba(45,212,191,.25))}50%{filter:drop-shadow(0 0 42px rgba(45,212,191,.55))}}
.in.glow{animation:rise 1s cubic-bezier(.16,1,.3,1) var(--d,0s) both,glow 2.6s ease-in-out infinite}
.pop.glow{animation:pop .8s cubic-bezier(.2,1.4,.35,1) var(--d,0s) both,glow 2.6s ease-in-out infinite}
/* ── 共用小元件（本片自訂） ── */
.row{display:flex;align-items:center;justify-content:center;gap:26px;flex-wrap:nowrap}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:34px}
.mod{padding:34px 30px;border-radius:24px;text-align:left;
 background:linear-gradient(165deg,rgba(24,38,62,.92),rgba(12,20,36,.94));
 border:1.5px solid rgba(150,200,255,.20);box-shadow:0 24px 64px rgba(0,0,0,.5),inset 0 1px 0 rgba(255,255,255,.07)}
.mod .mt{font-size:42px;font-weight:900;color:#f2f7ff;white-space:nowrap}
.mod .md{font-size:26px;color:rgba(232,238,247,.62);margin-top:12px;line-height:1.5}
.mod .ms{display:inline-block;margin-top:18px;padding:7px 18px;border-radius:10px;font-size:22px;font-weight:700;white-space:nowrap;
 background:rgba(45,212,191,.15);border:1px solid rgba(45,212,191,.42);color:#7ff0df}
.mod .ms.wip{background:rgba(251,191,36,.15);border-color:rgba(251,191,36,.45);color:#fde09a}
.bar{height:16px;border-radius:999px;background:rgba(150,200,255,.13);overflow:hidden}
.bar > i{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,#2dd4bf,#7dd3fc);width:0;
 animation:fill 1.9s cubic-bezier(.2,.9,.2,1) both;animation-delay:var(--d,0s)}
@keyframes fill{to{width:var(--w,70%)}}
.num{font-size:104px;font-weight:900;line-height:1;letter-spacing:-.02em;
 background:linear-gradient(100deg,#f4f8ff,#9be8db);-webkit-background-clip:text;background-clip:text;color:transparent}
.nlab{font-size:27px;color:rgba(232,238,247,.62);margin-top:14px;line-height:1.4;white-space:nowrap}
@@TONE@@
/* ▼ 本景專屬 ▼ */
@@CSS@@
</style></head>
<body>
<div class="bg"></div><div class="aur a"></div><div class="aur b"></div><div class="grid"></div>
@@FX@@
<div class="stage" style="z-index:2">
@@CONTENT@@
</div>
<div class="vig" style="z-index:3"></div>
</body></html>
"""

FX = """<canvas id="fx" style="position:absolute;inset:0;z-index:1;pointer-events:none"></canvas>
<script>
const cv=document.getElementById('fx');cv.width=1920;cv.height=1080;const cx=cv.getContext('2d');
const P=[];for(let i=0;i<80;i++){P.push({x:Math.random()*1920,y:Math.random()*1080,
 r:.8+Math.random()*2.6,s:.12+Math.random()*.5,o:.12+Math.random()*.4,
 hue:Math.random()<.6?'45,212,191':'167,139,250',ph:Math.random()*6.28});}
function draw(){const t=performance.now()/1000;cx.clearRect(0,0,1920,1080);
 for(const p of P){const y=(p.y-t*38*p.s)%1080,yy=y<0?y+1080:y;
  const x=p.x+Math.sin(t*.5+p.ph)*26;const tw=.55+.45*Math.sin(t*1.7+p.ph*3);
  cx.beginPath();cx.arc(x,yy,p.r,0,6.283);
  cx.fillStyle=`rgba(${p.hue},${(p.o*tw).toFixed(3)})`;cx.fill();}
 requestAnimationFrame(draw);}
requestAnimationFrame(draw);
</script>"""

# count-up 小工具：<span class="cu" data-to="998" data-d="1.2" data-t="1.6">0</span>
COUNTUP = """<script>
(function(){
 const els=[...document.querySelectorAll('.cu')];
 const t0=performance.now();
 function ease(x){return 1-Math.pow(1-x,3);}
 function tick(){
  const el=performance.now()-t0;
  for(const e of els){
   const to=parseFloat(e.dataset.to), d=(parseFloat(e.dataset.d)||0)*1000,
         dur=(parseFloat(e.dataset.t)||1.5)*1000, dec=parseInt(e.dataset.dec||'0');
   let p=(el-d)/dur; p=p<0?0:(p>1?1:p);
   const v=to*ease(p);
   e.textContent=dec?v.toFixed(dec):Math.round(v).toLocaleString('en-US');
  }
  requestAnimationFrame(tick);
 }
 requestAnimationFrame(tick);
})();
</script>"""


def scene(stem: str, title: str, dur: float, tone: str, content: str,
          css: str = "", fx: bool = False, countup: bool = False) -> None:
    body = content + (COUNTUP if countup else "")
    html = (HEAD
            .replace("@@TITLE@@", title)
            .replace("@@DUR@@", str(dur))
            .replace("@@TONE@@", TONES[tone])
            .replace("@@CSS@@", css)
            .replace("@@FX@@", FX if fx else "")
            .replace("@@CONTENT@@", body))
    (OUT / f"{stem}.html").write_text(html, encoding="utf-8")


# ═════════════════════════════════════════════════════════════════════════
# 18 景
# ═════════════════════════════════════════════════════════════════════════

# ── 第 1 章：開場 ─────────────────────────────────────────────────────────
scene("scene01_open", "S01 開場", 10, "deep", fx=True, css="""
.wm{font-size:196px;font-weight:900;letter-spacing:-.01em;line-height:1;
 background:linear-gradient(100deg,#f4f8ff 18%,#9be8db 50%,#c4b5fd 82%);-webkit-background-clip:text;background-clip:text;color:transparent;
 filter:drop-shadow(0 10px 56px rgba(45,212,191,.22))}
.zh{font-size:62px;font-weight:700;color:rgba(232,238,247,.9);letter-spacing:.16em;margin-top:26px}
.rule{width:340px;height:3px;margin:44px auto 0;border-radius:2px;
 background:linear-gradient(90deg,transparent,#2dd4bf,transparent);transform-origin:center;
 animation:wipe 1.4s cubic-bezier(.16,1,.3,1) both;animation-delay:1.5s}
@keyframes wipe{from{transform:scaleX(0);opacity:0}to{transform:scaleX(1);opacity:1}}
""", content="""
 <div class="kicker in" style="--d:.15s">OFFSHORE WIND O&amp;M PLATFORM</div>
 <div class="wm pop" style="--d:.5s;margin-top:34px">windMindOM</div>
 <div class="zh in" style="--d:1.15s">風心智運維平台</div>
 <div class="rule"></div>
 <div class="sub in" style="--d:2.1s;margin-top:44px">離岸風場運維廠商的一站式作業平台</div>
 <div class="row" style="margin-top:52px">
   <span class="badge in" style="--d:2.7s">監控</span>
   <span class="badge in" style="--d:2.85s">派工</span>
   <span class="badge in" style="--d:3.0s">成本</span>
   <span class="badge in" style="--d:3.15s">報表</span>
   <span class="badge in" style="--d:3.3s">知識</span>
 </div>
""")

scene("scene02_problem", "S02 問題", 10, "deep", css="""
.pain{width:1640px;display:grid;grid-template-columns:repeat(4,1fr);gap:32px;margin-top:64px}
.pc{padding:38px 30px;border-radius:24px;text-align:center;
 background:linear-gradient(165deg,rgba(38,28,24,.92),rgba(18,14,12,.94));
 border:1.5px solid rgba(251,146,60,.26);box-shadow:0 26px 70px rgba(0,0,0,.55)}
.pc .ic{font-size:64px;line-height:1}
.pc .tt{font-size:38px;font-weight:900;color:#f7efe8;margin-top:20px;white-space:nowrap}
.pc .dd{font-size:25px;color:rgba(247,239,232,.58);margin-top:12px;line-height:1.5}
.foot{margin-top:64px;font-size:42px;font-weight:700;color:#fbbf24;text-align:center;white-space:nowrap}
""", content="""
 <div class="kicker in" style="--d:.15s;color:#fb923c">THE PROBLEM</div>
 <div class="h1 in" style="--d:.5s;margin-top:26px;font-size:92px">運維資料，散在四個地方</div>
 <div class="pain">
   <div class="pc pop" style="--d:1.2s"><div class="ic">📈</div><div class="tt">SCADA</div><div class="dd">即時數據看得到<br>但看不出成本</div></div>
   <div class="pc pop" style="--d:1.45s"><div class="ic">📋</div><div class="tt">Excel 工單</div><div class="dd">派工靠表格<br>簽核靠 LINE</div></div>
   <div class="pc pop" style="--d:1.7s"><div class="ic">💰</div><div class="tt">另一套成本表</div><div class="dd">維修值不值得<br>事後才算得出來</div></div>
   <div class="pc pop" style="--d:1.95s"><div class="ic">📕</div><div class="tt">PDF 手冊</div><div class="dd">警報碼查排除<br>翻幾百頁</div></div>
 </div>
 <div class="foot in" style="--d:2.8s">每一次故障，工程師要開四個系統</div>
""")

scene("scene03_platform", "S03 六大模組", 11, "deep", css="""
.mg{width:1680px;display:grid;grid-template-columns:repeat(3,1fr);gap:32px;margin-top:56px}
""", content="""
 <div class="kicker in" style="--d:.15s">ONE PLATFORM · SIX MODULES</div>
 <div class="h1 in" style="--d:.5s;margin-top:26px;font-size:96px">一個平台，六個模組</div>
 <div class="mg">
   <div class="mod pop" style="--d:1.2s"><div class="mt">monitoring</div><div class="md">SCADA 即時監控 + 物理模擬器</div><div class="ms">既有</div></div>
   <div class="mod pop" style="--d:1.4s"><div class="mt">cost</div><div class="md">K13 成本模型 / LCOE / Monte Carlo</div><div class="ms">M2 done</div></div>
   <div class="mod pop" style="--d:1.6s"><div class="mt">workflow</div><div class="md">工單 + 多階簽核 + 庫存領料</div><div class="ms">M3-M4 done</div></div>
   <div class="mod pop" style="--d:1.8s"><div class="mt">reporting</div><div class="md">月報 PDF / 年度預算 / KPI</div><div class="ms">M4 done</div></div>
   <div class="mod pop" style="--d:2.0s"><div class="mt">knowledge</div><div class="md">RAG 警報查手冊</div><div class="ms wip">M5 進行中</div></div>
   <div class="mod pop" style="--d:2.2s"><div class="mt">auth</div><div class="md">JWT + RBAC 角色授權</div><div class="ms">M6 done</div></div>
 </div>
 <div class="sub in" style="--d:3.1s;margin-top:52px">同一個資料模型、同一組帳號、同一份現場流程</div>
""")

# ── 第 2 章：功能章 ───────────────────────────────────────────────────────
scene("scene04_monitoring", "S04 monitoring 概念", 10, "cyan", css="""
.mono{font-family:"Noto Sans Mono CJK TC",monospace}
""", content="""
 <div class="kicker in" style="--d:.15s">MODULE 01 · MONITORING</div>
 <div class="h1 in" style="--d:.5s;margin-top:28px;font-size:100px">看得見的，<br>不只是數字</div>
 <div class="sub in" style="--d:1.4s;margin-top:44px">
   SCADA 即時監控與<span class="accent">物理模擬器同源</span>——<br>
   模擬跑出來的訊號，走的是真實 SCADA 那條資料路徑
 </div>
 <div class="row" style="margin-top:60px">
   <span class="chip in" style="--d:2.2s">IEC 61400-12-1/2</span>
   <span class="chip in" style="--d:2.4s">Modbus TCP</span>
   <span class="chip in" style="--d:2.6s">OPC UA · Bachmann Z72</span>
 </div>
""")

scene("scene05_physics", "S05 monitoring 演示", 11, "cyan", countup=True, css="""
.panel{width:1680px;display:grid;grid-template-columns:1.05fr .95fr;gap:34px;margin-top:48px}
.pl{padding:38px 42px;border-radius:26px;background:linear-gradient(165deg,rgba(16,38,58,.94),rgba(8,20,34,.96));
 border:1.5px solid rgba(125,211,252,.24);box-shadow:0 30px 80px rgba(0,0,0,.55)}
.ph{font-size:25px;font-weight:700;letter-spacing:.3em;color:#7dd3fc;white-space:nowrap}
.tg{margin-top:26px}
.tg .tr{display:flex;align-items:center;gap:20px;margin-top:22px}
.tg .tn{font-size:27px;color:rgba(232,238,247,.66);width:180px;white-space:nowrap}
.tg .tb{flex:1}
.tg .tv{font-size:32px;font-weight:900;color:#e6f6ff;width:180px;text-align:right;white-space:nowrap}
.wake{position:relative;height:330px;margin-top:24px;border-radius:18px;overflow:hidden;background:rgba(3,12,22,.6);border:1px solid rgba(125,211,252,.16)}
.wt{position:absolute;width:20px;height:20px;border-radius:50%;background:#7dd3fc;box-shadow:0 0 22px rgba(125,211,252,.9)}
.wc{position:absolute;height:74px;border-radius:0 40px 40px 0;transform-origin:left center;
 background:linear-gradient(90deg,rgba(45,212,191,.42),rgba(45,212,191,.02));
 animation:grow 2.2s cubic-bezier(.2,.9,.2,1) both;animation-delay:var(--d,0s)}
@keyframes grow{from{opacity:0;transform:scaleX(.1)}to{opacity:1;transform:scaleX(1)}}
.bl{display:flex;gap:16px;flex-wrap:nowrap;margin-top:38px;justify-content:center}
""", content="""
 <div class="kicker in" style="--d:.15s">PHYSICS-COUPLED SIMULATION</div>
 <div class="h1 in" style="--d:.45s;margin-top:22px;font-size:80px">104 個 SCADA tag，11 種故障情境</div>
 <div class="panel">
   <div class="pl in" style="--d:1.1s">
     <div class="ph">LIVE TAGS</div>
     <div class="tg">
       <div class="tr"><div class="tn">風速 m/s</div><div class="tb bar"><i style="--w:62%;--d:1.4s"></i></div><div class="tv"><span class="cu" data-to="11.4" data-dec="1" data-d="1.4" data-t="1.8">0</span></div></div>
       <div class="tr"><div class="tn">功率 kW</div><div class="tb bar"><i style="--w:78%;--d:1.6s"></i></div><div class="tv"><span class="cu" data-to="3120" data-d="1.6" data-t="1.8">0</span></div></div>
       <div class="tr"><div class="tn">累積損傷</div><div class="tb bar"><i style="--w:34%;--d:1.8s"></i></div><div class="tv"><span class="cu" data-to="0.34" data-dec="2" data-d="1.8" data-t="1.8">0</span></div></div>
       <div class="tr"><div class="tn">RUL 年</div><div class="tb bar"><i style="--w:55%;--d:2.0s"></i></div><div class="tv"><span class="cu" data-to="13.2" data-dec="1" data-d="2.0" data-t="1.8">0</span></div></div>
     </div>
   </div>
   <div class="pl in" style="--d:1.3s">
     <div class="ph">GAUSSIAN WAKE + MEANDERING</div>
     <div class="wake">
       <div class="wc" style="left:120px;top:44px;width:560px;--d:1.9s"></div>
       <div class="wc" style="left:120px;top:140px;width:640px;--d:2.1s"></div>
       <div class="wc" style="left:120px;top:236px;width:520px;--d:2.3s"></div>
       <div class="wt" style="left:104px;top:71px"></div>
       <div class="wt" style="left:104px;top:167px"></div>
       <div class="wt" style="left:104px;top:263px"></div>
       <div class="wt" style="left:560px;top:167px;background:#fbbf24;box-shadow:0 0 22px rgba(251,191,36,.9)"></div>
     </div>
   </div>
 </div>
 <div class="bl">
   <span class="badge in" style="--d:2.9s">Bastankhah-Porté-Agel</span>
   <span class="badge in" style="--d:3.05s">大氣穩定度五重耦合</span>
   <span class="badge in" style="--d:3.2s">Fatigue / DEL</span>
   <span class="badge in" style="--d:3.35s">Miner damage → RUL</span>
 </div>
""")

scene("scene06_cost", "S06 cost 概念", 10, "amber", content="""
 <div class="kicker in" style="--d:.15s">MODULE 02 · COST</div>
 <div class="h1 in" style="--d:.5s;margin-top:28px;font-size:112px">這場維修，<br>值得嗎？</div>
 <div class="sub in" style="--d:1.4s;margin-top:46px">
   ECN <span class="accent">K13 成本模型</span>移植進平台——<br>
   出海一趟的船機、人時、備品，換回多少度電
 </div>
 <div class="row" style="margin-top:60px">
   <span class="chip in" style="--d:2.2s">farm-aware dataset</span>
   <span class="chip in" style="--d:2.4s">LCOE</span>
   <span class="chip in" style="--d:2.6s">20 年 var-fluct</span>
 </div>
""")

scene("scene07_cost_mock", "S07 cost 演示", 11, "amber", countup=True, css="""
.wrap{width:1660px;display:grid;grid-template-columns:.62fr 1fr;gap:38px;margin-top:46px;align-items:stretch}
.kpi{padding:40px 42px;border-radius:26px;background:linear-gradient(165deg,rgba(44,32,10,.94),rgba(22,16,6,.96));
 border:1.5px solid rgba(251,191,36,.28);box-shadow:0 30px 80px rgba(0,0,0,.55);display:flex;flex-direction:column;justify-content:center}
.kpi .kl{font-size:26px;letter-spacing:.28em;color:#fbbf24;white-space:nowrap}
.kpi .kv{font-size:112px;font-weight:900;line-height:1;margin-top:18px;
 background:linear-gradient(100deg,#fffaf0,#fcd34d);-webkit-background-clip:text;background-clip:text;color:transparent;white-space:nowrap}
.kpi .ku{font-size:28px;color:rgba(247,239,232,.6);margin-top:14px;white-space:nowrap}
.chart{padding:34px 40px 30px;border-radius:26px;background:linear-gradient(165deg,rgba(30,24,10,.94),rgba(16,12,6,.96));
 border:1.5px solid rgba(251,191,36,.24);box-shadow:0 30px 80px rgba(0,0,0,.55)}
.chart .ct{font-size:25px;letter-spacing:.24em;color:#fbbf24;white-space:nowrap}
.bars{display:flex;align-items:flex-end;gap:13px;height:280px;margin-top:26px}
.bars i{flex:1;border-radius:8px 8px 3px 3px;transform-origin:bottom;
 background:linear-gradient(180deg,#fcd34d,rgba(249,115,22,.55));
 animation:up 1.6s cubic-bezier(.2,.9,.2,1) both;animation-delay:var(--d,0s)}
@keyframes up{from{transform:scaleY(.02);opacity:.2}to{transform:scaleY(1);opacity:1}}
.xax{display:flex;justify-content:space-between;font-size:22px;color:rgba(247,239,232,.45);margin-top:14px}
""", content="""
 <div class="kicker in" style="--d:.15s">LCOE · MONTE CARLO</div>
 <div class="h1 in" style="--d:.45s;margin-top:22px;font-size:84px">20 年的成本，先跑一萬次</div>
 <div class="wrap">
   <div class="kpi in" style="--d:1.1s">
     <div class="kl">LCOE (P50)</div>
     <div class="kv"><span class="cu" data-to="72.4" data-dec="1" data-d="1.5" data-t="2.2">0</span></div>
     <div class="ku">EUR / MWh</div>
     <div style="margin-top:34px"><span class="badge">Monte Carlo × 10,000</span></div>
   </div>
   <div class="chart in" style="--d:1.3s">
     <div class="ct">ANNUAL O&amp;M COST · 20 YEARS</div>
     <div class="bars">
       <i style="height:34%;--d:1.6s"></i><i style="height:41%;--d:1.66s"></i><i style="height:38%;--d:1.72s"></i>
       <i style="height:52%;--d:1.78s"></i><i style="height:47%;--d:1.84s"></i><i style="height:61%;--d:1.9s"></i>
       <i style="height:55%;--d:1.96s"></i><i style="height:70%;--d:2.02s"></i><i style="height:64%;--d:2.08s"></i>
       <i style="height:78%;--d:2.14s"></i><i style="height:72%;--d:2.2s"></i><i style="height:86%;--d:2.26s"></i>
       <i style="height:80%;--d:2.32s"></i><i style="height:93%;--d:2.38s"></i><i style="height:88%;--d:2.44s"></i>
       <i style="height:100%;--d:2.5s"></i><i style="height:91%;--d:2.56s"></i><i style="height:97%;--d:2.62s"></i>
       <i style="height:89%;--d:2.68s"></i><i style="height:94%;--d:2.74s"></i>
     </div>
     <div class="xax"><span>Y1</span><span>Y5</span><span>Y10</span><span>Y15</span><span>Y20</span></div>
   </div>
 </div>
""")

scene("scene08_workflow", "S08 workflow 概念", 10, "violet", content="""
 <div class="kicker in" style="--d:.15s">MODULE 03 · WORKFLOW</div>
 <div class="h1 in" style="--d:.5s;margin-top:28px;font-size:92px">從發現故障，<br>到簽核完工</div>
 <div class="sub in" style="--d:1.4s;margin-top:44px">
   工單 × 多階簽核 × 庫存領料，<span class="accent">一條龍走完</span>——<br>
   不再一半在系統裡、一半在群組訊息裡
 </div>
 <div class="row" style="margin-top:60px">
   <span class="chip in" style="--d:2.2s">4 種工單類型</span>
   <span class="chip in" style="--d:2.4s">雙寫交易模型</span>
   <span class="chip in" style="--d:2.6s">領料 → 出庫 → 回沖</span>
 </div>
""")

scene("scene09_statemachine", "S09 工單狀態機", 11, "violet", css="""
.pipe{width:1740px;margin-top:56px}
.track{display:flex;align-items:stretch;gap:0;position:relative}
.st{flex:1;text-align:center}
.st .dot{width:30px;height:30px;border-radius:50%;margin:0 auto;background:rgba(167,139,250,.22);border:2.5px solid rgba(167,139,250,.5);
 animation:lit 1s cubic-bezier(.2,1.4,.35,1) both;animation-delay:var(--d,0s)}
@keyframes lit{from{opacity:.2;transform:scale(.4)}to{opacity:1;transform:scale(1);background:#c4b5fd;box-shadow:0 0 30px rgba(196,181,253,.85)}}
.st .sn{font-size:29px;font-weight:900;color:#f2efff;margin-top:22px;white-space:nowrap}
.st .sd{font-size:23px;color:rgba(232,238,247,.55);margin-top:10px;white-space:nowrap}
.line{position:absolute;left:9%;right:9%;top:14px;height:4px;border-radius:2px;background:rgba(167,139,250,.16);z-index:-1}
.line > i{display:block;height:100%;border-radius:2px;background:linear-gradient(90deg,#c4b5fd,#818cf8);width:0;
 animation:fill2 2.6s cubic-bezier(.2,.9,.2,1) both;animation-delay:1.2s}
@keyframes fill2{to{width:100%}}
.alt{display:flex;gap:20px;justify-content:center;margin-top:56px}
.alt span{padding:12px 28px;border-radius:12px;font-size:26px;font-weight:700;white-space:nowrap;
 background:rgba(148,163,184,.12);border:1.5px solid rgba(148,163,184,.32);color:rgba(226,232,240,.78)}
""", content="""
 <div class="kicker in" style="--d:.15s">7-STATE WORK ORDER MACHINE</div>
 <div class="h1 in" style="--d:.45s;margin-top:22px;font-size:80px">狀態機管著每一張工單</div>
 <div class="pipe in" style="--d:1.0s">
   <div class="track">
     <div class="line"><i></i></div>
     <div class="st"><div class="dot" style="--d:1.3s"></div><div class="sn">DRAFT</div><div class="sd">開單</div></div>
     <div class="st"><div class="dot" style="--d:1.9s"></div><div class="sn">DISPATCHED</div><div class="sd">派工 · 等天氣窗</div></div>
     <div class="st"><div class="dot" style="--d:2.5s"></div><div class="sn">IN_PROGRESS</div><div class="sd">維修進行中</div></div>
     <div class="st"><div class="dot" style="--d:3.1s"></div><div class="sn">AWAITING_SIGNOFF</div><div class="sd">完工待簽核</div></div>
     <div class="st"><div class="dot" style="--d:3.7s"></div><div class="sn">CLOSED</div><div class="sd">關單</div></div>
   </div>
 </div>
 <div class="alt">
   <span class="in" style="--d:4.3s">CANCELLED 取消</span>
   <span class="in" style="--d:4.45s">REOPENED 追蹤重開</span>
   <span class="in" style="--d:4.6s">簽核 chain：組長 → 主管 → 總務</span>
 </div>
""")

scene("scene10_reporting", "S10 reporting", 10, "indigo", countup=True, css="""
.doc{width:1520px;display:grid;grid-template-columns:1fr 1fr;gap:34px;margin-top:52px}
.dc{padding:36px 40px;border-radius:26px;background:linear-gradient(165deg,rgba(20,28,58,.94),rgba(10,14,32,.96));
 border:1.5px solid rgba(129,140,248,.26);box-shadow:0 30px 80px rgba(0,0,0,.55);text-align:left}
.dc .dh{font-size:25px;letter-spacing:.26em;color:#a5b4fc;white-space:nowrap}
.kv{display:flex;justify-content:space-between;align-items:baseline;margin-top:26px}
.kv .k{font-size:28px;color:rgba(232,238,247,.6);white-space:nowrap}
.kv .v{font-size:44px;font-weight:900;color:#eef2ff;white-space:nowrap}
.lines{margin-top:26px}
.lines i{display:block;height:13px;border-radius:999px;background:rgba(165,180,252,.2);margin-top:15px;width:0;
 animation:fill 1.5s cubic-bezier(.2,.9,.2,1) both;animation-delay:var(--d,0s)}
""", content="""
 <div class="kicker in" style="--d:.15s">MODULE 04 · REPORTING</div>
 <div class="h1 in" style="--d:.45s;margin-top:22px;font-size:92px">月報，不再手工做</div>
 <div class="doc">
   <div class="dc in" style="--d:1.1s">
     <div class="dh">MONTHLY REPORT · PDF</div>
     <div class="lines">
       <i style="--w:96%;--d:1.5s"></i><i style="--w:82%;--d:1.62s"></i><i style="--w:90%;--d:1.74s"></i>
       <i style="--w:68%;--d:1.86s"></i><i style="--w:88%;--d:1.98s"></i><i style="--w:54%;--d:2.1s"></i>
     </div>
     <div style="margin-top:32px"><span class="badge">一鍵產出 · iframe 預覽</span></div>
   </div>
   <div class="dc in" style="--d:1.3s">
     <div class="dh">KPI &amp; 年度預算</div>
     <div class="kv"><span class="k">工單完成率</span><span class="v"><span class="cu" data-to="94" data-d="1.7" data-t="1.6">0</span>%</span></div>
     <div class="kv"><span class="k">平均修復時間</span><span class="v"><span class="cu" data-to="8.6" data-dec="1" data-d="1.9" data-t="1.6">0</span> h</span></div>
     <div class="kv"><span class="k">備品週轉</span><span class="v"><span class="cu" data-to="3.2" data-dec="1" data-d="2.1" data-t="1.6">0</span> ×</span></div>
     <div class="kv"><span class="k">預算執行率</span><span class="v"><span class="cu" data-to="87" data-d="2.3" data-t="1.6">0</span>%</span></div>
   </div>
 </div>
""")

scene("scene11_knowledge", "S11 knowledge RAG", 11, "green", css="""
.flow{width:1700px;display:grid;grid-template-columns:.7fr 100px 1.3fr;gap:26px;align-items:center;margin-top:52px}
.alm{padding:40px 34px;border-radius:26px;text-align:center;
 background:linear-gradient(165deg,rgba(48,26,10,.94),rgba(24,14,6,.96));
 border:1.5px solid rgba(251,146,60,.38);box-shadow:0 30px 80px rgba(0,0,0,.55)}
.alm .al{font-size:24px;letter-spacing:.26em;color:#fb923c;white-space:nowrap}
.alm .ac{font-family:"Noto Sans Mono CJK TC",monospace;font-size:76px;font-weight:900;color:#fed7aa;margin-top:18px;white-space:nowrap}
.alm .ad{font-size:26px;color:rgba(254,215,170,.65);margin-top:14px;white-space:nowrap}
.arw{font-size:76px;color:#34d399;text-align:center;
 animation:sh 1.8s ease-in-out infinite;animation-delay:2.2s;opacity:0}
@keyframes sh{0%{opacity:.35;transform:translateX(-14px)}50%{opacity:1;transform:translateX(10px)}100%{opacity:.35;transform:translateX(-14px)}}
.man{padding:34px 40px;border-radius:26px;text-align:left;
 background:linear-gradient(165deg,rgba(10,40,32,.94),rgba(5,20,17,.96));
 border:1.5px solid rgba(52,211,153,.3);box-shadow:0 30px 80px rgba(0,0,0,.55)}
.man .mh{font-size:24px;letter-spacing:.24em;color:#34d399;white-space:nowrap}
.man .mq{font-size:34px;line-height:1.6;color:#e9fff8;margin-top:22px}
.man .mm{font-size:24px;color:rgba(167,243,208,.72);margin-top:22px;white-space:nowrap}
""", content="""
 <div class="kicker in" style="--d:.15s">MODULE 05 · KNOWLEDGE · RAG</div>
 <div class="h1 in" style="--d:.45s;margin-top:22px;font-size:78px">警報碼丟進去，手冊段落跳出來</div>
 <div class="flow">
   <div class="alm pop" style="--d:1.1s">
     <div class="al">ALARM</div>
     <div class="ac">3172</div>
     <div class="ad">主軸承溫度高</div>
   </div>
   <div class="arw">➜</div>
   <div class="man in" style="--d:2.0s">
     <div class="mh">Z72 USER MANUAL · TOP-1 CHUNK</div>
     <div class="mq">「主軸承溫度超過 85°C 時，先確認潤滑油泵運轉與濾網壓差；若壓差 &gt; 1.5 bar 應先更換濾芯再復歸警報……」</div>
     <div class="mm">§ 7.4.2　排除步驟　·　相似度 0.91</div>
   </div>
 </div>
 <div class="row" style="margin-top:52px">
   <span class="badge in" style="--d:3.0s">531 chunks 真語料</span>
   <span class="badge in" style="--d:3.15s">研究端策略檔</span>
   <span class="badge in" style="--d:3.3s">預計算向量檔</span>
   <span class="badge in" style="--d:3.45s">ChromaDB</span>
 </div>
""")

scene("scene12_auth", "S12 auth", 10, "blue", css="""
.roles{width:1680px;display:grid;grid-template-columns:repeat(4,1fr);gap:28px;margin-top:52px}
.rc{padding:34px 28px;border-radius:24px;text-align:center;
 background:linear-gradient(165deg,rgba(12,32,54,.94),rgba(6,16,30,.96));
 border:1.5px solid rgba(125,211,252,.26);box-shadow:0 26px 68px rgba(0,0,0,.5)}
.rc .rl{font-family:"Noto Sans Mono CJK TC",monospace;font-size:30px;font-weight:900;color:#7dd3fc;white-space:nowrap}
.rc .rz{font-size:34px;font-weight:900;color:#f2faff;margin-top:16px;white-space:nowrap}
.rc .rp{font-size:23px;color:rgba(232,238,247,.55);margin-top:14px;line-height:1.5}
.rc .rk{margin-top:18px;font-size:22px;font-weight:700;color:#a5b4fc;white-space:nowrap}
""", content="""
 <div class="kicker in" style="--d:.15s">MODULE 06 · AUTH</div>
 <div class="h1 in" style="--d:.45s;margin-top:22px;font-size:92px">誰能簽核，系統說了算</div>
 <div class="roles">
   <div class="rc pop" style="--d:1.1s"><div class="rl">EMPLOYEE</div><div class="rz">現場工程師</div><div class="rp">派工簽收<br>完工申報</div><div class="rk">level 100</div></div>
   <div class="rc pop" style="--d:1.3s"><div class="rl">LEADER</div><div class="rz">組長</div><div class="rp">第一階簽核<br>工單派發</div><div class="rk">level 300</div></div>
   <div class="rc pop" style="--d:1.5s"><div class="rl">SUPERVISOR</div><div class="rz">主管</div><div class="rp">成本核可<br>第二階簽核</div><div class="rk">level 500</div></div>
   <div class="rc pop" style="--d:1.7s"><div class="rl">TREASURY</div><div class="rz">總務 · 庫管</div><div class="rp">領料出庫<br>庫存盤點</div><div class="rk">level 666</div></div>
 </div>
 <div class="row" style="margin-top:54px">
   <span class="badge in" style="--d:2.5s">JWT HS256</span>
   <span class="badge in" style="--d:2.65s">PBKDF2 純 stdlib</span>
   <span class="badge in" style="--d:2.8s">61+ 端點全面授權</span>
 </div>
""")

# ── 第 3 章：戲劇景（全片唯一，前一刀 fadeblack）─────────────────────────
scene("scene13_drama", "S13 戲劇景 Simulator-first", 12, "blast", fx=True, css="""
.big{font-size:132px;font-weight:900;line-height:1.16;text-align:center;letter-spacing:.01em;
 background:linear-gradient(100deg,#ffffff 15%,#7ff0df 52%,#5eead4 85%);-webkit-background-clip:text;background-clip:text;color:transparent;
 filter:drop-shadow(0 12px 60px rgba(45,212,191,.35));
 animation:slam 1.1s cubic-bezier(.16,1,.3,1) both;animation-delay:.8s}
@keyframes slam{0%{opacity:0;transform:scale(1.22)}60%{opacity:1;transform:scale(.985)}100%{opacity:1;transform:scale(1)}}
.shake{animation:shk .5s ease-in-out both;animation-delay:1.85s}
@keyframes shk{0%,100%{transform:translate(0,0)}18%{transform:translate(-9px,4px)}38%{transform:translate(8px,-5px)}58%{transform:translate(-5px,-3px)}78%{transform:translate(4px,3px)}}
.mark{font-size:34px;font-weight:900;letter-spacing:.5em;text-indent:.5em;color:#5eead4;white-space:nowrap;
 animation:rise 1.1s cubic-bezier(.16,1,.3,1) both;animation-delay:.2s;opacity:0}
.punch{margin-top:58px;font-size:46px;font-weight:700;color:#ffffff;text-align:center;line-height:1.55}
.hair{width:520px;height:2px;margin:52px auto 0;background:linear-gradient(90deg,transparent,rgba(94,234,212,.9),transparent);
 animation:wipe2 1.3s cubic-bezier(.16,1,.3,1) both;animation-delay:3.2s;transform-origin:center}
@keyframes wipe2{from{transform:scaleX(0);opacity:0}to{transform:scaleX(1);opacity:1}}
.last{margin-top:44px;font-size:38px;color:rgba(232,238,247,.72);text-align:center;white-space:nowrap}
""", content="""
 <div class="mark">SIMULATOR-FIRST</div>
 <div class="shake" style="margin-top:40px">
   <div class="big">沒有實場，<br>也能完整 demo</div>
 </div>
 <div class="punch in" style="--d:2.6s">
   物理模擬器與真實 SCADA <span class="accent">走同一條資料路徑</span>
 </div>
 <div class="hair"></div>
 <div class="last in" style="--d:3.9s">客戶不必先把機組交給你，你就能證明平台真的會動</div>
""")

# ── 第 4 章：成果章 ───────────────────────────────────────────────────────
scene("scene14_scenario", "S14 情境模式", 11, "cyan", css="""
.cmp{width:1700px;display:grid;grid-template-columns:1fr 1fr;gap:36px;margin-top:48px}
.cc{padding:34px 40px;border-radius:26px;background:linear-gradient(165deg,rgba(10,30,50,.94),rgba(5,14,26,.96));
 border:1.5px solid rgba(125,211,252,.24);box-shadow:0 30px 80px rgba(0,0,0,.55)}
.cc.f{border-color:rgba(251,146,60,.36)}
.cc .ch{font-size:25px;letter-spacing:.24em;white-space:nowrap;color:#7dd3fc}
.cc.f .ch{color:#fb923c}
.spark{position:relative;height:250px;margin-top:26px;border-radius:16px;overflow:hidden;
 background:rgba(3,12,22,.55);border:1px solid rgba(125,211,252,.14)}
.spark svg{position:absolute;inset:0;width:100%;height:100%}
.spark path{fill:none;stroke-width:5;stroke-linecap:round;
 stroke-dasharray:2000;stroke-dashoffset:2000;animation:trace 2.6s cubic-bezier(.3,.8,.3,1) both;animation-delay:var(--d,0s)}
@keyframes trace{to{stroke-dashoffset:0}}
.cc .cf{font-size:27px;color:rgba(232,238,247,.62);margin-top:22px;white-space:nowrap}
.cc .cf b{color:#e6f6ff;font-size:32px}
""", content="""
 <div class="kicker in" style="--d:.15s">SCENARIO MODE · DEC-20260720-01</div>
 <div class="h1 in" style="--d:.45s;margin-top:22px;font-size:82px">情境＝一份凍結的資料集</div>
 <div class="cmp">
   <div class="cc f in" style="--d:1.1s">
     <div class="ch">FAULTED GROUP</div>
     <div class="spark"><svg viewBox="0 0 700 250" preserveAspectRatio="none">
       <path style="--d:1.5s;stroke:#fb923c" d="M10,70 L100,84 L190,72 L280,96 L370,150 L460,186 L550,206 L690,222"/>
     </svg></div>
     <div class="cf">結束 RUL <b>9.4 年</b>　·　累積損傷 <b>0.61</b></div>
   </div>
   <div class="cc in" style="--d:1.3s">
     <div class="ch">HEALTHY GROUP</div>
     <div class="spark"><svg viewBox="0 0 700 250" preserveAspectRatio="none">
       <path style="--d:1.7s;stroke:#2dd4bf" d="M10,66 L100,78 L190,64 L280,80 L370,70 L460,86 L550,74 L690,88"/>
     </svg></div>
     <div class="cf">結束 RUL <b>16.8 年</b>　·　累積損傷 <b>0.22</b></div>
   </div>
 </div>
 <div class="row" style="margin-top:48px">
   <span class="badge in" style="--d:2.9s">重播同一份資料</span>
   <span class="badge in" style="--d:3.05s">faulted vs healthy 分群</span>
   <span class="badge in" style="--d:3.2s">情境摘要 API</span>
 </div>
""")

scene("scene15_numbers", "S15 數據", 11, "cyan", countup=True, css="""
.ng{width:1740px;display:grid;grid-template-columns:repeat(3,1fr);gap:44px 40px;margin-top:52px}
.nc{text-align:center;padding:26px 16px}
.nc .num{font-size:112px}
""", content="""
 <div class="kicker in" style="--d:.15s">BY THE NUMBERS</div>
 <div class="h1 in" style="--d:.45s;margin-top:20px;font-size:84px">不是簡報，是跑得動的系統</div>
 <div class="ng">
   <div class="nc pop" style="--d:1.1s"><div class="num"><span class="cu" data-to="6" data-d="1.4" data-t="1.4">0</span></div><div class="nlab">功能模組</div></div>
   <div class="nc pop" style="--d:1.28s"><div class="num"><span class="cu" data-to="998" data-d="1.5" data-t="1.9">0</span></div><div class="nlab">backend pytest</div></div>
   <div class="nc pop" style="--d:1.46s"><div class="num"><span class="cu" data-to="957" data-d="1.6" data-t="1.9">0</span></div><div class="nlab">frontend vitest</div></div>
   <div class="nc pop" style="--d:1.64s"><div class="num"><span class="cu" data-to="104" data-d="1.7" data-t="1.7">0</span></div><div class="nlab">SCADA tags</div></div>
   <div class="nc pop" style="--d:1.82s"><div class="num"><span class="cu" data-to="40" data-d="1.8" data-t="1.5">0</span>+</div><div class="nlab">REST / WebSocket 端點</div></div>
   <div class="nc pop" style="--d:2.0s"><div class="num"><span class="cu" data-to="11" data-d="1.9" data-t="1.5">0</span></div><div class="nlab">故障情境</div></div>
 </div>
 <div class="sub in" style="--d:3.0s;margin-top:46px">CI 每次 push 跑完 6 個 module + physics 驗證 + e2e lifecycle</div>
""")

scene("scene16_persona", "S16 雙 persona", 10, "cyan", css="""
.two{width:1700px;display:grid;grid-template-columns:1fr 1fr;gap:40px;margin-top:52px}
.pcol{padding:40px 44px;border-radius:28px;text-align:left;box-shadow:0 30px 80px rgba(0,0,0,.55)}
.pcol.a{background:linear-gradient(165deg,rgba(10,30,52,.94),rgba(5,14,28,.96));border:1.5px solid rgba(125,211,252,.26)}
.pcol.b{background:linear-gradient(165deg,rgba(24,20,50,.94),rgba(12,10,26,.96));border:1.5px solid rgba(167,139,250,.28)}
.pcol .pi{font-size:56px;line-height:1}
.pcol .pn{font-size:48px;font-weight:900;margin-top:18px;white-space:nowrap}
.pcol.a .pn{color:#bfe9ff}.pcol.b .pn{color:#ddd3ff}
.pcol .pw{font-size:25px;letter-spacing:.2em;margin-top:12px;white-space:nowrap}
.pcol.a .pw{color:#7dd3fc}.pcol.b .pw{color:#c4b5fd}
.pcol ul{margin-top:26px;list-style:none}
.pcol li{font-size:31px;color:rgba(232,238,247,.8);margin-top:17px;padding-left:38px;position:relative;white-space:nowrap}
.pcol li:before{content:"▸";position:absolute;left:0;top:0}
.pcol.a li:before{color:#2dd4bf}.pcol.b li:before{color:#a78bfa}
""", content="""
 <div class="kicker in" style="--d:.15s">TWO PERSONAS · ONE SYSTEM</div>
 <div class="h1 in" style="--d:.45s;margin-top:20px;font-size:92px">一套系統，兩種現場</div>
 <div class="two">
   <div class="pcol a in" style="--d:1.1s">
     <div class="pi">🖥️</div>
     <div class="pn">管理層</div>
     <div class="pw">DESKTOP</div>
     <ul>
       <li>成本試算與 LCOE 決策</li>
       <li>月報 / 年度預算 / KPI</li>
       <li>多階簽核與庫存總覽</li>
     </ul>
   </div>
   <div class="pcol b in" style="--d:1.35s">
     <div class="pi">📱</div>
     <div class="pn">現場工程師</div>
     <div class="pw">MOBILE</div>
     <ul>
       <li>手機收派工單、拍照回報</li>
       <li>領料掃碼、完工申報</li>
       <li>警報碼即時查手冊</li>
     </ul>
   </div>
 </div>
""")

# ── 第 5 章：路線圖 + CTA ─────────────────────────────────────────────────
scene("scene17_roadmap", "S17 路線圖", 10.2, "deep", css="""
.gt{width:1600px;margin-top:56px}
.gr{display:flex;align-items:center;gap:28px;margin-top:22px}
.gr .gl{width:400px;text-align:right;font-size:30px;font-weight:700;color:rgba(232,238,247,.8);white-space:nowrap}
.gr .gb{flex:1;height:34px;border-radius:999px;background:rgba(150,200,255,.08);position:relative;overflow:hidden}
.gr .gb > i{position:absolute;top:0;bottom:0;border-radius:999px;transform-origin:left center;
 background:linear-gradient(90deg,#2dd4bf,#7dd3fc);
 animation:gw 1.5s cubic-bezier(.2,.9,.2,1) both;animation-delay:var(--d,0s)}
.gr .gb > i.wip{background:linear-gradient(90deg,#fbbf24,#fb923c)}
@keyframes gw{from{opacity:0;transform:scaleX(.02)}to{opacity:1;transform:scaleX(1)}}
.gr .gp{width:150px;font-size:27px;font-weight:700;color:rgba(232,238,247,.62);white-space:nowrap}
.goal{margin-top:58px;font-size:44px;font-weight:700;text-align:center;color:#e8eef7;white-space:nowrap}
""", content="""
 <div class="kicker in" style="--d:.15s">ROADMAP · M1 → M6</div>
 <div class="h1 in" style="--d:.45s;margin-top:20px;font-size:86px">六個月，一步一個模組</div>
 <div class="gt">
   <div class="gr in" style="--d:1.0s"><div class="gl">M1　搬遷 baseline</div><div class="gb"><i style="left:0;width:17%;--d:1.3s"></i></div><div class="gp">2026-05</div></div>
   <div class="gr in" style="--d:1.15s"><div class="gl">M2　cost</div><div class="gb"><i style="left:16%;width:17%;--d:1.45s"></i></div><div class="gp">✅ done</div></div>
   <div class="gr in" style="--d:1.3s"><div class="gl">M3　workflow 工單簽核</div><div class="gb"><i style="left:32%;width:17%;--d:1.6s"></i></div><div class="gp">✅ done</div></div>
   <div class="gr in" style="--d:1.45s"><div class="gl">M4　庫存 + reporting</div><div class="gb"><i style="left:48%;width:17%;--d:1.75s"></i></div><div class="gp">✅ done</div></div>
   <div class="gr in" style="--d:1.6s"><div class="gl">M5　knowledge + mobile</div><div class="gb"><i class="wip" style="left:64%;width:17%;--d:1.9s"></i></div><div class="gp">🟡 75%</div></div>
   <div class="gr in" style="--d:1.75s"><div class="gl">M6　PoC + 第一筆合約</div><div class="gb"><i class="wip" style="left:80%;width:19%;--d:2.05s"></i></div><div class="gp">2026-10</div></div>
 </div>
 <div class="goal in" style="--d:2.9s">目標：<span class="accent">2026 Q4</span>　Z72 機型運維廠商 PoC + 第一筆合約</div>
""")

scene("scene18_cta", "S18 CTA", 11, "deep", fx=True, css="""
.wm{font-size:172px;font-weight:900;letter-spacing:-.01em;line-height:1;
 background:linear-gradient(100deg,#f4f8ff 18%,#9be8db 50%,#c4b5fd 82%);-webkit-background-clip:text;background-clip:text;color:transparent;
 filter:drop-shadow(0 10px 56px rgba(45,212,191,.22))}
.zh{font-size:52px;font-weight:700;color:rgba(232,238,247,.86);letter-spacing:.18em;margin-top:22px;white-space:nowrap}
.link{margin-top:56px;font-family:"Noto Sans Mono CJK TC",monospace;font-size:44px;font-weight:700;color:#7ff0df;white-space:nowrap}
.sig{margin-top:34px;font-size:28px;color:rgba(232,238,247,.5);white-space:nowrap}
.rule{width:400px;height:3px;margin:40px auto 0;border-radius:2px;
 background:linear-gradient(90deg,transparent,#2dd4bf,transparent);transform-origin:center;
 animation:wipe 1.4s cubic-bezier(.16,1,.3,1) both;animation-delay:2.6s}
@keyframes wipe{from{transform:scaleX(0);opacity:0}to{transform:scaleX(1);opacity:1}}
""", content="""
 <div class="wm pop" style="--d:.3s">windMindOM</div>
 <div class="zh in" style="--d:1.0s">風心智運維平台</div>
 <div class="row" style="margin-top:52px">
   <span class="chip in" style="--d:1.6s">Simulator-first</span>
   <span class="chip in" style="--d:1.78s">六大模組一體</span>
   <span class="chip in" style="--d:1.96s">FastAPI + React</span>
 </div>
 <div class="rule"></div>
 <div class="link in" style="--d:3.3s">github.com/dofliu/windMindOM</div>
 <div class="sig in" style="--d:4.0s">從 digiWindTurbine 商業化升級　·　v0.8.1</div>
""")

# ═════════════════════════════════════════════════════════════════════════
STORYBOARD = {
    "fps": 30, "width": 1920, "height": 1080, "xfade": 0.6,
    "scenes": [
        {"file": "scene01_open.html",         "duration": 10,   "transition": "fade"},
        {"file": "scene02_problem.html",      "duration": 10,   "transition": "smoothleft"},
        {"file": "scene03_platform.html",     "duration": 11,   "transition": "circleopen"},
        {"file": "scene04_monitoring.html",   "duration": 10,   "transition": "fade"},
        {"file": "scene05_physics.html",      "duration": 11,   "transition": "smoothup"},
        {"file": "scene06_cost.html",         "duration": 10,   "transition": "fade"},
        {"file": "scene07_cost_mock.html",    "duration": 11,   "transition": "circleopen"},
        {"file": "scene08_workflow.html",     "duration": 10,   "transition": "fade"},
        {"file": "scene09_statemachine.html", "duration": 11,   "transition": "smoothleft"},
        {"file": "scene10_reporting.html",    "duration": 10,   "transition": "fade"},
        {"file": "scene11_knowledge.html",    "duration": 11,   "transition": "smoothup"},
        {"file": "scene12_auth.html",         "duration": 10,   "transition": "fadeblack"},
        {"file": "scene13_drama.html",        "duration": 12,   "transition": "fade"},
        {"file": "scene14_scenario.html",     "duration": 11,   "transition": "smoothleft"},
        {"file": "scene15_numbers.html",      "duration": 11,   "transition": "circleopen"},
        {"file": "scene16_persona.html",      "duration": 10,   "transition": "fade"},
        {"file": "scene17_roadmap.html",      "duration": 10.2, "transition": "fade"},
        {"file": "scene18_cta.html",          "duration": 11},
    ],
}

(OUT / "storyboard.json").write_text(
    json.dumps(STORYBOARD, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

_total = sum(s["duration"] for s in STORYBOARD["scenes"]) - \
    (len(STORYBOARD["scenes"]) - 1) * STORYBOARD["xfade"]
print(f"18 scenes written → {OUT}")
print(f"預期成片長度：{_total:.1f}s")
