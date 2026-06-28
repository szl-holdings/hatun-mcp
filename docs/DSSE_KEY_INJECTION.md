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

## Step 2 — Inject the secret into the HF Space

1. Go to **[SZLHOLDINGS/hatun-mcp HF Space](https://huggingface.co/spaces/SZLHOLDINGS/hatun-mcp) → Settings → Repository secrets**
2. Add a new secret:
   - **Name:** `HATUN_MCP_SIGNING_KEY`
   - **Value:** the full PEM contents of `hatun_signing_key.pem` (including `-----BEGIN EC PRIVATE KEY-----` and `-----END EC PRIVATE KEY-----`)
3. Restart the Space (Settings → Factory restart, or push a whitespace commit)

## Step 3 — Verify activation

After the Space restarts, call any governed tool and check the receipt envelope:

```bash
curl -X POST https://szlholdings-hatun-mcp.hf.space/mcp \
  -H "content-type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Look for `"signer_mode": "ECDSA-P256"` in the governance block. If it still says
`"PLACEHOLDER"`, the secret was not injected — check the Space logs for errors in
`DsseSigner.__init__`.

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

- The private key is a **repository secret** (HF Space secrets are not exposed in
  build logs or to fork builders).
- The signer reads the key from `os.environ.get("HATUN_MCP_SIGNING_KEY")` at
  init — no disk write, no logging of the key value.
- SIGSTORE Rekor transparency-log anchoring is Doctrine v12 §2 (disclosed
  placeholder). It does NOT affect the ECDSA-P256 signing path.

---

*Doctrine v11 LOCKED · Λ = Conjecture 1 (advisory, NOT a theorem) · SLSA L1+L2 honest*  
*Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>*  
*Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>*
