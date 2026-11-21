# QuantumSAR — Project Guide

**Finding vehicles in noisy radar images with quantum optimisation**

Team **From Nowhere** · Thales SAR Image Segmentation challenge · built with Classiq

| | |
|---|---|
| **Live app** | **https://quantumsar.onrender.com** |
| **Source code** | **https://github.com/jerrickg456/quantumsar** |
| **API (interactive docs)** | https://quantumsar.onrender.com/docs |
| **Demo video** | [`video/out/final.mp4`](../video/out/final.mp4) (about 5 minutes, with subtitles) |
| **Team** | Jerrick Austin Manuel G · Nidhin Suresh · Suresh Ramanujam · Yokeshwaran Anandan · Hari Babu |

> The live app runs on a free server that sleeps when nobody uses it. The first visit after a quiet
> period can take about a minute to load; after that it is fast.

---

## 1. The problem, in simple words

Some satellites carry a special radar called **SAR (Synthetic Aperture Radar)**. Unlike a normal camera,
SAR can take pictures **at night and through clouds or smoke**, which makes it very useful for
monitoring, rescue and defence.

The catch: SAR pictures are **very noisy**. They are covered in a grainy pattern called **speckle**.

**Our task (from Thales):** in each 64 × 64 radar image, find the vehicle. Every pixel must be labelled
as one of:

* **vehicle** (target),
* **shadow** (the dark area behind the vehicle that the radar cannot see), or
* **background**.

This is called **image segmentation**. Thales also asked for two extras: **edge detection** (drawing the
outline of the vehicle) and a **3-class** version (vehicle, shadow, background).

**Why it is hard:** a pixel cannot be judged alone. A bright pixel might be part of the vehicle, or just
noise. You have to look at each pixel *together with its neighbours*. With 4,096 pixels, the number of
possible labellings is 2⁴⁰⁹⁶ — far more than there are atoms in the universe. Classical computers have to
use shortcuts to search such a huge space.

---

## 2. Our idea, in simple words

1. **Each pixel becomes a tiny magnet (a "spin")** that points up or down. Up = vehicle, down = background.
2. **Bright pixels prefer to point up.** Dark, noisy pixels prefer to point down.
3. **Neighbouring magnets like to point the same way.** This keeps the picture smooth and removes speckle.
4. Each arrangement of all magnets has an **energy**. The arrangement with the **lowest energy** is the
   cleanest, most likely picture.
5. Finding the lowest energy of a system of spins is exactly what the quantum algorithm **QAOA**
   (Quantum Approximate Optimisation Algorithm) is designed for. We run it on **Classiq**'s quantum
   platform.
6. One image has 4,096 pixels, far more qubits than today's quantum simulators allow. So we **cut the
   image into small 3 × 3 tiles (9 qubits each)**, solve each tile with QAOA, and stitch the tiles back
   together carefully.

In technical terms: the image is a *Markov random field*; its energy is rewritten exactly as a
*QUBO / Ising Hamiltonian*; QAOA searches for its ground state.

---

## 3. How to use the live app (step by step)

Open **https://quantumsar.onrender.com** and scroll to **Live demo**.

1. **Pick an image.** Click one of the sample thumbnails (normal, low-contrast, no-vehicle, very
   speckled), or click **Upload image** to use your own grayscale picture (PNG, JPG or `.npy`; large
   images are shrunk automatically).
2. **Pick a solver.** The default is **Quantum · QAOA on Classiq**. You can also choose the classical
   methods to compare.
3. **Optional switches:**
   * **3 classes** — also find the shadow (shown in blue).
   * **Edge detection** — draw the outline (red = vehicle, cyan = shadow).
   * Sliders for smoothness (λ), tile size, QAOA depth, shots and sweeps.
4. Press **▶ Run segmentation**.
5. Read the result:
   * **Segmentation** — orange = vehicle, blue = shadow.
   * **Ground truth** — the correct answer (sample images only).
   * **Badge** — tells you exactly which engine produced the result:

