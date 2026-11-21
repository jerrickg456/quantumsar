"""Classiq integration. Model construction runs offline; synthesis/execution
needs credentials and only runs with QUANTUMSAR_TEST_CLASSIQ=1."""
import os

import pytest

classiq = pytest.importorskip("classiq")

from quantumsar.data import SampleSpec, make_sample  # noqa: E402
from quantumsar.mrf import build_model  # noqa: E402
from quantumsar.qubo import brute_force, tile_qubo  # noqa: E402
from quantumsar.solvers.classical import ml_labels  # noqa: E402
from quantumsar.solvers.classiq_qaoa import (  # noqa: E402
    ClassiqQAOASolver, _bits_from_state, _signature, build_qaoa_model)


def test_qmod_model_builds_offline():
    m = classiq.create_model(build_qaoa_model(4, [(0, 1), (1, 2), (2, 3)], 2))
    assert "RZ" in str(m) or len(m) > 1000


def test_parameter_layout():
    img, _ = make_sample(SampleSpec(seed=0))
    m = build_model(img, 2, 1.5, 3)
    q = tile_qubo(m, ml_labels(m), 20, 20, 3, 3)
    n, edges = _signature(q)
    s = ClassiqQAOASolver(p=2)
    assert n == 9 and len(edges) == 12
    assert len(s.params_for(q, [0.1, 0.2, 0.3, 0.4])) == 4 + 9 + 12


def test_bit_decoding():
    assert list(_bits_from_state([1, 0, 1], 3)) == [1, 0, 1]
    assert list(_bits_from_state(5, 3)) == [1, 0, 1]


@pytest.mark.skipif(os.environ.get("QUANTUMSAR_TEST_CLASSIQ") != "1", reason="needs Classiq credentials")
def test_classiq_qaoa_matches_bruteforce_3x3():
    from quantumsar.auth import setup_classiq_auth

    setup_classiq_auth()
    img, _ = make_sample(SampleSpec(seed=5))
    m = build_model(img, 2, 1.5, 3)
    lab = ml_labels(m)
    qs = [tile_qubo(m, lab, r, c, 3, 3) for r, c in [(20, 20), (26, 30)]]
    res = ClassiqQAOASolver(p=2, shots=2048).solve_batch(qs)
    for q, r in zip(qs, res):
        assert r.energy == pytest.approx(brute_force(q)[1], abs=1e-8)
