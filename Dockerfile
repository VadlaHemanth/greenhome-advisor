# Optional repeatable service image. No image build/deployment is claimed.
FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS service
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    GREENHOME_LIVE_GEMINI=false GREENHOME_WARM_MODELS=true
WORKDIR /app
COPY requirements.txt requirements-postgres.txt ./
RUN pip install --no-cache-dir -r requirements-postgres.txt \
    && useradd --create-home --uid 10001 app \
    && mkdir /app/state && chown app:app /app/state
COPY greenhome/ ./greenhome/
COPY models/ ./models/
COPY reports/training_metrics.json ./reports/training_metrics.json
COPY scripts/check_readiness.py scripts/init_shared_budget.py ./scripts/
COPY --from=frontend /build/frontend/dist ./frontend/dist/
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/readiness', timeout=8)"
CMD ["python", "-m", "uvicorn", "greenhome.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers", "--limit-concurrency", "256"]
