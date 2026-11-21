"""Fill the Results section of docs/PROJECT_GUIDE.md with a simple table.

Uses results/benchmark_full.csv when it exists; otherwise runs the main solvers
on all bundled images (Classiq rows come from the stored Classiq runs).
"""
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from quantumsar.data import list_samples, load_sample  # noqa: E402
from quantumsar.pipeline import SegParams, load_cached_quantum, segment  # noqa: E402

NAMES = {"classiq": "**QAOA on Classiq (quantum)**", "qaoa_local": "QAOA, local simulator (quantum)",
         "graphcut": "Graph cut (classical, exact)", "annealing": "Simulated annealing (classical)",
         "sa_tiled": "Quantum-inspired annealing", "icm": "ICM (classical)",
         "otsu": "Otsu threshold (classical)", "kmeans": "k-means (classical)"}
ORDER = list(NAMES)


def collect() -> pd.DataFrame:
    full = ROOT / "results" / "benchmark_full.csv"
    if full.exists() and pd.read_csv(full)["sample"].nunique() >= 50:
        return pd.read_csv(full)
    rows = []
    names = [n for n in list_samples(ROOT / "data") if not n.startswith("mstar/")]
    for name in names:
        img, gt = load_sample(ROOT / "data", name)
        for nc in (2, 3):
            for s in ["classiq", "qaoa_local", "graphcut", "annealing", "icm", "otsu", "kmeans"]:
                prm = SegParams(n_classes=nc, solver=s)
                if s == "classiq" and load_cached_quantum(img, prm) is None:
                    continue
                r = segment(img, prm, gt)
                rows.append({"sample": name, "n_classes": nc, "solver": s, "runtime_s": r["runtime_s"],
                             "energy": r["energy"], **r["metrics"]})
        print(name, flush=True)
    return pd.DataFrame(rows)


def table(df: pd.DataFrame, nc: int) -> str:
    d = df[df.n_classes == nc]
    g = d.groupby("solver").agg(images=("sample", "nunique"), acc=("accuracy", "mean"), iou=("iou", "mean"),
                                rt=("runtime_s", "median"))
    lines = ["| Method | Images | Accuracy | IoU | Typical time per image |", "|---|---|---|---|---|"]
    for s in ORDER:
        if s in g.index:
            r = g.loc[s]
            t = f"{r.rt:.0f} s (Classiq cloud)" if s == "classiq" else (f"{r.rt * 1000:.0f} ms" if r.rt < 1 else f"{r.rt:.1f} s")
            label = "Graph cut, α-expansion (classical)" if (s == "graphcut" and nc == 3) else NAMES[s]
            lines.append(f"| {label} | {int(r.images)} | {100 * r.acc:.1f} % | {r.iou:.3f} | {t} |")
    return "\n".join(lines)


def main():
    df = collect()
    gc = df[(df.n_classes == 2) & (df.solver == "graphcut")].set_index("sample")["energy"]
    cq = df[(df.n_classes == 2) & (df.solver == "classiq")].set_index("sample")["energy"]
    common = cq.index.intersection(gc.index)
    gap = 100 * ((cq[common] - gc[common]) / gc[common]).mean()
    same = (abs(cq[common] - gc[common]) < 1e-6).mean()
    text = f"""Tested on **50 synthetic MSTAR-like radar images** (normal, low-contrast, no-vehicle and very speckled
cases). The Classiq rows are real runs on Classiq's cloud simulator.

**2 classes (vehicle vs. background)**

{table(df, 2)}

On the {len(common)} images, QAOA on Classiq reached **the exact best energy (same as graph cut) on
{100 * same:.0f} % of them**, and on average it was within **{gap:.2f} %** of the exact optimum.

**3 classes (vehicle, shadow, background)**

{table(df, 3)}
"""
    p = ROOT / "docs" / "PROJECT_GUIDE.md"
    s = p.read_text(encoding="utf-8")
    start, end = "<!-- RESULTS-TABLE -->", "<!-- /RESULTS-TABLE -->"
    if end in s:
        s = s[: s.index(start)] + start + "\n" + text + end + s[s.index(end) + len(end):]
    else:
        s = s.replace(start, start + "\n" + text + end)
    p.write_text(s, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
