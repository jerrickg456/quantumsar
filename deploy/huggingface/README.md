---
title: QuantumSAR
emoji: 🛰️
colorFrom: indigo
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
short_description: SAR segmentation with QAOA (Classiq) vs classical solvers
---

QuantumSAR — Markov-random-field segmentation of SAR images, solved tile-by-tile
with QAOA on Classiq, benchmarked against graph cut, annealing, ICM, Otsu and k-means.
Quantum results shown in this Space are **precomputed on Classiq** (cached in the repo);
any other setting runs the same QAOA circuit on a local statevector simulator and is labelled as such.
