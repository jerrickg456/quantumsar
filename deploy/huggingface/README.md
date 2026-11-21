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
With the `CLASSIQ_DEPLOY_CREDENTIALS` secret and `QUANTUMSAR_ALLOW_LIVE_CLASSIQ=1` set, the
"QAOA on Classiq" solver runs **live on Classiq's cloud simulator** (a background job, about 2–4 minutes
per image, with a progress bar). Results already computed on Classiq are served instantly. Every result
is labelled with the engine that produced it.
