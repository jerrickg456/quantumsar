"""QuantumSAR REST API.

    uvicorn api.main:app --port 8000

Endpoints
---------
GET  /health                 liveness + Classiq status
GET  /solvers                available solvers
GET  /samples                bundled sample names
GET  /samples/{name}         sample image (+ ground truth) as arrays
POST /segment                segment a sample or an uploaded image
POST /edges                  segment + edge map
POST /benchmark              run several solvers; ?format=csv for CSV
"""
from __future__ import annotations

import base64
import io
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Classiq credentials must be in place BEFORE `classiq` is imported anywhere.
from quantumsar.auth import setup_classiq_auth  # noqa: E402

AUTH_SETUP = setup_classiq_auth()

from quantumsar import __version__  # noqa: E402
from quantumsar.data import list_samples, load_sample, to_uint8  # noqa: E402
from quantumsar.pipeline import (  # noqa: E402
    SOLVERS, SegParams, _classiq_live_ok, benchmark, classiq_status, load_cached_quantum, save_cached_quantum, segment)

DATA_DIR = Path(os.environ.get("QUANTUMSAR_DATA", ROOT / "data"))
ALLOW_LIVE = os.environ.get("QUANTUMSAR_ALLOW_LIVE_CLASSIQ", "0") == "1"
MAX_QUEUE = int(os.environ.get("QUANTUMSAR_MAX_QUEUE", "4"))

app = FastAPI(title="QuantumSAR API", version=__version__,
              description="MRF segmentation of SAR images with QAOA (Classiq) and classical baselines.")


class Params(BaseModel):
    solver: str = "classiq"
    n_classes: int = Field(2, ge=2, le=3)
    lam: float = Field(1.5, ge=0, le=20)
    looks: float | None = None
    tile: int = Field(3, ge=1, le=5)
    sweeps: int = Field(2, ge=1, le=6)
    p: int = Field(2, ge=1, le=6)
    shots: int = Field(1024, ge=16, le=20000)
    maxiter: int = Field(30, ge=0, le=300)
    margin: float | None = 3.0
    multires: bool = True
    seed: int = 0


class SegmentRequest(BaseModel):
    sample: str | None = None
    image_b64: str | None = Field(None, description="base64 PNG/JPEG or .npy (2-D intensity)")
    params: Params = Params()
    edges: bool = False
    single_edges: bool = True


class BenchmarkRequest(BaseModel):
    sample: str | None = None
    image_b64: str | None = None
    params: Params = Params()
    solvers: list[str] | None = None


def _decode_image(b64: str) -> np.ndarray:
    raw = base64.b64decode(b64)
    if raw[:6] == b"\x93NUMPY":
        img = np.load(io.BytesIO(raw))
    else:
        from PIL import Image

        img = np.asarray(Image.open(io.BytesIO(raw)).convert("F"), dtype=np.float32)
    if img.ndim == 3:                      # e.g. an RGB .npy -> grayscale
        img = img.mean(axis=2)
    if img.ndim != 2:
        raise HTTPException(400, "image must be a 2-D grayscale array or an image file")
    return np.maximum(_fit_size(img.astype(np.float32)), 1e-3)


MAX_SIDE = 128


