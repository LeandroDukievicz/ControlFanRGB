#!/usr/bin/env python3
"""Gera os mockups de layout do ControlFanRGB (HTML -> PNG via chrome headless).

Uso:  python3 _gerar.py          # gera HTML + PNG de todos os mockups
      python3 _gerar.py --html   # so o HTML (pra abrir no navegador e mexer)
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1440, 920

# ---------------------------------------------------------------- teclado ----
# PH315-54: teclado com numpad. Larguras em "unidades" de tecla.
MAIN_ROWS = [
    [("esc",1),("F1",1),("F2",1),("F3",1),("F4",1),("F5",1),("F6",1),("F7",1),
     ("F8",1),("F9",1),("F10",1),("F11",1),("F12",1),("del",2)],
    [("~",1),("1",1),("2",1),("3",1),("4",1),("5",1),("6",1),("7",1),("8",1),
     ("9",1),("0",1),("-",1),("=",1),("⌫",2)],
    [("tab",1.5),("Q",1),("W",1),("E",1),("R",1),("T",1),("Y",1),("U",1),("I",1),
     ("O",1),("P",1),("[",1),("]",1),("\\",1.5)],
    [("caps",1.75),("A",1),("S",1),("D",1),("F",1),("G",1),("H",1),("J",1),("K",1),
     ("L",1),(";",1),("'",1),("enter",2.25)],
    [("shift",2.25),("Z",1),("X",1),("C",1),("V",1),("B",1),("N",1),("M",1),
     (",",1),(".",1),("/",1),("shift",1.75),("↑",1)],
    [("ctrl",1.25),("fn",1.25),("⊞",1.25),("alt",1.25),("space",4.75),("alt",1.25),
     ("ctrl",1.25),("←",1),("↓",1),("→",1)],
]
NUM_ROWS = [
    [("num",1),("/",1),("*",1),("-",1)],
    [("7",1),("8",1),("9",1),("+",1)],
    [("4",1),("5",1),("6",1),("",1)],
    [("1",1),("2",1),("3",1),("⏎",1)],
    [("0",2),(".",1),("",1)],
]
MAIN_FRAC = 0.785          # fatia da largura total ocupada pelo bloco principal

ZONE_COLORS = ["#ff2d6f", "#b14aed", "#4f7cff", "#2de2ff"]

# destaques tecla-a-tecla usados no mockup "per key"
PERKEY = {
    "W": "#ff3b30", "A": "#ff3b30", "S": "#ff3b30", "D": "#ff3b30",
    "shift": "#ffb020", "space": "#ffb020", "ctrl": "#ffb020",
    "↑": "#2de2ff", "↓": "#2de2ff", "←": "#2de2ff", "→": "#2de2ff",
    "esc": "#ffffff", "Q": "#9dff3c", "E": "#9dff3c", "R": "#9dff3c",
}

def _zone(center):
    return min(3, int(center * 4))

def keyboard(mode="zones", scale=1.0):
    """mode: 'zones' (4 faixas) | 'perkey' (tecla a tecla) | 'flat'"""
    out = [f'<div class="kb" style="--kbs:{scale}">', '<div class="kb-main">']
    for row in MAIN_ROWS:
        total = sum(w for _, w in row)
        out.append('<div class="kb-row">')
        cum = 0.0
        for label, w in row:
            center = MAIN_FRAC * (cum + w / 2) / total
            cum += w
            z = _zone(center)
            col = ZONE_COLORS[z]
            if mode == "perkey" and label in PERKEY:
                col = PERKEY[label]
            elif mode == "perkey":
                col = "#1b1d2a"
            elif mode == "flat":
                col = "#1b1d2a"
            long = "" if len(label) <= 2 else " kb-wide"
            out.append(
                f'<div class="kb-key{long}" style="flex:{w};--kc:{col}">'
                f'<span>{label}</span></div>')
        out.append('</div>')
    out.append('</div><div class="kb-num">')
    for row in NUM_ROWS:
        out.append('<div class="kb-row">')
        cum = 0.0
        for label, w in row:
            center = MAIN_FRAC + (1 - MAIN_FRAC) * (cum + w / 2) / 4
            cum += w
            col = ZONE_COLORS[_zone(center)]
            if mode == "perkey":
                col = PERKEY.get(label, "#1b1d2a")
            elif mode == "flat":
                col = "#1b1d2a"
            empty = " kb-empty" if label == "" else ""
            out.append(f'<div class="kb-key{empty}" style="flex:{w};--kc:{col}">'
                       f'<span>{label}</span></div>')
        out.append('</div>')
    out.append('</div></div>')
    return "".join(out)

def gauge(pct, label, value, unit, color, size=108):
    r, c = 44, 2 * 3.14159 * 44
    off = c * (1 - pct)
    return f'''<div class="gauge" style="--gc:{color};width:{size}px">
<svg viewBox="0 0 100 100"><circle class="gbg" cx="50" cy="50" r="{r}"/>
<circle class="gfg" cx="50" cy="50" r="{r}"
 style="stroke-dasharray:{c:.1f};stroke-dashoffset:{off:.1f}"/></svg>
<div class="gval"><b>{value}</b><i>{unit}</i></div>
<div class="glab">{label}</div></div>'''

def sparkline(points, color, w=240, h=52):
    n = len(points)
    mx, mn = max(points), min(points)
    rng = (mx - mn) or 1
    pts = " ".join(f"{i/(n-1)*w:.1f},{h - (p-mn)/rng*(h-8) - 4:.1f}"
                   for i, p in enumerate(points))
    return f'''<svg class="spark" viewBox="0 0 {w} {h}" style="--sc:{color}">
<polyline points="{pts}"/>
<polyline class="fill" points="0,{h} {pts} {w},{h}"/></svg>'''

RPM = [2100,2180,2240,2190,2350,2600,2980,3310,3620,3910,4120,4080,4210,4330,4290,4260]

# ------------------------------------------------------------------- css ----
BASE_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1440px;height:920px;overflow:hidden}
body{font-family:'Rajdhani','Inter',system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace}
.disp{font-family:'Orbitron','Rajdhani',sans-serif;letter-spacing:.06em}

/* ---- teclado ---- */
.kb{display:flex;gap:calc(10px*var(--kbs));padding:calc(12px*var(--kbs));
    border-radius:14px;background:#0a0b12;border:1px solid rgba(255,255,255,.07)}
.kb-main{flex:var(--mf,785);display:flex;flex-direction:column;gap:calc(5px*var(--kbs))}
.kb-num{flex:215;display:flex;flex-direction:column;gap:calc(5px*var(--kbs))}
.kb-row{display:flex;gap:calc(5px*var(--kbs))}
.kb-key{position:relative;height:calc(30px*var(--kbs));border-radius:calc(5px*var(--kbs));
    background:linear-gradient(#20222f,#14161f);display:grid;place-items:center;
    box-shadow:inset 0 0 0 1px rgba(255,255,255,.05),
               inset 0 calc(-1px*var(--kbs)) 0 rgba(0,0,0,.6),
               0 0 calc(14px*var(--kbs)) -2px var(--kc);overflow:hidden}
.kb-key::before{content:'';position:absolute;inset:0;background:var(--kc);opacity:.5}
.kb-key::after{content:'';position:absolute;inset:0;
    background:radial-gradient(120% 140% at 50% 120%,rgba(255,255,255,.35),transparent 60%)}
.kb-key span{position:relative;z-index:2;font-size:calc(10px*var(--kbs));font-weight:600;
    color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.8);letter-spacing:.02em}
.kb-key.kb-wide span{font-size:calc(8.5px*var(--kbs));text-transform:uppercase;opacity:.9}
.kb-key.kb-empty{opacity:0;box-shadow:none}

/* ---- gauges ---- */
.gauge{position:relative;aspect-ratio:1;display:grid;place-items:center}
.gauge svg{position:absolute;inset:0;transform:rotate(-135deg)}
.gauge circle{fill:none;stroke-width:7;stroke-linecap:round}
.gbg{stroke:rgba(255,255,255,.08)}
.gfg{stroke:var(--gc);filter:drop-shadow(0 0 6px var(--gc))}
.gval{text-align:center;line-height:1}
.gval b{font-family:'JetBrains Mono',monospace;font-size:21px;color:#fff;font-weight:700}
.gval i{display:block;font-style:normal;font-size:9px;letter-spacing:.14em;
    color:rgba(255,255,255,.45);margin-top:3px}
.glab{position:absolute;bottom:-17px;font-size:10px;letter-spacing:.16em;
    text-transform:uppercase;color:rgba(255,255,255,.5);white-space:nowrap}

/* ---- sparkline ---- */
.spark{width:100%;height:52px}
.spark polyline{fill:none;stroke:var(--sc);stroke-width:2;stroke-linejoin:round}
.spark polyline.fill{fill:color-mix(in srgb,var(--sc) 16%,transparent);stroke:none}
"""

