# Hatun-MCP — doctrine-aware MCP server (Streamable HTTP /mcp + legacy /sse)
# HF Space sdk=docker. Port 7860 is the HF Spaces convention.
# Doctrine v11 LOCKED — 749 / 14 / 163 — per-file COPY (no directory copies).
# SPDX-License-Identifier: Apache-2.0
FROM mirror.gcr.io/library/python:3.15-slim@sha256:e97b88e416c3c01eb427b21fd8cd3ebf006e6ee38afcfcc3cae1c54ee2ab0a75

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860

WORKDIR /app

# Non-root user (HF Spaces best practice; least privilege)
RUN useradd -m -u 1000 hatun

# Hash-pinned install: the same lock CI tests with (requirements/ci/runtime.txt,
# generated from requirements.txt). pip refuses any artifact whose hash differs.
COPY requirements/ci/runtime.txt /app/requirements.lock
RUN pip install --no-cache-dir --disable-pip-version-check --require-hashes -r /app/requirements.lock

# ── Per-file COPY (Doctrine: explicit, auditable, no glob/dir copies) ───────────
COPY hatun_mcp/__init__.py        /app/hatun_mcp/__init__.py
COPY hatun_mcp/formulas.py        /app/hatun_mcp/formulas.py
COPY hatun_mcp/server.py          /app/hatun_mcp/server.py
COPY hatun_mcp/server_http.py     /app/hatun_mcp/server_http.py
COPY hatun_mcp/deployment.py      /app/hatun_mcp/deployment.py
COPY hatun_mcp/payment_context.py /app/hatun_mcp/payment_context.py
COPY hatun_mcp/console.py         /app/hatun_mcp/console.py
COPY hatun_mcp/console_v2.py      /app/hatun_mcp/console_v2.py
COPY hatun_mcp/state.py           /app/hatun_mcp/state.py
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
COPY hatun_mcp/adapters/anatomy.py     /app/hatun_mcp/adapters/anatomy.py
COPY hatun_mcp/adapters/second_brain.py /app/hatun_mcp/adapters/second_brain.py
COPY README.md                    /app/README.md

# The DSSE signing key is injected at runtime as a Space secret
# (HATUN_MCP_SIGNING_KEY, PEM contents). Never baked into the image.
# The exact source commit is not secret: CI passes it so /api/build-info can
# report it. Without the build argument the route honestly reports UNAVAILABLE.
ARG SZL_GIT_SHA=""
ENV SZL_GIT_SHA=${SZL_GIT_SHA}
USER hatun

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import json,urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:7860/healthz', timeout=2)); assert data['status']=='ok' and data['service']=='hatun-mcp'"

# uvicorn serves the Starlette gateway that mounts /mcp, /sse, /messages.
CMD ["sh", "-c", "uvicorn hatun_mcp.server_http:app --host 0.0.0.0 --port ${PORT:-7860}"]
