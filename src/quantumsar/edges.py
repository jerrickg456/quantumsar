"""Edge detection on a segmentation (Thales extension b/c).

* ``edges_double``: every pixel with at least one 4-neighbour of a different
  class (the definition in the use case: edges are 2 pixels wide).
* ``edges_single``: one pixel per edge - only the pixel on the higher-priority
  side (target > shadow > background) of each class transition is marked.
* Multi-class edge map: value = class whose boundary the pixel lies on
  (1 = target edge, 2 = shadow edge), distinguishing object vs shadow edges.
"""
from __future__ import annotations

import numpy as np

PRIORITY = np.array([0, 2, 1])  # background < shadow < target


def _neighbours(lab: np.ndarray):
    pad = np.pad(lab, 1, mode="edge")
    return [pad[:-2, 1:-1], pad[2:, 1:-1], pad[1:-1, :-2], pad[1:-1, 2:]]


def edges_double(labels: np.ndarray) -> np.ndarray:
    lab = np.asarray(labels)
    e = np.zeros(lab.shape, dtype=bool)
    for nb in _neighbours(lab):
        e |= nb != lab
    return e.astype(np.uint8)


def edges_single(labels: np.ndarray) -> np.ndarray:
    lab = np.asarray(labels).astype(int)
    pr = PRIORITY[lab]
    e = np.zeros(lab.shape, dtype=bool)
    for nb in _neighbours(lab):
        e |= (nb != lab) & (pr > PRIORITY[nb])
    return e.astype(np.uint8)


def edge_classes(labels: np.ndarray, single: bool = True) -> np.ndarray:
    """Edge pixels labelled with the class of the region they bound."""
    lab = np.asarray(labels).astype(np.uint8)
    e = edges_single(lab) if single else edges_double(lab)
    out = np.zeros_like(lab)
    if single:
        out[e > 0] = lab[e > 0]
    else:
        # for the 2-pixel definition attribute background-side pixels to the
        # foreground class they touch
        out[e > 0] = lab[e > 0]
        for nb in _neighbours(lab):
            m = (e > 0) & (out == 0) & (nb > 0)
            out[m] = nb[m]
    return out