def page(title, css, body, fonts=True):
    f = ('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?'
         'family=Orbitron:wght@500;700;900&family=Rajdhani:wght@400;500;600;700&'
         'family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@400;500;600;700'
         '&display=swap" rel="stylesheet">') if fonts else ''
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<title>{title}</title>{f}<style>{BASE_CSS}{css}</style></head>'
            f'<body>{body}</body></html>')

# =========================================================== A — CYBER HUD ===
CSS_A = """
body{background:
  radial-gradient(1100px 700px at 12% -10%,#1b0f2e 0%,transparent 60%),
  radial-gradient(900px 600px at 96% 8%,#04232c 0%,transparent 55%),#06060b;
  color:#e8eaf2;display:flex}
.rail{width:62px;border-right:1px solid rgba(255,255,255,.06);
  display:flex;flex-direction:column;align-items:center;gap:6px;padding:14px 0;
  background:rgba(0,0,0,.35)}
.rail .logo{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;
  background:linear-gradient(140deg,#ff2d6f,#8b5cf6);font-weight:900;font-size:15px;
  color:#fff;margin-bottom:12px;box-shadow:0 0 18px -4px #ff2d6f}
.rail a{width:40px;height:38px;border-radius:9px;display:grid;place-items:center;
  font-size:17px;color:rgba(255,255,255,.4);text-decoration:none}
.rail a.on{background:rgba(45,226,255,.12);color:#2de2ff;
  box-shadow:inset 0 0 0 1px rgba(45,226,255,.3)}
.rail .sp{flex:1}
.wrap{flex:1;display:flex;flex-direction:column;min-width:0}
.top{height:52px;display:flex;align-items:center;gap:14px;padding:0 20px;
  border-bottom:1px solid rgba(255,255,255,.06)}
.top h1{font-size:15px;font-weight:700;letter-spacing:.14em}
.top h1 em{font-style:normal;color:#2de2ff}
.chip{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;padding:4px 9px;
  border-radius:20px;border:1px solid rgba(255,255,255,.12);color:rgba(255,255,255,.6)}
.chip.live{border-color:rgba(157,255,60,.35);color:#9dff3c;background:rgba(157,255,60,.07)}
.dot{display:inline-block;width:5px;height:5px;border-radius:50%;background:#9dff3c;
  margin-right:6px;box-shadow:0 0 7px #9dff3c}
.body{flex:1;display:grid;grid-template-columns:1fr 286px;min-height:0}
.main{padding:18px 20px;display:flex;flex-direction:column;gap:14px;min-width:0}
.side{border-left:1px solid rgba(255,255,255,.06);padding:18px 18px;
  display:flex;flex-direction:column;gap:16px;background:rgba(0,0,0,.22)}
.lbl{font-size:9.5px;letter-spacing:.2em;text-transform:uppercase;
  color:rgba(255,255,255,.38);margin-bottom:9px;display:flex;
  justify-content:space-between;align-items:center}
.lbl b{color:#2de2ff;font-weight:700;letter-spacing:.1em}
.zones{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}
.zone{border-radius:9px;padding:9px 10px;background:#0d0e16;
  border:1px solid rgba(255,255,255,.07);display:flex;align-items:center;gap:8px}
.zone.sel{border-color:#2de2ff;box-shadow:0 0 0 1px #2de2ff,0 0 16px -6px #2de2ff}
.sw{width:22px;height:22px;border-radius:6px;box-shadow:0 0 12px -2px var(--c);
  background:var(--c);flex:none}
.zone i{font-style:normal;font-size:9px;letter-spacing:.12em;
  color:rgba(255,255,255,.45);text-transform:uppercase;display:block}
.zone b{font-size:11px;font-family:'JetBrains Mono',monospace;color:#fff}
.modes{display:flex;flex-wrap:wrap;gap:6px}
.mode{padding:7px 12px;border-radius:7px;font-size:11.5px;font-weight:600;
  background:#0d0e16;border:1px solid rgba(255,255,255,.07);color:rgba(255,255,255,.62)}
.mode.on{background:linear-gradient(135deg,#ff2d6f,#8b5cf6);color:#fff;border-color:transparent;
  box-shadow:0 0 18px -6px #ff2d6f}
.mode.new{border-color:rgba(157,255,60,.3);color:#9dff3c}
.turbo{display:grid;grid-template-columns:auto 1fr auto;gap:18px;align-items:center;
  padding:14px 18px;border-radius:13px;
  background:linear-gradient(100deg,rgba(255,45,111,.14),rgba(139,92,246,.06) 60%,transparent);
  border:1px solid rgba(255,45,111,.28)}
.tbtn{width:92px;height:92px;border-radius:50%;display:grid;place-items:center;
  background:radial-gradient(circle at 50% 35%,#ff5c8a,#c1003c);color:#fff;
  box-shadow:0 0 34px -6px #ff2d6f,inset 0 -3px 10px rgba(0,0,0,.4);text-align:center}
.tbtn b{display:block;font-family:'Orbitron',sans-serif;font-size:16px;font-weight:900;
  letter-spacing:.08em}
.tbtn i{font-style:normal;font-size:9px;letter-spacing:.18em;opacity:.85}
.tinfo h3{font-family:'Orbitron',sans-serif;font-size:13px;letter-spacing:.1em;margin-bottom:5px}
.tinfo p{font-size:12px;color:rgba(255,255,255,.52);line-height:1.5;max-width:330px}
.kbd{font-family:'JetBrains Mono',monospace;font-size:10.5px;padding:2px 6px;
  border-radius:4px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.13);
  color:#fff}
.dials{display:flex;gap:26px;padding-right:6px}
.wheel{width:100%;aspect-ratio:1;border-radius:50%;position:relative;
  background:conic-gradient(#ff2d6f,#ffb020,#9dff3c,#2de2ff,#4f7cff,#b14aed,#ff2d6f);
  box-shadow:0 0 36px -12px #b14aed,inset 0 0 0 1px rgba(255,255,255,.12)}
.wheel::after{content:'';position:absolute;inset:26%;border-radius:50%;
  background:#0a0b12;box-shadow:inset 0 0 0 1px rgba(255,255,255,.08)}
.wheel .pick{position:absolute;width:17px;height:17px;border-radius:50%;
  border:2.5px solid #fff;top:14%;left:62%;box-shadow:0 2px 8px rgba(0,0,0,.6)}
.hex{display:flex;gap:7px;align-items:center;margin-top:12px}
.hex .box{flex:1;background:#0d0e16;border:1px solid rgba(255,255,255,.09);
  border-radius:7px;padding:7px 10px;font-family:'JetBrains Mono',monospace;
  font-size:12px;color:#2de2ff}
.sl{margin-top:13px}
.sl .t{display:flex;justify-content:space-between;font-size:10.5px;
  color:rgba(255,255,255,.5);margin-bottom:6px;letter-spacing:.06em}
.sl .t b{font-family:'JetBrains Mono',monospace;color:#fff}
.track{height:5px;border-radius:4px;background:rgba(255,255,255,.1);position:relative}
.track i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;
  background:linear-gradient(90deg,#8b5cf6,#2de2ff)}
.track b{position:absolute;top:50%;width:13px;height:13px;border-radius:50%;
  background:#fff;transform:translate(-50%,-50%);box-shadow:0 0 10px #2de2ff}
.presets{display:grid;grid-template-columns:1fr 1fr;gap:7px}
.pre{border-radius:8px;padding:8px 9px;background:#0d0e16;
  border:1px solid rgba(255,255,255,.07)}
.pre .bar{height:7px;border-radius:3px;margin-bottom:7px}
.pre span{font-size:10.5px;color:rgba(255,255,255,.7);font-weight:600}
.pre.on{border-color:#2de2ff}
"""

