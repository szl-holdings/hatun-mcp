# Leader-Study Upgrade Plan - W27 loop-8 - 2026-11-23

Status: PROPOSE-ONLY DRAFT - DO NOT MERGE. Owner-gated: merging requires governing approval and the estate signature-wall owner unlock.

Repo: hatun-mcp - Hatun-MCP — doctrine-aware Model Context Protocol server. 16 SZL tools under PURIQ governance (Yuyay-13 gate, Khipu receipts, DSSE-signed). Streamable HTTP + SSE.

Frame: OUROBOROS loop-8 leader study. Governing seat: Kimi kimi-k3.1-pro (json_ok, think off). Advisory seats: Astra/Sol/Claude community rails (provenance unverified, advisory only). Leader evidence web-verified 2026-11-23.

## Leader moats to absorb
- MCP Streamable HTTP transport (spec revision 2026-07-28): Single HTTP POST endpoint with removal of the GET stream endpoint and protocol-level sessions, replacing 2024-11-05 HTTP+SSE; MCP-Protocol-Version header and Accept application/json text/event-stream. Moat: Standards-level interoperability and a simpler transport contract that MCP clients can target consistently.
- FastMCP 2.0: Complete toolkit beyond the core spec: deployment, auth, clients, server proxying and composition, REST-to-server generation, dynamic tool rewriting, built-in testing, and Pythonic @mcp.tool decorators for tools/resources/prompts. Moat: Breadth of server and client capabilities plus Python-native ergonomics that reduce integration and testing friction.

## Honest gaps (grounded in repo facts)
- The facts assert Streamable HTTP + SSE but provide no code, tests, or endpoint traces proving conformance to the cited 2026-07-28 revision, including single-POST behavior, removal of the GET stream endpoint and protocol-level sessions, MCP-Protocol-Version handling, or Accept negotiation.
- The README explicitly says the public Hatun Gateway product is not proof that this package's /mcp/ endpoint or a newly added tool is deployed, so live deployment and endpoint reachability remain unverified.
- Receipts are DSSE-signed only with an operator signing key; without one the signer is explicitly PLACEHOLDER and /readyz reports not_ready, so production-grade signed evidence is conditional rather than guaranteed by the repository description.
- The description says 16 SZL tools, while the README says the non-canonical platform copy exposes a smaller tool set; no tool catalog or parity tests are supplied to establish the exact canonical set or prevent divergence.
- The README records that folding in the platform copy is a later founder step, so consolidation is unfinished and the embedded copy remains a stated divergence risk.
- No facts demonstrate FastMCP 2.0 adoption or equivalent capabilities for auth, clients, proxying/composition, REST-to-server generation, dynamic tool rewriting, or built-in testing; these must not be assumed from the Python language or MCP label.
- The SLSA badge claims L1 honest with L2 on the roadmap, so L2 provenance is not established; no CI run, release attestation, or verification instructions are included in the facts.
- pushed_at is null, so current maintenance activity cannot be established from the supplied metadata despite the README's November 2026 web-verification statement.

## Dosed upgrade plan
- Dose 1 — propose a contract-and-evidence inventory only: enumerate the 16 canonical tools, transports, auth behavior, signing modes, and the platform copy's smaller set; mark every item verified or unverified from repository evidence.
- Dose 2 — propose transport conformance tests for the 2026-07-28 revision, covering POST-only behavior, absence of the removed GET stream and protocol-level sessions, MCP-Protocol-Version, Accept negotiation, and any intentionally retained SSE compatibility.
- Dose 3 — propose governance-preserving capability tests for tool registration, Yuyay-13 denial/allow paths, Khipu receipts, and readyz behavior in both PLACEHOLDER and operator-key modes; do not claim DSSE verification without a real key and test evidence.
- Dose 4 — propose a canonical/embedded-copy parity check that fails on contract drift while preserving CANONICAL.md, the smaller local-import scope, and the instruction not to delete repos or recreate hf-deploy.
- Dose 5 — propose a FastMCP 2.0 fit/gap evaluation and, only where compatible, small behind-gate pilots for built-in testing, auth, clients, or composition; exclude REST generation and dynamic rewriting until their governance boundaries are specified.
- Dose 6 — propose release evidence that separates build success, SLSA L1 claims, L2 roadmap work, signed-receipt verification, and actual /mcp/ deployment verification; keep the public product site out of the deployment proof chain.
- Risk note: Medium-high: transport and capability changes can break MCP clients or create a false compliance claim, while auth, dynamic rewriting, proxying, or REST generation could widen the action surface beyond PURIQ governance. Signing and deployment claims carry separate evidence risk because PLACEHOLDER mode is explicit and the public gateway is not endpoint proof; mitigate with small gated changes, negative tests, canonical-copy drift checks, and no SLSA L2 or live-deployment claim until independently verified.
- Propose-only note: This audit proposes changes only; it does not modify the repository, fold in the platform copy, recreate hf-deploy, delete repositories, or assert deployment. Each dose requires founder review and repository-backed evidence before implementation, with Λ = Conjecture 1 (advisory) preserved verbatim.

## Advisory notes (unverified rails, non-binding)
- astra: szl-router: Verifiable routing provenance via cryptographic receipts. szl-forge: Domain-specific data curation pipelines for high-signal QLoRA. hatun-mcp: Formal semantic mapping between doctrine and tool schemas.
- sol: szl-router: Verifiable routing provenance via cryptographic receipts. szl-forge: Domain-specific QLoRA optimization presets for sovereign hardware. hatun-mcp: Formal doctrine-to-tool mapping for deterministic server behavior.
- claude: szl-router: Cryptographic proof of routing intent to prevent provider-side steering. szl-forge: Automated synthetic data curation loops tied to routing receipt failures. hatun-mcp: Formal verification of doctrine compliance for tool-call execution.

## DO NOT MERGE
This plan is a proposal artifact of the 10-pass OUROBOROS loop (loop-8 of 10). No code, no CI, no behavior changes in this file. A reviewer with authority may convert to a work order later.