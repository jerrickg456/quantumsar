#!/usr/bin/env bash
# Publish the repo as a Hugging Face Docker Space.
# Usage: HF_SPACE=<user>/quantumsar ./deploy/huggingface/push_space.sh   (needs `huggingface-cli login`)
set -euo pipefail
: "${HF_SPACE:?set HF_SPACE=<user>/<space>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
git clone "https://huggingface.co/spaces/${HF_SPACE}" "$TMP/space"
rsync -a --delete --exclude .git --exclude .venv --exclude video/build --exclude frontend/node_modules --exclude frontend/dist --exclude 'config.env' \
      --exclude '*.mp4' "$ROOT/" "$TMP/space/"
cp "$ROOT/deploy/huggingface/README.md" "$TMP/space/README.md"   # Space metadata front-matter
cd "$TMP/space"
git lfs install && git lfs track "*.npz" "*.png"
git add -A && git commit -m "Deploy QuantumSAR" && git push
echo "Deployed: https://huggingface.co/spaces/${HF_SPACE}"
