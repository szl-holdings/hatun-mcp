# Configuring and verifying the DSSE signer (ECDSA-P256)

<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Doctrine v11 LOCKED 749/14/163 @ c7c0ba17 · Λ = Conjecture 1 (advisory) -->

`hatun_mcp/governance.py:DsseSigner` produces ECDSA-P256 signatures over
DSSE pre-authentication encoding (PAE) when it loads a usable key. Otherwise it
returns `PLACEHOLDER` with an empty `signatures` array. A hash-linked receipt,
HTTP 200, or a tool catalog alone does not establish cryptographic signing.

Follow the [surface contract](HATUN_SURFACE_CONTRACT.md) for deployment authority.
The standalone Hugging Face publisher is retired. This procedure applies only to
an operator-admitted Hatun runtime; it does not authorize restoring that publisher
or changing the canonical product surface at <https://a-11-oy.com/wires>.

## 1. Establish the expected signing identity

Use the deployment's approved P-256 private key, or generate one for a new
identity in the operator's protected key-management environment:

```bash
umask 077
openssl ecparam -name prime256v1 -genkey -noout -out hatun_signing_key.pem
openssl ec -in hatun_signing_key.pem -pubout -out expected-public.pem
```

Never commit, log, return, or put the private key in command history or an image.
Record the expected public key
through a trusted channel before checking the runtime. The repository's
`PUBKEY_szlholdings-ec-p256.pem` is an expected key only if the deployed private
key is its matching counterpart. The `szlholdings-ec-p256` key ID is a label,
not a fingerprint or proof of that match.

## 2. Configure the admitted runtime before startup

Set `HATUN_MCP_PUBLIC_BASE` to the admitted runtime's HTTPS origin before
process startup, for example `https://gateway.example.org`. Its `/connect`
descriptor, console client snippet, manifest identity and attestation public-key
URL use that fixed origin; request headers cannot rewrite them. Paths such as
`/mcp/` are mounted at the origin root. Credentials, path prefixes, query strings,
fragments and malformed origins fail startup. HTTP is accepted only on loopback
for local development; the unset default is `http://127.0.0.1:7860`.

Set `HATUN_MCP_ALLOWED_ORIGINS` explicitly if browser clients need additional
origins. Reverse proxies forwarding another host must explicitly configure
`HATUN_MCP_ALLOWED_HOSTS`. These settings do not admit a release or establish
availability. The public product page is not an MCP transport origin.

For HTTP, configure an existing admitted operator key's explicit
`HATUN_MCP_SCOPE_<fingerprint>` binding as described in
[HTTP operator admission](HTTP_AUTHENTICATION.md). The operator credential and
DSSE private key have separate purposes. A `szl_` prefix alone does not admit a
caller. Send exactly one credential header through the client's protected
configuration; never place credentials in source, command-line arguments or
URLs. Only stateless Streamable HTTP at `/mcp/` is enabled; legacy `/sse` and
`/messages` return 410 after admission.

Use the deployment's secret injection mechanism to supply either:

- `HATUN_MCP_SIGNING_KEY`: the complete unencrypted P-256 private-key PEM; or
- `HATUN_MCP_SIGNING_KEY_PATH`: a protected, readable file containing that PEM.

The direct PEM environment variable takes precedence when present, including
when its value is empty or invalid. Key-path loading is considered only when the
direct variable is absent. The signer loads once at process initialization;
changing a secret does not reload the existing signer. Use the deployment's
normal controlled restart procedure after a configuration change.

`SZL_COSIGN_PRIVATE_PEM` does not configure this signer. The `dsse_sign` tool's
`key_env_var` argument is an advisory compatibility field and cannot select,
reload, or inject a key. RSA, non-P-256 EC, malformed, and encrypted PEM keys do
not activate the signing path. An unreadable key file can prevent startup.

## 3. Observe local readiness and verify the actual identity

Set `HATUN_MCP_PUBLIC_BASE` in your inspection shell to the same admitted origin
configured in the runtime, then inspect:

```bash
curl --fail --silent --show-error "${HATUN_MCP_PUBLIC_BASE:?set the admitted runtime origin}/readyz"
curl --fail --silent --show-error "${HATUN_MCP_PUBLIC_BASE}/pubkey" --output observed-public.pem
openssl pkey -pubin -in expected-public.pem -outform DER | openssl dgst -sha256
openssl pkey -pubin -in observed-public.pem -outform DER | openssl dgst -sha256
```

The fingerprints must match the separately trusted identity. `/pubkey` can
return HTTP 200 with placeholder text when no key is configured; successful
HTTP transport alone is insufficient. Do not replace the expected key merely
because the runtime serves a different one.

`/readyz` returns 200 only for a verified current-process receipt chain, an
`ECDSA-P256` signer and at least one recognized operator scope binding;
otherwise it returns 503. It does not validate the inspecting caller's key,
probe upstream organs, prove durable ledger delivery, or establish that the
signer has the expected identity.

## 4. Verify a permitted HTTP read receipt

Use `/connect` configuration for an initialized MCP client at the admitted
`/mcp/` endpoint, authenticated with the existing operator key. Confirm that
absent and unadmitted credentials are rejected. For the admitted call, use
`szl_formula_evaluate` with `{"name":"sigmoid","args":{"x":0}}`; this exact
formula executes locally and should return `status: "success"` and
`data.value: 0.5`. Save the decoded tool response as `response.json` (the JSON
inside the MCP result content, not the outer JSON-RPC response).

