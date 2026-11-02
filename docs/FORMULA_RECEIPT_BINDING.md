# Formula call receipts v1

`szl_formula_evaluate` adds a versioned binding to its existing signed Khipu
receipt. It binds the effective formula name, arguments and optional caller
challenge to the returned `tool`, `status`, `data` and `backend` fields.

This contract covers this one tool. Other tool receipts retain their existing
scope. The HTTP operator allowlist, permitted local formulas, signer loading,
key discovery and raw-signing prohibition are unchanged.

## Call and verify

An existing call with `name` and optional `args` keeps the same result shape.
A caller that wants to associate a response with one pending request generates
and saves a fresh challenge, for example `secrets.token_urlsafe(32)`, and includes
it in `arguments.receipt_challenge`. Accepted challenges are 22–128 ASCII
base64url characters. Entropy is the caller's responsibility.

After an authenticated MCP call, parse the JSON tool response (the JSON text in
`result.content[0].text`) and verify it locally:

```python
from pathlib import Path
from hatun_mcp.formula_receipts import verify_formula_response

packet = verify_formula_response(
    response,
    trusted_public_key_pem=Path("trusted-operator-p256.pem").read_bytes(),
    expected_client_id=expected_operator_identity,
    name="sigmoid",
    args={"x": 0},
    receipt_challenge=saved_pending_challenge,
)
assert packet["status"] == "success"  # Declines and failures are also verifiable.
```

The public key and expected operator identity must come from a separately
trusted operator configuration. Fetching `/pubkey` beside the response does not
establish that trust. Signature key IDs and envelope mode labels do not replace
cryptographic verification. Key rotation/revocation policy is outside this helper.

The helper verifies the P-256 DSSE signature over the existing payload type,
the signed packet hash, expected operator/tool/operation, the outer receipt
identity, and both binding digests. A changed result, changed request, wrong
challenge, wrong key, missing binding, unsigned receipt or duplicate signed JSON
member fails verification. Unsigned server mode remains explicit and is rejected
by the verifier.

## Bytes and schema

`receipt.detail.formula_call_binding` has exactly these v1 members:

```json
{
  "schema": "urn:szl:hatun:formula-call-binding:v1",
  "canonicalization": "python-json-finite-v1",
  "algorithm": "sha256",
  "request_digest": "<lowercase SHA-256 hex>",
  "response_digest": "<lowercase SHA-256 hex>"
}
```

The request object has `tool: "szl_formula_evaluate"`,
`operation_id: "formula.evaluate"`, `name`, `args`, and `receipt_challenge`.
Omitted/null `args` normalize to `{}`; an omitted/null challenge normalizes to
`null`. Arguments are the effective JSON values passed to the tool after MCP
argument validation, rather than the original HTTP message bytes. The snapshot
is taken before backend construction; backend mutation cannot rewrite it.

The response projection consists of exactly `tool`, `status`, `data` and
`backend`. It is constructed by the same helper used for the returned response.
Declined calls bind the request and null data/backend without backend execution.
Non-finite or non-JSON backend results become a bound failure with null data.
Non-JSON request values are rejected before backend construction.

Each digest is SHA-256 of these bytes, concatenated without additional framing:

1. ASCII `urn:szl:hatun:formula-call-binding:v1`.
2. One NUL byte.
3. ASCII `request` or `response` (domain separation).
4. One NUL byte.
5. Canonical bytes of that object.

`python-json-finite-v1` is UTF-8 output of Python `json.dumps` with
`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=True`, and
`allow_nan=False`, after recursively requiring JSON null, booleans, strings,
integers, finite floats, lists and objects with string keys. Object keys sort by
Unicode code point; non-ASCII characters are escaped. Integer `0`, float `0.0`
and float `-0.0` intentionally have different bytes. Tuple and non-string key
coercions are forbidden. This profile is **not RFC 8785/JCS**. Other languages
must reproduce the stated profile and its vectors, or invoke the supplied Python
verifier. [Three byte/digest vectors](../tests/fixtures/formula-call-binding-v1.json)
cover integer/float distinctions, negative zero, Unicode and own `__proto__` keys.
The existing Khipu packet hash and DSSE payload type do not change.

## Limits and migration

A verified binding authenticates the signer's assertion about these fields. It
does not prove correct arithmetic, honest server execution, authorization beyond
the separately trusted operator policy, whole-chain completeness or durable
receipt acceptance. The verifier does not certify unsigned narrative/governance
metadata outside the listed projection and signed packet.

The server does not consume challenges or maintain a replay store. A fresh,
unpredictable caller challenge compared against a saved pending request prevents
accepting an unrelated response for that request; accepting the same response
again with the same challenge remains possible. Callers needing one-time use
must atomically consume their pending request in their own durable store.

Legacy callers can ignore the added signed detail. New verifiers require v1
binding and intentionally reject older unbound receipts; there is no fallback
that upgrades a historical receipt to proof of its separately returned data.
Roll out the producer before requiring v1 in clients. Existing records remain
historical evidence with their original narrower scope. This source proposal
has not been deployed or qualified against a live provider.
