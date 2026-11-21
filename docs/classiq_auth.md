# Classiq authentication

Classiq offers two flows (see docs.classiq.io → *SDK authentication*):

| flow | how | where to use |
|---|---|---|
| Interactive device login | `classiq.authenticate()` opens a browser once; refresh tokens are cached locally | local development |
| Machine-to-machine (M2M) | env vars `CLASSIQ_CLIENT_ID`, `CLASSIQ_CLIENT_SECRET` (optional `CLASSIQ_ORG_ID`); no browser, tokens kept in memory | servers / CI; M2M clients are provisioned by Classiq, not self-service |

## Local development (Windows)

```powershell
python -m pip install keyrings.alt
python -c "from quantumsar.auth import setup_classiq_auth; setup_classiq_auth(); import classiq; classiq.authenticate()"
```

`src/quantumsar/auth.py` implements the documented Windows workaround for
`(1783, 'CredWrite', 'The stub received bad data.')`: it switches `keyring` to
`keyrings.alt.file.PlaintextKeyring` **before** `classiq` is imported and copies `config.env` (if present)
to `%APPDATA%\classiq\config.env`. The plaintext keyring stores tokens unencrypted in your profile: use it
only on a personal machine.

`config.env` / `.env` are git-ignored; copy `.env.example` to create one. Never commit credentials.

## Deployment: live Classiq on a headless server

A deployed server cannot open a browser. Two ways to give it Classiq access:

**A. Dedicated deployment login (works today, no Classiq agreement needed)**

```bash
python scripts/create_deploy_credentials.py --check-rotation
```

1. Approve the Classiq device login that opens in your browser (a login used *only* by the server,
   kept in the git-ignored `deploy/.classiq_deploy_keyring.cfg`, separate from your own login).
2. The script verifies it with a test synthesis, checks token rotation (Classiq refresh tokens did
   **not** rotate when tested, so the secret survives server restarts), and writes the git-ignored
   `deploy/classiq_deploy.env` with one value, `CLASSIQ_DEPLOY_CREDENTIALS`.
3. On the host, add `CLASSIQ_DEPLOY_CREDENTIALS` as a **secret** and `QUANTUMSAR_ALLOW_LIVE_CLASSIQ=1`
   as a variable. At startup `quantumsar.auth.install_deploy_credentials()` seeds the plaintext keyring
   the Classiq SDK reads (`classiqTokenService`); the SDK refreshes the access token by itself.

The secret gives access to *your* Classiq account: keep it in the host's secret store only (it is
excluded by `.gitignore`, `.dockerignore` and the Hugging Face push script). Live jobs run one at a
time; at most `QUANTUMSAR_MAX_QUEUE` (default 4) can wait, protecting your quota. To revoke it, sign out
of that session / rotate your Classiq credentials and re-run the script.

**B. Machine-to-machine (M2M)**: if Classiq provisions an M2M client for you, set
`CLASSIQ_CLIENT_ID` / `CLASSIQ_CLIENT_SECRET` (optional `CLASSIQ_ORG_ID`) as secrets instead; the SDK
uses them automatically.

### What users see

* Results already computed on Classiq (bundled samples via `scripts/precompute_quantum.py`, or earlier
  live runs) are served instantly: badge **CLASSIQ · CACHED RUN**, runtime = original Classiq run time.
* Anything else runs **live**: `POST /jobs` queues a background job, the UI polls `GET /jobs/{id}` and
  shows a progress bar (~2–4 minutes per 64×64 image); badge **LIVE ON CLASSIQ**. The result is then
  stored, so the same request is instant next time.
* Synthesized circuits for every tile shape ship in `results/classiq_programs/`
  (`scripts/synthesize_programs.py`), so a fresh server executes without re-synthesizing.
* Without credentials (or `QUANTUMSAR_ALLOW_LIVE_CLASSIQ=0`) the same QAOA circuit runs on the local
  statevector simulator, labelled **FALLBACK** with the reason.
