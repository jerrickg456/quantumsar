import { useEffect, useMemo, useRef, useState } from 'react'
import StarBorder from './reactbits/StarBorder/StarBorder'
import CountUp from './reactbits/CountUp/CountUp'
import { Card, ModeBadge, Pill, PixelPanel, SectionTitle, Slider, Toggle } from './ui'
import { api, fileToB64, type Grid, type Health, type ImageSource, type Job, type Params, type Sample, type SegResult } from '../api'
import { fmt, groundTruthView, logicalCircuit, paint } from '../lib/viz'

export const SOLVERS: { key: string; label: string; sub: string }[] = [
  { key: 'classiq', label: 'Quantum · QAOA on Classiq', sub: 'cached Classiq runs, else local QAOA' },
  { key: 'qaoa_local', label: 'Quantum · QAOA local sim', sub: 'exact statevector simulator' },
  { key: 'annealing', label: 'Simulated annealing', sub: 'global MRF, classical' },
  { key: 'sa_tiled', label: 'Quantum-inspired SA', sub: 'same tile QUBOs' },
  { key: 'graphcut', label: 'Graph cut', sub: 'exact (2-class) / α-expansion' },
  { key: 'icm', label: 'ICM', sub: 'greedy local' },
  { key: 'otsu', label: 'Otsu', sub: 'threshold' },
  { key: 'kmeans', label: 'k-means', sub: 'clustering' },
]

/** Client-side grayscale preview of an uploaded PNG/JPG (same downscaling rule as the API). */
async function previewGrid(file: File): Promise<Grid | null> {
  if (file.name.toLowerCase().endsWith('.npy')) return null
  const bmp = await createImageBitmap(file)
  const f = Math.max(1, Math.ceil(Math.max(bmp.width, bmp.height) / 128))
  const w = Math.floor(bmp.width / f), h = Math.floor(bmp.height / f)
  const c = document.createElement('canvas')
  c.width = w; c.height = h
  const ctx = c.getContext('2d')!
  ctx.drawImage(bmp, 0, 0, w, h)
  const d = ctx.getImageData(0, 0, w, h).data
  return Array.from({ length: h }, (_, y) => Array.from({ length: w }, (_, x) => {
    const o = (y * w + x) * 4
    return Math.round(0.299 * d[o] + 0.587 * d[o + 1] + 0.114 * d[o + 2])
  }))
}

export type DemoState = {
  source: ImageSource
  sample: Sample | null
  params: Params
}

function Thumb({ name, active, onClick }: { name: string; active: boolean; onClick: () => void }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    let live = true
    api.sample(name).then((s) => live && ref.current && paint(ref.current, s.display, 'gray'))
    return () => { live = false }
  }, [name])
  const kind = name.split('_').slice(2).join(' ')
  return (
    <button type="button" onClick={onClick} data-testid={`thumb-${name}`} title={name}
      className={`group relative overflow-hidden rounded-lg border transition ${active ? 'border-amber-400 shadow-[0_0_16px_rgba(255,166,0,0.45)]' : 'border-white/10 hover:border-white/40'}`}>
      <canvas ref={ref} className="aspect-square w-full" style={{ imageRendering: 'pixelated' }} />
      <span className="absolute inset-x-0 bottom-0 bg-black/60 px-1 py-0.5 text-[10px] text-slate-200">{kind}</span>
    </button>
  )
}

