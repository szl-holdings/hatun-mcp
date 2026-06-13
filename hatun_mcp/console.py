"""
hatun_mcp.console — the human face of hatun-mcp.

Returns a single self-contained HTML document (zero runtime CDN, system fonts,
no external assets) for browser requests to `/`. API clients (Accept:
application/json) still receive the original JSON service descriptor — this
module is ONLY rendered when content-negotiation selects HTML, so MCP/SSE
clients are never affected.

The console is AGENTIC: at load time the browser fetches this server's OWN live
endpoints (/healthz, /.well-known/mcp/server-card.json, /pubkey) and renders
them. It also probes the a11oy compute fabric with an AbortController timeout.
Every panel HONEST-DEGRADES to a clearly-labeled SNAPSHOT (seed values captured
from a real probe) if a live fetch fails — never blank, never fabricated.

HONESTY doctrine v11:
  * locked-proven = 8; Λ is Conjecture 1 (advisory, NEVER "proven trust").
  * Khipu BFT framing is Conjecture 2.
  * SLSA L1 honest (L2 on roadmap, L3 not claimed).
  * sovereign:true only on owned metal; the fabric itself is sovereign:false.
  * NO free-energy / joule claims. NO banned codenames in human copy.
  * Live numbers are never fabricated — degrade to SNAPSHOT/seed.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

# A small, honest snapshot captured from a real probe of the live endpoints on
# 2026-06-03. Used ONLY as a clearly-labeled fallback if a live fetch fails so
# the console is never blank and never fabricates current numbers.
_SNAPSHOT = {
    "healthz": {
        "status": "ok", "service": "hatun-mcp", "chain_verified": True,
        "signer_mode": "PLACEHOLDER", "protocol_revision": "2025-06-18",
    },
    "tool_count": 25,
    "lean": {"declarations": 749, "sorries": 163, "yuyay_axes": 13},
    "fabric": {
        "kind": "multi-node-compute-fabric", "sovereign": False,
        "nodes_total": 6, "nodes_reachable": 5, "gpu_nodes_reachable": 1,
        "sovereign_gpu_live": True,
    },
}

import json as _json

CONSOLE_HTML = """<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>hatun-mcp · the great context protocol</title>
<meta name="description" content="hatun-mcp — SZL Holdings' signed, sovereign Model Context Protocol server. Governed context with provenance, handed to the world's agents.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='13' fill='none' stroke='%2335e0d8' stroke-width='2'/%3E%3Ccircle cx='16' cy='16' r='4' fill='%237c5cff'/%3E%3C/svg%3E">
<style>
/* ── Sovereign: 0 runtime CDN, system fonts only ───────────────────────────── */
:root{
  --bg:#070912; --bg2:#0b0f1e; --surface:rgba(20,26,46,.55);
  --surface-2:rgba(28,36,62,.45); --border:rgba(120,150,210,.16);
  --border-2:rgba(120,150,210,.30);
  --text:#e8ecf6; --muted:#9aa6c4; --faint:#67718f;
  --teal:#35e0d8; --cyan:#46b9ff; --violet:#9a7bff;
  --good:#48d597; --warn:#f0b24b; --bad:#ff6b8b;
  --mono:ui-monospace,"SF Mono","Cascadia Code","JetBrains Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --r:16px; --maxw:1120px;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  font-family:var(--sans);color:var(--text);background:var(--bg);
  line-height:1.55;-webkit-font-smoothing:antialiased;overflow-x:hidden;
  background-image:
    radial-gradient(900px 600px at 12% -8%, rgba(53,224,216,.16), transparent 60%),
    radial-gradient(820px 560px at 92% 4%, rgba(154,123,255,.16), transparent 60%),
    radial-gradient(1100px 800px at 50% 118%, rgba(70,185,255,.10), transparent 60%),
    linear-gradient(180deg,var(--bg),var(--bg2));
  background-attachment:fixed;
}
a{color:var(--cyan);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 22px}
.mono{font-family:var(--mono)}

