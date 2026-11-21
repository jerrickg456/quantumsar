"""Synthesize (once) every QAOA tile program a server can need, and store them in
results/classiq_programs/ so deployed servers execute on Classiq without
re-synthesizing. Needs Classiq auth.

    python scripts/synthesize_programs.py
"""
import sys
import time
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from quantumsar.auth import setup_classiq_auth  # noqa: E402

setup_classiq_auth()

from quantumsar.data import load_sample  # noqa: E402
from quantumsar.pipeline import SegParams, fit_model  # noqa: E402
from quantumsar.qubo import tile_qubo  # noqa: E402
from quantumsar.solvers.classical import ml_labels  # noqa: E402
from quantumsar.solvers.classiq_qaoa import ClassiqQAOASolver, _load_program, _signature  # noqa: E402

img, _ = load_sample(ROOT / "data", "sar_000_normal")
JOBS = []  # (n_classes, max tile side, QAOA depths)
JOBS += [(2, 3, (1, 2, 3)), (2, 2, (2,)), (3, 2, (1, 2, 3))]
for nc, t, depths in JOBS:
    model = fit_model(img, SegParams(n_classes=nc))
    lab = ml_labels(model)
    for p in depths:
        solver = ClassiqQAOASolver(p=p)
        for h, w in product(range(1, t + 1), repeat=2):
            q = tile_qubo(model, lab, 20, 20, h, w)
            key = (*_signature(q), p)
            if _load_program(key) is not None:
                continue
            t0 = time.time()
            solver.program(q)
            print(f"{nc}-class tile {h}x{w} ({q.n} qubits) p={p}: {time.time() - t0:.1f}s", flush=True)
print("programs in", ROOT / "results" / "classiq_programs")
