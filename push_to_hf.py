"""Push Hatun-MCP source to SZLHOLDINGS/hatun-mcp Space via founder-token HfApi."""
from pathlib import Path
from huggingface_hub import HfApi

tok = Path("/home/user/workspace/szl/audit_2026-05-30_cursor_offline/.secret/hf_token").read_text().strip()
api = HfApi(token=tok)
repo = "SZLHOLDINGS/hatun-mcp"

commit = api.upload_folder(
    repo_id=repo,
    repo_type="space",
    folder_path="/home/user/workspace/szl_hatun_mcp",
    commit_message="Hatun-MCP v1.0.0 — doctrine-aware MCP server (25 static tools: 19 szl_* + "
                   "6 governance; PURIQ governance, Khipu receipts, DSSE-signed; "
                   "v11 LOCKED 749/14/163). Real MCP protocol.",
    ignore_patterns=[
        ".git/*", ".git", "**/.git/**",
        ".pytest_cache/*", "**/__pycache__/**", "*.pyc",
        ".keys_DO_NOT_COMMIT.pem", ".secret/*", ".env", "*.log",
        "push_to_hf.py",
    ],
    allow_patterns=None,
)
print("commit:", commit)
info = api.space_info(repo)
print("space sha:", info.sha)
print("runtime stage:", getattr(getattr(info, "runtime", None), "stage", None))
