"""Fail-closed tests for Hatun's FastMCP dependency contract."""

import re
from importlib import metadata
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _mcp_requirement() -> str:
    for raw_line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        requirement = raw_line.split("#", 1)[0].strip()
        if re.match(r"^mcp(?:\s|[<>=!~])", requirement, flags=re.IGNORECASE):
            return requirement
    raise AssertionError("requirements.txt must declare the mcp runtime dependency")


def test_mcp_runtime_stays_on_the_fastmcp_compatible_major() -> None:
    requirement = _mcp_requirement()
    assert re.search(r"<\s*2(?:\D|$)", requirement), (
        "Hatun imports mcp.server.fastmcp and must fail closed before mcp 2.x"
    )

    installed_version = metadata.version("mcp")
    assert installed_version.split(".", 1)[0] == "1", installed_version

    from mcp.server.fastmcp import FastMCP

    assert FastMCP is not None


def test_dependabot_cannot_reopen_the_mcp_major_version_outage() -> None:
    config = yaml.safe_load(
        (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    )
    pip_root = next(
        update
        for update in config["updates"]
        if update["package-ecosystem"] == "pip" and update["directory"] == "/"
    )
    mcp_ignore = next(
        rule for rule in pip_root["ignore"] if rule["dependency-name"] == "mcp"
    )
    assert mcp_ignore["update-types"] == ["version-update:semver-major"]
