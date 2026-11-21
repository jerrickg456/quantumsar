import { useEffect, useState } from 'react'
import { Card, SectionTitle } from './ui'
import { api, type BenchRow, type ImageSource, type Params } from '../api'
import { fmt, modeKind, toCSV } from '../lib/viz'
import { SOLVERS } from './Demo'

const SHORT: Record<string, string> = {
  classiq: 'QAOA · Classiq', qaoa_local: 'QAOA · local', annealing: 'Annealing', sa_tiled: 'Tiled SA',
  graphcut: 'Graph cut', icm: 'ICM', otsu: 'Otsu', kmeans: 'k-means',
}
const QUANTUM = new Set(['classiq', 'qaoa_local'])

function Bars({ rows, value, title, unit = '', better, color, testid, digits = 3 }:
  { rows: BenchRow[]; value: (r: BenchRow) => number | undefined; title: string; unit?: string
    better: 'high' | 'low'; color: string; testid: string; digits?: number }) {
  const [grow, setGrow] = useState(false)
  useEffect(() => { setGrow(false); const t = setTimeout(() => setGrow(true), 60); return () => clearTimeout(t) }, [rows])
  const vals = rows.map(value).filter((v): v is number => v !== undefined)
  const max = Math.max(...vals, 1e-9)
  const min = Math.min(...vals)
  const sorted = [...rows].sort((a, b) => ((better === 'high' ? -1 : 1) * ((value(a) ?? 0) - (value(b) ?? 0))))
  return (
    <Card testid={testid} glow={`${color}44`}>
      <div className="flex items-baseline justify-between">
        <div className="font-semibold text-white">{title}</div>
        <div className="text-xs text-slate-400">{better === 'high' ? 'higher is better' : 'lower is better'}</div>
      </div>
      <div className="mt-4 space-y-2">
        {sorted.map((r, i) => {
          const v = value(r)
          const w = v === undefined ? 0 : Math.max(4, (v / max) * 100)
          const best = v !== undefined && (better === 'high' ? v === max : v === min)
          return (
            <div key={r.solver} className="grid grid-cols-[110px_1fr_70px] items-center gap-3 text-sm">
              <span className={`truncate ${QUANTUM.has(r.solver) ? 'font-semibold text-amber-300' : 'text-slate-300'}`}>{SHORT[r.solver] ?? r.solver}</span>
              <div className="h-3 overflow-hidden rounded-full bg-white/5">
                <div className="h-full rounded-full transition-all duration-1000 ease-out"
                  style={{ width: grow ? `${w}%` : '0%', transitionDelay: `${i * 70}ms`,
                    background: QUANTUM.has(r.solver) ? 'linear-gradient(90deg,#ff8a00,#ffd166)' : color,
                    boxShadow: best ? `0 0 12px ${color}` : undefined }} />
              </div>
              <span className="text-right font-mono text-slate-200">{v === undefined ? '–' : v.toFixed(digits)}{unit}</span>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

export default function Benchmark({ source, params }: { source: ImageSource | null; params: Params }) {
  const [rows, setRows] = useState<BenchRow[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [summary, setSummary] = useState<Record<string, any>[]>([])
  useEffect(() => { api.resultsSummary().then(setSummary).catch(() => {}) }, [])
  useEffect(() => { setRows(null) }, [source])

  async function run() {
    if (!source) return
    setBusy(true)
    try { setRows(await api.benchmark(source, params, SOLVERS.map((s) => s.key))) } finally { setBusy(false) }
  }

  function exportCSV() {
    if (!rows) return
    const blob = new Blob([toCSV(rows)], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `quantumsar_benchmark_${source?.sample ?? 'upload'}_${params.n_classes}class.csv`
    a.click()
  }

  const ok = rows?.filter((r) => !r.error) ?? []
  return (
    <section id="benchmark" className="mx-auto max-w-7xl scroll-mt-6 px-6 py-16">
      <SectionTitle kicker="Benchmark" title="Quantum vs. classical, same image"
        sub="All MRF solvers minimise the same energy, so energy shows optimisation quality; IoU and accuracy show segmentation quality." />
      <div className="flex flex-wrap items-center gap-3">
        <button data-testid="bench-btn" onClick={run} disabled={busy || !source}
          className="rounded-xl border border-amber-400/60 bg-amber-400/10 px-5 py-2.5 font-semibold text-amber-200 transition hover:bg-amber-400/20 disabled:opacity-50">
          {busy ? 'Running every solver…' : '⚡ Benchmark all solvers'}
        </button>
        {rows && <button data-testid="export-csv" onClick={exportCSV}
          className="rounded-xl border border-white/15 px-4 py-2.5 text-sm text-slate-200 hover:bg-white/5">⬇ Export CSV</button>}
        <span className="text-sm text-slate-500">{params.n_classes}-class · λ={params.lam} · tile {params.tile}×{params.tile} · p={params.p}</span>
      </div>

      {rows && (
        <>
          <Card testid="bench-table" className="mt-6 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wider text-slate-400">
                <tr>{['Solver', 'Engine', 'Accuracy', 'IoU', 'Dice', 'Runtime (s)', 'Energy', 'Tiles'].map((h) => <th key={h} className="px-2 py-2">{h}</th>)}</tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.solver} data-testid={`row-${r.solver}`} className={`border-t border-white/5 ${QUANTUM.has(r.solver) ? 'bg-amber-400/[0.06]' : ''}`}>
                    <td className={`px-2 py-2 font-semibold ${QUANTUM.has(r.solver) ? 'text-amber-300' : 'text-slate-100'}`}>{SHORT[r.solver] ?? r.solver}</td>
                    <td className="px-2 py-2"><EngineTag mode={r.mode ?? r.error ?? ''} /></td>
                    <td className="px-2 py-2 font-mono">{fmt(r.accuracy)}</td>
                    <td className="px-2 py-2 font-mono">{fmt(r.iou)}</td>
                    <td className="px-2 py-2 font-mono">{fmt(r.dice)}</td>
                    <td className="px-2 py-2 font-mono">{fmt(r.runtime_s)}</td>
                    <td className="px-2 py-2 font-mono">{fmt(r.energy, 1)}</td>
                    <td className="px-2 py-2 font-mono text-slate-400">{r.tiles_solved ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <Bars testid="chart-iou" rows={ok} value={(r) => r.iou} title="Accuracy (IoU)" better="high" color="#60a5fa" />
            <Bars testid="chart-runtime" rows={ok} value={(r) => r.runtime_s} title="Runtime" unit=" s" better="low" color="#a78bfa" />
            <Bars testid="chart-energy" rows={ok} value={(r) => r.energy} title="MRF energy reached" better="low" color="#34d399" digits={1} />
          </div>
        </>
      )}

      {summary.length > 0 && (
        <details className="mt-8 rounded-2xl border border-white/10 bg-white/[0.02] p-4">
          <summary className="cursor-pointer font-semibold text-slate-200">Dataset-wide results ({summary[0]?.images ?? 50} synthetic SAR images)</summary>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-400">
                <tr>{['Classes', 'Solver', 'Images', 'Accuracy', 'IoU', 'Dice', 'Median runtime (s)', 'Energy'].map((h) => <th key={h} className="px-2 py-1">{h}</th>)}</tr>
              </thead>
              <tbody>
                {summary.map((r, i) => (
                  <tr key={i} className="border-t border-white/5">
                    <td className="px-2 py-1">{r.n_classes}</td><td className="px-2 py-1">{r.name}</td><td className="px-2 py-1">{r.images}</td>
                    <td className="px-2 py-1 font-mono">{fmt(r.accuracy)}</td><td className="px-2 py-1 font-mono">{fmt(r.iou)}</td>
                    <td className="px-2 py-1 font-mono">{fmt(r.dice)}</td><td className="px-2 py-1 font-mono">{fmt(r.runtime_s_median)}</td>
                    <td className="px-2 py-1 font-mono">{fmt(r.energy, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  )
}

function EngineTag({ mode }: { mode: string }) {
  const k = modeKind(mode)
  const cls = { live: 'text-emerald-300', cached: 'text-sky-300', fallback: 'text-orange-300', classical: 'text-slate-400' }[k]
  return <span className={`text-xs ${cls}`}>{mode}</span>
}