BODY_A = f"""
<div class="rail">
  <div class="logo">P</div>
  <a class="on" title="Iluminação">◉</a><a title="Resfriamento">❄</a>
  <a title="Perfis">▤</a><a title="Macros">⌘</a><div class="sp"></div>
  <a title="Ajustes">⚙</a>
</div>
<div class="wrap">
  <div class="top">
    <h1 class="disp">PULSE<em>DECK</em></h1>
    <span class="chip">Predator PH315-54</span>
    <span class="chip live"><span class="dot"></span>daemon ativo</span>
    <div style="flex:1"></div>
    <span class="chip">perfil: <b style="color:#fff">Vapor</b></span>
  </div>
  <div class="body">
    <div class="main">
      <div>
        <div class="lbl">Teclado <span>4 zonas · clique numa tecla pra pintar <b>→ resolve pra zona</b></span></div>
        {keyboard("zones", 1.42)}
      </div>
      <div class="zones">
        <div class="zone sel" style="--c:#ff2d6f"><div class="sw"></div><div><i>zona 1</i><b>#FF2D6F</b></div></div>
        <div class="zone" style="--c:#b14aed"><div class="sw"></div><div><i>zona 2</i><b>#B14AED</b></div></div>
        <div class="zone" style="--c:#4f7cff"><div class="sw"></div><div><i>zona 3</i><b>#4F7CFF</b></div></div>
        <div class="zone" style="--c:#2de2ff"><div class="sw"></div><div><i>zona 4</i><b>#2DE2FF</b></div></div>
      </div>
      <div>
        <div class="lbl">Efeito</div>
        <div class="modes">
          <span class="mode">Estático</span><span class="mode">Respiração</span>
          <span class="mode">Neon</span><span class="mode on">Onda</span>
          <span class="mode">Shifting</span><span class="mode">Zoom</span>
          <span class="mode new">+ Arco-íris</span><span class="mode new">+ Carga CPU</span>
          <span class="mode new">+ Áudio</span>
        </div>
      </div>
      <div class="turbo">
        <div class="tbtn"><div><b>ON</b><i>TURBO</i></div></div>
        <div class="tinfo">
          <h3>Modo turbo ligado</h3>
          <p>Ventoinhas em máximo e overclock liberado. Atalho global
          <span class="kbd">Super</span>+<span class="kbd">T</span> — ou a tecla Turbo do chassi.</p>
        </div>
        <div class="dials">
          {gauge(.84,"Vent. CPU","4290","RPM","#ff2d6f")}
          {gauge(.88,"Vent. GPU","4610","RPM","#2de2ff")}
          {gauge(.72,"CPU","72","°C","#ffb020")}
        </div>
      </div>
    </div>
    <div class="side">
      <div>
        <div class="lbl">Cor da zona 1</div>
        <div class="wheel"><div class="pick"></div></div>
        <div class="hex"><div class="box">#FF2D6F</div>
          <div class="box" style="flex:none;color:rgba(255,255,255,.5)">HSV</div></div>
      </div>
      <div>
        <div class="sl"><div class="t"><span>Brilho</span><b>100%</b></div>
          <div class="track"><i style="width:100%"></i><b style="left:100%"></b></div></div>
        <div class="sl"><div class="t"><span>Velocidade</span><b>5</b></div>
          <div class="track"><i style="width:55%"></i><b style="left:55%"></b></div></div>
        <div class="sl"><div class="t"><span>Direção</span><b>→</b></div>
          <div class="track"><i style="width:100%"></i><b style="left:100%"></b></div></div>
      </div>
      <div>
        <div class="lbl">Temas prontos</div>
        <div class="presets">
          <div class="pre on"><div class="bar" style="background:linear-gradient(90deg,#ff2d6f,#b14aed,#4f7cff,#2de2ff)"></div><span>Vapor</span></div>
          <div class="pre"><div class="bar" style="background:linear-gradient(90deg,#39ff14,#0aff9d,#00e0ff,#0066ff)"></div><span>Matrix</span></div>
          <div class="pre"><div class="bar" style="background:linear-gradient(90deg,#ff0040,#ff6a00,#ffd000,#ff0040)"></div><span>Inferno</span></div>
          <div class="pre"><div class="bar" style="background:linear-gradient(90deg,#00e5ff,#2979ff,#7c4dff,#00e5ff)"></div><span>Glacial</span></div>
          <div class="pre"><div class="bar" style="background:linear-gradient(90deg,#ffe8c2,#ffd089,#ffb347,#ff8c42)"></div><span>Âmbar</span></div>
          <div class="pre"><div class="bar" style="background:linear-gradient(90deg,#009b3a,#ffdf00,#002776,#009b3a)"></div><span>Brasil</span></div>
        </div>
      </div>
      <div>
        <div class="lbl">Ventoinhas · últimos 60 s</div>
        {sparkline(RPM,"#2de2ff")}
      </div>
    </div>
  </div>
</div>
"""

