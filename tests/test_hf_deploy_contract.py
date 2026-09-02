"""Source-level contract for the governed Hatun-MCP Hugging Face deployment."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_PIN = "5a4c781502417fd0c4162514b2972a5852ae9fab"
DRIFT_PIN = "5d339cf22e394635285f2c5fccb14d9ebb4f7455"


def test_space_card_is_source_controlled_and_complete():
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


def test_deployer_is_pinned_source_bound_and_automatic():
    workflow = (ROOT / ".github/workflows/hf-deploy.yml").read_text(encoding="utf-8")
    required = (
        "branches: [main]",
        '      - .github/workflows/hf-deploy.yml',
        f"reusable-hf-deploy.yml@{DEPLOY_PIN}",
        "hf-repo: SZLHOLDINGS/hatun-mcp",
        "ref: ${{ github.sha }}",
        "include-readme: true",
        "prune: true",
        "restart-space: true",
        "wait-running: 1200",
        "require-default-branch-tip: true",
        "source-revision-variable: SZL_GIT_SHA",
        "source-revision-probe-path: /api/build-info",
        '"/.well-known/mcp-manifest-attestation"',
        '"/api/build-info"',
        "HF_TOKEN: ${{ secrets.HF_ORG_TOKEN || secrets.HF_TOKEN }}",
    )
    for marker in required:
        assert workflow.count(marker) == 1, marker
    assert "workflow_dispatch: {}" in workflow
    assert "secrets: inherit" not in workflow
    assert "@main" not in workflow
    assert "restart-space: false" not in workflow
    assert "require-default-branch-tip: false" not in workflow
    assert "wait-running: 0" not in workflow


def test_deployer_does_not_confuse_health_with_source_identity():
    workflow = (ROOT / ".github/workflows/hf-deploy.yml").read_text(encoding="utf-8")
    assert "source-revision-probe-path: /api/build-info" in workflow
    assert "source-revision-probe-path: /healthz" not in workflow
    smoke = workflow.split("smoke-paths:", 1)[1].splitlines()[0]
    for route in (
        '"/"',
        '"/healthz"',
        '"/.well-known/mcp/server-card.json"',
        '"/.well-known/mcp-manifest-attestation"',
        '"/api/build-info"',
    ):
        assert route in smoke, route


def test_drift_is_sequenced_after_deploy_and_has_no_waivers():
    workflow = (ROOT / ".github/workflows/hf-drift-check.yml").read_text(
        encoding="utf-8"
    )
    required = (
        "workflow_run:",
        "Deploy to HuggingFace Space",
        "github.event.workflow_run.conclusion == 'success'",
        f"reusable-hf-module-drift-check.yml@{DRIFT_PIN}",
        "hf-repo: SZLHOLDINGS/hatun-mcp",
        "mode: direct",
    )
    for marker in required:
        assert marker in workflow, marker
    assert "@main" not in workflow

    allowlist = json.loads(
        (ROOT / ".github/hf-module-drift-allow.json").read_text(encoding="utf-8")
    )
    assert allowlist["accepted_divergences"] == {}


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


def test_dockerfile_deploy_set_contains_build_identity_code_and_card():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY hatun_mcp/server_http.py" in dockerfile
    assert "COPY README.md" in dockerfile


def test_dockerfile_copies_every_package_module():
    # The image uses per-file COPY (no directory copies), so a new module that is
    # not listed here imports fine in CI and then fails at container start. Lock
    # the deploy set to the actual package contents instead.
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    package = ROOT / "hatun_mcp"
    missing = [
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in sorted(package.rglob("*.py"))
        if "__pycache__" not in path.parts
        and f"COPY {str(path.relative_to(ROOT))} " not in dockerfile
    ]
    assert not missing, f"module(s) absent from the Dockerfile deploy set: {missing}"


def test_source_contract_runs_for_runtime_dependency_changes():
    workflow = (ROOT / ".github/workflows/hf-deploy-contract.yml").read_text(
        encoding="utf-8"
    )
    for path in (
        "requirements.txt",
        "hatun_mcp/server.py",
        "tests/test_dependency_contract.py",
    ):
        assert workflow.count(f"- {path}") == 2, path
