# Receiver-Side Co-Signing for hatun-mcp — Technical Proposal

## Problem this solves

Current `szl-receipt` records are signed exclusively by the originating
runtime. This means the same party whose decision is being recorded is the
only party attesting to it — a compromised or dishonest runtime can produce
a receipt that is internally consistent and tamper-evident from that point
forward, but was false at the moment of signing. This is the same limitation
shared with IETF draft-chueayen-attestation-receipts. Sello (arXiv:2606.04193)
addresses this by having the *receiving service* sign instead of the caller.

Full receiver-signing requires infrastructure SZL does not have today (HPKE
encryption-to-owner, witness-cosigned transparency log). This proposal
captures the core benefit — a receipt harder to forge because more than one
party had to agree to it — using only what `hatun-mcp` already has: a policy
gate sitting between the agent and the tool call.

## Design

### Current flow
```
Agent -> [runtime signs receipt] -> szl-receipt store
```
One party. One signature. Trust boundary = trust the runtime.

### Proposed flow
```
Agent -> hatun-mcp policy gate -> tool/service
              |                        |
              v                        v
     [gate co-signs receipt]  [service attests execution]
              |
              v
      dual-signed receipt -> szl-receipt store
```

### Receipt schema addition

Extend the existing DSSE envelope with a second signature slot:

```json
{
  "payload": { "...existing receipt fields...": "unchanged" },
  "payloadType": "application/vnd.szl.receipt+json",
  "signatures": [
    {
      "keyid": "runtime-key-2026",
      "sig": "<base64 ECDSA-P256 signature from originating runtime>"
    },
    {
      "keyid": "hatun-mcp-gate-key-2026",
      "sig": "<base64 ECDSA-P256 signature from policy gate, independent key>"
    }
  ]
}
```

### Verification rule change

`governed-receipt-spec`'s verifier is updated from:
> "Valid if signature[0] verifies against runtime public key."

to:
> "Valid if signature[0] verifies against runtime public key AND
> signature[1] verifies against gate public key AND both signatures cover
> the identical payload hash."

A receipt with only one valid signature is downgraded from `VERIFIED` to
`PARTIALLY_ATTESTED` in the status vocabulary — it still proves the runtime's
claim, but no longer proves gate-level independent agreement.

### Key management

- Gate key lives in `hatun-mcp`'s own process, generated independently of
  the runtime key. Different key material, different storage.
- This does not require a witness-cosigned public transparency log (Sello's
  full design). It requires only that the gate is a genuinely separate
  process from the runtime it is co-signing for — which `hatun-mcp` already
  is architecturally, since it sits at the MCP boundary.

## What this does and does not fix

**Fixes:** a single compromised runtime can no longer unilaterally produce
a `VERIFIED` receipt. Forging one now requires compromising both the runtime
and the gate process.

**Does not fix:** collusion between runtime and gate (both compromised
together); missing receipts (a call that bypasses the gate entirely is not
addressed by this proposal — see governed-receipt-spec `docs/NON_GOALS.md`,
item 6); confidentiality of receipt contents (still unencrypted, unlike
Sello's HPKE design).

## Implementation scope estimate

- Add second keypair generation to `hatun-mcp` gate initialization: small.
- Extend DSSE envelope signature array handling in `szl-receipt`: small,
  additive, backward-compatible (single-signature receipts remain valid,
  just labeled `PARTIALLY_ATTESTED` instead of rejected).
- Update `governed-receipt-spec` verifier logic and status vocabulary: small.
- No new external dependency, no witness infrastructure, no HPKE.

This is intentionally the minimum viable version of Sello's idea, sized to
what `hatun-mcp` already has rather than importing Sello's full stack.
