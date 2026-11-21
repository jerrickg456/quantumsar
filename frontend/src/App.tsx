import { useState } from 'react'
import ClickSpark from './components/reactbits/ClickSpark/ClickSpark'
import Hero from './components/Hero'
import Demo from './components/Demo'
import Benchmark from './components/Benchmark'
import HowItWorks from './components/HowItWorks'
import type { ImageSource, Params } from './api'

const DEFAULTS: Params = { solver: 'classiq', n_classes: 2, lam: 1.5, tile: 3, p: 2, shots: 1024, sweeps: 2 }

export default function App() {
  const [params, setParams] = useState<Params>(DEFAULTS)
  const [source, setSource] = useState<ImageSource | null>(null)
  return (
    <ClickSpark sparkColor={['#ffb020', '#ffd166', '#60a5fa']} sparkSize={11} sparkRadius={26} sparkCount={10} duration={450}>
      <div className="min-h-screen bg-[#070b14] text-slate-200 antialiased">
        <Hero onStart={() => document.getElementById('demo')?.scrollIntoView({ behavior: 'smooth' })} />
        <Demo params={params} setParams={setParams} onResult={(src) => setSource(src)} />
        <Benchmark source={source} params={params} />
        <HowItWorks />
        <footer className="border-t border-white/10 px-6 py-10 text-center text-sm text-slate-500">
          QuantumSAR · MRF segmentation of SAR images with QAOA on Classiq · FastAPI + React (React Bits)
          <div className="mt-1">Thales SAR use case · synthetic MSTAR-like data · every result labelled with its engine</div>
        </footer>
      </div>
    </ClickSpark>
  )
}
