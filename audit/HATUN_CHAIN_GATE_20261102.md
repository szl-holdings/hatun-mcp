# Canonical Hatun receipt-chain gate proof packet

**Workcell:** `HATUN-CHAIN-GATE-20261102`

**Base revision:** `3fb34549a14709007d734464eea4654a10dd9d3e` (`main`)

**Evidence class:** local source candidate

## Trigger and prior behavior

`hatun_mcp.server.governed()` awaited its backend before verifying the in-memory
Khipu chain. A broken pre-existing chain could therefore coexist with an already
executed state-changing backend. `KhipuChain.emit()` also wrote
`chain_verified=true` without checking the preceding chain.

## Candidate behavior

- `governed()` verifies Khipu integrity before every backend await.
- An invalid chain closes the unawaited backend coroutine and returns a receipted
  `declined` result with reason `receipt_chain_invalid` and tripwire `T01`.
- `emit()` verifies under the same lock used for append, records the real
  pre-append state, and binds `chain_verified` into the continuum hash and DSSE
  payload.
- `verify()` is serialized with append and also checks the recorded chain head.
- The server-card builder no longer imports `anyio` in a dead `if False` path.

## Verification

| Command | Result |
|---|---|
| `python -m pytest tests/test_chain_gate.py -q` | PASS: `2 passed` |
| `python -m pytest tests/test_governance.py -q -k 'not tool_pipeline and not state_changing'` | PASS: `16 passed, 3 deselected` |
| `python -m py_compile hatun_mcp/governance.py hatun_mcp/server.py hatun_mcp/server_http.py tests/test_chain_gate.py` | PASS |
| `git diff --check` | PASS |
| Baseline `python -m pytest tests/test_governance.py -q` | PARTIAL: `16 passed`, three server tests blocked because the environment lacks `mcp` |

The new regression mutates a continuum hash and proves that a subsequent
receipt reports `chain_verified=false`. It also proves that a fully
authenticated, two-person, state-changing call returns before entering its
backend coroutine. It disables import-time dynamic organ discovery so the test
does not contact or wait for live catalogs. Its minimal import-only MCP stub registers decorators and
the one private tool-manager shape exercised during module import; it never
starts a server or substitutes backend behavior.

## Dependency audit

The supported README, CI, and container paths install `requirements.txt`.
Direct live imports are covered there by `mcp`, `httpx`, `starlette`,
`uvicorn`, `cryptography`, and `py_ecc`. The only additional direct import was
`anyio` in unreachable server-card code; the candidate removes that dead import
instead of depending on a transitive package. `pyproject.toml` intentionally
contains no dependency metadata and the repository does not publish a Python
wheel in the inspected workflows. Wheel self-containment therefore remains an
explicit future packaging decision rather than an implied property of this fix.

## Remaining boundaries

- The Khipu chain is process-local and mutable by a process controller. It is
  neither durable nor independently witnessed.
- The preflight check and backend execution are not one atomic transaction;
  independently durable admission and idempotency remain future work.
- The local environment does not contain the declared MCP SDK, so real SDK
  import and transport integration remain unverified here.
- No container, registry release, hosted runtime, deployment, branch control,
  or public readback changed.
