"""Source-level contract for the governed Hatun-MCP Hugging Face deployment."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = "5d339cf22e394635285f2c5fccb14d9ebb4f7455"


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


def test_deployer_is_pinned_source_bound_and_automatic():
    workflow = (ROOT / ".github/workflows/hf-deploy.yml").read_text(encoding="utf-8")
    required = (
        "branches: [main]",
        f"reusable-hf-deploy.yml@{PIN}",
        "hf-repo: SZLHOLDINGS/hatun-mcp",
        "ref: ${{ github.sha }}",
        "include-readme: true",
        "prune: true",
        "source-revision-variable: SZL_GIT_SHA",
        "source-revision-probe-path: /api/build-info",
        '"/api/build-info"',
        "HF_TOKEN: ${{ secrets.HF_ORG_TOKEN || secrets.HF_TOKEN }}",
    )
    for marker in required:
        assert marker in workflow, marker
    assert "workflow_dispatch: {}" in workflow
    assert "secrets: inherit" not in workflow
    assert "@main" not in workflow


def test_drift_is_sequenced_after_deploy_and_has_no_waivers():
    workflow = (ROOT / ".github/workflows/hf-drift-check.yml").read_text(
        encoding="utf-8"
    )
    required = (
        "workflow_run:",
        "Deploy to HuggingFace Space",
        "github.event.workflow_run.conclusion == 'success'",
        f"reusable-hf-module-drift-check.yml@{PIN}",
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


def test_dockerfile_deploy_set_contains_build_identity_code_and_card():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY hatun_mcp/server_http.py" in dockerfile
    assert "COPY README.md" in dockerfile