| Badge | Meaning |
|---|---|
| 🟢 **LIVE ON CLASSIQ** | computed just now on Classiq's quantum cloud (about 1–3 minutes, with a progress bar) |
| 🔵 **CLASSIQ · CACHED RUN** | computed on Classiq earlier and saved, so it loads instantly |
| 🟠 **LOCAL FALLBACK** | the same QAOA circuit run on a local simulator (only if Classiq is not available) |
| ⚪ **CLASSICAL** | a classical method (graph cut, annealing, Otsu, …) |

6. **Metrics** show the accuracy, IoU and Dice scores, the energy reached, the runtime, and how many
   tiles QAOA solved. **Quantum circuit per tile** shows the qubits, couplings and the circuit size
   reported by Classiq.
7. In **Benchmark**, press **⚡ Benchmark all solvers** to compare every method on the same image, and
   **⬇ Export CSV** to download the numbers.

---

## 4. Results

<!-- RESULTS-TABLE -->

What the numbers mean:

* **Accuracy** — percentage of pixels labelled correctly.
* **IoU / Dice** — how well the found vehicle shape overlaps the true shape (1.0 = perfect).
* **Energy** — how good the solution is for the optimisation problem (lower = better).
  Graph cut finds the **exact** lowest energy for the 2-class problem, so it is the reference.
* **Runtime** — time per image. For Classiq this is the real time of the cloud run.

**Honest summary:** QAOA on Classiq reaches the same quality as the best classical method (graph cut) and
is far more accurate than simple thresholding (Otsu, k-means). But classical methods are still much
faster today. Our contribution is a correct, tested, end-to-end quantum pipeline that is ready to scale as
quantum hardware grows.

---

## 5. What we built and how

### Quantum part (Classiq)

* The QAOA circuit is written in Python with the **Classiq SDK** (`src/quantumsar/solvers/classiq_qaoa.py`).
  Cost layer: `RZ(2γh)` and `CX·RZ(2γJ)·CX`; mixer: `RX(2β)`.
* Classiq **synthesizes** the circuit (9 qubits, depth 41 for a 3 × 3 tile with p = 2) and runs it on its
  **cloud simulator**.
* All the tile's numbers are passed as *execution parameters*, so **one circuit serves every tile**, and a
  whole batch of tiles runs in **one Classiq job**.
* Synthesized circuits are saved (`results/classiq_programs/`), so the server never has to rebuild them.
* **Verified:** on 3 × 3 and 4 × 4 tiles, the QAOA answer equals a full brute-force search (automatic
  tests). QAOA makes the best answer much more likely than random guessing (about 160× more likely on
  9 qubits, 7,000× on 16 qubits).

### Classical part (for comparison)

Graph cut (exact for 2 classes), α-expansion (3 classes), simulated annealing, ICM, Otsu thresholding and
k-means — all in Python (`src/quantumsar/solvers/classical.py`).

### Tiling (how 4,096 pixels fit into 9 qubits)

A quick pass on a 4× smaller copy of the image finds the big shapes, then the full-size image is solved
tile by tile. Tile borders act as fixed neighbours; tiles that do not touch are solved together; a tile's
new answer is only kept if it lowers the energy; shifted grids and a final clean-up stitch the seams.

### Software

| Layer | Technology |
|---|---|
| Quantum | Classiq Python SDK 1.36 (QAOA, synthesis, cloud simulator) |
| Science code | Python 3.11, NumPy, SciPy, PyMaxflow |
| Backend API | FastAPI (background jobs for live Classiq runs) |
| Website | React + TypeScript + Tailwind, animated components from React Bits |
| Packaging | One Docker container (website + API) |
| Quality | 46 automated tests, GitHub Actions CI |
| Hosting | Render (free web service) |

---

## 6. How it is deployed

```
GitHub (public code) ──► GitHub Actions (tests + Docker build) ──► Render (Docker container)
                                                                     │  React website + FastAPI
                                                                     ▼
                                                     Classiq cloud (QAOA synthesis + simulator)
```

* Every change pushed to GitHub is tested automatically and then **re-deployed on Render**.
* **Classiq login on a server:** Classiq normally logs in through a browser. A server cannot do that, so we
  created a **separate, dedicated Classiq login for the server**, stored as a hidden **Render secret**
  (never in the code). The live site uses it to run quantum jobs on its own.
