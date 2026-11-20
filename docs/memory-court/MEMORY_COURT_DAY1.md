# Memory Court — day-1 pins and receipt schema (v0)

Status: **ROADMAP → design** (schema definition only; no implementation in this PR).
Provenance: adopted from the three-dreamer ruling (Kimi session-10, 2026-11-20, receipts banked in the DC CTO lane runtime; Mistral dream-3 extensions quarantined as UNVERIFIED).

## 1. Spec pins (day-1 requirement)

| Pin | Value | State |
|---|---|---|
| MCP profile | **2026-07-28 GA specification** (stateless core, MRTR, header-based routing) | MEASURED (spec published 2026-07-28, modelcontextprotocol.io blog + modelcontextprotocol/modelcontextprotocol docs/specification/2026-07-28) |
| Normative doc revision (exact commit SHA) | — | **UNKNOWN** — must be cloned and pinned before any conformance claim; fill in the pin table on pin day |
| Hatun source revision | this branch's merge commit | MEASURED at merge time by CI build metadata; server self-report is never trusted |
| Signer trust root | owner-approved, versioned bundle | ROADMAP — owner decision; block all admitted mutations until it exists |

Rule: routing metadata never grants authorization. Stateless core means no process-local protocol/session state in the new path.

## 2. Atomic record: `szl.memory-admissibility-receipt/v0`

Every admitted memory operation produces a signed envelope. JCS (RFC 8785) canonicalization for every digest.

```json
{
  "schema": "szl.memory-admissibility-receipt/v0",
  "operation": "commit | query | revoke | abstain | blocked",
  "memory_id": "mem_...",
  "event_id": "evt_...",
  "ts": "2026-11-20T00:00:00Z",
  "operator": { "subject": "<verified operator id>", "tenant": "<tenant id>", "claims_source": "hatun-live-auth:v1" },
  "request_digest": { "canonical_jcs_sha256": "…", "args_redacted": true },
  "mcp": { "spec_profile": "2026-07-28", "transport": "streamable-http" },
  "hatun": { "source_revision": "…", "build_digest": "…", "doctrine_digest": "…", "policy_digest": "…", "tool_schema_digest": "…" },
  "adjudication": { "gate": "yuyay-13", "decision": "admit | abstain | block", "reason_code": "…" },
  "lineage": { "sources": [{"uri": "…", "revision": "…", "content_sha256": "…"}], "parents": ["mem_…"], "lineage_complete": true },
  "khipu": { "entry_id": "…", "outcome": "appended" },
  "dsse": { "envelope": "…", "signer_key_id": "…", "trust_root_version": "…", "trust_root_digest": "…" },
  "status_current": "admissible | revoked | superseded | unknown"
}
```

Invariants (v0, testable):
1. Missing operator auth, wrong tenant, unknown/revoked signer, or unknown/dirty build ⇒ **no admitted operation** (fail closed).
2. Revocation appends; it never deletes. Old receipts stay historically verifiable; `status_current` is the only living truth.
3. Revoked ancestry is never returned as currently admissible.
4. Incomplete lineage is never presented as a complete blast radius: emit `abstain` with `reason_code: "lineage-incomplete"` instead.
5. Sensitive payloads stay access-controlled; the receipt carries digests only.
6. Signer failure blocks every admitted mutation (no unsigned writes, ever).

## 3. Tool surface (first slice — three tools only)

| Tool | Contract |
|---|---|
| `khipu_memory_commit` | Accept payload, provenance class, exact source revisions/digests, parent ids, supersession, idempotency key. Derived memories must declare parents in v0. Returns memory/event ids + adjudication + signed receipt. |
| `khipu_memory_query` | Return only currently admissible memory: id/key/metadata + lineage queries; provenance + status + receipts, or a structured abstention. Semantic/vector retrieval is a later derived index, never the source of truth. |
| `khipu_memory_revoke` | Appends source or memory revocation (reason + evidence required); traverses declared lineage; returns impacted ids, coverage limits, signed impact receipt. |

Common response envelope: `status`, `data`, `provenance`, `receipt`, `abstention_reason`.
Later candidates (`verify`, `export`, `replay`) are out of scope for the first slice.

## 4. Substrate ruling (agentic database)

**szl-khipu LMDB is the append-only system of record**, using its tested replication where available. Materialized current-admissibility views sit on top. Graph/search/vector indexes may be added later but must be disposable and rebuildable from Khipu. A vector store is never the source of truth. One writer/partition path in v0; no distributed-consensus, multi-writer, or global-consistency claims.

Operating rule: **the agent proposes; Yuyay/PURIQ adjudicates; Khipu remembers; DSSE/cosign makes the record verifiable.**

## 5. Negative test vectors (must exist before any green claim)

1. Unauthenticated caller ⇒ no admitted op.
2. Unknown/revoked signer ⇒ no admitted mutation.
3. Tampered covered field ⇒ verification fails.
4. Stale source revision ⇒ commit abstains (`reason_code: "source-stale"`).
5. Missing declared parent on derived memory ⇒ commit blocked.
6. Revocation with incomplete lineage ⇒ `abstain`, never partial blast-radius presented as complete.
7. Restart mid-commit ⇒ no process-local session dependency; idempotency key replays cleanly.
8. Signer unavailable ⇒ zero admitted writes (fail closed).

## 6. Labels and non-claims

- This PR is design/schema only: **no GA claim, no conformance claim, no performance claim**.
- MRTR semantics come from the pinned normative text only; none are invented here.
- Issues #200 and #195 are advanced (design surfaces defined), **not closed**; they close only on their own acceptance criteria and recorded conformance matrices.
- Novelty claim is bounded to the 2026-11-20 ecosystem scan (mcp-finder/best-mcp-servers-2026, awesomeagents.ai leaderboard): no known competitor combines DSSE-signed calls + per-call adjudication + retroactive provenance receipts on memory. No global novelty or FTO claim is made.