HTTP denies `dsse_sign` for every scope, including `write` and `admin`. Do not
use raw signing or state-changing tools as hosted availability probes.
`tools/list` is discovery and does not exercise the signer or grant permission.

Record the expected `client_<fingerprint>` identity separately from the
operator's admitted binding as `expected-client.txt`; do not derive it from the
returned receipt or include the API key. Verify the receipt under the trusted
public key (requires `cryptography`):

```bash
python - expected-public.pem response.json expected-client.txt <<'PY'
import base64
import hashlib
import json
import sys
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

key = serialization.load_pem_public_key(Path(sys.argv[1]).read_bytes())
assert isinstance(key, ec.EllipticCurvePublicKey)
assert isinstance(key.curve, ec.SECP256R1)
response = json.loads(Path(sys.argv[2]).read_text())
envelope = response["dsse"]
assert envelope["payloadType"] == "application/vnd.szl.hatun-mcp.response+json"
kind = envelope["payloadType"].encode("utf-8")
payload = base64.b64decode(envelope["payload"], validate=True)
assert len(envelope["signatures"]) == 1
signature = base64.b64decode(envelope["signatures"][0]["sig"], validate=True)
pae = b"DSSEv1 %d %s %d %s" % (len(kind), kind, len(payload), payload)
key.verify(signature, pae, ec.ECDSA(hashes.SHA256()))
signed = json.loads(payload)
receipt = signed["receipt"]
assert receipt["client_id"] == Path(sys.argv[3]).read_text().strip()
assert receipt["tool"] == response["tool"] == "szl_formula_evaluate"
assert receipt["operation_id"] == "formula.evaluate"
assert receipt["status"] == response["status"] == "success"
assert receipt["detail"]["backend_error"] is None
assert receipt["detail"]["sovereign_mode"] is False
packet = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
assert hashlib.sha256(packet).hexdigest() == signed["continuum_hash"]
assert signed["continuum_hash"] == response["khipu_receipt"]["continuum_hash"]
assert receipt["receipt_id"] == response["khipu_receipt"]["receipt_id"]
assert receipt["prev_hash"] == response["khipu_receipt"]["prev_hash"]
assert response["data"]["value"] == 0.5
print("Verified the read receipt under the trusted P-256 key.")
PY
```

The signed receipt binds the operator, tool, operation, status, detail and
receipt hash. It does not include the formula arguments, result value or a
caller nonce; the result check above observes an unsigned response field.
This verifier alone does not prove freshness, correct computation, a complete
receipt chain, or an external action. Record the authenticated transport
observation and exact build revision separately; public readiness is not that
evidence.

## 5. Optional trusted local signer diagnostic

For a separately authorized local stdio process, `dsse_sign` can test that
process's signer directly. It is unavailable over HTTP. A local diagnostic
does not witness the hosted process or authorize copying its private key.
Call `dsse_sign` with an innocuous payload containing a freshly generated nonce,
for example `{"readiness_probe":"<fresh random nonce>"}`. Save that exact payload
as `probe.json` and the returned `envelope` object as `envelope.json`. `tools/list`
is discovery and does not run the signer. The probe signs the supplied payload;
it does not mint a governed execution receipt.

Verify independently using the trusted public key (requires `cryptography`):

```bash
python - expected-public.pem envelope.json probe.json <<'PY'
import base64
import json
import sys
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

key = serialization.load_pem_public_key(Path(sys.argv[1]).read_bytes())
assert isinstance(key, ec.EllipticCurvePublicKey)
assert isinstance(key.curve, ec.SECP256R1)
envelope = json.loads(Path(sys.argv[2]).read_text())
assert envelope["payloadType"] == "application/vnd.szl.hatun-mcp.response+json"
kind = envelope["payloadType"].encode("utf-8")
payload = base64.b64decode(envelope["payload"], validate=True)
assert json.loads(payload) == json.loads(Path(sys.argv[3]).read_text())
assert len(envelope["signatures"]) == 1
signature = base64.b64decode(envelope["signatures"][0]["sig"], validate=True)
pae = b"DSSEv1 %d %s %d %s" % (len(kind), kind, len(payload), payload)
key.verify(signature, pae, ec.ECDSA(hashes.SHA256()))
print("Verified the expected probe payload under the trusted P-256 key.")
PY
```

An actual governed tool response exposes its receipt envelope in `dsse`. To
assess that evidence, also check the signed receipt's tool, operation, detail,
status and hash against the operation being audited. A signature proves those
bytes were signed; it does not independently prove an external action occurred.

## Persistence and aggregation boundaries

Khipu receipts are held in process memory. `SZL_RECEIPT_SINK` forwarding is
optional and best effort: a daemon thread attempts a POST and errors are
swallowed. Neither emission nor local readiness waits for durable acceptance.
This procedure establishes no restart recovery or durable delivery guarantee.

BLS aggregation is separate from the ECDSA signer. A dependency declaration or
successful `py_ecc` import alone does not establish signer provenance or
independent organ signatures. `MERKLE-AGG` is the unsigned hash aggregation
fallback; it is not a BLS signature. Review the actual envelope and trusted
signing identity before making an aggregation claim.

Sigstore Rekor transparency-log inclusion remains a disclosed placeholder.

*Doctrine v11 LOCKED · Λ = Conjecture 1 (advisory, NOT a theorem) · SLSA L1 honest*
