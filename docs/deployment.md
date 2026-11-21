# Deployment

## Local, one command

```bash
docker compose up --build
```

* `app`: one container; a Node build stage compiles the React UI, and FastAPI serves UI + API on port 7860
  (Docker healthcheck on `/health`)
* `streamlit` (optional profile): the classic Streamlit UI on 8501, calling the API

Optional `config.env` (git-ignored) is passed to the API container for Classiq M2M credentials.

## Hugging Face Spaces (free, Docker SDK)

1. Create a Space with SDK **Docker** (e.g. `<user>/quantumsar`) and `huggingface-cli login`.
2. Live Classiq: run `python scripts/create_deploy_credentials.py` once, then in the Space
   **Settings → Variables and secrets** add the *secret* `CLASSIQ_DEPLOY_CREDENTIALS` (value from
   `deploy/classiq_deploy.env`) and the *variable* `QUANTUMSAR_ALLOW_LIVE_CLASSIQ=1`.
   See [classiq_auth.md](classiq_auth.md).
3. `HF_SPACE=<user>/quantumsar ./deploy/huggingface/push_space.sh`
4. Open the Space: the controls card shows "Classiq connected: live quantum runs enabled".

The script copies the repo, uses `deploy/huggingface/README.md` as the Space card (`app_port: 7860`)
and tracks `.npz`/`.png` with Git LFS. The container serves the React UI and the API from one uvicorn
process on `$PORT` (`scripts/start.sh`).

## Render (free web service)

Create a *Blueprint* from the repo; `render.yaml` defines one Docker web service with health check
`/health` and live Classiq enabled; Render asks for the `CLASSIQ_DEPLOY_CREDENTIALS` secret value when
you create it. Render injects `$PORT`, which `scripts/start.sh` passes to uvicorn.

## Environment variables

| variable | default | |
|---|---|---|
| `PORT` | 7860 | UI + API port |
| `QUANTUMSAR_ALLOW_LIVE_CLASSIQ` | 0 | 1 = run Classiq live (background jobs) when credentials work |
| `CLASSIQ_DEPLOY_CREDENTIALS` | (unset) | **secret** from `scripts/create_deploy_credentials.py` |
| `QUANTUMSAR_MAX_QUEUE` | 4 | max queued + running live Classiq jobs (HTTP 429 beyond) |
| `QUANTUMSAR_DISABLE_CLASSIQ` | 0 | 1 = never try Classiq |
| `QUANTUMSAR_FALLBACK` | `qaoa_local` | or `annealing` |
| `QUANTUMSAR_API_URL` | (unset) | UI talks to this API instead of running in-process |
| `CLASSIQ_CLIENT_ID` / `CLASSIQ_CLIENT_SECRET` | (unset) | Classiq M2M auth (host secrets only) |

## CI

`.github/workflows/ci.yml`: `pytest` (live Classiq tests skipped without credentials), `npm ci && npm run
build` for the React UI, then a Docker build with a `/health` + UI smoke test.
