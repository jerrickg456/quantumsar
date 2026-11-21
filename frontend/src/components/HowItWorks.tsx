import { Card, SectionTitle } from './ui'

const STEPS = [
  { n: '01', title: 'Model the image', testid: 'how-model',
    body: 'A Markov random field: a Gamma-speckle likelihood for each pixel plus a Potts/Ising smoothness term λ between 4-neighbours. The number of looks and class means are estimated from the image itself.' },
  { n: '02', title: 'Pixels become qubits', testid: 'how-encoding',
    body: 'Binary: 1 qubit per pixel, [xᵢ≠xⱼ] = xᵢ + xⱼ − 2xᵢxⱼ. Three classes: one-hot, 3 qubits per pixel plus a penalty P(Σ y − 1)². The QUBO maps to an Ising Hamiltonian H = Σ hZ + Σ JZZ.' },
  { n: '03', title: 'QAOA on Classiq', testid: 'how-qaoa',
    body: 'Cost layer RZ(2γh) and CX·RZ(2γJ)·CX, mixer RX(2β). Coefficients are execution parameters: one synthesized program per tile shape, one batched job per checkerboard colour.' },
  { n: '04', title: 'Tile, stitch, verify', testid: 'how-tiling',
    body: '4096 pixels ≫ qubits, so the image is solved as 3×3 tiles whose borders act as external fields: a coarse 4× pass, shifted sweeps, energy-monotone acceptance and ICM stitching.' },
]

const LIMITS = [
  ['Not a speed-up (yet)', 'For two classes graph cut is exact and takes milliseconds. QAOA reaches the same energy, but on simulators it is far slower.'],
  ['Small tiles', 'Simulators cap tiles at 9–12 qubits, so the quantum part optimises local blocks; the global optimum is not guaranteed.'],
  ['Cached Classiq runs', 'A live Classiq run takes ~2–4 minutes per image, so this demo serves precomputed Classiq results and labels every fallback.'],
  ['Synthetic data', 'MSTAR-like synthetic chips with Gamma speckle; real MSTAR chips can be dropped into data/mstar/.'],
]

export default function HowItWorks() {
  return (
    <section id="how" className="mx-auto max-w-7xl scroll-mt-6 px-6 py-16">
      <SectionTitle kicker="How it works" title="From speckle to spins"
        sub="The Thales use case: MAP inference in a Markov random field, rewritten exactly as a QUBO and solved with QAOA." />
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((s) => (
          <Card key={s.n} testid={s.testid} glow="rgba(124,58,237,0.25)">
            <div className="font-mono text-sm text-amber-400">{s.n}</div>
            <div className="mt-2 text-lg font-bold text-white">{s.title}</div>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">{s.body}</p>
          </Card>
        ))}
      </div>
      <Card testid="how-limits" className="mt-8" glow="rgba(255,106,61,0.22)">
        <div className="text-xs font-semibold uppercase tracking-widest text-orange-300">Honest limitations</div>
        <div className="mt-3 grid gap-4 md:grid-cols-2">
          {LIMITS.map(([t, b]) => (
            <div key={t}>
              <div className="font-semibold text-white">{t}</div>
              <p className="text-sm text-slate-400">{b}</p>
            </div>
          ))}
        </div>
      </Card>
    </section>
  )
}
