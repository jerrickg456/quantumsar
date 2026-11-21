# Architecture and method

## Components

```mermaid
flowchart LR
    subgraph Client
        UI[React + React Bits UI<br/>frontend/ (served at /)]
        ST[Streamlit UI, optional<br/>app/streamlit_app.py]
    end
    subgraph Backend
        API[FastAPI<br/>api/main.py<br/>/segment /edges /benchmark /health]
        PIPE[pipeline.py<br/>model fit, solver registry, provenance]
        MRF[mrf.py<br/>Gamma-speckle unary + Potts prior]
        QUBO[qubo.py<br/>tile QUBO / Ising, brute force]
        TILE[tiling.py<br/>checkerboard block descent,<br/>coarse-to-fine, ICM stitching]
        CL[solvers/classical.py<br/>Otsu, k-means, ICM, SA,<br/>graph cut, alpha-expansion]
        TS[solvers/tile_solvers.py<br/>statevector QAOA, QUBO annealing]
        CQ[solvers/classiq_qaoa.py<br/>Qmod QAOA, batched execution]
        CACHE[(results/quantum_cache<br/>precomputed Classiq runs)]
    end
    CLASSIQ[(Classiq platform<br/>synthesis + classiq/simulator)]

    UI -- HTTP --> API
    ST -- in-process or HTTP --> PIPE
    API --> PIPE
    PIPE --> MRF --> QUBO
    PIPE --> CL
    PIPE --> TILE --> QUBO
    TILE --> TS
    TILE --> CQ --> CLASSIQ
    PIPE <--> CACHE
```

## Pipeline

1. **Model fitting** (`pipeline.fit_model`): number of looks *L* estimated from the log-intensity spread
   (Var[log z] = ψ₁(L) for Gamma speckle), class means from a robust clutter estimate + 1-D k-means,
   then one ICM-EM refinement. The same model is used by every MRF solver, so comparisons isolate the
   optimiser.
2. **Energy**: `E(x) = Σᵢ θᵢ(xᵢ) + λ Σ₍ᵢⱼ₎ [xᵢ ≠ xⱼ]`, θᵢ(k) = L (zᵢ/μₖ + log μₖ).
3. **Tile QUBO** (`qubo.tile_qubo`): free variables = tile pixels; neighbours outside the tile are fixed
   and enter as linear terms (external fields).
   * binary: `[xᵢ≠xⱼ] = xᵢ + xⱼ − 2xᵢxⱼ`
   * K classes, one-hot: `λ(1 − Σₖ yᵢₖ yⱼₖ)` + penalty `P(Σₖ yᵢₖ − 1)²`, with P larger than any gain from
     breaking the constraint (unit-tested: QUBO optimum is always one-hot valid).
   * Ising: `x = (1 − s)/2` → `H = Σ hᵢ Zᵢ + Σ Jᵢⱼ ZᵢZⱼ + c`.
4. **QAOA** (`tile_solvers.StatevectorQAOA`, `classiq_qaoa.build_qaoa_model`):
   `|ψ⟩ = Πₖ e^{-iβₖΣX} e^{-iγₖH} |+⟩ⁿ`; the Hamiltonian is normalised by
   √(Σh² + ΣJ²) (its standard deviation under the uniform distribution), which makes angles transferable
   between tiles. Angles are optimised (COBYLA on ⟨H⟩) on the first few tiles of each size and then
   reused (parameter transfer). The lowest-energy sampled bitstring is returned.
5. **Classiq execution**: the Qmod `main(params, v)` takes `[γ₁..γₚ, β₁..βₚ, h₁..hₙ, J₁..Jₘ]` as one
   execution parameter array. One synthesized program per tile shape (`get_circuit_metrics` gives width/
   depth), and all tiles of one checkerboard colour are sent in a single `ExecutionSession.sample([...])`
   call. Example: 3×3 binary tile → 9 qubits, 12 ZZ couplings, synthesized depth 41 for p = 2.
6. **Tiling** (`tiling.multires_solve`):
   * coarse pass on a 4×-downsampled MRF (block-summed unaries, λ·4 between blocks) solved with the same
     tile solver; upsampled solution used as initialisation if it lowers the energy;
   * fine pass: tiles of one colour share no MRF edge → solved as one batch; a tile's result is accepted
     only if it does not increase the energy (monotone descent, unit-tested);
   * grid offset alternates (0, tile/2) between sweeps; optional skipping of *confident* tiles
     (local conditional-energy margin ≥ 3) keeps the quantum workload to uncertain regions;
   * 3 ICM sweeps stitch seams.
7. **Edges** (`edges.py`): 2-pixel definition from the use case, single-pixel variant (only the
   higher-priority side: target > shadow > background), and class-labelled edges (object vs shadow).

## Provenance of results

Every result carries a `mode` string shown in the UI:

| mode | meaning |
|---|---|
| `Classiq QAOA - live` | circuits synthesized and sampled on Classiq during the request |
| `Classiq QAOA - cached result` | produced earlier on Classiq by `scripts/precompute_quantum.py`, served from `results/quantum_cache/` |
| `FALLBACK: same QAOA circuit on local statevector simulator` | Classiq unavailable / no cache for these settings |
| `quantum-inspired simulated annealing` | classical annealing on the same tile QUBOs |
| `classical ...` | classical baselines |

## Why tiles are small

A tile of t×t pixels needs t² qubits (binary) or 3t² (3-class one-hot). The local statevector simulator
is capped at 20 qubits (2²⁰ amplitudes) and the Classiq simulator at 28 qubits, so the defaults are 3×3
(9 qubits) for binary and 2×2 (12 qubits) for 3-class.
