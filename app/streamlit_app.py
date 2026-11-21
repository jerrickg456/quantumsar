"""QuantumSAR - Streamlit front-end.

    streamlit run app/streamlit_app.py

Runs the pipeline in-process by default. Set QUANTUMSAR_API_URL to use the
FastAPI backend instead (docker-compose does this).
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantumsar.data import list_samples, load_sample, to_uint8  # noqa: E402
from quantumsar.pipeline import (  # noqa: E402
    SOLVERS, SegParams, benchmark, effective_tile, load_cached_quantum, segment, tile_qubits)

DATA_DIR = ROOT / "data"
API_URL = os.environ.get("QUANTUMSAR_API_URL", "").rstrip("/")
ALLOW_LIVE = os.environ.get("QUANTUMSAR_ALLOW_LIVE_CLASSIQ", "0") == "1"

UI_SOLVERS = {
    "Quantum (QAOA on Classiq)": "classiq",
    "Quantum (QAOA, local simulator)": "qaoa_local",
    "Simulated annealing": "annealing",
    "Quantum-inspired annealing (tiled QUBO)": "sa_tiled",
    "Graph cut": "graphcut",
    "ICM": "icm",
    "Otsu": "otsu",
    "k-means": "kmeans",
}
SHORT = {"classiq": "QAOA·Classiq", "qaoa_local": "QAOA·local", "annealing": "Annealing",
         "sa_tiled": "Tiled SA", "graphcut": "Graph cut", "icm": "ICM", "otsu": "Otsu", "kmeans": "k-means",
         "bruteforce_tiled": "Exact tiles"}
CLASS_COLORS = np.array([[40, 48, 66], [255, 166, 0], [64, 132, 255]], dtype=np.uint8)
EDGE_COLORS = np.array([[0, 0, 0], [255, 60, 60], [80, 230, 255]], dtype=np.uint8)

st.set_page_config(page_title="QuantumSAR", page_icon="🛰️", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 1.4rem; max-width: 1500px;}
.mode-badge {display:inline-block; padding:4px 12px; border-radius:14px; font-weight:600; font-size:0.9rem;}
.mode-live {background:#1b5e20; color:#fff;} .mode-cached {background:#0d47a1; color:#fff;}
.mode-fallback {background:#e65100; color:#fff;} .mode-classical {background:#424242; color:#fff;}
.caption-strong {font-weight:600; text-align:center; margin-bottom:4px;}
</style>""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------- helpers
def big(a: np.ndarray, px: int = 300) -> Image.Image:
    return Image.fromarray(a).resize((px, px), Image.NEAREST)


def colorize(labels: np.ndarray) -> np.ndarray:
    return CLASS_COLORS[np.asarray(labels).astype(int)]


def edge_overlay(img: np.ndarray, ecls: np.ndarray) -> np.ndarray:
    g = to_uint8(img)
    rgb = np.stack([g, g, g], -1) // 2
    m = ecls > 0
    rgb[m] = EDGE_COLORS[ecls[m].astype(int)]
    return rgb


def mode_badge(mode: str) -> str:
    cls = ("mode-live" if "live" in mode else "mode-cached" if "cached" in mode
           else "mode-fallback" if "FALLBACK" in mode else "mode-classical")
    return f'<span class="mode-badge {cls}">{mode}</span>'


def logical_circuit(prm: SegParams, tile: int) -> dict:
    """Analytic size of the tile QAOA circuit (before synthesis)."""
    n = tile_qubits(prm, tile)
    if prm.n_classes == 2:
        m = 2 * tile * (tile - 1)
    else:
        K = prm.n_classes
        m = K * 2 * tile * (tile - 1) + tile * tile * K * (K - 1) // 2
    return {"qubits": n, "couplings (ZZ terms)": m, "QAOA layers p": prm.p,
            "gates per layer": f"{n} RZ + {m}x(CX-RZ-CX) + {n} RX",
            "parameters": 2 * prm.p + n + m}


@st.cache_data(show_spinner=False)
def get_sample(name: str):
    return load_sample(DATA_DIR, name)


def run_segment(img, gt, prm: SegParams, edges: bool, single: bool):
    if API_URL:
        import requests

        buf = io.BytesIO()
        np.save(buf, img.astype(np.float32))
        payload = {"image_b64": base64.b64encode(buf.getvalue()).decode(), "edges": edges, "single_edges": single,
                   "params": {k: v for k, v in asdict(prm).items() if k != "allow_live_classiq"}}
        r = requests.post(f"{API_URL}/segment", json=payload, timeout=900)
        r.raise_for_status()
        res = r.json()
        for k in ("labels", "edges", "edge_classes"):
            if k in res:
                res[k] = np.array(res[k], dtype=np.uint8)
        if gt is not None:
            from quantumsar.metrics import segmentation_metrics
            res["metrics"] = segmentation_metrics(res["labels"], gt, prm.n_classes)
        return res
    return segment(img, prm, gt, edges=edges, single_edges=single)


# ----------------------------------------------------------------------------- sidebar
st.sidebar.title("🛰️ QuantumSAR")
st.sidebar.caption("SAR segmentation as an Ising/QUBO problem, solved with QAOA")

src = st.sidebar.radio("Input", ["Sample", "Upload"], horizontal=True)
samples = list_samples(DATA_DIR)
gt = None
if src == "Sample":
    default = samples.index("sar_002_low_snr") if "sar_002_low_snr" in samples else 0
    name = st.sidebar.selectbox("Sample image", samples, index=default)
    img, gt = get_sample(name)
else:
    up = st.sidebar.file_uploader("Grayscale image (PNG/JPG/.npy, <=128 px)", type=["png", "jpg", "jpeg", "npy"])
    if up is None:
        st.info("Upload an image or switch to *Sample*.")
        st.stop()
    if up.name.endswith(".npy"):
        img = np.load(up).astype(np.float32)
    else:
        img = np.asarray(Image.open(up).convert("F"), dtype=np.float32)
    img = np.maximum(img[:128, :128], 1e-3)
    name = up.name

solver_label = st.sidebar.selectbox("Solver", list(UI_SOLVERS), index=0)
solver = UI_SOLVERS[solver_label]
three = st.sidebar.toggle("3 classes (target / shadow / background)", value=False)
show_edges = st.sidebar.toggle("Edge detection", value=False)
single = st.sidebar.toggle("Single-pixel edges", value=True, disabled=not show_edges)

with st.sidebar.expander("Hyperparameters", expanded=True):
    lam = st.slider("λ smoothness", 0.0, 5.0, 1.5, 0.1)
    tile = st.slider("Tile size (pixels per side)", 2, 4, 3)
    p = st.slider("QAOA depth p", 1, 4, 2)
    shots = st.select_slider("Shots", [128, 256, 512, 1024, 2048, 4096], value=1024)
    sweeps = st.slider("Tiling sweeps", 1, 4, 2)

prm = SegParams(solver=solver, n_classes=3 if three else 2, lam=lam, tile=tile, p=p, shots=shots,
                sweeps=sweeps, allow_live_classiq=ALLOW_LIVE)
eff_tile = effective_tile(prm, 20)
cache_hit = load_cached_quantum(img, SegParams(**{**asdict(prm), "solver": "classiq"})) is not None
if solver == "classiq":
    if cache_hit:
        st.sidebar.success("Precomputed Classiq result available for these settings.")
    elif ALLOW_LIVE:
        st.sidebar.warning("Will run live on Classiq (several minutes).")
    else:
        st.sidebar.info("No cached Classiq result for these settings: the same QAOA circuit "
                        "runs on the local simulator (clearly labelled).")
run = st.sidebar.button("▶ Run segmentation", type="primary", use_container_width=True)

# ----------------------------------------------------------------------------- header
st.title("QuantumSAR · quantum-optimised SAR segmentation")
st.caption("Each pixel's label is a spin. The Markov-random-field energy "
           "E(x) = Σ θᵢ(xᵢ) + λ Σ [xᵢ ≠ xⱼ] becomes an Ising Hamiltonian, solved tile-by-tile with QAOA.")

key = (name, json.dumps(asdict(prm), sort_keys=True), show_edges, single)
if run:
    with st.spinner(f"Running {solver_label}…"):
        st.session_state["result"] = (key, run_segment(img, gt, prm, show_edges, single), solver_label)
res_entry = st.session_state.get("result")
res = res_entry[1] if res_entry and res_entry[0][0] == name else None

# ----------------------------------------------------------------------------- images
ncols = 4 if (res is not None and show_edges and "edges" in res) else 3
cols = st.columns(ncols)
with cols[0]:
    st.markdown('<div class="caption-strong">SAR input (log scale)</div>', unsafe_allow_html=True)
    st.image(big(to_uint8(img)), use_container_width=True)
with cols[1]:
    st.markdown('<div class="caption-strong">Ground truth</div>', unsafe_allow_html=True)
    if gt is not None:
        g = gt if prm.n_classes == 3 else (gt == 1).astype(np.uint8)
        st.image(big(colorize(g)), use_container_width=True)
    else:
        st.caption("not available")
with cols[2]:
    st.markdown('<div class="caption-strong">Segmentation</div>', unsafe_allow_html=True)
    if res is not None:
        st.image(big(colorize(res["labels"])), use_container_width=True)
    else:
        st.caption("press **Run segmentation**")
if ncols == 4:
    with cols[3]:
        st.markdown('<div class="caption-strong">Edges (red = target, cyan = shadow)</div>', unsafe_allow_html=True)
        st.image(big(edge_overlay(img, res["edge_classes"])), use_container_width=True)
st.markdown("<small>■ <span style='color:#ffa600'>target</span> &nbsp; ■ <span style='color:#4084ff'>shadow</span>"
            " &nbsp; ■ background</small>", unsafe_allow_html=True)

# ----------------------------------------------------------------------------- result details
if res is not None:
    st.markdown(f"**Result produced by:** {mode_badge(res['mode'])}", unsafe_allow_html=True)
    c1, c2 = st.columns([3, 2])
    with c1:
        st.subheader("Metrics")
        m = {"solver": res_entry[2], "runtime (s)": f"{res['runtime_s']:.3f}", "MRF energy": f"{res['energy']:.1f}"}
        m.update({k.replace("_", " "): f"{v:.3f}" for k, v in res.get("metrics", {}).items()})
        mt = pd.DataFrame(m.items(), columns=["metric", "value"]).set_index("metric")
        mc1, mc2 = st.columns(2)
        half = (len(mt) + 1) // 2
        mc1.table(mt.iloc[:half])
        mc2.table(mt.iloc[half:])
        info = res.get("info", {})
        if "tiles_solved" in info:
            extra = {"tiles solved by tile solver": info["tiles_solved"], "tiles in grid": info["tiles_total"],
                     "batched jobs": info["batches"], "qubits / tile": info.get("max_qubits")}
            if "qaoa_mean_p_opt" in info:
                extra["P(optimum) after QAOA"] = f"{info['qaoa_mean_p_opt']:.1%}"
                extra["P(optimum) random guess"] = f"{info['qaoa_mean_p_opt_uniform']:.2%}"
                extra["tiles where QAOA found the optimum"] = f"{info['qaoa_found_opt_rate']:.1%}"
            st.table(pd.DataFrame([{k: str(v) for k, v in extra.items()}]).set_index("tiles solved by tile solver"))
    with c2:
        st.subheader("Quantum circuit (per tile)")
        lc = logical_circuit(prm, eff_tile)
        circ = res.get("info", {}).get("circuit") or {}
        if circ.get("depth"):
            lc.update({"synthesized width (Classiq)": circ.get("width"),
                       "synthesized depth (Classiq)": circ.get("depth")})
        st.table(pd.DataFrame(lc.items(), columns=["property", "value"]).astype(str).set_index("property"))
        if eff_tile != tile:
            st.caption(f"Tile reduced to {eff_tile}×{eff_tile} to stay within the simulator qubit limit.")

# ----------------------------------------------------------------------------- benchmark
st.divider()
st.subheader("Benchmark all solvers on this image")
if st.button("⚡ Benchmark all solvers", key="bench_btn"):
    with st.spinner("Running every solver…"):
        rows = benchmark(img, gt, prm, list(UI_SOLVERS.values()))
        st.session_state["bench"] = (name, pd.DataFrame(rows))
bench = st.session_state.get("bench")
if bench and bench[0] == name:
    df = bench[1]
    show = [c for c in ["name", "mode", "accuracy", "iou", "dice", "runtime_s", "energy", "tiles_solved"] if c in df]
    fmt = df[show].copy()
    for c in ("accuracy", "iou", "dice"):
        if c in fmt:
            fmt[c] = fmt[c].map(lambda v: f"{v:.3f}")
    fmt["runtime_s"] = fmt["runtime_s"].map(lambda v: f"{v:.3f}")
    fmt["energy"] = fmt["energy"].map(lambda v: f"{v:.1f}")
    if "tiles_solved" in fmt:
        fmt["tiles_solved"] = fmt["tiles_solved"].map(lambda v: "" if pd.isna(v) else str(int(v)))
    df = df.assign(short=df["solver"].map(SHORT))
    st.table(fmt.set_index("name"))
    b1, b2, b3 = st.columns(3)
    if "iou" in df:
        b1.altair_chart(alt.Chart(df).mark_bar(color="#ffa600").encode(
            x=alt.X("iou:Q", title="IoU (higher is better)", scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("short:N", sort="-x", title=None, axis=alt.Axis(labelOverlap=False))).properties(height=260, title="Accuracy (IoU)"),
            use_container_width=True)
    b2.altair_chart(alt.Chart(df).mark_bar(color="#4084ff").encode(
        x=alt.X("runtime_s:Q", title="runtime (s)"),
        y=alt.Y("short:N", sort="x", title=None, axis=alt.Axis(labelOverlap=False))).properties(height=260, title="Runtime"),
        use_container_width=True)
    b3.altair_chart(alt.Chart(df).mark_bar(color="#7e57c2").encode(
        x=alt.X("energy:Q", title="MRF energy (lower is better)", scale=alt.Scale(zero=False)),
        y=alt.Y("short:N", sort="x", title=None, axis=alt.Axis(labelOverlap=False))).properties(height=260, title="Energy reached"),
        use_container_width=True)
    st.download_button("⬇ Export CSV", df.to_csv(index=False), file_name=f"benchmark_{name.replace('/', '_')}.csv",
                       mime="text/csv")

ds = ROOT / "results" / "benchmark_summary.csv"
if ds.exists():
    with st.expander("Dataset-wide results (50 synthetic SAR images)"):
        st.dataframe(pd.read_csv(ds), hide_index=True, use_container_width=True)
        fig = ROOT / "results" / "figures" / "benchmark_bars.png"
        if fig.exists():
            st.image(str(fig))

with st.expander("How it works & honest limitations"):
    st.markdown("""
* **Model.** Markov random field: Gamma-speckle likelihood unary term + Potts/Ising smoothness (λ) over 4-neighbours.
* **Quantum encoding.** Binary: 1 qubit/pixel. 3-class: one-hot, 3 qubits/pixel + penalty.
* **Tiling.** 4096 pixels ≫ qubits, so the image is split into small tiles whose border pixels act as external
  fields; tiles of one checkerboard colour are solved in one batched job, a coarse (4×-downsampled) pass fixes
  large-scale structure, grid offsets alternate between sweeps, and ICM sweeps stitch the seams. Each accepted
  tile never increases the energy.
* **Limits.** Tiles are tiny (9–12 qubits), so the quantum part optimises local blocks; the global optimum is not
  guaranteed and graph cut (exact for 2 classes) is faster on classical hardware. QAOA angles are pre-trained on a
  local simulator and transferred between tiles. Live Classiq runs take minutes per image, so the public demo serves
  **precomputed Classiq results** and otherwise falls back to the local simulator — every result is labelled.
""")
