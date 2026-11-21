"""Run QAOA-on-Classiq on bundled samples and store the results in the cache
(results/quantum_cache/) so the deployed app can serve *real* Classiq results
without credentials. Requires Classiq auth (see src/quantumsar/auth.py).

    python scripts/precompute_quantum.py --classes 2 --limit 50
    python scripts/precompute_quantum.py --classes 3 --limit 10

Existing cache entries are skipped, so the script can be resumed.
"""
import argparse
import datetime as dt
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantumsar.auth import classiq_ready, setup_classiq_auth  # noqa: E402

setup_classiq_auth()

import classiq  # noqa: E402

from quantumsar.data import list_samples, load_sample  # noqa: E402
from quantumsar.metrics import segmentation_metrics  # noqa: E402
from quantumsar.pipeline import SegParams, load_cached_quantum, run_solver, save_cached_quantum  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", type=int, default=2)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--only", default="", help="comma separated sample names")
    a = ap.parse_args()
    ok, msg = classiq_ready(120)
    print(msg, flush=True)
    if not ok:
        sys.exit(1)
    names = [n for n in list_samples(ROOT / "data") if not n.startswith("mstar/")]
    if a.only:
        names = [n for n in names if n in a.only.split(",")]
    names = names[: a.limit]
    log = ROOT / "results" / "precompute_log.jsonl"
    log.parent.mkdir(exist_ok=True)
    for i, name in enumerate(names):
        img, gt = load_sample(ROOT / "data", name)
        prm = SegParams(solver="classiq", n_classes=a.classes, allow_live_classiq=True)
        if load_cached_quantum(img, prm) is not None:
            print(f"[{i + 1}/{len(names)}] {name}: cached, skip", flush=True)
            continue
        t0 = time.time()
        res = run_solver(img, prm)
        if "live" not in res["mode"]:
            print(f"{name}: Classiq did not run live ({res['mode']}); aborting", flush=True)
            sys.exit(2)
        m = segmentation_metrics(res["labels"], gt, a.classes) if gt is not None else {}
        meta = {"sample": name, "params": asdict(prm), "mode": res["mode"], "runtime_s": res["runtime_s"],
                "energy": res["energy"], "metrics": m, "classiq_version": classiq.__version__,
                "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "tiling": {k: v for k, v in res["info"].items()}}
        save_cached_quantum(img, prm, res["labels"], meta)
        with log.open("a") as f:
            f.write(json.dumps({k: meta[k] for k in ("sample", "runtime_s", "energy", "metrics", "created")}
                               | {"n_classes": a.classes}) + "\n")
        print(f"[{i + 1}/{len(names)}] {name}: iou={m.get('iou', float('nan')):.3f} "
              f"t={time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
