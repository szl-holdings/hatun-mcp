# Hatun-MCP — doctrine-aware MCP server (Streamable HTTP /mcp + legacy /sse)
# HF Space sdk=docker. Port 7860 is the HF Spaces convention.
# SPDX-License-Identifier: Apache-2.0
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860 \
    HATUN_MCP_ALLOWED_ORIGINS="https://szlholdings-hatun-mcp.hf.space,https://smithery.ai,http://localhost"

WORKDIR /app

# Non-root user (HF Spaces best practice; least privilege)
RUN useradd -m -u 1000 hatun

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY hatun_mcp /app/hatun_mcp
COPY README.md /app/README.md

# The DSSE signing key is injected at runtime as a Space secret
# (HATUN_MCP_SIGNING_KEY, PEM contents). Never baked into the image.
USER hatun

EXPOSE 7860

# uvicorn serves the Starlette gateway that mounts /mcp, /sse, /messages.
CMD ["sh", "-c", "uvicorn hatun_mcp.server_http:app --host 0.0.0.0 --port ${PORT:-7860}"]
