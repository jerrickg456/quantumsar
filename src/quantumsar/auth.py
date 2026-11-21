"""Classiq authentication helper (LOCAL DEVELOPMENT ONLY).

Classiq supports two authentication flows (docs.classiq.io, "SDK authentication"):

1. Interactive device flow: ``classiq.authenticate()`` opens a browser once and
   caches refresh tokens locally (OS keyring).
2. Machine-to-machine (headless): set ``CLASSIQ_CLIENT_ID`` and
   ``CLASSIQ_CLIENT_SECRET`` (optional ``CLASSIQ_ORG_ID``). M2M clients are
   provisioned by Classiq, not self-service.

Windows pitfall: the default Windows Credential Manager backend can fail with
``(1783, 'CredWrite', 'The stub received bad data.')`` because the tokens are
too large. Workaround (documented by Classiq): use the plaintext file keyring
from ``keyrings.alt`` **before importing classiq**, and keep a copy of your
``config.env`` in ``%APPDATA%\\classiq\\config.env``.

``PlaintextKeyring`` stores tokens unencrypted in your user profile; never use
it on shared machines and never commit ``config.env``.

Usage::

    from quantumsar.auth import setup_classiq_auth
    status = setup_classiq_auth()          # call BEFORE `import classiq`
"""

import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_env_file(path: str | Path | None = None) -> dict:
    """Minimal KEY=VALUE loader for config.env / .env (no dependency)."""
    loaded = {}
    candidates = [Path(path)] if path else [REPO_ROOT / "config.env", REPO_ROOT / ".env"]
    for p in candidates:
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)
                loaded[k] = "***"
    return loaded


def _windows_workaround(config_env: Path | None) -> list[str]:
    notes = []
    appdata = os.environ.get("APPDATA")
    if config_env and config_env.is_file() and appdata:
        dst = Path(appdata) / "classiq" / "config.env"
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(config_env, dst)
            notes.append(f"copied config.env -> {dst}")
    try:
        import keyring
        from keyrings.alt.file import PlaintextKeyring

        keyring.set_keyring(PlaintextKeyring())
        notes.append("keyring backend: keyrings.alt PlaintextKeyring")
    except ImportError:
        notes.append("keyrings.alt not installed (pip install keyrings.alt)")
    return notes


def setup_classiq_auth(config_env: str | Path | None = None, windows_workaround: bool | None = None) -> dict:
    """Prepare the environment so ``import classiq`` can find credentials."""
    if "classiq" in sys.modules:
        notes = ["warning: classiq already imported; keyring change may not apply"]
    else:
        notes = []
    cfg = Path(config_env) if config_env else REPO_ROOT / "config.env"
    loaded = load_env_file(cfg if cfg.is_file() else None)
    if windows_workaround is None:
        windows_workaround = sys.platform.startswith("win")
    m2m = bool(os.environ.get("CLASSIQ_CLIENT_ID") and os.environ.get("CLASSIQ_CLIENT_SECRET"))
    deploy = bool(os.environ.get(DEPLOY_ENV)) and not m2m
    if deploy:
        notes += install_deploy_credentials()
    elif windows_workaround:
        notes += _windows_workaround(cfg if cfg.is_file() else None)
    return {"env_keys": sorted(loaded), "m2m": m2m, "deploy_credentials": deploy, "notes": notes}


# --------------------------------------------------------------------- deployment
# Headless servers (Hugging Face Spaces, Render, Docker) cannot open a browser.
# `scripts/create_deploy_credentials.py` performs ONE dedicated device login and
# packs the resulting Classiq tokens into a single secret, CLASSIQ_DEPLOY_CREDENTIALS
# (base64 JSON). At startup we seed the plaintext keyring that the Classiq SDK
# reads (`classiqTokenService`), so `import classiq` finds the tokens and refreshes
# them by itself. Tokens refreshed while the server runs are kept in that keyring
# file; the env secret is only used when the file is empty (fresh container).

DEPLOY_ENV = "CLASSIQ_DEPLOY_CREDENTIALS"
_SERVICE = "classiqTokenService"
_ACCESS_KEY = "classiqTokenAccount"
_REFRESH_KEY = "classiqRefershTokenAccount"  # (sic) the SDK's own spelling


def _keyring_path() -> Path:
    base = os.environ.get("CLASSIQ_DIR") or os.environ.get("HOME") or os.environ.get("TMPDIR") or "/tmp"
    return Path(base) / ".quantumsar_classiq_keyring.cfg"


def _use_plaintext_keyring(path: Path):
    import keyring
    from keyrings.alt.file import PlaintextKeyring

    kr = PlaintextKeyring()
    kr.file_path = str(path)
    keyring.set_keyring(kr)
    return kr


def encode_deploy_credentials(access_token: str | None, refresh_token: str) -> str:
    import base64
    import json

    blob = json.dumps({"access": access_token, "refresh": refresh_token}).encode()
    return base64.b64encode(blob).decode()


def install_deploy_credentials() -> list[str]:
    import base64
    import json

    raw = os.environ.get(DEPLOY_ENV, "").strip()
    try:
        creds = json.loads(base64.b64decode(raw))
        refresh = creds["refresh"]
    except Exception:  # noqa: BLE001
        return [f"{DEPLOY_ENV} is set but could not be decoded"]
    path = _keyring_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    kr = _use_plaintext_keyring(path)
    if kr.get_password(_SERVICE, _REFRESH_KEY):
        return [f"Classiq tokens already present in {path} (kept: they may be newer)"]
    kr.set_password(_SERVICE, _REFRESH_KEY, refresh)
    if creds.get("access"):
        kr.set_password(_SERVICE, _ACCESS_KEY, creds["access"])
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return [f"Classiq deploy credentials installed into {path}"]


def classiq_ready(timeout_s: float = 60.0) -> tuple[bool, str]:
    """Try a tiny synthesis to check that Classiq works without prompting.

    Returns (ok, message). Never opens a browser: if no cached tokens/M2M
    credentials exist we report unavailability instead of blocking.
    """
    if os.environ.get("QUANTUMSAR_DISABLE_CLASSIQ") == "1":
        return False, "disabled by QUANTUMSAR_DISABLE_CLASSIQ=1"
    try:
        setup_classiq_auth()
        import concurrent.futures as cf

        def probe():
            from classiq import Output, QBit, allocate, qfunc, synthesize, H

            @qfunc
            def main(q: Output[QBit]):
                allocate(q)
                H(q)

            synthesize(main)

        ex = cf.ThreadPoolExecutor(1)
        try:
            ex.submit(probe).result(timeout=timeout_s)
        finally:
            ex.shutdown(wait=False)  # don't block on an interactive login prompt
        return True, "Classiq authenticated"
    except Exception as e:  # noqa: BLE001
        return False, f"Classiq unavailable: {type(e).__name__}: {str(e)[:200]}"


if __name__ == "__main__":
    print(setup_classiq_auth())
    print(classiq_ready())
