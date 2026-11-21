#!/usr/bin/env bash
# Rebuild the QuantumSAR demo video end-to-end (re-run after any UI change).
#
#   ./video/make_video.sh                 # starts the app itself on :8501
#   APP_URL=http://host:port ./video/make_video.sh   # use an already running app
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
if [ -z "${APP_URL:-}" ]; then
  APP_URL="http://localhost:8000"
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

echo "== 1/4 narration (edge-tts)";   "$PY" tts.py
echo "== 2/4 screen recording";       "$PY" record.py --url "$APP_URL"
echo "== 3/4 compose (ffmpeg)";       "$PY" compose.py
echo "== 4/4 sync check";             "$PY" check.py
echo "done: $HERE/out/final.mp4"
