"""Stable public import for the Hatun Gateway human console.

The implementation lives in :mod:`hatun_mcp.console_v2` so the HTTP server,
existing integrations, and test imports retain the established
``hatun_mcp.console.CONSOLE_HTML`` contract.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

from .console_v2 import CONSOLE_HTML, REPO_URL, SPACE_URL

__all__ = ["CONSOLE_HTML", "REPO_URL", "SPACE_URL"]
