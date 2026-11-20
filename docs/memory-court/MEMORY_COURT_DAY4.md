# Memory Court Day 4: Trust Root Binding (TOCTOU closure)

Status: IMPLEMENTED, MEASURED by contract tests (this PR).
Predecessors: day-3 gateway merged in #205; day-2 spec #204; day-1
docs/memory-court/MEMORY_COURT_DAY1.md.

## What day-4 closes

Day-3 left a flagged hole: auth/tenant/build/trust were sampled before
commit, and the receipt envelope carried no trust binding, so a trust-root
rotation (or a post-commit field edit) could not be detected at commit or
replay time. Day-4 binds the active trust root into every admission.

## Adversarial design review (before implementation)

Two independent reviewers were given the day-4 design and asked to attack
it (strict output format, verdict line required):

- GPT-6 (the owner's ChatGPT desktop app; Measured: model radio
  IsSelected=True, response marker observed).
  Transcript: runtime/transcripts/gpt6_trustroot_rev_transcript.md
- mistral-large-4:cloud (via kimi_chat.ps1 harness).
  Transcript: runtime/transcripts/mistral_trustroot_rev_transcript.md

Both verdicts: **FIX-FIRST**. Findings folded into the implementation:

| # | Severity (source) | Finding | Implementation |
|---|---|---|---|
| 1 | CRITICAL (both) | Signature must cover the full envelope incl. trust fields, or post-commit edits are undetectable | `signed_payload()` domain-separated over the FULL v1 envelope (minus signature); optional injected `signature_verifier` must pass before commit |
| 2 | CRITICAL (GPT-6) / HIGH (Mistral) | Precondition must pin the whole snapshot, not just the version | `append_with_precondition(expect_snapshot_digest)` with `snapshot_digest = sha256(version|build_digest|epoch|sorted signer_key_ids)` re-asserted INSIDE the commit lock |
| 3 | HIGH (GPT-6) | v0 empty-string defaults permit ambiguous security claims | v1 fields mandatory at build (ValueError); half-signed refused; v0 appends LOCKED at the writer; strict schema discrimination on load |
| 4 | HIGH (Mistral) | event_id must bind the trust root (cross-root alias) | v1 event_id = sha256(memory_id+request_digest+decision+snapshot_digest) |
| 5 | HIGH (GPT-6) | Append success is not durable proof | lock + flush + fsync per append; duplicate/idempotency refusal; LMDB precondition stays in its write txn (ROADMAP) |
| 6 | MEDIUM (both) | Version ABA / provider regression | monotonic epoch enforced by the provider; digest includes epoch; regression raises |
| 7 | LOW (Mistral) | Empty signer_key_ids must fail closed | `TrustSnapshot.validate()`; empty set is an invalid root (503) |
| 8 | replay policy (conflict) | GPT-6: conditional historical allow; Mistral: refuse | Fail-closed resolves to REFUSE; conditional allow requires an owner-adopted historical trust policy (ROADMAP) |

Contract vectors pinning each failure mode live in
tests/memory_court/test_trust_root_day4.py (rotation before/after sign,
ABA, epoch regression, forged key id, verifier failure, half-built v1,
v0 downgrade + replay refusal, cross-root refusal, precondition abort,
zero dependent writes on every denial).

## Locked invariants

1. ONE TrustSnapshot per invoke; provider failure or invalid root => 503,
   nothing signed.
2. A receipt only commits when its key_id is in the SNAPSHOT's signer set
   AND the live snapshot digest still equals the sampled one inside the
   commit boundary.
3. Replays return committed evidence only, never re-adjudicate, never
   re-sign; v0 receipts are read-only legacy and refuse to replay.
4. Nothing half-bound, half-signed, or half-committed is ever a success.

## ROADMAP (owner-gated)

- DSSE envelope + owner key material (signature verification against the
  snapshot-bound public key is the injected verifier in production).
- Build-attestation provider that exposes the BUILD DIGEST (today
  `build_admissible` is a boolean; `snapshot.build_digest` carries the
  binding).
- szl-khipu LMDB adapter (precondition inside the write transaction).
- Historical trust policy for conditional replay-of-rotated-root (owner
  decision), and JCS (RFC 8785) canonicalization.