# ====================================================== B — GNOME / ADWAITA ===
CSS_B = """
body{background:#f6f5f4;color:#2e3436;font-family:'Inter',system-ui,sans-serif;
  display:flex;flex-direction:column}
.hb{height:47px;display:flex;align-items:center;gap:9px;padding:0 10px;
  background:#fff;border-bottom:1px solid #dcdad5;flex:none}
.hb .ttl{font-size:13.5px;font-weight:700;flex:1;text-align:center}
.hb .ttl i{display:block;font-style:normal;font-size:11px;font-weight:400;color:#8b8e8f}
.ibtn{width:30px;height:30px;border-radius:7px;display:grid;place-items:center;
  background:#f0efee;border:1px solid #dcdad5;font-size:14px;color:#5e5c64;flex:none}
.ibtn.sug{background:#1c71d8;border-color:#1c71d8;color:#fff;width:auto;padding:0 13px;
  font-size:12.5px;font-weight:600}
.split{flex:1;display:flex;min-height:0}
.sb{width:224px;background:#ebe8e6;border-right:1px solid #dcdad5;padding:9px 8px;flex:none}
.sb .sh{font-size:10px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;
  color:#9a9996;padding:9px 9px 6px}
.sb .it{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:8px;
  font-size:13px;color:#3d3846;margin-bottom:1px}
.sb .it.on{background:#1c71d8;color:#fff;font-weight:600}
.sb .it .ic2{width:18px;text-align:center;font-size:14px;opacity:.8}
.sb .it .bd{margin-left:auto;font-size:10.5px;font-weight:700;padding:1px 7px;border-radius:9px;
  background:#fde8e8;color:#c01c28}
.sb .it.on .bd{background:rgba(255,255,255,.22);color:#fff}
.pg{flex:1;padding:17px 22px;display:flex;flex-direction:column;gap:14px;min-width:0}
.grp{background:#fff;border:1px solid #dcdad5;border-radius:12px;overflow:hidden;
  box-shadow:0 1px 2px rgba(0,0,0,.03)}
.gt{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:#8b8e8f;margin:0 0 6px 3px}
.row{display:flex;align-items:center;gap:12px;padding:10px 14px;border-top:1px solid #f0efee}
.row .ic{width:29px;height:29px;border-radius:8px;display:grid;place-items:center;
  font-size:14px;background:#f0efee;color:#5e5c64;flex:none}
.row .tx{flex:1}
.row .tx b{display:block;font-size:13px;font-weight:600}
.row .tx i{font-style:normal;font-size:11.5px;color:#8b8e8f}
.sw2{width:41px;height:23px;border-radius:13px;background:#1c71d8;position:relative;flex:none}
.sw2::after{content:'';position:absolute;top:2px;right:2px;width:19px;height:19px;
  border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.2)}
.pill{font-size:11px;font-weight:700;padding:3px 10px;border-radius:13px;
  background:#f0efee;color:#5e5c64}
.pill.blue{background:#e1effd;color:#1c71d8}
.pill.red{background:#fde8e8;color:#c01c28}
.kbcard{padding:13px}
.chips{display:flex;gap:6px;padding:0 13px 12px;flex-wrap:wrap}
.chips span{font-size:11.5px;font-weight:600;padding:5px 11px;border-radius:8px;
  background:#f0efee;color:#5e5c64;border:1px solid #dcdad5}
.chips span.on{background:#1c71d8;color:#fff;border-color:#1c71d8}
.chips span.nw{background:#eaf6ec;color:#26a269;border-color:#bfe3c6}
.themes{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;padding:13px}
.th{border-radius:9px;overflow:hidden;border:2px solid transparent;background:#f6f5f4}
.th.on{border-color:#1c71d8}
.th .bar{height:25px}
.th span{display:block;font-size:10.5px;font-weight:600;padding:5px 7px;color:#5e5c64}
.fan2{display:grid;grid-template-columns:1fr 1fr;gap:13px;padding:13px}
.fbox{border:1px solid #dcdad5;border-radius:10px;padding:11px 13px;background:#fafafa}
.fbox .n{font-family:'JetBrains Mono',monospace;font-size:24px;font-weight:700}
.fbox .n i{font-style:normal;font-size:11.5px;color:#8b8e8f;font-weight:500;margin-left:4px}
.fbox .k{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:#8b8e8f;margin-bottom:3px}
"""

