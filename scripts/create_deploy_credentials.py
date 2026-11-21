"""Create a DEDICATED Classiq login for a deployed QuantumSAR server.

    python scripts/create_deploy_credentials.py

1. Opens Classiq's device login in your browser (approve it once).
2. Stores the tokens in a separate, git-ignored keyring file
   (deploy/.classiq_deploy_keyring.cfg) so your personal login on this laptop
   is never shared with the server (refresh tokens can rotate).
3. Verifies the login with a tiny synthesis on Classiq.
4. Optionally checks whether refresh tokens rotate (compares hashes only).
5. Writes deploy/classiq_deploy.env containing ONE secret:
       CLASSIQ_DEPLOY_CREDENTIALS=<base64>
   Paste that value into your host's *secret* settings (Hugging Face Space ->
   Settings -> Variables and secrets -> New secret; Render -> Environment ->
   Secret). Also set QUANTUMSAR_ALLOW_LIVE_CLASSIQ=1.

Never commit deploy/classiq_deploy.env or the keyring file (both git-ignored).
Anyone with this secret can run jobs on your Classiq account.
"""
import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
DEPLOY_DIR = ROOT / "deploy"
KEYRING_FILE = DEPLOY_DIR / ".classiq_deploy_keyring.cfg"
OUT = DEPLOY_DIR / "classiq_deploy.env"

from quantumsar.auth import (  # noqa: E402
    DEPLOY_ENV, _ACCESS_KEY, _REFRESH_KEY, _SERVICE, _use_plaintext_keyring, encode_deploy_credentials)


def h(s: str | None) -> str:
    return hashlib.sha256((s or "").encode()).hexdigest()[:10]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-rotation", action="store_true",
                    help="force one token refresh and report whether the refresh token changes")
    a = ap.parse_args()

    DEPLOY_DIR.mkdir(exist_ok=True)
    kr = _use_plaintext_keyring(KEYRING_FILE)   # must happen before `import classiq`
    import classiq

    if not kr.get_password(_SERVICE, _REFRESH_KEY):
        print("Opening Classiq login in your browser - approve the device login...", flush=True)
        classiq.authenticate()
    else:
        print(f"Using existing deploy login in {KEYRING_FILE}")

    from classiq import H, Output, QBit, allocate, qfunc, synthesize

    @qfunc
    def main(q: Output[QBit]):  # Classiq's entry point must be called `main`
        allocate(q)
        H(q)

    synthesize(main)
    print("Login verified: a test circuit was synthesized on Classiq.")

    if a.check_rotation:
        from classiq._internals.client import client

        before = kr.get_password(_SERVICE, _REFRESH_KEY)
        asyncio.run(client().update_expired_access_token())
        after = kr.get_password(_SERVICE, _REFRESH_KEY)
        rotated = h(before) != h(after)
        print(f"refresh token rotates on refresh: {'YES' if rotated else 'no'} "
              f"(hash {h(before)} -> {h(after)})")
        if rotated:
            print("  -> the server keeps refreshed tokens in its keyring file while it runs; after a "
                  "container restart, re-run this script and update the secret (or use Classiq M2M).")

    secret = encode_deploy_credentials(kr.get_password(_SERVICE, _ACCESS_KEY), kr.get_password(_SERVICE, _REFRESH_KEY))
    OUT.write_text(f"# QuantumSAR deployment secret - DO NOT COMMIT\n{DEPLOY_ENV}={secret}\n"
                   f"QUANTUMSAR_ALLOW_LIVE_CLASSIQ=1\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(ROOT)} (git-ignored).")
    print(f"Add {DEPLOY_ENV} as a SECRET on your host, and QUANTUMSAR_ALLOW_LIVE_CLASSIQ=1 as a variable.")


if __name__ == "__main__":
    main()
