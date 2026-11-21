"""High-level segmentation pipeline shared by the API, UI, scripts and tests."""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from . import mrf
from .edges import edge_classes, edges_double, edges_single
from .metrics import edge_metrics, segmentation_metrics
from .solvers import classical
from .solvers.tile_solvers import AnnealingTileSolver, BruteForceSolver, LocalQAOASolver
from .tiling import multires_solve

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = Path(os.environ.get("QUANTUMSAR_CACHE", REPO_ROOT / "results" / "quantum_cache"))

SOLVERS = {
    # key: (display name, kind)
    "classiq": ("Quantum - QAOA on Classiq", "tiled"),
    "qaoa_local": ("Quantum - QAOA (local statevector)", "tiled"),
    "annealing": ("Simulated annealing (global MRF)", "mrf"),
    "sa_tiled": ("Quantum-inspired SA (same tiled QUBOs)", "tiled"),
    "graphcut": ("Graph cut (exact binary / alpha-expansion)", "mrf"),
    "icm": ("ICM", "mrf"),
    "otsu": ("Otsu threshold", "pixel"),
    "kmeans": ("k-means", "pixel"),
    "bruteforce_tiled": ("Exact tiles (brute force)", "tiled"),
}


@dataclass
class SegParams:
    solver: str = "qaoa_local"
    n_classes: int = 2
    lam: float = 1.5
    looks: float | None = None      # None = estimate ENL from the image
    tile: int = 3
    sweeps: int = 2
    p: int = 2
    shots: int = 1024
    maxiter: int = 30
    margin: float | None = 3.0       # only uncertain tiles -> quantum; None = all tiles
    em_iters: int = 1
    seed: int = 0
    multires: bool = True            # coarse-to-fine (x4 then x1) tiling
    allow_live_classiq: bool = False

    def cache_key(self, img: np.ndarray) -> str:
        d = asdict(self)
        for k in ("solver", "allow_live_classiq"):
            d.pop(k)
        h = hashlib.sha1(np.ascontiguousarray(img, dtype=np.float32).tobytes())
        h.update(json.dumps(d, sort_keys=True).encode())
        return h.hexdigest()[:16]


def fit_model(img: np.ndarray, prm: SegParams) -> mrf.MRFModel:
    """Unsupervised model fitting shared by all MRF solvers (ICM-EM)."""
    looks = prm.looks if prm.looks else mrf.estimate_looks(img)
    model = mrf.build_model(img, prm.n_classes, prm.lam, looks)
    for _ in range(prm.em_iters):
        lab = classical.icm(model)
        means = mrf.refit_means(img, lab, model.means)
        model = mrf.build_model(img, prm.n_classes, prm.lam, looks, means=means)
    return model


def tile_qubits(prm: SegParams, tile: int | None = None) -> int:
    t = prm.tile if tile is None else tile
    return t * t * (1 if prm.n_classes == 2 else prm.n_classes)


def effective_tile(prm: SegParams, max_qubits: int) -> int:
    """Largest square tile <= prm.tile whose QUBO fits in ``max_qubits``."""
    t = prm.tile
    while t > 1 and tile_qubits(prm, t) > max_qubits:
        t -= 1
    return t


def _tiled(model, solver, prm: SegParams, tile: int, progress=None):
    factors = (4,) if prm.multires else ()
    lab, rep = multires_solve(model, solver, tile, prm.sweeps, margin=prm.margin,
                              factors=factors, progress=progress)
    info = rep.summary()
    info["tile_effective"] = tile
    info["qubits_per_tile"] = tile_qubits(prm, tile)
    return lab, info


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.npz"


def load_cached_quantum(img: np.ndarray, prm: SegParams):
    p = _cache_path(prm.cache_key(img))
    if p.is_file():
        z = np.load(p, allow_pickle=False)
        return z["labels"], json.loads(str(z["meta"]))
    return None


def save_cached_quantum(img: np.ndarray, prm: SegParams, labels: np.ndarray, meta: dict) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = _cache_path(prm.cache_key(img))
    np.savez_compressed(p, labels=labels.astype(np.uint8), meta=json.dumps(meta, default=str))
    return p


