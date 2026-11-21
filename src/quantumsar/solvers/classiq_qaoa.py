"""QAOA tile solver running on Classiq (synthesis + cloud simulator execution).

Design
------
* The cost Hamiltonian of a tile is an Ising model on the tile's 4-neighbour
  grid graph: H_C = sum_i h_i Z_i + sum_(ij) J_ij Z_i Z_j.
* The *structure* (number of qubits, coupling graph) depends only on the tile
  shape, while the *coefficients* change from tile to tile. We therefore pass
  every coefficient as an execution parameter::

      params = [gamma_1..gamma_p, beta_1..beta_p, h_1..h_n, J_1..J_m]

  so ONE synthesized quantum program serves all tiles of a given shape, and all
  tiles of one checkerboard colour are sampled in ONE batched ``sample`` call.
* Cost layer: RZ(2 gamma h_i) on qubit i and CX-RZ(2 gamma J_ij)-CX on each edge
  (= exp(-i gamma H_C)); mixer: RX(2 beta) on every qubit (= exp(-i beta X)).
* Angles: optimised classically on an exact statevector of the same circuit
  ("pre-trained / transferred angles", see ``LocalQAOASolver``), or optionally
  optimised on Classiq itself with ``ExecutionSession.estimate_cost``.
* The best (lowest-energy) bitstring among the Classiq shots is returned.

The Classiq simulator ``classiq/simulator`` supports up to 28 qubits.
"""

import time

import numpy as np

from ..qubo import TileQUBO
from .tile_solvers import StatevectorQAOA, TileResult, TileSolver, linear_ramp, qaoa_normalisation

CLASSIQ_SIM_MAX_QUBITS = 28


def _signature(q: TileQUBO) -> tuple:
    h, J, _, _ = qaoa_normalisation(q)
    return q.n, tuple(sorted(J.keys()))


def build_qaoa_model(n: int, edges: list[tuple[int, int]], p: int):
    """Return the Qmod ``main`` for an n-qubit QAOA with parametric coefficients."""
    from classiq import CArray, CReal, CX, Output, QArray, QBit, RX, RZ, allocate, hadamard_transform, qfunc

    n_params = 2 * p + n + len(edges)

    @qfunc
    def main(params: CArray[CReal, n_params], v: Output[QArray[QBit, n]]):  # noqa: F821
        allocate(v)
        hadamard_transform(v)
        for k in range(p):
            g = params[k]
            for i in range(n):
                RZ(2 * g * params[2 * p + i], v[i])
            for e, (i, j) in enumerate(edges):
                CX(v[i], v[j])
                RZ(2 * g * params[2 * p + n + e], v[j])
                CX(v[i], v[j])
            for i in range(n):
                RX(2 * params[p + k], v[i])

    return main


def _circuit_metrics(qprog) -> dict:
    out = {}
    try:
        from classiq import get_circuit_metrics  # type: ignore

        m = get_circuit_metrics(qprog)
        for key in ("width", "depth"):
            if hasattr(m, key):
                out[key] = int(getattr(m, key))
        if hasattr(m, "gate_counts"):
            out["gate_counts"] = dict(getattr(m, "gate_counts"))
    except Exception:
        pass
    if not out:
        try:
            out["width"] = int(qprog.data.width)
            tc = qprog.transpiled_circuit
            out["depth"] = int(tc.depth)
            if getattr(tc, "count_ops", None):
                out["gate_counts"] = dict(tc.count_ops)
        except Exception:
            pass
    return out


def _bits_from_state(v, n: int) -> np.ndarray:
    if isinstance(v, (list, tuple, np.ndarray)):
        return np.array([int(b) for b in v], dtype=int)
    # integer encoding: bit i = (v >> i) & 1
    v = int(v)
    return np.array([(v >> i) & 1 for i in range(n)], dtype=int)


