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

## Deployment

Free hosts (Hugging Face Spaces, Render) cannot complete a browser login, and M2M credentials require a
Classiq agreement. The deployed app therefore:

* sets `QUANTUMSAR_ALLOW_LIVE_CLASSIQ=0` by default;
* serves **precomputed Classiq results** for the bundled samples from `results/quantum_cache/`
  (produced with `python scripts/precompute_quantum.py`, which records Classiq SDK version, timestamp,
  runtime and circuit metrics in each entry);
* for any other image / setting, runs the **same QAOA circuit on the local statevector simulator** and
  labels the result `FALLBACK` in the UI and API.

With M2M credentials, set `CLASSIQ_CLIENT_ID` / `CLASSIQ_CLIENT_SECRET` as host secrets and
`QUANTUMSAR_ALLOW_LIVE_CLASSIQ=1` to enable live runs (expect ~2–4 minutes per 64×64 image).
