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
2. `HF_SPACE=<user>/quantumsar ./deploy/huggingface/push_space.sh`

The script copies the repo, uses `deploy/huggingface/README.md` as the Space card (`app_port: 7860`)
and tracks `.npz`/`.png` with Git LFS. The container serves the React UI and the API from one uvicorn
process on `$PORT` (`scripts/start.sh`).

## Render (free web service)

Create a *Blueprint* from the repo; `render.yaml` defines one Docker web service with health check
`/health`. Render injects `$PORT`, which `scripts/start.sh` passes to uvicorn.

## Environment variables

| variable | default | |
|---|---|---|
| `PORT` | 7860 | UI + API port |
| `QUANTUMSAR_ALLOW_LIVE_CLASSIQ` | 0 | 1 = run Classiq live when credentials work |
| `QUANTUMSAR_DISABLE_CLASSIQ` | 0 | 1 = never try Classiq |
| `QUANTUMSAR_FALLBACK` | `qaoa_local` | or `annealing` |
| `QUANTUMSAR_API_URL` | (unset) | UI talks to this API instead of running in-process |
| `CLASSIQ_CLIENT_ID` / `CLASSIQ_CLIENT_SECRET` | (unset) | Classiq M2M auth (host secrets only) |

## CI

`.github/workflows/ci.yml`: `pytest` (live Classiq tests skipped without credentials), `npm ci && npm run
build` for the React UI, then a Docker build with a `/health` + UI smoke test.
