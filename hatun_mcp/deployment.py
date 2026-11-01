"""Operator-bound public origin for runtime discovery; never request-derived.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import ipaddress
import os
import re
from urllib.parse import urlsplit


def public_base(value: str) -> str:
    """Accept an HTTPS origin, or HTTP on loopback for local development.

    Routes are mounted at the origin root. Reject credentials, paths and URL
    controls rather than publishing misleading or unsafe client instructions.
    Error messages deliberately exclude the supplied value.
    """
    error = "HATUN_MCP_PUBLIC_BASE must be an HTTPS origin (HTTP only on loopback)"
    if not value or any(
        c.isspace() or ord(c) < 32 or ord(c) == 127 or c in '\\<>"\''
        for c in value
    ):
        raise ValueError(error)
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise ValueError(error) from None
    if (
        not host
        or parsed.netloc.endswith(":")
        or parsed.scheme not in {"http", "https"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or "?" in value
        or "#" in value
        or (port is not None and port == 0)
    ):
        raise ValueError(error)
    try:
        address = ipaddress.ip_address(host)
        loopback = address.is_loopback
        if "%" in host:  # Scoped IPv6 addresses are not public browser origins.
            raise ValueError(error)
    except ValueError:
        labels = host.removesuffix(".").split(".")
        if len(host) > 253 or any(
            not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
            for label in labels
        ):
            raise ValueError(error) from None
        loopback = host.lower() == "localhost"
    if parsed.scheme == "http" and not loopback:
        raise ValueError(error)
    authority = f"[{host.lower()}]" if ":" in host else host.lower()
    default_port = 443 if parsed.scheme == "https" else 80
    if port is not None and port != default_port:
        authority += f":{port}"
    return f"{parsed.scheme}://{authority}"


PUBLIC_BASE = public_base(
    os.environ.get("HATUN_MCP_PUBLIC_BASE", "http://127.0.0.1:7860")
)
