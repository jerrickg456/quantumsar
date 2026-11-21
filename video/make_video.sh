#!/usr/bin/env bash
# Rebuild the QuantumSAR demo video end-to-end (re-run after any UI change).
#
#   ./video/make_video.sh                                 # records the deployed app (segments.json app_url)
#   APP_URL=http://localhost:8000 ./video/make_video.sh   # or any running instance
#
# Steps: TTS narration -> paced Playwright recording -> ffmpeg compose -> sync check.
# Outputs: video/out/final.mp4, video/out/final.srt, video/out/thumbnail.png, video/script.md
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then PY="$ROOT/.venv/Scripts/python.exe";
elif [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"; else PY=python3; fi
cd "$HERE"
"$PY" -m playwright install chromium >/dev/null

APP_PID=""
APP_URL="${APP_URL:-$("$PY" -c "import json;print(json.load(open('segments.json'))['app_url'])")}"
if [ "$APP_URL" = "http://localhost:8000" ]; then
  if ! curl -fs "$APP_URL/health" >/dev/null 2>&1; then
    echo "starting QuantumSAR (FastAPI + React UI) on :8000"
    [ -f "$ROOT/frontend/dist/index.html" ] || (cd "$ROOT/frontend" && npm ci && npm run build)
    (cd "$ROOT" && QUANTUMSAR_ALLOW_LIVE_CLASSIQ=0 "$PY" -m uvicorn api.main:app --port 8000 \
        >"$HERE/build_app.log" 2>&1) &
    APP_PID=$!
    for _ in $(seq 1 60); do curl -fs "$APP_URL/health" >/dev/null 2>&1 && break; sleep 1; done
  fi
fi
trap '[ -n "$APP_PID" ] && kill "$APP_PID" 2>/dev/null || true' EXIT

echo "== 1/5 explainer slides";       "$PY" slides.py
echo "== 2/5 narration (edge-tts)";   "$PY" tts.py
echo "== 3/5 screen recording";       "$PY" record.py --url "$APP_URL"
echo "== 4/5 compose (ffmpeg)";       "$PY" compose.py
echo "== 5/5 sync check";             "$PY" check.py
echo "done: $HERE/out/final.mp4"
