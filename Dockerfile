FROM node:22-bookworm-slim AS web
WORKDIR /build
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DB_PATH=/data/p15.sqlite WEB_DIR=/app/web/dist
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates fonts-dejavu-core fonts-dejavu-extra && rm -rf /var/lib/apt/lists/* && useradd --uid 10001 --create-home hub && mkdir /data && chown hub:hub /data
WORKDIR /app
COPY api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ ./api/
COPY --from=web /build/dist ./web/dist
USER hub
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2)"
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
