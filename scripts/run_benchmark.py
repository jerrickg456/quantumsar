"""Dataset-wide benchmark -> results/ (CSV tables, figures, RESULTS.md).

    python scripts/run_benchmark.py              # all samples, 2 and 3 classes
    python scripts/run_benchmark.py --quick      # 10 samples

Classiq rows come from the precomputed cache (scripts/precompute_quantum.py);
samples without a cached Classiq result are simply not reported for Classiq.
"""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from quantumsar.data import list_samples, load_sample, to_uint8  # noqa: E402
from quantumsar.edges import edges_single  # noqa: E402
from quantumsar.metrics import edge_metrics, segmentation_metrics  # noqa: E402
from quantumsar.pipeline import SOLVERS, SegParams, fit_model, load_cached_quantum, segment  # noqa: E402
from quantumsar.qubo import tile_qubo  # noqa: E402
from quantumsar.solvers.classical import ml_labels  # noqa: E402
from quantumsar.solvers.tile_solvers import LocalQAOASolver, StatevectorQAOA  # noqa: E402
from quantumsar.tiling import uncertain_mask  # noqa: E402

OUT = ROOT / "results"
FIG = OUT / "figures"
SOLVER_LIST = ["qaoa_local", "sa_tiled", "annealing", "graphcut", "icm", "otsu", "kmeans"]
SHORT = {"classiq": "QAOA (Classiq)", "qaoa_local": "QAOA (local sim)", "sa_tiled": "Tiled SA",
         "annealing": "Annealing", "graphcut": "Graph cut", "icm": "ICM", "otsu": "Otsu", "kmeans": "k-means"}
COLORS = {"classiq": "#ffa600", "qaoa_local": "#ff7c43", "sa_tiled": "#f95d6a", "annealing": "#a05195",
          "graphcut": "#665191", "icm": "#2f4b7c", "otsu": "#7a8ba8", "kmeans": "#9aa7bd"}


def run(names, classes):
    rows = []
    for i, name in enumerate(names):
        img, gt = load_sample(ROOT / "data", name)
        for nc in classes:
            base = SegParams(n_classes=nc)
            for s in SOLVER_LIST + ["classiq"]:
                prm = SegParams(**{**asdict(base), "solver": s})
                if s == "classiq" and load_cached_quantum(img, prm) is None:
                    continue
                r = segment(img, prm, gt, edges=True)
                m = r["metrics"]
                row = {"sample": name, "case": name.split("_", 2)[2], "n_classes": nc, "solver": s,
                       "mode": r["mode"], "runtime_s": r["runtime_s"], "energy": r["energy"], **m}
                if s == "classiq":  # report the wall time of the original live run
                    row["runtime_s"] = r["info"].get("cached_meta", {}).get("runtime_s", np.nan)
                info = r["info"]
                for k in ("tiles_solved", "tiles_total", "max_qubits", "qaoa_mean_p_opt",
                          "qaoa_mean_p_opt_uniform", "qaoa_found_opt_rate"):
                    if k in info:
                        row[k] = info[k]
                rows.append(row)
        print(f"[{i + 1}/{len(names)}] {name}", flush=True)
    return pd.DataFrame(rows)


def gap_to_optimum(df):
    """Relative energy gap to the exact graph-cut optimum (binary only)."""
    ref = df[(df.solver == "graphcut") & (df.n_classes == 2)].set_index("sample")["energy"]
    d = df[df.n_classes == 2].copy()
    d["energy_gap_pct"] = 100 * (d["energy"] - d["sample"].map(ref)) / d["sample"].map(ref)
    return d.groupby("solver")["energy_gap_pct"].mean()


