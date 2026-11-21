#!/bin/sh
# One process serves everything: REST API + React UI (frontend/dist) on $PORT.
set -e
exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-7860}"
