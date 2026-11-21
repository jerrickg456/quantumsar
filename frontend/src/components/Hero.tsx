import Aurora from './reactbits/Aurora/Aurora'
import SplitText from './reactbits/SplitText/SplitText'
import BlurText from './reactbits/BlurText/BlurText'
import ShinyText from './reactbits/ShinyText/ShinyText'
import GradientText from './reactbits/GradientText/GradientText'
import CountUp from './reactbits/CountUp/CountUp'

const STATS = [
  { to: 4096, label: 'pixels → spins per image', suffix: '' },
  { to: 9, label: 'qubits per QAOA tile', suffix: '' },
  { to: 0.1, label: 'energy gap to exact optimum', suffix: '%', decimals: 1, prefix: '≈' },
  { to: 50, label: 'benchmark SAR images', suffix: '' },
]

export default function Hero({ onStart }: { onStart: () => void }) {
  return (
    <header className="relative isolate overflow-hidden">
      <div className="absolute inset-0 -z-10 h-[680px] opacity-90">
        <Aurora colorStops={['#ff8a00', '#7c3aed', '#2563eb']} amplitude={1.1} blend={0.55} speed={0.6} glow={0.7} />
      </div>
      <div className="absolute inset-x-0 top-[520px] -z-10 h-40 bg-gradient-to-b from-transparent to-[#070b14]" />

      <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2 text-lg font-bold text-white">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-amber-400/20 text-amber-300">◈</span>
          QuantumSAR
        </div>
        <div className="hidden gap-6 text-sm text-slate-300 md:flex">
          <a href="#demo" className="hover:text-white">Demo</a>
          <a href="#benchmark" className="hover:text-white">Benchmark</a>
          <a href="#how" className="hover:text-white">How it works</a>
          <a href="/docs" className="hover:text-white">API</a>
        </div>
      </nav>

      <div className="mx-auto max-w-7xl px-6 pb-20 pt-14 text-center md:pt-20">
        <div className="mb-6 flex justify-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-1.5 backdrop-blur">
            <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
            <ShinyText text="QAOA on Classiq · Ising MRF · Synthetic Aperture Radar" speed={3} color="#cbd5e1" shineColor="#ffffff"
              className="text-xs font-semibold tracking-wide md:text-sm" />
          </div>
        </div>

        <div className="flex justify-center">
          <SplitText text="QuantumSAR" tag="h1" splitType="chars" delay={45} duration={1.1} trigger="load"
            className="text-6xl font-black tracking-tight text-white md:text-8xl" />
        </div>

        <h2 className="mt-4 text-2xl font-bold md:text-4xl">
          <GradientText colors={['#ffb020', '#ff6a3d', '#a855f7', '#60a5fa', '#ffb020']} animationSpeed={6}>
            Quantum optimisation for radar image segmentation
          </GradientText>
        </h2>

        <div className="mx-auto mt-6 max-w-3xl text-lg text-slate-300">
          <BlurText text="Every pixel becomes a spin. Noisy radar images become an Ising energy landscape, solved tile by tile with QAOA and checked against exact classical solvers."
            delay={35} animateBy="words" direction="top" trigger="load" className="justify-center" />
        </div>

        <div className="mt-9 flex flex-wrap justify-center gap-4">
          <button onClick={onStart} data-testid="cta-start"
            className="rounded-xl bg-amber-400 px-6 py-3 font-semibold text-[#111] shadow-[0_0_35px_rgba(255,166,0,0.45)] transition hover:scale-[1.03] hover:bg-amber-300">
            Try the live demo ↓
          </button>
          <a href="#how" className="rounded-xl border border-white/20 bg-white/5 px-6 py-3 font-semibold text-white backdrop-blur transition hover:bg-white/10">
            How it works
          </a>
        </div>

        <div className="mx-auto mt-14 grid max-w-4xl grid-cols-2 gap-4 md:grid-cols-4">
          {STATS.map((s) => (
            <div key={s.label} className="rounded-2xl border border-white/10 bg-[#0b1222]/60 px-4 py-4 backdrop-blur">
              <div className="text-3xl font-black text-white">
                <CountUp to={s.to} duration={2} separator="," suffix={s.suffix} prefix={s.prefix ?? ''} decimals={s.decimals} />
              </div>
              <div className="mt-1 text-xs text-slate-400">{s.label}</div>
            </div>
          ))}
        </div>

        <p data-testid="hero-formula" className="mx-auto mt-10 max-w-3xl rounded-xl border border-white/10 bg-black/30 px-5 py-3 font-mono text-sm text-slate-300 backdrop-blur">
          E(x) = Σ<sub>i</sub> θ<sub>i</sub>(x<sub>i</sub>) + λ Σ<sub>(i,j)</sub> [x<sub>i</sub> ≠ x<sub>j</sub>]
          <span className="text-amber-300"> ⟶ </span> H = Σ h<sub>i</sub>Z<sub>i</sub> + Σ J<sub>ij</sub>Z<sub>i</sub>Z<sub>j</sub>
        </p>
      </div>
    </header>
  )
}
