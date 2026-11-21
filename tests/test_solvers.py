import itertools

import numpy as np
import pytest

from quantumsar.data import SampleSpec, make_sample
from quantumsar.edges import edges_double, edges_single
from quantumsar.metrics import segmentation_metrics
from quantumsar.mrf import MRFModel, build_model, energy, estimate_looks
from quantumsar.pipeline import SegParams, benchmark, segment
from quantumsar.solvers import classical
from quantumsar.solvers.tile_solvers import LocalQAOASolver
from quantumsar.tiling import coarsen, multires_solve, tiled_solve


def test_graph_cut_is_exact_on_tiny_image():
    rng = np.random.default_rng(0)
    m = MRFModel(unary=rng.random((3, 4, 2)) * 3, lam=1.0, means=np.ones(2), looks=1)
    best = min(energy(m, np.array(t).reshape(3, 4)) for t in itertools.product((0, 1), repeat=12))
    assert energy(m, classical.graph_cut(m)) == pytest.approx(best)


def test_graph_cut_beats_local_methods():
    img, _ = make_sample(SampleSpec(seed=2, snr_db=5))
    m = build_model(img, 2, lam=1.5, looks=3)
    e_gc = energy(m, classical.graph_cut(m))
    assert e_gc <= energy(m, classical.icm(m)) + 1e-9
    assert e_gc <= energy(m, classical.simulated_annealing(m, sweeps=60)) + 1e-9


def test_alpha_expansion_improves_on_icm():
    img, _ = make_sample(SampleSpec(seed=4))
    m = build_model(img, 3, lam=1.5, looks=3)
    assert energy(m, classical.alpha_expansion(m)) <= energy(m, classical.icm(m)) + 1e-9


def test_tiling_is_monotone_and_near_optimal():
    img, _ = make_sample(SampleSpec(seed=8))
    m = build_model(img, 2, lam=1.5, looks=3)
    lab, rep = tiled_solve(m, LocalQAOASolver(p=1, shots=256, maxiter=10), tile=3, sweeps=2)
    tr = rep.energy_trace
    assert all(b <= a + 1e-9 for a, b in zip(tr, tr[1:]))
    lab2, _ = multires_solve(m, LocalQAOASolver(p=1, shots=256, maxiter=10), tile=3, sweeps=2)
    e_opt = energy(m, classical.graph_cut(m))
    assert energy(m, lab2) <= e_opt * 1.02


def test_coarsening_preserves_energy_of_block_labelings():
    img, _ = make_sample(SampleSpec(seed=9))
    m = build_model(img, 2, lam=1.5, looks=3)
    cm = coarsen(m, 4)
    rng = np.random.default_rng(0)
    cl = rng.integers(0, 2, cm.shape).astype(np.uint8)
    up = np.repeat(np.repeat(cl, 4, 0), 4, 1)
    assert energy(cm, cl) == pytest.approx(energy(m, up))


def test_estimate_looks():
    img, _ = make_sample(SampleSpec(has_target=False, looks=4.0, seed=1))
    assert 2.5 < estimate_looks(img) < 6.0


def test_edges_match_use_case_example():
    lab = np.array([[1, 1, 0, 0, 0]] * 2 + [[1, 1, 1, 0, 0]] * 3)
    single = edges_single(lab)
    exp = np.array([[0, 1, 0, 0, 0]] * 2 + [[0, 0, 1, 0, 0]] * 3)
    np.testing.assert_array_equal(single, exp)
    d = edges_double(lab)
    assert d.sum() > single.sum()
    assert np.all(d[single > 0] == 1)


def test_metrics_empty_target_is_perfect():
    z = np.zeros((8, 8), int)
    assert segmentation_metrics(z, z)["iou"] == 1.0
    m = segmentation_metrics(np.ones((8, 8), int), z)
    assert m["iou"] == 0.0 and m["accuracy"] == 0.0


@pytest.mark.parametrize("nc", [2, 3])
def test_pipeline_end_to_end(nc):
    img, gt = make_sample(SampleSpec(seed=11))
    r = segment(img, SegParams(solver="qaoa_local", n_classes=nc, maxiter=10, shots=256), gt, edges=True)
    assert r["labels"].shape == img.shape
    assert r["metrics"]["accuracy"] > 0.95
    assert "edges" in r and r["edges"].shape == img.shape
    assert "local statevector" in r["mode"]


def test_no_target_image_is_all_background():
    img, gt = make_sample(SampleSpec(has_target=False, seed=12))
    r = segment(img, SegParams(solver="graphcut"), gt)
    assert r["labels"].sum() == 0


def test_classiq_falls_back_without_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("QUANTUMSAR_DISABLE_CLASSIQ", "1")
    import quantumsar.pipeline as pl

    monkeypatch.setattr(pl, "CACHE_DIR", tmp_path)
    pl._LIVE_STATE.clear()
    img, gt = make_sample(SampleSpec(seed=13))
    r = segment(img, SegParams(solver="classiq", allow_live_classiq=True, maxiter=5, shots=128), gt)
    assert r["mode"].startswith("FALLBACK")
    # cached results are served (and labelled) when present
    pl.save_cached_quantum(img, SegParams(solver="classiq", maxiter=5, shots=128), r["labels"], {"tiling": {}})
    r2 = segment(img, SegParams(solver="classiq", maxiter=5, shots=128), gt)
    assert "cached" in r2["mode"]
    pl._LIVE_STATE.clear()


def test_benchmark_rows():
    img, gt = make_sample(SampleSpec(seed=14))
    rows = benchmark(img, gt, SegParams(maxiter=5, shots=128), ["graphcut", "otsu", "qaoa_local"])
    assert [r["solver"] for r in rows] == ["graphcut", "otsu", "qaoa_local"]
    assert all("error" not in r for r in rows)
