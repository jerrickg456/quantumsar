"""Tile-level QUBO solvers.

Every solver exposes ``solve_batch(qubos) -> list[TileResult]`` so the tiling
driver can submit all independent tiles of one checkerboard colour at once
(important for Classiq, where each round-trip to the cloud is expensive).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize

from ..qubo import TileQUBO, all_bitstrings, brute_force


@dataclass
class TileResult:
    bits: np.ndarray
    energy: float
    info: dict = field(default_factory=dict)


class TileSolver:
    name = "base"
    label = "base"          # human readable, shown in the UI
    provenance = "classical"

    def solve(self, q: TileQUBO) -> TileResult:  # pragma: no cover - interface
        raise NotImplementedError

    def solve_batch(self, qs: list[TileQUBO]) -> list[TileResult]:
        return [self.solve(q) for q in qs]

    def describe(self) -> dict:
        return {"solver": self.name, "provenance": self.provenance}


class BruteForceSolver(TileSolver):
    name = "bruteforce"
    label = "Brute force (exact)"

    def solve(self, q):
        b, e = brute_force(q)
        return TileResult(b, e)


class AnnealingTileSolver(TileSolver):
    """Quantum-inspired fallback: simulated annealing on the *same* QUBO the QAOA
    circuit encodes (single-bit-flip Metropolis, geometric schedule, restarts)."""

    name = "annealing"
    label = "Simulated annealing (QUBO, quantum-inspired)"
    provenance = "quantum-inspired (classical)"

    def __init__(self, sweeps: int = 100, restarts: int = 3, seed: int = 0):
        self.sweeps, self.restarts = sweeps, restarts
        self.rng = np.random.default_rng(seed)

    def solve(self, q):
        n = q.n
        Qs = q.quad + q.quad.T
        scale = max(np.abs(q.lin).max(initial=0), np.abs(Qs).max(initial=0), 1e-9)
        temps = scale * 2.0 * (1e-3) ** (np.arange(self.sweeps) / max(self.sweeps - 1, 1))
        best_b, best_e = None, np.inf
        for _ in range(self.restarts):
            x = self.rng.integers(0, 2, n).astype(float)
            field_ = q.lin + Qs @ x
            e = q.energy(x)
            for T in temps:
                for i in self.rng.permutation(n):
                    d = (1 - 2 * x[i]) * field_[i]      # delta E of flipping bit i
                    if d <= 0 or self.rng.random() < np.exp(-d / T):
                        s = 1 - 2 * x[i]
                        x[i] += s
                        field_ += s * Qs[:, i]
                        e += d
            if e < best_e:
                best_e, best_b = e, x.astype(int).copy()
        return TileResult(best_b, float(q.energy(best_b)))


# ======================================================================= QAOA
def qaoa_normalisation(q: TileQUBO) -> tuple[np.ndarray, dict, float, float]:
    """Ising coefficients scaled by the std of the energy under the uniform
    distribution, sqrt(sum h^2 + sum J^2). This makes QAOA angles transferable
    between tiles (the same schedule works for every tile)."""
    h, J, off = q.to_ising()
    norm = float(np.sqrt((h ** 2).sum() + sum(v * v for v in J.values()))) or 1.0
    return h / norm, {k: v / norm for k, v in J.items()}, off, norm


def linear_ramp(p: int, delta: float = 0.6) -> np.ndarray:
    """Standard 'linear ramp' (discretised adiabatic) initial schedule."""
    k = (np.arange(p) + 0.5) / p
    return np.concatenate([delta * k, delta * (1 - k)])  # [gammas, betas]


class StatevectorQAOA:
    """Exact statevector simulation of the QAOA circuit used on Classiq:

        |psi> = prod_k [ RX(2 beta_k)^{(x)n}  exp(-i gamma_k H_C) ] |+>^n

    with H_C = sum h_i Z_i + sum J_ij Z_i Z_j (normalised). The cost layer is
    diagonal, so it is applied as a phase vector."""

    def __init__(self, q: TileQUBO):
        self.q = q
        self.n = q.n
        h, J, _, _ = qaoa_normalisation(q)
        bits = all_bitstrings(self.n).astype(float)
        s = 1 - 2 * bits                              # Z eigenvalues
        hc = s @ h
        for (i, j), v in J.items():
            hc += v * s[:, i] * s[:, j]
        self.hc = hc
        self.bits = bits.astype(np.int8)
        self.energies = q.energy(bits)                # true QUBO energies

    def state(self, params: np.ndarray) -> np.ndarray:
        p = len(params) // 2
        g, b = params[:p], params[p:]
        n = self.n
        psi = np.full(2 ** n, 2 ** (-n / 2), dtype=complex)
        for k in range(p):
            psi = psi * np.exp(-1j * g[k] * self.hc)
            c, s = np.cos(b[k]), -1j * np.sin(b[k])
            for qb in range(n):
                v = psi.reshape(-1, 2, 2 ** qb)
                psi = (c * v + s * v[:, ::-1, :]).reshape(-1)   # RX(2 beta) on qubit qb
        return psi

    def expectation(self, params) -> float:
        pr = np.abs(self.state(np.asarray(params))) ** 2
        return float(pr @ self.hc)

    def optimise(self, p: int, maxiter: int = 60, init: np.ndarray | None = None):
        x0 = linear_ramp(p) if init is None else np.asarray(init, float)
        res = minimize(self.expectation, x0, method="COBYLA",
                       options={"maxiter": maxiter, "rhobeg": 0.2})
        return res.x, float(res.fun), int(res.nfev)


class LocalQAOASolver(TileSolver):
    """QAOA executed on a local exact statevector simulator (no credentials).

    Angles are optimised per tile (COBYLA on <H_C>) starting from a linear
    ramp, then ``shots`` bitstrings are sampled and the lowest-energy sample is
    returned, as in standard QAOA practice."""

    name = "qaoa_local"
    label = "QAOA (local statevector simulator)"
    provenance = "quantum algorithm, simulated locally"
    max_qubits = 20

    def __init__(self, p: int = 2, shots: int = 1024, maxiter: int = 40, seed: int = 0,
                 opt_tiles: int = 4):
        """``opt_tiles``: angles are optimised on the first ``opt_tiles`` tiles of
        each size and then *transferred* (reused) for the remaining tiles -
        QAOA parameter concentration on normalised Hamiltonians makes this
        accurate and saves most of the classical optimisation cost.
        ``opt_tiles=-1`` optimises every tile."""
        self.p, self.shots, self.maxiter, self.opt_tiles = p, shots, maxiter, opt_tiles
        self.rng = np.random.default_rng(seed)
        self._angles: dict = {}
        self._count: dict = {}

    def solve(self, q):
        if q.n > self.max_qubits:
            raise ValueError(f"tile has {q.n} qubits > local simulator limit {self.max_qubits}")
        t0 = time.perf_counter()
        sim = StatevectorQAOA(q)
        nfev = 0
        params = self.angles_for(sim)
        nfev = self._last_nfev
        prob = np.abs(sim.state(params)) ** 2
        prob /= prob.sum()
        idx = self.rng.choice(len(prob), size=self.shots, p=prob)
        uniq = np.unique(idx)
        k = uniq[np.argmin(sim.energies[uniq])]
        opt_idx = int(np.argmin(sim.energies))
        info = {
            "qubits": q.n,
            "p": self.p,
            "nfev": nfev,
            "p_opt": float(prob[opt_idx]),            # probability of the exact optimum
            "p_opt_uniform": 1.0 / 2 ** q.n,
            "found_opt": bool(np.isclose(sim.energies[k], sim.energies[opt_idx])),
            "seconds": time.perf_counter() - t0,
        }
        return TileResult(sim.bits[k].astype(int), float(sim.energies[k]), info)

    def angles_for(self, sim: "StatevectorQAOA") -> np.ndarray:
        """Optimise (warm-started) or transfer angles for this tile size."""
        n = sim.n
        cnt = self._count.get(n, 0)
        prev = self._angles.get(n)
        self._last_nfev = 0
        if self.maxiter and (self.opt_tiles < 0 or cnt < self.opt_tiles):
            init = prev if prev is not None else linear_ramp(self.p)
            params, _, self._last_nfev = sim.optimise(self.p, self.maxiter, init=init)
            # running mean of optimised angles = transferred schedule
            self._angles[n] = params if prev is None else (prev * cnt + params) / (cnt + 1)
            self._count[n] = cnt + 1
            return params
        return prev if prev is not None else linear_ramp(self.p)

    def describe(self):
        return {**super().describe(), "p": self.p, "shots": self.shots, "maxiter": self.maxiter}