class ClassiqQAOASolver(TileSolver):
    name = "classiq"
    label = "QAOA on Classiq (cloud simulator)"
    provenance = "quantum circuit executed on Classiq"

    def __init__(self, p: int = 2, shots: int = 1024, maxiter: int = 40,
                 optimise_on_classiq: bool = False, batch_size: int = 32, seed: int = 0):
        self.p, self.shots, self.maxiter = p, shots, maxiter
        self.optimise_on_classiq = optimise_on_classiq
        self.batch_size = batch_size
        self._progs: dict = {}
        from .tile_solvers import LocalQAOASolver
        self._angle_src = LocalQAOASolver(p=p, maxiter=maxiter, seed=seed)  # angle optimiser/transfer
        self.seed = seed
        self.circuit: dict = {}

    # ----------------------------------------------------------- synthesis
    def program(self, q: TileQUBO):
        sig = _signature(q)
        if sig not in self._progs:
            from classiq import Constraints, synthesize

            n, edges = sig
            if n > CLASSIQ_SIM_MAX_QUBITS:
                raise ValueError(f"{n} qubits exceeds Classiq simulator limit {CLASSIQ_SIM_MAX_QUBITS}")
            t0 = time.perf_counter()
            qprog = synthesize(build_qaoa_model(n, list(edges), self.p),
                               constraints=Constraints(max_width=CLASSIQ_SIM_MAX_QUBITS))
            metrics = _circuit_metrics(qprog)
            metrics.update({"qubits_logical": n, "edges": len(edges), "p": self.p,
                            "synthesis_seconds": round(time.perf_counter() - t0, 2)})
            self._progs[sig] = (qprog, metrics)
            if not self.circuit or n >= self.circuit.get("qubits_logical", 0):
                self.circuit = metrics
        return self._progs[sig]

    def params_for(self, q: TileQUBO, angles: np.ndarray) -> list[float]:
        h, J, _, _ = qaoa_normalisation(q)
        edges = sorted(J.keys())
        return [float(a) for a in angles] + [float(x) for x in h] + [float(J[e]) for e in edges]

    # ----------------------------------------------------------- execution
    def solve_batch(self, qs: list[TileQUBO]) -> list[TileResult]:
        from classiq import ExecutionSession

        results: list[TileResult | None] = [None] * len(qs)
        groups: dict = {}
        for i, q in enumerate(qs):
            groups.setdefault(_signature(q), []).append(i)
        for sig, idxs in groups.items():
            qprog, metrics = self.program(qs[idxs[0]])
            angles_all = []
            for i in idxs:
                sim = StatevectorQAOA(qs[i]) if qs[i].n <= 20 else None
                if sim is not None:
                    ang = self._angle_src.angles_for(sim)
                else:
                    ang = self._angle_src._angles.get(qs[i].n, linear_ramp(self.p))
                angles_all.append((ang, sim))
            with ExecutionSession(qprog, num_shots=self.shots) as es:
                if self.optimise_on_classiq:
                    angles_all = [(self._optimise_remote(es, qs[i], a), s) for i, (a, s) in zip(idxs, angles_all)]
                for start in range(0, len(idxs), self.batch_size):
                    chunk = idxs[start : start + self.batch_size]
                    plist = [{"params": self.params_for(qs[i], angles_all[idxs.index(i)][0])} for i in chunk]
                    t0 = time.perf_counter()
                    dfs = es.sample(plist)
                    dt = time.perf_counter() - t0
                    if not isinstance(dfs, list):
                        dfs = [dfs]
                    for i, df in zip(chunk, dfs):
                        q = qs[i]
                        samples = [(_bits_from_state(pc.state["v"], q.n), pc.shots) for pc in df.parsed_counts]
                        bits = np.array([b for b, _ in samples])
                        e = q.energy(bits)
                        k = int(np.argmin(e))
                        sim = angles_all[idxs.index(i)][1]
                        info = {"qubits": q.n, "p": self.p, "circuit": metrics,
                                "distinct_samples": len(samples), "seconds": dt / len(chunk)}
                        if sim is not None:
                            opt = float(sim.energies.min())
                            info["found_opt"] = bool(np.isclose(e[k], opt))
                            tot = sum(s for _, s in samples)
                            info["p_opt"] = float(sum(s for (b, s), ee in zip(samples, e) if np.isclose(ee, opt)) / tot)
                            info["p_opt_uniform"] = 1.0 / 2 ** q.n
                        results[i] = TileResult(bits[k], float(e[k]), info)
        return results  # type: ignore[return-value]

    def _optimise_remote(self, es, q: TileQUBO, init: np.ndarray) -> np.ndarray:
        from scipy.optimize import minimize

        h, J, _, _ = qaoa_normalisation(q)
        edges = sorted(J.keys())
        tail = [float(x) for x in h] + [float(J[e]) for e in edges]

        def cost_state(state) -> float:
            b = _bits_from_state(state["v"], q.n)
            return float(q.energy(b))

        def f(angles):
            return es.estimate_cost(cost_state, {"params": list(map(float, angles)) + tail})

        res = minimize(f, init, method="COBYLA", options={"maxiter": self.maxiter, "rhobeg": 0.2})
        return res.x

    def solve(self, q):
        return self.solve_batch([q])[0]

    def describe(self):
        return {**super().describe(), "p": self.p, "shots": self.shots, "circuit": self.circuit}
