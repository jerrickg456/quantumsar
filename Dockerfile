# QuantumSAR: React UI (built with Node) served by FastAPI on $PORT (default 7860).

# ---- 1. build the React front-end ------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 2. Python runtime -------------------------------------------------------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PORT=7860 QUANTUMSAR_ALLOW_LIVE_CLASSIQ=0 HOME=/home/user
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* && useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY --chown=user:user . .
COPY --from=web --chown=user:user /web/dist ./frontend/dist
USER user
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fs "http://localhost:${PORT}/health" || exit 1
CMD ["sh", "scripts/start.sh"]
