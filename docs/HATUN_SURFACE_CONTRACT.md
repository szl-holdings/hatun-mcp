# Hatun surface contract

## Current authority

| Layer | Canonical surface | Role |
|---|---|---|
| Runtime source | `szl-holdings/hatun-mcp` | Python MCP gateway, tests, Docker image contract, server card, and local developer console |
| Public product experience | `https://a-11-oy.com/wires` | Hatun Gateway inside the A11oy product shell |
| Runtime interface | `/mcp/` when this package is deployed by an admitted operator | Streamable HTTP Model Context Protocol endpoint |
| Evidence | GitHub tests plus the source-bound server-card and manifest-attestation contracts | Reproducible verification; not an uptime claim |

## Lifecycle decision

The standalone `SZLHOLDINGS/hatun-mcp` Hugging Face publisher was retired on
September 3, 2026 by protected-main commit
`5a3c340a1115ad0654350b77ac545ff537e3382c`. The deletion of
`.github/workflows/hf-deploy.yml` is intentional. It prevents the retired Space
from being recreated by an automatic writer.

The local `push_to_hf.py` uploader (a founder-token `upload_folder` to the same
retired Space) was a second write path left behind by that retirement. It was
removed on September 29, 2026. No tracked non-test file may call a Hugging Face
write API; `tests/test_hf_deploy_contract.py` enforces this. Re-creating a Hub
writer requires the same explicit product-architecture decision as invariant 1,
and then a committed workflow, never a local script.

The canonical user-facing Hatun experience is the product route at
`a-11-oy.com/wires`. That route is source-owned by `szl-holdings/a11oy`, reads
A11oy's live mesh contract, links back to this repository, and fails closed when
runtime evidence is unavailable.

## Non-negotiable invariants

1. Do not recreate `.github/workflows/hf-deploy.yml` without a new, explicit
   product-architecture decision.
2. Do not treat a retired Hugging Face repository or application host as the
   current public Hatun front door.
3. Keep the Python package independently buildable and container-testable.
4. Keep `hatun_mcp.console.CONSOLE_HTML` as the stable import used by the HTTP
   server; implementation modules must be present in the Docker deploy set.
5. Public product status must come from a live contract. Missing evidence is
   `UNAVAILABLE`; no count, tool, wire, or signer state may be fabricated.
6. The shared SZL family grammar is Obsidian Signal. Hatun's unique instrument is
   the indigo/frost gateway weave; decorative lines are not telemetry.
7. Λ remains Conjecture 1 and is not a theorem.

## Admitted runtime configuration

The independently deployed Python package uses `HATUN_MCP_PUBLIC_BASE` as its
public origin, for example `https://gateway.example.org`. Configure it before
process startup. Its `/connect` descriptor, console client snippet, manifest
identity, and attestation public-key URL use that same fixed origin. Request
`Host` and forwarded headers cannot rewrite these cached artifacts.

With no setting, the development default is `http://127.0.0.1:7860`. HTTP is
accepted only for loopback; hosted origins require HTTPS. Credentials, path
prefixes, query strings, fragments and malformed origins fail startup. The
origin's admitted stateless Streamable HTTP endpoint is `/mcp/`, mounted at the
root. Legacy `/sse` and `/messages` transports are disabled; admitted requests
receive `410`. The operator binding and restricted read capability contract is
documented in [HTTP operator admission](HTTP_AUTHENTICATION.md). Set
`HATUN_MCP_ALLOWED_ORIGINS` explicitly if browser clients need additional
origins; its default includes the configured public origin.
The MCP transport pins the configured host and port as well. Reverse proxies
that forward another host must explicitly set `HATUN_MCP_ALLOWED_HOSTS`.

This setting does not deploy a server, admit a release, configure credentials,
or establish availability. The public product at `a-11-oy.com/wires` is not an
MCP transport origin. The retired Hugging Face address is not a default or a
readiness probe target. An operator must separately witness `/healthz`,
`/readyz`, `/api/build-info`, and authenticated MCP behavior on the admitted
runtime before claiming that runtime is operational.

## Public witness

`.github/workflows/hf-drift-check.yml` retains its historical filename for
workflow continuity, but it no longer performs Hugging Face module drift. It is
a credential-free, read-only witness of the canonical A11oy Hatun product route.
It checks the public route for the Hatun identity, the live mesh endpoint,
source-repository attribution, and the single local Holo asset bindings.

## Public GitHub estate observer

The source catalog adds `szl_github_estate_snapshot`, a parameterless, bounded
public-organization observer. It inventories public GitHub repository metadata
and open-PR check-run evidence with source citations and canonical digest
binding. It does not search private repositories, mutate repositories or PRs,
dispatch workflows, or publish models/Spaces. The provider client is fixed to
GitHub and never inherits authentication or proxy configuration.

`COMPLETE` describes coverage of this limited, non-atomic observation, not
passing CI, protected merge eligibility, signed deployment, model quality, or
whole-estate readiness. Missing or unknown checks remain `UNKNOWN`; truncated
or unavailable evidence is disclosed. The observer's digest is covered by the
existing governance receipt; signatures exist only if the envelope actually
contains them. Optional operator receipt forwarding remains unchanged.

A source test or server-card entry does not make this tool live on A11oy's
public product route or on any remote MCP server. Deployment admission and an
exact-source runtime `tools/list` / `tools/call` witness remain separate steps.
