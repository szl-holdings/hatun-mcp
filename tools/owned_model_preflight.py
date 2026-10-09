#!/usr/bin/env python3
"""Read-only, fail-closed SZL owned-model Hugging Face preflight.

Checks repository metadata without running inference, downloading weights, or
printing credentials. Intended for operators before enabling Hatun llm_chat.
Python 3.10+; standard library only.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

MODEL_IDS = (
    "SZLHOLDINGS/SZL-Khipu-1.5B",
    "SZLHOLDINGS/chaski",
    "SZLHOLDINGS/WILLAY",
    "SZLHOLDINGS/brain-navigator-r2",
    "SZLHOLDINGS/szl-triage-qwen3.5-0.8b-lora-study5",
    "SZLHOLDINGS/A11OY-MINI",
    "SZLHOLDINGS/MiniEmbed-Nano",
)

def inspect(model_id: str, token: str | None = None, timeout: int = 12) -> dict:
    if model_id not in MODEL_IDS:
        raise ValueError("Model is not in the source-bound registry")
    url = "https://huggingface.co/api/models/" + "/".join(
        urllib.parse.quote(part, safe="") for part in model_id.split("/")
    )
    headers = {"User-Agent": "szl-owned-model-preflight/1", "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = json.load(response)
        if not isinstance(body, dict) or body.get("id") != model_id:
            return {"id": model_id, "status": "UNKNOWN", "reason": "identity_mismatch"}
        sha = body.get("sha")
        return {
            "id": model_id, "status": "METADATA_ONLY" if isinstance(sha, str) and len(sha) == 40 else "UNKNOWN",
            "revision": sha if isinstance(sha, str) and len(sha) == 40 else None,
            "private": body.get("private") if isinstance(body.get("private"), bool) else None,
            "pipeline_tag": body.get("pipeline_tag"),
            "gated": body.get("gated"),
            "reason": "not_inference_proof",
        }
    except urllib.error.HTTPError as exc:
        # No provider response body: it may include private account details.
        return {"id": model_id, "status": "UNKNOWN", "reason": "http_error", "http_status": exc.code}
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return {"id": model_id, "status": "UNKNOWN", "reason": type(exc).__name__}

def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="owned-model-preflight.json")
    p.add_argument("--timeout", type=int, default=12)
    args = p.parse_args(argv)
    if not 1 <= args.timeout <= 60:
        p.error("--timeout must be between 1 and 60")
    token = os.environ.get("HF_TOKEN")
    models = [inspect(model, token=token, timeout=args.timeout) for model in MODEL_IDS]
    result = {
        "schema": "szl.owned-model-preflight/v1",
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "models": models,
        "metadata_complete": all(m["status"] == "METADATA_ONLY" for m in models),
        "inference_verified": False,
        "production_qualified": False,
    }
    with open(args.output, "w", encoding="utf-8") as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")
    print(json.dumps({"metadata_complete": result["metadata_complete"],
                      "checked": len(models), "unknown": sum(m["status"] == "UNKNOWN" for m in models),
                      "inference_verified": False}))
    return 0 if result["metadata_complete"] else 2

if __name__ == "__main__":
    sys.exit(main())
