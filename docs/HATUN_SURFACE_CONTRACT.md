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

## Public witness

`.github/workflows/hf-drift-check.yml` retains its historical filename for
workflow continuity, but it no longer performs Hugging Face module drift. It is
a credential-free, read-only witness of the canonical A11oy Hatun product route.
It checks the public route for the Hatun identity, the live mesh endpoint,
source-repository attribution, and the single local Holo asset bindings.
