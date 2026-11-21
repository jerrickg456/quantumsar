"""Segmentation quality metrics."""
from __future__ import annotations

import numpy as np


def _iou_dice(pred: np.ndarray, gt: np.ndarray) -> tuple[float, float]:
    inter = np.logical_and(pred, gt).sum()
    union = np.logical_or(pred, gt).sum()
    s = pred.sum() + gt.sum()
    if union == 0:  # both empty (e.g. image without a target): perfect
        return 1.0, 1.0
    return float(inter / union), float(2 * inter / s)


def segmentation_metrics(pred: np.ndarray, gt: np.ndarray, n_classes: int = 2) -> dict:
    pred = np.asarray(pred).astype(int)
    gt = np.asarray(gt).astype(int)
    if n_classes == 2:
        gt = (gt == 1).astype(int)  # shadow counts as background in 2-class mode
        pred = (pred == 1).astype(int)
    out = {"accuracy": float((pred == gt).mean())}
    ious, dices = [], []
    for k in range(1, n_classes):
        i, d = _iou_dice(pred == k, gt == k)
        name = {1: "target", 2: "shadow"}[k]
        out[f"iou_{name}"], out[f"dice_{name}"] = i, d
        ious.append(i)
        dices.append(d)
    out["iou"] = float(np.mean(ious))
    out["dice"] = float(np.mean(dices))
    return out


def edge_metrics(pred_edges: np.ndarray, gt_edges: np.ndarray) -> dict:
    p, g = np.asarray(pred_edges) > 0, np.asarray(gt_edges) > 0
    tp = np.logical_and(p, g).sum()
    prec = tp / p.sum() if p.sum() else float(g.sum() == 0)
    rec = tp / g.sum() if g.sum() else float(p.sum() == 0)
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"edge_precision": float(prec), "edge_recall": float(rec), "edge_f1": float(f1)}
