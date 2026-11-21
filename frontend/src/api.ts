// Typed client for the QuantumSAR FastAPI backend (same origin in production).

export type Params = {
  solver: string
  n_classes: number
  lam: number
  tile: number
  p: number
  shots: number
  sweeps: number
}

export type Grid = number[][]

export type Sample = { name: string; image: Grid; display: Grid; labels: Grid | null }

export type SegResult = {
  labels: Grid
  display: Grid
  edges?: Grid
  edge_classes?: Grid
  mode: string
  solver: string
  solver_name: string
  runtime_s: number
  energy: number
  metrics?: Record<string, number>
  info: Record<string, any>
}

export type BenchRow = {
  solver: string
  name: string
  mode?: string
  runtime_s?: number
  energy?: number
  accuracy?: number
  iou?: number
  dice?: number
  tiles_solved?: number
  error?: string
}

export type ImageSource = { sample?: string; image_b64?: string }

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error((await r.text()) || r.statusText)
  return r.json() as Promise<T>
}

export const api = {
  samples: async (): Promise<string[]> => (await fetch('/samples')).json(),
  sample: async (name: string): Promise<Sample> => (await fetch(`/samples/${name}`)).json(),
  health: async () => (await fetch('/health')).json(),
  segment: (src: ImageSource, params: Params, edges: boolean, single_edges: boolean) =>
    post<SegResult>('/segment', { ...src, params, edges, single_edges }),
  benchmark: (src: ImageSource, params: Params, solvers: string[]) =>
    post<BenchRow[]>('/benchmark', { ...src, params, solvers }),
  cacheStatus: (src: ImageSource, params: Params) =>
    post<{ cached: boolean; live_enabled: boolean; meta: Record<string, any> | null }>('/cache-status', { ...src, params }),
  resultsSummary: async (): Promise<Record<string, any>[]> => (await fetch('/results/summary')).json(),
}

export async function fileToB64(file: File): Promise<string> {
  const buf = new Uint8Array(await file.arrayBuffer())
  let s = ''
  for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000))
  return btoa(s)
}
