# Injecting the DSSE Signing Key (ECDSA-P256)

<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Doctrine v11 LOCKED 749/14/163 @ c7c0ba17 · Λ = Conjecture 1 (advisory) -->
<!-- Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com> -->

The hatun-mcp DSSE signer (`hatun_mcp/governance.py:DsseSigner`) is **fully
implemented**. Without the signing key, every receipt carries `signer_mode:
"PLACEHOLDER"` — a real hash-chain but no cryptographic signature. Injecting
the key activates full ECDSA-P256 signing on every governed tool receipt.

## Current state

| Field | Value |
|---|---|
| `signer_mode` (no key) | `"PLACEHOLDER"` |
| `signer_mode` (key set) | `"ECDSA-P256"` |
| Public key committed | `PUBKEY_szlholdings-ec-p256.pem` |
| Key implementation | `DsseSigner.__init__` in `hatun_mcp/governance.py` |
| BLS12-381 aggregator | `BlsAggregator` in `hatun_mcp/dsse.py`; `py_ecc>=8.0.0` in `requirements.txt` |

## Step 1 — Generate or retrieve the signing key

If you already have the SZL ECDSA-P256 key, skip to Step 2.

To generate a new key pair:

```bash
openssl ecparam -name prime256v1 -genkey -noout -out hatun_signing_key.pem
openssl ec -in hatun_signing_key.pem -pubout -out PUBKEY_szlholdings-ec-p256.pem
```

**Never commit the private key** (`hatun_signing_key.pem`) to any repository.
Commit only the public key (`PUBKEY_szlholdings-ec-p256.pem`).

## Step 2 — Inject the secret into the admitted runtime

The standalone Hugging Face Space is retired. Follow the
[surface contract](HATUN_SURFACE_CONTRACT.md); do not recreate that publisher or
use the public product page as an MCP endpoint.

Use the admitted runtime's operator-managed secret store to inject
`HATUN_MCP_SIGNING_KEY` with the full PEM contents of the existing signing key.
Set `HATUN_MCP_PUBLIC_BASE` to that runtime's HTTPS origin and restart the
process through its normal deployment mechanism. Never put a private key in
the image, source, command history or logs.

## Step 3 — Verify activation

After the process restarts, read the local readiness and public-key contracts
at the admitted origin (set `HATUN_MCP_PUBLIC_BASE` in your shell first):

```bash
curl --fail --silent --show-error "${HATUN_MCP_PUBLIC_BASE:?set the admitted origin}/readyz"
curl --fail --silent --show-error "${HATUN_MCP_PUBLIC_BASE:?set the admitted origin}/pubkey"
```

`/readyz` returns HTTP 200 only when the local receipt chain verifies and
`signer_mode` is `ECDSA-P256`; otherwise it returns HTTP 503. Compare the served
public key to the admitted operator identity. Then use an authenticated MCP
client with `/connect` configuration to call a permitted read-only tool and
verify its DSSE receipt. A `tools/list` response is not a signed tool receipt.
These checks do not establish upstream organ availability.

For the BLS12-381 aggregator (`szl_lambda_quorum` tool):

```bash
python3 -c "from hatun_mcp.dsse import BlsAggregator; a = BlsAggregator(); assert a.available, 'py_ecc not installed'; print('BLS available:', a.available)"
```

This will return `BLS available: True` since `py_ecc>=8.0.0` is in
`requirements.txt`.

## Honest labels

- `signer_mode: "ECDSA-P256"` — real cryptographic signing; verifiable against
  `PUBKEY_szlholdings-ec-p256.pem` offline.
- `signer_mode: "PLACEHOLDER"` — no signature; hash-chain integrity preserved;
  honest disclosure.
- `mode: "MERKLE-AGG"` in quorum receipts — BLS path active only when `py_ecc` is
  importable (it is in the current `requirements.txt`); fallback label honest.

## Security notes

- The private key belongs in the admitted runtime's **secret store**, with no
  exposure to build logs, public configuration or fork builders.
- The signer reads the key from `os.environ.get("HATUN_MCP_SIGNING_KEY")` at
  init — no disk write, no logging of the key value.
- SIGSTORE Rekor transparency-log anchoring is Doctrine v12 §2 (disclosed
  placeholder). It does NOT affect the ECDSA-P256 signing path.

---

*Doctrine v11 LOCKED · Λ = Conjecture 1 (advisory, NOT a theorem) · SLSA L1+L2 honest*  
*Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>*  
*Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>*
