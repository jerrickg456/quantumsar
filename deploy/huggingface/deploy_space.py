"""Deploy QuantumSAR to a Hugging Face Docker Space (no git / rsync needed).

    hf auth login                                   # once, with a WRITE token
    python deploy/huggingface/deploy_space.py       # -> https://huggingface.co/spaces/<you>/quantumsar

Options: --space NAME (default quantumsar), --private, --no-live (skip the Classiq secret).

* Creates (or reuses) the Space with the Docker SDK.
* Live Classiq: reads CLASSIQ_DEPLOY_CREDENTIALS from the git-ignored
  deploy/classiq_deploy.env (see scripts/create_deploy_credentials.py) and stores it
  as a Space SECRET (never printed, never uploaded as a file); sets the variable
  QUANTUMSAR_ALLOW_LIVE_CLASSIQ=1.
* Uploads the project, excluding secrets, virtualenvs, build outputs and the video.
"""
import argparse
import sys
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[2]
SECRET_FILE = ROOT / "deploy" / "classiq_deploy.env"
IGNORE = [
    ".git/*", ".git/**", ".venv/**", "**/node_modules/**", "frontend/dist/**", "**/__pycache__/**",
    ".pytest_cache/**", "**/.ipynb_checkpoints/**", "video/build/**", "video/out/**", "video/build_app.log",
    # secrets - never upload
    "config.env", ".env", "deploy/classiq_deploy.env", "deploy/.classiq_deploy_keyring.cfg", "**/*keyring*.cfg",
    "README.md",  # replaced by the Space card below
]


def read_secret() -> str:
    for line in SECRET_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("CLASSIQ_DEPLOY_CREDENTIALS="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"CLASSIQ_DEPLOY_CREDENTIALS not found in {SECRET_FILE}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", default="quantumsar")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--no-live", action="store_true")
    a = ap.parse_args()

    api = HfApi()
    user = api.whoami()["name"]
    repo_id = f"{user}/{a.space}"
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=a.private, exist_ok=True)
    print(f"Space ready: {repo_id} ({'private' if a.private else 'public'})")

    if a.no_live:
        api.add_space_variable(repo_id, "QUANTUMSAR_ALLOW_LIVE_CLASSIQ", "0")
        print("live Classiq: off (stored Classiq results + labelled local fallback)")
    else:
        if not SECRET_FILE.is_file():
            sys.exit("missing deploy/classiq_deploy.env - run: python scripts/create_deploy_credentials.py")
        api.add_space_secret(repo_id, "CLASSIQ_DEPLOY_CREDENTIALS", read_secret(),
                             description="Classiq login for live QAOA runs (scripts/create_deploy_credentials.py)")
        api.add_space_variable(repo_id, "QUANTUMSAR_ALLOW_LIVE_CLASSIQ", "1")
        print("live Classiq: on (secret CLASSIQ_DEPLOY_CREDENTIALS set, value not shown)")

    api.upload_folder(folder_path=str(ROOT), repo_id=repo_id, repo_type="space", ignore_patterns=IGNORE,
                      commit_message="Deploy QuantumSAR")
    api.upload_file(path_or_fileobj=str(ROOT / "deploy" / "huggingface" / "README.md"), path_in_repo="README.md",
                    repo_id=repo_id, repo_type="space", commit_message="Space card")
    print(f"\nDeployed. Build logs + app: https://huggingface.co/spaces/{repo_id}")
    print(f"Direct app URL (after the build): https://{user}-{a.space}.hf.space".replace("_", "-").lower())


if __name__ == "__main__":
    main()