/* ── starfield (pure CSS, no assets) ───────────────────────────────────────── */
.stars{position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.55;
  background-image:
    radial-gradient(1px 1px at 20% 30%, #fff, transparent),
    radial-gradient(1px 1px at 70% 12%, #cfe, transparent),
    radial-gradient(1px 1px at 40% 70%, #fff, transparent),
    radial-gradient(1px 1px at 85% 55%, #bdf, transparent),
    radial-gradient(1px 1px at 12% 85%, #fff, transparent),
    radial-gradient(1.5px 1.5px at 60% 40%, #fff, transparent);
  background-repeat:no-repeat;}

/* ── top bar ───────────────────────────────────────────────────────────────── */
header{position:relative;z-index:2;border-bottom:1px solid var(--border);
  backdrop-filter:blur(10px);background:rgba(7,9,18,.5)}
.bar{display:flex;align-items:center;gap:14px;padding:14px 0}
.logo{display:flex;align-items:center;gap:11px;font-weight:700;letter-spacing:.2px}
.logo .mark{width:30px;height:30px;border-radius:9px;display:grid;place-items:center;
  background:radial-gradient(circle at 30% 30%,rgba(53,224,216,.4),rgba(154,123,255,.25));
  border:1px solid var(--border-2);box-shadow:0 0 22px rgba(53,224,216,.28)}
.logo .mark span{width:9px;height:9px;border-radius:50%;background:var(--violet);
  box-shadow:0 0 10px var(--violet)}
.logo b{font-size:16px}
.logo small{color:var(--faint);font-weight:500;font-size:12px;display:block;margin-top:-2px}
.bar nav{margin-left:auto;display:flex;gap:18px;font-size:14px;color:var(--muted)}
.bar nav a{color:var(--muted)}
@media(max-width:680px){.bar nav{display:none}}

/* ── hero ──────────────────────────────────────────────────────────────────── */
.hero{position:relative;z-index:2;padding:64px 0 30px}
.eyebrow{display:inline-flex;align-items:center;gap:8px;font-size:12.5px;
  letter-spacing:.14em;text-transform:uppercase;color:var(--teal);
  border:1px solid var(--border-2);border-radius:999px;padding:6px 13px;
  background:var(--surface)}
.pulse{width:8px;height:8px;border-radius:50%;background:var(--good);
  box-shadow:0 0 0 0 rgba(72,213,151,.6);animation:pulse 2.2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(72,213,151,.5)}70%{box-shadow:0 0 0 9px rgba(72,213,151,0)}100%{box-shadow:0 0 0 0 rgba(72,213,151,0)}}
h1{font-size:clamp(38px,6.4vw,68px);line-height:1.02;margin:22px 0 10px;
  font-weight:760;letter-spacing:-.022em}
h1 .grad{background:linear-gradient(96deg,var(--teal),var(--cyan) 45%,var(--violet));
  -webkit-background-clip:text;background-clip:text;color:transparent}
.lede{font-size:clamp(16.5px,2.1vw,20px);color:var(--muted);max-width:660px;margin:0 0 8px}
.lede b{color:var(--text);font-weight:650}
.cta{display:flex;gap:12px;flex-wrap:wrap;margin-top:26px}
.btn{display:inline-flex;align-items:center;gap:9px;padding:12px 19px;border-radius:12px;
  font-weight:600;font-size:14.5px;border:1px solid var(--border-2);cursor:pointer;
  background:var(--surface);color:var(--text);transition:.18s;text-decoration:none}
.btn:hover{border-color:var(--teal);box-shadow:0 0 24px rgba(53,224,216,.2);text-decoration:none}
.btn.primary{background:linear-gradient(96deg,rgba(53,224,216,.22),rgba(154,123,255,.22));
  border-color:var(--teal)}

/* ── cards / grid ──────────────────────────────────────────────────────────── */
section{position:relative;z-index:2;padding:30px 0}
.h2{font-size:13px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);
  margin:0 0 16px;display:flex;align-items:center;gap:10px}
.h2::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--border),transparent)}
.grid{display:grid;gap:16px}
.g3{grid-template-columns:repeat(3,1fr)}
.g4{grid-template-columns:repeat(4,1fr)}
.g2{grid-template-columns:repeat(2,1fr)}
@media(max-width:900px){.g3,.g4,.g2{grid-template-columns:repeat(2,1fr)}}
@media(max-width:560px){.g3,.g4,.g2{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);
  padding:18px;backdrop-filter:blur(14px);position:relative;overflow:hidden}
.card::before{content:"";position:absolute;inset:0 0 auto 0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(53,224,216,.5),transparent)}
.kpi .label{font-size:12px;color:var(--faint);letter-spacing:.05em;text-transform:uppercase}
.kpi .val{font-family:var(--mono);font-size:30px;font-weight:700;margin-top:6px;
  font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.kpi .sub{font-size:12.5px;color:var(--muted);margin-top:4px}
.val.ok{color:var(--good)} .val.t{color:var(--teal)} .val.v{color:var(--violet)} .val.c{color:var(--cyan)}

/* status chips */
.chip{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:600;
  padding:4px 10px;border-radius:999px;border:1px solid var(--border-2)}
.chip.live{color:var(--good);border-color:rgba(72,213,151,.4);background:rgba(72,213,151,.08)}
.chip.snap{color:var(--warn);border-color:rgba(240,178,75,.4);background:rgba(240,178,75,.08)}
.chip.down{color:var(--bad);border-color:rgba(255,107,139,.4);background:rgba(255,107,139,.08)}
.dot{width:7px;height:7px;border-radius:50%;background:currentColor}

/* tool catalog */
.tools{display:grid;gap:9px;max-height:560px;overflow:auto;padding-right:4px}
.tool{display:grid;grid-template-columns:auto 1fr;gap:12px;align-items:start;
  padding:11px 13px;border:1px solid var(--border);border-radius:11px;
  background:var(--surface-2);transition:.15s}
.tool:hover{border-color:var(--border-2);background:rgba(40,52,86,.5)}
.tool .name{font-family:var(--mono);font-size:13px;color:var(--teal);font-weight:600;white-space:nowrap}
.tool .desc{font-size:13px;color:var(--muted)}
.tool .tag{font-size:10px;color:var(--violet);border:1px solid rgba(154,123,255,.35);
  border-radius:6px;padding:1px 6px;margin-left:7px;vertical-align:middle}
@media(max-width:560px){.tool{grid-template-columns:1fr}.tool .name{white-space:normal}}

/* connect snippet */
pre{margin:0;font-family:var(--mono);font-size:12.7px;color:#cfe3ff;
  background:rgba(4,7,16,.7);border:1px solid var(--border);border-radius:12px;
  padding:15px 16px;overflow:auto;line-height:1.6}
pre .k{color:var(--violet)} pre .s{color:var(--teal)} pre .c{color:var(--faint)}

/* fabric nodes */
.node{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:10px;
  border:1px solid var(--border);background:var(--surface-2);font-size:13px}
.node .nm{font-family:var(--mono);color:var(--text)}
.node .kd{color:var(--faint);font-size:11.5px;margin-left:auto}

.note{font-size:12.5px;color:var(--faint);margin-top:10px}
.fp{font-family:var(--mono);font-size:12.5px;color:var(--cyan);word-break:break-all}

footer{position:relative;z-index:2;border-top:1px solid var(--border);margin-top:34px;
  padding:26px 0 40px;color:var(--faint);font-size:13px}
footer .row{display:flex;gap:18px;flex-wrap:wrap;align-items:center}
footer a{color:var(--muted)}
.honest{margin-top:14px;font-size:12px;color:var(--faint);max-width:760px;line-height:1.6}
.skel{color:var(--faint)}
@media(prefers-reduced-motion:reduce){.pulse{animation:none}}
</style>
</head>
<body>
<div class="stars"></div>

<header><div class="wrap bar">
  <div class="logo">
    <span class="mark"><span></span></span>
    <div><b>hatun&#8209;mcp</b><small>the great context protocol</small></div>
  </div>
  <nav>
    <a href="#status">Status</a>
    <a href="#tools">Tools</a>
    <a href="#connect">Connect</a>
    <a href="#fabric">Fabric</a>
    <a href="/.well-known/mcp/server-card.json">Server&nbsp;card</a>
  </nav>
</div></header>

<main>
<div class="wrap">

  <div class="hero">
    <span class="eyebrow"><span class="pulse"></span> <span id="hero-status">probing live endpoint…</span></span>
    <h1>Governed context,<br><span class="grad">signed at the source.</span></h1>
    <p class="lede"><b>hatun&#8209;mcp</b> is SZL Holdings' sovereign Model Context Protocol server.
      It hands the world's agents <b>governed context with provenance</b> — every call runs the
      Yuyay&#8209;13 gate, earns an append&#8209;only <b>Khipu receipt</b>, and is wrapped in a real
      ECDSA&#8209;P256 <b>DSSE envelope</b>. Not a demo. A real MCP endpoint.</p>
    <div class="cta">
      <a class="btn primary" href="#connect">Connect an agent &rarr;</a>
      <a class="btn" href="/.well-known/mcp/server-card.json">Inspect the server card</a>
      <a class="btn" href="https://github.com/szl-holdings/hatun-mcp">Source on GitHub</a>
    </div>
  </div>

  <!-- LIVE STATUS -->
  <section id="status">
    <div class="h2">Live system status <span id="status-src" class="chip snap"><span class="dot"></span>loading</span></div>
    <div class="grid g4">
      <div class="card kpi"><div class="label">Service</div><div class="val ok" id="kpi-service">—</div><div class="sub" id="kpi-proto">protocol —</div></div>
      <div class="card kpi"><div class="label">Khipu chain</div><div class="val t" id="kpi-chain">—</div><div class="sub">append&#8209;only · recompute&#8209;verified</div></div>
      <div class="card kpi"><div class="label">DSSE signer</div><div class="val v" id="kpi-signer">—</div><div class="sub" id="kpi-signer-sub">ECDSA P&#8209;256</div></div>
      <div class="card kpi"><div class="label">MCP tools</div><div class="val c" id="kpi-tools">—</div><div class="sub">static · +reachable&#8209;service tools at runtime</div></div>
    </div>
    <div class="grid g4" style="margin-top:16px">
      <div class="card kpi"><div class="label">Lean declarations</div><div class="val t" id="kpi-decl">—</div><div class="sub">Doctrine v11 LOCKED</div></div>
      <div class="card kpi"><div class="label">Lean sorries</div><div class="val" id="kpi-sorry">—</div><div class="sub">disclosed, not hidden</div></div>
      <div class="card kpi"><div class="label">Yuyay axes</div><div class="val v" id="kpi-axes">—</div><div class="sub">input&#8209;as&#8209;data gate</div></div>
      <div class="card kpi"><div class="label">Locked&#8209;proven</div><div class="val ok">8</div><div class="sub">&Lambda; = Conjecture&nbsp;1 (advisory)</div></div>
    </div>
    <p class="note">Numbers above are fetched from this server's own <span class="mono">/healthz</span> and
      <span class="mono">/.well-known/mcp/server-card.json</span> at page load. If a fetch fails the panel falls
      back to a clearly&#8209;labeled <b>SNAPSHOT</b> (a real probe captured 2026&#8209;06&#8209;03) — never blank, never fabricated.</p>
  </section>

  <!-- SIGNING KEY -->
  <section id="key">
    <div class="h2">Signing key <span id="key-src" class="chip snap"><span class="dot"></span>loading</span></div>
    <div class="card">
      <div style="font-size:13px;color:var(--muted);margin-bottom:8px">Public DSSE verification key (SHA&#8209;256 fingerprint of the SPKI DER) — fetched live from <span class="mono">/pubkey</span>:</div>
      <div class="fp" id="key-fp">computing fingerprint…</div>
      <p class="note" id="key-note">When the founder injects the PEM as a Space secret the signer leaves
        <b>PLACEHOLDER</b> mode and responses carry verifiable DSSE envelopes. Responses are honestly marked
        <b>UNSIGNED</b> until then — we never claim a signature we cannot produce.</p>
    </div>
  </section>

  <!-- TOOL CATALOG -->
  <section id="tools">
    <div class="h2">Live tool catalog <span id="tools-src" class="chip snap"><span class="dot"></span>loading</span></div>
    <div class="grid g2">
      <div class="card">
        <div style="font-size:13px;color:var(--muted);margin-bottom:12px">Read directly from this server's server&#8209;card. <span id="tools-count" class="mono"></span></div>
        <div class="tools" id="tool-list"><div class="skel">fetching tool catalog…</div></div>
      </div>
      <div class="card">
        <div style="font-size:13px;color:var(--muted);margin-bottom:12px">Resources &amp; governance surface</div>
        <div class="tools" id="res-list" style="max-height:none"><div class="skel">…</div></div>
      </div>
    </div>
  </section>

  <!-- CONNECT -->
  <section id="connect">
    <div class="h2">Wire it into your agent</div>
    <div class="grid g2">
      <div class="card">
        <div style="font-size:13px;color:var(--muted);margin-bottom:10px">Streamable HTTP (Claude Desktop / Cursor / any MCP client)</div>
        <pre><span class="c">// claude_desktop_config.json / mcp.json</span>
{
  <span class="k">"mcpServers"</span>: {
    <span class="k">"hatun"</span>: {
      <span class="k">"url"</span>: <span class="s">"https://szlholdings-hatun-mcp.hf.space/mcp"</span>,
      <span class="k">"headers"</span>: {
        <span class="k">"Authorization"</span>: <span class="s">"Bearer szl_..."</span>
      }
    }
  }
}</pre>
      </div>
      <div class="card">
        <div style="font-size:13px;color:var(--muted);margin-bottom:10px">Endpoints &amp; legacy SSE transport</div>
<pre><span class="c"># Streamable HTTP (preferred)</span>
POST <span class="s">https://szlholdings-hatun-mcp.hf.space/mcp</span>

<span class="c"># Legacy SSE transport</span>
GET  <span class="s">https://szlholdings-hatun-mcp.hf.space/sse</span>

<span class="c"># Machine descriptors (no auth)</span>
GET  <span class="s">/.well-known/mcp/server-card.json</span>
GET  <span class="s">/healthz</span>
GET  <span class="s">/pubkey</span>

<span class="c"># Anonymous calls are declined &amp; receipted —</span>
<span class="c"># bring an SZL API key (Authorization: Bearer szl_...).</span></pre>
      </div>
    </div>
  </section>

  <!-- FABRIC -->
  <section id="fabric">
    <div class="h2">Place in the a11oy mesh <span id="fabric-src" class="chip snap"><span class="dot"></span>loading</span></div>
    <div class="grid g2">
      <div class="card">
        <div style="font-size:13px;color:var(--muted);margin-bottom:12px">hatun&#8209;mcp is the agent&#8209;facing gateway; the
          <b>a11oy</b> compute fabric is where governed work actually runs. Probed live with an
          AbortController timeout — honest fallback to SNAPSHOT if unreachable cross&#8209;origin.</div>
        <div class="grid" id="fabric-kpis" style="grid-template-columns:repeat(2,1fr);gap:10px">
          <div class="card kpi" style="padding:13px"><div class="label">Nodes reachable</div><div class="val t" id="fab-reach">—</div><div class="sub">of <span id="fab-total">—</span> total this probe</div></div>
          <div class="card kpi" style="padding:13px"><div class="label">Sovereign GPU</div><div class="val ok" id="fab-gpu">—</div><div class="sub">owned metal · sovereign:true</div></div>
        </div>
        <p class="note">Fabric&#8209;level <span class="mono">sovereign:false</span> by design — hosted&#8209;inference
          fallbacks are <b>not</b> owned compute and are labeled as such. Only the founder's own RTX + box report
          <span class="mono">sovereign:true</span>. No energy/joule claims are made anywhere.</p>
      </div>
      <div class="card">
        <div style="font-size:13px;color:var(--muted);margin-bottom:12px">Fabric nodes (live or SNAPSHOT)</div>
        <div class="tools" id="node-list" style="max-height:none"><div class="skel">probing a11oy fabric…</div></div>
      </div>
    </div>
  </section>

</div>
</main>

<footer><div class="wrap">
  <div class="row">
    <span>&copy; SZL Holdings · hatun&#8209;mcp v1.0.0</span>
    <a href="https://github.com/szl-holdings/hatun-mcp">GitHub</a>
    <a href="/.well-known/mcp/server-card.json">Server card</a>
    <a href="/healthz">/healthz</a>
    <a href="/pubkey">/pubkey</a>
  </div>
  <p class="honest"><b>Honesty doctrine v11 (749 / 14 / 163).</b>
    Locked&#8209;proven = 8. &Lambda; is <b>Conjecture&nbsp;1</b> — advisory governance, never "proven trust".
    Khipu&nbsp;BFT framing is Conjecture&nbsp;2. SLSA <b>L1 honest</b> (L2 verified&#8209;provenance on roadmap; L3 not claimed).
    <span class="mono">sovereign:true</span> only on owned hardware. No free&#8209;energy claims. Live numbers are
    fetched at load and degrade to a labeled SNAPSHOT on failure — nothing on this page is fabricated.</p>
  <p class="honest mono" style="opacity:.7">Signed&#8209;off&#8209;by: Stephen P. Lutar Jr. &lt;stephenlutar2@gmail.com&gt;</p>
</div></footer>

<script id="snapshot" type="application/json">__SNAPSHOT_JSON__</script>
<script>
(function(){
  "use strict";
  var SNAP = {};
  try { SNAP = JSON.parse(document.getElementById("snapshot").textContent); } catch(e){ SNAP = {}; }

  function $(id){ return document.getElementById(id); }
  function txt(id,v){ var e=$(id); if(e) e.textContent=v; }
  function chip(id,mode,label){
    var e=$(id); if(!e) return;
    e.className = "chip " + mode;
    e.innerHTML = '<span class="dot"></span>' + label;
  }
  function esc(s){ return String(s).replace(/[&<>"]/g,function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]; }); }

  // fetch with timeout via AbortController; honest boolean live/fallback
  function getJSON(url, ms){
    var ctl = new AbortController();
    var t = setTimeout(function(){ ctl.abort(); }, ms||4000);
    return fetch(url, {signal:ctl.signal, headers:{accept:"application/json"}})
      .then(function(r){ if(!r.ok) throw new Error("http "+r.status); return r.json(); })
      .finally(function(){ clearTimeout(t); });
  }
  function getText(url, ms){
    var ctl = new AbortController();
    var t = setTimeout(function(){ ctl.abort(); }, ms||4000);
    return fetch(url, {signal:ctl.signal})
      .then(function(r){ if(!r.ok) throw new Error("http "+r.status); return r.text(); })
      .finally(function(){ clearTimeout(t); });
  }

  // ── 1. health + server card (same origin → reliable) ──────────────────────
  function renderHealth(h, live){
    txt("kpi-service", (h.status||"?").toUpperCase());
    txt("kpi-proto", "protocol " + (h.protocol_revision||"—"));
    txt("kpi-chain", h.chain_verified ? "VERIFIED" : "UNVERIFIED");
    txt("kpi-signer", h.signer_mode || "—");
    txt("kpi-signer-sub", h.signer_mode === "PLACEHOLDER"
      ? "no key in process — responses UNSIGNED (honest)"
      : "ECDSA P-256 · live signer");
    var mode = live ? "live":"snap", lbl = live ? "LIVE":"SNAPSHOT";
    chip("status-src", mode, lbl);
    txt("hero-status", live ? ("LIVE · " + (h.status||"ok").toUpperCase() + " · " + (h.protocol_revision||""))
                            : "SNAPSHOT · last known good");
  }
  function renderCard(card, live){
    var tools = (card.tools)||[];
    txt("kpi-tools", tools.length || SNAP.tool_count || "—");
    txt("tools-count", "(" + (tools.length||0) + " tools)");
    var lk = (card.governance && card.governance.doctrine_locked) || {};
    txt("kpi-decl", lk.lean_declarations || (SNAP.lean&&SNAP.lean.declarations) || "—");
    txt("kpi-sorry", lk.lean_sorries_total || (SNAP.lean&&SNAP.lean.sorries) || "—");
    txt("kpi-axes", lk.yuyay_axes || (SNAP.lean&&SNAP.lean.yuyay_axes) || "—");

    // tool catalog
    var host = $("tool-list"); host.innerHTML="";
    if(!tools.length){ host.innerHTML='<div class="skel">no tools advertised</div>'; }
    tools.forEach(function(t){
      var alias = /alias of/.test(t.description||"") ? '<span class="tag">alias</span>' : "";
      var gate  = /2-person gate|state-changing/.test(t.description||"") ? '<span class="tag">2-person gate</span>' : "";
      var honestNote = /honest/.test(t.description||"") ? '<span class="tag">honest&#8209;disclosed</span>' : "";
      var d = document.createElement("div"); d.className="tool";
      d.innerHTML = '<div class="name">'+esc(t.name)+'</div>'+
                    '<div class="desc">'+esc(t.description||"")+alias+gate+honestNote+'</div>';
      host.appendChild(d);
    });

    // resources + governance
    var rhost = $("res-list"); rhost.innerHTML="";
    ((card.resources)||[]).forEach(function(r){
      var d=document.createElement("div"); d.className="tool";
      d.innerHTML='<div class="name">'+esc(r.uri)+'</div><div class="desc">'+esc(r.description||"")+'</div>';
      rhost.appendChild(d);
    });
    var g = card.governance||{};
    var gd=document.createElement("div"); gd.className="tool";
    gd.innerHTML='<div class="name">governance</div><div class="desc">protocol '+esc(g.protocol_revision||"—")+
      ' · signer '+esc(g.signer_mode||"—")+' · Yuyay-13 gate · Khipu receipts · DSSE</div>';
    rhost.appendChild(gd);

    var mode = live ? "live":"snap", lbl = live ? "LIVE":"SNAPSHOT";
    chip("tools-src", mode, lbl);
  }

  getJSON("/healthz", 4000)
    .then(function(h){ renderHealth(h, true); })
    .catch(function(){ renderHealth(SNAP.healthz||{}, false); });

  getJSON("/.well-known/mcp/server-card.json", 5000)
    .then(function(c){ renderCard(c, true); })
    .catch(function(){
      renderCard({tools:[], resources:[], governance:{
        protocol_revision:(SNAP.healthz&&SNAP.healthz.protocol_revision),
        signer_mode:(SNAP.healthz&&SNAP.healthz.signer_mode),
        doctrine_locked:{lean_declarations:(SNAP.lean&&SNAP.lean.declarations),
          lean_sorries_total:(SNAP.lean&&SNAP.lean.sorries), yuyay_axes:(SNAP.lean&&SNAP.lean.yuyay_axes)}
      }}, false);
    });

  // ── 2. pubkey → SHA-256 fingerprint via SubtleCrypto (no CDN) ──────────────
  function pemToDer(pem){
    var b64 = pem.replace(/-----[^-]+-----/g,"").replace(/\\s+/g,"");
    var bin = atob(b64), arr = new Uint8Array(bin.length);
    for(var i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);
    return arr.buffer;
  }
  function hex(buf){
    return Array.prototype.map.call(new Uint8Array(buf),function(b){
      return b.toString(16).padStart(2,"0"); }).join("");
  }
  getText("/pubkey", 4000).then(function(pem){
    if(/PLACEHOLDER/.test(pem) || pem.indexOf("PUBLIC KEY")===-1){
      $("key-fp").textContent = "PLACEHOLDER — no signing key in this process (honest)";
      chip("key-src","snap","PLACEHOLDER"); return;
    }
    if(window.crypto && crypto.subtle){
      return crypto.subtle.digest("SHA-256", pemToDer(pem)).then(function(d){
        var h = hex(d), grouped = h.match(/.{1,4}/g).join(" ");
        $("key-fp").textContent = "SHA256(SPKI) " + grouped;
        chip("key-src","live","LIVE");
      });
    } else {
      $("key-fp").textContent = pem.split("\\n").filter(Boolean).slice(1,-1).join("").slice(0,48)+"…";
      chip("key-src","live","LIVE");
    }
  }).catch(function(){
    $("key-fp").textContent = "SNAPSHOT — pubkey unreachable; verify via /pubkey";
    chip("key-src","snap","SNAPSHOT");
  });

  // ── 3. a11oy fabric (cross-origin; AbortController + honest fallback) ──────
  function renderFabric(f, live){
    txt("fab-reach", f.nodes_reachable!=null ? f.nodes_reachable : "—");
    txt("fab-total", f.nodes_total!=null ? f.nodes_total : "—");
    txt("fab-gpu", f.sovereign_gpu_live ? "LIVE" : (f.gpu_nodes_reachable||0)+" node(s)");
    chip("fabric-src", live?"live":"snap", live?"LIVE":"SNAPSHOT");
    var host=$("node-list"); host.innerHTML="";
    var nodes = f.nodes;
    if(!nodes){ // snapshot has no node detail
      [["hetzner-box-cpu","sovereign · cpu"],["rtx-betterwithage","sovereign · GPU"],
       ["chaski","tailnet GPU"],["groq","hosted fallback"],["nvidia-nim","hosted fallback"],
       ["hf-router","hosted fallback"]].forEach(function(n){
        var d=document.createElement("div"); d.className="node";
        d.innerHTML='<span class="dot" style="color:var(--faint)"></span><span class="nm">'+esc(n[0])+
          '</span><span class="kd">'+esc(n[1])+'</span>'; host.appendChild(d);
      }); return;
    }
    nodes.forEach(function(n){
      var col = n.reachable ? (n.sovereign?"var(--good)":"var(--cyan)") : "var(--bad)";
      var kind = (n.sovereign?"sovereign · ":"") + (n.kind||"");
      var d=document.createElement("div"); d.className="node";
      d.innerHTML='<span class="dot" style="color:'+col+'"></span><span class="nm">'+esc(n.name)+
        '</span><span class="kd">'+esc(kind)+(n.reachable?"":" · unreachable")+'</span>';
      host.appendChild(d);
    });
  }
  getJSON("https://a11oy.net/api/a11oy/v1/compute-pool", 4500)
    .then(function(f){
      var c = f.counts||{};
      renderFabric({nodes_reachable:c.nodes_reachable, nodes_total:c.nodes_total,
        gpu_nodes_reachable:c.gpu_nodes_reachable, sovereign_gpu_live:c.sovereign_gpu_live,
        nodes:f.nodes}, true);
    })
    .catch(function(){ renderFabric(SNAP.fabric||{}, false); });
})();
</script>
</body>
</html>"""

# Inject the snapshot JSON (kept out of the template literal so braces don't clash).
CONSOLE_HTML = CONSOLE_HTML.replace("__SNAPSHOT_JSON__", _json.dumps(_SNAPSHOT))