def run_solver(img: np.ndarray, prm: SegParams, progress=None) -> dict:
    """Run one solver. Returns labels + diagnostics including a ``mode`` string
    that states exactly which engine produced the result."""
    t0 = time.perf_counter()
    model = None
    info: dict = {}
    s = prm.solver
    if s not in SOLVERS:
        raise ValueError(f"unknown solver {s!r}; choose from {list(SOLVERS)}")
    kind = SOLVERS[s][1]
    if progress:
        progress(0.01, "fitting the MRF model")
    if kind != "pixel":
        model = fit_model(img, prm)
        t_fit = time.perf_counter() - t0
    else:
        t_fit = 0.0

    if s == "otsu":
        lab, mode = classical.otsu(img, prm.n_classes), "classical"
    elif s == "kmeans":
        lab, mode = classical.kmeans(img, prm.n_classes), "classical"
    elif s == "icm":
        lab, mode = classical.icm(model), "classical"
    elif s == "annealing":
        lab, mode = classical.simulated_annealing(model, seed=prm.seed), "classical"
    elif s == "graphcut":
        lab = classical.graph_cut(model)
        mode = "classical (exact)" if prm.n_classes == 2 else "classical (alpha-expansion)"
    elif s == "classiq":
        cached = load_cached_quantum(img, prm)
        if cached is not None:
            lab, meta = cached
            info = {**meta.get("tiling", {}), "cached_meta": meta}
            mode = "Classiq QAOA - cached result (precomputed on Classiq)"
        elif prm.allow_live_classiq and _classiq_live_ok():
            from .solvers.classiq_qaoa import ClassiqQAOASolver

            if progress:
                progress(0.02, "loading / synthesizing QAOA circuits on Classiq")
            solver = ClassiqQAOASolver(p=prm.p, shots=prm.shots, maxiter=prm.maxiter, seed=prm.seed)
            # angles are pre-trained on a local statevector (<= 20 qubits)
            lab, info = _tiled(model, solver, prm, effective_tile(prm, LocalQAOASolver.max_qubits), progress)
            info["circuit"] = solver.circuit
            mode = "Classiq QAOA - live (Classiq cloud simulator)"
        else:
            # Fallback: same QAOA circuit on the local statevector simulator when
            # it fits, otherwise simulated annealing on the same QUBOs.
            # State *why* Classiq was not used, so the UI label is accurate.
            if not prm.allow_live_classiq:
                why = "no cached Classiq run for this image/settings; live Classiq is off"
            else:
                why = "Classiq login/connection failed: " + classiq_status().get("msg", "")[:80]
            if os.environ.get("QUANTUMSAR_FALLBACK", "qaoa_local") == "qaoa_local":
                solver = LocalQAOASolver(p=prm.p, shots=prm.shots, maxiter=prm.maxiter, seed=prm.seed)
                tile = effective_tile(prm, LocalQAOASolver.max_qubits)
                mode = f"FALLBACK: same QAOA circuit on local simulator ({why})"
            else:
                solver, tile = AnnealingTileSolver(seed=prm.seed), prm.tile
                mode = f"FALLBACK: simulated annealing on the tile QUBOs ({why})"
            lab, info = _tiled(model, solver, prm, tile, progress)
    else:
        solver = {
            "qaoa_local": lambda: LocalQAOASolver(p=prm.p, shots=prm.shots, maxiter=prm.maxiter, seed=prm.seed),
            "sa_tiled": lambda: AnnealingTileSolver(seed=prm.seed),
            "bruteforce_tiled": lambda: BruteForceSolver(),
        }[s]()
        limit = {"qaoa_local": LocalQAOASolver.max_qubits, "bruteforce_tiled": 20}.get(s, 10 ** 6)
        lab, info = _tiled(model, solver, prm, effective_tile(prm, limit), progress)
        mode = {"qaoa_local": "QAOA on local statevector simulator",
                "sa_tiled": "quantum-inspired simulated annealing (classical)",
                "bruteforce_tiled": "exact tile enumeration (classical)"}[s]
    runtime = time.perf_counter() - t0
    if "cached_meta" in info and info["cached_meta"].get("runtime_s"):
        # report the wall time of the original Classiq run, not the cache lookup
        info["served_from_cache_s"] = runtime
        runtime = float(info["cached_meta"]["runtime_s"])
    if model is None:
        model = fit_model(img, prm)
    return {
        "labels": lab.astype(np.uint8),
        "solver": s,
        "solver_name": SOLVERS[s][0],
        "mode": mode,
        "runtime_s": runtime,
        "fit_s": t_fit,
        "energy": mrf.energy(model, lab),
        "info": info,
        "means": [float(m) for m in model.means],
    }


_LIVE_STATE: dict = {}


def _classiq_live_ok() -> bool:
    if "ok" not in _LIVE_STATE:
        from .auth import classiq_ready

        ok, msg = classiq_ready()
        _LIVE_STATE.update(ok=ok, msg=msg)
    return _LIVE_STATE["ok"]


def classiq_status() -> dict:
    return dict(_LIVE_STATE) if _LIVE_STATE else {"ok": None, "msg": "not checked yet"}


def segment(img: np.ndarray, prm: SegParams, gt: np.ndarray | None = None,
            edges: bool = False, single_edges: bool = True, progress=None) -> dict:
    res = run_solver(img, prm, progress=progress)
    lab = res["labels"]
    if edges:
        res["edges"] = edges_single(lab) if single_edges else edges_double(lab)
        res["edge_classes"] = edge_classes(lab, single=single_edges)
    if gt is not None:
        res["metrics"] = segmentation_metrics(lab, gt, prm.n_classes)
        if edges:
            g = gt if prm.n_classes == 3 else (gt == 1).astype(np.uint8)
            ge = edges_single(g) if single_edges else edges_double(g)
            res["metrics"].update(edge_metrics(res["edges"], ge))
    return res


def benchmark(img: np.ndarray, gt: np.ndarray | None, base: SegParams,
              solvers: list[str] | None = None) -> list[dict]:
    rows = []
    for s in solvers or ["classiq", "qaoa_local", "sa_tiled", "annealing", "graphcut", "icm", "otsu", "kmeans"]:
        prm = SegParams(**{**asdict(base), "solver": s})
        try:
            r = segment(img, prm, gt)
            row = {"solver": s, "name": SOLVERS[s][0], "mode": r["mode"],
                   "runtime_s": round(r["runtime_s"], 4), "energy": round(r["energy"], 3)}
            row.update({k: round(v, 4) for k, v in r.get("metrics", {}).items()})
            if "tiles_solved" in r["info"]:
                row["tiles_solved"] = r["info"]["tiles_solved"]
                row["max_qubits"] = r["info"]["max_qubits"]
        except Exception as e:  # noqa: BLE001
            row = {"solver": s, "name": SOLVERS[s][0], "error": str(e)[:200]}
        rows.append(row)
    return rows
