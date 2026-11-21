"""Generate the synthetic MSTAR-like SAR dataset (images + ground-truth masks).

    python scripts/generate_dataset.py --n 50 --out data/synthetic

Each sample is an .npz with ``image`` (float32 intensity) and ``labels``
(uint8: 0 background, 1 target, 2 shadow). A PNG preview strip is also written.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from quantumsar.data import load_sample, save_dataset, to_uint8  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--out", default=str(ROOT / "data" / "synthetic"))
    a = ap.parse_args()
    index = save_dataset(a.out, a.n, a.seed)
    print(f"wrote {len(index)} samples to {a.out}")
    try:
        from PIL import Image

        tiles = []
        for e in index[:10]:
            img, lab = load_sample(ROOT / "data", e["name"])
            g = to_uint8(img)
            m = (lab * 120).astype(np.uint8)
            tiles.append(np.vstack([g, m]))
        Image.fromarray(np.hstack(tiles)).resize((640 * 2, 128 * 2), Image.NEAREST).save(Path(a.out) / "preview.png")
    except Exception as e:  # noqa: BLE001
        print("preview skipped:", e)


if __name__ == "__main__":
    main()
