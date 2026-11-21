"""QUBO / Ising encoding of an MRF tile.

A tile is a rectangular block of pixels whose labels are free variables; the
pixels just outside the tile are *fixed* to their current labels and enter the
QUBO as external fields (this is what makes tiling a principled block-coordinate
descent on the full-image energy).

Binary (2-class) encoding: one bit per pixel, ``x_i = 1`` means target.

    theta_i(x)    = theta_i0 + (theta_i1 - theta_i0) x_i
    [x_i != x_j]  = x_i + x_j - 2 x_i x_j

Multi-class (K>=3) one-hot encoding: K bits per pixel ``y_ik``.

    Potts      lam [x_i != x_j] = lam (1 - sum_k y_ik y_jk)
    one-hot    P (sum_k y_ik - 1)^2 = P (1 - sum_k y_ik + 2 sum_{k<l} y_ik y_il)

The penalty ``P`` is chosen larger than any energy gain obtainable by breaking
the one-hot constraint, so every QUBO minimum is a valid labelling.

Ising form uses ``x = (1 - s) / 2`` with ``s in {+1,-1}`` the Z eigenvalue
(qubit |0> <-> x = 0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

import numpy as np

from .mrf import MRFModel


@dataclass
class TileQUBO:
    lin: np.ndarray                  # (n,)
    quad: np.ndarray                 # (n, n) strictly upper triangular
    const: float
    pixels: list[tuple[int, int]]    # tile pixels (row, col) in variable order
    n_classes: int
    penalty: float = 0.0
    meta: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.lin)

    # ---------------------------------------------------------------- evaluation
    def energy(self, bits: np.ndarray) -> np.ndarray | float:
        """Energy of one bitstring (n,) or a batch (m, n)."""
        b = np.asarray(bits, dtype=float)
        single = b.ndim == 1
        b = np.atleast_2d(b)
        e = self.const + b @ self.lin + np.einsum("mi,ij,mj->m", b, self.quad, b)
        return float(e[0]) if single else e

    def decode(self, bits: np.ndarray) -> np.ndarray:
        """Bits -> class label per tile pixel. Invalid one-hot falls back to argmax of
        the unary-preferred set bit (never happens at the QUBO optimum)."""
        bits = np.asarray(bits).astype(int)
        if self.n_classes == 2:
            return bits.copy()
        y = bits.reshape(-1, self.n_classes)
        lab = np.argmax(y, axis=1)
        lab[y.sum(axis=1) == 0] = 0
        return lab

    def encode(self, labels: np.ndarray) -> np.ndarray:
        labels = np.asarray(labels).astype(int)
        if self.n_classes == 2:
            return labels.copy()
        y = np.zeros((len(labels), self.n_classes), dtype=int)
        y[np.arange(len(labels)), labels] = 1
        return y.ravel()

    # ---------------------------------------------------------------- Ising
    def to_ising(self) -> tuple[np.ndarray, dict[tuple[int, int], float], float]:
        """Return (h, J, offset) with E = offset + sum h_i s_i + sum J_ij s_i s_j."""
        n = self.n
        h = -0.5 * self.lin.copy()
        off = self.const + 0.5 * self.lin.sum()
        J: dict[tuple[int, int], float] = {}
        ii, jj = np.nonzero(self.quad)
        for i, j in zip(ii, jj):
            q = self.quad[i, j]
            off += q / 4
            h[i] -= q / 4
            h[j] -= q / 4
            J[(int(i), int(j))] = J.get((int(i), int(j)), 0.0) + q / 4
        return h, J, float(off)


def all_bitstrings(n: int) -> np.ndarray:
    """(2^n, n) matrix; row b holds the bits of integer b, bit q = (b >> q) & 1."""
    idx = np.arange(2 ** n, dtype=np.int64)
    return ((idx[:, None] >> np.arange(n)[None, :]) & 1).astype(np.int8)


def brute_force(q: TileQUBO, max_n: int = 22) -> tuple[np.ndarray, float]:
    """Exact minimiser by exhaustive enumeration (validation / tiny tiles)."""
    if q.n > max_n:
        raise ValueError(f"brute force limited to {max_n} variables, got {q.n}")
    best_e, best_b = np.inf, None
    chunk = 1 << min(q.n, 16)
    bits_all = all_bitstrings(q.n) if q.n <= 16 else None
    if bits_all is not None:
        e = q.energy(bits_all)
        k = int(np.argmin(e))
        return bits_all[k].astype(int), float(e[k])
    # chunked enumeration for 17..22 variables
    for start in range(0, 2 ** q.n, chunk):
        idx = np.arange(start, start + chunk, dtype=np.int64)
        b = ((idx[:, None] >> np.arange(q.n)[None, :]) & 1).astype(np.int8)
        e = q.energy(b)
        k = int(np.argmin(e))
        if e[k] < best_e:
            best_e, best_b = float(e[k]), b[k].astype(int)
    return best_b, best_e


def tile_qubo(model: MRFModel, labels: np.ndarray, r0: int, c0: int, h: int, w: int) -> TileQUBO:
    """Build the QUBO of tile [r0:r0+h, c0:c0+w] with the outside fixed to ``labels``."""
    H, W, K = model.unary.shape
    lam = model.lam
    pixels = [(r, c) for r in range(r0, r0 + h) for c in range(c0, c0 + w)]
    pid = {p: i for i, p in enumerate(pixels)}
    nb_bits = 1 if K == 2 else K
    n = len(pixels) * nb_bits
    lin = np.zeros(n)
    quad = np.zeros((n, n))
    const = 0.0

    def add_q(a: int, b: int, v: float):
        i, j = (a, b) if a < b else (b, a)
        quad[i, j] += v

    internal_edges = []
    for (r, c), i in pid.items():
        th = model.unary[r, c]
        if K == 2:
            const += th[0]
            lin[i] += th[1] - th[0]
        else:
            for k in range(K):
                lin[i * K + k] += th[k]
        for dr, dc in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            rr, cc = r + dr, c + dc
            if not (0 <= rr < H and 0 <= cc < W):
                continue
            if (rr, cc) in pid:
                if (dr, dc) in ((1, 0), (0, 1)):
                    internal_edges.append((i, pid[(rr, cc)]))
                continue
            b = int(labels[rr, cc])  # fixed boundary neighbour -> external field
            if K == 2:
                if b == 0:
                    lin[i] += lam
                else:
                    const += lam
                    lin[i] -= lam
            else:
                const += lam
                lin[i * K + b] -= lam

    for i, j in internal_edges:
        if K == 2:
            lin[i] += lam
            lin[j] += lam
            add_q(i, j, -2 * lam)
        else:
            const += lam
            for k in range(K):
                add_q(i * K + k, j * K + k, -lam)

    penalty = 0.0
    if K > 2:
        # Breaking one-hot can gain at most (unary spread + 4 lam) per pixel.
        spread = float(np.ptp(model.unary[r0 : r0 + h, c0 : c0 + w], axis=2).max())
        penalty = spread + 4 * lam + 1.0
        for i in range(len(pixels)):
            const += penalty
            for k in range(K):
                lin[i * K + k] -= penalty
                for l in range(k + 1, K):
                    add_q(i * K + k, i * K + l, 2 * penalty)

    return TileQUBO(lin=lin, quad=quad, const=const, pixels=pixels, n_classes=K,
                    penalty=penalty, meta={"r0": r0, "c0": c0, "h": h, "w": w})


def tile_energy_from_model(model: MRFModel, labels: np.ndarray, q: TileQUBO, tile_labels: np.ndarray) -> float:
    """Energy of the tile-dependent part of E computed directly from the MRF
    (reference implementation used in tests to validate the QUBO)."""
    H, W, K = model.unary.shape
    lab = labels.copy()
    for (r, c), k in zip(q.pixels, tile_labels):
        lab[r, c] = k
    tile = set(q.pixels)
    e = 0.0
    for (r, c) in q.pixels:
        e += model.unary[r, c, lab[r, c]]
        for dr, dc in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            rr, cc = r + dr, c + dc
            if not (0 <= rr < H and 0 <= cc < W):
                continue
            if (rr, cc) in tile and (dr, dc) in ((-1, 0), (0, -1)):
                continue  # count internal edges once
            e += model.lam * (lab[r, c] != lab[rr, cc])
    return float(e)


def enumerate_labelings(n_pixels: int, K: int):
    return product(range(K), repeat=n_pixels)