BODY_B = f"""
<div class="hb">
  <div class="ibtn">☰</div>
  <div class="ttl">ControlFanRGB<i>Predator PH315-54 · 4 zonas · daemon conectado</i></div>
  <div class="ibtn">⌕</div><div class="ibtn sug">Aplicar</div>
</div>
<div class="split">
  <div class="sb">
    <div class="sh">Teclado</div>
    <div class="it on"><span class="ic2">◉</span>Iluminação</div>
    <div class="it"><span class="ic2">▦</span>Temas</div>
    <div class="it"><span class="ic2">✎</span>Tecla a tecla</div>
    <div class="sh">Sistema</div>
    <div class="it"><span class="ic2">❄</span>Resfriamento<span class="bd">TURBO</span></div>
    <div class="it"><span class="ic2">⚡</span>Energia</div>
    <div class="it"><span class="ic2">▤</span>Perfis</div>
    <div class="sh">App</div>
    <div class="it"><span class="ic2">⌨</span>Atalhos</div>
    <div class="it"><span class="ic2">⚙</span>Preferências</div>
  </div>
  <div class="pg">
    <div>
      <div class="gt">Iluminação</div>
      <div class="grp">
        <div class="kbcard">{keyboard("zones",1.25)}</div>
        <div class="chips">
          <span class="on">Onda</span><span>Estático</span><span>Respiração</span>
          <span>Neon</span><span>Shifting</span><span>Zoom</span>
          <span class="nw">Arco-íris ✨</span><span class="nw">Carga da CPU ✨</span>
          <span class="nw">Áudio ✨</span>
        </div>
        <div class="row"><div class="ic">◉</div><div class="tx"><b>Pintar tecla a tecla</b>
          <i>Escolha teclas individuais — a cor é resolvida na zona correspondente</i></div>
          <span class="pill blue">4 zonas</span></div>
        <div class="row"><div class="ic">☀</div><div class="tx"><b>Brilho</b>
          <i>Reduz junto com o brilho da tela</i></div><span class="pill">100%</span></div>
      </div>
    </div>
    <div>
      <div class="gt">Temas</div>
      <div class="grp"><div class="themes">
        <div class="th on"><div class="bar" style="background:linear-gradient(90deg,#ff2d6f,#b14aed,#4f7cff,#2de2ff)"></div><span>Vapor</span></div>
        <div class="th"><div class="bar" style="background:linear-gradient(90deg,#39ff14,#0aff9d,#00e0ff,#0066ff)"></div><span>Matrix</span></div>
        <div class="th"><div class="bar" style="background:linear-gradient(90deg,#ff0040,#ff6a00,#ffd000,#ff0040)"></div><span>Inferno</span></div>
        <div class="th"><div class="bar" style="background:linear-gradient(90deg,#00e5ff,#2979ff,#7c4dff,#00e5ff)"></div><span>Glacial</span></div>
        <div class="th"><div class="bar" style="background:linear-gradient(90deg,#ffe8c2,#ffd089,#ffb347,#ff8c42)"></div><span>Âmbar</span></div>
        <div class="th"><div class="bar" style="background:linear-gradient(90deg,#009b3a,#ffdf00,#002776,#009b3a)"></div><span>Brasil</span></div>
      </div></div>
    </div>
    <div>
      <div class="gt">Resfriamento</div>
      <div class="grp">
        <div class="row" style="border-top:none"><div class="ic" style="background:#fde8e8;color:#c01c28">🔥</div>
          <div class="tx"><b>Modo turbo</b><i>Ventoinhas no máximo + overclock · atalho Super+T</i></div>
          <span class="pill red">LIGADO</span><div class="sw2"></div></div>
        <div class="fan2">
          <div class="fbox"><div class="k">Ventoinha CPU</div>
            <div class="n">4290<i>rpm</i></div>{sparkline(RPM,"#c01c28")}</div>
          <div class="fbox"><div class="k">Ventoinha GPU</div>
            <div class="n">4610<i>rpm</i></div>{sparkline([r+320 for r in RPM],"#1c71d8")}</div>
        </div>
      </div>
    </div>
  </div>
</div>
"""

# =============================================== C — COMPACTO / TRAY + OSD ===
CSS_C = """
body{background:
  radial-gradient(900px 600px at 20% 15%,#2a1b4d,transparent 60%),
  radial-gradient(800px 600px at 85% 80%,#0d3b4a,transparent 60%),#0b0a12;
  color:#e8eaf2;position:relative;overflow:hidden}
.desk{position:absolute;inset:0;opacity:.5;
  background-image:repeating-linear-gradient(90deg,rgba(255,255,255,.03) 0 1px,transparent 1px 46px),
   repeating-linear-gradient(0deg,rgba(255,255,255,.03) 0 1px,transparent 1px 46px)}
.panel{position:absolute;top:0;left:0;right:0;height:30px;background:rgba(0,0,0,.55);
  backdrop-filter:blur(14px);display:flex;align-items:center;padding:0 14px;gap:16px;
  font-size:11.5px;color:rgba(255,255,255,.7)}
.panel .sp{flex:1}
.panel .tray{display:flex;gap:11px;align-items:center;font-size:13px}
.panel .tray .act{color:#2de2ff;text-shadow:0 0 10px #2de2ff}

/* janela compacta */
.win{position:absolute;top:52px;right:36px;width:372px;border-radius:14px;overflow:hidden;
  background:rgba(14,15,23,.93);backdrop-filter:blur(26px);
  border:1px solid rgba(255,255,255,.1);box-shadow:0 30px 70px -18px rgba(0,0,0,.85)}
.wh{display:flex;align-items:center;gap:9px;padding:11px 13px;
  border-bottom:1px solid rgba(255,255,255,.07)}
.wh .lg{width:22px;height:22px;border-radius:6px;background:linear-gradient(140deg,#ff2d6f,#8b5cf6);
  display:grid;place-items:center;font-size:11px;font-weight:900}
.wh b{font-size:12.5px;letter-spacing:.1em}
.wh .x{margin-left:auto;display:flex;gap:6px}
.wh .x i{width:11px;height:11px;border-radius:50%;background:rgba(255,255,255,.18);font-style:normal}
.wc{padding:13px}
.wl{font-size:9px;letter-spacing:.2em;text-transform:uppercase;color:rgba(255,255,255,.35);
  margin:12px 0 7px}
.wl:first-child{margin-top:0}
.sws{display:flex;gap:7px}
.sws .s{flex:1;height:32px;border-radius:8px;background:var(--c);
  box-shadow:0 0 14px -3px var(--c);border:1px solid rgba(255,255,255,.14)}
.sws .s.sel{outline:2px solid #fff;outline-offset:2px}
.mrow{display:flex;gap:5px;flex-wrap:wrap}
.mrow span{font-size:10.5px;font-weight:600;padding:5px 9px;border-radius:6px;
  background:rgba(255,255,255,.06);color:rgba(255,255,255,.6)}
.mrow span.on{background:linear-gradient(135deg,#ff2d6f,#8b5cf6);color:#fff}
.tline{display:flex;align-items:center;gap:11px;margin-top:14px;padding:11px 12px;
  border-radius:10px;background:rgba(255,45,111,.12);border:1px solid rgba(255,45,111,.3)}
.tline .big{font-family:'Orbitron',sans-serif;font-size:13px;font-weight:900;color:#ff5c8a}
.tline .rp{margin-left:auto;text-align:right;font-family:'JetBrains Mono',monospace;
  font-size:11px;line-height:1.5;color:rgba(255,255,255,.8)}
.tsw{width:40px;height:22px;border-radius:12px;background:#ff2d6f;position:relative;flex:none;
  box-shadow:0 0 14px -3px #ff2d6f}
.tsw::after{content:'';position:absolute;top:2px;right:2px;width:18px;height:18px;
  border-radius:50%;background:#fff}

/* menu do tray */
.menu{position:absolute;top:36px;left:50%;transform:translateX(-50%);width:252px;
  border-radius:12px;background:rgba(18,19,28,.96);backdrop-filter:blur(22px);
  border:1px solid rgba(255,255,255,.1);box-shadow:0 26px 60px -16px rgba(0,0,0,.85);
  padding:7px;font-size:12.5px}
.menu .mi{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:8px;
  color:rgba(255,255,255,.82)}
.menu .mi.hl{background:rgba(255,255,255,.08)}
.menu .mi .k{margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:10px;
  color:rgba(255,255,255,.35)}
.menu .hr{height:1px;background:rgba(255,255,255,.08);margin:5px 8px}
.menu .mi .sq{width:13px;height:13px;border-radius:4px;background:var(--c)}

/* OSD */
.osd{position:absolute;left:50%;bottom:92px;transform:translateX(-50%);
  display:flex;align-items:center;gap:20px;padding:19px 30px;border-radius:18px;
  background:rgba(10,10,16,.88);backdrop-filter:blur(30px);
  border:1px solid rgba(255,45,111,.35);
  box-shadow:0 0 60px -10px rgba(255,45,111,.55),0 30px 60px -20px #000}
.osd .ring{width:66px;height:66px;border-radius:50%;display:grid;place-items:center;
  background:radial-gradient(circle at 50% 35%,#ff5c8a,#c1003c);
  font-family:'Orbitron',sans-serif;font-weight:900;font-size:19px;
  box-shadow:0 0 30px -4px #ff2d6f}
.osd h2{font-family:'Orbitron',sans-serif;font-size:17px;letter-spacing:.1em;margin-bottom:5px}
.osd p{font-size:12px;color:rgba(255,255,255,.55)}
.osd .st{display:flex;gap:22px;padding-left:22px;border-left:1px solid rgba(255,255,255,.12)}
.osd .st div{text-align:center}
.osd .st b{display:block;font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:700}
.osd .st i{font-style:normal;font-size:9px;letter-spacing:.16em;text-transform:uppercase;
  color:rgba(255,255,255,.4)}
.track{height:5px;border-radius:4px;background:rgba(255,255,255,.1);position:relative;
  margin-bottom:2px}
.track i{position:absolute;left:0;top:0;bottom:0;border-radius:4px;
  background:linear-gradient(90deg,#8b5cf6,#2de2ff)}
.track b{position:absolute;top:50%;width:12px;height:12px;border-radius:50%;
  background:#fff;transform:translate(-50%,-50%);box-shadow:0 0 10px #2de2ff}
.note{position:absolute;left:36px;bottom:30px;font-size:11.5px;color:rgba(255,255,255,.4);
  max-width:330px;line-height:1.6;border-left:2px solid rgba(45,226,255,.5);padding-left:12px}
"""

