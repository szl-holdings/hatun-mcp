# MCP Registry listing — hatun-mcp

Server name: `io.github.szl-holdings/hatun-mcp`
Package: OCI image `ghcr.io/szl-holdings/hatun-mcp:<version>` (stdio via `python -m hatun_mcp.server`)
Publisher: `.github/workflows/publish-mcp.yml`, GitHub OIDC, runs only from a `v*` tag.

## State

The listing exists only when `mcp-registry-receipt.json` from a `publish-mcp` run shows
`state: MEASURED_LISTED`. Until a receipt says so, this repository does not claim to be listed.
A green `publish` step that cannot be read back from the registry fails the run on purpose.

## What a client runs

```
docker run -i --rm -e HATUN_MCP_DISABLE_DYNAMIC=true ghcr.io/szl-holdings/hatun-mcp:<version> python -m hatun_mcp.server
```

Without `HATUN_MCP_SIGNING_KEY` the receipts are emitted UNSIGNED and say so; with the ECDSA-P256
PEM injected they verify against `PUBKEY_szlholdings-ec-p256.pem`.

## Release procedure

1. Bump `hatun_mcp/__init__.py` `__version__`, `server.json` `version` and the OCI identifier tag together.
2. Merge to `main` (ci.yml pushes `:latest` and `:<sha>` to GHCR as before).
3. Tag `v<version>` on that commit. `publish-mcp.yml` builds `:<version>` with the
   `io.modelcontextprotocol.server.name` label the registry uses for ownership verification,
   attests provenance, publishes `server.json`, re-reads the registry, and uploads the receipt.

## Not claimed

No remote (`streamable-http`) endpoint is listed: the hosted Space URL returned 404 on 2026-10-01.
Add a `remotes` entry only after the endpoint answers `initialize` publicly.
