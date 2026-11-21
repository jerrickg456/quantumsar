"""The QUBO must be an exact re-encoding of the MRF energy, and every solver
must recover the brute-force optimum on tiny (3x3, 4x4) tiles."""
import itertools

import numpy as np
import pytest

from quantumsar.data import SampleSpec, make_sample
from quantumsar.mrf import build_model, energy
from quantumsar.qubo import all_bitstrings, brute_force, tile_energy_from_model, tile_qubo
from quantumsar.solvers.classical import ml_labels
from quantumsar.solvers.tile_solvers import AnnealingTileSolver, LocalQAOASolver


def _model(K=2, seed=0, lam=1.5):
    img, _ = make_sample(SampleSpec(seed=seed, snr_db=6))
    return img, build_model(img, K, lam=lam, looks=3.0)


TILES = [(20, 20, 3, 3), (0, 0, 3, 3), (61, 61, 3, 3), (24, 30, 4, 4), (0, 60, 4, 4)]


@pytest.mark.parametrize("K", [2, 3])
@pytest.mark.parametrize("r0,c0,h,w", TILES)
def test_qubo_energy_matches_mrf(K, r0, c0, h, w):
    """For random valid labellings, QUBO energy == tile-dependent MRF energy, and
    differences equal differences of the full-image energy."""
    _, m = _model(K)
    rng = np.random.default_rng(1)
    lab = rng.integers(0, K, m.shape).astype(np.uint8)
    q = tile_qubo(m, lab, r0, c0, h, w)
    base = energy(m, lab)
    ref = None
    for _ in range(25):
        tl = rng.integers(0, K, h * w)
        e_q = q.energy(q.encode(tl))
        assert e_q == pytest.approx(tile_energy_from_model(m, lab, q, tl), abs=1e-8)
        full = lab.copy()
        for (r, c), k in zip(q.pixels, tl):
            full[r, c] = k
        d = energy(m, full) - e_q
        ref = d if ref is None else ref
        assert d == pytest.approx(ref, abs=1e-6)   # constant offset => same argmin
    assert base is not None


def test_ising_conversion_exact():
    _, m = _model(2)
    q = tile_qubo(m, ml_labels(m), 20, 20, 3, 3)
    h, J, off = q.to_ising()
    bits = all_bitstrings(q.n)
    s = 1 - 2 * bits.astype(float)
    e_ising = off + s @ h + sum(v * s[:, i] * s[:, j] for (i, j), v in J.items())
    np.testing.assert_allclose(e_ising, q.energy(bits), atol=1e-9)


@pytest.mark.parametrize("K,h", [(2, 3), (2, 4), (3, 2)])
def test_bruteforce_qubo_equals_bruteforce_labelings(K, h):
    """argmin over all bitstrings (incl. invalid one-hot) == argmin over labelings."""
    _, m = _model(K, seed=3)
    lab = ml_labels(m)
    q = tile_qubo(m, lab, 22, 22, h, h)
    b, e = brute_force(q)
    best = min(tile_energy_from_model(m, lab, q, np.array(t))
               for t in itertools.product(range(K), repeat=h * h))
    assert e == pytest.approx(best, abs=1e-8)
    if K == 3:
        assert np.all(b.reshape(-1, 3).sum(1) == 1), "optimum must be one-hot valid"


@pytest.mark.parametrize("h", [3, 4])
def test_qaoa_and_annealing_match_bruteforce(h):
    """Acceptance criterion: QAOA (best of shots) and annealing hit the exact optimum."""
    _, m = _model(2, seed=5)
    lab = ml_labels(m)
    qaoa = LocalQAOASolver(p=2, shots=2048, maxiter=40, seed=0)
    sa = AnnealingTileSolver(seed=0)
    for r0, c0 in [(20, 20), (26, 30), (30, 26), (0, 0)]:
        q = tile_qubo(m, lab, r0, c0, h, h)
        _, e_opt = brute_force(q)
        rq = qaoa.solve(q)
        assert rq.energy == pytest.approx(e_opt, abs=1e-8)
        assert rq.info["p_opt"] > rq.info["p_opt_uniform"], "QAOA must amplify the optimum"
        assert sa.solve(q).energy == pytest.approx(e_opt, abs=1e-8)


def test_qaoa_three_class_tile_matches_bruteforce():
    _, m = _model(3, seed=7)
    lab = ml_labels(m)
    q = tile_qubo(m, lab, 24, 24, 2, 2)  # 12 qubits, one-hot
    _, e_opt = brute_force(q)
    r = LocalQAOASolver(p=2, shots=4096, maxiter=40).solve(q)
    assert r.energy == pytest.approx(e_opt, abs=1e-8)