* **Long jobs:** a live Classiq run takes about a minute or more, so it runs as a **background job** with a
  progress bar. Jobs run **one at a time** (at most 4 waiting) to protect the Classiq account, and every
  finished result is **saved** so it loads instantly next time.
* Results computed earlier on Classiq for all 50 sample images (2-class) and 10 images (3-class) are
  shipped with the app.

---

## 7. Honest limitations

* **Not faster than classical (yet).** For 2 classes, graph cut gives the exact answer in milliseconds.
  QAOA reaches the same answer but takes much longer on today's simulators.
* **Small tiles.** Qubit limits force 9-qubit tiles (12 for 3 classes), so the quantum part optimises
  small blocks, not the whole image at once.
* **3 classes is harder** for the quantum method; α-expansion is better there.
* **Synthetic data.** The real MSTAR images are not freely redistributable, so we generated realistic
  MSTAR-like images with radar speckle. Real images can be added to `data/mstar/`.
* **Free hosting.** The server sleeps when idle and live results are kept only until it restarts.

---

## 8. Run it on your own computer

```bash
git clone https://github.com/jerrickg456/quantumsar.git && cd quantumsar
docker compose up --build            # then open http://localhost:7860
```

Without Docker (Python 3.11 + Node 20+):

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cd frontend && npm ci && npm run build && cd ..
uvicorn api.main:app --port 8000                      # open http://localhost:8000
python -m pytest -q                                   # run the tests
```

To run Classiq live locally, log in once: `python -c "from quantumsar.auth import setup_classiq_auth;
setup_classiq_auth(); import classiq; classiq.authenticate()"` and start the server with
`QUANTUMSAR_ALLOW_LIVE_CLASSIQ=1`.

---

## 9. Where things are in the code

| Folder / file | What it contains |
|---|---|
| `src/quantumsar/mrf.py` | the energy model (speckle likelihood + smoothness) |
| `src/quantumsar/qubo.py` | turns a tile into a QUBO / Ising problem |
| `src/quantumsar/tiling.py` | splits the image into tiles and stitches results |
| `src/quantumsar/solvers/classiq_qaoa.py` | the QAOA circuit on Classiq |
| `src/quantumsar/solvers/tile_solvers.py` | local QAOA simulator and quantum-inspired annealing |
| `src/quantumsar/solvers/classical.py` | classical comparison methods |
| `api/main.py` | the web API (segment, edges, benchmark, live jobs) |
| `frontend/` | the website (React + React Bits) |
| `tests/` | automated tests |
| `notebooks/QuantumSAR_walkthrough.ipynb` | step-by-step explanation with code |
| `results/` | benchmark tables, figures and saved Classiq results |
| `video/` | the demo video and the scripts that make it |
| `docs/` | technical documents (architecture, Classiq login, deployment) |

---

## 10. Glossary

| Word | Meaning |
|---|---|
| **SAR** | Synthetic Aperture Radar — a radar that makes images, day or night, through clouds |
| **Speckle** | the grainy noise in radar images |
| **Segmentation** | giving every pixel a label (vehicle / shadow / background) |
| **Qubit** | the basic unit of a quantum computer (like a bit, but can be 0 and 1 at once) |
| **Spin / Ising model** | a set of up/down magnets with an energy; our image becomes one |
| **QUBO** | the same kind of problem written with 0/1 variables |
| **QAOA** | a quantum algorithm that searches for low-energy (good) answers |
| **Classiq** | the quantum software platform we use to build and run the circuits |
| **Graph cut** | a fast classical method that finds the exact best answer for 2 classes |
| **IoU** | Intersection over Union — how much the found shape overlaps the true shape |

---

**Team From Nowhere** — Jerrick Austin Manuel G, Nidhin Suresh, Suresh Ramanujam, Yokeshwaran Anandan,
Hari Babu. Code: https://github.com/jerrickg456/quantumsar · Live app: https://quantumsar.onrender.com