def amplification_study(n_tiles=12):
    """How much does QAOA amplify the probability of the optimal tile labelling?"""
    img, _ = load_sample(ROOT / "data", "sar_000_normal")
    model = fit_model(img, SegParams())
    lab = ml_labels(model)
    unc = uncertain_mask(model, lab, 3.0)
    rows = []
    for t in (2, 3, 4):
        cands = [(r, c) for r in range(0, 64 - t, t) for c in range(0, 64 - t, t) if unc[r:r + t, c:c + t].any()]
        rng = np.random.default_rng(0)
        pick = [cands[i] for i in rng.choice(len(cands), min(n_tiles, len(cands)), replace=False)]
        for p in (1, 2, 3):
            ps = []
            for r, c in pick:
                q = tile_qubo(model, lab, r, c, t, t)
                sim = StatevectorQAOA(q)
                params, _, _ = sim.optimise(p, maxiter=60)
                prob = np.abs(sim.state(params)) ** 2
                ps.append(prob[np.argmin(sim.energies)] / prob.sum())
            rows.append({"qubits": t * t, "p": p, "p_opt": float(np.mean(ps)), "uniform": 1 / 2 ** (t * t),
                         "amplification": float(np.mean(ps) * 2 ** (t * t))})
            print("amplification", rows[-1], flush=True)
    return pd.DataFrame(rows)


def figures(df, amp):
    FIG.mkdir(parents=True, exist_ok=True)
    plt.style.use("dark_background")
    # 1. bars: IoU and runtime per solver, 2- and 3-class
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    for ax, nc in zip(axes[:2], (2, 3)):
        g = df[df.n_classes == nc].groupby("solver")["iou"].mean().sort_values()
        ax.barh([SHORT[s] for s in g.index], g.values, color=[COLORS[s] for s in g.index])
        ax.set_xlim(0, 1)
        ax.set_title(f"Mean IoU, {nc} classes")
        for y, v in enumerate(g.values):
            ax.text(v + 0.01, y, f"{v:.3f}", va="center", fontsize=9)
    g = df[df.n_classes == 2].groupby("solver")["runtime_s"].median().sort_values()
    axes[2].barh([SHORT[s] for s in g.index], g.values, color=[COLORS[s] for s in g.index])
    axes[2].set_xscale("log")
    axes[2].set_title("Median runtime per image, 2 classes (s, log)")
    fig.tight_layout()
    fig.savefig(FIG / "benchmark_bars.png", dpi=130)
    plt.close(fig)

    # 2. IoU per case
    piv = df[df.n_classes == 2].groupby(["case", "solver"])["iou"].mean().unstack()
    ax = piv[[s for s in SHORT if s in piv]].rename(columns=SHORT).plot.bar(
        figsize=(12, 4.5), color=[COLORS[s] for s in SHORT if s in piv], width=0.85)
    ax.set_ylabel("IoU (target)")
    ax.set_title("IoU by image type (2 classes)")
    ax.legend(ncol=4, fontsize=8)
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig(FIG / "iou_by_case.png", dpi=130)
    plt.close()

    # 3. QAOA amplification
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    for p, g in amp.groupby("p"):
        ax.plot(g.qubits, g.amplification, "o-", label=f"p = {p}")
    ax.set_yscale("log")
    ax.set_xlabel("qubits per tile")
    ax.set_ylabel("P(optimum) / P(random guess)")
    ax.set_title("QAOA amplification of the optimal tile labelling")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "qaoa_amplification.png", dpi=130)
    plt.close(fig)

    # 4. qualitative grid
    names = ["sar_000_normal", "sar_002_low_snr", "sar_003_no_target", "sar_004_speckled"]
    sol = ["graphcut", "qaoa_local", "otsu"]
    fig, axes = plt.subplots(len(names), 2 + len(sol) + 1, figsize=(14, 2.6 * len(names)))
    cmap = matplotlib.colors.ListedColormap(["#283042", "#ffa600", "#4084ff"])
    for i, n in enumerate(names):
        img, gt = load_sample(ROOT / "data", n)
        axes[i, 0].imshow(to_uint8(img), cmap="gray")
        axes[i, 1].imshow(gt, cmap=cmap, vmin=0, vmax=2)
        for j, s in enumerate(sol):
            r = segment(img, SegParams(solver=s, n_classes=3), gt)
            axes[i, 2 + j].imshow(r["labels"], cmap=cmap, vmin=0, vmax=2)
            axes[i, 2 + j].set_title(f"{SHORT[s]}  IoU {r['metrics']['iou']:.2f}", fontsize=9)
        r = segment(img, SegParams(solver="qaoa_local", n_classes=3), gt, edges=True)
        axes[i, -1].imshow(r["edge_classes"], cmap=matplotlib.colors.ListedColormap(["black", "#ff3c3c", "#50e6ff"]),
                           vmin=0, vmax=2)
        axes[i, 0].set_ylabel(n.split("_", 2)[2], fontsize=10)
    for ax, t in zip(axes[0], ["input", "ground truth"]):
        ax.set_title(t, fontsize=9)
    axes[0, -1].set_title("edges (QAOA)", fontsize=9)
    for ax in axes.ravel():
        ax.set_xticks([])
        ax.set_yticks([])
    fig.tight_layout()
    fig.savefig(FIG / "examples_3class.png", dpi=110)
    plt.close(fig)


