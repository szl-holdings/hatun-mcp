// Hermetic browser-client contract. Provider data is SIMULATED.
// SPDX-License-Identifier: Apache-2.0
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";
import {createHash, webcrypto} from "node:crypto";

const source=readFileSync(new URL("../hatun_mcp/console_v2.py",import.meta.url),"utf8");
const script=source.match(/<script>\s*\/\* owned-cortex-proposal-client \*\/([\s\S]*?)<\/script>/)?.[1];
assert.ok(script,"The production console must ship the tested client");
const hash=s=>createHash("sha256").update(s,"utf8").digest("hex");
const TOOL="szl_owned_cortex_infer", KEY="szl_SIMULATED_UI_TEST", QUESTION="Explain the evidence boundary.";
const REV="a".repeat(40), REQUEST="b".repeat(32);

class Element {
  constructor(id){this.id=id;this.value="";this.children=[];this.listeners={};this.attrs={};this.disabled=false;this.hidden=false;this.open=false;this._text="";}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join(" ");}
  set innerHTML(value){throw Error("Untrusted client content must not use innerHTML");}
  appendChild(child){this.children.push(child);}
  setAttribute(name,value){this.attrs[name]=value;}
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
  async fire(name,event={}){for(const fn of this.listeners[name]??[])await fn({preventDefault(){},...event});}
}
function fixture(question=QUESTION){
  const text="A model proposal is text, not execution authority.";
  const payload={source_revision:REV,request_id:REQUEST,prompt_sha256:hash(question),output_sha256:hash(text),authority_state:"NO_ACTION_AUTHORITY",executed:false,tool_execution:false};
  return {
    tool:TOOL,status:"success",
    data:{schema:"szl.hatun.owned-cortex-proposal/v1",state:"PROPOSAL",observed_at:"2026-11-16T23:50:00Z",source_revision:REV,
      verification:{scope:"STRUCTURAL_CONSISTENCY_ONLY",signature_verification:"NOT_PERFORMED",freshness:"REQUEST_PREFLIGHT_BOUND"},
      upstream:{state:"PROPOSAL",source_revision:REV,request_id:REQUEST,output:text,output_sha256:hash(text),
        authority_state:"NO_ACTION_AUTHORITY",executed:false,tool_execution:false,
        model:{repository:"SIMULATED/model",revision:"c".repeat(40)},evidence_handles:[],
        formula_authority:{locked_proven_count:8},
        receipt:{payload,receipt_sha256:"d".repeat(64),signature:{status:"UNSIGNED_RUNTIME",durable:false}},
        anatomy_observation:{delivery:"DELIVERED",persistence:"EPHEMERAL_PROCESS_MEMORY_ONLY"}}},
    khipu_receipt:{continuum_hash:"e".repeat(64)},dsse:{signatures:[]},
  };
}
function json(body,status=200,headers={}){return new Response(JSON.stringify(body),{status,headers:{"content-type":"application/json",...headers}});}
function harness({reply=fixture(),secure=true,framed=false,responder,crypto=webcrypto,textOnly=false}={}){
  const nodes=new Map();
  const el=id=>{if(!nodes.has(id))nodes.set(id,new Element(id));return nodes.get(id);};
  const calls=[],timers=new Map(),listeners={};let next=0;
  const window={isSecureContext:secure,crypto,addEventListener(name,fn){(listeners[name]??=[]).push(fn);}};
  window.self=window;window.top=framed?{}:window;
  const context={window,document:{getElementById:el,createElement:tag=>new Element(tag)},AbortController,TextEncoder,TextDecoder,Uint8Array,Date,Promise,
    setTimeout(fn){timers.set(++next,fn);return next;},clearTimeout(id){timers.delete(id);},
    fetch:async(url,options)=>{
      const message=JSON.parse(options.body);calls.push({url,options,message});
      assert.equal(el("proposal-key").value,"","Credential field must clear before any network call");
      if(responder){const response=await responder(message,options,calls);if(response!==undefined)return response;}
      if(message.method==="initialize")return json({jsonrpc:"2.0",id:message.id,result:{protocolVersion:"2025-06-18",serverInfo:{name:"hatun-mcp"}}});
      if(message.method==="notifications/initialized")return new Response(null,{status:202});
      return json({jsonrpc:"2.0",id:message.id,result:textOnly?{content:[{type:"text",text:JSON.stringify(reply)}]}:{structuredContent:reply}});
    }};
  for(const name of ["localStorage","sessionStorage"]){
    Object.defineProperty(context,name,{get(){throw Error("Browser storage is forbidden");}});
    Object.defineProperty(window,name,{get(){throw Error("Browser storage is forbidden");}});
  }
  vm.runInNewContext(script,context,{filename:"owned-cortex-proposal-client.js"});
  async function send(question=QUESTION,key=KEY){el("proposal-prompt").value=question;el("proposal-key").value=key;await el("proposal-form").fire("submit");}
  async function event(name,args={}){for(const fn of listeners[name]??[])await fn(args);}
  return {el,calls,timers,send,event};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test("loading the client never generates a proposal or sends a credential",()=>{
  const h=harness();assert.equal(h.calls.length,0);assert.equal(h.el("proposal-submit").disabled,false);
});
test("one explicit submit performs the real stateless MCP sequence and preserves evidence",async()=>{
  const h=harness();await h.send();
  assert.deepEqual(h.calls.map(c=>c.message.method),["initialize","notifications/initialized","tools/call"]);
  for(const {url,options} of h.calls){
    assert.equal(url,"/mcp/");assert.equal(options.redirect,"error");assert.equal(options.credentials,"omit");
    assert.equal(options.headers.Authorization,"Bearer "+KEY);assert.equal(options.body.includes(KEY),false);
  }
  assert.deepEqual(h.calls[2].message.params,{name:TOOL,arguments:{prompt:QUESTION,max_new_tokens:64,k:3}});
  assert.match(h.el("proposal-status").textContent,/^PROPOSAL/);
  assert.equal(h.el("proposal-output").textContent,fixture().data.upstream.output);
  assert.match(h.el("proposal-evidence").textContent,/NO_ACTION_AUTHORITY/);
  assert.match(h.el("proposal-evidence").textContent,/UNSIGNED_RUNTIME/);
  assert.equal(h.el("proposal-key").value,"");assert.equal(h.el("proposal-details").hidden,false);
  assert.equal(h.timers.size,0);
});
test("text-only SDK result is accepted only as a single JSON text block",async()=>{
  const h=harness({textOnly:true});await h.send();assert.match(h.el("proposal-status").textContent,/^PROPOSAL/);
});
test("Unicode prompt and output are bound as UTF-8 bytes",async()=>{
  const question="Δ · evidence 🌱",reply=fixture(question);
  reply.data.upstream.output="<img src=x onerror=alert(1)> Δ — 🌱";
  reply.data.upstream.output_sha256=hash(reply.data.upstream.output);
  reply.data.upstream.receipt.payload.output_sha256=reply.data.upstream.output_sha256;
  const h=harness({reply});await h.send(question);
  assert.equal(h.el("proposal-output").textContent,reply.data.upstream.output);
  assert.match(h.el("proposal-status").textContent,/^PROPOSAL/);
});
for(const [label,mutate] of [
  ["source revision",r=>r.data.source_revision="f".repeat(40)],
  ["receipt source",r=>r.data.upstream.receipt.payload.source_revision="f".repeat(40)],
  ["request identity",r=>r.data.upstream.receipt.payload.request_id="f".repeat(32)],
  ["prompt digest",r=>r.data.upstream.receipt.payload.prompt_sha256="f".repeat(64)],
  ["output digest",r=>r.data.upstream.output+=" changed"],
  ["receipt output digest",r=>r.data.upstream.receipt.payload.output_sha256="f".repeat(64)],
  ["execution truth",r=>r.data.upstream.executed=true],
  ["string false",r=>r.data.upstream.tool_execution="false"],
  ["receipt authority",r=>r.data.upstream.receipt.payload.authority_state="EXECUTE"],
  ["signed Cortex claim",r=>r.data.upstream.receipt.signature.status="SIGNED"],
  ["durable Cortex claim",r=>r.data.upstream.receipt.signature.durable=true],
  ["inflated locked count",r=>r.data.upstream.formula_authority.locked_proven_count=9],
  ["signature verification upgrade",r=>r.data.verification.signature_verification="VERIFIED"],
  ["freshness upgrade",r=>r.data.verification.freshness="LIVE"],
  ["missing source",r=>delete r.data.source_revision],
  ["empty output",r=>r.data.upstream.output=""],
  ["oversized output",r=>r.data.upstream.output="x".repeat(32769)],
  ["invalid observation time",r=>r.data.observed_at="yesterday"],
]){
  test("rejects mismatched "+label+" without retaining a prior answer",async()=>{
    const reply=fixture();mutate(reply);const h=harness({reply});
    h.el("proposal-output").textContent="stale answer";await h.send();
    assert.doesNotMatch(h.el("proposal-status").textContent,/^PROPOSAL —/);
    assert.equal(h.el("proposal-output").textContent,"No proposal to display.");
    assert.equal(h.el("proposal-details").hidden,true);assert.equal(h.calls.length,3);
  });
}
for(const state of ["UNAVAILABLE","REJECTED"]){
  test("preserves "+state+" without exposing unvalidated output or error body",async()=>{
    const reply=fixture();reply.status="error";reply.data.state=state;
    reply.data.reason_codes=["MODEL_UNAVAILABLE","<img src=x>"];
    reply.data.upstream.output="unvalidated private output";
    const h=harness({reply});await h.send();
    assert.match(h.el("proposal-status").textContent,new RegExp("^"+state));
    assert.match(h.el("proposal-status").textContent,/MODEL_UNAVAILABLE/);
    assert.doesNotMatch(h.el("proposal-status").textContent,/<img|private/);
    assert.equal(h.el("proposal-output").textContent,"No proposal to display.");
  });
}
for(const status of [401,403,429,500]){
  test("HTTP "+status+" stops before tool dispatch and never retries",async()=>{
    const h=harness({responder:()=>new Response("DO_NOT_RENDER_PRIVATE_SERVER_BODY",{status})});await h.send();
    assert.equal(h.calls.length,1);assert.doesNotMatch(h.el("proposal-status").textContent,/DO_NOT_RENDER/);
    assert.equal(h.el("proposal-key").value,"");
  });
}
test("network and redirect failures do not echo exception details",async()=>{
  const h=harness({responder:()=>{throw Error("SECRET_CANARY_TOKEN")}});await h.send();
  assert.equal(h.calls.length,1);assert.doesNotMatch(h.el("proposal-status").textContent,/SECRET_CANARY/);
});
for(const [name,responder] of [
  ["protocol drift",m=>m.method==="initialize"?json({jsonrpc:"2.0",id:m.id,result:{protocolVersion:"9999-01-01",serverInfo:{name:"hatun-mcp"}}}):undefined],
  ["wrong server",m=>m.method==="initialize"?json({jsonrpc:"2.0",id:m.id,result:{protocolVersion:"2025-06-18",serverInfo:{name:"another-gateway"}}}):undefined],
  ["wrong RPC identity",m=>json({jsonrpc:"2.0",id:"wrong",result:{}})],
  ["HTML",()=>new Response("<html>not an API</html>",{headers:{"content-type":"text/html"}})],
  ["SSE",()=>new Response("data: {}",{headers:{"content-type":"text/event-stream"}})],
  ["declared oversize",()=>json({},200,{"content-length":"1048577"})],
  ["actual oversize",()=>json({padding:"x".repeat(1048577)})],
]){
  test("rejects "+name+" before calling a tool",async()=>{
    const h=harness({responder});await h.send();assert.equal(h.calls.length,1);
    assert.equal(h.el("proposal-output").textContent,"No proposal to display.");
  });
}
test("invalid UTF-8 is refused",async()=>{
  const h=harness({responder:()=>new Response(new Uint8Array([123,34,255,34,58,49,125]),{headers:{"content-type":"application/json"}})});
  await h.send();assert.equal(h.calls.length,1);assert.match(h.el("proposal-status").textContent,/invalid response/);
});
test("a user abort ignores a late valid answer and does not promise upstream cancellation",async()=>{
  let finish,started;const ready=new Promise(resolve=>started=resolve);
  const h=harness({responder:async m=>{if(m.method==="tools/call"){started();return await new Promise(resolve=>finish=()=>resolve(json({jsonrpc:"2.0",id:m.id,result:{structuredContent:fixture()}})));}}});
  const pending=h.send();await ready;await h.el("proposal-cancel").fire("click");finish();await pending;
  assert.match(h.el("proposal-status").textContent,/may still finish/);
  assert.equal(h.el("proposal-output").textContent,"No proposal to display.");assert.equal(h.calls.length,3);
  assert.equal(h.el("proposal-submit").disabled,false);
});
test("the total wait deadline aborts transport and never retries",async()=>{
  let started;const ready=new Promise(resolve=>started=resolve);
  const h=harness({responder:async(m,options)=>{if(m.method==="tools/call"){started();return await new Promise((resolve,reject)=>options.signal.addEventListener("abort",()=>reject(new Error("aborted"))));}}});
  const pending=h.send();await ready;for(const timer of [...h.timers.values()])timer();await pending;
  assert.match(h.el("proposal-status").textContent,/may still finish/);assert.equal(h.calls.length,3);
});
test("deadline during digest verification cannot leave the client waiting forever",async()=>{
  let finishHash;const digestGate=new Promise(resolve=>finishHash=resolve);
  const slowCrypto={subtle:{digest:async(...args)=>{await digestGate;return webcrypto.subtle.digest(...args)}}};
  const h=harness({crypto:slowCrypto});const pending=h.send();
  for(let i=0;i<10&&h.calls.length<3;i++)await tick();
  await tick();for(const timer of [...h.timers.values()])timer();finishHash();await pending;
  assert.match(h.el("proposal-status").textContent,/may still finish/);assert.equal(h.el("proposal-submit").disabled,false);
});
for(const id of ["proposal-prompt","proposal-key"]){
  test("changing "+id+" invalidates displayed evidence",async()=>{
    const h=harness();await h.send();await h.el(id).fire("input");
    assert.equal(h.el("proposal-output").textContent,"No proposal to display.");
    assert.equal(h.el("proposal-details").hidden,true);assert.equal(h.calls.length,3);
  });
}
test("clear and navigation discard local question, credential, and results",async()=>{
  const h=harness();await h.send();await h.el("proposal-clear").fire("click");
  assert.equal(h.el("proposal-prompt").value,"");assert.equal(h.el("proposal-key").value,"");
  await h.send();await h.event("pagehide");assert.equal(h.el("proposal-prompt").value,"");
  h.el("proposal-key").value=KEY;await h.event("pageshow",{persisted:true});
  assert.equal(h.el("proposal-key").value,"");assert.equal(h.el("proposal-output").textContent,"No proposal to display.");
});
for(const options of [{secure:false},{framed:true}]){
  test("insecure or embedded contexts cannot send credentials "+JSON.stringify(options),async()=>{
    const h=harness(options);await h.send();assert.equal(h.calls.length,0);assert.equal(h.el("proposal-submit").disabled,true);
  });
}
test("signature presence and trace delivery never become verification claims",async()=>{
  const reply=fixture();reply.dsse.signatures=[{sig:"SIMULATED-NOT-A-REAL-SIGNATURE"}];
  reply.data.upstream.trace_observation={state:"OBSERVED"};
  const h=harness({reply});await h.send();
  assert.match(h.el("proposal-evidence").textContent,/SIGNATURE PRESENT · not verified here/);
  assert.match(h.el("proposal-evidence").textContent,/OBSERVED · reported, not independently witnessed/);
  assert.match(h.el("proposal-evidence").textContent,/EPHEMERAL_PROCESS_MEMORY_ONLY/);
});

test("Python-style prompt normalization binds exactly the question shown and sent",async()=>{
  const h=harness();await h.send(" \t\n"+QUESTION+"\u0085\u001c\u3000");
  assert.equal(h.calls[2].message.params.arguments.prompt,QUESTION);
  assert.equal(h.el("proposal-prompt").value,QUESTION);assert.match(h.el("proposal-status").textContent,/^PROPOSAL/);
});
test("a non-whitespace BOM is preserved consistently with upstream Python normalization",async()=>{
  const question="\ufeff"+QUESTION+"\ufeff",h=harness({reply:fixture(question)});await h.send(question);
  assert.equal(h.calls[2].message.params.arguments.prompt,question);assert.match(h.el("proposal-status").textContent,/^PROPOSAL/);
});

test("original input length is checked before whitespace normalization",async()=>{
  const h=harness();await h.send(" ".repeat(4000)+QUESTION);
  assert.equal(h.calls.length,0);assert.equal(h.el("proposal-key").value,"");
});
