# Hatun-MCP — doctrine-aware MCP server (Streamable HTTP /mcp + legacy /sse)
# HF Space sdk=docker. Port 7860 is the HF Spaces convention.
# Doctrine v11 LOCKED — 749 / 14 / 163 — per-file COPY (no directory copies).
# SPDX-License-Identifier: Apache-2.0
FROM mirror.gcr.io/library/python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860 \
    HATUN_MCP_ALLOWED_ORIGINS="https://szlholdings-hatun-mcp.hf.space,https://smithery.ai,http://localhost"

WORKDIR /app

# Non-root user (HF Spaces best practice; least privilege)
RUN useradd -m -u 1000 hatun

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# ── Per-file COPY (Doctrine: explicit, auditable, no glob/dir copies) ───────────
COPY hatun_mcp/__init__.py        /app/hatun_mcp/__init__.py
COPY hatun_mcp/server.py          /app/hatun_mcp/server.py
COPY hatun_mcp/server_http.py     /app/hatun_mcp/server_http.py
COPY hatun_mcp/console.py         /app/hatun_mcp/console.py
COPY hatun_mcp/backends.py        /app/hatun_mcp/backends.py
COPY hatun_mcp/governance.py      /app/hatun_mcp/governance.py
COPY hatun_mcp/puriq.py           /app/hatun_mcp/puriq.py
COPY hatun_mcp/dsse.py            /app/hatun_mcp/dsse.py
COPY hatun_mcp/quorum.py          /app/hatun_mcp/quorum.py
COPY hatun_mcp/loop.py            /app/hatun_mcp/loop.py
COPY hatun_mcp/tools/__init__.py          /app/hatun_mcp/tools/__init__.py
COPY hatun_mcp/tools/governance_tools.py  /app/hatun_mcp/tools/governance_tools.py
COPY hatun_mcp/adapters/__init__.py    /app/hatun_mcp/adapters/__init__.py
COPY hatun_mcp/adapters/base.py        /app/hatun_mcp/adapters/base.py
COPY hatun_mcp/adapters/a11oy.py       /app/hatun_mcp/adapters/a11oy.py
COPY hatun_mcp/adapters/immune.py      /app/hatun_mcp/adapters/immune.py
COPY hatun_mcp/adapters/companion.py   /app/hatun_mcp/adapters/companion.py
COPY hatun_mcp/adapters/killinchu.py   /app/hatun_mcp/adapters/killinchu.py
COPY hatun_mcp/adapters/llm.py         /app/hatun_mcp/adapters/llm.py
COPY README.md                    /app/README.md

# The DSSE signing key is injected at runtime as a Space secret
# (HATUN_MCP_SIGNING_KEY, PEM contents). Never baked into the image.
USER hatun

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import json,urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:7860/healthz', timeout=2)); assert data['status']=='ok' and data['service']=='hatun-mcp'"

# uvicorn serves the Starlette gateway that mounts /mcp, /sse, /messages.
CMD ["sh", "-c", "uvicorn hatun_mcp.server_http:app --host 0.0.0.0 --port ${PORT:-7860}"]
