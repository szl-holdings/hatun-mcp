# hatun-mcp: Reference Implementation of the Singapore Agentic AI Governance Framework

## Purpose

Singapore's Model Governance Framework for Generative AI (January 2026) is the only
governance document in the world that addresses autonomous agents directly. This
document maps hatun-mcp's governance architecture to that framework, positioning
the estate's MCP server as its reference implementation.

## Mapping: Singapore Framework → hatun-mcp Implementation

### 1. Accountability (who is responsible for agent actions)

| Singapore requirement | hatun-mcp implementation |
|---|---|
| Clear accountability chain for agent decisions | Every tool call emits a Khipu receipt with: client ID (authenticated), operation ID, timestamp, input digest, output digest, receipt chain position. The accountability chain IS the receipt chain. |
| Human oversight for consequential actions | State-changing operations require a **2-person gate**: the `hatun_mcp_factor` returns 0 unless `two_person=True`. Anonymous requests are declined by construction. |
| Audit trail | The Khipu chain is append-only, hash-linked (SHA-256), and independently verifiable. The `hatun://khipu/recent` resource exposes the last 20 receipts for audit. |

### 2. Transparency (can agents and humans understand what the system does)

| Singapore requirement | hatun-mcp implementation |
|---|---|
| Agent capabilities disclosed | The server card (`/.well-known/mcp/server-card.json`) discloses: all admitted tools, the governance profile (operator-read-only), the transport policy, the authentication scheme, and the proof status of every formula. |
| Limitations disclosed | The server card explicitly states: `portal_validation: NOT_IMPLEMENTED`, `write_authorization: UNAVAILABLE`, `approval_headers: NOT_TRUSTED`. What doesn't work is published, not hidden. |
| Pricing transparent | When x402 payment admission is on, the server card and `/connect` publish `http_transport_policy.payment_admission`: the scheme, atomic amount, audience and paid tools this origin verifies, and how it reports settlement. When admission is off, the field reads `DISABLED`. The edge rules themselves live in the Cloudflare dashboard. The separately hosted pricing manifest is not generated from this source and is not cited as a control. |

### 3. Safety (does the system prevent harm)

| Singapore requirement | hatun-mcp implementation |
|---|---|
| Input validation | The **Yuyay-13 gate**: 13 conjunctive axes, each with a floor. Any axis below its floor vetoes the call. Model output is treated as untrusted input (OWASP MCP06 defense). |
| Output governance | Every response is DSSE-signed with the receipt hash attached. A response without a verifiable receipt is not a governed response. |
| Fail-closed design | If the Yuyay gate fails → declined. If the Khipu chain is broken → the chain verification fails. If authentication is absent → declined. The system fails toward refusal, not toward action. |

### 4. Fairness / Data Governance

| Singapore requirement | hatun-mcp implementation |
|---|---|
| Training data provenance | Every model in the estate carries a wave receipt (training run, datasets used, exit code) published to `SZLHOLDINGS/wave-logs`. Models without receipts are not admitted to production. |
| Data rights | The HIRAG admission gate (`license_admissible` axis) refuses to admit content with inadmissible licenses into the generation context. |
| Bias monitoring | The fleet-eval receipts (published verbatim to `SZLHOLDINGS/model-eval-receipts`) include measured failure modes with the exact text — biases are published, not hidden. |

### 5. Agent-Specific Requirements (unique to Singapore's framework)

| Singapore requirement | hatun-mcp implementation |
|---|---|
| Agents must not exceed authorized scope | The PBKDF2-fingerprint scope binding (`HATUN_MCP_SCOPE_<fingerprint>`) restricts each client to their declared scope. Write operations require the two-person gate. The HTTP surface is operator-read-only by design. |
| Agents must be verifiable | Every tool call produces a receipt that can be verified offline using standard open tools (cosign-compatible ECDSA-P256). |
| Agent interactions must be logged | The Khipu chain IS the log: append-only, hash-linked, tamper-evident, independently verifiable. |
| Agents must fail safely | The hatun_mcp_factor is multiplicative: any zero (no auth, wrong scope, failed gate, broken chain) makes the entire score zero. The PURIQ master operator cannot select an action with any zero factor. |

## What hatun-mcp has that the framework doesn't require

- **Lean-verified governance formulas**: The Λ aggregator's axioms (A2, A4) are
  machine-checked in Lean. The Schur-concavity (Robin Hood lemma) is proved with
  0 sorries. The PAC-Bayes bound is a conditional theorem. No other governance
  system has formal verification behind its admission criteria.
- **Statistical certification**: The McAllester PAC-Bayes bound + Hoeffding
  inequality provide computed confidence bounds on model risk — published in
  the Formal AI Underwriting product.
- **Ancient mathematical grounding**: The Khipu receipt chain is named after the
  Andean knot-record system — the first tamper-evident record (5000 years old).
  The formula atlas carries Liu Hui, Madhava, Archimedes: the traditions that
  invented certified computation.
- **Governed validation**: The estate publicly runs its own Λ-spine gate on its
  own models and publishes the verdicts — including NO_GO on its own flagship.
  No other AI company does this.

## Status

This is a mapping document, not a certification. The Singapore framework is
guidance, not law. hatun-mcp is an implementation of the principles, not an
endorsement by any government body.