def write_markdown(df, amp, gaps):
    agg = {"accuracy": "mean", "iou": "mean", "dice": "mean", "runtime_s": "median", "energy": "mean",
           "sample": "count"}
    lines = ["# QuantumSAR benchmark results", "",
             f"Synthetic MSTAR-like dataset, {df['sample'].nunique()} images of 64x64. "
             "Classiq rows only cover the images whose Classiq run is cached "
             "(`results/quantum_cache/`); runtime for Classiq is the wall time of the live cloud run.", ""]
    for nc in (2, 3):
        d = df[df.n_classes == nc]
        if d.empty:
            continue
        t = d.groupby("solver").agg(agg).rename(columns={"sample": "images", "runtime_s": "median runtime (s)"})
        if nc == 2:
            t["energy gap to optimum (%)"] = gaps
            if "edge_f1" in d:
                t["edge F1"] = d.groupby("solver")["edge_f1"].mean()
        t.index = [SHORT[s] for s in t.index]
        t = t.sort_values("iou", ascending=False)
        lines += [f"## {nc} classes", "", t.to_markdown(floatfmt=".3f"), ""]
    piv = df[df.n_classes == 2].groupby(["case", "solver"])["iou"].mean().unstack().rename(columns=SHORT)
    lines += ["## IoU by image type (2 classes)", "", piv.to_markdown(floatfmt=".3f"), ""]
    lines += ["## QAOA amplification", "", "Mean probability of measuring the exact optimum of a tile, "
              "QAOA vs. uniform random guessing (12 uncertain tiles per size).", "",
              amp.to_markdown(index=False, floatfmt=".4g"), ""]
    lines += ["![bars](figures/benchmark_bars.png)", "", "![cases](figures/iou_by_case.png)", "",
              "![amp](figures/qaoa_amplification.png)", "", "![examples](figures/examples_3class.png)", ""]
    (OUT / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--classes", default="2,3")
    ap.add_argument("--skip-amp", action="store_true")
    a = ap.parse_args()
    names = [n for n in list_samples(ROOT / "data") if not n.startswith("mstar/")]
    if a.quick:
        names = names[:10]
    df = run(names, [int(c) for c in a.classes.split(",")])
    OUT.mkdir(exist_ok=True)
    df.to_csv(OUT / "benchmark_full.csv", index=False)
    summ = df.groupby(["n_classes", "solver"]).agg(
        images=("sample", "count"), accuracy=("accuracy", "mean"), iou=("iou", "mean"), dice=("dice", "mean"),
        runtime_s_median=("runtime_s", "median"), energy=("energy", "mean")).round(4).reset_index()
    summ.insert(2, "name", summ["solver"].map(SHORT))
    summ.to_csv(OUT / "benchmark_summary.csv", index=False)
    amp_path = OUT / "qaoa_amplification.csv"
    if a.skip_amp and amp_path.exists():
        amp = pd.read_csv(amp_path)
    else:
        amp = amplification_study()
        amp.to_csv(amp_path, index=False)
    gaps = gap_to_optimum(df)
    figures(df, amp)
    write_markdown(df, amp, gaps)
    print(summ.to_string())
    print("energy gap to optimum (%):\n", gaps.round(3).to_string())


if __name__ == "__main__":
    main()
