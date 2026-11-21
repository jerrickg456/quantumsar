# Thales SAR use case: requirement checklist

| Use-case requirement | Where it is met |
|---|---|
| Markov random field on the pixel graph, MAP = energy minimisation with unary + pairwise terms | `src/quantumsar/mrf.py` (`energy`, `build_model`), docs/architecture.md |
| Ising prior (graph-cut exact in polynomial time) | `solvers/classical.py::graph_cut` (PyMaxflow), used as the exact reference |
| Use quantum parallelism to treat all neighbour interactions | tile QUBO/Ising (`qubo.py`) solved by QAOA on Classiq (`solvers/classiq_qaoa.py`) |
| 64×64 SAR images, class 0 background / class 1 object | `data.py`, 50 samples in `data/synthetic/` |
| Validation includes images **without an object** and **low SNR** | sample types `no_target` and `low_snr` (and `speckled`, L = 1); per-type results in `results/RESULTS.md` |
| 3+ classes: shadow as class 2 | one-hot QUBO (`qubo.py`), 3-class toggle in UI/API, α-expansion baseline |
| Edge detection: pixel with ≥ 1 neighbour of another class | `edges.py::edges_double` (exact definition, test reproduces the PDF example) |
| Multi-class edges (object vs shadow edges) | `edges.py::edge_classes` (red = target, cyan = shadow in the UI) |
| Single pixel per edge | `edges.py::edges_single` (unit test uses the PDF example) |
| Metric: number of well-labelled pixels | `metrics.py` (accuracy) + IoU, Dice, edge precision/recall/F1, energy, runtime |
| Classical baseline comparison (paper: GA / branch-and-bound class of solvers) | Otsu, k-means, ICM, simulated annealing, graph cut, α-expansion, exact brute force on tiles |
| MSTAR data | loader for `data/mstar/*.png|*.npz`; synthetic MSTAR-like set shipped because MSTAR is not redistributable |
