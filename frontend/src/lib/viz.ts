import type { Grid, Params } from '../api'

export const CLASS_RGB: [number, number, number][] = [
  [30, 38, 58], // background
  [255, 166, 0], // target
  [64, 132, 255], // shadow
]
export const EDGE_RGB: [number, number, number][] = [
  [0, 0, 0],
  [255, 70, 70], // target edge
  [80, 230, 255], // shadow edge
]

export type PixelKind = 'gray' | 'labels' | 'edges'

/** Paint a 2-D grid into a canvas at 1 px per cell (CSS scales it, pixelated). */
export function paint(canvas: HTMLCanvasElement, data: Grid, kind: PixelKind, base?: Grid) {
  const h = data.length
  const w = data[0]?.length ?? 0
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  if (!ctx || !w) return
  const img = ctx.createImageData(w, h)
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const v = data[y][x]
      const o = (y * w + x) * 4
      let rgb: [number, number, number]
      if (kind === 'gray') rgb = [v, v, v]
      else if (kind === 'labels') rgb = CLASS_RGB[v] ?? CLASS_RGB[0]
      else {
        const g = base ? base[y][x] * 0.45 : 0
        rgb = v > 0 ? EDGE_RGB[v] : [g, g, g]
      }
      img.data[o] = rgb[0]
      img.data[o + 1] = rgb[1]
      img.data[o + 2] = rgb[2]
      img.data[o + 3] = 255
    }
  }
  ctx.putImageData(img, 0, 0)
}

export function groundTruthView(labels: Grid, nClasses: number): Grid {
  return nClasses === 3 ? labels : labels.map((r) => r.map((v) => (v === 1 ? 1 : 0)))
}

export function effectiveTile(p: Params, maxQubits = 20): number {
  let t = p.tile
  const per = p.n_classes === 2 ? 1 : p.n_classes
  while (t > 1 && t * t * per > maxQubits) t--
  return t
}

/** Analytic size of the per-tile QAOA circuit (before synthesis). */
export function logicalCircuit(p: Params) {
  const t = effectiveTile(p)
  const K = p.n_classes
  const n = t * t * (K === 2 ? 1 : K)
  const m = K === 2 ? 2 * t * (t - 1) : K * 2 * t * (t - 1) + (t * t * K * (K - 1)) / 2
  return { tile: t, qubits: n, couplings: m, layers: p.p, params: 2 * p.p + n + m }
}

export const fmt = (v: number | undefined, d = 3) => (v === undefined || Number.isNaN(v) ? '–' : v.toFixed(d))

export function modeKind(mode: string): 'live' | 'cached' | 'fallback' | 'classical' {
  if (mode.includes('live')) return 'live'
  if (mode.includes('cached')) return 'cached'
  if (mode.includes('FALLBACK')) return 'fallback'
  return 'classical'
}

export function toCSV(rows: Record<string, unknown>[]): string {
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(r))))
  const esc = (v: unknown) => {
    const s = v === undefined || v === null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))].join('\n')
}
