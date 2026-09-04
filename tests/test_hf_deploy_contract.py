"""Source-level contract for Hatun's consolidated public architecture."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RETIRE_COMMIT = "5a3c340a1115ad0654350b77ac545ff537e3382c"
CANONICAL_PRODUCT = "https://a-11-oy.com/wires"


def test_source_card_is_controlled_and_complete():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("---\n")
    header = readme.split("---\n", 2)[1]
    required = (
        "sdk: docker",
        "app_port: 7860",
        "license: apache-2.0",
        "title: Hatun MCP",
    )
    for marker in required:
        assert marker in header, marker
    short_description = next(
        line.removeprefix("short_description: ").strip()
        for line in header.splitlines()
        if line.startswith("short_description: ")
    )
    assert len(short_description) <= 60


def test_standalone_hf_publisher_is_intentionally_retired():
    assert not (ROOT / ".github/workflows/hf-deploy.yml").exists()
    contract = (ROOT / "docs/HATUN_SURFACE_CONTRACT.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        RETIRE_COMMIT,
        CANONICAL_PRODUCT,
        "szl-holdings/hatun-mcp",
        "Do not recreate `.github/workflows/hf-deploy.yml`",
        "decorative lines are not telemetry",
        "Λ remains Conjecture 1",
    ):
        assert marker in contract, marker


def test_canonical_product_witness_is_read_only_and_has_no_hf_writer():
    workflow = (ROOT / ".github/workflows/hf-drift-check.yml").read_text(
        encoding="utf-8"
    )
    required = (
        "name: Hatun Canonical Product Surface Witness",
        "workflow_dispatch: {}",
        "types: [hatun-product-deployed]",
        RETIRE_COMMIT,
        CANONICAL_PRODUCT,
        "Hatun Gateway",
        "/api/a11oy/v1/mesh/state",
        "https://github.com/szl-holdings/hatun-mcp",
        'data-szl-holo-asset="style-v2"',
        'data-szl-holo-asset="script-v2"',
        "permissions:\n  contents: read",
        "persist-credentials: false",
    )
    for marker in required:
        assert marker in workflow, marker
    for forbidden in (
        "HF_TOKEN",
        "HF_ORG_TOKEN",
        "HF_WRITE_TOKEN",
        "SZLHOLDINGS/hatun-mcp",
        "reusable-hf-deploy",
        "reusable-hf-module-drift-check",
        "workflow_run:",
        "contents: write",
        "secrets: inherit",
    ):
        assert forbidden not in workflow, forbidden


def test_runtime_exposes_fail_closed_build_identity():
    source = (ROOT / "hatun_mcp/server_http.py").read_text(encoding="utf-8")
    required = (
        'os.environ.get("SZL_GIT_SHA"',
        '"state": "OBSERVED" if observed else "UNAVAILABLE"',
        '"receipt_minted": False',
        'Route("/api/build-info", build_info)',
        "status_code=200 if observed else 503",
    )
    for marker in required:
        assert marker in source, marker


def test_runtime_exposes_exact_byte_manifest_attestation():
    source = (ROOT / "hatun_mcp/server_http.py").read_text(encoding="utf-8")
    governance = (ROOT / "hatun_mcp/governance.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required_source = (
        'MCP_MANIFEST_ATTESTATION_PATH = "/.well-known/mcp-manifest-attestation"',
        'MCP_MANIFEST_PREDICATE_TYPE = (',
        "hashlib.sha256(manifest_bytes).hexdigest()",
        "_SERVER_CARD_BYTES = _deterministic_json_bytes(_server_card())",
        "_MANIFEST_ATTESTATION_BYTES = _deterministic_json_bytes(",
        "Route(MCP_MANIFEST_ATTESTATION_PATH, manifest_attestation)",
    )
    for marker in required_source:
        assert marker in source, marker
    assert 'IN_TOTO_PAYLOAD_TYPE = "application/vnd.in-toto+json"' in governance
    assert "dsseEnvelope=null" in readme
    assert "DRAFT extension" in readme


def test_readme_separates_hatun_readiness_from_upstream_live_evidence():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    normalized = " ".join(readme.split())
    required = (
        "**PARTIAL**: Hatun is locally ready",
        "Hatun's local process, receipt chain, and signer only",
        "they do not probe the upstream organs",
        "separate bounded, read-only probe",
        "response status, source, and observation timestamp",
        "never trigger an action merely to claim availability",
        "present that row as **PARTIAL** or **UNAVAILABLE**",
        "These checks do not establish killinchu or a11oy organ availability",
    )
    for marker in required:
        assert marker in normalized, marker


def test_dockerfile_deploy_set_contains_runtime_console_and_card():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY hatun_mcp/server_http.py" in dockerfile
    assert "COPY hatun_mcp/console.py" in dockerfile
    assert "COPY hatun_mcp/console_v2.py" in dockerfile
    assert "COPY README.md" in dockerfile


def test_dockerfile_copies_every_package_module():
    # The image uses per-file COPY (no directory copies), so a new module that is
    # not listed here imports fine in unit tests and then fails at container start.
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    package = ROOT / "hatun_mcp"
    missing = [
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in sorted(package.rglob("*.py"))
        if "__pycache__" not in path.parts
        and f"COPY {str(path.relative_to(ROOT))} " not in dockerfile
    ]
    assert not missing, f"module(s) absent from the Dockerfile deploy set: {missing}"


def test_consolidated_contract_runs_for_runtime_and_surface_changes():
    workflow = (ROOT / ".github/workflows/hf-deploy-contract.yml").read_text(
        encoding="utf-8"
    )
    assert "name: Hatun Consolidated Surface Contract" in workflow
    assert "Verify source runtime, retired publisher, and canonical product route" in workflow
    for path in (
        "requirements.txt",
        "hatun_mcp/server.py",
        "hatun_mcp/console_v2.py",
        "docs/HATUN_SURFACE_CONTRACT.md",
        "tests/test_dependency_contract.py",
        ".github/workflows/hf-drift-check.yml",
    ):
        assert workflow.count(f"- {path}") == 2, path
    assert ".github/workflows/hf-deploy.yml" not in workflow
