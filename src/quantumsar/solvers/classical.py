"""Classical baselines: Otsu, k-means, ICM, simulated annealing, graph cut."""
from __future__ import annotations

import numpy as np

from ..mrf import MRFModel, local_costs


# ------------------------------------------------------------------ thresholding
def _otsu_threshold(x: np.ndarray, bins: int = 256) -> float:
    hist, edges = np.histogram(x, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m = np.cumsum(hist * centers)
    mu0 = m / np.maximum(w0, 1)
    mu1 = (m[-1] - m) / np.maximum(w1, 1)
    var_between = w0 * w1 * (mu0 - mu1) ** 2
    return float(centers[np.argmax(var_between)])


def despeckle(img: np.ndarray, size: int = 5) -> np.ndarray:
    """Log-domain box filter (a simple multi-look average) used before the
    pixel-wise baselines; without it Otsu / k-means just segment speckle."""
    from scipy.ndimage import uniform_filter

    return uniform_filter(np.log(np.maximum(img, 1e-6)), size=size, mode="reflect")


def otsu(img: np.ndarray, n_classes: int = 2, filter_size: int = 5) -> np.ndarray:
    """Otsu on despeckled log-intensity. 3 classes: two-level multi-Otsu (exhaustive)."""
    x = despeckle(img, filter_size) if filter_size else np.log(np.maximum(img, 1e-6))
    if n_classes == 2:
        return (x > _otsu_threshold(x)).astype(np.uint8)
    hist, edges = np.histogram(x, bins=128)
    p = hist / hist.sum()
    c = (edges[:-1] + edges[1:]) / 2
    best, tt = -1.0, (0, 0)
    P, M = np.cumsum(p), np.cumsum(p * c)
    mt = M[-1]
    for a in range(1, 126):
        for b in range(a + 1, 127):
            w = [P[a], P[b] - P[a], 1 - P[b]]
            if min(w) <= 0:
                continue
            m = [M[a] / w[0], (M[b] - M[a]) / w[1], (mt - M[b]) / w[2]]
            v = sum(wi * (mi - mt) ** 2 for wi, mi in zip(w, m))
            if v > best:
                best, tt = v, (c[a], c[b])
    out = np.zeros(img.shape, dtype=np.uint8)  # middle band = background
    out[x > tt[1]] = 1
    out[x <= tt[0]] = 2
    return out


def kmeans(img: np.ndarray, n_classes: int = 2, iters: int = 50, filter_size: int = 5) -> np.ndarray:
    """Lloyd k-means on despeckled log-intensity, clusters mapped to semantic labels."""
    x = (despeckle(img, filter_size) if filter_size else np.log(np.maximum(img, 1e-6))).ravel()
    qs = [0.5, 0.97] if n_classes == 2 else [0.5, 0.97, 0.03]
    c = np.quantile(x, qs)
    for _ in range(iters):
        lab = np.argmin(np.abs(x[:, None] - c[None]), axis=1)
        new = np.array([x[lab == k].mean() if np.any(lab == k) else c[k] for k in range(n_classes)])
        if np.allclose(new, c):
            break
        c = new
    return lab.reshape(img.shape).astype(np.uint8)


# ------------------------------------------------------------------ MRF solvers
def ml_labels(model: MRFModel) -> np.ndarray:
    """Pixel-wise maximum likelihood (no smoothness)."""
    return np.argmin(model.unary, axis=2).astype(np.uint8)


def icm(model: MRFModel, init: np.ndarray | None = None, max_sweeps: int = 30) -> np.ndarray:
    """Iterated Conditional Modes with checkerboard (red/black) updates."""
    lab = ml_labels(model) if init is None else init.astype(np.uint8).copy()
    H, W = lab.shape
    checker = (np.add.outer(np.arange(H), np.arange(W)) % 2).astype(bool)
    for _ in range(max_sweeps):
        changed = 0
        for color in (False, True):
            best = np.argmin(local_costs(model, lab), axis=2).astype(np.uint8)
            m = (checker == color) & (best != lab)
            lab[m] = best[m]
            changed += int(m.sum())
        if changed == 0:
            break
    return lab


def simulated_annealing(
    model: MRFModel,
    init: np.ndarray | None = None,
    sweeps: int = 300,
    t0: float = 3.0,
    t1: float = 0.05,
    seed: int = 0,
) -> np.ndarray:
    """Metropolis/Gibbs annealing on the full Potts MRF (checkerboard-parallel)."""
    rng = np.random.default_rng(seed)
    lab = ml_labels(model) if init is None else init.astype(np.uint8).copy()
    H, W, K = model.unary.shape
    checker = (np.add.outer(np.arange(H), np.arange(W)) % 2).astype(bool)
    temps = t0 * (t1 / t0) ** (np.arange(sweeps) / max(sweeps - 1, 1))
    for T in temps:
        for color in (False, True):
            cost = local_costs(model, lab)
            # heat-bath (Gibbs) sampling of each pixel's label
            logits = -(cost - cost.min(axis=2, keepdims=True)) / T
            p = np.exp(logits)
            p /= p.sum(axis=2, keepdims=True)
            u = rng.random((H, W, 1))
            new = (np.cumsum(p, axis=2) < u).sum(axis=2).clip(0, K - 1).astype(np.uint8)
            lab[checker == color] = new[checker == color]
    return icm(model, lab, max_sweeps=5)  # quench


def graph_cut(model: MRFModel) -> np.ndarray:
    """Exact MAP for the binary Ising/Potts MRF via s-t min-cut (PyMaxflow)."""
    import maxflow

    H, W, K = model.unary.shape
    if K != 2:
        return alpha_expansion(model)
    g = maxflow.Graph[float]()
    ids = g.add_grid_nodes((H, W))
    g.add_grid_edges(ids, weights=model.lam, symmetric=True,
                     structure=np.array([[0, 0, 0], [0, 0, 1], [0, 1, 0]]))
    # source capacity = cost of label 1, sink capacity = cost of label 0
    g.add_grid_tedges(ids, model.unary[..., 1], model.unary[..., 0])
    g.maxflow()
    return g.get_grid_segments(ids).astype(np.uint8)  # True = sink side = label 1


def alpha_expansion(model: MRFModel, init: np.ndarray | None = None, cycles: int = 5) -> np.ndarray:
    """Boykov-Veksler-Zabih alpha-expansion for Potts (2-approximation for K>2)."""
    import maxflow

    from ..mrf import energy

    H, W, K = model.unary.shape
    lab = ml_labels(model) if init is None else init.astype(np.uint8).copy()
    lam = model.lam
    best_e = energy(model, lab)
    for _ in range(cycles):
        improved = False
        for a in range(K):
            g = maxflow.Graph[float]()
            ids = g.add_grid_nodes((H, W))
            # node on sink side => switches to alpha
            keep = np.take_along_axis(model.unary, lab[..., None].astype(int), 2)[..., 0]
            to_a = model.unary[..., a]
            # Pairwise terms use the Kolmogorov-Zabih construction per 4-neighbour edge.
            # x=1 (sink side) means "switch to alpha"; the source capacity is the
            # cost paid when x=1, the sink capacity the cost paid when x=0.
            src, snk = to_a.copy(), keep.copy()
            for (dr, dc) in ((0, 1), (1, 0)):
                li = lab[: H - dr, : W - dc]
                lj = lab[dr:, dc:]
                # E(0,0)=lam[li!=lj], E(0,1)=lam[li!=a], E(1,0)=lam[a!=lj], E(1,1)=0
                A = lam * (li != lj)
                B = lam * (li != a)
                C = lam * (lj != a)
                D = np.zeros_like(A, dtype=float)
                # decomposition: E = A + (C-A)x_i + (D-C)x_j + (B+C-A-D) * (1-x_i) x_j
                sl_i = (slice(0, H - dr), slice(0, W - dc))
                sl_j = (slice(dr, H), slice(dc, W))
                const_i = (C - A)
                const_j = (D - C)
                # x=1 means "sink" (take alpha); unary cost for x_i=1 adds to source cap
                src_i = np.zeros((H, W)); snk_i = np.zeros((H, W))
                for arr, sl in ((const_i, sl_i), (const_j, sl_j)):
                    pos = np.clip(arr, 0, None)
                    neg = np.clip(-arr, 0, None)
                    tmp_s = np.zeros((H, W)); tmp_t = np.zeros((H, W))
                    tmp_s[sl] = pos
                    tmp_t[sl] = neg
                    src_i += tmp_s
                    snk_i += tmp_t
                src += src_i
                snk += snk_i
                w = B + C - A - D  # >= 0 for Potts (metric)
                for r in range(H - dr):
                    for c in range(W - dc):
                        if w[r, c] > 0:
                            # cost w when x_i=0 (source) and x_j=1 (sink): edge i->j
                            g.add_edge(ids[r, c], ids[r + dr, c + dc], w[r, c], 0.0)
            g.add_grid_tedges(ids, src, snk)
            g.maxflow()
            seg = g.get_grid_segments(ids)
            cand = lab.copy()
            cand[seg] = a
            e = energy(model, cand)
            if e < best_e - 1e-9:
                lab, best_e, improved = cand, e, True
        if not improved:
            break
    return lab