BODY_C = f"""
<div class="desk"></div>
<div class="panel">
  <span>Atividades</span><span class="sp"></span>
  <span class="tray">◉<span class="act">▲</span> ⌨ 🔊 ⏻</span>
  <span class="sp"></span><span class="mono">16:42</span>
</div>
<div class="menu">
  <div class="mi hl"><span class="sq" style="--c:#ff2d6f"></span> Turbo <b style="margin-left:4px;color:#ff5c8a">ligado</b><span class="k">Super+T</span></div>
  <div class="mi">❄ Ventoinhas <span class="k">4290 / 4610</span></div>
  <div class="hr"></div>
  <div class="mi"><span class="sq" style="--c:#b14aed"></span> Tema: Vapor</div>
  <div class="mi"><span class="sq" style="--c:#39ff14"></span> Tema: Matrix</div>
  <div class="mi"><span class="sq" style="--c:#ff6a00"></span> Tema: Inferno</div>
  <div class="hr"></div>
  <div class="mi">◉ Apagar teclado <span class="k">Super+K</span></div>
  <div class="mi">Abrir ControlFanRGB…</div>
</div>
<div class="win">
  <div class="wh"><div class="lg">P</div><b class="disp">CONTROLFANRGB</b>
    <div class="x"><i></i><i></i><i></i></div></div>
  <div class="wc">
    <div class="wl">Pré-visualização</div>
    {keyboard("zones",0.80)}
    <div class="wl">Zonas</div>
    <div class="sws">
      <div class="s sel" style="--c:#ff2d6f"></div><div class="s" style="--c:#b14aed"></div>
      <div class="s" style="--c:#4f7cff"></div><div class="s" style="--c:#2de2ff"></div>
    </div>
    <div class="wl">Efeito</div>
    <div class="mrow"><span class="on">Onda</span><span>Estático</span><span>Neon</span>
      <span>Respiração</span><span>Zoom</span><span>Arco-íris</span></div>
    <div class="wl">Brilho · 100%</div>
    <div class="track"><i style="width:100%"></i><b style="left:100%"></b></div>
    <div class="tline">
      <div class="tsw"></div>
      <div><div class="big">TURBO</div></div>
      <div class="rp">CPU 4290 rpm<br>GPU 4610 rpm</div>
    </div>
  </div>
</div>
<div class="osd">
  <div class="ring">ON</div>
  <div><h2>TURBO</h2><p>Ventoinhas em máximo</p></div>
  <div class="st">
    <div><b>4290</b><i>cpu rpm</i></div>
    <div><b>4610</b><i>gpu rpm</i></div>
    <div><b>72°</b><i>cpu temp</i></div>
  </div>
</div>
<div class="note">Opção C — mora no tray. Atalho global liga/desliga o turbo e o
OSD aparece por 3 s com a rotação real das ventoinhas. A janela grande é opcional.</div>
"""

