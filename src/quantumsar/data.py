"""Synthetic SAR data generation and MSTAR loading.

SAR intensity images are well modelled by *multiplicative* speckle: the observed
intensity is ``I = R * S`` where ``R`` is the underlying reflectivity and ``S``
follows a unit-mean Gamma distribution with shape ``L`` (the number of looks).
We generate MSTAR-like 64x64 chips containing

* a bright, roughly rectangular / elliptical *target* (class 1),
* a dark *shadow* cast behind it, away from the radar (class 2),
* homogeneous clutter *background* (class 0).

``snr_db`` is the target-to-background reflectivity ratio in dB, so low values
produce the "low signal-to-noise" cases requested by the use case.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

BACKGROUND, TARGET, SHADOW = 0, 1, 2


@dataclass
class SampleSpec:
    size: int = 64
    snr_db: float = 8.0          # target / background reflectivity ratio (dB)
    shadow_db: float = -6.0      # shadow / background reflectivity ratio (dB)
    looks: float = 3.0           # Gamma speckle shape parameter L
    has_target: bool = True
    target_len: float = 18.0     # target extent along its main axis (pixels)
    target_wid: float = 9.0
    angle_deg: float = 30.0
    shadow_len: float = 12.0     # shadow extent behind the target (pixels)
    seed: int = 0


def _rotated_coords(size: int, cx: float, cy: float, angle: float):
    yy, xx = np.mgrid[0:size, 0:size].astype(float)
    dx, dy = xx - cx, yy - cy
    c, s = np.cos(angle), np.sin(angle)
    u = c * dx + s * dy          # along main axis
    v = -s * dx + c * dy         # across
    return u, v, yy


def make_sample(spec: SampleSpec) -> tuple[np.ndarray, np.ndarray]:
    """Return (intensity image float32, ground-truth labels uint8 in {0,1,2})."""
    rng = np.random.default_rng(spec.seed)
    n = spec.size
    labels = np.zeros((n, n), dtype=np.uint8)
    if spec.has_target:
        cx = n / 2 + rng.uniform(-6, 6)
        cy = n / 2 + rng.uniform(-8, 2)
        ang = np.deg2rad(spec.angle_deg)
        u, v, yy = _rotated_coords(n, cx, cy, ang)
        # super-ellipse => vehicle-like rounded rectangle
        a, b = spec.target_len / 2, spec.target_wid / 2
        target = (np.abs(u / a) ** 4 + np.abs(v / b) ** 4) <= 1.0
        # Shadow: the target footprint swept "down-range" (towards +y),
        # i.e. pixels hidden behind the target from a radar looking from -y.
        shadow = np.zeros_like(target)
        ys, xs = np.nonzero(target)
        for k in range(1, int(spec.shadow_len) + 1):
            yk = np.clip(ys + k, 0, n - 1)
            shadow[yk, xs] = True
        shadow &= ~target
        labels[shadow] = SHADOW
        labels[target] = TARGET

    refl = np.ones((n, n))
    refl[labels == TARGET] = 10 ** (spec.snr_db / 10)
    refl[labels == SHADOW] = 10 ** (spec.shadow_db / 10)
    # mild texture on the target (bright scatterers), as in real MSTAR chips
    if spec.has_target:
        tex = rng.gamma(4.0, 1 / 4.0, size=(n, n))
        refl[labels == TARGET] *= tex[labels == TARGET]
    speckle = rng.gamma(spec.looks, 1.0 / spec.looks, size=(n, n))
    img = (refl * speckle).astype(np.float32)
    return img, labels


def to_uint8(img: np.ndarray) -> np.ndarray:
    """Log-scale display normalisation (how SAR chips are usually shown)."""
    x = np.log1p(np.asarray(img, dtype=float))
    lo, hi = np.percentile(x, [0.5, 99.5])
    return (np.clip((x - lo) / max(hi - lo, 1e-9), 0, 1) * 255).astype(np.uint8)


def default_specs(n: int = 50, seed: int = 1234) -> list[tuple[str, SampleSpec]]:
    """A varied benchmark set: normal, low-SNR, no-target and few-looks cases."""
    rng = np.random.default_rng(seed)
    out: list[tuple[str, SampleSpec]] = []
    for i in range(n):
        kind = ["normal", "normal", "low_snr", "no_target", "speckled"][i % 5]
        spec = SampleSpec(
            snr_db=float(rng.uniform(7, 11)),
            shadow_db=float(rng.uniform(-8, -5)),
            looks=float(rng.choice([3.0, 4.0])),
            target_len=float(rng.uniform(14, 22)),
            target_wid=float(rng.uniform(7, 11)),
            angle_deg=float(rng.uniform(0, 180)),
            shadow_len=float(rng.uniform(8, 14)),
            seed=int(seed + i),
        )
        if kind == "low_snr":
            spec.snr_db = float(rng.uniform(3, 4.5))
            spec.shadow_db = float(rng.uniform(-4, -3))
        elif kind == "no_target":
            spec.has_target = False
        elif kind == "speckled":
            spec.looks = 1.0
        out.append((f"sar_{i:03d}_{kind}", spec))
    return out


def save_dataset(out_dir: str | Path, n: int = 50, seed: int = 1234) -> list[dict]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = []
    for name, spec in default_specs(n, seed):
        img, lab = make_sample(spec)
        np.savez_compressed(out_dir / f"{name}.npz", image=img, labels=lab)
        index.append({"name": name, **asdict(spec)})
    (out_dir / "index.json").write_text(json.dumps(index, indent=1))
    return index


# --------------------------------------------------------------------------- loading
def list_samples(data_dir: str | Path) -> list[str]:
    data_dir = Path(data_dir)
    names = sorted(p.stem for p in (data_dir / "synthetic").glob("*.npz"))
    mstar = data_dir / "mstar"
    if mstar.exists():
        names += sorted(f"mstar/{p.stem}" for p in mstar.glob("*.npz"))
        names += sorted(f"mstar/{p.name}" for p in mstar.glob("*.png"))
    return names


def load_sample(data_dir: str | Path, name: str) -> tuple[np.ndarray, np.ndarray | None]:
    """Load a sample by name. MSTAR chips may be .npz (image[,labels]) or .png."""
    data_dir = Path(data_dir)
    if name.startswith("mstar/"):
        p = data_dir / name
        if p.suffix == ".png":
            from PIL import Image

            img = np.asarray(Image.open(p).convert("F"), dtype=np.float32)
            return center_crop(img, 64), None
        z = np.load(p.with_suffix(".npz"))
        lab = z["labels"] if "labels" in z else None
        img = center_crop(z["image"].astype(np.float32), 64)
        return img, (center_crop(lab, 64) if lab is not None else None)
    z = np.load(data_dir / "synthetic" / f"{name}.npz")
    return z["image"], z["labels"]


def center_crop(a: np.ndarray, size: int) -> np.ndarray:
    h, w = a.shape[:2]
    if h < size or w < size:
        return a
    t, l = (h - size) // 2, (w - size) // 2
    return a[t : t + size, l : l + size]
