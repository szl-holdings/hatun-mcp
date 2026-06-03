# hatun-mcp

> **Note:** the canonical mirror of this service also lives at
> [`platform/services/hatun-mcp`](https://github.com/szl-holdings/platform/tree/main/services/hatun-mcp).
> This repository remains **live** and is the home of the PURIQ governance MCP tools below.

**HATUN-MCP** — "the great context protocol" (Quechua: *hatun* = great + MCP). The doctrine-aware
MCP server that extends SZL governance — the Yuyay-13 gate, HUKLLA tripwires, Khipu receipts, and the
PURIQ master formula — to the world's MCP clients (Claude Desktop, Cursor, Continue, Zed, Goose, Smithery).

---

## PURIQ — the named operational architecture

PURIQ is the v21 **PURIQ-OS Substrate**: a 12-organ runtime, 23 agentic formulas (5 proved in Lean 4),
the Yuyay-13 axis gate, the Khipu DAG, and DSSE-signed receipts — now wired as **one named, operational,
citable architecture** with a single entrypoint.

### The PURIQ master formula

For an action `a` over input `x`:

```
u(a) = Λ(x) · 1[Yuyay₁₃ passes] · exp(−β · |HUKLLA tripwires|) · 1[Khipu chain verifies] · Hatun_MCP(a)
```

with `Hatun_MCP(a) = 1[key valid ∧ scope ⊇ op] · r(client) · 1[2-person if state-changing]`, `β = 8.0`.
Every factor lies in `[0,1]`, so `u(a) ∈ [0,1]`. A single failed gate drives `u(a) → 0` (default-decline).
Implemented verbatim in [`hatun_mcp/governance.py`](hatun_mcp/governance.py) (`puriq_utility`).

> **Λ is Conjecture 1 — never a theorem.** The aggregator's uniqueness chain is not complete on
> `main` ([thesis v22 "Convergence"](https://doi.org/10.5281/zenodo.19944926)). Doctrine v11 LOCKED:
> 749 declarations / 14 unique axioms / 163 sorries @ kernel `c7c0ba17`. SLSA L1 + L2 attested (NOT L3).

### The single operational claim

```
PURIQ(input, organs, context) = (Λ ∈ [0,1], DSSE-signed Khipu receipt, traceparent chain)
```

- **Λ ∈ [0,1]** — bounded, monotone, default-decline acceptability score.
- **DSSE-signed Khipu receipt** — tamper-evident append-only sha256 chain + real ECDSA P-256 DSSE
  envelope over the PAE preimage. (Cosign signature is empty until `SZL_COSIGN_PRIVATE_PEM` is set;
  disclosed, never faked.)
- **traceparent chain** — W3C trace context threaded organ-to-organ; each hop emits its own receipt.

### Governance tools (first-class MCP tools)

Registered by [`hatun_mcp/tools/governance_tools.py`](hatun_mcp/tools/governance_tools.py) and composed
by the orchestrator [`hatun_mcp/puriq.py`](hatun_mcp/puriq.py):

| Tool | What it does |
|------|--------------|
| `yuyay_gate_check(input, axes_to_run=None)` | Run the 13-axis Yuyay gate; returns per-axis verdicts, Λ contribution, receipt |
| `khipu_append_and_verify(payload, parent_hash)` | Append one Khipu link; recompute-verify the chain; return DSSE envelope |
| `dsse_sign(payload, key_env_var="SZL_COSIGN_PRIVATE_PEM")` | Real ECDSA P-256 DSSE; `honesty: REAL` when keyed, else `UNSIGNED` |
| `mesh_quorum_status(organ_ids, present=None)` | Byzantine `n ≥ 3f+1` quorum; `threshold = 2f+1` |
| `governance_pacbayes_bound(emp_risk, kl, n, delta)` | Published PAC-Bayes (McAllester) bound (F7) |
| **`puriq_master_tool(input, context)`** | **THE named entrypoint** — Yuyay-13 → quorum → HUKLLA → Khipu → DSSE → master verdict |

### Yuyay-13 axes (real, from `governance.py`)

`moralGrounding`*, `measurabilityHonesty`*, `empiricalGrounding`, `logicalConsistency`,
`sourceTransparency`, `uncertaintyDisclosure`, `reversibility`, `scopeDiscipline`, `claimCalibration`,
`introspectionT03`, `introspectionT04`, `introspectionT09`, `introspectionT10`.
(*sacred floor 0.95; the rest structural floor 0.90.) Conjunctive AND; injection markers are treated as
**data, not commands** (OWASP MCP06/MCP03).

### Tests

- `tests/test_puriq_real.py` — feeds real input through `puriq_master`, asserts `Λ ∈ [0,1]` and the
  receipt chain verifies.
- `tests/test_no_mock.py` — meta-test that the implementation contains no `mock`/`fake`/`stub` outside
  `/tests/` (HONESTY OVER CHECKLIST).

---

*Doctrine v11 LOCKED — 749/14/163 @ `c7c0ba17` · Λ = Conjecture 1 (never a theorem) · SLSA L1 + L2 (never L3) · per-file Dockerfile COPY · Section 889 = {Huawei, ZTE, Hytera, Hikvision, Dahua}.*

*Signed-off-by: Yachay <yachay@szlholdings.ai>*
*Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>*
