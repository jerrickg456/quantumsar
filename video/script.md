# QuantumSAR — demo video narration

Voice: `en-US-AndrewNeural` (edge-tts), rate +0%. 391 words, 144 s of speech.

## 0:00 Hook  (18.2 s)

Radar satellites can see through clouds and darkness, but their images come with a catch: speckle. Every synthetic aperture radar picture is covered in grainy noise, so even finding a vehicle on the ground is hard. And the classical methods that clean this up get slow, or stuck, as images grow.

## 0:20 The idea  (25.9 s)

QuantumSAR turns segmentation into an energy puzzle. Each pixel gets a label, target or background, which we write as a tiny magnet, a spin, pointing up or down. Neighbouring spins like to agree, and bright pixels prefer to be target. That is an Ising problem, exactly the kind of optimisation quantum computers are built for. We solve it with QAOA, the Quantum Approximate Optimisation Algorithm, running on Classiq.

## 0:45 Live demo  (38.7 s)

Let's try it. I pick a noisy radar sample and choose the quantum solver. A sixty-four by sixty-four image has four thousand pixels, far more than any simulator has qubits, so the app cuts it into tiny three-by-three tiles. Each tile becomes a nine-qubit circuit, and Classiq runs a whole batch of tiles at once. The badge always says where a result came from: this one was computed on Classiq's cloud simulator, then cached. Orange is the target, and it matches the ground truth closely. Now switch on three classes. Every pixel now uses three qubits, and the dark radar shadow behind the vehicle appears in blue.

## 1:30 Edge detection  (11.0 s)

Turn on edge detection, and the app outlines every region, one pixel wide. Red traces the vehicle, cyan traces its shadow, ready for a target-recognition step.

## 1:50 Benchmark  (21.4 s)

So how does it compare? One click benchmarks every solver on the same image. Quantum QAOA lands within a fraction of a percent of the exact optimum found by graph cut, and far ahead of Otsu and k-means thresholding, which speckle fools. To be fair, annealing and graph cut are still faster on a laptop. And everything exports to CSV.

## 2:20 Honest limits  (20.3 s)

Now, the honest limits. Qubit counts keep tiles small, so the quantum part optimises local blocks, not the whole image at once. Live cloud runs take a few minutes per image, which is why this demo serves cached Classiq results. Bigger devices mean bigger tiles, and next we want real MSTAR data and hardware runs.

## 2:40 Call to action  (8.3 s)

QuantumSAR is open source, tested, and runs with one Docker command. Grab the code and try the live demo from the links on screen.