def _fit_size(img: np.ndarray) -> np.ndarray:
    """Shrink large uploads by integer block-averaging (a multi-look average, which
    keeps SAR speckle statistics sensible) so the longest side is <= MAX_SIDE."""
    f = int(np.ceil(max(img.shape) / MAX_SIDE))
    if f > 1:
        h, w = (img.shape[0] // f) * f, (img.shape[1] // f) * f
        img = img[:h, :w].reshape(h // f, f, w // f, f).mean(axis=(1, 3))
    return img


def _get_image(sample: str | None, b64: str | None):
    if b64:
        return _decode_image(b64), None
    if not sample:
        raise HTTPException(400, "provide 'sample' or 'image_b64'")
    try:
        return load_sample(DATA_DIR, sample)
    except FileNotFoundError:
        raise HTTPException(404, f"unknown sample {sample!r}")


def _prm(p: Params) -> SegParams:
    if p.solver not in SOLVERS:
        raise HTTPException(400, f"unknown solver {p.solver!r}; choose from {list(SOLVERS)}")
    return SegParams(**p.model_dump(), allow_live_classiq=ALLOW_LIVE)


def _jsonable(res: dict) -> dict:
    out = {}
    for k, v in res.items():
        if isinstance(v, np.ndarray):
            out[k] = v.tolist()
        elif isinstance(v, dict):
            out[k] = _jsonable(v)
        elif isinstance(v, (np.floating, np.integer)):
            out[k] = v.item()
        else:
            out[k] = v
    return out


@app.on_event("startup")
def _probe_classiq():
    """Check the Classiq login in the background so /health can report it."""
    if ALLOW_LIVE:
        threading.Thread(target=_classiq_live_ok, daemon=True).start()


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__, "samples": len(list_samples(DATA_DIR)),
            "live_classiq_enabled": ALLOW_LIVE, "classiq": classiq_status(),
            "auth": {k: AUTH_SETUP[k] for k in ("m2m", "deploy_credentials")},
            "jobs_active": sum(j["status"] in ("queued", "running") for j in JOBS.values())}


# ----------------------------------------------------------------------------- async jobs
# Live Classiq runs take minutes, longer than typical proxy timeouts on free hosts.
# POST /jobs queues a segmentation; GET /jobs/{id} reports progress and the result.
# One worker => Classiq jobs run one at a time (protects the account's quota).
JOBS: dict[str, dict] = {}
_WORKER = ThreadPoolExecutor(max_workers=1)
_LOCK = threading.Lock()


def _public(job: dict, with_result: bool = True) -> dict:
    out = {k: v for k, v in job.items() if k != "result" or with_result}
    if job["status"] == "queued":
        ahead = [j for j in JOBS.values() if j["status"] in ("queued", "running") and j["created"] < job["created"]]
        out["queue_position"] = len(ahead)
    if job.get("started"):
        out["elapsed_s"] = round((job.get("finished") or time.time()) - job["started"], 1)
    return out


def _run_job(jid: str, img, gt, prm: SegParams, edges: bool, single: bool):
    job = JOBS[jid]
    job.update(status="running", started=time.time(), stage="fitting MRF model")

    def progress(frac: float, msg: str):
        job.update(progress=round(min(max(frac, 0.0), 0.99), 3), stage=msg)

    try:
        res = segment(img, prm, gt, edges=edges, single_edges=single, progress=progress)
        res["display"] = to_uint8(img)
        if "live" in res["mode"]:  # remember live Classiq runs: identical requests become instant
            import classiq

            meta = {"mode": res["mode"], "runtime_s": res["runtime_s"], "energy": res["energy"],
                    "classiq_version": classiq.__version__, "tiling": res["info"],
                    "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            save_cached_quantum(img, prm, res["labels"], meta)
        job.update(status="done", progress=1.0, stage="done", finished=time.time(), result=_jsonable(res))
    except Exception as e:  # noqa: BLE001
        job.update(status="error", stage="failed", finished=time.time(), error=f"{type(e).__name__}: {e}"[:400])


@app.post("/jobs", status_code=202)
def create_job(req: SegmentRequest):
    img, gt = _get_image(req.sample, req.image_b64)
    prm = _prm(req.params)
    with _LOCK:
        now = time.time()
        for k in [k for k, j in JOBS.items() if j.get("finished") and now - j["finished"] > 3600]:
            JOBS.pop(k)  # forget results after an hour
        if sum(j["status"] in ("queued", "running") for j in JOBS.values()) >= MAX_QUEUE:
            raise HTTPException(429, "the Classiq queue is full, please try again in a few minutes")
        jid = uuid.uuid4().hex[:12]
        JOBS[jid] = {"id": jid, "status": "queued", "progress": 0.0, "stage": "queued", "created": now,
                     "solver": prm.solver, "live": prm.allow_live_classiq}
    _WORKER.submit(_run_job, jid, img, gt, prm, req.edges, req.single_edges)
    return _public(JOBS[jid])


@app.get("/jobs/{jid}")
def get_job(jid: str):
    if jid not in JOBS:
        raise HTTPException(404, "unknown or expired job")
    return _public(JOBS[jid])


@app.get("/solvers")
def solvers():
    return {k: {"name": v[0], "kind": v[1]} for k, v in SOLVERS.items()}


@app.get("/samples")
def samples():
    return list_samples(DATA_DIR)


@app.get("/samples/{name:path}")
def sample(name: str):
    img, gt = _get_image(name, None)
    return {"name": name, "image": img.tolist(), "display": to_uint8(img).tolist(),
            "labels": None if gt is None else gt.tolist()}


@app.post("/cache-status")
def cache_status(req: SegmentRequest):
    """Is there a precomputed Classiq result for this image + parameters?"""
    img, _ = _get_image(req.sample, req.image_b64)
    prm = SegParams(**{**req.params.model_dump(), "solver": "classiq"})
    hit = load_cached_quantum(img, prm)
    return {"cached": hit is not None, "live_enabled": ALLOW_LIVE,
            "meta": None if hit is None else {k: hit[1].get(k) for k in ("created", "classiq_version", "runtime_s")}}


@app.get("/results/summary")
def results_summary():
    """Dataset-wide benchmark summary (results/benchmark_summary.csv), if present."""
    import pandas as pd

    p = ROOT / "results" / "benchmark_summary.csv"
    return [] if not p.exists() else pd.read_csv(p).fillna("").to_dict(orient="records")


@app.post("/segment")
def segment_ep(req: SegmentRequest):
    img, gt = _get_image(req.sample, req.image_b64)
    try:
        res = segment(img, _prm(req.params), gt, edges=req.edges, single_edges=req.single_edges)
    except ValueError as e:
        raise HTTPException(400, str(e))
    res["display"] = to_uint8(img)
    return _jsonable(res)


@app.post("/edges")
def edges_ep(req: SegmentRequest):
    req.edges = True
    return segment_ep(req)


@app.post("/benchmark")
def benchmark_ep(req: BenchmarkRequest, format: str = Query("json", pattern="^(json|csv)$")):
    img, gt = _get_image(req.sample, req.image_b64)
    # never start minute-long live Classiq runs inside one benchmark request:
    # the Classiq row uses a stored Classiq run, otherwise the labelled local fallback
    prm = _prm(req.params)
    prm.allow_live_classiq = False
    rows = benchmark(img, gt, prm, req.solvers)
    if format == "csv":
        import pandas as pd

        return PlainTextResponse(pd.DataFrame(rows).to_csv(index=False), media_type="text/csv")
    return rows


# ----------------------------------------------------------------------------- web UI
# The React front-end (frontend/, built with `npm run build`) is served from "/".
# API routes above take precedence over the static mount.
_DIST = ROOT / "frontend" / "dist"
if _DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_DIST, html=True), name="ui")
