"""Tile decomposition of the full-image MRF for qubit-limited solvers.

A 64x64 image has 4096 binary variables (12288 for one-hot 3-class) - far
beyond any simulator. We therefore run *block coordinate descent*:

1. Start from the pixel-wise maximum-likelihood labelling.
2. Partition the image into ``tile x tile`` blocks. Each block becomes a small
   QUBO in which the pixels just outside the block are fixed and act as
   external fields (see ``qubo.tile_qubo``).
3. Blocks are 2-coloured like a checkerboard. Blocks of one colour share no
   MRF edge, so all of them are solved as one *batch* (one Classiq job).
4. A block's new labelling is accepted only if it does not increase the
   energy, so the full-image energy is monotonically non-increasing.
5. Successive sweeps shift the grid by ``tile // 2`` so that block borders
   move ("overlapping tiles"), letting information cross tile boundaries.
6. Finish with a few ICM sweeps to stitch any residual seams.

Optionally only *uncertain* blocks are sent to the quantum solver: blocks in
which some pixel's best label wins its local conditional energy by less than
``margin``. Confident blocks (most of the clutter) are skipped - they would
come back unchanged anyway. The fraction of blocks solved is reported.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .mrf import MRFModel, energy, local_costs
from .qubo import TileQUBO, tile_qubo
from .solvers.classical import icm, ml_labels
from .solvers.tile_solvers import TileSolver


@dataclass
class TilingReport:
    tile: int
    sweeps: int
    tiles_total: int = 0
    tiles_solved: int = 0
    tiles_improved: int = 0
    batches: int = 0
    max_qubits: int = 0
    solver_seconds: float = 0.0
    energy_trace: list = field(default_factory=list)
    tile_infos: list = field(default_factory=list)
    levels: list = field(default_factory=lambda: ["x1"])

    def summary(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "tile_infos"}
        infos = [i for i in self.tile_infos if i]
        if infos and "p_opt" in infos[0]:
            d["qaoa_mean_p_opt"] = float(np.mean([i["p_opt"] for i in infos]))
            d["qaoa_mean_p_opt_uniform"] = float(np.mean([i["p_opt_uniform"] for i in infos]))
            d["qaoa_found_opt_rate"] = float(np.mean([i["found_opt"] for i in infos]))
        if infos and "circuit" in infos[0]:
            d["circuit"] = infos[0]["circuit"]
        return d


def tile_grid(H: int, W: int, tile: int, offset: int):
    def starts(N):
        s = [0] + list(range(offset, N, tile)) if offset else list(range(0, N, tile))
        s = sorted(set(x for x in s if x < N))
        return [(a, (s[i + 1] if i + 1 < len(s) else N) - a) for i, a in enumerate(s)]

    rows, cols = starts(H), starts(W)
    for ti, (r0, h) in enumerate(rows):
        for tj, (c0, w) in enumerate(cols):
            yield ti, tj, r0, c0, h, w


def uncertain_mask(model: MRFModel, labels: np.ndarray, margin: float) -> np.ndarray:
    c = np.sort(local_costs(model, labels), axis=2)
    cur = np.take_along_axis(local_costs(model, labels), labels[..., None].astype(int), 2)[..., 0]
    not_opt = cur > c[..., 0] + 1e-9
    return not_opt | ((c[..., 1] - c[..., 0]) < margin)


def tiled_solve(
    model: MRFModel,
    solver: TileSolver,
    tile: int = 4,
    sweeps: int = 2,
    init: np.ndarray | None = None,
    margin: float | None = None,
    icm_sweeps: int = 3,
    progress: Callable[[float, str], None] | None = None,
) -> tuple[np.ndarray, TilingReport]:
    H, W, K = model.unary.shape
    lab = ml_labels(model) if init is None else init.astype(np.uint8).copy()
    rep = TilingReport(tile=tile, sweeps=sweeps)
    rep.energy_trace.append(energy(model, lab))
    for s in range(sweeps):
        offset = 0 if s % 2 == 0 else tile // 2
        grid = list(tile_grid(H, W, tile, offset))
        for color in (0, 1):
            unc = uncertain_mask(model, lab, margin) if margin is not None else None
            batch: list[TileQUBO] = []
            for ti, tj, r0, c0, h, w in grid:
                if (ti + tj) % 2 != color:
                    continue
                rep.tiles_total += 1
                if unc is not None and not unc[r0 : r0 + h, c0 : c0 + w].any():
                    continue
                batch.append(tile_qubo(model, lab, r0, c0, h, w))
            if not batch:
                continue
            rep.tiles_solved += len(batch)
            rep.batches += 1
            rep.max_qubits = max(rep.max_qubits, max(q.n for q in batch))
            t0 = time.perf_counter()
            results = solver.solve_batch(batch)
            rep.solver_seconds += time.perf_counter() - t0
            for q, res in zip(batch, results):
                cur_bits = q.encode(np.array([lab[r, c] for r, c in q.pixels]))
                if q.energy(res.bits) <= q.energy(cur_bits) + 1e-9:
                    new = q.decode(res.bits)
                    if not np.array_equal(new, q.decode(cur_bits)):
                        rep.tiles_improved += 1
                    for (r, c), k in zip(q.pixels, new):
                        lab[r, c] = k
                rep.tile_infos.append(res.info)
            if progress:
                progress((s + (color + 1) / 2) / sweeps, f"sweep {s + 1}/{sweeps}, colour {color}")
        rep.energy_trace.append(energy(model, lab))
    if icm_sweeps:
        lab = icm(model, lab, max_sweeps=icm_sweeps)
        rep.energy_trace.append(energy(model, lab))
    return lab, rep


def coarsen(model: MRFModel, f: int) -> MRFModel:
    """Block-aggregated MRF: each f x f block becomes one super-pixel whose unary
    is the sum of its pixels' unaries; neighbouring blocks share f pixel edges,
    so the coarse Potts weight is f * lambda. An upsampled coarse labelling has
    exactly the same energy in the fine model."""
    H, W, K = model.unary.shape
    Hc, Wc = H // f, W // f
    u = model.unary[: Hc * f, : Wc * f].reshape(Hc, f, Wc, f, K).sum(axis=(1, 3))
    return MRFModel(unary=u, lam=model.lam * f, means=model.means, looks=model.looks)


def multires_solve(
    model: MRFModel,
    solver: TileSolver,
    tile: int = 3,
    sweeps: int = 2,
    margin: float | None = None,
    factors: tuple[int, ...] = (4,),
    icm_sweeps: int = 3,
    progress: Callable[[float, str], None] | None = None,
) -> tuple[np.ndarray, TilingReport]:
    """Coarse-to-fine tiling: the same tile solver (e.g. QAOA) first solves the
    block-aggregated MRF; its upsampled solution initialises the fine level.
    Large-scale structure (whole target / no target) is decided at the coarse
    level, where a 3x3 tile spans 12x12 pixels; the fine level refines edges."""
    H, W, _ = model.unary.shape
    init = ml_labels(model)
    reports = []
    for f in factors:
        if f <= 1 or H % f or W % f:
            continue
        cm = coarsen(model, f)
        clab, crep = tiled_solve(cm, solver, tile, sweeps, margin=None, icm_sweeps=icm_sweeps)
        up = np.repeat(np.repeat(clab, f, axis=0), f, axis=1)
        reports.append((f"x{f}", crep))
        if energy(model, up) < energy(model, init):
            init = up
    lab, rep = tiled_solve(model, solver, tile, sweeps, init=init, margin=margin,
                           icm_sweeps=icm_sweeps, progress=progress)
    for _, crep in reports:  # merge coarse-level statistics
        rep.tiles_total += crep.tiles_total
        rep.tiles_solved += crep.tiles_solved
        rep.tiles_improved += crep.tiles_improved
        rep.batches += crep.batches
        rep.solver_seconds += crep.solver_seconds
        rep.max_qubits = max(rep.max_qubits, crep.max_qubits)
        rep.tile_infos = crep.tile_infos + rep.tile_infos
    rep.levels = [name for name, _ in reports] + ["x1"]
    return lab, rep
