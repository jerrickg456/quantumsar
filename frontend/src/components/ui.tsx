import { useEffect, useRef, type ReactNode } from 'react'
import SpotlightCard from './reactbits/SpotlightCard/SpotlightCard'
import ShinyText from './reactbits/ShinyText/ShinyText'
import type { Grid } from '../api'
import { modeKind, paint, type PixelKind } from '../lib/viz'

export function Card({ children, className = '', testid, glow = 'rgba(255,166,0,0.22)' }:
  { children: ReactNode; className?: string; testid?: string; glow?: string }) {
  return (
    <SpotlightCard data-testid={testid} spotlightColor={glow} intensity={0.18} spotlightSize={320}
      className={`rounded-2xl border border-white/10 bg-[#0d1424]/80 backdrop-blur-md p-5 ${className}`}>
      {children}
    </SpotlightCard>
  )
}

export function SectionTitle({ kicker, title, sub }: { kicker: string; title: string; sub?: string }) {
  return (
    <div className="mb-6">
      <div className="text-xs font-semibold uppercase tracking-[0.25em] text-amber-400/90">{kicker}</div>
      <h2 className="mt-1 text-3xl font-bold text-white md:text-4xl">{title}</h2>
      {sub && <p className="mt-2 max-w-3xl text-slate-400">{sub}</p>}
    </div>
  )
}

export function Toggle({ label, checked, onChange, disabled, testid }:
  { label: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; testid?: string }) {
  return (
    <button type="button" data-testid={testid} disabled={disabled} onClick={() => onChange(!checked)}
      className={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm transition
        ${disabled ? 'opacity-40' : 'hover:bg-white/5'}`}>
      <span className="text-slate-200">{label}</span>
      <span className={`relative h-6 w-11 shrink-0 rounded-full transition ${checked ? 'bg-amber-400' : 'bg-white/15'}`}>
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${checked ? 'left-[22px]' : 'left-0.5'}`} />
      </span>
    </button>
  )
}

export function Slider({ label, value, min, max, step = 1, onChange, hint, testid, format }:
  { label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void
    hint?: string; testid?: string; format?: (v: number) => string }) {
  return (
    <label data-testid={testid} className="block rounded-xl px-3 py-2">
      <div className="flex items-baseline justify-between text-sm">
        <span className="text-slate-300">{label}</span>
        <span className="font-mono font-semibold text-amber-300">{format ? format(value) : value}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} className="qs-range mt-2 w-full" />
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </label>
  )
}

export function PixelPanel({ title, data, kind, base, testid, placeholder, accent }:
  { title: string; data?: Grid | null; kind: PixelKind; base?: Grid; testid?: string; placeholder?: string; accent?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    if (ref.current && data) paint(ref.current, data, kind, base)
  }, [data, kind, base])
  return (
    <div data-testid={testid} className="group flex flex-col">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-200">
        <span className="h-2 w-2 rounded-full" style={{ background: accent ?? '#94a3b8' }} />
        {title}
      </div>
      <div className="relative aspect-square overflow-hidden rounded-xl border border-white/10 bg-[#111a2e] shadow-inner">
        {data ? (
          <canvas ref={ref} className="h-full w-full transition duration-500 group-hover:scale-[1.03]"
            style={{ imageRendering: 'pixelated' }} />
        ) : (
          <div className="flex h-full items-center justify-center p-4 text-center text-sm text-slate-500">{placeholder}</div>
        )}
      </div>
    </div>
  )
}

const MODE_STYLE = {
  live: { bg: 'bg-emerald-500/15 border-emerald-400/50', color: '#6ee7b7', shine: '#ecfdf5', label: 'LIVE ON CLASSIQ' },
  cached: { bg: 'bg-sky-500/15 border-sky-400/50', color: '#7dd3fc', shine: '#f0f9ff', label: 'CLASSIQ · CACHED RUN' },
  fallback: { bg: 'bg-orange-500/15 border-orange-400/50', color: '#fdba74', shine: '#fff7ed', label: 'LOCAL FALLBACK' },
  classical: { bg: 'bg-slate-500/15 border-slate-400/40', color: '#cbd5e1', shine: '#ffffff', label: 'CLASSICAL' },
}

export function ModeBadge({ mode }: { mode: string }) {
  const s = MODE_STYLE[modeKind(mode)]
  return (
    <div data-testid="mode-badge" className={`inline-flex flex-wrap items-center gap-3 rounded-full border px-4 py-1.5 ${s.bg}`}>
      <ShinyText text={s.label} color={s.color} shineColor={s.shine} speed={2.5} className="text-xs font-bold tracking-widest" />
      <span className="text-sm text-slate-200">{mode}</span>
    </div>
  )
}

export function Pill({ active, children, onClick, testid }:
  { active: boolean; children: ReactNode; onClick: () => void; testid?: string }) {
  return (
    <button type="button" data-testid={testid} onClick={onClick}
      className={`rounded-xl border px-3 py-2 text-left text-sm transition
        ${active ? 'border-amber-400/70 bg-amber-400/15 text-amber-200 shadow-[0_0_18px_rgba(255,166,0,0.25)]'
          : 'border-white/10 bg-white/[0.03] text-slate-300 hover:border-white/25 hover:bg-white/[0.06]'}`}>
      {children}
    </button>
  )
}
