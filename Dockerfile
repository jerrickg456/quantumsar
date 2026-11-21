# QuantumSAR: FastAPI (port 8000) + Streamlit UI (port $PORT, default 7860)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PORT=7860 QUANTUMSAR_ALLOW_LIVE_CLASSIQ=0 HOME=/home/user
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* && useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY --chown=user:user . .
USER user
EXPOSE 7860 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fs http://localhost:8000/health || exit 1
CMD ["sh", "scripts/start.sh"]