# ============================================= D — PRO / ESTÚDIO DE EFEITOS ===
CSS_D = """
body{background:#0a0a0f;color:#dfe3ec;display:grid;
  grid-template-columns:196px 1fr 268px;grid-template-rows:44px 1fr 128px;
  grid-template-areas:"hd hd hd" "lf ct rt" "tl tl tl"}
.hd{grid-area:hd;display:flex;align-items:center;gap:13px;padding:0 16px;
  background:#101119;border-bottom:1px solid rgba(255,255,255,.07)}
.hd .lg{width:25px;height:25px;border-radius:7px;display:grid;place-items:center;
  background:linear-gradient(140deg,#9dff3c,#00d4a0);color:#06240f;font-weight:900;font-size:12px}
.hd b{font-size:13px;letter-spacing:.13em}
.tabs{display:flex;gap:1px;margin-left:12px}
.tabs span{font-size:11.5px;font-weight:600;padding:5px 12px;border-radius:6px;
  color:rgba(255,255,255,.45)}
.tabs span.on{background:rgba(157,255,60,.12);color:#9dff3c}
.hd .r{margin-left:auto;display:flex;gap:8px;align-items:center;font-size:10.5px;
  color:rgba(255,255,255,.45)}
.tag{padding:3px 8px;border-radius:5px;background:rgba(255,255,255,.06);
  font-family:'JetBrains Mono',monospace;font-size:10px}
.tag.ok{background:rgba(157,255,60,.12);color:#9dff3c}

.lf{grid-area:lf;background:#0d0e14;border-right:1px solid rgba(255,255,255,.07);
  padding:13px 11px;overflow:hidden}
.ct{grid-area:ct;padding:16px 18px;display:flex;flex-direction:column;gap:13px;min-width:0}
.rt{grid-area:rt;background:#0d0e14;border-left:1px solid rgba(255,255,255,.07);
  padding:13px 13px;display:flex;flex-direction:column;gap:14px}
.tl{grid-area:tl;background:#0d0e14;border-top:1px solid rgba(255,255,255,.07);
  padding:11px 16px}

.sl2{font-size:9px;letter-spacing:.2em;text-transform:uppercase;
  color:rgba(255,255,255,.3);margin-bottom:8px}
.pf{display:flex;align-items:center;gap:9px;padding:7px 9px;border-radius:7px;
  font-size:12px;color:rgba(255,255,255,.72);margin-bottom:2px}
.pf.on{background:rgba(157,255,60,.1);color:#fff;
  box-shadow:inset 0 0 0 1px rgba(157,255,60,.22)}
.pf .d{width:16px;height:16px;border-radius:5px;background:var(--g)}
.pf .kb2{margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:9px;
  color:rgba(255,255,255,.3)}

.lay{display:flex;align-items:center;gap:8px;padding:7px 9px;border-radius:7px;
  background:#12141d;margin-bottom:4px;font-size:11.5px}
.lay .e{width:7px;height:7px;border-radius:50%;background:#9dff3c}
.lay .o{margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:10px;
  color:rgba(255,255,255,.4)}

.card{background:#10111a;border:1px solid rgba(255,255,255,.07);border-radius:11px;padding:13px}
.head{display:flex;align-items:center;gap:9px;margin-bottom:11px}
.head h3{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;
  color:rgba(255,255,255,.55)}
.head .hint{margin-left:auto;font-size:10.5px;color:rgba(255,255,255,.3)}
.zbar{display:flex;gap:4px;margin-top:9px}
.zbar div{flex:1;height:22px;border-radius:5px;display:grid;place-items:center;
  font-size:9px;font-family:'JetBrains Mono',monospace;color:rgba(0,0,0,.6);font-weight:700;
  background:var(--c)}
.tools{display:flex;gap:5px;margin-bottom:11px}
.tools span{width:28px;height:28px;border-radius:7px;display:grid;place-items:center;
  background:#171926;font-size:13px;color:rgba(255,255,255,.5)}
.tools span.on{background:#9dff3c;color:#06240f}
.pal{display:grid;grid-template-columns:repeat(9,1fr);gap:4px;margin-top:10px}
.pal i{aspect-ratio:1;border-radius:4px;background:var(--c);font-style:normal}

.kv{display:flex;justify-content:space-between;font-size:11.5px;padding:5px 0;
  border-bottom:1px solid rgba(255,255,255,.05)}
.kv b{font-family:'JetBrains Mono',monospace;color:#fff}
.kv.warn b{color:#ffb020}
.fanbtns{display:flex;gap:5px;margin-top:9px}
.fanbtns span{flex:1;text-align:center;font-size:10.5px;font-weight:700;padding:6px 0;
  border-radius:6px;background:#171926;color:rgba(255,255,255,.5)}
.fanbtns span.on{background:#ff2d6f;color:#fff;box-shadow:0 0 14px -4px #ff2d6f}

/* timeline */
.tlh{display:flex;align-items:center;gap:11px;margin-bottom:9px}
.tlh b{font-size:10.5px;letter-spacing:.15em;text-transform:uppercase;
  color:rgba(255,255,255,.45)}
.tlh .pl{width:24px;height:24px;border-radius:50%;background:#9dff3c;color:#06240f;
  display:grid;place-items:center;font-size:10px}
.tlh .tm{margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:10.5px;
  color:rgba(255,255,255,.4)}
.lanes{display:flex;flex-direction:column;gap:4px}
.lane{display:flex;align-items:center;gap:9px}
.lane .nm{width:62px;font-size:10px;font-family:'JetBrains Mono',monospace;
  color:rgba(255,255,255,.4)}
.lane .trk{flex:1;height:16px;border-radius:5px;background:#12141d;position:relative;
  overflow:hidden}
.lane .trk .blk{position:absolute;top:2px;bottom:2px;border-radius:4px;background:var(--c);
  opacity:.85}
.pcursor{position:absolute;top:-4px;bottom:-4px;width:2px;background:#9dff3c;left:38%;
  box-shadow:0 0 10px #9dff3c;z-index:3}
.resolve{display:flex;align-items:center;gap:15px}
.rstep{flex:1}
.rstep b{display:block;font-size:10px;letter-spacing:.11em;text-transform:uppercase;
  color:rgba(255,255,255,.4);margin-bottom:9px;font-weight:700}
.rkeys{display:flex;gap:5px}
.rkeys i{width:30px;height:30px;border-radius:6px;background:var(--c);font-style:normal;
  display:grid;place-items:center;font-size:11px;font-weight:700;color:rgba(0,0,0,.65);
  box-shadow:0 0 13px -3px var(--c)}
.rmix{display:flex;gap:5px}
.rmix span{flex:1;height:30px;border-radius:6px;background:var(--c);
  box-shadow:0 0 13px -3px var(--c)}
.rarrow{color:rgba(255,255,255,.22);font-size:17px}
.rcode{font-size:10px;line-height:1.72;color:rgba(255,255,255,.5)}
.rcode em{font-style:normal;color:#9dff3c}
"""

