"""Hatun Gateway console for the SZL Obsidian Signal product family.

The document is self-contained, same-origin only, mobile-first, and source-bound.
Every operational value is read from ``/api/console-state`` in the running
process. Decorative weave geometry is presentation, never telemetry.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

from html import escape

from .deployment import PUBLIC_BASE

REPO_URL = "https://github.com/szl-holdings/hatun-mcp"
# Compatibility export; the configured runtime is not a standalone HF Space.
SPACE_URL = PUBLIC_BASE

CONSOLE_HTML = r"""<!doctype html>
<html lang="en" data-theme="dark" data-szl-family="obsidian-signal" data-szl-surface="hatun">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<title>Hatun Gateway · governed context mesh</title>
<meta name="description" content="Hatun is a governed Model Context Protocol gateway: inspect its live registry, build against its interfaces, and verify source-bound evidence.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='12.5' fill='none' stroke='%239e9bff' stroke-width='1.5'/%3E%3Ccircle cx='16' cy='16' r='3.5' fill='%2370dbff'/%3E%3C/svg%3E">
<style>
:root{
  --deep:#02030a;--bg:#060711;--panel:#0d1020;--panel2:#151a31;
  --ink:#f1f3f6;--bone:#e8e2d6;--muted:#9aa5b7;--faint:#667186;
  --violet:#9e9bff;--ice:#70dbff;--signal:#e3b76e;--success:#65d9ae;--danger:#ef746f;
  --line:color-mix(in srgb,var(--ink) 11%,transparent);
  --line-violet:color-mix(in srgb,var(--violet) 32%,transparent);
  --shadow:0 28px 92px rgb(0 0 0 / .46);
  --head:Inter,"SF Pro Display","Segoe UI",system-ui,-apple-system,sans-serif;
  --mono:"SFMono-Regular","Cascadia Code","Roboto Mono",ui-monospace,Menlo,Consolas,monospace;
  --max:1180px;
}
*{box-sizing:border-box}
html{min-width:0;max-width:100%;overflow-x:clip;background:var(--deep);scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{margin:0;min-width:0;max-width:100%;overflow-x:clip;color:var(--ink);background:
  radial-gradient(circle at 78% 10%,rgb(158 155 255 / .13),transparent 30rem),
  radial-gradient(circle at 16% 54%,rgb(112 219 255 / .065),transparent 28rem),
  linear-gradient(180deg,var(--deep),var(--bg) 48%,var(--deep));
  font-family:var(--head);line-height:1.55;text-rendering:optimizeLegibility;-webkit-font-smoothing:antialiased}
a{color:inherit}.shell{width:min(var(--max),calc(100% - 28px));margin-inline:auto}.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
:where(h1,h2,h3){color:var(--ink);letter-spacing:-.04em;text-wrap:balance}:where(p,li){text-wrap:pretty}:where(pre,code,td,th,a){overflow-wrap:anywhere}
::selection{color:var(--deep);background:var(--ice)}
:where(a,button,input,textarea,select,summary,[tabindex]):focus-visible{outline:2px solid var(--ice);outline-offset:3px}

.family-rail{position:sticky;top:0;z-index:50;min-height:60px;display:grid;grid-template-columns:minmax(180px,.7fr) minmax(0,1fr);align-items:center;gap:12px;padding:max(8px,env(safe-area-inset-top)) max(14px,env(safe-area-inset-right)) 8px max(14px,env(safe-area-inset-left));border-bottom:1px solid var(--line);background:color-mix(in srgb,var(--deep) 88%,transparent);backdrop-filter:blur(22px) saturate(118%);box-shadow:0 14px 46px rgb(0 0 0 / .2)}
.identity{min-width:0;min-height:44px;display:inline-flex;align-items:center;gap:11px;text-decoration:none}.mark{position:relative;width:28px;height:28px;flex:0 0 auto;border:1px solid var(--line-violet);border-radius:50%;background:conic-gradient(from 42deg,var(--violet),transparent 18% 33%,var(--ice) 34% 52%,transparent 53% 71%,var(--signal) 72% 73%,transparent 74%);box-shadow:0 0 24px rgb(158 155 255 / .18)}
.mark::after{position:absolute;inset:10px;border-radius:50%;background:var(--ice);box-shadow:0 0 12px var(--ice);content:""}.identity-copy{min-width:0;display:grid;gap:1px}.identity-copy small{color:var(--faint);font:700 9px/1.2 var(--mono);letter-spacing:.18em;text-transform:uppercase}.identity-copy strong{overflow:hidden;font:650 14px/1.25 var(--head);text-overflow:ellipsis;white-space:nowrap}
.family-links{min-width:0;display:flex;align-items:center;justify-content:flex-end;gap:4px;overflow-x:auto;overscroll-behavior-inline:contain;scroll-snap-type:x proximity;scrollbar-width:thin;scrollbar-color:rgb(158 155 255 / .3) transparent;touch-action:pan-x;-webkit-overflow-scrolling:touch}.family-links::-webkit-scrollbar{height:4px}.family-links::-webkit-scrollbar-thumb{border-radius:999px;background:rgb(158 155 255 / .3)}
.family-links a{min-height:44px;flex:0 0 auto;display:inline-flex;align-items:center;padding:8px 11px;border:1px solid transparent;border-radius:9px;color:var(--muted);font:700 10px/1.15 var(--mono);letter-spacing:.08em;text-decoration:none;text-transform:uppercase;white-space:nowrap;scroll-snap-align:start;touch-action:manipulation}.family-links a:hover,.family-links a[aria-current="page"]{border-color:var(--line-violet);color:var(--ink);background:rgb(158 155 255 / .065)}

.hero{position:relative;min-height:min(770px,86vh);display:grid;align-items:center;overflow:hidden;border-bottom:1px solid var(--line)}.weave{position:absolute;inset:-18%;pointer-events:none;opacity:.64;mask-image:linear-gradient(to bottom,#000,transparent 94%);background:
  repeating-linear-gradient(28deg,transparent 0 54px,rgb(158 155 255 / .10) 55px 56px),
  repeating-linear-gradient(152deg,transparent 0 88px,rgb(112 219 255 / .065) 89px 90px);
  transform:perspective(950px) rotateX(58deg) rotateZ(-8deg) scale(1.15)}
.hero::after{position:absolute;inset:0;pointer-events:none;background:linear-gradient(90deg,var(--deep),rgb(2 3 10 / .75) 48%,transparent 78%),linear-gradient(180deg,transparent 62%,var(--deep));content:""}.hero-grid{position:relative;z-index:1;display:grid;grid-template-columns:minmax(0,1.08fr) minmax(320px,.92fr);gap:clamp(34px,7vw,92px);align-items:center;padding-block:clamp(72px,11vw,150px)}
.eyebrow{margin:0;color:var(--violet);font:750 10px/1.4 var(--mono);letter-spacing:.19em;text-transform:uppercase}h1{max-width:820px;margin:16px 0 0;font-size:clamp(46px,7.8vw,108px);font-weight:530;line-height:.9;letter-spacing:-.07em}h1 span{color:var(--ice)}.lede{max-width:65ch;margin:26px 0 0;color:var(--muted);font-size:clamp(16px,1.55vw,20px);line-height:1.65}.hero-actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:30px}.button{min-height:48px;display:inline-flex;align-items:center;justify-content:center;padding:11px 16px;border:1px solid var(--line);border-radius:10px;color:var(--ink);background:rgb(13 16 32 / .78);font:700 11px/1.2 var(--mono);letter-spacing:.07em;text-decoration:none;touch-action:manipulation}.button.primary{border-color:var(--line-violet);background:linear-gradient(135deg,rgb(158 155 255 / .17),rgb(112 219 255 / .07))}.button:hover{border-color:color-mix(in srgb,var(--ice) 52%,transparent);transform:translateY(-1px)}
.instrument{position:relative;min-height:430px;overflow:hidden;border:1px solid var(--line);border-radius:24px;background:rgb(7 8 17 / .84);box-shadow:var(--shadow);backdrop-filter:blur(18px)}.instrument-head{display:flex;align-items:center;gap:9px;padding:14px 16px;border-bottom:1px solid var(--line);color:var(--muted);font:700 10px/1.2 var(--mono);letter-spacing:.1em;text-transform:uppercase}.pulse{width:7px;height:7px;border-radius:50%;background:var(--faint)}.instrument[data-state="READY"] .pulse,.instrument[data-state="SIGNED"] .pulse{background:var(--success);box-shadow:0 0 14px var(--success)}.instrument[data-state="NOT-READY"] .pulse,.instrument[data-state="UNSIGNED"] .pulse{background:var(--signal);box-shadow:0 0 14px var(--signal)}.instrument[data-state="UNAVAILABLE"] .pulse{background:var(--danger)}
.gateway-map{position:relative;height:300px}.gateway-map::before{position:absolute;inset:0;background:linear-gradient(rgb(255 255 255 / .035) 1px,transparent 1px),linear-gradient(90deg,rgb(255 255 255 / .035) 1px,transparent 1px);background-size:38px 38px;content:""}.thread{position:absolute;height:1px;transform-origin:left center;background:linear-gradient(90deg,var(--violet),var(--ice),transparent);opacity:.48}.thread:nth-child(1){left:12%;top:24%;width:62%;transform:rotate(12deg)}.thread:nth-child(2){left:24%;top:64%;width:57%;transform:rotate(-27deg)}.thread:nth-child(3){left:37%;top:19%;width:45%;transform:rotate(61deg)}.thread:nth-child(4){left:9%;top:78%;width:64%;transform:rotate(-51deg)}
.node{position:absolute;width:10px;height:10px;border:1px solid currentColor;border-radius:50%;color:var(--violet);box-shadow:0 0 18px currentColor;transform:translate(-50%,-50%)}.node::after{position:absolute;inset:3px;border-radius:50%;background:currentColor;content:""}.node.n1{left:13%;top:24%}.node.n2{left:47%;top:31%;color:var(--ice)}.node.n3{left:78%;top:42%;color:var(--signal)}.node.n4{left:25%;top:69%;color:var(--ice)}.node.n5{left:69%;top:75%}
.instrument-readings{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid var(--line)}.reading{min-width:0;padding:14px;border-right:1px solid var(--line)}.reading:last-child{border-right:0}.reading small{display:block;color:var(--faint);font:700 9px/1.2 var(--mono);letter-spacing:.12em;text-transform:uppercase}.reading strong{display:block;margin-top:6px;font:650 13px/1.3 var(--mono);overflow-wrap:anywhere}

.pathways{display:grid;grid-template-columns:1fr;gap:1px;background:var(--line);border-bottom:1px solid var(--line)}.pathway{min-height:0;padding:clamp(24px,4vw,42px);background:var(--deep);text-decoration:none}.pathway small{color:var(--faint);font:700 10px/1.2 var(--mono);letter-spacing:.15em;text-transform:uppercase}.pathway h2{margin:14px 0 0;font-size:clamp(26px,3vw,40px)}.pathway p{max-width:38ch;margin:10px 0 0;color:var(--muted)}.pathway:hover h2{color:var(--ice)}
.kpis{display:grid;grid-template-columns:1fr;gap:1px;background:var(--line);border-bottom:1px solid var(--line)}.kpi{min-width:0;padding:clamp(18px,4vw,26px);background:var(--bg)}.kpi .value{font:650 clamp(24px,5vw,38px)/1.1 var(--mono);letter-spacing:-.03em;font-variant-numeric:tabular-nums}.kpi .label{margin-top:8px;color:var(--faint);font:700 10px/1.35 var(--mono);letter-spacing:.1em;text-transform:uppercase}
section.content{padding-block:clamp(58px,8vw,108px);border-bottom:1px solid var(--line)}.section-head{display:grid;grid-template-columns:1fr;gap:20px;align-items:end;margin-bottom:32px}.section-head h2{margin:12px 0 0;font-size:clamp(34px,5vw,66px);font-weight:530;line-height:.98;letter-spacing:-.055em}.section-head .sub{max-width:62ch;margin:0;color:var(--muted)}.grid{display:grid;grid-template-columns:1fr;gap:12px}
.card{position:relative;min-width:0;overflow:hidden;border:1px solid var(--line);border-radius:16px;background:linear-gradient(145deg,rgb(21 26 49 / .64),transparent 48%),rgb(8 9 19 / .92);padding:20px;box-shadow:0 20px 66px rgb(0 0 0 / .26)}.card::before{position:absolute;inset:0;pointer-events:none;background:radial-gradient(circle at 80% 0,rgb(158 155 255 / .085),transparent 19rem);content:""}.card>*{position:relative}.card:hover{border-color:var(--line-violet)}.card .title{margin:9px 0 0;font-size:clamp(16px,2.1vw,20px);font-weight:650;letter-spacing:-.02em}.card .description{margin:9px 0 0;color:var(--muted);font-size:14px}.metrics{display:flex;flex-wrap:wrap;gap:7px 15px;margin-top:14px;color:var(--muted);font:600 11px/1.45 var(--mono);font-variant-numeric:tabular-nums}.metrics b{color:var(--ink);font-weight:650}.chip{min-height:30px;display:inline-flex;align-items:center;margin-top:14px;padding:5px 9px;border:1px solid currentColor;border-radius:999px;color:var(--muted);font:700 9px/1.2 var(--mono);letter-spacing:.09em;text-transform:uppercase}.chip[data-state="MEASURED"],.chip[data-state="MATCH"],.chip[data-state="READY"],.chip[data-state="SIGNED"],.chip[data-state="VERIFIED"]{color:var(--success)}.chip[data-state="DECLARED"],.chip[data-state="OBSERVED"],.chip[data-state="UNSIGNED"],.chip[data-state="NOT-READY"],.chip[data-state="DIVERGENT"]{color:var(--signal)}.chip[data-state="UNAVAILABLE"],.chip[data-state="FAILED"]{color:var(--danger)}.foot{margin-top:14px;padding-top:13px;border-top:1px solid var(--line);color:var(--faint);font:600 10px/1.55 var(--mono)}.foot a{color:var(--ice);text-decoration:none}.loading{color:var(--muted);font:650 11px/1.55 var(--mono)}
pre{margin:14px 0 0;padding:16px;overflow-x:auto;border:1px solid var(--line);border-radius:12px;color:var(--ink);background:var(--deep);font:500 12px/1.7 var(--mono)}pre .comment{color:var(--faint)}pre .key{color:var(--violet)}
.disclosure{margin-top:24px;padding:18px 20px;border-left:2px solid var(--signal);color:var(--muted);background:rgb(227 183 110 / .045);font:500 12px/1.72 var(--mono)}
footer{padding:34px 0 calc(34px + env(safe-area-inset-bottom));color:var(--faint);font:600 10px/1.65 var(--mono)}footer .row{display:flex;flex-wrap:wrap;align-items:center;gap:11px 22px}footer a{color:var(--muted);text-decoration:none}footer .honesty{max-width:82ch;margin:18px 0 0;color:var(--muted)}

@media (min-width:760px){.pathways{grid-template-columns:repeat(3,minmax(0,1fr))}.kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.grid.g2{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (min-width:1000px){.kpis{grid-template-columns:repeat(4,minmax(0,1fr))}.grid.g3{grid-template-columns:repeat(3,minmax(0,1fr))}.section-head{grid-template-columns:.46fr 1fr}}
@media (max-width:900px){.hero{min-height:0}.hero-grid{grid-template-columns:1fr}.instrument{min-height:370px}.family-rail{grid-template-columns:1fr}.family-links{justify-content:flex-start}.weave{opacity:.42}}
@media (max-width:620px){.shell{width:min(var(--max),calc(100% - 20px))}.family-rail{align-items:flex-start}.identity-copy small{display:none}.family-links{width:100%}.instrument-readings{grid-template-columns:1fr}.reading{border-right:0;border-bottom:1px solid var(--line)}.reading:last-child{border-bottom:0}h1{font-size:clamp(44px,15vw,70px)}}
@media (prefers-reduced-motion: reduce){html{scroll-behavior:auto}*,*::before,*::after{animation:none!important;transition:none!important}.button:hover{transform:none}}
@media (prefers-contrast: more){:root{--line:rgb(241 243 246 / .38);--line-violet:rgb(158 155 255 / .7)}.weave{opacity:.2}.family-rail{background:var(--deep);backdrop-filter:none}}
@media (forced-colors: active){.weave{display:none}.family-rail,.instrument,.card,.button,.pathway,pre{border:1px solid CanvasText;color:CanvasText;background:Canvas;box-shadow:none}.mark{border-color:CanvasText;background:Canvas}}
@media print{.family-rail,.weave{display:none!important}body{color:#000!important;background:#fff!important}.instrument,.card,.pathway,pre{color:#000!important;background:#fff!important;box-shadow:none!important}}

/* Operator proposal form: existing family tokens, no external assets. */
#proposal{scroll-margin-top:136px}
.proposal-form label{display:block;margin:16px 0 7px;color:var(--ink);font:650 12px/1.5 var(--head)}
.proposal-form fieldset{min-width:0;margin:0;padding:0;border:0}
.proposal-form textarea,.proposal-form input{display:block;width:100%;min-height:48px;padding:12px;border:1px solid var(--line-violet);border-radius:10px;color:var(--ink);background:var(--deep);font:500 14px/1.6 var(--mono)}
.proposal-form textarea{min-height:150px;resize:vertical}
.proposal-form textarea,.proposal-form input{scroll-margin-top:150px}
.proposal-form .hint{margin:7px 0;color:var(--muted);font-size:12px}
.proposal-form .controls{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}
.proposal-form button{cursor:pointer}
.proposal-form button:disabled{cursor:default;opacity:.55;transform:none}
.proposal-form fieldset:disabled{opacity:.7}
.proposal-status{min-height:3em;margin:0 0 16px;color:var(--muted);font:600 12px/1.65 var(--mono);overflow-wrap:anywhere}
.proposal-output{min-height:140px;max-height:420px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}
.proposal-evidence{display:grid;grid-template-columns:minmax(95px,.36fr) minmax(0,1fr);gap:10px 14px;margin:20px 0 0;font:500 11px/1.6 var(--mono)}
.proposal-evidence[hidden],.proposal-details[hidden]{display:none}
.proposal-evidence dt{color:var(--muted)}
.proposal-evidence dd{min-width:0;margin:0;overflow-wrap:anywhere}
.proposal-details{margin-top:20px}
.proposal-details summary{min-height:44px;display:flex;align-items:center;cursor:pointer;color:var(--ice);font:650 12px/1.5 var(--mono)}
.proposal-details pre{max-height:360px;white-space:pre-wrap;overflow-wrap:anywhere}
@media print{.proposal-form{display:none!important}}

</style>
</head>
<body>
<header class="family-rail">
  <a class="identity" href="/" aria-label="Open Hatun Gateway"><span class="mark" aria-hidden="true"></span><span class="identity-copy"><small>SZL / Obsidian Signal</small><strong>Hatun Gateway</strong></span></a>
  <nav class="family-links" aria-label="Hatun pathways"><a href="#understand" aria-current="page">Understand</a><a href="#connect">Build</a><a href="#proposal">Ask Cortex</a><a href="/.well-known/mcp-manifest-attestation">Verify</a><a href="/.well-known/mcp/server-card.json">Server card</a><a href="https://github.com/szl-holdings/hatun-mcp" rel="noopener">Source</a></nav>
</header>

<main>
<section class="hero" id="understand">
  <div class="weave" aria-hidden="true"></div>
  <div class="shell hero-grid">
    <div>
      <p class="eyebrow">Governed context gateway · streamable HTTP</p>
      <h1>Context in.<br><span>Evidence out.</span></h1>
      <p class="lede">Hatun connects an agent to governed tools, resources, provenance, and receipts. Every operational value on this surface is read from the running Python process. Missing state stays UNAVAILABLE.</p>
      <div class="hero-actions"><a class="button primary" href="#connect">Connect an agent</a><a class="button" href="/.well-known/mcp/server-card.json">Inspect the server card</a><a class="button" href="https://github.com/szl-holdings/hatun-mcp" rel="noopener">Source on GitHub</a></div>
    </div>
    <aside class="instrument" id="gateway-instrument" data-state="UNAVAILABLE" aria-label="Live Hatun gateway state">
      <div class="instrument-head"><span class="pulse" aria-hidden="true"></span><span id="instrument-state">UNAVAILABLE · reading process state</span></div>
      <div class="gateway-map" aria-hidden="true"><i class="thread"></i><i class="thread"></i><i class="thread"></i><i class="thread"></i><i class="node n1"></i><i class="node n2"></i><i class="node n3"></i><i class="node n4"></i><i class="node n5"></i></div>
      <div class="instrument-readings"><div class="reading"><small>Transport</small><strong id="read-transport">UNAVAILABLE</strong></div><div class="reading"><small>Registry</small><strong id="read-registry">UNAVAILABLE</strong></div><div class="reading"><small>Evidence</small><strong id="read-evidence">UNAVAILABLE</strong></div></div>
    </aside>
  </div>
</section>

<nav class="pathways" aria-label="Primary Hatun journey">
  <a class="pathway" href="#runtime"><small>01 · Understand</small><h2>Read the process</h2><p>Inspect transport, chain, signer, build identity, parity, and organ registration.</p></a>
  <a class="pathway" href="#connect"><small>02 · Build</small><h2>Use the interfaces</h2><p>Connect through the trailing-slash streamable HTTP endpoint and discover live tools.</p></a>
  <a class="pathway" href="/.well-known/mcp-manifest-attestation"><small>03 · Verify</small><h2>Follow the evidence</h2><p>Check the exact cached server-card bytes and their source-bound attestation.</p></a>
</nav>

<div class="kpis" aria-label="Live process summary">
  <div class="kpi"><div class="value" id="kpi-tools">UNAVAILABLE</div><div class="label">Tools in live registry</div></div>
  <div class="kpi"><div class="value" id="kpi-chain">UNAVAILABLE</div><div class="label">Receipt chain</div></div>
  <div class="kpi"><div class="value" id="kpi-receipts">UNAVAILABLE</div><div class="label">Receipts this process</div></div>
  <div class="kpi"><div class="value" id="kpi-parity">UNAVAILABLE</div><div class="label">Card ↔ runtime parity</div></div>
</div>

<section class="content" id="runtime"><div class="shell">
  <div class="section-head"><div><p class="eyebrow">Runtime / source-bound readings</p><h2>What this process can establish.</h2></div><p class="sub">A transport response is not correctness. Each panel retains the state emitted by the live process; unreadable values carry no invented number.</p></div>
  <div class="grid g3" id="runtime-cards"><article class="card"><div class="loading">Reading /api/console-state…</div></article></div>
</div></section>


<section class="content" id="proposal"><div class="shell">
  <div class="section-head"><div><p class="eyebrow">Operator / governed proposal</p><h2>Ask owned Cortex.</h2></div><p class="sub">Send a bounded question through this gateway, then inspect the source, model, and receipt returned with the answer. A proposal carries no authority to execute an action.</p></div>
  <div class="grid g2">
    <form class="card proposal-form" id="proposal-form" method="post" action="/mcp/" autocomplete="off">
      <p class="eyebrow">One question / one explicit request</p>
      <fieldset id="proposal-fields" disabled>
        <label for="proposal-prompt">Question</label>
        <textarea id="proposal-prompt" rows="6" maxlength="4000" required spellcheck="false" aria-describedby="proposal-prompt-hint"></textarea>
        <p class="hint" id="proposal-prompt-hint">Up to 4,000 characters; surrounding whitespace is removed. This request uses at most 64 generated tokens and three evidence handles. Review your text before sending.</p>
        <label for="proposal-key">Admitted operator API key</label>
        <input id="proposal-key" type="password" maxlength="256" required autocomplete="off" autocapitalize="none" spellcheck="false" aria-describedby="proposal-key-hint">
        <p class="hint" id="proposal-key-hint">Used only for this request to this gateway. The field clears before sending; the client uses no browser storage. Payment credentials do not admit this capability.</p>
      </fieldset>
      <div class="controls"><button class="button primary" id="proposal-submit" type="submit" disabled>Request a proposal</button><button class="button" id="proposal-cancel" type="button" disabled>Stop waiting</button><button class="button" id="proposal-clear" type="button">Clear</button></div>
      <noscript><p class="hint">JavaScript is required to make an authenticated proposal request.</p></noscript>
      <p class="hint">The fixed owned Cortex receives your question through Hatun. Your operator key stays at this gateway. This form does not issue credentials or authorize consequential actions.</p>
    </form>
    <article class="card" aria-label="Proposal and evidence">
      <p class="proposal-status" id="proposal-status" role="status" aria-live="polite">No proposal requested.</p>
      <pre class="proposal-output" id="proposal-output" aria-label="Model proposal">No proposal to display.</pre>
      <dl class="proposal-evidence" id="proposal-evidence" hidden></dl>
      <details class="proposal-details" id="proposal-details" hidden><summary>Inspect the returned evidence</summary><pre id="proposal-raw"></pre></details>
      <p class="hint description">Results describe a single request. They do not establish current readiness, a verified signature, durable storage, or mathematical proof replay. Model text is displayed as text.</p>
    </article>
  </div>
</div></section>

<section class="content" id="tools"><div class="shell">
  <div class="section-head"><div><p class="eyebrow">Capabilities / live registry</p><h2>Tools Hatun exposes <span class="mono" id="tools-count"></span></h2></div><p class="sub">Enumerated in-request from the FastMCP tool manager. The page carries no hand-written capability count.</p></div>
  <div class="grid g3" id="tool-cards"><article class="card"><div class="loading">Enumerating the live tool registry…</div></article></div>
</div></section>

<section class="content" id="resources"><div class="shell">
  <div class="section-head"><div><p class="eyebrow">Resources / readable context</p><h2>Source handles, not decorative claims.</h2></div><p class="sub">Every resource card comes from the process resource manager. An empty or unreadable registry remains explicit.</p></div>
  <div class="grid g2" id="resource-cards"><article class="card"><div class="loading">Reading the resource registry…</div></article></div>
</div></section>

<section class="content" id="connect"><div class="shell">
  <div class="section-head"><div><p class="eyebrow">Build / connect</p><h2>Wire Hatun into an agent.</h2></div><p class="sub">Use the trailing-slash transport endpoint. Descriptors are public; governed tool calls require the configured bearer credential.</p></div>
  <div class="grid g2">
    <article class="card"><p class="eyebrow">Client configuration</p><pre><span class="comment">// claude_desktop_config.json / mcp.json</span>
{
  <span class="key">"mcpServers"</span>: {
    <span class="key">"hatun"</span>: {
      <span class="key">"url"</span>: "__HATUN_PUBLIC_BASE__/mcp/",
      <span class="key">"headers"</span>: {
        <span class="key">"Authorization"</span>: "Bearer szl_..."
      }
    }
  }
}</pre></article>
    <article class="card"><p class="eyebrow">Source-bound interfaces</p><pre><span class="comment"># transport</span>
POST /mcp/          <span class="comment">streamable HTTP</span>
GET  /sse/          <span class="comment">disabled · HTTP 410</span>

<span class="comment"># understand</span>
GET  /api/console-state
GET  /.well-known/mcp/server-card.json
GET  /connect

<span class="comment"># verify</span>
GET  /.well-known/mcp-manifest-attestation
GET  /api/build-info
GET  /healthz  /readyz  /pubkey</pre></article>
  </div>
  <div class="disclosure"><strong>Honesty boundary.</strong> Λ is <strong>Conjecture&nbsp;1 · not a theorem</strong>. Khipu BFT framing remains Conjecture 2. Signing is SIGNED only when a real ECDSA P-256 key is loaded. No energy, consciousness, or unmeasured autonomy claim is made. Decorative weave lines are not telemetry.</div>
</div></section>
</main>

<footer><div class="shell"><div class="row"><span>© SZL · Hatun Gateway</span><a href="https://github.com/szl-holdings/hatun-mcp" rel="noopener">GitHub</a><a href="/.well-known/mcp/server-card.json">Server card</a><a href="/api/console-state">Console state</a><a href="/healthz">Health</a><a href="/pubkey">Public key</a></div><p class="honesty mono" id="foot-label">UNAVAILABLE until /api/console-state is read in this request.</p><p class="honesty">Every visible operational value originates in the running Python process. A failed read displays UNAVAILABLE and no number. <span class="mono" id="foot-locked"></span></p></div></footer>

<script>
(function(){
  "use strict";
  var UNAVAILABLE="UNAVAILABLE";
  function $(id){return document.getElementById(id)}
  function txt(id,value){var node=$(id);if(node)node.textContent=value===null||value===undefined||value===""?UNAVAILABLE:String(value)}
  function esc(value){return String(value===null||value===undefined?"":value).replace(/[&<>\"]/g,function(char){return {"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;"}[char]})}
  function num(value){return value===null||value===undefined?UNAVAILABLE:String(value)}
  function normalize(value){var state=String(value||UNAVAILABLE).toUpperCase();return /^[A-Z][A-Z-]*$/.test(state)?state:UNAVAILABLE}
  function getJSON(url,ms){var controller=new AbortController();var timer=setTimeout(function(){controller.abort()},ms||6000);return fetch(url,{cache:"no-store",signal:controller.signal,headers:{accept:"application/json"}}).then(function(response){if(!response.ok)throw new Error("HTTP "+response.status);return response.json()}).finally(function(){clearTimeout(timer)})}
  function getText(url,ms){var controller=new AbortController();var timer=setTimeout(function(){controller.abort()},ms||5000);return fetch(url,{cache:"no-store",signal:controller.signal}).then(function(response){if(!response.ok)throw new Error("HTTP "+response.status);return response.text()}).finally(function(){clearTimeout(timer)})}

  function card(o){
    var article=document.createElement("article");article.className="card";
    var label=normalize(o.label||UNAVAILABLE);
    var markup='<p class="eyebrow">'+esc(o.eyebrow||"")+'</p><h3 class="title">'+esc(o.title||UNAVAILABLE)+'</h3>';
    if(o.desc)markup+='<p class="description">'+esc(o.desc)+'</p>';
    if(o.metrics&&o.metrics.length)markup+='<div class="metrics">'+o.metrics.map(function(metric){return '<span>'+esc(metric[0])+' <b>'+esc(metric[1])+'</b></span>'}).join("")+'</div>';
    markup+='<span class="chip" data-state="'+esc(label)+'">'+esc(label)+'</span>';
    if(o.foot)markup+='<div class="foot">'+o.foot+'</div>';
    article.innerHTML=markup;return article;
  }
  function fill(id,cards){var host=$(id);if(!host)return;host.textContent="";if(!cards.length){host.appendChild(card({eyebrow:"NO READING",title:UNAVAILABLE,desc:"This registry could not be read in this request.",label:UNAVAILABLE}));return}cards.forEach(function(item){host.appendChild(item)})}
  function shortHash(value){if(!value)return UNAVAILABLE;if(/^0{64}$/.test(value))return "GENESIS";return value.slice(0,12)+"…"+value.slice(-6)}

  function renderUnavailable(){
    ["read-transport","read-registry","read-evidence","kpi-tools","kpi-chain","kpi-receipts","kpi-parity"].forEach(function(id){txt(id,UNAVAILABLE)});
    $("gateway-instrument").dataset.state=UNAVAILABLE;txt("instrument-state","UNAVAILABLE · process state not read");txt("foot-label","UNAVAILABLE — /api/console-state did not answer this request.");txt("foot-locked","");fill("runtime-cards",[]);fill("tool-cards",[]);fill("resource-cards",[])
  }

  function render(state){
    var runtime=state.runtime||{},signing=state.signing||{},khipu=state.khipu||{},build=state.build||{},health=state.health||{},tools=state.tools||{},resources=state.resources||{},parity=state.card_parity||{},organs=state.organs||{},doctrine=state.doctrine||{};
    var instrumentState=normalize(health.readiness||UNAVAILABLE);$("gateway-instrument").dataset.state=instrumentState;txt("instrument-state",instrumentState+" · in-request process read");txt("read-transport",runtime.transport);txt("read-registry",tools.state);txt("read-evidence",khipu.chain);txt("kpi-tools",num(tools.count));txt("kpi-chain",khipu.chain);txt("kpi-receipts",num(khipu.receipts_this_process));txt("kpi-parity",parity.state);txt("foot-label","Read "+(state.generated_at||UNAVAILABLE)+" · signing "+(signing.state||UNAVAILABLE)+" · chain "+(khipu.chain||UNAVAILABLE));txt("foot-locked",num(doctrine.lean_declarations)+" declarations · "+num(doctrine.lean_axioms_unique)+" unique axioms · "+num(doctrine.lean_sorries_total)+" sorries · "+num(doctrine.yuyay_axes)+" Yuyay axes");

    fill("runtime-cards",[
      card({eyebrow:"RUNTIME · TRANSPORT",title:runtime.transport||UNAVAILABLE,desc:"The MCP transport served by this process.",metrics:[["protocol",runtime.protocol_revision||UNAVAILABLE],["python",runtime.python||UNAVAILABLE],["uptime s",num(runtime.uptime_seconds)]],label:"MEASURED"}),
      card({eyebrow:"GOVERNANCE · KHIPU",title:khipu.chain||UNAVAILABLE,desc:"Append-only receipt-chain state recomputed by the process.",metrics:[["receipts",num(khipu.receipts_this_process)],["head",shortHash(khipu.head_hash)]],label:khipu.chain||UNAVAILABLE}),
      card({eyebrow:"ATTESTATION · SIGNER",title:signing.state||UNAVAILABLE,desc:signing.state==="SIGNED"?"A real ECDSA P-256 key is loaded in this process.":"No compatible signing key is loaded; responses remain UNSIGNED.",metrics:[["mode",signing.signer_mode||UNAVAILABLE],["algorithm",signing.algorithm||UNAVAILABLE],["transparency",signing.transparency_log||UNAVAILABLE]],label:signing.state||UNAVAILABLE,foot:'<a href="/pubkey">/pubkey</a> · <span id="key-fp">fingerprint reading…</span>'}),
      card({eyebrow:"PROVENANCE · BUILD",title:build.state||UNAVAILABLE,desc:"Exact Git revision injected at deployment, or UNAVAILABLE.",metrics:[["revision",build.revision?build.revision.slice(0,12):UNAVAILABLE]],label:build.state||UNAVAILABLE,foot:'<a href="/api/build-info">/api/build-info</a>'}),
      card({eyebrow:"DISCOVERY · PARITY",title:parity.state||UNAVAILABLE,desc:"Measured comparison between the published card and runtime registry.",metrics:[["card",num(parity.card_tool_count)],["runtime",num(parity.runtime_tool_count)],["only card",String((parity.only_in_card||[]).length)],["only runtime",String((parity.only_in_runtime||[]).length)]],label:parity.state||UNAVAILABLE,foot:'<a href="/.well-known/mcp/server-card.json">server card</a>'}),
      card({eyebrow:"FEDERATION · ORGANS",title:organs.state||UNAVAILABLE,desc:organs.state==="DISABLED"?"Dynamic organ registration is disabled in this process.":"Boot-time organ registration state, without fabricated reachability.",metrics:(organs.organs&&organs.organs.length)?organs.organs.map(function(organ){return [organ.organ,num(organ.tools_registered)]}):[["organs",num(organs.organs&&organs.organs.length)]],label:organs.state||UNAVAILABLE,foot:organs.detail?esc(organs.detail):""})
    ]);

    var toolItems=tools.items||[];txt("tools-count",tools.state==="MEASURED"?"· "+toolItems.length+" measured":"· "+UNAVAILABLE);fill("tool-cards",toolItems.map(function(tool){return card({eyebrow:"TOOL · "+String(tool.family||"").toUpperCase()+(tool.is_async?" · ASYNC":""),title:tool.name,desc:tool.description||"",metrics:[["params",num(tool.parameters_total)],["required",num(tool.parameters_required)]],label:"MEASURED"})}));
    fill("resource-cards",(resources.items||[]).map(function(resource){return card({eyebrow:"RESOURCE",title:resource.uri,desc:resource.description||"",label:resources.state||UNAVAILABLE})}));
  }

  getJSON("/api/console-state",6000).then(render).catch(renderUnavailable);

  function pemToDer(pem){var b64=pem.replace(/-----[^-]+-----/g,"").replace(/\s+/g,"");var binary=atob(b64),bytes=new Uint8Array(binary.length);for(var i=0;i<binary.length;i+=1)bytes[i]=binary.charCodeAt(i);return bytes.buffer}
  function hex(buffer){return Array.prototype.map.call(new Uint8Array(buffer),function(value){return value.toString(16).padStart(2,"0")}).join("")}
  function setFingerprint(value){var node=$("key-fp");if(node)node.textContent=value}
  setTimeout(function(){getText("/pubkey",5000).then(function(pem){if(pem.indexOf("PUBLIC KEY")===-1){setFingerprint("no key in process · UNSIGNED");return}if(window.crypto&&crypto.subtle)return crypto.subtle.digest("SHA-256",pemToDer(pem)).then(function(digest){setFingerprint("SHA256(SPKI) "+hex(digest).slice(0,24)+"…")});setFingerprint("key served · fingerprint UNAVAILABLE in this browser")}).catch(function(){setFingerprint("fingerprint UNAVAILABLE")})},250);
})();
</script>

<script>
/* owned-cortex-proposal-client */
(function(){
  "use strict";
  var TOOL="szl_owned_cortex_infer",SCHEMA="szl.hatun.owned-cortex-proposal/v1";
  var PROTOCOL="2025-06-18",MAX_BYTES=1048576,WAIT_MS=60000;
  var generation=0,active=null;
  function $(id){return document.getElementById(id)}
  var form=$("proposal-form"),fields=$("proposal-fields"),prompt=$("proposal-prompt"),key=$("proposal-key");
  var submit=$("proposal-submit"),cancel=$("proposal-cancel"),clear=$("proposal-clear");
  var status=$("proposal-status"),output=$("proposal-output"),evidence=$("proposal-evidence"),details=$("proposal-details"),raw=$("proposal-raw");
  function fault(code){var error=new Error(code);error.code=code;return error}
  function object(value){return value!==null&&typeof value==="object"&&!Array.isArray(value)}
  function normalizePrompt(value){return value.replace(/^[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+|[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+$/g,"")}
  function digest(value){return typeof value==="string"&&/^[0-9a-f]{64}$/.test(value)}
  function revision(value){return typeof value==="string"&&/^[0-9a-f]{40}$/.test(value)}
  function short(value){return typeof value==="string"&&value.length<=180?value:"UNAVAILABLE"}
  function wipe(){
    output.textContent="No proposal to display.";evidence.textContent="";evidence.hidden=true;
    raw.textContent="";details.hidden=true;details.open=false;
  }
  function busy(on){
    fields.disabled=on||!usable;submit.disabled=on||!usable;cancel.disabled=!on;
    form.setAttribute("aria-busy",on?"true":"false");
  }
  function row(label,value){
    var term=document.createElement("dt"),description=document.createElement("dd");
    term.textContent=label;description.textContent=String(value);evidence.appendChild(term);evidence.appendChild(description);
  }
  async function hash(text){
    if(!window.crypto||!window.crypto.subtle)throw fault("CLIENT_VERIFICATION_UNAVAILABLE");
    var bytes=await window.crypto.subtle.digest("SHA-256",new TextEncoder().encode(text));
    return Array.from(new Uint8Array(bytes),function(n){return n.toString(16).padStart(2,"0")}).join("");
  }
  async function boundedJSON(response){
    var length=response.headers.get("content-length");
    if(length!==null&&(!/^[0-9]+$/.test(length)||Number(length)>MAX_BYTES))throw fault("RESPONSE_TOO_LARGE");
    if(!/^application\/json(?:\s*;|$)/i.test(response.headers.get("content-type")||""))throw fault("INVALID_RESPONSE");
    if(!response.body||typeof response.body.getReader!=="function")throw fault("INVALID_RESPONSE");
    var reader=response.body.getReader(),decoder=new TextDecoder("utf-8",{fatal:true}),parts=[],size=0;
    try{
      for(;;){
        var chunk=await reader.read();if(chunk.done)break;
        size+=chunk.value.byteLength;if(size>MAX_BYTES)throw fault("RESPONSE_TOO_LARGE");
        parts.push(decoder.decode(chunk.value,{stream:true}));
      }
      parts.push(decoder.decode());
      var body=JSON.parse(parts.join(""));if(!object(body))throw fault("INVALID_RESPONSE");return body;
    }catch(error){try{await reader.cancel()}catch(ignore){}throw error.code==="RESPONSE_TOO_LARGE"?error:fault("INVALID_RESPONSE")}
    finally{reader.releaseLock()}
  }
  async function rpc(message,credential,signal,protocol){
    var headers={"Accept":"application/json, text/event-stream","Content-Type":"application/json","Authorization":"Bearer "+credential};
    if(protocol)headers["MCP-Protocol-Version"]=protocol;
    var response;
    try{response=await fetch("/mcp/",{method:"POST",headers:headers,body:JSON.stringify(message),cache:"no-store",credentials:"omit",redirect:"error",signal:signal})}
    catch(error){throw signal.aborted?fault("WAIT_ENDED"):fault("TRANSPORT_UNAVAILABLE")}
    if(!response.ok){
      if(response.body)try{await response.body.cancel()}catch(ignore){}
      throw fault(response.status===401?"OPERATOR_NOT_ADMITTED":response.status===403?"CAPABILITY_NOT_ADMITTED":response.status===429?"RATE_LIMITED":"TRANSPORT_UNAVAILABLE");
    }
    if(message.id===undefined){
      if(response.body)try{await response.body.cancel()}catch(ignore){}
      if(response.status!==202&&response.status!==204)throw fault("INVALID_RESPONSE");return null;
    }
    var body=await boundedJSON(response);
    if(body.jsonrpc!=="2.0"||body.id!==message.id||Object.prototype.hasOwnProperty.call(body,"error")||!object(body.result))throw fault("INVALID_RESPONSE");
    return body.result;
  }
  function envelope(result){
    if(result.isError===true)throw fault("TOOL_CALL_FAILED");
    var data=result.structuredContent;
    if(!object(data)){
      if(!Array.isArray(result.content)||result.content.length!==1||result.content[0].type!=="text"||typeof result.content[0].text!=="string")throw fault("INVALID_RESPONSE");
      try{data=JSON.parse(result.content[0].text)}catch(ignore){throw fault("INVALID_RESPONSE")}
    }
    if(!object(data)||data.tool!==TOOL||typeof data.status!=="string")throw fault("INVALID_RESPONSE");
    return data;
  }
  async function inspect(reply,question){
    var data=reply.data;
    if(!object(data)||data.schema!==SCHEMA||!["PROPOSAL","UNAVAILABLE","REJECTED"].includes(data.state))throw fault("PROPOSAL_UNAVAILABLE");
    if(data.state!=="PROPOSAL"||reply.status!=="success"){
      var codes=Array.isArray(data.reason_codes)?data.reason_codes.filter(function(c){return typeof c==="string"&&/^[A-Z][A-Z0-9_]{0,79}$/.test(c)}).slice(0,8):[];
      return {ready:false,state:data.state,reasons:codes};
    }
    var upstream=data.upstream,verification=data.verification;
    if(!object(upstream)||!object(verification)||verification.scope!=="STRUCTURAL_CONSISTENCY_ONLY"||verification.signature_verification!=="NOT_PERFORMED"||verification.freshness!=="REQUEST_PREFLIGHT_BOUND")throw fault("INVALID_RESPONSE");
    var receipt=upstream.receipt,payload=receipt&&receipt.payload;
    if(!object(receipt)||!object(payload)||!object(receipt.signature)||receipt.signature.status!=="UNSIGNED_RUNTIME"||receipt.signature.durable!==false)throw fault("INVALID_RESPONSE");
    if(upstream.state!=="PROPOSAL"||upstream.authority_state!=="NO_ACTION_AUTHORITY"||upstream.executed!==false||upstream.tool_execution!==false||payload.authority_state!=="NO_ACTION_AUTHORITY"||payload.executed!==false||payload.tool_execution!==false)throw fault("AUTHORITY_MISMATCH");
    if(!revision(data.source_revision)||data.source_revision!==upstream.source_revision||data.source_revision!==payload.source_revision||typeof upstream.request_id!=="string"||!/^[0-9a-f]{32}$/.test(upstream.request_id)||upstream.request_id!==payload.request_id)throw fault("BINDING_MISMATCH");
    if(typeof upstream.output!=="string"||!upstream.output.trim()||upstream.output.length>32768||!digest(upstream.output_sha256)||!digest(receipt.receipt_sha256)||!digest(payload.prompt_sha256)||upstream.output_sha256!==payload.output_sha256)throw fault("BINDING_MISMATCH");
    var hashes=await Promise.all([hash(question),hash(upstream.output)]);
    if(hashes[0]!==payload.prompt_sha256||hashes[1]!==upstream.output_sha256)throw fault("BINDING_MISMATCH");
    if(!object(upstream.model)||!Array.isArray(upstream.evidence_handles)||upstream.evidence_handles.length>4||!object(upstream.formula_authority)||upstream.formula_authority.locked_proven_count!==8)throw fault("INVALID_RESPONSE");
    var observed=Date.parse(data.observed_at);
    if(!Number.isFinite(observed))throw fault("INVALID_RESPONSE");
    return {ready:true,data:data,upstream:upstream,receipt:receipt,observed:observed};
  }
  function show(reply,view){
    wipe();
    if(!view.ready){status.textContent=view.state+" — no proposal delivered."+(view.reasons.length?" "+view.reasons.join(", "):"");return}
    var data=view.data,upstream=view.upstream,receipt=view.receipt;
    output.textContent=upstream.output;
    row("Observed",new Date(view.observed).toISOString()+" · this request only");
    row("Source",data.source_revision);row("Request",upstream.request_id);
    row("Model",short(upstream.model.repository));row("Model revision",short(upstream.model.revision));
    row("Evidence",upstream.evidence_handles.length+" returned handles");
    row("Doctrine","8 locked source formulas · proof replay not performed here");
    row("Authority","NO_ACTION_AUTHORITY · executed false");
    row("Output SHA-256",upstream.output_sha256);row("Cortex receipt",receipt.receipt_sha256);
    row("Cortex signature","UNSIGNED_RUNTIME · ephemeral process memory");
    var khipu=reply.khipu_receipt;row("Hatun receipt",object(khipu)&&digest(khipu.continuum_hash)?khipu.continuum_hash:"UNAVAILABLE");
    var signatures=reply.dsse&&reply.dsse.signatures;
    var present=Array.isArray(signatures)&&signatures.some(function(s){return object(s)&&typeof s.sig==="string"&&s.sig.length>0});
    row("Hatun signature",present?"SIGNATURE PRESENT · not verified here":"UNSIGNED / PLACEHOLDER");
    var trace=upstream.trace_observation;
    row("Trace observation",object(trace)?short(trace.state||trace.status||trace.delivery)+" · reported, not independently witnessed":"NOT RETURNED");
    var anatomy=upstream.anatomy_observation;
    row("Anatomy observation",object(anatomy)?short(anatomy.delivery)+" · "+short(anatomy.persistence):"NOT RETURNED");
    row("Validation","Prompt and output digests checked in this browser. Upstream structural checks reported by Hatun; signatures not verified.");
    evidence.hidden=false;raw.textContent=JSON.stringify(reply,null,2);details.hidden=false;
    status.textContent="PROPOSAL — inspect the answer and its evidence. No action executed.";
  }
  function endWaiting(message){
    generation+=1;if(active)active.abort();active=null;key.value="";wipe();busy(false);status.textContent=message;
  }
  var usable=window.isSecureContext&&window.top===window.self;
  busy(false);if(!usable)status.textContent="Open this gateway directly in a secure window to request a proposal.";
  form.addEventListener("submit",async function(event){
    event.preventDefault();if(active||!usable)return;
    wipe();
    var originalLength=Array.from(prompt.value).length,question=normalizePrompt(prompt.value),credential=key.value;
    prompt.value=question;
    if(!question||originalLength>4000||!/^szl_[A-Za-z0-9_-]{1,252}$/.test(credential)){key.value="";status.textContent="Enter a question and a valid admitted operator key.";return}
    key.value="";busy(true);status.textContent="Requesting a governed proposal…";
    var mine=++generation,controller=new AbortController();active=controller;
    var timer=setTimeout(function(){controller.abort()},WAIT_MS);
    try{
      var initialized=await rpc({jsonrpc:"2.0",id:"init-"+mine,method:"initialize",params:{protocolVersion:PROTOCOL,capabilities:{},clientInfo:{name:"hatun-proposal-console",version:"1.0.0"}}},credential,controller.signal,null);
      if(initialized.protocolVersion!==PROTOCOL||!object(initialized.serverInfo)||initialized.serverInfo.name!=="hatun-mcp")throw fault("PROTOCOL_MISMATCH");
      await rpc({jsonrpc:"2.0",method:"notifications/initialized"},credential,controller.signal,PROTOCOL);
      var result=await rpc({jsonrpc:"2.0",id:"proposal-"+mine,method:"tools/call",params:{name:TOOL,arguments:{prompt:question,max_new_tokens:64,k:3}}},credential,controller.signal,PROTOCOL);
      credential="";
      var reply=envelope(result),view=await inspect(reply,question);
      if(mine!==generation)return;
      if(controller.signal.aborted)throw fault("WAIT_ENDED");
      show(reply,view);
    }catch(error){
      if(mine!==generation)return;
      wipe();
      var messages={
        OPERATOR_NOT_ADMITTED:"Operator key not admitted. No proposal displayed.",
        CAPABILITY_NOT_ADMITTED:"This operator is not admitted to the proposal capability.",
        RATE_LIMITED:"The gateway rate-limited this request. Nothing was retried.",
        PROTOCOL_MISMATCH:"The gateway protocol does not match this client.",
        BINDING_MISMATCH:"The response did not match this question, source, or output digest.",
        AUTHORITY_MISMATCH:"The response violated the proposal-only authority contract.",
        RESPONSE_TOO_LARGE:"The gateway response exceeded the client byte limit.",
        CLIENT_VERIFICATION_UNAVAILABLE:"This browser could not verify the prompt and output digests.",
        PROPOSAL_UNAVAILABLE:"No validated governed proposal was returned.",
        TOOL_CALL_FAILED:"The governed tool could not complete the request.",
        WAIT_ENDED:"Stopped waiting. The upstream request may still finish; no retry was sent.",
        INVALID_RESPONSE:"The gateway returned an invalid response.",
        TRANSPORT_UNAVAILABLE:"The gateway request could not be completed. Nothing was retried."
      };
      var code=controller.signal.aborted?"WAIT_ENDED":error.code;
      status.textContent=messages[code]||"The proposal could not be validated.";
    }finally{
      credential="";clearTimeout(timer);
      if(mine===generation){active=null;busy(false)}
    }
  });
  cancel.addEventListener("click",function(){endWaiting("Stopped waiting. The upstream request may still finish; no retry was sent.")});
  clear.addEventListener("click",function(){var running=active!==null;endWaiting(running?"Cleared. The upstream request may still finish; no retry was sent.":"No proposal requested.");prompt.value=""});
  prompt.addEventListener("input",function(){if(!active){wipe();status.textContent="Question changed. Request a new proposal to bind evidence to this text."}});
  key.addEventListener("input",function(){if(!active){wipe();status.textContent="Credential changed. No proposal requested with this credential."}});
  window.addEventListener("pagehide",function(){endWaiting("No proposal requested.");prompt.value=""});
  window.addEventListener("pageshow",function(event){if(event.persisted){endWaiting("No proposal requested.");prompt.value=""}});
})();
</script>

</body>
</html>""".replace("__HATUN_PUBLIC_BASE__", escape(PUBLIC_BASE, quote=True))
