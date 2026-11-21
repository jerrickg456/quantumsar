# QuantumSAR web UI (React + React Bits)

Vite + React + TypeScript + Tailwind v4. Animated components come from
[React Bits](https://reactbits.dev) (TS + Tailwind variants), vendored in
`src/components/reactbits/` with `node scripts/add-reactbits.mjs <Name> ...`:
Aurora, SplitText, BlurText, ShinyText, GradientText, SpotlightCard, CountUp, StarBorder, ClickSpark.

```bash
npm install
npm run dev     # http://localhost:5173, proxies API calls to http://localhost:8000
npm run build   # -> dist/, served by FastAPI at "/"
```

Start the API first: `uvicorn api.main:app --port 8000` (from the repo root).
