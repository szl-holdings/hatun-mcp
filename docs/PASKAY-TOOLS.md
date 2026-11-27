# Hatun-MCP PASKAY Tool Spec v0.1 (propose-only draft)

**Proposed extension to the hatun-mcp governed tool catalog.** This document is a
specification card only: adding a tool to this repo is not itself proof it is
deployed at the gateway (surface contract). Merge is owner-gated; the platform
monorepo embedded copy (`platform/packages/hatun-mcp`) must not diverge from
these contracts if adopted.

Doctrine v11 · Λ = Conjecture 1 (advisory) · Conjecture 3 (shared key space) open ·
Apache-2.0 · `receipts.in ≡ receipts.out`

## Background

Plato's Key (Hazy Research, Stanford, 2026-11-25 — https://hazyresearch.stanford.edu/blog/2026-11-25-platos-key)
demonstrates closed-form rotation+scale transfer of factual representations across
LLMs, and donor-key recovery of dark memories (facts stored but not recalled).
PASKAY is the estate's governed extension: rotation artifacts and knowledge
attestations become receipted, verifiable, witnessed objects. Hatun is the
exposure surface: any MCP client can then verify a rotation or request a
witnessed knowledge attestation under the same PURIQ / Yuyay-13 governance as
every other tool.

## Tool 1: `paskay_verify_rotation_receipt`

Offline, dependency-free verification of a PASKAY rotation receipt artifact.

- **Input:** rotation receipt (DSSE-signed, or UNSIGNED_HONEST chain), plus the claimed donor/recipient digests.
- **Checks:** chain integrity and order; donor/recipient/adapter sha256 presence and match; fit-fact COUNT present (never contents); layer pair (lA, lB) present and within depth bounds; scale s present and positive; test transfer accuracy present WITH n and population; control accuracies present (random rotation, shuffled keys, scale-only) and each ≤ 0.05; acceptance criteria stated and falsifiable; no "proven" language.
- **Verdicts:** `VERIFIED` · `FAILED (reason named)` · `INCOMPARABLE (fields missing — fail-closed, never guessed)`.
- **Receipt out:** the verification itself is receipted (hash-chained), per `receipts.in ≡ receipts.out`.

## Tool 2: `paskay_attest_knowledge`

Witnessed knowledge attestation over a frozen model's memory.

- **Input:** a dark-memory probe result set across k named donors (k ≥ 4), each donor carrying a VERIFIED rotation receipt; the fact's identifier (ID only, no content); the recipient abstention record.
- **Governance:** BFT 3-of-4 witness pattern (khipu-consensus class): at least 3 of 4 donor keys must unlock the same stored value for a DARK_MEMORY verdict. Witnesses sign the action hash with their own keys over DSSE.
- **Verdicts (closed vocabulary, fixed before the run):**
  - `TRUE_ABSENCE_MEASURED` — pre-checks and donor keys agree: not stored.
  - `DARK_MEMORY_ATTESTED (witnesses=n, donors named)` — stored, retrieval ineffective, consensus-signed.
  - `INSUFFICIENT_WITNESSES` — fewer than 3 donors agree; fail-closed, no guess.
  - `INCOMPARABLE` — any witness's rotation receipt unverifiable.
- **Non-claims (on the face of every attestation):** attests presence-in-weights under the stated probe, not truth of the fact; not biological or commercial validation; Λ advisory; Conjecture 3 open.

## Gate wiring

Both tools enter through the standard catalog governance: PURIQ formula,
Yuyay-13 gate, DSSE signing when an operator key is armed (else explicit
PLACEHOLDER mode, `/readyz` not_ready), anonymous calls declined. No new
auth surface. No hf-deploy (retired 2026-09-03; must not be recreated).
Deployment is a separate owner-gated step.

## Dependency posture

Pure stdlib verification path; no model weights are loaded by these tools; no
network calls required for verification. The probing harness lives in the
training lane (PASKAY-P1/P2 job specs), not in hatun.

## Status

LEADER-STUDY CARD, propose-only, owner-gated. No implementation in this PR.
No deployment claim. No "proven" claims anywhere.
