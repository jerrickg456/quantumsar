"""Quick development benchmark on N generated samples (no files written)."""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from quantumsar.data import default_specs, make_sample  # noqa: E402
from quantumsar.pipeline import SegParams, benchmark  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("-n", type=int, default=10)
ap.add_argument("--classes", default="2,3")
ap.add_argument("--solvers", default="qaoa_local,sa_tiled,annealing,graphcut,icm,otsu,kmeans")
ap.add_argument("--lam", type=float, default=1.5)
a = ap.parse_args()

rows = []
for name, spec in default_specs(a.n):
    img, gt = make_sample(spec)
    for nc in map(int, a.classes.split(",")):
        for r in benchmark(img, gt, SegParams(n_classes=nc, lam=a.lam), a.solvers.split(",")):
            r.update(sample=name, n_classes=nc)
            rows.append(r)
df = pd.DataFrame(rows)
if "error" in df:
    print(df[df["error"].notna()][["solver", "n_classes", "error"]].drop_duplicates())
df["kind"] = df["sample"].str.split("_").str[2]
pd.set_option("display.width", 220)
print(df.groupby(["n_classes", "solver"])[["accuracy", "iou", "dice", "energy", "runtime_s"]].mean().round(3))
print(df.groupby(["n_classes", "kind", "solver"])["iou"].mean().round(3).unstack("solver").to_string())