BODY_D = f"""
<div class="hd">
  <div class="lg">P</div><b class="disp">CONTROLFANRGB STUDIO</b>
  <div class="tabs"><span>Zonas</span><span class="on">Tecla a tecla</span>
    <span>Efeitos</span><span>Resfriamento</span></div>
  <div class="r"><span class="tag">PH315-54</span><span class="tag ok">facer 1.0 · 4 zonas</span>
    <span class="tag">62 fps</span></div>
</div>

<div class="lf">
  <div class="sl2">Perfis</div>
  <div class="pf on" style="--g:linear-gradient(135deg,#ff3b30,#ffb020)">FPS / WASD<span class="kb2">F1</span></div>
  <div class="pf" style="--g:linear-gradient(135deg,#ff2d6f,#2de2ff)">Vapor<span class="kb2">F2</span></div>
  <div class="pf" style="--g:linear-gradient(135deg,#39ff14,#0066ff)">Matrix<span class="kb2">F3</span></div>
  <div class="pf" style="--g:linear-gradient(135deg,#ffd089,#ff8c42)">Noturno<span class="kb2">F4</span></div>
  <div class="pf" style="--g:#1b1d2a">Apagado<span class="kb2">F5</span></div>
  <div class="sl2" style="margin-top:17px">Camadas</div>
  <div class="lay"><span class="e"></span>Base · cor fixa<span class="o">100%</span></div>
  <div class="lay"><span class="e"></span>WASD · destaque<span class="o">100%</span></div>
  <div class="lay"><span class="e" style="background:#2de2ff"></span>Carga CPU<span class="o">40%</span></div>
  <div class="lay"><span class="e" style="background:#ffb020"></span>Alerta temp.<span class="o">auto</span></div>
</div>

<div class="ct">
  <div class="card">
    <div class="head"><h3>Mapa de teclas</h3>
      <span class="hint">pinte tecla a tecla — o app resolve a cor dominante de cada zona ▾</span></div>
    <div class="tools"><span class="on">🖌</span><span>▢</span><span>⬧</span><span>⟳</span><span>⌫</span></div>
    {keyboard("perkey",1.46)}
    <div class="zbar">
      <div style="--c:#ff3b30">Z1 · FF3B30</div><div style="--c:#c8a63a">Z2 · C8A63A</div>
      <div style="--c:#8fd44a">Z3 · 8FD44A</div><div style="--c:#2de2ff">Z4 · 2DE2FF</div>
    </div>
  </div>
  <div class="card" style="flex:1;display:flex;flex-direction:column">
    <div class="head"><h3>Como a cor chega no hardware</h3>
      <span class="hint">o PH315-54 tem 4 zonas físicas — o mapa de teclas é resolvido antes de escrever</span></div>
    <div class="resolve">
      <div class="rstep"><b>1 · você pinta</b>
        <div class="rkeys"><i style="--c:#ff3b30">W</i><i style="--c:#ff3b30">A</i>
          <i style="--c:#ff3b30">S</i><i style="--c:#ff3b30">D</i>
          <i style="--c:#9dff3c">Q</i><i style="--c:#ffb020">⇧</i></div></div>
      <div class="rarrow">→</div>
      <div class="rstep"><b>2 · média ponderada por zona</b>
        <div class="rmix"><span style="--c:#ff3b30"></span><span style="--c:#c8a63a"></span>
          <span style="--c:#8fd44a"></span><span style="--c:#2de2ff"></span></div></div>
      <div class="rarrow">→</div>
      <div class="rstep"><b>3 · escrita no driver</b>
        <div class="rcode mono">write(/dev/acer-gkbbl-static-0)<br>
          <em>0b0001</em> FF3B30 · <em>0b0010</em> C8A63A<br>
          <em>0b0100</em> 8FD44A · <em>0b1000</em> 2DE2FF<br>
          commit → /dev/acer-gkbbl-0</div></div>
    </div>
  </div>
</div>

<div class="rt">
  <div>
    <div class="sl2">Cor</div>
    <div style="height:92px;border-radius:9px;background:
      linear-gradient(to top,#000,transparent),linear-gradient(to right,#fff,#ff3b30);
      position:relative;border:1px solid rgba(255,255,255,.1)">
      <div style="position:absolute;top:22%;left:72%;width:15px;height:15px;border-radius:50%;
        border:2.5px solid #fff;transform:translate(-50%,-50%)"></div></div>
    <div class="pal">
      <i style="--c:#ff3b30"></i><i style="--c:#ff6a00"></i><i style="--c:#ffb020"></i>
      <i style="--c:#ffe100"></i><i style="--c:#9dff3c"></i><i style="--c:#00d4a0"></i>
      <i style="--c:#2de2ff"></i><i style="--c:#4f7cff"></i><i style="--c:#b14aed"></i>
    </div>
  </div>
  <div>
    <div class="sl2">Telemetria</div>
    <div class="kv"><span>Ventoinha CPU</span><b>4290 rpm</b></div>
    <div class="kv"><span>Ventoinha GPU</span><b>4610 rpm</b></div>
    <div class="kv warn"><span>CPU</span><b>72 °C</b></div>
    <div class="kv"><span>GPU</span><b>64 °C</b></div>
    {sparkline(RPM,"#ff2d6f")}
  </div>
  <div>
    <div class="sl2">Ventoinhas</div>
    <div class="fanbtns"><span>Auto</span><span>Silencioso</span><span class="on">Turbo</span></div>
    <div style="font-size:10.5px;color:rgba(255,255,255,.35);margin-top:8px;line-height:1.55">
      Turbo liga o overclock e tira a curva do automático.
      Atalho <span class="kbd" style="font-family:'JetBrains Mono';background:rgba(255,255,255,.08);padding:1px 5px;border-radius:4px">Super+T</span>.
    </div>
  </div>
</div>

<div class="tl">
  <div class="tlh"><div class="pl">▶</div><b>Linha do tempo do efeito</b>
    <span class="tm">00:01.84 / 00:04.00 · loop</span></div>
  <div class="lanes" style="position:relative">
    <div class="pcursor"></div>
    <div class="lane"><span class="nm">zona 1</span><div class="trk">
      <div class="blk" style="--c:#ff2d6f;left:0%;width:30%"></div>
      <div class="blk" style="--c:#b14aed;left:32%;width:26%"></div>
      <div class="blk" style="--c:#4f7cff;left:60%;width:40%"></div></div></div>
    <div class="lane"><span class="nm">zona 2</span><div class="trk">
      <div class="blk" style="--c:#b14aed;left:6%;width:28%"></div>
      <div class="blk" style="--c:#4f7cff;left:36%;width:30%"></div>
      <div class="blk" style="--c:#2de2ff;left:68%;width:32%"></div></div></div>
    <div class="lane"><span class="nm">zona 3</span><div class="trk">
      <div class="blk" style="--c:#4f7cff;left:12%;width:26%"></div>
      <div class="blk" style="--c:#2de2ff;left:40%;width:30%"></div>
      <div class="blk" style="--c:#9dff3c;left:72%;width:28%"></div></div></div>
    <div class="lane"><span class="nm">zona 4</span><div class="trk">
      <div class="blk" style="--c:#2de2ff;left:18%;width:28%"></div>
      <div class="blk" style="--c:#9dff3c;left:48%;width:28%"></div>
      <div class="blk" style="--c:#ff2d6f;left:78%;width:22%"></div></div></div>
  </div>
</div>
"""

# ------------------------------------------------------------------ build ----
MOCKUPS = [
    ("A-cyber-hud",        "ControlFanRGB — Cyber HUD",        CSS_A, BODY_A),
    ("B-gnome-adwaita",    "ControlFanRGB — GNOME nativo",     CSS_B, BODY_B),
    ("C-compacto-tray-osd","ControlFanRGB — Compacto + OSD",   CSS_C, BODY_C),
    ("D-studio-pro",       "ControlFanRGB — Studio",           CSS_D, BODY_D),
]

def main():
    only_html = "--html" in sys.argv
    chrome = next((c for c in ("google-chrome","google-chrome-stable","chromium")
                   if subprocess.run(["which",c],capture_output=True).returncode==0), None)
    for slug, title, css, body in MOCKUPS:
        html = os.path.join(HERE, slug + ".html")
        with open(html, "w") as f:
            f.write(page(title, css, body))
        print("html  ->", os.path.basename(html))
        if only_html or not chrome:
            continue
        png = os.path.join(HERE, slug + ".png")
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        f"--window-size={W},{H}", "--force-device-scale-factor=2",
                        "--virtual-time-budget=4000", "--default-background-color=00000000",
                        f"--screenshot={png}", "file://" + html],
                       capture_output=True, timeout=120)
        ok = os.path.exists(png)
        print("  png ->", os.path.basename(png),
              f"({os.path.getsize(png)//1024} KB)" if ok else "FALHOU")

if __name__ == "__main__":
    main()