export default function Demo({ params, setParams, onResult }:
  { params: Params; setParams: (p: Params) => void; onResult: (src: ImageSource, s: Sample | null) => void }) {
  const [samples, setSamples] = useState<string[]>([])
  const [name, setName] = useState('sar_002_low_snr')
  const [sample, setSample] = useState<Sample | null>(null)
  const [upload, setUpload] = useState<{ b64: string; name: string; preview: Grid | null } | null>(null)
  const [edges, setEdges] = useState(false)
  const [single, setSingle] = useState(true)
  const [res, setRes] = useState<SegResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [cache, setCache] = useState<boolean | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [showAll, setShowAll] = useState(false)

  const source: ImageSource = useMemo(() => (upload ? { image_b64: upload.b64 } : { sample: name }), [upload, name])

  useEffect(() => { api.samples().then((s) => setSamples(s)) }, [])
  useEffect(() => {   // Classiq connection status (re-checked every 20 s)
    const tick = () => api.health().then(setHealth).catch(() => {})
    tick()
    const t = setInterval(tick, 20000)
    return () => clearInterval(t)
  }, [])
  useEffect(() => {
    if (upload) return
    api.sample(name).then((s) => { setSample(s); setRes(null) })
  }, [name, upload])
  useEffect(() => { onResult(source, upload ? null : sample) }, [source, sample]) // eslint-disable-line
  useEffect(() => {
    setCache(null)
    api.cacheStatus(source, params).then((c) => setCache(c.cached)).catch(() => setCache(null))
  }, [source, params])

  const set = (patch: Partial<Params>) => setParams({ ...params, ...patch })
  const circuit = logicalCircuit(params)

  const liveOn = !!health?.live_classiq_enabled
  const willRunLive = params.solver === 'classiq' && cache === false && liveOn

  async function run() {
    setBusy(true)
    setErr(null)
    setJob(null)
    try {
      if (willRunLive) {
        // live Classiq run: background job + progress polling (takes minutes)
        let j = await api.createJob(source, params, edges, single)
        setJob(j)
        while (j.status === 'queued' || j.status === 'running') {
          await new Promise((r) => setTimeout(r, 1500))
          j = await api.job(j.id)
          setJob(j)
        }
        if (j.status === 'error') throw new Error(j.error)
        setRes(j.result!)
        setCache(true)
      } else {
        setRes(await api.segment(source, params, edges, single))
      }
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  const visible = showAll ? samples : samples.slice(0, 10)
  const gt = !upload && sample?.labels ? groundTruthView(sample.labels, params.n_classes) : null
  const display = res?.display ?? (upload ? upload.preview : sample?.display) ?? null
  const info = res?.info ?? {}
  const synth = info.circuit && info.circuit.depth ? info.circuit : info.cached_meta?.tiling?.circuit

  return (
    <section id="demo" className="mx-auto max-w-7xl scroll-mt-6 px-6 py-16">
      <SectionTitle kicker="Live demo" title="Segment a radar image"
        sub="Pick a noisy SAR chip, choose a solver and run it. Every result is labelled with the engine that produced it." />

      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        {/* ------------------------------------------------ controls */}
        <Card testid="controls" className="h-fit">
          <div className="text-xs font-semibold uppercase tracking-widest text-slate-400">Image</div>
          <div className="mt-3 grid grid-cols-5 gap-2">
            {visible.map((n) => (
              <Thumb key={n} name={n} active={!upload && n === name} onClick={() => { setUpload(null); setName(n) }} />
            ))}
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <button type="button" data-testid="show-all" onClick={() => setShowAll(!showAll)}
              className="flex items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/[0.04] px-3 py-3 text-sm font-semibold text-slate-200 transition hover:border-white/35 hover:bg-white/[0.08]">
              <span className="text-lg leading-none">{showAll ? '▴' : '▦'}</span>
              {showAll ? 'Show fewer' : `All ${samples.length} samples`}
            </button>
            <label data-testid="upload-btn"
              className="flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-amber-400/60 bg-amber-400/10 px-3 py-3 text-sm font-semibold text-amber-200 transition hover:bg-amber-400/20 hover:shadow-[0_0_18px_rgba(255,166,0,0.3)]">
              <span className="text-lg leading-none">⬆</span>
              Upload image
              <input type="file" accept=".png,.jpg,.jpeg,.npy" className="hidden" onChange={async (e) => {
                const f = e.target.files?.[0]
                if (f) { setUpload({ b64: await fileToB64(f), name: f.name, preview: await previewGrid(f) }); setRes(null) }
                e.target.value = ''
              }} />
            </label>
          </div>
          <div data-testid="sample-name" className="mt-2 truncate font-mono text-xs text-amber-300">{upload ? `uploaded: ${upload.name}` : name}</div>
          <div className="mt-1 text-[11px] leading-snug text-slate-500">
            Upload a grayscale image (PNG / JPG / .npy). Large images are block-averaged down to ≤128 px.
            Uploads have no ground truth, so accuracy / IoU are not shown.
          </div>

          <div className="mt-5 text-xs font-semibold uppercase tracking-widest text-slate-400">Solver</div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {SOLVERS.map((s) => (
              <Pill key={s.key} testid={`solver-${s.key}`} active={params.solver === s.key} onClick={() => set({ solver: s.key })}>
                <div className="font-semibold leading-tight">{s.label}</div>
                <div className="mt-0.5 text-[11px] text-slate-400">{s.sub}</div>
              </Pill>
            ))}
          </div>

          <div className="mt-5 space-y-1">
            <Toggle testid="toggle-3class" label="3 classes (target / shadow / background)" checked={params.n_classes === 3}
              onChange={(v) => set({ n_classes: v ? 3 : 2 })} />
            <Toggle testid="toggle-edges" label="Edge detection" checked={edges} onChange={setEdges} />
            <Toggle testid="toggle-single" label="Single-pixel edges" checked={single} onChange={setSingle} disabled={!edges} />
          </div>

          <div className="mt-4 space-y-1 border-t border-white/10 pt-3">
            <Slider label="λ smoothness" value={params.lam} min={0} max={5} step={0.1} onChange={(v) => set({ lam: v })} format={(v) => v.toFixed(1)} />
            <Slider testid="slider-tile" label="Tile size" value={params.tile} min={2} max={4} onChange={(v) => set({ tile: v })}
              format={(v) => `${v}×${v}`} hint={`${circuit.qubits} qubits per tile${circuit.tile !== params.tile ? ` (reduced to ${circuit.tile}×${circuit.tile})` : ''}`} />
            <Slider label="QAOA depth p" value={params.p} min={1} max={4} onChange={(v) => set({ p: v })} />
            <Slider label="Shots" value={Math.log2(params.shots)} min={7} max={12} onChange={(v) => set({ shots: 2 ** v })} format={() => String(params.shots)} />
            <Slider label="Tiling sweeps" value={params.sweeps} min={1} max={4} onChange={(v) => set({ sweeps: v })} />
          </div>

          {params.solver === 'classiq' && (
            <div data-testid="cache-hint" className={`mt-4 rounded-xl border px-3 py-2 text-xs ${cache ? 'border-sky-400/40 bg-sky-500/10 text-sky-200' : 'border-orange-400/40 bg-orange-500/10 text-orange-200'}`}>
              {cache === null ? 'checking Classiq cache…' : cache
                ? '✓ A Classiq result for this image and these settings is already stored: instant.'
                : liveOn
                  ? '⚛ Not run on Classiq yet: this will execute LIVE on the Classiq cloud simulator (about 2–4 minutes). Progress is shown below.'
                  : 'No stored Classiq run for these settings and live Classiq is off on this server: the same QAOA circuit runs on the local simulator (labelled FALLBACK).'}
            </div>
          )}

          <StarBorder as="button" data-testid="run-btn" onClick={run} disabled={busy} color="#ffb020" duration={5}
            className="mt-5 w-full" radius={14} stars={2} glow={0.8} backgroundColor="#1a1407" textColor="#ffd48a">
            <span className="flex items-center justify-center gap-2 py-1 text-base font-bold">
              {busy ? <><span className="h-4 w-4 animate-spin rounded-full border-2 border-amber-300 border-t-transparent" /> Solving…</> : '▶ Run segmentation'}
            </span>
          </StarBorder>
          {job && job.status !== 'done' && <JobProgress job={job} />}
          {err && <div className="mt-3 rounded-lg bg-red-500/15 p-2 text-xs text-red-200">{err}</div>}
          <ClassiqStatus health={health} />
        </Card>

        {/* ------------------------------------------------ results */}
        <div className="space-y-6">
          <Card testid="panels">
            <div className={`grid gap-4 ${res?.edge_classes ? 'grid-cols-2 xl:grid-cols-4' : 'grid-cols-1 sm:grid-cols-3'}`}>
              <PixelPanel testid="panel-input" title="SAR input (log scale)" data={display} kind="gray" accent="#e2e8f0" />
              <PixelPanel testid="panel-gt" title="Ground truth" data={gt} kind="labels" accent="#22c55e" placeholder="not available for uploads" />
              <PixelPanel testid="panel-seg" title="Segmentation" data={res?.labels} kind="labels" accent="#ffa600"
                placeholder={busy ? 'solving…' : 'press Run segmentation'} />
              {res?.edge_classes && (
                <PixelPanel testid="panel-edges" title="Edges (red target · cyan shadow)" data={res.edge_classes} kind="edges" base={display ?? undefined} accent="#ff4646" />
              )}
            </div>
            <div className="mt-4 flex flex-wrap gap-4 text-xs text-slate-400">
              <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-[#ffa600]" />target</span>
              <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-[#4084ff]" />shadow</span>
              <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-[#1e263a] ring-1 ring-white/20" />background</span>
            </div>
            {res && <div className="mt-4"><ModeBadge mode={res.mode} /></div>}
          </Card>

          {res && (
            <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
              <Card testid="metrics" glow="rgba(96,165,250,0.22)">
                <div className="text-xs font-semibold uppercase tracking-widest text-slate-400">Metrics</div>
                <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {[
                    ['Accuracy', res.metrics?.accuracy, 100, '%', 1],
                    ['IoU', res.metrics?.iou, 1, '', 3],
                    ['Dice', res.metrics?.dice, 1, '', 3],
                    ['Runtime (s)', res.runtime_s, 1, '', res.runtime_s < 1 ? 3 : 1],
                  ].map(([label, v, k, suf, d]) => (
                    <div key={label as string} className="rounded-xl bg-white/[0.04] p-3">
                      <div className="whitespace-nowrap text-2xl font-black text-white">
                        {v === undefined ? '–' : <CountUp key={`${label}-${v}`} to={(v as number) * (k as number)} duration={1.2} decimals={d as number} suffix={suf as string} trigger="load" />}
                      </div>
                      <div className="text-xs text-slate-400">{label as string}</div>
                    </div>
                  ))}
                </div>
                {info.served_from_cache_s !== undefined && (
                  <div className="mt-2 text-xs text-sky-300/80">Runtime = wall time of the original Classiq cloud run (served from cache in {info.served_from_cache_s.toFixed(3)} s).</div>
                )}
                <div className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                  <Kv k="MRF energy" v={fmt(res.energy, 1)} />
                  {Object.entries(res.metrics ?? {}).filter(([k]) => !['accuracy', 'iou', 'dice'].includes(k))
                    .map(([k, v]) => <Kv key={k} k={k.replace(/_/g, ' ')} v={fmt(v)} />)}
                </div>
                {'tiles_solved' in info && (
                  <div data-testid="tiles-card" className="mt-4 grid grid-cols-1 gap-x-6 border-t border-white/10 pt-3 text-sm sm:grid-cols-2">
                    <Kv k="tiles solved (quantum)" v={String(info.tiles_solved)} />
                    <Kv k="batched jobs" v={String(info.batches)} />
                    <Kv k="qubits / tile" v={String(info.max_qubits)} />
                    {info.qaoa_mean_p_opt !== undefined && <>
                      <Kv k="P(optimum) after QAOA" v={`${(info.qaoa_mean_p_opt * 100).toFixed(1)}%`} hi />
                      <Kv k="P(optimum) random guess" v={`${(info.qaoa_mean_p_opt_uniform * 100).toFixed(2)}%`} />
                      <Kv k="tiles at exact optimum" v={`${(info.qaoa_found_opt_rate * 100).toFixed(1)}%`} hi />
                    </>}
                  </div>
                )}
              </Card>

              <Card testid="circuit-card" glow="rgba(168,85,247,0.25)">
                <div className="text-xs font-semibold uppercase tracking-widest text-slate-400">Quantum circuit per tile</div>
                <CircuitDiagram qubits={Math.min(circuit.qubits, 12)} />
                <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                  <Kv k="qubits" v={String(circuit.qubits)} hi />
                  <Kv k="ZZ couplings" v={String(circuit.couplings)} />
                  <Kv k="QAOA layers p" v={String(circuit.layers)} />
                  <Kv k="parameters" v={String(circuit.params)} />
                  {synth?.depth && <><Kv k="Classiq width" v={String(synth.width)} hi /><Kv k="Classiq depth" v={String(synth.depth)} hi /></>}
                </div>
              </Card>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

function JobProgress({ job }: { job: Job }) {
  const pct = Math.round(job.progress * 100)
  return (
    <div data-testid="job-progress" className="mt-4 rounded-xl border border-emerald-400/30 bg-emerald-500/10 p-3 text-xs text-emerald-100">
      <div className="flex justify-between font-semibold">
        <span>{job.status === 'queued' ? `Queued for Classiq${job.queue_position ? ` (${job.queue_position} ahead)` : ''}` : 'Running live on Classiq'}</span>
        <span className="font-mono">{pct}% · {job.elapsed_s ?? 0}s</span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-amber-300 transition-all duration-700" style={{ width: `${Math.max(pct, 3)}%` }} />
      </div>
      <div className="mt-2 truncate text-emerald-200/80">{job.stage}</div>
    </div>
  )
}

function ClassiqStatus({ health }: { health: Health | null }) {
  if (!health) return null
  const live = health.live_classiq_enabled
  const ok = health.classiq?.ok
  const [dot, text] = !live ? ['bg-slate-500', 'Live Classiq off on this server (stored Classiq runs only)']
    : ok === true ? ['bg-emerald-400 animate-pulse', 'Classiq connected: live quantum runs enabled']
    : ok === false ? ['bg-red-400', `Classiq login failed: ${health.classiq.msg}`]
    : ['bg-amber-400 animate-pulse', 'Connecting to Classiq…']
  return (
    <div data-testid="classiq-status" className="mt-3 flex items-center gap-2 text-xs text-slate-400">
      <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />{text}
    </div>
  )
}

function Kv({ k, v, hi }: { k: string; v: string; hi?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-white/5 py-1">
      <span className="text-slate-400">{k}</span>
      <span className={`font-mono ${hi ? 'text-amber-300' : 'text-slate-100'}`}>{v}</span>
    </div>
  )
}

/** Schematic of one QAOA layer: H on all qubits, ZZ/RZ cost block, RX mixer. */
function CircuitDiagram({ qubits }: { qubits: number }) {
  const rows = Math.max(qubits, 2)
  const h = rows * 14 + 16
  return (
    <svg viewBox={`0 0 320 ${h}`} className="mt-3 w-full">
      {Array.from({ length: rows }).map((_, i) => (
        <g key={i}>
          <line x1={20} x2={310} y1={12 + i * 14} y2={12 + i * 14} stroke="#334155" strokeWidth={1} />
          <text x={4} y={15 + i * 14} fontSize={8} fill="#64748b">q{i}</text>
          <rect x={30} y={6 + i * 14} width={14} height={12} rx={2} fill="#1e3a8a" />
          <text x={34} y={15 + i * 14} fontSize={8} fill="#bfdbfe">H</text>
          <rect x={250} y={6 + i * 14} width={26} height={12} rx={2} fill="#14532d" />
          <text x={252} y={15 + i * 14} fontSize={7} fill="#bbf7d0">RX 2β</text>
        </g>
      ))}
      <rect x={70} y={4} width={160} height={rows * 14} rx={6} fill="rgba(255,166,0,0.12)" stroke="#ffa600" />
      <text x={150} y={rows * 7 + 4} fontSize={11} textAnchor="middle" fill="#ffd48a">e^(−iγ H_C)</text>
      <text x={150} y={rows * 7 + 18} fontSize={8} textAnchor="middle" fill="#fbbf24">RZ(2γh) · CX–RZ(2γJ)–CX</text>
      <text x={290} y={h - 2} fontSize={8} textAnchor="end" fill="#64748b">× p layers</text>
    </svg>
  )
}
