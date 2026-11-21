"""Markov Random Field model for SAR segmentation.

Energy (MAP inference, Thales use case):

    E(x, z) = sum_i theta_i(x_i, z_i) + lambda * sum_{(i,j) in E} [x_i != x_j]

* Unary term ``theta_i(k)``: negative log-likelihood of the observed intensity
  ``z_i`` under a Gamma speckle model with ``L`` looks and class mean ``mu_k``::

      -log p(z | mu_k) = L * (z / mu_k + log mu_k) + const(z)

* Pairwise term: Potts prior (Ising for 2 classes) over the 4-neighbour grid.

Class order in label space is fixed: 0 = background, 1 = target, 2 = shadow.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class MRFModel:
    unary: np.ndarray        # (H, W, K) unary costs theta_i(k)
    lam: float               # Potts smoothness weight
    means: np.ndarray        # (K,) class means used for the unary
    looks: float

    @property
    def n_classes(self) -> int:
        return self.unary.shape[2]

    @property
    def shape(self) -> tuple[int, int]:
        return self.unary.shape[:2]


def _kmeans_1d(x: np.ndarray, init: np.ndarray, iters: int = 30) -> np.ndarray:
    c = init.astype(float).copy()
    for _ in range(iters):
        lab = np.argmin(np.abs(x[:, None] - c[None, :]), axis=1)
        new = np.array([x[lab == k].mean() if np.any(lab == k) else c[k] for k in range(len(c))])
        if np.allclose(new, c):
            break
        c = new
    return c


def estimate_means(img: np.ndarray, n_classes: int, min_ratio_db: float = 3.0) -> np.ndarray:
    """Unsupervised class means in label order [background, target, (shadow)].

    Background clutter dominates SAR chips, so its mean is estimated robustly
    from the central part of the histogram. Target / shadow means come from a
    1-D k-means on log-intensity, but are kept at least ``min_ratio_db`` away
    from the background so pure-clutter chips do not get a spurious target.
    """
    z = np.asarray(img, dtype=float).ravel()
    z = np.maximum(z, 1e-6)
    lz = np.log(z)
    q = np.quantile(lz, [0.1, 0.5, 0.97])
    if n_classes == 2:
        c = _kmeans_1d(lz, np.array([q[1], q[2]]))
        bg, tg = np.exp(c[0]), np.exp(c[1])
    else:
        c = _kmeans_1d(lz, np.array([q[1], q[2], q[0]]))
        bg, tg = np.exp(c[0]), np.exp(c[1])
    # robust background: trimmed mean of the middle of the distribution
    lo, hi = np.quantile(z, [0.05, 0.80])
    bg = float(z[(z >= lo) & (z <= hi)].mean() * 1.12)
    r = 10 ** (min_ratio_db / 10)
    tg = max(float(tg), bg * r)
    if n_classes == 2:
        return np.array([bg, tg])
    sh = min(float(np.exp(c[2])), bg / r)
    return np.array([bg, tg, sh])


def estimate_looks(img: np.ndarray, lo: float = 0.5, hi: float = 16.0) -> float:
    """Equivalent number of looks (ENL) from the spread of log-intensity.

    For Gamma(L) speckle Var[log z] = trigamma(L). Clutter dominates SAR chips,
    so a robust (MAD-based) spread of log z over the image estimates L."""
    from scipy.special import polygamma

    lz = np.log(np.maximum(np.asarray(img, float).ravel(), 1e-6))
    mad = np.median(np.abs(lz - np.median(lz)))
    var = (1.4826 * mad) ** 2
    Ls = np.geomspace(lo, hi, 200)
    return float(Ls[np.argmin(np.abs(polygamma(1, Ls) - var))])


def build_model(
    img: np.ndarray,
    n_classes: int = 2,
    lam: float = 1.5,
    looks: float = 3.0,
    means: np.ndarray | None = None,
) -> MRFModel:
    z = np.maximum(np.asarray(img, dtype=float), 1e-6)
    if means is None:
        means = estimate_means(z, n_classes)
    means = np.asarray(means, dtype=float)
    unary = looks * (z[..., None] / means[None, None, :] + np.log(means)[None, None, :])
    unary -= unary.min(axis=2, keepdims=True)  # constant shift per pixel, argmin unchanged
    return MRFModel(unary=unary, lam=float(lam), means=means, looks=float(looks))


def refit_means(img: np.ndarray, labels: np.ndarray, prev: np.ndarray, min_count: int = 10) -> np.ndarray:
    """M-step of ICM-EM: class means from the current labelling (Gamma MLE = mean)."""
    z = np.asarray(img, dtype=float)
    out = prev.copy()
    for k in range(len(prev)):
        m = labels == k
        if m.sum() >= min_count:
            out[k] = z[m].mean()
    # keep the semantic order intact (target brightest, shadow darkest)
    out[1] = max(out[1], out[0] * 1.2)
    if len(out) > 2:
        out[2] = min(out[2], out[0] / 1.2)
    return out


def energy(model: MRFModel, labels: np.ndarray) -> float:
    """Total MRF energy of a full labelling."""
    H, W = labels.shape
    u = np.take_along_axis(model.unary, labels[..., None].astype(int), axis=2).sum()
    pw = (labels[1:, :] != labels[:-1, :]).sum() + (labels[:, 1:] != labels[:, :-1]).sum()
    return float(u + model.lam * pw)


def local_costs(model: MRFModel, labels: np.ndarray) -> np.ndarray:
    """(H, W, K) conditional energy of assigning each class to each pixel,
    holding its 4 neighbours fixed (used by ICM / annealing / tile selection)."""
    H, W, K = model.unary.shape
    cost = model.unary.copy()
    pad = np.pad(labels, 1, constant_values=-1)
    neigh = [pad[:-2, 1:-1], pad[2:, 1:-1], pad[1:-1, :-2], pad[1:-1, 2:]]
    for k in range(K):
        for nb in neigh:
            cost[..., k] += model.lam * ((nb != k) & (nb >= 0))
    return cost
