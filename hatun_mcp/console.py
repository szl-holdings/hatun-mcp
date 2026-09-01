"""
hatun_mcp.console — the human face of hatun-mcp.

Returns a single self-contained HTML document (zero runtime CDN, no external
assets, no webfont fetch) for browser requests to `/`. API clients (Accept:
application/json) still receive the JSON service descriptor — this module is
ONLY rendered when content-negotiation selects HTML, so MCP/SSE clients are
never affected.

The console renders the SZL monochrome design system: black canvas, warm
off-white display type, a single neutral grey ramp, hairline rules, and one
holographic point-cloud kernel in the hero. No color pop, no decorative
gradient; hierarchy is carried by weight and spacing. Mobile-first: single
column below 1000px, clamp() on every size.

DATA: every value on the page is fetched at load from this server's OWN Python
endpoint `/api/console-state` (hatun_mcp.state), which reads the LIVE FastMCP
tool registry, the LIVE Khipu chain, the signer and the injected build
revision in-request. There is no seeded snapshot in this file. If the fetch
fails, panels display the honest label UNAVAILABLE and no number is shown.

HONESTY doctrine v11:
  * Λ is Conjecture 1 — advisory governance, never a theorem, never "proven".
  * Khipu BFT framing is Conjecture 2.
  * SLSA L1 honest (L2 attested on the pushed image; L3 not claimed).
  * signing state is UNSIGNED unless a real ECDSA P-256 key is in-process.
  * no energy/joule claims; no consciousness claims; no fabricated numbers.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

REPO_URL = "https://github.com/szl-holdings/hatun-mcp"
SPACE_URL = "https://szlholdings-hatun-mcp.hf.space"

CONSOLE_HTML = r"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<title>hatun-mcp · the great context protocol</title>
<meta name="description" content="hatun-mcp — SZL Holdings' Model Context Protocol gateway. Governed context with receipts and provenance, handed to the world's agents.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='12.5' fill='none' stroke='%23e8e8ea' stroke-width='1.5'/%3E%3Ccircle cx='16' cy='16' r='3.5' fill='%23f0eee6'/%3E%3C/svg%3E">
<style>
/* ── SZL monochrome design system · no runtime CDN, no webfont fetch ───────── */
:root{
  --bg:#000000; --bg-soft:#0a0a0b; --panel:#0d0d0f;
  --ink:#ffffff; --cream:#f0eee6;
  --t1:#e8e8ea; --t2:#9a9a9e; --t3:#5f5f63;
  --line:#1c1c1f; --line2:#2a2a2e;
  --head:'Space Grotesk',system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace;
  --maxw:1120px;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{
  background:var(--bg); color:var(--t1); font-family:var(--head);
  line-height:1.55; -webkit-font-smoothing:antialiased; overflow-x:hidden;
}
a{color:var(--t1); text-decoration:none; border-bottom:1px solid var(--line2)}
a:hover{color:var(--ink); border-bottom-color:var(--t2)}
.wrap{
  width:100%; max-width:var(--maxw); margin:0 auto;
  padding-left:max(clamp(18px,5vw,40px),env(safe-area-inset-left));
  padding-right:max(clamp(18px,5vw,40px),env(safe-area-inset-right));
}
.mono{font-family:var(--mono)}
.eyebrow{
  font-family:var(--mono); font-size:clamp(10px,2.4vw,11px); letter-spacing:.13em;
  text-transform:uppercase; color:var(--t3);
}

/* ── top bar ───────────────────────────────────────────────────────────────── */
header{
  position:sticky; top:0; z-index:20; background:rgba(0,0,0,.82);
  backdrop-filter:blur(10px); border-bottom:1px solid var(--line);
  padding-top:env(safe-area-inset-top);
}
header .bar{display:flex; align-items:center; gap:14px; height:clamp(52px,11vw,60px)}
header .mark{font-weight:600; letter-spacing:-.02em; font-size:clamp(14px,3.6vw,16px); color:var(--ink)}
header .mark span{color:var(--t3); font-weight:400}
header nav{margin-left:auto; display:flex; gap:clamp(12px,3.5vw,22px)}
header nav a{
  font-family:var(--mono); font-size:11px; letter-spacing:.09em; text-transform:uppercase;
  color:var(--t2); border-bottom:none;
}
header nav a:hover{color:var(--ink)}
@media (max-width:640px){ header nav a.opt{display:none} }

/* ── hero ──────────────────────────────────────────────────────────────────── */
.hero{position:relative; overflow:hidden; border-bottom:1px solid var(--line)}
#holo{
  position:absolute; inset:0; width:100%; height:100%;
  opacity:.72; pointer-events:none;
}
.hero .wrap{
  position:relative; z-index:2;
  padding-top:clamp(56px,14vw,110px); padding-bottom:clamp(48px,12vw,96px);
}
.hero h1{
  font-size:clamp(34px,7vw,72px); font-weight:600; letter-spacing:-.03em;
  line-height:1.02; margin:14px 0 0; color:var(--cream);
}
.hero .lede{
  font-size:clamp(15px,3.4vw,18px); font-weight:400; color:var(--t2);
  max-width:620px; margin:18px 0 0;
}
.hero .statusline{
  margin-top:22px; font-family:var(--mono); font-size:clamp(11px,2.7vw,12px);
  letter-spacing:.06em; color:var(--t2); display:flex; flex-wrap:wrap; gap:8px 16px;
}
.hero .statusline b{color:var(--t1); font-weight:500}
.cta{display:flex; flex-wrap:wrap; gap:10px; margin-top:26px}
.cta a{
  font-family:var(--mono); font-size:12px; letter-spacing:.06em; padding:11px 16px;
  border:1px solid var(--line2); border-radius:10px; color:var(--t1); background:var(--panel);
  transition:border-color .2s ease, transform .2s ease, color .2s ease;
}
.cta a:hover{border-color:var(--t2); color:var(--ink); transform:translateY(-1px)}
.cta a.solid{background:var(--cream); color:#000; border-color:var(--cream)}
.cta a.solid:hover{background:var(--ink)}

/* ── kpi strip ─────────────────────────────────────────────────────────────── */
.kpis{display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:1px; background:var(--line);
  border-top:1px solid var(--line); border-bottom:1px solid var(--line)}
@media (min-width:1000px){ .kpis{grid-template-columns:repeat(4,minmax(0,1fr))} }
.kpi{background:var(--bg); padding:clamp(16px,4vw,24px)}
.kpi .v{font-size:clamp(24px,6vw,36px); font-weight:600; letter-spacing:-.02em; color:var(--cream);
  line-height:1.1; font-variant-numeric:tabular-nums}
.kpi .s{font-family:var(--mono); font-size:11px; color:var(--t3); margin-top:8px; letter-spacing:.05em}

/* ── sections ──────────────────────────────────────────────────────────────── */
section{padding-top:clamp(40px,9vw,76px); padding-bottom:clamp(40px,9vw,76px); border-bottom:1px solid var(--line)}
.h2{font-size:clamp(22px,4vw,34px); font-weight:600; letter-spacing:-.02em; color:var(--t1); margin:10px 0 0}
.sub{font-size:clamp(14px,3.2vw,16px); color:var(--t2); max-width:640px; margin:12px 0 0}
.grid{display:grid; grid-template-columns:1fr; gap:clamp(12px,2.6vw,16px); margin-top:clamp(22px,5vw,32px)}
@media (min-width:1000px){
  .grid.g2{grid-template-columns:repeat(2,minmax(0,1fr))}
  .grid.g3{grid-template-columns:repeat(3,minmax(0,1fr))}
}

/* ── THE shared card component (tools, runtime, resources, repos) ──────────── */
.card{
  border:1px solid var(--line2); border-radius:14px; background:var(--panel);
  padding:18px; font-family:var(--head);
  transition:border-color .2s ease, transform .2s ease, box-shadow .2s ease;
}
.card:hover{border-color:var(--t2); transform:translateY(-1px); box-shadow:0 8px 30px -12px #000}
.card .t{font-size:clamp(15px,3.6vw,18px); font-weight:600; color:var(--ink); margin:8px 0 0;
  letter-spacing:-.01em; word-break:break-word}
.card .d{font-size:clamp(13px,3vw,14px); color:var(--t2); margin:8px 0 0}
.card .metrics{
  display:flex; flex-wrap:wrap; gap:6px 14px; margin-top:14px;
  font-family:var(--mono); font-size:11px; color:var(--t2); letter-spacing:.04em;
  font-variant-numeric:tabular-nums;
}
.card .metrics b{color:var(--t1); font-weight:500}
.chip{
  display:inline-block; margin-top:12px; padding:3px 8px; border-radius:999px;
  border:1px solid currentColor; color:var(--t2);
  font-family:var(--mono); font-size:10px; letter-spacing:.1em; text-transform:uppercase;
}
.card .foot{margin-top:12px; font-family:var(--mono); font-size:11px; color:var(--t2)}
.card .foot a{border-bottom:none; color:var(--t2)}
.card .foot a:hover{color:var(--ink)}

.loading{font-family:var(--mono); font-size:12px; color:var(--t3); letter-spacing:.06em}
.count{font-family:var(--mono); font-size:12px; color:var(--t3); letter-spacing:.08em}

/* ── code blocks ───────────────────────────────────────────────────────────── */
pre{
  font-family:var(--mono); font-size:clamp(11px,2.7vw,12.5px); line-height:1.7;
  background:var(--bg-soft); border:1px solid var(--line); border-radius:12px;
  padding:14px; overflow-x:auto; color:var(--t1); margin:14px 0 0;
}
pre .c{color:var(--t3)}
pre .k{color:var(--t2)}

/* ── footer ────────────────────────────────────────────────────────────────── */
footer{padding-top:clamp(32px,7vw,52px); padding-bottom:calc(clamp(32px,7vw,52px) + env(safe-area-inset-bottom))}
footer .row{display:flex; flex-wrap:wrap; gap:10px 20px; font-family:var(--mono); font-size:11px;
  letter-spacing:.06em; color:var(--t3); align-items:center}
footer .row a{color:var(--t2); border-bottom:none}
footer .row a:hover{color:var(--ink)}
footer .honest{font-size:12px; color:var(--t3); margin-top:18px; max-width:760px; line-height:1.7}
footer .honest b{color:var(--t2); font-weight:500}

@media (prefers-reduced-motion: reduce){
  *{transition:none !important; animation:none !important}
}
</style>
</head>
<body>

<header><div class="wrap bar">
  <div class="mark">hatun&#8209;mcp <span>/ SZL Holdings</span></div>
  <nav>
    <a href="#runtime">runtime</a>
    <a href="#tools">tools</a>
    <a class="opt" href="#connect">connect</a>
    <a class="opt" href="/.well-known/mcp/server-card.json">card</a>
  </nav>
</div></header>

<div class="hero">
  <canvas id="holo" aria-hidden="true"></canvas>
  <div class="wrap">
    <div class="eyebrow">MODEL CONTEXT PROTOCOL GATEWAY · STREAMABLE HTTP</div>
    <h1>The great<br>context protocol.</h1>
    <p class="lede">hatun&#8209;mcp hands governed context to any MCP client. Every call passes a
      13&#8209;axis gate, mints a hash&#8209;linked Khipu receipt, and returns with its provenance
      attached. Everything below is read from this process at page load.</p>
    <div class="statusline">
      <span>STATE <b id="hero-state">reading…</b></span>
      <span>PROTOCOL <b id="hero-proto">—</b></span>
      <span>SIGNING <b id="hero-sign">—</b></span>
      <span>READ <b id="hero-read">—</b></span>
    </div>
    <div class="cta">
      <a class="solid" href="#connect">Connect an agent</a>
      <a href="/.well-known/mcp/server-card.json">Inspect the server card</a>
      <a href="https://github.com/szl-holdings/hatun-mcp">Source on GitHub</a>
    </div>
  </div>
</div>

<div class="kpis">
  <div class="kpi"><div class="v" id="kpi-tools">—</div><div class="s">TOOLS IN LIVE REGISTRY</div></div>
  <div class="kpi"><div class="v" id="kpi-chain">—</div><div class="s">RECEIPT CHAIN (RECOMPUTED)</div></div>
  <div class="kpi"><div class="v" id="kpi-receipts">—</div><div class="s">RECEIPTS THIS PROCESS</div></div>
  <div class="kpi"><div class="v" id="kpi-parity">—</div><div class="s">CARD ↔ RUNTIME PARITY</div></div>
</div>

<main>

<section id="runtime"><div class="wrap">
  <div class="eyebrow">01 · RUNTIME</div>
  <div class="h2">What this process can prove right now</div>
  <p class="sub">Each panel is one reading from the live server. A value that cannot be read is
    labelled UNAVAILABLE rather than filled in.</p>
  <div class="grid g3" id="runtime-cards">
    <div class="card"><div class="loading">reading /api/console-state…</div></div>
  </div>
</div></section>

<section id="tools"><div class="wrap">
  <div class="eyebrow">02 · CAPABILITIES</div>
  <div class="h2">Tools this server exposes <span class="count" id="tools-count"></span></div>
  <p class="sub">Enumerated from the live FastMCP tool registry in this process — not from a
    hand-written list. Parameter counts come from each tool's real input schema.</p>
  <div class="grid g3" id="tool-cards">
    <div class="card"><div class="loading">enumerating live tool registry…</div></div>
  </div>
</div></section>

<section id="resources"><div class="wrap">
  <div class="eyebrow">03 · RESOURCES</div>
  <div class="h2">Readable resources</div>
  <div class="grid g2" id="resource-cards">
    <div class="card"><div class="loading">reading resource registry…</div></div>
  </div>
</div></section>

<section id="connect"><div class="wrap">
  <div class="eyebrow">04 · CONNECT</div>
  <div class="h2">Wire it into your agent</div>
  <div class="grid g2">
    <div class="card">
      <div class="eyebrow">CLIENT CONFIG · CLAUDE DESKTOP / CURSOR</div>
      <pre><span class="c">// claude_desktop_config.json / mcp.json</span>
{
  <span class="k">"mcpServers"</span>: {
    <span class="k">"hatun"</span>: {
      <span class="k">"url"</span>: "https://szlholdings-hatun-mcp.hf.space/mcp/",
      <span class="k">"headers"</span>: {
        <span class="k">"Authorization"</span>: "Bearer szl_..."
      }
    }
  }
}</pre>
    </div>
    <div class="card">
      <div class="eyebrow">ENDPOINTS · NO AUTH ON DESCRIPTORS</div>
      <pre><span class="c"># transport</span>
POST /mcp/          <span class="c">streamable http</span>
GET  /sse/          <span class="c">legacy sse</span>

<span class="c"># descriptors</span>
GET  /.well-known/mcp/server-card.json
GET  /.well-known/mcp-manifest-attestation
GET  /connect
GET  /api/console-state   <span class="c">this page's data</span>
GET  /api/build-info
GET  /healthz  /readyz  /pubkey

<span class="c"># anonymous calls are declined and receipted —</span>
<span class="c"># bring an SZL API key.</span></pre>
    </div>
  </div>
</div></section>

</main>

<footer><div class="wrap">
  <div class="row">
    <span>© SZL Holdings · hatun&#8209;mcp</span>
    <a href="https://github.com/szl-holdings/hatun-mcp">GitHub</a>
    <a href="/.well-known/mcp/server-card.json">Server card</a>
    <a href="/api/console-state">Console state</a>
    <a href="/healthz">/healthz</a>
    <a href="/pubkey">/pubkey</a>
  </div>
  <p class="honest mono">offline&#8209;checkable · no trust in SZL — <span id="foot-label">state UNAVAILABLE until read</span></p>
  <p class="honest"><b>Doctrine v11.</b> Locked numbers <span class="mono" id="foot-locked">—</span>.
    &Lambda; is <b>Conjecture&nbsp;1 · not a theorem</b> — advisory governance, and it stays open.
    Khipu BFT framing is Conjecture&nbsp;2. SLSA <b>L1 honest</b> (L2 attested on the pushed image;
    L3 not claimed). Responses are <b>UNSIGNED</b> unless a real ECDSA&nbsp;P&#8209;256 key is loaded
    in this process. No energy or joule claims are made anywhere on this surface. Every number on
    this page is read in&#8209;request from <span class="mono">/api/console-state</span>; where a
    reading fails the panel says UNAVAILABLE and shows no number.</p>
  <p class="honest mono">Signed&#8209;off&#8209;by: Stephen P. Lutar Jr. &lt;stephenlutar2@gmail.com&gt;</p>
</div></footer>

<script>
/* ---- monochrome holographic point-cloud "proof kernel" (SZL design system) ---- */
(function(){
  var cv=document.getElementById('holo'); if(!cv||!cv.getContext) return;
  var ctx=cv.getContext('2d'); if(!ctx) return;
  var W,H,DPR=Math.min(window.devicePixelRatio||1,2),CX,CY,S;
  function rs(){W=cv.width=cv.clientWidth*DPR;H=cv.height=(cv.clientHeight||600)*DPR;CX=W*0.5;CY=H*0.5;S=Math.min(W,H)*0.32;}
  rs();addEventListener('resize',rs);
  var reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  var N=reduce?420:900, pts=[];
  for(var i=0;i<N;i++){
    var y=1-(i/(N-1))*2, rr=Math.sqrt(1-y*y), th=i*2.399963;
    pts.push([Math.cos(th)*rr,y,Math.sin(th)*rr]);
  }
  var t=0;
  function frame(){
    ctx.clearRect(0,0,W,H);
    if(!reduce)t+=0.0032;
    var cy=Math.cos(t),sy=Math.sin(t),cx=Math.cos(t*0.5),sx=Math.sin(t*0.5);
    var proj=[],i,j;
    for(i=0;i<pts.length;i++){
      var x=pts[i][0],yy=pts[i][1],z=pts[i][2];
      var x1=x*cy - z*sy, z1=x*sy + z*cy;
      var y2=yy*cx - z1*sx, z2=yy*sx + z1*cx;
      var d=2.6/(2.6+z2);
      proj.push([CX+x1*S*d, CY+y2*S*d, z2, d]);
    }
    ctx.lineWidth=0.6*DPR;
    for(i=0;i<proj.length;i+=7){
      var a=proj[i];
      for(j=i+1;j<Math.min(i+9,proj.length);j++){
        var b=proj[j];var dx=a[0]-b[0],dy=a[1]-b[1];
        if(dx*dx+dy*dy<(46*DPR)*(46*DPR)){
          ctx.strokeStyle='rgba(255,255,255,'+(0.05*a[3])+')';
          ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();
        }
      }
    }
    for(i=0;i<proj.length;i++){
      var px=proj[i][0],py=proj[i][1],pz=proj[i][2],pd=proj[i][3];
      var bright=0.28+0.72*((pz+1)/2);
      var r=(0.7+1.3*pd)*DPR;
      ctx.fillStyle='rgba(255,255,255,'+(0.15+0.6*bright).toFixed(3)+')';
      ctx.beginPath();ctx.arc(px,py,r,0,7);ctx.fill();
    }
    var g=ctx.createRadialGradient(CX,CY,0,CX,CY,S*1.4);
    g.addColorStop(0,'rgba(240,238,230,0.06)');g.addColorStop(1,'rgba(240,238,230,0)');
    ctx.fillStyle=g;ctx.beginPath();ctx.arc(CX,CY,S*1.4,0,7);ctx.fill();
    if(reduce) return;
    requestAnimationFrame(frame);
  }
  frame();
})();
</script>

<script>
/* ---- live data: ONE read of this server's own Python endpoint ----------------
   Deliberately a SEPARATE <script> element from the hero canvas: a rendering
   failure in the decorative kernel must never stop the real data from loading. */
(function(){
  "use strict";
  var UNAVAILABLE = "UNAVAILABLE";
  function $(id){ return document.getElementById(id); }
  function txt(id,v){ var e=$(id); if(e) e.textContent=v; }
  function esc(s){ return String(s).replace(/[&<>"]/g,function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]; }); }
  function num(v){ return (v===null||v===undefined) ? UNAVAILABLE : String(v); }

  function getJSON(url, ms){
    var ctl = new AbortController();
    var timer = setTimeout(function(){ ctl.abort(); }, ms||5000);
    return fetch(url, {signal:ctl.signal, headers:{accept:"application/json"}})
      .then(function(r){ if(!r.ok) throw new Error("http "+r.status); return r.json(); })
      .finally(function(){ clearTimeout(timer); });
  }
  function getText(url, ms){
    var ctl = new AbortController();
    var timer = setTimeout(function(){ ctl.abort(); }, ms||5000);
    return fetch(url, {signal:ctl.signal})
      .then(function(r){ if(!r.ok) throw new Error("http "+r.status); return r.text(); })
      .finally(function(){ clearTimeout(timer); });
  }

  /* the ONE shared card component — every card on this page is built here */
  function card(o){
    var el = document.createElement("article");
    el.className = "card";
    var html = '<div class="eyebrow">'+esc(o.eyebrow||"")+'</div>'+
               '<div class="t">'+esc(o.title||UNAVAILABLE)+'</div>';
    if(o.desc) html += '<div class="d">'+esc(o.desc)+'</div>';
    if(o.metrics && o.metrics.length){
      html += '<div class="metrics">'+o.metrics.map(function(m){
        return '<span>'+esc(m[0])+' <b>'+esc(m[1])+'</b></span>'; }).join("")+'</div>';
    }
    if(o.label) html += '<div class="chip">'+esc(o.label)+'</div>';
    if(o.foot) html += '<div class="foot">'+o.foot+'</div>';
    el.innerHTML = html;
    return el;
  }
  function fill(hostId, cards){
    var host = $(hostId); if(!host) return;
    host.innerHTML = "";
    if(!cards.length){
      host.appendChild(card({eyebrow:"NO READING", title:UNAVAILABLE,
        desc:"This registry could not be read in this request.", label:UNAVAILABLE}));
      return;
    }
    cards.forEach(function(c){ host.appendChild(c); });
  }

  function shortHash(h){
    if(!h) return UNAVAILABLE;
    if(/^0{64}$/.test(h)) return "GENESIS";
    return h.slice(0,12) + "…" + h.slice(-6);
  }

  function renderUnavailable(){
    ["hero-state","hero-proto","hero-sign","hero-read"].forEach(function(id){ txt(id, UNAVAILABLE); });
    ["kpi-tools","kpi-chain","kpi-receipts","kpi-parity"].forEach(function(id){ txt(id, UNAVAILABLE); });
    txt("foot-label", "state UNAVAILABLE — /api/console-state did not answer this request");
    txt("foot-locked", UNAVAILABLE);
    fill("runtime-cards", []);
    fill("tool-cards", []);
    fill("resource-cards", []);
  }

  function render(s){
    var rt = s.runtime||{}, sg = s.signing||{}, kh = s.khipu||{},
        bd = s.build||{}, hl = s.health||{}, tl = s.tools||{},
        rs = s.resources||{}, pa = s.card_parity||{}, og = s.organs||{},
        dc = s.doctrine||{};

    /* hero + kpi strip */
    txt("hero-state", (hl.status||UNAVAILABLE).toUpperCase()+" · "+(hl.readiness||UNAVAILABLE));
    txt("hero-proto", rt.protocol_revision||UNAVAILABLE);
    txt("hero-sign", sg.state||UNAVAILABLE);
    txt("hero-read", s.read||UNAVAILABLE);
    txt("kpi-tools", num(tl.count));
    txt("kpi-chain", kh.chain||UNAVAILABLE);
    txt("kpi-receipts", num(kh.receipts_this_process));
    txt("kpi-parity", pa.state||UNAVAILABLE);
    txt("foot-label", "read "+(s.generated_at||UNAVAILABLE)+" · signing "+(sg.state||UNAVAILABLE)+
        " · chain "+(kh.chain||UNAVAILABLE));
    txt("foot-locked", num(dc.lean_declarations)+" declarations / "+num(dc.lean_axioms_unique)+
        " unique axioms / "+num(dc.lean_sorries_total)+" sorries · "+num(dc.yuyay_axes)+" Yuyay axes");

    /* runtime cards — same shared component as every tool card */
    var runtime = [
      card({eyebrow:"RUNTIME · TRANSPORT", title:rt.transport||UNAVAILABLE,
        desc:"MCP transport served by this process, with the legacy SSE mount alongside it.",
        metrics:[["protocol", rt.protocol_revision||UNAVAILABLE],
                 ["python", rt.python||UNAVAILABLE],
                 ["uptime s", num(rt.uptime_seconds)]],
        label:"MEASURED"}),
      card({eyebrow:"GOVERNANCE · KHIPU CHAIN", title:kh.chain||UNAVAILABLE,
        desc:"Append-only receipt chain, recomputed from genesis on every read of this endpoint.",
        metrics:[["receipts", num(kh.receipts_this_process)],
                 ["head", shortHash(kh.head_hash)]],
        label:kh.link||UNAVAILABLE}),
      card({eyebrow:"ATTESTATION · DSSE SIGNER", title:sg.state||UNAVAILABLE,
        desc:sg.state==="SIGNED"
          ? "A real ECDSA P-256 key is loaded in this process; responses carry a DSSE envelope."
          : "No signing key is loaded in this process, so responses are returned UNSIGNED.",
        metrics:[["signer", sg.signer_mode||UNAVAILABLE],
                 ["algorithm", sg.algorithm||UNAVAILABLE],
                 ["transparency log", sg.transparency_log||UNAVAILABLE]],
        label:sg.state||UNAVAILABLE,
        foot:'<a href="/pubkey">/pubkey</a> · <span id="key-fp">fingerprint reading…</span>'}),
      card({eyebrow:"PROVENANCE · SOURCE REVISION", title:bd.state||UNAVAILABLE,
        desc:"The exact Git revision the deployer injected into this container.",
        metrics:[["revision", bd.revision ? bd.revision.slice(0,12) : UNAVAILABLE]],
        label:bd.state||UNAVAILABLE,
        foot:'<a href="/api/build-info">/api/build-info</a>'}),
      card({eyebrow:"DISCOVERY · CARD ↔ RUNTIME", title:pa.state||UNAVAILABLE,
        desc:"Measured comparison between the published server card and the live tool registry.",
        metrics:[["card", num(pa.card_tool_count)],
                 ["runtime", num(pa.runtime_tool_count)],
                 ["card only", String((pa.only_in_card||[]).length)],
                 ["runtime only", String((pa.only_in_runtime||[]).length)]],
        label:pa.state===UNAVAILABLE?UNAVAILABLE:"MEASURED",
        foot:'<a href="/.well-known/mcp/server-card.json">server card</a>'}),
      card({eyebrow:"FEDERATION · ORGAN REGISTRATION", title:og.state||UNAVAILABLE,
        desc:og.state==="DISABLED"
          ? "Dynamic organ-tool registration is switched off in this process, so only the static registry is served."
          : "Organ catalogues fetched at boot; unreachable organs register no tools and say so.",
        metrics:(og.organs&&og.organs.length)
          ? og.organs.map(function(o){ return [o.organ, num(o.tools_registered)]; })
          : [["organs", (og.organs&&og.organs.length)||0]],
        label:og.state===UNAVAILABLE?UNAVAILABLE:og.state,
        foot:og.detail ? esc(og.detail) : ""})
    ];
    fill("runtime-cards", runtime);

    /* tool cards — one shared card per REAL registered tool */
    var items = tl.items||[];
    txt("tools-count", tl.state==="MEASURED" ? "· "+items.length+" measured" : "· "+UNAVAILABLE);
    fill("tool-cards", items.map(function(t){
      return card({
        eyebrow:"TOOL · "+String(t.family||"").toUpperCase()+(t.is_async?" · ASYNC":""),
        title:t.name,
        desc:t.description||"",
        metrics:[["params", num(t.parameters_total)],
                 ["required", num(t.parameters_required)]],
        label:"MEASURED · LIVE REGISTRY"
      });
    }));

    /* resource cards */
    fill("resource-cards", (rs.items||[]).map(function(r){
      return card({eyebrow:"RESOURCE", title:r.uri, desc:r.description||"",
        label:"MEASURED · LIVE REGISTRY"});
    }));
  }

  getJSON("/api/console-state", 6000).then(render).catch(renderUnavailable);

  /* pubkey fingerprint — computed in the browser from the served PEM */
  function pemToDer(pem){
    var b64 = pem.replace(/-----[^-]+-----/g,"").replace(/\s+/g,"");
    var bin = atob(b64), arr = new Uint8Array(bin.length);
    for(var i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);
    return arr.buffer;
  }
  function hex(buf){
    return Array.prototype.map.call(new Uint8Array(buf),function(b){
      return b.toString(16).padStart(2,"0"); }).join("");
  }
  function setFp(v){ var e=$("key-fp"); if(e) e.textContent=v; }
  setTimeout(function(){
    getText("/pubkey", 5000).then(function(pem){
      if(pem.indexOf("PUBLIC KEY") === -1){ setFp("no key in process — UNSIGNED"); return; }
      if(window.crypto && crypto.subtle){
        return crypto.subtle.digest("SHA-256", pemToDer(pem)).then(function(d){
          setFp("SHA256(SPKI) " + hex(d).slice(0,24) + "…");
        });
      }
      setFp("key served · fingerprint " + UNAVAILABLE + " in this browser");
    }).catch(function(){ setFp("fingerprint " + UNAVAILABLE); });
  }, 250);
})();
</script>
</body>
</html>"""
